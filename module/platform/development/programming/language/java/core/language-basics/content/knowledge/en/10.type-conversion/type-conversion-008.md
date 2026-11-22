# Conversions in Assignment, Method Invocation, and Expressions — Java 17+

## 1. Objective: the same value, three conversion contexts

Java does not apply a single “auto-convert” rule everywhere. The compiler inspects the **context** of the value:

1. **Assignment context**: placing a value into a variable, field, or array element with a defined type.
2. **Method invocation context**: passing an argument expression to a parameter, while also handling overload selection.
3. **Expression context**: determining the types and conversions of operands in addition, multiplication, comparison, string concatenation, conditional operators, etc.

~~~java
byte value = 7;              // Assignment with an int constant within byte range
long wide = value;            // Assignment: byte -> long
System.out.println(value + 1); // Expression: byte is promoted to int
~~~

The three lines involve the same `value` variable, yet the conversion semantics are **not the same**. A program behaves correctly when the types are accepted by the compiler **and** the converted value still satisfies business requirements.

This lesson focuses on rules commonly used in Java 17+, especially **widening**, **narrowing**, **boxing/unboxing**, arithmetic expressions, and overloaded method calls.

## 2. Foundations: widening, narrowing, boxing, and unboxing

| Mechanism | Example | Meaning |
|---|---|---|
| Identity conversion | `int x = 5;` | Source type matches target type |
| Widening primitive | `long x = 5;` | `int` converts to `long` |
| Narrowing primitive | `byte b = (byte) 130;` | Cast to a smaller type, may lose data |
| Boxing | `Integer x = 5;` | Converts `int` value to `Integer` |
| Unboxing | `int x = Integer.valueOf(5);` | Extracts `int` from `Integer` |
| Widening reference | `Object o = "Hi";` | `String` reference assigned to `Object` type |
| Boxing + widening reference | `Number n = 5;` | `int` → `Integer` → `Number` |
| Unboxing + widening primitive | `long n = Integer.valueOf(5);` | `Integer` → `int` → `long` |

Not every combination is performed automatically. For instance:

~~~java
Long good = 5L;
// Long wrong = 5; // Invalid: int does not auto-widen to long and then box to Long
~~~

`5` is an `int` literal, while `5L` is a `long` literal. Java does not automatically allow **primitive widening followed by boxing to `Long`** in this assignment.

`boolean` does not convert to/from numeric types via primitive widening or narrowing. `String` is also not a primitive type: `Integer.parseInt("5")` is a string-parsing API call, not an implicit conversion from `String` to `int`.

## 3. Assignment context

When the left-hand side of an assignment has a defined type, the compiler must check whether the expression on the right-hand side can be converted to that type.

~~~java
byte small = 8;
int asInt = small;       // byte -> int
long asLong = asInt;     // int -> long
double asDouble = asLong; // long -> double
~~~

The assignments above are valid without a cast. However, **valid does not always mean strictly exact**: a very large `long` value converted to `double` can lose trailing digits due to finite significand precision.

Narrowing assignments are generally **not performed automatically** on runtime variables:

~~~java
int source = 130;
// byte b = source;   // Compile error: possible lossy conversion
byte b = (byte) source;
System.out.println(b); // -126
~~~

The `(byte)` cast only requests the conversion, **without** checking whether 130 fits in -128..127. After narrowing, the value changes to -126.

### Places where assignment context applies

In addition to `x = expression` statements, assignment context rules appear in variable initializers, fields, array elements, and return contexts matching the declared return type:

~~~java
long[] values = {1, 2, 3}; // int literals can be assigned to long elements

static long getCount() {
    int count = 7;
    return count; // int -> long in return context
}
~~~

Do not infer from an assignment allowing constant narrowing that **every Java context** allows the same thing.


**Specifically for `int` constants within `byte`/`short`/`char` range**, assignment has a compile-time narrowing exception (`byte b = 7;` is valid); the method argument `takeByte(7)` does not get this exception. Distinguish the two contexts before adding casts.

## 4. Method invocation context: arguments must match parameter types

A method declares parameter types. At a call site, Java inspects the argument expression types to find an applicable method.

~~~java
static void acceptLong(long value) {
    System.out.println("long=" + value);
}

// In main:
byte b = 7;
acceptLong(b); // Valid: byte -> long
~~~

This is **primitive widening in method invocation context**.

Conversely, **the in-range `int` constant assignment rule does not apply automatically to a `byte` parameter**:

~~~java
static void acceptByte(byte value) {
    System.out.println("byte=" + value);
}

// acceptByte(7);       // Compile error: int does not auto-narrow to byte
acceptByte((byte) 7);   // Valid: explicit cast
~~~

Distinguish clearly:

| Syntax | Compiles? | Why |
|---|---|---|
| `byte b = 7;` | Yes | Constant expression narrowing exception in assignment |
| `acceptByte(7);` | No | Method invocation does not narrow `int` constants to `byte` |
| `acceptByte((byte) 7);` | Yes | Argument after cast already has type `byte` |
| `acceptLong(7);` | Yes | `int` widens to `long` |
| `acceptLong((byte) 7);` | Yes | `byte` widens to `long` |

**Good practice:** pass the exact parameter type using appropriate literals or value-producing functions; only use a cast when justified and after checking the value range.

## 5. Boxing and unboxing in method calls

Since Java 5, Java has supported **autoboxing** and **unboxing** in appropriate contexts; Java 17 continues to use this mechanism.

~~~java
static void showNumber(Number number) {
    System.out.println(number.getClass().getSimpleName());
}

// In main:
showNumber(5); // Prints Integer
~~~

`5` starts as an `int`. In the call above, Java can box it to `Integer`, then apply reference widening to `Number`.

Conversely:

~~~java
static void takeLong(long value) {
    System.out.println(value);
}

Integer boxed = Integer.valueOf(42);
takeLong(boxed); // Integer unboxing -> int, then widening to long
~~~

**Null pitfall:** unboxing a `null` reference causes a `NullPointerException` at runtime:

~~~java
Integer missing = null;
// long value = missing; // Compiles, but throws NullPointerException at runtime
~~~

The compiler checks conversion compatibility, not whether the wrapper is non-`null` at runtime.

## 6. Overloading: choosing a method before performing conversions

When there are multiple methods with the **same name** but different parameters, the compiler resolves overloading based on argument types and phases of finding applicable methods. Essentially, Java prioritizes calls applicable via *strict* conversions such as widening first; only if none is found does it consider options involving boxing/unboxing, and then suitable varargs cases.

~~~java
static void choose(long value) {
    System.out.println("choose(long)");
}

static void choose(Integer value) {
    System.out.println("choose(Integer)");
}
~~~

With:

~~~java
choose(7);                  // choose(long)
choose(Integer.valueOf(7)); // choose(Integer)
~~~

Why?

- `7` has type **`int`**; `int -> long` is primitive widening, so `choose(long)` is selected during the strict invocation phase.
- `Integer.valueOf(7)` has type **`Integer`**; `choose(Integer)` takes the exact reference type, so it is chosen before unboxing-then-widening.

This is not a simplistic “always prefer primitive” rule. **The argument type and available overloads** decide. Overloads with multiple parameters, subtypes, varargs, or generics have even more specific selection rules.

**Practice:** avoid creating overloads with different business meanings solely based on boxing vs. numeric primitives; the API easily becomes confusing when callers switch from primitive to wrapper.

## 7. Expression context: arithmetic auto-promotes types

In arithmetic expressions with small integer operands, Java applies **numeric promotion**. Specifically, `byte`, `short`, and `char` are normally promoted to `int` before ordinary arithmetic addition, subtraction, multiplication, or division.

~~~java
byte a = 100;
byte b = 20;

int sum = a + b; // a+b has type int
System.out.println(sum); // 120

// byte wrong = a + b; // Error: expression result is int
byte castResult = (byte) (a + b); // Only safe if value fits in byte
~~~

The constant assignment exception is different again:

~~~java
byte constantSum = 100 + 20; // Valid because this is an int constant expression = 120
~~~

**Both lines produce 120, yet the compiler handles them differently:**

- `byte constantSum = 100 + 20;`: constant expression, allowing narrowing in assignment context.
- `byte s = a + b;`: expression based on `byte` variables, result is `int` and does not auto-narrow to `byte`.

When there is a `long`, `float`, or `double` operand, the result is computed under the corresponding promotion rules. For example:

~~~java
double result = 3 + 0.5;
System.out.println(result); // 3.5
~~~

A `double` operand causes addition to be performed in `double` floating-point.

## 8. Comparison table of the three contexts

| Situation | Example code | Valid? | Key takeaway |
|---|---|---|---|
| Widening assignment | `long n = 7;` | Yes | `int` → `long` |
| In-range `int` constant assignment to `byte` | `byte b = 7;` | Yes | Special assignment rule |
| Assigning `int` variable to `byte` | `byte b = intValue;` | Usually no | Needs cast/check |
| Boxed assignment then reference widening | `Number n = 7;` | Yes | `int` → `Integer` → `Number` |
| Assigning `int` to `Long` | `Long n = 7;` | No | Does not auto `int` → `long` → `Long` |
| Passing `int` literal to `byte` parameter | `acceptByte(7);` | No | Method invocation does not narrow constants |
| Passing `byte` to `long` parameter | `acceptLong((byte) 7);` | Yes | Primitive widening |
| Calling `Number` parameter with `int` | `acceptNumber(7);` | Yes | Boxing + reference widening |
| Expression `byte + byte` | `int s = a + b;` | Yes | Numeric promotion to `int` |
| Assigning `byte + byte` result to `byte` | `byte s = a + b;` | No | Does not auto-narrow runtime results |
| Assigning constant expression to `byte` | `byte s = 100 + 20;` | Yes | In-range constant expression |
| Compound assignment on `byte` | `b += 10;` | Yes | Implicit narrowing, can overflow |
| Concatenating `String` with number | `"n=" + 7` | Yes | Result is `String` `"n=7"` |

Not every conversion falls into just a single cell in the table: an expression can undergo **numeric promotion first**, and then **assignment conversion afterwards**. Analyze step by step.

## 9. Standalone runnable Java 17 program

Create a file with the exact name **`ConversionContextsDemo.java`**:

~~~java
public final class ConversionContextsDemo {
    private ConversionContextsDemo() {}

    static void acceptLong(long value) {
        System.out.println("call long=" + value);
    }

    static void acceptByte(byte value) {
        System.out.println("call byte=" + value);
    }

    static void acceptNumber(Number value) {
        System.out.println("call Number type="
                + value.getClass().getSimpleName());
    }

    static void choose(long value) {
        System.out.println("choose=long");
    }

    static void choose(Integer value) {
        System.out.println("choose=Integer");
    }

    public static void main(String[] args) {
        byte small = 7;
        long widened = small;
        System.out.println("assignment widening=" + widened);

        byte constant = 120;
        final int KNOWN = 12;
        byte fromFinalConstant = KNOWN;
        Byte boxedConstant = 9;
        System.out.println("assignment constant=" + constant);
        System.out.println("assignment final=" + fromFinalConstant);
        System.out.println("assignment boxed constant=" + boxedConstant);

        int runtime = 130;
        byte narrowed = (byte) runtime;
        System.out.println("assignment explicit cast=" + narrowed);

        Integer boxed = Integer.valueOf(42);
        long unboxedAndWidened = boxed;
        System.out.println("assignment unbox widen=" + unboxedAndWidened);
        Number asNumber = 17;
        System.out.println("assignment Number type="
                + asNumber.getClass().getSimpleName());
        Long fromLongLiteral = 17L;
        System.out.println("assignment Long=" + fromLongLiteral);

        acceptLong(small);
        acceptByte((byte) 7);
        acceptNumber(5);

        choose(7);
        choose(Integer.valueOf(7));

        byte a = 100;
        byte b = 20;
        int sum = a + b;
        byte constantSum = 100 + 20;
        System.out.println("expression promoted=" + sum);
        System.out.println("expression constant sum=" + constantSum);
        System.out.println("expression mixed=" + (3 + 0.5));

        long wrong = 2_000_000_000 + 2_000_000_000;
        long correct = 2_000_000_000L + 2_000_000_000;
        System.out.println("expression overflow int=" + wrong);
        System.out.println("expression safe long=" + correct);

        byte counter = 120;
        counter += 10;
        System.out.println("compound assignment=" + counter);

        System.out.println("concat=" + 1 + 2);
        System.out.println("parenthesized=" + (1 + 2));

        double fractional = 8.9;
        System.out.println("explicit double cast=" + (int) fractional);

        Integer missing = null;
        try {
            long shouldFail = missing;
            System.out.println(shouldFail);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }
    }
}
~~~

**Requirements:** JDK 17 or later, terminal opened in the directory containing the file. No Maven, Gradle, or libraries outside the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ConversionContextsDemo.java
java -cp . ConversionContextsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ConversionContextsDemo.java
java -cp . ConversionContextsDemo
~~~

**Expected output:**

~~~text
assignment widening=7
assignment constant=120
assignment final=12
assignment boxed constant=9
assignment explicit cast=-126
assignment unbox widen=42
assignment Number type=Integer
assignment Long=17
call long=7
call byte=7
call Number type=Integer
choose=long
choose=Integer
expression promoted=120
expression constant sum=120
expression mixed=3.5
expression overflow int=-294967296
expression safe long=4000000000
compound assignment=-126
concat=12
parenthesized=3
explicit double cast=8
null unboxing=NullPointerException
~~~

**Key points to verify:**

1. `byte constant = 120` and `byte fromFinalConstant = KNOWN` are valid thanks to the `int` constant exception in assignment context.
2. `acceptByte((byte) 7)` requires a cast because method invocation does not automatically narrow an `int` literal to `byte`.
3. `choose(7)` picks `long` via strict invocation; `choose(Integer.valueOf(7))` picks `Integer`.
4. `a + b` has type `int` even though both variables are `byte`; `100 + 20` is a constant expression assignable to `byte`.
5. `wrong` produces an overflowed `int` result before assigning to `long`; `correct` uses `long` right at addition.
6. `counter += 10` performs implicit narrowing and becomes -126.
7. `"concat=" + 1 + 2` concatenates Strings into `12`, unlike numeric addition in parentheses.
8. `missing` is a null `Integer`; runtime unboxing throws `NullPointerException`, which is intentionally caught.

## 10. Exercises and answers

### Exercise A — same value, different contexts

Suppose we have:

~~~java
static void takeByte(byte value) {}

byte a = 100;
takeByte(a);
// takeByte(100);
~~~

**Answer:** `byte a = 100` is valid due to the `int` constant exception in assignment. `takeByte(a)` is valid because the argument already has type `byte`; `takeByte(100)` is invalid because method invocation does not automatically narrow an `int` literal. You can write `takeByte((byte) 100)`.

### Exercise B — constant or runtime variable?

~~~java
byte a = 100 + 20;
byte x = 100;
byte y = 20;
// byte b = x + y;
~~~

**Answer:** the first line is valid because `100+20` is an `int` constant equal to 120. The line `byte b = x+y` errors because the addition operator promotes both `byte`s to `int`, and the result does not auto-narrow to `byte`.

### Exercise C — boxing and widening

~~~java
Number a = 5;
Integer b = 5;
long c = b;
// Long d = 5;
~~~

**Answer:** `a` is valid via boxing `int -> Integer` then reference widening; `b` is valid via boxing; `c` is valid via unboxing then widening `int → long`. `Long d = 5` is invalid; write `5L`.

### Exercise D — addition occurs before assignment

~~~java
int x = 2_000_000_000;
long a = x + x;
long b = (long) x + x;
System.out.println(a);
System.out.println(b);
~~~

**Answer:**

~~~text
-294967296
4000000000
~~~

`a` receives the overflowed `int` result, while `b` performs `long` addition because the first operand was cast beforehand.

### Exercise E — overload selection

~~~java
static void choose(long x) { System.out.println("long"); }
static void choose(Integer x) { System.out.println("Integer"); }

// In main:
choose(3);
choose(Integer.valueOf(3));
~~~

**Answer:**

~~~text
long
Integer
~~~

### Exercise F — compound assignment

~~~java
byte b = 127;
b += 1;
System.out.println(b);
~~~

**Answer:** `-128`. The `+=` operator includes a narrowing conversion to `byte` and does not report overflow automatically. If unexpected negative values are unacceptable, compute in `int` and check range beforehand.

## 11. Summary checklist

- [ ] Distinguish **assignment**, **method invocation**, and **expression context**.
- [ ] Know that primitive widening allows assigning or passing arguments when types are compatible.
- [ ] Know the exception for assigning in-range `int` constants into `byte`/`short`/`char`.
- [ ] Understand that the exception does **not** mean a method taking `byte` automatically accepts `int` literals.
- [ ] Know boxing/unboxing and the risk of unboxing `null`.
- [ ] Understand `Number n = 5` is valid whereas `Long n = 5` is not.
- [ ] Know overload resolution can choose widening before boxing.
- [ ] Remember `byte`/`short`/`char` are promoted to `int` in arithmetic operations.
- [ ] Distinguish compound assignment from ordinary `=` assignment.
- [ ] Determine operand types **before** adding to avoid overflow.
- [ ] Do not confuse `String` concatenation with numeric addition.
- [ ] Use casts after checking values and matching business requirements.
- [ ] Run `ConversionContextsDemo.java` on JDK 17+ and verify every line of expected output.

**Conclusion:** Java decides conversions based on **where the value is used**. Assignment allows special `int` constant narrowing; method calls use parameter type adaptation and overload resolution rules; expressions have numeric promotion and operator-specific semantics. To write correct code, trace **source type → context → conversion → actual value**, instead of looking only at the receiving variable's type.