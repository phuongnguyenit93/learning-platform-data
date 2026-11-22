# Character Literals and String Literals in Java 17+

When you write `'A'` and `"A"`, you are creating **two different kinds of values**: `'A'` is a character literal of type `char`, whereas `"A"` is a string literal of type `String`. Single quotes, double quotes, escapes, and the number of characters inside determine whether the code snippet is valid.

This lesson helps you declare, print, compare, and handle those literals with Java 17+, while avoiding confusion between **a UTF-16 code unit** and **a full Unicode character**.

## 1. Distinguishing `char` and `String`

| Aspect | Character literal | String literal |
| --- | --- | --- |
| Syntax | `'A'` | `"A"` |
| Java type | `char`, 16-bit *primitive* type | `String`, *immutable* reference type |
| Number of code units represented | Exactly one UTF-16 code unit | Can be 0, 1, or many UTF-16 code units |
| Empty | `''` is **invalid** | `""` is valid |
| Line break | `'\n'` | `"\n"` |
| Concatenation | No `concat` method on `char` | `"Ja" + "va"` produces `"Java"` |
| Reading length | Cannot call `.length()` on `char` | `"Java".length()` returns 4 |

Example:

~~~java
char grade = 'A';
String gradeText = "A";
String empty = "";
String message = "Xin chao!";
~~~

Although `grade` and `gradeText` both display the letter A, they **do not have the same type**. `char` stores one code unit (a 16-bit unsigned integer value); `String` represents a sequence of code units and provides many string manipulation methods.

Note: a Unicode character like the emoji `🚀` typically requires **two UTF-16 code units** (a surrogate pair). Thus `"🚀"` is valid, whereas the entire emoji cannot fit inside a single `char` literal.

## 2. Escapes and the `char`/`String` boundary

In both character literals and string literals, the backslash starts an escape. An appropriate escape can represent **one code unit** that we do not type directly:

| Java source | Runtime value | Example type |
| --- | --- | --- |
| `'\n'` | One LF char, code 10 | `char` |
| `"\n"` | String of length 1 UTF-16 unit containing LF | `String` |
| `'\\'` | One backslash char | `char` |
| `"\\n"` | String consisting of backslash and letter n, length 2 | `String` |
| `'\''` | One single-quote char | `char` |
| `"Say \"hi\""` | String containing two double quotes | `String` |

What needs to be checked is **the type and length of the value after interpreting the literal**, not counting the characters typed in source code. Escapes `\t`, `\r`, `\b`, and `\f` also have specific uses; for instance, `"\t"` contains one tab code unit.

Unicode escapes such as `\u0041` are a different mechanism: Java processes Unicode escapes **before tokenization**, even in places that look like comments. Therefore, do not use the Unicode escape for LF to insert a newline into a normal string literal; use `"\n"` or `'\n'`. Examples handling backslashes, quotes, paths, and multiple escape layers are analyzed thoroughly in the dedicated lesson on escape sequences.


## 3. Runnable Java 17+ program

Save a UTF-8 file named **`CharacterStringDemo.java`**:

~~~java
public class CharacterStringDemo {
    public static void main(String[] args) {
        char first = 'J';
        char newline = '\n';
        char apostrophe = '\'';

        String language = "Java";
        String greeting = "Xin chao, " + language + "!";
        String twoLines = "dong 1\ndong 2";
        String rocket = "🚀";

        String block = """
                Alpha
                Beta
                """;

        System.out.println("char=" + first);
        System.out.println("newlineCode=" + (int) newline);
        System.out.println("apostrophe=" + apostrophe);
        System.out.println("greeting=" + greeting);
        System.out.println("lines=" + twoLines.replace("\n", "|"));
        System.out.println("length=" + language.length());
        System.out.println("rocketUnits=" + rocket.length());
        System.out.println(
                "rocketPoints=" + rocket.codePointCount(0, rocket.length()));
        System.out.println("block=" + block.replace("\n", "|"));
        System.out.println("equals=" + language.equals("Java"));
    }
}
~~~

Open a terminal in the directory containing the file (Windows PowerShell or Linux Bash):

~~~bash
java -version
javac -version
javac -encoding UTF-8 CharacterStringDemo.java
java CharacterStringDemo
~~~

**Expected output:**

~~~text
char=J
newlineCode=10
apostrophe='
greeting=Xin chao, Java!
lines=dong 1|dong 2
length=4
rocketUnits=2
rocketPoints=1
block=Alpha|Beta|
equals=true
~~~

Explanation of notable results:

1. `(int) newline` converts the `char` value of LF to the integer `10`.
2. `twoLines` genuinely contains a newline; `replace("\n", "|")` makes the boundary between the two lines visible when printed.
3. `rocket.length() == 2` because emoji U+1F680 occupies two UTF-16 code units. `codePointCount(...) == 1` because it is one Unicode code point.
4. Text block `""" ... """` has been supported since Java 15, so it works in Java 17. This literal contains newlines and strips common indentation; because there is a trailing newline, `replace` produces `Alpha|Beta|`.
5. `equals` compares **string content**, not whether two variables refer to the same object.

You can try `java CharacterStringDemo.java` on JDK 17+ to run the source file directly without invoking `javac` separately. The program output remains the same as above.

## 4. When you need multi-line strings: text blocks

Java 17 supports text blocks `"""` (standardized since Java 15), which still produce a **`String`**, not a new character type. The opening delimiter `"""` must be followed by a newline; the compiler strips common indentation to make source formatting convenient:

~~~java
String normal = "A\nB";
String multi = """
        A
        B
        """;
~~~

The two strings above are not completely equal: `multi` has a **trailing newline**, whereas `normal` does not. Placing the closing delimiter right after `B` instead of on its own line is one way to omit the trailing newline. A text block can contain ordinary double quotes and escapes, though leading/trailing spaces are also subject to separate indentation and whitespace processing rules. When exact content matters, verify using `length()` or by making newlines visible; operations like `\s`, line continuation, and closing delimiter placement are covered in depth in the text block lesson.


## 5. Common mistakes

| Code snippet | Result | Fix |
| --- | --- | --- |
| `char c = 'A';` | Valid | A `char` literal |
| `String s = "A";` | Valid | A `String` literal |
| `char c = '';` | Compile error | `char` must contain one code unit; if empty is needed, use `String s = "";` |
| `char c = 'AB';` | Compile error | Use `String s = "AB";` |
| `String s = 'A';` | Type error | Use `String s = "A";` |
| `char c = "A";` | Type error | Use `char c = 'A';` |
| `String s = "C:\temp";` | Likely unintended: `\t` is a tab | Use `"C:\\temp"` |
| `String s = "a\nb";` | Valid: contains a newline at runtime | If you want to see `\n` literally, use `"a\\nb"` |
| `String s = "a" + "b";` | Valid | Produces content `ab` |

**Comparing strings:** avoid using `==` to check the content of two arbitrary `String`s. `==` compares references; `equals` compares content. In the running example, `language.equals("Java")` returns `true`.

**Immutability:** `String` does not change its content after creation. For example, calling `language.concat(" 17")` returns a **new string**, without modifying the value of `language` unless you assign the result.

## 6. Short exercises

**Exercise 1.** Choose the right types for a single letter `K` and a string `"K"`; explain why `'KK'` is invalid.

*Answer:* `char c = 'K';` and `String s = "K";`. `'KK'` has two code units, not a single `char`.

**Exercise 2.** Predict `"Hi\nJava".length()` and `"Hi\\nJava".length()`.

*Answer:* `7` and `8`. The first string contains one LF character; the second string contains two characters: a backslash and the letter `n`.

**Exercise 3.** In `CharacterStringDemo`, replace `language = "Java"` with `"Kotlin"`. What will the values of `greeting` and `equals` be?

*Answer:* `Xin chao, Kotlin!` and `false`.

**Exercise 4.** Write a literal containing the exact line of text `C:\work\java`.

*Answer:* `"C:\\work\\java"`.

**Exercise 5.** Why is `"🚀".length()` equal to 2 while `codePointCount` is 1?

*Answer:* A code point outside the BMP is encoded as **two UTF-16 code units**. `String.length()` counts code units; `codePointCount` counts code points (not necessarily the number of *grapheme clusters* perceived by human eyes).

## Key takeaway

- **`'A'` → `char`** (one UTF-16 code unit); **`"A"` → `String`** (character sequence, may be empty).
- Use `\n`, `\t`, `\`, `\"`, `\'` appropriately; distinguish **string escapes** from **Unicode escapes processed before tokenization**.
- `String` is immutable; compare content using `equals`; `length()` counts UTF-16 code units.
- A **text block** `""" ... """` is also a `String`, useful for multi-line content in Java 17+.
