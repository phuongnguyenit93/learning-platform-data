# Using valueOf Instead of Deprecated Wrapper Constructors in Java

> **Java core – numbers · Number and wrappers**  
> **Objective:** Properly replace deprecated wrapper constructor calls with `valueOf`, distinguish `valueOf` from `parseXxx` and autoboxing, understand why not to rely on wrapper object identity, and avoid mistakes in parsing, comparing, and unboxing.

## 1. The Problem: Wrappers Should Not Be Created with Legacy Constructors

Java has **primitive types** used to store numbers and boolean/character values, along with corresponding object **wrapper classes**:

| Primitive | Wrapper | Creation method from primitive |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf(byte)` |
| `short` | `Short` | `Short.valueOf(short)` |
| `int` | `Integer` | `Integer.valueOf(int)` |
| `long` | `Long` | `Long.valueOf(long)` |
| `float` | `Float` | `Float.valueOf(float)` |
| `double` | `Double` | `Double.valueOf(double)` |
| `char` | `Character` | `Character.valueOf(char)` |
| `boolean` | `Boolean` | `Boolean.valueOf(boolean)` |

Previously you might encounter syntax like:

```java
// Legacy style: avoid in modern Java source code.
// Integer boxed = new Integer(42);
// Long count = new Long(100L);
// Double rate = new Double(2.5);
// Boolean enabled = new Boolean(true);
```

The **public constructors** of these wrappers were marked **deprecated for removal** starting in Java 9; in Java 17, code using them can trigger compiler warnings. Being *deprecated* **does not mean** the constructors have vanished in every JDK: legacy code may still compile/run on some versions, yet that style is no longer recommended and should not be used in new code.

Recommended style:

```java
Integer boxed = Integer.valueOf(42);
Long count = Long.valueOf(100L);
Double rate = Double.valueOf(2.5);
Boolean enabled = Boolean.valueOf(true);
```

**Main reasons:**

1. `valueOf` is a **static factory method** aligned with modern API conventions.
2. Factory methods **can reuse** existing wrapper instances instead of forcing a new object allocation on every call.
3. Wrappers are **value-based classes**: what matters is the **wrapped value**, not reference identity or locking on the object.
4. This style avoids depending on constructors slated for removal in the future.

**Short takeaway:** When you genuinely need an `Integer` object, use `Integer.valueOf(42)` or autoboxing where appropriate; **do not** use `new Integer(42)`.

## 2. What Are Wrappers Used For When Primitives Already Exist?

Primitives are usually simpler and more efficient for arithmetic:

```java
int quantity = 42;
double price = 19.5;
boolean available = true;
```

However, some APIs and data structures require **reference objects**:

```java
import java.util.List;

List<Integer> counts = List.of(1, 2, 3);
Integer optionalCount = null;
Number number = Integer.valueOf(42);
```

Common scenarios include:

- Type arguments for collections/generics: `List<Integer>`, `Map<String, Long>`; Java generics cannot directly use `List<int>`.
- APIs accepting `Object`, `Number`, or related interfaces rather than primitives.
- Representing a *missing value* state with a `null` reference, when the data contract permits.
- Using class methods such as `Integer.compare`, `Integer.toHexString`, `Double.isFinite`, or `intValue()`.

The numeric wrappers `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` are subclasses of `java.lang.Number`. `Character` and `Boolean` **do not** extend `Number`; therefore, do not treat every wrapper as a `Number`.

Wrappers are **immutable** objects: you cannot change the internal value of an already created `Integer`. Assigning another wrapper to a variable only makes the variable reference the new value.

## 3. valueOf Is a Factory Method, Not a Constructor

Compare the two ways of expressing intent:

```java
// Legacy style — deprecated constructor:
 // Integer oldStyle = new Integer(42);

// Modern style — static factory:
Integer modern = Integer.valueOf(42);
```

A constructor like `new Integer(42)` demands creating a new object. By contrast, `Integer.valueOf(42)` returns a reference to an `Integer` with value 42; whether that reference points to a reused object or a newly created one **is not something business logic should depend on**.

Some factories have explicit caching rules. In Java, for instance, `Integer.valueOf(int)` guarantees caching values **from −128 to 127**; implementations may cache additional values outside that range. Keep in mind:

- **Caching is an optimization/factory-specification detail, not a way to compare numbers.**
- Do not assume every `Integer.valueOf(1000)` returns the same object or always returns distinct objects.
- Do not use wrapper identity to represent distinct states.
- Do not synchronize (`synchronized`) on wrappers: wrappers are considered **value-based**, and identity-dependent operations create synchronization risks.

In particular, **`valueOf` is not a "trick to get a fresh object every time."** If your program needs distinct identity, create a dedicated domain object class instead of trying to use wrappers as identity tokens.

## 4. How to Replace Each Deprecated Constructor

When updating legacy Java code, refer to the following table:

| Legacy constructor (avoid) | Recommended replacement | Notes |
| --- | --- | --- |
| `new Byte((byte) 7)` | `Byte.valueOf((byte) 7)` | `byte` type has range −128..127 |
| `new Short((short) 300)` | `Short.valueOf((short) 300)` | Does not alter narrowing rules |
| `new Integer(42)` | `Integer.valueOf(42)` | Do not use `==` to compare values |
| `new Long(42L)` | `Long.valueOf(42L)` | Result is wrapper `Long` |
| `new Float(1.25f)` | `Float.valueOf(1.25f)` | Use `f` suffix for `float` literals |
| `new Double(1.25)` | `Double.valueOf(1.25)` | Accepts primitive `double` |
| `new Character('A')` | `Character.valueOf('A')` | Accepts one `char`, not a string |
| `new Boolean(true)` | `Boolean.valueOf(true)` | Can return constant `Boolean.TRUE` |

Constructors taking **strings** should also be replaced with the corresponding factory or parser:

```java
// Avoid:
// Integer n = new Integer("123");
// Long id = new Long("123456789");
// Double d = new Double("1.25");
// Boolean flag = new Boolean("true");

// Replace with:
Integer n = Integer.valueOf("123");
Long id = Long.valueOf("123456789");
Double d = Double.valueOf("1.25");
Boolean flag = Boolean.valueOf("true");
```

There is no valid reason to replace a wrapper constructor by writing `new Integer(Integer.parseInt(text))`: the `new` step still constructs an object via a deprecated API. When a wrapper is needed, call `Integer.valueOf(text)` directly.

## 5. valueOf with Primitive Values vs. Strings Are Two Different Cases

`Integer.valueOf` has multiple overloads:

```java
Integer fromInt = Integer.valueOf(123);        // primitive int -> wrapper Integer
Integer fromText = Integer.valueOf("123");    // String -> wrapper Integer
Integer fromHex = Integer.valueOf("FF", 16);  // base-16 String -> Integer 255
```

In the second and third examples, the method must **parse the string**. An invalid string can throw `NumberFormatException`. In the first example, the input type is already a valid primitive, so no string-parsing step occurs.

Other wrapper examples:

```java
Byte byteValue = Byte.valueOf("127");
Short shortValue = Short.valueOf("-123");
Long longValue = Long.valueOf("9000000000");
Float floatValue = Float.valueOf("1.25");
Double doubleValue = Double.valueOf("1.25");
Boolean boolValue = Boolean.valueOf("TrUe");
Character charValue = Character.valueOf('J');
```

**There is no** `Character.valueOf(String)` accepting an arbitrary string. `Character.valueOf` takes a single `char`, meaning one UTF-16 code unit. If you need to handle Unicode characters outside the BMP, you may need an `int` **code point** or `String`, rather than arbitrarily taking `charAt(0)` and treating it as a whole character.

## 6. valueOf Differs from parseXxx in Return Type

For integer strings:

```java
String text = "42";

int primitive = Integer.parseInt(text); // int
Integer wrapper = Integer.valueOf(text); // Integer
```

For floating-point strings:

```java
double primitive = Double.parseDouble("1.25"); // double
Double wrapper = Double.valueOf("1.25");        // Double
```

Quick-reference table:

| Call | Input | Return type |
| --- | --- | --- |
| `Integer.parseInt("42")` | String | `int` |
| `Integer.valueOf("42")` | String | `Integer` |
| `Long.parseLong("42")` | String | `long` |
| `Long.valueOf("42")` | String | `Long` |
| `Double.parseDouble("1.25")` | String | `double` |
| `Double.valueOf("1.25")` | String | `Double` |
| `Float.parseFloat("1.25")` | String | `float` |
| `Float.valueOf("1.25")` | String | `Float` |
| `Boolean.parseBoolean("true")` | String | `boolean` |
| `Boolean.valueOf("true")` | String | `Boolean` |

Guidance on choosing:

- Performing ordinary arithmetic where variables are primitives and objects are not needed: prefer **`parseXxx`** and stay with primitives.
- APIs/collections requiring a wrapper: use **`valueOf`** to obtain the right object type.
- Already holding a primitive while an API requires a wrapper: use **`valueOf(primitive)`** or **autoboxing**.
- Already holding a wrapper and needing a primitive: use **unboxing** or methods like `intValue()`, while handling potential `null`.

Even though `parseXxx` and `valueOf(String)` share the same underlying string-parsing rules, they cannot be mechanically substituted for each other when the **return type** is part of an API signature or nullability contract.

## 7. Radix Strings and decode: Avoiding 0x Misunderstandings

When parsing bases other than 10:

```java
Integer decimal = Integer.valueOf("255");       // 255
Integer hex = Integer.valueOf("FF", 16);         // 255
Integer binary = Integer.valueOf("11111111", 2); // 255
```

For overloads taking a radix parameter, the input string normally contains only valid digits for that radix; it **does not** automatically accept a `0x` prefix:

```java
// Integer.valueOf("0xFF", 16); // NumberFormatException
Integer prefixed = Integer.decode("0xFF"); // 255
```

`Integer.decode` has its own rules accepting prefixes such as `0x` or `#` for hex and a leading `0` for octal; do not use it as a decimal parser for user input if interpreting a leading zero as octal would be unintended.

For negative integers, the parser follows sign rules:

```java
System.out.println(Integer.valueOf("-42"));   // -42
System.out.println(Integer.valueOf("-2A", 16)); // -42
```

When parsing untrusted input, bound length, validate radix, and document how signs are interpreted. Strings outside the `int`/`long` range throw `NumberFormatException`; `valueOf` **does not widen the value range**. If integers beyond `long` are genuinely needed, use `BigInteger` as required by the problem, rather than treating `Integer.valueOf` as arbitrary precision.

## 8. Boolean.valueOf: Different from Strict Numeric Parsers

`Boolean.valueOf(String)` and `Boolean.parseBoolean(String)` have important behavior:

- If the string equals `"true"` under **case-insensitive** comparison, the result is `true`.
- Any other string, such as `"yes"`, `"1"`, or `"falsee"`, produces `false` instead of throwing `NumberFormatException`.

```java
System.out.println(Boolean.valueOf("TrUe")); // true
System.out.println(Boolean.valueOf("yes"));  // false
System.out.println(Boolean.parseBoolean("1")); // false
```

Therefore, do not use `Boolean.valueOf(text)` as a **strict boolean format validator** when an API allows only exact `"true"` and `"false"` values. If inputs can be misspelled, silently returning `false` easily hides bad data.

Example of validating before parsing:

```java
static boolean parseStrictBoolean(String text) {
    if ("true".equalsIgnoreCase(text)) return true;
    if ("false".equalsIgnoreCase(text)) return false;
    throw new IllegalArgumentException("Expected true or false");
}
```

This is an **illustrative method** to place inside a class if you want to compile/run it. It intentionally does not accept whitespace or synonyms like `yes/no`; expand the rules according to your API contract.

## 9. Autoboxing and Unboxing: When Does Java Handle Them Automatically?

**Autoboxing** is the language-supported conversion from primitive to wrapper:

```java
Integer count = 42;     // boxing int -> Integer
Long length = 100L;     // boxing long -> Long
Boolean enabled = true; // boxing boolean -> Boolean
```

It has the same value semantics as writing explicitly:

```java
Integer count = Integer.valueOf(42);
```

When types are clear in code, autoboxing is often concise; when you want to highlight object creation, parse strings, or pick the right overload, `valueOf` is clearer. Neither form **is a promise to allocate a fresh object**.

**Unboxing** extracts the primitive from a wrapper:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed;          // unboxing
int explicit = boxed.intValue(); // same value
```

### Null unboxing risk

```java
Integer maybe = null;
// int wrong = maybe; // compiles, yet throws NullPointerException at runtime
```

A wrapper type allows `null` in a reference slot, whereas a primitive cannot hold `null`. To prevent errors, **check for null before unboxing** or design APIs using a type that expresses absence explicitly.

```java
Integer maybe = null;
int safeDefault = maybe == null ? 0 : maybe.intValue();
```

Choosing a default value of 0 is a **business decision**, not an automatic Java rule. In many applications, distinguishing 0 from "no value" is mandatory; in such cases, do not silently turn `null` into 0.

## 10. Wrapper Caching and ==: A Particularly Common Pitfall

For primitives:

```java
int a = 1000;
int b = 1000;
System.out.println(a == b); // true: compares int values
```

For wrappers:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(a.equals(b)); // true: same int value 1000
```

However, `a == b` when both sides are wrappers **compares references**, not numeric values. The result can depend on whether the factory reused an object. **Do not rely on this expression to check integer contents**.

The cache of `Integer.valueOf` mandatorily covers the range `−128..127`. For example:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
System.out.println(a == b); // true within the mandatory cache range
```

This only illustrates potential reuse, **not a comparison pattern to use**. To compare contents:

```java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second));    // true
System.out.println(first.compareTo(second)); // 0
```

When comparing with a primitive, Java can perform unboxing:

```java
Integer boxed = Integer.valueOf(1000);
System.out.println(boxed == 1000); // true: unboxes then compares numerically
```

Be especially careful if `boxed` can be `null`: evaluating `boxed == 1000` throws `NullPointerException`.

**Practical rule:** wrapper ↔ wrapper uses `equals` or `compareTo` for values; primitive ↔ primitive uses `==`; if `null` is possible, check first or use `Objects.equals(a,b)` for null-safe reference equality.

## 11. Collections/Generics: Wrappers Are Necessary, Yet Avoid Useless Boxing

`List<Integer>` works with objects:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>();
numbers.add(10);               // autoboxing
numbers.add(Integer.valueOf(20)); // explicit factory

int sum = 0;
for (Integer n : numbers) {
    sum += n; // unboxing
}
System.out.println(sum); // 30
```

Note that this list **can** contain `null` if the API permits; in that case `sum += n` causes `NullPointerException`.

Performance-wise, repeated boxing/unboxing inside loops over many elements can incur overhead and allocations depending on values, compiler/JIT, and usage. In purely arithmetic computation blocks, prefer primitive accumulators:

```java
long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // long arithmetic, no boxing at every step
}
Long boxedTotal = Long.valueOf(total); // box only at the API boundary
```

Do not turn every arithmetic operation into a chain of `Integer.valueOf` calls simply because legacy constructors are deprecated. The goal is to **replace wrapper creation properly when a wrapper is needed**, not force every numeric variable to become a wrapper.

## 12. Float and Double: valueOf Does Not Cure Binary Error

`Float.valueOf` and `Double.valueOf` return wrappers for floating-point values:

```java
Float f = Float.valueOf(1.25f);
Double d = Double.valueOf(0.1);
```

Even though `valueOf` is the recommended factory, it **does not make 0.1 decimally exact**:

```java
Double wrapped = Double.valueOf(0.1);
System.out.println(Double.toHexString(wrapped)); // 0x1.999999999999ap-4
```

`Double.valueOf("0.1")` parses the decimal string and creates a wrapper holding the closest `double` value to 0.1; this is still finite binary arithmetic. For monetary/exact decimal problems requiring scale and rounding, consider `BigDecimal` created from a string (e.g., `new BigDecimal("0.1")`), rather than using `Double.valueOf` as an exact solution.

For `Double`, the `equals` method uses canonicalized bit semantics to handle special cases like NaN and signed zero; it **does not fully coincide** with primitive `==` comparison. When working with NaN, ±Infinity, or ±0.0, choose comparison rules that match your business contract.

## 13. Parsing Errors: Do Not Assume valueOf Accepts All Inputs

For `Integer.valueOf(String)` and similarly for integers:

```java
Integer good = Integer.valueOf("42");

// NumberFormatException:
// Integer bad = Integer.valueOf("42abc");
// Integer tooLarge = Integer.valueOf("2147483648");
// Integer withSpaces = Integer.valueOf(" 42 ");
```

These are **input data** errors, not reasons to revert to deprecated constructors. You must define the rules: are leading/trailing whitespace, plus signs, minus signs, prefixes, or range bounds allowed?

If leading/trailing ASCII whitespace is allowed, you can normalize explicitly:

```java
static int parseIntWithTrim(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing integer");
    }
    return Integer.parseInt(raw.trim());
}
```

This is an illustrative method. `trim()` merely selects one whitespace character set per the `String` specification; if broader Unicode rules are needed, define an appropriate parser. Do not automatically `trim` identifier data or numeric signatures if whitespace is part of the data contract.

### Preserving proper exception types

- `Integer.valueOf("invalid")` can throw `NumberFormatException`.
- `Integer.valueOf(1000)` takes a valid primitive, so it does not parse strings.
- Unboxing from a `null` wrapper causes `NullPointerException`.
- `Boolean.valueOf("invalid")` **does not** throw `NumberFormatException`; it returns `false`, so validate separately when strictness is required.

Do not "handle errors" by swallowing all exceptions and returning 0 or false if those values also carry business meaning, as it becomes hard to distinguish bad data from valid values.

## 14. Standalone Runnable Java 17+ Program

Create the file **`WrapperValueOfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class WrapperValueOfDemo {
    private static boolean parseStrictBoolean(String text) {
        if ("true".equalsIgnoreCase(text)) return true;
        if ("false".equalsIgnoreCase(text)) return false;
        throw new IllegalArgumentException("Expected true or false");
    }

    public static void main(String[] args) {
        Integer boxed = Integer.valueOf(42);
        int parsed = Integer.parseInt("42");
        Integer parsedWrapper = Integer.valueOf("42");

        System.out.println("boxed = " + boxed);
        System.out.println("parsed primitive = " + parsed);
        System.out.println("parsed wrapper = " + parsedWrapper);
        System.out.println("hex = " + Integer.valueOf("FF", 16));
        System.out.println("prefixed hex = " + Integer.decode("0xFF"));

        Integer a = Integer.valueOf(1000);
        Integer b = Integer.valueOf(1000);
        System.out.println("value equals = " + a.equals(b));
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("null-safe equals = "
                + Objects.equals(a, b));

        Integer cachedA = Integer.valueOf(127);
        Integer cachedB = Integer.valueOf(127);
        System.out.println("cached reference = " + (cachedA == cachedB));

        System.out.println("boolean TRUE = "
                + Boolean.valueOf("TrUe"));
        System.out.println("boolean yes = "
                + Boolean.valueOf("yes"));

        try {
            parseStrictBoolean("yes");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict boolean: rejected");
        }

        List<Integer> numbers = new ArrayList<>();
        numbers.add(10); // autoboxing
        numbers.add(Integer.valueOf(20));
        int sum = 0;
        for (Integer value : numbers) {
            sum += value; // unboxing
        }
        System.out.println("list sum = " + sum);

        Integer absent = null;
        try {
            int value = absent;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: rejected");
        }

        try {
            Integer.valueOf("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("int parse range: rejected");
        }

        System.out.println("double hex = "
                + Double.toHexString(Double.valueOf(0.1)));
    }
}
```

Run in the directory containing the file:

```bash
javac WrapperValueOfDemo.java
java WrapperValueOfDemo
```

**Standard output:**

```text
boxed = 42
parsed primitive = 42
parsed wrapper = 42
hex = 255
prefixed hex = 255
value equals = true
compareTo = 0
null-safe equals = true
cached reference = true
boolean TRUE = true
boolean yes = false
strict boolean: rejected
list sum = 30
null unboxing: rejected
int parse range: rejected
double hex = 0x1.999999999999ap-4
```

**Grouped explanation:**

1. `valueOf(42)` returns a wrapper, `parseInt("42")` returns a primitive, and `valueOf("42")` parses the string and returns a wrapper.
2. `valueOf("FF",16)` uses a radix; `decode("0xFF")` has rules for accepting prefixes.
3. `equals`, `compareTo`, and `Objects.equals` perform content-based or null-safe comparisons without relying on reference identity.
4. Both `127` values are cached under `Integer.valueOf`'s contract; the example illustrates caching rather than **encouraging `==`** for wrappers.
5. `Boolean.valueOf("yes")` returns `false`; the custom strict parser rejects it.
6. `List<Integer>` uses autoboxing when adding a primitive and unboxing when summing.
7. Unboxing `null` throws `NullPointerException`; a string outside the `int` range throws `NumberFormatException`.
8. `Double.valueOf(0.1)` still holds the binary `double` value and does not resolve representation error.

## 15. Checklist for Replacing Constructors in a Codebase

When encountering `new Integer(...)`, `new Long(...)`, or similar wrapper constructors, proceed step by step:

1. **Determine the target type**: does the API need a primitive or a wrapper? If `int` is needed, `Integer.parseInt` is usually more natural than `Integer.valueOf`.
2. **Determine the source**: primitive or string? Use the matching `valueOf(primitive)` or `valueOf(String)` overload.
3. **Replace the constructor** with `valueOf` or autoboxing where suitable; **do not keep `new` just to allocate a fresh object**.
4. **Do not rely on identity**: replace wrapper `==` comparisons with `equals`/`compareTo`, or check for null and compare primitives.
5. **Audit nullability**: if a wrapper can be `null`, inspect every unboxing, arithmetic operation, primitive comparison, or collection usage.
6. **Audit parsing**: could inputs be malformed, out of range, in a different radix, contain whitespace, or have arbitrary boolean spellings?
7. **Audit performance**: avoid pointless boxing/unboxing inside heavy loops; use primitives for pure calculations.
8. **Check type bounds**: `Integer.valueOf` does not hold values outside `int`; `Double.valueOf` does not create exact decimals.
9. **Do not use wrappers as synchronization locks** or identity tokens; switch to a dedicated lock object if needed.
10. **Compile on the target Java version** and genuinely resolve deprecated-for-removal warnings, instead of ignoring them because the program "still runs."

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Deprecated wrapper constructors mean it won't compile in Java 17" | It may still compile with warnings; avoid using them because they are deprecated for removal |
| "`valueOf` always allocates a new object" | The factory can reuse/cache objects |
| "`valueOf` always caches every value" | Only certain ranges/behaviors are guaranteed; do not rely on identity |
| "`Integer.valueOf("42")` and `Integer.parseInt("42")` return the same type" | One returns `Integer`, the other returns `int` |
| "`Integer.valueOf("0xFF",16)` is the same as `Integer.decode("0xFF")`" | The radix overload does not accept `0x` prefixes; `decode` has its own prefix rules |
| "`Boolean.valueOf("yes")` will throw an error" | It returns `false`; a strict parser is needed if you want to reject it |
| "For two numeric wrappers with the same value, `==` is always true" | `==` on two references compares identity; use `equals`/`compareTo` |
| "Autoboxing eliminates all costs" | Boxing/unboxing can still create overhead, especially inside loops |
| "A null wrapper defaults to unboxing as 0" | Unboxing `null` throws `NullPointerException` |
| "`Double.valueOf("0.1")` preserves exact 1/10" | It returns a binary `double` near 0.1, not a `BigDecimal` |
| "Every wrapper extends Number" | `Character` and `Boolean` do not extend `Number` |
| "You can use an Integer wrapper as a lock because caching shares it" | Wrappers are value-based; do not use them for synchronization or rely on identity |

## 17. Exercises with Solutions

**Exercise 1.** Rewrite `new Integer(123)` and `new Double("2.5")` using the recommended API.  
**Solution:** `Integer.valueOf(123)` and `Double.valueOf("2.5")`. If only primitives are needed, you can choose `123` and `Double.parseDouble("2.5")`.

**Exercise 2.** How do the return types of `Integer.parseInt("7")` and `Integer.valueOf("7")` differ?  
**Solution:** `int` and `Integer`, respectively. The digits are parsed identically, yet the result has a different form (primitive vs. wrapper).

**Exercise 3.** What value does `Integer.valueOf("FF",16)` produce? And `Integer.valueOf("0xFF",16)`?  
**Solution:** `255`; the second throws `NumberFormatException` due to the prefix. `Integer.decode("0xFF")` is the option that accepts the prefix.

**Exercise 4.** Should you use `Integer.valueOf(1000) == Integer.valueOf(1000)` to check value equality?  
**Solution:** No. Even if an implementation caches extra values, `==` on two wrapper references is not a numeric comparison contract; use `equals` or `compareTo`.

**Exercise 5.** What does `Boolean.valueOf("YES")` produce, and how should you handle it if only `true/false` are accepted?  
**Solution:** It produces `false`. If all invalid tokens must be rejected, validate against the two accepted values first before returning a boolean or throwing an error.

**Exercise 6.** What happens with `Integer absent = null; int x = absent;`?  
**Solution:** The statements compile, yet at runtime unboxing throws `NullPointerException`. Check for null or design the API with an explicit absence state.

**Exercise 7.** Why does using `Double.valueOf(0.1)` not enable exact decimal monetary calculations?  
**Solution:** It only wraps a binary `double` value close to 0.1; exact decimal problems should use a decimal representation such as `BigDecimal` from a string, along with rounding rules.

**Exercise 8.** Why should you avoid writing `Integer sum=0;` and looping `sum += x` millions of times when simply summing integers?  
**Solution:** The expression unboxes and reboxes on every iteration, creating overhead and allocations; use a primitive accumulator suited to the value range and box only where an object is required.

**Exercise 9.** Does `Character.valueOf("A")` compile?  
**Solution:** No. The method takes `char`, so write `Character.valueOf('A')`. A `String` can contain multiple UTF-16 code units, so extracting Unicode characters from strings requires an explicit contract.

**Exercise 10.** What can replace `new Long("9000000000")`?  
**Solution:** `Long.valueOf("9000000000")` if the API needs a wrapper; `Long.parseLong("9000000000")` if a primitive `long` is needed.

**Key takeaway:** Wrappers are **value-representing objects**, not places to rely on identity. When you need a wrapper, prefer `valueOf` or autoboxing instead of deprecated constructors; when you need a primitive from a string, use `parseXxx`. Always guard against parse errors, null unboxing, return type mismatches, and incorrect comparisons.