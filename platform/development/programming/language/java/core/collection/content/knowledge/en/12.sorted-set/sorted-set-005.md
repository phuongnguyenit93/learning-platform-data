# first, last, headSet, tailSet, and subSet

## 1. Working with the endpoints and ranges of an ordered Set

Suppose an application stores unique price levels in sorted order. It needs to know the lowest level, the highest level, the levels before a threshold, or the levels between two thresholds. If the data is already in a sorted Set, there is no need to convert it to a List and scan it manually just to express those queries.

Five methods of `SortedSet` serve two groups of operations:

- `first()`, `last()`: read one element at either end according to the ordering.
- `headSet(...)`, `tailSet(...)`, `subSet(...)`: create a **range view** over the existing set.

The most common source of confusion is that the second group returns a view backed by the original data, not an independently filtered copy. When using `TreeSet`, valid modifications through the view can directly update the backing set.

This lesson uses `TreeSet` to demonstrate `SortedSet` and the `NavigableSet` overloads. API rules are referenced against [Java 17 SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html) and [Java 17 NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

Key terms to distinguish:

| Term | Meaning in this lesson |
|---|---|
| Backing set | The collection holding the data that a view is based on |
| View | A way to access the backing set with range bounds over the same underlying data |
| Lower bound, upper bound | The boundary markers limiting a range according to the Set's ordering |
| Closed bound, inclusive | Allows an element equivalent to the boundary marker |
| Open bound, exclusive | Excludes any element equivalent to the boundary marker |
| Copy, snapshot | A separate collection created from the data at the time of copying |

"Before", "after", "first", and "last" must always be read according to the **Set's ordering**, not assumed to mean ascending numerical order.

## 2. first and last: reading elements without removing them

For a Set in ascending integer order:

```text
[10, 20, 30, 40, 50]
 ^               ^
first           last
```

`first()` returns `10`, and `last()` returns `50`. Neither call removes them from the set.

These are not two indices of a List:

- `first` is the leading member according to the ordering.
- `last` is the trailing member according to the ordering.
- `SortedSet` does not provide `get(index)` merely because it has an ordering.
- In `TreeSet`, the first element is not necessarily the root node of the internal tree.

When called on a view, both methods consider only the members within that view. For example, for the range `[20, 50)` of the set above, `first` is `20` and `last` is `40`.

### 2.1. An empty set is a case that must be handled

`first()` and `last()` throw `NoSuchElementException` if the set under consideration is empty. The "set under consideration" can be a non-empty backing set whose range view currently has no members.

For example, the backing set contains `10, 20, 30`, while the range `[21, 29)` contains no elements. Calling `first` on that range still fails.

In single-threaded or properly coordinated code, you can check `isEmpty()` when having no data is a normal case. Do not assume that `first` returns `null` to signal emptiness. If a comparator permits a `null` member, `first` can return that member itself; that is still a non-empty case, not a signal of an empty set.

The `pollFirst` and `pollLast` methods of `NavigableSet` behave differently: they both retrieve and remove the element, returning `null` when none exists. Do not replace `first` with `pollFirst` merely to avoid an exception if you do not intend to mutate the data.

### 2.2. "Smallest" depends on the ordering relation

With a descending comparator, the traversal sequence can be:

```text
[50, 40, 30, 20, 10]
 ^               ^
first           last
```

Here, `first()` returns the numerically largest value. Therefore, calling `first` "the first element according to the comparator" is more accurate than always calling it "the smallest number".

## 3. The three default range forms of SortedSet

First, consider natural ascending order with the set:

```text
S = [10, 20, 30, 40, 50]
```

The overloads without boolean flags have fixed rules:

| Call | Ordering condition | Interval notation | Example |
|---|---|---|---|
| `S.headSet(b)` | Elements strictly before b | `(-∞, b)` | `headSet(30)` → `[10, 20]` |
| `S.tailSet(a)` | Elements from a onward, including a | `[a, +∞)` | `tailSet(30)` → `[30, 40, 50]` |
| `S.subSet(a, b)` | From a up to before b | `[a, b)` | `subSet(20, 50)` → `[20, 30, 40]` |

The infinity symbol here only describes the unbounded side; there does not need to be an "infinity" object in the Set.

Two rules to remember as plain statements:

- `headSet` by default **excludes the upper bound**.
- `tailSet` by default **includes the lower bound**.

Because of this, `headSet(x)` and `tailSet(x)` partition the set into two non-overlapping parts at the same marker. If a member equivalent to `x` exists, it belongs to the tail side.

For `subSet(a, b)`, the start is closed and the end is open. This is a half-open interval, which is often convenient when partitioning adjacent regions.

### 3.1. Bounds are comparison markers, not required members

With `S = [10, 20, 30, 40, 50]`:

```text
headSet(25)      -> [10, 20]
tailSet(25)      -> [30, 40, 50]
subSet(25, 45)   -> [30, 40]
```

The absence of `25` or `45` in the Set still produces valid ranges. The endpoints are used for comparison, not as a requirement to locate two stored objects and slice by their positions.

Therefore, there is no need to call `contains(a)` or `contains(b)` as a prerequisite before creating a `subSet`. What you need to ensure is that the endpoints are comparable, in valid order, and within the limits of any parent view.

### 3.2. A valid range can still be empty

`subSet(21, 29)` on the set above is valid, even though it currently has no elements. That is different from passing invalid arguments.

If `25` is later added to the backing set, the `[21, 29)` view can see it. The two bounds remain fixed; the current contents change along with the backing set.

With `subSet(30, 30)`, the interval is `[30, 30)`: no value is both from 30 onward and strictly before 30. That range is empty even when the backing set contains `30`.

## 4. Program 1: default bounds and endpoints

Save the file `SortedSetBoundsDemo.java`:

```java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedSetBoundsDemo {
    public static void main(String[] args) {
        SortedSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));

        System.out.println("values = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("after first and last = " + values);
        System.out.println("headSet 30 = " + values.headSet(30));
        System.out.println("tailSet 30 = " + values.tailSet(30));
        System.out.println("subSet 20 to 50 = " + values.subSet(20, 50));
        System.out.println("headSet 25 = " + values.headSet(25));
        System.out.println("tailSet 25 = " + values.tailSet(25));
        System.out.println("subSet 25 to 45 = " + values.subSet(25, 45));

        SortedSet<Integer> empty = values.subSet(30, 30);
        System.out.println("equal endpoints = " + empty);
        System.out.println("equal endpoints empty = " + empty.isEmpty());

        try {
            empty.first();
        } catch (NoSuchElementException ex) {
            System.out.println("empty first = "
                    + ex.getClass().getSimpleName());
        }
        try {
            empty.last();
        } catch (NoSuchElementException ex) {
            System.out.println("empty last = "
                    + ex.getClass().getSimpleName());
        }
        try {
            values.subSet(50, 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("reversed endpoints = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 SortedSetBoundsDemo.java
java SortedSetBoundsDemo
```

Verified run output:

```text
values = [10, 20, 30, 40, 50]
first = 10
last = 50
after first and last = [10, 20, 30, 40, 50]
headSet 30 = [10, 20]
tailSet 30 = [30, 40, 50]
subSet 20 to 50 = [20, 30, 40]
headSet 25 = [10, 20]
tailSet 25 = [30, 40, 50]
subSet 25 to 45 = [30, 40]
equal endpoints = []
equal endpoints empty = true
empty first = NoSuchElementException
empty last = NoSuchElementException
reversed endpoints = IllegalArgumentException
```

The code uses language features and APIs available in Java 17 and later. The programs in this lesson were compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

Points to check against the output:

1. After `first` and `last`, the set remains unchanged.
2. `headSet(30)` excludes 30, while `tailSet(30)` includes 30.
3. `subSet(20, 50)` includes 20 but excludes 50.
4. Absent bounds like 25 or 45 do not cause an error by themselves.
5. Equal endpoints with the default overload produce an empty range.
6. Reversing the two endpoints in ascending order throws `IllegalArgumentException`.

Do not catch all of these situations with a single generic "no data" handler. An empty range, an empty set, and invalid arguments are distinct states with different meanings.

## 5. NavigableSet lets you choose closed or open bounds

The boolean overloads let you explicitly express whether each bound is included:

```java
headSet(toElement, inclusive)
tailSet(fromElement, inclusive)
subSet(fromElement, fromInclusive, toElement, toInclusive)
```

These are call-pattern signatures for illustration, not standalone method declarations in a program.

The corresponding two-sided interval forms:

| Call | Interval type |
|---|---|
| `subSet(a, true, b, false)` | `[a, b)` |
| `subSet(a, true, b, true)` | `[a, b]` |
| `subSet(a, false, b, false)` | `(a, b)` |
| `subSet(a, false, b, true)` | `(a, b]` |

On the set `[10, 20, 30, 40, 50]`, the range `(20, 50]` is `[30, 40, 50]`.

Do not try to simulate a closed upper bound by adding `1` to the upper marker for arbitrary data types. That can overflow with integers, does not apply directly to strings, and does not generalize across time domains. The boolean overloads state the intent directly without inventing a "next value".

### 5.1. Which forms are equivalent to the default overloads?

For a `NavigableSet`, the legacy calls can be understood as:

```text
headSet(b)       is equivalent to headSet(b, false)
tailSet(a)       is equivalent to tailSet(a, true)
subSet(a, b)     is equivalent to subSet(a, true, b, false)
```

The equivalence here is in the range expressed. The declared return type of the legacy overloads in Java 17 remains `SortedSet`; the flag-based overloads return `NavigableSet`.

Example:

```java
// Excerpt; requires importing java.util.NavigableSet, SortedSet, and TreeSet.
NavigableSet<Integer> values = new TreeSet<>();

SortedSet<Integer> defaultRange = values.subSet(20, 50);
NavigableSet<Integer> explicitRange =
        values.subSet(20, true, 50, false);
```

If a variable is typed only as `SortedSet`, you cannot call the boolean overloads directly through that variable. Declare the type that matches the capabilities you need, rather than arbitrarily casting an arbitrary `SortedSet` to `NavigableSet`.

### 5.2. Equivalent endpoints are not always empty

When the two endpoints are equivalent according to the comparator:

- The `[a, a]` form can contain a member equivalent to `a`.
- Any form with at least one open side is empty.

If no member equivalent to `a` is present yet, the `[a, a]` view is initially empty, but it can allow adding an equivalent member later. By contrast, `[a, a)` has no valid position for insertion.

"Equal" here must be interpreted as a comparison result of `0`, not merely reference identity or `equals` returning `true`.

## 6. Program 2: inclusive/exclusive bounds and nested views

Save the file `NavigableSetInclusiveDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableSetInclusiveDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));

        System.out.println("head 30 exclusive = "
                + values.headSet(30, false));
        System.out.println("head 30 inclusive = "
                + values.headSet(30, true));
        System.out.println("tail 30 exclusive = "
                + values.tailSet(30, false));
        System.out.println("tail 30 inclusive = "
                + values.tailSet(30, true));
        System.out.println("sub (20, 50] = "
                + values.subSet(20, false, 50, true));
        System.out.println("sub [30, 30] = "
                + values.subSet(30, true, 30, true));
        System.out.println("sub [30, 30) = "
                + values.subSet(30, true, 30, false));
        System.out.println("sub (30, 30) = "
                + values.subSet(30, false, 30, false));

        NavigableSet<Integer> parent = values.subSet(20, false, 50, false);
        System.out.println("parent (20, 50) = " + parent);
        System.out.println("child excludes parent endpoint = "
                + parent.headSet(50, false));
        try {
            parent.headSet(50, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("child includes excluded parent endpoint = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 NavigableSetInclusiveDemo.java
java NavigableSetInclusiveDemo
```

Verified run output:

```text
head 30 exclusive = [10, 20]
head 30 inclusive = [10, 20, 30]
tail 30 exclusive = [40, 50]
tail 30 inclusive = [30, 40, 50]
sub (20, 50] = [30, 40, 50]
sub [30, 30] = [30]
sub [30, 30) = []
sub (30, 30) = []
parent (20, 50) = [30, 40]
child excludes parent endpoint = [30, 40]
child includes excluded parent endpoint = IllegalArgumentException
```

The first four lines only vary the inclusive flag, yet they change whether the element at marker `30` is retained. This is a common off-by-one bug when reading only the method name `headSet` or `tailSet` and overlooking which overload is being called.

The two-equal-endpoints section shows that `[30, 30]` retains `30`, whereas `[30, 30)` and `(30, 30)` are empty.

### 6.1. A child range cannot widen its parent range

The parent range in the program is `(20, 50)`, currently containing `[30, 40]`.

The call:

```java
parent.headSet(50, false)
```

keeps the same open upper limit, so it is valid. However:

```java
parent.headSet(50, true)
```

requests a closed bound at `50`, whereas `50` itself is excluded by the parent range. This case is rejected with `IllegalArgumentException`.

What gets checked is the **allowed range**, not just the elements currently present. Even though in the current example both requests appear as if they would print the same `[30, 40]`, the second request still attempts to include an endpoint that the parent does not permit.

### 6.2. Do not assume nested ranges automatically intersect

If the parent range is `[20, 50)`, calling `parent.headSet(60)` does not mean "just take all elements of the parent because they are all less than 60". The new bound falls outside the parent's range and can be rejected.

Determine the appropriate bounds before calling. If the goal is the intersection of two independent conditions, compute the intersected bounds according to the comparator along with their inclusive/exclusive flags, then create a range within the valid limits.

Endpoints that land right on an open bound of the parent require special care: whether you ask to include or exclude that endpoint can determine whether the call is valid, as the program just demonstrated.

## 7. Backed views: same data, with a range fence

An easy mental model is:

```text
backing set: 10  20  30  40  50  60
                 |----------|
view:           [20, 50)

There is no separate copy of 20, 30, 40.
The view only allows working with the corresponding region on the same data.
```

By the contract of `SortedSet`'s range-view methods, the view is backed by the original set: changes made through one side are reflected on the other. This includes data added or removed after the view was created.

With a modifiable `TreeSet`:

- Adding an in-range value to the backing set makes it visible in the view.
- Removing an in-range value through the view removes it from the backing set.
- Adding a valid in-range value through the view adds it to the backing set.
- Adding an out-of-range value through the view is rejected.
- Calling `clear()` on the view removes the members currently in the range from the backing set.

A view does not automatically mean read-only. Nor does it mean an independent data table.

### 7.1. Fixed bounds, mutable contents

Creating `window = root.subSet(20, true, 50, false)` establishes the range `[20, 50)`. If `25` or `35` is added to `root`, `window`'s contents change, but its two bounds do not automatically shift.

If all elements currently in the range are removed, `window` can become empty. Afterward, adding a valid value through `root` or `window` can populate it again.

Do not use `window.first()` and `window.last()` as a way to recover the declared bounds. They return the currently present elements, which may differ from the bounds and may not exist at all when the range is empty.

### 7.2. Inserting out of range differs from absence of a member

In an integer view `[20, 50)`, adding `50` violates the open upper bound and throws `IllegalArgumentException`. The fact that `root` already contains `50` does not make that call valid.

For a value that is validly comparable but lies outside the range, membership queries or removals simply do not find it in the view. Do not equate that with permission to insert out-of-range values.

Type mismatches or `null` when unsupported by the comparator are separate issues; do not rely on out-of-range rules to skip valid comparability checks.

### 7.3. clear does not detach the view variable

`window.clear()` does not mean "unbind the `window` variable and leave `root` untouched". It is a collection mutation: it removes the elements belonging to `window`.

Afterward, `window` still represents the same range view over the same `root`. If you need to drop the reference to the view, that is a variable-management step; if you need to keep separate data and clear it locally, you must create an appropriate copy first.

## 8. Program 3: mutating through the view and through the backing set

Save the file `BackedRangeViewDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class BackedRangeViewDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> root =
                new TreeSet<>(List.of(10, 20, 30, 40, 50, 60));
        NavigableSet<Integer> window = root.subSet(20, true, 50, false);

        System.out.println("initial window = " + window);
        root.add(35);
        System.out.println("after root add 35 = " + window);

        System.out.println("window remove 30 = " + window.remove(30));
        System.out.println("root after remove = " + root);
        System.out.println("window add 25 = " + window.add(25));
        System.out.println("root after add = " + root);

        TreeSet<Integer> snapshot = new TreeSet<>(window);

        try {
            window.add(50);
        } catch (IllegalArgumentException ex) {
            System.out.println("add excluded endpoint = "
                    + ex.getClass().getSimpleName());
        }
        try {
            window.headSet(60);
        } catch (IllegalArgumentException ex) {
            System.out.println("widen child bound = "
                    + ex.getClass().getSimpleName());
        }

        root.remove(20);
        System.out.println("window after root remove 20 = " + window);
        System.out.println("snapshot after root remove = " + snapshot);

        window.clear();
        System.out.println("root after window clear = " + root);
        System.out.println("window after clear = " + window);
        System.out.println("snapshot after clear = " + snapshot);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 BackedRangeViewDemo.java
java BackedRangeViewDemo
```

Verified run output:

```text
initial window = [20, 30, 40]
after root add 35 = [20, 30, 35, 40]
window remove 30 = true
root after remove = [10, 20, 35, 40, 50, 60]
window add 25 = true
root after add = [10, 20, 25, 35, 40, 50, 60]
add excluded endpoint = IllegalArgumentException
widen child bound = IllegalArgumentException
window after root remove 20 = [25, 35, 40]
snapshot after root remove = [20, 25, 35, 40]
root after window clear = [10, 50, 60]
window after clear = []
snapshot after clear = [20, 25, 35, 40]
```

Read this stage by stage.

### 8.1. Adding through root changes window

Initially `window` is `[20, 30, 40]`. After `root.add(35)`, `window` becomes `[20, 30, 35, 40]`. No call was made to recreate the `subSet`.

That is direct proof of backing linkage. If you want a report that preserves the exact data at the start time, holding only the `window` variable is not enough.

### 8.2. Removing and adding through window changes root

`window.remove(30)` removes `30` from `root`. `window.add(25)` adds `25` to `root`. Both operations act on the underlying data.

Next, `window.add(50)` is rejected because `50` is an excluded upper bound. This error does not widen the range.

The call `window.headSet(60)` is also rejected: a child view cannot request a bound beyond its parent view.

### 8.3. A snapshot has its own lifecycle

The program creates:

```java
TreeSet<Integer> snapshot = new TreeSet<>(window);
```

At that moment, `snapshot` contains `[20, 25, 35, 40]`. When `root` removes `20`, `window` loses `20` while `snapshot` keeps `20`.

After `window.clear()`, `root` has only `[10, 50, 60]`: the elements in the range have been removed. `snapshot` remains `[20, 25, 35, 40]`.

Because the elements are immutable `Integer`s, this example makes it easy to observe the independence of the two containers without the added complication of sharing mutable objects.

## 9. Every bound is interpreted by the comparator

Suppose `cmp(x, y)` is the Set's comparison function. When no explicit comparator is present, treat it as natural-order comparison.

The general rules can be written as:

```text
headSet(b):       cmp(x, b) < 0
tailSet(a):       cmp(x, a) >= 0
subSet(a, b):     cmp(x, a) >= 0 and cmp(x, b) < 0
```

With a descending comparator, "x comes before b" can mean `x` is numerically greater than `b`.

The validity condition for two endpoints is also that `a` does not come after `b` according to the comparator, not always `a <= b` numerically.

### 9.1. Reading head and tail on a concrete sequence

Given a sequence ordered by the comparator:

```text
50, 40, 30, 20, 10
```

- Head before marker `30` is `50, 40`.
- Tail from marker `30` is `30, 20, 10`.
- Range from `40` up to before `20` is `40, 30`.

A practical habit is to write the sequence in the Set's actual order and mark the endpoints on that sequence, rather than always drawing an ascending number line.

### 9.2. Bounds on domain objects

If the comparator inspects one attribute, the bound is also interpreted through that attribute. For example, if the comparator only compares scores, a bound object can be equivalent under the comparison rule to multiple objects with the same score.

However, `TreeSet` keeps only one member per equivalence class defined by the comparator. If you need to keep multiple people with the same score, you must design an appropriate tie-breaker or use a different data model.

How the comparator defines equivalence affects both set membership and whether an element sits on a bound. Do not assume a bound is matched only when an object has the exact same reference as the endpoint.

## 10. Program 4: ranges in descending order

Save the file `ReverseRangeBoundsDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class ReverseRangeBoundsDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(Comparator.reverseOrder());
        values.addAll(List.of(10, 20, 30, 40, 50));

        System.out.println("reverse values = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("headSet 30 = " + values.headSet(30));
        System.out.println("tailSet 30 = " + values.tailSet(30));
        System.out.println("subSet 40 to 20 = " + values.subSet(40, 20));
        System.out.println("subSet inclusive endpoints = "
                + values.subSet(40, true, 20, true));

        NavigableSet<Integer> view = values.subSet(40, true, 20, false);
        TreeSet<Integer> snapshot = new TreeSet<>(view);
        System.out.println("snapshot preserves order = " + snapshot);
        values.remove(30);
        System.out.println("view after root remove = " + view);
        System.out.println("snapshot after root remove = " + snapshot);

        try {
            values.subSet(20, 40);
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong comparator endpoint order = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ReverseRangeBoundsDemo.java
java ReverseRangeBoundsDemo
```

Verified run output:

```text
reverse values = [50, 40, 30, 20, 10]
first = 50
last = 10
headSet 30 = [50, 40]
tailSet 30 = [30, 20, 10]
subSet 40 to 20 = [40, 30]
subSet inclusive endpoints = [40, 30, 20]
snapshot preserves order = [40, 30]
view after root remove = [40]
snapshot after root remove = [40, 30]
wrong comparator endpoint order = IllegalArgumentException
```

Here, `first` is `50` and `last` is `10`. `headSet(30)` contains `[50, 40]`, completely different from the assumption that "head is always the smaller numbers".

The call `subSet(40, 20)` is valid because `40` comes before `20` under the descending comparator. Conversely, `subSet(20, 40)` reverses the endpoint order under the comparator and throws `IllegalArgumentException`.

The inclusive flags keep their exact meaning: `subSet(40, true, 20, true)` includes both ends, producing `[40, 30, 20]`.

The snapshot is created from a variable of type `NavigableSet`. `TreeSet`'s constructor taking a `SortedSet` preserves the ordering relation, so `snapshot` still traverses `[40, 30]`. When `30` is removed from the backing set, `view` has only `40` left while `snapshot` remains unchanged.

This example connects two independent decisions:

1. Do you want a view or a copy?
2. Which comparator do you want to keep?

Choosing a copy while accidentally changing the comparator can produce results different from your intent, even with the same input data.

## 11. Creating a copy and preserving the ordering

### 11.1. Copying from a SortedSet

If the source variable has type `SortedSet` or a suitable subtype:

```java
// Illustrative excerpt; view has type SortedSet<Integer>.
SortedSet<Integer> snapshot = new TreeSet<>(view);
```

The `TreeSet(SortedSet)` constructor uses the same ordering as the source. This is a concise way to create a separate set from an ordered range.

However, pay attention to the static type at the overload call site:

```java
// Excerpt illustrating overload differences.
SortedSet<Integer> orderedView = view;
Collection<Integer> generalCollection = orderedView;

TreeSet<Integer> sameOrder = new TreeSet<>(orderedView);
TreeSet<Integer> naturalOrder = new TreeSet<>(generalCollection);
```

Imports are omitted from the excerpt. The constructor taking `Collection` sorts by natural order, whereas the constructor taking `SortedSet` preserves the `SortedSet`'s ordering. If the source is descending, the two copies can traverse differently. If the elements lack a suitable natural order, calling via `Collection` can even fail.

Do not choose an overload by guessing the runtime type. Java selects overloads from compile-time type information.

These constructors are documented in the [Java 17 TreeSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### 11.2. Passing the comparator explicitly

You can state the intent directly:

```java
// Excerpt; view is a SortedSet<Integer>.
TreeSet<Integer> snapshot = new TreeSet<>(view.comparator());
snapshot.addAll(view);
```

A comparator returning `null` means the source uses natural order; the corresponding constructor accepts that representation.

If you supply a different comparator, that is an intentional reorganization. Check whether the new comparator merges elements that the source kept distinct.

### 11.3. Read-only does not mean snapshot

An unmodifiable wrapper around a view can still see changes in the backing data. It restricts operations through the wrapper; it does not copy the underlying data.

If you need a snapshot that disallows additions or removals through the returned reference, combine copying with wrapping:

```java
// Excerpt; requires importing java.util.Collections.
SortedSet<Integer> snapshot =
        Collections.unmodifiableSortedSet(new TreeSet<>(view));
```

Here, constructing the new `TreeSet` separates the container; the wrapper restricts updates through this reference. The two steps serve different purposes.

### 11.4. Copying the container can still share elements

With a mutable element type, both the copy and the backing set can hold references to the same objects. Mutating an object's attributes can be observed in both places.

In particular, do not mutate attributes involved in the comparator while the object is inside a `TreeSet`. Having an extra container copy does not make the key immutable and can affect multiple structures at once.

If the goal is a stable business-data snapshot, determine whether each element also needs to be copied or converted into an immutable value.

## 12. Applying half-open intervals to partition data

The `[a, b)` interval is useful when partitioning adjacent regions:

```text
[a, b)    and    [b, c)
```

Marker `b` belongs only to the second region, so the two regions do not overlap at that boundary.

For example, when organizing dates or instants:

- From the start of a period up to before the start of the next period.
- From a score threshold upward up to before the next tier's threshold.
- Codes from a start marker up to before an end marker according to the comparator.

There is no need to subtract a tiny fraction from the upper bound to turn it into "the last possible instant". Expressing it with the next period's start and an open upper bound is clearer, especially when data resolution may change.

An excerpt for timestamps:

```java
// Illustrative excerpt; types are in java.time and java.util.
NavigableSet<Instant> times = new TreeSet<>();
Instant start = Instant.parse("2026-10-01T00:00:00Z");
Instant end = Instant.parse("2026-11-01T00:00:00Z");

NavigableSet<Instant> octoberUtc =
        times.subSet(start, true, end, false);
```

This is a range based on the stated UTC instants, not an automatic inference of a month in a local time zone. If the business rule defines a range in another time zone, compute the two instants correctly before querying the Set.

Also remember that a Set deduplicates by membership equality: a Set of instants cannot store multiple distinct events at the exact same instant. If you need all events, choose a distinguishing key or a structure mapping each instant to its events.

If the range is used as fixed report data, create a snapshot at the appropriate time. If it is used as an operational window over managed data, a backed view may fit the requirement better.

## 13. Understanding range costs and reference retention

In `TreeSet`, a range is built on an ordered tree structure. Creating a view does not mean immediately copying every element inside the range.

One implementation model is: the view holds a reference to the underlying data, the boundary markers, and the inclusive/exclusive flags, then constrains operations by them. The [OpenJDK 17 TreeMap source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java) shows how range views and bounded member lookups work.

### 13.1. Separating view creation cost from data reading cost

Suppose the backing set has `n` members, the range currently has `k` members, and comparison takes constant time:

| Action | Appropriate mental model |
|---|---|
| Creating a bounded view | Mainly records and validates bounds, not copying `k` elements |
| Finding the first or last element of the range in the tree | May require a bounded search path in the backing tree |
| Iterating over all `k` elements of the range | Must process the traversed elements; cannot be treated as free |
| Creating an independent copy | Must process and store the copy's members |
| Clearing the entire range | Multiple mutations to the backing data, not just dropping a view variable |

In standard tree analysis, iterating over a range can be understood as `O(log n + k)`: finding the starting point and then stepping through the matching elements. This is a structural analysis, not a guarantee that every `SortedSet` implementation has the exact same cost.

Likewise, do not infer that every method on a view is `O(1)` just because creating the view is lightweight.

### 13.2. Range size may require counting

A full `TreeSet` can maintain its member count directly. A range view does not necessarily have a dedicated counter that stays updated across every change to the underlying data.

In the OpenJDK 17 implementation, computing the size of a range may require traversing to count, and the result may be cached under certain conditions. Do not write algorithms that call `view.size()` repeatedly while assuming every call is constant-time.

If you only need to know whether there is any data, `isEmpty()` expresses the intent better than fetching `size()` and comparing to `0`. Exact costs still depend on the implementation and the view.

### 13.3. A small view can keep the backing set alive

Because a view is linked to the underlying structure, holding onto a range with only a few elements for a long time can simultaneously retain a reference to a much larger backing dataset.

If you need to keep a small result long-term without needing it to track source changes, a separate copy can be better for both semantics and memory lifecycle.

This does not mean you must always copy. A view is appropriate when you need live linkage; a copy is appropriate when you need to decouple lifecycles. Choose based on usage requirements, not just fewer lines of code.

## 14. Exceptions, iterators, and non-atomic operations

### 14.1. Distinguishing error types

| Situation | Expected behavior |
|---|---|
| `first` or `last` on an empty range | `NoSuchElementException` |
| Reversed bounds according to the comparator | `IllegalArgumentException` |
| Adding outside the bounds of a `TreeSet` range | `IllegalArgumentException` |
| Requesting a child range beyond the parent's scope | May be rejected with `IllegalArgumentException` |
| Value not comparable by the set's rules | May throw `ClassCastException` |
| `null` when the comparison rule does not support it | May throw `NullPointerException` |
| Updating through an unmodifiable collection | `UnsupportedOperationException` per its contract |

Do not treat the absence of a bound in the set as a reason to throw a custom error if the data domain and ordering are valid. A comparison marker is not a "this element must exist" requirement.

### 14.2. Iterators are not snapshots

If you are iterating over a `TreeSet` view and modify the structure through the backing set or another path, the iterator can detect the modification and throw `ConcurrentModificationException`.

Even a modification outside the range being iterated can affect the modification-detection mechanism of the same underlying structure. Do not design code around the assumption that "not changing elements inside the view guarantees the iterator is unaffected".

If you want to remove while iterating, use an update approach compatible with the iterator contract or separate the processing phases clearly. If you need a stable result list for independent traversal, create a copy.

Fail-fast is a best-effort bug-detection mechanism of the implementation, not a synchronization tool or a consistent-snapshot guarantee for multiple threads.

### 14.3. addAll and check sequences are not automatically transactional

When adding multiple values to a range, an out-of-bounds value can cause the call to fail after earlier valid values have already been added. Do not assume an exception means all changes were automatically rolled back.

If business logic requires all-or-nothing behavior, you need an explicit workflow: full validation, data preparation, and appropriate update coordination. Merely catching exceptions from `addAll` does not create atomicity.

Similarly, checking `!view.isEmpty()` and then calling `view.first()` are two separate operations. In uncoordinated multi-threaded code, the data can change between the two steps.

The examples in this lesson are single-threaded to clarify range semantics. A view's live linkage does not by itself provide thread safety.

## 15. Common mistakes to avoid

| Misconception or misuse | Problem | Fix |
|---|---|---|
| `headSet(x)` includes `x` | Default overload excludes the upper bound | Use `headSet(x, true)` if needed |
| `tailSet(x)` excludes `x` | Default overload includes the lower bound | Use `tailSet(x, false)` if needed |
| `subSet(a, b)` includes both ends | Default is `[a, b)` | Choose the explicit boolean overload |
| Bounds must exist in the set | Confuses comparison markers with members | Allow absent but valid bounds |
| `first` returns `null` when empty | API throws an exception when no element exists | Handle emptiness according to your semantics |
| `first` is always the smallest number | Ignores the comparator | Read according to the set's ordering |
| A range is a copy | Changes can propagate to the backing set | Create a separate collection when needed |
| `view.clear()` only clears temporary results | Actually removes backing data in the range | Clarify ownership before mutating |
| A child range auto-intersects with the parent | Out-of-scope bounds can be rejected | Compute and validate appropriate bounds |
| Adding 1 gives a closed upper bound | Can overflow or fail on other data domains | Use the inclusive flag |
| Keeping a read-only wrapper gives a snapshot | The source can still change | Copy first if fixed data is required |
| Copying via `Collection` preserves the comparator | `Collection` overload uses natural order | Keep `SortedSet` type or pass the comparator |
| Every `size` on a range is `O(1)` | May require traversal to count | Read the contract and analyze operations accurately |

A useful habit before writing a range query is to write down three lines:

```text
What ordering is being used?
Is each endpoint inclusive or exclusive?
Should the result be backed by the source or independent of it?
```

These three decisions usually explain most of the difference between code that looks right and code that meets the requirement.

## 16. Practice exercises

### Exercise 1: default ranges

Given `[5, 10, 15, 20, 25]` in natural order, predict `headSet(15)`, `tailSet(15)`, and `subSet(10, 25)`.

**Suggested answer:** `[5, 10]`, `[15, 20, 25]`, and `[10, 15, 20]`, respectively.

### Exercise 2: absent bounds

On the same set, is `subSet(11, 24)` valid, and what does it contain?

**Suggested answer:** valid, containing `[15, 20]`. The two endpoints do not need to be members.

### Exercise 3: including both ends

Write a range containing members from `10` to `20`, including both `10` and `20`.

**Suggested answer:** with a `NavigableSet` variable, use `subSet(10, true, 20, true)`.

### Exercise 4: three distinct empty concepts

Distinguish an empty backing set, a range that currently has no data, and the range `[a, a)`.

**Suggested answer:** all three may print `[]`, but they differ in underlying data and future insertion capability. A range with valid width can receive members when the source changes; a half-open range with two equivalent endpoints has no valid value it can contain.

### Exercise 5: mutating through a view

Create a `[10, 20)` view, then call `view.clear()`. What happens to the backing set?

**Suggested answer:** the backing set's members within that range are removed. Members outside the range remain; the view remains linked to the backing set.

### Exercise 6: descending order

Given `[25, 20, 15, 10, 5]` under a descending comparator, predict `headSet(15)` and `subSet(20, 5)`.

**Suggested answer:** `[25, 20]` and `[20, 15, 10]`. Bounds are interpreted according to the comparator, not ascending numerical conditions.

### Exercise 7: child range at an open bound

The parent range is `(10, 25)`. Compare `headSet(25, false)` with `headSet(25, true)`.

**Suggested answer:** the first request keeps the open upper bound and can succeed; the second tries to include a marker the parent excluded and is rejected. Do not judge validity solely by the currently present contents.

### Exercise 8: stable report data

A function returns a view of a set that continues to be updated. The caller wants a report that preserves the data at the time of the call. Is wrapping the view in an unmodifiable wrapper enough?

**Suggested answer:** not enough. You must decouple the data with a copy that preserves the comparator, and only then restrict updates if desired. For mutable elements, you must also decide the level of element copying needed.

### Exercise 9: reading the start of a range

The range `[11, 14)` currently contains no elements. Does calling `first()` automatically return `11` or the nearest member outside the range?

**Suggested answer:** no. `first()` only reads members currently inside the range and throws `NoSuchElementException` when the range is empty. If you need to find a neighboring element near a marker on the backing set, look at appropriate navigation methods such as `ceiling` or `higher`.

When implementing range operations, express the ordering, inclusivity, and data lifecycle accurately. That is the foundation for using the same API for endpoint reads, range queries, and bounded updates without misjudging what affects the backing set.
