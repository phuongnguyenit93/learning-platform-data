# reversed: a reverse-ordered view rather than a copy

## 1. Reversing the view of data is a different decision from copying

An event list is stored from oldest to newest, yet the screen needs to read it from newest to oldest. There are two different needs:

- View the same data in reverse order.
- Keep a separate sequence in reverse order for independent use later.

Starting in Java 21, `reversed()` provides a **reverse-ordered view** for appropriate sequenced interfaces. By default, it does not create an independent copy of the data.

With the original list a, b, c, d, you can picture it as:

```text
original view:       a → b → c → d
reversed view:       d → c → b → a
                     same elements of the underlying data
```

Simply calling `reversed` does not automatically mutate the original list into d, c, b, a. It provides a reversed-direction access surface.

When a program can modify through the view, changes may affect the underlying data according to the contract. If you need a sequence with its own links, you must actively copy it.

This article distinguishes four concepts that are often conflated:

| Concept | What it means |
| --- | --- |
| Encounter order | Which direction elements/mappings are traversed in |
| View | An access surface backed by the underlying data |
| Structural copy | A separate set of element/mapping links |
| Deep copy | Creating additional element data according to an application-defined level of independence |

**The examples require JDK 21 or later.** They were compiled with `--release 21` and run on OpenJDK 24.0.2, without preview features.

## 2. The `reversed` contract and how mutations work

### 2.1. Head and tail swap roles

`reversed` reverses the encounter order—that is, the order in which data is encountered. The first element in the view corresponds to the last element in the original order.

For a `List` supporting the listed modification operations, the view relationship is:

| Operation via the reversed view | Corresponding position in the original view |
| --- | --- |
| getFirst() | Tail (end) |
| getLast() | Head (start) |
| set(0, value) | Replace the last element |
| addFirst(value) | Add to the end |
| addLast(value) | Add to the start |
| removeFirst() | Retrieve and remove from the end |
| removeLast() | Retrieve and remove from the start |

The table describes the meaning of the ordering, not a requirement that the JVM invoke a specific internal method name.

If a `List` currently has `n` elements and no intervening modifications occur, the element at index `i` of the view corresponds to the element at index `n - 1 - i` of the original list.

Insertion positions, by contrast, lie between elements: inserting at index `i` of the view corresponds to position `n - i` in the original view. Do not use the `n - 1 - i` access formula for insertion positions.

### 2.2. Having a view does not automatically grant write access

If an implementation allows modification through the view, changes are written through to the underlying structure. However, a list that disallows adding/removing may still reject those operations on the view.

`set` permission can also differ from add/remove permissions. A fixed-size list can replace elements without increasing or decreasing the element count.

At the [Java 21 SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html) level, whether changes from the underlying data are visible through the view also depends on the implementation. Do not infer a universal change-reflection guarantee for all custom classes solely from the word "view".

The `ArrayList` and `LinkedHashMap` examples in this article have specific relationships explained in detail. An application needs to know the concrete types and contracts it relies on.

### 2.3. `reversed` is not a sorting operation

The view reverses the current order. A list `8, 2, 5` yields the view order `5, 2, 8`, not automatically `2, 5, 8` or `8, 5, 2`.

For sorted structures, the view is evaluated under the reversed ordering relation. For maps with insertion order, the view observes mappings in the reverse of the encounter order.

Do not apply an arbitrary new `Comparator` just because you want to call `reversed`.

### 2.4. The return type can still preserve specific capabilities

`List.reversed` returns a `List`; `Deque.reversed` returns a `Deque`; `SortedSet.reversed` and `SortedMap.reversed` preserve their respective sorted types.

Through a reversed `List`, you still have indices. Through a reversed map, you still operate by key/mapping. `reversed` does not turn a map into a list.

See [Java 21 List.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()) for the view contract and how order-sensitive operations are interpreted.

## 3. Example 1: modifying through a List view and observing a separate copy

Save as **ReversedListViewDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class ReversedListViewDemo {
    public static void main(String[] args) {
        List<String> base = new ArrayList<>(List.of("a", "b", "c", "d"));
        List<String> view = base.reversed();
        List<String> copy = new ArrayList<>(view);
        System.out.println("base after creating view: " + base);
        System.out.println("view initially: " + view);
        System.out.println("copy initially: " + copy);

        view.set(1, "C");
        System.out.println("base after view set: " + base);
        view.addFirst("e");
        view.addLast("z");
        System.out.println("base after view end additions: " + base);
        System.out.println("view after end additions: " + view);

        System.out.println("view removeFirst: " + view.removeFirst());
        System.out.println("view removeLast: " + view.removeLast());
        System.out.println("base after view removals: " + base);
        base.addFirst("x");
        System.out.println("view after base addFirst: " + view);
        System.out.println("copy remains: " + copy);
        System.out.println("double reverse has base order: "
                + view.reversed().equals(base));

        List<String> duplicates = new ArrayList<>(List.of("x", "y", "x"));
        duplicates.reversed().remove("x");
        System.out.println("base after reversed remove x: " + duplicates);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 ReversedListViewDemo.java
java ReversedListViewDemo
```

Stdout:

```text
base after creating view: [a, b, c, d]
view initially: [d, c, b, a]
copy initially: [d, c, b, a]
base after view set: [a, b, C, d]
base after view end additions: [z, a, b, C, d, e]
view after end additions: [e, d, C, b, a, z]
view removeFirst: e
view removeLast: z
base after view removals: [a, b, C, d]
view after base addFirst: [d, C, b, a, x]
copy remains: [d, c, b, a]
double reverse has base order: true
base after reversed remove x: [x, y]
```

### 3.1. Creating a view does not reverse the original data in place

After creating `view`, `base` is still `a, b, c, d`. `view` reads as `d, c, b, a`.

`copy` was created with `new ArrayList<>(view)`, so initially it also holds `d, c, b, a`. Printing the same sequence does not prove that `view` and `copy` share the same sharing semantics.

The subsequent statements make the difference clear.

### 3.2. `set` and both additions use the view's direction

`view.set(1, "C")` replaces the second element in reverse order, which is `c` near the end of `base`. `base` becomes `a, b, C, d`.

`view.addFirst("e")` places `e` at the end of `base`. `view.addLast("z")` places `z` at the start of `base`.

Thus `base` is `z, a, b, C, d, e`, while `view` reads `e, d, C, b, a, z`. There are not two lists syncing by copying back and forth; the program is using a view over the same underlying structure.

### 3.3. Removals at the head/tail also flip direction

`removeFirst` through `view` retrieves `e`, and `removeLast` through `view` retrieves `z`. `base` is left with `a, b, C, d`.

After `x` is added to the start of `base`, `view` in this `ArrayList` example reads `d, C, b, a, x`. This shows that sharing works in both directions, not only when modifying through the view.

`copy` remains `d, c, b, a`. `set` or adding/removing links in `base` does not alter the links already copied into `copy`.

### 3.4. With duplicate elements, "first occurrence" belongs to the observed order

The separate list `x, y, x` has two `x`s. `remove("x")` through the view inspects from the head of the reversed order, so it removes the `x` at the end of the original list.

The original list is left with `x, y`, not `y, x`.

This is why reversing traversal direction can change which element is affected by an order-sensitive operation, even when the argument passed is the exact same string `"x"`.

### 3.5. Double reversal and object identity are two separate questions

The example verifies that `view.reversed` has the same `List` order as `base` using `equals`.

Do not use this result to infer that `reversed().reversed()` on every interface/implementation must return the exact same object instance as the source.

The default contract of `List` describes reversing a view back to the source `List`; when writing general-purpose code, rely on the semantics promised by the specific type, not on internal class names or the number of view objects allocated.

## 4. Distinguishing `reversed`, copies, and in-place reversal

### 4.1. Different approaches answer different requirements

| Usage with a List | Primary outcome |
| --- | --- |
| source.reversed() | Obtains a reverse-ordered view; does not reverse `source` in place |
| new ArrayList<>(source.reversed()) | Creates a separate list containing elements in the view's order at the time of copying |
| List.copyOf(source.reversed()) | Creates an unmodifiable `List` result, preserving the captured element order and disallowing `null` |
| Collections.reverse(source) | Reverses positions within the passed list itself if it supports element replacement |

`Collections.reverse` takes a `List` and returns `void`. It is an in-place mutating algorithm, unlike the `reversed` method that returns a view. The [Java 21 Collections.reverse](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)) documentation highlights this distinction.

Do not choose an approach simply because the name contains "reverse"; determine whether the original data should be mutated and whether the result needs structural independence.

### 4.2. A structural copy can still share elements

`new ArrayList<>(view)` copies element references into its own structure. It does not automatically clone every element object.

If an element is a `Task` with a mutable `name` field, modifying that `Task` itself will be visible through the source, the view, and the copy holding the same `Task`.

Conversely, removing an element from `copy` does not automatically remove the corresponding link in `base`.

If you want independence for element data as well, choose an immutable model or an appropriate deep-copying policy. There is no universal deep copy that works for every object type simply by calling the `ArrayList` constructor.

### 4.3. Unmodifiable does not mean an independent snapshot

`Collections.unmodifiableList` creates a view that prevents callers from modifying through that surface. If the underlying list still changes and the view is backed by it, readers can still observe the data changing.

`List.copyOf`, on the other hand, has a contract where the result does not reflect subsequent structural changes to the source `Collection`. However, mutable element objects can still be shared.

The two options differ in both write permissions through the result and the relationship to the source structure. The [List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) and [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) documentation are the contracts to check.

### 4.4. When `null` is present, how you copy is also a decision

An `ArrayList` can hold `null` elements; a reversed view can read that `null` if it sits at the queried position.

`List.copyOf` does not accept `null` elements. Therefore, switching from the `ArrayList` constructor to `List.copyOf` does not only change mutability; it also changes data validity constraints.

Do not let a "cleaner-looking" substitution accidentally introduce failures at data boundaries.

## 5. Example 2: separate structures, shared elements, and levels of modification restriction

Save as **ViewCopyAndElementSharing.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ViewCopyAndElementSharing {
    static final class Task {
        String name;

        Task(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        Task a = new Task("A");
        Task b = new Task("B");
        List<Task> base = new ArrayList<>(List.of(a, b));
        List<Task> view = base.reversed();
        List<Task> copy = new ArrayList<>(view);
        List<Task> frozen = List.copyOf(view);

        base.addLast(new Task("C"));
        System.out.println("view after adding C: " + view);
        System.out.println("copy after adding C: " + copy);
        System.out.println("frozen after adding C: " + frozen);

        a.name = "A*";
        System.out.println("base after element edit: " + base);
        System.out.println("copy after element edit: " + copy);
        System.out.println("frozen after element edit: " + frozen);
        copy.removeFirst();
        System.out.println("copy after removing its first: " + copy);
        System.out.println("base after copy removal: " + base);

        try {
            frozen.reversed().addFirst(new Task("D"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable reversed add: rejected");
        }

        String[] array = {"left", "right"};
        List<String> fixed = Arrays.asList(array);
        List<String> fixedView = fixed.reversed();
        fixedView.set(0, "RIGHT");
        System.out.println("array after reversed set: " + Arrays.toString(array));
        try {
            fixedView.addLast("extra");
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed-size reversed add: rejected");
        }

        List<Integer> changingBase = new ArrayList<>(List.of(1, 2));
        List<Integer> readOnlyView = Collections.unmodifiableList(changingBase.reversed());
        changingBase.addLast(3);
        System.out.println("unmodifiable view after source add: " + readOnlyView);

        List<Integer> inPlace = new ArrayList<>(List.of(1, 2, 3));
        Collections.reverse(inPlace);
        System.out.println("Collections.reverse changed list: " + inPlace);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 ViewCopyAndElementSharing.java
java ViewCopyAndElementSharing
```

Stdout:

```text
view after adding C: [C, B, A]
copy after adding C: [B, A]
frozen after adding C: [B, A]
base after element edit: [A*, B, C]
copy after element edit: [B, A*]
frozen after element edit: [B, A*]
copy after removing its first: [A*]
base after copy removal: [A*, B, C]
unmodifiable reversed add: rejected
array after reversed set: [left, RIGHT]
fixed-size reversed add: rejected
unmodifiable view after source add: [3, 2, 1]
Collections.reverse changed list: [3, 2, 1]
```

### 5.1. Adding C distinguishes the view from both copy results

`base` initially contains `Task` `A` and `B`; `view`, `copy`, and `frozen` are all created before `C` is added.

After adding `C`, `view` reads `C, B, A`, whereas `copy` and `frozen` still have the two links `B, A`. This demonstrates the structural independence of the copy results.

The name `frozen` in the example is just a variable name for the `List.copyOf` result. It does not mean every object referenced inside is deeply immutable.

### 5.2. Editing A shows that elements can still be shared

Changing `a.name` to `A*` causes `base`, `copy`, and `frozen` to all print the new name of the same `Task`.

Then `copy.removeFirst()` only removes the link to `B` in `copy`. `base` still holds `A*, B, C`.

You need to distinguish "modifying object B" from "removing B from a list". Those two operations act on two different layers.

### 5.3. Fixed-size is not the same as prohibiting all modifications

`Arrays.asList` creates a fixed-size `List` backed by an array. Its reversed view can use `set` to replace the last element of the array, so `array` becomes `left, RIGHT`.

`addLast`, however, is rejected because it requires increasing the element count.

This matches the [Java 21 Arrays.asList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)) contract, not a new permission granted by the view itself.

### 5.4. A read-only view still observes changes, while in-place reverse mutates the source

The `readOnlyView` variable disallows modification through the wrapper, yet when `changingBase` adds `3`, it reads `3, 2, 1`.

`inPlace` is a separate list to illustrate `Collections.reverse`: that list itself changes from `1, 2, 3` to `3, 2, 1`.

Both `3, 2, 1` sequences may look identical in the output, but one comes from a reversed view over the `1, 2, 3` source, while the other is data that has been reversed in place.

## 6. `reversed` on Map, SortedSet, and Deque

### 6.1. Map reverses mapping order, not keys and values

A `SequencedMap` has key, value, and entry views. A reversed map view makes these views read in the reversed encounter order.

`get` and `put` still operate by key. It does not turn keys into values, sort values independently, or create a new group of mappings just by calling `reversed`.

For supported boundary-placement operations:

| Via reversed map view | Corresponding side in the underlying map |
| --- | --- |
| firstEntry() | Last mapping |
| lastEntry() | First mapping |
| putFirst(key, value) | Place at the end |
| putLast(key, value) | Place at the start |
| pollFirstEntry() | Retrieve and remove from the end |
| pollLastEntry() | Retrieve and remove from the start |

[Java 21 SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html) describes the encounter-order reversal contract for the map and its views.

### 6.2. Specific map policies remain in effect

The default `LinkedHashMap` in the example uses insertion order. Updating the value of an existing key `b` does not turn mapping `b` into a new key at a different position.

If using an access-ordered `LinkedHashMap`, an access such as `get` can change the order according to the map's policy. The reversed view does not freeze that policy. Read the contract of the chosen mode, not just the `SequencedMap` type.

The [Java 21 LinkedHashMap.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html#reversed()) documentation also specifically states that modifications through the view propagate to the map and modifications to the map are visible through the view for this implementation.

### 6.3. Reversing SortedMap/SortedSet still preserves sorted rules

The view of a `TreeMap`/`TreeSet` is evaluated under the reversed comparison order. It still does not open up arbitrary position placement.

`putFirst`/`putLast` on `SortedMap` and `addFirst`/`addLast` on `SortedSet` are rejected. The fact that a key or element happens to belong at the boundary does not make that operation supported.

Regular `put`/`add` can modify the view of those mutable structures; the position is determined by the comparison order.

See Java 21 [SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html) and [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

### 6.4. Deque reverses both ends

For a `Deque`, head and tail swap roles in the reversed view. `removeFirst` through the view can retrieve the element at the tail of the original deque.

Empty conditions and each operation's contract still apply. `getFirst` on an empty deque throws `NoSuchElementException`; `peek`/`poll` APIs have different rules.

The view does not supply data on its own if the source has been cleared. Refer to [Java 21 Deque.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html#reversed()).

## 7. Example 3: views sharing mappings and preserving underlying structure limits

Save as **ReversedMapAndEndViews.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SequencedMap;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class ReversedMapAndEndViews {
    public static void main(String[] args) {
        SequencedMap<String, Integer> base = new LinkedHashMap<>();
        base.put("a", 1);
        base.put("b", 2);
        base.put("c", 3);
        SequencedMap<String, Integer> view = base.reversed();
        System.out.println("map view initially: " + new ArrayList<>(view.entrySet()));
        view.putFirst("d", 4);
        view.putLast("z", 0);
        view.put("b", 20);
        view.remove("a");
        System.out.println("base after view edits: " + new ArrayList<>(base.entrySet()));

        base.put("e", 5);
        System.out.println("view after base put: " + new ArrayList<>(view.entrySet()));
        System.out.println("view pollFirstEntry: " + view.pollFirstEntry());
        System.out.println("base remaining: " + new ArrayList<>(base.entrySet()));
        System.out.println("view values: " + new ArrayList<>(view.sequencedValues()));

        SortedMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(1, "A");
        sorted.put(2, "B");
        sorted.put(3, "C");
        SortedMap<Integer, String> sortedView = sorted.reversed();
        try {
            sortedView.putFirst(4, "D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("reversed SortedMap putFirst: rejected");
        }
        sortedView.put(4, "D");
        System.out.println("sorted base keys: " + new ArrayList<>(sorted.keySet()));
        System.out.println("sorted view keys: " + new ArrayList<>(sortedView.keySet()));

        SortedSet<Integer> set = new TreeSet<>(List.of(1, 2, 3));
        SortedSet<Integer> setView = set.reversed();
        try {
            setView.addFirst(4);
        } catch (UnsupportedOperationException expected) {
            System.out.println("reversed SortedSet addFirst: rejected");
        }
        setView.add(4);
        System.out.println("set base: " + new ArrayList<>(set));
        System.out.println("set view: " + new ArrayList<>(setView));

        Deque<String> deque = new ArrayDeque<>(List.of("front", "back"));
        Deque<String> dequeView = deque.reversed();
        System.out.println("reversed deque removeFirst: " + dequeView.removeFirst());
        System.out.println("deque remaining: " + new ArrayList<>(deque));
        deque.clear();
        try {
            dequeView.getFirst();
        } catch (NoSuchElementException expected) {
            System.out.println("empty reversed deque getFirst: NoSuchElementException");
        }
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 ReversedMapAndEndViews.java
java ReversedMapAndEndViews
```

Stdout:

```text
map view initially: [c=3, b=2, a=1]
base after view edits: [z=0, b=20, c=3, d=4]
view after base put: [e=5, d=4, c=3, b=20, z=0]
view pollFirstEntry: e=5
base remaining: [z=0, b=20, c=3, d=4]
view values: [4, 3, 20, 0]
reversed SortedMap putFirst: rejected
sorted base keys: [1, 2, 3, 4]
sorted view keys: [4, 3, 2, 1]
reversed SortedSet addFirst: rejected
set base: [1, 2, 3, 4]
set view: [4, 3, 2, 1]
reversed deque removeFirst: back
deque remaining: [front]
empty reversed deque getFirst: NoSuchElementException
```

### 7.1. View operations affect the same map

The underlying map starts with `a=1, b=2, c=3`. `view` reads `c=3, b=2, a=1`.

`putFirst("d", 4)` through `view` places `d` at the end of `base`. `putLast("z", 0)` through `view` places `z` at the start of `base`.

`put("b", 20)` updates the value of `b`; `remove("a")` removes the `a` mapping in the shared data. Thus `base` is left with `z=0, b=20, c=3, d=4`.

No "sync copy" step is needed after these operations.

### 7.2. Adding to `base` and then removing from the head of `view`

When `base` adds `e=5`, the `LinkedHashMap` view in the example reads `e` first. `pollFirstEntry` on `view` retrieves and removes `e=5`, corresponding to the end of `base`'s order.

The value sequence `4, 3, 20, 0` follows the mappings `d, c, b, z` in `view`. The numbers are not sorted ascending or descending by numeric value.

If a program extracts only values and forgets the ordering tied to the keys, it is very easy to misinterpret the reversed map's result.

### 7.3. Sorted views allow modification but reject forced boundary placement

The `SortedMap` view rejects `putFirst(4, "D")`, then accepts `put(4, "D")`. `base` has key order `1, 2, 3, 4`; `view` reads `4, 3, 2, 1`.

The `SortedSet` view similarly rejects `addFirst(4)`, while regular `add(4)` succeeds. The underlying set stays sorted in its original order, and the view reflects the reversed direction.

Both experiments use a new element that naturally belongs at the boundary to avoid the misconception that merely picking a "fitting" value lets you force placement.

### 7.4. The Deque view shares the underlying data's lifecycle in the example

`removeFirst` through `view` retrieves `"back"`, leaving the original deque with only `"front"`.

After `deque.clear()`, `getFirst` through `view` throws an exception because the underlying data is empty. The view does not keep a private copy of the two strings to continue returning them as when it was created.

## 8. Cost, ownership, and shared data

### 8.1. A view does not mean zero object allocation

An implementation may allocate a view object to forward calls to the underlying data in reverse. Not copying all elements is different from not allocating any object at all.

Do not rely on the number of objects created, the view's implementation class name, or `==` object identity comparison as a general-purpose API performance guarantee.

The `reversed` contract does not mandate a single time complexity across all collections, all operations, and all custom classes.

### 8.2. Copying must maintain the result structure's own data

A new `ArrayList` containing `n` elements needs to hold `n` element references in its own structure and must read the data to copy it.

If you only need to traverse once in reverse over an appropriate structure, a view can express that need without actively copying all data.

If you need a result isolated from additions/removals on the source, the copying cost serves a real requirement. Do not omit a copy just for optimization and break the stability callers expect.

### 8.3. Returning a view externally means sharing a relationship with the source

If an API returns a mutable view of an internal list, callers can modify the underlying data through that surface.

A read-only wrapper can restrict modification through the returned value. By default, it does not turn the contents into an independent snapshot or make the elements inside immutable.

When designing a return value, clearly answer:

1. Is the recipient allowed to modify the structure?
2. Should the recipient see subsequent additions/removals on the source?
3. Are element objects shared?
4. Is a stable version of the data at a point in time required?

Do not use a generic `List` type to obscure all of those decisions.

### 8.4. A view does not decouple its lifetime from the source

A view backed by underlying data may need to retain a reference to the source to execute later calls. Do not assume the source can be freed independently just because you kept a differently named `view` variable.

If you need to retain a result set separately without depending on the source structure, choose an appropriate copying strategy and also consider shared element data.

This is a consequence of data ownership, not a reason that every case must copy.

### 8.5. No new thread-safety guarantees

`ArrayList` does not automatically become safe for concurrent modification when viewed through `reversed`.

If one thread modifies the source while another thread traverses the view, you must follow the implementation's concurrency/iterator contract. Not getting a `ConcurrentModificationException` does not prove that the access pattern is safe.

Copying from a source that is being concurrently modified also does not automatically produce an atomic snapshot. For a consistent snapshot, you need proper data reading/publishing protocols or coordinated synchronization with mutators.

A read-only view is also not a synchronization lock and does not automatically freeze shared data.

## 9. Choosing a view or a copy based on usage requirements

| Scenario | Option to evaluate |
| --- | --- |
| Traverse existing events in reverse, while accepting a relationship to the source | `reversed` view of the appropriate type |
| Modify the head of the reversed view and want to update the source itself | A view that permits the corresponding modification |
| Export a separate list preserving the observed order | Copy from the view, such as a new `ArrayList` |
| Return a result that disallows add/remove/replace and does not reflect source structural edits | `List.copyOf` if `null` policy and element types fit |
| Disallow modification through one surface while still sharing underlying data | Read-only view with a documented contract |
| Isolate mutable element data as well | Immutable data or a custom deep-copy policy |
| Want the current list itself to reverse positions in place | `Collections.reverse` when the list supports the required operation |

Neither choice is universally better. Views serve intentional shared relationships; copies serve intentional independence.

When the result is only used within a short scope for reading, a view is often easy to express. When the result crosses time, task, or ownership boundaries, publish stability and modification policies more explicitly.

## 10. How to test without confusing views with copies

### 10.1. Test with operations that distinguish the two models

Comparing printed sequences right after creation is not enough, because both a view and a copy can print `d, c, b, a`.

A meaningful test should check behaviors that differ:

- Does creating the view leave the original view unchanged?
- Does modifying a position through the view affect the corresponding position in the source?
- Do additions/removals at both ends through the view go in the right direction?
- Does a structural copy retain its copied links when the source adds/removes?
- Are mutable elements still shared?
- Does the view preserve the source's `set`/add/remove restrictions?

For maps, also test entry/key/value ordering and verify that an operation through the view updates the underlying mapping correctly.

### 10.2. Do not use `equals` of every type to prove ordering

`List.equals` is sequence-aware. However, `Map.equals` and `Set.equals` do not compare encounter order the way `List` does.

A map or set can be equal to its reversed view under the mapping/membership contract while still having opposite iteration orders.

If you are testing order, explicitly compare the element/entry sequence in traversal order, as with the `ArrayList`s created for printing in the examples. Do not use a `true` `equals` result as evidence that the order did not change.

### 10.3. Keep empty, `null`, and optional-operation cases in the test suite

An empty source, a single-element source, a source with duplicate elements, and a source containing `null` can expose assumptions that examples with distinct elements miss.

For indexed insertion, distinguish element indices `0` to `n-1` from insertion positions `0` to `n`.

For restricted-modification data, test element replacement, addition, and removal separately. Do not infer from a successful `set` that `add` will succeed, or from a rejected `add` that `get` no longer works.

Tests should assert published API behavior, not a specific view class name, object address, or internal optimization detail.

## 11. Common pitfalls

| Misconception | Correction |
| --- | --- |
| `reversed` already reversed the source in place | It returns a reverse-ordered view; creating the view alone does not alter the original order |
| Two variables with the same initial sequence are both copies | Check sharing behavior after mutations |
| `addFirst` on the view should add to the start of the source | Head/tail directions are swapped |
| Access index and insertion index use the same formula | Access uses `n - 1 - i`, insertion position uses `n - i` in the `List` model described |
| `remove` on a duplicate element always removes the same object as the source | The first occurrence is determined by the view's order |
| An `ArrayList` copy automatically clones every element | It copies the reference structure, not a deep copy |
| `List.copyOf` makes every element inside immutable | Mutable elements can still be shared |
| A read-only view is an independent snapshot | Write permission through the view is distinct from reflecting source data |
| Fixed-size means `set` is not allowed | `Arrays.asList` can replace elements but cannot change size |
| `reversed` unlocks `addFirst` on `SortedSet` | It preserves the constraints of the sorted model |
| A reversed map swaps keys and values | Only the encounter order of mappings is reversed |
| A view allocates nothing and every operation is O(1) | The general API does not promise that |
| Copying from a concurrently modified source is always an atomic snapshot | A separate consistency mechanism is required |
| `reversed` automatically provides thread safety | The implementation's concurrency contract still governs |

## 12. Self-check exercises

### Exercise 1. After creating a view, does the source change?

`base` is `1, 2, 3`. You only call `base.reversed()` and hold the result, without modifying anything. Does `base` automatically become `3, 2, 1`?

**Answer hint:** No. The view reads in reverse order; the original view remains `1, 2, 3`.

### Exercise 2. Where does adding at the head of the view land?

An `ArrayList` `a, b, c` has a mutable reversed view. What sequence does `base` become after `view.addFirst("x")`?

**Answer hint:** `base` becomes `a, b, c, x`. The head of the view corresponds to the tail of `base`.

### Exercise 3. Which position is index 0 of the view?

The source has `n` elements, with no intervening modifications. Which index of the source `List` does `view.set(0, value)` affect?

**Answer hint:** Index `n - 1`. For an insertion at index `0` of the view, the corresponding insertion position is `n`.

### Exercise 4. Why does the copy still see the `Task` name change?

`copy` was created with `new ArrayList<>(view)`. Modifying a field on the `Task` held by both is visible in both. Does this contradict `copy` having its own structure?

**Answer hint:** No. A separate structure can still hold the same `Task` reference; a structural copy is not a deep copy.

### Exercise 5. Does read-only mean stable?

`Collections.unmodifiableList` wraps a view backed by a still-changing source. Can it be treated as an independent snapshot?

**Answer hint:** No. It restricts modification through that surface, without detaching the underlying data.

### Exercise 6. Can `List.copyOf` be used when `null` is present?

The source `ArrayList` contains `null` and the view can read that element. Does switching to `List.copyOf(view)` always preserve the same validity constraints?

**Answer hint:** No. `List.copyOf` rejects `null` elements.

### Exercise 7. Does a `TreeMap` view accept `putFirst`?

The new key would be the first element in reverse order. Does that make `putFirst` allowed on a `SortedMap` view?

**Answer hint:** No. `SortedMap` does not support forced placement via `putFirst`/`putLast`; regular `put` goes through the sorting rules.

### Exercise 8. Does a map view remove from a separate copy?

`pollFirstEntry` on a mutable `LinkedHashMap` view retrieves an entry. Does the corresponding entry remain in the underlying map because "it is just a view"?

**Answer hint:** No. Removal through the view is written through to the underlying map according to the implementation contract.

### Exercise 9. Does double `reversed` require comparing addresses?

To check whether reversing a `List` twice restores the encounter order, do you need to use `==` as a general correctness condition?

**Answer hint:** No. Check semantics according to the specific contract; do not generalize an object-identity optimization to all interfaces and implementations.

### Exercise 10. How does `Collections.reverse` differ from `reversed`?

One method returns a view, and the other mutates a list in place. Which should you evaluate if the requirement is to keep the source order unchanged and only traverse in reverse?

**Answer hint:** Evaluate a `reversed` view as appropriate; do not use `Collections.reverse` on the source when you do not want to alter positions in the source.

## 13. References

- [SequencedCollection — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): reverse-ordered views, both-end operations, and limits of the general contract.
- [List.reversed — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()): `List` view and semantics of reverse-order operations.
- [List.copyOf — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable result, ordering, `null`, and relationship to the source.
- [Collections — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): in-place `reverse` and read-only wrappers.
- [Arrays.asList — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size `List` backed by an array.
- [SequencedMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): mapping order, views, and boundary operations.
- [LinkedHashMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): encounter-order policies and relationship between the `reversed` view and the map.
- [SortedMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html): key-ordered reversed view and forced-placement limits.
- [SortedSet — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html): element-ordered reversed view and forced-placement limits.
- [Deque — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html): both ends of a deque and the `reversed` view.
- [ArrayList — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html): `List` structure and synchronization requirements under concurrent modification.
