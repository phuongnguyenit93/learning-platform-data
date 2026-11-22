# BigInteger: Arbitrary-Precision Integers and Immutability in Java

`java.math.BigInteger` is the class that represents **arbitrary-precision signed integers** in Java. Unlike `int` with 32 bits and `long` with 64 bits, `BigInteger` does not force values into that fixed width. When adding, multiplying, or shifting bits to produce a larger number, the library can expand its internal representation instead of automatically wrapping around on 32/64-bit two's complement overflow.

At the same time, `BigInteger` is **immutable**: after an object is created, **the value of that object itself does not change**. Operations such as `add`, `multiply`, `subtract`, and `pow` create/return an object representing the result; the reference variable must be reassigned if you want to continue using the new result.

```java
import java.math.BigInteger;

BigInteger original = BigInteger.valueOf(Integer.MAX_VALUE);
BigInteger next = original.add(BigInteger.ONE);

System.out.println(original); // 2147483647
System.out.println(next);     // 2147483648
```

Here `original` is **not** modified. The result `next` exceeds `Integer.MAX_VALUE` while remaining exact. However, "arbitrary" does not mean infinite resources: memory, object size, computation time, and implementation limits still exist.

## 1. Why Do We Need `BigInteger` When Java Already Has `int` and `long`?

Integer primitives have fixed value ranges:

| Type | Bits | Signed value range |
| --- | ---: | --- |
| `byte` | 8 | −128 to 127 |
| `short` | 16 | −32,768 to 32,767 |
| `int` | 32 | −2,147,483,648 to 2,147,483,647 |
| `long` | 64 | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| `BigInteger` | No fixed 32/64-bit width | Very large negative, zero, and positive integers, limited by implementation/resources |

With regular `int` addition, when the result exceeds the range, Java keeps the result according to integer overflow rules:

```java
int a = Integer.MAX_VALUE;
System.out.println(a + 1); // -2147483648: overflow.
```

`BigInteger` avoids overflow **at primitive limits** by using an expandable representation structure:

```java
BigInteger a = BigInteger.valueOf(Integer.MAX_VALUE);
System.out.println(a.add(BigInteger.ONE)); // 2147483648.
```

A large number exceeding even `long` can also be represented with `BigInteger`:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
System.out.println(beyondLong); // 9223372036854775808.
```

**Important:** `BigInteger` is still an **integer**. It has no fractional part; `1 / 2` equals 0 under integer division in this class. If the problem requires exact decimals and scale, see `BigDecimal`. If you only need counts within the `int`/`long` range, you should not default to `BigInteger` because it incurs extra memory, object, and operational overhead.

## 2. Nature and Type Relationships of `BigInteger`

`BigInteger` belongs to the `java.math` package; unlike `Integer` and `Long` in `java.lang`, you need `import java.math.BigInteger;` or its fully qualified name.

It is a **reference class**:
- Extends `Number`, so it has `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`.
- Implements `Comparable<BigInteger>`, so it has `compareTo`.
- Is **immutable** and has an object-oriented math API.
- Has no overloaded `+`/`-`/`*`/`/` operators on objects as in some other languages.

```java
BigInteger x = BigInteger.valueOf(12);
BigInteger y = BigInteger.valueOf(5);

// BigInteger z = x + y; // Does not compile.
BigInteger z = x.add(y); // 17.
```

Do not confuse `BigInteger` with `Integer`:
- `Integer` is the immutable wrapper for the 32-bit `int` primitive.
- `BigInteger` stores an integer not limited to 32-bit precision and provides many computation methods.
- `BigInteger` is not a subtype of `Integer`, and `BigInteger` does not auto-unbox to `int`.

The fact that both types extend `Number` does not mean references can be cast arbitrarily between them.

## 3. Creating `BigInteger` Objects Properly

### 3.1. From `long` with `valueOf`

```java
BigInteger a = BigInteger.valueOf(42);
BigInteger b = BigInteger.valueOf(-17);
BigInteger c = BigInteger.valueOf(Long.MAX_VALUE);
```

`BigInteger.valueOf(long)` accepts a **`long` value**. It is suitable when the input already fits within the 64-bit range.

```java
// BigInteger wrong = BigInteger.valueOf(99999999999999999999999L);
// long literal too large: compile error, BigInteger cannot rescue it beforehand.
```

If the value **exceeds `long`**, create it directly from a controlled digit string.

### 3.2. From a Decimal String Using the Constructor

```java
BigInteger population =
        new BigInteger("123456789012345678901234567890");

BigInteger negative = new BigInteger("-12345678901234567890");
BigInteger zero = new BigInteger("0");
```

`new BigInteger(String)` parses decimal by default, and can handle a valid leading `+` or `-` sign. If the text is invalid, the constructor throws `NumberFormatException`:

```java
// new BigInteger("12.5");      // Wrong: has a fractional part.
// new BigInteger("1_000");     // Wrong: underscores are not accepted as in literals.
// new BigInteger(" 100 ");     // Wrong: has unhandled whitespace.
// new BigInteger("0xFF");      // Wrong: does not auto-detect hex prefix.
```

The calls above are **commented out** because they intentionally illustrate errors, not code to run sequentially.

### 3.3. From a String in Radix 2–36

```java
BigInteger hex = new BigInteger("ff", 16);     // 255.
BigInteger binary = new BigInteger("1010", 2); // 10.
BigInteger signed = new BigInteger("-ff", 16); // -255.
```

The `radix` parameter specifies the base. The `BigInteger(String,int)` constructor does not understand `0x`/`0b` by default; the string must contain digits appropriate for the radix and a valid sign. `toString(int radix)` performs the reverse conversion:

```java
System.out.println(hex.toString(16)); // ff.
System.out.println(binary.toString(2)); // 1010.
```

If the input is an **identifier** with leading zeros that must be preserved, do not convert it to `BigInteger` when arithmetic is not needed: the integer value does not retain the width or digit grouping of the original string.

### 3.4. Useful Constants

The JDK provides:

```java
BigInteger.ZERO
BigInteger.ONE
BigInteger.TWO
BigInteger.TEN
```

In Java 17, the constants above are available (for instance `BigInteger.TWO` since Java 9). They are **shared immutable objects**.

```java
BigInteger count = BigInteger.ZERO;
count = count.add(BigInteger.ONE);
```

Using `BigInteger.ZERO` is clearer than `new BigInteger("0")`. However, do not assume that results of different operations are always the same object when equal in value; use `equals` for value comparison.

## 4. Immutability: Operations Do Not Modify the Original Object

A common mistake:

```java
BigInteger total = BigInteger.ZERO;
total.add(BigInteger.TEN);
System.out.println(total); // 0, not 10!
```

`add` created/returned the **result**, but the program did not store the result. To update the `total` variable, reassign it:

```java
BigInteger total = BigInteger.ZERO;
total = total.add(BigInteger.TEN);
System.out.println(total); // 10.
```

This does not change the value of the old object. Java only changes **the reference held in the `total` variable**.

### Visualizing with Two Variables Referencing the Same Object

```java
BigInteger a = new BigInteger("100");
BigInteger alias = a;
a = a.add(BigInteger.ONE);

System.out.println(a);     // 101.
System.out.println(alias); // 100.
```

Initially both variables `a` and `alias` reference the same `BigInteger(100)`. After reassignment, `a` references the result 101; `alias` still sees the unchanged object with value 100.

### Benefits of Immutability

1. **Fewer side effects:** a method receiving a `BigInteger` cannot alter the internal value of the object the caller holds.
2. **Easy sharing:** the same value can be referenced in many places without its numeric state being mutated.
3. **Convenient as keys:** `BigInteger` provides value-based `equals` and `hashCode`, suitable for `HashMap` or `HashSet`.
4. **Simplifies concurrency:** a safely published `BigInteger` object can be read by multiple threads without locks to prevent mutating that value.
5. **Easy reasoning:** the expression `a.add(b)` returns the result while keeping `a` and `b` intact.

**Limit of the thread-safety claim:** the immutability of `BigInteger` **does not make reassigning a shared variable atomic**. For example, `counter = counter.add(ONE)` on a shared variable can lose updates when multiple threads read/assign concurrently. For concurrent counters, proper synchronization or atomic tools suited to the problem are needed.

### No `++` and `+=` on `BigInteger`

```java
BigInteger n = BigInteger.ZERO;
// n++;       // Does not compile.
// n += 1;    // Does not compile.
n = n.add(BigInteger.ONE); // Correct.
```

Needing to produce a new value is part of the **API model**, not a quirk specific to `add`. `multiply`, `subtract`, `negate`, `abs`, `shiftLeft`, etc., all leave the receiver object unchanged rather than mutating it into another value.

## 5. Common Arithmetic Operations

| Method | Meaning | Example |
| --- | --- | --- |
| `a.add(b)` | `a + b` | `12 + 5 = 17` |
| `a.subtract(b)` | `a - b` | `12 - 5 = 7` |
| `a.multiply(b)` | `a × b` | `12 × 5 = 60` |
| `a.divide(b)` | Integer quotient, truncated toward 0 | `12 / 5 = 2` |
| `a.remainder(b)` | Remainder from integer division | `12 % 5 = 2` |
| `a.divideAndRemainder(b)` | Returns two-element array [quotient, remainder] | `[2, 2]` |
| `a.pow(n)` | Exponentiation with non-negative `int` exponent | `12^2 = 144` |
| `a.negate()` | Negation (flip sign) | `-12` |
| `a.abs()` | Absolute value | `12` |
| `a.gcd(b)` | Non-negative greatest common divisor | `gcd(54,24) = 6` |
| `a.signum()` | Sign of the number | −1, 0, or 1 |
| `a.min(b)` / `a.max(b)` | Smaller/larger value | Comparing two BigIntegers |

```java
BigInteger a = BigInteger.valueOf(12);
BigInteger b = BigInteger.valueOf(5);

System.out.println(a.add(b));      // 17
System.out.println(a.subtract(b)); // 7
System.out.println(a.multiply(b)); // 60
System.out.println(a.divide(b));   // 2
System.out.println(a.remainder(b)); // 2
```

The operations above are **not Java operator overloads**. For example, `a.multiply(b)` returns a `BigInteger` without changing `a`. `divide` and `remainder` throw `ArithmeticException` when the divisor is 0.

### Accumulating into a Result Variable in a Loop

```java
BigInteger sum = BigInteger.ZERO;

for (int i = 1; i <= 100; i++) {
    sum = sum.add(BigInteger.valueOf(i));
}
System.out.println(sum); // 5050.
```

If you omit `sum =` on the left, the result will remain 0. This is the **forgotten reassignment** bug caused by habit with mutable objects.

## 6. Integer Division, `remainder`, and `mod` Differ

`BigInteger.divide(b)` takes the integer quotient **truncated toward 0**; `remainder(b)` is the corresponding remainder and can be negative. With `a=-17,b=5`, the quotient is `-3` and the remainder is `-2`, satisfying `a=q*b+r`. If a non-negative remainder is needed, `mod(m)` selects the representative in `[0,m)` but **requires `m>0`**. Dividing by zero throws `ArithmeticException`. Getting quotient and remainder simultaneously and checking divisibility will be practiced separately.

## 7. Exponentiation, Bit Shifting, GCD, and Modular Arithmetic

`pow(int)` computes integer exponentiation with a non-negative exponent; `sqrt()` takes the integer square root of a non-negative value; `gcd(b)` returns the non-negative greatest common divisor. `shiftLeft(n)` operates on the bits of a signed integer, unlike a fixed 32/64-bit word representation. In modular arithmetic, `modPow(e,m)` computes modular exponentiation efficiently, while `modInverse(m)` exists only when the value and modulus are coprime. These are APIs with specific input preconditions, explained with concrete exercises in dedicated lessons.

## 8. Converting to `int`, `long`, and Data-Loss Traps

`intValue()` and `longValue()` can **truncate high bits**, for example `BigInteger.ONE.shiftLeft(32).intValue()` equals 0. If the API contract requires preserving the exact value, use `intValueExact()` or `longValueExact()` and handle `ArithmeticException` when it does not fit the corresponding signed range. Type conversion should be placed at the boundary where the application truly needs a primitive, not performed prematurely during large calculations.

## 9. Comparison, Equality, and Ordering

`a.compareTo(b)` determines the less-than/equal/greater-than relationship from the sign of the returned number; `a.equals(b)` compares equal `BigInteger` values; `a == b` compares only object references. `signum()` returns -1, 0, or 1; `abs()` and `negate()` operate on magnitude or negation while keeping the source object immutable. These rules matter for sorting code, boundary checks, and collection keys.

## 10. Two Different Ways of Interpreting Byte Arrays

`new BigInteger(bytes)` decodes **signed two's complement big-endian**, so a single byte `FF` is `-1`. `new BigInteger(1,bytes)` takes an unsigned magnitude with a separate positive sign, so byte `FF` is `+255`. `toByteArray()` outputs minimal signed two's complement; the positive number 128 requires `00 80` to keep the sign bit 0. When a protocol requires fixed-width or unsigned encoding, specify width, padding, and range checks instead of arbitrarily stripping leading bytes.

## 11. Bit Operations Without Default 32/64-Bit Limits

`and`, `or`, `xor`, `not`, `shiftLeft`, `shiftRight`, `testBit`, and `setBit` follow a **sign-extended** two's complement model. Therefore `BigInteger.valueOf(5).not()` is -6 rather than the value 250 of an **8-bit unsigned** inversion. If you must simulate a word of width `w`, apply an appropriate `2^w - 1` mask. Details of `bitLength`, `bitCount`, and bit-position operations are separated into their own lesson.

## 12. Real Limits of "Arbitrary Precision"

"Arbitrary precision" means **not being forced into a fixed primitive width**, not that the system has infinite memory or time.

Practical limits include:

1. **Heap memory:** a number with millions of digits requires large memory to store and manipulate.
2. **Computation time:** multiplying/dividing/GCD/`modPow` on numbers with millions of bits costs far more than primitive operations.
3. **Size and implementation limits:** the JDK has internal limits on bit count or array length; values cannot grow arbitrarily to infinity.
4. **Untrusted input:** gigantic numeric strings, large `pow` exponents, or random-number construction calls can cause unexpected resource consumption.
5. **Converting to fixed types:** when calling `intValue`, `longValue`, or `doubleValue`, you again face the target type's limits.
6. **Transport and formatting:** a very large number formatted as a decimal string can be megabytes long, adding overhead to logging, JSON, CSV, or databases.

**Do not put `BigInteger` inside hot loops just because it is "safer than int" if the problem only needs small numbers.** For summing millions of elements within the `long` range, `long` can be simpler and more efficient. When primitive overflow detection is needed, `Math.addExact`/`multiplyExact` can be used or upgraded to `BigInteger` according to specific requirements.

### Note on the Factorial Algorithm

Factorials grow very fast. `20!` fits in `long`, but `21!` already exceeds the signed `long` range. With `BigInteger`:

```java
static BigInteger factorial(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }
    BigInteger result = BigInteger.ONE;
    for (int i = 2; i <= n; i++) {
        result = result.multiply(BigInteger.valueOf(i));
    }
    return result;
}
```

This is an **illustrative method**, needing to be placed inside a class. It still needs **a bound on `n`** when accepting user input to avoid excessive resource requests. `BigInteger` provides precision, not an automatic computation quota.

### "Exact Arithmetic" Does Not Mean "Every Operation's Result Is Representable"

Integer addition, subtraction, and multiplication within the JDK-supported range are exact operations, with no floating-point rounding error. However, **integer division** still drops the fractional part because the result type is an integer. `BigInteger.ONE.divide(BigInteger.TWO)` returns 0; to represent `1/2`, you must choose a fraction consisting of `BigInteger` numerator/denominator or a decimal model with a rounding policy.

## 13. Randomness, Primes, and Cryptography: More Contracts Needed

`BigInteger` has several APIs for generating large/random numbers and working with primes, such as `probablePrime`, `isProbablePrime`, `nextProbablePrime`, and modular operations. These are very useful mathematical APIs, but their scope must be understood:

- `isProbablePrime(certainty)` pertains to probabilistic primality testing with a certainty level per the API contract, and **should not** casually be read as an absolute mathematical proof.
- If generating parameters for cryptography, the randomness source and parameter selection must meet standards; `java.util.Random` is not the default choice for secrets.
- `BigInteger` does not guarantee all operations are **constant-time**; do not roll your own cryptographic primitives assuming "exact BigInteger arithmetic" equals side-channel safety.
- For keys, signatures, and encryption, use `java.security`/`javax.crypto` APIs and appropriate protocol standards rather than assembling custom `BigInteger` operations.

In an introductory lesson, view modular arithmetic and primes as **additional capabilities**, without overshadowing the two main properties: **arbitrary precision** and **immutability**.

## 14. Input Handling and Data Exchange

When receiving very large integers from users, files, or APIs:

```java
String text = "123456789012345678901234567890";
BigInteger value = new BigInteger(text);
```

You should have a process:

1. Define the schema: signed/unsigned, radix, whether leading +/- is allowed, whether digit grouping is allowed.
2. Limit string length and value range **before** creating very large objects.
3. Do not assume `0x` prefixes or underscores in runtime `String`s: `new BigInteger("0xFF")` does not auto-parse hex like the compiler.
4. Catch `NumberFormatException` at data boundaries and return contextual errors.
5. Define serialization: decimal string, specific radix, or signed/unsigned bytes, with clear width and byte order.
6. If the receiver uses JavaScript `Number`, note that integers beyond `2^53` can lose precision; **schema-defined decimal strings** are often suitable for large IDs and numbers needing exact precision.
7. Do not send the result of `doubleValue` and treat it as a faithful copy of the original BigInteger.

`BigInteger.toString()` produces a decimal string without locale grouping:

```java
BigInteger big = new BigInteger("12345678901234567890");
String wireText = big.toString(); // "12345678901234567890".
```

This is a good representation if the protocol **already specifies a decimal string**. If the schema uses a JSON number, using a JSON library with an appropriate type can also be reasonable, but all consumers and precision requirements must be evaluated. Do not equate `toString` with a full JSON serializer.

## 15. Standalone Runnable Java 17+ Program

Save file `BigIntegerBasicsDemo.java`:

```java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerBasicsDemo {
    static BigInteger factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        BigInteger result = BigInteger.ONE;
        for (int i = 2; i <= n; i++) {
            result = result.multiply(BigInteger.valueOf(i));
        }
        return result;
    }

    public static void main(String[] args) {
        int wrapped = Integer.MAX_VALUE + 1;
        BigInteger base = BigInteger.valueOf(Integer.MAX_VALUE);
        BigInteger next = base.add(BigInteger.ONE);

        System.out.println("int overflow: " + wrapped);
        System.out.println("BigInteger result: " + next);
        System.out.println("Original unchanged: " + base);
        System.out.println("2^100: " + BigInteger.ONE.shiftLeft(100));
        System.out.println("20!: " + factorial(20));

        BigInteger negative = BigInteger.valueOf(-17);
        BigInteger five = BigInteger.valueOf(5);
        System.out.println("divide (-17,5): " + negative.divide(five));
        System.out.println("remainder (-17,5): " + negative.remainder(five));
        System.out.println("mod (-17,5): " + negative.mod(five));
        System.out.println("gcd(54,24): "
                + BigInteger.valueOf(54).gcd(BigInteger.valueOf(24)));
        System.out.println("2^10: " + BigInteger.TWO.pow(10));
        System.out.println("sqrt(1000): "
                + new BigInteger("1000").sqrt());

        System.out.println("hex ff: " + new BigInteger("ff", 16));
        System.out.println("255 in hex: "
                + BigInteger.valueOf(255).toString(16));

        System.out.println("negative one bytes: "
                + Arrays.toString(BigInteger.valueOf(-1).toByteArray()));
        System.out.println("unsigned ff byte: "
                + new BigInteger(1, new byte[] {(byte) 0xff}));

        System.out.println("intValue overflow: " + next.intValue());
        try {
            next.intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("intValueExact: rejected");
        }
        System.out.println("long max + 1: "
                + BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        System.out.println("equals same value: "
                + new BigInteger("42").equals(BigInteger.valueOf(42)));
        System.out.println("compare 99 vs 100: "
                + BigInteger.valueOf(99).compareTo(BigInteger.valueOf(100)));
        System.out.println("modPow(3,13,7): "
                + BigInteger.valueOf(3).modPow(
                        BigInteger.valueOf(13), BigInteger.valueOf(7)));
        System.out.println("signum(-17): " + negative.signum());
    }
}
```

Compile and run:

```bash
javac --release 17 BigIntegerBasicsDemo.java
java BigIntegerBasicsDemo
```

Stdout:

```text
int overflow: -2147483648
BigInteger result: 2147483648
Original unchanged: 2147483647
2^100: 1267650600228229401496703205376
20!: 2432902008176640000
divide (-17,5): -3
remainder (-17,5): -2
mod (-17,5): 3
gcd(54,24): 6
2^10: 1024
sqrt(1000): 31
hex ff: 255
255 in hex: ff
negative one bytes: [-1]
unsigned ff byte: 255
intValue overflow: -2147483648
intValueExact: rejected
long max + 1: 9223372036854775808
equals same value: true
compare 99 vs 100: -1
modPow(3,13,7): 3
signum(-17): -1
```

The lines demonstrate in turn: primitive overflow; BigInteger addition leaving the original object unmodified; numbers exceeding 64 bits; exact calculation; integer division and the difference between `remainder`/`mod`; radix conversion; signed/unsigned bytes; unchecked narrowing to `int` versus `intValueExact`; and modular operations.

## 16. Choosing `int`, `long`, `BigInteger`, or `BigDecimal`?

| Need | Typically suitable type | Things to note |
| --- | --- | --- |
| Array indices, counts fitting in 32 bits | `int` | Natural API access, lightweight; check overflow when needed |
| Timestamps, quantities, numeric IDs fitting in 64 bits | `long` | Fixed width; avoid precision loss on binary64 clients |
| Very large integers, factorials, powers, exact integer math | `BigInteger` | Immutable; method-based operations and resource cost proportional to size |
| Decimals needing exact math, money, scaled values | `BigDecimal` | Requires rounding/scale policy |
| Continuous measurements allowing binary64 error | `double` | Does not represent all decimal fractions exactly |
| Approximate results focused on low memory | `float` if error is acceptable | Lower precision than double |
| Concurrently updated counters within int/long range | `AtomicInteger`/`AtomicLong` or synchronization | Immutable BigInteger does not provide atomic updates on its own |
| Numbers exceeding all primitives needing exact transmission | `BigInteger` + text/binary schema | Specify signedness, radix, width, client support |

Do not choose `BigInteger` just because an input looks like "many digits" if it is actually an identifier not used for arithmetic: many data types need to preserve leading `0` characters, separators, or original formatting, so `String` can be semantically more accurate.

## 17. Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `+`, `-`, `*` on two `BigInteger`s | Does not compile | `add`, `subtract`, `multiply` |
| Calling `a.add(b)` without storing the result | `a` stays unchanged | `a = a.add(b)` or use a result variable |
| Assuming `BigInteger` makes every calculation "exact decimal" | It is an **integer**-only type | Use `BigDecimal` or a Rational type when fractions exist |
| Converting a large number to `long` before computing | Can lose bits before using `BigInteger` | Construct directly from string or keep as BigInteger |
| Using `intValue()`/`longValue()` as checked conversions | Can lose bits / flip sign | `intValueExact()`/`longValueExact()` |
| Trusting `doubleValue()` not to lose digits | Binary64 has a 53-bit significand | Keep BigInteger if all digits are needed |
| Using `a == b` to compare two BigIntegers | Compares object identity, not value | `a.equals(b)` |
| Using `a > b` | No operators on objects | `a.compareTo(b) > 0` |
| Confusing `remainder` with `mod` for negative numbers | One can be negative, the other non-negative | Read the contract and pick the right API |
| Calling `mod` with 0 or negative modulus | `ArithmeticException` | Validate positive modulus |
| Thinking `divide` produces fractional digits | Integer division, truncates fraction | Choose a fraction model or BigDecimal |
| Thinking `BigInteger.valueOf` accepts any number beyond long | Method accepts `long` | `new BigInteger(decimalText)` |
| Parsing `"0xFF"` directly with decimal constructor | `NumberFormatException` | `new BigInteger("FF",16)` or normalize |
| Using `new BigInteger(new byte[]{(byte)0xff})` to get 255 | Returns −1 due to signed two's complement | `new BigInteger(1,magnitude)` |
| Assuming every produced byte array is fixed width | `toByteArray` length follows signed representation | Codec padding/width per schema |
| Believing `counter = counter.add(ONE)` is atomic | Multiple threads can overwrite results | Appropriate synchronization/atomic update mechanism |
| Allowing unbounded exponents or input lengths | Can exhaust CPU/heap | Apply quotas and validate input |
| Building cryptography solely out of `modPow` | Lacks security standards, randomness, side-channel protection | Use vetted crypto libraries and protocols |

## 18. Self-Check Questions

1. Why does `Integer.MAX_VALUE + 1` yield a negative number, whereas `BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE)` yields 2147483648?
2. Does `BigInteger` "arbitrary precision" mean every operation is free of memory and time limits?
3. Does `BigInteger a = BigInteger.ZERO; a.add(ONE);` change `a`? Rewrite it so `a` actually references the value 1.
4. Two variables point to `BigInteger("100")`; after one variable is assigned the result of `add(ONE)`, what value does the other still see? Why?
5. Why can't `BigInteger` use `+` like `int`? What are the equivalent methods?
6. How do `new BigInteger("ff",16)` and `new BigInteger("0xff")` differ?
7. Compare `divide`, `remainder`, and `mod` when the dividend is −17 and the divisor/modulus is 5.
8. When can `intValue`/`longValue` lose data? Why are the `Exact` versions safer?
9. What value does a one-byte array `0xff` become when calling `new BigInteger(bytes)`? What do you do if you want positive 255?
10. Why is `BigInteger.valueOf(Long.MAX_VALUE).add(ONE)` valid while `BigInteger.valueOf(9223372036854775808L)` is not a valid `long` literal?
11. When should `equals` be used and when should `compareTo` be used with `BigInteger`? Why not use `==` for value comparison?
12. Why does `BigInteger.ONE.divide(BigInteger.TWO)` not return 0.5? How can exact fractions be represented?
13. Is sharing a `BigInteger` across multiple threads safe? What remains unsafe when multiple threads **update a shared reference variable**?
14. When sending a very large BigInteger to a JavaScript client using `Number`, what can happen? What should the exchange schema decide?
15. Why do extremely large `pow` exponents still need input limits even when using arbitrary precision?
16. When should `BigInteger.modPow` be used instead of computing `pow` then `mod`? Does that automatically create a secure cryptosystem?

## 19. Official References

- [Java SE 17 — `java.math.BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): Value creation API, arithmetic, immutability, exact conversion, modular arithmetic, byte representation, and implementation limits.
- [Java SE 17 — `java.lang.Number`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): Conversion methods `intValue`, `longValue`, `floatValue`, `doubleValue` and potential information loss.
- [Java SE 17 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): Exact decimals with scale and rounding policies, used when data is no longer purely integers.
- [Java Language Specification `4.2.1–`4.2.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): Integer primitive ranges and integer operations.
- [Java SE 17 — `Math` exact methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, and checked arithmetic options when staying with primitives.

**Key takeaway:** `BigInteger` represents **signed integers with arbitrary precision within resource limits**, and is **immutable**. `add`, `multiply`, `pow`, and other methods return new values; to use the result, you must capture/reassign it. Every conversion down to `int`/`long` or `double` is a potentially lossy boundary; choose `...ValueExact()` when preservation is required. Distinguish `remainder` from `mod`, pay attention to signed bytes and data schema design, and do not mistake the immutability of numeric values for atomic updates to a shared variable.