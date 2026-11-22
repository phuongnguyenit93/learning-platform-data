# Designing Exchange Formats That Keep Numbers Exact Without `double` Intermediaries

## 1. Problem Statement and Success Criteria

When transmitting a `BigDecimal` value over JSON, HTTP, message queues, files, or between Java and JavaScript, a common bug is passing the number through `double`/`Double` at some stage. `double` is a finite binary floating-point number (IEEE 754 binary64), so it cannot represent every decimal fraction accurately—including `0.1`—and cannot keep all large integers distinct.

Java example:

~~~java
BigDecimal exact = new BigDecimal("9007199254740993.01");
BigDecimal altered = BigDecimal.valueOf(exact.doubleValue());

System.out.println(exact.toPlainString());   // 9007199254740993.01
System.out.println(altered.toPlainString()); // 9007199254740994
~~~

Converting to `double` lost data; converting back with `BigDecimal.valueOf(...)` **cannot recover** the digits that were rounded away.

A sound exchange format must explicitly define:

1. **Preserving the numeric value**: the receiver reads the exact decimal number the sender intended to transmit.
2. **Does `scale` also need to be preserved?** `1.0` and `1.00` have the same value under `compareTo`, yet are not equal under `BigDecimal.equals`.
3. **Preserving every digit on the wire**, without implicitly converting through `double`, `float`, JavaScript `Number`, or similar casts.
4. **A testable contract**: agree on data types, syntax, limits, rounding rules, and error reporting.
5. **Resource protection**: bound length, `precision`, `scale`, and exponents before memory-intensive conversions.

This lesson focuses on designing and implementing `BigDecimal` exchange across components. When rounded calculations are needed, the rounding policy must be specified separately, never hidden inside encoding or decoding steps.

## 2. Why Is `double` an Unsafe Intermediary?

`BigDecimal` represents a number as `unscaledValue × 10^(-scale)`. For a decimal string, `new BigDecimal(String)` reads the digits accurately according to decimal representation.

By contrast, `double` stores a finite number of bits for the binary significand and exponent. There are two primary failure modes:

- **Decimal fractions**: many numbers like `0.1` cannot be represented exactly in finite binary. `new BigDecimal(0.1)` gives the exact value of *the stored double*, which is much longer than the string `"0.1"`.
- **Integers exceeding JavaScript's safe range**: `Number` is binary64, so only integers in `[-(2^53-1), 2^53-1]` are guaranteed to be represented exactly to the unit. `9007199254740993` falls outside that range.

Illustration:

~~~java
BigDecimal text = new BigDecimal("0.1");
BigDecimal viaDoubleConstructor = new BigDecimal(0.1);

System.out.println(text.equals(viaDoubleConstructor)); // false

BigDecimal huge = new BigDecimal("9007199254740993");
System.out.println(
        BigDecimal.valueOf(huge.doubleValue()).toPlainString()
); // 9007199254740992
~~~

Do not misunderstand `BigDecimal.valueOf(double)` as useless: it is usually preferable to `new BigDecimal(double)` when **the input truly is already a `double`** and you want its `Double.toString` decimal representation. However, neither approach recovers digits that existed before the data was converted into `double`.

**Architectural rule:** if the source is a decimal string, `DECIMAL/NUMERIC` data, or a `BigDecimal`, keep it as an **exact decimal string or exact decimal type** all the way to its destination.

## 3. First Distinguish Two Levels of "Preservation"

### A. Preserving Numeric Value

Two representations have equal value if:

~~~java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = new BigDecimal("1E+3");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

This level of preservation is appropriate when only computation results matter, such as normalized measurement totals where business rules do not rely on `scale`.

### B. Preserving Both Value and `scale`

`BigDecimal.equals` checks both value and `scale`. Examples:

| Input Value | `unscaledValue()` | `scale()` |
| --- | ---: | ---: |
| `"1.0"` | `10` | `1` |
| `"1.00"` | `100` | `2` |
| `"1000"` | `1000` | `0` |
| `"1E+3"` | `1` | `-3` |

If `scale` is part of the contract (e.g., to preserve the declared number of decimal places), you need a round-trip where `BigDecimal.equals` also returns `true`.

Do not dismiss trailing zeros as "unimportant" across all systems. They may not affect arithmetic, yet in data entry, document generation, or representation-based exchanges, that information may need to be retained.

## 4. Wire Format Options and Trade-Offs

### Option 1 — JSON String Containing Exact Decimal (Default Recommendation)

~~~json
{
  "currency": "USD",
  "amount": "9007199254740993.01"
}
~~~

Contract: `amount` is a **JSON string**, not a JSON number. The string content represents the decimal number under an agreed syntax; the Java side decodes directly with `new BigDecimal(amount)`.

Advantages:

- JavaScript `JSON.parse` returns a **string**, avoiding automatic rounding via `Number`.
- Java, Python, .NET, or other languages can parse using a decimal type with the required precision.
- Easily preserves the integrity of huge integers, many decimal digits, and exponential notation.
- Can stipulate that the string is the output of `BigDecimal.toString()` to preserve `scale` as well.

Agree on the schema: field name, JSON **string** type, decimal point format, negative sign, exponent support, maximum length, and value range constraints. Do not let clients arbitrarily call `Number(amount)` or `parseFloat(amount)` before computing.

### Option 2 — JSON Number with End-to-End Exact Decimal Pipeline

~~~json
{
  "amount": 9007199254740993.01
}
~~~

JSON syntax **permits** numeric literals with many digits, yet JSON does not guarantee every parser preserves precision. If any participant runs standard `JSON.parse` in JavaScript, `amount` becomes a `Number`; precision is already lost at the parse step.

This option satisfies requirements only when **every link in the chain** reads the numeric token directly into an arbitrary decimal type with no binary64 intermediary. For instance, one Java parser configured to bind the field to `BigDecimal` can read the decimal token accurately, while another parser binding to `Double` can round it.

Having Java serialize `BigDecimal` as a JSON numeric token is not enough to prove the whole pipeline is safe. Test all consumers, message brokers, proxies, and data transformation steps.

### Option 3 — Smallest Unit as an Integer String

For example, if the contract specifies two decimal places:

~~~json
{
  "currency": "USD",
  "minorUnits": "123456",
  "scale": 2
}
~~~

The value is interpreted as `123456 × 10^(-2) = 1234.56`. `minorUnits` is an **integer string** so JavaScript does not accidentally lose precision; Java can use `BigInteger`.

This option is useful in payments or systems requiring integers in a predefined unit. However, `scale` should not be guessed arbitrarily from a currency code; apply the proper business policy and versioned rules. If the original value has more digits than `scale` permits, define whether to **reject** or **round with a specific mode** before encoding.

### Option 4 — Transmitting Separate `unscaled` and `scale`

~~~json
{
  "unscaled": "100000",
  "scale": 2
}
~~~

The receiver reconstructs it:

~~~java
BigDecimal number = new BigDecimal(
        new BigInteger("100000"), 2
); // 1000.00
~~~

This representation preserves both value and `scale` without relying on canonical string rules. `unscaled` must be treated as a large integer string; `scale` is an integer with reasonable range and magnitude constraints (in Java, `BigDecimal.scale()` returns `int`).

The advantage is an explicit contract that is straightforward to reconstruct. The downside is a more verbose schema and the requirement that all parties implement `unscaled × 10^(-scale)` properly, especially for negative `scale`.

### Which Option Should You Choose?

| Goal | Recommendation |
| --- | --- |
| JSON API with web clients or multiple languages | Decimal **string** |
| Services only, all using verified decimal parsers | JSON number may be used, with end-to-end testing |
| Data tied to fixed smallest units | Integer minor-units **string** alongside scale/unit |
| Must preserve exact `BigDecimal` representation including scale | Canonical `toString()` or `unscaled/scale` pair |

## 5. Decimal String Contract: `toString()` vs. `toPlainString()`

Both methods produce a string containing the numeric value without passing through `double`, yet **their ability to preserve scale when parsed back differs**.

| Initial Value | `toString()` | `toPlainString()` | Preserves Scale When Reparsed? |
| --- | --- | --- | --- |
| `new BigDecimal("12.3400")` | `12.3400` | `12.3400` | Both |
| `new BigDecimal("1E+3")` | `1E+3` | `1000` | Only `toString()` |
| `new BigDecimal("1000")` | `1000` | `1000` | Both |
| `new BigDecimal("0.000")` | `0.000` | `0.000` | Both |

Key takeaway:

~~~java
BigDecimal original = new BigDecimal("1E+3");

BigDecimal canonicalRoundTrip =
        new BigDecimal(original.toString());

BigDecimal plainRoundTrip =
        new BigDecimal(original.toPlainString());

System.out.println(original.equals(canonicalRoundTrip)); // true
System.out.println(original.equals(plainRoundTrip));     // false
System.out.println(original.compareTo(plainRoundTrip));  // 0
~~~

`BigDecimal.toString()` may use exponential notation (`1E+3`), yet this canonical representation contains sufficient information for `new BigDecimal(original.toString()).equals(original)` to return `true`.

`toPlainString()` removes exponential notation, making it suitable for display or exchange when only the **numeric value** needs to be preserved. With negative scales, reading back a plain string typically creates a different scale. If a system only allows exponent-free decimal strings yet still must preserve scale, transmit a separate `scale` field in the schema.

Note: `stripTrailingZeros()` **changes scale** even though the value remains unchanged; do not call it thoughtlessly before outputting data that needs exact `equals()` round-trips. Likewise, `setScale(...)` can add zeros or round, so it is a separate business rule rather than a mandatory serialization step.

## 6. Designing a Concrete Exchange Contract

Example contract specification for `PaymentWire`:

~~~json
{
  "currency": "USD",
  "amount": "9007199254740993.01"
}
~~~

- `currency`: unit code from the system's supported list, validated independently.
- `amount`: JSON **string**, containing the canonical string generated by `BigDecimal.toString()`.
- Uses `.` as the decimal separator, `-` for negative numbers, and may include exponent `E` with exponent sign `+` or `-`.
- Contains no grouping separators (`,`), currency symbols, whitespace, or locale-dependent formatting.
- Total character length, `precision`, `scale`, and value bounds are defined by business rules.
- The receiver parses directly `String → BigDecimal`, without using `Double`, `Float`, `BigDecimal(double)`, or `Number` as an intermediary.
- If data is invalid, the receiver returns a clear validation error; never silently substitute `0` or round.

Because the contract chooses canonical strings, forms like `"01.20"`, `"1e3"`, or `"1E+03"` might be readable by a decimal parser, yet **are rejected by the canonical check** if `BigDecimal.toString()` differs verbatim from the input. If compatibility with producers following varying rules is required, you can relax the canonical check while still enforcing exact decimal parsing and agreeing on scale preservation requirements.

## 7. Java 17+ — Complete Standalone Runnable Example

File: `LosslessDecimalWireDemo.java`.

This is a wire data model independent of any JSON library. A JSON library can map the `PaymentWire` record into a JSON object in which the `amount` field has string type. The program below focuses on verifying decimal integrity at encode/decode boundaries.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class LosslessDecimalWireDemo {
    record PaymentWire(String currency, String amount) {}

    private static final int MAX_TEXT_LENGTH = 120;
    private static final int MAX_PRECISION = 50;
    private static final int MAX_ABS_SCALE = 50;

    static PaymentWire encode(String currency, BigDecimal amount) {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");
        return new PaymentWire(currency, amount.toString());
    }

    static BigDecimal decode(PaymentWire wire) {
        Objects.requireNonNull(wire, "wire");
        String decimal = wire.amount();

        if (decimal == null || decimal.isEmpty()
                || decimal.length() > MAX_TEXT_LENGTH
                || !decimal.matches(
                        "-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?"
                )) {
            throw new IllegalArgumentException("Invalid decimal string");
        }

        final BigDecimal parsed;
        try {
            parsed = new BigDecimal(decimal);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid decimal number", ex);
        }

        if (parsed.precision() > MAX_PRECISION
                || Math.abs((long) parsed.scale()) > MAX_ABS_SCALE) {
            throw new IllegalArgumentException("Decimal outside contract");
        }

        // Ensure one canonical spelling corresponds to one representation.
        if (!parsed.toString().equals(decimal)) {
            throw new IllegalArgumentException("Non-canonical decimal");
        }

        return parsed;
    }

    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("9007199254740993.01");
        PaymentWire wire = encode("USD", original);
        BigDecimal decoded = decode(wire);

        System.out.println("wire amount: " + wire.amount());
        System.out.println(
                "same numeric value: " + (original.compareTo(decoded) == 0)
        );
        System.out.println("same value and scale: " + original.equals(decoded));

        BigDecimal passedThroughDouble =
                BigDecimal.valueOf(original.doubleValue());
        System.out.println(
                "through double: " + passedThroughDouble.toPlainString()
        );

        BigDecimal exponent = new BigDecimal("1E+3");
        BigDecimal restored = decode(encode("USD", exponent));
        System.out.println("exponent wire: " + exponent.toString());
        System.out.println("restored scale: " + restored.scale());
        System.out.println("exponent round-trip equals: "
                + exponent.equals(restored));
        System.out.println("plain reparsed equals: "
                + exponent.equals(new BigDecimal(exponent.toPlainString())));
    }
}
~~~

Run:

~~~bash
javac LosslessDecimalWireDemo.java
java LosslessDecimalWireDemo
~~~

Expected stdout:

~~~text
wire amount: 9007199254740993.01
same numeric value: true
same value and scale: true
through double: 9007199254740994
exponent wire: 1E+3
restored scale: -3
exponent round-trip equals: true
plain reparsed equals: false
~~~

`MAX_TEXT_LENGTH`, `MAX_PRECISION`, and `MAX_ABS_SCALE` are **illustrative bounds** that must be redesigned to match each API's numeric domain. The `currency` field in the demo is merely carried along; real implementations must verify against a currency enum/allowlist, access permissions, and value rules (e.g., whether negative numbers are allowed). Scale bounds are checked **before** any `toPlainString()` call that could expand a massive exponent into an overly long string.

### Using with a JSON Library

In Java, a JSON library such as Jackson can deserialize the `"amount"` JSON string directly into a `String` property on a DTO or record, then call `decode`. Example payload:

~~~json
{"currency":"USD","amount":"9007199254740993.01"}
~~~

The `amount` field must remain a **string** in the JSON schema. When serializing, call `BigDecimal.toString()` to produce the string. When deserializing, read the string and call `new BigDecimal(String)` as shown. **Do not bind to `double` or `Double` and then call `BigDecimal.valueOf`**.

If choosing a JSON number, you can bind the token directly to `BigDecimal` with proper parser configuration, but you must verify all other links in the chain also process decimals accurately. Many parsers default to converting JSON number tokens into binary64 or another bounded type; it is unsafe to guess from the sender side alone.

## 8. JavaScript Client: Read Strings as Strings

In standard JavaScript:

~~~javascript
const payload = JSON.parse(
  '{"currency":"USD","amount":"9007199254740993.01"}'
);

console.log(typeof payload.amount); // string
console.log(payload.amount);        // 9007199254740993.01
~~~

The `amount` string preserves the exact decimal characters. **Do not** do this if exact computation is needed:

~~~javascript
const unsafe = Number(payload.amount);
console.log(unsafe); // value has already been rounded
~~~

JavaScript `BigInt` suits arbitrary integers, **and does not directly support fractional parts**. For general decimals, use an arbitrary-precision decimal library or pass the string back to a service with `BigDecimal`. Under a minor-units contract, convert the minor-units string to `BigInt` only after validation and track scale separately.

If locale-specific display is desired, handle formatting in the UI layer using tools that support decimal inputs properly. `Intl.NumberFormat` works with `Number` under common usage; calling `Number(decimalString)` before formatting may already lose precision. Do not replace periods with commas in wire data because of a user's locale.

## 9. Other Channels Must Also Preserve Accuracy

### HTTP/REST

- Request/response schemas define `amount` as a string and document limits, e.g., `"12.3400"`.
- The Java side receives the string directly, validates it, and parses it into `BigDecimal`.
- The server serializes back from `BigDecimal` via `toString()` if scale preservation is needed.
- Test real HTTP traffic through serializers, gateways, and clients rather than unit-testing only the `decode` function.

### Relational Databases

With `DECIMAL(p,s)` or `NUMERIC(p,s)` columns per RDBMS specification, use `PreparedStatement.setBigDecimal(...)` and `ResultSet.getBigDecimal(...)`. Avoid passing data through `setDouble/getDouble`.

~~~java
// Illustration assuming PreparedStatement ps and ResultSet rs already exist:
ps.setBigDecimal(1, new BigDecimal("1234.56"));
BigDecimal amount = rs.getBigDecimal("amount");
~~~

This is a **JDBC illustrative snippet**, not a standalone runnable program. The database schema may still enforce precision/scale, round, or reject data depending on the engine/configuration. Verify column policies and round-trip behavior of the specific driver/database in use.

### Message Brokers, CSV, Spreadsheets, and Files

- Payloads over queues should continue using a decimal string contract; avoid intermediate mapper steps that convert to `Double`.
- CSV is text, yet import tools may auto-detect columns as floating-point. Declare decimal columns as text or import using an exact decimal parser.
- If transmitting `unscaled/scale`, avoid placing `unscaled` in a JSON number for JavaScript consumers.
- When integrating with systems lacking exact decimal support, mandate **string** output formats and test round-trips rather than expecting "JSON numbers are always exact."

## 10. Validation, Normalization, and Resource Safety

An exact decimal parser does not mean every input is valid:

1. **Syntax**: block `NaN`, `Infinity`, empty strings, disallowed whitespace, grouping separators, and out-of-contract number formats. `BigDecimal` does not represent `NaN/Infinity` values.
2. **Length and precision**: cap digit counts to avoid huge payloads.
3. **Scale and exponent**: bound the `scale` range; do not call `toPlainString()` on `1E+100000000` unchecked, as it can allocate an enormous string.
4. **Value domain**: validate sign, `min/max`, units, currency type, and field semantics.
5. **Canonical representation**: if signing, hashing, caching, or preventing multiple spellings of the same representation, define a canonicalization algorithm and apply it consistently. `BigDecimal.toString()` preserves scale, yet it does not collapse two numerically equal values with different scales into one string.
6. **Processing atomicity**: validate before writing to the database or forwarding downstream; never silently round in infrastructure layers.

For zero, `BigDecimal` does not preserve a separate negative sign: `new BigDecimal("-0.00").toString()` is `"0.00"`. If the contract requires preserving every input character (including the `-` sign of "negative zero," leading zeros, lowercase `e`, or whitespace), store the **raw input string** separately. Preserving `BigDecimal` under `equals` is not byte-for-byte verbatim preservation of original input text.

If the sender may supply `1.00` while the receiver stores it in a database column with fixed scale `2`, that scale can be retained; however, never blindly assume every `DECIMAL/NUMERIC` column preserves the exact scale of every payload. Test the driver, schema, and query mechanics.

## 11. Rules for Testing a Decimal Protocol

A minimal test suite:

- **Large values**: `9007199254740993`, `9007199254740993.01`; verify no `double` pass-through and no altered digits.
- **Very small values**: `0.0000000000000000000001`; verify no loss of fractional digits.
- **Different scales**: `1.0` and `1.00`; test both `compareTo` and `equals`.
- **Negative scales**: `1E+3` and `1E-7`; verify `toString` and reparsing preserve scale.
- **Negative numbers and zero**: `-12.3400`, `0`, `0.00`; check canonical rules.
- **Validation boundaries**: empty payload, excessive length, grouping separators, out-of-bounds exponents, out-of-domain values.
- **Interoperability**: Java → JSON → JavaScript → JSON → Java; consumers must keep the `amount` field as a string end-to-end.

For contracts requiring scale preservation, a test invariant can be written as:

~~~java
BigDecimal before = new BigDecimal("1E+3");
String wireValue = before.toString();
BigDecimal after = new BigDecimal(wireValue);

assert before.equals(after);
assert before.scale() == after.scale();
~~~

When assertions are not enabled (`-ea`), Java skips `assert`; in JUnit tests, use the test suite's assertion framework to avoid depending on JVM flags. This snippet illustrates a round-trip invariant, not a standalone application.

### Short Exercises

1. A web client receives `{"amount":9007199254740993}` via `JSON.parse`. Where is the risk of information loss?
2. For `new BigDecimal("1E+3")`, do you choose `toString()` or `toPlainString()` so that `scale = -3` remains after parsing?
3. Service A writes `BigDecimal("123.4500")` as the JSON string `"123.4500"`, and Service B parses through `Double` before creating `BigDecimal`. Does that pipeline still guarantee both value and scale?
4. If a contract transmits only minor units `"12345"` and specifies `scale = 2`, what is the monetary value?
5. If you must preserve the verbatim string `"-0.00"`, is keeping only the parsed `BigDecimal` object enough?

**Answers:** (1) `JSON.parse` creates a `Number` from the JSON number token, which can round integers beyond the safe range. (2) `toString()`; `toPlainString()` produces `"1000"` and loses the negative scale when read back. (3) No: the `Double` step can alter the value or lose the scale, even if results happen to match on some inputs. (4) `123.45`. (5) No: `BigDecimal` does not store a negative sign on zero as an independent sign; you must store the raw input string when verbatim preservation is needed.

**Technical takeaway:** choose an exact decimal wire format right in the schema, use `String ↔ BigDecimal` (or `unscaled + scale`), define the preservation level explicitly, and always test end-to-end with JavaScript/JSON parsers. A single pass through binary64 can make a precision loss bug permanent.
