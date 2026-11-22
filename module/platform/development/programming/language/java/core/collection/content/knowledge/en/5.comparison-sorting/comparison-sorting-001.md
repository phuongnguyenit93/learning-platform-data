# Comparable and Natural Ordering

When you have a list of numbers, "sorting in ascending order" is usually clear enough. However, with objects such as a software version, an invoice, or a product, the program needs to know **which object comes before which**.

`Comparable<T>` allows a type to declare its own comparison rule against compatible objects. That default rule is called the **natural ordering** of the type.

This article explains the meaning of natural ordering, the contract of `compareTo`, how to implement it yourself, and how a comparison rule affects collections. The complete programs use Java 17 APIs, have been compiled with `--release 17`, and run to verify stdout. The remaining short snippets illustrate a single operation or method body rather than standalone runnable files.

After this lesson, you should be able to:

- Interpret the negative, zero, or positive result of `compareTo`.
- Explain when a type should have a natural ordering.
- Implement multi-field comparison without causing integer overflow.
- Distinguish "equivalence in ordering" from `equals`.
- Predict the impact of `compareTo == 0` on `TreeSet` and `TreeMap` keys.

## 1. What Problem Does Natural Ordering Solve?

Suppose we have the following versions:

```text
2.0.0
1.10.0
1.2.0
```

We want to compare the major version first, then the minor version, and finally the patch version:

```text
1.2.0 < 1.10.0 < 2.0.0
```

If every place that uses the list rewrites the comparison rule on its own, it is easy for one place to compare numerically while another compares lexicographically as strings. A rule attached directly to the `Version` type ensures that operations relying on natural ordering share a single meaning.

### "Natural" Is a Convention of the Type

Natural ordering is not a single universal rule for every object:

- `Integer` is ordered by numerical value.
- `String` is ordered lexicographically by UTF-16 code units.
- A simple version type can choose an ordering based on three numeric components.
- A product type may have multiple ordering needs—such as by price, name, or arrival date—without a single obvious choice to serve as the default.

Therefore, do not add `Comparable` merely to make a sort call compile. First ask: **does this type have a stable, meaningful default rule that all callers understand in the same way?**

If you only need a custom ordering for a specific screen, an external rule via `Comparator` is usually more appropriate. `Comparator` is mentioned here to separate responsibilities; the focus of this article is the ordering declared by the type itself.

### Comparing Does Not Sort by Itself

Calling:

```java
first.compareTo(second);
```

only returns the result of comparing two objects. It does not swap them and does not automatically sort a list.

A sorting algorithm calls that rule repeatedly to decide the order of elements. Sorted data structures also use the rule to locate storage and lookup positions.

## 2. Reading the Comparable<T> Interface

A simplified view of the interface:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

This is an illustrative signature, not code to redefine the standard library interface yourself.

In the complete program later in this article, the `Version` type declares `implements Comparable<Version>`.

`Comparable<Version>` states that instances of the class provide a comparison with a compatible `Version` object. In an actual implementation, `compareTo` must be a `public` method.

You should always use a specific type parameter rather than implementing raw `Comparable`. A specific type lets the compiler check usage and reduces the need for unsafe casts.

### Meaning of the Return Value

For `x.compareTo(y)`:

| Result | Meaning |
| --- | --- |
| Less than `0` | `x` comes before `y` |
| Equal to `0` | `x` and `y` have equal rank under the ordering rule |
| Greater than `0` | `x` comes after `y` |

What matters is the **sign**, not a specific magnitude.

The right way to check:

```java
if (x.compareTo(y) < 0) {
    // x comes before y.
}
```

Do not write `x.compareTo(y) == -1` to detect every "comes before" case. A valid method may return `-5`, `-32`, or any other negative integer.

### Zero Does Not Mean the Same Object Instance

Two distinct objects in memory can produce `compareTo == 0`. Its direct meaning is that the ordering rule treats them as equivalent in rank.

To know whether this equivalence matches the type's notion of equality, you must also consider `equals`. This is a critical point when working with sorted sets and maps.

## 3. APIs That Use Natural Ordering

| API or Structure | How Natural Ordering Is Used |
| --- | --- |
| `Collections.sort(list)` | Sorts the list according to the natural ordering of its elements |
| `list.sort(null)` | Passes no custom comparator; uses natural ordering |
| `Arrays.sort(objectArray)` | Sorts an array of mutually comparable objects |
| `Collections.min(values)`, `Collections.max(values)` | Finds the minimum or maximum element according to natural ordering |
| `new TreeSet<E>()` | Organizes elements by natural ordering when no custom comparator is provided |
| `new TreeMap<K, V>()` | Organizes keys by natural ordering when no custom comparator is provided |

Two things must be distinguished:

1. An `ArrayList` does not automatically sort itself after `add`. You must explicitly request sorting when needed.
2. A `TreeSet` maintains element order within the structure; it also uses comparison results to detect duplicate elements.

`Comparable` applies to objects. Overloads such as `Arrays.sort(int[])` handle primitive arrays under their own contracts; primitive `int` values are not objects implementing `Comparable`.

### Prerequisites for Use

- Elements or keys must be mutually comparable under the active rule.
- A list being sorted must support modifying element positions.
- The data must satisfy the `null` policy.
- `Collections.min` and `max` require non-empty data; an empty collection throws `NoSuchElementException`.

For example, `List.of(...)` is unmodifiable and cannot be sorted in place directly. You can copy the data into an `ArrayList` before sorting, as shown in the program below.

## 4. Observing the Built-in Ordering of Integer and String

Create the file **`NaturalOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class NaturalOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(10, 2, -3, 2));
        Collections.sort(numbers);
        System.out.println("numbers = " + numbers);
        System.out.println("min = " + Collections.min(numbers));
        System.out.println("max = " + Collections.max(numbers));

        String[] words = {"a", "B", "A", "b", "aa", "a2", "a10"};
        Arrays.sort(words);
        System.out.println("words = " + Arrays.toString(words));
        System.out.println("text 1.10 vs 1.2 = "
                + Integer.signum("1.10".compareTo("1.2")));
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 NaturalOrderDemo.java
java -Dfile.encoding=UTF-8 NaturalOrderDemo
```

Stdout:

```text
numbers = [-3, 2, 2, 10]
min = -3
max = 10
words = [A, B, a, a10, a2, aa, b]
text 1.10 vs 1.2 = -1
```

### Reading the Results

- Integers are sorted by numerical value, not by their string representation.
- Both `2` elements remain in the list after sorting. Sorting a list does not deduplicate it.
- In `String`'s natural ordering, `"A"` and `"B"` come before lowercase letters in this dataset.
- When one string is a prefix of another, the shorter string comes first: `"a"` comes before `"a10"`.
- `"a10"` comes before `"a2"` because the first differing position compares `'1'` against `'2'`, rather than parsing the digit sequence as a number.
- The string `"1.10"` comes before `"1.2"`, whereas numeric version `1.10` should come after `1.2` under our chosen version rule.

This article uses `Integer.signum(...)` purely to display the sign as `-1`, `0`, or `1`. That is a normalization for readable output, not a requirement that every `compareTo` must return only those three values.

The natural ordering of `String` is not a locale-aware rule for sorting human names across languages. When you need locale-sensitive or case-insensitive ordering, design a dedicated comparison policy and verify its character handling requirements.

## 5. The Contract That compareTo Must Obey

A single sort operation may compare a pair of objects in either direction and at different times. If the results are contradictory, the data structure or algorithm can no longer rely on a consistent ordering relation.

Let `sign(v)` denote the sign of integer `v`: negative, zero, or positive.

### 5.1. Reversing the Direction Must Reverse the Sign

For two valid objects:

```text
sign(x.compareTo(y)) == -sign(y.compareTo(x))
```

If `x` comes before `y`, then `y` must come after `x`. You must never write a rule that can conclude each object is smaller than the other.

Check the relationship via the sign; `x.compareTo(y)` is not required to equal the exact arithmetic negation of `y.compareTo(x)`.

Part of the contract also requires symmetry of comparability: if comparing `x` with `y` throws an exception because they are not mutually comparable, the reverse direction must not pretend to be a valid comparison either.

### 5.2. Transitivity

If `x` comes after `y` and `y` comes after `z`, then `x` must come after `z`:

```text
x > y and y > z  =>  x > z
```

A circular rule such as "A before B, B before C, C before A" cannot form a valid natural ordering.

### 5.3. Two Equivalent Objects Must Relate Identically to Any Third Object

If:

```text
x.compareTo(y) == 0
```

then for every `z` in the compatible comparison domain:

```text
sign(x.compareTo(z)) == sign(y.compareTo(z))
```

Once a rule treats `x` and `y` as equal in rank, it must not place one before `z` and the other after `z`.

### 5.4. Comparing an Object to Itself Must Return Zero

For a valid object whose state does not change:

```text
x.compareTo(x) == 0
```

This is a small but useful sanity check when writing custom types.

### 5.5. The Rule Must Remain Stable During Use

Comparison results must not depend on randomness, the current wall-clock time, or uncontrolled external state.

If values participating in the ordering can change, you must have a clear usage policy—especially while the object is stored as an element or key inside a sorted data structure.

Violating the contract can lead to wrong sort results, unreliable data structure behavior, or runtime exceptions when the sorting algorithm detects a contradiction. Not every contract violation is caught immediately by Java; a single error-free run does not prove the rule is valid.

## 6. Implementing Natural Ordering for a Version Type

Let us build a version type consisting of three non-negative integers:

```text
major.minor.patch
```

Rule:

1. Compare `major`.
2. If tied, compare `minor`.
3. If still tied, compare `patch`.

This is **multi-field lexicographical comparison**: stop at the first field that produces a difference. Here "lexicographical" describes how components are prioritized in sequence; each component itself is still compared numerically.

Examples:

| Two Versions | Deciding Field |
| --- | --- |
| `1.99.99` and `2.0.0` | `major` |
| `1.2.9` and `1.10.0` | `minor` |
| `1.2.3` and `1.2.4` | `patch` |
| `1.2.3` and `1.2.3` | No difference |

This example type only represents a triple of numbers. It does not implement the full Semantic Versioning specification, pre-release labels, build metadata, or string parsing.

### Complete Program

Create the file **`VersionComparableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

public class VersionComparableDemo {
    public record Version(int major, int minor, int patch)
            implements Comparable<Version> {
        public Version {
            if (major < 0 || minor < 0 || patch < 0) {
                throw new IllegalArgumentException("Version parts must be non-negative");
            }
        }

        @Override
        public int compareTo(Version other) {
            int result = Integer.compare(major, other.major);
            if (result != 0) {
                return result;
            }

            result = Integer.compare(minor, other.minor);
            if (result != 0) {
                return result;
            }

            return Integer.compare(patch, other.patch);
        }

        @Override
        public String toString() {
            return major + "." + minor + "." + patch;
        }
    }

    public static void main(String[] args) {
        Version first = new Version(1, 2, 0);
        Version same = new Version(1, 2, 0);
        Version later = new Version(1, 10, 0);

        List<Version> versions = new ArrayList<>(List.of(
                new Version(2, 0, 0), later, first, same));
        versions.sort(null);

        System.out.println("sorted = " + versions);
        System.out.println("1.10.0 vs 1.2.0 = "
                + Integer.signum(later.compareTo(first)));
        System.out.println("same compareTo = " + first.compareTo(same));
        System.out.println("same equals = " + first.equals(same));
        System.out.println("set = " + new TreeSet<>(versions));
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 VersionComparableDemo.java
java -Dfile.encoding=UTF-8 VersionComparableDemo
```

Stdout:

```text
sorted = [1.2.0, 1.2.0, 1.10.0, 2.0.0]
1.10.0 vs 1.2.0 = 1
same compareTo = 0
same equals = true
set = [1.2.0, 1.10.0, 2.0.0]
```

### Why Does This Implementation Fit the Chosen Model?

- A `record` provides components that cannot be reassigned after creation, which suits keeping comparison keys stable.
- The constructor rejects negative components, keeping the value domain valid by design.
- `Integer.compare` compares numerically without subtraction that could overflow.
- Later fields are evaluated only when earlier fields are equal.
- Two versions return `0` when all three components are equal.
- The record-generated `equals` method also checks those same three components, so equality and ordering equivalence are consistent in this example.
- `toString` is purely for display. Sorting does not rely on the string it returns.

The sorted list keeps both `1.2.0` instances. When transferred into a `TreeSet`, those two versions collapse into a single element because the ordering rule considers them equivalent.

### Why Not Sum All the Components?

Taking the sum `major + minor + patch` destroys component priority. For example, `1.9.0` and `2.0.0` would be ordered by their sum rather than by major version first.

Packing them into `major * 10000 + minor * 100 + patch` also imposes strict limits on each component's range and risks integer overflow. Comparing field by field preserves the exact semantics without encoding multiple fields into a single number.

## 7. Avoiding Subtraction and Sign Bugs

A common error-prone pattern is:

```java
return this.value - other.value;
```

With fixed-width integers, subtraction can overflow and produce the opposite sign of the actual relationship.

For example:

```text
Integer.MIN_VALUE < 1
```

yet the subtraction `Integer.MIN_VALUE - 1` overflows into a positive number. A comparison rule written that way will claim the smaller number comes after the larger number.

The proper way to compare an integer field:

```java
return Integer.compare(this.value, other.value);
```

Similarly, use `Long.compare` for `long` and the appropriate comparison methods for other types. For floating-point numbers, you must also understand the policy for special values (`NaN`, `-0.0`, `+0.0`); never subtract them and cast the result to `int`.

### Do Not Negate an Arbitrary Result with Unary Minus

Writing `-other.compareTo(this)` can fail if the returned value is `Integer.MIN_VALUE`, because `Integer.MIN_VALUE` has no positive counterpart representable as an `int`.

If you need to reverse the comparison direction, use a safe approach such as swapping the arguments in a safe comparison helper or applying a reverse comparator. Do not turn a UI requirement for descending display into an ad-hoc mutation of natural ordering.

## 8. Consistency with equals

A natural ordering is **consistent with equals** when:

```text
x.compareTo(y) == 0  if and only if  x.equals(y)
```

This is strongly recommended, even though the `Comparable` specification documents real-world standard library classes that are exceptions.

### Why Does It Matter?

Different collection structures determine duplicates using different mechanisms:

| Structure | Primary Mechanism for Equivalence / Uniqueness |
| --- | --- |
| `HashSet`, `HashMap` keys | `equals` together with the `hashCode` contract |
| `TreeSet`, `TreeMap` keys using natural ordering | Result of `compareTo` |
| `List` | Allows duplicate elements; sorting does not remove elements of equal rank |

If `compareTo` only checks a person's age while `equals` checks a user ID, two distinct people of the same age will be treated by a `TreeSet` as the same element.

The fix is not always to tack an arbitrary tie-breaker field onto the end of `compareTo`. First determine **what equality means for the type** and whether ordering by age is truly the type's natural ordering or merely one way of viewing the data.

If you want multiple people of the same age to be retained, the right choice might be a list sorted by age or a sorting rule with an appropriate tie-breaker. Clarify the domain semantics before choosing the data structure.

### Relationship with hashCode

`Comparable` does not replace the `equals`/`hashCode` contract.

- If you override `equals`, you must ensure `hashCode` remains consistent with it.
- `compareTo == 0` does not automatically adjust hash codes.
- A mathematically valid ordering rule can still be inconsistent with `equals`; when that happens, using set or map structures requires careful deliberation and clear documentation.

## 9. BigDecimal: A Real-World Exception

`BigDecimal` clearly illustrates the two perspectives:

- `compareTo` compares numerical value, so `4.0` and `4.00` are considered equal in rank.
- `equals` also considers the scale representation, so those two values are not equal according to `equals`.

This is not a bug in the sorting engine. It is a deliberate difference between the type's equality contract and its ordering contract.

Create the file **`ComparisonPitfallsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparisonPitfallsDemo {
    public static void main(String[] args) {
        int small = Integer.MIN_VALUE;
        int large = 1;

        System.out.println("bad subtraction sign = "
                + Integer.signum(small - large));
        System.out.println("safe comparison sign = "
                + Integer.signum(Integer.compare(small, large)));

        BigDecimal first = new BigDecimal("4.0");
        BigDecimal second = new BigDecimal("4.00");

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(first);
        hashSet.add(second);

        TreeSet<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(first);
        boolean secondAdded = treeSet.add(second);

        TreeMap<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(first, "first");
        treeMap.put(second, "second");

        System.out.println("decimal equals = " + first.equals(second));
        System.out.println("decimal compareTo = " + first.compareTo(second));
        System.out.println("HashSet size = " + hashSet.size());
        System.out.println("TreeSet second added = " + secondAdded);
        System.out.println("TreeSet size = " + treeSet.size());
        System.out.println("TreeMap size = " + treeMap.size());
        System.out.println("TreeMap value = " + treeMap.get(first));
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ComparisonPitfallsDemo.java
java -Dfile.encoding=UTF-8 ComparisonPitfallsDemo
```

Stdout:

```text
bad subtraction sign = 1
safe comparison sign = -1
decimal equals = false
decimal compareTo = 0
HashSet size = 2
TreeSet second added = false
TreeSet size = 1
TreeMap size = 1
TreeMap value = second
```

### Reading the Two Groups of Evidence

**Integer group:**

- Subtraction produces a positive sign that contradicts the actual relationship.
- `Integer.compare` produces the correct negative sign.

**BigDecimal group:**

- `HashSet` retains two elements because they differ according to `equals`.
- `TreeSet` does not add the second element because the comparison returns `0`.
- `TreeMap` has a single key under the ordering rule; the second `put` updates the associated value to `"second"`.

If your system design uses decimal numbers as unique set elements or map keys, you must explicitly choose which notion of "same value" applies. Never treat `TreeSet` and `HashSet` as drop-in replacements that differ only in performance.

There is no single representation normalization that fits every business domain. If a system requires normalizing scale or representation format, enforce that at the data boundary rather than patching things up after noticing unexpected element counts.

## 10. Null, Incompatible Types, and Mutable Data

### Null Has No Position in an Object's Natural Ordering

According to the `Comparable` contract, comparing a valid object with `null` must throw `NullPointerException`.

In the `Version` example, accessing a component of `other` when `other == null` throws that exception naturally. If desired, you can check explicitly at the start of the method to make the failure message clearer.

Do not assume that every sort operation containing `null` will always fail immediately: whether a comparison is actually executed depends on the input data (for example, a single-element list may not compare any pairs). A safe design either rejects/removes `null` upfront or supplies an explicit null policy via a `Comparator` when `null` values need to be placed first or last.

Similarly, `TreeSet` and `TreeMap` using natural ordering are not suitable places to store `null` as a naturally ordered element or key.

### Do Not Arbitrarily Mix Objects from Different Domains

A collection mixing integers, strings, and custom objects does not automatically have a shared natural ordering.

Generics catch many such mismatches at compile time. Using raw types and mixing mutually incomparable objects merely pushes the failure to runtime as a `ClassCastException`.

### Do Not Mutate Comparison Keys While an Object Is Inside a Tree Structure

Suppose an object is placed into a `TreeSet` at a position determined by its current state. If you later mutate a field used by `compareTo`, the tree structure is not notified to relocate the object.

Consequences can include:

- Iteration order no longer reflects current values.
- Lookups or removals fail to behave as expected.
- Uniqueness guarantees become unreliable.

Prefer immutable comparison keys. If a key field must change, remove the object while it still has its old state, apply the change, and re-insert it according to your system's rules. Once an element has been mutated in place inside a tree structure, do not assume a later `remove` call will reliably find it.

A sorted list also does not automatically re-sort itself when an element's fields change. Although there is no internal search tree invariant to corrupt, you must still re-sort the list before relying on the updated order.

## 11. Distinguishing Comparable from Comparator

| Question | `Comparable<T>` | `Comparator<T>` |
| --- | --- | --- |
| Where does the rule live? | Attached to the object type itself | External rule object |
| Primary method | `x.compareTo(y)` | `comparator.compare(x, y)` |
| Typical role | Default ordering of the type | Context-specific ordering strategies |
| Number of policies | One natural ordering published by the type | Can have multiple independent policies |
| Must the target class be modified? | Yes, to declare and implement the interface | Not necessarily |

A type can implement `Comparable` and still be sorted using many different comparators.

If you pass a comparator to a sort operation or data structure, that comparator governs the ordering in that context. Having `compareTo` on the class does not mean the natural ordering is always invoked regardless of configuration.

For example, `Version` chooses ascending numerical version order as its default. A screen that wants to display the newest version first can use a reversed policy in its sort call while leaving the type's natural contract intact.

When a comparator is used with `TreeSet` or `TreeMap`, a zero result from the comparator affects uniqueness in the same way we saw with `compareTo`.

## 12. Workflow for Designing and Verifying a Natural Ordering

### Step 1: Write the Rule in Plain Language

For example:

> One version comes before another if the first differing numeric component—checked in the order major, minor, patch—has a smaller value.

If a description is still vague, such as "more important objects come first," clarify which fields represent importance and how ties are broken.

### Step 2: Align on the Data Domain and the Notion of Equality

Answer these questions:

- Are missing values or `null` allowed?
- Can the object mutate after creation?
- When are two objects considered the same value?
- Does `compareTo == 0` align with `equals`?
- Will the type be used as a key or element in tree-based collections?

### Step 3: Implement Criterion by Criterion Without Lossy Aggregation

Use type-appropriate comparison helpers; return immediately as soon as a higher-priority criterion differs. Only move to the next criterion when the current result is zero.

### Step 4: Verify Signs and Boundary Datasets

A thorough test suite should cover:

| Scenario | What to Verify |
| --- | --- |
| Ordinary smaller/larger pairs | Sign matches the specification |
| Same logical value in two distinct instances | Compares to zero; also check `equals` |
| Swapping the two arguments | Sign flips |
| Three values in strictly increasing sequence | Transitivity holds |
| Two equivalent objects plus a third object | Both relate identically to the third object |
| Values near numeric type boundaries | No wrong signs caused by overflow |
| Objects differing only in the last criterion | Final criterion is not forgotten |
| `null` or out-of-domain data | Clear rejection behavior |

Tests on a handful of sample inputs do not mathematically prove the contract for all inputs. They serve as executable evidence that should be combined with careful reasoning about the rule.

### Step 5: Verify Consumer Collections as Well

- Sort a list and verify adjacent pairs.
- Test elements that compare equal to confirm a list retains all of them.
- Insert into a `TreeSet` and verify the element count matches your uniqueness rule.
- If used as map keys, test `put` with two rank-equivalent keys in a `TreeMap`.
- Cross-check against `equals`/`hashCode`-based collections (`HashSet`, `HashMap`) when applicable.

## 13. Common Mistakes and How to Fix Them

### Returning Only 1 or -1 Without a Zero Case

Omitting the zero case can claim an object is greater than itself or give both comparison directions the same invalid sign. Always handle equal criteria and return `0` when no difference remains.

### Using Subtraction or Lossy Narrowing Casts

Use type-specific comparison methods (`Integer.compare`, `Long.compare`, etc.) rather than turning arithmetic differences into comparison results. In particular, casting a `long` difference down to `int` can discard the high bits that determine the sign.

### Comparing Display Strings Instead of Data Semantics

Version strings are a classic example: `"1.10"` as a string is not compared as two numbers. Compare structured fields when the business meaning is structured.

### Choosing a Secondary Attribute as the Entire Natural Ordering

Two people of the same age or two products with the same price are rarely the exact same logical entity. Before using a single non-unique attribute as a natural ordering, evaluate its impact on `equals` and unique sets/maps.

### Relying on the Current Position in an External List

An element's index, insertion order, or position in an external list should not become a volatile dependency of `compareTo`. The rule must belong to the object's value and its defined comparison domain.

### Confusing Stable Sorting with Deduplication

A stable list sort preserves the relative order of elements that compare equal (`compareTo == 0`). It does not merge them into a single element; it is `TreeSet` that enforces uniqueness based on comparison results.

### Assuming Comparable Automatically Works Across Subclasses

Adding extra fields in a subclass and overriding comparison logic can easily break symmetry with the superclass. Define the comparable domain and symmetry contract carefully; for value types, favoring immutability and restricting inheritance (such as using `record` or `final` classes) keeps the model simple and sound.

## 14. Practice Exercises

### Exercise 1: Predict String Ordering

Change the string array to:

```text
v2, v10, v1, V2, v01
```

Before running the program, predict the natural ordering and explain each position using the first differing character. Contrast this result with "sorting by version number" and "case-insensitive sorting."

### Exercise 2: Verify the Final Criterion

Add the following versions to the version list:

```text
1.2.9
1.2.1
1.2.0
```

Verify that `patch` decides the order only when both `major` and `minor` are tied. Then test very large component values that still fit in `int` to confirm that no combined arithmetic or subtraction causes overflow bugs.

### Exercise 3: Contrast Equality and Rank Equivalence

Given two `BigDecimal` instances created from `"7.0"` and `"7.00"`:

1. Predict `equals`.
2. Predict the sign of `compareTo`.
3. Predict the size when both are added to a `HashSet`.
4. Predict the size when both are added to a `TreeSet`.
5. Explain the results using the exact contract of each data structure.

### Exercise 4: Design a New Value Type

Design a `Point` type with two integer coordinates `x` and `y`, where the chosen ordering explicitly compares `x` first and then `y`.

- Use an immutable type.
- Implement `Comparable<Point>` using safe comparison methods.
- Ensure two points have equal rank when both coordinates are equal.
- Verify consistency with `equals`.
- Sort a list containing duplicate points and compare its size with a `TreeSet` populated from the same list.
- Explain why this is a convention chosen for the type rather than ordering by distance from the origin.

The completion criterion is that your specification, implementation code, and collection behavior are all consistent—even when reversing comparison arguments or testing boundary values.
