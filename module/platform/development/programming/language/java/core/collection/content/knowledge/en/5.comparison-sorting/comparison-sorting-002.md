# Comparator and the Sign, Transitivity, and Consistency Contract

A `Comparator<T>` answers the question: **according to a chosen rule, which object comes first, which object comes next, and which objects are considered equally ranked?**

For example, items can be ordered by ascending score, or by descending score followed by ascending code. The comparator describes the rule; a sorting algorithm or data structure uses that rule.

Crucially, a comparator must give answers that work coherently together. Getting a single comparison right is not enough: the results must remain valid when reversing the two arguments, examining triples of objects, and replacing an object with one considered equally ranked.

## 1. Reading the compare Result Correctly

The central method has the form:

```java
int compare(T x, T y);
```

This is an illustrative method signature from the interface, not a standalone program.

| Result | Meaning according to the comparator |
| --- | --- |
| Less than 0 | `x` comes before `y` |
| Equal to 0 | `x` and `y` have the same rank under the rule |
| Greater than 0 | `x` comes after `y` |

**Only the sign of the returned number matters for ordering.** A valid comparator may return `-7`, `0`, `12`; it is not required to return strictly `-1`, `0`, `1`.

When expressing the contract, use the sign function:

```text
sign(n) = -1 if n < 0
sign(n) =  0 if n = 0
sign(n) =  1 if n > 0
```

In Java, `Integer.signum(result)` performs this normalization.

Therefore, callers should check `compare(x, y) < 0`, not `compare(x, y) == -1`. If you want to reverse the order, reverse the comparison relationship rather than assuming the absolute magnitude of the result.

## 2. Three Core Constraints

Let `c(x, y)` be the result of `comparator.compare(x, y)`. The constraints apply over the domain of objects that the comparator accepts.

### 2.1. Reversing Direction Must Flip the Sign

```text
sign(c(x, y)) = -sign(c(y, x))
```

If `x` comes before `y`, reversing the direction must state that `y` comes after `x`. If one direction returns 0, the other direction must also return 0.

This is **sign antisymmetry**, not a requirement that the two returned integers always be arithmetic negations of each other. For instance, returning `-2` in one direction and `9` in the other still satisfies the sign condition.

A consequence worth checking is `c(x, x) == 0`: an object cannot both precede itself and obey the sign-flipping rule.

If comparison is unsupported and one direction throws an exception, the reversed direction must also throw an exception. Do not design a case where `compare(x, y)` fails with an error while `compare(y, x)` returns a valid result.

### 2.2. The Ordering Must Be Transitive

```text
c(x, y) > 0 and c(y, z) > 0  =>  c(x, z) > 0
```

For example, if `A`'s score is higher than `B`'s, and `B`'s score is higher than `C`'s, a consistent rule must place `A` higher than `C`.

A cycle must never be formed:

```text
0 comes before 1
1 comes before 2
2 comes before 0
```

With such a cycle, no linear sequence satisfies all answers. An algorithm cannot repair a self-contradictory relation into a valid ordering.

The corresponding condition in the "comes before" direction must also hold; it follows alongside the sign-reversal condition.

### 2.3. Equally Ranked Objects Must Behave Consistently Toward a Third Object

```text
c(x, y) == 0  =>  sign(c(x, z)) == sign(c(y, z))
```

If `x` and `y` have the same rank, replacing `x` with `y` when comparing against the same `z` must not change the result from "before" to "after", or from "same rank" to "before".

A small counterexample:

| Comparison | Returned result |
| --- | --- |
| `compare(0, 2)` | `0`: treats 0 and 2 as having the same rank |
| `compare(0, 1)` | Negative |
| `compare(2, 1)` | Positive |

The comparator simultaneously claims that 0 and 2 have the same rank, yet places 1 between them. These answers are incompatible.

This rule is stronger than merely checking that "two objects with equal scores return 0". Objects grouped into the same ordering equivalence class must be viewed identically when compared against every other group.

The formal formulas, exception conditions, and `equals` provisions are specified in the [Java 17 Comparator.compare contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T)).

## 3. Two Meanings of "Consistency" to Keep Distinct

### 3.1. Consistency of Equally Ranked Groups

This is the mandatory condition just stated: when `compare(x, y) == 0`, the two objects must compare with the same sign against every third object.

A comparator that orders items solely by `score` can be completely valid. Two items with different codes but the same score are placed in the same rank, provided every comparison continues to use that exact score.

This validity does not depend on whether they are one or two objects, or whether they share the same code or have different codes.

### 3.2. Consistency with equals of the Compared Objects

The commonly desired condition is:

```text
(compare(x, y) == 0) == x.equals(y)
```

In the expression above, the middle `==` compares two boolean values. It requires:

- If two objects are equal according to `equals`, the comparator also returns 0.
- If the comparator returns 0, the two objects are also equal according to `equals`.

This condition is **recommended, though not required for every comparator**. If a comparator intentionally differs from `equals`, that difference must be understood and documented, especially when the comparator is passed to a sorted set or sorted map.

For example, with the type:

```java
record Item(String code, int score) {}
```

Two objects `new Item("A", 90)` and `new Item("B", 90)` are not equal according to `equals` because their `code` values differ. A comparator that only examines `score` still returns 0.

This comparator is inconsistent with the record's `equals`, but that does not make it violate the three ordering constraints. It orders by score rather than defining the full identity of an item.

Even a comparator that returns 0 for every pair in a non-empty domain can satisfy the ordering constraints: it groups the entire domain into a single rank. Whether it is useful and appropriate for its call site is a separate question.

### 3.3. Keeping the Rule Stable During Use

There is also a practical requirement: as long as the relevant data remains unchanged, the comparator must continue to describe the same rule.

Avoid using randomness, state that increments on each call, the current wall-clock time, or configuration that mutates during sorting. Likewise, do not let another thread modify fields used as comparison keys while an algorithm is running.

This should not be misunderstood as meaning objects can never change. The point is that comparisons belonging to the same operation or data structure must rely on mutually consistent data and rules.

A comparator with no fields of its own can still lose stability if it reads mutable state from the elements being compared.

## 4. Impact on List, TreeSet, and TreeMap

### 4.1. Sorting a List Retains Equally Ranked Elements

A list can contain multiple items with the same score. Sorting by score does not remove them from the list.

`List.sort` guarantees a stable sort: elements that the comparator treats as equally ranked retain their previous relative order. However, "stable" here refers to how the algorithm handles tied elements; it does not turn a broken comparator into a valid one, nor does it make a comparator consistent with `equals`. See the [List.sort API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

If you need a display order that does not depend on input order when scores are tied, add an explicit secondary criterion.

### 4.2. TreeSet Treats compare Returning 0 as the Same Element by Ordering

When using a score-only comparator, adding an item with code `"A"` and score 90 followed by an item with code `"B"` and score 90 into a `TreeSet` will keep only one element representing the score-90 rank.

That does not prove the tree is buggy. The tree is applying the exact rule provided by the comparator. If the goal is to store every distinct item, using score alone as the entire rule is an unsuitable choice.

The opposite mismatch can also occur: two objects are `equals` to each other, yet the comparator distinguishes them by inspecting extra data not included in `equals`. In that case, the tree can retain objects that the general set contract considers duplicates.

Therefore, if proper `equals`-based set behavior is needed, the comparator's zero-equivalence relation must align with `equals`. See the [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### 4.3. TreeMap Applies the Same Principle to Keys

With `TreeMap`, what matters is the comparator of the **keys**. If two keys compare equal to 0, a `put` for the second key updates the corresponding mapping instead of creating a separate key in the tree.

Key uniqueness in a `TreeMap` is determined by ordering. You cannot keep multiple entries with the same comparison key by forcing the comparator to return an arbitrary non-zero result; doing so would break the contract. Choose an appropriate key model or storage structure instead. See the [TreeMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

### 4.4. BigDecimal Is a Deliberate Example of Divergence

`new BigDecimal("2.0")` and `new BigDecimal("2.00")` have the same numerical value when compared via `compareTo`, but they are not equal according to `equals`, because `equals` also considers scale.

Consequently, a `HashSet` containing these two values can have size 2, whereas a `TreeSet` using natural ordering has size 1. This reflects the difference between the two equivalence contracts in use, not a reason to conclude that `BigDecimal`'s natural ordering violates transitivity. See the [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

## 5. Writing Safe and Expressive Comparators

### 5.1. Do Not Compare Integers Using Subtraction

An error-prone pattern:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

If `a` is `Integer.MIN_VALUE` and `b` is 0, subtraction in both directions yields a negative number due to `int` overflow. The sign-reversal relation is broken.

`Integer.signum(a - b)` does not save this either, because the subtraction overflows before the sign is computed. Similarly, subtracting two `long` values and casting to `int` is not a solution.

Use:

```java
Comparator<Integer> safe = Integer::compare;
Comparator<Item> byScore = Comparator.comparingInt(Item::score);
```

For `long` or `double` fields, choose the corresponding APIs such as `comparingLong` or `comparingDouble`. Do not cast a `double` difference to `int`: two distinct numbers may be truncated to 0, and special floating-point values require well-defined rules.

The sign-return rule for `Integer.compare` is published in the [Integer.compare API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#compare(int,int)).

### 5.2. When Two Objects Have the Same Rank, Return 0

The following pattern is wrong:

```java
Comparator<Integer> bad = (a, b) -> a > b ? 1 : -1;
```

When `a` equals `b`, it still returns a negative value. Even an element compared against itself does not return 0.

Do not "fix" `TreeSet` element merging by deliberately returning 1 or -1 for equally ranked objects. If multiple records must be kept, use a list or design a meaningful secondary criterion.

### 5.3. Chaining Secondary Criteria in Priority Order

The following illustrative declarations use the `Item` type defined above:

```java
Comparator<Item> byScore = Comparator.comparingInt(Item::score);

Comparator<Item> byScoreThenCode =
        byScore.thenComparing(Item::code);

Comparator<Item> scoreDescendingCodeAscending =
        byScore.reversed().thenComparing(Item::code);
```

`thenComparing` only consults the next criterion when the preceding criterion returns 0. It does not sum the numerical scores of comparisons.

In the final comparator:

1. Higher scores come first.
2. When scores are tied, smaller codes according to `String` ordering come first.

Where `reversed()` is called changes the meaning:

```java
// Reverses the entire rule: score descending, and code also descending on a score tie.
Comparator<Item> bothDescending =
        byScore.thenComparing(Item::code).reversed();
```

In the `Item` record example, comparing both `score` and `code` aligns the zero-return relation with `equals`, assuming `code` is non-null. Do not generalize that adding any `thenComparing` always produces consistency with `equals`; you must check all fields and the equality rules of the type in question.

To reverse an existing comparator, use `reversed()` or compare the two arguments in reverse order. Avoid writing `-comparator.compare(a, b)`: a valid return value can be `Integer.MIN_VALUE`, whose negation remains negative due to overflow.

### 5.4. Define a Null Policy

If the data domain includes `null`, state explicitly where it belongs:

```java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());
```

The comparator above places null strings after non-null strings, and treats two nulls as equally ranked.

Distinguish between:

- **The element itself is null:** wrap the element comparator.
- **A property of the element is null:** provide a null-safe comparator for that property.

An illustrative example where the `code` property may be null:

```java
Comparator<Item> nullableCode = Comparator.comparing(
        Item::code,
        Comparator.nullsLast(Comparator.naturalOrder()));

Comparator<Item> nullableItem = Comparator.nullsLast(nullableCode);
```

The first declaration handles a null `code`, but does not handle a null `Item` itself. The second declaration adds that outer layer of handling.

Reversing an entire comparator also reverses the position of nulls. For instance, `nullLast.reversed()` will place nulls first. If you want non-null values in descending order while still keeping nulls last, wrap `nullsLast` around the descending comparator.

## 6. Complete Program to Observe Behavior

Save as **ComparatorContractDemo.java**. The APIs used are compatible with Java 17 and later:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class ComparatorContractDemo {
    record Item(String code, int score) {}

    private static List<String> describe(Collection<Item> items) {
        return items.stream()
                .map(item -> item.code() + ":" + item.score())
                .toList();
    }

    public static void main(String[] args) {
        Comparator<Integer> subtraction = (a, b) -> a - b;
        Comparator<Integer> safe = Integer::compare;
        int min = Integer.MIN_VALUE;

        System.out.println("Subtraction signs: "
                + Integer.signum(subtraction.compare(min, 0)) + ", "
                + Integer.signum(subtraction.compare(0, min)));
        System.out.println("Integer.compare signs: "
                + Integer.signum(safe.compare(min, 0)) + ", "
                + Integer.signum(safe.compare(0, min)));

        Item b = new Item("B", 90);
        Item a = new Item("A", 90);
        Item c = new Item("C", 75);
        List<Item> input = List.of(b, a, c);

        Comparator<Item> byScore = Comparator.comparingInt(Item::score);
        Comparator<Item> byScoreThenCode =
                byScore.thenComparing(Item::code);

        List<Item> ascending = new ArrayList<>(input);
        ascending.sort(byScoreThenCode);
        System.out.println("Ascending: " + describe(ascending));

        List<Item> descending = new ArrayList<>(input);
        descending.sort(byScore.reversed().thenComparing(Item::code));
        System.out.println("Descending score: " + describe(descending));

        System.out.println("Score tie compare: " + byScore.compare(a, b));
        System.out.println("Record equals: " + a.equals(b));

        TreeSet<Item> scoreOnly = new TreeSet<>(byScore);
        scoreOnly.addAll(input);
        System.out.println("TreeSet score only size: " + scoreOnly.size());

        TreeSet<Item> complete = new TreeSet<>(byScoreThenCode);
        complete.addAll(input);
        System.out.println("TreeSet score/code: " + describe(complete));

        List<String> names =
                new ArrayList<>(Arrays.asList("b", null, "a"));
        names.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("Nulls last: " + names);

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("Decimal compare: " + x.compareTo(y));
        System.out.println("Decimal equals: " + x.equals(y));
        System.out.println("HashSet decimals: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet decimals: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparatorContractDemo.java
java ComparatorContractDemo
```

Stdout:

```text
Subtraction signs: -1, -1
Integer.compare signs: -1, 1
Ascending: [C:75, A:90, B:90]
Descending score: [A:90, B:90, C:75]
Score tie compare: 0
Record equals: false
TreeSet score only size: 2
TreeSet score/code: [C:75, A:90, B:90]
Nulls last: [a, b, null]
Decimal compare: 0
Decimal equals: false
HashSet decimals: 2
TreeSet decimals: 1
```

### Reading the Results

**The first two lines** show that the subtraction-based comparator fails to preserve opposite signs, whereas `Integer.compare` preserves them.

**The two sorted lists** show that the score and code criteria operate in the intended priority order. Items with tied scores are not lost from the list.

**`Score tie compare: 0` while `Record equals: false`** is the deliberate difference of a comparator that only inspects score.

**`TreeSet score only size: 2`** is the result of three items belonging to two score ranks. When code is compared as well, the tree retains all three items in the desired order.

**The names list** demonstrates placing `null` at the end using a null-handling comparator.

**The four BigDecimal lines** show that a valid ordering can differ from `equals`, and that difference causes the two set structures to identify duplicates differently.

## 7. Verifying the Contract with Pairs and Triples

Simply passing a list to `sort` and seeing output that looks right is insufficient testing. On a small dataset, the sorting algorithm might never execute the specific comparisons that expose a bug.

The program below checks the constraints across **a finite sample**. The sample must lie within the domain that the comparator can compare normally; the program does not serve as a comprehensive test suite for exception policies.

Save as **ComparatorCheckDemo.java**:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorCheckDemo {
    static <T> String firstViolation(
            Comparator<? super T> comparator, List<T> sample) {
        for (T x : sample) {
            if (comparator.compare(x, x) != 0) {
                return "self comparison";
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                int xy = Integer.signum(comparator.compare(x, y));
                int yx = Integer.signum(comparator.compare(y, x));
                if (xy != -yx) {
                    return "opposite signs";
                }
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                for (T z : sample) {
                    int xy = comparator.compare(x, y);
                    int xz = comparator.compare(x, z);
                    int yz = comparator.compare(y, z);

                    if (xy == 0
                            && Integer.signum(xz) != Integer.signum(yz)) {
                        return "zero consistency";
                    }
                }
            }
        }

        for (T x : sample) {
            for (T y : sample) {
                for (T z : sample) {
                    if (comparator.compare(x, y) > 0
                            && comparator.compare(y, z) > 0
                            && comparator.compare(x, z) <= 0) {
                        return "transitivity";
                    }
                }
            }
        }
        return "no violation in sample";
    }

    public static void main(String[] args) {
        Comparator<Integer> subtract = (a, b) -> a - b;

        Comparator<Integer> cyclic = (a, b) -> {
            if (a.equals(b)) {
                return 0;
            }
            if ((a == 0 && b == 1)
                    || (a == 1 && b == 2)
                    || (a == 2 && b == 0)) {
                return -1;
            }
            return 1;
        };

        Comparator<Integer> brokenZero = (a, b) -> {
            if ((a == 0 && b == 2) || (a == 2 && b == 0)) {
                return 0;
            }
            return Integer.compare(a, b);
        };

        System.out.println("Safe: " + firstViolation(
                Integer::compare,
                List.of(Integer.MIN_VALUE, -1, 0, 1, Integer.MAX_VALUE)));
        System.out.println("Subtract: " + firstViolation(
                subtract, List.of(Integer.MIN_VALUE, 0)));
        System.out.println("Cyclic: " + firstViolation(
                cyclic, List.of(0, 1, 2)));
        System.out.println("Broken zero: " + firstViolation(
                brokenZero, List.of(0, 1, 2)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparatorCheckDemo.java
java ComparatorCheckDemo
```

Stdout:

```text
Safe: no violation in sample
Subtract: opposite signs
Cyclic: transitivity
Broken zero: zero consistency
```

### 7.1. Meaning of the Test Comparators

- `Integer::compare` shows no violation on a sample that includes boundary values.
- `subtract` exposes a sign error caused by integer overflow.
- `cyclic` defines a cycle where 0 precedes 1, 1 precedes 2, and 2 precedes 0. It handles self-comparison and sign reversal properly, but violates transitivity.
- `brokenZero` treats 0 and 2 as equally ranked while still placing 1 between them. The checker detects that zero-rank consistency is broken.

A comparator can violate multiple conditions simultaneously. The function returns the first condition violated in check order; it does not claim that is the only defect.

### 7.2. Limitations to Understand

Triple-nested loops have cubic cost in the number of sample elements. They suit small samples for illustration or unit tests, not checking large datasets in a main production path.

Finding no violation in a sample **is not a proof of correctness for all inputs**. You should supplement the sample with:

- Negative numbers, positive numbers, 0, and numeric type boundaries.
- Two distinct objects that are `equals` to each other.
- Two objects sharing the primary criterion but differing in the secondary criterion.
- `null` if accepted, and both comparison directions if `null` is rejected.
- Triples capable of forming cycles or exposing inconsistent equal-rank groups.
- Reproducible randomly generated data to broaden test coverage.

If the design requires consistency with `equals`, test that condition separately. Do not lump it into mandatory contract errors and conclude that every single-attribute comparator is broken.

If a comparator relies on external data, you must also check whether configuration or data can mutate while in use. Three nested loops cannot by themselves prove system-wide stability.

## 8. When a Comparator Is Broken or Comparison Keys Mutate

Sorting algorithms may throw `IllegalArgumentException` when they detect a contract violation. The `Arrays.sort` documentation permits such detection, but does not guarantee that every broken comparator will be caught on every run. Consequently, "no exception thrown" does not prove a comparator is valid. See the [Arrays.sort with Comparator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#sort(T%5B%5D,java.util.Comparator)).

Similarly, do not mutate fields used as comparison keys on an element currently stored in a `TreeSet` or a key currently stored in a `TreeMap`. Positions organized under the old value are not automatically rebuilt when a field changes; lookups may no longer follow the expected path.

If data that determines ordering position must change, the standard approach is:

1. Remove the element or mapping while its comparison key is still in the old state.
2. Mutate the data.
3. Re-insert it under the new ordering.

Designing key objects so that fields governing equality and ordering are immutable is usually much easier to control. Under concurrent updates, the entire workflow also requires proper coordination; a comparator does not provide collection synchronization.

## 9. Self-Review Checklist

Before putting a comparator into production code, answer the following:

1. What types and values make up the input domain? Is `null` part of the domain?
2. Which exact business rule do negative, zero, and positive results represent?
3. Does reversing the arguments flip the sign, and does self-comparison return 0?
4. Could any triple form an ordering cycle?
5. Do equally ranked objects compare with the same sign against every third object?
6. Does a zero result align with `equals`? If not, does the call site accept that behavior?
7. Could subtraction, type casting, mutable data, or one-way exceptions corrupt the rule?
8. Does a list need to retain tied elements, or does a set/map need to treat them as the same key?
9. Have secondary criteria, descending directions, and null placement been verified together?

The comparator contract is the foundation that allows algorithms and ordered data structures to rely on a single coherent relation. Stating the relation clearly up front, composing safe comparison primitives, and verifying with pairs and triples lets you explain the resulting order rather than merely hoping a single sort call happens to pass.
