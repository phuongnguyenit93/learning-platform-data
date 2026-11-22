# Integer Overflow Does Not Automatically Throw an Exception in Java

> **Java core — language-basics / Arithmetic**  
> **Environment:** JDK 17+; using only the Java standard library.  
> **Objectives:** Recognize overflow in `int`/`long`, understand why calculations continue without **automatically throwing an exception**, and know how to choose `Math.*Exact`, timely type widening, or `BigInteger` so results are not silently lost.

## 1. What Is Integer Overflow?

`int` is a **32-bit signed** integer type, from **-2,147,483,648** to **2,147,483,647**. `long` is a **64-bit signed** integer type, from **-9,223,372,036,854,775,808** to **9,223,372,036,854,775,807**.

An addition, subtraction, or multiplication whose mathematical result exceeds the representable range will **overflow** (*integer overflow*).

~~~java
int max = Integer.MAX_VALUE; // 2147483647
int wrapped = max + 1;
System.out.println(wrapped); // -2147483648
~~~

Java **does not automatically throw `ArithmeticException` when addition, subtraction, or multiplication overflows `int`/`long`**. The remaining result bits are interpreted under signed integer representation, so the result can flip sign or differ wildly from the expected mathematical value.

- `int` uses 32 bits; overflowing integer operations wrap around **modulo `2^32`**.
- `long` uses 64 bits; similarly **modulo `2^64`**.
- This is behavior **specified by Java**, not random behavior or a memory bug.
- `float`/`double` follow different floating-point rules: they can produce `Infinity`/`NaN`. They are not a solution for preserving every integer value.

**Conclusion:** A program that runs successfully **does not prove the calculation is mathematically correct**.

## 2. Operations That Overflow Easily Yet Keep Running

| Expression | Mathematical Value | Actual `int` Result |
| --- | ---: | ---: |
| `Integer.MAX_VALUE + 1` | 2147483648 | -2147483648 |
| `Integer.MIN_VALUE - 1` | -2147483649 | 2147483647 |
| `50_000 * 50_000` | 2500000000 | -1794967296 |
| `-Integer.MIN_VALUE` | 2147483648 | -2147483648 |
| `Integer.MIN_VALUE / -1` | 2147483648 | -2147483648 |

The operation `Integer.MIN_VALUE / -1` is a **special case**: this integer division has a mathematical result exceeding `int`, yet Java still returns `Integer.MIN_VALUE` without **throwing an exception**. The remainder `Integer.MIN_VALUE % -1` equals **0**.

Similarly with `long`:

~~~java
long max = Long.MAX_VALUE;
System.out.println(max + 1L); // -9223372036854775808
~~~

Increment `++`, decrement `--`, or compound addition `+=` can also overflow when computing and storing into an integer type. For example, `int n = Integer.MAX_VALUE; n++;` causes `n` to become `Integer.MIN_VALUE`.

## 3. Converting to `long`: Must Be Done **Before** the Calculation

A common trap:

~~~java
int max = Integer.MAX_VALUE;

long wrong = max + 1;        // -2147483648, then widened to long.
long right = (long) max + 1; // 2147483648, addition performed in long.
~~~

In `long wrong = max + 1`, both operands have type `int`, so **`int` addition runs first**, overflows, and is then assigned to `long`. The target variable's type cannot rescue an operation that already happened.

Even casting after parentheses is too late:

~~~java
long wrongAgain = (long) (max + 1); // -2147483648
long rightAgain = ((long) max) + 1; // 2147483648
~~~

**For multiplication**, convert an operand before multiplying:

~~~java
int a = 50_000, b = 50_000;
long wrongProduct = a * b;         // -1794967296
long rightProduct = (long) a * b; // 2500000000
~~~

**Limit:** `long` can also overflow. Converting `int` to `long` only solves the issue when the result **fits within the `long` range**; no primitive integer type in Java expands infinitely on its own.

## 4. To Detect Overflow: Use `Math.*Exact` Operations

Java provides proactive **overflow-checking** APIs. When the result does not fit in the requested integer type's range, they throw **`ArithmeticException`**:

| Method | Role |
| --- | --- |
| `Math.addExact(a, b)` | Add, detect overflow |
| `Math.subtractExact(a, b)` | Subtract, detect overflow |
| `Math.multiplyExact(a, b)` | Multiply, detect overflow |
| `Math.incrementExact(a)` | Increment by 1, detect overflow |
| `Math.decrementExact(a)` | Decrement by 1, detect overflow |
| `Math.negateExact(a)` | Negate sign, detect minimum-value case |
| `Math.toIntExact(value)` | Convert `long` to `int`, check out-of-range |

Example:

~~~java
int a = Integer.MAX_VALUE;

try {
    int sum = Math.addExact(a, 1);
    System.out.println(sum);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
~~~

When a system requires **zero tolerance for off-by-even-one errors**, using checked arithmetic APIs makes more sense than silently accepting wrap-around arithmetic. Do not call `Math.addExact` on a result that **already overflowed earlier** hoping it can recover the original value: you must call the checking method **right at the calculation that risks overflowing**.

## 5. Division by 0 Is a Different Exception

Do not confuse **integer overflow** with **integer division by 0**:

~~~java
int a = 10;
int zero = 0;
// a / zero; // ArithmeticException at runtime.
// a % zero; // ArithmeticException at runtime.
~~~

- `int`/`long` division or remainder by **0** → `ArithmeticException`.
- `int`/`long` addition, subtraction, multiplication overflow → **does not throw automatically**.
- `Integer.MIN_VALUE / -1` → **overflows under a special rule without throwing**.
- `Math.addExact`/`multiplyExact`/`negateExact`... → **throws** if not exactly representable.

If the divisor can be 0, you must validate inputs. Choosing `Exact` APIs does not replace a divide-by-zero guard.

## 6. Standalone Runnable Java 17+ Program

Create the file **IntegerOverflowDemo.java**:

~~~java
import java.math.BigInteger;

public final class IntegerOverflowDemo {
    private static void checked(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=ok");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int min = Integer.MIN_VALUE;
        long maxLong = Long.MAX_VALUE;

        System.out.println("addWrap=" + (max + 1));
        System.out.println("subtractWrap=" + (min - 1));
        System.out.println("multiplyWrap=" + (50_000 * 50_000));
        System.out.println("longWrap=" + (maxLong + 1L));

        long lateWiden = max + 1;
        long earlyWiden = (long) max + 1;
        System.out.println("lateWiden=" + lateWiden);
        System.out.println("earlyWiden=" + earlyWiden);

        System.out.println("negateMinimum=" + (-min));
        System.out.println("minDivNegOne=" + (min / -1));
        System.out.println("minRemNegOne=" + (min % -1));

        checked("addExact", () -> Math.addExact(max, 1));
        checked("subtractExact", () -> Math.subtractExact(min, 1));
        checked("multiplyExact", () -> Math.multiplyExact(50_000, 50_000));
        checked("negateExact", () -> Math.negateExact(min));
        checked("toIntExact", () -> Math.toIntExact(2_147_483_648L));

        int zero = 0;
        checked("divideZero", () -> {
            int result = max / zero;
            System.out.println(result);
        });

        BigInteger exact = BigInteger.valueOf(maxLong).add(BigInteger.ONE);
        System.out.println("bigInteger=" + exact);
    }
}
~~~

Open a terminal in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 IntegerOverflowDemo.java
java IntegerOverflowDemo
~~~

**Exact expected output:**

~~~text
addWrap=-2147483648
subtractWrap=2147483647
multiplyWrap=-1794967296
longWrap=-9223372036854775808
lateWiden=-2147483648
earlyWiden=2147483648
negateMinimum=-2147483648
minDivNegOne=-2147483648
minRemNegOne=0
addExact=ArithmeticException
subtractExact=ArithmeticException
multiplyExact=ArithmeticException
negateExact=ArithmeticException
toIntExact=ArithmeticException
divideZero=ArithmeticException
bigInteger=9223372036854775808
~~~

The lines `addWrap`, `subtractWrap`, `multiplyWrap`, `longWrap`, and `minDivNegOne` **produce no exception**, even though the mathematical value does not fit in the target type. The `...Exact=ArithmeticException` lines show that an exception only appears when proactively using checked operations. `divideZero` is an **integer divide-by-zero** error, independent of overflow.

## 7. When Results Exceed Even `long`: Use `BigInteger`

`BigInteger` in `java.math` stores integers with magnitude not limited by 32/64-bit primitives (in practice limited only by memory):

~~~java
BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger y = x.add(BigInteger.ONE);
System.out.println(y); // 9223372036854775808
~~~

Operations on `BigInteger` use methods such as `add`, `subtract`, `multiply`. It **does not** support writing `x + y` like primitives.

If you still need to output `int`/`long`, check the range or use exact conversion methods like `intValueExact()`/`longValueExact()` so **digits are not silently lost**. Converting `BigInteger` to a primitive with plain `intValue()` can truncate significant bits.

## 8. Safe Practices and Exercises

| Requirement | Choice |
| --- | --- |
| Counting, small sums guaranteed to fit in `int` | Use `int` and control data domain |
| Result may exceed `int` but fits in `long` | Convert one operand to `long` **before computing** |
| Silent overflow must not occur | `Math.addExact`, `subtractExact`, `multiplyExact`, ... |
| May exceed even `long` | `BigInteger`, along with resource limit handling |
| Convert `long` to `int` while preserving exact value | `Math.toIntExact` |
| Dividing by a divisor that may be 0 | Guard input before `/` or `%` |

**Exercise 1.** Compute `Integer.MAX_VALUE + 1` and `Integer.MIN_VALUE - 1` in Java. Why doesn't the program stop?

**Exercise 2.** Compare `long x = 50_000 * 50_000;` with `long y = 50_000L * 50_000;`. Which one overflows? When does Java decide the type of the multiplication?

**Exercise 3.** Write `Math.multiplyExact(50_000, 50_000)` inside `try/catch`. Explain the difference from the `*` operator.

**Exercise 4.** Predict `Integer.MIN_VALUE / -1` and `Integer.MIN_VALUE % -1`. Why is this unlike the divide-by-zero case?

**Exercise 5.** Compute `Long.MAX_VALUE + 1` using `BigInteger` without losing the original integer value.

### Key Takeaways

**Java does not automatically throw an exception when ordinary `int`/`long` integer operations overflow.** Values can wrap around at bit limits and corrupt data while the program keeps running. If an exact result is needed, **widen an operand before computing** (when `long` has enough range), use **`Math.*Exact`** to detect overflow, or use **`BigInteger`** when exceeding `long` range. Integer division by 0 is a separate error: it **throws `ArithmeticException`**.