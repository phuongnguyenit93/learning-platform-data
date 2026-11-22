# Unary Sign Operators `+`, `-`, and Logical Complement `!` — Java 17+

In Java, `+`, `-`, and `!` are **unary operators** when placed before **one** operand. They must be distinguished from binary addition and subtraction.

~~~java
int number = 7;
int positive = +number;   // 7.
int negative = -number;   // -7.
boolean online = true;
boolean offline = !online; // false.
~~~

`+x` preserves the numeric value after applying **unary numeric promotion**; `-x` negates the numeric value; `!condition` inverts a boolean value. They **do not modify the source variable** (unlike `++x`, `x++`, or `--x`).

## 1. Recognizing the Three Operators

| Expression | Name | Valid Operand Types | Result |
| --- | --- | --- | --- |
| `+x` | Unary plus | Numeric primitive or unboxed numeric wrapper | Numeric value after type promotion |
| `-x` | Unary minus | Numeric primitive or unboxed numeric wrapper | Negated value after type promotion |
| `!x` | Logical complement | `boolean` or unboxed `Boolean` | Inverted `boolean` value |

For example, `+5` is not two-operand addition, whereas `5 + 2` is binary addition. Similarly, `-5` is unary minus, whereas `5 - 2` is binary subtraction. `!` cannot be used with `int`, `double`, `String`, or any object unless that object can be unboxed to `boolean`.

## 2. Standalone Java 17+ Program

Create a UTF-8 file **`UnarySignsAndNotDemo.java`**:

~~~java
public class UnarySignsAndNotDemo {
    static String typeOf(int unused) {
        return "int";
    }

    static String typeOf(long unused) {
        return "long";
    }

    static String typeOf(double unused) {
        return "double";
    }

    public static void main(String[] args) {
        int number = 7;
        System.out.println("unaryPlus=" + (+number));
        System.out.println("unaryMinus=" + (-number));
        System.out.println("binaryPlus=" + (10 + number));
        System.out.println("binaryMinus=" + (10 - number));
        System.out.println("originalNumber=" + number);

        byte small = 5;
        short medium = 6;
        char letter = 'A';
        long large = 7L;
        double fraction = 2.5;

        System.out.println("plusByteType=" + typeOf(+small));
        System.out.println("minusShortType=" + typeOf(-medium));
        System.out.println("plusCharType=" + typeOf(+letter));
        System.out.println("plusCharValue=" + (+letter));
        System.out.println("plusLongType=" + typeOf(+large));
        System.out.println("minusDoubleType=" + typeOf(-fraction));
        System.out.println("minusDoubleValue=" + (-fraction));

        Integer boxedNumber = 8;
        Boolean boxedFalse = Boolean.FALSE;
        System.out.println("boxedMinusType=" + typeOf(-boxedNumber));
        System.out.println("boxedMinusValue=" + (-boxedNumber));
        System.out.println("boxedNot=" + (!boxedFalse));

        boolean ready = true;
        boolean enabled = false;
        System.out.println("notReady=" + (!ready));
        System.out.println("doubleNot=" + (!!ready));
        System.out.println("groupedNot=" + (!(ready && enabled)));
        System.out.println("notComparison=" + (!(number > 10)));
        System.out.println("deMorgan="
                + ((!(ready && enabled))
                        == ((!ready) || (!enabled))));

        int minimum = Integer.MIN_VALUE;
        System.out.println("minNegatedInt=" + (-minimum));
        System.out.println("minNegatedAsLong=" + (-(long) minimum));
        try {
            Math.negateExact(minimum);
            System.out.println("unexpected=no-error");
        } catch (ArithmeticException ex) {
            System.out.println("negateExact=ArithmeticException");
        }

        double negativeZero = -0.0;
        System.out.println("negativeZero=" + negativeZero);
        System.out.println("zerosEqual=" + (negativeZero == +0.0));
        System.out.println("negativeZeroReciprocal=" + (1.0 / negativeZero));

        double notANumber = Double.NaN;
        System.out.println("notNaNEquality="
                + (!(notANumber == notANumber)));

        Integer missingNumber = null;
        try {
            int unused = -missingNumber;
            System.out.println("unexpectedNumber=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullNumber=NullPointerException");
        }

        Boolean missingFlag = null;
        try {
            boolean unused = !missingFlag;
            System.out.println("unexpectedFlag=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullBoolean=NullPointerException");
        }
    }
}
~~~

Run with JDK 17 or later in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 UnarySignsAndNotDemo.java
java UnarySignsAndNotDemo
~~~

**Exact expected stdout** of `java UnarySignsAndNotDemo` (excluding JDK version output):

~~~text
unaryPlus=7
unaryMinus=-7
binaryPlus=17
binaryMinus=3
originalNumber=7
plusByteType=int
minusShortType=int
plusCharType=int
plusCharValue=65
plusLongType=long
minusDoubleType=double
minusDoubleValue=-2.5
boxedMinusType=int
boxedMinusValue=-8
boxedNot=true
notReady=false
doubleNot=true
groupedNot=true
notComparison=true
deMorgan=true
minNegatedInt=-2147483648
minNegatedAsLong=2147483648
negateExact=ArithmeticException
negativeZero=-0.0
zerosEqual=true
negativeZeroReciprocal=-Infinity
notNaNEquality=true
nullNumber=NullPointerException
nullBoolean=NullPointerException
~~~

The `typeOf(int)`, `typeOf(long)`, and `typeOf(double)` overloads demonstrate **the static type of the expression at compile time**. They prove that `+small` has type `int`, no longer `byte`. The code intentionally catches the demonstrated exceptions to keep stdout deterministic.

## 3. Unary `+` and Binary `+`

~~~java
int n = 4;
int unchanged = +n; // 4.
int total = n + 5;   // 9.
~~~

- `+n` has only one numeric operand and does not increment `n`.
- `n + 5` has two operands and performs addition.
- `"count=" + n` is binary `+` for **string concatenation** because one operand is a `String`.

Unary `+` **does not** read a string and parse it into a number:

~~~java
// int invalid = +"42";  // Compile error.
int parsed = Integer.parseInt("42"); // 42.
~~~

Even though the value does not change, unary `+` still applies numeric promotion. This matters for `byte`, `short`, and `char`.

## 4. Unary Numeric Promotion

For unary `+` and `-`, Java applies **unary numeric promotion**:

| Original Operand | Type of `+x` or `-x` |
| --- | --- |
| `byte`, `short`, `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |
| `Byte`, `Short`, `Character` | Unboxed then promoted to `int` |
| `Integer`, `Long`, `Float`, `Double` | Unboxed to the corresponding primitive |

~~~java
byte b = 5;
int a = +b;  // 5, type int.
int c = -b;  // -5, type int.
// byte d = -b; // Error: cannot auto-assign int to byte.

char letter = 'A';
int codeUnit = +letter; // 65, type int.
~~~

`char` is a UTF-16 code unit, so `+'A'` returns `int` 65 rather than a signed character. With numeric wrappers, **unboxing** can throw `NullPointerException`:

~~~java
Integer missing = null;
// int result = -missing; // Throws NullPointerException at runtime.
~~~

Check for null if the data may be absent.

## 5. Unary `-`: Negation Is Not Always Safe

~~~java
int n = 12;
int opposite = -n; // -12; n remains 12.
~~~

Negating an integer at the negative boundary can **overflow** because the `int` range is asymmetric:

~~~java
int min = Integer.MIN_VALUE; // -2147483648.
int stillMin = -min;         // -2147483648 (int overflow).
long correct = -(long) min; // 2147483648.
~~~

The mathematical value `2147483648` cannot be represented as an `int`. Java does not automatically throw an exception on ordinary integer negation. If you want to **detect overflow**, use `Math.negateExact(min)`, which throws `ArithmeticException`. `Long.MIN_VALUE` has the same behavior.

For floating-point numbers, the negative sign on **zero** is preserved:

~~~java
double negZero = -0.0;
System.out.println(negZero == 0.0); // true.
System.out.println(1.0 / negZero);  // -Infinity.
~~~

`+0.0` and `-0.0` are equal under primitive `==` but differ in their sign bit; unary minus produces `-0.0` from `+0.0`, and unary plus does not clear the negative sign of `-0.0`.

## 6. Logical Complement `!` Is Only for Booleans

~~~java
boolean online = true;
boolean offline = !online; // false.

boolean ready = true;
boolean enabled = false;
boolean blocked = !(ready && enabled); // true.
~~~

| Expression | Result |
| --- | --- |
| `!true` | `false` |
| `!false` | `true` |
| `!!true` | `true` |
| `!(true && false)` | `true` |
| `!(true || false)` | `false` |

Do not use `!` on integers as in languages that have truthiness:

~~~java
int count = 0;
// boolean wrong = !count; // Compile error.
boolean empty = !(count > 0); // true.
~~~

`!` is **logical complement**; `~` is the **bitwise complement** operator on integral types. The two operators are not interchangeable.

With `Boolean`, Java automatically **unboxes** to apply `!`, so null can cause an exception:

~~~java
Boolean setting = null;
// boolean disabled = !setting; // Throws NullPointerException.
~~~

### De Morgan's Laws

For boolean expressions `a` and `b`:

| Negated Compound Expression | Equivalent Transformed Form |
| --- | --- |
| `!(a && b)` | `!a || !b` |
| `!(a || b)` | `!a && !b` |

In cases where `a` and `b` have side effects (method calls, state mutations), evaluate the semantics of each expression when refactoring; for ordinary boolean variables, this table helps negate conditions accurately and clearly.

## 7. Precedence and Parentheses

The unary operators `+`, `-`, and `!` have higher precedence than binary addition/subtraction and comparison/logical operators:

~~~java
int a = 6;
int b = 2;
int first = -a + b;   // -4.
int second = -(a + b); // -8.

boolean smaller = !(a > b); // false.
~~~

In `-a + b`, `-a` is the subexpression. In `-(a + b)`, the minus sign applies to **the entire sum**. With `!`, you must likewise negate **the entire condition** when needed:

~~~java
// boolean wrong = !a > b; // Type mismatch: !a requires boolean.
boolean correct = !(a > b);
~~~

## 8. Common Pitfalls

| Misconception | Fact |
| --- | --- |
| “`+x` always keeps the type of `x`.” | `byte`, `short`, `char` are promoted to `int` |
| “`-x` mutates `x` directly.” | No, it returns a new value |
| “`+ "12"` turns a string into a number.” | False; use parsing such as `Integer.parseInt` |
| “`!0` is true.” | Invalid: `!` requires a boolean |
| “`!` is like `~`.” | `!` is logical negation; `~` is bitwise complement |
| “`-Integer.MIN_VALUE` is positive.” | Overflows `int`, result remains `MIN_VALUE` |
| “`Boolean` can use `!` even when null.” | Null causes `NullPointerException` on unboxing |
| “`-0.0` is identical to `+0.0` in every operation.” | Equal under `==`, but differs in reciprocal and sign bit |

## 9. Self-Check

1. Given `int x = 6; int y = -x;`, what are `x` and `y`?  
   *Answer:* 6 and -6.
2. How does `-(3 + 2)` differ from `-3 + 2`?  
   *Answer:* -5 and -1.
3. Given `byte b = 7; var n = -b;`, what is the type of `n`?  
   *Answer:* `int`.
4. Given `var code = +'A';`, what are the type and value of `code`?  
   *Answer:* `int`, 65.
5. What is the value of `!(true && false)`?  
   *Answer:* `true`.
6. Does `Boolean flag = null; boolean x = !flag;` run normally?  
   *Answer:* No; it throws `NullPointerException`.
7. How do `-Integer.MIN_VALUE` and `-(long) Integer.MIN_VALUE` differ?  
   *Answer:* The `int` result is -2147483648, whereas the `long` result is 2147483648.
8. What does `1.0 / -0.0` return?  
   *Answer:* `-Infinity`.

## Checklist

- [ ] Distinguish unary `+x`/`-x` from binary `a+b`/`a-b`.
- [ ] Understand that unary `+` does not change the value, yet can promote the numeric type.
- [ ] Understand that `-` negates values and can overflow at the minimum integer value.
- [ ] Use `!` only for booleans, not integers or `String`.
- [ ] Check for null before unboxing wrappers.
- [ ] Remember floating-point numbers have `+0.0` and `-0.0` with different sign bits.
- [ ] Use parentheses to negate the exact intended expression.
- [ ] Use `Math.negateExact` if business logic requires detecting overflow on negation.

**Conclusion:** Unary `+` and `-` operate on **numeric operands after promotion**, while unary `!` applies only to **booleans**. Knowing the result type, precedence scope, and edge cases such as null, overflow, and signed zero will help you use these three operators accurately.