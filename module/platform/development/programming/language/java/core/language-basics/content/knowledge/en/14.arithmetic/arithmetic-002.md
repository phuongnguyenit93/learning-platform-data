# Integer Division and Truncation Toward Zero — Java 17+

## 1. Objective: Understanding the `/` Division Operator on Integers

In Java 17+, when **both operands of `/` are integer types** (`byte`, `short`, `char`, `int`, `long` after promotion rules), the result is an **integer quotient**. Java takes the integer part of the mathematical quotient by **truncating the fractional part toward zero** (*truncation toward zero*).

~~~java
int a = 7;
int b = 2;

int quotient = a / b;
System.out.println(quotient); // 3
~~~

Mathematically, `7 / 2 = 3.5`; integer division returns **3** because the `.5` part is discarded. If the signs change:

~~~java
System.out.println(-7 / 2);  // -3, not -4
System.out.println(7 / -2);  // -3
System.out.println(-7 / -2); // 3
~~~

For negative numbers, "truncating toward zero" differs from "rounding down":

- `-3.5` truncated toward zero → `-3`.
- `-3.5` rounded down along the number line → `-4`.

**Main point:** `/` on two integers **does not automatically compute a floating-point number**, does not round to nearest, and is not `Math.floor`. To get a result with a fractional part, you must use at least one floating-point operand **before the division**.

## 2. Sign Rules and Basic Examples

| Java Expression | Exact Mathematical Quotient | Integer Division Result | Explanation |
|---|---:|---:|---|
| `7 / 2` | 3.5 | `3` | Drops .5 toward 0 |
| `-7 / 2` | -3.5 | `-3` | Drops -.5 toward 0, does not become -4 |
| `7 / -2` | -3.5 | `-3` | One negative sign |
| `-7 / -2` | 3.5 | `3` | Two negative signs |
| `-1 / 2` | -0.5 | `0` | `int` has no negative 0 |
| `1 / -2` | -0.5 | `0` | Truncated toward 0 |
| `8 / 2` | 4 | `4` | Divides evenly |
| `0 / 3` | 0 | `0` | Dividend is 0, non-zero divisor |

The sign of a **non-zero quotient** is negative when the two operands have opposite signs, and positive when they have the same sign. If the magnitude of the quotient is less than 1, the integer result is 0 regardless of the mathematical sign; Java has no `-0` in `int` or `long`.

### Do Not Think of "Truncating the Fractional Part" as a String Operation

The operation `7 / 2` works at the level of **the language's arithmetic rules**, not by turning `3.5` into a string and deleting the `.5` characters. No intermediate value needs to exist as a `double`:

~~~java
var result = 7 / 2; // result has type int and value 3
~~~

Using `var` does not change the type of the division expression.

## 3. Operand Types Determine the Result Type

| Operands | Expression | Result Type | Example |
|---|---|---|---|
| `int` and `int` | `7 / 2` | `int` | `3` |
| `long` and `int` | `7L / 2` | `long` | `3L` |
| `int` and `long` | `7 / 2L` | `long` | `3L` |
| `float` and `int` | `7f / 2` | `float` | `3.5f` |
| `double` and `int` | `7.0 / 2` | `double` | `3.5` |
| `int` and `double` | `7 / 2.0` | `double` | `3.5` |

In Java, `byte`, `short`, and `char` are **promoted to `int`** when participating in ordinary arithmetic division:

~~~java
byte first = 9;
short second = 2;

int quotient = first / second; // Expression result is int
System.out.println(quotient); // 4

// byte wrong = first / second; // Compile error: int cannot be implicitly assigned to byte
~~~

Why? The *binary numeric promotion* rule applies before `/` is executed. Do not infer an expression's type from the receiving variable's type or from the fact that the result happens to fit in the `byte` range.

**`boolean` cannot be used with division.** Wrapper types such as `Integer`, `Long` can be **unboxed** in arithmetic operations; if the wrapper is `null`, unboxing can throw a `NullPointerException` before dividing.

## 4. The Receiving Variable Type Does Not Change an Already-Computed Quotient

~~~java
int numerator = 7, denominator = 2;
double assignedAfter = numerator / denominator;       // 3.0
double castAfter = (double) (numerator / denominator); // 3.0
double castBefore = (double) numerator / denominator;  // 3.5
~~~

The first two lines use `int / int` division, so the fractional part is already lost before assigning or casting the result. The last line converts **an operand before `/`**, so it performs floating-point division. The next lesson goes deeper into cast placement, result types, and precision limits; the focus here is recognizing the **truncation toward zero** step.

## 5. The Remainder Is the Trace of a Quotient Truncated Toward Zero

For `b != 0`, the integer quotient `q = a / b` and remainder `r = a % b` satisfy the mathematical relation `a = q * b + r`. For instance, `-7 / 2` equals `-3`, so `-7 % 2` equals `-1`: `-7 = (-3) * 2 + (-1)`.

~~~java
System.out.println(-7 / 2); // -3
System.out.println(-7 % 2); // -1
~~~

A non-zero integer remainder has the same sign as the **dividend**. The lesson on remainder sign analyzes all four sign pairs, `Math.floorMod`, and edge cases in full.

## 6. `Math.floorDiv`: Differing from Integer Division on Negative Numbers

Java 17 provides `Math.floorDiv(int, int)` and `Math.floorDiv(long, long)` along with related overloads. Unlike `/` which truncates the quotient toward zero, **`Math.floorDiv` rounds the mathematical quotient down toward negative infinity**.

~~~java
System.out.println(-7 / 2);           // -3
System.out.println(Math.floorDiv(-7, 2)); // -4

System.out.println(7 / -2);           // -3
System.out.println(Math.floorDiv(7, -2)); // -4
~~~

| Number Pair | `a / b` (toward 0) | `Math.floorDiv(a,b)` (floor) |
|---|---:|---:|
| 7, 2 | 3 | 3 |
| -7, 2 | -3 | -4 |
| 7, -2 | -3 | -4 |
| -7, -2 | 3 | 3 |
| -1, 2 | 0 | -1 |

To get a **compatible floor quotient and remainder** pair, use `Math.floorMod`:

~~~java
int a = -7;
int b = 2;

int q = Math.floorDiv(a, b); // -4
int r = Math.floorMod(a, b); // 1

System.out.println(q * b + r); // -7
~~~

With a **positive** divisor, `Math.floorMod` produces a **non-negative** remainder. When the divisor is negative, the `floorMod` result can be negative; **do not generalize** that this method always returns a non-negative number.

**Choose the rule based on business requirements:** counting full chunks when negative values can arise, splitting time into negative intervals, or normalizing indices are cases where `floorDiv`/`floorMod` should be considered. For ordinary Java integer division, the `/` operator uses truncation toward zero.

## 7. Parentheses and Associativity of `/`

The operators `*`, `/`, `%` share the same precedence group and **associate from left to right**:

~~~java
System.out.println(20 / 3 / 2);   // 3: (20 / 3) / 2
System.out.println(20 / (3 / 2)); // 20: 20 / 1
~~~

Notice that every integer division truncates the fractional part:

- `20 / 3 / 2`: `20 / 3 = 6`, then `6 / 2 = 3`.
- `20 / (3 / 2)`: `3 / 2 = 1`, then `20 / 1 = 20`.

**You cannot arbitrarily move parentheses** in a chain of integer divisions. Grouping determines where fractional parts are discarded and thus changes the result.

In business formulas with multiple divisions, name intermediate variables or write parentheses that express the meaning of each step.

## 8. Boundary: Integer Division by 0

Both `/` and `%` on integers throw `ArithmeticException` when the divisor is `0`. With `double`, `7.0 / 0.0` yields `Infinity`, and `0.0 / 0.0` yields `NaN`; this is **not** a valid integer quotient. Check the divisor before dividing if it comes from input and you need a finite result or a clear error contract. The dedicated division-by-zero lesson analyzes guards, `OptionalInt`, unboxing, and side effects.

## 9. Edge Case: `MIN_VALUE / -1`

The mathematical quotient of `Integer.MIN_VALUE / -1` exceeds the `int` range, yet Java returns `-2147483648` and **does not throw an exception**:

~~~java
System.out.println(Integer.MIN_VALUE / -1);          // -2147483648
System.out.println(((long) Integer.MIN_VALUE) / -1); // 2147483648
~~~

`Long.MIN_VALUE / -1L` also overflows the `long` range; getting the mathematical value requires a larger type such as `BigInteger`. `Math.floorDiv` is not an overflow-checking operation. The lesson on overflow focuses on `Math.*Exact`, timely operand widening, and range checks.

## 10. Writing a Checked Integer Division Helper for Business Logic

The illustrative method below **does not allow** division by 0 or `int` overflow:

~~~java
static int divideChecked(int a, int b) {
    if (b == 0) {
        throw new IllegalArgumentException("zero divisor");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("int quotient overflow");
    }
    return a / b;
}
~~~

Checking `b == 0` is necessary because Java integer division throws an exception; checking `MIN_VALUE/-1` is necessary **if the requirement forbids silent overflow**.

Depending on your API, you can let `ArithmeticException` be thrown naturally for a zero divisor, but you should **explicitly document the contract** callers can rely on. The example above intentionally throws `IllegalArgumentException` for a zero divisor input to describe a data validation requirement.

If business logic allows the `MIN_VALUE/-1` case to follow Java's overflow behavior, no custom method is needed; understand that choice clearly and avoid assuming the quotient always equals the exact mathematical quotient.

## 11. `>>` Is Not Power-of-Two Division for All Negative Cases

For **non-negative** integers, arithmetic right-shifting by one bit usually produces the same value as integer division by 2:

~~~java
System.out.println(7 / 2);  // 3
System.out.println(7 >> 1); // 3
~~~

But negative numbers give different results:

~~~java
System.out.println(-7 / 2);  // -3: truncated toward 0
System.out.println(-7 >> 1); // -4: sign-extending bit shift
~~~

Because `>>` is a bitwise shift operator and does not apply the truncation-toward-zero rule like `/`. **Do not replace `x / 2` with `x >> 1` when `x` may be negative** merely assuming it is an equivalent optimization.

Modern JITs can optimize division when safe, so the criterion for choosing an operator in source code must be **correct semantics**, not guessing at speed.

## 12. Compound Assignment `/=` and Expression Type

~~~java
int count = 20;
count /= 3;
System.out.println(count); // 6
~~~

With type `int`, `count /= 3` updates `count` with the integer division result `20 / 3 = 6`. Compound assignment is also an expression with a side effect, though writing `count /= 3;` on its own is usually easier to understand.

With smaller operands such as `byte`:

~~~java
byte value = 9;
value /= 2;
System.out.println(value); // 4
~~~

The statement above **compiles**, even though `value / 2` is promoted to `int`, because compound assignment applies an implicit narrowing conversion back to the receiving variable's type. Conversely:

~~~java
byte value = 9;
// value = value / 2; // Compile error: division result is int
~~~

When using `/=`, you still need to watch out for division by 0 and data loss when converting back to the target variable's type; shorter syntax is not a validation mechanism.

## 13. Application: Splitting into Full Groups and a Remainder

A familiar application is splitting **11 items** into groups holding at most **5 items**, with `items >= 0`, `size > 0`:

~~~java
int items = 11;
int size = 5;

int fullGroups = items / size;
int remaining = items % size;
int totalGroups = fullGroups + (remaining == 0 ? 0 : 1);

System.out.println(fullGroups); // 2
System.out.println(remaining);  // 1
System.out.println(totalGroups); // 3
~~~

Explanation: there are 2 full groups, with 1 item remaining requiring 1 extra group. This formula does not automatically apply to every partitioning problem that might have negative data, because **the meaning of negative groups and rounding group counts** must be defined separately.

Before using `totalGroups` as an array size or iteration count, ensure valid domain constraints (`items >= 0`, `size > 0`) and consider integer limits for large calculations.

## 14. Complete, Standalone Java 17 Program

Create a file named exactly **`IntegerDivisionDemo.java`**:

~~~java
import java.math.BigInteger;

public final class IntegerDivisionDemo {
    private IntegerDivisionDemo() {}

    static void showPair(int a, int b) {
        System.out.println("pair " + a + "/" + b
                + ": q=" + (a / b) + ", r=" + (a % b));
    }

    static int divideChecked(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("zero divisor");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("int quotient overflow");
        }
        return a / b;
    }

    public static void main(String[] args) {
        showPair(7, 2);
        showPair(-7, 2);
        showPair(7, -2);
        showPair(-7, -2);
        showPair(-1, 2);

        System.out.println("int result=" + (7 / 2));
        System.out.println("widen after=" + ((double) (7 / 2)));
        System.out.println("double first=" + (((double) 7) / 2));
        System.out.println("double literal=" + (7 / 2.0));
        System.out.println("long operands=" + (7L / 2));

        byte a = 9;
        short b = 2;
        var inferred = a / b;
        System.out.println("byte/short promoted=" + inferred);

        System.out.println("remainder negative=" + (-7 % 2));
        System.out.println("identity=" + ((-7 / 2) * 2 + (-7 % 2)));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 2));
        System.out.println("floorMod=" + Math.floorMod(-7, 2));
        System.out.println("floor reconstructed="
                + (Math.floorDiv(-7, 2) * 2 + Math.floorMod(-7, 2)));

        System.out.println("group left=" + (20 / 3 / 2));
        System.out.println("group right=" + (20 / (3 / 2)));
        System.out.println("shift positive=" + (7 >> 1));
        System.out.println("shift negative=" + (-7 >> 1));
        System.out.println("divide negative=" + (-7 / 2));

        int count = 20;
        count /= 3;
        System.out.println("compound int=" + count);
        byte small = 9;
        small /= 2;
        System.out.println("compound byte=" + small);

        System.out.println("min int / -1=" + (Integer.MIN_VALUE / -1));
        System.out.println("min int widened="
                + (((long) Integer.MIN_VALUE) / -1));
        System.out.println("min long / -1=" + (Long.MIN_VALUE / -1L));
        BigInteger exactLong = BigInteger.valueOf(Long.MIN_VALUE)
                .divide(BigInteger.valueOf(-1));
        System.out.println("min long BigInteger=" + exactLong);

        int zero = 0;
        try {
            int impossible = 7 / zero;
            System.out.println(impossible);
        } catch (ArithmeticException ex) {
            System.out.println("plain zero=ArithmeticException");
        }
        try {
            divideChecked(7, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked zero=" + ex.getMessage());
        }
        try {
            divideChecked(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow=" + ex.getMessage());
        }
        System.out.println("checked normal=" + divideChecked(-7, 2));

        System.out.println("floating / zero=" + (7.0 / 0.0));
        System.out.println("floating 0 / 0=" + (0.0 / 0.0));

        int items = 11;
        int size = 5;
        int full = items / size;
        int remaining = items % size;
        int groups = full + (remaining == 0 ? 0 : 1);
        System.out.println("full groups=" + full);
        System.out.println("remaining=" + remaining);
        System.out.println("total groups=" + groups);
    }
}
~~~

Requires **JDK 17 or newer** and a terminal in the directory containing `IntegerDivisionDemo.java`. No Maven, Gradle, or libraries outside the JDK are needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerDivisionDemo.java
java -cp . IntegerDivisionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerDivisionDemo.java
java -cp . IntegerDivisionDemo
~~~

**Exact expected output:**

~~~text
pair 7/2: q=3, r=1
pair -7/2: q=-3, r=-1
pair 7/-2: q=-3, r=1
pair -7/-2: q=3, r=-1
pair -1/2: q=0, r=-1
int result=3
widen after=3.0
double first=3.5
double literal=3.5
long operands=3
byte/short promoted=4
remainder negative=-1
identity=-7
floorDiv=-4
floorMod=1
floor reconstructed=-7
group left=3
group right=20
shift positive=3
shift negative=-4
divide negative=-3
compound int=6
compound byte=4
min int / -1=-2147483648
min int widened=2147483648
min long / -1=-9223372036854775808
min long BigInteger=9223372036854775808
plain zero=ArithmeticException
checked zero=zero divisor
checked overflow=int quotient overflow
checked normal=-3
floating / zero=Infinity
floating 0 / 0=NaN
full groups=2
remaining=1
total groups=3
~~~

**How to verify the output:**

1. The `pair` lines show the quotient **truncated toward 0** and the remainder **following the dividend's sign**.
2. `widen after` differs from `double first`: casting **after** dividing does not restore the fractional part.
3. `byte/short promoted` shows two small operands still produce an `int` division result.
4. `floorDiv`/`floorMod` differ from `/`/`%` on negative numbers, yet still reconstruct -7 in the example.
5. The two groupings `20 / 3 / 2` and `20 / (3 / 2)` differ because integer division truncates after **each step**.
6. Bitwise shift `-7 >> 1` gives -4, differing from `-7 / 2` giving -3.
7. The `MIN_VALUE/-1` case overflows without Java **automatically throwing an exception**; `divideChecked` actively detects overflow.
8. Integer division by 0 throws an exception; `double` gives Infinity or NaN per floating-point rules.
9. The final group-splitting section applies both quotient and remainder to non-negative data.

## 15. Common Mistakes

| Code / Misconception | Why Is It Wrong? | How to Handle It |
|---|---|---|
| `7 / 2` gives 3.5 | Both operands are `int`; integer division | Use `7.0 / 2` if a floating-point number is wanted |
| `double d = 7 / 2;` gives 3.5 | 3 is produced first, then widened | Cast an operand **before dividing** |
| `(double)(7 / 2)` restores .5 | Cast occurs after truncation | `((double)7)/2` |
| `-7 / 2` gives -4 | Java truncates toward 0, not floor | Use `Math.floorDiv(-7, 2)` if floor is needed |
| `-7 % 2` gives 1 | Java remainder takes the dividend's sign | Use `Math.floorMod` if a non-negative remainder with a positive divisor is wanted |
| `20 / 3 / 2` always equals `20 / (3/2)` | Integer division and grouping differ | Keep parentheses intentional |
| `long q = intA / intB` is always exact in long | Division happens in int first | Cast an operand to long when needed |
| `byte q = byteA / byteB;` | Numeric promotion produces an int result | Receive as int or cast with checks |
| `int q = 7 / 0` gives Infinity | Integer division with divisor 0 throws an exception | Check divisor, handle error |
| `Integer.MIN_VALUE / -1` throws overflow | Java returns MIN_VALUE when the quotient does not fit in int | Check separately, use long when appropriate |
| `Long.MIN_VALUE / -1L` can be handled in long | Positive quotient exceeds long range | Use `BigInteger` when an exact value is needed |
| `x >> 1` is always equivalent to `x / 2` | Negative numbers follow different rules | Keep `/` if truncation toward 0 is needed |
| `value /= 2` never loses information | Integer division and compound conversion can reduce values | Confirm business logic first |
| Grouping with `size = 0` | Zero divisor | Validate `size > 0` |

**Debugging tip:** always ask **what types are the operands → what kind of division is it → what are the signs of the numbers → at which step is the fractional part lost → could the divisor be 0 → could the quotient exceed the range?**

## 16. Exercises with Answers

### Exercise A — Negative Numbers and Remainder

~~~java
System.out.println(-11 / 4);
System.out.println(-11 % 4);
~~~

**Answer:**

~~~text
-2
-3
~~~

Quotient -2 because -2.75 truncates toward 0; remainder -3 because `-11 = (-2)*4 + (-3)`.

### Exercise B — Integer Division vs. Floating-Point Division

~~~java
int a = 9, b = 4;
double x = a / b;
double y = ((double) a) / b;
System.out.println(x);
System.out.println(y);
~~~

**Answer:**

~~~text
2.0
2.25
~~~

### Exercise C — Checking `floorDiv`

~~~java
System.out.println(-11 / 4);
System.out.println(Math.floorDiv(-11, 4));
System.out.println(Math.floorMod(-11, 4));
~~~

**Answer:**

~~~text
-2
-3
1
~~~

Because `-11 = -3 * 4 + 1`.

### Exercise D — Expression Type

~~~java
short a = 9;
short b = 2;
var q = a / b;
System.out.println(q);
~~~

**Answer:** prints `4`, and `q` has type **int**, not short.

### Exercise E — Division by 0

~~~java
int denominator = 0;
// int result = 9 / denominator;
~~~

**Answer:** if the commented line runs, `ArithmeticException` occurs during integer division. You must validate the divisor beforehand; there is no `int` infinity.

### Exercise F — Overflow at the Boundary

~~~java
int a = Integer.MIN_VALUE;
int result = a / -1;
System.out.println(result);
~~~

**Answer:** `-2147483648`, no exception thrown. If you want the exact quotient, use `((long) a) / -1` to get `2147483648`.

### Exercise G — Splitting into Groups

There are 14 items and each box holds at most 6 items. Compute the number of full boxes, the remaining items, and the number of boxes needed (non-negative data, positive capacity).

**Answer:**

~~~java
int items = 14, capacity = 6;
int full = items / capacity;  // 2
int rest = items % capacity;  // 2
int boxes = full + (rest == 0 ? 0 : 1); // 3
~~~

## 17. Checklist and Conclusion

- [ ] Know that dividing two integers returns an integer quotient, truncating the fractional part **toward 0**.
- [ ] Distinguish truncation toward 0 from `Math.floorDiv` on negative numbers.
- [ ] Know the sign of the quotient and why `-1 / 2 == 0`.
- [ ] Understand that `int / int` happens before assignment to `double`.
- [ ] Know how to convert one operand to `double` before dividing when a floating-point number is needed.
- [ ] Know that `byte`/`short`/`char` are promoted to `int` in division.
- [ ] Remember the `%` remainder rule and the quotient–remainder relationship.
- [ ] Distinguish `Math.floorMod` from `%` on negative data.
- [ ] Know that parentheses change the result when grouping multiple integer divisions.
- [ ] Check that the divisor is non-zero before integer division if proactive handling is needed.
- [ ] Understand the `Integer.MIN_VALUE / -1` and `Long.MIN_VALUE / -1L` cases.
- [ ] Do not replace `/2` with right shift `>>1` if negative numbers are possible.
- [ ] Know that `/=` can perform division and convert to the target variable's type.
- [ ] Run `IntegerDivisionDemo.java` with Java 17+ and compare each line against expected output.

**Conclusion:** The `/` operator on integer types in Java 17+ **truncates the quotient toward 0**, even when an operand is negative. To round down, use `Math.floorDiv`; to keep the fractional part, choose a floating-point operand before dividing. Combining a solid grasp of `%`, expression types, division by 0, and the `MIN_VALUE / -1` overflow case will help you write integer division that is accurate, predictable, and safe for business requirements.