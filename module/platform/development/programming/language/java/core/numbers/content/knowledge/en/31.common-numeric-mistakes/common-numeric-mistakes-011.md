# Confusing Integer.parseInt, Integer.decode, and Integer.getInteger

## 1. Three Methods, Three Completely Different Meanings

In Java, `java.lang.Integer` has method names that can easily mislead you into thinking they all accept a string and convert it into an integer. The difference lies in **whether the passed string is a value or a configuration property name** and in **the radix rules**:

- **`Integer.parseInt(String)`** parses **the contents of a value string** in **base 10 (decimal)**, returning primitive `int`. The overload `parseInt(String, int radix)` uses an explicit radix from 2 to 36.
- **`Integer.decode(String)`** parses **the contents of a value string** and recognizes prefixes to infer the radix automatically: `0x`/`0X` or `#` for hex, a leading `0` on multi-digit strings for octal, and no prefix for decimal. The return type is `Integer`.
- **`Integer.getInteger(String)`** treats the string argument as **a JVM system property name**, reads that property, and then interprets **the property's value** as `decode` does; it does not parse the passed argument itself. The result is `Integer`, or `null` if absent/unparseable when no default is given.

Example:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
```

Meanwhile, `Integer.getInteger("010")` looks up **a system property named `010`**; the result depends on JVM configuration and may be `null`. It does not mean converting the string `"010"` to `10` or `8`.

### Comparison Table

| Criterion | `parseInt` | `decode` | `getInteger` |
| --- | --- | --- | --- |
| String parameter | Value to parse | Value to decode | **Property name** |
| Actual source of number | Argument `s` | Argument `nm` | `System.getProperty(name)` |
| Default radix | 10 | Inferred from prefix | Inferred from **property value** |
| Input `"010"` | 10 | 8 | Looks up property named `010` |
| Input `"0x10"` | Error | 16 | Looks up property named `0x10` |
| Return type | `int` | `Integer` | `Integer` |
| Invalid number string | Throws `NumberFormatException` | Throws `NumberFormatException` | `null` or default value if property cannot be parsed |
| Intended for | Integers with explicit radix | Integers allowing prefixes | JVM `-D` configuration |

This is a lesson in **choosing APIs by data contract**, not just memorizing method names. The mistake often stays hidden when testing `"123"`, since `parseInt` and `decode` both return 123; inputs with leading zeros and JVM properties expose the difference.

## 2. parseInt: Default Decimal Integers

`Integer.parseInt(String s)` uses radix 10:

```java
System.out.println(Integer.parseInt("42"));   // 42
System.out.println(Integer.parseInt("+42"));  // 42
System.out.println(Integer.parseInt("-42"));  // -42
System.out.println(Integer.parseInt("010"));  // 10
System.out.println(Integer.parseInt("08"));   // 8
```

A `+` or `-` sign may appear **at the start** of the number. A leading `0` does **not** turn the string into octal. Conversely, the following strings are **invalid** for the decimal overload:

```java
// Each line below throws NumberFormatException at runtime:
Integer.parseInt("0x10");
Integer.parseInt("12.5");
Integer.parseInt("1_000");
Integer.parseInt(" 42 ");
Integer.parseInt("");
Integer.parseInt("2147483648");
```

`parseInt` does not strip whitespace, accept thousands separators, or accept underscores `_` in strings. Java source code supports numeric literals like `1_000`, yet Java literal syntax **is not the same as** the runtime string syntax of `parseInt`.

### Explicit Radix

`Integer.parseInt(String s, int radix)` supports radices from `Character.MIN_RADIX` (2) through `Character.MAX_RADIX` (36):

```java
System.out.println(Integer.parseInt("1010", 2)); // 10
System.out.println(Integer.parseInt("17", 8));   // 15
System.out.println(Integer.parseInt("10", 16));  // 16
System.out.println(Integer.parseInt("ff", 16));  // 255
System.out.println(Integer.parseInt("-ff", 16)); // -255
System.out.println(Integer.parseInt("Z", 36));   // 35
```

Even when passing radix 16, **the `0x` prefix is not accepted**:

```java
// Both throw NumberFormatException:
Integer.parseInt("0x10", 16);
Integer.parseInt("0b1010", 2);
```

To parse `"0x10"` in radix 16, strip the prefix after validation and parse `"10"`, or use `decode` if the syntax contract permits it. If stripping the prefix manually, handle `+`/`-` before the prefix, empty strings, and `int` bounds.

**Return type:** `parseInt` returns primitive `int`, whereas `Integer.valueOf("42")` returns wrapper `Integer` after decimal parsing. Neither looks up a system property.

## 3. decode: Prefixes and the Octal Trap

`Integer.decode(String nm)` accepts the following representations:

| Input | Radix | Result |
| --- | ---: | ---: |
| `"42"` | 10 | 42 |
| `"0x2A"` | 16 | 42 |
| `"0X2a"` | 16 | 42 |
| `"#2A"` | 16 | 42 |
| `"052"` | 8 | 42 |
| `"-0x2A"` | 16 | -42 |
| `"+052"` | 8 | 42 |

```java
System.out.println(Integer.decode("42"));    // 42
System.out.println(Integer.decode("0x2A"));  // 42
System.out.println(Integer.decode("0X2a"));  // 42
System.out.println(Integer.decode("#2A"));   // 42
System.out.println(Integer.decode("052"));   // 42
System.out.println(Integer.decode("-0x2A")); // -42
System.out.println(Integer.decode("+052"));  // 42
```

Place the sign before the prefix: `"-0x2A"` is valid, while `"0x-2A"` is invalid. Hexadecimal allows digits `a-f` or `A-F`.

**Biggest risk: leading zeros mean octal.** For values zero-padded for display:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
System.out.println(Integer.parseInt("08"));  // 8
// Integer.decode("08") -> NumberFormatException
```

Because `8` and `9` are not octal digits, `decode("08")` or `decode("09")` fails. If users enter zero-padded decimal quantities, `parseInt` is far more appropriate.

### decode Does Not Accept All Java Literals

Java source supports `0b1010` as a binary integer literal, yet `Integer.decode("0b1010")` **cannot** parse it. Use `Integer.parseInt("1010", 2)` when the contract specifies radix 2.

```java
System.out.println(0b1010);                    // 10: literal in code
System.out.println(Integer.parseInt("1010", 2)); // 10
// Integer.decode("0b1010") throws NumberFormatException
```

`decode` also does not parse fractional numbers like `"10.5"`. It returns a signed `Integer`, so an input representing a value larger than `Integer.MAX_VALUE` does not become a valid positive number just because it was written in hex.

## 4. getInteger: Reads a JVM System Property, Not a Direct Value

`Integer.getInteger(String name)` is conceptually equivalent to looking up a string from a system property and then decoding **its value**:

```java
String raw = System.getProperty("app.maxWorkers");
Integer parsed = raw == null ? null : Integer.decode(raw);
```

This only illustrates **the data flow**; the real API also handles malformed property syntax and default values. Keep in mind:

```java
System.setProperty("app.maxWorkers", "0x10");

System.out.println(System.getProperty("app.maxWorkers")); // 0x10
System.out.println(Integer.getInteger("app.maxWorkers")); // 16
System.out.println(Integer.getInteger("app.maxWorkers", 4)); // 16
```

`System.getProperty` returns the raw string, whereas `getInteger` returns an `Integer` after decoding. Never assume `getInteger("100")` yields 100; it looks up a property named `100`.

### Three Overloads

```java
Integer.getInteger(String name)
Integer.getInteger(String name, int defaultValue)
Integer.getInteger(String name, Integer defaultValue)
```

These are **illustrative signatures**, not three Java statements placed inside a method body. The overload without a default returns `null` if the property does not exist **or its value cannot be decoded**. The overloads with a default return that default value in both cases.

```java
System.setProperty("app.retryLimit", "08");

System.out.println(Integer.getInteger("app.retryLimit"));    // null
System.out.println(Integer.getInteger("app.retryLimit", 3)); // 3
```

Why? `getInteger` uses `decode` logic on `"08"`, so octal parsing fails. Notably, in `getInteger`, **a configuration syntax error can be masked by the default**, whereas calling `decode("08")` directly throws `NumberFormatException`.

### JVM -D Properties and Environment Variables Are Different

System properties can be passed at program startup:

```bash
java -Dapp.maxWorkers=0x10 App
```

In that case, `Integer.getInteger("app.maxWorkers")` can return 16. By contrast, an environment variable `APP_MAX_WORKERS` must be read using:

```java
String raw = System.getenv("APP_MAX_WORKERS");
int maxWorkers = raw == null ? 4 : Integer.parseInt(raw);
```

The snippet above is illustrative only; production code needs syntax error reporting and range checks. **`Integer.getInteger("APP_MAX_WORKERS")` does not read environment variables** — unless the JVM happens to have a *separate* system property with the same name, the two configuration namespaces are completely distinct.

System properties are JVM-wide and mutable at runtime. In tests, save the old value, set the temporary property, and restore it in `finally`. Property access can also be restricted, and a `SecurityException` is a different issue from a "missing property".

## 5. Table of Cases Distinguishing the Three APIs

| Expression | Result / Meaning |
| --- | --- |
| `parseInt("10")` | 10 |
| `parseInt("010")` | 10 |
| `decode("010")` | 8 |
| `parseInt("10", 8)` | 8 |
| `parseInt("10", 16)` | 16 |
| `decode("0x10")` | 16 |
| `decode("#10")` | 16 |
| `decode("-0x10")` | -16 |
| `parseInt("08")` | 8 |
| `decode("08")` | `NumberFormatException` |
| `parseInt("0x10")` | `NumberFormatException` |
| `parseInt("0x10", 16)` | `NumberFormatException` |
| `parseInt("1010", 2)` | 10 |
| `decode("0b1010")` | `NumberFormatException` |
| `getInteger("app.limit")` | Value read from property `app.limit`; may be `null` |
| `getInteger("010")` | Looks up **property named 010**, does not parse number 010 |

Choose a parser based on **the input specification**, not whichever method feels most convenient. For user-entered decimals, silently supporting octal is usually a dangerous surprise.

## 6. Complete Java 17+ Program and Deterministic Stdout

This program sets uniquely named system properties itself, clears a property representing "missing" within the scope of the example, and restores the initial state via `finally`. It checks error cases by catching `NumberFormatException` and printing the exception name rather than relying on error message text that may vary across JDKs.

Save as **`IntegerMethodComparison.java`**:

```java
public class IntegerMethodComparison {

    static void restore(String key, String previous) {
        if (previous == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, previous);
        }
    }

    static void expectBad(String label, String text, boolean decode) {
        try {
            if (decode) {
                Integer.decode(text);
            } else {
                Integer.parseInt(text);
            }
            System.out.println(label + ": unexpectedly accepted");
        } catch (NumberFormatException ex) {
            System.out.println(label + ": NumberFormatException");
        }
    }

    public static void main(String[] args) {
        System.out.println("parseInt 010 = " + Integer.parseInt("010"));
        System.out.println("decode 010 = " + Integer.decode("010"));
        System.out.println("parseInt base16 = "
                + Integer.parseInt("10", 16));
        System.out.println("decode hex = " + Integer.decode("0x10"));
        System.out.println("decode #2A = " + Integer.decode("#2A"));
        System.out.println("decode -010 = " + Integer.decode("-010"));

        expectBad("parseInt 0x10", "0x10", false);
        expectBad("decode 08", "08", true);
        expectBad("decode 0b1010", "0b1010", true);
        expectBad("parseInt overflow", "2147483648", false);

        String good = "lesson381.integer.good";
        String invalid = "lesson381.integer.invalid";
        String absent = "lesson381.integer.absent";
        String prevGood = System.getProperty(good);
        String prevInvalid = System.getProperty(invalid);
        String prevAbsent = System.getProperty(absent);

        try {
            System.setProperty(good, "0x10");
            System.setProperty(invalid, "08");
            System.clearProperty(absent);

            System.out.println("raw property = "
                    + System.getProperty(good));
            System.out.println("getInteger good = "
                    + Integer.getInteger(good));
            System.out.println("getInteger invalid default = "
                    + Integer.getInteger(invalid, 7));
            System.out.println("getInteger absent = "
                    + Integer.getInteger(absent));
            System.out.println("getInteger absent default = "
                    + Integer.getInteger(absent, 3));
        } finally {
            restore(good, prevGood);
            restore(invalid, prevInvalid);
            restore(absent, prevAbsent);
        }
    }
}
```

Run with JDK 17 or newer, from the directory containing the file:

```bash
javac IntegerMethodComparison.java
java IntegerMethodComparison
```

Expected output:

```text
parseInt 010 = 10
decode 010 = 8
parseInt base16 = 16
decode hex = 16
decode #2A = 42
decode -010 = -8
parseInt 0x10: NumberFormatException
decode 08: NumberFormatException
decode 0b1010: NumberFormatException
parseInt overflow: NumberFormatException
raw property = 0x10
getInteger good = 16
getInteger invalid default = 7
getInteger absent = null
getInteger absent default = 3
```

The example tests both **radix differences** and **data-source differences** simultaneously. It does not rely on any pre-existing system property; values are temporarily overridden and restored. Using unique property names limits impact on other code in the same JVM, though real-world tests must still watch out for concurrent threads sharing global properties.

## 7. Controlling Input Syntax: Parsing True Decimal

For count data received from a form or API, users normally expect decimal, possibly with leading zeros. A strict function can reject anything other than ASCII digits, validate bounds, and then parse:

```java
static int parseItemCount(String raw) {
    if (raw == null || !raw.matches("[0-9]+")) {
        throw new IllegalArgumentException(
                "Count must use ASCII decimal digits only");
    }
    final int count;
    try {
        count = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Count exceeds int range", ex);
    }
    if (count > 5000) {
        throw new IllegalArgumentException("Count too large");
    }
    return count;
}
```

This is an **illustrative method that must live inside a class**, not a complete program. It accepts `"0008"` as decimal 8 and rejects `"-2"`, `"+2"`, whitespace, `"0x10"`, commas, and non-ASCII Unicode digits. If the contract permits negative numbers, plus signs, or outer whitespace, update validation explicitly instead of switching `parseInt` to `decode`.

`parseInt` internally uses `Character.digit` for each character in the given radix, so it can accept certain Unicode digits. If the system requires **strict ASCII**, add a validation step as shown above.

### What If Users Want to Enter Hex?

If the contract permits decimal `42` or hex `0x2A` yet **not** leading-zero octal, `decode` is not quite right. You can detect the hex prefix and apply `parseInt` with radix 16, parsing everything else as decimal. Make sure `-` and `+` signs are handled before the prefix, and do not let bare `"0x"` slip through.

Test `"08"`, `"010"`, `"0x2A"`, `"-0x2A"`, `"0x"`, and values exceeding `int`. Parser behavior should be defined by the concrete protocol rather than blindly copying Java source literal rules.

## 8. getInteger with a Default Can Hide Configuration Errors

Consider `-Dapp.poolSize=08`. The operator expects eight threads; if the program calls:

```java
int poolSize = Integer.getInteger("app.poolSize", 4);
```

the actual value becomes **4**, because `decode("08")` is invalid in octal and the API falls back to the default. The program runs, yet not with the intended configuration. This contrasts with `parseInt("08")`, which returns 8.

A **stricter decimal** approach:

```java
static int positiveDecimalProperty(String name, int defaultValue) {
    String raw = System.getProperty(name);
    if (raw == null) {
        return defaultValue; // Only use default when missing.
    }

    final int value;
    try {
        value = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid decimal property: " + name, ex);
    }
    if (value <= 0) {
        throw new IllegalArgumentException(
                "Property must be positive: " + name);
    }
    return value;
}
```

This is an illustrative method to place inside a class; the example assumes `defaultValue` is valid in the positive domain, so callers should also validate the default. It distinguishes a **missing** property from a **present yet malformed** property while ensuring the number is greater than 0.

If a property is required, do not return a default when missing; throw `IllegalStateException` or a configuration exception with a clear message. If `0x` is allowed while implicit octal is forbidden, give the parser an explicit policy instead of using `getInteger` as a magic validator.

## 9. Overflow, Wrapper Types, null, and Signedness

`Integer.parseInt` and `Integer.decode` handle 32-bit signed integers: range `-2147483648` to `2147483647`. Strings representing out-of-range values throw `NumberFormatException`:

```java
// These calls throw NumberFormatException:
Integer.parseInt("2147483648");
Integer.decode("0x80000000");
```

If values larger than `int` are needed, consider `Long.parseLong`/`Long.decode` or `java.math.BigInteger`. For 32-bit unsigned bit patterns, `Integer.parseUnsignedInt` has a different contract: it can return an `int` whose bit pattern is interpreted as negative when signed; use `Integer.toUnsignedString` or a wider type when presenting it. Never cast blindly or use `decode` as an unsigned parser.

Because `getInteger` returns a nullable `Integer`, auto-unboxing can throw `NullPointerException`:

```java
Integer maybePort = Integer.getInteger("app.port");
if (maybePort != null) {
    int port = maybePort;
    System.out.println(port);
}
```

Do not write `int port = Integer.getInteger("app.port");` unless the property is guaranteed to exist and be valid. Use an overload with a default when a fallback is defined, or check null explicitly.

`Integer.valueOf("123")` returns wrapper `Integer`; `Integer.parseInt("123")` returns primitive `int`. Comparing two wrappers with `==` can depend on object caching; use `equals` for values (after checking null), or compare primitives.

## 10. Regression Tests for Confusion Bugs

When reviewing uses of `parseInt`, `decode`, and `getInteger`, test at least these input groups:

| Group | Data | What to Verify |
| --- | --- | --- |
| Standard decimal | `"0"`, `"123"`, `"-9"` | Sign and radix 10. |
| Zero-padded | `"010"`, `"08"`, `"009"` | `decode` changes meaning or rejects. |
| Hex | `"0x2A"`, `"#2A"`, `"-0x2A"` | `decode` accepts; decimal `parseInt` rejects. |
| Binary | `"1010"` radix 2, `"0b1010"` | Binary prefix is unsupported by `decode`. |
| Unclean | `""`, `" 42 "`, `"1_000"`, `"12.0"` | Verify NFE/validation. |
| int boundaries | `"2147483647"`, `"2147483648"`, `"-2147483648"` | Overflow or exact acceptance. |
| Missing property | Unset test key | `getInteger` returns null/default. |
| Invalid property | `"08"`, `"abc"` | Default can mask errors; strict parser must catch them. |
| Valid property | `"42"`, `"0x2A"` | Value is parsed via `decode`. |
| Source distinction | `-Dapp.x` vs separate environment variable | `getInteger` reads only system properties. |

In unit tests, do not use common existing property names like `java.version` to demonstrate a specific integer. Create an isolated key, save its initial value, set/clear it, and restore it in `finally`. If running tests in parallel, system properties are **global state** and can cause races; prefer passing configuration into functions via parameters or config objects instead of relying solely on JVM state.

### Diagnostic Checklist When a Config Value Is Wrong

1. Inspect the method **argument**: is it a value `"08"` or a key `"app.limit"`?
2. Inspect the **raw value** from `System.getProperty` if using `getInteger`.
3. State the expected radix explicitly: decimal, implicit octal, hex, or binary.
4. Check signs, prefixes, whitespace, and invalid characters.
5. Check `int` bounds and whether `long`/`BigInteger` is needed.
6. Decide whether missing configuration falls back to a default or must fail.
7. Write regression tests for `"010"`, `"08"`, and `"0x10"`; these three cases distinguish parsers far faster than `"123"`.

## 11. Common Mistakes

1. **Calling `getInteger("42")` to convert `"42"` to a number:** actually looks up a property named `42`.
2. **Assuming `getInteger` reads environment variables:** it reads JVM system properties, not `System.getenv`.
3. **Using `decode` for zero-padded decimal numbers:** `"010"` becomes 8 and `"08"` throws an error.
4. **Passing `0x` into `parseInt(s,16)`:** requires radix-16 digits without a prefix.
5. **Using `decode` to parse `0b`:** binary prefixes are not supported.
6. **Assuming string inputs support underscores like Java literals:** `"1_000"` is invalid for all of these parsers.
7. **Failing to distinguish missing vs. invalid properties:** `getInteger(name,default)` uses the default for both.
8. **Ignoring null from `getInteger`:** auto-unboxing throws NPE when the property is missing or malformed.
9. **Not checking `int` overflow:** oversized strings cannot be parsed into a signed 32-bit number.
10. **Abusing `decode` out of convenience:** protocols needing decimal must use a decimal parser rather than silently altering input semantics.
11. **Using wrapper `==` as a content check:** risks instance caching confusion; check values via `equals`/primitives.
12. **Hiding all parsing errors with catch-and-return-0:** bad config becomes a silent business bug; classify and report with field names.
13. **Using `Integer` for decimals with fractional parts:** if monetary/measurement data needs exact decimals, use `BigDecimal` and an appropriate rounding policy.
14. **Assuming `parseInt` validates ASCII:** it uses `Character.digit`; validate ASCII format upfront if the protocol requires it.
15. **Not testing properties via `-D` and `System.setProperty`:** tests calling `decode` directly miss key/property confusion bugs.

## 12. Self-Check Questions

**Question 1.** What are `parseInt("075")` and `decode("075")`?

**Answer:** 75 and 61. `decode` treats `075` as octal, i.e., `7 × 8 + 5 = 61`.

**Question 2.** Why does `parseInt("08")` yield 8 while `decode("08")` throws an error?

**Answer:** `parseInt` defaults to radix 10; `decode` with a leading 0 uses radix 8, and octal has no digit 8.

**Question 3.** Which method should you choose to parse `"0x2A"`?

**Answer:** `Integer.decode("0x2A")` returns 42; if using `parseInt` with radix 16, pass only the digits `"2A"`.

**Question 4.** Does `getInteger("123")` return 123?

**Answer:** Not by default. It looks up a JVM system property named `123`; only if that property exists with a valid value does it decode that value.

**Question 5.** Why might `getInteger("app.workers", 4)` be unsuitable for required configuration?

**Answer:** Both a missing property and a malformed one yield the default 4, masking operator typos.

**Question 6.** Is `"0b1010"` accepted by `decode`?

**Answer:** No. Use `Integer.parseInt("1010", 2)` when the radix is known.

**Question 7.** With property `app.port` set to `"0x1F90"`, what is `getInteger("app.port")`?

**Answer:** 8080, because `0x1F90` is hexadecimal.

**Question 8.** When should you validate `[0-9]+` before `parseInt`?

**Answer:** When the protocol requires pure ASCII digits and forbids Unicode digits, plus/minus signs, or other characters the parser might accept.

**Question 9.** Why is `int x = Integer.getInteger("missing.key")` dangerous?

**Answer:** If the property is absent, `getInteger` returns `null`; auto-unboxing to `int` causes `NullPointerException`.

**Question 10.** What are the three best test values to catch parser confusion?

**Answer:** `"010"`, `"08"`, and `"0x10"` — they produce starkly different outputs/errors between `parseInt` and `decode`; for `getInteger`, also test with named properties.

## 13. References

- [Java SE 17 — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `valueOf`, `decode`, `getInteger`, signed/unsigned, and overloads.
- [Java SE 17 — System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `getProperty`, `setProperty`, `clearProperty`, and `getenv`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `Character.digit` and digits by radix.
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): integers beyond `int` range when needed by the application.

**Remember:** `parseInt` reads **a value with a specified radix**, `decode` reads **a value with hex/octal prefixes**, and `getInteger` reads **a JVM system property by name** and decodes the property's content. To keep code clear, call the right API for **the data source, syntax, and error policy**; test leading zeros and invalid properties before assuming two calls are equivalent.
