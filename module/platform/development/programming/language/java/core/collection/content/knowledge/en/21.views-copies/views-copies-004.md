# Range Views of TreeSet, TreeMap, and Reversed-Order Views

## 1. The Right Mental Model: One Dataset, Multiple Windows

Suppose a system stores sorted timestamps. One feature needs to inspect timestamps from 20 up to (but excluding) 50; another needs to traverse that exact same range from end to start. If you filtered and copied them into a new collection every time, the two results would quickly become independent datasets that you would have to update manually whenever the source changes.

**Range views** address the need to work directly on an interval of an ordered structure. **Reversed-order views** let you read the same data in the opposite direction. For TreeSet and TreeMap, these views are backed by the source structure: permitted modifications through a view go straight into the source, and changes in the source appear in the view whenever they satisfy the range condition.

Separate these three questions:

- **Where does the data live?** The views still use the data managed by the source tree.
- **Which part is visible?** The range selects set elements or map keys using comparison.
- **In which direction is it viewed?** The direction of the current comparator determines first, last, previous, and next.

A single view can both restrict a range and reverse the order. Reversing the direction does not remove the bounds; restricting a range does not create a copy.

For example, an ascending source with elements 10, 20, 30, 40, 50:

| Object being viewed | Contents in iteration order |
|---|---|
| Source | 10, 20, 30, 40, 50 |
| Range from 20 (inclusive) to 50 (exclusive) | 20, 30, 40 |
| Reversed view of the range above | 40, 30, 20 |
| Copy created from the range | Elements at the time of copying; structure independent of the source |

If 35 is added to the source, both range views immediately include that element. A copy created earlier does not automatically receive 35. If 60 is added to the source, neither range view sees 60 because it is outside the bounds.

This lesson follows the order: reading bounds → operating on ranges → reading reversed order → combining both transformations → deciding when to copy. You need to know how to use basic TreeSet, TreeMap, and Comparator; you do not need to know how balanced trees are implemented.

The complete programs target JDK 21 or later and require no external libraries. The range APIs along with `descendingSet()`/`descendingMap()` existed before Java 17; the name `reversed()` was added in Java 21. Short snippets are explicitly marked as illustrative snippets, not standalone runnable files.

## 2. Range APIs: Bounds Are Defined by Comparison

### 2.1. Sets Check Elements; Maps Check Keys

TreeSet implements NavigableSet, which extends SortedSet. TreeMap implements NavigableMap, which extends SortedMap. The two API families correspond directly:

| Purpose | NavigableSet | NavigableMap |
|---|---|---|
| Bound both ends | subSet(from, fromInclusive, to, toInclusive) | subMap(from, fromInclusive, to, toInclusive) |
| Take the part before a bound | headSet(to, inclusive) | headMap(to, inclusive) |
| Take the part from a bound onward | tailSet(from, inclusive) | tailMap(from, inclusive) |

Terms like “before”, “from”, and “start” are always relative to the order of the receiver object. For an ascending tree of integers, that order matches normal numeric order. With a descending comparator, the relationship flips.

You can express this precisely using `c(a, b)`, the comparison result of the current comparator:

- A closed lower bound accepts `x` when `c(x, from) >= 0`; an open lower bound requires `> 0`.
- A closed upper bound accepts `x` when `c(x, to) <= 0`; an open upper bound requires `< 0`.
- `head` takes what precedes the bound in this order; `tail` takes what follows the bound in this order.

When using natural ordering, `c(a, b)` has the meaning of `a.compareTo(b)`—you do not need to create a custom Comparator just to call the range methods.

### 2.2. Four Bound Combinations

In the table below, the source is in ascending numeric order and contains every integer from 1 to 5:

| Call | Interval notation | Result |
|---|---|---|
| subSet(2, true, 5, true) | [2, 5] | 2, 3, 4, 5 |
| subSet(2, true, 5, false) | [2, 5) | 2, 3, 4 |
| subSet(2, false, 5, true) | (2, 5] | 3, 4, 5 |
| subSet(2, false, 5, false) | (2, 5) | 3, 4 |

For maps, replace `subSet` with `subMap` and read the numbers in the table as keys. The values associated with the keys do not participate in bound checks.

The two endpoints do not have to already exist in the source. If the source contains 10, 20, 30, `subSet(12, true, 28, false)` is still valid and shows 20. A view describes an ordering condition, not a stored “position of element 12” in the tree.

A valid range can also contain no elements at all. When the source later receives an element belonging to that range, the view will see it.

### 2.3. Legacy Forms with Default Bounds

SortedSet and SortedMap provide forms without boolean flags:

| Shorthand form | Bound equivalent |
|---|---|
| subSet(a, b) | subSet(a, true, b, false) |
| headSet(b) | headSet(b, false) |
| tailSet(a) | tailSet(a, true) |
| subMap(a, b) | subMap(a, true, b, false) |
| headMap(b) | headMap(b, false) |
| tailMap(a) | tailMap(a, true) |

That means the two-ended shorthand defaults to **inclusive start, exclusive end**; `head` excludes the bound, and `tail` includes the bound. Do not rely on a vague memory of “both inclusive” to deduce results. You can verify the signatures directly in [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) and [SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html).

The shorthand forms on TreeSet have a declared return type of `SortedSet`, and on TreeMap `SortedMap`. Consequently, writing `var v = tree.subSet(a, b)` does not give `v` navigation methods like `floor()` through its declared type. If you need `NavigableSet` or `NavigableMap`, use the boolean-parameter overloads. There is no need to cast to keep working.

### 2.4. Equal Endpoints and Reversed Endpoints

When both endpoints compare as equal:

- Both sides closed: the view can contain the element/key equivalent to that endpoint, if the source currently has it.
- At least one side open: the view is empty.
- The shorthand `[a, a)` is therefore always empty.

“Equal” here is according to the comparison used by the tree. A case-insensitive Comparator may treat two strings that differ under `equals` as the same endpoint.

Conversely, `from` coming after `to` under the current comparator is an invalid request and throws `IllegalArgumentException`. This is not how you request an empty range. On an ascending tree, `subSet(40, true, 20, true)` is invalid; on a descending view, that exact pair of endpoints can be valid.

## 3. TreeSet: Live Views and Operations Flowing into the Source

The following program tests updates in both directions, out-of-range queries, nested ranges, and a view whose data has been completely cleared.

File **RangeSetDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class RangeSetDemo {
    private static void expectIAE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> source =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));
        NavigableSet<Integer> middle =
                source.subSet(20, true, 50, false);

        System.out.println("initial=" + middle);
        System.out.println("legacy=" + source.subSet(20, 50));
        System.out.println("headClosed=" + source.headSet(20, true));
        System.out.println("tailOpen=" + source.tailSet(40, false));
        System.out.println("contains50=" + middle.contains(50));
        System.out.println("remove50=" + middle.remove(50));
        expectIAE("add50", () -> middle.add(50));

        middle.add(25);
        middle.remove(30);
        source.add(35);
        source.add(60);
        System.out.println("middle=" + middle);
        System.out.println("source=" + source);
        System.out.println("floor100=" + middle.floor(100));
        System.out.println("ceiling0=" + middle.ceiling(0));
        System.out.println("higher40=" + middle.higher(40));

        NavigableSet<Integer> nested = middle.tailSet(25, true);
        System.out.println("nested=" + nested);
        System.out.println("sameExcludedEnd=" + middle.headSet(50, false));
        expectIAE("includeExcludedEnd", () -> middle.headSet(50, true));
        expectIAE("expandNested", () -> middle.headSet(70, false));
        expectIAE("wrongDirection", () -> source.subSet(40, true, 20, true));

        middle.clear();
        System.out.println("afterClear=" + source);
        System.out.println("nestedAfterClear=" + nested);
        source.add(32);
        System.out.println("liveAgain=" + middle);
        System.out.println("nestedLiveAgain=" + nested);
        System.out.println("equalClosed=" + source.subSet(32, true, 32, true));
        System.out.println("equalHalfOpen=" + source.subSet(32, true, 32, false));
    }
}
```

Run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 RangeSetDemo.java
java RangeSetDemo
```

Exact stdout:

```text
initial=[20, 30, 40]
legacy=[20, 30, 40]
headClosed=[10, 20]
tailOpen=[50]
contains50=false
remove50=false
add50=IllegalArgumentException
middle=[20, 25, 35, 40]
source=[10, 20, 25, 35, 40, 50, 60]
floor100=40
ceiling0=20
higher40=null
nested=[25, 35, 40]
sameExcludedEnd=[20, 25, 35, 40]
includeExcludedEnd=IllegalArgumentException
expandNested=IllegalArgumentException
wrongDirection=IllegalArgumentException
afterClear=[10, 50, 60]
nestedAfterClear=[]
liveAgain=[32]
nestedLiveAgain=[32]
equalClosed=[32]
equalHalfOpen=[]
```

### 3.1. Reading the Key Changes

`middle` starts with 20, 30, 40. The endpoint 50 is excluded, even though the source actually contains 50.

`middle.add(25)` adds 25 to the source tree. `middle.remove(30)` removes 30 from the source tree. Next, `source.add(35)` becomes visible in `middle`, while `source.add(60)` is outside the range so it only appears in `source`.

Updates through the source are not restricted by the view. Whoever holds `source` still has access to the entire tree; creating `middle` does not “lock” the source to `[20, 50)`.

Another common point of confusion is: **restricting where results can be found is different from restricting the query argument**. `middle.floor(100)` is valid and returns 40, the largest element currently in the view that does not exceed 100. `middle.ceiling(0)` returns 20. Neither is allowed to return elements outside the view, even though the source contains other elements.

`middle.higher(40)` returns `null` because there is no element after 40 within the range. It does not reach into the source to return 50.

### 3.2. Querying, Removing, and Inserting Out of Range Do Not Have the Same Outcome

In the program, the arguments are valid `Integer` values under natural ordering:

| Operation on `middle = [20, 50)` | Result | Source modified? |
|---|---|---|
| contains(50) | false | No |
| remove(50) | false | No |
| add(50) | IllegalArgumentException | Does not add 50 through the view |
| floor(100) | Matching element in the view, here 40 | No |
| clear() | Removes all elements currently in the view | Yes |

The fact that 50 already exists in `source` does not make `add(50)` through `middle` valid. Insertion is checked against the range of the receiver object.

This table does not mean that any arbitrary argument is accepted: an incomparable type or `null` not supported by the comparator can still throw an exception. Do not generalize the `Integer` results into “all out-of-bounds queries are safe”.

The specification for [TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html#subSet(E,boolean,E,boolean)) range methods confirms that the view is backed by the source and rejects insertions outside the range.

### 3.3. What Does clear() Remove?

`middle.clear()` does not merely empty an intermediate object. It removes elements 20, 25, 35, 40 from the source structure. Elements outside the range—10, 50, 60—remain.

`nested` is backed by the same data, so it immediately becomes empty. Later, `source.add(32)` makes both `middle` and `nested` show 32 again. The bounds of both views still exist even when the data currently matching them is empty.

That is why `clear()` should never be described as “clearing a filter” or “disconnecting a view”. To disconnect, you must copy into another structure.

## 4. Nested Ranges: Checked Narrowing, Not Automatic Clamping

Consider `middle` already bounded to `[20, 50)`, followed by `middle.tailSet(25, true)`. `nested` gets the interval `[25, 50)`. It has no separate data structure; source updates and related views still share the underlying data.

However, you cannot request a sub-view with an endpoint outside the parent view’s bounds and expect Java to automatically take the intersection:

- `middle.headSet(70, false)` throws `IllegalArgumentException`.
- `middle.tailSet(10, true)` also requests an endpoint outside the parent range and is invalid.
- `middle.headSet(50, false)` is valid: it keeps 50 excluded.
- `middle.headSet(50, true)` is invalid: it asks to include the very endpoint the parent excluded.

Those last two calls are especially helpful for understanding bounds. An endpoint sitting right on the parent’s open boundary can be used as the child’s open boundary; asking to include that endpoint exceeds what the parent allows.

Even if the source does not currently contain 50, `includeExcludedEnd` still fails. The constraint is based on the declared bounds, regardless of whether any violating key/element exists at the time the view is created.

To combine two arbitrary business intervals, compute the intersecting bounds yourself using the same Comparator and handle the empty-intersection case first, or create the view from a sufficiently wide source using the final validated bounds. Do not treat chained `headSet()`/`tailSet()` calls as automatic intersection for arbitrary endpoints.

The corresponding rules apply to `subMap`/`headMap`/`tailMap` on TreeMap ranges. The bounds specification in [NavigableMap.subMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html#subMap(K,boolean,K,boolean)) is the basis for failing on out-of-range bounds right at view creation.

## 5. TreeMap: Selection by Key, Updates Across the Mapping

With TreeMap, the range applies to **keys**. For example, an order lookup table keyed by order ID might use `[100, 300)` to view orders with IDs from 100 to 299. Whether the value is labeled “outside range”, “priority”, or has a large or small monetary amount does not affect whether the mapping is selected.

This program also demonstrates a reversed view of a range, a key-set view, and an unmodifiable wrapper.

File **RangeMapDemo.java**:

```java
import java.util.Collections;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;

public class RangeMapDemo {
    private static void expectIAE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> source = new TreeMap<>();
        source.put(50, "outside-low");
        source.put(100, "A");
        source.put(200, "B");
        source.put(300, "outside-high");

        NavigableMap<Integer, String> window =
                source.subMap(100, true, 300, false);
        System.out.println("initial=" + window);
        System.out.println("get300=" + window.get(300));
        System.out.println("remove300=" + window.remove(300));
        System.out.println("sourceKeeps300=" + source.containsKey(300));
        expectIAE("put300", () -> window.put(300, "blocked"));

        window.put(150, "C");
        window.put(100, "A2");
        source.put(250, "D");
        source.put(375, "outside-later");
        System.out.println("updated=" + window);

        NavigableMap<Integer, String> reverse = window.descendingMap();
        System.out.println("reverse=" + reverse);
        System.out.println("reverseKeys=" + reverse.navigableKeySet());
        System.out.println("reverseValues=" + reverse.values());
        System.out.println("reverseHead200=" + reverse.headMap(200, false));
        System.out.println("reverseFloor175=" + reverse.floorKey(175));
        System.out.println("reverseCeiling175=" + reverse.ceilingKey(175));

        System.out.println("pollReverseFirst=" + reverse.pollFirstEntry());
        System.out.println("afterPoll=" + window);
        NavigableSet<Integer> keys = window.navigableKeySet();
        keys.remove(150);
        System.out.println("afterKeyRemoval=" + window);

        NavigableMap<Integer, String> readOnly =
                Collections.unmodifiableNavigableMap(window);
        source.put(175, "E");
        System.out.println("readOnlyLive=" + readOnly);
        System.out.println("firstOutside=" + source.firstEntry());
        window.clear();
        System.out.println("afterWindowClear=" + source);
        System.out.println("readOnlyAfterClear=" + readOnly);
    }
}
```

Compile and run commands:

```shell
javac --release 21 -encoding UTF-8 RangeMapDemo.java
java RangeMapDemo
```

Exact stdout:

```text
initial={100=A, 200=B}
get300=null
remove300=null
sourceKeeps300=true
put300=IllegalArgumentException
updated={100=A2, 150=C, 200=B, 250=D}
reverse={250=D, 200=B, 150=C, 100=A2}
reverseKeys=[250, 200, 150, 100]
reverseValues=[D, B, C, A2]
reverseHead200={250=D}
reverseFloor175=200
reverseCeiling175=150
pollReverseFirst=250=D
afterPoll={100=A2, 150=C, 200=B}
afterKeyRemoval={100=A2, 200=B}
readOnlyLive={100=A2, 175=E, 200=B}
firstOutside=50=outside-low
afterWindowClear={50=outside-low, 300=outside-high, 375=outside-later}
readOnlyAfterClear={}
```

### 5.1. New Insertions and Value Replacements Both Flow Through the Same Window

`window` includes keys 100 and 200, and excludes key 300. `window.put(150, "C")` adds a mapping to `source`; `window.put(100, "A2")` replaces an existing value in `source`. `source.put(250, "D")` appears in `window`, while key 375 does not.

`window.get(300)` returns `null` and `window.remove(300)` returns `null` in this example, even though `source` actually has a mapping for 300. That key lies outside `window`’s perspective. By contrast, `window.put(300, ...)` is rejected because it attempts to write outside the range.

For a TreeMap that allows `null` values, `get()` returning `null` is not enough to distinguish “no mapping” from “mapping with a `null` value”. When you need to tell them apart in a view, call `containsKey()` on that view itself. Ranges do not alter this basic Map rule.

Do not rely on querying `source` to decide whether a key can be written through `window`. The condition is that the key falls within `window`’s range, even if `source` already contains that key.

### 5.2. A View of a View Still Modifies the Source

`reverse = window.descendingMap()` only changes the order of the `[100, 300)` window. When `reverse.pollFirstEntry()` is called, the “first” element in descending order is key 250. The mapping for 250 is removed from both `source` and `window`.

`keys = window.navigableKeySet()` is a view of the keys in that same range. `keys.remove(150)` removes the entire mapping for 150 from `source`. It does not leave a key with a `null` value behind.

This key set supports removal, but it does not support `add()`/`addAll()`: a key alone does not provide the value needed to add a mapping. Sharing the `NavigableSet` type does not mean every instance supports the same addition operations as `TreeSet`.

`reverse.values()` iterates values in descending key order; it does not sort values alphabetically or by a value Comparator. Thus `D, B, C, A2` is a consequence of the key order `250, 200, 150, 100`.

### 5.3. Unmodifiable Wrappers Do Not Stop Source Mutations

`readOnly` is created via `Collections.unmodifiableNavigableMap(window)`. It blocks update operations through the returned interface, but it does not hold a snapshot of `window`.

`source.put(175, "E")` still shows up in `readOnly`. After `window.clear()`, `readOnly` is empty. The program clearly distinguishes two different properties:

- **Cannot be modified through this reference**: a property of the wrapper.
- **Does not change when the source changes**: a property that requires a copy or a separate versioning mechanism.

The wrappers in [Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableNavigableMap(java.util.NavigableMap)) keep reads backed by the wrapped structure. Wrapping a view does not detach the data.

## 6. Reversing Order: Navigation Semantics Flip Too

### 6.1. descending and reversed

| Type | API available in Java 17 | API added in Java 21 | Return type |
|---|---|---|---|
| TreeSet/NavigableSet | descendingSet() | reversed() | NavigableSet |
| TreeMap/NavigableMap | descendingMap() | reversed() | NavigableMap |

In these two Navigable families, `reversed()` is equivalent to `descendingSet()`/`descendingMap()`. For TreeSet and TreeMap, the reversed view is backed by the source, so permitted updates continue to reflect in both directions. There is no need to iterate and re-insert everything just to read from end to start. The equivalence specification is in [NavigableSet.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html#reversed()) and [NavigableMap.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html#reversed()).

Do not infer from this specific property that every `reversed()` method on every Java collection has the same live-update guarantee. This lesson focuses on trees and their views.

Reversing twice restores the original order in behavior. Do not use reference comparison `==` as a correctness condition in your algorithm; the specification does not require every implementation to return the exact same object after two reversals.

### 6.2. “First” Means First According to the View’s Comparator

Suppose an ascending source contains 10, 20, 30, 40, 50. In the descending view:

| Call on the descending view | Result |
|---|---|
| first() | 50 |
| last() | 10 |
| headSet(30, false) | 50, 40 |
| tailSet(30, true) | 30, 20, 10 |
| lower(30) | 40 |
| higher(30) | 20 |
| floor(35) | 40 |
| ceiling(35) | 30 |

`lower(30)` returning 40 is not an arithmetic exception. In descending order, 40 comes before 30. `lower` finds the greatest element strictly less than the argument **under the active order**; in descending order, that result looks numerically larger.

Similarly, `floor(35)` moves toward elements not exceeding 35 in descending order, so it picks 40; `ceiling(35)` picks 30. To work these out yourself, write the iteration sequence down on paper before reading method names by intuition like “floor means smaller number”.

For a view `v` and its reversed view `d`, the following relationships help verify your reasoning, provided both cover the same current data range:

| On `d` | Equivalent on `v` |
|---|---|
| first | last |
| last | first |
| lower(x) | higher(x) |
| floor(x) | ceiling(x) |
| ceiling(x) | floor(x) |
| higher(x) | lower(x) |

For maps, substitute `firstKey`/`lastKey`, `lowerKey`/`higherKey`, and `floorKey`/`ceilingKey`; entry-returning methods flip in the same way. Results remain constrained to `v`’s range. Do not compare a descending view of a small range against the entire ascending source and apply the table mechanically.

### 6.3. Reversing a Tree That Already Has a Descending Comparator

`descendingSet()` does not mean “sort numbers descending” in an absolute sense. It reverses the **existing order**. If the original TreeSet uses `Comparator.reverseOrder()` for integers, the source order is already 50, 40, 30, 20, 10; its descending view will iterate 10, 20, 30, 40, 50.

The same holds for Comparators sorting codes, strings by length, or objects by timestamp. Identify the source’s comparator first; do not permanently equate the word `descending` with how values print.

## 7. Combining Ranges with Reversal: Swap Endpoints and Keep Their Flags

There are two ways to build a view for the same data interval:

1. Select the range on the source, then reverse the order.
2. Reverse the source, then select the range in the new order.

The second approach must swap the two endpoints. For an ascending source `s`, both illustrative snippets below select 20, 30, 40 and both iterate 40, 30, 20:

```java
// Illustrative snippet; s is an ascending NavigableSet<Integer>.
NavigableSet<Integer> a = s.subSet(20, true, 50, false).descendingSet();
NavigableSet<Integer> b = s.descendingSet().subSet(50, false, 20, true);
```

The “include 20” flag must stay attached to endpoint 20; the “exclude 50” flag must stay attached to endpoint 50. Swapping the endpoints without swapping their flags selects the wrong boundaries.

The expression `s.descendingSet().subSet(20, true, 50, false)` is no longer valid because 20 comes after 50 in descending order. Java does not automatically interpret those two numbers as “numeric lower/upper bounds”.

General rules for valid views and bounds:

| Created from reversed view of `s` | Equivalent view from `s` |
|---|---|
| descendingSet().subSet(b, bi, a, ai) | subSet(a, ai, b, bi).descendingSet() |
| descendingSet().headSet(k, inclusive) | tailSet(k, inclusive).descendingSet() |
| descendingSet().tailSet(k, inclusive) | headSet(k, inclusive).descendingSet() |

Maps follow the exact same transformation with `descendingMap`, `subMap`, `headMap`, and `tailMap`. For instance, `window.descendingMap().headMap(200, false)` in the earlier program leaves only key 250: “before 200” in descending order means the keys greater than 200 in `window`.

These equivalences describe contents, order, and shared backing data—they do not claim that the two expressions return the same object reference. Nor do they allow widening bounds beyond an already-restricted parent view.

A practical tip: if a business requirement is stated as an ascending numeric interval or an earliest-to-latest time window, it is usually clearer to create the range in that order first, then reverse it for display. Writing it that way keeps the business bounds easier to read.

## 8. Combined Program: Reversing Ranges and Copying in the Right Order

The complete example below tests:

- Two ways of creating the same reversed range view.
- `head`/`tail` and navigation operations in reversed order.
- A copy that preserves the Comparator versus a copy that uses natural ordering.
- Mutating the source without mutating the copy.
- The copy no longer carrying the original view’s range restriction.
- Rejecting explicit first/last positioning APIs on an order-determined structure.

File **ReverseRangeDemo.java**, requiring JDK 21 or later:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class ReverseRangeDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> source =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));
        NavigableSet<Integer> descending = source.reversed();
        NavigableSet<Integer> rangeThenReverse =
                source.subSet(20, true, 50, false).reversed();
        NavigableSet<Integer> reverseThenRange =
                descending.subSet(50, false, 20, true);

        System.out.println("descending=" + descending);
        System.out.println("rangeThenReverse=" + rangeThenReverse);
        System.out.println("reverseThenRange=" + reverseThenRange);
        System.out.println("sameMembers=" +
                rangeThenReverse.equals(reverseThenRange));
        System.out.println("head30=" + descending.headSet(30, false));
        System.out.println("tail30=" + descending.tailSet(30, true));
        System.out.println("lower30=" + descending.lower(30));
        System.out.println("higher30=" + descending.higher(30));
        System.out.println("floor35=" + descending.floor(35));
        System.out.println("ceiling35=" + descending.ceiling(35));

        TreeSet<Integer> sortedCopy = new TreeSet<>(rangeThenReverse);
        Collection<Integer> widened = rangeThenReverse;
        TreeSet<Integer> naturalCopy = new TreeSet<>(widened);
        List<Integer> listCopy = new ArrayList<>(rangeThenReverse);
        System.out.println("sortedCopy=" + sortedCopy);
        System.out.println("naturalCopy=" + naturalCopy);
        System.out.println("listCopy=" + listCopy);

        source.add(45);
        System.out.println("viewAfterAdd45=" + rangeThenReverse);
        System.out.println("copyAfterAdd45=" + sortedCopy);
        sortedCopy.add(100);
        System.out.println("copyOutsideFormerRange=" + sortedCopy);
        System.out.println("sourceHas100=" + source.contains(100));
        expectUOE("addFirst", () -> descending.addFirst(99));
        System.out.println("doubleReverseEquals=" +
                descending.reversed().equals(source));

        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableMap<Integer, String> mapView =
                map.subMap(10, true, 30, false).reversed();
        TreeMap<Integer, String> sortedMapCopy = new TreeMap<>(mapView);
        Map<Integer, String> widenedMap = mapView;
        TreeMap<Integer, String> naturalMapCopy = new TreeMap<>(widenedMap);
        System.out.println("mapView=" + mapView);
        System.out.println("sortedMapCopy=" + sortedMapCopy);
        System.out.println("naturalMapCopy=" + naturalMapCopy);
        map.put(15, "D");
        System.out.println("mapViewAfterPut15=" + mapView);
        System.out.println("mapCopyAfterPut15=" + sortedMapCopy);
        expectUOE("putFirst", () -> mapView.putFirst(12, "X"));
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 ReverseRangeDemo.java
java ReverseRangeDemo
```

Exact stdout:

```text
descending=[50, 40, 30, 20, 10]
rangeThenReverse=[40, 30, 20]
reverseThenRange=[40, 30, 20]
sameMembers=true
head30=[50, 40]
tail30=[30, 20, 10]
lower30=40
higher30=20
floor35=40
ceiling35=30
sortedCopy=[40, 30, 20]
naturalCopy=[20, 30, 40]
listCopy=[40, 30, 20]
viewAfterAdd45=[45, 40, 30, 20]
copyAfterAdd45=[40, 30, 20]
copyOutsideFormerRange=[100, 40, 30, 20]
sourceHas100=false
addFirst=UnsupportedOperationException
doubleReverseEquals=true
mapView={20=B, 10=A}
sortedMapCopy={20=B, 10=A}
naturalMapCopy={10=A, 20=B}
mapViewAfterPut15={20=B, 15=D, 10=A}
mapCopyAfterPut15={20=B, 10=A}
putFirst=UnsupportedOperationException
```

Matching iteration order between `rangeThenReverse` and `reverseThenRange` is visible directly in the two printed list lines. Note that `Set.equals()` only checks set membership, not iteration order; `sameMembers=true` alone does not prove the orders match.

`source.add(45)` appears in the view as `45, 40, 30, 20`. `sortedCopy` remains `40, 30, 20`. When `sortedCopy.add(100)` runs, 100 is accepted: it is now an independent TreeSet with a descending Comparator, no longer bound by the `[20, 50)` restriction of the original view.

In the map half, `map.put(15, "D")` updates `mapView` but does not update `sortedMapCopy`. A copy’s ordering and its link to the source are two separate properties that must be verified individually.

If you are on Java 17, use `descendingSet()`/`descendingMap()` to create reversed views. Do not call `reversed()`, `addFirst()`, or `putFirst()` from the Java 21 example on a Java 17 API baseline. Those newer APIs are not required to understand or use TreeSet/TreeMap ranges.

## 9. Copying a View: Preserving Contents, Order, or Constraints?

### 9.1. Constructors Taking SortedSet/SortedMap Preserve the Comparator

In `ReverseRangeDemo`:

- `rangeThenReverse` has type `NavigableSet`, which is a `SortedSet`, so `new TreeSet<>(rangeThenReverse)` selects the `SortedSet` constructor and preserves the view’s ordering.
- `widened` has type `Collection`, so `new TreeSet<>(widened)` selects the `Collection` constructor and uses natural ordering.
- `mapView` has type `NavigableMap`, which is a `SortedMap`, so `new TreeMap<>(mapView)` selects the `SortedMap` constructor and preserves the Comparator.
- `widenedMap` has type `Map`, so `new TreeMap<>(widenedMap)` selects the `Map` constructor and uses natural ordering of keys.

The same runtime object, yet **the declared type of the argument** causes a different constructor overload to be chosen at compile time. The printed outputs `[40, 30, 20]` and `[20, 30, 40]` make this difference clear.

For custom elements/keys that do not implement `Comparable`, accidentally selecting the natural-ordering constructor can also cause a `ClassCastException`, even when the source worked fine with its own Comparator.

If an input API only exposes `Collection` or `Map` and you want to preserve a custom order, you must pass the known Comparator explicitly into the target structure before adding the data. Do not guess a Comparator from a few printed elements.

### 9.2. Copying Does Not Copy the “Fence”

A new TreeSet built from a view does not retain the old bounds. Neither does a new TreeMap. The copy preserves the elements/mappings selected at copy time, and may preserve the comparator depending on the constructor, but it does not automatically inherit the restriction that only items within the original range may be inserted.

If you need an independent copy that still only allows edits within a range, that is a new requirement: create the independent structure and then create a range view on that independent structure itself, or encapsulate update methods with appropriate business validation.

Distinguish these goals:

| Goal | Choice |
|---|---|
| Update a subset of data directly in the source | Range view |
| Same source, read in reverse order | Reversed view |
| Independent data, still supporting ordered lookup | New TreeSet/TreeMap with the right Comparator |
| Keep the current traversal order as an independent sequence | New ArrayList from the set/view |
| Block edits through the returned reference while still tracking the source | Unmodifiable wrapper around the view |
| Stop tracking the source and block structural edits through the returned reference | Create an independent copy, then wrap the copy |

An `ArrayList` built from a view preserves the order in which elements were encountered at copy time, but it does not become a navigable set; it allows duplicates and does not automatically maintain order after subsequent additions. Copies made with `Set.copyOf()`/`Map.copyOf()` likewise make no promise to preserve a Comparator or tree navigation capabilities.

### 9.3. A Standard Copy Only Separates the Structure

Copying a `TreeMap<Integer, MutableValue>` into another `TreeMap` does not automatically clone the `MutableValue` instances. The two maps have separate mapping structures, yet they can still hold references to the exact same value objects.

Likewise, copying a set does not automatically clone each element. If you need a snapshot that is also independent in its internal state, choose immutable data or design an appropriate object-copying step. Do not call a structural copy “deeply immutable”.

Creating a copy and wrapping it with an unmodifiable wrapper is only enough to block structural updates through that wrapper. It does not make the contained objects immutable, nor does it guarantee a consistent snapshot if another thread is modifying the source without coordination.

## 10. Updating Through Views: A Range Is a Condition, Not a Transaction

### 10.1. Reversing Order Does Not Grant Arbitrary Positioning

Trees maintain order by comparison. Adding through a reversed view still uses `add()`/`put()`, with position determined by the Comparator, and must also satisfy the range if the view is bounded.

Java 21 adds `addFirst`/`addLast` on sequenced collections and `putFirst`/`putLast` on sequenced maps. TreeSet and TreeMap do not support such explicit positioning: those operations throw `UnsupportedOperationException`. Reversing the view does not change that rule.

In the program, `descending.addFirst(99)` and `mapView.putFirst(12, "X")` are both rejected. To add 12 to `mapView`, the proper operation is `put(12, "X")`, because 12 belongs to `[10, 30)`; it naturally appears after 15 and before 10 in the current descending order.

### 10.2. Removal Operations Can Affect a Large Part of Source Data

`remove()` is not the only method that modifies the source. The following operations, when supported by the structure/view, also affect the visible portion of the source:

- `clear()` removes the entire current range.
- `pollFirst()`/`pollLast()` on sets and `pollFirstEntry()`/`pollLastEntry()` on maps retrieve and remove the first/last item of the view.
- `removeIf()`, `retainAll()`, `removeAll()`, or removing through a set’s iterator can drop multiple elements within the range.
- Removing through a `subMap`’s key set or entry set can delete mappings in the source.

Returning a mutable view to a caller is therefore equivalent to granting write permission over part of your data. If a feature should only read, express that through an appropriate API or wrapper.

Entries returned by navigation methods such as `TreeMap.firstEntry()`/`floorEntry()` are snapshots of the mapping, not an arbitrary backdoor to call `setValue()` and update the tree. To change a value, use `put()` on the map or view with a valid key. Do not assume all `Map.Entry` instances have the same mutability behavior.

### 10.3. Do Not Assume Multi-Element Operations Roll Back on Error

An `addAll()`/`putAll()` call on a view may encounter an out-of-range element or key partway through. There is no transactional guarantee that all valid updates applied earlier will be rolled back if a later item fails.

For an “all valid or none updated” requirement, validate the entire input beforehand using the same bound/Comparator rules, then write under application-owned synchronization or transaction control. Checking and writing as separate steps also does not protect against concurrent modifications on its own.

Do not catch `IllegalArgumentException` and then assume the source was left untouched after a bulk operation. Depending on the algorithm used, the source may already have received partial updates.

A range is a condition for selecting data and validating write locations; it does not replace overall business constraints, error handling, or atomicity mechanisms.

## 11. Practical Limits When Holding and Iterating Views

### 11.1. Do Not Mutate Comparison Fields While Elements/Keys Are in the Tree

Ranges are determined by the tree’s ordering. If a `TreeSet` element or `TreeMap` key has a field used by the Comparator, mutating that field directly while the object is still in the tree can corrupt the structural ordering relative to the current state.

You cannot use a view to fix that situation. Prefer immutable elements/keys; if a sort attribute must change, remove the object through a valid operation first, update it, and re-insert it. The Comparator must also remain consistent for as long as the tree is in use.

Changing a field of a map value does not automatically change key-based range membership. If business logic needs to filter by a value’s attribute, `subMap` is not the right tool directly; you need an index keyed appropriately or a different filtering step.

### 11.2. A Live View Does Not Mean Iterators Tolerate Arbitrary Modifications

A view can still observe data after sequential updates to the source. However, an iterator currently traversing the source or view is a separate object from the view itself.

TreeSet and TreeMap are not thread-safe. Modifying the structure while iterating through another reference can cause the iterator to throw `ConcurrentModificationException`. This detection mechanism is best-effort bug detection, not a synchronization guarantee, and should never be used as a program correctness condition.

If you need to remove the current element during iteration and the iterator supports it, use `iterator.remove()`. For batch updates, it is usually easier to control if you identify the target items first and then perform the updates in a single step with clear ownership and synchronization.

Creating a reversed view, range view, or unmodifiable wrapper does not turn a `TreeMap` into a `ConcurrentNavigableMap`. Even a copy is only a reliable snapshot when reading the source during the copy is properly coordinated with writers.

### 11.3. Do Not Equate View Creation Cost with Data Processing Cost

Creating a view does not eagerly copy every element in the interval into a new tree. That makes views well suited for working with a window over live data.

However, iterating `k` elements still reads `k` elements; clearing a range may still have to remove many mappings; copying a range still builds a new structure containing the selected items. Do not assume `size()`, `clear()`, or every operation on a view is `O(1)`.

Nor should you treat a small view as a tiny independent cache: because the view stays linked to the source, holding onto it for a long time can keep the entire source structure alive in memory. If you only need a few historical items and want to release a large source, an explicit copy may express that intent much better.

## 12. Applying It: Time Windows and Batch Processing

Suppose a `TreeMap` stores events by `Instant`, where each key represents a point in time. The requirement “events from the start of the day, excluding the start of the next day, displayed newest first” has three clear steps:

1. Determine the two `Instant` bounds using the business time-zone rules.
2. Create `subMap(start, true, nextStart, false)` in ascending chronological order.
3. Take `descendingMap()` of that range to display in reverse order.

The half-open interval `[start, nextStart)` lets two consecutive days adjoin without both capturing an event on the boundary. You do not need to calculate “the last second” or “the last nanosecond” of the day. The specific timestamps must still be constructed in the right time zone; the range API does not handle calendar and time-zone conversions for the application.

Once you have the range, decide on update permissions:

- A screen that must track live data can use a view protected from edits on the reading side, backed by appropriate synchronization.
- A fixed report should create a copy at a controlled point in time.
- A cleanup job for old data can use `headMap(cutoff, false).clear()`, bearing in mind that this deletes source data before `cutoff` and requires proper business ownership.
- A task that claims the latest event in the window can call `pollFirstEntry()` on the descending view; after the call, that event is no longer in the source.

If multiple events share the same timestamp, `TreeMap<Instant, Event>` only holds one value per key under comparison. To keep all of them, use a list of events as the value or a composite key whose ordering also distinguishes by event ID. Views do not change key uniqueness.

A view’s bounds are fixed to the endpoints passed at creation. It does not automatically “slide with the clock” into a new day. For a “last 24 hours” window, you must recompute the endpoints as needed and create the corresponding view; liveness only means data within the current bounds remains shared with the source.

## 13. Mistakes to Spot When Reading Code

| Misconception / Wrong Choice | Consequence | How to Handle It |
|---|---|---|
| Treating `subSet`/`subMap` as a copy | Modifying the view unexpectedly mutates the source | Decide whether an independent structure is needed as soon as data is received |
| Assuming `subMap` filters by value | Selects the wrong set of mappings | Build a key/index for the attribute you need to query |
| Misremembering shorthand default bounds | Extra or missing data at boundaries | Use the boolean overloads when bounds must be explicit |
| Reversing order while keeping endpoint order unchanged | `IllegalArgumentException` | Swap endpoints and carry each endpoint’s include/exclude flag with it |
| Assuming `head` always means smaller numbers | Results on the opposite side of what was expected | Interpret `head` according to the active Comparator |
| Using a sub-view to automatically clamp an out-of-bounds range | Exception when creating the sub-view | Compute the intersection bounds or create from a sufficiently wide source |
| Assuming an empty view is detached from the source | New data appears unexpectedly | Distinguish currently empty views from copies |
| Thinking `clear()` only clears an intermediate object | Deletes real data in the source | Verify range and write permissions before clearing |
| Widening input type to `Collection`/`Map` when copying | Loses custom Comparator | Choose the `SortedSet`/`SortedMap` constructor or pass the Comparator explicitly |
| Assuming a copy still blocks elements outside the old range | Out-of-range data can be inserted | Re-apply the constraint on the independent structure if needed |
| Wrapping with `unmodifiable` and calling it a snapshot | Reads still change when the source changes | Copy first if you need to sever the link |
| Using `equals` to check Set/Map ordering | Different orders still compare equal | Compare iteration sequences when order matters |
| Relying on `ConcurrentModificationException` for coordination | Concurrent behavior lacks guarantees | Use proper ownership and synchronization mechanisms |

## 14. Self-Check Exercises and Solutions

### Exercise 1 — Four Bounds, Without Mutating Data

An ascending source contains 1, 2, 3, 4, 5, 6. Write the result in iteration order for:

1. `subSet(2, false, 5, true)`.
2. `headSet(3)`.
3. `tailSet(3)`.
4. `subSet(4, true, 4, true)`.
5. `subSet(4, false, 4, true)`.

**Solution:** `[3, 4, 5]`, `[1, 2]`, `[3, 4, 5, 6]`, `[4]`, `[]`, respectively. The last two cases share the same endpoint value but differ in whether it is included.

### Exercise 2 — Source and an Empty Range

The source contains 10, 50. Create `v = subSet(20, true, 40, false)`, then add 30 and 45 through the source. What is `v`? If `v.clear()` is called, what remains in the source?

**Solution:** `v` is initially empty, then shows `[30]` after the additions. 45 is outside the range. `v.clear()` removes 30 from the source, leaving `[10, 45, 50]`. The view still retains the `[20, 40)` range and remains connected.

### Exercise 3 — Open Parent Bound

`p` is the view `[10, 40)` on an ascending source. Compare `p.headSet(40, false)`, `p.headSet(40, true)`, and `p.headSet(50, false)`.

**Solution:** The first is valid and does not widen the range; the second tries to include 40, which the parent excluded; the third uses endpoint 50, which exceeds the parent’s upper bound. The latter two throw `IllegalArgumentException` rather than clamping back to `[10, 40)`.

### Exercise 4 — Equivalent Reversed Range

An ascending source `s` contains 10, 20, 30, 40, 50. To get the same data and order as `s.subSet(20, false, 50, true).descendingSet()`, write the equivalent expression starting from `s.descendingSet()`.

**Solution:** `s.descendingSet().subSet(50, true, 20, false)`, producing `[50, 40, 30]`. The `true` flag stays with 50; the `false` flag stays with 20. If you only swap the endpoints without moving the two flags, the boundary behavior will be wrong.

### Exercise 5 — Navigation in Descending Order

`d` is the descending view of an ascending source `[10, 20, 30, 40, 50]`. Evaluate `d.headSet(30, true)`, `d.floor(25)`, `d.ceiling(25)`, and the element removed by `d.pollLast()`.

**Solution:** `headSet` is `[50, 40, 30]`; `floor(25)` is `30`; `ceiling(25)` is `20`; `pollLast()` removes `10` from the source. The “last” element of `d` is the numerically smallest element in this example.

### Exercise 6 — TreeMap Selection by Key

The source contains `1→"Z"`, `2→"A"`, `3→"M"`. Create `w = subMap(1, true, 3, false)`, then read `w.descendingMap().values()`. If `w.navigableKeySet().remove(2)` is called, how does the source change?

**Solution:** The value sequence is `A, Z` because the keys are iterated in order `2, 1`. Removing key 2 through the key set deletes the entire mapping `2→"A"` from the source, leaving `1→"Z"` and `3→"M"`. Key 3 was never in `w`, even if its value were similar to one inside the range.

### Exercise 7 — Same View, Different Constructors

`rev` has type `NavigableSet<Integer>` and currently shows `[9, 7, 5]`. Compare `new TreeSet<>(rev)` with assigning `rev` to a `Collection<Integer>` variable and passing that variable to `new TreeSet<>(...)`.

**Solution:** The first selects the `SortedSet` constructor and preserves descending order; the second selects the `Collection` constructor and uses natural ordering, so it iterates `[5, 7, 9]`. Both detach the structure from the source; neither automatically preserves `rev`’s insertion bounds. Preserving the Comparator depends on which constructor overload is selected, not merely on the class name `TreeSet`.

### Exercise 8 — Choosing an API for Callers

A service stores a `TreeMap` by ID. Callers should only see the range `[100, 200)`, must not see data change after the call returns, and must not be able to modify the returned structure. Should it return `unmodifiableNavigableMap(source.subMap(...))` or create a copy and wrap it?

**Solution:** Create a copy of the range under consistent source-reading conditions, then wrap the copy. Wrapping the view alone blocks writes through that reference, but still exposes subsequent source updates. If the values are mutable objects, you must also decide whether to copy the values or switch to immutable data.

### Exercise 9 — Source Comparator Already Reversed

The source uses `Comparator.reverseOrder()` for `Integer` and contains 1, 2, 3, 4. What does `source.headSet(3, false)` show? What does `source.descendingSet().headSet(3, false)` show?

**Solution:** The source iterates `[4, 3, 2, 1]`, so `head` before 3 is `[4]`. The reversed view iterates `[1, 2, 3, 4]`, so `head` before 3 is `[1, 2]`. You cannot determine the correct result from the words `head` or `descending` alone while ignoring the receiver’s Comparator.

## 15. References for Further Verification

The explanations and programs in this lesson can be verified against the following official API contracts:

- [TreeSet — constructors, ranges, descendingSet, and operation bounds](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).
- [TreeMap — constructors, subMap, descendingMap, and navigation methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).
- [NavigableSet — explicit bounds and reversed since Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).
- [NavigableMap — key-based ranges and reversed views](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).
- [Collections — unmodifiable wrappers](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).
