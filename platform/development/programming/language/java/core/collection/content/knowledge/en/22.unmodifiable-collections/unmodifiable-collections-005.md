# List.copyOf, Set.copyOf, and Map.copyOf

## 1. Starting from the need to freeze data for reading

A method receives a configuration list from outside and stores it for later use. If it stores the input reference directly, the caller can still add, remove, or replace elements through the variable they hold. If it only exposes a read-only wrapper, modifications through the wrapper are blocked, but the underlying data can still change through the source. When the requirement is "keep the received dataset without following subsequent structural modifications to the source," a stronger boundary is needed.

The three static factory methods `List.copyOf`, `Set.copyOf`, and `Map.copyOf` serve this boundary. They take an existing collection or map and return a result that does not allow structural modifications through the result's API. The source can still be modified if the source type itself supports it; adding, removing, or replacing element references or mappings in the source after copying does not alter what the result holds.

You can think of the result as a **structural snapshot**: it locks in the element references, or the key–value associations, taken from the input. This framing helps separate two questions:

- Which elements does the resulting collection contain, and in what order, if any?
- Can the objects referenced by the collection still mutate themselves?

`copyOf` answers the first question according to the contract of `List`, `Set`, or `Map`. It does not automatically copy the entire internal state of each object to answer the second question.

For example, a list containing `String` is usually easy to use as stable data because `String` is immutable. A list containing `StringBuilder` can still display different text when a builder is modified. Both lists may disallow `add`, `remove`, and `set`; the difference lies in the element objects.

This lesson proceeds in order: distinguishing the three data shapes; understanding the rules for null, duplicates, and ordering; verifying each factory; and then determining the level of protection needed when using them in constructors or return values. Learners should know that collections can hold references to objects and be familiar with basic operations of `ArrayList`, `Set`, and `Map`.

## 2. Three signatures, three copying semantics

These `copyOf` methods have been available since Java 10. All programs in this lesson use Java 17 and are saved as standalone files named after their `public` class. The `javac --release 17` and `java` commands should be run with JDK 17 or a compatible newer version.

| Call | Input | Result type | What is preserved |
| --- | --- | --- | --- |
| `List.copyOf(collection)` | `Collection<? extends E>` | `List<E>` | Elements in the input's iteration order, including duplicates |
| `Set.copyOf(collection)` | `Collection<? extends E>` | `Set<E>` | Each distinct value under set semantics, with no iteration order guarantee |
| `Map.copyOf(map)` | `Map<? extends K, ? extends V>` | `Map<K, V>` | Key–value mappings, with no iteration order guarantee |

`List.copyOf` does not only accept a `List`: a `Set` is also a `Collection`. However, the resulting `List` only locks in the order the source provided during iteration. It does not turn a source without a guaranteed order into a meaningful business sorting rule.

`Set.copyOf` can also accept a `List`. This is useful when converting iterable data into a read-only set. Deduplication is a data-modeling choice: occurrence counts are no longer represented in the result. If frequency matters, do not use a `Set` to replace the input list.

`Map.copyOf` accepts a `Map` because it needs the relationship between keys and values. A list of standalone values does not provide enough information to infer keys; a list of pairs that might have duplicate keys still needs conflict-resolution rules before creating a `Map`.

Distinguish `of` from `copyOf`: `List.of("A", "B")` creates data from element arguments; `List.copyOf(existing)` takes elements from an existing `Collection`. If `existing` is a `List`, `List.of(existing)` creates a list with a single element—that `List` itself—rather than flattening its inner elements. Do not swap the two calls just because both return a read-only `List`.

The official API documentation describes the signature and version of each method: [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).

## 3. List.copyOf: preserve order, preserve duplicates, block replacement

For a list, position is part of the data. From an ordered source `[A, B, A]`, the result must represent those three positions in the exact order the source was iterated. The two occurrences of `A` are not merged; `size()` remains three.

Once you have the result, three kinds of modifications are blocked:

- Adding an element increases the number of positions.
- Removing an element decreases the number of positions.
- Replacing an element at a position with `set`, even though the size does not change.

The last point distinguishes an unmodifiable list from a fixed-size list. A `List` that does not support adding or removing does not necessarily forbid `set`. Do not use `add` throwing an exception as proof that every other `List` shares the same contract as `List.copyOf`.

Suppose `source` is an `ArrayList` and has been copied to `snapshot`. Calling `source.set(0, "Z")` replaces the reference that the source stores at the first position; it does not change the reference stored by the result at the corresponding position. Similarly, `source.add("C")` does not add an element to the result. This is structural container independence.

If the first element is a mutable object, calling a mutating method on that object is a different matter. `source.get(0).append(...)` does not change the positions or references of the source; it mutates the very object held by both sides. Sections 9 and 10 will verify this boundary.

The input `List` must not be null, and must not contain null elements. An empty `List` is valid: a list containing no elements is different from having no `List` object at all.

## 4. List experiment: snapshot and read-only wrapper

Save the program as `ListCopyOfDemo.java`. The program creates a source, a read-only wrapper of the source, and two snapshots: one from the source, and one from the wrapper itself. Taking a snapshot from the wrapper must still produce a result independent of subsequent structural changes to the underlying data.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListCopyOfDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> snapshotFromView = List.copyOf(view);

        source.set(0, "Z");
        source.add("C");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("snapshotFromView=" + snapshotFromView);
        System.out.println("emptySize=" + List.copyOf(List.of()).size());

        try {
            snapshot.set(0, "X");
        } catch (UnsupportedOperationException e) {
            System.out.println("set=UnsupportedOperationException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add(null);
        try {
            List.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            List.<String>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListCopyOfDemo.java
java ListCopyOfDemo
```

Stdout:

```text
source=[Z, B, A, C]
view=[Z, B, A, C]
snapshot=[A, B, A]
snapshotFromView=[A, B, A]
emptySize=0
set=UnsupportedOperationException
nullElement=NullPointerException
nullSource=NullPointerException
```

Read the output across three points in time. Initially, both the source and the results see `A, B, A`. Two mutating calls are made on `source` after both snapshots have been created. When printed, both the source and `view` show `Z, B, A, C`, while both snapshots still show `A, B, A`.

The `snapshotFromView` line avoids a common misconception: "if the input is already read-only, just return it." A wrapper that reads through to the source can continue to change its observable content. The result of `copyOf` must satisfy the structural snapshot contract, even if the input is passed through a variable with a read-only interface.

Calling `snapshot.set(0, "X")` is blocked even though it does not change the size. The two null cases are prepared separately to pinpoint where the error occurs: `ArrayList` in the example allows adding null; the exception is observed at `List.copyOf(withNull)`. If a factory that already forbids null were used to prepare the data, the program could fail before actually reaching `copyOf`.

The exception-catching blocks only help the experiment keep running to observe multiple cases. In real API design, declare input preconditions and handle invalid data at the appropriate boundary; do not use exceptions to randomly probe the capabilities of arbitrary `List` instances.

## 5. Set.copyOf: deduplication changes data semantics

A `Set` answers the question "is this value present?" rather than storing occurrence counts like a `List`. If the source has `beta, alpha, beta`, the resulting set has two distinct values. This is normal behavior for `Set.copyOf`, not a duplicate-data error.

Distinguish this clearly from `Set.of`. Passing two equal elements to `Set.of` throws `IllegalArgumentException`, whereas `Set.copyOf` accepts a `Collection` with duplicate elements and keeps one representative from each group of equal elements. Do not infer from the label "read-only factory" that every factory handles duplicate input the same way.

If two objects are considered equal by `equals` but carry different additional information, do not rely on whether the retained representative is the first or last one. For example, two item objects with the same ID but different descriptions might be considered equal by class rules. If you need to pick the latest description, handle that rule beforehand; `Set.copyOf` is not a tool for selecting the winning record by time.

The result does not promise to preserve the insertion order or sorting order of the source. A `LinkedHashSet` source with its own order or a `TreeSet` with its own comparator does not turn the `Set.copyOf` result into the corresponding specialized set type.

In the next experiment, printing via `new TreeSet<>(snapshot)` only creates an alphabetical presentation so stdout is easy to inspect. It does not prove that `snapshot` itself has that order. When comparing sets in program checks, check elements and set equality; only check order when the API guarantees order.

## 6. Set experiment: deduplication and input rules

Save as `SetCopyOfDemo.java`. The source is deliberately chosen as a `List` so that the duplicate count is observable before converting to a `Set`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("beta", "alpha", "beta"));
        Set<String> snapshot = Set.copyOf(source);

        System.out.println("sourceSize=" + source.size());
        System.out.println("snapshotSize=" + snapshot.size());
        System.out.println("snapshotForDisplay=" + new TreeSet<>(snapshot));

        source.clear();
        source.add("gamma");
        System.out.println("sourceNow=" + source);
        System.out.println("snapshotAfterChange=" + new TreeSet<>(snapshot));

        try {
            snapshot.add("delta");
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }

        try {
            Set.of("beta", "beta");
        } catch (IllegalArgumentException e) {
            System.out.println("ofDuplicate=IllegalArgumentException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add("alpha");
        withNull.add(null);
        try {
            Set.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            Set.<String>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SetCopyOfDemo.java
java SetCopyOfDemo
```

Stdout:

```text
sourceSize=3
snapshotSize=2
snapshotForDisplay=[alpha, beta]
sourceNow=[gamma]
snapshotAfterChange=[alpha, beta]
add=UnsupportedOperationException
ofDuplicate=IllegalArgumentException
nullElement=NullPointerException
nullSource=NullPointerException
```

`sourceSize=3` and `snapshotSize=2` are evidence of the change in data shape. After `source.clear()` and `source.add("gamma")`, the result still contains `alpha` and `beta`; changes to the source do not propagate to the resulting set.

Calling `snapshot.add("delta")` attempts to add a new value and directly demonstrates that modification is blocked. The `Set.of("beta", "beta")` case is separated and printed under a different name to avoid attributing an `of` exception to `copyOf`.

For null data, `Set` has no policy to "skip invalid elements." Both null inside the `Collection` and null in place of the `Collection` itself cause an error. If the business requirement is to strip nulls, that must be an intentional normalization step before calling the factory, and you must decide whether stripping them loses important information.

Printing used its own sorting step. Do not remove `TreeSet` and then expect raw stdout of the `Set` to be `[alpha, beta]` on every run or every JDK.

## 7. Map.copyOf: locking in key–value associations

For a `Map`, both the key set and the value associated with each key must be protected. If the source initially contains `alpha -> 1` and `beta -> 2`, and then the source changes `beta` to `20`, the created result still maps `beta` to `2`. A new key added to the source does not appear in the result either.

You cannot modify the resulting `Map` with `put`, `remove`, `replace`, or other mapping-changing methods. Indirect paths through `keySet`, `values`, or `entrySet` are not backdoors to modify the `Map` either. In the experiment, removing a key through `keySet` and calling `setValue` on an `Entry` are both blocked.

Read "cannot modify values through the Map" carefully. If a value is a `List`, replacing the `List` associated with a key is changing a mapping in the `Map`. Calling `add` on the retrieved `List` is mutating the value object. These two operations act on two different objects; a read-only `Map` does not automatically turn a `List` inside it into a read-only `List`.

The resulting `Map` does not accept null keys or null values. The source's rules may be broader: a `HashMap` used as the source may allow them, but that does not make converting it with `Map.copyOf` valid.

`Map.copyOf` also does not carry over the iteration order of `LinkedHashMap` or the comparator of `TreeMap` as a guarantee on the result. If a report needs key ordering, explicitly build an ordered presentation step. If the API itself requires `SortedMap` or `NavigableMap` operations, the `Map` returned by the factory cannot replace that contract.

For a normal `Map` source whose key rules are consistent with `equals`, each key already has at most one mapping. When loading raw data with multiple records sharing a key into a `Map`, the decision of which record to keep happens when building the source `Map`. `Map.copyOf` does not accept a merge function and does not infer a "latest wins" policy.

## 8. Map experiment: source changes, result keeps old mappings

Save as `MapCopyOfDemo.java`. `TreeMap` in the print lines is only used to fix display order; it is not the actual type requested from `Map.copyOf`.

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class MapCopyOfDemo {
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("beta", 2);
        source.put("alpha", 1);
        Map<String, Integer> snapshot = Map.copyOf(source);

        source.put("beta", 20);
        source.put("gamma", 3);
        System.out.println("sourceForDisplay=" + new TreeMap<>(source));
        System.out.println("snapshotForDisplay=" + new TreeMap<>(snapshot));
        System.out.println("oldBeta=" + snapshot.get("beta"));

        try {
            snapshot.put("delta", 4);
        } catch (UnsupportedOperationException e) {
            System.out.println("put=UnsupportedOperationException");
        }

        try {
            snapshot.keySet().remove("alpha");
        } catch (UnsupportedOperationException e) {
            System.out.println("keySetRemove=UnsupportedOperationException");
        }

        try {
            snapshot.entrySet().iterator().next().setValue(99);
        } catch (UnsupportedOperationException e) {
            System.out.println("entrySetValue=UnsupportedOperationException");
        }

        Map<String, Integer> nullKey = new HashMap<>();
        nullKey.put(null, 1);
        try {
            Map.copyOf(nullKey);
        } catch (NullPointerException e) {
            System.out.println("nullKey=NullPointerException");
        }

        Map<String, Integer> nullValue = new HashMap<>();
        nullValue.put("alpha", null);
        try {
            Map.copyOf(nullValue);
        } catch (NullPointerException e) {
            System.out.println("nullValue=NullPointerException");
        }

        try {
            Map.<String, Integer>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 MapCopyOfDemo.java
java MapCopyOfDemo
```

Stdout:

```text
sourceForDisplay={alpha=1, beta=20, gamma=3}
snapshotForDisplay={alpha=1, beta=2}
oldBeta=2
put=UnsupportedOperationException
keySetRemove=UnsupportedOperationException
entrySetValue=UnsupportedOperationException
nullKey=NullPointerException
nullValue=NullPointerException
nullSource=NullPointerException
```

After the source changes the value of `beta` and adds `gamma`, the source display shows `beta=20` along with the new key. The result display still shows `beta=2` without `gamma`. The `oldBeta=2` line checks the mapping directly and therefore does not depend on iteration order.

The three modification cases go through three different paths:

| Call path | Target object receiving the operation | What is requested to change |
| --- | --- | --- |
| `snapshot.put(...)` | Resulting `Map` | Add a mapping |
| `snapshot.keySet().remove(...)` | Key-set view | Remove the mapping with the corresponding key |
| `snapshot.entrySet().iterator().next().setValue(...)` | `Entry` obtained from the result | Replace the value in a mapping |

All three are rejected. The `Entry` case does not need to predict which key appears first: every `Entry` obtained from this result disallows changing its value via `setValue`.

The two sources containing null are created separately with `HashMap`, each testing a single kind of violation. That way, `nullKey` and `nullValue` in stdout pinpoint the exact condition under test. The null case for the `Map` itself is a third condition, independent of keys and values.

Reading a read-only `Map` can still return mutable objects. In this example the keys are `String` and the values are `Integer`, so there is no way to mutate their internal state as there would be with a `List` value. Inspect the actual data types before drawing conclusions about the degree of immutability.

## 9. Shallow copy limits and data ownership

"Shallow copy" means creating a boundary at the container while keeping the object references taken from the source. The three factories do not know how to create an independent copy of every application-defined class. There is no single universal rule that works for every object graph, resource connection, or relationship between objects.

You can picture a `List` as having two layers:

1. The list layer: the positions and the references stored at each position.
2. The element layer: the internal state of the objects that those references point to.

`List.copyOf` protects the list layer in the result. To protect the element layer, you need immutable objects or an appropriate transformation/copying policy. If an element is itself a collection, you must decide whether to protect that layer as well.

`Map` adds the distinction between keys and values. `Map.copyOf` locks in the key–value reference pairs. It does not invoke a "deep copy" operation on each key or value. A `Map<String, List<String>>` may disallow changing which `List` is associated with a key while still allowing mutations to the currently associated `List` if that `List` happens to be an `ArrayList`.

For `Set` elements and `Map` keys, mutable objects also affect identity semantics. Mutating state involved in `equals` or `hashCode` after inserting an object into a set or using it as a key can violate the structure's usage contract. Do not infer from "the outer collection is read-only" that mutating those fields is safe. Choose keys and elements with stable equality semantics throughout their lifetime.

A deep copy is not always necessary. A configuration of `Map<String, List<String>>` can be sufficiently protected by snapshotting each inner `List` and then snapshotting the outer `Map`, because `String` has no mutable state. With `Map<String, List<Customer>>`, that approach still shares the same `Customer` instances. You must identify precisely which data layers need independence.

"Ownership" in this context is the convention of who is allowed to hold and modify which data. `copyOf` lets an object accept an input collection without continuing to grant the caller permission to modify its internal list or mappings. It does not revoke any references to the element objects that the outside world already holds.

## 10. Ownership experiment: shared elements, nested collections, and constructors

Save as `CopyOfOwnershipDemo.java`. The program contains three independent cases:

- A `List` containing a builder shows that element references are still shared.
- A `Map` containing a `List` shows the difference between snapshotting only the outer `Map` and also snapshotting the inner `List`s.
- `Catalog` accepts a `List` of names to keep its own configuration, without following additions made by the caller to the input.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CopyOfOwnershipDemo {
    static final class Catalog {
        private final List<String> names;

        Catalog(Collection<String> input) {
            names = List.copyOf(input);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<StringBuilder> source =
                new ArrayList<>(List.of(new StringBuilder("draft")));
        List<StringBuilder> shallow = List.copyOf(source);
        source.get(0).append("-edited");
        System.out.println("sameElement=" + (source.get(0) == shallow.get(0)));
        System.out.println("shallowText=" + shallow.get(0));

        List<String> permissions = new ArrayList<>(List.of("read"));
        Map<String, List<String>> sourceMap = new HashMap<>();
        sourceMap.put("admin", permissions);
        Map<String, List<String>> outerOnly = Map.copyOf(sourceMap);

        Map<String, List<String>> staged = new HashMap<>();
        sourceMap.forEach((key, value) -> staged.put(key, List.copyOf(value)));
        Map<String, List<String>> nestedSnapshot = Map.copyOf(staged);

        permissions.add("write");
        System.out.println("outerOnly=" + outerOnly.get("admin"));
        System.out.println("nestedSnapshot=" + nestedSnapshot.get("admin"));
        sourceMap.put("admin", new ArrayList<>(List.of("replacement")));
        System.out.println("sourceMapping=" + sourceMap.get("admin"));
        System.out.println("oldMapping=" + outerOnly.get("admin"));

        List<String> input = new ArrayList<>(List.of("Java"));
        Catalog catalog = new Catalog(input);
        input.add("SQL");
        System.out.println("catalogNames=" + catalog.names());
        try {
            catalog.names().add("HTTP");
        } catch (UnsupportedOperationException e) {
            System.out.println("catalogAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CopyOfOwnershipDemo.java
java CopyOfOwnershipDemo
```

Stdout:

```text
sameElement=true
shallowText=draft-edited
outerOnly=[read, write]
nestedSnapshot=[read]
sourceMapping=[replacement]
oldMapping=[read, write]
catalogNames=[Java]
catalogAdd=UnsupportedOperationException
```

The `sameElement=true` line compares the two element references, not the identity of the two collections. `shallowText=draft-edited` appears because both the source and the result hold the same builder. No `add` or `set` was performed on `shallow`.

In the nested `Map` case, both results were created when the permissions list only contained `read`. Then `permissions.add("write")` mutates the old `List`:

- `outerOnly` still holds a reference to that old `List`, so it reads `[read, write]`.
- `nestedSnapshot` holds the read-only `List` snapshotted earlier, so it reads `[read]`.

Next, the source replaces the entire `List` associated with key `admin` with another `List` containing `replacement`. `outerOnly` does not follow the new mapping; it continues to hold the old `List` `[read, write]`. The two lines `sourceMapping` and `oldMapping` demonstrate two properties at once: the mapping itself was locked in, while the old value object could still have been mutated.

The `staged` variable is a temporary `Map` used to collect the snapshotted `List`s. Once preparation is complete, `Map.copyOf(staged)` locks in the outer layer. This is a two-layer procedure specific to the data types in the example, not a general-purpose deep-copy algorithm for all object types.

In `Catalog`, the `names` field is `final`, but `List.copyOf(input)` is what actually isolates the internal list from changes to the input list. If you only wrote `names = input`, the `final` keyword would still not prevent `input.add("SQL")` from modifying the contents of the list held by the object.

The `names()` method can return the `names` field directly in this design because the collection is locked in and the `String` elements are immutable. There is no need to create a new snapshot on every read just to prevent add/remove operations by the caller. If the element type is later changed to a mutable object, the return contract must be re-evaluated; keeping the same method name does not preserve the same level of protection.

## 11. Data equality does not mean the same object

The name `copyOf` does not promise that every call allocates a new collection with a different identity. When the input already meets the appropriate conditions, the implementation may reuse an existing read-only result. This optimization does not change the observable data contract.

Therefore, do not design code around either of these two assumptions:

- "Since I called copy, `result != input` is guaranteed."
- "Since the input is read-only, `result == input` is guaranteed."

When you want to check data, use the appropriate semantics: `List` checks elements and order, `Set` checks the set of elements, `Map` checks the mappings. When you want to check isolation from the source, modify the source in ways its contract allows and observe the result. The first two programs did that without needing to know the implementation class name of the result.

The factory results are value-based objects: do not choose them as synchronization lock objects or rely on object identity to drive business logic. Use a dedicated lock object when the design truly needs synchronization, with a clear management mechanism.

This also explains why you should not cast the result to `ArrayList`, `HashSet`, or `HashMap`. The factories provide the published interface, not a promise that the implementation name matches the source structure's name. Fix code by removing casts and programming to the required contract; if you need a mutable copy, explicitly construct a mutable type.

Do not infer from possible reuse that `copyOf` is always cheap or always zero-allocation. For a mutable source, creating independent data may require iterating the source and storing separate references. Measure with realistic data when copying cost affects a critical path; do not build identity assumptions into algorithms.

## 12. Choosing a tool by mutability and source dependency

Before choosing a method, describe the contract in concrete sentences: "can the recipient modify it?", "if the source changes, does the result follow?", "are element objects shared?". The single word "immutable" on its own is usually not enough to answer all three.

| Requirement | Recommended choice | What still needs attention |
| --- | --- | --- |
| Recipient may modify its own `List` | `new ArrayList<>(source)` | Elements may still be shared |
| Recipient may only read and must see changes from the source `List` | `Collections.unmodifiableList(source)` | Underlying source can still change |
| Recipient only reads a frozen list | `List.copyOf(source)` | Rejects null; does not deep-copy |
| Recipient only needs frozen distinct values | `Set.copyOf(source)` | Loses occurrence counts; no order guarantee |
| Recipient only reads frozen mappings | `Map.copyOf(source)` | Rejects null keys/values; inner values may be mutable |
| Recipient needs ordering or a specialized interface | Choose a structure and wrapper matching that contract | Must state whether dependency on the source remains |

The table uses `List` to illustrate the difference between a copy constructor, a wrapper, and a factory. For `Set` and `Map`, you also need to distinguish mutability and relationship to the source; do not choose solely based on whether a method name contains `copy` or `unmodifiable`.

A wrapper can be very appropriate if the goal is to provide a read window into data managed by an owner. `copyOf` is appropriate when you want to publish a frozen dataset to a recipient. These are two different contracts that a design may need in different places.

If you need a resulting `List` that can be modified further, do not try modifying `List.copyOf` and catch the exception to fall back. Create a mutable copy directly. If you need to sort and then publish read-only, perform the sorting step on mutable data before taking the snapshot; do not call a sort operation on a frozen `List` expecting the factory to switch modes automatically.

If you need to preserve the insertion order of a set or map as part of an API, do not use `Set.copyOf`/`Map.copyOf` to promise that order. You can prepare a dedicated ordered structure and wrap it read-only, provided no modification path to the source remains to alter the published data. The preparation must reflect the application's actual contract, not just the superficial class name.

Compare the description of how a wrapper reads through to the source in [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) to see clearly why a read-only view still differs from a frozen dataset.

## 13. Null, empty data, and validation responsibility

All three factories accept empty data as valid. An empty `List`, empty `Set`, and empty `Map` are still objects with clear contracts. Allowing "no data" in business logic does not have to be represented by null.

| Case | List.copyOf | Set.copyOf | Map.copyOf |
| --- | --- | --- | --- |
| Input object itself is null | `NullPointerException` | `NullPointerException` | `NullPointerException` |
| Valid empty input | Accepted | Accepted | Accepted |
| Contains null element | `NullPointerException` | `NullPointerException` | See key and value separately |
| Contains null key | Not applicable | Not applicable | `NullPointerException` |
| Contains null value | Not applicable | Not applicable | `NullPointerException` |

The factory's null rule is a technical precondition. Business rules may be stricter: strings must not be blank, codes must exist, a list must not exceed a limit, or a user must not have duplicate permissions. `copyOf` does not replace those checks.

For example, `Set.copyOf` can deduplicate successfully, but that does not mean duplicate data is always acceptable in business logic. If the requirement is to report an error when duplicate permissions are entered, converting to a `Set` without checking can hide input errors. If the requirement is a unique permission set, deduplication may be right. State the goal first before applying the mechanism.

Conversely, do not silently turn every null input into an empty collection if the two states carry different meanings. "No items" and "the caller forgot to supply data" may require different handling. Put this rule on the receiving API so callers understand their responsibility.

When a factory throws an exception in the examples, execution exits that call; no "partially copied" result is returned to the receiving variable. The programs above only catch the expected exception types to observe each case, not to turn null into valid data.

## 14. Using copyOf at object boundaries and return values

A readable flow is often: accept data; normalize or validate as required; build intermediate data if needed; freeze the collection; publish the result. Placing the freeze step where ownership changes helps readers know which side still has permission to modify the container.

In constructors, `Catalog` in section 10 is a small example. The object does not want its configuration to change just because the caller continues to modify the `List` they passed in. Snapshotting the input right at acceptance creates an easily verifiable boundary. The `final` field then expresses that the field reference itself cannot be reassigned.

In return methods, there are two situations:

- The object already holds a frozen collection with an appropriate level of element protection. It can return the existing result, like `Catalog.names()`.
- The object manages mutable data, while the caller needs a separate result for the current request. Snapshot the data at the return boundary, with an appropriate element policy.

Do not use a method name like `getItems` to assume that both situations behave the same way. Contract documentation should state clearly whether the recipient sees future changes made by the owner.

With nested maps, check both the input and the output access paths. Snapshotting the outer `Map` while returning mutable `List` values still gives the recipient permission to modify those `List`s. If the goal is a two-layer read-only configuration, snapshot each `List` and then snapshot the `Map`; if `List` elements are mutable objects, continue evaluating that layer.

A structural snapshot does not automatically provide a synchronization protocol with threads writing to the source. Calling `copyOf` alone does not establish a shared lock with other mutation paths in the application. If multiple threads can modify the source while reading data, you need a coordination rule suited to the source type and consistency requirements. Do not infer from "the result is unmodifiable" that "reading the input is always an atomic snapshot."

Similarly, do not treat calling the factory multiple times as a way to manage business versioning. If each configuration snapshot needs a version number, effective timestamp, or relationship to other data, model those details separately. `copyOf` is just one step for building the collection data within that model.

## 15. Diagnosing common misconceptions

| Observation or assumption | Accurate interpretation and fix |
| --- | --- |
| Calling `set` on a `List` result throws an exception | The result blocks replacing elements, not just changing size; create a mutable copy if modification is required |
| Source changes and the read-only view still changes with it | A view can read through to the source; choose a snapshot if you need to freeze the data |
| Mutating a builder changes the text inside the copied `List` | Elements are shared; choose immutable elements or transform/copy elements |
| A three-element `List` becomes a two-element `Set` | Duplicate values were merged; use a `List` if occurrence counts must be preserved |
| Expecting `Set.copyOf` to throw on duplicate elements | That rule differs from `Set.of`; check uniqueness separately if business logic requires an error |
| Order of the resulting `Set` or `Map` differs from the source | The factory does not promise to preserve that order; choose a contract with explicit ordering |
| Casting the result to the source's implementation class | The factory only guarantees the published interface and behavior; remove class-name dependencies |
| Using `==` to prove a copy was made | Identity does not prove data independence; test behavior against source mutations |
| Outer `Map` is read-only but value `List` can still be modified | Protect the `List` layer if you do not want to grant modification rights to it |
| Marking a field `final` yet the data still changes | `final` prevents reassigning the field; you must manage the referenced object |

When an error occurs, identify the exact object receiving the mutating operation. `map.put(key, list)` acts on the `Map`; `map.get(key).add(value)` acts on the `List`; `map.get(key).get(0).setName(...)` acts on an even deeper element object. This layered breakdown helps locate the right place to change the design, instead of adding an outer wrapper and hoping all internal state is protected too.

Do not deduce a contract from a single print output. An accidental iteration order, an identity comparison, or a class name seen in a debugger may be an implementation detail. Verification cases should focus on published requirements: elements/mappings, mutability, relationship to the source, and degree of object sharing.

## 16. Practice with observable criteria

### Exercise 1: Freezing search results

A method builds a `List` of product codes, where the same code may appear twice. The recipient must see the exact order of search results and must not be allowed to add, remove, or replace elements.

Choose the factory, state the null policy, and write a check by modifying the source `List` after creating the result. Passing criteria: order and both occurrences are preserved; changing the source `List` does not change the result; mutating operations on the result are blocked. The right choice is `List.copyOf`, because positions and order are part of the requirement.

### Exercise 2: Unique permission set

The input is a `List` of `String` permissions, containing duplicate permissions because multiple groups grant the same permission. The result only needs to answer whether a permission is present; there is no ordering requirement.

Decide whether duplicates should raise an error or be merged. If business logic allows merging, `Set.copyOf` accurately represents the unique permission set. Verify contents using set equality, not by writing a test that expects a specific ordered print string.

If the requirement changes to "duplicate permissions must raise an error," calling `Set.copyOf` alone is not enough. You must add input validation; do not switch to `Set.of(list)` thinking the `List` will automatically be flattened into permissions.

### Exercise 3: Configuration table with nested values

The source is `Map<String, List<String>>`, where keys are feature names and values are environment names. The recipient must not replace mappings or modify the environment `List`s. All names are non-null `String`s.

Describe the two-layer procedure and verify two different mutation paths: replacing the `List` bound in the source `Map`; adding an element to the old `List`. Passing criteria: neither source mutation path alters the published data. The procedure in section 10 provides one way to handle this exact data shape.

### Exercise 4: Result requiring key order

A report must iterate over entries in a defined insertion order. Someone proposes converting a `LinkedHashMap` with `Map.copyOf` and assuming the order is preserved because the source is ordered.

Point out the missing guarantee and choose a representation that satisfies the ordering requirement. Passing criteria: clearly state which structure's contract holds the ordering and whether the outside world still retains a path to modify that structure. Checking a single print output is not enough to prove the design.

### Exercise 5: Changing the element type in Catalog

Replace the list of `String` names with a list of objects that have a method to rename them. The constructor still uses `List.copyOf`.

Predict what is protected and what remains shared. Passing criteria: distinguish replacing a position in the `List` from mutating the name on the object at that position; propose immutable objects or an appropriate copying approach if name stability is required.

## 17. Self-check before applying

1. **Do the three factories always create a new collection object?** No. The data contract does not depend on whether a new allocation occurs or an appropriate existing result is reused. Do not test correctness by identity.
2. **Does `List.copyOf` remove duplicate elements?** No. It preserves elements in the source's iteration order. `Set.copyOf` is what represents distinct values.
3. **Does `Set.copyOf` pick the first representative among equal elements?** There is no such guarantee. If you need a record-selection rule, apply that rule explicitly before creating the resulting set.
4. **Does `Map.copyOf` preserve the order of `LinkedHashMap`?** There is no corresponding iteration-order guarantee. Put ordering requirements into the contract and choose the appropriate tool.
5. **What if the source contains null because the source itself allows null?** Source rules do not override factory rules. Handle null according to the intake contract before snapshotting if needed.
6. **Does `Map.copyOf` make value `List`s read-only?** No. It locks in the mappings; inner `List`s must be handled separately.
7. **How do a read-only wrapper and a snapshot differ?** A wrapper can continue reading through to the source; a `copyOf` snapshot does not follow additions, removals, or replacements of elements or mappings in the source after copying.
8. **When can a frozen collection be returned directly from a field?** When mutability and element sharing satisfy the object's contract. With immutable `String`s in `Catalog`, this condition is clearer than with mutable elements.
9. **Why did stdout for `Set` and `Map` in this lesson go through a sorted structure?** For stable presentation when verifying data; do not attribute to a factory result an ordering that the API does not promise.
10. **What check proves source independence better than comparing with `==`?** Create the result, modify the source in permitted ways, and verify that the elements or mappings in the result remain as required. Also check element object sharing separately when immutability matters.
