# How valueOf(String) Differs from parse in Return Type in Java

## 1. Lesson objectives

When parsing a digit string into a Java integer, the two ways of writing below look alike:

```java
int number = Integer.parseInt("42");
Integer boxed = Integer.valueOf("42");
```

Both read the characters `"42"` into the numeric value forty-two, but their **compile-time return types differ**:

- `Integer.parseInt(String)` returns a **primitive `int`**.
- `Integer.valueOf(String)` returns a **wrapper object `Integer`**.

This is the core focus of **Java Core — Numbers / Integer Parsing**. For `Long`, `Short`, and `Byte`, the corresponding method pairs share the same return-type difference. Choosing a method is not merely a naming preference: it affects variable types, autoboxing/unboxing, overloaded method calls, generic/collection APIs, `null` handling, and code readability.

After this lesson, you will be able to:

1. Read method signatures to distinguish `parseInt`/`parseLong`/`parseShort`/`parseByte` from `valueOf(String)`.
2. Understand why `println` can print the same text even though the return types differ.
3. Choose the right parsing approach for primitive arithmetic or APIs requiring wrappers.
4. Recognize when the compiler performs automatic boxing/unboxing and the risk of `NullPointerException`.
5. Know that `valueOf(String)` **does not relax** string syntax, numeric range, radix, or exception handling compared to its corresponding parse method.
6. Properly use the overloads `valueOf(primitive)` and `valueOf(String, radix)` and distinguish `decode` and `parseUnsignedInt`.
7. Write runnable Java 17+ code and accurately predict stdout.

**Quick rule:** *parse* typically reads a string into a **primitive value**; *valueOf(String)* reads the same content into a **wrapper for that value**. Do not conclude that the latter creates a new numeric type or automatically alters the data format.

## 2. Method comparison table across the four integer families

| Family | String parse | Return type | String valueOf | Return type |
| --- | --- | --- | --- | --- |
| `byte` / `Byte` | `Byte.parseByte("127")` | `byte` | `Byte.valueOf("127")` | `Byte` |
| `short` / `Short` | `Short.parseShort("32767")` | `short` | `Short.valueOf("32767")` | `Short` |
| `int` / `Integer` | `Integer.parseInt("42")` | `int` | `Integer.valueOf("42")` | `Integer` |
| `long` / `Long` | `Long.parseLong("3000000000")` | `long` | `Long.valueOf("3000000000")` | `Long` |

The `String` parameter examples in the table above exclude the `null` case and assume valid strings within the target type's range. Both parsing approaches can throw `NumberFormatException` on invalid data.

### 2.1. The method signature determines the return type

Representative signatures:

```java
// Illustrative names and return types; these are not custom declarations to write.
static int Integer.parseInt(String s)
static Integer Integer.valueOf(String s)

static long Long.parseLong(String s)
static Long Long.valueOf(String s)

static short Short.parseShort(String s)
static Short Short.valueOf(String s)

static byte Byte.parseByte(String s)
static Byte Byte.valueOf(String s)
```

The snippet above is **signature notation for study**, not valid Java source code to place inside a class. The compiler knows the return type from the respective API, not from what the actual input string contains.

For example, `"42"` or `"-42"` does not change the return type; `Integer.parseInt` still returns `int`, and `Integer.valueOf` still returns `Integer`.

### 2.2. Distinguishing the type from printed output

```java
int primitive = Integer.parseInt("42");
Integer wrapper = Integer.valueOf("42");

System.out.println(primitive); // 42
System.out.println(wrapper);   // 42
```

Both lines print `42` because `println` has overloads and appropriate string-conversion mechanisms. You cannot infer from stdout that `primitive` and `wrapper` have the same **compile-time type**.

`primitive` stores an `int` value; `wrapper` is a reference to an `Integer` object carrying the value `42`. Wrappers are immutable and can participate in object-oriented APIs such as `equals`, `compareTo`, or generic collections.

## 3. Nearly identical parsed value, different return type

In terms of content semantics, `Integer.valueOf(String)` reads the string like `Integer.parseInt(String)` in radix 10, then returns an `Integer` holding the parsed value. Reading the API docs, you can picture it as:

```java
Integer result = Integer.valueOf(Integer.parseInt("42"));
```

In terms of numeric value, this is equivalent to `Integer.valueOf("42")` for valid strings. Do **not** interpret this as a guarantee on the number of allocated objects or object identity on every call: Java/the JVM may cache commonly used wrappers.

For invalid strings, both `Integer.parseInt(s)` and `Integer.valueOf(s)` **cannot produce a valid `int`/`Integer` result** and both throw `NumberFormatException`. `valueOf(String)` is not a "safe parse that returns null" or "ignore errors" method.

### 3.1. Wrappers do not automatically become null on parse failure

```java
// Integer.parseInt("abc");  // NumberFormatException
// Integer.valueOf("abc");   // NumberFormatException
```

The two calls above are **intentionally commented out** so the illustrative example does not halt the program. In an API required to return `null` on bad data, you must explicitly design a wrapper method and error policy, such as returning `OptionalInt`, `Optional<Integer>`, or a status-bearing result.

Do not arbitrarily substitute `null` for any invalid value, because `null` can cause the program to throw `NullPointerException` when unboxed to a primitive.

## 4. Boxing and unboxing can hide the difference

Java supports **autoboxing** from primitive to wrapper and **unboxing** from wrapper to primitive in permitted contexts.

```java
int a = Integer.parseInt("42");     // int -> int
Integer b = Integer.valueOf("42"); // Integer -> Integer

Integer c = Integer.parseInt("42"); // int -> Integer: boxing
int d = Integer.valueOf("42");     // Integer -> int: unboxing
```

All four lines compile. Yet this convenience makes it easy to overlook the actual return type:

| Right-hand side | Left-hand side | Conversion |
| --- | --- | --- |
| `parseInt(...)` = `int` | `int` | No boxing |
| `parseInt(...)` = `int` | `Integer` | Boxing |
| `valueOf(...)` = `Integer` | `Integer` | No unboxing |
| `valueOf(...)` = `Integer` | `int` | Unboxing |

Do not explain `int d = Integer.valueOf("42")` as proof that `valueOf` returns `int`. The compiler itself applied unboxing during the assignment.

### 4.1. Why pick the right API from the start?

If the goal is a loop summing `int` values, `parseInt` conveys that intent directly. If you want to pass an object into a `List<Integer>`, `Map<String,Integer>`, or a method taking `Integer`, `valueOf` makes the required wrapper type clear.

There is no need to optimize blindly: the JIT can optimize away boxing in some contexts, and `Integer.valueOf` may reuse objects. **What matters first are the data type, null semantics, value range, and readability**, rather than assuming every `valueOf` call necessarily creates a new allocation.

### 4.2. Null is a wrapper issue, not a valid parse result

```java
Integer boxed = null;
// int unboxed = boxed; // NullPointerException at runtime
```

There is no `null` value of type `int`. When an API taking/returning `Integer` may return `null` to represent "missing data", you must check before unboxing:

```java
Integer optional = null;
int fallback = optional == null ? 0 : optional.intValue();
```

Using `0` as a fallback is only appropriate if `0` carries a business-acceptable meaning. If `0` is a distinct meaningful value, keep the missing-data state in the data model rather than automatically defaulting to zero.

## 5. Observable differences in method overloading

When code has overloads `accept(int)` and `accept(Integer)`, the return type of `parseInt`/`valueOf` can determine which method is selected at compile time.

Save as **`ParseReturnTypes.java`**:

```java
public class ParseReturnTypes {
    static String describe(int value) {
        return "primitive int: " + value;
    }

    static String describe(Integer value) {
        return "wrapper Integer: " + value;
    }

    public static void main(String[] args) {
        int raw = Integer.parseInt("42");
        Integer boxed = Integer.valueOf("42");

        System.out.println(describe(raw));
        System.out.println(describe(boxed));
        System.out.println(raw == boxed);
        System.out.println(boxed.getClass().getSimpleName());
    }
}
```

Run:

```bash
javac --release 17 ParseReturnTypes.java
java ParseReturnTypes
```

**Exact stdout:**

```text
primitive int: 42
wrapper Integer: 42
true
Integer
```

Explanation:

1. `describe(raw)` selects the `describe(int)` overload.
2. `describe(boxed)` selects the `describe(Integer)` overload.
3. In the expression `raw == boxed`, `boxed` is unboxed to `int` for primitive value comparison; the result is true.
4. `boxed.getClass().getSimpleName()` returns the wrapper class name `Integer`.

**Note:** if `boxed == null`, the comparison expression `raw == boxed` can throw `NullPointerException` during unboxing. That does not occur in the current example because `Integer.valueOf("42")` returns a valid object.

## 6. Return types affect generic collections

Generic type arguments in Java cannot be primitives:

```java
// List<int> invalid;        // invalid
java.util.List<Integer> values = new java.util.ArrayList<>();

values.add(Integer.parseInt("12")); // int is boxed into Integer
values.add(Integer.valueOf("34"));  // already an Integer
```

Both `values.add` calls work. However:

- With `parseInt`, a boxing step may occur.
- With `valueOf`, the API receives an `Integer` directly.
- When `values.get(0)` is assigned to an `int`, unboxing can occur.

`valueOf(String)` is not "better" in every case. Choose consistently according to the data type's role. If you are building an API where data may be absent, `Integer` helps express nullability, though it also forces you to clearly define how `null` is handled.

### 6.1. `Integer` is an object; do not compare identity with `==`

```java
Integer x = Integer.valueOf("42");
Integer y = Integer.valueOf("42");

boolean equalValue = x.equals(y); // true
```

`x.equals(y)` compares **`Integer` values**. `x == y`, when both have type `Integer`, compares **object references** and can be affected by `valueOf` caching. Java guarantees caching a standard small range of values for certain wrappers, but application code should never rely on object identity to conclude two numbers have the same value.

This does not contradict `raw == boxed` in the earlier example: when one operand is a primitive `int`, Java applies unboxing/numeric equality. The types of **both** operands determine the meaning of the operator.

## 7. Same string syntax rules, same value range

### 7.1. Valid strings in decimal

`Integer.parseInt(String)` and `Integer.valueOf(String)` accept valid **signed decimal** integer string representations. Examples:

| Input | Numeric result | Meaning |
| --- | ---: | --- |
| `"42"` | 42 | Standard decimal |
| `"+42"` | 42 | Leading ASCII plus sign accepted |
| `"-42"` | −42 | ASCII minus sign |
| `"0"` | 0 | Zero |
| `"-0"` | 0 | Integers have no separate signed zero |
| `"00042"` | 42 | Leading zeros do not automatically switch to octal |
| `"2147483647"` | 2147483647 | `Integer.MAX_VALUE` |
| `"-2147483648"` | −2147483648 | `Integer.MIN_VALUE` |

The Java API allows digit characters recognized by `Character.digit(char,radix)` in the corresponding radix, not only ASCII in all contexts. However, the API does not automatically perform localization/normalization for every locale-specific number format; if input comes from users, you must specify the charset, accepted digits, and appropriate security constraints.

### 7.2. Invalid strings

The following inputs are not valid standard representations accepted by `Integer.parseInt(s)` or `Integer.valueOf(s)`:

| Input | Why invalid |
| --- | --- |
| `""` | Empty string |
| `" "`, `" 42 "` | Contains whitespace; the methods do not automatically trim |
| `"42.0"` | Contains a decimal point, no longer an integer string |
| `"1e3"` | Exponent notation belongs to floating-point numbers, not signed integer strings |
| `"1_000"` | Underscores are only accepted by Java source grammar in valid positions within literals, not by this string parser |
| `"0xFF"` | Hex prefix is not automatically recognized by the default-radix overload |
| `"+"`, `"-"` | Sign only, missing digits |
| `"2147483648"` | Exceeds `Integer.MAX_VALUE` |
| `"-2147483649"` | Less than `Integer.MIN_VALUE` |

`Integer.parseInt(null)` and `Integer.valueOf((String)null)` also do not produce valid values; with the `String` overload, the JDK reports `NumberFormatException`. With `null` and multiple overloads, pay attention to **which signature is selected** and the exception documented for that signature.

### 7.3. String literals and source literals differ

```java
int a = 1_000;                 // valid: source code integer literal
// int b = Integer.parseInt("1_000"); // runtime NumberFormatException
```

`0xFF` written in Java source code is a **base-16 integer literal**. But `"0xFF"` is a **string containing the characters** `0`, `x`, `F`, `F` and is not automatically parsed according to source literal grammar.

**Do not try to solve this by switching `parseInt` to `valueOf`:** both have the same fundamental restrictions on input strings. Choose a radix overload or the `decode` method with the appropriate contract.

## 8. Overloads with radix: `parseInt(String,int)` and `valueOf(String,int)`

Both API families allow specifying a base `radix`:

```java
int primitiveHex = Integer.parseInt("FF", 16);       // 255
Integer boxedHex = Integer.valueOf("FF", 16);       // Integer(255)

int primitiveBinary = Integer.parseInt("101010", 2); // 42
Integer boxedBinary = Integer.valueOf("101010", 2); // Integer(42)
```

The difference **is still only the return type**, while the rules for converting the string in that radix are identical.

The APIs accept valid radices from `Character.MIN_RADIX` (2) to `Character.MAX_RADIX` (36). With radix 16, characters `A`–`F` represent digits 10–15 (case-insensitive within the valid range). A leading `+`/`-` sign is allowed for signed parsing; a sign in the middle of the string is not.

Points to note:

- `Integer.parseInt("FF",16)` → 255.
- `Integer.parseInt("-FF",16)` → −255.
- `Integer.valueOf("FF",16)` → wrapper `Integer` with value 255.
- `Integer.parseInt("0xFF",16)` does **not** automatically strip the `0x` prefix.
- `Integer.parseInt("010")` defaults to radix 10 → 10; it does not infer octal from the leading zero.
- An invalid radix, a character not valid in the radix, or a result outside the `int` range all lead to `NumberFormatException` in the `String` overloads.

### 8.1. `decode(String)` has a different job

`Integer.decode("0xFF")` accepts the `0x` prefix to parse hex, `Integer.decode("#FF")` also uses hex convention, and a number starting with `0` can be interpreted as octal. For example:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
System.out.println(Integer.decode("0xFF"));  // 255
```

`decode` returns **`Integer`**, but is not synonymous with `valueOf(String)`: they differ in **accepted string grammar**. Depending on data requirements, using an explicit radix is usually less surprising than inferring the base from a prefix or leading zero.

`Long.decode`, `Short.decode`, and `Byte.decode` carry corresponding meanings within each class's type range. If a system receives numeric codes following a custom protocol format, you should explicitly specify the conventions (base, prefix, sign, value range) rather than mixing multiple parsing methods haphazardly.

## 9. Value ranges of `Byte`, `Short`, `Integer`, and `Long`

The same string is only accepted if its value lies within the **range of the parsing type**:

| API | Signed range |
| --- | --- |
| `Byte.parseByte` / `Byte.valueOf` | −128 to 127 |
| `Short.parseShort` / `Short.valueOf` | −32768 to 32767 |
| `Integer.parseInt` / `Integer.valueOf` | −2147483648 to 2147483647 |
| `Long.parseLong` / `Long.valueOf` | −9223372036854775808 to 9223372036854775807 |

`Byte.parseByte("128")` throws `NumberFormatException`; so does `Byte.valueOf("128")`. `Integer.parseInt("3000000000")` exceeds the `int` range, whereas `Long.parseLong("3000000000")` is valid and returns `long`. With `Long.valueOf("3000000000")`, that value is boxed into a `Long`.

Do not solve a range error by parsing first through a type that is too small and then casting to a larger type: once `Integer.parseInt` fails because the string is out of range, casting the result (which was never produced) accomplishes nothing. **Choose the appropriate type before parsing.**

### 9.1. Special case: unsigned parsing

`Integer.parseUnsignedInt(String)` reads an unsigned 32-bit value from string form, yet still returns a **primitive `int`** containing the same 32-bit pattern.

```java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                           // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
```

The `-1` on the first line is the **signed reading** of the all-1s bit pattern; the next line interprets the **same bit pattern** as unsigned. No separate `unsigned int` primitive is created.

`Integer.valueOf("4294967295")` cannot replace `parseUnsignedInt` because it uses standard signed parsing and the value exceeds the signed `int` range. If you need a wrapper for the unsigned bits result, write:

```java
Integer bitsObject = Integer.valueOf(
        Integer.parseUnsignedInt("4294967295"));
```

For 64 bits, `Long.parseUnsignedLong` has the same meaning and returns `long`. Clearly define the system's contract before displaying or comparing signed/unsigned values.

## 10. Complete program: numeric values, wrappers, and ranges

Save as **`IntegerParsingTypes.java`**:

```java
public class IntegerParsingTypes {
    public static void main(String[] args) {
        int primitive = Integer.parseInt("42");
        Integer boxed = Integer.valueOf("42");

        System.out.println(primitive);
        System.out.println(boxed.getClass().getSimpleName());
        System.out.println(primitive == boxed);

        long large = Long.parseLong("3000000000");
        Long boxedLong = Long.valueOf("3000000000");
        System.out.println(large);
        System.out.println(boxedLong.getClass().getSimpleName());

        System.out.println(Byte.parseByte("127"));
        System.out.println(Short.valueOf("32767"));

        System.out.println(Integer.valueOf("42")
                .equals(Long.valueOf("42")));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 IntegerParsingTypes.java
java IntegerParsingTypes
```

**Exact stdout:**

```text
42
Integer
true
3000000000
Long
127
32767
false
```

Analysis:

1. `primitive` is `int`, `boxed` is `Integer`; they represent the same arithmetic quantity `42`.
2. Comparing `primitive == boxed` unboxes `boxed` to `int`.
3. `Long.parseLong`/`Long.valueOf` have return types `long`/`Long`, suitable when `3000000000` exceeds the `int` range.
4. `Byte.parseByte` returns `byte`; `Short.valueOf` returns the wrapper `Short`.
5. `Integer.valueOf("42").equals(Long.valueOf("42"))` is false because `Integer.equals` only accepts the same `Integer` class with the same value; having the same number 42 does not mean wrappers of different types are `equals`.

## 11. Complete program: radix, decode, and unsigned

Save as **`ParsingRadix.java`**:

```java
public class ParsingRadix {
    public static void main(String[] args) {
        System.out.println(Integer.parseInt("FF", 16));
        System.out.println(Integer.valueOf("FF", 16));
        System.out.println(Integer.parseInt("-FF", 16));

        System.out.println(Integer.parseInt("010"));
        System.out.println(Integer.decode("010"));
        System.out.println(Integer.decode("0xFF"));

        int unsignedBits =
                Integer.parseUnsignedInt("4294967295");
        System.out.println(unsignedBits);
        System.out.println(
                Integer.toUnsignedString(unsignedBits));

        System.out.println(Integer.parseInt("+42"));
        System.out.println(Integer.valueOf("-0"));
    }
}
```

Run:

```bash
javac --release 17 ParsingRadix.java
java ParsingRadix
```

**Exact stdout:**

```text
255
255
-255
10
8
255
-1
4294967295
42
0
```

The `decode` method differs from `parseInt` in how it recognizes prefixes and leading zeros. The `parseUnsignedInt` method differs from `parseInt` in the accepted data range, **not** by changing the primitive type of the result. All `println` calls here print values rather than showing on their own whether an expression has type `int` or `Integer`; to verify the type, inspect the signature or variable declaration.

## 12. Validating parse errors properly

With data from user input, files, APIs, or databases, `NumberFormatException` is part of the contract. Sample code should define a policy when encountering invalid input rather than silently returning `0` by default.

Save as **`SafeIntegerParsing.java`**:

```java
public class SafeIntegerParsing {
    static void show(String raw) {
        try {
            int result = Integer.parseInt(raw);
            System.out.println("ok: " + result);
        } catch (NumberFormatException ex) {
            System.out.println("invalid: [" + raw + "]");
        }
    }

    public static void main(String[] args) {
        show("42");
        show(" 42 ");
        show("42.0");
        show("1_000");
        show("2147483648");
        show("");
    }
}
```

Run:

```bash
javac --release 17 SafeIntegerParsing.java
java SafeIntegerParsing
```

**Exact stdout:**

```text
ok: 42
invalid: [ 42 ]
invalid: [42.0]
invalid: [1_000]
invalid: [2147483648]
invalid: []
```

You can replace `Integer.parseInt(raw)` with `Integer.valueOf(raw)` and assign the result to `Integer`; **invalid inputs remain invalid**. Catching the exception in the example is meant to clarify the boundary between valid and invalid input, not to recommend silently swallowing errors in real applications.

### 12.1. When should you `trim` or `strip`?

If the contract **allows leading and trailing whitespace**, normalize deliberately before parsing:

```java
String input = " 42 ";
int number = Integer.parseInt(input.strip()); // 42
```

If the contract forbids whitespace, **do not normalize and silently accept invalid input**. `strip` handles Unicode whitespace according to `Character.isWhitespace`, which does not mean every character that looks like a space is removed. `trim` has different rules; choose the approach based on the data format.

If the string has thousands separators, currency symbols, or locale-formatted numbers, `parseInt`/`valueOf` is not a general-purpose format parser. You need to define the format or use an appropriate, controlled tool.

### 12.2. Avoid using exceptions for every row in bulk data without evaluation

For clean, pre-validated data sources, calling parse directly is reasonable. For external data that may contain many errors, use a validation layer and return status-bearing results; consider the cost of creating exceptions if parsing millions of invalid records. However, **do not write an ad-hoc custom number parser** just to avoid exceptions unless you genuinely need specialized performance.

## 13. `valueOf` overloads do not only accept String

One source of confusion is that the name `valueOf` has multiple overloads:

```java
Integer fromNumber = Integer.valueOf(42);   // valueOf(int) -> Integer
Integer fromText = Integer.valueOf("42");  // valueOf(String) -> Integer
Integer fromHex = Integer.valueOf("2A", 16); // valueOf(String,int) -> Integer
```

These methods take **different inputs** yet all return `Integer`.

`Integer.valueOf(42)` does not parse any characters: it takes an existing primitive `int` to create/obtain a wrapper. `Integer.valueOf("42")` parses a `String`. `Integer.valueOf("2A",16)` parses a string in radix 16.

Do not write `Integer.parseInt(42)` because `parseInt` requires a string (or a `CharSequence` overload with indices/radix), and has no simple overload accepting an `int`.

### 13.1. Methods on CharSequence

In Java 17, `Integer.parseInt(CharSequence s, int beginIndex, int endIndex, int radix)` and `Long.parseLong(CharSequence,beginIndex,endIndex,radix)` allow parsing a slice of a `CharSequence` without necessarily creating a substring manually.

Example:

```java
CharSequence line = "id=0042;";
int id = Integer.parseInt(line, 3, 7, 10); // 42
```

The snippet above is a code fragment; `beginIndex` is 0-based and `endIndex` is **exclusive**. `"id=0042;"` has four digits at indices 3..6. You must control the indices and ensure the input is not mutated concurrently if the `CharSequence` is mutable. This is still a **parse returning primitive `int`**; there is no corresponding `Integer.valueOf(CharSequence,begin,end,radix)` overload in Java 17.

## 14. Comparing `valueOf` with legacy wrapper constructors

In Java 17, the constructors `new Integer(String)` and `new Integer(int)` are **deprecated for removal**. For new applications, prefer:

- `Integer.parseInt("42")` when you need an `int`.
- `Integer.valueOf("42")` when you need an `Integer` from a `String`.
- `Integer.valueOf(42)` when you already have an `int` and want to use it as a wrapper.

`valueOf` can reuse cached objects, whereas the legacy constructors create a new object, but **do not use this to write logic relying on object identity**. The goal is clear API usage and following JDK recommendations, not arbitrary optimization using `==` on wrappers.

### 14.1. Why not use `new Integer("42")` to bypass the cache?

Some legacy code intentionally created two distinct objects so `a == b` would return false. That is not a proper value-comparison mechanism: `==` on two references checks identity; `equals` is what checks value equality within the same wrapper class. Creating new objects just to manipulate `==` makes code depend on unnecessary implementation details.

## 15. Generalizing carefully to avoid wrong conclusions about all parse/valueOf classes

**Within the integer topic**, `Byte`, `Short`, `Integer`, and `Long` have `parse...` methods returning primitives and `valueOf(String)` returning wrappers. However, do not mechanically apply the rule that "every Java class has `parseX` and `valueOf(String)` with the same rules."

For example:

- `Double.parseDouble(String)` returns primitive `double`; `Double.valueOf(String)` returns wrapper `Double`.
- `Float.parseFloat(String)` returns primitive `float`; `Float.valueOf(String)` returns wrapper `Float`.
- `Boolean.parseBoolean(String)` returns primitive `boolean` and `Boolean.valueOf(String)` returns `Boolean`, **but the string rules differ from integers**: only `"true"` (case-insensitive) is treated as true, other strings yield false, and neither throws `NumberFormatException` like the integer parsers.
- `BigInteger` does not have a corresponding `parseBigInteger(String)` or `valueOf(String)`; the standard way is `new BigInteger(String)`, while `BigInteger.valueOf(long)` takes a primitive `long`.
- `BigDecimal` has a constructor from a string to preserve exact decimal numbers in supported formats; `BigDecimal.valueOf(long)` or `valueOf(double)` has a different contract, not a `valueOf(String)` overload.

You must read the **signature and documentation of the exact class/overload**. The name "parse" or "valueOf" is a useful hint, not a substitute for type checking.

## 16. Common mistakes in code reviews

1. **"`Integer.valueOf("12")` returns `int`."** False: it returns `Integer`. Unboxing on assignment can make you think the opposite.
2. **"`parseInt` cannot be added to `List<Integer>`."** False: the compiler can autobox. However, `List<int>` is invalid.
3. **"`valueOf(String)` automatically returns null if the string is invalid."** False: it throws `NumberFormatException`.
4. **"`valueOf` understands `"0xFF"` while `parseInt` does not."** False for the radix-10 overload; use `decode` or pass `"FF",16` when appropriate.
5. **"The string `"1_000"` is valid because the literal `1_000` is valid."** False: Java source literals and `String` contents have different grammars.
6. **"`Integer.parseInt("010")` interprets octal."** False: it defaults to decimal 10; `Integer.decode("010")` is what has the octal convention.
7. **"If it is `Integer`, then any number can be null."** A wrapper reference variable can hold `null`, but `valueOf("42")` does not return null; null usually comes from another source.
8. **"`Integer.valueOf("42") == Integer.valueOf("42")` is always the right way to compare numbers."** Do not use reference identity. Use `equals` for the same wrapper type or compare primitives.
9. **"Mixing `Integer` and `Long` with the same value will be `equals` true."** False: wrapper equality distinguishes classes.
10. **"After parsing an int that is too large, casting to `long` will fix it."** False: the error occurs inside `parseInt` before any result is produced.
11. **"`parseUnsignedInt` returns a separate unsigned primitive."** False: it is still `int`, with bits interpreted as unsigned via companion APIs.
12. **"Any whitespace is automatically ignored."** False: `parseInt` and `valueOf` do not automatically trim.
13. **"`Integer.parseInt(null)` returns 0 by default."** False: there is no valid value; the `String` overload throws `NumberFormatException`.
14. **"`Integer.valueOf(42)` and `Integer.valueOf("42")` both parse strings."** False: the overload taking `int` does not parse, while the overload taking `String` does.
15. **"`Integer.parseInt` can read a decimal `"42.0"` and drop the fractional part."** False: `"42.0"` is not a valid integer string; casting a `double` and parsing an integer are two different operations.

## 17. Exercises with explained answers

### Exercise 1 — What type is returned?

Choose the compile-time type of `Integer.parseInt("7")`, `Integer.valueOf("7")`, `Long.parseLong("7")`, and `Long.valueOf("7")`.

**Answer:** `int`, `Integer`, `long`, `Long`, respectively. The digits inside the string do not determine the return type.

### Exercise 2 — Where does boxing happen?

Why is `Integer x = Integer.parseInt("10");` still valid?

**Answer:** `parseInt` returns `int`; the compiler applies boxing to assign it to `Integer`. `parseInt` does not change its signature just because the left-hand side is a wrapper.

### Exercise 3 — Where does unboxing happen?

Why is `int x = Integer.valueOf("10");` valid?

**Answer:** `valueOf(String)` returns `Integer`; the compiler unboxes it to `int` upon assignment. If `null` arrives from another source during unboxing, the program can throw NPE; `valueOf("10")` is not that source of null.

### Exercise 4 — Invalid string syntax

Are `Integer.parseInt("1_000")` and `Integer.valueOf("1_000")` accepted?

**Answer:** no. Underscores belong to literal syntax in Java source code, not to the integer string format accepted by these two methods.

### Exercise 5 — Hex and radix

How do you obtain the value 255 from the string `"FF"` using both parse and valueOf?

**Answer:** `int p = Integer.parseInt("FF",16);` and `Integer v = Integer.valueOf("FF",16);`. Both yield the numeric value 255, with different result types.

### Exercise 6 — Decode

What values do `Integer.parseInt("010")` and `Integer.decode("010")` return?

**Answer:** `10` and wrapper `Integer` with value `8`, because `decode` interprets a leading zero as octal, whereas `parseInt` defaults to decimal.

### Exercise 7 — Value range

What happens with `Byte.valueOf("128")`, `Integer.parseInt("3000000000")`, and `Long.parseLong("3000000000")`?

**Answer:** the first two calls throw `NumberFormatException` because they exceed the range; the third call is valid and returns `long` 3000000000.

### Exercise 8 — Comparing wrappers

What does `Integer.valueOf("42").equals(Long.valueOf("42"))` return?

**Answer:** false because they are different wrapper classes, even though they represent the same mathematical quantity. If you genuinely need cross-type numeric equality, you must define a custom type-conversion and data-range policy.

### Exercise 9 — Unsigned

What type does `Integer.parseUnsignedInt("4294967295")` return, and what signed value does it print?

**Answer:** returns an `int` with all bits set to 1; `System.out.println` on `int` prints `-1`. `Integer.toUnsignedString(bits)` prints `4294967295`.

### Exercise 10 — Null

If `String text = null;`, do `Integer.parseInt(text)` and `Integer.valueOf(text)` return 0/null?

**Answer:** no; the overloads taking `String` throw `NumberFormatException`. `Integer.valueOf((String)null)` is different from an `Integer` variable that already holds `null`.

### Exercise 11 — Method overloading

Given two methods `show(int)` and `show(Integer)`. Which method does `show(Integer.parseInt("9"))` select, and which does `show(Integer.valueOf("9"))` select?

**Answer:** the first selects `show(int)`, the second selects `show(Integer)`. The expression type at the call site determines the matching overload.

### Exercise 12 — API design

For a method summing a million integers and a method returning data that may be in an unentered state, which types should be used?

**Answer:** the arithmetic sum can use primitive `int`/`long` depending on the range; the field with a missing state should have a dedicated model such as nullable `Integer`, `OptionalInt`, or a status record. You cannot decide based solely on speed while ignoring null/error requirements.

### Exercise 13 — Decimal and octal

Why is `Integer.valueOf("010")` not the same as `Integer.decode("010")`?

**Answer:** `valueOf(String)` applies signed decimal just like `parseInt(String)`, yielding 10; `decode` interprets the leading-zero prefix under its own rules, yielding 8.

### Exercise 14 — Does switching to a wrapper solve out-of-range values?

The value `"2147483648"` exceeds `Integer.MAX_VALUE`. Can `Integer.valueOf("2147483648")` hold it because it is an object?

**Answer:** no. `Integer` wraps the exact value range of `int`. Use `Long.parseLong`/`Long.valueOf` or `BigInteger` if the data range requires it; do not assume a wrapper increases numeric width.

## 18. Checklist and standard documentation

- [ ] I accurately recall `parseInt(String) -> int` and `valueOf(String) -> Integer`.
- [ ] I can cross-reference `parseLong/valueOf`, `parseShort/valueOf`, and `parseByte/valueOf`.
- [ ] I can identify where boxing/unboxing occurs when choosing a target variable type.
- [ ] I know wrappers can be used in generic collections, whereas `List<int>` is invalid.
- [ ] I do not use `==` between two wrapper references to check value equality.
- [ ] I understand both parse and valueOf can throw `NumberFormatException` on invalid input.
- [ ] I check the signed range before choosing `byte`, `short`, `int`, or `long`.
- [ ] I use the proper radix overload when a string is not decimal.
- [ ] I do not confuse `decode` with `parseInt`/`valueOf(String)`.
- [ ] I know parseUnsignedInt still returns `int` and requires unsigned APIs for corresponding display/comparison.
- [ ] I distinguish Java source literals containing underscores/prefixes from strings passed to a parser.
- [ ] I know `valueOf(int)` differs from `valueOf(String)` in its input.
- [ ] I have run all three Java 17+ programs and tested additional empty, whitespace, out-of-range, and invalid-radix inputs.
- [ ] I clearly document the error-parsing contract and handle `null` before unboxing.

**Official Java SE 17 documentation:**

- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `valueOf`, `decode`, `parseUnsignedInt`, `toUnsignedString`.
- [Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `parseLong`, `valueOf`, `parseUnsignedLong`.
- [Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `parseByte`, `valueOf`.
- [Short API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html): `parseShort`, `valueOf`.
- [Character API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `digit` and the radix concept.
- [JLS 17, `5.1.7–`5.1.8 Boxing and Unboxing Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7): boxing/unboxing rules.
- [BigInteger API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): converting strings to arbitrary-precision integers when exceeding primitive ranges.

**Conclusion:** when reading an integer string, `parse...` and `valueOf(String)` largely share the same interpretation of the **numeric string**, but differ in **return type**. Prefer primitives when the API needs primitive values, use wrappers when the model requires objects/generics/nullability, and remember that syntax errors, range limits, radices, and data-handling policies are not automatically "solved" by `valueOf`.