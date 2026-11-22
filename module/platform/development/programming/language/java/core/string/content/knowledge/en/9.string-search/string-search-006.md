# The `-1` Value and Bugs from Using Search Results as Indices in Java String

When searching for a character or text segment with `String.indexOf(...)` or `String.lastIndexOf(...)`, the result is the **starting match position as a UTF-16 index**, or **`-1` if not found**. The value `-1` is a *sentinel value*, not a character position in the string.

A common mistake is passing the search result straight into `substring(...)`, `charAt(...)`, or index arithmetic without checking it first. In some cases Java throws a clear exception; in others, arithmetic turns `-1` into `0` and returns **wrong content with no error at all**. To handle this properly, understand the search method's contract first, check the "not found" state, and only then compute extraction boundaries.

## 1. What Do `indexOf` and `lastIndexOf` Return?

Familiar `String` overloads include:

```java
text.indexOf('a');             // search for character/code point
text.indexOf("abc");           // search for substring
text.indexOf("abc", fromIndex); // search from specified position
text.lastIndexOf('a');         // last match position
text.lastIndexOf("abc");       // starting position of last match
```

This is an **illustrative snippet of calls**, assuming `text` is a non-null `String`. `indexOf` searches from left to right; `lastIndexOf` finds the last occurrence (or searches backward toward the start for the `fromIndex` overloads). Both return an **`int`**, with two outcome groups:

- **Found:** returns a **non-negative** UTF-16 offset. `0` is a valid result, meaning a match right at the beginning of the string. When searching for a segment longer than 0, the match position cannot exceed `text.length() - needle.length()`.
- **Not found:** returns **`-1`**, with no corresponding position in the string.

Example with `"bananas"` of length `7`:

| Call | Result | Explanation |
|---|---:|---|
| `"bananas".indexOf('a')` | `1` | First letter `a` is at position 1 |
| `"bananas".lastIndexOf('a')` | `5` | Last letter `a` is at position 5 |
| `"bananas".indexOf("na")` | `2` | First `"na"` match starts at 2 |
| `"bananas".lastIndexOf("na")` | `4` | Last match starts at 4 |
| `"bananas".indexOf("xy")` | `-1` | Does not contain `"xy"` |
| `"bananas".indexOf("ba")` | `0` | Match at start of string; **not** a failure |
| `"bananas".indexOf("")` | `0` | Empty search string matches at start boundary |
| `"bananas".lastIndexOf("")` | `7` | Empty search string matches at end boundary |

**Distinguishing `0` and `-1`:** The condition `if (index > 0)` misses matches at the start; `if (index == 0)` does not mean "not found". To check for a match, use `index >= 0` or `index != -1`; to check for failure, use `index == -1` or `index < 0` when the value comes from these search APIs.

### Runnable Example: Reading Positions and the Sentinel Properly

Save as **`SearchResultDemo.java`**:

```java
public class SearchResultDemo {
    public static void main(String[] args) {
        String text = "bananas";

        System.out.println("first a: " + text.indexOf('a'));
        System.out.println("last a: " + text.lastIndexOf('a'));
        System.out.println("first na: " + text.indexOf("na"));
        System.out.println("last na: " + text.lastIndexOf("na"));
        System.out.println("missing xy: " + text.indexOf("xy"));
        System.out.println("at beginning: " + text.indexOf("ba"));
        System.out.println("empty indexOf: " + text.indexOf(""));
        System.out.println("empty lastIndexOf: " + text.lastIndexOf(""));
    }
}
```

Compile and run with Java 17+:

```bash
javac SearchResultDemo.java
java SearchResultDemo
```

**Stdout:**

```text
first a: 1
last a: 5
first na: 2
last na: 4
missing xy: -1
at beginning: 0
empty indexOf: 0
empty lastIndexOf: 7
```

The empty string is an **important special case**. Searching for `""` does not mean the search fails: `indexOf("")` gives `0`, and `lastIndexOf("")` gives `length()`. Therefore, when designing a "find occurrences of a keyword" feature, decide explicitly whether an empty keyword is accepted or must be rejected upfront.

## 2. Why Is `-1` Dangerous When Used as an Index?

Many string-access APIs only accept non-negative indices:

| API | Valid index domain | If `-1` is passed directly |
|---|---|---|
| `charAt(index)` | `0 <= index < length()` | Throws `IndexOutOfBoundsException` |
| `substring(begin)` | `0 <= begin <= length()` | Throws `IndexOutOfBoundsException` |
| `substring(begin, end)` | `0 <= begin <= end <= length()` | Throws `IndexOutOfBoundsException` if begin/end is `-1` |
| `subSequence(begin, end)` | Same as `substring(begin, end)` | Invalid range; throws exception |
| `codePointAt(index)` | `0 <= index < length()` | Throws `IndexOutOfBoundsException` |
| `substring(position + 1)` | Depends on addition result | **Can be valid yet semantically wrong** if `position == -1` |

The last row is especially easy to miss:

```java
String input = "name=value";
int colon = input.indexOf(':'); // -1

// Wrong: from 0 to -1, throws exception.
String beforeColon = input.substring(0, colon);

// Also semantically wrong: -1 + 1 = 0.
// No exception; the result becomes the entire string "name=value".
String afterColon = input.substring(colon + 1);
```

This is **code illustrating two bugs**, not a program meant to run as-is. One bug manifests immediately as an exception; the other is dangerous because the result looks valid and can easily slip past superficial tests.

**Rule:** check the **raw search result before adding or subtracting**. Do not use `index + 1`, `index - 1`, `substring(index)`, or `charAt(index)` before ensuring `index >= 0` and that any derived boundaries remain valid.

## 3. Contrasting Example: Exception vs. Silent Wrong Output

**`SearchIndexPitfallDemo.java`**

```java
public class SearchIndexPitfallDemo {
    public static void main(String[] args) {
        String input = "name=value";
        int colon = input.indexOf(':');

        System.out.println("colon: " + colon);

        try {
            System.out.println(input.substring(0, colon));
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("substring(0, -1): invalid");
        }

        try {
            System.out.println(input.charAt(colon));
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("charAt(-1): invalid");
        }

        String misleading = input.substring(colon + 1);
        System.out.println("substring(-1 + 1): " + misleading);
    }
}
```

```bash
javac SearchIndexPitfallDemo.java
java SearchIndexPitfallDemo
```

**Stdout:**

```text
colon: -1
substring(0, -1): invalid
charAt(-1): invalid
substring(-1 + 1): name=value
```

The example intentionally catches exceptions to demonstrate the failure modes. In production code, do not use exception catching as routine validation for cases where a delimiter may be absent: `indexOf()` already returns `-1` to signal that clearly.

A related trap: if you write `text.substring(found, found + keyword.length())` when `found == -1`, the expression can throw; if `keyword.length() == 1`, then `found + keyword.length() == 0`, which is still wrong because the start boundary is `-1`. No arithmetic turns `found == -1` into proof of a match.

## 4. Standard Workflow: Check First, Compute Indices Afterward

To extract before/after a delimiter, separate into three steps:

1. **Search** for the delimiter with `indexOf()` or `lastIndexOf()`.
2. **Check** whether the result is `-1`.
3. **Only when found**, use the position to call `substring()`.

Example parsing `key=value` strings:

**`SafeDelimiterDemo.java`**

```java
public class SafeDelimiterDemo {
    private static void parse(String line) {
        int separator = line.indexOf('=');

        if (separator < 0) {
            System.out.println("Missing separator: " + line);
            return;
        }

        String key = line.substring(0, separator);
        String value = line.substring(separator + 1);

        System.out.println("key=<" + key + ">, value=<" + value + ">");
    }

    public static void main(String[] args) {
        parse("name=Java");
        parse("=value");
        parse("key=");
        parse("missing");
        parse("a=b=c");
    }
}
```

```bash
javac SafeDelimiterDemo.java
java SafeDelimiterDemo
```

**Stdout:**

```text
key=<name>, value=<Java>
key=<>, value=<value>
key=<key>, value=<>
Missing separator: missing
key=<a>, value=<b=c>
```

Boundary cases to understand:

- A delimiter at the **start** has `separator == 0`. This counts as **found**, so the substring before it is `""`.
- A delimiter at the **end** has `separator == length() - 1`, so `substring(separator + 1)` equals `substring(length())`, which is a **valid** extraction returning `""`.
- Without a delimiter, `separator == -1`. The example handles it with a separate message and stops computing boundaries.
- If multiple `=` signs exist, `indexOf('=')` picks the **first** one, so the right-hand part may still contain `=`. If you want the last one, switch to `lastIndexOf('=')` while keeping the `-1` check.
- Your problem might require a **non-empty key**, a **non-empty value**, or allow only a single `=`. Those are **additional business validations**; the presence of the delimiter alone does not guarantee them.

### The Not-Found Case Needs a Clear Contract

Instead of always printing a message, a library method might:

- Return `Optional<String>` or a result type explicitly stating "present/absent".
- Throw `IllegalArgumentException` if the delimiter is mandatory and missing it indicates bad input.
- Return `null` if the API specifies so, provided callers know and check for `null`.

Do not unconditionally return `""` to represent "delimiter missing": a delimiter at the end of the string also produces a **valid empty value**. If the two states have different meanings, represent them differently.

## 5. From Match Position to Substring Range

For a **non-empty** keyword `needle` and `position = text.indexOf(needle)`:

```text
If position == -1:
    No matching region; do not fabricate sub-indices.

If position >= 0:
    begin = position
    end   = position + needle.length()
    [begin, end) lies within text.
```

`indexOf(String)` returns the starting position of the entire matched substring, so when found, Java guarantees enough code units exist for `needle`. Here the length is `needle.length()` in UTF-16, the same unit as the index returned by `indexOf`.

Example:

**`MatchRangeDemo.java`**

```java
public class MatchRangeDemo {
    private static void showMatch(String text, String needle) {
        if (needle.isEmpty()) {
            System.out.println("Empty keyword is not supported");
            return;
        }

        int position = text.indexOf(needle);
        if (position < 0) {
            System.out.println("Not found: " + needle);
            return;
        }

        int end = position + needle.length();
        String found = text.substring(position, end);
        System.out.println("match [" + position + "," + end + "): " + found);
    }

    public static void main(String[] args) {
        showMatch("Java String", "String");
        showMatch("Java String", "Java");
        showMatch("Java String", "Kotlin");
        showMatch("Java String", "");
    }
}
```

```bash
javac MatchRangeDemo.java
java MatchRangeDemo
```

**Stdout:**

```text
match [5,11): String
match [0,4): Java
Not found: Kotlin
Empty keyword is not supported
```

The `needle.isEmpty()` case is **intentionally rejected by the example's contract**, since the goal is matching a non-empty keyword. This is not a limitation of `indexOf("")`; Java allows searching for an empty string.

Once `position` is checked, extracting the entire matched range is useful for highlighting, controlled replacement, logging offsets, or parsing. If you only need to check presence, `text.contains(needle)` or `text.indexOf(needle) >= 0` may suffice without `substring`.

## 6. Extracting a File Extension with `lastIndexOf`

An application often looks for the last dot and takes what follows:

```java
int dot = filename.lastIndexOf('.');
String extension = filename.substring(dot + 1);
```

If there is no dot, `dot == -1`, making `dot + 1 == 0`, so `extension` receives the **entire file name** instead of an extension. No exception is thrown, yet the data semantics are wrong.

Even when a dot is present, distinguish:

- `"report.txt"`: dot in the middle, extension `"txt"`.
- `"report"`: no dot, no extension.
- `".env"`: dot at the start; many systems treat this as a hidden file **with no extension**.
- `"report."`: dot at the end; the trailing part is empty, and application policy may treat it as having no extension.
- `"archive.tar.gz"`: uses the last dot so the extension is `"gz"`, not `"tar.gz"`.

The example below specifies **returning an extension only if the dot lies strictly inside the file name**.

**`FileExtensionDemo.java`**

```java
import java.util.Optional;

public class FileExtensionDemo {
    private static Optional<String> extensionOf(String name) {
        int dot = name.lastIndexOf('.');
        if (dot <= 0 || dot == name.length() - 1) {
            return Optional.empty();
        }
        return Optional.of(name.substring(dot + 1));
    }

    private static void show(String name) {
        System.out.println(name + " -> "
                + extensionOf(name).orElse("(none)"));
    }

    public static void main(String[] args) {
        show("report.txt");
        show("report");
        show(".env");
        show("report.");
        show("archive.tar.gz");
    }
}
```

```bash
javac FileExtensionDemo.java
java FileExtensionDemo
```

**Stdout:**

```text
report.txt -> txt
report -> (none)
.env -> (none)
report. -> (none)
archive.tar.gz -> gz
```

This is only a **simple file-name string** parsing rule, not a full path parser or a universal convention across all operating systems. For paths with directories, dots in directory names, or special file types, extract the file name separately and standardize the application policy.

## 7. Traps with `fromIndex`, Initial Positions, and Empty Keywords

The `fromIndex` overloads control where searching starts, but they do not turn `-1` into a valid index for slicing a string.

Examples on `"bananas"`:

| Expression | Result | Meaning |
|---|---:|---|
| `indexOf("na", 0)` | `2` | First match from position 0 |
| `indexOf("na", 3)` | `4` | Skips match starting at 2 |
| `indexOf("na", 5)` | `-1` | No match starting at or after 5 |
| `indexOf("na", -10)` | `2` | For `indexOf`, negative `fromIndex` is treated as 0 |
| `indexOf("na", 99)` | `-1` | Search starting position is past all matches |
| `lastIndexOf("na", 3)` | `2` | Last match whose start position does not exceed 3 |
| `lastIndexOf("na", -1)` | `-1` | No non-negative start position <= -1 |
| `lastIndexOf("na", 99)` | `4` | Still finds the last existing match |

**Note the difference:** `indexOf(..., -10)` can find a match because of how it handles negative starting offsets, whereas `lastIndexOf(..., -1)` returns `-1`. That is a **search method** contract, not a license to pass negative indices into `substring()` or `charAt()`.

In addition:

- `text.indexOf("")` equals `0` and `text.lastIndexOf("")` equals `text.length()` for the forms **without `fromIndex`**.
- For `indexOf("", fromIndex)`, Java clamps the result boundary to `[0, length()]`; searching for an empty string still succeeds even when the starting offset is outside the length.
- For `lastIndexOf("", fromIndex)`, boundaries greater than `length()` are clamped to `length()`; if `fromIndex < 0`, `-1` is returned.
- If an iterative algorithm searches for all matches, an empty `needle` needs special handling. Otherwise, advancing an index past `length()` while keeping calling `indexOf("", fromIndex)` can cause an **infinite loop** as the result keeps returning `length()`.

If the caller only needs **to know whether it is present or not**, `text.contains(needle)` is a direct, clear choice, though remember `contains("")` is `true`. When you need offsets for extraction, `indexOf`/`lastIndexOf` remain necessary.

## 8. Finding All Positions: Checking `-1` and Advancing Indices Properly

To find multiple occurrences, you typically use a loop calling `indexOf(needle, fromIndex)` repeatedly. Always:

1. Require a non-empty keyword or provide a separate branch for empty strings.
2. Check `position < 0` **before** using or adding to the match position.
3. Advance the next search position so the algorithm makes progress.
4. Decide whether **overlapping** matches are allowed.

For example, with `"aaaa"` and `"aa"`: overlapping match positions are `0, 1, 2`. If `fromIndex` advances by `needle.length() == 2` after each match, the algorithm only collects `0, 2` (non-overlapping).

**`FindAllMatchesDemo.java`**

```java
public class FindAllMatchesDemo {
    private static void findAllOverlapping(String text, String needle) {
        if (needle.isEmpty()) {
            throw new IllegalArgumentException("needle must not be empty");
        }

        int from = 0;
        while (true) {
            int index = text.indexOf(needle, from);
            if (index == -1) {
                return;
            }

            System.out.println("match at: " + index);
            from = index + 1;
        }
    }

    public static void main(String[] args) {
        findAllOverlapping("aaaa", "aa");
    }
}
```

```bash
javac FindAllMatchesDemo.java
java FindAllMatchesDemo
```

**Stdout:**

```text
match at: 0
match at: 1
match at: 2
```

Here we advance `from = index + 1` to allow overlaps. Because `needle` is non-empty, each match position precedes the end of the string; `from` increases and the loop terminates when no matches remain. If the application requires non-overlapping matches, set `from = index + needle.length()` after each result while keeping the `-1` check.

## 9. Search Indices Are UTF-16 Offsets, Not "Visible Character" Counts

`String` search overloads return **UTF-16 offsets**, consistent with `substring`. This matters for emojis, non-BMP characters, combining marks, and certain character sequences.

For example, `"A😊B😊"` has `length() == 6`: `A` takes one code unit, each 😊 emoji takes two code units, and `B` takes one. The two emojis start at offsets `1` and `4`, even though a reader perceives them at the second and fourth character positions when counting by display elements.

**`UnicodeSearchIndexDemo.java`**

```java
public class UnicodeSearchIndexDemo {
    public static void main(String[] args) {
        String smile = "\uD83D\uDE0A";
        String text = "A" + smile + "B" + smile;

        int first = text.indexOf(smile);
        int last = text.lastIndexOf(smile);
        int missing = text.indexOf("X");

        System.out.println("units: " + text.length());
        System.out.println("points: "
                + text.codePointCount(0, text.length()));
        System.out.println("first smile: " + first);
        System.out.println("last smile: " + last);
        System.out.println("missing X: " + missing);
        System.out.println("complete smile: "
                + text.substring(first, first + smile.length()).equals(smile));

        String broken = text.substring(first, first + 1);
        System.out.println("broken high surrogate: "
                + Character.isHighSurrogate(broken.charAt(0)));
    }
}
```

```bash
javac UnicodeSearchIndexDemo.java
java UnicodeSearchIndexDemo
```

**Stdout:**

```text
units: 6
points: 4
first smile: 1
last smile: 4
missing X: -1
complete smile: true
broken high surrogate: true
```

**Explanation:** `indexOf(smile)` returns the starting offset of the entire surrogate pair; `smile.length() == 2` so the range `[first, first + 2)` captures the full emoji. If you only slice `[first, first + 1)`, the result is a lone high surrogate even though the bounds are arithmetically valid.

If indices are used to mark UI positions or count code points, convert units explicitly. Even when extracting whole code points, a base letter plus accent or a composite emoji can span multiple code points; when you need to preserve "user-perceived characters", segment by grapheme clusters.

## 10. Distinguishing Search Results, Invalid Indices, and `null` Inputs

These three situations require different handling:

- **Not found:** `indexOf`/`lastIndexOf` returns `-1`. This is a **normal outcome** of a search, not an exception.
- **Using an invalid index to access/extract:** `charAt(-1)`, `substring(0, -1)`, or `substring(length() + 1)` throws an `IndexOutOfBoundsException`.
- **No `String` object on which to invoke the method:** if `text == null` and you call `text.indexOf("a")`, the program throws `NullPointerException`. `null` cannot be treated as "not found" unless an outer wrapper API is explicitly designed to do so.

If you only need to check whether a string contains a text segment, `contains()` is an expressive choice:

```java
String text = "Java String";
boolean found = text.contains("String"); // true
boolean absent = text.contains("Kotlin"); // false
```

This is an illustrative snippet, not a standalone class. `contains()` returns a `boolean` and has no `-1` sentinel; however, it also gives no position for slicing. If `text` is `null`, `text.contains(...)` still throws `NullPointerException`.

Also, **never check the result with `if (index)`** as in some other languages: Java does not implicitly convert `int` to `boolean`, so that statement will not compile. Write `if (index >= 0)` or `if (index == -1)` explicitly.

## 11. Typical Mistakes and How to Prevent Them

| Mistake | Consequence | Fix |
|---|---|---|
| `substring(0, text.indexOf(':'))` | If `:` is absent, `end == -1` and throws an exception | Store result in a variable and check `>= 0` first |
| `substring(text.indexOf(':') + 1)` | If `:` is missing, returns whole string from offset 0 | Check the sentinel **before adding 1** |
| `if (index > 0)` to test for found | Misses matches at position `0` | Use `index >= 0` |
| `charAt(indexOf(...))` | May receive index `-1` and throw an exception | Access only after confirming a match |
| Getting extension via `substring(lastIndexOf('.') + 1)` | Without a dot, returns the whole file name | Check `dot` and enforce valid position constraints |
| Looping `indexOf("", fromIndex)` without a special branch | Can fail to advance and loop forever at the end | Handle empty keywords explicitly |
| Treating `indexOf(...) == 0` as failure | Ignores keywords at the beginning | `0` is a valid position |
| Thinking every `-1` result is an exception | Confuses search contract with extraction contract | Search returns a sentinel; misusing the index causes errors |
| Using search index as code point ordinal | Wrong position when strings contain non-BMP characters | Specify UTF-16 offset and convert when needed |
| Treating an empty string after a delimiter as "not found" | Conflates two distinct business states | Distinguish sentinel `-1` from `substring(length()) == ""` |

## 12. Self-Check

Given `text = "a:b:c"`, predict the output of the following:

```java
String text = "a:b:c";

int first = text.indexOf(':');
int last = text.lastIndexOf(':');
int absent = text.indexOf('/');

System.out.println(first);
System.out.println(last);
System.out.println(absent);
System.out.println(text.substring(first + 1));
System.out.println(text.substring(last + 1));
System.out.println(text.substring(absent + 1));
```

**Stdout:**

```text
1
3
-1
b:c
c
a:b:c
```

The last three lines highlight a crucial point: both `first + 1` and `last + 1` are valid **because `:` exists**, whereas `absent + 1 == 0` produces the entire string without throwing an exception. If a search may fail to match, never write the last line in that pattern in real code.

**Short practice exercise:** write a method that extracts the part before `@` from an input address. Test `"a@b"`, `"@b"`, `"a@"`, `"abc"`, and `""`. Define separately the missing-sign case, the empty-prefix case, and the empty-suffix case; do not let addition or `substring` silently decide your business policy.

**Rule to remember:** whenever an API returns a search position, read `-1` as **"no position"**, `0` as **"matched at the start"**, and any valid positive value as the **UTF-16 offset of the match**. Check the sentinel **first**, and only then compute `begin`, `end`, or call `substring`. Doing so prevents both obvious exceptions and silent bugs where `-1 + 1` becomes `0`.
