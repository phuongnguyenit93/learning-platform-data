# Resource Limits for Very Large BigInteger or BigDecimal Inputs

## 1. Why Do "Exact, Unbounded" Numbers Still Need Limits?

`java.math.BigInteger` and `java.math.BigDecimal` overcome the range or precision limits of primitive integer and floating-point types in many situations. Even so, **arbitrary precision** does not mean memory, CPU, processing time, or output length are infinite.

When receiving numeric strings from users, APIs, files, or message queues, an application can face three categories of input:

1. **Very long digit sequences**: e.g., an integer containing millions of digits. Simply receiving, storing, validating, and scanning the string consumes resources; constructing `BigInteger` must also build a huge integer representation.
2. **Short strings with huge exponents**: e.g., `"1E+1000000000"`. The input has very few characters, yet the `BigDecimal` has a massive negative scale. Attempting plain output via `toPlainString()` can require allocating a gigantic string.
3. **Modest-looking inputs whose operations blow up**: e.g., left-shifting a `BigInteger` by millions of bits or raising to a very large exponent. Intermediate results can dwarf the inputs.

Consequences can include excessive RAM usage, GC pressure, CPU saturation, high latency, `OutOfMemoryError`, timeouts, exhausted service quotas, or *denial of service*. Never assume constructors will automatically enforce business-appropriate limits.

**Design goal:** establish resource budgets before parsing, before size-expanding operations, and before converting numbers into output strings. Every limit must be determined from **business context**, rather than taking example constants from this article as production defaults.

## 2. Understanding Data Size and Cost

### BigInteger: Digit Sequences and Bit Counts

`BigInteger` represents arbitrary-magnitude integers. A decimal string `d` digits long typically needs about \(d \times \log_2(10)\), or roughly \(3.322d\) bits to represent magnitude (an estimate excluding object headers, arrays, and temporary buffers).

For example, one million decimal digits corresponds to roughly 3.32 million bits—hundreds of KiB for the raw bit data alone in theory. Yet the actual pipeline must also hold the input string, arrays, objects, temporary structures, and resources for parsing/calculation algorithms. **Never treat bit-count estimates as a guarantee of actual RAM usage.**

`BigInteger.bitLength()` reports the minimum bit length per the API contract (negative numbers have their own rule); `toString().length()` is the decimal representation length, which can require substantial conversion work. When inputs are untrusted, **count digits on the string first**, before constructing `BigInteger`.

Operations that can grow results rapidly:

- `a.multiply(b)`: result bit count is roughly the sum of both operands' bit counts.
- `a.shiftLeft(n)`: bit count can grow by roughly `n` when `n` is huge.
- `a.pow(n)`: result digit/bit count can scale with `n`, even when `a` is short.
- `modPow`, division, `gcd`, primality testing: time cost depends on operand size and algorithm; bounding input length alone is not enough.

### BigDecimal: Precision, Scale, and Exponent

`BigDecimal` consists of an unscaled integer value (*unscaled value*) and an `int` `scale`:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`precision()` is the digit count of the unscaled value (zero has precision 1). `scale()` can be negative, positive, or zero:

| Input | Precision | Scale | Meaning |
|---|---:|---:|---|
| `"123.4500"` | 7 | 4 | Value 123.4500, retaining 4 digits after decimal point |
| `"1E+6"` | 1 | -6 | Value one million |
| `"1E-7"` | 1 | 7 | Value one ten-millionth |
| `"0.00"` | 1 | 2 | Value 0 with scale 2 |

**Small precision does not mean small output.** `new BigDecimal("1E+1000000")` has unscaled value `1` and scale `-1000000`, yet `toPlainString()` must render a `1` followed by one million zeros. Meanwhile `toString()` can stay in very short scientific notation. Therefore, you need separate policies for **scale/exponent** and **output string length**.

Even if an exponent string exceeds Java's allowed range and the constructor throws `NumberFormatException`, the application still should not leave detection to the constructor after already ingesting an unbounded payload. Early limits keep outcomes controllable and reduce risk before allocating large objects.

## 3. First Line of Defense: Bounding Input Before Parsing

A numeric input policy should explicitly state:

| Limit | What It Protects | How to Enforce |
|---|---|---|
| Total request/file/message size | Memory and I/O of the whole payload | Limits at HTTP gateway, message consumer, file reader |
| `maxTextChars` or `maxBytes` | String memory and scanning cost | Check before building numbers; bound bytes at transport layer |
| Mantissa/integer digit count | Parsing cost and unscaled value size | Count `0..9` characters before constructor |
| Exponent digit count | Reject abnormally long exponents | Inspect part after `E`/`e` |
| Absolute exponent magnitude | Avoid extreme scales and bloated output strings | Parse exponent as integer with overflow check |
| Absolute scale magnitude | Bound decimal/scientific forms and operations | Verify `scale()` after parse, with pre-parse budget |
| Output string length | Prevent `toPlainString()` from generating huge strings | Estimate before calling string-formatting methods |
| Bit and operation budget | Huge intermediate results, high CPU | Predict growth and reject operations exceeding quota |

**Do not rely solely on `text.length()`.** The string `"1E+1000000"` has few characters yet its decimal form can be massive. Conversely, a string of millions of zeros must be blocked even though its mathematical value is 0.

For untrusted data, prefer a **simple agreed grammar**: ASCII characters only, optional `+`/`-` per policy, at most one `.` if decimal, optional exponent with `E`/`e`, and no whitespace or foreign characters. This also avoids locale-separator confusion: `BigDecimal(String)` uses Java's numeric syntax, not arbitrary regional UI formatting.

If data arrives in JSON, consider receiving exact decimal values as **strings** when text/precision must be preserved; set body limits and value length limits **before** deserialization layers construct `BigInteger`/`BigDecimal` automatically. Avoid parsing arbitrary numbers into `double` first and converting to `BigDecimal` afterward, as that can lose precision.

## 4. Java 17+ Program Validating Before Constructing and Before Formatting

This example uses an **illustrative policy**, not recommended parameters for every system: strings at most 80 UTF-16 chars, at most 20 digits in the numeric part, exponent at most 3 digits and magnitude at most 30, `|scale| <= 30`, plain form at most 32 characters, left-shift result at most 128 bits. In the example, all inputs permit ASCII characters only, so `String.length()` matches character count; request byte limits must still be handled at the transport layer.

Save the file **`SafeBigNumbers.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class SafeBigNumbers {
    private static final int MAX_TEXT_CHARS = 80;
    private static final int MAX_DIGITS = 20;
    private static final int MAX_EXPONENT_DIGITS = 3;
    private static final int MAX_ABS_EXPONENT = 30;
    private static final int MAX_ABS_SCALE = 30;
    private static final int MAX_PLAIN_CHARS = 32;
    private static final int MAX_RESULT_BITS = 128;

    private static boolean decimalDigit(char c) {
        return c >= '0' && c <= '9';
    }

    public static BigInteger parseInteger(String text) {
        if (text == null || text.isEmpty()
                || text.length() > MAX_TEXT_CHARS) {
            throw new IllegalArgumentException("invalid integer length");
        }

        int i = (text.charAt(0) == '-' || text.charAt(0) == '+')
                ? 1 : 0;
        int digits = 0;

        for (; i < text.length(); i++) {
            if (!decimalDigit(text.charAt(i))) {
                throw new IllegalArgumentException("integer has non-digit");
            }
            if (++digits > MAX_DIGITS) {
                throw new IllegalArgumentException("too many integer digits");
            }
        }

        if (digits == 0) {
            throw new IllegalArgumentException("missing digits");
        }
        return new BigInteger(text);
    }

    public static BigDecimal parseDecimal(String text) {
        if (text == null || text.isEmpty()
                || text.length() > MAX_TEXT_CHARS) {
            throw new IllegalArgumentException("invalid decimal length");
        }

        int i = (text.charAt(0) == '-' || text.charAt(0) == '+')
                ? 1 : 0;
        int digits = 0;
        boolean pointSeen = false;

        while (i < text.length()) {
            char c = text.charAt(i);
            if (c == 'e' || c == 'E') {
                break;
            }

            if (c == '.') {
                if (pointSeen) {
                    throw new IllegalArgumentException("two decimal points");
                }
                pointSeen = true;
            } else if (decimalDigit(c)) {
                if (++digits > MAX_DIGITS) {
                    throw new IllegalArgumentException("too many decimal digits");
                }
            } else {
                throw new IllegalArgumentException(
                        "invalid decimal character");
            }
            i++;
        }

        if (digits == 0) {
            throw new IllegalArgumentException(
                    "missing mantissa digits");
        }

        if (i < text.length()) {
            i++; // Skip E/e.
            if (i < text.length()
                    && (text.charAt(i) == '+'
                            || text.charAt(i) == '-')) {
                i++;
            }

            int exponentDigits = 0;
            int magnitude = 0;

            for (; i < text.length(); i++) {
                char c = text.charAt(i);
                if (!decimalDigit(c)) {
                    throw new IllegalArgumentException(
                            "invalid exponent character");
                }
                if (++exponentDigits > MAX_EXPONENT_DIGITS) {
                    throw new IllegalArgumentException(
                            "exponent text too long");
                }

                int digit = c - '0';
                if (magnitude > (MAX_ABS_EXPONENT - digit) / 10) {
                    throw new IllegalArgumentException(
                            "exponent too large");
                }
                magnitude = magnitude * 10 + digit;
            }

            if (exponentDigits == 0) {
                throw new IllegalArgumentException(
                        "missing exponent digits");
            }
        }

        BigDecimal value = new BigDecimal(text);
        // Cast to long before calling abs to be safe with int MIN_VALUE.
        if (Math.abs((long) value.scale()) > MAX_ABS_SCALE) {
            throw new IllegalArgumentException("scale too large");
        }
        if (plainLength(value) > MAX_PLAIN_CHARS) {
            throw new IllegalArgumentException(
                    "plain representation too long");
        }
        return value;
    }

    // Expected character length of toPlainString(), without creating a huge string.
    private static long plainLength(BigDecimal n) {
        long p = n.precision();
        long scale = n.scale();
        long length;

        if (n.signum() == 0 && scale <= 0) {
            length = 1;
        } else if (scale <= 0) {
            length = p - scale;
        } else if (p > scale) {
            length = p + 1;   // Includes the decimal point.
        } else {
            length = scale + 2; // "0." and the fractional digits.
        }

        return length + (n.signum() < 0 ? 1 : 0);
    }

    public static BigInteger shiftLeftBounded(
            BigInteger value, int bits) {
        if (bits < 0
                || (long) value.bitLength() + bits > MAX_RESULT_BITS) {
            throw new IllegalArgumentException(
                    "shift would exceed bit limit");
        }
        return value.shiftLeft(bits);
    }

    private static void expectRejected(
            String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": NOT REJECTED");
        } catch (IllegalArgumentException ok) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        BigInteger integer = parseInteger("12345678901234567890");
        BigDecimal decimal = parseDecimal("1.25E+2");

        System.out.println("integer digits: "
                + integer.toString().length());
        System.out.println("decimal plain: " + decimal.toPlainString());
        System.out.println("bounded shift: "
                + shiftLeftBounded(BigInteger.valueOf(3), 10));
        System.out.println("scientific plain length: "
                + plainLength(parseDecimal("1E+30")));

        expectRejected("too many digits",
                () -> parseInteger("123456789012345678901"));
        expectRejected("large exponent",
                () -> parseDecimal("1E+999"));
        expectRejected("large plain output",
                () -> parseDecimal("100.0E+30"));
        expectRejected("oversize shift",
                () -> shiftLeftBounded(BigInteger.ONE, 128));
    }
}
```

Compile and run:

```bash
javac SafeBigNumbers.java
java SafeBigNumbers
```

Output:

```text
integer digits: 20
decimal plain: 125
bounded shift: 3072
scientific plain length: 31
too many digits: rejected
large exponent: rejected
large plain output: rejected
oversize shift: rejected
```

### Understanding Each Validation Layer

**`parseInteger`:** checks null/empty and total length; permits at most one leading sign and up to 20 digits `0..9`, only then calling `new BigInteger(text)`. Foreign characters or repeated signs are rejected. Leading zeros still **count** toward the limit because they lengthen the input and incur parsing cost.

**`parseDecimal`:** scans the mantissa, counts all digits, and rejects two decimal points. For the exponent, the program checks **both length and value** before constructing `BigDecimal`. The check `magnitude > (MAX_ABS_EXPONENT - digit) / 10` detects overflow before multiplying by 10 and adding the digit, avoiding overflowing the `int` variable while parsing the exponent. This policy accepts forms like `1.25E+2` and `.5` while rejecting whitespace, thousands grouping characters, or locale-formatted numbers.

**Scale control:** after constructing the value from bounded textual input, checks `Math.abs((long) value.scale())`. Promoting to `long` before `abs` avoids the `Integer.MIN_VALUE` edge case. This is an **additional post-parse check**, not a substitute for pre-constructor textual input/exponent limits.

**`plainLength`:** estimates only the plain decimal string length without calling `toPlainString()`. The formula uses `precision()` and `scale()`; there is a special case for zero with non-positive scale and one character for the minus sign when negative. In the example, `1E+30` has plain length 31 and is allowed; `100.0E+30` has plain length 33 and is rejected under the budget of 32.

**`shiftLeftBounded`:** uses the sum `bitLength + bits` as a **conservative upper bound** before `shiftLeft`. With this input domain and policy, the check blocks requests that could exceed 128 bits; occasionally it also rejects an actual result that might fall below the bound, which is acceptable in a resource-safety policy. For right shifts, exponentiation, multiplication/division, or `modPow`, build dedicated limits before each operation.

**`expectRejected`:** illustrates rejected cases via `IllegalArgumentException`; in real applications, translate those validation failures into structured validation responses and **never echo oversized input data into logs or error responses**.

Constants in this program are for illustration only. An accounting system, scientific computation, or cryptographic processor has vastly different budgets and data characteristics. Set limits according to product requirements and deployment resources.

## 5. Predicting Output Size Before String Conversion

It is very easy to overlook output issues. Consider:

```java
BigDecimal value = new BigDecimal("1E+1000000");

String compact = value.toString();     // Scientific notation, short.
// String huge = value.toPlainString(); // Can generate > 1 million characters.
```

`BigDecimal.toString()` chooses scientific notation when appropriate given scale/adjusted exponent. `toPlainString()` **forbids E notation** and can pad millions of zeros when scale is extremely negative or positive. `toEngineeringString()` also has its own layout, yet must not be relied upon as a general size-limiting mechanism.

A way to predict plain length for most non-zero numbers:

- `scale <= 0`: digit count is typically `precision - scale`.
- `scale > 0` and `precision > scale`: requires `precision + 1` characters (including the decimal point).
- `scale > 0` and `precision <= scale`: requires `scale + 2` characters, consisting of `0.` and fractional digits.
- If negative, add one character for the minus sign. For zero with non-positive scale, `toPlainString()` is `"0"`.

Estimation arithmetic must use `long` or overflow-checked math, never careless `int` addition/subtraction when scale may lie near `int` bounds. Given a small budget, **compare the predicted length before calling string-creation methods**.

Beyond `toPlainString()`, audit data paths through JSON serialization, logging, report generation, CSV, HTML, string-accepting APIs, or database columns. A value in compact scientific notation at ingestion can explode into a massive output after format normalization.

## 6. Resource Limits Before Operations

Even if both operands pass input validation, subsequent operations can still produce numbers exceeding the budget:

| Operation | Risk | Recommended Limit |
|---|---|---|
| `BigInteger.multiply` | Result size is roughly sum of operand bit lengths | Estimate result bit bound; block values exceeding budget |
| `BigInteger.shiftLeft` | `n` can be huge even when operand is short | Bound both `n` and predicted result bits |
| `BigInteger.pow` | Result digit count scales with exponent | Bound exponent and bit/precision budget |
| `BigInteger.modPow` | Expensive for large modulus/exponent | Bound bitLength and operation count/latency |
| `BigInteger.gcd`, divide/mod | Cost depends on operand size | Bound input bitLength and processing quota |
| `BigDecimal.multiply` | Unscaled value and scale can grow | Bound predicted precision/scale and result |
| `BigDecimal.divide` | Can have infinite decimal expansion or many digits | Specify precision/scale and `RoundingMode` per business rules |
| `BigDecimal.pow` | Precision, exponent, scale, and intermediate cost can grow huge | Bound exponent, precision, scale, and cost |
| `toPlainString` | Output string can be huge even for small unscaled value | Pre-calculate plain length; block before creating |

Prediction examples:

- When multiplying two integers of bit lengths `a` and `b`, result `bitLength` does not exceed roughly `a + b`; use this sum as a conservative upper bound before multiplying.
- For `shiftLeft(n)`, adding `n` to existing `bitLength` gives a simple upper bound; reject negative `n` or `n` exceeding the limit.
- For `pow(exponent)`, the product `bitLength × exponent` can overflow. Use a wider type or overflow check when estimating, especially when `exponent` is user-controlled.

`MathContext` bounds **the precision of the rounded result** in supporting `BigDecimal` APIs, yet **is not a general shield against memory/CPU exhaustion**. An algorithm may still need to build large intermediates or process gigantic operands before rounding. `new MathContext(20)` does not make parsing multi-million-character strings or computing huge powers resource-safe.

Remember also that `BigDecimal.divide(BigDecimal)` without a scale/rounding context can throw `ArithmeticException` when the quotient has no finite decimal representation; that is a **separate** issue from excessive resource consumption. Bound inputs first and specify an appropriate division mode.

## 7. System-Wide Budgets, Not Only Inside One Parse Function

A good validator is insufficient if earlier layers have already read an entire gigantic request into memory. Layer your defenses:

1. **Data ingestion gateway:** bound HTTP request bytes, JSON body size, uploads, messages, and batch sizes; avoid constructing large objects once payloads exceed limits.
2. **Parsing:** scan input in linear time, bounding length, digit count, exponent, and scale before building large objects; avoid unbounded regexes on arbitrary strings.
3. **Data model:** express per-field business limits, such as maximum digits, valid scale, value range, and sign/zero handling.
4. **Calculation:** estimate result expansion and iteration count before multiplication, exponentiation, shifts, or format conversions; bound total concurrent tasks and processing time.
5. **Output and storage:** bound output strings, row/field counts, log lengths, database column sizes; never accidentally expand short scientific numbers into huge plain strings.
6. **Resilience:** enforce timeouts, per-request/per-user quotas, concurrency/memory limits, early rejection, and metrics for limit violations.

Never treat `try/catch (OutOfMemoryError)` as an input-validation mechanism. By the time that error fires, the JVM may already be in a severely resource-starved state; preventing via pre-allocation limits and process/infrastructure resource controls is far more reliable.

If you genuinely need to support computing huge numbers, **architect for that workload**: asynchronous jobs with explicit quotas, bounded memory/CPU, suitable result storage formats, cancellable/throttled execution, and resource monitoring. Never relax all limits in synchronous APIs serving normal requests.

## 8. Common Design Mistakes

### "Digits are bounded, so it must be safe"

A 20-digit mantissa limit still accepts `1E+1000000000` if the exponent is unchecked. The value may be compactly represented yet `toPlainString()` is gigantic. Conversely, `BigInteger.ONE.shiftLeft(100000000)` has a one-bit input yet a huge output. Validate **numeric representation**, **operations**, and **output formatting**.

### "Parse first, then check `precision()` and `bitLength()`"

Post-constructor checks can be useful, yet are already too late to prevent spending resources parsing an unbounded string. For untrusted data, always enforce raw limits and count digits **before** constructing `BigInteger`/`BigDecimal`.

### "Low precision means `toPlainString()` is short"

`new BigDecimal("1E+1000000")` has precision 1 yet its plain string is over a million characters long. **Precision** describes digits of the unscaled value, whereas **scale** determines decimal point placement and how many zeros must be rendered.

### "`stripTrailingZeros()` makes everything small"

`stripTrailingZeros()` can reduce unscaled digits and alter scale, sometimes yielding a negative scale so `toString()` uses scientific notation. It is not an output-size control; calling `toPlainString()` afterward can still create a massive string. Do not use this method as a substitute for resource limits or precision/scale policies.

### "Using `BigDecimal` with a small `MathContext` is enough"

A small `MathContext` bounds result precision in operations that use it; it does not block gigantic input strings, out-of-policy exponents, operation counts, or all temporary memory. Resource limits must come **before** potentially expensive steps.

### "Using `double` reduces cost without affecting data"

`double` has finite binary range and precision. Converting financial amounts or exact decimal data to `double` can lose digits or alter values. If `BigDecimal` data must be bounded, **reject out-of-policy values** or define explicit rounding, rather than silently switching types.

### "Reject the error and log the full input"

When error responses or logs print the entire multi-million-digit string, error reporting itself causes memory/I/O pressure. Log only safe metadata such as error code, field name, bounded length, and request ID; avoid echoing the entire payload into messages.

## 9. Defining Policies by Business Domain

No single limit fits every application:

- **Currency:** typically requires precision, scale, value range, rounding, and format limits per currency or contract. Negative values, plus signs, trailing zeros, and exponents may be allowed or forbidden per API specification.
- **Product counts / counters:** bound the integer range (and non-negativity if business rules require); `long` alone may suffice if range permits. `BigInteger` is only helpful when requirements genuinely exceed primitive ranges.
- **Scientific computing:** may need large exponents, high precision, and scientific notation; budget unscaled value length, precision, scale, operation counts, and output cost.
- **Cryptographic arithmetic:** `BigInteger` can represent large integers, yet handling secrets requires considering execution timing, bounds, security APIs, and side-channel properties; never assume every `BigInteger` operation is suitable for secret handling.
- **Public APIs:** add per-user quotas, request size limits, timeouts, and clear validation responses, because inputs may be untrusted.

For instance, one schema may specify "maximum 30 digits, scale 0–4, absolute value below threshold X, no E notation"; another may allow `E` while bounding exponent and plain string length. When implementing, **express limits as testable conditions**, not vague notes like "numbers must not be too large."

## 10. Testing Checklist

Test not only normal valid values, but also resource boundaries:

- Empty string, lone `+`/`-` sign, foreign characters, whitespace, multiple decimal points, exponent missing digits.
- Values exactly at the limit and one character/digit past the limit.
- Long strings of all zeros, value equal to 0 yet mantissa still overly long.
- Exponents with many digits, negative/positive signs, exceeding limits, or capable of overflowing if accumulated carelessly.
- Very large positive scale (`1E-1000000`) and very large negative scale (`1E+1000000`).
- Short inputs leading to `pow` or `shiftLeft` expanding beyond budget.
- Short `toString()` yet very long `toPlainString()`.
- Multiple concurrent requests/tasks using budgets near the threshold simultaneously.
- Error/log outputs not accidentally copying back the entire huge number.

**Self-check 1:** Why is a "maximum 50 input characters" limit not enough to protect `toPlainString()`? Because scientific notation such as `1E+1000000` is very short yet produces millions of characters in full decimal form.

**Self-check 2:** Why doesn't checking `BigInteger.bitLength()` after `new BigInteger(text)` replace bounding the string? Because the string already had to be received and parsed, potentially incurring high cost before the check.

**Self-check 3:** `new BigDecimal("1E+30")` has precision 1; can we conclude multiplication and output are both cheap? **No.** Precision does not contain enough information about scale, formatting, or the cost of subsequent operations.

**Key takeaway:** `BigInteger` and `BigDecimal` enable high-precision numeric representation, yet resource safety is the application's responsibility. Bound **inputs before parsing**, **scale/exponent**, **result magnitude before operations**, **string length before formatting**, and **system-level execution quotas**.