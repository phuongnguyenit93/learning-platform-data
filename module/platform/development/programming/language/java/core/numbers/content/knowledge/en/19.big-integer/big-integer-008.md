# BigInteger: `mod`, `modPow`, `modInverse`, and Input Preconditions

## 1. Learn All Three Operations Properly — Not Just Method Names

In Java, `java.math.BigInteger` supports arbitrary-precision integers and three very important modular operations:

```java
BigInteger r = a.mod(m);
BigInteger p = a.modPow(exponent, m);
BigInteger inverse = a.modInverse(m);
```

They serve different problems:

- **`a.mod(m)`**: returns the **non-negative modular remainder** of `a` modulo `m`.
- **`a.modPow(e,m)`**: returns `a^e mod m`, implemented for large modular exponentiation **without building the full `a^e`**.
- **`a.modInverse(m)`**: finds `x` such that `a*x ≡ 1 (mod m)`, **if the inverse exists**.

The core of this **Java Core — Numbers / BigInteger** lesson is *input preconditions*. All three require **modulus `m > 0`**. `modInverse` also requires `gcd(a,m) = 1`; `modPow` allows **negative exponents** in Java, though in that case it also requires the base to be invertible modulo `m`.

Example:

```java
BigInteger a = BigInteger.valueOf(-13);
BigInteger m = BigInteger.valueOf(5);

System.out.println(a.remainder(m)); // -3
System.out.println(a.mod(m));       // 2
```

`remainder` can be negative; `mod` with a positive modulus always returns a value in `[0,m−1]`. This is a memorable difference in every cyclic algorithm, hash, congruence, or modular cryptography task.

**Goal:** read the Java 17 contract accurately, know how to check preconditions yourself, predict results/exceptions for negative/0/1 values, understand inverses and negative exponents, and use Java 17+ examples with verifiable outputs.

## 2. Preparation: Creating and Comparing `BigInteger`

`BigInteger` is an **immutable class**, not a primitive. Operations return a new `BigInteger` value or a reusable object; they **do not mutate the receiver**.

```java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(17);
BigInteger c = a.add(b);

System.out.println(a); // a unchanged
```

Code snippets must be placed in a class/method to run. For numbers within the `long` range, `BigInteger.valueOf(long)` is convenient; for very long numbers, use `new BigInteger(String)` to parse accurately from decimal. Do not pass an oversized `long` literal exceeding `Long.MAX_VALUE` hoping `BigInteger.valueOf` can fix it: the error already happens at the **literal or primitive calculation** before conversion.

Standard constants:

```java
BigInteger.ZERO
BigInteger.ONE
BigInteger.TWO   // available since Java 9
BigInteger.TEN
```

Ways to check:

- `m.signum() > 0`: `m` is positive.
- `m.compareTo(BigInteger.ZERO) > 0`: another way to check `m` is positive.
- `a.equals(b)`: compares the **values** of two `BigInteger`s.
- `a.gcd(m).equals(BigInteger.ONE)`: `a` and `m` are **coprime**.

**Do not use `a == b` to compare values of two `BigInteger` objects.** `==` between two references checks whether they are the same object, and will not satisfy equality for independently created values.

### 2.1. Method Signatures

```text
BigInteger mod(BigInteger m)
BigInteger modPow(BigInteger exponent, BigInteger m)
BigInteger modInverse(BigInteger m)

BigInteger remainder(BigInteger val)
BigInteger pow(int exponent)
BigInteger gcd(BigInteger val)
```

The lines above are **illustrative signatures**, not standalone Java source declarations. Note that `modPow` takes the exponent as **`BigInteger`**, whereas `pow` takes **`int`** and computes integer exponentiation *without* taking a modulus. Picking the wrong API can cause huge memory cost or exceptions on negative exponents.

## 3. Congruence and Residue Classes

Two integers `a` and `b` are called **congruent modulo `m`** if the difference `a−b` is divisible by `m`:

```text
a ≡ b (mod m)
⇔ there exists an integer k such that a - b = k*m.
```

Examples:

```text
-13 ≡ 2 (mod 5), because -13 - 2 = -15 = -3*5.
17 ≡ 2 (mod 5), because 17 - 2 = 15 = 3*5.
```

For `m > 0`, we pick a **canonical representative** in the range `0≤r<m`. `BigInteger.mod(m)` returns that canonical representative, whether `a` is positive, negative, or zero.

| `a` | `m` | `a.mod(m)` | Meaning |
| ---: | ---: | ---: | --- |
| 13 | 5 | 3 | 13 = 2×5+3 |
| −13 | 5 | 2 | −13 = −3×5+2 |
| 0 | 5 | 0 | Zero belongs to class 0 |
| 10 | 5 | 0 | Divisible |
| 5 | 5 | 0 | Representative of `m` is 0 |
| 5 | 1 | 0 | Only one class modulo 1 |

Distinguish **`a.mod(m)`** (computing a result) from **`a.equals(b)`** (comparing object values). A pair of numbers may be unequal under `equals` yet yield the same modulo result.

### 3.1. Why Must the Modulus Be Positive?

`BigInteger.mod(m)` defines its output in `0..m−1`. If `m=0`, the notion of residue classes modulo 0 does not fit the API contract. If `m<0`, the representative interval `[0,m−1]` has no meaning in the specified form.

Therefore, **`mod` throws `ArithmeticException` when `m≤0`**. Do not assume `mod(-5)` "automatically takes absolute value" to become `mod(5)`. If a domain genuinely defines negative moduli, you must design a `m.abs()` normalization policy *before* calling and explain its meaning clearly; never silently flip input signs.

## 4. `remainder` and `mod`: Source of Many Negative-Number Bugs

`BigInteger.remainder(m)` mirrors Java's integer `%` operator: the quotient is truncated toward 0 and the remainder can have the **same sign as the dividend** (or be 0). `BigInteger.mod(m)`, by contrast, always returns a **non-negative** result when `m>0`.

Example:

```java
BigInteger a = BigInteger.valueOf(-13);
BigInteger five = BigInteger.valueOf(5);

System.out.println(a.remainder(five)); // -3
System.out.println(a.mod(five));       // 2
```

Both results represent the same congruence class because `−3 ≡ 2 (mod 5)`. However, they are **not the same integer value** and can have different effects in code.

| Expression | Result | Note |
| --- | ---: | --- |
| `BigInteger.valueOf(-13).remainder(BigInteger.valueOf(5))` | −3 | Negative sign from dividend |
| `BigInteger.valueOf(-13).mod(BigInteger.valueOf(5))` | 2 | Non-negative normalization |
| `BigInteger.valueOf(13).remainder(BigInteger.valueOf(-5))` | 3 | `remainder` allows nonzero negative divisor |
| `BigInteger.valueOf(13).mod(BigInteger.valueOf(-5))` | Throws `ArithmeticException` | `mod` rejects negative modulus |
| `BigInteger.valueOf(13).remainder(BigInteger.ZERO)` | Throws `ArithmeticException` | Division by zero |

**Precondition:** `remainder` forbids only a zero divisor; `mod` forbids a **non-positive** modulus. Do not assume "`remainder` and `mod` are two names for the same method" just from a few positive examples.

### 4.1. Normalizing Remainder Manually

If you already have `r = a.remainder(m)` with `m>0`, you can turn it into the canonical representative:

```java
BigInteger r = a.remainder(m);
if (r.signum() < 0) {
    r = r.add(m);
}
```

With a positive modulus, `remainder` has magnitude strictly less than the modulus, so you only need to add `m` **once** when `r` is negative. Still, the **most direct and clearest way** remains `a.mod(m)`.

A formula sometimes seen in other languages is `((a % m) + m) % m`. It can normalize negative remainders, yet with `BigInteger` you should use `mod` to express the exact intent and avoid confusion with `remainder`.

## 5. Java Program A — Distinguishing Remainder and Modulo

Create file **`ModVsRemainder.java`**:

```java
import java.math.BigInteger;

public class ModVsRemainder {
    public static void main(String[] args) {
        BigInteger minus13 = BigInteger.valueOf(-13);
        BigInteger five = BigInteger.valueOf(5);

        System.out.println(minus13.remainder(five));
        System.out.println(minus13.mod(five));

        System.out.println(BigInteger.valueOf(13).mod(five));
        System.out.println(BigInteger.ZERO.mod(five));
        System.out.println(BigInteger.valueOf(10).mod(five));
        System.out.println(BigInteger.valueOf(99).mod(BigInteger.ONE));

        System.out.println(BigInteger.valueOf(13)
                .remainder(BigInteger.valueOf(-5)));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 ModVsRemainder.java
java ModVsRemainder
```

**Exact stdout:**

```text
-3
2
3
0
0
0
3
```

After running, verify each result satisfies `0≤a.mod(m)<m` for `m>0`. `mod(BigInteger.ONE)` always returns 0, regardless of the receiver's integer value.

## 6. `modPow(exponent,m)` — Modular Exponentiation

`a.modPow(e,m)` computes the canonical remainder of `a^e` modulo `m`. For `e≥0`, the mathematical meaning is:

```text
result = a^e mod m,  m > 0, e >= 0.
```

The output lies in `[0,m−1]`. Unlike `pow(int)`, this method **does not need to build the full number `a^e` first before dividing for the remainder**. This is vital when exponents are large.

Classic example:

```text
4^13 mod 497 = 445.
```

Java:

```java
BigInteger result = BigInteger.valueOf(4)
        .modPow(BigInteger.valueOf(13),
                BigInteger.valueOf(497));

System.out.println(result); // 445
```

The result `445` is always non-negative and smaller than `497`. The base `a` can be negative: `(−2)^5 mod 13 = 7`, because `−32 ≡ 7 (mod 13)`.

### 6.1. Repeated Squaring — Algorithmic Intuition

A fundamental method to compute `a^e mod m` for `e≥0` is **binary exponentiation** (repeated squaring):

1. Set `result = 1 mod m` and `base = a mod m`.
2. For each bit of `e` from least significant to most significant, if the current bit is 1, set `result = (result*base) mod m`.
3. Square `base = base*base mod m` and shift `e` right by one bit.
4. When `e` reaches 0, return `result`.

Multiplication is reduced modulo `m` after every step so intermediate values never explode to the giant size of `a^e`. The number of loop iterations is proportional to the **bit length of the exponent**, not the exponent's value. Actual cost also depends on the modulus bit length, big-integer multiplication algorithms, and the JDK implementation.

### 6.2. Illustrative Repeated Squaring Code (Not Replacing the Standard API)

```java
static BigInteger repeatedSquaring(
        BigInteger a, BigInteger e, BigInteger m) {
    if (m.signum() <= 0 || e.signum() < 0) {
        throw new IllegalArgumentException("Require m>0, e>=0");
    }

    BigInteger result = BigInteger.ONE.mod(m);
    BigInteger base = a.mod(m);
    BigInteger power = e;

    while (power.signum() > 0) {
        if (power.testBit(0)) {
            result = result.multiply(base).mod(m);
        }
        power = power.shiftRight(1);
        if (power.signum() > 0) {
            base = base.multiply(base).mod(m);
        }
    }
    return result;
}
```

This is an **illustrative method**, requiring `import java.math.BigInteger` and placement inside a class; it only accepts `e≥0`. The condition `m>0` must be checked **before** calling `ONE.mod(m)`. The bit operation `testBit(0)` checks the lowest bit, equivalent to testing whether the exponent is odd.

The illustrative function helps understand the algorithm; in ordinary Java applications, prefer `BigInteger.modPow`, which is optimized and widely tested. Do not use the illustrative version for sensitive cryptography: execution time can depend on exponent bits and leak sensitive data via side channels.

## 7. `modPow` and `pow` Are Not the Same

| Feature | `a.pow(int e)` | `a.modPow(BigInteger e, BigInteger m)` |
| --- | --- | --- |
| Result | Full integer `a^e` | Representative of `a^e` modulo `m` |
| Modulus | None | Requires `m>0` |
| Exponent type | `int` | `BigInteger` |
| Negative exponent | **Disallowed**, throws `ArithmeticException` | **Allowed if `a` is invertible modulo `m`** |
| Result size | Can be enormous | Bit length never exceeds representative under `m` |
| Use case | Ordinary integer exponentiation | Congruences / modular exponentiation |

Potentially confusing example:

```java
BigInteger a = BigInteger.valueOf(2);

System.out.println(a.pow(10)); // 1024
System.out.println(a.modPow(
        BigInteger.TEN, BigInteger.valueOf(17))); // 4
```

Because `1024 mod 17 = 4`. Yet for an exponent thousands of bits long, creating `a.pow(...)` before taking the modulus is usually infeasible, whereas `modPow` computes via modular exponentiation.

**Important note:** `BigInteger.pow(-1)` throws `ArithmeticException`. **Do not** infer from that that `BigInteger.modPow(BigInteger.valueOf(-1),m)` must also throw; the `modPow` API allows negative exponents whenever an inverse exists.

## 8. Input Preconditions of `modPow` — Including Negative Exponents

Java 17 contract:

- `m` must be **positive**; `m≤0` ⇒ `ArithmeticException`.
- `exponent` can be **negative, zero, or positive**.
- If `exponent<0`, the base must be **coprime to the modulus**, equivalent to `gcd(a,m)=1`. Otherwise, `ArithmeticException`.
- If `exponent≥0`, `gcd(a,m)=1` is **not required**. For instance, `6.modPow(2,15)` is still well-defined.
- Passing `null` object arguments throws `NullPointerException` per general `BigInteger` rules; never treat null as zero.

| Base | e | m | Result / behavior |
| ---: | ---: | ---: | --- |
| 4 | 13 | 497 | 445 |
| 2 | 10 | 17 | 4 |
| −2 | 5 | 13 | 7 |
| 3 | −1 | 11 | 4 |
| 3 | −2 | 11 | 5 |
| 6 | 2 | 15 | 6 |
| 6 | −1 | 15 | `ArithmeticException`: no inverse |
| 2 | 10 | 0 | `ArithmeticException`: non-positive modulus |
| 2 | 10 | −7 | `ArithmeticException`: non-positive modulus |
| 2 | 0 | 7 | 1 |
| 0 | 0 | 7 | 1 |
| 0 | 5 | 7 | 0 |
| 99 | 0 | 1 | 0 |

For the `6^2 mod 15` row: `36 mod 15=6`, not requiring 6 and 15 to be coprime because the exponent is non-negative.

### 8.1. Zero Exponent and `0^0` in `BigInteger`

`a.modPow(BigInteger.ZERO, m)` returns `1 mod m` when `m>0`. Thus:

- If `m>1`, the result is `1`, even for base `a=0`.
- If `m=1`, the result is `0` because every value modulo 1 is represented by 0.

Java defines the `0.modPow(0,m)` case via API semantics, without requiring learners to debate the analytic meaning of `0^0`. Similarly, `BigInteger.ZERO.pow(0)` returns `BigInteger.ONE`.

### 8.2. Why Is a Negative Exponent a Valid Case?

For `e<0`, modular exponentiation is interpreted via the **multiplicative inverse**:

```text
a^(-1) mod m = inverse(a) mod m
a^(-k) mod m = (inverse(a))^k mod m, k>0
```

For example, `3 mod 11` has inverse 4 because `3×4=12 ≡ 1 (mod 11)`. Therefore:

```text
3^(-1) mod 11 = 4
3^(-2) mod 11 = 4^2 mod 11 = 16 mod 11 = 5.
```

In Java:

```java
BigInteger a = BigInteger.valueOf(3);
BigInteger m = BigInteger.valueOf(11);

System.out.println(a.modPow(BigInteger.valueOf(-1), m)); // 4
System.out.println(a.modPow(BigInteger.valueOf(-2), m)); // 5
```

Do not think `e<0` produces a `BigDecimal`-like rational number via `1/a^k`. It is an **inverse in the modular residue structure**; if no inverse exists, the expression has no modular value and Java throws an error.

## 9. Java Program B — `modPow` and Exponent Preconditions

Create file **`ModularExponentiation.java`**:

```java
import java.math.BigInteger;

public class ModularExponentiation {
    private static BigInteger bi(long n) {
        return BigInteger.valueOf(n);
    }

    public static void main(String[] args) {
        System.out.println(bi(4).modPow(bi(13), bi(497)));
        System.out.println(bi(2).modPow(bi(10), bi(17)));
        System.out.println(bi(-2).modPow(bi(5), bi(13)));

        System.out.println(bi(3).modPow(bi(-1), bi(11)));
        System.out.println(bi(3).modPow(bi(-2), bi(11)));

        System.out.println(bi(2).modPow(bi(0), bi(7)));
        System.out.println(bi(0).modPow(bi(0), bi(7)));
        System.out.println(bi(99).modPow(bi(0), bi(1)));
    }
}
```

Run:

```bash
javac --release 17 ModularExponentiation.java
java ModularExponentiation
```

**Exact stdout:**

```text
445
4
7
4
5
1
1
0
```

The fourth and fifth lines confirm **negative exponents are supported** when `gcd(a,m)=1`. The last line confirms modulus 1 has only the single residue class 0.

## 10. `modInverse(m)` — Multiplicative Inverse Modulo `m`

In real arithmetic, learners may be used to the inverse of 3 being `1/3`. Modulo 11, the inverse of 3 is **4**, because:

```text
3 × 4 = 12
12 mod 11 = 1
⇒ 3 × 4 ≡ 1 (mod 11).
```

Java supports this directly:

```java
BigInteger three = BigInteger.valueOf(3);
BigInteger eleven = BigInteger.valueOf(11);
BigInteger inv = three.modInverse(eleven);

System.out.println(inv); // 4
```

This is a **canonical integer representative** in `[0, m−1]`, not a `double`/`BigDecimal` or ordinary fraction. Given the result `x`, you can verify:

```java
System.out.println(
        three.multiply(inv).mod(eleven)); // 1
```

### 10.1. Condition for the Existence of an Inverse

For modulus `m>1`, the inverse of `a` exists **if and only if**:

```text
gcd(a,m) = 1.
```

This is the most important theorem of this lesson. **The modulus does not have to be prime**. For instance:

- `3` has an inverse modulo `10` because `gcd(3,10)=1`; the result is `7` since `3×7=21 ≡1 (mod 10)`.
- `3` has an inverse modulo `11` because `gcd(3,11)=1`; the result is `4`.
- `6` **does not** have an inverse modulo `15` because `gcd(6,15)=3`.
- `2` **does not** have an inverse modulo `4` because `gcd(2,4)=2`.
- `0` **does not** have an inverse modulo `m>1` because `gcd(0,m)=m≠1`.

`BigInteger.modInverse(m)` throws `ArithmeticException` if `m≤0` or no inverse exists. `m=1` is an algebraically **degenerate** case, explained separately; avoid building algorithms requiring "1 as a nonzero element" while assuming modulus 1 behaves like larger moduli.

### 10.2. Negative Numbers Can Still Have Inverses

A negative base **does not automatically make `modInverse` fail**. For example, `−3 ≡ 8 (mod 11)`. The inverse of `−3` modulo 11 is `7`, because:

```text
(-3)*7 = -21
-21 ≡ 1 (mod 11).
```

Java:

```java
System.out.println(BigInteger.valueOf(-3)
        .modInverse(BigInteger.valueOf(11))); // 7
```

By residue-class properties, `a.modInverse(m)` and `a.mod(m).modInverse(m)` yield the same solution class for `m>0` when the inverse exists.

## 11. `gcd` and the Extended Euclidean Algorithm

`BigInteger.gcd(BigInteger)` returns the **non-negative greatest common divisor** of two numbers (with `gcd(0,0)=0` per the API). When wanting to check before `modInverse`, use:

```java
BigInteger g = a.gcd(m);
boolean invertible = g.equals(BigInteger.ONE);
```

Example:

```java
System.out.println(BigInteger.valueOf(6)
        .gcd(BigInteger.valueOf(15))); // 3
```

### 11.1. Why Does `gcd=1` Guarantee an Inverse?

Bézout's identity states: there exist two integers `x,y` such that:

```text
a*x + m*y = gcd(a,m).
```

If `gcd(a,m)=1` then:

```text
a*x + m*y = 1
⇒ a*x ≡ 1 (mod m).
```

Thus `x` is a modular inverse modulo `m`. The extended Euclidean algorithm finds those coefficients `x,y` and is the classic mathematical basis for computing inverses.

Example `a=3,m=11`:

```text
3*4 + 11*(-1) = 1
⇒ x = 4 is the inverse of 3 modulo 11.
```

Example `a=6,m=15`: every combination `6x+15y` is divisible by 3, so it can never equal 1. No `x` satisfies `6x ≡ 1 (mod 15)`.

### 11.2. Do Not Use Ordinary `x/y` Instead of `modInverse`

Given `a*x ≡ b (mod m)`, sometimes you want to "divide by `a`" to find `x`. That is valid via modular inverse only when `a` is **invertible modulo `m`**:

```text
x ≡ b * inverse(a) (mod m), if gcd(a,m)=1.
```

If `gcd(a,m)>1`, modular division is not as simple as real-number division. The congruence `a*x ≡ b (mod m)` may have **no solution** or **multiple distinct solutions**; a dedicated linear congruence solver is needed along with checking whether `gcd(a,m)` divides `b`. Never catch the exception and replace it with `BigInteger.divide`.

## 12. Java Program C — Inverse, `gcd`, and Exceptions

Create file **`ModularInverseDemo.java`**:

```java
import java.math.BigInteger;

public class ModularInverseDemo {
    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    public static void main(String[] args) {
        BigInteger three = bi(3);
        BigInteger eleven = bi(11);

        BigInteger inverse = three.modInverse(eleven);
        System.out.println(inverse);
        System.out.println(three.multiply(inverse).mod(eleven));

        System.out.println(bi(-3).modInverse(eleven));
        System.out.println(bi(3).modInverse(bi(10)));

        System.out.println(bi(6).gcd(bi(15)));

        try {
            System.out.println(bi(6).modInverse(bi(15)));
        } catch (ArithmeticException ex) {
            System.out.println("No inverse for 6 mod 15");
        }

        try {
            System.out.println(bi(6).modPow(bi(-1), bi(15)));
        } catch (ArithmeticException ex) {
            System.out.println("Negative exponent needs inverse");
        }
    }
}
```

Run:

```bash
javac --release 17 ModularInverseDemo.java
java ModularInverseDemo
```

**Exact stdout:**

```text
4
1
7
7
3
No inverse for 6 mod 15
Negative exponent needs inverse
```

The exception handling here **illustrates the mathematical conditions** for learners, which does not mean an application should silently ignore errors. In production code, validate inputs, distinguish "invalid modulus" from "no inverse exists," and return an appropriate message/status.

## 13. Precondition and Error Table for the Three Methods

| Operation | Valid modulus | Other preconditions | Notable errors |
| --- | --- | --- | --- |
| `a.mod(m)` | `m > 0` | Any integer `a` | `ArithmeticException` if `m≤0` |
| `a.modPow(e,m)` | `m > 0` | For `e<0`, must have `gcd(a,m)=1` | `ArithmeticException` if `m≤0` or negative exponent without inverse |
| `a.modInverse(m)` | `m > 0` | Must be invertible modulo `m`: `gcd(a,m)=1` | `ArithmeticException` if `m≤0` or no inverse |
| `a.remainder(m)` | `m ≠ 0` | `m` can be negative | `ArithmeticException` if `m=0` |
| `a.pow(int e)` | No modulus | `e ≥ 0` | `ArithmeticException` if `e<0` |

**Null:** `BigInteger` methods throw `NullPointerException` when passed null object arguments per general rules; if receiver `a` is null, calling any instance method throws NPE. Never use null as a "modulus zero value."

**Resource capacity:** although `BigInteger` provides arbitrary precision, implementations have resource/memory limits and maximum supported bit lengths. Large operations can consume heavy CPU/memory; `BigInteger` can throw `ArithmeticException` when results exceed supported ranges, in addition to the error conditions listed in the table.

### 13.1. There Is No "`m` Must Be Prime" Condition for `modPow`

`modPow(e,m)` works with **composite moduli** such as `497` or `15` as long as `m>0` and negative-exponent conditions are met. Likewise, `modInverse` **does not require a prime modulus**, only `gcd(a,m)=1`.

A prime modulus `p` gives every nonzero class an inverse, but that is a **finite field** property of `Z/pZ`, not a restriction imposed by Java on the API.

## 14. Edge Cases: `m=1`, `a=0`, `e=0`, Negative Numbers

### 14.1. Modulus Equal to 1

`m=1` is **valid** because `m>0`. Every integer is congruent to 0 modulo 1:

```java
System.out.println(BigInteger.valueOf(99)
        .mod(BigInteger.ONE)); // 0

System.out.println(BigInteger.valueOf(5)
        .modPow(BigInteger.ZERO, BigInteger.ONE)); // 0
```

On JDK 17, `BigInteger.valueOf(2).modInverse(BigInteger.ONE)` returns `0`. This is the degenerate case having a single congruence class `0=1` modulo 1, **not** an ordinary arithmetic inverse. By the same logic, `a.modPow(e,ONE)` returns 0 for exponents, including negative-exponent cases accepted by the JDK.

**Recommendation:** if business designs using inverses, multiplicative groups, or cryptography require a non-degenerate modulus, enforce a stronger precondition: **`m>1`**. This is an **additional business constraint**, not a general restriction of `BigInteger.mod`.

### 14.2. Base Zero

- `0.mod(m)` equals 0 for all `m>0`.
- `0.modPow(e,m)` equals 0 for `e>0` and `m>1`.
- `0.modPow(0,m)` equals `1 mod m`.
- `0.modInverse(m)` **does not exist** if `m>1` because `gcd(0,m)=m`.
- `0.modPow(e<0,m)` throws `ArithmeticException` if `m>1` due to missing inverse.

Do not conclude from "`0^0` is debated in calculus" that Java lacks a defined value for `modPow(0,m)`: the API returns the specified result.

### 14.3. Negative Base

Negative bases are allowed. `mod` normalizes remainders to be non-negative, `modPow` computes the exact congruence class, and `modInverse` works if `gcd=1`.

Examples:

```java
System.out.println(BigInteger.valueOf(-13)
        .mod(BigInteger.valueOf(5))); // 2
System.out.println(BigInteger.valueOf(-2)
        .modPow(BigInteger.valueOf(5),
                BigInteger.valueOf(13))); // 7
```

**Do not use `abs()` instead of `mod()`**: `abs(-13)=13`, not the canonical congruence result of `-13 mod 5`. A sign flip does not preserve residue classes.

### 14.4. Modulus Equal to Zero or Negative

`a.mod(BigInteger.ZERO)`, `a.modPow(e,BigInteger.ZERO)`, and `a.modInverse(BigInteger.ZERO)` all throw `ArithmeticException`. The same applies for a negative modulus. In input-accepting applications, check `m.signum()>0` before computing and provide a clear message.

## 15. Java Program D — Intentional Input Validation

Create file **`CheckedModularArithmetic.java`**:

```java
import java.math.BigInteger;
import java.util.Objects;

public class CheckedModularArithmetic {
    static BigInteger modularPower(
            BigInteger base,
            BigInteger exponent,
            BigInteger modulus) {

        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(exponent, "exponent");
        Objects.requireNonNull(modulus, "modulus");

        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException("modulus must be positive");
        }

        if (exponent.signum() < 0
                && !base.gcd(modulus).equals(BigInteger.ONE)) {
            throw new IllegalArgumentException(
                    "negative exponent requires inverse");
        }

        return base.modPow(exponent, modulus);
    }

    public static void main(String[] args) {
        System.out.println(modularPower(
                BigInteger.valueOf(2),
                BigInteger.TEN,
                BigInteger.valueOf(17)));

        System.out.println(modularPower(
                BigInteger.valueOf(3),
                BigInteger.valueOf(-1),
                BigInteger.valueOf(11)));

        try {
            modularPower(BigInteger.TWO,
                    BigInteger.TEN, BigInteger.ZERO);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            modularPower(BigInteger.valueOf(6),
                    BigInteger.valueOf(-1),
                    BigInteger.valueOf(15));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Run:

```bash
javac --release 17 CheckedModularArithmetic.java
java CheckedModularArithmetic
```

**Exact stdout:**

```text
4
4
modulus must be positive
negative exponent requires inverse
```

An application may choose to let `BigInteger` throw `ArithmeticException` itself, or validate early to deliver business error messages. Validating `gcd` up front can **add cost** because `modPow` with a negative exponent also has to handle invertibility; computing `gcd` beforehand is not necessary on every hot path. However, explicit validation is helpful when classifying input errors is required.

In work involving **untrusted** data, you must also bound `BigInteger` string lengths, base/modulus and exponent bit lengths, execution time, memory, and logging policies. `m>0` does not mean every computation has acceptable cost.

## 16. Theorems That Help Verify Results

When working modulo `m>0`, useful mathematical identities include:

```text
(a + b) mod m = ((a mod m) + (b mod m)) mod m

(a * b) mod m = ((a mod m) * (b mod m)) mod m

a^e mod m = (a mod m)^e mod m, for e >= 0

If gcd(a,m)=1:
a * modInverse(a,m) mod m = 1 mod m.
```

In Java `BigInteger`:

```java
BigInteger left = a.multiply(b).mod(m);
BigInteger right = a.mod(m)
        .multiply(b.mod(m)).mod(m);

boolean equal = left.equals(right);
```

This snippet requires `a`, `b`, and positive non-null `m` to be declared before running. It makes a good **property test** for modular operations, provided inputs belong to the valid domain.

### 16.1. Do Not "Cancel" a Factor When It Is Not Invertible

From:

```text
a*x ≡ a*y (mod m)
```

it does not always follow that `x≡y (mod m)`. Canceling `a` is valid only when `gcd(a,m)=1`.

Example:

```text
2*1 ≡ 2*3 (mod 4)  because 2 ≡ 6 (mod 4),
but 1 is not congruent to 3 (mod 4).
```

This is why "dividing both sides" or calling `modInverse` **is impossible** if `a` lacks an inverse modulo `m`.

### 16.2. Do Not Equate Modular Equivalence with Integer Equality

`a.mod(m).equals(b.mod(m))` is true when `a` and `b` share the same congruence class modulo `m`; it does not mean `a.equals(b)`. For example, `-13` and `2` differ in integer value, yet are congruent modulo 5.

When keying data by residue class, you can use `a.mod(m)` as a **canonical key**, provided the modulus is fixed and consistent. Never change the modulus for keys already inserted into a map/set without defining how to regroup them.

## 17. Java Program E — Mathematical Example Illustrating RSA

Modular exponentiation and modular inverses are used in many mathematical structures, including the RSA cryptosystem. The tiny example below is **for learning only**—never use it for real security.

We pick very small primes:

```text
p = 61
q = 53
n = p*q = 3233
φ(n) = (p-1)*(q-1) = 3120
e = 17
d = e^(-1) mod 3120 = 2753
message = 65
cipher = message^e mod n = 2790
decoded = cipher^d mod n = 65
```

Create file **`ToyRsaMath.java`**:

```java
import java.math.BigInteger;

public class ToyRsaMath {
    public static void main(String[] args) {
        BigInteger p = BigInteger.valueOf(61);
        BigInteger q = BigInteger.valueOf(53);
        BigInteger n = p.multiply(q);

        BigInteger phi = p.subtract(BigInteger.ONE)
                .multiply(q.subtract(BigInteger.ONE));

        BigInteger e = BigInteger.valueOf(17);
        BigInteger d = e.modInverse(phi);

        BigInteger message = BigInteger.valueOf(65);
        BigInteger cipher = message.modPow(e, n);
        BigInteger decoded = cipher.modPow(d, n);

        System.out.println(n);
        System.out.println(phi);
        System.out.println(d);
        System.out.println(cipher);
        System.out.println(decoded);
    }
}
```

Run:

```bash
javac --release 17 ToyRsaMath.java
java ToyRsaMath
```

**Exact stdout:**

```text
3233
3120
2753
2790
65
```

Meaning: `modInverse` finds `d` when `gcd(e,φ(n))=1`; `modPow` performs modular exponentiation without computing gigantic integers. Small numbers let you verify the formulas by hand.

**Security warning:** Real-world RSA requires standard key generation, secure padding (e.g., OAEP for encryption and PSS for signatures), proper randomness, key management, side-channel protection against timing/power attacks, and vetted cryptographic APIs/providers. `BigInteger.modPow` is an arithmetic operation, **not** a complete RSA API or constant-time guarantee. Do not use this example to encrypt or sign real data.

## 18. Common Mistakes

1. **"`mod` is identical to `remainder`."** False for negative numbers. `(-13).remainder(5)=-3`, `(-13).mod(5)=2`.
2. **"Negative moduli are automatically normalized."** False: `mod`, `modPow`, and `modInverse` require `m>0`, otherwise throwing `ArithmeticException`.
3. **"The modulus must be a prime number."** False: composite moduli are allowed as long as each operation's preconditions hold.
4. **"`modInverse` always exists when `m>0`."** False: `gcd(a,m)=1` is required (`m=1` is a degenerate case).
5. **"`modPow` does not allow negative exponents."** False: this is a major difference from `pow(int)`.
6. **"Negative exponents in `modPow` produce ordinary fractions."** False: they compute modular inverses, existing only when invertible.
7. **"`a.pow(e).mod(m)` is always the best way."** False: `pow` can build gigantic numbers; use `modPow`.
8. **"`a.pow(-1)` means inverse."** False: `pow(int)` rejects negative exponents.
9. **"`BigInteger.ZERO.modPow(BigInteger.ZERO,m)` must error."** False: for `m>1`, Java returns 1 by contract.
10. **"`m=1` is disallowed for being too small."** False per the API; `m=1` is a positive modulus, and modulo results are always 0.
11. **"The result of `modInverse` is decimal `1/a`."** False: it is the integer representative of the inverse in the residue class.
12. **"If `a*x ≡ a*y`, you can always cancel `a`."** False if `gcd(a,m)>1`.
13. **"Use `==` to compare two `BigInteger`s with the same number."** False: that compares reference identity; use `equals`.
14. **"`BigInteger` has infinite resources, no need to bound input."** False: resources and implementation ranges are finite.
15. **"`BigInteger.modPow` is enough to write production RSA."** False: RSA also requires padding, randomness, key management, and side-channel defenses.
16. **"`BigInteger.mod` mutates the receiver."** False: `BigInteger` objects are immutable.
17. **"Catching `ArithmeticException` and returning 0 in all cases is safe."** False: it can hide an invalid modulus or non-existent inverse; 0 is a valid result for many operations.
18. **"`gcd(0,m)` always equals 0."** False: for `m>0`, `gcd(0,m)=m`.

## 19. Exercises with Answers

### Exercise 1 — `remainder` and `mod`

Compute `BigInteger.valueOf(-13).remainder(BigInteger.valueOf(5))` and `.mod(BigInteger.valueOf(5))`.

**Answer:** `-3` and `2`. Both lie in the same congruence class, yet `mod` picks the non-negative representative.

### Exercise 2 — Negative modulus

Does `BigInteger.valueOf(13).mod(BigInteger.valueOf(-5))` return 3 or -2?

**Answer:** Neither. The API throws `ArithmeticException` because the modulus is non-positive.

### Exercise 3 — Modulus equal to 1

What does `BigInteger.valueOf(-123456).mod(BigInteger.ONE)` equal?

**Answer:** `0`. Modulo 1 has only one representative, 0.

### Exercise 4 — Basic `modPow`

Compute `4^13 mod 497` using `BigInteger.modPow`.

**Answer:** `445`: `BigInteger.valueOf(4).modPow(BigInteger.valueOf(13), BigInteger.valueOf(497))`.

### Exercise 5 — Comparing `pow` and `modPow`

How does `BigInteger.TWO.pow(10)` differ from `BigInteger.TWO.modPow(BigInteger.TEN,BigInteger.valueOf(17))`?

**Answer:** `1024` and `4`. `pow` computes the full power; `modPow` returns the modular result.

### Exercise 6 — Negative exponent

What does `BigInteger.valueOf(3).modPow(BigInteger.valueOf(-1), BigInteger.valueOf(11))` return?

**Answer:** `4`, because `3×4≡1 (mod 11)`. This is the modular inverse, not the real number `1/3`.

### Exercise 7 — Second negative exponent

What is `3^(-2) mod 11`?

**Answer:** `5`, because the inverse of 3 is 4, and `4² mod 11 = 16 mod 11 = 5`.

### Exercise 8 — Inverse condition

Does `6.modInverse(15)` succeed? Why?

**Answer:** No, it throws `ArithmeticException` because `gcd(6,15)=3≠1`.

### Exercise 9 — Non-prime modulus

What does `3.modInverse(10)` equal?

**Answer:** `7`, because `3×7=21≡1 (mod 10)`. Composite modulus 10 still allows an inverse for 3.

### Exercise 10 — Negative base

What value does `(-2)^5 mod 13` return via `modPow`?

**Answer:** `7`, because `-32 ≡ 7 (mod 13)`. Negative bases are valid.

### Exercise 11 — Zero exponent

What do `0.modPow(0,7)` and `0.modPow(0,1)` return?

**Answer:** `1` and `0`. The rule is `1 mod m` when the exponent is zero.

### Exercise 12 — Negative-exponent precondition

Is `6.modPow(-1,15)` allowed?

**Answer:** The method signature accepts a negative exponent, but the call throws `ArithmeticException` because the base is not invertible modulo 15.

### Exercise 13 — Solving congruences

Solve `3*x ≡ 5 (mod 11)` using `modInverse`.

**Answer:** `inverse(3)=4`, so `x≡5×4≡20≡9 (mod 11)`. You can write `bi(5).multiply(bi(3).modInverse(bi(11))).mod(bi(11))`, where `bi(long)` is a helper creating `BigInteger`.

### Exercise 14 — Checking congruence

Are `-13` and `2` equal via `BigInteger.equals`? Are they congruent mod 5?

**Answer:** Not equal under `equals`, yet `(-13).mod(5)=2.mod(5)=2`, so they are congruent.

### Exercise 15 — Comparing two values as modular keys

When needing to group integers by residue class modulo `m>0`, should you use `a` directly or `a.mod(m)`?

**Answer:** Use `a.mod(m)` as the canonical key if grouping by residue class. The same residue class can contain many distinct integers.

### Exercise 16 — Checking the modulus

A business function requires `m>1` and an invertible base if `e` is negative. In what order should validation run?

**Answer:** Check non-null; check `m.compareTo(BigInteger.ONE)>0`; if `e.signum()<0`, check `a.gcd(m).equals(ONE)`; then call `a.modPow(e,m)`. `m>1` is a stricter business constraint than the API's `m>0`.

### Exercise 17 — Cancellation concept

Why does `2*x ≡ 2*y (mod 4)` not imply `x≡y (mod 4)`?

**Answer:** `2` is not invertible modulo `4` because `gcd(2,4)=2`. Counterexample: `x=1,y=3`.

### Exercise 18 — RSA application

In the tiny example, `e=17` and `φ(n)=3120`; compute `d=e.modInverse(phi)` and `65^e mod 3233`.

**Answer:** `d=2753` and ciphertext `2790`; `2790^2753 mod 3233=65`. This is solely an illustrative exercise, not for real security.

## 20. Pre-Project Checklist

- [ ] I know `mod` returns a **non-negative** representative for a positive modulus, unlike `remainder` when the receiver is negative.
- [ ] I check `m.signum()>0` before `mod`/`modPow`/`modInverse`.
- [ ] I know `m=1` is valid per the API but may be disallowed by business rules.
- [ ] I use `modPow` for large modular exponentiation instead of `pow` followed by `mod`.
- [ ] I distinguish the exponent parameter types of `pow(int)` and `modPow(BigInteger,BigInteger)`.
- [ ] I know `modPow` **allows negative exponents** if the base has an inverse modulo `m`.
- [ ] I use `gcd(a,m)=1` to verify `modInverse` existence rather than needlessly requiring a prime modulus.
- [ ] I distinguish modular inverses from ordinary integer division or fractions.
- [ ] I do not cancel non-invertible factors in congruences.
- [ ] I know how to recognize `ArithmeticException` for non-positive moduli or missing inverses.
- [ ] I know null throws `NullPointerException` and `BigInteger` is immutable.
- [ ] I consider edge cases: 0, 1, negative numbers, exponent 0, and negative exponents.
- [ ] I verify inverse results with `a.multiply(inv).mod(m).equals(BigInteger.ONE.mod(m))`.
- [ ] I avoid confusing reference `==` with value equality `equals`.
- [ ] I bound input sizes if operations could be abused to exhaust CPU/RAM.
- [ ] I do not use illustrative modular-arithmetic programs as real security systems.
- [ ] I compiled/ran the five sample programs and compared stdout.

## 21. Official Documentation and Further Reading

- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html) — contracts for `mod`, `remainder`, `modPow`, `modInverse`, `pow`, `gcd`, and exceptions.
- [Java SE 17 — ArithmeticException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html) — exception for invalid arithmetic operations.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — separate class for decimals, **not** a replacement for integer modular arithmetic.
- [JLS 17, `4.2.2 Integer Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.2) — division and remainder of integer primitives to compare against `BigInteger.remainder`.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html) — high-level cryptography API; mathematical `modPow` illustrations do not replace it.
- [Java SE 17 — Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — high-level digital signature API; do not roll raw modular exponentiation for signing.

**Conclusion:** the three APIs have clear, distinct scopes: **`mod`** normalizes remainders into `[0,m−1]`, **`modPow`** computes modular exponentiation efficiently and supports negative exponents when invertible, and **`modInverse`** finds the modular inverse only when `gcd(a,m)=1`. Most bugs stem not from Java syntax, but from **forgetting to check the modulus, invertibility, and edge cases**.