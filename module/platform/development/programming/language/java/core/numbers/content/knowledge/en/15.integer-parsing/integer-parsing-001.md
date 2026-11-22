# parseInt, parseLong, and Corresponding Integer Parsing Methods in Java

When data from a form, configuration file, or CSV contains `"125"`, the value is currently a `String`. To add, compare, or store it as a number, the program needs to **parse** the string into an appropriate primitive while validating its syntax and value range. This introductory lesson focuses on the **signed** parsers of `Byte`, `Short`, `Integer`, and `Long`; variants involving wrappers, unsigned values, prefixes, and `BigInteger` are covered in depth in subsequent lessons.

## 1. The four main signed parsers and return types

| API | Primitive type | Range |
| --- | --- | --- |
| `Byte.parseByte("127")` | `byte` | -128 to 127 |
| `Short.parseShort("32767")` | `short` | -32768 to 32767 |
| `Integer.parseInt("42")` | `int` | -2147483648 to 2147483647 |
| `Long.parseLong("3000000000")` | `long` | -9223372036854775808 to 9223372036854775807 |

Example inside a Java method:

```java
byte flag = Byte.parseByte("100");
short temperature = Short.parseShort("-120");
int count = Integer.parseInt("125");
long total = Long.parseLong("3000000000");
```

The four calls above return **primitives**. The method `Integer.valueOf("42")` returns the wrapper `Integer`, not `int`; the next lesson explains boxing/unboxing. Do not pick a smaller parser just because the receiving variable is wider:

```java
long valid = Long.parseLong("3000000000");
// long invalid = Integer.parseInt("3000000000");
// Integer.parseInt still throws NumberFormatException before assigning to long.
```

**Choose the type from the business domain before parsing.** If a field can be larger than `int` but fits in `long`, use `Long.parseLong`. If it exceeds `long`, choose `BigInteger` when an exact numeric value is needed. If it is an identifier that must preserve leading zeros, keep it as a `String`.

## 2. String syntax and invalid characters

The single-`String` overloads default to parsing **decimal**, optionally starting with an ASCII plus or minus sign followed by at least one valid digit. For example:

```java
int a = Integer.parseInt("+42"); // 42
int b = Integer.parseInt("-42"); // -42
int c = Integer.parseInt("-0");  // 0
int d = Integer.parseInt("077"); // 77, not automatically interpreted as base 8
```

The parser validates the entire string and the value range. The following table gives invalid inputs for `Integer.parseInt(String)`:

| Input | Reason for rejection |
| --- | --- |
| `""`, `"+"`, `"-"` | No digits |
| `"12x"`, `"4 2"` | Invalid character in the middle of the string |
| `"1.5"`, `"1e3"` | Not a decimal integer string |
| `" 42 "` | Does not automatically strip whitespace |
| `"1_000"`, `"42L"` | Literal notation belongs to Java source code, not the string parser |
| `"0x2A"` | Does not automatically recognize hex prefix |
| `"2147483648"` | Exceeds `Integer.MAX_VALUE` |

Java may accept certain Unicode digits via `Character.digit`. If a protocol requires ASCII `0..9`, validate ASCII separately. Calling `strip()` before the parser is only appropriate when the data policy allows ignoring leading/trailing whitespace. Later lessons analyze Unicode, `trim`/`strip`, `NumberFormatException` errors, and literals versus Strings in full detail.

## 3. The radix is a parameter, not a prefix

The parsers have `parse...(String, int radix)` overloads supporting radices from 2 to 36:

```java
int binary = Integer.parseInt("101101", 2); // 45
int octal = Integer.parseInt("77", 8);      // 63
int hex = Integer.parseInt("FF", 16);      // 255
long limit = Long.parseLong("7FFFFFFFFFFFFFFF",16); // Long.MAX_VALUE
```

`Integer.parseInt("0xFF", 16)` throws `NumberFormatException`: `x` is not a valid hex digit in this API. If the input format specifies a hex prefix or a leading zero meaning octal, read the `decode` lesson to choose the appropriate parser. The radix does not increase the integer size that the target type can hold.

## 4. Parse errors differ from arithmetic overflow

`NumberFormatException` occurs for malformed strings, invalid radices, or out-of-range numbers. The parser rejects the input instead of silently wrapping around like `int` addition:

```java
int max = Integer.parseInt("2147483647");  // Success.
// Integer.parseInt("2147483648");         // NumberFormatException.
int wrapped = Integer.MAX_VALUE + 1;       // Integer.MIN_VALUE.
```

When receiving input from users, you should not catch every exception and return 0, because `"0"` is a valid value. You can catch `NumberFormatException` specifically and return an error status or validation message. Some business rules, such as a positive quantity, also require checking `n > 0` after parsing succeeds.

## 5. Standalone runnable Java 17 program

Save as `SignedParsingBasics.java`:

```java
public class SignedParsingBasics {
    static void invalid(String text) {
        try {
            Integer.parseInt(text);
            System.out.println(text + "=UNEXPECTED");
        } catch (NumberFormatException ex) {
            System.out.println(text + "=INVALID");
        }
    }

    public static void main(String[] args) {
        System.out.println("byte=" + Byte.parseByte("127"));
        System.out.println("short=" + Short.parseShort("-32768"));
        System.out.println("int=" + Integer.parseInt("+42"));
        System.out.println("long=" + Long.parseLong("3000000000"));
        System.out.println("binary=" + Integer.parseInt("101101", 2));
        System.out.println("hex=" + Integer.parseInt("FF", 16));
        System.out.println("decimalZero=" + Integer.parseInt("077"));
        invalid("2147483648");
        invalid("1_000");
        invalid(" 42 ");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SignedParsingBasics.java
java SignedParsingBasics
```

Output:

```text
byte=127
short=-32768
int=42
long=3000000000
binary=45
hex=255
decimalZero=77
2147483648=INVALID
1_000=INVALID
 42 =INVALID
```

The three `INVALID` lines come from the program itself catching the exact exception type; they do not depend on the JDK's exception message.

## 6. Self-check

1. Why does `Integer.parseInt("3000000000")` fail, while `Long.parseLong("3000000000")` works?
2. Does `Byte.parseByte("128")` automatically wrap around to -128?
3. Does `Integer.parseInt("077")` return 77 or 63? Why?
4. Distinguish between `Integer.parseInt("FF",16)` and `Integer.parseInt("0xFF",16)`.
5. Should an identifier `"00042"` be converted to an integer for storage?

**Key takeaway:** choose the primitive based on the range to support; specify the radix, sign, digits, bounds, and error reporting strategy. Subsequent lessons dive deeper into each aspect rather than treating a single parse method as sufficient for all formats.

**Standard documentation:** [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html), [Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html), [Short](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html).
