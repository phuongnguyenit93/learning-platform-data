# Message Patterns and Indexed Arguments {0}, {1}

`java.text.MessageFormat` lets you **create a message pattern containing placeholders for dynamic data**. Instead of hardcoding string concatenation in your program, the application stores a pattern like `"Hello {0}, you have {1} messages."` and passes the user's name and message count when rendering. Symbols such as `{0}` and `{1}` are **indexed arguments** and are replaced by the corresponding element in the argument array.

This is a key foundation for localization: given the same set of data, different languages can arrange sentence components in different orders without changing code. When needed, `MessageFormat` also formats numbers, dates, and times using a specific `Locale`.

The goal of this lesson is to understand **message patterns, index-to-value mapping, appearance order, repeated indices, format syntax, escaping, and error cases** so you can use them properly with `ResourceBundle`.

## 1. What Is a Message Pattern?

A pattern is a string containing fixed text and replacement placeholders:

~~~text
Hello {0}, you have {1} messages.
~~~

Where:

- `Hello `, `, you have `, and ` messages.` are fixed text.
- `{0}` references the **first argument**, at index 0.
- `{1}` references the **second argument**, at index 1.
- The values are not inside the pattern; the code passes the arguments when formatting.

Standalone program example `BasicMessageDemo.java`:

~~~java
import java.text.MessageFormat;

public class BasicMessageDemo {
    public static void main(String[] args) {
        String pattern = "Hello {0}, you have {1} messages.";
        String result = MessageFormat.format(pattern, "Mai", 3);

        System.out.println(result);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BasicMessageDemo.java
java BasicMessageDemo
~~~

Output:

~~~text
Hello Mai, you have 3 messages.
~~~

The static call `MessageFormat.format(pattern, Object...)` is convenient for short examples, but **it does not allow passing a `Locale` directly in this signature**; it creates a formatter using the JVM's default format locale. In multi-user services, you should create `MessageFormat` with an explicit `Locale`, as shown in the next section.

## 2. Indices Start at 0, Not 1

The basic syntax of a replacement placeholder is:

~~~text
{argumentIndex}
~~~

`argumentIndex` is a non-negative integer representing the **position in the `Object[]` array**, starting from 0. Mapping:

| Pattern | Argument used | Example |
| --- | --- | --- |
| `{0}` | `arguments[0]` | Recipient name |
| `{1}` | `arguments[1]` | Quantity |
| `{2}` | `arguments[2]` | Price |
| `{3}` | `arguments[3]` | Timestamp or next detail |

For instance:

~~~java
Object[] arguments = {"Lan", 5, "October"};
String pattern = "{0} received {1} notifications in {2}.";
~~~

This is an **illustrative snippet inside a method**. When calling `new MessageFormat(pattern, locale).format(arguments)` with an appropriate locale, the three placeholders take values from `arguments[0]`, `arguments[1]`, and `arguments[2]`, respectively.

**Important:** `{1}` does not mean "the second parameter written in the pattern". It always refers to **the element at index 1 of the input array**, whether it appears at the beginning or the end of the sentence.

Java also uses notations like `{name}` in some other libraries/templates, but standard `java.text.MessageFormat` uses **integer indices**; `{username}` is not a valid named argument in this API.

## 3. Appearance Order May Differ from Argument Order

A core feature for translation: translators can **reorder placeholders** while still using the same set of arguments.

For example, a message displaying two values:

~~~text
{0} delivered {1} to you.
~~~

Another language might need:

~~~text
You received {1} from {0}.
~~~

Both still use `arguments[0]` for the sender and `arguments[1]` for the delivered item. The code does not have to change the order in which arguments are passed to match the placeholder order in the sentence, as long as the translation preserves the **meaning** of each index.

Runnable example `ArgumentOrderDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentOrderDemo {
    public static void main(String[] args) {
        Object[] arguments = {"first", "last"};
        MessageFormat formatter = new MessageFormat(
                "Positions: {1} then {0}, after that {1}.",
                Locale.US
        );

        System.out.println(formatter.format(arguments));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Output:

~~~text
Positions: last then first, after that last.
~~~

Thus:

- `{1}` is used **before** `{0}` in the sentence.
- The same `{1}` appears **twice**, each time reading `arguments[1]`.
- There is no "consume argument once in order and discard" mechanism: placeholders are **indexed references** and can be repeated.

The order in the `arguments` array is a contract between code and translators. If you change the meaning of index 0 from "person's name" to "quantity", every translation using `{0}` may become wrong even though the syntax remains valid.

## 4. Patterns Can Use a Subset or Repeat Arguments

A pattern is not required to reference **all** arguments passed in. For example, the pattern `"{1}"` can still be formatted with a two-element array; the element at index 0 simply does not appear.

Indices also do not have to appear consecutively in the pattern. A pattern `"{2} - {0}"` can omit `{1}`, as long as the argument at index 2 exists when needed.

However, at the business layer you should establish clear conventions for such cases to avoid passing the wrong arguments:

- Fix the argument order according to a **contract pattern** or meaningful data types.
- Verify that translations do not add placeholders beyond the number of arguments the code can provide.
- If the same index is used multiple times with **different format types**, check consistency carefully: `{0}`, `{0,number,integer}`, and `{0,number,currency}` can produce three different representations of the same value.

**Note:** Passing extra arguments generally does not cause an error just because they are unused; that is not a sufficient mechanism to verify the correctness of patterns and code.

## 5. Full Syntax: Index, Format Type, and Format Style

A replacement placeholder can have the form:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Three components:

1. **`argumentIndex`:** position in the array, such as `0` or `1`.
2. **`formatType`:** formatter type, commonly `number`, `date`, `time`, `choice`.
3. **`formatStyle`:** display style; for `number`, this can be `integer`, `currency`, `percent`, or a custom number pattern; for `date`/`time`, it can be `short`, `medium`, `long`, `full`, or an appropriate pattern.

Examples:

| Placeholder | Meaning |
| --- | --- |
| `{0}` | Directly substitute argument 0; numeric/date objects may be formatted implicitly |
| `{1,number,integer}` | Format argument 1 as an integer for display |
| `{2,number,#,##0.00}` | Format argument 2 using a specific number pattern |
| `{1,number,currency}` | Format argument 1 as currency according to the locale |
| `{2,date,short}` | Format the date in argument 2 using the short date style |
| `{2,time,short}` | Format the time in argument 2 using the short time style |

The comma after `argumentIndex` is part of `MessageFormat` syntax. Without that comma, `{1}` is a plain placeholder.

### Example with an Explicit `Locale`

Create `TypedArgumentsDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class TypedArgumentsDemo {
    public static void main(String[] args) {
        String pattern =
                "Order {0}: {1,number,integer} items; " +
                "total {2,number,#,##0.00}";

        MessageFormat formatter =
                new MessageFormat(pattern, Locale.US);

        Object[] arguments = {"A-17", 12, 1234.5};

        System.out.println(formatter.format(arguments));
    }
}
~~~

~~~bash
javac TypedArgumentsDemo.java
java TypedArgumentsDemo
~~~

Output with standard `Locale.US` number formatting:

~~~text
Order A-17: 12 items; total 1,234.50
~~~

Explanation:

- `{0}` takes the string `"A-17"`.
- `{1,number,integer}` formats the value `12`.
- `{2,number,#,##0.00}` uses a number pattern requiring two decimal digits and thousands grouping per US conventions.
- `Locale.US` specifies the formatting conventions when creating the formatter.

The number pattern `#,##0.00` uses `DecimalFormat` pattern syntax. The comma/period characters **in the pattern** describe grouping and the decimal separator, while the **output characters** are adapted to the locale. You should not manually replace separators in the string after formatting.

For monetary data, `MessageFormat` only handles display; it **does not convert exchange rates**. For exact monetary amounts in business logic, prefer `BigDecimal` instead of computing money with `double`.

## 6. Placeholders Are Meaningful Syntax; Single Quotes Are Used for Escaping

In a `MessageFormat` pattern, curly braces `{` and `}` have syntactic meaning. If you want them to appear **literally**, you must quote them according to `MessageFormat` rules.

In particular, the single quote `'` is an escape character, **not** just an ordinary text apostrophe:

| Pattern | Meaning | Output when argument 0 is `X` |
| --- | --- | --- |
| `Value {0}` | Substitute argument | `Value X` |
| `Value '{0}'` | Quote the placeholder literally | `Value {0}` |
| `Value ''{0}''` | Two single quotes represent one literal single quote | `Value 'X'` |
| `Display '{0}' and value {0}.` | One literal placeholder, one substituted | `Display {0} and value X.` |

Runnable example `MessageQuotingDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuotingDemo {
    public static void main(String[] args) {
        MessageFormat quotedWord = new MessageFormat(
                "User ''{0}'' has finished.",
                Locale.US
        );
        MessageFormat literalBraces = new MessageFormat(
                "Display '{0}' and value {0}.",
                Locale.US
        );

        System.out.println(quotedWord.format(new Object[]{"Lan"}));
        System.out.println(literalBraces.format(new Object[]{"X"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MessageQuotingDemo.java
java MessageQuotingDemo
~~~

Output:

~~~text
User 'Lan' has finished.
Display {0} and value X.
~~~

In the first pattern, `''` produces a visible single quote, while `{0}` is still substituted. In the second pattern, the pair of single quotes around `{0}` turns it into literal text.

### Pitfalls with Natural Text

An English translation containing an apostrophe such as `don't` can break because the `'` character is interpreted as the start/end of a quoted section. In a `MessageFormat` pattern, write `don''t` to represent a literal apostrophe.

For example:

~~~text
Pattern:  Don''t forget {0}.
Output:   Don't forget X.
~~~

Do not use `\{0\}`-style escaping to quote placeholders: a backslash does not escape curly braces as it does in many other programming languages. Also do not automatically wrap every placeholder in single quotes, because doing so prevents them from **being substituted with arguments**.

For an unclosed single quote in a pattern, Java has specific handling rules that easily produce surprising results. Use balanced patterns, write tests for translations containing apostrophes, and explain quoting conventions to translators.

## 7. Missing Arguments, Wrong Types, and Invalid Patterns

### Missing Arguments

If a pattern references `{1}` but the array only has `arguments[0]`, formatting may **leave the `{1}` symbol intact** in the output string. This is dangerous behavior because the application might not throw an error and instead display a raw placeholder to the user.

Standalone example `MissingArgumentDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MissingArgumentDemo {
    public static void main(String[] args) {
        MessageFormat formatter =
                new MessageFormat("Missing {1}", Locale.US);

        System.out.println(formatter.format(new Object[]{"one"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingArgumentDemo.java
java MissingArgumentDemo
~~~

Output:

~~~text
Missing {1}
~~~

Because the array only has one element (index 0), `{1}` was not substituted. **Do not treat the formatter returning a string as proof that the pattern was supplied with enough arguments.**

### Malformed Patterns

Patterns such as `{abc}` (non-numeric index), `{0` (missing closing brace), or `{0,unknown}` (invalid format type) can cause construction or `applyPattern` to throw `IllegalArgumentException`.

Catch these errors during build, tests, or translation loading rather than waiting for a user request. For resource sets with multiple locales, test every pattern, not just the default locale.

### Wrong Argument Type

`{0,number,integer}` expects an argument suitable for numeric formatting. Passing a non-numeric text string can cause `IllegalArgumentException` when formatting. `null`, date objects, and special data types may be handled by different branches of the API; do not rely on implicit coercion when the business contract already defines the type.

Separate three categories of errors:

- **Pattern error:** unable to parse the replacement expression.
- **Argument contract error:** index does not exist, or data type is incompatible.
- **Translation semantic error:** the pattern is valid, but the translator used the wrong index, wrong plural form, or wrong meaning.

The Java compiler cannot automatically guarantee that pattern strings loaded from translation files always match the arguments at every call site.

## 8. Combining `MessageFormat` and `ResourceBundle`

In a multilingual application, message patterns usually reside in a `ResourceBundle`; `MessageFormat` takes the pattern string retrieved from the bundle and substitutes the arguments.

Example of a two-language resource set:

**File `Messages_en.properties`:**

~~~properties
notification=Hello {0}, you have {1,number,integer} messages.
~~~

**File `Messages_vi.properties`:**

~~~properties
notification=Xin chào {0}, bạn có {1,number,integer} tin nhắn.
~~~

**File `LocalizedMessageDemo.java`:**

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    private static String notification(Locale locale, String name, int count) {
        ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

        MessageFormat formatter =
                new MessageFormat(bundle.getString("notification"), locale);

        return formatter.format(new Object[]{name, count});
    }

    public static void main(String[] args) {
        System.out.println(notification(Locale.ENGLISH, "Mai", 3));
        System.out.println(notification(
                Locale.forLanguageTag("vi"), "Mai", 3));
    }
}
~~~

Run in the directory containing all three files:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java -cp . LocalizedMessageDemo
~~~

Output:

~~~text
Hello Mai, you have 3 messages.
Xin chào Mai, bạn có 3 tin nhắn.
~~~

In Java 17, `PropertyResourceBundle` supports reading `.properties` resources in UTF-8 via the JDK's compatibility mechanism; save files consistently in UTF-8. In real applications, place bundles on the runtime classpath/module in the proper structure, such as `src/main/resources`.

**Two objects handle two different responsibilities:**

1. `ResourceBundle` **selects the pattern string** based on the locale and lookup/fallback mechanism.
2. `MessageFormat` **replaces placeholders and formats values** according to the locale passed at instantiation.

If you only pass the locale to `getBundle` but construct `new MessageFormat(pattern)` without a locale, you might get the Vietnamese translation yet format numbers/dates using the JVM's default locale. Therefore, pass the **same effective locale** to both when the domain requires a unified context.

### Index Contract Between Code and Translations

In the two files above, `{0}` is **always** the name, and `{1}` is **always** the count. Translators are allowed to change placeholder order in the sentence, but must not arbitrarily change the meaning of each index.

For example, a notification sentence in one language could be written:

~~~properties
notification={1,number,integer} notifications are waiting for {0}.
~~~

Only the **order in the pattern** changes, not `new Object[]{name, count}`. That is why indexed arguments are useful for i18n.

Do not build a replacement mechanism using `String.replace("{0}", name)` for all messages: it does not understand quoting, format types, repeated parameters, or `MessageFormat`-specific syntax.

## 9. Passing Arguments to the Right Overload

`MessageFormat` has both static and instance methods, which can easily cause confusion when working with argument arrays:

~~~java
// Short form: uses the default FORMAT Locale at the time of formatting.
String a = MessageFormat.format("Xin chào {0}", "Mai");

// Explicit form: creates a formatter with a specific locale.
MessageFormat formatter =
        new MessageFormat("Xin chào {0}", Locale.forLanguageTag("vi-VN"));
String b = formatter.format(new Object[]{"Mai"});
~~~

This is a **snippet placed inside a method**, requiring imports for `java.text.MessageFormat` and `java.util.Locale`. Both approaches return `Xin chào Mai` in this example, but **the second approach controls the locale** and is explicit when arguments are numbers/dates.

With the instance method `format(Object[] arguments)`, each position in the array matches an index in the pattern. When an API takes `Object...` varargs, arguments passed as a list are also packed into an array. Read the overload signature carefully instead of mistakenly passing an `Object[]` as a **single** argument in custom-built APIs.

If multiple business methods share the same pattern, create a helper function with meaningfully named parameters, such as `formatTransfer(sender, recipient, amount, locale)`, and inside it pack them into `Object[]{sender, recipient, amount}` following a stable convention. This avoids scattering index ordering across many places.

## 10. Locale Determines Number/Date Presentation, Not Index Meaning

Consider the pattern:

~~~text
{0} ordered {1,number,integer} items on {2,date,short}.
~~~

The elements can include a person's name, a quantity, and a date object:

~~~java
Object[] arguments = {
        "Mai",
        4,
        new java.util.Date(0)
};
~~~

This is an **illustrative snippet**, not a complete program. When creating a formatter with `new MessageFormat(pattern, locale)`:

- `{0}` remains the name, even when the locale changes.
- `{1,number,integer}` uses the locale's number conventions.
- `{2,date,short}` uses the locale's short date rules for a compatible temporal object.

A `java.util.Date` represents an instant in time, so the displayed date may also depend on the time zone selected by the underlying formatter. With Java Time (`LocalDate`, `Instant`), standard `MessageFormat` does not automatically support all modern time types in the same way as `DateTimeFormatter`; you can convert appropriately or **pre-format** with `java.time.format.DateTimeFormatter` and pass a string.

Do not assume `MessageFormat` automatically converts currencies or time zones. It only applies formatters to parameters; unit conversion, exchange rates, and time logic must be handled separately.

### Why Can Localized Results Differ Across JDKs?

The runtime's CLDR/locale provider data determines many symbols, date patterns, number grouping rules, and display names. Therefore, the same pattern and arguments may produce slightly different strings on two runtime versions. When you want stable examples or snapshot tests, choose an explicit locale, pin the test environment, and avoid comparing visually similar Unicode characters (regular spaces vs. non-breaking spaces).

## 11. Pluralization Rules and the Limits of Indexed Placeholders

`{0}` and `{1}` help **insert and arrange** data; they **do not automatically choose singular/plural grammar** for a language. For example, an English pattern:

~~~properties
notification=You have {0,number,integer} messages.
~~~

will produce `You have 1 messages.` for the number 1: the placeholder only substitutes the number, without turning `messages` into `message`. Similarly, a Vietnamese sentence may need different natural phrasing depending on the count or context.

Java provides the `choice` format in `MessageFormat` to select text based on numeric thresholds, but the plural grammar of the world's languages is far richer than a few threshold conditions. For large international applications, you may need an i18n solution with per-language plural rules, such as a library supporting ICU MessageFormat or a message catalog system with proper plural support.

**Do not declare a pattern with `{0,number,integer}` as a "plural-handled" translation.** This lesson focuses on **indexed arguments**, not as a replacement for a dedicated topic on plural rules.

## 12. User-Supplied Strings and Pattern Safety

If a user's name is `"{1}"` and the code passes it as an **argument**, that value is treated as data and **does not automatically become a new placeholder to evaluate** in normal formatting. This is why you should clearly separate the **pattern** controlled by the application from **arguments** supplied by users or data providers.

Conversely, putting arbitrary input into the **pattern** can cause syntax errors, produce unpredictable output, or complicate content control. Never construct a pattern by concatenating untrusted content directly into the pattern string.

Example to avoid:

~~~java
// Do not do this: user input is concatenated directly into the pattern.
String pattern = "Comment: " + userInput + " - {0}";
MessageFormat formatter = new MessageFormat(pattern, locale);
~~~

If `userInput` contains `'` or `{...}`, the parser may misinterpret it as pattern syntax. The safe approach in terms of data separation:

~~~java
String pattern = "Comment: {0} - {1}";
MessageFormat formatter = new MessageFormat(pattern, locale);
String rendered = formatter.format(new Object[]{userInput, status});
~~~

Both snippets above are **in-method snippets**, with `userInput`, `locale`, and `status` declared in the caller. Argument substitution prevents input content from controlling **`MessageFormat` syntax**. However, if the output will go into HTML, SQL, or shell commands, the application still needs context-appropriate escaping/encoding and specialized safe APIs; `MessageFormat` is not an HTML sanitizer.

## 13. Formatter Lifecycle and Multithreaded Usage

`MessageFormat` is a **mutable** class, with methods such as `applyPattern(...)`, `setFormat(...)`, and `setLocale(...)`. By the API contract, sharing a single instance across multiple threads without synchronization is not guaranteed to be safe.

Do not cache a `static MessageFormat` and reuse it for requests with different locales. That design can be wrong for both **locale** and **thread-safety**.

Options:

- Create a new `MessageFormat(pattern, locale)` when needed, especially if formatting volume is modest.
- Cache **immutable patterns** by message key/locale, then create a new formatter per use.
- If you truly need to cache formatters, use cloning or a safe synchronization strategy after measuring performance and understanding locale/pattern settings.

In a multi-user application, select each request's locale explicitly. Do not call `Locale.setDefault(...)` to serve an individual request, because the default state is shared across the JVM and can mix data across threads.

## 14. Testing the Contract Between Patterns and Arguments

A practical test checklist should include:

| Case | What to verify |
| --- | --- |
| Pattern using `{0}` and `{1}` | Correct values for index 0 and 1 |
| Translation reversing `{1}` before `{0}` | Input data is not reordered to match appearance order |
| Repeated index | Same parameter is inserted at every position |
| Missing `arguments[1]` | `{1}` is not exposed in the UI |
| Extra arguments | Successful formatter execution is not treated as contract validation |
| Number/date types | Values have types compatible with the formatter |
| Pattern with apostrophes | `''` and literal quotes are handled properly |
| Pattern loaded from bundle | Key exists, pattern is valid, locale is accurate |
| Different languages | Sentence structure can change while index meaning stays fixed |
| Concurrent execution | Mutable `MessageFormat` is not shared without synchronization |

When checking placeholders, **do not just search for the plain string `"{0}"` with regex** and consider it sufficient: a pattern may contain `{0,number,integer}`, a placeholder quoted as literal text, or nested formats. Across multiple locales, use an appropriate parser/test mechanism or representative sample cases, and compare actual output against the content specification.

A thorough test suite should cover every locale the product officially supports, patterns with varying indices, and strings containing single quotes. When a translation reorders indices while remaining syntactically valid, checking the **semantic meaning of arguments** determines pass or fail.

## 15. Common Misconceptions

1. **"`{1}` is the first argument."** False: indices start at 0; `{1}` is the second element.
2. **"Placeholder order must match array order."** False: `{1}` can come before `{0}`; this is a key capability when translating sentences.
3. **"Each index can only be used once."** False: the same `{0}` can be repeated in multiple places.
4. **"The pattern will fail immediately if an index is missing."** Not always true; in some cases, the missing placeholder is left intact in the output.
5. **"`{name}` is a valid argument name in `java.text.MessageFormat`."** False: the standard API uses integer indices.
6. **"Wrap `{0}` in single quotes to put quotes around the result."** False: `'{0}'` produces the literal text `{0}`; to display quotes around the value, use `''{0}''`.
7. **"Use `\` to escape curly braces."** Incorrect under `MessageFormat` pattern syntax.
8. **"Number pattern `#,##0.00` always produces a decimal point."** False: the output depends on the locale; symbols in the pattern have conventional meaning.
9. **"`MessageFormat` translates content automatically."** False: translations are patterns supplied by the application (e.g., via `ResourceBundle`).
10. **"MessageFormat is thread-safe because it only formats strings."** False: the class has mutable state and is not guaranteed thread-safe.
11. **"`{0,number,integer}` handles plurals."** False: it formats numbers, not word forms.
12. **"User input can be inserted directly into the pattern."** Easily breaks syntax; pass input as an argument.

## 16. Workflow for Applying in Real Projects

1. **Define message keys and index contracts**: e.g., `order.confirmed` has index 0 = order ID, 1 = quantity, 2 = amount.
2. **Store per-language patterns** in bundles/catalogs and allow translators to change placeholder **positions**.
3. **Keep placeholder meanings consistent** across translations; when specific type formatting is needed, specify `number`/`date`/`time` appropriately.
4. **Pass the effective `Locale` explicitly** to `MessageFormat` so it does not rely on the JVM default.
5. **Pass dynamic values as arguments**, never concatenate them into the pattern.
6. **Test translations**: complete indices, correct types, apostrophe escaping, plural grammar, fallback, and output for major locales.
7. **Manage formatter lifecycle**: avoid sharing mutable instances without a thread-safety strategy.
8. **Encode content at the output boundary** if the final string goes into HTML or another sensitive format.

### Self-Check Questions

**1.** Given `new Object[]{"Lan", 5}`, what data does `{1}` retrieve?

**Answer:** The number `5` (the element at index 1); `{0}` retrieves the string `"Lan"`.

**2.** Is the pattern `"{1} - {0} - {1}"` valid?

**Answer:** Valid. With the array `{"A", "B"}`, the output is `B - A - B`.

**3.** Why can `{1}` be placed before `{0}` when translating a sentence?

**Answer:** Placeholders reference by index, independent of appearance position, so translations can use natural word order.

**4.** How do you display single quotes around the value of `{0}`?

**Answer:** Use `''{0}''` in the `MessageFormat` pattern.

**5.** When should the pattern and values use the same locale?

**Answer:** When the application needs both the translation and value formatting to match a consistent user context: load the pattern from the bundle for that locale and construct `MessageFormat(pattern, locale)`.

**6.** Why is returning the string `Missing {1}` a sign that inputs should be checked?

**Answer:** Index 1 may not have been provided; `MessageFormat` does not necessarily throw an error for every missing index.

**Takeaway:** `{0}`, `{1}`, and `{2}` form a **positional contract between the message pattern and the argument array**. Appearance order may vary by language; the data bound to each index must keep the same meaning. Combine `ResourceBundle` to select the pattern, `MessageFormat` to substitute/format arguments, and thoroughly test escaping, missing indices, and locales.
