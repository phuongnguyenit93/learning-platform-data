# Distinguishing Character Arithmetic Addition from String Concatenation in Java

In Java, the `+` operator has **two roles**: performing arithmetic addition or string concatenation. Because `char` stores a 16-bit character code unit with a numeric value, the expression `'A' + 1` does **not** mean joining the letter `A` with the digit `1`: Java promotes `char` to `int` and adds them, yielding `66`. Conversely, `"A" + 1` has a `String` operand, so it produces the string `"A1"`.

This distinction is crucial when printing logs, building strings, handling digit characters, shifting characters, and reading expressions with multiple `+` operators. Simply replacing single quotes with double quotes, adding an empty string, or placing parentheses differently can change **both the result type and its value**.

## 1. Distinguishing `char`, `String`, and `int`

| Expression | Type | Meaning |
| --- | --- | --- |
| `'A'` | `char` | A UTF-16 code unit corresponding to the character `A` (value `U+0041`, decimal 65) |
| `"A"` | `String` | A string object whose content is the letter `A` |
| `1` | `int` | The integer value one |
| `'1'` | `char` | The digit character `1` (value `U+0031`, decimal 49) |
| `"1"` | `String` | A string consisting of the character `1` |

**Single quotes `'...'` are not the same as double quotes `"..."`.**

- `'A'` is a primitive `char` value that can participate in arithmetic operations.
- `"A"` is a `String`, which makes the `+` operator in a binary expression perform string concatenation.
- `'1'` carries the character code value of the digit, **not the integer 1**.
- `"1"` is a string. To convert the content of a digit string into a number, you can use `Integer.parseInt("1")` and handle input errors when needed.

For familiar characters in the ASCII table (which are also part of Unicode), `'A'` has code value 65; `'B'` has code value 66; `'0'` has code value 48; `'1'` has code value 49.

## 2. Rules of the `+` operator

### When adding numeric operands, `char` is promoted to `int`

If both operands are primitive numeric types suitable for arithmetic addition, Java applies **binary numeric promotion**. For `char`, `byte`, and `short`, the value is promoted to at least `int` before computation.

Examples:

```java
int a = 'A' + 1;    // 65 + 1 = 66
int b = 'A' + 'B';  // 65 + 66 = 131
int c = 1 + '2';   // 1 + 50 = 51
```

The result of `'A' + 1` is an `int`, not a `char`. Java **does not automatically convert code 66 into the character `B`** just because the first operand is a `char`.

### When one operand is `String`, `+` concatenates strings

If at least one operand of binary `+` is `String`, Java performs **string concatenation**. The other operand is converted into an appropriate textual representation:

```java
String a = "A" + 1;   // "A1"
String b = 'A' + "1"; // "A1"
String c = "A" + 'B'; // "AB"
String d = "" + 42;   // "42"
```

In the examples above, the `char` operand is represented as a **character** when participating in concatenation with `String`: `'A' + "1"` produces `"A1"`, not `"651"`.

The two modes of `+` are **semantically different**, rather than being the same addition where Java arbitrarily chooses how to print the result.

## 3. Complete example: the same letter A, completely different results

Create the file `CharPlusDemo.java`:

```java
public class CharPlusDemo {
    public static void main(String[] args) {
        System.out.println('A');
        System.out.println('A' + 1);
        System.out.println("A" + 1);
        System.out.println('A' + "1");
        System.out.println('A' + 'B');
        System.out.println("" + 'A' + 'B');
        System.out.println(String.valueOf('A' + 1));
        System.out.println(String.valueOf((char) ('A' + 1)));
    }
}
```

Compile and run on Java 17 or later:

```bash
javac -encoding UTF-8 CharPlusDemo.java
java CharPlusDemo
```

Exact output:

```text
A
66
A1
A1
131
AB
66
B
```

Each line illustrates a rule:

1. `println('A')` calls the overload with a `char` parameter, so it prints the character `A`.
2. `'A' + 1` is numeric addition: 65 + 1 = 66; `println` receives the integer result and prints `66`.
3. `"A" + 1` has a `String`, so it concatenates into `A1`.
4. `'A' + "1"` also has a `String`, so it concatenates into `A1`.
5. `'A' + 'B'` is integer addition: 65 + 66 = 131.
6. `"" + 'A' + 'B'` starts with string concatenation and continues concatenating both characters into `AB`.
7. `String.valueOf('A' + 1)` receives the `int` value 66, so it returns the string `"66"`.
8. `(char) ('A' + 1)` casts 66 to `char`, corresponding to the character `B`; `String.valueOf(char)` returns `"B"`.

**Remember:** seeing the letter `A` in source code is not enough on its own to tell whether the program will print `A` or `65`. You must determine the **type of the entire expression** passed to `println`.

## 4. Left-to-right associativity and the role of parentheses

Grouping order determines whether character code addition happens **before or after** the expression becomes a `String`:

```java
System.out.println('A' + 1 + "!");      // 66!
System.out.println("!" + 'A' + 1);      // !A1
System.out.println("value=" + ('A' + 'B')); // value=131
```

Use parentheses when you want to compute numeric codes first. The lesson **Left-to-right associativity of + with numbers and strings** explains associativity, precedence, and expression evaluation order separately; here the focus is the **`int` type of `char` addition**.

## 5. A digit character is not its corresponding numeric value

A common mistake is using `'5' + 2` when intending to compute `5 + 2`. `'5'` stores the character code `U+0035` (decimal 53), so `'5' + 2` returns `55`, not `7`.

File `DigitCharDemo.java`:

```java
public class DigitCharDemo {
    public static void main(String[] args) {
        char digitChar = '5';

        System.out.println("digitChar=" + digitChar);
        System.out.println("codeUnit=" + (int) digitChar);
        System.out.println("charPlusTwo=" + (digitChar + 2));
        System.out.println("numericValue=" + (digitChar - '0'));
        System.out.println("numericPlusTwo=" + (digitChar - '0' + 2));
        System.out.println("Character.digit=" + Character.digit(digitChar, 10));
        System.out.println("String.parse=" +
                Integer.parseInt(String.valueOf(digitChar)));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DigitCharDemo.java
java DigitCharDemo
```

Output:

```text
digitChar=5
codeUnit=53
charPlusTwo=55
numericValue=5
numericPlusTwo=7
Character.digit=5
String.parse=5
```

**Why does `digitChar - '0'` give 5?** The ASCII digit characters `'0'` through `'9'` have consecutive codes from 48 to 57, so `'5' - '0'` is 53 − 48 = 5. This is a useful formula **if you have already verified that the character is in `'0'..'9'`**.

`Character.digit(digitChar, 10)` is a clearer choice when handling a digit character recognized by Java in base 10; it returns `-1` when the character is invalid for that radix. `Integer.parseInt(...)` is appropriate when the input is an entire digit string, possibly multi-character, and you need to catch format errors.

Do not blindly apply `c - '0'` to every Unicode character that looks like a digit: digits across different writing systems do not all sit near ASCII `'0'`.

## 6. `char` variables in addition and assignment back to `char`

`char` is an **unsigned 16-bit** primitive type used to represent a UTF-16 code unit. When added to an integer, the usual result is `int`. Therefore, with a `char` **variable**:

```java
char c = 'A';
int number = c + 1;            // 66
char next = (char) (c + 1);    // 'B'
// char wrong = c + 1;         // Compile error: int does not narrow to char automatically
```

This is an illustrative snippet placed inside a method.

However, Java has an **exception for compile-time constant expressions**. A constant expression of type `int` whose value falls within the `char` range can be assigned directly to a `char` variable:

```java
char fromConstant = 'A' + 1; // Valid: integer constant 66 is within char range

char letter = 'A';
// char fromVariable = letter + 1; // Invalid: result is int
char fromCast = (char) (letter + 1); // Valid
```

Thus, saying “`char` plus `int` can **never** be assigned to `char`” is inaccurate: the addition **still has type `int`**, but the assignment rule allows **implicit narrowing of an integer constant expression within the `char` bounds**. Meanwhile `letter + 1` involves a variable, so it is not a constant expression under that rule.

### How do `+=` and `++` work?

With compound assignment, Java allows converting the operation's result back to the type of the left-hand variable under a dedicated rule:

```java
char c = 'A';
c += 1; // B
c++;    // C
```

This **does not make the expression `c + 1` have type `char`**. It simply means that in the compound assignment `c += 1`, Java performs the operation and converts the result to `c`'s type according to the semantics of `+=`. Be careful with large values: converting back to `char` keeps only the low 16 bits of the numeric value, and is not guaranteed to produce the intended Unicode character.

File `CharArithmeticAssignment.java`:

```java
public class CharArithmeticAssignment {
    public static void main(String[] args) {
        char fromConstant = 'A' + 1;
        char fromVariable = 'A';
        int beforeCast = fromVariable + 1;
        char fromCast = (char) beforeCast;

        fromVariable += 1;
        fromVariable++;

        System.out.println("constant=" + fromConstant);
        System.out.println("intResult=" + beforeCast);
        System.out.println("cast=" + fromCast);
        System.out.println("compound=" + fromVariable);
    }
}
```

Run:

```bash
javac -encoding UTF-8 CharArithmeticAssignment.java
java CharArithmeticAssignment
```

Output:

```text
constant=B
intResult=66
cast=B
compound=C
```

Using character-code addition to shift letters is **not** a general natural-text processing technique: Unicode contains non-contiguous ranges, accented letters, and supplementary characters. Even using `c++` for ASCII characters should be restricted to technical tasks with input validation and bounds checks.

## 7. When passing to `print` or `println`, the argument type determines how it prints

The `PrintStream` class has multiple overloads, including `println(char)`, `println(int)`, and `println(String)`. Java chooses the method matching the **expression's type** at compile time.

| Statement | Argument expression type | Printed output |
| --- | --- | --- |
| `System.out.println('A');` | `char` | `A` |
| `System.out.println((int) 'A');` | `int` | `65` |
| `System.out.println('A' + 1);` | `int` | `66` |
| `System.out.println((char) ('A' + 1));` | `char` | `B` |
| `System.out.println("A" + 1);` | `String` | `A1` |
| `System.out.println('A' + "1");` | `String` | `A1` |

This explains why the same `'A'` sometimes prints as the letter `A`, sometimes as `65`, or as the number `66`.

If you need to display the **numeric code** of a `char`, cast it explicitly to `int`: `(int) c`. If you need to display the **character after a calculation**, decide whether converting the number back to `char` is genuinely valid for your problem.

## 8. Joining characters into a string: clearer alternatives

When you want to concatenate two characters without adding their codes, several options express your intent clearly:

### Use a `String` as an operand

```java
char first = 'J';
char second = 'a';

String joined = "" + first + second; // "Ja"
```

This approach is simple and avoids turning the `char` values into numbers. However, in longer code or loops, you can choose a more dedicated string-building tool to make intent clear.

### Use `StringBuilder`

```java
StringBuilder builder = new StringBuilder();
builder.append('J');
builder.append('a');
String joined = builder.toString(); // "Ja"
```

`StringBuilder.append(char)` appends **the character represented by the code unit**, without adding numeric values. This is usually the right choice when building strings across multiple steps or inside loops. Do not rely on which internal class Java uses to execute a particular concatenation expression; JDKs may choose different optimization strategies.

### Use `String.valueOf(char)`

```java
char letter = 'A';
String text = String.valueOf(letter); // "A"
```

Distinguish `String.valueOf(letter)` (argument is `char`) from `String.valueOf(letter + 1)` (argument is already `int`). The clearest way to produce text from a character is to pass **the character itself** or a character array to the appropriate API, without adding numeric codes unless the problem genuinely calls for it.

## 9. `char` is only one UTF-16 code unit, not every complete Unicode character

In the examples above, `'A'` and `'5'` are both BMP characters, so each is both one `char` and one Unicode code point. However, not every Unicode character fits in a single `char`. For instance, the emoji 😀 (`U+1F600`) requires **a surrogate pair consisting of two `char` values** in UTF-16.

Therefore:

- `char` participates in addition using its **code unit** value, which is not automatically a complete Unicode code point.
- You cannot obtain a non-BMP Unicode code point simply by taking one `char` from a surrogate pair and adding numbers to it.
- If you need to handle Unicode codes as single units, use `int` to store code points; APIs such as `String.codePointAt(...)` and `Character.toChars(int)` support working with code points.

File `CodePointVsChar.java`:

```java
public class CodePointVsChar {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));

        System.out.println("length=" + emoji.length());
        System.out.printf("firstUnit=U+%04X%n", (int) emoji.charAt(0));
        System.out.printf("codePoint=U+%X%n", emoji.codePointAt(0));
        System.out.println("concat=" + ("X" + emoji));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CodePointVsChar.java
java CodePointVsChar
```

Output (the console must support emoji rendering to display the last line properly):

```text
length=2
firstUnit=U+D83D
codePoint=U+1F600
concat=X😀
```

When concatenating `"X" + emoji`, Java concatenates the entire `String` content. When performing arithmetic on `emoji.charAt(0)`, you are operating on **only one half of a surrogate pair**, not the whole emoji.

## 10. Common mistakes and how to avoid them

- `'1' + 2` gives `51`, because `'1'` has code 49 rather than the number 1.
- `'A' + 'B'` gives `131` (`int`), while `"" + 'A' + 'B'` gives `"AB"`.
- `String.valueOf('A' + 1)` receives `int` and gives `"66"`; use `String.valueOf((char) ('A' + 1))` to produce `"B"` when the conversion makes sense.
- `char next = c + 1` does not compile if `c` is a variable; the implicit narrowing exception applies only to valid `int` **constant expressions**.
- A `char` may be only half of a surrogate pair; do not apply ASCII addition/subtraction tricks to general Unicode text.

## 11. Self-check questions

**Question 1.** What does the following snippet print?

```java
System.out.println('A' + 2);
System.out.println("A" + 2);
System.out.println('A' + "2");
```

**Answer:** `67`, `A2`, `A2`. Only the first line adds a character code to an integer.

**Question 2.** Why is `'1' + '2'` neither the number 3 nor the string `"12"`?

**Answer:** Both operands are `char`, so they are promoted to `int` and their codes are added: `49 + 50 = 99`. To compute 1 + 2, convert the digits to numbers; to join them into `"12"`, use `String`.

**Question 3.** How does `"result=" + 'A' + 1` differ from `"result=" + ('A' + 1)`?

**Answer:** The first expression prints `result=A1` because string concatenation begins right from `"result="`. The second prints `result=66` because the addition inside parentheses is performed before concatenation.

**Question 4.** Is `char c = 'A' + 1;` valid? What about `char c = 'A'; char d = c + 1;`?

**Answer:** The first case is valid because `'A' + 1` is an **`int` constant expression** whose value 66 is within the `char` range. The second case is invalid because `c + 1` depends on a variable, and an `int` result is not automatically narrowed to `char` in a regular assignment.

**Question 5.** When you want to build the string `"Hi"` from `char a = 'H'; char b = 'i';`, how should you write it?

**Answer:** You can write `String result = "" + a + b;` or `new StringBuilder().append(a).append(b).toString()`. Do not use `a + b` because that performs numeric addition.

**Takeaway:** `char + number` or `char + char` is **numeric addition** after promotion to `int`; `String + value` is **string concatenation**. To do arithmetic, check operand types; to join characters, form an explicit `String` concatenation; and when multiple `+` signs appear, use parentheses to express your exact intent.
