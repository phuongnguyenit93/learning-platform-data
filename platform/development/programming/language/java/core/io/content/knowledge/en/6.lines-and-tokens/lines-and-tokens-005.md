# Scanner in Java: Data Sources, Delimiters, and Tokens

## 1. What Problem Does Scanner Solve?

When receiving a piece of text like `"Lan 21 8.5"`, an application usually does not want to just read character by character: it wants to extract the **name**, **age**, and **score**. `java.util.Scanner` helps split input into **tokens** (units of text) according to a delimiter rule, then read tokens as `String` or convert them into types such as `int`, `double`, and `boolean`.

Example data:

~~~text
Lan 21 8.5
~~~

If whitespace is used as the delimiter, the resulting token stream is:

~~~text
Source:   L a n [space] 2 1 [space] 8 . 5
                   │               │
                   ▼               ▼
Token 1: "Lan"  Token 2: "21"  Token 3: "8.5"
~~~

`Scanner` does not only accept in-memory strings; it can also read content from files, `InputStream`, `Readable`, and other sources supported by the API. When using `Scanner` over real I/O, searching for tokens **can block** while waiting for enough data or a delimiter.

This lesson focuses on three directly related questions:

1. What is `Scanner`'s **data source**, how is it decoded into characters, and who must close the resource?
2. What boundaries does the **delimiter** (separating expression) define, and which regex rules govern it?
3. How are **tokens** recognized, checked, and consumed? When should you read tokens versus reading full lines?

The first point to keep in mind: **Scanner is a token-based text parser**. It is not the default tool for every file format or every data protocol.

## 2. The Scanner Model: source → decoding → delimiter → token → value

~~~text
Source
  ├─ In-memory String
  ├─ Pre-created Reader
  ├─ InputStream (bytes) + charset
  └─ Path/File + charset
            │
            ▼
  Read/decoded text
            │
            ▼
  Delimiter rule (Pattern / regex)
            │
            ▼
  Sequence of tokens:  "Lan" | "21" | "8.5"
            │
            ├─ next()       → String
            ├─ nextInt()    → int, if valid
            ├─ nextDouble() → double, if valid per Locale
            └─ next(...)    → String matching the requested pattern
~~~

Do not mix up these layers:

- **Source** specifies where the data lives and how it is supplied.
- **Charset** specifies the rule by which bytes from the source are converted into characters, when the source is bytes.
- **Delimiter** specifies where to split tokens in the character sequence already read.
- **Target data type** specifies whether a token is interpreted as a number, boolean, or text.

Changing the delimiter **does not change the charset**; changing the Scanner's `Locale` for parsing numbers **does not change the charset**. For example, UTF-8 determines how `"Đà Nẵng"` is decoded from bytes; `Locale.GERMANY` determines how `nextDouble()` interprets the decimal comma in `"3,5"`.

## 3. Scanner Data Sources

### 3.1. String: Learning and Testing Without I/O

`new Scanner(String source)` creates a Scanner reading from existing string content. This is a good choice for testing delimiters and token rules because the data is deterministic and does not depend on files.

**Standalone runnable example**, save as `ScannerStringDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerStringDemo {
    public static void main(String[] args) {
        String source = "  Java\t17\nI/O  ";

        try (Scanner scanner = new Scanner(source)) {
            while (scanner.hasNext()) {
                System.out.println("[" + scanner.next() + "]");
            }
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 ScannerStringDemo.java
java ScannerStringDemo
~~~

Output:

~~~text
[Java]
[17]
[I/O]
~~~

By default, Scanner uses **whitespace** as its delimiter, including spaces, tabs, and newlines recognized according to Java's whitespace rules. It skips leading delimiters before a token, so it does not produce tokens for each consecutive whitespace character in the example above.

### 3.2. From InputStream: Bytes Must Be Decoded

An `InputStream` supplies bytes, whereas Scanner processes characters. Specify the charset explicitly:

~~~java
Scanner scanner = new Scanner(inputStream, StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet**, assuming `inputStream` is already open; required imports are `java.util.Scanner` and `java.nio.charset.StandardCharsets`. The constructor taking `Charset` is available in Java 17. The source class might be `FileInputStream` or another byte source. Determine which party owns closing `inputStream` before closing the Scanner.

Without an explicit charset, decoding can depend on environment configuration or the Java version's API. For data exchanged across machines, use the charset specified by the data format, typically UTF-8.

### 3.3. From Reader: Receiving Already-Decoded Characters

`new Scanner(Reader)` fits when another component already created a `Reader` or when attaching Scanner to an I/O wrapper chain:

~~~java
Scanner scanner = new Scanner(reader);
~~~

This is an illustrative snippet with an existing `reader`. If `reader` was created via `Files.newBufferedReader(path, UTF_8)`, converting bytes to characters already happens inside the Reader. Scanner applies delimiters to the **received characters**, not as regex over raw UTF-8 bytes.

### 3.4. From Path/File: Choose Charset and Manage Lifecycle

You can create a Scanner from a `Path` together with a `Charset`:

~~~java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    while (scanner.hasNext()) {
        String token = scanner.next();
        // Process token.
    }
}
~~~

This is an illustrative snippet: `path` has type `java.nio.file.Path`; the enclosing method must declare or handle the appropriate I/O exception. `Scanner` opens the file resource and `try-with-resources` closes it when finished.

Another valid approach is:

~~~java
try (Scanner scanner = new Scanner(
        Files.newBufferedReader(path, StandardCharsets.UTF_8))) {
    // Read data.
}
~~~

These snippets require importing `java.util.Scanner`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`. When Scanner closes, if its source implements `Closeable`, Scanner closes that source; therefore, do not inadvertently close a `Reader` or `InputStream` still owned by another component.

### 3.5. From System.in: Process-Wide Shared Stream

Reading console input can use:

~~~java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
~~~

If a command-line program uses `System.in` throughout its lifetime, keep the corresponding Scanner for the entire session. **Closing the Scanner closes `System.in`** because the source is a closeable `InputStream`; a library or short helper method should not close this shared resource if other parts of the program still need input.

General ownership rule: the component that creates the source and hands ownership to Scanner may let Scanner close it; if merely borrowing a source from a caller, document the closing contract clearly or use another API to avoid unintended closing.

## 4. What Is a Delimiter?

A delimiter is a **regular expression (regex) pattern** indicating the text spans that separate tokens. Initially, Scanner uses a pattern that matches whitespace.

Suppose the input is:

~~~text
An, Bình; Chi
~~~

With the default delimiter, only whitespace counts as a boundary, so you get tokens `"An,"`, `"Bình;"`, and `"Chi"`. The comma and semicolon remain inside the tokens.

If you want both commas and semicolons to separate names, change the delimiter, for example `\\s*[,;]\\s*`:

- `[,;]`: matches **one** comma or semicolon.
- `\\s*`: matches **zero or more** whitespace characters on either side of the separator.
- This pattern splits names on a comma or semicolon, optionally surrounded by whitespace.

In a **Java string**, regex backslashes must be escaped. The Java string representing regex `\s*` here must be written `"\\s*"` (two backslashes in Java code before `s`). Careful: since Java 15, `\s` in a Java string literal is an escape for a single space, so writing `"\s*"` is not equivalent to the whitespace regex `"\\s*"`.

### 4.1. Changing the Delimiter with useDelimiter

Save as `ScannerDelimiterDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerDelimiterDemo {
    public static void main(String[] args) {
        String source = "An, Bình; Chi";

        try (Scanner scanner = new Scanner(source)) {
            scanner.useDelimiter("\\s*[,;]\\s*");

            while (scanner.hasNext()) {
                System.out.println("<" + scanner.next() + ">");
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerDelimiterDemo.java
java ScannerDelimiterDemo
~~~

Output:

~~~text
<An>
<Bình>
<Chi>
~~~

`useDelimiter(String pattern)` compiles the string into a regex pattern. You can use `useDelimiter(Pattern)` when you already have a precompiled `java.util.regex.Pattern`. `scanner.delimiter()` returns the delimiter pattern currently in use.

A delimiter does not have to be **a single character**: it can be a multi-character separator (such as `"::"`), repeated characters, or a regex-matched construct. However, the more complex it becomes, the more carefully you must account for regex metacharacters and empty-string matches.

### 4.2. Regex Has Special Characters

Several characters have special meaning in regex:

| Desired separator | Regex required | Java string passed to useDelimiter |
| --- | --- | --- |
| Comma | `,` | `","` |
| Semicolon | `;` | `";"` |
| Literal period (dot) | `\\.` | `"\\."` |
| Literal vertical bar (pipe) | `\\|` | `"\\|"` |
| One or more whitespace characters | `\\s+` | `"\\s+"` |
| Comma or semicolon with surrounding whitespace | `\\s*[,;]\\s*` | `"\\s*[,;]\\s*"` |

An unescaped `.` means "any character" in most regex modes; an unescaped `|` represents alternation. Thus `useDelimiter(".")` or `useDelimiter("|")` usually does not mean "split on literal dots or pipes."

If the delimiter is a **literal** character sequence coming from configuration, use `Pattern.quote(delimiter)` to avoid treating it as regex accidentally:

~~~java
String separator = "|";
scanner.useDelimiter(java.util.regex.Pattern.quote(separator));
~~~

This is an illustrative snippet assuming `scanner` already exists. `Pattern.quote` cleanly represents a **fixed delimiter string**; for a deliberately designed regex rule, pass the regex pattern itself.

### 4.3. Empty Delimiters or Patterns That Can Match Zero Length

Regexes such as `""`, `"\\s*"`, or lookarounds can match at empty positions. Such patterns can produce unexpected tokens—even turning every single character into a token—and make parsing unpredictable.

If you want to separate on **at least one** whitespace character, use `"\\s+"` instead of `"\\s*"`. Only use a regex capable of matching empty text once you understand Scanner's rules and have tests for leading/trailing strings, repeated delimiters, Unicode, and empty input.

## 5. What Is a Token and How Does Scanner Consume Tokens?

Given a delimiter, a token is essentially **the text segment between delimiter matches** detected by Scanner. `next()` retrieves the next token and **advances the read position**. `hasNext()` checks whether another token exists **without consuming** it.

Example:

~~~java
try (Scanner scanner = new Scanner("red blue")) {
    System.out.println(scanner.hasNext());
    System.out.println(scanner.hasNext());
    System.out.println(scanner.next());
    System.out.println(scanner.next());
    System.out.println(scanner.hasNext());
}
~~~

This is a small runnable snippet inside a method declaring `throws Exception` or an appropriate Java context supporting `try-with-resources`. To run standalone, place it inside a class with `main` and `import java.util.Scanner`.

Output:

~~~text
true
true
red
blue
false
~~~

The first two `hasNext()` calls both see the same token `red`; only `next()` consumes the token and advances the position.

Do not call `next()` blindly when the source is exhausted: it throws `NoSuchElementException`. `hasNext()` may block while Scanner waits for more input from a live source. A common loop:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
    // Process token.
}
~~~

This is an illustrative snippet with an existing `scanner`. Each iteration consumes exactly one token. Omitting `scanner.next()` while looping only on `hasNext()` causes the program to make no progress.

### 5.1. hasNext(Pattern) and next(Pattern)

`hasNext(pattern)` checks whether the next token matches the specified pattern without consuming it. `next(pattern)` retrieves the next token if it matches; if not, it throws `InputMismatchException`.

The pattern in `next(Pattern)` / `hasNext(Pattern)` applies to the **entire token** under Scanner's matching contract, rather than merely searching for an arbitrary substring.

Example:

~~~java
scanner.hasNext("[A-Za-z]+"); // Does the next token consist of ASCII letters?
scanner.hasNext("\\d+");      // Does the next token consist of one or more digits?
~~~

This is an illustrative snippet. For the token `"id42"`, neither expression matches the whole token. If you need to find a text segment **inside** a line, look at search methods like `findInLine` or use a `Matcher` on a line `String` already read; do not force `next(regex)` to act as a substring finder.

### 5.2. Tokens Are Not Lines

The default delimiter treats newlines as whitespace, so two lines:

~~~text
Hoa 18
Nam 20
~~~

become four tokens `Hoa`, `18`, `Nam`, `20`. Scanner does not automatically retain the fact that the first two tokens came from the first line if the application only calls `next()`.

When **line** boundaries carry business meaning, consider `hasNextLine()` / `nextLine()` and then parsing each line individually, or use `BufferedReader`. Do not assume every two tokens form one line if the source might have blank columns, quotes, or complex structure.

## 6. Relationship Between next() and nextLine(): A Very Common Pitfall

`next()` reads a token using the active delimiter. `nextInt()` and `nextDouble()` also read one token and parse its value. `nextLine()` behaves differently: it reads the remainder of the **current line**, excluding the line terminator, and advances Scanner's position to the next line.

After `nextInt()`, the trailing newline at the end of that line has not yet been consumed by `nextLine()`. If you call `nextLine()` immediately, you typically receive an **empty string** when no characters remain between the number and the newline.

Standalone runnable example: `ScannerLinePitfallDemo.java`

~~~java
import java.util.Scanner;

public class ScannerLinePitfallDemo {
    public static void main(String[] args) {
        String input = "42\nNguyen Van A\n";

        try (Scanner scanner = new Scanner(input)) {
            int age = scanner.nextInt();
            String restOfNumberLine = scanner.nextLine();
            String name = scanner.nextLine();

            System.out.println("Age: " + age);
            System.out.println("Remaining chars: " + restOfNumberLine.length());
            System.out.println("Name: " + name);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerLinePitfallDemo.java
java ScannerLinePitfallDemo
~~~

Output:

~~~text
Age: 42
Remaining chars: 0
Name: Nguyen Van A
~~~

With input that has other characters after the number on the **same line**, `nextLine()` returns those remaining characters rather than necessarily returning an empty string. Do not call `nextLine()` mechanically "to clear the buffer": that call **consumes the rest of the current line** and can discard useful data.

Two clear strategies:

- **Token-oriented problems:** consistently use `hasNext`/`next`/`nextInt` when the format genuinely consists of tokens.
- **Line-oriented form problems:** use `nextLine()` to fetch each line, then parse with `Integer.parseInt(line.strip())` or create a dedicated Scanner per line. This keeps line boundaries explicit.

Another easy point of confusion: `scanner.useDelimiter(",")` changes the token separator to a comma, yet `nextLine()` still looks for line boundaries per its contract; it **does not turn into "read up to the comma"**.

## 7. Parsing Numbers: Delimiter and Locale Are Two Different Rules

`nextInt()`, `nextLong()`, `nextDouble()`, and similar methods perform two steps:

1. Identify the **token** using the delimiter.
2. Interpret the **token's content** using the data type's grammar, radix, and appropriate `Locale`.

Decimal separators and digit grouping separators can depend on `Locale`. Therefore, token `"3,5"` may represent `3.5` under one locale and be invalid or mean something else under another. Set `Locale` explicitly for fixed numeric formats.

Standalone runnable example, `ScannerLocaleDemo.java`:

~~~java
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleDemo {
    public static void main(String[] args) {
        try (Scanner scanner =
                     new Scanner("17 3,5 yes").useLocale(Locale.GERMANY)) {
            int count = scanner.nextInt();
            double value = scanner.nextDouble();
            String flag = scanner.next();

            System.out.println("Count: " + count);
            System.out.println("Value: " + value);
            System.out.println("Flag: " + flag);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerLocaleDemo.java
java ScannerLocaleDemo
~~~

Output:

~~~text
Count: 17
Value: 3.5
Flag: yes
~~~

`Scanner` parses `3,5` under `Locale.GERMANY` into the double value `3.5`. When printing via `System.out.println(double)`, Java uses its standard string representation with a dot; printing numbers with `println` does not inherit the Scanner's locale.

### 7.1. Example with Comma Separators and Decimal Commas

Suppose a format separates tokens with commas, while a numeric value also contains a locale-dependent decimal comma. You cannot use `useDelimiter(",")` and expect Scanner to guess which comma separates columns and which comma belongs to a number.

**The delimiter resolves token boundaries; the Locale resolves the meaning of an extracted token**. If both rules use the same symbol, you need a format with explicit quoting/escaping rules (such as standard CSV) or a different separator character. Scanner with a simple delimiter regex is not a full CSV parser.

### 7.2. hasNextInt() Does Not Consume an Invalid Token

When `hasNextInt()` returns `false`, the next token is still waiting in the input. Looping to check it without processing/consuming it prevents the program from advancing.

Example `ScannerValidationDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerValidationDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("12 wrong 34")) {
            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    System.out.println("Number: " + scanner.nextInt());
                } else {
                    System.out.println("Skipped: " + scanner.next());
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerValidationDemo.java
java ScannerValidationDemo
~~~

Output:

~~~text
Number: 12
Skipped: wrong
Number: 34
~~~

`hasNextInt()` checks the syntax and `int` range per Scanner's grammar. If a token does not conform, `nextInt()` throws `InputMismatchException`; the offending token **is not automatically discarded**. In a real application, depending on requirements, you can halt to report a contextual error or consume the invalid token to recover.

## 8. Delimiters Can Completely Change Tokenization

Consider the string:

~~~text
A|B C|D
~~~

Different configurations produce different parses:

| Delimiter | Tokens Detected |
| --- | --- |
| Default (whitespace) | `A|B`, `C|D` |
| `"\\|"` | `A`, `B C`, `D` |
| `"[\\s|]+"` | `A`, `B`, `C`, `D` |

Because `|` is a special regex character, splitting on a literal vertical bar requires escaping like `"\\|"` or using a character class `"[|]"`. In `"[\\s|]+"`, the `|` inside the character class has literal meaning.

**Do not strip whitespace automatically** when spaces are a meaningful part of the token. For example, `"Hà Nội|Việt Nam"` with a pipe delimiter should produce two tokens `"Hà Nội"` and `"Việt Nam"`; adding `\\s+` to the delimiter would unexpectedly split them into four tokens.

### 8.1. Empty Tokens, Consecutive Delimiters, and Quotes

A simple split regex cannot represent every format with empty fields or quoting. For data like:

~~~text
a,,c
~~~

you may need to interpret this as three fields where the second field is empty. However, requirements to preserve empty fields accurately **should not be left** to casual tokenization logic without testing delimiter behavior and leading/trailing boundaries. For in-memory strings with a simple separator, `String.split(",", -1)` is one option that preserves trailing empty fields when field-level parsing is genuinely required.

For CSV data such as:

~~~text
"Nguyễn, An",21,"Hà Nội"
~~~

the comma inside the quoted name **is not a column separator**. `scanner.useDelimiter(",")` will split it incorrectly. CSV also involves quote-escaping rules, embedded newlines in cells, and many edge cases. When true CSV compliance is required, use a dedicated format-compliant CSV parser rather than a single regex.

## 9. Parsing Tokens by Data Pattern

`next(String pattern)` and `next(Pattern pattern)` retrieve the next token only if it matches the pattern; they can be useful when data has well-defined token shapes.

Example `ScannerPatternDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerPatternDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("abc 123 x9")) {
            while (scanner.hasNext()) {
                if (scanner.hasNext("[A-Za-z]+")) {
                    System.out.println("WORD: " + scanner.next());
                } else if (scanner.hasNext("\\d+")) {
                    System.out.println("NUMBER: " + scanner.next());
                } else {
                    System.out.println("OTHER: " + scanner.next());
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerPatternDemo.java
java ScannerPatternDemo
~~~

Output:

~~~text
WORD: abc
NUMBER: 123
OTHER: x9
~~~

The pattern `"[A-Za-z]+"` only matches ASCII letters; if the data contains Vietnamese letters, use an appropriate Unicode pattern, such as character class `\\p{L}+` for Unicode Letter characters. If combining marks must also be accepted, the definition of a "word" must include combining characters and business rules.

Do not use `hasNext("[A-Za-z]+")` to validate all real human names; real names contain spaces, diacritics, hyphens, and varied scripts. The pattern here only illustrates token classification.

## 10. Pattern: Read Line by Line, Then Tokenize Each Line

Data structured so that **each line is one record** is usually safer when the application preserves line boundaries:

~~~text
Lan;21;Ha Noi
Minh;22;Da Nang
~~~

You can use an outer Scanner to read lines and an inner Scanner to parse tokens on each line:

~~~java
try (Scanner lines = new Scanner(text)) {
    while (lines.hasNextLine()) {
        String line = lines.nextLine();
        try (Scanner fields = new Scanner(line).useDelimiter(";")) {
            // Read fields from a single line.
        }
    }
}
~~~

This is an **illustrative snippet**, where `text` has type `String`. It works for simple formats without embedded separators inside fields and without special empty-field semantics. It also makes reporting the exact line number on error straightforward. If data permits empty fields, escaped separators, quoted fields, or embedded newlines, use a parser designed for that exact format.

### 10.1. Do Not Mix nextLine and hasNext Uncontrolled

Different iteration patterns have different contracts:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
}
~~~

This loop stops when no **tokens** remain according to the delimiter.

~~~java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
}
~~~

This loop stops when no **lines** remain to be read. With blank lines or consecutive separators, the number of lines does not equal the number of tokens. If the problem must preserve blank lines, looping only by tokens will miss that information.

## 11. Errors and Exceptions to Handle

Scanner methods have notable error behaviors:

| Situation | Typical Behavior | How to Handle |
| --- | --- | --- |
| `next()` when no token exists | `NoSuchElementException` | Check `hasNext()` or handle EOF |
| `nextInt()` encounters a non-integer token or `int` overflow | `InputMismatchException` | Check `hasNextInt()` or catch and process the token |
| Calling a method on a closed Scanner | `IllegalStateException` | Stop using after `close()`; manage ownership |
| Invalid delimiter regex | `PatternSyntaxException` | Test regex or use `Pattern.quote` for literals |
| Opening file fails | I/O exception when creating source/Scanner | Check path, permissions, charset, and handle error |
| Underlying Reader throws `IOException` while Scanner reads | Scanner treats it as end of input at tokenization layer; records error | Check `scanner.ioException()` when distinguishing I/O failure from EOF |

An important detail: Scanner is designed for convenience in text parsing, so it may **not directly throw an `IOException` raised while reading from a `Readable`**. The `scanner.ioException()` API returns the last I/O exception thrown by the source, if any. If the program must distinguish "normal end of data" from "mid-stream read error," check that method and propagate the error appropriately.

Illustrative check at the end of scanning:

~~~java
IOException problem = scanner.ioException();
if (problem != null) {
    throw problem;
}
~~~

This is an **illustrative snippet**, requiring an existing `scanner`, `import java.io.IOException`, and an enclosing method that declares or catches `IOException`. With a `String` source, there is no external read error to observe; with files or network connections, this check is valuable.

Do not catch `InputMismatchException` and simply ignore it to call `nextInt()` again on the same token: the bad token typically remains at the current position. To retry, you must consume or replace the invalid token, or fix the source per program rules.

## 12. Resource Lifecycle and Closing Responsibility

`Scanner` implements `Closeable`, so it can be used in `try-with-resources`:

~~~java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    // Scan tokens.
}
~~~

Upon completion, Scanner closes automatically, even if an exception occurs inside the `try` body. If Scanner's source implements `Closeable`, `Scanner.close()` closes that source. Hence this pattern is suitable when Scanner **owns** the opened file source.

Ownership scenarios:

- Creating a Scanner over a `String`: there is no file handle to release, though closing Scanner still expresses usage lifecycle.
- Creating a Scanner from a `Path` or opening a dedicated `Reader` for a task: normally the creator ensures the resource is closed.
- Receiving a caller's `Reader` or `InputStream`: agree on who closes it, because closing Scanner may close a shared source.
- Scanner over `System.in`: do not close prematurely inside a small helper if subsequent features still require console input.

`Scanner` is **not thread-safe for concurrent sharing without external synchronization**. It maintains scan position, delimiter, locale, and buffer state. If multiple components must parse different data, create a separate Scanner per independent source or build controlled coordination.

## 13. Performance: When Is Scanner Appropriate?

Scanner is convenient for small-to-medium data, CLI tools, practice exercises, simple token formats, and programs needing direct type conversion. However, it also evaluates regexes and multiple parsing rules, so for huge volumes of numbers or logs, overhead can be higher than specialized linear readers.

Some choices:

| Problem | Recommendation |
| --- | --- |
| Console input by word/number | Scanner with clear token and locale rules |
| Splitting a small `String` on a simple separator | Scanner or `String.split` depending on empty-field needs |
| Reading a file line by line, keeping full lines | `BufferedReader.readLine()` / `Files.newBufferedReader` |
| Reading very large text files sequentially by record | `BufferedReader` and a format-appropriate parser |
| Reading binary files | `InputStream` / byte NIO; do not use Scanner |
| CSV with quotes, embedded commas, multiline cells | Format-compliant CSV parser |
| JSON/XML | JSON/XML parser; simple Scanner delimiters are insufficient |
| Complex tokens needing Unicode/custom grammar | Build a tailored parser or use a dedicated library |

An extremely long token without a matching delimiter can force Scanner to buffer many characters searching for a boundary. For untrusted input, define size limits, token counts, timeouts/cancellation policies, and validation rules depending on the source type.

Do not pick an overly complex delimiter regex when a simpler format description works. A backtracking-prone regex can make token matching abnormally slow on long inputs.

## 14. Comprehensive Example: Parsing Semicolon-Delimited Records with Token Validation

The following example reads a data record with three tokens: name, age, and city, separated by semicolons and optional surrounding whitespace. Fixed data makes verifying the output straightforward.

Save as **ScannerRecordDemo.java**:

~~~java
import java.util.Scanner;

public class ScannerRecordDemo {
    public static void main(String[] args) {
        String record = "Nguyễn An; 23; Hà Nội";

        try (Scanner scanner = new Scanner(record)) {
            scanner.useDelimiter("\\s*;\\s*");

            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing name");
            }
            String name = scanner.next();

            if (!scanner.hasNextInt()) {
                throw new IllegalArgumentException("Invalid age");
            }
            int age = scanner.nextInt();

            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing city");
            }
            String city = scanner.next();

            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Unexpected extra token");
            }

            System.out.println("Name: " + name);
            System.out.println("Age: " + age);
            System.out.println("City: " + city);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerRecordDemo.java
java ScannerRecordDemo
~~~

Output:

~~~text
Name: Nguyễn An
Age: 23
City: Hà Nội
~~~

Explanation:

1. The delimiter is only a semicolon with optional surrounding whitespace. Because **spaces between words in a name or city are not delimiters**, `"Nguyễn An"` and `"Hà Nội"` each stay together as one token.
2. `hasNext()` guards `next()` calls against missing tokens; `hasNextInt()` validates the age token against integer syntax.
3. `nextInt()` consumes the same token that `hasNextInt()` just checked, since no other read happens between those two calls.
4. The final `hasNext()` check detects trailing extra data. In real formats, also validate length, age range, leading/trailing whitespace, empty fields, and relevant error cases.
5. Scanner takes a `String` so no file is required; in production systems, the same token parsing can apply to a `Reader`, provided charset, I/O, and ownership are managed properly.

This example **is not a quoted CSV parser**, and `hasNextInt()` depends on locale configuration. When a format has fixed rules, set `Locale` and validation policies accordingly.

## 15. Common Mistakes in Applications

| Practice | What Can Happen | Fix |
| --- | --- | --- |
| Using default delimiter to read `"A,B,C"` | Entire string may become one token | `useDelimiter(",")` if truly comma-delimited |
| Using `useDelimiter(".")` to split on dots | `.` is a regex metacharacter matching almost any character | `useDelimiter("\\.")` or `Pattern.quote(".")` |
| Calling `nextLine()` right after `nextInt()` expecting the name | May read the empty remainder of the number's line | Separate token/line strategies; read the intended line cleanly |
| Mixing `next()` and `nextLine()` without tracking Scanner position | Data skipped or misread | Document format and test with multiple line-ending styles |
| Using `hasNextInt()` in a loop without consuming bad tokens | Loop stalls forever | Call `next()` to skip the bad token or throw an error |
| Assuming `hasNext()` never blocks | On live sources, Scanner may wait for data | Design timeouts/cancellation around the I/O source |
| Using `useDelimiter(",")` for quoted CSV | Mis-splits fields containing commas | Use a dedicated CSV parser |
| Using Scanner to read binary data | Bytes get decoded as text characters | Use byte streams/NIO |
| Not specifying charset for a byte source | Accented characters can be corrupted | Choose charset per data contract |
| Not specifying Locale for numbers | `nextDouble()` may misinterpret decimals | `useLocale(Locale.US)` or specified locale |
| Closing a Scanner on `System.in` too early | Other components can no longer read console input | Manage lifecycle at application level |
| Ignoring `scanner.ioException()` when source fails | May mistake an I/O error for EOF | Check and report errors at the proper boundary |
| Tokenizing untrusted data without bounds | Tokens/regex can exhaust memory and CPU | Validate size, token count, and timeouts |

## 16. Self-Check Comprehension

**Question 1.** With source `"A, B C"` and the default delimiter, how many tokens are there?

**Answer:** three whitespace-separated tokens: `"A,"`, `"B"`, `"C"`. The comma is not automatically a delimiter.

**Question 2.** With source `"A, B C"` and `useDelimiter("\\s*,\\s*")`, what are the two tokens?

**Answer:** `"A"` and `"B C"`. The space inside `"B C"` is preserved because only a comma with optional surrounding whitespace acts as a separator.

**Question 3.** Does calling `hasNext()` twice in a row consume two tokens?

**Answer:** no. It only checks without consuming; `next()` advances the position.

**Question 4.** When `nextInt()` encounters token `"abc"`, after catching `InputMismatchException`, can you immediately call `nextInt()` again to read the next number?

**Answer:** normally no. The offending token is still there. You must decide whether to halt with an error or consume the bad token via `next()` before continuing.

**Question 5.** Does `Locale.GERMANY` make Scanner change its token delimiter from whitespace to a comma?

**Answer:** no. Locale affects locale-specific number interpretation; the delimiter is controlled separately via `useDelimiter`.

**Question 6.** When `Scanner scanner = new Scanner(System.in)` is closed, what happens?

**Answer:** `Scanner.close()` closes a source implementing `Closeable`, here `System.in`. Avoid closing prematurely if multiple components still need console input.

**Question 7.** Why shouldn't you simply use a comma delimiter to parse an arbitrary CSV file?

**Answer:** commas can appear inside quoted fields, fields can be empty or contain newlines; you need a parser that understands CSV rules.

### Practice Exercises

1. Modify `ScannerDelimiterDemo` to accept `"Đà Nẵng|Hồ Chí Minh|Hà Nội"` and use a literal `|` delimiter. Verify the three city names with spaces stay intact.
2. Modify `ScannerValidationDemo` to report the sum of valid integers and the count of skipped tokens; test with `"2 bad 7 10"`.
3. Run `ScannerLinePitfallDemo` with `"42 abc\nNguyen Van A\n"`. Observe the remainder of the first line to see why `nextLine()` is not merely a "clear the newline" call.
4. Create a UTF-8 file containing `"Lan; 21; Hà Nội"`, read it with Scanner via `Path`/`Reader`, and compare results against the String source. Add missing-file handling and clearly define who closes the resource.

## 17. Key Takeaways

- **Scanner turns character input into tokens** using a regex delimiter and can parse tokens into target data types.
- **Sources are String, Reader, InputStream, or files**, and byte sources require choosing the right charset. Closing Scanner may also close the underlying source.
- **The default delimiter is whitespace**; `useDelimiter` changes token-splitting rules without changing charset or Locale.
- **`hasNext` checks; `next` consumes.** `hasNextInt`/`nextInt` parse numeric tokens, whereas `nextLine` handles line boundaries under a different contract.
- **Regex is not a literal string**: escape `.`, `|`, and metacharacters, or use `Pattern.quote` for fixed separators.
- **Scanner suits relatively simple token data**. For quoted CSV, JSON, XML, binary files, or strict formats, use an appropriate parser or API.

### References

- [Scanner — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html)
- [Pattern — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [InputStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
