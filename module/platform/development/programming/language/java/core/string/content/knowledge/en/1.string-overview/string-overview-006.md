# String Operation Categories in Java: Reading, Comparing, Searching, Transforming, and Encoding

In Java, `String` is a reference type representing text. Five common categories of operations include: **reading/extracting**, **comparing**, **searching**, **transforming**, and **converting/encoding**. Each category serves a distinct purpose; choosing the right API keeps code readable and avoids bugs with Unicode, regular expressions, or data from external systems.

## 1. Fundamental rules before operating on strings

1. **`String` is immutable:** `replace()`, `strip()`, `substring()`, and `toUpperCase()` return results without modifying the original string. You must assign `s = s.strip();` if you want to keep the transformed value. If no change occurs, a method may return the same object; do not rely on reference identity to determine content.
2. **Indices are 0-based, end boundary is exclusive:** `"Java".substring(1, 3)` is `"av"`. Invalid index values throw `StringIndexOutOfBoundsException`.
3. **String's index unit is the UTF-16 code unit:** `"🚀".length() == 2` even though the emoji is one Unicode code point. `charAt()` may return half of a surrogate pair; `codePoints()` is more appropriate when iterating by code point. A visible character can also consist of multiple code points, such as a base letter plus a combining accent.
4. **`null` differs from `""`:** `null` has no object; an empty string has `length() == 0`. Calling `length()` or any instance method on null throws `NullPointerException`.
5. **Text differs from bytes:** `String` holds text, whereas `byte[]` holds byte data. Converting between them requires selecting a charset, typically `StandardCharsets.UTF_8`, on both ends.

## 2. Reading and extracting

| Need | Method | Note |
|---|---|---|
| Measure length | `length()` | Number of UTF-16 code units |
| Empty string | `isEmpty()` | `true` only when length is 0 |
| Empty or whitespace-only | `isBlank()` | Uses `Character.isWhitespace` rules |
| Read one code unit | `charAt(index)` | Returns `char` |
| Read one code point | `codePointAt(index)` | Returns `int`; index is still in UTF-16 units |
| Count code points | `codePointCount(begin, end)` | Both bounds are UTF-16 indices |
| Iterate code points | `codePoints()` | Returns `IntStream` |
| Extract slice | `substring(begin, end)` | Takes from begin up to before end |
| Extract as `CharSequence` | `subSequence(begin, end)` | Use when an API accepts `CharSequence` |
| Copy `char` values | `toCharArray()`, `getChars(...)` | Still based on UTF-16 code units |
| Iterate line by line | `lines()` | Returns `Stream<String>` |

~~~java
String s = "Java 🚀";
System.out.println(s.length());                      // 7
System.out.println(s.charAt(0));                     // J
System.out.println(s.substring(0, 4));              // Java
System.out.println(s.codePointCount(0, s.length())); // 6
s.codePoints().forEach(cp -> System.out.print(Character.toString(cp)));
System.out.println();                                // Java 🚀
~~~

To slice by **code point count**, use `offsetByCodePoints()` to compute the UTF-16 position before calling `substring()`:

~~~java
String s = "A🚀B";
int end = s.offsetByCodePoints(0, 2);
System.out.println(s.substring(0, end)); // A🚀
~~~

`s.substring(0, 2)` in this case slices between the two code units of 🚀 and produces a string containing an unpaired surrogate. If you must operate by **grapheme cluster** (user-perceived character), counting code points alone is still insufficient; an appropriate text-segmentation utility is needed.

## 3. Comparing: content, letter case, and ordering

- `a.equals(b)`: compares exact content by code unit and is case-sensitive.
- `a.equalsIgnoreCase(b)`: compares case-insensitively according to Java's Unicode rules; does not replace full natural-language collation.
- `a.compareTo(b)`: compares lexicographical order in UTF-16, returning **negative / 0 / positive**; do not assume it only returns `-1, 0, 1`. `compareToIgnoreCase(b)` ignores letter case.
- `a.contentEquals(charSequence)`: compares content against a `CharSequence` such as `StringBuilder`.
- `a.regionMatches(...)`: compares two subregions, with an overload to ignore case.
- `Objects.equals(a, b)`: compares safely when references may be null.

~~~java
import java.util.Objects;

String a = new String("Java");
String b = "Java";
System.out.println(a == b);                                // false
System.out.println(a.equals(b));                           // true
System.out.println("Java".equalsIgnoreCase("JAVA"));       // true
System.out.println("Java".compareTo("Kotlin"));            // -1
System.out.println(Objects.equals(null, null));           // true
System.out.println("Java".contentEquals(
        new StringBuilder("Java")));                      // true
~~~

**Common mistake:** `==` compares reference identity, **not** content. The string pool can make two literals point to the same object, causing `"abc" == "abc"` to evaluate to true, yet that is not guaranteed for runtime-created strings. Use `"expected".equals(candidate)` or `Objects.equals(...)` when null is possible.

When you need to **sort display names according to a language** such as Vietnamese, use `java.text.Collator` with the appropriate locale instead of relying on `compareTo()`:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
int result = collator.compare("An", "Ánh");
// result is negative, 0, or positive according to the locale's collation rules.
~~~

Collation results depend on locale data, accent/case sensitivity configuration (`strength`), and environment; do not infer language-specific ordering from Unicode code point values.

## 4. Searching substrings and regular expressions

| Method | Result | When to use |
|---|---|---|
| `contains(part)` | `boolean` | Whether a literal substring is present |
| `startsWith(prefix)`, `endsWith(suffix)` | `boolean` | Check prefix/suffix |
| `indexOf(part)` | First occurrence index or `-1` | Find position (UTF-16) |
| `indexOf(part, fromIndex)` | Index or `-1` | Continue searching from a position |
| `lastIndexOf(part)` | Last occurrence index or `-1` | Search from the end |
| `matches(regex)` | `boolean` | **Entire string** matches regex |
| `Pattern` + `Matcher.find()` | `boolean`/groups/positions | A **substring** matches regex |

~~~java
String text = "Java 17, Java 21";
System.out.println(text.contains("Java"));            // true
System.out.println(text.indexOf("Java"));             // 0
System.out.println(text.indexOf("Java", 1));          // 9
System.out.println(text.lastIndexOf("Java"));         // 9
System.out.println(text.startsWith("Java 17"));       // true
System.out.println("ABC123".matches("[A-Z]+\\d+"));   // true
System.out.println("x123y".matches("\\d+"));          // false
~~~

`matches()` requires the regex to match the **entire** string. To find multiple substrings, use `find()`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

Matcher m = Pattern.compile("\\d+").matcher("A12 B345");
while (m.find()) {
    System.out.println(m.group() + " at " + m.start());
}
// 12 at 1
// 345 at 5
~~~

In Java source code, the regex `\d+` must be written as the string `"\\d+"` because the backslash has to be escaped at the Java string level. The dot `.` in regex matches any character per regex rules, not a literal period. If a user supplies text to search for, use `Pattern.quote(userText)` to create a literal regex pattern. If you are only searching for literal text, `contains()`/`indexOf()` are usually shorter and clearer than regex.

## 5. Transforming content

### 5.1. Concatenating, joining, and repeating

`+` or `concat()` concatenates strings. `String.join(delimiter, elements...)` joins parts with a delimiter. `repeat(n)` repeats `n` times (negative `n` throws `IllegalArgumentException`). With many concatenations in a large loop, `StringBuilder.append()` reduces intermediate string creation; `StringBuilder` is mutable, so do not share it across multiple threads for concurrent modification without synchronization.

~~~java
System.out.println("Java".concat(" 17"));                // Java 17
System.out.println(String.join(" | ", "read", "find", "replace")); // read | find | replace
System.out.println("ha".repeat(3));                     // hahaha

StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) builder.append(", ");
    builder.append(i);
}
System.out.println(builder); // 1, 2, 3
~~~

### 5.2. Literal replacement vs. regex replacement

- `replace(char, char)` and `replace(CharSequence, CharSequence)`: replace **literal** values.
- `replaceAll(regex, replacement)`: replaces all matches of **regex**. The replacement supports group-reference syntax like `$1`.
- `replaceFirst(regex, replacement)`: replaces the first match.

~~~java
System.out.println("a.b".replace(".", "-"));           // a-b
System.out.println("a.b".replaceAll(".", "-"));        // ---
System.out.println("a12b34".replaceAll("\\d+", "#"));  // a#b#
System.out.println("1 2 3".replaceFirst("\\d", "X"));  // X 2 3
~~~

When the replacement comes from user input, use `Matcher.quoteReplacement(replacement)` to prevent `$` or backslashes from being interpreted as special syntax. For literal data, prefer `replace(old, new)` to reduce errors.

### 5.3. Whitespace, letter case, and Unicode

`strip()`, `stripLeading()`, and `stripTrailing()` remove whitespace according to `Character.isWhitespace`; `trim()` only removes leading/trailing code units with values from U+0000 to U+0020, so there are cases where it differs from `strip()`.

`toUpperCase(locale)` and `toLowerCase(locale)` apply locale rules. When representing language-independent machine keys where the specification permits simple case folding, explicitly use `Locale.ROOT`. For display text, use the appropriate locale. Changing case can alter the code point count or string length.

`java.text.Normalizer` is used to normalize Unicode representations. Two visually identical strings can differ in code points, such as precomposed `é` versus `e` plus a combining acute accent:

~~~java
import java.text.Normalizer;
import java.util.Locale;

String raw = "  Java  ";
System.out.println("[" + raw.trim() + "]");              // [Java]
System.out.println("[" + raw.strip() + "]");             // [Java]
System.out.println("java".toUpperCase(Locale.ROOT));     // JAVA

String composed = "\u00E9";
String decomposed = "e\u0301";
System.out.println(composed.equals(decomposed));          // false
System.out.println(composed.equals(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC))); // true
~~~

NFC normalizes canonically equivalent Unicode representations, but it does not equate every pair of visually similar words. For multi-line text, Java also provides `indent()`, `stripIndent()`, and `translateEscapes()`; read the newline/escape rules carefully before applying them.

## 6. Data type conversion, charsets, and encoding formats

### 6.1. Java values ↔ String

`String.valueOf(42)` creates `"42"`; `String.valueOf(true)` creates `"true"`; `String.valueOf((Object)null)` creates the **character string** `"null"`, distinct from a null reference.

`Integer.parseInt()`, `Long.parseLong()`, and `Double.parseDouble()` convert strings to numbers and may throw `NumberFormatException`. `Boolean.parseBoolean()` returns true when equal to `"true"` case-insensitively; all other values return false.

~~~java
import java.util.Locale;

int count = Integer.parseInt("42");
String number = String.valueOf(count);
String code = String.format(Locale.ROOT, "ITEM-%04d", count);
System.out.println(number); // 42
System.out.println(code);   // ITEM-0042
~~~

`String.format(Locale, format, args)` lets you specify a locale explicitly, which is very useful when text sent across systems must remain consistent. `"ITEM-%04d".formatted(42)` is concise syntax, but it uses the default locale. `Integer.parseInt("12.5")` is invalid. `Double.parseDouble` uses Java's decimal point syntax and does not automatically interpret locale comma formatting; for locale-formatted data, consider `NumberFormat` and validate the entire input.

### 6.2. Text ↔ bytes: charsets

Encoding maps Unicode to bytes; decoding converts bytes back to text. Both directions must agree on the charset. Typically choose `StandardCharsets.UTF_8` to avoid depending on the JVM/OS default charset.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào 🚀";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
System.out.println(bytes.length);                       // 14
System.out.println(message.equals(restored));          // true
System.out.println(HexFormat.of().formatHex(
        "A".getBytes(StandardCharsets.UTF_8)));         // 41
~~~

Byte length differs from `String` length: `à` is 2 bytes in UTF-8, and 🚀 is 4 bytes in UTF-8 but 2 UTF-16 code units. Decoding UTF-8 bytes with the wrong charset can cause display corruption. Some convenience conversion APIs replace invalid data with replacement characters; to **reject** invalid encoded input, create a `CharsetDecoder`/`CharsetEncoder` with `CodingErrorAction.REPORT` and handle `CharacterCodingException`.

### 6.3. Base64, hex, and URL encoding serve different purposes from charsets

| Problem | API | Meaning |
|---|---|---|
| Unicode ↔ bytes | `getBytes(UTF_8)`, `new String(bytes, UTF_8)` | Charset encoding/decoding |
| Bytes ↔ Base64 | `Base64.getEncoder()/getDecoder()` | Represent bytes using ASCII characters |
| Bytes ↔ hex | `HexFormat` (Java 17+) | Represent each byte as two hexadecimal digits |
| Form/query parameter values | `URLEncoder.encode(text, UTF_8)` / `URLDecoder.decode(...)` | `application/x-www-form-urlencoded` rules; spaces become `+` |
| Unicode code point ↔ text | `codePointAt()`, `Character.toString(int)` | Unicode manipulation, not byte charsets |

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] data = "Java".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(data);
String decoded = new String(Base64.getDecoder().decode(encoded),
                            StandardCharsets.UTF_8);
System.out.println(encoded); // SmF2YQ==
System.out.println(decoded); // Java
~~~

Base64, hex, and URL encoding **do not secure data** because they are reversible. `URLEncoder` encodes according to form rules, not as a tool for arbitrarily encoding entire URLs or all path segments.

## 7. Combined example: standalone runnable file on Java 17+

Save the code below in a UTF-8 file `StringOperationsDemo.java`. Earlier snippets illustrate individual APIs separately and may need to be placed inside a class/method if run on their own.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class StringOperationsDemo {
    public static void main(String[] args) {
        String data = "  Java Java 🚀  ";

        // Read
        System.out.println("len=" + data.length());
        System.out.println("strip=[" + data.strip() + "]");
        System.out.println("charAt2=" + data.charAt(2));
        System.out.println("substring=" + data.substring(2, 6));
        System.out.println("codePointsEmoji=" +
                "🚀".codePointCount(0, "🚀".length()));

        // Compare
        System.out.println("equals=" + "Java".equals(new String("Java")));
        System.out.println("compareTo=" + "Java".compareTo("Kotlin"));

        // Search
        System.out.println("indexOf=" + data.indexOf("Java"));
        System.out.println("lastIndexOf=" + data.lastIndexOf("Java"));
        System.out.println("contains=" + data.contains("Java"));

        // Transform
        System.out.println("replace=" + data.strip().replace("Java", "Core"));
        System.out.println("replaceAll=" + "a12b34".replaceAll("\\d+", "#"));
        System.out.println("upper=" + "java".toUpperCase(Locale.ROOT));
        Matcher m = Pattern.compile("\\d+").matcher("A12 B345");
        while (m.find()) {
            System.out.println("match=" + m.group() + "@" + m.start());
        }

        // Convert & encode
        byte[] utf8 = "Xin chào 🚀".getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("decode=" + new String(utf8, StandardCharsets.UTF_8));
        String nfc = Normalizer.normalize("e\u0301", Normalizer.Form.NFC);
        System.out.println("nfcEqual=" + nfc.equals("\u00E9"));
    }
}
~~~

Compile/run commands:

~~~bash
javac -encoding UTF-8 StringOperationsDemo.java
java StringOperationsDemo
~~~

Expected output:

~~~text
len=16
strip=[Java Java 🚀]
charAt2=J
substring=Java
codePointsEmoji=1
equals=true
compareTo=-1
indexOf=2
lastIndexOf=7
contains=true
replace=Core Core 🚀
replaceAll=a#b#
upper=JAVA
match=12@1
match=345@5
utf8Bytes=14
decode=Xin chào 🚀
nfcEqual=true
~~~

`javac -encoding UTF-8` specifies the **source code** encoding, whereas `StandardCharsets.UTF_8` specifies the **program data** encoding. These are two separate purposes.

## 8. API selection table and common mistakes

| When you need… | Choose… | Avoid… |
|---|---|---|
| Check empty/blank | `isEmpty()`, `isBlank()` | Ignoring `null` |
| Exact text equality | `equals()` | Using `==` because of the string pool |
| Null-safe equality | `Objects.equals()` | Calling instance methods on null |
| Vietnamese display sorting | `Collator` and locale | Expecting `compareTo()` to sort by language rules |
| Find a literal | `contains()`, `indexOf()` | Unnecessary regex |
| Find pattern matches | `Pattern` + `Matcher.find()` | Confusing `matches()` with substring search |
| Literal replacement | `replace()` | Mistakenly assuming `replaceAll()` treats `.` as a literal dot |
| Strip leading/trailing whitespace | `strip()` | Thinking `trim()` is always equivalent |
| Concatenate in a loop | `StringBuilder` | Repeated `+` creating many strings |
| Slice by code points | `offsetByCodePoints()` | Splitting a surrogate pair in half |
| Canonical Unicode equality | `Normalizer` NFC when needed | Concluding `equals` from visual appearance alone |
| Change case for machine keys | `Locale.ROOT` when spec-appropriate | Depending on default locale |
| String ↔ bytes | Explicitly specified UTF-8 | Confusing `length()` with byte count |
| Represent bytes as ASCII text | Base64/hex | Treating it as a security technique |

### Application checklist

1. Identify the need: reading, content comparison, locale ordering, literal search, regex, transformation, or encoding.
2. Identify the unit being manipulated: UTF-16 code unit, code point, grapheme cluster, or byte. These units are different.
3. Handle null, empty/whitespace cases, invalid indices, number parsing errors, and special regex input.
4. Prefer direct, self-explanatory APIs: `equals()` for content, `replace()` for literals, `Matcher.find()` for regex matches, and explicit UTF-8 when transferring bytes.
5. Test edge cases: accented Vietnamese text, emojis, combining characters, multi-line text, letter case, mismatched charsets, and invalid byte data.

Once you clearly understand these five categories, you will choose text-processing approaches with clear intent, handle tricky Unicode cases accurately, and keep code maintainable as programs grow.