# Prefix and Suffix Search with `startsWith`, `startsWith(prefix, offset)`, and `endsWith` in Java

When you need to determine whether a `String` begins or ends with a given sequence of characters, Java provides three direct methods: `startsWith(String prefix)`, `startsWith(String prefix, int toffset)`, and `endsWith(String suffix)`. All three return a `boolean` and **compare character content at fixed positions** without modifying the source string.

The most common point of confusion lies in the overload with `toffset`: it checks whether the prefix **starts strictly at index `toffset` in the source string**, rather than searching for the prefix at an arbitrary position from `toffset` onward.

## 1. Meaning of the Three Methods

| Method | What does it check? | Example |
| --- | --- | --- |
| `text.startsWith(prefix)` | Does `prefix` appear right at the **start** of `text` (index 0)? | `"banana".startsWith("ban")` → `true` |
| `text.startsWith(prefix, toffset)` | Does `prefix` match **starting right at index `toffset`** in `text`? | `"banana".startsWith("ana", 1)` → `true` |
| `text.endsWith(suffix)` | Does `suffix` appear right at the **end** of `text`? | `"banana".endsWith("ana")` → `true` |

Public signatures in class `java.lang.String`:

```java
public boolean startsWith(String prefix)
public boolean startsWith(String prefix, int toffset)
public boolean endsWith(String suffix)
```

These are method signatures for reference, not a standalone runnable program.

All three check **a contiguous substring**. The string can be longer than the prefix/suffix. For example, `"Spring Boot"` starts with `"Spring"` even though more characters follow; `"file.txt"` ends with `".txt"` even though a file name precedes the suffix.

## 2. `startsWith(String prefix)`: Checking at the Start of the String

Basic example:

```java
String text = "Java Core";

System.out.println(text.startsWith("Java"));   // true
System.out.println(text.startsWith("Ja"));     // true
System.out.println(text.startsWith("Core"));   // false
System.out.println(text.startsWith("Java Core")); // true
System.out.println(text.startsWith("Java Core!")); // false
```

The statements above are an illustrative snippet placed inside a Java method.

A prefix can equal the entire string content: `text.startsWith(text)` returns `true`. Conversely, a prefix longer than the source string cannot match. The method does not skip whitespace, does not fold case, and does not strip newline characters.

Runnable file `StartsWithBasics.java`:

```java
public class StartsWithBasics {
    public static void main(String[] args) {
        String text = "banana";

        System.out.println("ban: " + text.startsWith("ban"));
        System.out.println("ana at start: " + text.startsWith("ana"));
        System.out.println("whole: " + text.startsWith("banana"));
        System.out.println("longer: " + text.startsWith("bananas"));
        System.out.println("uppercase: " + text.startsWith("Ban"));
        System.out.println("suffix ana: " + text.endsWith("ana"));
        System.out.println("suffix ban: " + text.endsWith("ban"));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StartsWithBasics.java
java StartsWithBasics
```

Output:

```text
ban: true
ana at start: false
whole: true
longer: false
uppercase: false
suffix ana: true
suffix ban: false
```

Here `"ana"` does exist in `"banana"`, yet `startsWith("ana")` is still `false` because `"ana"` is not at the **start of the string**. If the goal is to check whether it appears **anywhere**, use `contains(...)` or `indexOf(...)` for a different search purpose.

## 3. `startsWith(String prefix, int toffset)`: Checking at a Specific Boundary

The two-parameter overload has the syntax:

```java
boolean matched = text.startsWith(prefix, toffset);
```

`toffset` is a **UTF-16 code unit index in `text`**, marking the position of the first character that must match `prefix`. If the prefix has length `m`, the method must match exactly `m` consecutive code units starting at index `toffset`.

For example, in `"banana"`:

```text
String:      b a n a n a
Index:       0 1 2 3 4 5
             | | | | | |
"ana" at 1:    a n a
"ana" at 3:        a n a
```

Therefore:

- `"banana".startsWith("ana", 0)` → `false`; the start of the string is `"ban"`.
- `"banana".startsWith("ana", 1)` → `true`; from position 1 it is `"ana..."`.
- `"banana".startsWith("ana", 2)` → `false`; from position 2 it is `"nan..."`.
- `"banana".startsWith("ana", 3)` → `true`; the last three characters are `"ana"`.

File `StartsWithOffsetDemo.java`:

```java
public class StartsWithOffsetDemo {
    public static void main(String[] args) {
        String text = "banana";

        for (int offset = 0; offset <= text.length(); offset++) {
            System.out.printf("offset %d: %b%n",
                    offset, text.startsWith("ana", offset));
        }

        System.out.println("offset -1: " + text.startsWith("ana", -1));
        System.out.println("offset 7: " + text.startsWith("ana", 7));
    }
}
```

Run:

```bash
javac -encoding UTF-8 StartsWithOffsetDemo.java
java StartsWithOffsetDemo
```

Output:

```text
offset 0: false
offset 1: true
offset 2: false
offset 3: true
offset 4: false
offset 5: false
offset 6: false
offset -1: false
offset 7: false
```

If `toffset` is negative, exceeds the string length, or does not leave enough characters to hold all of `prefix`, the result is `false` (for a non-`null` `prefix`). This is a **failed match result**, not a call that throws `IndexOutOfBoundsException` whenever `toffset` is out of range. An empty prefix has its own valid boundary rule explained in a later section.

### Very Common Mistake: `offset` Is Not a Search Starting Position

Example:

```java
String text = "abaXaba";

System.out.println(text.startsWith("aba", 1)); // false
System.out.println(text.indexOf("aba", 1));     // 4
```

`startsWith("aba", 1)` only checks the three characters **strictly at position 1** (`"baX"`), so it returns `false`. `indexOf("aba", 1)` searches **from index 1 onward** and returns position 4 when found. These two methods are not interchangeable.

If you need to match a label located after a fixed-length header, `startsWith(prefix, offset)` is a great fit:

```java
String line = "2026-10-22 ERROR: connection lost";

System.out.println(line.startsWith("ERROR:", 11)); // true
System.out.println(line.startsWith("ERROR:", 10)); // false
```

With the data above, the first character `E` of `ERROR:` is at index 11. However, when the header has variable length, do not guess a fixed offset: find the appropriate anchor with `indexOf` or parse the data structure first.

## 4. `endsWith(String suffix)`: Checking the Ending

`endsWith(suffix)` returns `true` if the trailing code units of the source string equal all of `suffix`. The method takes no offset parameter because the position is determined from the **end of the source string**.

```java
String file = "report.csv";

System.out.println(file.endsWith(".csv"));  // true
System.out.println(file.endsWith("csv"));   // true
System.out.println(file.endsWith(".txt"));  // false
System.out.println(file.endsWith("report.csv")); // true
System.out.println(file.endsWith("REPORT.CSV")); // false
```

The suffix can equal the entire string. If the suffix is longer than the string, the result is `false`. The check has no awareness of file extensions, URLs, or MIME types; it purely compares characters.

Semantically, for a non-`null` `suffix`, you can think of the check:

```java
text.endsWith(suffix)
```

as equivalent in result to:

```java
text.startsWith(suffix, text.length() - suffix.length())
```

If the suffix is longer than the string, `text.length() - suffix.length()` is negative and the check starting at a negative offset fails. This is a mental model for understanding where the check occurs, **not a requirement to rewrite `endsWith`** in application code.

## 5. Empty Prefix and Suffix: Boundary Cases

The empty string `""` is a valid prefix and suffix of **every `String`**.

```java
String text = "Java";
String empty = "";

System.out.println(text.startsWith(empty)); // true
System.out.println(text.endsWith(empty));   // true
System.out.println(empty.startsWith(empty)); // true
System.out.println(empty.endsWith(empty));  // true
```

With the offset overload, an empty prefix matches at **every valid boundary from 0 to `text.length()`**, including the trailing boundary:

| Call with `text = "Java"` (length 4) | Result | Explanation |
| --- | --- | --- |
| `text.startsWith("", 0)` | `true` | Empty prefix at start boundary |
| `text.startsWith("", 2)` | `true` | Empty prefix at middle boundary |
| `text.startsWith("", 4)` | `true` | Empty prefix at end boundary |
| `text.startsWith("", -1)` | `false` | Invalid negative offset |
| `text.startsWith("", 5)` | `false` | Offset greater than length |
| `text.startsWith("J", 4)` | `false` | No code units left for a non-empty prefix |

This resembles an empty interval `[k, k)` at a valid boundary: because zero characters need to match, the result is `true`. Do not automatically equate `startsWith("") == true` with the string containing data; even an empty source string returns `true`.

File `EmptyPrefixSuffix.java` helps verify this thoroughly:

```java
public class EmptyPrefixSuffix {
    public static void main(String[] args) {
        String text = "Java";

        System.out.println("empty prefix: " + text.startsWith(""));
        System.out.println("empty suffix: " + text.endsWith(""));
        System.out.println("at length: "
                + text.startsWith("", text.length()));
        System.out.println("after length: "
                + text.startsWith("", text.length() + 1));
        System.out.println("nonempty at length: "
                + text.startsWith("a", text.length()));
        System.out.println("empty source: "
                + "".startsWith(""));
    }
}
```

Compile:

```bash
javac -encoding UTF-8 EmptyPrefixSuffix.java
java EmptyPrefixSuffix
```

Output:

```text
empty prefix: true
empty suffix: true
at length: true
after length: false
nonempty at length: false
empty source: true
```

If you require a prefix/suffix **to be non-empty**, validate `!prefix.isEmpty()` or `!suffix.isEmpty()` before checking. The API's default behavior is intentional and consistent.

## 6. Case-Sensitive Comparison and No Automatic Unicode Normalization

All three methods compare **exact sequences of UTF-16 code units**. They do not automatically:

- ignore uppercase/lowercase differences;
- trim leading/trailing whitespace;
- handle canonically equivalent Unicode variants;
- execute regular expressions (regex), `*` wildcards, or `?`;
- interpret text according to natural language rules.

Example:

```java
String name = "Readme.md";

System.out.println(name.startsWith("read")); // false
System.out.println(name.endsWith(".MD"));    // false
System.out.println(name.endsWith(".md"));    // true
```

If business logic **for ASCII data** wants case-insensitive comparison, you can convert both sides using the same rule, such as `toLowerCase(Locale.ROOT)`. However, full Unicode handling can be more complex because case mapping sometimes changes the number of code points; normalizing both strings must be designed and tested against real data.

When you only need to match a fixed region case-insensitively, `regionMatches(true, ...)` is another API worth considering:

```java
String text = "Java Core";
String prefix = "java";
boolean result = text.regionMatches(
        true, 0, prefix, 0, prefix.length()
);
System.out.println(result); // true
```

Here `true` enables case-insensitive mode in `regionMatches`; this is **not** an overload of `startsWith`. The snippet must be placed inside a method and the variable `text` is declared as shown above.

With Unicode, two strings can look identical yet have different code point sequences. For example, `"\u00E9"` (precomposed é) and `"e\u0301"` (e plus combining acute accent) are not automatically equal in `startsWith` or `endsWith` without prior normalization. Distinguish that issue from prefix/suffix comparison rules.

## 7. Positions in `startsWith(prefix, toffset)` Are UTF-16, Not Code Points

In Java, `String.length()`, `charAt()`, and the `toffset` parameter use **UTF-16 code unit indices**. A Unicode code point outside the BMP (for instance, emoji 😀, `U+1F600`) occupies two code units (a surrogate pair). Thus, code point position and UTF-16 index may not coincide.

File `UnicodeOffsetPrefix.java`:

```java
public class UnicodeOffsetPrefix {
    public static void main(String[] args) {
        String smile = new String(Character.toChars(0x1F600));
        String text = "A" + smile + "B";

        System.out.println("length=" + text.length());
        System.out.println("smile at 1=" + text.startsWith(smile, 1));
        System.out.println("smile at 2=" + text.startsWith(smile, 2));
        System.out.println("B at 2=" + text.startsWith("B", 2));
        System.out.println("B at 3=" + text.startsWith("B", 3));
        System.out.println("ends with B=" + text.endsWith("B"));

        int indexAfterTwoCodePoints = text.offsetByCodePoints(0, 2);
        System.out.println("B at code point boundary="
                + text.startsWith("B", indexAfterTwoCodePoints));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 UnicodeOffsetPrefix.java
java UnicodeOffsetPrefix
```

Output:

```text
length=4
smile at 1=true
smile at 2=false
B at 2=false
B at 3=true
ends with B=true
B at code point boundary=true
```

`text` contains three code points (`A`, the emoji, `B`) but has four UTF-16 code units. `B` is at UTF-16 index **3**, not **2**. If starting from a **code point position**, convert it to a UTF-16 index with `offsetByCodePoints(...)`.

Prefix/suffix methods only perform code-unit matching; they do not validate grapheme cluster boundaries and do not reject a string containing an unpaired surrogate. For international text data, define the index unit accurately before calling the offset overload.

## 8. Applied Example: Checking Line-Start Labels and File Extensions

Problem: read several input strings and classify them by `INFO:` or `ERROR:` labels, or check whether a file name has the `.csv` suffix. These comparisons fit because the label is **at the start** and the file extension is **at the end**.

File `PrefixSuffixUseCase.java`:

```java
public class PrefixSuffixUseCase {
    static String logLevel(String line) {
        if (line.startsWith("ERROR:")) {
            return "error";
        }
        if (line.startsWith("INFO:")) {
            return "info";
        }
        return "other";
    }

    static boolean isCsv(String fileName) {
        return fileName.endsWith(".csv");
    }

    public static void main(String[] args) {
        System.out.println(logLevel("ERROR: disk full"));
        System.out.println(logLevel("INFO: started"));
        System.out.println(logLevel(" WARN: pending"));

        System.out.println(isCsv("report.csv"));
        System.out.println(isCsv("report.csv.bak"));
        System.out.println(isCsv("REPORT.CSV"));

        String message = "2026-10-22 ERROR: disk full";
        System.out.println(message.startsWith("ERROR:", 11));
    }
}
```

Run:

```bash
javac -encoding UTF-8 PrefixSuffixUseCase.java
java PrefixSuffixUseCase
```

Output:

```text
error
info
other
true
false
false
true
```

Cases to understand:

- `" WARN: pending"` has a leading space so it does not match any label starting at index 0; applications wishing to ignore whitespace must handle it separately.
- `"report.csv.bak"` contains `".csv"` in the middle, but does not **end** with `".csv"`; `endsWith(".csv")` returns `false`.
- `"REPORT.CSV"` does not end with `".csv"` under case-sensitive comparison.
- In `message`, `"ERROR:"` starts at index 11, so the `startsWith("ERROR:", 11)` overload checks it successfully.

Checking `endsWith(".csv")` only detects a character suffix; it **does not verify that the file contents are actually CSV**, does not ensure path safety, and does not replace data-format validation.

## 9. Comparison with `contains`, `indexOf`, `matches`, and `regionMatches`

When choosing an API, start with the question you are asking:

| Application question | Appropriate API |
| --- | --- |
| Does it start with a prefix at index 0? | `startsWith(prefix)` |
| Is the exact prefix at a specific UTF-16 index? | `startsWith(prefix, toffset)` |
| Does it end with a suffix? | `endsWith(suffix)` |
| Does a character sequence appear **anywhere**? | `contains(fragment)` |
| Where does a string **first appear**, optionally starting from a position? | `indexOf(fragment)` or `indexOf(fragment, fromIndex)` |
| Does the entire string match a **regex**? | `matches(regex)` |
| Are two character regions equal, optionally ignoring case? | `regionMatches(...)` |

Example:

```java
String text = "banana";

System.out.println(text.startsWith("ana"));    // false
System.out.println(text.startsWith("ana", 1)); // true
System.out.println(text.contains("ana"));      // true
System.out.println(text.indexOf("ana"));       // 1
System.out.println(text.endsWith("ana"));      // true
```

Do not use `matches(".*prefix.*")` just to ask whether a string starts with fixed content. `startsWith` makes the intent clearer and does not turn characters in the prefix into regex syntax.

## 10. `null` Values and Safe Usage

These methods do not treat `null` as an empty prefix or suffix. Passing a `null` argument to `startsWith` or `endsWith` throws `NullPointerException`. If the source string variable itself is `null`, calling a method on it also causes `NullPointerException`.

Example handling potentially `null` references:

```java
static boolean hasErrorPrefix(String line) {
    return line != null && line.startsWith("ERROR:");
}

static boolean hasCsvSuffix(String fileName) {
    return fileName != null && fileName.endsWith(".csv");
}
```

The two methods above are illustrative examples that must be placed inside a Java class. The `&&` operator performs short-circuit evaluation, so the string API is only called when the source reference is non-`null`.

If `prefix` or `suffix` comes from input data and may be `null`, handle it according to business rules (reject, require non-empty, or use an intentional default value) instead of silently treating `null` as `""`.

## 11. Common Mistakes and How to Avoid Them

**1. Thinking `startsWith(prefix, offset)` finds the first occurrence after `offset`.** The method checks **only at `offset`**; to search from `offset` onward, use `indexOf(prefix, offset)`.

**2. Assuming an out-of-range offset always throws an exception.** For a non-`null` prefix, `startsWith(prefix, offset)` returns `false` if `offset` is negative or beyond what can match, including when not enough characters remain.

**3. Overlooking empty prefixes/suffixes.** `startsWith("")` and `endsWith("")` are always `true`; `startsWith("", offset)` is only `true` when `offset` is between 0 and `length()`. Check `isEmpty()` additionally if business rules require a non-empty substring.

**4. Assuming these methods ignore case, whitespace, or normalization.** All three match the exact contents of the `String`; any preprocessing must be designed explicitly.

**5. Confusing `offset` with a Unicode code point count.** Java uses UTF-16 indices; for emojis and supplementary characters, the index can differ from the code point position.

**6. Treating `endsWith(".txt")` as conclusive proof of content type.** A suffix only reflects the string name, not file verification or data-format validation.

**7. Passing `null` and expecting `false`.** Validate inputs explicitly if they may be `null`.

**8. Using `contains` instead of exact start/end checks.** `contains` can return `true` even if the target appears in the middle of the string; classification conditions will be wrong if business logic requires a prefix or suffix.

## 12. Self-Check Questions

**Question 1.** Given `String s = "banana";`, what do these three expressions return?

```java
s.startsWith("ana")
s.startsWith("ana", 1)
s.startsWith("ana", 2)
```

**Answer:** `false`, `true`, `false`, respectively. `"ana"` is not at the start of the string, but appears right at index 1 and does not appear at index 2.

**Question 2.** Why is `"abc".startsWith("", 3)` `true` while `"abc".startsWith("", 4)` is `false`?

**Answer:** An empty prefix matches at valid boundaries from 0 through `length()` (which is 3), whereas index 4 exceeds the trailing boundary.

**Question 3.** What does `"archive.tar.gz".endsWith(".tar")` evaluate to?

**Answer:** `false`, because the full string ends with `".gz"`. `".tar"` only appears before the final suffix.

**Question 4.** If you need to find `"ERROR:"` at any position from offset 5 onward, which API should you use?

**Answer:** `indexOf("ERROR:", 5)`, then check whether the result differs from `-1`. `startsWith("ERROR:", 5)` checks strictly at position 5.

**Question 5.** Do `startsWith` and `endsWith` treat `.` or `*` as regex wildcards?

**Answer:** No. The arguments are plain character sequences; to use regular expressions, pick a regex-capable API and handle regex syntax separately.

**Takeaway:** `startsWith(prefix)` checks the **start of the string**, `startsWith(prefix, toffset)` checks **strictly at a UTF-16 offset**, and `endsWith(suffix)` checks the **end of the string**. All three are case-sensitive, follow boundary rules for empty prefixes/suffixes, and do not search arbitrarily inside the string.
