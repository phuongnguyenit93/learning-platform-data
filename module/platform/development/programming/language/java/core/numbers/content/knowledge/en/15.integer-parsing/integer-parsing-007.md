# NumberFormatException from Invalid Characters or Out-of-Range Values in Java

When converting text to an integer using `Integer.parseInt`, `Long.parseLong`, or similar APIs, Java can throw **`NumberFormatException`**. The two most important groups of causes are:

1. **The string does not match the integer syntax** of the chosen API/radix: containing invalid characters, a misplaced sign, a decimal point, unhandled whitespace, an unrecognized prefix, etc.
2. **The string represents a number exceeding the value range** of the target type: for instance, `2147483648` is a syntactically valid decimal number yet greater than `Integer.MAX_VALUE`.

Core point: **`parseInt` validates *both* syntax and representable range**. On error, the method does not return an approximation, does not ignore trailing characters, and does not "wrap around" to yield another `int` value. This lesson belongs to the **Integer Parsing** topic and focuses on diagnosing, preventing, and properly handling these cases in Java 17+.

## 1. Where does `NumberFormatException` occur?

`NumberFormatException` is a subclass of `IllegalArgumentException`, belonging to **unchecked exceptions**. Therefore Java does not force callers to declare `throws` or `catch`, yet untrusted input data still requires an explicit handling policy.

~~~java
int quantity = Integer.parseInt("123"); // 123
long balance = Long.parseLong("123");  // 123L
~~~

Commonly encountered APIs:

| API | Return type | When does NumberFormatException occur? |
| --- | --- | --- |
| `Integer.parseInt(text)` | signed `int`, base 10 | Invalid syntax or outside 32-bit range |
| `Integer.parseInt(text, radix)` | signed `int`, base 2–36 | Character not in radix, invalid radix, or outside `int` range |
| `Long.parseLong(text)` | signed `long`, base 10 | Invalid syntax or outside 64-bit range |
| `Integer.parseUnsignedInt(text)` | `int` holding bits of 32-bit unsigned number | Invalid syntax or outside 0 to 2³² − 1 |
| `Long.parseUnsignedLong(text)` | `long` holding bits of 64-bit unsigned number | Invalid syntax or outside 0 to 2⁶⁴ − 1 |
| `Integer.decode(text)` | `Integer` | Invalid syntax, invalid prefix, or exceeds target type range |
| `new BigInteger(text)` | `BigInteger` | Invalid syntax; **not blocked by `int`/`long` limits** |

`Integer.valueOf(String)` and `Long.valueOf(String)` also rely on parsing with corresponding syntax/range checks. `valueOf` returns a wrapper, whereas `parseInt` / `parseLong` return primitives; **neither turns invalid strings into null or 0 by default**.

Do not confuse `NumberFormatException` with `ArithmeticException` from integer division by 0 or `NullPointerException` from unboxing a null wrapper. They have different origins and handling strategies.

## 2. Characters that cause `Integer.parseInt` to fail

`Integer.parseInt(text)` by default expects a **decimal integer string**, with an optional `+` or `-` sign at the **start of the string**, followed by at least one valid digit. The function parses the entire string, not just a leading numeric prefix.

| String | Result when calling `Integer.parseInt` | Explanation |
| --- | --- | --- |
| `"42"` | `42` | Valid |
| `"+42"` | `42` | Leading plus sign is allowed |
| `"-42"` | `-42` | Leading ASCII minus sign is allowed |
| `"0012"` | `12` | Leading zeros do not make `parseInt` automatically switch to base 8 |
| `""` | Exception | No digits |
| `"+"` or `"-"` | Exception | Sign only, missing digits |
| `"12x"`, `"1 2"` | Exception | Contains non-digit characters in base 10 |
| `"1_000"` | Exception | Underscore does not belong to runtime parser syntax |
| `"12.0"`, `"1e3"` | Exception | This is not `parseInt` integer syntax |
| `" 42 "` or `"42\n"` | Exception | Contains whitespace/newline characters |
| `"0x2A"` | Exception | Base-10 `parseInt` does not automatically handle `0x` prefix |
| `"−42"` | Exception | Unicode minus sign U+2212 is not ASCII minus `-` |

**Special note on underscores:** Java source code accepts `1_000` as a valid *integer literal* in the compiler, whereas the runtime string `"1_000"` passed to `parseInt` is **invalid**. Do not confuse literal syntax written in source code with text data syntax parsed by the API.

**Special note on Unicode:** Java parsing uses digit recognition rules based on `Character.digit`, so certain Unicode digits (such as fullwidth digits) can be accepted. If a protocol's input format must strictly be ASCII `0–9`, verify the ASCII rule explicitly—do **not** rely on `parseInt` rejecting all non-ASCII digits. Conversely, the Unicode minus sign U+2212 is not treated as an ASCII `-` sign.

## 3. Syntactically valid strings can still exceed numeric type bounds

Java's signed `int` is a 32-bit type with range:

- `Integer.MIN_VALUE = -2147483648`
- `Integer.MAX_VALUE = 2147483647`

Therefore:

~~~java
int max = Integer.parseInt("2147483647");  // Valid
int min = Integer.parseInt("-2147483648"); // Valid

// Integer.parseInt("2147483648");  // NumberFormatException
// Integer.parseInt("-2147483649"); // NumberFormatException
~~~

`"2147483648"` is a string consisting entirely of valid digits. It is rejected because **its mathematical value does not fit within `int`**, not because of "strange characters."

For signed `long`, the corresponding limits are:

- `Long.MIN_VALUE = -9223372036854775808`
- `Long.MAX_VALUE = 9223372036854775807`

~~~java
long maxLong = Long.parseLong("9223372036854775807");

// Long.parseLong("9223372036854775808"); // NumberFormatException
~~~

The number `2147483648` can be parsed into `long`, while numbers exceeding `Long.MAX_VALUE` can be represented using `BigInteger`:

~~~java
long largerThanInt = Long.parseLong("2147483648");
java.math.BigInteger largerThanLong =
        new java.math.BigInteger("9223372036854775808");
~~~

**A larger type only solves range overflow errors, not strings with invalid characters.** `new BigInteger("12x")` still throws `NumberFormatException`.

Also distinguish **parsing** from **arithmetic after parsing**: `Integer.parseInt("2147483647") + 1` can overflow under `int` integer rules, whereas `Integer.parseInt("2147483648")` throws an exception right at parse time. If you want to detect overflow during addition, use `Math.addExact` or widen the data type appropriately.

## 4. Radix (base) and valid characters

`Integer.parseInt(text, radix)` accepts bases from `Character.MIN_RADIX` = 2 to `Character.MAX_RADIX` = 36. A character's digit value must be less than the radix; with radix 16, letters `A`–`F` represent 10–15 (case-insensitive for ASCII).

~~~java
int decimalFromBinary = Integer.parseInt("1010", 2); // 10
int decimalFromHex = Integer.parseInt("2A", 16);     // 42

// Integer.parseInt("102", 2);    // NumberFormatException: digit 2 is not in base 2
// Integer.parseInt("0x2A", 16);  // NumberFormatException: parseInt does not strip 0x prefix
~~~

**Radix and prefix are two separate mechanisms:**

| Call | Result | Notes |
| --- | --- | --- |
| `Integer.parseInt("2A", 16)` | `42` | Base 16 without prefix |
| `Integer.parseInt("0x2A", 16)` | Exception | `parseInt` does not automatically strip `0x` |
| `Integer.decode("0x2A")` | `42` | `decode` accepts hexadecimal prefix |
| `Integer.decode("#2A")` | `42` | Another hexadecimal prefix form |
| `Integer.parseInt("010")` | `10` | Base 10 by default |
| `Integer.decode("010")` | `8` | `decode` treats leading zero as octal |

`Integer.decode` also supports signs placed before the prefix, such as `"-0x2A"`. Do not use `decode` for an identifier string with leading zeros if the data contract states all values are decimal; octal behavior can be very surprising.

If protocol input allows a `0x` prefix and radix 16, you can parse the prefix per the protocol rules and call `parseInt` on the digit portion, or use `decode` when it matches all syntaxes defined by that API. Always verify the *value range* after determining syntax/radix.

## 5. Parsing unsigned integers: bit results can appear negative when viewed as signed

`Integer.parseUnsignedInt` parses the 32-bit unsigned range, from 0 to 4294967295. However, the return type is still **32-bit `int`**; there is no separate `uint` primitive in Java.

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                       // -1 (printed as signed int)
System.out.println(Integer.toUnsignedLong(bits)); // 4294967295
~~~

`bits == -1` here does not mean parsing failed: all bits of the maximum unsigned value are 1, which when interpreted as signed `int` is -1. Use `Integer.toUnsignedLong` or `Integer.toUnsignedString` to display with unsigned semantics.

~~~java
// Integer.parseUnsignedInt("4294967296"); // NumberFormatException
// Integer.parseUnsignedInt("-1");         // NumberFormatException
~~~

For `Long.parseUnsignedLong`, the unsigned range is 0 to 18446744073709551615, yet the result still has type `long`; when printing as unsigned, use `Long.toUnsignedString`. If you need to hold positive values larger than `Long.MAX_VALUE` as positive mathematical integers in an object, `BigInteger` usually expresses intent more clearly.

**Do not fix a `parseInt` overflow by switching to unsigned if the data domain is actually signed integers.** Pick the right API per the data specification, not out of a temporary wish to "make parsing pass."

## 6. Whitespace, normalization, and external data

`Integer.parseInt(" 42 ")` fails because it contains whitespace. If the input contract permits trimming **leading and trailing** whitespace, do so explicitly at the input boundary:

~~~java
String raw = " 42 ";
String normalized = raw.strip();
int parsed = Integer.parseInt(normalized); // 42
~~~

`strip` is based on `Character.isWhitespace`; `trim` and `strip` do not recognize the exact same set of characters. You should not claim a single `strip` call handles every kind of whitespace across all data standards.

**Normalize only if the specification permits.** For identifiers, signature tokens, or financial data, stripping `+` signs, leading zeros, group separators, or "look-alike" characters can alter meaning. For example, if a system must keep code `"0012"` distinct from `"12"`, converting to `int` loses the original digit count information.

Do not replace `parseInt` with `replaceAll("[^0-9]", "")` to "clean dirty strings": turning `"-25"` into `"25"`, `"1,234"` into `"1234"`, or a value with stray characters into another number **silently alters data**, easily causing business logic bugs and validation bypasses.

If data accepts localized formats with grouping/decimal separators, parse syntax with an appropriate parser (`NumberFormat` has its own parsing mechanisms and policies). Note that some locale parsers can accept **a partial string**; check the parse end position if the contract requires consuming the entire input. `Integer.parseInt` itself requires a fully valid string.

## 7. Validating errors in the right place: do not swallow `NumberFormatException`

Suppose a CSV column must contain a positive `int` quantity. Input boundary handling might look like:

~~~java
static int parsePositiveQuantity(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    String normalized = raw.strip();
    try {
        int value = Integer.parseInt(normalized);
        if (value <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return value;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "quantity must be a valid 32-bit integer", ex);
    }
}
~~~

This is **an illustrative method**, which must be placed inside a Java class; it is not a standalone program. The structure above separates:

- **Missing field:** `null` → explicit "required" error.
- **Bad syntax or out of range:** `NumberFormatException` → translated into a contextual validation error while preserving `cause` for diagnosis.
- **Valid integer violating business rule:** `0` or negative value → "must be positive" error.

Do not wrap an entire processing pipeline in a broad `catch (Exception)` and return 0 by default. When taking untrusted input, you can return a validation success/failure result or an appropriate user message, while real system errors must remain distinct.

Avoid echoing verbatim error messages for data containing sensitive information, tokens, or overly long fields; use a stable message such as "Invalid integer value" and log carefully. The text of `NumberFormatException.getMessage()` is not a stable machine-readable contract across all APIs/JDK versions.

## 8. Why pre-validation with regex is not enough

You can check signed ASCII decimal syntax with a regular expression:

~~~java
static boolean looksLikeAsciiInteger(String text) {
    return text != null && text.matches("[+-]?[0-9]+");
}
~~~

However, this regex **only checks character patterns**, not numeric type bounds. The string `"999999999999999999999999999999"` still exceeds `int`/`long` limits even though it matches the regex.

Conversely, `parseInt` can accept certain Unicode digits that the ASCII regex above rejects. If the system strictly requires ASCII, that rejection may be intentional and right. If data must accept valid Unicode digits, choose another validation rule.

**Principle:** validate syntax per the data contract first (if genuinely needed), yet still call the appropriate parser and **handle `NumberFormatException`** because range errors can still happen. A single parse call with a narrow `try/catch` is usually simpler than writing manual value bounds checks everywhere.

## 9. Complete Java 17+ example: distinguishing character errors from range errors

Save as file `ParseFailuresDemo.java`:

~~~java
import java.math.BigInteger;

public class ParseFailuresDemo {
    static void checkInt(String input) {
        try {
            System.out.println("parseInt(" + String.valueOf(input)
                    + ") = " + Integer.parseInt(input));
        } catch (NumberFormatException ex) {
            System.out.println("parseInt(" + String.valueOf(input)
                    + ") = NumberFormatException");
        }
    }

    public static void main(String[] args) {
        checkInt("2147483647");
        checkInt("2147483648");
        checkInt("-2147483648");
        checkInt("-2147483649");
        checkInt("12x");
        checkInt("1_000");
        checkInt(" 42 ");
        checkInt("12.0");
        checkInt("");
        checkInt(null);
        checkInt("+42");
        checkInt("0x2A");

        System.out.println("binary 1010 = "
                + Integer.parseInt("1010", 2));
        try {
            Integer.parseInt("102", 2);
        } catch (NumberFormatException ex) {
            System.out.println("binary 102 = NumberFormatException");
        }
        System.out.println("hex 2A = "
                + Integer.parseInt("2A", 16));
        System.out.println("decode 0x2A = "
                + Integer.decode("0x2A"));
        System.out.println("parseInt 010 = "
                + Integer.parseInt("010"));
        System.out.println("decode 010 = "
                + Integer.decode("010"));

        int unsigned = Integer.parseUnsignedInt("4294967295");
        System.out.println("unsigned bits as int = " + unsigned);
        System.out.println("unsigned as long = "
                + Integer.toUnsignedLong(unsigned));
        try {
            Integer.parseUnsignedInt("4294967296");
        } catch (NumberFormatException ex) {
            System.out.println("unsigned 4294967296 = NumberFormatException");
        }
        try {
            Long.parseLong("9223372036854775808");
        } catch (NumberFormatException ex) {
            System.out.println("long overflow = NumberFormatException");
        }
        System.out.println("BigInteger = "
                + new BigInteger("9223372036854775808"));
        System.out.println("strip then parse = "
                + Integer.parseInt(" 42 ".strip()));
    }
}
~~~

Compile/run commands:

~~~bash
javac ParseFailuresDemo.java
java ParseFailuresDemo
~~~

Expected stdout (exceptions are handled in the program so no stack trace is printed):

~~~text
parseInt(2147483647) = 2147483647
parseInt(2147483648) = NumberFormatException
parseInt(-2147483648) = -2147483648
parseInt(-2147483649) = NumberFormatException
parseInt(12x) = NumberFormatException
parseInt(1_000) = NumberFormatException
parseInt( 42 ) = NumberFormatException
parseInt(12.0) = NumberFormatException
parseInt() = NumberFormatException
parseInt(null) = NumberFormatException
parseInt(+42) = 42
parseInt(0x2A) = NumberFormatException
binary 1010 = 10
binary 102 = NumberFormatException
hex 2A = 42
decode 0x2A = 42
parseInt 010 = 10
decode 010 = 8
unsigned bits as int = -1
unsigned as long = 4294967295
unsigned 4294967296 = NumberFormatException
long overflow = NumberFormatException
BigInteger = 9223372036854775808
strip then parse = 42
~~~

The first lines show that the parser **does not distinguish syntax errors from range errors by exception type**: both are `NumberFormatException`. Callers can rely on the data contract to display suitable prompts, rather than inferring the cause by parsing JDK exception message strings.

## 10. When you do not want exceptions to halt the program flow

There are two common strategies, both needing clear intent:

**Strategy A — fail fast.** Used for strictly required data or system configuration values.

~~~java
static int requirePort(String value) {
    int port = Integer.parseInt(value);
    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException("port outside 1..65535");
    }
    return port;
}
~~~

If the string `value` is malformed or out of range, the error is still `NumberFormatException` right at the parse step; if the `int` is valid yet outside the port range, the application throws `IllegalArgumentException`. Keeping this distinction helps fix the right source of error.

**Strategy B — failable parse result.** Used when normal input data can legitimately be missing/invalid and the caller decides what to do.

~~~java
static java.util.OptionalInt tryParseInt(String raw) {
    if (raw == null) {
        return java.util.OptionalInt.empty();
    }
    try {
        return java.util.OptionalInt.of(Integer.parseInt(raw));
    } catch (NumberFormatException ex) {
        return java.util.OptionalInt.empty();
    }
}
~~~

This is an illustrative method inside a class. `OptionalInt.empty()` signals failure without pretending the result is 0. **In exchange, this strategy merges "invalid characters" and "out of range" into a single failure state.** If the UI needs to pinpoint the exact error, design a result type carrying error details or validate input at the application layer.

For streams reading millions of values, do not repeatedly use exceptions as a tokenizer in place of proper data design; consider a parser with a status-returning contract and measure actual performance. Regardless of optimization, you must still verify representable range.

## 11. Misconceptions to avoid

1. **"An all-digit string will definitely parse."** False: `2147483648` has no stray characters yet exceeds `int` range.
2. **"`parseInt` will overflow like `int` addition."** False: it checks range and throws `NumberFormatException`.
3. **"`parseInt` understands Java literal syntax."** False: underscores, `L` suffixes, and `0x` prefixes are not automatically valid in `parseInt(text)`.
4. **"Increasing the radix lets it read `0xFF`."** No: `parseInt("0xFF", 16)` still contains invalid `x`; use `"FF"` with radix 16 or `Integer.decode("0xFF")` if matching the contract.
5. **"`parseInt("010")` is octal."** False: `parseInt` defaults to base 10, unlike `Integer.decode`.
6. **"Calling `strip` removes all 'weird' characters."** False: `strip` only handles recognized whitespace characters at both ends.
7. **"Switching to `long` or `BigInteger` makes a string with invalid characters valid."** False: larger types solve value range, not invalid syntax.
8. **"An unsigned number must always print positively when held in `int`."** False: high unsigned bits appear negative under signed interpretation.
9. **"A valid regex proves NumberFormatException cannot happen."** False: basic regexes usually do not check numeric bounds.
10. **"Catching the exception and returning `0` is safe."** False: it destroys the ability to distinguish valid 0 data from a failed parse.
11. **"The `NumberFormatException` message is a stable API for classifying causes."** Do not parse the message: it can change and is not a business contract.
12. **"Leading zeros have no meaning."** Parsing into `int` may discard identifier formatting. If you need to keep strings like `0012`, store them as strings instead of forcing numeric conversion.

## 12. Checklist when processing external integer strings

1. Determine the **purpose**: quantity, ID, postal code, port, or unsigned bits? Not all digit-only data should be stored as numbers.
2. Define the **input syntax**: are plus/minus signs, radix, `0x` prefixes, Unicode digits, whitespace, or grouping characters permitted?
3. Choose **type and range**: `int`, `long`, unsigned, or `BigInteger`; state business bounds if narrower than the type.
4. Normalize **only per contract**; never blindly strip all "non-digit" characters.
5. Parse with the proper API, catching `NumberFormatException` at the **data boundary** where enough context exists to handle it.
6. Distinguish **syntax error**, **type overflow**, **business-range violation**, and **missing data** in messages or validation results if needed.
7. Never mask failures with `0` or a sentinel number that could be valid data; log safely, preserving raw input when needed for diagnosis.

## 13. Self-check

**Q1.** Why does `Integer.parseInt("2147483648")` throw `NumberFormatException` even though every character is a digit?

**Answer:** The mathematical value 2147483648 is greater than `Integer.MAX_VALUE`. The parser validates both syntax and type range.

**Q2.** Is `Integer.parseInt("1_000")` valid because Java allows writing the literal `1_000`?

**Answer:** No. Underscores are literal syntax in Java source code, not part of the runtime string grammar of `parseInt`.

**Q3.** In binary, why does `Integer.parseInt("102", 2)` fail? How do you convert `"1010"` to decimal?

**Answer:** Digit 2 is invalid in radix 2. `Integer.parseInt("1010", 2)` returns 10.

**Q4.** Are `Integer.parseInt("010")` and `Integer.decode("010")` equal?

**Answer:** No: they return 10 and 8 respectively according to each API's radix rules.

**Q5.** If `Integer.parseUnsignedInt("4294967295")` prints `-1`, is the parser broken?

**Answer:** No. The largest 32-bit unsigned bit pattern, when read as a signed `int`, is -1. Use `Integer.toUnsignedLong` or `Integer.toUnsignedString` to inspect the unsigned value.

**Q6.** How should a valid numeric string exceeding even `Long.MAX_VALUE` be handled? When does `BigInteger` still not help?

**Answer:** Choose `BigInteger` if business rules permit arbitrary-precision integers. `BigInteger` still throws `NumberFormatException` when the string has invalid integer syntax.

## References

- [Java SE 21 — Integer.parseInt, parseUnsignedInt, and decode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
- [Java SE 21 — Long.parseLong and parseUnsignedLong](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).
- [Java SE 21 — NumberFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NumberFormatException.html).
- [Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
- [Java Language Specification `3.10.1 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.1): distinguishing source literal syntax from runtime string parsers.