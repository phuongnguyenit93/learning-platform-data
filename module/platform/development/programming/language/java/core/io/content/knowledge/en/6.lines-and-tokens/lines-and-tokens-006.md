# `Scanner.next()`, `nextLine()`, and Remaining Newlines

When reading input in Java, a common bug occurs: a program reads a number with `Scanner.nextInt()`, immediately asks for a name with `nextLine()`, yet the name variable becomes an empty string or the program appears to "skip" the prompt. Similarly, calling `next()` before `nextLine()` can cause the second read to return only **the remainder of the current line**, rather than a brand-new line.

To understand and handle this accurately, distinguish two reading modes in `java.util.Scanner`:

- **Reading tokens:** `next()`, `nextInt()`, `nextDouble()`, etc. work with items separated by a **delimiter**.
- **Reading lines:** `nextLine()` reads **the remainder of the current line** up to and consuming the line terminator, advancing the read position to the next line.

The issue is not that `nextLine()` is buggy; it is a direct consequence of the **current scan position** after a token-reading operation. This lesson explains the mechanism, illustrates cases with and without leftover spaces, and presents the right coding approaches depending on the input structure.

## 1. How Do Tokens and Lines Differ?

### Token: A Unit Separated by a Delimiter

`Scanner` uses a delimiter pattern to split input into tokens. By default, the delimiter matches whitespace characters according to Java rules, including ordinary spaces and line breaks.

Given input:

~~~text
Java Core
27
Nguyễn Văn An
~~~

Consecutive `next()` calls return tokens such as:

~~~text
"Java" -> "Core" -> "27" -> "Nguyễn" -> "Văn" -> "An"
~~~

`next()` skips delimiters before the next token, then returns that token. It **does not automatically return a whole line with spaces** and has no notion of "one full name" when a name contains multiple words. Methods like `nextInt()` also use the same token-finding mechanism before parsing the token into the target data type.

### Line: Text Up to a Line Terminator

`nextLine()` operates along **text lines**. It returns the text **remaining on the line at the current scan position**, excluding the line terminator that ends that line. Afterward, the scan position is placed at the start of the next line.

With the same input string and starting position:

~~~java
String firstLine = scanner.nextLine(); // "Java Core"
String secondLine = scanner.nextLine(); // "27"
String thirdLine = scanner.nextLine(); // "Nguyễn Văn An"
~~~

These are illustrative lines where `scanner` is a `Scanner` created from the exact data above. Each read gets one **line**, including spaces within the line. `nextLine()` can return `""` if the current position is directly before a line terminator.

**Easy mental model:** `next()` asks "what is the next token?", whereas `nextLine()` asks "what remains from the current position to the end of the line?".

## 2. Why Do `next()` and `nextLine()` Produce Surprising Results?

Consider a one-line input `Java Core`, ending with Enter. To make spaces and line-ending characters visible, let `↵` denote Enter:

~~~text
Java Core↵
^^^^       next() reads token "Java"
    ^^^^^  nextLine() next reads " Core" (including the leading space)
         ↵ line terminator consumed by nextLine()
~~~

If `next()` is called first, it returns token `Java`; the scan position stops at the separator following the token. When `nextLine()` is called immediately afterward, the method **does not automatically discard the remainder to jump to a new line**: it returns `" Core"`, with a leading space.

If the input is:

~~~text
Java↵
Core↵
~~~

then after `next()` reads `"Java"`, the remainder before Enter **contains no content characters**. Therefore, the subsequent `nextLine()` returns **`""`**, consumes Enter, and moves the position to the start of the `Core` line.

The two cases differ only in whether characters exist in the remainder of the line. Consequently, do not mechanically memorize that "after `next()`, `nextLine()` is always empty." It returns **the remainder of the current line**, which may be empty, contain whitespace, or contain full text.

## 3. The Classic Case: `nextInt()` Followed by `nextLine()`

Suppose a program prompts for age and full name:

~~~text
27↵
Nguyễn Văn An↵
~~~

A frequently seen snippet:

~~~java
System.out.print("Tuổi: ");
int age = scanner.nextInt();

System.out.print("Họ tên: ");
String fullName = scanner.nextLine();
~~~

This is an **illustrative snippet** placed inside a method where `scanner` reads from input. On the sample data above, `nextInt()` reads the numeric token `27` but **does not read the whole line like `nextLine()`**. Because the remainder before Enter is empty, `nextLine()` right after receives `""` and consumes the line terminator. The name on the next line **has not been read yet**.

Illustrating the scan position:

~~~text
Before:
27↵
Nguyễn Văn An↵

After nextInt():
27|↵              ("|" is the current read position)
Nguyễn Văn An↵

After nextLine():
27↵
|Nguyễn Văn An↵  (nextLine returned "")
~~~

Note: this is a conceptual model of **logical behavior**; do not interpret it as a literal description of `Scanner`'s internal bytes or buffer indices.

### What If There Are Two Spaces After the Number?

With:

~~~text
27··↵
Nguyễn Văn An↵
~~~

where `·` represents a space. After `nextInt()`, calling `nextLine()` returns **two spaces** (`"  "`) rather than an empty string. Thus, checking `fullName.isEmpty()` is not enough to catch every case of "name not read yet."

If there is content after the number on the **same line**, for instance `27 Nguyễn Văn An↵`, `nextLine()` returns `" Nguyễn Văn An"`. That is meaningful data and **should not be discarded blindly**.

## 4. Runnable Java 17 Example: Same Data, Three Behaviors

The following program reads from `String` so results are deterministic without manual typing during testing. It creates separate independent `Scanner` instances to clearly compare:

1. `next()` + `nextLine()` on a multi-word line.
2. `nextInt()` + `nextLine()` right at a line boundary.
3. Reading the **entire line** before parsing the number, avoiding leftover newlines.
4. A line tail consisting solely of two spaces after a numeric token.

Save file **`ScannerTokenLineDemo.java`**:

~~~java
import java.util.Scanner;

public class ScannerTokenLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("Java Core\n")) {
            String token = scanner.next();
            String restOfLine = scanner.nextLine();
            System.out.println("Token: [" + token + "]");
            System.out.println("Remaining line: [" + restOfLine + "]");
        }

        String input = "27\nNguyễn Văn An\n";
        try (Scanner scanner = new Scanner(input)) {
            int age = scanner.nextInt();
            String tail = scanner.nextLine();
            String name = scanner.nextLine();

            System.out.println("Age: " + age);
            System.out.println("After nextInt: [" + tail + "]");
            System.out.println("Next full line: [" + name + "]");
        }

        try (Scanner scanner = new Scanner(input)) {
            int age = Integer.parseInt(scanner.nextLine().trim());
            String name = scanner.nextLine();

            System.out.println("Line-based age: " + age);
            System.out.println("Line-based name: [" + name + "]");
        }

        try (Scanner scanner = new Scanner("27  \nAn\n")) {
            int age = scanner.nextInt();
            String tail = scanner.nextLine();
            System.out.println("Age with spaces: " + age);
            System.out.println("Tail with spaces: [" + tail + "]");
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 ScannerTokenLineDemo.java
java ScannerTokenLineDemo
~~~

Expected output (spaces inside square brackets are **intentional**):

~~~text
Token: [Java]
Remaining line: [ Core]
Age: 27
After nextInt: []
Next full line: [Nguyễn Văn An]
Line-based age: 27
Line-based name: [Nguyễn Văn An]
Age with spaces: 27
Tail with spaces: [  ]
~~~

Explanation:

- `Remaining line: [ Core]` has **one leading space** before `Core` because `next()` took only the first token `Java`.
- `After nextInt: []` is empty because a newline directly follows `27`, and `nextLine()` consumes it.
- Once the first `nextLine()` has consumed the empty tail, the second `nextLine()` returns the full name.
- The line-based approach `Integer.parseInt(scanner.nextLine().trim())` converts the numeric text into an `int` after consuming the whole line, so the next `nextLine()` reads the name immediately.
- `Tail with spaces: [  ]` contains **two spaces**, demonstrating that the method returns the remainder of the line rather than always returning an empty string.
- `Scanner` is created from a `String` rather than `System.in`; closing via `try-with-resources` does not affect the application's standard input stream.

When displayed on a terminal without Unicode support or with mismatched encoding settings, Vietnamese names may render differently on screen; token/line splitting behavior inside `String` remains as demonstrated.

## 5. Three Proper Approaches and When to Choose Each

### Approach A — Prefer Reading Full Lines, Then Parse Data

If each prompt/value occupies **its own line**, the clearest solution is to use `nextLine()` consistently:

~~~java
int age = Integer.parseInt(scanner.nextLine().trim());
String fullName = scanner.nextLine();
~~~

Pros:

- Does not mix token and line mechanisms.
- Can read multi-word names, addresses, and sentences without cutting off internal spaces.
- Relatively easy to validate each line, display errors, and re-prompt the user.

Cons:

- Must handle conversion errors manually: `Integer.parseInt` throws `NumberFormatException` if the input line is empty, non-numeric, or outside `int` range.
- `trim()` should only be applied to the age line when stripping leading/trailing spaces is desired; for names, passwords, or data where whitespace is significant, **do not trim arbitrarily** unless the specification asks for it.
- If multiple fields appear on one line, you need a separate field-splitting convention or a structured line parser.

A safe validation pattern is reading the line into a variable first:

~~~java
String ageLine = scanner.nextLine();
try {
    int age = Integer.parseInt(ageLine.trim());
    // Handle valid age here.
} catch (NumberFormatException ex) {
    // Prompt again or report error according to application design.
}
~~~

This is an **illustrative method snippet**; to avoid errors at end of input, check `hasNextLine()` first. Note that the comments inside `try`/`catch` represent where the application runs specific business logic rather than performing re-prompting automatically.

### Approach B — Read a Token, Then Intentionally Discard the Remainder of the Line

If you genuinely want to use `nextInt()` for age and **know for certain** the rest of the line holds no data worth keeping:

~~~java
int age = scanner.nextInt();
scanner.nextLine();          // Consume the remainder of the age line.
String fullName = scanner.nextLine();
~~~

The middle `scanner.nextLine()` does not mean "clear newline" as a special command. It **reads and discards the entire remainder of the current line, including any text content if present**, then advances to the next line.

**Use only when the input format is strictly defined:** each age line contains only the age token (and possibly trailing spaces), while the name begins on the following line. If the user enters `27 Nguyễn Văn An` on one line, that extra call will **discard the name**.

Likewise, do not append `nextLine()` after **every** `nextInt()` call: if you intentionally read multiple tokens on the same line, discarding the remainder drops data. The rule must follow the **input format** and where the next piece of data sits.

### Approach C — Read the Full Line, Then Use a Dedicated `Scanner` to Split Tokens

If each line holds a multi-field record, for example:

~~~text
27 Nguyễn Văn An
~~~

you can read the entire line from the main stream, then parse the line structure in another `Scanner`:

~~~java
String record = scanner.nextLine();
try (Scanner lineScanner = new Scanner(record)) {
    int age = lineScanner.nextInt();
    String name = lineScanner.nextLine().stripLeading();
    // age = 27; name = "Nguyễn Văn An"
}
~~~

This is an **illustrative snippet**, where `scanner` reads the application's input data. `stripLeading()` strips leading whitespace from the name portion after the numeric token **without removing internal spaces inside the name**. If records follow a stricter format (CSV, TSV, JSON, etc.), use a parser matching that format rather than inventing ad-hoc whitespace splitting.

Only wrap `lineScanner` around **an already-read line string**; avoid creating multiple independent `Scanner` instances over `System.in` because each scanner maintains its own buffer and can read ahead, depriving the other scanner of expected data.

## 6. `hasNext()` and `hasNextLine()`: Check What You Are About to Read

The two check methods serve different purposes:

| Check call | Question answered | Usually paired with |
|---|---|---|
| `hasNext()` | Is there another **token**? | `next()` |
| `hasNextInt()` | Can the next token be parsed as an `int`? | `nextInt()` |
| `hasNextLine()` | Is there another **line** to read? | `nextLine()` |

Example of safely iterating line by line:

~~~java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
    System.out.println("Line: [" + line + "]");
}
~~~

And when reading only tokens:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
    System.out.println("Token: [" + token + "]");
}
~~~

Both loops are **illustrative snippets** using an already created `scanner`. An empty line can be returned by `nextLine()` as `""`, whereas `next()` with the default delimiter **skips whitespace** and does not emit an empty token for that blank line.

`hasNextInt()` is useful to avoid `InputMismatchException` when a token cannot convert to an integer; however, if the token is invalid, you must decide whether to **discard that token, report an error, or re-read**. Calling `hasNextInt()` repeatedly without advancing the read position will not fix the input.

Read or check methods on an interactive input stream can **wait for data**. `hasNextLine()` does not guarantee the next line is already available immediately.

## 7. Line Terminators, Leftover Whitespace, and Custom Delimiters

### Line Terminators

Line terminators are typically LF (`\n`) or CRLF (`\r\n`) depending on the source and environment. `Scanner.nextLine()` recognizes line-ending forms per Java's contract and **returns the line content without the line terminator**.

If the read position is directly before a newline, `nextLine()` can return `""`. An actual blank line in a file also returns `""`. The same empty-string result **is not enough to infer the cause**; you must know the read position and input data.

If the final line **has no line terminator** yet still contains content, `nextLine()` can still return that final content. Do not assume the last line must end with Enter.

### Leftover Whitespace

Spaces or tabs before Enter can become the content returned by `nextLine()` after a token is read. To detect "the remainder is only whitespace":

~~~java
String remainder = scanner.nextLine();
boolean onlyWhitespace = remainder.isBlank();
~~~

`isBlank()` also returns `true` for an empty string. However, **detecting is not synonymous with automatically deleting**: some formats treat whitespace as valid data. If data must be preserved, keep `remainder` intact.

### Custom Delimiters

`Scanner.useDelimiter(pattern)` changes the token-splitting rule. For example:

~~~java
try (Scanner scanner = new Scanner("red,blue,green")) {
    scanner.useDelimiter(",");
    System.out.println(scanner.next()); // red
    System.out.println(scanner.next()); // blue
    System.out.println(scanner.next()); // green
}
~~~

This is a Java snippet you can place inside `main` with `import java.util.Scanner`; it only illustrates changing the delimiter. **`nextLine()` does not become "read until comma"**: it still operates on text lines. Consequently, changing to a custom delimiter makes mixing `next()` and `nextLine()` require even more care.

`useDelimiter` takes a **regular expression**, not necessarily a plain character string. For special regex characters such as dot (`.`), escape the regex properly; passing `"."` literally means "any character" in regex.

## 8. When Reading Real Keyboard Input: One Scanner, Clear Lifecycle

Interactive terminal example using **a single `Scanner`** for `System.in` and reading both fields as lines:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class ConsoleProfile {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);

        System.out.print("Tuổi: ");
        if (!scanner.hasNextLine()) return;
        String rawAge = scanner.nextLine();

        int age;
        try {
            age = Integer.parseInt(rawAge.trim());
        } catch (NumberFormatException ex) {
            System.out.println("Tuổi không hợp lệ.");
            return;
        }

        System.out.print("Họ tên: ");
        if (!scanner.hasNextLine()) return;
        String name = scanner.nextLine();

        System.out.println("Tuổi: " + age);
        System.out.println("Họ tên: " + name);
    }
}
~~~

Save as **`ConsoleProfile.java`**, compile and run:

~~~bash
javac --release 17 -encoding UTF-8 ConsoleProfile.java
java ConsoleProfile
~~~

A **sample run** when the user types `27` and `Nguyễn Văn An` followed by Enter (the two user-entered lines are keyboard echo):

~~~text
Tuổi: 27
Họ tên: Nguyễn Văn An
Tuổi: 27
Họ tên: Nguyễn Văn An
~~~

In the example, `new Scanner(System.in, StandardCharsets.UTF_8)` specifies how input bytes are decoded into characters. Pick the charset matching your actual terminal. `Scanner.close()` also closes the input source if the source implements `Closeable`; since `System.in` is typically a shared process-wide resource, the example **does not close `System.in`** at the end of this short operation.

If the application creates and owns the source itself (such as a file or `StringReader`), use `try-with-resources` to close the scanner promptly. For input owned by a caller or framework, follow the resource provider's ownership contract.

## 9. Exceptions and Misconceptions to Avoid

| Misconception | Why Is It Wrong? | Solution |
|---|---|---|
| "`next()` reads a line." | It reads one **token** per the current delimiter. | Use `nextLine()` if you need the whole line. |
| "`nextLine()` after `nextInt()` is always empty." | There may still be spaces or text on the same line. | Understand it returns the remainder of the line. |
| "Adding a `nextLine()` everywhere fixes all bugs." | Can accidentally discard valid data on the same line. | Discard the tail only when the input format allows it. |
| "Calling `nextLine()` gets the next line even from mid-line." | It starts from the **current** position, rather than skipping ahead a line. | Track where the prior token operation left the position. |
| "Reading `nextInt()` then trimming the name is enough." | If the name was skipped, trimming cannot recover it. | Redesign reading flow or consume line boundaries intentionally. |
| "`hasNext()` and `hasNextLine()` are equivalent." | One checks tokens; the other checks lines, especially differing on blank lines. | Use the check matching the read operation. |
| "`nextInt()` reads any value." | Non-numeric or out-of-range tokens throw `InputMismatchException`. | Check `hasNextInt()` or read a line and parse/validate. |
| "`nextLine()` always has a line." | When input runs out, it can throw `NoSuchElementException`. | Check `hasNextLine()` or handle end of input. |
| "You can create multiple Scanners reading `System.in`." | Read-ahead buffering lets one scanner consume data another expects. | Use a single scanner with a clear lifecycle. |
| "`scanner.close()` only closes the wrapper." | It closes the input source if the source is `Closeable`. | Confirm ownership before closing a scanner wrapping `System.in`. |

### Case of Parsing Numbers with a Decimal Comma

`Scanner.nextDouble()` parses numeric formatting according to **locale**. A dot or comma can carry different meanings across locales. This is a **token content parsing** concern, separate from the **line boundary** concern: even when a numeric token is valid, a subsequent `nextLine()` still reads the remainder of the line.

When consistent numeric rules are needed, explicitly call `useLocale(...)` matching the input contract; do not treat setting locale as a fix for newline bugs.

## 10. Self-Check

**Question 1.** Input is `"An Bình\n"`. What does `next()` return, and what does `nextLine()` right after return?

> **Answer:** `next()` returns `"An"`; `nextLine()` returns `" Bình"`, including one leading space. The `\n` is not included in the returned string.

**Question 2.** Input is `"42\nHà Nội\n"`. After `nextInt()` then `nextLine()`, what is the line-read result?

> **Answer:** `nextInt()` returns `42`; `nextLine()` returns `""` because the remainder directly after the numeric token to the end of the line is empty. The next `nextLine()` reads `"Hà Nội"`.

**Question 3.** Input is `"42  Hà Nội\n"` (two spaces between the number and name). Should you discard the first `nextLine()` result after `nextInt()`?

> **Answer:** No, if you need to keep the name. `nextLine()` returns `"  Hà Nội"`; discarding this string loses data on the same line.

**Question 4.** If you want age on line 1 and a multi-word full name on line 2, what is the clearest and least error-prone approach?

> **Answer:** `Integer.parseInt(scanner.nextLine().trim())` for age (with error handling), then `scanner.nextLine()` for the name. Both follow **line boundaries** consistently.

**Question 5.** Input consists of an empty line followed by `"hello"`. Why do a `nextLine()` loop and a `next()` loop produce different results?

> **Answer:** `nextLine()` captures the empty line, returning `""` before `"hello"`; `next()` skips default whitespace, so its first token is `"hello"`.

**Question 6.** Should a helper method receiving the application's `System.in` close its scanner?

> **Answer:** Only if the contract permits closing that source. Because closing `Scanner` can also close `System.in`, a helper merely borrowing the shared source should let the owner manage its lifecycle.

## Key Takeaway

**`next()`/`nextInt()` reads a token; `nextLine()` reads the remainder of the line at the current position and consumes the line terminator.** That remainder may be empty, whitespace-only, or actual text. Choose a consistent input strategy: if data is organized by lines, **read the line first and then parse**; if mixing tokens and lines, discard the line tail intentionally only when you are sure it holds no data you need to keep.

**Reference:** [Java SE 17 — `java.util.Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
