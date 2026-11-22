# The `+` Operator and Value-to-String Conversion in Java

## 1. When is `+` string concatenation?

In Java, the `+` symbol is used for two purposes: **numeric addition** and **string concatenation**. When one operand of `+` has type `String`, that operation produces a `String` value by concatenating the textual representations of the two operands in left-to-right order.

```java
String language = "Java";
int version = 17;

String message = language + " " + version;
System.out.println(message); // Java 17
```

In this example, `version` is an `int` integer, but it is converted to the text `"17"` when participating in concatenation with `String`. The final result is a string, not arithmetic addition.

Three concepts should be distinguished:

- **`String` object:** represents text in Java; its content cannot be modified in place.
- **`+` operator:** forms a string concatenation expression when there is a `String` operand; it can also add numbers if the appropriate operands are numeric types.
- **Conversion to string:** produces the textual representation of an `int`, `double`, `boolean`, `char`, object, or `null` value to participate in concatenation.

Short code snippets in this lesson are understood to be written **inside a Java method**, except for the complete program with `class` and `main` in a later section.

## 2. Rules for distinguishing numeric addition from string concatenation

### Case 1: both operands are numeric

```java
int result = 2 + 3;          // 5
double total = 2.5 + 1.5;   // 4.0
```

This is arithmetic addition. Primitive numeric types may undergo **numeric promotion** according to Java rules. No `String` has appeared yet, so there is no string concatenation yet.

### Case 2: one operand is `String`

```java
String one = "Java" + 17;     // "Java17"
String two = 17 + "Java";     // "17Java"
String three = "score=" + 5; // "score=5"
```

Java performs **string conversion** on the remaining operand. Concatenation preserves order: `"Java" + 17` is different from `17 + "Java"`.

A numeric value placed inside double quotes is already a string:

```java
String digits = "17"; // String
int number = 17;      // int
```

`"17" + 3` yields `"173"`, whereas `17 + 3` yields the number `20`.

### Case 3: not every type can be used with `+`

For example, two arbitrary objects cannot be added together simply because they have a `toString()` method:

```java
Object a = new Object();
Object b = new Object();

// Object invalid = a + b; // Does not compile
String valid = "objects: " + a + ", " + b;
```

On the valid line, each concatenation has a `String` operand. Java converts the objects to their textual representations; the default representation of `Object` is typically the class name followed by a hexadecimal hash code, not a meaningful description of business data.

## 3. Left-to-right associativity: the `"1" + 2 + 3` trap

`+` operations at the same precedence level are left-associative: `1 + 2 + "3"` produces `"33"`, while `"1" + 2 + 3` produces `"123"`. Parentheses make clear which numeric addition must happen first:

```java
System.out.println("sum=" + 2 + 3);   // sum=23
System.out.println("sum=" + (2 + 3)); // sum=5
```

Multiplication still has higher precedence than `+`. The lesson **Left-to-right associativity of + with numbers and strings** expands on expression breakdown tables, examples with side effects, and overflow traps; here you only need to recognize when `+` is returning a number versus a `String`.

## 4. How does Java convert values to strings?

For `String` concatenation, Java converts the remaining operands according to **the language's string conversion rules**. The table below lists common cases.

| Value participating in concatenation | Typical textual representation | Example |
|---|---|---|
| `int` | Decimal digits, possibly with a minus sign | `"n=" + 42` → `"n=42"` |
| `long` | Digits of the long integer | `"n=" + 42L` → `"n=42"` |
| `double` | Decimal representation of the floating-point number | `"x=" + 2.5` → `"x=2.5"` |
| `boolean` | `"true"` or `"false"` | `"ok=" + true` → `"ok=true"` |
| `char` | The character represented by the `char` value | `"c=" + 'A'` → `"c=A"` |
| `String` | Existing string content | `"A" + "B"` → `"AB"` |
| `null` reference | The text `"null"` | `"x=" + (String) null` → `"x=null"` |
| Regular object | Based on its `toString()` representation | Can be customized in the class |

For integer values, string concatenation **does not perform numeric addition** again. Java simply obtains the textual representation of the value at the point concatenation is needed.

For `float`/`double`, the default representation of the concatenation operator is not a locale-aware number formatter for end users. If you need thousands separators, fixed-decimal rounding, or locale rules, use formatting APIs such as `String.format(...)`, `NumberFormat`, or `DecimalFormat` according to the specific requirements.

### Objects: the role of `toString()`

For a non-`null` object, the string conversion rule can rely on that object's `toString()` method. A class often overrides `toString()` to provide a meaningful representation:

```java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book(" + title + ")";
    }
}
```

When used inside a method of another class:

```java
Book book = new Book("Java");
System.out.println("item=" + book);
// item=Book(Java)
```

`toString()` is a textual description of the object—it is not necessarily normalized data, not a JSON interchange format, and should not include sensitive information by default. In real systems, design `toString()` appropriately for debugging or display purposes.

## 5. `null` in string concatenation: not the same as calling a method on `null`

A `String` reference can hold the value `null`:

```java
String name = null;

System.out.println("name=" + name); // name=null
```

Concatenation turns the `null` variable `name` into the text `"null"`. The result is an ordinary string `"name=null"`; it is **not** a `null` object.

However, that does not mean you can call methods on a `null` reference:

```java
String name = null;

// name.concat("!"); // NullPointerException
// name.length();     // NullPointerException

System.out.println("name=" + name); // Valid
```

Distinguish between:

- **String conversion in `+`:** has a specific rule to represent a `null` reference as `"null"`.
- **Method call `name.concat(...)`:** requires `name` to refer to a `String` object; if `null`, it throws `NullPointerException`.

If `"null"` is unwanted output, you must define how to handle missing data:

```java
String name = null;
String display = name == null ? "(not available)" : name;
System.out.println("Name: " + display);
// Name: (not available)
```

This is a display policy decided by the program. Do not confuse the four-character string `"null"` with an actual `null` reference.

## 6. `char` can be a character or participate in numeric addition

`char` is a UTF-16 code unit that can participate in numeric addition after numeric promotion; when placed next to a `String`, it is concatenated as text:

```java
System.out.println('A' + 1);       // 66 (int)
System.out.println("A" + 1);       // A1
System.out.println("" + 'A' + 1);  // A1
```

Adding `char` code values is not how to process arbitrary Unicode code points. The lesson **Distinguishing character arithmetic addition from string concatenation** analyzes type conversion, digit characters, parentheses, and surrogate pairs.

## 7. Arrays do not concatenate element-by-element automatically

Suppose you have an array of numbers:

```java
int[] numbers = {1, 2, 3};
```

The expression `"numbers=" + numbers` does not produce `"numbers=[1, 2, 3]"` under general rules. An array is an object; if not converted into a dedicated description, its default representation typically contains array type information and a hash code, making it unsuitable as the intended output. The hash portion may vary across runs.

Choose an API that matches your intent:

```java
int[] numbers = {1, 2, 3};
String readable = "numbers=" + java.util.Arrays.toString(numbers);

System.out.println(readable); // numbers=[1, 2, 3]
```

For multidimensional arrays, you may need `Arrays.deepToString(...)` to represent nested arrays.

### The `char[]` case also requires attention

```java
char[] letters = {'J', 'a', 'v', 'a'};

String actualText = new String(letters);
System.out.println("letters=" + actualText); // letters=Java
```

Do not assume that the `+` operator will automatically join the elements of a `char[]` the way `new String(letters)` does. There are `String.valueOf` overloads specifically for `char[]`, but concatenating through an array reference is not an arbitrary call to that overload.

## 8. Complete Java 17+ example and stdout

Save to the file **`StringPlusConversionDemo.java`**:

```java
import java.util.Arrays;

public class StringPlusConversionDemo {
    public static void main(String[] args) {
        String language = "Java";
        int release = 17;
        double rating = 4.5;
        boolean supported = true;

        String summary = "summary=" + language + " " + release
                + ", rating=" + rating + ", supported=" + supported;
        System.out.println(summary);

        System.out.println("left=" + 2 + 3);
        System.out.println("right=" + (2 + 3));
        System.out.println(2 + 3 + " points");
        System.out.println("value=" + 2 + 3 * 4);

        char letter = 'A';
        System.out.println("letter=" + letter + 1);
        System.out.println("code=" + (letter + 1));
        System.out.println("next=" + (char) (letter + 1));

        String missing = null;
        System.out.println("missing=" + missing);
        System.out.println("valueOfMissing=" + String.valueOf(missing));

        int[] numbers = {1, 2, 3};
        System.out.println("numbers=" + Arrays.toString(numbers));

        char[] letters = {'J', 'a', 'v', 'a'};
        System.out.println("letters=" + new String(letters));

        System.out.println("joined=" + String.join(" | ", "A", "B", "C"));

        String source = "Hi";
        String modified = source + "!";
        System.out.println("source=" + source + ", modified=" + modified);

        String folded = "Ja" + "va";
        System.out.println("foldedSameLiteral=" + (folded == "Java"));
    }
}
```

Run using **JDK 17 or later** in the folder containing the file:

```bash
javac -encoding UTF-8 StringPlusConversionDemo.java
java StringPlusConversionDemo
```

**Exact stdout:**

```text
summary=Java 17, rating=4.5, supported=true
left=23
right=5
5 points
value=212
letter=A1
code=66
next=B
missing=null
valueOfMissing=null
numbers=[1, 2, 3]
letters=Java
joined=A | B | C
source=Hi, modified=Hi!
foldedSameLiteral=true
```

Explanation of the key results:

1. `summary` converts `int`, `double`, and `boolean` to text and concatenates them in order.
2. `"left=" + 2 + 3` concatenates sequentially into `"left=23"`, while `"right=" + (2 + 3)` adds the numbers in parentheses first, yielding `"right=5"`.
3. `2 + 3 + " points"` adds the first two numbers to get `5` and then concatenates `" points"`.
4. Multiplication in `"value=" + 2 + 3 * 4` has higher precedence than `+`, so `3 * 4 = 12`, ultimately producing `"value=212"`.
5. The character `'A'` plus `1` gives the numeric value `66`, but when participating in left-to-right concatenation after a string it produces the text `"A1"`.
6. The reference `missing` is `null`; concatenation and `String.valueOf(missing)` both produce the `"null"` representation in this case.
7. `Arrays.toString` represents the array element values; `new String(letters)` creates text from the `char` array.
8. `source + "!"` produces a result stored in `modified`, without modifying the content of `source`.
9. `"Ja" + "va"` is a **constant string expression** resolved at compile time; the constant string value is interned so it shares the same reference as the literal `"Java"`.

## 9. `String.valueOf(...)`: explicitly converting a value to a string

When you need to explicitly convert a value to a `String` before further processing, use the appropriate `String.valueOf(...)` overloads.

```java
String number = String.valueOf(42);       // "42"
String yes = String.valueOf(true);        // "true"
String letter = String.valueOf('A');      // "A"
String pi = String.valueOf(3.5);          // "3.5"

Object missing = null;
String absent = String.valueOf(missing);  // "null"
```

Notable detail: `String.valueOf` has multiple overloads such as `int`, `long`, `double`, `boolean`, `char`, `char[]`, and `Object`. The compiler selects an overload based on the **static type of the argument expression**.

Example of an important difference with character arrays:

```java
char[] chars = {'J', 'a', 'v', 'a'};

String a = String.valueOf(chars);          // "Java" (char[] overload)
String b = String.valueOf((Object) chars); // Array object representation
```

`b` is not guaranteed to be `"Java"`; it takes the `Object` overload and may contain the type `[C` along with a hash code.

**Be careful with an untyped `String.valueOf(null)`.** Because there are multiple overloads accepting reference types, passing a bare `null` literal may select an unintended overload, especially the `char[]` overload. When you need to represent a `null` object reference as `"null"`, use an argument with an explicit type:

```java
String value = String.valueOf((Object) null); // "null"
```

If the argument is actually a `null` `char[]` array, calling the `valueOf(char[])` overload can throw `NullPointerException`. Therefore, the static type of the argument significantly affects a `String.valueOf` call, even though the `+` operator is often conveniently used for text concatenation.

### Why sometimes use `String.valueOf` instead of `+`?

Two different purposes:

- **Building a new sentence:** `"Count: " + count` expresses the intent directly and reads naturally.
- **Converting a single value to a standalone string:** `String.valueOf(count)` makes clear that you need a `String` to pass to another API or store beforehand.

You do not need to proactively write `String.valueOf` for **every** operand when already using concatenation: Java already has string conversion rules for the `+` operator.

## 10. Converting a string to a number is the reverse direction

When a `String` contains digits, using the `+` operator with a number does **not** automatically parse the string into a number:

```java
String text = "20";
System.out.println(text + 3); // 203
```

To perform arithmetic addition, you must convert the text using a parsing API:

```java
String text = "20";
int number = Integer.parseInt(text);

System.out.println(number + 3); // 23
```

If the text does not have a valid numeric format, `Integer.parseInt(...)` can throw `NumberFormatException`:

```java
// Integer.parseInt("twenty"); // NumberFormatException
```

Clearly distinguish the two directions:

| Direction | API / operation | Example |
|---|---|---|
| **Value → string** | `+` operator with `String`, `String.valueOf(...)` | `42` → `"42"` |
| **String → number** | `Integer.parseInt`, `Double.parseDouble`, ... | `"42"` → `42` |

Appending `""` via `number + ""` can convert a number to a string, but `String.valueOf(number)` expresses intent more clearly when only conversion is needed. Never use `Integer.parseInt` just to concatenate numbers with text.

## 11. `+=` and the immutability of `String`

`+=` on a `String` variable creates a concatenated result and reassigns the variable; the source string is not modified:

```java
String first = "Hi";
String alias = first;
first += "!";
System.out.println(alias); // Hi
```

A `final String` variable cannot use `+=` because it cannot be reassigned. See the lesson **+= creates a result and reassigns the reference** for an analysis of complex left-hand sides and the difference between `s += 1 + 2` and `s = s + 1 + 2`.

## 12. Constant expressions and runtime concatenation

The expression `"Ja" + "va"` is a **constant expression**, resolved at compile time and having an interned constant value. Conversely, when the result depends on a variable that is not a constant variable, concatenation occurs at runtime. Use `equals()` to compare content; do not rely on `==` even though some constant results share the same reference. Bytecode details belong to the lesson **Concatenation compilation details may vary across JDKs**.

## 13. Performance: when to use `+`, when to use `StringBuilder`?

For a short expression like `"Hello, " + name`, `+` is readable and modern Java can optimize it. When accumulating repeatedly across a loop, `StringBuilder.append(...)` is generally more appropriate because it avoids recreating the accumulated prefix on every iteration. To join a list with a delimiter, prefer `String.join()` when appropriate. The lesson **Concatenation in a single expression vs. accumulation across loops** provides detailed guidance on choosing APIs and verifying costs.

## 14. Evaluation order and side effects

Java operands are evaluated in left-to-right order, even when concatenation is optimized. For example:

```java
int n = 1;
String text = "n=" + n++ + ", after=" + n;
System.out.println(text); // n=1, after=2
```

Avoid side effects in long expressions. The lesson on **Left-to-right associativity** distinguishes associativity, precedence, and evaluation order.

## 15. Common mistakes

| Misconception | Correct check |
|---|---|
| `"2" + 3` is numeric addition | The result is `"23"`; use `Integer.parseInt` when numeric addition is wanted |
| `'A' + 1` produces `"A1"` | The `int` result is `66` |
| Arrays list their elements when concatenated | Use `Arrays.toString(...)` |
| `s + "B";` is a valid statement | The result must be used/assigned; a standalone `+` expression is not a statement expression |
| Concatenating `null` and calling a method on `null` are the same | `"x=" + ref` can print `"null"`; `ref.concat(...)` can throw NPE |

Common thread: you must identify the **type of the operation under consideration**, the conversion rules, and the API contract.

## 16. Self-check questions

**Question 1.** How do `"n=" + 2 + 3` and `"n=" + (2 + 3)` differ? **Answer:** `"n=23"` versus `"n=5"`.

**Question 2.** Does `"values=" + numbers` (where `numbers` is `int[]`) list the elements? **Answer:** No; use `Arrays.toString(numbers)`.

**Question 3.** What does `String.valueOf((Object) null)` return? **Answer:** `"null"`; do not automatically assume the same for the `char[]` overload with a null argument.

**Question 4.** Why is `"Hi" + name` usually good enough for a short greeting? **Answer:** it expresses intent clearly; only consider a builder for multi-step accumulation.

## 17. Takeaways

The `+` operator in Java is **string concatenation** only when one operand in the operation is of type `String`; if both are suitable numeric operands, it is **numeric addition**. During string concatenation, Java converts values to text according to string conversion rules: numbers to digits, `boolean` to `"true"`/`"false"`, `char` to the corresponding character, `null` references to `"null"`, and regular objects based on their textual representation.

Pay attention to **left associativity**, **operator precedence**, and parentheses: `"sum=" + 2 + 3` yields `"sum=23"`, whereas `"sum=" + (2 + 3)` yields `"sum=5"`. Use `String.valueOf` when explicit conversion is needed, `Arrays.toString` for arrays, `String.join` for delimited data, and `StringBuilder` when building strings over multiple steps. Because `String` is immutable, every concatenation creates a result value to store or use without modifying the content of the original string object.
