# Comparing BigDecimal: do not change system-wide equals for a single comparison

## 1. Scenario and principle

In Java, two `BigDecimal` values can be **numerically equal yet unequal under `equals`**:

- `new BigDecimal("2.0")` and `new BigDecimal("2.00")` both represent the number 2, but have `scale()` values of 1 and 2 respectively.
- `a.compareTo(b) == 0` checks whether two numbers are equal **in numeric value**.
- `a.equals(b)` checks for the same **numeric value and scale**. Therefore `a.equals(b)` returns `false` for the pair above.

Problems often arise when a very specific requirement—such as "compare the calculated total with the user-entered total, ignoring trailing zeros"—is handled by **changing the equals rule across the entire model, the whole application, or everywhere BigDecimal is used**. That is far too broad a solution: it can break `hashCode` consistency, collection keys, object identity rules, caches, and persisted data.

**Principle:** place the comparison policy at the exact operation that needs it. Leave existing equality contracts elsewhere intact, unless **the specification of the data type itself** demands a new equality definition and you fully control all consequences.

## 2. Why do equals and compareTo differ?

`BigDecimal` stores an unscaled integer value and a `scale`:

`value = unscaledValue × 10^(-scale)`.

| Representation | `unscaledValue()` | `scale()` | Mathematical value |
|---|---:|---:|---:|
| `2` | 2 | 0 | 2 |
| `2.0` | 20 | 1 | 2 |
| `2.00` | 200 | 2 | 2 |
| `0.00` | 0 | 2 | 0 |

Example:

~~~java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));     // false
System.out.println(x.compareTo(y));  // 0
System.out.println(x.scale());       // 1
System.out.println(y.scale());       // 2
~~~

`compareTo` returns a negative number, 0, or a positive number when the mathematical value of the first operand is less than, equal to, or greater than the second operand, respectively. **Do not check `compareTo(...) == -1` or `== 1`**, because the contract only guarantees the sign of the result. To check numeric equality, use `compareTo(...) == 0`.

`BigDecimal.equals` checks both value and scale; `hashCode` aligns with this interpretation, so two mathematically equal numbers with different scales usually have different hashes. `BigDecimal` is a `final` class: you cannot subclass it to override `BigDecimal.equals` itself. However, you can still accidentally alter the equality of **wrappers, records, or entities**, or force BigDecimal normalization system-wide just to fix one comparison.

Distinguish the contracts:

- **Numeric equality:** `a.compareTo(b) == 0`.
- **BigDecimal representational equality:** `a.equals(b)`.
- **Business equality:** may also require **currency, status, unit, timestamp, identifier**, or other fields. Checking only numeric amount does not necessarily establish that two domain objects are the same.

## 3. Runnable example: impact on HashSet, TreeSet, HashMap, and TreeMap

Save the following program in `BigDecimalEqualityDemo.java` (Java 17+):

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");

        System.out.println("HashMap get(b): " + hashMap.get(b));
        System.out.println("TreeMap get(b): " + treeMap.get(b));
        System.out.println("local numeric equality: "
                + (a.compareTo(b) == 0));
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
~~~

Stdout:

~~~text
equals: false
compareTo: 0
HashSet size: 2
TreeSet size: 1
HashMap get(b): null
TreeMap get(b): first
local numeric equality: true
~~~

**Explanation:**

- `HashSet` and `HashMap` rely on `equals`/`hashCode`. Key `2.0` **differs** from key `2.00` under BigDecimal's rule.
- `TreeSet` and `TreeMap` use natural ordering from `compareTo` (or a provided `Comparator`). `compareTo` treats both representations as the same position in the sorted structure; the second key can be treated as a duplicate of the first.
- Java's own documentation states that `BigDecimal`'s natural ordering is **inconsistent with equals**. `TreeSet` handles these two values according to its ordering rule; do not assume the same definition of "duplicate" across all collections.

Operations relying on `equals`—such as `List.contains`, `List.remove`, `Stream.distinct`, `HashMap.get`, or `Collectors.groupingBy` (with default `HashMap`)—can behave differently from `TreeSet` or `TreeMap`. Choose the structure and comparison function per requirement instead of altering equality system-wide to mask the difference.

## 4. The right approach when you only need a numeric comparison

Suppose you are checking "is the user-submitted value numerically equal to the calculated total?". Whether the user entered `100.0` or `100.00` does not change the validation outcome. Compare directly at the point of check:

~~~java
BigDecimal calculated = new BigDecimal("100.00");
BigDecimal entered = new BigDecimal("100.0");

boolean matches = calculated.compareTo(entered) == 0;
System.out.println(matches); // true
~~~

There is no need to modify the model, `equals`, `hashCode`, or global input normalization rules.

If that operation is used in multiple places with the same meaning, extract it into a specifically named function:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class AmountComparisons {
    private AmountComparisons() {}

    public static boolean sameNumericValue(BigDecimal left, BigDecimal right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) == 0;
    }
}
~~~

This is a **utility class** and does not run standalone because it has no `main`; it can be compiled separately with `javac AmountComparisons.java` or called from other code. The `null`-handling decision is part of the contract: this version rejects `null` so "missing value" is not silently treated as 0. If you need `null == null` in the sense of "both absent", build a separate function with a clear name and tests. Do not use `Objects.equals(left, right)` as a silent substitute, because it falls back to `BigDecimal.equals`.

**Limitation of this function:** it only compares two numbers. For money, you must verify the currency unit. `100 USD` is not equivalent to `100 EUR` merely because both amounts equal 100.

### Do not use ==, toString, or convert to double

- `a == b` only checks **the same `BigDecimal` object reference**, not value.
- `a.toString().equals(b.toString())` compares representation strings, unsuitable for numeric equality.
- `a.doubleValue() == b.doubleValue()` can lose precision or overflow to infinity, causing genuinely different `BigDecimal` values to be treated as equal.
- `a.subtract(b).abs().compareTo(epsilon) <= 0` is **comparison with tolerance**, a different specification, not BigDecimal equality. Tolerance requires explicit units and a clear business/technical justification.

## 5. Why should you not override equals on a wrapper or entity to fix one need?

Consider a model with stable identity:

~~~java
record InvoiceLine(String lineId, BigDecimal amount) {}
~~~

This is a Java 17 record; equality is auto-generated from **both** `lineId` and `amount`, where `amount` uses `BigDecimal.equals`. If one screen needs to compare **amounts ignoring scale**, do not rush to override `InvoiceLine.equals` just for that screen. Doing so changes the meaning of "two invoice lines are equal" across the entire program, even though two lines can still have different IDs, tax rates, or business transactions.

Common consequences of changing equality globally:

1. **Hash contract:** if `equals` changes, `hashCode` must change to match; any objects considered equal must have the same hash. Changing only one method breaks the contract.
2. **Data used as keys:** `HashSet`/`HashMap` can lose the ability to locate keys or change duplicate logic. If equality or fields participating in hashing change **after inserting a key into a HashMap**, lookups can fail.
3. **Caches, grouping, and distinct:** objects previously considered distinct are now merged, losing results or producing wrong element counts.
4. **Identity and persistence:** entities have their own identity/lifecycle rules; changing equals merely because of an amount's scale can affect handling of transient entities without IDs, persisted entities, relationship collections, or caching. Exact behavior depends on the technology; evaluate against the entity contract.
5. **APIs and tests:** equality is a contract many places rely on. Altering it can cause regressions even though the first comparison now "passes."

Conversely, there are **value objects designed from the start** with equality based on a normalized value; that is a *value-type* decision and can be valid. However, it requires a clear specification, synchronized `equals`/`hashCode`, defined canonicalization, and tests everywhere it is used. Do not impose that rule on every class because of a single screen.

## 6. When does normalizing make sense? When does it cause trouble?

Two common techniques:

### 6.1. Removing trailing zeros with stripTrailingZeros

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.stripTrailingZeros().equals(b.stripTrailingZeros())); // true
System.out.println(new BigDecimal("1000.00").stripTrailingZeros());        // 1E+3
~~~

`stripTrailingZeros()` returns another `BigDecimal` that may have a **negative scale** and scientific notation (`1E+3`), especially when the number is a power of 10. The result may suit a **dedicated canonical key** but is not automatically suitable for formatting, serialization, validation, or accounting reports that need to show scale. If the goal is merely checking whether two numbers are equal, `compareTo(...) == 0` is clearer and avoids transforming data.

A value `0.00` after stripping trailing zeros can become zero with scale 0; this further underscores that normalization can erase original representation details.

### 6.2. Fixing scale when the data type *truly* has a scale invariant

For example, an internal monetary type **clearly defined** as always having two decimal places, where inputs must not be rounded silently:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record FixedTwoDecimalAmount(BigDecimal value) {
    public FixedTwoDecimalAmount {
        Objects.requireNonNull(value, "value");
        value = value.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

This is a **value object for a domain with a fixed scale**, not a policy for every currency. The Java record generates `equals`/`hashCode` from the `value` component **after normalizing in the constructor**. As a result, `new FixedTwoDecimalAmount(new BigDecimal("2.0"))` and the `2.00` version are equal; input `2.001` throws `ArithmeticException` because it requires rounding, which the policy forbids.

Do not arbitrarily use `setScale(2, HALF_UP)` in a constructor, as it silently alters input values. If accepting and rounding is required, make that an explicit rule in the specification and factory method name. Different currencies can use decimal place counts other than 2; do not infer an invariant from display habits.

### Deciding where to place normalization

If you **only need a one-time comparison**, call `compareTo` directly in the business logic. If a data type has a stable scale invariant, normalize at the creation boundary of **that type** after domain agreement. If hash-key data requires canonicalization, normalize **when constructing the key** and do not mutate keys after inserting into a map/set. Do not "clean up trailing zeros" on reads/writes system-wide just to make an incidental `equals` call return true.

## 7. Collections, comparators, and consistency with equals

`Comparator<BigDecimal> numericOrder = BigDecimal::compareTo;` can be used explicitly when a collection needs **numeric ordering**. In a sorted collection, a comparator returning 0 causes two elements to be treated as the same key, even when `equals` returns false.

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

Comparator<BigDecimal> numericOrder = BigDecimal::compareTo;
Set<BigDecimal> uniqueNumericValues = new TreeSet<>(numericOrder);
uniqueNumericValues.add(new BigDecimal("2.0"));
uniqueNumericValues.add(new BigDecimal("2.00"));
System.out.println(uniqueNumericValues.size()); // 1
~~~

This is an **illustrative snippet placed inside a method body** (not a standalone program); all imports used are declared. Note that `TreeSet` and `TreeMap` drop/merge elements when the comparator returns 0. If keeping multiple representations for reporting or auditing, using this comparator to "deduplicate" can lose data. If you need to keep both while sorting by value, use an appropriate collection or a comparator with a **scale tie-breaker** to distinguish representations—choosing based on the desired semantics.

Do not convert an entire collection to `TreeSet` merely to work around equality at one step. When keeping `HashMap`, you can use a documented local normalized key; pay attention to original values, scale, null, currency, and hashing/serialization. Do not overuse `stripTrailingZeros` when `compareTo == 0` solves the need directly.

### Distinguishing equality from "approximately equal"

Consider a tolerance of 0.10: `0.00` is close to `0.09`, `0.09` is close to `0.18`, yet `0.00` is not close to `0.18`. This kind of near-equality relation is **not transitive**, so it is unsuitable as `equals` or as a comparator used by a sorted collection to define key equivalence. If a problem needs to allow deviation, write a local predicate with a specific threshold rather than changing equality or blindly passing an approximate comparator to `TreeSet`/`TreeMap`.

## 8. How to decide by scenario

| Requirement | Appropriate approach | What to avoid |
|---|---|---|
| Check whether two BigDecimals are numerically equal | `a.compareTo(b) == 0` at the check site | Overriding model equals for one `if` statement |
| Check exact scale/representation as original data | `a.equals(b)` or check both value and `scale()` | Using compareTo and ignoring scale requirements |
| Check transaction amount | Check currency, amount, and related business rules | Comparing only amount and treating two transactions as identical |
| Sort by numeric value | `Comparator<BigDecimal>` or `compareTo` | Assuming comparator agrees with equals |
| Deduplicate numerically for a report | Use a dedicated canonical structure/key with documented duplicate semantics | Normalizing the entire database or model |
| Scale-invariant amount type | Fix scale when creating the value object per domain contract | Scattering `setScale` everywhere |
| Check deviation within tolerance | Predicate `abs(a-b) <= tolerance`, specifying units | Using approximate relation as equals/hash/comparator |
| Entity needing identity comparison | Rely on entity identity contract, considering lifecycle | Using amount comparison in place of entity identity |

These choices are semantically **independent**. A system can simultaneously use `equals` for identity keys, `compareTo` for reconciliation, a comparator for display order, and a canonical value object for a specific domain flow.

## 9. Designing tests to guard both intended behavior and side effects

In a unit performing numeric reconciliation, test both directions:

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

if (a.compareTo(b) != 0) {
    throw new AssertionError("Numeric value should match");
}
if (a.equals(b)) {
    throw new AssertionError("BigDecimal representation unexpectedly matched");
}
~~~

This snippet is **assertion code placed inside a method**, without `main`; integrate it into an appropriate unit test.

Additional test cases:

1. **Different-scale pairs:** `2.0` and `2.00` are numerically equal yet differ in `equals`; `2.00` and `2.01` must be numerically different.
2. **Negatives and zero:** `-0.00` and `0.0` are numerically equal; scale comparison still differs. `-2.0` and `-2.00` are also equal under `compareTo`.
3. **Nulls:** define whether to throw, treat as absent, or skip comparison. Never let null be mistaken for zero.
4. **Model hash contract:** if designing a new type with custom equality, verify reflexivity, symmetry, transitivity, consistency, and `equals ⇒ same hashCode`; test `HashSet` and `HashMap` operations.
5. **Comparator-backed collections:** test element counts, `contains`, and put/get when `compareTo` matches while `equals` does not; verify whether the system truly intends to drop duplicate representations.
6. **Multi-currency transactions:** amounts with the same number but different currencies must not be considered the same monetary value in the domain.
7. **Regression:** when changing only one comparison, verify that equality/identity in caches, mappings, and remaining flows still follow existing contracts.

When you need a dedicated comparison function, choose a name reflecting **business meaning**, such as `sameNumericTotal` or `matchesEnteredAmount`; avoid a vague general helper like `isEqual` that ends up misused in every context.

## 10. Common mistakes

- **"equals is wrong so fix it":** usually you just need numeric equality at one spot, while `BigDecimal.equals` is fulfilling its own contract properly.
- **Overriding equals on an entity to make one amount comparison true:** changes the definition of "same entity" across the whole application.
- **Changing equals while forgetting hashCode:** breaks collection contracts and causes hard-to-reproduce bugs.
- **Using BigDecimal as a mutable key:** `BigDecimal` is immutable, but a **wrapper holding the key or fields participating in equality/hash** can be mutated after insertion; that is the real risk.
- **Replacing HashSet with TreeSet assuming equivalent behavior:** BigDecimal's natural ordering is inconsistent with equals, leading to different element/key counts.
- **Normalizing with stripTrailingZeros at every layer:** can change scale and display strings, such as `1000.00 → 1E+3`.
- **Using only compareTo while ignoring currency:** amount equality does not imply monetary equality.
- **Using double for comparisons:** can lose exact information preserved by BigDecimal.
- **Using tolerance as equality:** approximate equality may not be transitive; unsuitable as a set/map contract.
- **Using equals to check "paid in full" when users enter differing scales:** choosing `compareTo == 0` allows reconciliation specified as numeric equality.

## 11. Reinforcement exercises

**Exercise 1.** For `new BigDecimal("0.00")` and `BigDecimal.ZERO`, predict `equals`, `compareTo`, and the element counts of `HashSet`/`TreeSet` after adding both. Explain based on scale.

**Exercise 2.** An API receives item quantity `"5.0"`, while calculated data is `"5"`. Business logic only needs to check equal quantity. Choose the comparison and null handling; should the DTO's `equals` be changed?

**Exercise 3.** A transaction history screen must preserve both the raw entered number and the formatted number. If `stripTrailingZeros` is applied right when reading from the database, what information could be lost?

**Exercise 4.** Write a test proving that "absolute difference at most 0.10" is not transitive for `0.00`, `0.09`, `0.18`. Why should that relation not be used as a `TreeSet` `Comparator`?

**Answer hints:** (1) `equals=false`, `compareTo=0`, HashSet has 2, TreeSet has 1. (2) use `compareTo == 0` in a validator with explicit null handling; no need to change DTO `equals`. (3) scale and trailing-zero representation, or even scientific notation. (4) A is close to B, B is close to C, yet A is not close to C; non-transitivity breaks total-order assumptions when sorted collections group keys.

## Standard documentation

- Java SE 17 — `BigDecimal` (`equals`, `compareTo`, `hashCode`, `stripTrailingZeros`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17 — `Comparable`, "consistent with equals" rule: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html
- Java SE 17 — `TreeSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html
- Java SE 17 — `Object.equals` and `hashCode`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html

**Key takeaway:** a need to compare by *numeric value* should be expressed directly with `compareTo(...) == 0` right where it is needed. Changing `equals` on a model or value object is only justified when **the entire definition of that type** genuinely requires it and `hashCode`, collection, identity, and data contracts have all been thoroughly accounted for.
