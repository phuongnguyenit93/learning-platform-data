# Converting a Map to a List of Entries, Keys, or Values

## 1. Choose What Information to Keep Before Choosing a Statement

`Map<K, V>` represents a mapping from keys to values. `List<T>` represents an indexed sequence of elements. When converting from a Map to a list, the first question is **what each element of the list needs to contain**.

Consider a score table:

~~~text
B -> 20
A -> 10
C -> 20
~~~

There are three outcomes with different purposes:

| Result | Sample Data | Preserved Information |
| --- | --- | --- |
| List of keys | `[B, A, C]` | Which codes exist |
| List of values | `[20, 10, 20]` | Which scores are stored, including duplicates |
| List of entries | `[B=20, A=10, C=20]` | Each code and score paired together |

An entry is a key–value pair, represented by `Map.Entry<K, V>`. Keeping entries lets you sort or filter entire rows without losing which score belongs to which code.

If you only take the values and discard the keys, you cannot infer on your own whether a score of `20` belongs to `B` or `C`. If you extract the keys separately and sort them without adjusting the corresponding data, re-pairing by index can produce pairs that never existed in the Map.

After choosing which information to keep, you need to decide three more things: the desired order, whether the list should be modifiable, and how isolated the data needs to be from the Map. These are independent decisions; a list that disallows adding or removing elements can still hold mutable element objects.

## 2. The Three Map Views as Conversion Sources

`Map` provides three collection views:

~~~java
Set<K> keys = map.keySet();
Collection<V> values = map.values();
Set<Map.Entry<K, V>> entries = map.entrySet();
~~~

This illustrates the data types rather than a standalone program; `K`, `V`, and `map` belong to the application's declaration context.

These methods return views backed by the underlying Map. If the Map changes, the contents observed through the view change as well. Supported removal operations on a view can remove the corresponding mapping from the Map. [Java SE 17 — Map collection views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#keySet()).

Distinguish between:

~~~java
Set<String> keyView = scores.keySet();
List<String> keyList = new ArrayList<>(scores.keySet());
~~~

`keyView` remains a view of `scores`. `keyList` has its own list structure, populated with the keys iterated at creation time.

In the examples in this article, the Map is not modified concurrently during conversion. If that condition does not hold, you should not describe every copy as a "point-in-time snapshot" without checking the source's concurrency contract.

### A Map Is Not Directly a Collection

You cannot use `new ArrayList<>(map)` as if a Map were a collection of elements of a single type. The collection constructor expects a `Collection`; a Map provides views so the writer explicitly chooses keys, values, or entries.

`Arrays.asList(map)` does not flatten a Map into pairs either. With a single-argument call like that, the resulting list contains one element: the Map object itself. It solves a different requirement.

Choose one of these three paths:

~~~text
Map<K,V>
   |-- keySet()  ------> list of K
   |-- values()  ------> list of V
   |-- entrySet() -----> list of K,V pairs
~~~

## 3. List of Keys: Copying Existing Keys

With a `Map<String, Integer>`:

~~~java
List<String> keys = new ArrayList<>(scores.keySet());
~~~

The list holds references to the keys in the source's iteration order. If the source Map is a `LinkedHashMap` in insertion order `B`, `A`, `C`, the result is `[B, A, C]`.

After copying:

- `keys.remove("B")` only removes the element from the list; it does not remove key `B` from `scores`.
- `keys.add("X")` only adds to the list; it does not create an `X` mapping in the Map.
- If key `D` is later added to the Map, `D` does not automatically appear in the copied list.
- You can sort the list without reordering the Map structure.

The fact that a Map has unique keys does not turn the resulting list into a `Set`. Once you have a separate `ArrayList`, you can still add a duplicate key to the list. Source uniqueness describes the original data; it does not become a duplicate-prevention rule for every structure created from it.

Independence here applies to **the list positions**, not necessarily to the entire key objects. If a key is a mutable object, both the list and the Map still hold references to that same object. In particular, mutating a key in a way that affects `equals` or `hashCode` while it is in the Map can break lookup structure assumptions. Converting to a list does not make such key mutations safe.

When you only need a list of codes to populate a UI selector, this is usually the simplest conversion with the right information. If you also need to display a name or score alongside each code, keep pairs from the start instead of repeatedly inferring relationships by index.

## 4. List of Values: Preserving Duplicate Values

The corresponding construction:

~~~java
List<Integer> values = new ArrayList<>(scores.values());
~~~

With the three mappings `B=20`, `A=10`, `C=20`, the list has three elements `[20, 10, 20]`. `values()` returns a `Collection<V>` because multiple keys can map to equal values.

If you pass the result through a `Set`, the two occurrences of `20` can collapse into one. That changes the meaning of the data, rather than being a required step when converting a Map to a list.

A list of values is appropriate when you need to compute a sum, gather statistics, or pass data to a function that only works with scores. However, it has already discarded key information. If you want to exclude student `B` specifically, do not just remove an element `20` and assume you targeted `B`.

Also keep operations on these two objects separate:

~~~java
scores.values().remove(20);
values.remove(Integer.valueOf(20));
~~~

The first line, when the view supports removal, requests removing a mapping with the matching value from the Map; it should not be used to target a specific key when multiple keys share the same value. The second line removes from the copied `values` list and does not remove any mapping from the Map.

Passing `Integer.valueOf(20)` on the second line selects the remove-by-object overload. For `List<Integer>`, `remove(20)` with an `int` argument would select removal by index `20`, which has a different meaning.

A `null` value is also valid data if the Map allows it. `new ArrayList<>(map.values())` preserves that value in the list. If a downstream step does not accept `null`, establish an explicit rule—keep, replace, filter out, or throw an error—rather than letting a structural conversion silently decide on behalf of the application.

## 5. List of Entries: Separate List Structure from Entry Objects

### 5.1. The Short Form Only Copies Entry References

A common pattern is:

~~~java
List<Map.Entry<String, Integer>> entries =
        new ArrayList<>(scores.entrySet());
~~~

This statement creates a separate list. Adding or removing positions in the list does not add or remove mappings in the Map. However, the `ArrayList` constructor does not create an independent key–value pair for each entry; it copies the element references provided by the source.

Therefore, do not interpret this statement as "the keys and values are now frozen independently of the Map." Nor should you assume that wrapping the list in an unmodifiable wrapper automatically replaces every entry inside with an independent entry.

The Java 17 contract places an important restriction on entries obtained while iterating `entrySet`: the connection to the Map is only defined for the duration of the iteration; behavior outside that iteration or after unsupported underlying modifications may be undefined. If you want to keep pairs for later use, create independent entry copies. [Java SE 17 — Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

This also means you should not run a test against one specific Map implementation and treat the observed result as a universal contract. An entry might appear to reflect updated values on one implementation, but that is not a guarantee across all Maps or subsequent modifications.

### 5.2. Independent Copies with Map.Entry.copyOf

For non-`null` keys and values, Java 17 provides:

~~~java
List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .toList();
~~~

`map(Map.Entry::copyOf)` has a different role from `toList()`:

- `copyOf` creates an entry representation that is not linked to the underlying Map and does not support changing the value via `setValue`.
- `toList` collects those entries into a list that does not allow modification through list-mutating methods.

`Map.Entry.copyOf`, introduced in Java 17, does not accept a `null` entry, `null` key, or `null` value. It does not guarantee allocating a new entry object if the input is already an appropriate copy type; what you rely on is the contract of independence from the Map, not object-identity comparison.

If you want a list that supports adding, removing, or sorting in place, choose the target explicitly:

~~~java
List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Here the list is modifiable, while each entry inside still disallows `setValue`. There is no contradiction: one permission belongs to the list, and the other belongs to the element object.

### 5.3. Should Independent Pairs Allow Value Updates?

You can create an independent entry using `AbstractMap.SimpleEntry`:

~~~java
Map.Entry<String, Integer> local =
        new AbstractMap.SimpleEntry<>("B", 20);
local.setValue(25);
~~~

The `local` entry becomes `B=25`. Because it is not linked to `scores`, this call does not update the Map. This is useful when an application needs a mutable pair before deciding whether to write it elsewhere. [Java SE 17 — SimpleEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).

If an independent entry has been modified and you want to persist the change, you need an explicit Map operation such as `scores.put(local.getKey(), local.getValue())`, along with an appropriate conflict-handling rule. Creating a working list does not automatically build a two-way synchronization mechanism.

Conversely, during `entrySet` iteration, an entry from a Map that supports updates can use `setValue` to write back to the Map. The full program demonstrates this directly inside the iteration loop without retaining the entry for later use.

## 6. Maps with Nulls: Choose the Right Copy Form

`LinkedHashMap` can contain a `null` key and `null` values. If you pass all of its entries to `Map.Entry.copyOf`, the conversion throws a `NullPointerException` when it encounters the null part.

Do not convert `null` data to the string `"null"` just to avoid the error, because the two values have different meanings. You can use `AbstractMap.SimpleImmutableEntry` to preserve pairs that have a `null` key or value.

A helper method can be placed in a class:

~~~java
static <K, V> List<Map.Entry<K, V>> snapshotAllowingNulls(Map<K, V> source) {
    List<Map.Entry<K, V>> result = new ArrayList<>();
    for (Map.Entry<K, V> entry : source.entrySet()) {
        result.add(new AbstractMap.SimpleImmutableEntry<>(entry));
    }
    return result;
}
~~~

Import `Map`, `List`, `ArrayList`, and `AbstractMap`. The helper creates a modifiable list where each element is an independent entry that does not support `setValue`.

`SimpleImmutableEntry` is not tied to the Map's view and does not allow replacing the key or value references via `setValue`. The class name does not mean that every object referenced by the key or value is itself immutable. [Java SE 17 — SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Example source:

~~~text
null  -> root
empty -> null
~~~

The copy has two entries: `null=root` and `empty=null`. After the Map changes `empty` to `filled`, the copied entry still retains the `null` value reference copied earlier.

If you also need the list to be unmodifiable, you can expose an unmodifiable wrapper around the list created by the helper, provided nothing else continues to mutate the backing list. Whether `null` is accepted depends on the entry type, how the list is created, and the input data; it cannot be inferred merely from the word "snapshot."

## 7. Where Does List Order Come From?

A list is indexed, but conversion does not invent a new business order on its own. It collects elements in the iteration order provided by the source.

### 7.1. LinkedHashMap: An Example with Explicit Insertion Order

`new LinkedHashMap<>()` preserves insertion order by default. When you insert `B`, then `A`, then `C`, the example lists start in that order. Updating the value of an existing key with `put` does not move that key to the end in insertion-order mode. [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

That is why the demo program uses `LinkedHashMap` for predictable stdout comparison, rather than printing an arbitrary order and treating it as canonical.

`LinkedHashMap` also has an access-order mode selected via a different constructor. In that mode, certain reads or updates can affect the order. You should not generalize that every `LinkedHashMap` always uses insertion order.

### 7.2. TreeMap: Ordered by Key

`TreeMap` keeps keys in natural order or according to a supplied comparator. A list of keys taken from a `TreeMap<String, ...>` with natural ordering follows string order, not insertion time. [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

A `TreeMap` populated with keys `B`, `A`, `C` yields the key list `[A, B, C]` when using the natural order of those strings.

### 7.3. HashMap and Maps Without an Order Guarantee

Do not rely on insertion order, ascending order, or a single printed output from a `HashMap` as a contract. Creating an `ArrayList` from a view preserves the order observed during that iteration; it adds no guarantee for future conversions.

If you need a specific order for reporting, testing, pagination, or stable display, choose a source with an appropriate ordering contract or sort the result by explicit criteria.

Likewise, do not use `Map.of` to build data and assume the resulting list preserves the argument order of the call. Those factory methods are not a way to request insertion order.

## 8. Sort Pairs Before Extracting Keys or Values

To sort by score descending, and by code ascending when scores are tied:

~~~java
List<Map.Entry<String, Integer>> sorted = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                .thenComparing(Map.Entry.<String, Integer>comparingByKey()))
        .toList();
~~~

This snippet assumes non-`null` keys and scores. `Comparator.reverseOrder()` reverses the score order; `thenComparing` adds a tie-breaker by code when scores are equal. [Java SE 17 — Comparator.thenComparing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#thenComparing(java.util.Comparator)).

With the source `C=20`, `B=20`, `A=10`, the result is:

~~~text
[B=20, C=20, A=10]
~~~

Scores are never separated from codes during sorting. If you need a list of codes in that exact ranking, extract the keys after the pairs are ordered:

~~~java
List<String> rankedKeys = sorted.stream()
        .map(Map.Entry::getKey)
        .toList();
~~~

The resulting list is `[B, C, A]`. If you only need the ranked list of scores, use `Map.Entry::getValue` in the final step.

A secondary criterion is useful when multiple pairs share the same score. Sorting solely by score may preserve the initial encounter order among tied pairs, but if the source has no guaranteed order, that will not produce a stable order across runs. Adding the code as a tie-breaker expresses the requirement more clearly.

If `null` values can appear, decide whether `null` comes first or last before choosing a comparator. For example, you can pass a `null`-aware comparator for keys or values. However, `Map.Entry.copyOf` still rejects `null`, so you must choose an appropriate entry-creation approach first; a `null`-aware comparator cannot fix an error that already happened during entry copying.

### Do Not Sort Two Independent Lists and Re-Pair by Index

Starting from `B=20`, `A=10`, `C=20`, if you only sort the key list to `[A, B, C]` and pair it with the old value list `[20, 10, 20]`, you produce `A=20` and `B=10`, corrupting the original data.

Even if two separate list extractions happen to align on a stable, ordered source initially, intermediate edits, filtering, or Map changes between the two extractions can easily break the correspondence. When the task requires pairs, use pairs as the unit of processing.

## 9. Filtering and Transforming into Output Data

You can keep only pairs with a score of `20` or higher:

~~~java
List<Map.Entry<String, Integer>> qualified = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 20)
        .map(Map.Entry::copyOf)
        .toList();
~~~

This snippet assumes non-`null` `Integer` scores. If values can be `null`, the predicate must handle that before performing numeric comparison.

Filtering creates a new result; it does not remove non-qualifying mappings from the Map. If you want to modify the Map, that is a different requirement and needs the appropriate operation on the source structure.

Sometimes output data should have domain-specific names instead of `Map.Entry`. For example, a `record ScoreRow(String code, Integer score)` can clearly represent the code and score columns in a display table. When converting to a record, read both the key and value in the same iteration and construct an independent row.

Whether you use entries or records, changing the outer wrapper still only copies references if the inner fields are objects. It does not automatically deep-copy profiles, addresses, or nested lists inside the value.

A new list is also not a synchronizer back to the Map. Editing a row in a working list does not automatically know which key to update, whether new keys are allowed, or how to handle cases where the Map changed since extraction. Those rules must be designed explicitly at write-back time.

## 10. List Mutability and Element Mutability Are Two Separate Layers

| Creation Approach | List Structure | Entries Held |
| --- | --- | --- |
| `new ArrayList<>(map.entrySet())` | Modifiable | Only copies entry references from the source; not considered independent entry copies |
| `map.entrySet().stream().toList()` | Unmodifiable list | Still lacks an independent entry-copy step |
| `stream().map(Map.Entry::copyOf).toList()` | Unmodifiable list | Independent entries, `setValue` disallowed, rejects null keys/values |
| `stream().map(Map.Entry::copyOf).collect(toCollection(ArrayList::new))` | Modifiable | Independent entries, still disallows `setValue` |
| Helper using `SimpleImmutableEntry` and `ArrayList` | Modifiable | Independent entries, `setValue` disallowed, can represent null keys/values |

`Stream.toList()` (since Java 16) returns an unmodifiable list and preserves encounter order if the stream is ordered. That does not make the element objects themselves immutable. [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

If you specifically need a modifiable `ArrayList`, use the constructor or `Collectors.toCollection(ArrayList::new)`. Do not treat `Collectors.toList()` as a contract requiring a modifiable `ArrayList`: the documentation guarantees neither the implementation type nor the mutability of its result. [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)).

Examine these two different statements:

~~~java
entries.remove(0);
entries.get(0).setValue(500);
~~~

The first statement requires list mutability. The second requires mutability on the entry object at index `0`. The fact that one succeeds does not prove the other will; and a mutable independent entry does not mean it writes back to the Map.

## 11. Pair Copies Can Still Share Value Objects

Consider a `StringBuilder` value:

~~~java
StringBuilder item = new StringBuilder("seed");
Map<String, StringBuilder> source = new LinkedHashMap<>();
source.put("item", item);

List<Map.Entry<String, StringBuilder>> snapshot = source.entrySet().stream()
        .map(Map.Entry::copyOf)
        .toList();
~~~

The entry is detached from the Map. However, the value it holds is still a reference to `item`.

After `item.append("!")`, reading the value from the copied entry shows `seed!`. No value reference was replaced at the entry level; the referenced object itself changed state.

If you then call:

~~~java
source.put("item", new StringBuilder("replacement"));
~~~

The Map now points to the new object. The copied entry still holds the old object `seed!`. This is the difference between **re-mapping a key to a different object** and **mutating the shared object itself**.

Deep copying requires rules for each value type. For a domain model, you can create dedicated immutable data objects or copy each field you need to preserve. You cannot expect a generic Map-to-List conversion method to understand every object relationship and deep-copy them properly.

## 12. When the Map May Be Modified Concurrently

A conversion must iterate over the source. `new ArrayList<>(map.values())` and entry-copying streams do not automatically lock the entire Map or turn multiple reads into an atomic snapshot.

With a regular Map guarded by a lock, the entire list-creation process must follow the same locking protocol as the code that modifies the Map. Specifically, `Collections.synchronizedMap` requires synchronizing on the wrapper Map itself when iterating over its views; do not substitute locking on `keySet` or `entrySet`. [Java SE 17 — Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

With `ConcurrentHashMap`, iteration has a contract suitable for concurrent access, but it does not automatically provide a single point-in-time snapshot of the whole Map. The resulting list may reflect observations gathered over the course of the iteration. [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Two properties must be evaluated separately:

- After creation, whether the copied entries are detached from subsequent mapping changes in the Map.
- During creation, whether the collected pairs belong to a single globally consistent state.

`Map.Entry.copyOf` solves the first property at the level of key–value reference pairs; it does not provide the second property on its own. If the business logic requires a consistent report across multiple keys, choose an appropriate coordination strategy rather than just changing the output collection.

The program in this article keeps the source stable while creating each list and only modifies the Map after the corresponding steps finish.

## 13. Complete Demonstration Program

Save the code as **MapListsDemo.java**. The APIs used are compatible with Java 17; `Map.Entry.copyOf` is the part that requires Java 17 in this example.

The `rejects` method verifies the expected exception type. The `snapshotAllowingNulls` helper creates independent entry copies during iteration while preserving `null` keys or values. The update via `entry.setValue` is performed directly inside the iteration loop, without storing view entries for later use.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapListsDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static <K, V> List<Map.Entry<K, V>> snapshotAllowingNulls(Map<K, V> source) {
        List<Map.Entry<K, V>> result = new ArrayList<>();
        for (Map.Entry<K, V> entry : source.entrySet()) {
            result.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("B", 20);
        scores.put("A", 10);
        scores.put("C", 20);

        Set<String> keyView = scores.keySet();
        Collection<Integer> valueView = scores.values();
        List<String> keys = new ArrayList<>(keyView);
        List<Integer> values = new ArrayList<>(valueView);
        List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
                .map(Map.Entry::copyOf)
                .collect(Collectors.toCollection(ArrayList::new));
        System.out.println("keys=" + keys);
        System.out.println("values=" + values);
        System.out.println("entries=" + entries);

        scores.put("A", 99);
        scores.put("D", 30);
        System.out.println("map-after-put=" + scores);
        System.out.println("key-view=" + keyView);
        System.out.println("value-view=" + valueView);
        System.out.println("copied-keys=" + keys);
        System.out.println("copied-values=" + values);
        System.out.println("snapshot-entries=" + entries);

        keys.remove("B");
        values.add(777);
        entries.remove(0);
        System.out.println("edited-lists=" + keys + " / " + values + " / " + entries);
        System.out.println("map-after-list-edits=" + scores);
        rejects("snapshot-setValue", UnsupportedOperationException.class,
                () -> entries.get(0).setValue(500));

        for (Map.Entry<String, Integer> entry : scores.entrySet()) {
            if (entry.getKey().equals("B")) {
                System.out.println("iterator-setValue-old=" + entry.setValue(25));
            }
        }
        System.out.println("map-after-entry-update=" + scores);
        keyView.remove("D");
        System.out.println("map-after-view-remove=" + scores);

        List<Map.Entry<String, Integer>> frozen = scores.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
        rejects("stream-list-add", UnsupportedOperationException.class,
                () -> frozen.add(Map.entry("X", 1)));
        System.out.println("frozen=" + frozen);

        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(frozen);
        sorted.sort(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                .thenComparing(Map.Entry.<String, Integer>comparingByKey()));
        System.out.println("sorted=" + sorted);
        System.out.println("map-order=" + new ArrayList<>(scores.keySet()));

        Map<String, Integer> tieMap = new LinkedHashMap<>();
        tieMap.put("C", 20);
        tieMap.put("B", 20);
        tieMap.put("A", 10);
        List<Map.Entry<String, Integer>> tieSorted = tieMap.entrySet().stream()
                .map(Map.Entry::copyOf)
                .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                        .thenComparing(Map.Entry.<String, Integer>comparingByKey()))
                .toList();
        System.out.println("tie-sorted=" + tieSorted);

        Map<String, Integer> tree = new TreeMap<>(scores);
        System.out.println("tree-keys=" + new ArrayList<>(tree.keySet()));

        Map<String, String> nullable = new LinkedHashMap<>();
        nullable.put(null, "root");
        nullable.put("empty", null);
        List<Map.Entry<String, String>> nullableEntries = snapshotAllowingNulls(nullable);
        System.out.println("nullable-keys=" + new ArrayList<>(nullable.keySet()));
        System.out.println("nullable-values=" + new ArrayList<>(nullable.values()));
        System.out.println("nullable-entries=" + nullableEntries);
        rejects("copyOf-null-entry-part", NullPointerException.class,
                () -> nullable.entrySet().stream().map(Map.Entry::copyOf).toList());
        rejects("nullable-entry-setValue", UnsupportedOperationException.class,
                () -> nullableEntries.get(0).setValue("changed"));
        nullable.put("empty", "filled");
        System.out.println("nullable-map=" + nullable);
        System.out.println("nullable-snapshot=" + nullableEntries);

        AbstractMap.SimpleEntry<String, Integer> local =
                new AbstractMap.SimpleEntry<>("local", 1);
        local.setValue(2);
        System.out.println("detached-editable-entry=" + local);

        StringBuilder item = new StringBuilder("seed");
        Map<String, StringBuilder> objects = new LinkedHashMap<>();
        objects.put("item", item);
        List<Map.Entry<String, StringBuilder>> shallow = objects.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
        item.append("!");
        System.out.println("shared-value-object=" + shallow.get(0).getValue());
        objects.put("item", new StringBuilder("replacement"));
        System.out.println("rebound-map-value=" + objects.get("item"));
        System.out.println("snapshot-old-reference=" + shallow.get(0).getValue());
    }
}
~~~

Compile and run from the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 MapListsDemo.java
java MapListsDemo
~~~

Exact stdout:

~~~text
keys=[B, A, C]
values=[20, 10, 20]
entries=[B=20, A=10, C=20]
map-after-put={B=20, A=99, C=20, D=30}
key-view=[B, A, C, D]
value-view=[20, 99, 20, 30]
copied-keys=[B, A, C]
copied-values=[20, 10, 20]
snapshot-entries=[B=20, A=10, C=20]
edited-lists=[A, C] / [20, 10, 20, 777] / [A=10, C=20]
map-after-list-edits={B=20, A=99, C=20, D=30}
snapshot-setValue -> UnsupportedOperationException
iterator-setValue-old=20
map-after-entry-update={B=25, A=99, C=20, D=30}
map-after-view-remove={B=25, A=99, C=20}
stream-list-add -> UnsupportedOperationException
frozen=[B=25, A=99, C=20]
sorted=[A=99, B=25, C=20]
map-order=[B, A, C]
tie-sorted=[B=20, C=20, A=10]
tree-keys=[A, B, C]
nullable-keys=[null, empty]
nullable-values=[root, null]
nullable-entries=[null=root, empty=null]
copyOf-null-entry-part -> NullPointerException
nullable-entry-setValue -> UnsupportedOperationException
nullable-map={null=root, empty=filled}
nullable-snapshot=[null=root, empty=null]
detached-editable-entry=local=2
shared-value-object=seed!
rebound-map-value=replacement
snapshot-old-reference=seed!
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. This verifies Java 17 API/language-level compatibility and reports the output on the stated JVM; it is not a claim of running on JVM 17.

Key points to compare in stdout:

- The first three lines show the same three mappings in three forms, with the value list preserving both occurrences of `20`.
- After `put`, the views reflect the new data, while the previously created key list, value list, and entry snapshots retain the data from the earlier copy.
- `edited-lists` changes while `map-after-list-edits` remains unchanged; `snapshot-setValue` is rejected because snapshot entries do not support value updates.
- `iterator-setValue-old` returns the old score and `map-after-entry-update` shows the new score because the operation occurs through the entry currently being iterated.
- `map-after-view-remove` demonstrates direct removal through a view, unlike removal on a copied list.
- `sorted` and `tie-sorted` keep keys paired with their scores; `map-order` shows that sorting a list does not reorder the Map.
- The `nullable` lines distinguish snapshots that allow null components from `Map.Entry.copyOf`, which rejects them.
- The final three lines distinguish mutating a shared value object from re-mapping the Map key to a different object.

## 14. Practice with Answers

### Exercise 1 — Choosing the List Type

One function only needs to check which codes exist; another needs to rank scores and display the associated code. Which view should each function use to build its list?

**Answer:** The first function uses `keySet` to build a `List<K>`. The ranking function uses `entrySet`, creates independent entries, and sorts the pairs before displaying them. Taking only `values` would lose the association between codes and scores.

### Exercise 2 — Are Duplicate Values Lost?

A Map contains `A=10`, `B=10`, `C=20`. How many elements does `new ArrayList<>(map.values())` have? What changes if you use a `Set` instead?

**Answer:** The list has three elements, including both occurrences of `10`. A `Set` can merge equal values and lose occurrence counts. Deduplication should be an explicit requirement, not a default conversion step.

### Exercise 3 — Removing from a View vs. a List

After `List<String> keys = new ArrayList<>(map.keySet())`, does calling `keys.remove("A")` remove `A` from the Map? What about `map.keySet().remove("A")` when the Map supports removal?

**Answer:** The first statement only modifies the independent list. The second operates on the view and removes the mapping from the Map. Both variables may initially contain the same keys, but they have different relationships to the source.

### Exercise 4 — Is a New Entry List Enough for a Snapshot?

Why is `new ArrayList<>(map.entrySet())` not enough to guarantee that pairs remain unchanged when the Map is modified?

**Answer:** The constructor only creates a new list and copies element references; it does not create independent entries. Entries obtained from a view are also subject to iteration-contract restrictions. Add an entry-copying step during iteration, such as `Map.Entry.copyOf` for non-null data or `SimpleImmutableEntry` when null keys or values must be preserved.

### Exercise 5 — Modifiable List, Unmodifiable Entries

A list is created with `map(Map.Entry::copyOf).collect(Collectors.toCollection(ArrayList::new))`. Why can `remove(0)` succeed while `get(0).setValue(...)` throws an exception?

**Answer:** List mutability belongs to `ArrayList`. Entry-value mutability belongs to the object returned by `copyOf`, which disallows `setValue`. The two layers of mutability are independent.

### Exercise 6 — Preserving Null Data

A Map allows null keys and null values, and data must not be dropped or altered. Can you pass every entry directly to `Map.Entry.copyOf`?

**Answer:** No, that method rejects both null keys and null values. Create `new AbstractMap.SimpleImmutableEntry<>(entry)` for each entry during iteration to preserve the data and detach the entry from the Map. Then choose the list's mutability separately as needed.

### Exercise 7 — Preserving Relationships While Sorting

The source in insertion order is `C=20`, `B=20`, `A=10`. You need scores descending, and codes ascending on ties. Which result is correct, and why shouldn't you just sort the key list?

**Answer:** `[B=20, C=20, A=10]`. Sorting the pairs by score and then by code preserves the data relationship. Sorting keys separately and pairing them with unsorted values can create wrong pairs. The secondary sort by code also makes the order between the two `20` entries deterministic.

### Exercise 8 — Copies and Shared Objects

A Map value is a `StringBuilder`. After creating entries with `copyOf`, will mutating the original `StringBuilder` show up in the copy? What if you use `put` to replace it with a new `StringBuilder`?

**Answer:** Mutating the original object is visible through the copied value reference. Replacing the mapping with `put` does not change the reference held by the independent entry. To isolate internal state as well, you need an object-copying rule or an appropriate immutable value type.

## 15. Choose the Output by Its Contract

If you need codes, take the keys; if you need aggregated data without key associations, take the values; if you need key–value rows, keep entries or construct a clearly named row object. Then decide on ordering and mutability for the result.

When you need to retain data for later use, create independent entries during iteration, handle nulls according to an explicit policy, and remember that mutable keys or values can still be shared. Copying into a list only guarantees a new list structure; the level of data isolation comes from how the elements themselves are copied.

This reasoning lets you convert a Map to a list for display, sorting, filtering, or passing across APIs while preserving relationships and understanding exactly where mutations can happen.
