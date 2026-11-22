# Zero-Width Regex Matches and Positive-Width Delimiters in Java String.split()

## 1. Distinguishing the two match types

In Java, **String.split(String regex)** splits a string according to a **regular expression (regex)**. The nature of a regex match determines the boundaries and the resulting elements.

- A **positive-width match** consumes one or more characters. For example, the regex ":" matches and consumes a colon. Consumed characters do not appear in the tokens.
- A **zero-width match** only matches a **position between characters**, consuming no characters at all. For example, "(?=:)" matches right *before* a colon; "(?<=:)" matches right *after* a colon. The delimiter still belongs to one of the tokens because it is not consumed.

Anchors "^" (start of string), "$" (end of string), lookahead "(?=...)", and lookbehind "(?<=...)" commonly produce zero-width matches. Do not confuse **the length of a regex expression** with **the width of a match**: the expression "(?=:)" has multiple characters yet consumes 0 characters.

**The most important rule of String.split:** if a regex produces a **zero-width match right at the start of the string**, that match **does not create a leading empty element**. Conversely, if a regex produces a **positive-width match at the start**, it **does create a leading empty element**. These two behaviors differ even when using the same **limit** value.

## 2. Same string, different regexes

Consider the input **":a:b"**:

~~~text
Boundary:   0   1   2   3   4
Character:   :   a   :   b
~~~

| Regex | Match characteristics | Resulting tokens |
| --- | --- | --- |
| ":" | Consumes the two ":" characters at character indices 0 and 2 | ["", "a", "b"] |
| "(?=:)" | Zero-width lookahead before the two ":" characters | [":a", ":b"] |
| "(?<=:)" | Zero-width lookbehind after the two ":" characters | [":", "a:", "b"] |

**With ":"**, the colon at index 0 is consumed; the segment before it is the empty string, so the first token is "". The delimiter is no longer in the result.

**With "(?=:)"**, the regex only checks whether the next character is ":". It matches at boundaries 0 and 2. The zero-width match at boundary 0 does not create an empty token; boundary 2 separates ":a" and ":b". Both ":" characters remain at the start of the tokens because they were not consumed.

**With "(?<=:)"**, the regex matches boundaries 1 and 3 right after ":". Therefore, the colon stays at the end of the preceding token: [":", "a:", "b"].

## 3. Standalone Java 17+ program

Save the following as **ZeroWidthSplitDemo.java**:

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class ZeroWidthSplitDemo {
    private static void show(String label, String[] parts) {
        // Wrap each token in quotes so empty strings are clearly visible.
        String visible = Arrays.stream(parts)
                .map(s -> "'" + s + "'")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " -> " + visible
                + " (n=" + parts.length + ")");
    }

    public static void main(String[] args) {
        String input = ":a:b";
        show("positive ':'", input.split(":"));
        show("zero '(?=:)'", input.split("(?=:)"));
        show("zero '(?<=:)'", input.split("(?<=:)"));

        show("zero '^'", "abc".split("^", -1));
        show("zero '$'", "abc".split("$", -1));
        show("zero empty regex", "abc".split("", -1));

        show("positive default", "a,b,,".split(","));
        show("positive -1", "a,b,,".split(",", -1));
        show("positive 2", "a,b,,".split(",", 2));
    }
}
~~~

Compile and run:

~~~bash
javac ZeroWidthSplitDemo.java
java ZeroWidthSplitDemo
~~~

Exact output:

~~~text
positive ':' -> ['', 'a', 'b'] (n=3)
zero '(?=:)' -> [':a', ':b'] (n=2)
zero '(?<=:)' -> [':', 'a:', 'b'] (n=3)
zero '^' -> ['abc'] (n=1)
zero '$' -> ['abc', ''] (n=2)
zero empty regex -> ['a', 'b', 'c', ''] (n=4)
positive default -> ['a', 'b'] (n=2)
positive -1 -> ['a', 'b', '', ''] (n=4)
positive 2 -> ['a', 'b,,'] (n=2)
~~~

The **show** method wraps each token in single quotes and prints **n** (the element count). This helps distinguish empty tokens from an empty array; **Arrays.toString** does not wrap strings in quotes by default and easily causes confusion when tokens are "".

## 4. Why can zero-width matches still split?

You can picture the algorithm as follows:

1. Find regex matches from left to right.
2. Put the segment before the match into a token, then resume scanning the remainder from **the end of the matched regex**.
3. If the match consumed characters, those characters act as the delimiter and are discarded. If the match has zero width, the boundary can still split the string, but **no characters are removed**.
4. Handle the remainder and trailing empty tokens according to the **limit** value.

Specifically, a **zero-width match at index 0** does not produce a "" token. If the regex produces a **positive-width match at index 0**, the leading "" token is produced. Zero-width matches in the middle of the string still create boundaries as usual; Java advances the match search to avoid repeatedly matching the same position.

Anchors at the two ends show the difference:

- **"abc".split("^", -1)** → ["abc"]. "^" is a zero-width match at the start, so there is no leading "" token even with a negative limit.
- **"abc".split("$", -1)** → ["abc", ""]. "$" is a zero-width match at the end, creating a trailing "" token, and limit -1 keeps it.
- **"abc".split("$")** → ["abc"]. The default limit 0 removes trailing empty tokens.
- **"abc".split("", -1)** → ["a", "b", "c", ""]. An empty regex can match multiple boundaries: it does not create a leading "" but can still create a trailing "" when limit is negative.

## 5. Do not confuse this with the limit parameter

**String.split(regex)** is equivalent to **String.split(regex, 0)**. The **limit** parameter has the following effects:

| limit | Meaning | "a,b,," with regex "," |
| --- | --- | --- |
| **0** (default) | Unlimited splits, **discards trailing empty tokens** | ["a", "b"] |
| **Negative**, e.g. **-1** | Unlimited splits, **keeps trailing empty tokens** | ["a", "b", "", ""] |
| **Positive**, e.g. **2** | At most **limit - 1** splits; last token holds the entire remainder | ["a", "b,,"] |
| **1** | No splits; returns the original string | ["a,b,,"] |

**Make a clear distinction:** limit 0 only discards **trailing empty** elements. It does not automatically remove **leading or middle** empty tokens created by a positive-width delimiter. Therefore **":a:b".split(":")** is ["", "a", "b"] even though the default limit is 0.

Meanwhile, **":a:b".split("(?=:)")** has no leading empty token **because of the zero-width match rule at the start**, not because limit 0 deleted that token. The rule at the start still holds if limit = -1.

A positive limit is a **maximum**, not a guarantee that the token count will always equal limit: if there are not enough matches, the resulting array may have fewer elements.

## 6. Choosing an expression for your needs

**Remove the delimiter from the result:** use a character-consuming regex, for example:

~~~java
String[] words = "red:green:blue".split(":");
// ["red", "green", "blue"]
~~~

**Keep the delimiter at the start of the next token:** use a lookahead:

~~~java
String[] words = "red:green:blue".split("(?=:)");
 // ["red", ":green", ":blue"]
~~~

**Keep the delimiter at the end of the preceding token:** use a lookbehind:

~~~java
String[] words = "red:green:blue".split("(?<=:)");
 // ["red:", "green:", "blue"]
~~~

The three snippets above are illustrative fragments that can be placed inside a method. Lookahead/lookbehind only **inspect context**, so the delimiter is preserved.

**Beware of special regex characters:** the dot "." is a regex matching almost any character, not a literal period. Thus **"a.b.c".split(".")** does not return ["a", "b", "c"]; with limit 0, the result is an empty array because all trailing empty tokens are discarded. Split on a literal dot using escaping or **Pattern.quote**:

~~~java
String[] a = "a.b.c".split("\\.");
String[] b = "a.b.c".split(java.util.regex.Pattern.quote("."));
// Both produce ["a", "b", "c"].
~~~

Distinguish between **Java string escaping** and **regex escaping**: the Java string "\\." produces the regex that matches a literal dot. For a literal "|", you can use "\\|" or **Pattern.quote("|")**.

## 7. Common mistakes

1. **Assuming zero-width matches cannot split:** they still define boundaries; they just do not remove characters.
2. **Expecting a leading lookahead to produce an empty token:** a zero-width match at index 0 is skipped for creating a leading token.
3. **Thinking the default limit removes all empty tokens:** only **trailing** empty tokens are removed.
4. **Confusing "^" and "$" with delimiter characters:** these are position anchors; they do not consume character delimiters.
5. **Using unescaped "." or "|" as literal characters:** the argument to split is a regex, so escape them or use Pattern.quote.
6. **Not checking token counts when printing arrays:** "" tokens are hard to see without wrapping in quotes and printing parts.length.

### Exercises with answers

**Exercise 1:** What does the string "::x" produce when split by the following two expressions?

- **"::x".split(":")** → ["", "", "x"]. Two matches consume the two consecutive ":" characters; there are leading and middle empty tokens.
- **"::x".split("(?=:)")** → [":", ":x"]. The leading zero-width match produces no empty token; the match at index 1 splits the string while keeping the colons.

**Exercise 2:** Why does **"x:".split("(?<=:)", -1)** give ["x:", ""]?

- The lookbehind creates a zero-width boundary **after** the ":" at the end of the string. limit -1 keeps the trailing empty token; with the default limit 0, this token is discarded.

## 8. Remember

Before calling **String.split**, ask yourself: **(1)** does the regex consume characters, **(2)** is there a zero-width match right at the start of the string, and **(3)** does limit keep trailing empty tokens? These three questions directly explain the difference between zero-width regexes and positive-width delimiters in Java.