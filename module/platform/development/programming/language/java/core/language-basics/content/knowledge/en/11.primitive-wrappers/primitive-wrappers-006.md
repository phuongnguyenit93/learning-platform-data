# `parseInt()`, `parseDouble()`, `valueOf()`, and Result Types — Java 17+

When reading numbers from configuration, command-line arguments, or forms, Java often initially receives the data as a `String`. To perform calculations, you need to **parse the string** (*parsing*) to obtain a numeric value. Methods with similar-looking names have **different return types**:

- `Integer.parseInt("42")` returns a **primitive `int`**.
- `Double.parseDouble("3.5")` returns a **primitive `double`**.
- `Integer.valueOf("42")` returns a **wrapper object `Integer`**.
- `Double.valueOf("3.5")` returns a **wrapper object `Double`**.

There is no universal `valueOf()` method shared across all classes with the same return type. **The class name before the dot determines the method and result type**: `Integer.valueOf(...)` returns `Integer`, `Long.valueOf(...)` returns `Long`, and `String.valueOf(...)` returns `String`.

## 1. Return Type Comparison Table

| Java Call | Argument | Declared Return Type | Illustrative Value |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | `String` | `int` | 42 |
| `Integer.valueOf("42")` | `String` | `Integer` | 42 |
| `Integer.valueOf(42)` | `int` | `Integer` | 42 |
| `Double.parseDouble("3.5")` | `String` | `double` | 3.5 |
| `Double.valueOf("3.5")` | `String` | `Double` | 3.5 |
| `Double.valueOf(3.5)` | `double` | `Double` | 3.5 |
| `Long.parseLong("9000000000")` | `String` | `long` | 9000000000 |
| `Long.valueOf("9000000000")` | `String` | `Long` | 9000000000 |
| `Boolean.parseBoolean("true")` | `String` | `boolean` | true |
| `Boolean.valueOf("true")` | `String` | `Boolean` | true |
| `String.valueOf(42)` | `int` | `String` | `"42"` |

`parseInt` and `parseDouble` belong to **different classes**. There is no `Integer.parseDouble` or `Double.parseInt`. The name `valueOf` is **overloaded** within each class, which does not mean every `valueOf` does the same thing.

### Data Flow Diagram

~~~text
"42" : String
  ├── Integer.parseInt("42") ──────> 42 : int
  └── Integer.valueOf("42") ───────> Integer holding value 42

"3.5" : String
  ├── Double.parseDouble("3.5") ───> 3.5 : double
  └── Double.valueOf("3.5") ───────> Double holding value 3.5

42 : int
  └── String.valueOf(42) ──────────> "42" : String
~~~

## 2. Standalone Runnable Java 17+ Program

Create the file **`ParsingReturnTypesDemo.java`** with the following content:

~~~java
public class ParsingReturnTypesDemo {
    static String typeOf(int ignored) {
        return "int";
    }

    static String typeOf(Integer ignored) {
        return "Integer";
    }

    static String typeOf(double ignored) {
        return "double";
    }

    static String typeOf(Double ignored) {
        return "Double";
    }

    public static void main(String[] args) {
        String wholeText = "42";
        String decimalText = "3.5";

        int primitiveInt = Integer.parseInt(wholeText);
        Integer boxedInt = Integer.valueOf(wholeText);
        double primitiveDouble = Double.parseDouble(decimalText);
        Double boxedDouble = Double.valueOf(decimalText);

        System.out.println("parseIntType=" + typeOf(primitiveInt));
        System.out.println("valueOfIntType=" + typeOf(boxedInt));
        System.out.println("parseDoubleType=" + typeOf(primitiveDouble));
        System.out.println("valueOfDoubleType=" + typeOf(boxedDouble));

        System.out.println("intValue=" + primitiveInt);
        System.out.println("doubleValue=" + primitiveDouble);
        System.out.println("wrapperIntPlusOne=" + (boxedInt + 1));
        System.out.println("wrapperDoublePlusHalf="
                + (boxedDouble + 0.5));

        Integer boxedByAssignment = Integer.parseInt("7");
        int unboxedByAssignment = Integer.valueOf("8");
        System.out.println("boxedAssignment=" + boxedByAssignment);
        System.out.println("unboxedAssignment=" + unboxedByAssignment);

        int hexPrimitive = Integer.parseInt("FF", 16);
        Integer hexWrapper = Integer.valueOf("FF", 16);
        System.out.println("hexPrimitive=" + hexPrimitive);
        System.out.println("hexWrapper=" + hexWrapper);

        long bigPrimitive = Long.parseLong("9000000000");
        Long bigWrapper = Long.valueOf("9000000000");
        System.out.println("longPrimitive=" + bigPrimitive);
        System.out.println("longWrapper=" + bigWrapper);

        boolean flagPrimitive = Boolean.parseBoolean("TrUe");
        Boolean flagWrapper = Boolean.valueOf("true");
        System.out.println("booleanPrimitive=" + flagPrimitive);
        System.out.println("booleanWrapper=" + flagWrapper);
        System.out.println("booleanUnknown="
                + Boolean.parseBoolean("yes"));

        String backToText = String.valueOf(primitiveInt);
        System.out.println("stringType=" + backToText.getClass().getSimpleName());
        System.out.println("stringValue=" + backToText);

        System.out.println("scientific="
                + Double.parseDouble("1e3"));
        System.out.println("nanAccepted="
                + Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("infinityAccepted="
                + Double.isInfinite(Double.parseDouble("Infinity")));

        try {
            Integer.parseInt("42.0");
        } catch (NumberFormatException ex) {
            System.out.println("invalidInteger=NumberFormatException");
        }

        try {
            Double.parseDouble("not-a-number");
        } catch (NumberFormatException ex) {
            System.out.println("invalidDouble=NumberFormatException");
        }

        try {
            Integer.parseInt("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("integerOverflow=NumberFormatException");
        }

        try {
            Integer.parseInt(" 42 ");
        } catch (NumberFormatException ex) {
            System.out.println("integerSpaces=NumberFormatException");
        }

        System.out.println("strippedInteger="
                + Integer.parseInt(" 42 ".strip()));

        Integer missing = null;
        System.out.println("wrapperMissing=" + (missing == null));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file and run with **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ParsingReturnTypesDemo.java
java ParsingReturnTypesDemo
~~~

**Exact expected output of `java ParsingReturnTypesDemo`** (excluding JDK version output):

~~~text
parseIntType=int
valueOfIntType=Integer
parseDoubleType=double
valueOfDoubleType=Double
intValue=42
doubleValue=3.5
wrapperIntPlusOne=43
wrapperDoublePlusHalf=4.0
boxedAssignment=7
unboxedAssignment=8
hexPrimitive=255
hexWrapper=255
longPrimitive=9000000000
longWrapper=9000000000
booleanPrimitive=true
booleanWrapper=true
booleanUnknown=false
stringType=String
stringValue=42
scientific=1000.0
nanAccepted=true
infinityAccepted=true
invalidInteger=NumberFormatException
invalidDouble=NumberFormatException
integerOverflow=NumberFormatException
integerSpaces=NumberFormatException
strippedInteger=42
wrapperMissing=true
~~~

The `typeOf(...)` methods are **overloaded** with parameters `int`, `Integer`, `double`, and `Double` to prove which input type the compiler selects. This demonstrates the **static type** of the expression, rather than relying on `getClass()` on primitives (primitives do not have a `getClass()` method).

## 3. `parseInt()`: Returns `int`, Validates Integer Strings

~~~java
int amount = Integer.parseInt("42");
int negative = Integer.parseInt("-15");
int hex = Integer.parseInt("FF", 16);
~~~

`Integer.parseInt(String)` uses base 10. The overload `Integer.parseInt(String, int radix)` lets you specify a radix from 2 to 36:

| Code | Result | Notes |
| --- | ---: | --- |
| `Integer.parseInt("1010", 2)` | 10 | Binary |
| `Integer.parseInt("17", 8)` | 15 | Octal |
| `Integer.parseInt("42")` | 42 | Decimal |
| `Integer.parseInt("FF", 16)` | 255 | Hexadecimal |
| `Integer.parseInt("-10")` | −10 | Negative number |
| `Integer.parseInt("+10")` | 10 | Valid plus sign |

If the string is not a valid integer representation in the chosen radix, the value exceeds the `int` range, or the argument is invalid, the method throws `NumberFormatException`. For example, `"42.0"` is not integer syntax, and `"2147483648"` exceeds `Integer.MAX_VALUE`.

`"0xFF"` is **not** automatically stripped of the `0x` prefix by `Integer.parseInt(..., 16)`. To parse `"FF"` with radix 16, pass only the digit portion. The `Integer.decode("0xFF")` API is a different mechanism with its own prefix-handling rules.

## 4. `parseDouble()`: Returns `double`

~~~java
double a = Double.parseDouble("3.5");
double b = Double.parseDouble("1e3");  // 1000.0.
double special = Double.parseDouble("NaN");
~~~

`Double.parseDouble` accepts Java's `double` string representation for valid strings; besides decimal numbers, it can accept scientific notation such as `1e3` and special values `NaN` and `Infinity`. Therefore, **successful parsing does not mean the data is a finite number**.

If business rules require a finite number:

~~~java
double rate = Double.parseDouble("1e3");
if (!Double.isFinite(rate)) {
    throw new IllegalArgumentException("Must be finite");
}
~~~

If the string is invalid, such as `"not-a-number"`, the method throws `NumberFormatException`. Note that `double` is an IEEE 754 binary floating-point number, so decimal values like `0.1` are often not represented with exact decimal precision. For currency requiring decimal precision, consider `BigDecimal` and explicit rounding rules rather than relying solely on `double`.

## 5. `valueOf()`: Result Depends on Class and Overload

### `Integer.valueOf`

~~~java
Integer fromText = Integer.valueOf("42");
Integer fromPrimitive = Integer.valueOf(42);
Integer fromHex = Integer.valueOf("FF", 16);
~~~

All three expressions above have type **`Integer`**. Some small values may use cached wrapper objects. Therefore, **do not use `==` between two wrappers to check numeric equality**; use `equals()` or `Objects.equals()` when null is possible.

### `Double.valueOf`

~~~java
Double fromText = Double.valueOf("3.5");
Double fromPrimitive = Double.valueOf(3.5);
~~~

Both return type **`Double`**. Unlike `Double.parseDouble`, the declared return type is a wrapper, not a primitive.

### `String.valueOf` Has a Completely Different Function

~~~java
String text = String.valueOf(42);     // "42".
String flagText = String.valueOf(true); // "true".
~~~

`String.valueOf(...)` returns **`String`**, converting a value to its text representation. It does not parse a string into a number. Saying "`valueOf` always returns a wrapper" is false because you must also identify the class defining the method.

### `Boolean` Also Has `parseBoolean` and `valueOf`

~~~java
boolean primitive = Boolean.parseBoolean("true");
Boolean wrapper = Boolean.valueOf("true");
~~~

`Boolean.parseBoolean` returns `true` only when the string equals `"true"` case-insensitively; other strings such as `"yes"` return `false` instead of throwing `NumberFormatException`. If you need to reject inputs other than `true`/`false`, you must perform **separate validation**.

## 6. Boxing and Unboxing Do Not Change a Method's Return Type

~~~java
Integer boxed = Integer.parseInt("42"); // parseInt RETURNS int, then boxing.
int primitive = Integer.valueOf("42"); // valueOf RETURNS Integer, then unboxing.
~~~

These two statements compile, but they do **not** prove that `parseInt` returns a wrapper or that `valueOf` returns a primitive. The actual return type is declared by the method; Java can automatically convert in the **assignment context**.

| Right-Hand Expression | Method Return Type | Left-Hand Variable Type | Additional Conversion |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | `int` | `int` | None |
| `Integer.parseInt("42")` | `int` | `Integer` | Boxing |
| `Integer.valueOf("42")` | `Integer` | `Integer` | None |
| `Integer.valueOf("42")` | `Integer` | `int` | Unboxing |
| `Double.parseDouble("3.5")` | `double` | `Double` | Boxing |
| `Double.valueOf("3.5")` | `Double` | `double` | Unboxing |

**`null` trap:** if an `Integer` or `Double` variable is null and gets unboxed, Java throws `NullPointerException`. Calling a parsing method on an invalid input string is a different kind of problem, typically `NumberFormatException`.

## 7. Cleaning and Validating Input

`Integer.parseInt(" 42 ")` throws `NumberFormatException` because leading/trailing spaces are not part of integer syntax. If the application allows surrounding whitespace, normalize it proactively:

~~~java
String raw = " 42 ";
int parsed = Integer.parseInt(raw.strip()); // 42.
~~~

**Never assume all whitespace is harmless** in formal data: the application must decide whether to strip it or report a format error.

A simple helper to handle a required integer input:

~~~java
static int parseRequiredInt(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Value is required");
    }
    return Integer.parseInt(raw.strip());
}
~~~

- `null` and blank strings are reported as missing.
- Valid strings after normalization are parsed into `int`.
- Malformed strings or values exceeding the `int` range throw `NumberFormatException`. You can catch this exception at the user-facing layer to return a clear message, rather than swallowing the error and defaulting to 0 when that is disallowed.

### Distinguishing Parsing from Casting

~~~java
String text = "42";
// int bad = (int) text;  // COMPILE ERROR.
int value = Integer.parseInt(text);
~~~

Numeric casts do not read digits inside a `String`. Parsing a string and casting a number are two different operations.

## 8. Which API Should You Choose in Java?

| Need | Choice | Reason |
| --- | --- | --- |
| Need primitive integer for calculation | `Integer.parseInt(raw)` | Directly returns `int` |
| Need `Integer` for API/generics | `Integer.valueOf(raw)` | Returns wrapper |
| Need primitive floating-point | `Double.parseDouble(raw)` | Returns `double` |
| Need floating-point wrapper | `Double.valueOf(raw)` | Returns `Double` |
| Need to read a long integer | `Long.parseLong(raw)` | Returns `long` |
| Need long integer wrapper | `Long.valueOf(raw)` | Returns `Long` |
| Need to convert primitive to text | `String.valueOf(value)` | Returns `String` |
| Need base-16 control | `Integer.parseInt(raw, 16)` | `int` result, hex digit string |
| Need exact monetary values | `new BigDecimal(raw)` with designed scale/rounding | Avoids binary floating-point errors of `double` |

Note that `valueOf` on a wrapper **does not necessarily create a new object every time**. The API may cache immutable objects. Therefore, do not equate "return type is a wrapper" with "always allocates a new object on every call".

## 9. Common Mistakes

| Misconception | Correct Fact |
| --- | --- |
| "`Integer.parseInt` returns `Integer`." | Returns **`int`**; may be boxed when assigned to `Integer` |
| "`Integer.valueOf` returns `int`." | Returns **`Integer`**; may be unboxed when assigned to `int` |
| "Every `valueOf` returns a wrapper." | `String.valueOf` returns **`String`** |
| "`Integer.parseInt("42.0")` gives 42." | Throws `NumberFormatException` |
| "`Double.parseDouble` only reads finite numbers." | Can accept `NaN` or `Infinity` |
| "`parseInt(" 42 ")` always trims automatically." | No; normalize according to contract |
| "`Integer.parseInt` automatically reads `0xFF` in base 16." | Must handle prefix/syntax or use an appropriate API |
| "Assigning to `Integer` changes `parseInt`'s return type." | No; that is **boxing after the method call** |
| "Two `valueOf` results with equal numbers mean `==` must be true." | No; compare wrapper **values** using `equals` |

## 10. Self-Check Exercises

1. **Result types:** What types do `Integer.parseInt("7")` and `Integer.valueOf("7")` return respectively?  
   *Answer:* `int` and `Integer`.
2. **Floating-point:** How does `Double.parseDouble("2.5")` differ from `Double.valueOf("2.5")` in return type?  
   *Answer:* `double` and `Double`.
3. **Overload:** What values and types do `Integer.parseInt("FF", 16)` and `Integer.valueOf("FF", 16)` produce?  
   *Answer:* Both have value 255, with types `int` and `Integer` respectively.
4. **Assignment context:** Does `Integer n = Integer.parseInt("8");` compile?  
   *Answer:* Yes, thanks to `int -> Integer` boxing.
5. **Invalid data:** Is `Integer.parseInt("8.0")` valid?  
   *Answer:* No, it throws `NumberFormatException`.
6. **Boolean:** Does `Boolean.parseBoolean("YES")` throw an exception or return false?  
   *Answer:* It returns `false`. To reject `"YES"`, you must validate manually.
7. **NaN:** Does `Double.parseDouble("NaN")` fail or succeed?  
   *Answer:* It succeeds, returning `double` NaN; `Double.isNaN(...)` returns true.

## Memory Checklist

- [ ] `parseInt` / `parseLong` / `parseDouble` return the corresponding **primitive**.
- [ ] Wrapper `valueOf` returns the corresponding **wrapper object**.
- [ ] `String.valueOf` returns a **String**, not a numeric wrapper.
- [ ] Boxing/unboxing happens **after** the method call if required by context.
- [ ] Distinguish syntax, value range, radix, and exceptions during parsing.
- [ ] Successful `double` parsing does not guarantee a finite or exact value.
- [ ] Normalize whitespace and validate null according to application requirements.
- [ ] Do not use casts in place of parsing, and do not use `==` to compare wrapper values.

**Conclusion:** When reading `"42"`, choose the API based on **the result type you need**: `Integer.parseInt` for `int`, `Integer.valueOf` for `Integer`. Similarly, `Double.parseDouble` for `double` and `Double.valueOf` for `Double`. The same name `valueOf` on another class can return a completely different type, so always check **the declaring class + method signature + boxing/unboxing context**.