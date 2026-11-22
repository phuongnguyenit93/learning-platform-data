# Closed–Open Boundaries, Null Policy, and Range Views

## 1. An Ordered Range Requires Three Separate Decisions

Suppose an application stores unique priority levels in a TreeSet. Some unspecified levels are represented by `null`. The application needs to retrieve levels from 10 up to (but excluding) 30 and allow updates within that region.

To operate on this correctly, three different questions must be answered:

1. **Ordering and null:** does the comparator accept `null`, and if so, does it place `null` before or after other values?
2. **Closed–open boundaries:** is a value equivalent to each endpoint included in the range?
3. **Range view:** is the result a view backed by the original data or an independent container?

Merely knowing that “TreeSet is sorted” does not answer those questions. A comparator that allows `null` does not mean every view of the Set allows adding `null`. A range that currently does not contain `null` also does not mean the comparator forbids it.

In this article, a **range view** is referred to as a **view over a range**: it accesses the same backing data but adds boundary constraints. It is not a copied list of results.

The rules used here are based on [Java 17 SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html), [Java 17 NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html), and the range methods of [Java 17 TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

A consistent way to read this is:

```text
element can be validly compared
    + position according to the comparator
    + condition of both boundaries
    -> inside or outside the range
```

After determining range membership, you must also decide whether operations through it should mutate the original set.

## 2. Reading Closed–Open Boundaries When null Can Be an Endpoint

The four range forms of `NavigableSet` are determined by two boundary-inclusion flags. Conditions are evaluated according to the **set's comparator**:

| Range form | Call |
|---|---|
| `[a, b]` | `subSet(a, true, b, true)` |
| `[a, b)` | `subSet(a, true, b, false)` |
| `(a, b]` | `subSet(a, false, b, true)` |
| `(a, b)` | `subSet(a, false, b, false)` |

The overloads without flags use `headSet(b)` to exclude `b`, `tailSet(a)` to include `a`, and `subSet(a,b)` to select `[a,b)`. “Including an endpoint” means including an element that **compares equal to 0** with the endpoint, even if the endpoint itself is not already present in the set. For example, on `[0,10,20,30,40]`, the range `[15,35]` contains `[20,30]`.

With `nullsFirst`, the `null` endpoint stands at the beginning of the relation: `subSet(null, true, 30, false)` can contain the `null` member itself, whereas `subSet(null, false, 30, false)` excludes it. For `nullsLast`, the order between `null` and 30 is reversed; do not use `null` as a marker for “unbounded”. When you need to omit one side of the bound, choose the appropriate `headSet` or `tailSet` call.

If two endpoints compare equal to 0, `[a,a]` can contain one equivalent element, while the three forms with at least one open end are all empty. An initially empty `[a,a]` view can still accept an element at that endpoint later. If the start endpoint comes after the end endpoint according to the comparator, the range is invalid and typically throws `IllegalArgumentException` on `TreeSet`. Use the inclusive flag instead of manually adding 1 to widen a boundary, because adding 1 does not generalize to numbers, strings, or timestamps.

## 3. Program 1: Testing All Four Boundary Forms

Save the file `RangeBoundaryMatrixDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class RangeBoundaryMatrixDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(0, 10, 20, 30, 40));

        System.out.println("values = " + values);
        System.out.println("[10, 30) = "
                + values.subSet(10, true, 30, false));
        System.out.println("[10, 30] = "
                + values.subSet(10, true, 30, true));
        System.out.println("(10, 30) = "
                + values.subSet(10, false, 30, false));
        System.out.println("(10, 30] = "
                + values.subSet(10, false, 30, true));
        System.out.println("default subSet = " + values.subSet(10, 30));
        System.out.println("absent boundaries = "
                + values.subSet(15, true, 35, true));
        System.out.println("[20, 20] = "
                + values.subSet(20, true, 20, true));
        System.out.println("[20, 20) = "
                + values.subSet(20, true, 20, false));
        System.out.println("(20, 20] = "
                + values.subSet(20, false, 20, true));
        System.out.println("(20, 20) = "
                + values.subSet(20, false, 20, false));
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 RangeBoundaryMatrixDemo.java
java RangeBoundaryMatrixDemo
```

Output from the verification run:

```text
values = [0, 10, 20, 30, 40]
[10, 30) = [10, 20]
[10, 30] = [10, 20, 30]
(10, 30) = [20]
(10, 30] = [20, 30]
default subSet = [10, 20]
absent boundaries = [20, 30]
[20, 20] = [20]
[20, 20) = []
(20, 20] = []
(20, 20) = []
```

The programs in this article use language features and APIs available in Java 17 and later, compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

With endpoints 10 and 30, only the members right at the boundaries change when toggling inclusive flags. A member strictly inside, such as 20, is kept in all four forms.

The absent boundaries example shows that closed or open does not require the endpoint to exist in the set. The example with both endpoints equal to 20 avoids the oversimplified rule “equal boundaries are always empty”: that holds for the default overload `[20, 20)`, but not for `[20, 20]`.

When testing a range query, include data right at each boundary. If you only test values deep inside the range, swapping `true` and `false` by mistake is very easy to miss.

## 4. Null Policy Starts with Ordering, Not with the View

### 4.1. Natural-Order TreeSet Does Not Accept null

A natural-order TreeSet of integers uses Integer's comparison relation. It has no natural rule for placing `null` before or after numbers.

Therefore, `add(null)` is not the only issue. Using `null` as a boundary in `headSet`, `tailSet`, or `subSet` also requires a suitable comparison rule. An empty Set does not make a `null` endpoint valid under natural ordering.

### 4.2. A Comparator Can Define a Position for null

Two common configurations:

```java
// Snippet; requires importing java.util.Comparator and TreeSet.
TreeSet<Integer> nullFirst =
        new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));

TreeSet<Integer> nullLast =
        new TreeSet<>(Comparator.nullsLast(Comparator.naturalOrder()));
```

Here:

- `nullsFirst` places `null` before all other values.
- `nullsLast` places `null` after all other values.
- `naturalOrder` compares non-null values.
- Two `null` values are considered equivalent, so the Set does not store multiple occurrences of `null`.

These rules are described in [Java 17 Comparator.nullsFirst and nullsLast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

`null` does not automatically mean 0, an empty string, or the minimum value of a numeric type. It has a position because a comparator was explicitly chosen.

### 4.3. Ability to Store null Does Not Determine Business Meaning

If `null` represents “unknown priority”, a Set of priority levels holds only one `null` member. It cannot automatically record how many tasks have no priority yet.

If you need multiple distinct records that are all missing an attribute, design a key per record or use an appropriate storage structure. Do not use a Set of values and expect it to preserve occurrence counts.

Similarly, putting `null` first does not automatically mean records with missing data should be processed first. Sorting policy and business policy must be aligned intentionally.

## 5. null as a Boundary Is a Real Position, Not an Omitted Bound

With `nullsFirst`, the order can be:

```text
null < 10 < 20 < 30
```

With `nullsLast`:

```text
10 < 20 < 30 < null
```

When passing `null` as an endpoint, the methods use that exact position. `null` does not mean “no lower bound” or “no upper bound”.

Suppose both sets contain `null, 10, 20, 30`:

| Call | nullsFirst | nullsLast |
|---|---|---|
| `headSet(null, false)` | `[]` | `[10, 20, 30]` |
| `headSet(null, true)` | `[null]` | `[10, 20, 30, null]` |
| `tailSet(null, false)` | `[10, 20, 30]` | `[]` |
| `tailSet(null, true)` | `[null, 10, 20, 30]` | `[null]` |

This table depends on the set currently having a `null` member. If `null` has not been added, ranges capable of including it do not synthesize it.

### 5.1. “Unbounded” Must Be Separated from null

If you only need an upper bound, use `headSet`. If you only need a lower bound, use `tailSet`. If you need the entire set, use the root set or an appropriate view of it.

Do not write `subSet(null, true, end, false)` as a general formula for “all values before end”. Under natural ordering it fails; with `nullsFirst` it starts at the `null` position; with `nullsLast` it can invert the boundary order.

A business API may use `null` to represent “caller did not pass an endpoint”, but the handling layer must translate that meaning into the right collection call. Do not pass `null` straight down to `TreeSet` and assume the collection shares the same convention.

### 5.2. A Range Can Intentionally Include or Exclude null

With `nullsFirst`:

```text
[null, 30)   -> null, 10, 20
(null, 30]   -> 10, 20, 30
```

With `nullsLast`:

```text
[20, null]   -> 20, 30, null
[20, null)   -> 20, 30
```

In both cases, `null` is an endpoint participating in comparison. The inclusive flag decides whether to keep the equivalence class at that endpoint.

## 6. Program 2: null at Both Ends and the Ambiguity of a null Result

Save the file `NullableRangeEndpointsDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NullableRangeEndpointsDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> nullFirst =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullFirst.addAll(List.of(10, 20, 30));
        nullFirst.add(null);

        System.out.println("nullsFirst = " + nullFirst);
        System.out.println("head null exclusive = "
                + nullFirst.headSet(null, false));
        System.out.println("head null inclusive = "
                + nullFirst.headSet(null, true));
        System.out.println("tail null exclusive = "
                + nullFirst.tailSet(null, false));
        System.out.println("tail null inclusive = "
                + nullFirst.tailSet(null, true));
        System.out.println("[null, 30) = "
                + nullFirst.subSet(null, true, 30, false));
        System.out.println("nullsFirst empty = " + nullFirst.isEmpty());
        System.out.println("nullsFirst first = " + nullFirst.first());

        NavigableSet<Integer> nullLast =
                new TreeSet<>(Comparator.nullsLast(Comparator.naturalOrder()));
        nullLast.addAll(List.of(10, 20, 30));
        nullLast.add(null);

        System.out.println("nullsLast = " + nullLast);
        System.out.println("head null exclusive = "
                + nullLast.headSet(null, false));
        System.out.println("head null inclusive = "
                + nullLast.headSet(null, true));
        System.out.println("tail null exclusive = "
                + nullLast.tailSet(null, false));
        System.out.println("tail null inclusive = "
                + nullLast.tailSet(null, true));
        System.out.println("[20, null] = "
                + nullLast.subSet(20, true, null, true));

        NavigableSet<Integer> after30 = nullLast.tailSet(30, false);
        NavigableSet<Integer> afterNull = nullLast.tailSet(null, false);
        System.out.println("higher 30 = " + nullLast.higher(30));
        System.out.println("after 30 empty = " + after30.isEmpty());
        System.out.println("after 30 first = " + after30.first());
        System.out.println("higher null = " + nullLast.higher(null));
        System.out.println("after null empty = " + afterNull.isEmpty());

        System.out.println("poll first from nullsFirst = "
                + nullFirst.pollFirst());
        System.out.println("after poll first = " + nullFirst);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 NullableRangeEndpointsDemo.java
java NullableRangeEndpointsDemo
```

Output from the verification run:

```text
nullsFirst = [null, 10, 20, 30]
head null exclusive = []
head null inclusive = [null]
tail null exclusive = [10, 20, 30]
tail null inclusive = [null, 10, 20, 30]
[null, 30) = [null, 10, 20]
nullsFirst empty = false
nullsFirst first = null
nullsLast = [10, 20, 30, null]
head null exclusive = [10, 20, 30]
head null inclusive = [10, 20, 30, null]
tail null exclusive = []
tail null inclusive = [null]
[20, null] = [20, 30, null]
higher 30 = null
after 30 empty = false
after 30 first = null
higher null = null
after null empty = true
poll first from nullsFirst = null
after poll first = [10, 20, 30]
```

### 6.1. first Returning null Does Not Mean the Set Is Empty

In the `nullsFirst` set, `isEmpty()` is `false` even though `first()` returns `null`, because `null` is the leading member.

A truly empty set causes `first()` to throw `NoSuchElementException`. Thus, checking “first is non-null” is not a general way to check whether a set has data.

### 6.2. higher Can Use null for Two Different Meanings

In the `nullsLast` set `[10, 20, 30, null]`:

- `higher(30)` returns `null` as a **real member** following 30.
- `higher(null)` returns `null` because **no member** follows `null`.

The same return value carries different meanings. The program uses corresponding views to show the difference:

```text
after 30:    view [null], not empty
after null:  view [], empty
```

Navigation methods returning `null` when nothing is found are described in [Java 17 NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html). When `null` itself is allowed as a member, callers need a separate way to express presence or absence of a result.

### 6.3. pollFirst Can Remove a Real null Member

Calling `pollFirst` on the `nullsFirst` set returns `null`, and afterward the set loses its `null` member and becomes `[10, 20, 30]`.

This is not a call on an empty set. Therefore, the following loop pattern can be wrong when the collection allows `null`:

```java
// Error-prone pattern with a Set containing a null member.
Integer value;
while ((value = values.pollFirst()) != null) {
    process(value);
}
```

This is a snippet illustrating a bug, not a standalone program. If `null` is at the front, the loop can remove it and stop immediately, leaving the other values behind.

In single-threaded code that needs to drain everything, you can distinguish the empty condition from the retrieved value. For read-only traversal, an iterator also separates `hasNext()` and `next()`:

```java
// Read snippet; values is a Set that allows null.
Iterator<Integer> iterator = values.iterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    processNullable(value);
}
```

`processNullable` represents handling designed to accept `null`. Do not auto-unbox `Integer` to `int` before handling the `null` case.

### 6.4. Optional Cannot Preserve a Present null

`Optional.ofNullable(result)` turns `null` into an empty `Optional`. If `result` can be a real `null` member, that conversion loses the “result is present” information.

When the distinction is required, you can use a result type with a separate presence flag, or model the domain without `null` as a member value. This decision belongs at the API boundary, not guessed from a `null` value after context is lost.

The examples above are single-threaded code. Checking emptiness and then reading or removing are multiple operations and are not automatically atomic in a multithreaded environment.

## 7. Range Views Add Constraints on Top of the Root Set's Policy

A comparator that accepts `null` only solves comparability. A view also has its own range conditions.

For example:

```text
root set with nullsFirst:
    [null, 10, 20, 30, 40]

nonNull view:
    tailSet(null, false)
    -> [10, 20, 30, 40]

inner band view:
    subSet(10, true, 30, false)
    -> [10, 20]
```

The root set allows `null`. However, `nonNull` excludes the `null` position with an open boundary, so adding `null` through `nonNull` is invalid. Likewise, adding 30 through `band` violates the open upper boundary.

Two failure cases must be separated in these examples:

| Situation | Issue |
|---|---|
| Natural-order TreeSet receives `null` | No valid `null` comparison exists |
| `nullsFirst` view that excludes `null` receives `add(null)` | Value is comparable, but outside the allowed range |

The first case typically throws `NullPointerException`; the second case on the demonstrated `TreeSet` view throws `IllegalArgumentException`.

Do not see `IllegalArgumentException` and assume the comparator cannot compare `null`. Nor should you see a comparator supporting `null` and infer that writes through every view are valid.

### 7.1. Constraints Apply to Future Range Membership, Not Just Existing Data

A view has bounds even when it has no elements. It is not merely a list of references extracted at creation time.

When adding a new value, the structure checks whether that value falls within the domain permitted by the view. When the root set adds a value inside the range, the view sees it without being recreated.

Conversely, an out-of-range value still cannot be added through the view even if the root set does not currently contain that value.

### 7.2. A Child View Cannot Widen Its Parent

A child view must stay within the bounds permitted by its parent. When the parent has an open boundary, placing a child endpoint right at that boundary also depends on the inclusive flag.

With `nonNull = root.tailSet(null, false)`:

- `nonNull.headSet(null, false)` can express a valid empty range.
- `nonNull.headSet(null, true)` attempts to include `null`, which the parent excluded, so it is rejected in the example.

Do not look at the current set of elements and conclude that both requests “are empty so they must be the same”. The API also guards the range that may receive data later.

Also do not assume a child view automatically takes the intersection with any passed boundary. An endpoint exceeding the parent's bounds can throw `IllegalArgumentException` instead of returning the desired intersection.

## 8. Program 3: null Valid at Root but Forbidden by View

Save the file `NullableRangeViewDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NullableRangeViewDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> root =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        root.addAll(List.of(10, 20, 30, 40));
        root.add(null);

        NavigableSet<Integer> nonNull = root.tailSet(null, false);
        NavigableSet<Integer> band = nonNull.subSet(10, true, 30, false);
        System.out.println("root = " + root);
        System.out.println("nonNull view = " + nonNull);
        System.out.println("band = " + band);
        band.add(15);
        System.out.println("root after band add 15 = " + root);

        try {
            nonNull.add(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("view add null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            band.add(30);
        } catch (IllegalArgumentException ex) {
            System.out.println("band add upper endpoint = "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("empty child at excluded null = "
                + nonNull.headSet(null, false));
        try {
            nonNull.headSet(null, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("child includes excluded null = "
                    + ex.getClass().getSimpleName());
        }

        TreeSet<Integer> snapshot = new TreeSet<>(band);
        System.out.println("snapshot initial = " + snapshot);
        System.out.println("snapshot add null = " + snapshot.add(null));
        System.out.println("snapshot after add null = " + snapshot);

        root.remove(10);
        System.out.println("band after root remove 10 = " + band);
        System.out.println("snapshot after root remove = " + snapshot);
        band.clear();
        System.out.println("root after band clear = " + root);
        System.out.println("snapshot after band clear = " + snapshot);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 NullableRangeViewDemo.java
java NullableRangeViewDemo
```

Output from the verification run:

```text
root = [null, 10, 20, 30, 40]
nonNull view = [10, 20, 30, 40]
band = [10, 20]
root after band add 15 = [null, 10, 15, 20, 30, 40]
view add null = IllegalArgumentException
band add upper endpoint = IllegalArgumentException
empty child at excluded null = []
child includes excluded null = IllegalArgumentException
snapshot initial = [10, 15, 20]
snapshot add null = true
snapshot after add null = [null, 10, 15, 20]
band after root remove 10 = [15, 20]
snapshot after root remove = [null, 10, 15, 20]
root after band clear = [null, 30, 40]
snapshot after band clear = [null, 10, 15, 20]
```

### 8.1. View and Root Set Mutate Each Other

`band.add(15)` adds 15 to the root set. When the root set removes 10, `band` is left with `[15, 20]`.

`band.clear()` removes the members currently in `band` from the root set. The root becomes `[null, 30, 40]`: `null` and 30 remain because neither belongs to the `band` under consideration.

`clear` does not just “erase temporary result data”. The view is linked to the same backing data, so write access through it is bounded write access to the root data.

### 8.2. Null Policy and Range Fences Are Not the Same Thing

`root` contains `null` and the comparator accepts it. Yet `nonNull.add(null)` is rejected because the lower fence is open at `null`.

`band.add(30)` is also rejected because the upper fence is open at 30. Both errors are range violations, even though the values can be validly compared.

### 8.3. A Copy Does Not Carry Over the View's Fences

The program creates:

```java
TreeSet<Integer> snapshot = new TreeSet<>(band);
```

The copy has the current elements and keeps `band`'s comparator. However, it is a new full `TreeSet` and no longer has `band`'s two bounding endpoints 10 and 30.

Because the preserved comparator is still `nullsFirst`, `snapshot.add(null)` succeeds. This does not contradict `band` forbidding `null`: `snapshot` preserves ordering, not range bounds.

Afterward, mutating `root` or clearing `band` does not cause `snapshot` to lose data. That is container-level independence.

## 9. Copying Data, Preserving the Comparator, and Preserving the Range Are Three Different Requirements

When passing a range result elsewhere, determine each separately:

| Requirement | What to protect |
|---|---|
| Detach container from source | Create a new collection |
| Preserve ordering and `null` position | Keep the appropriate comparator |
| Preserve closed–open bounds if further edits are allowed | Recreate a bounded view on the new container or encapsulate the rule |
| Disallow edits through the returned reference | Use an appropriate interface and wrapper |
| Detach mutable element data as well | Requires a copy policy or immutable values |

No single constructor automatically fulfills every row in the table.

### 9.1. Preserving the Comparator When Copying a SortedSet

With a variable typed as `SortedSet` or `NavigableSet`, `new TreeSet<>(source)` selects the `SortedSet` constructor and preserves the same ordering.

If the source is viewed through the `Collection` type, the overload taking `Collection` uses natural ordering. When the data contains `null` or lacks a suitable `Comparable`, that copy approach can fail.

You can pass the comparator explicitly:

```java
// Snippet; source is a SortedSet<Integer>.
TreeSet<Integer> copy = new TreeSet<>(source.comparator());
copy.addAll(source);
```

Do not only ask “was it copied?”; also ask “copied under which ordering?”.

### 9.2. To Preserve the Range, Re-establish the Range

If you need a separate copy that still restricts edits to `[10, 30)`:

```java
// Snippet; band is a SortedSet<Integer> with an appropriate comparator.
TreeSet<Integer> detachedRoot = new TreeSet<>(band);
NavigableSet<Integer> detachedBand =
        detachedRoot.subSet(10, true, 30, false);
```

`detachedBand` is linked to the new container, not the old root. It re-establishes both boundaries, so it still prevents adding out-of-range values.

This is a separate view on a separate backing store, not a claim that the `TreeSet` constructor remembered the source's bounds. If you do not want callers to bypass the fence through the backing container, do not expose `detachedRoot` directly to them.

### 9.3. Read-Only and Snapshots

Wrapping a view in a read-only wrapper does not snapshot the data; changes through the source can still be observed.

To get a read-only snapshot, create a copy first and then wrap it. When the source accepts `null`, you must choose a copy operation that also accepts the data and preserves the appropriate ordering.

If elements are mutable objects, copying the Set can still share the same objects. Modifying a field used by the comparator can leave both structures improperly organized; a container copy does not replace stable key design.

## 10. Switching to Another API Can Change the Null Policy

Not every Set has the same rules.

- Natural-order `TreeSet` rejects `null`.
- A `TreeSet` with a suitable comparator can accept `null`.
- A view can exclude `null` by range even though the comparator still accepts it.
- `Set.copyOf` does not accept a collection containing a `null` member.
- An unmodifiable wrapper and a comparator are two separate mechanisms.

According to [Java 17 Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), `null` in the input collection causes `NullPointerException`. At the same time, the result has the general `Set` type; it does not replace a `SortedSet` with the same comparator and range APIs.

Therefore, do not use `Set.copyOf(nullableView)` as a default way to create an “immutable TreeSet copy”. You must consciously decide whether to keep or reject `null`, then choose the appropriate type and copy mechanism.

In the examples, non-null data is added first via `List.of(...)`, and `null` is added separately through the `TreeSet` with a supporting comparator. Do not feed `null` into a factory with a null-forbidding policy and then think the error came from the `TreeSet` receiving the data.

If `null` has no business value, the simplest policy is usually to reject it at the input boundary. If `null` has meaning that must be kept, preserve that meaning across the entire processing pipeline instead of letting a collection conversion silently alter the requirement.

## 11. Program 4: Testing Where Policies Change

Save the file `NullPolicyTransferDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.Set;
import java.util.TreeSet;

public class NullPolicyTransferDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> natural = new TreeSet<>();
        try {
            natural.add(null);
        } catch (NullPointerException ex) {
            System.out.println("natural add null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            natural.headSet(null, true);
        } catch (NullPointerException ex) {
            System.out.println("natural null endpoint = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<Integer> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(List.of(10, 20));
        nullable.add(null);

        try {
            Set.copyOf(nullable);
        } catch (NullPointerException ex) {
            System.out.println("Set.copyOf nullable = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<Integer> snapshot =
                Collections.unmodifiableNavigableSet(new TreeSet<>(nullable));
        nullable.add(15);
        System.out.println("source after add 15 = " + nullable);
        System.out.println("read-only snapshot = " + snapshot);
        try {
            snapshot.add(12);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<String> collapsed =
                new TreeSet<>(Comparator.nullsFirst(null));
        System.out.println("collapsed add A = " + collapsed.add("A"));
        System.out.println("collapsed add B = " + collapsed.add("B"));
        System.out.println("collapsed contains Z = " + collapsed.contains("Z"));
        collapsed.add(null);
        System.out.println("collapsed members = " + collapsed);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 NullPolicyTransferDemo.java
java NullPolicyTransferDemo
```

Output from the verification run:

```text
natural add null = NullPointerException
natural null endpoint = NullPointerException
Set.copyOf nullable = NullPointerException
source after add 15 = [null, 10, 15, 20]
read-only snapshot = [null, 10, 20]
snapshot add = UnsupportedOperationException
collapsed add A = true
collapsed add B = false
collapsed contains Z = true
collapsed members = [null, A]
```

### 11.1. Natural Order Rejects null, Including as an Endpoint

Both of the first two calls throw `NullPointerException`: one call adds `null`, and the other uses `null` as a boundary. That confirms `null` must be comparable before discussing closed or open bounds.

### 11.2. Set.copyOf Does Not Accept null Members

The `nullable` source has a suitable comparator so it validly contains `null`. However, `Set.copyOf`'s policy rejects that data. The target collection has its own contract.

The read-only snapshot in the program is created from `new TreeSet<>(nullable)` and then wrapped. It preserves `null` and the ordering, does not see the value 15 added to the source afterward, and prevents adding 12 through the `snapshot` reference.

### 11.3. Comparator.nullsFirst(null) Does Not Mean Natural Order

The final part is an intentionally easy-to-misunderstand configuration:

```java
new TreeSet<>(Comparator.nullsFirst(null))
```

By the `Comparator` contract, when the inner comparator of `nullsFirst` is `null`, **all non-null values are treated as equivalent**. It does not automatically choose natural ordering for them.

Therefore, after adding `"A"`:

- Adding `"B"` returns `false` because the comparator treats A and B as equal.
- Querying `contains("Z")` returns `true` under the same comparison relation.
- Adding `null` creates a separate member at the front.

This is an ordering inconsistent with `String`'s `equals` and does not satisfy the usual `equals`-based uniqueness expectation of a Set. The example shows that comparator configuration can change uniqueness itself, not just the position of `null`.

If you want natural ordering for non-null values, pass `Comparator.naturalOrder()` explicitly to `nullsFirst` or `nullsLast`.

## 12. Different null Positions in Configuration Do Not Have the Same Meaning

There are at least three cases that are easily mixed up:

| Where `null` appears | Meaning |
|---|---|
| Explicit comparator passed to `TreeSet` is `null` | Uses natural ordering |
| Comparator argument to `Comparator.nullsFirst(null)` is `null` | All non-null values are treated as equivalent |
| Endpoint of `headSet(null, ...)` or `tailSet(null, ...)` | A boundary value that must be compared under the chosen ordering |

In Java, calling the constructor with a literal `null` without type information can also run into overload resolution ambiguity. When demonstrating the first case, use a typed variable:

```java
// Snippet: a null comparator in the constructor means natural order.
Comparator<Integer> noExplicitComparator = null;
TreeSet<Integer> values = new TreeSet<>(noExplicitComparator);
```

This `TreeSet` still has no policy accepting `null` elements. It differs from a `TreeSet` using a real `nullsFirst` comparator object.

### 12.1. Reversing Order Can Also Reverse the Position of null

The following two intents are not the same:

```java
// Snippet illustrating two different ordering relations.
Comparator<Integer> nullFirstDescending =
        Comparator.nullsFirst(Comparator.reverseOrder());

Comparator<Integer> reverseEverything =
        Comparator.nullsFirst(Comparator.<Integer>naturalOrder()).reversed();
```

The first case keeps `null` at the front, while sorting numbers in descending order.

The second case reverses the entire existing relation, so `null` moves to the end. When creating ranges on a reversed order, both endpoint positions and the meaning of before/after must be read according to that order.

Do not treat a variable name like “nullFirst” as proof after the comparator has had `reversed()` called on it; inspect the actual relation produced.

### 12.2. Element null Differs from Property null

Suppose a `TreeSet` holds `Task` items and sorts by a nullable `priority` property:

```java
// Model snippet; assumes name is non-null.
record Task(String name, Integer priority) {
}

Comparator<Task> byPriorityThenName =
        Comparator.comparing(
                Task::priority,
                Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(Task::name);
```

The inner comparator handles `null` for **priority**, not automatically allowing the `Task` object itself to be `null`. If the `Task` element itself can be `null`, a policy is also needed at the outer comparison layer.

Conversely, simply wrapping the whole `Task` comparator in `nullsFirst` does not automatically fix an inner comparator that unboxes a `null` priority into an `int`.

Identify which level `null` lives at: element, data field, comparator configuration, or query endpoint. Those are four distinct roles that need to be handled at the right boundary.

## 13. View Lifecycle and Backing-Data Write Access

`TreeSet` range views are backed by the root set. This makes them useful for bounded operations, while introducing assumptions that must be clear.

### 13.1. Live Read or Point-in-Time Snapshot?

A view reflects matching data currently in the backing set. Additions or removals in the backing set can change the view's contents.

If you need a fixed report, check results for later processing, or a small piece of data kept for a long time, consider a copy. A small view can still hold a reference to a much larger backing data structure.

Do not equate “creating a view does not modify the source” with “using the view will not modify the source”. Creation only reads configuration; subsequent operations such as `add`, `remove`, and `clear` can update the backing set.

### 13.2. Range Constraints Do Not Replace Business Policy

A `[10, 30)` view only checks the ordering condition; it does not know whether 10–29 are valid business priorities.

If a comparator puts `null` at one end and a view excludes it, that is a structural fence. Other rules such as accepting only levels divisible by 5 require separate validation; a view is not an arbitrary filter for all conditions.

### 13.3. Mutating Data Used for Comparison Is Still a Bug

Bounds are checked when the collection performs an operation, not by a mechanism watching every setter on stored objects.

If an element has a mutable `priority` property and is modified directly after insertion, its tree position and range membership may no longer be valid. You need immutable elements, stable comparison keys, or a controlled remove-and-reinsert flow.

Also do not mutate the configuration of a comparator currently used by a populated tree and expect the tree to reorganize itself.

### 13.4. Iterators and Multi-Step Operations

An iterator is not a snapshot. Structural modification through the root set or another view during iteration can throw `ConcurrentModificationException`. This modification-detection mechanism is not a multithreaded synchronization scheme.

A check-then-update sequence is also not automatically atomic. When adding multiple values to a view, an out-of-range value can fail after earlier values have already been added. If you need all-or-nothing behavior, you must have a separate procedure.

These assumptions are independent of whether the comparator handles `null` properly. Solving the `null` policy does not automatically solve consistency across a sequence of updates.

## 14. Layer-by-Layer Checklist for a Nullable Range

A systematic way to verify is to follow this order.

### Step 1: Establish the ordering relation

State explicitly:

```text
null is rejected
or
null comes first
or
null comes last
```

Then state the order among non-null values. If there are multiple criteria, determine when the comparison result is 0.

### Step 2: Establish both boundaries and flags

Specify `[a, b)`, `[a, b]`, `(a, b]`, or `(a, b)`. Verify that `a` does not come after `b` according to the comparator.

If an endpoint is `null`, read it as a real endpoint. If the business requirement wants no bound, choose the appropriate `headSet`/`tailSet` call instead of assigning special meaning to `null`.

### Step 3: Establish the parent range

If creating a view from another view, check that the endpoints and inclusive flags stay within what the parent permits. In particular, check an endpoint right at a parent's open boundary.

### Step 4: Establish mutability permissions

Distinguish between:

- Linked and mutable view.
- Linked view wrapped as read-only.
- Separate mutable copy.
- Separate read-only copy.
- Separate copy with range bounds re-applied.

These cases may print the same contents initially, yet behave differently when updates occur.

### Step 5: Test with representative data

At minimum, include:

- Empty set.
- Set containing only `null` if the policy allows it.
- Set with `null` and normal values.
- Values right at each boundary.
- Values inside and outside the range.
- Endpoints absent from the set.
- Two equivalent endpoints.
- Reversed ordering if the application uses a descending comparator.
- Mutations through the source and through the view.
- Copying and then trying to add a value that the source view excluded.

Do not test with a sequence containing only numbers in the middle of the range. Such a sequence will not expose boundary bugs or `null` bugs.

## 15. Common Pitfalls and How to Spot Them

| Practice | What is missed | How to handle |
|---|---|---|
| Passing `null` to represent unbounded | The collection may treat it as a real endpoint or fail to compare it | Translate the business requirement into the right overload |
| Comparator accepts `null`, so every view accepts `null` | Views have their own fences | Check `null`'s position against the boundaries |
| Toggling inclusive to handle an incomparable `null` | Closed/open does not create an ordering relation | Design the comparator first |
| Checking `first` non-null to see if data exists | The first member can be `null` | Use emptiness state or a separate presence representation |
| Looping `pollFirst` until it returns `null` | Can stop after removing a real `null` | Separate the remaining-elements condition from the element value |
| Using `Optional.ofNullable` while wanting to keep a present `null` | An empty `Optional` loses information | Change the result type or value model |
| Using `nullsFirst(null)` to get natural order | All non-null values are treated as equivalent | Pass `naturalOrder` explicitly |
| Copying a view and assuming bounds remain | Constructor preserves data and order, not fences | Recreate the view on the copy if needed |
| `Set.copyOf` to preserve a nullable `SortedSet` | `null` is rejected and ordering type is not preserved | Choose a copy with a matching policy |
| Read-only means data is fixed | The wrapper's source can still change | Copy when a snapshot is needed |
| Reversing a comparator while assuming `null` stays first | Reversing the whole relation also reverses `null`'s position | Verify the final ordering |
| Wrapping the outer comparator with `nullsFirst` to fix all property `null`s | Only handles `null` at the element level | Place the policy at the right data level |

When an exception occurs, identify which layer failed: incomparable, wrong endpoint order, exceeding parent bounds, adding out of range, or updating through an unmodifiable wrapper. Do not randomly flip flags until the error disappears.

## 16. Practice Exercises

### Exercise 1: Four Range Forms

Given `[5, 10, 15, 20]` in ascending order, predict `[10, 20)`, `(10, 20]`, and `[10, 10]`.

**Suggested answer:** `[10, 15]`, `[15, 20]`, and `[10]`, respectively.

### Exercise 2: null Is Not Unbounded

A set uses `nullsLast` and contains `[5, 10, null]`. What do `headSet(null, false)` and `tailSet(null, true)` contain?

**Suggested answer:** `[5, 10]` and `[null]`, respectively. `null` is the last endpoint of the relation, not a marker for an omitted bound.

### Exercise 3: null Present but Range Not Empty

A set uses `nullsFirst` and has only one member, `null`. What do `first()` and `isEmpty()` return?

**Suggested answer:** `first()` returns `null` as a real member; `isEmpty()` returns `false`.

### Exercise 4: Same null Return, Different Meanings

A `nullsLast` set is `[5, 10, null]`. Explain `higher(10)` and `higher(null)`.

**Suggested answer:** the first call finds the `null` member; the second call finds no member. If they must be distinguished, presence state must be tracked separately.

### Exercise 5: Root Has null, View Forbids null

Create the view `root.tailSet(null, false)` from a `root` using `nullsFirst`. Is adding `null` through the view valid?

**Suggested answer:** no. `null` is comparable, but it is excluded by the open lower boundary; on the example `TreeSet` view, the operation throws `IllegalArgumentException`.

### Exercise 6: Copying a View That Contains No null

The view above contains no `null`. Create a new `TreeSet` using the constructor taking a `SortedSet`, then add `null` to the copy.

Can that succeed?

**Suggested answer:** yes, because the `nullsFirst` comparator is preserved, while the `tailSet` restriction is not carried over. To keep the restriction, recreate the view on the new container.

### Exercise 7: Inner Comparator Left Empty

A `TreeSet` uses `Comparator.nullsFirst(null)` and already has string `"A"` added. Why can adding `"B"` return `false`?

**Suggested answer:** a `null` inner comparator means all non-null strings are considered equivalent; no natural ordering is automatically inserted.

### Exercise 8: Read-Only Snapshot

The source validly contains `null`. You need to return a separate copy that preserves ordering and disallows adding/removing through the returned reference. Should you default to `Set.copyOf`?

**Suggested answer:** no. `Set.copyOf` rejects `null` and does not preserve the `SortedSet` interface or comparator. You can copy into a `TreeSet` preserving the right comparator and then wrap it with an appropriate wrapper; also determine immutability requirements for individual elements.

### Exercise 9: null on a Property

A `Task` is non-null, but its `priority` is `null`. Is wrapping the whole `Task` comparator with `nullsLast` enough?

**Suggested answer:** not necessarily. You must handle `null` in the `priority` comparison itself; an outer wrapper only handles the case where the entire `Task` element is `null`.

A clear range design must account for the value domain, `null` position, boundary-inclusion rules, and write permissions through views. When these decisions are kept distinct, API calls reflect the true meaning of the data rather than merely producing a desired output by coincidence.
