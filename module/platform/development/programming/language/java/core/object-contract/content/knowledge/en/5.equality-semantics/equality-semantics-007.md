# Why Comparing Floating-Point Numbers With a Tolerance Can Break Transitivity

## 1. The Problem: Is "Approximately Equal" Truly "Equal"?

When working with floating-point numbers in Java, we frequently encounter representation and arithmetic errors in `double`/`float`. For instance, adding `0.1 + 0.2` does not necessarily yield the same `double` value as the literal `0.3`. A common technique to check whether two numeric results are close enough is using a **tolerance** (or epsilon):

```java
static boolean approximatelyEqual(double x, double y, double epsilon) {
    return Math.abs(x - y) <= epsilon;
}
```

This is an **illustrative snippet**, without handling `NaN`, infinity, invalid arguments, or overflow in subtraction. Its usual meaning is: the distance between two numbers is no greater than `epsilon`.

The issue arises when we turn this “approximately equal” result into the definition of `equals()`. Under the `Object.equals(Object)` contract, transitivity must hold:

> If `a.equals(b)` is true and `b.equals(c)` is true, then `a.equals(c)` must also be true, for every triple of objects `a`, `b`, `c`.

The relation `|x - y| <= epsilon` for `epsilon > 0` **does not guarantee transitivity**, even though it looks like an equality comparison. Therefore, an “approximately equal” function can be useful for checking measurement results, yet is unsuitable as a replacement for `equals()`.

## 2. Concrete Counterexample With Three Numbers

Choose `epsilon = 0.125` and three values:

- `a = 1.0`;
- `b = 1.09375`;
- `c = 1.1875`.

The values above as well as `0.125` are all represented **exactly** in binary floating-point (IEEE 754 binary floating-point), so we do not need to rely on rounding error to obtain a counterexample.

| Comparison | Absolute distance | Less than or equal to `0.125`? |
| --- | ---: | --- |
| `a` vs `b` | `|1.0 - 1.09375| = 0.09375` | Yes, `true` |
| `b` vs `c` | `|1.09375 - 1.1875| = 0.09375` | Yes, `true` |
| `a` vs `c` | `|1.0 - 1.1875| = 0.1875` | No, `false` |

Result:

```text
a ~ b: true
b ~ c: true
a ~ c: false
```

The `~` symbol here denotes the “approximately equal within epsilon” relation, **not a Java operator**.

Because both `a ~ b` and `b ~ c` are true while `a ~ c` is false, this relation is not transitive. This is the core reason: **being pairwise “close” does not mean the endpoints of a chain are close to each other**.

### Explanation via the Triangle Inequality

For real numbers, we have:

```text
|a - c| <= |a - b| + |b - c|
```

If each interval `|a-b|` and `|b-c|` does not exceed `epsilon`, we can only deduce:

```text
|a - c| <= 2 * epsilon
```

We **cannot** deduce `|a-c| <= epsilon`. In the example, two steps of length `0.09375` combine into `0.1875`; each step satisfies the condition, yet the sum exceeds the threshold `0.125`.

The argument applies even when the numbers are mathematical real numbers with infinitely exact arithmetic. `double` rounding error can complicate epsilon checks further, but it is **not the root cause** of losing transitivity.

## 3. Testing Directly With Java 17+

Save the complete program below as `FloatingToleranceDemo.java`:

```java
public class FloatingToleranceDemo {
    private static final double EPSILON = 0.125;

    // This is an "approximately equal" check for finite measurements.
    // Intentionally NOT used as Object.equals().
    static boolean near(double x, double y) {
        return Double.isFinite(x)
                && Double.isFinite(y)
                && Math.abs(x - y) <= EPSILON;
    }

    // A grouping key illustrating a proper equality relation.
    record BucketKey(int index) {}

    static BucketKey fixedBucket(double value) {
        // Domain bound solely so the example converts safely to int.
        if (!Double.isFinite(value) || value < -1000 || value > 1000) {
            throw new IllegalArgumentException("Value outside supported range");
        }
        return new BucketKey((int) Math.floor(value / 0.5));
    }

    public static void main(String[] args) {
        double a = 1.0;
        double b = 1.09375;
        double c = 1.1875;

        System.out.println("epsilon: " + EPSILON);
        System.out.println("|a-b|: " + Math.abs(a - b));
        System.out.println("|b-c|: " + Math.abs(b - c));
        System.out.println("|a-c|: " + Math.abs(a - c));
        System.out.println("near(a,b): " + near(a, b));
        System.out.println("near(b,c): " + near(b, c));
        System.out.println("near(a,c): " + near(a, c));

        // Premise is true, yet conclusion is false.
        boolean chainIsTransitive =
                !(near(a, b) && near(b, c)) || near(a, c);
        System.out.println("near transitive for this triple: "
                + chainIsTransitive);

        BucketKey ka = fixedBucket(a);
        BucketKey kb = fixedBucket(b);
        BucketKey kc = fixedBucket(c);
        System.out.println("bucket(a): " + ka.index());
        System.out.println("bucket(b): " + kb.index());
        System.out.println("bucket(c): " + kc.index());
        System.out.println("bucket a=b: " + ka.equals(kb));
        System.out.println("bucket b=c: " + kb.equals(kc));
        System.out.println("bucket a=c: " + ka.equals(kc));

        System.out.println("near(NaN,NaN): "
                + near(Double.NaN, Double.NaN));
        System.out.println("near(+inf,+inf): "
                + near(Double.POSITIVE_INFINITY,
                       Double.POSITIVE_INFINITY));
    }
}
```

Compile and run commands:

```bash
javac FloatingToleranceDemo.java
java FloatingToleranceDemo
```

Exact stdout output:

```text
epsilon: 0.125
|a-b|: 0.09375
|b-c|: 0.09375
|a-c|: 0.1875
near(a,b): true
near(b,c): true
near(a,c): false
near transitive for this triple: false
bucket(a): 2
bucket(b): 2
bucket(c): 2
bucket a=b: true
bucket b=c: true
bucket a=c: true
near(NaN,NaN): false
near(+inf,+inf): false
```

Things to observe:

1. `near(a, b)` and `near(b, c)` are both `true`, yet `near(a, c)` is `false`: a single counterexample suffices to refute the statement “this approximate equality relation is always transitive”.
2. The expression `!(P && Q) || R` tests the implication `(P && Q) => R` for **one triple**. A `false` result proves the triple breaks transitivity; a `true` result on another triple is insufficient to prove the contract holds across the entire domain.
3. `BucketKey` is a `record` whose `equals()`/`hashCode()` are based on `index`. When `index(a) = index(b)` and `index(b) = index(c)`, then `index(a) = index(c)`; thus equality by grouping key is transitive. All three values here fall into the bucket with index `2`.
4. Buckets have boundaries: for example, `1.49` and `1.51` are very close yet belong to two different buckets (`Math.floor(x / 0.5)` yields `2` and `3`). **Bucket equality is not equivalent to “differing by at most epsilon”**; use it only when the domain truly defines fixed intervals.
5. `near` intentionally rejects `NaN` and infinity to reflect a domain of finite measurements. This is not an `equals()` design because `equals()` must be reflexive for every object, including objects containing special values.

## 4. Why Does Choosing a Smaller Epsilon Still Not Solve It?

Reducing epsilon can decrease the number of accepted pairs, yet for **any positive epsilon** on a sufficiently wide domain, one can still construct three values:

```text
a = 0
b = 0.75 * epsilon
c = 1.50 * epsilon

|a-b| = 0.75 * epsilon <= epsilon
|b-c| = 0.75 * epsilon <= epsilon
|a-c| = 1.50 * epsilon >  epsilon
```

This is a mathematical proof for real numbers; when implementing with `double`, one must account for range, representation resolution, and rounding operations. Therefore, claiming “**every positive epsilon is guaranteed to produce a counterexample on every set of `double` values**” is too strong: on a discrete or tiny domain, three such elements might not exist. What is true is that a threshold-distance formula **does not guarantee transitivity in principle**, so it must not be used as the general basis of `equals()`.

Changing the comparison from `<= epsilon` to `< epsilon` does not fix it either. Choosing intervals smaller than epsilon whose sum exceeds epsilon still creates a counterexample. Likewise, replacing an absolute threshold with a relative threshold based on magnitude `max(|x|, |y|)` can be useful for numerical computation, yet **does not automatically confer transitivity**.

## 5. Distinguishing Three Different Needs

| Need | Appropriate approach | Property to note |
| --- | --- | --- |
| Are two computed/measured results close enough? | Dedicated method `near`/`withinTolerance` | Approximate closeness may not be transitive |
| Do two values carry the same logical identity in a Java object? | `equals()` and `hashCode()` based on stable, consistent criteria | Must satisfy reflexive, symmetric, transitive, consistent, non-`null` |
| Do two numbers belong to the same business grouping interval? | Normalize into a bucket key and compare keys | Key equality is transitive, yet has hard boundaries |

### a. When You Only Need Approximate Comparison

An explicit-intent API can accept tolerance at the call site:

```java
static boolean nearFinite(double x, double y, double epsilon) {
    if (!Double.isFinite(epsilon) || epsilon < 0) {
        throw new IllegalArgumentException("Invalid epsilon");
    }
    return Double.isFinite(x)
            && Double.isFinite(y)
            && Math.abs(x - y) <= epsilon;
}
```

This is an **isolated illustrative method**, not a program with `main`. It fits when the usage domain consists of finite numbers, subtraction does not overflow, and absolute distance is the right criterion. Examples: evaluating algorithm outputs on fixed-scale data, checking sensor values within a specified tolerance, or comparing output error in tests.

For values with widely differing magnitudes, you may need relative tolerance, combined absolute and relative tolerance, or ULP checks (units in the last place at the value region under consideration). Which choice to pick depends on the numerical problem; **all remain closeness checks**, not a replacement for the `equals()` contract.

Extreme-value note: `Math.abs(x-y)` can become `Infinity` when two very large finite numbers with opposite signs cause subtraction to overflow. A reliable numeric library implementation must define behavior for overflow, underflow, `NaN`, `Infinity`, `+0.0`/`-0.0`, and negative/non-finite epsilon.

### b. When You Need to Define `equals()`

Do not implement patterns like:

```java
// DESIGN ANTI-PATTERN; do not copy into production classes:
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof Measurement other)) {
        return false;
    }
    return Math.abs(this.value - other.value) <= EPSILON;
}
```

The fragment above assumes it sits inside a class with type `Measurement`, field `value`, and constant `EPSILON`. It intentionally demonstrates a broken rule, **not a standalone runnable file**. Beyond the transitivity bug, the comparison is unspecified for `NaN`/infinity, and how `hashCode()` is computed may further violate the contract.

Instead, first determine logical identity: same identifier? same value components? same normalized unit? same quantized key per business rules? Then compare **deterministic, stable keys**. An immutable class or `record` whose components have valid equality semantics is usually a manageable choice.

Values requiring approximate comparison can remain stored in the record and be compared through a different method, such as `measurement.closeTo(other, tolerance)`. Do not force the notion of “close enough” into “same logical object”.

### c. When Using Bucketing/Quantization

If the business domain snaps values to multiples of a measurement step—for example, partitioning into intervals `[0.0, 0.5)`, `[0.5, 1.0)`, `[1.0, 1.5)`—compute the bucket key first and compare only the keys. Objects mapped to the same key form an **equivalence class**.

However, positions near a boundary can be split into different buckets despite a tiny difference; step size and rounding policy must be decided by business rules. In code using `double`, specify domain bounds, handle special values, and control division/multiplication precision when computing keys; do not assume `Math.round(x / step)` is accurate for arbitrarily huge numbers.

## 6. Relationship With `hashCode()` and Collections

Collections such as `HashSet` and `HashMap` assume objects obey the equality contract. If epsilon is put into `equals()`:

- An object `a` can be considered equal to `b`, `b` equal to `c`, yet `a` not equal to `c`. The notion of “duplicate value” during search, insertion, removal, and deduplication loses consistency.
- `hashCode()` must also satisfy: when `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()`. Taking the hash directly from a `double` generally fails for pairs considered approximately equal under epsilon. Rounding to hash into fixed buckets still fails to rescue equality defined by **pairwise distance** at bucket boundaries.
- Giving every object the same hash may formally satisfy “equal implies equal hash”, yet causes heavy collisions and **still does not fix the transitivity bug**.

Similarly, `TreeSet`/`TreeMap` rely on ordering via `Comparator`. A comparator returning `0` when two numbers are merely “close enough” can also produce inconsistent ordering, violating the requirements of a valid order. When sorting or keying is needed, define a clear order/key instead of pairwise “close enough counts as equal”.

## 7. Common Java Misconceptions

1. **`==` between `double`s and `Double.equals` do not behave identically on all special values.** For primitive `double`, `Double.NaN == Double.NaN` is `false` and `+0.0 == -0.0` is `true`. For `Double.equals`, objects holding `NaN` are considered equal and `+0.0` differs from `-0.0`. The two have different rules; choose the appropriate semantics rather than mixing them.
2. **`Double.compare(x, y) == 0` is a comparison under the total order defined for `double` values**, distinct from an epsilon closeness check. It distinguishes signed zeros and groups NaN representations consistently; if used as an equality relation, transitivity is guaranteed by a consistent comparison criterion.
3. **A small test suite does not prove validity for all triples.** You must reason from the comparison rule itself; for tolerance checks, a three-element counterexample is already enough to prove the flaw.
4. **Transitivity failure differs from rounding error.** The exact same example can use exactly representable binary numbers. Replacing `double` arithmetic with `BigDecimal` still does not make “within epsilon” a transitive relation.
5. **Arithmetic equality and representational equality can differ.** For `BigDecimal`, `compareTo` can treat `1.0` and `1.00` as the same numeric value, while `equals` distinguishes scale. Having two different criteria does not by itself prove either lacks transitivity; what matters is consistently using one criterion for each relation.

## 8. Self-Check Questions

**Question 1.** With `epsilon = 0.2`, `a = 2.0`, `b = 2.15`, `c = 2.3`, what will the three closeness checks yield?

Ideal distance answer: `|a-b| = 0.15 <= 0.2`, `|b-c| = 0.15 <= 0.2`, yet `|a-c| = 0.3 > 0.2`. This remains a transitivity counterexample. When running with `double`, approximate values may not match those exact decimals, yet the gaps are chosen far enough from the threshold that the boolean outcomes match the description.

**Question 2.** Does changing to `epsilon = 0.001` solve the root problem?

No. With a sufficiently wide numeric domain, you can still choose two individual steps not exceeding `0.001` whose sum exceeds `0.001`. Shrinking tolerance only changes which pairs are accepted.

**Question 3.** Why is bucket-key equality valid with respect to transitivity even though two very close numbers sometimes fall into different buckets?

Because the relation is defined as **“has the same key”**, not “is close to”. Key equality is stable and transitive; bucket boundaries are a semantic trade-off that must be explicitly accepted.

**Question 4.** When testing floating-point computations, should `Double.compare(x, y) == 0` always be used?

Not necessarily. If the goal is to evaluate whether a result is near an expected value within an error margin, an explicit tolerance check is more appropriate. However, if defining an object's logical identity or a collection key, a non-transitive tolerance relation should not be used.

## Conclusion

**Comparing floating-point numbers with an epsilon threshold only ensures pairwise closeness.** Two consecutive pairs meeting the threshold can still cause the first–last pair to exceed it (`0.09375 + 0.09375 > 0.125`). This is a property of distance relations, not a quirk of how Java rounds `double`. Use a separate method for approximate checks and use a stable, transitive equality criterion when designing `equals()`, `hashCode()`, or collection keys.