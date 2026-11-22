# Choosing BigInteger for Numeric Strings Exceeding long Limits in Java

## 1. When do you need BigInteger?

If the input is a **string representing a decimal integer** and the value can exceed the limits of **long**, use **java.math.BigInteger** when you need to preserve the **exact arithmetic value**.

The range of long is:

- **Long.MIN_VALUE = −9223372036854775808** (−2^63).
- **Long.MAX_VALUE = 9223372036854775807** (2^63−1).

For example, the string **"9223372036854775808"** is only 1 greater than Long.MAX_VALUE yet already cannot be represented as a positive number in long. The string **"-9223372036854775809"** is only 1 less than Long.MIN_VALUE. Both can be represented accurately using BigInteger.

~~~java
import java.math.BigInteger;

BigInteger aboveMax = new BigInteger("9223372036854775808");
BigInteger belowMin = new BigInteger("-9223372036854775809");
~~~

These two lines are an illustrative snippet, used inside a Java method/class. **BigInteger** represents signed integers with arbitrary precision, subject to resource and implementation limits rather than a 64-bit cap.

**The deciding factor is not string length alone**, but the **value range to support** and **how the data is used afterward**. A 30-digit string starting with many zeros can still be a small number; conversely, a 19-digit positive number can already exceed Long.MAX_VALUE.

## 2. Distinguishing three problems before choosing a type

| Scenario | Typically suitable representation | Reason |
| --- | --- | --- |
| Integer always lies within 64-bit signed range | **long/Long** | Compact, fast, supports primitive arithmetic |
| Integer can exceed signed long and needs exact calculation | **BigInteger** | Does not overflow the long range during ordinary operations |
| Digit-only identifier, possibly with leading zeros, not used in math | **String** | Preserves all characters, including leading zeros and formatting |
| Number with fractional part needing decimal precision | **BigDecimal** | BigInteger represents **integers** only |
| 64-bit unsigned numeric string needing exact positive values up to 2^64−1 | **BigInteger** | long still uses a sign bit and cannot hold the whole range as positive numbers |
| Data only needs a 64-bit unsigned bit pattern and APIs are designed for it | **long** with unsigned APIs | Must adhere consistently to unsigned conventions, never treating long as positive |

If it is an account number, phone number, postal code, or ID **without arithmetic operations**, keeping it as String is usually more accurate. Converting **"000123"** to BigInteger and printing it back gives **"123"**: the numeric value is unchanged, yet the identifier may already be broken.

If the problem genuinely involves addition, subtraction, multiplication, division, primality testing, integer exponentiation, or processing very large integers, BigInteger is the direct choice.

## 3. Why Long.parseLong fails and why you shouldn't cast through double

~~~java
long maximum = Long.parseLong("9223372036854775807"); // Valid

// At runtime, this throws NumberFormatException:
// long tooLarge = Long.parseLong("9223372036854775808");
~~~

**Long.parseLong** throws **NumberFormatException** when the string has invalid syntax *or* when the value exceeds the long range. If you need to distinguish syntax errors from range overflow, validate the string per input rules and then compare the BigInteger value against the two long bounds.

Do not convert through **double** to bypass long limits: double can represent very large numbers in *magnitude*, yet cannot represent every integer accurately as magnitude grows. Adjacent integers can round to the same double, because double's significand has only 53 bits of precision.

~~~java
double a = 9007199254740992.0; // 2^53
double b = 9007199254740993.0; // rounds to the same double as a
boolean equal = (a == b);       // true
~~~

If the string has passed through a system outside Java, such as a JSON consumer using JavaScript Number, the value may already have lost precision **before** entering Java. For large numbers needing cross-system exactness, transmit decimal strings or use an agreed-upon big-number type.

## 4. Creating BigInteger directly from String

Add the import:

~~~java
import java.math.BigInteger;
~~~

The most common constructor is **new BigInteger(String val)**, which decodes a signed decimal integer value:

~~~java
BigInteger zero = new BigInteger("0");
BigInteger positive = new BigInteger("+123456789012345678901234567890");
BigInteger negative = new BigInteger("-123456789012345678901234567890");
BigInteger withZeros = new BigInteger("00000099"); // numeric value 99
~~~

The input string may have a leading **+** or **−** sign; the sign cannot stand alone. The constructor rejects invalid syntax with NumberFormatException.

Examples of strings **that should not be passed straight to the decimal constructor**:

| String | Issue |
| --- | --- |
| **""** | No digits |
| **"+"**, **"-"** | Sign only |
| **"12.0"** | Has fractional part, not an integer |
| **"1_000"** | Underscores are Java source literal syntax, not string decimal syntax |
| **" 123 "** | Leading/trailing whitespace; constructor does not automatically trim |
| **"0xFF"** | 0x prefix is not automatically recognized by the decimal constructor |

If business rules allow outer whitespace, you can call **strip()** before parsing. However, decide this rule at the input boundary; never automatically delete characters when they carry meaning.

### Choosing a radix with the two-parameter constructor

**new BigInteger(String val, int radix)** supports reading bases from **Character.MIN_RADIX = 2** to **Character.MAX_RADIX = 36**:

~~~java
BigInteger binary = new BigInteger("101010", 2); // 42
BigInteger hex = new BigInteger("FF", 16);        // 255
BigInteger negativeHex = new BigInteger("-FF", 16); // -255
~~~

When using radix 16, pass **"FF"**, not **"0xFF"** expecting the constructor to strip the prefix. If the input format specifies a **0x** prefix, validate and strip the exact prefix per protocol before calling the constructor.

**BigInteger.toString()** gives normalized decimal form; **toString(16)** gives a hexadecimal string (lowercase by default, without a "0x" prefix). Negative values carry a minus sign:

~~~java
BigInteger value = new BigInteger("9223372036854775808");
String hex = value.toString(16);   // "8000000000000000"
BigInteger parsedBack = new BigInteger(hex, 16);
boolean same = parsedBack.equals(value); // true
~~~

## 5. Validating input before parsing very large numbers

The BigInteger constructor reports syntax errors, yet for untrusted input, applications typically must enforce **length limits** and **accepted digit sets** to prevent excessive resource consumption.

For example, a contract accepts only **ASCII digits 0..9**, an optional leading sign, and at most N digits. The following method validates strictly against that contract:

~~~java
static BigInteger parseDecimal(String text, int maxDigits) {
    if (text == null || maxDigits < 1) {
        throw new IllegalArgumentException("Invalid input or limit");
    }

    int start = text.startsWith("+") || text.startsWith("-") ? 1 : 0;
    int count = text.length() - start;

    if (count < 1 || count > maxDigits) {
        throw new IllegalArgumentException("Invalid digit count");
    }

    for (int i = start; i < text.length(); i++) {
        char digit = text.charAt(i);
        if (digit < '0' || digit > '9') {
            throw new IllegalArgumentException("Expected ASCII decimal digits");
        }
    }

    return new BigInteger(text);
}
~~~

This is a **member method placed inside a class**, requiring `import java.math.BigInteger`. The function will:

1. Reject null or invalid maxDigits.
2. Allow an optional **+/-** sign, excluded from the digit quota.
3. Reject strings with no digits, too many digits, or characters outside ASCII 0..9.
4. Construct BigInteger only once syntax meets all conditions.

This method intentionally **rejects whitespace, grouping separators, underscores, non-ASCII Unicode digits, and exponent notation**. If a product needs those formats, define an appropriate parser rather than accepting them silently.

The **maxDigits** cap is not a fixed constant for all applications: set it per API contract and capacity. A number with millions of digits incurs both parse/storage cost and high CPU/memory cost for later multiplication or exponentiation. Resource limits remain necessary even though BigInteger has no 64-bit limit.

## 6. Checking whether a BigInteger fits in the long range

Do not use **longValue()** to check whether a number fits in long: that method can **truncate high bits** without reporting an error.

Use **compareTo** against both range endpoints:

~~~java
static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);

static boolean fitsLong(BigInteger value) {
    return value.compareTo(LONG_MIN) >= 0
            && value.compareTo(LONG_MAX) <= 0;
}
~~~

These are fields/methods placed inside a class. **BigInteger.compareTo** returns a negative number, 0, or a positive number depending on less/greater/equal relation; never compare BigInteger with **<** or **>** operators.

If you are certain the value fits in long, convert accurately with **longValueExact()**:

~~~java
BigInteger ok = new BigInteger("1234567890123");
long n = ok.longValueExact(); // 1234567890123L
~~~

If out of range, **longValueExact()** throws **ArithmeticException** instead of producing a wrong result. **intValueExact()**, **shortValueExact()**, and **byteValueExact()** provide equivalent behavior for narrower ranges.

### Why can longValue() be dangerous?

~~~java
BigInteger above = new BigInteger("9223372036854775808");
long truncated = above.longValue(); // -9223372036854775808
// above.longValueExact() -> ArithmeticException
~~~

**9223372036854775808 = 2^63**. When converted via **longValue()**, the low 64 bits are interpreted as a signed long, becoming **Long.MIN_VALUE**. The sign flips without any exception.

Rule of practice: use **longValueExact()** at API boundaries requiring long, and use **longValue()** only when deliberately extracting low bits per documented semantics.

## 7. Performing exact arithmetic with BigInteger

Unlike primitives, BigInteger is an **immutable object**. Each operation creates/returns a result object; it never mutates the mathematical value of the existing object.

| Operation | BigInteger API |
| --- | --- |
| Add, subtract | **add**, **subtract** |
| Multiply | **multiply** |
| Integer division | **divide** |
| Division remainder | **remainder** |
| Quotient and remainder together | **divideAndRemainder** |
| Compare | **compareTo**, **equals** |
| Absolute value, negate | **abs**, **negate** |
| Non-negative integer power | **pow(int exponent)** |
| Bit shifts | **shiftLeft**, **shiftRight** |
| Bit inspection | **bitLength**, **testBit** |

Example:

~~~java
BigInteger a = new BigInteger("9223372036854775808");
BigInteger b = a.add(BigInteger.TWO);           // 9223372036854775810
BigInteger product = a.multiply(BigInteger.valueOf(3));
// 27670116110564327424

BigInteger[] result = a.divideAndRemainder(BigInteger.valueOf(10));
// result[0] = 922337203685477580, result[1] = 8
~~~

Constants **BigInteger.ZERO**, **ONE**, and **TEN** work in Java 17; **BigInteger.TWO** is also available since Java 9. Avoid writing **a + b** when a and b are BigInteger because there is no operator overloading for plus on objects.

**BigInteger.divide** performs integer division, rounding the quotient toward 0. If you need fractional decimals from division, use **BigDecimal** or a rational format per contract. For negative numbers, **remainder** and **mod** are not always interchangeable: **mod** requires a positive modulus and returns a non-negative value.

## 8. 64-bit unsigned strings: two different ranges

The 64-bit unsigned integer range is **0 .. 18446744073709551615** (2^64−1), larger than the maximum positive signed long.

~~~java
String digits = "18446744073709551615";
BigInteger unsignedMax = new BigInteger(digits); // positive, exact
long bits = Long.parseUnsignedLong(digits);      // -1 as signed long
String recovered = Long.toUnsignedString(bits);  // "18446744073709551615"
~~~

**Long.parseUnsignedLong** fits when storing a **64-bit pattern** and consistently using **compareUnsigned**, **divideUnsigned**, **remainderUnsigned**, and **toUnsignedString**. If business logic needs to compare, add/subtract, or compute on an **unsigned positive integer** with values that may exceed 2^64−1, BigInteger is usually more direct and less error-prone.

Never call **Long.parseUnsignedLong** and then compare with the ordinary **>** operator: the internal long value can be negative due to the sign bit. Keep signed-vs-unsigned usage consistent.

## 9. When data comes from APIs, JSON, CSV, and databases

**CSV/text:** read as String, validate syntax/length, parse BigInteger. On output, call **toString()**. If leading zeros or original formatting must be preserved, store the **raw string** as well, because BigInteger normalizes numeric representation.

**JSON:** under the JSON standard, numeric tokens do not guarantee every consumer stores huge integers accurately. Many JavaScript applications use **Number** and represent integers accurately only within the safe range **±(2^53−1)**. Agree on a contract transmitting big integers as **strings**, or use an agreed parser/BigInt mechanism. Never blindly send BigInteger as a JSON number assuming every client will read it accurately.

**Database:** choose a column type supporting the data range and matching mapping library, such as a **DECIMAL/NUMERIC** type with sufficient precision if supported by the DBMS. Do not assume SQL BIGINT supports unbounded BigInteger, because many DBMSs use 64-bit BIGINT. Check precision, scale, overflow/truncation, and driver behavior against the actual database.

**Message queue/gRPC:** an explicit wire format is required. A fixed int64 field cannot represent positive numbers above 2^63−1 under signed semantics. You can use decimal strings or an agreed byte representation if required by the system.

## 10. Complete Java 17+ program and actual output

Create file **BigIntegerTextDemo.java**:

~~~java
import java.math.BigInteger;

public class BigIntegerTextDemo {
    static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
    static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);

    static BigInteger parseDecimal(String text, int maxDigits) {
        if (text == null || maxDigits < 1) {
            throw new IllegalArgumentException("Invalid input or limit");
        }

        int start = text.startsWith("+") || text.startsWith("-") ? 1 : 0;
        int count = text.length() - start;

        if (count < 1 || count > maxDigits) {
            throw new IllegalArgumentException("Invalid digit count");
        }

        for (int i = start; i < text.length(); i++) {
            char digit = text.charAt(i);
            if (digit < '0' || digit > '9') {
                throw new IllegalArgumentException("Expected ASCII decimal digits");
            }
        }
        return new BigInteger(text);
    }

    static boolean fitsLong(BigInteger value) {
        return value.compareTo(LONG_MIN) >= 0
                && value.compareTo(LONG_MAX) <= 0;
    }

    public static void main(String[] args) {
        BigInteger above = parseDecimal("9223372036854775808", 24);
        BigInteger below = parseDecimal("-9223372036854775809", 24);
        BigInteger unsignedMax =
                parseDecimal("18446744073709551615", 24);

        System.out.println("Long.MAX_VALUE: " + Long.MAX_VALUE);
        System.out.println("First above long: " + above);
        System.out.println("Above fits long: " + fitsLong(above));
        System.out.println("Below fits long: " + fitsLong(below));
        System.out.println("Unsigned 64 max: " + unsignedMax);
        System.out.println("Unsigned max fits signed long: "
                + fitsLong(unsignedMax));

        System.out.println("Leading zeros: "
                + parseDecimal("+0009223372036854775808", 24));
        System.out.println("Above + 2: " + above.add(BigInteger.TWO));
        System.out.println("Above * 3: "
                + above.multiply(BigInteger.valueOf(3)));

        System.out.println("Above in hex: " + above.toString(16));
        System.out.println("Round trip: "
                + new BigInteger(above.toString(16), 16).equals(above));
        System.out.println("Truncated longValue: " + above.longValue());

        try {
            System.out.println(above.longValueExact());
        } catch (ArithmeticException e) {
            System.out.println("longValueExact: out of range");
        }

        try {
            System.out.println(Long.parseLong("9223372036854775808"));
        } catch (NumberFormatException e) {
            System.out.println("parseLong: out of range");
        }

        try {
            parseDecimal("1_000", 24);
        } catch (IllegalArgumentException e) {
            System.out.println("strict decimal: invalid syntax");
        }

        System.out.println("Matches MAX + ONE: "
                + above.equals(LONG_MAX.add(BigInteger.ONE)));
        System.out.println("Unsigned parse as long: "
                + Long.parseUnsignedLong("18446744073709551615"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 BigIntegerTextDemo.java
java BigIntegerTextDemo
~~~

Stdout output:

~~~text
Long.MAX_VALUE: 9223372036854775807
First above long: 9223372036854775808
Above fits long: false
Below fits long: false
Unsigned 64 max: 18446744073709551615
Unsigned max fits signed long: false
Leading zeros: 9223372036854775808
Above + 2: 9223372036854775810
Above * 3: 27670116110564327424
Above in hex: 8000000000000000
Round trip: true
Truncated longValue: -9223372036854775808
longValueExact: out of range
parseLong: out of range
strict decimal: invalid syntax
Matches MAX + ONE: true
Unsigned parse as long: -1
~~~

**Key takeaways:**

- The positive number **2^63** does not fit in signed long, yet BigInteger preserves it intact.
- When converting back to long, **longValue()** takes the low 64 bits and can turn negative; **longValueExact()** throws an error.
- The integer **2^64−1** can be stored as a positive BigInteger, whereas Long.parseUnsignedLong returns a bit pattern that signed long reads as −1.
- Strings with a plus sign and leading zeros parse into a **normalized numeric value**, without retaining the string formatting.
- add/multiply operations remain exact across the illustrated range.

## 11. Performance and resource safety

BigInteger supports very large integers, yet **is not free**:

- Parsing long strings allocates large data structures and takes CPU time.
- Multiplication, division, exponentiation, and modular exponentiation grow in cost with number length.
- If a network request can send a string with millions of digits, limit **digit count and resources** before constructing or computing on BigInteger.
- If every value is proven to fit in long, primitive long is usually simpler and more efficient.
- BigInteger is immutable and thread-safe as an immutable value, yet shared reference updates must still follow concurrency rules.

Do not optimize by **slicing the first 19 digits and calling parseLong**: that loses data and mishandles signs, leading zeros, or multi-digit numbers. When accuracy is needed, parse the true value or reject with a clear error.

## 12. Common mistakes

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| Using Long.parseLong thinking it auto-expands on overflow | NumberFormatException | Parse BigInteger if the range can exceed long |
| Using double to hold huge integers | Can lose low digits | Use BigInteger when integer exactness is required |
| Using BigInteger.longValue() to check if it fits in long | Truncates high bits, can flip sign | compareTo against bounds or longValueExact() |
| Assuming length > 19 digits always exceeds long | Leading zeros can keep the value small | Parse/normalize then compare range |
| Assuming 19 digits always fits in long | 9223372036854775808 already exceeds Long.MAX_VALUE | Compare against both exact bounds |
| Assuming parseUnsignedLong gives a positive long above MAX_VALUE | Result is a signed long bit pattern | Use unsigned APIs consistently or BigInteger |
| Using + operator on two BigIntegers | Does not compile | Use a.add(b) |
| Not assigning the return value of add | Old object is unchanged | Assign result = a.add(b) |
| Assuming BigInteger preserves leading zeros | toString normalizes numeric form | Keep original String if needed |
| Parsing unbounded huge numbers from clients | CPU and memory exhaustion risk | Limit length and processing scope |
| Using BigInteger for decimal numbers with a point | NumberFormatException | Consider BigDecimal |
| Treating SQL BIGINT as synonymous with BigInteger | May be capped at 64 bits | Check column type and precision |

## 13. Self-check exercises

**Exercise 1.** Why can **"9223372036854775808"** not be parsed by Long.parseLong, yet can be parsed by BigInteger?

*Answer:* Its value equals **2^63**, exceeding the signed long maximum **2^63−1**; BigInteger is not limited to 64 bits.

**Exercise 2.** If a BigInteger representing **2^63** is converted via longValue(), what is the signed result?

*Answer:* **−9223372036854775808** because the low 64 bits are interpreted as a signed long. **longValueExact()** must throw ArithmeticException.

**Exercise 3.** Is the string **"00000000000000000000000042"** necessarily greater than Long.MAX_VALUE?

*Answer:* No; its integer value is 42. Raw digit count alone is insufficient to determine range when leading zeros are present.

**Exercise 4.** Why should an identifier **"00042"** probably not be converted to BigInteger?

*Answer:* If the leading zeros are part of the identifier, BigInteger normalizes it to "42" and loses the original form.

**Exercise 5.** If an application uses 64-bit unsigned values and receives **"18446744073709551615"**, which approach should be chosen to continue arithmetic on a **positive value**?

*Answer:* BigInteger represents that positive number directly. If storing long as a bit pattern, unsigned APIs must be used consistently; signed operators can yield negative results.

**Exercise 6.** How do you return a long when a BigInteger fits in range, while rejecting it when it does not?

*Answer:* Use **longValueExact()**, optionally checking beforehand with **compareTo(Long.MIN_VALUE/MAX_VALUE)** converted to BigInteger.

**Exercise 7.** Why must input digit count be limited even though BigInteger has arbitrary precision?

*Answer:* Parsing, storing, and computing on huge numbers still cost CPU and memory; limits prevent uncontrolled resource usage.

## 14. Official documentation

- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): String/radix constructors, toString, compareTo, immutable arithmetic, and longValueExact.
- [Long Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): 64-bit signed limits, parseLong, parseUnsignedLong, toUnsignedString.
- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): when data has fractional decimal parts.
- [Java Language Specification SE 17 — Integer Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): ranges and representations of primitive int/long.