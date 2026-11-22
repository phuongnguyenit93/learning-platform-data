# Comparing `null` and choosing an API contract when working with `BigDecimal`

`BigDecimal` is a reference type, so a `BigDecimal` variable can be `null`. When writing a comparison API, two independent questions must be answered: **are two numbers compared by numeric value or by representation (including scale)?**, and **how must one or both missing values be handled?**. The missing-value policy affects business rules, sorting operations, ordered collections, and API return types.

This lesson distinguishes three contracts: (1) rejecting `null`, (2) ordering `null` in a defined position, and (3) returning an "unknown" result when an operand is missing. The goal is to choose an appropriate contract and enforce it consistently, without conflating `null` with 0 or with an equal comparison result.

## 1. `null` is not the number 0

```java
BigDecimal zero = BigDecimal.ZERO; // Has a value, equal to 0.
BigDecimal missing = null;         // No BigDecimal object.
```

In financial reporting, a balance of `0` means the balance has been determined and equals zero; `null` can mean not provided, not yet calculated, or not applicable. Replacing `null` with `BigDecimal.ZERO` on your own is a **business decision**, not a bug-fix technique. It can skew threshold comparisons or turn "unknown" into "equal to 0."

Before implementing, verify whether the data source permits `null` and why. If an argument is always required, the API should reject missing data. If data can be missing, explicitly decide where missing rows belong in a list or whether to return an inconclusive status.

## 2. Native behavior of `BigDecimal` when encountering `null`

`BigDecimal.compareTo(BigDecimal)` compares by **numeric value** and returns a negative integer, 0, or a positive integer. Comparing with `null` is not supported:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.compareTo(b);    // 0: same numeric value.
a.equals(b);       // false: scale 1 differs from scale 2.
a.equals(null);    // false.
a.compareTo(null); // NullPointerException.
```

If `a` itself is `null`, calling `a.compareTo(b)` or `a.equals(b)` throws `NullPointerException` because there is no receiver object. The methods `a.min(null)` and `a.max(null)` are not null-safe options either.

`Objects.equals(left, right)` differs from `compareTo`:

- `Objects.equals(null, null)` returns `true`.
- `Objects.equals(null, BigDecimal.ZERO)` returns `false`.
- `Objects.equals(new BigDecimal("1.0"), new BigDecimal("1.00"))` returns `false`, because it still uses `BigDecimal.equals`.
- `Objects.equals` only solves **equality checks via `equals`**; it does not replace `BigDecimal.compareTo` or establish numeric ordering.

`Objects.compare(left, right, comparator)` also does not automatically make a comparator accept null. It returns 0 if both references point to the same object (including when both are null); if the references differ, it invokes the provided comparator. With a comparator that forbids null, having only one side null still throws an exception.

### `compareTo` and `equals`: two relations to distinguish

| `BigDecimal` pair | `compareTo == 0` | `equals` |
| --- | --- | --- |
| `"1.0"` / `"1.00"` | `true` | `false` |
| `"0"` / `"0.00"` | `true` | `false` |
| `"1.0"` / `"2.0"` | `false` | `false` |
| `"1.00"` / `"1.00"` | `true` | `true` |

`BigDecimal`'s `equals` and `hashCode` consider both value and **scale**. If you need to check "same monetary amount" regardless of scale, `compareTo == 0` is usually appropriate. If representation (`1.0` vs `1.00`) is part of the data, `equals` is the better choice.

## 3. Contract A: `null` is an invalid input

For mandatory thresholds, approved totals, or recorded payment amounts, it is usually best to require **both operands to be non-null**. Failing at the parameter entry point ensures bugs are caught clearly:

```java
import java.math.BigDecimal;
import java.util.Objects;

static int compareRequired(BigDecimal left, BigDecimal right) {
    Objects.requireNonNull(left, "left must not be null");
    Objects.requireNonNull(right, "right must not be null");
    return Integer.signum(left.compareTo(right));
}
```

This is an illustrative method; place it inside an appropriate class. `Objects.requireNonNull` throws `NullPointerException` with a message identifying the offending argument. `Integer.signum(...)` normalizes the result to **-1, 0, or 1**; without normalization, `compareTo` only promises negative/0/positive, not necessarily -1/0/1.

The contract can be documented with Javadoc:

```java
/**
 * Compares two required decimal values.
 * @param left must not be null
 * @param right must not be null
 * @return -1 if left is less than right, 0 if numerically equal,
 *         1 if left is greater than right
 * @throws NullPointerException if either argument is null
 */
```

This Javadoc snippet merely illustrates the documentation for the method above. The API should clarify that **0 means both values were compared and are equal**, not that data is missing.

When writing comparison conditions, write `left.compareTo(right) > 0` instead of `left.compareTo(right) == 1`, since the `Comparable` contract only guarantees the **sign** of the result.

**Do not** catch `NullPointerException` and automatically return 0: doing so turns an error into an "equal" conclusion, leading to incorrect business logic branches.

## 4. Contract B: `null` is ordered first or last

If a list must still be sorted when some amount fields are missing, Java provides `Comparator.nullsFirst` and `Comparator.nullsLast`. They define a deterministic order for `null` and non-null values:

```java
import java.math.BigDecimal;
import java.util.Comparator;

Comparator<BigDecimal> nullsFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<BigDecimal> nullsLast =
        Comparator.nullsLast(Comparator.naturalOrder());
```

In `nullsFirst`, `null` precedes all non-null values; in `nullsLast`, `null` follows all non-null values. Two `null`s are considered equal for **sorting** (`compare(null, null) == 0`). When both are non-null, the comparator uses `BigDecimal`'s natural ordering, i.e., `compareTo`.

| Two values | `nullsFirst` | `nullsLast` |
| --- | --- | --- |
| `null`, `null` | `0` | `0` |
| `null`, `BigDecimal.ZERO` | Negative | Positive |
| `BigDecimal.ZERO`, `null` | Positive | Negative |
| `1.0`, `1.00` | `0` | `0` |
| `2`, `1` | Positive | Positive |

Placing `null` first or last is strictly a **display ordering convention**. It does not mean an "unknown" amount is actually smaller or larger than any amount. Do not implicitly use a display convention as a business comparison rule.

For example, the snippet below puts missing values at the end:

```java
List<BigDecimal> values = new ArrayList<>(Arrays.asList(
        new BigDecimal("2.0"),
        null,
        new BigDecimal("1.00"),
        new BigDecimal("1.0"),
        null,
        BigDecimal.ZERO));

values.sort(Comparator.nullsLast(Comparator.naturalOrder()));
System.out.println(values);
```

This snippet requires imports for `BigDecimal`, `List`, `ArrayList`, `Arrays`, and `Comparator`, and must be inside a method. Output:

```text
[0, 1.00, 1.0, 2.0, null, null]
```

`List.sort` preserves the relative order of elements whose comparator result is 0, so `1.00` stays ahead of `1.0`. Numerically equal values are not forced to the same scale.

When you want **descending order with null still at the end**, pick reverse order for numbers first and then wrap it with the null policy:

```java
Comparator<BigDecimal> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

`Comparator.nullsLast(Comparator.naturalOrder()).reversed()` reverses the **entire** ordering, including null placement; in that case nulls move to the front.

### Element `null` vs property `null`

Suppose there is a record consisting of an invoice code and an amount:

```java
record Invoice(String code, BigDecimal amount) {}

Comparator<Invoice> byNullableAmount =
        Comparator.comparing(
                Invoice::amount,
                Comparator.nullsLast(Comparator.naturalOrder()));
```

The comparator above allows `amount()` to be null, but **does not** allow `Invoice` itself to be null, because the method reference still has to invoke `amount()` on an existing object. If the list can also contain null elements:

```java
Comparator<Invoice> nullableInvoices =
        Comparator.nullsLast(
                Comparator.comparing(
                        Invoice::amount,
                        Comparator.nullsLast(Comparator.naturalOrder())));
```

These record and comparator examples are code snippets that must be placed inside a complete program. Two layers of null are handled independently: null on the **element** and null on the **amount field**. Do not wrap the wrong layer and assume every null case is now safe.

## 5. Contract C: missing value means **inconclusive**

For a business question like "is the current price higher than the limit?", if either number has not been supplied, the sensible answer may be "unknown", rather than "less than", "equal to", or "greater than".

A comparison API returning a plain `int` has no room to express that fourth state. In Java, you can use `OptionalInt`:

```java
import java.math.BigDecimal;
import java.util.OptionalInt;

static OptionalInt compareIfPresent(BigDecimal left, BigDecimal right) {
    if (left == null || right == null) {
        return OptionalInt.empty();
    }
    return OptionalInt.of(Integer.signum(left.compareTo(right)));
}
```

`OptionalInt.empty()` means **no comparison result**, whereas `OptionalInt.of(0)` means **both values were present and equal**. In particular, never convert `empty()` into 0 unconditionally.

Callers can handle it as:

```java
OptionalInt result = compareIfPresent(amount, limit);
if (result.isEmpty()) {
    // Unknown: request missing data or display a distinct status.
} else if (result.getAsInt() > 0) {
    // amount is known and greater than limit.
} else {
    // amount is known and less than or equal to limit.
}
```

`amount` and `limit` in this example are application `BigDecimal` variables; the snippet does not run standalone. For complex business APIs, you can use an enum `LESS`, `EQUAL`, `GREATER`, `UNKNOWN`, while documenting under what conditions `UNKNOWN` arises.

`Comparator` must return an `int` and provide a consistent ordering for values in its domain. Therefore, **do not** encode an "unknown" policy as a special numeric return value inside a comparator. If you truly do not want to rank items with missing data, separate or filter them per business policy; if you still want to sort everything, use an explicit `nullsFirst/Last` policy.

Using `Optional<BigDecimal>` as a return value can help distinguish presence vs absence. However, when used in parameters or DTO fields, follow project conventions and document the contract. Do not arbitrarily mix `null`, `Optional.empty()`, and 0 as three ways of expressing the same state.

## 6. Equality with nullable values: choosing the right meaning

There are three ways to define "equal" depending on your intent:

**Option 1 — `equals`, treating both null as the same state:**

```java
boolean sameObjects = Objects.equals(left, right);
```

Returns `true` for `(null, null)`, but `false` for `(1.0, 1.00)` because scales differ.

**Option 2 — numeric equality, only when both are present:**

```java
boolean sameNumericValueIfPresent =
        left != null && right != null && left.compareTo(right) == 0;
```

Two null values return `false` because there are not two numbers to compare. If you need to distinguish "different" from "unknown", use a three-state return type instead of a boolean.

**Option 3 — same nullable state or same numeric value:**

```java
boolean sameNullableAmount =
        left == right
                || (left != null && right != null && left.compareTo(right) == 0);
```

Here both sides being null is treated as equivalent **under the nullable data contract**. That does not claim two unknown numbers are mathematically equal.

| Value pair | `Objects.equals` | Numerically equal when present | Nullable/numeric equivalent |
| --- | --- | --- | --- |
| `null`, `null` | `true` | `false` | `true` |
| `null`, `0` | `false` | `false` | `false` |
| `1.0`, `1.00` | `false` | `true` | `true` |
| `1.0`, `2.0` | `false` | `false` | `false` |

Method names should state their meaning clearly, such as `sameNumericValueIfPresent` or `sameNullableAmount`, rather than an undocumented `isEqual`.

## 7. `TreeSet`, `TreeMap`, `HashSet`, and the scale issue

Because `BigDecimal.compareTo` ignores scale differences when two numbers are equal, its natural ordering is **inconsistent with `equals`**:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.compareTo(b) == 0; // true
a.equals(b);         // false
```

`HashSet` uses `equals`/`hashCode`, so these two objects are treated as two distinct elements. `TreeSet` and `TreeMap` rely on a comparator (or `compareTo` when none is supplied), so they treat two values whose comparison returns 0 as **the same key in sort order**. Only one representative element/key is stored.

`Comparator.nullsFirst/Last(Comparator.naturalOrder())` allows placing `null` in the chosen order, but **does not change** the inconsistency between `BigDecimal.compareTo` and `BigDecimal.equals`.

If you also need to distinguish scale in an ordered collection, you can chain a secondary criterion:

```java
Comparator<BigDecimal> numericThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

Comparator<BigDecimal> nullableNumericThenScale =
        Comparator.nullsLast(numericThenScale);
```

For non-null `BigDecimal` values, this comparator compares numerically first, then by scale. Two `BigDecimal` objects with the same numeric value **and** the same scale are equal under `equals`, so this ordering fits better when scale carries identity meaning. However, if the business treats `1.0` and `1.00` as the same monetary amount, choose a normalization policy or accept that natural ordering treats them as equivalent. Do not change the rule just to force element counts in `HashSet` and `TreeSet` to match.

A `TreeSet` constructed with a null-allowing comparator can hold one null element and order it per policy; a `TreeSet` using natural ordering does not support that. In real-world data, document both the **null rule** and the **duplicate-value rule**.

## 8. Complete Java 17+ program

Save the following code as **`BigDecimalNullComparisonDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalNullComparisonDemo {
    static int compareRequired(BigDecimal left, BigDecimal right) {
        Objects.requireNonNull(left, "left must not be null");
        Objects.requireNonNull(right, "right must not be null");
        return Integer.signum(left.compareTo(right));
    }

    static OptionalInt compareIfPresent(BigDecimal left, BigDecimal right) {
        if (left == null || right == null) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(Integer.signum(left.compareTo(right)));
    }

    static boolean sameNumericValueIfPresent(BigDecimal left, BigDecimal right) {
        return left != null && right != null && left.compareTo(right) == 0;
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("equals = " + a.equals(b));
        System.out.println("Objects.equals(null, null) = " + Objects.equals(null, null));
        System.out.println("sameNumericValueIfPresent = " + sameNumericValueIfPresent(a, b));

        System.out.println("compareRequired = " + compareRequired(a, b));
        System.out.println("compareIfPresent(null, b).isEmpty = "
                + compareIfPresent(null, b).isEmpty());
        try {
            compareRequired(null, b);
        } catch (NullPointerException ex) {
            System.out.println("compareRequired(null, b) = rejected");
        }

        Comparator<BigDecimal> nullsFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        Comparator<BigDecimal> nullsLast =
                Comparator.nullsLast(Comparator.naturalOrder());
        System.out.println("nullsFirst(null, 0) = "
                + Integer.signum(nullsFirst.compare(null, BigDecimal.ZERO)));
        System.out.println("nullsLast(null, 0) = "
                + Integer.signum(nullsLast.compare(null, BigDecimal.ZERO)));

        List<BigDecimal> values = new ArrayList<>(Arrays.asList(
                new BigDecimal("2.0"), null, b, a, null, BigDecimal.ZERO));
        values.sort(nullsLast);
        System.out.println("sorted = " + values);

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> naturalTreeSet = new TreeSet<>(List.of(a, b));
        Comparator<BigDecimal> numericThenScale =
                Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
        Set<BigDecimal> scaleAwareTreeSet = new TreeSet<>(numericThenScale);
        scaleAwareTreeSet.addAll(List.of(a, b));
        System.out.println("set sizes = " + hashSet.size() + "/"
                + naturalTreeSet.size() + "/" + scaleAwareTreeSet.size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BigDecimalNullComparisonDemo.java
java BigDecimalNullComparisonDemo
```

Stdout verified on Java 21; code is Java 17 compatible:

```text
compareTo = 0
equals = false
Objects.equals(null, null) = true
sameNumericValueIfPresent = true
compareRequired = 0
compareIfPresent(null, b).isEmpty = true
compareRequired(null, b) = rejected
nullsFirst(null, 0) = -1
nullsLast(null, 0) = 1
sorted = [0, 1.00, 1.0, 2.0, null, null]
set sizes = 2/1/2
```

The final line shows the sizes of `HashSet`, natural-order `TreeSet`, and scale-aware `TreeSet` respectively. When comparing results, distinguish **same numeric value**, **same representation including scale**, and **adjacent positions in a sorted list**.

## 9. Choosing a contract by scenario

| Scenario | Recommended contract | Reason |
| --- | --- | --- |
| Two amounts required before payment | `Objects.requireNonNull` then `compareTo` | Missing data must be rejected |
| Sorting a list that may have missing prices | `Comparator.nullsLast(Comparator.naturalOrder())` | Every row displays, missing prices at the end |
| Putting missing entries first in a list needing completion | `Comparator.nullsFirst(...)` | Highlights data needing completion |
| Deciding whether a price exceeds a threshold, when threshold is missing | `OptionalInt` or enum with `UNKNOWN` | Avoids drawing false conclusions when data is incomplete |
| Matching decimal values regardless of fractional digit count | Both non-null and `compareTo(...) == 0` | `equals` checks scale |
| Matching data when both null is treated as the same state | Check `left == right` first, then `compareTo` if present | Nullable rule is expressed explicitly |
| Key must distinguish `1.0` and `1.00` | `equals`/`hashCode` or scale-aware comparator | Preserves representational distinction |
| Key only distinguishes numeric value | Ordered set by `compareTo` or predefined normalization | Avoids identity inconsistency |

If an API has multiple callers, document in Javadoc: which arguments are nullable; what `null` means; what is returned when missing; whether comparison is numeric or scale-aware; where null sits if a comparator is used; and which values are considered duplicates if used as keys. Avoid overly generic names like `isEqual` or `compare` when multiple null rules coexist.

## 10. Common mistakes and test suite

Common mistakes:

1. Calling `left.compareTo(right)` without being sure both are non-null.
2. Using `Objects.equals` to check whether two `BigDecimal` objects are numerically equal, forgetting `scale`.
3. Treating `null` as 0 via `Objects.requireNonNullElse(value, BigDecimal.ZERO)` without a business rule.
4. Returning `0` when one side is missing, corrupting the meaning of "compared and equal."
5. Using `Comparator.nullsLast` inside business conditions rather than solely for sorting.
6. Wrapping a comparator for a nullable property while forgetting the parent object holding the property can also be null.
7. Calling `.reversed()` on a null-last comparator and being surprised when nulls appear first.
8. Assuming `TreeSet` will keep two `BigDecimal` values with `equals == false` even though `compareTo == 0`.
9. Converting to `double` before comparing, risking precision loss.
10. Testing only normal value pairs, omitting `null` and differing scales.

A minimal test suite for a nullable API includes `(null, null)`, `(null, 0)`, `(0, null)`, `(0, 0)`, `(1.0, 1.00)`, `(-1, 0)`, `(1, 2)`, and `(2, 1)`. For comparators, also test symmetry, transitivity, and behavior when used to order a `TreeSet`/`TreeMap`.

In short, **`null` represents missing data, `compareTo` is numeric ordering, and `equals` also considers scale**. Those three concerns must be decided separately in the API contract. An API that rejects missing data, an API that sorts with null rules, and an API that allows an "unknown" result address different needs.

Java SE 21 documentation for reference:

- [`BigDecimal`: `compareTo`, `equals`, `min`, `max`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Comparable`: ordering contract and consistency with `equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html)
- [`Comparator`: `nullsFirst`, `nullsLast`, `comparing`, `reversed`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html)
- [`Objects`: `requireNonNull`, `equals`, `compare`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html)
