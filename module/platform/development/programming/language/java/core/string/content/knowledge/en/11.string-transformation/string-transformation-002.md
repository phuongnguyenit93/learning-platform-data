# `String.replace(CharSequence, CharSequence)` — Literal String Replacement in Java

When you need to replace one text segment with another in a `String`, Java provides the **`replace(CharSequence target, CharSequence replacement)`** overload. The method finds **contiguous, exact-matching, non-overlapping** occurrences of `target` and replaces them with `replacement`. Both strings are treated as **literal text**, not regular expressions (regex).

Example:

```java
String text = "Java Java Core";
String updated = text.replace("Java", "Kotlin");

System.out.println(updated); // Kotlin Kotlin Core
System.out.println(text);    // Java Java Core
```

This is a **content transformation** operation on a string: the return value is a `String` holding the new content; the original `String` object remains unchanged because `String` is *immutable*.

## 1. Syntax and Meaning of the Two Parameters

API signature:

```java
public String replace(CharSequence target,
                      CharSequence replacement)
```

- **`target`:** the character sequence to search for. For example, `"old"` or `" "`. Occurrences are matched by **exact content**, case-sensitively.
- **`replacement`:** the character sequence inserted in place of each match. It is used **literally**; characters such as `$` and `\` in `replacement` carry no special regex meaning.
- **Return value:** the resulting string after replacing all **non-overlapping** matches of `target`. If no segment matches, the resulting content equals the original content.
- **Receiver object:** the source string, such as `text` in `text.replace(target, replacement)`.
- **Parameter type:** `CharSequence`, so it accepts not only `String` but also `StringBuilder` and other `CharSequence` implementations.

Common cases:

| Source string | `target` | `replacement` | Resulting content |
| --- | --- | --- | --- |
| `"red blue red"` | `"red"` | `"green"` | `"green blue green"` |
| `"2026/10/22"` | `"/"` | `"-"` | `"2026-10-22"` |
| `"a.b.c"` | `"."` | `"-"` | `"a-b-c"` |
| `"hello"` | `"ll"` | `"LL"` | `"heLLo"` |
| `"hello"` | `"xyz"` | `"?"` | `"hello"` |
| `"AB"` | `"a"` | `"x"` | `"AB"` |

Notice `"a.b.c".replace(".", "-")` replaces the two exact dot characters. Here, `.` is **not** the regex operator meaning "any character."

### Complete Example Runnable on Java 17+

Save the file `ReplaceBasicDemo.java`:

```java
public class ReplaceBasicDemo {
    public static void main(String[] args) {
        String original = "Java Java Core";
        String updated = original.replace("Java", "Kotlin");

        System.out.println(updated);
        System.out.println(original);
        System.out.println("a.b.c".replace(".", "-"));
        System.out.println("a.b.c".replace("\\.", "-"));

        System.out.println(
                "abc".replace("xyz", "?").equals("abc"));
        System.out.println("Java".replace(
                new StringBuilder("av"),
                new StringBuilder("123")));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ReplaceBasicDemo.java
java ReplaceBasicDemo
```

Output:

```text
Kotlin Kotlin Core
Java Java Core
a-b-c
a.b.c
true
J123a
```

Explanation:

1. Both occurrences of `"Java"` are replaced with `"Kotlin"`. `original` does not change.
2. `replace(".", "-")` matches real dots; `replace("\\.", "-")` searches for **two characters**, a backslash followed by a dot, which does not appear in `"a.b.c"`, so it returns the same content.
3. `"xyz"` does not appear in `"abc"`, so the result still has the same content as `"abc"`. The example uses `equals()` to check **content**, without relying on whether the two references are identical.
4. `new StringBuilder("av")` and `new StringBuilder("123")` are accepted because they implement `CharSequence`. In `"Java"`, `"av"` is replaced with `"123"`, creating `"J123a"`.

## 2. All *Non-Overlapping* Matches, Evaluated Left to Right

`replace(target, replacement)` replaces all **non-overlapping** occurrences of `target`. If matches overlap, the earlier match is consumed first; positions already used cannot be reused for another match.

Example with `"aaaaa"`, searching for `"aa"`:

```text
String:    a a a a a
Index:     0 1 2 3 4
Match 1:   [0,2)  -> X
Match 2:       [2,4) -> X
Remaining:         a
Result:    XXa
```

In particular, `"aaa".replace("aa", "b")` returns **`"ba"`** because it consumes the `aa` pair at indices 0–1 and leaves the final `a` untouched; there is no second non-overlapping match.

### Edge Cases and Non-Infinite Replacement

Save `ReplaceEdgesDemo.java`:

```java
public class ReplaceEdgesDemo {
    public static void main(String[] args) {
        System.out.println("aaaaa".replace("aa", "X"));
        System.out.println("aaa".replace("aa", "b"));
        System.out.println("banana".replace("ana", "X"));

        System.out.println("aba".replace("a", "aa"));
        System.out.println("aba".replace("", "-"));
        System.out.println("".replace("", "X"));
        System.out.println("abc".replace("b", ""));

        System.out.println(
                "ab".replace("b", "$1\\").equals("a$1\\"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReplaceEdgesDemo.java
java ReplaceEdgesDemo
```

Output:

```text
XXa
ba
bXna
aabaa
-a-b-a-
X
ac
true
```

Key details to understand:

- `"banana".replace("ana", "X")` becomes `"bXna"`: the first `"ana"` from index 1 to before 4 is replaced, and the remaining `"na"` stays intact. The two potential occurrences of `"ana"` overlap, so both are not replaced.
- `"aba".replace("a", "aa")` becomes `"aabaa"`. **It does not continue searching for `"a"` inside the newly inserted `"aa"`**; repeating indefinitely like that would behave completely differently from a single replacement pass.
- `"abc".replace("b", "")` becomes `"ac"`: an empty replacement effectively **deletes** occurrences of `target`.
- `"ab".replace("b", "$1\\")` produces exact `"a$1\\"` as a Java string value. `$` and backslash in `replacement` are **literal characters**; no regex group or escape syntax is interpreted.

### The Empty `target` Case

`""` is an empty sequence and matches at string **boundaries**. In the simple ASCII case:

```java
System.out.println("aba".replace("", "-")); // -a-b-a-
System.out.println("".replace("", "X"));    // X
```

This is often surprising: **an empty target does not mean "replace nothing."** If `target` is user-supplied, you must explicitly decide whether to allow empty strings:

```java
if (target == null || target.isEmpty()) {
    throw new IllegalArgumentException(
            "target must be non-empty");
}
String updated = original.replace(target, replacement);
```

This snippet is **inside a method**, assuming `original` and `replacement` are valid. Especially with Unicode, do not use insertion at every string unit as a substitute for user-perceived character segmentation; an emoji can occupy multiple UTF-16 units.

## 3. Boundary Between Literal Strings and Regex

`replace(CharSequence, CharSequence)` treats **both `target` and `replacement` as literal text**. `replaceFirst(regex, replacement)` and `replaceAll(regex, replacement)` use regular expressions to search; their `replacement` has special syntax for `$1` and backslashes.

~~~java
String source = "a.b.c";
System.out.println(source.replace(".", "-"));       // a-b-c
System.out.println(source.replaceAll(".", "-"));    // -----
System.out.println(source.replaceAll("\\.", "-")); // a-b-c
System.out.println("ab".replace("b", "$1\\"));       // a$1\
~~~

In the literal overload, `"."` matches an exact dot and `"$1\\"` is inserted literally. With regex, you must escape the dot as `"\\."`; if pattern and replacement come from dynamic data, `Pattern.quote(target)` and `Matcher.quoteReplacement(replacement)` ensure those parts are treated literally. The dedicated lesson comparing `replace`, `replaceFirst`, and `replaceAll` in this chapter covers escaping, capture groups, and regex pitfalls in depth. When regex is not needed, choose `replace(target, replacement)` directly.

## 4. `String` Immutability and Using the Return Value

The method searches and produces a **result value**, without modifying the `String` receiving the call:

~~~java
String original = "red red";
String updated = original.replace("red", "blue");
System.out.println(original); // red red
System.out.println(updated);  // blue blue
~~~

If you only write `original.replace("red", "blue");` and discard the return value, `original` still holds `"red red"`. You can reassign a variable when the original is no longer needed; if you need to display or compare against the received content, keep `original` and `updated` separate. With multiple chained replacements, each subsequent call runs on the result of the previous one; rule order can change the result.

## 5. Null Checks and Input Data

There is no object to invoke `replace()` on if the receiver variable is `null`. In addition, for the `replace(CharSequence, CharSequence)` overload, Java requires **both `target` and `replacement` to be non-`null`**.

```java
String text = "hello";

// The following calls will throw NullPointerException:
// text.replace((CharSequence) null, "x");
// text.replace("l", (CharSequence) null);

String missing = null;
// missing.replace("a", "b");
```

If inputs can be absent, choose an explicit policy: reject with an exception, keep unchanged, or return another value according to business requirements. Example utility returning `null` if the source string is `null`, while requiring the two replacement parameters to be valid:

```java
import java.util.Objects;

public class SafeReplaceDemo {
    public static String replaceOrNull(
            String text, String target, String replacement) {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(replacement, "replacement");
        return text == null
                ? null
                : text.replace(target, replacement);
    }

    public static void main(String[] args) {
        System.out.println(
                replaceOrNull("a/b/c", "/", "-"));
        System.out.println(
                replaceOrNull(null, "/", "-") == null);
    }
}
```

Run `javac -encoding UTF-8 SafeReplaceDemo.java` and `java SafeReplaceDemo`, output:

```text
a-b-c
true
```

The example method deliberately chooses a policy of returning `null` when `text` is missing. In another API, throwing `IllegalArgumentException` or `NullPointerException` per contract might be more appropriate. **Do not silently turn `null` into the string `"null"`** when business rules have not specified that behavior.

## 6. Unicode and Case Sensitivity

`String.replace(CharSequence, CharSequence)` matches character sequences **by exact UTF-16 content**, without automatically applying Unicode normalization, removing diacritics, or matching by culture/language.

Two visually identical representations can have different code unit sequences:

- `"\u00E9"` is the precomposed `é` character (U+00E9).
- `"e\u0301"` consists of `e` (U+0065) and combining acute accent U+0301.

Example file `ReplaceUnicodeDemo.java`:

```java
import java.text.Normalizer;

public class ReplaceUnicodeDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        System.out.println(
                composed.replace("e\u0301", "X"));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println(
                normalized.replace("\u00E9", "X"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReplaceUnicodeDemo.java
java ReplaceUnicodeDemo
```

Output:

```text
Café
CafX
```

The first string does not contain the two-code-point sequence `e + combining acute accent`, so its content stays unchanged. After normalizing the decomposed string to `NFC`, the string has the precomposed character and replacing `é` with `X` succeeds.

If Unicode equivalence handling is required, **normalize both source and target** to the same appropriate form before replacing; remember that normalization can change code points and offsets. If case-insensitive search is required, consider `Locale`-aware case conversion or appropriate Unicode case folding algorithms; `replace()` by default **does not ignore** case.

Be careful with emojis, combining marks, and surrogate pairs: the method searches segments by UTF-16 and **does not guarantee** preserving *grapheme cluster* (user-perceived character) boundaries. If the goal is to replace a complete displayed character, you must determine Unicode boundaries according to application rules.

## 7. When Should You Use `replace()`?

Some reasonable scenarios:

- **Changing a fixed delimiter:** `"a/b/c".replace("/", "-")` → `"a-b-c"`.
- **Replacing a recognized text token:** `"Hello, {name}!".replace("{name}", "Lan")` → `"Hello, Lan!"`, where input and replacement order are controlled.
- **Removing a specific segment:** `"a--b".replace("--", "")` → `"ab"`.
- **Normalizing a fixed phrase in internal text:** `"ERROR: ERROR:".replace("ERROR", "WARN")` → `"WARN: WARN:"`.

Note that **literal replacement is not parsing**: replacing `"cat"` in `"catalog"` also replaces part of a larger word. For business tokens, identifiers, placeholders with escaping/nesting, or structured data, use a parser or dedicated templating mechanism to avoid accidental replacements.

With long text, many replacement targets, or repeated `replace()` calls inside a loop, performance depends on the processing strategy and data. Each call returns a `String` per API semantics, though the actual number of allocations is an implementation detail and may be optimized by the JVM. When assembling many parts in a loop, `StringBuilder` is usually suitable; when there are many replacement patterns or you need to prevent replacements from interfering with one another, design a single-pass processor based on the specific replacement rules.

Example showing the difference between **one call** and **two chained calls**:

```java
String text = "ab";
System.out.println(text.replace("a", "b"));   // bb
System.out.println(text.replace("a", "b")
                       .replace("b", "c"));     // cc
```

In two chained calls, the second call matches both the old `"b"` and the `"b"` created by the first call. This **differs** from a single `target` replacement: newly inserted text **is not reprocessed within that same call**.

## 8. Common Mistakes

1. **Using `replaceAll()` when `target` is literal text:** `.`, `*`, `[`, `(`, or `\` can carry regex meaning and lead to wrong results or `PatternSyntaxException`. Use `replace(CharSequence, CharSequence)` for literal text.
2. **Thinking it only replaces the first match:** `replace()` replaces **all** non-overlapping matches; for regex, `replaceFirst()` is the separate API for the first match.
3. **Not storing the return value:** `text.replace(...)` does not mutate the `text` object because `String` is immutable.
4. **Putting `$1` in `replacement` and expecting group substitution:** the `replace(CharSequence, CharSequence)` overload **has no** group capture. `$1` is inserted literally.
5. **Thinking an empty `target` always has no effect:** `"ab".replace("", "-")` can insert characters at boundaries; validate or define an input policy.
6. **Forgetting `null`:** a `null` target or replacement causes `NullPointerException`; a `null` string receiver cannot invoke the method either.
7. **Confusing substring matching with word matching:** `"catalog".replace("cat", "dog")` becomes `"dogalog"` because `replace()` does not understand word boundaries.
8. **Expecting case-insensitivity:** `"Java".replace("java", "X")` remains `"Java"`.
9. **Testing only ASCII:** data with diacritics, Unicode normalization, emojis, and combining marks may require additional handling rules.
10. **Replacing multiple times without considering order:** output from the first replacement can become the target of the second if `replace()` calls are chained.
11. **Relying on `==` to verify results:** use `equals()` to compare content instead of comparing references.

## 9. Self-Check

Given `String s = "aaaa";`:

| Call | Result | Explanation |
| --- | --- | --- |
| `s.replace("a", "X")` | `"XXXX"` | Four literal matches of `a` |
| `s.replace("aa", "b")` | `"bb"` | Two non-overlapping `aa` segments |
| `s.replace("aaa", "Z")` | `"Za"` | One `aaa` segment from left to right |
| `s.replace("a", "")` | `""` | Removes all `a`s |
| `s.replace("A", "X")` | `"aaaa"` | Case-sensitive |
| `s.replace("b", "X")` | `"aaaa"` | Target not present |
| `s.replace("", "-")` | `"-a-a-a-a-"` | Replaces empty target at boundaries |

You can create your own Java file for the examples above and use `System.out.println(...)` to verify. When processing user-supplied data, also test empty strings, `null`, targets longer than the source, special characters like `.`/`$`/`\`, and Vietnamese strings with diacritics.

**Key takeaway:** `replace(CharSequence target, CharSequence replacement)` replaces **all non-overlapping literal occurrences**; **both `target` and `replacement` are interpreted literally**. `replaceAll()` uses **regex** and follows different replacement rules. Always use the returned `String` value, validate `null`/empty inputs as required, and only use `equals()` when comparing string content.
