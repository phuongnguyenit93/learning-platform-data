# Inclusive Bounds, Exclusive Bounds, and Choice Branches in Java MessageFormat

## 1. The Problem: A Number May Require Different Phrasing

Messages containing quantities usually cannot concatenate a single fixed string for all values:

- `0` files: “No files”.
- `1` file: “One file”.
- `2` files: “2 files”.

In Java, `java.text.ChoiceFormat` defines **text branches by numeric value ranges**. `java.text.MessageFormat` integrates that mechanism via the syntax:

```text
{argumentIndex,choice,limit#text|limit<text|...}
```

A basic pattern:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

When argument `0` is `0`, `no files` is selected; when it equals `1`, `one file` is selected; when it is greater than `1`, the third branch is selected and the numeric value is formatted inside `{0,number,integer}`.

The core of this lesson is understanding **inclusive bounds (`#`), exclusive bounds (`<`), branch ordering**, how Java decides the branch right at the boundary, and how to combine `ChoiceFormat` with `MessageFormat`.

Scope note: `choice` is a selection based on **numeric thresholds**. It can express a few simple quantity cases, but it **does not automatically replace full natural-language plural rules**.

## 2. Syntax of a Choice Pattern

Each choice has three parts:

```text
limit comparator format
```

Where:

| Component | Meaning | Example |
|---|---|---|
| `limit` | Numeric threshold at which the branch starts applying | `0`, `1`, `2.5` |
| `comparator` | Relation to the threshold: `#` or `<` | `1#`, `1<` |
| `format` | String output when the branch is selected | `one file`, `many files` |
| `|` | Separator between choices | `0#zero|1#one` |

Example:

```text
0#none|1#one|1<many
```

There are no independent `if/else` statements here. Java converts each choice into an **effective threshold**, and then finds the branch corresponding to the numeric value.

### `#` — inclusive bound

`1#one` means the `one` branch **starts applying from the value 1, including 1 itself**. Until the threshold of a subsequent branch is reached, values remain in this branch.

Specifically, in the string `0#none|1#one|1<many`:

- `0` selects `none`.
- `1` selects `one`.
- `1.5` selects `many`.

### `<` — exclusive bound

`1<many` means the `many` branch only starts when the value is **strictly greater than 1**. At exactly `1`, this branch is not yet active; at a value greater than `1`, it becomes active.

Placing the two thresholds side by side:

```text
1#one|1<many
```

This is especially useful for separating **equal to 1** and **greater than 1** without having to write endless integer thresholds `2`, `3`, `4`.

### `|` separates branches

`|` is the delimiter in a choice pattern. The pattern:

```text
0#zero|1#one|1<more
```

has exactly **three choices**. When part of the content requires characters with special meaning in pattern syntax, you must handle the quoting/escaping rules of `ChoiceFormat` and `MessageFormat`; you cannot simply insert arbitrary text containing `|` or quotes and expect the parser to understand it properly. Keep patterns simple, and test thoroughly when they must contain syntax characters.

## 3. Value Range Model: Understanding the Whole Range, Not Just the Boundaries

With the pattern:

```text
0#zero|1#one|1<more
```

we can view the results as follows, in the domain of ordinary numbers:

| Input Value `n` | Selected Branch | Explanation |
|---:|---|---|
| `-2` | `zero` | Below the first threshold: Java still selects the first branch |
| `0` | `zero` | `0#` includes 0 |
| `0.5` | `zero` | Has not reached the `1#` threshold yet |
| `1` | `one` | `1#` includes 1; `1<` does not apply yet |
| `1.0001` | `more` | Already greater than 1 |
| `2` | `more` | Still belongs to the last branch |
| `10` | `more` | No next branch, so the last branch is used |

A practical way to express this is:

- First branch: all `n < 1`, including values below 0.
- Second branch: only `n = 1` in the `double` model with two consecutive limits `1#` and `1<`.
- Third branch: all `n > 1`.

**Warning about the first branch:** `ChoiceFormat` does not automatically report “no matching choice” when a number is smaller than all limits. It uses the **first branch**. Therefore, if negative counts are invalid data, validate beforehand; do not assume the pattern above prevents displaying `-2` files as `zero`.

## 4. Actual Branch Selection Mechanism

`ChoiceFormat` stores limits normalized as `double` numeric thresholds. Conceptually, Java selects the branch with the **largest effective threshold that is not greater than the value being formatted**; if the value does not exceed the first threshold, the first branch is still used.

With the operators:

- `#`: the effective threshold is the written number itself.
- `<`: the effective threshold is shifted to the next representable `double` value above the written number, ensuring the **greater than** comparison is exclusive.

That is why `1#one` and `1<many` can both write the threshold `1` yet remain two distinct effective limits. In Java `double`:

```text
1#one  -> effective limit 1.0
1<many -> effective limit 1.0000000000000002
```

The number `1.0000000000000002` is `Math.nextUp(1.0)`, the smallest `double` greater than `1.0`. This is **not** a rule of “add 0.0000000000000002” for every threshold; the spacing between floating-point numbers depends on the magnitude of the threshold.

Therefore, when checking exact boundaries of `double` data, understand `<` as an exact exclusive bound in floating-point representation, not as “threshold plus one” in counting units.

## 5. Runnable Example: Verifying Values Near Boundaries

Create the file `ChoiceBoundaryDemo.java`:

```java
import java.text.ChoiceFormat;
import java.util.Arrays;

public class ChoiceBoundaryDemo {
    public static void main(String[] args) {
        ChoiceFormat choices =
                new ChoiceFormat("0#zero|1#one|1<more");

        double[] values = {-2.0, 0.0, 0.5, 1.0, 1.5, 2.0};

        for (double value : values) {
            System.out.println(value + " => " + choices.format(value));
        }

        System.out.println("limits=" +
                Arrays.toString(choices.getLimits()));

        double justAboveOne = Math.nextUp(1.0);
        System.out.println("nextUp(1.0) => " +
                choices.format(justAboveOne));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ChoiceBoundaryDemo.java
java ChoiceBoundaryDemo
```

Verified output on the JDK:

```text
-2.0 => zero
0.0 => zero
0.5 => zero
1.0 => one
1.5 => more
2.0 => more
limits=[0.0, 1.0, 1.0000000000000002]
nextUp(1.0) => more
```

The key insight lies in the last two lines: `getLimits()` shows that Java stores the `1<` limit as the next `double` after 1. `Math.nextUp(1.0)` enters the `more` branch, while `1.0` itself stays in the `one` branch.

This example uses `double` because `ChoiceFormat` extends `NumberFormat` and defines intervals by numeric thresholds. In object-counting business logic, you typically use non-negative integers; thus you should validate before passing values to the formatter.

## 6. Choice Ordering Must Be Strictly Ascending

Branches in a choice pattern must be declared in **ascending order of effective limits**. Valid example:

```text
0#none|1#one|1<more
```

An invalid pattern:

```text
0#none|2#two|1#one
```

The thresholds `0` → `2` → `1` are not ascending. When constructing `ChoiceFormat` or parsing a `MessageFormat` containing the corresponding choice pattern, Java throws `IllegalArgumentException`.

Standalone verification snippet, saved as `InvalidChoiceOrder.java`:

```java
import java.text.ChoiceFormat;

public class InvalidChoiceOrder {
    public static void main(String[] args) {
        try {
            new ChoiceFormat("0#none|2#two|1#one");
            System.out.println("Unexpected success");
        } catch (IllegalArgumentException exception) {
            System.out.println("Invalid choice order");
        }
    }
}
```

Run `javac InvalidChoiceOrder.java` and `java InvalidChoiceOrder`:

```text
Invalid choice order
```

Even when the written thresholds look identical, consider the **operator**:

- `1#one|1<more` has increasing effective thresholds (`1.0` then `nextUp(1.0)`), so it is valid.
- `1<more|1#one` reverses the order of effective thresholds, so it is invalid.

Do not order choices by sentence length, alphabetical order, or “zero, many, one”; order them by their **defined mathematical thresholds**.

## 7. Pitfall: `2#many` Does Not Mean `>1`

Two patterns look similar but have different logic:

```text
0#zero|1#one|2#many
0#zero|1#one|1<many
```

For **non-negative integers**, both usually produce the same results at 0, 1, 2, 3. But for floating-point numbers:

| Value | `...|2#many` | `...|1<many` |
|---:|---|---|
| `1.0` | `one` | `one` |
| `1.1` | `one` | `many` |
| `1.5` | `one` | `many` |
| `2.0` | `many` | `many` |

If the true requirement is “in the many branch when **n > 1**”, you must use `1<`. If business logic only accepts integer counts, `2#` can express the same desired boundary, but it turns the assumption “quantity is an integer” into an important condition that must be validated.

Similarly:

```text
0#non-positive|0<positive
```

will select `non-positive` for every number `n <= 0` and `positive` for `n > 0`. In this usage, the first branch also covers negative values smaller than the first threshold.

## 8. Choice Branches Inside MessageFormat

`ChoiceFormat` formats a `Number` value into a string by itself. `MessageFormat` combines multiple parameters in one message, allowing `choice` to be written directly inside a placeholder:

```text
Found {0,choice,0#no files|1#one file|1<{0,number,integer} files}.
```

Here:

- The first `0` is the **argument index**, not the numeric value 0.
- `choice` requests `ChoiceFormat` threshold logic.
- `0#no files`, `1#one file`, `1<...` are the three branches.
- In the third branch, `{0,number,integer}` is a nested sub-placeholder to reformat the **same argument 0** with integer display style.

### Standalone Java 17+ program

Save as `MessageChoiceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "Found {0,choice,0#no files|1#one file|" +
                "1<{0,number,integer} files}.";

        MessageFormat formatter = new MessageFormat(pattern, Locale.US);

        for (int count : new int[] {0, 1, 2, 12}) {
            System.out.println(formatter.format(new Object[] {count}));
        }
    }
}
```

Compile and run:

```bash
javac MessageChoiceDemo.java
java MessageChoiceDemo
```

Output:

```text
Found no files.
Found one file.
Found 2 files.
Found 12 files.
```

With `count = 2`, `MessageFormat` selects the `1<` branch, then sees that the branch string contains `{0,number,integer}` and formats it further using `Locale.US`.

**Distinguish the two processing stages:**

1. **Branch selection:** based on the input number and the `#` / `<` limits.
2. **Message generation:** uses the selected branch's string; if it contains nested placeholders, `MessageFormat` processes them according to its rules.

Do not place `{0,number,integer}` in every branch if you only want to display “one” for the 1 case. Nested placeholders are useful when the same branch needs to embed the actual number into the sentence.

## 9. Why Can MessageFormat Process Nested Choice Patterns?

Per Java's `MessageFormat` behavior, if a `ChoiceFormat` branch is selected and **the resulting string contains `{`**, the system can re-parse that string as a `MessageFormat` pattern, using the same argument array to substitute nested placeholders.

This explains why the fragment:

```text
1<{0,number,integer} files
```

can display `2 files` instead of literally returning `{0,number,integer} files`.

However, pattern nesting brings two things to be careful about:

- If the displayed message needs literal braces, single quotes, or the syntax character `|`, you must obey the quoting rules of both `MessageFormat` and `ChoiceFormat`; escaping at one layer may not suffice at the next layer. Test actual strings containing special characters.
- Do not pass untrusted user text into a **pattern** to be compiled as `MessageFormat` syntax. Pass user data in **arguments**; patterns should reside in controlled resources/configuration.

In multilingual applications, pattern translations should preserve the exact argument indices. When branches contain nested placeholders, test all cases per locale to catch mismatched braces and quotes.

## 10. Branch Selection Uses the Raw Value, Not the Rounded Display Number

A common cause of display bugs: `ChoiceFormat` compares the **actual numeric value**, not the string rounded by `{0,number,integer}`.

Standalone example program `ChoiceRoundingDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceRoundingDemo {
    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(
                "{0,choice,0#zero|1#one|1<{0,number,integer} items}",
                Locale.US);

        System.out.println(formatter.format(new Object[] {1.0}));
        System.out.println(formatter.format(new Object[] {1.4}));
        System.out.println(formatter.format(new Object[] {2.0}));
    }
}
```

Run:

```bash
javac ChoiceRoundingDemo.java
java ChoiceRoundingDemo
```

Verified output:

```text
one
1 items
2 items
```

At `1.4`, the **`1<`** branch is correctly selected because 1.4 is greater than 1, but `{0,number,integer}` rounds the displayed value to **1**. The result `1 items` sounds contradictory. That is not a bug in `ChoiceFormat`; it is the consequence of business logic allowing floating-point numbers while the wording template assumes an integer count.

If the number is an **object count**, validate that it is a non-negative integer before formatting; if the number is a continuous measurement, choose patterns appropriate for decimals and real semantics.

## 11. Zero, Negative Numbers, and Unexpected Domains

The pattern `0#none|1#one|1<many` only works reliably when the input domain is constrained. For negative numbers, `ChoiceFormat` still selects the first branch (`none`), because it has no branch with a limit lower than `0`. In applications managing counts, the proper handling is **not to silently normalize negative numbers** by turning them into “none”.

A helper method validating counts before formatting can be written as follows (code snippet placed in a class that imports `MessageFormat`):

```java
static String filesMessage(MessageFormat formatter, int count) {
    if (count < 0) {
        throw new IllegalArgumentException("count must be >= 0");
    }
    return formatter.format(new Object[] {count});
}
```

Do not use `double` values with non-finite states like `NaN` or infinities from unvalidated inputs as counts. If a number comes from JSON, a database, or a calculation, validate its data type and valid range before selecting a branch.

If a separate branch for negative numbers is needed to **display an error or status**, you can design thresholds starting with negative numbers or `-∞`, while ensuring continuity, proper order, and meaningfulness for all values. For normal business logic, validating and reporting clear errors is easier to maintain.

## 12. ChoiceFormat Does Not Automatically Understand All Plural Rules

In the parent context of “Plurals and grammar”, `choice` is often used to distinguish `0`, `1`, and `n > 1`. However, **plural rules are not the same across all languages**.

Some languages use groups depending on the last digit, multiples, fractional parts, or grammatical morphology. `ChoiceFormat` selects by **contiguous intervals of a numeric value** and does not automatically apply CLDR plural categories. Therefore, a simple English pattern cannot infer the full rules of Arabic, Russian, Polish, and many other languages.

What you should do:

1. Use `ChoiceFormat` when the problem genuinely involves **partitioning clear numeric ranges** or a few simple quantity cases defined by the product.
2. Do not copy the same `0#...|1#...|1<...` pattern to every locale without reviewing language rules.
3. For large i18n products requiring locale-specific plural rules, ordinals, gender, case, or complex grammatical forms, consider a library with real **plural rules** support (such as ICU4J) and manage translations per language.
4. Regardless of the library used, still test **0, 1, 2**, key thresholds per locale, and decimal numbers if the product accepts them.

Choice is a **value-based** branching mechanism, whereas plural is a **language** rule; they overlap, but they are not identical.

## 13. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Writing `1#many` and expecting >1 | `#` includes 1 itself | Use `1<many` if strictly >1 is desired |
| Writing `2#many` while allowing decimals | `1.5` stays in the `one` branch | Use `1<` or validate integers |
| Ordering `0, 2, 1` | Limits must be ascending | Sort by ascending thresholds |
| Having only `0#zero|1#one` | All numbers >1 stay in the last branch `one` | Add a `1<many` branch |
| Assuming values below the first limit yield no result | `ChoiceFormat` uses the first branch | Validate the numeric domain or pick limits covering the whole domain |
| Assuming `<` means “equal to or greater than” | `<` is an exclusive bound | Use `#` when the limit value must be included |
| Using `Math.nextUp(1)` and comparing `double` output | Literal `1` may select the `float` overload | Write `Math.nextUp(1.0)` for a `double` result |
| Formatting `1.4` as an integer and expecting selection by “1” | Choice selects by raw number; formatting happens afterward | Validate the domain or avoid contradictory rounding |
| Inserting `|`, `'`, and `{` arbitrarily into patterns | Characters have syntactic meaning | Quote each layer properly; write tests with real translations |
| Assuming `choice` is CLDR plural | It only selects by thresholds | Use language-specific plural rules when needed |

## 14. Boundary Test Case Suite

For the pattern `0#zero|1#one|1<more`, a minimal test suite:

| Test Input | Expected Output | Purpose |
|---:|---|---|
| `0.0` | `zero` | First inclusive boundary |
| `0.5` | `zero` | Value between two limits |
| `1.0` | `one` | Exact hit on `1#` boundary |
| `Math.nextUp(1.0)` | `more` | First `double` value greater than 1 |
| `2.0` | `more` | Past exclusive boundary |
| `-1.0` | `zero` | Understand behavior below the first limit |
| `1.4` in MessageFormat with integer format | `1 items` | Detect discrepancy between branch selection and display |

For patterns used in translations, test both **the displayed string** and **the semantic correctness of the choice**, not just that the code throws no exceptions. If `count` is restricted to non-negative integers, also test that validation rejects `-1` before it reaches the formatter.

## 15. Knowledge Self-Check

**Question 1.** Does `1#one` include the number 1?  
**Answer:** Yes. `#` is an inclusive bound.

**Question 2.** Does `1<more` include 1?  
**Answer:** No. It applies only when strictly greater than 1.

**Question 3.** Given `0#zero|1#one|1<more`, which branch does input 0.75 select?  
**Answer:** `zero`; the `1#` threshold has not been reached.

**Question 4.** With the same pattern, which branch does input 1.0001 select?  
**Answer:** `more` because it is greater than 1.

**Question 5.** Does `0#zero|1#one|2#many` properly distinguish 1.5 and 2?  
**Answer:** 1.5 still selects `one`, while 2 selects `many`. If all real numbers greater than 1 must enter `many`, use `1<many`.

**Question 6.** Why is `0#zero|2#two|1#one` invalid?  
**Answer:** The limits are not ascending; Java throws `IllegalArgumentException`.

**Question 7.** Why can MessageFormat display `1 items` for the value 1.4?  
**Answer:** `ChoiceFormat` selects the greater-than-1 branch based on the raw number; the `number,integer` placeholder rounds the displayed representation afterward.

**Question 8.** Can a single choice pattern replace all plural rules of every language?  
**Answer:** No. ChoiceFormat partitions numeric intervals; it does not execute full locale-specific plural rules.

**Key Takeaway:** In `ChoiceFormat`, **`#` means “from this threshold, inclusive”**, while **`<` means “greater than this threshold, exclusive”**. Branches must be ordered by ascending effective limits. When embedded in `MessageFormat`, branch selection and number formatting are two distinct stages; both must be tested.

**Official documentation:** [Java SE 17 — ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html) · [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [Java SE 17 — Math.nextUp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#nextUp(double)).
