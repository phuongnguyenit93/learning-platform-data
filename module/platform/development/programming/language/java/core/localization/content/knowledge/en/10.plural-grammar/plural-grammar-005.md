# Nested Messages and Escaping Layers to Distinguish

A localized message pattern can contain **subpatterns** selected by quantity, gender, condition, or business branch. At the same time, that pattern often passes through multiple representation layers: **a Java string**, **a `.properties` or JSON file**, **the `MessageFormat` parser**, **`ChoiceFormat`/subpattern**, and finally **HTML or the user interface**. Each layer has different escaping syntax.

If the layers are confused, the program may print literal `{0}` instead of inserting an argument, drop single quotes in text, fail Java compilation, pick the wrong singular/plural sentence, or produce unsafe HTML. The solution is to identify **which layer a character belongs to**, **which layer runs first**, and **whether a subpattern is re-parsed or treated strictly as data**.

This lesson uses `java.text.MessageFormat` and `ChoiceFormat` in Java 17+ to explain pattern nesting mechanics, limits of threshold-based pluralization, and real-world escaping cases. Plural syntaxes of the ICU library are a separate system that must be read from that library's own documentation.

## 1. What Does a Nested Message Mean?

A simple message has a single pattern:

~~~text
Hello {0}, you have {1} notifications.
~~~

Here `{0}` and `{1}` refer to the corresponding positions in the argument array. For sentences with quantities, natural phrasing may vary:

~~~text
0 → You have no messages.
1 → You have one message.
5 → You have 5 messages.
~~~

Instead of writing three disconnected `if/else` sentences, `MessageFormat` can use a `choice` format element to pick a branch. The selected branch can in turn contain placeholders that need further substitution, such as `{0,number,integer}`.

Example pattern:

~~~text
You have {0,choice,0#no messages|1#one message|1<{0,number,integer} messages}.
~~~

This is a **nested pattern** in the sense that the `choice` part picks a string which in some branches contains `MessageFormat` syntax requiring further processing. It is not a nested JSON tree or nested bundle file; the nesting lies in the **pattern parsing/formatting pipeline**.

Two concepts must always be kept separate:

- **Branch selection:** `ChoiceFormat` selects a message fragment based on a numeric value of an argument.
- **Argument substitution inside the branch:** `MessageFormat` can format the selected branch fragment further when it contains placeholder syntax.

Do not assume every string returned by any formatter is automatically parsed a second time. This special mechanism belongs to how `MessageFormat` integrates `ChoiceFormat`.

## 2. Processing Layers: From Source Code to Output String

For a message stored in Java code, the common processing flow is:

~~~text
Java source containing a string literal
    ↓ Java compiler interprets Java string escapes
Runtime pattern string
    ↓ MessageFormat parses {index}, single quotes, and formats
Choice part selects a branch (if present)
    ↓ MessageFormat re-parses the selected branch when it contains pattern syntax
Final values are inserted into the string
    ↓ Encode for HTML/JSON/UI if needed
Displayed data
~~~

With a `.properties` file, the first layer is replaced by the **properties reader**: it interprets escapes defined for the resource file format and produces the pattern string. With JSON, the corresponding first layer is the **JSON parser**.

| Layer | Characteristic Syntax | Key Example |
| --- | --- | --- |
| Java string literal | `\\`, `\"`, `\n` | Java source `"A\nB"` creates a runtime string with a newline |
| Java `.properties` | `\n`, `\t`, `\\`, `\uXXXX`, backslash line continuation | Source `line=Hello\n{0}` becomes a pattern with a newline |
| JSON string | `\"`, `\\`, `\n`, `\uXXXX` | JSON is parsed **before** becoming a pattern |
| `MessageFormat` | `{0}`, `{1,number}`, `'`, `''` | `'{0}'` is literal placeholder text; `''{0}''` displays quotes around the value |
| `ChoiceFormat` | `|`, `#`, `<`, numeric limits | `0#none|1#one|1<many` |
| HTML | `&amp;`, `&lt;`, text/attribute escaping | MessageFormat output still requires context-appropriate encoding |

**Do not use a single “escape everything” function for all layers.** For instance, `\\` is an escape in Java strings or properties, but a backslash is **not** the way to quote curly braces in `MessageFormat`.

## 3. Syntax of `ChoiceFormat` Inside `MessageFormat`

In `java.text.MessageFormat`, a format element has the general form:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

For `choice`:

~~~text
{0,choice,0#none|1#one|1<many}
~~~

Meaning:

- The first `0`, before `,choice,`: **index of the argument** in the input array.
- `0#none`: selects the text `none` when the value reaches the branch with limit 0.
- `1#one`: selects `one` at limit 1.
- `1<many`: selects `many` when the value is **greater than 1**.
- `|`: separates choice branches.

`#` represents an **inclusive** limit; `<` represents an **exclusive** limit. `ChoiceFormat` selects branches based on thresholds; it does not inherently know the plural rules of individual languages.

With the pattern `0#none|1#one|1<many` and non-negative integers:

| Value | Branch |
| ---: | --- |
| 0 | `none` |
| 1 | `one` |
| 2 | `many` |
| 5 | `many` |

**Business scope limitation:** this pattern is designed only for non-negative integer counts. Negative inputs, fractions, or special values need explicitly defined rules. Do not apply an example threshold to every quantity problem and assume it is grammatically right.

## 4. Java 17+ Example: Select a Branch Then Format the Subpattern

Create the file **`NestedChoiceDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class NestedChoiceDemo {
    private static final String PATTERN =
            "You have {0,choice," +
            "0#no messages|" +
            "1#one message|" +
            "1<{0,number,integer} messages}.";

    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(PATTERN, Locale.US);

        System.out.println(formatter.format(new Object[]{0}));
        System.out.println(formatter.format(new Object[]{1}));
        System.out.println(formatter.format(new Object[]{5}));
    }
}
~~~

Compile and run:

~~~bash
javac NestedChoiceDemo.java
java NestedChoiceDemo
~~~

Output:

~~~text
You have no messages.
You have one message.
You have 5 messages.
~~~

In the third branch, `{0,number,integer} messages` contains a placeholder. `MessageFormat` treats the result of `ChoiceFormat` as **a pattern to format further**, so the count argument is substituted inside the branch.

Importantly, **argument indices do not change across nested parsing**: `{0,number,integer}` still points to `arguments[0]`. If `{1}` appears inside the branch, it still reads `arguments[1]` from the same array, not a first argument local to the sub-branch.

### Repeating indices and using multiple indices in a branch

Another example:

~~~text
Status: {0,choice,0#empty|1#one item for {1}|1<{0,number,integer} items for {1}}
~~~

With `new Object[]{3, "Lan"}`, the result is:

~~~text
Status: 3 items for Lan
~~~

In the last branch, `{0,number,integer}` and `{1}` are processed after `choice` selects that branch's text. This is the memorable “nesting” model of `MessageFormat` and `ChoiceFormat`.

## 5. Subpatterns Are Re-Parsed; Argument Data Is Not

The two snippets below look similar but mean different things.

**Scenario A:** `ChoiceFormat` returns a string containing `{1}`, and `MessageFormat` uses that string as a **nested pattern**.

**Scenario B:** `ChoiceFormat` returns the same string, but the application passes it as **the value of argument `{0}`** to another `MessageFormat`. Then `{1}` inside the value is treated as **data**, not parsed further.

Create **`NestedVersusDataDemo.java`**:

~~~java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class NestedVersusDataDemo {
    public static void main(String[] args) {
        ChoiceFormat choice =
                new ChoiceFormat("0#none|1#one|1<many {1}");

        String selected = choice.format(3);
        System.out.println(selected);

        MessageFormat asData =
                new MessageFormat("Status: {0}", Locale.US);
        System.out.println(asData.format(new Object[]{selected}));

        MessageFormat nested = new MessageFormat(
                "Status: {0,choice,0#none|1#one|1<many {1}}",
                Locale.US
        );
        System.out.println(nested.format(new Object[]{3, "X"}));
    }
}
~~~

~~~bash
javac NestedVersusDataDemo.java
java NestedVersusDataDemo
~~~

Output:

~~~text
many {1}
Status: many {1}
Status: many X
~~~

Explanation:

- `choice.format(3)` only produces the text `many {1}`.
- `asData.format(new Object[]{selected})` **inserts the string value verbatim**; it does not interpret `{1}` inside the argument as a placeholder to replace.
- `nested.format(new Object[]{3, "X"})` runs the choice mechanism **inside MessageFormat**; the `many {1}` branch is formatted further and receives `X`.

Positive consequence: user data containing `{0}` normally does not turn into pattern code if passed properly as an **argument**. Dangerous consequence: if the application constructs a new pattern from that data and re-parses it, the data can be interpreted as syntax. Keep **trusted patterns** separate from **dynamic values**.

## 6. Single Quotes Are `MessageFormat`'s Escape

When `MessageFormat` parses a pattern, the single quote `'` has special meaning:

- `''` in a pattern represents **one literal single quote**.
- `'{0}'` makes `{0}` **literal text**, without inserting the argument.
- `''{0}''` displays **single quotes around the inserted value**.

This is **not** Java syntax for creating strings. Those `'` characters inside **the runtime pattern value** are interpreted by `MessageFormat`.

Runnable example **`MessageQuoteDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        MessageFormat apostrophe =
                new MessageFormat("It''s {0}.", Locale.US);
        MessageFormat literal =
                new MessageFormat("Use '{0}' then {0}.", Locale.US);
        MessageFormat quotedValue =
                new MessageFormat("Value: ''{0}''.", Locale.US);

        System.out.println(apostrophe.format(new Object[]{"ready"}));
        System.out.println(literal.format(new Object[]{"X"}));
        System.out.println(quotedValue.format(new Object[]{"X"}));
    }
}
~~~

~~~bash
javac MessageQuoteDemo.java
java MessageQuoteDemo
~~~

Output:

~~~text
It's ready.
Use {0} then X.
Value: 'X'.
~~~

In natural languages, apostrophes such as in `It's`, `don't`, `l'utilisateur` are a frequent source of bugs. For patterns processed by `MessageFormat`, write `It''s`, `don''t`, `l''utilisateur` when you want them to appear properly.

**Common mistake:** writing `"Value: '{0}'"` and expecting to see `'X'`. In `MessageFormat`, that pattern displays `Value: {0}` because `{0}` was quoted into a literal.

## 7. Curly Braces: Do Not Escape with Backslash

In `MessageFormat`:

~~~text
'{0}'        → literal text {0}
{0}          → value of the first argument
''{0}''      → ' + argument value + '
~~~

The backslash `\` is **not** a mechanism to quote placeholders. If you write `\{0}` in a runtime pattern, the backslash does not stop `{0}` from being interpreted as a substitution.

The right way to display a literal string with braces like `{name}` is to quote the braced segment using **`MessageFormat`'s single-quote rule**, for example:

~~~text
Pattern:  Please type '{name}' exactly.
Output:   Please type {name} exactly.
~~~

Do not try to create a placeholder named `name` and pass an argument under that key: `java.text.MessageFormat` uses **numeric indices** and does not support `{name}` as a named reference.

When a string has multiple pairs of braces or apostrophes, write tests against the **final runtime pattern**. Looking at Java source code or a `.properties` file while ignoring the first parsing layer easily leads to miscounting escape characters.

## 8. Escaping in Java String Literals vs. Escaping in `MessageFormat`

When a pattern is written directly in Java, the Java compiler must process the string literal first.

Example:

~~~java
String pattern = "It''s {0}";
~~~

The runtime string still contains `It''s {0}`; single quotes do not need backslash escaping inside a Java **double-quoted string literal**. However, when the pattern passes through `MessageFormat`, the two single quotes are processed into one displayed single quote.

Comparison:

| Java Source | Runtime String Before Formatting | `MessageFormat` with Argument `X` |
| --- | --- | --- |
| `"Hi {0}"` | `Hi {0}` | `Hi X` |
| `"It''s {0}"` | `It''s {0}` | `It's X` |
| `"'{0}'"` | `'{0}'` | `{0}` |
| `"''{0}''"` | `''{0}''` | `'X'` |
| `"A\n{0}"` | Two lines: `A` then `{0}` | Two lines: `A` then `X` |

In the `"A\n{0}"` example, the sequence `\n` is converted by the **Java compiler** into a newline character before `MessageFormat` receives the pattern.

Double quotes `"` in Java source must be escaped per Java rules to appear inside a string literal; curly braces `{` are not a Java string escape. Do not use `\\'` in a Java string to “fix” how `MessageFormat` interprets apostrophes: backslashes belong to the Java layer and do not replace `''` at the pattern layer.

### How to inspect when it is hard to tell apart

Log or debug the string **after Java has created the string** and **before passing it to `MessageFormat`**. If the runtime string is already not what you expect, the bug is in the string literal layer. If the runtime pattern is right but the output drops an apostrophe or prints literal `{0}`, check `MessageFormat` syntax.

## 9. Escaping in `.properties` Differs from `MessageFormat` Escaping

When placing translations in `.properties` files, there are **two consecutive transformations**:

~~~text
.properties file content
    → PropertyResourceBundle / properties parser
Runtime pattern string
    → MessageFormat parser
Result string
~~~

Example **`Messages_en.properties`**:

~~~properties
success=It''s ready, {0}.
literal=Type '{0}' then enter {1}.
line=First line\nSecond line: {0}
~~~

Points to remember:

- `It''s` uses **two single quotes** because of **MessageFormat** rules, not because the properties parser requires it.
- `'{0}'` is preserved in the pattern and `MessageFormat` prints `{0}` literally.
- `\n` in `.properties` is an escape that produces a **newline character** after the parser reads the file; `MessageFormat` receives a string that already contains a newline.
- In `.properties`, a backslash must be written as `\\` if you want to preserve a literal backslash after reading. A single backslash before an unspecified character may be stripped by the parser without preserving the backslash itself.

Create **`PropertiesMessageDemo.java`** and place it in the same directory as `Messages_en.properties`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class PropertiesMessageDemo {
    public static void main(String[] args) {
        Locale locale = Locale.ENGLISH;
        ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

        String success = bundle.getString("success");
        String literal = bundle.getString("literal");
        String line = bundle.getString("line");

        System.out.println(new MessageFormat(success, locale)
                .format(new Object[]{"Lan"}));
        System.out.println(new MessageFormat(literal, locale)
                .format(new Object[]{"ignored", "X"}));
        System.out.println(new MessageFormat(line, locale)
                .format(new Object[]{"done"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PropertiesMessageDemo.java
java -cp . PropertiesMessageDemo
~~~

Output:

~~~text
It's ready, Lan.
Type {0} then enter X.
First line
Second line: done
~~~

Notice the order: the file contains `\n` as **two characters** (backslash + letter `n`), yet the output contains a single newline because the properties parser layer processes it first. The Java source code contains no corresponding `\n` for this value.

`ResourceBundle` can fall back to another translation if a bundle or key is missing; when troubleshooting escaping bugs, confirm **which bundle was actually loaded** and **what the runtime pattern string is**. Avoid “fixing” a file that the application never loaded.

## 10. JSON and Transport Formats Do Not Share the Same Rules

If messages are stored as JSON, the JSON parser also processes strings before `MessageFormat` sees them:

~~~json
{
  "message": "It''s {0}.",
  "twoLines": "First line\nSecond line: {0}"
}
~~~

In JSON, `\n` represents a newline; in the parsed string, that character is no longer two characters (backslash + `n`). The `''` syntax has no special meaning to JSON; it becomes special **only when the string is passed into `MessageFormat`**.

If the string is embedded inside another Java literal to build JSON, there is yet another escaping layer **before the JSON parser**. Do not count backslashes by intuition: trace each step from source to runtime pattern.

Do not confuse Java `MessageFormat` syntax with the ICU MessageFormat library or ICU plural syntax:

~~~text
{count, plural, one {...} other {...}}
~~~

This is **not** a plural syntax accepted by standard Java 17 `java.text.MessageFormat`. To use ICU plurals, you need a formatter/library with a corresponding ICU parser; `ChoiceFormat` in the JDK uses different thresholds and rules. Pasting an ICU pattern verbatim into `new java.text.MessageFormat(...)` can cause parse errors.

## 11. Subpatterns and Apostrophes: Why Must Multiple Parse Passes Be Considered?

`MessageFormat` receives the outer pattern. When selecting a `choice` branch whose content looks like a pattern, it can create and use another `MessageFormat` to format the **branch string**. This introduces an additional **layer of single-quote and brace interpretation**.

Example:

~~~text
{0,choice,0#none|1#one|1<{0,number,integer} items}
~~~

In the last branch, `{0,number,integer}` is not fixed text; it is parsed as a placeholder when the branch is formatted again.

If you want a branch segment to contain a **literal single quote**, or **literal braces**, you must account for two parser passes: the outer pattern (including single-quote processing) and the selected branch pattern. The number of apostrophes needed can differ when the pattern lives in `.properties`, a Java string, or a string already constructed by code.

**There is no shortcut rule like “always double quotes once and it is enough” for all nesting depths.** A better process:

1. Write down the **desired output string**.
2. Identify which placeholders must be processed in the **subpattern**.
3. Write a valid subpattern for its parser and test it standalone if possible.
4. Build the outer pattern; determine which quote characters will be consumed by the outer parser.
5. Finally, encode the outer pattern according to the storage source: Java literal, `.properties`, or JSON.
6. Test with **every choice branch**, especially branches not triggered by typical test data.

Testing only the `0#...` branch and assuming the entire pattern is safe is insufficient: bugs in the `1<...` branch may only surface when the actual count exceeds 1.

### Avoiding deep nesting when hard to maintain

If nesting grows rapidly and quoting becomes hard to read, an application can:

- Use **separate message keys for each branch** and format each message exactly once.
- Select branches in well-tested code, passing dynamic data as **arguments** rather than concatenating pattern strings.
- Use a plural/grammar library suitable for the languages the product serves.

The goal is grammatical correctness and easy verification, not maximizing `ChoiceFormat` nesting depth.

## 12. Special Bug: User-Supplied Strings Parsed as Patterns

Suppose a user enters the text:

~~~text
Hello {1}
~~~

**If passed as an argument**, `MessageFormat` treats it as data:

~~~java
MessageFormat formatter =
        new MessageFormat("Comment: {0}", Locale.US);
System.out.println(formatter.format(new Object[]{"Hello {1}"}));
~~~

This snippet sits inside a method importing `java.text.MessageFormat` and `java.util.Locale`. Output:

~~~text
Comment: Hello {1}
~~~

There is no second parse pass on argument contents under this normal usage.

**If concatenated into the pattern**:

~~~java
String userInput = "Hello {1}";
String pattern = "Comment: " + userInput + " / {0}";
MessageFormat formatter = new MessageFormat(pattern, Locale.US);
~~~

`{1}` inside the data has been injected into **pattern syntax**; the result may be substituted, left unreplaced due to a missing argument, or break the pattern if other text contains special characters. Therefore, **never build patterns from untrusted data**.

For values used with nested choice, care is even more critical: a re-parsed branch can turn `{...}` characters into placeholders if they belong to the branch's **pattern**. Keep patterns managed by the application or a trusted translation system, and keep user content in arguments.

This only addresses the **`MessageFormat` syntax** boundary. When output is placed into HTML, URLs, SQL, or another template, safety handling for **that target** is still required. `MessageFormat` does not automatically HTML-encode or replace prepared statements.

## 13. HTML Escaping and MessageFormat Escaping Are Two Separate Concerns

Suppose the formatted output is:

~~~text
Hello <script>alert(1)</script>
~~~

To `MessageFormat`, `<` and `>` are ordinary text characters. If the string above is assigned to `innerHTML` without handling, the browser can interpret user-supplied HTML.

To display **plain text**, the UI should use text-assignment APIs such as `textContent` on the web, or HTML-encode for the exact **output context** when generating HTML is required. Do not replace all MessageFormat apostrophes/braces and assume you have achieved HTML safety.

| Character / Syntax | Relevant Layer | Interpretation |
| --- | --- | --- |
| `{0}` | `MessageFormat` | Substitutes argument 0 |
| `'{0}'` | `MessageFormat` | Prints `{0}` literally |
| `&lt;` | HTML text | Represents `<` when rendering HTML |
| `\"` in JSON string | JSON parser | Produces a double quote inside the string value |
| `\\` in `.properties` | Properties parser | Keeps one literal backslash after reading |
| `<script>` in argument | Output UI | Must not be assumed HTML-safe just because it passed through MessageFormat |

Proper escaping syntax at **one layer** does not replace escaping at **another layer**.

## 14. Plurals and Grammar: Limitations of `ChoiceFormat`

The three-branch example 0, 1, many for English is easy to understand, yet insufficient to support global plural rules.

Some languages have distinct plural forms for 0, 1, 2, number groups like 3–10, numbers ending in 1, or decimals. `ChoiceFormat` relies on **numeric thresholds**, so many branches would be required and it still might not accurately express all CLDR plural rules.

Therefore:

- Do not treat `0#...|1#...|1<...` as a correct plural algorithm for every locale.
- Do not confuse `{0,number,integer}` with selecting **word morphology** by count; it only formats the number.
- For multilingual products, consider an i18n tool that understands each language's **plural categories** and test `0`, `1`, `2`, `5`, `11`, `21`, negative numbers, and decimals depending on the language.
- When using a non-JDK library, use **that library's parser and escaping rules**; do not blindly apply Java `ChoiceFormat` assumptions to ICU messages.

A string can be **syntactically valid** yet **grammatically wrong**. Successful formatting does not prove a translation is natural in every locale.

## 15. Testing Escaping and Nested Messages

Build test suites around the **final output strings**, rather than only checking that patterns look right.

| Scenario | What to Check |
| --- | --- |
| `choice` with 0, 1, 2, 5 | Correct branch and grammar across supported data domain |
| Subpattern containing `{0}` or `{1}` | Uses the right arguments array in the nested parse |
| Same `{1}` string passed as an argument | Preserved verbatim as data, not parsed as a pattern |
| `It's` / `don't` | Apostrophes appear correctly |
| `'{0}'` / `''{0}''` | Distinguishes literal placeholder from quoted value |
| `.properties` containing `\n` | Actual newline exists after reading the resource |
| JSON containing `\n` | JSON parser handles escapes before the formatter |
| Invalid pattern or missing arguments | Never leak `{1}` into the UI due to a broken data contract |
| JDK/provider upgrades | Watch for changes in localized numbers/dates, spacing, and display rules |
| HTML output with dynamic content | Encode per HTML context; do not rely on MessageFormat |

### Testing branches independently

With `ChoiceFormat`, do not test just one “representative” number and skip boundaries. For `0#none|1#one|1<many`, test at minimum `0`, `1`, `2`, and out-of-domain values if the API can receive them.

If a sub-branch contains a new placeholder `{2}` while the code passes only two arguments, the output may leave `{2}` intact. Catch this via contract tests over **index sets and the meaning of each index**, rather than hoping the formatter always throws an error.

### Testing literal apostrophes across multiple sources

The same English message, such as “It's ready, Lan.”, when stored in a Java string literal, `.properties`, and JSON, may be written differently with respect to backslashes, yet the **decoded runtime pattern** must preserve `It''s ready, {0}.`. Only then does `MessageFormat` produce output with one apostrophe.

Do not run global regex replacements on `'` or `{...}` across translation files without understanding parser order; you can break already properly quoted patterns.

## 16. Common Misconceptions

1. **“`ChoiceFormat` automatically handles CLDR plurals.”** No: it selects branches by numeric limits, not a multilingual plural rules engine.
2. **“Any returned string containing `{1}` will be re-parsed by `MessageFormat`.”** No: strings entering as arguments are data; subpatterns chosen from `choice` inside `MessageFormat` have their own mechanism.
3. **“Backslashes escape `MessageFormat` curly braces.”** No: use the pattern's single-quote rule.
4. **“Writing `'{0}'` prints single quotes around the argument.”** False: it prints literal `{0}`; `''{0}''` is needed to print `'X'`.
5. **“Putting a pattern in a properties file means apostrophes don't need quoting.”** False if the pattern is passed to `MessageFormat`; the properties parser does not replace formatter rules.
6. **“If it escapes cleanly in Java source, it's definitely right for MessageFormat.”** False: those are two sequential parsers.
7. **“JSON and Java MessageFormat share the same plural syntax.”** False: JSON only acts as a string transport format; `MessageFormat` governs the syntax of the pattern inside.
8. **“Nesting another formatting pass is always safe and preserves meaning.”** False: strings containing braces or apostrophes may be re-parsed as syntax.
9. **“MessageFormat automatically prevents XSS when rendering HTML.”** False: output must be encoded for the HTML context.
10. **“If one branch runs right, the whole pattern is right.”** False: unexercised branches may have missing placeholders or broken grammar logic.

## 17. Practical Application Workflow

1. **Identify the pattern source** (Java source, `.properties`, JSON, or an i18n library catalog) and the first parser that reads it.
2. **Define the argument contract**: what index 0 represents, what index 1 represents, and what data types are expected.
3. **Design branches** for real grammatical needs. Use `ChoiceFormat` for suitable threshold problems; for complex plurals, choose a tool with locale-specific plural data.
4. **Write the runtime pattern**, then escape for **`MessageFormat`** (apostrophes, braces) and for the **storage source parser**.
5. **If there are subpatterns**, test the selected part standalone and then test the full pattern to catch nested parse bugs.
6. **Pass `Locale` explicitly** when formatting numbers/dates; do not change the JVM default per request.
7. **Pass user data as arguments**, avoiding pattern concatenation; encode the result for its display destination.
8. **Test every branch and product-supported locale**, especially single quotes, literal braces, boundary quantities, and escaping layers.

### Self-Check

**Question 1.** Why can `Status: many {1}` appear verbatim when passing `many {1}` as an argument to `MessageFormat("Status: {0}")`?

**Answer:** `{1}` is **inside argument data**, so it is not parsed as a placeholder.

**Question 2.** Why can `{1}` in the `1<many {1}` branch of a `choice` nested inside `MessageFormat` become `X`?

**Answer:** The selected branch fragment is processed as a **nested pattern** using the same argument array.

**Question 3.** To print `It's ready.` from `MessageFormat`, what must be written in the runtime pattern?

**Answer:** `It''s ready.` — two apostrophes to produce one displayed apostrophe.

**Question 4.** Is using `\{0}` to print literal `{0}` correct?

**Answer:** No. In `MessageFormat`, use `'{0}'` in the runtime pattern.

**Question 5.** Can a string properly escaped for `MessageFormat` be inserted straight into HTML?

**Answer:** Not necessarily. You must still encode content for the HTML context or use an appropriate text-display API.

**Key Takeaway:** **Nested messages mean nested pattern interpretations; escaping must be right at every layer.** Distinguish source strings, runtime patterns, re-formatted `choice` branches, argument data, and the final display context. When the layers are clearly separated, writing and testing multilingual translations becomes far more reliable.
