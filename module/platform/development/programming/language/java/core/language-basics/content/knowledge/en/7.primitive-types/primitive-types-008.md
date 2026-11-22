# Choosing Types Based on Data Range and Computational Requirements in Java

> **Java core — language-basics / Primitive Types**  
> **Requirements:** JDK 17+, no external libraries required for the main runnable example.  
> **Goal:** Choose types with sufficient value range, precision, and operations; avoid overflow, unintended integer division, and decimal rounding errors. When exactness beyond primitive type characteristics is needed, know when to switch to standard library types.

## 1. Do Not Choose a Type Just Because the Current Value Fits

A variable has a fixed declared type, yet **the results of future calculations** are what matter most. Before choosing, ask yourself:

1. Is the data **whole numbers, fractional numbers, true/false, or characters**?
2. What are the **minimum/maximum** bounds of the inputs and **intermediate results**?
3. Is **exact precision** required (e.g., monetary amounts), or is rounding error acceptable?
4. Do you need to store very large quantities in an **array/buffer** or interface with a binary format requiring a specific bit width?
5. When a result exceeds the range, must it **report an error**, or are overflow/rounding rules acceptable?

For example, the quantity of an order may only be a few hundred, but `quantity * priceInCents` can exceed the `int` range. Do not choose the result type based solely on the `quantity` variable.


## 2. Requirements-Based Decision Matrix

Instead of picking a type purely by bit count, explicitly state the **representation**, **computation**, and **data integration** requirements:

| Actual need | Initial choice | What must be verified |
| --- | --- | --- |
| Counts/integers in typical Java APIs | `int` | Could the largest sum/product exceed roughly ±2.1 billion? |
| Counts/sums larger than the `int` range | `long` | Are intermediates promoted to `long` yet; is `long` enough? |
| Byte data, 16-bit integer protocols | `byte`/`short` | Is the format signed or unsigned; how should interpretation/range checks work? |
| Measured values with tolerance | `double`, sometimes `float` | Are resolution and `NaN`/`Infinity` handling sufficient? |
| Money or exact decimal calculations | `long` in smallest units or `BigDecimal` | What are the scale, rounding, value range, and division rules? |
| True/false state | `boolean` | Is there a need to represent an undetermined state with `Boolean`? |
| Text/Unicode | `String`; `char` for code units | Do you need code units, code points, or displayed characters? |

This table is a way to bring **problem constraints** into the decision. Earlier lessons explained the structure and limits of each primitive; the next section examines the consequences of choosing the wrong operand type.

## 3. Choosing `int` or `long`: Consider Intermediate Calculations Too

Decimal integer literals default to `int`. Use the `L` suffix when a `long` literal is needed:

~~~java
int count = 12_000;
long customers = 3_000_000_000L;
// long wrong = 3_000_000_000; // Wrong: literal is already too large for int.
~~~

More importantly, **the type of the receiving variable does not automatically promote the operands before calculation**:

~~~java
int side = 50_000;
long wrongArea = side * side;        // int multiplication already overflowed before assigning to long.
long correctArea = (long) side * side; // At least one long operand -> long multiplication.
~~~

The true value is `2_500_000_000`, which exceeds `Integer.MAX_VALUE`. `wrongArea` receives `-1_794_967_296`: converting an already overflowed `int` result to `long` cannot recover the lost information.

If you want to **detect overflow**, you can use `Math.multiplyExact`, `Math.addExact`, or `Math.subtractExact`; those methods throw `ArithmeticException` when exceeding the `int`/`long` range respectively. Simply casting to `long` solves the case where `int` is too narrow, and **does not** guarantee every `long` multiplication is safe.

## 4. Choosing Types Based on How Operations Are Executed

### Integer Division Differs from Floating-Point Division

~~~java
int whole = 7 / 4;          // 1: division of two ints, fractional part is discarded.
double stillWhole = 7 / 4;  // 1.0: int division executes before assignment.
double fraction = 7.0 / 4;  // 1.75: has a double operand.
~~~

Do not expect the `double` type of the **target variable** to fix integer division on the right-hand side. At least one operand must be `double` before the operation if a fractional result is desired.

### `float` and `double` Are Both Approximate Floating-Point Numbers

`float` saves space compared to `double` but has fewer bits of precision. Even `double` **does not represent every decimal number exactly**, for example the result of `0.1 + 0.2` does not equal the literal `0.3` under the `==` comparison.

When handling **currency/decimals requiring exactness**:

- Use **`long` holding the smallest unit** (e.g., cents) if the value range is sufficient, rounding/division rules are clearly defined, and operations are checked for overflow.
- Or use **`BigDecimal`** in `java.math`: this is a **reference type**, not a primitive. Initialize from a string such as `new BigDecimal("0.1")` to represent the exact desired decimal value; avoid `new BigDecimal(0.1)` when you want exact decimal 0.1.
- When decimal division is non-terminating (such as `1 / 3`), `BigDecimal.divide` requires specifying an appropriate precision/rounding mode.

Do not use `float` just because the current value is "small"; **precision** is different from **representable magnitude range**.

## 5. Runnable Java 17+ Program

Create the file **TypeChoiceDemo.java**:

~~~java
import java.math.BigDecimal;

public final class TypeChoiceDemo {
    public static void main(String[] args) {
        int units = 1_200;
        long centsPerUnit = 2_499L;
        long totalCents = units * centsPerUnit;

        int side = 50_000;
        long wrongArea = side * side;
        long correctArea = (long) side * side;

        int integerDivide = 7 / 4;
        double floatingDivide = 7.0 / 4;

        float roundedFloat = 16_777_217f;
        double approximate = 0.1 + 0.2;
        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        boolean qualifies = totalCents >= 3_000_000L;
        char grade = 'A';

        System.out.println("totalCents=" + totalCents);
        System.out.println("intArea=" + wrongArea);
        System.out.println("longArea=" + correctArea);

        try {
            Math.multiplyExact(side, side);
        } catch (ArithmeticException ex) {
            System.out.println("checked=overflow");
        }

        System.out.println("integerDivide=" + integerDivide);
        System.out.println("floatingDivide=" + floatingDivide);
        System.out.println("floatRounded=" + (long) roundedFloat);
        System.out.println("doubleEquals0.3=" + (approximate == 0.3));
        System.out.println("exactDecimal=" + exact.toPlainString());
        System.out.println("qualifies=" + qualifies + ",grade=" + grade);
    }
}
~~~

Use the terminal in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 TypeChoiceDemo.java
java TypeChoiceDemo
~~~

**Exact expected output:**

~~~text
totalCents=2998800
intArea=-1794967296
longArea=2500000000
checked=overflow
integerDivide=1
floatingDivide=1.75
floatRounded=16777216
doubleEquals0.3=false
exactDecimal=0.3
qualifies=false,grade=A
~~~

Explanation: `units * centsPerUnit` uses `long` multiplication because one operand is `long`; the result is 2,998,800 cents. `side * side` runs in `int` and overflows; casting `side` to `long` **before multiplication** gives 2,500,000,000. `Math.multiplyExact` reports overflow via an exception. `7 / 4` discards the fractional part; `7.0 / 4` is `double` division. The value 16,777,217 is not represented exactly by 32-bit `float` and rounds to 16,777,216. `BigDecimal` created from strings produces the exact decimal result `0.3`.

## 6. Type Conversions: When Can Data Be Lost?

| Situation | Example | What to note |
| --- | --- | --- |
| Integer widening | `int x = 100; long y = x;` | Preserves value |
| Large integer to floating-point | `long x = 9_007_199_254_740_993L; double y = x;` | Can **lose precision** |
| Integer narrowing | `int x = 130; byte y = (byte) x;` | `y == -126` due to keeping low 8 bits |
| Floating-point to integer | `int n = (int) 3.9;` | `n == 3`, fractional part truncated |
| Checked `long` to `int` | `int n = Math.toIntExact(big);` | Throws exception if it does not fit in `int` |

Operands of type `byte`, `short`, and `char` in ordinary addition/multiplication are promoted to `int`, so for example `byte a = 10, b = 20;` followed by `byte c = a + b;` **is invalid** without an appropriate conversion/cast.

## 7. Practical Selection Checklist

1. **General counts/indices/integers:** choose `int`; if overflow is anticipated, choose `long` and widen **before** the operation that could overflow.
2. **Measured/approximate real-number data:** prefer `double`; choose `float` only when there are memory, format, or API interface reasons.
3. **Money or values needing accuracy to decimal places:** consider `long` in smallest units or `BigDecimal` with clear rounding rules.
4. **Boolean flags:** `boolean`, do not use `0`/`1` as substitutes.
5. **Character code units:** `char`; if full Unicode code points are needed, use the corresponding String APIs.
6. **Intermediate division, multiplication, addition:** inspect **operand types**, not only the target variable type; test boundary values and overflow cases.
7. **Values beyond `long`:** consider `BigInteger` if very large exact integers are needed.

### Practice

**Exercise 1.** Choose types for (a) login count; (b) total cents of a very large transaction; (c) approximate measured weight; (d) paid flag. State the range and precision constraints before deciding.

**Exercise 2.** Explain why `long x = 50_000 * 50_000;` can be wrong, then fix it **without** changing the meaning of the multiplication.

**Exercise 3.** Try `double d = 5 / 2;` and `double d = 5.0 / 2;` in two independent cases. Predict `println`.

**Exercise 4.** Change `centsPerUnit` to `3_000_000L` in the program; predict the total and evaluate whether `int` would still suffice as the **result type**.

**Summary:** Choose primitives based on **data range + precision + operations**, not merely the magnitude of the initial value. In particular, `int` overflow and integer division occur **before assignment**; and `float`/`double` are not solutions for strictly exact decimal arithmetic.
