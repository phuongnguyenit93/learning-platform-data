# Implicit Conversion and Explicit Casting in Java 17+

**Type conversion** is how Java converts the value of an expression from one type to another. Two cases need to be distinguished when writing code:

- **Implicit conversion**: Java applies an allowed conversion rule without requiring a cast operator, such as converting `int` to `long` during assignment or promoting numeric operands before an operation.
- **Explicit cast**: the programmer writes the `(TargetType) expression` operator, usually when a conversion may lose data or when narrowing a reference is needed. **A cast does not guarantee an accurate or safe result at runtime.**

~~~java
int count = 120;
long wide = count;         // Implicit: int -> long.
byte small = (byte) count; // Explicit: int -> byte.
~~~

In the example, both `wide` and `small` are 120 because the value 120 can be represented by `byte`. However, if `count = 130`, casting to `byte` yields `-126`.

## 1. Primitive numeric conversions: widening and narrowing

| Kind | Example | Compiler handling | Things to note |
| --- | --- | --- | --- |
| **Widening primitive** | `long a = 42;` | Automatically allowed | Not every conversion to floating-point preserves precision |
| **Narrowing primitive** | `byte b = (byte) 130;` | Usually requires a cast | May lose bits, changing the value |
| Widening `char` | `int n = 'A';` | Automatic | `char` is unsigned, `'A'` becomes 65 |
| Narrowing to `char` | `char c = (char) 66;` | Usually requires a cast | Result is in the range 0–65,535 |
| Converting `double` to `int` | `int n = (int) 12.9;` | Requires a cast | Discards the fractional part, **does not round to nearest** |
| Implicit in arithmetic expressions | `int sum = byteA + byteB;` | Two `byte`s are usually promoted to `int` | The result type depends on the operands |
| Converting `boolean` and numeric types | `(int) true` | **Invalid** | Java does not convert `boolean` to a number via cast |

A familiar widening conversion chain:

~~~text
byte -> short -> int -> long -> float -> double
                  ^
                 char  (char -> int -> long -> float -> double)
~~~

This is a mnemonic diagram for **some valid paths**, not a list of every individual conversion. Note that `char -> short` and `byte -> char` are **not** valid widening conversions. `boolean` stands outside these numeric type conversions.

Widening **does not necessarily preserve all digits**: for example, converting a large `long` to `double` may round because `double` only has 53 bits of significand precision. Conversely, `int -> long` preserves the exact value of every `int`.

## 2. Runnable Java 17+ program

Create a UTF-8 file named **`TypeConversionDemo.java`**:

~~~java
public class TypeConversionDemo {
    public static void main(String[] args) {
        int original = 120;
        long asLong = original;
        double asDouble = original;

        System.out.println("widenIntToLong=" + asLong);
        System.out.println("widenIntToDouble=" + asDouble);

        long huge = 9_007_199_254_740_993L;
        double approximate = huge;
        System.out.println("largeLongPreserved="
                + ((long) approximate == huge));

        int outsideByte = 130;
        byte wrappedByte = (byte) outsideByte;
        System.out.println("byteFrom130=" + wrappedByte);

        System.out.println("positiveToInt=" + (int) 12.9);
        System.out.println("negativeToInt=" + (int) -12.9);
        System.out.println("hugeDoubleToInt=" + (int) 1.0e20);
        System.out.println("nanToInt=" + (int) Double.NaN);

        char letter = 'A';
        int letterCode = letter;
        System.out.println("charToInt=" + letterCode);
        System.out.println("intToChar=" + (char) 66);

        byte literalByte = 100;
        byte left = 10;
        byte right = 20;
        int sum = left + right;
        System.out.println("literalByte=" + literalByte);
        System.out.println("sumTypeInt=" + sum);

        int five = 5;
        int two = 2;
        double integerDivision = five / two;
        double floatingDivision = (double) five / two;
        System.out.println("integerDivision=" + integerDivision);
        System.out.println("floatingDivision=" + floatingDivision);

        Object general = "Java";
        System.out.println("upcastIsString=" + (general instanceof String));

        String specific = (String) general;
        System.out.println("downcast=" + specific);

        try {
            Integer wrong = (Integer) general;
            System.out.println("unexpected=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("badDowncast=ClassCastException");
        }
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file; use **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TypeConversionDemo.java
java TypeConversionDemo
~~~

**Exact expected output** of the `java TypeConversionDemo` command (excluding JDK version information):

~~~text
widenIntToLong=120
widenIntToDouble=120.0
largeLongPreserved=false
byteFrom130=-126
positiveToInt=12
negativeToInt=-12
hugeDoubleToInt=2147483647
nanToInt=0
charToInt=65
intToChar=B
literalByte=100
sumTypeInt=30
integerDivision=2.0
floatingDivision=2.5
upcastIsString=true
downcast=Java
badDowncast=ClassCastException
~~~

### Explanation of important results

1. `int -> long` and `int -> double` are automatic widening conversions. The value 120 is preserved accurately; because the variable `asDouble` is `double`, printing displays `120.0`.
2. `long huge = 2^53 + 1` can no longer be represented accurately when converted to `double`. The value is rounded, so comparing after converting back to `long` yields `false`. **Do not equate widening with “always accurate”.**
3. `(byte) 130` narrows to 8 signed bits: 130 exceeds 127, resulting in `-126`. The cast is still permitted by Java without reporting overflow.
4. `(int) 12.9` returns 12 and `(int) -12.9` returns -12: the fractional part is truncated **toward 0**. For a finite `double` exceeding the `int` range, the cast result is clamped to the nearest boundary (`(int) 1.0e20` becomes `Integer.MAX_VALUE`). `(int) Double.NaN` becomes 0.
5. `char 'A'` widens to `int` as code value 65; casting `(char) 66` yields the character `B`.
6. The two `byte` variables in `left + right` are promoted to `int`. Assigning the result to `int sum` is valid; assigning directly to a `byte` variable is not allowed by the compiler unless the result is a suitable constant expression.
7. `five / two` occurs between two `int`s, yielding 2 **before** being assigned to `double` as `2.0`. Casting `five` to `double` **before division** produces `2.5`.
8. `Object general = "Java"` is an allowed reference widening (*upcast*). Casting down to `String` is valid when the actual object is a String. Casting down to `Integer` can still compile from `Object` but fails **at runtime**, throwing `ClassCastException`.

## 3. `int` constants in assignment context

Java allows assigning a constant expression of type `int` within the range of `byte`, `short`, or `char` without writing a cast. This exception applies only in specified contexts; do not generalize it into an implicit conversion for ordinary `int` variables.

~~~java
byte threshold = 100;  // int constant fits within byte range.
int runtime = 100;
// byte wrong = runtime; // Does not compile.
byte checked = (byte) runtime;
~~~

Whether an expression is a compile-time constant differs from a variable happening to hold a small value at runtime. The dedicated lesson on constant assignment will further distinguish `final` constant variables and their scope of application.
## 4. Casting at the right time in expressions

Operand types determine the operation type **before** the result is assigned. Therefore, `long wrong = (long) (50_000 * 50_000);` still receives the overflowed `int` product, whereas `long right = (long) 50_000 * 50_000;` performs multiplication in `long`, yielding `2500000000`. Casting after the calculation cannot recover lost bits. With division, `(double) 5 / 2` gives `2.5`, while `(double) (5 / 2)` only gives `2.0`.

## 5. Reference casting: checking the actual object

`Object o = "Java";` can be downcast to `String` because the actual object is a string. If that same reference is cast to `Integer`, the program throws `ClassCastException`. Casting **does not create a new object** and does not convert the content into a string.

~~~java
Object o = "Java";
if (o instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

Pattern matching `instanceof` is available in Java 17; the expression `null instanceof String` is `false`, while a valid cast of a `null` reference still produces `null`.

## 6. Mechanisms distinct from numeric casting

`Integer boxed = 42; int raw = boxed;` use boxing and unboxing respectively; if the wrapper is `null`, unboxing throws `NullPointerException`. `Integer.parseInt("42")` parses a string, not a reference cast. Java also does not support `(int) true`; if a numeric code from a boolean is needed, you must write an explicit rule such as `flag ? 1 : 0`.
## 7. Self-check exercises

1. **Implicit or explicit?** What category do `long x = 17;` and `byte y = (byte) 130;` belong to?  
   *Answer:* The first is implicit widening, the second is explicit narrowing and `y = -126`.
2. **When is precision lost?** Does `double d = 9_007_199_254_740_993L;` preserve every unit accurately?  
   *Answer:* No; `double` cannot accurately represent the integer `2^53 + 1`.
3. **Intermediate type:** Given `int a = 50_000, b = 50_000;`, which way is correct for a `long` product: `(long)(a*b)` or `(long)a*b`?  
   *Answer:* `(long) a * b`, because the cast happens before the multiplication.
4. **Division:** What do `double z = 7 / 2;` and `double w = (double) 7 / 2;` equal respectively?  
   *Answer:* `3.0` and `3.5`.
5. **Reference cast:** Is `Object o = "Hi"; String a = (String) o;` valid? What about `Integer b = (Integer) o;`?  
   *Answer:* Casting to String succeeds; casting to Integer throws `ClassCastException` at runtime.

## Pre-conversion checklist

- [ ] Distinguish **implicit widening** and **explicit narrowing**.
- [ ] Check **value range and precision**, not just type size.
- [ ] Determine the type of **each intermediate expression** before casting/assigning the result.
- [ ] Know that `byte`/`short`/`char` are usually promoted to `int` in arithmetic operations.
- [ ] Know that casting floating-point to integer truncates toward 0 and handles out-of-range values according to Java rules.
- [ ] Distinguish reference casting from object creation, parsing, and boxing.
- [ ] Do not assume a downcast is always safe; consider `instanceof`.

**Conclusion:** Java performs many **implicit** conversions when the context permits, but a cast `(TargetType)` is a **conversion request**, not a promise of preserving the value or succeeding at runtime. Consider the value range, expression kind, and dynamic type of the object before choosing how to convert.