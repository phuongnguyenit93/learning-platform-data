# Unmodifiable Collections Do Not Mean Deep Immutability in Java

## 1. The Problem: Not Being Able to Call `add()` Does Not Mean Data Cannot Change

In Java, a collection can **forbid structural modification through its own interface**, yet the values observed by users through that collection can still change. The reason is that a collection stores **references to elements**, and may simply be a *view* over a source collection.

Consider two examples:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
// view is now [A, B], even though view.add(...) is unsupported.
```

```java
StringBuilder item = new StringBuilder("A");
List<StringBuilder> list = List.of(item);
item.append("B");
// list.get(0).toString() is now "AB", even though list.add(...) is unsupported.
```

Both snippets are illustrative fragments (requiring `import java.util.*`); a complete Java 17 program appears in Section 6. In the first example, **the source collection** continues to change and the *unmodifiable view* reflects those changes. In the second example, **the element object itself** mutates, even though the container has an unmodifiable interface.

Therefore, we must distinguish three concepts:

1. **Structurally unmodifiable through the held reference** (*unmodifiable interface/view*): you cannot successfully call `add`, `remove`, `set`, `put`, or equivalent update operations through that reference.
2. **Independent structural snapshot** (*structural snapshot*): subsequent additions, removals, or replacements in the source collection do not alter the list/element links held in the snapshot.
3. **Deep immutability** (*deep immutability*): there is no valid mutation path through any provided or shared reference to alter either the container structure or the mutable state of elements considered part of the value.

Key point: `unmodifiable` describes **operations disallowed through an API**; `immutable` describes **whether observable state can change over time**. A class can satisfy the first without satisfying the other two.

## 2. Two Independent Axes: Collection Structure and Element State

A collection holds references, not automatic copies of element objects. Hence there are at least two types of mutation to consider:

| Type of Mutation | Example | Can an Unmodifiable Container Prevent It? |
| --- | --- | --- |
| Adding a new element | `list.add(newItem)` | Prevented through that list's own API |
| Removing an element | `list.remove(0)` | Prevented through that list's own API |
| Replacing an element at an index | `list.set(0, other)` | Prevented through that list's own API |
| Mutating the object itself at index 0 | `list.get(0).rename("X")` | **No**, if the element is mutable and its reference is exposed |
| Mutating via an alias to the source collection | `backing.add(newItem)` | **No** for an unmodifiable *view* wrapping a mutable backing |
| Mutating a collection nested inside the collection | `list.get(0).add("X")` | **No**, if the inner list remains mutable |

A reference diagram helps reveal the risks:

```text
source (ArrayList) ──────────────┐
                                 ▼
unmodifiableView ────────────> backing ArrayList ──> MutableItem #1
                                                       ▲
                                                       │
caller.item ────────────────────────────────────────────┘

view.add(...)                 => rejected
source.add(...)               => changes data visible through view
caller.item.rename(...)       => changes element visible through view
```

In the diagram, the last two mutation paths **do not need** to call any mutating method on `unmodifiableView`.

## 3. `Collections.unmodifiableXxx`: Unmodifiable Views

Methods like `Collections.unmodifiableList`, `unmodifiableSet`, and `unmodifiableMap` return a wrapper that does not support modification through the wrapper interface. Elements and structure can still mutate through the **backing collection** if other code continues to hold a reference to it.

A predictable example:

```java
List<String> backing = new ArrayList<>(List.of("red"));
List<String> view = Collections.unmodifiableList(backing);

backing.add("blue");
System.out.println(view); // [red, blue]

view.add("green"); // Throws UnsupportedOperationException
```

An `unmodifiableList` does not automatically call `new ArrayList<>(backing)` to detach from the source. Similarly, `Collections.unmodifiableMap(map)` does not automatically capture an independent copy of the map, and `Collections.unmodifiableSet(set)` does not automatically detach from the original set.

Do not confuse this with an intentional **read-only view**: in some APIs, you *want* recipients to see subsequent updates from the owner without having permission to update through the view. That is valid semantics when clearly designed and documented. However, if an API promises a "snapshot at call time" or an "unchanging value", a wrapper alone is not enough.

If you want a **structural** snapshot, you can copy first and then wrap:

```java
List<String> snapshot =
    Collections.unmodifiableList(new ArrayList<>(backing));
```

After that, `backing.add(...)` does not change `snapshot`'s size. Even so, if the list holds `MutableItem` instead of `String`, both the snapshot and the source can still point to the same `MutableItem`; mutating the element still has an effect.

## 4. What Do `List.of`, `List.copyOf`, and `Stream.toList` Guarantee?

### 4.1. `List.of(...)`

`List.of(a, b, ...)` creates a list that does not support structural modification. It does not allow `null` elements. However, if `a` or `b` are mutable objects, those objects **remain mutable**; the list stores references rather than automatically cloning elements.

```java
StringBuilder name = new StringBuilder("A");
List<StringBuilder> names = List.of(name);
name.append("B");
System.out.println(names.get(0)); // AB
```

### 4.2. `List.copyOf(source)`

`List.copyOf` (Java 10+) returns an unmodifiable list containing the elements of the input collection at copy time, in the observed iteration order. When `source` is a typical mutable collection, later structural changes to the source will not alter the structural contents of the resulting list.

However:

- It is a **shallow copy of elements**: mutable objects inside remain shared by reference.
- `List.copyOf` does not allow `null` elements; if the input contains `null`, it throws `NullPointerException`.
- If the input is already a suitable unmodifiable list, the JDK may **reuse that exact instance**; do not rely on `copyOf` always allocating a new list object.
- The snapshot does not define element equality semantics itself; `List.equals()` and `List.hashCode()` use the elements' equality/hash relations.

### 4.3. `Stream.toList()` in Java 17

`stream.toList()` returns a `List` that forbids modification through standard update operations, preserving the stream's encounter order if any. Unlike `List.copyOf`, `Stream.toList()` can contain `null`. The list being unmodifiable **does not** make mutable element objects immutable. Never infer "deep immutability" from the "unmodifiable" property of a stream's result.

### 4.4. `Set` and `Map` Have the Same Issue

- `Set.of`, `Set.copyOf`, and `Map.of`, `Map.copyOf` create unmodifiable containers without deep-copying mutable keys/values.
- `Set.of` rejects duplicate elements under equality; `Set.copyOf` from a collection with duplicates retains only one representative, with no guarantee as to which equal instance is kept. If duplicate information matters, do not mechanically convert a list to a set.
- `Map.copyOf` does not accept `null` keys/values; `Set.copyOf` does not accept `null`. Converting can change the null policy previously accepted by an API.
- Iteration order of unmodifiable collections from `Set.of/copyOf` and `Map.of/copyOf` must not be assumed to be insertion order or sorted order.
- If a mutable object is used as a map key or set element and fields participating in `equals/hashCode` are mutated, lookups can break **even when the map/set itself forbids structural modification**.

## 5. How Do Shallow Copies and Deep Immutability Differ?

A **shallow copy** creates a new container while keeping element references. With immutable elements such as `String`, `Integer`, or a record containing only immutable values, a shallow copy is usually enough to protect the entire value the API cares about.

With mutable elements, a shallow copy is not enough:

```java
StringBuilder part = new StringBuilder("A");
List<StringBuilder> input = new ArrayList<>();
input.add(part);

List<StringBuilder> shallow = List.copyOf(input);
part.append("B");

System.out.println(shallow.get(0)); // AB
```

If external code holds `part`, it can still change the data presented by `shallow`. To get a truly stable snapshot, you must **copy or convert each mutable element** into a corresponding immutable representation:

```java
List<String> stable =
    input.stream()
         .map(StringBuilder::toString)
         .toList();
```

Here `StringBuilder::toString` creates an immutable `String` value at iteration time; mutating the builder afterward does not change the recorded Strings. This is a **value-based snapshot approach** suitable when only string contents are needed, without preserving the identity of individual builders.

For nested data, copying must traverse each mutable level:

```java
// input: List<List<String>>, where the inner lists are initially mutable.
// After this operation, both the outer container and each inner container are
// unmodifiable; String is also immutable.
List<List<String>> nestedSnapshot = List.copyOf(
    input.stream().map(List::copyOf).toList()
);
```

This is an illustrative fragment using `java.util.List`, placed in a context where an `input` variable of the right type exists. The `List<List<MutableItem>>` case still requires copying/converting each `MutableItem`; a two-level wrapper is not yet deep immutability.

An important point: "deep immutability" must be evaluated with respect to **the relevant state graph**. If a child object is a network connection, an entity with a unique identity ID, or a live data source, copying every node in a generic clone style is neither always feasible nor semantically sound. A class must define which data belongs to its value and what boundary needs snapshotting.

## 6. Runnable Java 17+ Example: Views, Snapshots, and Mutable Elements

The complete example below contrasts four cases: a view reflecting a backing list; a structural snapshot detaching the backing but not the elements; a deep snapshot of element values; and a nested list copied at every level.

Save as **`CollectionDeepImmutabilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class CollectionDeepImmutabilityDemo {
    static final class MutableItem {
        private String code;

        MutableItem(String code) {
            this.code = Objects.requireNonNull(code);
        }

        String code() {
            return code;
        }

        void rename(String newCode) {
            this.code = Objects.requireNonNull(newCode);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof MutableItem that)) return false;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    record ImmutableItem(String code) {
        ImmutableItem {
            Objects.requireNonNull(code);
        }
    }

    static final class Catalog {
        private final List<ImmutableItem> items;

        Catalog(List<MutableItem> source) {
            Objects.requireNonNull(source);
            this.items = source.stream()
                .map(item -> new ImmutableItem(item.code()))
                .toList();
        }

        List<ImmutableItem> items() {
            return items;
        }
    }

    static final class ShallowKey {
        private final List<MutableItem> parts;

        ShallowKey(List<MutableItem> source) {
            parts = List.copyOf(source);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ShallowKey that)) return false;
            return parts.equals(that.parts);
        }

        @Override
        public int hashCode() {
            return parts.hashCode();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("red"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("blue");
        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
        try {
            view.add("green");
        } catch (UnsupportedOperationException ex) {
            System.out.println("View rejects add: true");
        }

        MutableItem item = new MutableItem("A");
        List<MutableItem> shallow = List.copyOf(List.of(item));
        Catalog catalog = new Catalog(List.of(item));
        item.rename("B");

        System.out.println("Shallow item: " + shallow.get(0).code());
        System.out.println("Catalog item: " + catalog.items().get(0).code());
        try {
            catalog.items().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Catalog rejects clear: true");
        }

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> outer = new ArrayList<>();
        outer.add(inner);
        List<List<String>> outerOnly = List.copyOf(outer);
        List<List<String>> allLevels = List.copyOf(
            outer.stream().map(List::copyOf).toList()
        );

        inner.add("y");
        System.out.println("Outer-only nested: " + outerOnly.get(0));
        System.out.println("All-level nested: " + allLevels.get(0));

        MutableItem keyPart = new MutableItem("K1");
        ShallowKey key = new ShallowKey(List.of(keyPart));
        Set<ShallowKey> keys = new HashSet<>();
        keys.add(key);
        int before = key.hashCode();
        keyPart.rename("K2");
        System.out.println("Key hash changed: "
            + (before != key.hashCode()));
    }
}
```

Compile and run with **JDK 17 or later** in the directory containing the file:

```bash
javac CollectionDeepImmutabilityDemo.java
java CollectionDeepImmutabilityDemo
```

Standard output:

```text
View: [red, blue]
Snapshot: [red]
View rejects add: true
Shallow item: B
Catalog item: A
Catalog rejects clear: true
Outer-only nested: [x, y]
All-level nested: [x]
Key hash changed: true
```

Detailed explanation:

1. `Collections.unmodifiableList(source)` is a **view** over `source`; when `"blue"` is added to the source, the view shows `[red, blue]`. `List.copyOf(source)` created an initial structural snapshot `[red]`, so it does not change.
2. The view rejects `add` through itself; the exception only confirms the view API is unmodifiable, **not that the backing cannot change**.
3. `shallow` holds the exact `MutableItem` reference. Even though the container forbids updates, `item.rename("B")` changes the observable element value to `B`.
4. `Catalog` converts each `MutableItem` into an `ImmutableItem` with an immutable `String` field. The value is captured while it is `"A"`, independent of later changes to `item`. `Stream.toList()` provides an unmodifiable container, so both the structure and record values in the example remain stable.
5. `outerOnly` copies the **outer list** yet still references the mutable `inner`; when `inner` is modified, the contents of `outerOnly.get(0)` change. `allLevels` copies the inner list before copying the outer list; the value `[x]` is preserved.
6. `ShallowKey` copies the container with `List.copyOf` yet still holds a `MutableItem` whose equality/hash is based on a mutable `code`. Changing `code` from `K1` to `K2` changes the hash of the entire `ShallowKey`. This is dangerous if `ShallowKey` is currently used as a key in a `HashSet`/`HashMap`. The example checks only that the hash changed, without depending on assumptions about buckets or implementation-specific lookup outcomes.

## 7. Relation to the `equals()` and `hashCode()` Contract

In Java, a `List` is compared by element order: `List.equals` compares elements sequentially using equality rules; `List.hashCode` aggregates element hashes in order. `Set` and `Map` have equality/hash contracts based on their respective elements or entries.

If a mutable element resides in a list, mutating the element can change:

- The result of `list.equals(otherList)`.
- The value of `list.hashCode()`.
- The `hashCode()` of an object wrapping the list and using the list as a component of equality/hash.

This is why a key created with `List.copyOf(mutableElements)` **can still be an unstable key** even though the list forbids structural modification. Once an object resides in a hash structure, avoid mutating information used in the key's `equals()` and `hashCode()`. If you need a content-based key, store elements as immutable value objects or snapshots.

Principles to follow:

- **Equal implies same hash:** if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`; the reverse is not required.
- **Hash consistent with equality state:** the hash code must stay stable when information used in equality does not change. Mutating a mutable element can alter both equality and hash.
- **Do not use container unmodifiability as proof of hash key safety.** Check keys, values, and nested objects alike.
- **Do not put mutable objects as keys of a `Map` merely because the map was built with `Map.copyOf`.** Map structural immutability and key stability are two different matters.

If a mutable element **does not** use the mutating fields in `equals/hashCode` (for instance, a class inheriting identity equality), editing display data may not alter the list's hash. Yet the list is still **not deeply immutable**: observable contents of its elements still change. These are two separate criteria to check.

## 8. Designing APIs That Protect Collection Values

### 8.1. When a Collection Holds Immutable Values

Example with `List<String>`:

```java
final class Tags {
    private final List<String> tags;

    Tags(List<String> input) {
        tags = List.copyOf(input);
    }

    List<String> tags() {
        return tags;
    }
}
```

This is a complete illustrative Java class without `main`. `Tags` holds a structural snapshot via `List.copyOf`, and `String` is immutable. Therefore, the getter can return the stored list directly: callers cannot `add/set/remove` through it and cannot mutate String contents. If the business domain allows `null` or needs to preserve a different structure, you must choose a contract-appropriate copy method instead of applying `copyOf` blindly regardless of data.

### 8.2. When a Collection Holds Mutable Elements

Do not stop at `List.copyOf(input)`:

```java
// Example: the value to expose is only the name at creation time.
List<String> namesSnapshot = input.stream()
    .map(Person::name)
    .toList();
```

This is an illustrative code snippet, assuming `input` is `List<Person>` and `Person.name()` returns `String`. The result is an unmodifiable list of immutable Strings. If the entire person state is needed, design an immutable DTO/record snapshot:

```java
record PersonSnapshot(String id, String name) {}
// Inside a transformation pipeline, if Person has the corresponding getters:
List<PersonSnapshot> snapshots = input.stream()
    .map(p -> new PersonSnapshot(p.id(), p.name()))
    .toList();
```

This is also an illustrative code snippet; the record above is only deeply immutable if its components are immutable values. If you pass a `List<MutableAddress>` into the record, the record does not automatically deep-copy it.

### 8.3. When Nested Values Are Maps/Lists

With `Map<String, List<String>>` and immutable Strings, you can copy each list and then copy the map:

```java
// input is Map<String, List<String>>.
Map<String, List<String>> nested = new HashMap<>();
input.forEach((key, value) ->
    nested.put(key, List.copyOf(value)));
Map<String, List<String>> snapshot = Map.copyOf(nested);
```

This snippet requires importing `java.util.Map` and `java.util.HashMap`, and is an illustrative fragment in a scope with an `input` variable. The result forbids structural modification of the map and value lists, while Strings in both keys and values are immutable. If the map holds mutable objects as keys or values, you must handle them. If insertion order or `null` values must be preserved, use an appropriate collection type and wrapping strategy rather than silently changing data semantics.

### 8.4. Distinguishing Snapshots from Live Data

An API can choose either of two contracts:

- **Snapshot:** "The received data is the value at call time; subsequent updates from the owner are not reflected in the returned copy."
- **Live view:** "The returned data may reflect updates from the owner; the recipient cannot update through this view."

Both are valid if clearly documented. To support thread safety or hashing, additional guarantees are needed on synchronization and **element object** stability; an unmodifiable API alone does not solve everything.

## 9. Common Misconceptions

| Misconception | Reality | How to Handle |
| --- | --- | --- |
| "Calling `add` throws an exception, so the list is deeply immutable" | It may only be a view and/or contain mutable elements | Check backing aliases and every element level |
| "`Collections.unmodifiableList` automatically copies the source" | It is a view wrapping the backing collection | Copy first and then wrap if a snapshot is needed |
| "`List.copyOf` clones each element object" | It copies element references | Convert to an immutable DTO/value or appropriate deep copy |
| "`List.of` containing mutable elements is still deeply immutable" | Container cannot be modified; elements remain mutable | Create value snapshots of elements |
| "`final List<Person>` is an immutable list" | `final` only prevents reassigning the field; does not lock list/person contents | Store an immutable snapshot and control getters |
| "Records are always deeply immutable" | A record component can point to a mutable array/collection/object | Copy-in, copy-out, and handle each mutable component |
| "Copying an outer list is enough for all nested lists" | Inner lists can still be shared | Copy every mutable level |
| "An unmodifiable `Map` protects mutable values" | Mutable values still change through aliases | Copy or use immutable values |
| "An unmodifiable collection stabilizes `hashCode`" | Hash can depend on mutable elements | Use stable fields/values in equality/hash |
| "Copying is always an atomic snapshot under concurrency" | Source may be mutated during copying | Synchronize reads/writes or use designed immutable snapshots |

## 10. Limitations to Know

### 10.1. There Is No Universal `deepCopy` for Every Object Graph

Objects can have circular references, hold system resources, caches, multithreaded state, or unique identity keys. Copying every node can distort semantics. Clearly identify the **value representation that needs immutability**, build a dedicated immutable representation, or establish explicit data ownership.

For example, for a `Person` with a list of mutable `Address` objects, you can store `List<AddressSnapshot>` where each address contains immutable String and numeric fields. This is business-value copying, which is usually clearer than trying to blindly clone the entire `Person`.

### 10.2. Immutability and Thread Safety Are Not Identical

A truly immutable graph, once constructed and **safely published**, can be shared for reading without locks to protect that value. However, calling `List.copyOf(source)` itself while another thread is modifying `source` does not guarantee an atomic snapshot; inconsistent data or exceptions can occur depending on the structure. You need a synchronization protocol between writer and copier, or ownership transfer/exchange of immutable snapshots.

An unmodifiable view of an `ArrayList` does not automatically make the `ArrayList` thread-safe. Likewise, mutable element objects inside an immutable container still require synchronization if accessed and modified by multiple threads.

### 10.3. Copying Cost and API Path Choices

Copying a container has a cost proportional to collection size; deep copying adds the cost of each element and nested data. If a getter frequently creates snapshots of a large list, consider storing an immutable snapshot once, exposing query operations like `size()`/`get()` over immutable values, or organizing an appropriate versioning/snapshot mechanism. Do not optimize by accidentally returning a mutable alias that breaches immutability.

## 11. Checklist for Reviewing a Collection Field

When evaluating a class with a `List`, `Set`, or `Map` field, answer in order:

1. Where is the collection created? Does any caller still hold a reference to the backing collection?
2. Does the constructor keep the input collection's reference directly, wrap it in a view, or create a structural snapshot?
3. Does the getter return a copy, an immutable container, or a live view? Does the contract clearly state the distinction?
4. Are the elements immutable or mutable? Can individual elements be mutated through an external alias or `get`?
5. Do elements contain arrays, lists, maps, or mutable objects inside? Are they protected to the necessary depth?
6. Do map keys/values and set elements have equality/hash based on mutable state?
7. Are there special requirements regarding `null`, duplicate elements, order, or data compatibility?
8. When another thread modifies the source during copying, must the snapshot data be consistent, and what mechanism guarantees that?
9. Do tests try mutating the source after the constructor, mutating an element via a retained reference, mutating via the getter, and mutating nested collections?

A good practical check is to test calling `add` on the returned list **while also trying to mutate the backing list, individual element objects, and nested collections**. Only checking for an exception from `add` is not enough to conclude deep immutability.

## 12. Self-Check

**Q1.** `Collections.unmodifiableList(backing)` returns a view; then `backing.add("B")`. Does the view show `"B"`?

**Answer:** Yes. The wrapper forbids updates through the view, yet reflects changes to the backing collection.

**Q2.** `List.copyOf(source)` holds `MutableItem`. After copying, can the caller invoke `item.rename("B")` and observe the changed name through the list?

**Answer:** Yes, if the list and the caller still hold the same `MutableItem` reference. `List.copyOf` only copies structure/elements by reference, without cloning individual mutable objects.

**Q3.** You store a `List<String>` from `List.copyOf` in a final field and return that exact list from the getter. Is deep immutability for those strings protected?

**Answer:** Yes, assuming no other mutable data in the relevant graph, because the list is unmodifiable and `String` is immutable. Whether the container is a new instance on each call does not affect the immutability of this value.

**Q4.** You create `List<List<String>> outerCopy = List.copyOf(outer)` while the inner lists remain mutable. Do you have deep immutability yet?

**Answer:** No. You must snapshot each inner list first (for example `List.copyOf(inner)`) before freezing the outer list.

**Q5.** Why does `Map.copyOf(source)` not guarantee a map key is safe for use in a hash structure if the key is mutable?

**Answer:** `Map.copyOf` does not deep-copy keys. If data participating in the key's `equals/hashCode` is mutated, equality or hash can change, breaking lookups even though the map itself forbids structural modification.

**Q6.** A class returns `Collections.unmodifiableList(new ArrayList<>(source))`. Is this a deep snapshot?

**Answer:** This is an independent **structural** snapshot at the outer list level; it is not a deep snapshot if `source` contains mutable objects or nested collections.

**Q7.** A record contains only a `List<MutableItem>` component. Does the record automatically make that value deeply immutable?

**Answer:** No. The component field is final, yet the mutable list and mutable items can be modified through shared references; copy-in/copy-out design and element snapshots are needed when required.

---

**Takeaway:** "Structurally unmodifiable" only protects **operations on the container through a single reference**. An *unmodifiable view* can still reflect updates to the backing collection; an immutable structural snapshot can still contain mutable objects. For deep immutability, examine the entire observable data graph, protect aliases on both input and output, and convert relevant mutable components into immutable values or snapshots.