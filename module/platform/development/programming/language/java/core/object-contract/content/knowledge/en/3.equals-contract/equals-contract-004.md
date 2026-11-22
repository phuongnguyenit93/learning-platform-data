# Transitivity Across Three Objects in `equals()`

## 1. What Is Transitivity?

In Java, `Object.equals(Object)` determines whether two objects are considered **logically equal**. A mandatory requirement of the `equals()` contract is **transitivity**:

> For any three non-`null` references `a`, `b`, and `c`: if `a.equals(b)` is `true` and `b.equals(c)` is `true`, then `a.equals(c)` must also be `true`.

This can be written as:

```text
a ==(equals)== b  and  b ==(equals)== c
                    => a ==(equals)== c
```

Here, "equal" refers to the result of `equals()`, **not necessarily the same object in memory** (`a == b`). Three distinct objects can still hold the same value, with `equals()` returning `true` for all three pairs.

Valid example: three objects representing the same immutable identifier `"A-101"`. When `a` equals `b` by this identifier and `b` equals `c` by the same identifier, `a` must equal `c`. The rule must hold consistently for **every triple** of that object type, not just the triple chosen for testing.

Transitivity is one component of the full `equals()` contract: reflexivity, symmetry, transitivity, consistency, and returning `false` when compared with `null`. This lesson focuses on transitivity; the remaining properties must still be upheld in real implementations.

## 2. Counterexample: Treating Two "Close Enough" Numbers as Equal

Suppose a distance-measuring class decides two values are equal when their difference is at most **10 mm**. With three objects storing `0 mm`, `8 mm`, and `16 mm` respectively:

| Object Pair | Difference | Result of "difference ≤ 10 mm" |
| --- | ---: | --- |
| `a(0)` and `b(8)` | `8 mm` | `true` |
| `b(8)` and `c(16)` | `8 mm` | `true` |
| `a(0)` and `c(16)` | `16 mm` | `false` |

We have `a.equals(b) && b.equals(c)` as `true`, yet `a.equals(c)` is `false`. This is a **direct violation of transitivity**.

The cause is not floating-point precision error: the example uses integers. The relation "within 10 units of each other" allows a chain of small steps to accumulate into a distance greater than 10; therefore it does not form a true equality relation. Replacing `10` with any fixed positive tolerance carries the exact same risk.

## 3. Runnable Java 17 Program: The Bug and Two Valid Designs

Save all the following code into the file `EqualsTransitivityDemo.java`. The `NearReading` class is **intentionally broken with respect to transitivity** for demonstration; do not use this `equals()` definition in an application. The two types `ExactReading` and `BucketReading` below demonstrate valid equality relations.

```java
import java.util.List;

public class EqualsTransitivityDemo {

    // COUNTEREXAMPLE: equals() based on a maximum distance of 10 mm.
    static final class NearReading {
        private final int millimeters;

        NearReading(int millimeters) {
            this.millimeters = millimeters;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof NearReading that)) {
                return false;
            }
            return Math.abs((long) millimeters - that.millimeters) <= 10;
        }

        @Override
        public int hashCode() {
            return 0; // Only to isolate the transitivity bug; poor hash efficiency.
        }
    }

    // VALID APPROACH 1: mm values must match exactly.
    record ExactReading(int millimeters) {}

    // VALID APPROACH 2: compare a clearly defined grouping key.
    record BucketReading(int bucket) {
        static BucketReading fromMillimeters(int millimeters) {
            return new BucketReading(Math.floorDiv(millimeters, 10));
        }
    }

    // Check ALL triples in a finite sample set.
    static <T> boolean isTransitiveOn(List<T> values) {
        for (T a : values) {
            for (T b : values) {
                for (T c : values) {
                    if (a.equals(b) && b.equals(c) && !a.equals(c)) {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        NearReading a = new NearReading(0);
        NearReading b = new NearReading(8);
        NearReading c = new NearReading(16);
        System.out.println("near a=b: " + a.equals(b));
        System.out.println("near b=c: " + b.equals(c));
        System.out.println("near a=c: " + a.equals(c));
        System.out.println("near transitive: "
                + isTransitiveOn(List.of(a, b, c)));

        ExactReading p = new ExactReading(8);
        ExactReading q = new ExactReading(8);
        ExactReading r = new ExactReading(8);
        System.out.println("exact p=q: " + p.equals(q));
        System.out.println("exact q=r: " + q.equals(r));
        System.out.println("exact p=r: " + p.equals(r));
        System.out.println("exact transitive: "
                + isTransitiveOn(List.of(p, q, r)));

        BucketReading u = BucketReading.fromMillimeters(0);
        BucketReading v = BucketReading.fromMillimeters(8);
        BucketReading w = BucketReading.fromMillimeters(16);
        System.out.println("bucket u=v: " + u.equals(v));
        System.out.println("bucket v=w: " + v.equals(w));
        System.out.println("bucket transitive: "
                + isTransitiveOn(List.of(u, v, w)));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac EqualsTransitivityDemo.java
java EqualsTransitivityDemo
```

Expected output:

```text
near a=b: true
near b=c: true
near a=c: false
near transitive: false
exact p=q: true
exact q=r: true
exact p=r: true
exact transitive: true
bucket u=v: true
bucket v=w: false
bucket transitive: true
```

Explanation:

- `NearReading` uses `Math.abs((long) millimeters - that.millimeters)` to avoid integer overflow when subtracting extreme `int` values. Even though the distance calculation is safe, **the equality rule is still wrong** because it is not transitive.
- `ExactReading` is a `record`; Java automatically provides `equals()` and `hashCode()` based on the `millimeters` component. Three records with the same value `8` are equal in every pair.
- `BucketReading` converts the data into a **fixed grouping key**: `Math.floorDiv(value, 10)`. Two records are equal when they share the same `bucket`. `0` and `8` are in bucket `0`; `16` is in bucket `1`. Whenever `bucket(a) = bucket(b)` and `bucket(b) = bucket(c)`, it is guaranteed that `bucket(a) = bucket(c)`.
- The `isTransitiveOn` check inspects every triple of the **given sample set**, with `O(n³)` cost, making it suitable for small tests. Returning `true` on one sample set **does not prove** the class is correct for all possible values; it must be combined with reasoning about the comparison rule.

Note: bucketing has hard boundaries. For example, `9 mm` and `10 mm` are very close yet fall into different buckets. Choose this model only when the business meaning is genuinely "in the same bucket"; do not use it to pretend to recreate a "within 10 mm" rule.

## 4. How to Design `equals()` to Preserve Transitivity

### Approach A — Compare Immutable, Consistent Keys or State

If two objects represent the same entity when they share an immutable identifier, compare **that exact identifier**. For value objects, compare the full set of fields defined as the logical identity. Use `record` when data fits value semantics; Java will generate component-based equality methods.

Example of a simple value object:

```java
record DocumentKey(String namespace, long id) {}
```

`new DocumentKey("docs", 7)` equals another `DocumentKey` with the same `namespace` and `id`. If `a`, `b`, and `c` share that pair of properties, transitivity follows from the transitivity of the component comparisons. The code above is an **illustrative snippet**, not a standalone program.

If writing `equals()` manually, check the object type and compare **the exact same set of criteria** on every call. Avoid changing the policy based on which side of the comparison is called, global state, time, or differing class branches.

### Approach B — Normalize into a Canonical Form

If the domain considers different representations equivalent (for example, case-insensitive codes), normalize **once using a stable rule**, then compare the normalized values. A deterministic normalization function `f` induces the relation `a ~ b` when `f(a).equals(f(b))`. Because equality on normalized values is transitive, this relation is also transitive if `f` is stable and semantically sound.

Normalization rules must be explicitly specified: Unicode normalization, whitespace, casing with an appropriate locale, measurement units, or fixed rounding precision. Do not arbitrarily trim text, round numbers, or switch locales, as doing so can accidentally merge values that must remain distinct.

### Approach C — Separate "Near" from "Equal"

If you need to ask whether two measurements are close within an allowable tolerance, create a dedicated method such as `withinTolerance(other, tolerance)`. This is an **approximation relation**, has no obligation to be transitive, and should not be used as `equals()`.

```java
static boolean withinTolerance(long a, long b, long tolerance) {
    if (tolerance < 0) {
        throw new IllegalArgumentException("tolerance must be nonnegative");
    }
    // Example limiting input range to avoid subtraction overflow:
    return Math.abs((double) a - (double) b) <= tolerance;
}
```

The illustrative snippet above casts to `double` for the difference to avoid integer overflow, but **can lose precision for very large `long` values**. In code requiring exact precision for every `long`, use `BigInteger` or guarded subtraction comparisons. For real-world measurement data, also define absolute vs. relative tolerance, units, and handling of `NaN`/infinity when using floating-point numbers. Using a standalone approximation API keeps the `equals()` contract intact.

## 5. Why Does This Bug Affect Java Collections?

`HashSet`, `HashMap`, and many lookup/deduplication operations rely on `equals()` representing **a stable equality relation**. If `a` equals `b` and `b` equals `c`, yet `a` does not equal `c`, the notion of "one equivalent element" becomes contradictory: insertions, lookups, and deduplication can produce unpredictable results depending on the data and operation order. Thus, the bug breaks far more than a single `if` expression.

Transitivity and `hashCode()` are related yet **distinct** requirements:

1. If `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()` must hold.
2. Equal hash codes **do not necessarily** mean two objects are equal.
3. Fixing `hashCode()` cannot cure a non-transitive `equals()` relation.

In `NearReading` in the example, `hashCode()` intentionally returns `0` for all objects so as **not to violate the "equals ⇒ equal hash" rule** while exposing the transitivity bug. Using a constant hash puts all elements into the same hash bucket and can severely degrade performance; it is not an implementation to use in practice. For valid types, compute the hash from the exact properties contributing to `equals()`, or let `record` generate it.

Another note: properties used as keys in `HashMap`/`HashSet` should remain stable while the object is inside the collection. Mutating fields involved in `equals()`/`hashCode()` after insertion can cause lookups to fail, even when the comparison rule itself is mathematically transitive.

## 6. Cases Easily Confused with Transitivity Bugs

- **Symmetry differs from transitivity.** If `a.equals(b)` differs from `b.equals(a)`, that is a symmetry bug. Superclass/subclass types writing custom `equals()` on different fields can exhibit symmetry bugs, transitivity bugs, or both; each property must be tested separately.
- **`==` differs from `equals()`.** `==` compares whether two references point to the exact same object; it is not the definition of logical identity for value objects.
- **`BigDecimal.compareTo()` and `BigDecimal.equals()` have different criteria.** For example, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, whereas those two objects are not `equals()` because their scales differ. This is **not evidence of a transitivity violation**: they are simply two relations with different semantics. Do not mix the criteria of both methods in one argument.
- **`Objects.equals(a, b)` only provides null-safety.** It calls `a.equals(b)` when `a` is non-null; it does not fix a class's non-transitive logic.
- **Consistency over time also matters.** If `equals()` depends on mutable data, clocks, or unstable context, the same pair of objects may return different results across calls; that issue must be addressed alongside transitivity.

## 7. How to Check During Code Review or Testing

For a class with a custom `equals()`, proceed step by step:

1. **Define logical identity:** specifically which properties/keys make two objects equal? Is that definition consistent across all objects, subclasses, and boundary data?
2. **Construct intentional triples:** choose `a`, `b`, and `c` such that both `a.equals(b)` and `b.equals(c)` are `true`; assert that `a.equals(c)` is also `true`. Specifically test values near thresholds, different class types, empty states, and extreme values where relevant.
3. **Check the full contract:** `a.equals(a)` is true; `a.equals(b) == b.equals(a)`; results repeat under unchanged state; `a.equals(null)` is false; when `equals` is true, hashes must match.
4. **Test with collections:** verify add/lookup/remove scenarios with equivalent objects while keeping keys immutable. Collection tests provide supporting evidence but do not replace triple checks.
5. **General reasoning:** compare the algorithm against the definition of an equivalence relation. For instance, "same immutable identifier" or "same canonical key" has a clear transitivity proof; "differs by at most epsilon" does not.

An assertion template for use in tests (assuming three objects `a`, `b`, and `c` have already been created):

```java
if (a.equals(b) && b.equals(c) && !a.equals(c)) {
    throw new AssertionError("equals() violates transitivity");
}
```

This is a **test fragment**, not a standalone Java file. When `a`, `b`, and `c` are the three `NearReading(0)`, `NearReading(8)`, and `NearReading(16)` objects in the program above, the assertion throws an error as expected; with a valid equality definition, no counterexample triple can exist.

## 8. Key Takeaways

Transitivity states that **when `a.equals(b)` and `b.equals(c)` are both true, `a.equals(c)` must be true**. It ensures objects considered "the same value" form consistent equivalence classes. Do not use tolerance ranges, "similar" rules, or comparison criteria that vary by object to define `equals()`. Define explicit equality keys or state; if approximation is needed, extract it into a separate operation.