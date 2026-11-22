# NumberFormatException and Input Data Conversion in Java

When reading data from forms, APIs, CSV files, the command line, or configuration, a program typically receives a **String** before converting it into an **int**, **long**, **double**, or **BigDecimal**. If the string does not have valid numeric syntax or cannot be represented in the target type, many Java APIs throw **java.lang.NumberFormatException**.

This is an **unchecked exception**, located in the inheritance chain **Throwable → Exception → RuntimeException → IllegalArgumentException → NumberFormatException**. The compiler does not require declaring **throws NumberFormatException** or using **try-catch**. However, untrusted input needs to be validated, reported, and logged clearly. A string that parses successfully is not necessarily guaranteed to satisfy business rules either.

This lesson covers integer and floating-point parsing syntax, numeric type ranges, radices, signs/whitespace, exact decimals, Unicode, locales, and how to place exception-handling boundaries. All complete programs run on Java 17+.

## 1. Understanding the Exception and API Contract

For example, **Integer.parseInt("abc")** throws NumberFormatException because the input characters do not form a valid integer. **Integer.parseInt("2147483648")** also throws the same exception even though the string consists solely of digits: the value exceeds **Integer.MAX_VALUE = 2147483647**.

Things to distinguish:

- **Syntax error:** empty string, invalid digits, or disallowed characters.
- **Range error:** integer value is greater than or less than the target type's range.
- **Business rule error:** parsing succeeds, but the value violates a rule, such as an age of 200 or a negative quantity.
- **Other conversion step error:** a valid long that cannot be converted exactly to an int using **Math.toIntExact**, in which case Java throws **ArithmeticException**, not NumberFormatException.

Because NumberFormatException inherits from IllegalArgumentException, a **catch (IllegalArgumentException ex)** block can catch it. If both catch blocks exist at the same level, **catch (NumberFormatException ex)** must be placed first; placing the parent class first shadows the subclass and causes a compilation error.

The message **ex.getMessage()** is not a stable business error code. It may contain the input string and vary across overloads/JDKs; you should not classify errors by comparing the exact full message from the JDK.

## 2. Syntax of Integer.parseInt(String)

In base 10, the parser accepts valid digits and an optional leading plus/minus sign, provided the value lies within the int range.

| Input | Result |
| --- | --- |
| "42" | int 42 |
| "+7" | int 7 |
| "-12" | int -12 |
| "0009" | int 9 |
| "" | NumberFormatException |
| " 42 " | NumberFormatException because whitespace is not trimmed automatically |
| "12.5" | NumberFormatException because this is not an integer |
| "1,000" | NumberFormatException because it contains a grouping separator |
| "1_000" | NumberFormatException; underscores in source numeric literals do not apply to runtime strings |
| "0xFF" | NumberFormatException with base-10 parseInt |
| "2147483648" | NumberFormatException because it overflows int |
| null | NumberFormatException |

A Java program can write the numeric literal **1_000**, but **Integer.parseInt("1_000")** does not understand that underscore syntax. Similarly, locale-specific decimal separators are not automatically recognized by integer parsers.

### Program 1: Successful and Failed Parsing

Save as **IntegerInputDemo.java**:

~~~java
public class IntegerInputDemo {
    static void inspect(String raw) {
        try {
            int value = Integer.parseInt(raw);
            System.out.println("ok=[" + raw + "]:" + value);
        } catch (NumberFormatException ex) {
            System.out.println("invalid=[" + raw + "]");
        }
    }

    public static void main(String[] args) {
        inspect("27");
        inspect("-4");
        inspect("+6");
        inspect("");
        inspect("2.5");
        inspect("2147483648");
        inspect(" 12 ");
    }
}
~~~

~~~bash
javac -encoding UTF-8 IntegerInputDemo.java
java IntegerInputDemo
~~~

Output:

~~~text
ok=[27]:27
ok=[-4]:-4
ok=[+6]:6
invalid=[]
invalid=[2.5]
invalid=[2147483648]
invalid=[ 12 ]
~~~

The program intentionally avoids printing the JDK message so stdout does not depend on the JDK version. When displaying errors to users, describe the input field and allowed format yourself.

## 3. Choosing a Method Based on the Target Numeric Type

| Requirement | API |
| --- | --- |
| 32-bit signed integer | **Integer.parseInt(text)**, returns primitive int |
| Integer object | **Integer.valueOf(text)**, returns wrapper Integer |
| 64-bit signed integer | **Long.parseLong(text)** |
| Arbitrary-precision integer | **new BigInteger(text)** |
| Integer with radix 2 to 36 | **Integer.parseInt(text, radix)** |
| String with radix prefix according to Java rules | **Integer.decode(text)** |
| 64-bit binary floating-point | **Double.parseDouble(text)** |
| 32-bit binary floating-point | **Float.parseFloat(text)** |
| Decimal value requiring exactness from string | **new BigDecimal(text)** |
| Locale-formatted numeric string | **NumberFormat** or **DecimalFormat** with an explicit Locale |

**Integer.valueOf("42")** yields the same numeric value as Integer.parseInt("42"), but returns a wrapper object. Do not use reference comparison **==** between two wrappers to check value equality; use the equals method or primitive values when appropriate.

Do not choose a numeric type solely based on string length. If the data is a postal code or an ID with leading zeros, converting it to an int can lose the original representation. Such fields should probably remain String if no arithmetic operations are performed.

## 4. Radix: parseInt(radix) and decode Are Not the Same

Integer.parseInt(text, radix) reads digits in base **2..36**. Meanwhile, Integer.decode accepts prefixed syntax such as **0x**, **#**, and applies octal rules when the string has a leading 0.

### Program 2: Radix Differences

Save as **RadixAndDecodeDemo.java**:

~~~java
public class RadixAndDecodeDemo {
    public static void main(String[] args) {
        System.out.println("binary=" + Integer.parseInt("101101", 2));
        System.out.println("hex=" + Integer.parseInt("7F", 16));
        System.out.println("negativeHex=" + Integer.parseInt("-20", 16));
        System.out.println("base36=" + Integer.parseInt("Z", 36));
        System.out.println("decimal010=" + Integer.parseInt("010"));
        System.out.println("decode010=" + Integer.decode("010"));
        System.out.println("decodeHex=" + Integer.decode("0x2A"));
        System.out.println("decodeHash=" + Integer.decode("#2A"));

        try {
            Integer.parseInt("0x2A");
        } catch (NumberFormatException ex) {
            System.out.println("prefixed=invalid");
        }
        try {
            Integer.parseInt("101", 1);
        } catch (NumberFormatException ex) {
            System.out.println("radix1=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RadixAndDecodeDemo.java
java RadixAndDecodeDemo
~~~

Output:

~~~text
binary=45
hex=127
negativeHex=-32
base36=35
decimal010=10
decode010=8
decodeHex=42
decodeHash=42
prefixed=invalid
radix1=invalid
~~~

When user data is decimal, avoid using decode indiscriminately: a value like **"010"** can be interpreted as octal 8 rather than decimal 10. Use parseInt(text, 10) when the contract strictly requires base 10.

## 5. Overflow: Parsing Errors vs. Narrowing Cast Errors

Java integer limits:

~~~text
int  : -2147483648 .. 2147483647
long : -9223372036854775808 .. 9223372036854775807
~~~

A string exceeding the int limit causes NumberFormatException in **Integer.parseInt**. However, after successfully parsing a long, if you want to convert it exactly to an int using **Math.toIntExact**, failure throws ArithmeticException.

### Program 3: Three Ways to Handle Integer Bounds

Save as **NumericBoundsDemo.java**:

~~~java
import java.math.BigInteger;

public class NumericBoundsDemo {
    public static void main(String[] args) {
        String large = "2147483648";
        System.out.println("long=" + Long.parseLong(large));
        System.out.println("big=" + new BigInteger(large));

        try {
            Integer.parseInt(large);
        } catch (NumberFormatException ex) {
            System.out.println("int=out-of-range");
        }

        try {
            Math.toIntExact(Long.parseLong(large));
        } catch (ArithmeticException ex) {
            System.out.println("narrowing=out-of-range");
        }

        String huge = "9223372036854775808";
        try {
            Long.parseLong(huge);
        } catch (NumberFormatException ex) {
            System.out.println("long=out-of-range");
        }
        System.out.println("bigHuge=" + new BigInteger(huge));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NumericBoundsDemo.java
java NumericBoundsDemo
~~~

Output:

~~~text
long=2147483648
big=2147483648
int=out-of-range
narrowing=out-of-range
long=out-of-range
bigHuge=9223372036854775808
~~~

Casting with **(int) someLong** can silently discard high bits without throwing an exception. To check accurately, use Math.toIntExact or validate the range before converting. BigInteger allows very large integers, but you still need to limit input length to avoid uncontrolled CPU/memory usage.

## 6. Double.parseDouble and Non-Finite Values

NumberFormatException is not thrown for all floating-point values that business logic might reject. Double.parseDouble supports scientific notation, NaN, Infinity, and can return Infinity for exponents that are too large.

For example:

- **Double.parseDouble("1.5e2")** → 150.0.
- **Double.parseDouble("NaN")** → NaN.
- **Double.parseDouble("Infinity")** → positive infinity.
- **Double.parseDouble("1e309")** → infinity on type double.
- **Double.parseDouble("1,5")** → NumberFormatException.
- **Double.parseDouble("1_000")** → NumberFormatException.

Unlike Integer.parseInt, Double.parseDouble accepts some leading/trailing whitespace according to a parser contract matching String.trim(). Do not assume that every number-parsing API shares the same whitespace policy.

### Program 4: Separating Invalid Syntax from Non-Finite Values

Save as **FloatingInputDemo.java**:

~~~java
public class FloatingInputDemo {
    static void inspect(String raw) {
        try {
            double value = Double.parseDouble(raw);
            if (!Double.isFinite(value)) {
                System.out.println("not-finite=[" + raw + "]");
            } else {
                System.out.println("finite=[" + raw + "]:" + value);
            }
        } catch (NumberFormatException ex) {
            System.out.println("invalid=[" + raw + "]");
        }
    }

    public static void main(String[] args) {
        inspect("12.5");
        inspect("1.5e2");
        inspect("NaN");
        inspect("Infinity");
        inspect("1e309");
        inspect("1,5");
        inspect("1_000");
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloatingInputDemo.java
java FloatingInputDemo
~~~

Output:

~~~text
finite=[12.5]:12.5
finite=[1.5e2]:150.0
not-finite=[NaN]
not-finite=[Infinity]
not-finite=[1e309]
invalid=[1,5]
invalid=[1_000]
~~~

For a field requiring a finite number, successful parsing is only the first step: continue by checking **Double.isFinite(value)** before evaluating min/max bounds and business rules.

## 7. BigDecimal(String) for Decimals Requiring Exactness

Double uses binary representation, so **0.1 + 0.2** in double is generally not equal to the exact decimal value 0.3. When the source data is a monetary string, **new BigDecimal(String)** is usually more appropriate.

### Program 5: Decimal Numbers and Conversion Errors

Save as **DecimalMoneyDemo.java**:

~~~java
import java.math.BigDecimal;

public class DecimalMoneyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("exact=" + a.add(b));
        System.out.println("doubleSum=" + (0.1 + 0.2));
        System.out.println("scientific="
                + new BigDecimal("1.25e2").toPlainString());

        try {
            new BigDecimal("1,25");
        } catch (NumberFormatException ex) {
            System.out.println("comma=invalid");
        }

        try {
            new BigDecimal("NaN");
        } catch (NumberFormatException ex) {
            System.out.println("nan=invalid");
        }

        try {
            new BigDecimal("12.5").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("fraction=not-an-exact-int");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DecimalMoneyDemo.java
java DecimalMoneyDemo
~~~

Output:

~~~text
exact=0.3
doubleSum=0.30000000000000004
scientific=125
comma=invalid
nan=invalid
fraction=not-an-exact-int
~~~

The decimal value from the string is preserved by BigDecimal. BigDecimal does not have NaN/Infinity values like double; invalid strings can produce NumberFormatException. Meanwhile, **intValueExact()** can throw ArithmeticException if there is a fractional part or if the value exceeds the int range.

Avoid using new BigDecimal(someDouble) just to try to recover the original text value: the double may already carry binary rounding error. If you receive a decimal string, prefer parsing directly from the string.

## 8. Layered Input Validation, Not Just Try-to-Parse

An age field might have the following contract:

1. Required input, non-null and non-empty.
2. Allow stripping leading and trailing whitespace using String.strip().
3. Accept only ASCII digits 0..9, disallowing plus/minus signs.
4. Value must be within the int range.
5. Age must not exceed 150.

~~~text
Raw input
  |
  +-- null / empty? -> "age required"
  |
  v
String.strip()
  |
  +-- not [0-9]+? -> "age must contain ASCII digits"
  |
  v
Integer.parseInt()
  |
  +-- NFE? -> "age out of integer range"
  |
  v
age <= 150?
  |
  +-- no -> "age must be <= 150"
  |
  v
Valid age
~~~

### Program 6: Contextual Input Errors Preserving the Cause

Save as **ValidatedAgeDemo.java**:

~~~java
public class ValidatedAgeDemo {
    static int parseAge(String raw) {
        if (raw == null || raw.strip().isEmpty()) {
            throw new IllegalArgumentException("age required");
        }

        String text = raw.strip();
        if (!text.matches("[0-9]+")) {
            throw new IllegalArgumentException(
                    "age must contain ASCII digits");
        }

        final int age;
        try {
            age = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "age out of integer range", ex);
        }

        if (age > 150) {
            throw new IllegalArgumentException(
                    "age must be <= 150");
        }
        return age;
    }

    static void inspect(String raw) {
        try {
            System.out.println("age=" + parseAge(raw));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        inspect(" 21 ");
        inspect("-1");
        inspect("200");
        inspect("2147483648");
        inspect("");
        inspect(null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidatedAgeDemo.java
java ValidatedAgeDemo
~~~

Output:

~~~text
age=21
invalid=age must contain ASCII digits
invalid=age must be <= 150
invalid=age out of integer range
invalid=age required
invalid=age required
~~~

Here, **"200"** parses validly but is rejected due to the age policy; **"-1"** is rejected at the grammar step; **"2147483648"** passes the grammar step but fails the int range check. When wrapping NumberFormatException into IllegalArgumentException with the **cause** parameter, the original technical information remains traceable at the logging layer.

Another field might allow negative signs or Unicode digits. Therefore, do not mechanically apply the regex policy from the age example to all data types.

## 9. Unicode Digits and Differences from ASCII

Integer.parseInt uses Character.digit to recognize digits for a given radix, not strictly ASCII characters in all cases. Conversely, the regex **[0-9]+** in the age example only allows ASCII.

### Program 7: Arabic-Indic Digits

Save as **UnicodeDigitDemo.java**:

~~~java
public class UnicodeDigitDemo {
    public static void main(String[] args) {
        String arabicIndic = "\u0661\u0662";
        System.out.println("parsed=" + Integer.parseInt(arabicIndic));
        System.out.println("asciiOnly="
                + arabicIndic.matches("[0-9]+"));
        System.out.println("digit=" + Character.digit('\u0661', 10));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeDigitDemo.java
java UnicodeDigitDemo
~~~

Output:

~~~text
parsed=12
asciiOnly=false
digit=1
~~~

The Unicode characters U+0661 and U+0662 are Arabic-Indic digits corresponding to 1 and 2. If a system communicates with a service that only accepts ASCII, explicit validation is needed; if multilingual input is supported, the Unicode policy should be documented and tested. A typographic minus sign is not necessarily parsed as an ASCII minus sign.

## 10. Batch Processing: Returning Status per Item

If CSV rows are independent, one malformed item does not necessarily have to halt the entire batch. You can convert each item into a value representing the result instead of throwing an exception that breaks the loop.

### Program 8: A Record Carrying Either Result or Error

Save as **BatchNumberParsingDemo.java**:

~~~java
import java.util.List;

public class BatchNumberParsingDemo {
    record ParseResult(String raw, Integer value, String error) {
        boolean success() {
            return error == null;
        }
    }

    static ParseResult parseOne(String raw) {
        try {
            return new ParseResult(raw, Integer.parseInt(raw), null);
        } catch (NumberFormatException ex) {
            return new ParseResult(raw, null, "invalid integer");
        }
    }

    public static void main(String[] args) {
        for (String raw : List.of("10", "bad", "25", "2147483648")) {
            ParseResult result = parseOne(raw);
            if (result.success()) {
                System.out.println("ok=" + result.raw()
                        + ":" + result.value());
            } else {
                System.out.println("error=" + result.raw()
                        + ":" + result.error());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BatchNumberParsingDemo.java
java BatchNumberParsingDemo
~~~

Output:

~~~text
ok=10:10
error=bad:invalid integer
ok=25:25
error=2147483648:invalid integer
~~~

Records are a standard feature in Java 17. The example illustrates collecting errors per element; in production, you should enforce invariants such as **success or failure, never both at the same time**. If a task requires atomicity, continuing after an error may be inappropriate; this choice belongs to the business contract.

## 11. Command-Line Input and Checking Argument Count

When accessing **args[0]**, another error can occur **before parsing**: if the program runs without arguments, array access throws ArrayIndexOutOfBoundsException. Therefore, you must check **args.length**.

Save as **CommandLineNumberDemo.java**:

~~~java
public class CommandLineNumberDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("usage: java CommandLineNumberDemo <count>");
            return;
        }

        final int count;
        try {
            count = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.out.println("count must be an integer");
            return;
        }

        if (count < 0) {
            System.out.println("count must be non-negative");
            return;
        }

        System.out.println("count=" + count);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CommandLineNumberDemo.java
java CommandLineNumberDemo 12
java CommandLineNumberDemo abc
java CommandLineNumberDemo -2
~~~

Output of the three runs:

~~~text
count=12
count must be an integer
count must be non-negative
~~~

When no arguments are provided, the program prints the usage line. A real-world CLI might need a non-zero exit status, but System.exit should not be used in an example meant solely to explain parsing mechanics.

## 12. Locale-Specific Decimal Separators and Full-String Parsing

Integer.parseInt and Double.parseDouble do not automatically parse formats for every locale. For instance, the string **"1.234,5"** means 1234.5 in Locale.GERMANY, but is invalid when passed directly to Double.parseDouble.

You can use **NumberFormat.getNumberInstance(Locale.GERMANY)**. Note: **NumberFormat.parse(String, ParsePosition)** can successfully parse a prefix and stop before an invalid suffix. If the input must match the entire string, check the ending position.

Save as **LocaleNumberDemo.java**:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberDemo {
    static Number parseAll(String text, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(text, position);

        if (value == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("invalid localized number");
        }
        return value;
    }

    public static void main(String[] args) {
        Number value = parseAll("1.234,5", Locale.GERMANY);
        System.out.println("value=" + value.doubleValue());

        try {
            parseAll("1.234,5tail", Locale.GERMANY);
        } catch (IllegalArgumentException ex) {
            System.out.println("suffix=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleNumberDemo.java
java LocaleNumberDemo
~~~

Output with standard locale data:

~~~text
value=1234.5
suffix=invalid
~~~

In the example, IllegalArgumentException is **created by parseAll itself** when the string is not fully consumed; do not assume NumberFormat.parse always throws NumberFormatException like Integer.parseInt. For money requiring exactness, you can configure DecimalFormat to parse into BigDecimal and validate scale/bounds.

## 13. Placing catch at the Right Boundary and Preserving the Root Cause

The following snippet has a problem with its error-catching scope:

~~~java
try {
    int id = Integer.parseInt(input);
    process(id);
} catch (NumberFormatException ex) {
    showInvalidInput();
}
~~~

This is a **non-standalone illustrative snippet**, assuming functions/variables are already defined. If process(id) also throws NumberFormatException due to another internal bug, the catch block may misidentify it as an input data error.

You should isolate the try block strictly around the conversion:

~~~java
final int id;
try {
    id = Integer.parseInt(input);
} catch (NumberFormatException ex) {
    throw new InputValidationException(
            "ID must be a decimal integer", ex);
}
process(id);
~~~

The latter assumes an **InputValidationException(String, Throwable)** exists. It preserves the original NumberFormatException as the cause of the application error and does not swallow other exceptions arising after the parse step.

Principle: **catch exceptions where sufficient context is available**, without wrapping too much unrelated logic. Messages shown to users should identify the input field and required format, rather than printing a raw stack trace or relying on a message that might contain sensitive data.

## 14. Successful Parsing Does Not Mean Valid

A few cases requiring special handling:

- **Integer.parseInt("-3")** succeeds, yet item quantity may have to be non-negative.
- **Integer.parseInt("0007")** returns 7, yet an identifier might need to retain all four characters.
- **Double.parseDouble("NaN")** succeeds, yet prices/scores typically must be finite.
- **new BigDecimal("1.234")** succeeds, yet currency units may be limited to two decimal places.
- **Integer.parseInt("+10")** accepts the plus sign, yet a protocol contract might forbid it.
- **Integer.parseInt** can accept Unicode digits while another system only supports ASCII.
- A very long string can incur excessive parsing cost. Untrusted input needs appropriate length and size limits.

A validation flow can be: **presence check → allowed normalization → grammar → parse → range and business semantics check → generate response**. Regex is not required for every field; complex regexes can even make code harder to maintain.

## 15. Common Mistakes and How to Avoid Them

| Mistake | Fact / Fix |
| --- | --- |
| Thinking NumberFormatException is a checked exception | It is a RuntimeException; the compiler does not require throws |
| Thinking parseInt trims automatically | No; normalize leading/trailing whitespace if the contract allows |
| Confusing numeric literal 1_000 with string "1_000" | Underscores in strings are rejected by parseInt |
| Using parseInt("0xFF") to read prefixed hex | Use parseInt("FF", 16) or decode depending on the contract |
| Using decode for decimals with leading zeros | Decode can interpret them as octal |
| Assuming parseInt overflow wraps around | ParseInt throws NumberFormatException |
| Catching NumberFormatException for Math.toIntExact | Math.toIntExact throws ArithmeticException |
| Treating parseDouble("NaN") as a syntax error | It returns NaN; you must explicitly check finiteness |
| Using double for money requiring exactness | Use BigDecimal from string |
| Skipping null/empty input checks | Report required-field errors clearly |
| Assuming NumberFormat.parse always reads the full string | Check ParsePosition |
| Catching Exception too broadly and returning 0 | Can hide internal bugs and turn fake data into valid values |
| Testing only happy-path strings | Test overflow, empty, signs, locale, Unicode, NaN, and domain rules |
| Writing raw ex.getMessage() to public logs | Can expose unwanted input data |

## 16. Code Review and Testing Checklist

1. Is this a real numeric value or a character-based ID?
2. Does the target type—int, long, BigInteger, double, or BigDecimal—have the right range and precision?
3. How are null, empty, and whitespace-only inputs handled?
4. Are plus/minus signs, leading zeros, whitespace, Unicode digits, and grouping separators allowed?
5. Is the right radix chosen, and is decode avoided when no prefix syntax is expected?
6. When a number is too large, does the application fail reliably or accidentally lose information?
7. Are floating-point numbers checked with Double.isFinite and business bounds?
8. Is locale-specific data parsed across the entire string?
9. Does the field have character count and value length limits?
10. Does the catch block wrap only the parse call, rather than a processing step that could fail internally?
11. Does the user receive the field name and how to fix it, while the logger retains the cause when needed?
12. For batches, does the stop-or-continue policy match the transaction's atomicity requirements?

## 17. Self-Check Questions

**1.** Is NumberFormatException checked or unchecked? **Unchecked**, because it is a subclass of RuntimeException.

**2.** What does Integer.parseInt(" 12 ") return? It throws NumberFormatException; whitespace is not stripped automatically.

**3.** Does Integer.parseInt("2147483648") wrap around to negative? No; it throws NumberFormatException because it exceeds the int range.

**4.** How does Integer.parseInt("010") differ from Integer.decode("010")? They return 10 and 8, respectively.

**5.** Does Double.parseDouble("NaN") throw an error? No; it returns NaN. Use Double.isFinite when the domain requires finite numbers.

**6.** When should you choose BigDecimal(String)? When exact decimal representation from a string is required, especially in monetary/value calculations requiring precision.

**7.** What does Math.toIntExact(Long.parseLong("2147483648")) throw? ArithmeticException at the narrowing step.

**8.** Does an age of 200 parsing successfully mean it is valid? Not yet; it violates the age range in the example.

**9.** Can NumberFormat.parse miss an invalid suffix? Yes; check ParsePosition when full-string parsing is needed.

**10.** Why shouldn't you catch NumberFormatException around both parse and process(id)? Because a NumberFormatException from process could be mistakenly attributed to an input error.

**11.** Must an invalid CSV row halt all remaining rows? Not necessarily; it depends on the contract and business atomicity.

**12.** Why shouldn't you only display ex.getMessage() to the UI? Because the message may lack context or contain sensitive input data; construct error messages with the field name and application error code.

## Official References

- [Java SE 21 API — NumberFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NumberFormatException.html).
- [Java SE 21 API — Integer.parseInt, Integer.valueOf, Integer.decode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
- [Java SE 21 API — Long.parseLong](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).
- [Java SE 21 API — Double.parseDouble and Double.isFinite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21 API — BigInteger(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
- [Java SE 21 API — BigDecimal(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java SE 21 API — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html).
- [JLS Java SE 21 §11.1.1 — Checked and unchecked exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).

**Takeaway:** NumberFormatException indicates that a string cannot be converted to a number according to the API's syntax or range. Choose the right parser for your intent, normalize deliberately, check for overflow, finiteness, and business rules, and handle errors right at the input boundary instead of letting invalid data propagate across layers.