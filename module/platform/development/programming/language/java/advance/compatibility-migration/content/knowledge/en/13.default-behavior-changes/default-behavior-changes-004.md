# Unicode, Character Classification, and Regular Expressions

When upgrading the JDK, many development teams focus on removed APIs, bytecode, and JVM configuration while overlooking a less obvious source of behavioral changes: **the Unicode data and character classification rules** used by the Java standard library. A regex that previously rejected a character may begin accepting it on a new JDK; a `Character.isLetter(...)` check may return a different result for a code point newly added or reclassified by Unicode; word splitting, normalization, or case-insensitive matching can also produce differences at data boundaries.

These changes do not necessarily cause compilation errors or throw exceptions at runtime. They can silently affect **validation, search, tokenization, user identifiers, log parsing, input security, and business outcomes**. Therefore, behavioral compatibility testing must include non-ASCII characters, combining marks, Unicode whitespace, and regular expression cases that rely on the JDK's Unicode data tables.

This lesson explains the Unicode model in Java, the differences among `char`, *code point*, and user-perceived characters; how `Character` classifies characters; how `java.util.regex.Pattern` interprets `\d`, `\w`, `\s`, and `\p{...}`; the impact of normalization; and steps to build regression tests when migrating JDKs.

## 1. What Is Unicode and Why Does the JDK Version Matter?

Unicode defines a code space for characters along with many associated properties: letters, digits, combining marks, punctuation, whitespace, text direction, scripts, and other processing rules. Each code value is called a **Unicode code point**, commonly written in the form `U+XXXX`.

Examples:

| Character | Code point | Notes |
|---|---|---|
| `A` | U+0041 | Uppercase Latin letter. |
| `á` | U+00E1 | Accented Latin letter encoded as a single code point. |
| `中` | U+4E2D | Chinese (Han) character. |
| `١` | U+0661 | Arabic-Indic digit one. |
| `😀` | U+1F600 | Emoji outside the Basic Multilingual Plane. |
| `◌́` | U+0301 | Combining acute accent; requires a base character to display as an accented letter. |

The JDK provides APIs such as `java.lang.Character`, `java.lang.String`, `java.text.Normalizer`, and `java.util.regex.Pattern`. These APIs can depend on the Unicode data bundled with the running Java version. When the JDK updates the Unicode version it supports, **the set of recognized characters and properties can change** even when source code has not changed.

This differs from an API change such as renaming a method. A call to `Character.isLetter(cp)` still exists and runs normally on both JDKs, yet the result for a specific code point can differ if Unicode metadata for that code point changed between the two versions.

### 1.1. Do Not Equate “Java Version” with “Unicode Version”

Java and Unicode have separate release schedules. Each JDK release integrates a particular Unicode version or adjusts related support. Therefore, when investigating a classification discrepancy, consult the documentation for **the exact JDK release and vendor** to identify the Unicode dataset it uses.

Do not assume that every Java bump changes all characters, or that a newer Java release always uses the latest Unicode standard published at the time. Focus on the code points and validation contracts that actually matter to the application.

### 1.2. Source Compatibility Does Not Guarantee Behavioral Compatibility

For example, suppose a service checks `Character.isLetter(cp)` and permits valid characters in an identifier. If a newer Unicode version adds a letter in a script not recognized by the older JDK, the same code may accept a broader set of inputs after upgrading the JDK.

This may be an accurate improvement according to the Unicode standard, yet still constitute a **business contract change** if the system previously specified the exact set of accepted characters. Regression tests must not merely verify that the program runs; they must verify which inputs are accepted and how outputs are normalized.

## 2. Distinguishing Code Points, UTF-16 Code Units, and Grapheme Clusters

One of the most common mistakes when handling Unicode in Java is treating every `char` as a complete user-visible character.

### 2.1. `char` Is a UTF-16 Code Unit

In Java, `char` is 16 bits wide. `String` is represented as a sequence of UTF-16 code units at the API level. Many characters in the Basic Multilingual Plane (BMP) use one code unit; supplementary code points outside the BMP are encoded as a **surrogate pair** consisting of two `char` values.

Example:

```java
String emoji = "😀";

System.out.println(emoji.length());
// 2: two UTF-16 code units

System.out.println(emoji.codePointCount(0, emoji.length()));
// 1: one Unicode code point
```

`String.length()` returns the number of UTF-16 code units, **not the number of Unicode code points or visible characters**. `emoji.charAt(0)` returns the high surrogate, not the entire emoji.

To iterate over code points, you can use:

```java
String text = "A😀中";

text.codePoints().forEach(cp -> {
    System.out.printf("U+%04X%n", cp);
});
```

The resulting code points are `U+0041`, `U+1F600`, and `U+4E2D`. When performing index operations, use `codePointAt`, `codePointBefore`, `offsetByCodePoints`, and `codePointCount` instead of blindly incrementing UTF-16 indices by one.

### 2.2. A Single Unicode Letter May Require Multiple Code Points

Vietnamese provides important examples of **combining marks**. The character `ắ` can be represented either as a single precomposed code point, or as the letter `a` followed by two combining marks.

```java
String composed = "ắ";              // U+1EAF
String decomposed = "a\u0306\u0301"; // a + combining breve + combining acute

System.out.println(composed.equals(decomposed));
// false: two different UTF-16 sequences
```

Both strings may look identical when rendered, yet `String.equals` compares sequences of code units without automatically applying Unicode canonical normalization. This affects usernames, storage keys, search, and comparing data from multiple input systems.

### 2.3. A Grapheme Cluster Is the Unit Users Typically Perceive as a Character

Even a code point does not always correspond to one displayed character. A sequence may consist of a base letter and multiple diacritics; an emoji may combine multiple code points joined by zero-width joiners.

For example, the sequence `👩‍💻` is typically perceived by users as one emoji, yet consists of code points for woman, zero-width joiner, and laptop. Therefore:

```java
String s = "👩‍💻";

System.out.println(s.length());
// 5 UTF-16 code units

System.out.println(s.codePointCount(0, s.length()));
// 3 code points
```

If the business rule is “at most 20 user-visible characters,” neither `length()` nor `codePointCount(...)` may satisfy the requirement. Use a grapheme cluster segmentation mechanism appropriate for Unicode and product rules; `Pattern` provides `\X` syntax to match an extended grapheme cluster on supported JDKs. Grapheme rules can evolve with Unicode data and runtime versions, so test on the exact deployed JDK.

### 2.4. Table for Choosing the Appropriate Measurement Unit

| Requirement | Usually Appropriate Unit/API | Notes |
|---|---|---|
| Number of code units in a String | `length()` | Not the number of code points. |
| Iterating over Unicode code points | `codePoints()` / `codePointAt()` | Carefully handle unpaired surrogates if data may be malformed. |
| Classifying letters, digits, or marks per code point | `Character` APIs taking `int` | Avoid splitting supplementary characters in half. |
| Number of user-perceived characters | Grapheme cluster segmentation | May differ from code point count; depends on Unicode rules. |
| Byte limits in protocols/files | Encode with a specific charset and count bytes | Do not infer UTF-8 byte count from String length. |

## 3. Classifying Characters with `java.lang.Character`

`Character` offers several character-classification methods. They do not share identical definitions and cannot be swapped interchangeably merely because they all return `boolean`.

### 3.1. `isLetter`, `isDigit`, `isLetterOrDigit`

```java
int latin = 'A';
int han = '中';
int arabicDigit = '١';

System.out.println(Character.isLetter(latin));       // true
System.out.println(Character.isLetter(han));         // true
System.out.println(Character.isDigit(arabicDigit));  // true
```

`Character.isLetter(int)` recognizes code points belonging to letter categories under the Unicode classification supported by the JDK. `Character.isDigit(int)` recognizes Unicode decimal digits per the API's criteria, not just ASCII `'0'` through `'9'`.

If the business rule permits only ASCII digits, use an explicit condition:

```java
boolean isAsciiDigit(int cp) {
    return cp >= '0' && cp <= '9';
}
```

Do not use `Character.isDigit` and assume it is equivalent to the regex `[0-9]`. A fixed ASCII rule and a Unicode rule are two distinct contracts.

### 3.2. Avoid the `char` Overload for Supplementary Code Points

For example, U+10400 is a Deseret letter outside the BMP:

```java
int codePoint = 0x10400;
String letter = new String(Character.toChars(codePoint));

System.out.println(letter.length());                     // 2
System.out.println(Character.isLetter(letter.charAt(0))); // false
System.out.println(Character.isLetter(letter.codePointAt(0))); // true
```

When calling `isLetter` with `letter.charAt(0)`, the method sees only a single surrogate code unit. The `int` overload checks the full code point. If the project needs to support Unicode outside the BMP, prefer code-point-based APIs at classification boundaries.

### 3.3. `getType`: Identifying the Specific Unicode Category

`Character.getType(int)` returns the code point's general category. Typical values include `UPPERCASE_LETTER`, `LOWERCASE_LETTER`, `OTHER_LETTER`, `DECIMAL_DIGIT_NUMBER`, `NON_SPACING_MARK`, `SPACE_SEPARATOR`, `CONTROL`, and `OTHER_SYMBOL`.

```java
int mark = 0x0301; // Combining acute accent

System.out.println(Character.getType(mark)
    == Character.NON_SPACING_MARK); // true
```

If a username filter accepts Unicode letters but rejects combining marks, strings in NFD form can be rejected even though they look identical to NFC. Therefore, decide normalization and validation policies **together**.

### 3.4. `isAlphabetic` Is Not Identical to `isLetter`

`Character.isAlphabetic(int)` is based on the Unicode Alphabetic property, which is broader than some simple category checks. It should not be mechanically replaced by `isLetter` when the business intent is accepting all characters with the Alphabetic property.

Conversely, a product's identifier rules need not allow every Unicode alphabetic character. The team should specify explicitly which scripts are accepted, whether combining marks and digits are allowed, and whether normalization applies.

### 3.5. `isJavaIdentifierStart` and `isJavaIdentifierPart`

Java defines its own rules for characters permitted in Java language identifiers:

```java
boolean canStart = Character.isJavaIdentifierStart(cp);
boolean canContinue = Character.isJavaIdentifierPart(cp);
```

These rules serve Java identifier syntax, **not** a suitable default for usernames, domain names, company names, or customer codes. Avoid adopting the Java compiler's rules as business policy without analyzing their meaning and security implications.

### 3.6. Unicode Scripts and Blocks

Sometimes an application needs to count or restrict certain writing systems. `Character.UnicodeScript.of(cp)` identifies the script, while `Character.UnicodeBlock.of(cp)` identifies the block a code point belongs to.

```java
int cp = '中';

System.out.println(Character.UnicodeScript.of(cp));
System.out.println(Character.UnicodeBlock.of(cp));
```

**Script is not synonymous with block.** A block is a contiguous code range defined in Unicode; a script describes a writing system. One script can span multiple blocks, and one block can contain multiple kinds of characters. When designing a script filter, rely on the appropriate property rather than assuming every code point in a block belongs to the same script.

## 4. Unicode Whitespace: An Often-Overlooked Source of Validation Changes

Whitespace does not consist solely of the ASCII space (`U+0020`), tab, and newline. Unicode includes multiple space separators and whitespace-related control characters. Java likewise provides different definitions for detecting and removing them.

### 4.1. `Character.isWhitespace` and `Character.isSpaceChar`

The two methods do not match the exact same character set:

```java
char regularSpace = ' ';
char nbsp = '\u00A0'; // NO-BREAK SPACE

System.out.println(Character.isWhitespace(regularSpace)); // true
System.out.println(Character.isSpaceChar(regularSpace));   // true

System.out.println(Character.isWhitespace(nbsp));         // false
System.out.println(Character.isSpaceChar(nbsp));          // true
```

NO-BREAK SPACE is an important example: it is a Unicode space separator, yet `Character.isWhitespace` excludes certain non-breaking spaces. Therefore, do not conclude a string is free of all whitespace merely because it was filtered with one specific API.

### 4.2. `String.trim()` and `String.strip()` Differ

`trim()` follows historical rules, mainly stripping leading/trailing code units less than or equal to U+0020. `strip()` uses `Character.isWhitespace` and supports many non-ASCII whitespace characters.

```java
String s = "\u2003Hello\u2003"; // EM SPACE

System.out.println(s.trim().equals("Hello"));  // false
System.out.println(s.strip().equals("Hello")); // true
```

However, `strip()` does not automatically remove every Unicode space separator, such as NO-BREAK SPACE in the example above. If the requirement is to remove Unicode White_Space characters under a different definition, define an explicit policy and test the full relevant character set.

### 4.3. Comparison with Regex `\s`

In Java regex, default `\s` generally corresponds to the basic ASCII whitespace set. When `Pattern.UNICODE_CHARACTER_CLASS` is enabled, predefined character classes like `\s` follow broader Unicode rules.

```java
import java.util.regex.Pattern;

String nbsp = "\u00A0";

System.out.println(Pattern.compile("\\s").matcher(nbsp).matches());
// false under default rules

System.out.println(Pattern.compile(
    "\\s", Pattern.UNICODE_CHARACTER_CLASS
).matcher(nbsp).matches());
// true: Unicode White_Space includes NO-BREAK SPACE
```

Key takeaway: **`Character.isWhitespace`, `Character.isSpaceChar`, `String.strip()`, and regex `\s` are not four equivalent ways of writing the same check**. If a project upgrades the JDK or alters regex flags, whitespace normalization may change and alter comparison or parsing results.

## 5. How Java Regex Classifies Characters

`java.util.regex.Pattern` supports both ASCII-based and Unicode-based syntax. To analyze migration impact, know which character set each pattern requests.

### 5.1. `[A-Za-z]` and `[0-9]`: Explicit ASCII Sets

```java
import java.util.regex.Pattern;

Pattern asciiCode = Pattern.compile("[A-Za-z0-9]+");

System.out.println(asciiCode.matcher("User123").matches()); // true
System.out.println(asciiCode.matcher("Tâm123").matches());   // false
```

These ranges specify exact ASCII code values. If a technical code's contract permits only ASCII, writing them explicitly is easy to control. However, if used for personal names or multilingual natural text, this policy may reject valid user data.

### 5.2. `\d`, `\w`, `\s`: Predefined Classes and Unicode Flags

Commonly used Java regex predefined classes:

| Regex | Common Default Meaning | When `UNICODE_CHARACTER_CLASS` Is Enabled |
|---|---|---|
| `\d` | ASCII digits `[0-9]` | Unicode decimal digits under the applicable definition. |
| `\w` | ASCII word characters, generally corresponding to ASCII letters/digits/underscore | Broader Unicode word characters, including many letters, digits, combining marks, and related characters. |
| `\s` | Certain ASCII whitespace such as space, tab, and newline | Unicode White_Space. |

Example with Arabic-Indic digits:

```java
import java.util.regex.Pattern;

String digits = "١٢٣"; // U+0661 U+0662 U+0663

Pattern defaultDigits = Pattern.compile("\\d+");
Pattern unicodeDigits = Pattern.compile(
    "\\d+", Pattern.UNICODE_CHARACTER_CLASS
);

System.out.println(defaultDigits.matcher(digits).matches()); // false
System.out.println(unicodeDigits.matcher(digits).matches()); // true
```

Here the source code is identical, yet toggling the flag produces an entirely different validation contract. Furthermore, if the JDK's Unicode tables change, Unicode-based predefined classes can also match a different set of code points.

### 5.3. `(?U)` Enables Unicode Character Classes Directly Inside the Pattern

Java regex supports the embedded `(?U)` flag, equivalent to enabling `Pattern.UNICODE_CHARACTER_CLASS` for the applicable scope of the pattern.

```java
Pattern p1 = Pattern.compile("(?U)\\w+");

Pattern p2 = Pattern.compile(
    "\\w+", Pattern.UNICODE_CHARACTER_CLASS
);
```

When reading a legacy regex, check both the flags passed to `Pattern.compile(...)` and embedded flags written inside the expression itself. A regex string `"\\w+"` does not reveal the full matching behavior if compilation flags are ignored.

### 5.4. Explicit Unicode Classes with `\p{...}`

Java regex supports many Unicode property classes. For example:

```java
Pattern letters = Pattern.compile("\\p{L}+");
Pattern marks = Pattern.compile("\\p{M}+");
Pattern decimalNumbers = Pattern.compile("\\p{Nd}+");
Pattern separators = Pattern.compile("\\p{Zs}+");
```

- `\p{L}`: Unicode letter categories.
- `\p{M}`: Unicode combining marks.
- `\p{Nd}`: Unicode decimal digits.
- `\p{Zs}`: Unicode space separators.

Pattern also supports other properties and notations, such as scripts or blocks, using the syntax supported by the JDK. Consult the `java.util.regex.Pattern` Javadoc for the exact JDK version in use when writing complex properties.

A regex such as `\p{L}` does not automatically include combining marks. If validation uses `\p{L}+` and the input is in decomposed form (NFD), accented strings may be rejected even though the precomposed form (NFC) is accepted.

### 5.5. `\b` and Word Boundaries Need Separate Testing

The word boundary `\b` depends on how the regex engine determines transitions between word and non-word characters. Behavior of word boundaries and Unicode-related classes has exhibited version differences across releases, so do not assume `\b` is always equivalent to a hand-written rule based on `\w` across every JDK.

For instance, tokenization based on `"\\b\\w+\\b"` may not satisfy the requirement “split natural words in Vietnamese, Thai, or Japanese.” For multilingual text, define the notion of *word* clearly and test representative strings. Regex word boundaries do not fully replace language-specific word segmentation algorithms.

### 5.6. `Pattern.CASE_INSENSITIVE` and `Pattern.UNICODE_CASE`

Case-insensitive matching is not a simple ASCII problem in every script. Java regex provides these flags:

```java
Pattern p = Pattern.compile(
    "somePattern",
    Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
```

`CASE_INSENSITIVE` enables case-insensitive matching; `UNICODE_CASE` makes those rules Unicode-aware rather than ASCII-only by default. `UNICODE_CHARACTER_CLASS` also enables Unicode case folding where applicable.

Do not treat these flags as **locale-sensitive** string comparison. Particularly for Turkish and other languages with special casing rules, case conversion, identifier comparison, and regex matching require explicit policies.

### 5.7. Escaping in Java Strings and Regex

Because a regex is written inside a Java string literal, the backslash `\` generally must be escaped an additional time:

```java
String regex = "\\p{L}+"; // regex engine receives \p{L}+
```

If reading the same expression from a configuration file, the escaping layer can differ:

```properties
# In configuration files, backslash interpretation depends on the parser
name.regex=\\p{L}+
```

The configuration example above illustrates that you must verify the escaping rules of **the format and configuration parsing library**; in `java.util.Properties`, backslash itself acts as an escape character. Do not copy a Java string literal into YAML/properties/JSON and assume the regex engine receives the exact same string. The safe approach is to log or test the expression **after the configuration parser has decoded it** in a test environment.

## 6. Unicode Normalization and Comparison Consistency

Unicode allows certain sequences to have multiple canonically equivalent representations. Java provides `java.text.Normalizer` to convert strings to different normalization forms.

### 6.1. NFC and NFD

- **NFC**: canonical composition, preferring precomposed character forms where available.
- **NFD**: canonical decomposition, breaking decomposable characters into their constituent parts.

Example:

```java
import java.text.Normalizer;

String a = "ắ";
String b = "a\u0306\u0301";

System.out.println(a.equals(b)); // false

String n1 = Normalizer.normalize(a, Normalizer.Form.NFC);
String n2 = Normalizer.normalize(b, Normalizer.Form.NFC);

System.out.println(n1.equals(n2)); // true
```

If the system uses normalized names as lookup keys, standardize normalization at **data ingestion points** as well as during comparison, search, and storage, rather than normalizing in only one service.

### 6.2. NFKC and NFKD Are Not Equivalent to NFC/NFD

`NFKC` and `NFKD` apply compatibility normalization, which can merge representations that differ only in compatibility formatting, such as fullwidth characters or ligatures.

This may be desirable when normalizing search tokens, yet should not be applied by default to all data. Compatibility normalization can lose meaningful distinctions in original text, proper names, or data requiring legal or technical exactness.

Clarify the goal: preserving original text, canonical-equivalent comparison, variant-insensitive search, or security identifier normalization. Each goal demands a different policy.

### 6.3. Normalization Before or After Validation?

Processing order can change the result:

```text
Input
  |
  v
Decode using the specified charset
  |
  v
Normalization per contract (if required)
  |
  v
Validation by code point/grapheme/regex
  |
  v
Store or use
```

If validating with `\p{L}+` before normalization, a decomposed Vietnamese string may be rejected due to combining marks. If normalizing to NFC first, many accented letters become single precomposed letter code points. However, not every valid sequence collapses into a single code point, so multilingual data generally still requires explicit rules for combining marks.

### 6.4. Should You Use `Pattern.CANON_EQ`?

Java regex has the `CANON_EQ` flag for canonical equivalence. However, enabling this mechanism carries performance costs and distinct matching behavior; do not treat it as a default substitute for a clearly designed normalization and validation pipeline.

For data contracts needing stability, it is usually easier to control by explicitly normalizing input first and then running regex on the chosen representation. Whichever method you use, test with combining marks and multi-code-point characters.

## 7. Real-World Scenarios Prone to Regressions After Upgrading the JDK

### 7.1. Username Validation Changes the Accepted Character Set

Suppose a service uses:

```java
boolean valid = Pattern.compile("(?U)\\w+")
    .matcher(username)
    .matches();
```

The regex uses the JDK's Unicode word class. When the JDK adds support for more code points or updates Unicode properties, usernames that were previously rejected may start being accepted. If security checks or duplicate-name logic relied on the old character set, behavior can diverge across nodes running different JDKs.

The solution is to write an explicit **validation contract**: allowed scripts, which unit measures length, which normalization form applies, how case and whitespace are handled, and a representative test dataset. Do not rely on a short regex and treat it as a complete policy.

### 7.2. Number Extraction from Text Changes Due to `\d`

```java
Pattern asciiOnly = Pattern.compile("\\d+");
Pattern unicode = Pattern.compile("(?U)\\d+");
```

The two patterns may match different sequences. For instance, text may contain Arabic-Indic digits or decimal digits from another script. If a field requires an ASCII transaction code by protocol, use `[0-9]` and document it clearly. If Unicode digits must be accepted for display or natural-language processing, define how they are normalized for storage and test numeric parsing.

Note: a regex accepting a character as a digit does not guarantee that all number-parsing libraries or downstream systems accept that representation.

### 7.3. Vietnamese NFC/NFD Data Yields Different Regex Results

```java
Pattern lettersOnly = Pattern.compile("\\p{L}+");

String composed = "ắ";
String decomposed = "a\u0306\u0301";

System.out.println(lettersOnly.matcher(composed).matches());
// true

System.out.println(lettersOnly.matcher(decomposed).matches());
// false: two combining marks belong to the Mark category, not Letter
```

If one client sends NFC and another sends NFD, validation can return different results even on the same JDK. A JDK upgrade is not the only cause; migrations frequently expose this issue due to changes in file-reading libraries, operating systems, or normalization pipelines.

### 7.4. Non-Breaking Spaces in Copy/Pasted Data

Users may copy a string containing U+00A0 from HTML. Code using `strip()` or default regex `\s` might not strip the character as the team expects. Conversely, enabling regex Unicode mode can cause tokenization to recognize additional whitespace characters.

If a payment system compares reference codes after “trimming whitespace,” define exactly which code points are removed instead of arbitrarily switching between `trim`, `strip`, and `replaceAll("\\s+", ...)`.

### 7.5. Locale-Dependent Case Mapping

```java
import java.util.Locale;

String key = "TITLE";

String defaultLower = key.toLowerCase();
String rootLower = key.toLowerCase(Locale.ROOT);
```

`toLowerCase()` without a locale argument can depend on the process's default locale. In certain languages such as Turkish, the letter `I` has special casing rules. If a JDK migration accompanies a change in the default locale or container environment, results can differ even if Unicode data did not change.

For technical codes independent of natural language, use an explicitly specified locale per policy; `Locale.ROOT` is usually more appropriate than relying accidentally on the default locale. For personal names and natural text, separately consider linguistic rules, Unicode normalization, and search behavior.

### 7.6. Tokenization and Word Boundaries in Logs or Search

A log-analysis system might use:

```java
Pattern token = Pattern.compile("\\b\\w+\\b");
```

Results can depend on the regex engine's definition of word characters and word boundaries, Unicode flags, and the JDK version. If a system builds search indexes across multiple nodes, do not run some nodes on an older JDK and others on a newer JDK without comparing tokenization outputs on multilingual data.

If the actual requirement is word segmentation for Vietnamese or another specific language, use a proper segmentation solution instead of relying on `\b` by default.

### 7.7. Visually Similar Characters with Different Code Points

Unicode contains characters across different scripts that look alike (*confusables*). Canonical normalization does not fully solve spoofing using look-alike characters. For example, certain Latin and Cyrillic letters appear nearly identical while having distinct code points.

For usernames, domains, filenames, or sensitive identifiers, analyze spoofing risks, mixed-script hazards, and appropriate identifier policies. Do not treat `\p{L}+` or NFC as a complete security filter.

## 8. Determining Whether an Issue Stems from Unicode Data or Application Policy

When observing differing results between two environments, classify the root cause rather than jumping to “the new JDK changed regex.”

| Possibility | Symptom | How to Verify |
|---|---|---|
| Different JDK Unicode version | `Character.getType`, `isLetter`, or Unicode regex differs on a code point | Print the code point and classification results on both runtimes. |
| Different regex flags | `\d`, `\w`, `\s`, or case-insensitive matching differs | Print the pattern, flags, and build/runtime configuration. |
| Different NFC/NFD strings | Text looks identical, yet `equals` or regex differs | Print the code point sequence and normalization form. |
| Different decoding charset | Characters entering the JVM already differed before regex ran | Inspect source bytes and the decoding charset. |
| Different default locale | Lowercasing, uppercasing, or locale-sensitive classification differs | Print the actual locale and set an explicit locale where needed. |
| Different regex library | Project switched between `java.util.regex`, ICU, or a third-party library | Confirm the regex engine, version, and property rules. |
| Input data changed | Client or OS sent a different string | Log the code points of sample inputs, not just screenshots. |
| Different configuration | Profile toggles Unicode mode or loads patterns from config | Check the effective regex string/flags after parsing config. |

### 8.1. Diagnosing by Code Point Instead of Visually Inspecting Logs

Two strings that look nearly identical in a console may have different code points. Printing hex values eliminates guesswork:

```java
static String codePoints(String text) {
    StringBuilder out = new StringBuilder();
    text.codePoints().forEach(cp ->
        out.append(String.format("U+%04X ", cp))
    );
    return out.toString().trim();
}
```

For the strings `"ắ"` and `"a\u0306\u0301"`, the code point outputs will differ even though their rendered appearance may look identical. When logging real data, comply with personal data protection policies; in tests, you can use synthetic character sets.

### 8.2. Inspecting `Pattern.flags()` and the Regex Source

```java
Pattern p = Pattern.compile(
    "\\w+", Pattern.UNICODE_CHARACTER_CLASS
);

System.out.println(p.pattern());
System.out.println(p.flags());
```

For regexes loaded from YAML/JSON/properties, inspect the actual string **after the configuration parser has decoded it**. One wrong escaping layer can cause differences unrelated to the Unicode version.

## 9. Designing a Regression Test Suite When Upgrading the JDK

A solid regression test suite should run the same source code, dependencies, and sample data across all JDKs to be supported. Record exact runtime versions to distinguish JDK-induced differences from build, locale, or data differences.

### 9.1. Selecting Representative Data

Do not test only `abc123`. A sample matrix might include:

| Group | Sample | What to Verify |
|---|---|---|
| ASCII | `ABC`, `123`, `_` | Do flags change ASCII rules? |
| Precomposed Vietnamese | `ắ`, `ế`, `ộ` | Letter category and validation. |
| Decomposed Vietnamese | `a\u0306\u0301` | Normalization, combining marks. |
| Han / other script letters | `中` | Unicode letter and `\w`. |
| Non-ASCII digits | `١٢٣` | `Character.isDigit` vs default/Unicode `\d`. |
| Supplementary characters | U+10400, `😀` | Code points vs UTF-16 code units, category. |
| Whitespace | U+0020, U+00A0, U+2003, `\t`, `\n` | `isWhitespace`, `strip`, `\s`. |
| Case mapping | `I`, `İ`, `ı` | Locale and Unicode case-insensitive matching. |
| Multi-code-point graphemes | `👩‍💻` | Display count, grapheme splitting, length limits. |
| Rare combining/script characters | Marks or scripts supported by the product | Unicode properties on the target JDK. |

Supplement with sanitized real data, especially if the application operates across multiple languages or markets.

### 9.2. Running the Same Diagnostic Program on Two JDKs

Example short program to observe classification and regex results:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeBehaviorProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("locale=" + Locale.getDefault());

        int[] points = { 'A', '中', '١', 0x0301, 0x10400, 0x00A0 };
        for (int cp : points) {
            System.out.printf(
                "U+%04X type=%d letter=%s digit=%s whitespace=%s spaceChar=%s%n",
                cp,
                Character.getType(cp),
                Character.isLetter(cp),
                Character.isDigit(cp),
                Character.isWhitespace(cp),
                Character.isSpaceChar(cp)
            );
        }

        String digits = "١٢٣";
        System.out.println("default \\d=" +
            Pattern.compile("\\d+").matcher(digits).matches());
        System.out.println("unicode \\d=" +
            Pattern.compile("\\d+", Pattern.UNICODE_CHARACTER_CLASS)
                .matcher(digits).matches());

        String a = "ắ";
        String b = "a\u0306\u0301";
        System.out.println("rawEqual=" + a.equals(b));
        System.out.println("nfcEqual=" +
            Normalizer.normalize(a, Normalizer.Form.NFC).equals(
                Normalizer.normalize(b, Normalizer.Form.NFC)));
    }
}
```

Compile and run on the runtimes within your support matrix, for example:

```bash
javac UnicodeBehaviorProbe.java
java UnicodeBehaviorProbe
```

When comparing different JDKs, control both the **compiler target** and the **runtime target**. If compiling with a newer JDK while still running on an older JDK, set `--release` appropriately. Do not use a class file requiring a newer Java version and draw wrong conclusions when an older JVM refuses to load it.

The illustrative program above does not represent every data path; expand it with actual production input samples and regexes.

### 9.3. Testing by Contract, Not Just Snapshotting Implementation

For technical fields accepting only ASCII, tests should enforce fixed rules, such as codes matching `[A-Z0-9]{8}`. For multilingual personal names, tests should assert explicit Unicode policies rather than merely asserting a few strings that happened to pass.

When changing JDKs, if a new result differs from the old one, categorize it:

1. Is this an intentional change per the Unicode/JDK specification?
2. Does it align with the product contract?
3. Are stored data and data sent by older clients still processed compatibly?
4. Are there security, uniqueness, or search-result impact risks?
5. Is it necessary to pin the rule, version the policy, or migrate data?

Not every difference is a bug to revert. Some differences are improvements adding support for newer languages. Decisions should rest on data contracts and consumer impact.

### 9.4. Testing Across Multiple Locales and Deployment Regions

If the product relies on case conversion, word segmentation, or language-specific text processing, test representative locales. Use `Locale.ROOT` only when a language-independent policy is intended; do not force all user text into locale-neutral rules when business logic genuinely requires linguistic rules.

In CI, record the locale and related environment variables, because changing a base image or OS configuration can alter the default locale or charset at the same time as the JDK upgrade.

## 10. Design Policies to Minimize Compatibility Risk

### 10.1. Distinguish ASCII and Unicode Rules Explicitly

For protocol identifiers, transaction codes, or machine-to-machine tokens that accept only ASCII, use `[A-Za-z0-9]`, `[0-9]`, or explicit code-point range comparisons. For natural text, use appropriate Unicode properties instead of forcing users into ASCII regexes without reason.

What matters is **documenting the choice explicitly**, rather than letting a flag or JDK version accidentally dictate product policy.

### 10.2. Choose a Normalization Form by Contract

If the system requires canonical-equivalent comparison, normalize before checking uniqueness or performing lookups. Document the normalization form, policy version, and how legacy data is handled. For sensitive data that must be stored verbatim, you can retain the raw original separately and compute a normalized key for search.

Do not use NFKC by default for every field; compatibility normalization can alter meaning in certain contexts.

### 10.3. Do Not Rely on a Single Regex for Complete Unicode Security

Regex can verify character sets and structure, yet does not fully solve issues such as confusable characters, IDNs, mixed scripts, canonical equivalence, semantic validation, and identifier uniqueness. For security-sensitive data, apply dedicated policies and test for spoofing risks.

### 10.4. Record Regex Flags and JDK Version in the Migration Dossier

When a regex is widely used in validation, record:

| Item | Value to Record |
|---|---|
| Regex source | Java literal, config key, or framework annotation. |
| Effective pattern | Regex string after all escaping is resolved. |
| Flags | `UNICODE_CHARACTER_CLASS`, `CASE_INSENSITIVE`, `UNICODE_CASE`, etc. |
| Input normalization | NFC/NFD/NFKC/NFKD or unnormalized. |
| Runtime | Relevant JDK version, vendor, and locale. |
| Allowed examples | Valid sample inputs and inputs that must be rejected. |
| Downstream contract | DB collation, API, index, parser, and consumers. |

This information enables accurate before/after migration comparisons, especially in microservice architectures running multiple runtime versions.

### 10.5. Avoid Changing Multiple Variables in the Same Experiment

When comparing two JDKs, keep inputs, dependencies, regex flags, normalization, and locale constant whenever possible. If you simultaneously upgrade the framework, change the regex, switch OS, change the charset, and upgrade the JDK, any validation difference will be very difficult to attribute.

Only after isolating the JDK's impact should additional changes be evaluated in separate waves or through a controlled test matrix.

## 11. Common Misconceptions

**“One `char` is one Unicode character.”** Not always. A supplementary code point is represented by two UTF-16 code units; a grapheme cluster can contain even multiple code points.

**“`String.length()` counts user-visible characters.”** No. It counts UTF-16 code units. To count code points or graphemes, use the corresponding mechanisms.

**“`Character.isDigit` and regex `\d` always match the same character set.”** No. Java `Character` classifies digits according to Unicode, whereas Java regex's default `\d` behaves differently from `\d` with Unicode character classes enabled.

**“`\p{L}` accepts every representation of accented Vietnamese letters.”** Not necessarily. Decomposed combining marks belong to the `Mark` category, not the `Letter` category.

**“`trim`, `strip`, `isWhitespace`, and regex `\s` are equivalent.”** No. They use different character sets and rules; NO-BREAK SPACE is a classic example.

**“Enabling Unicode regex only adds language support without changing contracts.”** No. The accepted input set, tokenization, and word matching can all change.

**“Two visually identical strings are always equal.”** No. `String.equals` does not automatically normalize; combining code point sequences can differ.

**“`Locale.ROOT` handles every language properly.”** No. It is suited for operations defined as locale-independent, whereas natural text may require a specific locale.

**“Upgrading the JDK cannot affect regexes if source code wasn't edited.”** It can, when regexes or `Character` depend on updated Unicode property tables. Verify against target data and runtime.

**“NFC and NFKC are the same.”** No. Compatibility normalization can collapse additional distinctions; choose based on data semantics.

**“Unicode regex is enough to prevent look-alike spoofing.”** No. Confusables and mixed-script issues require dedicated security policies.

## 12. Migration Checklist for Unicode and Regex

- [ ] Recorded exact JDK, vendor, update level, and locale of source/target environments.
- [ ] Identified all usages of `Character`, `String`, `Normalizer`, and `Pattern` in data validation/parsing.
- [ ] Distinguished usages of UTF-16 `char`, code points, and grapheme clusters.
- [ ] Audited regexes using `\d`, `\w`, `\s`, `\b`, `\p{...}`, and Unicode flags.
- [ ] Confirmed whether ASCII or Unicode semantics are intended for each data field.
- [ ] Defined the normalization form and the order of normalization and validation.
- [ ] Tested precomposed and decomposed Vietnamese data, non-ASCII digits, special whitespace, and supplementary code points.
- [ ] Verified locale-sensitive casing and case-insensitive regexes where applicable.
- [ ] Compared outputs across all supported JDKs using identical inputs and configurations.
- [ ] Evaluated impacts on uniqueness, search indexes, parsers, database collations, and downstream consumers.
- [ ] Documented accepted behavioral changes and data migration plans where needed.
- [ ] Checked confusable/mixed-script risks for sensitive identifiers.
- [ ] Saved regression tests and sample datasets so future JDK upgrades can re-run them.

## 13. Technical References to Consult

When you need to confirm the exact regex property or Unicode version supported by a JDK, prioritize documentation for **the exact target JDK** and the Unicode specification:

- `java.lang.Character` Javadoc: category classification, `isLetter`, `isDigit`, `isWhitespace`, `UnicodeScript`, `UnicodeBlock`.
- `java.util.regex.Pattern` Javadoc: predefined classes, Unicode properties, and the flags `UNICODE_CHARACTER_CLASS`, `UNICODE_CASE`, `CASE_INSENSITIVE`, and `CANON_EQ`.
- `java.text.Normalizer` Javadoc: NFC, NFD, NFKC, NFKD.
- Java Language Specification and Java Virtual Machine Specification: `char`, Unicode escapes, class files, and related rules.
- The Unicode Standard and its technical annexes concerning normalization, grapheme clusters, and character properties.
- JDK vendor release notes and migration guides: changes to Unicode data, the regex engine, locales, and standard library behavior across releases.

Do not grab an arbitrary Unicode table from the Internet and assume it matches the data used by the running JDK. If a discrepancy affects the product, reproduce it with the exact runtime, version, and input.

## 14. Conclusion

Unicode in Java is more than the ability to store accented letters. `char` represents a UTF-16 code unit; a code point may require two code units; a displayed character may consist of multiple code points. The `Character`, normalization, and regex APIs provide distinct interpretations of letters, digits, combining marks, whitespace, and word boundaries.

In Java Advance Compatibility Migration, **JDK Unicode property tables, regex flags, normalization, and locales** can all affect behavior without causing compile or linkage errors. The safeguard is to define clear data contracts, choose ASCII or Unicode intentionally, measure lengths in the proper units, normalize consistently, and test multilingual strings on the exact target runtime. That allows the team to distinguish an acceptable Unicode improvement from a regression that must be fixed before rolling out a new JDK.
