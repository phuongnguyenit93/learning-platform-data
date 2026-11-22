# Integer.getInteger and Long.getLong: Reading System Properties, Not Ordinary Parsing

## 1. The easiest thing to confuse

The names `Integer.getInteger(String)` and `Long.getLong(String)` lead many people to think they are ways to convert a numeric string into an `Integer` or `Long`. **That is a misunderstanding.**

These two methods take **the name of a Java system property**; they look up **the string value assigned to that property name**, and then decode the retrieved value into an integer. By contrast, `Integer.parseInt(String)` and `Long.parseLong(String)` process **the contents of the passed string itself**.

~~~java
// Illustrative code placed inside a method:
System.setProperty("app.retries", "5");

Integer retries = Integer.getInteger("app.retries");  // 5
int direct = Integer.parseInt("5");                    // 5

// Integer.getInteger("5") does NOT mean parse the number 5:
// It looks up the system property NAMED "5".
~~~

Distinguish the two roles of strings:

- **Property key/name**: `"app.retries"` — the key name used to look up configuration.
- **Property value**: `"5"` — the text containing the number, readable via `System.getProperty("app.retries")`.

For `getInteger`/`getLong`, the lookup step **always precedes the numeric decoding step**. If no matching property exists, the result defaults to `null` or a fallback value specified by the developer.

## 2. Table distinguishing easily confused APIs

| API | Parameter string interpreted as | Return type | Behavior when missing/invalid data |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | The numeric text `"42"` itself | `int` | Throws `NumberFormatException` if not a valid integer |
| `Long.parseLong("42")` | The numeric text `"42"` itself | `long` | Throws `NumberFormatException` if unparseable |
| `Integer.valueOf("42")` | The numeric text `"42"` itself | `Integer` | Throws `NumberFormatException` if invalid |
| `Long.valueOf("42")` | The numeric text `"42"` itself | `Long` | Throws `NumberFormatException` if invalid |
| `Integer.decode("0x2A")` | Numeric string possibly carrying a radix prefix | `Integer` | Throws `NumberFormatException` if invalid |
| `Long.decode("0x2A")` | Numeric string possibly carrying a radix prefix | `Long` | Throws `NumberFormatException` if invalid |
| `System.getProperty("app.port")` | System property **name** | `String` or `null` | Returns the property string; does not parse |
| `Integer.getInteger("app.port")` | System property **name** | `Integer` or `null` | Missing/undecodable → `null` |
| `Long.getLong("app.limit")` | System property **name** | `Long` or `null` | Missing/undecodable → `null` |

Property-reading methods also have overloads accepting a **default value**:

~~~java
Integer count = Integer.getInteger("app.count", 10);
Long limit = Long.getLong("app.limit", 1_000L);
~~~

If the property **does not exist or cannot be decoded into a valid number**, these overloads return a wrapper containing the default value. They do not write that default value into the system properties table.

**Important note:** in environments with property-access security controls, reading can raise `SecurityException`. Default values are not a mechanism to bypass or disable access restrictions.

## 3. What is a system property and where does it come from?

Java system properties are a collection of **string key/value** pairs belonging to the JVM process. Examples include `"java.version"` or application-defined keys such as `"app.worker.count"`.

Values can be supplied at JVM startup via the `-Dkey=value` option:

~~~bash
java -Dapp.retries=5 -Dapp.limit=0x100 MyApplication
~~~

At runtime, the application can read:

~~~java
String text = System.getProperty("app.retries");
Integer retries = Integer.getInteger("app.retries");
Long limit = Long.getLong("app.limit");
~~~

In the command example above:

- `text` is the string `"5"`.
- `retries` is an `Integer` wrapper holding `5`.
- `limit` is a `Long` wrapper holding `256L` because the text `0x100` is decoded in base 16.

In code, an application can also modify a property via `System.setProperty(key, value)` or remove it via `System.clearProperty(key)`. System properties are typically shared within **a single JVM process**, not an OS-level configuration store.

### System property differs from environment variable

`System.getProperty("APP_PORT")` and `System.getenv("APP_PORT")` are **two different data sources**:

- `System.getProperty` reads the Java system properties table, typically set via `-D` or Java code.
- `System.getenv` reads OS-provided process environment variables.
- `Integer.getInteger` and `Long.getLong` **do not automatically read environment variables**.

~~~java
// Illustration: the two calls read two different key namespaces.
String property = System.getProperty("APP_PORT");
String environment = System.getenv("APP_PORT");
~~~

You can design an application to accept both sources, yet you must implement explicit precedence/validation logic; Java does not automatically expose environment variables as system properties for `getInteger`/`getLong`.

## 4. How Integer.getInteger works

In usage terms, you can picture `Integer.getInteger(name)` as equivalent to this flow:

1. Accept string `name` as the **key name**.
2. Read `System.getProperty(name)`.
3. If no valid string value is obtained, return `null`.
4. If a string is present, decode the number using rules like `Integer.decode(String)`.
5. If a number in `int` range is decoded, return the corresponding `Integer`; if malformed or out of range, return `null`.

This is a **conceptual model explaining public behavior**, not a statement-by-statement guarantee of JDK internals.

~~~java
System.setProperty("demo.threads", "8");
Integer threads = Integer.getInteger("demo.threads");

System.out.println(threads); // 8
~~~

If no property named `"demo.threads"` exists:

~~~java
System.clearProperty("demo.threads");
Integer threads = Integer.getInteger("demo.threads");
System.out.println(threads); // null
~~~

`null` indicates the call did not supply a numeric `Integer` value; it is **not zero**. In practice, `null` can result from a missing property, an invalid name, or an undecodable string value. Looking only at the `null` result is not enough to identify the cause without inspecting the raw property and access state.

## 5. How Long.getLong works

`Long.getLong(name)` also reads the **property named `name`**, yet parses it into a 64-bit signed `long` integer instead of a 32-bit `int`:

~~~java
System.setProperty("demo.max.id", "9223372036854775807");

Long id = Long.getLong("demo.max.id");
System.out.println(id); // 9223372036854775807
~~~

That number equals `Long.MAX_VALUE`; `Integer.getInteger("demo.max.id")` cannot represent that value and returns `null`.

| Feature | `Integer.getInteger` | `Long.getLong` |
| --- | --- | --- |
| Return type | `Integer` | `Long` |
| Numeric range | −2³¹ to 2³¹−1 | −2⁶³ to 2⁶³−1 |
| Decoding method with same rules | `Integer.decode` | `Long.decode` |
| Missing/invalid property | `null` or default | `null` or default |
| Reads environment directly? | No | No |

The name `Long.getLong` does not mean "read a Long from an arbitrary named variable" or "turn the passed `String` value into a long." It uses the **value of the `name` parameter as a lookup key**.

## 6. Decoding rules: decimal, hexadecimal, octal

`getInteger` and `getLong` decode the **property value** using `Integer.decode`/`Long.decode` rules. Common strings:

| Property value | How `decode` interprets it | Decimal value |
| --- | --- | --- |
| `"42"` | Decimal | 42 |
| `"+42"` | Decimal, plus sign | 42 |
| `"-42"` | Decimal, minus sign | −42 |
| `"0x2A"` or `"0X2A"` | Hexadecimal | 42 |
| `"#2A"` | Hexadecimal | 42 |
| `"052"` | Octal due to leading zero | 42 |
| `"-0x2A"` | Negative hexadecimal | −42 |
| `"0"` | Zero | 0 |

Remember that **leading zeros are significant**:

~~~java
System.setProperty("demo.mode", "010");
System.out.println(Integer.getInteger("demo.mode")); // 8
System.out.println(Integer.parseInt("010"));         // 10
~~~

`Integer.getInteger` reads property value `"010"` and decodes it as **octal 8**. `Integer.parseInt("010")` defaults to **radix 10** and yields **10**.

This difference easily causes configuration bugs: a configuration author might think `010` means ten, while code reading via `getInteger` receives eight. When config docs specify decimal values, reading `System.getProperty` followed by `parseInt` can be more appropriate.

### Which prefixes are unsupported by decode?

`Integer.decode`/`Long.decode` do not accept the `0b`/`0B` prefix of **binary literals in Java source code**. Strings like `"0b1010"` typically make `getInteger`/`getLong` return `null` or the fallback.

Furthermore, underscores `_` in **Java source literals** like `1_000` are compiler syntax, not automatically valid in configuration strings `"1_000"`. Do not infer parsing capabilities of these APIs from Java literal support.

Wrong example:

~~~java
System.setProperty("demo.binary", "0b1010");
Integer value = Integer.getInteger("demo.binary", -1);
System.out.println(value); // -1: 0b is unsupported by decode
~~~

If configuration genuinely specifies base 2, use `Integer.parseInt(text, 2)` on the digit text `"1010"`, or design an explicit handling step for the `0b` prefix before parsing.

### Signs, whitespace, and formatting

The `decode` methods allow a `+` or `-` sign at the **start of the string**, before any radix prefix. Never place the sign after the prefix, such as `"0x-2A"`.

They do not automatically strip whitespace. Values like `" 42 "` are invalid for `decode`; `getInteger` returns `null` or the fallback. If the configuration contract allows whitespace, read the string and normalize explicitly, e.g., `text.trim()`, then parse.

## 7. Missing property vs. invalid content

Three states can mean very different things in configuration:

1. Property **does not exist**.
2. Property **exists but is empty or malformed**.
3. Property **exists but the number exceeds the target type's range**.

With `Integer.getInteger(name)`, all three cases can result in `null`. With a default-value overload, all three return the same fallback, unless a security error occurs when reading the property.

~~~java
System.clearProperty("demo.missing");
System.setProperty("demo.invalid", "abc");
System.setProperty("demo.too.big", "2147483648");

System.out.println(Integer.getInteger("demo.missing"));       // null
System.out.println(Integer.getInteger("demo.invalid"));       // null
System.out.println(Integer.getInteger("demo.too.big"));       // null
System.out.println(Integer.getInteger("demo.missing", 7));    // 7
System.out.println(Integer.getInteger("demo.invalid", 7));    // 7
System.out.println(Integer.getInteger("demo.too.big", 7));    // 7
~~~

`2147483648` is one greater than `Integer.MAX_VALUE`, yet still within the `long` range:

~~~java
System.out.println(Long.getLong("demo.too.big")); // 2147483648
~~~

**Important note:** `getInteger`/`getLong` can let **invalid configuration data be masked** by a fallback. For mandatory and critical settings (e.g., resource limits), picking a default arbitrarily can hide operational errors.

## 8. Overloads and default values

`Integer` provides:

~~~java
Integer getInteger(String name)
Integer getInteger(String name, int defaultValue)
Integer getInteger(String name, Integer defaultValue)
~~~

`Long` provides the corresponding forms:

~~~java
Long getLong(String name)
Long getLong(String name, long defaultValue)
Long getLong(String name, Long defaultValue)
~~~

The signatures above are for API reference (not method declarations to copy into an application class).

Examples:

~~~java
System.clearProperty("app.timeout");
System.out.println(Integer.getInteger("app.timeout", 30)); // 30
System.out.println(Long.getLong("app.timeout", 60L));      // 60

Integer fallback = Integer.valueOf(15);
Integer timeout = Integer.getInteger("app.timeout", fallback);
System.out.println(timeout); // 15
~~~

The wrapper overload allows passing a wrapper default value; as a result, it can return `null` if the wrapper default parameter is `null`:

~~~java
Integer noDefault = Integer.getInteger("app.timeout", (Integer) null);
System.out.println(noDefault); // null
~~~

In this case, when the property is missing or undecodable, a null fallback still produces null. Deliberately pick the overload type, especially when passing a `null` literal — use a cast to express intent or choose the method without a default parameter.

### If you want to detect configuration errors instead of silently taking defaults

~~~java
static int requiredDecimalProperty(String name) {
    String text = System.getProperty(name);
    if (text == null) {
        throw new IllegalArgumentException("Missing system property: " + name);
    }
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid decimal integer property: " + name, ex);
    }
}
~~~

This is an **illustrative method inside a class**, compilable on Java 17. It specifies accepting strictly **decimal numbers**; unlike `Integer.getInteger`, `"010"` is interpreted as 10 and `"0x10"` is rejected. Do not add `trim()` implicitly if the system needs to detect invalid whitespace.

This function does **not** automatically enforce business limits such as "thread count must be greater than 0"; that requires additional validation after parsing.

## 9. Standalone runnable Java 17+ program

Create file `SystemPropertyNumberDemo.java`:

~~~java
public class SystemPropertyNumberDemo {
    public static void main(String[] args) {
        System.setProperty("lesson.count", "42");
        System.setProperty("lesson.hex", "0x2A");
        System.setProperty("lesson.octal", "010");
        System.setProperty("lesson.binary", "0b1010");
        System.setProperty("lesson.invalid", "abc");
        System.setProperty("lesson.outOfInt", "2147483648");
        System.setProperty("lesson.maxLong", "9223372036854775807");
        System.clearProperty("lesson.missing");

        System.out.println("getInteger decimal=" +
                Integer.getInteger("lesson.count"));
        System.out.println("getInteger hex=" +
                Integer.getInteger("lesson.hex"));
        System.out.println("getInteger octal=" +
                Integer.getInteger("lesson.octal"));
        System.out.println("parseInt octal text=" +
                Integer.parseInt(System.getProperty("lesson.octal")));
        System.out.println("getLong max=" +
                Long.getLong("lesson.maxLong"));

        System.out.println("missing=" +
                Integer.getInteger("lesson.missing"));
        System.out.println("missing default=" +
                Integer.getInteger("lesson.missing", 99));
        System.out.println("invalid default=" +
                Integer.getInteger("lesson.invalid", 7));
        System.out.println("binary default=" +
                Integer.getInteger("lesson.binary", -1));
        System.out.println("int overflow default=" +
                Integer.getInteger("lesson.outOfInt", -1));
        System.out.println("same number as long=" +
                Long.getLong("lesson.outOfInt"));

        System.out.println("parse direct=" + Integer.parseInt("42"));
        System.out.println("raw property=" +
                System.getProperty("lesson.count"));

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            System.out.println("parse invalid: NumberFormatException");
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 SystemPropertyNumberDemo.java
java SystemPropertyNumberDemo
~~~

Stdout output:

~~~text
getInteger decimal=42
getInteger hex=42
getInteger octal=8
parseInt octal text=10
getLong max=9223372036854775807
missing=null
missing default=99
invalid default=7
binary default=-1
int overflow default=-1
same number as long=2147483648
parse direct=42
raw property=42
parse invalid: NumberFormatException
~~~

Explanation:

- Properties are set via `System.setProperty` within the program itself, so output is independent of external `-D` settings for those keys.
- `"010"` is decoded by `getInteger` in octal as 8; `parseInt` parses it in decimal as 10.
- `"0b1010"` is not a `decode` prefix, so it falls back to −1.
- `"2147483648"` exceeds `int` range yet remains valid for `long`.
- `Integer.parseInt("abc")` throws `NumberFormatException`; `getInteger` on a property with value `"abc"` returns the default.
- `System.getProperty` returns the raw string; it does not cast or perform decoding.

## 10. Using -D when deploying real programs

For an application program with a compiled `ServerApp` class, you can configure from the command line:

~~~bash
java -Dserver.port=8080 -Dserver.workers=4 ServerApp
~~~

Application code snippet:

~~~java
int port = Integer.getInteger("server.port", 8080);
int workers = Integer.getInteger("server.workers", 4);
~~~

Here Java **autounboxes** the wrapper result from `getInteger` into `int`. With the primitive-default overload, missing/invalid property cases yield a wrapper holding the default before unboxing, so null does not occur on the normal path. However, if property access is restricted, an exception can still be thrown.

Do not misplace the JVM argument:

~~~bash
java -Dserver.port=8080 ServerApp
~~~

`-Dserver.port=8080` is a **JVM option before the class name**. Writing `java ServerApp -Dserver.port=8080` passes that string into `main(String[] args)` as a program argument rather than setting the system property.

### Relationship with the deployment environment

In container/service systems, there may be an environment variable `SERVER_PORT`, config files, application CLI flags, or system property `server.port`. These are independent configuration sources. If deployment requires a precedence hierarchy such as "`-D` overrides environment", you must write explicit resolution logic.

Do not casually put passwords, tokens, or sensitive secrets into system properties just for convenience. JVM properties may be exposed via diagnostic tools, logging, or process argument listings depending on the environment; follow proper secret storage mechanisms.

## 11. Strings containing numbers: parseInt, parseLong, decode, or getInteger?

A practical criterion:

| Need | Recommended API |
| --- | --- |
| User-entered decimal string `"123"` | `Integer.parseInt(text)` or `Long.parseLong(text)` |
| Decimal string needing a wrapper | `Integer.valueOf(text)` or `Long.valueOf(text)` |
| Radix-prefixed numeric string with `0x`, `#`, leading `0` | `Integer.decode(text)` or `Long.decode(text)` |
| Digit string with explicitly specified radix | `Integer.parseInt(text, radix)` or `Long.parseLong(text, radix)` |
| Read JVM property accepting `decode` rules and fallback | `Integer.getInteger(name, default)` or `Long.getLong(name, default)` |
| Read JVM property requiring strict decimal and exact error reporting | `System.getProperty(name)`, check then `parseInt`/`parseLong` |
| Read environment variable | `System.getenv(name)`, then validate/parse if needed |

A safe mental model:

- Have **text value** to convert to a number → pick a **parse/decode** method.
- Have **JVM property name** to read numeric configuration → pick `getInteger`/`getLong` when decode/fallback rules fit.
- Have **environment variable name** → read via `System.getenv` first; never use `getInteger` to look it up.

## 12. Caution with number parsing and range limits

### Numbers exceeding target type range

~~~java
System.setProperty("app.large", "9223372036854775807");
System.out.println(Long.getLong("app.large"));     // 9223372036854775807
System.out.println(Integer.getInteger("app.large")); // null
~~~

If the value even exceeds `long`, `Long.getLong` cannot decode it either; without a default it returns `null`. Config elements needing values larger than `long` can use `BigInteger` after reading text, with dedicated validation.

### Null is not zero

~~~java
System.clearProperty("app.items");
Integer items = Integer.getInteger("app.items");

System.out.println(items == null); // true
~~~

If you write `int count = Integer.getInteger("app.items");`, unboxing `null` throws `NullPointerException`. This is a common mistake when using the no-default overload with primitive variables.

If "missing property" differs from "zero value", keep nullable `Integer` and handle both cases explicitly, or throw an informative configuration exception.

### Does not automatically ignore whitespace

~~~java
System.setProperty("app.spaces", " 7 ");
System.out.println(Integer.getInteger("app.spaces", -1)); // -1
~~~

If users might enter whitespace, read the text and apply a **deliberate** normalization policy. Malformed errors should also be logged carefully so operators know the cause instead of losing track behind a "plausible-looking" default.

## 13. Configuration policy: optional, required, and valid range

For a system property defining worker pool size, we typically need at least three steps:

1. **Read** the value from the intended source.
2. **Parse** using the published format rules.
3. **Validate** the business range, e.g., worker count from 1 to 128.

An illustrative Java 17 function:

~~~java
static int workerCount() {
    String raw = System.getProperty("app.workers");
    if (raw == null) {
        return 4; // Default when key is absent
    }

    final int count;
    try {
        count = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "app.workers must be a decimal integer", ex);
    }

    if (count < 1 || count > 128) {
        throw new IllegalArgumentException(
                "app.workers must be in 1..128");
    }
    return count;
}
~~~

Differences from `Integer.getInteger("app.workers", 4)`:

- **Missing property** → uses 4.
- **Malformed property** → reports error instead of silently using 4.
- **Property with 0, negative, or overly large business value** → reports error.
- `"010"` is parsed as decimal 10, not octal 8.

Choosing fallback versus fail-fast depends on how critical the configuration is. For parameters affecting resources, safety, or critical data, **fail-fast** usually catches deployment mistakes early.

## 14. Common mistakes

| Mistake | Consequence | Proper fix |
| --- | --- | --- |
| `Integer.getInteger("123")` to parse 123 | Looks up property named `"123"`, usually gets `null` | `Integer.parseInt("123")` |
| `Long.getLong("9223372036854775807")` to parse number | Looks up property named as the entire digit string | `Long.parseLong(text)` |
| Thinking `getInteger` reads environment variables | Misses `System.getenv` | Read environment first if that is the data source |
| Thinking `getInteger` always uses decimal | Property `"010"` becomes octal 8 | `System.getProperty` + `parseInt` when decimal is needed |
| Property `"0b1010"` decoded as binary literal | Returns null/default | Parse radix 2 after handling format |
| Property `"1_000"` decoded as Java literal | Returns null/default | Define and perform separate normalization/parsing |
| Malformed property silently falls back | Hides misconfiguration | Read string then fail-fast |
| Assigning `getInteger(name)` directly to `int` without check | `NullPointerException` if missing/invalid property | Use default overload or null guard |
| `Integer.getInteger` reading number beyond int range | Null/default even though text is valid long | Use `Long.getLong` or parse with matching type |
| Thinking fallback writes a new property | Misunderstands config state | Fallback is only the return value |
| Placing `-D` after class name in `java` command | Does not set JVM property | Place `-Dkey=value` before class/JAR name |
| Using getInteger for all configs without validation | Accepts negative/zero outside contract | Validate business range after parsing |

## 15. Self-check exercises

**1.** Given:

~~~java
System.setProperty("demo.number", "25");
System.out.println(Integer.getInteger("demo.number"));
System.out.println(Integer.getInteger("25"));
~~~

What does the first line print? Is the second line guaranteed to print 25?

**Answer:** the first line prints `25`. The second line looks up a property **named** `"25"`; the result may be `null` if that property does not exist, and you cannot assume it will print 25.

**2.** Property `demo.limit=0x20` read via `Long.getLong("demo.limit")` yields what?

**Answer:** `32L`, because `0x20` is hexadecimal.

**3.** Why might `Integer.getInteger("mode", -1)` return −1 even though property `mode` exists?

**Answer:** The property value may be malformed or outside `int` range, causing decode to fail and the overload to return the fallback.

**4.** Why does `Integer.getInteger` read `"010"` differently from `Integer.parseInt("010")`?

**Answer:** getInteger uses `Integer.decode` rules on the **property value**, so it reads octal 8; parseInt defaults to decimal so it reads 10.

**5.** If you want the application to report an error when `app.workers` has value `"abc"` yet use a default when the property does not exist: what should you use?

**Answer:** `System.getProperty("app.workers")`; if it returns null use the default, whereas if a string is present use `Integer.parseInt` inside `try/catch` plus business validation.

**6.** Can `Long.getLong` read the environment variable `MAX_COUNT`?

**Answer:** Not automatically. `Long.getLong("MAX_COUNT")` searches for a **system property** of that name. To read an environment variable, use `System.getenv("MAX_COUNT")` and parse.

## 16. Key takeaways

- **`Integer.getInteger(name)` and `Long.getLong(name)` take a *system property name*, not a numeric string to parse directly.**
- They read the property value and decode it using decimal/hex/octal rules, unlike default decimal parsing.
- Missing property or invalid value → returns `null` or the overload's default; check for null before unboxing.
- `System.getProperty`, `System.getenv`, and `Integer.parseInt`/`Long.parseLong` solve **different problems**.
- For critical configuration, separate read source → parse → validate → error handling, rather than accidentally hiding errors with fallbacks.

Official documentation (Java 17):

- [Integer.getInteger / Integer.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): rules for reading system properties and decoding values.
- [Long.getLong / Long.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): corresponding methods for `long`.
- [System.getProperty](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#getProperty(java.lang.String)) and [System.getenv](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#getenv(java.lang.String)): distinguishing configuration sources.
- [Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Dproperty=value` option.