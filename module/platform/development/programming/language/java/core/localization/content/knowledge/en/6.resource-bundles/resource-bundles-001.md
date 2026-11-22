# Separating Text from Source Code Using Resource Keys

## 1. Why Shouldn't UI Text Be Hardcoded in Java?

An application can have many kinds of user-facing text: page titles, button labels, confirmation messages, input validation errors, and greetings. If every place directly embeds a Vietnamese string in Java code, changing wording or adding English will force developers to find and update many locations:

```java
System.out.println("Xin chào, " + name + "!");
System.out.println("Bạn có muốn đăng xuất?");
```

When a language-switching requirement arises, this style easily leads to scattered conditional branches:

```java
String greeting = locale.getLanguage().equals("vi")
        ? "Xin chào, " + name + "!"
        : "Hello, " + name + "!";
```

Initially there are only two languages, but as more languages are added, the same message must be updated in many places. The text is also tightly coupled to processing logic.

The solution is to **define a stable resource key for each message**, store the display values in the resource file corresponding to each language, and use Java to look them up by `Locale`.

For example:

| Technical Key | Vietnamese Value | English Value |
| --- | --- | --- |
| `app.title` | `Ví dụ ResourceBundle` | `ResourceBundle demo` |
| `greeting` | `Xin chào, {0}!` | `Hello, {0}!` |
| `logout.confirm` | `Bạn muốn đăng xuất?` | `Do you want to sign out?` |

The **key** acts as an identifier in the source code; the **value** is the localizable content. A Java call still invokes `getString("logout.confirm")` regardless of whether the displayed text is Vietnamese or English.

This lesson focuses on **separating text from Java code using resource keys** in `ResourceBundle`: how to organize files, perform lookups, parameterize messages, handle fallback, manage keys, and write tests. This is the foundation for scaling a maintainable multilingual system.

## 2. ResourceBundle and the Relationship Between Base Name, Key, Value, and Locale

`java.util.ResourceBundle` is Java's API for retrieving resources based on `Locale`. A set of resources shares a common **base name** and can include multiple variants by language, region, or script.

For example, choosing the base name `messages`:

```text
messages.properties       # root resource
messages_vi.properties    # Vietnamese
messages_en.properties    # English
```

In each `.properties` file, the typical content consists of `key=value` pairs. With `ResourceBundle`, a key is a `String`; `getString(key)` reads the corresponding value. The filename suffix indicates the locale; it is **not** part of the key.

Three independent components:

1. `baseName` (`"messages"`): the resource group to search for.
2. `locale` (for example `Locale.forLanguageTag("vi-VN")`): the desired language or variant.
3. `key` (`"greeting"`): the specific message within the group.

Basic lookup:

```java
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
String text = bundle.getString("app.title");
```

Java determines the matching bundle through candidate locales, searches for resources on the classpath/module path according to the API's rules, and can use parent bundles to look up missing keys. **A key is not like a file path**; `getString("app.title")` looks up the key in the loaded bundle.

Besides `.properties`, `ResourceBundle` can also use `ListResourceBundle` classes or environment-specific providers. For typical UI text tasks, `.properties` files are easy to read, easy to translate, and help keep Java logic mostly unchanged when wording is updated.

## 3. Complete Example with `.properties` Files and a Java 17+ Program

Create four files in the **same directory**:

```text
localization-demo/
├── ResourceBundleDemo.java
├── messages.properties
├── messages_vi.properties
└── messages_en.properties
```

Contents of `messages.properties`, acting as the root bundle:

```properties
app.title=ResourceBundle demo
greeting=Hello, {0}!
logout.confirm=Do you want to sign out?
```

Contents of `messages_vi.properties`:

```properties
app.title=Ví dụ ResourceBundle
greeting=Xin chào, {0}!
logout.confirm=Bạn muốn đăng xuất?
```

Contents of `messages_en.properties`:

```properties
app.title=ResourceBundle demo
greeting=Hello, {0}!
logout.confirm=Do you want to sign out?
```

Contents of `ResourceBundleDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceBundleDemo {

    private static void show(Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);

        String title = bundle.getString("app.title");
        String greetingPattern = bundle.getString("greeting");

        MessageFormat formatter =
                new MessageFormat(greetingPattern, locale);
        String greeting = formatter.format(new Object[] {"Mai"});

        System.out.println(locale.toLanguageTag());
        System.out.println(title);
        System.out.println(greeting);
        System.out.println(bundle.getString("logout.confirm"));
    }

    public static void main(String[] args) {
        show(Locale.forLanguageTag("vi-VN"));
        show(Locale.forLanguageTag("en-US"));
    }
}
```

Save the text files as UTF-8. With JDK 17+:

```bash
javac -encoding UTF-8 ResourceBundleDemo.java
java -cp . ResourceBundleDemo
```

Exact stdout:

```text
vi-VN
Ví dụ ResourceBundle
Xin chào, Mai!
Bạn muốn đăng xuất?
en-US
ResourceBundle demo
Hello, Mai!
Do you want to sign out?
```

Explanation:

- `vi-VN` is requested, and Java can narrow candidate locales to `vi`, so `messages_vi.properties` is selected.
- `en-US` uses `messages_en.properties` because it has the language component `en`.
- The same key `greeting` returns different values depending on the locale.
- `{0}` in the text is a placeholder replaced by `MessageFormat` with the name `Mai`. The name is not hardcoded into the translation, and translators can place the parameter in a grammatically appropriate position.
- The root bundle `messages.properties` is a place to provide default resources and acts as a fallback source in cases permitted by `ResourceBundle` rules.

The directory containing the `.properties` files must be on the classpath at runtime. In the example, `-cp .` causes the program to find the files next to the `.class` files. If you place the files inside package `com.example.i18n`, the base name can be `"com.example.i18n.messages"`; the resource path on the classpath must match accordingly.

**In a Maven/Gradle project:** the usual locations are `src/main/resources/messages.properties`, `src/main/resources/messages_vi.properties`, etc. In code, call `ResourceBundle.getBundle("messages", locale)`. The build system typically copies `src/main/resources` to the output classpath; you do not need to manually read files with `FileInputStream` to look up messages.

## 4. Designing Maintainable Long-Term Resource Keys

A good key name is an **identifier with business meaning or display purpose**, independent of the translated text. Use consistent, searchable names:

```properties
auth.login.title=Sign in
auth.login.submit=Continue
auth.login.error.invalidCredentials=Incorrect email or password.
profile.save.success=Changes saved.
order.checkout.confirm=Place order?
```

Practical rules:

- Group by feature (`auth`, `profile`, `order`) and purpose (`title`, `submit`, `error`, `success`).
- Keys stay stable when English or Vietnamese wording changes; **do not** use the full display sentence as a key.
- Do not reuse a single key for two different contexts just because the current text happens to be identical. The word "Open" for a file and for a door may require different translations.
- Do not include personal data, dynamic data, or secrets in key names.
- Define clear casing conventions; typically use ASCII letters, digits, and dots to avoid subtle errors.
- Keys form an internal API between code and translation files: renaming a key requires updating all call sites and all locales.

An example to **avoid**:

```java
bundle.getString("Please press the blue button to continue");
```

Display text is meant to be edited; if you turn it into a key, editing a sentence forces changes to Java code and all translation files.

To avoid scattered keys, large projects can centralize keys as constants:

```java
public final class MessageKeys {
    private MessageKeys() {}

    public static final String LOGIN_TITLE = "auth.login.title";
    public static final String INVALID_CREDENTIALS =
            "auth.login.error.invalidCredentials";
}
```

Constants make keys easier to find and refactor in code; however, the Java compiler **does not automatically verify** that a key exists in every file. Separate tests or resource-checking tools are needed. You do not necessarily have to create a constant for every key if the project already uses an automated key-verification solution.

## 5. Parameterizing Strings Instead of Concatenating Text

Translations often need to insert names, quantities, or times. Do not concatenate English fragments and apply the same structure to every language:

```java
String message = "Hello, " + name + "!";
```

With `MessageFormat`, the resource file holds the complete sentence:

```properties
greeting=Hello, {0}!
files.count=You have {0,number,integer} files.
```

Another locale can reorder placeholders without modifying code. `MessageFormat` supports numbers, dates, and formatting patterns, but it must be constructed with the **target locale**:

```java
String pattern = bundle.getString("files.count");
MessageFormat format = new MessageFormat(pattern, locale);
String message = format.format(new Object[] {3});
```

In this example, `{0}` takes the element at index 0 of the argument array, while `{0,number,integer}` requests formatting as an integer according to `MessageFormat`'s locale. Do not substitute `String.format` if translation files use `MessageFormat` syntax: the two APIs use different placeholder syntaxes.

**Two important `MessageFormat` rules:**

1. A single quote `'` acts as an escape character in patterns. To display a literal single quote, use `''` in the pattern, e.g., `You''re welcome, {0}!`. If a translator inserts a single quote as in ordinary prose, the pattern may produce unexpected output.
2. Curly braces have special syntax. If you need to display literal `{` or `}` characters, they must be escaped according to `MessageFormat` syntax. Write tests for messages containing quotes and braces.

For text with singular/plural forms, grammatical gender, or complex grammatical structures, a single sentence with `{0}` is not enough. Design contextual translation templates or use an i18n mechanism that supports appropriate pluralization, such as built-in framework/system options. Do not manually assemble individual words into sentences based on English grammar rules.

## 6. Understanding Fallback and Parent Bundles

When calling:

```java
ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))
```

Java has rules for finding candidate bundles in order of decreasing locale specificity. In a simple example, it may check `messages_vi_VN`, `messages_vi`, and then the root bundle `messages`, depending on `ResourceBundle.Control` and the environment. `ResourceBundle` also has a **fallback mechanism to the JVM's default locale** when no bundle matching the requested locale is found. Therefore, you should not assume that whenever `messages_ja` is absent Java immediately picks `messages.properties`; resources for the default locale may take precedence along certain lookup paths.

Distinguish between:

- **Locale fallback:** when no bundle exists for the requested locale, Java searches for other candidates according to `ResourceBundle` rules.
- **Key fallback:** when the selected bundle is missing a key, Java can look it up from a parent bundle.
- **Business fallback:** the product decides its intended default language (for example `en-US`), independent of arbitrary server configuration.

To select a language accurately according to the product's actual supported list, resolve the supported locales before calling `getBundle`, then pass the chosen locale. Do not treat `Locale.getDefault()` as product policy. In multi-request applications, do not call `Locale.setDefault(...)` to pick a language per user: it mutates global JVM state and can affect other requests.

A complete `messages.properties` serves as an important fallback, but it **does not replace verifying the quality of each translation**. A UI mixing Vietnamese and English due to missing keys may work technically yet deliver a poor user experience.

## 7. Missing Bundle and Missing Key Are Two Different Errors

If the base name does not exist or no matching bundle can be found, `ResourceBundle.getBundle` throws `MissingResourceException`. If a bundle is found but `getString(key)` cannot locate the key in the bundle/parent chain, it also throws `MissingResourceException`.

Example checking a key using the loaded bundle itself:

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingKeyDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"));

        String key = "not.existing";
        try {
            System.out.println(bundle.getString(key));
        } catch (MissingResourceException error) {
            System.out.println("Missing key: " + error.getKey());
        }
        System.out.println(bundle.containsKey("app.title"));
    }
}
```

Run in the same resource directory as the example in section 3:

```bash
javac -encoding UTF-8 MissingKeyDemo.java
java -cp . MissingKeyDemo
```

Stdout:

```text
Missing key: not.existing
true
```

`containsKey` can help check for a key before calling `getString`, but you **should not silently return an empty string** for every missing key: doing so hides translation bugs during development. Depending on the product, you can display a controlled fallback in production while logging a clear warning code and maintaining tests to detect missing keys before release.

Distinguish between a nonexistent key error and an intentionally empty translation string. An empty string can be valid for certain resources, whereas a missing key is a resource contract violation.

## 8. Encoding, Vietnamese Characters, and the `.properties` Format

The `.properties` files in the example are saved as **UTF-8**. In Java 9+, `PropertyResourceBundle` reads streams as UTF-8 by default under standard behavior and falls back to ISO-8859-1 when encountering invalid UTF-8 sequences; this can be controlled via the `java.util.PropertyResourceBundle.encoding` property. With Java 17+, Vietnamese in UTF-8 files works directly during normal builds and execution.

Keep in mind that APIs or tools processing `.properties` files may behave differently:

- `ResourceBundle` uses `PropertyResourceBundle` for resource files.
- `java.util.Properties.load(InputStream)` reads ISO-8859-1 by contract, unlike `PropertyResourceBundle`'s default Unicode handling on Java 17.
- Some legacy translation pipelines use Unicode escapes like `\\u00E9` instead of literal characters. If multiple tools write these files, standardize the encoding across the entire pipeline.

In `.properties` files, lines starting with `#` or `!` are comments; `=` and `:` can separate keys and values. Special characters such as backslashes, newlines, or separator characters in keys follow escaping rules. For multiline messages, use proper line continuation or escaping syntax and test the actual output.

**Do not put byte manipulation or manual charset handling into key-lookup logic**, because resource loading is already built into `ResourceBundle`. Just make sure the files are on the right classpath and properly encoded.

## 9. Resource Placement and Lifecycle

The example keeps `.properties` files next to `.class` files for ease of learning. In a real project, place resources in a directory that the build tool includes on the runtime classpath, for example:

```text
src/main/java/com/example/app/GreetingService.java
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
src/main/resources/messages_en.properties
```

Java code in a package can then still call `ResourceBundle.getBundle("messages", locale)`, because `messages.properties` is at the classpath root. If you put bundles in `src/main/resources/i18n/`, the base name must correspondingly be `i18n.messages`.

`ResourceBundle` has a caching mechanism to avoid reloading resources repeatedly. This suits long-running applications, but **modifying a file on disk does not mean resources will automatically refresh immediately** in every application. Resources packaged inside a JAR are usually managed through the build/deploy lifecycle. When dynamic reloading is needed, explicitly design the cache/reload policy, class loader, and deployment environment; the API provides `ResourceBundle.clearCache()`, though clearing the cache can affect multiple callers.

An application or framework (such as Spring) may provide a different abstraction for accessing resource messages, with its own lifecycle and cache configuration. Even so, the principle of separating **stable keys** from **localized text** remains the same.

## 10. Translator Workflow and Quality Control

When a project supports multiple languages, developers and translators need to follow a shared contract:

1. **Lock down key meaning and context.** A short phrase like "Save" can mean saving data or saving money. Describe the usage location and intent for translators.
2. **Add keys in the root bundle first**, then add them to supported translations. Each key must have a consistent meaning across locales.
3. **Keep placeholders stable.** If the root uses `{0}`, translators may reorder placeholders but must not arbitrarily delete them or change them to `%s`.
4. **Allow full-sentence translation.** Do not force translators to piece together `prefix`, `noun`, and `suffix` fragments; grammar varies across languages.
5. **Check for extra and missing keys** in CI or an appropriate test. There should be a mechanism to detect keys removed from code that still linger in translation files.
6. **Inspect directly in the UI**: string length, line wrapping, punctuation, plurals, proper nouns, number/date formatting, and UI layout.
7. **Security note:** translated content is display data, not trusted HTML strings or SQL commands. When rendering to the web, HTML escaping/contextual encoding is still required based on the insertion context; `MessageFormat` is not an XSS sanitizer.

You can keep comments directly in the root file for explanation:

```properties
# Appears on the final confirmation button before a purchase.
checkout.confirm=Place order

# {0}: customer display name. Keep the placeholder.
greeting=Hello, {0}!
```

Every translation file does not necessarily have to mirror comments identically, but there should be a source of context data so translators avoid misunderstandings.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Hardcoding text directly in Java | Every translation requires code changes | Move values to `.properties` and look up by key |
| Using full English sentences as keys | Wording changes force code changes | Name keys by feature and context |
| Sharing one key for two meanings | Translating one place breaks another | Split keys by purpose |
| Forgetting bundle files on the classpath | `MissingResourceException` | Verify directory structure and build output |
| Missing keys in one language | Unintended fallback or missing-key error | Test key-set parity across locales |
| Concatenating sentence fragments with `+` | Broken grammar in translations | Use complete messages with placeholders |
| Using `MessageFormat` without checking quotes | Pattern renders incorrectly | Escape quotes and test patterns |
| Using the default locale for all users | Requests depend on server environment | Pass an explicit `Locale` per request |
| Editing resource files and expecting instant reload | Cache serves stale content | Establish a clear deploy/reload process |
| Confusing `Properties.load(InputStream)` with `ResourceBundle` | Unicode may be read incorrectly | Use the right API and encoding |

Do not use `getString` as a test for whether a language is supported: a key may still be found via a parent/fallback bundle even when the intended translation does not exist. If the product only supports a specific list of locales, declare and validate that list before loading bundles.

## 12. What Should Unit and Integration Tests Verify?

- **Bundle existence**: the base name can be found on the classpath after building, both when running locally and when packaged as a JAR.
- **Key set**: the root bundle contains every key used by Java code; translations have the coverage required by product policy.
- **Locale fallback**: requesting `vi-VN` when only `messages_vi` exists, requesting an unsupported language, and verifying the right business fallback.
- **Key fallback**: a translation misses a key; verify whether it falls back to the parent or reports an error as designed.
- **Placeholders**: each locale has the right number and order of parameters; `MessageFormat` patterns are valid, especially sentences with single quotes, braces, numbers, and dates.
- **Unicode**: Vietnamese diacritics are saved, read, and displayed accurately on the target Java runtime.
- **No default-locale dependency**: pass explicit locales to APIs; do not mutate JVM-wide `Locale.setDefault` in request logic.
- **Changing wording without changing code**: update a value in a translation file, rebuild/redeploy, and verify the same key displays the new message.
- **Output safety**: if user-supplied values appear in placeholders, the presentation layer must encode them for the target context.

**Note on testing:** a demo program printing Vietnamese and English does not prove all keys are valid. In real modules, add automated checks to catch missing keys or invalid placeholders before release.

## 13. Practice Exercises

Keep the program from section 3 and try:

1. Add `messages_fr.properties` with French translations for the three keys `app.title`, `greeting`, and `logout.confirm`; call `show(Locale.forLanguageTag("fr-FR"))`. Verify the code needs no new conditional for French.
2. Change the `logout.confirm` text in the Vietnamese file while keeping the key unchanged; verify no Java edits are needed.
3. Temporarily remove `greeting` from `messages_vi.properties`; observe how `ResourceBundle` looks up the value from the parent bundle. Then restore the key and explain why a UI mixing two languages can be undesirable.
4. Add the key `files.count` with pattern `You have {0,number,integer} files.` and a complete Vietnamese translation. Use `new MessageFormat(pattern, locale)` to substitute `3`; avoid fragment concatenation.
5. Call `getString("missing.key")`, observe the `MissingResourceException`, and consider an appropriate error-reporting strategy instead of hiding the error with an empty string.

These exercises reinforce one core rule: **Java code identifies which message is needed by key; resource files determine how that message is expressed for the selected locale**. When those two responsibilities are cleanly separated, the application is easier to translate, test, and maintain.

## 14. API Documentation for Further Reading

- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle JDK 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
