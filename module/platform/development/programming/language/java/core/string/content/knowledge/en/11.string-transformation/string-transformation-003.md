# Distinguishing `replace`, `replaceFirst`, and `replaceAll` in Java

The three string-processing methods `replace()`, `replaceFirst()`, and `replaceAll()` all produce a transformed result from a `String`. The decisive differences are **whether the search target is treated as literal text or a regex**, and **whether replacement happens once or multiple times**. In addition, for the two regex methods, the replacement string has special syntax for capture groups.

**Core rule:** `replace()` searches for a literal and replaces **all** occurrences; `replaceFirst()` searches with a regex and replaces the **first match**; `replaceAll()` searches with a regex and replaces **all non-overlapping matches**.

## 1. API Comparison

| Method | How the search target is interpreted | Number of replacements | How the replacement content is interpreted |
|---|---|---|---|
| `replace(char, char)` | One `char` by UTF-16 | Every occurrence | Literal |
| `replace(CharSequence, CharSequence)` | Literal substring | Every non-overlapping occurrence | Literal, including dollar and backslash |
| `replaceFirst(String regex, String replacement)` | Regex | First match | Supports capture group syntax like `$1` |
| `replaceAll(String regex, String replacement)` | Regex | All matches | Supports capture group syntax like `$1` |

Example:

~~~java
String text = "a.b.a";
System.out.println(text.replace(".", "-"));      // a-b-a
System.out.println(text.replaceFirst(".", "-")); // -.b.a
System.out.println(text.replaceAll(".", "-"));   // -----
~~~

In `replace()`, the dot is a real dot character. In regex, a dot usually means match any single character (except certain line terminators unless DOTALL mode is enabled), so `replaceAll(".", "-")` replaces all five characters.

Because `String` is immutable, none of these three calls **modify the `text` object**. To keep the result, you must reassign the variable or pass the result directly to the next processing step.

## 2. `replace()`: Replace Every Literal Substring

The two overloads on `String` are:

~~~java
public String replace(char oldChar, char newChar)
public String replace(CharSequence target, CharSequence replacement)
~~~

These are **illustrative API signatures**, not a standalone runnable Java file.

Characteristics:

- `replace(char,char)` replaces every code unit equal to `oldChar` with `newChar`.
- `replace(CharSequence,CharSequence)` searches for a literal segment and replaces all non-overlapping occurrences.
- Neither the pattern nor the replacement is a **regex**. Dots, asterisks, dollar signs, square brackets, or backslashes carry plain text meaning.
- The name `replace` does not contain the word `All`, yet this method still replaces **all occurrences** of the literal.

~~~java
System.out.println("a.b".replace(".", "-"));         // a-b
System.out.println("a.b".replace('.', '_'));         // a_b
System.out.println("a.b".replace(".", "$1"));        // a$1b
System.out.println("red red".replace("red", "blue")); // blue blue
System.out.println("aaaa".replace("aa", "X"));       // XX
~~~

In the `"aaaa"` example, the `"aa"` segments are chosen at indices 0 and 2, yielding `"XX"`. Matches are **non-overlapping**; the method does not scan every possible segment starting at every position.

With emojis like 🚀, one displayed character can consist of two UTF-16 `char`s, so to replace the whole emoji you should choose the `CharSequence` overload:

~~~java
System.out.println("🚀 + 🚀".replace("🚀", "⭐")); // ⭐ + ⭐
~~~

If `target` is an empty string, replacement can insert the replacement string at the beginning, between code units, and at the end: `"ab".replace("", "-")` produces `"-a-b-"`. Validate empty search values if you do not want that behavior.

## 3. `replaceFirst()`: Replace Only the First Regex Match

Signature:

~~~java
public String replaceFirst(String regex, String replacement)
~~~

The first argument is compiled as a regex. Java finds the first match inside the string and replaces it exactly once. It does not require the entire string to match the regex.

~~~java
String text = "Code 12, code 345, code 67";
System.out.println(text.replaceFirst("\\d+", "#"));
// Code #, code 345, code 67

System.out.println("red red".replaceFirst("red", "blue")); // blue red
System.out.println("abc123def".replaceFirst("\\d+", "#")); // abc#def
System.out.println("hello".replaceFirst("\\d+", "#")); // hello
~~~

The regex `\\d+` represents one or more digits. Because a backslash must be passed to the regex engine, **Java source code** must write `"\\d+"` and cannot use an invalid Java escape sequence. `replaceFirst()` performs *substring* searching like `Matcher.find()`, unlike `String.matches()`, which checks the **entire** string.

To replace the first dot literally using a regex API, you must escape the dot:

~~~java
System.out.println("a.b.c".replaceFirst("\\.", "/")); // a/b.c
~~~

If you only have a single word to replace literally, you can use `Pattern.quote(target)` before calling `replaceFirst()`, and `Matcher.quoteReplacement(replacement)` when the replacement string contains dollar signs or backslashes.

## 4. `replaceAll()`: Replace Every Regex Match

Signature:

~~~java
public String replaceAll(String regex, String replacement)
~~~

It finds non-overlapping regex matches and replaces all of them. Regex is more flexible than literals because it can describe character classes, repetition counts, boundaries, and other conditions.

~~~java
String text = "Code 12, code 345, code 67";
System.out.println(text.replaceAll("\\d+", "#"));
// Code #, code #, code #

System.out.println("A  B   C".replaceAll(" +", " ")); // A B C
System.out.println("abc123def456".replaceAll("\\d+", "#")); // abc#def#
System.out.println("a,b;c".replaceAll("[,;]", "|")); // a|b|c
~~~

The regex `\\d+` groups a **sequence of consecutive digits** into a single match. The regex `" +"` matches clusters of one or more spaces. If you need a broader whitespace group, consider `\\s+` while understanding Java's character class rules and Unicode flags; it does not automatically equate to every application criterion for Unicode whitespace.

If you only need to replace all occurrences of a fixed segment, `replace()` is usually more suitable than `replaceAll()` because it does not have to interpret regex.

## 5. Escaping: Two Different Syntax Layers

When writing Java source code, you must distinguish:

1. **Java string literal:** backslash acts as Java's escape character.
2. **Regex pattern:** Java regex processes operators such as `.`, `*`, `+`, `[]`, `()`, `^`, dollar, and character classes.
3. **Regex replacement:** a dollar sign followed by a group index such as `$1`, `$2` means substituting the captured group; backslash can escape characters in the replacement.

### 5.1. Patterns with Special Characters

| Purpose | Java String literal used as regex |
|---|---|
| One or more digits | `"\\d+"` |
| Literal dot | `"\\."` |
| Literal dollar sign | `"\\$"` |
| One or more ASCII spaces | `" +"` |
| User-entered literal substring | `Pattern.quote(userText)` |

Note that in Java 17, the Java escape `"\s"` produces **a single space** before reaching the regex engine. If you want the regex `\\s`, you must write `"\\s"` in source code. This is an easy bug to slip past compilation because `"\s"` is a valid Java String literal in modern Java, yet it does not mean the regex whitespace class.

### 5.2. Replacements with `$1` and Capture Groups

Example swapping first and last name separated by a comma:

~~~java
String name = "Nguyen, An";
String result = name.replaceAll("(\\w+),\\s*(\\w+)", "$2 $1");
System.out.println(result); // An Nguyen
~~~

The regex has two capture groups: group 1 is `Nguyen`, and group 2 is `An`. In the replacement, `$2 $1` takes group 2 first, followed by group 1. If you want a group only for structural grouping without numbering, use the `(?:...)` form; named groups are declared with `(?<name>...)` and referenced by name as documented in `Matcher`.

In `replace()`, the replacement `"$1"` is literal and does not reference a group. In `replaceAll()` or `replaceFirst()`, the replacement `"$1"` has special meaning; if there is no corresponding capture group, it can throw an exception. Do not mix the two semantics.

### 5.3. Replacement Data Containing Dollar/Backslash

If the replacement comes from a user and all characters must be preserved literally, use `Matcher.quoteReplacement()`:

~~~java
import java.util.regex.Matcher;

String replacement = "$1\\temp";
String result = "abc".replaceAll(
        "b", Matcher.quoteReplacement(replacement));

System.out.println(result.equals("a$1\\tempc")); // true
~~~

`quoteReplacement()` ensures dollar signs and backslashes **are not interpreted as replacement syntax**. This function **does not** turn a regex in the search parameter into a literal.

### 5.4. Search Data Containing Regex Symbols

If you want to search for a dot entered by a user, passing the dot directly into `replaceAll()` will match too broadly. Use `Pattern.quote()` to protect the search side:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String source = "a.b";
String find = ".";
String put = "$5\\x";
String converted = source.replaceAll(
        Pattern.quote(find),
        Matcher.quoteReplacement(put));

System.out.println(converted.equals("a$5\\xb")); // true
~~~

`Pattern.quote()` protects regex **pattern** syntax; `Matcher.quoteReplacement()` protects **replacement** syntax. If both sides are literals, writing `source.replace(find, put)` is simpler and clearer.

## 6. Important Edge Cases

### Empty or Zero-Width Matches

~~~java
System.out.println("ab".replace("", "-"));         // -a-b-
System.out.println("ab".replaceFirst("", "-"));    // -ab
System.out.println("ab".replaceAll("", "-"));      // -a-b-
~~~

A regex can match at a **position** without consuming characters, such as an empty regex or a lookahead. The regex engine has position-advancing rules to avoid infinite loops during replacement. Therefore, validate empty search inputs beforehand if that is not the expected outcome.

### Non-Overlapping Match Replacement

~~~java
System.out.println("aaaa".replace("aa", "X"));       // XX
System.out.println("aaaa".replaceFirst("aa", "X"));  // Xaa
System.out.println("aaaa".replaceAll("aa", "X"));    // XX
~~~

Here, both regex and literal search examine non-overlapping matches. If you need a specialized algorithm that handles overlapping positions as well, design a dedicated solution with lookarounds, index tracking, or custom string-scanning logic; do not assume these APIs do that.

### Newly Inserted Replacements Are Not Reprocessed in the Same Pass

~~~java
System.out.println("aaa".replace("a", "aa")); // aaaaaa
~~~

`replace()` performs one pass over the original data: three `a` characters are replaced with six `a` characters. It does not recursively keep replacing newly generated text forever.

### Original `String` Is Not Mutated

~~~java
String s = "red red";
s.replace("red", "blue");
System.out.println(s); // red red
s = s.replace("red", "blue");
System.out.println(s); // blue blue
~~~

Remember to use the return value because `String` is immutable.

### Null and Invalid Regex

- Null `String` receiver reference: calling the method throws `NullPointerException`.
- Target/pattern/replacement must be non-null. Validate beforehand; do not use null to express "skip replacement."
- Syntactically invalid regex, such as `"["`, can throw `PatternSyntaxException`.
- A replacement referencing a non-existent group can throw an exception; `Matcher.quoteReplacement()` is the solution when you want literal text.

~~~java
try {
    "abc".replaceAll("[", "x");
} catch (java.util.regex.PatternSyntaxException e) {
    System.out.println("Invalid regex"); // Invalid regex
}
~~~

### Unicode and Displayed Characters

The `char` overload operates on UTF-16 code units; emojis often consist of two `char`s. Use the `CharSequence` overload when you want to replace an entire emoji. At the same time, `replace()` and regex **do not automatically normalize Unicode**. Two visually identical strings, such as precomposed `é` and `e` plus combining acute accent, may not match by code point sequence; if you need to compare equivalent representations, use `Normalizer` deliberately.

## 7. Performance and Safety When Handling Dynamic Data

For short literals or fixed keywords, `replace()` is usually clearer in intent and avoids unnecessary regex processing work. If you must apply **a single regex repeatedly**, you can compile `Pattern` once and use `Matcher` on each string:

~~~java
import java.util.regex.Pattern;

Pattern numbers = Pattern.compile("\\d+");
System.out.println(numbers.matcher("A12").replaceAll("#"));  // A#
System.out.println(numbers.matcher("B345").replaceAll("#")); // B#
~~~

`Pattern` can be shared and reused; `Matcher` holds mutable state and should not be used concurrently across multiple threads without proper synchronization. Do not claim regex is always slower in every case; measure with a profiler/JMH on representative data when performance matters.

**User-supplied regex** can contain syntax errors, and certain patterns can cause very slow execution on crafted input (*ReDoS*). If users only want literal search, avoid passing raw input into regex: use `replace()` or `Pattern.quote()`. If you genuinely provide regex functionality, limit input/pattern length, test worst-case inputs, and enforce resource protection policies. `Pattern.quote()` turns the pattern into a literal, not a way to "make arbitrary regex safe" while keeping regex features.

When performing repeated replacements on a large `String` inside many loops, creating intermediate `String`s can consume memory; consider `StringBuilder` or a streaming algorithm depending on the problem.

## 8. Complete Java 17 Program

Save the following code into a UTF-8 file **`ReplaceMethodsDemo.java`**. Unlike the individual snippets above, this is a standalone runnable program.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReplaceMethodsDemo {
    public static void main(String[] args) {
        String source = "a.b.a";
        System.out.println("literal=" + source.replace(".", "-"));
        System.out.println("regexFirst=" + source.replaceFirst(".", "-"));
        System.out.println("regexAll=" + source.replaceAll(".", "-"));
        System.out.println("escapedFirst=" + source.replaceFirst("\\.", "-"));
        System.out.println("escapedAll=" + source.replaceAll("\\.", "-"));

        String repeated = "aa aa aa";
        System.out.println("repeatLiteral=" + repeated.replace("aa", "X"));
        System.out.println("repeatFirst=" + repeated.replaceFirst("aa", "X"));
        System.out.println("repeatAll=" + repeated.replaceAll("aa", "X"));

        String digits = "AB12-CD034";
        System.out.println("digitsFirst=" + digits.replaceFirst("\\d+", "#"));
        System.out.println("digitsAll=" + digits.replaceAll("\\d+", "#"));

        String name = "Nguyen, An";
        System.out.println("group=" +
                name.replaceAll("(\\w+),\\s*(\\w+)", "$2 $1"));

        String find = ".";
        String replace = "$5\\x";
        String safe = "a.b".replaceAll(Pattern.quote(find),
                Matcher.quoteReplacement(replace));
        System.out.println("safeLiteral=" + safe.equals("a$5\\xb"));

        System.out.println("overlap=" + "aaaa".replace("aa", "X"));
        System.out.println("emptyTarget=" + "ab".replace("", "-"));
        System.out.println("original=" + source);
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac -encoding UTF-8 ReplaceMethodsDemo.java
java ReplaceMethodsDemo
~~~

Output:

~~~text
literal=a-b-a
regexFirst=-.b.a
regexAll=-----
escapedFirst=a-b.a
escapedAll=a-b-a
repeatLiteral=X X X
repeatFirst=X aa aa
repeatAll=X X X
digitsFirst=AB#-CD034
digitsAll=AB#-CD#
group=An Nguyen
safeLiteral=true
overlap=XX
emptyTarget=-a-b-
original=a.b.a
~~~

`regexAll` produces five `-` characters because the regex `.` matches every single character of `a.b.a`. `safeLiteral=true` verifies that both dollar and backslash in the replacement are preserved literally thanks to `Matcher.quoteReplacement()`. `original=a.b.a` shows that these methods do not alter the source `String` content.

## 9. Common Mistakes

| Mistake | Why | How to handle |
|---|---|---|
| `replaceAll(".", "X")` to replace dots | Dot is a regex operator | Use `replace(".", "X")` or an escaped dot regex |
| Thinking `replace()` only replaces once | Method name is misleading | `replace()` replaces all literals |
| Searching user text via unescaped regex | Brackets/asterisks/dots have special meaning | `replace()` or `Pattern.quote()` |
| User replacement containing dollar sign | May be interpreted as a regex group | `Matcher.quoteReplacement()` |
| Writing Java regex `"\d+"` | Invalid Java escape sequence | `"\\d+"` |
| Writing `"\s+"` for regex whitespace search | In modern Java, `\\s` at the Java literal level can be a space | Write `"\\s+"` |
| Ignoring the return value | `String` is immutable | Reassign or pass along the result |
| Using `replace(char,char)` for a whole emoji | An emoji can consist of two code units | Use `replace(CharSequence,CharSequence)` |
| Thinking replacement is recursive | Single pass over the input string | If multiple phases are needed, build steps explicitly |
| Accepting arbitrary unbounded regexes | Can cause syntax errors or high CPU usage | Validate, bound, and test |

## 10. Checklist for Choosing the Right Method

1. **Replace a literal everywhere:** choose `replace()`.
2. **Replace the first regex match:** choose `replaceFirst()`.
3. **Replace all regex matches:** choose `replaceAll()`.
4. **Input contains dots, dollar signs, backslashes, or brackets:** distinguish whether characters belong to *pattern* or *replacement*; quote appropriately if going through regex.
5. **Empty input, null, or complex Unicode:** validate and define semantics upfront.
6. **Regex applied multiple times:** compile `Pattern` once; use a fresh or properly managed `Matcher` per task.
7. **Optimization needs or untrusted input:** measure performance and bound regex size/complexity.

**Key takeaway:** `replace()` replaces all literals; `replaceFirst()` replaces the first regex match; `replaceAll()` replaces all regex matches. With regex, **patterns and replacements have different syntaxes**, and both must also be properly escaped in Java source code.