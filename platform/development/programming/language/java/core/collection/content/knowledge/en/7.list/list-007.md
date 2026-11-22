# subList with Inclusive Start and Exclusive End Range

## 1. How does subList select a position range?

`List.subList(fromIndex, toIndex)` returns a list view of a contiguous portion of the original list. The range is written as `[fromIndex, toIndex)`:

- The leading `[` means the element at `fromIndex` is included.
- The trailing `)` means the range stops before `toIndex`, excluding the element at that index.
- The selected elements retain their order from the original list.

For the list `[A, B, C, D, E]`:

| Index in original list | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Element | A | B | C | D | E |
| In range `[1, 4)`? | No | Yes | Yes | Yes | No |

Therefore, `list.subList(1, 4)` produces the slice `[B, C, D]`. It does not select `E`, nor does it interpret the second argument as "take 4 elements".

Illustrative snippet inside a method, assuming `java.util.List` and `java.util.ArrayList` are imported:

```java
List<String> letters =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));

List<String> middle = letters.subList(1, 4);

// middle = [B, C, D]
// middle.size() = 3
```

Two concepts must go together: how the range is calculated and the nature of the result. The result is a view backed by the original list, not an independent copy by default. Reading the two bounds correctly while misunderstanding this relationship can still cause a program to accidentally mutate the wrong data. [List.subList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

## 2. Why use an inclusive start and exclusive end?

### 2.1. Length is calculated by subtracting the two bounds

If the range is valid, the initial size of the result is:

```text
length = toIndex - fromIndex
```

Examples:

| Call on a 5-element list | Selected indices | Result | Size |
|---|---|---|---|
| `subList(0, 2)` | 0, 1 | `[A, B]` | 2 |
| `subList(1, 4)` | 1, 2, 3 | `[B, C, D]` | 3 |
| `subList(4, 5)` | 4 | `[E]` | 1 |
| `subList(0, 5)` | 0, 1, 2, 3, 4 | `[A, B, C, D, E]` | 5 |
| `subList(2, 2)` | None | `[]` | 0 |
| `subList(5, 5)` | None | `[]` | 0 |

To take `count` elements starting at `from`, the end bound is `from + count`, after ensuring the calculation does not overflow and does not exceed the list size. Do not use `from + count - 1` as `toIndex`; doing so omits the last element.

If a problem specifies an inclusive end index—for instance, taking from index 1 through index 3—the corresponding half-open range is `[1, 4)`. Converting from "the last included index" to "the stopping bound" must be done explicitly.

### 2.2. Two adjacent ranges share a common bound

A list can be split at position `split` into:

```java
List<String> left = letters.subList(0, split);
List<String> right = letters.subList(split, letters.size());
```

These are illustrative expressions assuming `letters` and `split` are validly declared. The element at `split` belongs only to the right side. The two ranges neither skip nor duplicate the element at the split point.

For example, with `split = 2` on `[A, B, C, D, E]`, the two segments are `[A, B]` and `[C, D, E]`. For read-only access, this is a convenient way to partition a list. If you plan to structurally modify one segment while keeping the other, you must handle the relationship between views explained below.

### 2.3. size() is a valid bound, but not a valid element index

A list with `n` elements has element indices from 0 to `n - 1`, whereas boundary positions run from 0 to `n`.

With `n = 5`, bound 5 sits right after `E`. It can be used as `toIndex` to select up to the end of the list, while `get(5)` remains invalid. Allowing `subList(5, 5)` does not create an element at index 5; it simply selects an empty range at the end.

## 3. Validity conditions and empty ranges

Every valid call must satisfy:

```text
0 <= fromIndex <= toIndex <= list.size()
```

Three conditions to check separately:

1. The start bound is non-negative.
2. The start bound does not come after the end bound.
3. The end bound does not exceed the current size.

`subList` does not automatically clamp bounds to fit the list. On a 5-element list, `subList(0, 100)` does not mean "take up to 100 elements"; it is an invalid range.

With `ArrayList`, out-of-range bounds throw `IndexOutOfBoundsException`, whereas in-range bounds in reversed order such as `subList(4, 2)` throw `IllegalArgumentException`. The exception examples in this article use `ArrayList`; when working with another implementation, consult its specific contract rather than relying on error message strings. [ArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#subList(int,int)).

An empty range is completely valid when both bounds are equal and lie within `[0, size()]`. For an empty list, `subList(0, 0)` is the only valid range.

An empty view is not automatically an unmodifiable list. If the backing list permits additions and the view remains valid, elements can be added through an empty view; they are inserted at the boundary position represented by the view. Therefore, do not infer mutability solely from `isEmpty()`.

## 4. Result indexing restarts from 0

Suppose:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));
List<String> part = source.subList(1, 4);
```

This is an illustrative initialization snippet inside a method. Before any structural modification, the index mapping is:

```text
index in source = fromIndex + index in part
```

| Index in part | Corresponding index in source | Value |
|---|---|---|
| 0 | 1 | B |
| 1 | 2 | C |
| 2 | 3 | D |

`part.get(0)` returns `B`, not `A`. `part.get(3)` fails because `part.size()` is 3. Even though `source.get(3)` is valid, index 3 is invalid when reading elements from `part`.

Similarly, `part.set(1, "X")` affects the position corresponding to index 2 in `source`. Operations such as `get`, `set`, `remove(int)`, and `indexOf` on the view use the view's own indexing system. If `part.indexOf("D")` returns 2, that is the position within `part`, not index 3 in the original list.

The offset-addition mapping helps explain how the view works; computed indices should not be stored as persistent element identities. After additions or removals, the positions of remaining elements can shift.

## 5. Complete program: ranges, bounds, and pagination

The following program uses APIs available in Java 17. Save it as `SubListRangeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListRangeDemo {
    private static void showRange(List<String> source, int from, int to) {
        try {
            List<String> part = source.subList(from, to);
            System.out.println("[" + from + ", " + to + ") -> "
                    + part + "; size = " + part.size());
        } catch (IndexOutOfBoundsException | IllegalArgumentException ex) {
            System.out.println("[" + from + ", " + to + ") -> "
                    + ex.getClass().getSimpleName());
        }
    }

    private static <T> List<T> pageCopy(
            List<T> source, int pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Invalid page");
        }
        int size = source.size();
        long offset = (long) pageIndex * pageSize;
        if (offset >= size) {
            return new ArrayList<>();
        }
        int from = (int) offset;
        int to = (int) Math.min((long) size, offset + pageSize);
        return new ArrayList<>(source.subList(from, to));
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        showRange(source, 1, 4);
        showRange(source, 0, source.size());
        showRange(source, 2, 2);
        showRange(source, source.size(), source.size());
        showRange(source, -1, 2);
        showRange(source, 0, 6);
        showRange(source, 4, 2);

        List<String> part = source.subList(1, 4);
        System.out.println("part.get(0) = " + part.get(0));
        System.out.println("part.get(2) = " + part.get(2));
        try {
            part.get(part.size());
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get(size) -> IndexOutOfBoundsException");
        }

        for (int page = 0; page < 4; page++) {
            System.out.println("page " + page + " = "
                    + pageCopy(source, page, 2));
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListRangeDemo.java
java SubListRangeDemo
```

Standard output:

```text
[1, 4) -> [B, C, D]; size = 3
[0, 5) -> [A, B, C, D, E]; size = 5
[2, 2) -> []; size = 0
[5, 5) -> []; size = 0
[-1, 2) -> IndexOutOfBoundsException
[0, 6) -> IndexOutOfBoundsException
[4, 2) -> IllegalArgumentException
part.get(0) = B
part.get(2) = D
get(size) -> IndexOutOfBoundsException
page 0 = [A, B]
page 1 = [C, D]
page 2 = [E]
page 3 = []
```

The initial calls test both normal cases and special boundary cases. The two ranges `[2, 2)` and `[5, 5)` are both empty, yet they represent two different positions. Invalid calls are not silently "auto-corrected" into valid ranges.

The `pageCopy` method illustrates a specific pagination policy:

- `pageIndex` starts at 0; `pageSize` must be positive.
- Pages beyond the end return an empty list.
- The last page takes only the remaining elements: with 5 elements and a page size of 2, the ranges are `[0, 2)`, `[2, 4)`, and `[4, 5)`.
- The multiplication is performed in `long` from the start using `(long) pageIndex * pageSize`, avoiding `int` overflow before bounds checking.
- The result is wrapped with `new ArrayList<>(...)` to decouple the returned list structure from the source list.
- The example assumes `source` is non-`null` and is not structurally modified while computing its size and extracting the range.

This is the policy of `pageCopy`, not built-in behavior of `subList`. Another method might choose to throw an exception when an out-of-range page is requested; such decisions should be explicit in the API rather than accidentally relying on exceptions.

## 6. The result is a view: changes can reflect in both directions

### 6.1. Replacing elements through the view affects the source

Illustrative snippet:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));
List<String> part = source.subList(1, 4);

part.set(1, "c");

// part = [B, c, D]
// source = [A, B, c, D, E]
```

No separate element array is promised to be allocated for `part`. The view provides a way to operate on a region of the source.

The reverse direction matters as well. With `ArrayList`, replacing an element via `source.set(index, value)` does not change the size and is not a structural modification. If the element falls within the viewed region, the view sees the new value.

This differs from adding or removing directly through the source. Do not lump all mutating methods into a single rule like "when the source changes, the view automatically updates safely"; structural modifications outside the view have their own usage limits.

### 6.2. Adding or removing through the view modifies the source structure

With a modifiable `ArrayList`:

- `part.remove(0)` removes the first element of the view from the source.
- `part.add(value)` appends to the end of the view, inserting right before the element immediately following the current range in the source.
- `part.clear()` removes all elements in the viewed range from the source.
- The size of the view changes after these operations.

Therefore, the pair of bounds used when creating the view does not mean the view forever holds its initial number of elements. After adding or removing through the view itself, it continues to represent the modified segment.

If you simply want to discard the view variable, do not call `clear()`. `clear()` deletes data from the backing list; it does not detach or dispose of a view object on its own.

### 6.3. Removing a range with subList(...).clear()

Illustrative snippet:

```java
List<Integer> values =
        new ArrayList<>(List.of(0, 1, 2, 3, 4, 5));

values.subList(1, 4).clear();

// values = [0, 4, 5]
```

The range `[1, 4)` contains the values 1, 2, 3 in this list. The statement removes the entire segment without removing the element at bound 4. This idiom avoids manually looping multiple times over shifting indices.

Do not confuse this with `values.clear()`, which clears the entire list. Also do not confuse it with creating a copy and clearing the copy; doing so would leave the source structure untouched.

## 7. Nested subList calls use bounds relative to the immediate view

Suppose the root list is `[A, B, C, D, E, F]`:

```java
List<String> middle = root.subList(1, 5);  // [B, C, D, E]
List<String> inner = middle.subList(1, 3); // [C, D]
```

This is an illustrative snippet assuming `root` has already been initialized. The bounds `1, 3` in the second call apply to `middle`, not directly to `root`. Before any structural modification, `inner.get(0)` corresponds to `middle.get(1)`, which in turn corresponds to `root.get(2)`.

If the outer range starts at `a` and the inner range starts at `c`, the effective start bound in the source is `a + c`. This addition helps verify bounds, but `inner` is still a linked view; nesting multiple times does not create a copy.

When structural modifications are needed through nested views, perform them through the exact view you will continue using and manage related views carefully. Do not hold arbitrary overlapping views and add or remove elements through different paths. The runnable example below demonstrates mutating through `inner` and reading the corresponding ancestor views.

## 8. Complete program: mutating through a view and nested views

Save as `SubListViewDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListViewDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> part = source.subList(1, 4);
        System.out.println("initial part = " + part);

        part.set(1, "c");
        System.out.println("after part.set: source = " + source);

        source.set(3, "d");
        System.out.println("after source.set: part = " + part);

        part.add(part.size(), "X");
        System.out.println("after part.add: source = " + source);
        System.out.println("after part.add: part = " + part);

        String removed = part.remove(0);
        System.out.println("removed = " + removed);
        System.out.println("after part.remove: source = " + source);
        System.out.println("after part.remove: part = " + part);

        part.clear();
        System.out.println("after part.clear: source = " + source);
        System.out.println("after part.clear: part = " + part);

        part.add("Z");
        System.out.println("after adding to empty part: source = " + source);
        System.out.println("after adding to empty part: part = " + part);

        List<Integer> numbers =
                new ArrayList<>(List.of(0, 1, 2, 3, 4, 5));
        numbers.subList(1, 4).clear();
        System.out.println("range cleared = " + numbers);

        List<String> root =
                new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
        List<String> middle = root.subList(1, 5);
        List<String> inner = middle.subList(1, 3);
        inner.set(0, "C*");
        inner.remove(1);
        System.out.println("nested root = " + root);
        System.out.println("nested middle = " + middle);
        System.out.println("nested inner = " + inner);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListViewDemo.java
java SubListViewDemo
```

Standard output:

```text
initial part = [B, C, D]
after part.set: source = [A, B, c, D, E]
after source.set: part = [B, c, d]
after part.add: source = [A, B, c, d, X, E]
after part.add: part = [B, c, d, X]
removed = B
after part.remove: source = [A, c, d, X, E]
after part.remove: part = [c, d, X]
after part.clear: source = [A, E]
after part.clear: part = []
after adding to empty part: source = [A, Z, E]
after adding to empty part: part = [Z]
range cleared = [0, 4, 5]
nested root = [A, B, C*, E, F]
nested middle = [B, C*, E]
nested inner = [C*]
```

Tracking the data region at key steps:

| Operation | Meaning in view | Consequence in source |
|---|---|---|
| `part.set(1, "c")` | Replace the second element of the view | Value `C` at index 2 of source becomes `c` |
| `source.set(3, "d")` | View sees the corresponding element replaced | `part` becomes `[B, c, d]` |
| `part.add(part.size(), "X")` | Insert at the current end bound of the view | `X` is placed before `E` in source |
| `part.remove(0)` | Remove `B` | `B` also disappears from source |
| `part.clear()` | Remove the entire segment `[c, d, X]` | Source is left with `[A, E]` |
| `part.add("Z")` when view is empty | Add at the boundary still held by the view | Source becomes `[A, Z, E]` |

The nested section replaces `C` with `C*`, then removes `D` through `inner`. The root list, middle view, and inner view all reflect the modified segment. The program does not structurally modify `root` directly and then continue assuming the old views remain valid.

## 9. When the source is structurally modified outside the view

### 9.1. Guaranteed usage boundary

The `subList` contract leaves the semantics of a view undefined if the backing list is structurally modified in any way other than via the view itself. Additions and removals that change the list size are direct examples.

Structural modification does not only mean the size increases or decreases. The contract also accounts for changes that could cause an in-progress iteration to yield incorrect results. Always check the specific operation and implementation; do not rely solely on `size()` remaining unchanged to conclude that a view is still valid.

The snippet below illustrates incorrect usage; it is not a program with reliable output to depend on:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> part = source.subList(1, 3);

source.add("E"); // Structural modification through source, outside part.

// Do not continue using part as a valid view.
// Discard this view or recreate a view based on the new data and bounds.
```

Even appending at the end, outside the range `[1, 3)`, does not make this usage safe under the contract. Do not assume a view remains valid simply because "none of the viewed elements were touched".

If you remove elements through a sibling view, another view you are holding may also become unusable. For instance, when two views point to the same source, structurally modifying through the first view is an external modification relative to the second view.

### 9.2. ConcurrentModificationException is only a fault-detection signal

Implementations commonly use a structural modification check to detect that a view is out of sync with its source. With `ArrayList`, a subsequent operation on a stale view can throw `ConcurrentModificationException`, including read operations like `size()` or printing that triggers element iteration.

The exception's name does not mean two threads are required for the error to occur. A single thread that creates a view, structurally modifies the source directly, and then reuses the old view can encounter this exact situation.

Do not build control flow around "just use it, and catch and retry if an exception occurs". What needs fixing is the view's lifecycle and the data modification path. Failing to observe an exception in a single test does not broaden the usage contract of `subList`. [View limitations in ArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#subList(int,int)), [how AbstractList tracks view modifications](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#subList(int,int)).

If an external modification has occurred, create a fresh view from the current state of the source and recompute the bounds according to your business logic. Do not mechanically reuse old bounds: after insertions or removals, the same pair of indices may point to different elements.

## 10. When do you need an independent copy?

If you need to return a slice of data so the caller can retain it long-term or mutate its own list, create a new list from the view:

```java
List<String> copy = new ArrayList<>(source.subList(from, to));
```

This is an illustrative expression assuming valid source and bounds. Calling `copy.add`, `copy.remove`, or `copy.set` alters the structure or reference slots of `copy` without modifying the corresponding reference slots in `source`.

If you need a result that disallows adding, removing, or replacing elements through the `List` API:

```java
List<String> snapshot = List.copyOf(source.subList(from, to));
```

`List.copyOf` does not accept `null` elements; choose an appropriate copying approach if the source region may contain `null`. The name `snapshot` here refers to the elements/references selected at the moment the result is created; it does not promise a deep copy of the internal state of each element object. [ArrayList(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)), [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

| Way to create result | Still dependent on source list structure? | Can caller mutate the result list? | Automatically deep-copies element objects? |
|---|---|---|---|
| `source.subList(from, to)` | Yes | Depends on source mutability | No |
| `new ArrayList<>(source.subList(from, to))` | No | Yes | No |
| `List.copyOf(source.subList(from, to))` | Does not reflect later changes to the source's element list | No | No |
| `Collections.unmodifiableList(source.subList(from, to))` | Yes, still wraps a view | Cannot mutate through this wrapper | No |

`Collections.unmodifiableList` is a wrapper that prevents mutation through the returned reference; it does not turn a view into an independent snapshot. If the source continues to be modified, the view restrictions must still be respected. [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

### 10.1. Copying a list does not mean copying its elements

Suppose each element is a mutable `Item` object whose name can change. Both a view and a copy can hold references to the exact same `Item`.

- Renaming that `Item` itself is visible from every list that still holds a reference to it.
- Calling `source.set(index, newItem)` replaces the reference in the source; a copy created earlier still holds the old reference.
- Adding an element to the copy does not make the source longer.

If independence of element state is also required, you must copy each object according to its type's rules or use suitable immutable element types. `subList`, the `ArrayList(Collection)` constructor, and `List.copyOf` do not automatically solve that requirement.

### 10.2. The mutability of the source still governs the view

`subList` does not grant extra mutation privileges:

- A view of `new ArrayList<>(...)` supports standard mutating operations.
- A view of a list created by `List.of(...)` does not allow adding, removing, or replacing elements.
- A view of a list created by `Arrays.asList(array)` allows replacing elements via `set`, but does not allow changing the size via additions or removals.
- Whether `null` is permitted, element type constraints, and other conditions still depend on the backing list.

If you want a modifiable copy from an unmodifiable source, `new ArrayList<>(view)` creates a new structure that can be modified independently. [Arrays.asList and fixed-size lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 11. Complete program: copies and shared elements

Save as `SubListCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListCopyDemo {
    private static final class Item {
        private String name;

        private Item(String name) {
            this.name = name;
        }

        private void rename(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Item> source = new ArrayList<>(List.of(
                new Item("A"), new Item("B"), new Item("C")));
        List<Item> view = source.subList(1, 3);
        List<Item> copy = new ArrayList<>(view);
        List<Item> snapshot = List.copyOf(view);

        source.get(1).rename("B*");
        System.out.println("after item rename: view = " + view);
        System.out.println("after item rename: copy = " + copy);
        System.out.println("after item rename: snapshot = " + snapshot);

        source.set(1, new Item("NEW"));
        System.out.println("after source.set: view = " + view);
        System.out.println("after source.set: copy = " + copy);
        System.out.println("after source.set: snapshot = " + snapshot);

        copy.add(new Item("COPY"));
        System.out.println("after copy.add: source = " + source);
        System.out.println("after copy.add: copy = " + copy);

        try {
            snapshot.add(new Item("X"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.add -> UnsupportedOperationException");
        }

        source.add(new Item("D"));
        System.out.println("after source.add: source = " + source);
        System.out.println("after source.add: copy = " + copy);
        System.out.println("after source.add: snapshot = " + snapshot);
        // Do not use view after structural modification through source.
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListCopyDemo.java
java SubListCopyDemo
```

Standard output:

```text
after item rename: view = [B*, C]
after item rename: copy = [B*, C]
after item rename: snapshot = [B*, C]
after source.set: view = [NEW, C]
after source.set: copy = [B*, C]
after source.set: snapshot = [B*, C]
after copy.add: source = [A, NEW, C]
after copy.add: copy = [B*, C, COPY]
snapshot.add -> UnsupportedOperationException
after source.add: source = [A, NEW, C, D]
after source.add: copy = [B*, C, COPY]
after source.add: snapshot = [B*, C]
```

Notice the difference between mutating an object and replacing a reference:

1. `rename("B*")` mutates a single `Item` object referenced by all three lists; all three print the new name.
2. `source.set(1, new Item("NEW"))` replaces the element in the source. The view sees `NEW`, while `copy` and `snapshot` retain the old object named `B*`.
3. `copy.add(...)` only makes the copy longer.
4. `snapshot.add(...)` throws `UnsupportedOperationException` because `List.copyOf` produces an unmodifiable list.
5. `source.add(...)` at the end structurally modifies the source. The program can continue using the copies, but deliberately stops using the stale view.

An unmodifiable list can still contain elements with mutable state. Therefore, "cannot call `add`" and "every observable value is permanently immutable" are two distinct requirements.

## 12. Choosing view scope and lifecycle in practice

`subList` is useful when processing a segment immediately within a controlled scope: reading a range, searching within a slice, sorting a specific segment in place on a list that supports element replacement, or deleting a segment via `clear`. Before passing a view to another method, you must know whether that method only reads or might mutate the list.

If a method accepts a `List<T>` and calls `clear()`, passing `source.subList(from, to)` to it grants permission to delete the corresponding segment from the source, assuming the source supports the operation. The parameter type `List` does not by itself express data ownership.

For return values from service methods, long-lived paginated data, caches, or deferred processing, you should explicitly decide whether to maintain a live link to the source or return an independent structure. Do not treat a view and a copy as equivalent just because a few printed elements look the same.

View implementations such as `ArrayList`'s view retain a reference to the backing list. Holding onto a small view for a long time can keep a large backing structure alive in memory. This is a natural consequence of reference retention, not proof that every `subList` call is a memory leak. If you only need to retain a small slice long-term and do not need a link to the source, an independent copy usually expresses that intent better.

Regarding performance cost, do not assume that creating, accessing, or mutating a view has the same complexity across every `List` implementation. A copy must traverse the selected elements and allocate its own storage; a view avoids copying all those elements just to look at a slice, while still relying on the access and mutation mechanisms of the backing implementation.

## 13. Common mistakes to spot when reading code

| Interpretation or code pattern | Problem | How to verify |
|---|---|---|
| `subList(1, 4)` includes the element at index 4 | Mistaking the end bound as inclusive | List the indices 1, 2, 3; the length is 3 |
| `subList(from, count)` to take `count` elements | Misinterpreting the second argument | Compute the end bound as `from + count` with proper checks |
| Using `size() - 1` as the end bound to take through the end | Drops the last element | Use `size()` as the stopping bound |
| Using `part.get(fromIndex)` to read the first element | Mixing source indices with view indices | The first element of a view is at index 0 |
| Assuming `subList(i, i)` is an error | Failing to recognize an empty range | Check that `i` lies within `[0, size()]` |
| Calling `part.clear()` to "dispose of the view" | Deletes actual data from the source | Only call `clear` when you intend to remove the segment |
| Adding to the source and continuing to use an old view | Violates the view contract boundary | Manage the structural modification path, or use a copy |
| Catching `ConcurrentModificationException` and continuing to use the view | Fails to fix the root cause of view invalidation | Discard the stale view and recompute from the current state |
| Wrapping in `unmodifiableList` and assuming it is copied | The wrapper is still backed by the underlying view | Choose `new ArrayList` or `List.copyOf` when structural decoupling is needed |
| Assuming a list copy creates new element objects | Confusing structural copying with deep copying | Check whether elements have mutable state and still share references |

## 14. Self-check by prediction

Each question is independent and uses a fresh list:

```java
List<String> data =
        new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
```

This is the initialization snippet for the exercises inside a method.

1. Which elements does `data.subList(2, 5)` contain, and what is its size?
2. To take exactly three elements starting at index 1, what are the two bounds?
3. To take the last two elements, what are the two bounds?
4. Is `data.subList(data.size(), data.size())` valid?
5. After `List<String> part = data.subList(1, 4);`, what is `part.get(1)`?
6. If `part.clear()` is called right after the setup in question 5, what remains in `data`?
7. If you create `List<String> copy = new ArrayList<>(data.subList(1, 4));` and then call `copy.clear()`, is the segment removed from `data`?
8. If you hold a view and then call `data.add("G")`, can you continue relying on the old view under the contract?

Answers:

1. `[C, D, E]`, size 3; index 5 containing `F` is excluded.
2. `[1, 4)`; the end bound is 1 + 3.
3. `[data.size() - 2, data.size())`, which is `[4, 6)`. This formula requires the source to have at least two elements.
4. Valid; the result is empty.
5. `C`; index 1 of the view corresponds to index 2 of the source.
6. `[A, E, F]`; the elements `B, C, D` are removed through the view.
7. No; `copy` has its own list structure, so the source remains `[A, B, C, D, E, F]`.
8. No; the source was structurally modified outside the view. You must recreate a valid view or use a copy as appropriate.

When using `subList`, always determine three things simultaneously: the `[fromIndex, toIndex)` range, the zero-based indexing of the returned view, and the fact that the result remains a view backed by the source. Together, these three factors determine which elements are selected, which operations mutate the original data, and how long the result can safely be retained.
