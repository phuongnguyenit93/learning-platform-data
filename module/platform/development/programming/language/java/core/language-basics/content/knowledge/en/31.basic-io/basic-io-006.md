# Distinguishing `next()`, `nextInt()`, and `nextLine()` in Java

## 1. Three `Scanner` methods that read data differently

The `java.util.Scanner` class helps read and parse data from the keyboard (`System.in`), strings, or other data sources. Three common methods are:

- **`next()`**: reads **one token** and returns a `String`.
- **`nextInt()`**: reads **one token representing a valid integer** and returns an `int` value.
- **`nextLine()`**: reads the **remainder of the current line** and returns a `String`, excluding the line terminator characters from the result.

The two methods `next()` and `nextInt()` work by **token**; `nextLine()` works by **line boundary**. This difference is the common root cause of the "`nextLine()` gets skipped" bug when combined with `nextInt()`.

```java
import java.util.Scanner;

// Place inside a method:
Scanner sc = new Scanner(System.in);
String word = sc.next();
int age = sc.nextInt();
String text = sc.nextLine();
```

The snippet above only illustrates syntax and is **not a standalone program**. The result depends on the input provided and the `Scanner`'s current position in the stream.

## 2. Quick comparison table

| Characteristic | `next()` | `nextInt()` | `nextLine()` |
| --- | --- | --- | --- |
| Returns | `String` | `int` | `String` |
| Unit read | Token | Integer token | Remainder of the line |
| Default whitespace handling | Skips delimiters before the token; stops at the delimiter after the token | Same as `next()`, while also parsing the token under integer rules | Preserves spaces within the line content; omits the line terminator from the result |
| Input `"Java Core"` | First call returns `"Java"` | Throws an error because the first token is not an integer | Returns `"Java Core"` when starting from the beginning of the line |
| Reading the number `42` | Returns string `"42"` | Returns number `42` | Returns string `"42"` if the line only contains `42` |
| If the first token has invalid number format | Can still read that token as a string | May throw `InputMismatchException` | Does not parse numbers; simply reads the line content |
| After reading | Usually leaves position at the boundary after the token | Usually leaves position at the boundary after the token | Consumes the line terminator as well if present |

With default settings, `Scanner` treats one or more **Java-defined whitespace** characters as token **delimiters**: spaces, tabs, newlines, and other whitespace characters. A different delimiter can be configured with `useDelimiter(...)`, so do not claim that `next()` always splits on spaces in every program.

**Note on `nextLine()`:** the method starts from the **current read position**, not necessarily the beginning of a line. If `next()` or `nextInt()` was called beforehand, the remainder of the line may just be an empty string or unconsumed spaces.

## 3. `next()`: reading a single token as a string

When entering:

```text
Nguyen Van An
```

and calling:

```java
String first = sc.next();   // "Nguyen"
String second = sc.next();  // "Van"
String third = sc.next();   // "An"
```

`next()` skips delimiters before each token and grabs the next token. It does not automatically combine three words into one full name.

A notable case:

```java
// If the input starts with: "Java 17"
String text = sc.next(); // "Java"
```

Even when `17` is a number, `next()` still returns a `String`. To process the number, you can call `nextInt()` on the next read if the token fits, or convert the received string with a method like `Integer.parseInt` after checking the data.

Because it reads tokens rather than lines, `next()` is unsuitable for reading **full names, addresses, or multi-word descriptions** when you need to preserve the whole line's content.

## 4. `nextInt()`: reading and parsing an integer token

Suppose the user enters:

```text
18 25
```

```java
int a = sc.nextInt(); // 18
int b = sc.nextInt(); // 25
```

`nextInt()` reads each token and converts it to `int`. Keep these distinctions clear:

- `next()` on token `18` returns the string `"18"`.
- `nextInt()` on token `18` returns the integer value `18`.
- Token `"abc"` is not a valid `int`, so `nextInt()` may throw `InputMismatchException`.
- A token representing a number **outside the range of `int`** can also cause `InputMismatchException`.
- If no tokens remain, the method may throw `NoSuchElementException`; if the `Scanner` is closed, read operations may throw `IllegalStateException`.

By default, `nextInt()` uses radix 10 and parses numbers according to the `Scanner`'s **locale**. You can specify a radix with `nextInt(radix)` or `useRadix`; locale can also affect how certain numeric formats are parsed. For simple inputs like `18` or `-7`, the standard behavior is to read the corresponding values.

When checking numeric input from a user, it is usually best to check first with `hasNextInt()`:

```java
if (sc.hasNextInt()) {
    int age = sc.nextInt();
    System.out.println("Tuoi: " + age);
} else if (sc.hasNext()) {
    String invalid = sc.next(); // Consume the invalid token
    System.out.println("Khong phai so nguyen: " + invalid);
}
```

This snippet illustrates code inside a method. `hasNextInt()` only **checks** the next token; it does not consume it. If you get `false` and call `nextInt()` again without changing data or handling the error, you will not solve the problem.

## 5. `nextLine()`: retrieving the remainder of the line

When starting from the beginning of a line:

```text
Nguyen Van An
```

```java
String fullName = sc.nextLine(); // "Nguyen Van An"
```

`nextLine()` keeps spaces between words in the string; it returns the line content **without line terminator characters**. This method is suited for full names, sentences, or addresses where spaces must be preserved.

If the current position is already mid-line, it only reads the **remainder**:

```text
Java Core
```

```java
String first = sc.next();    // "Java"
String rest = sc.nextLine(); // " Core" (has a leading space)
```

This behavior has an important implication: `nextLine()` does not strip leading whitespace the way `next()` does. Call `trim()` if you want to remove whitespace at both ends, but **only do so when the input requirements actually allow it**, because it can alter content the user intended to keep.

If the end of input is reached and no line remains to be read, `nextLine()` may throw `NoSuchElementException`. When reading from a file or string, you can use `hasNextLine()` before calling `nextLine()` to handle end-of-data cases.

## 6. Mixing tokens and lines: check the remainder before discarding

Given a two-line input `20\nNguyen Van An\n`, `nextInt()` consumes the token `20`, yet the following `nextLine()` returns `""` because it only reads the remainder of the number line. To read the next name line, you can **read and discard the remainder** with one `nextLine()` call before reading again.

This approach is only right when the name truly sits on a separate line. With `20 Nguyen Van An\n`, the remainder of the number line is `" Nguyen Van An"` and must be **kept**. If the program specifies one field per line, you can consistently read with `nextLine()` and then convert numbers with `Integer.parseInt`, handling `NumberFormatException`.

The standalone runnable program below tests empty remainders, remainders containing numbers, and invalid tokens; the dedicated lesson on **leftover newlines** covers EOF, multiple fields on one line, and preventing data loss in greater detail.

## 7. Standalone runnable Java 17+ program for exact observation

To make output deterministic on every machine without manual typing, the example uses `Scanner` reading from **fixed input strings**. These are the exact same methods used when the data source is `System.in`.

Create the file **`ScannerReadDemo.java`**:

```java
import java.util.Scanner;

public class ScannerReadDemo {
    static void tokensAndLines() {
        String input = "Lan Nguyen\n27\nJava Core\n";
        try (Scanner scanner = new Scanner(input)) {
            System.out.println("next1=[" + scanner.next() + "]");
            System.out.println("next2=[" + scanner.next() + "]");
            System.out.println("nextInt=" + scanner.nextInt());
            System.out.println("afterInt=[" + scanner.nextLine() + "]");
            System.out.println("fullLine=[" + scanner.nextLine() + "]");
        }
    }

    static void remainingSameLine() {
        try (Scanner scanner = new Scanner("42  7\nHello world\n")) {
            System.out.println("number=" + scanner.nextInt());
            System.out.println("rest=[" + scanner.nextLine() + "]");
            System.out.println("line=[" + scanner.nextLine() + "]");
        }
    }

    static void recoverInvalidToken() {
        try (Scanner scanner = new Scanner("abc 15\n")) {
            if (!scanner.hasNextInt() && scanner.hasNext()) {
                System.out.println("bad=[" + scanner.next() + "]");
            }
            System.out.println("valid=" + scanner.nextInt());
        }
    }

    static void parseWholeLine() {
        try (Scanner scanner = new Scanner("20\nNguyen Van An\n")) {
            int age = Integer.parseInt(scanner.nextLine().trim());
            String name = scanner.nextLine();
            System.out.println("age=" + age);
            System.out.println("name=[" + name + "]");
        }
    }

    public static void main(String[] args) {
        tokensAndLines();
        remainingSameLine();
        recoverInvalidToken();
        parseWholeLine();
    }
}
```

Open a terminal in the directory containing the file, with **JDK 17 or later**, and run identically on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 ScannerReadDemo.java
java ScannerReadDemo
```

**Exact stdout** result (a successful compilation prints nothing):

```text
next1=[Lan]
next2=[Nguyen]
nextInt=27
afterInt=[]
fullLine=[Java Core]
number=42
rest=[  7]
line=[Hello world]
bad=[abc]
valid=15
age=20
name=[Nguyen Van An]
```

Explanation:

1. The two `next()` calls read `Lan` and `Nguyen`. `nextInt()` skips the newline and reads the number `27`.
2. `afterInt=[]` demonstrates that calling `nextLine()` after `nextInt()` immediately meets the newline of line `27`, receiving an empty string; the next call then reads `Java Core`.
3. In `"42  7\n"`, after `nextInt()` reads `42`, `nextLine()` returns **two spaces followed by `7`**; the remainder is **not always empty**.
4. `hasNextInt()` encounters token `abc` and returns `false` without consuming the token; `next()` consumes it, and then `nextInt()` reads `15`.
5. `parseWholeLine()` shows how to read age and full name line by line, converting the age string to a number with `Integer.parseInt`.

In this example, each `Scanner` is created from a `String` and closed with **try-with-resources**, without affecting `System.in`. That is why the program runs on its own and requires no keyboard interaction.

## 8. Using `Scanner(System.in)` in a program with keyboard input

A simple pattern when the user enters age and full name on **two separate lines**:

```java
import java.util.Scanner;

public class KeyboardInput {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.print("Nhap tuoi: ");
        int age = sc.nextInt();
        sc.nextLine(); // Consume the remainder on the age line
        System.out.print("Nhap ho ten: ");
        String name = sc.nextLine();
        System.out.println("Tuoi=" + age);
        System.out.println("Ten=" + name);
    }
}
```

Save as **`KeyboardInput.java`**, compile, and run:

```bash
javac -encoding UTF-8 KeyboardInput.java
java KeyboardInput
```

Example input:

```text
20
Nguyen Van An
```

The two final output lines of the program are:

```text
Tuoi=20
Ten=Nguyen Van An
```

This is an **interactive** example, so the prompts `Nhap tuoi:` and `Nhap ho ten:` may appear on the same line as what the user types; do not treat a terminal screen capture (including keyboard echo) as pure fixed stdout.

A note on closing resources: `Scanner.close()` also closes the underlying input source if that source implements `Closeable`. When using `new Scanner(System.in)`, closing the scanner may also close the shared **`System.in`** stream, preventing other parts of the program from reading further. For small console programs that read once and exit, consider resource ownership; for larger applications, **do not create and close multiple separate scanners on the same `System.in`**. In the keyboard example above, the scanner is kept for the entire reading period and is not manually closed midway.

## 9. Common errors and how to handle them

| Symptom | Cause / how to handle |
| --- | --- |
| `nextLine()` receives an empty string after `nextInt()` | Remaining line terminator; if two fields are on separate lines, call `nextLine()` once to consume the remainder |
| `next()` only receives one word of a full name | It reads a token, not the whole line; use `nextLine()` if the full content is needed |
| `nextInt()` throws `InputMismatchException` | Current token is not a valid integer or is out of `int` range; check with `hasNextInt()` and have a strategy to discard the bad token |
| Program keeps hitting the same invalid token | `hasNextInt()` does not consume tokens; you need `next()`, re-reading the line, or adjusting the input flow |
| `nextLine()` loses data on the number line | A remainder-consuming call discarded content after the number; clearly design whether data sits on the same line or separate lines |
| Reading past the end of data causes `NoSuchElementException` | Check `hasNext()` / `hasNextLine()` appropriately before reading |
| Reading after closing `Scanner` causes `IllegalStateException` | Do not use a closed scanner; manage the input source lifecycle |
| Two `Scanner` instances on the same `System.in` cause confusing behavior | Use one scanner within an appropriate scope; do not close a still-shared source |
| Reading a numeric string with `nextLine()` fails in `parseInt` | Handle `NumberFormatException` and specify rules for empty strings, whitespace, and numeric range |
| Assuming `nextInt()` always consumes the whole line | It only reads the integer token and does not consume the trailing newline |

## 10. Checklist for deciding how to read

1. Need to read **a single word or code with no delimiters**? Choose `next()`.
2. Need to read **an integer from the next token**? Choose `nextInt()`, checking for invalid data when needed.
3. Need to read **a full name/sentence/line**? Choose `nextLine()`.
4. Just read with a token method and now want to read another line? Check **whether there is a remainder after the token**; handle the line boundary intentionally.
5. Need data **line by line in a fixed structure**? Usually use `nextLine()` consistently and then convert values, so each read consumes one line.
6. Reading a file/string that might end unexpectedly? Use `hasNext()`, `hasNextInt()`, or `hasNextLine()` matching the method you intend to call.

**Key takeaway:** `next()` returns **a string token**; `nextInt()` returns **an integer token**; `nextLine()` returns the **remainder of the line**, not just a token. When mixing token reads and line reads, understand the scanner's position and handle the leftover newline to avoid losing data.