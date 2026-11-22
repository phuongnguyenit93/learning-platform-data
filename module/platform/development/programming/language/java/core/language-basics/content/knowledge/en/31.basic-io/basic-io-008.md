# Validating Input and Converting Strings to Numbers — Java 17+

## 1. Why validate both before and after type conversion?

Data a program receives from the keyboard, files, or command line usually starts out as a **string**. Even when the user types `25`, the value read via `BufferedReader.readLine()` or `Scanner.nextLine()` still has type `String`. To add, multiply, or compare against limits, you need to **convert the string into a numeric type** and **validate the data**.

Three steps that must not be confused with each other:

1. **Read the data:** obtain the string entered by the user, e.g. `"12"`.
2. **Convert the type (parse):** use `Integer.parseInt("12")` to obtain the integer `12`; this step can fail if the string has an invalid format or exceeds the type's range.
3. **Check constraints (validation):** confirm the value belongs to the business domain, e.g. quantity `1..100`. Successfully parsing `"0"` to `0` does not mean a quantity of 0 is permitted.

~~~text
Input string
    |
    v
Check missing/empty, normalize appropriately
    |
    v
Convert to number (parse)
    |             \
    |              \ format error / out of type range
    v               v
Check business      Appropriate error message
domain
    |             \
    v              \ out of domain
Use valid number     Appropriate error message
~~~

The goal is to **prevent bad data from propagating into calculations**, while providing a specific message so the user can fix the input.

## 2. Reading a line from stdin

In Java 17, you can use `BufferedReader` to receive a line verbatim:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = reader.readLine();
~~~

- `System.in` is the standard input stream (stdin).
- `InputStreamReader` converts bytes to characters; specifying `StandardCharsets.UTF_8` ensures consistent encoding.
- `BufferedReader.readLine()` reads one line, removes the line terminator, and returns a `String`.
- If **end of data** is reached before reading a line, `readLine()` returns **`null`**.
- I/O operations can throw the checked `IOException`, so the method must catch it or declare `throws IOException`.

When the user **simply presses Enter**, `readLine()` returns `""` (empty string), which **differs** from `null` at EOF. Input containing only whitespace like `"   "` is a string with non-zero length yet may be considered "no content" after normalization.

~~~java
if (line == null) {
    System.out.println("Missing line (EOF)");
} else if (line.isBlank()) {
    System.out.println("Empty or whitespace-only line");
}
~~~

This is illustrative code placed after `line` has been read; the standalone runnable program is in section 9.

## 3. Normalizing strings before parsing

`String.strip()` (Java 11+) removes leading and trailing whitespace characters according to the Unicode rules supported by the API. If the contract permits leading/trailing whitespace:

~~~java
String raw = " 42 ";
String normalized = raw.strip();
int number = Integer.parseInt(normalized);
System.out.println(number);
~~~

**Exact stdout:**

~~~text
42
~~~

You must check for `null` before calling `strip()`. An empty string `""` or whitespace-only string will not parse into a number with `Integer.parseInt`; report a "required field" error first so the user understands, rather than showing a confusing technical error.

**Do not alter every string arbitrarily:** for example, financial rules or identifiers may strictly define whether spaces may be stripped or a leading plus sign is accepted. Normalization must follow the **input contract**.

## 4. Converting strings to `int` and `long`

Common APIs:

~~~java
int age = Integer.parseInt("21");
long population = Long.parseLong("9000000000");

System.out.println(age);
System.out.println(population);
~~~

**Exact stdout:**

~~~text
21
9000000000
~~~

`Integer.parseInt(String)` accepts strings representing integers in the range **`-2147483648..2147483647`**; `Long.parseLong` accepts `long` integers with a larger range. Both can throw the **unchecked `NumberFormatException`** when the string does not represent a valid number of that type.

Examples:

| String passed to `Integer.parseInt` | Result |
|---|---|
| `"15"` | `15` |
| `"-8"` | `-8` |
| `"+9"` | `9` |
| `"0012"` | `12` |
| `"3.5"` | `NumberFormatException` |
| `"ten"` | `NumberFormatException` |
| `"2147483648"` | `NumberFormatException` due to exceeding `int` range |
| `" 12 "` | Not parsed directly; requires `strip()` if the contract permits |

If you need to **accept only ASCII digits**, signs or special formats must be specified and checked explicitly. Automatic numeric parsing does not replace system format validation.

Exception-handling pattern:

~~~java
try {
    int quantity = Integer.parseInt(text.strip());
    System.out.println("quantity=" + quantity);
} catch (NumberFormatException ex) {
    System.out.println("quantity must be an integer");
}
~~~

This snippet assumes `text` is not `null`; the complete example handles EOF/blank input before parsing.

## 5. Converting floating-point numbers: `double` and `BigDecimal`

Converting to a floating-point number:

~~~java
double rate = Double.parseDouble("2.5");
System.out.println(rate);
~~~

**Exact stdout:**

~~~text
2.5
~~~

`Double.parseDouble` understands scientific notation like `"1e3"` and also accepts special values like `"NaN"` or `"Infinity"`. If the contract only accepts **finite** numbers, check additionally:

~~~java
double value = Double.parseDouble(text.strip());
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("value must be finite");
}
~~~

You also need to check the allowed range, such as `0.0 <= value && value <= 1.0`.

### When exact decimal representation is needed

For **prices, totals, or unit prices** requiring consistent decimal representation, `BigDecimal` is generally more suitable than `double`:

~~~java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("12.50");
BigDecimal total = price.multiply(BigDecimal.valueOf(3));
System.out.println(total.toPlainString());
~~~

**Exact stdout:**

~~~text
37.50
~~~

Avoid `new BigDecimal(0.1)` when you want the exact decimal value `0.1`, because `double` does not store that value accurately in binary. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` depending on your intent.

**Important:** `BigDecimal` handles **already-parsed** decimal numbers accurately, yet it does not automatically confirm a "valid price." You still must constrain the range, number of decimal places, unit, and rounding rules. The sample program only allows prices with at most **two digits after the decimal point**, strictly positive and within the upper limit.

## 6. Number formats and separators

Users might enter:

~~~text
12.50
12,50
1 000
1,000
1e3
~~~

These strings are **not automatically equivalent**. For example, `new BigDecimal("12,50")` cannot be parsed directly. In the example in section 9, the price follows a fixed contract:

- Uses only **ASCII digits `0..9`** and a **dot `.`** for the fractional part.
- Allows whole numbers like `"12"` or numbers with 1–2 decimal places like `"12.5"` and `"12.50"`.
- Rejects commas, internal spaces, currency symbols, exponents, and negative numbers.
- **Leading and trailing** whitespace is removed via `strip()`.
- After parsing, it must be greater than `0` and at most `1_000_000`.

Java format-checking expression:

~~~java
boolean validFormat = normalized.matches("[0-9]+(\\.[0-9]{1,2})?");
~~~

In a Java string literal, `\\.` represents a literal dot in regex; the dot is escaped so it does not mean "any character." Using a single uniform format rule keeps the code from guessing whether `12,50` means twelve point five or a list of two values.

If an application supports multiple locales, choose a parser for a specific `Locale` (such as `NumberFormat`/`DecimalFormat`) with a clear contract and verify that the **entire valid string was consumed**. Do not assume comma/decimal input conventions are identical across operating systems.

## 7. Distinguishing syntax errors, type overflows, and business domain errors

These three error categories require distinct handling:

| Error group | Examples | How to handle |
|---|---|---|
| Missing data | EOF before quantity; empty string | Report a required-field error |
| Cannot convert to numeric type | `"abc"`, `"2.5"` for `int`, value too large for `int` | Catch `NumberFormatException` or validate syntax first |
| Syntactically valid number, out of domain | `0` for quantity requiring `1..100`; price `0.00` | Throw or return a validation error with a dedicated message |

Do not use `assert quantity > 0` to check required input: `assert` statements can be disabled when running the JVM. Use regular `if` conditions that always execute.

~~~java
static int validateQuantity(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("quantity is required");
    }

    final int quantity;
    try {
        quantity = Integer.parseInt(input.strip());
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "quantity must be an integer", ex);
    }

    if (quantity < 1 || quantity > 100) {
        throw new IllegalArgumentException("quantity must be 1..100");
    }
    return quantity;
}
~~~

With `"abc"`, the error comes from parsing; with `"0"`, parsing succeeds yet domain validation fails. When invalid data is detected, **stop the current computation** rather than continuing with a guessed default or silently "fixing" the data.

## 8. Choosing a consistent input-reading approach

When a problem requires validating **one field per line**, `Scanner.nextLine()` combined with `Integer.parseInt` or `BigDecimal(String)` separates three responsibilities: reading text, converting types, and validating bounds. With a source that may end early, check `hasNextLine()` before reading.

`nextInt()` reads by token, so calling `nextLine()` afterward may read the remainder of the number line; it also uses `Scanner`'s syntax/locale rules and can throw `InputMismatchException` instead of `Integer.parseInt`'s `NumberFormatException`. Since this chapter builds a strict validator, the complete example chooses `BufferedReader.readLine()` and handles EOF explicitly.

## 9. Complete Java 17+ program: entering quantity and unit price

The example reads **two lines from stdin**:

1. Integer quantity, from **1 to 100**.
2. Decimal unit price, **greater than 0 up to 1_000_000**, using a dot `.`, with at most 2 decimal places.

The program computes `quantity × unitPrice` using `BigDecimal`, normalizes output to two decimal places, rejects missing/invalid input, and returns exit status **2** when invalid.

Save as **`InputNumberValidationDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;

public final class InputNumberValidationDemo {
    private InputNumberValidationDemo() {}

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("quantity is required");
        }

        final int value;
        try {
            value = Integer.parseInt(raw.strip());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", ex);
        }

        if (value < 1 || value > 100) {
            throw new IllegalArgumentException("quantity must be 1..100");
        }
        return value;
    }

    static BigDecimal parsePrice(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("price is required");
        }

        String normalized = raw.strip();
        if (!normalized.matches("[0-9]+(\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException(
                    "price must use digits and optional dot with 1-2 decimals");
        }

        final BigDecimal price;
        try {
            price = new BigDecimal(normalized);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "price must be a decimal number", ex);
        }

        if (price.compareTo(BigDecimal.ZERO) <= 0
                || price.compareTo(new BigDecimal("1000000")) > 0) {
            throw new IllegalArgumentException(
                    "price must be > 0 and <= 1000000");
        }

        return price.setScale(2, RoundingMode.UNNECESSARY);
    }

    static int run(BufferedReader reader) throws IOException {
        System.out.println("quantity?");
        String quantityLine = reader.readLine();
        if (quantityLine == null) {
            System.out.println("error: quantity is missing");
            return 2;
        }

        final int quantity;
        try {
            quantity = parseQuantity(quantityLine);
        } catch (IllegalArgumentException ex) {
            System.out.println("error: " + ex.getMessage());
            return 2;
        }

        System.out.println("price?");
        String priceLine = reader.readLine();
        if (priceLine == null) {
            System.out.println("error: price is missing");
            return 2;
        }

        final BigDecimal unitPrice;
        try {
            unitPrice = parsePrice(priceLine);
        } catch (IllegalArgumentException ex) {
            System.out.println("error: " + ex.getMessage());
            return 2;
        }

        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(quantity));
        System.out.println("quantity=" + quantity);
        System.out.println("unitPrice=" + unitPrice.toPlainString());
        System.out.println("total=" + total.toPlainString());
        System.out.println("status=OK");
        return 0;
    }

    public static void main(String[] args) {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));

        int status;
        try {
            status = run(reader);
        } catch (IOException ex) {
            System.out.println("error: input unavailable");
            status = 2;
        }

        if (status != 0) {
            System.exit(status);
        }
    }
}
~~~

**Technical explanation:**

- The two `readLine()` calls read strings; the program checks EOF separately to distinguish it from a blank line.
- `parseQuantity` catches `NumberFormatException` from `Integer.parseInt` and translates it into a clear message, while also checking the `1..100` range.
- `parsePrice` checks format first, constructs `BigDecimal` from the string, compares values with `compareTo`, and calls `setScale(2, RoundingMode.UNNECESSARY)`. Because the input has at most two decimal digits, setting scale does not round numbers; it normalizes output, such as turning `12.5` into `12.50`.
- Error branches return code `2` from `run` without computing the total when input is invalid.
- `System.exit(2)` belongs at the **application boundary**. Do not call `System.exit` inside a parsing utility; libraries should let callers decide how errors are handled.
- Messages in the example print to stdout for straightforward matching. Production CLIs usually print errors to `System.err`.

### Compiling

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 InputNumberValidationDemo.java
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\InputNumberValidationDemo.java
~~~

No Maven/Gradle, external libraries, or preview features needed. Run in the directory containing the compiled `.class` file.

### Case 1 — valid data

**Bash:**

~~~bash
printf '3\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("3", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
quantity=3
unitPrice=12.50
total=37.50
status=OK
~~~

This case returns **exit status 0**.

### Case 2 — quantity is not an integer

**Bash:**

~~~bash
printf 'abc\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("abc", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
error: quantity must be an integer
~~~

The program does not read the unit price after rejecting the quantity; **exit status 2**.

### Case 3 — parsed as a number but out of range

**Bash:**

~~~bash
printf '0\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("0", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
error: quantity must be 1..100
~~~

`"0"` parses as an integer successfully, yet violates the `1..100` business domain. **Exit status 2**.

### Case 4 — invalid format using a comma

**Bash:**

~~~bash
printf '2\n12,50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("2", "12,50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price must use digits and optional dot with 1-2 decimals
~~~

The price format is defined to use `.`, rejecting `,`. **Exit status 2**.

### Case 5 — price equals 0

**Bash:**

~~~bash
printf '2\n0.00\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("2", "0.00") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price must be > 0 and <= 1000000
~~~

`"0.00"` matches the format and parses to `BigDecimal`, yet violates the rule that **price must be greater than 0**; **exit status 2**.

### Case 6 — end of data before entering price

**Bash:**

~~~bash
printf '2\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
"2" | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price is missing
~~~

End of input causes the second `readLine()` to return `null`; the program reports a missing field instead of assuming `0`. **Exit status 2**.

## 10. Common mistakes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Assuming `readLine()` returns a converted number | The API returns `String` or `null` | Call parse after checking the input |
| Calling `null.strip()` at EOF | `NullPointerException` | Check for `null` first |
| Treating an empty string as 0 | Easily fabricates bogus data | Distinguish missing data from an actual 0 |
| Parsing `"abc"` without error handling | `NumberFormatException` | Catch the right exception or report the error |
| Parsing `"2147483648"` with `int` and assuming validity | Exceeds `int` range | Use an appropriate type and check range |
| `int n = Integer.parseInt(s);` without checking `n` | `n` may be 0, negative, or past business limits | Validate the domain after parsing |
| Using `double` for money totals expecting exact decimal precision | Floating-point binary rounding can occur | Use `BigDecimal` and explicit scale/rounding rules |
| Assuming `Double.parseDouble("NaN")` is a valid finite number | NaN is a special value | Check `Double.isFinite` if required by the contract |
| Assuming `12,50` always parses like `12.50` | Parsers and locales differ | Choose a clear format and validate it |
| Using `==` to compare input strings | `==` compares reference identity | Use `equals` or parse as a number |
| Mixing `Scanner.nextInt()` with `nextLine()` without handling line remainder | Can read unexpected empty strings | Use `nextLine()` + parse or consume the line properly |
| Using `assert` to validate required input | Assertions can be disabled | Use always-on `if`/throw/validation logic |
| Swallowing `NumberFormatException` and silently using 0 | Hides invalid data | Report the error or re-prompt per contract |
| Confusing syntax errors with domain errors | Two distinct issues needing separate handling | Parse first, validate domain afterward |

## 11. Exercises and answers

**A.** Given `String s = " 18 ";`, how do you convert it to `int` if leading and trailing whitespace is allowed?

**Answer:**

~~~java
int n = Integer.parseInt(s.strip()); // 18
~~~

**B.** What does `Integer.parseInt("2.5")` return?

**Answer:** it throws `NumberFormatException` because `2.5` does not represent a valid `int` integer.

**C.** If quantity is `0` and `Integer.parseInt("0")` succeeds, is the data valid yet?

**Answer:** **No**. The example contract requires `1..100`, so quantity 0 must be rejected by validation.

**D.** If you need exact decimal values to calculate prices, should you use `new BigDecimal("12.50")` or `new BigDecimal(12.50)`?

**Answer:** prefer `new BigDecimal("12.50")` when the input is a validated decimal string; avoid constructing from `double` due to binary floating-point precision.

**E.** When does `BufferedReader.readLine()` return `null`?

**Answer:** when EOF is reached before reading a line, unlike `""` when reading a blank line.

**F.** Why is `Double.parseDouble("NaN")` insufficient to validate a measurement required to be finite?

**Answer:** `NaN` is a special `double` value; check `Double.isFinite` and the appropriate domain range.

**G.** For what reason is `12,50` rejected by the example?

**Answer:** a **format** error: the unit price contract requires ASCII digits and a dot `.` decimal separator, not a comma.

**H.** With `2` and `12.50`, what is the total according to the example?

**Answer:** `25.00` because `2 × 12.50 = 25.00`.

## 12. Checklist and conclusion

- [ ] Know that input from `readLine()`/`nextLine()` is a string requiring conversion.
- [ ] Distinguish EOF (`null`), empty strings, and whitespace-only strings.
- [ ] Check for `null` before normalizing with `strip()`.
- [ ] Use `Integer.parseInt` and `Long.parseLong` for integers.
- [ ] Understand `NumberFormatException` and numeric type bounds.
- [ ] Know `Double.parseDouble` and check for finite values when needed.
- [ ] Know how to use `BigDecimal` from `String` for exact decimal arithmetic.
- [ ] Choose rules for decimal separators, whitespace, and digit counts per contract.
- [ ] Check business domain bounds after the parse step.
- [ ] Do not use `assert` or arbitrary default values to replace validation.
- [ ] Understand the trap of mixing `Scanner.nextInt()` and `nextLine()`.
- [ ] Read and understand error messages and exit statuses in CLIs.
- [ ] Run `InputNumberValidationDemo.java` on JDK 17+ for both valid and invalid cases, verifying stdout.

**Conclusion:** **Reading a string, converting it to a number, and validating the data** are three distinct yet sequential steps. A robust Java program must handle missing input, syntax errors, and out-of-range values while choosing numeric types suited to the domain. Perform calculations only after all required checks have succeeded.