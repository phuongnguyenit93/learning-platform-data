# Distinguishing Unmodifiable Collections from Deep Immutability in Java

## 1. The problem: being unable to add elements does not mean all data is immutable

When collecting results with Java Stream, we often encounter code patterns like:

~~~java
List<Person> people = source.stream().toList();
List<Person> copied = List.copyOf(people);
List<Person> wrapped = Collections.unmodifiableList(people);
~~~

The lines above are **illustrative** assuming `source`, `Person`, and the imports already exist. They raise three **distinct** questions:

1. Can `add()`, `remove()`, or `set()` be called to change the **list structure through the current reference**?
2. Does the resulting list change **indirectly** when another source collection is modified?
3. Can the **objects inside** the list be modified? If so, can the fields and deeply nested structures inside them continue to change?

An **unmodifiable collection** usually only blocks structural/content modifications to the collection **through that interface itself**. It **does not automatically make all element objects immutable**.

**Deep immutability** requires something stronger: every observable state across the entire object graph accessible through the public API must also be protected from modification. This does not happen automatically just by using `Stream.toList()`, `List.copyOf()`, `Collections.unmodifiableList()`, `record`, or `final`.

In this article, we distinguish three concepts: **unmodifiable view**, **structural snapshot**, and **deeply immutable object graph**, and then apply them to collecting Stream results and designing immutable DTOs in Java 17.

## 2. Three layers of immutability to separate

### 2.1. Unmodifiable through the current reference

Example:

~~~java
List<String> names = List.of("An", "Bình");
names.add("Chi"); // Throws UnsupportedOperationException.
~~~

`List.of(...)` creates an unmodifiable list: operations that modify the list through `names` such as `add`, `remove`, or `set` are not supported. However, the word “unmodifiable” is **not enough to conclude that all elements inside are immutable**. Here `String` itself is immutable, so the example looks safe at both layers, but the reason comes from **both the list type and the element type**.

### 2.2. A structural snapshot differs from a live view

A **view** maintains a link to the source collection, so modifications made through the **source** reference can be reflected in the view. A **structural snapshot** stores the set of element references at creation time; subsequent additions/removals on the source do not automatically change the snapshot's structure.

~~~java
List<String> source = new ArrayList<>(List.of("a"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("b");

System.out.println(view);     // [a, b]
System.out.println(snapshot); // [a]
~~~

This is an illustrative snippet inside a method, requiring imports for `List`, `ArrayList`, and `Collections`. Both `view` and `snapshot` forbid modification **through themselves**, but **`view` can observe structural changes in the source**. `snapshot` retains the structure taken at the time of copying.

### 2.3. A structural snapshot does not mean a deep copy

~~~java
StringBuilder text = new StringBuilder("draft");
List<StringBuilder> source = new ArrayList<>();
source.add(text);

List<StringBuilder> snapshot = List.copyOf(source);
text.append("-changed");

System.out.println(snapshot.get(0)); // draft-changed
~~~

`List.copyOf` creates a snapshot of **the elements in the list**, but does not deep-copy each `StringBuilder`. `snapshot.get(0)` still points to **the same mutable object** as `text`. Therefore, if someone else modifies `text`, the data observed through the snapshot still changes.

**Conclusion:** Blocking collection modification and blocking modification of **element state** are **two separate things**.

## 3. Common collection APIs have different contracts

| API | Mutability contract | Deep-copies elements? | Important notes |
|---|---|---|---|
| `Stream.toList()` (Java 16+) | Returns an **unmodifiable** list | No | Result does not allow `add/remove/set`; no specific implementation promised |
| `Collectors.toList()` | **No guarantee** of list type, mutability, thread safety, or serializability | No | Do not rely on the current implementation returning `ArrayList` |
| `Collectors.toUnmodifiableList()` (Java 10+) | **Unmodifiable** list | No | Rejects `null` elements |
| `Collectors.toCollection(ArrayList::new)` | Result is an `ArrayList` created by the supplier, structurally mutable | No | Explicitly chooses the collection type to create |
| `List.of(...)` (Java 9+) | **Unmodifiable** list | No | Rejects `null`; elements may be mutable |
| `List.copyOf(collection)` (Java 10+) | **Unmodifiable** list, structural snapshot from the input collection | No | Rejects `null`; may reuse a suitable instance |
| `Collections.unmodifiableList(list)` | **Unmodifiable view** over the wrapped list | No | Changing the original list may cause the view to change |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Unmodifiable view over a separate structural copy | No | Keeps the internal copy source unexposed, but elements still share references |

All these options belong to the Java Collections/Stream ecosystem, but serve different needs. **The right question is not “which method is best?” but “which constraints are needed?”**

### 3.1. `Stream.toList()`: structurally unmodifiable

~~~java
List<String> result = Stream.of("a", "b")
        .map(String::toUpperCase)
        .toList();
~~~

`result` contains `[A, B]` and `result.add("C")` throws `UnsupportedOperationException`. Java SE 17 does not promise a specific implementation class or serializability of the returned list object. Therefore, avoid casting to `ArrayList` or relying on the list's class name.

`Stream.toList()` also does not automatically deep-copy the objects produced by the pipeline. If the mapper produces the same mutable reference multiple times, the result may contain multiple elements pointing to that object.

### 3.2. `Collectors.toList()`: do not infer mutability

~~~java
List<String> result = Stream.of("a", "b")
        .collect(Collectors.toList());
~~~

Although some popular JDKs currently return a mutable result, the API documentation for `Collectors.toList()` **does not guarantee** mutability/unmodifiability or a specific collection type. Therefore, writing code whose correctness **depends** on `result.add(...)` succeeding is not based on a public guarantee.

**If a mutable list is truly needed:** explicitly choose `Collectors.toCollection(ArrayList::new)` or `new ArrayList<>(stream.toList())`.

**If an unmodifiable list is truly needed:** choose `Stream.toList()` or `Collectors.toUnmodifiableList()`, after considering the `null` policy.

### 3.3. `Collectors.toUnmodifiableList()` and `List.copyOf()`

Both APIs produce an unmodifiable list; they do not make element objects immutable. `Collectors.toUnmodifiableList()` requires non-null elements, and `List.copyOf` also rejects null elements. `List.copyOf` may return the same object when the input is already a suitable unmodifiable list; **do not rely on it always allocating a new list**.

### 3.4. `Collections.unmodifiableList(...)` is a view, not a copy

~~~java
List<String> backing = new ArrayList<>(List.of("x"));
List<String> view = Collections.unmodifiableList(backing);

backing.set(0, "y");
System.out.println(view); // [y]
~~~

Wrapping with `Collections.unmodifiableList` **does not make `backing` immutable**. Anyone who still holds the `backing` reference can modify the structure or element values of the source list; the view sees those changes.

Only use a view if you **accept data changing along with the backing collection** or have absolute control over references that can modify the backing collection. For public API snapshots, consider `List.copyOf` or an appropriate defensive copy.

## 4. Runnable program: view, snapshot, and mutable elements

Save the file **`UnmodifiableVsDeepDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableVsDeepDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        List<StringBuilder> source = new ArrayList<>();
        source.add(first);

        List<StringBuilder> view =
                Collections.unmodifiableList(source);
        List<StringBuilder> snapshot =
                List.copyOf(source);
        List<StringBuilder> streamList =
                source.stream().toList();

        source.add(new StringBuilder("B"));
        first.append("!");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("streamList=" + streamList);

        try {
            snapshot.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.add=blocked");
        }

        try {
            streamList.set(0, new StringBuilder("X"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("streamList.set=blocked");
        }

        snapshot.get(0).append("?");
        System.out.println("sourceAfterElementEdit=" + source);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac UnmodifiableVsDeepDemo.java
java UnmodifiableVsDeepDemo
~~~

Stdout:

~~~text
source=[A!, B]
view=[A!, B]
snapshot=[A!]
streamList=[A!]
snapshot.add=blocked
streamList.set=blocked
sourceAfterElementEdit=[A!?, B]
~~~

**What just happened?**

1. `view` was created from `source` without copying. After `source.add(...)`, `view` has two elements.
2. `snapshot = List.copyOf(source)` and `streamList = source.stream().toList()` were created when the source had only **one** element. After adding `B` to `source`, the sizes of these two lists **do not increase automatically**.
3. `first` is still the same `StringBuilder` referenced by `source`, `view`, `snapshot`, and `streamList`. Therefore, `first.append("!")` causes the first element's value to be observed as `A!` in all four lists.
4. `snapshot.add(...)` and `streamList.set(...)` are unsupported and throw `UnsupportedOperationException`.
5. However, `snapshot.get(0).append("?")` is still allowed because it **modifies the `StringBuilder` object**, not the structure of `snapshot`. The source changes to `[A!?, B]`.

This example proves that **being unable to modify a list through an API does not mean all data inside is “frozen”**. This is a very intuitive check during code review.

## 5. Record and final do not automatically create deep immutability

Java records allow concise data declarations and have `private final` member fields. However, **`final` only prevents changing the field's reference**, not modifying the object that the reference points to.

~~~java
record Team(String name, List<String> members) {}

List<String> members = new ArrayList<>(List.of("An"));
Team team = new Team("A", members);

members.add("Bình");
System.out.println(team.members()); // [An, Bình]
~~~

This is an illustrative snippet inside a method. `Team` is a record, but has no defensive copy in its constructor. The record object still exposes a reference to the mutable list passed in; the caller holding `members` can modify it.

Similarly:

~~~java
record Document(String title, StringBuilder content) {}
~~~

The record above is **not deeply immutable** because `StringBuilder` can be modified. Even though the field is `final`, a user can get `document.content()` and call `append`.

**Rule:** To build an immutable data model, you must examine **all reference paths** to mutable state, not just the `final` keyword or the outer object type.

## 6. Defensive copying: toward immutable data snapshots

A common design approach is **defensive copying at the boundary** between mutable data and public data, while using immutable element types.

For example, with an order having an id and `String` tags:

~~~java
record OrderSnapshot(String id, List<String> tags) {
    public OrderSnapshot {
        tags = List.copyOf(tags);
    }
}
~~~

This is an **illustrative record**. In the compact constructor, reassigning the `tags` parameter with `List.copyOf(tags)` initializes the record field with an unmodifiable snapshot list. Because `String` is immutable, callers cannot change the content of a tag after creation.

In this model:

- **Input copy**: if the outside modifies the original list, `OrderSnapshot.tags()` does not change structure.
- **No mutable list exposed**: `tags()` returns an unmodifiable list, so callers cannot add/remove/modify positions through the accessor.
- **Elements are `String`**: they are immutable, so no deeper mutable reference is exposed through tags.
- **`id` is also `String`**: there is no mutable state behind it.

This is an example of **deep immutability for the data graph exposed by the record**. It does not mean `List.copyOf` is a general-purpose deep-copy function: safety comes from **combining structural copying and immutable leaf types**.

### 6.1. Complete Java 17 program: copying when collecting a Stream

Save as **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableSnapshotDemo {
    record SourceOrder(String id, List<String> tags) {}

    record OrderSnapshot(String id, List<String> tags) {
        public OrderSnapshot {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> originalTags =
                new ArrayList<>(List.of("java"));
        List<SourceOrder> source = new ArrayList<>();
        source.add(new SourceOrder("A", originalTags));

        List<OrderSnapshot> snapshots = source.stream()
                .map(order -> new OrderSnapshot(
                        order.id(), order.tags()))
                .toList();

        originalTags.add("changed");
        source.add(new SourceOrder("B", List.of("new")));

        System.out.println("sourceSize=" + source.size());
        System.out.println("sourceTags=" + originalTags);
        System.out.println("snapshotSize=" + snapshots.size());
        System.out.println("snapshots=" + snapshots);

        try {
            snapshots.get(0).tags().add("bad");
        } catch (UnsupportedOperationException ex) {
            System.out.println("tags.add=blocked");
        }

        try {
            snapshots.add(new OrderSnapshot("C", List.of()));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshots.add=blocked");
        }
    }
}
~~~

Run:

~~~bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

Stdout:

~~~text
sourceSize=2
sourceTags=[java, changed]
snapshotSize=1
snapshots=[OrderSnapshot[id=A, tags=[java]]]
tags.add=blocked
snapshots.add=blocked
~~~

**Analysis:**

1. `SourceOrder` holds the mutable `originalTags` list; later, external code can add `"changed"`.
2. `source.stream().map(...)` creates a **new record** `OrderSnapshot` for each source item. This `map` step itself is where **mutable data is converted into a safe representation**.
3. The compact constructor of `OrderSnapshot` uses `List.copyOf` to create an unmodifiable tag list, independent of subsequent additions/removals on the source.
4. `Stream.toList()` guarantees the **outer snapshot list** cannot be modified. Meanwhile, the `OrderSnapshot` constructor protects **the list inside each record**.
5. Because `id` and the tags are immutable `String`s, within the scope of this object graph we have an end-to-end immutable structure.
6. Both attempts to modify the outer list and the tag list are blocked; the before/after results are unaffected by changes to `originalTags`.

This is a design that is often valuable when exporting DTOs from a processing pipeline, exchanging data across public APIs, or returning read-only configuration. **Simply calling `toList()` at the end is not enough:** if you omit the `map`/defensive copy step and let mutable objects pass straight into the result, deep mutation risks remain.

## 7. Wanting to modify the result after collecting: choose an explicit mutable API

If the actual requirement is to **add/remove/sort** the list after obtaining the result, do not assume `toList()` or `Collectors.toList()` is suitable.

Example:

~~~java
List<String> sorted = words.stream()
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));

sorted.add("extra");
sorted.sort(String::compareTo);
~~~

This illustrative snippet requires `words` and imports `List`, `ArrayList`, and `Collectors`. `Collectors.toCollection(ArrayList::new)` creates an `ArrayList`, so its structure can be modified. On the other hand, even if the outer list is mutable, **the elements are still determined by the mapper**: if they are mutable objects, you still must watch out for aliasing.

An easy-to-understand alternative:

~~~java
List<String> mutable = new ArrayList<>(
        words.stream().map(String::trim).toList());
~~~

This new `ArrayList` structurally copies the stream result to produce a mutable list. It is not a deep copy.

If the goal is an **unmodifiable** list, usually choose `Stream.toList()` (Java 16+) or `Collectors.toUnmodifiableList()` and avoid converting it to mutable just to wrap it again.

### 7.1. Complete program: collectors and mutability

Save as **`CollectorChoiceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorChoiceDemo {
    public static void main(String[] args) {
        ArrayList<String> editable = Stream.of("a", "b")
                .collect(Collectors.toCollection(ArrayList::new));

        List<String> fixed = Stream.of("a", "b")
                .toList();

        List<String> unmodifiable = Stream.of("a", "b")
                .collect(Collectors.toUnmodifiableList());

        editable.add("c");

        System.out.println("editable=" + editable);
        System.out.println("fixed=" + fixed);
        System.out.println("unmodifiable=" + unmodifiable);

        try {
            fixed.add("x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("fixed.add=blocked");
        }

        try {
            unmodifiable.remove(0);
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable.remove=blocked");
        }
    }
}
~~~

Compile and run:

~~~bash
javac CollectorChoiceDemo.java
java CollectorChoiceDemo
~~~

Stdout:

~~~text
editable=[a, b, c]
fixed=[a, b]
unmodifiable=[a, b]
fixed.add=blocked
unmodifiable.remove=blocked
~~~

`editable` is explicitly created with the `ArrayList::new` supplier, so it has a mutable contract like `ArrayList`. `fixed` and `unmodifiable` have unmodifiable contracts, without assuming they use the same internal class type or automatically deep-copy objects.

**Subtle point:** `Collectors.toList()` does not appear in the mutability test in this example because the API **does not guarantee a mutable result**. To learn the contract properly, avoid writing tests that “pass because the current JDK version happens to return a specific list type”.

## 8. Deep immutability is a property of the entire object graph

Consider a data shape like:

~~~text
List<Order>
   ├── Order{id, List<Line>}
   │                └── Line{sku, int[] quantities}
   └── Order{id, List<Line>}
                    └── Line{sku, int[] quantities}
~~~

Even if the outer `List<Order>` is unmodifiable, the following points may still be mutable:

- `Order` has setters or fields that can be updated.
- `Order.lines` is an `ArrayList` and can be modified.
- `Line` has setters; or contains an `int[]` array whose elements a caller can modify.
- An external reference still points to the same `Order`, `Line`, or array.

To achieve deep immutability, you must identify **which parts of the object graph are publicly observable** and protect every mutable component at API entry/exit points.

Examples of how to handle this:

1. Use **immutable types for leaf values** such as `String`, primitives, enums, or immutable value objects.
2. For `List`/`Set`/`Map`, create a structural snapshot and ensure **each element or value inside is also immutable**.
3. For `byte[]`, `int[]`, and object arrays, perform **defensive cloning/copying**, including when returning through accessors.
4. For classes with setters or mutable state, create a separate **value snapshot** instead of sharing references.
5. For deep graphs with cycles or complex aliasing, design an explicit copy policy; Java has no general-purpose `deepCopy()` operation that is safe for every kind of object.

**No collection wrapper automatically traverses the entire graph and turns every object into an immutable one.** Deep immutability is a design property of the data model and the reachability of mutable references.

### 8.1. Arrays in records: must copy in both constructor and accessor

~~~java
record Bytes(byte[] data) {
    public Bytes {
        data = data.clone();        // Copy when receiving from caller.
    }

    @Override
    public byte[] data() {
        return data.clone();        // Copy when returning to caller.
    }
}
~~~

This is an **illustrative record snippet**, compilable when placed in a Java file with the proper context. Even though a record contains a `final` field, a `byte[]` array is still mutable: if the getter returns the original array directly, callers can modify the record's elements from the outside.

Example:

~~~java
byte[] original = {1, 2};
Bytes safe = new Bytes(original);
original[0] = 9;
byte[] exposed = safe.data();
exposed[1] = 8;
System.out.println(java.util.Arrays.toString(safe.data())); // [1, 2]
~~~

Here, cloning in the constructor prevents modifications coming from `original`; cloning in the accessor prevents modifications coming from `exposed`. **Both directions** are necessary because a mutable array reference can be retained before or after the record is created.

**Note:** Because the accessor returns a new array each time, the default `equals()`/`hashCode()` methods of a record with an array field do not automatically compare array contents as desired. If designing an array-based value object, you also need to consider equality/hashCode semantics alongside deep immutability.

### 8.2. A nested collection can still be modified

~~~java
List<List<String>> outer = List.of(
        new ArrayList<>(List.of("a"))
);

outer.get(0).add("b"); // Succeeds: the inner list is still mutable.
~~~

`outer` does not allow structural modification; the **inner list** is an `ArrayList` and `"b"` can be added to it. To have unmodifiable inner lists that are structurally independent of the source:

~~~java
List<List<String>> deepStructure = outer.stream()
        .map(List::copyOf)
        .toList();
~~~

Because the leaf is an immutable `String`, this creates a graph of unmodifiable lists at two levels. If the inner list elements are `StringBuilder` or another mutable class, **you still must create a separate snapshot for each element**.

### 8.3. A Map containing Lists must also protect its values

~~~java
Map<String, List<String>> snapshot = sourceMap.entrySet()
        .stream()
        .collect(Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())
        ));
~~~

This is an **illustrative snippet**, requiring imports for `Map` and `Collectors`; `sourceMap` must have a compatible type, non-null keys/values, and no duplicate keys from a normal entry set. `toUnmodifiableMap` makes the outer map unmodifiable; `List.copyOf` makes the value lists unmodifiable structural snapshots; `String` in both keys and list elements is immutable.

If you omit `List.copyOf` and only use `toUnmodifiableMap`, a mutable list value can still be modified. This is a general example showing that **protecting the outer container does not automatically protect the inner containers**.

## 9. Nulls, ordering, and guarantees you should not infer

### 9.1. Null policies are not the same across all factories

- `List.of(...)` and `List.copyOf(...)` reject `null` elements.
- `Collectors.toUnmodifiableList()` also rejects `null`.
- `Collections.unmodifiableList(backing)` wraps a backing list; if the backing list contains `null`, the view can display null.
- `Stream.toList()` in Java 17 can collect `null` elements; **do not assume** it applies the same null policy as `Collectors.toUnmodifiableList()`.
- `Collectors.toList()` does not promise a specific list type; if business logic requires a clear null policy, validate and check the source or choose an API with an appropriate contract.

For example, `Stream.of("a", null).toList()` on Java 17 produces a result with a null element; whereas `Stream.of("a", null).collect(Collectors.toUnmodifiableList())` throws `NullPointerException`. However, in applications, for safer data it is usually better to define the null policy right at the system entry boundary.

### 9.2. Unmodifiable does not mean thread-safe

Even a `Collections.unmodifiableList(backing)` can reflect changes made by another thread on the backing list. The wrapper does not automatically synchronize modifications/iteration. A snapshot list with mutable elements can still observe element mutations from another thread.

With a truly immutable model, sharing data across threads is usually easier to reason about, but **safe publication of references** and synchronization mechanisms during initialization/sharing must still follow the Java Memory Model in the overall design.

### 9.3. Do not rely on the identity of an unmodifiable list

Some factories may share or reuse list objects, and the returned lists may be *value-based*. Do not use `==`, `System.identityHashCode`, locking on the list object, or class names to define business logic. When comparing list contents, use `equals()` according to `List` semantics.

### 9.4. A structural snapshot is not a transactional snapshot

If the source is modified concurrently while you are collecting or copying, `Stream.toList()` or `List.copyOf()` does not automatically turn that operation into a consistent snapshot transaction. Concurrent modification without proper synchronization can cause unpredictable results or errors. You need to control access to the source if point-in-time consistency is required.

## 10. Common design choices when collecting results

| Practical need | Approach | Why |
|---|---|---|
| Return a **structurally unmodifiable** list | `stream.toList()` | Concise API, clear unmodifiable contract (Java 16+) |
| Return an unmodifiable list and **forbid null** | `collect(toUnmodifiableList())` | Explicit null-rejecting contract |
| Need a mutable list and know the exact collection type | `collect(toCollection(ArrayList::new))` | Specifies concrete collection |
| Want a structural snapshot from an existing collection | `List.copyOf(source)` | Independent of subsequent additions/removals on the mutable source |
| Want a read-only view **reflecting backing changes** | `Collections.unmodifiableList(backing)` | Intentionally keeps connection to backing |
| Want a list containing immutable DTOs | `map(this::toSnapshot).toList()` | Mapper handles defensive copying of each object |
| Want to protect an internal array | Copy in constructor **and** accessor | Prevents exposing mutable reference |
| Want to protect `Map<K,List<V>>` | Copy map and each value list, ensure immutable K/V | Protects every layer of the object graph |
| Want a snapshot of large data with concurrent writers | Dedicated synchronization/snapshot mechanism before copying | Unmodifiable copy does not provide transactional snapshot on its own |

Choose based on **public API constraints**, not just syntax brevity. A deeply immutable DTO may require more lines of code at data boundaries, but often reduces state-checking overhead at usage sites.

## 11. Common mistakes and how to fix them

### Mistake 1: “Called `toList()`, so everything is immutable”

~~~java
List<StringBuilder> list = Stream.of(
        new StringBuilder("a")
).toList();

list.get(0).append("b"); // Succeeds.
~~~

`toList()` prevents modifying the list structure, **not** making `StringBuilder` immutable. If you want immutable strings, convert to `String` with `map(StringBuilder::toString)` before collecting.

### Mistake 2: “`Collections.unmodifiableList` creates a snapshot”

~~~java
List<String> backing = new ArrayList<>(List.of("x"));
List<String> view = Collections.unmodifiableList(backing);
backing.add("y"); // view reflects "y".
~~~

If you want a snapshot structurally independent of the source, use `List.copyOf(backing)` or make a separate copy and then wrap it. Do not keep exposed references to the internal backing list if you want to prevent modification.

### Mistake 3: “`Collectors.toList()` is definitely an ArrayList”

The Javadoc does not guarantee mutability or a concrete type. If you truly need an `ArrayList`, use `Collectors.toCollection(ArrayList::new)`. Do not cast blindly or rely on a JDK version.

### Mistake 4: “Records are always immutable”

~~~java
record Config(List<String> flags) {}
~~~

If `flags` is a mutable list, the default record only holds the reference. Copy defensively in the constructor:

~~~java
record Config(List<String> flags) {
    public Config {
        flags = List.copyOf(flags);
    }
}
~~~

Because the leaf `String` is immutable here and the list cannot be modified, the public object is safer against external modification.

### Mistake 5: Copying only in the constructor while returning the raw array from the accessor

Even if the constructor clones the array, a getter returning the array directly still exposes internal state. Copy in both directions, or use another immutable representation.

### Mistake 6: Forgetting to copy nested layers

`List.copyOf(listOfMutableLists)` only locks the outer list. Callers can still call `result.get(0).add(...)` if the inner list is mutable. You must make each inner list immutable and copy mutable elements if any.

### Mistake 7: Using an unmodifiable view as a thread-safety mechanism

A view wrapping a mutable list does not automatically solve race conditions or synchronization. If multiple threads can modify the backing list, design thread safety separately.

### Mistake 8: Thinking `List.copyOf` always allocates a new object

The API may reuse a suitable unmodifiable list. Do not rely on `copy != original` or identity to verify a deep copy. Check **observable behavior** and element constraints instead.

### Mistake 9: Ignoring the possibility of null elements

`List.copyOf` and `Collectors.toUnmodifiableList` reject null. When migrating a pipeline from `toList` to `toUnmodifiableList`, check the data and null tests first.

### Mistake 10: Copying via serialization or arbitrary cloning

`clone()` does not deep-copy by default. Serialization is also not a safe/efficient default approach for creating immutable graphs, having security and versioning issues depending on the data. Explicitly define how mutable data is converted into immutable data.

## 12. Review checklist for APIs returning collections

1. **Is the outer collection mutable?** Read the contract rather than inferring from the current JDK's class.
2. **Is the result a view or a structural snapshot?** If the source adds/removes items, does the output change?
3. **Do elements have mutable state?** Does the element class/record have setters, lists, maps, arrays, or any mutable objects?
4. **Is there inbound aliasing?** Can the caller retain references to the original elements?
5. **Is there outbound aliasing?** Do accessors/getters return mutable objects directly?
6. **Have all necessary layers been copied?** Especially nested collections and arrays.
7. **Are leaf values immutable?** `String`, immutable primitives/boxed types, and properly designed value objects.
8. **Is the null policy appropriate?** `List.copyOf`/`toUnmodifiableList` do not accept null.
9. **Is a mutable result needed?** If so, explicitly choose `toCollection(ArrayList::new)`.
10. **Is stable element ordering needed?** Check the encounter order of the source/pipeline; do not conflate it with immutability.
11. **Are there concurrency/consistent snapshot requirements?** If so, control the source data and copy timing.
12. **Have both source changes and element changes been tested?** Try modifying the backing source, calling `add` on the result, and calling an element's setter separately.

A good test suite does not just verify that `result.add(...)` throws `UnsupportedOperationException`. It also attempts to **modify the source after copying** and **modify objects inside the collection**. That is the proper way to distinguish a structural snapshot from deep immutability.

## 13. Self-check questions

**Question 1.** Does `Stream.of("a", "b").toList()` allow `add("c")`? Is it guaranteed to be an `ArrayList`?

**Question 2.** What is the key difference between `Collections.unmodifiableList(backing)` and `List.copyOf(backing)`?

**Question 3.** Is `List.copyOf(List.of(new StringBuilder("a")))` deeply immutable? Why?

**Question 4.** Should you rely on `Collectors.toList()` always returning a mutable list?

**Question 5.** How can you collect a Stream into a mutable `ArrayList` according to the API contract?

**Question 6.** Is a record with a `List<String>` field that receives a mutable list directly without copying deeply immutable?

**Question 7.** Why is it necessary to clone a `byte[]` in both the constructor and the accessor to protect state?

**Question 8.** Do `List.of` and `List.copyOf` allow null elements?

**Question 9.** After `List.copyOf(source)`, a new element is added to the source. Does the snapshot automatically gain that element? What if an old mutable element is modified?

**Question 10.** To create an immutable `List<OrderSnapshot>` from `Stream<MutableOrder>`, is using `stream.toList()` alone sufficient?

**Answers:**

1. It does not allow modification; it is not guaranteed to be implemented as `ArrayList`.
2. `unmodifiableList` is a view reflecting the backing list, whereas `copyOf` creates a structural snapshot by contract.
3. No; `StringBuilder` is still mutable and its reference is shared.
4. No, the API does not promise mutability.
5. `collect(Collectors.toCollection(ArrayList::new))` or copy into `new ArrayList<>(...)`.
6. No, if the mutable list reference is retained or exposed through the accessor; appropriate defensive copying is needed.
7. To prevent modifications from the input reference and prevent callers from modifying the array through the getter.
8. No; both reject null.
9. No structural addition occurs; however, old element objects can still change if they are mutable.
10. No; you must convert each `MutableOrder` to an immutable DTO/snapshot and copy all necessary nested state.

## 14. Official documentation

- [Java SE 17 — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): unmodifiable list contract and implementation notes.
- [Java SE 17 — Collectors.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): no guarantee on list type or mutability.
- [Java SE 17 — Collectors.toUnmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collects into an unmodifiable list and rejects null.
- [Java SE 17 — List.of()/List.copyOf()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): immutable collection factories, structural snapshots, and null rules.
- [Java SE 17 — Collections.unmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable **view** of the source list.
- [Java SE 17 — Collectors.toCollection()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): choosing a concrete collection via a factory.

**Takeaway:** **Unmodifiable** means the collection cannot be modified **through that interface**. **Structural snapshot** means additions/removals on the source do not automatically alter the obtained list. **Deep immutability** means all observable state across the object graph has been designed so it cannot be modified from public references. `Stream.toList()`, `List.copyOf()`, and `Collections.unmodifiableList()` **do not automatically deep-copy elements**. To achieve a deeply immutable result, you must combine **unmodifiable collection**, **defensive copying**, and **immutable element types** at every relevant data layer.