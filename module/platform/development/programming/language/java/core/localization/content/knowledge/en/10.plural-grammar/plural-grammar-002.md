# ChoiceFormat and Message Selection by Numeric Ranges

## 1. Why Can a Number Change a Message Sentence?

When a program displays a file count, an English message should not always concatenate `count + " files"`:

- `0` → “no files”.
- `1` → “one file”.
- `2` → “2 files”.

Another problem unrelated to plurals is order tier classification: under 10 points displays “basic”, from 10 to under 20 is “silver”, and 20 and above is “gold”. Both are **selecting text based on a numeric value**.

Java provides `java.text.ChoiceFormat` to map **numeric ranges** to **result strings**. This class is often used together with `java.text.MessageFormat` when a branch needs to contain parameters such as `{0}`. However, it only executes **developer-defined numeric range rules**; it does not automatically understand the plural grammar of individual languages.

This lesson focuses on defining ranges, declaring patterns, selecting messages, combining with `MessageFormat`, handling boundaries, formatting, and testing. All examples use Java 17+.

## 2. What Is ChoiceFormat and What Rules Does It Follow?

`ChoiceFormat` belongs to the `java.text` package and is a subclass of `NumberFormat`. When creating a `ChoiceFormat`, you provide an array of **ascending `double` thresholds** along with an array of **selected strings**.

Example:

| Starting Threshold | String | Numeric Values in Branch |
| --- | --- | --- |
| 0 | `"none"` | From 0 up to less than 1 |
| 1 | `"one"` | From 1 up to before the `double` immediately after 1 |
| The `double` immediately after 1 | `"many"` | Greater than 1 |

Given thresholds `limit[0] < limit[1] < …`, branch `j` is used when:

\[
\mathrm{limit}[j] \leq x < \mathrm{limit}[j+1]
\]

The last branch applies from the last threshold upward. If a value is smaller than the first threshold, Java still uses the **first branch**; if it is greater than all thresholds, Java uses the **last branch**. `Double.NaN` is also treated as lower than every threshold, meaning it selects the first branch.

Therefore, `ChoiceFormat` is not an input validation tool: if business logic only accepts **non-negative integer** file counts, validate that constraint **before formatting**. If you pass `-3` into a rule designed for `0, 1, many`, it can still output the “none” branch even though negative numbers are invalid data.

In particular, `ChoiceFormat` has no `getInstance(locale)` factory. It **does not contain a `Locale`-based grammar rule set** itself. Phrases like “none”, “one”, “many” are supplied by you, not translations automatically chosen by Java.

## 3. Creating ChoiceFormat from Threshold and String Arrays

The constructor accepts two corresponding arrays:

```java
ChoiceFormat format = new ChoiceFormat(
        new double[] {
                0,
                1,
                ChoiceFormat.nextDouble(1)
        },
        new String[] {
                "none",
                "one",
                "many"
        }
);
```

Elements at the **same index** form one choice. Both arrays must have the same number of elements; the limits must be ascending for branch selection to work properly. Do not pass an arbitrary unsorted threshold array: the result can be wrong. When thresholds are built dynamically, validate their order and count before creating the formatter.

### Why not use {0, 1, 2} for a “0 / 1 / greater than 1” sentence?

For **non-negative integer** counts, the array `{0, 1, 2}` is reasonable because the next valid value after 1 is 2. However, `ChoiceFormat` operates on **`double`**, not strictly on integers. If you use `{0, 1, 2}`, the value `1.5` still falls into the “one” branch. If the problem requires a **greater than 1** relation for floating-point numbers, use:

```java
ChoiceFormat.nextDouble(1)
```

This method returns the **smallest representable `double` greater than 1** (equivalent to `Math.nextUp(1.0)`). Thus, you can distinguish `x == 1` from `x > 1` without manually adding an imprecise epsilon.

`ChoiceFormat.previousDouble(d)` is the corresponding method to find the `double` immediately below `d`. Do not use `nextDouble`/`previousDouble` as currency rounding rules or for comparing data with decimal precision: they exist for binary floating-point representation boundaries.

Notable methods:

| API | Meaning |
| --- | --- |
| `new ChoiceFormat(double[], String[])` | Creates a formatter from thresholds and strings |
| `new ChoiceFormat(String)` | Creates a formatter using a pattern |
| `format(double)`, `format(long)` | Selects and returns a string based on the number |
| `setChoices(double[], String[])` | Replaces all thresholds and strings on the instance |
| `getLimits()`, `getFormats()` | Inspects the configured thresholds/outputs |
| `applyPattern(String)` | Replaces the configuration with a new pattern |
| `toPattern()` | Exports a pattern representing the configuration |
| `nextDouble(double)`, `previousDouble(double)` | Determines adjacent boundary `double` values |
| `parse(String, ParsePosition)` | Parses a choice string into its corresponding threshold; **does not recover the original numeric value** |

`format(long)` internally operates via `double`. For extremely large `long` integers beyond the exact integer representation range of `double`, precisely checking adjacent boundaries may be unreliable; if that is critical business data, compare integers/`BigDecimal` with dedicated logic.

## 4. Writing Patterns: #, <, and the | Symbol

A common declaration style is:

```java
ChoiceFormat files = new ChoiceFormat(
        "0#no files|1#one file|1<many files"
);
```

General syntax:

```text
threshold#message|threshold#message|threshold<message
```

- `#`: **inclusive threshold**. `1#one file` starts applying at `1`.
- `<`: **exclusive threshold**. `1<many files` starts applying at the first `double` greater than `1`.
- `|`: separates branches.
- `≤` (single Unicode character U+2264) also denotes an inclusive threshold relation; it is **not** the two-character sequence `<=`.
- Thresholds are processed in ascending order. The right-hand side of each relation is the **choice string**.

Applying the pattern `0#no files|1#one file|1<many files` to values:

| Value | Selected String | Reason |
| ---: | --- | --- |
| 0 | `no files` | Branch starts at 0 |
| 0.5 | `no files` | Lies in the interval `[0, 1)` |
| 1 | `one file` | Threshold 1 includes 1 |
| 1.5 | `many files` | Greater than 1 |
| 2 | `many files` | Greater than 1 |
| -1 | `no files` | Smaller than all thresholds, so uses first branch |
| `Double.NaN` | `no files` | NaN is treated as below the first threshold |
| `Double.POSITIVE_INFINITY` | `many files` | Falls into the last branch |

This shows that the three-branch pattern **only makes business sense for non-negative integer counts**; it is not a rule guaranteeing grammatical correctness if the input contains fractional or negative numbers.

### Practical tier example

```java
ChoiceFormat tier = new ChoiceFormat(
        "0#basic|10#silver|20#gold"
);

System.out.println(tier.format(9));  // basic
System.out.println(tier.format(10)); // silver
System.out.println(tier.format(19)); // silver
System.out.println(tier.format(20)); // gold
```

Here the `#` relation expresses the thresholds `x >= 0`, `x >= 10`, `x >= 20`; each branch is selected up until the next threshold. Negative numbers will also become `basic`, so the application must decide whether to accept such input.

### Escaping special characters

In patterns, `|`, `#`, `<`, and single quotes have syntactic meaning. When you want to output them as part of a message, use `ChoiceFormat`'s **single quote** rule; two consecutive single quotes represent one literal single quote.

```java
ChoiceFormat quoted = new ChoiceFormat(
        "0#'|'|1#ready"
);
System.out.println(quoted.format(0)); // |
```

When a pattern is also passed through `MessageFormat`, there are **additional** escaping rules for braces and quotes; you must test patterns after each parsing layer, especially translations containing apostrophes. Do not arbitrarily concatenate user-supplied content into a pattern.

## 5. ChoiceFormat and MessageFormat Handle Different Parts

`ChoiceFormat` selects the **string of one branch**. It does not substitute `{0}` or `{1}` inside the branch string by itself.

Example:

```java
ChoiceFormat choice = new ChoiceFormat(
        "0#no files|1#one file|1<{0,number,integer} files"
);

System.out.println(choice.format(2));
// {0,number,integer} files
```

The line above returns a **template containing a parameter**. When combined with `MessageFormat`, Java can re-parse the branch result containing `{` as a message pattern and format the parameter in the current context.

A clear, maintainable way to combine them:

1. Create the outer sentence message using `MessageFormat`.
2. Create `ChoiceFormat` to select phrasing by number.
3. Attach the formatter to the corresponding **argument index** using `setFormatByArgumentIndex`.
4. Call `format(Object[])` with data, testing 0, 1, and many.

This approach allows the quantity to appear at the appropriate position in the whole sentence rather than concatenating fixed sentence fragments following English structure.

## 6. Standalone Java 17+ Example: Message by File Count

Create a UTF-8 file named **`ChoiceFormatDemo.java`**:

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceFormatDemo {
    public static void main(String[] args) {
        ChoiceFormat choices = new ChoiceFormat(
                "0#no files|1#one file|1<{0,number,integer} files"
        );

        MessageFormat message = new MessageFormat(
                "Folder contains {0}.", Locale.US
        );
        message.setFormatByArgumentIndex(0, choices);

        for (int count : new int[] {0, 1, 2, 5}) {
            if (count < 0) {
                throw new IllegalArgumentException("Negative file count");
            }
            System.out.println(count + " -> "
                    + message.format(new Object[] {count}));
        }

        System.out.println("ChoiceFormat only: "
                + choices.format(2));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ChoiceFormatDemo.java
java ChoiceFormatDemo
```

**Exact stdout:**

```text
0 -> Folder contains no files.
1 -> Folder contains one file.
2 -> Folder contains 2 files.
5 -> Folder contains 5 files.
ChoiceFormat only: {0,number,integer} files
```

Analysis:

- The message argument is `count` at index `0`.
- `0` selects `no files`; `1` selects `one file`; numbers greater than `1` select the template `{0,number,integer} files`.
- `MessageFormat` sees that the selected branch contains `{0,...}` and proceeds to process parameter `0`, producing `2 files` or `5 files`. The `number,integer` formatter formats according to `Locale.US` passed to `MessageFormat`.
- Calling `choices.format(2)` directly only returns the pattern string as shown; there is no `MessageFormat` parameter substitution pass.
- The loop receives non-negative integers, so the three branches accurately reflect the example's requirements. The negative check in the example illustrates an input contract; values coming from a request or database must be validated at the ingestion boundary.

This pattern illustrates a simple selection common in **English**. For large numbers, digit grouping depends on the `MessageFormat` locale and JDK internationalization data; do not assume every locale uses commas like `Locale.US`.

## 7. Second Example: Configuring with Arrays and nextDouble

This is another program, independent of the previous example. Create **`ChoiceBoundariesDemo.java`**:

```java
import java.text.ChoiceFormat;

public class ChoiceBoundariesDemo {
    public static void main(String[] args) {
        double[] limits = {
                0,
                1,
                ChoiceFormat.nextDouble(1)
        };
        String[] labels = {
                "none",
                "one",
                "many"
        };
        ChoiceFormat format = new ChoiceFormat(limits, labels);

        for (double value : new double[] {0, 0.5, 1, 1.5, 2}) {
            System.out.println(value + " -> " + format.format(value));
        }
        System.out.println("NaN -> " + format.format(Double.NaN));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ChoiceBoundariesDemo.java
java ChoiceBoundariesDemo
```

Output:

```text
0.0 -> none
0.5 -> none
1.0 -> one
1.5 -> many
2.0 -> many
NaN -> none
```

Because `ChoiceFormat.nextDouble(1)` is the starting threshold of the “many” branch, numbers greater than 1 are classified correctly in terms of **`double`** ranges. In particular, `0.5` is still “none”; file-counting problems must use non-negative integers.

The array-based constructor is suitable when thresholds/strings are built from validated data. The pattern constructor is concise when the threshold table consists of readable constants. Both share the same numeric-range selection model.

## 8. Using ChoiceFormat with Localized Messages

Suppose a UI supports Vietnamese and English. **Do not share a single English pattern string** for all languages and just swap a few words. Store entire messages in locale-specific resources, for example these keys:

```properties
# messages_en.properties
folder.summary=Folder contains {0}.
folder.count=0#no files|1#one file|1<{0,number,integer} files
```

```properties
# messages_vi.properties
folder.summary=Thư mục có {0}.
folder.count=0#không có tệp|1#một tệp|1<{0,number,integer} tệp
```

Then, in the presentation layer, use `ResourceBundle.getBundle("messages", locale)` to retrieve the translated messages, build a `ChoiceFormat` from `folder.count`, and attach it to a `MessageFormat` initialized with `folder.summary` and `locale`.

Example snippet (placed inside a method with a `locale` variable of type `Locale`, importing `java.util.ResourceBundle`, `java.text.MessageFormat`, `java.text.ChoiceFormat`):

```java
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

ChoiceFormat countChoice =
        new ChoiceFormat(bundle.getString("folder.count"));
MessageFormat sentence = new MessageFormat(
        bundle.getString("folder.summary"), locale);
sentence.setFormatByArgumentIndex(0, countChoice);

String result = sentence.format(new Object[] {5});
```

This snippet requires the properties files to be on the classpath and contain the corresponding keys. With `Locale.forLanguageTag("vi-VN")` and valid Vietnamese resources, `result` will mean “Thư mục có 5 tệp.”. With an English locale, it uses the entire English sentence.

This organization is helpful because a translation can change **phrasing order**, not just substitute nouns. However:

- `ChoiceFormat` does not translate on its own; translators must provide the pattern for each locale.
- Special syntax of `ChoiceFormat` and `MessageFormat` must be preserved, including `|`, `#`, `<`, `{0}`, and quotes.
- When there are many plural forms, prepositions, grammatical genders, or complex grammatical requirements, a three-branch string is **insufficient**.

**Important regarding international plurals:** English typically has singular and plural forms, but some languages have forms corresponding to `0, 1, 2, few, many, other` or rules based on final digits, fractional parts, and context. `ChoiceFormat` does not automatically fetch CLDR plural rules and does not guarantee correctness if `count == 1` is applied across all languages. When global pluralization is needed, consider ICU MessageFormat/CLDR plural rules or a localization system supporting those rules, combined with translators and testing. Do not assume `0/1/>1` is the rule for every locale.

## 9. Numeric Range Issues to Test

### 9.1. Inclusive and exclusive boundaries

Compare:

```java
new ChoiceFormat("0#low|10#high"); // 10 belongs to high
new ChoiceFormat("0#low|10<high"); // only greater than 10 belongs to high
```

The exact value at a threshold is an often-overlooked case. With `10<`, Java finds the smallest `double` greater than 10 as the actual threshold. Choosing `#` or `<` must come from the business rule (“10 and above” vs. “above 10”), not from two outputs looking similar on a few test values.

### 9.2. Values below the first threshold and special numbers

If the first threshold is 0, `-5` still selects the 0 branch; `NaN` also selects the first branch, while positive infinity selects the last branch. This only reflects the formatter's **fallback mechanism**, not proof that the input data is valid. Before formatting counts, validate non-negative integers; for measurement conditions, decide separately how to handle `NaN`/infinity.

### 9.3. Floating-point values and precision

`ChoiceFormat` uses `double`. When classifying monetary amounts at decimal precision (e.g., amounts with cents), do not construct thresholds by adding a decimal epsilon; consider comparing with `BigDecimal.compareTo` per business rules and then selecting the appropriate message. For very large `long` values, `format(long)` internally converts to `double`, so it may fail to distinguish two consecutive integers beyond `double`'s precision limit.

### 9.4. Variability of number formatting

If a branch contains `{0,number,integer}`, the final output is the result of `MessageFormat` and locale-dependent `NumberFormat`. If exact string assertions are needed in tests, pin the `Locale` in tests and account for locale data differences across JDK versions. Do not treat a formatted and reverse-parsed value as the source of truth for business calculations.

## 10. ChoiceFormat's Parse Does Not Recover the Original Number

`ChoiceFormat` inherits parsing capability, but the meaning of `parse` differs from standard number parsing. It attempts to match the **selected message string** and returns the corresponding **threshold**, not the `count` number originally formatted.

For example, if multiple values `2, 3, 10` all format to `"many"`, there is no way to determine the original number from `"many"` alone. In an example containing `{0,number,integer}`, `ChoiceFormat`'s parse is not a mechanism that reverses all nested `MessageFormat` logic.

`parse(String, ParsePosition)` operates on text content and updates the parse position; you must check the return value, `ParsePosition.getIndex()`, and `getErrorIndex()` when using it. Do not use parsed results from localized labels to recover order quantities or business state. **Store and pass raw numbers using numeric types**, and format only at the presentation layer.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Using `count + " files"` for all situations | Sentence is wrong when count is 0/1; not adaptable across languages | Choose complete messages by context |
| Assuming `ChoiceFormat` knows locale plural rules | The formatter has no CLDR plural rules | Supply appropriate rules or use ICU/plural framework |
| Writing `1#one|2#many` and believing 1.5 is many | 1.5 is still less than threshold 2 | Use `1<` or `ChoiceFormat.nextDouble(1)` if decimals are needed |
| Using `10<` while expecting 10 to enter the next branch | `<` excludes the threshold | Use `10#` for “from 10” |
| Testing only values far from thresholds | Fails to catch boundary bugs | Test immediately before, at, and immediately after thresholds |
| Calling `ChoiceFormat.format(2)` and expecting `{0}` to be replaced | ChoiceFormat only returns the branch string | Combine with `MessageFormat` when parameter interpolation is needed |
| Putting messages containing `|`, `#`, `<` into a pattern without escaping | Parser treats them as syntax | Use proper quoting and test real patterns |
| Treating negative numbers/NaN as valid counts | Formatter still picks a branch, but business logic is wrong | Validate input before formatting |
| Using `parse` output as the original number | A branch can represent infinitely many values | Keep raw numbers in the model; do not reverse-parse display text |
| Using one English plural template for all locales | Grammar rules differ across languages | Translate messages in context and use plural rules when needed |
| Sharing a mutable `MessageFormat` and swapping patterns per request | Formatting state can leak across threads | Create formatters per context or manage lifecycle/thread-safety explicitly |
| Assuming number formatting is financial calculation | Formatter only decides display text | Perform calculations using numeric types/business logic before display |

## 12. Testing and Practice

For a choice table with boundaries `0`, `1`, `10`, test at minimum the values immediately before and after each threshold, along with special values if inputs allow them. A small matrix:

| Case Group | Example Values | What to Verify |
| --- | --- | --- |
| Low boundary | `-1`, `0`, `0.5` | Below-threshold behavior; negative numbers are not wrongly accepted |
| Unit boundary | `1`, `ChoiceFormat.nextDouble(1)`, `2` | Distinguishing “equals 1” from “greater than 1” |
| Tier boundary | `9.99`, `10`, `10.01` | Inclusive/exclusive threshold policy |
| Special numbers | `NaN`, `-Infinity`, `+Infinity` | How the application validates and responds |
| Nested parameters | `0`, `1`, `2`, `5` | `MessageFormat` substitutes `{0}` correctly |
| Other locales | `en-US`, `vi-VN`, and product-supported locales | Appropriate text/number formatting; pattern syntax does not break |
| Translation variants | Messages with apostrophes, pipes, or braces | Escaping works and does not break layout |

If you want to turn this exercise into code, create another `ChoiceFormat` to classify points: `0–9` “basic”, `10–19` “silver”, from `20` “gold”; test `9`, `10`, `19`, and `20`. Then try replacing `10#` with `10<` to see why inclusive/exclusive bounds matter so much.

## 13. Key Takeaways

- `ChoiceFormat` selects **strings by `double` numeric ranges**, according to ascending thresholds. Each branch represents a half-open interval; values below the first threshold still select the first branch.
- Patterns use `#` for **threshold inclusive**, `<` for **greater than threshold**, and `|` to separate branches. `ChoiceFormat.nextDouble` helps with strict boundaries on `double`.
- `ChoiceFormat` does not substitute nested parameters itself; `MessageFormat` can process a branch string containing `{0,number,...}` after selection.
- It is a **threshold-based** selector, not a global plural rule engine. For complex plural grammar, use a localization tool that supports language-specific plural rules and test thoroughly.
- Validate numeric inputs before formatting, keep raw numbers in the data layer, and test values right around boundaries.

**Official documentation:**

- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
