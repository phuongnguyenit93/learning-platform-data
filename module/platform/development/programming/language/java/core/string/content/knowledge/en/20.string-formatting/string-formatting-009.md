# MessageFormat When Templates Must Reorder Arguments by Language

## Objectives

After this lesson, you will be able to:

- Explain why translating a sentence by concatenating fixed strings often causes wrong word order, prepositions, and grammatical structure.
- Use `java.text.MessageFormat` with **indexed** placeholders `{0}`, `{1}`, `{2}` to place the same data in different positions across translations.
- Combine `ResourceBundle` and `Locale` to select message templates by language while the program keeps the passed argument order unchanged.
- Recognize `MessageFormat` syntax for numbers, dates/times, single quotes, curly braces, and important limitations in internationalization (i18n).

## 1. Why Is Reordering by Language Necessary?

Suppose an application announces that **Lan sent PDF to Minh at 09:00**. English and Vietnamese can express the same event while placing the time in different positions:

- English: “Lan sent PDF to Minh at 09:00.”
- Vietnamese: “Lúc 09:00, Lan gửi PDF cho Minh.”
- Japanese (one illustrative phrasing): “09:00にLanがMinhへPDFを送りました。”

Hardcoded concatenation like the following is very difficult to localize:

~~~java
String message = sender + " sent " + item + " to " + receiver + " at " + time;
~~~

If you translate by simply replacing the word `sent` with `gửi`, connecting words or component order can still be wrong. A better approach is to **translate the entire sentence template**, letting the translator choose where each argument goes.

`MessageFormat` takes a **pattern** containing numbered placeholders, along with an array of arguments:

~~~text
English: {0} sent {2} to {1} at {3}.
Tiếng Việt: Lúc {3}, {0} gửi {2} cho {1}.
日本語: {3}に{0}が{1}へ{2}を送りました。
~~~

All three templates use the same mapping:

| Index | Meaning | Illustrative Value |
| --- | --- | --- |
| `{0}` | Sender | `Lan` |
| `{1}` | Recipient | `Minh` |
| `{2}` | Item/file sent | `PDF` |
| `{3}` | Time | `09:00` |

**Core point:** the index indicates **which argument** is used, without forcing arguments to appear in ascending order. A template can place `{3}` before `{0}`, reuse `{0}` multiple times, or omit an argument. The order of elements in the array passed to `format` remains stable.

## 2. Standalone Runnable Java 17+ Example: Reordering by Locale

Save to a file `MessageOrderDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageOrderDemo {
    public static void main(String[] args) {
        Object[] values = {"Lan", "Minh", "PDF", "09:00"};

        String english = "{0} sent {2} to {1} at {3}.";
        String vietnamese = "Lúc {3}, {0} gửi {2} cho {1}.";
        String japanese = "{3}に{0}が{1}へ{2}を送りました。";

        System.out.println(
                new MessageFormat(english, Locale.ENGLISH).format(values));
        System.out.println(
                new MessageFormat(vietnamese, Locale.forLanguageTag("vi-VN"))
                        .format(values));
        System.out.println(
                new MessageFormat(japanese, Locale.JAPANESE).format(values));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 MessageOrderDemo.java
java MessageOrderDemo
~~~

Output (view in a UTF-8 capable terminal):

~~~text
Lan sent PDF to Minh at 09:00.
Lúc 09:00, Lan gửi PDF cho Minh.
09:00にLanがMinhへPDFを送りました。
~~~

**Notable observations:**

1. The `values` array is created **once** with a fixed order: sender, recipient, sent item, time.
2. English places `{3}` at the end of the sentence; Vietnamese and Japanese can place `{3}` at the start.
3. You do not have to reorder elements in `values` for each `Locale`; each pattern decides the order of appearance.
4. The example uses `String`s like `"09:00"` and `"PDF"` so the output is deterministic. In real applications, represent times, currencies, and formatted values using appropriate data types, then format them for the recipient's locale.

A `MessageFormat` object has two independent components: the **sentence template** to order components, and the **Locale** to govern how language/region-sensitive types like numbers or dates are formatted. Choosing a `Locale` does not automatically translate English text inside a pattern; the program must supply translated templates.

## 3. How MessageFormat Interprets Placeholders

Common general syntax:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Where:

- `argumentIndex` is a non-negative integer, 0-based; corresponds to the element at the same index in the `Object[]` passed to `format`.
- `formatType` can be `number`, `date`, `time`, `choice`, or omitted when only the text value is needed.
- `formatStyle` specifies display style, such as `short`, `medium`, `long`, or `integer`, depending on `formatType`.

Template examples:

| Pattern | Meaning |
| --- | --- |
| `"Hello {0}!"` | Inserts argument 0 |
| `"{1} invited {0}"` | Swaps the positions of two arguments |
| `"{0} / {0}"` | Uses the same argument twice |
| `"Total: {0,number,integer}"` | Formats argument 0 as an integer per locale |
| `"Date: {0,date,short}"` | Formats a date argument in the locale's short style |

`MessageFormat` **does not use variable names as placeholder keys** in standard Java syntax. `{sender}` is not valid named-substitution syntax in `java.text.MessageFormat`; use `{0}` and clearly document the mapping between indices and parameter meanings. If you change parameter positions in code but forget to update the convention, translated templates can display the wrong data while still running.

When a template requests an index that does not exist in `Object[]`, `MessageFormat` cannot retrieve the intended value. Validate argument counts and types in the program or test translations. Do not treat successful Java compilation as proof that all translation resources are valid.

## 4. Separating Translated Sentences with ResourceBundle

The example in Section 2 illustrates the mechanism with strings placed directly in code. In real applications, templates should live in translation files selected by `ResourceBundle` according to `Locale`. That way, translators can adjust placeholder positions without modifying Java logic.

Suppose four files sit in the **same directory** when compiling/running:

~~~text
LocalizedMessageDemo.java
messages.properties
messages_en.properties
messages_vi.properties
messages_ja.properties
~~~

Contents of `messages.properties` — fallback default when no matching translation exists:

~~~properties
sent={0} sent {2} to {1} at {3}.
~~~

Contents of `messages_en.properties`:

~~~properties
sent={0} sent {2} to {1} at {3}.
~~~

Contents of `messages_vi.properties`:

~~~properties
sent=Lúc {3}, {0} gửi {2} cho {1}.
~~~

Contents of `messages_ja.properties`:

~~~properties
sent={3}に{0}が{1}へ{2}を送りました。
~~~

Save the following program into `LocalizedMessageDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    private static String buildMessage(Locale locale, Object[] values) {
        ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
        String pattern = bundle.getString("sent");
        return new MessageFormat(pattern, locale).format(values);
    }

    public static void main(String[] args) {
        Object[] values = {"Lan", "Minh", "PDF", "09:00"};

        System.out.println(buildMessage(Locale.ENGLISH, values));
        System.out.println(
                buildMessage(Locale.forLanguageTag("vi-VN"), values));
        System.out.println(buildMessage(Locale.JAPANESE, values));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java LocalizedMessageDemo
~~~

Output:

~~~text
Lan sent PDF to Minh at 09:00.
Lúc 09:00, Lan gửi PDF cho Minh.
09:00にLanがMinhへPDFを送りました。
~~~

Execution flow:

1. `ResourceBundle.getBundle("messages", locale)` looks up the resource family with base name `messages` and selects the appropriate translation. For instance, `vi-VN` may look for a country-specific bundle first, then fall back to the language bundle `messages_vi.properties`.
2. `bundle.getString("sent")` retrieves the raw message template for key `sent`. Keys stay stable; pattern content can differ per language.
3. `new MessageFormat(pattern, locale)` creates a formatter with the specific locale.
4. `format(values)` applies the placeholders to the right array elements, regardless of the order in which they appear in the sentence.

Since Java 9, `ResourceBundle`'s reader for `.properties` supports UTF-8 (with historical fallback), so Vietnamese or Japanese text can be saved directly in UTF-8 resource files. Control editor and runtime encodings to avoid garbled characters. If the required translation file or key does not exist on the lookup path, `getBundle`/`getString` calls can throw `MissingResourceException`.

### Maintaining Parameter Contracts During Translation

Create a testable specification for each key:

~~~text
sent:
  {0} = sender (String)
  {1} = recipient (String)
  {2} = item sent (String)
  {3} = time already formatted for display (String)
~~~

Translators are allowed to **change placeholder order within the pattern**, but must not silently alter the meaning of each index. If a translation mistakenly writes `{4}` or changes `{1}` to mean sender, the output will be wrong. Test all supported locales and realistic values, rather than testing only the default language.

### Note on Fallback

`ResourceBundle` follows language/country variant lookup rules and may also consult the JVM's default locale before using the root bundle in certain situations. Therefore, keep a base bundle `messages.properties`, provide `messages_en.properties` when a deterministic English bundle is required, and write tests with explicit locales. Do not assume a missing translation always falls back straight to the root bundle immediately.

## 5. Formatting Numbers, Dates, and Times by Locale

Reordering components is only one part of localization. For structured values, `MessageFormat` also has direct formatting syntax:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        Object[] values = {"Lan", 1234.5};

        String en = "{0}: {1,number}";
        String vi = "Số điểm của {0}: {1,number}";

        System.out.println(
                new MessageFormat(en, Locale.US).format(values));
        System.out.println(
                new MessageFormat(vi, Locale.forLanguageTag("vi-VN"))
                        .format(values));
    }
}
~~~

Save `LocaleNumberDemo.java` and run with `javac -encoding UTF-8 LocaleNumberDemo.java`, then `java LocaleNumberDemo`. The thousands and decimal separators in the two lines can vary with the locale data used by your Java distribution, so observe the actual printed characters (including special whitespace) rather than hardcoding a separator expectation.

Several rules worth remembering:

- `{0,number}` and `{0,number,integer}` use `Locale`-specific number formatting; `integer` pertains to **formatting/rounding for display**, not converting the input into an integer type.
- `{0,number,currency}` uses currency formatting for the formatter's locale. If you need to specify a particular business currency (e.g., USD vs. VND), manage `Currency` and `NumberFormat` separately to avoid wrong symbols or units.
- `{0,date,short}` and `{0,time,short}` require a compatible date/time argument, typically `java.util.Date`; do not pass an arbitrary date string and expect the formatter to recognize it.
- Legacy date/time formats under `MessageFormat` may use the JVM's default time zone. If the application must display a fixed time zone, control the time zone through an appropriate formatter or pre-prepare localized values.
- With the modern `java.time` API, `DateTimeFormatter` supports more temporal types, locales, and explicit time zones. You can use it to format into a `String` before inserting into a `MessageFormat` template, especially when working with `Instant`, `ZonedDateTime`, or multi-timezone schedules.

Also distinguish **grammar translation** from **value formatting**: swapping `{1}` and `{0}` solves parameter order, but does not automatically translate product names, singular/plural nouns, or time expressions. Such display data must be localized appropriately when business logic requires it.

## 6. Single Quotes and Curly Braces: `MessageFormat` Syntax Traps

`MessageFormat` has its own syntax: a single quote `'` is used to quote segments of a pattern, while `{...}` is used for placeholders. This is especially important when translating messages into languages with apostrophes.

Java 17 example:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        Object[] values = {"done"};

        System.out.println(new MessageFormat(
                "It's {0}.", Locale.ENGLISH).format(values));

        System.out.println(new MessageFormat(
                "It''s {0}.", Locale.ENGLISH).format(values));

        System.out.println(new MessageFormat(
                "Use '{' and '}' around {0}.", Locale.ENGLISH)
                .format(new Object[] {"x"}));
    }
}
~~~

Save `MessageQuoteDemo.java` and run `javac -encoding UTF-8 MessageQuoteDemo.java` and `java MessageQuoteDemo`. Output:

~~~text
Its {0}.
It's done.
Use { and } around x.
~~~

**Why is the first line surprising?** In the pattern `"It's {0}."`, a single `'` opens a quoted region and turns `{0}` into literal text, preventing the placeholder from being substituted. Write `"It''s {0}."` to represent a literal apostrophe when using `MessageFormat` syntax.

To display curly braces without starting a placeholder, quote them in the pattern such as `"'{' "` or `"'}'"` (for example, `"Use '{' and '}' around {0}."`). Do not use Java String or regex escape rules to guess `MessageFormat` rules; this is a different grammar.

In `.properties` files, distinguish file-format escaping, Java string escaping, and `MessageFormat` syntax. For example, a translation containing words with literal apostrophes must still follow the doubled `''` rule when passed to `MessageFormat`, even when the content was loaded from a `ResourceBundle`.

## 7. How Does `MessageFormat` Differ from `String.format`?

Both support parameterized formatting, but their syntax and purposes usually differ:

| Criterion | `MessageFormat` | `String.format` / `Formatter` |
| --- | --- | --- |
| Placeholders | `{0}`, `{1}`, `{0,number}` | `%s`, `%d`, `%.2f` |
| Reordering parameters in template | Indices `{2}`, `{0}` | Argument indices `%2$s`, `%1$s` |
| Templates in translation files | Works well with `ResourceBundle` and `Locale` | Also usable, but must preserve `%...` syntax |
| Locale-aware numbers/dates | Built-in `number/date/time` syntax | Formatter has its own conversions and flags |
| Special characters to watch | Apostrophe `'`, braces `{ }` | Percent sign `%`, conversion characters |
| Practical choice | i18n message templates with language-dependent argument positions and presentation styles | Formatted string output with type/width/precision specifiers, logs, numeric tables |

`MessageFormat` is not the only way to swap argument order: `String.format` also supports positional references. In this lesson, `MessageFormat` is the right choice because the application **already uses locale-specific message templates** and can take advantage of number/date display syntax inside translation resources.

Do not mix syntaxes: passing `"%2$s -> %1$s"` to `MessageFormat` will not substitute `Formatter`-style specifiers; and passing `"{1} -> {0}"` to `String.format` will not understand `MessageFormat`-style placeholders.

## 8. Common Mistakes and How to Avoid Them

**Mistake 1 — Concatenating sentences word-by-word before translating.** Joining words with `+` or scattered placeholders can break grammar when a language requires reordering components. Translate **complete sentence templates**, letting translators decide where `{0}`, `{1}` belong.

**Mistake 2 — Changing data order to accommodate translations.** Altering `Object[]` per `Locale` breaks the index contract. Keep argument order fixed in code, and only reorder placeholders in translation resources.

**Mistake 3 — Writing the wrong index or argument type.** A template `{2,number}` will fail if argument 2 is `"PDF"` instead of a number. Define a parameter contract table, and test every translation with values of the actual data types.

**Mistake 4 — Thinking `Locale` translates sentences automatically.** `Locale.forLanguageTag("vi-VN")` only informs the formatter of regional/language rules. To get a Vietnamese sentence, you must load the Vietnamese template via `ResourceBundle` or an equivalent i18n system.

**Mistake 5 — Failing to escape apostrophes in `MessageFormat`.** A single `'` in a pattern can prevent placeholders from being processed. Use `''` when a literal apostrophe must appear, and inspect translations containing quotes.

**Mistake 6 — Translating only the template while forgetting the values.** Passing `"Monday"`, `"a report"`, or a US-style date string into a Vietnamese template still yields mismatched content. Values carrying language or regional formatting must also be localized.

**Mistake 7 — Sharing a single mutable `MessageFormat` across threads.** `MessageFormat` holds mutable state and is not thread-safe. Create a new formatter per operation or use separate thread-local instances. If performance matters, manage pattern/bundle caching and controlled per-thread formatter strategies instead of sharing a single mutated object.

**Mistake 8 — Treating i18n messages as an all-purpose pluralization engine.** Standard Java `MessageFormat` supports `choice` syntax for some quantity cases, but does not cover every grammatical gender, declension, or singular/plural rule across all languages. When complex plural/gender rules are needed, consider specialized i18n libraries such as ICU MessageFormat and proper translation models; do not append `"s"` suffixes using English logic.

**Mistake 9 — Not testing all locales.** A working English version does not guarantee Vietnamese or Japanese works. Test with normal inputs, empty strings, varied numbers/dates, special characters, display length limits, and reordered placeholders.

**Mistake 10 — Believing formatters automatically escape HTML or code.** `MessageFormat` only creates display strings; it does not sanitize HTML, SQL, or content placed into risky contexts. When rendering on the web, apply output-context escaping and avoid using untrusted patterns as control strings.

## 9. Practice: Predict the Output Yourself

Given data:

~~~java
Object[] values = {"Mai", "Lan", "file.zip", "10:30"};
~~~

And templates:

~~~text
A = "{0} gửi {2} cho {1} lúc {3}."
B = "Vào {3}, {1} nhận {2} từ {0}."
C = "{0} đã gửi; người gửi là {0}."
~~~

Try mentally substituting each index before running the program:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class OrderQuiz {
    public static void main(String[] args) {
        Object[] values = {"Mai", "Lan", "file.zip", "10:30"};
        String[] patterns = {
            "{0} gửi {2} cho {1} lúc {3}.",
            "Vào {3}, {1} nhận {2} từ {0}.",
            "{0} đã gửi; người gửi là {0}."
        };
        for (String pattern : patterns) {
            System.out.println(new MessageFormat(
                    pattern, Locale.forLanguageTag("vi-VN")).format(values));
        }
    }
}
~~~

Save `OrderQuiz.java` and run with `javac -encoding UTF-8 OrderQuiz.java` and `java OrderQuiz`. Output:

~~~text
Mai gửi file.zip cho Lan lúc 10:30.
Vào 10:30, Lan nhận file.zip từ Mai.
Mai đã gửi; người gửi là Mai.
~~~

All three sentences use the same data array. A pattern can **reorder**, **repeat**, or **omit** an argument; template authors control phrasing without changing data-passing logic.

### Project Adoption Checklist

1. Name message keys with stable meanings such as `sent`, `payment.received`, `notification.invite`.
2. Document indices `{0}`, `{1}`, ... along with types and meanings, and keep that contract consistent across all locales.
3. Translate complete sentences in each resource bundle; allow reordering placeholders and adjusting connectors for natural phrasing.
4. Load patterns by `Locale`, construct `MessageFormat(pattern, locale)`, and pass **the exact same parameter order**.
5. Test translations for missing/wrong placeholders, apostrophes, number/date formatting, bundle fallback, and longer-than-expected text.

## Official References

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
