# `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` in Java

## 1. What Are the Six Wrapper Classes?

Java has six primitive types representing numbers discussed here: `byte`, `short`, `int`, `long`, `float`, `double`. Each type has a corresponding **wrapper class** in the `java.lang` package:

| Primitive type | Wrapper class | Number kind | Width |
| --- | --- | --- | ---: |
| `byte` | `Byte` | Signed integer | 8 bits |
| `short` | `Short` | Signed integer | 16 bits |
| `int` | `Integer` | Signed integer | 32 bits |
| `long` | `Long` | Signed integer | 64 bits |
| `float` | `Float` | IEEE 754 binary floating-point | 32 bits |
| `double` | `Double` | IEEE 754 binary floating-point | 64 bits |

These wrappers are **immutable objects**: once created, the internal value does not change. They are all `final` classes, all extend the abstract class `java.lang.Number`, and all support same-type comparison via `Comparable<T>`.

Example:

```java
byte primitiveByte = 7;
Byte wrappedByte = Byte.valueOf(primitiveByte);

int primitiveInt = 42;
Integer wrappedInt = Integer.valueOf(primitiveInt);

double primitiveDouble = 0.5;
Double wrappedDouble = Double.valueOf(primitiveDouble);
```

Important differences:

- **Primitive** (`int`, `double`, etc.) directly represents a primitive-type value; it has no instance methods and cannot be `null`.
- **Wrapper** (`Integer`, `Double`, etc.) is a reference to an object containing the value; it has useful methods like `compareTo`, `intValue`, `toString`, `equals`, can be `null`, and works where an object or a generic type argument is required.
- `Byte`, `Short`, `Integer`, and `Long` represent fixed-width integers; `Float` and `Double` represent finite floating-point numbers or special values like `NaN` and infinity.

This lesson focuses on the six numeric wrappers listed above. `Boolean` and `Character` are also primitive wrappers, but do not belong to the numeric group extending `Number`. `BigInteger` and `BigDecimal` are other object numeric types that do not directly correspond to a primitive.

## 2. Value Ranges and Key Constants

### 2.1. Integer wrappers

| Wrapper | Primitive | `MIN_VALUE` | `MAX_VALUE` |
| --- | --- | ---: | ---: |
| `Byte` | `byte` | `-128` | `127` |
| `Short` | `short` | `-32768` | `32767` |
| `Integer` | `int` | `-2147483648` | `2147483647` |
| `Long` | `long` | `-9223372036854775808` | `9223372036854775807` |

Each integer wrapper has the constants `SIZE` (number of bits), `BYTES` (number of bytes), and `TYPE` (the `Class` object representing the corresponding primitive).

```java
System.out.println(Integer.SIZE);  // 32
System.out.println(Long.BYTES);    // 8
System.out.println(Integer.TYPE);  // int
```

These are **illustrative lines inside a method**, not a complete program. You can use `Integer.MIN_VALUE` and `Integer.MAX_VALUE` when checking range before narrowing from `long` to `int`.

### 2.2. `Float` and `Double`: do not misunderstand `MIN_VALUE`

| Wrapper | Bits | `MAX_VALUE` | `MIN_VALUE` |
| --- | ---: | --- | --- |
| `Float` | 32 | About `3.4028235E38` | About `1.4E-45`, **positive** |
| `Double` | 64 | About `1.7976931348623157E308` | About `4.9E-324`, **positive** |

For `Float`/`Double`, `MIN_VALUE` is the **smallest representable nonzero positive number** (a subnormal number), **not** the negative number with the largest magnitude. The lowest finite negative value is `-Float.MAX_VALUE` or `-Double.MAX_VALUE`.

Other useful constants:

- `Float.MIN_NORMAL`, `Double.MIN_NORMAL`: smallest positive normal number.
- `Float.POSITIVE_INFINITY`, `Double.POSITIVE_INFINITY` and the `NEGATIVE_INFINITY` constants: positive/negative infinity.
- `Float.NaN`, `Double.NaN`: "Not-a-Number" value.
- `Float.SIZE == 32`, `Double.SIZE == 64`; `Float.BYTES == 4`, `Double.BYTES == 8`.

Both floating-point types can lose precision when representing decimal fractions or large integers. `Float` has about 24 bits of significand precision, and `Double` has about 53 bits; this differs from the total bit width of the type. Therefore, do not choose `Double` just because it can hold very large numbers and assume all decimal calculations are completely exact.

## 3. Relationship with `java.lang.Number`

`Number` is an abstract class for representing "a numeric value" as an object. All six wrappers extend it. Common conversion methods of `Number` include:

| Method | Return type | Meaning |
| --- | --- | --- |
| `byteValue()` | `byte` | Gets the value as `byte` |
| `shortValue()` | `short` | Gets the value as `short` |
| `intValue()` | `int` | Gets the value as `int` |
| `longValue()` | `long` | Gets the value as `long` |
| `floatValue()` | `float` | Gets the value as `float` |
| `doubleValue()` | `double` | Gets the value as `double` |

Polymorphism example:

```java
Number[] values = {
    Byte.valueOf((byte) 7),
    Short.valueOf((short) 300),
    Integer.valueOf(42),
    Long.valueOf(9_000_000_000L),
    Float.valueOf(1.25f),
    Double.valueOf(0.5)
};

for (Number value : values) {
    System.out.println(value.getClass().getSimpleName()
            + ": " + value.doubleValue());
}
```

Thanks to `Number`, code can read a **common numeric form** from different kinds of objects. However, the `...Value()` methods do not guarantee exact conversions:

```java
Number n = Integer.valueOf(257);
byte narrowed = n.byteValue(); // 1: keeps only the low 8 bits
```

A large `Long` converted to `double` can lose significand bits; a `Double` with a fractional part converted to `int` is truncated toward 0 or clamped at the boundary; `Float.NaN` converted to an integer type yields 0 per Java rules.

**`Number` does not define a common `parse`, `valueOf`, `compareTo`, or `add` for all subtypes.** Methods like `parseXxx`, `valueOf`, and `compare` are APIs specific to concrete wrappers. Declaring a variable as `Number` does not turn Java into a language with polymorphic arithmetic operators on objects:

```java
Number n = Integer.valueOf(12);
int a = n.intValue();     // valid
// int b = n + 1;         // does not compile: Number does not auto-unbox to int
```

When you want to preserve the concrete type, use `Integer`, `Long`, `Double`, or well-designed APIs/generics instead of assuming `Number` automatically converts to every primitive.

## 4. Creating Wrappers: `valueOf`, Autoboxing, and Constructors

The standard ways to obtain wrappers are **`valueOf`** or letting Java perform **autoboxing**:

```java
Byte b = Byte.valueOf((byte) 10);
Short s = Short.valueOf((short) 1000);
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(9_000_000_000L);
Float f = Float.valueOf(1.25f);
Double d = Double.valueOf(0.5);

Integer autoInteger = 42; // compiler inserts boxing operation
Double autoDouble = 0.5;  // autoboxing from double
```

Wrappers are immutable; to get a new value, assign a different wrapper:

```java
Integer count = 5;
count++; // unbox -> add 1 as int -> box, then reassign count
```

The `count` variable switches the object it references; **the original `Integer` object is not modified**. Because autoboxing involves object operations, in tight loops and heavy arithmetic it is usually preferable to use primitives if `null`/generics are not needed.

There is no need to call `new Integer(...)`, `new Double(...)`, or other legacy wrapper constructors. Constructors of this kind are deprecated, so prefer `valueOf`/autoboxing to express intent clearly and allow the JVM to reuse objects where appropriate.

### Warning when using `==` with wrappers

`==` between **two wrapper references** checks whether they point to the same object. `equals` checks value according to each class's contract. `Integer.valueOf` is required to cache at least the values `-128` through `127`, yet code must not rely on identity to compare numbers:

```java
Integer x = Integer.valueOf(100);
Integer y = Integer.valueOf(100);
System.out.println(x == y);      // true within the guaranteed cache range

Integer p = Integer.valueOf(200);
Integer q = Integer.valueOf(200);
System.out.println(p.equals(q));  // true
```

The result of `p == q` **must not be relied upon as a rule**, because caching outside the guaranteed range can vary by environment. When one side is a primitive and the other is a wrapper, the wrapper operand can be *unboxed* to perform a numeric comparison:

```java
Integer boxed = 42;
int primitive = 42;
System.out.println(boxed == primitive); // true: compares int values
```

Because expressions that look similar can carry reference or numeric semantics, when checking values of same-type wrappers, prefer `equals` (handling `null`) or convert to primitive explicitly when needed.

## 5. Autoboxing, Unboxing, and `null`

**Autoboxing** converts a primitive into a wrapper; **unboxing** converts a wrapper into a primitive:

```java
Integer boxed = 12; // autoboxing: int -> Integer
int raw = boxed;     // unboxing: Integer -> int
```

Unboxing a `null` reference throws `NullPointerException`:

```java
Integer missing = null;
// int n = missing; // NullPointerException at runtime
```

This trap also shows up in arithmetic, comparisons with primitives, or the `++` operator:

```java
Integer maybeCount = null;
// if (maybeCount > 0) { } // NullPointerException
// maybeCount++;            // NullPointerException
```

If `null` means "unknown," check first:

```java
Integer count = null;
int safeCount = count == null ? 0 : count;
```

Choose a default value of 0 only when business rules allow it; many applications must distinguish zero from missing data.

### Wrappers in collections and generics

Java generics require reference types, so:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> scores = new ArrayList<>();
scores.add(10);                // 10 is boxed into Integer
scores.add(20);
int first = scores.get(0);    // unboxing
```

`List<int>` is invalid in Java 17; use `List<Integer>`. Similarly, you can create `List<Long>`, `Map<String, Double>`, or `List<Number>`.

Note that `List<Integer>` is not a subtype of `List<Number>`, even though `Integer` extends `Number`: Java generics are **invariant** by default. To read a list of multiple numeric types, a signature like `List<? extends Number>` may fit, though writing to the list is restricted by the wildcard. This is a generic typing matter, not a difference in wrapper values.

Collections can contain `null` wrappers when the data structure permits, so reading from `List<Integer>` and then unboxing still risks `NullPointerException`.

## 6. Parsing Numeric Strings: `parseXxx`, `valueOf(String)`, and Radix

Each wrapper provides corresponding string parsing APIs:

| Wrapper | Returns primitive | Returns wrapper |
| --- | --- | --- |
| `Byte` | `Byte.parseByte(text)` | `Byte.valueOf(text)` |
| `Short` | `Short.parseShort(text)` | `Short.valueOf(text)` |
| `Integer` | `Integer.parseInt(text)` | `Integer.valueOf(text)` |
| `Long` | `Long.parseLong(text)` | `Long.valueOf(text)` |
| `Float` | `Float.parseFloat(text)` | `Float.valueOf(text)` |
| `Double` | `Double.parseDouble(text)` | `Double.valueOf(text)` |

Example:

```java
int a = Integer.parseInt("42");       // primitive int
Integer b = Integer.valueOf("42");    // Integer
long c = Long.parseLong("9000000000");
double d = Double.parseDouble("0.5");
```

**`parseXxx` does not create a wrapper as its result** (though the JIT/runtime may have internal optimizations), whereas `valueOf(String)` returns a wrapper object. Both can throw `NumberFormatException` if the string is invalid or exceeds the type's range.

### Number bases (radix) for integer wrappers

The four integer wrappers have overloads taking a **radix**, typically from 2 to 36:

```java
int hex = Integer.parseInt("FF", 16); // 255
int binary = Integer.parseInt("1010", 2); // 10
long base36 = Long.parseLong("Z", 36); // 35
```

If the string includes a prefix such as `"0xFF"` or `"0b1010"`, do not assume `parseInt(text, radix)` accepts the prefix as-is:

```java
int hex = Integer.parseInt("FF", 16); // valid
int prefixed = Integer.decode("0xFF"); // 255
// Integer.parseInt("0xFF", 16); // NumberFormatException
```

`Integer.decode`/`Long.decode`/`Byte.decode`/`Short.decode` support the hexadecimal and octal prefix rules of those APIs, but they are not general parsers for every Java literal form. Some separators valid in source code, such as the underscore in `1_000`, **are not automatically accepted** when parsing strings:

```java
int literal = 1_000;            // valid in Java code
// Integer.parseInt("1_000");  // NumberFormatException
```

`Integer.parseInt(" 42 ")` also does not automatically strip whitespace; only `trim()`/`strip()` when the input policy allows. For locale-specific formats (such as a decimal comma), `parseDouble` does not replace a locale-aware parser.

### Floating-point strings and special values

`Float.parseFloat` and `Double.parseDouble` accept decimal syntax or floating-point forms specified by the Java API; they can also parse `"NaN"`, `"Infinity"`, and `"-Infinity"`.

```java
double half = Double.parseDouble("0.5");           // 0.5
double infinity = Double.parseDouble("Infinity");  // positive infinity
boolean infinite = Double.isInfinite(infinity);    // true
```

Syntactically valid input strings do not necessarily carry finite values: check `Float.isFinite` / `Double.isFinite` if business logic requires finiteness. Do not use `Double.parseDouble` to store monetary decimals needing exact precision; consider `BigDecimal` from the input string.

## 7. Converting Back to Strings and Integer Utilities

Wrappers provide `toString`, `toString(primitive)`, and `valueOf`; for `Integer`/`Long`, there is additional support for binary, hexadecimal, and unsigned formatting:

```java
String decimal = Integer.toString(255);       // "255"
String hex = Integer.toHexString(255);        // "ff"
String binary = Integer.toBinaryString(10);   // "1010"
String base16 = Integer.toString(255, 16);    // "ff"
String unsigned = Integer.toUnsignedString(-1); // "4294967295"
```

`Integer.toUnsignedString(-1)` and `Long.toUnsignedString(-1L)` treat the same 32/64-bit pattern under an **unsigned interpretation**. They do not give Java `uint`/`ulong` primitive types.

Example reading a negative value as an unsigned bit pattern:

```java
int mask = -1;
System.out.println(Integer.toUnsignedString(mask));  // 4294967295
System.out.println(Long.toUnsignedString(-1L));       // 18446744073709551615
```

For `byte` and `short`, you can widen without sign extension:

```java
int uByte = Byte.toUnsignedInt((byte) -1);   // 255
int uShort = Short.toUnsignedInt((short) -1); // 65535
```

`Integer` and `Long` also provide utility methods such as `bitCount`, `highestOneBit`, `lowestOneBit`, `numberOfLeadingZeros`, `numberOfTrailingZeros`, `rotateLeft`, `rotateRight`, and unsigned comparison/division (`compareUnsigned`, `divideUnsigned`, etc.). These methods operate on **fixed-width bit patterns**. Calling them does not automatically turn `Integer`/`Long` into unsigned integer types.

Operators like `+`, `-`, `&`, and `<<` apply to primitives after unboxing, not as instance methods on wrappers.

## 8. Comparisons, `equals`, `compareTo`, and Special Values

### 8.1. Integer wrappers

For `Byte`, `Short`, `Integer`, and `Long`, `equals` checks for the same **wrapper class** and the same value:

```java
Integer a = Integer.valueOf(10);
Integer b = Integer.valueOf(10);
Long c = Long.valueOf(10L);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false: different wrapper type
```

`Integer.compare(x, y)`, `Long.compare(x, y)`, or `compareTo` gives signed integer ordering. `Integer.compareUnsigned`/`Long.compareUnsigned` are used when the same bit patterns must be interpreted as unsigned numbers.

```java
System.out.println(Integer.compare(-1, 1));        // -1
System.out.println(Integer.compareUnsigned(-1, 1)); // 1
```

Do not write `a - b` as an `Integer` `Comparator` because subtraction can overflow, yielding wrong ordering. Use `Integer.compare(a, b)` or `Comparator.comparingInt(...)` depending on the situation.

### 8.2. `Float` and `Double`: `NaN`, sign of zero, and ordering

Here is a memorable difference between primitive comparison operators and the wrapper contract:

```java
double nan = Double.NaN;

System.out.println(nan == nan); // false
System.out.println(
        Double.valueOf(nan).equals(Double.valueOf(nan))); // true

System.out.println(+0.0 == -0.0); // true
System.out.println(
        Double.valueOf(+0.0).equals(Double.valueOf(-0.0))); // false
```

`Double.equals` considers all `NaN` values equal under the wrapper contract, while distinguishing `+0.0` from `-0.0`. `Float.equals` has corresponding behavior. This keeps `equals` and `hashCode` of wrappers consistent, including in collections.

`Double.compare(a, b)` and `Float.compare(a, b)` define an ordering suitable for sorting: `-0.0` is ordered less than `+0.0`, and `NaN` is ordered greater than every numeric value, including positive infinity.

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(
        Double.compare(Double.NaN, Double.POSITIVE_INFINITY)); // 1
```

Do not use `Double.compare` to decide whether two values are numerically close enough. If a problem needs a tolerance, define an explicit epsilon comparison policy; approximate equality can be **non-transitive**, making it unsuitable for `equals`/`hashCode` contracts or sorting `Comparator`s.

### 8.3. Comparing across wrapper types

`Integer.valueOf(10).equals(Long.valueOf(10L))` is `false`, even though both integers represent the same mathematical value. If you need to compare two `Number` values of different types, define the conversion rule first:

- For integers within suitable ranges, comparing in a wider integer type may be reasonable.
- Converting a very large `long` to `double` can **lose digits**, causing two distinct values to become the same `double`.
- For decimal numbers requiring exactness, use an appropriate decimal representation from the source rather than blindly casting every `Number` to `double`.

There is no single `Number.equalsNumericValue` method shared across all subtypes and value ranges.

## 9. Converting via `xxxValue()` Can Lose Values

Wrappers provide methods to extract values in several primitive types. They are convenient, but usually follow rules similar to Java casts:

```java
Integer n = Integer.valueOf(257);
byte small = n.byteValue(); // 1

Double d = Double.valueOf(-2.9);
int truncated = d.intValue(); // -2

Long large = Long.valueOf(9_007_199_254_740_993L);
double approximate = large.doubleValue();
// approximate holds the value 9_007_199_254_740_992
```

Distinguish among:

- **Value-preserving:** `Integer.intValue()`, `Long.longValue()` for their own corresponding types, or converting a smaller integer to a wider type with sufficient range.
- **Integer narrowing:** `long` → `int`, `int` → `short`/`byte` can drop high bits; wrapper operations do not report overflow automatically.
- **Floating-point to integer:** `Double.intValue()`, `Float.longValue()` truncate the fractional part toward 0 when finite and in range; NaN and out-of-range values produce special results per Java rules.
- **Integer to floating-point:** `Long.doubleValue()` and `Integer.floatValue()` can round low-order bits.

If you want to check whether a `long` fits in the `int` range, use `Math.toIntExact(longValue)` instead of `Integer.valueOf((int) longValue)`:

```java
long quantity = 3_000_000_000L;

// int wrong = (int) quantity; // negative value due to int range overflow
// int checked = Math.toIntExact(quantity); // throws ArithmeticException
```

For `BigInteger` and `BigDecimal`, `intValueExact()`/`longValueExact()` apply a different contract to check for information loss. The six primitive wrappers in this lesson **are not** arbitrary-length integer or decimal types.

## 10. Complete Java 17 Example

Create the file `NumberWrappersDemo.java`:

```java
public class NumberWrappersDemo {
    public static void main(String[] args) {
        Number[] numbers = {
                Byte.valueOf((byte) 7),
                Short.valueOf((short) 300),
                Integer.valueOf(42),
                Long.valueOf(9_000_000_000L),
                Float.valueOf(1.25f),
                Double.valueOf(0.5)
        };

        for (Number value : numbers) {
            System.out.println(
                    value.getClass().getSimpleName() + " = " + value);
        }

        System.out.println("parse hex = " + Integer.parseInt("FF", 16));
        System.out.println("unsigned byte = " + Byte.toUnsignedInt((byte) -1));
        System.out.println("unsigned int = " + Integer.toUnsignedString(-1));
        System.out.println("narrowed 257 = "
                + Integer.valueOf(257).byteValue());

        Integer a = Integer.valueOf(200);
        Integer b = Integer.valueOf(200);
        System.out.println("boxed equals = " + a.equals(b));

        System.out.println("primitive NaN == NaN = "
                + (Double.NaN == Double.NaN));
        System.out.println("wrapper NaN equals = "
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));

        System.out.println("primitive signed zero = " + (+0.0 == -0.0));
        System.out.println("wrapper signed zero equals = "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));

        System.out.println("unsigned compare(-1, 1) = "
                + Integer.compareUnsigned(-1, 1));
    }
}
```

Compile/run:

```bash
javac NumberWrappersDemo.java
java NumberWrappersDemo
```

Output:

```text
Byte = 7
Short = 300
Integer = 42
Long = 9000000000
Float = 1.25
Double = 0.5
parse hex = 255
unsigned byte = 255
unsigned int = 4294967295
narrowed 257 = 1
boxed equals = true
primitive NaN == NaN = false
wrapper NaN equals = true
primitive signed zero = true
wrapper signed zero equals = false
unsigned compare(-1, 1) = 1
```

The special values and parsing in the example use APIs whose behavior is specified by Java; `valueOf(200)` is only checked via `equals`, so the result does not depend on caching outside the guaranteed range.

## 11. Which Wrapper Should You Choose?

| Need | Choice |
| --- | --- |
| Small integer guaranteed in -128..127 range | `Byte` if API/generics require an object; `byte` otherwise |
| 16-bit signed integer | `Short`/`short` when required by a protocol/format |
| General integers, indices, counters | `Integer`/`int` if within 32-bit range |
| Integers larger than `int` range | `Long`/`long` if within 64-bit range |
| Binary floating-point with lower memory requirement, tolerating larger error | `Float`/`float` |
| General binary floating-point needing higher precision than `float` | `Double`/`double` |
| Collections, generics, potentially absent (`null`) data | Corresponding wrapper, with an explicit `null`-handling policy |
| Integers exceeding `long` range | `BigInteger` |
| Decimals requiring exact decimal digits and explicit rounding rules | `BigDecimal` created from an appropriate decimal source |

`Byte`/`Short` do not always save memory compared to `Integer` when used as **objects**: a wrapper incurs object and reference overhead, unlike primitives inside a primitive array. When storing millions of non-nullable numbers, `byte[]`, `int[]`, and `double[]` arrays usually avoid boxing overhead compared to `List<Byte>`, `List<Integer>`, and `List<Double>`.

`Float`/`Double` are not a safe default choice for currency because decimals such as `0.1` cannot be represented exactly in binary. When inputs are decimal, `BigDecimal` from a string preserves the exact source digits; storing monetary amounts as integers in the smallest unit is also a viable strategy within an appropriate range.

## 12. Common Mistakes and Fixes

1. **Using `==` on two wrappers to compare values.** Results can depend on caching and identity. Use `equals`, `Objects.equals(a, b)` when `null` is possible, or controlled unboxing.
2. **Unboxing `null`.** `Integer missing = null; int n = missing;` throws `NullPointerException`; check for missing values before computing.
3. **Thinking `valueOf` and `parseXxx` have the same return type.** `Integer.parseInt` returns `int`, whereas `Integer.valueOf` returns `Integer`.
4. **Mistaking `Float.MIN_VALUE` for the most negative value.** It is the **smallest positive nonzero** value; the smallest finite negative value is `-Float.MAX_VALUE`.
5. **Converting a wrapper via `xxxValue()` and assuming no data loss.** `Integer.valueOf(257).byteValue()` is `1`, and `Long.doubleValue()` can lose precision.
6. **Letting Java implicitly unbox in ambiguous comparisons.** `Integer` compared to `int` unboxes; two `Integer`s with `==` is a reference comparison. Make your intended semantics explicit.
7. **Assuming every `Number` has `valueOf`, `parseInt`, or object addition.** Those APIs belong to concrete wrappers; `Number` only provides an interface to extract primitive-typed values.
8. **Parsing strings with differing syntax without error handling.** `Integer.parseInt("1_000")` is unsupported even though `1_000` is a valid Java literal; string parsing can throw `NumberFormatException`.
9. **Ignoring `NaN` and infinity.** `Double.valueOf("NaN")` is valid to the parser, yet may violate data contracts; use `isNaN`, `isInfinite`, `isFinite`.
10. **Confusing the floating-point wrapper `equals` contract with primitive `==`.** Wrappers treat NaN as equal to NaN under `equals` and distinguish the sign of zero; primitives do the opposite in both cases.
11. **Using subtraction of two numbers in a comparator.** `return a-b` can overflow; use `Integer.compare(a,b)`, `Long.compare(a,b)`, and appropriate comparators.
12. **Using wrapper objects in hot arithmetic loops unnecessarily.** Boxing/unboxing can increase allocations or overhead and introduce `null` risk; use primitives and primitive arrays when appropriate.
13. **Reading unsigned numbers as signed.** The bit pattern `0xFFFFFFFF` is `-1` when read as signed `int`, but `"4294967295"` when calling `Integer.toUnsignedString(-1)`.
14. **Assuming `equals` across `Number` subtypes compares mathematical values.** `Integer(10)` and `Long(10)` are not equal under `equals`; choose a common conversion rule safely based on the data.

## 13. Self-Check Exercises

**Question 1.** Given two variables:

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);
```

Should you use `a == b` or `a.equals(b)` to check for the same integer value?

**Answer:** `a.equals(b)`. `==` checks identity of the two wrapper references and is not guaranteed to hold for all values.

**Question 2.** Is `Float.MIN_VALUE` negative or positive? If you need the smallest finite negative `float` in arithmetic order, how do you write it?

**Answer:** `Float.MIN_VALUE` is positive, being the smallest nonzero positive number; the finite negative bound is `-Float.MAX_VALUE`.

**Question 3.** What happens when running:

```java
Integer count = null;
int n = count;
```

**Answer:** Throws `NullPointerException` at the unboxing step.

**Question 4.** What types do the expressions `Integer.parseInt("42")` and `Integer.valueOf("42")` return?

**Answer:** Primitive `int` and wrapper `Integer`, respectively.

**Question 5.** Why is `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` `true`, whereas `Double.NaN == Double.NaN` is `false`?

**Answer:** The `Double.equals` wrapper method uses the object value contract, treating NaN as equal to NaN to stay consistent with `hashCode`; the primitive `==` operator follows floating-point arithmetic rules, under which NaN is not equal to any number, including itself.

**Question 6.** What does `Byte.toUnsignedInt((byte)-1)` return? And `Integer.valueOf(257).byteValue()`?

**Answer:** `255` and `1`. The first interprets the all-`1` 8-bit pattern as unsigned; the second narrows `int` 257 to its low 8 bits.

**Question 7.** Given `Number n = Long.valueOf(9_007_199_254_740_993L);`, does calling `n.doubleValue()` preserve the exact integer value?

**Answer:** No. `double` does not represent the integer `2^53 + 1` exactly; the value is rounded to `9_007_199_254_740_992`. Calling `doubleValue()` reports no error and does not retain the lost information.

**Question 8.** Should you use `List<int>` in Java 17? Why can `List<Integer>` contain `null`?

**Answer:** `List<int>` is invalid in Java generics; use `List<Integer>` because generics require reference types. Because `Integer` is a reference type, some collections allow `null` elements, unlike primitive `int`.

**Key takeaway:** `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` are the six immutable wrapper classes for numeric primitives, all extending `Number`. They help with parsing, formatting, comparing, bit manipulation, and using generics/collections. Choose types by value range and precision; distinguish primitives from objects, `parseXxx` from `valueOf`, `==` from `equals`, and check for `null` as well as precision loss during conversion.