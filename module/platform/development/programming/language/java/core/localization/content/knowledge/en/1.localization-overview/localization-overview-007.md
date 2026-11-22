# Boundaries Between Data Processing, Resources, and UI in Java Localization

## 1. Why Separate These Three Responsibilities?

In an application supporting multiple languages and regions, **business data**, **localization resources**, and **display formatting** change for different reasons. Separating them ensures an order remains the exact same order when a user switches from Vietnamese to English, changes date formatting, or uses another device.

- **Data processing (domain/application):** validates business rules, computes, stores, and exchanges values with stable meaning. For example: order ID, monetary amount with currency unit, order placement instant, order status.
- **Localization resources:** provide messages, labels, translations, and sentence templates per language. For example: key `order.summary` has a Vietnamese version and an English version.
- **UI or presentation layer:** selects `Locale`, time zone, and formatters; retrieves the right message from resources; turns data into text the user sees. For example: the same amount 1,234.50 USD can be presented differently depending on the locale.

**Core principle:** changing locale must update presentation appropriately without changing business values. Some business logic has country-specific rules (taxes, allowed units, laws); those are **explicitly modeled business rules**, not automatic side effects of switching UI language.

## 2. Responsibility Boundaries

| Question | Primarily Responsible Layer | Data Representation to Use |
| --- | --- | --- |
| What is the order ID and total amount? | Domain/application | `String` ID, `BigDecimal`, and `Currency` |
| When did the event occur? | Domain/infrastructure | `Instant` or a time type matching business meaning |
| Which language displays “Order …” ? | Resource + presentation | Message key and `ResourceBundle` |
| How are decimal points, thousand grouping, and date/time written? | Presentation | `NumberFormat`, `DateTimeFormatter`, `Locale`, `ZoneId` |
| Which time zone does the reader view the instant in? | Presentation / user choice | `ZoneId` independent of `Locale` |
| Is ordering allowed in this currency? | Domain/application | Currency, market, and contract rules |

A typical display flow:

~~~text
Data source / API
        |
        v
Domain: Order(id, amount, currency, placedAt)
        |
        v
Application: validate and execute business logic
        |
        v
Presentation adapter: (Order, Locale, ZoneId)
        |                         |
        |                         +--> ResourceBundle: translations + message patterns
        +--> NumberFormat / DateTimeFormatter
        |
        v
UI or user-facing response
~~~

In the reverse direction, **UI input** may need locale-aware parsing (for example `1.234,50`), followed by validation and conversion into structured values before entering the domain. Never pass display strings directly into monetary calculations or business logic.

## 3. Business Data Must Preserve Its Meaning

Example with an order:

- Store **monetary amount** as `BigDecimal` and **currency unit** as `Currency` or an ISO 4217 code; do not store only `"$1,234.50"` or `"1.234,50"`.
- Store **actual timestamp** as `Instant` when business logic refers to an absolute event. At presentation time, combine with `ZoneId`; do not infer time zone solely from language.
- Store **status** as a stable code (for example `PENDING`, `PAID`); translations “Chờ xử lý”/“Pending” belong in UI resources. Never use translated text as a database key or business enum value.
- Data genuinely entered by users (personal names, addresses, descriptive text) is **data**, not automatically turned into translation keys. Only translate fields with an explicit design and translation source.

**Wrong example:** storing `total = "1.234,50 USD"` and splitting strings to add money; or using `status = "Đã thanh toán"` to drive state transitions. **Right example:** storing `amount = 1234.50`, `currency = USD`, `status = PAID`, then displaying according to the requested locale.

Note: `Locale` is not an exchange rate. Switching from `en-US` to `vi-VN` does not convert USD to VND. If the system needs **currency conversion**, that is a separate business operation with an exchange rate, rate source, effective time, and rounding rules.

## 4. Localization Resources Contain Wording, Not Business Logic

Java provides `ResourceBundle` to select resources by `Locale`. With properties-based resource bundles, files such as `messages_en.properties` and `messages_vi.properties` share **stable keys**, while values are translations:

~~~properties
# messages_en.properties
order.summary=Order {0}: {1}; placed at {2}
~~~

~~~properties
# messages_vi.properties
order.summary=Đơn hàng {0}: {1}; đặt lúc {2}
~~~

Here, `order.summary` is a **message identifier**, not source English text. Placeholders `{0}`, `{1}`, `{2}` receive order ID, formatted money, and formatted time respectively; translators can reorder words in the sentence without changing business rules.

Important rules:

1. Keep keys consistent across languages; check for missing or extra keys during development.
2. Provide context to translators: “Order” can be the noun “đơn hàng” or the verb “đặt hàng”.
3. Do not concatenate sentences from separate translated pieces like “You have ” + count + “ orders”; word order and grammar may vary. Use complete message patterns.
4. `MessageFormat` has special rules for single quotes and curly braces. In a pattern, to produce a literal single quote you usually write two consecutive quotes; do not assume templates behave like normal string concatenation.
5. `ResourceBundle` follows a locale resource lookup chain and may fall back to another matching bundle or default. A **missing key** can cause `MissingResourceException`; do not assume Java always prints the key name automatically.
6. With Java 17, `.properties` resource bundles support reading international content in UTF-8 (default behavior since Java 9). Save files with the right encoding; terminal display encoding is a separate concern.

Localization resources should not contain SQL statements, tax calculation rules, total formulas, or authorization decisions. If translated text contains HTML or user-generated data, the presentation layer must still escape/encode appropriately for the output target (HTML, JSON, etc.); translations are not inherently safe to inject raw into markup.

## 5. UI Combines Data, Resources, and Formatting

**`Locale`** expresses language/regional conventions; **`ZoneId`** specifies time zone; **`Currency`** represents monetary unit. These three concepts relate to user experience, yet do not substitute for one another.

Standalone runnable example with **Java 17+**. Place the three files below **in the same directory**.

**File `LocalizedOrderDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedOrderDemo {
    record Money(BigDecimal amount, Currency currency) {}
    record Order(String id, Money total, Instant placedAt) {}

    static String render(Order order, Locale locale, ZoneId zone) {
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);

        NumberFormat moneyFormat = NumberFormat.getCurrencyInstance(locale);
        Currency currency = order.total().currency();
        moneyFormat.setCurrency(currency);

        // setCurrency does not guarantee updating the number of decimal digits automatically.
        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            moneyFormat.setMinimumFractionDigits(digits);
            moneyFormat.setMaximumFractionDigits(digits);
        }
        String localizedAmount = moneyFormat.format(order.total().amount());

        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                        .withLocale(locale);
        String localizedTime =
                dateFormat.format(order.placedAt().atZone(zone));

        MessageFormat message =
                new MessageFormat(messages.getString("order.summary"), locale);
        return message.format(
                new Object[] {order.id(), localizedAmount, localizedTime});
    }

    public static void main(String[] args) {
        Order order = new Order(
                "A-17",
                new Money(
                        new BigDecimal("1234.50"),
                        Currency.getInstance("USD")),
                Instant.parse("2026-01-15T10:30:00Z"));

        ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("en-US -> " +
                render(order, Locale.US, displayZone));
        System.out.println("vi-VN -> " +
                render(order, Locale.forLanguageTag("vi-VN"), displayZone));
    }
}
~~~

**File `messages_en.properties`:**

~~~properties
order.summary=Order {0}: {1}; placed at {2}
~~~

**File `messages_vi.properties`:**

~~~properties
order.summary=Đơn hàng {0}: {1}; đặt lúc {2}
~~~

**Compile and run** from the directory containing the three files:

~~~bash
javac -encoding UTF-8 LocalizedOrderDemo.java
java LocalizedOrderDemo
~~~

The two output lines start with **`en-US -> Order A-17:`** and **`vi-VN -> Đơn hàng A-17:`** respectively. Both show the same order ID, the same **1,234.50 USD in value**, and the same instant `2026-01-15T10:30:00Z` converted to the `Asia/Ho_Chi_Minh` time zone. Number separators, currency symbol/code position, and date/time phrasing will differ by locale; exact strings can vary across JDK/CLDR versions, so do not assert the entire stdout verbatim across all environments.

In this code, the domain layer holds only `Order`, `Money`, and `Instant`. The `render` method is the **presentation boundary**: it receives locale/time zone choices, looks up the message, and formats money and time. `ResourceBundle` holds only wording. `MessageFormat` places parameters into the sentence; if plurals, grammatical gender, declension, or more complex layouts are needed, design a suitable localization solution instead of concatenating fixed strings.

## 6. Input and Output: Put Conversion at System Boundaries

An easy-to-control application structure is:

1. **Input adapter (UI/API):** receives locale and time zone from user profile or request; resolves to the set of supported locales. If numbers/dates are entered as localized text, parse them here and verify full-string consumption, valid format, and value bounds.
2. **Application/domain:** operates on normalized values. It does not need to know what language UI messages are in to calculate totals, check status, or save invoices.
3. **Output adapter/presenter:** receives structured results; builds labels and messages from bundles, formats times/numbers, and returns them to the UI.

For **machine-facing APIs**, prefer keeping structured data, such as:

~~~json
{
  "id": "A-17",
  "amount": "1234.50",
  "currency": "USD",
  "placedAt": "2026-01-15T10:30:00Z",
  "status": "PAID"
}
~~~

The UI may additionally receive presentation fields such as `displayAmount` or `displayStatus` when needed, but **do not replace canonical values** with translated strings. Another client can render with a different locale without altering the data.

Several distinctions to keep clear:

- **Locale is not language:** within English, `en-US` and `en-GB` have different conventions; sharing a language does not imply sharing a time zone or currency.
- **Locale is not time zone:** a user choosing Vietnamese in Europe may still want European time. Local calendar schedules (such as “9 a.m. every Monday”) require their own model like `LocalTime` + `ZoneId`, and cannot simply be replaced by an `Instant` without semantics.
- **Locale is not encoding:** UTF-8 preserves Unicode characters when storing/transmitting data; `Locale` governs display conventions. Never use encoding changes to “translate” text.
- **Sorting is not identity:** lists of personal names can use a locale-appropriate `Collator` for display. Technical identifiers, map keys, URL slugs, and business matching rules need their own stable criteria; do not default to UI-style text comparison.
- **Casing rules:** for language-independent technical codes, consider `Locale.ROOT` when normalizing casing. For natural user text, consider the proper locale (for instance, the letter `i` in Turkish).

## 7. Common Mistakes and Fixes

| Design Mistake | Consequence | Fix |
| --- | --- | --- |
| Domain returns `"Đã thanh toán"` directly | Changing language changes conditional values and contracts | Domain returns code `PAID`; presenter translates label |
| Storing `"1.234,50"` instead of a number | Wrong locale parsing, broken math | Parse at input boundary, store `BigDecimal` |
| Using locale to infer currency | USD gets labeled VND without conversion | Bind `Currency` to amount, convert only in business logic |
| Calling `Locale.getDefault()` everywhere | Output depends on server, tests become flaky | Pass locale explicitly to presenter/formatter |
| Using `String.format` and joining loose labels for every sentence | Grammar and word order do not translate cleanly | Use keys and complete message patterns |
| Ignoring missing resource keys or mismatched placeholders | Runtime errors or garbled messages | Check key parity, test each bundle |
| Formatting time without choosing a time zone | Users misread the time | Domain holds instant; presenter receives `ZoneId` |
| Formatting numbers to strings then calculating further | Loss of precision, rounding errors | Compute on canonical values; format once at display |

Do not hold mutable `NumberFormat` or `MessageFormat` instances as singletons used concurrently across threads without proper synchronization; create formatters per request or manage them per thread. Conversely, `DateTimeFormatter` is immutable and thread-safe, so it can be reused when configured properly.

## 8. Testing the Boundaries

Switching locales is a useful architectural test: **the same input data** is rendered in at least two locales; only presentation elements are allowed to change.

Test across three layers:

- **Domain:** calculations and statuses stay accurate under environments with different default locales. Test `Money` and `Order` by values, not by translated sentences.
- **Resources:** bundles have complete keys; `MessageFormat` patterns parse cleanly and use the right placeholder counts; accented characters appear properly; fallback is intentional and tested.
- **Presentation:** Vietnamese/English locales produce matching phrasing and formats; `Currency` and `Instant` stay unchanged; time zone shifts displayed time without altering the source instant. For numbers, dates, and currency names, test structural/key properties or tightly pin the locale provider version rather than snapshotting entire CLDR strings across all JDKs.

You can add edge cases: unsupported locales, missing resource keys, negative values, currencies with 0 or 3 fractional digits, instants near daylight saving transitions, accented text and combining Unicode characters, and inputs with wrong separators. For user-entered numbers and dates, also test cases where a parser accepts a prefix and ignores trailing characters: that is not valid input if business rules require a full match.

## 9. Applying This in Your Project

When adding a screen or endpoint with multilingual content, cross-check:

1. Do stored, computed, and cross-layer data remain accurate if the user switches languages?
2. Are keys and translations kept in unified resources, with context for translators and clear fallbacks?
3. Which layer decides `Locale`, `ZoneId`, and formatting rules? Are those decisions passed explicitly to the rendering point?
4. Is translated text ever used to compare statuses, perform calculations, key data, or infer currency?
5. When adding a new locale, are most changes concentrated in resources and presenters rather than modifying business logic?

A design succeeds when you can keep **orders and business rules** intact, add a new language bundle, and adjust the presentation layer without rewriting data processing.
