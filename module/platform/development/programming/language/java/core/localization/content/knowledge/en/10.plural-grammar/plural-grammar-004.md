# Combining ChoiceFormat with MessageFormat

## 1. The Problem: Quantities Change the Entire Sentence

In multilingual applications, message content often depends on quantity:

- No files.
- One file.
- 2 files.

In English, the corresponding examples are “No files”, “One file”, “2 files”. An inflexible implementation concatenates the count with a translated noun:

```java
String text = "You have " + count + " files.";
```

This sentence is wrong when `count == 1`: “You have 1 files.”. Adding `if (count == 1)` only handles a few English cases, whereas the grammar of another language can change verbs, nouns, forms of address, or punctuation.

Java has two APIs in `java.text` that help handle **certain sentence forms that vary by numeric value ranges**:

- **`ChoiceFormat`** selects a text branch based on numeric thresholds. For example, 0 and below selects sentence A, exactly 1 selects sentence B, and greater than 1 selects sentence C.
- **`MessageFormat`** inserts parameters into a **complete sentence** with `{0}`, `{1}`, … syntax; when a `choice` branch contains a nested placeholder, `MessageFormat` can further interpret that branch to insert the quantity.

Combining both APIs allows writing a single message with choices:

```text
You have {0,choice,0#no files|1#one file|1<{0,number,integer} files}.
```

With `0` it produces “You have no files.”, with `1` “You have one file.”, and with `2` “You have 2 files.”. The varying text parts stay inside the same template rather than forcing translators to piece fragments together.

**Important scope:** `ChoiceFormat` is a **numeric-threshold selection** mechanism, not a complete solver for plural rules of every language. This affects how real-world problems are designed.

## 2. How Does ChoiceFormat Work?

`java.text.ChoiceFormat` represents a sequence of thresholds and corresponding strings. Given an input numeric value, it finds the branch whose limit matches the declared intervals. Limits must be in ascending order.

Basic `ChoiceFormat` pattern:

```text
0#No files|1#One file|1<Many files
```

Syntax meaning:

| Component | Meaning |
| --- | --- |
| `0`, `1` | Numeric thresholds used to select a branch |
| `#` | Branch applies **from that threshold upward**, including the threshold itself |
| `<` | Branch applies to values **greater than** the threshold, excluding the threshold |
| `|` | Separator character between choices |
| Text after the threshold delimiter | Value returned when that branch is selected |

With `0#No files|1#One file|1<Many files`:

- `0` selects `No files`.
- `1` selects `One file`.
- `2` selects `Many files`.

In the `1<` branch, the threshold greater than 1 starts immediately after `1` in `double` representation; values like `1.1` also fall into this branch. Therefore, this branching **is only appropriate** when the contract accepts the inputs used, such as non-negative integer counts.

**A subtle bug:** if a value is smaller than the first threshold, `ChoiceFormat` still selects the first choice. Thus a pattern starting at `0#` can display “No files” for a negative number. If negative numbers are invalid data, validate inputs before formatting rather than hoping ChoiceFormat rejects them automatically.

A `ChoiceFormat` can be created from a pattern string or from two equal-sized arrays: `double[] limits` and `String[] formats`. These are two ways of constructing the same threshold-based branch selector.

## 3. What Does MessageFormat Add?

`MessageFormat` has parameter syntax:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Examples:

- `{0}`: uses the first argument.
- `{0,number,integer}`: formats the first argument as an integer.
- `{0,choice,0#none|1#one|1<many}`: selects a branch based on the number.
- `{1}`: uses the second argument, such as the message recipient's name.

When `MessageFormat` processes a `choice` argument:

1. Retrieves the corresponding numeric argument.
2. Passes that value to `ChoiceFormat`.
3. Selects the text of one branch.
4. If the branch text contains a placeholder like `{0,number,integer}`, `MessageFormat` processes the branch as a **nested message pattern** with the same argument list.

Thanks to the fourth step, the “many” branch can include the **actual quantity**; if you only call `ChoiceFormat.format(2)` directly, the string `{0,number,integer} files` is just raw text not yet interpreted by MessageFormat.

Example pattern (Vietnamese):

```text
Có {0,choice,0#không có tệp nào|1#một tệp|1<{0,number,integer} tệp}.
```

What the user sees:

| Input `count` | Output |
| ---: | --- |
| 0 | `Có không có tệp nào.` |
| 1 | `Có một tệp.` |
| 2 | `Có 2 tệp.` |

The pattern above is **mechanically valid yet unnatural for the 0 case** (“Có không có tệp nào”). This is an important lesson: the branch-selection algorithm can be right while **the whole sentence is still grammatically wrong**. Translators need to be allowed to replace **the entire clause** in each branch, without being locked into a rigid prefix.

## 4. Complete Example: Each Branch Is a Natural Sentence

Put the full message inside each branch so grammar can be adjusted completely:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceMessageDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#Không có tệp nào.|1#Có một tệp.|1<Có {0,number,integer} tệp.}";

        MessageFormat message = new MessageFormat(
                pattern, Locale.forLanguageTag("vi-VN"));

        for (int count : new int[] {0, 1, 2, 5}) {
            System.out.println(message.format(new Object[] {count}));
        }
    }
}
```

Save as `ChoiceMessageDemo.java` with UTF-8. Run on JDK 17+:

```bash
javac -encoding UTF-8 ChoiceMessageDemo.java
java ChoiceMessageDemo
```

Stdout:

```text
Không có tệp nào.
Có một tệp.
Có 2 tệp.
Có 5 tệp.
```

Explanation:

- `0#` is the first branch, covering the value `0`.
- `1#` is for the value `1`.
- `1<` is for values greater than `1`.
- `{0,number,integer}` in the last branch is processed after `ChoiceFormat` selects the branch, so the output contains the actual input number.

This is an example for **non-negative integer counts**, where these sentences fit. Before using this in an application, clearly decide behavior for negative numbers, decimals, and large values. If a user enters `-2` and the system displays “Không có tệp nào”, that is a business rule bug to handle before rendering.

## 5. You Do Not Always Need to Embed Choice Directly in the Pattern

There are two common ways to combine them:

**Approach A — `choice` syntax inside the MessageFormat pattern**

```java
MessageFormat message = new MessageFormat(
        "{0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}",
        Locale.US);
```

**Approach B — create `ChoiceFormat` in Java and attach it to a `MessageFormat` argument**

```java
ChoiceFormat choice = new ChoiceFormat(limits, labels);
MessageFormat message = new MessageFormat("{0}", Locale.US);
message.setFormatByArgumentIndex(0, choice);
```

Both use `MessageFormat` to handle parameters. Approach A is convenient when patterns are localized in resource files; Approach B fits when branching thresholds are built from code-controlled policies. However, if you want translators to change sentence structure, keep the **complete template** in translation files instead of hardcoding all branches in Java.

### Runnable example with ChoiceFormat created from arrays

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ProgrammaticChoiceDemo {
    public static void main(String[] args) {
        double[] limits = {0, 1, 2};
        String[] labels = {
                "No files",
                "One file",
                "{0,number,integer} files"
        };

        ChoiceFormat choices = new ChoiceFormat(limits, labels);
        MessageFormat message =
                new MessageFormat("Result: {0}.", Locale.US);

        message.setFormatByArgumentIndex(0, choices);

        for (int count : new int[] {0, 1, 2, 5}) {
            System.out.println(
                    message.format(new Object[] {count})
            );
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ProgrammaticChoiceDemo.java
java ProgrammaticChoiceDemo
```

Stdout:

```text
Result: No files.
Result: One file.
Result: 2 files.
Result: 5 files.
```

Here `limits` has three thresholds 0, 1, 2. For inputs 2 or 5, `ChoiceFormat` selects the last element in `labels`. `MessageFormat` then sees that the selected string contains `{0,number,integer}`, so it inserts the actual count.

**Distinction:** when using arrays with `new ChoiceFormat(limits, labels)`, each array threshold is the **inclusive lower bound of that interval**. With text patterns, `1<` expresses an open bound, suitable for inputs greater than 1. Do not replace `1<` with `2#` if floating-point inputs like `1.5` can occur; they are only equivalent when the input contract restricts values to integers.

## 6. Combining Additional Parameters, Such as Recipient Name

Messages often contain both a quantity and a user name. You can use `{0}` for the count and `{1}` for the name:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class NamedChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{1}, {0,choice,0#you have no new messages.|1#you have one new message.|1<you have many new messages.}";
        MessageFormat message = new MessageFormat(pattern, Locale.US);

        System.out.println(message.format(new Object[] {0, "Mai"}));
        System.out.println(message.format(new Object[] {1, "Mai"}));
    }
}
```

This example prints the two cases for counts 0 and 1. The `1<` branch is valid for any count greater than 1; if you want to show the actual count in that branch, use the following complete pattern:

```text
{1}, {0,choice,0#you have no new messages.|1#you have one new message.|1<you have {0,number,integer} new messages.}
```

Dynamic data can appear in different positions depending on the language. This is especially important when a sentence has multiple parameters. Another translation might place the name `{1}` at the end of the sentence, or omit the greeting if contextually appropriate. **Do not split translations into fragments and concatenate them rigidly in Java.**

## 7. Separating Patterns by Locale via ResourceBundle

In a multilingual project, each locale should have the **entire message**, including the `ChoiceFormat` branches. Example file layout:

```text
src/main/resources/
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

Contents of `messages_en.properties`:

```properties
files.summary={0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}
```

Contents of `messages_vi.properties`:

```properties
files.summary={0,choice,0#Không có tệp nào.|1#Có một tệp.|1<Có {0,number,integer} tệp.}
```

The base bundle `messages.properties` should have the same semantic key and a complete fallback template:

```properties
files.summary={0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}
```

Java retrieves the pattern by key and formats it:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleChoiceDemo {
    static String render(Locale locale, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);

        String pattern = bundle.getString("files.summary");
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] {count});
    }

    public static void main(String[] args) {
        System.out.println(render(Locale.US, 1));
        System.out.println(render(Locale.US, 3));
        System.out.println(render(Locale.forLanguageTag("vi-VN"), 0));
        System.out.println(render(Locale.forLanguageTag("vi-VN"), 2));
    }
}
```

Place `BundleChoiceDemo.java` alongside the three resource files to run standalone:

```bash
javac -encoding UTF-8 BundleChoiceDemo.java
java -cp . BundleChoiceDemo
```

Stdout:

```text
One file.
3 files.
Không có tệp nào.
Có 2 tệp.
```

In a Maven or Gradle project, when `messages*.properties` live in `src/main/resources`, the build tool normally puts them on the classpath. Running `ResourceBundle.getBundle("messages", locale)` at the classpath root does not require opening files manually with `FileInputStream`.

**Two separate responsibilities:** `ResourceBundle` selects the **text template** by locale and key; `MessageFormat`/`ChoiceFormat` selects the **branch and inserts parameters**. If the resource set is missing a locale or key, ResourceBundle's fallback/`MissingResourceException` rules still apply; `ChoiceFormat` does not solve translation lookup.

## 8. Why Translate Whole Branches Instead of Individual Words?

A flawed approach:

```java
// Template dependent on English structure.
String result = count + " " + bundle.getString("file.label")
        + bundle.getString("files.suffix");
```

This assumes the order **number → noun → remainder** is identical in every language. Even if `file.label` is translated, the system still cannot change the full sentence or verb.

A better approach: a single `files.summary` key holds the entire pattern, and each branch contains a natural clause. English has “No files”, “One file”, “2 files”; Vietnamese can use “Không có tệp nào”, “Có một tệp”, “Có 2 tệp”. Details like subject placement, pronouns, punctuation, and noun forms are handled inside the translation.

Translators need to know:

- `{0}` is the file count and must be a non-negative integer.
- `0#`, `1#`, `1<` are **branch-control syntax** and must not be altered arbitrarily.
- `{0,number,integer}` is a Java placeholder, not sentence text to translate.
- Text segments following `#` or `<` can be translated so grammar is complete.
- If a language requires number groups other than 0/1/many, they must notify the i18n designer rather than forcing an English template.

**Translation context** is needed for the key, such as display location, quantity unit, input data type, punctuation requirements, and test values. A syntactically valid pattern can still be grammatically wrong.

## 9. Grammatical Limitations of ChoiceFormat

`ChoiceFormat` is primarily based on **ascending numeric intervals**. That suffices for messages with branches:

- No results (`count == 0`).
- Exactly one result (`count == 1`).
- More than one result (`count > 1`).

However, plural rules of languages do not always partition into contiguous intervals.

For instance, some languages use different noun forms depending on the last digit or last two digits of the count. Two distant numbers may then belong to the same grammatical category while adjacent numbers belong to different categories. Pure threshold-based `ChoiceFormat` cannot accurately express such modulo-based rules. Some languages also require multiple plural categories such as `zero`, `one`, `two`, `few`, `many`, `other`; rules cannot be inferred from English alone.

**Do not conclude that `0#...|1#...|1<...` is “the pluralization method for every locale”.** It is a **specific threshold-based business rule**, verified for non-negative integer counts and the languages actually supported.

When a project involves multiple languages with complex plurals/gender:

1. Identify the actual languages and plural rules.
2. Consult CLDR rules; for example, numbers 0/1/2/5/11/21/101 may need different branches depending on the language.
3. Consider an i18n library supporting plural rules such as ICU4J or a proven framework mechanism.
4. Still keep **entire clauses** inside each branch and test with people fluent in that language.

This is not a reason to discard ChoiceFormat: the API is very useful for threshold-based selections such as result counts, score bands, alert levels, or simple number groups. Simply avoid using it beyond the grammatical scope it can express.

## 10. Boundary Values, Floating-Point Numbers, and Precision

### 10.1. Negative values

A `ChoiceFormat` starting with `0#No files` can still select the first branch if the input is less than 0. If a count must be non-negative, validate it:

```java
if (count < 0) {
    throw new IllegalArgumentException("count must be non-negative");
}
```

This is an **illustrative code snippet** that must be placed inside a method with a `count` variable. Do not habitually call `Math.max(0, count)` because that hides invalid business data.

### 10.2. Non-integer numbers

`1<` applies to every number greater than 1, including `1.5`, not just `2, 3, 4`. If the message talks about “files”, “people”, “products” and the input must be a count, use `int`/`long` and validate the allowed range.

### 10.3. Very large numbers

`ChoiceFormat` processes thresholds as `double`; do not rely on threshold selection when integer counts exceed the exact representable range of `double` (around `2^53`). If business logic requires large integers, design classification using more precise data types and conditions at the logic layer, then choose the corresponding sentence template.

### 10.4. NaN and infinity

Branch selection results for `NaN` or infinity should not be treated as a way to validate input data. For count inputs, reject `NaN` and non-finite values if the data type can hold them. Use integer types when the counting problem is integer-based.

### 10.5. Thresholds and equal values

A choice pattern must have limits ordered in ascending order. Reordering or duplicating thresholds leads to unintended patterns or syntax errors. For floating-point data, distinguish `1#` (includes 1) from `1<` (greater than 1); with thresholds 0, 1, 2 in the array constructor, each threshold applies from that limit upward.

## 11. Quotes, Delimiters, and Nested Patterns

`MessageFormat` uses a single quote `'` to quote literals, and `''` to represent a single quote. `ChoiceFormat` also uses `|`, `#`, `<` to separate branches and thresholds.

Therefore, when placing ChoiceFormat inside MessageFormat:

- The pattern has **two syntax layers**: the branch selector and the message template.
- Do not insert `'` to “escape” in the manner of Java strings; quoting rules in runtime patterns differ from escaping in Java source code.
- If a translator needs to output `|` or braces, use the proper quoting mechanism and test the output after both parser layers process it.
- Avoid concatenating user data into the **pattern**; pass that data as an **argument**. Users should not control parser rules.
- When patterns live in `.properties`, also check `.properties` syntax and encoding. A `#` in the **middle of a value** is not a line-start comment, but `\\` and escape characters still have meaning under properties rules.

An example without ChoiceFormat that highlights quoting:

```java
MessageFormat formatter =
        new MessageFormat("You''re invited, {0}!", Locale.US);
System.out.println(formatter.format(new Object[] {"Mai"}));
```

Output:

```text
You're invited, Mai!
```

If you write `You're invited, {0}!` with a single quote in the pattern, `MessageFormat` can treat everything after the quote as a literal and fail to substitute `{0}` as intended.

## 12. Thread Safety and Performance

`MessageFormat` and `ChoiceFormat` are stateful formatter objects with methods that modify patterns/formats. A shared mutable instance across multiple requests should not be assumed safe for all concurrent operations.

For example, in an API service, a simple option is creating a formatter from pattern and locale per render operation; when optimizing performance, consider caching **immutable patterns** or managing formatter copies in a controlled way. If formats are reconfigured via `applyPattern`, `setFormat`, or `setFormatByArgumentIndex`, avoid sharing mutable state across threads.

Do not call `Locale.setDefault` to switch language per request: that is shared JVM state. Pass the explicit locale into `new MessageFormat(pattern, locale)` and use the selected locale when retrieving the ResourceBundle.

## 13. Testing ChoiceFormat + MessageFormat

Minimal test cases for the `0#...|1#...|1<...` pattern:

| Input | Expected | Objective |
| ---: | --- | --- |
| 0 | “No” sentence | Correct first branch |
| 1 | “One” sentence | Correct second branch |
| 2 | “Many” sentence with number 2 | Correct open bound and number insertion |
| 5 | “Many” sentence with number 5 | Not hardcoded to number 2 |
| -1 | Rejected by business validation | Avoid accidentally selecting first branch |
| 1.5 | Handled by clear policy | Recognize `1<` does not apply only to integers |

Additional checks to run:

1. **Locale switching:** render Vietnamese and English from ResourceBundle with the same `count`, verifying each sentence is complete with proper punctuation.
2. **Nested parameters:** the `1<` branch contains `{0,number,integer}` and displays the value accurately, especially with locale-specific thousands separators.
3. **Missing keys:** if `files.summary` is absent from the bundle/parent, verify `MissingResourceException` or the product's chosen fallback.
4. **Special characters:** apostrophes, `|`, `{`, `}`, newlines, Unicode strings from files.
5. **Grammar:** verify with people fluent in the target language, rather than only comparing machine-generated strings.
6. **Dynamic data:** user names containing quotes or HTML characters; `MessageFormat` does not HTML-escape automatically, so the web layer must escape according to the output context.
7. **Multithreaded immutability:** if formatters are cached or shared, verify the instance management strategy; never update a pattern on an instance being used by another thread.

In Java tests, keep patterns small and easy to understand, checking every threshold. Do not test only `count = 2`, because `0`, `1`, and invalid values are what reveal boundary bugs.

## 14. Common Misconceptions

1. **“ChoiceFormat automatically translates plurals correctly for every language.”** False; it only selects by numeric value ranges. Complex plural rules usually require CLDR/ICU or verified custom logic.
2. **“Just concatenate number + translated noun.”** False; changes can affect the entire clause and punctuation.
3. **“If ChoiceFormat directly selects a branch containing `{0}`, the number is substituted automatically.”** Not with standalone `ChoiceFormat.format`. Nested placeholder interpretation occurs when ChoiceFormat is used inside `MessageFormat`.
4. **“The `1<` branch means integers from 2.”** With floating-point numbers, `1.1` is also greater than 1. It is equivalent to “from 2” only when inputs are already integers.
5. **“Thresholds do not need to be ascending.”** ChoiceFormat relies on ordered limits; out-of-order patterns may be rejected or behave unexpectedly.
6. **“Negative inputs will automatically error.”** A value below the first limit can select the first branch; business validation must handle it.
7. **“Putting patterns in ResourceBundle is enough.”** You also need to verify keys, fallback, syntax, quotes, plurals, and grammar for each locale.
8. **“MessageFormat will HTML-escape data.”** No; it is a formatter, not a safe encoding mechanism for HTML or SQL.
9. **“Every language must use the same word order.”** No; each translation is allowed to reorganize clauses and placeholder positions.
10. **“You can share a mutable formatter and change its pattern per request.”** Not safe under concurrent use by multiple threads; state must be managed properly.

## 15. When to Choose ChoiceFormat and When to Choose Another Solution?

`ChoiceFormat` fits when you have **a few conditions by numeric thresholds**: such as 0 results, 1 result, many results; rating tiers by score; or simple message branches that the supported languages can express accurately.

For complex language-specific pluralization, consult the rules of the specific locale and consider an i18n tool supporting plural categorization and grammatical variants. Whether using ChoiceFormat, ICU4J, or another mechanism, the stable principles are:

- **Keep entire sentences in translation resources.**
- **Give translators context and freedom to reorder parameters.**
- **Separate business values from formatting-control patterns.**
- **Test thresholds, boundary values, and sentence naturalness.**
- **Select locale and fallback explicitly at the application layer.**

## 16. Practice Exercises

1. Run `ChoiceMessageDemo` with `count` equal to 0, 1, 2, and 5. Explain why `1<` selects the last branch when `count=2`.
2. Replace `1<` with `2#`, run with `count=1.5` of type `double`, observe the difference, and identify the condition under which the two patterns are considered equivalent.
3. Take `ProgrammaticChoiceDemo` and change the limits to `{0,1,2,10}`, adding a branch for 10 and above. Verify the ascending order of limits.
4. Move the pattern to the `files.summary` key in `messages_en.properties` and `messages_vi.properties`, confirming the Java code calls only one key for both locales.
5. Translate a message with recipient name and count so one language places the name at the start and another places it at the end; keep the Java argument list unchanged.
6. Check negative inputs and `NaN` at the business boundary before formatting. Explain why a “none” output must not be used to mask data errors.
7. Pick a language with complex plural categories in CLDR. Analyze why `0#|1#|1<` is insufficient and propose how to manage translation templates with a tool that supports plural rules.

## Official Documentation

- [Oracle JDK 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
