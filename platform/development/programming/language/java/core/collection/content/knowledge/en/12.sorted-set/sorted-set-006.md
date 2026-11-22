# NavigableSet: lower, floor, ceiling, and higher

## 1. From checking element presence to finding an element near a threshold

`contains(x)` only answers whether an element corresponding to `x` exists in the set. Many problems ask a different question:

- What is the closest element before the threshold?
- What is the largest value not exceeding the limit?
- What is the smallest value meeting or exceeding the requirement?
- If we skip the threshold itself when it is present, what is the next element?

`NavigableSet<E>` extends a sorted set to support directional searches like these. The four core methods are `lower`, `floor`, `ceiling`, and `higher`.

For integers sorted in ascending natural order:

| Method | Condition to satisfy | Which candidate element is chosen? |
| --- | --- | --- |
| `lower(x)` | Less than x, denoted `< x` | Largest among elements less than x |
| `floor(x)` | Less than or equal to x, `≤ x` | Largest among elements not exceeding x |
| `ceiling(x)` | Greater than or equal to x, `≥ x` | Smallest among elements meeting or exceeding x |
| `higher(x)` | Greater than x, `> x` | Smallest among elements greater than x |

All four return a matching element currently in the set, or `null` if there is no candidate. They do not return an index, do not create a new value to fit the threshold, and do not automatically remove the found element. [NavigableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

An easy-to-remember distinction:

- `lower` and `higher` are **strict** relations: they exclude elements equivalent to the threshold.
- `floor` and `ceiling` are **inclusive** relations: they can return an element equivalent to the threshold.

The terms "less than" and "greater than" in the contract follow the **set's ordering**. For ascending natural numbers, that is the familiar numeric relation. With a different `Comparator` or a reversed view, you must interpret them according to the ordering currently in use.

## 2. Choosing the right declared type to call these methods

A common usage on Java 17:

```java
NavigableSet<Integer> values =
        new TreeSet<>(List.of(10, 20, 30, 40));
```

Type hierarchy:

```text
Set
  ↑
SortedSet
  ↑
NavigableSet
  ↑
TreeSet implements the corresponding capabilities
```

`Set` represents a collection with no duplicates; `SortedSet` adds ordering; `NavigableSet` adds the ability to find neighboring values around a threshold.

If a variable is declared as `Set<Integer>`, that interface does not provide `floor` or `ceiling`, even though the actual object might be a `TreeSet`. When an API or algorithm truly needs this navigation capability, use a declared type that accurately expresses that requirement.

The signatures have the form:

```java
E lower(E value);
E floor(E value);
E ceiling(E value);
E higher(E value);
```

The snippet above shows method signatures, not a standalone program. With `NavigableSet<Integer>`, the result has type `Integer`, so it can be `null`.

`TreeSet` is an ordered tree-based implementation. Do not assume that every `Set`, especially an arbitrary `HashSet`, has these four methods or the same search model.

## 3. Where do they actually differ when the threshold is present?

Given the set:

```text
[10, 20, 30, 40]
```

### 3.1. Threshold 20 is already in the set

```text
10 -------- 20 -------- 30 -------- 40
            ↑
          threshold
```

Results:

| Call | Result | Explanation |
| --- | --- | --- |
| `lower(20)` | `10` | Skips 20 itself, picks the largest element still less than 20 |
| `floor(20)` | `20` | Inclusive, so 20 qualifies and is the closest candidate on this side |
| `ceiling(20)` | `20` | Inclusive, so there is no need to move up to 30 |
| `higher(20)` | `30` | Skips 20 itself, picks the smallest element still greater than 20 |

If you are looking for "the next value after the current value", `higher` usually expresses the need to skip the current value. Using `ceiling` could return that same value again.

Similarly, "the previous value" under a strict relation is `lower`; "the closest value not exceeding the current one" is `floor`.

### 3.2. Threshold 25 is not in the set

```text
10 -------- 20 ---- 25 ---- 30 -------- 40
                    ↑
                  threshold
```

Results:

```text
lower(25)   = 20
floor(25)   = 20
ceiling(25) = 30
higher(25)  = 30
```

Because there is no element equivalent to `25`, allowing or excluding equality does not change the candidate set in this example.

That does not make the method pairs synonymous. They only happen to produce the same result when no element equals the threshold under the set's ordering.

The threshold does not need to exist in the set beforehand. Do not insert `25` first just to query its neighbors and then remove it; that modifies the data unnecessarily and can alter the meaning of the set.

### 3.3. Why isn't floor(25) equal to 10?

Both `10` and `20` do not exceed `25`, but `floor` chooses the **largest element** among the candidates. Likewise, both `30` and `40` exceed `25`, but `ceiling` chooses the **smallest element** among the candidates on that side.

These methods do not return an arbitrary element merely because it satisfies the comparison operator.

## 4. Boundaries, empty sets, and the meaning of null

Still using `[10, 20, 30, 40]`:

| Threshold | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `5` | `null` | `null` | `10` | `10` |
| `10` | `null` | `10` | `10` | `20` |
| `20` | `10` | `20` | `20` | `30` |
| `25` | `20` | `20` | `30` | `30` |
| `40` | `30` | `40` | `40` | `null` |
| `45` | `40` | `40` | `null` | `null` |

`null` does not necessarily mean the set is empty. With threshold `5`, the set has four elements, but none of them lie on the lower side.

With an empty set and a valid query threshold, all four methods have no candidates and return `null`.

### 4.1. Checking for null before unboxing to a primitive type

Clear handling:

```java
// Illustrative snippet: values is a NavigableSet<Integer> that does not contain null.
Integer previous = values.floor(5);
if (previous == null) {
    System.out.println("Không có giá trị không vượt quá 5");
} else {
    int usableValue = previous;
    System.out.println("Giá trị được chọn: " + usableValue);
}
```

Error-prone approach:

```java
// May throw NullPointerException when floor finds no result.
int previous = values.floor(5);
```

The error occurs when Java automatically unboxes a `null` `Integer` into an `int`. It is not that `floor` itself throws an "element not found" exception for that valid query.

Do not default to `0` or `-1` as a fallback value if those numbers could be valid data. The policy when no match is found must be decided according to the application's requirements.

### 4.2. null as a result vs. null as an element are two different things

The natural-number examples in this article do not store `null` elements, so `null` returned from navigation clearly means no candidate was found.

A `Comparator` can be designed to allow `null`, for instance via `Comparator.nullsFirst`. In that case, a `null` element itself can be a valid result under the ordering, making the return value ambiguous.

For example, with an ordering that places `null` before all strings and the set `[null, b]`, `lower("b")` can return the stored `null` element. A single return value looks identical to the case where no candidate exists.

If you must use such a data type, you need to account for both whether the set contains `null` and its relation to the threshold. When there is no requirement to store `null`, keeping the element domain `null`-free makes the navigation API easier to use. The `NavigableSet` documentation also notes this ambiguity. [NavigableSet: null values](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

Do not use `null` as a "default threshold" for a set that does not support it. An incomparable argument or an unaccepted `null` can lead to an exception; that is an input-domain error, distinct from a valid query with no result.

## 5. Complete program: all four lookups and handling absent results

Save the entire code to **NavigableNeighborsDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableNeighborsDemo {
    private static void show(NavigableSet<Integer> values, int target) {
        System.out.println("target " + target
                + ": lower=" + values.lower(target)
                + ", floor=" + values.floor(target)
                + ", ceiling=" + values.ceiling(target)
                + ", higher=" + values.higher(target));
    }

    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40));
        System.out.println("values: " + values);
        show(values, 20);
        show(values, 25);
        show(values, 5);
        show(values, 45);
        System.out.println("after queries: " + values);
        System.out.println("size: " + values.size());

        NavigableSet<Integer> empty = new TreeSet<>();
        System.out.println("empty set:");
        show(empty, 20);

        Integer previous = values.floor(5);
        if (previous == null) {
            System.out.println("no value at or below 5");
        }
        try {
            int unsafe = values.floor(5);
            System.out.println("unsafe value: " + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("unboxing absent result: NullPointerException");
        }

        NavigableSet<Integer> widths =
                new TreeSet<>(List.of(320, 640, 960, 1280));
        System.out.println("smallest width at least 700: " + widths.ceiling(700));
        System.out.println("largest width at most 700: " + widths.floor(700));
        System.out.println("next above 640: " + widths.higher(640));
        System.out.println("previous below 640: " + widths.lower(640));
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 NavigableNeighborsDemo.java
java NavigableNeighborsDemo
```

Stdout:

```text
values: [10, 20, 30, 40]
target 20: lower=10, floor=20, ceiling=20, higher=30
target 25: lower=20, floor=20, ceiling=30, higher=30
target 5: lower=null, floor=null, ceiling=10, higher=10
target 45: lower=40, floor=40, ceiling=null, higher=null
after queries: [10, 20, 30, 40]
size: 4
empty set:
target 20: lower=null, floor=null, ceiling=null, higher=null
no value at or below 5
unboxing absent result: NullPointerException
smallest width at least 700: 960
largest width at most 700: 640
next above 640: 960
previous below 640: 320
```

How to read the output:

1. Present threshold `20` demonstrates the difference between strict and inclusive relations.
2. Absent threshold `25` still queries normally.
3. Out-of-bounds thresholds on both sides show that having no candidates on one side does not mean the set is empty.
4. The set and its size remain unchanged after the queries.
5. An empty set returns `null` for valid queries.
6. The unsafe unboxing block intentionally catches `NullPointerException` to demonstrate the bug to avoid.
7. The width example uses `ceiling` to pick the smallest size meeting the requirement, and `floor` to pick the largest size not exceeding the limit.

The four methods only find and return an element; they do not retrieve and remove it. Do not confuse them with operations like `pollFirst` or `pollLast`, which mutate the set under their own contracts.

## 6. "Less than" and "equal" depend on the set's ordering

### 6.1. Relations are defined by Comparator or Comparable

With ordering `c`, the conditions can be read as:

```text
lower(target):   c.compare(candidate, target) < 0
floor(target):   c.compare(candidate, target) <= 0
ceiling(target): c.compare(candidate, target) >= 0
higher(target):  c.compare(candidate, target) > 0
```

After selecting the side that satisfies the condition, the method returns the candidate closest to the threshold under that ordering.

When using natural ordering, `compareTo` fulfills the corresponding role. Do not mentally replace all relations with ordinary numeric comparison if the set holds strings, domain objects, or uses a custom comparator.

### 6.2. Inclusive means accepting cases where compare returns 0

If a set of strings uses a case-insensitive comparator and holds `"Bee"`, then querying `"BEE"` can yield:

```text
floor("BEE")   → "Bee"
ceiling("BEE") → "Bee"
```

The returned element is the representative stored in the set. It is not required to be the argument reference itself or a string equal to the argument under `String.equals`.

A case-insensitive comparator for strings is inconsistent with `String.equals`; using it in a `TreeSet` requires understanding that it does not fully satisfy the general `Set` contract. This example serves to illustrate the comparison mechanism, not to recommend ignoring that consistency in design. [TreeSet: ordering and equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

`lower` and `higher` skip all elements equivalent under the ordering, not just an object with the same reference.

### 6.3. Do not mutate data used for ordering while an element is in the set

If the comparison uses a mutable field, an element's position in the structure may no longer be valid after that field is modified.

Navigation results can then no longer be reasoned about as they would be with a set whose rules are stable. Prefer immutable comparison keys and a comparator with stable behavior for as long as the set is in use.

## 7. descendingSet reverses the search direction too

`descendingSet()` returns a view whose ordering is the reverse of the original set. It does not merely change `for-each` iteration order; navigation operations are also interpreted in the reversed order.

Given an ascending original set:

```text
ascending:  [10, 20, 30, 40]
descending: [40, 30, 20, 10]
```

In descending order, `30` comes before `25`, and `20` comes after `25`. Therefore:

```text
descending.lower(25)   = 30
descending.floor(25)   = 30
descending.ceiling(25) = 20
descending.higher(25)  = 20
```

There is no contradiction with the definition table: the terms before/after and less/greater are being read according to the view's ordering.

If `d = s.descendingSet()`, the dual relationships are:

| Query on d | Equivalent on s |
| --- | --- |
| `d.lower(x)` | `s.higher(x)` |
| `d.floor(x)` | `s.ceiling(x)` |
| `d.ceiling(x)` | `s.floor(x)` |
| `d.higher(x)` | `s.lower(x)` |

Equality still retains its inclusive nature; only the direction of the relation is reversed.

The view is backed by the original set's data. When the underlying data changes, subsequent query results can also change. It is not a frozen snapshot copied at the time of the call. [NavigableSet.descendingSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html#descendingSet())

## 8. Queries on a view search only within the view's range

Suppose the original set is `[10, 20, 30, 40]`, but the current variable is a view containing only elements in the range from `20` inclusive to `40` exclusive:

```java
NavigableSet<Integer> window = ascending.subSet(20, true, 40, false);
```

The elements visible through `window` are `[20, 30]`.

When calling:

```text
ascending.lower(20)   → 10
window.lower(20)      → null

ascending.ceiling(35) → 40
window.ceiling(35)    → null
```

`10` and `40` exist in the original set, but they are outside the range exposed by `window`. Navigation does not step outside that range to return a candidate from the backing set.

When you encounter an unexpected `null`, check whether the object receiving the call is the whole set, a reversed view, or a bounded view. A variable name or the `NavigableSet` type alone is not enough to know the actual data range.

This section only illustrates the candidate scope of queries; creating and modifying views have their own contracts. [NavigableSet: range views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

## 9. Complete program: reversed order, bounded range, and custom Comparator

Save the code to **NavigableOrderDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableOrderDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> ascending =
                new TreeSet<>(List.of(10, 20, 30, 40));
        NavigableSet<Integer> descending = ascending.descendingSet();

        System.out.println("ascending: " + ascending);
        System.out.println("descending: " + descending);
        System.out.println("descending lower 25: " + descending.lower(25));
        System.out.println("descending floor 25: " + descending.floor(25));
        System.out.println("descending ceiling 25: " + descending.ceiling(25));
        System.out.println("descending higher 25: " + descending.higher(25));
        System.out.println("descending floor 20: " + descending.floor(20));
        System.out.println("descending ceiling 20: " + descending.ceiling(20));
        System.out.println("lower/higher dual: "
                + descending.lower(25).equals(ascending.higher(25)));

        NavigableSet<Integer> window = ascending.subSet(20, true, 40, false);
        System.out.println("window: " + window);
        System.out.println("ascending lower 20: " + ascending.lower(20));
        System.out.println("window lower 20: " + window.lower(20));
        System.out.println("ascending ceiling 35: " + ascending.ceiling(35));
        System.out.println("window ceiling 35: " + window.ceiling(35));

        NavigableSet<String> words =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        words.addAll(List.of("ant", "Bee", "dog"));
        String target = "BEE";
        System.out.println("words: " + words);
        System.out.println("word lower: " + words.lower(target));
        System.out.println("word floor: " + words.floor(target));
        System.out.println("word ceiling: " + words.ceiling(target));
        System.out.println("word higher: " + words.higher(target));
        System.out.println("floor equals query text: "
                + words.floor(target).equals(target));
        System.out.println("words after queries: " + words);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NavigableOrderDemo.java
java NavigableOrderDemo
```

Stdout:

```text
ascending: [10, 20, 30, 40]
descending: [40, 30, 20, 10]
descending lower 25: 30
descending floor 25: 30
descending ceiling 25: 20
descending higher 25: 20
descending floor 20: 20
descending ceiling 20: 20
lower/higher dual: true
window: [20, 30]
ascending lower 20: 10
window lower 20: null
ascending ceiling 35: 40
window ceiling 35: null
words: [ant, Bee, dog]
word lower: ant
word floor: Bee
word ceiling: Bee
word higher: dog
floor equals query text: false
words after queries: [ant, Bee, dog]
```

How to read the output:

1. The descending view reverses the direction of all four lookups.
2. When threshold `20` has an equivalent element, `floor` and `ceiling` can still return `20` in both directions.
3. The `lower/higher dual` line checks a specific case where both results are present; in general code, you still need to handle `null` results.
4. The bounded view does not return candidates outside its range.
5. The custom comparator causes `floor("BEE")` and `ceiling("BEE")` to return the stored representative `"Bee"`.
6. The string queries do not modify the set.

Both standalone programs in this article were compiled with `--release 17` and run to verify matching stdout. This option checks the language/API level and produces Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 10. Choosing a method by writing out the requirement clearly

Instead of memorizing names in isolation, translate the question into an inequality and identify which side to pick from.

| Question on ascending numbers | Condition | Method |
| --- | --- | --- |
| Previous value, skipping the current value | `candidate < target`, pick largest | `lower` |
| Largest value not exceeding the limit | `candidate <= limit`, pick largest | `floor` |
| Smallest size sufficient to meet the requirement | `candidate >= request`, pick smallest | `ceiling` |
| Next value strictly greater than the current one | `candidate > current`, pick smallest | `higher` |

Example with supported widths `[320, 640, 960, 1280]`:

- Minimum requirement `700`: `ceiling(700)` picks `960`.
- Maximum limit `700`: `floor(700)` picks `640`.
- Size strictly greater than `640`: `higher(640)` picks `960`.
- Size strictly less than `640`: `lower(640)` picks `320`.

If no size satisfies the requirement, the result is `null`; the program needs a branch to handle an unmet requirement rather than assuming the largest element is always sufficient.

### 10.1. Do not simulate strict relations by adding or subtracting 1

Do not default to replacing `lower(x)` with `floor(x - 1)` or `higher(x)` with `ceiling(x + 1)`.

That approach depends on a discrete integer domain, can hit numeric overflow boundaries, and does not apply to strings or other domain comparators. The strict methods already express the exact semantics without fabricating another threshold.

### 10.2. This is not Math.floor rounding

`floor(25)` on the set `[10, 20, 30, 40]` returns the existing element `20`. It does not perform arithmetic rounding to produce an integer from a floating-point value.

Similarly, `ceiling` on a set does not synthesize a new element. It selects an existing representative that satisfies the relation.

### 10.3. Neither method automatically picks the nearest by absolute distance

Given the set `[20, 30]` and threshold `29`:

```text
floor(29)   = 20
ceiling(29) = 30
```

`30` is closer to `29` by arithmetic distance, yet `floor` must still return the side that does not exceed the threshold.

If the requirement is the nearest by distance, you usually need to fetch candidates from both sides and compare distances, handling a missing side and a tie-breaking rule when distances are equal. That is an additional algorithm, not the default meaning of `floor` or `ceiling`.

For types without a natural distance metric, such as string codes, "nearest" must be defined by the requirements rather than inferred solely from having an ordering.

## 11. Search mechanism and how far you need to understand its cost

`TreeSet` is backed by the ordered tree of `TreeMap`. You can think of `floor` as progressively narrowing the search region while keeping track of the best candidate seen so far on the side not exceeding the threshold.

If a value equal to the threshold under comparison is encountered, an inclusive operation can return that candidate. For a strict operation, it must still search before or after rather than accepting the equal case.

Analysis of `TreeSet`'s balanced-tree implementation gives neighbor lookups a step count proportional to the tree height, commonly described as O(log n) comparisons. This is an analysis tied to the implementation structure, not an absolute timing guarantee or a mandatory requirement for every class implementing `NavigableSet`. The cost of each individual comparison must also be considered if keys are complex. [TreeMap: underlying tree structure](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [OpenJDK 17 TreeMap source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java)

When you already have a suitable `NavigableSet`, there is no need to convert the entire set into a list and scan it linearly for each threshold lookup. Nor should you probe by inserting a dummy argument to deduce its adjacent element, since these four methods are already direct read operations.

Results depend on the current state of the set. Multiple separate calls do not automatically form an atomic snapshot if the program allows another party to modify the data in between. The examples in this article assume a stable set during queries.

## 12. Common mistakes

| Misconception or mistake | Problem | How to fix |
| --- | --- | --- |
| Thinking lower and floor are always the same | Misses the case where the threshold has an equivalent element | Check whether equality should be included |
| Using ceiling to find the element after the current one | May return the current element itself | Use higher when a strict relation is needed |
| Only querying a threshold after contains returns true | The threshold is not required to belong to the set | Call the navigation method directly |
| Expecting floor to return any smaller element | Ignores the requirement to pick the largest candidate on that side | Identify both the condition and the extremum |
| Assigning the result directly to int | May auto-unbox null and throw an exception | Receive into Integer and handle the absent case |
| Seeing null and concluding the set is empty | Candidates may simply be missing on one side or within a view | Check the range and query direction |
| Keeping ascending-number intuition when using descendingSet | The relation direction has been reversed | Read according to the view's ordering |
| Thinking floor returns the exact query object | It returns the stored representative under the comparison rule | Account for the Comparator and compare returning 0 |
| Expecting a bounded view to search outside its range | Candidates must belong to the view's range | Call the method on the right set |
| Using floor to pick the nearest by absolute distance | Only picks from the side not exceeding the threshold | Fetch both sides and apply a distance metric if needed |
| Adding/subtracting 1 to replace lower/higher | Not general and can hit numeric bounds | Use the proper method |
| Assuming the query retrieves and removes the element | These four methods are read operations | Use dedicated mutating operations when actually needed |

When faced with an unexpected result, check: which set is receiving the call, which ordering is in use, whether the threshold has an equivalent element, whether the target side is inclusive, and whether the candidate is excluded by a view's range.

## 13. Self-practice and verification

### Exercise 1: distinguishing equality

Given a `NavigableSet<Integer>` in natural order containing `[5, 12, 18, 27]`.

Fill in the results:

| Threshold | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `12` | ? | ? | ? | ? |
| `15` | ? | ? | ? | ? |
| `4` | ? | ? | ? | ? |
| `30` | ? | ? | ? | ? |

Check your answers:

| Threshold | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `12` | `5` | `12` | `12` | `18` |
| `15` | `12` | `12` | `18` | `18` |
| `4` | `null` | `null` | `5` | `5` |
| `30` | `27` | `27` | `null` | `null` |

### Exercise 2: reversing the order

Take the descending view of the set from Exercise 1. Predict the four results for threshold `15`.

Check your answers:

```text
lower(15)   = 18
floor(15)   = 18
ceiling(15) = 12
higher(15)  = 12
```

Explain using descending order rather than mechanically memorizing the four numbers.

### Exercise 3: choosing by requirement

The set of supported sizes is `[100, 250, 500]`:

1. Smallest size at least `200`: `ceiling(200)` → `250`.
2. Largest size not exceeding `200`: `floor(200)` → `100`.
3. Next size strictly greater than `250`: `higher(250)` → `500`.
4. Size strictly less than `100`: `lower(100)` → `null`.

The last item requires a no-result branch, not an implicit fallback numeric value.

### Exercise 4: explaining an unboxing error

With the set from Exercise 1, the snippet:

```java
int result = values.ceiling(30);
```

can throw `NullPointerException` because `ceiling(30)` has no candidate and returns `null`. Fix it by using an `Integer` variable and a check branch before using it as an `int`.

### Exercise 5: distinguishing search scope

The original set is `[5, 12, 18, 27]`, and a view contains only `[12, 18]`.

`floor(25)` on both objects is `18`, whereas `ceiling(20)` on the original set is `27`, and on the view there is no candidate so it is `null`.

What needs to be explained is the candidate range, not saying that an out-of-set threshold always causes the method to fail.

## 14. Reference documentation

- [NavigableSet Java 17 — four lookup operations, views, and null values](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)
- [TreeSet Java 17 — ordered set implementation and Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [Comparator — ordering rules and consistency with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [TreeMap — underlying tree structure for understanding the search mechanism](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
