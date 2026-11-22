# The += Operator on Java Strings: Creating a Result and Reassigning the Reference

## 1. Understanding the goal

When writing:

~~~java
String name = "Java";
name += " Core";
~~~

the value of the variable `name` becomes `"Java Core"`. However, **the `"Java"` string object is not modified**. Java computes the string concatenation, produces a result, and then **assigns that result back to the reference variable `name`**.

This is an important distinction between *changing a variable's value* and *changing an object's contents*. `String` is **immutable**: the contents of a `String` object cannot change after creation. The `+=` syntax simply makes concatenation and assignment more concise; it **does not break immutability**.

After this lesson, you will be able to:

1. Explain the meaning of `s += part` when `s` is a `String`.
2. Distinguish `s += x`, `s = s + x`, `s.concat(x)`, and `StringBuilder.append(x)`.
3. Predict the values of other variables holding the **old reference** after `s += ...`.
4. Understand how `+=` converts operands to text, including numbers, objects, and `null`.
5. Distinguish evaluation order, parentheses, and results when concatenating numbers.
6. Recognize compile errors when using `+=` with `final` variables and consider `StringBuilder` for repeated concatenations.
7. Read and verify results using standalone Java 17+ programs.

Prerequisites: variables, object references, `=`, `+`, `String`, primitive types, and `final`.

## 2. += both concatenates strings and assigns the result

`+=` is the **compound assignment operator**. For a simple `String` variable, you can think of it as:

~~~java
String s = "Hello";

s += " World";    // Shorthand
// Equivalent in result to:
// s = s + " World";
~~~

The final value of `s` is `"Hello World"`. The operation can be pictured in three steps:

1. Read the current value referenced by the variable `s`, here `"Hello"`.
2. Compute `s + " World"`, producing a value with content `"Hello World"`.
3. Assign the concatenated result back to the variable `s`.

Notice the phrase **“equivalent in result”**: for a complex left-hand expression with side effects such as `array[index++]`, Java evaluates the left-hand side of a compound assignment **once**. Therefore, you cannot mechanically rewrite every `left += value` as `left = left + value` if evaluating `left` has side effects.

Simple reference diagram:

~~~text
Initially:
s ─────────► String "Hello"

After s += " World":
s ─────────► String "Hello World"

The object containing "Hello" is not modified.
If another variable still points to the old object, that variable still reads "Hello".
~~~

In Java, `String` is immutable, although the compiler and JVM can optimize how the resulting value is constructed in various ways. You should not guess **exactly how many intermediate objects every concatenation allocates**.

## 3. Key example: another variable remains unchanged

~~~java
String first = "Java";
String second = first;

first += " Core";

System.out.println(first);  // Java Core
System.out.println(second); // Java
~~~

Before `+=`, both `first` and `second` reference the same value `"Java"`. After the assignment, **only `first` is reassigned**; `second` still keeps its original reference, so it prints `"Java"`.

~~~text
Before:
first  ───┐
          ├──► "Java"
second ───┘

After:
first  ──────► "Java Core"
second ──────► "Java"
~~~

A way to verify the meaning (prefer checking with `equals()`):

~~~java
String original = "A";
String copyOfReference = original;
original += "B";

System.out.println("A".equals(copyOfReference)); // true
System.out.println("AB".equals(original));       // true
~~~

This is precisely what **“creating a result and reassigning the reference”** means. The assignment does not propagate changes back to other reference variables.

### Contrast with StringBuilder

~~~java
StringBuilder builder = new StringBuilder("A");
StringBuilder alias = builder;

builder.append("B");

System.out.println(builder); // AB
System.out.println(alias);   // AB
~~~

Both `builder` and `alias` reference **the same mutable `StringBuilder` object**, so changes made by `append()` are visible through both variables. `StringBuilder.append()` mutates the builder; `String += ...` replaces the value held by the `String` variable.

## 4. Mechanism of String + and conversion to text

`s += value` uses `String` concatenation rules: numbers, `boolean`, `char`, and objects are converted to text. A `null` value can become the text `"null"`:

```java
String label = "count=";
label += 42;
System.out.println(label); // count=42

String missing = null;
missing += "!";
System.out.println(missing); // null!
```

`+=` does not format numbers according to locale or automatically resolve missing data. This is **conversion during concatenation**; see the lessons on `+` and `String.valueOf` for the full conversion table.

## 5. Arithmetic, operator order, and parentheses

`+` means both **numeric addition** and **string concatenation**, so evaluation order can yield different results.

~~~java
String first = "N";
first += 1 + 2;
System.out.println(first); // N3

String second = "N";
second += 1;
second += 2;
System.out.println(second); // N12
~~~

In the first example, the right-hand expression `1 + 2` performs numeric addition first, yielding `3`, before being concatenated to `"N"`. The second example concatenates each number sequentially.

Similarly:

~~~java
String a = "Result=";
a += (10 + 5);
System.out.println(a); // Result=15

String b = "Result=";
b = b + 10 + 5;
System.out.println(b); // Result=105
~~~

The expression `b + 10 + 5` associates from left to right: starting with a `String`, subsequent `+` operations perform text concatenation.

**Safe reading practice:** When you want to add first and then convert to text, wrap the arithmetic operation in parentheses. When you want to concatenate individual values, make delimiters explicit or use a formatter.

### += is not necessarily the same as calling concat()

~~~java
String a = "ID";
a += 17;                // Valid: ID17

String b = "ID";
// b = b.concat(17);     // Does not compile: concat accepts String
b = b.concat("17");      // Valid: ID17
~~~

`concat(String)` requires a `String` argument; the `+` operator with `String` has more flexible operand conversion rules.

## 6. Differences between += and common assignment operations

| Expression | Mechanism | Is the source String object modified? |
| --- | --- | --- |
| `s = "Hello"` | Assigns reference to string | No |
| `s = s + "!"` | Creates concatenated value, assigns result | No |
| `s += "!"` | Compound assignment: concatenates then reassigns | No |
| `s.concat("!")` | Returns concatenated result, **discards result** | No; `s` stays unchanged |
| `s = s.concat("!")` | Captures result from `concat()` | No |
| `builder.append("!")` | Modifies `StringBuilder` contents | Not applicable to `String`; builder is mutable |

Common mistake example:

~~~java
String s = "Hello";

s.concat("!");
System.out.println(s); // Hello

s += "!";
System.out.println(s); // Hello!
~~~

The difference lies in **whether the result is assigned**. Calling `concat()` and discarding the result leaves the variable unchanged. `+=` includes assignment in its syntax.

### final variables cannot use +=

~~~java
final String title = "Java";
// title += " Core"; // Compile error: cannot reassign a final variable
~~~

`final` prevents reassigning the variable. Even though `String` itself is immutable, `+=` is still a **reassignment**, so it is forbidden on a `final` variable.

Conversely:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core"); // Valid: does not reassign the builder variable
~~~

`final` does not turn a mutable object into an immutable one; it only fixes the variable's **reference**.

## 7. String Pool and issues with ==

`String` literals and constant expressions can share interned values, whereas `+=` typically produces results at runtime. `==` compares references; `equals()` compares content:

```java
String name = "Ja";
name += "va";
System.out.println(name.equals("Java")); // true
```

Result identity is not the right basis for checking content. Interning and constant-expression mechanisms are explained separately in lessons on the String pool and the compiler.

## 8. Complex left-hand side: evaluated only once

For simple variables, you can read `s += x` like `s = s + x`. However, **the language rule** for compound assignment is that the left-hand side is evaluated once.

~~~java
String[] values = {"A", "B"};
int index = 0;

values[index++] += "!";

System.out.println(index);     // 1
System.out.println(values[0]); // A!
System.out.println(values[1]); // B
~~~

`index++` executes only once; Java then concatenates onto element `values[0]` and assigns the result back to that exact element.

Do not mechanically rewrite this statement as:

~~~java
// NOT equivalent, because index++ would run twice:
// values[index++] = values[index++] + "!";
~~~

In the incorrect replacement, the index expression would be evaluated twice and different elements could be read/written. With field access, array access, or methods with side effects on the left-hand side, you must follow Java's specific evaluation rules.

### += with String array elements

~~~java
String[] labels = {"A", "B"};
String old = labels[0];

labels[0] += "1";

System.out.println(labels[0]); // A1
System.out.println(old);       // A
~~~

The array element is **reassigned a new reference**. The old string object `"A"` remains immutable; the variable `old` continues to hold the old value.

## 9. Cost of repeated concatenation

Repeating `result += part` many times must build a new result value on each iteration; as data grows, `StringBuilder.append(part)` is usually more appropriate. That does not mean every short `+=` is worth changing:

```java
String greeting = "Hello";
greeting += ", Java"; // Clear, valid
```

The lesson **Concatenation in a single expression vs. accumulation across loops** analyzes the cost model and how to benchmark; here, the focus remains **reference reassignment**.

## 10. A complete verification program for Java 17+

Create the file **`StringPlusEqualsDemo.java`**:

~~~java
public class StringPlusEqualsDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;
        first += " Core";
        System.out.println("first=" + first);
        System.out.println("alias=" + alias);

        String missing = null;
        missing += "!";
        System.out.println("missing=" + missing);

        String number = "N";
        number += 1 + 2;
        System.out.println("number=" + number);

        String pieces = "N";
        pieces += 1;
        pieces += 2;
        System.out.println("pieces=" + pieces);

        String[] values = {"A", "B"};
        int index = 0;
        values[index++] += "!";
        System.out.println("index=" + index);
        System.out.println("values[0]=" + values[0]);
        System.out.println("values[1]=" + values[1]);

        StringBuilder builder = new StringBuilder("A");
        StringBuilder builderAlias = builder;
        builder.append("B");
        System.out.println("builder=" + builder);
        System.out.println("builderAlias=" + builderAlias);

        String text = "Ja";
        text += "va";
        System.out.println("equals=" + text.equals("Java"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StringPlusEqualsDemo.java
java StringPlusEqualsDemo
~~~

**Exact stdout:**

~~~text
first=Java Core
alias=Java
missing=null!
number=N3
pieces=N12
index=1
values[0]=A!
values[1]=B
builder=AB
builderAlias=AB
equals=true
~~~

**Explanation:**

1. `first` is assigned the concatenated result, while `alias` keeps the string `"Java"`.
2. `missing`, initially `null`, is converted to the text segment `"null"`, producing `"null!"`.
3. `number += 1 + 2` adds the numbers first and concatenates `3`; `pieces` concatenates two separate numbers, yielding `"N12"`.
4. `values[index++] += "!"` increments `index` only once and assigns the result at the first element.
5. `StringBuilder.append()` mutates the mutable builder, so `builderAlias` also reads `"AB"`.
6. `equals()` confirms the content after `+=` is right, without relying on object identity comparison.

This standalone program has one public class matching the filename, runs on Java 17 or later, and requires no libraries outside the JDK.

## 11. Misconceptions to correct

| Misconception | Reality |
| --- | --- |
| `s += x` modifies the source `String` object's content | It creates a result value and **reassigns the variable** |
| Every variable referencing the same `String` sees the new value after `+=` | Only the left-hand side is reassigned; other references keep the old value |
| `+=` is always safe when `s == null` | It can produce unintended `"null..."` text |
| `s += 1 + 2` always yields `"...12"` | `1 + 2` performs numeric addition first, yielding `3` |
| `s += value` is always the same as textually substituting `s = s + value` | When the left-hand side has side effects, the single-evaluation rule matters |
| A `final String` variable can use `+=` because String is immutable | `+=` is reassignment, so it is a **compile error** |
| Calling `s.concat(x)` and ignoring the return value still changes `s` | No: String is immutable, you must capture the result |
| `==` is sufficient to compare content after concatenation | Use `String.equals()` |
| Using `+=` in a large loop is always optimal | Consider `StringBuilder`, and measure performance when needed |
| `StringBuilder.append()` is the same as `String +=` | `append()` mutates the builder; `+=` on String reassigns the reference |
| Every new `String` holds the same reference as a literal with equal content | Do not rely on pooling to infer identity of runtime results |

## 12. Practice exercises

### Exercise 1 — Predict two variables

~~~java
String a = "Hello";
String b = a;
a += "!";
System.out.println(a);
System.out.println(b);
~~~

Predict and explain why one variable prints `"Hello!"` and the other prints `"Hello"`.

### Exercise 2 — null vs. method error

Run `String s = null; s += "X";`. Compare with `s.concat("X")` while `s` is still `null`. Explain how the text string `"nullX"` differs from an absent-data state and why you should not accept it automatically.

### Exercise 3 — Arithmetic parentheses

Write three concatenation expressions starting from `"N"` with `1` and `2`: one returning `"N3"`, one returning `"N12"`, and one returning `"N1,2"`. Use parentheses or separators to express intent.

### Exercise 4 — final

Try compiling:

~~~java
final String code = "A";
// code += "B";
~~~

Uncomment the second line to observe the compiler error. Then try `final StringBuilder builder = new StringBuilder("A"); builder.append("B");` and explain the difference.

### Exercise 5 — Arrays and side effects

Given `String[] a = {"X", "Y"}; int i = 0;`, execute `a[i++] += "?";`. Predict `i` and each element, then explain why an expansion using `i++` twice would change the semantics.

### Exercise 6 — Concatenating numbers in a loop

Build a string of numbers from `0` to `9999` in two ways: concatenating with `+=` in a loop and using `StringBuilder.append()`. Verify that **the resulting content is identical** and compare the design/complexity. If benchmarking, warm up the JVM, repeat many times, and avoid basing conclusions on a single timing measurement.

### Exercise 7 — Do not discard the result

Given:

~~~java
String title = "Java";
title.concat(" Core");
~~~

Fix the snippet so `title` has content `"Java Core"` in two ways: `title = title.concat(" Core");` and `title += " Core";`. Explain what the two ways have in common.

### Exercise 8 — Keep the original

Create `String raw = "  Java  "; String display = raw;`. Execute `display += " Core";`. Verify that `raw` stays unchanged. If you want to remove whitespace from `display`, apply `strip()` to the result and capture the return value.

## 13. Lesson completion checklist

Before using `+=` with `String`, ask yourself:

- Is the left-hand variable a `String` and can it be **reassigned**?
- Am I concatenating text or intending to perform arithmetic first? Are parentheses needed?
- Could the left-hand value or argument be `null`? Do I want `"null"` to appear?
- Are other variables holding references to the original string?
- Am I concatenating in a loop many times? Would `StringBuilder` be clearer/more efficient?
- Am I comparing results with `equals()` rather than relying on `==`?
- If the left-hand side is an array element or field, does evaluating that expression have side effects?

**Long-term takeaway:** for `String`, `s += part` means **compute the concatenated text result and assign that result to `s`**. The old `String` object's content does not change; other references to it do not change either. This is normal Java behavior—there is no in-place modification of `String`.

## 14. Official references

- [Java Language Specification 17 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26.2): `+=` rules, single evaluation of the left-hand side, and assignment.
- [Java Language Specification 17 — String Concatenation Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): `+` on `String`, string conversion, and constant expressions.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutability, `concat()`, `equals()`, and the string API.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `append()`, mutable builder, and `toString()`.
