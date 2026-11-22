# Reading Console Data with `Scanner` (Java 17+)

## 1. What is `Scanner` and when is it used?

`java.util.Scanner` is a utility class that reads input as **tokens** or **lines**, and can parse data into types such as `int`, `long`, `double`, and `boolean`. In console I/O lessons, a `Scanner` is commonly attached to `System.in`:

```java
import java.util.Scanner;

Scanner scanner = new Scanner(System.in);
String name = scanner.nextLine();
int age = scanner.nextInt();
```

These are illustrative statements that belong inside an appropriate method or code block. `System.in` is the standard input stream; it usually receives characters from the keyboard when running in a terminal, though it can also read data from a file or pipe. `Scanner` turns this stream into structured values.

`Scanner` is well suited for small console programs, exercises, and simple command-line tools. For very large volumes of text data, you may consider `BufferedReader` to explicitly read line by line; `Scanner` is more convenient when you need to split and parse tokens.

## 2. Key methods

| Method | Data read | Characteristics |
| --- | --- | --- |
| `next()` | Next token, returns `String` | Skips whitespace delimiters by default; reads only one token |
| `nextLine()` | Remainder of the current line, returns `String` | Can include spaces; strips the line terminator from the return value |
| `nextInt()` / `nextLong()` | Integer token | Parses using the current radix/locale; throws an error if the token is invalid or out of range |
| `nextDouble()` / `nextFloat()` | Floating-point token | Decimal separator and grouping rules are affected by `Locale` |
| `nextBoolean()` | Boolean token | Accepts `true`/`false` using case-insensitive matching |
| `hasNext()` / `hasNextLine()` | `boolean` | Checks whether another token/line remains, useful at end of input |
| `hasNextInt()` / `hasNextDouble()` | `boolean` | Checks whether the next token can be parsed as that type |
| `useLocale(locale)` | Configures Scanner | Sets number syntax rules according to locale |
| `useDelimiter(regex)` | Configures Scanner | Replaces the default token delimiter pattern with a regular expression |

**Tokens differ from lines:** given the input `Nguyen Van An`, `next()` only reads `Nguyen`, whereas `nextLine()` can read the entire `Nguyen Van An` (when starting at the beginning of the line).

By default, `Scanner`'s token delimiters are whitespace characters (spaces, tabs, newlines, etc.). Methods like `nextInt()`, `nextDouble()`, and `next()` read by **token**; `nextLine()` reads by **line boundary**. Mixing these two styles requires care.

## 3. Complete example: reading name, age, score, and note

Create the file **`ScannerDemo.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            scanner.useLocale(Locale.US);

            System.out.println("Enter full name:");
            String name = scanner.nextLine();

            System.out.println("Enter age:");
            int age = scanner.nextInt();

            System.out.println("Enter score:");
            double score = scanner.nextDouble();

            scanner.nextLine(); // consume the remainder of the score line
            System.out.println("Enter note:");
            String note = scanner.nextLine();

            System.out.printf(Locale.US,
                    "Result: %s | age=%d | score=%.1f | note=%s%n",
                    name, age, score, note);
        }
    }
}
```

**Input** (type each value and press Enter, or create a file `sample.txt` containing these exact four lines):

```text
Nguyen Van An
20
8.5
Likes Java
```

Compile in the directory containing `ScannerDemo.java` using **JDK 17+**:

```sh
javac -encoding UTF-8 --release 17 -d out ScannerDemo.java
java -cp out ScannerDemo
```

Create the `out` directory beforehand with `mkdir out` if it does not already exist. In an interactive run, the terminal may echo back the characters the user types; characters echoed by the terminal **are not part of the stdout printed by Java**.

To verify stable output with `sample.txt`:

- **Linux/macOS or Windows CMD:** `java -cp out ScannerDemo < sample.txt`
- **Windows PowerShell 5.1+:** `Get-Content -LiteralPath sample.txt | java -cp out ScannerDemo`

**Exact stdout of the program** with the input shown above (excluding input echoed by the terminal):

```text
Enter full name:
Enter age:
Enter score:
Enter note:
Result: Nguyen Van An | age=20 | score=8.5 | note=Likes Java
```

Key steps to understand:

1. `nextLine()` reads the entire name including spaces.
2. `nextInt()` reads the token `20`; `nextDouble()` reads the token `8.5`.
3. `scanner.useLocale(Locale.US)` specifies `.` as the decimal separator. The machine's default locale may differ, so `8.5` might not always be parsed as expected if this configuration is omitted.
4. `scanner.nextLine()` immediately after `nextDouble()` explicitly reads and discards the remainder of the score line so that the following `nextLine()` receives the note line.
5. `System.out.printf(Locale.US, ...)` fixes how the decimal point is formatted in the output.

The example code assumes age and score are **properly formatted**. If the input is malformed or truncated, `nextInt()`, `nextDouble()`, and `nextLine()` may throw exceptions; sections 6–7 explain how to handle them.

## 4. Watch out when switching from token reading to line reading

`nextInt()` and `nextDouble()` read a **numeric token**; `nextLine()` reads the **remainder of the current line**. Given the input `21\nHello Java\n`, after `nextInt()`, the next `nextLine()` receives `""` because the number's line has nothing left on it. If there is text after the number on the same line, `nextLine()` returns that text instead of an empty string.

When the contract specifies **a number on one line and a note on the next line**, you can call `nextLine()` once to consume the remainder and then call it again to read the note. When you want one field per line with straightforward error checking, using `Integer.parseInt(scanner.nextLine().strip())` after checking that a line exists is another option. Do not blindly discard the remainder if it holds data you need to keep.

`ScannerDemo` above applies the first approach; the lesson on handling leftover newlines covers cases with or without same-line text, EOF, and alternative strategies using standalone reproducible programs.

## 5. Reading tokens, lines, and custom delimiters as needed

A token is determined by the current **delimiter**. Example of reading words separated by whitespace:

```java
import java.util.Scanner;

public class TokenDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("red green\nblue")) {
            while (scanner.hasNext()) {
                System.out.println("token=" + scanner.next());
            }
        }
    }
}
```

```sh
javac -encoding UTF-8 --release 17 -d out TokenDemo.java
java -cp out TokenDemo
```

Output:

```text
token=red
token=green
token=blue
```

If you want to split on commas, you can change the delimiter:

```java
scanner.useDelimiter(",");
```

This is an illustrative statement to place inside a block with a suitable `scanner` variable. `useDelimiter` accepts a **regex**, not a plain literal string for arbitrary symbols. For example, to split on both commas and whitespace, use `scanner.useDelimiter("[,\\s]+");` in Java source; Java turns `\\` in the string literal into `\`, so the regular expression receives `\s` as the whitespace character class.

Use `nextLine()` when you need to preserve spaces between words (full names, user-entered sentences), and use `next()`/`nextInt()` when the input is genuinely structured as a sequence of tokens.

## 6. Checking data before parsing

If `nextInt()` encounters `abc`, `Scanner` typically throws `InputMismatchException`. If no tokens remain, `nextInt()` can throw `NoSuchElementException`. `hasNextInt()` checks the next token before reading:

```java
if (scanner.hasNextInt()) {
    int value = scanner.nextInt();
    System.out.println("value=" + value);
} else {
    System.out.println("Not a valid int token");
}
```

The snippet above is illustrative and depends on a `scanner` variable. When `hasNextInt()` returns `false` because of a bad token, the scanner **has not automatically removed the invalid token**; if you loop without consuming or discarding it, the loop may fail to make progress. When validating line-based input, read `nextLine()`, parse it, and give feedback to the user.

### Complete example: reading a line, handling invalid integers and EOF

Create **`ValidatedScannerDemo.java`**:

```java
import java.util.Scanner;

public class ValidatedScannerDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            System.out.println("Enter an integer from 0 to 100:");

            if (!scanner.hasNextLine()) {
                System.out.println("Error: no input");
                return;
            }

            String text = scanner.nextLine().strip();
            try {
                int number = Integer.parseInt(text);
                if (number < 0 || number > 100) {
                    System.out.println("Error: out of range");
                } else {
                    System.out.println("Accepted: " + number);
                }
            } catch (NumberFormatException ex) {
                System.out.println("Error: not an integer");
            }
        }
    }
}
```

Compile:

```sh
javac -encoding UTF-8 --release 17 -d out ValidatedScannerDemo.java
```

Run:

```sh
java -cp out ValidatedScannerDemo
```

For each run, the user provides **a single line**. Corresponding outputs:

| Input | Stdout from the program |
| --- | --- |
| `42` | `Enter an integer from 0 to 100:` then `Accepted: 42` |
| `abc` | Prompt line then `Error: not an integer` |
| `150` | Prompt line then `Error: out of range` |
| Immediate EOF | Prompt line then `Error: no input` |

With input `42`, the **exact stdout** is:

```text
Enter an integer from 0 to 100:
Accepted: 42
```

The example reads the entire line, so it handles values with leading/trailing whitespace via `trim()` without hitting the post-`nextInt()` newline pitfall. `Integer.parseInt` here is an `Integer` API, so a format error produces `NumberFormatException`, unlike `Scanner.nextInt()`'s `InputMismatchException`.

**Difference between checking and validating:** `hasNextLine()` prevents calling `nextLine()` at EOF, yet it does not verify numeric format. Conversely, `hasNextInt()` verifies an integer token according to `Scanner`, yet it does not replace business range checks such as 0 to 100.

## 7. Exceptions and issues to know

| Situation | Possible consequence | How to prevent |
| --- | --- | --- |
| `nextInt()` reads `abc` or a number outside `int` range | `InputMismatchException` | `hasNextInt()`, notify the user, discard the bad token, or read the full line and parse |
| `nextLine()` or `next()` when no lines/tokens remain | `NoSuchElementException` | Use `hasNextLine()` or `hasNext()` appropriately before reading |
| Using scanner after `scanner.close()` | `IllegalStateException` | Do not continue using a closed object |
| Forgetting the leftover line after `nextInt()` | `nextLine()` returns an empty string or the rest of the old line | Use `nextLine()` to discard the remainder when appropriate, or read full lines and parse |
| `nextDouble()` does not accept `8.5` as expected | Active numeric locale differs | Set `useLocale(Locale.US)` if `.` is required as the decimal separator |
| Entering a number outside the business range | May parse successfully yet still be invalid data | Check the value domain after parsing |
| Using multiple `Scanner(System.in)` instances simultaneously | Buffering/lookahead causes scanners to compete and produce confusing errors | Maintain one shared scanner for console input |

In addition to these errors, `Scanner` may block waiting when the program requests data and the input has not yet supplied a complete token or line. For interactive console tasks, check the prompt and confirm you pressed Enter or closed the input stream.

## 8. `Locale` and input source encoding

`scanner.useLocale(Locale.US)` makes `nextDouble()` parse forms like `8.5` with a dot decimal point. Other locales may use a comma, so examples needing deterministic output should specify the locale explicitly. `Scanner.nextLine()` returns an unparsed string; calling `Double.parseDouble` on a dot-formatted string follows a different contract from locale-sensitive `Scanner.nextDouble()`.

For a byte source that needs UTF-8 decoding, you can construct `new Scanner(System.in, StandardCharsets.UTF_8)` (with the corresponding import). `javac -encoding UTF-8` only controls reading the **source code**; it does not configure the default encoding for `System.in` data. The lesson on `Locale` and input ownership analyzes each case in detail.

## 9. Ownership and closing `Scanner`

`Scanner` implements `AutoCloseable`; when closed, it also closes the underlying source if that source implements `Closeable`. Therefore `try (Scanner s = new Scanner(System.in)) { ... }` fits small programs that finish all reading upon exiting the block. However, `System.in` may be shared, so do not close a scanner borrowing it mid-program if other parts still need to read.

Sources opened by your own code (such as files) should be closed promptly; a scanner created from a `String` does not affect `System.in`. Keep one place responsible for the input lifecycle and avoid creating multiple scanners competing over the shared console stream. The final lesson in the chapter provides dedicated examples on closing sources and configuring locale.

## 10. Good habits when writing console programs

1. **Decide whether input is organized by token or by line.** Full names and descriptive sentences should use `nextLine()`; lists of whitespace-separated numbers may fit `nextInt()`/`nextDouble()`.
2. **Keep reading consistent.** Use line reading plus parsing when you want clear validation and error messages; when mixing tokens and lines, watch out for the remainder of the line.
3. **Check for EOF before reading** with the appropriate `hasNext...()` method if the input source can end early.
4. **Validate type and range independently.** `42` may be a valid `int` yet not a valid age under the application's contract.
5. **Set `Locale` explicitly** for floating-point numbers and keep input/output formatting rules consistent.
6. **Do not use multiple scanners on the same `System.in`** unless genuinely necessary; pass a single scanner across methods.
7. **Do not display or log sensitive data** such as passwords entered from the terminal. `Scanner(System.in)` does not disable terminal echo, so it is unsuitable for password prompts that need masked input; look at `System.console().readPassword()` in environments where a console is available.

## 11. Self-check

**1. Given input `Tran Van Binh`, how do `next()` and `nextLine()` differ?** `next()` reads the token `Tran`; `nextLine()` reads the remainder of the current line depending on the read position. If at the start of the line, it reads `Tran Van Binh`.

**2. Why does `nextLine()` immediately after `nextInt()` often return an empty string?** Because `nextInt()` consumes only the numeric token, leaving the newline behind; `nextLine()` reads the remainder of that line.

**3. Does reading `abc` with `nextInt()` return 0?** No. It typically throws `InputMismatchException`. Use format checks and error handling.

**4. When `hasNextInt()` returns `false`, does it discard the invalid token automatically?** No. To continue, you must read/discard the invalid token to advance to the next input.

**5. Does `nextDouble()` always treat `8.5` as a valid floating-point number?** No; it depends on `Locale`. You can call `scanner.useLocale(Locale.US)`.

**6. Is closing `Scanner(System.in)` mid-program harmless?** No. It can close `System.in` itself, preventing subsequent input steps from working.

**Key takeaway:** `Scanner` makes reading and parsing console data convenient, yet you must choose **token vs. line** boundaries intentionally, manage **locale**, handle **invalid data/EOF**, and control the lifecycle of `System.in` deliberately.