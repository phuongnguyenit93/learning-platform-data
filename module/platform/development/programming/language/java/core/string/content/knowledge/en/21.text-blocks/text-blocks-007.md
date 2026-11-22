# `String.stripIndent()` and `String.indent(int)` — Handling Indentation in Java Text Blocks

When writing JSON, HTML, SQL, or multiline messages in Java, **leading whitespace** can serve two different purposes: aligning source code for readability or representing the actual structure of the text. Java provides two methods on `String` to help control them:

- `stripIndent()`: removes **unnecessary common indentation** at the start of lines, preserves relative indentation differences between them, and strips extra trailing whitespace at the end of lines.
- `indent(int n)`: adds or removes **a specified number of indentation characters** for *each line*, while normalizing line terminators.

Both methods are especially useful when working with **text blocks** (`"""..."""`), yet they also apply to any `String`, including data read from files or APIs.

## 1. Why must indentation in text blocks be understood properly?

Java 15 officially introduced text blocks: a way to write multiline strings using triple double quotes. Java code is usually indented inside classes, methods, and conditional blocks; if every whitespace character in source were preserved, the resulting string could be indented far too deeply.

Example:

```java
String html = """
        <ul>
          <li>Java</li>
          <li>String</li>
        </ul>
        """;
```

With the layout above, the actual value of `html` is equivalent to:

```text
<ul>
  <li>Java</li>
  <li>String</li>
</ul>
```

In the actual string, there is also an `\n` character after `</ul>`. The compiler **automatically stripped indentation whitespace attributable to source-code layout** while keeping the two spaces before each `<li>` tag. This mechanism is called stripping *incidental indentation*.

**Key takeaway:** the compiler has already processed the text block's indentation when creating the `String` value. Calling `stripIndent()` again on that text block does not mean Java will keep stripping another arbitrary level of indentation.

## 2. How does `stripIndent()` work?

API signature:

```java
public String stripIndent()
```

`stripIndent()` was added in **Java 15**. The algorithm applied to a multiline string:

1. Split the text into lines. `\n`, `\r`, and `\r\n` are valid line terminators.
2. For **every line that is non-empty according to `isBlank()`**, count the number of leading whitespace characters. **The last line is also considered, even if it is blank.**
3. Pick the smallest among those indentation counts (commonly called *minimum indentation*).
4. Remove that exact number of leading whitespace characters from every **non-blank** line, and remove all trailing whitespace on each line; lines containing only whitespace become empty strings.
5. Rejoin using `\n` (LF), preserving the **number of line terminators** from the input.

For example, using `·` to represent a single space for clarity:

```text
Before stripIndent():
····root··
······child··

After stripIndent():
root
··child
```

The first two lines originally have **4** and **6** leading spaces, respectively. The common indentation is **4**, so the result has **0** and **2** spaces left. The two trailing spaces on each line are stripped.

You can test this yourself:

```java
String text = "    root  \n      child  ";
String output = text.stripIndent();
System.out.println(output.equals("root\n  child")); // true
```

**Difference from `strip()`:** `strip()` only removes whitespace at *both ends of the entire string*; `stripIndent()` examines indentation **line by line** and preserves the internal relative structure.

### Easy-to-miss exception: a trailing newline at the end of the string

Compare:

```java
String a = "    root\n      child";
String b = "    root\n      child\n";

System.out.println(a.stripIndent().equals("root\n  child")); // true
System.out.println(b.stripIndent().equals(b));             // true
```

For `b`, after the final `\n` there is **a final empty line**, whose indentation level is 0. Because the algorithm **still considers the last line even when it is blank**, the common indentation is 0: the two content lines **are not shifted to the left**. This is not a Java bug; it is a direct consequence of the minimum indentation rule.

This matters greatly when receiving strings from files or comparing against text blocks. A text block has line terminators governed by the structure of the literal itself, and the compiler also considers the position of the closing `"""` delimiter to determine incidental indentation before creating the `String`. Therefore, **do not assume calling `stripIndent()` on a `String` ending with LF always matches what the compiler did on a text block**.

## 3. `indent(int n)` adds and removes indentation

API signature:

```java
public String indent(int n)
```

`indent(int)` has existed since **Java 12**. The value of `n` determines how the start of **each line** is adjusted:

| Parameter | Behavior |
| --- | --- |
| `n > 0` | Inserts exactly `n` space characters `U+0020` at the beginning of each line |
| `n = 0` | Leaves line indentation unchanged, **yet still normalizes line endings** |
| `n < 0` | Removes up to `abs(n)` leading whitespace characters from each line; lines with fewer have all their leading whitespace removed |

Spaces on the right side of the content **are not automatically removed** by `indent()`. When `n < 0`, each line is processed individually; it does not compute a minimum common indentation like `stripIndent()`.

Suppose `text = "    root  \n      child  "`:

| Call | Result (`·` is one space, `\n` is an LF character) |
| --- | --- |
| `text.stripIndent()` | `root\n··child` |
| `text.indent(2)` | `······root··\n········child··\n` |
| `text.indent(-2)` | `··root··\n····child··\n` |
| `text.indent(0)` | `····root··\n······child··\n` |

**Note the trailing LF:** `indent()` splits the string into lines using rules similar to `lines()`, then **appends `\n` after each line in the result**. Consequently, a non-empty input string that does not end with a line terminator will **gain a trailing `\n` after calling `indent()`**, even with `indent(0)`. For the empty string `""`, the result remains an empty string.

Example:

```java
System.out.println("A".indent(0).equals("A\n")); // true
System.out.println("".indent(3).equals(""));      // true
```

### A negative number does not mean removing that exact number of spaces

`indent(-4)` removes **up to four leading whitespace characters from each line**. A line with only two leading spaces loses two; a line with six leading spaces ends up with two. If a line already has no indentation, it stays unchanged.

A tab character `\t` counts as **one whitespace character** in this count; Java does not expand tabs to 4 or 8 visual spaces. Results can be surprising when input mixes tabs and spaces.

## 4. Standalone Java 17+ example showing every space clearly

To distinguish spaces and LF, use a `show` method that replaces spaces with `_` and converts actual newlines into the text `\n`.

Create `IndentAndStripIndentDemo.java`:

```java
public class IndentAndStripIndentDemo {

    private static String show(String value) {
        return value.replace(" ", "_")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String raw = "    root  \n      child  ";

        System.out.println("raw          = " + show(raw));
        System.out.println("stripIndent  = " + show(raw.stripIndent()));
        System.out.println("indent(2)    = " + show(raw.indent(2)));
        System.out.println("indent(-2)   = " + show(raw.indent(-2)));
        System.out.println("indent(0)    = " + show(raw.indent(0)));

        String block = """
                root
                  child
                """;

        System.out.println("textBlock    = " + show(block));
        System.out.println("block.indent = " + show(block.indent(2)));

        String withFinalLf = "    root\n      child\n";
        System.out.println("endLF.strip  = "
                + show(withFinalLf.stripIndent()));

        String windowsLines = "  one\r\n    two\r";
        System.out.println("CRLF.indent  = "
                + show(windowsLines.indent(0)));
    }
}
```

Compile and run:

```bash
javac IndentAndStripIndentDemo.java
java IndentAndStripIndentDemo
```

Stdout output (`_` represents **one** actual space in the input string):

```text
raw          = ____root__\n______child__
stripIndent  = root\n__child
indent(2)    = ______root__\n________child__\n
indent(-2)   = __root__\n____child__\n
indent(0)    = ____root__\n______child__\n
textBlock    = root\n__child\n
block.indent = __root\n____child\n
endLF.strip  = ____root\n______child\n
CRLF.indent  = __one\n____two\n
```

Observe three things:

1. `stripIndent()` removes common indentation and trailing whitespace on each line when the input **has no trailing LF**.
2. `indent(2)` and `indent(-2)` preserve spaces at the end of content; every line in the result ends with an LF.
3. The text block already had its incidental indentation stripped by the compiler; calling `block.indent(2)` adds two new spaces to each line.

## 5. Combining text blocks with `indent()` for nested content

A common use case is building HTML snippets, messages, or configuration blocks at different nesting depths:

```java
String item = """
        <li>Java</li>
        <li>Regex</li>
        """;

String html = "<ul>\n"
        + item.indent(2)
        + "</ul>\n";

System.out.print(html);
```

Output:

```html
<ul>
  <li>Java</li>
  <li>Regex</li>
</ul>
```

Analysis: after compilation, the text block `item` is `"<li>Java</li>\n<li>Regex</li>\n"`, so `indent(2)` places two spaces before each tag. This is convenient when creating one text block and nesting it inside another.

**Do not treat `indent()` as an HTML, JSON, or YAML formatter.** It only modifies leading spaces and line terminators, without validating internal syntax. For JSON with values needing escaping, use a serializer; for HTML built from untrusted data, escape data before inserting.

### Adjusting indentation using the closing `"""` delimiter position

In a text block, the amount of incidental indentation stripped usually depends on the line with the fewest spaces **and** the position of the closing `"""`:

```java
String a = """
        first
          second
        """;

String b = """
            first
              second
        """;
```

In `a`, the result is `"first\n  second\n"`. In `b`, the closing delimiter is indented less than the content: the result keeps four spaces before `first` and six before `second`. This allows preserving a fixed indentation level intentionally, though readable text block layout should come first; when indentation needs to increase or decrease **at runtime**, `indent(n)` is clearer.

## 6. Trailing whitespace, blank lines, and newlines

### Trailing whitespace

`stripIndent()` removes whitespace at **the end of each line**, even when that whitespace was intentional. `indent()` does not automatically remove it. If the output format needs to preserve trailing whitespace (certain protocols or representations), choose the API carefully.

In text blocks, the compiler also treats literal trailing whitespace as incidental and typically removes it. Java provides the `\s` escape to represent **an intentional space**:

```java
String withSpace = """
        value\s
        """;

System.out.println(withSpace.equals("value \n")); // true
```

The `\s` escape is processed after incidental whitespace removal, so it can preserve trailing spaces. If you then call `stripIndent()` on `withSpace`, that trailing space can be removed: the runtime method does not know it originated from an escape.

### Blank lines

`stripIndent()` replaces a whitespace-only line with an empty line while preserving the number of newlines. `indent(n)` processes every line according to `n`: for example, when `n > 0`, it still adds spaces to the start of a blank line. Use `show` or `String.equals` to check exact values rather than relying on visual display.

### Normalizing CRLF and CR

Both methods produce results using LF `\n` as the line terminator, even when the input contains CRLF `\r\n` or CR `\r`. Example:

```java
String source = "  A\r\n    B\r";
String output = source.indent(0);
System.out.println(output.equals("  A\n    B\n")); // true
```

This is useful when processing text coming from different operating systems; however, if you must preserve **exact bytes** or the file's original line-ending style, do not treat either method as a lossless operation.

## 7. Choosing a method by requirement

| Scenario | Choice |
| --- | --- |
| Multiline text from another system where all lines share deep indentation | `stripIndent()`, while checking the trailing-blank-line case |
| Existing text block where the whole content should be nested four space columns deeper | `indent(4)` |
| Need to remove up to two leading whitespace characters from **each line** | `indent(-2)` |
| Need to keep indentation as is, only normalizing LF and ensuring a trailing LF on each line | `indent(0)` |
| Need to strip whitespace at both ends of **the entire string**, without line-by-line analysis | `strip()` |
| Need to preserve every original space and CRLF verbatim | Do not call these indentation-normalizing methods |

When indentation carries structural meaning (such as YAML), **do not blindly shift margins with `stripIndent()` without inspecting the input**; in particular, check the final line, blank lines, and intentional whitespace. If consistent common indentation is required, build rules tailored to that format.

## 8. Common mistakes

1. **Calling `stripIndent()` twice expecting each call to reduce indentation by one level.** After the first call, the common indentation may be 0; calling it again is not a way to remove another level.
2. **Overlooking a trailing LF in the string.** The trailing empty line has indentation 0 and can prevent `stripIndent()` from shifting earlier lines left.
3. **Confusing `indent(-n)` with `stripIndent()`.** A negative count trims up to `n` characters per line; it can flatten relative indentation when lines have little whitespace.
4. **Assuming `indent(0)` leaves data unchanged.** It still normalizes CRLF/CR to LF and can append a trailing LF.
5. **Believing `indent(n)` removes trailing whitespace.** Only `stripIndent()` strips trailing line whitespace; `indent()` keeps it.
6. **Mixing tabs and spaces and judging indentation by eye.** One tab character counts as one character rather than its visual column width; alignment can vary across editors.
7. **Adding `stripIndent()` to a properly structured text block.** The compiler already removed incidental indentation. Check the actual `String` before modifying it further.
8. **Forgetting `String` immutability.** Both methods return a new string; assign or use the return value: `text = text.indent(2);` if you want to keep the change.

## 9. Knowledge check

**Question 1.** What does `"   one\n     two".stripIndent()` return?

Answer: `"one\n  two"`. The minimum common indentation is three spaces.

**Question 2.** Is `"A".indent(0).equals("A")` `true` or `false`?

Answer: `false`. The result is `"A\n"`, because `indent()` appends an LF at the end of the line.

**Question 3.** What string does `"  A\n B".indent(-3)` produce?

Answer: `"A\nB\n"`. Each line loses up to three leading whitespace characters, then gets a trailing LF.

**Question 4.** Why does `"  A\n  B\n".stripIndent()` still keep two spaces at the start of each line?

Answer: the last line after the LF character is an empty line with indentation 0, making the minimum indentation equal to 0.

**Question 5.** A text block already contains `"A\n  B\n"`. How do you add four spaces before each line while keeping the two relative spaces before `B`?

Answer: `text.indent(4)`, resulting in `"    A\n      B\n"`.

**Remember:** `stripIndent()` finds and removes *common indentation* (while also stripping trailing line whitespace); `indent(n)` adds or subtracts *a fixed indentation amount per line* and always normalizes line endings. Text blocks handle incidental indentation at compile time, so distinguish **source-code text** from **the runtime `String` value**.

## Official documentation

- [`String.indent(int)` and `String.stripIndent()`, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Text Blocks — Oracle Java Language Guide](https://docs.oracle.com/en/java/javase/21/language/text-blocks.html)
