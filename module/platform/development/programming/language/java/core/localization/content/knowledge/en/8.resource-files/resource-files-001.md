# .properties Syntax: Keys, Values, Comments, and Line Continuations in Java

## 1. What is a .properties file?

A `.properties` file contains text-based **key–value** pairs. In Java, it is commonly used for application configuration (via `java.util.Properties`) and localization (via `ResourceBundle` / `PropertyResourceBundle`). For example:

```properties
# Config
app.name=Learning Platform
timeout.seconds=30
welcome=Xin chào!
```

Even though `timeout.seconds` looks like a number, the value returned by `Properties.getProperty("timeout.seconds")` is still the string `"30"`. The file format itself has no JSON data types, no nested objects, and no automatic placeholder expansion. The dot in `app.name` is simply part of the key name. A framework may support its own syntax outside Java's standard parser contract; this lesson focuses on **standard .properties syntax**.

A key can appear in a `Messages_vi.properties` resource and then be retrieved with `bundle.getString("key")`. The internal syntax remains the same; the important difference lies in **the reading API and encoding decoding rules**, which are clarified at the end of this lesson.

## 2. How to write keys, values, and separators

Each property entry is a **logical line** with a key and a value. Three common separator styles are all valid:

```properties
app.name=Learning Platform
app.version:1.0
app.owner Development Team
app.mode = production
```

The first **unescaped** separator can be `=`, `:`, or whitespace. The parser skips leading whitespace on the line, identifies the key, and then skips whitespace and an optional separator before reading the value.

| Line in file | Actual Key | Actual Value |
|---|---|---|
| `name=Lan` | `name` | `Lan` |
| `name:Lan` | `name` | `Lan` |
| `name Lan` | `name` | `Lan` |
| `name = Lan` | `name` | `Lan` |
| `empty=` | `empty` | Empty string `""` |
| `justKey` | `justKey` | Empty string `""` |
| `a=b=c` | `a` | `b=c` |
| `url=https://example.com?a=b` | `url` | `https://example.com?a=b` |

An `=` or `:` appearing after the value has started is just an ordinary character. You should consistently use the `key=value` style for readability and to reduce misunderstandings during code reviews.

### Keys are case-sensitive

`app.name` and `App.Name` are **two different keys**. Key names such as `button.save`, `menu.file`, and `error.notFound` are usually convenient because they are descriptive and contain no whitespace. Do not arbitrarily change letter casing when calling `getProperty` or `getString`.

### Escaping in keys

If a key needs to contain a space, `=`, or `:`, prefix it with a backslash `\`:

```properties
first\ name=Lan
user\=id=42
server\:port=8080
\#headline=Introduction
\!notice=Attention
```

The corresponding keys are: `first name`, `user=id`, `server:port`, `#headline`, and `!notice`. An **unescaped** line `first name=Lan` would be interpreted as the key `first` and the value `name=Lan` because the first space acts as the separator.

## 3. Comments: lines starting with `#` or `!`

A **natural line** is ignored as a comment if its first non-whitespace character is `#` or `!`:

```properties
# Comment style one
! Comment style two

   # Indented comment
   ! Also valid
name=Lan
```

Blank lines or lines containing only whitespace are also ignored. Comments are **not** key-value pairs. Do not use `//` or `/* ... */` as in Java comments; they have no comment meaning in `.properties` file syntax.

### No inline comments after values

```properties
# Entire line is comment
message=Hello! # This is part of the value
\#key=value
```

The `message` line contains the entire string `Hello! # This is part of the value`. The line `\#key=value` creates a key starting with `#` because that character is escaped. Therefore, do not write `timeout=30 # seconds` expecting the parser to strip `# seconds`; the actual value includes that part. Place notes on their own dedicated line.

A comment line cannot be extended with a continuation using the same mechanism as values. To write a multi-line comment, start each line with its own comment marker.

## 4. Values: whitespace, quotes, and regular characters

Values can contain `=`, `:`, `#`, and `!` after the separator:

```properties
query=https://example.com/search?q=java#results
expression=a=b:c
notice=Save! # Not an inline comment
```

Once the start of the value has been determined, these characters no longer act as separators or comment markers.

### Leading and trailing whitespace

Plain whitespace immediately after the separator is ignored. If you want to preserve **a leading space in the value**, escape it:

```properties
trimmed=    hello
leading=\ hello
```

The result is `trimmed` → `"hello"` and `leading` → `" hello"`. Whitespace at the end of a logical line is not automatically trimmed; avoid accidental trailing spaces because they are hard to spot when comparing configurations.

### Quotes are not stripped automatically

```properties
title="Hello"
```

Here, the value **includes both double quotes**, meaning `"Hello"` as seen by the reader, rather than automatically becoming `Hello`. `.properties` has no JSON-style quoted-string syntax. Similarly, `roles=admin,user` is a single string containing a comma; if you want a list, you must define how to split and validate it yourself.

### Empty values and duplicate keys

`empty=` or just `empty` both produce an empty value. Within the same `Properties` file, if two lines have the same key, the later value overwrites the earlier one:

```properties
mode=development
mode=production
```

After `load`, `mode` has the value `production`. This behavior is useful to know for understanding the parser, but **you should not intentionally rely on duplicate keys** in a production file, as it easily leads to misconfiguration. You should not expect iterating keys via `Properties` to preserve the original line order from the file.

## 5. Line continuations: multiple natural lines as one logical line

When a line ends with an **odd number of consecutive backslashes**, the final `\` escapes the line terminator and joins the content of the next line. The continuation `\` and the newline character are **not** added to the value. Leading whitespace on the next line is ignored.

```properties
long.message=Hello, \
    Java \
    developer!
```

The parsed value is `Hello, Java developer!`. The spaces in the result come from the spaces written **before** the `\` after `Hello,` and after `Java`. The parser does not automatically insert spaces when joining lines.

Compare:

```properties
a=Hello\
    Java
b=Hello \
    Java
```

- `a` → `HelloJava`.
- `b` → `Hello Java`.

### The number of trailing `\` characters determines whether lines are joined

| End of line | Interpretation |
|---|---|
| One `\` | The next line is joined |
| Two `\\` | Becomes one literal backslash, **not joined** |
| Three `\\\` | One literal backslash and one continuation marker |
| Four `\\\\` | Two literal backslashes, **not joined** |

When lines are joined, a `#` or `!` at the start of the continued part is treated as part of the logical line, not as a standalone comment. To avoid confusion, do not place comments between the parts of a continued value.

### Distinguishing continuations from escaped newlines

```properties
joined=Hello\
    World
two.lines=Hello\nWorld
```

`joined` → `HelloWorld`, **with no newline**. `two.lines` is a string with an actual LF character between `Hello` and `World`. These serve two different purposes: wrapping source lines for readability, or storing a newline inside the value itself.

## 6. Important escape sequences

| Written in file | Character read | Purpose |
|---|---|---|
| `\t` | Tab | Insert a tab in the value |
| `\n` | Newline LF | Insert a line break in the value |
| `\r` | Carriage return CR | Special cases |
| `\f` | Form feed | Rarely used |
| `\\` | Single backslash `\` | Windows paths, regex |
| `\ ` | Single space | Space in a key or at the start of a value |
| `\=` | `=` | Equals sign in a key |
| `\:` | `:` | Colon in a key |
| `\#` and `\!` | `#` and `!` | Special characters in a key |
| `\u00E9` | `é` | 4-hex-digit Unicode escape |

In a `.properties` file, two backslashes `\\` represent one literal `\`. Distinguish this from Java source code: Java string literals also have their own escaping rules.

### Backslashes that are not special escapes

In `Properties.load(...)`, if a backslash precedes a character that is not a meaningful escape, the backslash may be **silently dropped**. For example, `a\qz` is read as `aqz`. Do not rely on the parser to warn about every backslash mistake.

Windows paths are very easy to get wrong:

```properties
bad.path=C:\temp\new
good.path=C:\\temp\\new
```

`bad.path` contains a tab from `\t` and a newline from `\n`, rather than the intended path. `good.path` is read as a path with single backslashes. When appropriate, you can use forward slashes `/` to reduce the need for escaping.

### Unicode escapes

`\uXXXX` requires **exactly four hex digits** representing a UTF-16 code unit. For example:

```properties
cafe=Caf\u00E9
hello=Xin ch\u00E0o
```

These become `Café` and `Xin chào`, respectively. Invalid Unicode escapes such as `\uZZZZ` can throw an `IllegalArgumentException` when loaded. Do not use `\u{1F600}` syntax because that is not a Java `Properties` Unicode escape; supplementary characters outside the BMP require two UTF-16 surrogate escapes when represented this way.

With a UTF-8 file loaded via a UTF-8 `Reader`, you can usually write Vietnamese directly instead of escaping every character.

## 7. Complete Java 17+ example: creating files, reading, and explaining stdout

Place **both files in the same directory** as follows.

### `app.properties`

```properties
# General configuration
! A second comment style

app.name = World Service
app\ title : Localization handbook
greeting: Hello!
long.message = Hello, \
    Java \
    developer!
path = C:\\data\\images
unicode = Caf\u00E9
inline = Value # still value
blank=
duplicate=first
duplicate=final
```

### `PropertiesSyntaxDemo.java`

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesSyntaxDemo {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(
                Path.of("app.properties"), StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        print(properties, "app.name");
        print(properties, "app title");
        print(properties, "greeting");
        print(properties, "long.message");
        print(properties, "path");
        print(properties, "unicode");
        print(properties, "inline");
        print(properties, "blank");
        print(properties, "duplicate");
    }

    private static void print(Properties properties, String key) {
        System.out.println(key + "=[" + properties.getProperty(key) + "]");
    }
}
```

Run:

```bash
javac PropertiesSyntaxDemo.java
java PropertiesSyntaxDemo
```

Output verified with `Properties.load`:

```text
app.name=[World Service]
app title=[Localization handbook]
greeting=[Hello!]
long.message=[Hello, Java developer!]
path=[C:\data\images]
unicode=[Café]
inline=[Value # still value]
blank=[]
duplicate=[final]
```

Output explanation:

1. `app\ title` creates a key containing a space: `app title`.
2. `long.message` joins three physical lines; the value keeps spaces between words because spaces were written before the continuation.
3. `path`: two backslashes in the file decode to one in the Java string.
4. `unicode`: `\u00E9` becomes `é`.
5. `inline` keeps the literal `#` in the middle of the value.
6. `blank` is an empty string, printed inside the square brackets.
7. `duplicate` is loaded twice; the second overwrites the first, resulting in `final`.

The program reads via `Files.newBufferedReader` with an explicit UTF-8 charset and automatically closes it using `try-with-resources`. If a key is missing, `properties.getProperty("missing")` returns `null` (unless the `Properties` object has matching defaults); you can use `getProperty("key", "fallback")` to specify a fallback value.

## 8. Encoding: Properties and PropertyResourceBundle differ

This is an essential API difference, especially for Vietnamese.

| Reading API | Encoding rule |
|---|---|
| `Properties.load(InputStream)` | **ISO-8859-1**, per the legacy `Properties` contract |
| `Properties.load(Reader)` | Uses **the Reader's charset**; UTF-8 can be chosen |
| `PropertyResourceBundle(InputStream)` on JDK 9+ | Prefers **UTF-8**; by default retries with ISO-8859-1 if the byte sequence is invalid UTF-8 |

Therefore, do not simply say that "every `.properties` file in Java 17 defaults to UTF-8." Java 9 switching *property resource bundles* to UTF-8 did not change `Properties.load(InputStream)`, which still reads ISO-8859-1.

### Reading a UTF-8 configuration file with Properties

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    Properties properties = new Properties();
    properties.load(reader);
}
```

This is a code snippet used inside a method that already has the relevant imports, not a standalone program. If you use `Properties.load(Files.newInputStream(...))` on a UTF-8 file containing non-ASCII characters, mojibake can occur due to ISO-8859-1 interpretation.

### Reading translation files via ResourceBundle

`PropertyResourceBundle(InputStream)` on JDK 17 defaults to preferring UTF-8. If it encounters a `MalformedInputException` or `UnmappableCharacterException` while decoding, it can re-read the stream using ISO-8859-1. The JVM property `java.util.PropertyResourceBundle.encoding` can force `UTF-8` or `ISO-8859-1`, and is evaluated at class initialization; changing it later does not necessarily take effect. `PropertyResourceBundle(Reader)` still depends on the Reader's encoding.

So align on an encoding convention with your build tools, keep files in UTF-8, and test with the exact JDK and API actually used. If you need to catch encoding errors early, intentionally configure strict UTF-8.

## 9. .properties files for localization with ResourceBundle

Suppose the classpath has two files:

```text
Messages.properties
Messages_vi.properties
```

Contents of `Messages.properties`:

```properties
welcome=Hello!
button.save=Save
```

Contents of `Messages_vi.properties`:

```properties
welcome=Xin chào!
button.save=Lưu
```

Place these files **at the classpath root** alongside `BundlePropertiesDemo.java` to run manually:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundlePropertiesDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", locale);

        System.out.println(bundle.getString("welcome"));
        System.out.println(bundle.getString("button.save"));
        System.out.println(bundle.getLocale().toLanguageTag());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BundlePropertiesDemo.java
java -cp . BundlePropertiesDemo
```

Output:

```text
Xin chào!
Lưu
vi
```

Java requests `vi-VN` and finds `Messages_vi.properties`, so the resolved bundle has locale `vi`. If a project uses Maven or Gradle, resources usually live under `src/main/resources` and are copied into the classpath output during the build; the source path alone is not enough for the file to be found at runtime.

The internal syntax of `Messages_vi.properties` is still key/value pairs with comments, escapes, and continuations as described in the previous sections. When a key does not exist in the language bundle but exists in a parent bundle, `ResourceBundle.getString(...)` can retrieve the value from the parent; `bundle.getLocale()` still reflects the locale of **the selected bundle**, not necessarily the origin of every key.

## 10. Common mistakes when writing .properties files

1. **Forgetting to escape spaces or separator characters in keys.** `first name=Lan` is different from `first\ name=Lan`.
2. **Adding an inline comment on a key/value line.** Anything after `#` or `!` in a value is not automatically stripped.
3. **Using `//` as a comment.** This is not a standard comment marker.
4. **Assuming quotes around a value are stripped.** `title="Hello"` includes the quotes.
5. **Confusing line continuation with `\n`.** Line continuation does not insert a newline; `\n` inserts an actual LF into the value.
6. **Overlooking the space before `\` at the end of a line.** It can decide whether the value is `HelloWorld` or `Hello World`.
7. **Using single backslashes in Windows paths.** `\t` and `\n` have escape meanings.
8. **Believing unrecognized escapes throw errors.** `\q` can become `q`; you must verify the actual values.
9. **Assuming `Properties.load(InputStream)` defaults to UTF-8 since Java 9.** Its contract is still ISO-8859-1.
10. **Failing to distinguish config files from ResourceBundle files.** They share the same syntax but have different charset and fallback rules depending on the API.
11. **Leaving unintentional duplicate keys.** Later occurrences overwrite earlier ones.
12. **Assuming key order is preserved after loading.** `Properties` does not guarantee iteration in the original file line order.
13. **Assuming values are parsed into numbers or booleans.** Convert types, validate, and handle errors separately.
14. **Using `store` to "reformat while keeping the file intact."** `Properties.store` may add timestamps/comments and rewrite escaping and ordering; it does not preserve original comments or layout.
15. **Placing translation files in the wrong classpath location or with the wrong filename.** `ResourceBundle.getBundle("Messages", ...)` requires the corresponding resource in a loadable location.

## 11. Self-check

- `x=y=z` → key **`x`**, value **`y=z`**.
- `user\ name=Lan` → key **`user name`**, value **`Lan`**.
- `message=Hello #note` → value **`Hello #note`**.
- `a=Hello\` followed by continued line `World` → value **`HelloWorld`**.
- `a=Hello\nWorld` → value contains a newline character between the two words.
- `path=C:\\tools` → value contains a single backslash before `tools`.
- `name=first` and later `name=second` → value **`second`**.
- `Properties.load(Reader UTF-8)` reads UTF-8 Unicode characters via the Reader; `Properties.load(InputStream)` reads **ISO-8859-1**.

**References:** [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) · [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) · [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html).
