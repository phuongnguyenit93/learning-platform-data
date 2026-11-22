# Pattern and Matcher for Repeated Processing in Java

In Java, the **java.util.regex.Pattern** class represents a compiled regular expression; the **java.util.regex.Matcher** class uses that Pattern to validate, search, extract, or replace content on an input string. When you need to process multiple strings or find multiple matches within a single string, **compile the Pattern once and create an appropriate Matcher for each processing pass**. This is the natural usage, makes state easy to control, and avoids unnecessarily recompiling the same regex.

This lesson focuses on repeated processing: one regex used with multiple inputs, one input containing multiple matches, reusing a Matcher sequentially, controlling state, and common pitfalls.

## 1. Distinguishing the Roles of Pattern and Matcher

| Component | Function | State and Shareability |
| --- | --- | --- |
| Pattern | Stores a compiled regex and flags. Creates a Matcher via matcher(input). | Immutable, safe for multiple threads to use concurrently. |
| Matcher | Executes the regex on a CharSequence; holds the input, search region, last match position, capturing groups, and position for the next search. | Has mutable state, **not safe to share concurrently across threads**. |
| PatternSyntaxException | Reports an invalid regex at compile time. | Must be handled when regexes are dynamically entered or configured. |

Example illustrating the idea (code snippet, not a standalone runnable program):

~~~java
Pattern pattern = Pattern.compile("\\d+");   // Compile once
Matcher first = pattern.matcher("Code 17");  // Matcher for the first input
Matcher second = pattern.matcher("Code 42"); // Another Matcher for the second input

System.out.println(first.find());            // true
System.out.println(second.find());           // true
~~~

Two independent Matchers can advance through their own inputs without altering each other's state. If the same regex is used frequently, the Pattern can be stored as a static final constant, in a service, or in a reused object.

### Why Not Compile Inside Every Loop Iteration?

The following approach recompiles the regex on every element iteration:

~~~java
for (String line : lines) {
    Matcher matcher = Pattern.compile("\\bID-\\d{3}\\b").matcher(line);
    // ...
}
~~~

You should move the compilation outside:

~~~java
Pattern idPattern = Pattern.compile("\\bID-\\d{3}\\b");
for (String line : lines) {
    Matcher matcher = idPattern.matcher(line);
    // ...
}
~~~

Similarly, String.matches(regex) and Pattern.matches(regex, input) are suitable for quick one-off checks, but they compile the regex on every call. In repeated processing with the same regex, a precompiled Pattern with matcher(input).matches() avoids that overhead. The practical benefit depends on regex complexity and call frequency; the most important optimization is still the correctness of the regex.

## 2. One Pattern Processing Multiple Lines, Each with Multiple Matches

Requirement: find all codes matching the format ID- followed by **exactly three digits**, and output the code, the numeric part, and the position. The word boundary \b prevents matching codes attached to adjacent word characters; the syntax (?<number>...) names the digit-capturing group.

File **RegexReuseDemo.java** (Java 17+):

~~~java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexReuseDemo {
    private static final Pattern ID_PATTERN =
            Pattern.compile("\\bID-(?<number>\\d{3})\\b");

    public static void main(String[] args) {
        List<String> lines = List.of(
                "Row ID-123, ID-045; invalid ID-7.",
                "ID-999 ends; xid-111 does not match."
        );

        for (String line : lines) {
            Matcher matcher = ID_PATTERN.matcher(line);
            while (matcher.find()) {
                System.out.printf(
                        "%s | code=%s | pos=[%d,%d)%n",
                        matcher.group(),
                        matcher.group("number"),
                        matcher.start(),
                        matcher.end()
                );
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RegexReuseDemo.java
java RegexReuseDemo
~~~

Output:

~~~text
ID-123 | code=123 | pos=[4,10)
ID-045 | code=045 | pos=[12,18)
ID-999 | code=999 | pos=[0,6)
~~~

Explanation:

1. **ID_PATTERN** is compiled only once when the class is initialized. Each line receives a new Matcher via matcher(line).
2. **find()** finds the next match. Calling it repeatedly in a while loop iterates over non-overlapping matches from left to right; when no matches remain, find() returns false.
3. **group()** (or group(0)) is the entire matched substring; **group("number")** is the content of the named group.
4. **start()** is the starting index, and **end()** is the index *immediately after* the last character. Thus the index range is [start, end). Indices are counted in Java char/UTF-16 units, which do not necessarily equal the number of visible characters if supplementary Unicode characters are present.
5. ID-7 does not have three digits. xid-111 does not match because ID is uppercase in the regex and it is not at an appropriate word boundary.

The braces \d{3} specify the count, while \b defines the word boundary; if business rules require a code to stand alone in a different way (such as underscores, Unicode characters, or custom code rules), you must design boundaries that match the requirement. The regex above illustrates a specific format, not a validator for every kind of identifier.

## 3. Reusing the Same Matcher Object with reset()

In a sequential processing flow, when you want to reduce the number of Matcher objects created, you can keep one Matcher and call **reset(newInput)** before each input. The Matcher discards its previous search results and starts over on the new string.

File **MatcherResetDemo.java**:

~~~java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatcherResetDemo {
    public static void main(String[] args) {
        Pattern numberPattern = Pattern.compile("\\b\\d+\\b");
        Matcher matcher = numberPattern.matcher("");

        for (String line : List.of("A: 17, B: 22", "C: 8")) {
            matcher.reset(line);
            while (matcher.find()) {
                System.out.printf("%s -> %s%n", line, matcher.group());
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MatcherResetDemo.java
java MatcherResetDemo
~~~

Output:

~~~text
A: 17, B: 22 -> 17
A: 17, B: 22 -> 22
C: 8 -> 8
~~~

There are two common reset forms:

- **reset()**: reuses the current input and restarts searching from the beginning.
- **reset(CharSequence input)**: switches to a new input, resetting the search state and the default search region to the entire new input.

After a reset, previous capturing groups and match positions are no longer valid. Only call group(), start(), and end() after matches(), lookingAt(), or find() has returned true. If there is no valid match result, these methods throw IllegalStateException.

**Default choice:** use a shared Pattern + a new Matcher per input because the code is clearer and less prone to state bugs. Reuse the same Matcher only when processing sequentially, controlling its lifecycle, and having a measurable reason to do so. Do not share a reused Matcher across parallel tasks.

## 4. Choosing a Method When Reusing a Pattern

A compiled `Pattern` can be used for all three matching modes; **the method called on the Matcher** determines what question each pass asks:

| Method | With regex `\d+` and input `"123abc456"` | Use when |
| --- | --- | --- |
| `matches()` | `false`: `abc456` remains outside the pattern | Validating the entire data region |
| `lookingAt()` | `true`: prefix `"123"` matches | Recognizing a token at the start of the region |
| `find()` | `true`: finds `"123"`, next call finds `"456"` | Iterating through consecutive matching substrings |

When testing **independent** modes, call `digits.matcher(input)` to create a separate Matcher for each test. When collecting all matches with `find()`, keep **one Matcher across the loop** so the search position advances properly; only call `reset()` if you intentionally want to start over. Distinguishing the scope of the three methods is foundational, while the focus of this lesson is managing `Pattern` lifecycle and `Matcher` state during repeated processing.

## 5. Working with Groups and Positions in a find() Loop

- group(0) or group(): the entire matched substring.
- group(1), group(2), ...: capturing groups numbered by the order of opening parentheses. group("name") accesses a named group.
- start(), end() are the positions of the entire match; start(1), end(1) are the positions of group 1; analogous overloads accept a group name.
- An optional capturing group might not participate in a match: the corresponding group returns null, while start/end for that group return -1. This differs from a group that participates and matches an empty string.
- Use (?:...) when you only need to group an expression **without creating a capturing group**; this keeps group indices stable and easier to read.

Conceptual example: the regex (ID)-(\\d{3}) has group(1) as "ID" and group(2) as the three digits; the regex (?:ID)-(\\d{3}) has only one digit-capturing group. When extracting data across multiple groups, check for the presence of optional groups before converting types or performing string operations.

Be careful with expressions that can match an **empty string** (such as .* or optional quantifiers). find() handles advancing to the next position for zero-length matches, but code that manually updates a scan index using end() can enter an infinite loop if it does not handle the start() == end() case. Do not assume every find() match consumes at least one character.

## 6. Compilation Flags and Escaping Characters

Flags can be specified at compile time:

~~~java
Pattern keyword = Pattern.compile(
        "\\bjava\\b",
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
~~~

- **CASE_INSENSITIVE**: case-insensitive matching; combine with UNICODE_CASE when matching Unicode letters according to Java's case-insensitive rules.
- **MULTILINE**: changes how ^ and $ recognize the start/end of lines in a multiline string; does not turn matches() into a line-by-line search.
- **DOTALL**: allows the dot . to match newline characters as well. Not directly related to Matcher reuse.

In a **Java string**, a backslash in regex syntax usually must be written as two backslashes: the regex \d is passed to Pattern from the Java string "\\d"; the regex \b from "\\b". If you write a single "\b" inside a Java string, that is a Java backspace character, not a regex word boundary expression.

If user input must be searched **literally**, use Pattern.quote(text) instead of concatenating it directly into the regex; if the replacement content contains $ or \, use Matcher.quoteReplacement(replacement) to preserve its literal meaning. The following illustrative snippet assumes three String variables already exist:

~~~java
Pattern literal = Pattern.compile(Pattern.quote(searchText));
Matcher matcher = literal.matcher(sourceText);
String result = matcher.replaceAll(Matcher.quoteReplacement(replacementText));
~~~

Without quoting, special characters in searchText can become regex operators; $ or \ in replacementText can be interpreted as group references or escape syntax. When you intentionally need group-based replacement, use Matcher's group reference syntax instead of quoteReplacement.

## 7. Repeated Processing in Programs and Multithreaded Applications

For an API/service handling many requests or workers running in parallel, a Pattern can be shared safely:

~~~java
private static final Pattern TOKEN = Pattern.compile("[A-Za-z0-9]+");

static boolean containsToken(String input) {
    return TOKEN.matcher(input).find();
}
~~~

Each call to containsToken creates a local Matcher. Because a Matcher holds the traversal position and a reference to the string being processed, do not store a single Matcher in a static field or share it across requests. Synchronization can prevent concurrent access but usually produces a confusing and unnecessary design; an immutable Pattern + a local Matcher is sufficient for most cases.

When regexes are supplied by users, validate and control the configuration: Pattern.compile can throw PatternSyntaxException; some expressions with heavy backtracking can consume significant CPU on long or adversarial data. **Caching a Pattern** only avoids repeated compilation; it **does not eliminate** the risk of slow regex processing. For dynamic regexes, consider the number of cached patterns, input size limits, worst-case testing, and designing expressions that avoid ambiguous repetitive branches.

## 8. Common Mistakes and Fixes

| Situation | Cause | Appropriate Practice |
| --- | --- | --- |
| Only the first match is collected | Using if (matcher.find()) once and stopping. | Use while (matcher.find()) when all matches are needed. |
| Cannot search again from the beginning | The Matcher has already reached the end after several find() calls. | Call reset() before a new scan or create another matcher(input). |
| Wrong / missing results on the next line | Reusing a Matcher while forgetting reset(newInput). | Reset with the proper input before each pass. |
| group()/start()/end() throws IllegalStateException | No valid successful match yet, or already reset. | Only access after a true result and before invalidating that state. |
| Validating the full string still accepts substrings | Using find() instead of matches(). | Use matches() for the entire input. |
| Slow when looping over thousands of lines | Repeatedly calling Pattern.compile or String.matches with the same regex; or a regex causing heavy backtracking. | Compile Pattern once, measure performance, and adjust the expression if needed. |
| Errors when running concurrently | Multiple threads sharing one mutable Matcher. | Share Pattern, create a separate Matcher per task. |
| Literal string search behaves unexpectedly | Input contains ., +, [, (, ... and is parsed as regex. | Use Pattern.quote() for literal patterns. |
| Replacement containing $ or \ fails | The replacement string is parsed as group/escape syntax. | Use Matcher.quoteReplacement() for literal replacements. |

## 9. Choosing a Design for Each Need

- **Same regex, many strings:** compile Pattern once; for each string, call pattern.matcher(input).
- **One string, many matches:** one Matcher with while (matcher.find()); read group/start/end immediately in each iteration.
- **One Matcher rescanning or switching inputs sequentially:** call reset() or reset(newInput) before the next scan.
- **Validating a single string:** call matcher(input).matches(); do not confuse with find().
- **Same Pattern across multiple threads:** share Pattern; each thread/task owns its Matcher.
- **External regex or replacement content:** check syntax errors, quote literal content properly, and assess performance risks.

The key takeaway is that **Pattern holds the rule; Matcher holds the state of one processing pass**. Managing these two lifecycles properly keeps regex code both clear and reliable when processing multiple strings and multiple matches.