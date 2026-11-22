# Float.parseFloat, Double.parseDouble, and valueOf in Java

## 1. Goal: same floating-point string, different return types

In Java, a string such as `"3.5"` can be parsed into a primitive floating-point value or into a wrapper object:

```java
float f = Float.parseFloat("3.5");
Float boxedF = Float.valueOf("3.5");

double d = Double.parseDouble("3.5");
Double boxedD = Double.valueOf("3.5");
```

All four variables represent the mathematical value 3.5 in the example above, but **their data types and how you work with them differ**:

| Method | Input Type | Return Type | Role |
| --- | --- | --- | --- |
| `Float.parseFloat(String)` | `String` | primitive `float` | Parses to binary32 |
| `Float.valueOf(String)` | `String` | wrapper `Float` | Parses and returns an object containing binary32 |
| `Double.parseDouble(String)` | `String` | primitive `double` | Parses to binary64 |
| `Double.valueOf(String)` | `String` | wrapper `Double` | Parses and returns an object containing binary64 |

This lesson belongs to **Java Core — Numbers / Floating-Point Parsing**. After completing it, you should be able to:

1. Read signatures accurately and choose `parseFloat`/`parseDouble` when you need a primitive, and `valueOf(String)` when you need a wrapper.
2. Understand **32-bit vs. 64-bit precision**: replacing `Float` with `Double` does not merely change the object class—it also changes precision and value range.
3. Recognize that the parser has its own numeric grammar, syntax errors, and special values that require separate validation.
4. Understand the effects of boxing/unboxing, overloads, wrapper equality, signed zero, and NaN.
5. Run and explain Java 17+ examples on return types, precision, and comparisons on your own.

**Key principle:** `parseFloat` differs from `Float.valueOf(String)` in **return type**; `parseDouble` differs from `Double.valueOf(String)` in the same way. However, `Float` and `Double` **differ in binary number format and precision**. Do not conflate these two kinds of differences into one.

## 2. Parse returns a primitive, valueOf(String) returns a wrapper

The two pairs of methods have standard signatures:

```text
public static float  Float.parseFloat(String s)
public static Float  Float.valueOf(String s)
public static double Double.parseDouble(String s)
public static Double Double.valueOf(String s)
```

The lines above are **illustrative signature notation**, not Java code for declaring a new class.

### 2.1. Same string parsing, different target types

`Float.valueOf(s)` parses the string with the same semantics as `Float.parseFloat(s)` and returns a `Float` containing the resulting `float` value. `Double.valueOf(s)` works similarly with `Double.parseDouble(s)` and the `Double` wrapper.

```java
float raw = Float.parseFloat("2.75");
Float object = Float.valueOf("2.75");

System.out.println(raw);       // 2.75
System.out.println(object);    // 2.75
```

Stdout is identical because `println` supports both primitives and objects. **Do not infer from the printed output** that the two expressions have the same compile-time type.

### 2.2. How the type difference affects computation or object APIs

Primitive `float`/`double` are suitable for arithmetic and APIs that accept primitives. Wrapper `Float`/`Double` are immutable objects that can:

- Be stored in `List<Float>` or `Map<String,Double>`.
- Be held in a reference variable that accepts `null` to represent missing data, if the design permits.
- Provide instance methods such as `equals`, `compareTo`, and `hashCode`.
- Be used with generics, which **do not accept primitives** as type arguments.

This does not mean every call to `valueOf` forces the JVM to allocate a new object. Wrappers may be reused depending on implementation/API policy. **Do not rely on reference `==` to check numerical equality** between two wrapper objects.

## 3. Boxing and unboxing make the two forms look alike

Java has autoboxing/unboxing:

```java
float a = Float.parseFloat("1.25");    // float -> float
Float b = Float.valueOf("1.25");      // Float -> Float

Float c = Float.parseFloat("1.25");   // boxing float -> Float
float d = Float.valueOf("1.25");      // unboxing Float -> float

double e = Double.parseDouble("1.25"); // double -> double
Double f = Double.valueOf("1.25");     // Double -> Double

Double g = Double.parseDouble("1.25");// boxing double -> Double
double h = Double.valueOf("1.25");    // unboxing Double -> double
```

All eight assignments are valid. **The method's original return type does not change** when the left-hand variable has a different type: the compiler simply applies a permitted conversion in the assignment context.

| Source Expression | Target Variable | Additional Step |
| --- | --- | --- |
| `Float.parseFloat(s)` | `float` | None |
| `Float.parseFloat(s)` | `Float` | Boxing |
| `Float.valueOf(s)` | `Float` | None |
| `Float.valueOf(s)` | `float` | Unboxing |
| `Double.parseDouble(s)` | `double` | None |
| `Double.parseDouble(s)` | `Double` | Boxing |
| `Double.valueOf(s)` | `Double` | None |
| `Double.valueOf(s)` | `double` | Unboxing |

**Note:** if a wrapper variable is assigned `null` by another source, unboxing can throw `NullPointerException`:

```java
Double missing = null;
// double result = missing; // runtime NullPointerException
```

However, `Double.valueOf("1.25")` with a valid string does not return `null`: it returns a `Double` object.

## 4. The difference between float and double is not just the wrapper

`float` and `double` are both IEEE 754 binary floating-point primitives, but they have different widths and precisions.

| Property | `float` | `double` |
| --- | --- | --- |
| Format | binary32 | binary64 |
| Width | 32 bits | 64 bits |
| Significand precision | 24 bits | 53 bits |
| Approximate useful significant decimal digits | 6–9 | 15–17 |
| Largest finite positive constant | `Float.MAX_VALUE` | `Double.MAX_VALUE` |
| Smallest nonzero positive number (subnormal) | `Float.MIN_VALUE` | `Double.MIN_VALUE` |
| Parsing method | `Float.parseFloat(s)` | `Double.parseDouble(s)` |

Decimal numbers such as `0.1` mostly cannot be stored with absolute exactness in a finite binary representation. `Float.parseFloat("0.1")` is rounded directly to `float`; `Double.parseDouble("0.1")` is rounded to `double`. Consequently, **the two values can differ when both are brought to type `double` for comparison**.

### 4.1. Precision example

```java
float f = Float.parseFloat("0.1");
double d = Double.parseDouble("0.1");

System.out.println(f);           // 0.1
System.out.println(d);           // 0.1
System.out.println((double) f);  // 0.10000000149011612
System.out.println(f == d);      // false
```

The printed `0.1` for `float` is the short decimal string form that reproduces the value when parsed back; it **does not mean** `float` stores 1/10 exactly. Widening `float` to `double` on the third line reveals the binary32 value after rounding.

Specifically:

- `Float.parseFloat("0.1") == 0.1f` is true: both have type `float` and the same binary32 value.
- `Float.parseFloat("0.1") == 0.1` is false: the right-hand side is `double`, while the `float` on the left is widened without recovering the lost precision bits.
- When exact decimal representation is required by business logic, consider `BigDecimal` constructed directly from the **original string**, rather than trying to promote `float` to `double` to "fix" the error.

### 4.2. Do not mechanically parse to double and then cast to float

`(float) Double.parseDouble(s)` may look similar to `Float.parseFloat(s)`, but Java/the JDK provides a dedicated `float` parser to round decimal values according to **binary32** rules. Rounding first to binary64 and then narrowing to binary32 can introduce **double-rounding** at subtle boundary cases.

If the requirement is a `float` value read from a string, **prefer `Float.parseFloat(s)`**; there is no need to detour through `Double.parseDouble`. If the requirement is truly `double`, use `Double.parseDouble` and keep the appropriate type throughout subsequent calculations.

## 5. Successful parsing and validation are two separate layers

`Double.parseDouble`/`Float.parseFloat` support decimal numbers (`"1.25"`, `"1e3"`), hexadecimal floating-point (`"0x1.8p1"`), f/d suffixes, and the tokens `NaN` and `Infinity`. The suffix does not change the return type specified by the API. Syntactically invalid strings such as `"1_000.0"`, `"1,5"`, and `"0x1.8"` cause `NumberFormatException`; a null input causes `NullPointerException`.

A syntactically valid string that is too large or too small may be rounded to infinity or zero; `isFinite` excludes NaN and Infinity, but does not prove no precision was lost. Detailed syntax, special numbers, rounding, locale, decimal exactness, and range validation are explained in depth in dedicated lessons of this chapter. When using `parseFloat` or `parseDouble`, always choose the target type first and validate the domain of the result.

## 6. Runnable program A: return types and overloads

Save as **`FloatingParseTypes.java`**:

```java
public class FloatingParseTypes {
    static String describe(float x) {
        return "float " + x;
    }

    static String describe(Float x) {
        return "Float " + x;
    }

    static String describe(double x) {
        return "double " + x;
    }

    static String describe(Double x) {
        return "Double " + x;
    }

    public static void main(String[] args) {
        float primitiveFloat = Float.parseFloat("3.5");
        Float boxedFloat = Float.valueOf("3.5");
        double primitiveDouble = Double.parseDouble("3.5");
        Double boxedDouble = Double.valueOf("3.5");

        System.out.println(describe(primitiveFloat));
        System.out.println(describe(boxedFloat));
        System.out.println(describe(primitiveDouble));
        System.out.println(describe(boxedDouble));

        System.out.println(boxedFloat.getClass().getSimpleName());
        System.out.println(boxedDouble.getClass().getSimpleName());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 FloatingParseTypes.java
java FloatingParseTypes
```

**Stdout:**

```text
float 3.5
Float 3.5
double 3.5
Double 3.5
Float
Double
```

The four `describe` calls select an overload based on the **expression type** at the call site, not on `"3.5"` looking like a decimal floating-point number. This is a practical way to demonstrate the difference in return types when default `println` prints them in the same format.

## 7. Wrapper equality, identity, NaN, and signed zero

Because `Float.valueOf(String)`/`Double.valueOf(String)` return wrapper objects, there are two kinds of comparison that are easily confused.

### 7.1. Two wrappers: `equals` instead of `==`

```java
Float a = Float.valueOf("1.5");
Float b = Float.valueOf("1.5");

System.out.println(a.equals(b)); // true
```

`a.equals(b)` uses `Float`'s equality rules. `a == b` between two `Float` references checks **object identity**, which may depend on caching; it should not be used to ask whether two numbers have the same value.

If one side is a primitive `float`, the `==` operator may unbox the wrapper and perform a primitive comparison:

```java
float raw = Float.parseFloat("1.5");
Float boxed = Float.valueOf("1.5");
System.out.println(raw == boxed); // true
```

Do not assume every `==` written with a wrapper compares values of the same type; you must check the compile-time types of **both** operands.

### 7.2. `Float` differs from `Double` under `equals`

```java
System.out.println(Float.valueOf("1.5")
        .equals(Double.valueOf("1.5"))); // false
```

The two wrappers are of different classes, so `Float.equals` does not consider a `Double` equivalent, even when both represent the exact mathematical quantity 1.5. If an API mixes `Number` or multiple wrappers, it must have an explicit data policy.

### 7.3. NaN and signed zero

```java
System.out.println(Double.parseDouble("NaN")
        == Double.parseDouble("NaN")); // false

System.out.println(Double.valueOf("NaN")
        .equals(Double.valueOf("NaN"))); // true

System.out.println(Double.parseDouble("-0.0")
        == Double.parseDouble("0.0")); // true

System.out.println(Double.valueOf("-0.0")
        .equals(Double.valueOf("0.0"))); // false
```

This rule comes from **primitive equality** and **wrapper equality**, not because strings `"NaN"` or `"-0.0"` are parsed "non-standardly" by `valueOf`.

`Double.compare(-0.0,+0.0)` also distinguishes the two zeros and orders negative zero before positive zero. For `Double.NaN`, `Double.compare` has a defined ordering suitable for wrapper ordering. When using `HashSet<Double>` or `TreeSet<Double>`, you need to understand these rules rather than arbitrarily adding an epsilon in `equals` or a comparator.

## 8. Which overloads does valueOf have?

The name `valueOf` on wrapper classes appears with multiple parameter types; not every overload parses a string:

```java
Float a = Float.valueOf(2.5f);    // valueOf(float), does not parse String
Float b = Float.valueOf("2.5");   // valueOf(String), parses string

Double c = Double.valueOf(2.5);   // valueOf(double), does not parse String
Double d = Double.valueOf("2.5"); // valueOf(String), parses string
```

**Important:** `Float.valueOf(2.5f)` receives an already-existing binary32 value; only `Float.valueOf("2.5")` starts from string characters. `Double.valueOf(2.5)` receives an existing `double`.

If the input source is a `float` that is then converted to `Double`:

```java
float f = Float.parseFloat("0.1");
Double wrappedWidened = Double.valueOf((double) f);
```

`wrappedWidened` holds that exact previously rounded `float` value after widening, **not** the binary64 value obtained from `Double.valueOf("0.1")`. Switching wrappers cannot make rounding steps that have already occurred disappear.

## 9. Practice exercises on return types

1. Compare the compile-time types of `Float.parseFloat("1.5")` and `Float.valueOf("1.5")`; when passed to overloads `describe(float)` and `describe(Float)`, which call is selected?
2. Explain why `Float f = Float.parseFloat("2.5")` is valid even though `parseFloat` returns a primitive.
3. Predict `Float.valueOf("1.5").equals(Double.valueOf("1.5"))` and explain the wrapper contract.
4. State why `Float.parseFloat("0.1") == Double.parseDouble("0.1")` is false whereas `Float.parseFloat("0.1") == 0.1f` is true.
5. Choose the appropriate parser and data type for a sensor reading expecting `double` and a `List<Float>`. What conditions need to be checked after parsing?

**Answer key:** `parseFloat` returns a primitive, `valueOf(String)` returns a wrapper; boxing/unboxing does not change the signature. Wrappers of different classes are not `equals` even for the same mathematical quantity, and a binary32 value does not equal a binary64 value when decimal 0.1 is rounded differently. Choose the API based on the target type, while validating finiteness/range according to the contract.

**References:** [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html), [JLS boxing/unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).