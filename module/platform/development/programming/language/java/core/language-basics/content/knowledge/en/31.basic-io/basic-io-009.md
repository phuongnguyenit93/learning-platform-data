# Locale, Decimal Separators, and Input Source Closing Responsibility in Java

## 1. Why can number input vary across machines?

When a user enters a floating-point number, how the decimal separator and thousands grouping separator are written depends on **regional conventions** (*locale*). For example:

| Locale | The number one thousand two hundred thirty-four point five | Meaning |
| --- | --- | --- |
| `Locale.US` | `1,234.50` | Comma groups thousands, dot separates decimal part |
| `Locale.GERMANY` | `1.234,50` | Dot groups thousands, comma separates decimal part |

Both notations represent the **same numeric value**, yet the input text differs. If you use `java.util.Scanner` to read a number, `Scanner`'s token parser can be affected by locale. If you use `System.out.printf` or `String.format` to display a number, the decimal and grouping characters can also change by locale.

**Two tasks to keep separate:**

1. **Reading/parsing:** converting text such as `"1.234,50"` into a `double` value.
2. **Displaying/formatting:** converting the value `1234.5` into text according to the required convention.

Do not treat commas and dots as having identical meaning in every locale. Nor should you assume the locale settings on your study machine match those of a grading environment or end-user machine.

## 2. `Scanner` reads numbers by locale

`Scanner` is a class in the `java.util` package. It reads input by token and provides methods such as `nextInt()`, `nextDouble()`, `next()`, and `nextLine()`.

```java
import java.util.Locale;
import java.util.Scanner;

// Code inside a method:
try (Scanner scanner = new Scanner("12.75")) {
    scanner.useLocale(Locale.US);
    double value = scanner.nextDouble(); // 12.75
}
```

- `scanner.useLocale(Locale.US)` sets the locale used when `Scanner` parses numbers.
- `nextDouble()` takes the next token and parses it into a `double` value using the selected locale.
- `nextInt()` also uses integer rules related to the current locale and radix.
- `next()` only reads one token as a `String` without converting it to a number.
- `nextLine()` reads the remainder of the line as a `String` without parsing the line's content into a number.

If `useLocale` is not called, `Scanner` uses the environment's default locale at creation time. Do not write tests that depend on that. In examples with exact expected output, **specify the locale explicitly**.

### Same value, two input notations

```java
try (Scanner us = new Scanner("1,234.50");
     Scanner de = new Scanner("1.234,50")) {
    us.useLocale(Locale.US);
    de.useLocale(Locale.GERMANY);

    double a = us.nextDouble(); // 1234.5
    double b = de.nextDouble(); // 1234.5
}
```

The strings used here have thousands-grouping and decimal formats valid for the two chosen locales. The results in variables `a` and `b` are **numeric values** and no longer carry the comma or dot notation from the original source.

If a token is invalid for the locale or outside the forms `Scanner` accepts, `nextDouble()` may throw `InputMismatchException`. If the source is exhausted, `NoSuchElementException` may occur; if the `Scanner` is closed, read operations may throw `IllegalStateException`.

## 3. Checking with `hasNextDouble()` and handling invalid data

`hasNextDouble()` checks whether the next token can be parsed by `Scanner` as a `double` under the current rules. It **does not consume** the token.

```java
import java.util.Locale;
import java.util.Scanner;

// Place inside a method:
try (Scanner scanner = new Scanner("abc 12.5")) {
    scanner.useLocale(Locale.US);

    if (!scanner.hasNextDouble() && scanner.hasNext()) {
        String invalid = scanner.next(); // Consume "abc"
        System.out.println("Invalid: " + invalid);
    }

    if (scanner.hasNextDouble()) {
        double number = scanner.nextDouble(); // 12.5
        System.out.println("Number: " + number);
    }
}
```

Crucial point: if `hasNextDouble()` returns `false` and a loop keeps checking the same token, the program can loop forever. You must **discard the invalid token**, re-prompt, or stop according to the chosen error policy.

`hasNextDouble()` checks **syntax parseable as a floating-point number**, not business conditions such as "value must be greater than 0" or "must be finite." If numeric data must be finite, additionally check `Double.isFinite(value)`. Not every `double` value fits the application's data domain.

Do not use an empty `catch (Exception e) { }` block to hide invalid input. For console programs, clear error messages and a retry loop are far more helpful.

## 4. `Double.parseDouble()` does not parse by locale

`Double.parseDouble(String)` processes floating-point representations according to Java's defined syntax, **without using the user's default locale** to interpret decimal separators. For example:

```java
double a = Double.parseDouble("12.5"); // 12.5

// Double.parseDouble("12,5");
// Throws NumberFormatException: comma is not treated as a decimal separator.
```

If you want to read a floating-point number from a **fixed text line** using dot-decimal syntax, you can use `Scanner.nextLine()` followed by `Double.parseDouble(text.trim())`. This avoids mixing `nextDouble()` with `nextLine()` and keeps the input syntax clear.

Conversely, if you want to accept localized text such as `"1.234,50"`, use `Scanner` with `Locale.GERMANY` or an appropriate parser such as `NumberFormat` with the desired locale and validation rules. Do not blindly replace every comma with a dot: in some locales a comma is a decimal separator, while in others it is a thousands-grouping separator. Incorrect replacement can **alter the numeric value**.

| API | Applies locale when reading numbers? | Example |
| --- | --- | --- |
| `Scanner.useLocale(...)` + `nextDouble()` | Yes | `"1.234,50"` with `Locale.GERMANY` |
| `Scanner.useLocale(...)` + `nextInt()` | Yes, per integer/radix rules | `"123"` with `Locale.US` |
| `Double.parseDouble("12.5")` | No | Accepts dot according to Java syntax |
| `Integer.parseInt("123")` | No | Accepts Java integer syntax, not locale thousands grouping |
| `Scanner.nextLine()` | Does not parse numbers automatically | Reads a text line, leaving parsing rules up to you |

## 5. Locale also affects `printf()`

When printing floating-point numbers, `System.out.printf` has an overload accepting a `Locale`:

```java
double price = 1234.5;

System.out.printf(Locale.US, "US: %,.2f%n", price);
System.out.printf(Locale.GERMANY, "DE: %,.2f%n", price);
```

This snippet requires `import java.util.Locale;` and placement inside a method. Corresponding stdout:

```text
US: 1,234.50
DE: 1.234,50
```

In `%,.2f`:

- `%f` formats a floating-point number in decimal form.
- `.2` selects two digits after the decimal separator.
- The `,` inside the **format template** enables digit grouping; the actual grouping character in the output depends on the locale.
- `%n` produces the platform-specific line terminator.

If the `Locale` argument is omitted, the displayed format may change depending on the environment's default locale. `String.format(Locale.US, ...)` also produces a formatted string under the corresponding rules without **automatically printing** to the console.

**Distinguishing two kinds of commas:** the `,` in the format string `"%,.2f"` is a flag that **enables grouping**, not a promise to always print a comma in the output. With `Locale.GERMANY`, the displayed grouping separator is a dot, while the decimal separator is a comma.

## 6. What does `Scanner.close()` close?

`Scanner` implements `java.io.Closeable` and provides a `close()` method. When closed, it marks the scanner as closed; if the underlying input source implements `Closeable`, the scanner **also calls `close()` on that source**.

Therefore, ask an important question: **does this code own the input source?**

### Sources opened by the program itself: should be closed

Example using `Scanner` to read a file opened by the method itself:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

class FileReaderExample {
    static void showFirstToken(Path file) throws IOException {
        try (Scanner scanner =
                new Scanner(file, StandardCharsets.UTF_8)) {
            if (scanner.hasNext()) {
                System.out.println(scanner.next());
            }
        } // Scanner is automatically closed here.
    }
}
```

This is an **illustrative class** without `main`. With the `Scanner(Path, Charset)` constructor on Java 17, you can specify the file's charset explicitly. `try-with-resources` calls `close()` automatically upon exiting the block, even if a `return` or exception occurs inside the block.

Promptly closing resources is especially important for files or streams owned by the program. Do not rely on the Garbage Collector to release all external resources on its own.

### `Scanner(String)`: suited for examples/tests, safe to close at end of scope

```java
try (Scanner scanner = new Scanner("Java 17")) {
    System.out.println(scanner.next());
}
```

This source is an in-memory string; the example neither opens a file nor closes `System.in`. Closing the scanner still aligns with the principle of not reusing a reader object after its scope ends.

### `Scanner(System.in)`: mind the shared source

`System.in` is the **shared standard input stream of the Java process**. When you write:

```java
Scanner console = new Scanner(System.in);
```

the scanner uses `System.in` as its source. If you call `console.close()`, `Scanner` can also close the underlying `System.in`. That affects other parts of the program that want to continue reading from `System.in`. **Do not arbitrarily close a scanner wrapping `System.in` when other components still need the input source.**

In a simple console application, you can create **one shared scanner** and keep it until all input reading is complete, rather than creating and closing multiple scanners on `System.in`. At the application shutdown boundary, the resource-closing strategy depends on **who owns** the stream. If a method only **borrows** a scanner supplied elsewhere, that method usually should not close it.

Do not mistakenly assume a `Scanner` must never be closed: the core rule is that **the owner of the source controls its lifecycle**, not "always close" or "never close" every scanner.

## 7. Standalone runnable Java 17+ program, independent of machine locale

Create the file **`LocaleInputDemo.java`**:

```java
import java.io.StringReader;
import java.util.Locale;
import java.util.Scanner;

public class LocaleInputDemo {
    static double read(String text, Locale locale) {
        try (Scanner scanner = new Scanner(text)) {
            scanner.useLocale(locale);
            if (!scanner.hasNextDouble()) {
                throw new IllegalArgumentException("invalid number");
            }
            double result = scanner.nextDouble();
            if (!Double.isFinite(result)) {
                throw new IllegalArgumentException("non-finite number");
            }
            return result;
        }
    }

    static class TrackedReader extends StringReader {
        boolean closed;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            super.close();
            closed = true;
        }
    }

    public static void main(String[] args) {
        double us = read("1,234.50", Locale.US);
        double de = read("1.234,50", Locale.GERMANY);

        System.out.printf(Locale.US, "US input: %.2f%n", us);
        System.out.printf(Locale.US, "DE input: %.2f%n", de);

        System.out.printf(Locale.US, "US output: %,.2f%n", us);
        System.out.printf(Locale.GERMANY, "DE output: %,.2f%n", de);

        double plain = Double.parseDouble("12.5");
        System.out.println("parseDouble: " + plain);

        try {
            Double.parseDouble("12,5");
        } catch (NumberFormatException ex) {
            System.out.println("parseDouble rejects comma");
        }

        try (Scanner scanner = new Scanner("abc 7.5")) {
            scanner.useLocale(Locale.US);
            if (!scanner.hasNextDouble() && scanner.hasNext()) {
                System.out.println("bad token: " + scanner.next());
            }
            System.out.printf(Locale.US, "next: %.1f%n",
                    scanner.nextDouble());
        }

        TrackedReader source = new TrackedReader("hello");
        try (Scanner scanner = new Scanner(source)) {
            System.out.println("owned input: " + scanner.next());
        }
        System.out.println("source closed: " + source.closed);
    }
}
```

Run in the directory containing the file with **JDK 17 or later**. These commands work on PowerShell/CMD (Windows) and bash/zsh (Linux/macOS):

```bash
javac -encoding UTF-8 LocaleInputDemo.java
java LocaleInputDemo
```

**Exact stdout** (a successful compilation command prints nothing):

```text
US input: 1234.50
DE input: 1234.50
US output: 1,234.50
DE output: 1.234,50
parseDouble: 12.5
parseDouble rejects comma
bad token: abc
next: 7.5
owned input: hello
source closed: true
```

### Example explanation

1. Both `read` calls use `Scanner.useLocale` tailored to each string, so `"1,234.50"` and `"1.234,50"` are both read as the value `1234.5`.
2. When formatted with `Locale.US`, the value displays as `1,234.50`; with `Locale.GERMANY`, as `1.234,50`. The numeric value **does not change**, only the display representation differs.
3. `Double.parseDouble("12.5")` succeeds, whereas `Double.parseDouble("12,5")` throws `NumberFormatException` because that API does not adopt locale commas automatically.
4. `hasNextDouble()` detects that the first token `abc` is invalid, `next()` discards it, and then `nextDouble()` reads `7.5`.
5. `TrackedReader` is a custom `StringReader` tracking whether the source was closed. Upon exiting `try (Scanner ...)`, the scanner closes `source` and the `closed` flag becomes `true`.

By using fixed input strings and explicit `Locale` arguments, the program **requires no manual typing** and does not depend on the host machine's default locale.

## 8. Keyboard-reading pattern: deciding where to close `Scanner`

Example of reading a line containing a floating-point number with a dot decimal separator, along with error messages:

```java
import java.util.Scanner;

public class KeyboardNumber {
    public static void main(String[] args) {
        Scanner input = new Scanner(System.in);
        System.out.print("Enter number with a dot: ");

        if (input.hasNextLine()) {
            String text = input.nextLine().trim();
            try {
                double value = Double.parseDouble(text);
                if (!Double.isFinite(value)) {
                    System.err.println("Number must be finite.");
                } else {
                    System.out.println("Value: " + value);
                }
            } catch (NumberFormatException ex) {
                System.err.println("Invalid number.");
            }
        } else {
            System.err.println("No input.");
        }

        // Do not close input here: the example treats System.in as a shared source.
    }
}
```

File named **`KeyboardNumber.java`**, run:

```bash
javac -encoding UTF-8 KeyboardNumber.java
java KeyboardNumber
```

This is an **interactive program**: the user enters data and presses Enter; output depends on the string entered. For example, if `12.5` is entered, stdout after the prompt contains `Value: 12.5`. Because `Double.parseDouble()` uses locale-independent syntax, the example **intentionally requires** entering a dot. If the application requires localized number entry, change the parsing mechanism to match rather than writing contradictory instructions.

Note on resource-leak checkers: for code borrowing `System.in`, some static analysis tools may warn that the scanner is not closed. Do not fix that warning by **closing the shared standard stream** if the program requires using that stream elsewhere; instead, define clear ownership and lifecycle boundaries.

## 9. Common mistakes

| Mistake or assumption | Explanation / fix |
| --- | --- |
| `Scanner.nextDouble()` parses incorrectly on a machine with another locale | Specify `useLocale(Locale.US)` or the locale matching the data format |
| Thinking `Double.parseDouble("1,5")` reads comma-decimal numbers by locale | No; `parseDouble` ignores locale; use an appropriate parser or controlled input syntax |
| Blindly replacing every comma with a dot on all numeric strings | Can alter the meaning of grouping vs. decimal separators, especially for values like `1,234` |
| Forgetting locale in `printf("%.2f", value)` when exact stdout is required | Specify `printf(Locale.US, ...)` when dot-formatted output is needed |
| Thinking `hasNextDouble()` already consumed the token | No; it only checks—you must call `nextDouble()` or discard the token logically |
| Catching an exception and retrying on the same bad token without removing it | The loop will hit the same error again; call `next()` or re-read the line with explicit rules |
| Always closing `Scanner(System.in)` right after one method | Can close `System.in` while other parts still need it |
| Never closing a `Scanner` reading from a file | Leaves file resources open; use `try-with-resources` for sources you own |
| Creating multiple independent scanners on the same `System.in` | Leads to hard-to-control buffering and lifecycle issues; use one scanner with an appropriate shared scope |
| Confusing closing a scanner with GC memory cleanup | `close()` manages resource lifecycles, not just Java object garbage collection |

## 10. Pre-build checklist for an input flow

1. **Where does the data format come from?** If it is a protocol or file specifying a dot, parse according to that syntax; if it is localized user input, pick a locale-aware parser.
2. **Reading tokens or reading lines?** When calling `nextDouble()` then `nextLine()`, remember to handle the leftover line terminator. If data is line-delimited, consider using `nextLine()` consistently and parsing afterward.
3. **How strict does number validity need to be?** After parsing, check range, positivity/non-negativity, and `Double.isFinite` per business domain rules.
4. **Who owns the source?** Close self-opened files/streams promptly, preferring `try-with-resources`; do not close shared `System.in` mid-program.
5. **Does output need to be identically reproducible?** Pass `printf(Locale.US, ...)` or an explicit target locale instead of relying on machine defaults.

**Key takeaway:** `Locale` governs how many APIs such as `Scanner.nextDouble()` recognize decimal separators and how `printf()` formats numbers. `Double.parseDouble()`, by contrast, uses locale-independent syntax. With `Scanner.close()`, manage closing by **input source ownership**: close sources you open yourself, and avoid accidentally closing `System.in` while the program still needs it.