# Numbers in switch and language version limits (Java)

## 1. Objectives

This lesson focuses on the **type of the selector expression in `switch`**, which numeric types Java supports in each version, and the impact of **numeric promotion** on the validity of `switch`/`case`. After this lesson, you will be able to:

- Choose `byte`, `short`, `char`, `int`, or their corresponding wrappers reliably for `switch` on Java 17.
- Explain why `byte + byte` produces `int`, why `case` labels must be valid constants, and why `long`/`double` cannot be used directly as selectors on Java 17/21.
- Distinguish `switch` statements and expressions, including `break`, `yield`, and branch exhaustiveness rules.
- Read historical version boundaries accurately: `String`/`enum`, pattern matching from Java 21, and expanded primitive selectors in Java 23–27 as a **preview** feature.
- Avoid casts that cause overflow or precision loss just to use `switch`.

**Primary runnable scope:** Java 17 and above, without preview flags. Examples using Java 21 features or Java 27 preview are clearly labeled and separated.

## 2. What is a selector? Accepted types on Java 17

In `switch (expression) { ... }`, `expression` is called the **selector**. Before inspecting any `case` branches, the compiler checks the *type of the entire selector expression*. It does not just look at the type of one variable inside the expression.

In Java 17 and in Java 21 for classic integer switches, the stably supported primitive numeric selectors are:

| Selector | Java 17 | Notes |
| --- | --- | --- |
| `byte` | Yes | Values −128..127 |
| `short` | Yes | Values −32768..32767 |
| `char` | Yes | Values 0..65535 |
| `int` | Yes | Values −2³¹..2³¹−1 |
| `Byte`, `Short`, `Character`, `Integer` | Yes | Wrappers handled via unboxing; `null` can cause `NullPointerException` |
| `long` | No | Including `1L` literals and `int + long` results |
| `float`, `double` | No | Not implicitly rounded to match `case` labels |
| `boolean` | No | Not a valid selector for classic integer `switch` |

`enum` has also been supported since Java 5 and `String` since Java 7, though they are not numeric types. Java 21 also supports **selectors of reference types** when using pattern matching for `switch`; see section 9 for details. Java 27 has a **preview** feature for broader primitive selectors; see section 10.

Valid examples on Java 17:

~~~java
byte b = 2;
short s = 300;
char c = 'A';
int i = 10;
Integer boxed = 2;

String a = switch (b) { case 2 -> "byte"; default -> "?"; };
String d = switch (s) { case 300 -> "short"; default -> "?"; };
String e = switch (c) { case 'A' -> "char"; default -> "?"; };
String f = switch (i) { case 10 -> "int"; default -> "?"; };
String g = switch (boxed) { case 2 -> "Integer"; default -> "?"; };
~~~

These are illustrative statements *inside a method*. They do not form a complete Java program; a full program is in section 8.

## 3. Expression promotion: byte + byte is no longer byte

Java applies **binary numeric promotion** to many arithmetic operators, including `+`, `-`, `*`, `/`, and `%`. When both operands are `byte`, `short`, or `char`, they are normally promoted to `int` before the operation occurs; the result has type `int`.

~~~java
byte left = 4;
byte right = 3;

int sum = left + right;      // type of (left + right) is int
// byte impossible = left + right; // compile error: int does not auto-narrow to byte

String text = switch (left + right) {
    case 7 -> "seven";
    default -> "other";
};
System.out.println(text); // seven
~~~

`switch (left + right)` is **valid**, because the selector has type `int`, which is also supported on Java 17. There is no need to cast back to `byte` to use `switch`.

If one operand is `long`, the addition expression is promoted to `long` (unless `float`/`double` with higher precedence is present) and cannot be used directly as a Java 17 selector:

~~~java
int count = 2;
long offset = 1L;

// Does not compile on Java 17 or Java 21:
// switch (count + offset) {
//     case 3L -> System.out.println("three");
// }
~~~

By the same logic, `switch (a * b)` with `int` or `byte` is accepted by *type*, yet the operation can **overflow** under Java arithmetic before matching any `case`. Just because a selector compiles does not mean the computed value stays in the expected range.

### Unary operators and automatic conversions

`+b`, `-b`, and `~b` with `b` of type `byte` also produce an `int` result (unary numeric promotion):

~~~java
byte b = 1;
int negated = -b;
int inverted = ~b;

System.out.println(negated); // -1
System.out.println(inverted); // -2
~~~

What matters when writing a `switch` is the **static type after applying expression rules**, not intuition from the original operands' declared types.

## 4. Case labels must be valid constants within the selector type's range

In a traditional constant `switch` (Java 17), a `case` label for an integer selector must be a **compile-time constant expression** and must be assignment-compatible with the selector type; an `int` constant may be narrowed to `byte`, `short`, or `char` when its value lies in the representable range.

~~~java
byte level = 100;
final int FIRST = 50;    // compile-time constant variable
final int SECOND = 50 + 50;

String category = switch (level) {
    case FIRST -> "first";
    case SECOND -> "second";
    default -> "other";
};
System.out.println(category); // second
~~~

`FIRST`/`SECOND` are `final int` variables initialized with constant expressions. They still work with `byte` because 50 and 100 lie within −128..127.

Conversely:

~~~java
byte b = 1;

// Does not compile on Java 17:
// String x = switch (b) {
//     case 128 -> "too large"; // 128 cannot be represented by byte
//     default -> "other";
// };

// Does not compile on Java 17:
// int dynamic = Integer.parseInt("1");
// String y = switch (b) {
//     case dynamic -> "one";    // dynamic is not a compile-time constant
//     default -> "other";
// };
~~~

Constants with the same value cannot be repeated across branches of the same `switch`:

~~~java
int n = 2;

// Does not compile: duplicate case value
// switch (n) {
//     case 2 -> System.out.println("two");
//     case 1 + 1 -> System.out.println("also two");
//     default -> System.out.println("other");
// }
~~~

`case 1 + 1` is a constant expression **with value 2**, so it duplicates `case 2`. This error is caught at compile time.

### Difference between constant types and runtime value types

An ordinary `int` variable, even if it has value 7 at runtime, never becomes a `case` constant. `final` alone is also insufficient if the value is computed by a method call. For example, `final int x = Integer.parseInt("7")` is still **not** a *constant variable* under the Java specification.

When you need to classify by dynamic ranges (e.g., `n >= min && n <= max`), use `if/else` on Java 17, or patterns/guards when using Java 21+ in the appropriate context. Do not try to force runtime conditions into constant `case` labels.

## 5. Char is a 16-bit unsigned integer, yet case labels have range rules

`char` can appear in a `switch` and represents a UTF-16 code unit from 0 to 65535. A character constant like `'A'` has value 65; Java allows writing either `case 'A'` or `case 65` when the selector is `char`:

~~~java
char letter = 'A';

String result = switch (letter) {
    case 65 -> "Latin capital A";
    default -> "another code unit";
};
System.out.println(result); // Latin capital A
~~~

However, `case -1` or `case 65536` is invalid for a `char` selector: those constants are outside the 0..65535 range.

`char` does not represent every Unicode character as **one** single value: supplementary characters outside the BMP use a UTF-16 surrogate pair. If you need to classify Unicode **code points**, obtain the `int` code point (for example `String.codePointAt(...)`), and then use `switch (intCodePoint)`. Do not assume every Unicode character is a single `char`.

## 6. Switch statements, switch expressions, and numeric branches

### Statement with colons (traditional syntax)

~~~java
int code = 2;
switch (code) {
    case 1:
        System.out.println("one");
        break;
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
~~~

The snippet above prints `two`. With the `case ...:` form, if `break` is missing, execution can **fall through** into subsequent branches. This is statement control-flow behavior, unrelated to automatic numeric type conversion.

### Switch rule with arrow

Since Java 14, the `case ... ->` form is standard syntax and does not fall through:

~~~java
int code = 2;
switch (code) {
    case 1 -> System.out.println("one");
    case 2, 3 -> System.out.println("two or three");
    default -> System.out.println("other");
}
~~~

This form prints `two or three`. In a **switch statement**, what follows the arrow must be a statement expression, a block, or `throw`; you cannot arbitrarily write a side-effect-free numeric expression and expect it to be a valid statement.

### Switch expression produces a value

A `switch` **expression** has been a standard feature since Java 14. It must produce a value for every possible path reaching a branch and must be **exhaustive**; with an `int` selector, `default` is normally required.

~~~java
int level = 3;

int score = switch (level) {
    case 1, 2 -> 10;
    case 3 -> {
        int bonus = 5;
        yield 20 + bonus; // 25
    }
    default -> 0;
};

System.out.println(score); // 25
~~~

Inside the `case 3 -> { ... }` block, the `yield` keyword returns the **result value of the switch expression**. `break` in a traditional switch statement only exits the statement; you do not use `break value` to return a value in Java 17 syntax.

Additionally, **the result type of a switch expression** is a separate question from **the type of the selector**. The values yielded by branches must be compatible with the assignment/return context; do not assume that because the selector is `byte`, the result always has type `byte`.

## 7. Wrappers, unboxing, null, and Number type limits

Java 17 supports `Byte`, `Short`, `Character`, and `Integer` as selectors via unboxing. Valid values inside wrappers work, yet **a null object cannot be unboxed**.

~~~java
Integer status = Integer.valueOf(2);
String message = switch (status) {
    case 1 -> "created";
    case 2 -> "accepted";
    default -> "unknown";
};
System.out.println(message); // accepted
~~~

If `status = null`, a traditional constant `switch (status)` on Java 17 throws `NullPointerException` before choosing any branch. `default` is **not** a mechanism for handling `null`.

`Long`, `Float`, `Double`, and `Number` are **not** selectors for traditional constant switches in Java 17. Example:

~~~java
Number numeric = Integer.valueOf(2);
// Does not compile on Java 17:
// switch (numeric) {
//     case 2 -> System.out.println("two");
// }
~~~

If the API contract guarantees the input is an `Integer`, you can take `numeric.intValue()` after confirming type/range; however, if `numeric` is a huge `Long` or a `BigDecimal` with a fractional part, `intValue()` can lose data. In general cases, use another classification approach or take advantage of pattern matching on Java 21+.

## 8. Complete Java 17+ program and output

Save as `NumericSwitchDemo.java`:

~~~java
public class NumericSwitchDemo {
    private static String byteLabel(byte code) {
        return switch (code) {
            case -1 -> "sentinel";
            case 0 -> "zero";
            case 127 -> "maximum byte";
            default -> "other";
        };
    }

    private static int score(int code) {
        return switch (code) {
            case 1, 2 -> 10;
            case 3 -> {
                int base = 20;
                yield base + 5;
            }
            default -> 0;
        };
    }

    public static void main(String[] args) {
        byte left = 4;
        byte right = 3;
        int sum = left + right; // binary numeric promotion: byte + byte -> int

        String sumLabel = switch (sum) {
            case 7 -> "seven";
            default -> "other";
        };
        System.out.println("sum=" + sum + ", label=" + sumLabel);

        System.out.println("byte -1=" + byteLabel((byte) -1));

        char letter = 'A';
        String charLabel = switch (letter) {
            case 65 -> "capital A";
            default -> "other";
        };
        System.out.println("char A=" + charLabel);

        Integer boxed = 2;
        System.out.println("boxed 2 score=" + score(boxed));

        System.out.println("code 3 score=" + score(3));

        long outsideInt = 2_147_483_648L;
        try {
            int exact = Math.toIntExact(outsideInt);
            System.out.println("exact=" + exact);
        } catch (ArithmeticException ex) {
            System.out.println("outside int range");
        }
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac --release 17 NumericSwitchDemo.java
java NumericSwitchDemo
~~~

Exact stdout:

~~~text
sum=7, label=seven
byte -1=sentinel
char A=capital A
boxed 2 score=10
code 3 score=25
outside int range
~~~

Explanation:

1. `left + right` has type `int`, so `switch (sum)` is valid.
2. `byteLabel((byte) -1)` matches `case -1` validly within the `byte` range.
3. The `char` selector matches integer constant `65` because the value is representable by `char`.
4. `Integer boxed` unboxes automatically to `int` when passed to `score(int)`; value 2 receives 10 points.
5. The `case 3` branch uses `yield` to return 25 points.
6. `Math.toIntExact` detects that 2,147,483,648 exceeds the `int` range. There is no dangerous silent cast from `long` to `int`.

## 9. Version limits: Java 21 expands switch to reference types

**Java 21** made *pattern matching for switch* a standard feature. This expands `switch` to **reference types** such as `Object`, `Number`, or `Long` when using valid patterns in `case` branches. It **does not** make primitive `long`, `float`, `double`, or `boolean` directly valid selectors in Java 21.

The example below requires JDK 21+, with no preview needed:

~~~java
public class ReferenceNumberSwitch {
    static String describe(Number value) {
        return switch (value) {
            case null -> "missing";
            case Integer i -> "int " + i;
            case Long l -> "long " + l;
            default -> "other number";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Long.valueOf(42)));
        System.out.println(describe(null));
        System.out.println(describe(Double.valueOf(1.5)));
    }
}
~~~

Compile/run with JDK 21 or newer:

~~~bash
javac --release 21 ReferenceNumberSwitch.java
java ReferenceNumberSwitch
~~~

Stdout:

~~~text
long 42
missing
other number
~~~

`case Long l` is a **type pattern** matching a `Long` object, not a `case 42L` constant for primitive `long`. `case null` appears in modern pattern switches, allowing intentional null handling; stable Java 17 does not support that same syntax. Distinguishing a **reference `Long` selector** from a **primitive `long` selector** is crucial when reading multi-version code.

In Java 21, you can add a `when` guard:

~~~java
static String classify(Number n) {
    return switch (n) {
        case null -> "missing";
        case Integer i when i > 0 -> "positive int";
        case Integer i -> "other int";
        default -> "other number";
    };
}
~~~

This is an *illustrative method* for Java 21+, not a standalone program. A guard is a runtime condition on a **pattern case**, unlike traditional numeric `case` labels which must be compile-time constants.

## 10. From Java 23 to Java 27: new primitive selectors remain in preview

Important version history:

| Version | Notable change |
| --- | --- |
| Java 1.0 | `switch` on `byte`, `short`, `char`, `int` |
| Java 5 | Added `enum` and wrappers `Byte`, `Short`, `Character`, `Integer` |
| Java 7 | `String` as selector |
| Java 12–13 | `switch expression` and `->` rule experimental (preview) |
| Java 14 | `switch expression` and `->` rule became standard |
| Java 17 | Traditional numeric selector types still limited up to `int`; pattern switch only preview, not standard syntax |
| Java 21 | Pattern matching for `switch` became standard; expanded selectors to reference types |
| Java 23 | *Primitive Types in Patterns, instanceof, and switch*: first preview |
| Java 24 | Second preview |
| Java 25 | Third preview (JEP 507) |
| Java 26 | Fourth preview (JEP 530) |
| Java 27 | Fifth preview (JEP 532); **not yet a standard language feature** |

In Java 27 with preview enabled, the scope of primitive selectors is expanded to include `long` and primitive types not previously usable directly. Example **for JDK 27 preview only**:

~~~java
public class PreviewLongSwitch {
    public static void main(String[] args) {
        long amount = 5_000_000_000L;
        String label = switch (amount) {
            case 0L -> "zero";
            case 5_000_000_000L -> "five billion";
            default -> "other";
        };
        System.out.println(label);
    }
}
~~~

Only when the environment has **JDK 27** installed with support for the corresponding preview feature, compile/run with:

~~~bash
javac --enable-preview --release 27 PreviewLongSwitch.java
java --enable-preview PreviewLongSwitch
~~~

Expected stdout:

~~~text
five billion
~~~

**Do not** use the preview example as proof that `switch (long)` runs under `--release 17` or `--release 21`. Preview features depend on the **exact JDK version and compile/run flags**; behavior/syntax may change or never become a standard feature. For Java 17 modules or long-lived systems, keep main examples within the stable `switch` scope.

## 11. Workarounds when input is genuinely long, double, or a big number

### 11.1. `long` whose value range is guaranteed to fit in `int`

If the data always fits within `int`, **check** before converting:

~~~java
static String classifyLongSafely(long value) {
    int small = Math.toIntExact(value); // throws ArithmeticException if outside int
    return switch (small) {
        case 0 -> "zero";
        case 1 -> "one";
        default -> "other int";
    };
}
~~~

This is an illustrative method for Java 17. Do not blindly cast `(int) value` if it could be out of range: for example, `(int) 4_294_967_296L` is `0`, which could mistakenly match `case 0` even though the input is nowhere near zero.

### 11.2. `long` with a range larger than `int`

If an application runs Java 17/21 with arbitrary primitive `long` values, you can use `if/else if` directly:

~~~java
static String classifyLargeLong(long value) {
    if (value == 5_000_000_000L) {
        return "five billion";
    }
    if (value == 0L) {
        return "zero";
    }
    return "other";
}
~~~

There is no need to convert to `String` and then `switch` just to bypass type checking; that adds conversion overhead and can obscure data semantics. If you are already processing a string protocol or have a status enum, switching on string/enum can be appropriate because the data contract is naturally that type.

### 11.3. `double` and precision concerns

On Java 17/21, `switch (double)` is not supported. Do not cast to `int` to classify floating-point numbers when the fractional part still matters: `(int) 2.9` gives 2, causing 2.9 to accidentally match the 2.0 branch.

If the data represents measurements, use range logic or error tolerances defined for the domain:

~~~java
static String temperatureBand(double celsius) {
    if (Double.isNaN(celsius)) {
        return "unknown";
    }
    if (celsius < 0.0) {
        return "freezing";
    }
    if (celsius < 30.0) {
        return "moderate";
    }
    return "hot";
}
~~~

This is an illustrative Java 17 method. Thresholds are merely for technical demonstration; real applications must set domain-appropriate limits. `NaN` needs a separate check because all ordering comparisons with `NaN` are false; `+Infinity` in the example above enters the `hot` branch and `-Infinity` enters `freezing`, so define an explicit infinity policy if inputs may contain these values.

### 11.4. BigInteger, BigDecimal, and Number

Big number classes can be compared using `BigInteger.compareTo`, `BigDecimal.compareTo`, or domain-specific APIs. With Java 21+, a `switch (Number n)` type pattern helps **classify the object's runtime class**, but does not turn an arbitrary `BigInteger` into a `case 123` constant. If you want to branch by value, compare values or convert to a narrower type **after verifying range and precision**.

## 12. Common pitfalls

| Code or assumption | Issue | How to handle |
| --- | --- | --- |
| `switch (byteValue + byteValue2)` is still a switch on byte | Addition promotes to `int` | Read the type of the whole expression; write cases within `int` range |
| `switch (longValue)` on Java 17 | Compile error on selector type | Use `Math.toIntExact` if range is guaranteed; otherwise use `if/else` |
| `switch (doubleValue)` on Java 17 | Compile error | Use range conditions, avoiding loss of fractional parts |
| `case 128` with a `byte` selector | Constant outside byte range | Use an in-range constant or change the selector model |
| `case variable` with a runtime variable | Not a constant expression | Use compile-time constants; dynamic conditions via `if` or guards on Java 21+ |
| `case 2` and `case 1 + 1` | Duplicate case label value | Remove duplicate labels |
| `switch ((int) hugeLong)` | Can overflow when narrowing | Check with `Math.toIntExact` beforehand |
| `default` will catch a null wrapper | Java 17 throws `NullPointerException` | Check null beforehand; or `case null` on Java 21+ where applicable |
| Switch expression with only a few `int` cases and no `default` | Not exhaustive | Add `default` or cover all cases |
| Using Java 27 preview code with Java 21 | Unsupported syntax | Stick to standard features of the target version |

## 13. Self-check exercises

**Exercise 1.** Is the following snippet valid on Java 17?

~~~java
byte x = 10, y = 20;
String label = switch (x + y) {
    case 30 -> "thirty";
    default -> "other";
};
~~~

**Answer:** Valid. `x + y` is `int` due to binary numeric promotion, and `case 30` is a valid `int` constant. The value of `label` is `"thirty"`.

**Exercise 2.** Why is `case 500` invalid in `switch (short s)`?

**Answer:** Actually it is **valid**: 500 is within the `short` range. `case 40000` is the one that is invalid because it exceeds 32767. Always check the range of the **selector type**, rather than judging from how an `int` literal is written.

**Exercise 3.** Why does declaring `final int id = Integer.parseInt("2")` still not allow `case id`?

**Answer:** `parseInt` is a method call, not a constant expression per the Java Language Specification. `final` only prevents reassigning the variable; it does not turn a runtime result into a compile-time constant.

**Exercise 4.** Does the Java 21 code `switch (Number n) { case Long l -> ... }` prove that `switch (long l)` is now supported?

**Answer:** No. The first case is **pattern matching on the reference type** `Long`, whereas the second uses **primitive** `long`. Expanding primitive selectors is a separate preview feature in newer JDKs.

**Exercise 5.** Given `long value = 4_294_967_296L`, what is dangerous about `switch ((int) value)`?

**Answer:** `(int) value` equals 0 because it keeps only the low 32 bits, so `case 0` could match unintentionally. If the value must stay within the `int` range, `Math.toIntExact(value)` will report an error instead of silently turning it into 0.

## 14. References and key takeaways

- [Java Language Specification, Java SE 17 — switch statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11) and [switch expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): selector rules, case labels, exhaustiveness, expression results.
- [Dev.java — Using preview features](https://dev.java/learn/first-steps/using-preview/): `switch expression` became a standard feature in Java 14.
- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): reference types and pattern branches.
- [Java SE 27 — Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html): JEP 532, fifth preview.

**Key takeaway:** First inspect the **static type of the selector after numeric promotion**. On Java 17, traditional integer switch accepts `byte`/`short`/`char`/`int` and their four corresponding wrappers; `case` labels are compile-time constants compatible with the selector's range. Java 21 expands `switch` to **reference types** via patterns, while direct `switch (long/float/double/boolean)` remains a **preview feature in Java 27**. Whenever casting to use `switch`, always verify value range and precision.