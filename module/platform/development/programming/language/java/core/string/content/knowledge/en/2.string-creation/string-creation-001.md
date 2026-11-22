# String Literals and Double-Quote Syntax in Java

## 1. What is a String Literal?

A **string literal** is a piece of text written directly in Java source code and enclosed between **two ASCII double quotes** (`"`). It represents a `String` object containing the corresponding sequence of characters.

```java
String greeting = "Hello, Java!";
String empty = "";
String numberAsText = "123";
```

- `"Hello, Java!"` and `"123"` are both expressions of type `String`, whether the content contains letters or digits.
- `""` is the **empty string**, which has length `0`, not `null`.
- Double quotes **mark the boundaries** of the literal; they do not become characters inside the string.
- `String` is the class `java.lang.String`; Java imports `java.lang` automatically, so no separate `import` statement is needed.

Read `String greeting = "Hello, Java!";` in two parts: `String greeting` declares a reference variable of type `String`, while `"Hello, Java!"` is the literal used to initialize its value. The variable name, data type, and literal are distinct components.

## 2. Double-Quote Syntax Rules

Basic syntax:

```java
String variableName = "content";
```

1. A standard string literal **opens with `"` and closes with `"`** on the same source line; the compiler determines that the string ends at the next unescaped `"`.
2. The content may have no characters (`""`), spaces (`" "`), Vietnamese characters, symbols, or valid **escape sequences**.
3. To include a `"` character as **content** in the string, you must write `\"`. To include a backslash `\` as content, you must write `\\`.
4. In a standard literal, you cannot insert a source-code line break directly between the two double quotes; use `\n` to represent a newline.

Syntax illustration examples, **not a complete program**:

```java
String a = "Java";                 // Valid
String b = "";                     // Valid: empty string
String c = " ";                    // Valid: single space
String d = "He said: \"Hello\"";  // Valid: contains double quotes
String e = "Line 1\nLine 2";       // Valid: has a newline character at runtime
```

Distinguishing quotes:

| Syntax | Type / Meaning | Notes |
|---|---|---|
| `"A"` | `String` | A 1-character-long string |
| `'A'` | `char` | A single character value |
| `""` | `String` | Empty string |
| `"null"` | `String` | Text consisting of 4 letters |
| `null` | `null` literal | References no object |

For example: `String value = 'A';` **does not compile** because `'A'` is a `char`, not a `String`. To assign a string, write `String value = "A";`.

## 3. Escape Sequences in String Literals

The `\` character introduces an **escape sequence**: a special notation in source code for inserting characters that are hard to type directly or have syntactic meaning into a string.

| Written in source code | Generated character | Common use case |
|---|---|---|
| `\"` | `"` | Displaying double quotes |
| `\\` | `\` | Windows paths, backslash character |
| `\n` | Newline (line feed) | Multi-line text |
| `\t` | Horizontal tab | Separating columns |

The remaining escapes such as `\r`, `\b`, `\f`, `\s`, and `\'` are covered in full in the dedicated escape lesson immediately following this one.

Distinguishing **source code** from **actual value**:

```java
String newline = "\n";      // Contains 1 newline character, not '\' and 'n'
String letters = "\\n";     // Contains 2 characters: '\' and 'n'
String quote = "\"";        // Contains 1 character: '"'
String windowsPath = "C:\\temp\\log.txt";
```

In particular, writing a path like `"C:\temp\log.txt"` does not match the intent: `\t` becomes a tab and `\l` is not a valid escape, so the compiler reports an error. If you need to represent an actual `\`, use `\\`.

An escape unrecognized by Java, such as `"\q"`, causes a compile error (*illegal escape character*), rather than silently keeping the `\`.

### Unicode in Strings

Java can use Unicode characters directly, such as `"Tiếng Việt"`, when the source file is read with the proper encoding. The form `\u0041` produces the character `A` during source translation, **before** literal parsing. Therefore, do not use `\u000A` to write a newline character in a literal: use `\n` instead. This mechanism and its pitfalls are analyzed in the dedicated Unicode escape lesson.

## 4. Runnable Java 17+ Example

Save the file **`StringLiteralDemo.java`** with the content:

```java
public class StringLiteralDemo {
    public static void main(String[] args) {
        String greeting = "Hello, Java!";
        String empty = "";
        String quoted = "You said: \"Java\"";
        String path = "C:\\docs\\note.txt";
        String twoLines = "Line 1\nLine 2";
        String tabSeparated = "A\tB";

        System.out.println(greeting);
        System.out.println("empty.length() = " + empty.length());
        System.out.println(quoted);
        System.out.println(path);
        System.out.println(twoLines);
        System.out.println(tabSeparated.replace("\t", "[TAB]"));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 StringLiteralDemo.java
java StringLiteralDemo
```

**Stdout** (each line in exact order; the example replaces the tab with `[TAB]` so the tab position is visible):

```text
Hello, Java!
empty.length() = 0
You said: "Java"
C:\docs\note.txt
Line 1
Line 2
A[TAB]B
```

Explanation:

- The literal `""` creates an empty string, so `empty.length()` is `0`.
- In `quoted`, `\"` produces double quotes that appear in stdout.
- In `path`, each `\\` produces **one** `\` character.
- In `twoLines`, `\n` makes `println` display two lines of content.
- `\t` creates a real tab; `replace` only swaps the tab for an observable label when printing the output.

## 5. String Literals, Variables, and String Objects

### Literals Can Be Used in Many Places

A literal is an **expression** of type `String`, not something that only appears on the right-hand side of an assignment:

```java
System.out.println("Ready");
boolean isEmpty = "".isEmpty();
int length = "Java".length(); // 4
String message = "Hello, " + "world";
```

Concatenation with `+` produces a string expression. In Java, `"Java"` does not automatically turn into a variable name, `"123"` does not automatically turn into an integer, and `"Hello, ${name}"` **has no variable interpolation mechanism** with `${...}` syntax. If there is a variable `name`, a simple way is `"Hello, " + name`.

### Why Shouldn't You Compare Strings with `==`?

Java **interns** string literals: literals with the same content usually reference the same object in the string pool. The compiler can also fold concatenation expressions containing only constants at compile time. However, `==` on two `String` references checks **whether they are the same object**, not whether they have the same content.

```java
String first = "Java";
String second = "Java";
String builtAtRuntime = new String("Java");

System.out.println(first == second);         // true
System.out.println(first == builtAtRuntime); // false
System.out.println(first.equals(builtAtRuntime)); // true
```

This is an illustration snippet placed **inside a method**, not a standalone Java file. Use `.equals(...)` to compare content; do not rely on the pool to assume `==` will always be true for two strings with identical text.

A literal is still an *immutable* `String` object. For example, `text.toUpperCase()` returns a new string (or may return the same string if no change is needed), rather than modifying the internal content of the original `String` object.

## 6. Common Mistakes

| Code snippet | Problem | Fix |
|---|---|---|
| `String s = 'Java';` | `'...'` does not create a `String`; multiple characters are also invalid for `char` | `String s = "Java";` |
| `String s = "Java;` | Missing closing `"` | `String s = "Java";` |
| `String s = "C:\temp\file";` | `\t`, `\f` are interpreted as control characters | `String s = "C:\\temp\\file";` |
| `String s = "A "B" C";` | Inner `"` terminates the literal prematurely | `String s = "A \"B\" C";` |
| `String s = "\q";` | `\q` is not a valid escape | Use `\\q` if you need `\` and `q` |
| `String s = ""; if (s == null) ...` | An empty string is not `null` | Check `s.isEmpty()` if checking for emptiness |
| `a == b` with `String` | Compares references | Use `a.equals(b)` when sure `a` is not `null` |

The error rows in the table are diagnostic examples, **not runnable source code**.

### What About Multi-Line Strings?

A **standard** string literal using `"..."`
cannot contain a direct line break in source code:

```java
// INVALID if there is an actual line break inside "..."
String invalid = "Line 1
Line 2";
```

Write `"Line 1\nLine 2"` or concatenate `"Line 1\n" + "Line 2"`. Since Java 15, there is also the **text block** using `"""` for multi-line text; that is a separate syntax suited for presenting large blocks of content, and differs from the standard literal's `"` pair discussed here.

## 7. Self-Check

1. How do `"A"` and `'A'` differ in type?
2. Is `" "` empty? Is `""` equal to `null`?
3. Write a literal representing the exact content `C:\java\src`.
4. Why can `String text = "Line 1\nLine 2";` print two lines even though the source code is on one line?
5. For two `String` variables with the same content, should you use `==` or `.equals()` to check the text?

**Answers:** (1) `String` and `char`; (2) `" "` contains one space, `""` is an empty string distinct from `null`; (3) `"C:\\java\\src"`; (4) `\n` is a newline character in the string's value; (5) `.equals()`.

A valid string literal requires proper double-quote boundaries, appropriate escapes, and a clear awareness of the difference between characters **written in source code** and characters **that actually exist inside the `String` object**.
