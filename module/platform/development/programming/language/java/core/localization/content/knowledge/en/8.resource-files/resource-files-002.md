# Escape Characters, Unicode Escapes, and Key Separators in Resource Files

## 1. Objectives and scope

In Java Core Localization, `.properties` resource files typically contain **key = value** pairs for `ResourceBundle`, for example:

```properties
app.title=Ứng dụng học Java
menu.open=Mở
menu.close=Đóng
```

The format looks like plain text, but it has **its own parsing rules**. `=`, `:`, whitespace, the backslash `\`, and `\uXXXX` sequences all have special meanings. If written incorrectly, a program can read **a different key than intended**, produce truncated values, lose `\` characters, or throw an exception when loading resources.

After this lesson, you should be able to:

- Distinguish **separators between keys and values** from characters that belong to the key itself.
- Correctly write keys containing spaces, `:`, `=`, `#`, `!`, or `\`.
- Understand `\t`, `\n`, `\r`, `\f`, `\\`, and `\uXXXX` escapes, as well as how unrecognized `\` characters are handled.
- Recognize that Unicode escapes represent **UTF-16 code units**, and characters outside the BMP require a surrogate pair if written entirely with escapes.
- Distinguish `.properties` escape processing from how Java source code interprets string literals.
- Choose the right encoding when using `PropertyResourceBundle` and `Properties.load(...)` on Java 17+, and handle line continuations properly.

This content focuses on **resource file syntax**; selecting bundles by language, region, and fallback is a separate step handled by `ResourceBundle`.

## 2. How is a `.properties` line parsed?

For `java.util.Properties` and `PropertyResourceBundle`, each normal **logical line** describes one key/value pair. The reader scans the key from the first non-whitespace character up to **the first unescaped `=`, `:`, or whitespace**. If whitespace follows the key, it skips that whitespace, optionally skips one `=` or `:`, and then skips any remaining whitespace before the value. The rest of the line is the value.

The following three lines are equivalent:

```properties
greeting=Hello
greeting: Hello
greeting Hello
```

All three have the key `greeting` and the value `Hello`. If they appear in **the same file**, later definitions overwrite earlier ones; this is a syntax example, not a recommended practice for placing three duplicate-key entries.

### The first separator decides where the key ends

| Source line | Actual key | Actual value |
| --- | --- | --- |
| `name=Alice` | `name` | `Alice` |
| `name:Alice` | `name` | `Alice` |
| `name Alice` | `name` | `Alice` |
| `a=b=c` | `a` | `b=c` |
| `a:b=c` | `a` | `b=c` |
| `user name=Alice` | `user` | `name=Alice` |
| `user\ name=Alice` | `user name` | `Alice` |
| `a\:b=Alice` | `a:b` | `Alice` |
| `a\=b:Alice` | `a=b` | `Alice` |
| `noValue` | `noValue` | empty string |

Between key and value, use `=` consistently for readability. **Colons `:` and equals signs `=` inside a value do not need escaping** once the reader has determined the key/value boundary. For instance:

```properties
url=https://example.org:8443/search?q=java
```

The key is `url` and the entire URL is the value. The `:` and `=` on **the value side** are normal data.

The whitespace characters that the parser treats as separators are **space (U+0020), tab (U+0009), and form feed (U+000C)**. Do not assume every Unicode character with a "whitespace" property is handled as a `.properties` separator.

## 3. Escaping special characters in keys

### 3.1. Whitespace and separators

When `=`, `:`, or whitespace is **part of the key name**, place `\` before it:

```properties
user\ name=Alice
service\:port=8080
data\=version=v2
leading\ space=yes
```

The keys after loading are, respectively:

```text
user name
service:port
data=version
leading space
```

For a key **starting with whitespace**, you must also escape the leading whitespace if you want to preserve it. For a key **ending with whitespace**, you can write `title\ =...`; however, you should avoid keys with leading or trailing spaces because they are hard to see and easy to mistype in code. In real projects, keys such as `account.name` or `menu.save` are simpler and more reliable.

### 3.2. `#` and `!`: comment or part of a key?

A line becomes a **comment** if its first non-whitespace character is `#` or `!`:

```properties
# UI translations
   ! Note for maintainers
title=Trang chủ
```

If you truly want a key **starting** with `#` or `!`, you can escape it:

```properties
\#literal=Hash key
\!important=Bang key
```

The keys are `#literal` and `!important`. When `#` or `!` appears **in the middle of a key**, such as `version#1=...`, no escape is needed to prevent a comment: comment markers are only special at the start of a line after skipping leading whitespace.

Inside a value, `#` and `!` are ordinary characters:

```properties
notice=Quan trọng! Xem #huongdan
```

No comment begins in the middle of the value here. Do not treat `#` after `=` as end-of-line comment syntax.

### 3.3. Preserving literal backslashes

`\` is the escape introducer. To get **one literal `\` in the loaded data**, write **two backslashes `\\`** in the file:

```properties
folder=C:\\data\\reports
key\\part=backslash
```

Result:

- Value of `folder`: `C:\data\reports`.
- Key `key\part` is a key name containing one backslash.

A common mistaken example:

```properties
folder=C:\temp\reports
```

`\t` becomes a tab and `\r` becomes a carriage return; after loading, the path is **no longer** the intended path. When storing Windows paths, either write `C:\\temp\\reports`, use `/` where appropriate for the API/system, or choose a clearly controlled storage format.

## 4. Valid escapes and how they are interpreted

Within keys and values, the basic `.properties` escape set includes:

| Form in file | Character after loading | Notes |
| --- | --- | --- |
| `\t` | Tab (U+0009) | Not the two characters `\` and `t` |
| `\n` | Newline LF (U+000A) | A character inside the value/key |
| `\r` | Carriage return (U+000D) | Distinct from LF |
| `\f` | Form feed (U+000C) | Rarely used |
| `\\` | One `\` | How to store a literal backslash |
| `\=` | `=` | Needed when the character belongs to the key |
| `\:` | `:` | Needed when the character belongs to the key |
| `\ ` | Space (U+0020) | Preserves space in a key or at the start of a value |
| `\u0041` | `A` (U+0041) | Exactly **four hex digits** |
| `\u00E9` | `é` (U+00E9) | One UTF-16 code unit |

**Note the difference from Java string literals:** the `.properties` parser **does not** support `\b` as backspace and **does not** support octal escapes. If `\` precedes a character outside the recognized escape set, the parser usually **drops the `\` and keeps the next character**. For example, `x=\q` reads the value `q` without throwing an error for an invalid `\q`; this is why mistyped escapes can silently corrupt data.

Single and double quotes **do not need escaping** in ordinary `.properties` values:

```properties
quote=He said "Hello"
name=O'Reilly
```

If you use `MessageFormat` to format values with placeholders, single quotes have **MessageFormat's own rules** and must be handled at the message-formatting layer; those are not `.properties` escape rules.

## 5. Unicode escapes: what is `\uXXXX`?

A Unicode escape in `.properties` has the form **`\u` followed immediately by exactly four hexadecimal digits** (0–9, A–F, a–f), for example:

```properties
letter=\u0041
cafe=caf\u00E9
vietnam=Xin ch\u00E0o
```

When loaded, the corresponding values are `A`, `café`, and `Xin chào`. The character `é` does not have to be written as `\u00E9` in UTF-8 files meant for Java 9+ `ResourceBundle`, though escaping remains valid syntax and is useful when files need an ASCII representation.

**Important point:** `\uXXXX` encodes **one UTF-16 code unit**, not an arbitrary Unicode syntax that allows more than four digits. For example, the rocket character 🚀 (U+1F680) lies outside the Basic Multilingual Plane (BMP); its traditional escape form is **a surrogate pair**:

```properties
rocket=\uD83D\uDE80
```

The two parts `D83D` (high surrogate) and `DE80` (low surrogate) form one U+1F680 code point when decoded into a valid Java string. Writing a single escape `\u1F680` is **incorrect for representing the intended character**: `\u` consumes only four hex digits, and the remaining characters do not represent U+1F680 as you might expect.

### Malformed Unicode escapes

```properties
broken=\u12G4
```

This is a malformed escape because `G` is not a hex digit. When loaded with `Properties.load`, it can throw `IllegalArgumentException` for a malformed Unicode escape. This error is distinct from **file bytes being decoded with the wrong charset**; you must separate escape syntax from byte encoding.

Do not write `\uu0041` with two `u`s expecting the `.properties` parser to behave like certain Java source Unicode escapes; `.properties` uses only **one `u`** before four hex digits.

### Why must you distinguish this from Java source Unicode escapes?

The Java compiler processes Unicode escapes from **source code before tokenization**, whereas a `.properties` file is **read at runtime** and then the parser processes escapes. When putting `.properties` file text into a `String` in a Java test, `\` belongs to **two different syntactic layers**:

```java
// The runtime String characters are: \u0041
String propertyLine = "letter=\\u0041";

// After Properties.load(...), key "letter" has value "A".
```

This is an **illustrative snippet inside a method**, not a standalone Java file. It shows that the Java literal `\\` produces one `\` in the runtime string; the `.properties` parser then sees `\u0041` and decodes it to `A`. Avoid using a "single escape layer" explanation for both Java source and resource files.

## 6. Line continuation with a trailing backslash

A key/value pair can span multiple **natural lines** while remaining **one logical line**. When a line ends with an **odd number of consecutive backslashes**, the last `\` escapes the newline; the parser discards the continuation `\`, the newline, and leading whitespace on the next line, then joins the remainder:

```properties
description=Học Java, \
    tìm hiểu Locale, \
    và đọc resource bundle.
```

Resulting value:

```text
Học Java, tìm hiểu Locale, và đọc resource bundle.
```

Note: the spaces **before the `\` at the end of the first two lines** remain part of the value and keep the words separated. If you write:

```properties
message=hello\
   world
```

The value will be `helloworld`, **not** `hello world`. To have a space between the two words, write `hello \` or place an escaped space in the appropriate continuation segment. Leading whitespace on the next line is **discarded**, not automatically converted into a space.

When there is an **even number of consecutive `\` characters** at the end of a line, those backslashes pair up into literal backslashes, and the line terminator is not escaped by an odd trailing backslash. Therefore, you cannot look only at the last character being `\` and conclude it is always a continuation; you must count the entire trailing run of consecutive `\` characters.

A comment line does not use this continuation mechanism; comment lines remain processed independently. Conversely, after a data line being continued, a `#` on the continued line does not automatically start a new comment as you might expect: it is part of the continuing logical line.

## 7. Standalone Java 17+ example: verifying keys and escapes

This example uses `java.util.Properties.load(Reader)` to demonstrate the exact syntax also used by `PropertyResourceBundle`; the test input is built at runtime without needing a physical file. Filename: `PropertiesSyntaxDemo.java`.

```java
import java.io.StringReader;
import java.util.Properties;

public class PropertiesSyntaxDemo {
    public static void main(String[] args) throws Exception {
        String source = String.join("\n",
                "# comment",
                "! note",
                "plain=xin chao",
                "a\\:b=colon-key",
                "x\\=y: equals-key",
                "user\\ name=space-key",
                "\\#literal=hash-key",
                "\\!bang=bang-key",
                "empty",
                "spaces=\\ leading",
                "line=first\\nsecond",
                "continued=one\\",
                "    two",
                "rocket=\\uD83D\\uDE80",
                "path=C:\\\\temp\\\\config");

        Properties properties = new Properties();
        properties.load(new StringReader(source));

        System.out.println("plain=" + properties.getProperty("plain"));
        System.out.println("a:b=" + properties.getProperty("a:b"));
        System.out.println("x=y=" + properties.getProperty("x=y"));
        System.out.println("user name=" + properties.getProperty("user name"));
        System.out.println("#literal=" + properties.getProperty("#literal"));
        System.out.println("!bang=" + properties.getProperty("!bang"));
        System.out.println(
                "empty.length=" + properties.getProperty("empty").length());
        System.out.println(
                "spaces.startsWithSpace="
                + properties.getProperty("spaces").startsWith(" "));
        System.out.println(
                "line=" + properties.getProperty("line")
                        .replace("\n", "<NL>"));
        System.out.println(
                "continued=" + properties.getProperty("continued"));
        System.out.println(
                "rocket=" + Integer.toHexString(
                        properties.getProperty("rocket").codePointAt(0)));
        System.out.println("path=" + properties.getProperty("path"));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 PropertiesSyntaxDemo.java
java PropertiesSyntaxDemo
```

Stdout:

```text
plain=xin chao
a:b=colon-key
x=y=equals-key
user name=space-key
#literal=hash-key
!bang=bang-key
empty.length=0
spaces.startsWithSpace=true
line=first<NL>second
continued=onetwo
rocket=1f680
path=C:\temp\config
```

The output clearly illustrates the two escape layers:

- For a `\` character to appear in Java's `source` data, the string literal writes `\\`; then the properties parser processes the escapes according to file syntax.
- `a\:b` and `x\=y` become keys containing separator characters; they are not split into two parts.
- `\#literal` and `\!bang` are real keys, not interpreted as comments.
- The `empty` line without a separator still creates an empty value.
- `spaces=\ leading` preserves one leading space in the value.
- `line=first\nsecond` creates a real LF newline, printed as `<NL>` purely for easy observation.
- `continued=one\` joins with the `two` line to form `onetwo`.
- The surrogate pair `\uD83D\uDE80` returns code point `1f680` (hexadecimal) when read with `codePointAt`.
- `path=C:\\temp\\config` preserves the path's backslashes.

In production code, there is no need to construct test strings like this manually; simply write valid `.properties` files and load them with `ResourceBundle`. `PropertiesSyntaxDemo` helps you **verify the parser accurately** and reproduce bugs while learning.

## 8. UTF-8, Latin-1, and Unicode escapes: three easily confused concepts

**Escape syntax** is how characters are represented inside `.properties` content, whereas **charset** determines how bytes are converted into characters **before parsing**. Different APIs have different rules:

| Reading approach | Default charset / behavior | Key takeaway |
| --- | --- | --- |
| `Properties.load(InputStream)` | **ISO-8859-1** | API contract still present on Java 17+; UTF-8 bytes for Vietnamese may be misread |
| `Properties.load(Reader)` | Determined by the chosen `Reader` | Use `InputStreamReader(..., UTF_8)` or `Files.newBufferedReader(..., UTF_8)` to read UTF-8 |
| `PropertyResourceBundle(InputStream)` (Java 9+) | Tries **UTF-8** first; falls back to **ISO-8859-1** on malformed/unmappable UTF-8 bytes | Can be forced with the system property `java.util.PropertyResourceBundle.encoding` set at startup |
| `PropertyResourceBundle(Reader)` | Uses characters already decoded by `Reader` | No reason to guess charset from strings after reading |
| `ResourceBundle.getBundle(...)` for `.properties` bundles (Java 9+) | Java 9+ properties bundle mechanism, typically UTF-8 first | Files can contain Unicode directly while still supporting `\uXXXX` |

Note that `-Djava.util.PropertyResourceBundle.encoding=UTF-8` or `ISO-8859-1` applies to `PropertyResourceBundle` at class initialization; it does not change the contract of `Properties.load(InputStream)`. If UTF-8 is forced, invalid byte sequences can trigger an error instead of falling back to Latin-1. When creating new bundles, standardize on **UTF-8**, save files with the right encoding, and test with your runtime and build tools.

With a real UTF-8 file:

```properties
welcome=Chào mừng bạn
farewell=Tạm biệt
```

On Java 17+, `ResourceBundle` can read Unicode directly from `.properties`; there is no need to convert everything into `\uXXXX` just because older Java 8 guides required Latin-1. However, **`Properties.load(InputStream)` does not automatically switch to UTF-8**; the two API classes have different compatibility histories.

### Runnable example: one UTF-8 string, two ways of reading

File `PropertiesEncodingDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        String original = "Tiếng Việt";
        byte[] bytes = ("greeting=" + original + "\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties utf8 = new Properties();
        try (var reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {
            utf8.load(reader);
        }

        Properties latin1 = new Properties();
        latin1.load(new ByteArrayInputStream(bytes));

        System.out.println(
                utf8.getProperty("greeting").equals(original));
        System.out.println(
                latin1.getProperty("greeting").equals(original));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
```

Output:

```text
true
false
```

Both objects read **the exact same initial byte array**, yet `load(Reader)` decodes UTF-8 correctly while `load(InputStream)` interprets the bytes as Latin-1. This is a **charset** issue that cannot be solved by changing `Locale.setDefault(...)` or `Locale.forLanguageTag(...)`.

## 9. Loading real resources with `ResourceBundle`

Suppose you create `Messages_vi_VN.properties` (UTF-8, on the classpath):

```properties
welcome=Xin chào
menu.open=Mở
service\:port=Cổng dịch vụ
line.break=Hàng 1\nHàng 2
rocket=\uD83D\uDE80
```

Then, in a class with access to the resource:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceMessageDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        System.out.println(bundle.getString("welcome"));
        System.out.println(bundle.getString("service:port"));
        System.out.println(bundle.getString("rocket").codePointAt(0));
    }
}
```

Place **both files in the same classpath directory** as the example's default-package class, then run:

```bash
javac -encoding UTF-8 ResourceMessageDemo.java
java -cp . ResourceMessageDemo
```

Output when using the given file on Java 17+ with default settings:

```text
Xin chào
Cổng dịch vụ
128640
```

The key name passed to `getString(...)` must be **the name after the parser has unescaped it**: use `"service:port"`, not `"service\\:port"`. `128640` is the decimal code point of U+1F680 (🚀). If the bundle or key cannot be found, the API can throw `MissingResourceException`; that is a lookup error, separate from malformed `\uXXXX` escapes in the file.

Note: Java resource files follow naming conventions like `Messages_vi_VN.properties`, using underscores per `ResourceBundle`. This syntax differs from BCP 47 language tags (`vi-VN`), which use hyphens. Separators in **filenames** and separators in **key/value contents** are two different rule sets.

## 10. Common mistakes and how to fix them

| Mistake | Wrong result | Fix |
| --- | --- | --- |
| `user name=...` while code calls `getString("user name")` | File only has key `user` | Use `user\ name=...` or standardize on `user.name` |
| `server:port=8080` when wanting key `server:port` | Key is `server` | Write `server\:port=8080` |
| `flag=one#comment` expecting `#comment` to be stripped | Value contains literal `one#comment` | Put comments on a separate line |
| `folder=C:\temp` | `\t` becomes a tab | Use `folder=C:\\temp` |
| `x=\q` thinking the parser reports an error | `\` is usually dropped, value becomes `q` | Only use defined escapes |
| `\u12G4` | Malformed Unicode escape | Write exactly four hex digits |
| `\u1F680` to store a non-BMP emoji | Does not represent U+1F680 as intended | Use `\uD83D\uDE80` or direct Unicode in UTF-8 |
| Putting unescaped whitespace at the start of a value | Whitespace before value is usually stripped | Use `\ ` for spaces that must be kept |
| Expecting line continuation to insert a space automatically | Parser drops newline and next line's leading whitespace | Insert an explicit space before `\` |
| Calling `Properties.load(InputStream)` on a UTF-8 file | Vietnamese characters are decoded incorrectly | Use `load(Reader)` with UTF-8, or `ResourceBundle` per its contract |
| Confusing Java source `\\` syntax with `.properties` | `\` is escaped wrongly in one or two layers | Check the runtime string and file separately |
| Storing the same key multiple times | The last value overwrites previous ones | Use unique keys and check for duplicates |

## 11. Self-check

1. In a `.properties` file, what key does `host:port=8080` create? **`host`**, with value `port=8080`; to get the key `host:port`, you must write `host\:port=8080`.
2. Does `menu.open=Mở` require escaping the dot? **No**. `.` is not a key delimiter; dotted structure is only a key-naming convention.
3. Does `title=Hello # note` strip `# note`? **No**. The value contains both `#` and everything after it.
4. How do you write a literal backslash `\` in a value? **`\\`** in the properties file.
5. Why does the Unicode escape for 🚀 need two `\uXXXX` sequences? **Because each escape holds one UTF-16 code unit, while U+1F680 is represented by a surrogate pair**.
6. What value does `name=hello\` joined with `   world` produce? **`helloworld`**; no space is added automatically.
7. Do `Properties.load(InputStream)` and `PropertyResourceBundle(InputStream)` share the same default charset on Java 17? **No**. `Properties` uses ISO-8859-1; `PropertyResourceBundle` tries UTF-8 first and has a fallback mechanism.
8. When the file contains `service\:port=8080`, does `bundle.getString("service:port")` look it up correctly? **Yes**, because the unescaped key is `service:port`.
9. When should you write Vietnamese directly instead of `\uXXXX`? **When using Java 9+ with UTF-8 resource bundles and tooling that saves files in the correct encoding**; you still need to know which API the application uses to read the file.

## References

- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): logical line syntax, key separators, escapes, Unicode, and `load(InputStream)`/`load(Reader)`.
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8/ISO-8859-1 bundle reading behavior on Java 9+.
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): bundle lookup and using `getString`.
- [Java SE 21 — Java Language Specification, Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.3): how the Java compiler processes Unicode escapes in **source code**, distinct from the `.properties` parser.
