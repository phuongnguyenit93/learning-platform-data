# Reading Numbers with `Scanner` by Locale and Radix

## 1. Problem: One Token, Multiple Numeric Interpretations

`java.util.Scanner` can read text from a `String`, file, `InputStream`, or character source, split it into **tokens**, and convert those tokens into `int`, `long`, `double`, `BigDecimal`, `BigInteger`, and other types. When reading numbers, two important configurations are:

- **Locale**: specifies how to interpret decimal separators, thousands grouping separators, plus/minus signs according to regional rules, and certain other numeric representations.
- **Radix**: the **number base** used to interpret digits of an **integer**, from 2 to 36.

A string like `1,234.50` is typically interpreted as one thousand two hundred thirty-four point five zero under `Locale.US`. Under `Locale.GERMANY`, the corresponding notation is `1.234,50`. On the other hand, token `FF` is not a base-10 integer, yet has the value `255` when read in base 16.

**Core idea:** `Scanner` does not "guess" the intent of data. The program must configure locale, radix, and token-splitting rules to match the **input format**. A file produced under another system's convention does not necessarily match the default locale of the machine running the code.

## 2. Scanner Splits Tokens First, Then Parses Numbers

By default, `Scanner` uses whitespace as its delimiter: spaces, tabs, and newlines according to Scanner's delimiter pattern. Example input:

```text
12 34
56
```

The three tokens in order are `12`, `34`, `56`. Calls to `nextInt()` take each token and parse it into an integer.

Relevant APIs:

| API | Meaning |
| --- | --- |
| `hasNextInt()` | Checks whether the next token can be parsed as an `int` in the current radix, **without consuming the token** |
| `nextInt()` | Consumes the next token and parses it into an `int` with the current radix |
| `hasNextInt(radix)` | Checks `int` according to the passed radix |
| `nextInt(radix)` | Consumes and reads `int` according to the passed radix |
| `hasNextDouble()` / `nextDouble()` | Checks/reads floating-point numbers according to the current locale |
| `hasNextBigDecimal()` / `nextBigDecimal()` | Reads exact decimal numbers as `BigDecimal` |
| `useLocale(locale)` | Sets the locale that Scanner applies for number recognition |
| `useRadix(radix)` | Sets the **default radix** for integer operations that accept a radix |
| `useDelimiter(pattern)` | Changes token-splitting rules; does not change locale or radix |

`hasNextInt()` and `hasNextDouble()` check the **full token** against numeric rules. They are not tools for finding an arbitrary numeric substring in the middle of text. If a token is malformed, `nextInt()` or `nextDouble()` does not auto-fix it. Establish the delimiter before parsing numbers.

## 3. Locale: Decimal Point and Thousands Grouping

Two convention families are commonly seen:

| Input Format | Corresponding Locale | Mathematical Value |
| --- | --- | ---: |
| `1,234.50` | `Locale.US` | 1234.5 |
| `1.234,50` | `Locale.GERMANY` | 1234.5 |
| `12.75` | `Locale.US` | 12.75 |
| `12,75` | `Locale.GERMANY` | 12.75 |

In the examples above:

- `Locale.US`: comma `,` groups thousands; period `.` is the decimal separator.
- `Locale.GERMANY`: period `.` groups thousands; comma `,` is the decimal separator.

These are two specific cases; not every locale uses strictly these two rules. A locale may use special whitespace for grouping, different numeral symbols, or distinct regional rules.

Example creating a Scanner with an explicit locale:

```java
try (Scanner scanner = new Scanner("1.234,50 42")
        .useLocale(Locale.GERMANY)) {
    double amount = scanner.nextDouble();
    int count = scanner.nextInt();
}
```

This is an **illustrative snippet**, requiring imports for `java.util.Scanner` and `java.util.Locale`; variables `amount` and `count` exist only inside the block. In this case, `amount` equals `1234.5` and `count` equals `42`.

Do not replace every comma with a dot before parsing: `"1.234,50"` contains both a grouping separator and a decimal separator, and blind replacement can create invalid strings or alter data meaning. Pick the right locale and let the corresponding parser handle it.

### Default Locale and Reproducibility

If `useLocale` is not called, Scanner initializes with the JVM's default formatting locale (typically based on `Locale.getDefault(Locale.Category.FORMAT)` at creation time). This value can differ across development machines, servers, and user machines.

For instance, if an international service exports fixed `1,234.50`: the program should pick `Locale.US` (or the specified machine format) even if the host machine runs a German locale. **Do not treat the host machine's locale as the file specification**.

Distinguish **Scanner's locale when reading**, **the locale when printing with `printf`/`String.format`**, and **the charset when converting bytes ↔ characters**:

- `Scanner.useLocale(Locale.GERMANY)` chooses how to interpret `1.234,50`.
- `System.out.printf(Locale.US, "%.2f", value)` chooses how to **print** `1234.50`.
- `StandardCharsets.UTF_8` controls how text converts to bytes; it **does not determine the decimal separator**.

## 4. Radix: Bases from 2 to 36 for Integers

Radix is the base used to interpret digit positions. With `nextInt(radix)`:

| Token | Radix | Decimal Value |
| --- | ---: | ---: |
| `1011` | 2 | 11 |
| `17` | 8 | 15 |
| `10` | 10 | 10 |
| `FF` | 16 | 255 |
| `Z` | 36 | 35 |

For example, `1011` in base 2 equals `1×2³ + 0×2² + 1×2¹ + 1×2⁰ = 11`. Valid radix values for Scanner integer-reading APIs range from **`Character.MIN_RADIX` (2)** to **`Character.MAX_RADIX` (36)**. An invalid radix such as 1 or 37 causes `IllegalArgumentException` per the API contract.

Two ways to specify radix:

```java
int a = scanner.nextInt(16); // radix 16 for this read only
scanner.useRadix(2);         // set default radix
int b = scanner.nextInt();   // read the next token in radix 2
```

This is an **illustrative snippet**; `scanner` must be initialized and have matching tokens. Initially by default, Scanner uses radix **10**. `useRadix(16)` affects calls without a radix argument on corresponding integer methods such as `nextInt()`, `hasNextInt()`, and `nextLong()`. A call like `nextInt(10)` still uses radix 10 for that single read.

**Radix is not locale.** Radix interprets digits of **integers**; locale interprets regional numeric conventions. `nextDouble()` and `nextBigDecimal()` have no `nextDouble(radix)` or `nextBigDecimal(radix)` overloads; `useRadix(16)` does not turn floating-point methods into a "hexadecimal floating-point parser."

When receiving hex integers from an agreed format, document clearly that it is radix 16 and supply digits like `FF`; do not assume `nextInt(16)` automatically handles `0x` prefixes, `#` signs, or digit separators defined by a particular programming language.

## 5. Complete Java 17+ Example: Reading by Locale and Radix

Create file **`ScannerLocaleRadixDemo.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleRadixDemo {
    public static void main(String[] args) {
        try (Scanner us = new Scanner("1,234.50 42")
                .useLocale(Locale.US)) {
            System.out.printf(Locale.ROOT, "US double=%.2f%n", us.nextDouble());
            System.out.println("US int=" + us.nextInt());
        }

        try (Scanner de = new Scanner("1.234,50 42")
                .useLocale(Locale.GERMANY)) {
            System.out.printf(Locale.ROOT, "DE double=%.2f%n", de.nextDouble());
            System.out.println("DE int=" + de.nextInt());
        }

        try (Scanner radix = new Scanner("FF 1011 17 10")
                .useLocale(Locale.US)) {
            System.out.println("hex FF=" + radix.nextInt(16));
            System.out.println("binary 1011=" + radix.nextInt(2));

            radix.useRadix(8);
            System.out.println("default octal 17=" + radix.nextInt());

            radix.useRadix(10);
            System.out.println("default decimal 10=" + radix.nextInt());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ScannerLocaleRadixDemo.java
java ScannerLocaleRadixDemo
```

Output:

```text
US double=1234.50
US int=42
DE double=1234.50
DE int=42
hex FF=255
binary 1011=11
default octal 17=15
default decimal 10=10
```

Why is the output correct?

1. The first two Scanners receive different grouping/decimal punctuation, yet `useLocale` causes both to parse the mathematical number `1234.5`. `printf(Locale.ROOT, "%.2f")` fixes the output dot notation so results are predictable across machines.
2. `nextInt(16)` parses `FF` to `255`; `nextInt(2)` parses `1011` to `11`.
3. `useRadix(8)` sets the default radix of the third scanner; token `17` equals `1×8+7=15`.
4. `useRadix(10)` resets the radix; token `10` is read as `10`.
5. All Scanners read from in-memory strings without depending on data files or `System.in`; `try-with-resources` closes resources properly.

## 6. Checking Tokens Before Reading and Handling Errors

When user-supplied content may be invalid, call `hasNextInt(radix)` or `hasNextDouble()` before `next...`. Those `hasNext...` methods **do not consume the token**, so you must advance the position with `next...` on success, or `next()` to discard an invalid token and avoid an infinite loop.

Create file **`ScannerValidationDemo.java`**:

```java
import java.util.Scanner;

public class ScannerValidationDemo {
    public static void main(String[] args) {
        try (Scanner input = new Scanner("FF G1 2147483648")) {
            if (input.hasNextInt(16)) {
                System.out.println("hex=" + input.nextInt(16));
            }

            if (!input.hasNextInt(16)) {
                System.out.println("invalid=" + input.next());
            }

            if (!input.hasNextInt()) {
                System.out.println("out of int=" + input.next());
            }
        }
    }
}
```

Compile and run:

```bash
javac ScannerValidationDemo.java
java ScannerValidationDemo
```

Output:

```text
hex=255
invalid=G1
out of int=2147483648
```

- `FF` is a valid base-16 integer token.
- `G1` contains `G`, which is not a valid base-16 digit. `hasNextInt(16)` returns `false`; `next()` is called to consume the bad token.
- `2147483648` exceeds `Integer.MAX_VALUE` (`2147483647`). Even though it contains only decimal digits, it is **not a valid `int`**. `hasNextInt()` returns `false`; if you need this number, consider `nextLong()` or `nextBigInteger()` after establishing data rules.

When calling `nextInt()`, `nextDouble()`, or `nextBigDecimal()` directly on a mismatched format or out-of-range number, `Scanner` can throw `InputMismatchException`. Calling `next...` when input is exhausted throws `NoSuchElementException`; using a closed scanner throws `IllegalStateException`. Do not lump them into a single generic "EOF" error; each case warrants its own error message or handling policy.

Loop pattern for processing untrusted tokens:

```java
while (scanner.hasNext()) {
    if (scanner.hasNextInt(16)) {
        int value = scanner.nextInt(16);
        // process value
    } else {
        String invalidToken = scanner.next();
        // record invalid token / report error to user
    }
}
```

This is an **illustrative snippet**; `scanner` must be declared and initialized by the caller. `hasNext()` checks whether another token exists per delimiter, `hasNextInt(16)` tests parsing without consuming, and `nextInt(16)`/`next()` advances the stream by exactly one token per iteration.

## 7. Delimiters and Decimal Commas Are Two Different Matters

By default, Scanner splits tokens on whitespace. The string `1,5;2,75` **does not automatically** become two German-locale numbers; `;` has not yet been configured as a delimiter.

If the input format uses semicolons to separate fields and commas as decimal points, specify **both the delimiter and the locale**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerSemicolonDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("1,5;2,75")
                .useDelimiter(";")
                .useLocale(Locale.GERMANY)) {
            System.out.println(scanner.nextDouble());
            System.out.println(scanner.nextDouble());
        }
    }
}
```

Run:

```bash
javac ScannerSemicolonDemo.java
java ScannerSemicolonDemo
```

Output (Java `println(double)` prints Java numeric syntax with a dot):

```text
1.5
2.75
```

`useDelimiter(";")` sets **token boundaries**, while `useLocale(Locale.GERMANY)` allows the comma inside each token to act as the decimal separator. If the delimiter were a comma instead, `1,5;2,75` would be split right inside the numeric content, causing the parser to fail or misinterpret values.

In CSV files, commas can appear both inside quoted fields as data and outside as delimiters. `Scanner.useDelimiter(",")` is not a complete CSV parser: it does not understand escaping, commas inside quotes, or embedded newlines inside fields. For real CSV, use a standards-compliant parser; use `Scanner` only when input syntax is simple and well-controlled.

## 8. When You Need Exact Decimals: `BigDecimal`

`nextDouble()` returns an IEEE 754 `double`, which cannot exactly represent decimal values like `0.1`. That is suitable for many scientific computations, yet not the default choice for monetary amounts or domains requiring exact decimal arithmetic.

`Scanner.nextBigDecimal()` parses a locale-conforming floating-point token into `java.math.BigDecimal`, supporting exact decimal arithmetic under `BigDecimal` rules.

Create file **`ScannerBigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Scanner;

public class ScannerBigDecimalDemo {
    public static void main(String[] args) {
        try (Scanner input = new Scanner("1.234,50;2,75")
                .useDelimiter(";")
                .useLocale(Locale.GERMANY)) {
            BigDecimal first = input.nextBigDecimal();
            BigDecimal second = input.nextBigDecimal();
            BigDecimal total = first.add(second);

            System.out.println("first=" + first.toPlainString());
            System.out.println("second=" + second.toPlainString());
            System.out.println("sum=" + total.toPlainString());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ScannerBigDecimalDemo.java
java ScannerBigDecimalDemo
```

Output:

```text
first=1234.50
second=2.75
sum=1237.25
```

`Scanner` recognizes grouping separator `.` and decimal separator `,` under `Locale.GERMANY`. `BigDecimal.toPlainString()` renders the number using decimal digits and a dot, without reusing the original locale's formatting. To output numbers according to regional conventions, format the **output** with an appropriate formatting API (such as `NumberFormat`) and specify the locale explicitly.

Radix does not apply to `nextBigDecimal()`; base does not affect the decimal point or fractional digit count.

## 9. Interaction Between `nextInt()` and `nextLine()`

`nextInt()` reads a **numeric token**, typically stopping before the newline character; `nextLine()` reads **the remainder of the current line**, stripping the line terminator. Therefore, right after `nextInt()`, `nextLine()` can return an empty string.

Example:

```java
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("42\nXin chào\n")) {
            int number = scanner.nextInt();
            String rest = scanner.nextLine();
            String nextLine = scanner.nextLine();

            System.out.println("number=" + number);
            System.out.println("rest empty=" + rest.isEmpty());
            System.out.println("next=" + nextLine);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ScannerLineDemo.java
java ScannerLineDemo
```

Output:

```text
number=42
rest empty=true
next=Xin chào
```

This is a consequence of mixing **token** reading with **line** reading, not a locale or radix bug. If each line represents a record, an alternative is reading the full line with `nextLine()` and creating a separate Scanner for that line string with explicit delimiter, locale, and radix. Avoid mechanically discarding `nextLine()` if the remainder of the line contains data you need to keep.

## 10. Reading Numbers from Files and Charset Issues

If the source is a byte file, **charset** handles converting bytes to text, while **locale/radix** handles converting text tokens to numbers. They are independent:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Scanner;

public class ScanNumbersFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("numbers.txt");

        try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)
                .useLocale(Locale.GERMANY)
                .useRadix(10)) {
            while (scanner.hasNext()) {
                if (scanner.hasNextDouble()) {
                    System.out.println(scanner.nextDouble());
                } else {
                    System.err.println("Token không phải số: " + scanner.next());
                }
            }
        }
    }
}
```

This program is **complete Java 17+ code**, though it requires a `numbers.txt` file in the working directory; since file contents vary, no fixed stdout is shown. `new Scanner(path, StandardCharsets.UTF_8)` specifies the file's charset; `useLocale(Locale.GERMANY)` specifies how decimals/grouping are parsed; `useRadix(10)` only applies to radix-aware **integer** reads and does not alter how `nextDouble()` works.

When opening `Scanner` over `System.in` and closing the Scanner, the underlying standard input stream is also closed; that can break other parts of the application that still need console input. Clarify who owns the resource. For a Scanner created over a `String`, `try-with-resources` is simple and safe.

`Scanner` has strong token-parsing capabilities, yet regular expressions and per-token parsing mean it is rarely the fastest choice for massive datasets. For high-throughput applications, consider reading line by line or byte by byte and parsing with dedicated APIs after benchmarking, while keeping locale and formatting consistent.

## 11. Locale, Radix, Delimiter, and Output Formatting: Quick Comparison

| Requirement | Configuration/API to Focus On | Do Not Confuse With |
| --- | --- | --- |
| Parse `1.234,50` as `1234.5` | `useLocale(Locale.GERMANY)`, `nextDouble()` | `useRadix(10)` |
| Parse `FF` as `255` | `nextInt(16)` or `useRadix(16)` | `useLocale(Locale.US)` |
| Split `1,5;2,75` into two tokens | `useDelimiter(";")` | Charset UTF-8 |
| Preserve exact monetary amounts | `nextBigDecimal()` with right locale | `nextDouble()` summed directly |
| Read bytes of a UTF-8 file | `new Scanner(path, StandardCharsets.UTF_8)` | Number locale |
| Print numbers in a fixed convention | `printf(Locale.ROOT, ...)` or `String.format(locale, ...)` | Scanner's locale |
| Detect invalid tokens | `hasNextInt(radix)`, `hasNextDouble()` | `hasNext()` checking only token existence |

A few common mistakes:

- Letting Scanner use the system locale so data with the same format works on one machine and fails on another.
- Assuming `"1,5"` is always `1.5`: under a locale that does not use a decimal comma, the token may be rejected or parsed differently.
- Setting `useRadix(16)` then calling `nextDouble()` expecting a "base-16 floating-point number."
- Calling `hasNextInt()` repeatedly without consuming the bad token when it returns `false`: the loop stalls indefinitely in one spot.
- Calling `nextInt()` on a number outside `int` range and assuming the token contains letters; check both radix and value bounds.
- Reading tokens and then calling `nextLine()` without accounting for the remainder of the line.
- Using a comma delimiter for text where commas belong inside decimal numbers.
- Using `Double.parseDouble(...)` as a locale-aware Scanner substitute: `Double.parseDouble` accepts Java's locale-independent numeric syntax, so `"1,5"` does not become `1.5` just because the machine locale is German.

**Self-practice exercise:** Given text `"1.234,50;FF;1011"`. Set delimiter `;`, use `Locale.GERMANY` to read the first token via `nextBigDecimal()`, followed by `nextInt(16)` and `nextInt(2)`. The expected values in order are **`1234.50`, `255`, `11`**. Explain why changing locale without setting the delimiter is insufficient.

**Key takeaway:** When using `Scanner` to read numbers, define **three distinct layers**: delimiter splits tokens, locale interprets punctuation and number notation, and radix interprets integer digits. Configure all three according to the data contract, validate tokens before consuming, and specify a separate charset when the source is bytes.
