# Repeated Replacement and the Limits of Using Regex Instead of a Parser

## 1. Two Kinds of "Multiple" Replacement

In Java, `String.replaceAll(String regex, String replacement)` finds **regex-matching and non-overlapping** segments in the input string, then replaces all of those segments in **a single pass**. It does not automatically continue searching inside the newly replaced text itself.

This differs from a program **calling replacement repeatedly over multiple passes**, such as looping until the result stabilizes, or applying multiple replacement rules in sequence.

```java
String once = "aaaa".replaceAll("aa", "a"); // "aa", not "a"

String twice = once.replaceAll("aa", "a");  // "a"
```

In the first pass, the two `"aa"` parts of `"aaaa"` are replaced with two `a` characters, yielding `"aa"`. Only the second pass produces `"a"`. One call to `replaceAll` replaces **all matches of the current pass**, not "loop until no matches remain".

`String` is an immutable type: each method returns a new string or the current string when unchanged; to use the result further, you must reassign the variable.

## 2. Choosing the Right Rule Before Looping

**String.replace** replaces fixed text literally; **String.replaceFirst** and **String.replaceAll** search by regex, replacing either the first match or every non-overlapping match in a single pass. If using the same regex across multiple inputs, compile one **Pattern** and create a separate **Matcher** for each input.

A fixed replacement template can reference groups using **$1** or **${name}**; literal values containing dollar signs or backslashes require **Matcher.quoteReplacement**. If the replacement depends on each match, Java 9+ provides **Matcher.replaceAll(Function<MatchResult,String>)**, while **appendReplacement/appendTail** helps when you want control over assembling the text. Choosing the right API does not replace the need to analyze convergence and the limits of structured data in the sections below.

## 3. Compilable and Runnable Java 17+ Example

Create the file `RepeatedRegexReplacementDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RepeatedRegexReplacementDemo {
    // Only use when the rule has a basis for convergence.
    private static String replaceUntilStable(
            String input, Pattern pattern, String replacement, int maxPasses) {
        if (maxPasses < 1) {
            throw new IllegalArgumentException("maxPasses must be positive");
        }

        String current = input;
        for (int pass = 0; pass < maxPasses; pass++) {
            String next = pattern.matcher(current).replaceAll(replacement);
            if (next.equals(current)) {
                return current;
            }
            current = next;
        }
        throw new IllegalStateException("No convergence within limit");
    }

    public static void main(String[] args) {
        // One pass collapses consecutive whitespace groups.
        String text = "red  green\tblue";
        System.out.println("Normalize: "
                + text.replaceAll("\\s+", " ").trim());

        // Single pass differs from looping multiple passes until stable.
        System.out.println("Single pass: " + "aaaa".replaceAll("aa", "a"));
        System.out.println("Until stable: "
                + replaceUntilStable("aaaa", Pattern.compile("aa"), "a", 10));

        // Literal replace differs from replaceAll which takes a regex.
        System.out.println("Literal dot: " + "a.b".replace(".", "|"));
        System.out.println("Regex dot: " + "a.b".replaceAll(".", "|"));

        // First match differs from all matches.
        System.out.println("First: " + "foo foo".replaceFirst("foo", "bar"));
        System.out.println("All: " + "foo foo".replaceAll("foo", "bar"));

        // Literal replacement containing special characters of replacement syntax.
        String price = "$5\\item";
        String safe = Pattern.compile("\\{\\{price\\}\\}")
                .matcher("cost={{price}}")
                .replaceAll(Matcher.quoteReplacement(price));
        System.out.println("Safe literal: " + safe);

        // Compute a separate replacement for each match (Java 9+).
        String calculated = Pattern.compile("(\\w+)=(\\d+)")
                .matcher("a=3;b=42")
                .replaceAll(match ->
                        match.group(1).toUpperCase()
                                + "=" + (Integer.parseInt(match.group(2)) + 1));
        System.out.println("Calculated: " + calculated);

        // Regex does not understand CSV double-quote rules.
        String csv = "a,\"b,c\",d";
        System.out.println("Naive CSV: " + csv.replaceAll(",", "|"));

        // A zero-width pattern can lead to inserting characters.
        System.out.println("Zero width: " + "aa".replaceAll("(?=a)", "X"));
    }
}
```

Compile and run:

```bash
javac RepeatedRegexReplacementDemo.java
java RepeatedRegexReplacementDemo
```

Output:

```text
Normalize: red green blue
Single pass: aa
Until stable: a
Literal dot: a|b
Regex dot: |||
First: bar foo
All: bar bar
Safe literal: cost=$5\item
Calculated: A=4;B=43
Naive CSV: a|"b|c"|d
Zero width: XaXa
```

In the `Until stable` section, the data goes through `"aaaa" → "aa" → "a"`: it takes **two passes with changes** and one check pass that sees no further change. The `Calculated` section computes a separate result for each match: `a=3` becomes `A=4`, and `b=42` becomes `B=43`. The `Naive CSV` section shows that regex replaces even a comma **inside a double-quoted field**, which is not a field delimiter according to CSV rules.

## 4. Replacing by Multiple Rules: Order Matters

Multiple rules can be chained for simple text processing:

```java
String input = "  Hello,\tJava!!  ";
String result = input
        .replaceAll("\\s+", " ")  // Collapse whitespace groups.
        .replaceAll("!+", "!")    // Collapse consecutive ! marks.
        .trim();                  // Remove leading and trailing whitespace.

System.out.println(result);      // Hello, Java!
```

This is an **illustrative snippet inside a method or block**, not a standalone Java class. Each call uses the result of the previous call, so changing the order can change the result. For example, if the first rule changes `"ab"` to `"b"`, and the second rule changes `"b"` to `"c"`, the string `"ab"` can reach `"c"` when used in the right order; reversing the order leaves `"b"`.

When using a regex many times, compile `Pattern` once:

```java
Pattern whitespace = Pattern.compile("\\s+");
String first = whitespace.matcher("a   b").replaceAll(" ");
String second = whitespace.matcher("c\t d").replaceAll(" ");
```

`Pattern` is designed for reuse. `Matcher` holds search state, so create a new `Matcher` for each string or manage state with appropriate APIs; do not share a single `Matcher` concurrently across multiple threads.

If you need to replace using capturing groups, you can use replacement syntax:

```java
String result = "2026-10-23".replaceAll(
        "(\\d{4})-(\\d{2})-(\\d{2})", "$3/$2/$1");
// result = "23/10/2026"
```

Capturing groups help reorder data with **simple, controlled** structure. Replacement strings obtained from external sources require `Matcher.quoteReplacement` if they are to be inserted literally. Even `Matcher.replaceAll(match -> ...)` returns a **replacement string** with `$`/`\\` syntax; wrap the result in `Matcher.quoteReplacement` if it may contain special characters and must be inserted literally.

## 5. Looping Until Stable: It Does Not Always Terminate

The rule `"aa" → "a"` reduces the number of `a` characters on each pass, so it has a basis for convergence. But not every replacement has this property:

- `"a" → "aa"`: each pass makes the string longer, never stabilizing if the input still contains `a`.
- Alternating rules `"a" → "b"` and `"b" → "a"`: can return to a previous state, creating a cycle.
- Some rules generate many new patterns, causing output size to grow rapidly and processing cost to rise accordingly.

The `replaceUntilStable` loop in the example uses a `maxPasses` limit and **throws an error** when it has not converged, avoiding infinite loops from merely waiting for two consecutive strings to be equal. However, limiting the number of passes **does not automatically limit string size**: in practice you may also need limits on output size, execution time, and detection of cycles longer than one state.

When designing an iterative pipeline, you should define:

1. **Stopping condition:** unchanged from the previous pass, no remaining tokens to replace, or reaching the specified pass limit.
2. **Reason for convergence:** for example, a non-negative quantity that strictly decreases on every pass. If unproven, you must handle the non-convergence case.
3. **Resource limits:** pass count, input/output size, and memory to allocate.
4. **Failure rule:** report an explicit error rather than silently returning an incomplete result if the caller expects a stabilized result.

A single `replaceAll` does not find all **overlapping matches**. For instance, `"aaa"` has two starting positions for the pattern `"aa"` if overlaps are considered, yet `replaceAll("aa", "X")` takes only the first match and produces `"Xa"`. If the problem truly requires handling overlapping matches, design a lookahead deliberately or write a character-index scanner; arbitrarily looping `replaceAll` is not a general solution.

**Zero-width** patterns, such as `(?=a)`, can insert rather than delete characters: `"aa".replaceAll("(?=a)", "X")` produces `"XaXa"`. The engine manages advancing past zero-width matches within one pass, though the output still needs thorough testing at start/end of string, empty strings, and with Unicode.

## 6. Limits of Using Regex Instead of a Parser

Regex describes **text patterns** and is suitable for local transformations, such as normalizing whitespace, masking an ID string with a simple format, changing a well-delimited prefix, or replacing a fixed token. A **parser** understands the roles of components in a grammar, such as "this character is inside a double-quoted string", "which tag does this attribute belong to", or "which nesting level does this parenthesis belong to".

| Data | Why simple regex replacement easily fails | Appropriate approach |
| --- | --- | --- |
| CSV | Commas inside double-quoted fields do not separate columns; there are also quote escapes and newlines inside fields. | Use a CSV parser to read each field and then write data according to CSV rules. |
| JSON | Commas, colons, brackets, and quotes play different roles depending on state; nested objects/arrays, escaped strings. | Parse JSON into a tree/object, modify the right node, then serialize. |
| HTML/XML | Tags, attributes, entities, comments, text nodes, and tree structure; `>` can appear inside a quoted attribute value. | Use an HTML/XML parser to manipulate nodes or attributes. |
| SQL and source code | Punctuation inside string literals, comments, and nested structures do not share the same meaning as syntax tokens. | Use a lexer/parser/AST or specialized API. |
| Arbitrarily deep nested brackets | Patterns need to remember structural levels; standard Java regex is not a general parser for unbounded nesting grammars. | Use a parser or a scanner with an explicit stack/state. |

For example, the CSV snippet `a,"b,c",d` has **3 fields**. Replacing all commas with `|` via regex produces `a|"b|c"|d`, putting a `|` inside the `"b,c"` field; afterward one cannot assume every `|` is a new separator of three fields. A CSV parser distinguishes commas **outside** and **inside** double quotes, including escaped quotes.

Similarly, an expression like `<[^>]*>` does not make a complete HTML parser: `>` can appear inside a quoted attribute, and tag/comment/text contexts can differ. Adding regexes to patch individual cases easily makes the solution hard to understand and prone to corrupting valid data.

**Decision criterion:** If how to replace depends on quote context, escaping, tree structure, nesting scope, or document grammar, use the **parse → modify structure → serialize** model. If the match depends only on a known local text fragment, regex may be appropriate.

Not every change in JSON, HTML, or CSV strictly forbids regex: for example, you can replace an independent text segment already extracted by a parser. What to avoid is using regex to **guess structural boundaries** of an entire complex document.

## 7. Performance and Common Mistakes

**Excessive backtracking.** Some regexes with nested quantifiers or ambiguous branches like `(a+)+$` can be very slow on long strings consisting of many `a`s followed by a non-matching character. Java `Pattern` uses a backtracking engine; for untrusted inputs or patterns, limit data size, avoid ambiguous patterns, and test worst-case inputs. Do not concatenate user-entered strings directly into a regex if the requirement is only literal matching.

**Repeated scanning and excessive string allocation.** Each regex pass may rescan a large string and allocate a new result. If the algorithm needs very many passes, consider a single-pass state scanner over the data or an appropriate parser.

**Confusing `replaceAll` with `replace`.** `.`, `|`, `*`, `[`, and `\\` have special syntax in regex. When replacing fixed text, `String.replace` is easier to read and less error-prone. If you still use regex with literal delimiters, apply `Pattern.quote` to the pattern.

**Confusing `$` and `\\` in the replacement.** If you want to insert the literal `"$5\item"`, use `Matcher.quoteReplacement`. If you intend to use capturing groups, `$1` or `${name}` syntax requires the capturing group to exist; otherwise an error may occur.

**Seemingly harmless rules that break syntax.** Globally replacing commas in CSV, replacing words inside source-code string literals, or renaming JSON keys by running regex over the whole document can replace the wrong locations. For structured data, use a parser.

**Missing boundary tests.** Test start/end of string, no match, consecutive matches, empty strings, zero-width matches, `$`, backslashes, Unicode, line breaks, and large data. Regex flags `DOTALL`, `MULTILINE`, `CASE_INSENSITIVE` can change the meaning of a pattern; use them deliberately with appropriate test cases.

## 8. Self-Check

**Question 1.** Why does `"aaaa".replaceAll("aa", "a")` return `"aa"`, while calling it one more time returns `"a"`? Explain using the concepts of non-overlapping matches and not rescanning the output.

**Question 2.** If a user submits the replacement text `"$5\item"`, why can passing it directly into `replaceAll` cause an error or alter the data? Point out the API used to quote the replacement part and the API used to quote the pattern part.

**Question 3.** To replace the field separator in the CSV `a,"b,c",d` while keeping the comma inside `"b,c"`, why is a single `replaceAll(",", "|")` insufficient? Describe the steps using a CSV parser.

**Question 4.** Does a rule replacing `"a"` with `"aa"` converge when looped until unchanged? If not, what limits must the loop enforce?

**Key takeaway:** `replaceAll` replaces all non-overlapping matches **in one pass**. When looping multiple passes, control stopping conditions and resources; when replacement depends on the structure/grammar of the data, use a parser to modify the right components.