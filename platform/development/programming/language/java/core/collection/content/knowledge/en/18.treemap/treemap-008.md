# Null Policy, Key Mutability, and Comparison Consistency

## 1. Three Factors That Determine Whether TreeMap Represents Keys Correctly

TreeMap needs an ordering relation to place keys into the tree and to find them again through comparisons.

Therefore, simply creating a TreeMap and calling put does not mean the key design is complete. Three questions must be answered:

1. Are null keys and null values allowed?
2. Does the information used to identify and order keys remain stable while the key is in the map?
3. Does the "compares equal to 0" relation match the key's equals relation?

These three issues are related, but they must not be lumped into a vague rule like "keys must be good."

A Comparator can order consistently yet merge keys that differ by equals. A key class with a correct equals/hashCode can still be misused if the sorting field is modified after put. A map that allows null values does not mean it also allows null keys.

This article separates each condition, provides runnable examples, and clarifies what is part of the public contract versus what is merely an observed result when keys are intentionally misused.

## 2. Keys, Values, and Ordering Have Different Roles

| Component | Role in TreeMap |
| --- | --- |
| Key | Determines the mapping's position through the ordering relation |
| Value | Data associated with the key; does not determine the default lookup path |
| `compareTo`/Comparator | Decides whether to go left, go right, or treat a key as already equivalent |
| `equals` | Object equality rule and the foundation of the general Map contract |
| State used for ordering | Must continue to match the position where the key was organized in the tree |

TreeMap does not use a key's hash to choose a bucket like HashMap does. That does not mean you can ignore the equals/hashCode contract of a general-purpose key type in Java; it only means TreeMap's lookup path relies on comparison.

A key may be used in other structures, and operations such as equals/hashCode on the map itself also have their own contracts. Type design should not work for one call and break when moved to another context.

## 3. Null Policy: Distinguishing Keys from Values

### 3.1. Natural order does not accept null keys

`new TreeMap<>()` uses the natural order of keys. Keys must be mutually comparable; null is not a valid key in a natural order configuration.

`put`(null, value) is rejected with a NullPointerException. Do not assume null is "smallest by default" just because null can appear in some other Map implementations.

The [Java 17 TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) documentation specifies the key requirements and the exceptions related to natural order or a Comparator that does not accept null.

### 3.2. A custom Comparator can allow null keys

If the problem intentionally requires null keys, you can choose an ordering relation that accepts null:

```java
Comparator<String> order =
        Comparator.nullsFirst(Comparator.naturalOrder());
Map<String, Integer> map = new TreeMap<>(order);
```

This is an illustrative declaration snippet in a context with the appropriate imports.

`nullsFirst` treats null as coming before other keys; nullsLast treats null as coming after. Non-null keys are compared using the inner Comparator.

There is still only one position for the null key, because comparing null with null returns 0. Calling `put` again with a null key updates the mapping at that position rather than creating infinite null entries.

### 3.3. Null values are allowed independently of the key policy

A TreeMap using natural order can still hold "beta" → null. Values do not need to be compared to locate the key "beta".

Therefore, the policy table can be:

| Configuration | Null Key | Null Value |
| --- | --- | --- |
| TreeMap using natural order | Not allowed | Allowed |
| Custom Comparator that does not handle null | Depends on the Comparator, usually rejected during comparison | Allowed |
| Comparator that validly accepts null | Can be allowed | Allowed |

Do not infer the key policy from the value policy or vice versa.

### 3.4. `get` returning null has two possibilities

`get`("beta") returning null can happen because:

- There is no key "beta".
- There is a key "beta", but its value is null.

Use containsKey when you need to distinguish existence. `getOrDefault` only returns the fallback value when the key is absent; it does not replace an existing mapping whose value is null with the fallback value.

Similarly, put/remove returning null is not always enough to infer whether a mapping existed before the operation.

If you check existence and then perform another step on shared data, you must consider the atomicity of the entire sequence; TreeMap is not synchronized by default.

### 3.5. Null key object and null field are two different layers

A Comparator comparing Person by name may need a policy for a null name. That is different from the entire Person object being null.

Wrapping the name Comparator with nullsLast only handles a null name value when an object is already present to extract the field. To allow a null key object itself, you must handle it at the appropriate outer layer.

You need to identify exactly where null can appear, rather than wrapping arbitrarily and hoping all cases are covered.

### 3.6. Do not confuse the two kinds of null Comparator arguments

Passing a null Comparator to the TreeMap constructor means using natural order.

However, passing null as the inner Comparator to nullsFirst/nullsLast has a different meaning: by those methods' contracts, all non-null values are considered equal.

Therefore, Comparator.nullsFirst(null) does not automatically mean "null first, and other values in natural order." If used for keys "a" and "b", the two non-null keys can end up at the same comparison position.

Explicitly pass Comparator.naturalOrder() or a proper Comparator for non-null values. See [Java 17 Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

## 4. Java 17 Example: natural order, nullsFirst, and nullsLast

Save as **TreeMapNullPolicy.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapNullPolicy {
    public static void main(String[] args) {
        NavigableMap<String, String> natural = new TreeMap<>();
        try {
            natural.put(null, "not accepted");
        } catch (NullPointerException expected) {
            System.out.println("natural null key: NullPointerException");
        }

        natural.put("beta", null);
        System.out.println("get beta: " + natural.get("beta"));
        System.out.println("contains beta: " + natural.containsKey("beta"));
        System.out.println("get missing: " + natural.get("missing"));
        System.out.println("contains missing: " + natural.containsKey("missing"));
        System.out.println("default beta: " + natural.getOrDefault("beta", "fallback"));
        System.out.println("default missing: " + natural.getOrDefault("missing", "fallback"));

        NavigableMap<String, String> first = new TreeMap<>(
                Comparator.nullsFirst(Comparator.naturalOrder()));
        first.put("b", "B");
        first.put(null, "NULL");
        first.put("a", "A");
        first.put(null, "UPDATED");
        System.out.println("nullsFirst keys: " + new ArrayList<>(first.keySet()));
        System.out.println("null-key value: " + first.get(null));
        System.out.println("nullsFirst size: " + first.size());

        NavigableMap<String, String> last = new TreeMap<>(
                Comparator.nullsLast(Comparator.naturalOrder()));
        last.putAll(first);
        System.out.println("nullsLast keys: " + new ArrayList<>(last.keySet()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapNullPolicy.java
java TreeMapNullPolicy
```

Stdout:

```text
natural null key: NullPointerException
get beta: null
contains beta: true
get missing: null
contains missing: false
default beta: null
default missing: fallback
nullsFirst keys: [null, a, b]
null-key value: UPDATED
nullsFirst size: 3
nullsLast keys: [a, b, null]
```

The programs in this article are compiled with --release 17 and run on OpenJDK 24.0.2. This flag selects the language/API level and target bytecode; it does not change the runtime JVM version.

### 4.1. Both return null, but their states differ

Beta has a mapping with a null value, whereas missing has no mapping. `containsKey` produces two different results.

`getOrDefault` on beta still returns null; getOrDefault on missing returns fallback.

### 4.2. Null ordering is an explicit choice

The first map produces the sequence null,a,b; the last map produces a,b,null. Wrapping the Comparator defines the position of null according to a clear rule.

The second `put` with a null key replaces "NULL" with "UPDATED", so size remains 3.

### 4.3. One successful run does not expand the contract

Do not use a single call that happens not to fail in a special state to conclude that all null queries are valid.

If the key model disallows null, enforce that condition at the data boundary. If it allows null, test insertion, lookup, and navigation under the chosen Comparator.

## 5. Ordering Contract and Consistency with equals Are Two Separate Requirements

### 5.1. A Comparator must define a consistent total order

A relation used for TreeMap must obey the Comparator contract, including:

- Reversing the two arguments must reverse the sign of the comparison result.
- The greater-than relation must be transitive.
- Two objects that compare equal to 0 must have the same sign relation when compared with a third object.

The return value of compare does not have to be strictly -1, 0, or 1; negative, 0, and positive signs are what matter.

Direct int subtraction for comparison can overflow. Using Integer.compare or Comparator.comparingInt avoids this bug for standard integers.

A Comparator that returns random results or flips direction across calls does not provide a stable basis for a search tree.

### 5.2. Exact meaning of "consistent with equals"

For every pair of keys in the supported domain, the desired condition is:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

For a domain that allows null, null equality must be understood according to the chosen policy; the check can be expressed using Objects.equals for that domain.

This is a **bidirectional** condition:

| Mismatch Case | What Can Happen with TreeMap |
| --- | --- |
| `equals` is false but compare returns 0 | Keys that are distinct according to equals are treated as the same position |
| `equals` is true but compare is non-zero | Objects that are the same key according to equals can be separated in order |

Checking only one direction is not enough.

### 5.3. A Comparator inconsistent with equals can still have a valid order

A Comparator that looks only at an object's priority can compare priority levels properly and satisfy transitivity. However, if the object's equals considers both priority and id, two different ids with the same priority will compare equal to 0 even though equals is false.

This is not necessarily a random Comparator or one that violates transitivity. The issue is that it defines equivalence classes that differ from the key's equals.

TreeMap behaves according to that comparison relation. The class documentation states that when an ordering is inconsistent with equals, the sorted map's behavior is still well-defined in terms of the ordering, but it fails to obey the general Map contract.

Do not describe key merging as the tree "randomly losing data" when the Comparator itself declared the two keys to be at the same position.

## 6. Compare Returning 0 Affects put, get, and remove

When searching in a TreeMap, a compare result of 0 means the search has reached the position of a key considered equivalent.

Consequences:

1. Calling `put` with a key that compares equal to 0 with an existing key can replace that mapping's value without increasing size.
2. Calling `get` with an object that is not equal by equals but compares equal to 0 can still find the same mapping.
3. Calling remove with an object that compares equal to 0 can delete the mapping at that equivalent position.
4. Key-based navigation also uses the comparison relation and does not switch to equals at the final step.

Therefore, a Comparator is not merely a display-formatting option for printing. It participates in how TreeMap identifies key positions.

If the requirement is simply "sort items for display," consider keeping a Map keyed by a stable identifier and producing a sorted sequence for display. You do not necessarily have to use the entire display object as the TreeMap key.

## 7. Java 17 Example: Duplicate Priorities and BigDecimal

The first example uses record Item(priority, id). The record's `equals` checks both components; id is required to be non-null.

A Comparator based only on priority merges two Items with the same priority. A complete Comparator by priority then id distinguishes them within this data domain.

The next example uses BigDecimal to show a standard library type whose natural order is inconsistent with equals.

Save as **ComparisonIdentityDemo.java**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class ComparisonIdentityDemo {
    record Item(int priority, String id) {
        Item {
            Objects.requireNonNull(id, "id");
        }
    }

    public static void main(String[] args) {
        Item a = new Item(1, "A");
        Item b = new Item(1, "B");
        Comparator<Item> byPriority = Comparator.comparingInt(Item::priority);
        Map<Item, String> grouped = new TreeMap<>(byPriority);
        grouped.put(a, "first");
        System.out.println("items equal: " + a.equals(b));
        System.out.println("priority comparison: " + byPriority.compare(a, b));
        System.out.println("old value on second put: " + grouped.put(b, "second"));
        System.out.println("priority-only size: " + grouped.size());
        System.out.println("lookup A: " + grouped.get(a));
        System.out.println("lookup B: " + grouped.get(b));

        Comparator<Item> complete = byPriority.thenComparing(Item::id);
        Map<Item, String> separate = new TreeMap<>(complete);
        separate.put(a, "first");
        separate.put(b, "second");
        System.out.println("complete comparison: " + complete.compare(a, b));
        System.out.println("complete size: " + separate.size());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("decimal equals: " + x.equals(y));
        System.out.println("decimal compareTo: " + x.compareTo(y));
        Map<BigDecimal, String> tree = new TreeMap<>();
        Map<BigDecimal, String> hash = new HashMap<>();
        tree.put(x, "one");
        tree.put(y, "two");
        hash.put(x, "one");
        hash.put(y, "two");
        System.out.println("decimal TreeMap size: " + tree.size());
        System.out.println("decimal HashMap size: " + hash.size());

        Comparator<BigDecimal> valueThenScale = Comparator
                .<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
        Map<BigDecimal, String> scaleAware = new TreeMap<>(valueThenScale);
        scaleAware.put(x, "one");
        scaleAware.put(y, "two");
        System.out.println("value-and-scale size: " + scaleAware.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparisonIdentityDemo.java
java ComparisonIdentityDemo
```

Stdout:

```text
items equal: false
priority comparison: 0
old value on second put: first
priority-only size: 1
lookup A: second
lookup B: second
complete comparison: -1
complete size: 2
decimal equals: false
decimal compareTo: 0
decimal TreeMap size: 1
decimal HashMap size: 2
value-and-scale size: 2
```

### 7.1. Priority-only keeps one position per priority

A and B differ by equals, but they share the same priority, so compare returns 0. Calling `put` with B returns the old value first and replaces it with second.

`size` is 1, and both get(A) and get(B) find second. This follows the provided comparison relation.

If the requirement is to keep the two objects separate, the priority-only Comparator does not express that requirement.

### 7.2. The complete Comparator matches this record

`thenComparing` on id only runs when priority is equal. Two Items compare equal to 0 only when both priority and id are equal, which matches the record's equals in this example.

Thus, keys A and B are kept separate, and size is 2.

Do not conclude that appending an arbitrary id tie-breaker always makes every key type consistent; you still need to know what the key type's equals checks.

### 7.3. BigDecimal distinguishes numeric value from scale

BigDecimal("1.0") and BigDecimal("1.00") have compareTo equal to 0 but equals is false: equals also checks scale.

Therefore, TreeMap under natural order has one comparison position, while HashMap using equals/hashCode keeps two keys according to this type's rules.

This is a documented characteristic in [Java 17 BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), not a hashing bug or a tree-balancing bug.

If the model needs to distinguish by both numeric value and scale, a Comparator by value then scale is a meaningful choice, as shown in the scaleAware section of the program.

If the model only cares about numeric value, you can design a key type or normalization step consistent with that identity. Normalization is a data decision: do not apply it arbitrarily if scale is information that must be preserved.

## 8. A Tie-Breaker Is Only Correct When Paired with the Identity Model

Suppose an entity type's equals only checks id, while the Comparator checks priority then id.

Two objects with the same id but different priorities still have equals true, while the Comparator returns non-zero. Appending id at the end does not resolve this direction of mismatch.

Conversely, if equals checks multiple components but the Comparator omits a component capable of distinguishing keys, it can still merge keys that differ by equals.

A clear model choice is needed:

| Requirement | Representation Approach to Consider |
| --- | --- |
| A mapping by a stable id | Use an appropriate identifier key |
| Multiple items with the same priority | Keep a list/group per priority or use a truly distinguishing composite key |
| Sorting for display | Sort a sequence of items instead of changing the map's identity |
| Both lookup by id and an ordered index | Design two indexes with a consistent update workflow |
| A composite key is the true identity | `equals` and Comparator must express the exact same identity components |

Do not introduce identityHashCode or a random number as a tie-breaker just to "avoid compare returning 0." That does not automatically match equals, can still collide, or destroys the meaning of identity.

The goal is not to force every pair of objects to have a distinct order; the goal is for the ordering relation and the key-sameness relation to align.

## 9. Why Modifying a Key After Insertion Can Break the Lookup Path

### 9.1. The tree stores positions; it does not continuously recompute them

When a key is inserted, TreeMap uses the comparison result at that time to organize the tree. The map holds a reference to the key object; it does not automatically snapshot an immutable copy of all fields.

If you modify a field that the Comparator uses, the current comparison result may differ from the result used to place the key in the tree. The object is still referenced in a node, but the lookup path from the root under the new ordering may branch in a different direction.

Finding the object during iteration does not prove that get with that same reference will find it. Iteration follows existing links; key lookup chooses its path using current comparison results.

This is why the problem is not solved by saying "I am still using the exact same object."

### 9.2. Distinguishing two kinds of stability constraints

Two things must be preserved:

- Do not change information that affects a key's equality relation while it is serving as a key.
- For TreeMap, the ordering relation used to organize and look up keys must also remain stable and consistent with the tree already built.

The [Java 17 Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) contract states that behavior is undefined if the value of an object is changed in a manner that affects equals comparisons while the object is a key in a map.

In addition, the ordered search mechanism explains why modifying a field read by the Comparator is dangerous, even if a different equals design did not read that field. A Comparator cannot change how left/right branching works and expect existing positions to adapt automatically.

Do not conflate this issue with hash collisions: TreeMap does not use hash to choose the lookup path. Modifying only hashCode without changing equals or ordering is not the same path-breaking mechanism just described, even though the data type design must still obey its Java contract.

### 9.3. Final and record do not always mean deep immutability

A final reference variable only prevents reassigning that variable to another object. It does not prevent mutating data inside the referenced object.

A record has final components, but if a component is a mutable list or object, its internal contents can still change. If the Comparator or equals reads those contents, the key can still change relationally.

In the safe example later, StableKey only contains int and String. There is no mutable data inside these two components, so the information used for equals and Comparator remains stable.

Do not generalize from one safe record example to every arbitrary record.

### 9.4. Not only the key object can change the ordering

A Comparator might read external state: a mutable priority table, a direction-flipping configuration, or changing classification rules.

If modifying that state causes the same pair of keys to yield a different comparison result than before, the existing tree is not re-sorted automatically either. Even completely immutable keys cannot save a Comparator that changes its rules mid-lifecycle.

When a new ordering is needed, create a new map with the new stable rule and rebuild the index from reliable data. Do not just flip a flag inside the Comparator of a map currently in use.

## 10. Java 17 Example: Mutable Keys and How to Replace Keys Safely

The program contains two independent experiments:

1. Intentionally mutating the rank of a key already inside a map to observe the design flaw.
2. Using a separate map with an immutable key, removing the old key, and then inserting a new key.

In the first experiment, rank participates in both equals and the Comparator. Mutating rank while the key is in the map falls into the case where the Map contract leaves behavior undefined.

**Lines starting with observed are results observed on OpenJDK 24.0.2 in this specific run. They are not results guaranteed by Java for every tree, every insertion order, or every JVM version.**

Save as **MutableTreeKeyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class MutableTreeKeyDemo {
    static final class MutableKey {
        private int rank;
        private final String id;

        MutableKey(int rank, String id) {
            this.rank = rank;
            this.id = Objects.requireNonNull(id, "id");
        }

        int rank() {
            return rank;
        }

        String id() {
            return id;
        }

        void setRank(int rank) {
            this.rank = rank;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && rank == key.rank && id.equals(key.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(rank, id);
        }

        @Override
        public String toString() {
            return id + "@" + rank;
        }
    }

    record StableKey(int rank, String id) {
        StableKey {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public String toString() {
            return id + "@" + rank;
        }
    }

    public static void main(String[] args) {
        Comparator<MutableKey> mutableOrder = Comparator
                .comparingInt(MutableKey::rank)
                .thenComparing(MutableKey::id);
        Map<MutableKey, String> broken = new TreeMap<>(mutableOrder);
        MutableKey a = new MutableKey(1, "A");
        broken.put(a, "value-A");
        broken.put(new MutableKey(2, "B"), "value-B");
        broken.put(new MutableKey(3, "C"), "value-C");
        System.out.println("before mutation: " + new ArrayList<>(broken.keySet()));

        a.setRank(4);
        System.out.println("observed keys after mutation: " + new ArrayList<>(broken.keySet()));
        System.out.println("observed get mutated key: " + broken.get(a));
        System.out.println("observed contains mutated key: " + broken.containsKey(a));

        Comparator<StableKey> stableOrder = Comparator
                .comparingInt(StableKey::rank)
                .thenComparing(StableKey::id);
        Map<StableKey, String> safe = new TreeMap<>(stableOrder);
        StableKey oldKey = new StableKey(1, "A");
        safe.put(oldKey, "value-A");
        safe.put(new StableKey(2, "B"), "value-B");
        safe.put(new StableKey(3, "C"), "value-C");
        String value = safe.remove(oldKey);
        StableKey newKey = new StableKey(4, "A");
        safe.put(newKey, value);
        System.out.println("safe keys: " + new ArrayList<>(safe.keySet()));
        System.out.println("safe lookup: " + safe.get(newKey));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 MutableTreeKeyDemo.java
java MutableTreeKeyDemo
```

Stdout on the environment above:

```text
before mutation: [A@1, B@2, C@3]
observed keys after mutation: [A@4, B@2, C@3]
observed get mutated key: null
observed contains mutated key: false
safe keys: [B@2, C@3, A@4]
safe lookup: value-A
```

### 10.1. The observed sequence does not automatically re-sort into the new order

Before mutation, the ranks are traversed as 1, 2, 3.

After mutating A to rank 4, this run still traverses the existing node positions, producing the sequence A@4, B@2, C@3. That is no longer ascending order according to the current Comparator.

The map receives no notification from setRank to unlink the node and reinsert it.

### 10.2. Even the same reference can fail to be found

In this run, get(a) returns null and containsKey(a) returns false after rank changes.

A's original value was a non-null string, so the null result from get in this experiment is not a valid mapping holding a null value like the example in section 4.

However, do not turn this observation into a rule that "mutating a key guarantees get returns null." A different tree shape might still happen to find the key, and that coincidence does not make the usage valid.

Nor should you write tests requiring every JVM version to always produce these exact three observed lines. This demonstrates a violated usage precondition, not a result contract to pin down.

### 10.3. The safe map replaces the key object instead of mutating it in place

The safe section uses a separate tree with StableKey. The key oldKey is removed while it still has rank 1, so the lookup path still matches its old position.

Next, the program creates a new StableKey with rank 4 and puts the value back. The tree gets to organize the new mapping according to the current order.

Because the example knows for certain that the old key exists and the value is a non-null string, the variable value receives "value-A". Applications that allow null values must handle existence information separately rather than inferring from remove returning null that the old key was absent.

## 11. Workflows for Updating and Recovering an Index

### 11.1. Choose stable data as the key

If a map looks up orders by order ID, the stable ID is usually a more natural key than the entire mutable order object.

Price, processing status, or priority level can reside in the value. Modifying the value does not change the key's position as long as the Comparator only reads the key and does not reference back into the modified data.

If the problem genuinely needs an index by priority then ID, use a stable key snapshot matching those components. The business object can change elsewhere; the key sitting in the index retains its value until it is removed.

This is a data-modeling choice, not a requirement that every object in the program be immutable.

### 11.2. When a key must change, remove the mapping while the old key is still valid

A controlled workflow should determine:

1. Does the old mapping exist, even when null values are allowed?
2. Is the new key valid with respect to null, type, and the Comparator?
3. Does the new key collide with an existing position according to the Comparator?
4. If it collides, does the business logic want to reject, merge, or replace the value?
5. Once the policy is decided, remove the old key while it is still valid and insert the new stable key.

Do not mutate the old key first and then call remove with the mutated key. By then, remove itself may no longer find the right path.

The example in section 10 is a simple case: no new-key collision, the old key is known to exist, and the data is used in a single thread. For shared data, the check and update steps must also be guarded as a single consistent business operation.

Merely wrapping individual calls in a synchronization mechanism does not automatically make the entire check–remove–insert sequence atomic.

### 11.3. Do not rely solely on remove returning null for decisions

If a map can contain null values, both of the following situations can cause remove to return null:

- There was no mapping to delete.
- A mapping existed with a null value and was deleted.

The application must track existence appropriately within the same update-control scope. When using containsKey followed by remove, you must ensure the data is not modified by another operation in between if correctness depends on those two steps.

This issue is independent of whether keys are immutable: stable keys ensure the right position is found, but they do not change the meaning of a null return value.

### 11.4. If keys have already been mutated, prefer the canonical data source

The reliable fix is to take the canonical data, construct new stable keys, and build a new index under the finalized Comparator.

Collision checks under the comparison relation are needed during the rebuild. If the old model merged multiple distinct keys into one position, the values that were previously overwritten will not magically reappear just by creating a new map. Restoring them requires another data source that still holds the information.

Do not assume a copy constructor will "fix the tree." In the OpenJDK 17 source code, the constructor accepting a SortedMap and certain putAll fast paths can build from a sequence assumed to be already sorted. They are not a recovery protocol for misused data. See [OpenJDK 17 TreeMap.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java).

If you need to build an index in a new order, explicitly create an empty map with the right Comparator and insert each stable key–value pair from the canonical source. You still must resolve duplicate keys according to business requirements; calling put does not make that decision for you.

Do not promise a general recovery strategy for every state reached after violating usage preconditions.

## 12. Combining the Three Policies into a Clear Design

### 12.1. Write down the policy before choosing a Comparator

An example specification might be:

- The key is a pair of priority and id.
- Both the key object and id must not be null.
- Priority and id do not change while the key is in the map.
- Two keys are equal when both components are equal.
- Ordering is ascending priority, then ascending id.
- Null values are allowed, so existence is checked separately from get.
- When priority changes, the application creates a new key and updates the index through the workflow.

These decisions explain why a Comparator by priority then id is appropriate. Looking at a single comparingInt line without knowing identity, null rules, and key lifecycle is not enough to evaluate a design.

Another problem may choose a different policy. What must be preserved is that the decisions do not contradict one another.

### 12.2. Wide generic types do not guarantee all keys are mutually comparable

TreeMap<Object, V> using natural order does not automatically turn every Object into a single ordered domain. An integer and a string have no natural way to always be compared with each other.

Similarly, a Comparator accepting a wide declared type might still read a field present on only some objects or reject part of the value domain.

Define the actual key domain, test all pairs that must be supported, and handle invalid data at the input boundary. Do not rely on the fact that the first key succeeded in put to infer that all future keys are valid.

### 12.3. Null handling is not a tool to fix merged keys

Wrapping a Comparator with nullsFirst/nullsLast only adds a policy for null. It does not automatically make the comparison of non-null keys consistent with equals.

If the inner Comparator only reads priority, two objects with different ids and the same priority can still compare equal to 0 after wrapping.

Conversely, adding a proper tie-breaker for identity does not automatically handle null for an inner field. Each layer must have an appropriate policy.

### 12.4. Synchronization does not replace key correctness

A TreeMap whose access is protected by a synchronization lock can still have a flawed design if a thread mutates a key's sorting field while it is in the tree.

Synchronization answers who gets access and when. It does not replace the Comparator, keep key data stable, or rebuild nodes after changes.

Similarly, switching to a concurrent ordered structure does not eliminate the requirements on the comparison relation and key lifecycle.

## 13. Verifying the Contract with Meaningful Scenarios

### 13.1. Test the Comparator independently first

For keys in the supported domain, check:

| What to Check | Expected Sign / Behavior |
| --- | --- |
| Comparing a key with itself | Result is 0 |
| Swapping a and b | Sign of result flips |
| a greater than b, b greater than c | a is greater than c |
| a and b compare equal to 0 | Comparing a with c and b with c must yield the same sign |
| Comparison and equals | Compare equals 0 if and only if Objects.equals is true in the chosen domain |
| Same pair of keys, unchanged valid state | Result stays the same across calls |

Include integer boundary values, such as MIN_VALUE and MAX_VALUE, to catch overflow-prone subtraction comparisons.

Use multiple new objects with identical data to avoid testing only with the exact same reference. A Comparator that only works for the exact existing object is not enough for a value-based map.

Do not treat a few typical cases as a mathematical proof for the entire infinite domain. They are bug-finding tests; reasoning from the definitions of the components is still required.

### 13.2. Test null at the right layer

If null is forbidden, verify that invalid input is rejected according to the published policy. If allowed, test null with null, null with regular keys, and regular keys with each other.

If the key object has a nullable field, add separate test cases for a null field. Do not use results from handling a null whole object as a substitute for testing a null field.

For nullsFirst/nullsLast, also test the inner Comparator's behavior. A valid wrapper cannot fix a broken inner comparison.

### 13.3. Test map operations according to the identity model

A meaningful test suite should include:

- Two genuinely distinct keys must be kept separate under the chosen identity.
- A new object equal to an old key must find the same mapping.
- Calling `put` with an equivalent key updates the value properly and does not increase the mapping count.
- Removing an equivalent key affects the right mapping.
- Iteration follows the published order when all usage conditions are valid.
- Null values and absent keys are distinguished when required by business logic.
- Replacing a key via the safe workflow does not lose data or overwrite outside policy.

If the Comparator is intentionally inconsistent with equals, clearly document that decision and its consequences for the Map contract. Do not write tests assuming TreeMap uses equals to separate keys in that case.

### 13.4. Check key stability and the limits of negative experiments

Inspect every field read by Comparator, compareTo, equals, and hashCode, along with any mutable data reachable indirectly from them.

Test the proper workflow using new keys with identical data, not just get with the original reference. For a multi-component index, changing one component must go through the designed update workflow.

The section intentionally mutating a key only helps illustrate one symptom of violating preconditions. Do not use the observed values as an application specification.

## 14. Common Mistakes and How to Recognize Them

| Assumption or Practice | Problem | How to Handle |
| --- | --- | --- |
| TreeMap allows null values so keys can be null too | The two policies are independent | Check natural order or the specific Comparator |
| `get` returning null means the key is absent | It could be a null value | Check existence when needed |
| `nullsFirst`(null) uses natural order for the rest | Non-null keys are treated as equal | Pass the inner Comparator explicitly |
| Comparator is only for sorted printing | It also determines key positions | Check put/get/remove and identity |
| Two different objects must have two mappings | Compare returning 0 can merge them | Cross-check the comparison relation with equals |
| A transitive Comparator always obeys the Map contract | It can still diverge from equals | Check both directions of compare == 0 and equals |
| Appending id at the end always solves it | `equals` might only check id or other components | Design from true identity |
| A final variable makes the key object immutable | Internal data can still be mutated | Inspect all data read by key relations |
| Mutate the key first, then remove to reinsert | Remove may also fail to find the path | Remove while the old key is still valid |
| Iteration still shows the key so get must find it | Iteration and lookup choose paths differently | Keep key relations stable |
| Flipping the Comparator direction re-sorts the tree | The tree does not reorganize itself | Build a new index under the new rule |
| It worked once so mutating keys is safe | Contract preconditions were violated | Review the design, do not rely on luck |
| Copying a SortedMap always fixes bad data | Fast paths trust input ordering | Use the canonical source and stable keys |
| Synchronizing access fixes mutable keys | Synchronization does not restore altered ordering | Design keys properly and guard the update workflow |

## 15. Self-Check Exercises

### Exercise 1. How does a null value differ from an absent key?

A natural-order TreeMap has "x" → null. Both `get`("x") and get("y") return null. What should be used to distinguish them, and what does getOrDefault("x", "fallback") return?

**Answer hint:** containsKey distinguishes existence. `getOrDefault` for "x" still returns null because the mapping exists; only "y" uses fallback.

### Exercise 2. Is putting null first enough?

An outer Comparator uses nullsFirst, but the inner Comparator only compares priority. Are two non-null keys with different ids and the same priority kept separate?

**Answer hint:** Not just by the null wrapper. The two keys still compare equal to 0 under the inner part, so TreeMap treats them as the same position.

### Exercise 3. A Comparator has a valid order but diverges from equals

Record Key(int level, String code) has the default equals. The Comparator only compares level. What flaw do two keys with the same level but different codes reveal?

**Answer hint:** It may still be a valid ordering by level, but it is inconsistent with equals. TreeMap merges keys according to the comparison relation, so it does not fully satisfy the general Map contract based on equals.

### Exercise 4. Is a tie-breaker enough?

A class has equals checking only id. The Comparator checks priority then id. Do two objects with the same id and different priorities satisfy the consistency condition?

**Answer hint:** No. `equals` is true while compare is non-zero. You need to change the key model or how the index is built to match the true business identity.

### Exercise 5. Two BigDecimals with the same numeric value

If you use new BigDecimal("2.0") and new BigDecimal("2.00") as keys in a natural-order TreeMap, why might only one mapping remain even though equals is false?

**Answer hint:** `compareTo` compares numeric value so it returns 0; equals also checks scale. TreeMap uses the comparison relation to determine the same key position.

### Exercise 6. Does the same reference guarantee lookup?

After putting a key object, you mutate a field read by the Comparator and then call get with that same object. Can you conclude for certain that it will be found or not found?

**Answer hint:** No. The built position may no longer match the new lookup path; if the change also affects equals, Map behavior is undefined in that case. A single observed result creates no guarantee.

### Exercise 7. Are records always safe?

A record holds a reference to a mutable list; the Comparator reads the list's contents. Is the fact that record components are final enough to preserve ordering?

**Answer hint:** Not enough. The reference does not change, but the contents being read can change. You must keep the data that actually determines key relations stable.

### Exercise 8. When should the old key be removed?

To change the rank of an existing mapping, should you mutate rank and then remove, or remove while the old key is still valid and then create a new key?

**Answer hint:** Remove the mapping while the old key is still valid, then use a new stable key, while handling existence, null values, new-key collisions, and consistency of the whole workflow as needed.

### Exercise 9. A Comparator reads a direction-reversal flag

All keys are immutable, but the Comparator reads a configuration flag that can switch from ascending to descending. Does flipping the flag reverse the tree?

**Answer hint:** No. The ordering between the same keys has changed while the old structure remains. Create a new index under the new stable rule.

### Exercise 10. Should you pin down the result of a mutated key?

An experiment mutating a key after put yields null from get on one JVM. Should application tests require every JVM to always return null to detect a "TreeMap bug"?

**Answer hint:** No. The experiment used a key outside contract preconditions. Tests must require a valid workflow to preserve mappings; behavior after a violation is not a specification to defend.

## 16. References

- [TreeMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): ordering relation, Map contract, null policy, and key operations.
- [Comparator — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparison rules, consistency with equals, nullsFirst/nullsLast, and thenComparing.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): meaning of equal keys, null values, and conditions for using mutable keys.
- [BigDecimal — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): relationship between compareTo, equals, and scale.
- [TreeMap.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): Comparator-based lookup mechanism and construction paths from data assumed to be ordered. Implementation details are version-specific; the API contract is the basis for valid usage.