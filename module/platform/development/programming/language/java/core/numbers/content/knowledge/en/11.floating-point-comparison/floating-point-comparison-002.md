# NaN Is Not Equal to Itself in Java Primitive Comparisons

When comparing primitive floating-point numbers `float` and `double`, the expression `x == x` is **not always `true`**. If `x` is **NaN (Not a Number)**, Java returns `false` for equality comparison, even when both sides are the exact same variable. Conversely, `x != x` returns `true`. This is an intentional rule of IEEE 754 floating-point numbers adopted by Java, not a bug in the `==` operator.

~~~java
double x = Double.NaN;

System.out.println(x == x);         // false
System.out.println(x != x);         // true
System.out.println(x == Double.NaN); // false
System.out.println(Double.isNaN(x)); // true
~~~

This is an illustrative code snippet that must be placed inside a Java method. In real programs, **you should use `Double.isNaN(x)` or `Float.isNaN(x)`** to explicitly detect NaN, instead of relying on the `x != x` trick.

This lesson belongs to the **floating-point comparison** topic: focusing on primitive comparison operators, error-prone conditions when NaN is present, and why wrapper class results can differ.

## 1. What Is NaN and Where Does It Come From?

`float` (32-bit) and `double` (64-bit) are Java's floating-point number types. In addition to finite values, they have special values such as **positive infinity**, **negative infinity**, and **NaN**. NaN represents a result that is not a normal numeric value capable of being ordered arithmetically.

Valid examples that produce NaN in Java:

~~~java
double a = 0.0 / 0.0;               // NaN
double b = Double.POSITIVE_INFINITY
         - Double.POSITIVE_INFINITY; // NaN
double c = Math.sqrt(-1.0);        // NaN
float d = Float.NaN;                // NaN
~~~

Note the difference between integer division and floating-point division:

- `0.0 / 0.0` is `double` division, producing NaN without throwing `ArithmeticException`.
- Integer division by 0 throws `ArithmeticException` when executed, including expressions like `1 / 0`. Do not confuse this with floating-point `0.0 / 0.0`, which produces NaN.
- `1.0 / 0.0` yields positive infinity, **not** NaN.
- Once NaN enters many ordinary arithmetic operations, the result continues to be NaN, for example `Double.NaN + 10.0`.

NaN has special bit patterns in floating-point representation, and multiple distinct NaN bit patterns can exist. Primitive comparison rules apply to **any NaN value**, regardless of how it was produced. You do not need to compare or manipulate these bits to detect NaN.

## 2. Rules for == and != with Primitive float/double

According to Java's floating-point comparison semantics:

- If **either operand** is NaN, `==` is always `false`.
- If **either operand** is NaN, `!=` is always `true`.
- This remains true when both operands are NaN, or when both sides come from **the same variable**.

| Primitive comparison | Result |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN == 1.0` | `false` |
| `Double.NaN != 1.0` | `true` |
| `Float.NaN == Float.NaN` | `false` |
| `Float.NaN != Float.NaN` | `true` |
| `1.0 == 1.0` | `true` |
| `1.0 != 1.0` | `false` |

The presence of NaN makes a familiar intuition—"everything equals itself"—**false for the `==` operator on primitive `float`/`double`**. Precisely stated, floating-point equality here is not reflexive across the entire domain of primitive values because of NaN.

A non-NaN variable still compares `true` to itself under `==`, even when it is `Double.POSITIVE_INFINITY` or `Double.NEGATIVE_INFINITY`. For example:

~~~java
double infinity = Double.POSITIVE_INFINITY;
System.out.println(infinity == infinity); // true

double zero = +0.0;
System.out.println(zero == -0.0);         // true
~~~

The two values `+0.0` and `-0.0` have different bit representations, yet primitive `==` considers them equal. NaN's special rule does not mean all special values are unequal to themselves.

## 3. Ordering Comparisons with NaN

NaN also causes the ordering comparisons `<`, `<=`, `>`, and `>=` to all return `false` when **at least one operand** is NaN.

| Expression | Result when `x = Double.NaN` |
| --- | --- |
| `x < 1.0` | `false` |
| `x <= 1.0` | `false` |
| `x > 1.0` | `false` |
| `x >= 1.0` | `false` |
| `x == 1.0` | `false` |
| `x != 1.0` | `true` |

NaN cannot be treated as a "very large" number, a "very small" number, or "equal to itself" in primitive comparisons. NaN is considered **unordered** relative to floating-point values in the ordering relation of the operators above.

An important consequence: checks that seem equivalent when data is finite **are not equivalent** if the data can contain NaN.

~~~java
double x = Double.NaN;

boolean outOfRange = x < 0.0 || x > 100.0; // false
boolean insideRange = x >= 0.0 && x <= 100.0; // false
boolean notInsideRange = !insideRange;        // true
~~~

The expression `x < 0 || x > 100` **fails to detect NaN** and can let NaN slip through if the application uses only it to reject out-of-range input. Similarly, `!(x < 0)` is `true` for NaN, whereas `x >= 0` is `false`. The two conditions are not equivalent across the entire `double` domain.

## 4. Detecting NaN with the Proper API

Prefer the two static methods:

~~~java
double x = 0.0 / 0.0;
float y = Float.NaN;

boolean a = Double.isNaN(x); // true
boolean b = Float.isNaN(y);  // true
~~~

They return `true` precisely when the argument is NaN and `false` for all other values, including positive and negative infinity.

You can write:

~~~java
boolean hasNaN = x != x; // true when x is NaN, based on IEEE 754 behavior
~~~

However, this check is harder to read. `Double.isNaN(x)` states the intent clearly, making code review, maintenance, and codebase searching easier.

If business logic needs to accept **only finite numeric values**, `isNaN` is not enough, because infinity is not NaN:

~~~java
double value = Double.POSITIVE_INFINITY;

System.out.println(Double.isNaN(value));   // false
System.out.println(Double.isFinite(value)); // false
~~~

`Double.isFinite(value)` and `Float.isFinite(value)` return `true` when the value is neither NaN nor infinite. When handling measurements, converted currencies, probabilities, or bounds, choose an explicit policy: forbid only NaN or forbid infinity as well.

## 5. Standalone Java 17+ Example and Output

Create the file `NaNComparisonDemo.java`:

~~~java
public class NaNComparisonDemo {
    public static void main(String[] args) {
        double invalid = 0.0 / 0.0;
        float missing = Float.NaN;

        System.out.println("value: " + invalid);
        System.out.println("self ==: " + (invalid == invalid));
        System.out.println("self !=: " + (invalid != invalid));
        System.out.println("NaN == NaN: " + (invalid == Double.NaN));
        System.out.println("NaN < 1: " + (invalid < 1.0));
        System.out.println("NaN <= 1: " + (invalid <= 1.0));
        System.out.println("NaN > 1: " + (invalid > 1.0));
        System.out.println("NaN >= 1: " + (invalid >= 1.0));
        System.out.println("float self ==: " + (missing == missing));

        System.out.println("Double.isNaN: " + Double.isNaN(invalid));
        System.out.println("Float.isNaN: " + Float.isNaN(missing));
        System.out.println("Double.isFinite: " + Double.isFinite(invalid));

        System.out.println("boxed equals: "
                + Double.valueOf(invalid).equals(Double.valueOf(Double.NaN)));
        System.out.println("Double.compare: "
                + Double.compare(invalid, Double.NaN));

        System.out.println("infinity self ==: "
                + (Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY));
        System.out.println("signed zero ==: " + (+0.0 == -0.0));
        System.out.println("sqrt(-1): " + Math.sqrt(-1.0));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac NaNComparisonDemo.java
java NaNComparisonDemo
~~~

Output:

~~~text
value: NaN
self ==: false
self !=: true
NaN == NaN: false
NaN < 1: false
NaN <= 1: false
NaN > 1: false
NaN >= 1: false
float self ==: false
Double.isNaN: true
Float.isNaN: true
Double.isFinite: false
boxed equals: true
Double.compare: 0
infinity self ==: true
signed zero ==: true
sqrt(-1): NaN
~~~

Explanation by group:

1. Dividing `0.0 / 0.0` produces NaN, so `invalid == invalid` is still `false` and `invalid != invalid` is `true`.
2. Relational operators with NaN return `false`, including `<=` and `>=`, because there is no arithmetic ordering with NaN.
3. `Float.NaN` follows the same **primitive comparison rules** as `Double.NaN`, regardless of 32-bit vs. 64-bit width.
4. `Double.isNaN`/`Float.isNaN` detect NaN, while `Double.isFinite` excludes both NaN and infinity.
5. The `boxed equals` and `Double.compare` lines produce results different from the primitive `==` operator according to the wrapper class **API contract**, explained in the next section.
6. Infinity compared with itself gives `true`, two zeros with opposite signs are still considered equal, and the square root of a negative number in `Math.sqrt(-1.0)` is NaN.

## 6. Differences from Double.equals, Double.compare, and Float Equivalents

The topic "NaN is not equal to itself" refers to **primitive value comparison operators**. Java also has APIs for object comparison, sorting, and data structures, with different conventions.

| Comparison method | Two NaN values | `+0.0` and `-0.0` | Purpose |
| --- | --- | --- | --- |
| `doubleA == doubleB` | `false` | `true` | Primitive comparison operation |
| `Double.valueOf(a).equals(Double.valueOf(b))` | `true` | `false` | Wrapper equality contract |
| `Double.compare(a, b)` | `0` | Non-zero | Defined ordering for sorting |

`Double.equals` considers all NaN values equal according to the `Double` class contract. It also distinguishes the sign bit of the two zeros; `Double.compare` uses the same ordering convention: `-0.0` comes before `+0.0`, and NaN is ordered greater than every numeric value (including positive infinity). These conventions are useful for sorting, ordered maps, and data structures that require consistent relations.

Example snippet **placed inside a Java method**:

~~~java
double a = Double.NaN;
double b = Double.NaN;

System.out.println(a == b);  // false (primitive)
System.out.println(Double.valueOf(a).equals(Double.valueOf(b))); // true
System.out.println(Double.compare(a, b) == 0); // true
System.out.println(+0.0 == -0.0);              // true
System.out.println(Double.compare(-0.0, +0.0)); // -1
~~~

Similarly, there are `Float.equals` and `Float.compare`. The `Double.compare`/`Float.compare` APIs establish a total order according to **Java's convention**, differing from primitive ordering when NaN appears.

Another pitfall to avoid: with two `Double` reference variables, the `==` operator on **two objects** can compare reference identity rather than floating-point content. If one side is primitive and unboxing occurs, the operation follows primitive rules again. Therefore, when talking about "comparing NaN," always specify whether you mean primitive operators, wrapper `equals`, or `compare`.

## 7. Common Bugs When Validating Data

### 7.1. Comparing Against Double.NaN with ==

~~~java
double value = compute();

// Wrong: condition is always false even when value is NaN.
if (value == Double.NaN) {
    throw new IllegalArgumentException("NaN");
}

// Correct: explicitly detect NaN.
if (Double.isNaN(value)) {
    throw new IllegalArgumentException("NaN");
}
~~~

Here `compute()` is a **hypothetical** method name, so this snippet only illustrates the validation condition and is not a standalone runnable program. Because `Double.NaN == Double.NaN` is inherently `false`, using `== Double.NaN` will never properly detect NaN.

### 7.2. Checking Only Out-of-Bounds Conditions

~~~java
double percentage = Double.NaN;

if (percentage < 0.0 || percentage > 100.0) {
    throw new IllegalArgumentException("Out of range");
}
// NaN slips through because both comparisons are false.
~~~

If you only accept finite percentages from 0 to 100, write a condition that covers the special domain:

~~~java
static boolean validPercentage(double value) {
    return Double.isFinite(value) && value >= 0.0 && value <= 100.0;
}
~~~

The snippet above is an **illustrative method** to place inside a Java class. When `value` is NaN, `Double.isFinite(value)` is `false`; the same holds for infinity. Only when the value is finite do the lower and upper bounds need checking.

If requirements allow infinity, define an explicit rule instead of automatically using `isFinite`. For example, optimization problems sometimes intentionally use `Double.POSITIVE_INFINITY` as a sentinel value.

### 7.3. Inferring from Negating an Ordering Operator

~~~java
double x = Double.NaN;
boolean notLess = !(x < 5.0); // true
boolean atLeast = x >= 5.0;   // false
~~~

With NaN, `!(x < 5)` and `x >= 5` **differ**. Similarly, `!(x == y)` is equivalent to `x != y`, but `!(x < y)` does not mean `x >= y` when one side is NaN. This is why mathematical rewrites of conditions can change results when data contains NaN.

### 7.4. Confusing NaN with null or Infinity

- `NaN` is **a special primitive value** of `float`/`double`, not `null`.
- `null` is a state of a **reference** such as `Double`, not a value a primitive `double` can hold.
- `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are infinities, not NaN. You can check them with `Double.isInfinite` or check finiteness with `Double.isFinite`.
- A `Double` variable holding `null`, if **unboxed** for a primitive operation, can cause a `NullPointerException`; this is a different error from comparison operators receiving NaN.

## 8. NaN in Branching Conditions and Sorting

Consider this pattern:

~~~java
double measurement = Double.NaN;

if (measurement < 0.0) {
    System.out.println("Negative");
} else if (measurement >= 0.0) {
    System.out.println("Nonnegative");
} else {
    System.out.println("Not ordered (NaN)");
}
~~~

The final branch executes because both `measurement < 0.0` and `measurement >= 0.0` are `false`. When an algorithm branches on ordering conditions, you must handle NaN explicitly upfront or provide a fallback branch for the unordered case.

When sorting a list that may contain NaN, do not write a naive comparator like `(a, b) -> a < b ? -1 : a > b ? 1 : 0`. That comparator returns 0 whenever either side is NaN, causing NaN to be treated as equal to every number and potentially violating the consistency required by the sorting algorithm.

Instead, use:

~~~java
java.util.List<Double> values = new java.util.ArrayList<>(
        java.util.List.of(Double.NaN, 2.0, -1.0, 0.0));
values.sort(Double::compare);
// Order according to Double.compare: -1.0, 0.0, 2.0, NaN
~~~

This is an **illustrative snippet** to place inside a method; `Double::compare` guarantees ordering according to Java's contract, including the rule that NaN comes after all numbers. The list formatting in the comment is an explanatory example, not mandatory stdout.

## 9. Practice Questions with Answers

**Question 1.** Given `double x = Double.NaN;`, what are the results of `x == x`, `x != x`, and `x <= x`?  
**Answer:** `false`, `true`, `false`. With NaN, equality and ordering comparisons are all `false`, while inequality (`!=`) is `true`.

**Question 2.** Do `Double.NaN == 5.0` and `Double.NaN > 5.0` give the same result?  
**Answer:** Yes, both are `false`; however, the reason is not that NaN is a number less than 5, but that NaN has no arithmetic ordering with 5.

**Question 3.** Why is `!(x < 10.0)` not always equivalent to `x >= 10.0`?  
**Answer:** When `x` is NaN, `x < 10.0` is `false`, so the negated expression is `true`, yet `x >= 10.0` remains `false`.

**Question 4.** What should you use to check that a `double` value is allowed in a calculation and must strictly not be NaN?  
**Answer:** `!Double.isNaN(value)`. If infinities are also disallowed, use `Double.isFinite(value)`.

**Question 5.** Why is `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` `true` while `Double.NaN == Double.NaN` is `false`?  
**Answer:** `Double.equals` applies the wrapper class contract that treats NaNs as equal; primitive `==` applies floating-point comparison rules, under which NaN is not equal to any value, including itself.

**Question 6.** What bug exists in a comparator written as `a < b ? -1 : a > b ? 1 : 0` when `a` or `b` is NaN?  
**Answer:** Both `a < b` and `a > b` are `false`, so the comparator returns 0 for many non-equivalent pairs, risking a violation of the comparison contract. Use `Double.compare(a, b)` for clear ordering rules.

## 10. Takeaways

- NaN is a special value of `float` and `double`; primitive `==` with any NaN returns `false`, even `x == x`.
- `!=` with NaN returns `true`; `<`, `<=`, `>`, and `>=` with NaN all return `false`.
- Use `Float.isNaN`/`Double.isNaN` to detect NaN. If infinities must also be rejected, use `Float.isFinite`/`Double.isFinite`.
- Do not infer "greater than or equal to" from "not less than" when data can contain NaN; range checks must account for the unordered case.
- `Double.equals` and `Double.compare` have their own conventions for NaN to support object equality and sorting, so distinguish them from primitive `==`.
