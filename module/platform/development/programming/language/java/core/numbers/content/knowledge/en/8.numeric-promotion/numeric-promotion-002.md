# Binary numeric promotion with int, long, float, and double in Java

## 1. What is binary numeric promotion?

**Binary numeric promotion** is the set of rules Java uses to determine a **common type for two numeric operands** across many binary operators. When two operands have different primitive types, Java converts them to an appropriate type before performing the operation. The result type of an arithmetic operation is determined by these rules, **not inferred backward from the type of the receiving variable**.

Example:

```java
int count = 50_000;
int price = 50_000;

long wrong = count * price;          // Multiplication is int, overflows before long assignment.
long correct = (long) count * price; // Multiplication is long, result 2500000000.
```

An arithmetic operation between two `int` values remains `int`, even when the result is assigned to a `long` or `double`. Only when **at least one operand** is promoted to `long`, `float`, or `double` *before the operation* does the operation type change according to the corresponding rule.

This lesson focuses on combinations of four types: `int`, `long`, `float`, and `double`. Smaller integer types are also mentioned to clarify why the default starting point is `int`.

## 2. Precedence rules for choosing the type

According to the Java Language Specification (JLS §5.6), given two numeric operands in a context where binary numeric promotion applies, applicable wrapper objects are first **unboxed** if needed. Then Java chooses the common type in the following order:

1. If **either operand is `double`**, the other operand is converted to `double`.
2. If there is no `double` but there is a **`float`**, the other operand is converted to `float`.
3. If neither floating-point type above is present but there is a **`long`**, the other operand is converted to `long`.
4. If none of the above types are present, both operands are converted to **`int`** as needed. This applies to `byte`, `short`, `char`, and `int`.

| Two operand types | Common type for arithmetic operation |
| --- | --- |
| `int` + `int` | `int` |
| `int` + `long` | `long` |
| `long` + `float` | `float` |
| `int` + `float` | `float` |
| `float` + `double` | `double` |
| `long` + `double` | `double` |
| `byte` + `short` | `int` |
| `char` + `int` | `int` |

The order to remember is **`double > float > long > int`** for picking the common type, but **"higher-ranking type" does not always mean "preserves all digits"**. In particular, `long → float` can round, and `long → double` can round large integers.

In the table above, the `+` sign illustrates **numeric addition**. If one operand is `String`, `+` can instead perform *string concatenation* under different rules. `boolean` is not a numeric type and is not subject to binary numeric promotion.

## 3. Which operators apply this rule?

Binary numeric promotion participates when Java evaluates many binary numeric operators:

- Arithmetic operators `+`, `-`, `*`, `/`, `%` when both operands are numeric.
- Relational ordering operators `<`, `<=`, `>`, `>=` on numeric operands. Both operands are promoted for comparison, but **the result of the comparison is `boolean`**.
- `==` and `!=` when comparing two operands of primitive numeric types (or unboxed according to applicable rules). The result is `boolean`.
- Bitwise operators `&`, `|`, `^` in **integer** mode, with a common type of `int` or `long`.

It is important **not to misapply this rule to every operator**. Shift operators `<<`, `>>`, `>>>` use independent *unary numeric promotion* on each operand; the result type depends on the **left** operand after promotion, and is not pulled up to `long` by the right operand. The conditional operator `?:` and compound assignment operators also have their own typing rules, even though numeric promotion may be involved internally.

Example:

```java
int a = 7;
long b = 2L;

long sum = a + b;       // long + long => long
long quotient = a / b;  // long / long => long; result 3L.
boolean larger = a > b; // Both operands compared as long; result boolean.
```

Even division with a common type of `long` is still **integer division** and truncates toward 0. To get `3.5`, a `float` or `double` operand must be used.

## 4. Combining `int` and `long`: 64-bit operations

If one operand is `long` and neither is `float`/`double`, Java converts the other operand to `long` before performing the operation:

```java
int n = 2_000_000_000;
long m = 2L;

long product = n * m;  // 4000000000; int * long => long operation.
long also = n * 2L;    // 4000000000; L suffix creates a long literal.
```

Compare with the case where there is no `long` operand:

```java
int n = 2_000_000_000;

long tooLate = n * 2;        // -294967296; int multiplication overflows.
long early = ((long) n) * 2; // 4000000000; long multiplication.
```

**Correct mental model:** the assignment `long tooLate = ...` consists of two steps: evaluate the **entire right-hand expression** in its own type, then convert the result to `long`. If the `int` multiplication already overflowed, the assignment step cannot recover the lost bits.

Parentheses can change when promotion occurs:

```java
int a = 50_000, b = 50_000;
long c = 2L;

long tooLate = (a * b) * c;      // -3589934592
long early = ((long) a * b) * c; // 5000000000
```

In `(a * b) * c`, the subexpression `a * b` already overflowed `int`; encountering `c` of type `long` afterward does not fix the earlier result. Promotion rules are applied **at each operation** of the expression tree.

## 5. Combining integers with `float`: watch out for rounding

When one operand is `float` and there is no `double`, Java evaluates the operation in `float`:

```java
int a = 4;
float b = 1.5f;
float sum = a + b;     // 5.5f

long big = 10L;
float product = big * b; // 15.0f, because long is converted to float.
```

`float` uses binary floating-point with **24 bits of significand precision**. This is not enough to represent every `int` or `long` value exactly. Every integer in the range `-16_777_216` to `16_777_216` is represented exactly in `float`, but larger integers can be rounded.

```java
int exactInt = 16_777_217;
float rounded = exactInt + 0.0f;

System.out.println(rounded == 16_777_216f); // true
System.out.println((int) rounded == exactInt); // false
```

Step-by-step explanation:

1. Operand `exactInt` is `int`, operand `0.0f` is `float`.
2. Binary numeric promotion converts `exactInt` to `float`.
3. The value `16_777_217` cannot be represented exactly in `float`, so it is rounded to `16_777_216.0f` (round-to-nearest under IEEE 754 rules).
4. Only then is `0.0f` added, yielding the rounded result.

Therefore, **converting to a type with a larger range does not guarantee precision**. `float` can represent larger magnitudes than `long`, yet has much poorer integer precision.

A common example is `long + float`:

```java
long id = 16_777_217L;
float value = id + 0.0f;

System.out.println((long) value == id); // false
```

For identifiers, counters, or exact integer currency amounts, do not use `float` to "avoid overflow" merely because it outranks `long` in the promotion order.

## 6. Combining with `double`: highest precedence, not infinite precision

If either operand is `double`, the arithmetic operation uses `double`:

```java
float left = 1.25f;
double right = 2.5;
double sum = left + right; // 3.75.

long count = 7L;
double factor = 0.5;
double half = count * factor; // 3.5.
```

`double` has **53 bits of significand precision**, so every `int` value and every integer with absolute value at most `2^53` is represented exactly. However, `long` can exceed `2^53`. A `long + double` calculation can lose precision when converting `long` to `double`:

```java
long exact = 9_007_199_254_740_993L; // 2^53 + 1.
double rounded = exact + 0.0;

System.out.println((long) rounded == exact); // false
```

The value `9_007_199_254_740_993` cannot be represented exactly in `double`. It is rounded to `9_007_199_254_740_992.0`. Casting `double` back to `long` does not restore the lost unit.

It is also necessary to distinguish **representable magnitude**, **precision**, and **operation rules**. For instance, `0.1 + 0.2` uses `double` but does not represent the exact mathematical decimal sum `0.3` because those decimal numbers have no finite binary representation. That is a limitation of floating-point, not a bug in binary numeric promotion.

## 7. Expression type is decided before variable assignment

Three examples of the same rule:

### 7.1. Assigning to `long` after `int` multiplication

```java
int price = 50_000;
int quantity = 50_000;

long wrong = price * quantity;          // -1794967296
long correct = (long) price * quantity; // 2500000000
```

### 7.2. Assigning to `double` after `int` division

```java
int numerator = 1;
int denominator = 2;

double wrong = numerator / denominator;         // 0.0
double correct = (double) numerator / denominator; // 0.5
double alsoCorrect = numerator / 2.0;           // 0.5
```

Because `int / int` is integer division, `numerator / denominator` yields `0`. Assigning that `0` to `double` produces `0.0`, not `0.5`. Conversely, `(double) numerator / denominator` uses `double` right from the division.

### 7.3. Casting after an expression vs. casting before

```java
int a = 50_000, b = 50_000;

long castAfter = (long) (a * b); // -1794967296
long castBefore = (long) a * b;  // 2500000000
```

Adding parentheses forces the multiplication to happen before the cast. To widen the computation domain, cast **one operand before performing the risky operation**, rather than casting the entire expression at the end.

## 8. `byte`, `short`, and `char` are all promoted to `int`

Binary numeric promotion has no branch that selects `byte`, `short`, or `char` as a common type. Without `long`/`float`/`double`, all those smaller integral types are promoted to `int`:

```java
byte b = 10;
short s = 20;
char c = 'A';

int sum = b + s;        // 30; expression type is int.
int codePointValue = c + 1; // 66; expression type is int.

// byte wrong = b + s; // Does not compile: int does not automatically narrow to byte.
```

The exception for assigning certain `int` **constant expressions** whose value lies within the target range (for example, `byte k = 10 + 20;`) is an *assignment conversion* rule for constants. It **does not change the type of the addition expression**: `10 + 20` is still `int`.

Wrappers such as `Integer`/`Long`/`Float`/`Double` can participate via **unboxing**:

```java
Integer boxedInt = 2;
Long boxedLong = 3L;
long sum = boxedInt + boxedLong; // 5L.
```

However, if a wrapper is `null` and must be unboxed to evaluate, the expression can throw `NullPointerException`. Binary numeric promotion does not turn `null` into `0`.

## 9. Two subtle traps: mixed comparisons and compound assignment

### 9.1. Comparing `int` with `float` can lose distinguishability

```java
int n = 16_777_217;
float f = 16_777_216f;

System.out.println(n == f); // true
```

The two integer values were meant to be distinct, yet the `==` operator applies binary numeric promotion to the `int`/`float` pair. `n` is rounded down to `16_777_216f` before comparison, so the result is `true`.

When you need **exact comparison of integers**, keep the operands in an integral type wide enough (`long` if in range, or `BigInteger` beyond 64 bits). Do not blindly perform mixed comparisons with `float`/`double`.

### 9.2. Compound assignment operators have an implicit narrowing cast

For `E1 += E2`, Java computes the addition and then converts the result to the type of `E1`. In terms of value, this is close to `E1 = (T) (E1 + E2)`, where `T` is the type of `E1`, except that `E1` is evaluated only once in compound assignment.

```java
byte count = 120;
count += 10; // Valid, addition as int, then narrowed to byte.
System.out.println(count); // -126

int whole = 2;
whole += 1.75; // Valid, addition as double, then converted to int.
System.out.println(whole); // 3
```

Writing `count = count + 10` and `whole = whole + 1.75` will not compile without appropriate casts. However, `+=` has an implicit conversion mechanism, which can lead to overflow or truncation of the fractional part. Therefore, **compound assignment is not proof that the underlying operation had a narrow type**.

## 10. Distinguishing from unary numeric promotion and bitwise shifts

The example below can easily tempt learners to apply the *binary* table to bitwise shifts:

```java
int bits = 1;
long count = 40L;

int shifted = bits << count; // Result type is int.
```

Even though the right operand `count` has type `long`, the shift **does not turn the left `int` operand into `long`**. Each operand undergoes *unary numeric promotion* separately; the result has the type of the promoted left operand. For an `int` shift, Java only uses the lowest 5 bits of the shift distance, so `1 << 40` is equivalent to `1 << 8`, giving `256`.

If you truly want a 64-bit shift:

```java
long shifted64 = 1L << 40; // 1099511627776.
```

This is an important distinction between **binary numeric promotion** for arithmetic operators and the separate rules for bitwise shift operators. Do not guess the result type based solely on which operand is "widest" if the operator does not apply binary numeric promotion.

## 11. Complete Java 17+ example

Create the file **`BinaryNumericPromotionDemo.java`**:

```java
public class BinaryNumericPromotionDemo {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        long late = a * b;
        long early = (long) a * b;
        System.out.println("int * int then long = " + late);
        System.out.println("long * int = " + early);

        int halfAsInt = 1 / 2;
        double halfLate = 1 / 2;
        double halfCorrect = 1 / 2.0;
        System.out.println("int division = " + halfAsInt);
        System.out.println("int division then double = " + halfLate);
        System.out.println("double division = " + halfCorrect);

        int number = 16_777_217;
        float roundedFloat = number + 0.0f;
        System.out.println("int to float exact = "
                + ((int) roundedFloat == number));

        long big = 9_007_199_254_740_993L;
        double roundedDouble = big + 0.0;
        System.out.println("long to double exact = "
                + ((long) roundedDouble == big));

        float f = 1.25f;
        double d = 2.5;
        System.out.println("float + double = " + (f + d));

        byte small = 120;
        small += 10;
        System.out.println("byte += 10 = " + small);

        int n = 16_777_217;
        float compare = 16_777_216f;
        System.out.println("int == float = " + (n == compare));

        long mixed = 2 + 3L;
        System.out.println("int + long = " + mixed);
    }
}
```

Compile and run from the directory containing the file using JDK 17 or higher:

```bash
javac BinaryNumericPromotionDemo.java
java BinaryNumericPromotionDemo
```

Expected output:

```text
int * int then long = -1794967296
long * int = 2500000000
int division = 0
int division then double = 0.0
double division = 0.5
int to float exact = false
long to double exact = false
float + double = 3.75
byte += 10 = -126
int == float = true
int + long = 5
```

In this example, `int * int` overflows even though the receiving variable is `long`; `int / int` drops the fractional part even though the receiving variable is `double`; and `float`/`double` operands can force integers to round **before the operation or comparison**. Each case shows that an expression's type must be determined at the **operator**, not inferred from where the result is stored.

## 12. Common mistakes and how to avoid them

| Misconception | Reality | How to handle |
| --- | --- | --- |
| "The left side is `long`, so `int * int` becomes 64-bit multiplication." | The `int` multiplication already happened before the assignment. | Write `(long) a * b` or use a `long` operand. |
| "The left side is `double`, so `1 / 2` gives `0.5`." | The division is `int / int`, producing `0`. | Write `1.0 / 2`. |
| "`float` is wider than `long`, so it holds every `long` exactly." | `float` has 24 bits of precision; many integers get rounded. | Stay in integral types when exactness is required. |
| "`double` always preserves every `long`." | `double` has 53 bits of precision; it cannot hold all 64-bit values. | Use `long`/`BigInteger` when exact integer arithmetic is needed. |
| "Adding two `byte` values yields a `byte`." | Arithmetic addition promotes to `int`. | Receive the result as `int`, check bounds before narrowing. |
| "Compound `+= `loses no data because no cast is required." | Compound assignment casts the result to the left operand's type. | Account for overflow and fractional truncation explicitly. |
| "All binary operators use the same precedence table." | Bitwise shifts, string concatenation, and `?:` have their own rules. | Identify the operator and check its exact typing context. |
| "Comparing an integer with `float` is always exact." | Conversion during comparison can round before `==` is evaluated. | Compare within a sufficiently wide integral type. |

**Takeaway:** For arithmetic operations subject to binary numeric promotion, the type precedence is **`double > float > long > int`**. Choosing a type before calculation does not guarantee exactness in all cases: `int` operations can overflow, while converting integers to `float`/`double` can round. To get the intended result, determine the type of **each operation and subexpression**, deliberately choose the right operands, and only afterward consider assigning the result.

**References:** [JLS §5.6 — Numeric Contexts and Promotions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [JLS §15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), [JLS §15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18), [JLS §15.20 — Relational Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20), [JLS §15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.26).