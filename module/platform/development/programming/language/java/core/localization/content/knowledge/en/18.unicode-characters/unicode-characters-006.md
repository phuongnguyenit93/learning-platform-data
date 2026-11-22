# Digits, Letters, and Unicode Properties via `Character`

In Java, `java.lang.Character` does not only handle Latin letters like `A–Z` or ASCII digits like `0–9`. It provides many APIs to query what kind of **Unicode character** a value is: whether it is a **letter**, a **decimal digit**, a **character with a numeric value**, **uppercase/lowercase**, a **combining mark**, **whitespace**, **which writing script it belongs to**, or what other **Unicode properties** it has.

Key point to grasp from the start: **a Java `char` is not synonymous with a Unicode code point**, and **"having a numeric value" is not synonymous with "being a decimal digit"**. A Roman numeral character can be considered alphabetic yet is neither a letter nor a digit in the sense of `isLetter` and `isDigit`. A letter outside the Basic Multilingual Plane (BMP) requires **two UTF-16 `char`s**, yet is only **one Unicode code point**.

This lesson uses Java 17+ to distinguish:
- `Character.isDigit`, `isLetter`, `isLetterOrDigit`, and `isAlphabetic`;
- `Character.digit` and `getNumericValue`;
- `Character.getType`, categories, `UnicodeScript`, and `UnicodeBlock`;
- `char` versus `int` code points;
- letter casing, combining marks, whitespace, and limitations when validating localized data.

The goal is to apply these properly in **Java core - localization**, while avoiding ASCII assumptions or the assumption that a single `Character.isLetterOrDigit` check suffices for all text validation requirements.

## 1. Three Levels: UTF-16 Unit, Code Point, and User-Perceived Character

Java stores `String` content as **UTF-16**. Three concepts to distinguish:

| Level | Meaning | Common APIs |
| --- | --- | --- |
| **Code unit** | A 16-bit UTF-16 unit, type `char` | `charAt`, `length` |
| **Code point** | A Unicode code value, type `int` | `codePointAt`, `codePoints`, `Character.isLetter(int)` |
| **Grapheme cluster** | A cluster of characters a user typically perceives as one unit | Requires text segmentation mechanisms, not just `charAt` |

For example, the letter **é** can be represented by:
- One code point **U+00E9** (LATIN SMALL LETTER E WITH ACUTE).
- Two code points **U+0065 + U+0301** (letter `e` and COMBINING ACUTE ACCENT).

The two representations can look identical yet have **different code point counts**. They are not guaranteed to compare equal under `String.equals` unless normalized.

Additionally, the **Deseret letter U+10400** outside the BMP is encoded as **one surrogate pair**, i.e., **two `char`s**. Thus `String.length()` can be 2 while `codePointCount(...)` is 1.

### Practical Rule

When classifying Unicode characters, prefer overloads taking **`int codePoint`**:

~~~java
Character.isLetter(codePoint);
Character.isDigit(codePoint);
Character.getType(codePoint);
~~~

When iterating through an arbitrary Unicode string, prefer `String.codePoints()` or traverse with `codePointAt` and `Character.charCount`. Do not assume each `charAt(i)` retrieves a complete character.

## 2. `Character.isDigit`: Unicode Decimal Digits

`Character.isDigit(int codePoint)` returns `true` if the code point belongs to the Unicode general category **DECIMAL_DIGIT_NUMBER (Nd)**.

That includes many decimal numeral systems, not only ASCII:

| Unicode code point | Example | `isDigit` | `getNumericValue` |
| --- | --- | --- | ---: |
| U+0035 | `5` ASCII | `true` | 5 |
| U+0665 | `٥` Arabic-Indic | `true` | 5 |
| U+096B | `५` Devanagari | `true` | 5 |
| U+FF15 | `５` Fullwidth | `true` | 5 |
| U+216B | `Ⅻ` Roman numeral 12 | `false` | 12 |
| U+00B2 | `²` superscript 2 | `false` | 2 |

**Important:** `isDigit` does not mean "a character allowed in your product's phone numbers/OTP codes/IDs". It means **it is a decimal digit according to the Unicode data used by the JDK**.

Runnable example **`UnicodeDigitDemo.java`**:

~~~java
public class UnicodeDigitDemo {
    public static void main(String[] args) {
        int[] points = {
                0x0035,  // ASCII digit five
                0x0665,  // Arabic-Indic digit five
                0x096B,  // Devanagari digit five
                0xFF15,  // Fullwidth digit five
                0x216B,  // Roman numeral twelve
                0x00B2   // Superscript two
        };

        for (int cp : points) {
            System.out.printf(
                    "U+%04X digit=%s numeric=%d%n",
                    cp,
                    Character.isDigit(cp),
                    Character.getNumericValue(cp)
            );
        }
    }
}
~~~

~~~bash
javac UnicodeDigitDemo.java
java UnicodeDigitDemo
~~~

Output:

~~~text
U+0035 digit=true numeric=5
U+0665 digit=true numeric=5
U+096B digit=true numeric=5
U+FF15 digit=true numeric=5
U+216B digit=false numeric=12
U+00B2 digit=false numeric=2
~~~

On the last two lines, the characters have **numeric values** yet do not belong to category **Nd**, so `isDigit` remains `false`. If you only want ASCII digits for a fixed protocol, the proper condition is usually `cp >= '0' && cp <= '9'`, not `Character.isDigit(cp)`.

## 3. `Character.isLetter`: Unicode Letters

`Character.isLetter(int)` returns `true` if the code point belongs to one of these Unicode categories:

- `UPPERCASE_LETTER (Lu)`;
- `LOWERCASE_LETTER (Ll)`;
- `TITLECASE_LETTER (Lt)`;
- `MODIFIER_LETTER (Lm)`;
- `OTHER_LETTER (Lo)`.

Thus "letter" does not mean only Latin letters. For instance, the Han character `中` (U+4E2D) and many letters from Arabic, Greek, Cyrillic, etc. can all be identified as letters.

Some code points that look like letters or letter symbols **do not belong to the letter group** under this rule. For instance, the Roman numeral `Ⅻ` (U+216B) belongs to **LETTER_NUMBER**, not the five letter categories listed above. It is accepted by `Character.isAlphabetic`, yet `isLetter` rejects it.

Example **`UnicodeLetterDemo.java`**:

~~~java
public class UnicodeLetterDemo {
    public static void main(String[] args) {
        int latin = 'A';
        int han = 0x4E2D;
        int romanNumber = 0x216B;
        int combiningAccent = 0x0301;

        System.out.println(Character.isLetter(latin));
        System.out.println(Character.isLetter(han));
        System.out.println(Character.isLetter(romanNumber));
        System.out.println(Character.isLetter(combiningAccent));
    }
}
~~~

~~~bash
javac UnicodeLetterDemo.java
java UnicodeLetterDemo
~~~

Output:

~~~text
true
true
false
false
~~~

The combining mark U+0301 by itself is not a letter. Yet a name containing **letter e + combining acute accent** can still be a valid personal name. This leads to an important limitation when validating strings: requiring **"every code point must be a letter"** can reject valid natural text.

## 4. `isAlphabetic` and `isLetter` Are Not the Same

`Character.isAlphabetic(int)` checks the Unicode **Alphabetic** property. It includes letters from the letter categories, and can also accept certain other code points marked as alphabetic by Unicode.

Therefore, these two expressions are **not always equivalent**:

~~~java
Character.isLetter(cp);
Character.isAlphabetic(cp);
~~~

Illustrative case U+216B (`Ⅻ`):

~~~text
isLetter     = false
isAlphabetic = true
~~~

Even though it is a **Roman numeral**, Unicode still treats it as having the alphabetic property. `isAlphabetic` does not mean "definitely a letter in the Latin alphabet"; the API name simply reflects following a specific Unicode property.

Create **`AlphabeticDifferenceDemo.java`**:

~~~java
public class AlphabeticDifferenceDemo {
    public static void main(String[] args) {
        int romanTwelve = 0x216B;

        System.out.println(Character.isLetter(romanTwelve));
        System.out.println(Character.isAlphabetic(romanTwelve));
        System.out.println(Character.isLetterOrDigit(romanTwelve));
        System.out.println(Character.getNumericValue(romanTwelve));
    }
}
~~~

~~~bash
javac AlphabeticDifferenceDemo.java
java AlphabeticDifferenceDemo
~~~

Output:

~~~text
false
true
false
12
~~~

When building an input filter, pick the property that **matches the product policy**—do not pick `isAlphabetic` merely because the name sounds broader or safer.

## 5. `isLetterOrDigit`: A Union, Not "Any Letter or Numeric Character"

`Character.isLetterOrDigit(cp)` is semantically equivalent to **`isLetter(cp) || isDigit(cp)`**. It does not automatically include every number category or combining marks.

Examples:

| Code point | `isLetter` | `isDigit` | `isLetterOrDigit` |
| --- | --- | --- | --- |
| `A` | true | false | true |
| `中` | true | false | true |
| `٥` | false | true | true |
| `Ⅻ` | false | false | false |
| `²` | false | false | false |
| U+0301 combining accent | false | false | false |
| Emoji U+1F600 | false | false | false |

An application accepting **personal names** cannot simply use `isLetterOrDigit` and call it correct: names can contain spaces, hyphens, apostrophes, combining marks, culturally specific characters, etc. Conversely, a technical code may need **ASCII-only**, and `isLetterOrDigit` is too broad because it accepts many writing systems.

Determine the **data purpose** first: natural user input, technical identifier, decimal number, verification code, or OCR data. Each kind requires a different policy.

## 6. `getNumericValue`: Numeric Value of a Code Point

`Character.getNumericValue(cp)` attempts to obtain the **integer numeric value** associated with a code point per Unicode. It can return:

- A **non-negative integer**, e.g., `5` or `12`;
- **`-1`** if no numeric value is supported;
- **`-2`** if it has a numeric value that **cannot be represented as a non-negative `int`** per the API contract, such as a fraction.

Therefore `getNumericValue` is **not** a check for "is a decimal digit" and does not replace a number parser.

Example **`NumericValueDemo.java`**:

~~~java
public class NumericValueDemo {
    public static void main(String[] args) {
        System.out.println(Character.getNumericValue('7'));
        System.out.println(Character.getNumericValue(0x216B));
        System.out.println(Character.getNumericValue(0x00B2));
        System.out.println(Character.getNumericValue(0x00BD));
        System.out.println(Character.getNumericValue('@'));
    }
}
~~~

~~~bash
javac NumericValueDemo.java
java NumericValueDemo
~~~

Output:

~~~text
7
12
2
-2
-1
~~~

U+00BD is the character **½**, which has a fractional numeric value and thus returns `-2`. Use `getNumericValue` to inspect a Unicode property; if you need to parse expressions like `"12.5"` or `"Ⅻ"` according to business rules, use a dedicated parser and explicit input policy.

**Warning for numeric input:** `getNumericValue('A')` can return 10 under extended digit tables, so **do not** treat every non-negative numeric value as proof that the original character is a valid decimal digit.

## 7. `Character.digit` and Radix

`Character.digit(codePoint, radix)` asks whether a code point can represent **a digit in the requested radix**, returning the valid numeric value or `-1`.

Examples:

~~~java
Character.digit('9', 10);       // 9
Character.digit('F', 16);       // 15
Character.digit('G', 16);       // -1
Character.digit(0x0665, 10);   // 5
Character.digit(0x216B, 10);   // -1
~~~

This is a snippet placed inside a method, not a standalone program.

A runnable example:

**`DigitRadixDemo.java`**

~~~java
public class DigitRadixDemo {
    public static void main(String[] args) {
        System.out.println(Character.digit('F', 16));
        System.out.println(Character.digit('G', 16));
        System.out.println(Character.digit(0x0665, 10));
        System.out.println(Character.digit(0x216B, 10));
    }
}
~~~

~~~bash
javac DigitRadixDemo.java
java DigitRadixDemo
~~~

Output:

~~~text
15
-1
5
-1
~~~

In supported radices, Latin letters `A–Z` can act as digits with values 10–35, though whether they are permitted as digits depends on `radix`. Do not call `getNumericValue` and assume every character with a numeric value belongs to the digit syntax of a radix.

`Integer.parseInt` and other number parsers have their own rules. In Java, certain Unicode Nd digits can be accepted by integer parsers, so an "ASCII digits only" requirement must be validated **before** parsing.

## 8. Java Parsers Can Accept Non-ASCII Digits

For example, instead of typing characters directly that might suffer console encoding issues, we construct a string from code points U+0661 and U+0662, corresponding to two Arabic-Indic digits with values `1` and `2`.

Create **`UnicodeParseDemo.java`**:

~~~java
public class UnicodeParseDemo {
    public static void main(String[] args) {
        String arabicDigits = new String(
                new int[]{0x0661, 0x0662}, 0, 2);

        System.out.println(arabicDigits.codePointCount(
                0, arabicDigits.length()));
        System.out.println(Integer.parseInt(arabicDigits));

        boolean onlyAscii = arabicDigits.codePoints()
                .allMatch(cp -> cp >= '0' && cp <= '9');

        System.out.println(onlyAscii);
    }
}
~~~

~~~bash
javac UnicodeParseDemo.java
java UnicodeParseDemo
~~~

Output:

~~~text
2
12
false
~~~

**Interpretation:** The parser can interpret those digits as the integer `12`, yet the input string does not contain ASCII digits. If an API receives an OTP code, invoice code, or value with a mandatory ASCII protocol format, it must enforce an **ASCII policy**, not merely check whether `parseInt` succeeds.

Conversely, in a multilingual user-facing UI, accepting localized digits might be a valid requirement. That must be an explicit product decision, not inferred from a single API.

## 9. Unicode General Category via `Character.getType`

`Character.getType(codePoint)` returns the **int code** of the code point's Unicode general category, corresponding to constants such as:

- `Character.UPPERCASE_LETTER`;
- `Character.LOWERCASE_LETTER`;
- `Character.OTHER_LETTER`;
- `Character.DECIMAL_DIGIT_NUMBER`;
- `Character.LETTER_NUMBER`;
- `Character.OTHER_NUMBER`;
- `Character.NON_SPACING_MARK`;
- `Character.SPACE_SEPARATOR`;
- `Character.OTHER_SYMBOL`;
- `Character.FORMAT`;
- `Character.UNASSIGNED`.

This is a Unicode category, not a sort rank or numeric value of the character. For example, `getType('5')` returns the category `DECIMAL_DIGIT_NUMBER`, not the number 5. To get the digit's value, use `digit` or `getNumericValue`.

Create **`UnicodeCategoryDemo.java`**:

~~~java
public class UnicodeCategoryDemo {
    public static void main(String[] args) {
        int asciiFive = '5';
        int roman = 0x216B;
        int superscript = 0x00B2;
        int accent = 0x0301;

        System.out.println(Character.getType(asciiFive)
                == Character.DECIMAL_DIGIT_NUMBER);
        System.out.println(Character.getType(roman)
                == Character.LETTER_NUMBER);
        System.out.println(Character.getType(superscript)
                == Character.OTHER_NUMBER);
        System.out.println(Character.getType(accent)
                == Character.NON_SPACING_MARK);
    }
}
~~~

~~~bash
javac UnicodeCategoryDemo.java
java UnicodeCategoryDemo
~~~

Output:

~~~text
true
true
true
true
~~~

General categories are often more useful than a Boolean check when an application needs to explain **why a code point was accepted or rejected**. For instance, a proper-name filter might explicitly allow letters, combining marks, and certain punctuation, instead of allowing only `isLetter`.

### A Category Is Not a Grammar Rule of a Language

No general category says whether a Vietnamese, French, or Arabic word is "grammatically valid". A category is a Unicode property of an **individual code point**, without full word/sentence context.

For spellchecking, word segmentation, bidirectional text handling, or plurals, you need specialized linguistic tools beyond `Character.getType`.

## 10. `UnicodeScript` and `UnicodeBlock`: Two Different Concepts

Java provides:

~~~java
Character.UnicodeScript.of(codePoint);
Character.UnicodeBlock.of(codePoint);
~~~

- **`UnicodeScript`** reflects the script property of a code point, e.g., `LATIN`, `CYRILLIC`, `ARABIC`, `HAN`, `DEVANAGARI`.
- **`UnicodeBlock`** reflects a **Unicode code block**, a named code range in the code chart.

Script and block are not synonymous. One script can span multiple blocks, and one block can contain characters with `COMMON`, `INHERITED`, or other script classifications.

Runnable example **`UnicodeScriptDemo.java`**:

~~~java
public class UnicodeScriptDemo {
    public static void main(String[] args) {
        int[] points = {'A', 0x4E2D, 0x0665, 0x0301};

        for (int cp : points) {
            System.out.printf("U+%04X script=%s%n",
                    cp, Character.UnicodeScript.of(cp));
        }
    }
}
~~~

~~~bash
javac UnicodeScriptDemo.java
java UnicodeScriptDemo
~~~

Output with the Unicode version supported by JDK 17:

~~~text
U+0041 script=LATIN
U+4E2D script=HAN
U+0665 script=ARABIC
U+0301 script=INHERITED
~~~

The combining mark U+0301 has script `INHERITED` because it depends on the context of the accompanying character. Digits or punctuation can carry script `COMMON`, `ARABIC`, or another script depending on the specific code point.

**Do not use `UnicodeBlock` as a "is Latin letter" check**. Likewise, do not conclude that a string of characters all in the same script is necessarily safe or meaningful: checking identifiers against lookalike characters (*confusables*) requires more rules.

## 11. Non-BMP Code Points: Why Can the `char` Overload Be Wrong?

`Character` APIs have multiple overloads:

~~~java
Character.isLetter(char ch);
Character.isLetter(int codePoint);
~~~

A `char` holds only one UTF-16 unit. For a non-BMP character, a single code point is encoded by **two surrogate code units**, so each individual `char` is not the whole character.

Example Deseret letter U+10400:

**`SupplementaryLetterDemo.java`**

~~~java
public class SupplementaryLetterDemo {
    public static void main(String[] args) {
        int codePoint = 0x10400;
        String text = new String(Character.toChars(codePoint));

        System.out.println(Character.charCount(codePoint));
        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));

        System.out.println(Character.isLetter(text.charAt(0)));
        System.out.println(Character.isLetter(text.codePointAt(0)));
    }
}
~~~

~~~bash
javac SupplementaryLetterDemo.java
java SupplementaryLetterDemo
~~~

Output:

~~~text
2
2
1
false
true
~~~

The line `isLetter(text.charAt(0))` receives only the **high surrogate**, not the actual Deseret letter. The line `isLetter(text.codePointAt(0))` receives U+10400 properly and returns `true`.

When a program must support all Unicode scripts, iterating over a `String` with `for (char ch : text.toCharArray())` and calling `isLetter(ch)` can accidentally reject non-BMP letters. Use code points to check.

### Iterating Over Code Points

Here is an example snippet inside a method:

~~~java
String text = new String(Character.toChars(0x10400)) + "A";

text.codePoints().forEach(cp -> {
    System.out.println(Character.isLetter(cp));
});
~~~

Output:

~~~text
true
true
~~~

Or manual iteration:

~~~java
for (int i = 0; i < text.length();) {
    int cp = text.codePointAt(i);
    // Process one complete code point here.
    i += Character.charCount(cp);
}
~~~

The second snippet assumes variable `text` is already declared. Remember **index `i` is still a UTF-16 code unit index**, because `String.codePointAt` accepts a position in `char`s; `cp` is one code point.

## 12. `String.length()` Does Not Measure "User-Perceived Characters"

For `String` in Java:

- `length()` returns the number of **UTF-16 code units**;
- `codePointCount(0, length())` counts **Unicode code points**;
- neither **necessarily equals the number of grapheme clusters**.

For example, a letter `e` followed by combining mark U+0301 has two code points, yet many interfaces treat it as **one visible character**. An emoji can comprise multiple code points linked by a zero-width joiner; slicing in the middle of that cluster can break its visual form.

Therefore:
- To classify code points, use `Character` + `codePoints()`.
- To limit byte count when transmitting data, measure bytes after encoding, e.g., UTF-8.
- To limit the "number of user-perceived characters", you need a **grapheme segmentation** algorithm following an appropriate standard, not just `String.length()` or `codePointCount()`.

Do not collapse these three counting rules into one in multilingual input screens.

## 13. Uppercase, Lowercase, and Unicode Case Mapping

`Character` has methods:

~~~java
Character.isUpperCase(cp);
Character.isLowerCase(cp);
Character.isTitleCase(cp);
Character.toUpperCase(cp);
Character.toLowerCase(cp);
Character.toTitleCase(cp);
~~~

These inspect or map properties of **a single code point**. Meanwhile, converting an entire `String` for a user's language may require **context- and locale-sensitive case mapping**, and can even produce multiple code points.

For example, the Latin letter `I` usually maps to `i` under simple mapping; however, in Turkish, uppercase `I` maps to **ı** (dotless i).

Example **`LocaleCaseDemo.java`**:

~~~java
import java.util.Locale;

public class LocaleCaseDemo {
    public static void main(String[] args) {
        String turkishLower =
                "I".toLowerCase(Locale.forLanguageTag("tr-TR"));

        System.out.println(Character.toLowerCase('I') == 'i');
        System.out.println(turkishLower.codePointAt(0) == 0x0131);

        String sharpS = new String(Character.toChars(0x00DF));
        String upperWord = sharpS.toUpperCase(Locale.GERMAN);

        System.out.println(upperWord.equals("SS"));
        System.out.println(Character.toUpperCase(0x00DF) == 0x00DF);
    }
}
~~~

~~~bash
javac LocaleCaseDemo.java
java LocaleCaseDemo
~~~

Output on Java 17:

~~~text
true
true
true
true
~~~

For the letter `ß`, `String.toUpperCase(Locale.GERMAN)` can expand into **two S letters**, whereas `Character.toUpperCase(int)` cannot represent a two-code-point expansion with a single `int`.

**Therefore:**
- Use `Character` for single-code-point checks/mappings when that is the exact requirement.
- Use `String.toLowerCase(locale)` / `toUpperCase(locale)` for string conversions with linguistic semantics.
- For protocol codes or technical keys needing locale-independent case normalization, consider `Locale.ROOT`.
- Do not treat case conversion as safe Unicode comparison for all identifiers; normalization and equivalence forms still apply.

## 14. Combining Marks and `Normalizer`

An accented Vietnamese or French word can be represented using a precomposed code point or a **sequence of base letter + combining mark**. `Character.isLetter` applies **to each code point individually**, so it returns `false` for a combining mark `NON_SPACING_MARK` even though the whole cluster is a valid letter.

Example:

**`UnicodeNormalizationDemo.java`**

~~~java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String decomposed = new String(new int[]{
                0x0065, 0x0301
        }, 0, 2);

        String composed = new String(new int[]{
                0x00E9
        }, 0, 1);

        System.out.println(decomposed.equals(composed));

        String left = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                composed, Normalizer.Form.NFC);

        System.out.println(left.equals(right));
        System.out.println(Character.isLetter(0x0301));
        System.out.println(
                Character.getType(0x0301)
                        == Character.NON_SPACING_MARK);
    }
}
~~~

~~~bash
javac UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Output:

~~~text
false
true
false
true
~~~

`Normalizer.Form.NFC` performs Unicode canonical composition normalization; it **does not translate languages** and does not decide on its own whether a name is valid. The NFD, NFKC, and NFKD forms serve different purposes—especially compatibility normalization, which can alter how presentation characters are interpreted.

**Practical consequence:** If a name validator only accepts `Character.isLetter` per code point, it might accept precomposed `é` yet reject `e + U+0301` even though both strings look identical. Design a clear Unicode policy and consider normalization/combining marks when appropriate.

## 15. Whitespace: `isWhitespace` and `isSpaceChar`

In localized text, whitespace is not only `U+0020`. Java provides:

- `Character.isWhitespace(cp)`;
- `Character.isSpaceChar(cp)`.

The two methods **do not produce the same result set**. For example, U+00A0 **NO-BREAK SPACE** is considered a **space character**, yet `isWhitespace` returns `false`.

Create **`UnicodeSpaceDemo.java`**:

~~~java
public class UnicodeSpaceDemo {
    public static void main(String[] args) {
        int ordinarySpace = 0x0020;
        int noBreakSpace = 0x00A0;

        System.out.println(Character.isWhitespace(ordinarySpace));
        System.out.println(Character.isSpaceChar(ordinarySpace));
        System.out.println(Character.isWhitespace(noBreakSpace));
        System.out.println(Character.isSpaceChar(noBreakSpace));
    }
}
~~~

~~~bash
javac UnicodeSpaceDemo.java
java UnicodeSpaceDemo
~~~

Output:

~~~text
true
true
false
true
~~~

A filter using only `String.trim()` or `Character.isWhitespace` may miss Unicode whitespace types the application needs to handle. Conversely, stripping all Unicode spaces can break valid formatting, such as currency amounts using a non-breaking space to keep the symbol and number on the same line.

**Do not automatically declare every "unusual" space to be malicious data.** Define input requirements, display expectations, and required Unicode properties for each text type.

## 16. Digits, Roman Numerals, and Symbols: Category Differs from Perception

Some characters carry numeric meaning or resemble numbers yet are not `DECIMAL_DIGIT_NUMBER`:

- `Ⅻ` belongs to **LETTER_NUMBER**, with numeric value `12`;
- `²` belongs to **OTHER_NUMBER**, with numeric value `2`;
- `½` has numeric value `1/2` and `getNumericValue` returns `-2`;
- An emoji symbol may fall under **OTHER_SYMBOL**;
- Han characters or alphabetic characters can have different numeric, mark, or script properties depending on the code point.

Thus, no single call answers all of these accurately:
1. "Is this a decimal digit?"
2. "Does this carry a numeric value?"
3. "Can this be a digit in a given radix?"
4. "Is this a valid numeric token under product syntax?"

Appropriate mapping:

| Need | Suggested API |
| --- | --- |
| Unicode decimal digit | `Character.isDigit(cp)` |
| Mandatory ASCII digit | `cp >= '0' && cp <= '9'` |
| Digit in radix 16 | `Character.digit(cp, 16)` |
| Unicode numeric value of a code point | `Character.getNumericValue(cp)` |
| Parsing a full integer | Number parser + policy validation |
| Parsing numbers by user locale | `NumberFormat`/`DecimalFormat` with locale and input validation |
| Knowing the actual category | `Character.getType(cp)` |

In machine-to-machine communication, numbers should generally be stored/exchanged in a structured or locale-independent notation. Localized digits are appropriate for **display or user input** when the product intentionally supports them.

## 17. Identifier Properties: Not Synonymous with Letters/Digits

Java provides:

~~~java
Character.isJavaIdentifierStart(cp);
Character.isJavaIdentifierPart(cp);
Character.isUnicodeIdentifierStart(cp);
Character.isUnicodeIdentifierPart(cp);
Character.isIdentifierIgnorable(cp);
~~~

These APIs answer whether a code point can **participate in an identifier under Java/Unicode rules**, not "is a user allowed to pick this username".

For instance, some code points are neither letters nor digits yet are allowed by Java in identifiers (such as underscore), and some code points behave differently between `isJavaIdentifierStart` and `isUnicodeIdentifierStart`.

Do not use `isJavaIdentifierPart` directly as a filter for passwords, usernames, or personal names:
- Some characters valid in Java source code are unsuitable for public identifiers.
- Some valid natural-language personal names may not be allowed in a Java identifier.
- A string satisfying Java identifier rules is not necessarily safe against **homoglyph/confusable** attacks, bidirectional controls, or spoofing.
- `Character.isIdentifierIgnorable` describes an identifier-related property; it does not mean every character returning `true` is safe to ignore in text.

When designing public identifiers, apply product-specific policies, normalization, mixed-script controls, and appropriate anti-spoofing checks. Relying on a single Boolean from `Character` is insufficient.

## 18. Text Direction, Mirrored Characters, and Control Characters

`Character` has several more useful APIs for Unicode handling:

- `Character.getDirectionality(cp)` — text directionality property per Unicode data;
- `Character.isMirrored(cp)` — whether the character has the mirrored property in bidirectional writing contexts;
- `Character.isISOControl(cp)` — certain ISO control characters;
- `Character.isDefined(cp)` — whether the code point is defined in the JDK's Unicode data;
- `Character.getName(cp)` — Unicode name of the code point when available.

Example:

~~~java
System.out.println(Character.isMirrored('('));
System.out.println(Character.getDirectionality('A')
        == Character.DIRECTIONALITY_LEFT_TO_RIGHT);
~~~

This is a snippet inside a method. Output:

~~~text
true
true
~~~

These properties help **detect/classify** characters, yet they **do not perform the full bidirectional text display algorithm**. When handling Arabic or Hebrew, you also need the UI or a suitable library's rendering/bidirectional algorithm.

Do not manually "reverse the string" to support RTL; reversing code units can break surrogate pairs and combining marks, while visual display order is governed by the bidi algorithm, not simple string reversal.

## 19. JDK Unicode Version and Changing Data

`Character` relies on a **Unicode data version** implemented by the JDK. When upgrading JDKs, newly assigned code points can receive categories, scripts, or other properties; methods like `isLetter`, `isDigit`, or `isDefined` may return new results for previously unsupported code points.

Therefore:
- Do not assume all Java versions recognize the exact same latest script set.
- If using Unicode classification to enforce **security policies or identifier validation**, re-test when updating the JDK.
- If strict compatibility is needed across services running on different runtimes, pin data policies and Unicode versions or use a centrally managed library.
- Do not write tests assuming "all currently undefined code points will remain `false` forever".

For this Java core lesson, treat examples U+0035, U+0665, U+216B, U+00B2, U+0301, and U+10400 as scenarios recognized in Java 17, and proactively verify on your deployed JDK whenever logic depends on categories/scripts.

## 20. Comprehensive Example: Classifying a String by Code Point

Create the file **`UnicodeClassifier.java`**:

~~~java
public class UnicodeClassifier {
    private static String classify(int cp) {
        if (Character.isDigit(cp)) {
            return "DECIMAL_DIGIT";
        }
        if (Character.isLetter(cp)) {
            return "LETTER";
        }
        if (Character.isAlphabetic(cp)) {
            return "ALPHABETIC_OTHER";
        }
        if (Character.getNumericValue(cp) >= 0) {
            return "NUMERIC_OTHER";
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        int[] points = {
                'A',
                0x0665,
                0x216B,
                0x00B2,
                0x1F600
        };

        for (int cp : points) {
            System.out.printf("U+%04X %s%n", cp, classify(cp));
        }
    }
}
~~~

~~~bash
javac UnicodeClassifier.java
java UnicodeClassifier
~~~

Output:

~~~text
U+0041 LETTER
U+0665 DECIMAL_DIGIT
U+216B ALPHABETIC_OTHER
U+00B2 NUMERIC_OTHER
U+1F600 OTHER
~~~

This example demonstrates how properties have **overlapping and distinct sets**; the label `ALPHABETIC_OTHER` is a custom label chosen by the program, not an official Unicode category.

**Example limitation:** Classifying a single code point cannot decide full acceptance rules for names, passwords, monetary amounts, or text. If an application needs to allow combining marks, consider the context of preceding and following code points, normalization, scripts, and product rules.

## 21. Deliberate Validation Examples for ASCII Digits and Unicode Letters

A technical reference code requiring **exactly six ASCII digits**:

~~~java
public static boolean isSixAsciiDigits(String input) {
    return input != null
            && input.length() == 6
            && input.chars().allMatch(
                    c -> c >= '0' && c <= '9');
}
~~~

This is a **snippet inside a class**. `String.chars()` is appropriate here **because the policy restricts to ASCII**, where every valid character uses one UTF-16 code unit. If a policy allows **Unicode decimal digits**, you must use code points and different criteria.

A coarse filter for **Unicode letters or combining marks** can be written as:

~~~java
public static boolean isLetterOrMark(int cp) {
    int type = Character.getType(cp);
    return Character.isLetter(cp)
            || type == Character.NON_SPACING_MARK
            || type == Character.COMBINING_SPACING_MARK
            || type == Character.ENCLOSING_MARK;
}
~~~

This is a snippet inside a class, **not yet a complete personal name validator**. If you allow combining marks in any position, a name starting with an orphaned mark could slip through. You need additional positional logic, allowed spaces/hyphens, length policies, and content controls as needed.

### Program Testing Two Different Policies

Create **`UnicodeValidationDemo.java`**:

~~~java
public class UnicodeValidationDemo {
    static boolean asciiDigits(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(
                        cp -> cp >= '0' && cp <= '9');
    }

    static boolean unicodeDecimalDigits(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(Character::isDigit);
    }

    public static void main(String[] args) {
        String ascii = "123";
        String arabic = new String(
                new int[]{0x0661, 0x0662, 0x0663}, 0, 3);

        System.out.println(asciiDigits(ascii));
        System.out.println(unicodeDecimalDigits(ascii));
        System.out.println(asciiDigits(arabic));
        System.out.println(unicodeDecimalDigits(arabic));
    }
}
~~~

~~~bash
javac UnicodeValidationDemo.java
java UnicodeValidationDemo
~~~

Output:

~~~text
true
true
false
true
~~~

Both checks are correct **within the scope of their declared policies**, yet they are not interchangeable. When validating business numeric values, also verify length, valid value range, overflow, and post-parse data types.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `char` as every Unicode character | Misses non-BMP code points | Use `int` overloads and `String.codePoints()` |
| Treating `String.length()` as user-perceived character count | Miscounts surrogate pairs and grapheme clusters | Pick the counting method matching the requirement |
| Treating `isDigit` as ASCII-only | Accepts digits from multiple numeral systems | Check `'0'..'9'` if policy is ASCII-only |
| Treating `getNumericValue>=0` as decimal digit | Accepts Roman numerals/superscripts, even Latin letters in some cases | Use `isDigit` or `digit` depending on intent |
| Treating `isLetter` and `isAlphabetic` as equivalent | Differing classification for letter-numbers | Pick the exact property |
| Treating `isLetterOrDigit` as a personal name validator | Rejects valid combining marks, spaces, and hyphens | Design context-aware validation |
| Treating `UnicodeBlock` as script | Wrong when a script spans multiple blocks | Use `UnicodeScript` when script is needed |
| Using `Character.toUpperCase` on whole strings needing locale | Misses multi-character conversions and linguistic rules | Use `String.toUpperCase(locale)` |
| Comparing visually identical Unicode strings with `equals` and concluding they are different text | Composed/decomposed forms may have different bytes | Consider `Normalizer` |
| Assuming all Unicode whitespace has `isWhitespace=true` | Misses NBSP | Distinguish `isWhitespace`/`isSpaceChar` |
| Assuming `isJavaIdentifierPart` suffices for safe usernames | Misses spoofing/mixed scripts/controls | Dedicated identifier policy and checks |
| Reversing strings to support RTL | Corrupts Unicode and violates the bidi algorithm | Use an appropriate bidi/rendering engine |
| Upgrading the JDK without checking Unicode properties | Classification results can change | Test/pin Unicode version |

## 23. Testing Checklist for Localization Applications

A practical test suite should cover:

1. **ASCII Latin and digits**: `A`, `z`, `0`, `9`.
2. **Localized digits**: Arabic-Indic, Devanagari, fullwidth.
3. **Numeric non-digits**: `Ⅻ`, `²`, `½`.
4. **Characters from multiple scripts**: Latin, Han, Cyrillic, Arabic.
5. **Non-BMP characters**: a surrogate-pair code point, e.g., U+10400.
6. **Combining marks**: precomposed strings and base + combining mark strings.
7. **Special spaces**: NBSP and narrow NBSP.
8. **Locale-specific casing**: at least Turkish and `ß`.
9. **Mixed scripts/confusables** if using public identifiers.
10. **Control and bidi characters** when data is displayed in sensitive logs/UIs.
11. **Runtime Unicode version** when upgrading the JDK.
12. **Number parsers and ASCII boundaries** if protocols require fixed notation.

When testing, prefer representing code points with `0xXXXX` or `U+XXXX` rather than relying on whether a font/console renders every script properly. `System.out.printf("U+%04X", cp)` helps verify exact code values.

## 24. Exercises with Answers

**Question 1.** What does `Character.isDigit(0x0665)` return? Does it guarantee this is an ASCII digit?

**Answer:** Returns `true`, yet U+0665 is Arabic-Indic digit five, **not ASCII**.

**Question 2.** Why does `Character.isDigit(0x216B)` return `false` while `getNumericValue(0x216B)` returns `12`?

**Answer:** U+216B is a Roman numeral in category `LETTER_NUMBER`, not decimal digit `Nd`.

**Question 3.** Do `isLetter(0x216B)` and `isAlphabetic(0x216B)` return the same result?

**Answer:** No. They return `false` and `true`, respectively.

**Question 4.** Why can `Character.isLetter(text.charAt(0))` be wrong for a non-BMP letter?

**Answer:** `charAt(0)` retrieves only a single surrogate code unit, not the complete code point. Use `codePointAt(0)` and the `int` overload.

**Question 5.** What does `Character.getNumericValue(0x00BD)` returning `-2` mean?

**Answer:** The character `½` has a fractional numeric value that cannot be represented by a non-negative `int` as returned by this API.

**Question 6.** Why can a name containing `e` + U+0301 be rejected by `isLetter` on the second code point?

**Answer:** U+0301 is a `NON_SPACING_MARK`, which does not belong to Unicode letter categories; name validation must consider combining marks/normalization.

**Question 7.** Is using `Character.isLetterOrDigit` to allow all personal names reasonable?

**Answer:** No; personal names can contain spaces, hyphens, apostrophes, or combining marks, and some name rules cannot be determined solely from individual code point categories.

**Question 8.** When uppercasing an entire string for Turkish users, should you use `Character` or `String.toUpperCase(locale)`?

**Answer:** Use the string conversion taking the right `Locale` for the language, because case mapping can depend on locale/context and can change string length.

**Question 9.** Why is `Character.isWhitespace(0x00A0)` `false` while `isSpaceChar(0x00A0)` is `true`?

**Answer:** They inspect different Unicode property sets; NBSP is a space character yet is excluded from the API's whitespace definition.

**Question 10.** If an OTP code filter requires exactly six ASCII digits, should you use `Character.isDigit`?

**Answer:** Do not use `isDigit` alone. Check exact length and verify each code point is in the range `'0'` to `'9'`.

## 25. Workflow for Applying This in Real-World Java Systems

1. **Identify data requirements**, rather than starting by picking an arbitrary `Character` method.
2. **Choose the processing level**: UTF-16 code unit, Unicode code point, or grapheme cluster.
3. **Pick the exact property**: `isDigit`, `isLetter`, `isAlphabetic`, general category, script, or an appropriate combination.
4. **If handling numeric data**, clarify ASCII-only, Unicode decimal digits, or locale-aware parser; validate the whole string after parsing.
5. **If handling names/identifiers**, consider normalization, combining marks, punctuation, mixed scripts, and spoofing per product policy.
6. **If changing case**, pass the appropriate `Locale` or use `Locale.ROOT` for technical contexts needing locale independence.
7. **If storing/displaying**, separate character classification from output encoding/escaping; `Character` does not automatically guarantee HTML, SQL, or log safety.
8. **If using Unicode properties in security rules**, re-test when upgrading Java/Unicode data.
9. **If RTL and grapheme clusters are needed**, use appropriate algorithmic tools instead of reversing strings or slicing by `char`.

**Takeaway:** In Java, `Character` supports **Unicode classification**, not just ASCII. `isDigit` differs from `getNumericValue`; `isLetter` differs from `isAlphabetic`; `char` differs from **code point**; and checking properties per code point differs from validating **a meaningful string in natural language**. Combining the right APIs with `Locale`, `Normalizer`, parsers, and product policies is the foundation for reliable multilingual text processing.

**Java SE 17 Documentation:** [Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html).
