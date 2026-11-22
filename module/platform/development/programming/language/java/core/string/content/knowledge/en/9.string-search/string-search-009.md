# Distinguishing Literal String Search from Regular Expression Search in Java

## 1. Two Search Types with Different Meanings

A text search operation can accept either a **literal keyword** or a **regular expression (regex)**. These two concepts differ even when they happen to produce the same result.

- **Literal search:** the characters of the keyword are the exact data to find. The keyword **a.b** matches only the three characters **a**, a period, and **b**.
- **Regex search:** the keyword is a *pattern* containing control symbols. The regex **a.b** matches **a.b**, **aXb**, and **a1b**, because the dot **.** represents any single character (except certain line terminators under default mode).

In Java, choose **String.contains()** or **String.indexOf()** when you want to find an exact text segment; choose **java.util.regex.Pattern** and **Matcher** when you need a rule like "a code starting with item- followed by multiple digits".

Do not assume that a `String` containing **.**, **\**, **+**, **?**, or square brackets automatically becomes a regex. They only carry regex meaning when passed to an API that **actively parses regular expressions**.

Quick example, placed inside a method:

~~~java
String text = "a.b aXb";
System.out.println(text.contains("a.b")); // true: literal "a.b"
System.out.println(text.indexOf("a.b"));  // 0
System.out.println(text.contains("a.b aXb")); // true
System.out.println(java.util.regex.Pattern
        .compile("a.b").matcher("aXb").find()); // true: "." is a wildcard
~~~

## 2. Literal Search APIs on `String`

| API | Result | How it searches |
| --- | --- | --- |
| **text.contains(query)** | boolean | Does **query** appear literally inside text? |
| **text.indexOf(query)** | int | First position of query, or **-1** if absent |
| **text.indexOf(query, fromIndex)** | int | Literal search starting from a UTF-16 offset |
| **text.lastIndexOf(query)** | int | Last occurrence searching backward |
| **text.startsWith(prefix)** | boolean | Literal prefix match |
| **text.endsWith(suffix)** | boolean | Literal suffix match |
| **text.equals(query)** | boolean | Compares full content, not a substring search |

Example:

~~~java
String path = "report.v1.txt";
System.out.println(path.contains(".v1."));   // true
System.out.println(path.indexOf(".v1."));    // 6
System.out.println(path.startsWith("rep"));  // true
System.out.println(path.endsWith(".txt"));   // true
System.out.println(path.contains("\\d+"));   // false
~~~

On the last line, **"\\d+"** is a Java `String` whose content consists of a backslash, the letter **d**, and **+**. **contains()** does not decode it as the regex "one or more digits".

The `String` search methods listed above are **case-sensitive**, do not automatically normalize Unicode, and do not apply Vietnamese accent-insensitive matching policies.

### Empty Strings, `null`, and Positions

- **text.contains("")** returns **true** for any non-null `String` `text`.
- **text.indexOf("")** returns **0**; **text.lastIndexOf("")** returns **text.length()**.
- If **text == null**, calling a method on `text` causes **NullPointerException**. If `query` passed to **contains** or **indexOf(String)** is `null`, the method rejects it as well and throws an exception.
- **indexOf()**, **lastIndexOf()**, and most `String` slicing operations use **UTF-16 offsets**, not visible character counts. Non-BMP emojis can occupy two UTF-16 units.

If an empty query makes no sense in your search feature, validate the input before calling the API; do not assume **contains("") == true** is what the user wants.

### Backslashes in Java Literals

~~~java
String location = "C:\\temp\\file.txt";
System.out.println(location.contains("\\"));  // true
System.out.println(location.contains(".txt")); // true
~~~

The **\\** in source code is doubled because of **Java string literal** syntax. That is Java's language-level escape mechanism, independent of regex syntax. If `query` was already read from keyboard input as a `String` variable, pass **contains(query)** directly without manually inserting extra backslashes.

## 3. Regex in Java: `Pattern` and `Matcher`

To use regular expressions, import:

~~~java
import java.util.regex.Pattern;
import java.util.regex.Matcher;
~~~

**Pattern.compile(regex)** compiles a regex into a **Pattern**. **pattern.matcher(text)** creates a stateful **Matcher** that scans text. Then:

- **find()** finds the next **subsequence** matching the regex.
- **matches()** requires the **entire target region** to match the regex.
- **lookingAt()** requires the regex to match right at the **start of the region**, not necessarily the entire region.
- **group()** retrieves the matched text; **start()** and **end()** return the starting UTF-16 offset and the offset right after the match.

Example finding codes matching a pattern:

~~~java
Pattern pattern = Pattern.compile("item-\\d+");
Matcher matcher = pattern.matcher("item-42, item-7");

while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Stdout:

~~~text
item-42
item-7
~~~

**\\d** in regex represents a digit according to Java `Pattern` rules; **+** means one or more times. In **Java source code**, this regex must be written **"item-\\d+"** so that the actual `String` value passed to the engine contains a backslash.

### `find()`, `matches()`, and `String.matches()`

~~~java
Pattern digits = Pattern.compile("\\d+");

System.out.println(digits.matcher("abc123xyz").find());      // true
System.out.println(digits.matcher("abc123xyz").matches());   // false
System.out.println(digits.matcher("123abc").lookingAt());    // true
System.out.println("123".matches("\\d+"));                   // true
System.out.println("abc123xyz".matches("\\d+"));             // false
~~~

The statements importing **Pattern** above are an illustration inside a method.

**String.matches(regex)** also checks the **entire string**. Hence **"abc123".matches("\\d+")** is `false`, even though the **123** part matches the regex completely. If you want to **check whether a matching segment exists** in the text, use **Pattern.compile(regex).matcher(text).find()**.

Do not mechanically wrap a regex with **".*"** on both ends to simulate `find()`: the rule becomes harder to read, is affected by how **.** handles newlines, and can incur unnecessary processing overhead.

## 4. Running a Java 17+ Example: Comparing Literal vs. Regex

Save as **LiteralVsRegexSearchDemo.java** in UTF-8:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class LiteralVsRegexSearchDemo {
    public static void main(String[] args) {
        String text = "file.txt | fileXtxt | item-42 | ITEM-7";

        System.out.println(text.contains("file.txt"));
        System.out.println(text.indexOf("file.txt"));
        System.out.println(text.indexOf("fileXtxt"));

        Pattern exactDot = Pattern.compile("file\\.txt");
        Pattern wildcardDot = Pattern.compile("file.txt");

        System.out.println(exactDot.matcher(text).find());
        System.out.println(wildcardDot.matcher("fileXtxt").matches());
        System.out.println(exactDot.matcher("fileXtxt").matches());
        System.out.println(text.matches("file\\.txt"));

        Matcher items = Pattern.compile("(?i)item-\\d+")
                .matcher(text);

        while (items.find()) {
            System.out.printf("%s@%d-%d%n",
                    items.group(), items.start(), items.end());
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 LiteralVsRegexSearchDemo.java
java LiteralVsRegexSearchDemo
~~~

Stdout:

~~~text
true
0
11
true
true
false
false
item-42@22-29
ITEM-7@32-38
~~~

Explanation:

1. **contains("file.txt")** searches for the literal string with a period, returning `true`.
2. **indexOf("file.txt") == 0**, while **fileXtxt** starts at offset 11.
3. The regex **file\\.txt** in Java requires a **literal period**; so it finds `file.txt` but does not match `fileXtxt`.
4. The regex **file.txt** allows any character at the dot position and therefore matches `fileXtxt` too.
5. **text.matches("file\\.txt")** returns `false` because `text` is longer than `file.txt`; **matches** requires a full match.
6. The inline flag **(?i)** enables case-insensitive matching, so both `item-42` and `ITEM-7` are found.
7. **start()/end()** return UTF-16 offsets, where **end()** is exclusive. You can use **text.substring(start, end)** to extract the matched segment.

## 5. Regex Symbols Easily Mistaken for Literal Text

| Regex syntax | Pattern meaning | When you want a literal match |
| --- | --- | --- |
| **.** | Any character, except certain line terminators depending on mode | Escape as **\\.** |
| **\\d** | A digit | Quote the backslash and `d` if they are actual data |
| **[abc]** | One character from the set `a`, `b`, `c` | Quote the whole string **[abc]** |
| **a+** | One or more `a` characters | Escape the plus sign if searching for **a+** |
| **a*** | Zero or more `a` characters | Escape the asterisk if searching for **a*** |
| **a?** | Zero or one `a` character | Escape the question mark if searching for **a?** |
| **^abc** | Pattern at start depending on mode | Quote the caret if it is literal data |
| **abc$** | Pattern at end depending on mode | Quote the dollar sign if it is literal data |
| **(abc)** | Regex group | Quote parentheses if searching for text with parentheses |
| **a\|b** | Match `a` or `b` | Quote the pipe character when it is literal text |
| **\\bcat\\b** | Word `cat` with word boundaries | Use regex when business rules actually need boundaries |

Regex has groups, character classes, quantifiers, anchors, and lookarounds. They are very useful when the input is an **intentional pattern**, but cause wrong results if you take a raw user keyword and treat it as a pattern.

### Searching for Whole Words vs. Substrings Inside Words

~~~java
String text = "cat scatter cat";
Pattern word = Pattern.compile("\\bcat\\b");
Matcher matcher = word.matcher(text);
while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

The snippet above prints:

~~~text
cat
cat
~~~

**String.contains("cat")** still returns `true` because the string contains `cat`; **indexOf** can even find the substring `cat` inside `scatter`. The regex **\\bcat\\b** constrains by word boundaries and does not match `cat` inside `scatter`. Regex word-boundary rules do not completely replace natural-language tokenization, especially for multilingual text.

## 6. Understanding the Two Escaping Layers: Java Literal and Regex

Suppose you want to match a literal dot:

1. Text to match: **.**
2. Regex syntax: **\\.**
3. Java string literal passed to `Pattern`: **"\\."**

**Java processes string literal escapes first; the regex engine reads the resulting string afterward.**

| Intent | Actual regex | Written in Java String literal |
| --- | --- | --- |
| A dot | **\\.** | **"\\."** |
| A plus sign | **\\+** | **"\\+"** |
| A question mark | **\\?** | **"\\?"** |
| One backslash | **\\\\** | **"\\\\\\\\"** |
| One or more digits | **\\d+** | **"\\d+"** |
| Three chars `a`, `.`, `b` | **a\\.b** | **"a\\.b"** |

For a variable **query** that is already a `String` holding user data, do not apply Java string literal escaping a second time. For example, **query = "a.b"** received from a form is already the actual text. To search literally, call **text.contains(query)**; to search with `Matcher` while keeping it literal, use **Pattern.quote(query)**.

## 7. Literal Search Using `Pattern`: `quote` and `LITERAL`

Sometimes an application wants to iterate over occurrences, get **Matcher.start()/end()**, or embed a literal part inside a larger regex pattern. Two important tools exist for this.

### 7.1. `Pattern.quote(query)`

**Pattern.quote(String)** turns `query` into a regex fragment meaning **literally match the entire content of `query`**, including plus signs, question marks, parentheses, backslashes, or the sequence **\\E**.

~~~java
String query = "a.b";
Pattern literalPattern = Pattern.compile(Pattern.quote(query));
System.out.println(literalPattern.matcher("aXb a.b").find()); // true
~~~

The snippet above sits inside a method with **Pattern** imported. The result is `true` because the text has **a.b** at the end; this regex does not match `aXb` as a literal.

Never manually concatenate **"\\Q" + query + "\\E"** for arbitrary input: `query` itself might contain **\\E**. **Pattern.quote** handles that edge case properly.

When only **part** of a pattern is user data, quote that part:

~~~java
String query = "a.b";
Pattern token = Pattern.compile(
        "start:" + Pattern.quote(query) + ":end");

System.out.println(token.matcher("start:a.b:end").matches()); // true
System.out.println(token.matcher("start:aXb:end").matches()); // false
~~~

The **start:** and **:end** parts in this example are fixed; `query` is literal text inserted in the middle. If the fixed parts contain regex metacharacters, those must also be designed or quoted appropriately.

### 7.2. `Pattern.LITERAL`

**Pattern.LITERAL** makes the **entire input pattern** be interpreted as literal text without parsing regex metacharacters:

~~~java
String query = "a.b";
Pattern literal = Pattern.compile(query, Pattern.LITERAL);

System.out.println(literal.matcher("aXb").find()); // false
System.out.println(literal.matcher("a.b").find()); // true
~~~

**Pattern.LITERAL** fits when the whole pattern is literal. **Pattern.quote** is more flexible when mixing fixed regex syntax with a literal data fragment. Case-matching flags like **CASE_INSENSITIVE** and **UNICODE_CASE** can still take effect with **LITERAL** patterns.

### Complete Java 17+ Example

Save as **SafeLiteralSearchDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SafeLiteralSearchDemo {
    static void printMatches(String label, Pattern p, String text) {
        Matcher m = p.matcher(text);
        while (m.find()) {
            System.out.printf("%s=%d:%s%n",
                    label, m.start(), m.group());
        }
    }

    public static void main(String[] args) {
        String text = "a.b aXb [a.b]";
        String query = "a.b";

        System.out.println("contains=" + text.contains(query));
        System.out.println("index=" + text.indexOf(query));

        printMatches("regex", Pattern.compile(query), text);
        printMatches("quoted", Pattern.compile(Pattern.quote(query)), text);
        printMatches("literal",
                Pattern.compile(query, Pattern.LITERAL), text);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeLiteralSearchDemo.java
java SafeLiteralSearchDemo
~~~

Stdout:

~~~text
contains=true
index=0
regex=0:a.b
regex=4:aXb
regex=9:a.b
quoted=0:a.b
quoted=9:a.b
literal=0:a.b
literal=9:a.b
~~~

The input has **3 segments** matching the regex **a.b**, because the wildcard also matches `aXb`, whereas **quote** and **LITERAL** match only the **2 segments** of literal `a.b`. Positions 0, 4, and 9 are UTF-16 offsets.

## 8. Distinguishing `replace`, `replaceAll`, and `split`

Much confusion arises because some `String` APIs take literals while others take regexes.

| API | Meaning of search argument |
| --- | --- |
| **contains(CharSequence)** | Literal |
| **indexOf(String)** | Literal |
| **replace(CharSequence, CharSequence)** | Literal for both target and replacement |
| **replaceAll(String regex, String replacement)** | Regex |
| **replaceFirst(String regex, String replacement)** | Regex |
| **split(String regex)** | Regex defining the delimiter |
| **matches(String regex)** | Regex requiring full-string match |

Example:

~~~java
String file = "one.two.three";
System.out.println(file.replace(".", "-"));     // one-two-three
System.out.println(file.replaceAll("\\.", "-")); // one-two-three
System.out.println(file.replaceAll(".", "-"));   // -------------
~~~

The regex **.** in **replaceAll** matches every character in an example without line terminators. With **split**, to split on a literal period, write **split("\\.")** or **split(Pattern.quote("."))** instead of **split(".")**.

**split(regex)** has an implicit **limit = 0**, which discards trailing empty elements. If you want to keep trailing empty strings, use **split(regex, -1)**.

### Replacement Has Its Own Syntax

The **replacement** argument of **Matcher.replaceAll** and **String.replaceAll** gives special meaning to **$** (capture group references) and backslash escapes. When the replacement comes from user data, use **Matcher.quoteReplacement(replacement)**, unlike **Pattern.quote(query)** which is for the search pattern:

~~~java
String text = "cost=42";
String replacement = "$5";
String safe = Pattern.compile("\\d+")
        .matcher(text)
        .replaceAll(Matcher.quoteReplacement(replacement));
System.out.println(safe); // cost=$5
~~~

This snippet sits inside a method importing **Pattern** and **Matcher**. Without quoting the replacement, **$5** can be interpreted as a reference to a non-existent capture group and cause an error. With **String.replace(old, new)**, the replacement string is literal text.

## 9. Case Sensitivity and Unicode Are Independent Rules

**String.contains** and **indexOf** perform case-sensitive literal matching. Regex can use:

~~~java
Pattern insensitive = Pattern.compile(
        "java", Pattern.CASE_INSENSITIVE);
System.out.println(insensitive.matcher("JAVA").find()); // true
~~~

If you need Unicode case folding in Java `Pattern`, combine **Pattern.UNICODE_CASE** with **CASE_INSENSITIVE**. Choose your business policy explicitly; case-insensitive matching is not synonymous with accent-insensitive Vietnamese search.

Neither `String` nor regex automatically guarantees that two visually identical Unicode encodings will match:

~~~java
String composed = "\u00E1";     // precomposed á
String decomposed = "a\u0301"; // a + combining acute accent

System.out.println(composed.contains(decomposed)); // false
~~~

If canonical equivalence is needed for Vietnamese, normalize both data and query with the same rule, such as **java.text.Normalizer.Form.NFC**, before searching. Regex has **Pattern.CANON_EQ**, though its usage and cost should be evaluated; consistent upfront normalization is usually easier to control for ordinary searching.

A regex can match one or more code points; a "visible character" can still be a grapheme cluster of multiple code points. If you genuinely need grapheme handling, Java `Pattern` supports **\\X**; that is a different problem from literal string search.

## 10. Performance, Safety, and User Input

**Simple literal search:** prefer **contains** or **indexOf**. Intent is expressed directly and no regex compilation is needed.

**True pattern search:** compile a **Pattern** and use **Matcher**. When reusing the same regex repeatedly, reuse the **Pattern**. A **Pattern** is immutable and safe to share across threads; a **Matcher** holds mutable search state, so each task or thread needs its own `Matcher`.

**Input is a user keyword:** do not call **Pattern.compile(userInput)** unless the feature intentionally lets users write regexes. Characters like **[** or **(** can throw **PatternSyntaxException**; quantifiers or other operators can completely alter results.

~~~java
String query = userInput; // value coming from a form or API
boolean found = text.contains(query);

// If you need match positions provided by Matcher:
Pattern safe = Pattern.compile(Pattern.quote(query));
boolean foundByMatcher = safe.matcher(text).find();
~~~

The snippet above assumes **text** and **userInput** are declared, with `Pattern` imported. For `null` or empty keywords, apply your input contract before searching.

**Intentionally allowing users to enter regexes:** catch **PatternSyntaxException** to report helpful syntax errors:

~~~java
try {
    Pattern userPattern = Pattern.compile("[unclosed");
} catch (java.util.regex.PatternSyntaxException ex) {
    System.out.println("Invalid regex");
}
~~~

Beyond syntax errors, running regexes on untrusted input can cause **backtracking overload** in complex patterns. If regex search mode is supported, bound inputs, control complexity, and test resource-heavy patterns. **Pattern.quote(query)** prevents regex symbol interpretation when literal search is intended.

## 11. Choosing an API by Scenario

| Requirement | Appropriate approach | Reason |
| --- | --- | --- |
| Does it contain exact **item.42**? | **text.contains("item.42")** | The dot is literal data |
| First position of a fixed URL/ID? | **text.indexOf(query)** | Returns UTF-16 offset |
| Find code **item-** with digits | **Pattern.compile("item-\\d+").matcher(text).find()** | Digit portion varies by pattern |
| Entire string is 3 letters and 4 digits | **text.matches("[A-Za-z]{3}\\d{4}")** | Full-string validation |
| User enters brackets, pluses, dots and needs offsets | **Pattern.compile(Pattern.quote(query))** | Literal search via `Matcher` |
| Whole pattern must be treated as text | **Pattern.compile(query, Pattern.LITERAL)** | Disables regex symbol parsing |
| Split data by a literal dot | **text.split("\\.")** | `split` takes a regex |
| Replace dots with hyphens | **text.replace(".", "-")** | `replace` searches literally |

Before implementing a search box, clarify: literal or regex, full match or substring, case-sensitive or insensitive, how Unicode normalization is handled, whether all match positions are needed, and how empty input is interpreted.

## 12. Common Mistakes

1. **Using `text.matches("abc")` to ask whether it contains `abc`.** Because `matches` requires a full match, use **contains** or **Matcher.find**.
2. **Assuming regex `a.b` only matches literal `a.b`.** Escape the dot (**"a\\.b"**), or use **Pattern.quote**.
3. **Passing a raw query to `Pattern.compile(query)`.** The query may contain metacharacters, causing wrong results or syntax errors. Use literal search when appropriate.
4. **Forgetting the two escaping layers for Java and regex.** The regex **\\.** is written **"\\."** in Java code.
5. **Using `split(".")` to split on a dot.** Regex **.** is a wildcard; use **split("\\.")**.
6. **Using `replaceAll(".", "-")` to replace only dots.** It replaces every character matching the wildcard; use **replace(".", "-")** or an escaped regex.
7. **Confusing `quoteReplacement` with `Pattern.quote`.** One handles replacement text, the other handles the search pattern.
8. **Assuming `Matcher.start()/end()` return Unicode code point counts.** They are UTF-16 offsets; pay special attention to non-BMP emojis.
9. **Skipping normalization.** Two Vietnamese strings that render identically may have different encodings and fail to match without a normalization policy.
10. **Sharing a `Matcher` across threads.** `Matcher` is mutable; create a separate one from the compiled `Pattern`.
11. **Assuming any regex that compiles is safe.** A regex can consume excessive CPU on certain inputs; restrict user-entered pattern search modes.

## 13. Knowledge Self-Check

1. How does **"a.b"** differ between **contains** and **Pattern.compile**? — `contains` looks for a literal dot; regex `a.b` allows any single character in the middle.
2. Why is **"abc123".matches("\\d+")** `false` while **Pattern.compile("\\d+").matcher("abc123").find()** is `true`? — Full-string match vs. substring match.
3. How do you search for an exact dot character with `String`? — **contains(".")** or **indexOf(".")**.
4. When a user-entered query contains **[**, **?**, **+**, how do you search literally with `Matcher`? — **Pattern.compile(Pattern.quote(query))**.
5. How does **Pattern.LITERAL** differ from **Pattern.quote**? — `LITERAL` applies to the whole pattern; `quote` lets you quote a component or whole keyword when composing a regex.
6. What is **Matcher.quoteReplacement** used for? — Preserving replacement text literally so **$** and backslashes are not interpreted as replacement syntax.
7. What kind of position does **Matcher.start()** return? — A UTF-16 offset.
8. What should you do if Vietnamese search must treat NFC and NFD forms as equivalent? — Define a normalization policy and normalize both data and query consistently before searching.

## 14. Key Takeaways

- **Literal search:** **String.contains**, **indexOf**, **startsWith**, **endsWith**. Regex special characters are just ordinary data characters.
- **Pattern search:** **Pattern.compile(regex)** and **Matcher.find()**; check full match with **Matcher.matches()** or **String.matches(regex)**.
- **Regex dot `.` is a wildcard**; a regex matching a literal dot needs escaping, written **"\\."** in Java.
- **User keywords needing literal search:** use **Pattern.quote(query)** or **Pattern.LITERAL** when you still need the Regex API.
- **contains/indexOf/replace** and **matches/replaceAll/split** have different semantics. Choose the right API before worrying about escaping.
- **Case sensitivity, Unicode normalization, and graphemes** are separate requirements that are not solved automatically simply by choosing literal or regex.

Java SE 17 references: **java.lang.String** (`contains`, `indexOf`, `matches`, `replace`, `replaceAll`, `split`), **java.util.regex.Pattern** (`compile`, `quote`, `LITERAL`, flags), and **java.util.regex.Matcher** (`find`, `matches`, `lookingAt`, `group`, `start`, `end`, `quoteReplacement`).