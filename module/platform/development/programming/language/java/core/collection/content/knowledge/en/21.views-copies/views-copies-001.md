# Distinguishing Collections That Own Their Data from Views Sharing a Backing Source

## 1. A Returned List Can Be Independent Data or a Window Into a Source

Suppose an object manages a list of tasks and returns a `List` to the caller. The caller adds or removes elements on the returned result and then observes that the managing object's data also changed.

One possible cause is that the result shares the underlying structure: it may be the original object itself or a view backed by it.

Conversely, two lists with separate structures can still hold the same task object. When a field of that object is modified, both lists see the change.

Therefore, you cannot simply ask, "Is this a copy?". You need to separate three questions:

1. Are the set of elements, positions, or mappings managed independently of the source?
2. Which modification operations are permitted through the surface you are holding?
3. Are the element objects themselves shared?

This article uses the phrase **owning the storage structure** to refer to a collection that manages its own element links, such as a new `ArrayList` created from source data.

This is not exclusive ownership enforced by Java's type system. A collection can still have multiple variables pointing to it; a structure with its own links can still share element objects.

A **view** provides an access surface backed by underlying data. It may restrict the range, change the representation, or limit modifications while remaining tied to the source.

## 2. Two Layers of Data: Container Structure and Element Objects

### 2.1. A Collection That Manages Its Own Structure

An expression such as `new ArrayList<>(source)` creates an `ArrayList` that manages its own list structure.

Once copying completes under valid source conditions, adding or removing a link in the source list does not automatically add or remove the corresponding link in the new `ArrayList`.

You can visualize this as:

```text
source ──> list structure 1 ──> Item A, Item B
copy   ──> list structure 2 ──> Item A, Item B
                                Items may still be shared
```

The independence lies in the list structure. Do not infer that `Item A` and `Item B` have been cloned.

### 2.2. A View Delegates Operations to the Source

A view typically maintains a relationship to the underlying data and forwards appropriate operations to the source rather than maintaining an independent set of elements.

For example, `Collections.unmodifiableList(source)` provides a read-only surface over the source list. As long as the source undergoes valid changes, readers of the view can observe those changes; modifications through the view are rejected by contract.

```text
source variable ────────> source list ──> Item A, Item B
view variable ──> view wrapper ───┘
```

Views have their own usage conditions. Do not interpret this diagram as meaning that every source modification is valid for every view, especially with `List.subList`.

The distinction between collections that manage storage and views is introduced in [Java 17 Collection, View Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

### 2.3. Reference Assignment Is Even Simpler Than a View

If you write `alias = source`, both variables point to the same object. No new collection and no new view wrapper are created merely by assignment.

A view can be a different object from the source while still sharing the underlying data. Therefore, a `!=` comparison result does not prove that two structures are independent.

`equals` does not prove independence either. Two collections can hold the same data at a point in time while having completely different sharing policies.

### 2.4. The List/Set/Collection Type Does Not Capture Ownership Policy

A `List` variable can hold an `ArrayList`, a `subList`, a read-only wrapper, a list backed by an array, or the result of `List.copyOf`.

The type `List` alone does not tell you whether the result is a copy, whether additions are allowed, or whether it is tied to another source.

You must read the contract of the method that creates or returns the result. Terms such as *backed by*, *view*, *copy*, and *unmodifiable* have distinct meanings in the documentation.

## 3. Example 1: Alias, View, Structural Copy, and Shared Elements

Save as **StructureOwnerAndView.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class StructureOwnerAndView {
    static final class Line {
        final String code;
        int quantity;

        Line(String code, int quantity) {
            this.code = code;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return code + ":" + quantity;
        }
    }

    public static void main(String[] args) {
        Line first = new Line("A", 1);
        List<Line> owner = new ArrayList<>(List.of(first, new Line("B", 2)));
        List<Line> alias = owner;
        List<Line> view = Collections.unmodifiableList(owner);
        List<Line> copy = new ArrayList<>(owner);
        List<Line> snapshot = List.copyOf(owner);

        System.out.println("alias is owner: " + (alias == owner));
        System.out.println("view is owner: " + (view == owner));
        owner.add(new Line("C", 3));
        System.out.println("view after owner add: " + view);
        System.out.println("copy after owner add: " + copy);
        System.out.println("snapshot after owner add: " + snapshot);

        first.quantity = 9;
        System.out.println("owner after element edit: " + owner);
        System.out.println("copy after element edit: " + copy);
        System.out.println("snapshot after element edit: " + snapshot);

        copy.remove(0);
        System.out.println("copy after its remove: " + copy);
        System.out.println("owner after copy remove: " + owner);
        try {
            view.add(new Line("D", 4));
        } catch (UnsupportedOperationException expected) {
            System.out.println("view add: rejected");
        }
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot clear: rejected");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StructureOwnerAndView.java
java StructureOwnerAndView
```

Stdout:

```text
alias is owner: true
view is owner: false
view after owner add: [A:1, B:2, C:3]
copy after owner add: [A:1, B:2]
snapshot after owner add: [A:1, B:2]
owner after element edit: [A:9, B:2, C:3]
copy after element edit: [A:9, B:2]
snapshot after element edit: [A:9, B:2]
copy after its remove: [B:2]
owner after copy remove: [A:9, B:2, C:3]
view add: rejected
snapshot clear: rejected
```

The examples in this article are compiled with `--release 17` and run on OpenJDK 24.0.2. The `--release` flag selects the language/API level and target bytecode version; it does not change the runtime JVM version.

### 3.1. An Alias Is the Same Object, While a View Is a Different Object Still Tied to the Source

`alias == owner` evaluates to `true` because there is simply another variable pointing to the `owner` list.

`view != owner` in this example, yet when `owner` adds `C`, `view` still reads `C`. Having a distinct view object does not create independent data.

Do not use an object identity check as a substitute for the data-sharing contract.

### 3.2. Copy and Snapshot Keep Their Own Captured Links

The `copy` variable is created with the `ArrayList` constructor; `snapshot` is created with `List.copyOf`. Both are created before `C` is added to `owner`.

`owner` adding `C` does not cause `copy` or `snapshot` to gain `C`. Removing `A` from `copy` also does not remove `A` from `owner`.

The name `snapshot` here refers to the captured set of links under the example's non-concurrent conditions. It does not promise a deep copy of all data or an atomic read transaction in every program.

### 3.3. Modifying Line A Affects the Element Layer

The `first` object is referenced by `owner`, `copy`, and `snapshot` alike. Changing its `quantity` to `9` makes all three print `A:9`.

This is not because the lists continuously copy state to one another. They are reading the same `Line` object.

If you want to avoid sharing mutable element data, you need an immutable model or an explicit element-copying policy.

### 3.4. Disallowing Modification Through the Result Is Not Enough to Distinguish a View from a Copy

The `view.add` call is rejected because of the read-only wrapper.

The `snapshot.clear` call is also rejected, but `snapshot` does not reflect element `C` added to `owner` after creation.

Two results that both block modifications can still have different relationships to the source structure. The documentation for [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) and [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) specifies those different contracts.

## 4. Range Views and Array-Backed Views

### 4.1. SubList Is a Range of the Source List

`List.subList(from, to)` returns a view from index `from` (inclusive) to `to` (exclusive).

By default, it does not copy the elements in that range into a separate `ArrayList`. If the source supports it, modifications through `subList` can affect the source list itself.

An operation like `subList(...).clear()` can remove an entire range from the original list. This is the intended use of a view when the caller deliberately wants to affect the source.

### 4.2. Important Limitations of subList

According to the [Java 17 List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)) contract, non-structural changes are reflected between the two views.

However, if the backing list is structurally modified through any path other than the returned `subList`, the semantics of the `subList` become undefined. Structural modifications include size changes or changes that otherwise disrupt ongoing iteration.

The example uses `full.set` to replace an element and `window.remove`/`add`/`clear` through the view itself. It does not add directly to `full` and then assume `window` remains valid.

Do not invent a rule such as "adding to the source always updates the `subList` like an independent list." Nor should you assume `ConcurrentModificationException` is the mandatory API outcome for every misuse of the view.

If you need a range that remains independent of later structural changes to the source, copy that range while the data is still valid.

### 4.3. Arrays.asList Is a Fixed-Size View Backed by an Array

`Arrays.asList(array)` creates a `List` backed by the passed-in array. Setting an element through the `List` updates the array slot; assigning to an array slot is visible through the `List`.

It does not allow increasing or decreasing the number of elements like a regular `ArrayList`. Fixed size does not mean element replacement is forbidden.

These permissions are described in [Java 17 Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### 4.4. Example 2: Modifying a Range and an Array Through Views

Save as **RangeAndArrayViews.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RangeAndArrayViews {
    public static void main(String[] args) {
        List<String> full = new ArrayList<>(
                List.of("zero", "one", "two", "three", "four"));
        List<String> window = full.subList(1, 4);
        List<String> copy = new ArrayList<>(window);

        window.set(1, "TWO");
        System.out.println("full after window set: " + full);
        full.set(1, "ONE");
        System.out.println("window after full set: " + window);

        window.remove(0);
        window.add("extra");
        System.out.println("window after its edits: " + window);
        System.out.println("full after window edits: " + full);
        window.clear();
        System.out.println("full after window clear: " + full);
        System.out.println("window size: " + window.size());
        System.out.println("copy remains: " + copy);

        String[] names = {"Lan", "Mai"};
        List<String> arrayView = Arrays.asList(names);
        names[0] = "Linh";
        System.out.println("view after array edit: " + arrayView);
        arrayView.set(1, "MAI");
        System.out.println("array after view set: " + Arrays.toString(names));
        try {
            arrayView.add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("array view add: rejected");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RangeAndArrayViews.java
java RangeAndArrayViews
```

Stdout:

```text
full after window set: [zero, one, TWO, three, four]
window after full set: [ONE, TWO, three]
window after its edits: [TWO, three, extra]
full after window edits: [zero, TWO, three, extra, four]
full after window clear: [zero, four]
window size: 0
copy remains: [one, two, three]
view after array edit: [Linh, Mai]
array after view set: [Linh, MAI]
array view add: rejected
```

### 4.5. Reading the Output According to Which Source Is Actually Affected

The `window` variable initially contains `one`, `two`, `three`. `window.set(1, "TWO")` changes element `two` in `full`; `full.set(1, "ONE")` is in turn visible through `window`.

The `remove`/`add` operations through `window` modify the corresponding range in `full`. `window.clear()` clears the current range, leaving `full` with only `zero` and `four`.

`copy` still holds `one`, `two`, `three` because it captured the links before those operations. The example uses `String` to focus on structure without mutable element fields changing.

In the array section, `names[0]` is changed to `Linh` and is visible through `arrayView`. `arrayView.set` changes the second slot to `MAI`. `add` is rejected because the view does not manage a new resizable array.

## 5. Map Collection Views Backed by Source Mappings

### 5.1. keySet, values, and entrySet Are Not Three Independent Copies

`Map.keySet` returns a `Set` view of the keys; `values` returns a `Collection` view of the values; `entrySet` returns a `Set` view of the mappings.

Adding a mapping to the map is visible through previously obtained views. When a view supports removal, removing through the view affects the mapping in the map.

Having only a key does not provide enough information to create a new value. Therefore, do not assume `keySet.add` is supported simply because the return type is `Set`.

The backed-view contracts and add/remove permissions are specified in [Java 17 Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### 5.2. Entry Is Another Modification Surface

A `Map.Entry` obtained while iterating over a map that permits updates may support `setValue` to modify the mapping's value.

You must read the contract regarding how long an entry remains connected to the map and the implementation's modification permissions. Do not hold an arbitrary entry across arbitrary map modifications and assume the connection remains valid.

In the example below, `setValue` is called directly during iteration over `LinkedHashMap`'s `entrySet`, not after a structural modification outside the iteration.

### 5.3. Example 3: Views Removing Mappings and Limitations of Wrapping entrySet

Save as **MapViewsAndEntryPermissions.java**:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class MapViewsAndEntryPermissions {
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("alpha", 1);
        source.put("beta", 2);
        source.put("gamma", 3);
        Set<String> keys = source.keySet();
        Collection<Integer> values = source.values();
        Set<Map.Entry<String, Integer>> entries = source.entrySet();
        Map<String, Integer> copy = new LinkedHashMap<>(source);

        source.put("delta", 4);
        System.out.println("keys after map put: " + keys);
        keys.remove("beta");
        values.remove(3);
        System.out.println("map after view removals: " + source);

        for (Map.Entry<String, Integer> entry : entries) {
            if (entry.getKey().equals("alpha")) {
                entry.setValue(10);
                break;
            }
        }
        System.out.println("map after entry setValue: " + source);
        try {
            keys.add("new-key");
        } catch (UnsupportedOperationException expected) {
            System.out.println("key view add: rejected");
        }

        Set<Map.Entry<String, Integer>> setOnlyWrapper =
                Collections.unmodifiableSet(entries);
        for (Map.Entry<String, Integer> entry : setOnlyWrapper) {
            if (entry.getKey().equals("alpha")) {
                entry.setValue(11);
                break;
            }
        }
        System.out.println("map after set-only entry edit: " + source);

        Map<String, Integer> readOnlyMap = Collections.unmodifiableMap(source);
        try {
            for (Map.Entry<String, Integer> entry : readOnlyMap.entrySet()) {
                entry.setValue(99);
                break;
            }
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable map entry edit: rejected");
        }
        source.put("epsilon", 5);
        System.out.println("read-only map after source put: " + readOnlyMap);
        System.out.println("copy remains: " + copy);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 MapViewsAndEntryPermissions.java
java MapViewsAndEntryPermissions
```

Stdout:

```text
keys after map put: [alpha, beta, gamma, delta]
map after view removals: {alpha=1, delta=4}
map after entry setValue: {alpha=10, delta=4}
key view add: rejected
map after set-only entry edit: {alpha=11, delta=4}
unmodifiable map entry edit: rejected
read-only map after source put: {alpha=11, delta=4, epsilon=5}
copy remains: {alpha=1, beta=2, gamma=3}
```

### 5.4. Removing Through Key/Value Views Removes From the Map

After the map adds `delta`, the previously obtained `keys` view also contains `delta`.

`keys.remove("beta")` removes the `beta=2` mapping. `values.remove(3)` removes the `gamma=3` mapping in this sample data.

`entry.setValue` changes `alpha` to `10`. The `copy` created earlier still retains `alpha=1`, `beta=2`, `gamma=3` because it has its own set of mapping links.

`LinkedHashMap` is used so that the printed order in the example is stable by insertion order. Do not assume every `Map` has that iteration order.

### 5.5. Wrapping a Set as Unmodifiable Does Not Automatically Make Its Entries Unmodifiable

The `setOnlyWrapper` variable is `Collections.unmodifiableSet(entries)`. It blocks set-modification operations through the `Set` surface, but it does not automatically turn each `Map.Entry` element into an unmodifiable object.

During this iteration, `entry.setValue(11)` still modifies `alpha` in the source map.

This is a concrete manifestation of the rule that "not modifying the collection" differs from "not modifying the element objects." For an entry, modifying that object can even be a path to updating the map.

If the goal is to provide a map that disallows modifications both through the map itself and through its collection views, `Collections.unmodifiableMap` provides the appropriate contract. The example shows that `setValue` from this map wrapper's `entrySet` is rejected.

The [Java 17 Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) documentation describes blocking modifications directly and through views.

### 5.6. A Read-Only Map Can Still Read New Source Data

`source` is still retained and continues to `put` `epsilon`. The `readOnlyMap` variable sees the new mapping because it is a view, not an independent copy.

If you need an unchanging snapshot of the mapping set when the source changes, you must create a separate mapping structure under the desired policy and then apply the appropriate modification permissions.

The key/value objects themselves must still be considered at the element-data layer. A map wrapper does not automatically deep-copy them.

## 6. Three Classification Axes Must Be Read Independently

| Created result | Structural relationship to source | Modifications through result | Can elements be shared? |
| --- | --- | --- | --- |
| `alias = source` | Same object | Same as that object | Yes |
| `new ArrayList<>(source)` | Separate list after copying | Same as `ArrayList` | Yes |
| `Collections.unmodifiableList(source)` | View backed by source | Disallows `List` modification through view | Yes |
| `source.subList(from, to)` | Range view, with its own validity conditions | Optional operations supported by source | Yes |
| `Arrays.asList(array)` | Array-backed view | Element replacement allowed; resizing disallowed | Yes |
| `List.copyOf(source)` | Does not reflect later source structural edits | Disallows modification on returned `List` | Yes |
| `map.keySet()` | View of map keys | Removal if supported; cannot add keys via `add` | Uses the map's keys |

This table does not replace the detailed contract of each view, especially structural modification limits on `subList` or modifying a map during iteration.

### 6.1. Modifiability Does Not Mean Independent Ownership

A modifiable `subList` is still a view. `Arrays.asList` allows element replacement yet remains backed by the array. `keySet` allows removal yet still affects the source map.

A successful modification call only proves that the operation is supported under the current conditions.

### 6.2. Unmodifiability Does Not Mean a Snapshot or Deep Immutability

A read-only view can reflect edits from the source. A `List.copyOf` result has a link set stable against source structural edits yet still holds shared mutable elements.

No single word substitutes for all three: modification permissions, sharing relationship, and copy depth.

### 6.3. Do Not Rely on a Factory Allocating a New Object

`List.copyOf` specifies the behavior of the result; the API may reuse an existing suitable unmodifiable result instead of being forced to allocate a new object on every call.

What you should rely on is that the result does not reflect subsequent structural changes to the source `Collection` per its contract. Do not check that objects are distinct using `!=` to prove a factory behaved correctly.

"Structural ownership" in design is not a promise about how the JVM allocates memory inside every collection-creation method.

### 6.4. Target Data Policies Can Also Differ

`List.copyOf` rejects `null` elements. The `ArrayList` constructor can copy a list containing `null`.

A target `Set` also enforces uniqueness; a sorted structure has its own ordering rules. Copying into a different type does not automatically preserve every characteristic of the source.

Choose the target type based on the data and usage requirements, not merely on the desire to "make a copy."

## 7. Ownership at API Boundaries

### 7.1. Receiving Input Data

If an object directly stores a `List` passed in by the caller, the caller may still hold a reference variable and continue modifying that `List`.

Declaring the field holding the `List` as `final` only prevents reassigning the field to another object. It does not prevent external code from adding/removing elements in the shared collection.

If the object needs to maintain its own stable dataset, copy the input according to a clear policy before storing it. If the data requires deep immutability, you must also choose an appropriate element type or element-copying strategy.

If the object intentionally shares a source that changes over time, keeping a view or reference is possible, but that must be a documented contract.

### 7.2. Returning Output Data

| Intended contract | Return strategy to evaluate |
| --- | --- |
| Caller may modify internal state directly | Return a reference or an intentionally modifiable view |
| Caller only reads, but needs to follow new internal data | Read-only view of the source |
| Caller may modify its own result without changing internal structure | Modifiable structural copy |
| Caller receives its own link set, unmodifiable through the result | Appropriate unmodifiable copy result |
| Caller must not affect internal element data either | Immutable elements or a deep-copy policy |

Do not call a getter "safe" merely because its return type is `List` or because it is wrapped with `unmodifiableList`. You must state what operations and sharing relationships it is safe with respect to.

### 7.3. Wrapping a Private Copy Can Combine Two Goals

`Collections.unmodifiableList(new ArrayList<>(source))` combines capturing the links into a separate list with blocking `List` modifications through the result.

As long as no reference to that private list is exposed, subsequent additions or removals on `source` will not alter the link set in the result.

This is still a shallow copy with respect to the element objects. And reading the source to copy it must still occur under valid source conditions.

`List.copyOf` is another option with its own contract, including disallowing `null`. The two options are not unconditionally interchangeable for all data.

### 7.4. Deep Copying Must Be Defined by the Data Domain

A `Line` may hold references to products, history, or other sub-elements. Creating a new `Line` does not necessarily isolate all underlying data.

You must decide which components can be shared, which must be copied, and whether relationships among objects must be preserved.

With a suitable immutable data model, sharing elements can be the right choice and simpler than cloning an object graph.

Do not mechanically use serialization or `clone` and assume every ownership problem is solved.

## 8. Lifecycle, Cost, and Usage Conditions

### 8.1. A View May Retain a Reference to the Source Longer Than Expected

A small view may still hold a reference to a large source structure in a given implementation. Keeping a view does not automatically decouple the storage lifetime of the viewed slice from the entire source.

When you need to keep a range long-term without depending on the original structure, copying that range may be the appropriate choice.

Do not label every view a memory leak; examine the reference graph and actual usage lifetime.

### 8.2. Copying Has a Cost, but Also Provides Valuable Independence

A separate structure must store its own links and read the data to initialize. For large sources, this can incur significant cost.

Views help avoid eagerly copying all data when controlled sharing is the goal. However, using a view to "save cost" when the requirement demands a stable result changes the meaning of the API.

Do not assert that every view is created in O(1), that every view operation has the same complexity, or that every copy has the same cost. Read the relevant contract and implementation when performance is a requirement.

### 8.3. Views and Copies Do Not Automatically Provide Thread Safety

A view of an `ArrayList` does not turn the source into a safe concurrent-update structure.

A copy created while the source is being modified is not automatically an atomic snapshot either. Iterating to copy must follow the source's contract and the consistency mechanism in use.

If you need a stable version for processing, coordinate writers and readers or publish stable data versions under an appropriate model.

### 8.4. Do Not Modify the Source in Ways That Invalidate a View

With `subList`, take special care to avoid structurally modifying the backing list directly and then continuing to use the view as if nothing changed.

With map views, structurally modifying a map during iteration must follow permitted paths such as `iterator.remove`; do not rely on the absence of an exception in a single run.

A collection that owns its own data also still has its own iterator and concurrency contracts. Owning the structure does not exempt you from iteration rules.

## 9. How to Read Documentation and Test Sharing Relationships

### 9.1. Look for Observable Guarantees

When encountering an API that returns a `Collection`/`List`/`Set`/`Map`, check:

1. Is the result a view or a copy?
2. What is the backing source?
3. Which changes are reflected, and in which direction?
4. Which modification operations are supported?
5. Are there conditions that invalidate the view?
6. Are elements shared, or copied to some depth?
7. What are the ordering, `null`, and data rules of the result?

This is how to read the usage contract, rather than guessing internal class names or using reflection to probe.

### 9.2. Write Tests That Distinguish the Cases

Comparing data immediately after creation does not distinguish a view from a copy with the same contents.

Meaningful checks include:

- Perform a valid modification on the source and observe whether the result reflects it.
- Modify through the result (if supported) and observe the source.
- Remove a link in the copy and verify the source still retains its own link.
- Modify an element object to detect sharing at the element layer.
- Test different permissions: `set`, `add`, `remove`, entry updates.
- Test data conditions such as `null` if a copy choice changes them.

Do not deliberately trigger contract-violating states and treat an incidental stdout output or exception as the API specification.

### 9.3. Use Simple Elements First, Mutable Elements Second

`String` or numbers make it easy to see additions, removals, and positional replacements because there are no mutable domain fields to track.

Then introduce a type like `Line` to test element-level sharing. Mixing both concerns from the start makes it easy to mistakenly conclude that a structural copy "doesn't work."

The examples in this article intentionally separate those stages so that each conclusion has clear evidence.

## 10. Common Misconceptions

| Statement | Accurate understanding |
| --- | --- |
| Different objects mean no shared data | A view that is a different object can still be backed by the source |
| Same initial data means same ownership policy | A view and a copy can have identical contents at creation time |
| Mutable means owning independent data | Many views are mutable and write through to the source |
| Unmodifiable means never changes | The source or the elements inside may still change |
| `List.copyOf` is a deep copy | Element objects can still be shared |
| A `final` `List` is an immutable `List` | `final` only prevents reassigning the field reference |
| `subList` is a new `ArrayList` of a slice | It is a range view with its own validity conditions |
| `subList` always stays valid after any `add` to `full` | Structural edits outside the view can make view semantics undefined |
| `Arrays.asList` is a resizable `ArrayList` | It is a fixed-size `List` backed by an array |
| `Map.keySet` is an independent `Set` | It is a view of the keys in the map's mappings |
| Wrapping `entrySet` with `unmodifiableSet` protects the entire map | Entries inside still need `setValue` permissions considered |
| A copy read from a mutating source is an atomic snapshot | A proper consistency mechanism is required |
| Having "copy" in the name means a new object must always be allocated | A factory may reuse a valid result per its contract |
| Having its own structure means exclusive ownership of all elements | Java does not automatically enforce such exclusive ownership |

## 11. Self-Check Exercises

### Exercise 1. Do two different names create two collections?

After `alias = source`, does removing an element via `alias` affect `source`?

**Suggested answer:** Yes, if the operation is supported by that object. Both variables point to the same object; assignment does not create a copy.

### Exercise 2. Does a view that is a different object have its own data?

An `unmodifiableList` is a different object from the source `ArrayList`. The source adds a valid element, and the view reads that element. What is proven?

**Suggested answer:** Different object identity does not create structural independence. The result is a view backed by the source.

### Exercise 3. Is being unable to add enough to know something is a snapshot?

Two results both throw `UnsupportedOperationException` on `add`. Can you conclude neither reflects edits to the source?

**Suggested answer:** No. Modification permissions through the result and the relationship to the source are two separate axes.

### Exercise 4. Why does a copy still see the new quantity?

A list is copied with `new ArrayList<>(source)`. A shared `Line` has its `quantity` modified. Does the copy seeing the new number prove its structure is still tied to the source?

**Suggested answer:** No. It shows that the same element reference is shared; the list structure can still be independent.

### Exercise 5. Where does `subList.clear` remove elements?

A valid `subList` of a source `ArrayList` calls `clear`. Should you expect the original list to keep the entire range intact?

**Suggested answer:** No. Removal through the view affects the corresponding range in the source list when supported.

### Exercise 6. Is modifying `full` outside `window` always valid?

You created `window = full.subList(...)`, then called `full.add` to add an element, and continued using `window`. Can all subsequent results be considered guaranteed by the contract?

**Suggested answer:** No. Structurally modifying the backing list outside the `subList` can make the view's semantics undefined.

### Exercise 7. Can an array-backed `List` be modified?

`Arrays.asList(array)` does not allow `add`. Does it follow that `set` must also be rejected?

**Suggested answer:** No. It has a fixed size, but it supports element replacement and reflects changes to and from the array by contract.

### Exercise 8. What does removing a key via `keySet` do?

A modifiable `Map` has a `keySet` view. `keys.remove("x")` succeeds. Does the mapping for `"x"` still exist in the map?

**Suggested answer:** No. Removing through the key view removes the corresponding mapping from the map.

### Exercise 9. Why is `unmodifiableSet(entrySet)` not enough?

In a `LinkedHashMap`, the entry set is wrapped with `unmodifiableSet`, yet an entry during iteration still supports `setValue`. Can the map's value be modified through that path?

**Suggested answer:** Yes, in that case. You need a contract that protects the map and its views, such as `unmodifiableMap`, if that is the goal.

### Exercise 10. What should you choose for an independent result that disallows `List` modifications?

You want the result not to reflect future additions/removals in the source, and the recipient must not be able to modify the structure through the result. Is `unmodifiableList(source)` alone enough?

**Suggested answer:** Not yet. You need to combine a policy for capturing independent data with appropriate modification permissions, such as `List.copyOf` if its data conditions fit. You must still consider the element objects.

## 12. Reference Documentation

- [Collection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): views, unmodifiable collections, and synchronization policies.
- [ArrayList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): a list managing its own structure and the `Collection`-copying constructor.
- [List.subList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)): range views and source structural modification conditions.
- [List.copyOf — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): result not reflecting source structural edits, `null` handling, and reusability.
- [Collections.unmodifiableList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): read-only view of a `List`.
- [Collections.unmodifiableMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): blocking map modifications directly and through collection views.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `keySet`, `values`, `entrySet`, and contracts of mapping views.
- [Arrays.asList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size `List` backed by an array.
