# List.copyOf, Set.copyOf, Map.copyOf and Shallow Copy Limitations in Java 17

**Topic:** Java 17 → Collections and Streams  
**Focus:** Creating unmodifiable collections with `List.copyOf`, `Set.copyOf`, and `Map.copyOf`; understanding the difference between a copy and an unmodifiable view; recognizing the limitations of *shallow copy* when inner elements or values remain mutable.

Since Java 10, Java provides three `copyOf` methods to create an unmodifiable `List`, `Set`, or `Map` from an existing collection. These methods are available in Java 17 and are commonly used when returning data from a class without letting callers add, remove, or replace elements in the collection.

However, **an unmodifiable collection does not mean the data inside is completely immutable**. `copyOf` only creates a new collection at the structural level; the referenced objects remain the same objects. If an element is a `StringBuilder`, a mutable domain object, or a nested collection, users can still mutate its internal state through that reference.

## 1. The Three copyOf Methods

Java SE 17 provides:

| Method | Input parameter | Result |
| --- | --- | --- |
| `List.copyOf(Collection<? extends E>)` | A `Collection` | An unmodifiable `List<E>`, preserving iteration order and duplicate elements. |
| `Set.copyOf(Collection<? extends E>)` | A `Collection` | An unmodifiable `Set<E>`, removing duplicates according to `Set` equality rules. |
| `Map.copyOf(Map<? extends K, ? extends V>)` | A `Map` | An unmodifiable `Map<K,V>`, preserving key-value mappings. |

Example:

~~~java
import java.util.List;
import java.util.Set;
import java.util.Map;

public class CopyOfIntro {
    public static void main(String[] args) {
        List<String> names = List.copyOf(List.of("An", "Binh", "An"));
        Set<String> roles = Set.copyOf(List.of("USER", "ADMIN", "USER"));
        Map<String, Integer> scores = Map.copyOf(
            Map.of("An", 90, "Binh", 85)
        );

        System.out.println(names);
        System.out.println(roles);
        System.out.println(scores);
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 CopyOfIntro.java
java CopyOfIntro
~~~

The `names` list keeps both occurrences of `"An"` because `List` allows duplicate elements. The `roles` set keeps only one `"USER"` element because `Set` cannot contain two equal elements. The display order of `Set` and `Map` is not guaranteed by the `copyOf` methods.

## 2. Unmodifiable Property

Collections returned by `copyOf` disallow structural modifications through operations such as:

- `add`, `addAll`: adding elements.
- `remove`, `removeAll`, `removeIf`, `clear`: removing elements.
- `List.set`: replacing an element at an index.
- Mutating operations on iterators/list iterators.
- `Map.put`, `putAll`, `remove`, `replace`, `compute`, `merge`, `clear`.
- `Map.Entry.setValue` on entries obtained from an unmodifiable map.

If a mutating operation is called, the unmodifiable collection throws `UnsupportedOperationException`.

~~~java
import java.util.List;

public class UnmodifiableListDemo {
    public static void main(String[] args) {
        List<String> names = List.copyOf(List.of("An", "Binh"));

        System.out.println(names.get(0));
        System.out.println(names.size());

        names.add("Chi"); // UnsupportedOperationException
    }
}
~~~

This property is useful when:

1. A class wants to return a result list that callers can only read.
2. A configuration is constructed once and used for the rest of the program.
3. A public API wants to prevent callers from accidentally adding/removing internal mappings.
4. A processing flow needs to keep the collection structure stable after creation.

**Unmodifiable collection** only restricts operations on the collection itself. It does not forbid changing the state of individual objects referenced by the collection; this is analyzed in the shallow copy section.

## 3. Difference Between List.copyOf and Collections.unmodifiableList

This is a critical point when choosing an API. `Collections.unmodifiableList(source)` creates a **read-only view** backed by the source collection. `List.copyOf(source)` creates an unmodifiable result decoupled from subsequent structural changes to an ordinary mutable source.

### 3.1. An Unmodifiable View Can Still Change When the Source Changes

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view = Collections.unmodifiableList(source);

        source.add("B"); // Mutate the original collection.

        System.out.println(view); // [A, B]

        // view.add("C"); // UnsupportedOperationException
    }
}
~~~

`view.add("C")` is blocked, but `source.add("B")` still succeeds. Because `view` reflects the `source` collection, callers can see the new element even though they cannot modify through `view`.

### 3.2. copyOf Decouples from Subsequent Structural Changes to a Mutable Source

~~~java
import java.util.ArrayList;
import java.util.List;

public class CopyOfSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> snapshot = List.copyOf(source);
        source.add("B");

        System.out.println(source);   // [A, B]
        System.out.println(snapshot); // [A]
    }
}
~~~

`snapshot` does not reflect the `"B"` element added to `source` after creation. This is the practical difference between an **unmodifiable result decoupled from source structural changes** and an **unmodifiable view still driven by a mutable source**.

### 3.3. Comparison Table

| Criterion | `List.copyOf(source)` | `Collections.unmodifiableList(source)` |
| --- | --- | --- |
| Caller adds/removes through the result | Not allowed | Not allowed |
| Mutable source changes structure after creation | Result does not reflect those structural changes | View reflects changes from source |
| Creates a structural copy | Yes, for ordinary mutable sources | No; creates only a view |
| Allows `null` elements | No | Depends on source collection; wrapper does not filter null |
| Mutable elements inside | Still mutable | Still mutable |
| Use when | You need an unmodifiable result independent of subsequent structural changes to a mutable source | You need to wrap an existing collection into a read-only view |

### 3.4. Note on Already Unmodifiable Sources

The Javadoc permits the implementation to reuse an input collection that is already unmodifiable, rather than always creating a new object. Therefore:

- Do not rely on `copyOf` always returning a different instance from the source.
- Do not use `==`, `System.identityHashCode`, or synchronization locks based on the identity of the resulting collection.
- Rely on the contract of contents and unmodifiability, not on object identity.

If the source is an **unmodifiable view backed by a mutable collection**, and the application strictly needs an independent structural snapshot, you can create an intermediate mutable collection first and then call `copyOf`:

~~~java
List<String> stableSnapshot = List.copyOf(
    new ArrayList<>(readOnlyView)
);
~~~

The intermediate `ArrayList` receives the elements at copy time; `List.copyOf` then creates an unmodifiable result from that intermediate list. The operation is still a shallow copy: element references are preserved.

## 4. List.copyOf: Preserving Order and Duplicates

`List.copyOf` accepts a `Collection` and creates an unmodifiable list following the iteration order of the input collection.

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
            List.of("Java", "Kotlin", "Java")
        );

        List<String> copy = List.copyOf(source);

        System.out.println(copy); // [Java, Kotlin, Java]
        System.out.println(copy.get(0)); // Java
        System.out.println(copy.get(2)); // Java
    }
}
~~~

Characteristics:

- Element order is preserved according to the source's iteration order.
- Duplicate elements are preserved.
- `null` elements are not allowed.
- Elements cannot be added, removed, or replaced in the result.
- Element objects are not cloned; only references are placed into the resulting list.

`List.copyOf` is suitable when returning a list in a well-defined order, such as workflow steps, result rows, or priority order.

## 5. Set.copyOf: Removing Duplicates and No Order Guarantee

`Set.copyOf` creates an unmodifiable set from an input collection.

~~~java
import java.util.List;
import java.util.Set;

public class SetCopyDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
            "ADMIN", "USER", "USER", "AUDITOR"
        );

        Set<String> roles = Set.copyOf(source);

        System.out.println(roles);
        System.out.println(roles.contains("ADMIN")); // true
        System.out.println(roles.size()); // 3
    }
}
~~~

### 5.1. What Happens to Duplicate Elements?

If the source collection contains elements that are equal according to `equals`, the resulting `Set` contains only one representative element per value. The Javadoc specifies that if the input contains duplicates, **an arbitrary element from the duplicate group** is retained.

~~~java
record User(String id, String displayName) {
}

List<User> source = List.of(
    new User("u1", "An"),
    new User("u1", "Nguyen An")
);

Set<User> users = Set.copyOf(source);
~~~

The two `User` records above have the same `id` but different `displayName`, so under the default record `equals`, they are **not equal** because all components participate in comparison. The result will contain both.

If you want to define two users with the same `id` as duplicates, design the type/set logic around the proper business key; do not assume `Set.copyOf` knows that `id` is a unique key.

For two elements that are genuinely equal according to `equals`, do not rely on the identity of which element is retained. If selecting the representative instance matters, handle that rule before calling `Set.copyOf`.

### 5.2. Set Ordering

`Set.copyOf` **does not guarantee the iteration order** matches the input collection. You should not write business logic that depends on the first element when iterating over the resulting set.

If insertion order must be preserved, use an ordered structure such as `LinkedHashSet` and wrap the copy with `Collections.unmodifiableSet`:

~~~java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

Set<String> orderedRoles = Collections.unmodifiableSet(
    new LinkedHashSet<>(source)
);
~~~

Here `LinkedHashSet` preserves insertion order. `unmodifiableSet` is a view over the newly created `LinkedHashSet` copy; as long as no reference to the intermediate mutable set is retained elsewhere, the resulting structure cannot be modified by external callers.

## 6. Map.copyOf: Copying Key-Value Mappings

`Map.copyOf` creates an unmodifiable map from a source map:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapCopyDemo {
    public static void main(String[] args) {
        Map<String, Integer> source = new HashMap<>();
        source.put("An", 90);
        source.put("Binh", 85);

        Map<String, Integer> scores = Map.copyOf(source);
        source.put("Chi", 95);

        System.out.println(source);
        System.out.println(scores);
        System.out.println(scores.get("An"));
    }
}
~~~

`Map.copyOf` preserves the key-value mappings present in the source map at creation time. Operations that modify the resulting map are forbidden.

### 6.1. No Guarantee of Iteration Order

The source map might be a `LinkedHashMap` or `TreeMap`, but `Map.copyOf` does not promise to preserve the source's iteration order. If order is part of the API contract, choose a copy and wrapper approach with explicit ordering:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> orderedCopy = Collections.unmodifiableMap(
    new LinkedHashMap<>(source)
);
~~~

`LinkedHashMap` preserves the insertion order of the entries iterated from `source`; the unmodifiable wrapper prevents callers from modifying the map through the returned reference.

If key-sorted order is needed, you can use `TreeMap` before wrapping:

~~~java
import java.util.Collections;
import java.util.Map;
import java.util.TreeMap;

Map<String, Integer> sortedCopy = Collections.unmodifiableMap(
    new TreeMap<>(source)
);
~~~

### 6.2. Keys and Values Must Be Non-null

`Map.copyOf` does not accept `null` keys or values:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, String> source = new HashMap<>();
source.put("name", "An");
source.put("nickname", null);

// Throws NullPointerException because the value for nickname is null.
Map<String, String> copy = Map.copyOf(source);
~~~

This differs from some implementations like `HashMap`, which allow one null key and multiple null values. Before using `Map.copyOf`, clarify the data's null policy.

If `null` carries business meaning, represent it explicitly, for example:

- Omit the entry if no value is present.
- Use a value type that represents present/absent state.
- Use `Optional` at appropriate API boundaries, without turning every field into an `Optional` by default.
- Clearly distinguish "missing key" from "key with empty value" according to the data contract.

Do not replace null with a fake string like `"null"` if that string could be valid data.

## 7. Null Is Rejected in All Three Methods

Unmodifiable collections created by `copyOf` do not allow null elements:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.Map;

List<String> listWithNull = Arrays.asList("A", null);
Set<String> setWithNull = Set.of("A"); // this set has no null

// Both of the following calls throw NullPointerException:
// List<String> list = List.copyOf(listWithNull);
// Set<String> set = Set.copyOf(listWithNull);

Map<String, String> mapWithNull = new java.util.HashMap<>();
mapWithNull.put("key", null);
// Map<String, String> map = Map.copyOf(mapWithNull);
~~~

`List.copyOf` and `Set.copyOf` throw `NullPointerException` if the input collection is null or contains a null element. `Map.copyOf` throws `NullPointerException` if the input map is null or has a null key or value.

The practical reason is that the unmodifiable collections of this API target a null-free data model, reducing ambiguous states callers must handle. If the domain allows null, handle it before creating the copy.

## 8. What Is a Shallow Copy?

`List.copyOf`, `Set.copyOf`, and `Map.copyOf` copy the **collection structure and references to elements**, rather than creating independent copies of each inner object.

For example, with:

~~~java
List<StringBuilder> source = ...;
List<StringBuilder> copy = List.copyOf(source);
~~~

The two collections are structurally distinct, but `source.get(0)` and `copy.get(0)` reference the **same `StringBuilder`**.

Diagram:

~~~text
Before copy:

source ──> [ reference A ] ──> StringBuilder("draft")

After List.copyOf:

source ──> [ reference A ] ──┐
                            ├──> same StringBuilder("draft")
copy   ──> [ reference A ] ──┘
~~~

Modifying the structure of `source` after copying does not alter the structure of `copy`. However, mutating the referenced object is visible through both collections.

### 8.1. Example Demonstrating Shallow Copy

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    public static void main(String[] args) {
        StringBuilder note = new StringBuilder("draft");

        List<StringBuilder> source = new ArrayList<>();
        source.add(note);

        List<StringBuilder> copy = List.copyOf(source);

        source.clear();             // Only removes the element from source.
        note.append(" updated");    // Mutates the shared object.

        System.out.println(source.size()); // 0
        System.out.println(copy.size());   // 1
        System.out.println(copy.get(0));   // draft updated
    }
}
~~~

The output shows two things are simultaneously true:

1. `copy` is independent of adding/removing elements in `source`.
2. `copy` still sees the updated state of the `StringBuilder`, because both collections hold the same reference to that object.

This is a **shallow copy**, not a deep copy.

## 9. Shallow Copy with Map Has the Same Limitation

A Map holds both keys and values. `Map.copyOf` copies the mappings, but key/value objects are not cloned.

~~~java
import java.util.HashMap;
import java.util.Map;

public class ShallowMapCopyDemo {
    public static void main(String[] args) {
        StringBuilder description = new StringBuilder("new");

        Map<String, StringBuilder> source = new HashMap<>();
        source.put("status", description);

        Map<String, StringBuilder> copy = Map.copyOf(source);

        source.put("other", new StringBuilder("value"));
        description.append(" -> reviewed");

        System.out.println(source.size()); // 2
        System.out.println(copy.size());   // 1
        System.out.println(copy.get("status")); // new -> reviewed
    }
}
~~~

The resulting map does not receive the `"other"` entry added to the source map after copying, but the `"status"` value still points to the old `StringBuilder`. When that object mutates, reading through `copy.get("status")` also sees the change.

If a key is a mutable object and fields participating in `equals`/`hashCode` are mutated after insertion into the map, a hash-based map can become hard to look up or violate application expectations. Therefore, keys should be immutable types or have stable equality/hash semantics.

## 10. What Is Needed for a Deep Copy?

Java cannot automatically deep-copy arbitrary objects because it does not know:

- Which fields of an object need to be copied.
- Which fields should be shared (for example `String`, enum, immutable objects).
- Which fields need new copies created.
- How circular references or object graphs should be handled.
- Whether resources such as file handles, sockets, or threads may be copied.

For that reason, `copyOf` does not invoke copy constructors, does not call `clone()`, and does not automatically serialize/deserialize to create new objects.

### 10.1. Defining a Copy Operation for Mutable Elements

Example of a mutable type:

~~~java
final class Task {
    private String title;
    private int progress;

    Task(String title, int progress) {
        this.title = title;
        this.progress = progress;
    }

    String title() {
        return title;
    }

    int progress() {
        return progress;
    }

    void setProgress(int progress) {
        this.progress = progress;
    }

    Task copy() {
        return new Task(title, progress);
    }

    @Override
    public String toString() {
        return title + " (" + progress + "%)";
    }
}
~~~

Creating a list of new elements:

~~~java
import java.util.List;

List<Task> source = List.of(
    new Task("Read", 20),
    new Task("Practice", 40)
);

List<Task> deepCopiedElements = List.copyOf(
    source.stream()
        .map(Task::copy)
        .toList()
);
~~~

Here:

- `Task.copy()` creates a new `Task` object with copied state.
- `map(Task::copy)` produces a sequence of new Task objects.
- `toList()` creates an unmodifiable list from the stream in Java 17.
- `List.copyOf(...)` emphasizes the unmodifiable result contract; for an input that is already unmodifiable, the implementation may not need to allocate another list.

Because `Task` currently only holds `String` and `int`, the copy operation in this example suffices to isolate `Task`'s mutable state. If `Task` contained another mutable `List`, `copy()` would also need to copy the nested list according to application policy. Calling `new Task(title, progress)` alone is not a deep copy for a complex object graph.

### 10.2. Deep Copy Is Not Always Needed

If elements are immutable types like `String`, `Integer`, `LocalDate`, or a record designed with only immutable components, sharing references is usually safe.

~~~java
record Address(String city, String country) {
}

List<Address> addresses = List.of(
    new Address("Hanoi", "Vietnam"),
    new Address("Da Nang", "Vietnam")
);

List<Address> copy = List.copyOf(addresses);
~~~

Because `Address` here contains only `String`, both collections can share references to the records without exposing mutable state. However, **records are not automatically deeply immutable**: a record containing a `List<StringBuilder>` can still reference a mutable collection or mutable elements.

## 11. CopyOf, List.of, and Stream.toList

These three APIs are closely related but have different input sources:

| API | Input | Result |
| --- | --- | --- |
| `List.of(a, b, ...)` | Directly passed elements | Unmodifiable list, disallows null. |
| `List.copyOf(collection)` | An existing collection | Unmodifiable list, in source iteration order, disallows null. |
| `stream.toList()` | A stream | Unmodifiable list of elements emitted by the stream, in encounter order if the stream is ordered. |
| `Collectors.toList()` | A stream via collector | No guarantees on type, mutability, or thread safety of the resulting list. |
| `Collectors.toUnmodifiableList()` | A stream via collector | Unmodifiable list, disallows null. |

Example:

~~~java
import java.util.List;

List<String> source = List.of("A", "B", "C");

List<String> copied = List.copyOf(source);

List<String> fromStream = source.stream()
    .filter(s -> !s.isBlank())
    .toList();
~~~

`Stream.toList()` already returns an unmodifiable list since Java 16. There is no need to wrap it in `Collections.unmodifiableList` just to prevent callers from adding/removing elements. `List.copyOf` is useful when the input is already a `Collection` and you want to explicitly enforce an unmodifiable contract.

For `Set` and `Map`, there are corresponding unmodifiable collectors such as `Collectors.toUnmodifiableSet()` and `Collectors.toUnmodifiableMap(...)`. Those collectors also disallow null and require handling duplicate elements/keys according to the collector's contract.

## 12. Ordering Guarantees: List vs. Set and Map

Do not assume every `copyOf` method preserves order:

| Collection | Guaranteed order |
| --- | --- |
| `List.copyOf` | Preserves source iteration order. |
| `Set.copyOf` | Does not guarantee iteration order. |
| `Map.copyOf` | Does not guarantee entry iteration order. |

If a public API needs a stable order:

- Use `List.copyOf` if data is ordered and may contain duplicates.
- Use `Collections.unmodifiableSet(new LinkedHashSet<>(source))` if you need a unique set preserving insertion order.
- Use `Collections.unmodifiableMap(new LinkedHashMap<>(source))` if you need a map preserving insertion order.
- Use `Collections.unmodifiableMap(new TreeMap<>(source))` if you need ordering by key comparator.

Do not rely on the display order of `Set.copyOf` or `Map.copyOf` in logs, snapshot tests, or API protocols.

## 13. CopyOf and null: Designing Data Contracts

Because all three methods reject null, before calling them you must decide which data is allowed to be missing.

For example, if an input list may contain null:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

List<String> source = new ArrayList<>();
source.add("A");
source.add(null);
source.add("B");

// Approach 1: filter out null under an explicit policy.
List<String> nonNull = List.copyOf(
    source.stream()
        .filter(Objects::nonNull)
        .toList()
);
~~~

Or if null is invalid data, validate and fail at the system boundary instead of silently dropping it:

~~~java
List<String> requiredValues = List.copyOf(source);
~~~

The call above throws `NullPointerException`, helping detect contract-violating input. Whether to filter out or reject null depends on business semantics; do not automatically filter nulls if doing so could silently lose information.

For maps, you can filter entries with non-null keys/values before creating a copy:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> clean = sourceMap.entrySet().stream()
    .filter(entry ->
        entry.getKey() != null && entry.getValue() != null
    )
    .collect(Collectors.toUnmodifiableMap(
        Map.Entry::getKey,
        Map.Entry::getValue
    ));
~~~

This creates an unmodifiable map from valid entries. If the data has duplicate keys after a transformation, the collector may throw `IllegalStateException`; define a clear merge policy instead of dropping data arbitrarily.

## 14. Value-Based Collections and Identity

Unmodifiable collections created by factory methods such as `List.of`, `Set.of`, `Map.of`, and `copyOf` should be treated as **value-based objects** per the API documentation. They are designed to be compared by contents, not for callers to depend on instance identity.

Avoid:

~~~java
if (List.copyOf(source) == List.copyOf(source)) {
    // Do not rely on this result.
}
~~~

Do not:

- Use `==` to determine whether two `copyOf` collections are the same instance.
- Use `System.identityHashCode` as a business identifier.
- Use a value-based collection as a monitor for `synchronized`.
- Hold collection identity references as cache keys when the real intent is content comparison.

Use `equals` when comparing contents:

~~~java
List<String> first = List.copyOf(List.of("A", "B"));
List<String> second = List.copyOf(List.of("A", "B"));

System.out.println(first.equals(second)); // true
~~~

The two lists are equal by content and order, regardless of whether the application knows if they share the same identity.

## 15. Using copyOf When Returning Collections from a Class

A common pattern is keeping a mutable collection inside a class for internal updates, while returning an unmodifiable copy:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CourseCatalog {
    private final List<String> lessons = new ArrayList<>();

    public void addLesson(String title) {
        lessons.add(title);
    }

    public List<String> lessons() {
        return List.copyOf(lessons);
    }
}
~~~

Callers can read the list but cannot add/remove elements on the result:

~~~java
CourseCatalog catalog = new CourseCatalog();
catalog.addLesson("Collections");

List<String> visible = catalog.lessons();
// visible.add("Streams"); // UnsupportedOperationException
~~~

If the catalog later adds another lesson, the previously returned `visible` list does not update automatically. Callers need to call `lessons()` again to obtain a new structural snapshot.

### 15.1. Protecting State Across Multiple Threads

`copyOf` by itself does not create a safe transactional snapshot if another thread is mutating the source during the copy. If a mutable source collection is accessed concurrently, synchronize reads and writes with the same mechanism.

Example with synchronized methods:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SynchronizedCatalog {
    private final List<String> lessons = new ArrayList<>();

    public synchronized void addLesson(String title) {
        lessons.add(title);
    }

    public synchronized List<String> lessons() {
        return List.copyOf(lessons);
    }
}
~~~

Here both reads and writes use the same object's monitor, so copying does not run concurrently with `addLesson`. If the application uses another locking mechanism, all relevant write and read paths must follow the same policy. Merely wrapping a collection with `copyOf` does not make operations on the mutable source thread-safe.

## 16. Common Pitfalls

| Mistake | Why it defies expectations | How to handle |
| --- | --- | --- |
| Thinking `copyOf` makes every inner object immutable | It only copies the structure; element references are still shared. | Design immutable elements or perform a deep copy according to the data model. |
| Using `Collections.unmodifiableList(source)` for a snapshot | It is a view; source changes still show through. | Use `List.copyOf` with a stable mutable source. |
| Assuming `Set.copyOf` preserves source order | Set does not guarantee iteration order. | Use `LinkedHashSet` and a wrapper if insertion order is required. |
| Assuming `Map.copyOf` preserves `LinkedHashMap` order | The resulting map does not guarantee iteration order. | Use a `LinkedHashMap` copy and wrapper. |
| Passing null inside list/set/map | The copyOf methods reject null. | Validate, remove, or represent missing state under an explicit policy. |
| Assuming `Set.copyOf` throws on duplicate elements in source | The resulting Set keeps one element per duplicate group; an arbitrary instance may be retained. | Determine the representative element yourself if identity matters. |
| Comparing results with `==` | Value-based collections do not promise identity. | Use `equals` for content comparison. |
| Calling `copyOf` while another thread mutates the source | A single copy operation has no atomic snapshot guarantee. | Synchronize the source or use a structure suited for concurrent access. |
| Calling copyOf and assuming nested data won't change | Nested collections or mutable values can still be mutated. | Copy recursively or use an immutable data model. |

## 17. Complete Program: Structural Snapshot with Shared Elements

File **`CopyOfShallowDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CopyOfShallowDemo {
    public static void main(String[] args) {
        StringBuilder mutableItem = new StringBuilder("draft");
        List<StringBuilder> sourceList = new ArrayList<>();
        sourceList.add(mutableItem);

        List<StringBuilder> listCopy = List.copyOf(sourceList);
        sourceList.add(new StringBuilder("later"));
        mutableItem.append(" updated");

        System.out.println("Source list size: " + sourceList.size());
        System.out.println("Copy list size: " + listCopy.size());
        System.out.println("Copied element: " + listCopy.get(0));

        Set<String> setCopy = Set.copyOf(
            List.of("USER", "ADMIN", "USER")
        );
        System.out.println("Set size: " + setCopy.size());

        Map<String, Integer> mapCopy = Map.copyOf(
            Map.of("An", 90, "Binh", 85)
        );
        System.out.println("Map value: " + mapCopy.get("An"));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 CopyOfShallowDemo.java
java CopyOfShallowDemo
~~~

List section output:

~~~text
Source list size: 2
Copy list size: 1
Copied element: draft updated
~~~

The set has size 2 because the two `"USER"` strings are equal so only one is kept; the map still reads the `An -> 90` mapping. The print order of set or map elements is not guaranteed by `copyOf`.

## 18. Frequently Asked Questions

**Does List.copyOf always create a new object?**  
Do not rely on that. The implementation may reuse an input collection that is already unmodifiable. Rely on the content and unmodifiability contract, not on identity.

**Does copyOf clone each element?**  
No. It copies the collection structure and element references. For a deep copy, the application must define how to copy each object type and nested objects.

**Does List.copyOf keep duplicate elements?**  
Yes. List preserves the order and occurrence count of elements from the source.

**Does Set.copyOf throw an error when the source collection contains duplicates?**  
No. Equal elements are collapsed into one; an arbitrary element from the duplicate group is kept.

**Does Map.copyOf preserve LinkedHashMap order?**  
There is no guarantee on iteration order. If order is part of the contract, create a LinkedHashMap copy and wrap it with Collections.unmodifiableMap.

**Why does Map.copyOf throw NullPointerException on a HashMap with a null value?**  
Because the unmodifiable map created by copyOf does not allow null keys or values, even though the source HashMap allows null.

**Is Collections.unmodifiableList the same as List.copyOf?**  
No. The wrapper is a view over the source; structural changes to the source are still reflected through the view. copyOf creates an unmodifiable result decoupled from subsequent structural changes to an ordinary mutable source.

**Does a record guarantee deeply immutable elements when passed to List.copyOf?**  
No. A record only has final component fields; if a component points to a mutable list or mutable object, that state can still change.

**Should I call List.copyOf(stream.toList())?**  
Usually unnecessary if the goal is just an unmodifiable list, because Stream.toList() in Java 17 already returns an unmodifiable list. Use copyOf when the input is a collection and that contract is needed.

## 19. Official References

- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): ordering, null handling, unmodifiability, and potential reuse of already-unmodifiable sources.
- [Java SE 17 API — Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): deduplication, null handling, and iteration order.
- [Java SE 17 API — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): mappings, null handling, unmodifiability, and ordering.
- [Java SE 17 API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): contract for a read-only view over a source list.
- [Java SE 17 API — Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)) and [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): unmodifiable wrappers.
- [Java SE 17 API — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): creating an unmodifiable list from stream elements.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): background on how factory methods for unmodifiable collections were introduced to Java.

**Guiding principle:** Use List.copyOf, Set.copyOf, and Map.copyOf to create unmodifiable collections with the right null and ordering policies. Remember they are shallow copies: the collection structure is separated, but element/key/value objects are still shared. When deep immutability, specific ordering, or synchronized snapshots are needed, design the corresponding policy explicitly.
