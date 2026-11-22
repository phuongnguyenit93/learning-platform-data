# Why Is Whole-Sentence Formatting Needed Instead of Concatenating Text Fragments?

## 1. The Problem: A Sentence Means More Than the Sum of Its Fragments

In a Java application, a simple way to build a dynamic message is to concatenate strings:

```java
String sentence = "Hello, " + name + "! You have "
        + count + " new messages.";
```

This code can work when only English is supported. However, if you use "fragments" for localization:

```java
String sentence = bundle.getString("greeting.prefix")
        + name
        + bundle.getString("inbox.middle")
        + count
        + bundle.getString("inbox.suffix");
```

then translators are forced to follow the **concatenation order dictated by Java**. The grammar of each language does not share the same order for subject, quantity, noun, and form of address. Some languages need to move entire phrases, add context-dependent suffixes, or omit punctuation that belonged to another fragment.

For example:

- English: **“Hello, Linh. You have 2 new messages.”**
- Vietnamese: **“Bạn có 2 tin nhắn mới, Linh.”**

In English, the name `Linh` appears before the count `2`; in Vietnamese, the positions are swapped. If the message is split into "prefix + name + middle + count + suffix", translations have to accept a rigid sentence structure, or the code must add language-specific conditional branches. Each new branch increases the risk of bugs.

**Key rule:** translate **whole sentences with context**, and pass dynamic data into **indexed placeholders**. Java handles the data, while the translation has the freedom to arrange the sentence components.

In Java, `java.text.MessageFormat` is a standard tool for representing a complete message with parameters, number/date formatting, and certain simple locale-sensitive choices.

## 2. Distinguishing String Concatenation from Message Patterns

Compare the two designs:

| Aspect | Concatenating multiple fragments | Whole-sentence formatting |
| --- | --- | --- |
| Translation unit | `prefix`, `suffix`, words, and punctuation | A message with complete meaning |
| Order of name and number | Hardcoded in code | Each translation can reorder parameters |
| Punctuation and spacing | Split across fragments, easily duplicated or missing | Belongs to the complete sentence |
| Natural phrasing | Easily forced into the source language's grammar | Translators choose the structure |
| Dynamic data | Manual concatenation or string replacement | Parameters `{0}`, `{1}`, ... |
| Locale-specific numbers/dates | Often converted to strings too early | Can be formatted at sentence-creation time |
| Testing | Hard to verify whole-sentence grammar | Test each message pattern and its arguments |

A whole-sentence design still needs a **message key** at the resource layer. For example:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

With the Vietnamese translation:

```properties
inbox.summary=Bạn có {1,number,integer} tin nhắn mới, {0}.
```

Both files use the **same key** `inbox.summary` and the same argument list, yet the order of `{0}` and `{1}` is completely different. That is the core benefit of formatting the entire sentence.

**Pitfall to avoid:** `MessageFormat` does not automatically translate English into Vietnamese. You must provide appropriate sentence patterns in the translation files; `MessageFormat` only parses the pattern and inserts data according to formatting rules.

## 3. Basic Structure of MessageFormat

Example pattern:

```text
Hello, {0}. You have {1,number,integer} new messages.
```

- `{0}`: takes the argument at **index 0**.
- `{1}`: takes the argument at **index 1**.
- `{1,number,integer}`: takes argument 1 and formats it as an integer according to the `MessageFormat` locale.
- Text outside curly braces is part of the sentence, preserved as written by the translator.

Main API:

```java
MessageFormat format = new MessageFormat(pattern, locale);
String result = format.format(new Object[] {name, count});
```

`pattern` is the **message pattern**; `locale` determines how numeric/date arguments are formatted. `name` and `count` are dynamic data. To change the sentence structure, modify the pattern in the translation without changing the argument order passed by Java.

In a pattern, argument indices start at 0 and **do not need to appear in ascending order**. An argument can be repeated in multiple places, or unused arguments can be omitted. Even so, keep a clear contract for each key: what argument 0 is, what argument 1 is, and which data types are allowed.

## 4. Standalone Java 17+ Example: Two Languages, One Argument List

Create the file `WholeSentenceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class WholeSentenceDemo {
    static String render(Locale locale, String pattern,
                         String name, int count) {
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] {name, count});
    }

    public static void main(String[] args) {
        String english =
                "Hello, {0}. You have {1,number,integer} new messages.";
        String vietnamese =
                "Bạn có {1,number,integer} tin nhắn mới, {0}.";

        System.out.println(render(Locale.US, english, "Linh", 2));
        System.out.println(render(
                Locale.forLanguageTag("vi-VN"),
                vietnamese,
                "Linh",
                2));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 WholeSentenceDemo.java
java WholeSentenceDemo
```

Stdout:

```text
Hello, Linh. You have 2 new messages.
Bạn có 2 tin nhắn mới, Linh.
```

Each complete sentence is stored in a pattern variable, while both receive the same data `"Linh"` and `2`. The Vietnamese version uses `{1}` before `{0}`. When adding another language, you add a whole-sentence translation and keep using the same `formatter.format(...)` call.

Hard-coding `english` and `vietnamese` in this example is only to focus on the `MessageFormat` mechanism. In a real application, patterns should be loaded from localized resources, such as `ResourceBundle`, so translators can edit text without modifying code.

## 5. Combining with ResourceBundle: Storing Whole Sentences in Resource Files

A working structure for Java 17+:

```text
message-demo/
├── MessageBundleDemo.java
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

`messages.properties` — the root bundle, containing the default version:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

`messages_en.properties`:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

`messages_vi.properties` (saved as UTF-8):

```properties
inbox.summary=Bạn có {1,number,integer} tin nhắn mới, {0}.
```

`MessageBundleDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageBundleDemo {
    static String message(Locale locale, String name, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);
        String pattern = bundle.getString("inbox.summary");

        MessageFormat format = new MessageFormat(pattern, locale);
        return format.format(new Object[] {name, count});
    }

    public static void main(String[] args) {
        System.out.println(message(Locale.US, "Linh", 2));
        System.out.println(message(
                Locale.forLanguageTag("vi-VN"), "Linh", 2));
    }
}
```

In the directory containing the four files:

```bash
javac -encoding UTF-8 MessageBundleDemo.java
java -cp . MessageBundleDemo
```

Stdout:

```text
Hello, Linh. You have 2 new messages.
Bạn có 2 tin nhắn mới, Linh.
```

**Execution flow:**

1. Java determines the locale requested by the user.
2. `ResourceBundle.getBundle("messages", locale)` finds a bundle according to locale/fallback rules.
3. `getString("inbox.summary")` retrieves the **whole sentence** using a fixed key.
4. `new MessageFormat(pattern, locale)` creates a formatter with the desired locale.
5. `format(new Object[] {name, count})` inserts data at the exact positions specified by the translation.

The `.properties` files must be on the classpath. In Maven or Gradle, they are typically placed in `src/main/resources`. With Java 9+ and `PropertyResourceBundle`, UTF-8 is the default encoding under the standard mechanism; keep the encoding consistent across compiler, editor, and translation tools.

**Distinguishing two kinds of fallback:** if no bundle exists for the requested locale, `ResourceBundle` has its own rules for searching parent bundles, the default locale, and the root bundle. If a bundle has been selected but is missing a key, key lookup can fall back to the parent bundle. `MessageFormat` does not handle finding translations; it only receives the `pattern` after lookup.

## 6. Why Does Sentence Concatenation Break When Switching Languages?

### 6.1. Word Order and Parameter Position

Languages can place the subject, object, or person's name in different positions. A whole-sentence translation can use `{1}` before `{0}`; concatenating `prefix + value + suffix` deprives translators of that freedom.

### 6.2. Punctuation and Spacing

If a `greeting.prefix` key ends with a comma and a space, and `greeting.suffix` has an exclamation mark, a minor edit can produce double spaces or missing spaces. Some languages use different spacing and punctuation rules. Keeping them in the whole sentence makes ownership clear.

### 6.3. Quantity-Dependent Grammar

Phrases like `count + " files"` are insufficient when singular/plural forms are needed, and rules vary across languages. English distinguishes "1 file" and "2 files"; many languages have **more than two plural categories**, or forms that depend on value and context. You should not translate the word "file" in isolation and append it after a number.

### 6.4. Gender, Form of Address, and Nuance

A notification sentence may change forms of address depending on the person, social relationship, or language grammar. Splitting into lexical fragments often prevents translators from seeing the context. Store whole sentences, add context notes, and create message variants when needed.

### 6.5. Numbers, Dates, and Currencies

If a `double` or `Date` is converted to a string before choosing the locale, you can bring number separators or month names from one language into a sentence of another language. Patterns like `{0,number}`, `{0,number,integer}`, and `{0,date,short}` defer formatting to the formatter's locale. Time zones are a separate concern; choose one explicitly when displaying instants.

### 6.6. Consistency and Maintainability

When a sentence is a single key, content authors can update tone, punctuation, and component order in one place. The code only knows the argument contract. Testing can also rely on the set of keys and sentence patterns, with less coupling to scattered fragments.

## 7. Number and Date Formatting Must Match the Reader's Context

Some `MessageFormat` patterns:

```text
Total items: {0,number,integer}
Price: {0,number,currency}
Processed on {0,date,short}
Started at {0,time,short}
```

The `number`, `date`, and `time` parameters rely on the `MessageFormat`'s locale. With `number,currency`, the default currency unit is usually inferred from the locale; if the domain manages multiple currencies, explicitly specify `Currency` and configure an appropriate `NumberFormat` instead of inferring everything from the language.

If the application needs to display instants in time, you also need to specify the `TimeZone` on the formatter/user context. A locale does not automatically select the right time zone.

**Do not confuse UI formatting with serialization:** JSON numbers, ISO timestamps, identifiers, or API exchange payloads must follow protocol specifications. Do not use `MessageFormat` to generate JSON by concatenating text fragments: escaping, data types, and security require a dedicated serializer.

## 8. Singular/Plural: ChoiceFormat Example and Its Limitations

Java's `MessageFormat` supports the `choice` syntax to branch based on a numeric value. A simple English example:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#No items|1#One item|1<{0,number,integer} items}";

        MessageFormat format = new MessageFormat(pattern, Locale.US);

        System.out.println(format.format(new Object[] {0}));
        System.out.println(format.format(new Object[] {1}));
        System.out.println(format.format(new Object[] {2}));
    }
}
```

Save `ChoiceDemo.java`, then run:

```bash
javac -encoding UTF-8 ChoiceDemo.java
java ChoiceDemo
```

Stdout:

```text
No items
One item
2 items
```

Here `0#` applies from 0 upward, `1#` from 1 upward, and `1<` applies to values **greater than 1**. Patterns can contain `{0,number,integer}` inside a branch, so Java continues processing nested placeholders.

This is only an example for English and non-negative integers. **Do not copy the 0/1/many rule for every language.** `ChoiceFormat` is based on numeric boundaries and does not provide full CLDR plural categories such as `one`, `few`, and `many` depending on the language. When a product needs multiple languages and accurate pluralization, consider a translation system supporting CLDR/ICU plural rules or a proven i18n solution, while keeping complete sentences in each branch.

The common principle remains: do not concatenate a prefix, a count, and a noun in a fixed order from Java.

## 9. Single Quotes, Curly Braces, and Special Characters in Patterns

`MessageFormat` has its own syntax: a **single quote** `'` is used to quote a literal segment. To display a single quote in a pattern, you usually must write it as `''` (two single quotes). For example:

```java
MessageFormat format = new MessageFormat(
        "You''re welcome, {0}!", Locale.US);
System.out.println(format.format(new Object[] {"Linh"}));
```

Stdout:

```text
You're welcome, Linh!
```

If you write `You're welcome, {0}!` directly in the pattern, the `'` character can start a quoted region, preventing `{0}` from being processed as intended. When translating sentences that use apostrophes (such as French), this is a very common bug.

Curly braces `{` and `}` also serve to delimit parameters. If they must appear as literal text, you must use `MessageFormat`'s quoting rules. Avoid putting unvalidated user strings into the **pattern**; users should only supply **argument values**, not an arbitrary format pattern executed by the parser.

For `.properties` files, the properties format also has its own escaping rules, such as `\\` or newline characters. Therefore, a pattern must be valid at **two levels**: the resource file syntax and the `MessageFormat` syntax after being read. Tests should use the actual `ResourceBundle` loading path.

## 10. Key Design and Parameter Contracts

A good translation key expresses the *purpose* of the message, rather than merely repeating the English sentence:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
checkout.total=Your total is {0,number,currency}.
profile.update.success=Your profile was updated.
```

So that translators do not confuse `{0}` and `{1}`, document the context:

```properties
# {0}: recipient display name; {1}: unread message count (integer)
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

Rules to standardize across the project:

1. **One key corresponds to one meaning and one display context.** Two buttons both labeled "Open" but serving different purposes may need separate keys.
2. **Arguments have a clear order and type.** For example, `{0}` is a display name (`String`), and `{1}` is a count (`Number`).
3. **Every locale uses the same argument contract**, while remaining free to reorder parameters and change sentence structure.
4. **Do not delete required placeholders** or arbitrarily replace `{0}` syntax with `%s`. `String.format` and `MessageFormat` are two different syntax systems.
5. **Changing wording does not require changing the key.** Changing the meaning or argument contract should be treated as an interface change between code and translation resources.
6. **Do not concatenate a complete sentence with another fragment** just for "reuse". Identical phrasing in two places today does not guarantee identical translations later.

If a target language does not need a specific parameter, a translation may intentionally omit it for a valid linguistic reason; nevertheless, critical keys should have tests to prevent accidentally dropping data. Especially for amounts, dates, names, and business conditions, essential information must never be lost.

## 11. How Does MessageFormat Differ from String.format and StringBuilder Concatenation?

- **String concatenation / `StringBuilder`:** useful for building simple structured technical data or combining parts that are **not prose sentences to be translated**. It should not be the primary mechanism for localizing whole sentences.
- **`String.format`:** supports `%s`, `%d`, `%.2f` style syntax and has an overload accepting `Locale`. It can be used for simple messages, though translations must follow `Formatter` argument indexing rules if they need to reorder arguments.
- **`MessageFormat`:** designed to handle message patterns with `{0}`, `{1,number}`, `{2,date}`, and choice constructs; commonly used together with `ResourceBundle`.

For example, `String.format(Locale.US, "Hello %s", name)` is still a valid short message. The value of `MessageFormat` becomes clearer when you have **an entire system of translation patterns** with parameters, numbers, and dates. The core takeaway of this lesson is that **the translation unit must be the whole sentence**, not necessarily that every sentence must use a single API.

## 12. Common Pitfalls in Production

| Pitfall | Why it is wrong | How to fix |
| --- | --- | --- |
| Translating `prefix` and `suffix` independently | Loses ability to reorder and adjust punctuation | Translate whole sentences with placeholders |
| Translating nouns separately and appending after numbers | Cannot handle multi-language singular/plural rules | Use full messages with an appropriate plural mechanism |
| Writing `{0}` in a hardcoded order in code | Translations struggle to place names and numbers naturally | Keep the argument contract, let translations reorder |
| Mixing `%s` with `{0}` | The two APIs have different syntaxes | Choose the formatter clearly per key |
| `MessageFormat` accidentally using the default locale | Numbers/dates can have the wrong regional format | Create the formatter with the user's locale |
| Concatenating pre-formatted values before translation | Locks in inappropriate number separators and time zones | Pass typed values, format in the message or via proper formatters |
| Forgetting to escape apostrophes | Placeholders become quoted and render incorrectly | Use `''` and write tests |
| Using one English plural branch for all locales | Multilingual rules are more complex | Use a proven localized plural solution |
| Merging translations that look identical in text but differ in meaning | Translators lack context | Name keys by purpose |
| Treating `MessageFormat` as an XSS/SQL filter | It only formats messages | Escape for the output context; use prepared statements/proper serializers |
| Sharing mutable `MessageFormat` objects across threads | Unsafe for concurrent updates/formatting | Create per-use instances, or manage copies/synchronization properly |

`MessageFormat` has mutable state via `applyPattern`, `setFormat`, etc. Do not assume a mutable instance shared freely across threads is thread-safe. Create a new instance when rendering or apply a verified concurrency strategy.

User data passed into `{0}` is inserted as data; `MessageFormat` does **not** perform HTML escaping. If the result is placed into HTML, JSON, SQL, or logs, the consuming layer must still apply context-appropriate encoding/escaping.

## 13. Testing: Proving Translations Are Natural and Complete

For each parameterized key, you should check:

- **Reordering:** one language uses `{0}` before `{1}`, another reverses the order, while code still passes the same data.
- **Preserving types:** counts passed as `Number`, dates as `Date`/types supported by the formatter, without losing information via early `toString`.
- **Correct punctuation:** spaces, commas, periods, braces, and single quotes are not malformed.
- **Required parameters present:** the resulting message displays mandatory business values.
- **Numeric cases:** 0, 1, 2, many, boundary values, and all required plural categories.
- **Different locales:** run with `vi-VN`, `en-US`, and all actually supported locales; verify number and date formatting.
- **Resources:** keys exist in the base bundle; all translations contain valid patterns, placeholders match the contract, and none are missing.
- **Fallback:** if a locale lacks a translation, the display policy is intentional; do not assume `ResourceBundle` will always pick the desired language.
- **Dangerous content:** for data containing `<`, `&`, quotes, or special characters, ensure the output layer applies appropriate escaping.

A typical test can directly assert the two stdout lines from section 4. Beyond automated tests, **real linguistic review** is necessary because a pattern can be syntactically valid yet grammatically wrong.

## 14. When Are Advanced Solutions Needed?

JDK `MessageFormat` is well-suited for learning whole-sentence principles, parameter insertion, number/date formatting, and handling certain `choice` patterns. For projects with many languages requiring complex plural/gender rules, sentence reordering, and deep quantity localization, you can use solutions based on ICU MessageFormat or a framework's i18n library, with clear formatting and resource policies.

Whichever tool you choose, the principles remain the same:

- **The whole sentence is the translation unit**, including punctuation and grammatical structure.
- **Dynamic data consists of contracted parameters**, not sentence fragments.
- **Translators have context** about parameter meanings and types.
- **The user's locale controls display formatting**; never accidentally use the server locale.
- **Each translation is tested as a complete message**, including error and fallback cases.

## 15. Hands-On Exercises

1. Change `count = 2` to `count = 12` in section 4. Confirm that both translations still use the same argument list; only the placeholder positions differ.
2. Write a version concatenating `prefix + name + middle + count + suffix`. Try moving the person's name to the end of the sentence; observe that you have to modify Java code or add custom logic.
3. Add a `messages_fr.properties` file with a whole French sentence and the same contract where `{0}` is the name and `{1}` is the count. Update the program to invoke the `fr-FR` locale without adding new concatenation branches.
4. Create a pattern containing an apostrophe: `You''re welcome, {0}!`. Try changing it to a single quote to observe how the parser behaves differently.
5. Add a message about the number of files or registrations. Test 0, 1, 2, 5, 21; identify the singular/plural rules of each supported language before choosing between `choice` or an advanced plural mechanism.
6. Try passing a name containing `<tag>` as an argument. Note that `MessageFormat` does not automatically escape HTML; if rendering on the web, encode it for the HTML context.

**Takeaway:** The flaw with concatenating text fragments is not just verbose code. It strips translators of the ability to write **a natural, complete sentence**. `MessageFormat` solves this by keeping the message intact, while dynamic parts are marked with placeholders that can be placed at any appropriate position in the translation.

## References

- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle JDK 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
