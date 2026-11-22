# Validating Full Input and Whitespace Policies When Parsing Integers in Java

A string that looks like a number is not necessarily a **valid integer input**. For example, `"42"`, `" 42 "`, `"42abc"`, `"4 2"`, or `"１２３"` can be handled differently depending on the parser, valid character set, and **whitespace-handling policy**. When data comes from users, configuration files, or protocols, two questions must be answered before calling `parseInt` or `parseLong`:

1. **Does the parser validate the entire string?** Or does it only consume a number-like prefix and ignore the tail?
2. **Which whitespace characters are permitted in the string, and where?** Reject all whitespace, strip only outer whitespace, or accept locale-dependent grouping/formatting?

In Java, **`Integer.parseInt` and `Long.parseLong` validate the entire passed integer string**. They do not automatically strip whitespace. This provides a solid foundation for a strict parser, yet **does not automatically define the entire business policy**: for instance, the Java parser can accept Unicode digits, whereas an external protocol allows only ASCII.

```java
int a = Integer.parseInt("42");       // 42.
// int b = Integer.parseInt(" 42 ");  // NumberFormatException.
// int c = Integer.parseInt("42abc"); // NumberFormatException.
int d = Integer.parseInt(" 42 ".strip()); // 42: DELIBERATELY strip outer whitespace.
```

The snippet above is an **illustrative fragment** that can be placed inside a method; two lines leading to exceptions are commented out. Calling `strip()` should not be assumed always good: in some protocols, having an extra space or newline is itself a data error that must be detected.

## 1. What does "validating the entire input" mean?

Suppose an application receives `"123abc"`. There are two very different behaviors:

- **Full-string parsing:** accepts only when **the entire specified input** matches integer syntax, with no trailing characters. The string `"123abc"` is rejected.
- **Prefix parsing:** accepts the `"123"` prefix, returns 123, and stops before `a`, potentially ignoring `"abc"` if the caller does not check the stopping position.

`Integer.parseInt(String)`, `Long.parseLong(String)`, `Byte.parseByte(String)`, `Short.parseShort(String)`, and their radix overloads follow the rule that **the integer input must be parsed in full**. For example:

```java
int value = Integer.parseInt("123"); // 123.
// Integer.parseInt("123abc");      // Throws NumberFormatException.
// Long.parseLong("123.0");         // Throws NumberFormatException.
```

The syntax of `parseInt` has an optional leading `+` or `-` sign, followed by accepted digits in the radix; stray characters, decimal points, suffixes, or trailing characters cause the parser to fail. **Range bounds** are also checked: `Integer.parseInt("2147483648")` throws `NumberFormatException` even though the string contains only decimal digits.

**Distinguishing validation scope:** `Integer.parseInt(CharSequence s, int begin, int end, int radix)` validates only **the entire specified slice `[begin,end)`**, rather than automatically inspecting characters outside the slice. If you pass the `"123"` slice of `"123abc"`, calling that "parsing the entire source string" would be wrong. When using a slice-based parser, ensuring accurate slice boundaries is the caller's responsibility.

## 2. Three common whitespace-handling policies

| Policy | Accepted examples | Rejected examples | When appropriate |
| --- | --- | --- | --- |
| **STRICT**: no normalization | `"42"`, `"-42"` | `" 42"`, `"42\n"` | Machine-readable files or protocols requiring exact syntax |
| **OUTER-STRIP**: strip outer whitespace | `" 42 "`, `"\t-42\n"` | `"4 2"` | Form/CLI input allowing users to leave extra spaces at both ends |
| **LOCALE-AWARE**: per cultural rules | E.g. `"1,234"` in US locale | Depends on locale and configuration | Strings entered by users by language/region with digit grouping |

**Do not conflate policies automatically.** If a system needs byte-level control or schema compliance, a value `"42\n"` may have to be rejected to catch framing errors. If an application prioritizes user-friendliness, stripping outer whitespace may be appropriate, provided it is clearly documented in the input contract.

The OUTER-STRIP policy does not mean removing all whitespace:

```java
" 42 ".strip().equals("42"); // true
"4 2".strip().equals("42");  // false: internal whitespace remains
```

In `String`, `strip`, `stripLeading`, and `stripTrailing` **affect only the edges**, never deleting or joining internal characters. Unconditionally calling `replaceAll("\\s+", "")` can turn `"4 2"` into `"42"` and mask bad input — never do this unless the schema genuinely mandates stripping separators.

## 3. `parseInt` and `parseLong` do not strip whitespace

```java
int a = Integer.parseInt("42"); // 42.
// Integer.parseInt(" 42");     // NumberFormatException.
// Integer.parseInt("42 ");     // NumberFormatException.
// Integer.parseInt("\t42");   // NumberFormatException.
```

`parseInt` itself does not treat spaces/tabs/newlines as valid components of a digit. A `+` or `-` sign is accepted at the **start of the number portion** (`"+42"`, `"-42"`), with no whitespace between the sign and the digits:

```java
int positive = Integer.parseInt("+42"); // 42.
// Integer.parseInt("+ 42");             // NumberFormatException.
// Integer.parseInt("4 2");              // NumberFormatException.
```

If data permits leading/trailing whitespace, call `strip()` **before** parsing:

```java
String raw = "  -42\t";
int n = Integer.parseInt(raw.strip()); // -42
```

However, distinguish **normalizing the string and then parsing in full** from **parsing the raw data in full**. After `strip`, some characters from the original data were intentionally discarded; do not claim "the parser validated every original character" if you chose input normalization.

## 4. How does `trim()` differ from `strip()`?

In Java 17:

- **`String.trim()`** removes leading/trailing characters with code `<= U+0020`. This is a historical code-unit-based rule, not all Unicode whitespace.
- **`String.strip()`** (Java 11+) relies on `Character.isWhitespace` per Unicode/Java, handling many non-ASCII spaces such as **EM SPACE U+2003**.
- **`stripLeading()`** and **`stripTrailing()`** strip only one side using the same `isWhitespace` rule.
- **`isBlank()`** tells whether a string is empty or contains only code points considered whitespace by `Character.isWhitespace`, not whether it is a valid number.

Concrete example:

```java
String surrounded = "\u200342\u2003"; // EM SPACE at both ends.
String trimmed = surrounded.trim();    // Still contains EM SPACE.
String stripped = surrounded.strip();  // "42".
int number = Integer.parseInt(stripped); // 42.
```

`strip` **does not mean removing every Unicode character that looks like whitespace**. For instance, `NO-BREAK SPACE U+00A0` is not considered whitespace by `Character.isWhitespace`. Therefore:

```java
String nbsp = "\u00A042\u00A0";
boolean unchanged = nbsp.strip().equals(nbsp); // true.
```

Do not assume `strip()` "cleans every kind of space." If data may contain NBSP, NARROW NO-BREAK SPACE, or other invisible characters, **decide whether to allow them**, and validate against an explicitly designed character list or encoding rule. Arbitrary normalization can make two distinct strings identical, breaking formatting contracts.

## 5. Validating the entire string with an ASCII regex before parsing

If a protocol requires decimal numbers **consisting strictly of ASCII digits**, a simple pattern is:

```regex
[+-]?[0-9]+
```

- `[+-]?`: allows at most one leading plus or minus sign (if the schema permits).
- `[0-9]+`: requires at least one ASCII digit.
- Call **`Matcher.matches()`**, not `find()`, to require *the entire string* to match the pattern.

Example methods inside a Java class:

```java
private static final java.util.regex.Pattern ASCII_INTEGER =
        java.util.regex.Pattern.compile("[+-]?[0-9]+");

static int parseAsciiStrict(String text) {
    java.util.Objects.requireNonNull(text, "text");
    if (!ASCII_INTEGER.matcher(text).matches()) {
        throw new IllegalArgumentException("Invalid ASCII integer");
    }
    return Integer.parseInt(text); // Still need to check int range.
}
```

These are **two class-level declarations**, not a standalone runnable file. The regex guarantees **valid ASCII syntax**, while `Integer.parseInt` guarantees **valid signed int range**. `"2147483648"` matches the regex yet is rejected during parsing because it exceeds the range.

Use `[0-9]` if you genuinely want ASCII. Some regex shorthands like `\\d` have semantics affected by regex engine flags and Unicode mode; writing `[0-9]` explicitly is usually clearer for ASCII protocols.

For a strict parser forbidding `+` or `-` signs, change the pattern to `[0-9]+` and verify non-negativity if needed. For a schema allowing negative numbers but **forbidding `+`**, use `-?[0-9]+`. For canonical requirements (such as forbidding `"0007"`), add a separate validation rule; the regex above **allows leading zeros**.

## 6. Parser rejecting all whitespace vs. parser accepting outer whitespace

You can implement both policies by separating the validation layer from the normalization step:

```java
static int parseAsciiWithOuterWhitespace(String text) {
    java.util.Objects.requireNonNull(text, "text");
    return parseAsciiStrict(text.strip());
}
```

Note this is a **method inside the same class** where `parseAsciiStrict` is defined. It accepts `" 42 "` or `"\t-42\n"`, yet rejects `"4 2"` and `"4\n2"`: `strip` does not remove internal characters.

An example of deliberate normalization:

```text
Input raw:       "  -42  "
Policy:          allow Unicode whitespace at both ends via strip()
Normalized:      "-42"
ASCII grammar:   [+-]?[0-9]+   → pass
Integer range:   -2^31..2^31-1 → pass
Parsed int:      -42
```

**Order of checks matters.** If you check the regex before `strip()`, inputs with outer whitespace will be rejected. If you `strip()` first, those inputs are accepted per policy. The two orders are not equivalent, so the choice must be clearly documented in the API spec.

## 7. Unicode digits: `parseInt` does not mean ASCII-only

Java can treat many Unicode digit characters as valid digits based on `Character.digit`, even when they are not ASCII `'0'` through `'9'`. For example:

```java
int value = Integer.parseInt("１２３"); // 123.
```

`"１２３"` here contains **FULLWIDTH DIGIT ONE/TWO/THREE**, which Java 17 parses as 123. If a system has an ASCII-only rule (e.g., a technical field requiring bytes `0x30`–`0x39`), then **calling `parseInt` alone is not enough to enforce the contract**.

Use `[0-9]` with `matches()` as in the example above to reject non-ASCII digits. Conversely, in internationalized applications you may intentionally accept Unicode digits — in which case clearly specify the accepted character domain and test each input kind.

Do not conflate **Unicode whitespace** with **Unicode digits**: `strip()` handles certain outer characters, while `parseInt` handles digits inside; they are two independent rules.

## 8. The danger of prefix-only parsers: `NumberFormat`

Locale-based number parsers can accept **only a prefix** of the input. For example, with `java.text.NumberFormat` and `ParsePosition`:

```java
String text = "123abc";
java.text.ParsePosition pos = new java.text.ParsePosition(0);
Number n = java.text.NumberFormat
        .getIntegerInstance(java.util.Locale.US)
        .parse(text, pos);
// n = 123; pos.getIndex() = 3; "abc" was not consumed.
```

`NumberFormat` is useful when handling locale-formatted numbers (grouping separators, local symbols), yet **is not by default a full-input validator for a strict protocol**.

If deliberately using `ParsePosition`, you must check both:

```java
boolean parsedSomething = n != null;
boolean consumedAll = parsedSomething && pos.getIndex() == text.length();
```

If `pos.getIndex()` is less than `text.length()`, unconsumed characters remain. When defining an **integer** by locale, also consider how the parser handles decimal points, grouping separators, rounding, and return-type bounds. `getIntegerInstance` does not mean the parser guarantees a 32-bit signed `int` and does not replace `Integer.parseInt`.

**Remember:** `String.matches` or `Matcher.matches()` checks the full string; `Matcher.find()`, `NumberFormat.parse`, or a regex `find` may match only **a part**. Do not treat "successfully read 123" as proof that "the entire original string is valid."

## 9. `parseInt(CharSequence, begin, end, radix)`: exact slice, not entire source

In modern Java releases (including Java 17), you can parse a portion of a `CharSequence`:

```java
CharSequence message = new StringBuilder("id=42;tail");
int result = Integer.parseInt(message, 3, 5, 10); // 42.
```

`beginIndex` (3) is the **inclusive** start position, and `endIndex` (5) is the **exclusive** end position. It consumes `"42"` across that exact span without requiring `";tail"` to be numeric. This is **intentional behavior for parsing sub-fields**, not an API bug.

If the source is expected to contain **only a single integer field**, use the full-string overload and/or explicitly check delimiters/length outside the slice. If a record has multiple fields, parsing the slice accurately is not enough: you need a **full-record parser** verifying prefixes, separators, field counts, end positions, and trailing bytes.

This is the distinction between **full-field validation** and **full-record validation**. A field can be syntactically valid as a number while the record containing it still violates the schema.

## 10. Table of whitespace kinds and easily confused characters

| Example character/string | `trim()` at edges | `strip()` at edges | Direct `parseInt` | Notes |
| --- | --- | --- | --- | --- |
| `" 42 "` (SPACE U+0020) | Removed | Removed | Error | Common ASCII space |
| `"\t42\n"` (TAB/LF) | Removed | Removed | Error | Outer newline may indicate a framing error |
| `"\u200342\u2003"` (EM SPACE) | Not removed | Removed | Error | Recognized by Unicode `Character.isWhitespace` |
| `"\u00A042\u00A0"` (NBSP) | Not removed | Not removed | Error | Not whitespace under `isWhitespace` |
| `"4 2"` | Middle unchanged | Middle unchanged | Error | Does not automatically join into 42 |
| `"42abc"` | No | No | Error | Trailing characters; full-string parser rejects |
| `"42\u200B"` (ZERO WIDTH SPACE) | Not removed | Not removed | Error | Invisible character outside default policy |
| `"１２３"` (full-width digits) | Irrelevant | Irrelevant | **123** | If ASCII-only, must validate separately |
| `"0007"` | Irrelevant | Irrelevant | **7** | Parsing loses original string representation with leading zeros |

The table describes **Java 17** for the specified characters. With Unicode data, inspect string **code points** when debugging instead of trusting visual appearance; many characters look like spaces or ASCII digits yet have different code points.

## 11. Standalone runnable Java 17+ program

Save file **`CompleteIntegerInputDemo.java`**:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public class CompleteIntegerInputDemo {
    private static final Pattern ASCII_INTEGER =
            Pattern.compile("[+-]?[0-9]+");

    static int parseAsciiStrict(String text) {
        Objects.requireNonNull(text, "text");
        if (!ASCII_INTEGER.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid ASCII integer");
        }
        return Integer.parseInt(text);
    }

    static int parseAsciiWithOuterWhitespace(String text) {
        Objects.requireNonNull(text, "text");
        return parseAsciiStrict(text.strip());
    }

    static String errorName(Runnable call) {
        try {
            call.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println("parsePlus=" + Integer.parseInt("+42"));
        System.out.println("parseFullLength=" + Integer.parseInt("123"));
        System.out.println("strictPlus=" + parseAsciiStrict("+42"));
        System.out.println("outerStrictError="
                + errorName(() -> parseAsciiStrict(" 42 ")));
        System.out.println("outerAccepted=" + parseAsciiWithOuterWhitespace(" 42 "));
        System.out.println("outerTabsAccepted="
                + parseAsciiWithOuterWhitespace("\t-42\n"));
        System.out.println("internalWhitespaceError="
                + errorName(() -> parseAsciiWithOuterWhitespace("4 2")));
        System.out.println("newlineInsideError="
                + errorName(() -> parseAsciiWithOuterWhitespace("4\n2")));

        String emSpaces = "\u200342\u2003";
        System.out.println("unicodeStripAccepted="
                + parseAsciiWithOuterWhitespace(emSpaces));
        System.out.println("unicodeTrimUnchanged="
                + emSpaces.trim().equals(emSpaces));

        String nbsp = "\u00A042\u00A0";
        System.out.println("nbspStripUnchanged="
                + nbsp.strip().equals(nbsp));
        System.out.println("nbspRejected="
                + errorName(() -> parseAsciiWithOuterWhitespace(nbsp)));

        System.out.println("parseUnicodeDigits="
                + Integer.parseInt("１２３"));
        System.out.println("asciiUnicodeDigitsError="
                + errorName(() -> parseAsciiStrict("１２３")));
        System.out.println("unicodeDigitsWithStrip="
                + Integer.parseInt(" \u2003１２３\u2003 ".strip()));

        System.out.println("intOverflowError="
                + errorName(() -> parseAsciiStrict("2147483648")));
        System.out.println("longMax="
                + Long.parseLong("9223372036854775807"));
        System.out.println("longOverflowError="
                + errorName(() -> Long.parseLong("9223372036854775808")));
        System.out.println("emptyError="
                + errorName(() -> parseAsciiStrict("")));
        System.out.println("spacesOnlyError="
                + errorName(() -> parseAsciiWithOuterWhitespace(" \t ")));
        System.out.println("plusOnlyError="
                + errorName(() -> parseAsciiStrict("+")));
        System.out.println("nullError="
                + errorName(() -> parseAsciiStrict(null)));
        System.out.println("underscoreError="
                + errorName(() -> parseAsciiStrict("1_000")));
        System.out.println("prefixError="
                + errorName(() -> parseAsciiStrict("0x10")));

        String whole = "123abc";
        ParsePosition pos = new ParsePosition(0);
        Number parsed = NumberFormat.getIntegerInstance(Locale.US)
                .parse(whole, pos);
        System.out.println("localeParsedPrefix=" + parsed);
        System.out.println("localeConsumed=" + pos.getIndex());
        System.out.println("localeFullConsumed="
                + (pos.getIndex() == whole.length()));
        System.out.println("leadingZeroValue=" + parseAsciiStrict("0007"));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 CompleteIntegerInputDemo.java
java CompleteIntegerInputDemo
```

Exact verified stdout output:

```text
parsePlus=42
parseFullLength=123
strictPlus=42
outerStrictError=IllegalArgumentException
outerAccepted=42
outerTabsAccepted=-42
internalWhitespaceError=IllegalArgumentException
newlineInsideError=IllegalArgumentException
unicodeStripAccepted=42
unicodeTrimUnchanged=true
nbspStripUnchanged=true
nbspRejected=IllegalArgumentException
parseUnicodeDigits=123
asciiUnicodeDigitsError=IllegalArgumentException
unicodeDigitsWithStrip=123
intOverflowError=NumberFormatException
longMax=9223372036854775807
longOverflowError=NumberFormatException
emptyError=IllegalArgumentException
spacesOnlyError=IllegalArgumentException
plusOnlyError=IllegalArgumentException
nullError=NullPointerException
underscoreError=IllegalArgumentException
prefixError=IllegalArgumentException
localeParsedPrefix=123
localeConsumed=3
localeFullConsumed=false
leadingZeroValue=7
```

Groups of results illustrated:

- `strictPlus`, `outerStrictError`, `outerAccepted`, and `outerTabsAccepted`: establish the STRICT or OUTER-STRIP policy explicitly.
- `internalWhitespaceError`, `newlineInsideError`: stripping **outer** whitespace does not delete **internal** characters.
- `unicodeStripAccepted` vs. `unicodeTrimUnchanged`: `strip` removes boundary EM SPACE, whereas `trim` does not.
- `nbspStripUnchanged`, `nbspRejected`: NBSP is not removed by `strip`, so it does not become valid numeric input under this policy.
- `parseUnicodeDigits=123` vs. `asciiUnicodeDigitsError`: `Integer.parseInt` accepts full-width digits, while regex `[0-9]` rejects them.
- `intOverflowError`, `longOverflowError`: digit syntax can be valid while the value exceeds the **target type range**.
- `emptyError`, `spacesOnlyError`, `plusOnlyError`, `nullError`: empty, sign-only, whitespace-only, and `null` inputs must be handled distinctly.
- `localeParsedPrefix=123`, `localeConsumed=3`, `localeFullConsumed=false`: the locale-based parser reads only a **prefix** of `"123abc"`; checking the consumed position is mandatory if policy requires the full string.
- `leadingZeroValue=7`: integer parsing succeeds yet **does not preserve the string's leading zeros**.

The program's `errorName` helper intentionally catches `RuntimeException` to **print exception names for the demo**, not as a production error-handling design pattern. In real applications, catch exceptions at exact levels such as `NumberFormatException` or custom validator exceptions, rather than silently lumping all runtime failures into "invalid input."

## 12. Separating syntax errors, range errors, and business errors

In a strict parser, distinguish at least three levels:

1. **Syntax**: stray characters, policy-violating whitespace, invalid signs, empty digits. E.g. `"4 2"`, `"0x10"` (if decimal-only).
2. **Type range**: valid digits yet outside signed int/long. E.g. `"2147483648"` with `Integer.parseInt`.
3. **Business constraints**: a successfully parsed `int` that violates rules. E.g. age 200, negative quantity, file size exceeding quota.

In the sample code, `parseAsciiStrict` throws `IllegalArgumentException` for **regex syntax** errors, while `Integer.parseInt` can throw `NumberFormatException` if **out of range**. Since `NumberFormatException` is a subclass of `IllegalArgumentException`, callers catching generic `IllegalArgumentException` lose the distinction between the two error sources unless another convention is used.

A cleaner architecture for a public API is returning a result type with an error code or throwing documented exceptions. For example:

```text
ParseResult:
- OK(value)
- MISSING
- INVALID_SYNTAX
- OUT_OF_RANGE
- DOMAIN_VIOLATION
```

This is a **result model**, not a built-in JDK API. It can be implemented with an enum + record/sealed interface or application exception classes if distinct errors must be separated. Never send internal details such as stack traces or sensitive raw input directly to public logs.

## 13. `null`, empty strings, and missing-data policies

Do not equate these situations:

| Data | Suggested classification |
| --- | --- |
| `null` | Missing input or non-null contract violation |
| `""` | String present but empty |
| `" "` | Whitespace-only (policy-dependent) |
| `"0"` | Valid zero |
| `"-0"` | Signed int parser returns 0, different string representation |
| `"+" ` | Sign present but no digits |
| `"0000"` | Valid zero if leading zeros are allowed |

`Objects.requireNonNull` can be used when the API requires non-null input; then **`NullPointerException`** signals a contract violation. If `null` represents valid missing form/API data, check for it and return `MISSING` instead of letting another method accidentally throw NPE.

`String.isBlank()` is helpful for detecting empty/whitespace-only strings per `Character.isWhitespace`, yet **`"0"` is not blank** and **NBSP is not considered whitespace by `isWhitespace`**. Do not replace `isBlank` with `parseInt` or vice versa: they answer two different questions.

## 14. Do not strip grouping separators, dots, or internal characters automatically

Strings like `"1,000"`, `"1.000"`, or `"1 000"` mean very different things across locales: a comma may be a thousands separator or a decimal separator; likewise for a period. If data comes from a machine-readable protocol with an ASCII decimal schema, the safe approach is to **reject** all unpermitted separators.

If a UI needs locale-aware parsing, select a **specific `Locale`** and use an appropriate formatting parser, then verify the parser consumed **the entire input**, check the result type/range, and ensure decimal/grouping rules match intent.

Dangerous example:

```java
// Do not strip grouping characters blindly:
String raw = "1,5";
// raw.replace(",", "") becomes "15" even though the user may have meant 1.5.
```

Running `replaceAll("[ ,._]", "")` across all characters can corrupt numeric meaning, bypass schema checks, or mask invalid data. Normalize **only the exact characters** explicitly permitted by the contract.

## 15. Length limits and safety with untrusted input

A string can contain millions of digits even when the target is only `int`. The parser will report out-of-range, yet reading/scanning still incurs cost. For public endpoints or untrusted data, you should:

- Set a **byte/character limit before reading or accepting huge payloads** per protocol and transport layer.
- After receiving a `String`, check `null`, total length, and whitespace policy before regex/parsing.
- Set a size limit on the **normalized portion** if the schema specifies maximum digit count. Do not confuse digit count with range validity: a string with many leading zeros can still parse into a small number.
- Avoid overly complex regexes prone to **catastrophic backtracking**. The pattern `[+-]?[0-9]+` is simple and has no nested repetition groups.
- Validate the parsed value against the business domain (sign, count bounds, units, quota).
- Never log untrusted input verbatim if it may contain sensitive info or control characters that corrupt logs.

If the schema requires strictly `n` digits, or forbids leading zeros, express that in a separate validator. Do not assume `Integer.parseInt` enforces such formatting rules.

## 16. Common implementation mistakes

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| Assuming "read 123" means `"123abc"` is valid | Prefix parser may ignore trailing characters | Verify `ParsePosition.getIndex() == input.length()` or use a full-string parser |
| Calling `strip()` by default in every API | Hides whitespace errors in strict protocols | Pick an explicit policy: STRICT or OUTER-STRIP |
| Thinking `strip()` removes all whitespace | NBSP can still remain | Check code points and Unicode policy |
| Using `trim()` when expecting Unicode whitespace support | Boundary EM SPACE can remain | Use `strip()` when matching contract |
| Replacing all `" "` in the string | Turns `"4 2"` into `"42"` | Strip only outer whitespace when allowed |
| Calling `Matcher.find()` instead of `matches()` | A partial substring match passes | Use `matches()` to validate the whole string |
| Using `parseInt` as an ASCII-only validator | Unicode digits can be accepted | ASCII regex `[0-9]` or code-point check |
| Regex only, then accepting `"2147483648"` as `int` | Valid syntax yet exceeds 32-bit range | Call `Integer.parseInt` to enforce range |
| Treating `null`, `""`, `"0"` identically | Loses distinction between missing data and valid 0 | Design parse result with error codes |
| Using the machine default locale to parse protocols | Results vary by environment | Fix locale per schema or use ASCII decimal parser |
| Checking only the numeric field inside a record | Record may still have stray characters or invalid fields | Validate full record structure and field positions |
| Allowing arbitrarily long digit strings | Resource exhaustion or quota breach | Enforce input limits early |
| Parsing identifiers into integers | Loses leading zeros and formatting chars | Keep `String` for identifiers |

## 17. Minimal test suite for the two policies

| Input | STRICT ASCII | OUTER-STRIP ASCII | Notes |
| --- | --- | --- | --- |
| `"42"` | 42 | 42 | Simple value |
| `"+42"` | 42 | 42 | If `+` sign is allowed |
| `"-42"` | -42 | -42 | If negative numbers are allowed |
| `" 42 "` | Error | 42 | Distinguishes policies |
| `"\t42\n"` | Error | 42 | Outer tab/newline |
| `"4 2"` | Error | Error | Internal whitespace |
| `"\u200342\u2003"` | Error | 42 | EM SPACE removed by `strip` |
| `"\u00A042\u00A0"` | Error | Error | NBSP not removed by `strip` |
| `"１２３"` | Error | Error | ASCII-only rejects full-width digits |
| `"0007"` | 7 | 7 | Unless leading zeros are forbidden |
| `"2147483647"` | 2147483647 | 2147483647 | Upper int bound |
| `"2147483648"` | Range error | Range error | Exceeds upper bound |
| `"1_000"` | Error | Error | `_` does not belong in numeric strings |
| `"0x10"` | Error | Error | Hex prefix outside decimal syntax |
| `""`, `" "`, `null` | Error/missing | Error/missing | Must never be treated as 0 |

For `long`, also test `Long.MIN_VALUE`, `Long.MAX_VALUE`, and two strings immediately outside the range; for unsigned, test `2^32-1` or `2^64-1` depending on the API. If policy permits locale-specific grouping, add tests for valid/invalid grouping and decimal points under the **pinned locale**, while also verifying full consumption.

## 18. Self-check questions

1. **Does `Integer.parseInt("123abc")` return 123 or fail?** Throws `NumberFormatException` because the input string is not a valid integer in full.
2. **Does `Integer.parseInt(" 42 ")` automatically strip whitespace?** No. Call `strip()` beforehand if the contract permits.
3. **Do `" 42 ".strip()` and `"4 2".strip()` give the same result?** No; `strip` removes only leading/trailing whitespace, not internal whitespace.
4. **How do `trim()` and `strip()` differ on EM SPACE U+2003?** `trim` does not remove it, `strip` removes it at the edges.
5. **Does `strip()` remove NO-BREAK SPACE U+00A0?** No, because it is not recognized by `Character.isWhitespace`.
6. **Why can `Integer.parseInt("１２３")` succeed?** Java uses Unicode digit recognition rules; if ASCII-only is needed, validate separately.
7. **Is regex `[+-]?[0-9]+` enough to guarantee the result fits in `int`?** No; `Integer.parseInt` is needed to check type limits.
8. **If `NumberFormat` reads 123 from `"123abc"`, does that mean the whole string is valid?** No; you must check the parser's consumed position.
9. **Does `parseInt(CharSequence, 0, 3, 10)` inspect anything after index 3?** No; it parses only the specified slice.
10. **Should `"0007"` be converted to the number 7 if it is an identifier?** Usually no; identifiers must preserve original formatting, so they are usually kept as strings.

**Conclusion:** safe integer parsing is a combination of **full-string syntax**, **whitespace rules**, **allowed character sets**, **numeric range limits**, and **business constraints**. Java's `parseInt`/`parseLong` consume the entire accepted integer string yet do not auto-`strip`; locale-based APIs can parse only a prefix if you do not check the stop position. Choose STRICT or OUTER-STRIP deliberately, validate ASCII/Unicode per specification, and test thoroughly for trailing characters, whitespace, null, Unicode, and overflow.