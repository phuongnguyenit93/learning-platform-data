# Insertion Order and Value-Replacement Behavior for Existing Keys

## 1. LinkedHashMap Maintains an Order Alongside Its Mappings

A map stores mappings from keys to values. `LinkedHashMap` also maintains a deterministic iteration order. In its default mode, that is **insertion order**.

Suppose we add the keys `B`, `A`, and `C` in sequence:

```text
put("B", 2)
put("A", 1)
put("C", 3)

Key iteration order: B → A → C
```

The result does not automatically become `A → B → C`, because insertion order is not sorted key order.

If we then call `put("A", 100)`, the map changes the value of `A` but still iterates in this order:

```text
B → A → C
```

Key `A` does not move to the end just because it was written again. This is the core rule of this lesson: **in an insertion-ordered LinkedHashMap, replacing the value of an existing key preserves that key's position**.

### Why Is This Behavior Useful?

A report might want to preserve the order in which fields were originally added while still allowing each field's numbers to be updated. A configuration set might preserve an established display order while its values are updated multiple times.

An insertion-ordered `LinkedHashMap` fits the "keep existing position, update content" pattern. If an application wants ordering by most recent modification, that is a different requirement that needs an explicit design.

The examples below use a standard `LinkedHashMap` without overriding any automatic eviction policy. Except for the mode comparison near the end, all maps use the default insertion order and Java 17-compatible APIs.

## 2. Insertion Order Is Specifically the Order of Creation for Currently Existing Mappings

Three events must be distinguished:

| Event | Creates a new mapping? | Impact on insertion order |
|---|---|---|
| `put` with a key not yet present | Yes | Appends the key at the end |
| `put` with an existing key | No; replaces value | Preserves position |
| `remove` followed by `put` for that key | Yes, a new insertion after removal | Key appears at the end upon re-insertion |

The phrase "insertion order" does not mean the map permanently remembers the position of a key's very first appearance across the entire program history. Once a mapping is removed, its slot is not reserved for automatic restoration later.

Example:

```text
Initial:           B → A → C
put("A", 100):     B → A → C
remove("A"):       B → C
put("A", 200):     B → C → A
```

Calling `put` on an existing key and removing then re-inserting are two different sequences of changes, even though both can end up leaving the same value for that key.

### Position Is Not an Index for List-Style Access

A `LinkedHashMap` has an iteration order, but that does not make it a list supporting `get(0)` to retrieve the first element.

`map.get(key)` still looks up by key. If the keys are integers and `0` is a key, `get(0)` looks up the mapping for key `0`, not "the element at index 0".

When you need an indexed list of keys, you can create a separate `List` from `keySet`; that is a different structure from a map.

## 3. Why Does Replacing a Value Not Change Position?

Conceptually, `LinkedHashMap` combines the key-lookup capability of a hash map with a linked chain through the mappings to define iteration order.

You can picture it like this:

```text
Order:   [B] ⇄ [A] ⇄ [C]
Value:    2     1     3
```

After replacing the value of `A`:

```text
Order:   [B] ⇄ [A] ⇄ [C]
Value:    2    100    3
```

The logical mapping for `A` already exists, so replacing its content is not creating a new position at the end.

When adding a new key `D`:

```text
Order:   [B] ⇄ [A] ⇄ [C] ⇄ [D]
```

When removing `A`, it is no longer in the order chain. Re-inserting it later creates a position at the end rather than restoring the old gap.

This is an explanatory model; it does not require the application to manage internal links manually. Hash table resizing or bucket distribution does not turn insertion order into hash-code order or key-sorted order.

### Having Order Does Not Replace the Key Contract

`LinkedHashMap` still requires a proper key definition. Two distinct key objects that are equal according to `equals` and consistent in `hashCode` represent the same logical key.

Therefore, `put(new String("A"), 100)` does not create a new position if the string key `"A"` is already present. Allocating a new object is different from having a new logical key.

Likewise, do not mutate identifying fields of a key object to "change position" or "rename" a key. A key must maintain a stable contract while acting as a map key; predictable iteration order cannot fix a key that breaks lookup mechanics.

## 4. Complete Program: Overwriting, Reading, Removing, and Re-inserting

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapInsertionDemo {
    public static void main(String[] args) {
        Map<String, Integer> numbers = new LinkedHashMap<>();
        numbers.put("B", 2);
        numbers.put("A", 1);
        numbers.put("C", 3);
        System.out.println("initialKeys=" + numbers.keySet());
        System.out.println("initialValues=" + numbers.values());

        Integer old = numbers.put(new String("A"), 100);
        System.out.println("replacementOld=" + old);
        System.out.println("afterReplaceKeys=" + numbers.keySet());
        System.out.println("afterReplaceMap=" + numbers);
        System.out.println("sizeAfterReplace=" + numbers.size());

        System.out.println("sameValueOld=" + numbers.put("B", 2));
        System.out.println("afterSameValueKeys=" + numbers.keySet());
        System.out.println("readB=" + numbers.get("B"));
        System.out.println("afterReadKeys=" + numbers.keySet());

        numbers.put("D", 4);
        System.out.println("afterNewKey=" + numbers.keySet());
        System.out.println("removedA=" + numbers.remove("A"));
        System.out.println("afterRemove=" + numbers.keySet());
        numbers.put("A", 200);
        System.out.println("afterReinsert=" + numbers.keySet());
        System.out.println("finalMap=" + numbers);

        Map<String, Integer> nullable = new LinkedHashMap<>();
        nullable.put(null, null);
        nullable.put("X", 1);
        System.out.println("nullKeyOld=" + nullable.put(null, 2));
        System.out.println("nullableKeys=" + nullable.keySet());
        System.out.println("nullableSize=" + nullable.size());
        System.out.println("nullKeyNow=" + nullable.get(null));
    }
}
```

Save as `LinkedHashMapInsertionDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapInsertionDemo.java
java LinkedHashMapInsertionDemo
```

Exact output:

```text
initialKeys=[B, A, C]
initialValues=[2, 1, 3]
replacementOld=1
afterReplaceKeys=[B, A, C]
afterReplaceMap={B=2, A=100, C=3}
sizeAfterReplace=3
sameValueOld=2
afterSameValueKeys=[B, A, C]
readB=2
afterReadKeys=[B, A, C]
afterNewKey=[B, A, C, D]
removedA=100
afterRemove=[B, C, D]
afterReinsert=[B, C, D, A]
finalMap={B=2, C=3, D=4, A=200}
nullKeyOld=null
nullableKeys=[null, X]
nullableSize=2
nullKeyNow=2
```

### 4.1. Insertion Order Is Not Alphabetical Order

`initialKeys=[B, A, C]` matches the three initial insertions. `initialValues=[2, 1, 3]` are the values in that same mapping order, not sorted by magnitude.

### 4.2. Equal Keys Replace the Same Mapping

Writing `new String("A")` returns the old value `1`, and the map now holds `A=100` at the old position:

```text
afterReplaceKeys=[B, A, C]
afterReplaceMap={B=2, A=100, C=3}
sizeAfterReplace=3
```

You do not need the exact same `String` reference inserted earlier to refer to the same logical key. This relies on `String`'s key contract.

Do not infer from this that the map must replace the internally stored key object with the newly passed reference. What is being verified here is the mapping, value, and order of the logical key.

### 4.3. Writing the Same Value and Reading Do Not Move a Key to the End

`put("B", 2)` returns `2` even though the new value equals the old value. It still does not move `B` to the end.

`get("B")` reads the current value and preserves order in insertion mode. There is no "recently used key moves to the end" rule in this default mode.

### 4.4. New Keys Append to the End; Removed and Re-inserted Keys Also Append to the End

Adding `D` produces `[B, A, C, D]`. Removing `A` leaves `[B, C, D]`. Re-inserting `A` produces `[B, C, D, A]`.

The final value of `A` is `200`, but its final position comes from the mapping having been removed and created anew. Not every update to value `200` has the same effect on order.

### 4.5. A `null` Old Value Does Not Mean the Key Was Absent

The `nullable` map already has a mapping from key `null` to value `null` before `X` is added. Calling `put(null, 2)` returns `null`, yet it still replaces the value of an existing mapping:

```text
nullableKeys=[null, X]
nullableSize=2
nullKeyNow=2
```

The `null` key keeps its position before `X`. Receiving `null` as the previous value is not enough to conclude that a new key was inserted. If you need to distinguish whether a mapping exists, check key existence rather than relying only on `get` or the returned previous value.

## 5. Behavior Table in Insertion-Order Mode

The following table assumes a mutable `LinkedHashMap`, valid operations, and no concurrent external modifications:

| Operation | Can the value change? | Order of an existing key |
|---|---|---|
| `put(k, newValue)` when `k` is present | Yes | Preserved |
| `put(k, sameValue)` when `k` is present | May remain unchanged in data meaning | Preserved |
| `get(k)` | Does not modify mapping | Preserved |
| `replace(k, newValue)` when replacement occurs | Yes | Preserved |
| `entry.setValue(newValue)` on a valid entry | Yes | Preserved |
| Adding a new key | Creates new mapping | New key at the end |
| Removing a key | Removes mapping | Key no longer has a position |
| Re-inserting a removed key | Creates new mapping | At the end upon re-insertion |

Other compute/update methods should also be understood by their actual effect. If the outcome **removes** a mapping, you cannot treat it as a "value-only update" and assume the position is preserved for the future.

If a value is a mutable object, modifying the contents of that object does not change the key's position in the map. That mutates the value object's data, which is different from adding or removing a mapping.

## 6. `putAll`: Preserves Existing Key Positions, Appends New Keys in Source Iteration Order

For an insertion-ordered target map, `putAll(source)` can be understood in two groups:

1. Source keys already present in the target: replace the value, preserve the target's position.
2. Source keys not yet in the target: create new mappings, appended at the end in the order the source yields its entries.

Example:

```text
Target before:       B → A → C
Source iteration:    A → E → D

Target after putAll: B → A → C → E → D
```

`A` is already present, so it is not moved to the end before `E` and `D`. Only the two new keys are appended after the existing sequence.

This is useful when a base configuration already has a display order and an update batch overrides some values while adding new entries. It does not reorder the entire target to match the source's order.

### The Source Must Have a Defined Order If New-Item Order Matters

If the source is a default `LinkedHashMap` kept stable, you can rely on the source's order to predict how new keys are appended.

If the source is a `HashMap`, do not assume keys will be taken in the historical order of `put` calls on that source. The target only receives whatever iteration order the source currently provides; it cannot reconstruct a history that was never retained.

Likewise, do not pass a multi-entry `Map.of` and treat the argument order as a guaranteed iteration order. If order is data that must be preserved, choose a source and construction process with an appropriate ordering contract.

## 7. Complete Program: `putAll` and Ordered Copies

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapPutAllCopyDemo {
    public static void main(String[] args) {
        Map<String, Integer> target = new LinkedHashMap<>();
        target.put("B", 2);
        target.put("A", 1);
        target.put("C", 3);

        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("A", 10);
        source.put("E", 5);
        source.put("D", 4);

        target.putAll(source);
        System.out.println("sourceOrder=" + source.keySet());
        System.out.println("targetOrder=" + target.keySet());
        System.out.println("targetValues=" + target.values());
        System.out.println("targetMap=" + target);

        Map<String, Integer> copied = new LinkedHashMap<>(target);
        target.put("A", 100);
        target.put("F", 6);
        System.out.println("sourceMapAfterChange=" + target.keySet());
        System.out.println("copyOrder=" + copied.keySet());
        System.out.println("copyA=" + copied.get("A"));
        System.out.println("sourceA=" + target.get("A"));

        Map<String, Integer> unordered = new HashMap<>();
        unordered.put("orange", 1);
        unordered.put("apple", 2);
        unordered.put("banana", 3);

        List<String> observedOrder = new ArrayList<>(unordered.keySet());
        Map<String, Integer> fromUnordered = new LinkedHashMap<>(unordered);
        System.out.println("copyMatchesObservedSourceOrder="
                + new ArrayList<>(fromUnordered.keySet()).equals(observedOrder));
    }
}
```

Save as `LinkedHashMapPutAllCopyDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapPutAllCopyDemo.java
java LinkedHashMapPutAllCopyDemo
```

Exact output:

```text
sourceOrder=[A, E, D]
targetOrder=[B, A, C, E, D]
targetValues=[2, 10, 3, 5, 4]
targetMap={B=2, A=10, C=3, E=5, D=4}
sourceMapAfterChange=[B, A, C, E, D, F]
copyOrder=[B, A, C, E, D]
copyA=10
sourceA=100
copyMatchesObservedSourceOrder=true
```

### 7.1. Existing Key Order Belongs to the Target

The source has order `[A, E, D]`, while the target after copying is `[B, A, C, E, D]`. `A` receives value `10` at its old position. `E` and `D` are appended at the end in source order.

The values `[2, 10, 3, 5, 4]` correspond to the keys in that exact new order.

### 7.2. The Copy Constructor Preserves the Order Observed at Copy Time

`new LinkedHashMap<>(target)` creates a new map with mappings in the order the source is iterated at the time of copying. Afterward, the source updates `A` to `100` and adds `F`; the copy still retains the old key sequence with `A=10`.

The copy is not a live view of the source. It copies the mapping structure, not a deep copy of every key or value object.

### 7.3. Copying a `HashMap` Does Not Restore Insertion History

The final part records the currently observed iteration order from a `HashMap`, then immediately copies it into a `LinkedHashMap` while the source remains unchanged.

`copyMatchesObservedSourceOrder=true` means the copy preserves the order provided by the source during that traversal. The program does not print or claim any specific alphabetical or insertion order for `HashMap`.

Creating an ordered target maintains a sequence from the moment of copying onward. It cannot retroactively recover historical data that the source did not guarantee.

## 8. Order Observed Through Views and `forEach`

For a map holding the order `B → A → C`:

| Traversal method | Observed data |
|---|---|
| `keySet()` | Keys in order `B`, `A`, `C` |
| `values()` | Values corresponding to `B`, then `A`, then `C` |
| `entrySet()` | Mapping pairs in that same order |
| `Map.forEach` | Action executed on mappings in the defined iteration order |

Replacing the value of `A` changes the corresponding value when iterating `values` or `entrySet`, without moving `A`'s position in insertion mode.

The fact that `keySet` has type `Set` does not mean its iterator must be unordered. A set view can iterate in the order backed by the map, while `Set` equality still ignores order. Those are two separate aspects.

### Live Views Differ from a Copied List

Suppose you store a key view and a separate list:

```java
// Illustrates first as an insertion-ordered LinkedHashMap.
Set<String> keysView = first.keySet();
List<String> copiedKeys = new ArrayList<>(keysView);
```

When a new key is added to the map and a new traversal begins:

- `keysView` reflects the new key.
- `copiedKeys` does not automatically gain the new element because it is a copied list.

Similarly, the values view sees the newly updated value. You should not call a view a "snapshot of the order at the time the view was obtained."

None of this permits arbitrary structural modification while an existing iterator is active. Live views and modifying during iteration are two separate issues.

### Replacing Values While Iterating

In insertion mode, merely replacing the value of an existing key is not treated as a structural order change like adding or removing a mapping. While iterating `entrySet`, the direct approach is to use `entry.setValue` on a valid entry when supported by the implementation.

Do not use this to infer that you can `remove` and `put` outside the iterator inside the loop. That sequence modifies structure and changes position. If you need to remove the current element during iteration, use the iterator's own `remove` mechanism when supported.

## 9. `Map.equals` Does Not Check Insertion Order

Two maps can contain the same mappings while iterating in two different orders:

```text
First map:  B → A → C
Second map: C → A → B

Every key in both maps still has the same corresponding value.
```

By general contract, `Map.equals` compares mappings and does not include insertion order in its equality criteria. A map's hash code is also not a specific encoding of iteration order.

Therefore, if you want to check whether the result has the right order, compare an ordered sequence such as a list of keys:

```java
// Illustrates two maps that remain stable during comparison.
boolean sameMappings = first.equals(second);
boolean sameKeyOrder =
        new ArrayList<>(first.keySet())
                .equals(new ArrayList<>(second.keySet()));
```

| Comparison | What is compared |
|---|---|
| `first.equals(second)` | Key-value mappings |
| `first.keySet().equals(second.keySet())` | Key sets, ignoring order |
| `first.entrySet().equals(second.entrySet())` | Entry sets, ignoring order |
| Comparing two `ArrayList`s copied from `keySet` | Ordered sequence of keys |

If the requirement is both identical data and identical order, you must check both aspects. Do not compare `keySet` as a set and assume order has been verified.

Also do not assume an arbitrary `Collection` of values has list-like `equals` for sequence comparison. Explicitly create a `List` when the goal is to verify element order.

## 10. Complete Program: Views, Value Replacement, and Order Verification

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class LinkedHashMapViewsEqualityDemo {
    public static void main(String[] args) {
        Map<String, Integer> first = new LinkedHashMap<>();
        first.put("B", 2);
        first.put("A", 1);
        first.put("C", 3);

        Set<String> keysView = first.keySet();
        Collection<Integer> valuesView = first.values();
        List<String> copiedKeys = new ArrayList<>(keysView);

        first.put("A", 10);
        System.out.println("keysAfterUpdate=" + keysView);
        System.out.println("valuesAfterUpdate=" + valuesView);

        List<String> lines = new ArrayList<>();
        first.forEach((key, value) -> lines.add(key + "=" + value));
        System.out.println("forEachLines=" + lines);

        for (Map.Entry<String, Integer> entry : first.entrySet()) {
            if (entry.getKey().equals("B")) {
                Integer old = entry.setValue(20);
                System.out.println("entryOld=" + old);
            }
        }
        System.out.println("afterEntryUpdate=" + first);

        Map<String, Integer> reversed = new LinkedHashMap<>();
        reversed.put("C", 3);
        reversed.put("A", 10);
        reversed.put("B", 20);
        System.out.println("sameMappings=" + first.equals(reversed));
        System.out.println("sameMapHash="
                + (first.hashCode() == reversed.hashCode()));
        System.out.println("sameKeyOrder="
                + new ArrayList<>(first.keySet()).equals(
                        new ArrayList<>(reversed.keySet())));

        first.put("D", 4);
        System.out.println("liveKeysAfterAppend=" + keysView);
        System.out.println("liveValuesAfterAppend=" + valuesView);
        System.out.println("copiedKeys=" + copiedKeys);
    }
}
```

Save as `LinkedHashMapViewsEqualityDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapViewsEqualityDemo.java
java LinkedHashMapViewsEqualityDemo
```

Exact output:

```text
keysAfterUpdate=[B, A, C]
valuesAfterUpdate=[2, 10, 3]
forEachLines=[B=2, A=10, C=3]
entryOld=2
afterEntryUpdate={B=20, A=10, C=3}
sameMappings=true
sameMapHash=true
sameKeyOrder=false
liveKeysAfterAppend=[B, A, C, D]
liveValuesAfterAppend=[20, 10, 3, 4]
copiedKeys=[B, A, C]
```

### 10.1. Value Changes at the Corresponding Position

After updating `A` to `10`:

```text
keysAfterUpdate=[B, A, C]
valuesAfterUpdate=[2, 10, 3]
forEachLines=[B=2, A=10, C=3]
```

The key order remains unchanged, and the value of the second mapping changes. The lines collected via `forEach` follow the same order.

The subsequent entry iteration replaces `B`'s value using `entry.setValue(20)`; the method returns the old value `2`. Afterward, the map still has the order `B, A, C`.

### 10.2. Two Equal Maps with Different Key Sequences

The `reversed` map was inserted in order `C, A, B` and has the same mappings as `first`. Result:

```text
sameMappings=true
sameMapHash=true
sameKeyOrder=false
```

All three lines are true at once with no contradiction. They are checking different aspects of the data.

### 10.3. Views Reflect Subsequent Additions

Adding `D` turns the key view into `[B, A, C, D]` and the values view into `[20, 10, 3, 4]`. The `copiedKeys` list remains `[B, A, C]`.

No open iterator is externally modified in this example; the program mutates the map between observation passes and then traverses the views again.

## 11. Access-Order Mode Is a Separate Option

`LinkedHashMap` also has a constructor that lets you select access order:

```java
// Illustrates construction; not a standalone program.
Map<String, Integer> insertion = new LinkedHashMap<>();
Map<String, Integer> access =
        new LinkedHashMap<>(16, 0.75f, true);
```

The third parameter `accessOrder` has these meanings:

| Value | Mode |
|---|---|
| `false` | Insertion order |
| `true` | Access order |

Standard constructors that do not select `true` create an insertion-ordered map. In access-order mode, certain calls such as `get` and `put` count as accesses to an entry; the key can be moved to the end according to this mode's rules.

Therefore, the statement "overwriting a key does not change order" in this lesson must be tied to **insertion-order mode and standard `put` operations**. Do not apply it verbatim to an instance created with `accessOrder=true`.

### Complete Program Comparing the Two Modes

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapOrderModesDemo {
    public static void main(String[] args) {
        Map<String, Integer> insertion = new LinkedHashMap<>();
        Map<String, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);

        int value = 1;
        for (String key : List.of("A", "B", "C")) {
            insertion.put(key, value);
            access.put(key, value);
            value++;
        }

        System.out.println("insertionBefore=" + insertion.keySet());
        System.out.println("accessBefore=" + access.keySet());

        insertion.put("B", 20);
        access.put("B", 20);
        System.out.println("insertionAfterPutB=" + insertion.keySet());
        System.out.println("accessAfterPutB=" + access.keySet());

        insertion.get("A");
        access.get("A");
        System.out.println("insertionAfterGetA=" + insertion.keySet());
        System.out.println("accessAfterGetA=" + access.keySet());
    }
}
```

Save as `LinkedHashMapOrderModesDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapOrderModesDemo.java
java LinkedHashMapOrderModesDemo
```

Exact output:

```text
insertionBefore=[A, B, C]
accessBefore=[A, B, C]
insertionAfterPutB=[A, B, C]
accessAfterPutB=[A, C, B]
insertionAfterGetA=[A, B, C]
accessAfterGetA=[C, B, A]
```

### Same Calls, Different Ordering Policy

Both maps start with `[A, B, C]`.

After `put("B", 20)`:

- The insertion-ordered map stays `[A, B, C]`.
- The access-ordered map becomes `[A, C, B]`.

After `get("A")`:

- The insertion-ordered map stays `[A, B, C]`.
- The access-ordered map becomes `[C, B, A]`.

The difference has nothing to do with `20` being larger or smaller than the other values. It comes from the mode selected when creating the map.

Do not treat access order as "most recently modified order" if the application also reads data: a read operation can also change the order. Define clearly which business events should affect position.

### Be Careful When Calling `get` Inside an Iteration Loop

In insertion-order mode, `get` does not move keys by access order. In access-order mode, a read call can alter the very order being iterated.

If you already hold an entry, calling `entry.getValue()` expresses the intent more directly than calling `map.get(entry.getKey())`. Do not assume every read call on every map has no effect on ordering state.

## 12. When You Intentionally Want to Move a Key to the End

With Java 17 APIs and an insertion-ordered map, removing and re-inserting is one way to establish a new position. However, you must understand that this is two separate operations, not merely a value change.

The snippet below assumes `numbers` is a mutable, insertion-ordered `LinkedHashMap<String, Integer>`, owned by a single thread, with no open iterator:

```java
String key = "A";
if (numbers.containsKey(key)) {
    Integer value = numbers.remove(key);
    numbers.put(key, value);
}
```

The existence check is intentional: if the key has a `null` value, the mapping still needs to be preserved when moving its position. Writing only `if (value != null)` after `remove` would lose a `null`-valued mapping. Conversely, removing a nonexistent key and unconditionally calling `put` with the `null` result would accidentally create a new mapping.

The remove-and-reinsert pair has limitations to understand:

- It changes the map structure and iteration position.
- It is not an atomic transaction across multiple threads.
- If exceptions or custom data-change rules exist, the application must handle them according to its own requirements.
- Do not perform it arbitrarily inside a `for-each` loop iterating over the map; structural modification outside the iterator can violate the iteration contract.

Fail-fast iterators may detect misuse with `ConcurrentModificationException`, but you must not rely on the absence of an exception in one run to conclude that modifying during iteration is valid. Maintaining predictable order does not make `LinkedHashMap` thread-safe for concurrent access.

### Version Boundary: Explicit Positioning Methods

Starting in Java 21, `LinkedHashMap` provides APIs such as `putFirst` and `putLast` for explicit positioning, which can change the position of an existing entry. They differ from regular `put`. Each method's rules must be read from its corresponding API specification.

The complete runnable programs in this lesson use Java 17-compatible APIs; this note prevents overgeneralizing to "no operation on LinkedHashMap can change the position of an existing key."

## 13. Applying This to Frequently Updated Data

A common scenario is needing to preserve the first-appearance order of field codes while keeping the latest value for each code:

```text
Updates:
B=1, A=2, B=3, C=4, A=5

Insertion order of remaining keys:
B → A → C

Final values:
B=3, A=5, C=4
```

By simply calling `put` for each update into an insertion-ordered map, you preserve the initial position of each existing key and replace its value whenever that key appears again.

This **does not retain the full change history**. Earlier values for the same key are overwritten; if you need a log of every modification, store the history in another suitable structure.

It also does not automatically create "most recently modified" order: in the example, `A` was updated last but did not become the last key.

### From Data Producer to Data Consumer

Declaring:

```java
Map<String, Integer> data = new LinkedHashMap<>();
```

does not remove the ordering behavior of the existing `LinkedHashMap` instance. The variable type is `Map`, while the actual object still keeps its chosen ordering policy.

However, if a method only promises to return an arbitrary `Map`, callers should not assume every implementation preserves insertion order. If order is a requirement across components, state it clearly in the contract.

If data passes through an intermediate step, also check whether that step preserves order. For example, `Map.copyOf` does not guarantee insertion order just because the source is a `LinkedHashMap`. A copy made with `LinkedHashMap` and an unmodifiable map from a factory have different contracts.

When outputting report lines or building a UI, ensure the consuming step follows the preserved order. Choosing the right source structure is not enough if a later step sorts the data or converts it to a structure that does not guarantee order.

## 14. Common Mistakes

| Misconception | Correct understanding in insertion-order mode |
|---|---|
| Re-writing a key automatically moves it to the end | `put` on an existing key preserves its position |
| Larger values get pushed to the back | Does not sort by value |
| Inserting B, A, C iterates as A, B, C | Iterates B, A, C in insertion order |
| Removing then re-inserting returns to the old historical position | Re-inserting creates a new position at the end |
| Returning `null` as the old value means the key was new | The existing key might have held a `null` value |
| `Map.equals` is enough to check order | It compares mappings; also compare sequences |
| `keySet` is a `Set` so it cannot have an iteration order | The view's iterator follows the order backed by the map |
| Copying a `HashMap` to a `LinkedHashMap` recovers old `put` order | It only preserves the order yielded by the source at copy time |
| `LinkedHashMap` always uses insertion order in all configurations | Access-order mode can be selected separately |
| Having an order means having an index-based access API | `get` still takes a key |

## 15. Self-Check with Operation Sequences

The questions below assume an insertion-ordered map with no explicit positioning calls or automatic eviction policy.

### Question 1: Replacing a Middle Value

A map has order `A, B, C`. Call `put("B", 99)`. Do the order and size change?

**Answer:** The order remains `A, B, C`; the size does not increase. The value of `B` changes to `99`.

### Question 2: Writing the Same Value

`B` currently has value `99`; call `put("B", 99)` again. Does the key move to the end because this is a new write?

**Answer:** No. The logical key already exists, so no new position is created in insertion order.

### Question 3: New Key Object That Satisfies `equals`

The map contains the string key `"B"`. Call `put(new String("B"), 7)`. Does this add a second position for B?

**Answer:** No. Two strings with equal content represent the same logical key, given `String`'s consistent hash contract.

### Question 4: Remove Then Insert

A map has order `A, B, C`; remove `B`, then insert `B` again. What is the final order?

**Answer:** `A, C, B`. The old position is not reserved after the mapping is removed.

### Question 5: New Key

A map has order `C, A`. Add a new key `B`. Does it automatically become `A, B, C`?

**Answer:** No. The result is `C, A, B`. Insertion order is different from alphabetical order.

### Question 6: `putAll`

The target has `A, B`; the source iterates `B, D, C`. Both are suitable, stable maps. What is the final key order in the target?

**Answer:** `A, B, D, C`. `B` keeps its position and receives the new value; `D` and `C` are new keys appended in source order.

### Question 7: Mapping with a `null` Value

Key `A` currently has value `null` before `B`. Calling `put("A", 1)` returns `null`. Should `A` move to the end?

**Answer:** No. `A` already had a mapping; the `null` previous value does not turn a value replacement into a new key insertion.

### Question 8: Comparing Two Maps with Different Orders

Two maps have the same mappings, but their key sequences are `A, B` and `B, A`. Can `Map.equals` return `true`?

**Answer:** Yes. To verify order, also compare lists of keys in iteration order.

### Question 9: The `accessOrder` Parameter

A map is created with `new LinkedHashMap<>(16, 0.75f, true)`. Can you apply the default mode's rule "get does not change order" to it?

**Answer:** No. That is access-order mode; `get` can change the order.

### Question 10: Copying from a `HashMap`

A `LinkedHashMap` copy matches the current traversal of a `HashMap` source. Does that prove it preserved the source's original insertion history?

**Answer:** No. The source does not promise that history through its iteration order; the copy only preserves the order provided at copy time.

## 16. Practice: Keep Position, Update Content

Write a program using a default `LinkedHashMap<String, Integer>` that performs these operations in sequence:

```text
put("name", 1)
put("price", 2)
put("stock", 3)
put("price", 20)
put("category", 4)
remove("name")
put("name", 10)
```

Before running, predict:

1. The key sequence after each operation.
2. The old value returned when replacing `price`.
3. The old value returned when removing `name`.
4. The final key and value sequences.
5. A concrete comparison to verify the exact order, in addition to checking the mappings.

**Final Checkpoint Answer:**

```text
Keys: [price, stock, category, name]
Values: [20, 3, 4, 10]
Old value when replacing price: 2
Old value when removing name: 1
Final size: 4
```

Extend the program with an update map whose source order is `stock, note, color`. Call `putAll`, predict which key keeps its position and which keys are appended at the end, then verify using the key list.

Finally, create a second map with the same mappings inserted in a different order. Test `Map.equals` and the separate key-list comparison. Explain why both data verification and order verification are necessary if both are required of the output.

## References

- [Java 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): insertion order, overwriting existing keys, copy constructor, views, and access-order mode.
- [Java 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): logical keys, `put`, `putAll`, `forEach`, `equals`, and factory contracts.
- [Java 21 — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): explicit positioning operations such as `putFirst` and `putLast`, to distinguish them from regular `put`.

The four standalone programs were compiled with `javac --release 17 -encoding UTF-8` and verified on JDK 24.0.2. They use only Java 17-compatible APIs; the output blocks show actual results.
