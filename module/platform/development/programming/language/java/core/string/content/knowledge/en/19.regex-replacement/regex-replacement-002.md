# Capturing Groups and Group References in Replacement Strings — Java Regex

When processing text, you may need to **reorder, preserve, or combine parts of a matched segment**. Java Regex lets you use *capturing groups* in the search expression and *group references* in the replacement string to reuse the matched data itself.

Example converting the date `2026-10-23` to `23/10/2026`:

```java
String result = "2026-10-23".replaceAll(
        "(\\d{4})-(\\d{2})-(\\d{2})",
        "$3/$2/$1");
System.out.println(result); // 23/10/2026
```

The three groups capture the year, month, and day in order. The replacement string uses `$3` (day), `$2` (month), and `$1` (year). This is a way to **rearrange data from a match** instead of slicing strings manually.

## 1. How Are Capturing Groups Created and Numbered?

Parentheses `(...)` in a regex create a **capturing group**. When a match is found, Java records the substring that each group matched.

Consider the regex:

```regex
(\d{4})-(\d{2})-(\d{2})
```

With the input `2026-10-23`:

| Group number | Value | Meaning |
| --- | --- | --- |
| 0 | `2026-10-23` | **Entire** matched segment |
| 1 | `2026` | First group: year |
| 2 | `10` | Second group: month |
| 3 | `23` | Third group: day |

Numbering rule: count **in the order of opening parentheses `(` of capturing groups, from left to right**, starting from 1. Group 0 is always the entire match and does not require its own pair of parentheses.

With nested groups `((ab)(cd))` on `abcd`, group 1 is `abcd`, group 2 is `ab`, and group 3 is `cd`, according to the positions of the three opening parentheses.

When you need to group parts of a regex but **do not want to create a capturing group**, use `(?:...)` (non-capturing group):

```regex
(?:Mr\.|Ms\.)\s+([A-Za-z]+)
```

`(?:Mr\.|Ms\.)` groups the two prefix alternatives without taking up a group number; `([A-Za-z]+)` is **group 1** to capture the name. If you do not need to reference a group, you should use `(?:...)` to avoid shifting the numbering of important groups.

## 2. Group References in Replacement Strings

`String.replaceAll(regex, replacement)` and `String.replaceFirst(regex, replacement)` use the replacement syntax of `Matcher`:

| Syntax in replacement | Meaning |
| --- | --- |
| `$1`, `$2`, ... | Inserts the text matched by capturing group 1, 2, ... |
| `$0` | Inserts the **entire** match (group 0) |
| `${name}` | Inserts the text matched by a **named group** |
| `\$` at runtime | Inserts a literal `$` character |
| `\\` at runtime | Inserts a literal `\` character |

In Java source code, `"$1"` does not need the `$` escaped. When you want to write a literal `$` directly in a Java replacement string, the runtime value `\$` is written as `"\\$"`; when you want to insert a literal `\` character, you need to express the runtime value `\\`, which is the Java string `"\\\\"`. For non-fixed runtime data, using `Matcher.quoteReplacement` is simpler and safer.

`${name}` is only for **group names**; do not write `${1}` instead of `$1`.

Example using group 0 and group 1:

```java
String s = "id=42";
System.out.println(s.replaceAll("(\\d+)", "<$0|$1>"));
// id=<42|42>
```

Both group 0 and group 1 are `42` in this example because the regex contains a single group enclosing the entire match. If the regex has parts outside parentheses, group 0 and group 1 can differ.

### Distinguishing References When Searching vs. When Replacing

**In the search regex**, `\1` means requiring the subsequent text to equal the exact content matched by group 1 (a backreference); in a Java string it must be written `"\\1"`.

**In the replacement**, `$1` means inserting the content of group 1 into the output.

```java
System.out.println(
        "ha ha".replaceAll("(\\w+)\\s+\\1", "$1"));
// ha
```

The regex `(\\w+)\\s+\\1` recognizes a word standing next to itself after whitespace; `"$1"` keeps one word.

## 3. Named Groups: `(?<name>...)` and `${name}`

With regexes that have many groups, `$1` and `$2` can easily cause confusion. Java lets you assign a name using `(?<name>regex)`, and then reference it with `${name}` in the replacement.

Example converting `"Last, First"` to `"First Last"`:

```java
String names = "Nguyen, An; Tran, Binh";
String reordered = names.replaceAll(
        "(?<last>[A-Za-z]+),\\s*(?<first>[A-Za-z]+)",
        "${first} ${last}");

System.out.println(reordered);
// An Nguyen; Binh Tran
```

Explanation: `(?<last>[A-Za-z]+)` captures the last name, `,\\s*` matches the comma and any whitespace immediately following it, and `(?<first>[A-Za-z]+)` captures the first name; `${first} ${last}` moves the first name before the last name.

A named group **is still numbered** like an ordinary group; it does not lose the ability to be accessed by number. A group name starts with a letter, followed by letters or digits, and each name must be unique within the regex.

The regex `[A-Za-z]+` here is used for unaccented Latin-letter sample data. Real-world personal names may contain Vietnamese diacritics, hyphens, spaces, and more complex rules; you should not use this illustrative regex to parse full personal names.

## 4. Standalone Runnable Java Example

Create the file `RegexGroupReplacementDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexGroupReplacementDemo {
    public static void main(String[] args) {
        String date = "2026-10-23";
        System.out.println("date     = " + date.replaceAll(
                "(\\d{4})-(\\d{2})-(\\d{2})",
                "$3/$2/$1"));

        String names = "Nguyen, An; Tran, Binh";
        System.out.println("names    = " + names.replaceAll(
                "(?<last>[A-Za-z]+),\\s*(?<first>[A-Za-z]+)",
                "${first} ${last}"));

        // (?:...) groups regex elements without creating a capturing group.
        System.out.println("noncap   = " + "a1 b2".replaceAll(
                "(?:[a-z])([0-9])",
                "[$1]"));

        // $0 is the entire match; $1 is the first group.
        System.out.println("full     = " + "id=42".replaceAll(
                "(\\d+)",
                "<$0|$1>"));

        // An optional group that did not match is replaced with an empty string.
        System.out.println("optional = " + "ab1 a2".replaceAll(
                "(a)(b)?(\\d)",
                "[$1|$2|$3]"));

        // $ and \ in the replacement are literal characters.
        String literal = "$5\\path";
        System.out.println("literal  = " + "amount=42".replaceAll(
                "\\d+",
                Matcher.quoteReplacement(literal)));

        // Replace with a value computed separately for each match.
        Matcher matcher = Pattern.compile("(\\d+)").matcher("a12 b3");
        StringBuilder out = new StringBuilder();
        while (matcher.find()) {
            int doubled = Integer.parseInt(matcher.group(1)) * 2;
            matcher.appendReplacement(
                    out, Matcher.quoteReplacement("[" + doubled + "]"));
        }
        matcher.appendTail(out);
        System.out.println("computed = " + out);
    }
}
```

Run with JDK 17 or later:

```bash
javac RegexGroupReplacementDemo.java
java RegexGroupReplacementDemo
```

Exact stdout output:

```text
date     = 23/10/2026
names    = An Nguyen; Binh Tran
noncap   = [1] [2]
full     = id=<42|42>
optional = [a|b|1] [a||2]
literal  = amount=$5\path
computed = a[24] b[6]
```

`String` in Java is immutable; `replaceAll` returns a new result without modifying the original string. If no segment matches, the returned content equals the input. Each match of `replaceAll` uses **the groups captured in that specific match**.

## 5. Optional Groups, Repeated Groups, and Multiple Matches

### Groups That May Not Match

With the regex `(a)(b)?(\\d)` on `"ab1 a2"`:

- Match `ab1`: group 1 is `a`, group 2 is `b`, group 3 is `1`.
- Match `a2`: group 1 is `a`, **group 2 did not participate in the match**, group 3 is `2`.

Because group 2 exists in the pattern, the reference `$2` is valid. However, when this group does not participate in a match, Java inserts an **empty string**:

```java
System.out.println(
        "ab1 a2".replaceAll("(a)(b)?(\\d)", "[$1|$2|$3]"));
// [a|b|1] [a||2]
```

**A group that exists but did not match** is different from **an undeclared group**. Referencing a nonexistent group throws an error.

### Group Under a Quantifier

For example, the regex `([a-z])+` matches `abc`, but group 1 contains **the last captured match**, which is `c`; the group does not store a list of all repetitions. If you want group 1 to contain all of `abc`, move the quantifier inside: `([a-z]+)`.

### Replacing Multiple Matches

`replaceAll` iterates through **non-overlapping** matches in left-to-right order and applies the replacement string to each match:

```java
System.out.println(
        "A=12; B=345".replaceAll("(\\d+)", "[$1]"));
// A=[12]; B=[345]
```

`$1` is `12` the first time and `345` the next time. `replaceFirst` replaces only the first match.

## 6. Keeping Regex and Replacement in Their Proper Roles

In the **search regex**, a backreference requires subsequent text to match a previously captured group again; in the **replacement**, **$1**, **$2**, and **${name}** insert data from groups into the result. **String.replace** works with literal strings, so it does not expand group references.

When you need to insert external content such as prices or file paths containing **$** and backslashes, use **Matcher.quoteReplacement**. However, if you intentionally use **$1** to reuse a capturing group, do not quote the entire template. The next lessons cover escape syntax and literal insertion techniques separately.

## 7. Accessing Groups to Compute Per-Match Values

**String.replaceAll** is suitable when every match uses the same capturing-group template. When you need to compute different results, **Matcher.find()** combined with **group(1)**, **appendReplacement**, and **appendTail** lets you extract groups, compute a new string, and keep the unmatched tail; the program in section 4 illustrated this workflow.

Since Java 9, **Matcher.replaceAll(Function<MatchResult, String>)** simplifies per-match replacement. In Java 17, the **MatchResult** callback lets you read groups by index, while **Matcher** also supports named groups. Both the value passed to appendReplacement and the string returned by the callback still follow replacement syntax, so quote them when you want to insert literal text.

## 8. Common Mistakes

1. **Putting `$1` in the search regex.** A group reference in a *regex* is `\1`; `$1` is for the *replacement*.
2. **Confusing non-capturing groups with capturing groups.** `(?:...)` does not create a group and has no number to reference. With a regex consisting only of non-capturing groups, a replacement `$1` is invalid.
3. **Numbering by closing parentheses.** You must number from left to right by the **opening parentheses** of capturing groups, including for nested groups.
4. **Forgetting a group may not participate in a match.** A group that exists but did not match is replaced by an empty string; a group that does not exist at all causes an error.
5. **Passing raw user strings as the replacement.** The characters `$` and `\` can have special meaning. If literal text is needed, use `Matcher.quoteReplacement`.
6. **Using `$10` and misunderstanding it.** Numeric syntax is parsed as long as needed according to the number of groups that actually exist. With ten groups, `$10` references group 10; with one group, `$10` can mean group 1 followed by the character `0`. Named groups help reduce ambiguity.
7. **Expecting a repeated group to hold all captures.** `([a-z])+` usually leaves only the last capture; `([a-z]+)` keeps the entire sequence of characters in a single match.
8. **Using `String.replace` and expecting `$1` to work.** `String.replace(CharSequence, CharSequence)` performs literal replacement; it does not interpret regex or group references.
9. **Using illustrative regexes as parsers for complex data.** You may need to handle Unicode, quoted values, escape characters, or multi-level formats; choose an appropriate parser rather than relying on a few simple capturing groups.

An invalid regex can throw `PatternSyntaxException`; a syntactically invalid replacement or a reference to a nonexistent group can throw `IllegalArgumentException` or `IndexOutOfBoundsException` depending on the situation. You must clearly determine whether external data is allowed to carry regex/replacement syntax or is strictly literal text.

## 9. Practice Exercises

**Exercise 1.** Convert `user:100` to `100 (user)` using two groups:

```java
"user:100".replaceAll("([a-z]+):(\\d+)", "$2 ($1)")
// "100 (user)"
```

**Exercise 2.** Why does `"a1 b2".replaceAll("(?:[a-z])(\\d)", "$1")` produce `"1 2"`?

Because `(?:[a-z])` matches the letter without **creating a capturing group**, so group 1 is `(\\d)`. The letter is discarded when the entire match is replaced by just the digit.

**Exercise 3.** To literally insert the exact two characters `$1` when replacing digits:

```java
"abc42".replaceAll("\\d+", Matcher.quoteReplacement("$1"))
// "abc$1"
```

**Exercise 4.** Given the regex `(?<area>\\d{3})-(?<number>\\d{4})`, which replacement keeps only the digits after the hyphen?

`${number}` (you can also use `$2`, though a group name makes the meaning clearer).

**Exercise 5.** Why is `"abc".replaceAll("([a-z])+", "$1")` equal to `"c"`? Group 1 is repeated and keeps only the last capture. To keep the whole string, use `([a-z]+)`.

**Key takeaway:** `(...)` creates a capturing group; `(?:...)` only groups syntax; `$1` and `${name}` reuse group contents in the replacement; `Matcher.quoteReplacement` protects literal replacement text; `Matcher` is suitable when replacement requires separate computation per match.

**Official references:** [`String.replaceAll` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#replaceAll(java.lang.String,java.lang.String)), [`Matcher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html), [`Pattern`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html).
