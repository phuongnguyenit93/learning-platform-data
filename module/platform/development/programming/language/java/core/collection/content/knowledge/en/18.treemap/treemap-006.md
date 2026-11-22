# TreeMap: headMap, tailMap, subMap, and Choosing Bounds

A TreeMap can hold many keys, but a task often needs only a specific region: milestones before a deadline, records from a certain point onward, or events between two timestamps.

`headMap`, `tailMap`, and `subMap` represent those regions in key order. What you need to choose is not just two numbers. You must determine the ordering direction, whether each bound is inclusive, and whether the result still shares data with the original map.

This article uses Java 17. After this article, you should be able to translate a range into comparison conditions, write the right API calls, test boundary-equality cases, and recognize the effects of operations performed through a view.

## 1. Model: a key window over the same data

Suppose a TreeMap uses ascending numeric order and has the keys:

~~~text
10, 20, 30, 40, 50
~~~

The three kinds of windows are:

- `headMap`: the part before an ending bound.
- `tailMap`: the part starting at or after a bound.
- `subMap`: the part between two bounds.

The result on a TreeMap is a key-range `view`, not an already-filtered copy. You can keep the view to read that region of data; when the original map changes within the range, the view reflects the change.

Creating a view does not itself add, remove, or modify mappings. Valid update operations performed through the view later are what affect the underlying data. [Java 17: TreeMap range methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 1.1. Conditions apply to keys

A key-range view does not automatically filter by value contents. If the key is a product code while the value has an updated-date field, `headMap` by code does not turn into a query before a date.

To have ranges serve time-based queries, the key must have an ordering rule that represents time appropriately. Key design and the business question must match before choosing a method.

### 1.2. A view does not mean read-only

The word "view" only describes the relationship with the underlying data; it does not mean all mutating operations are forbidden. TreeMap provides supported mutating operations within the key range.

For example, `view.remove(key)` can delete the corresponding mapping from the original map; `view.clear()` can delete the entire range. Therefore, do not use a view as a place for "trial edits" under the assumption that the original map will not be affected.

## 2. Three defaults of SortedMap

The methods without booleans use fixed bounds:

| Call | Key condition k in map order | Range notation |
|---|---|---|
| headMap(b) | k < b | Part before b, excluding b |
| tailMap(a) | k ≥ a | Part from a, including a |
| subMap(a, b) | a ≤ k < b | [a, b) |

With keys 10, 20, 30, 40, 50:

~~~text
headMap(30)   -> 10, 20
tailMap(30)   -> 30, 40, 50
subMap(20,40) -> 20, 30
~~~

By default, `headMap` excludes the ending bound; `tailMap` includes the starting bound; `subMap` includes the lower bound and excludes the upper bound. Do not memorize a blanket rule like "these methods all exclude bounds" or "they all include bounds." [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html)

### 2.1. Meaning of a half-open interval

`[a, b)` means starting with `a` included, ending before `b`. Two adjacent regions `[a, b)` and `[b, c)` do not duplicate a key equal to `b`.

That is useful when partitioning data into sessions or days. The boundary point belongs to the second region and does not appear twice just because it equals the exact border.

This is a bound-selection rule, not a requirement that the data must contain `a` or `b`. If there are no keys at the bounds, keys in between are still selected.

### 2.2. Return types in Java 17

The older forms without booleans are declared to return `SortedMap`. The forms with booleans in `NavigableMap` return `NavigableMap`.

Partial illustration with a variable `map` of type `NavigableMap`:

~~~java
SortedMap<Integer, String> legacy = map.subMap(20, 40);

NavigableMap<Integer, String> explicit =
        map.subMap(20, true, 40, false);
~~~

If you need to continue using `floorKey`, `firstEntry`, or other navigation methods on the result, the boolean overloads also express the `NavigableMap` type directly. Do not cast arbitrarily just to bypass declaration differences.

## 3. Explicitly choosing each bound with booleans

`NavigableMap` adds:

~~~text
headMap(toKey, inclusive)
tailMap(fromKey, inclusive)
subMap(fromKey, fromInclusive, toKey, toInclusive)
~~~

This is a signature diagram for reading parameters, not a standalone runnable snippet.

`true` means accepting a key that compares equal to the corresponding bound; `false` means excluding a key that compares equal to that bound. With `subMap`, the two booleans apply separately to the two ends. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

### 3.1. One bound: before or after a milestone

On an ascending sequence of numbers:

| Requirement | Call with milestone 30 | Resulting keys |
|---|---|---|
| Before 30 | headMap(30, false) | 10, 20 |
| Not after 30 | headMap(30, true) | 10, 20, 30 |
| From 30 onward | tailMap(30, true) | 30, 40, 50 |
| After 30 | tailMap(30, false) | 40, 50 |

Words like "to", "from", and "before" in natural-language requirements can be interpreted differently by users. In code, convert them into conditions with or without equality first.

### 3.2. Two bounds: four common regions

With a = 20 and b = 40:

| Region | Call | Resulting keys |
|---|---|---|
| [20, 40] | subMap(20, true, 40, true) | 20, 30, 40 |
| [20, 40) | subMap(20, true, 40, false) | 20, 30 |
| (20, 40] | subMap(20, false, 40, true) | 30, 40 |
| (20, 40) | subMap(20, false, 40, false) | 30 |

The boolean pair does not say "sort ascending or descending." It only selects the inclusivity of the two bounds within the order the map already has.

If a multi-parameter call is hard to read in an important piece of code, you can name variables to express intent:

~~~java
boolean includeStart = true;
boolean includeEnd = false;

NavigableMap<Integer, String> selected =
        map.subMap(start, includeStart, end, includeEnd);
~~~

The snippet above is an illustration with `map`, `start`, and `end` already defined. Variable names should match the business domain, rather than just replacing `true`/`false` with generic names that are harder to understand.

### 3.3. Write out comparison conditions when in doubt

Let `c` be the map's comparison rule. You can read the interval `[a, b)` as:

~~~text
c(k, a) >= 0
and
c(k, b) < 0
~~~

The interval `(a, b]` only changes the two signs at the bounds:

~~~text
c(k, a) > 0
and
c(k, b) <= 0
~~~

This is a reasoning tool, not a mandate to write a manual filtering loop instead of the API. It helps determine accurately whether a key equal to the start or end is kept.

## 4. Bounds do not need to exist, but must be valid

### 4.1. Bounds are comparison points

With keys 10, 20, 30, 40, 50, `subMap(15, true, 45, false)` selects 20, 30, 40. The absence of 15 or 45 in the map does not make the call meaningless.

Nor do you need to find the nearest existing key before calling `subMap`. The bounds already define the comparison region that the application wants.

### 4.2. Equal bounds

On an unrestricted root map, with valid bounds and key types:

- `subMap(a, true, a, true)` can contain a key that compares equal to `a` if it exists.
- If at least one end is excluded, no key can satisfy both conditions simultaneously when the two bounds compare equal.
- `subMap(a, a)` is an empty range by default.

Examples:

~~~text
subMap(20, true, 20, true)  -> 20
subMap(20, true, 20, false) -> empty
subMap(25, true, 25, true)  -> empty if the map does not contain key 25
~~~

"Can contain a key at the bound" does not mean the API creates a new key if it is not there yet. It only allows that position to fall within the range.

### 4.3. Reversed bounds are a request error

If `fromKey` comes after `toKey` according to the comparator, `subMap` throws `IllegalArgumentException`. Do not treat it as an empty region and swallow the error, unless the application layer already has an explicit request-normalization policy.

"A valid region that currently has no data" is different from "invalid bounds." The two states usually need different responses at the business layer.

### 4.4. Null does not mean infinity

Do not pass `null` to imply "no bound." Natural-order `TreeMap` does not allow `null` keys or bounds; you may hit a `NullPointerException`. A custom comparator only allows `null` when it explicitly defines how to compare `null`.

Even when `null` is valid, it is a point according to the comparator, not automatically negative infinity or positive infinity for every map. When you only want to limit one end, `headMap` or `tailMap` already expresses that need properly.

Keys and bounds must also be comparable under the map's rule. A type mismatch or incompatible comparator error is different from a valid empty range.

## 5. Bound inclusion follows compare, not equals

Suppose a comparator treats uppercase and lowercase letters as equivalent. Key `"b"` compares equal to `0` against bound `"B"`.

Then:

~~~text
headMap("B", false) -> excludes key "b"
headMap("B", true)  -> may include key "b"
~~~

Inclusivity checks whether the comparison result is `0`; it does not require the bound object to be the exact same key object or equal under another equality check.

The case-insensitive comparator example in the program is only used to illustrate how bounds are evaluated. When designing real keys, consider consistency between the comparator and `equals` so the map adheres to the desired data contract. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

Key components and state used by the comparator must remain stable while using the map. A rule that mutates based on external variables does not produce a reliable key window just by calling `headMap` again.

## 6. Live views and their effect on the original map

### 6.1. Two-way changes

Starting with original keys 10, 20, 30, 40, 50 and view `[20, 40)`:

~~~text
original: 10, 20, 30, 40, 50
view:     20, 30

original adds 25:
view sees 20, 25, 30

view adds 35:
original has 10, 20, 25, 30, 35, 40, 50

view removes 20:
original now has 10, 25, 30, 35, 40, 50
~~~

You do not need to re-acquire the view to see new mappings that fall within the range. In contrast, a `List` of keys copied earlier is a separate structure and does not automatically gain elements like a view.

### 6.2. Reading outside the range vs. inserting outside the range

On view `[20, 40)`, key 40 is out of range even though the original map currently contains 40.

With data that has no `null` values in the example:

- `get(40)` through the view finds no mapping in the view.
- `remove(40)` through the view does not remove the out-of-range mapping from the original map.
- `put(40, ...)` through the view is rejected with `IllegalArgumentException`.

Do not assume from the original map's permissions that the view can also write every key. A view only represents the portion of data within its range.

### 6.3. Clearing a view clears the range

After the view contains 25, 30, 35, calling `clear` on the view removes those three mappings from the original map, leaving 10, 40, 50.

This is a very direct way to express a range deletion. Understand that this mutates the data, rather than merely clearing a temporary object holding filtered results.

Do not hold an old iterator over the shared structure while arbitrarily adding or removing through the other map or view. Objects with different variable names can still be backed by the same underlying data.

### 6.4. Copying when independent data is needed

Illustration:

~~~java
NavigableMap<Integer, String> window =
        source.subMap(20, true, 40, false);

TreeMap<Integer, String> independent = new TreeMap<>(window);
~~~

The constructor taking `SortedMap` matches the source `NavigableMap` type, so the new `TreeMap` preserves the source's ordering. The mapping structure is independent of `window` for subsequent add or remove operations.

This is still a copy of the mappings, not a deep copy of the key and value objects. If values are mutable objects, choose the appropriate copy depth for your requirements.

If the source undergoes concurrent modifications, creating a copy also requires an appropriate source-reading policy. An independent result structure does not by itself solve synchronization while collecting data from the source.

## 7. Nested views: cannot expand bound permissions

### 7.1. The parent view's limits still apply

Suppose `outer` is `[20, 40)`. Calling a range method on `outer` cannot expand it to include 10 or include 40.

Examples:

~~~text
outer.headMap(40, false) -> keeps the part before 40, still excludes 40: valid
outer.headMap(40, true)  -> wants to include 40: rejected
outer.tailMap(10, false) -> sets lower bound outside outer's range: rejected
~~~

Do not assume an out-of-bounds request is always clamped by the API to the intersection with the parent's range. Range contracts specify that creating a view with invalid bounds can be rejected.

### 7.2. A bound equal to an excluded endpoint is not always forbidden

One detail to read carefully is the inclusivity flag. On `outer` `[20, 40)`, `tailMap(40, false)` creates a valid empty region in `TreeMap`: it still excludes 40 and does not take any key beyond `outer`'s authority.

Meanwhile, requesting `40` to be included demands a bound the parent already excluded. Therefore, simply asking "does 40 appear in outer?" is not enough to decide every nested call with bound 40.

The way to reason about it is to consider both the bound value and the permission to include that bound. The full program verifies the pair of cases: keeping the excluded upper bound versus requesting to include it.

### 7.3. Emptiness does not remove range constraints

A view can be empty because the data has no keys in the range yet. It still carries its bound limits; do not use emptiness to infer that you can insert or create sub-views arbitrarily.

Separate two concepts:

- The key domain that the view is permitted to represent.
- The mappings that currently exist within that domain.

When checking for bound errors, examine the permitted domain, not just the list of keys currently printed.

## 8. Descending order: head no longer means smaller numbers

### 8.1. Read the comparator direction first

With a reversed view of keys 10, 20, 30, 40, 50:

~~~text
50, 40, 30, 20, 10
~~~

`head` is the part before the bound in this order. `tail` is the part at or after the bound in this order.

| Call on descending view | Resulting keys in view order |
|---|---|
| headMap(30, true) | 50, 40, 30 |
| tailMap(30, false) | 20, 10 |
| subMap(40, true, 20, false) | 40, 30 |

There is no accidental sign-flip bug here. The view's comparison rule is reversed, so before/after relationships change accordingly.

### 8.2. From and to must follow the map's direction

On the descending view, 40 comes before 20, so the pair `from = 40`, `to = 20` is valid. Passing `from = 20`, `to = 40` out of ascending-number habit puts `from` after `to` in the view's comparator and is rejected.

Do not automatically sort two bounds with `Math.min` and `Math.max` when a method is designed to accept an arbitrary sorted map. That implicitly imposes ascending numeric order, which may conflict with the source comparator.

A descending view still shares data. Valid additions or removals through the descending view's range still go to the original map; there is no separate data layer just because the traversal direction differs.

## 9. Choose bounds from business logic, don't invent "fake bounds"

### 9.1. Use inclusive instead of adding one unit

To include `b`, use the inclusive flag for `b` instead of always rewriting it as "less than `b + 1`."

Adding one unit carries several assumptions: the key must support addition, the domain must be discrete by that exact unit, and the addition must not overflow. With `Integer.MAX_VALUE`, adding one is wrong in `int`.

`subMap(max, true, max, true)` represents a single-point range at the maximum value without needing to construct a next number. For strings or complex business keys, the concept of "`b + 1`" might not even exist.

### 9.2. A single-day range

If the keys are `LocalDateTime` in local time in the example, and you want events belonging to day `d`:

~~~text
start = start of day d
end   = start of day d + 1 calendar day
select [start, end)
~~~

Events exactly at `start` are kept. Events exactly at `end` belong to the next day and are excluded. You do not need to guess a "last second of the day" and miss sub-second precision.

Partial illustration:

~~~java
LocalDateTime start = day.atStartOfDay();
LocalDateTime end = day.plusDays(1).atStartOfDay();

NavigableMap<LocalDateTime, String> daily =
        events.subMap(start, true, end, false);
~~~

The example uses `LocalDate` and `LocalDateTime` within valid date ranges; a system storing timestamps in another time model needs to determine bounds according to its own time model. [Java 17: LocalDate.plusDays and atStartOfDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)

### 9.3. Boundary test matrix

Before using in a real task, pick test inputs:

| Key position | Question |
|---|---|
| Just before from | Excluded? |
| Equal to from | Matches fromInclusive? |
| In between | Kept? |
| Equal to to | Matches toInclusive? |
| Just after to | Excluded? |

Add cases with missing keys at the bounds, equal bounds, and a descending comparator if the method allows custom ordering. Boundary-equality cases are where the difference between the two booleans actually shows up.

## 10. Complete Java program

Save all the following code to `TreeMapRangeBoundsDemo.java`. The program requires no external libraries.

It uses separate data groups so that `clear` or removals in one group do not affect the remaining groups. The checks verify live views, independent copies, bound errors, and data within a day range.

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapRangeBoundsDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        for (int key : new int[] {10, 20, 30, 40, 50}) {
            map.put(key, "v" + key);
        }
        return map;
    }

    private static <K, V> List<K> keys(java.util.Map<K, V> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected range result");
        }
    }

    private static boolean rejected(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException exception) {
            return true;
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> map = sample();
        System.out.println("default/head30=" + keys(map.headMap(30)));
        System.out.println("default/tail30=" + keys(map.tailMap(30)));
        System.out.println("default/sub20to40=" + keys(map.subMap(20, 40)));
        System.out.println("flags/head30Inclusive="
                + keys(map.headMap(30, true)));
        System.out.println("flags/tail30Exclusive="
                + keys(map.tailMap(30, false)));
        System.out.println("flags/open20to40="
                + keys(map.subMap(20, false, 40, false)));
        System.out.println("flags/closed20to40="
                + keys(map.subMap(20, true, 40, true)));
        System.out.println("bounds/notPresent="
                + keys(map.subMap(15, true, 45, false)));
        System.out.println("equal/closed="
                + keys(map.subMap(20, true, 20, true)));
        System.out.println("equal/halfOpen="
                + keys(map.subMap(20, true, 20, false)));
        System.out.println("equal/missing="
                + keys(map.subMap(25, true, 25, true)));

        TreeMap<Integer, String> parent = sample();
        NavigableMap<Integer, String> window =
                parent.subMap(20, true, 40, false);
        TreeMap<Integer, String> independent = new TreeMap<>(window);
        parent.put(25, "v25");
        window.put(35, "v35");
        window.remove(20);
        require(keys(window).equals(List.of(25, 30, 35)));
        require(keys(parent).equals(List.of(10, 25, 30, 35, 40, 50)));
        require(keys(independent).equals(List.of(20, 30)));
        System.out.println("live/window=" + keys(window));
        System.out.println("live/parent=" + keys(parent));
        System.out.println("live/copy=" + keys(independent));
        boolean outside = rejected(() -> window.put(40, "not-allowed"));
        require(outside && parent.get(40).equals("v40"));
        System.out.println("live/outsidePutRejected=" + outside);
        System.out.println("live/outsideGet=" + window.get(40)
                + ", outsideRemove=" + window.remove(40));
        window.clear();
        require(keys(parent).equals(List.of(10, 40, 50)));
        System.out.println("live/parentAfterClear=" + keys(parent));

        NavigableMap<Integer, String> outer =
                sample().subMap(20, true, 40, false);
        System.out.println("nested/sameExcludedUpper="
                + keys(outer.headMap(40, false)));
        boolean includeUpper = rejected(() -> outer.headMap(40, true));
        boolean expandLower = rejected(() -> outer.tailMap(10, false));
        require(includeUpper && expandLower);
        System.out.println("nested/includeUpperRejected=" + includeUpper);
        System.out.println("nested/emptyAtUpper="
                + keys(outer.tailMap(40, false)));
        System.out.println("nested/expandLowerRejected=" + expandLower);

        NavigableMap<Integer, String> descending = sample().descendingMap();
        System.out.println("descending/head30Inclusive="
                + keys(descending.headMap(30, true)));
        System.out.println("descending/tail30Exclusive="
                + keys(descending.tailMap(30, false)));
        System.out.println("descending/sub40to20="
                + keys(descending.subMap(40, true, 20, false)));
        boolean wrongDirection =
                rejected(() -> descending.subMap(20, true, 40, false));
        require(wrongDirection);
        System.out.println("descending/wrongDirectionRejected="
                + wrongDirection);

        TreeMap<String, Integer> words =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        words.put("a", 1);
        words.put("b", 2);
        words.put("c", 3);
        System.out.println("comparison/headBExclusive="
                + keys(words.headMap("B", false)));
        System.out.println("comparison/headBInclusive="
                + keys(words.headMap("B", true)));

        TreeMap<Integer, String> maximum = new TreeMap<>();
        maximum.put(Integer.MAX_VALUE, "maximum");
        System.out.println("max/closed="
                + keys(maximum.subMap(Integer.MAX_VALUE, true,
                        Integer.MAX_VALUE, true)));

        LocalDate day = LocalDate.of(2026, 10, 20);
        LocalDateTime start = day.atStartOfDay();
        LocalDateTime nextStart = day.plusDays(1).atStartOfDay();
        TreeMap<LocalDateTime, String> events = new TreeMap<>();
        events.put(start.minusNanos(1), "previous");
        events.put(start, "start");
        events.put(start.plusHours(8), "morning");
        events.put(nextStart, "next");
        NavigableMap<LocalDateTime, String> today =
                events.subMap(start, true, nextStart, false);
        require(new ArrayList<>(today.values())
                .equals(List.of("start", "morning")));
        System.out.println("day/values=" + new ArrayList<>(today.values()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 TreeMapRangeBoundsDemo.java
java TreeMapRangeBoundsDemo
~~~

Stdout from the verification run:

~~~text
default/head30=[10, 20]
default/tail30=[30, 40, 50]
default/sub20to40=[20, 30]
flags/head30Inclusive=[10, 20, 30]
flags/tail30Exclusive=[40, 50]
flags/open20to40=[30]
flags/closed20to40=[20, 30, 40]
bounds/notPresent=[20, 30, 40]
equal/closed=[20]
equal/halfOpen=[]
equal/missing=[]
live/window=[25, 30, 35]
live/parent=[10, 25, 30, 35, 40, 50]
live/copy=[20, 30]
live/outsidePutRejected=true
live/outsideGet=null, outsideRemove=null
live/parentAfterClear=[10, 40, 50]
nested/sameExcludedUpper=[20, 30]
nested/includeUpperRejected=true
nested/emptyAtUpper=[]
nested/expandLowerRejected=true
descending/head30Inclusive=[50, 40, 30]
descending/tail30Exclusive=[20, 10]
descending/sub40to20=[40, 30]
descending/wrongDirectionRejected=true
comparison/headBExclusive=[a]
comparison/headBInclusive=[a, b]
max/closed=[2147483647]
day/values=[start, morning]
~~~

The code was compiled with `--release 17` and ran successfully. The release option specifies the API level and compatible target bytecode; it does not assert that the executing JVM is specifically JDK 17.

## 11. Explaining key results

### 11.1. Default, flags, and equal

The three `default` lines contrast the three different defaults. The `flags` group shows that booleans change whether the exact bound is taken, not the map's ordering.

The `equal` group distinguishes a single-point region with data, a region that excludes one end and is therefore empty, and a valid single-point region that has no mapping at that point yet. Empty is not always an error.

### 11.2. Live

The `copy` was created when `window` contained 20 and 30. The original map added 25, the view added 35 and then removed 20; `window` and the original map both reflect the new state, while `copy` keeps the copied mappings.

Putting 40 through `window` is rejected. Getting or removing 40 through `window` does not cross the range boundary to retrieve or delete the mapping for 40 in the original map. Clearing `window` afterward only removes the current region, leaving 10, 40, 50 in the original map.

### 11.3. Nested

`headMap` at upper bound 40 with `inclusive` `false` is valid, while changing it to `true` is rejected. `tailMap` at 40 with `false` yields an empty region; `tailMap` from 10 is rejected because it falls outside the parent's limits.

These results remind us that the permitted key domain and the currently present mappings are two different things to reason about.

### 11.4. Descending and comparison

The `descending` group reads `head`, `tail`, and `from`/`to` in the direction from 50 down to 10. Passing bounds in the wrong direction is rejected with `IllegalArgumentException`.

The `comparison` group uses bound `"B"` against key `"b"` to show that `inclusive` depends on the comparison. The program does not rely on `equals` equality between the two strings to select the bound.

### 11.5. Max and day

The closed interval at `Integer.MAX_VALUE` does not need to add one unit. The day range keeps the event right at the start of the day and in the morning, while excluding the event just before the start of the day and the event right at the start of the next day.

These examples show that bound flags solve the requirement directly instead of needing a trick to fabricate a hypothetical next key.

## 12. Common mistakes

| Mistake | Fix |
|---|---|
| `headMap` includes the bound by default | The non-boolean form excludes the ending bound |
| `tailMap` excludes the bound by default | The non-boolean form includes the starting bound |
| Two-argument `subMap` includes both ends | It is `[from, to)` |
| Bounds must exist in the map | Bounds are comparison points |
| Equal bounds are always an error | They can be a valid single-point or empty region |
| Reversed bounds just return an empty region | That can be an `IllegalArgumentException` |
| A view is a copy for trial edits | Valid mutating operations affect the original map |
| Clearing a view only clears a temporary object | It deletes the mappings in the range from the original map |
| If the original has a key, the view can write it | The view is still constrained by its range |
| Sub-views automatically clamp any bound to the parent region | Out-of-bounds requests can be rejected |
| `head` always means smaller numbers | Must read according to the comparator, including descending order |
| Including `b` requires changing to `b + 1` | Use `inclusive`; do not assume a next key exists |
| `null` represents unbounded | `null` follows comparison rules, not an infinity symbol |
| Copying a view makes value objects immutable | Copying mappings does not deep-copy |

## 13. Practice and solutions

### Exercise 1. Three defaults

A map has 5, 10, 15, 20, 25. Give the keys in `headMap(15)`, `tailMap(15)`, and `subMap(10, 20)`.

**Solution:** Head is 5, 10. Tail is 15, 20, 25. Sub is 10, 15 because the lower bound is included while the upper bound is excluded.

### Exercise 2. Equality on both ends

You need to select keys from 10 to 20, inclusive of both bounds. Write the call and explain why you do not need to use 21.

**Solution:** `subMap(10, true, 20, true)`. The last flag directly expresses including 20. Using 21 assumes a discrete numeric domain, can fail at type limits, or does not apply to other key types.

### Exercise 3. Missing bounds and equal bounds

With keys 10, 20, 30, 40, what is the result of `subMap(15, true, 35, false)`? How do `subMap(20, true, 20, true)` and `subMap(20, false, 20, true)` differ?

**Solution:** The first range contains 20, 30 even though bounds 15 and 35 are absent. The closed single-point range contains 20; the range that excludes the lower bound with the same two bounds is empty.

### Exercise 4. Where does a view write?

The original map has 10, 20, 30, 40, 50; the view is `[20, 40)`. Add 35 through the view, then clear the view. Which keys remain in the original map? Can you `put(40, ...)` through the view before clearing?

**Solution:** `clear` removes 20, 30, and 35 from the original map, leaving 10, 40, 50. `put(40, ...)` through the view is rejected because the upper bound excludes 40, even though the original map already has that key.

### Exercise 5. Nested views

`outer` is `[20, 40)`. Distinguish `outer.headMap(40, false)`, `outer.headMap(40, true)`, and `outer.tailMap(10, false)`.

**Solution:** The first case preserves the exclusion limit of 40, so it is valid. The second case demands including a bound the parent already excluded, so it is rejected. The third case places a bound outside the parent's limits; it is not implicitly clamped to `outer`'s range.

### Exercise 6. Descending order

A descending view has 50, 40, 30, 20, 10. What do `headMap(30, true)`, `tailMap(30, false)`, and `subMap(40, true, 20, false)` contain?

**Solution:** Respectively: 50, 40, 30; 20, 10; and 40, 30. The before/after relationships follow the descending comparator, not ascending numeric comparison.

### Exercise 7. Selecting a day

Events are located just before the start of the day, right at the start of the day, midday, and right at the start of the next day. You need the current day's region. Which interval do you use and which events are kept?

**Solution:** Use `[start of day, start of next day)`. Keeps the event right at the start of the day and midday; excludes the event before the start of the day and the event at the start of the next day. No need to calculate the last second of the day.

### Exercise 8. An empty region still has limits

View `[100, 200)` currently has no mappings. Can you `put` 50 through the view because "the view has no data yet"? Is a copy of the view still constrained to `[100, 200)` like the view?

**Solution:** You cannot `put` 50 through the view; the permitted domain does not depend on whether it is currently empty. A new `TreeMap` copying the mappings from the view has its own map structure and does not remain a bounded window of the original map just because it was created from a view. The comparator is preserved via the `SortedMap` constructor, but the view's range restrictions do not become insertion limits on a new `TreeMap`.

## 14. Re-reading a range call to yourself

Before running it, paraphrase the call into a complete sentence: "in this order, take keys after or equal to which bound, before or equal to which bound, and the result is a view of which data."

When that sentence is clear, the boolean flags become less of a memorization exercise. `headMap`, `tailMap`, and `subMap` are ways to express key domains; choosing the right bounds and understanding shared data are both needed to use them properly.
