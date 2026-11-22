# Organizing Message Lookup and Formatting Services in Java Applications

A multilingual Java application must solve two related yet distinct problems: **retrieving localized messages by language** and **formatting values by regional convention**. For example, an order screen needs to display sentences in Vietnamese or English, while monetary amounts must preserve the transaction's `Currency`, scheduled dates must be rendered in the recipient's time zone, and decimal separators must honor the viewer's formatting preference.

If every controller looks up **ResourceBundle** on its own, concatenates sentences with `+`, and calls **NumberFormat**, **SimpleDateFormat**, or **DateTimeFormatter** directly, the application easily ends up with duplicated code, missing keys, mixed languages, wrong dates/times, and thread-safety bugs from sharing mutable formatters across requests. A resilient design separates **LocaleResolver**, **MessageService**, **FormattingService**, and a **Presenter/Composer** to coordinate the output.

This lesson covers the responsibilities, Java 17+ APIs, translation file structure, interface contracts, runnable examples, fallbacks, caching, thread safety, testing, and common pitfalls when building a localization architecture.

## 1. How Do Message Translation and Formatting Differ?

Suppose an order has:

- **Customer name:** Lan.
- **Order ID:** DH-2026-07.
- **Amount:** BigDecimal("1234.50").
- **Currency:** EUR.
- **Order timestamp:** Instant.parse("2026-10-28T02:30:00Z").
- **UI language:** vi-VN.
- **Formatting locale:** vi-VN.
- **ZoneId:** Asia/Ho_Chi_Minh.

The application may need to build a sentence along the lines of: "Chào Lan, đơn DH-2026-07 có tổng ... vào ngày ...".

| Component | Decision | Related APIs |
| --- | --- | --- |
| **Sentence language** | Greetings, word order, and punctuation | ResourceBundle, MessageFormat |
| **Monetary amount** | Grouping separator, decimal separator, currency symbol and placement | NumberFormat, Currency |
| **Date** | Day/month/year by language and region | DateTimeFormatter, Locale |
| **Time zone** | Which local date an Instant falls on | Instant, ZoneId |
| **Product policy** | Supported UI locales, fallbacks, currency decimal digits | LocaleResolver, configuration, and domain |

**Principle:** store business data in typed form; format only at the boundary where data reaches the viewer. The string `"1.234,50 €"` is a presentation, not a substitute for `BigDecimal` and `Currency`.

### 1.1. Separating `uiLocale` and `formatLocale`

The UI language and the formatting region can differ. A user may prefer an English UI while viewing dates and numbers in Vietnamese conventions. Therefore, name **uiLocale** and **formatLocale** explicitly instead of cramming every preference into a single locale variable.

Likewise, **ZoneId** must not be inferred from `Locale`. A user who selects Vietnamese may live in Berlin; an amount paid in EUR does not automatically convert to VND when displayed under `vi-VN`.

## 2. Architecture Overview

~~~text
Controller / API / Notification use case
                 |
                 v
            LocaleResolver
          /       |       \
         v        v        v
    uiLocale  formatLocale  ZoneId
         |        |
         v        v
 MessageService  FormattingService
         |        |
         v        v
  ResourceBundle  NumberFormat
   MessageFormat  DateTimeFormatter
          \       /
           \     /
            v   v
       Presenter/Composer
              |
              v
       UI / Email / PDF
~~~

Responsibilities should be separated as follows:

1. **LocaleResolver:** selects a UI language officially supported by the application and applies fallback rules.
2. **MessageService:** retrieves text templates by key/locale and fills in arguments.
3. **FormattingService:** formats numbers, currency, percentages, dates, and times from typed data.
4. **Presenter/Composer:** combines formatted value strings with translated message templates without performing business logic.
5. **Domain:** holds `BigDecimal`, `Currency`, `LocalDate`, `Instant`, order IDs, statuses, and calculations.
6. **Observability and tests:** detects missing keys, unexpected fallbacks, malformed patterns, and JDK/CLDR differences.

A large framework is not required. A small application may use just a few classes, provided **responsibility boundaries are clear** so each screen does not reinvent internationalization.

## 3. Designing `MessageService`

Basic contract:

~~~java
interface MessageService {
    String render(
            Locale locale, String key, Object... values);
}
~~~

This is an illustrative signature requiring `import java.util.Locale` when placed in a Java file. **Locale** is always passed explicitly, **key** is a stable technical identifier, and **values** are the arguments inserted into the message pattern.

Good keys:

~~~text
order.title
order.summary
order.status.pending
validation.date.invalid
payment.refund.confirmed
~~~

They describe **content semantics** rather than using a full English sentence as the key. That lets translators adjust wording without changing keys in Java code.

Do not allow users to supply arbitrary keys to read internal resources. Keys are normally chosen by application code per use case; if an API must accept a key, enforce an allowlist and appropriate authorization.

### 3.1. Letting Translators Reorder Clauses

An English sentence and a Vietnamese sentence do not have to share the same word order. Numbered placeholders allow:

~~~text
English: Hello {0}, order {1} totals {2} on {3}.
Vietnamese: Chào {0}, đơn {1} có tổng {2} vào ngày {3}.
~~~

Translators can reorder **{0}, {1}, {2}, {3}** when grammar requires it. Conversely, fixed concatenation like **prefix + name + amount + suffix** easily produces awkward sentences, wrong prepositions, or broken punctuation.

**Message patterns must not hardcode user data or fixed amounts.** Data must flow through arguments, never be baked into translation files.

## 4. `ResourceBundle` and Translation Structure

`ResourceBundle` looks up resources based on a **base name** and `Locale`. A project can be laid out as:

~~~text
src/main/java/LocalizedServicesDemo.java
src/main/resources/messages_en.properties
src/main/resources/messages_vi.properties
~~~

For examples run directly with `javac`/`java`, place the `.properties` files next to the Java/class files so the default classpath finds them.

**File `messages_en.properties`**

~~~properties
order.title=Order details
order.summary=Hello {0}, order {1} totals {2} on {3}.
order.status.pending=Payment pending
~~~

**File `messages_vi.properties`**

~~~properties
order.title=Chi tiết đơn hàng
order.summary=Chào {0}, đơn {1} có tổng {2} vào ngày {3}.
order.status.pending=Đang chờ thanh toán
~~~

These files are **owned by the application**, not generated by the JDK. Java 17 supports UTF-8 for `ResourceBundle` properties with defined encoding compatibility rules; save and validate translations in UTF-8 to preserve Vietnamese diacritics.

Usage example:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);
String heading = bundle.getString("order.title");
~~~

This snippet requires importing `ResourceBundle` and `Locale` and having a `locale` variable. Do not pass **messages_vi.properties** as the base name; Java resolves candidates automatically from the base name **messages** according to the locale.

### 4.1. Fallbacks Can Cause Mixed-Language Translations

If a request asks for `fr-CA` but the project has no French translation, bundle lookup may fall back to the base resource or default `Locale` depending on configuration. That does not mean the app genuinely supports `fr-CA`.

If the Vietnamese translation is missing a key that exists in the base bundle, the application may display a sentence in another language. Therefore distinguish:

- **Missing bundle:** no matching resource source can be found.
- **Missing key:** the bundle exists, but the key is absent across the inheritance chain.
- **Partial translation:** some keys are still falling back.
- **Invalid pattern:** the key exists, but its `MessageFormat` syntax is broken.
- **Unsupported UI locale:** the product has not committed to translating the requested language.

During development and CI, catch these issues before release. In production, when falling back to keep the UI usable, follow a documented policy and emit metrics.

## 5. `MessageFormat` and Placeholders

**java.text.MessageFormat** handles numbered placeholders:

~~~java
String template =
        "Hello {0}, order {1} totals {2} on {3}.";
MessageFormat format =
        new MessageFormat(template, Locale.US);

String sentence = format.format(new Object[] {
        "Lan", "DH-2026-07",
        "EUR 1,234.50", "October 28, 2026"
});
~~~

This snippet lives inside a method and requires importing `MessageFormat` and `Locale`. The money/date arguments here have already been formatted into `String`s. This lets `uiLocale` and `formatLocale` vary independently.

### 5.1. Single-Quote Syntax

`MessageFormat` has special quoting rules. To print a literal single quote in a pattern, you usually need **two consecutive single quotes**. If a translator inadvertently alters them, placeholders may not be processed as expected.

**File `MessageFormatQuoteDemo.java`**

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatQuoteDemo {
    public static void main(String[] args) {
        MessageFormat fmt = new MessageFormat(
                "User {0}: it''s ready; value {1,number,integer}",
                Locale.US);

        System.out.println(fmt.format(
                new Object[] {"Lan", 42}));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MessageFormatQuoteDemo.java
java MessageFormatQuoteDemo
~~~

Stdout:

~~~text
User Lan: it's ready; value 42
~~~

Curly braces also have special syntax. If you must print a literal **{** or **}**, quote it according to `MessageFormat` rules and test it. Do not rely on a simple regex to validate every pattern completely, because patterns can contain quotes and nested subformats.

### 5.2. Built-in Number/Date Subformats and `java.time`

`MessageFormat` supports built-in subformats such as **{0,number}** or **{0,date}** backed by `java.text` APIs. However, **LocalDate**, **LocalTime**, and **Instant** from `java.time` are not automatically handled like `java.util.Date` in all cases.

In Java 17+, a clean design is:

1. `FormattingService` formats `LocalDate` using `DateTimeFormatter`.
2. `FormattingService` formats `BigDecimal`/`Currency` using `NumberFormat`.
3. `MessageService` accepts the already-formatted strings and inserts them per message syntax.

If the system needs typed arguments with formatting embedded directly inside messages, provide an explicit adapter or a dedicated i18n library. **Do not treat core Java `MessageFormat` as a full CLDR pluralization/gender engine.**

## 6. `FormattingService`: Numbers, Money, and Dates/Times

Contract:

~~~java
interface FormattingService {
    String money(
            BigDecimal amount, Currency currency, Locale locale);
    String date(
            LocalDate date, Locale locale);
}
~~~

This is an illustrative signature requiring imports for `BigDecimal`, `Currency`, `Locale`, and `LocalDate`.

**money** must accept **Currency** from the transaction, never inferring `USD` from `Locale.US` or `VND` from `vi-VN`. **date** should take `LocalDate` for a pure calendar date. A separate method for `Instant` needs an additional `ZoneId` because the same instant can fall on different calendar dates in two time zones.

Money is typed data, not a translation string:

~~~java
record Money(BigDecimal amount, Currency currency) {}
~~~

This is a valid Java 17 record when placed in a file with imports. `Currency` only states the currency unit; `NumberFormat` does not perform exchange-rate conversion. Rounding/tax rules should also never be hidden inside `MessageService`.

### 6.1. `NumberFormat` Is Mutable

**NumberFormat.getCurrencyInstance(locale)** creates a formatter for a locale. You can then call **setCurrency(currency)** to choose the actual currency unit. However, **NumberFormat is mutable**, so never share a singleton and mutate `Currency` or fraction digits across requests without isolation.

By contrast, **DateTimeFormatter** is immutable and thread-safe once configured, so it can be reused or cached by locale/format style.

## 7. Complete Integrated Java 17+ Example

The example consists of three files: **LocalizedServicesDemo.java**, **messages_en.properties**, and **messages_vi.properties** as defined in Section 4. This is pure core Java with no framework required.

**File `LocalizedServicesDemo.java`**

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.Set;

public class LocalizedServicesDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private static final Set<Locale> SUPPORTED =
            Set.of(VI, Locale.US);

    record RequestContext(
            Locale uiLocale,
            Locale formatLocale,
            ZoneId zoneId,
            Currency currency) {}

    interface MessageService {
        String render(
                Locale locale, String key, Object... arguments);
    }

    static final class BundleMessageService
            implements MessageService {

        @Override
        public String render(
                Locale locale, String key, Object... arguments) {

            ResourceBundle.Control control =
                    ResourceBundle.Control
                            .getNoFallbackControl(
                                    ResourceBundle.Control
                                            .FORMAT_PROPERTIES);

            ResourceBundle bundle =
                    ResourceBundle.getBundle(
                            "messages", locale, control);

            MessageFormat formatter =
                    new MessageFormat(
                            bundle.getString(key), locale);

            return formatter.format(arguments);
        }
    }

    interface FormattingService {
        String money(
                BigDecimal amount, Currency currency, Locale locale);
        String date(LocalDate day, Locale locale);
    }

    static final class JdkFormattingService
            implements FormattingService {

        @Override
        public String money(
                BigDecimal amount, Currency currency, Locale locale) {

            NumberFormat fmt =
                    NumberFormat.getCurrencyInstance(locale);
            fmt.setCurrency(currency);

            int digits = currency.getDefaultFractionDigits();
            if (digits >= 0) {
                fmt.setMinimumFractionDigits(digits);
                fmt.setMaximumFractionDigits(digits);
            }

            return fmt.format(amount);
        }

        @Override
        public String date(LocalDate day, Locale locale) {
            DateTimeFormatter fmt =
                    DateTimeFormatter
                            .ofLocalizedDate(FormatStyle.LONG)
                            .withLocale(locale);
            return fmt.format(day);
        }
    }

    private static Locale chooseUiLocale(Locale requested) {
        if (SUPPORTED.contains(requested)) {
            return requested;
        }
        if ("vi".equals(requested.getLanguage())) {
            return VI;
        }
        return Locale.US;
    }

    public static void main(String[] args) {
        Locale ui = chooseUiLocale(
                Locale.forLanguageTag("vi-VN"));

        RequestContext context = new RequestContext(
                ui,
                ui,
                ZoneId.of("Asia/Ho_Chi_Minh"),
                Currency.getInstance("EUR"));

        MessageService messages =
                new BundleMessageService();
        FormattingService formats =
                new JdkFormattingService();

        BigDecimal amount = new BigDecimal("1234.50");
        Instant created =
                Instant.parse("2026-10-28T02:30:00Z");

        LocalDate localDate =
                created.atZone(context.zoneId()).toLocalDate();

        String amountText = formats.money(
                amount, context.currency(),
                context.formatLocale());

        String dateText = formats.date(
                localDate, context.formatLocale());

        System.out.println(messages.render(
                context.uiLocale(), "order.title"));

        System.out.println(messages.render(
                context.uiLocale(),
                "order.summary",
                "Lan",
                "DH-2026-07",
                amountText,
                dateText));
    }
}
~~~

In the directory containing the files, compile and run:

~~~bash
javac -encoding UTF-8 LocalizedServicesDemo.java
java LocalizedServicesDemo
~~~

The first line of stdout is exact because it comes directly from `messages_vi.properties`:

~~~text
Chi tiết đơn hàng
~~~

The second line contains the Vietnamese message with **Lan**, order ID **DH-2026-07**, the EUR amount, and the local date 28/10/2026 formatted under `vi-VN`. Do not hard-pin the entire second line of stdout across all JDK 17+ versions, because CLDR/provider data may differ in date wording, grouping separators, currency symbols, and Unicode spaces.

### 7.1. What Is Right About This Structure

- **SUPPORTED** is the set of locales the product publishes, not raw `Locale.getAvailableLocales()`.
- **RequestContext** is an immutable record holding `uiLocale`, `formatLocale`, `ZoneId`, and `Currency`.
- **BundleMessageService** handles resource lookup and `MessageFormat`.
- **JdkFormattingService** only formats typed data.
- **chooseUiLocale** illustrates application-level fallback without mutating the JVM's default `Locale`.
- **NumberFormat** is created fresh per call, preventing configuration leaks across requests.
- **DateTimeFormatter** is constructed with an explicit locale.
- **Instant** is converted using `ZoneId` before extracting `LocalDate`.
- Formatted value strings are passed into messages via placeholders.
- `ResourceBundle.Control` specifies not falling back to the JVM's default locale during lookup.

### 7.2. Understanding `getNoFallbackControl` Properly

**ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)** prevents **falling back to the JVM's default locale** during resource resolution. It does **not** forbid parent language candidates or the **root bundle**. If a request asks for `vi-VN` and only `messages_vi.properties` exists, the `vi` language resource is still found.

To enforce exact region translations or detect untranslated keys, add dedicated coverage checks; do not confuse "no fallback" with "never using any other candidate locale". Furthermore, `ResourceBundle.Control` support depends on module/runtime setup; this example targets a Java 17 application running on the classpath.

## 8. How Should Presenter/Composer Coordinate?

A presenter uses `MessageService` and `FormattingService`:

~~~text
Order domain:
    amount=1234.50, currency=EUR, createdAt=Instant

LocaleResolver:
    uiLocale=vi-VN, formatLocale=vi-VN, zone=Asia/Ho_Chi_Minh

FormattingService:
    money(...) -> money text in vi-VN
    date(...)  -> date text in vi-VN

MessageService:
    order.summary + 4 arguments -> complete sentence

UI:
    Render sentence with channel-appropriate font, direction, and escaping.
~~~

The presenter must not change `Currency`, compute tax, pick exchange rates, or write translated messages back as the primary data source. If sending an email, the recipient may have a different `Locale` from the operator triggering the action; the composer should receive **the recipient's context**.

For machine-facing APIs, it is usually better to return JSON containing `amount`, `currency`, `Instant`, and a separate message key/status, rather than returning only a localized sentence that the client would have to parse back.

## 9. Locale Selection and `supportedLocales`

**Locale.getAvailableLocales()** is a list published by the JDK; it **does not prove the application has translations**. An application may only support `vi-VN` and `en-US` even though the JVM ships formatting data for many more locales.

Sources for determining `uiLocale` can include:

- User profile settings.
- Organization configuration.
- Client language preferences.
- A product-defined default fallback.

Never call `Locale.setDefault` per request: that is JVM-wide state and can affect other threads.

### 9.1. `Locale.LanguageRange` and `Locale.lookup`

If the application accepts a header like:

~~~text
vi-VN, en-US;q=0.8
~~~

Java supports negotiation against the application's supported list:

**File `LocaleSelectionDemo.java`**

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleSelectionDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.US);

        List<Locale.LanguageRange> preferred =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8");

        Locale chosen =
                Locale.lookup(preferred, supported);

        if (chosen == null) {
            chosen = Locale.US;
        }

        System.out.println(chosen.toLanguageTag());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocaleSelectionDemo.java
java LocaleSelectionDemo
~~~

Exact stdout:

~~~text
vi-VN
~~~

**Locale.lookup** can return `null`, so a fallback is mandatory. Untrusted headers must be size-limited and parse errors caught. The chosen locale comes from the **supported** list; do not expand to every JDK locale merely because it appears in `getAvailableLocales()`.

### 9.2. Different Locale-Related Fields in a Request

| Attribute | Purpose |
| --- | --- |
| requestedLocale | Requested by user/client |
| uiLocale | Translation language available in the product |
| formatLocale | Number/date rules for display |
| zoneId | Time zone of the instant/viewer |
| currency | Business currency unit |
| userId / tenantId | Identifies context, permissions, and configuration |

Do not hardcode `Locale.US` when the user requests `vi-VN` and translations exist. Conversely, if a `formatLocale` has not been tested, the product must define an explicit fallback rather than silently mixing unpredictable conventions.

## 10. Fallbacks and Missing Keys Are Operational Concerns

Possible failure modes:

1. **Unsupported locale:** apply the approved fallback.
2. **Missing bundle:** `ResourceBundle` throws `MissingResourceException` when no matching candidate exists.
3. **Missing key:** `getString` can throw `MissingResourceException`.
4. **Key exists only in root bundle:** strings from the default language leak into another language's screen.
5. **Broken pattern:** `MessageFormat` can throw `IllegalArgumentException`.
6. **Missing placeholder:** sentences may show literal text or format differently than the translator intended.
7. **Out-of-context translation:** the key exists, but the text does not fit the screen.

**In CI**, verify keys across all bundles and render critical templates. **In production**, if falling back to keep the UI working, log the key/locale and increment metrics per policy—never return stack traces or secret strings directly.

Do not catch a broad `Exception` and return the key as a "success"; that can mask code or pattern bugs. Choosing a fallback message should be an explicit policy, not turning every error into user content.

## 11. Validating Placeholders Across Translations

When a key takes four parameters, translators may change their order while preserving full meaning. For example:

~~~text
order.summary: {0}=name, {1}=orderId,
               {2}=formattedMoney, {3}=formattedDate
~~~

QA should catch:

- Missing keys.
- Empty patterns.
- Unsupplied argument indices like **{9}**.
- Unescaped single quotes.
- Malformed curly braces.
- Format types incompatible with the supplied value.
- Translations hardcoding currency symbols or dates.
- Buttons and labels missing accessibility text.

Do not use a naive regex like **\\{[0-9]+\\}** to declare every `MessageFormat` pattern valid. `MessageFormat` has quoting rules and subformats; actually parse and test critical resources.

### 11.1. Pluralization and Inflection

Some languages have complex singular/plural rules or word forms based on gender and context. Core Java `MessageFormat` has a `choice` option, **but it is not a complete solution for the plural/gender rules of all CLDR locales**. Major international products may need a dedicated i18n library along with resource compilation/linting rules.

Do not append **"s"** in code for English and treat that as a multilingual mechanism. Do not hardcode `"{0} items"` when translations must inflect words based on count.

## 12. Caching and Thread Safety

| Component | Characteristic | Recommendation |
| --- | --- | --- |
| `ResourceBundle` | JDK caches bundles | Use default cache; design reload policy if hot-updating |
| `MessageFormat` | Mutable | Create new or clone/isolate cleanly |
| `NumberFormat` | Mutable | Create per operation/request or synchronize properly |
| `DateTimeFormatter` | Immutable and thread-safe | Safe to cache by locale/pattern |
| Formatted message with arguments | Contains user-specific data | Do not cache globally by key alone |
| Localizer context | Recipient-dependent | Use immutable objects or request scope |

**Anti-pattern:**

~~~java
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance();

void changeCurrency(Currency currency) {
    SHARED.setCurrency(currency);
}
~~~

This illustrates a bug, not a standalone program. If two requests with different currencies or locales share `SHARED`, the mutable formatter can produce mixed-configuration output. Likewise, never share one `MessageFormat` and call `setFormat`/`format` concurrently without synchronization.

**Cache keys must carry sufficient context.** Caching a formatted string by amount alone without `Currency` and `formatLocale` yields wrong results. Caching a personalized message containing a customer name by message key alone can leak another user's data.

`ResourceBundle` has built-in caching, so hot-reloading translations requires an explicit reload/versioning policy; never call `ResourceBundle.clearCache()` across the entire JVM arbitrarily without assessing impact.

## 13. Pure Dates, `Instant`, and `ZoneId`

A **`LocalDate`** has no time zone. An **`Instant`** is an absolute point in time. To display an `Instant`'s date in a region, convert first:

~~~java
Instant moment =
        Instant.parse("2026-10-28T02:30:00Z");

LocalDate inVietnam =
        moment.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDate();
~~~

This snippet requires importing `Instant`, `LocalDate`, and `ZoneId`. This step is separate from choosing the language of month names.

**`Locale` is not `ZoneId`.** A Vietnamese UI may be viewed from the US or Europe. A `FormattingService` method for an instant should accept `Instant`, `ZoneId`, and `Locale`, or a `ZonedDateTime` already converted to the target zone.

### 13.1. Method Design Direction

~~~java
String formatDate(LocalDate date, Locale locale);

String formatMoment(
        Instant instant, ZoneId zone, Locale locale);
~~~

These are illustrative signatures, not a full program. When formatting by locale, `DateTimeFormatter.ofLocalizedDate/DateTime` is generally preferable to hardcoding **dd/MM/yyyy** for all regions. For API/machine data, ISO formatters are better suited than localized strings lacking a strict parse contract.

## 14. Storing Data and Delivering Multi-Channel Notifications

An "order created" event may target web UI, email, push notifications, and PDFs. Each destination may use a different locale, time zone, and presentation policy.

**Model worth keeping:**

~~~text
Event type: ORDER_CREATED
Order ID: DH-2026-07
Amount: 1234.50
Currency: EUR
OccurredAt: 2026-10-28T02:30:00Z
Recipient: a user ID
~~~

At render time, the system resolves **the recipient's context**, selects the `ResourceBundle`/formatter, and builds the channel-specific content. Do not use the operator's locale when emailing another user who has their own preferences.

For technical logs, prefer recording **event codes and structured data** rather than translated sentences: translated copy changes across languages, is harder to search, and varies across software versions.

If the system must store an issued invoice for legal reconciliation, store an additional **rendered document snapshot**; that is an explicit audit requirement, not a reason to discard typed source data.

## 15. Security and Output-Channel Escaping

`MessageFormat` only builds strings; **it does not escape HTML, SQL, URLs, or shell commands**. If arguments contain user input, escape them or use channel-safe APIs:

- **HTML:** use auto-escaping templates or safe text insertion.
- **SQL:** use prepared statements, never concatenate translated strings into queries.
- **URL:** properly encode URL components.
- **HTML Email:** escape content and verify layout.
- **PDF:** use fonts supporting the script and RTL/LTR layout if needed.
- **Logs:** avoid sensitive data, and watch out for control/BiDi characters in names.

Project-managed translations may be trusted resources, yet **arguments do not automatically become trusted data** simply by being inserted via `MessageFormat`.

Never use translated labels as business IDs or authorization checks. A button translated from "Thanh toán" to "Pay" must still invoke the exact same immutable action ID, never inferring behavior from displayed text.

## 16. Testing by Component

**LocaleResolver:**

- Returns a supported locale when requested by the user.
- Has an explicit fallback for unsupported tags.
- Never mutates `Locale.setDefault` per request.
- Handles Unicode extensions, regions, and language ranges per policy.

**MessageService:**

- All required keys exist in all bundles.
- Patterns are valid and placeholders carry the right meanings.
- Single quotes and curly braces are handled properly.
- Fallbacks never accidentally pick up the JVM default `Locale`.
- The same key allows translators to change clause order.

**FormattingService:**

- The transaction's actual `Currency` is never altered.
- Number/date formatting varies according to `formatLocale`.
- Fraction digits and rounding follow business rules.
- `LocalDate` is never shifted to another day by an implicit time zone.
- `Instant` is converted with `ZoneId` when required.
- Mutable `NumberFormat` instances are never shared across threads.

**Presenter/Composer:**

- Picks the right key for the use case.
- Passes typed arguments in the expected order.
- Does not hardcode English/Vietnamese glue words in code.
- Does not feed translated strings back into business calculations.

## 17. Minimum Integration Test Suite

| Scenario | Assertion |
| --- | --- |
| `uiLocale=vi-VN` and `formatLocale=vi-VN` | Vietnamese sentence and regional number/date |
| `uiLocale=en-US` and `formatLocale=en-US` | English sentence and US number/date |
| `uiLocale=en-US` and `formatLocale=vi-VN` | Language and formatting are independent |
| `Currency=EUR` with Vietnamese locale | Does not convert EUR to VND |
| `Instant` in `Asia/Ho_Chi_Minh` and another `ZoneId` | Accurate local calendar dates |
| Key removed from one bundle | Error or fallback follows policy |
| Pattern containing single quotes | `MessageFormat` quotes properly |
| Pattern with four placeholders | No dropped or swapped parameters |
| 2 concurrent requests with different `Currency` | No `NumberFormat` configuration bleed |
| Different JDK/CLDR version | Detect meaningful output differences |
| Money containing NBSP/NNBSP | Preserves Unicode spacing when rendered |
| HTML/PDF/email with Vietnamese/RTL | Font, escaping, and direction are correct |
| `ResourceBundle` with only base bundle | Does not falsely advertise locale support |

**Separate two kinds of tests:** unit tests of internal logic using stub formatters to assert message structure, and integration tests using real formatters on the target JDK. Avoid pinning every single code point of localized output when you do not control CLDR/provider data.

## 18. Common Pitfalls

### Pitfall 1: Every controller calls `ResourceBundle` and `NumberFormat` directly

Produces inconsistent fallback logic, mixed-language messages, and inconsistent dates/times. Use a shared service layer.

### Pitfall 2: Using one `Locale` for language, currency, and time zone

`Locale` does not know an order's currency or a user's time zone. Those values need separate typed fields.

### Pitfall 3: Concatenating sentences with `+` and translating only prefixes/suffixes

Word order differs across languages; use `MessageFormat` placeholders so translators can arrange the sentence.

### Pitfall 4: Misunderstanding `MessageFormat` single quotes

Literal apostrophes must be properly quoted. Do not use string replacement to patch broken translation patterns after the fact.

### Pitfall 5: Passing `LocalDate` directly to `MessageFormat` built-in date subformats

Core Java `MessageFormat` does not automatically convert all `java.time` types to `java.util.Date`. Use `DateTimeFormatter` or a tested adapter.

### Pitfall 6: Assuming `getBundle` returning a bundle means the locale is translated

`ResourceBundle` falls back; maintain an explicit `supportedLocales` list and run coverage checks.

### Pitfall 7: Sharing a `NumberFormat` singleton and calling `setCurrency` per request

Mutable formatters cause race conditions and configuration leaks. Create new instances or isolate them.

### Pitfall 8: Caching rendered messages by key without accounting for arguments

Can return content containing another user's name or order ID. Never cache personalized messages under a generic key.

### Pitfall 9: Calling `Locale.setDefault` when a user switches language

The JVM default affects other requests. Pass `Locale` explicitly.

### Pitfall 10: Treating formatting as currency business logic

`setCurrency` does not convert exchange rates; `NumberFormat` does not validate tax calculations. Keep monetary logic in the domain.

### Pitfall 11: Hardcoding `dd/MM/yyyy` for every locale

Some regions use different field orders and month names. Use locale-aware `DateTimeFormatter` or an approved pattern.

### Pitfall 12: Not checking translation keys and patterns in CI

Bugs surface only when a user switches to a less common language. Check bundle coverage and pattern rendering before release.

### Pitfall 13: Using translated messages as technical event codes

Language and wording change; event IDs should remain stable and separate from user-facing sentences.

### Pitfall 14: Forgetting HTML/RTL/font concerns

`ResourceBundle` supplies text, not guaranteed rendering across every channel. Text layout and escaping still require dedicated handling.

## 19. Implementation Roadmap

1. **Model the domain:** keep `amount`, `Currency`, `Instant`, `LocalDate`, and IDs strongly typed.
2. **Define `supportedLocales`:** publish only translations that have passed QA.
3. **Build `LocaleResolver`:** define language, region, and fallback rules.
4. **Create `ResourceBundle`s:** semantic keys, UTF-8 files, split by module where helpful.
5. **Build `MessageService`:** accepts `uiLocale`/key/args, manages missing keys and `MessageFormat`.
6. **Build `FormattingService`:** accepts `formatLocale` with typed data; uses the proper APIs.
7. **Build `Presenter/Composer`:** coordinates services without recomputing business logic.
8. **Ensure thread safety:** cache immutable formatters, avoid mutating shared `NumberFormat`/`MessageFormat`.
9. **Test:** unit tests, integration tests, and versioned snapshots for legally required outputs.
10. **Operate:** log/emit metrics for fallbacks, missing keys, malformed patterns, and JDK/CLDR updates.

Avoid over-engineering abstractions in a small project. The goal is **making parts independently testable and replaceable** without editing display logic across dozens of controllers.

## 20. Self-Review Questions

1. Why can't `Locale.getAvailableLocales()` serve as the app's supported-language menu?
2. Which parameters should `MessageService` accept to avoid relying on the JVM default?
3. Why does `FormattingService` need `Currency` even when `Locale` is provided?
4. How does `DateTimeFormatter` differ from `NumberFormat` in mutability and thread safety?
5. For the message `"It's ready"`, why does `MessageFormat` require doubled single quotes?
6. Why does `ResourceBundle` returning a value not prove a translation is complete?
7. When two users have different `formatLocale`s, what is the risk of a `NumberFormat` singleton?
8. What information does an `Instant` need to determine the recipient's `LocalDate`?
9. Why shouldn't rendered sentences be cached by message key alone?
10. If a message is output in HTML, does `MessageFormat` already prevent XSS?

**Suggested answers:** (1) The JDK supports more locales than the app has translated; (2) `Locale`, key, arguments; (3) `Currency` is business data; (4) `DateTimeFormatter` is immutable, `NumberFormat` is mutable; (5) `MessageFormat` quoting rules; (6) fallback resolution; (7) race conditions/configuration leakage; (8) `ZoneId`; (9) arguments carry user-specific data; (10) no, channel-specific escaping is required.

## 21. Completion Checklist

- [ ] Translated messages and formatted values are kept distinct.
- [ ] `LocaleResolver`, `MessageService`, `FormattingService`, and composer have clear responsibilities.
- [ ] Domain uses `BigDecimal`/`Currency`/`LocalDate`/`Instant` instead of formatted strings.
- [ ] Product `supportedLocales` is enforced rather than advertising all JDK locales.
- [ ] `Locale` is passed explicitly to `MessageFormat`/`NumberFormat`/`DateTimeFormatter`.
- [ ] `uiLocale`, `formatLocale`, `ZoneId`, and `Currency` have distinct meanings.
- [ ] `ResourceBundle` keys are stable, translations are UTF-8, and placeholders are consistent.
- [ ] Fallbacks and missing keys are detected and managed.
- [ ] `MessageFormat` single quotes and curly braces pass QA.
- [ ] Sentences are never concatenated around a single language's grammar.
- [ ] `MessageFormat` is not treated as a full pluralization engine.
- [ ] `Currency` is never altered by changing `Locale`.
- [ ] Rounding and fraction digits follow business policy.
- [ ] Mutable formatters are never shared and mutated concurrently.
- [ ] Messages containing user data are not cached under overly broad keys.
- [ ] `Locale.setDefault` is never called per request.
- [ ] Tests cover missing keys, invalid patterns, concurrency, and JDK/CLDR changes.
- [ ] Escaping and text direction are handled per render channel.
- [ ] Metrics track unexpected fallbacks and translation errors.

## 22. Summary

**Message lookup services** own language-specific sentence templates; **formatting services** own the representation of numbers, money, and dates/times; **LocaleResolver** resolves the viewer's context; and **Presenter/Composer** combines them into output. Java 17 provides **ResourceBundle**, **MessageFormat**, **NumberFormat**, **DateTimeFormatter**, **Locale**, and **ZoneId** to implement these responsibilities cleanly.

A sound design not only eliminates code duplication, it also prevents locale changes from altering monetary data, avoids wrong time zones, eliminates mutable-formatter races, catches missing translations, and enables independent testing. Keep domain data strongly typed, pass context explicitly, govern fallbacks by application policy, and format only at the presentation boundary.
