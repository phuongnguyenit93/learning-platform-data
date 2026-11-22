# Exact Division and JDK-Version-Specific Additional APIs

Java has had integer division `/` and `Math.floorDiv` for a long time. However, ordinary integer division has a special overflow case: `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` itself instead of reporting an error. Starting in **JDK 18**, the `Math` class added `divideExact`, `floorDivExact`, and `ceilDivExact` to detect this overflow case. That same release also added `ceilDiv` and `ceilMod` for ceiling-rounded division.

The word **exact** here means **division must not silently return a quotient that overflowed the representation range**, and does **not mean the two numbers must divide evenly without remainder**. Distinguishing this is central when choosing an API and when deploying on JDK 17 or newer.

## 1. Why Does Integer Division Need Overflow Checking?

Java integer types are signed and have finite bounds:

- `int`: `-2_147_483_648` to `2_147_483_647`.
- `long`: `-9_223_372_036_854_775_808L` to `9_223_372_036_854_775_807L`.

The negative range has one extra value in magnitude compared to the positive range. The mathematical value of `-Integer.MIN_VALUE` is 2,147,483,648, which exceeds `int`. Therefore, `Integer.MIN_VALUE / -1` has a mathematical quotient outside the `int` range. The same holds for `Long.MIN_VALUE / -1L`.

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1); // -2147483648: overflowed result.
System.out.println(min % -1); // 0.
```

**Java does not throw an exception in this division overflow case.** That is the specified behavior of the `/` operator. Conversely, integer division by **0** always throws `ArithmeticException`.

### Different from addition and multiplication overflow

Addition and multiplication can also overflow, and many combinations of values can cause overflow. For signed integer division with a non-zero divisor, **the only quotient overflow case** is:

| Type | Dividend | Divisor | Mathematical Quotient | Standard Java Quotient |
| --- | --- | --- | --- | --- |
| `int` | `Integer.MIN_VALUE` | `-1` | 2,147,483,648 | `Integer.MIN_VALUE` |
| `long` | `Long.MIN_VALUE` | `-1L` | 9,223,372,036,854,775,808 | `Long.MIN_VALUE` |

Every other integer division with a non-zero divisor has its quotient truncated toward 0 and fits within the same type's range. Even so, the quotient still **drops any remainder**, because integer division does not store fractional parts.

## 2. JDK Version Determines Which APIs Can Be Used

When developing a shared library, there are two independent factors: the running JDK and the **APIs permitted for the target version**. Code compiled with a newer JDK can still be incompatible with Java 17 if it calls methods introduced only in JDK 18.

| API / API Group in `Math` | Starting Version | Purpose |
| --- | --- | --- |
| `addExact`, `subtractExact`, `multiplyExact` (`int,int` and `long,long` overloads), `incrementExact`, `decrementExact`, `negateExact`, `toIntExact` | Java 8 | Overflow checking for add/subtract/multiply/increment/decrement/negate/`long`-to-`int` conversion |
| `floorDiv` and `floorMod` (initial overloads) | Java 8 | Division with quotient rounded down, remainder taking divisor's sign |
| `multiplyFull(int,int)`, `multiplyHigh(long,long)`, `multiplyExact(long,int)` | Java 9 | Additional multiplication capabilities and observing larger results |
| `absExact(int)`, `absExact(long)` | Java 15 | Absolute value, throwing an exception on the minimum value |
| **`divideExact(int,int)`, `divideExact(long,long)`** | **Java 18** | Truncating-toward-0 division that throws an exception if the quotient overflows |
| **`floorDivExact(int,int)`, `floorDivExact(long,long)`** | **Java 18** | Floor division with quotient overflow checking |
| **`ceilDivExact(int,int)`, `ceilDivExact(long,long)`** | **Java 18** | Ceiling division with quotient overflow checking |
| `ceilDiv`, `ceilMod` | Java 18 | Ceiling-rounded quotient and accompanying remainder; plain versions do not check `MIN_VALUE / -1` overflow |
| `unsignedMultiplyHigh(long,long)` | Java 18 | Gets the upper 64 bits of a 128-bit product in an unsigned sense |

This table lists APIs relevant to integer arithmetic; it is not meant to enumerate every method in `Math`.

**Compatibility rules:**

- On **Java 17**, `Math.divideExact`, `Math.floorDivExact`, `Math.ceilDivExact`, `Math.ceilDiv`, and `Math.ceilMod` **do not exist yet**. Calling them when compiling with `--release 17` fails with a method-not-found error.
- On **Java 18+**, you can use the new methods, provided both the build and runtime environments meet that version.
- On **Java 17**, you can check for the overflow case before `/` or `Math.floorDiv` using a small helper function (see section 6).
- Java 17 **already has `Math.absExact`**, `Math.addExact`, `Math.multiplyExact`, and `Math.toIntExact`. Do not assume the entire `Exact` family appeared in the same version.

Use these commands to check your toolchain:

```bash
java -version
javac -version
javac --release 17 YourFile.java
```

`--release 17` restricts the language and public APIs to Java 17, making it the right check for library code requiring Java 17 compatibility. Running an application that uses Java 18+ APIs on an older runtime can cause a linkage error `NoSuchMethodError` (or a class-file version error, depending on how it was compiled); do not care only whether it runs on the development machine.

## 3. `Math.divideExact`: Still Truncating-Toward-Zero Division

From Java 18:

```java
System.out.println(Math.divideExact(7, 3));  // 2.
System.out.println(Math.divideExact(-7, 3)); // -2.
System.out.println(Math.divideExact(7, -3)); // -2.
```

For normal operands, `divideExact(x,y)` gives the same value as `x / y`, namely **truncation toward zero**. If the division has a remainder, both return the truncated integer quotient and **do not throw an exception merely because there is a remainder**.

For example, `Math.divideExact(7, 3) == 2`, with no error saying "7 is not divisible by 3."

### Exception cases

`Math.divideExact` throws `ArithmeticException` when:

1. The divisor equals **0**.
2. The quotient **overflows**, i.e., the `MIN_VALUE` and `-1` pair of the same type.

```java
// Java 18+:
Math.divideExact(Integer.MIN_VALUE, -1); // ArithmeticException.
Math.divideExact(Long.MIN_VALUE, -1L);   // ArithmeticException.
Math.divideExact(9, 0);                  // ArithmeticException.
```

Note that `Math.divideExact` does **not** throw `ArithmeticException` for `Math.divideExact(7,3)`. Do not rely on the method's name as a substitute for a **divisibility** check.

### Want to require exact divisibility with no remainder?

A custom policy can combine **two conditions**: the quotient does not overflow **and** the remainder equals 0.

```java
// Java 18+ illustrative helper (place inside a class):
static int divideWithoutRemainder(int dividend, int divisor) {
    int quotient = Math.divideExact(dividend, divisor);
    if (dividend % divisor != 0) {
        throw new ArithmeticException("Division has remainder");
    }
    return quotient;
}
```

For example, `divideWithoutRemainder(12,4)` equals 3; `divideWithoutRemainder(7,3)` throws an exception due to a remainder; `divideWithoutRemainder(Integer.MIN_VALUE,-1)` throws an exception due to overflow. `Math.divideExact` already checks for a zero divisor before `%`, so modulo by 0 cannot occur.

If the problem accepts **fractional** results, change the data model (such as keeping integer numerator/denominator with custom normalization rules, or using decimal numbers with a rounding policy), rather than expecting `divideExact` to produce 2.333… as an `int`.

## 4. Three Ways to Obtain a Quotient: Truncate, Floor, and Ceiling

Quotient rounding modes produce different results when division has a remainder:

| Operation | Quotient Rule | Example `-7 / 3` | Example `7 / 3` |
| --- | --- | ---: | ---: |
| `x / y` or `Math.divideExact(x,y)` | Truncate fraction **toward 0** | −2 | 2 |
| `Math.floorDiv(x,y)` or `Math.floorDivExact(x,y)` | Round **down toward negative infinity** | −3 | 2 |
| `Math.ceilDiv(x,y)` or `Math.ceilDivExact(x,y)` | Round **up toward positive infinity** | −2 | 3 |

The `Exact` methods in the table are all available from **Java 18**; `floorDiv` existed earlier, while `ceilDiv` was also added in Java 18.

Mathematical definitions, when the result is representable:

- `trunc(x/y)`: takes the integer part toward 0.
- `floor(x/y)`: largest integer not exceeding the mathematical quotient.
- `ceil(x/y)`: smallest integer not less than the mathematical quotient.

Examples with negative signs:

```java
// Java 18+:
System.out.println(Math.divideExact(-7, 3));   // -2.
System.out.println(Math.floorDivExact(-7, 3)); // -3.
System.out.println(Math.ceilDivExact(-7, 3));  // -2.

System.out.println(Math.divideExact(7, 3));   // 2.
System.out.println(Math.floorDivExact(7, 3)); // 2.
System.out.println(Math.ceilDivExact(7, 3));  // 3.
```

**Quotient rounding and overflow checking are two separate decisions.** `floorDiv` addresses the rounding direction, while `floorDivExact` both uses the same rounding direction and reports overflow. `ceilDiv` and `ceilDivExact` work analogously.

### Matching remainder for each quotient style

To preserve the arithmetic identity `x = quotient * y + remainder`:

| Rounding Direction | Quotient | Accompanying Remainder |
| --- | --- | --- |
| Truncate | `/` or `divideExact` | `%` |
| Floor | `floorDiv` or `floorDivExact` | `floorMod` |
| Ceiling | `ceilDiv` or `ceilDivExact` | `ceilMod` |

With `x=-7` and `y=3`:

- Truncate: quotient −2, remainder −1; since `-7 = -2 * 3 + (-1)`.
- Floor: quotient −3, remainder 2; since `-7 = -3 * 3 + 2`.
- Ceiling: quotient −2, remainder −1; same result as truncate in this case.

With `x=7` and `y=3`:

- Truncate: quotient 2, remainder 1.
- Floor: quotient 2, remainder 1.
- Ceiling: quotient 3, remainder −2; since `7 = 3 * 3 + (-2)`.

`floorMod` produces a remainder with the same sign as the **divisor** or 0; `ceilMod` produces a remainder with the opposite sign to the **divisor** or 0. When you truly need a non-negative remainder, use `floorMod(x, m)` with **`m > 0`**. `ceilMod` does not replace `floorMod` for standard circular indexing.

**Representation-range exception:** if `x = MIN_VALUE` and `y = -1`, the non-`Exact` methods can return an overflowed quotient. The identities above should be understood mathematically or verified within a valid numeric range; avoid inferring exact mathematical results from an overflowed calculation.

## 5. Exact Methods That Do *Not* Share the Same Semantics

The word `Exact` in `Math` usually means "detect when an integer result **exceeds the return type's range**," with each method checking its corresponding operation:

| Method | Success Example | When It Throws an Error |
| --- | --- | --- |
| `Math.addExact(a,b)` | `addExact(2,3) == 5` | Sum exceeds `int`/`long` |
| `Math.subtractExact(a,b)` | `subtractExact(5,3) == 2` | Difference out of range |
| `Math.multiplyExact(a,b)` | `multiplyExact(3,4) == 12` | Product out of range |
| `Math.negateExact(a)` | `negateExact(-7) == 7` | `a == MIN_VALUE` |
| `Math.absExact(a)` | `absExact(-7) == 7` | `a == MIN_VALUE` |
| `Math.incrementExact(a)` / `decrementExact(a)` | Increment/decrement by 1 | Crosses bound when incrementing/decrementing |
| `Math.toIntExact(value)` | `toIntExact(42L) == 42` | `long` value does not fit in `int` |
| `Math.divideExact(x,y)` | `divideExact(7,3) == 2` | Divide by 0 or **quotient overflow** |
| `Math.floorDivExact(x,y)` | `floorDivExact(-7,3) == -3` | Divide by 0 or **quotient overflow** |
| `Math.ceilDivExact(x,y)` | `ceilDivExact(7,3) == 3` | Divide by 0 or **quotient overflow** |

Some non-`Exact` methods can still store an exact mathematical result in a **wider** type. For instance, `Math.multiplyFull(int,int)` returns the product of two `int`s in a `long`, because the product of two `int`s always fits in `long`. `Math.multiplyHigh(long,long)` only provides the upper 64 bits of a 128-bit product, **not** the full product as a single exact `long`.

Note that `Math.abs(Integer.MIN_VALUE)` still returns `Integer.MIN_VALUE`; `Math.absExact(Integer.MIN_VALUE)` is what detects the overflow. `Math.toIntExact` does not check for negative numbers or array bounds: it only checks the `int` range, not business validity.

## 6. Java 17: Building Overflow-Checked Division Without `divideExact`

If a module targets Java 17, do not try to call Java 18 methods by "adding an import." `Math` belongs to the JDK's `java.base` module and you cannot add a newer API version via an import.

To get **equivalent checking behavior** to `divideExact(int,int)` on Java 17, handle the overflowing pair before the `/` operator:

```java
// Place inside a class on Java 17+:
static int divideChecked(int x, int y) {
    if (y == 0) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Integer.MIN_VALUE && y == -1) {
        throw new ArithmeticException("integer overflow");
    }
    return x / y;
}
```

Version for `long`:

```java
static long divideChecked(long x, long y) {
    if (y == 0L) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Long.MIN_VALUE && y == -1L) {
        throw new ArithmeticException("long overflow");
    }
    return x / y;
}
```

These functions throw `ArithmeticException` just like the Java 18 methods, but **the message content is chosen by the function**, not a JDK exception-message guarantee. When writing business tests, check the **error type/condition** rather than depending on a fixed message string.

### Java 17: checking floor quotient instead of truncate

You can check for overflow and then call `Math.floorDiv`:

```java
static int floorDivChecked(int x, int y) {
    if (y == 0) {
        throw new ArithmeticException("/ by zero");
    }
    if (x == Integer.MIN_VALUE && y == -1) {
        throw new ArithmeticException("integer overflow");
    }
    return Math.floorDiv(x, y);
}
```

`Math.floorDiv` already exists in Java 17; after excluding the overflow case, the result matches Java 18's `floorDivExact` semantics.

If **ceil division** is needed on Java 17, implement it carefully for negative signs too—do not blindly apply `(a+b-1)/b`, because that formula can overflow and fails for negative numbers.

A Java 17-compatible approach based on the quotient and remainder of ordinary division is:

```java
static int ceilDivChecked(int x, int y) {
    int quotient = divideChecked(x, y);
    int remainder = x % y;
    if (remainder != 0 && ((x ^ y) >= 0)) {
        return quotient + 1;
    }
    return quotient;
}
```

In `int` arithmetic, `(x ^ y) >= 0` checks whether the two numbers have the **same sign** (the XOR sign bit is 0). When a positive quotient has a remainder, ceiling needs to add one; for a negative quotient, the truncated result is already the ceiling. The overflow pair was already excluded by `divideChecked`; `quotient + 1` in this branch will not exceed the `int` range. This is an illustrative function showing one overflow-checked implementation, not a standard Java 17 API.

For new code requiring Java 18+, calling `Math.ceilDivExact` directly is more readable and easier to maintain.

## 7. Standalone Runnable Example on Java 18+

Save the program as `ExactDivisionDemo18.java`:

```java
public class ExactDivisionDemo18 {
    public static void main(String[] args) {
        System.out.println("7 / 3 = " + (7 / 3));
        System.out.println("Math.divideExact(7,3) = "
                + Math.divideExact(7, 3));
        System.out.println("Math.divideExact(-7,3) = "
                + Math.divideExact(-7, 3));

        System.out.println("Math.floorDivExact(-7,3) = "
                + Math.floorDivExact(-7, 3));
        System.out.println("Math.ceilDivExact(7,3) = "
                + Math.ceilDivExact(7, 3));
        System.out.println("Math.ceilDivExact(-7,3) = "
                + Math.ceilDivExact(-7, 3));

        System.out.println("Math.floorMod(-7,3) = "
                + Math.floorMod(-7, 3));
        System.out.println("Math.ceilMod(7,3) = "
                + Math.ceilMod(7, 3));

        System.out.println("Long division = "
                + Math.divideExact(9_000_000_000L, 3L));

        try {
            Math.divideExact(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("MIN_VALUE / -1: ArithmeticException");
        }

        try {
            Math.floorDivExact(1, 0);
        } catch (ArithmeticException ex) {
            System.out.println("Division by zero: ArithmeticException");
        }

        System.out.println("7 divisible by 3? " + (7 % 3 == 0));
        System.out.println("12 divisible by 4? " + (12 % 4 == 0));
    }
}
```

Run with JDK 18 or newer:

```bash
javac --release 18 ExactDivisionDemo18.java
java ExactDivisionDemo18
```

Stdout:

```text
7 / 3 = 2
Math.divideExact(7,3) = 2
Math.divideExact(-7,3) = -2
Math.floorDivExact(-7,3) = -3
Math.ceilDivExact(7,3) = 3
Math.ceilDivExact(-7,3) = -2
Math.floorMod(-7,3) = 2
Math.ceilMod(7,3) = -2
Long division = 3000000000
MIN_VALUE / -1: ArithmeticException
Division by zero: ArithmeticException
7 divisible by 3? false
12 divisible by 4? true
```

The last two lines emphasize that `Math.divideExact(7,3)` still equals 2 and **does not guarantee even divisibility**; only checking `7 % 3 == 0` tells you whether two integers divide evenly.

### Separate runnable example on Java 17

Save `ExactDivisionDemo17.java`:

```java
public class ExactDivisionDemo17 {
    static int divideChecked(int x, int y) {
        if (y == 0) throw new ArithmeticException("/ by zero");
        if (x == Integer.MIN_VALUE && y == -1) {
            throw new ArithmeticException("integer overflow");
        }
        return x / y;
    }

    static int floorDivChecked(int x, int y) {
        if (y == 0) throw new ArithmeticException("/ by zero");
        if (x == Integer.MIN_VALUE && y == -1) {
            throw new ArithmeticException("integer overflow");
        }
        return Math.floorDiv(x, y);
    }

    public static void main(String[] args) {
        System.out.println("Checked quotient: " + divideChecked(-7, 3));
        System.out.println("Checked floor: " + floorDivChecked(-7, 3));
        try {
            divideChecked(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("Overflow detected");
        }
    }
}
```

```bash
javac --release 17 ExactDivisionDemo17.java
java ExactDivisionDemo17
```

Stdout:

```text
Checked quotient: -2
Checked floor: -3
Overflow detected
```

These are **two independent files/programs** with two different JDK requirement levels. If you genuinely must run on Java 17, pick the Java 17 example and do not call `divideExact`/`ceilDivExact`.

## 8. Boundary Testing and Choosing the Right API in Practice

A minimal test suite for overflow-checked integer division should cover:

| Input | Expected Result of `divideExact` (Java 18+) | What to Verify |
| --- | --- | --- |
| `(7,3)` | 2 | Has remainder yet does **not** throw an exception |
| `(-7,3)` | −2 | Truncates toward 0 |
| `(7,-3)` | −2 | Truncates toward 0 |
| `(-7,-3)` | 2 | Both numbers have the same sign |
| `(Integer.MIN_VALUE,-1)` | `ArithmeticException` | `int` overflow |
| `(Long.MIN_VALUE,-1L)` | `ArithmeticException` | `long` overflow |
| `(1,0)` | `ArithmeticException` | Division by 0 |
| `(0,3)` | 0 | Zero dividend |
| `(Integer.MIN_VALUE,1)` | `Integer.MIN_VALUE` | Value within range |

For `floorDivExact` and `ceilDivExact`, add tests dividing negative numbers with remainders: `(-7,3)` gives −3/−2 respectively, and `(7,3)` gives 2/3; test negative divisors as well. On JDK 17, run the same test cases for your custom `divideChecked`, `floorDivChecked`, or `ceilDivChecked` helpers, and test compiling with `--release 17`.

### Which "exact" does the business requirement actually need?

At least three needs must be distinguished:

1. **Disallow overflow:** use `Math.divideExact`, `floorDivExact`, or `ceilDivExact` on Java 18+, or check before dividing on Java 17.
2. **Disallow remainders:** in addition to checking overflow, check `x % y == 0`. No divisibility guarantee can be inferred solely from the name `divideExact`.
3. **Need a mathematical result larger than `long`, or exact fractions/decimals:** use large-number structures or an appropriate representation contract, such as `BigInteger` for large integers and `BigDecimal` for decimal values with an explicit division/rounding policy. `BigDecimal.divide` with an exact requirement can throw `ArithmeticException` when the decimal expansion does not terminate; this **is different semantics** from `Math.divideExact`.

If untrusted data arrives from outside, handle `ArithmeticException` at an appropriate boundary and decide explicitly which errors to report externally. Do not catch all exceptions and return 0, because 0 is a valid division result and can mask invalid data.

### Common pitfalls

- **Confusing `divideExact` with "divisible without remainder."** `divideExact(7,3)` returns 2 without throwing.
- **Using Java 18 APIs in a project that requires Java 17.** Check with `javac --release 17`, not just the JDK installed on your machine.
- **Using `Math.floorDiv` expecting it to detect overflow automatically.** `floorDiv(MIN_VALUE,-1)` can still return an overflowed value; Java 18+ provides `floorDivExact`.
- **Using `Math.ceilDiv` thinking it is checked division.** `ceilDiv` handles rounding direction; `ceilDivExact` adds overflow checking.
- **Converting to `double` and calling `Math.floor` or `Math.ceil` on very large `long` values.** Converting `long` to `double` can lose precision; prefer integer APIs.
- **Assuming `Math.abs` checks for overflow.** `Math.abs(Integer.MIN_VALUE)` stays negative; `Math.absExact` (from Java 15) is what detects it.
- **Using `(a+b-1)/b` for ceiling division on all inputs.** That formula can overflow and mishandles many negative-number cases.
- **Confusing overloads with return types.** When using `int`/`long`, check the actual method signature; do not implicitly narrow a `long` result to `int`.
- **Comparing exception message text as a protocol.** Verify the error type and semantics, because messages are not a fixed contract across all JDKs.

## 9. Self-Check

1. Why doesn't `Integer.MIN_VALUE / -1` throw an exception whereas `Math.divideExact(Integer.MIN_VALUE,-1)` does? Which Java version added the latter method?
2. Does `Math.divideExact(10,3)` throw `ArithmeticException`? If you want to enforce that 10 is divisible by 3, what condition is missing?
3. For `x=-7, y=3`, distinguish the quotients of `/`, `floorDivExact`, and `ceilDivExact`.
4. Why does `Math.ceilDiv(7,3)` equal 3 while `Math.ceilMod(7,3)` equals −2? Verify the relation between quotient and remainder.
5. When developing a library that runs on Java 17, why doesn't building with JDK 24 automatically allow calling `Math.divideExact` in a Java 17-compatible artifact?
6. Write a Java 17 checked integer-division helper for the `Long.MIN_VALUE/-1L` case and divisor 0 case.
7. When should you use `Math.toIntExact`, `Math.absExact`, or `Math.multiplyExact` instead of `Math.divideExact`?

## 10. Official JDK API References

- [Math — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): overloads available prior to Java 18, including `floorDiv`, `floorMod`, `absExact`, `addExact`, `multiplyExact`, and `toIntExact`.
- [Math — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/Math.html): `Since: 18` for `divideExact`, `floorDivExact`, `ceilDivExact`, `ceilDiv`, and `ceilMod`.
- [Java Language Specification `15.17.2 — Division Operator /](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): integer division rules and the overflow case.

**Remember:** **Java 18+** provides `divideExact`/`floorDivExact`/`ceilDivExact` to **report errors when an integer quotient overflows**. "Exact" does not mean the result has no remainder. **Java 17** can still implement the checking policy by catching `MIN_VALUE/-1` before `/` or `floorDiv`, and you must clearly specify rounding rules, divisibility requirements, division-by-zero handling, and the target JDK version.
