# MessageFormat Locale and Component Formatters

**MessageFormat** in Java Core constructs parameterized messages from a text pattern: the wording is supplied by translations, while the inserted values can be numbers, dates, times, percentages, or currency amounts. Passing the right **Locale** ensures parameters render according to the reader's conventions. However, MessageFormat has a detail that easily causes bugs: **the locale held by MessageFormat does not automatically update component formatters that were already created**.

This lesson examines the locale mechanism of **java.text.MessageFormat**, its subformatters such as **NumberFormat**, **DecimalFormat**, **DateFormat**, **SimpleDateFormat**, and **ChoiceFormat**, how to replace them, how to use them with modern **java.time**, and common pitfalls when applications run across multiple environments or serve multiple users. Examples target Java 17+.

## 1. Where Does Locale Sit in Message Construction?

A localized message has three distinct layers:

1. **Sentence wording:** determined by the translated pattern, usually loaded from a **ResourceBundle**.
2. **Parameter position and type:** recorded in the pattern via placeholders such as **{0}**, **{1,number,integer}**, or **{2,date,short}**.
3. **How parameters are converted to strings:** handled by component formatters, using a locale and potentially a time zone, currency, or custom pattern.

Example pattern:

~~~text
Xin chào {0}, tổng tiền của bạn là {1,number,currency}.
~~~

Argument **0** can be a person's name, and argument **1** a monetary amount. Even though the pattern is in Vietnamese, if the currency formatter was created with **en-US**, the currency symbol and separators can still follow US conventions. **MessageFormat does not translate automatically**; it only substitutes parameters and invokes the appropriate formatters.

| Object | Role | What it does not do |
| --- | --- | --- |
| **ResourceBundle** | Looks up message patterns along the locale/candidate chain | Does not decide every custom formatter |
| **MessageFormat** | Parses patterns, manages placeholders, uses locale to create formatters | Does not automatically replace existing formatters when locale changes |
| **NumberFormat/DecimalFormat** | Converts numbers to strings | Does not validate monetary values or business exchange rates |
| **DateFormat/SimpleDateFormat** | Converts Date to date/time strings | Does not automatically know the user's time zone |
| **ChoiceFormat** | Selects a branch from numeric thresholds | Does not provide complete plural grammar for all languages |

Locale is a language/region context, **not identical** to ZoneId, Currency code, charset, or the application's existing translations.

## 2. Which Constructor Accepts Locale?

Two common ways to instantiate:

~~~java
MessageFormat implicit = new MessageFormat(pattern);
MessageFormat explicit = new MessageFormat(pattern, locale);
~~~

This is illustrative code inside a method, importing **java.text.MessageFormat** with variables **pattern** and **locale**. The first constructor uses the JVM's **default Locale belonging to Locale.Category.FORMAT**. The second constructor accepts an explicit locale.

Java has no **MessageFormat.getInstance(locale)** factory like NumberFormat does. Using the explicit constructor is the clear way for multi-user applications to avoid depending on the server's locale.

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class BasicMessageLocale {
    public static void main(String[] args) {
        MessageFormat us = new MessageFormat(
                "Value: {0,number,0.00}", Locale.US);
        MessageFormat de = new MessageFormat(
                "Value: {0,number,0.00}", Locale.GERMANY);

        System.out.println(us.format(new Object[] {1.5}));
        System.out.println(de.format(new Object[] {1.5}));
    }
}
~~~

Save **BasicMessageLocale.java** and run:

~~~bash
javac BasicMessageLocale.java
java BasicMessageLocale
~~~

Stdout:

~~~text
Value: 1.50
Value: 1,50
~~~

Both inputs are **double 1.5**. Only the decimal separator differs because the two child **DecimalFormat** instances were created with different locales. The pattern text **Value:** itself does not change language because MessageFormat does not translate patterns.

## 3. How Patterns Determine Subformatters

Placeholder syntax generally takes three forms:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Argument indices start at 0 and point into the **Object[]** array. The format types supported by standard Java 17 MessageFormat are **number**, **date**, **time**, and **choice**.

| Placeholder | Subformatter |
| --- | --- |
| **{0,number}** | NumberFormat.getInstance(locale) |
| **{0,number,integer}** | NumberFormat.getIntegerInstance(locale) |
| **{0,number,percent}** | NumberFormat.getPercentInstance(locale) |
| **{0,number,currency}** | NumberFormat.getCurrencyInstance(locale) |
| **{0,number,0.00}** | DecimalFormat with DecimalFormatSymbols for locale |
| **{0,date}** | DateFormat.getDateInstance(DEFAULT, locale) |
| **{0,date,short}** | DateFormat.getDateInstance(SHORT, locale) |
| **{0,time,short}** | DateFormat.getTimeInstance(SHORT, locale) |
| **{0,date,dd/MM/yyyy}** | SimpleDateFormat with pattern and locale |
| **{0,choice,...}** | ChoiceFormat from threshold and branch string |
| **{0}** | No fixed formatter at pattern-parse time |

Formatters for typed elements like **{0,number,...}** are created when the constructor or **applyPattern(...)** parses the pattern. For untyped placeholders like **{0}**, at **format** execution time MessageFormat inspects the argument: a **Number** is formatted using the default NumberFormat of **getLocale()**; a **java.util.Date** is formatted with short date/time per locale; a **String** is inserted verbatim, while other objects may use **toString()**.

Thus **setLocale** can affect untyped placeholders without fixed formatters, but **does not modify** already-created DecimalFormat/DateFormat instances. Distinguish these two stages when debugging output.

## 4. setLocale Does Not Automatically Update Existing Component Formatters

The API provides:

~~~java
message.getLocale();
message.setLocale(newLocale);
message.applyPattern(pattern);
~~~

**getLocale()** returns the locale held by MessageFormat. **setLocale(...)** changes the context used for formatters created afterward and for untyped placeholders. **applyPattern(...)** re-parses the pattern, creating new formatters for typed placeholders based on the current locale.

If you do:

~~~java
MessageFormat message = new MessageFormat(
        "{0,number,0.00}", Locale.US);
message.setLocale(Locale.GERMANY);
~~~

the formatter created for the US remains intact. Even though **message.getLocale()** is now **de-DE**, the number may still use a period. This behavior is explicitly stated in the Java 17 API contract.

### 4.1. Complete Experiment with Exact Output

**File MessageFormatLocaleDemo.java**

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatLocaleDemo {
    private static final String PATTERN =
            "Value: {0,number,0.00}";

    public static void main(String[] args) {
        MessageFormat message =
                new MessageFormat(PATTERN, Locale.US);
        Object[] values = {1.5};

        System.out.println(
                "start=" + message.format(values));

        message.setLocale(Locale.GERMANY);
        System.out.println(
                "setLocale=" + message.format(values));

        message.applyPattern(PATTERN);
        System.out.println(
                "applyPattern=" + message.format(values));

        DecimalFormat us = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        message.setFormatByArgumentIndex(0, us);

        System.out.println(
                "custom=" + message.format(values));

        message.setLocale(Locale.US);
        System.out.println(
                "afterSetLocale=" + message.format(values));
    }
}
~~~

Save **MessageFormatLocaleDemo.java**, compile and run:

~~~bash
javac -encoding UTF-8 MessageFormatLocaleDemo.java
java MessageFormatLocaleDemo
~~~

Stdout:

~~~text
start=Value: 1.50
setLocale=Value: 1.50
applyPattern=Value: 1,50
custom=Value: 1.50
afterSetLocale=Value: 1.50
~~~

**Analysis:** The constructor creates a DecimalFormat for en-US; **setLocale(Locale.GERMANY)** does not alter the old formatter; **applyPattern** creates a new DecimalFormat for de-DE; **setFormatByArgumentIndex** attaches an explicit en-US formatter; changing MessageFormat's locale again does not overwrite that custom formatter.

This is the most important distinction between **the MessageFormat's locale** and **the locale/configuration of component formatters**.

## 5. Safe Ways to Change Message Language

For per-request systems, the clearest approach is to **create a new MessageFormat** using the translated pattern and resolved locale:

~~~java
String localizedPattern = bundle.getString("order.total");

MessageFormat formatter = new MessageFormat(
        localizedPattern, selectedLocale);

String result = formatter.format(
        new Object[] {amount});
~~~

This snippet is illustrative, requiring **bundle**, **selectedLocale**, **amount**, and appropriate imports. Each instantiation initializes child formatters consistently for the chosen locale.

If reusing an instance on a sequential single thread, you can do:

~~~java
message.setLocale(newLocale);
message.applyPattern(newPattern);
~~~

However, **applyPattern** recreates child formatters from the pattern; prior customizations via **setFormat...** must be re-evaluated and re-attached. In particular, **never do this on a MessageFormat shared across concurrent requests**, because setters and legacy formatters are mutable.

Also never use **Locale.setDefault** to switch languages for a single request. That is JVM-wide state and can cause other requests to receive the wrong formatting.

## 6. Attaching Custom Formatters with setFormatByArgumentIndex

Key methods:

| API | How it identifies placeholders |
| --- | --- |
| **setFormat(int index, Format)** | Element order in the pattern sentence, left to right |
| **setFormatByArgumentIndex(int argumentIndex, Format)** | Argument index; applies to every position using that index |
| **setFormats(Format[])** | In order of format element appearance |
| **setFormatsByArgumentIndex(Format[])** | By argument index |
| **getFormats()** | Returns formatters in appearance order |
| **getFormatsByArgumentIndex()** | Returns formatters by argument index; for repeated indices, the last occurrence's formatter is reflected in that slot |

Translations may reorder parameters. For example:

~~~text
Pattern A: "{0} bought {1,number,integer} items."
Pattern B: "{1,number,integer} sản phẩm đã được {0} mua."
~~~

In both patterns, **argument 1** is the quantity, yet the position of the quantity element changed. **setFormatByArgumentIndex(1, formatter)** still targets the right argument; **setFormat(1, formatter)** can target the wrong element when a translation reorders the sentence.

### 6.1. Runnable Example

**File ArgumentIndexDemo.java**

~~~java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class ArgumentIndexDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Items={1,number,integer}; ratio={0,number,integer}",
                Locale.US);

        message.setFormatByArgumentIndex(
                0, NumberFormat.getPercentInstance(Locale.US));

        System.out.println(
                message.format(new Object[] {0.25, 4}));
    }
}
~~~

Run:

~~~bash
javac ArgumentIndexDemo.java
java ArgumentIndexDemo
~~~

Stdout:

~~~text
Items=4; ratio=25%
~~~

Even though **argument 0** sits in the second placeholder, the percentage formatter still attaches to it properly.

**Pitfall:** If the same argument appears multiple times with different styles—such as **{0,number,integer}** and **{0,number,0.00}**—then **setFormatByArgumentIndex(0, custom)** overwrites the formatter at **all** positions containing argument 0. When each occurrence needs distinct formatting, consider controlled **setFormat(elementIndex, ...)** calls or separate arguments for clarity.

## 7. NumberFormat, DecimalFormat, and Currency

For the placeholder **{0,number}**, MessageFormat creates a NumberFormat for the current locale when the pattern is applied. For **{0,number,0.00}**, it creates a DecimalFormat based on the pattern and the locale's DecimalFormatSymbols. DecimalFormat can have its own fraction digits, grouping, and rounding settings.

An explicit NumberFormat example:

~~~java
Locale locale = Locale.GERMANY;
MessageFormat message = new MessageFormat(
        "Amount: {0}", locale);
NumberFormat number =
        NumberFormat.getNumberInstance(locale);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
message.setFormatByArgumentIndex(0, number);
~~~

This illustrative snippet requires importing **MessageFormat**, **NumberFormat**, and **Locale**. When `format` is called with a number, the attached formatter controls its rendering.

### 7.1. Locale Does Not Determine Transaction Currency

**{0,number,currency}** selects a default currency from the locale. However, a USD order can perfectly well be displayed in a Vietnamese UI. For real money, the currency unit comes from transaction data:

~~~java
Locale displayLocale = Locale.forLanguageTag("vi-VN");
NumberFormat money =
        NumberFormat.getCurrencyInstance(displayLocale);
money.setCurrency(Currency.getInstance("USD"));

MessageFormat message = new MessageFormat(
        "Thành tiền: {0}", displayLocale);
message.setFormatByArgumentIndex(0, money);
~~~

Requires importing **Locale**, **Currency**, **NumberFormat**, and **MessageFormat**. **setCurrency** does not change exchange rates or monetary values; it only changes the displayed currency unit metadata. For exact monetary calculations, use **BigDecimal** and business rounding rules; formatting cannot replace those calculations.

### 7.2. Formatter Configuration Can Differ from getLocale()

After calling **setFormatByArgumentIndex(0, NumberFormat.getInstance(Locale.US))**, MessageFormat can still hold **Locale.GERMANY**. Because a custom formatter is an independent object, **getLocale() does not prove all subformatters share the same locale**. When output mixes separators or symbols, inspect manually attached formatters and their options.

## 8. DateFormat, SimpleDateFormat, and Time Zones

Java 17 MessageFormat uses **java.text.DateFormat** for **{0,date}**/**{0,time}**. For styles **short**, **medium**, **long**, or **full**, MessageFormat picks the corresponding DateFormat factory. For a pattern style like **dd/MM/yyyy**, it creates a **SimpleDateFormat** for the locale.

**DateFormat/SimpleDateFormat** belong to the legacy API and typically accept **java.util.Date**. Do not pass **LocalDate** or **Instant** directly into **{0,date,short}** expecting Java to convert types automatically.

An example controlling time zone:

~~~java
Locale locale = Locale.US;
MessageFormat message =
        new MessageFormat("Date: {0}", locale);

DateFormat date = DateFormat.getDateInstance(
        DateFormat.SHORT, locale);
date.setTimeZone(TimeZone.getTimeZone("UTC"));

message.setFormatByArgumentIndex(0, date);

String output = message.format(new Object[] {
        java.util.Date.from(
                java.time.Instant.parse("2026-10-28T00:00:00Z"))
});
~~~

This illustrative snippet requires importing **Locale**, **MessageFormat**, **DateFormat**, and **TimeZone** inside a method. **Locale** chooses date presentation; **TimeZone** determines how the instant maps to local date/time. Because date formatting can vary with JDK locale data, do not hardcode outputs across all JDK versions in tests without pinning the runtime.

Without a time zone set, DateFormat can depend on the server's default time zone. Two machines with the same locale can print different dates if an Instant crosses a midnight boundary. For servers and APIs, choose **ZoneId** or TimeZone from actual data, never inferring it from locale.

## 9. Combining java.time with MessageFormat

The newer **java.time** API uses **DateTimeFormatter**, which is immutable. However, DateTimeFormatter is not directly a subclass of **java.text.Format**, so you cannot simply cast it to DateFormat.

There are two clear strategies:

- **Pre-format** using DateTimeFormatter and pass the resulting String into an unformatted placeholder **{0}**.
- **Attach the adapter** returned by **DateTimeFormatter.toFormat()**, using **MessageFormat.setFormatByArgumentIndex(...)** with a suitable temporal object.

Complete example with stable output:

**File ModernTimeMessage.java**

~~~java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ModernTimeMessage {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        DateTimeFormatter date = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale);

        MessageFormat message = new MessageFormat(
                "Ngày giao hàng: {0}", locale);
        message.setFormatByArgumentIndex(
                0, date.toFormat());

        System.out.println(
                message.format(new Object[] {
                        LocalDate.of(2026, 10, 28)
                }));
    }
}
~~~

Save **ModernTimeMessage.java**, run:

~~~bash
javac -encoding UTF-8 ModernTimeMessage.java
java ModernTimeMessage
~~~

Stdout:

~~~text
Ngày giao hàng: 28/10/2026
~~~

**Explanation:** The **toFormat()** adapter wraps DateTimeFormatter into a Format attachable to MessageFormat. The locale lives on DateTimeFormatter and is set at creation, while the pattern **dd/MM/uuuu** defines the exact presentation. Calling **message.setLocale(Locale.US)** later does not automatically update this formatter adapter.

For an Instant that needs local time display, use DateTimeFormatter with an explicit ZoneId; a locale does not determine a time zone. If already pre-formatted into a string, MessageFormat merely inserts that string without re-converting it.

## 10. ChoiceFormat and Locale Limitations

**ChoiceFormat** selects a string based on a numeric value and intervals/thresholds defined in a pattern or arrays. It is useful for a few simple conditions, but **does not replace a full pluralization system** across multiple languages. MessageFormat's locale does not automatically translate ChoiceFormat branches.

Illustrative example:

~~~java
ChoiceFormat choice = new ChoiceFormat(
        new double[] {0, 1, 2},
        new String[] {
                "không có mục",
                "một mục",
                "{0,number,integer} mục"
        });

MessageFormat message = new MessageFormat(
        "Giỏ hàng: {0}", Locale.forLanguageTag("vi-VN"));
message.setFormatByArgumentIndex(0, choice);

System.out.println(
        message.format(new Object[] {3}));
~~~

Requires importing **ChoiceFormat**, **MessageFormat**, and **Locale**; this is a snippet inside a method. With argument 3, ChoiceFormat picks the last branch. That branch contains a nested placeholder, so MessageFormat formats the number using its own locale. Output meaning: **Giỏ hàng: 3 mục**.

**Note:** the words in the three branches are pre-written Vietnamese strings, not automatically generated translations. For English, Russian, Arabic, or other languages with different plural rules, appropriate translations and conditional mechanisms are required. Do not just change MessageFormat's locale while keeping a Vietnamese ChoiceFormat, because the branch text will not change.

If a pattern requires complex plurals, gender, grammatical cases, or nested conditions, consider a dedicated localization mechanism designed for the languages supported by the product.

## 11. Patterns and Single-Quote Rules

MessageFormat has special escaping syntax. A single quote in a pattern is a syntactic character used to quote literal spans; to display an actual single quote, you usually must write **two consecutive single quotes**.

~~~text
Unintended pattern: You're {0}
Proper pattern:     You''re {0}
~~~

The first snippet can change how placeholders are parsed. This is a very common error when translators or developers assemble patterns from natural text containing apostrophes. MessageFormat's escaping rules also differ from Java string escaping and **.properties** file escaping.

Curly braces **{** and **}** also participate in placeholder syntax; if they must appear as ordinary text, quote them properly. For complex patterns, run formatting tests with sample arguments for each language rather than merely checking that translation files exist.

**Do not treat a pattern from an untrusted source as an arbitrary string to format.** A pattern can trigger syntax errors or unintended format selection. Only use verified patterns with proper update and testing policies.

## 12. ResourceBundle Supplies Language, MessageFormat Formats Values

In a multilingual application, the typical flow is:

~~~text
User / profile / Accept-Language
              |
              v
     Select supported Locale
              |
              v
     ResourceBundle by Locale
              |
              v
     Retrieve translated pattern
              |
              v
  new MessageFormat(pattern, Locale)
              |
              v
   Attach specific subformatters
   (Currency, TimeZone, java.time)
              |
              v
      format(Object[] values)
~~~

Example classpath files:

**messages.properties**

~~~properties
notice=You have {0,number,integer} messages.
~~~

**messages_vi.properties**

~~~properties
notice=Bạn có {0,number,integer} tin nhắn.
~~~

Java snippet:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);

MessageFormat message = new MessageFormat(
        bundle.getString("notice"), locale);

System.out.println(
        message.format(new Object[] {3}));
~~~

Requires importing **Locale**, **ResourceBundle**, and **MessageFormat**. With the resources above on the classpath, stdout:

~~~text
Bạn có 3 tin nhắn.
~~~

Distinguish two fallback layers: **ResourceBundle selection** walks a candidate chain and may inspect the JVM default in certain cases when no matching bundle exists; meanwhile, **MessageFormat** formats parameters using its configured locale/subformatters. For completely deterministic output, the bundle fallback policy must also be controlled; merely passing a locale to MessageFormat does not handle that.

With named modules/JPMS and specialized resource packaging, test bundle lookup accordingly. ResourceBundle is used to locate text patterns, not to force an already-constructed subformatter to adopt a new locale.

## 13. Common Bugs When Using Subformatter Locales

| Error | Symptom | How to handle |
| --- | --- | --- |
| Using static **MessageFormat.format(pattern, args...)** | Result follows the JVM's default FORMAT locale | Use the constructor accepting a locale |
| Calling **setLocale** after creating **{0,number}** | Numbers still use the old locale | Create a new MessageFormat or call applyPattern at the right time |
| Attaching a NumberFormat from another locale | Separators inconsistent with the translated sentence | Create custom formatters with the resolved locale |
| Calling **setFormat(0, ...)** on reordered translations | Formatter lands on a different argument | Prefer setFormatByArgumentIndex when appropriate |
| Using **{0,date}** with **LocalDate** | Incompatible with legacy DateFormat | Use toFormat adapter or pre-format |
| Using DateFormat without specifying time zone | Dates/times differ between dev and server | Set time zone per business requirements |
| Using locale currency to interpret transactions | Displays wrong currency unit | Take Currency from payment data |
| Attaching a hardcoded Vietnamese ChoiceFormat to other locales | Mixed-language sentences | Translate branches or replace plural mechanism |
| Sharing mutable MessageFormat across threads | Race conditions or unstable language output | Create per-request instances or isolate properly |
| Assuming String.format and MessageFormat are identical | Patterns are parsed incorrectly | Choose the matching API and syntax |
| Not testing translations containing quotes | Disappearing placeholders, malformed patterns | Test patterns after translation |

**One key difference:** **String.format(Locale, ...) / Formatter** uses percent-sign syntax like **%.2f**, whereas **MessageFormat** uses brace placeholders like **{0,number,0.00}**. Do not move patterns between the two APIs without rewriting the syntax.

## 14. Testing Critical Behavior

Tests should cover:

1. The same number with **Locale.US** and **Locale.GERMANY** must use the decimal separator of the chosen locale.
2. **getLocale()** reflects the new locale after **setLocale**; previously created numeric formatters retain their old formatting.
3. Calling **applyPattern** after changing locale creates new formatters for the new locale.
4. **setFormatByArgumentIndex** applies to the right argument even if appearance order changes across translations.
5. For an argument repeated multiple times, verify understanding that setFormatByArgumentIndex overwrites all positions.
6. Custom formatters with a different locale or currency retain their own configuration.
7. DateFormat has an explicit time zone attached when deterministic time output is required.
8. LocalDate is formatted via DateTimeFormatter.toFormat or converted to an appropriate string before passing into MessageFormat.
9. ResourceBundle supplies the right pattern and missing-key/fallback cases are controlled.
10. Every translation with single quotes, curly braces, and placeholders parses and formats properly.
11. Tests run under different JVM defaults still yield identical output when all locales are passed explicitly.
12. JDK version and CLDR data are accounted for if snapshots require byte-for-byte matches on month names, currency symbols, or whitespace.

To simulate different JVM defaults, prefer **running tests in separate processes**. **Locale.setDefault** mutates JVM-wide state and can cause parallel tests to interfere with one another.

**Do not assert a single long date string or currency symbol across all JDKs** without pinning locale data; certain whitespace, symbols, and month names can change between JDK releases. With simple numeric patterns like the 0.00 example, stdout is well-defined and easy to compare.

## 15. Implementation Checklist

- Resolve the **supported Locale** before looking up translations and formatting messages.
- Read the pattern in the right language from prepared resources.
- Construct **new MessageFormat(pattern, locale)** rather than implicitly using the JVM default.
- Use component formatters matching the same locale, unless business rules require another setting.
- Explicitly set **Currency**, **TimeZone**, and rounding rules; do not infer them from locale.
- Understand that **setLocale** does not update already-created formatters.
- When using **applyPattern** to switch locales, inspect and re-attach custom formatters.
- Use **setFormatByArgumentIndex** when translations can reorder parameters; handle separately when one argument needs multiple formats.
- Use **DateTimeFormatter.toFormat()** or pre-format when inputs are java.time types.
- Validate MessageFormat syntax for all translations, especially single quotes and curly braces.
- Never share a mutable instance and mutate locale/pattern across concurrent requests.
- Test ResourceBundle fallback and output across locales/JDKs matching the product contract.

## 16. Key Takeaways

**MessageFormat's locale is only the context used when creating or selecting subformatters, not a switch that reconfigures all existing formatters.** Typed placeholders like **number/date/time** create formatters when the pattern is applied; calling **setLocale** afterward does not change them. Formatters explicitly attached via **setFormatByArgumentIndex** can also carry their own locale, time zone, and currency.

A controllable design is to fetch the translated pattern for the user's locale, construct a new MessageFormat with that exact locale, intentionally configure component formatters, and format typed parameters. This keeps messages consistent on Java 17+, across requests, and across dev, CI, and production.
