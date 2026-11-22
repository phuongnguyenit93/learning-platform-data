# Do Not Arbitrarily Use Approximate Comparison as `equals` or Sort Order

## 1. The Core Problem

When using `float` or `double` in Java, learners are often advised to avoid `a == b` after calculations with rounding error. That advice makes sense for **tolerance checks driven by measurement requirements**, yet there is a crucial boundary:

> **"Two numbers being close enough" is not automatically a valid equality relation for implementing `equals`, `hashCode`, `Comparator`, or keys in `HashMap`/`TreeMap`.**

Consider the rule "treat as equal if the difference does not exceed 0.1":

```java
static boolean close(double a, double b) {
    return Math.abs(a - b) <= 0.1;
}
```

Take three values:

```text
a = 0.00
b = 0.09
c = 0.18

close(a, b) = true
close(b, c) = true
close(a, c) = false
```

This is a **non-transitive** case: `a` is close to `b` and `b` is close to `c`, yet `a` is not close to `c`. If you let `close` replace `equals` or return `0` in `Comparator.compare`, data structures that rely on a **consistent** notion of equality or ordering can behave counterintuitively.

This lesson belongs to **Java Core — Numbers / Floating-Point Comparison**. The goals are:

1. Know when to use **exact-value** floating-point comparison and when to use **approximate comparison** with tolerance.
2. Understand the **reflexivity, symmetry, and transitivity** requirements of `equals` and its relationship with `hashCode`.
3. Understand the `Comparator` contract, especially the constraint when `compare(a,b) == 0` and transitivity.
4. Explain why an "epsilon comparator" is unsafe for `TreeSet`, `TreeMap`, and sorting algorithms.
5. Use `Double.compare` or a **normalized/quantized representative key** with explicit rules.
6. Design separate approximate-equality checks for numerical algorithms, accounting for NaN, infinity, signed zero, absolute/relative error, and boundary data.

Examples run on **Java 17+**; no libraries outside the JDK are needed.

## 2. Four Distinct Questions to Separate

Questions about two `double` values do not necessarily share the same answer:

| Question | Suggested tool | Purpose |
| --- | --- | --- |
| Are two values equal under Java's floating-point comparison? | `a == b` | Primitive operator logic |
| Are two values close within the problem's error margin? | `isClose(a,b,absTol,relTol)` | Validating measurement/calculation error |
| Are two objects the same key under the application contract? | Consistent `equals` and `hashCode` | `HashSet`, `HashMap`, data modeling |
| What order do two elements have for sorting or tree storage? | Valid `Comparator`; usually `Double.compare` | `sort`, `TreeSet`, `TreeMap` |

Approximate comparison is a **query** about distance, not by default a **definition of identity** for an element.

Do not interpret "`==` is dangerous with `double`" as "replace every equality check with epsilon." Exact `==` can be completely right when checking sentinels, testing zero by value, or when a contract requires **exact floating-point values**. What matters is choosing the comparison that matches the data's meaning.

## 3. The Equivalence Relation That `equals` Must Obey

By the contract of `Object.equals`, for non-`null` objects, a valid equality relation must have at least the following properties:

- **Reflexive:** `x.equals(x)` must be `true`.
- **Symmetric:** if `x.equals(y)`, then `y.equals(x)`.
- **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
- **Consistent:** repeated calls do not change results if the information used for comparison has not changed.
- `x.equals(null)` must be `false`.

Furthermore, if `x.equals(y)` is `true`, then **`x.hashCode() == y.hashCode()` must hold**. Two unequal objects may still collide in hash code, but two equal objects must never have different hash codes.

### 3.1. Why Does Epsilon Break Transitivity?

Set `ε = 0.1` and define:

```text
a ≈ b  when  |a - b| <= ε
```

Choose `a = 0.00`, `b = 0.09`, and `c = 0.18`.

| Pair | Distance | "Nearly equal"? |
| --- | ---: | --- |
| `a,b` | 0.09 | Yes |
| `b,c` | 0.09 | Yes |
| `a,c` | 0.18 | No |

The `equals` contract requires that if `a` equals `b` and `b` equals `c`, then `a` must equal `c`. Yet the tolerance check says the opposite.

A **fixed positive** tolerance over a continuous numeric domain always exhibits "chaining across nearby steps." Changing `<=` to `<` or making epsilon smaller does not turn it into a general equivalence relation.

### 3.2. NaN Can Even Break Reflexivity If Written Wrong

Suppose:

```java
boolean near = Math.abs(Double.NaN - Double.NaN) <= 1e-9;
```

`near` is `false` because every `<=` ordering comparison with NaN returns false. If an object's `equals` uses that check to compare fields and **lacks an appropriate identity branch**, an object containing NaN may not even equal itself. Adding `if (this == other) return true;` only patches **one reflexivity case**—it does not fix the non-transitivity of the epsilon relation.

Putting an epsilon into `equals` is not a comprehensive "upgrade" for floating-point comparison.

## 4. `hashCode` Cannot Rescue a Non-Transitive Approximate Relation

A common mistake:

```java
// WRONG IDEA CODE, DO NOT USE IN equals:
return Math.abs(this.value - other.value) <= EPSILON;
```

and then implementing `hashCode` with `Double.hashCode(value)`. When `this.value` is close to `other.value` yet has different bits/values, two objects can be deemed equal by `equals` while having different hashes. This **directly violates** the contract between `equals` and `hashCode`.

Some try to fix it by making `hashCode()` return a constant `1` for every object. That avoids unequal hashes, yet:

1. It does not restore transitivity to `equals`.
2. It degrades `HashMap`/`HashSet` performance due to excessive collisions.
3. When items match pairwise without transitivity, lookup/removal/grouping operations remain impossible to define consistently.

**Conclusion:** a non-transitive approximate relation cannot become a valid `equals` merely by picking a clever `hashCode` formula.

## 5. `Comparator` Needs a Consistent Ordering Relation

Java defines `Comparator<T>` via the method:

```java
int compare(T a, T b);
```

Meaning of the result sign:

- Less than `0`: `a` comes before `b`.
- Equal to `0`: the comparator treats `a` and `b` as **order-equivalent**.
- Greater than `0`: `a` comes after `b`.

The comparator contract requires (stated mathematically):

1. **Swapping arguments flips the sign:** the sign of `compare(a,b)` must be opposite to `compare(b,a)`, with appropriate exception requirements.
2. **Transitivity:** if `a > b` and `b > c` under the comparator, then `a > c`.
3. **Consistency of the zero-comparison class:** if `compare(a,b) == 0`, then the signs of `compare(a,z)` and `compare(b,z)` must match for all `z`.

Requirement (3) means a comparator defines an **equivalence relation based on returning zero**. If you use "difference below epsilon" to return 0, requirement (3) easily breaks.

### 5.1. Typical Broken Comparator

```java
static final double EPSILON = 0.1;

static int badCompare(double a, double b) {
    if (Math.abs(a - b) <= EPSILON) {
        return 0;
    }
    return Double.compare(a, b);
}
```

This looks plausible because it separates distant numbers while treating close ones as equal. Yet with `a=0.00`, `b=0.09`, `c=0.18`:

```text
badCompare(a, b) = 0
badCompare(b, c) = 0
badCompare(a, c) = -1
```

The comparator just claimed `a` is equivalent to `b` and `b` is equivalent to `c`, yet claimed `a` comes before `c`. That is a **contract violation**, not merely "imperfect accuracy."

**Warning:** do not write `return (int) (a - b);` to compare `double`s. Subtraction can round, produce infinity or NaN; casting to `int` drops the fractional part, makes many distinct pairs return 0, and can even overflow/saturate. Even for `int`/`long`, subtracting to compare can overflow. Use a comparator with a well-defined contract.

## 6. Runnable Example: Same Data, `TreeSet` Results Depend on Insertion Order

Save the file **`BadEpsilonComparator.java`**:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class BadEpsilonComparator {
    private static final double EPSILON = 0.1;

    public static void main(String[] args) {
        double a = 0.00;
        double b = 0.09;
        double c = 0.18;

        System.out.println(near(a, b));
        System.out.println(near(b, c));
        System.out.println(near(a, c));

        Comparator<Double> bad = (x, y) ->
                near(x, y) ? 0 : Double.compare(x, y);

        System.out.println(bad.compare(a, b));
        System.out.println(bad.compare(b, c));
        System.out.println(bad.compare(a, c));

        TreeSet<Double> first = new TreeSet<>(bad);
        first.add(a);
        first.add(b);
        first.add(c);

        TreeSet<Double> second = new TreeSet<>(bad);
        second.add(b);
        second.add(a);
        second.add(c);

        System.out.println(first.size());
        System.out.println(second.size());
    }

    static boolean near(double x, double y) {
        return Math.abs(x - y) <= EPSILON;
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 BadEpsilonComparator.java
java BadEpsilonComparator
```

**Stdout on standard Java JDK:**

```text
true
true
false
0
0
-1
2
1
```

Interpretation:

- When adding `a` first: `b` is treated as the same element as `a`, while `c` differs from `a`, so the set has `2` elements.
- When adding `b` first: both `a` and `c` are treated by the comparator as the same element as `b`, so the set has only `1` element.
- The input is the exact same triple, yet "deduplication" depends on insertion order. This counterexample suffices to rule out epsilon comparators.

`TreeSet`/`TreeMap` use `compare(a,b) == 0` to decide whether two keys occupy the same position in the tree, **not `equals` in this step**. `sort` algorithms also assume comparators obey the contract; a broken comparator can produce nonsensical orderings or throw `IllegalArgumentException` for violating the contract in some cases, though it is not guaranteed to throw every time.

**Do not deploy a broken comparator just because "tests didn't crash" and conclude it is safe.** The contract must hold over the entire permitted data domain.

## 7. Using `Double.compare` for a Stable Ordering

For keys based on `double` values, the appropriate default choice is usually:

```java
Comparator<Double> byNumericValue = Double::compare;
```

Or for objects with a numeric property:

```java
Comparator<Reading> byValue =
        Comparator.comparingDouble(Reading::value);
```

Here `Reading` is a user-defined type with a `value()` method returning `double`; the second snippet is an **illustrative fragment**, not a complete program without declaring `Reading`.

`Double.compare` establishes a defined order even for special values:

- `Double.compare(-0.0, +0.0) < 0`: **negative zero comes before positive zero**.
- `Double.compare(Double.NaN, Double.NaN) == 0`: NaNs are treated as equivalent in `Double`'s ordering.
- NaN is ordered **greater than all other numeric values**, including `Double.POSITIVE_INFINITY`.
- Ordinary finite numbers and ±Infinity are ordered by their numeric values.

This differs from the primitive `==` operator:

```java
System.out.println(-0.0 == +0.0); // true
System.out.println(Double.compare(-0.0, +0.0)); // -1

System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
```

**Do not use `x < y ? -1 : x > y ? 1 : 0` as a general comparator for `double`**: with NaN both `<` and `>` are false, so it can return 0 for NaN and any number; for ±0, it also treats them as equal. If you want an ordering different from `Double.compare`, design the **entire** rule set (including NaN, ±Infinity, ±0) so it remains transitive and consistent.

### 7.1. A Stable Ordering Does Not Mean Measurements Are "Identical"

`Double.compare(a,b) == 0` is an **ordering criterion by IEEE 754 value** useful for keys; it is not a check of whether two measurements lie within allowed error. Thus, you can still use `isClose(a,b)` to display a warning "two sensors reported similar readings" while using `Double.compare` to sort a list by reading value.

## 8. `Double.equals`, `hashCode`, Signed Zero, and NaN

`Double.equals` has a different contract from primitive `==`:

| Case | Primitive `==` | `Double.equals` |
| --- | --- | --- |
| `+0.0` and `-0.0` | `true` | `false` |
| `Double.NaN` and `Double.NaN` | `false` | `true` |
| Two finite values with identical value representation | `true` | `true` |

`Double.equals` compares by the bit encoding returned by `Double.doubleToLongBits`; that method normalizes NaN forms to a canonical pattern while **preserving the ±0 distinction**. `Double.hashCode` is consistent with this contract.

Therefore, `HashSet<Double>` can keep `+0.0` and `-0.0` as two separate keys, while adding another canonically equivalent NaN does not create a new element.

### Runnable Example: Equality at Three Layers

Save **`FloatingIdentity.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class FloatingIdentity {
    public static void main(String[] args) {
        System.out.println(+0.0 == -0.0);
        System.out.println(Double.valueOf(+0.0)
                .equals(Double.valueOf(-0.0)));

        System.out.println(Double.NaN == Double.NaN);
        System.out.println(Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));

        System.out.println(Double.compare(-0.0, +0.0));
        System.out.println(Double.compare(Double.NaN,
                Double.POSITIVE_INFINITY));

        Set<Double> values = new HashSet<>();
        values.add(+0.0);
        values.add(-0.0);
        values.add(Double.NaN);
        values.add(Double.NaN);
        System.out.println(values.size());
    }
}
```

Run:

```bash
javac --release 17 FloatingIdentity.java
java FloatingIdentity
```

**Stdout:**

```text
true
false
false
true
-1
1
3
```

The two zero values differ under wrapper equality; the two NaNs are canonicalized for `equals`. This fits Java collections and is not meant to claim NaN obeys ordinary mathematical equality.

### 8.1. If You Write Your Own Type with a `double` Field

A valid option when **identity truly is the `Double` bit-value** is writing compatible `equals`/`hashCode`:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof Measurement other)) return false;
    return Double.doubleToLongBits(this.value)
            == Double.doubleToLongBits(other.value);
}

@Override
public int hashCode() {
    return Double.hashCode(value);
}
```

These are **two illustrative methods inside a `Measurement` class** having a `private final double value` field, not standalone Java code. Use `Double.doubleToLongBits` instead of raw bits if you want all NaN patterns to share the same `equals`/`hashCode` rule as the wrapper. Use `Double.compare` in comparators to stay compatible with wrapper ordering.

If object identity is a stable `id`, define `equals` by `id` and use the measurement only for filtering/approximate checks. Avoid letting a **mutable** floating-point field determine `hashCode` after the object has been placed into a `HashSet`/`HashMap`.

## 9. When Is **Approximate Comparison** Truly Appropriate?

A tolerance check is very useful when you care about **difference magnitude in a physical or numerical sense**, for example:

- Two temperature measurements differing within sensor error.
- Comparing a numerical algorithm's result with an expected value using a defined tolerance.
- Detecting simulation outputs that differ yet stay within acceptable bounds.
- Checking convergence under an error-based criterion with appropriately designed thresholds and stopping rules.

Yet the answer `isClose(a,b)` should be **a boolean for a specific query**, not used by default to decide which objects share a "key" in hash/tree collections.

### 9.1. Absolute Tolerance

A simple check:

```java
boolean near = Math.abs(actual - expected) <= absoluteTolerance;
```

If `absoluteTolerance` has measurement units (e.g., °C, meters, seconds), set the value according to business-accepted error; do not use one "magic ε" for all situations.

For example, `|1.00001 - 1.00002| <= 0.0001` makes sense when an error below `0.0001` units is all that is needed; yet that same epsilon may be too small or too large on another scale.

### 9.2. Relative Tolerance

When the magnitude scale varies, we can use:

```text
|a - b| <= relTol × max(|a|, |b|)
```

Relative error makes sense only when the scale is non-zero. Near zero, a pure relative tolerance becomes hard to use; an **absolute tolerance** part is usually needed for stability.

Combined example:

```text
|a - b| <= max(absTol, relTol × max(|a|, |b|))
```

This is a **chosen business rule**, not the language's equality definition. It is still **not generally transitive**.

### 9.3. Classifying NaN/Infinity and Validating Input

`Math.abs(a - b) <= eps` can return false for `a == b == Double.POSITIVE_INFINITY` because `+∞ - +∞` is NaN. With NaN, `<=` returns false. If a system wants "same infinity means same state," write that rule explicitly rather than inferring it from subtraction.

If a comparator uses `near` to return 0 and falls back to `Double.compare` on NaN, the mixed relation still is not guaranteed to be transitive. With negative or NaN epsilon, behavior becomes even murkier; **validate tolerances** right at the start.

## 10. Java 17+ Example for a Scope-Safe Approximate-Equality Query

Save to **`NearEnough.java`**:

```java
public class NearEnough {
    static boolean near(double a, double b,
                        double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }

        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false; // Policy: only compare finite numbers for closeness
        }

        double diff = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return diff <= Math.max(absTol, relTol * scale);
    }

    public static void main(String[] args) {
        System.out.println(near(0.0, 5e-13, 1e-12, 1e-8));
        System.out.println(near(0.0, 2e-12, 1e-12, 1e-8));
        System.out.println(near(1_000_000.0, 1_000_000.005,
                1e-12, 1e-8));
        System.out.println(near(Double.NaN, Double.NaN,
                1e-12, 1e-8));
        System.out.println(near(-0.0, +0.0,
                1e-12, 1e-8));
    }
}
```

Run:

```bash
javac --release 17 NearEnough.java
java NearEnough
```

**Expected stdout:**

```text
true
false
true
false
true
```

The function's goal is **querying "is the difference within the allowed margin" on finite data**. It must **not** be used directly for `equals` or `Comparator`.

Understand the limits of this sample function itself:

- If `a-b` overflows to `Infinity` even with finite inputs, this check returns false. That fits many small-tolerance closeness policies, though it needs analysis if the data domain is huge.
- The product `relTol * scale` can overflow for large tolerances; constrain `relTol` and input ranges per application. The function checks that tolerances are finite and non-negative, but does not replace evaluating numerical conditions across all IEEE 754 ranges.
- `-0.0` and `+0.0` are considered nearly equal; right if the application only cares about difference magnitude, **wrong** if signed zero must be preserved.
- Tolerance can be non-transitive regardless of how you combine absolute and relative thresholds.

## 11. If Grouping Is Needed: Choose a Stable **Key** Rule, Do Not Use Epsilon as equals

Sometimes the actual requirement is: "every number falling in the same interval should be grouped together." This is a different problem from "two numbers are within epsilon of each other."

You can define a function mapping **each value to a deterministic key**, then apply equality/ordering on the key:

```text
bucket(x) = floor((x - origin) / width)
```

Then:

```text
sameBucket(a, b) = bucket(a) == bucket(b)
```

Because each value has **one unique key**, the `sameBucket` relation is reflexive, symmetric, and transitive, assuming inputs and bucket rules are controlled consistently. It differs from distance-based closeness: two very close numbers on opposite sides of a bucket boundary **can** land in two different groups. This is an intentional trade-off to obtain **key-relation stability**.

### 11.1. Bucket Example for a Bounded Data Domain

Save **`BucketGrouping.java`**:

```java
public class BucketGrouping {
    static long bucket(double value) {
        if (!Double.isFinite(value)
                || value < -1_000_000.0
                || value > 1_000_000.0) {
            throw new IllegalArgumentException("Out of range");
        }
        return (long) Math.floor(value / 0.5);
    }

    public static void main(String[] args) {
        System.out.println(bucket(0.1));
        System.out.println(bucket(0.4));
        System.out.println(bucket(0.51));
        System.out.println(bucket(-0.1));

        System.out.println(bucket(0.1) == bucket(0.4));
        System.out.println(bucket(0.49) == bucket(0.51));
    }
}
```

Run:

```bash
javac --release 17 BucketGrouping.java
java BucketGrouping
```

**Stdout:**

```text
0
0
1
-1
true
false
```

`0.49` and `0.51` are only `0.02` apart yet fall into two different buckets. This is **not a bug** in the function: it shows that bucket equality and distance-based closeness are **two different concepts**.

The example deliberately uses `width=0.5` (exact in binary) and a bounded input range. If bucketing by decimal steps like `0.01` or very large numbers, consider boundary rounding, overflow/cast saturation, and rounding contracts. You can use `BigDecimal` for decimal data requiring exactness and choose an appropriate rounding mode. Do not pass NaN/Infinity into a bucket function without an explicit policy.

### 11.2. If You Want to Group by Error, You May Need a Clustering Algorithm

If the requirement is "measurements belong to the same cluster when linked by a chain of close neighbors," you are defining **connected components under a proximity relation**, not pairwise equality. A cluster can contain two points farther than epsilon apart if bridged by intermediate points. If the requirement is "every pair in a cluster is close," that is a different criterion. Explicitly pick the clustering problem; do not sneak it into `equals` or an arbitrary comparator.

## 12. Practical Notes with `HashMap`, `TreeMap`, `TreeSet`, and `sort`

### 12.1. `HashMap`/`HashSet`

Hash-based collections use a key's `hashCode` and `equals`. They expect a stable, transitive equality contract and consistent hashes. If an object holding a floating-point value changes **after being used as a key**, the key may no longer be found in its original bucket.

Situation to avoid:

```java
// Wrong idea: using a mutable field for hash/equality then changing it
// after the object has been inserted into a HashSet/HashMap.
```

This is a **description of a mistake**, not a runnable Java API. A better design is using **immutable** keys—for example an ID, measurement sample code, or a bucket key determined upfront.

### 12.2. `TreeMap`/`TreeSet`

Tree-based collections use `compare` or `compareTo` to determine order and key duplicates. If a comparator returns `0` for two objects that `equals` treats as distinct, the set can behave differently from an `equals`-based `Set`. Java permits comparators that are **inconsistent with equals** in certain contexts if documented; for `SortedSet`/`SortedMap`, inconsistency can violate general expectations of the `Set`/`Map` contracts.

However, a **non-transitive** comparator is a far more serious problem: it violates the `Comparator` contract itself and can yield path-dependent results, as in Section 6's example.

If you need to order by measurement and break ties by ID:

```java
// This snippet assumes Sample has value():double and id():long
Comparator<Sample> order =
        Comparator.comparingDouble(Sample::value)
                .thenComparingLong(Sample::id);
```

This is an **illustrative fragment**, requiring `Sample` to be declared. The comparator creates an order with clear criteria without using epsilon to return `0`. Note: adding an ID tie-breaker only resolves cases **already equal under a valid primary criterion**; it does not rescue a non-transitive epsilon comparator.

### 12.3. `Collections.sort` and `List.sort`

Sorting algorithms expect comparators to obey the contract. With a broken comparator, sort order may be inconsistent, or an exception may be thrown indicating a contract violation on certain inputs. **No exception thrown** does not prove the comparator is right; a transitivity counterexample suffices to reject its validity.

## 13. Special Floating-Point Pitfalls When Designing Equality/Ordering

### 13.1. Signed Zero

`+0.0 == -0.0` is `true`, whereas `Double.compare(-0.0,+0.0) < 0` and `Double.equals` distinguish the two zero forms.

If the application wants to merge both into one key, normalize by this rule:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

This method snippet turns `-0.0` into `+0.0`, keeping other numbers unchanged; use it only if zero's sign carries no meaning in subsequent operations. In division or `Math.atan2`, signed zero can have real significance.

### 13.2. NaN

`Double.NaN == Double.NaN` is false, whereas `Double.compare(Double.NaN, Double.NaN) == 0`. A hand-written comparator based on `a > b` and `a < b` usually breaks on NaN. When the domain forbids NaN, **block it with `Double.isFinite`** (which also excludes infinity) or `Double.isNaN`; if the domain allows NaN, explicitly define its ordering and equality.

### 13.3. Infinity and Subtraction Overflow

`Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` is NaN. `Double.MAX_VALUE - (-Double.MAX_VALUE)` overflows to infinity even though both inputs are finite. The formula `Math.abs(a-b)` is only suitable once you have evaluated the value domain and your policy for special results.

### 13.4. Tolerance Varies by Context

Acceptable error for temperature measurements can vary by unit, device accuracy, and sampling period. Error for numerical algorithms can vary with magnitude and operation accumulation. Do not define one global `EPSILON` and apply it to every field, domain, and feature.

### 13.5. BigDecimal Also Distinguishes Equality and Ordering

`BigDecimal` offers arbitrary-precision decimals, yet `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is false because `equals` checks scale as well, while `compareTo` returns `0` because the numeric values are equal. If using `BigDecimal` as a key, decide whether scale is part of identity or whether a normalization rule applies. Switching from `double` to `BigDecimal` **does not automatically solve every equals/comparator design issue**.

## 14. Process for Choosing a Comparison Relation in a Project

**Step 1 — Identify the purpose.** Do you need to answer "is it within allowed error," "is it the same entity," "is it in the same defined group," or "what is the sort order"?

**Step 2 — Identify the domain.** Are `NaN`, `Infinity`, `-0.0`, out-of-range values, or decimals needing exactness allowed? Do measurements need to be distinguished by unit, timestamp, or ID?

**Step 3 — If it is only an approximate-equality query**, choose absolute/relative tolerance from the problem, check finiteness and boundary datasets; return a separate `boolean`, not `equals`/`compare`.

**Step 4 — If identity is needed**, use a stable ID or a canonical/bucket key with an explicit policy, creating consistent `equals`/`hashCode`; avoid mutable fields.

**Step 5 — If ordering is needed**, use `Double.compare` or a comparator with transitive comparison steps, verify the `compare(a,b)==0` rule, and consider compatibility with key equality.

**Step 6 — Test counterexamples.** For the triple `0.00, 0.09, 0.18`, an approximate query may be non-transitive; however, any actual `equals` or comparator-zero used for keys must be transitive. Add datasets containing ±0, NaN, ±Infinity, large numbers, and values near bucket boundaries.

**Step 7 — Document the decision.** Write down: "tolerance-based closeness is a business query" or "group key is a 0.5 bucket on the validated domain," avoiding vague claims like "everything close is equal."

## 15. Property-Based Test Suite to Include

Instead of testing only arbitrary pairs, for comparators/equality test these **properties**:

| Property | Verification question |
| --- | --- |
| Reflexivity | For a valid object `x`, is `x.equals(x)` always true? |
| Symmetry | Do `x.equals(y)` and `y.equals(x)` match? |
| Transitivity | If `x == y` and `y == z` under custom equality, does `x == z` hold? |
| Hash consistency | If `x.equals(y)`, do their hashes match? |
| Comparator sign symmetry | Are the signs of `compare(x,y)` and `compare(y,x)` opposite? |
| Comparator transitivity | If `x>y` and `y>z`, does `x>z` hold? |
| Comparator zero consistency | If `compare(x,y)==0`, does every `z` see `x` and `y` with the same ordering sign? |
| Special values | How are ±0.0, NaN, ±Infinity, very large/very small numbers handled? |
| Mutable key | Can a key be mutated while inside a collection? |

**Mandatory triple to catch epsilon bugs:** `a=0.00`, `b=0.09`, `c=0.18`, `ε=0.1`. If a comparator returns `0` for `a,b` and `b,c` yet non-zero for `a,c`, stop and redesign the relation—do not just add more tests.

## 16. Common Misconceptions

1. **"All `double ==` comparisons are wrong."** False. `==` is an arithmetic comparison with a well-defined contract; what is wrong is using it for approximate equality when results have unaccounted error.
2. **"Adding epsilon is a general fix for `equals`."** False: closeness is usually not transitive.
3. **"`hashCode() = 1` makes epsilon equals valid."** False: transitivity is still broken.
4. **"A comparator returning 0 means distance is less than epsilon."** Only possible if the zero-returning relation remains a valid equivalence relation; an arbitrary difference threshold does not satisfy this.
5. **"`TreeSet` uses `equals` to deduplicate."** False: it uses comparator/natural-ordering comparison equal to 0.
6. **"Sorting without throwing an exception proves the comparator is right."** False: contract bugs may simply remain unexposed on the tested dataset.
7. **"`a < b ? -1 : a > b ? 1 : 0` is enough."** Insufficient for NaN and signed zero.
8. **"`Double.compare` is just `a-b`."** False: it defines clear ordering for NaN, ±0, and other numbers.
9. **"A 0.5 bucket is equivalent to closeness within 0.5."** False: two very close points across a bucket boundary can land in different groups.
10. **"NaN is always treated as unequal by every kind of comparison."** Primitive `==` and wrapper `equals` have different contracts.
11. **"Measurement values that are close should share the same HashMap key."** Not automatically; you need a stable identity policy.
12. **"Using BigDecimal means equals always compares numeric value."** False when scales differ.
13. **"Epsilon = 1e-9 works for every scale."** False; error must reflect units, scale, and contract.
14. **"A non-transitive zero relation can still make a valid comparator."** False; this directly violates the comparator contract.

## 17. Exercises with Answers

### Exercise 1 — Find the Violated Property

Given `ε=0.1`, `a=0.00`, `b=0.09`, `c=0.18`, identify which property of `equals` fails to hold.

**Answer:** transitivity. `near(a,b)` and `near(b,c)` are true, yet `near(a,c)` is false.

### Exercise 2 — Broken Comparator

Given a comparator that returns 0 if `Math.abs(x-y)<=0.1` and otherwise delegates to `Double.compare`, why should it not be used in a `TreeSet`?

**Answer:** the `compare(x,y)==0` relation is not transitive. `TreeSet` uses the comparator to determine duplicate keys, so insertion order can change the resulting contents.

### Exercise 3 — Distinguish `==` from `Double.compare`

Predict `-0.0 == +0.0` and `Double.compare(-0.0,+0.0)`.

**Answer:** `true` and `-1`. Java primitive equality treats signed zeros as equal, while wrapper comparison orders them distinctly.

### Exercise 4 — NaN

Predict `Double.NaN == Double.NaN` and `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))`.

**Answer:** `false` and `true`, following the separate contracts of primitive equality and wrapper equality.

### Exercise 5 — HashCode

Why should you not implement `equals` as `Math.abs(a-b)<=eps` while implementing `hashCode` as `Double.hashCode(a)`?

**Answer:** two objects deemed equal within epsilon can have different hashes. That violates the requirement "equals true ⇒ equal hashCode," in addition to lacking transitivity.

### Exercise 6 — Choosing the Comparison for the Need

A temperature measurement has a tolerance of ±0.2°C. Which relation should determine **whether two measurements differ within tolerance**, and which should determine **whether two records share the same ID**?

**Answer:** an approximate query based on `Math.abs(temp1-temp2)<=0.2` for the first requirement; equality by stable `id` for the second. Never use temperature distance as record identity.

### Exercise 7 — Bucket Boundary

Given `bucket(x)=floor(x/0.5)`, are `bucket(0.49)` and `bucket(0.51)` equal?

**Answer:** no; they fall into buckets `0` and `1` even though they are only 0.02 apart. This is a consequence of a quantization policy, not a transitivity violation.

### Exercise 8 — Infinity

Why is `Math.abs(Double.POSITIVE_INFINITY-Double.POSITIVE_INFINITY)<=1e-6` false?

**Answer:** `Infinity-Infinity` is NaN, and `NaN <= ...` is false. If business logic wants to recognize "same infinity," an explicit rule is needed.

### Exercise 9 — Secondary Comparator

When sorting measurement samples by value, if two values are equal under `Double.compare`, you want to break ties by record ID. What should you do?

**Answer:** use `Comparator.comparingDouble(Sample::value).thenComparingLong(Sample::id)` with `Sample` providing both methods. Do not use an epsilon comparator hoping ID will fix its violations.

### Exercise 10 — Choosing a Data Structure

You need to store values and support the query "list all numbers within 0.1 of target." Do you have to turn the closeness rule into `equals`/comparator?

**Answer:** no. Store using a valid key/order (`Double.compare` or an ID key), then perform a separate distance query over candidate elements. You can use a range query with appropriate bounds and filter with a `near` function; keep the policy for NaN/Infinity clear.

## 18. Checklist Before Using Floating-Point Numbers as Keys or Ordering

- [ ] I know clearly that **approximate equality** is an error query, not equality by default.
- [ ] I check reflexivity, symmetry, **transitivity**, and `hashCode` when implementing `equals`.
- [ ] I check the `Comparator` contract, especially consistency when `compare(a,b)==0`.
- [ ] I never return 0 in a comparator merely because `Math.abs(a-b)<=epsilon`.
- [ ] I use `Double.compare`/`Comparator.comparingDouble` when ordering by floating-point value.
- [ ] I know the different rules of primitive `==`, `Double.equals`, and `Double.compare` for NaN and signed zero.
- [ ] I choose tolerances by **units and magnitude scale**, validating NaN/Infinity and overflow cases.
- [ ] If stable grouping is needed, I define a **canonical/bucket key** with explicit group boundaries.
- [ ] I never mutate a field participating in equality/hash while the object is inside a hash collection.
- [ ] I test sorting/sets with the triple `0.00,0.09,0.18` as well as ±0, NaN, and ±Infinity.
- [ ] I compiled/ran at least three examples and understand why results differ by collection mechanism.
- [ ] Comparison/grouping/sorting rules are clearly documented for future maintainers.

**Official Documentation (Java SE 17):**

- [Object.equals and Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): equality and hash contracts.
- [Comparator interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): ordering, transitivity, and consistency.
- [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `compare`, `equals`, `hashCode`, signed zero, NaN.
- [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): ordering and equality criteria.
- [TreeMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): comparator-sorted map.
- [HashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): uses key equality/hash.
- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `equals` distinguishes scale, `compareTo` compares numeric value.

**Conclusion:** approximate error is **problem-domain information**, whereas `equals`, `hashCode`, and `Comparator` are **data-structure contracts**. Keep them separate: use tolerance for numerical queries; use stable keys or `Double.compare` for identity and ordering.
