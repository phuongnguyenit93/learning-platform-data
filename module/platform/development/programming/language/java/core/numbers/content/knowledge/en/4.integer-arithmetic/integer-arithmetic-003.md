# The `%` Operator and Remainder Sign in Java

In Java, `%` is the **remainder operator**. For integer operations, it is paired with `/` division that **truncates the quotient toward zero** (*truncation toward zero*). Consequently, the remainder can be **negative** when the dividend is negative. For instance:

```java
System.out.println(7 % 3);     //  1
System.out.println(-7 % 3);    // -1
System.out.println(7 % -3);    //  1
System.out.println(-7 % -3);   // -1
```

These lines are illustrative code snippets placed inside `main`. The key point to remember: for Java integers, **a non-zero remainder has the same sign as the dividend (the left-hand operand)**, not necessarily the same sign as the divisor on the right. If you want a **non-negative** result for a cycle of positive size, you should generally use `Math.floorMod(x, modulus)`.

This lesson belongs to the **Integer Arithmetic** section of the **Java core – numbers** module. The content progresses from the mechanics of `/` and `%` to bugs with negative numbers, how to use `Math.floorMod`, real-world scenarios, and boundary testing.

## 1. How Is the Remainder Determined?

Given two integers `a` and `b` with `b != 0`. In Java integer arithmetic:

- `q = a / b`: the integer quotient computed by division that **truncates the fractional part toward zero**.
- `r = a % b`: the remainder accompanying that division.
- The corresponding mathematical identity is `a = q × b + r`. In Java code with fixed-width integers, manually computing `q * b + r` must also account for overflow in the intermediate expression.

Example with two positive numbers:

```text
7 / 3 = 2
7 % 3 = 1

7 = 2 × 3 + 1
```

With a negative dividend:

```text
-7 / 3 = -2      (truncates the fractional part of -2.333... toward 0)
-7 % 3 = -1

-7 = (-2) × 3 + (-1)
```

If the quotient is taken using **floor** division, the result differs from Java integer division when the mathematical quotient is negative and non-integer:

```text
floor(-7 / 3) = -3
-7 = (-3) × 3 + 2
```

That is why the `%` operator and `Math.floorMod` can produce **two different results**.

### Exact Sign Rules

For integers and a non-zero divisor:

1. The remainder is `0` or has the same sign as the **dividend**.
2. The absolute value of the remainder is **strictly less than the absolute value of the divisor** mathematically.
3. Flipping the sign of the divisor **does not change the remainder** if the dividend stays the same and within the same representable range.

The second rule does not require calling `Math.abs` in code: `Math.abs(Integer.MIN_VALUE)` remains negative because the corresponding positive value is not representable in `int`. This is why the condition should be stated in terms of **mathematical magnitude**, rather than using an arbitrary test expression `Math.abs(r) < Math.abs(b)` for all inputs.

## 2. The Four Sign Combinations You Must Understand

| Dividend `a` | Divisor `b` | `a / b` | `a % b` | Check `a = q × b + r` |
| ---: | ---: | ---: | ---: | --- |
| `7` | `3` | `2` | `1` | `7 = 2 × 3 + 1` |
| `-7` | `3` | `-2` | `-1` | `-7 = -2 × 3 - 1` |
| `7` | `-3` | `-2` | `1` | `7 = (-2) × (-3) + 1` |
| `-7` | `-3` | `2` | `-1` | `-7 = 2 × (-3) - 1` |

A negative divisor **does not pull the remainder's sign negative**. Look at the left-hand operand: `7 % -3 == 1`; `-7 % -3 == -1`.

For exact divisibility, the remainder is `0` regardless of sign:

```java
12 % 3     // 0
-12 % 3    // 0
12 % -3    // 0
-12 % -3   // 0
```

Therefore, `n % d == 0` remains a valid divisibility check for negative integers and negative divisors, provided `d != 0`.

## 3. Why Doesn't `%` Always Return a Positive Result?

Many mathematical texts define **modulo by a positive modulus** so that the result lies in `0, 1, ..., m-1` for `m > 0`. That convention is very convenient for discrete mathematics and circular indexing. However, Java defines `%` for integers based on **division truncated toward zero**, so:

```java
int remainder = -1 % 5;  // -1; NOT 4
```

In arithmetic modulo 5, `-1` and `4` belong to the same congruence class. However, "congruence" is a mathematical relation, whereas `%` in Java returns **one specific representative** according to the remainder rule. To obtain the non-negative representative when the modulus is positive, choose `Math.floorMod`.

Do not mix up the two concepts:

| Need | Java expression | Result for `-7` and `3` |
| --- | --- | --- |
| Remainder of integer division truncated toward 0 | `-7 % 3` | `-1` |
| Remainder of floor integer division | `Math.floorMod(-7, 3)` | `2` |
| Quotient of integer division truncated toward 0 | `-7 / 3` | `-2` |
| Quotient of floor integer division | `Math.floorDiv(-7, 3)` | `-3` |

Neither operation is "wrong"; they follow **two different conventions**. Bugs occur when an algorithm requires a result in a non-negative range, yet the author uses `%` on a number that can be negative.

## 4. Math.floorMod: The Choice for Circular Indices and Positive Moduli

Java provides `Math.floorMod(int x, int y)` and `Math.floorMod(long x, long y)`, along with several other overloads. This method pairs with `Math.floorDiv` using **floor** division rather than truncation toward zero:

```java
Math.floorDiv(-7, 3); // -3
Math.floorMod(-7, 3); //  2

Math.floorDiv(7, 3);  //  2
Math.floorMod(7, 3);  //  1
```

With a **positive modulus** `m > 0`, `Math.floorMod(x, m)` always returns an integer in the range **from `0` to `m - 1`**, even when `x` is negative.

| `x` | `m` | `x % m` | `Math.floorMod(x, m)` |
| ---: | ---: | ---: | ---: |
| `8` | `5` | `3` | `3` |
| `-1` | `5` | `-1` | `4` |
| `-8` | `5` | `-3` | `2` |
| `-10` | `5` | `0` | `0` |
| `-11` | `5` | `-1` | `4` |

**Note on negative divisors:** `Math.floorMod` **does not guarantee a non-negative return value** if `m` is negative. A non-zero remainder under floor division has the same sign as the **divisor**. For example:

```java
7 % -3;                //  1
Math.floorMod(7, -3);  // -2
Math.floorDiv(7, -3);  // -3
```

Therefore, when using `floorMod` to generate an index `0..n-1`, **ensure `n > 0`**. For an empty list or array, `n = 0` is an indexing design error, not a case `floorMod` can handle.

### Avoid Writing Unsafe Normalization Formulas Yourself

A common trick is:

```java
int normalized = (x % m + m) % m;
```

If `m > 0` and operations occur in fixed-width integer types, **the expression `x % m + m` can overflow** when `x % m` is already positive. For example, with `x = 2_147_483_646` and `m = 2_147_483_647`, the intermediate addition `2_147_483_646 + 2_147_483_647` overflows `int`, potentially producing an incorrect result.

Use:

```java
int normalized = Math.floorMod(x, m);
```

When `m > 0`, this directly expresses the desired rule and avoids the overflow-prone addition in the homemade formula.

## 5. Real-World Scenario: Circular Buffer Indexing

Suppose a circular buffer has `capacity = 5`, and the algorithm steps backward one position from index `0`. The desired result is index `4`.

The following code is **wrong** when `currentIndex == 0`:

```java
int capacity = 5;
int currentIndex = 0;
int previousIndex = (currentIndex - 1) % capacity; // -1
// buffer[previousIndex] will cause ArrayIndexOutOfBoundsException.
```

Using `Math.floorMod`:

```java
int capacity = 5;
int currentIndex = 0;
int previousIndex = Math.floorMod(currentIndex - 1, capacity); // 4
```

This rule is useful for cyclic schedules, wrap-around positions, and negative step counts. However, two things must be considered:

- **The size must be positive:** `capacity > 0`. You cannot take a remainder with `0`.
- **The input expression can also overflow:** if `currentIndex` or `offset` can be very large, `currentIndex + offset` can overflow **before** calling `floorMod`. You can promote the addition to `long` when guaranteed safe within range, or design an overflow-safe modular addition.

Example with an `int` index, `int` offset, and a validated positive capacity:

```java
static int wrappedIndex(int current, int offset, int capacity) {
    if (capacity <= 0) {
        throw new IllegalArgumentException("capacity must be positive");
    }
    long position = (long) current + offset;
    return (int) Math.floorMod(position, (long) capacity);
}
```

This is an illustrative method to be placed inside a class. Since the sum of two `int`s always fits in `long`, the addition here does not overflow. The remainder lies in `0..capacity-1`, so casting the result back to `int` is safe. If the API specifies that `current` must lie in `0..capacity-1`, you should still validate that condition separately.

## 6. Real-World Scenario: Parity and Divisibility Checks

A common check is:

```java
boolean isEven = value % 2 == 0;
boolean isOdd = value % 2 != 0;
```

Both are correct for negative and positive `int`s. **Do not write `value % 2 == 1` as a general odd-number check:** `-3 % 2` equals `-1`, so `-3 % 2 == 1` is `false` even though `-3` is odd.

For example:

| `value` | `value % 2` | `value % 2 != 0` |
| ---: | ---: | --- |
| `4` | `0` | `false` |
| `5` | `1` | `true` |
| `-4` | `0` | `false` |
| `-5` | `-1` | `true` |

If a system only accepts non-negative integers, validating the input beforehand is a reasonable option. However, **the correct odd-number check for all integers** is `value % 2 != 0`, without needing to exclude negative numbers just to protect the check.

### Extracting the Last Digit of a Negative Integer

`-123 % 10` equals `-3`, so `value % 10` does not automatically yield a digit in `0..9` if `value` can be negative. When a positive base-10 remainder is needed for modular arithmetic algorithms, `Math.floorMod(value, 10)` yields `7` for `-123`; **that is not the digit `3` of the absolute value**.

If the goal is the units digit of the **absolute magnitude**, state that intent clearly and handle `Integer.MIN_VALUE` carefully; do not apply `Math.abs(value)` unconditionally. You can widen to `long` first and then take the magnitude:

```java
int value = Integer.MIN_VALUE;
long magnitude = Math.abs((long) value);
long lastDigit = magnitude % 10; // 8
```

The right computation depends on whether the question asks for "the digit of the absolute value" or "the non-negative modular representative".

## 7. Division by Zero and Boundary Values

For integers, both `a / 0` and `a % 0` cause `ArithmeticException` when evaluated. Do not use `%` as a safe check if the divisor comes from unvalidated input.

```java
static boolean divisibleBy(int value, int divisor) {
    if (divisor == 0) {
        throw new IllegalArgumentException("divisor must not be zero");
    }
    return value % divisor == 0;
}
```

This method handles negative divisors, negative dividends, and even the case `Integer.MIN_VALUE % -1 == 0`.

### Special Case: Integer.MIN_VALUE / -1

This is an important boundary case because `Integer.MIN_VALUE = -2_147_483_648` and the positive value `2_147_483_648` cannot be represented as an `int`.

```java
int x = Integer.MIN_VALUE;
int quotient = x / -1;  // Integer.MIN_VALUE, mathematical quotient overflows int
int remainder = x % -1; // 0
```

Java's rules allow the quotient in ordinary integer division to overflow in this special case, yet **the remainder is still `0`**. Do not infer that every integer division throws an exception on overflow. If you need the exact mathematical quotient, widen an operand before dividing:

```java
long quotient = (long) Integer.MIN_VALUE / -1; // 2147483648L
```

When verifying the identity `a == (a / b) * b + a % b` in `int` code, watch out for overflow in the multiplication/quotient. The identity is a tool for reasoning about arithmetic, but test expressions must also be designed to fit the representable range.

## 8. Type of a `%` Expression and Type Conversion Rules

With primitive operands, the `%` operator applies **binary numeric promotion**:

- `byte`, `short`, and `char` are generally promoted to `int` before computing.
- If one operand has type `long`, the integer expression is generally promoted to `long`.
- The result has the post-promotion type; it does not automatically shrink back to a variable's original type.

For example:

```java
byte small = -7;
int remainder = small % 3; // -1, expression type is int
// byte invalid = small % 3; // Does not compile: int expression to byte.
long large = -7L;
long longRemainder = large % 3; // -1L
```

The `%` operator is also defined in Java for `float`/`double`, but floating-point remainder also involves `NaN`, infinity, and signed zero cases. **This lesson focuses on integer remainder**; do not apply conclusions about integer division-by-zero errors to `double` or assume floating-point `%` follows the same exception-handling rules.

## 9. BigInteger: `remainder` and `mod` Follow Two Different Conventions

When integers exceed the `long` range, `java.math.BigInteger` provides two methods that must be distinguished:

- `remainder(divisor)`: remainder under division truncated toward zero, matching the sign behavior of `%` with negative integers.
- `mod(modulus)`: chooses the **non-negative** modular representative, but **requires a positive modulus**; a zero or negative modulus throws `ArithmeticException`.

```java
BigInteger negative = new BigInteger("-7");
BigInteger three = BigInteger.valueOf(3);

BigInteger remainder = negative.remainder(three); // -1
BigInteger modulo = negative.mod(three);          //  2
```

This snippet requires `import java.math.BigInteger;`. `BigInteger` is immutable and does not support the `%` operator directly between two `BigInteger` objects; use the methods instead. With `BigInteger`, also explicitly check for a zero divisor and enforce resource limits on large inputs.

The distinction between `BigInteger.remainder` and `BigInteger.mod` shows why documenting "remainder" versus "non-negative modulo" in API docs is important, especially when porting algorithms from `int` to arbitrary-precision integer types.

## 10. Standalone Runnable Java 17+ Program

Save the following code as **`RemainderSignDemo.java`**. The program prints results for all four sign combinations, compares `%` with `Math.floorMod`, checks negative parity, demonstrates circular indexing, the `Integer.MIN_VALUE` edge case, and `BigInteger`.

```java
import java.math.BigInteger;

public class RemainderSignDemo {
    public static void main(String[] args) {
        int[][] pairs = {
            {7, 3},
            {-7, 3},
            {7, -3},
            {-7, -3}
        };

        for (int[] pair : pairs) {
            int a = pair[0];
            int b = pair[1];
            System.out.printf(
                    "%d / %d = %d, %% = %d, floorDiv = %d, floorMod = %d%n",
                    a, b, a / b, a % b,
                    Math.floorDiv(a, b), Math.floorMod(a, b));
        }

        System.out.println("wrapped-index=" + Math.floorMod(-1, 5));
        System.out.println("odd-negative=" + (-5 % 2 != 0));
        System.out.println("negative-remainder=" + (-123 % 10));
        System.out.println("divisible-negative=" + (-12 % 3 == 0));
        System.out.println(
                "min-divisor-remainder=" + (Integer.MIN_VALUE % -1));

        BigInteger minusSeven = new BigInteger("-7");
        BigInteger three = BigInteger.valueOf(3);
        System.out.println(
                "big-remainder=" + minusSeven.remainder(three));
        System.out.println("big-mod=" + minusSeven.mod(three));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac RemainderSignDemo.java
java RemainderSignDemo
```

Exact stdout:

```text
7 / 3 = 2, % = 1, floorDiv = 2, floorMod = 1
-7 / 3 = -2, % = -1, floorDiv = -3, floorMod = 2
7 / -3 = -2, % = 1, floorDiv = -3, floorMod = -2
-7 / -3 = 2, % = -1, floorDiv = 2, floorMod = -1
wrapped-index=4
odd-negative=true
negative-remainder=-3
divisible-negative=true
min-divisor-remainder=0
big-remainder=-1
big-mod=2
```

On the second line, `-7 / 3` truncates the quotient toward `0`, giving `-2` and remainder `-1`; `floorDiv(-7,3)` is `-3`, so `floorMod` is `2`. On the third line, a negative divisor causes `floorMod(7,-3)` to be `-2`, proving you cannot assume it is always non-negative. The last two lines show that `BigInteger.remainder` and `BigInteger.mod` follow two different conventions.

## 11. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `a % b` is always non-negative | The sign of a non-zero integer remainder follows `a` | Use `Math.floorMod(a, b)` when `b > 0` and range `0..b-1` is required |
| Checking oddness with `n % 2 == 1` | Negative odd numbers give remainder `-1` | Use `n % 2 != 0` |
| Using `(index - 1) % length` to index an array | At index 0, this produces `-1` | Check `length > 0` and use `Math.floorMod` |
| Assuming `(x % m + m) % m` is always safe | Can overflow at the addition step | Use `Math.floorMod(x, m)` |
| Thinking flipping the divisor's sign flips the remainder's sign | For `%`, the sign depends on the dividend | Write out the four sign combinations table to verify |
| Calling `Math.floorMod(x, negativeM)` and assuming non-negative | When the divisor is negative, a non-zero result is also negative | Validate a positive modulus before using it as an index |
| Ignoring zero divisors | Integer `%` with a zero divisor throws `ArithmeticException` | Validate divisor or size before the operation |
| Using `Math.abs(x)` without boundary checks | `Math.abs(Integer.MIN_VALUE)` stays negative | Widen to `long` before taking absolute value when needed |
| Expecting `BigInteger.remainder` to always be positive | The method returns remainder under truncation toward zero | Use `BigInteger.mod` with a positive modulus |
| Testing only with positive numbers | Fails to catch remainder sign bugs | Add negative dividends, negative divisors, zero, and boundary values |

### Note on Formula Transformations

For `m > 0`, it can be proved mathematically that `x` and `Math.floorMod(x,m)` are congruent modulo `m`. However, when optimizing expressions containing `+`, `-`, or `*` on `int`/`long`, you must still consider overflow **before** the modulo step. Not every identity of infinite-precision integer arithmetic preserves its meaning when evaluated in fixed-width integer types.

For example, an algorithm computing `(a + b) % m` in `int` can be wrong if `a + b` already overflowed. `Math.floorMod(a + b, m)` **cannot fix** an overflowed intermediate value either; you must widen the type or use a modular addition algorithm safe for the input range.

## 12. Self-Check Questions and Exercises

1. Without running Java, compute `11 % 4`, `-11 % 4`, `11 % -4`, `-11 % -4`. For each case, compute `/` and verify the quotient-remainder identity.
2. Why does `-17 % 5` equal `-2` while `Math.floorMod(-17, 5)` equals `3`? Explain using the difference between "truncate toward zero" and "floor".
3. An array of length 7 uses indices `0` to `6`. Write a function to get the element before and after when at index `0` or `6`. Test behavior with negative and positive offsets, and handle an empty array.
4. Write an `isOdd(int value)` function that works for `Integer.MIN_VALUE`, `0`, and negative numbers. Why is `value % 2 == 1` insufficient?
5. Compare the results of `Math.floorMod(7, -3)` and `7 % -3`. Why should an algorithm requiring a non-negative remainder enforce a positive divisor?
6. Design tests for a parser receiving `divisor` from JSON or CLI, ensuring `%` is never executed with `0`. Would you handle the invalid input as an exception or a validation message?
7. For `BigInteger(-7)`, compare `remainder(3)`, `mod(3)`, and `mod(-3)`. Which method requires a positive modulus and why?
8. Test the formula `(x % m + m) % m` when `x = 2_147_483_646`, `m = 2_147_483_647`. Identify where overflow occurs and replace it with a `Math.floorMod` call.

## 13. Key Takeaways

- **Java integer `%` is the remainder of division truncated toward zero**, so when non-zero it has the same sign as the **dividend**.
- **`-7 % 3 == -1`**, whereas **`Math.floorMod(-7, 3) == 2`**. Choose according to the convention your algorithm requires.
- Use **`Math.floorMod(x, m)` with `m > 0`** when you want a circular index or modular representative in `0..m-1`; check that `m` is not zero.
- To check oddness for all integers, use **`n % 2 != 0`**; to check divisibility, use **`n % d == 0`** after ensuring `d != 0`.
- Modulo **does not prevent overflow** in input expressions, and `Math.floorMod` with a negative divisor does not guarantee a non-negative return value.
- For arbitrary-precision integers, `BigInteger.remainder` and `BigInteger.mod` represent two different conventions.

Understanding the **sign of the remainder** prevents subtle bugs in index calculations, cyclic handling, and integer algorithms. Choose the operation that matches your problem requirements before writing the expression.
