# Parsing a CharSequence Slice Without Creating a Substring When the API Supports It

> **Java core – numbers · Integer parsing**  
> **Goal:** Parse a slice of characters directly inside `String`, `StringBuilder`, `StringBuffer`, or `CharBuffer` when reading signed or unsigned `int`/`long`; specify start/end indices and radix accurately; avoid creating unnecessary `substring` objects; handle exceptions, overflow, and performance limits properly in Java 17+.

## 1. Real-world scenario: needing just one number inside a long string

Suppose a processor receives a line:

```text
id=12345;delta=-42;flags=7F
```

The goal is to read `12345` as an `int`, `-42` as an `int`, and `7F` as a base-16 integer.

How many developers write it:

```java
String line = "id=12345;delta=-42;flags=7F";
int idStart = line.indexOf("id=") + 3;
int idEnd = line.indexOf(';', idStart);

int id = Integer.parseInt(line.substring(idStart, idEnd));
```

This works for controlled input. Yet `substring(idStart, idEnd)` allocates a `String` object representing the slice, whereas parsing actually only needs to **read characters from the start position to the end position**.

If the API being called directly supports a `CharSequence` range, you can write:

```java
int id = Integer.parseInt(line, idStart, idEnd, 10);
```

This syntax reads the range `[idStart, idEnd)` of the original string directly and does not require the program to create a substring via `substring`. This is an advantage worth considering in parsers that process many numeric fields or large record volumes.

**Important distinction:** "Not creating a substring yourself" **does not mean** "the entire operation is guaranteed zero-allocation" or "definitely faster in every case." The aim is to avoid an **unnecessary** intermediate conversion step; actual performance also depends on inputs, the JVM, the JIT, error handling, and how indices are determined.

## 2. What is CharSequence and why can it be parsed directly?

`CharSequence` is an interface representing an **indexable sequence of characters**. Several familiar types implement this interface:

| Type | Typical characteristics | Significance when parsing |
| --- | --- | --- |
| `String` | Immutable string | Can parse a range directly without calling `substring` |
| `StringBuilder` | Mutable character buffer | Parse accumulated data directly without `toString()` |
| `StringBuffer` | Mutable character buffer with class-level synchronization | Also passable as `CharSequence`; must account for concurrent modification |
| `CharBuffer` | Buffer-style character access region | Can parse from a buffer view if indices align |
| Custom `CharSequence` implementation | Class-defined access rules | Must keep `length()`, `charAt()`, and data consistent |

The basic methods of the interface include `length()`, `charAt(index)`, and `subSequence(start,end)`. Range-based parse overloads can access characters directly through the interface so the caller **does not have to** extract a substring to pass into a `String`-only API.

However, a `CharSequence` can be **mutable**. The JDK documentation explicitly states that range-based parse overloads **do not defend themselves** if the character sequence is modified while being parsed. Therefore, buffers shared across multiple threads must control data mutation with an appropriate synchronization contract; never assume the parser API makes a safe copy automatically.

## 3. The four suitable overloads in Integer and Long

Java 9 added overloads for parsing a `CharSequence` range; all are available in Java 17+:

| Method | Number kind | Return type |
| --- | --- | --- |
| `Integer.parseInt(CharSequence, int, int, int)` | signed `int` | `int` |
| `Integer.parseUnsignedInt(CharSequence, int, int, int)` | 32 bits interpreted unsigned | `int` (same 32 bits) |
| `Long.parseLong(CharSequence, int, int, int)` | signed `long` | `long` |
| `Long.parseUnsignedLong(CharSequence, int, int, int)` | 64 bits interpreted unsigned | `long` (same 64 bits) |

All four parameters follow the same order:

```java
Integer.parseInt(sequence, beginIndex, endIndex, radix);
Long.parseLong(sequence, beginIndex, endIndex, radix);
Integer.parseUnsignedInt(sequence, beginIndex, endIndex, radix);
Long.parseUnsignedLong(sequence, beginIndex, endIndex, radix);
```

- `sequence`: source character sequence; can be a `StringBuilder`, not necessarily a `String`.
- `beginIndex`: **starting index, included in the slice** (*inclusive*).
- `endIndex`: **ending index, excluded from the slice** (*exclusive*).
- `radix`: base used to interpret digits; Java supports from `Character.MIN_RADIX = 2` to `Character.MAX_RADIX = 36`.

There is no three-parameter overload `(CharSequence, begin, end)` defaulting to radix 10 in this group. When parsing by range, pass **all four arguments** and write `10` for decimal numbers.

**API coverage note:** Methods such as `Byte.parseByte`, `Short.parseShort`, `Integer.valueOf`, `Long.valueOf`, or `BigInteger` constructors **do not automatically have the same four-parameter overload** just because `Integer.parseInt` does. Always check the exact signature of the class/method before refactoring code.

## 4. Indices [beginIndex, endIndex): position-by-position example

Example:

```text
String: id=12345;delta=-42
Index:  0123456789...
        ^  ^    ^
        |  |    |
        |  3    8
        0

id=       at [0,3)
12345     at [3,8)
;         at index 8
```

Java code:

```java
StringBuilder line = new StringBuilder("id=12345;delta=-42");
int from = 3;
int to = 8;

int id = Integer.parseInt(line, from, to, 10);
System.out.println(id); // 12345
```

Because `endIndex` is exclusive, the semicolon at index 8 is **not** passed to the parser. If you accidentally call `Integer.parseInt(line, 3, 9, 10)`, the slice includes `"12345;"` and parsing fails because `;` is not a decimal digit.

### Rules for specifying indices

A valid range satisfies:

\[
0 \le beginIndex \le endIndex \le sequence.length()
\]

- `beginIndex == endIndex`: empty range; indices are **valid**, yet there are no digits to parse, causing `NumberFormatException`.
- `beginIndex < 0`: invalid range, `IndexOutOfBoundsException`.
- `beginIndex > endIndex`: invalid range, `IndexOutOfBoundsException`.
- `endIndex > sequence.length()`: invalid range, `IndexOutOfBoundsException`.

Do not mix indices from a **UTF-8 byte array**, token byte offsets, or **Unicode code point** counts with the indices used by `CharSequence.charAt`. In standard Java strings, these indices count **UTF-16 code units**; characters outside the BMP can occupy two `char` units. For ASCII numeric tokens, each digit occupies one `char`, yet the token's starting position must still come from the exact `CharSequence` being parsed.

## 5. Parsing directly from StringBuilder: no need for toString or substring

When a line is being constructed with `StringBuilder`, an older approach might look like:

```java
StringBuilder buffer = new StringBuilder("count=12345;");
int start = 6;
int end = 11;

// Create a string from the slice and then parse:
// int count = Integer.parseInt(buffer.substring(start, end));
```

Direct approach:

```java
int count = Integer.parseInt(buffer, start, end, 10);
System.out.println(count); // 12345
```

**Do not write** `buffer.toString().substring(start,end)`. That creates a full `String` and then another substring — defeating the purpose of using the range overload.

There is also no need to call `subSequence(start,end)` just to pass it to the parser; the overload already accepts indices and the `CharSequence` directly. For custom `CharSequence` types or special views, calling `subSequence` may have its own allocation characteristics; rely on the implementation contract rather than guessing.

## 6. Signed int and long: the sign belongs to the parsed range itself

Decimal number strings can have an ASCII `+` or `-` sign **at the start of the parsed slice**:

```java
StringBuilder text = new StringBuilder("delta=-42;next=+17");

int delta = Integer.parseInt(text, 6, 9, 10); // -42
int next = Integer.parseInt(text, 15, 18, 10); // +17
```

Why pay attention to the range? For example, if `beginIndex` skips the `-` sign, it parses as **42**, corrupting the record's meaning even though Java throws no exception:

```java
int wrongMeaning = Integer.parseInt(text, 7, 9, 10); // 42
```

If there is only `+` or `-` with no digits, parsing fails with `NumberFormatException`. A sign in the **middle** of digits is also invalid.

Range bounds:

```java
StringBuilder minimum = new StringBuilder("value=-2147483648");
int min = Integer.parseInt(minimum, 6, minimum.length(), 10);
System.out.println(min == Integer.MIN_VALUE); // true
```

This is the negative boundary of `int`. If the numeric string falls outside `Integer.MIN_VALUE` to `Integer.MAX_VALUE`, the parser **rejects** it rather than silently wrapping around like a narrowing primitive cast.

For `long`:

```java
StringBuilder text = new StringBuilder("n=-9223372036854775808");
long min = Long.parseLong(text, 2, text.length(), 10);
System.out.println(min == Long.MIN_VALUE); // true
```

If you need to parse integers larger than the `long` range, use an appropriate arbitrary-precision integer strategy such as `BigInteger`, though **there is no matching range overload** in `BigInteger` corresponding to these four methods.

## 7. Bases other than 10: hexadecimal, binary, and signs

Pass `radix` explicitly:

```java
StringBuilder line = new StringBuilder("hex=7F;bits=101011");

int hex = Integer.parseInt(line, 4, 6, 16);  // 127
int bits = Integer.parseInt(line, 12, 18, 2); // 43
```

Accepted characters must be valid digits per `Character.digit(char, radix)`, aside from a leading ASCII sign in signed parsers. This means the parser is supported by the JDK for multiple radices and can accept certain Unicode digits, rather than **automatically restricting the whole token to ASCII**.

If your protocol requires **ASCII characters only**, validate that rule separately. Do not use `parseInt` succeeding as proof that a token strictly obeys a protocol's ASCII character set.

### Does not automatically recognize the 0x prefix

With radix 16, the parsed slice must be base-16 digits (optionally with a valid leading sign), such as `"FF"` or `"-FF"`, and does not automatically allow a `"0x"` prefix:

```java
StringBuilder s = new StringBuilder("value=0xFF");
// Integer.parseInt(s, 6, 10, 16); // NumberFormatException
int value = Integer.parseInt(s, 8, 10, 16); // 255
```

Here `[8,10)` skips the `0x` prefix. When a protocol standard allows multiple prefixes, you need to identify/strip the prefix during tokenization.

`Integer.decode(String)` supports its own prefix rules, yet **does not provide a `(CharSequence,begin,end,radix)` overload**. If choosing range-based parsing, the parser author determines the radix and digit span directly.

### Underscores and the L suffix are not numeric string syntax

`1_000` and `123L` may have meaning in *Java source-code numeric literals* (depending on placement), yet that does not mean `Integer.parseInt`/`Long.parseLong` accept `_` underscores or `L` suffixes in ordinary decimal strings:

```java
// Integer.parseInt(new StringBuilder("1_000"), 0, 5, 10); // NFE
// Long.parseLong(new StringBuilder("123L"), 0, 4, 10);     // NFE
```

Explicitly define the **runtime data** syntax instead of copying Java source-code numeric literal rules verbatim.

## 8. Unsigned parse: numbers above MAX_VALUE can be valid in 32/64 bits

The two unsigned overloads:

```java
Integer.parseUnsignedInt(seq, from, to, radix);
Long.parseUnsignedLong(seq, from, to, radix);
```

allow reading values from `0` to `2^32−1` or `0` to `2^64−1`. Yet Java still uses **32-bit `int`** or **64-bit `long`** as the return type, with no separate unsigned primitive.

Maximum-value example:

```java
StringBuilder u32Text = new StringBuilder("u=4294967295");
int bits32 = Integer.parseUnsignedInt(
        u32Text, 2, u32Text.length(), 10);

System.out.println(bits32);                      // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
```

Note that `System.out.println(bits32)` reads the bits as a signed `int` and prints `-1`; that **does not prove the unsigned parser is broken**. The same `0xFFFFFFFF` pattern means `4294967295` unsigned and `-1` signed.

For 64 bits:

```java
StringBuilder u64Text =
        new StringBuilder("u=18446744073709551615");

long bits64 = Long.parseUnsignedLong(
        u64Text, 2, u64Text.length(), 10);

System.out.println(bits64);                    // -1
System.out.println(Long.toUnsignedString(bits64));
// 18446744073709551615
```

Unsigned parsers do not accept negative numbers as signed negative integers: a `-` sign at the start of the slice is not a valid unsigned value. A leading ASCII plus sign may be accepted, yet never treat the token `"-1"` as an alternative spelling for unsigned max.

When working with unsigned bit patterns, APIs such as `Integer.compareUnsigned`, `Long.compareUnsigned`, `Integer.divideUnsigned`, and equivalents may be necessary. **Do not use signed comparison `bits32 < 0` to conclude an unsigned value is negative.**

## 9. Error-handling mechanism: three exception types to keep separate

For `parseInt(CharSequence,int,int,int)` and the corresponding overloads of `Long`:

| Case | Exception typically specified by the API | Example |
| --- | --- | --- |
| `CharSequence` is `null` | `NullPointerException` | `Integer.parseInt(null,0,1,10)` |
| Indices out of range or reversed | `IndexOutOfBoundsException` | `beginIndex=-1` |
| Empty range, invalid character, invalid radix, out-of-range value | `NumberFormatException` | `[0,0)`; `"12x"`; radix 1; `"2147483648"` when reading signed int |

**Notable detail:** the `String`-based overloaded method differs from the `CharSequence`-based overload in how the documentation specifies `null`. Do not treat them identically if your API needs to map exceptions to distinct error codes.

An illustrative example:

```java
StringBuilder buffer = new StringBuilder("x=12A");

try {
    Integer.parseInt(buffer, 2, 5, 10);
} catch (NumberFormatException ex) {
    System.out.println("Invalid decimal token");
}
```

If both token boundaries and data can be wrong, consider:

- Checking `beginIndex` and `endIndex` separately to catch internal parser bugs in locating tokens.
- Handling `NumberFormatException` as **invalid numeric data** or **out of range**.
- Handling `NullPointerException` as missing input character sequence if the business domain allows null sources.
- Never catching all `RuntimeException`s and returning 0: a parser error and a real zero are two situations that must never be conflated.

Avoid printing entire strings containing sensitive data into error logs. Log field names, indices, or a generic message instead of logging raw records verbatim.

## 10. Do you need to trim whitespace?

Integer parsers do not automatically trim whitespace surrounding a token:

```java
StringBuilder data = new StringBuilder("n= 42 ");
 // Integer.parseInt(data, 2, data.length(), 10); // NFE
```

If the data format permits leading/trailing whitespace, you can **shift the two bounds** before parsing without creating a substring.

Example for simple ASCII spaces:

```java
static int parseTrimmedAscii(CharSequence text, int from, int to) {
    while (from < to && text.charAt(from) == ' ') {
        from++;
    }
    while (to > from && text.charAt(to - 1) == ' ') {
        to--;
    }
    return Integer.parseInt(text, from, to, 10);
}
```

This is an **illustrative method** that does not self-validate all indices; it assumes the caller passes `0 <= from <= to <= text.length()`. It strips only ASCII space `' '` per a specific convention and does not handle all Unicode whitespace. If the contract permits tabs, CR/LF, or other Unicode whitespace, add an explicit policy such as checking code points or an appropriate helper.

**Do not trim arbitrarily** if the protocol forbids whitespace in tokens; in a strict parser, accepting an invalid token can be more serious than saving one allocation.

## 11. Do not replace the Parse API with a manual parser unless necessary

A direct digit-accumulating loop via `charAt` looks simple:

```java
int result = 0;
for (int i = from; i < to; i++) {
    result = result * 10 + (text.charAt(i) - '0');
}
```

Yet this illustrative snippet is **unsafe for production**:

- it does not verify every character lies within `'0'..'9'`;
- it does not support `+`/`-` signs;
- it does not check overflow when multiplying by 10 and adding digits;
- it does not check empty ranges or other radices;
- it does not implement `Character.digit` rules per the Java API;
- it can accept bad input and silently return an untrustworthy number.

The four built-in overloads implement standard parser semantics accurately. Only write a specialized optimized parser when you have an **explicit data contract**, overflow tests, and benchmarks on the concrete workload.

If data lives in a UTF-8 `byte[]` instead of a `CharSequence`, these overloads **do not parse byte arrays directly**. In that case decode to characters or use a vetted byte-level parser; never try to fake-cast a `byte[]` into a `CharSequence`.

## 12. Performance: reducing intermediate Strings without promising zero allocation

Conceptual comparison:

```java
StringBuilder builder = new StringBuilder("qty=12345;");
int from = 4, to = 9;

// Approach with intermediate string:
int a = Integer.parseInt(builder.substring(from, to));

// Approach using CharSequence slice:
int b = Integer.parseInt(builder, from, to, 10);
```

Both return `12345`. The second approach **does not require calling `substring`**; the method receives the character sequence and bounds directly. This can avoid allocating substring objects in caller code and helps repetitive parser loops.

Even so:

1. The API does not guarantee a specific allocation count across every implementation or error path.
2. The JIT can optimize away intermediate objects in some workloads; the old version is not guaranteed to always be slower.
3. Finding delimiters with `indexOf`/scanning still has a cost, and the scanning algorithm may dominate parsing time.
4. A parser running on a mutable `StringBuilder` shared across threads must ensure consistency; "fewer copies" does not mean "thread-safe."
5. Creating a substring is sometimes appropriate when a token must be retained long-term after the original buffer is overwritten or reused.

To measure how much improvement you get, use **JMH** or a properly designed Java benchmark, checking allocation rate and throughput with realistic data. Avoid timing a tiny loop with `System.nanoTime()` and drawing absolute conclusions because dead-code elimination, warmup, GC, and JIT can skew results.

## 13. Defining token boundaries accurately: content outside the range remains untouched

The range parser reads only the span you pass. For example:

```java
StringBuilder line = new StringBuilder("A=123;B=oops;");
int n = Integer.parseInt(line, 2, 5, 10);
System.out.println(n); // 123
```

The string `"oops"` outside the slice **does not need to be a valid number** because the parser never reads that far. This is a useful property when multiple fields of different kinds share the same record.

Conversely, if boundary positions are miscalculated, the parser can:

- include the delimiter and throw `NumberFormatException`;
- drop the minus sign and read a semantically wrong positive number;
- spill into the next field's characters;
- parse a slice of digits that is **valid yet not the intended token**, which is more dangerous than an obvious parse error.

Therefore **tokenization** (finding field start/end positions) must be designed and tested independently from **numeric conversion** (turning a valid token into a number). A good parse overload cannot substitute for a protocol-level parser.

## 14. Complete Java 17+ program

Create file **`CharSequenceRangeParsingDemo.java`**:

```java
public class CharSequenceRangeParsingDemo {

    private static int beginAfter(StringBuilder source, String field) {
        int keyIndex = source.indexOf(field);
        if (keyIndex < 0) {
            throw new IllegalArgumentException("Missing field: " + field);
        }
        return keyIndex + field.length();
    }

    private static int endOfField(StringBuilder source, int begin) {
        int separator = source.indexOf(";", begin);
        return separator >= 0 ? separator : source.length();
    }

    public static void main(String[] args) {
        StringBuilder record = new StringBuilder(
                "id=12345;delta=-42;hex=7F;u32=4294967295;"
              + "u64=18446744073709551615");

        int start = beginAfter(record, "id=");
        int end = endOfField(record, start);
        int id = Integer.parseInt(record, start, end, 10);
        System.out.println("id = " + id);

        start = beginAfter(record, "delta=");
        end = endOfField(record, start);
        int delta = Integer.parseInt(record, start, end, 10);
        System.out.println("delta = " + delta);

        start = beginAfter(record, "hex=");
        end = endOfField(record, start);
        int hex = Integer.parseInt(record, start, end, 16);
        System.out.println("hex = " + hex);

        start = beginAfter(record, "u32=");
        end = endOfField(record, start);
        int u32 = Integer.parseUnsignedInt(record, start, end, 10);
        System.out.println("u32 signed view = " + u32);
        System.out.println("u32 unsigned view = "
                + Integer.toUnsignedString(u32));

        start = beginAfter(record, "u64=");
        end = endOfField(record, start);
        long u64 = Long.parseUnsignedLong(record, start, end, 10);
        System.out.println("u64 signed view = " + u64);
        System.out.println("u64 unsigned view = "
                + Long.toUnsignedString(u64));

        StringBuilder signedLong =
                new StringBuilder("n=-9223372036854775808");
        long min = Long.parseLong(
                signedLong, 2, signedLong.length(), 10);
        System.out.println("long minimum = " + min);

        try {
            Integer.parseInt(new StringBuilder("x=12A"), 2, 5, 10);
        } catch (NumberFormatException ex) {
            System.out.println("bad digits: rejected");
        }

        try {
            Integer.parseInt(new StringBuilder("x=1"), -1, 3, 10);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("bad range: rejected");
        }

        try {
            Integer.parseInt(
                    new StringBuilder("n=2147483648"), 2, 12, 10);
        } catch (NumberFormatException ex) {
            System.out.println("signed int overflow: rejected");
        }

        StringBuilder extra = new StringBuilder("A=123;B=oops;");
        int first = Integer.parseInt(extra, 2, 5, 10);
        System.out.println("first field = " + first);
    }
}
```

Save the file with the exact class name, then compile and run:

```bash
javac CharSequenceRangeParsingDemo.java
java CharSequenceRangeParsingDemo
```

**Expected output:**

```text
id = 12345
delta = -42
hex = 127
u32 signed view = -1
u32 unsigned view = 4294967295
u64 signed view = -1
u64 unsigned view = 18446744073709551615
long minimum = -9223372036854775808
bad digits: rejected
bad range: rejected
signed int overflow: rejected
first field = 123
```

**Analysis:**

- `id`, `delta`, `hex` are parsed from regions inside a `StringBuilder` without allocating a substring for each numeric field.
- `u32`, `u64` illustrate how the same bit pattern can print `-1` when read as signed, yet have the unsigned max value when using `toUnsignedString`.
- `Long.parseLong` accepts `Long.MIN_VALUE` accurately without requiring conversion via `double` or `BigInteger`.
- Invalid characters trigger `NumberFormatException`; invalid index bounds trigger `IndexOutOfBoundsException`; signed overflow also triggers `NumberFormatException`.
- Field `B=oops` lies outside the parsed range of field `A`, so it does not affect the result `123`.

**Scope of illustration:** `beginAfter` in the example uses `StringBuilder.indexOf` for simplicity. It is **not a production-grade key/value parser**: if a field name is repeated, partially matches another key, or appears inside another value, naive searching can pick the wrong offset. Real applications must tokenize by delimiters and check full field names.

## 15. Common mistakes when optimizing integer parsing

| Misconception | Correct understanding |
| --- | --- |
| "`parseInt` only accepts String" | Java 9+ has overloads taking `CharSequence` and a range |
| "You only need to pass `sequence, from, to`" | This overload also requires `radix` |
| "`endIndex` is the position of the last character" | `endIndex` is **exclusive**, not including that character |
| "`beginIndex == endIndex` is an index error" | An empty range is index-valid, yet cannot parse a number |
| "The parser automatically strips whitespace" | You must strip or reject per the data specification |
| "`radix=16` automatically understands the 0x prefix" | No; handle prefixes and digit spans separately |
| "Runtime numeric strings understand underscores like Java literals" | `"1_000"` is generally not parsed by this overload |
| "Unsigned parse returns positive values in int/long" | Still returns `int`/`long` bit patterns, which can print as negative signed values |
| "A passed StringBuilder is safely snapshotted by the parser" | The JDK does not protect against a CharSequence mutated during parsing |
| "Not calling substring means zero allocation" | Only avoids caller-side substring allocation; does not guarantee 0 allocations |
| "Catching NumberFormatException covers all errors" | Null and invalid indices are distinct exception types |
| "Correct token bounds come automatically from the number parser" | You must still compute begin/end accurately per protocol |
| "Succeeding means the token is ASCII-only" | The JDK follows `Character.digit` rules, which can accept certain non-ASCII digits |
| "Every wrapper parse class has identical overloads" | Each API's signatures differ; check Javadoc |

## 16. Self-check exercises

**Exercise 1.** Given `StringBuilder s = new StringBuilder("x=987;y=1");`, write a call to parse `987` without creating a substring.

**Exercise 2.** Which indices does `Integer.parseInt(s, 2, 5, 10)` read?

**Exercise 3.** Given `StringBuilder s = new StringBuilder("n=-42;");`, what are the results of `Integer.parseInt(s, 2, 5, 10)` and `Integer.parseInt(s, 3, 5, 10)` respectively?

**Exercise 4.** Why does `Integer.parseInt(new StringBuilder("h=0xFF"), 2, 6, 16)` fail? How do you fix it without creating a substring?

**Exercise 5.** Given `StringBuilder s = new StringBuilder("u=4294967295");`, what type does `Integer.parseUnsignedInt(s, 2, s.length(), 10)` return, and how do you print `4294967295`?

**Exercise 6.** A token has leading/trailing spaces. Can you call `parseInt` directly over the full span and expect the parser to trim automatically?

**Exercise 7.** Which case throws `IndexOutOfBoundsException`: `begin=-1` or a valid range containing the letter `A` in radix 10? What error is the other case?

**Exercise 8.** Why does using `Integer.parseInt(builder,from,to,10)` not automatically prove a program runs faster than a version using `substring`?

**Exercise 9.** What bit pattern in `long` does `Long.parseUnsignedLong` produce for `18446744073709551615`? How do normal printing and `Long.toUnsignedString` differ?

**Exercise 10.** Is it safe for thread A to modify a `StringBuilder` while thread B calls `Integer.parseInt(builder,...)`?

### Answers and explanations

1. `Integer.parseInt(s, 2, 5, 10)`. Range `[2,5)` is `987`.
2. Reads indices `2, 3, 4`; does not read the character at index 5.
3. `-42` and `42` respectively; starting at index 3 drops the `-` sign, corrupting the meaning.
4. Token `"0xFF"` contains `x`, which is not a radix-16 digit; fix with `Integer.parseInt(s, 4, 6, 16)` to read `FF`.
5. Returns primitive `int` with all 32 bits set to 1, which prints as `-1` when signed; use `Integer.toUnsignedString(result)` to print `4294967295`.
6. No. You must decide whether whitespace is allowed by policy; if so, adjust bounds before parsing.
7. `begin=-1` causes `IndexOutOfBoundsException`; letter `A` invalid in radix 10 causes `NumberFormatException`.
8. JIT, tokenization, error handling, and data characteristics all matter. Range-based parsing removes caller-side substring creation, yet proving speed requires proper benchmarking.
9. All 64 bits set to 1, signed value `long=-1`; `Long.toUnsignedString(result)` prints `18446744073709551615`.
10. The parser provides no snapshot/consistency guarantee. You must synchronize, avoid modifying during parsing, or transfer buffer ownership per an appropriate protocol.

## 17. Checklist before using CharSequence overloads

1. **Identify the actual input:** `String`, `StringBuilder`, `StringBuffer`, `CharBuffer`, or a custom implementation?
2. **Pick the right API:** `Integer` or `Long`, signed or unsigned? Does the `(CharSequence,begin,end,radix)` overload exist?
3. **Maintain exact bounds:** `0 <= begin <= end <= length`, `end` exclusive, leading `+`/`-` signs not dropped.
4. **Indices count source characters:** do not pass UTF-8 byte offsets into a `CharSequence`.
5. **Specify radix and prefix policy** clearly; do not assume a radix-16 parser accepts `0x`.
6. **Define whitespace and valid characters:** ASCII-only or accepting Unicode digits per `Character.digit`?
7. **Review numeric ranges:** signed/unsigned `int`, `long`; out-of-range values are parse errors, not silent wraps in signed parsing.
8. **Handle exceptions:** null, bad indices, and bad data/radix/overflow are distinct failure modes.
9. **Ensure consistency:** avoid concurrently modifying a mutable `CharSequence` while parsing.
10. **Verify performance** with benchmarks if optimizing a hot path; never promise zero allocation or universal speedup.
11. **Retain tokens when needed:** if logic must keep text values after a buffer is reused, copying the token per data lifetime requirements is reasonable.
12. **Test boundary data:** empty strings, sign without digits, ±MAX/MIN, unsigned max, delimited tokens, prefixes, whitespace, bad radices, and out-of-range indices.

## API documentation

- [Java 17 – Integer: parseInt and parseUnsignedInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [Java 17 – Long: parseLong and parseUnsignedLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html)

**Key takeaway:** When you already have a `CharSequence` and know the `beginIndex/endIndex` of a numeric field, prefer the overload that parses directly on the **character subsequence** if the API supports it. This helps avoid creating unnecessary substring `String` objects, while still ensuring **correct indices, radix, value range, signedness, data consistency, and error semantics**. Saving allocations is only useful when the value is parsed **correctly**.
