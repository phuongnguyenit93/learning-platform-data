# Why an Unmodifiable View Still Sees Changes from the Source

## 1. A Write-Blocked Read Path, Not Frozen Data

Suppose a class holds a list of people currently in a classroom. That class wants to let other callers view the list, while requiring all join/leave operations to go through its business methods.

`Collections.unmodifiableList(source)` meets this requirement: the recipient cannot modify the list through the returned result, while the owner of `source` continues adding or removing people. When reading the view again after valid sequential updates on the source, the recipient sees the new state.

Those two facts do not contradict each other. **unmodifiable describes operations that are disallowed through an interface; view describes which source the data is read from.**

Distinguish three requirements:

| Requirement | Corresponding question |
|---|---|
| Block writes through a reference | Can the holder of this reference call `add`, `remove`, `set`, `put`, etc.? |
| Isolate from structural changes in the source | If the source adds/removes/reorders elements, does the returned data change accordingly? |
| Preserve the state of every element | If an object inside changes its fields, does the reader see it? |

An unmodifiable view directly solves only the first requirement. The other two depend on whether data is copied and whether the objects inside are mutable.

This article uses the wrappers `Collections.unmodifiableList`, `unmodifiableSet`, and `unmodifiableMap` as the primary model. The complete examples run on Java 17 or later. All updates in the examples are performed sequentially on a single thread; multi-threaded usage is analyzed separately.

## 2. Mechanism: The Wrapper Reads Through the Wrapped Collection

### 2.1. The Link to the Source Still Remains

A view does not need to manage an independent set of elements. It keeps a reference to the wrapped structure and forwards appropriate read operations to that structure.

Conceptually, when `view.size()` is called, the answer comes from the current size of the source. When `view.get(i)` is called, the value comes from the current element at index `i` of the source. Modification operations through the view are blocked.

This describes the mechanism, not that the implementation source code must look identical across every JDK. What to rely on is the API contract: queries on `unmodifiableList` and `unmodifiableMap` read through the supplied structure. [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) and [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) state this behavior directly.

Because the source still exists and is still modified through another reference, subsequent reads of the view see the updated source. There is no background content-sync task, event dispatch, or silent re-copying to achieve that result; the wrapper is simply reading the same underlying data.

### 2.2. Two Access Paths with Different Permissions

You can picture it as:

- The owner holds `source` and can modify it using the `source` API.
- The recipient holds `view` and can read it, but update operations through `view` are rejected.
- Both access paths ultimately point to the same data structure.

Wrapping `source` does not turn `source` itself into an unmodifiable collection. Nor does it revoke mutable references that were handed out earlier.

If another piece of code already has `source` or a writable view of `source`, that code can still mutate the data. When evaluating ownership, follow the actual references, not just a variable name like `readOnly`.

### 2.3. Not Every Wrapper Needs to Be a New Object

Do not use `view != source` as the definition of an unmodifiable view. Some calls may reuse an object that already satisfies the contract. Details such as the number of wrapper layers or internal class names do not determine whether it is backed by a source.

The proper test is to observe write permissions and read results after the source changes. Comparing references, inspecting runtime class names, or casting to an internal class does not replace the API contract.

The [Collection — View Collections and Unmodifiable Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) documentation is the reference point for distinguishing where data is stored from a layer that provides a view.

## 3. Program with List: Source Changes, View Changes; Copy Keeps the Old Structure

The program creates three results from the same source:

- `view` wraps `source` directly.
- `copiedThenWrapped` wraps a copied `ArrayList`.
- `copiedByFactory` is created with `List.copyOf(source)`.

The source holds immutable `String`s so the first part focuses strictly on changes to the list structure.

File **LiveListViewDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class LiveListViewDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> copiedThenWrapped =
                Collections.unmodifiableList(new ArrayList<>(source));
        List<String> copiedByFactory = List.copyOf(source);

        source.set(0, "A2");
        source.add("C");
        System.out.println("view=" + view);
        System.out.println("copiedThenWrapped=" + copiedThenWrapped);
        System.out.println("copiedByFactory=" + copiedByFactory);
        expectUOE("viewAdd", () -> view.add("D"));
        expectUOE("viewSet", () -> view.set(0, "X"));
        Iterator<String> iterator = view.iterator();
        iterator.next();
        expectUOE("iteratorRemove", iterator::remove);

        List<String> current = source;
        List<String> fromCurrent = Collections.unmodifiableList(current);
        current = new ArrayList<>(List.of("X"));
        current.add("Y");
        System.out.println("reboundVariable=" + current);
        System.out.println("oldObjectView=" + fromCurrent);

        source.remove("B");
        System.out.println("afterSourceRemove=" + view);
        source.clear();
        System.out.println("afterSourceClear=" + view);
        source.add("NEW");
        System.out.println("afterSourceRefill=" + view);

        String[] array = {"red", "blue"};
        List<String> arrayView =
                Collections.unmodifiableList(Arrays.asList(array));
        array[0] = "green";
        System.out.println("arrayBacked=" + arrayView);

        CopyOnWriteArrayList<String> concurrentSource =
                new CopyOnWriteArrayList<>(List.of("old"));
        List<String> concurrentView =
                Collections.unmodifiableList(concurrentSource);
        Iterator<String> oldIterator = concurrentView.iterator();
        concurrentSource.add("new");
        List<String> oldIteration = new ArrayList<>();
        oldIterator.forEachRemaining(oldIteration::add);
        System.out.println("currentView=" + concurrentView);
        System.out.println("oldIterator=" + oldIteration);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LiveListViewDemo.java
java LiveListViewDemo
```

Exact stdout:

```text
view=[A2, B, C]
copiedThenWrapped=[A, B]
copiedByFactory=[A, B]
viewAdd=UnsupportedOperationException
viewSet=UnsupportedOperationException
iteratorRemove=UnsupportedOperationException
reboundVariable=[X, Y]
oldObjectView=[A2, B, C]
afterSourceRemove=[A2, C]
afterSourceClear=[]
afterSourceRefill=[NEW]
arrayBacked=[green, blue]
currentView=[old, new]
oldIterator=[old]
```

### 3.1. `set` Is Also a Change Visible Through the View

`source.set(0, "A2")` replaces the element at a position without increasing the size. `source.add("C")` adds a new position. `view` sees both results and prints `[A2, B, C]`.

Therefore, do not restrict the meaning of "changes from the source" to only add/remove operations. Replacing elements, valid reordering, or updating mapped values can also change what the view reads.

`copiedThenWrapped` remains `[A, B]` because it wraps a different `ArrayList`, created before `source` changed. `copiedByFactory` also retains the elements from the time of copying. The point of decoupling is the **structural copy** step, not the name `unmodifiable`.

### 3.2. Mutation Paths on the View Itself Are Blocked

`view.add("D")`, `view.set(0, "X")`, and `iterator.remove()` all throw `UnsupportedOperationException`. For `List`, being unmodifiable includes disallowing element replacement; it is not merely a fixed-size list.

An `Iterator` obtained from an unmodifiable view does not provide a backdoor to remove from the source. Similarly, the wrapper's `ListIterator` disallows modifications via `add`/`set`/`remove` on that interface.

However, the fact that these operations fail does not imply that `source.add(...)` must also fail. `source` itself is the update path still held by the owner.

### 3.3. Reassigning a Variable Does Not Change Which Object the View Wraps

`current` initially points to `source`. `fromCurrent` is created from the object that `current` points to at the moment `unmodifiableList` is called.

Later, `current` is reassigned to a new `ArrayList` `[X, Y]`. This assignment only changes the value of the `current` variable. It does not redirect `fromCurrent` to wrap the new object. `fromCurrent` still reads the old list, so it prints `[A2, B, C]`.

This is a useful detail when reading code:

- Mutating the wrapped source object -> the view reads the valid changes of that object.
- Reassigning a variable to another object -> the old view does not automatically switch targets.

If an API needs to always fetch the current collection from a replaceable field, that is a different query design. Do not expect an already-returned wrapper to track an application variable.

### 3.4. `clear` Does Not Break the Link

After `source.clear()`, `view` becomes empty. After `source.add("NEW")`, that same `view` prints `NEW`. It did not become an independent empty collection, nor was it "closed" after `clear`.

An empty view is merely observing an empty source at the time of reading. Emptiness says nothing about whether the source can change later.

### 3.5. The Source Can Sit Behind Another View

`arrayView` wraps `Arrays.asList(array)`, which is backed by `array`. When `array[0]` is changed to `green`, the outer wrapper reads through the intermediate list and sees `green`.

The chain here is: unmodifiable view -> array-backed list -> array. Adding a wrapper layer does not sever the link in inner layers.

[Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) returns a fixed-size list backed by an array. It allows replacing elements via `set` when not blocked by an outer wrapper, unlike an unmodifiable list.

The `CopyOnWriteArrayList` part at the end of the program will be explained in the iterator section: the current view and a previously created iterator are not required to reflect the same data version.

## 4. The Same Rules Apply to Set and Map

### 4.1. `UnmodifiableSet` Still Relies on the Source Set

`Collections.unmodifiableSet(sourceSet)` blocks updates through the returned set. If the owner validly adds or removes elements via `sourceSet`, reads from the view reflect the current source set.

The wrapper does not create a new ordering. If the source has a guaranteed iteration order, the view reads according to that contract; if the source does not guarantee ordering, wrapping does not make the order stable.

For `SortedSet` or `NavigableSet`, choose the corresponding wrapper if the API needs to preserve ordering/navigation capabilities. Returned sub-views must still enforce write blocking per the wrapper contract. However, mutable elements in a set remain a separate issue, especially when mutating fields affects `equals`/`hashCode` or `Comparator`.

### 4.2. `UnmodifiableMap` Also Blocks Write Paths Through Collection Views

`Map` has multiple ways to modify mappings: direct `put`/`remove`, removal through `keySet`/`values`, or updating an entry when the entry supports `setValue`.

`Collections.unmodifiableMap` must block write paths from the returned result itself. It cannot simply block `put` and leave `keySet().remove(...)` as a backdoor to delete from the source.

Meanwhile, the owner of the source map can still update mappings. The key set and values collection obtained from the view also continue to serve as views into the managed data.

## 5. Map Program: Views Track the Source and Protect Update Paths

The example uses `LinkedHashMap` so that print order follows insertion order deterministically. Immutable `String` keys and `Integer` values avoid mixing in mutations of inner object fields.

File **LiveMapViewDemo.java**:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class LiveMapViewDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("A", 10);
        source.put("B", 20);
        Map<String, Integer> view = Collections.unmodifiableMap(source);
        Set<String> keys = view.keySet();
        Collection<Integer> values = view.values();

        System.out.println("initial=" + view);
        source.put("C", 30);
        source.put("A", 11);
        source.remove("B");
        System.out.println("updated=" + view);
        System.out.println("capturedKeys=" + keys);
        System.out.println("capturedValues=" + values);

        Map.Entry<String, Integer> writableEntry =
                source.entrySet().iterator().next();
        writableEntry.setValue(12);
        System.out.println("afterSourceEntryUpdate=" + view);

        Map.Entry<String, Integer> readOnlyEntry =
                view.entrySet().iterator().next();
        expectUOE("mapPut", () -> view.put("D", 40));
        expectUOE("keyRemove", () -> keys.remove("A"));
        expectUOE("valueRemove", () -> values.remove(12));
        expectUOE("entrySetValue", () -> readOnlyEntry.setValue(99));
        System.out.println("afterBlockedWrites=" + source);

        source.clear();
        System.out.println("emptyView=" + view);
        System.out.println("emptyKeys=" + keys);
        source.put("N", 7);
        System.out.println("refilledView=" + view);
        System.out.println("refilledValues=" + values);
    }
}
```

Run command:

```shell
javac --release 17 -encoding UTF-8 LiveMapViewDemo.java
java LiveMapViewDemo
```

Exact stdout:

```text
initial={A=10, B=20}
updated={A=11, C=30}
capturedKeys=[A, C]
capturedValues=[11, 30]
afterSourceEntryUpdate={A=12, C=30}
mapPut=UnsupportedOperationException
keyRemove=UnsupportedOperationException
valueRemove=UnsupportedOperationException
entrySetValue=UnsupportedOperationException
afterBlockedWrites={A=12, C=30}
emptyView={}
emptyKeys=[]
refilledView={N=7}
refilledValues=[7]
```

### 5.1. Additions, Value Updates, and Removals All Go Through the Source

When the source adds `C`, updates `A`'s value, and removes `B`, `view` prints `{A=11, C=30}`. `keys` and `values` obtained earlier from `view` also display the current keys/values rather than holding a snapshot from when they were obtained.

`writableEntry` obtained from `source.entrySet()` in this `LinkedHashMap` example can update `A` to `12`. That is still a valid write path on the source, so `view` reads `A=12`.

Do not generalize the `setValue` capability of a source entry to every `Map.Entry` in Java. Some entries from other APIs are non-updatable snapshots; this article only uses the path supported by this specific map.

### 5.2. Entries Returned from the Wrapper Do Not Reopen Write Access

`readOnlyEntry` obtained via `view.entrySet()` disallows `setValue(99)`. `keys.remove("A")` and `values.remove(12)` are also blocked, just like `view.put("D", 40)`.

Distinguish two operations:

- `entry.setValue(newValue)` changes the map's mapping; the map wrapper blocks this write path.
- `entry.getValue().someMutator()` invokes a method on the value object; if the value is mutable, the map wrapper does not automatically make that object immutable.

The program uses `Integer`, so there is no method to mutate the inner value. With a `List` or a business object as the value, you must analyze that object layer as well.

### 5.3. Previously Obtained Views Still Follow New Data

After `source.clear()`, both `view` and `keys` are empty. After `source.put("N", 7)`, `view` prints `N=7` and `values` prints `7`.

There is no need to re-fetch `view.values()` to see new mappings through the old `values` collection. However, an iterator already mid-traversal on that collection has its own rules; do not use this example to conclude that every old iterator automatically follows new data.

## 6. Elements Can Still Change Even Through a Read-Only View

A wrapper controls collection operations. It does not block every method of every object returned by the collection.

If `view.get(0)` returns a `Reading` with a mutable `value` field, the statement `view.get(0).value = 15` does not call `list.set()`. It mutates the `Reading` itself. Therefore, there is no reason for the list wrapper to throw `UnsupportedOperationException` for that operation.

Similarly, an unmodifiable outer list can contain inner lists that are still mutable. There is no automatic recursive wrapping of every inner data layer.

### 6.1. Program Distinguishing Three Layers

The program below compares:

- `view` of the source list.
- `shallowSnapshot`, a copy of element references via `List.copyOf`.
- `detachedValues`, a list of new values, each a record containing only an `int`.

The second half uses nested lists containing `String` to illustrate copying only the outer layer.

File **ReadOnlyLayersDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ReadOnlyLayersDemo {
    static final class Reading {
        int value;

        Reading(int value) {
            this.value = value;
        }
    }

    record ReadingSnapshot(int value) {}

    private static List<Integer> values(List<Reading> readings) {
        return readings.stream().map(r -> r.value).toList();
    }

    public static void main(String[] args) {
        List<Reading> source = new ArrayList<>();
        source.add(new Reading(10));
        source.add(new Reading(20));
        List<Reading> view = Collections.unmodifiableList(source);
        List<Reading> shallowSnapshot = List.copyOf(source);

        view.get(0).value = 15;
        System.out.println("sourceAfterElementEdit=" + values(source));
        System.out.println("snapshotAfterElementEdit=" + values(shallowSnapshot));

        source.set(0, new Reading(99));
        System.out.println("viewAfterReplacement=" + values(view));
        System.out.println("snapshotAfterReplacement=" + values(shallowSnapshot));

        List<ReadingSnapshot> detachedValues = source.stream()
                .map(r -> new ReadingSnapshot(r.value))
                .toList();
        source.get(0).value = 100;
        System.out.println("viewAfterLaterEdit=" + values(view));
        System.out.println("detachedValues=" +
                detachedValues.stream().map(ReadingSnapshot::value).toList());

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> nestedSource = new ArrayList<>();
        nestedSource.add(inner);
        List<List<String>> outerView =
                Collections.unmodifiableList(nestedSource);
        List<List<String>> outerSnapshot = List.copyOf(nestedSource);

        outerView.get(0).add("y");
        List<List<String>> copiedBothLevels = nestedSource.stream()
                .map(List::copyOf)
                .toList();
        inner.add("z");
        System.out.println("nestedView=" + outerView);
        System.out.println("outerSnapshot=" + outerSnapshot);
        System.out.println("copiedBothLevels=" + copiedBothLevels);

        source.clear();
        System.out.println("viewAfterClear=" + values(view));
        System.out.println("shallowSnapshotAfterClear=" + values(shallowSnapshot));
        System.out.println("detachedAfterClear=" +
                detachedValues.stream().map(ReadingSnapshot::value).toList());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyLayersDemo.java
java ReadOnlyLayersDemo
```

Exact stdout:

```text
sourceAfterElementEdit=[15, 20]
snapshotAfterElementEdit=[15, 20]
viewAfterReplacement=[99, 20]
snapshotAfterReplacement=[15, 20]
viewAfterLaterEdit=[100, 20]
detachedValues=[99, 20]
nestedView=[[x, y, z]]
outerSnapshot=[[x, y, z]]
copiedBothLevels=[[x, y]]
viewAfterClear=[]
shallowSnapshotAfterClear=[15, 20]
detachedAfterClear=[99, 20]
```

### 6.2. A Shallow Copy Can Still Show Field Mutations

Initially, `view`, `shallowSnapshot`, and `source` all hold the same first `Reading`. Changing that `Reading`'s `value` to `15` causes both `source` and `shallowSnapshot` to read `15`.

Then `source.set(0, new Reading(99))` replaces the reference in `source`. `view` follows `source`'s slot and sees `99`. `shallowSnapshot` still holds the reference to the earlier `Reading`, so it sees `15`.

These two lines of output point to two different causes for observed data changing:

1. The source structure changes elements/mappings -> the live view reads it.
2. A shared element object is mutated -> anywhere still holding that object can see the new state, including a shallow copy.

Do not conclude that `List.copyOf` "is still a live view of `source`" just because a mutable object inside the copy changed state.

### 6.3. Convert to Immutable Values When a State Snapshot Is Needed

`detachedValues` creates a new `ReadingSnapshot` from the `int` value being read. `ReadingSnapshot` contains only an `int`, so the stored state no longer has a mutable link to the source `Reading`.

When the source changes `value` from `99` to `100` and is then cleared, `detachedValues` still holds `[99, 20]`. This is the result of explicit value mapping combined with an unmodifiable result structure; it is not a special effect of an `unmodifiable` wrapper.

Not every `record` is deeply immutable. If a `record` holds a mutable `List` and stores that reference as-is, its inner state can still change. This example chose an `int` component to avoid that ambiguity.

### 6.4. Nested Lists Need Each Layer Considered

`outerView.get(0).add("y")` succeeds because the inner list is unwrapped and still mutable. `outerSnapshot` created via `List.copyOf(nestedSource)` also holds that same `inner` list.

`copiedBothLevels` copies each inner list using `List.copyOf` and collects the results into an unmodifiable outer list. When the original `inner` receives `z`, `outerView` and `outerSnapshot` both show `x, y, z`, while `copiedBothLevels` keeps `x, y`.

Because the leaf elements are immutable `String`s, two levels of copying in this specific model are enough to isolate the state to be saved. Do not call this pattern a general deep-copy algorithm for arbitrary object graphs.

`Stream.toList()` is used in the example to produce an unmodifiable result list; it is a terminal collection operation, not an unmodifiable view that tracks the source list. The contract at [Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) should be read separately from `Collections.unmodifiableList`.

## 7. To Keep the Result Unchanged When the Source Changes, Sever the Appropriate Link

### 7.1. Copy the Structure Before Wrapping

For a list, the expression `Collections.unmodifiableList(new ArrayList<>(source))` has two distinct steps:

1. `new ArrayList<>(source)` creates a list holding the element references at the time of copying.
2. `unmodifiableList(...)` blocks write operations through the returned result.

Subsequent structural changes to `source` do not change that private list. However, if someone still holds a mutable reference to that private list, they can modify it and the wrapper will read those changes. A policy of "a snapshot whose structure nobody can change" also requires not leaking any write path to the copy.

When creating the private list inline in the expression and returning only the wrapper, the application can keep exclusive ownership of that structure. Elements themselves remain subject to the shallow-copy behavior seen in `ReadOnlyLayersDemo`.

### 7.2. `List.copyOf` Is a Clear Choice for Non-Null Element Snapshots

`List.copyOf(source)` returns an unmodifiable list, and later changes to the input collection are not reflected in the result with respect to adding, removing, or replacing element references. It still does not clone element objects.

This method does not accept `null` elements. Therefore, replacing `Collections.unmodifiableList(source)` with `List.copyOf(source)` can change all of the following:

- Whether updates from the source are tracked.
- When data is copied.
- The `null` policy.
- Allocation/creation cost.

Do not treat that replacement as a "behavior-preserving optimization" if the previous API intentionally returned a live view or supported `null`.

If the contract must allow `null` elements, one way to copy the structure is the illustrative method below. This is a method to place inside a Java class that imports `Collection`, `List`, `ArrayList`, and `Collections`; it is not a standalone `main` program:

```java
static <T> List<T> snapshotAllowingNull(Collection<? extends T> source) {
    return Collections.unmodifiableList(new ArrayList<>(source));
}
```

The method only allows `null` elements as supported by `ArrayList`; passing a `null` `source` reference is still invalid. It does not deep-copy elements.

`List.copyOf` may reuse an already-suitable input list in some cases. That is not a reason to test with `==` or infer that it is allowed to return a view still backed by an external mutable structure. Rely on the result's contract, not on allocation counts.

See [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) to verify the guarantees of isolation from input collection updates and `null` constraints.

### 7.3. `Map` and `Set` Also Need Copying Strategies Matched to Requirements

`Map.copyOf(sourceMap)` creates an unmodifiable result that does not follow subsequent mapping updates on the input map; keys and values can still share objects. It does not accept `null` keys or values and is not the default choice for preserving a custom iteration order of the source.

If you need the specific insertion order of a `LinkedHashMap` at the time of copying, you can copy into a private `LinkedHashMap` and wrap it with `unmodifiableMap`. If you need `Comparator` ordering and tree navigation, choose a copy structure and wrapper that preserve those capabilities.

For `Set`, detaching elements from the source structure does not make mutable elements safe keys or immutable. Mutating fields that affect `equals`/`hashCode`/`Comparator` while an element is in a set remains a data-modeling issue.

Distinguish these levels when choosing:

| Result | Tracks structural changes of `source`? | Can share mutable elements? |
|---|---|---|
| `Collections.unmodifiableList(source)` | Yes, per source/view contract | Yes |
| `Collections.unmodifiableList(new ArrayList<>(source))` | No, detached from original `source` | Yes |
| `List.copyOf(source)` | No, structurally detached from input collection | Yes |
| Separately constructed list of immutable values | No, detached from source structure | Only shares what the value model permits |

## 8. API Design: Expose a View or Expose a Snapshot?

If a business object wants to own a list while letting callers observe new state, returning a live view can be the right behavior. If callers need a fixed result for reporting, validation, or a processing step, returning a snapshot is usually more appropriate.

This distinction should be reflected in method names or documentation. Simply writing "returns a read-only list" does not clarify what happens to the result when the source changes.

The following illustrative class has no `main` and can be saved in **TagCatalog.java**. Immutable `String` elements keep the focus on structural ownership:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

final class TagCatalog {
    private final List<String> tags;
    private final List<String> readOnlyTags;

    TagCatalog(Collection<String> initialTags) {
        tags = new ArrayList<>(List.copyOf(initialTags));
        readOnlyTags = Collections.unmodifiableList(tags);
    }

    void addTag(String tag) {
        tags.add(Objects.requireNonNull(tag));
    }

    List<String> tagsView() {
        return readOnlyTags;
    }

    List<String> tagsSnapshot() {
        return List.copyOf(tags);
    }
}
```

In the constructor, the input data is copied and checked for `null` via `List.copyOf`, then placed into a private `ArrayList` so `TagCatalog` can still add tags. Subsequent modifications by the caller to `initialTags` do not directly modify the internal structure.

`tagsView()` always returns a view of the internal list. A view obtained earlier will see tags validly added via `addTag()`. `tagsSnapshot()` returns a list holding the elements at the time of the call; adding tags later does not update that snapshot.

Here, `final` keeps the `tags` and `readOnlyTags` references stable after construction. It does not make the contents of `tags` immutable: `addTag` still modifies `tags`. Blocking writes on the recipient side comes from the wrapper, while `TagCatalog`'s ability to update is intentional design.

This illustrative class does not define a multi-threading policy. If concurrent use is needed, a synchronization contract or appropriate snapshot publication must be added; no such guarantee exists merely because fields are `private final` or the result is `unmodifiable`.

### 8.1. Wrapping Input Directly Still Leaves the Caller with a Write Path

A common design mistake is storing `Collections.unmodifiableList(input)` in a field and assuming the structure is now solely controlled by the class. The caller still has the mutable `input` and can modify it.

If the goal is to prevent the caller from altering the internal structure through the passed-in collection, a defensive copy is needed upon receiving the input. If the goal is intentionally to track a changing `input`, wrapping directly can be valid, but that relationship must be documented and accepted.

There is no single right choice for every getter or constructor. The choice depends on the data ownership contract.

### 8.2. Wrapping Multiple Times Does Not Make Data More Independent

If a new wrapper reads through an old wrapper, and the old wrapper reads a mutable source, the ultimate source is still where the data lives.

Therefore, `unmodifiableList(unmodifiableList(source))` does not mean "frozen twice." A JDK may even reuse a wrapper that already fits. To sever the link, an actual copy step is required, not additional wrapper layers.

### 8.3. If the Source Can No Longer Change, the View May Look Fixed

`Collections.unmodifiableList(List.of("a", "b"))` has no underlying mutable source for the holder of that list to modify structurally through normal APIs. In that case, the data does not change structurally.

This does not change the general definition of an unmodifiable view. It simply means the source in that specific case is also unmodifiable. If elements are mutable objects, element state still needs separate consideration.

## 9. A Live View Does Not Mean Iterators Are Always Live

### 9.1. View and Iterator Are Two Objects with Different Contracts

A collection view can read the current source state on each query. An iterator created for traversal may hold a position, modification-check state, or its own snapshot.

Therefore, do not infer that an iterator created from a view must see every element newly added to the source. An unmodifiable wrapper blocks modifications through the iterator; it does not turn the source's iterator into a completely new version-tracking traversal mechanism.

### 9.2. The `CopyOnWriteArrayList` Example in the First Program

`concurrentView` wraps a `CopyOnWriteArrayList` initially containing `old`. `oldIterator` is created before the source adds `new`.

After adding, reading `concurrentView` prints `[old, new]`. However, iterating `oldIterator` yields only `old`. There is no second thread in this example: the difference comes from `CopyOnWriteArrayList`'s contract where iterators hold a snapshot.

[CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) specifies that iterators reflect the state of the array at the time the iterator was created. Thus, "the view continues tracking the source" and "an already-obtained iterator keeps the old version" can both be true.

### 9.3. With `ArrayList`, an Active Iterator Can Be Invalidated

`ArrayList` has iterators that detect structural modification on a fail-fast basis. If the owner modifies the source while another caller is traversing the view's iterator, the wrapper does not make that modification disappear and does not automatically protect the iterator.

`ConcurrentModificationException` can signal this kind of error, including sequential changes caused on the same thread through another reference. Detection is best-effort for catching bugs; do not use that exception as a synchronization tool or program correctness condition.

Do not conclude "it is read-only, so `ConcurrentModificationException` cannot happen." The reader does not write through the view, but another party can still write to the source.

## 10. Working Across Threads: Read-Only Does Not Guarantee Seeing Fresh Data

The programs in this article perform updates and reads sequentially, making the source/view relationship easy to observe. When multiple threads are involved, an additional contract layer is required.

Wrapping an `ArrayList` in `unmodifiableList` does not create locks, does not establish publication/happens-before relationships for new data across threads, and does not turn `ArrayList` into a concurrent collection.

From the word "live," you cannot promise that another thread will see every update immediately or observe a consistent snapshot across multiple operations.

A concurrent design must determine:

- Who has write access, and what mechanism coordinates readers and writers.
- Whether a read needs a single element, multiple consistent operations, or a fixed version.
- How mutable elements are managed concurrently.
- When creating a snapshot, whether reading the source is protected so it does not capture a mixed state.

`Collections.synchronizedList` is a different mechanism from `unmodifiableList`. If you choose a synchronized wrapper, access and iteration must follow that design's lock; stacking an `unmodifiable` wrapper on top does not allow arbitrarily locking on a different object and assuming synchronization with writers.

A concurrent collection like `CopyOnWriteArrayList` also has its own contract for operations and iterators, and is not automatically suitable for every write workload or every mutable element.

The access rules of [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)) and the specification of [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) help separate wrapper responsibilities from cross-thread coordination responsibilities.

## 11. Composed Views Still Inherit Limitations of the Source

### 11.1. Cannot Cure `subList` Invalidation Conditions

If you wrap `unmodifiableList(source.subList(...))`, the outer layer blocks writes through the result, but the inner list is still a `subList`.

The `List.subList` contract specifies that its semantics become undefined if the backing list is structurally modified in any way other than via the `subList`. Therefore, do not promise that every structural edit to `source` will leave a wrapped `subList` as a valid self-adjusting window.

One mistake to avoid is taking a valid result for `unmodifiableList(source)` on the whole list and applying it blindly to every sub-view chain. You must read the contract of each layer in the chain.

### 11.2. Range Views Only Expose Data Within Bounds

An `unmodifiableNavigableSet` wrapping a range view of `TreeSet` still only sees elements within that range. If the source adds an element outside the range, the view does not show that element; that is the filtering condition of the inner view, not evidence that the wrapper created a snapshot.

Similarly, an `unmodifiableMap` wrapping a `subMap` only reads mappings within the `subMap`'s key range. Source changes outside that range may not change what is observed through that window.

Liveness must be understood as reading according to the source and the active view's conditions, not that every update anywhere in the underlying structure will appear.

### 11.3. Do Not Hold an Entry Across Arbitrary Mutations and Assume It Stays Valid

A `Map.Entry` obtained from an iterator has usage conditions defined by the `Map` contract and the specific entry type. A wrapper does not turn a retrieved entry into a key tracker with an infinite lifetime.

When you need to read the current value of a key through a map view after updates, use the appropriate map lookup operation. When you need to save an entry snapshot, create a separate data representation and decide the copying depth for the key/value.

`LiveMapViewDemo` only uses entries at controlled update/read points; it does not rely on an old entry after the source is cleared and refilled.

## 12. Cost, Lifetime, and How to Verify the Contract

A direct wrapper does not copy all source elements into an independent structure. This is a benefit when you want to expose changing state for reading without creating a snapshot on every request.

However, that does not mean every read operation is equally cheap. Traversing `n` elements still reads `n` elements; searching or positional access depends on the source structure and its contract. A wrapper does not turn a `LinkedList` into an `ArrayList` or build new indexes.

Holding a view keeps a reference to the source. If a view or chain of views outlives its original purpose, it can extend the lifetime of the source structure. When only a small piece of historical data is needed and you want to decouple lifetimes, appropriate copying may be better than holding a view.

To properly test the behavior of a read-only API, do not just test `add` and stop. A behavioral test suite should:

1. Attempt an actual write operation through the result and confirm it is rejected per contract.
2. Modify the source through an allowed path, then read the result again to see whether it is a live view or a snapshot.
3. Try replacing the reference at a source position, separate from merely mutating an element's field.
4. If elements are mutable, try mutating a field to check actual independence.
5. For nested structures, check the inner layers as well.
6. If there are iterators or sub-views, test them according to their own contracts.
7. If a consistent snapshot across threads is required, verify the coordination mechanism during snapshot creation.

Do not use a no-op operation, such as a call with empty data, to classify every collection in Java. Some no-op updates have exception rules that depend on the specific contract. Choose an actual write operation when the goal is to verify that writes are blocked.

## 13. Exercises and Solutions

### Exercise 1 — Direct Wrap or Wrap After Copy?

`source` is `ArrayList` `[1, 2]`. Create `a = unmodifiableList(source)` and `b = unmodifiableList(new ArrayList<>(source))`. After `source.add(3)`, what do `a` and `b` show?

**Solution:** `a` shows `[1, 2, 3]`, `b` shows `[1, 2]`. `a` still reads the `source` structure; `b` reads a different `ArrayList` created before the addition. Neither allows adding elements through the returned reference itself.

### Exercise 2 — Variable Reassignment

`x` points to `ArrayList` `[A]`. `v = unmodifiableList(x)`. After `x = new ArrayList<>(List.of("B"))`, does `v` show `A` or `B`?

**Solution:** `A`. The wrapper holds a reference to the object passed in at creation time, not to the variable name `x`. Only if the old object is validly modified through another reference will `v` read those modifications.

### Exercise 3 — Does `final` Prevent the Source from Changing?

A `final List<String> source` field is initialized with an `ArrayList`. Another `final` field wraps `source` with `unmodifiableList`. Is `source.add("new")` inside the class blocked because of `final`?

**Solution:** No. `final` prevents reassigning the `source` field after initialization under normal rules; it does not forbid modifying the `ArrayList`'s contents. The view sees the new element; `add` through the view is still blocked.

### Exercise 4 — Shallow Copy with Mutable Elements

`source` contains a mutable `Account` with `balance = 10`. `a` is an unmodifiable view, `b` is `List.copyOf(source)`. If `source.get(0).balance = 20`, what `balance` do `a` and `b` read? What about after `source.set(0, new Account(30))`?

**Solution:** After the field mutation, both read `20` because they still share the same `Account`. After replacing the reference, `a` reads the new `Account` with `30`, while `b` keeps the old `Account` with `20`. The first result does not prove `b` is a view of `source`'s structure.

### Exercise 5 — Does `Map.Entry` Block All Inner State?

`m` is an `unmodifiableMap` of `Map<String, List<String>>`. Compare the behavior of `m.entrySet().iterator().next().setValue(newList)` and `m.get("k").add("x")`, assuming the existing value is a mutable `ArrayList`.

**Solution:** `setValue` is a mapping-replacement operation through the wrapper's entry and is blocked. Calling `add` on the value `ArrayList` can still succeed, because it mutates the returned object rather than calling a `Map` write operation. To block or isolate that state, you must design protection at the value layer.

### Exercise 6 — Empty View

After creating a view, the owner calls `source.clear()`. Can the view be treated as a permanently empty list for long-term caching?

**Solution:** You cannot conclude that from `clear` alone. The source can add data later and the same view will read it again. If you need to preserve an empty result from a specific point in time, obtain a result with an appropriate snapshot contract.

### Exercise 7 — `CopyOnWriteArrayList` Iterator

Create an unmodifiable view of `CopyOnWriteArrayList` `[a]`. Obtain iterator `i`, then the source adds `b`. Must a read of the view and a traversal of `i` both show `a, b`?

**Solution:** No. The current view has `[a, b]`, while `i` holds a snapshot from creation time and traverses `[a]`. Blocking writes through an iterator and which version an iterator sees are two separate concerns.

### Exercise 8 — Switching a Getter to `List.copyOf`

A getter previously returned a live view of a list that could contain `null`. Can it be replaced entirely with `List.copyOf` without announcing a contract change?

**Solution:** No. The result will no longer track subsequent structural updates like the previous view, and data containing `null` can cause the call to fail. You must redefine the contract, handle `null`, and check callers that relied on liveness.

### Exercise 9 — Choosing a Contract for a Report

A report needs the list of transactions accurate at the moment report generation starts. Source data continues to be updated. Is returning `unmodifiableList(source)` sufficient?

**Solution:** Not yet. It prevents the report from modifying the list through the returned reference, but it does not isolate source updates. You need to create a consistent snapshot under proper coordination with writers. If transactions are mutable and the report needs their fixed state, you also need to create appropriate values/snapshots for each transaction.

## 14. Key Takeaways When Reading Real-World Code

| What you see in code | Valid conclusion | What still needs checking |
|---|---|---|
| `Collections.unmodifiableList(source)` | Writes via wrapper are blocked; reads follow source | Who else still has a write path to `source`? |
| Source is modified after view creation | Full-source view can read valid new state | Iterator rules, threads, and sub-views |
| `new ArrayList<>(source)` then wrapped | Separate structure from original `source` | Does the copy leak a write path; are elements shared? |
| `List.copyOf(source)` | Result does not track structural changes of input collection | `null`, mutable elements, and copy timing |
| Source field is `final` | Field reference cannot be reassigned | Object contents can still change |
| Outer layers are all `unmodifiable` | Writes blocked through wrapped layers | Unwrapped inner layers and value objects |
| Printed data matches view creation time | No change observed yet | Was the source actually modified, and within range? |
| An iterator sees only old data | May be the iterator's contract | Do not conclude the whole view is a snapshot from that iterator alone |
| Result is only read by the recipient | Recipient does not write through that reference | Is another party writing, and is synchronization correct? |

The most useful question when encountering an unmodifiable view is: **which object is the wrapper reading from, and who can still modify that object or the elements inside it?** Only from that answer can you decide whether you need a live view, a structural copy, or a value snapshot.

## 15. References

- [Collections — unmodifiableList, unmodifiableSet, and unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).
- [Collection — View Collections and Unmodifiable Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [List — copyOf and subList contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
- [Map — collection views and copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [CopyOnWriteArrayList — snapshot iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).
