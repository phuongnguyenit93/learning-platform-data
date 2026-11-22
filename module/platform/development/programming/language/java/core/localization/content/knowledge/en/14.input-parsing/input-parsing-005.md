# Grouping Separators, Whitespace, and Unicode Digits When Parsing Input

## 1. Why Can a Number That “Looks Right” Still Be Parsed Wrong?

In a multilingual Java application, form input does not consist only of ASCII digits `0–9` and periods. Users may enter numbers such as:

| String the User Sees | Illustrative Locale/Context | Notable Characters |
| --- | --- | --- |
| `1,234.50` | `en-US` | Comma `,` thousands grouping, dot `.` decimal |
| `1.234,50` | `de-DE` | Dot thousands grouping, comma decimal |
| `1 234,50` | `fr-FR`, common CLDR data | Grouping separator **NNBSP** `U+202F`, not an ASCII space |
| `1 234,50` | Some data/input methods using NBSP | Grouping separator **NBSP** `U+00A0` |
| `١٬٢٣٤٫٥٠` | Arabic-Indic numeral data | Arabic-Indic digits `U+0660–U+0669`, grouping `U+066C`, decimal `U+066B` |
| `１２３４．５０` | Fullwidth digits | Do not assume every parser accepts fullwidth punctuation too |

Two strings that look identical can contain **different Unicode code points**. When parsing numbers, the parser does not just look at visual glyph shapes: it applies rules for grouping separators, decimal separators, digits, and conventions from `Locale`/`DecimalFormatSymbols`. A small difference—such as replacing an NNBSP grouping separator with an ordinary space—can cause the parser to stop partway through.

**Lesson goal:** parse localized numbers in Java 17+ in the right context, distinguish different kinds of whitespace and Unicode digits, verify that parsing **consumed the entire input**, and avoid confusing a successful parse with strict data structure validation.

## 2. Distinguishing the Numeric Value from Its String Representation

The value `1234.50` is a decimal number; `"1,234.50"` and `"1.234,50"` are two **textual representations** that can express that value. If an application receives `"1.234,50"` and calls:

~~~java
new BigDecimal("1.234,50")
~~~

the code fails because `BigDecimal(String)` **is not a locale-aware number parser**. That constructor accepts a canonical decimal syntax and does not understand localized grouping or decimal commas.

For localized user input, you should normally use:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
Number parsed = format.parse(input);
~~~

This is a **code snippet inside a method**, requiring imports for `java.text.NumberFormat` and `java.util.Locale`, existing `locale`/`input` variables, and handling for `ParseException`. However, this simple call alone is not enough to validate that the **entire** input string is valid.

### Three Steps That Must Not Be Mixed Together

1. **Determine the source convention:** which locale is the user entering data in, such as `de-DE` or `en-US`?
2. **Convert text into a number:** which grouping separators, decimal separators, signs, and digits does the parser understand?
3. **Validate business rules:** is grouping syntax strict, are there trailing characters, is the value in the allowed range, and are precision/scale valid?

Succeeding at step 2 **does not mean** you can skip step 3.

## 3. What Do `Locale` and `DecimalFormatSymbols` Control?

`java.text.NumberFormat.getNumberInstance(locale)` returns a formatter/parser configured with the corresponding numeric conventions. In standard JDKs, this is typically a `DecimalFormat`. `DecimalFormatSymbols` holds the concrete symbols for a format:

| API | Role |
| --- | --- |
| `DecimalFormatSymbols.getInstance(locale)` | Retrieve the numeric symbols for the locale |
| `getGroupingSeparator()` | Character used as the thousands grouping separator |
| `getDecimalSeparator()` | Decimal separator character |
| `getZeroDigit()` | Default zero digit character of the numeral system |
| `getMinusSign()` | Minus sign symbol |
| `NumberFormat.getNumberInstance(locale)` | Locale-aware number formatter/parser |
| `NumberFormat.parse(...)` | Parse a string into a `Number` |
| `DecimalFormat.setParseBigDecimal(true)` | Instruct `DecimalFormat` to return `BigDecimal` when appropriate instead of a typical `Double` |

Explicit example:

~~~java
Locale locale = Locale.FRANCE;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);

char grouping = symbols.getGroupingSeparator();
char decimal = symbols.getDecimalSeparator();
~~~

This is a **code snippet inside a method**, requiring imports for `java.util.Locale` and `java.text.DecimalFormatSymbols`.

With the CLDR data commonly shipped in modern JDKs, `fr-FR` typically uses `U+202F` as the grouping separator and `,` as the decimal separator. However, JDKs, providers, and locale data can vary. **Do not assume from a locale name that its characters are always fixed**; when you need certainty, inspect the actual `DecimalFormatSymbols` and test in your deployment environment.

### Look at Code Points, Not Just Visual Appearance

When debugging, instead of printing an ambiguous space, print `U+XXXX`:

~~~java
System.out.printf(
        Locale.ROOT,
        "Grouping = U+%04X%n",
        (int) symbols.getGroupingSeparator()
);
~~~

This is a **code snippet inside a method**, assuming `symbols` is declared and `java.util.Locale` is imported. If it prints `U+202F`, that character is NNBSP, not ASCII space `U+0020`.

## 4. ASCII Space, NBSP, and NNBSP Are Not Equivalent

The three characters below often look like “whitespace,” but they have different Unicode code points and properties:

| Name | Code Point | English Name | Typical Context |
| --- | --- | --- | --- |
| Regular space | `U+0020` | SPACE | Typed from the Spacebar |
| Non-breaking space | `U+00A0` | NO-BREAK SPACE (NBSP) | Text that should not wrap, localized numbers/resources |
| Narrow non-breaking space | `U+202F` | NARROW NO-BREAK SPACE (NNBSP) | Thousands grouping separator in some locales, notably `fr-FR` in modern CLDR |

This matters when users **copy and paste** a number from web pages, PDFs, spreadsheets, or emails. For example, `1 234,50` and `1 234,50` may differ only in the character between `1` and `2`, yet the parser will handle them differently.

### Do Not Assume `trim()`/`strip()` Removes All Unicode Spaces

In Java 17:

- `String.trim()` strips a traditional range of leading/trailing characters based on character code values.
- `String.strip()` uses `Character.isWhitespace`.
- `Character.isWhitespace` **does not treat NBSP `U+00A0` or NNBSP `U+202F` as whitespace**.
- `Character.isSpaceChar` **does** recognize both NBSP and NNBSP.

Standalone runnable example—save as `SpaceCodePointDemo.java`:

~~~java
public class SpaceCodePointDemo {
    public static void main(String[] args) {
        int space = 0x0020;
        int nbsp = 0x00A0;
        int narrowNbsp = 0x202F;

        System.out.println("SPACE whitespace: "
                + Character.isWhitespace(space));
        System.out.println("NBSP whitespace: "
                + Character.isWhitespace(nbsp));
        System.out.println("NBSP space-char: "
                + Character.isSpaceChar(nbsp));
        System.out.println("NNBSP whitespace: "
                + Character.isWhitespace(narrowNbsp));
        System.out.println("NNBSP space-char: "
                + Character.isSpaceChar(narrowNbsp));

        String wrapped = "\u00A0123\u202F";
        System.out.println("Original length: " + wrapped.length());
        System.out.println("After strip length: "
                + wrapped.strip().length());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 SpaceCodePointDemo.java
java SpaceCodePointDemo
~~~

Output:

~~~text
SPACE whitespace: true
NBSP whitespace: false
NBSP space-char: true
NNBSP whitespace: false
NNBSP space-char: true
Original length: 5
After strip length: 5
~~~

Thus `strip()` **does not remove** leading or trailing NBSP/NNBSP. However, that does not mean you should unconditionally delete **every** `Character.isSpaceChar`: inside a number, NBSP/NNBSP can be a **valid grouping separator**. Stripping it before parsing can discard structural input information.

**The right approach:** distinguish whether those characters are grouping separators inside a number, extra surrounding whitespace, or invalid data. Design explicit handling rules for each position.

## 5. Complete Example: `fr-FR` and Unicode Grouping Separators

Create `FrenchGroupingDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class FrenchGroupingDemo {
    public static void main(String[] args) {
        Locale locale = Locale.FRANCE;

        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        System.out.printf(
                Locale.ROOT,
                "Grouping separator: U+%04X%n",
                (int) symbols.getGroupingSeparator()
        );
        System.out.printf(
                Locale.ROOT,
                "Decimal separator: U+%04X%n",
                (int) symbols.getDecimalSeparator()
        );

        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1234.50");
        String formatted = format.format(original);

        System.out.println("Formatted: " + formatted);
        System.out.print("Code points: ");
        formatted.codePoints().forEach(cp ->
                System.out.printf(Locale.ROOT, "U+%04X ", cp)
        );
        System.out.println();

        ParsePosition end = new ParsePosition(0);
        Number parsed = format.parse(formatted, end);

        System.out.println("Parsed: " + parsed);
        System.out.println("Fully consumed: "
                + (parsed != null && end.getIndex() == formatted.length()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FrenchGroupingDemo.java
java FrenchGroupingDemo
~~~

On a JDK using CLDR data with grouping separator `U+202F`, illustrative output is:

~~~text
Grouping separator: U+202F
Decimal separator: U+002C
Formatted: 1 234,50
Code points: U+0031 U+202F U+0032 U+0033 U+0034 U+002C U+0035 U+0030
Parsed: 1234.50
Fully consumed: true
~~~

If the provider uses a different grouping character, the `Grouping separator`, `Formatted`, and `Code points` lines may differ. Even so, because the program obtains symbols **from the same locale/provider**, formats, and parses using that formatter, the example verifies behavior appropriate to the runtime environment.

**Key takeaway:** `DecimalFormatSymbols.getGroupingSeparator()` reveals the actual configured character instead of guessing from a space-like glyph on screen.

### Why Not Simply Write `replace(" ", "")`?

In `"1 234,50"`, the grouping character is NNBSP, **not** `" "`. `replace(" ", "")` does not touch that character. Conversely, deleting all Unicode spaces indiscriminately can turn an input with **misplaced grouping separators** into a seemingly valid digit string, erasing the signal needed for validation.

If a product has a policy allowing multiple space forms in numeric input, **normalization** must be restricted to valid positions and followed by locale-aware structure validation, rather than “stripping everything just to make the parser succeed.”

## 6. `NumberFormat.parse` Can Read Only a Prefix

A major risk is that `NumberFormat.parse(String)` or `parse(String, ParsePosition)` **does not check full-string syntax as required by a form**. A parser can accept the leading portion and stop.

Example with US locale:

~~~java
NumberFormat parser =
        NumberFormat.getNumberInstance(Locale.US);
Number number = parser.parse("1,234.50abc");
~~~

This is a **code snippet inside a method**, requiring imports for `java.text.NumberFormat` and `java.util.Locale`. Implementations can return `1234.5` even though `abc` remains. If you only check `number != null`, the system can accept invalid input.

### Checking Ending Position with `ParsePosition`

Create `PrefixParsingDemo.java`:

~~~java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class PrefixParsingDemo {
    public static void main(String[] args) {
        String input = "1,234.50abc";

        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);

        System.out.println("Parsed: " + parsed);
        System.out.println("Consumed: " + position.getIndex());
        System.out.println("Input length: " + input.length());
        System.out.println("Valid full input: "
                + (parsed != null
                   && position.getIndex() == input.length()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PrefixParsingDemo.java
java PrefixParsingDemo
~~~

With standard JDKs, the output is:

~~~text
Parsed: 1234.50
Consumed: 8
Input length: 11
Valid full input: false
~~~

Explanation: the 8-character `"1,234.50"` portion was parsed; `"abc"` was not consumed. `ParsePosition.getIndex()` reports the ending position (in UTF-16 character indices), while `getErrorIndex()` can report an error position when parsing fails.

A reliable check pattern for forms:

~~~java
ParsePosition position = new ParsePosition(0);
Number result = parser.parse(input, position);

if (result == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid localized number");
}
~~~

This is a **code snippet** assuming `parser` and `input` already exist. In production applications, also cap input length and enforce policies for signs, zero, range, and precision.

**Important:** checking full consumption only catches trailing characters. It **does not** prove that grouping separators are positioned strictly or that input satisfies all business rules.

## 7. Parsers Can Accept Misplaced Grouping Separators

`DecimalFormat` is built to parse numbers across varied user inputs, and many implementations do not strictly enforce three-digit grouping placement. Non-standard inputs can still parse into a number.

The example below illustrates the difference between **parsing** and **validation** in standard JDKs:

~~~text
Input:       12,34,567.89
Meaning:     grouping does not follow standard en-US style
Parsed:      1234567.89
Full input:  true
Strict UI:   must reject if product requires three-digit grouping
~~~

Create `GroupingValidationDemo.java`:

~~~java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class GroupingValidationDemo {
    public static void main(String[] args) {
        String input = "12,34,567.89";

        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);

        System.out.println("Parsed: " + parsed);
        System.out.println("Entire input consumed: "
                + (parsed != null
                   && position.getIndex() == input.length()));

        boolean strictEnUS = input.matches(
                "(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
              + "(?:\\.[0-9]{1,2})?"
        );
        System.out.println("Strict en-US shape: " + strictEnUS);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GroupingValidationDemo.java
java GroupingValidationDemo
~~~

Output with common JDK parsers:

~~~text
Parsed: 1234567.89
Entire input consumed: true
Strict en-US shape: false
~~~

**Why can this regex not be used for every locale?**

- It was written **specifically for an en-US form requirement**: non-negative numbers, ASCII `0–9` only, comma `,` three-digit grouping, `.` decimal separator, at most two fractional digits, and no exponent.
- It accepts both ungrouped `1234567.89` and standard grouped `1,234,567.89`.
- It intentionally rejects `12,34,567.89` even though the parser can read it as a number.
- It is **not** a generic `Locale` regex: regions differ in grouping rules, Unicode signs, negative parts, non-ASCII digits, or allowances for more than two fractional digits.
- Do not silently normalize `12,34,567.89` into `1234567.89` without warning the user if the product requires strict grouping.

In sensitive domains (finance, tax, accounting), define an explicit **input contract**, validate structure before or alongside parsing, check range/scale, and log errors under privacy policies. Never treat `setGroupingUsed(true)` as a “strict grouping” mode; it only controls whether grouping is used, **without guaranteeing strict validation of every separator position**.

## 8. Unicode Digits: Not Only `0–9`

In Java, a digit can belong to many writing systems:

| Numeral System | Illustration | Common Unicode Range |
| --- | --- | --- |
| Latin/ASCII | `0123456789` | `U+0030–U+0039` |
| Arabic-Indic | `٠١٢٣٤٥٦٧٨٩` | `U+0660–U+0669` |
| Extended Arabic-Indic | `۰۱۲۳۴۵۶۷۸۹` | `U+06F0–U+06F9` |
| Devanagari | `०१२३४५६७८९` | `U+0966–U+096F` |
| Fullwidth | `０１２３４５６７８９` | `U+FF10–U+FF19` |

`Character.digit(int codePoint, int radix)` can determine the **numeric value** of many Unicode digit characters. For example:

~~~java
System.out.println(Character.digit('3', 10));  // 3
System.out.println(Character.digit('٣', 10));  // 3
System.out.println(Character.digit('३', 10));  // 3
System.out.println(Character.digit('３', 10)); // 3
~~~

This is a **code snippet inside a method**. Here `Character.digit` illustrates the *arithmetic value* of a character; it **does not** prove that `NumberFormat` for **every locale** will accept every digit script or its accompanying decimal/grouping separators.

A locale such as `ar-EG` may use Arabic-Indic digits and separators specific to that numeral system, whereas an `en-US` parser may reject those very characters. Parser behavior also depends on `DecimalFormatSymbols`, the provider, and input syntax.

### Do Not Confuse Numbers That “Look Alike” with Identical Bytes/Strings

`"123"` and `"١٢٣"` carry different code points. Even if both denote one hundred twenty-three in a given context, `String.equals` between them returns `false`.

Furthermore, a string can mix multiple numeral systems, pair one locale's grouping separator with another's decimal separator, or contain confusable characters. When a system validates account codes, identifiers, access keys, or protocol fields, **do not automatically allow arbitrary Unicode digits just because they have numeric values 0–9**. Such fields usually require explicit ASCII syntax rather than a UI number parser.

## 9. Runnable Example: Arabic-Indic Digits with `ar-EG`

Create `ArabicDigitsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class ArabicDigitsDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("ar-EG");

        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        System.out.printf(Locale.ROOT,
                "Zero digit: U+%04X%n", (int) symbols.getZeroDigit());
        System.out.printf(Locale.ROOT,
                "Grouping: U+%04X%n",
                (int) symbols.getGroupingSeparator());
        System.out.printf(Locale.ROOT,
                "Decimal: U+%04X%n",
                (int) symbols.getDecimalSeparator());

        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setParseBigDecimal(true);

        BigDecimal source = new BigDecimal("1234.5");
        String shown = format.format(source);
        System.out.println("Formatted: " + shown);

        ParsePosition position = new ParsePosition(0);
        Number read = format.parse(shown, position);
        System.out.println("Parsed: " + read);
        System.out.println("Full input: "
                + (read != null
                  && position.getIndex() == shown.length()));
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 ArabicDigitsDemo.java
java ArabicDigitsDemo
~~~

With a CLDR provider using Arabic-Indic digits for `ar-EG`, illustrative output is:

~~~text
Zero digit: U+0660
Grouping: U+066C
Decimal: U+066B
Formatted: ١٬٢٣٤٫٥
Parsed: 1234.5
Full input: true
~~~

This output depends on locale data; other datasets may choose a different numeral system or support Unicode locale extensions such as `u-nu-latn`. The point is that **the formatter and parser must share a consistent locale/numeral-system policy**, rather than swapping characters by eye.

### When Is a Unicode Locale Extension Needed?

A tag like `ar-EG-u-nu-latn` expresses a preference for Latin digits within an Arabic (Egypt) locale context. `Locale` can store the `nu` keyword, but the specific API/provider must honor it to affect number formatting. If your application mandates Latin digits, test the actual `NumberFormat` or configure an explicit display policy; do **not** assume every library honors every extension.

## 10. Safe Unicode Input Normalization Strategies

Some users paste strings containing NBSP/NNBSP from documents; others type an ASCII space in place of a locale's space grouping separator. An application may choose **strict input** or **lenient input**, as long as it specifies the rules clearly.

### Option A — Strict Locale Input

- Determine the user's input locale.
- Obtain the exact grouping/decimal separators for that locale.
- Accept one documented grouping form and one allowed digit set.
- Validate the entire string, minus-sign and separator positions, and fractional digit count.
- Parse and verify value range and precision/scale.
- Display a clear error if visually similar but non-compliant characters were entered.

Suitable for monetary amounts or regulated data requiring strict control.

### Option B — Lenient Input with Controlled Normalization

A product might let users type a regular space instead of NNBSP, subject to strict boundaries:

1. Replace only **permitted characters** at **grouping separator positions**, never all whitespace everywhere.
2. Before or after replacement, validate group sizes per locale and enforce rules for negative signs/decimals.
3. Never replace a decimal separator by “guessing” if a character can act as a grouping separator in one locale and a decimal separator in another.
4. Parse using the determined locale and confirm full input consumption.
5. If auditability is required, consider retaining the raw input under privacy controls to explain error sources.

**Do not do the following across all locales:**

~~~java
String guessed = input
        .replace(" ", "")
        .replace(",", ".");
~~~

This is a **code snippet with an `input` variable** illustrating an error-prone approach. For `de-DE`, `"1.234,50"` with commas simply replaced by dots becomes `"1.234.50"`, which is syntactically invalid as a standard number. For `en-US`, `"1,234.50"` also breaks when commas become dots. For `fr-FR`, deleting ASCII spaces fails to remove NNBSP.

### Why Be Cautious with Unicode Normalization?

`java.text.Normalizer` can apply NFC/NFKC, but **do not call `Normalizer.normalize(input, Form.NFKC)` on every numeric input and assume it is clean**. NFKC can convert certain compatibility characters (such as fullwidth digits), which **does not** automatically handle every locale's grouping separators, decimal separators, and safety rules.

If you adopt NFKC normalization in a product, document the rationale, the allowed character set before and after normalization, how ambiguities are prevented, and test mixed-script cases. Never use normalization as a substitute for validation.

## 11. Accurate Parsing Still Requires Range and Precision Checks

A syntactically valid number can still be **invalid for the business domain**, such as a negative amount in a positive-only form or a number with too many fractional digits.

Use `BigDecimal` when exact decimal values are required:

~~~java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);

ParsePosition position = new ParsePosition(0);
Number number = parser.parse(input, position);

if (number == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid number");
}
BigDecimal amount = (BigDecimal) number;

if (amount.signum() < 0) {
    throw new IllegalArgumentException("Negative amount not allowed");
}
if (amount.scale() > 2) {
    throw new IllegalArgumentException("Too many decimal places");
}
~~~

This is a **code snippet inside a method**, requiring imports for `java.math.BigDecimal`, `java.text.DecimalFormat`, `java.text.NumberFormat`, `java.text.ParsePosition`, and `java.util.Locale`. `input` is the string to parse. Checking `scale()` is an illustrative policy choice; if you want to accept inputs like `1.230` in a field capped at two fractional digits, decide how to handle trailing zeros before enforcing the limit. `scale` is not the sole criterion for validating money.

**Do not infer that `setParseBigDecimal(true)` creates a strict parser.** It primarily affects return type and precision. Input syntax rules still must be enforced separately.

### Parsing and Formatting Are Not Strict Inverses

If a formatter rounds `1234.567` to `1,234.57`, parsing it back produces `1234.57`, **not** `1234.567`. When normalizing Unicode or accepting varied grouping styles, different input strings can also parse into the same value.

Therefore, never use formatted strings as your primary stored representation. Store numbers in typed form (such as `BigDecimal`), and reserve localized strings for display and user input.

## 12. Cases Where Locale-Aware Number Parsers Should Not Be Used

**Numbers used for service-to-service communication** (JSON numbers, canonical configs, machine data) usually require a deterministic syntax **independent** of who is viewing them. For example, JSON numbers use a dot as the decimal separator and never use locale grouping separators.

**Identifiers** such as account numbers, postal codes, phone numbers, and order codes may contain digits and separators, yet they are **not arithmetic quantities**. Never pass them through `NumberFormat`: you can lose leading zeros, alter character structure, or accept invalid contract inputs.

If the data is an ID or security-sensitive token, you typically need **strings with dedicated validation**, intentionally restricted to ASCII `[0-9]` if appropriate; do not conflate them with localized numeric formatting.

## 13. Common Mistakes Comparison Table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `" "`, NBSP, and NNBSP are the same character | Fails to parse numbers pasted from web/PDF | Inspect code points and use `DecimalFormatSymbols` |
| Assuming `strip()` removes all whitespace | NBSP/NNBSP remain untouched | Handle specific character classes per policy |
| Deleting all whitespace before parsing | Can turn misplaced grouping into valid-looking input | Validate group positions before normalizing |
| Calling `new BigDecimal("1.234,50")` | Fails because constructor is locale-unaware | Use a locale-aware parser and validate |
| Checking only `parse(...) != null` | May accept only the prefix of a bad string | Use `ParsePosition` and require full consumption |
| Assuming full consumption implies valid grouping | May accept `12,34,567.89` | Add strict validation per contract |
| Applying one ASCII regex to every locale | Rejects valid inputs in other locales | Design validation for each supported locale |
| Assuming `Character.digit` means every parser accepts all digits | Parser rejects digits or separators from another script | Test `NumberFormat` per locale/provider |
| Blindly replacing `,` with `.` on multi-locale input | Can flip decimal and grouping meanings | Identify source locale and parse by its rules |
| Skipping precision/range checks after parsing | Accepts oversized amounts or excess decimals | Use `BigDecimal` and enforce business checks |
| Using `NumberFormat` for IDs with leading zeros | Loses identifier structure | Keep the original string and validate against schema |
| Sharing a `DecimalFormat` across requests unsynchronized | State/config leakage across threads | Create per-request parsers or synchronize/copy safely |

`NumberFormat` and `DecimalFormat` are **not guaranteed thread-safe when shared without synchronization**. `Locale` is immutable, whereas formatters/parsers hold mutable state and can be reconfigured. In multi-user applications, pass `Locale` from the request context and create appropriate parser instances.

## 14. Testing Checklist and Exercises

### QA Checklist

1. For each supported locale, verify actual grouping separator, decimal separator, and zero digit using `DecimalFormatSymbols`.
2. Test strings with SPACE `U+0020`, NBSP `U+00A0`, and NNBSP `U+202F`; remember they differ.
3. Test ASCII digits, Arabic-Indic digits, and mixed-script inputs per product policy.
4. Test fully parsed strings versus prefix-only parses such as `"1,234.50abc"`.
5. Test irregular grouping such as `"12,34,567.89"`; do not rely on lenient defaults for business validation.
6. Test negative numbers, zero, very large values, many fractional digits, and overly long inputs.
7. Test on the exact JDK and locale provider used in production; `fr-FR` grouping and Unicode rules can vary across locale data versions.
8. Test precision with `BigDecimal`; do not let format-then-parse overwrite rounded source values.
9. Test multithreaded parser usage or lifecycle scope so mutable instances are not shared improperly.

### Self-Check Exercises

1. Write a program printing `DecimalFormatSymbols.getGroupingSeparator()` for `Locale.US`, `Locale.GERMANY`, and `Locale.FRANCE` in `U+XXXX` notation; why is visual inspection insufficient?
2. Given the NNBSP string `"1 234,50"`, why does `replace(" ", "")` fail to remove the grouping separator? Why should you still avoid deleting all Unicode spaces?
3. Use `ParsePosition` to parse `"1,234.50abc"` under `en-US`. Inspect `getIndex()` and explain why the full input cannot be accepted.
4. Run `GroupingValidationDemo` with `"12,34,567.89"`, `"1,234,567.89"`, and `"1234567.89"`. Which are valid under the article's regex, and which are accepted by the lenient parser?
5. For locale `ar-EG`, inspect the zero digit, grouping separator, decimal separator, and format of `1234.5`. Why can you not assume an `en-US` parser accepts the same input?
6. Explain the difference between `Character.isWhitespace(0x202F)` and `Character.isSpaceChar(0x202F)`. Does `String.strip()` remove this character from either end?
7. Design a parser for a localized monetary amount form allowing at most two fractional digits. Distinguish syntax validation, `BigDecimal`, valid range, and transaction currency.
8. Why should order code `"001234"` not be formatted or parsed with `NumberFormat`?

**Key takeaway:** grouping separators are not simply commas or spaces; they can be **NBSP `U+00A0`**, **NNBSP `U+202F`**, or script-specific characters. Unicode digits may carry the same numeric values as ASCII digits while having different code points and differing parser support. Always **identify the source locale, read the actual `DecimalFormatSymbols`, verify full string consumption, and validate syntax and business rules separately**. For machine interchange or identifiers, use schemas with explicit syntax rather than user-facing number formats.

### References

- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — locale-aware number formatting and parsing.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — grouping, parsing, patterns, and `setParseBigDecimal`.
- [Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html) — grouping separator, decimal separator, zero digit.
- [Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) — parsed position and parse error offset.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — `digit`, `isWhitespace`, `isSpaceChar`, and Unicode.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — `strip` and Unicode string operations.