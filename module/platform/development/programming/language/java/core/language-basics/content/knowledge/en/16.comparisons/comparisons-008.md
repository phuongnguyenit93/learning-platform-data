# Writing Clear Range Validation Conditions — Java 17+

## 1. Objective

**Range validation** determines whether a value belongs to the set of permitted values: age from 18 to 65, array index from 0 to `length - 1`, ratio between 0 and 1, a value excluded from a forbidden zone, and so on.

In Java, a correct condition does not just specify the **lower and upper bounds**; it must also define:

- Are the two bounds **inclusive or exclusive**?
- Are **negative numbers**, zero, and extreme values accepted?
- Are the two conditions joined with **`&&` (and)** or **`||` (or)**?
- Does the value come from `int`/`long`, `float`/`double`, a nullable wrapper, or a decimal type?
- If the bounds are misconfigured (`min > max`), should it throw an error or return false?

A readable, semantically sound expression:

~~~java
int age = 20;
boolean validAge = (age >= 18) && (age <= 65);

System.out.println(validAge); // true
~~~

This is the **closed interval** `[18, 65]`: both 18 and 65 are included. Putting parentheses around each comparison clarifies the two conditions; for short expressions, `age >= 18 && age <= 65` is also fine.

## 2. Translating Requirements into Mathematical Intervals and Java Conditions

| Meaning | Mathematical notation | Java condition |
|---|---|---|
| From `min` to `max`, including both bounds | `[min, max]` | `value >= min && value <= max` |
| Between, excluding both bounds | `(min, max)` | `value > min && value < max` |
| Including lower bound, excluding upper bound | `[min, max)` | `value >= min && value < max` |
| Excluding lower bound, including upper bound | `(min, max]` | `value > min && value <= max` |
| Less than `min` or greater than `max` | Outside `[min, max]` | `value < min || value > max` |
| Not less than `min` | `[min, +∞)` | `value >= min` |
| Less than `max` | `(-∞, max)` | `value < max` |
| Equal to a boundary value | `value = min` | `value == min` |

**Choose `<` or `<=` from the requirements, not arbitrarily.** For example, an index into an array of `length` elements must belong to **`[0, length)`**, because position `length` does not exist:

~~~java
int[] numbers = {10, 20, 30};
int index = 2;
boolean validIndex = index >= 0 && index < numbers.length;
System.out.println(validIndex); // true
~~~

If `index == numbers.length`, the condition returns false. Before indexing an array, you must still check that the array reference is not null if the input could be missing.

## 3. Java Does Not Support Mathematical Chained Comparisons

In mathematics you can write:

~~~text
18 <= age <= 65
~~~

However, Java **does not** allow:

~~~java
// 18 <= age <= 65 // COMPILATION ERROR
~~~

The expression `18 <= age` produces a `boolean`, which cannot then be used in `<= 65` between a boolean and an int.

Write two complete comparisons:

~~~java
boolean valid = (age >= 18) && (age <= 65);
~~~

Do **not** use `||` when you want the value to lie within both bounds:

~~~java
int age = 100;
boolean wrong = (age >= 18) || (age <= 65);
System.out.println(wrong); // true: semantically wrong condition
~~~

With `min <= max`, `value >= min || value <= max` is almost always true for integers: it asks **"satisfies at least one side"**, not "is in between".

## 4. Checking Outside a Range: Use `||`, Not `&&`

If the valid domain is `[min, max]`, an integer lies **outside the range** when:

~~~java
boolean outside = (value < min) || (value > max);
~~~

An integer cannot simultaneously be less than `min` **and** greater than `max` when `min <= max`, so avoid writing:

~~~java
// value < min && value > max // Wrong when checking outside range
~~~

Equivalent condition pairs on integers when the bounds are valid:

| Intent | Expression |
|---|---|
| Inside closed interval | `value >= min && value <= max` |
| Outside closed interval | `value < min || value > max` |
| Negated inside-range condition | `!(value >= min && value <= max)` |
| Inside open interval | `value > min && value < max` |
| Outside open interval | `value <= min || value >= max` |

This applies **De Morgan's law**: `!(A && B)` is equivalent to `!A || !B`. For complex conditions, give intermediate booleans clear names:

~~~java
boolean inside = (value >= min) && (value <= max);
boolean rejected = !inside;
~~~

**Note on `double` and `NaN`:** `value < min || value > max` **does not catch NaN**, because both comparisons return false when `value` is NaN. Dedicated handling is covered in the floating-point section.

## 5. `&&`, `||`, Parentheses, and Short-Circuiting

`&&` has higher precedence than `||`. When combining multiple groups, add parentheses according to the **business rules**:

~~~java
boolean adult = true;
boolean verified = false;
boolean admin = true;

boolean ruleA = adult && (verified || admin);
boolean ruleB = (adult && verified) || admin;

System.out.println(ruleA); // true
System.out.println(ruleB); // true
~~~

With the inputs above, both evaluate to true; however, that **does not mean** they are always equivalent. Consider `adult = false`, `verified = false`, `admin = true`: `ruleA` is false while `ruleB` is true. If the age requirement is mandatory for everyone, only `adult && (verified || admin)` reflects the requirement accurately.

The `&&` and `||` operators use **short-circuit evaluation**:

~~~java
Integer age = null;
boolean validAge = (age != null) && (age >= 18) && (age <= 65);
System.out.println(validAge); // false, does not unbox null
~~~

If `age == null`, the remaining parts do not execute, avoiding `NullPointerException`. Do not replace `&&` with `&` when the goal is to skip subsequent checks if an earlier condition fails.

## 6. Validate Boundary Configuration Before Use

A range `[min, max]` is only valid if `min <= max`. If an API receives inverted bounds:

~~~java
int min = 100;
int max = 50;
~~~

then `value >= min && value <= max` returns false for every `int`, **hiding a configuration bug**.

Create a function with an explicit contract:

~~~java
static boolean inClosedRange(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return value >= min && value <= max;
}
~~~

**Two distinct design choices:**

1. **Invalid bounds are a configuration error:** throw `IllegalArgumentException`.
2. **An empty range is an intentional state:** returning false can be acceptable, provided it is clearly documented in the contract.

This lesson chooses the first option. For `[min, max)`, if `min == max`, the interval is empty by definition and is not necessarily an error — decide based on your API design. In the complete Java example below, the half-open interval allows equal bounds and always returns false.

## 7. Do Not Validate Integer Ranges with Overflow-Prone Subtraction

You may come across this pattern:

~~~java
// AVOID:
// value - min >= 0 && max - value >= 0
~~~

With `int`, subtraction can **overflow** before the comparison happens. For example:

~~~java
int value = Integer.MAX_VALUE;
int min = -1;

System.out.println(value - min); // -2147483648: int overflow
~~~

By contrast, direct comparison:

~~~java
boolean atLeastMin = value >= min;
System.out.println(atLeastMin); // true
~~~

is correct across the entire integer range without risking subtraction overflow.

**Use direct comparisons** for range checks; if you genuinely need the interval width, widen types **before subtracting**:

~~~java
long width = (long) max - (long) min;
~~~

Do not assign an already-overflowed `int` subtraction result to a `long` expecting the number to fix itself.

## 8. Floating-Point: `NaN`, Infinity, and Valid Range Choices

For `double`:

~~~java
double value = Double.NaN;

boolean inside = value >= 0.0 && value <= 1.0;
boolean naivelyOutside = value < 0.0 || value > 1.0;

System.out.println(inside);         // false
System.out.println(naivelyOutside); // false
~~~

Both return false because any ordering comparison (`<`, `<=`, `>`, `>=`) with a NaN operand returns false. If you only check `outside` and assume `!outside` means valid, NaN **can slip through**.

If the valid domain allows **only finite numbers**, use:

~~~java
static boolean inFiniteClosedRange(
        double value, double min, double max) {
    if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
        throw new IllegalArgumentException("invalid floating bounds");
    }
    return Double.isFinite(value) && value >= min && value <= max;
}
~~~

Here:

- `min` and `max` must be finite and properly ordered.
- `value` being `NaN` or Infinity -> false.
- Both `+0.0` and `-0.0` satisfy a closed range containing 0.
- The comparisons test the exact **represented `double` values**.

**Floating-point boundaries need explicit specification**: `0.1 + 0.2` in double yields `0.30000000000000004`, so `value <= 0.3` returns false. Do not widen bounds arbitrarily just to make results look "nice" when the business requires a strict boundary. For measured data with real-world tolerance, define and verify an appropriate **error-margin policy**; for decimal values requiring exactness, consider `BigDecimal`.

## 9. `BigDecimal`: Range Validation on Exact Decimal Values

For monetary amounts or ratios requiring exact decimal comparison, use `BigDecimal.compareTo`:

~~~java
java.math.BigDecimal rate = new java.math.BigDecimal("0.30");
java.math.BigDecimal min = new java.math.BigDecimal("0.00");
java.math.BigDecimal max = new java.math.BigDecimal("1.00");

boolean valid = rate.compareTo(min) >= 0 && rate.compareTo(max) <= 0;
System.out.println(valid); // true
~~~

`compareTo` compares **numeric values** without requiring identical scales. For example, `new BigDecimal("1.0")` and `new BigDecimal("1.00")` yield `compareTo == 0`, whereas `equals` returns false because their scales differ.

**Do not construct `BigDecimal` from `new BigDecimal(0.1)` if you want the exact decimal value 0.1**. Construct from the string `"0.1"` or follow a specified conversion path, and standardize units/rounding according to business rules.

## 10. Valid Domains with Multiple Intervals or Forbidden Zones

For example, permitting scores within **`[1, 5]` or `[10, 12]`**:

~~~java
boolean allowed =
        (score >= 1 && score <= 5)
        || (score >= 10 && score <= 12);
~~~

Parentheses show that the two intervals are **joined with OR**. Using helper methods:

~~~java
boolean allowed =
        inClosedRange(score, 1, 5)
        || inClosedRange(score, 10, 12);
~~~

For example, accepting `[1, 10]` while **excluding `[4, 6]`**:

~~~java
boolean allowed = inClosedRange(score, 1, 10)
        && !inClosedRange(score, 4, 6);
~~~

**Verify boundary semantics:** if `score = 4` or 6, the closed exclusion condition returns true and the entire expression returns false. If you only want to forbid `(4, 6)`, use `>` and `<` instead of `>=` and `<=`.

## 11. Guard Clauses: Separating Validation from Processing

Instead of burying conditions inside deeply nested branches, a method can reject out-of-range inputs up front:

~~~java
static int requireAge(int age) {
    if (!inClosedRange(age, 18, 65)) {
        throw new IllegalArgumentException("age out of range");
    }
    return age;
}
~~~

This approach ensures:

- Range bounds are checked in **one clear location**.
- Core processing runs only after inputs are validated.
- Writing tests for the **lower bound, upper bound, and values adjacent to both sides** is easier.
- **Invalid argument errors** are clearly separated from valid results like `0` or `false`.

For user-input applications, you can return a validation result object instead of throwing an exception; that is an API-interface choice and does not change the underlying comparison operators.

~~~mermaid
flowchart TD
    A["Receive value, min, max"] --> B{"Valid bounds?"}
    B -- "No" --> C["Report configuration/input error"]
    B -- "Yes" --> D{"Floating-point? Require finite?"}
    D -- "Yes" --> E{"Finite value?"}
    E -- "No" --> F["Reject value"]
    E -- "Yes" --> G{"Satisfies both boundary conditions?"}
    D -- "No" --> G
    G -- "Yes" --> H["Valid"]
    G -- "No" --> F
~~~

## 12. Essential Boundary Test Table

For the closed interval **`[10, 20]`**:

| Value | Expected result | Reason |
|---:|---|---|
| `9` | false | Just below lower bound |
| `10` | true | Equals lower bound |
| `11` | true | Inside range |
| `20` | true | Equals upper bound |
| `21` | false | Just above upper bound |

For the half-open index interval **`[0, 3)`**:

| Value | Expected result |
|---:|---|
| `-1` | false |
| `0` | true |
| `2` | true |
| `3` | false |

Beyond ordinary values, also test:

- `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, and values near them.
- `min == max` and `min > max` per the function contract.
- `null` for wrapper or object inputs.
- `Double.NaN`, both signs of Infinity, and signed zeros when using floating-point.
- Values very close to floating-point boundaries due to rounding.
- Composite ranges joined with `||` or excluded with `!`.

## 13. Complete Java 17 Program — Runnable via CLI

Create the exact file **`RangeConditionDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class RangeConditionDemo {
    private RangeConditionDemo() {}

    static boolean inClosedRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value >= min && value <= max;
    }

    static boolean inOpenRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value > min && value < max;
    }

    static boolean inHalfOpenRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value >= min && value < max;
    }

    static boolean inFiniteClosedRange(
            double value, double min, double max) {
        if (!Double.isFinite(min) || !Double.isFinite(max)
                || min > max) {
            throw new IllegalArgumentException("invalid floating bounds");
        }
        return Double.isFinite(value)
                && value >= min && value <= max;
    }

    static int requireAge(int age) {
        if (!inClosedRange(age, 18, 65)) {
            throw new IllegalArgumentException("age out of range");
        }
        return age;
    }

    public static void main(String[] args) {
        System.out.println("closed lower="
                + inClosedRange(10, 10, 20));
        System.out.println("closed upper="
                + inClosedRange(20, 10, 20));
        System.out.println("closed below="
                + inClosedRange(9, 10, 20));
        System.out.println("closed above="
                + inClosedRange(21, 10, 20));

        System.out.println("open lower="
                + inOpenRange(10, 10, 20));
        System.out.println("open middle="
                + inOpenRange(15, 10, 20));
        System.out.println("half open start="
                + inHalfOpenRange(0, 0, 3));
        System.out.println("half open end="
                + inHalfOpenRange(3, 0, 3));
        System.out.println("half open empty="
                + inHalfOpenRange(3, 3, 3));

        int score = 4;
        boolean union = inClosedRange(score, 1, 5)
                || inClosedRange(score, 10, 12);
        System.out.println("union accepted=" + union);

        score = 7;
        boolean gap = inClosedRange(score, 1, 5)
                || inClosedRange(score, 10, 12);
        System.out.println("union gap=" + gap);

        boolean excluded = inClosedRange(score, 1, 10)
                && !inClosedRange(score, 4, 6);
        System.out.println("exclude forbidden=" + excluded);
        System.out.println("negative accepted="
                + inClosedRange(-2, -5, 0));
        System.out.println("near int max="
                + inClosedRange(Integer.MAX_VALUE,
                        Integer.MAX_VALUE - 1, Integer.MAX_VALUE));

        int value = Integer.MAX_VALUE;
        int min = -1;
        System.out.println("unsafe subtraction=" + (value - min));
        System.out.println("direct comparison=" + (value >= min));

        double computed = 0.1 + 0.2;
        System.out.println("floating upper strict="
                + inFiniteClosedRange(computed, 0.0, 0.3));
        System.out.println("floating inside="
                + inFiniteClosedRange(computed, 0.0, 0.4));
        System.out.println("NaN accepted="
                + inFiniteClosedRange(Double.NaN, 0.0, 1.0));
        System.out.println("Infinity accepted="
                + inFiniteClosedRange(Double.POSITIVE_INFINITY, 0.0, 1.0));
        System.out.println("negative zero accepted="
                + inFiniteClosedRange(-0.0, 0.0, 1.0));

        double nan = Double.NaN;
        System.out.println("naive NaN outside="
                + (nan < 0.0 || nan > 1.0));
        System.out.println("validated NaN invalid="
                + !inFiniteClosedRange(nan, 0.0, 1.0));

        BigDecimal rate = new BigDecimal("0.30");
        BigDecimal low = new BigDecimal("0.00");
        BigDecimal high = new BigDecimal("1.00");
        boolean validDecimal = rate.compareTo(low) >= 0
                && rate.compareTo(high) <= 0;
        System.out.println("decimal within=" + validDecimal);

        Integer nullableAge = null;
        boolean validNullableAge = nullableAge != null
                && inClosedRange(nullableAge, 18, 65);
        System.out.println("nullable age=" + validNullableAge);

        int denominator = 0;
        boolean guarded = denominator != 0
                && 10 / denominator > 1;
        System.out.println("short circuit guard=" + guarded);

        System.out.println("age valid=" + requireAge(20));
        try {
            requireAge(17);
        } catch (IllegalArgumentException ex) {
            System.out.println("age invalid=" + ex.getMessage());
        }
        try {
            inClosedRange(10, 20, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad integer bounds=" + ex.getMessage());
        }
        try {
            inFiniteClosedRange(0.5, 1.0, 0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad floating bounds=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later, terminal opened in the directory containing the file; no Maven, Gradle, or external libraries beyond the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RangeConditionDemo.java
java -cp . RangeConditionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RangeConditionDemo.java
java -cp . RangeConditionDemo
~~~

**Exact expected stdout:**

~~~text
closed lower=true
closed upper=true
closed below=false
closed above=false
open lower=false
open middle=true
half open start=true
half open end=false
half open empty=false
union accepted=true
union gap=false
exclude forbidden=true
negative accepted=true
near int max=true
unsafe subtraction=-2147483648
direct comparison=true
floating upper strict=false
floating inside=true
NaN accepted=false
Infinity accepted=false
negative zero accepted=true
naive NaN outside=false
validated NaN invalid=true
decimal within=true
nullable age=false
short circuit guard=false
age valid=20
age invalid=age out of range
bad integer bounds=min > max
bad floating bounds=invalid floating bounds
~~~

### Explanation of Output Groups

1. **Closed/open/half-open intervals:** `[10,20]` includes both 10 and 20, `(10,20)` excludes 10, `[0,3)` includes 0 and excludes 3.
2. **Multiple intervals and forbidden zones:** `||` expresses the union of two intervals, while `&& !(...)` excludes a sub-interval.
3. **Negative numbers and large bounds:** direct comparison remains accurate; `value-min` on `int` can overflow and produce the wrong value.
4. **Floating-point:** `0.1 + 0.2` is slightly above literal `0.3`; the finite-only function rejects NaN and Infinity.
5. **NaN:** both `nan < min` and `nan > max` are false; an explicit finiteness check policy is required first.
6. **Decimal:** `BigDecimal.compareTo` checks exact decimal values.
7. **Wrappers and short-circuiting:** `null` and zero-denominator guards prevent dangerous operations on the right-hand side.
8. **Guard clauses:** return valid values or throw exceptions with clear messages when values or bounds are invalid.

## 14. Common Mistakes and Fixes

| Mistake or misconception | Problem | Correct approach |
|---|---|---|
| `min <= x <= max` | Java has no chained comparisons | `x >= min && x <= max` |
| `x >= min || x <= max` to check inside range | `||` only requires one side true | Use `&&` |
| `x < min && x > max` to check outside range | Cannot both be true when `min <= max` | Use `||` |
| Using `<= length` for array index | Accessing index equal to length goes out of bounds | Use `index < length` |
| Forgetting to check lower and upper bounds | Off-by-one bugs | Test right around both bounds |
| Failing to check `min > max` | Misconfiguration silently becomes false | Validate bounds |
| `x - min >= 0` instead of `x >= min` | Integer subtraction can overflow | Compare directly |
| `!(x < min || x > max)` to validate double without checking NaN | NaN makes both comparisons false, negation returns true | `Double.isFinite(x)` plus range check |
| Treating Infinity as valid measured data | Infinity is not finite | Clear acceptance policy |
| Using double bound 0.3 expecting values near 0.3 to pass | Binary rounding error | Well-founded tolerance or `BigDecimal` |
| Using `BigDecimal.equals` to compare decimal values across scales | `equals` also checks scale | `compareTo` |
| Using `&` instead of `&&` to guard against null | `&` evaluates both sides | `&&` |
| Combining multiple `&&`/`||` groups without parentheses | Easy to misread logic | Parenthesize per business rules |
| Truncating `double` to `int` before checking range | Drops fractional part, may falsely accept | Validate in the right type before converting |

## 15. Exercises with Answers

### Exercise A — Closed Interval

Check that `score` is from 0 to 100, **inclusive**.

~~~java
boolean valid = score >= 0 && score <= 100;
~~~

**Answer:** for `score = 0` or `100`, true; for `-1` or `101`, false.

### Exercise B — Array Index

An array has `length = 5`. Write the condition for a valid index.

~~~java
boolean validIndex = index >= 0 && index < 5;
~~~

**Answer:** `0..4` are valid; `-1` and `5` are invalid.

### Exercise C — Outside Range

Write a condition to reject ages **outside `[18,65]`**.

~~~java
boolean rejected = age < 18 || age > 65;
~~~

**Answer:** for age 17 or 66, true; for age 18 or 65, false.

### Exercise D — Empty Interval

~~~java
System.out.println(inHalfOpenRange(5, 5, 5));
~~~

**Answer:** `false`, because `[5,5)` is empty. The example function allows `min == max` for half-open intervals.

### Exercise E — NaN

~~~java
double x = Double.NaN;
boolean outside = x < 0 || x > 1;
System.out.println(outside);
~~~

**Answer:** `false`, which **does not mean `x` is valid**. You must explicitly reject NaN using `Double.isFinite(x)` or `Double.isNaN(x)` according to policy.

### Exercise F — Two Permitted Ranges

Accept `x` in `[1,3]` **or** `[7,9]`.

~~~java
boolean accepted =
        (x >= 1 && x <= 3)
        || (x >= 7 && x <= 9);
~~~

**Answer:** 1, 3, 7, and 9 are accepted; 4, 5, and 6 are rejected.

### Exercise G — Overflow Bug in Range Check

~~~java
int value = Integer.MAX_VALUE;
int min = -1;
System.out.println(value - min >= 0);
System.out.println(value >= min);
~~~

**Answer:**

~~~text
false
true
~~~

The first line overflows during `int` subtraction; the second uses direct comparison and is accurate.

## 16. Checklist and Conclusion

- [ ] Clearly choose closed, open, or half-open intervals and boundary semantics.
- [ ] Use `&&` to require meeting both lower and upper bounds simultaneously.
- [ ] Use `||` to detect out-of-range values or unions of multiple ranges.
- [ ] Never write `min <= value <= max` in Java.
- [ ] Validate `min <= max` per the API contract.
- [ ] Test `min - 1`, `min`, inside range, `max`, and `max + 1` where it does not overflow.
- [ ] For array indices, use `[0,length)`.
- [ ] Avoid integer range checks that use overflow-prone subtraction.
- [ ] For `double`, define explicit policies for NaN, Infinity, and boundary precision errors.
- [ ] Do not use arbitrary tolerance to bypass safety constraints.
- [ ] For exact decimals, consider `BigDecimal.compareTo`.
- [ ] Use `null` guards with wrappers and `&&` to avoid null unboxing.
- [ ] Use parentheses so readers can clearly recognize business condition groups.
- [ ] Run `RangeConditionDemo.java` with Java 17+ and verify every line of expected output.

**Conclusion:** A solid range validation condition must **accurately express the permitted set of values**, handle both boundaries clearly, use `&&`/`||` properly, avoid overflow, and define policies for anomalous floating-point data. Name important conditions, validate bounds, and test right at the boundaries so Java 17+ code stays readable, maintainable, and free from false acceptances.
