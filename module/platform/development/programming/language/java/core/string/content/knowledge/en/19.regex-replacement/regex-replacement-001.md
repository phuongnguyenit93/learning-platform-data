# replaceFirst and replaceAll: Regex Replacement in Java

In Java, the **String** class has two methods for replacing content using **regular expressions (regex)**: **replaceFirst** and **replaceAll**. Both find text matching a pattern and create a resulting String; the core difference is whether they replace **the first match** or **every match**.

## 1. Syntax and How They Work

~~~java
String replaceFirst(String regex, String replacement)
String replaceAll(String regex, String replacement)
~~~

| Method | Meaning | Example Result |
| --- | --- | --- |
| **replaceFirst** | Replaces the first match from left to right | "a1 b2".replaceFirst("\\d+", "#") → "a# b2" |
| **replaceAll** | Replaces all non-overlapping matches | "a1 b2".replaceAll("\\d+", "#") → "a# b#" |

- **regex** is the search pattern following the regex syntax of **java.util.regex.Pattern**.
- **replacement** is the replacement string following the syntax of **java.util.regex.Matcher**. In it, **$** and the backslash have special meanings; they are not always treated as ordinary characters.
- Neither method **modifies the original String**, because String is immutable. You must use the return value if you want to keep the change.
- If the regex matches no substring, the result has the same content as the input string.
- The engine evaluates matching segments from left to right; newly inserted results are not searched again in the same pass.
- The regex does not need to match the entire string: a matching substring is enough to be replaced.

You can think of the implementation semantically as:

~~~java
Pattern.compile(regex).matcher(input).replaceFirst(replacement);
Pattern.compile(regex).matcher(input).replaceAll(replacement);
~~~

This snippet illustrates the mechanism; to run it, you must declare the variables and import **java.util.regex.Pattern**. When processing many strings with the same pattern, you can keep a Pattern object yourself for reuse (see section 8).

## 2. Runnable Java 17+ Program

Save the file **ReplaceRegexDemo.java**:

~~~java
public class ReplaceRegexDemo {
    public static void main(String[] args) {
        String original = "Code A12, B345 and C6";

        System.out.println(original.replaceFirst("\\d+", "#"));
        System.out.println(original.replaceAll("\\d+", "#"));
        System.out.println("a.b.c".replaceAll("\\.", "-"));
        System.out.println("Java JAVA java".replaceAll("(?i)java", "JVM"));
        System.out.println(
                "2026-10-23".replaceFirst(
                        "(\\d{4})-(\\d{2})-(\\d{2})", "$3/$2/$1"));
        System.out.println("ababa".replaceAll("aba", "X"));
        System.out.println(
                "  Hello   Java  ".replaceAll("\\s+", " ").trim());
    }
}
~~~

Run with:

~~~bash
javac ReplaceRegexDemo.java
java ReplaceRegexDemo
~~~

Stdout:

~~~text
Code A#, B345 and C6
Code A#, B# and C#
a-b-c
JVM JVM JVM
23/10/2026
Xba
Hello Java
~~~

Step-by-step explanation: **\\d+** matches a sequence of digits; **\\.** matches a literal dot; **(?i)** enables case-insensitive matching; **$3/$2/$1** reorders the data of the three capturing groups; **"ababa"** has only one non-overlapping match of "aba" when scanning left to right; **\\s+** collapses whitespace runs, and **trim()** removes leading and trailing whitespace.

## 3. Two Layers of Escaping: Java String and Regex

A regex string passes through **two parsers**: the Java compiler reads the String literal first, and then Pattern interprets the resulting string as a regex. Therefore, many backslashes must be doubled in Java code.

| What to find | Regex pattern | String literal in Java |
| --- | --- | --- |
| One or more digits | \d+ | "\\d+" |
| One or more whitespace characters | \s+ | "\\s+" |
| A literal dot | \. | "\\." |
| A literal backslash | \\ | "\\\\" |
| Uppercase letters from A to Z | [A-Z] | "[A-Z]" |
| String starting with ID- | ^ID- | "^ID-" |

Some commonly used regex syntax:

- **.**: any character except certain line-terminator characters in default mode.
- **[0-9]**, **[A-Z]**, **[^,]**: character classes.
- **+**: at least once; **\***: zero or more times; **?**: zero or one time; **{n}**: exactly n times.
- **^** and **$**: start-of-string and end-of-string anchors (can change in MULTILINE mode).
- **(...)**: capturing group; **(?:...)**: non-capturing group.
- **(?i)**: flag to ignore uppercase/lowercase differences; **(?m)**: makes ^/$ operate per line.
- **\\s+**: matches runs of whitespace characters; **\\d{4}**: exactly four digits.

Example removing whitespace only **at the beginning**:

~~~java
String input = "   Java   regex   ";
String first = input.replaceFirst("^\\s+", ""); // "Java   regex   "
String all   = input.replaceAll("\\s+", " ");   // " Java regex "
~~~

The two lines serve different goals: using **^** to select only the start of the string, or normalizing all whitespace runs. If you want the entire string to match an exact format, use appropriate start/end anchors rather than assuming replaceAll checks the whole string.

## 4. Capturing Groups: Reusing What Was Found

Regex **(...)** numbers capturing groups in the order of their opening parentheses. The replacement uses **$1**, **$2**... to retrieve each group, **$0** to retrieve the entire match, and **${name}** to retrieve a group named with **(?<name>...)**. In the date-reordering example using **$3/$2/$1** in section 2: the third group contains the day, the second group contains the month, and the first group contains the year.

When you only need to group regex branches without changing group numbers, use **(?:...)**. An optional group that was declared but did not participate in a match is replaced with an empty string; referencing a nonexistent group, however, is an error. The next lesson dives deeper into nested groups, named groups, and reference rules.

## 5. Finding and Inserting Literal Text

For user-supplied search text like **a.b**, **Pattern.quote(needle)** causes the dot to be interpreted literally instead of as a wildcard. For text to be inserted such as **$5\backup**, **Matcher.quoteReplacement(value)** preserves the dollar sign and backslash, avoiding mistaking **$5** for a group reference.

The two quote APIs protect **two independent parameters**; do not use them interchangeably. If both the search part and the replacement part are literal strings, **String.replace(target, replacement)** is simpler. The lessons on special characters and quoteReplacement further clarify each case and how to test them.

## 6. Comparison with String.replace

**String.replace** operates literally and does not parse regex:

~~~java
String input = "a.b 1.2";

System.out.println(input.replace(".", "-"));      // a-b 1-2
System.out.println(input.replaceAll("\\.", "-")); // a-b 1-2
System.out.println(input.replaceAll(".", "-"));    // -------
~~~

- **replace(CharSequence, CharSequence)** replaces all occurrences of fixed text.
- **replace(char, char)** replaces all occurrences of a fixed character.
- **replaceAll(regex, replacement)** replaces every substring matching a regular expression.
- **replaceFirst(regex, replacement)** replaces only the first matching substring.

For ordinary literal replacement needs, use **replace** to avoid writing regex and to avoid special replacement rules. For example, **"a$b".replace("$", "$$")** returns **"a$$b"** without needing to quote the replacement.

## 7. Behavior in Edge Cases

**No match found:** "abc".replaceAll("\\d+", "#") yields "abc"; this is normal behavior.

**Zero-length matches:** a regex with anchors or lookaheads can match at positions between characters without consuming characters:

~~~java
System.out.println("abc".replaceFirst("^", ">>"));  // >>abc
System.out.println("abc".replaceAll("(?=b)", "|")); // a|bc
~~~

**Non-overlapping matches:** "ababa".replaceAll("aba", "X") is **"Xba"**, not the result of replacing all possible overlapping starting positions.

**Multiple lines:** the dot **.** does not match certain line-terminator characters by default. If you want the dot to include line breaks, consider **DOTALL** mode, such as the **(?s)** prefix. The **(?m)** flag makes ^ and $ match per line; the two flags do not replace each other.

**Regex/replacement errors:** an invalid regex such as **[** throws **PatternSyntaxException**; an invalid group reference or malformed **$**/**\\** syntax in the replacement can throw **IllegalArgumentException** or **IndexOutOfBoundsException**. A null parameter can lead to **NullPointerException**. You should validate inputs and report clear error messages to the user.

**Immutable String:**

~~~java
String original = "a1 b2";
String updated = original.replaceAll("\\d", "#");

System.out.println(original); // a1 b2
System.out.println(updated);  // a# b#
~~~

Calling replaceAll while ignoring the return value leaves the **original** variable completely unchanged.

## 8. Reusing Pattern and Dynamic Replacement

If processing many strings with the same regex, compile the Pattern once:

~~~java
import java.util.List;
import java.util.regex.Pattern;

public class ReusePatternDemo {
    public static void main(String[] args) {
        Pattern digits = Pattern.compile("\\d+");

        for (String value : List.of("A12", "B345", "C6")) {
            System.out.println(digits.matcher(value).replaceAll("#"));
        }
    }
}
~~~

Save as **ReusePatternDemo.java**, run:

~~~bash
javac ReusePatternDemo.java
java ReusePatternDemo
~~~

Stdout:

~~~text
A#
B#
C#
~~~

**Pattern** is an immutable object and can be shared across threads. **Matcher** stores the state of a single search pass and should not be shared for concurrent operations across threads.

Since Java 9, **Matcher.replaceAll(Function<MatchResult, String>)** allows computing a different replacement for each match. The string returned by the function is still interpreted according to replacement syntax; if you want to literally insert computed content containing **$** or a backslash, use **Matcher.quoteReplacement**. The dedicated lesson on callbacks analyzes how to read groups, manage state, and handle errors.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Cause | Solution |
| --- | --- | --- |
| replaceAll(".", "") wipes out almost all text | The dot is a wildcard | Use "\\." or Pattern.quote(".") |
| Writing "\d" causes Java to report an escape error | Java Strings require escaping backslashes | Use "\\d" in Java code |
| Replacement containing "$" leads to a group error | $ is parsed as a group reference | Use Matcher.quoteReplacement |
| Only the first occurrence is replaced when all were intended | Using replaceFirst | Use replaceAll |
| Wanting to find fixed text but regex matches too broadly | Literal data is interpreted as regex | Use replace or Pattern.quote |
| Result does not change on the original variable | String is immutable | Assign the variable to the return value |
| Repeatedly processing many strings takes too long | The regex is recompiled many times | Create one Pattern and use a separate matcher per string |

Regexes with nested quantifiers or complex backtracking structures can execute very slowly on specially crafted long inputs. For external data, you should enforce reasonable size limits, restrict accepted regexes, and prefer literal searching when the problem only requires exact character matching.

## 10. Self-Check and How to Choose

Given the string **"x9 y88 z777"**, predict the output:

~~~java
String s = "x9 y88 z777";
System.out.println(s.replaceFirst("\\d+", "?"));
System.out.println(s.replaceAll("\\d+", "?"));
~~~

Stdout answer:

~~~text
x? y88 z777
x? y? z?
~~~

When you only want to replace **the single** first match, choose **replaceFirst**. When you want to replace **all** matches, choose **replaceAll**. When you do not need regular expressions, use **replace**. If you have to perform replacements on many strings with the same pattern, you can use a reusable **Pattern**; if data must be interpreted literally, use **Pattern.quote** and **Matcher.quoteReplacement** appropriately for each side.
