# `BigInteger`: `add`, `subtract`, `multiply`, `divide`, and `remainder`

`java.math.BigInteger` represents integers with **arbitrary precision**. When addition, subtraction, or multiplication exceeds the limits of `int` or `long`, `BigInteger` still keeps the exact integer result, provided enough memory and computation resources remain. It is an **integer** type, distinct from `BigDecimal` (decimal) and `double` (approximate floating-point).

| Method | Operation | Result |
|---|---|---|
| `a.add(b)` | `a + b` | Exact integer sum |
| `a.subtract(b)` | `a - b` | Exact integer difference |
| `a.multiply(b)` | `a × b` | Exact integer product |
| `a.divide(b)` | Integer division, quotient truncated toward 0 | `BigInteger` quotient |
| `a.remainder(b)` | Remainder corresponding to integer quotient | `BigInteger` remainder |

All five methods accept a `BigInteger` argument and return a `BigInteger`. `divide` and `remainder` reject a zero divisor. The most important identity when learning the last two operations is **`a = q × b + r`**, where `q = a.divide(b)`, `r = a.remainder(b)`, and `b != 0`.

## 1. Creating Values and Understanding Immutability

```java
import java.math.BigInteger;

BigInteger a = new BigInteger("12345678901234567890");
BigInteger b = BigInteger.valueOf(97);
BigInteger negative = new BigInteger("-17");
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
```

These are illustrative statements meant for use inside a method or JShell, not a standalone Java file yet.

- `new BigInteger("...")` parses an integer string, suitable even when the number exceeds the `long` range.
- `BigInteger.valueOf(long)` is used when the input already fits within the `long` range. Writing a literal larger than `long` and passing it to `valueOf` will not compile.
- `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` are convenient constants.
- The string `"12.34"` is not a valid integer for `new BigInteger(...)` and throws `NumberFormatException`.
- `BigInteger` is immutable: operation results do not mutate the original number. Do not infer that the result is always a new instance, as the library may reuse objects in some cases.

```java
BigInteger x = BigInteger.valueOf(100);
BigInteger y = BigInteger.valueOf(5);

x.add(y);                 // Computes 105 but discards the result.
System.out.println(x);    // 100
x = x.add(y);
System.out.println(x);    // 105
```

Java does not support `x + y`, `x - y`, `x * y`, `x / y`, or `x % y` when both variables are `BigInteger`: methods must be called. Two `BigInteger` objects compare values with `equals` or order with `compareTo`; `==` compares only references.

## 2. `add`: Integer Addition

```java
BigInteger large = new BigInteger("999999999999999999999");
BigInteger sum = large.add(BigInteger.ONE);
// sum = 1000000000000000000000
```

`add` adds accurately according to sign rules: `5 + (-8) = -3`, `(-5) + (-8) = -13`, and adding 0 preserves the numeric value. It does not overflow like `int`/`long` simply from exceeding a fixed-width limit.

Accumulation must reassign because the object is immutable:

```java
BigInteger total = BigInteger.ZERO;
for (int i = 1; i <= 100; i++) {
    total = total.add(BigInteger.valueOf(i));
}
// total has value 5050
```

If you only call `total.add(...)`, the value of `total` stays unchanged. To verify in Java, use `total.equals(BigInteger.valueOf(5050))`.

## 3. `subtract`: Signed Subtraction

```java
BigInteger a = BigInteger.valueOf(25);
BigInteger b = BigInteger.valueOf(40);

BigInteger difference = a.subtract(b); // -15
```

Subtraction returns the exact value `a - b`, even when negative. If you want **non-negative distance**, you can use `a.subtract(b).abs()`; if you need the **signed difference**, keep the result as is. Properties:

- `a.subtract(b)` equals `a.add(b.negate())` by value.
- `a.subtract(BigInteger.ZERO)` equals `a`.
- `a.subtract(a)` equals 0.
- `a.subtract(b).add(b)` returns `a`.

`BigInteger` does not enforce whether account balances, inventory, or scores can be negative. Such constraints belong to business logic.

## 4. `multiply`: Large Integer Multiplication

```java
BigInteger factor = new BigInteger("100000000000000000000");
BigInteger product = factor.multiply(BigInteger.valueOf(12));
// product = 1200000000000000000000
```

Multiplying two numbers with the same sign gives a positive result; opposite signs give a negative result; if either factor is 0, the product is 0. Given valid integer inputs, the mathematical result is exact with no rounding.

```java
BigInteger factorial = BigInteger.ONE;
for (int i = 2; i <= 6; i++) {
    factorial = factorial.multiply(BigInteger.valueOf(i));
}
// factorial = 720
```

A common mistake is writing `BigInteger.valueOf(x * y)` when `x` and `y` are `long`: the multiplication `x*y` is already computed in `long` **before** converting to `BigInteger` and can overflow. Use `BigInteger.valueOf(x).multiply(BigInteger.valueOf(y))`.

Even without a 64-bit limit, multiplying huge numbers still carries CPU/RAM cost. For inputs from external systems, bound number lengths according to application requirements.

## 5. `divide`: Integer Quotient, Truncated Toward 0

`a.divide(b)` does not return a fraction or decimal. It returns the integer quotient by **truncating the fractional part toward 0**, also called *truncation toward zero*.

| `a` | `b` | `a.divide(b)` | Explanation |
|---:|---:|---:|---|
| 17 | 5 | 3 | 17 / 5 = 3.4 |
| -17 | 5 | -3 | -17 / 5 = -3.4; truncated toward 0 |
| 17 | -5 | -3 | 17 / -5 = -3.4 |
| -17 | -5 | 3 | Two negative signs cancel |
| 15 | 5 | 3 | Exact division |
| 0 | 5 | 0 | Dividend is 0 |

**Do not confuse truncation toward 0 with floor division.** `BigInteger.valueOf(-17).divide(BigInteger.valueOf(5))` yields `-3`, not `-4`. For positive numbers, the two approaches sometimes give the same result, so testing only with positive numbers misses bugs.

```java
BigInteger numerator = BigInteger.valueOf(7);
BigInteger denominator = BigInteger.valueOf(2);
BigInteger quotient = numerator.divide(denominator);
// quotient = 3, not 3.5
```

If you want a decimal ratio, use `BigDecimal` with explicit precision, scale, and rounding rules, or represent a fraction using a numerator/denominator pair. `BigInteger` division does not automatically switch to `BigDecimal`.

### Division by 0

`a.divide(BigInteger.ZERO)` throws `ArithmeticException`. If the divisor comes from a user, check `b.signum() == 0` or `b.equals(BigInteger.ZERO)` and report an appropriate error. This integer division does not produce `Infinity` or `NaN` like some floating-point divisions.

## 6. `remainder`: Remainder of Integer Division

Let:

\[
q = a.divide(b),\qquad r = a.remainder(b),\qquad b \ne 0.
\]

Then:

\[
a = q \times b + r,\qquad |r| < |b|.
\]

In addition, `r == 0` or the remainder `r` has the **same sign as the dividend `a`**. The sign of the divisor does not determine the sign of the remainder.

| `a` | `b` | `divide` | `remainder` | Identity |
|---:|---:|---:|---:|---|
| 17 | 5 | 3 | 2 | `17 = 3*5+2` |
| -17 | 5 | -3 | -2 | `-17 = (-3)*5+(-2)` |
| 17 | -5 | -3 | 2 | `17 = (-3)*(-5)+2` |
| -17 | -5 | 3 | -2 | `-17 = 3*(-5)+(-2)` |
| 15 | 5 | 3 | 0 | `15 = 3*5` |
| 3 | 5 | 0 | 3 | `3 = 0*5+3` |

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);
BigInteger q = a.divide(b);     // -3
BigInteger r = a.remainder(b);  // -2
boolean valid = q.multiply(b).add(r).equals(a); // true
```

Therefore, **`remainder` can return a negative result** if the dividend is negative; it is not always non-negative like the remainder in modular arithmetic. `remainder(BigInteger.ZERO)` throws `ArithmeticException`.

### `remainder` Differs from `mod`

`BigInteger.mod(m)` is for a **positive** modulus and always returns a non-negative remainder in `[0, m)`. Meanwhile, `remainder(m)` allows a negative `m` as long as it is nonzero, and the remainder's sign follows the dividend:

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger m = BigInteger.valueOf(5);

a.remainder(m); // -2
a.mod(m);       // 3
```

Calling `a.mod(BigInteger.valueOf(-5))` or `a.mod(BigInteger.ZERO)` throws `ArithmeticException` because the modulus is non-positive. You must distinguish the two results when computing cyclic indices, wrap-around schedules, or congruences.

Important: `a.divide(b) * b + a.remainder(b) = a` holds by value, but you cannot replace `remainder` with `mod` and keep the same quotient in all cases. With `a=-17`, `b=5`, the quotient/remainder pair from `divide` and `remainder` is `(-3, -2)`; to use the modular remainder `3`, the corresponding quotient must be `-4`: `-17 = (-4)*5+3`.

## 7. `divideAndRemainder`: Getting Quotient and Remainder Simultaneously

If both values are needed for the same division, use:

```java
BigInteger a = new BigInteger("12345678901234567890");
BigInteger b = BigInteger.valueOf(97);

BigInteger[] qr = a.divideAndRemainder(b);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];
boolean valid = quotient.multiply(b).add(remainder).equals(a);
```

The array always contains **two elements**: `qr[0]` is the quotient equal to `divide(b)`, and `qr[1]` is the remainder equal to `remainder(b)`. When both are needed, this call is usually more efficient than performing two separate divisions. If `b` is 0, it also throws `ArithmeticException`.

Example splitting a **non-negative** duration into minutes and seconds:

```java
BigInteger seconds = BigInteger.valueOf(125);
BigInteger[] qr = seconds.divideAndRemainder(BigInteger.valueOf(60));
// qr[0] = 2 minutes; qr[1] = 5 seconds
```

For negative durations, you must design specific representation rules because the remainder can be negative.

## 8. Standalone Runnable Java 17+ Program

Save into file **`BigIntegerArithmeticDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerArithmeticDemo {
    public static void main(String[] args) {
        BigInteger a = new BigInteger("12345678901234567890");
        BigInteger b = BigInteger.valueOf(97);

        System.out.println("add: " + a.add(b));
        System.out.println("subtract: " + a.subtract(b));
        System.out.println("multiply: " + a.multiply(b));
        System.out.println("divide: " + a.divide(b));
        System.out.println("remainder: " + a.remainder(b));

        BigInteger[] pair = a.divideAndRemainder(b);
        System.out.println("q*r + remainder == a: "
                + pair[0].multiply(b).add(pair[1]).equals(a));
        System.out.println("a unchanged: " + a);

        BigInteger minus17 = BigInteger.valueOf(-17);
        BigInteger plus5 = BigInteger.valueOf(5);
        BigInteger minus5 = BigInteger.valueOf(-5);
        System.out.println("-17 / 5 = " + minus17.divide(plus5));
        System.out.println("-17 remainder 5 = " + minus17.remainder(plus5));
        System.out.println("-17 mod 5 = " + minus17.mod(plus5));
        System.out.println("17 / -5 = " + BigInteger.valueOf(17).divide(minus5));
        System.out.println("17 remainder -5 = "
                + BigInteger.valueOf(17).remainder(minus5));
        System.out.println("-17 / -5 = " + minus17.divide(minus5));
        System.out.println("-17 remainder -5 = " + minus17.remainder(minus5));

        try {
            a.divide(BigInteger.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("division by zero: ArithmeticException");
        }
        try {
            minus17.mod(minus5);
        } catch (ArithmeticException ex) {
            System.out.println("nonpositive modulus: ArithmeticException");
        }
    }
}
```

Compile/run commands with JDK 17+:

```bash
javac -encoding UTF-8 BigIntegerArithmeticDemo.java
java BigIntegerArithmeticDemo
```

Stdout verified by compiling and running Java:

```text
add: 12345678901234567987
subtract: 12345678901234567793
multiply: 1197530853419753085330
divide: 127275040218913071
remainder: 3
q*r + remainder == a: true
a unchanged: 12345678901234567890
-17 / 5 = -3
-17 remainder 5 = -2
-17 mod 5 = 3
17 / -5 = -3
17 remainder -5 = 2
-17 / -5 = 3
-17 remainder -5 = -2
division by zero: ArithmeticException
nonpositive modulus: ArithmeticException
```

The line `q*r + remainder == a: true` verifies the integer division equation. The line `a unchanged` demonstrates `BigInteger` immutability. The four sign combinations show truncation toward 0 for quotients and remainders matching the sign of the **dividend**. The two `try/catch` blocks demonstrate division by 0 and non-positive modulus errors without halting the program.

## 9. Testing Using Algebraic Properties

For `BigInteger` variables `a`, `b`, we can check:

```java
a.add(b).subtract(b).equals(a);               // true
a.subtract(b).add(b).equals(a);               // true
a.multiply(BigInteger.ONE).equals(a);         // true
a.multiply(BigInteger.ZERO).equals(BigInteger.ZERO); // true
```

If `b.signum() != 0`, call `BigInteger[] qr = a.divideAndRemainder(b);` and verify:

```java
qr[0].multiply(b).add(qr[1]).equals(a);
qr[1].abs().compareTo(b.abs()) < 0;
qr[1].signum() == 0 || qr[1].signum() == a.signum();
```

These are illustrative test expressions assuming the variables already exist. Use `compareTo` to compare large numbers without casting down to `long`. You should test exact division, non-exact division, negative numbers in both positions, 0, very large numbers, and division by 0.

## 10. Common Mistakes

1. **Using primitive operators:** `a + b` and `a % b` are invalid when `a`, `b` are `BigInteger`. Use `add`, `remainder`.
2. **Discarding the result:** `a.add(b)` does not modify `a`; use `a = a.add(b)` or a new variable.
3. **Overflowing before type conversion:** `BigInteger.valueOf(x * y)` can receive an already-overflowed `long` value. Convert each operand first, then call `multiply`.
4. **Misunderstanding `divide`:** `7/2` is `3` as a `BigInteger`, not `3.5`.
5. **Confusing rounding direction:** `-17 / 5` yields `-3`, not `-4`.
6. **Assuming remainder is always non-negative:** the `remainder` of `-17` by `5` is `-2`; `mod(5)` yields `3`.
7. **Ignoring zero divisor:** `divide`, `remainder`, and `divideAndRemainder` all throw `ArithmeticException`.
8. **Using `==` for value equality:** use `equals`; `==` checks reference identity.
9. **Narrowing to smaller types:** `longValue()` can drop high-order bits on large numbers; use `longValueExact()` to require exact conversion (throws `ArithmeticException` if impossible).
10. **Leaving input sizes unbounded:** arbitrary-length integers still carry CPU/RAM cost; applications need an appropriate size policy.

## 11. Exercises with Solutions

| Java expression | Result |
|---|---|
| `BigInteger.valueOf(8).add(BigInteger.valueOf(-3))` | `5` |
| `BigInteger.valueOf(8).subtract(BigInteger.valueOf(13))` | `-5` |
| `BigInteger.valueOf(-4).multiply(BigInteger.valueOf(-6))` | `24` |
| `BigInteger.valueOf(-23).divide(BigInteger.valueOf(7))` | `-3` |
| `BigInteger.valueOf(-23).remainder(BigInteger.valueOf(7))` | `-2` |
| `BigInteger.valueOf(-23).mod(BigInteger.valueOf(7))` | `5` |
| `BigInteger.ZERO.remainder(BigInteger.valueOf(17))` | `0` |
| `BigInteger.ONE.divide(BigInteger.ZERO)` | `ArithmeticException` |

Explanation of `-23`: `-23 = (-3)*7 + (-2)` with the quotient truncated toward 0. If choosing the non-negative modular remainder `5`, the corresponding quotient must be `-4` to give `-23 = (-4)*7 + 5`.

## Key Takeaway

`BigInteger` stores arbitrary-length integers whose values are **immutable**. `add`, `subtract`, and `multiply` yield exact integer results. `divide` returns an integer quotient truncated toward 0, `remainder` can be negative matching the dividend's sign, and the quotient–remainder pair satisfies `a = q*b + r` when `b != 0`. Use `mod(m)` when you want a non-negative remainder with `m > 0`. When needing both quotient and remainder, `divideAndRemainder` returns `[quotient, remainder]`. Always check for zero divisors and use `equals` to compare values.