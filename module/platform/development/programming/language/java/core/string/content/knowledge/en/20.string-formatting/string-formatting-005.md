# `%%` and `%n` in Java String Formatting

## Objectives

When using `String.format(...)`, `String.formatted(...)`, or `System.out.printf(...)`, you need to know how to print a literal percent sign and insert platform-appropriate newlines:

- `%%` represents **a single `%` sign in the output**.
- `%n` represents **an OS-specific line separator character or sequence**.
- Both are **special conversions of `java.util.Formatter`** and **do not consume an argument** in the formatting parameter list.

These two symbols are only interpreted when the string acts as a **format string**. They are not special syntax on every `String` object.

## 1. Why Do These Two Symbols Exist?

In the `Formatter`-based API family, a normal `%` begins a format specifier: `%s` inserts a string, `%d` inserts an integer, `%.2f` formats a floating-point number with two decimal digits. Because `%` already has control meaning, displaying it literally requires writing `%%`.

Similarly, `%n` instructs the formatter to append the line separator appropriate for the runtime environment, which is convenient for generating multi-line reports and printing to the console.

| Pattern in Format String | Meaning | Argument Required |
| --- | --- | --- |
| `%%` | Outputs a single `%` sign | No |
| `%n` | Outputs a platform-specific line separator | No |
| `%d` | Inserts an integer | Yes |
| `%s` | Inserts the string representation of a value | Yes |

For example: the template string `"Progress: %d%%%n"` is read as `%d` (numeric value), `%%` (percent sign), and `%n` (line separator). Three consecutive `%` signs before the letter `n` here are valid syntax: the first two belong to `%%`, and the third starts `%n`.

## 2. `%%` — Printing a Percent Sign

With `Formatter`, `%%` produces exactly one `%` sign:

```java
String result = String.format("Processed 100%%");
System.out.println(result);
```

Output:

```text
Processed 100%
```

To attach a dynamic percentage value, place `%%` after the number specifier:

```java
int progress = 75;
System.out.printf("Progress: %d%%%n", progress);
```

The output is the line `Progress: 75%` followed by a newline. `%d` consumes the `progress` argument, while `%%` consumes no argument. If you only want the resulting string without printing it to the screen, use `String.format("Progress: %d%%", progress)`.

**Distinguishing from ordinary strings:** `System.out.print("50%%")` prints both `%%` characters literally, because `print` does not parse a format string. Conversely, `System.out.printf("50%%")` prints `50%`.

In particular, a lone `%` sign in a format string usually causes a formatting error because `Formatter` expects the next conversion name. Writing `"100%"` remains completely valid when passed to `print`/`println` as plain text.

## 3. `%n` — Platform-Specific Line Separator

`%n` does not print the two characters `%` and `n`. Inside a format string, it generates a line separator matching the value provided by `System.lineSeparator()` in the runtime environment. Typically, Unix/Linux/macOS use LF (`\n`); Windows uses CRLF (`\r\n`).

```java
String report = String.format("First line%nSecond line");
System.out.print(report);
```

Displayed output:

```text
First line
Second line
```

Multiple `%n` tokens can be used consecutively when **intentionally** creating blank lines:

```java
System.out.printf("Item A%n%nItem B%n");
```

Output:

```text
Item A

Item B
```

**Comparison with `\n` and `println`:**

- `\n` is a *Java string literal* escape sequence: the Java compiler turns it into an LF newline character. It is understood even without `Formatter`.
- `%n` is a *format string* directive: it is only converted into a line separator when passed through `Formatter`, and is usually a good choice for platform-native text formatting.
- `println(...)` automatically adds a line separator after the printed value. If a value already ends with `%n` from `String.format` and you call `println`, there will be an unintended extra blank line.
- `System.out.print("%n")` prints `%n` verbatim. To output a newline with it, call `System.out.printf("%n")` or use `println()`.

Do not assume `%n` always produces a single character: on Windows the line separator typically consists of two characters `\r\n`. This matters if you compare strings byte-by-byte or test text across platforms.

## 4. Complete Runnable Java 17+ Example

Create a file `FormatTokensDemo.java`:

```java
public class FormatTokensDemo {
    public static void main(String[] args) {
        int completed = 7;
        int total = 10;
        int percentage = completed * 100 / total;

        // %d takes a number; %% prints %; %n ends the line.
        System.out.printf(
                "Completed: %d/%d (%d%%)%n",
                completed, total, percentage
        );

        // String.format builds the string; println adds the final newline.
        String report = String.format(
                "Discount: 15%%%nOrder recorded"
        );
        System.out.println(report);

        // print does not interpret %% or %n.
        System.out.print("regular print: 50%% and %n");
        System.out.println();
    }
}
```

Compile and run:

```bash
javac FormatTokensDemo.java
java FormatTokensDemo
```

Displayed output (lines look the same on every platform; line-ending bytes may differ):

```text
Completed: 7/10 (70%)
Discount: 15%
Order recorded
regular print: 50%% and %n
```

Explanation: the expression `completed * 100 / total` yields `70` via integer arithmetic; `%d` places that number into the string. The pair `%%` after `%d` produces the percent sign, and `%n` closes the line. In `report`, `15%%%n` corresponds to `15%` followed by a newline before the next sentence. `print` at the end simply outputs the exact characters of the passed string value.

When a format string is already stored in a variable, you can also call `template.formatted(args)` (Java 15+); `%%` and `%n` still carry the same meaning because this method uses `String.format`-style formatting.

## 5. Combination Rules and Common Mistakes

| Desired Output | Pattern with `printf`/`String.format` | Result |
| --- | --- | --- |
| Print `100%` | `"100%%"` | `100%` |
| Print `80%` from integer 80 | `"%d%%"` and argument `80` | `80%` |
| Print `80%` then end the line | `"%d%%%n"` and argument `80` | `80%` followed by newline |
| Print two lines | `"A%nB"` | `A` and `B` on two lines |
| Print literal `%n` via Formatter | `"%%n"` | `%n` |

Mistakes to avoid:

1. **Missing the second `%` sign:** `System.out.printf("Completed 100%")` has an invalid format string; you must use `"Completed 100%%"`. When only printing fixed text, `System.out.println("Completed 100%")` is also valid.
2. **Confusing with Java string escapes:** `\%` is not a valid escape sequence in a Java string literal. Do not use `"100\%"` to handle percent signs.
3. **Forgetting the formatting context:** `"A%nB"` passed directly to `print` still contains the characters `%n`. Only passing it through `printf`, `format`, or `formatted` interprets it.
4. **Inserting a newline twice:** `System.out.println(String.format("X%n"))` produces one newline from `%n` and another newline from `println`. Choose one or the other when you only want to end a single line.
5. **Attaching formatting options to `%n`:** `%n` does not accept flags, width, or precision. For `%%`, width and the left-alignment flag `-` can be specified (for example, `%5%` prints `%` in a 5-character wide field), though precision like number or string formatting is not used.
6. **Supplying an argument by mistake:** `%%` and `%n` do not consume any element from the argument list; only `%d`, `%s`, etc. consume corresponding arguments. For example, `String.format("%s: 100%%%n", "Download")` requires only one argument, `"Download"`.

## 6. Self-Check

**Question 1.** What does the following code display?

```java
System.out.printf("CPU: %d%%%n", 80);
```

Answer: prints `CPU: 80%` and ends the line. `%d` receives `80`; `%%` prints the percent sign; `%n` outputs a newline.

**Question 2.** Why do the two calls below produce different results?

```java
System.out.print("X%nY");
System.out.printf("X%nY");
```

Answer: `print` displays `X%nY` verbatim; `printf` interprets `%n` and displays `X` and `Y` on two lines. Because the `print` call does not add a newline, when run consecutively as above, the `X` from `printf` appears immediately after the `Y` printed by `print`.

## Key Takeaways

In a **format string**, use `%%` to produce a visible percent sign and `%n` to produce a platform-compatible line separator. They do not consume formatting arguments. In strings passed straight to `print`/`println`, both symbols remain unchanged because there is no format-parsing step.
