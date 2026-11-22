# `System.out.print()`, `println()` and `printf()` in Java

## 1. Three ways to output data to the console

In Java, `System.out` is a `java.io.PrintStream` object representing the **standard output** stream (commonly called stdout). The three most familiar method groups are:

- **`System.out.print(value)`**: prints the value without **automatically adding a newline character**.
- **`System.out.println(value)`**: prints the value and then **terminates the line**; `println()` with no arguments prints only a line terminator, often used to create a blank line.
- **`System.out.printf(format, args...)`**: prints a string **according to a format template**, using specifiers such as `%s`, `%d`, `%.2f`. `printf()` **does not automatically add a line terminator** if the format string does not request one.

Example placed inside a method:

```java
System.out.print("Xin ");
System.out.print("chao");
System.out.println(" Java");
System.out.println("Dong moi");
System.out.println();
System.out.println("Sau mot dong trong");
```

Result:

```text
Xin chao Java
Dong moi

Sau mot dong trong
```

The first two `print` calls continue writing on the **same line**. `println(" Java")` appends the content and terminates the line. `println()` with no arguments creates a **blank line** before the next content.

**Do not confuse `print()` with `println()`:** `print("A")` does not automatically move to a new line, whereas `println("A")` does. Similarly, `printf("A")` does not automatically add a newline.

## 2. `print()`: continue printing without automatically moving to a new line

`print` is useful for assembling the content of a single line from multiple smaller parts, such as a label and a value.

```java
int count = 4;
System.out.print("So luong: ");
System.out.print(count);
System.out.println(" san pham");
```

Stdout:

```text
So luong: 4 san pham
```

If you only call `print` without a newline character in the passed value, the next print call will continue on the current line. For example, `print("A\nB")` **can create a line break** because the string itself contains the `\n` character; not *automatically* adding a newline does not mean the printed value cannot contain a newline.

`print` has overloads for types such as `boolean`, `char`, `char[]`, `int`, `long`, `float`, `double`, `String`, and `Object`. For primitive values, Java converts them to an appropriate text representation. For many objects, printing uses their string representation (`String.valueOf`/`toString()`). Keep in mind that `toString()` on a custom object might not describe its fields the way you want.

Example:

```java
System.out.print(25);
System.out.print(" tuoi");
System.out.println();
```

The result is a single line `25 tuoi`.

## 3. `println()`: print and terminate the line

`println` is suited for messages, logging values line by line, and printing results after each step.

```java
System.out.println("Java");
System.out.println(17);
System.out.println(true);
```

Stdout:

```text
Java
17
true
```

`println()` with no arguments only terminates the current line. Unlike a space character, a line terminator affects how the terminal displays data.

### String concatenation with the `+` operator

When one operand is a `String`, the `+` operator can be used for string concatenation:

```java
int a = 2, b = 3;
System.out.println("Tong: " + (a + b)); // Tong: 5
System.out.println("Ket qua: " + a + b); // Ket qua: 23
System.out.println(a + b + " la tong"); // 5 la tong
```

**Why are they different?** In `"Ket qua: " + a + b`, the operations are evaluated from left to right: after concatenating the string with `a`, the `+ b` operation continues concatenating text. To perform arithmetic before concatenating, place the expression in parentheses `(a + b)`.

### Printing arrays and objects

```java
int[] numbers = {4, 6};
System.out.println(java.util.Arrays.toString(numbers)); // [4, 6]
```

For arrays, **do not expect** `System.out.println(numbers)` to automatically print every element. Arrays do not override `toString()` as a list of elements; the result usually has a form containing type information and an identity hash code, not `[4, 6]`. Use `Arrays.toString` for one-dimensional arrays or `Arrays.deepToString` for nested arrays as appropriate.

## 4. `printf()`: template-based printing instead of manual string concatenation

`printf(format, args...)` accepts a template string containing specifiers starting with `%` and the corresponding arguments. For example, `System.out.printf("Ten: %s; Tuoi: %d%n", "An", 18);` prints `Ten: An; Tuoi: 18` and then moves to a new line. Unlike `println()`, `printf()` **does not automatically add** a line terminator.

| Specifier | Meaning in basic examples |
| --- | --- |
| `%s` / `%d` | Text / decimal integer |
| `%.2f` | Floating-point number with two decimal places |
| `%04d` / `%-6s` | Zero-pad number to width 4 / left-align string in a 6-character field |
| `%%` / `%n` | A literal percent sign / platform-specific line terminator |

Floating-point formatting is affected by `Locale`. Flags, width, precision, argument indices, and `Formatter` exceptions are covered in detail in the lesson on `printf()` formatting; the standalone runnable example directly below illustrates the difference between the three print methods.

## 5. Choosing a `Locale` for comparable output

`System.out.printf(Locale.US, "Gia: %.2f%n", 12.5);` prints `Gia: 12.50` and then terminates the line. If `Locale.US` is omitted, the decimal separator of `%.2f` may follow the default locale and differ across machines. Choose a locale appropriate for the reader or exchange format; `Locale.US` merely fixes the example to use a dot.

`%n` requests the platform's line terminator, whereas the `\n` escape in a Java string represents the LF character. The dedicated `printf()` formatting lesson further explains this difference when running across different operating systems.

## 6. Standalone runnable Java 17+ example and exact output

Create the file **`ConsoleOutputDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;

public class ConsoleOutputDemo {
    public static void main(String[] args) {
        System.out.print("Xin ");
        System.out.print("chao");
        System.out.println(" Java");
        System.out.println("Dong trong");
        System.out.println();

        System.out.println(2 + 3);
        System.out.println("Tong: " + (2 + 3));

        System.out.printf(Locale.US, "So luong: %d%n", 7);
        System.out.printf(Locale.US, "Gia: %.2f%n", 12.5);
        System.out.printf(Locale.US, "Bang: |%-6s|%04d|%n", "A", 9);
        System.out.printf(Locale.US, "Ty le: %.1f%%%n", 87.4);
        System.out.printf(Locale.US, "Hex: %x, ky tu: %c, dung: %b%n",
                          255, 'Z', true);

        String saved = String.format(Locale.US, "Ma=%03d", 5);
        System.out.println("Chuoi: " + saved);

        int[] values = {4, 6};
        System.out.println("Mang: " + Arrays.toString(values));
    }
}
```

Open a terminal in the directory containing the file, using **JDK 17 or later** on Windows (PowerShell/CMD) or Linux/macOS:

```bash
javac -encoding UTF-8 ConsoleOutputDemo.java
java ConsoleOutputDemo
```

Exact stdout (there is **one blank line** after `Dong trong`; a successful `javac` command prints nothing):

```text
Xin chao Java
Dong trong

5
Tong: 5
So luong: 7
Gia: 12.50
Bang: |A     |0009|
Ty le: 87.4%
Hex: ff, ky tu: Z, dung: true
Chuoi: Ma=005
Mang: [4, 6]
```

Breakdown:

1. The first two `print()` calls continue on the same line; `println(" Java")` ends that line.
2. `println()` with no arguments produces a blank line.
3. `println(2 + 3)` prints the result of the arithmetic addition, `5`.
4. `printf` outputs the exact types and widths for `%d`, `%.2f`, `%-6s`, `%04d`, `%.1f`, `%x`, `%c`, `%b`; `%%` is a literal percent sign.
5. `String.format` **returns a `String`** without printing it; `println` then writes that string to the console.
6. `Arrays.toString` turns the array contents into a readable string.

## 7. When `printf()` throws an error or merges lines

Invalid format strings can **compile successfully but throw an exception at runtime**: `printf("%d", "7")` passes a `String` instead of an integer and causes `IllegalFormatConversionException`; `printf("%d %s", 3)` is missing an argument and causes `MissingFormatArgumentException`.

`%f` does not automatically convert a `String` to a floating-point number; when needed, parse and validate the data first. `printf("Ti le: %d%%%n", 80);` prints `Ti le: 80%` and moves to a new line: `%%` prints the percent sign, and `%n` terminates the line. Do not write a bare `%` sign in a format template, and do not expect `printf()` to automatically add a newline. The in-depth formatting lesson provides a complete table of conversion, flag, and precision errors.

## 8. When should you choose which method?

| Need | Suitable method |
| --- | --- |
| Print a simple message and move to a new line | `println("Da xong")` |
| Print multiple parts of the same line | `print(...)`, then `println(...)` when you want to end the line |
| Print multiple values needing width, decimal places, or padding | `printf(...)` |
| Build a formatted string to store or return, **without printing immediately** | `String.format(...)` |
| Output errors/diagnostics separately from the stdout stream | `System.err.println(...)` when appropriate |

`System.out` is **standard output**; `System.err` is **standard error**, typically used for error messages. A terminal may display both on the same screen, but they are two separate streams and can be redirected independently.

Example:

```bash
java ConsoleOutputDemo > output.txt
```

This command redirects stdout into the file `output.txt` using common shell syntax. File encoding resulting from redirection may vary by shell environment; when an application needs exact formatting and characters in an output file, use a file-writing API with an explicit charset rather than relying implicitly on terminal configuration.

## 9. Quick pre-run checklist

- If parts run together on one line: check whether you accidentally used `print` instead of `println` or forgot `%n` in `printf`.
- If math results are concatenated as text: wrap the arithmetic expression in parentheses before using `+` with a `String`.
- If decimal numbers do not display as expected: check `%.nf`, the argument type, and the `Locale`.
- If formatting throws an exception: match each specifier (`%d`, `%f`, `%s`) against the actual argument count and types.
- If an array prints in an unreadable form: use `Arrays.toString` or `Arrays.deepToString` as appropriate.
- If error messages appear in the same place as results: remember to distinguish `System.err` from `System.out`; both streams may be displayed in the same terminal.

**Key takeaway:** `print` continues on the same line, `println` prints and moves to a new line, and `printf` prints using a template and only moves to a new line when the template includes a line terminator. Choosing the right method keeps console output readable and accurately verifiable.