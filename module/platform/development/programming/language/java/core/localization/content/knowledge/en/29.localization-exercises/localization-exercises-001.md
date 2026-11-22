# Comprehensive Practice: Building a Language-Switching CLI Program with ResourceBundle in Java

## 1. Objectives and Deliverable

This hands-on exercise builds a **CLI (command-line interface)** running on Java 17 or later. Users can **switch languages mid-session** without restarting the JVM. The program supports the following commands:

| Command | Effect |
| --- | --- |
| `help` | Displays usage instructions in the current language |
| `lang en` | Switches messages to English |
| `lang vi` | Switches messages to Vietnamese |
| `greet NAME` | Prints a greeting with a dynamic name |
| `count N` | Prints the message count; formats the number according to the locale |
| `quit` | Exits with a localized farewell message |

Example interactive session:

```text
Language Switch CLI
Welcome! Type help for commands.
Commands: lang en | lang vi | greet NAME | count N | help | quit
> greet Lan
Hello, Lan!
> count 1234
You have 1,234 messages.
> lang vi
Đã chuyển sang tiếng Việt.
> greet Minh
Xin chào, Minh!
> count 1234
Bạn có 1.234 tin nhắn.
> help
Lệnh: lang en | lang vi | greet TÊN | count N | help | quit
> lang en
Language switched to English.
> quit
Goodbye!
```

The `>` character is the program prompt; the lines following the prompt are commands typed by the user. For the number `1234`, US English typically uses a comma as the thousands separator, whereas Vietnamese in Vietnam typically uses a dot. This presentation depends on the JDK's locale data; the output above illustrates formatting in a modern JDK. Terminal fonts/encoding can affect the display of Vietnamese diacritics without changing the underlying behavior of `ResourceBundle`.

After completing this exercise, you will know how to:

1. Separate **CLI control logic** from **display language**.
2. Create and organize `.properties` files using the proper **base name**, **classpath root**, and **locale suffix**.
3. Use `Locale`, `ResourceBundle.getBundle`, `getString`, and `MessageFormat`.
4. Switch languages in a controlled way without calling `Locale.setDefault` across the entire JVM.
5. Format dynamic arguments, counts, and complete sentences.
6. Handle input validation, unsupported languages, missing keys, resource errors, and encoding.
7. Compile, run, package as a JAR, and test a practical i18n application.

## 2. Architecture: Language-Independent Business Data

The application has two layers of responsibility:

- **CLI Logic:** reads commands, validates input, stores the currently selected language, and dispatches to the corresponding functionality.
- **Localization:** selects the `ResourceBundle` matching the locale, retrieves message patterns by key, and formats data.

Conceptual diagram:

```text
User enters "count 1234"
             |
             v
   CLI command handler
             |
             v
   Parse number 1234 (long)
             |
             v
  Select message key "count.other"
             |
             v
 ResourceBundle for current locale
             |
             v
   MessageFormat with argument [1234]
             |
             v
  "You have 1,234 messages."
              or
  "Bạn có 1.234 tin nhắn."
```

**Important:** the program does **not** write `if (locale == vi) System.out.println("Bạn có...")` for every sentence. It uses the **same key**, while the resource files supply the corresponding sentence pattern. As a result, adding a new language mainly involves adding translations and updating the supported language list, without duplicating the entire command-handling logic.

### Key Names Must Be Stable and Describe Purpose

The key set for this exercise:

| Key | Meaning |
| --- | --- |
| `app.name` | Neutral application name |
| `welcome` | Welcome line |
| `help` | Command syntax |
| `language.changed` | Language switch success message |
| `greeting` | Greeting sentence with name argument `{0}` |
| `count.one` | Count sentence when `N == 1` |
| `count.other` | Count sentence for all other non-negative integers |
| `error.locale` | Unsupported language code |
| `error.name` | Missing name for the `greet` command |
| `error.number` | Invalid count value |
| `error.command` | Unrecognized command |
| `goodbye` | Exit message |

These are technical keys: **key names do not need to be translated**. Translators only edit the corresponding values. Avoid naming keys `message1`, `message2`, because their purpose is unclear and translations become hard to manage.

## 3. Proper Directory Structure for Java to Locate Bundles

This simple project **requires no external libraries**:

```text
language-cli/
├── src/
│   └── main/
│       ├── java/
│       │   └── LanguageCli.java
│       └── resources/
│           ├── Messages.properties
│           ├── Messages_en.properties
│           └── Messages_vi.properties
└── out/                      # directory created after javac
```

Because the `.properties` files are placed **directly at the resource directory root**, the base name is `"Messages"`, not `"src.main.resources.Messages"` and not `"Messages.properties"`. When the classpath includes `src/main/resources`, or when the files are copied to the **JAR root**, Java looks for:

```text
Messages.properties
Messages_en.properties
Messages_vi.properties
```

If you place resources deeper, such as `src/main/resources/com/example/i18n/Messages_vi.properties`, the corresponding base name must be `com.example.i18n.Messages`. Do not pass a filesystem path to `getBundle`.

A typical call:

```java
ResourceBundle messages =
        ResourceBundle.getBundle("Messages", locale);
```

Java uses the base name, locale, and classpath/module lookup mechanism to load resources. With `Locale.US` (language `en`) and the files above, `Messages_en.properties` is selected; with `vi-VN`, it looks for `Messages_vi_VN.properties` if present and then `Messages_vi.properties`. Keys missing in a child bundle can be looked up in parent bundles such as `Messages.properties`.

### Why Do We Need a Root Messages.properties?

A `Messages.properties` file without a locale suffix acts as the root fallback. This exercise keeps a **complete English version** in the root as a fallback and places locale-specific translations in separate files. For instructional clarity, `Messages_en.properties` is provided in full even though many keys overlap with the root. In real-world projects, you can choose a source language as the root or define a custom fallback policy, but you must verify translation coverage before release.

**Fallback is not an official way to support a language:** `ResourceBundle.getBundle("Messages", Locale.forLanguageTag("xx"))` can still find the root and return English. Therefore, the CLI must **restrict supported language codes itself**, rather than relying on an exception to detect an invalid `xx` request.

## 4. Creating the Root Resource and Translations

All three files below are **UTF-8 files**. Java 9+ supports UTF-8 for `PropertyResourceBundle` under JEP 226, with a compatibility mechanism that falls back to ISO-8859-1 when bytes are not valid UTF-8. `Properties.load(InputStream)` is a different API and should not be confused with this rule.

### 4.1. src/main/resources/Messages.properties

```properties
app.name=Language Switch CLI
welcome=Welcome! Type help for commands.
help=Commands: lang en | lang vi | greet NAME | count N | help | quit
language.changed=Language switched to English.
greeting=Hello, {0}!
count.one=You have {0,number,integer} message.
count.other=You have {0,number,integer} messages.
error.locale=Unsupported language. Use en or vi.
error.name=Please provide a name.
error.number=Enter a non-negative integer.
error.command=Unknown command. Type help.
goodbye=Goodbye!
```

The root file contains all keys. This matters when a translation is missing a key: Java can retrieve it from the parent bundle instead of immediately failing. However, in a translation pipeline, you should still detect omitted keys.

### 4.2. src/main/resources/Messages_en.properties

```properties
welcome=Welcome! Type help for commands.
help=Commands: lang en | lang vi | greet NAME | count N | help | quit
language.changed=Language switched to English.
greeting=Hello, {0}!
count.one=You have {0,number,integer} message.
count.other=You have {0,number,integer} messages.
error.locale=Unsupported language. Use en or vi.
error.name=Please provide a name.
error.number=Enter a non-negative integer.
error.command=Unknown command. Type help.
goodbye=Goodbye!
```

Note that `app.name` is absent from the `_en` file. It is inherited from the root; this is intentional to demonstrate **parent bundle lookup**. Even though `Locale.US` has no `Messages_en_US.properties` file, Java still finds `Messages_en.properties` and resolves `app.name` from the root.

### 4.3. src/main/resources/Messages_vi.properties

```properties
welcome=Chào mừng! Gõ help để xem các lệnh.
help=Lệnh: lang en | lang vi | greet TÊN | count N | help | quit
language.changed=Đã chuyển sang tiếng Việt.
greeting=Xin chào, {0}!
count.one=Bạn có {0,number,integer} tin nhắn.
count.other=Bạn có {0,number,integer} tin nhắn.
error.locale=Ngôn ngữ không hỗ trợ. Hãy dùng en hoặc vi.
error.name=Vui lòng nhập tên.
error.number=Nhập số nguyên không âm.
error.command=Lệnh không hợp lệ. Gõ help.
goodbye=Tạm biệt!
```

Here, the two keys `count.one` and `count.other` share the same Vietnamese phrasing. **That is a grammatical choice for the two illustrated languages, not a rule that every language only has two plural categories.** English requires `message`/`messages`, whereas Vietnamese does not inflect the noun by count in this example sentence. For Arabic, Russian, or other languages, plural selection rules must follow CLDR or an appropriate framework rather than just `N == 1`.

### Placeholders Are Data, Not Text to Translate

Patterns:

```properties
greeting=Xin chào, {0}!
count.other=Bạn có {0,number,integer} tin nhắn.
```

Use `{0}` as the argument position. `MessageFormat` substitutes the content without requiring translators to know Java variable names. The `{0,number,integer}` syntax indicates that the argument is a number and should be formatted as an integer according to the locale.

If a translation needs to reorder information, the placeholder can move within the pattern while the Java code still passes the same argument array. **Do not split sentences into multiple fragments and concatenate strings**, because each language has a different grammatical word order.

## 5. Implementing a Complete LanguageCli.java on Java 17+

Create the file **src/main/java/LanguageCli.java**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class LanguageCli {
    private static final String BUNDLE_BASE = "Messages";
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    // Language state belongs specifically to this CLI instance.
    private Locale locale = Locale.US;
    private ResourceBundle messages =
            ResourceBundle.getBundle(BUNDLE_BASE, locale);

    private String tr(String key) {
        return messages.getString(key);
    }

    private String trf(String key, Object... arguments) {
        return new MessageFormat(tr(key), locale)
                .format(arguments);
    }

    private void changeLanguage(String code) {
        Locale requested;
        switch (code.toLowerCase(Locale.ROOT)) {
            case "en" -> requested = Locale.US;
            case "vi" -> requested = VI;
            default -> {
                System.out.println(tr("error.locale"));
                return;
            }
        }

        ResourceBundle selected =
                ResourceBundle.getBundle(BUNDLE_BASE, requested);
        locale = requested;
        messages = selected;
        System.out.println(tr("language.changed"));
    }

    private void run() throws IOException {
        try (BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8))) {

            System.out.println(tr("app.name"));
            System.out.println(tr("welcome"));
            System.out.println(tr("help"));

            while (true) {
                System.out.print("> ");
                System.out.flush();

                String line = input.readLine();
                if (line == null) {
                    // EOF when stdin closes: avoid an infinite loop.
                    System.out.println();
                    return;
                }

                line = line.strip();
                if (line.isEmpty()) {
                    continue;
                }

                String[] parts = line.split("\\s+", 2);
                String command = parts[0].toLowerCase(Locale.ROOT);
                String argument = parts.length == 2
                        ? parts[1].strip() : "";

                switch (command) {
                    case "help" -> System.out.println(tr("help"));
                    case "lang" -> changeLanguage(argument);
                    case "greet" -> {
                        if (argument.isBlank()) {
                            System.out.println(tr("error.name"));
                        } else {
                            System.out.println(
                                    trf("greeting", argument));
                        }
                    }
                    case "count" -> {
                        try {
                            long count = Long.parseLong(argument);
                            if (count < 0) {
                                System.out.println(
                                        tr("error.number"));
                            } else {
                                String key = count == 1
                                        ? "count.one"
                                        : "count.other";
                                System.out.println(trf(key, count));
                            }
                        } catch (NumberFormatException ex) {
                            System.out.println(
                                    tr("error.number"));
                        }
                    }
                    case "quit" -> {
                        System.out.println(tr("goodbye"));
                        return;
                    }
                    default -> System.out.println(
                            tr("error.command"));
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        new LanguageCli().run();
    }
}
```

This is a **single standalone Java class in terms of source code**, but the program requires the three `Messages*.properties` files **on the runtime classpath**. On Java 17+, syntax features such as `switch ->`, `String.strip()`, and `String.isBlank()` are all supported.

### 5.1. Why Does Locale State Live on the Instance?

`locale` and `messages` are fields of a **single `LanguageCli` instance**, not global JVM state. When the user types `lang vi`, only that instance updates its bundle.

Do not do the following:

```java
Locale.setDefault(Locale.forLanguageTag("vi-VN"));
```

Changing the JVM's default locale affects other libraries/components that rely on the default locale implicitly and can cause conflicts when an application serves multiple users. Even a single-user CLI should pass the locale explicitly so the design easily scales to a server or multi-session interface.

### 5.2. Why Select Languages with a Whitelist?

The `switch` block accepts only `en` or `vi`. If it accepted `fr` and passed `Locale.FRENCH` straight through, `ResourceBundle` could still locate the English root file and **not throw an error**. The program would report that the language switched even though no French translation exists.

A whitelist accomplishes two things:

- Ensures the language code belongs to the languages officially supported by the product.
- Gives the user a clear error on `lang zz` instead of silently falling back.

For larger products, this list can be managed in application configuration or via a `Map<String, Locale>` structure. Do not assume `Locale.forLanguageTag` validates that a bundle file exists.

### 5.3. Why Update Both locale and ResourceBundle?

`ResourceBundle.getBundle(BUNDLE_BASE, requested)` selects the translation. However, `MessageFormat` also uses `locale` to determine **number formatting rules**, such as the thousands separator. If you only swap `messages` and forget to update `locale`, the sentence may be in Vietnamese while numbers still use US formatting.

Sequence in `changeLanguage`:

1. Validate the language.
2. Obtain the corresponding locale (`Locale.US` or `vi-VN`).
3. Load the bundle for the new locale.
4. Update both the `locale` and `messages` fields.
5. Print the confirmation message from the **new bundle**.

Thus, `lang vi` prints `Đã chuyển sang tiếng Việt.` rather than the English line from the old bundle.

### 5.4. Why Use Locale.ROOT for Command Names?

Commands like `LANG`, `Lang`, `greet`, and `COUNT` are **ASCII technical keywords**, not user-facing text that needs case conversion according to user grammar. `toLowerCase(Locale.ROOT)` avoids unexpected transformations when the default locale is Turkish (for instance, the letter `I` has special casing rules). For actual user data, do not blindly apply `Locale.ROOT` as a substitute for natural-language processing.

### 5.5. Why Does BufferedReader Only Read Line by Line?

The CLI operates as **one command per line**. `readLine()` returns a string without line-termination characters. When stdin ends (`EOF`), it returns `null`; the code exits instead of calling `split` on `null`.

`line.strip()` removes leading/trailing whitespace as defined by Java; `split("\\s+", 2)` splits the **command name** from the **remaining argument portion**. Passing 2 as the second parameter ensures `greet Nguyễn Văn A` preserves the full name `Nguyễn Văn A` instead of keeping only `Nguyễn`.

**Note:** this is a demo CLI, not a general-purpose command-line parser. `greet "Nguyễn Văn A"` will retain the double quotes as part of the name because the program does not implement shell-style quote parsing. If you need escaped arguments, option flags, multiple quoted arguments, or command completion, design a dedicated parser or use a specialized CLI library.

### 5.6. Why Handle Counts as long Instead of String Concatenation?

`Long.parseLong(argument)` accepts integer strings according to Java's parsing rules and throws `NumberFormatException` if the value is invalid or exceeds the `long` range. Then:

- `count < 0` is rejected.
- `count == 1` selects the singular pattern.
- All remaining values select the `count.other` pattern.
- `trf(key, count)` passes the `Long` to `MessageFormat`, allowing `{0,number,integer}` to format the number according to the locale.

Do not take `argument` as a string and insert it directly into the pattern: that leaves `1234` unformatted even when the locale requires `1,234` or `1.234`. If a product requires numbers larger than `long`, consider `BigInteger`, dedicated formatting rules, and explicit validation contracts.

## 6. Compiling and Running Directly with the JDK

Maven/Gradle are not required for this exercise. From the `language-cli` directory, compile with:

```bash
javac -encoding UTF-8 -d out src/main/java/LanguageCli.java
```

`-encoding UTF-8` specifies the encoding of the **Java source file**. Depending on your setup, `javac` uses the `out` directory as the root for compiled class output.

On Linux/macOS, run:

```bash
java -cp "out:src/main/resources" LanguageCli
```

On Windows PowerShell:

```powershell
java -cp "out;src/main/resources" LanguageCli
```

Classpath separators:

- `:` on Unix systems (Linux/macOS).
- `;` on Windows.

Java requires **both the class directory** and the **resource directory** on the runtime classpath. `out` holds `LanguageCli.class`; `src/main/resources` holds `Messages.properties`, `Messages_en.properties`, and `Messages_vi.properties`.

If you only run:

```bash
java -cp out LanguageCli
```

and `out` does not contain the properties files, `ResourceBundle.getBundle` cannot locate the base name and can throw `MissingResourceException` right when constructing `LanguageCli`.

### Do Not Confuse Source File, Stdin, and Stdout Charsets

The program uses `new InputStreamReader(System.in, StandardCharsets.UTF_8)` to **decode input bytes** as UTF-8. Therefore, the terminal or pipe **must actually supply UTF-8 bytes** when you type names with diacritics. If the terminal sends a different charset, names can become garbled. On JDK 18+, the default charset for many APIs is UTF-8, but this exercise specifies it explicitly because **the chosen stdin protocol is UTF-8**.

`System.out`/`System.err` are tied to the console mechanism and may use a charset different from the JVM default charset. If emojis or Vietnamese diacritics render as garbled characters, inspect the encoding on both the Java output side and the terminal renderer rather than immediately assuming the resource file is wrong.

## 7. Testing Different Scenarios

### 7.1. Switching to Vietnamese and Back to English

Type sequentially:

```text
lang vi
greet Minh
count 1234
lang en
greet Lan
quit
```

Messages in order:

```text
Đã chuyển sang tiếng Việt.
Xin chào, Minh!
Bạn có 1.234 tin nhắn.
Language switched to English.
Hello, Lan!
Goodbye!
```

These are the **response lines**, omitting the prompts and initial welcome lines. The number-formatting lines reflect a modern JDK.

### 7.2. Entering Invalid Commands

Try sequentially:

```text
greet
count abc
count -3
lang fr
unknown
```

While still in English, the corresponding responses are:

```text
Please provide a name.
Enter a non-negative integer.
Enter a non-negative integer.
Unsupported language. Use en or vi.
Unknown command. Type help.
```

If you switch to Vietnamese **before** entering the invalid commands, the same error keys display in Vietnamese. No error messages are hardcoded inside `run()`; all of them are retrieved via `tr(key)`.

### 7.3. Testing Singular and Plural Forms

In English:

```text
> count 0
You have 0 messages.
> count 1
You have 1 message.
> count 2
You have 2 messages.
```

In Vietnamese:

```text
> lang vi
Đã chuyển sang tiếng Việt.
> count 1
Bạn có 1 tin nhắn.
> count 2
Bạn có 2 tin nhắn.
```

The count-handling code runs **once** and only swaps the pattern by key. Each pattern remains a **complete sentence**, allowing translators to adjust word order and grammar as needed.

Demo limitation: selecting `count.one` when the value is exactly 1 and `count.other` for the rest only suffices to illustrate the two English/Vietnamese locales supported in this lesson. Do not apply `count == 1` logic to every language. Production multilingual systems should consult **CLDR plural rules** or an ICU MessageFormat/MessageFormat library with appropriate plural-category support.

## 8. Extension Exercise: Wrapping Keys Behind Meaningful Methods

In this program, `tr("greeting")` keeps business logic unaware of translated sentences. `trf("count.other", count)` both looks up the pattern and formats data. This is the first step toward a reusable message-provider layer.

In a real application, you can define a translation interface:

```java
interface Localizer {
    String text(String key);
    String format(String key, Object... arguments);
}
```

The snippet above is an **interface snippet**, not a standalone runnable class. An implementation can accept the session/request `Locale` and `ResourceBundle`; this lets business logic depend on a small abstraction instead of calling static `ResourceBundle.getBundle` everywhere.

However, **do not over-engineer abstractions before there is a real need**. For a single-file CLI, the two `tr`/`trf` methods are enough to explain the principle. A `Localizer` abstraction pays off in larger applications with unit-test mocks and multiple output channels.

## 9. ResourceBundle Fallback and Caching

### 9.1. A Selected Locale Does Not Guarantee a Region-Specific File Exists

When using `Locale.US` (en-US), Java typically checks candidate bundles `Messages_en_US`, `Messages_en`, and then the root. This project has no `Messages_en_US.properties`, so `Messages_en.properties` is used.

Similarly, `vi-VN` has no `Messages_vi_VN.properties`, but it does have `Messages_vi.properties`. As a result, Vietnamese still prints as intended.

**Do not assume `getBundle` throws an error if a specific locale is missing.** It uses fallback logic. Having English in the root ensures the program still has messages in some situations, but it can hide missing translations unless you have translation-coverage tests.

### 9.2. Caching Is Normal Behavior

`ResourceBundle` has a built-in caching mechanism. Calling `getBundle` multiple times can return a previously loaded bundle. For this CLI:

- `lang vi` retrieves the Vietnamese bundle.
- `lang en` retrieves the English bundle.
- Switching back to `lang vi` does not need to reload the file from disk in all cases.

Do not call `ResourceBundle.clearCache()` after every `lang` command; switching languages **does not mean** the files on disk have changed. If you are building a system that edits translations at runtime, you need an explicit reload/cache-control strategy and thorough testing. This exercise only reads resources bundled with the application.

## 10. Packaging into a JAR to Run Without the Source Tree

Recompile if the class file does not exist yet:

```bash
javac -encoding UTF-8 -d out src/main/java/LanguageCli.java
```

Create the JAR from the **contents** of the compiled classes output and resource root:

```bash
jar --create --file language-cli.jar -C out . -C src/main/resources .
```

Inspect entries:

```bash
jar tf language-cli.jar
```

The output must contain at least the relevant entries (this is an **excerpt**, not the full listing):

```text
LanguageCli.class
Messages.properties
Messages_en.properties
Messages_vi.properties
```

Run:

```bash
java -cp language-cli.jar LanguageCli
```

Because this example does not configure `Main-Class` in the manifest, running `java -jar language-cli.jar` may report that there is no main manifest attribute. To create an executable JAR, you can use:

```bash
jar --create --file language-cli-run.jar --main-class LanguageCli -C out . -C src/main/resources .
java -jar language-cli-run.jar
```

Both approaches require **packaging `Messages*.properties` at the right path**. If you package `src/main/resources/Messages_vi.properties` inside the JAR instead of `Messages_vi.properties` at the root, `getBundle("Messages", ...)` will not find the file.

### What About Using Maven/Gradle?

In a standard Maven/Gradle Java project layout, `src/main/resources` is normally copied into the classpath output and packaged into the JAR. Do not embed `src/main/resources` itself as a subdirectory inside the artifact. Verify with `jar tf` after any build change affecting resources.

This exercise uses the default package for easy manual compilation. In production code, use a package like `com.example.cli` for Java sources and a namespace like `com.example.i18n.Messages` for the bundle; in that case, place files under `com/example/i18n` inside resources and pass the matching base name.

## 11. Common Errors and Root Causes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `MissingResourceException` at startup | Cannot find `Messages.properties` or a matching bundle | Check classpath and file paths |
| Runs in IDE but fails from JAR | Resources omitted during packaging | Check entries with `jar tf` |
| `lang vi` still displays English | Missing `Messages_vi.properties`; falls back to root | Check locale/bundle and translation coverage |
| `lang fr` does not error when calling `getBundle` directly | Fallback returns the English root | Whitelist supported languages |
| Vietnamese text appears, but numbers use US commas | `MessageFormat` uses the old US locale | Update `locale` alongside the bundle |
| Output contains literal `{0}` unreplaced | Printing `getString` directly instead of formatting | Use `new MessageFormat(pattern, locale).format(args)` |
| Error when handling `greet` without a name | Accessing an empty or missing argument | Validate input and use key `error.name` |
| `count abc` crashes | Parsing number without error handling | `catch NumberFormatException` |
| `count -5` treated as a valid count | Missing business validation | Check `count >= 0` |
| Vietnamese diacritics turn into garbled characters | Mismatched input/output, resource, or terminal charset | Identify where bytes are encoded/decoded incorrectly |
| Added translations but app behavior unchanged | Bundle cache or stale artifact | Verify the right JAR version and cache lifecycle |
| Calling `Locale.setDefault` across multiple requests | Shared JVM state affects other tasks | Store locale per session/request |
| Translating word-by-word and concatenating sentences | Word order hardcoded in Java | Keep full sentence patterns per locale |
| Using `count == 1` for all languages | Plural rules go beyond one/other | Use CLDR/ICU per locale |
| Passing user name as the `MessageFormat` pattern | Names with `{ }` or apostrophes cause syntax errors | Load pattern from catalog; pass name as an argument |
| Unescaped `'` in pattern | `MessageFormat` treats apostrophe as quoting syntax | Use `''` for a literal apostrophe in patterns |
| Splitting commands with unbounded `split(" ")` | Multi-word names get split unexpectedly | Use `split("\\s+", 2)` |

### Special Pitfall: MessageFormat and Single Quotes

`MessageFormat` uses `'` to quote literal sections; to display an apostrophe in a pattern, you normally must write `''`. For example:

```java
MessageFormat fmt = new MessageFormat(
        "It''s {0}''s message.", Locale.US);
System.out.println(fmt.format(new Object[]{"Lan"}));
// It's Lan's message.
```

This is a **snippet**, separate from the complete CLI application. When adding English strings with apostrophes in `Messages_en.properties`, test pattern parsing. If a user's name contains an apostrophe such as `O'Connor`, it is passed as an **argument**, not parsed as template syntax.

## 12. Automated Behavior-Based Testing

For a multilingual CLI, test more than simply verifying that `getBundle` does not throw an exception. Test categories:

| Category | Input | Expected Outcome |
| --- | --- | --- |
| Start | No command entered | Displays app name, welcome, and help in English |
| Switch vi | `lang vi` | Message in Vietnamese |
| Switch en | `lang en` | Message in English |
| Greeting | `greet Lan` | `Hello, Lan!` or `Xin chào, Lan!` |
| Multi-word name | `greet Nguyễn Văn A` | Preserves full name without dropping text after spaces |
| Count 0 | `count 0` | `count.other` pattern |
| Count 1 | `count 1` | `count.one` pattern |
| Count 2 | `count 2` | `count.other` pattern |
| Grouping | `count 1234` | EN shows `1,234`; VI shows `1.234` on tested JDK |
| Invalid number | `count NaN` | Returns `error.number`, no crash |
| Negative number | `count -3` | Returns `error.number` |
| Overflow | Number exceeding `long` range | `NumberFormatException` handled |
| Unsupported locale | `lang fr` | Keeps current locale; prints `error.locale` |
| Unknown command | `whatever` | Prints `error.command` in current language |
| Blank line | Spaces only | Ignored without crashing |
| EOF | Close stdin | Exits cleanly, no infinite loop |
| Keys | Each locale | All required keys present or acceptable fallback per policy |
| Packaging | After building JAR | Runs without the source resource directory |
| UTF-8 | `greet Đặng Văn A` | Reads and displays characters properly when terminal supports UTF-8 |

### Invariants to Preserve

1. The same key string can return different sentences depending on `Locale`.
2. **User data** such as names must never be auto-translated or altered when changing locales.
3. Switching languages only affects messages/formatting for **subsequent commands**; previously printed output does not need to change.
4. `lang fr` must not overwrite the existing language state.
5. `ResourceBundle` can fall back; maintain separate validation for the product's supported locale list.
6. Resource paths inside the JAR must match the base name.
7. Translations may reorder placeholders; this must not require changing argument order in code.
8. Input/output byte encoding and locale are **two independent axes**.

### Testing Key Completeness

For the example resource files, you can use `ResourceBundle` to verify that required keys are retrievable:

```java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
if (!vi.containsKey("greeting")
        || !vi.containsKey("count.one")
        || !vi.containsKey("count.other")) {
    throw new IllegalStateException("Missing required message");
}
```

This is a **method snippet**. Note that `containsKey` checks parent bundles as well, so it does not prove that **`Messages_vi.properties` itself defines every key**. To guarantee translation coverage per file, CI should read the catalog directly or use a tool that inspects translated keys prior to fallback.

## 13. Extending the Practice for Real-World Needs

### 13.1. Adding a Third Language

To add French:

1. Create `Messages_fr.properties` with the corresponding keys.
2. Add `case "fr" -> requested = Locale.FRENCH;` to the whitelist.
3. Translate all sentence patterns, checking apostrophes and grammar.
4. Update the translated help/menu strings across all locales.
5. Test numbers and thousands separators under the actual French locale.
6. Verify that fallback does not mask untranslated keys.

Adding `Messages_fr.properties` alone without adding `fr` to the whitelist is **not enough**; this exercise's CLI intentionally restricts support to `en` and `vi`. Likewise, adding `case "fr"` without the file is not enough, because `ResourceBundle` would still fall back to English.

### 13.2. Persisting Language Preferences Across Sessions

The demo CLI stores the language in **memory for a single run**. Exiting and restarting defaults back to English. If you need to remember the choice, you can store a language tag such as `"vi"` in a configuration file or database and validate the value at startup.

Do not use environment variables or `Locale.getDefault()` to store preferences for a multi-user system with multiple accounts. Persisting preferences requires an explicit contract covering user identity, access permissions, and fallback when a language is deprecated.

### 13.3. Using Locale for Numbers and Dates Without Mixing Logic

In this exercise, `MessageFormat` uses the active locale to format numbers. If you add a `today` command, you can use `java.time.format.DateTimeFormatter.ofLocalizedDate(...)` with `withLocale(locale)`, while real dates/times require a separate time zone if the application handles timestamps. **A locale is not a timezone.**

Example snippet:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
String today = java.time.LocalDate.of(2026, 10, 28)
                .format(formatter);
```

This snippet requires importing `java.time.format.DateTimeFormatter` and `FormatStyle`, with `locale` already defined. It illustrates UI-layer formatting responsibility; it is omitted from the core CLI to keep the practice focused on `ResourceBundle`.

### 13.4. Switching Languages in Multi-User Applications

In web or server applications, never share a single `static Locale currentLocale` variable across all requests. A request from user A selecting Vietnamese must not unexpectedly switch the language for user B. Instead, each request or session carries its own locale, and the localizer receives the locale as a parameter. The CLI's pattern forms the basis for isolating state per session.

## 14. Exercises with Answers

**Exercise 1.** Why must `Messages_vi.properties` be on the runtime classpath?

**Answer:** `ResourceBundle.getBundle("Messages", locale)` resolves the matching resource name from the classpath/module path, not by searching source repository paths automatically. If the file is not copied or placed on the classpath, Java may fall back to the root or throw `MissingResourceException` if no bundle is found.

**Exercise 2.** What must the CLI update when the user types `lang vi`?

**Answer:** Select `Locale.forLanguageTag("vi-VN")`, load the `ResourceBundle` for that locale, store both the locale and the bundle so that translations **and number formatting** use the same locale, and then print the confirmation message using the new bundle.

**Exercise 3.** Why is calling `Locale.setDefault` not a good way to switch languages per session?

**Answer:** The default locale is JVM-wide state that can affect other code. A multi-request application would suffer from language state leakage. Pass `Locale` explicitly and store it per instance or session.

**Exercise 4.** Why does `count 1` need a separate key in English, while Vietnamese in this exercise can use the same pattern for `one` and `other`?

**Answer:** English in the sample sentence distinguishes the singular/plural noun `message/messages`, whereas Vietnamese typically uses `tin nhắn` for both counts. Those two branches are specific illustrations, not universal global plural rules.

**Exercise 5.** To preserve the full name in `greet Nguyễn Văn A`, why must we split with a limit of 2?

**Answer:** Because everything after the command name is a **single multi-word string argument**. `split("\\s+", 2)` separates the command name from the rest of the line without splitting the name at spaces.

**Exercise 6.** If `count 1234` prints `1,234` in English but `1.234` in Vietnamese, does the numeric calculation logic change?

**Answer:** No. `count` remains the exact same `long` value `1234`; only its presentation through `MessageFormat` changes with the locale.

**Exercise 7.** The command `lang fr` produces no error because Java still returns the English root bundle. Where is the bug?

**Answer:** In the application's language-support logic: `ResourceBundle` uses fallback. You must validate supported language tags against a whitelist before loading or accepting a locale switch.

**Exercise 8.** To run `java -cp language-cli.jar LanguageCli` after packaging, which entries must the JAR contain?

**Answer:** `LanguageCli.class` and the `Messages*.properties` entries directly at the JAR root matching the base name `Messages`. You can verify this with `jar tf language-cli.jar`.

**Exercise 9.** What problem can occur if you add `title=It's OK` to a properties file and format it with `MessageFormat`?

**Answer:** A single quote has special syntactic meaning in `MessageFormat` patterns. To output a literal apostrophe, you usually need `It''s` and should test the formatter. If `MessageFormat` is not used for that key, `getString` returns raw text; you must be clear about which keys are patterns.

**Exercise 10.** Why isn't checking `messages.containsKey("greeting")` sufficient to conclude that the Vietnamese translation is complete?

**Answer:** Because `containsKey` can return `true` due to a key inherited from a parent/root bundle. You must verify coverage directly on the **actual translation file** or use a translation management pipeline.

## 15. Summary

- A multilingual CLI should separate **command handling** from **localized messages**.
- `ResourceBundle.getBundle(baseName, locale)` loads resources by base name and locale; files must be at the **correct classpath root** with corresponding `_en` and `_vi` suffixes.
- `Locale` governs language and formatting rules; `MessageFormat` inserts dynamic values `{0}` into **complete sentence patterns**.
- Switching `lang vi` or `lang en` only requires updating the session's **locale + bundle**, without calling `Locale.setDefault`.
- Do not assume a missing translation throws an exception, because `ResourceBundle` has fallback behavior. Always **validate** supported languages and key coverage.
- For counts, input validation and plural logic must be separated from text; the `one`/`other` branches are only a starting point for the two illustrated locales.
- Compile and run with `javac`/`java -cp` or package with `jar`; verify that `Messages*.properties` are placed correctly in the final artifact.
- When testing i18n, test **mid-session language switching**, numbers/placeholders, invalid inputs, Unicode, fallback, and JAR packaging.

**Official Documentation:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
- [CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
