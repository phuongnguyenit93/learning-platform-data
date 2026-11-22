# Separating Approximate Matching From `equals()` When It Does Not Form an Equivalence Relation

In Java, `equals(Object)` expresses **logical equality** under the `Object` contract. Meanwhile, questions such as “do two measurements differ by at most 1°C?”, “are two coordinates less than 10 meters apart?”, or “do two strings have over 90% similarity?” are usually **approximate matching operations**. They can be useful in the business domain, yet do not necessarily form an equivalence relation. Putting them into `equals()` can make the behavior of `HashSet`, `HashMap`, and comparisons in the program confusing or wrong.

**Rule:** reserve `equals()` for a stable equality definition that forms an equivalence relation; express approximation through a dedicated API such as `isCloseTo`, `matchesWithinTolerance`, or `isSimilarTo`, with explicit rules and thresholds.

## 1. What Is an Equivalence Relation?

A relation `~` over objects is an *equivalence relation* when it satisfies three properties:

| Property | Expression | Example with objects `a`, `b`, `c` |
| --- | --- | --- |
| Reflexive | Every object equals itself | `a ~ a` |
| Symmetric | If `a` equals `b`, then `b` equals `a` | `a ~ b ⇒ b ~ a` |
| Transitive | If `a` equals `b` and `b` equals `c`, then `a` must equal `c` | `a ~ b` and `b ~ c` ⇒ `a ~ c` |

Java's `Object.equals(Object)` contract requires these properties. It also requires **consistency** (when the information used for comparison does not change, repeated calls must return the same result) and that `x.equals(null)` always returns `false`. When overriding `equals()`, you must simultaneously guarantee: if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()`. The converse is not required.

An equivalence relation partitions a set of objects into well-defined equality groups: any two objects in the same group must be considered equal, regardless of comparison order. This is especially important for collections that organize elements by equality.

## 2. Why Is Tolerance-Range Matching Usually Not Transitive?

Suppose two temperatures are “close” if their absolute difference is at most `1.0`:

~~~java
static boolean close(double x, double y, double tolerance) {
    return Math.abs(x - y) <= tolerance;
}
~~~

This is only a **rule-illustration snippet**, lacking checks for `NaN`, infinity, and input threshold validation; the full runnable example later will include those checks.

Consider three values:

- `a = 0.0` and `b = 0.6`: difference `0.6`, so `a ~ b` is `true`.
- `b = 0.6` and `c = 1.2`: difference `0.6`, so `b ~ c` is `true`.
- `a = 0.0` and `c = 1.2`: difference `1.2`, so `a ~ c` is `false`.

We have `a ~ b` and `b ~ c`, yet **not** `a ~ c`. Thus, the rule “difference ≤ threshold” **is not transitive** for a general positive threshold. Even though this rule is reflexive and symmetric for finite numbers and valid thresholds, breaking just one of the three properties means it is no longer an equivalence relation.

That is why you **should not** write:

~~~java
// Violates the equals contract: illustrates what NOT to do.
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof Temperature other)) {
        return false;
    }
    return Math.abs(celsius - other.celsius) <= 1.0;
}
~~~

The code fragment above assumes a `Temperature` class and a `celsius` field; it is not a complete class for standalone compilation. Even if you write a `hashCode()` returning the same constant for every object, the transitivity violation **still remains**. Trying to invent a hash formula cannot fix an invalid relation.

A threshold can also depend on the user, measurement, screen, or time. If a context-varying threshold is used to implement `equals()`, the exact same pair of objects can sometimes be considered equal and sometimes not, even when the objects themselves have not changed. This also violates the expectation of `equals()` consistency.

## 3. Proper Design: `equals()` Expresses Identity; Dedicated API Expresses Closeness

Suppose each sensor reading has a unique, fixed **reading ID** (`readingId`). Two objects with the same ID represent the same logical reading, so they can be treated as equal by business identity. The temperature value (`celsius`) is only used to ask “are these two readings close in temperature?”.

The design then has two independent operations:

- `equals(Object)`: compares `readingId`, answering **“same reading?”**; this is an equivalence relation if the ID is stable and consistently assigned.
- `isCloseTo(Reading other, double tolerance)`: compares temperatures within a threshold, answering **“are two measurements close?”**; it does not claim the two objects are equal.

One object can **differ** from another under `equals()`, yet be **close** under `isCloseTo()`. That is not a contradiction: the two methods answer two different business questions.

### Complete Java 17 Example

Create the file **`ApproximateMatchDemo.java`** with the following content:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ApproximateMatchDemo {

    static final class Reading {
        private final String readingId;
        private final double celsius;

        Reading(String readingId, double celsius) {
            this.readingId = Objects.requireNonNull(readingId, "readingId");
            if (!Double.isFinite(celsius)) {
                throw new IllegalArgumentException("celsius must be finite");
            }
            this.celsius = celsius;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Reading other)) {
                return false;
            }
            return readingId.equals(other.readingId);
        }

        @Override
        public int hashCode() {
            return readingId.hashCode();
        }

        public boolean isCloseTo(Reading other, double tolerance) {
            if (!Double.isFinite(tolerance) || tolerance < 0.0) {
                throw new IllegalArgumentException(
                    "tolerance must be finite and >= 0");
            }
            return other != null
                && Math.abs(celsius - other.celsius) <= tolerance;
        }
    }

    public static void main(String[] args) {
        Reading a = new Reading("A", 0.0);
        Reading b = new Reading("B", 0.6);
        Reading c = new Reading("C", 1.2);
        Reading copyOfA = new Reading("A", 0.0);

        double tolerance = 1.0;

        System.out.println("a close b: " + a.isCloseTo(b, tolerance));
        System.out.println("b close c: " + b.isCloseTo(c, tolerance));
        System.out.println("a close c: " + a.isCloseTo(c, tolerance));

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a equals copyOfA: " + a.equals(copyOfA));
        System.out.println("same hash for equal: "
            + (a.hashCode() == copyOfA.hashCode()));
        System.out.println("a close null: " + a.isCloseTo(null, tolerance));

        Set<Reading> readings = new HashSet<>();
        readings.add(a);
        readings.add(b);
        readings.add(c);
        readings.add(copyOfA);
        System.out.println("HashSet size: " + readings.size());
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac ApproximateMatchDemo.java
java ApproximateMatchDemo
~~~

**Expected output:**

~~~text
a close b: true
b close c: true
a close c: false
a equals b: false
a equals copyOfA: true
same hash for equal: true
a close null: false
HashSet size: 3
~~~

Explanation:

1. The three `close` calls intentionally reproduce the non-transitive counterexample. This is **correct** behavior for approximate matching, since this method is not used as `equals()`.
2. `a.equals(b)` is `false` because the two reading IDs differ, even though the temperatures are close enough.
3. `a.equals(copyOfA)` is `true` because they carry the same `readingId`; `hashCode()` is based on the same ID and therefore obeys the hash rule.
4. `isCloseTo(null, tolerance)` chooses to return `false` per this API's design; `equals(null)` also returns `false` per the `Object` contract.
5. `HashSet` holds three elements: `A`, `B`, `C`. The copy of `A` does not add a fourth element, and the temperature comparison threshold does not affect membership.

**Intentional limitations:** the `Reading` class is `final`, its fields are `final`, and `readingId` does not change after construction. This keeps equality defined on a stable identifier. The rule “same `readingId` means the same logical reading” holds only when the system genuinely guarantees that meaning; do not blindly apply the same approach to every data model. `isCloseTo` checks that both temperature and threshold are finite; if the threshold is negative, `NaN`, or infinite, the method throws `IllegalArgumentException`.

## 4. Harm of Stuffing Approximate Matching Into `equals()`

### Hash-Based Collections

`HashSet` and `HashMap` use `hashCode()` to locate the lookup region and then use `equals()` to determine equal elements or keys. If `equals()` is not transitive, whether a value is treated as a duplicate can depend on which elements were already added and the order of operations. There is no longer a consistent partitioning into equality groups.

For example, with `a = 0.0`, `b = 0.6`, `c = 1.2`: if `b` represents both `a` and `c` under threshold `1.0`, yet `a` and `c` are not equal under the same rule, you cannot treat “all nearby values” as one logical hash key while preserving the meaning of direct closeness.

**Do not make an approximate relation the identity key of a `Map`, the deduplication condition of a `Set`, or the basis for `hashCode()`.** Store objects by an exact identifier/value key and find nearby objects via a separate operation.

### Comparing for Ordering

Avoid writing a `Comparator` that returns `0` for two values merely because they are within a threshold: such a rule generally breaks consistent ordering requirements. `TreeSet` and `TreeMap` rely on comparison results to determine order and whether two keys are considered equivalent in the tree structure. If sorting is needed, use a clear order (such as `Double.compare` on valid measurements), then search within the tolerance range separately.

### Relative Error and Asymmetric Matching

Not every “approximate” formula is automatically symmetric. For example, `abs(a-b) / abs(a) <= p` depends on picking `a` as the denominator; swapping the two arguments can yield different results. You must clearly define the meaning of absolute thresholds, relative thresholds, measurement units, and how `0` is handled. Even if the formula is fixed to be symmetric, the **non-transitivity** issue can generally still exist.

## 5. What If You Genuinely Need Equality Grouping by Precision?

Sometimes the business requirement genuinely is **to treat values belonging to the same resolution level as equal**, such as caring only about temperatures recorded to the nearest tenth of a degree. In that case, you can **normalize into a stable representative value before comparing**, then define equality as equality of the representative value.

Illustrative example of the idea:

~~~java
// After validating finite input and appropriate value range:
long tenthDegrees = Math.round(celsius * 10.0);
~~~

If a data type stores the canonical key `tenthDegrees` and uses `Long.equals`/comparing `long` (with matching `hashCode`), key-based equality **is transitive**: same key means same group. However, this is a **different rule** from `Math.abs(a - b) <= 0.1`: two very close numbers lying on opposite sides of a rounding boundary can land in different groups, whereas two numbers in the same group are treated as equal at the chosen resolution. This boundary must be accepted at the business-requirement level, without pretending the two rules are equivalent.

Choosing based on data meaning:

| Actual requirement | Appropriate design |
| --- | --- |
| “Same record/measurement?” | `equals()` based on the record's stable ID |
| “Same value normalized to a fixed resolution?” | Normalize then compare exact keys; keep `equals()` and `hashCode()` in sync |
| “Two measurements within ε of each other?” | `isCloseTo(other, epsilon)` / `matchesWithinTolerance` |
| “Measurement points forming connected clusters by distance?” | Dedicated clustering/graph algorithm with clearly documented membership rules |
| “Need to find every value within a neighborhood around X?” | Range filtering/search with explicit criteria, without faking it via `equals()` |

With clustering by proximity, elements in the same cluster via a chain do not necessarily lie close to each other directly. For example, `a` and `c` may belong to the same connected component through `b`, even though `a` is not close to `c`. Therefore, name and test the exact relation the product intends to express.

## 6. Design and Testing Checklist

Before defining `equals()` for a class, ask yourself:

1. Does “equal” mean same identity, same value, or same canonical key? Is the rule **reflexive, symmetric, and transitive**?
2. Is the data used for `equals()` and `hashCode()` stable while the object is used as a `HashMap` key or `HashSet` element?
3. Are “closeness” thresholds, measurement units, similarity algorithms, or user preferences getting mixed into `equals()`? If so, separate them into a dedicated API.
4. For the approximate API, have behaviors for `null`, negative thresholds, `NaN`, infinity, error bounds, and boundary cases been explicitly defined?
5. Have you tested a triple `a, b, c` where `a` is close to `b`, `b` is close to `c`, yet `a` is not close to `c`? This case must be **allowed** in an approximate API, yet exposes a bug if it occurs in `equals()`.

**Learning takeaway:** `equals()` is about *logical equality* and must obey the `Object` contract. A threshold-based match can be completely valid in the business domain while still not being an equivalence relation. Give it its own name, pass thresholds explicitly, test edge cases, and keep `equals()`/`hashCode()` grounded in a stable equality definition.