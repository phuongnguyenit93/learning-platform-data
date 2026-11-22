# `String.replace(char, char)` — Replacing Every Matching Character in Java

## 1. Purpose and Meaning

`String.replace(char oldChar, char newChar)` is a method used to **replace all occurrences** of a `char` character unit with another `char` in a Java string. For example, `"banana".replace('a', 'o')` produces `"bonono"`: all three `a` characters are replaced. The method does not stop at the first match and does not require a manual loop to find each position.

Four key points to understand:

1. `oldChar` and `newChar` are two **`char`** arguments, written with single quotes such as `'a'`; they represent UTF-16 code units, not arbitrary character strings.
2. `replace(char,char)` finds and replaces **every exact match**. Matching is case-sensitive: `'a'` is different from `'A'`.
3. `String` is **immutable**. The method returns a `String` result; it does not modify the string it was called on. To keep the result, you must assign it to a variable or pass it where it is needed.
4. This is a **literal character** replacement operation, not a regular expression (*regex*). To replace an entire text segment with multiple `char`s, use the `replace(CharSequence, CharSequence)` overload; to process regex, use `replaceAll(String, String)`.

This lesson goes from syntax to runnable examples, distinguishing overloads, Unicode, and common mistakes when processing text data.

## 2. Syntax, Data Types, and Return Value

API declaration in Java SE 17:

```java
public String replace(char oldChar, char newChar)
```

| Component | Meaning |
| --- | --- |
| `oldChar` | The `char` unit to search for in the source string |
| `newChar` | The `char` unit that will replace each matching position |
| Return value | A `String` value containing the content after replacing matching positions |
| Matching rule | Compares exact `char` values; does not automatically ignore case, diacritics, or normalize Unicode |
| Scope | The entire string, from start to end; there is no parameter to limit the number of replacements |

Expression examples (placed inside a method, such as `main`):

```java
"banana".replace('a', 'o');   // "bonono"
"aaaa".replace('a', 'b');     // "bbbb"
"aba".replace('a', 'b');      // "bbb"
"Java".replace('a', 'A');     // "JAvA"
"Java".replace('A', 'x');     // "Java" (no 'A')
```

The lines above are **illustrative expressions**, not a standalone Java file. In Java, a `char` literal has exactly one UTF-16 code unit; `'a'` is a `char`, whereas `"a"` is a `String`. Passing two `String`s to `replace("a","o")` is still valid, but Java selects the **`CharSequence` overload**, not the overload being studied here.

The method does not take a `boolean` parameter controlling the number of replacements and has no `replace(char,char,int limit)` version in `String`. If you only want to replace the first occurrence or replace a specific range, you need to choose a different algorithm/API.

## 3. Complete Program: Every Matching Position Is Replaced

Save as `ReplaceCharDemo.java`:

```java
public class ReplaceCharDemo {
    public static void main(String[] args) {
        String original = "banana";
        String changed = original.replace('a', 'o');

        System.out.println(original);
        System.out.println(changed);
        System.out.println("aaaa".replace('a', 'b'));
        System.out.println("aba".replace('a', 'b'));
        System.out.println("a.b.a".replace('.', '-'));
        System.out.println("a$a$a".replace('$', '#'));
        System.out.println("Java".replace('x', 'y'));
        System.out.println("Java".replace('a', 'a'));
        System.out.println("Java".replace('a', 'A'));
        System.out.println("Java".replace('A', 'x'));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ReplaceCharDemo.java
java ReplaceCharDemo
```

Standard output:

```text
banana
bonono
bbbb
bbb
a-b-a
a#a#a
Java
Java
JAvA
Java
```

Explanation:
- `original` remains `banana`; the `changed` variable holds the result `bonono`.
- `"aaaa".replace('a','b')` replaces all four positions, and `"aba".replace('a','b')` yields `bbb`, not just the first `a`.
- `'.'` and `'$'` are treated as ordinary characters. They **do not carry regex meaning** in the `char,char` overload.
- There is no `'x'` in `Java`, so the content stays unchanged. `oldChar == newChar` also leaves the content unchanged.
- Replacement is case-sensitive: lowercase `a` in `Java` matches, while uppercase `A` is not present in `Java`.

## 4. Why Is This a Simultaneous Operation on Source Content?

The match condition is evaluated against the **original source string** in a single call. Newly inserted characters are not treated as new targets for "chained replacement" within that same call.

For example:

```java
System.out.println("aba".replace('a', 'b')); // bbb
```

From `aba`, the two `a` positions are replaced with `b`; the original `b` stays `b`. There is no second pass within this call to continue processing the `b` characters. Therefore, the result is `bbb`.

However, **chaining multiple `replace` calls** is a sequence of distinct transformations; each subsequent call sees the result of the previous one:

```java
System.out.println(
        "aba".replace('a', 'b').replace('b', 'c')); // ccc
System.out.println(
        "aba".replace('b', 'c').replace('a', 'b')); // bcb
```

This is a snippet placed in `main`. In the first line, `aba` becomes `bbb`, and then all `b`s become `c`. The second line starts with `aca`, then replaces `a` with `b` to become `bcb`. **Call order matters**; never assume two character replacements are always commutative.

If you want to perform a multi-character mapping simultaneously without letting newly replaced characters be processed by subsequent rules, you can iterate over the source string once, decide the replacement character for each position, and build a separate result. Avoid chaining `replace` calls when the second replacement must not affect characters just produced by the first.

## 5. `String` Is Immutable: The Result Must Be Retained

A common mistake:

```java
String text = "banana";
text.replace('a', 'o'); // Computes the result, but the result is discarded.
System.out.println(text); // banana
```

`replace` **does not modify** the `String` object that `text` points to. To use the content after replacement:

```java
String text = "banana";
text = text.replace('a', 'o');
System.out.println(text); // bonono
```

The subsequent assignment only makes the **variable** `text` reference the result; the original immutable `"banana"` string is not modified in content. If another variable still points to the old string, that variable continues to see `banana`.

In case the target character does not appear, the `String.replace(char,char)` documentation allows returning a reference to the called `String` itself. Therefore, **do not infer that calling `replace` always allocates a new object**. What is guaranteed at the programming level is the **result content** and **immutability**. To compare strings, use `equals`, not `==`, to guess whether a replacement occurred.

A `final String` variable cannot be reassigned:

```java
final String text = "banana";
String changed = text.replace('a', 'o'); // Valid.
// text = changed; // Compile error: cannot reassign a final variable.
```

This is an illustrative snippet. `final` on a variable prevents reassigning the reference, whereas `String` immutability prevents modifying the object's content; those are two different concepts.

## 6. Choosing the Right API When Working with a `char`

`String` has multiple replacement forms. This lesson uses **`replace(char,char)`** when both input and output are *one UTF-16 unit*; the two arguments in single quotes are handled as literal characters. Three similarly named options serve different purposes:

| API | What is searched | Number of replacements |
| --- | --- | --- |
| `replace(char, char)` | One exact `char` | All matching positions |
| `replace(CharSequence, CharSequence)` | A literal string segment, possibly longer than one `char` | All non-overlapping matches |
| `replaceFirst(String, String)` | Regex | First match |
| `replaceAll(String, String)` | Regex | All matches |

Example placed in `main`:

~~~java
System.out.println("a.b".replace('.', '/'));      // a/b
System.out.println("a.b".replace(".", "/"));      // a/b
System.out.println("a.b".replaceAll(".", "/"));   // ///
System.out.println("a.b".replaceFirst(".", "/")); // /.b
~~~

In regex, `.` has a special meaning; in both `replace` overloads, it is simply a dot. `replaceAll` and `replaceFirst` also interpret `$1` and backslashes in the replacement string according to regex syntax, whereas `replace` inserts the replacement literally. If you only need to change a single delimiter character, the `char,char` overload expresses intent most clearly; the comparison lesson later in the chapter covers capture groups, escaping, and regex choices in depth.

## 7. When Should You Choose `replace(char,char)`?

Choose the `char,char` overload when:
- The target is **exactly one** UTF-16 unit with a fixed value or passed via a `char` variable.
- You want to replace **every** matching position directly, such as changing delimiter `','` to `';'` or changing ASCII space `' '` to `'_'`.
- You do not need regex, capture groups, multi-character matching, or a replacement count limit.
- You want the result to keep the same number of UTF-16 units as the source (since each `char` is replaced with exactly one `char`).

A common use case is normalizing delimiters for an exact known character:

```java
String csvLike = "red,green,blue";
String separated = csvLike.replace(',', ';');
System.out.println(separated); // red;green;blue
```

This is a snippet in `main`. Replacement does not understand CSV syntax: if a comma is inside a double-quoted field, replacing all commas with semicolons can break the data structure. Use a CSV parser if you need format-aware semantics.

Similarly, `replace(' ', '_')` only replaces **space U+0020**; it does not replace all whitespace forms such as tabs, newlines, or non-breaking spaces. If you need rules based on character classes, choose an appropriate Unicode regex or handle code points explicitly.

## 8. Matching Scope: Case Sensitivity, Diacritics, and Unicode

`replace(char,char)` matches **each `char` exactly**. It does not know whether two letters are upper/lowercase variants or Vietnamese diacritical forms of the same base letter:

```java
System.out.println("Java".replace('a', 'o')); // Jovo
System.out.println("Java".replace('A', 'o')); // Java
System.out.println("café".replace('é', 'e')); // cafe
```

This is an illustrative snippet. The precomposed letter `é` is a Unicode BMP code point that fits in one `char`. However, Unicode also allows representing accented letters as **base letter + combining mark**; the two representations may look identical, but their `char` data differs.

Standalone program, save as `ReplaceUnicodeFormDemo.java`:

```java
public class ReplaceUnicodeFormDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";       // café: U+00E9
        String decomposed = "cafe\u0301";    // e + combining acute accent U+0301

        System.out.println(composed.replace('\u00E9', 'e'));
        System.out.println(decomposed.replace('\u00E9', 'e')
                .equals(decomposed));
        System.out.println(composed.equals(decomposed));
    }
}
```

```bash
javac -encoding UTF-8 ReplaceUnicodeFormDemo.java
java ReplaceUnicodeFormDemo
```

```text
cafe
true
false
```

Because `decomposed` **does not contain a `char` element with value U+00E9**, replacing `'é'` has no effect on that string. If business logic requires handling equivalent Unicode representations, consider normalizing with `java.text.Normalizer` before applying replacement rules; choose the appropriate normalization form and understand that normalization can also change the code point sequence.

## 9. `char` Is a UTF-16 Unit, Not Every Displayed Character

Java `char` is 16 bits wide, holding **one UTF-16 code unit**. Unicode code points outside the BMP (for example, many emojis) require **two** `char`s: a high surrogate and a low surrogate. A `char` literal cannot represent an **entire** emoji like `🙂` as a single `char` value.

Suppose a string contains two emojis:

```java
String emoji = "A🙂B🙂";
System.out.println(emoji.length()); // 6 char units
System.out.println(emoji.codePointCount(0, emoji.length())); // 4 code points
```

You cannot use `emoji.replace('🙂', '*')` as a way to replace a whole emoji: a supplementary emoji outside the BMP does not fit in a `char` literal. Choose the string overload to match the full surrogate pair:

```java
String result = emoji.replace("🙂", "*");
System.out.println(result); // A*B*
```

Complete program, save as `ReplaceEmojiDemo.java`:

```java
public class ReplaceEmojiDemo {
    public static void main(String[] args) {
        String text = "A🙂B🙂";

        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));
        System.out.println(text.replace("🙂", "*"));
        System.out.println(text.replace('A', 'X'));
        System.out.println(text);
    }
}
```

```bash
javac -encoding UTF-8 ReplaceEmojiDemo.java
java ReplaceEmojiDemo
```

```text
6
4
A*B*
X🙂B🙂
A🙂B🙂
```

Calling `replace("🙂", "*")` replaces the entire **string segment** consisting of two code units; `replace('A','X')` only replaces the single `A` code unit. Neither modifies `text`.

**Surrogate risk:** calling `replace(char,char)` on an individual high surrogate or low surrogate of a non-BMP code point can break valid UTF-16 pairs and produce unpaired surrogate sequences. When transforming by Unicode code point, use `String.codePoints()` and `StringBuilder.appendCodePoint()` or string-processing methods with proper boundaries; when the requirement is "one user-perceived character," you must also consider *grapheme clusters* (such as letters with combining marks or emojis joined with ZWJ).

## 10. Writing Helper Methods Taking `char` Parameters and Managing Results

A character-replacement helper method can be very short:

```java
import java.util.Objects;

public class ReplaceUtility {
    public static String replaceEvery(
            String input, char from, char to) {
        Objects.requireNonNull(input, "input");
        return input.replace(from, to);
    }

    public static void main(String[] args) {
        String original = "a-a-a";
        String updated = replaceEvery(original, '-', '_');

        System.out.println(updated);
        System.out.println(original);
    }
}
```

Save as `ReplaceUtility.java` and run:

```bash
javac -encoding UTF-8 ReplaceUtility.java
java ReplaceUtility
```

```text
a_a_a
a-a-a
```

`Objects.requireNonNull` gives a clear error at the method boundary when `input` is `null`; calling `input.replace(...)` itself cannot work if `input` is `null` anyway. The two `char` parameters are primitive values, so they cannot be `null`. The method returns a new string by **value**; other references to `original` continue to see the original content.

You can pass `char` variables instead of literals:

```java
char delimiter = ',';
char newDelimiter = ';';
String converted = "a,b,c".replace(delimiter, newDelimiter);
// converted has content "a;b;c".
```

This is a standalone expression snippet that needs to be placed inside a Java method body. If the system allows arbitrary character selection from users, verify that the input value has exactly **one UTF-16 unit** before converting it to `char`; do not call `input.charAt(0)` and silently drop the rest of a multi-unit string.

## 11. Cost, Multiple Replacements, and Choosing the Right Tool

Algorithmically, to locate all matching positions, Java must inspect the string content being processed. For a single replacement on a string of length `n` code units, scanning cost can be considered **O(n)**; result creation and allocation optimizations depend on the JDK version and implementation. Do not rely on assuming `replace` always creates a new object, nor use reference comparison to test whether a replacement happened.

When **multiple consecutive transformations** are needed, code like the following is easy to read, though each call is an independent processing step:

```java
String normalized = "a.b-c".replace('.', '_').replace('-', '_');
// normalized: "a_b_c"
```

For very large data volumes and many character rules, you can scan once and write to a `StringBuilder` or array to avoid repeated scans; choose based on actual complexity and performance measurements. For example, if several different source characters all need to be replaced with `'_'`, a loop with a `switch` over each `char` can express simultaneous replacement more clearly; for complex Unicode, consider iterating over code points rather than individual `char`s.

Do not optimize prematurely: `replace(char,char)` is concise, readable, communicates intent clearly, and is usually appropriate for single-character replacements.

## 12. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling `text.replace('a','o')` and ignoring the result | `String` is immutable; variable `text` does not change | Reassign `text = text.replace(...)` or keep the result variable |
| Thinking it only replaces the first occurrence | `replace(char,char)` replaces **all** matching positions | Use a first-match replacement algorithm if that is the requirement |
| Using `replaceAll(".", "_")` to match a literal dot | `.` in regex matches many characters | Use `replace('.', '_')` or `replace(".", "_")` |
| Thinking `'a'` and `'A'` are the same character | The method matches exact values | Apply a separate case policy if needed |
| Using `char` for a supplementary emoji outside BMP | One emoji can require two UTF-16 units | Use the `replace(CharSequence,CharSequence)` overload with the full string |
| Assuming `'é'` matches every way to write an accented e | Unicode data may be precomposed or decomposed | Normalize Unicode if required |
| Chaining multiple `replace` calls when wanting simultaneous mapping | Later calls also process characters produced by earlier calls | Write a per-position mapping against the original source |
| Checking `result == original` to see if replacement occurred | `==` checks identity, not content | Use `equals` or compare content as required |
| Assuming `replace(' ', '_')` replaces all whitespace | Only replaces space U+0020 | Choose whitespace handling according to specification |
| Using single-character replacement for syntax-aware formats | Does not understand quotes/escapes/grammar of CSV, URL, JSON... | Use the corresponding parser/encoder |
| Breaking surrogate pairs by replacing half of one | `char` is not always a complete code point | Transform by code point or full string |

## 13. Self-Check Exercises

**Exercise 1.** Given `String s = "aAaA";`, what is the result of `s.replace('a','x')`? Why do the two `A` characters stay unchanged?

**Exercise 2.** Predict the output:
```java
String value = "abba";
String result = value.replace('a', 'b');
System.out.println(value);
System.out.println(result);
```

**Exercise 3.** Why do `"a.b".replace('.', '_')` and `"a.b".replaceAll(".", "_")` produce two different results?

**Exercise 4.** If you need to change every `"cat"` segment to `"dog"` in `"cat-cat"`, which overload would you use? Why cannot `replace(char,char)` satisfy this directly?

**Exercise 5.** Given `String source = "A🙂A";`, explain why `replace('A','X')` works as expected, while replacing the emoji with a `char` literal is not a valid option.

Answers:
- Exercise 1: `"xAxA"` because `'a'` differs from `'A'`.
- Exercise 2: prints `abba` then `bbbb`; no character array mutation is involved, these are two immutable `String` values.
- Exercise 3: `char`-based `replace` looks for the exact dot character so it produces `a_b`; the regex `.` in `replaceAll` matches three characters so it produces `___`.
- Exercise 4: `"cat-cat".replace("cat", "dog")` yields `"dog-dog"`; an entire three-`char` segment must be replaced with another segment.
- Exercise 5: `A` is one UTF-16 unit; the `🙂` emoji requires a surrogate pair, so it must be replaced using the string `"🙂"` or by code point processing.

## 14. Key Takeaways

- `String.replace(char oldChar, char newChar)` replaces **every `char` matching `oldChar`** in the string, without using regex and without stopping at the first match.
- The result is a `String`; the source string content remains immutable. To use the result, **keep the return value**.
- `char` represents one UTF-16 unit. Choose the right overload for the target unit: single `char`, literal `CharSequence` segment, or regex pattern.
- Matching is exact, sensitive to case and Unicode representation; if business requirements differ, you must explicitly define normalization/handling rules.
- Chained `replace` calls execute in order; each call sees the output of the previous call.

## Java SE 17 Documentation

- [`String.replace(char,char)`, `replace(CharSequence,CharSequence)` and `replaceAll` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Character`, UTF-16 and surrogates — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [`Normalizer` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
