# `String.contains()` for Checking Substrings in Java

In Java, **`String.contains(CharSequence s)`** returns `true` if the target string **contains a contiguous sequence of characters equal to** the argument `s`, and `false` otherwise. This is a simple tool for checking whether a **substring** occurs without needing to know its starting position.

Example:

```java
String text = "Java Core - String";

System.out.println(text.contains("Core")); // true
System.out.println(text.contains("core")); // false
```

The key terms are **contiguous** and **literal**: `contains()` is case-sensitive, does not ignore whitespace, does not automatically normalize Unicode, does not split words, and **does not use regular expressions (regex)**.

## 1. Syntax, Parameters, and Return Value

Declaration in class `java.lang.String`:

```java
public boolean contains(CharSequence s)
```

- **Target object:** a `String` to search inside, such as `text`.
- **Parameter `s`:** a `CharSequence` serving as the substring to search for. Typically a `String` such as `"Java"` is passed; the argument can also be another `CharSequence` implementation such as `StringBuilder`.
- **Result:** `boolean`, `true` if the contiguous character sequence is found, `false` otherwise.
- **Position:** `contains()` **does not return an index**. If you need the first occurrence index, use `indexOf()`.
- **`null`:** calling the method on `null` or passing a `null` argument causes a `NullPointerException` (details in the null-handling section).

Comparison examples:

| Input | Call | Result | Explanation |
| --- | --- | --- | --- |
| `"Java Core"` | `contains("Java")` | `true` | Found at the beginning |
| `"Java Core"` | `contains("Core")` | `true` | Found at the end |
| `"Java Core"` | `contains("va Co")` | `true` | Contiguous sequence exists across the space |
| `"Java Core"` | `contains("java")` | `false` | `J` and `j` differ |
| `"Java Core"` | `contains("JavaCore")` | `false` | Missing space compared to source data |
| `"Java Core"` | `contains("Python")` | `false` | Does not appear |

**`contains()` does not require a full-string match**. `"Java Core".contains("Java")` is `true` even though the target has `" Core"` after it, whereas `"Java Core".equals("Java")` is `false`.

## 2. Complete Java 17+ Example

Save the code as `ContainsBasics.java`:

```java
public class ContainsBasics {
    public static void main(String[] args) {
        String text = "Java Core - String";

        System.out.println(text.contains("Core"));
        System.out.println(text.contains("core"));
        System.out.println(text.contains("Java Core"));
        System.out.println(text.contains(""));

        System.out.println("".contains(""));
        System.out.println("".contains("Java"));

        System.out.println(
                text.contains(new StringBuilder("String")));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ContainsBasics.java
java ContainsBasics
```

Output:

```text
true
false
true
true
true
false
true
```

Explanation:

1. The string `"Core"` appears contiguously, so it returns `true`.
2. `"core"` differs from `"Core"` due to case sensitivity, so `false`.
3. `"Java Core"` appears at the beginning of the string, matching the space as well.
4. **The empty string `""` is considered a substring of every `String`**, including the empty string itself; therefore both `text.contains("")` and `"".contains("")` return `true`.
5. An empty string does not contain the character sequence `"Java"`, so `"".contains("Java")` returns `false`.
6. `StringBuilder` implements `CharSequence`, so `contains(new StringBuilder("String"))` is valid and finds the character sequence.

Semantically, Java checks for the presence of **an exact substring**. There is no need to call `toString()` before passing a `StringBuilder`, though if the object's content changes while another thread is using it, appropriate synchronization is required; mutable `CharSequence` implementations do not have thread-safety guarantees by default.

## 3. Distinguishing `contains`, `indexOf`, `startsWith`, `endsWith`, `equals`, and `matches`

These APIs all work with strings, but ask different questions:

| API | Purpose | Example |
| --- | --- | --- |
| `text.contains(part)` | Does it contain the literal segment **anywhere**? | `"file.txt".contains("le.")` → `true` |
| `text.indexOf(part)` | Where does the literal segment **first appear**? | `"banana".indexOf("ana")` → `1` |
| `text.lastIndexOf(part)` | Where does the literal segment **last appear**? | `"banana".lastIndexOf("ana")` → `3` |
| `text.startsWith(part)` | Does the string **start** with this segment? | `"file.txt".startsWith("file")` → `true` |
| `text.endsWith(part)` | Does the string **end** with this segment? | `"file.txt".endsWith(".txt")` → `true` |
| `text.equals(other)` | Do both strings have **identical full content**? | `"java".equals("java")` → `true` |
| `text.matches(regex)` | Does the **entire** string match a regular expression? | `"abc123".matches(".*\\d+.*")` → `true` |

In particular, `String.contains()` does not interpret `.`, `*`, `+`, `?`, or `\d` as regex syntax. Searching for a dot with `contains(".")` searches for a **literal period character**; searching with `contains("\\d+")` searches for the **three characters** backslash, `d`, and `+` in the text, rather than meaning "one or more digits".

Standalone runnable example `ContainsCompare.java`:

```java
public class ContainsCompare {
    public static void main(String[] args) {
        String text = "Error: file missing";

        System.out.println(text.contains("Error:"));
        System.out.println(text.startsWith("Error:"));
        System.out.println(text.endsWith("Error:"));
        System.out.println(text.indexOf("file"));

        System.out.println("a.b".contains("."));
        System.out.println("abc123".contains("\\d+"));
        System.out.println("abc123".matches(".*\\d+.*"));
    }
}
```

Command:

```bash
javac -encoding UTF-8 ContainsCompare.java
java ContainsCompare
```

Output:

```text
true
true
false
7
true
false
true
```

Here `"file"` starts at UTF-16 index **7**. When you only need a true/false value, `contains()` expresses intent clearly; when you need to slice a segment or report a position, `indexOf()` provides the index. `indexOf(part) >= 0` generally has the same meaning regarding the presence of a character segment as `contains(part)` when the argument is a non-null `String`.

### `contains()` Does Not Check Word Boundaries

`"supervisor".contains("admin")` is `false` because `"admin"` does not appear; meanwhile `"superadministrator".contains("admin")` and `"superadmin".contains("admin")` are both `true`. The search has no concept of **words**, **permissions**, or **product codes**. If a system needs to check whether a role equals `"admin"`, check the exact tokenized and normalized value according to the contract; do not use `contains("admin")` to make authorization decisions.

## 4. Empty Strings and `null` Values

Two cases need to be distinguished:

- **`""` is a valid empty string.** Every string contains the empty string by API definition.
- **`null` means there is no reference to a `String` object.** You cannot call an instance method on `null`.

```java
String text = "hello";
System.out.println(text.contains("")); // true

String missing = null;
// missing.contains("h"); // NullPointerException
// text.contains(null);   // NullPointerException
```

The snippet above is illustrative code inside a method body (the two lines that would throw an exception are commented out). When receiving potentially absent data, choose an explicit business policy:

```java
public static boolean containsSafely(
        String text, String query) {
    return text != null
            && query != null
            && text.contains(query);
}
```

This is an **illustrative method to place inside a class**. It returns `false` when `text` or `query` is `null`; however, for `query.equals("")`, if `text` is non-null, it still returns `true`. This policy fits when `null` means "cannot be checked"; another application may prefer reporting an input error.

**Easy-to-miss detail:** If a search UI should not let a blank keyword match every record, explicitly check `query.isEmpty()` or `query.isBlank()` before calling `contains()`. These two methods differ: `isBlank()` also accepts strings consisting solely of whitespace according to Java's definition of whitespace, which does not mean all Unicode blank characters are necessarily recognized the same way.

## 5. Case Sensitivity and Case-Insensitive Search

`contains()` is a **case-sensitive** match:

```java
System.out.println("Introduction to Java".contains("java"));
// false
```

If a basic search problem wants to ignore case differences, you can convert **both strings** to lowercase using the same `Locale` before searching:

Save `ContainsIgnoreCaseDemo.java`:

```java
import java.util.Locale;

public class ContainsIgnoreCaseDemo {
    public static void main(String[] args) {
        String text = "INTRO JAVA";
        String query = "java";

        boolean found = text.toLowerCase(Locale.ROOT)
                .contains(query.toLowerCase(Locale.ROOT));

        System.out.println(found);
        System.out.println(text.contains(query));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ContainsIgnoreCaseDemo.java
java ContainsIgnoreCaseDemo
```

Output:

```text
true
false
```

`Locale.ROOT` is a consistent choice for many matching scenarios **independent of the user's language**. However, case conversion follows complex Unicode rules, can change code point counts, and depends on locale; lowercasing and then calling `contains()` **is not fully equivalent to Unicode case folding, collation-based search, word segmentation, or accent-insensitive search**. For multilingual text and language-specific matching requirements, choose an appropriate algorithm/library and test cases like `I/i/İ/ı` in Turkish.

Do not automatically apply the same lowercasing where **exact protocol-level matching** is required, such as case-sensitive identifier keys, digital signatures, or security tokens.

## 6. Unicode: Visually Identical Strings Can Still Fail Substring Matching

`String.contains()` searches for a contiguous matching sequence of **UTF-16 code units**. It does **not** perform Unicode normalization, nor does it consider grapheme clusters or visually equivalent accented characters.

For example, “é” can be represented in two ways:

- `"\u00E9"`: a single precomposed code point U+00E9.
- `"e\u0301"`: the letter `e` (U+0065) followed by combining acute accent U+0301.

The two forms usually look identical, but their UTF-16 sequences differ. To match canonically equivalent forms, you can proactively normalize **both source and query** to the same Unicode normalization form.

Standalone example `ContainsUnicodeDemo.java`:

```java
import java.text.Normalizer;

public class ContainsUnicodeDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        System.out.println(composed.contains(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println(composed.contains(normalized));

        String emojiText = "A\uD83D\uDE00B"; // A😀B
        System.out.println(
                emojiText.contains("\uD83D\uDE00"));
        System.out.println(
                emojiText.contains("\uD83D"));
    }
}
```

Command:

```bash
javac -encoding UTF-8 ContainsUnicodeDemo.java
java ContainsUnicodeDemo
```

Output:

```text
false
true
true
true
```

The last two lines illustrate an important distinction: the string `"A😀B"` contains both code units that form the emoji, yet also **contains the lone high surrogate `\uD83D`** at the code-unit level, so the search returns `true`. That does not mean a high surrogate is a complete Unicode character. If you need to search for "user-perceived characters", combine grapheme cluster handling (for example `\X` in `java.util.regex.Pattern` on Java 9+) with the relevant business rules; `contains()` does not enforce character cluster boundaries.

**Do not confuse normalization with accent stripping:** `Normalizer.Form.NFC`/`NFD` converts representations to a canonical form; it does not turn `"é"` into `"e"`. Accent-insensitive search requires its own separate policy, especially for Vietnamese.

## 7. Practical Use Cases

### 7.1. Filtering a List by a Text Segment

Suppose a list of titles is already in memory and the user enters a keyword. In this example, searching is case-sensitive using `contains()`:

```java
import java.util.List;

public class FilterBySubstringDemo {
    public static void main(String[] args) {
        List<String> titles = List.of(
                "Java String",
                "Java Collection",
                "Spring Boot",
                "Modern Java");

        String query = "Java";

        List<String> selected = titles.stream()
                .filter(title -> title.contains(query))
                .toList();

        System.out.println(selected);
    }
}
```

Run:

```bash
javac -encoding UTF-8 FilterBySubstringDemo.java
java FilterBySubstringDemo
```

Output:

```text
[Java String, Java Collection, Modern Java]
```

`contains()` is reasonable for small in-memory lists when business requirements call for literal matching. For large datasets, full-text search systems, word analysis, result ranking, or database queries, choose an appropriate mechanism (indexes, full-text search, collation…). Avoid repeatedly lowercasing or normalizing the same content thousands of times when it can be precomputed once in a pipeline.

### 7.2. Checking Whether a Message Fragment Appears

```java
String message = "WARN: connection timeout";
boolean hasTimeout = message.contains("timeout"); // true
```

This is convenient for detecting a text fragment in simple situations. If you need to parse logs in a structured format, count frequencies, or verify event codes, parse individual fields or use a structured log format; user messages can contain a similar phrase without corresponding to the same event.

### 7.3. Deciding Which Tool to Use

- Need only **presence/absence** of a literal segment → `contains()`.
- Need the **starting position** of a segment → `indexOf()`, which returns `-1` if not found.
- Need to **extract before/after** a delimiter → `indexOf()` then `substring()`, remembering to check `-1`.
- Need **prefix/suffix matching** → `startsWith()`/`endsWith()`.
- Need **regex rules** → `Pattern`/`Matcher` or `matches()` when full-string matching is required; do not pass regex into `contains()`.
- Need **word matching, accent stripping, locale-insensitive matching, or Unicode segmentation** → clarify the search specification first and pick the right tool; `contains()` does not provide those properties automatically.

## 8. Common Mistakes

1. **Treating `contains()` as "fuzzy search":** it actually performs exact contiguous substring matching and does not tolerate typos, arbitrary whitespace, or edit distance.
2. **Forgetting case sensitivity:** `"Java".contains("java")` is `false`.
3. **Passing regex expecting the pattern to be interpreted:** `contains("\\d+")` searches for the literal string `\d+`, not digits.
4. **Using `contains("")` to check whether data is non-empty:** always `true` for a non-null receiver. To check for an empty string use `isEmpty()`; to check for whitespace you can use `isBlank()`.
5. **Not handling `null`:** both a `null` receiver and a `null` query cause `NullPointerException`.
6. **Using `contains()` instead of token checks:** finding `"admin"` in a string does not verify an `admin` role; searching for `"cat"` in `"catalog"` still yields `true`.
7. **Treating the boolean result as a position:** `contains()` only returns `boolean`; `indexOf()` returns the index.
8. **Not normalizing Unicode when canonical equivalence is required:** two representations of an accented letter may look identical yet return `false`.
9. **Assuming UTF-16 substrings represent complete Unicode characters:** a match can hit half of a surrogate pair; `contains()` ignores code point/grapheme boundaries.
10. **Calling `toLowerCase()` with an uncontrolled default locale:** results can vary across environments; choose locale and matching policy based on business rules.
11. **Overusing free-text checks for business logic:** for status codes, permissions, identifiers, and structured formats, parsing or exact field comparison is usually far more reliable.

## 9. Self-Check Questions

Given `String s = "Java Core"`, predict the results:

| Expression | Result | Why |
| --- | --- | --- |
| `s.contains("Java")` | `true` | A prefix is also a substring |
| `s.contains("a C")` | `true` | Contiguous segment spanning the space |
| `s.contains("Core")` | `true` | A suffix is also a substring |
| `s.contains("core")` | `false` | Case mismatch |
| `s.contains("JavaCore")` | `false` | Missing space |
| `s.contains("")` | `true` | Empty string matches in every string |
| `s.contains("Java Core!")` | `false` | Argument is longer and has different content |
| `s.indexOf("Core")` | `5` | `indexOf` returns position, not boolean |

Ask yourself one more question: if `s` is `null`, what happens with `s.contains("Java")`? The answer is **`NullPointerException`**, because there is no object on which to invoke the method.

**Takeaway:** `contains(CharSequence)` checks **whether an exact contiguous sequence of characters exists** in a `String`. It returns `boolean`, is **case-sensitive**, **does not use regex**, **does not normalize Unicode automatically**, and **`contains("")` is always true for a non-null receiver**. When you need positions, word/locale-aware rules, or approximate matching, use specialized APIs/algorithms.
