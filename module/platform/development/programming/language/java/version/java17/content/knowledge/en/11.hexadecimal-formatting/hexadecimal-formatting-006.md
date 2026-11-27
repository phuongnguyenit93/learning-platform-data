# Converting Hex Characters and Detecting Invalid Input

## 1. Hexadecimal and How Java Represents Data

Hexadecimal (often abbreviated as **hex**) uses base 16. A single hex digit can take one of 16 values:

| Character | Decimal value | Character | Decimal value |
|---|---:|---|---:|
| `0` | 0 | `8` | 8 |
| `1` | 1 | `9` | 9 |
| `2` | 2 | `A` or `a` | 10 |
| `3` | 3 | `B` or `b` | 11 |
| `4` | 4 | `C` or `c` | 12 |
| `5` | 5 | `D` or `d` | 13 |
| `6` | 6 | `E` or `e` | 14 |
| `7` | 7 | `F` or `f` | 15 |

One hex digit represents 4 bits, called a **nibble**. Two hex digits combined represent one byte (8 bits):

~~~text
Hex:        A       7
Value:     1010    0111
            \\      /
Byte:       10100111
            = 0xA7
            = 167 (unsigned)
            = -89 (signed byte in Java)
~~~

Examples:

- `0x10` = 16 in decimal.
- `0xFF` = 255 when interpreted as an 8-bit unsigned integer.
- `0xA7` = 167 when interpreted as unsigned, but the same 8 bits equal -89 when interpreted as Java's signed `byte` type.

In Java, a hex character has type `char` or lives inside a `String`. To turn it into a nibble value, you must **decode the character in radix 16**, not take the character's Unicode code value.

~~~java
char hex = 'F';
System.out.println((int) hex); // 70: character code of 'F'
System.out.println(Character.digit(hex, 16)); // 15: hex value
~~~

This is the starting point of the lesson: converting characters properly, defining an input acceptance policy, and detecting errors before data reaches business logic.

## 2. Converting a Single Hex Character to a Numeric Value

### 2.1. Using `Character.digit(char, radix)`

Java provides `Character.digit(char ch, int radix)` to convert a character into a numeric value in a given radix:

~~~java
int a = Character.digit('0', 16); // 0
int b = Character.digit('9', 16); // 9
int c = Character.digit('A', 16); // 10
int d = Character.digit('f', 16); // 15
int invalid = Character.digit('G', 16); // -1
~~~

The `radix` parameter is the base used for interpretation. For hex, use `16`. If the character is not a valid digit in that radix or the radix is out of range, the method returns `-1`.

A small helper method can wrap this to turn errors into clear messages:

~~~java
static int parseHexDigit(char ch) {
    int digit = Character.digit(ch, 16);
    if (digit < 0) {
        throw new IllegalArgumentException(
                "Invalid hex character: '" + ch + "'"
        );
    }
    return digit;
}
~~~

Example:

~~~java
System.out.println(parseHexDigit('B')); // 11
System.out.println(parseHexDigit('e')); // 14
System.out.println(parseHexDigit('8')); // 8
// parseHexDigit('X') -> IllegalArgumentException
~~~

**Do not deduce the value by casting `(int) ch`.** `'A'` has character code 65 but hex value 10; `'F'` has code 70 but hex value 15.

### 2.2. Using `Character.forDigit(int digit, int radix)` in Reverse

`Character.forDigit` converts a numeric value into its character representation in the given radix:

~~~java
char zero = Character.forDigit(0, 16);   // '0'
char nine = Character.forDigit(9, 16);   // '9'
char ten = Character.forDigit(10, 16);   // 'a'
char fifteen = Character.forDigit(15, 16); // 'f'
~~~

With radix 16, letters are returned in lowercase. To display uppercase:

~~~java
char upper = Character.toUpperCase(Character.forDigit(15, 16));
System.out.println(upper); // F
~~~

If the digit is invalid for the radix, `Character.forDigit` returns the null character `'\u0000'`. Therefore, if numeric data comes from external input, validate it first:

~~~java
static char toHexDigit(int value) {
    if (value < 0 || value > 15) {
        throw new IllegalArgumentException("Nibble must be in [0, 15]");
    }
    return Character.toUpperCase(Character.forDigit(value, 16));
}
~~~

### 2.3. Checking ASCII Characters Manually When the Format Requires ASCII Hex

`Character.digit` follows Java's Unicode rules and can recognize certain non-ASCII digit characters. That is useful for multilingual text, but **not every format allows it**. Hex in protocols, binary files, identifiers, and many data-exchange standards typically accept only the six ASCII ranges: `0-9`, `A-F`, `a-f`.

If the input contract requires strict ASCII, check explicitly:

~~~java
static int asciiHexDigit(char ch) {
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'A' && ch <= 'F') {
        return ch - 'A' + 10;
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    return -1;
}
~~~

Example:

~~~java
System.out.println(asciiHexDigit('0')); // 0
System.out.println(asciiHexDigit('9')); // 9
System.out.println(asciiHexDigit('A')); // 10
System.out.println(asciiHexDigit('f')); // 15
System.out.println(asciiHexDigit('G')); // -1
System.out.println(asciiHexDigit(' ')); // -1
~~~

The two approaches have different goals:

| Approach | Behavior | Use when |
|---|---|---|
| `Character.digit(ch, 16)` | Follows Java Unicode digit/letter rules | Processing characters with Unicode semantics |
| ASCII check helper | Accepts only `0-9`, `A-F`, `a-f` | Reading protocols, hex files, tokens, or ASCII-only formats |

Do not use an overly permissive check for protocol data simply because it "can convert to a number." Accepting more characters than the specification allows can cause discrepancies between systems, canonicalization bugs, or difficulty detecting malformed data.

## 3. Converting an Entire Hex String to an Integer

### 3.1. Using `Integer.parseInt(text, 16)`

When a hex string represents a signed integer within the `int` range, you can use:

~~~java
int decimal = Integer.parseInt("7B", 16);
System.out.println(decimal); // 123
~~~

Example:

~~~java
int a = Integer.parseInt("FF", 16);  // 255
int b = Integer.parseInt("10", 16);  // 16
int c = Integer.parseInt("7fffffff", 16); // Integer.MAX_VALUE
~~~

This method:

- Accepts uppercase or lowercase hex digits.
- Does not automatically recognize the `0x` or `0X` prefix.
- Can accept a `+` or `-` sign according to integer parsing rules.
- Throws `NumberFormatException` if the string is empty, contains invalid characters, or the value exceeds the `int` range.

Invalid examples:

~~~java
Integer.parseInt("0xFF", 16); // NumberFormatException
Integer.parseInt("FG", 16);   // NumberFormatException
Integer.parseInt("FF ", 16);  // NumberFormatException
~~~

If a protocol permits the `0x` prefix, strip the prefix **according to a clearly defined rule** before parsing:

~~~java
static int parseHexInt(String text) {
    if (text == null) {
        throw new IllegalArgumentException("Hex value must not be null");
    }

    String digits = text.startsWith("0x") || text.startsWith("0X")
            ? text.substring(2)
            : text;

    if (digits.isEmpty()) {
        throw new IllegalArgumentException("Missing hex digits");
    }
    return Integer.parseInt(digits, 16);
}
~~~

This code does not trim whitespace and does not accept signs. That is an intentional contract choice; if those forms are to be allowed, add explicit rules for them.

### 3.2. Distinguishing Signed Integers from Unsigned Bit Interpretation

An 8-digit hex string such as `FFFFFFFF` represents 32 bits all equal to 1. If parsed with `Integer.parseInt`, the value exceeds `Integer.MAX_VALUE` and is rejected:

~~~java
// Throws NumberFormatException:
// int value = Integer.parseInt("FFFFFFFF", 16);
~~~

If you want to interpret those 32 bits as an **unsigned integer**, use `Integer.parseUnsignedInt`:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);

System.out.println(bits); // -1: how Java stores the bit pattern in a signed int
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toHexString(bits)); // ffffffff
~~~

Java's `int` remains a signed type. `parseUnsignedInt` lets you read the 32-bit unsigned range and return the same bit pattern in `int`; when displaying the unsigned quantity, use `Integer.toUnsignedString` or `Integer.toUnsignedLong`.

Similarly, `Long.parseUnsignedLong(text, 16)` can read 64-bit unsigned values and retain the bit pattern in `long`. Choose the API based on the **numeric meaning** of the data, not merely the number of hex digits.

### 3.3. Converting an Integer to a Hex String

Convenient methods:

~~~java
String a = Integer.toHexString(255); // "ff"
String b = Long.toHexString(255L);   // "ff"
String c = Integer.toHexString(16);  // "10"
~~~

`toHexString`:

- Returns lowercase.
- Does not add a `0x` prefix.
- Does not guarantee fixed width or leading zeros.
- For negative numbers, returns the bit representation of the corresponding primitive type, not a string with a minus sign.

Example:

~~~java
System.out.println(Integer.toHexString(15));  // f
System.out.println(Integer.toHexString(-1));  // ffffffff
~~~

If fixed width is required, you can use formatting:

~~~java
int value = 15;
String twoDigits = String.format("%02X", value);
System.out.println(twoDigits); // 0F
~~~

For a single byte, remember Java `byte` is signed; use `b & 0xff` to obtain the unsigned value before formatting:

~~~java
byte b = (byte) 0xA7;
String hex = String.format("%02X", b & 0xff);
System.out.println(hex); // A7
~~~

In Java 17, if the goal is to convert an entire byte array to a hex string, `HexFormat` is usually clearer than writing a formatting loop manually.

## 4. Reading a Byte from Two Hex Characters

### 4.1. A Byte Consists of Two Nibbles

Suppose we have the string `"A7"`:

~~~text
'A' -> 10 -> 1010 (high nibble)
'7' ->  7 -> 0111 (low nibble)

(10 << 4) | 7
= 160 | 7
= 167
= 0xA7
~~~

Code:

~~~java
int high = asciiHexDigit('A');
int low = asciiHexDigit('7');
int unsignedByte = (high << 4) | low;

System.out.println(unsignedByte); // 167
System.out.println(Integer.toHexString(unsignedByte)); // a7
~~~

The expression `(high << 4) | low` places the high nibble into the upper four bits and the low nibble into the lower four bits. Before combining, both nibbles must be in `0..15`; if either is `-1`, the result is meaningless.

### 4.2. Why Doesn't `Byte.parseByte("FF", 16)` Work?

`byte` in Java is an **8-bit signed** integer ranging from -128 to 127. The hex string `FF` has an unsigned value of 255, which exceeds that range:

~~~java
Byte.parseByte("7F", 16); // 127
Byte.parseByte("80", 16); // NumberFormatException
Byte.parseByte("FF", 16); // NumberFormatException
~~~

If you need to read a binary byte, parse the 0..255 value first and then convert it to the `byte` bit pattern:

~~~java
int unsigned = Integer.parseInt("FF", 16); // 255
byte bits = (byte) unsigned;                // -1

System.out.println(bits);          // -1
System.out.println(bits & 0xff);   // 255
System.out.println(Integer.toHexString(bits & 0xff)); // ff
~~~

Casting `(byte) 255` preserves the low 8 bits `11111111`, which is interpreted as -1 in Java. If you need to represent the byte as an unsigned number when reading, use `bits & 0xff`.

### 4.3. Combining Bytes and Extracting Nibbles

Given a byte value:

~~~java
int value = 0xA7;
int highNibble = (value >>> 4) & 0x0F;
int lowNibble = value & 0x0F;

System.out.println(highNibble); // 10
System.out.println(lowNibble);  // 7
~~~

For a signed `byte`, convert to unsigned before shifting:

~~~java
byte raw = (byte) 0xA7;
int unsigned = raw & 0xff;

int high = (unsigned >>> 4) & 0x0f;
int low = unsigned & 0x0f;
~~~

This avoids sign-extension bugs when `byte` is widened to `int`.

## 5. Using `HexFormat` in Java 17

### 5.1. `HexFormat` Is the Standard API from Java 17

Java 17 provides the `java.util.HexFormat` class for formatting and parsing hex strings. When you need to convert a byte array to a hex string or parse a hex string into a byte array, it is usually cleaner and less error-prone than writing manual loops.

~~~java
import java.util.HexFormat;

public class HexFormatBasic {
    public static void main(String[] args) {
        byte[] data = {
                (byte) 0xCA,
                (byte) 0xFE,
                0x01,
                0x23
        };

        HexFormat hex = HexFormat.of();
        String encoded = hex.formatHex(data);
        byte[] decoded = hex.parseHex(encoded);

        System.out.println(encoded); // cafe0123
        System.out.println(java.util.Arrays.equals(data, decoded)); // true
    }
}
~~~

`HexFormat.of()` creates the default formatter:

- Uses lowercase.
- Has no delimiter between bytes.
- Adds no prefix/suffix.
- Represents each byte with exactly two hex digits.

`HexFormat` is immutable and thread-safe; a configured instance can be reused.

### 5.2. Switching to Uppercase or Adding a Delimiter

~~~java
import java.util.HexFormat;

byte[] bytes = { 0x01, 0x23, (byte) 0xAB, (byte) 0xFF };

String lower = HexFormat.of().formatHex(bytes);
String upper = HexFormat.of().withUpperCase().formatHex(bytes);
String colon = HexFormat.ofDelimiter(":").formatHex(bytes);
String spaced = HexFormat.ofDelimiter(" ").withUpperCase()
        .formatHex(bytes);

System.out.println(lower);  // 0123abff
System.out.println(upper);  // 0123ABFF
System.out.println(colon);  // 01:23:ab:ff
System.out.println(spaced); // 01 23 AB FF
~~~

You can configure a prefix and suffix if the protocol format requires them:

~~~java
HexFormat prefixed = HexFormat.of().withPrefix("0x");
String text = prefixed.formatHex(new byte[] { 0x01, (byte) 0xAF });
~~~

Prefix/suffix/delimiter are part of the configured format. When parsing, use a formatter matching the exact rules used to produce the string; do not assume the default formatter strips arbitrary prefixes or whitespace.

### 5.3. Parsing Hex into a Byte Array

~~~java
import java.util.HexFormat;
import java.util.Arrays;

byte[] bytes = HexFormat.of().parseHex("CAFE0123");

System.out.println(Arrays.toString(bytes));
System.out.println(HexFormat.of().withUpperCase().formatHex(bytes));
~~~

`parseHex` requires digits to pair up into bytes. A string with an odd number of characters cannot form complete bytes in the default format; strings with non-hex characters are also rejected with `IllegalArgumentException`.

Example:

~~~java
HexFormat.of().parseHex("ABC");  // IllegalArgumentException: odd number of digits
HexFormat.of().parseHex("ABG1"); // IllegalArgumentException: G is not hex
~~~

If the input has a delimiter, configure the matching delimiter:

~~~java
HexFormat colonHex = HexFormat.ofDelimiter(":");
byte[] data = colonHex.parseHex("CA:FE:01:23");
System.out.println(HexFormat.of().formatHex(data)); // cafe0123
~~~

Do not strip delimiters by removing every non-hex character without an explicit contract. Doing so can turn invalid input like `"CA:ZZ:FE"` into a different string that appears valid after filtering.

### 5.4. Checking Hex Characters with `HexFormat.isHexDigit`

Java 17 provides:

~~~java
System.out.println(HexFormat.isHexDigit('0')); // true
System.out.println(HexFormat.isHexDigit('A')); // true
System.out.println(HexFormat.isHexDigit('f')); // true
System.out.println(HexFormat.isHexDigit('G')); // false
System.out.println(HexFormat.isHexDigit(' ')); // false
~~~

This API is suitable when you want to check characters against the ASCII hex digit set. It can be used in validation before calling the parser or when building custom error messages with character positions.

## 6. Detecting Invalid Hex Input

### 6.1. Define the Contract Before Writing a Parser

Before parsing, define what the input format allows:

| Aspect | Question to decide |
|---|---|
| Null | Is it allowed? If not, what error is returned? |
| Empty string | Does it represent an empty byte array or missing input? |
| Letter case | Are both uppercase and lowercase accepted? |
| Prefix | Is `0x`/`0X` allowed? |
| Whitespace | Should leading/trailing whitespace be trimmed, or spaces allowed between bytes? |
| Delimiter | Are `:`, hyphens, or spaces allowed between bytes? |
| Digit count | Must it be even, or are odd nibbles allowed with a padding rule? |
| Characters | ASCII only, or Unicode digits accepted? |
| Length | Is there a byte limit to prevent excessive memory consumption? |

A safe parser does not guess the format. If an API specifies a contiguous hex string, the parser should reject separators, prefixes, and whitespace rather than silently fixing the input.

### 6.2. Common Errors

| Input | Problem | Handling approach |
|---|---|---|
| `null` | No string to parse | Reject or represent absence according to the contract |
| `""` | Empty string | Decide whether it represents an empty array |
| `"A"` | Single nibble, not a full byte | Reject or define a clear padding rule |
| `"ABC"` | Odd character count | Reject if the format requires byte pairs |
| `"G1"` | `G` is not hex | Report the invalid character position |
| `"1Z"` | `Z` is not hex | Report the invalid character position |
| `"0xFF"` | Prefix not accepted by default parser | Handle the prefix explicitly if allowed by the contract |
| `"FF "` | Trailing whitespace | Reject or trim if specified by the contract |
| `"FF:00"` | Delimiter not part of default format | Use a formatter configured with the matching delimiter |
| `"FFFFFFFF"` with `parseInt` | Exceeds signed int range | Use unsigned API or a wider type |
| `"FF"` with `Byte.parseByte` | 255 exceeds signed byte range | Parse unsigned 0..255 and convert bit pattern if needed |

### 6.3. Distinguishing Syntax Errors from Range Errors

These are two distinct error categories:

- **Syntax error:** contains invalid characters, empty string, odd digit count, malformed prefix/delimiter.
- **Range error:** string contains all valid hex characters, but the value cannot be represented by the target numeric type.

Example:

~~~java
Integer.parseInt("GG", 16); // Syntax error
Integer.parseInt("FFFFFFFF", 16); // Signed int range error
~~~

If user-friendly error messages are needed, you can validate syntax first, then parse into a sufficiently wide type or use the appropriate unsigned API to separate the two error types.

## 7. Writing a Custom Byte-Array Parser with Positional Error Reporting

### 7.1. Rules of the Example Parser

Suppose an API accepts a hex string representing a byte array with these rules:

1. The string must not be null.
2. The string must have an even number of characters.
3. Only ASCII characters `0-9`, `A-F`, `a-f` are accepted.
4. No `0x` prefix, delimiter, or whitespace is accepted.
5. An empty string represents an empty byte array.

This is a concrete contract. Another API may choose different rules, but they must be clearly documented.

### 7.2. Parser Implementation

~~~java
import java.util.Objects;

public class StrictHexParser {

    private static int digitAt(String input, int index) {
        char ch = input.charAt(index);
        int value = asciiHexDigit(ch);

        if (value < 0) {
            throw new IllegalArgumentException(
                    "Invalid hex character at index " +
                    index + ": '" + ch + "'"
            );
        }
        return value;
    }

    private static int asciiHexDigit(char ch) {
        if (ch >= '0' && ch <= '9') {
            return ch - '0';
        }
        if (ch >= 'A' && ch <= 'F') {
            return ch - 'A' + 10;
        }
        if (ch >= 'a' && ch <= 'f') {
            return ch - 'a' + 10;
        }
        return -1;
    }

    public static byte[] parse(String input) {
        Objects.requireNonNull(input, "input");

        if ((input.length() & 1) != 0) {
            throw new IllegalArgumentException(
                    "Hex string must have an even number of characters"
            );
        }

        byte[] result = new byte[input.length() / 2];

        for (int i = 0; i < input.length(); i += 2) {
            int high = digitAt(input, i);
            int low = digitAt(input, i + 1);
            int value = (high << 4) | low;
            result[i / 2] = (byte) value;
        }

        return result;
    }
}
~~~

Usage example:

~~~java
byte[] bytes = StrictHexParser.parse("CAFE0123");

for (byte value : bytes) {
    System.out.printf("%02X ", value & 0xff);
}
~~~

Output:

~~~text
CA FE 01 23
~~~

### 7.3. Why Check Length First?

Each byte requires exactly two nibbles. If the length is odd, the loop could access `input.charAt(i + 1)` out of bounds on the last pair. Checking up front:

~~~java
if ((input.length() & 1) != 0) {
    throw new IllegalArgumentException("...");
}
~~~

gives a clearer error and avoids processing an undefined half-byte.

### 7.4. Why Validate Both High and Low Nibbles?

The combined value:

~~~java
int value = (high << 4) | low;
~~~

is valid only if `high` and `low` are in `0..15`. If a character-conversion helper returns `-1` for invalid characters without checking, the bit shift and OR still execute and produce a meaningless byte. Therefore, the parser must reject invalid characters **before combining them into a byte**.

### 7.5. Limiting Input Size

In real systems, a string can be very long. Before allocating:

~~~java
if (input.length() > MAX_HEX_CHARACTERS) {
    throw new IllegalArgumentException("Hex payload is too long");
}
~~~

The limit should be based on the business payload size, protocol, or allowable resources. When parsing data from untrusted requests, this limit prevents overly large array allocations and reduces the risk of unexpected memory consumption.

## 8. Parsing a Hex Number and Parsing a Byte Array Are Different Tasks

A hex string can be interpreted in several ways:

- As **a signed or unsigned integer**.
- As **a byte sequence**.
- As **a fixed-width identifier**.
- As **a binary representation** for a protocol or encoded data.

For example, `"FF"`:

| Interpretation | Result |
|---|---|
| `Integer.parseInt("FF", 16)` | integer 255 |
| `Integer.parseUnsignedInt("FF", 16)` | `int` bit pattern with unsigned value 255 |
| `HexFormat.of().parseHex("FF")` | byte array with one byte having bit pattern `11111111` |
| `Byte.parseByte("FF", 16)` | error because 255 is outside signed byte range |
| `Character.digit('F', 16)` | nibble 15 |

Do not choose an API merely because "the input is a hex string." Determine whether the desired result is an integer, a nibble, a byte, or a byte array.

### 8.1. Reading a Byte Array as a Multi-Byte Integer

Suppose the data `"0102"` represents a 16-bit big-endian integer:

~~~java
byte[] bytes = HexFormat.of().parseHex("0102");

int value = ((bytes[0] & 0xff) << 8)
        | (bytes[1] & 0xff);

System.out.println(value); // 258
~~~

For multi-byte data, you must know the **endianness**:

- Big-endian: the most significant byte comes first.
- Little-endian: the least significant byte comes first.

A hex string only shows the order in which bytes are written; it does not tell you the byte order of an integer field in a protocol.

### 8.2. Using ByteBuffer When Reading Binary Structures

For binary data with multiple fields, `ByteBuffer` makes byte order explicit:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

byte[] bytes = HexFormat.of().parseHex("01020304");

int bigEndian = ByteBuffer.wrap(bytes)
        .order(ByteOrder.BIG_ENDIAN)
        .getInt();

int littleEndian = ByteBuffer.wrap(bytes)
        .order(ByteOrder.LITTLE_ENDIAN)
        .getInt();

System.out.println(bigEndian);    // 16909060
System.out.println(littleEndian); // 67305985
~~~

Use this only after the input length and structure have been validated. `ByteBuffer.getInt()` requires at least four bytes from the current position; otherwise, it throws `BufferUnderflowException`.

## 9. Proper Error Handling in Applications

### 9.1. Do Not Catch Errors and Return a Dummy Value

Avoid:

~~~java
static int unsafeParse(String input) {
    try {
        return Integer.parseInt(input, 16);
    } catch (NumberFormatException ex) {
        return 0; // Hides invalid input
    }
}
~~~

If inputs like `"G1"` or `"ZZ"` are turned into 0, the system may mistake them for valid data. A default value should only be used if the business contract explicitly specifies it.

### 9.2. Report Clear Errors and Preserve the Cause

~~~java
static int parseUserHex(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Hex code must not be null");
    }
    if (input.isEmpty()) {
        throw new IllegalArgumentException("Hex code must not be empty");
    }

    try {
        return Integer.parseInt(input, 16);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid hex code: " + input,
                ex
        );
    }
}
~~~

At the API layer, you can catch `IllegalArgumentException` at the boundary and convert it into an appropriate validation response. Do not expose internal stack traces or sensitive data in external error messages.

### 9.3. Validate Before Parsing or Use a Standard Parser?

If you need detailed positional error messages, you can inspect characters first. If you only need to know whether the entire string is valid, `HexFormat.parseHex` or `Integer.parseInt` is usually sufficient.

Do not reimplement an entire library parser without a specific requirement. Writing a custom parser makes you responsible for:

- Character pairs and error positions.
- ASCII/Unicode rules.
- Maximum length.
- Prefix, delimiter, and whitespace.
- Numeric overflow and byte order.
- Format compatibility with other systems.

## 10. Formatting Choices and Canonicalization

### 10.1. Contiguous Hex Strings

~~~text
CAFE0123
~~~

Pros: compact, easy to store in JSON or logs. Cons: for long payloads, humans find it hard to count bytes and locate error positions.

### 10.2. Using Colons or Spaces Between Bytes

~~~text
CA:FE:01:23
CA FE 01 23
~~~

Pros: easy to read and inspect visually. Cons: parsers must agree on the delimiter and must not arbitrarily strip separators.

### 10.3. The `0x` Prefix

~~~text
0xCAFE
~~~

A prefix helps readers recognize the base, but not every parsing API accepts it. `Integer.parseInt("0xFF", 16)` and `HexFormat.of().parseHex("0xFF")` do not automatically remove the prefix in their default configurations.

If a format specifies a single prefix at the start of the string, validate and remove that exact prefix before parsing; do not remove all `x` or `0` characters using a global replacement.

### 10.4. Uppercase or Lowercase

Hex can be represented in uppercase or lowercase. Two representations of the same bytes:

~~~text
ca fe 01 23
CA FE 01 23
~~~

When data is used as a signature, hash, cache key, or exact-match string, establish a **canonicalization rule** (for example lowercase, no delimiter, no prefix) so that two different representations of the same data do not diverge.

## 11. Security and Untrusted Input Data

Hex frequently appears in tokens, digests, key IDs, binary data, requests, or files. Validation should match the intended use:

- **Enforce length limits before allocation:** prevent huge payloads from exhausting memory.
- **Reject out-of-format characters:** do not silently strip invalid characters.
- **Do not trim or normalize outside the contract:** avoid two system layers interpreting the same string differently.
- **Verify exact byte counts:** for example, a fixed-length hash must have the exact byte count, not just valid hex characters.
- **Do not log secrets:** if a hex string is a key, token, or credential, avoid putting the full value into exception messages or logs.
- **Distinguish encoding from encryption:** hex is merely a representation of bytes as characters; it does not encrypt secrets and does not provide integrity.

Example checking digest length:

~~~java
import java.util.HexFormat;

static byte[] parseSha256Hex(String input) {
    if (input == null || input.length() != 64) {
        throw new IllegalArgumentException(
                "SHA-256 hex must have exactly 64 characters"
        );
    }

    byte[] bytes = HexFormat.of().parseHex(input);
    if (bytes.length != 32) {
        throw new IllegalArgumentException("Invalid digest length");
    }
    return bytes;
}
~~~

SHA-256 produces a 256-bit digest, corresponding to 32 bytes and 64 hex digits. Having the right length does not prove the digest is genuine or trustworthy; verification requires comparing against an expected value or following an appropriate verification flow.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Casting `(int) 'F'` to get the hex value | Gets character code 70 instead of 15 | Use `Character.digit('F', 16)` |
| Not checking `Character.digit` returning -1 | Combines invalid nibble into a wrong byte | Check each digit before shift/OR |
| Using `Character.digit` when protocol requires ASCII | May accept non-ASCII Unicode characters outside contract | Use an explicit ASCII check or `HexFormat.isHexDigit` |
| Using `Integer.parseInt` with `0x` prefix | `NumberFormatException` | Validate and strip prefix per contract |
| Calling `trim()` or filtering characters without a rule | Hides malformed input or alters data | Reject or handle the defined delimiter properly |
| Using `Byte.parseByte("FF", 16)` | Signed byte range error | Parse 0..255 and cast if bit pattern is needed |
| Using `Integer.parseInt("FFFFFFFF",16)` | Signed int overflow | Use `parseUnsignedInt` when semantically appropriate |
| Forgetting even-length check in manual byte-array parser | Index error or undefined trailing nibble | Validate length before the loop |
| Not checking maximum length | Can allocate overly large memory | Enforce protocol-defined limits |
| Confusing hex with encryption | Data remains publicly readable | Use appropriate cryptographic mechanisms |
| Using default `HexFormat` with delimited/prefixed input | Parser rejects the format | Configure matching formatters consistently in both directions |
| Forgetting `& 0xff` when displaying bytes | Bytes above 127 display as negative numbers | Convert to unsigned when displaying |

## 13. Practice Exercises

### Exercise 1 — Converting a Single Hex Character

Write a method `int parseNibble(char ch)` using `Character.digit(ch, 16)`. The method must throw `IllegalArgumentException` if the result is negative. Test inputs `'0'`, `'9'`, `'A'`, `'f'`, `'G'`, and a space.

Then write an ASCII-only version using `HexFormat.isHexDigit` or character range checks.

### Exercise 2 — Converting a Number to a Hex Character

Write `char toHexDigit(int value)` for the range 0..15. Use `Character.forDigit`, return uppercase, and reject values -1, 16, and 100.

### Exercise 3 — Reading a Single Byte

Write a method that takes two hex characters and returns a `byte`. Validate both characters, combine the nibbles with shift/OR, and test `FF`, `80`, and `00`. Explain why `(byte) 0xFF` prints as -1 while its bit pattern remains 255 unsigned.

### Exercise 4 — Parsing a Byte Array

Write a parser that accepts only contiguous ASCII hex strings of even length, with no prefix, no delimiter, and a maximum limit of 4,096 bytes. On failure, report the invalid character position or the length violation.

Compare with `HexFormat.of().parseHex(input)`: when should you use the standard library, and when is a custom parser needed?

### Exercise 5 — Formatting Data

Given the byte array:

~~~java
byte[] data = { 0x01, 0x23, (byte) 0xAB, (byte) 0xFF };
~~~

Produce four strings:

1. Lowercase hex, contiguous.
2. Uppercase hex, contiguous.
3. Hex with delimiter `:`.
4. Hex with a space delimiter.

Use `HexFormat`, then parse each string back using the matching formatter and compare the byte arrays.

### Exercise 6 — Distinguishing Syntax and Range Errors

With `Integer.parseInt(input, 16)`, test:

- `"G1"`
- `"FFFFFFFF"`
- `"7FFFFFFF"`
- `""`
- `"0xFF"`

Classify syntax errors, range errors, and valid cases. Use an unsigned API if your requirement is to read all 32 bits.

### Exercise 7 — Validating Hash Input

Write a function to parse a SHA-256 hex string:

- Not null.
- Exactly 64 ASCII hex characters.
- No prefix, delimiter, or whitespace.
- Returns a 32-byte array.

Explain why valid format/length does not prove the digest content is authentic.

## 14. Self-Check Questions

1. How many bits are in a nibble, and how many hex digits are in a byte?
2. Why does `(int) 'A'` differ from `Character.digit('A', 16)`?
3. What value does `Character.digit` return when a character is invalid?
4. What is the difference between `Character.digit` and an explicit ASCII check?
5. What character does `Character.forDigit(15, 16)` return?
6. Why does `Integer.parseInt("0xFF", 16)` not automatically strip the prefix?
7. What is the difference between `parseInt` and `parseUnsignedInt` when reading `FFFFFFFF`?
8. Why does `Byte.parseByte("FF", 16)` throw an exception?
9. Why must `b & 0xff` be used when reading a byte as an unsigned number?
10. Which Java version introduced `HexFormat` and what problem does it solve?
11. When does `HexFormat.parseHex` throw `IllegalArgumentException`?
12. Why does a hex string representing a byte array usually require an even number of characters?
13. Why should you not silently remove all non-hex characters?
14. How does endianness affect combining multiple bytes into a number?
15. Why is hex not encryption?

## 15. References

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): standard API from Java 17 to format, validate, and parse hex.
- [Java SE 17 API — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `digit`, `forDigit`, and character-to-radix conversion rules.
- [Java SE 17 API — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `parseUnsignedInt`, `toHexString`, and unsigned methods.
- [Java SE 17 API — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): range and conversions of the signed byte type.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): reading binary data according to byte order.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): primitive types, numeric conversions, and value representations in Java.

When working with hex, determine beforehand whether you are converting **a character into a nibble, a string into an integer, or a string into a byte array**. Use `Character.digit` or `HexFormat` for the right task, validate length and characters against the contract, and distinguish signed integers from unsigned bit patterns. Clear validation ensures malformed hex data is rejected right at the boundary instead of silently turning into a different value in downstream processing layers.
