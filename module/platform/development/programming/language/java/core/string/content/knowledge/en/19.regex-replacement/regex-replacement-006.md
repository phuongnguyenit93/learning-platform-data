# Matcher.replaceAll with a Function Computing the Replacement String in Java

When using regex, in many cases we want each matched segment to receive **a different replacement string**, computed based on that segment itself. For example: doubling every number in a sentence, normalizing each identifier, masking data according to length, or looking up values to fill placeholders. Since **Java 9**, the **java.util.regex.Matcher** class has provided **replaceAll(Function<MatchResult, String>)** to solve these problems.

The core idea: for **each matched segment**, Matcher calls the function we supply, passes in the current match information, and takes **the replacement string returned by the function**. Unmatched segments are kept unchanged. This lesson covers the API, mechanism, standalone runnable Java 17 examples, and mistakes to avoid.

## 1. Difference Between Fixed Replacement and Function-Based Replacement

| Usage | Meaning | When suitable |
| --- | --- | --- |
| matcher.replaceAll(String replacement) | Applies one replacement template to all matches; can reference capturing groups. | All matches use the same template, e.g., placing group 2 before group 1. |
| matcher.replaceAll(Function<MatchResult, String> replacer) | Computes a separate replacement string for each match via a function/lambda. | Numeric conversions, lookups, conditions, or complex string transformations. |
| input.replaceAll(regex, replacement) | String method taking a regex and a **replacement string**. | Quick syntax when a lambda is not needed. |

API signature, written concisely:

~~~java
String replaceAll(Function<MatchResult, String> replacer)
~~~

Function is a functional interface in java.util.function; MatchResult belongs to java.util.regex. The lambda typically takes one parameter such as match and returns a String. **String.replaceAll does not have an overload taking a lambda**: if you want a callback, you must create a Pattern/Matcher and call Matcher's overload.

When the same expression is used multiple times, you should compile the Pattern once and then create a Matcher for the input being processed. Pattern is immutable and safe to share; Matcher holds mutable state and should not be shared across threads.

## 2. Complete Example: Doubling Matched Numbers

Create the file **NumberReplacementDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class NumberReplacementDemo {
    private static final Pattern NUMBER = Pattern.compile("\\d+");

    public static void main(String[] args) {
        String input = "Score A=7, B=12, C=3.";
        Matcher matcher = NUMBER.matcher(input);

        String output = matcher.replaceAll(match -> {
            int number = Integer.parseInt(match.group());
            return Integer.toString(number * 2);
        });

        System.out.println(input);
        System.out.println(output);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 NumberReplacementDemo.java
java NumberReplacementDemo
~~~

Expected output:

~~~text
Score A=7, B=12, C=3.
Score A=14, B=24, C=6.
~~~

**Step-by-step explanation:** the expression \d+ finds three segments: 7, 12, and 3. Matcher invokes the lambda three times; each time match.group() is the digit sequence currently being processed. The lambda parses the string to an integer, doubles it, and returns a new string. Java inserts those replacement strings at their corresponding positions, keeping all spaces, letters, and punctuation outside the matches intact. The input variable does not change because String in Java is immutable.

In the example, Integer.parseInt is appropriate because the input is small and controlled. With arbitrary data, overly large numbers can cause NumberFormatException, and int multiplication can overflow; you should choose BigInteger/long or apply business limits. Nor does the pattern \d+ represent a full parser for negative numbers, decimals, and Unicode digits across all locale conventions.

## 3. Reading Groups to Compute Structured Replacements

A regex can split a match into multiple **capturing groups**. The MatchResult object provides:

- group() or group(0): the entire matched segment.
- group(1), group(2), ...: content of capturing groups by index.
- start() and end(): bounds of the entire match; end() is the position right after the last character.
- start(n), end(n): bounds of capturing group n. An optional group that did not participate may have group(n) equal to null and start/end equal to -1.

Example: normalize codes consisting of two letters, a hyphen, and one to three digits. Letters are converted to uppercase; numbers are left-padded with zeros to three digits.

Create the file **CodeNormalizeDemo.java**:

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public class CodeNormalizeDemo {
    public static void main(String[] args) {
        Pattern code = Pattern.compile("(?i)\\b([a-z]{2})-(\\d{1,3})\\b");
        String input = "Order ab-7 and Cd-42; notes unchanged.";

        String output = code.matcher(input).replaceAll(match -> {
            String prefix = match.group(1).toUpperCase(Locale.ROOT);
            int number = Integer.parseInt(match.group(2));
            return String.format(Locale.ROOT, "%s-%03d", prefix, number);
        });

        System.out.println(output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CodeNormalizeDemo.java
java CodeNormalizeDemo
~~~

~~~text
Order AB-007 and CD-042; notes unchanged.
~~~

Here (?i) enables case-insensitive matching for the ASCII letters in the pattern; group(1) is the prefix, group(2) is the digits. The regex accepts only segments matching the structure so the lambda can transform the two parts separately.

**Important note for Java 17:** the lambda parameter is inferred as the **MatchResult** interface, not Matcher. In Java 17, you should access groups by **index** using group(1), group(2); calling group("groupName") does not exist on the MatchResult interface in Java 17. Do not cast this parameter to Matcher to mutate state.

## 4. The Replacement Returned by the Lambda Still Has Special Syntax

This is the most common source of bugs. Even though the replacement is computed by a function, the returned string **is still interpreted by Matcher according to replacement string syntax**, rather than always being inserted as plain text.

In replacement syntax:
- $1, $2, ... can reference capturing groups by number.
- Dollar-sign syntax with a group name in curly braces can reference named groups.
- Backslash \ can be used to escape the following character.

Therefore, if a function returns the literal **Price $5** or the path **C:\data\test**, the $ and \ characters can be interpreted as replacement syntax. Output may be wrong or throw an exception. When you want to return **verbatim text**, use:

~~~java
String literal = "Price $5";
String safe = Matcher.quoteReplacement(literal);
~~~

**Matcher.quoteReplacement(String)** creates a string that can be used as a replacement while preserving the literal content after replacement. If the lambda has already assembled the target string, the safe way is:

~~~java
return Matcher.quoteReplacement(computedValue);
~~~

Distinguish from **Pattern.quote(String)**: Pattern.quote turns user data into a literal **search pattern**; Matcher.quoteReplacement turns data into a literal **replacement string**. They serve opposite sides of search and replace.

When you **want** the replacement to execute group references such as $1, $2, you can intentionally return that syntax **without quoting**. If you have already used match.group(1) to construct the complete result inside the lambda, you should usually quote the result string to avoid $ or \ originating from data.

## 5. Complete Example: Replacing Placeholders from a Map, Preserving Special Characters

Requirement: a template string contains placeholders in the form {{key}}. Look up the corresponding value from a Map, keeping the placeholder unchanged if no data is present. Specifically, values may contain $ and \, and the output must preserve those exact characters.

Create the file **TemplateReplacementDemo.java**:

~~~java
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TemplateReplacementDemo {
    private static final Pattern PLACEHOLDER =
            Pattern.compile("\\{\\{([A-Za-z][A-Za-z0-9_]*)\\}\\}");

    public static void main(String[] args) {
        String input = "Person: {{person}}; folder: {{path}}; missing: {{unknown}}";
        Map<String, String> values = Map.of(
                "person", "Lan$1",
                "path", "C:\\data\\test"
        );

        String output = PLACEHOLDER.matcher(input).replaceAll(match -> {
            String key = match.group(1);
            String value = values.getOrDefault(key, match.group());
            return Matcher.quoteReplacement(value);
        });

        System.out.println(output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 TemplateReplacementDemo.java
java TemplateReplacementDemo
~~~

~~~text
Person: Lan$1; folder: C:\data\test; missing: {{unknown}}
~~~

**Explanation:** the regex accepts only placeholders matching the {{name}} structure. Group 1 is the key name such as person, path, unknown. The lambda retrieves the value from the Map; if absent, it uses match.group() to keep the placeholder. Then quoteReplacement ensures the $ in Lan$1 and the \ characters in the path are preserved. Without quoteReplacement, Lan$1 could be interpreted as a $1 group reference, and \ characters could be consumed during replacement processing.

This is a text replacement example, **not a complete templating system**: it does not handle HTML, URL, SQL, JavaScript, or other output-context escaping. When placing external data into those contexts, proper escaping or parameterized queries are still required.

## 6. Processing Order and Matcher State

Behaviorally, replaceAll(Function) restarts the search, finds matching segments in order, invokes the replacer for each segment, and assembles the result into an output string:

1. **No match:** the function is not called, and the input string's content is preserved.
2. **Multiple matches:** the function is called for the found matches, normally from left to right; matches found by find() are non-overlapping segments.
3. **Unmatched text:** always placed into the result intact.
4. **Replacement is not re-searched in the same pass:** if the newly inserted replacement also matches the regex, it is not processed again in the current call.
5. **Matcher holds traversal state:** replaceAll begins the replacement pass from the start of the Matcher's input region; do not expect a previous search position to be preserved. If you need to traverse again, create a new Matcher or call reset() properly.
6. **Do not modify the Matcher inside the replacer:** calling find(), reset(), region(), or state-mutating methods on the very Matcher performing replaceAll can throw ConcurrentModificationException. The callback should read the MatchResult argument and produce the return string.

Do not retain the MatchResult object given to the callback for use after the Matcher continues working; if you need to record data, copy group/start/end immediately inside the callback. An immutable Pattern can be reused from multiple threads, but each thread/request should use its own Matcher.

## 7. Comparison with find() + appendReplacement() + appendTail()

Before Java 9, programmers typically used a find() loop to compute per-match replacements. Two methods, appendReplacement() and appendTail(), help assemble the result: appendReplacement appends unprocessed text along with the current replacement; appendTail appends the remainder of the original string.

The following snippet assumes **pattern**, **input**, and a custom **transform(String)** method already exist (not a standalone compilable program):

~~~java
Matcher matcher = pattern.matcher(input);
StringBuffer output = new StringBuffer();

while (matcher.find()) {
    String replacement = transform(matcher.group());
    matcher.appendReplacement(
            output,
            Matcher.quoteReplacement(replacement)
    );
}
matcher.appendTail(output);
String result = output.toString();
~~~

With Java 9+, when the operation is simply generating a replacement from each match, you can write it more concisely:

~~~java
String result = pattern.matcher(input).replaceAll(
        match -> Matcher.quoteReplacement(transform(match.group()))
);
~~~

Both approaches must pay attention to replacement syntax, and both should be tested with data containing $ and \. The manual loop remains useful when you must manage additional state or assemble output using custom rules; the callback is more convenient for independent per-match transformations.

## 8. Conditions in the Lambda: Changing Only Some Matches

There are cases where the regex matches every segment to be inspected, but not every segment needs changing. The callback can decide to leave it unchanged by returning group() itself.

The following snippet assumes **input** has already been declared; the goal is to wrap single-digit numbers in square brackets while leaving other numbers unchanged:

~~~java
Pattern numbers = Pattern.compile("\\b\\d+\\b");
String result = numbers.matcher(input).replaceAll(match -> {
    int value = Integer.parseInt(match.group());
    String replacement = value < 10
            ? "[" + value + "]"
            : match.group();
    return Matcher.quoteReplacement(replacement);
});
~~~

Even on the keep-unchanged branch, the lambda is still invoked for that match. If you want to optimize, design the regex to find only the segments that truly need replacing when feasible. You should handle numbers that are too large or formatted differently before calling parseInt.

Callbacks should focus on **string computation**. Avoid writing to databases, making HTTP calls, mutating shared variables, or performing external interactions during a replaceAll call; such side effects easily lead to unpredictable results upon errors or retries. If computation per match is expensive, actual performance depends on match count, regex complexity, and the work done by the function.

## 9. Common Mistakes and How to Avoid Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Lambda for replaceAll fails to compile | Using Java 8 or calling String.replaceAll instead of Matcher.replaceAll. | Use Java 9+, call Pattern.compile(...).matcher(input).replaceAll(lambda). |
| Fails when value contains `$` | Data is interpreted as a group reference in the replacement. | Use Matcher.quoteReplacement for literal strings. |
| `\` disappears or alters the following character | Replacement interprets `\` as an escape character. | Quote literal replacement; double-check escaping in Java strings. |
| match.group("name") fails to compile on Java 17 | MatchResult in Java 17 uses group indices. | Use positional group(1), group(2). |
| NullPointerException when processing groups | Optional group did not participate, or lookup value is null. | Check for null and return a non-null default string. |
| NumberFormatException | Numeric data too long or invalid for the target parse type. | Restrict format/range; use long/BigInteger if needed. |
| ConcurrentModificationException | Lambda mutates the state of the Matcher currently performing replacement. | Use only the MatchResult argument; do not call find/reset on that Matcher. |
| Function does not run | No matches, or regex does not recognize expected segments. | Check the expression, compile flags, and input. |
| Replaces too much content | Regex is too broad, e.g., unconstrained `.*`. | Narrow the pattern, add proper boundaries, and test counterexamples. |
| Too slow on long inputs | Regex causes backtracking or function runs heavy work per match. | Benchmark, write clear regexes, and optimize callback work. |

## 10. Choosing a Solution in Practice

Choose **replaceAll(Function)** when the replacement string must be computed individually from the match content: numeric conversion, capturing-group normalization, Map lookup, or conditional logic. Choose **replaceAll(String)** when you only need a fixed template or group references in the replacement. Choose the **find + appendReplacement + appendTail** loop when you need control over output assembly or must maintain compatibility with older Java versions.

When testing, cover at least: input with no matches; multiple adjacent matches; optional capturing groups; replacements containing $ or \; out-of-range numbers; regexes that can match empty strings; and callback errors. An error in the callback can cause the entire replaceAll call to fail, so validate data and decide on an error-handling strategy before using it in an application.

Remember: **Pattern determines which segments are selected; Function decides each replacement string; Matcher interprets the replacement and assembles the result.** Understanding these three steps clearly makes using replaceAll with a function accurate, easier to test, and safer.