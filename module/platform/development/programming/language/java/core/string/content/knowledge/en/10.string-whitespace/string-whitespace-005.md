# Non-Breaking Spaces Are Not Always Removed by `String.strip()`

## 1. Goal and key phenomenon to remember

In Java 11+ (including Java 17), `String.strip()` removes characters classified by `Character.isWhitespace(...)` as whitespace **at the start and end of a string**. The method name easily misleads people into thinking it deletes **every** kind of character that looks like a space. In reality, several **non-breaking spaces** (*non-breaking spaces*) are kept intact.

For example:

```java
String text = "\u00A0Java\u00A0"; // NBSP + Java + NBSP
System.out.println(text.strip().equals(text)); // true
System.out.println(text.isBlank());             // false
```

The two spaces on either side have Unicode code point **U+00A0 NO-BREAK SPACE**, not the ASCII space U+0020. `strip()` keeps them intact, and `isBlank()` does not treat a string containing only NBSP as “blank.”

This lesson helps you:
- Distinguish **visible spaces**, **Unicode space characters**, and characters Java treats as `whitespace`.
- Understand the differences among `strip()`, `trim()`, `isBlank()`, and `Character.isSpaceChar()`.
- Properly handle NBSP, FIGURE SPACE, and NARROW NO-BREAK SPACE when cleaning text.
- Choose an appropriate whitespace-removal policy so you do not alter data meaning.

## 2. What are non-breaking spaces?

In typeset text, some spaces are meant to **keep two pieces of text on the same line**. For instance, the space between a number and its unit in `"10 kg"` is sometimes written with NBSP to prevent a line break between `10` and `kg`.

Three common code points:

| Code point | Unicode name | Characteristics |
| --- | --- | --- |
| `U+00A0` | NO-BREAK SPACE (NBSP) | Common non-breaking space; HTML has the `&nbsp;` entity. |
| `U+2007` | FIGURE SPACE | Space with the width of a digit, non-breaking. |
| `U+202F` | NARROW NO-BREAK SPACE | Narrower non-breaking space; appears in certain typesetting conventions. |

They are often hard to distinguish visually from an ordinary space. When copying from HTML, PDFs, word processors, or typeset content, strings can contain these code points even when users think there is only a “space.”

**Note:** These characters are meaningful text data. Depending on business rules, arbitrarily deleting or converting all NBSPs into ordinary spaces can break presentation intent or formatting rules.

## 3. Why doesn't `strip()` remove all spaces?

By Java's contract, `String.strip()` determines which characters to remove using **`Character.isWhitespace(int)`**. In Java 17, `Character.isWhitespace` returns `false` for the three non-breaking characters `U+00A0`, `U+2007`, and `U+202F`.

This differs from `Character.isSpaceChar(int)`, which returns `true` for characters in the Unicode space separator categories, including those three cases.

Notable results table in Java 17:

| Character | `Character.isWhitespace(cp)` | `Character.isSpaceChar(cp)` | Can `strip()` remove it at start/end? |
| --- | --- | --- | --- |
| `U+0020` SPACE | `true` | `true` | Yes |
| `U+0009` TAB | `true` | `false` | Yes |
| `U+00A0` NO-BREAK SPACE | `false` | `true` | **No** |
| `U+2007` FIGURE SPACE | `false` | `true` | **No** |
| `U+202F` NARROW NO-BREAK SPACE | `false` | `true` | **No** |
| `U+2003` EM SPACE | `true` | `true` | Yes |
| `U+3000` IDEOGRAPHIC SPACE | `true` | `true` | Yes |

The difference is clear in these three snippets:

```java
System.out.println("\u2003Java\u2003".strip().equals("Java")); // true
System.out.println("\u00A0Java\u00A0".strip().equals("Java")); // false
System.out.println("\u00A0Java\u00A0".strip()
        .equals("\u00A0Java\u00A0"));                       // true
```

You cannot conclude that `strip()` will remove a character just because its Unicode name contains “SPACE” or because it renders like whitespace.

### A surprising case: mixing SPACE and NBSP

```java
String mixed = " \u00A0Java\u00A0 ";
String result = mixed.strip();

System.out.println(result.equals("\u00A0Java\u00A0")); // true
```

`strip()` removes the outermost ASCII spaces `U+0020`. Then, upon hitting NBSP `U+00A0` at the start and end of the remaining region, it **stops** because NBSP does not satisfy `Character.isWhitespace`. As a result, a string on which `strip()` has been called can still start or end with a non-breaking space.

## 4. Distinguishing checks when encountering NBSP

`strip()` only trims code points recognized by `Character.isWhitespace` at both edges; `stripLeading()` and `stripTrailing()` trim only one side. `isBlank()` inspects the whole string using the same Java whitespace criterion, so neither `strip()` nor `isBlank()` **treats NBSP as ignorable whitespace**. `trim()` trims code units `char <= U+0020`, so it preserves NBSP as well.

~~~java
String nbsp = "\u00A0";
String em = "\u2003";
System.out.println(nbsp.strip().isEmpty()); // false
System.out.println(nbsp.isBlank());         // false
System.out.println(em.strip().isEmpty());   // true
System.out.println(em.trim().isEmpty());    // false
~~~

These two pairs of results help distinguish **non-breaking spaces** from EM SPACE and `trim()`'s specific limitation. If you only need to detect empty or *Java whitespace*-only input, use `isBlank()`; if you need to accept or also trim NBSP at the boundaries, apply a business-contract predicate as shown in Section 7.

## 5. Standalone Java 17+ example that shows code points clearly

Because NBSP is hard to see visually, the example below **prints Unicode code points** instead of just printing spaces so the result can be verified.

Save as `NonBreakingSpaceDemo.java`:

```java
import java.util.stream.Collectors;

public class NonBreakingSpaceDemo {
    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String ascii = "\t Java \n";
        String nbsp = "\u00A0Java\u00A0";
        String emSpace = "\u2003Java\u2003";
        String mixed = " \u00A0Java\u00A0 ";

        System.out.println("ASCII strip = "
                + codePoints(ascii.strip()));
        System.out.println("NBSP strip = "
                + codePoints(nbsp.strip()));
        System.out.println("EM SPACE strip = "
                + codePoints(emSpace.strip()));
        System.out.println("mixed strip = "
                + codePoints(mixed.strip()));

        System.out.println("NBSP only isBlank = "
                + "\u00A0".isBlank());
        System.out.println("EM SPACE only isBlank = "
                + "\u2003".isBlank());
        System.out.println("NBSP trim unchanged = "
                + nbsp.trim().equals(nbsp));

        int[] samples = {
            0x0020, 0x0009, 0x00A0,
            0x2007, 0x202F, 0x2003
        };
        for (int cp : samples) {
            System.out.printf(
                    "U+%04X whitespace=%s spaceChar=%s%n",
                    cp,
                    Character.isWhitespace(cp),
                    Character.isSpaceChar(cp));
        }
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 NonBreakingSpaceDemo.java
java NonBreakingSpaceDemo
```

Output:

```text
ASCII strip = U+004A U+0061 U+0076 U+0061
NBSP strip = U+00A0 U+004A U+0061 U+0076 U+0061 U+00A0
EM SPACE strip = U+004A U+0061 U+0076 U+0061
mixed strip = U+00A0 U+004A U+0061 U+0076 U+0061 U+00A0
NBSP only isBlank = false
EM SPACE only isBlank = true
NBSP trim unchanged = true
U+0020 whitespace=true spaceChar=true
U+0009 whitespace=true spaceChar=false
U+00A0 whitespace=false spaceChar=true
U+2007 whitespace=false spaceChar=true
U+202F whitespace=false spaceChar=true
U+2003 whitespace=true spaceChar=true
```

**Explanation:**
1. The string with TAB `U+0009`, SPACE `U+0020`, and LINE FEED `U+000A` has whitespace at both ends removed by `strip()`, leaving only `Java`.
2. The string with NBSP at both ends still contains two `U+00A0` code points after `strip()`.
3. EM SPACE `U+2003` is recognized by `Character.isWhitespace` and is removed.
4. With `mixed`, `strip()` removes the outer SPACEs and preserves the NBSPs right next to the letters.
5. `"\u00A0".isBlank()` is `false` even though in the UI the string may look like blank space.

## 6. When should NBSP be preserved?

NBSP is not always “dirty” data. It can be used to:
- Keep numbers and units on the same line, such as `"10 km"` or `"25 °C"`.
- Keep currencies and values on the same line per presentation conventions.
- Keep parts of a proper name or phrase together as intentionally typeset.
- Represent non-breaking whitespace from HTML via the `&nbsp;` entity.

Distinguish two tasks:

**Cleaning input to extract a business value:** If a form allows users to paste data containing NBSP at the **start/end**, you may intentionally treat NBSP as boundary whitespace and remove it.

**Preserving text content:** If the application processes presentation content, documents, or records requiring integrity, keep special spaces unless requirements explicitly permit normalizing them.

There is no single “correct” method for both goals. Before normalizing, answer: **Do we want to remove boundary whitespace, or alter all internal whitespace?** Replacing inside the string can change typesetting semantics.

## 7. How to remove NBSP at boundaries as well if required by business logic

If the policy is “remove all characters Java treats as whitespace **or** Unicode space characters at both ends,” you can combine `Character.isWhitespace` and `Character.isSpaceChar`.

Example Java 17 helper methods:

```java
static boolean boundarySpace(int codePoint) {
    return Character.isWhitespace(codePoint)
            || Character.isSpaceChar(codePoint);
}

static String stripBoundarySpaces(String text) {
    java.util.Objects.requireNonNull(text, "text");

    int begin = 0;
    int end = text.length();

    while (begin < end) {
        int cp = text.codePointAt(begin);
        if (!boundarySpace(cp)) {
            break;
        }
        begin += Character.charCount(cp);
    }

    while (begin < end) {
        int cp = text.codePointBefore(end);
        if (!boundarySpace(cp)) {
            break;
        }
        end -= Character.charCount(cp);
    }

    return text.substring(begin, end);
}
```

These are **methods that must be placed inside a Java class**, not a standalone program with `main`. Example calls inside `main`:

```java
String input = "\u00A0\u202FJava\u2007\u00A0";

System.out.println(input.strip().equals(input)); // true
System.out.println(stripBoundarySpaces(input)
        .equals("Java"));                         // true

String meaningful = "10\u00A0kg";
System.out.println(stripBoundarySpaces(meaningful)
        .equals(meaningful));                     // true
```

**Why use `codePointAt` and `codePointBefore`?** These two methods allow scanning both ends of the string by code point and using `Character.charCount(cp)` to advance or step back the exact number of UTF-16 `char`s. In the NBSP examples, the code points are in the BMP, yet this implementation makes the unit of operation explicit and works for any Unicode input within the policy's scope.

**Limitations to understand:**
- `isWhitespace || isSpaceChar` is **an explicit policy chosen by the application**; it is not the sole definition of “whitespace” across all standards and languages.
- The method removes characters only at **both ends**; it does not delete or replace NBSP **in the middle**, such as in `"10\u00A0kg"`.
- For text containing lone surrogates (incomplete UTF-16 strings), the method does not automatically repair such data.
- When strict adherence to a specific Unicode version or external standard is required, explicitly define the allowed code point set and write tests for that set.

### If you only want to remove regular NBSP at both ends

You can choose a narrower policy than `boundarySpace`, for example treating only `U+00A0` in addition to what `strip()` already removes. That is an appropriate choice if the application needs to keep `U+2007` and `U+202F` for layout purposes.

Do not blindly replace all special spaces with an ASCII space just because users see them as looking alike.

## 8. Using Unicode regex when the contract includes NBSP

If the policy explicitly states “remove characters belonging to Unicode White_Space at the start/end,” Java regex with the `(?U)` flag is one option. By default `\s` does not cover NBSP, whereas `(?U)\s` also recognizes NBSP and several other Unicode characters.

~~~java
String nbsp = "\u00A0Hello\u00A0";
String cleaned = nbsp.replaceAll("(?U)\\A\\s+|\\s+\\z", "");
System.out.println(cleaned.equals("Hello")); // true
~~~

The two anchors `\A` and `\z` ensure removal only at **both ends of the entire string**, without replacing meaningful NBSPs between words. Unicode White_Space also differs from the union `Character.isWhitespace || Character.isSpaceChar` in Section 7: for example, U+0085 belongs to Unicode White_Space yet is not recognized by those two `Character` APIs. Test against the exact character set your business logic requires and keep original data if recovery is needed.

## 9. Should Unicode normalization be used to “remove whitespace”?

`java.text.Normalizer` is for normalizing Unicode forms, not a dedicated API for stripping leading/trailing whitespace.

For example, compatibility normalization `NFKC` can turn NBSP `U+00A0` into SPACE `U+0020`:

```java
String nbsp = "\u00A0";
String nfkc = java.text.Normalizer.normalize(
        nbsp, java.text.Normalizer.Form.NFKC);
System.out.println(nfkc.equals(" ")); // true
```

However, **do not automatically run NFKC on every input just to deal with NBSP**. Compatibility normalization can alter many other kinds of characters and erase typographic or formatting distinctions the application needs to keep.

If you only need to handle boundary whitespace, a better approach is to define the boundary character set and strip **only the region that needs stripping**. If business requirements call for normalizing all text with NFKC, apply it as a separate policy and thoroughly test all of its consequences.

## 10. Common pitfalls

| Misconception | Actual problem | How to handle it |
| --- | --- | --- |
| “`strip()` removes all spaces.” | `U+00A0`, `U+2007`, `U+202F` can still remain at edges. | Check `Character.isWhitespace` and application policy. |
| “`trim()` definitely removes more than `strip()`.” | `trim()` mainly relies on code units `<= U+0020` and does not handle NBSP. | Use APIs by their contract, not their name. |
| “With NBSP present, `isBlank()` must return `true`.” | `isBlank()` also relies on `Character.isWhitespace`. | If you want a broader blank definition, check using your chosen predicate. |
| “If it looks empty, the string is empty.” | NBSP has real length, e.g., `"\u00A0".length() == 1`. | Print code points when debugging. |
| “Replacing all NBSPs with SPACE is always safe.” | Can lose non-breaking behavior, affecting layout. | Normalize only under an explicit policy. |
| “Default `\s` in regex always catches NBSP.” | The character set depends on `Pattern`'s Unicode flag. | Use `(?U)` when Unicode regex is needed and tested. |
| “`NFKC` only changes NBSP.” | It is a compatibility normalization affecting many characters. | Do not use NFKC as a whitespace-cleaning trick if unnecessary. |

### How to diagnose a string that looks like it has spaces

Do not just print `System.out.println(text)` directly. When you need to identify special characters, print the code point values:

```java
String input = "\u00A0Hi\u202F";
input.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Output:

```text
U+00A0
U+0048
U+0069
U+202F
```

This inspection shows exactly why a string **appears trimmed/stripped yet still contains whitespace at both ends**.

## 11. Self-check quiz

### Question 1

```java
String s = "\u00A0";
System.out.println(s.isBlank());
System.out.println(s.strip().isEmpty());
```

**Answer:** `false` and `false`. `U+00A0` does not satisfy `Character.isWhitespace`, so `strip()` does not remove it, and `isBlank()` does not consider this string blank.

### Question 2

```java
String s = "\u2003Java\u2003";
System.out.println(s.trim().equals(s));
System.out.println(s.strip().equals("Java"));
```

**Answer:** `true` and `true`. `trim()` does not remove EM SPACE `U+2003`, whereas `strip()` does because `Character.isWhitespace(0x2003)` is `true`.

### Question 3

```java
String s = " \u00A0A\u00A0 ";
System.out.println(s.strip()
        .equals("\u00A0A\u00A0"));
```

**Answer:** `true`. `strip()` removes the outer ASCII SPACEs and stops upon hitting NBSP.

### Question 4

A product needs to strip NBSP at the start/end of a name field pasted from HTML, while preserving the non-breaking space between number and unit in `"10\u00A0kg"`. What should be done?

**Answer:** Apply a **boundary-only removal** rule (such as `stripBoundarySpaces` above); do not run `replace("\u00A0", " ")` across the entire text. Test both boundary NBSPs and meaningful internal NBSPs.

### Question 5

In Java 17, do `Character.isSpaceChar(0x00A0)` and `Character.isWhitespace(0x00A0)` return the same result?

**Answer:** No. `isSpaceChar(0x00A0) == true` while `isWhitespace(0x00A0) == false`. This is why NBSP is not removed by `strip()`.

## 12. Summary

- `String.strip()` (Java 11+) removes **`Character.isWhitespace` at both ends**, not every Unicode space character.
- Three important non-breaking spaces are **NBSP `U+00A0`**, **FIGURE SPACE `U+2007`**, and **NARROW NO-BREAK SPACE `U+202F`**; in Java 17 they are recognized by `isSpaceChar` but not by `isWhitespace`.
- `trim()` does not remove NBSP either; `isBlank()` can return `false` for a string containing only NBSP.
- If business requirements call for also removing non-breaking spaces at the **start/end**, explicitly define a boundary predicate or use a Unicode-aware regex with appropriate tests.
- Do not delete internal NBSPs or apply compatibility normalization arbitrarily; non-breaking spaces may carry layout meaning.

## References

- [Java SE 17 — `String.strip()`, `stripLeading()`, `stripTrailing()`, and `isBlank()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character.isWhitespace` and `Character.isSpaceChar`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Java SE 17 — `Pattern` and `UNICODE_CHARACTER_CLASS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Standard — Unicode Character Database](https://www.unicode.org/ucd/)