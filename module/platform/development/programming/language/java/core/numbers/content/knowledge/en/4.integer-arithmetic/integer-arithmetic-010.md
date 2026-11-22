# How Does String Concatenation with `+` Differ from Addition in Java?

## 1. Same `+` Sign, Two Different Behaviors

In Java, the `+` sign is an operator with **two primary uses** in expressions:

- **Numeric addition** when both operands are numeric values eligible for numeric promotion: `2 + 3` produces the integer **5**.
- **String concatenation** when at least one operand has type `String`: `"2" + 3` produces the string **"23"**.

Initial examples:

| Java expression | Result type | Result value | Why? |
|---|---|---|---|
| `2 + 3` | `int` | `5` | Adds two integers |
| `2L + 3` | `long` | `5L` | Has `long`, so result is `long` |
| `"2" + 3` | `String` | `"23"` | Concatenates text `"2"` with value `3` |
| `2 + "3"` | `String` | `"23"` | Concatenates number `2` converted to text with `"3"` |
| `"2" + "3"` | `String` | `"23"` | Concatenates two strings |
| `'2' + 3` | `int` | `53` | Character `'2'` has UTF-16 code `50`, added to `3` |
| `"2" + '3'` | `String` | `"23"` | One operand is `String` |

**The value `"23"` is different from the numeric value `23`.** A string is text data and can contain letters, spaces, units, or identifiers; numeric addition yields a numeric result according to operand types and ranges.

Seeing `+` does not always mean Java adds numbers, nor does seeing digit characters always mean a `String` object. Always determine **the type of each operand at the moment the `+` operator is evaluated**.

## 2. Rules for Choosing Numeric Addition vs. String Concatenation

### 2.1. Two Numeric Operands: Promote Then Add

For primitive numeric operands, `+` uses *binary numeric promotion*:

1. `byte`, `short`, and `char` are promoted to `int`.
2. If a `long` operand is present, integral addition uses `long`.
3. If no `long` is present, addition of primitive integral types produces `int`.

For example:

```java
byte a = 10;
byte b = 20;
int sum = a + b;     // 30, expression a + b has type int
long wide = a + 20L; // 30L, expression has type long
```

You cannot assign `byte c = a + b;` directly because adding two `byte` variables returns `int`; converting back to `byte` requires an explicit cast, along with range checking when needed.

### 2.2. One Operand Is `String`: Convert to Text Then Concatenate

If at a binary `+` operator **one operand has type `String`**, Java performs string concatenation. The other operand is converted to a text representation:

```java
String name = "Lan";
int points = 12;
String message = name + " has " + points + " points";
// "Lan has 12 points"
```

In the final concatenation, the integer `points` is converted to its text representation `"12"`. That is a **number-to-string** conversion, not adding `12` to another number.

Primitive types such as `int`, `long`, `boolean`, and `char` can all appear in concatenation with `String`. Reference values can also be concatenated: `null` is represented as the text `"null"`; other objects have a corresponding string representation, typically involving `toString()`.

**Scope note:** `+` can concatenate `String`, but Java **does not allow** `-` or `*` on strings. For example, `"8" - "3"` and `"8" * 3` are both compile errors. To do arithmetic on numbers inside strings, **parse** them to numeric types first.

## 3. Evaluation Order and Left-Associativity Causing Unexpected Results

The binary `+` operator is **left-associative**: without parentheses, a chain of additions/concatenations at the same level groups from left to right.

Therefore:

```java
String a = "Result: " + 2 + 3;   // "Result: 23"
String b = "Result: " + (2 + 3); // "Result: 5"
String c = 2 + 3 + " is the sum"; // "5 is the sum"
String d = 2 + "3" + 4;           // "234"
```

Step-by-step analysis:

- `"Result: " + 2 + 3` groups as `("Result: " + 2) + 3`. The first step is already string concatenation, yielding `"Result: 2"`; the next step concatenates `"3"`.
- `"Result: " + (2 + 3)`: parentheses force `2 + 3` to be computed as integers first, yielding `5`; only then is it concatenated into `"Result: 5"`.
- `2 + 3 + " is the sum"` groups as `(2 + 3) + " is the sum"`. The first step adds two numbers to `5`, and the next converts `5` to a string and concatenates.
- `2 + "3" + 4`: `2 + "3"` already produces the string `"23"`, so the next operator appends the character `4`; there is no numeric addition `23 + 4`.

**Key takeaway:** deciding whether `+` is addition or concatenation is evaluated **at each node of the expression**, not as a single line-wide decision. Once a subexpression produces a `String`, subsequent `+` operations with it become string concatenation; parentheses can isolate an **independent** numeric addition before concatenation.

### Precedence with Other Operators

Multiplication `*` has higher precedence than `+`:

```java
String x = "Total: " + 2 * 3;       // "Total: 6"
String y = "Total: " + (2 + 3) * 4; // "Total: 20"
```

Parentheses help clarify intent, especially in log lines, reports, message formatting, and strings displaying calculation results. You do not need parentheses everywhere, but use them whenever a reader could confuse numeric addition with string concatenation.

## 4. Java 17+ Program to Verify

Create a file `PlusOperatorDemo.java`:

```java
public class PlusOperatorDemo {
    public static void main(String[] args) {
        System.out.println("2 + 3 = " + (2 + 3));
        System.out.println("plain addition: " + (2 + 3));
        System.out.println("concat first: " + 2 + 3);
        System.out.println(2 + 3 + " is five");
        System.out.println("mixed: " + 2 + "3" + 4);
        System.out.println("multiply: " + 2 * 3);
        System.out.println("char arithmetic: " + ('A' + 1));
        System.out.println("char concat: " + 'A' + 1);

        String count = "count=";
        count += 4;
        count += 5;
        System.out.println(count);
    }
}
```

Compile and run:

```bash
javac PlusOperatorDemo.java
java PlusOperatorDemo
```

Exact output:

```text
2 + 3 = 5
plain addition: 5
concat first: 23
5 is five
mixed: 234
multiply: 6
char arithmetic: 66
char concat: A1
count=45
```

The `char` lines illustrate an important difference. `'A'` is a literal of **type `char`**, with numeric code unit value `65`. In `'A' + 1`, Java promotes `char` to `int`, giving **66**. In `"char concat: " + 'A'`, one operand is already `String`, so the character **A** is appended to the string; the subsequent `+ 1` then appends the text **1**.

### `char` Is Not the Same as `String`

```java
int numeric = '1' + 2;     // 49 + 2 = 51
String text = "1" + 2;      // "12"
String letters = 'A' + "" + 'B'; // "AB"
int codes = 'A' + 'B';      // 65 + 66 = 131
```

Single quotes `'A'` denote a `char`; double quotes `"A"` denote a `String`. This **type** difference determines the behavior of `+`.

A Unicode code point outside the BMP may require two `char`s (a surrogate pair), because `char` is a **UTF-16 code unit**, not every user-perceived character. When concatenating a `String` with a `char`, Java appends that code unit as its string representation.

## 5. String Concatenation Does Not Fix Earlier Overflow

Integer addition has a finite width. For 32-bit `int`, `Integer.MAX_VALUE` is `2_147_483_647`. Adding `1` **in `int`** overflows to `-2_147_483_648`.

Consider:

```java
int max = Integer.MAX_VALUE;

String a = "sum=" + (max + 1);       // "sum=-2147483648"
String b = "sum=" + max + 1;         // "sum=21474836471"
String c = "sum=" + ((long) max + 1); // "sum=2147483648"
```

- For `a`, parentheses force adding two `int`s first → **overflow**, and only then is the negative value converted to text.
- For `b`, `"sum=" + max` already created a string, so `+ 1` merely appends the text `1`, creating a numeric-looking string that is **not an arithmetic sum**.
- For `c`, `(long) max + 1` is computed in `long`, giving the correct numeric result before concatenation.

Writing `long result = max + 1;` does not prevent overflow either: the addition finishes in `int` before assignment. If overflow must be rejected, use `Math.addExact(max, 1)` so Java throws `ArithmeticException`, rather than computing and formatting a wrong number.

**Rule:** get **the numeric type and arithmetic right first**, and only then concatenate the presentation text. Do not use string display output as a substitute for verifying numeric results.

## 6. Concatenating Floating-Point Numbers, Booleans, Null, and Objects

### 6.1. Floating-Point Numbers and Booleans

```java
String temperature = "Temp: " + 23.5; // "Temp: 23.5"
String enabled = "Enabled: " + true;  // "Enabled: true"
```

`true` is a `boolean` and cannot be numerically added to `int`; however, `"Enabled: " + true` is valid because it is **string concatenation**.

Floating-point numbers are also converted to text during concatenation. If the UI requires explicit formatting rules (such as two decimal places or locale-specific separators), use an appropriate formatting API instead of relying on the default string representation of `double`.

### 6.2. `null` in String Concatenation

When a **reference** is `null` and participates in string concatenation, the appended text is **"null"**:

```java
String name = null;
Object item = null;
System.out.println("name=" + name); // name=null
System.out.println("item=" + item); // item=null
```

This does not turn the variable `name` into a real `String` object containing `"null"`: `name` remains a `null` reference. The text `"null"` is only generated to represent it in the resulting string.

With numeric wrappers like `Integer`, the distinction is even more important:

```java
Integer quantity = null;
System.out.println("quantity=" + quantity); // quantity=null

// int n = quantity + 1; // throws NullPointerException at runtime
```

The first case is string concatenation with a **reference**; the second is numeric addition, so Java must **unbox** `Integer` to `int` first, and unboxing `null` throws `NullPointerException`.

### 6.3. Objects and `toString()`

An ordinary object is converted to a text representation when concatenated with `String`. The representation is typically determined by `toString()`.

```java
record Item(String code, int quantity) {}

Item item = new Item("BK", 2);
String description = "item=" + item;
```

This is an **illustrative code snippet** within a scope where `record` can be declared and variables used; to run standalone, place it inside a complete Java structure. For a Java record, the default representation has the form `Item[code=BK, quantity=2]` (if `toString()` is not overridden).

**Do not assume all custom objects produce useful information when concatenated.** If a class does not override `toString()`, the default result is usually the class name followed by `@` and a hexadecimal hash code, not its business fields. To display an array, use `Arrays.toString(array)` or `Arrays.deepToString(array)` for nested arrays instead of directly concatenating the array with a string.

## 7. Runnable Example Handling `null` and Displaying Objects

Create a file `StringConversionDemo.java`:

```java
import java.util.Arrays;

public class StringConversionDemo {
    record Product(String code, int count) {}

    public static void main(String[] args) {
        Integer quantity = null;
        String name = null;
        int[] numbers = {1, 2, 3};

        System.out.println("quantity=" + quantity);
        System.out.println("name=" + name);
        System.out.println("array=" + Arrays.toString(numbers));
        System.out.println("product=" + new Product("BK", 2));

        try {
            int next = quantity + 1; // must unbox null
            System.out.println(next);
        } catch (NullPointerException e) {
            System.out.println("numeric null: NullPointerException");
        }

        System.out.println("boolean=" + true);
        System.out.println("decimal=" + 23.5);
    }
}
```

Run:

```bash
javac StringConversionDemo.java
java StringConversionDemo
```

Output:

```text
quantity=null
name=null
array=[1, 2, 3]
product=Product[code=BK, count=2]
numeric null: NullPointerException
boolean=true
decimal=23.5
```

This code demonstrates why two `+` operations can handle the same variable `quantity` in two different ways: `"quantity=" + quantity` is string concatenation; `quantity + 1` is an arithmetic operation requiring unboxing.

## 8. `+=`: Compound Numeric Addition or String Append?

The `+=` operator also depends on the type of the left-hand variable:

```java
int number = 5;
number += 3;        // numeric addition: number = 8

String label = "item";
label += 3;         // string concatenation: label = "item3"
label += 4;         // further concatenation: label = "item34"
```

For a `String` variable, `s += x` appends `x` to the previous string in `s`; the result remains `String`. For a numeric variable, `+=` uses numeric arithmetic and Java's compound assignment rules, which may include an **implicit cast** back to the left-hand variable's type.

```java
byte small = 120;
small += 10; // yields -126 due to int addition then narrowing to byte

String text = "120";
text += 10;  // "12010", no numeric overflow
```

For `String`, the `+=` operator creates a new result because **`String` is immutable**: the existing string's contents are never modified in place. Reassignment points the variable `text` to the newly concatenated result.

**Reverse limitation:** `int x = 10; x += "20";` is a compile error because a string result cannot be assigned back to an `int` variable. Java does not automatically parse a digit string just because the target variable is numeric.

## 9. Evaluation Order and Side Effects in `+` Operations

Java evaluates the operands of binary operators **from left to right**. If an operand performs a state-modifying action (such as `i++` or calling a mutating method), that order affects the resulting string.

For example:

```java
int i = 1;
System.out.println("before=" + i++ + ", after=" + i);
```

Output:

```text
before=1, after=2
```

`i++` returns the old value `1` for the current concatenation, then increments `i` to `2`. The operand `", after=" + i` is evaluated afterward and observes the new value. Evaluation order is defined by the Java language; however, for readability, avoid packing multiple side effects into a long concatenation expression.

Another note: `"result=" + calculate()` **still calls** `calculate()` before producing the string, even if the value is only used for display. Avoid calling functions with side effects inside concatenation solely for formatting.

## 10. Converting Digit Strings to Numbers for Real Arithmetic

String concatenation **does not automatically parse** digits:

```java
String left = "20";
String right = "3";

String joined = left + right;  // "203"
int total = Integer.parseInt(left) + Integer.parseInt(right); // 23
```

If user input represents numbers entered as text, validate the input and convert using an appropriate API such as `Integer.parseInt` or `Long.parseLong`. When the string is not a valid numeric format or exceeds the target type's range, parse methods throw `NumberFormatException`.

For example:

```java
String price = "120";
String quantity = "3";
int amount = Integer.parseInt(price) * Integer.parseInt(quantity);
// amount = 360
String display = "amount=" + amount; // "amount=360"
```

An easy-to-control pipeline is **parse → compute → check overflow/range → format result**. If the computation risks overflowing, choose a wider type or appropriate `Math.addExact`/`Math.multiplyExact` before converting the result to a string.

**Unary `+`:** `+5` and `+number` are solely numeric positive signs, not string concatenation; you cannot write `+"hello"`. The string concatenation topic here refers to the **binary `+` operator** taking two operands.

## 11. Performance, `StringBuilder`, and Writing Clear Code

Because `String` is immutable, concatenating inside a **large loop** can allocate many intermediate strings and consume memory/allocations:

```java
String result = "";
for (int n = 1; n <= 3; n++) {
    result += n;
}
// result = "123"
```

When accumulating many text fragments in a loop, you can use `StringBuilder`:

```java
StringBuilder builder = new StringBuilder();
for (int n = 1; n <= 3; n++) {
    builder.append(n);
}
String result = builder.toString(); // "123"
```

A regular concatenation expression such as `"name=" + name + ", age=" + age` remains natural and readable; modern Java versions optimize string concatenation at compile time and runtime. There is no need to turn every `String` `+` into `StringBuilder`. Only consider a builder when genuinely **looping many times**, accumulating large text, or when profiling proves performance is an issue.

When formatting multi-field messages, you can also use `String.format`, `System.out.printf`, or other suitable formatting tools. These APIs help with display layout, field width, decimal precision, and locale; the underlying numeric arithmetic must still be determined beforehand.

## 12. Common Bugs and Fixes

| Symptom | Cause | Clearer way to write it |
|---|---|---|
| `"Sum=" + 2 + 3` prints `Sum=23` | String concatenation occurs before numeric addition | `"Sum=" + (2 + 3)` |
| `2 + "3" + 4` becomes `234` | After the first step, the result is `String` | Parse or parenthesize operations per intent |
| `'1' + 2` yields `51` | `char` promotes to `int`; `'1'` has code `49` | Use `"1" + 2` to concatenate, or convert digit char to number |
| `"x=" + (max + 1)` prints a negative number | `int` addition overflows before concatenation | Widen to `long` or use `Math.addExact` |
| `Integer value = null; value + 1` throws NPE | Arithmetic needs to unbox a null reference | Check for null before computing |
| `"obj=" + obj` prints unreadable text | Default object string lacks business data | Implement a useful `toString()` or pick explicit fields |
| `"array=" + array` does not print elements | Arrays do not display contents via concatenation | `Arrays.toString(array)` |
| `int x = 10; x += "20";` fails to compile | A string result cannot be assigned to a numeric variable | Parse the string or use a `String` variable |
| Repeated string concatenation causes overhead | `String` is immutable; accumulates many strings | Use `StringBuilder` for large loops |

## 13. Self-Check Exercises

**Q1.** What does `System.out.println("Total: " + 10 + 20);` print?  
**Answer:** `Total: 1020`, because the first operator already begins string concatenation.

**Q2.** To print `Total: 30` from `10` and `20`, what should you write?  
**Answer:** `System.out.println("Total: " + (10 + 20));`.

**Q3.** What does `System.out.println(10 + 20 + " items");` print?  
**Answer:** `30 items`, because `10 + 20` is numeric addition before encountering `String`.

**Q4.** Does `'3' + 1` equal `"3" + 1`?  
**Answer:** No. `'3'` is a `char` with code `51`, so the numeric result is `int` `52`; `"3"` is a `String`, so the result is `"31"`.

**Q5.** Given `String s = null; String t = "value=" + s;`, what does `t` equal?  
**Answer:** `"value=null"`. The variable `s` remains a `null` reference.

**Q6.** Does `Integer n = null; System.out.println("n=" + n);` fail like `n + 1`?  
**Answer:** No. The first concatenates the text `"null"`; the second must unbox `n` and throws `NullPointerException`.

**Q7.** Why does `"sum=" + (Integer.MAX_VALUE + 1)` print a negative number?  
**Answer:** Because the sum of two `int`s overflows **before** being converted to a string. Promote an operand to `long` before adding if a larger range is needed.

**Q8.** When should you use `StringBuilder`?  
**Answer:** When accumulating many string fragments across a loop or needing to reduce intermediate string allocations; for a single short statement, `+` is usually clear and appropriate.

**Q9.** What does `String s = "x"; s += 2; s += 3;` produce?  
**Answer:** `"x23"`, because both `+=` operations append text to the `String` variable.

**Q10.** What does `"Result: " + 2 * 3` produce, and why?  
**Answer:** `"Result: 6"`. The multiplication operator `*` has higher precedence than `+`, so `6` is computed before string concatenation.

**Key Takeaway:** For binary `+`, **two numeric operands → numeric addition; any `String` operand → string concatenation**. Java groups `+` operators at the same level from left to right. To display a **numeric sum**, parenthesize the calculation (or compute into a variable first) before concatenating into a string; a string result does not fix an arithmetic overflow that has already occurred.