# `NumberFormatException` on Invalid Strings in Java

> **Java core — language-basics / Primitive Wrappers**  
> **Environment:** JDK 17+; no external libraries required.  
> **Objective:** Identify why converting a string to a number can throw `NumberFormatException`, distinguish malformed format from out-of-range values, properly apply `Integer.parseInt`/`Long.parseLong`/`Double.parseDouble`, and handle invalid input values at program boundaries.

## 1. A String Does Not Automatically Become a Number

`String` holds text, whereas `int`, `long`, and `double` store numeric values. To parse text into a number, Java provides conversion methods on the wrapper classes (*wrappers*):

~~~java
int quantity = Integer.parseInt("42");  // 42
long count = Long.parseLong("3000000000"); // 3000000000L
double rate = Double.parseDouble("3.14"); // 3.14
~~~

If the string cannot be parsed according to the syntax or value range required by the method, Java throws **`java.lang.NumberFormatException`** (*NFE*). This is a subclass of `IllegalArgumentException`.

~~~java
// int value = Integer.parseInt("12x"); // If executed: NumberFormatException.
~~~

**Key point:** `"12x"` is still a valid `String`. The error occurs when **attempting to interpret that content as an integer**, not when creating the string.

## 2. Input Categories That Cause `NumberFormatException`

| Data and Conversion Call | Result | Cause |
| --- | --- | --- |
| `Integer.parseInt("42")` | `42` | Valid decimal string |
| `Integer.parseInt("-7")` | `-7` | Valid minus sign |
| `Integer.parseInt("+8")` | `8` | Valid leading plus sign |
| `Integer.parseInt("007")` | `7` | Leading zeros are still decimal by default |
| `Integer.parseInt(" 42 ")` | NFE | Does not automatically strip whitespace |
| `Integer.parseInt("")` | NFE | Empty string |
| `Integer.parseInt("12x")` | NFE | Contains invalid character in base 10 |
| `Integer.parseInt("3.14")` | NFE | Decimal number with fractional part is not `int` syntax |
| `Integer.parseInt("1_000")` | NFE | Underscore is valid in **Java literals**, not input strings for `parseInt` |
| `Integer.parseInt("2147483648")` | NFE | Exceeds `Integer.MAX_VALUE` of 2147483647 |
| `Integer.parseInt(null)` | NFE | No string to parse |
| `Byte.parseByte("128")` | NFE | Value 128 exceeds `byte` limit of 127 |

`Integer.parseInt` defaults to **base 10**. It does not understand literal syntax like `0xFF` or underscores used in source code; do not confuse the format of a **Java source literal** with the format of a **runtime input string**.

Parsing methods do not handle all business constraints automatically: `"-1"` can be parsed into `int` successfully, yet still be **invalid** if it represents an item quantity or network port that must be positive.

## 3. Radix: Valid Strings Depend on the Base

The `radix` parameter specifies the base to use for `Integer.parseInt(String, int)`:

~~~java
int hex = Integer.parseInt("FF", 16);   // 255
int binary = Integer.parseInt("101", 2); // 5
int decimal = Integer.parseInt("101", 10); // 101

// Integer.parseInt("FF");     // NFE: F is not a decimal digit.
// Integer.parseInt("102", 2);  // NFE: 2 does not belong to base 2.
~~~

`Integer.parseInt("FF", 16)` requires specifying radix 16; it is not a numeric type cast. Valid radices for `Integer.parseInt` range from `Character.MIN_RADIX` (2) to `Character.MAX_RADIX` (36); an invalid radix also results in `NumberFormatException`.

If the input has a `0x` prefix, the `Integer.decode(...)` API has its own rules for recognizing prefixes. Do not automatically replace `parseInt` with `decode` if the input format must be strictly controlled.

## 4. Distinguishing Syntax, Range, and Number Type

Parsing methods have different formats/ranges:

| API | Valid Example | Important Notes |
| --- | --- | --- |
| `Byte.parseByte` | `"127"` | Exceeding `byte` range causes NFE |
| `Short.parseShort` | `"-30000"` | Exceeding `short` range causes NFE |
| `Integer.parseInt` | `"2147483647"` | Decimal numbers with fractional parts are invalid |
| `Long.parseLong` | `"2147483648"` | Larger than `int` yet still fits in `long` |
| `Double.parseDouble` | `"3.14"` or `"1e3"` | Supports floating-point, exponent notation, and special tokens |
| `Float.parseFloat` | `"2.5"` | Follows floating-point parsing rules, unlike `parseInt` |

**Important:** `Double.parseDouble("NaN")` returns the value **`Double.NaN`**, without throwing NFE. A valid string according to `double` rules is **not necessarily a finite value** either: for instance, an overly large input can become infinity. When business rules only permit finite floating-point numbers, additionally check `Double.isFinite(value)` after parsing.

For monetary amounts requiring precision to exact decimal digits, consider `BigDecimal` created from a validated string along with business scale/rounding rules; do not casually pass money through `double` and assume exact precision.

## 5. Runnable Java 17+ Program

Create the file **NumberFormatDemo.java**:

~~~java
public final class NumberFormatDemo {
    private static void checkInt(String label, String text) {
        try {
            System.out.println(label + "=" + Integer.parseInt(text));
        } catch (NumberFormatException ex) {
            System.out.println(label + "=NumberFormatException");
        }
    }

    private static int parsePort(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("port required");
        }

        int port;
        try {
            port = Integer.parseInt(input.strip());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "port must be decimal integer", ex);
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port outside 1..65535");
        }
        return port;
    }

    private static void checkPort(String label, String input) {
        try {
            System.out.println(label + "=" + parsePort(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(label + "=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        checkInt("plain", "42");
        checkInt("negative", "-7");
        checkInt("leadingPlus", "+8");
        checkInt("leadingZero", "007");
        checkInt("spaces", " 42 ");
        checkInt("decimal", "3.14");
        checkInt("empty", "");
        checkInt("nonDigit", "12x");
        checkInt("overflow", "2147483648");
        checkInt("underscore", "1_000");
        checkInt("nullInput", null);

        System.out.println("hexFF=" + Integer.parseInt("FF", 16));
        try {
            Integer.parseInt("102", 2);
        } catch (NumberFormatException ex) {
            System.out.println("binaryInvalid=NumberFormatException");
        }

        System.out.println("longLarge=" + Long.parseLong("2147483648"));
        try {
            Byte.parseByte("128");
        } catch (NumberFormatException ex) {
            System.out.println("byteOverflow=NumberFormatException");
        }

        System.out.println("doubleDecimal=" + Double.parseDouble("3.14"));
        System.out.println("doubleNaN=" + Double.parseDouble("NaN"));
        try {
            Double.parseDouble("1.2.3");
        } catch (NumberFormatException ex) {
            System.out.println("doubleInvalid=NumberFormatException");
        }

        checkPort("validPort", "8080");
        checkPort("spacesPort", " 8080 ");
        checkPort("badPort", "abc");
        checkPort("tooLargePort", "65536");
        checkPort("missingPort", null);
    }
}
~~~

Open a terminal in the directory containing the file, compile, and run (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 NumberFormatDemo.java
java NumberFormatDemo
~~~

**Exact expected output:**

~~~text
plain=42
negative=-7
leadingPlus=8
leadingZero=7
spaces=NumberFormatException
decimal=NumberFormatException
empty=NumberFormatException
nonDigit=NumberFormatException
overflow=NumberFormatException
underscore=NumberFormatException
nullInput=NumberFormatException
hexFF=255
binaryInvalid=NumberFormatException
longLarge=2147483648
byteOverflow=NumberFormatException
doubleDecimal=3.14
doubleNaN=NaN
doubleInvalid=NumberFormatException
validPort=8080
spacesPort=8080
badPort=port must be decimal integer
tooLargePort=port outside 1..65535
missingPort=port required
~~~

The program **does not depend on the JDK's default error text**: for the invalid format examples, it only prints the exception type name; in `parsePort`, the messages are defined by our own code so they are easy to test.

## 6. Handling Errors Properly at Input Boundaries

In `parsePort`, the steps are intentional:

1. **Check for missing data:** `null` or an all-whitespace string → `"port required"`. Avoid accidentally treating missing data as 0.
2. **Normalize input when allowed:** `strip()` removes leading/trailing whitespace, but only because this example's contract **allows** whitespace. If a strict format does not accept whitespace, omit this step.
3. **Parse and catch errors in the right place:** `Integer.parseInt` handles integer syntax. `NumberFormatException` is translated into an input error with a business message, preserving `cause` for diagnostics.
4. **Validate business range after parsing:** the integer `65536` has valid syntax and fits in `int`, yet is invalid as a network port; `"-1"` is similar.
5. **Do not turn every error into 0:** a malformed string usually needs to be reported to the user or upstream caller, not silently fed into calculations.

The `try/catch` here wraps **the parsing of untrusted data**, rather than catching around an overly large application block or catching generic `Exception` and ignoring it. Internal APIs with a different contract may let NFE propagate to the caller to handle, instead of always wrapping it in a new `IllegalArgumentException`.

## 7. Why Should You Not Rely on `ex.getMessage()` for Control Flow?

`NumberFormatException` indicates a number-parsing failure, but **the exact wording of its message** is not a stable business format for parsers or UIs to depend on. Avoid writing:

~~~java
// Not recommended:
// if (ex.getMessage().contains("For input string")) { ... }
~~~

Instead, catch the exact **exception type**, check the source data field, and build a clear message yourself such as `"quantity must be a whole number"`. You can log the exception/cause according to system policy, but never expose raw stack trace details to end users.

**Do not confuse with other errors:**

- `Integer.parseInt("12x")` → **`NumberFormatException`** because the text cannot be parsed.
- `int x = someIntegerWrapper;` when the wrapper is `null` → **`NullPointerException`** from unboxing, not a string syntax error.
- `Integer.valueOf(12)` creates/retrieves a wrapper from an integer value, not a parser for a malformed text string.
- `Integer.valueOf("12x")` can also throw **`NumberFormatException`** because it must parse the string as an integer.

## 8. Practice Exercises

**Exercise 1:** Predict the results of `Integer.parseInt("+15")`, `Integer.parseInt("015")`, `Integer.parseInt("15 ")`, `Integer.parseInt("15.0")` and explain why the source string is a valid `String` yet the parser can still reject it.

**Exercise 2:** Compare `Integer.parseInt("2147483648")` with `Long.parseLong("2147483648")`. What changes when choosing a different wrapper?

**Exercise 3:** Use `Integer.parseInt("101", 2)` and `Integer.parseInt("101", 10)`. Why can the same string turn into two different numbers?

**Exercise 4:** Write a method accepting a product quantity as a `String`. Reject null/blank, parse the integer, then reject negative quantities. Explain why these are two separate validation layers.

**Exercise 5:** Try `Double.parseDouble("NaN")` and `Double.parseDouble("1e309")`. Write a `Double.isFinite(result)` condition if the application requires finite measurements.

### Key Takeaways

**`NumberFormatException` signals that a string cannot be interpreted under the requested numeric type, radix, or bounds.** Check missing inputs and whitespace per contract; use the right `parseInt`/`parseLong`/`parseDouble`; catch NFE at untrusted data boundaries, then **validate business constraints next**. Do not rely on JDK error text and never silently replace all invalid inputs with 0.