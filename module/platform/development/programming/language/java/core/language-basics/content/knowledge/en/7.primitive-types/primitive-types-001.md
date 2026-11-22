# Overview of the Eight Primitive Types in Java (Java 17+)

Java has **eight primitive types**: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, and `boolean`. They represent basic values, distinct from reference types such as `String`, arrays, or objects. Understanding their value ranges, literals, and how the types interact helps avoid overflow, loss of precision, and type assignment errors.

## 1. Overview Table

| Type | Size, value range | Example | Purpose |
| --- | --- | --- | --- |
| `byte` | 8 bits, −128 to 127 | `byte a = -5;` | Small numeric data, binary bytes |
| `short` | 16 bits, −32,768 to 32,767 | `short b = 32000;` | Compatibility with formats requiring 16-bit integers |
| `int` | 32 bits, −2,147,483,648 to 2,147,483,647 | `int c = 42;` | General-purpose integers |
| `long` | 64 bits, −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | `long d = 9_000_000_000L;` | Integers exceeding the `int` range |
| `float` | 32-bit IEEE 754, about 6–7 significant decimal digits | `float e = 1.25F;` | Floating-point numbers needing less space/precision |
| `double` | 64-bit IEEE 754, about 15–16 significant digits | `double f = 2.5;` | Default floating-point numbers |
| `char` | 16-bit unsigned, 0–65,535 | `char g = 'A';` | A single **UTF-16 code unit** |
| `boolean` | Two values: `true`, `false` | `boolean h = true;` | Conditional logic |

The four types `byte`, `short`, `int`, and `long` are **signed integers**. `char` is an **unsigned** 16-bit code unit, and not every full Unicode character fits in a single `char`: for example, emojis outside the BMP require two `char` values when UTF-16 encoded.

`float` and `double` store **approximate** values, and also support `NaN`, `Infinity`, and `-0.0`. As for `boolean`, it **does not** accept `0` or `1` in place of `false`/`true`. Java does not mandate a fixed storage size for `boolean`; the bit widths in the table reflect the language-level value width, **not a guarantee of RAM bytes used for every variable**.

## 2. Runnable Java 17+ Example

Create a UTF-8 file named **`PrimitiveTypesDemo.java`**:

~~~java
public class PrimitiveTypesDemo {
    static int defaultNumber;       // Default int field is 0.
    static boolean defaultFlag;     // Default boolean field is false.
    static char defaultCharacter;   // Default char field is code 0.

    public static void main(String[] args) {
        byte smallest = -128;
        short tickets = 30_000;
        int population = 2_000_000_000;
        long distance = 9_000_000_000L;
        float rate = 1.25F;
        double price = 2.5D;
        char grade = 'A';
        boolean active = true;

        System.out.println("byte=" + smallest);
        System.out.println("short=" + tickets);
        System.out.println("int=" + population);
        System.out.println("long=" + distance);
        System.out.println("float=" + rate);
        System.out.println("double=" + price);
        System.out.println("char=" + grade + ", code=" + (int) grade);
        System.out.println("boolean=" + active);

        System.out.println("defaultInt=" + defaultNumber);
        System.out.println("defaultBoolean=" + defaultFlag);
        System.out.println("defaultCharCode=" + (int) defaultCharacter);

        int sum = smallest + tickets;
        System.out.println("promotedSum=" + sum);
        System.out.println("intDivision=" + (5 / 2));
        System.out.println("doubleDivision=" + (5 / 2.0));
        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("narrowByte=" + (byte) 130);
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 PrimitiveTypesDemo.java
java PrimitiveTypesDemo
~~~

**Expected output:**

~~~text
byte=-128
short=30000
int=2000000000
long=9000000000
float=1.25
double=2.5
char=A, code=65
boolean=true
defaultInt=0
defaultBoolean=false
defaultCharCode=0
promotedSum=29872
intDivision=2
doubleDivision=2.5
overflow=-2147483648
narrowByte=-126
decimalEqual=false
~~~

Explanation of notable lines:

- `9_000_000_000L` has the `L` suffix to have type `long`; `1.25F` has `F` to have type `float`; `2.5D` is `double`, and `D` can be omitted.
- `'A'` is a `char`, cast to `int` to give UTF-16 code `65`. Casting `(int)` here is only to display the numeric code.
- `smallest + tickets` is **promoted to `int`**, computing `-128 + 30000 = 29872`.
- `5 / 2` performs integer division resulting in `2`; `5 / 2.0` performs floating-point division resulting in `2.5`.
- `Integer.MAX_VALUE + 1` overflows the `int` to `-2147483648`; narrowing `130` to `byte` yields `-126`.
- `0.1 + 0.2 == 0.3` is `false` because binary floating-point cannot represent many decimal fractions exactly.

## 3. Literals and Type Conversions

### Writing Literals with the Right Type

~~~java
int days = 7;                   // int
long distance = 5_000_000_000L; // long
float portion = 0.5F;           // float
double ratio = 0.5;             // double
char separator = ':';           // char
boolean valid = false;          // boolean
~~~

Decimal integer literals like `7` default to type `int` (if within range); floating-point literals like `0.5` default to type `double`. Common mistakes:

~~~java
// float x = 0.5;         // Wrong: double does not automatically narrow to float.
float x = 0.5F;
// long y = 5000000000;   // Wrong: integer literal without L exceeds int range.
long y = 5_000_000_000L;
~~~

Java also allows hexadecimal and binary literals, such as `0xFF` and `0b1010`. Underscores like `1_000_000` group digits at valid positions without changing the value.

### Widening and Narrowing

Some common numeric conversions:

~~~text
byte → short → int → long → float → double
               ↑
             char
~~~

Converting `int` to `long` typically preserves the value. However, **widening conversions do not always preserve precision**: some large `long` values cannot be represented intact by `float` or `double`. Conversely, narrowing such as `int` to `byte` can change the value:

~~~java
int original = 130;
byte narrowed = (byte) original; // -126
~~~

A special integer constant assignment is permitted when the value is within range, such as `byte b = 100;` even though the literal `100` has type `int`. However, a general `int` variable does not automatically narrow to `byte`:

~~~java
int n = 100;
// byte b = n; // Wrong without casting.
byte b = (byte) n;
~~~

### Integer Promotion in Expressions

With standard arithmetic operators, `byte`, `short`, and `char` are promoted to `int` before the operation:

~~~java
byte left = 10, right = 20;
int sum = left + right;        // Correct.
// byte sum2 = left + right;  // Compile error: result is int.
~~~

**The type of the variable on the left-hand side does not automatically change the type of the operation.** Therefore, `double answer = 5 / 2;` produces `2.0`, not `2.5`.

## 4. Default Values and Uninitialized Errors

Object/class **fields** receive default values if not explicitly initialized: `0` for integers, `0.0` for floating-point numbers, code `0` for `char`, and `false` for `boolean`. This is why the three static fields in the example program can be read immediately.

**Local variables** are different:

~~~java
int count;
// System.out.println(count); // Compile error: count has not been assigned.
count = 3;
System.out.println(count); // 3
~~~

Java requires local variables to be definitely assigned before reading; there is no rule that every primitive variable automatically gets `0` upon declaration.

No primitive type accepts `null` directly:

~~~java
// int n = null;         // Wrong.
// boolean b = null;     // Wrong.
Integer boxed = null;    // Correct: Integer is a reference type.
~~~

The corresponding wrapper classes such as `Integer`, `Long`, `Double`, and `Boolean` are **wrapper/reference types**, not the eight primitive types. Unboxing a `null` wrapper to a primitive throws a `NullPointerException` at runtime.


## 5. From the Value to Store to the Type to Choose

The eight-type table above helps identify representational capability; when programming, you must also consider **the maximum value of intermediate results** and **the desired precision**:

- For counts, typically start with `int`; use `long` when sums/products may exceed the `int` limit. Convert operands to `long` **before the operation**, because a receiving `long` variable cannot fix an `int` result that has already overflowed.
- For approximate measured quantities, `double` is usually appropriate; use `float` only when data or an API requires 32 bits. Do not use binary floating-point if decimal arithmetic must be strictly exact: when needed, consider `BigDecimal` or the smallest integer unit.
- `byte`/`short` are mainly useful when data formats require that exact width; `boolean` is for conditions; `char` is for **a single UTF-16 code unit**, while general text uses `String`.

This is only an orientation map. The lessons on integers, floating-point, Unicode, and type selection will analyze conditions, risks, and how to verify them with source code in turn.

## 6. Self-Check Exercises

1. **Classifying the eight types:** Name the four signed integer types, the two floating-point types, the character type, and the logical type.  
   *Answer:* `byte`/`short`/`int`/`long`; `float`/`double`; `char`; `boolean`.
2. **Predict:** What do `double x = 7 / 2;` and `double y = 7 / 2.0;` produce?  
   *Answer:* `x = 3.0`, `y = 3.5`.
3. **Explain:** Why is `float f = 0.25;` invalid while `float f = 0.25F;` is valid?  
   *Answer:* `0.25` is a `double` literal; `F` creates a `float` literal.
4. **Overflow:** Predict `(byte) 130`.  
   *Answer:* `-126` due to narrowing to an 8-bit signed value.
5. **Local variables:** Why does `int x; System.out.println(x);` inside a method fail to compile, whereas reading an `int` field declared without an initializer works?  
   *Answer:* A local variable has no default value; a field has a default value of `0`.
6. **Unicode:** Can a single `char` hold an entire emoji outside the BMP?  
   *Answer:* No; it requires two UTF-16 code units. Use `String` when processing text.

## Key Takeaways

Java 17 has **exactly eight primitive types**. `int` and `double` are usually the default choices for integers and floating-point numbers; `boolean` is not numeric; `char` is **a single UTF-16 code unit**. Check value ranges, literal suffixes, promotion/casting rules, overflow, and floating-point rounding errors **before** deciding on a data type for a problem.
