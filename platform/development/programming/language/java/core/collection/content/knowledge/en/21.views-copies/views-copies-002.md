# subList and Structural Modifications via View or Source

## 1. A Range View Over a List, Not a Copy

When you need to process a segment of a `List`, `subList` lets you work with that range through another `List` object. The key point is that **the returned `List` is a view backed by the source list**. It does not create an independent backing storage list.

Given a source `A,B,C,D,E`, calling `subList(1,4)` views `B,C,D`:

```text
Source index:   0   1   2   3   4
Source:         A   B   C   D   E
                    └───────┘
View:               B   C   D
View index:         0   1   2
```

If the source allows modifications and the view is still valid, `set` on the view replaces the reference at the corresponding position in the source. Adding, removing, or calling `clear` through the view can also structurally modify the source.

Conversely, adding or removing directly on the source and then continuing to use the old view is a different situation: the `List` contract no longer defines the behavior of that view when the source is structurally modified outside the view.

This lesson focuses on the relationship between the source, views, structural modifications, and copies. The complete programs use Java 17 or later, with `ArrayList` as the primary source for clear, verifiable behavior.

### 1.1. Key Terms to Know

| Term in this lesson | Meaning |
|---|---|
| Source, backing list | The list that backs the data for the view |
| View | An object that allows viewing/operating on a portion of the source's data |
| Half-open range | Includes the start `fromIndex`, excludes the end `toIndex` |
| Non-structural modification | For example, `set` replacing an element at an existing position without adding/removing positions |
| Structural modification | Additions/removals that change the size, or changes that affect the correctness of iteration |
| Structurally independent copy | A `List` with its own storage that no longer tracks positions in the source |
| Shallow copy | Copies element references; the element objects themselves may still be shared |
| Fail-fast | Detects certain improper modifications and fails early; not a concurrency guarantee mechanism |

## 2. Ranges and Indices of subList

### 2.1. from Is Included, to Is Excluded

For `source.subList(fromIndex, toIndex)`, the range condition is:

```text
0 <= fromIndex <= toIndex <= source.size()
Initial number of elements in the view = toIndex - fromIndex
```

`subList(1,4)` takes source indices 1, 2, 3. It does not include the element at index 4.

`subList(0,source.size())` views the entire list. `subList(i,i)` is a valid empty range when `i` is from 0 to `size`. `subList(size,size)` is also valid; it is an empty range at the end of the source.

These conditions are about indices, not searching by value. `subList` does not filter for all elements whose values fall between two numbers.

### 2.2. The View Re-indexes from 0

`view.get(0)` is the first element of the range, not necessarily `source.get(0)`. In the `B,C,D` example, `view.get(1)` is `C` at source index 2.

When inserting into a still-valid `ArrayList` view, the insertion position is relative to the view. `view.add(0,x)` inserts before the first element of the view; `view.add(view.size(),x)` inserts at the end of the view, immediately before any source elements following the range.

After adding/removing through the view, the size and indices within the view change. Do not continue using old indices without recalculating them.

### 2.3. Do Not Cast a View to an Independent ArrayList

The return type of `subList` is `List<E>`. The view object is not an `ArrayList` holding its own separate copy of the range's elements.

If you need a structurally independent `ArrayList`, create it using the constructor that takes a `Collection`, such as `new ArrayList<>(view)`, while the view is still valid. Casting does not perform a copy and can throw `ClassCastException`.

The range contract and backing relationship are described in [List.subList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 3. Content Modification vs. Structural Modification: Which Path?

### 3.1. set Replaces an Element at an Existing Position

With `ArrayList`, `set` replaces the reference at an index without adding or removing positions. While the source and view are still valid:

- `view.set(i,x)` is reflected at the corresponding position in the source.
- `source.set(j,x)` at a position within the range is reflected when reading the view.
- `set` outside the range does not cause an out-of-range element to appear in the view.

This is a position-sharing relationship. It does not mean the view re-searches for a set of elements by value after every change to the source.

### 3.2. Adding/Removing Through the View Can Validly Modify the Source

If the source supports it, `view.add`, `view.remove`, and `view.clear` modify the source. The view is performing an operation that updates its own corresponding size.

`clear` on a view removes the portion currently belonging to the view, not the entire source. Therefore, the pattern `source.subList(from,to).clear()` is useful when you need to remove a range directly from the source.

There is no rule saying “a view must never change size.” What matters is whether the source supports the operation and whether the modification is performed through the appropriate view path.

### 3.3. Adding/Removing Directly on the Source Is a Different Condition

When the backing list is structurally modified through a path other than the view in use, the `subList` contract no longer defines the behavior of that view. Do not continue relying on `size`, `get`, loops, or `toString` of the old view.

This holds true even when:

- Adding at the end of the source, outside the view's range.
- Removing an element before the range.
- Modifying through a non-overlapping sibling view.
- Removing and then adding back so the final size equals the initial size.
- Both source and view are operated on in a single thread.

Do not treat a view as an auto-sliding window that keeps the same `from`/`to` or re-finds the old objects after a structural modification to the source.

### 3.4. Object Path Matters More Than Variable Name

If `alias` and `view` point to the same view object, calling `alias.add` is still calling through that view. Renaming a variable does not turn the operation into an external source modification.

Conversely, creating two separate `subList`s from the same source produces two view objects with separate tracking states. A valid structural modification through the first view does not automatically synchronize the second view or keep it valid.

## 4. Program 1: set, add, remove, and clear Through a View

Save to `SubListBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListBasicsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> view = source.subList(1, 4);
        System.out.println("initialView=" + view);
        System.out.println("oldViewValue=" + view.set(1, "C2"));
        System.out.println("sourceAfterViewSet=" + source);
        source.set(1, "B2");
        System.out.println("viewAfterSourceSet=" + view);
        view.add(1, "X");
        System.out.println("sourceAfterViewAdd=" + source);
        System.out.println("viewAfterAdd=" + view);
        System.out.println("removedFromView=" + view.remove(2));
        System.out.println("sourceAfterViewRemove=" + source);
        view.clear();
        System.out.println("sourceAfterViewClear=" + source);
        System.out.println("clearedView=" + view);
        view.add("Y");
        System.out.println("sourceAfterReusingEmptyView=" + source);
        System.out.println("viewAfterReuse=" + view);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListBasicsDemo.java
java SubListBasicsDemo
```

Stdout:

```text
initialView=[B, C, D]
oldViewValue=C
sourceAfterViewSet=[A, B, C2, D, E]
viewAfterSourceSet=[B2, C2, D]
sourceAfterViewAdd=[A, B2, X, C2, D, E]
viewAfterAdd=[B2, X, C2, D]
removedFromView=C2
sourceAfterViewRemove=[A, B2, X, D, E]
sourceAfterViewClear=[A, E]
clearedView=[]
sourceAfterReusingEmptyView=[A, Y, E]
viewAfterReuse=[Y]
```

### 4.1. Two set Paths Looking at the Same Position

`view` initially contains `B,C,D`. `view.set(1,C2)` returns the old value `C` and changes the source to `A,B,C2,D,E`.

`source.set(1,B2)` replaces `B` in the source. The view reads `B2,C2,D`. Neither operation adds or removes positions, so the example does not invalidate the view.

### 4.2. Inserting and Removing by View Index

`view.add(1,X)` inserts `X` before element `C2` in the view. The source becomes `A,B2,X,C2,D,E`, while the view is `B2,X,C2,D`.

`view.remove(2)` removes `C2`, not the element at source index 2. The return value confirms `removedFromView` is `C2`; the source is left with `A,B2,X,D,E`.

### 4.3. clear Only Removes the Range and the View May Still Be Usable

At the time of `clear`, the view contains `B2,X,D`. Clearing through the view leaves the source with `A,E` and the view becomes empty.

`view.add(Y)` afterward is still valid in this `ArrayList` example. It inserts at the position of the emptied range, making the source `A,Y,E`. The view is not invalidated just because it cleared itself through a supported operation.

Do not confuse this case with calling `source.clear()` and then continuing to use the old view: `clear` directly on the source is a structural modification outside the view.


## 5. Losing View Guarantees Does Not Mean Always Throwing the Same Exception

### 5.1. Contract and Detection Signals Are Two Different Layers

`List.subList` specifies that the behavior of a view becomes undefined if the backing list is structurally modified through another path. This is what the programmer must avoid.

`ArrayList` often detects some cases using a fail-fast mechanism and throws `ConcurrentModificationException`. This exception is a sign of a usage violation, not a license to modify the source arbitrarily and expect the library to “fix the view automatically.”

Do not treat a single run that did not throw an exception as proof that the view is still valid. Nor is it guaranteed that every `List` implementation will throw the exact same exception on the same method after an external modification.

[ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) states the limits of fail-fast guarantees. [AbstractList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) describes a view implementation mechanism that tracks size, offset, and expected modification count.

### 5.2. Do Not Look Only at Current Size

A view can track the history of structural modifications, not just compare the final size. Removing one element and adding another so the size returns to its old value does not make the view valid again.

Beyond adding/removing, you need to check the policy of the specific operation and class. For `ArrayList`, the documentation even counts explicit resizing of the backing array as a structural modification; comparing size alone is not a sufficient safety check.

`set` at an existing position is a clearly distinguished case. Do not overgeneralize “`set` is fine” into “every operation that does not change size leaves views and iterators unaffected.”

### 5.3. Modifying Through One View Can Break Another View

Suppose `left` and `right` are two separate `subList`s of the same `ArrayList`. `left.remove` can be a valid operation for `left` and update the source. But from `right`'s perspective, the source was just structurally modified through another path.

Non-overlapping ranges do not eliminate this issue either. A view is not an independent subscriber that recalculates all offsets after modifications by other views.

Similarly, a source iterator created before `view.add` can still become invalid. “The view that just modified is still usable” does not mean every other iterator or view on the same source remains usable.

### 5.4. ConcurrentModificationException Does Not Require Two Threads

The exception name easily leads learners to think only multithreading causes it. A single thread creating a view, modifying the source directly, and then using the old view is enough to create an invalid situation.

The core issue is having multiple modification paths on the same backing structure. Synchronizing access can resolve contention between threads, but it does not change the validity rules of a view after an external structural modification to the source.

## 6. Program 2: Ways Old Views or Iterators Become Invalid

This program **intentionally demonstrates invalid usage**. The `ConcurrentModificationException` lines below are observed results with `ArrayList` on JDK 17.0.15. This is not a guarantee that every `List` will detect the same error at the same point.

Each independent case creates a new list. After observing the error, the program does not continue using the invalidated view or iterator.

Save to `SubListInvalidationDemo.java`:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class SubListInvalidationDemo {
    static void expectConcurrent(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected ConcurrentModificationException");
        } catch (ConcurrentModificationException observed) {
            System.out.println(label + "=ConcurrentModificationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> view = source.subList(1, 3);
        source.add("E");
        System.out.println("sourceAfterOutsideAdd=" + source);
        expectConcurrent("oldViewGet", () -> view.get(0));

        List<String> sameSize = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> oldRange = sameSize.subList(1, 3);
        sameSize.remove(0);
        sameSize.add(0, "Z");
        System.out.println("sourceSameSize=" + sameSize.size());
        expectConcurrent("oldRangeSize", () -> oldRange.size());

        List<String> shared = new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
        List<String> left = shared.subList(0, 2);
        List<String> right = shared.subList(3, 5);
        left.remove(0);
        System.out.println("sharedAfterLeftRemove=" + shared);
        System.out.println("leftStillUsable=" + left);
        expectConcurrent("rightGet", () -> right.get(0));

        List<String> root = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> rootIterator = root.iterator();
        List<String> current = root.subList(1, 3);
        current.add("D");
        System.out.println("currentView=" + current);
        expectConcurrent("oldRootIteratorNext", () -> rootIterator.next());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListInvalidationDemo.java
java SubListInvalidationDemo
```

Stdout:

```text
sourceAfterOutsideAdd=[A, B, C, D, E]
oldViewGet=ConcurrentModificationException
sourceSameSize=4
oldRangeSize=ConcurrentModificationException
sharedAfterLeftRemove=[B, C, D, E, F]
leftStillUsable=[B]
rightGet=ConcurrentModificationException
currentView=[B, C, D]
oldRootIteratorNext=ConcurrentModificationException
```

### 6.1. Adding Outside the Range Still Breaks the Old View

`view` looks at range `B,C` of source `A,B,C,D`. `source.add(E)` does not insert between `B` and `C`, yet it still structurally modifies the source directly.

`oldViewGet` throws `ConcurrentModificationException` in the tested environment. There is no rule allowing continued use of the view just because `E` is after the range.

### 6.2. Returning to Size 4 Does Not Restore the View

`sameSize` initially has 4 elements. `remove(0)` followed by `add(0,Z)` leaves the final element count at 4. Nevertheless, `oldRange` was created before that sequence of structural modifications, so calling `size` on that view still fails detection.

Do not try to repair a view by restoring the source's size or data to “look like the original.” You must stop using the old view object.

### 6.3. Sibling Views Do Not Synchronize With Each Other

`left` initially views `A,B`, and `right` views `D,E`. `left.remove(0)` removes `A` from the source and `left` becomes `B`.

`leftStillUsable` is `[B]` because `left` itself performed the operation. `rightGet` fails because `right` was not the path that performed the structural modification. The two ranges do not need to overlap to hit this problem.

### 6.4. A Valid View Does Not Save a Previously Created Source Iterator

`rootIterator` was created before `current.add(D)`. The `current` view remains usable and contains `B,C,D` after adding through it.

`rootIterator.next` after the modification fails detection. You must track the lifecycle of each individual iterator, not just the view object.

## 7. When You Need Independence, Make a Copy While the View Is Still Valid

### 7.1. Modifiable Copy

`new ArrayList<>(view)` collects the elements currently visible in `view` into a new `ArrayList` structure. Afterward, adding or removing on the source does not cause the copy to change size or positions along with the source.

Conversely, `add`/`remove`/`set` on the copy do not affect the source's structure. Elements are copied by reference, so the underlying objects may still be shared.

Make the copy **before** the source is modified outside the view. `new ArrayList<>(view)` is not a tool to repair an already invalidated view; the copy operation must also read the view and can fail.

### 7.2. Unmodifiable Result

`List.copyOf(view)` creates an unmodifiable `List` result that does not allow adding, removing, or replacing elements. Subsequent modifications to the source collection are not reflected as a live view in this result.

There is no promise that each `copyOf` call always allocates a brand-new object: the API may reuse a suitable unmodifiable `List`. What you should rely on is the result content contract, not object identity comparison.

`List.copyOf` does not accept `null` elements. This is a condition to check if the source range may contain `null`. `new ArrayList<>(view)` can be used when you need to preserve `null` and want a modifiable copy.

Reference: [List.copyOf — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### 7.3. Unmodifiable Does Not Mean Deep Copy

If the elements are `StringBuilder`s, both the source and the shallow copy can point to the same `StringBuilder`. Changing the `List` structure and changing the state of an element object are two different things.

If you need completely deep-independent data, you must define how to clone according to the element type. A generic deep copy cannot be inferred from `List<E>` alone.

### 7.4. Wrapping with unmodifiable Does Not Sever the Backing Relationship

`Collections.unmodifiableList(view)` blocks modifications through the wrapper, but it still relies on the underlying view. It does not create a copy, nor does it make an old view valid again after a structural modification to the source.

If the requirement is to keep a subset of data longer than the lifecycle of a changing source, choose an appropriate copy instead of merely wrapping for read-only access.

## 8. Program 3: The Source Changes, Yet Copies Remain Structurally Independent

Save to `SubListCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SubListCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> view = source.subList(1, 3);
        List<String> copy = new ArrayList<>(view);
        List<String> frozen = List.copyOf(view);
        source.add("E");
        System.out.println("sourceAfterAdd=" + source);
        System.out.println("copyAfterSourceAdd=" + copy);
        System.out.println("frozenAfterSourceAdd=" + frozen);
        copy.set(0, "B2");
        copy.add("X");
        System.out.println("editedCopy=" + copy);
        System.out.println("sourceAfterCopyEdit=" + source);
        try {
            frozen.set(0, "changed");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("frozenSet=UnsupportedOperationException");
        }

        StringBuilder value = new StringBuilder("shared");
        List<StringBuilder> builders = new ArrayList<>(List.of(value));
        List<StringBuilder> shallow = new ArrayList<>(builders.subList(0, 1));
        shallow.get(0).append("!");
        System.out.println("sourceMutableValue=" + builders.get(0));
        System.out.println("sameElement=" + (builders.get(0) == shallow.get(0)));

        List<String> nullable = new ArrayList<>(Arrays.asList("A", null, "C"));
        System.out.println("nullableCopy=" + new ArrayList<>(nullable.subList(1, 3)));
        try {
            List.copyOf(nullable.subList(1, 3));
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullableCopyOf=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListCopyDemo.java
java SubListCopyDemo
```

Stdout:

```text
sourceAfterAdd=[A, B, C, D, E]
copyAfterSourceAdd=[B, C]
frozenAfterSourceAdd=[B, C]
editedCopy=[B2, C, X]
sourceAfterCopyEdit=[A, B, C, D, E]
frozenSet=UnsupportedOperationException
sourceMutableValue=shared!
sameElement=true
nullableCopy=[null, C]
nullableCopyOf=NullPointerException
```

### 8.1. Two Results Created Before Modifying the Source

`view` looks at `B,C`. Both `copy` and `frozen` are created while `view` is still valid. `source.add(E)` then structurally modifies the source directly, so the program does not reuse `view`.

`copyAfterSourceAdd` and `frozenAfterSourceAdd` are both `[B, C]`. They do not become auto-updating ranges of the source.

### 8.2. Different Modifiability of the Results

`copy.set` and `copy.add` turn `copy` into `[B2, C, X]`; the source remains `A,B,C,D,E`. `frozen.set` is rejected with `UnsupportedOperationException`.

The variable name `frozen` is just for readability in the example. The unmodifiable property comes from `List.copyOf`; it does not deep-freeze every element object.

### 8.3. Same StringBuilder Means Both See the Change

`shallow` receives the `StringBuilder` reference already in the source. Appending through `shallow` turns `sourceMutableValue` into `shared!`, and `sameElement` is `true`.

This does not contradict the fact that the storage structures are independent. If you replace a reference at a position in the copy, the source is not updated; if you mutate the shared object itself, all places pointing to it observe that state.

### 8.4. Null Affects the Choice of Copy Type

The range `nullable.subList(1,3)` contains `null,C`. The `ArrayList` constructor preserves both positions, so `nullableCopy` is `[null, C]`.

`List.copyOf` on the same range throws `NullPointerException`. Do not use `copyOf` as an automatic null filter; if business policy requires removing or handling `null`, make that explicit before creating the result.


## 9. A View Only Has the Capabilities That the Source Supports

### 9.1. Modifiable ArrayList vs. Fixed-Size List

`subList` does not grant extra structural modification capabilities if the source does not support them.

`Arrays.asList` returns a fixed-size `List` backed by an array. It allows `set` but not additions/removals that change the number of elements. Its view cannot turn into a freely resizable range either.

Therefore, separate two questions:

1. Is replacing an element at an existing position allowed?
2. Is changing the number of positions allowed?

A source can answer “yes” to `set` and “no” to `add`/`remove`. Reference: [Arrays.asList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).

### 9.2. Unmodifiable List

`List.of` returns a `List` that does not allow adding, removing, or replacing elements. Its `subList` does not unlock modification capabilities either.

With `Collections.unmodifiableList(backing)`, the wrapper blocks modifications through the wrapper. If `backing` is an `ArrayList` and another reference calls a valid `set` on the source, the read-only view can still see that change.

Do not describe every “unmodifiable” object as deeply immutable data or an independent copy. You need to know whether it comes from an unmodifiable factory or from a wrapper still backed by a source.

The wrapper contract is described in [Collections.unmodifiableList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

### 9.3. Capability Errors Differ from Index Errors and Stale View Errors

| Condition in the examples | Issue category |
|---|---|
| `add` to a view of `Arrays.asList` | Source does not support resizing |
| `set` through an unmodifiable view | No permission to replace elements through that path |
| Negative `from` or `to` exceeding `size` | Invalid range |
| `from` greater than `to` | Bounds are out of order |
| `get` using an index equal to the view's `size` | Element index out of bounds |
| Using an old view after external structural modification of source | Violated `subList` backing contract |

Do not catch all errors and lump them together as “`subList` doesn't work.” You must distinguish between wrong range, wrong capability, and wrong lifecycle relative to the source.

## 10. Program 4: Modification Capabilities and Index Bounds

Save to `SubListCapabilitiesDemo.java`. The bounds checks use `ArrayList`, so the detailed exception names below are verified against this class's contract.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class SubListCapabilitiesDemo {
    static void expect(String label, Class<? extends RuntimeException> type,
                       Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + type.getSimpleName());
        } catch (RuntimeException observed) {
            if (!type.isInstance(observed)) {
                throw observed;
            }
            System.out.println(label + "=" + type.getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> fixed = Arrays.asList("A", "B", "C");
        List<String> fixedView = fixed.subList(1, 3);
        fixedView.set(0, "B2");
        System.out.println("fixedAfterSet=" + fixed);
        expect("fixedViewAdd", UnsupportedOperationException.class,
                () -> fixedView.add("D"));
        expect("fixedViewClear", UnsupportedOperationException.class,
                () -> fixedView.clear());

        List<String> constantView = List.of("A", "B", "C").subList(1, 3);
        expect("constantViewSet", UnsupportedOperationException.class,
                () -> constantView.set(0, "B2"));

        List<String> backing = new ArrayList<>(List.of("A", "B", "C"));
        List<String> readOnly = Collections.unmodifiableList(backing).subList(0, 2);
        expect("readOnlyRemove", UnsupportedOperationException.class,
                () -> readOnly.remove(0));
        backing.set(0, "A2");
        System.out.println("readOnlyAfterSourceSet=" + readOnly);

        ArrayList<String> checked = new ArrayList<>(List.of("A", "B", "C"));
        expect("negativeFrom", IndexOutOfBoundsException.class,
                () -> checked.subList(-1, 2));
        expect("pastEnd", IndexOutOfBoundsException.class,
                () -> checked.subList(0, 4));
        expect("reversedBounds", IllegalArgumentException.class,
                () -> checked.subList(2, 1));
        List<String> one = checked.subList(1, 2);
        expect("viewIndexPastEnd", IndexOutOfBoundsException.class,
                () -> one.get(1));
        System.out.println("emptyEndRange=" + checked.subList(3, 3));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListCapabilitiesDemo.java
java SubListCapabilitiesDemo
```

Stdout:

```text
fixedAfterSet=[A, B2, C]
fixedViewAdd=UnsupportedOperationException
fixedViewClear=UnsupportedOperationException
constantViewSet=UnsupportedOperationException
readOnlyRemove=UnsupportedOperationException
readOnlyAfterSourceSet=[A2, B]
negativeFrom=IndexOutOfBoundsException
pastEnd=IndexOutOfBoundsException
reversedBounds=IllegalArgumentException
viewIndexPastEnd=IndexOutOfBoundsException
emptyEndRange=[]
```

### 10.1. Fixed-Size Source Still Allows set

`fixedView.set(0,B2)` replaces `B` in the source, so `fixedAfterSet` is `[A, B2, C]`. However, `add` and `clear` require changing the size, so they are rejected with `UnsupportedOperationException`.

Do not equate fixed-size with “cannot modify anything.” Allowing `set` while disallowing `add` are two consistent conditions for this source.

### 10.2. An Unmodifiable View Can Still See source.set

`constantView` comes from `List.of`, so `set` is rejected. `readOnly` comes from an unmodifiable wrapper, so `remove` is also rejected.

`backing.set(0,A2)` is performed through the `ArrayList` source, not through `readOnly`. That is a modification that does not add/remove positions, so `readOnly` reads `[A2, B]` in the example. The wrapper does not turn the visible data into a fixed snapshot.

### 10.3. Source Range Differs from View Index

For `ArrayList` `checked` with size 3:

- `subList(-1,2)` and `subList(0,4)` are out of bounds.
- `subList(2,1)` reverses the bound order.
- `subList(1,2)` has only one element, so `get(1)` exceeds the view's index bounds.
- `subList(3,3)` is a valid empty range at the end.

These bounds errors are tested on data that has not been structurally modified outside the view. That helps separate index errors from stale-view errors.

## 11. Using a View to Operate on a Range Directly on the Source

### 11.1. Algorithms Accepting List Can Accept a View

When an algorithm takes a `List` and only needs to operate on a segment, you can pass a `subList` instead of the entire source. For example, `Collections.sort` on a valid view sorts that segment without sorting the entire source list.

This is a way to extend operations to a range without rewriting algorithms with `from`/`to` parameters for every method.

The conditions remain the same: the source supports the operations the algorithm needs; the view is still valid; and no other path structurally modifies the source outside the algorithm's coordination.

### 11.2. Removing Multiple Elements Through the View Itself

`clear` or `removeIf` on a modifiable view can remove a portion of the source data. Elements outside the view do not become targets of the filter.

While an algorithm is iterating, do not make extra structural calls from outside the iteration's permitted modification mechanism. A for-each loop has its own iterator; calling `view.remove` arbitrarily inside that loop is not the same as removing through the iterator.

If you need to both iterate and add/remove at the cursor position, a `ListIterator` provided by the view can be suitable, as long as you follow the `next`/`remove`/`add`/`set` lifecycle and the source's capabilities.

### 11.3. Nested Views Also Have Their Own Lifecycles

You can call `subList` on a view. The child view's indices are calculated relative to the parent view, not directly to the original source.

In the following `ArrayList` example, modifying through the child view updates the parent views in that chain and the source. However, this does not extend to guaranteeing that any sibling views or separate views created from the source remain valid.

After a parent view is structurally modified through a path other than the child view being held, do not continue relying on the old child view. When there are multiple layers of views, clearly manage which layer remains usable after each operation.

## 12. Program 5: Range Sorting, Filtering, Child Views, and ListIterator

Save to `SubListRangeOperationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ListIterator;

public class SubListRangeOperationsDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(9, 8, 7, 6, 5, 4));
        List<Integer> middle = source.subList(1, 5);
        Collections.sort(middle);
        System.out.println("sourceAfterRangeSort=" + source);
        middle.removeIf(value -> value % 2 == 0);
        System.out.println("sourceAfterRangeFilter=" + source);
        System.out.println("middleAfterFilter=" + middle);

        List<Integer> outer = source.subList(1, 3);
        List<Integer> inner = outer.subList(1, 2);
        inner.clear();
        System.out.println("sourceAfterInnerClear=" + source);
        System.out.println("outerAfterInnerClear=" + outer);
        System.out.println("innerAfterClear=" + inner);

        List<String> words = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> selected = words.subList(1, 3);
        ListIterator<String> cursor = selected.listIterator();
        System.out.println("cursorNext=" + cursor.next());
        cursor.remove();
        cursor.add("X");
        System.out.println("cursorNextAgain=" + cursor.next());
        cursor.set("C2");
        System.out.println("wordsAfterCursorEdits=" + words);
        System.out.println("selectedAfterCursorEdits=" + selected);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SubListRangeOperationsDemo.java
java SubListRangeOperationsDemo
```

Stdout:

```text
sourceAfterRangeSort=[9, 5, 6, 7, 8, 4]
sourceAfterRangeFilter=[9, 5, 7, 4]
middleAfterFilter=[5, 7]
sourceAfterInnerClear=[9, 5, 4]
outerAfterInnerClear=[5]
innerAfterClear=[]
cursorNext=B
cursorNextAgain=C
wordsAfterCursorEdits=[A, X, C2, D]
selectedAfterCursorEdits=[X, C2]
```

### 12.1. Only the Middle Range Is Sorted and Filtered

`middle` views `8,7,6,5` in source `9,8,7,6,5,4`. Sorting through `middle` changes the source to `[9, 5, 6, 7, 8, 4]`: `9` and `4` outside the range do not participate in that sort.

`middle.removeIf` removes even numbers in the view, so the source becomes `[9, 5, 7, 4]` and `middle` becomes `[5, 7]`. This is a structural modification performed through `middle` itself.

### 12.2. Clearing the Child View Changes the Source

`outer` is newly created from range `5,7`; `inner` views element `7` in `outer`. `inner.clear` leaves the source as `[9, 5, 4]`, `outer` as `[5]`, and `inner` empty.

These results are verified on a specific `ArrayList` view chain. `middle` was a separate view created earlier, so the program does not reuse `middle` after the structural modification through `inner`. Do not assume it is still valid just because it previously viewed `5,7` as well.

### 12.3. Editing Through the View's ListIterator

`selected` initially views `B,C` in source `A,B,C,D`. `cursor.next` gets `B`, `cursor.remove` deletes `B`; `cursor.add(X)` inserts `X` at the cursor position. The next `next` call gets `C`, then `cursor.set(C2)` replaces it.

The source becomes `[A, X, C2, D]` and `selected` becomes `[X, C2]`. The code uses `cursor`'s own operations throughout the traversal; it does not interleave a `selected.add` or `words.remove` from another path.

You do not need an extra copy just to perform range operations directly on the source, if the intent is to modify the source and the view's lifecycle is controlled.

## 13. Choosing View or Copy Based on Lifetime

### 13.1. A View Fits When You Want to Operate Directly on a Range

For example, when you need to remove a range once in a modifiable list. The following snippet is an illustration placed inside a method that already has valid `items`, `start`, and `end`; it is not a standalone Java file:

```java
items.subList(start, end).clear();
```

Its effect is to immediately remove that range from `items`. Do not keep a long-lived view if you only need a single range operation.

A short-lived view is also suitable for searching or sorting a segment in isolation, when all source modification paths are coordinated.

### 13.2. A Copy Fits When You Need a Result That Lives Independently of Source Structure

If you return a portion of data to another caller for storage while the source continues to have elements added/removed, consider a copy based on mutability requirements.

The illustrative snippet below must be placed inside a method with `source`, `start`, `end`, and `ArrayList`/`List` imports:

```java
List<String> result = new ArrayList<>(source.subList(start, end));
```

Choose `List.copyOf` for an unmodifiable result when elements are non-null. Both options still need separate deep-copy handling if element state can mutate.

There is no right choice based solely on “`subList` is faster.” The decision must consider whether the recipient wants to modify the source, whether the source will be modified outside the view, and how long the result needs to live.

### 13.3. Do Not Keep a Small View Assuming You Have Detached a Large Source

A view may still hold references to the source structure. A view of just a few elements does not mean data outside the range is guaranteed to no longer be kept alive.

If you need a long-lived subset of elements that is structurally independent, creating a copy expresses the intent more clearly. Even so, the selected elements may still reference other objects; a shallow copy does not automatically resolve all memory relationships in the object graph.

### 13.4. Handling After an External Structural Modification to the Source

Stop using the old view. If you still need a range of the current source, recalculate the bounds and create a new view or a new copy from the current source.

Distinguish between “same current indices” and “same old group of objects.” After additions/removals on the source, keeping the same `from`/`to` numbers may select different data than before.

Do not catch `ConcurrentModificationException` and continue reading the old view. Nor should you catch it and try to copy that same view to recover: a copy must read valid data to be meaningful.

## 14. Common Mistakes and Verification Criteria

| Mistake | Consequence or misconception | How to handle |
|---|---|---|
| Thinking `subList` is a copy | Modifying the view accidentally modifies the source | Choose a copy if you need an independent structure |
| Thinking `toIndex` is included in the range | Off by one element | Use the half-open range `[from,to)` |
| Using source indices to `remove` in a view | Removes the wrong element or goes out of bounds | Calculate indices relative to the view |
| `source.add` outside the range then using the old view | The view contract is no longer guaranteed | Stop using the view, create a new result from the current source |
| Removing then adding back to match the old size | Structural modification history has still changed | Do not treat size as a way to restore a view |
| Modifying through a first view then reusing a sibling view | The second view does not automatically stay valid/synced | Coordinate lifecycles or use a copy |
| Thinking `ConcurrentModificationException` only occurs with multithreading | Misses bugs from multiple references in a single thread | Check all structural modification paths |
| Expecting an exception immediately upon source modification | Fail-fast is not a guarantee for every case | Avoid invalid usage per the contract |
| Wrapping with `unmodifiable` to make an independent view | The wrapper still relies on the underlying data | Use an appropriate copy if independence is needed |
| Using `List.copyOf` on a range containing `null` | `NullPointerException` | Choose an explicit null policy or `ArrayList` when appropriate |
| Treating a shallow copy as a deep copy | Mutating element objects still affects other places | Design element cloning appropriately |
| `add`/`remove` on a view of `Arrays.asList` | The source does not support resizing | Create an `ArrayList` if you need a resizable list |
| Structurally modifying source via view then using old source iterator | The iterator may become invalid | Manage iterator lifecycles separately |
| Iterating with an iterator while modifying through another path | Violates modification policy during iteration | Use the iterator's own operations or change the approach |

A useful test suite should cover start/middle/end ranges, empty ranges, single-element sources, `set` from both sides, `add`/`remove`/`clear` through a view, external source modifications, sibling views, different modification capabilities, and shallow copies.

When checking source data after each operation, do not accidentally read an invalidated view just to print progress. Even `toString` on an old view is not an observation exempt from the contract.

## 15. Self-Check and Practice

### 15.1. Questions with Answers

1. **How many initial elements does `subList(1,4)` take?** Three elements at source indices 1, 2, 3.
2. **Do view indices start at `fromIndex`?** No. The view re-indexes starting from 0.
3. **Does `view.set` change the source?** Yes, when the operation is supported by the source and the view is still valid; the corresponding position in the source is replaced.
4. **Can `source.set` within the range reflect in the view?** Yes. For `ArrayList`, replacing an element at an existing position is not a structural addition/removal.
5. **Does `view.add` always fail because it changes the source size?** No. On a supporting source, adding through the view can be a valid operation and updates the view's size.
6. **Does `source.add` at the end outside the range guarantee the old view remains usable?** No. That is still a structural modification outside the view path.
7. **Can two non-overlapping views continue to be used independently after one view removes an element?** There is no such guarantee; the remaining view had its source modified through another path.
8. **Does `ConcurrentModificationException` prove there must be multiple threads?** No. A single thread with multiple references can also cause that situation.
9. **Is copying after a view has failed a valid fix?** No. You must create the copy from still-valid data, typically before the source continues to be structurally modified.
10. **Does `new ArrayList<>(view)` deep-copy `StringBuilder`?** No. It copies element references.
11. **Is `subList(size,size)` valid?** Yes, it is an empty range at the end of the source if `size` is obtained in a valid context.
12. **Can a view of `Arrays.asList` allow `set` but disallow `add`?** Yes. Fixed size is different from forbidding all modification operations.

### 15.2. Exercise: Calculate Indices and Effect on Source

Create an `ArrayList` of numbers `0,1,2,3,4,5`; take a view with `subList(2,5)`. Predict and then run `view.remove(1)`, `view.add(0,9)`, `view.clear`.

Expected: the initial view is `2,3,4`. Removing view index 1 leaves the source as `0,1,2,4,5`. Adding `9` at the start of the view makes the source `0,1,9,2,4,5`. Clearing the view afterward leaves the source as `0,1,5`.

Explain why `remove(1)` removes `3` instead of `1`.

### 15.3. Exercise: Separate Capability Errors and Lifecycle Errors

Create three separate sources: a modifiable `ArrayList`, `Arrays.asList`, and `List.of`. For each source, take the same non-empty range and try `set`, `add`, and `clear` on the view in independent tests.

With another `ArrayList`, create a view, then structurally modify the source directly and stop using the old view in proper code. You can write a separate error demonstration to observe on your current JDK, but do not turn the exception type/timing into a general guarantee for `List`.

Present the results along two axes: the source's operation capabilities and the view's validity at the time of the call.

### 15.4. Exercise: Design a Return Value

A method receives a `List<String>` and selects a range to return to the caller for long-term storage. The source will still have elements added/removed after the method finishes.

Choose between `subList`, `new ArrayList<>(subList)`, and `List.copyOf(subList)`, then state the mutability of the result and the `null` policy. If a structurally independent result is needed, do not return the view directly.

Change the element type to an object with mutable state. State what else remains unresolved by a shallow copy.

## 16. References and Verification Scope

- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `subList` contract, half-open range, external structural modifications to the source, and `copyOf`.
- [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): mutability, `subList` bounds, structural modifications, and fail-fast limits.
- [AbstractList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): a view mechanism based on offset, size, and expected modification count.
- [Arrays — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): fixed-size array-backed `List` from `asList`.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `unmodifiableList` wrapper and algorithms accepting `List`.

The five complete programs were compiled with `javac --release 17 -encoding UTF-8` and run on Corretto JDK 17.0.15, producing the exact recorded stdout. The `ConcurrentModificationException`s in the error-demonstration program are observations on `ArrayList` in that environment; the proper usage rule remains avoiding structural modifications to the source outside the view in use. The two snippets in the view/copy selection section are marked as illustrative and must be placed inside a method with appropriate variables and imports.
