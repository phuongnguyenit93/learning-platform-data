# Separating Business Data from Display Text in Java Applications

## 1. Why Separate Business Data from Display Text?

In a localized (*localization*) application, **business data** describes the facts and rules of the system: monetary amounts, currency units, quantities, timestamps, order statuses, and product codes. **Display text** is the way that data is expressed to a user using a specific language, number format, date/time convention, and layout.

Suppose an order has a total amount of **1,234.50 EUR**. The exact same data can be displayed as:

```text
en-US: €1,234.50
de-DE: 1.234,50 €
```

The code `EUR`, the decimal value `1234.50`, and the order ID **do not change** when the user switches from English to German. Only the presentation layer uses `Locale` to determine the decimal separator, grouping separator, symbol position, and spacing.

If `"€1,234.50"` is stored as the monetary value, a `de-DE` parser might misinterpret or reject it; if display strings are compared as keys, changing the language can break lookups; if `"Đã thanh toán"` is stored instead of the status `PAID`, the system becomes dependent on the Vietnamese translation to operate.

**Principle:** *Domain data is the source of truth; display text is a reproducible result based on locale and context.* Do not invert the roles of these two layers.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between domain model, application/service, persistence/API, localization/presentation, and UI layout.
2. Represent **monetary amounts** with `BigDecimal` and `Currency`, **timestamps** with `Instant` or the appropriate temporal type, and **statuses** with enums/stable codes.
3. Use `NumberFormat`, `DateTimeFormatter`, `ResourceBundle`, and `MessageFormat` at the proper presentation boundary.
4. Design locale-aware input while storing data under a **locale-independent contract**.
5. Avoid common mistakes such as mixing translations into business rules, storing money as formatted strings, relying on the JVM-wide default locale, or comparing UI labels.
6. Distinguish **machine-readable codes for exchange** from **human-readable names/labels**, and separate locale, currency, and timezone into independent attributes.
7. Test switching languages without altering business values.

## 2. An Example: Same Order, Multiple Views

Consider the domain data:

```text
orderId    = "ORD-2026-042"
quantity   = 3
unitPrice  = 411.50
currency   = "EUR"
total      = 1234.50
paidAt     = 2026-10-28T01:30:00Z
status     = PAID
```

The **stored** part must carry these meanings without depending on the current language. Only given a specific display locale and timezone does the UI produce the strings:

| Domain field | User en-US, UTC | User de-DE, Europe/Berlin |
| --- | --- | --- |
| `status = PAID` | Paid | Bezahlt |
| `total = 1234.50 EUR` | €1,234.50 | 1.234,50 € |
| `paidAt = 2026-10-28T01:30:00Z` | Date/time in UTC | Date/time in Europe/Berlin |
| `orderId` | ORD-2026-042 | ORD-2026-042 |

The table describes **meaning**; specific translations, date/time strings, and currency strings depend on resources, the Java locale provider, and product configuration. Even when presentation changes, `total`, `currency`, `paidAt`, and `status` remain invariant.

If the user switches language, the system should recompute the **view model** or displayed strings, rather than modifying the original record in the database.

## 3. Layers of Responsibility

| Layer | Owns | Should not own |
| --- | --- | --- |
| **Domain model** | Business values and rules: money, tax, status, quantity, timestamps | Text like `"Đã thanh toán"`, grouping separators, month names, UI buttons |
| **Application/service** | Use cases, calculations, domain validation, transactions, access control | Mixing translated labels into business logic |
| **Persistence/API** | Schema, IDs, currency codes, decimals, instants, enums/codes, exchange contracts | Locale-dependent presentation strings unless explicitly defined as data |
| **Localization/presenter** | `Locale`, `ResourceBundle`, number/date formatters, messages and placeholders | Deciding the actual amount, actual status, or business rounding |
| **UI/layout** | Wrapping, alignment, fonts, RTL, ellipsis, accessibility | Inferring business values back from labels |

One-way flow diagram:

```text
Persistence / API (canonical data)
                 |
                 v
    Domain model / use case
                 |
                 | typed and semantic data
                 v
          Presenter / i18n
         /          |          \
   ResourceBundle  NumberFormat  DateTimeFormatter
         \          |          /
                 v
       View model / UI strings
                 |
                 v
       Layout, font, RTL, wrap

User input → locale-aware parser → validation → domain value
```

The UI submitting input does not break this principle: the input string is **only temporary input**; a parsing/validation step is responsible for converting it into a typed value before passing it to business logic.

## 4. Money: `BigDecimal` and Currency Code, Not a `String`

A common flawed design:

```java
// Flawed data model:
String total = "1.234,50 €";
```

This string simultaneously bundles **value**, **grouping separator**, **decimal separator**, **currency symbol**, and **locale convention**. It is hard to add, compare, persist reliably, or re-parse when the locale or JDK changes. The symbol `€` cannot replace a currency model; similarly, the symbol `$` can refer to many different currencies.

A clearer design:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
```

This is **a standalone Java file** if saved as `Money.java` (in the default package), runnable on Java 17+. It represents *amount + currency* without embedding any display locale. In production code, you also need scale/fractional unit rules, rounding, value ranges, and addition methods that only allow compatible currencies. `BigDecimal` preserves decimal digits, but it does not automatically enforce all financial rules.

### 4.1. `amount` Cannot Just Be `double` for Exact Monetary Calculations

`double` represents binary approximations; many numbers like `0.1` cannot be stored accurately in decimal. Use:

```java
BigDecimal amount = new BigDecimal("1234.50");
```

instead of:

```java
BigDecimal amount = new BigDecimal(1234.50);
```

when converting accurately from literal decimal text. For operations like division, you must choose scale and `RoundingMode` according to business rules. **The display formatter must not silently alter the domain amount** just because the UI only displays two digits.

### 4.2. Currency and Locale Are Two Separate Parameters

`Locale.GERMANY` only describes the user's display convention; it does not mean every transaction for that user uses EUR. A USD transaction for a user in Germany must still store `USD` and the exact amount, then format using **German locale** and **USD currency**.

Use `NumberFormat.getCurrencyInstance(displayLocale)` to obtain a formatter, then call `setCurrency(domainCurrency)`. Do not infer the actual currency from `Currency.getInstance(displayLocale)` if the transaction contract specifies its own currency.

## 5. Java 17+: One `Money`, Two Display Strings

Create `MoneyPresentationDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class MoneyPresentationDemo {
    record Money(BigDecimal amount, Currency currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }
    }

    static String display(Money money, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(money.currency());
        return formatter.format(money.amount());
    }

    public static void main(String[] args) {
        Money money = new Money(
                new BigDecimal("1234.50"),
                Currency.getInstance("EUR"));

        System.out.println("domain amount: "
                + money.amount().toPlainString());
        System.out.println("domain currency: "
                + money.currency().getCurrencyCode());

        for (String tag : List.of("en-US", "de-DE")) {
            Locale locale = Locale.forLanguageTag(tag);
            System.out.println(tag + ": " + display(money, locale));
        }

        System.out.println("unchanged: "
                + money.amount().equals(new BigDecimal("1234.50")));
    }
}
```

Run:

```bash
javac -encoding UTF-8 MoneyPresentationDemo.java
java MoneyPresentationDemo
```

Sample output from a JDK with standard CLDR locale data:

```text
domain amount: 1234.50
domain currency: EUR
en-US: €1,234.50
de-DE: 1.234,50 €
unchanged: true
```

The `de-DE` line may contain **U+00A0 NO-BREAK SPACE** before `€`, rather than an ASCII space. Symbol/position/spacing may differ across JDK versions or locale providers. The `domain amount`, `domain currency`, and `unchanged` lines illustrate what must remain invariant.

**Important isolation:** because `NumberFormat` is mutable and not thread-safe, the example creates a **new formatter per call**. Do not share a static `NumberFormat` across multiple requests while repeatedly calling `setCurrency`: configuration can leak and print the wrong currency.

### What if Two Fractional Digits Are Needed?

Do not rely solely on `setMinimumFractionDigits(2)` to determine whether a monetary amount is valid: that is **display formatting**. The domain currency policy may require different numbers of digits depending on currency and transaction type. Before storing or calculating, apply business validation and rounding (for example `RoundingMode.HALF_EVEN` or a mandatory business rule); only afterward should the formatter present the result according to the locale.

## 6. Status: Stable Codes Differ from Translated Labels

A serious design flaw:

```java
if (order.statusText().equals("Đã thanh toán")) {
    releaseGoods();
}
```

Every time the translation changes, the logic can break. Likewise, switching the language from English to Vietnamese is no reason for an order to change status.

Instead, use an enum or a stable domain status:

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED, REFUNDED
}
```

The corresponding resource can be:

```properties
status.NEW=New
status.PAID=Paid
status.CANCELLED=Cancelled
status.REFUNDED=Refunded
```

and the Vietnamese version:

```properties
status.NEW=Mới
status.PAID=Đã thanh toán
status.CANCELLED=Đã hủy
status.REFUNDED=Đã hoàn tiền
```

The `.properties` examples above are **two separate datasets**, not combined in the same file. In deployment, store them as `Labels_en.properties` and `Labels_vi.properties` on the classpath.

`ResourceBundle.getBundle("Labels", locale)` selects the translation via the locale fallback mechanism. `ResourceBundle` is a **presentation** component, whereas `OrderStatus.PAID` is business information. Do not pass translated labels into an API as an enum code; the API should use `"PAID"` per the agreed schema.

If the product needs to change the label `"Paid"` to `"Payment received"`, only the resource changes; domain logic requires no modification.

## 7. Java 17+ Example: `ResourceBundle` and `MessageFormat`

Place the three files in the **same directory** when running:

```text
Labels_en.properties
Labels_vi.properties
LocalizedStatusDemo.java
```

File `Labels_en.properties`:

```properties
status.PAID=Paid
receipt.summary=Order {0}: {1} — {2}
```

File `Labels_vi.properties`:

```properties
status.PAID=Đã thanh toán
receipt.summary=Đơn {0}: {1} — {2}
```

File `LocalizedStatusDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedStatusDemo {
    static String receipt(String orderId, String amountText,
            Locale locale) {
        ResourceBundle messages =
                ResourceBundle.getBundle("Labels", locale);
        String status = messages.getString("status.PAID");
        String pattern = messages.getString("receipt.summary");

        MessageFormat messageFormat =
                new MessageFormat(pattern, locale);
        return messageFormat.format(
                new Object[] {orderId, amountText, status});
    }

    public static void main(String[] args) {
        String id = "ORD-42";
        String currencyText = "1234.50 EUR";
        System.out.println(receipt(
                id, currencyText, Locale.ENGLISH));
        System.out.println(receipt(
                id, currencyText, Locale.forLanguageTag("vi-VN")));
    }
}
```

Run:

```bash
javac -encoding UTF-8 LocalizedStatusDemo.java
java LocalizedStatusDemo
```

Output:

```text
Order ORD-42: 1234.50 EUR — Paid
Đơn ORD-42: 1234.50 EUR — Đã thanh toán
```

Here `currencyText` intentionally uses an illustrative string created externally, to focus on **translation content**. In production, the value should flow from `Money` through `NumberFormat` for the locale before being inserted into the message.

**Important notes on `MessageFormat`:**

- A message pattern should be a **full sentence**, so translators can reorder placeholders `{0}`, `{1}`, `{2}` according to grammar.
- In `MessageFormat` patterns, the single quote `'` has special escaping rules; displaying a literal single quote often requires writing `''`. Do not route every resource string through `MessageFormat` without understanding its quoting rules.
- For complex locale-specific plurals, basic Java SE `MessageFormat` is not an engine that fully supports all CLDR plural categories; consider ICU MessageFormat or an i18n solution suited to the product.
- Translations are **linguistic data**, not a channel for embedding state-transition logic, SQL, monetary calculation expressions, or business action ordering.
- In web applications, data rendered into HTML still needs context-appropriate escaping (text nodes, attributes, URLs, etc.). `MessageFormat` does not automatically protect against HTML/script injection.

## 8. Date and Time: `Instant` Is Not a Language-Specific Date String

A transaction completes at:

```text
2026-10-28T01:30:00Z
```

This is an **absolute point in time**. A user in Tokyo sees a different wall-clock time than a user in UTC, but the `Instant` must be **the exact same instant**.

Do not store:

```text
"28/10/2026 08:30"
```

without an offset/timezone and schema, and then assume you can recover an invariant instant. `28/10/2026` may be a Vietnamese date format; elsewhere `10/28/2026` is used. With DST, the same local time may not exist or may occur twice.

### 8.1. Temporal Types by Business Meaning

| Need | Typically appropriate Java type | Notes |
| --- | --- | --- |
| Timestamp of an event that occurred | `Instant` | An absolute point on the timeline |
| Birth date, holiday (no time needed) | `LocalDate` | Do not convert to an instant without a zone/semantics |
| Daily recurring store opening hours | `LocalTime` + zone/schedule policy | Not equivalent to a timestamp |
| Scheduled appointment at 9:00 in a region | `LocalDateTime` + `ZoneId` and DST policy | Zone rules can change |
| Instant paired with a timezone | `ZonedDateTime` | Carries zone ID; consider storing instant and zone separately |
| Timestamp sent over API with an offset | `OffsetDateTime` if the schema requires it | Offset does not always preserve the region zone ID |

`DateTimeFormatter` turns a temporal object into a string. For localized display, you can use `ofLocalizedDateTime` with `withLocale` and `withZone` when formatting an `Instant`. If a machine-readable timestamp is needed, use `Instant.toString()`/`DateTimeFormatter.ISO_INSTANT` instead of localized output.

### Java 17+ Example: Same `Instant`, Multiple Display Times

Create `InstantPresentationDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class InstantPresentationDemo {
    public static void main(String[] args) {
        Instant paidAt =
                Instant.parse("2026-10-28T01:30:00Z");

        DateTimeFormatter format =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        System.out.println("stored: " + paidAt);
        System.out.println("UTC: " + format
                .withZone(ZoneId.of("UTC"))
                .format(paidAt));
        System.out.println("Tokyo: " + format
                .withZone(ZoneId.of("Asia/Tokyo"))
                .format(paidAt));
        System.out.println("unchanged: "
                + paidAt.equals(Instant.parse(
                        "2026-10-28T01:30:00Z")));
    }
}
```

```bash
javac InstantPresentationDemo.java
java InstantPresentationDemo
```

```text
stored: 2026-10-28T01:30:00Z
UTC: 2026-10-28 01:30 Z
Tokyo: 2026-10-28 10:30 +09:00
unchanged: true
```

This uses a fixed pattern for clear stdout output. In a multilingual UI, use `DateTimeFormatter.ofLocalizedDateTime(style).withLocale(locale).withZone(zone)` to apply the user's conventions, and **do not use the resulting string to store the instant**.

`DateTimeFormatter` is immutable; `withZone` returns a new formatter without mutating the old one. Conversely, many legacy formatters like `SimpleDateFormat` and `NumberFormat` are mutable and should not be shared across threads that change configuration.

## 9. Parsing Input: A Dedicated Layer Converts Text to Business Values

When a user enters `1.234,50` in a `de-DE` interface, this is **an input form string**. The domain should not parse commas/periods itself. An adapter/presenter/parser layer needs to know the locale and produce a `BigDecimal`:

```text
UI input "1.234,50" + locale de-DE
           |
           v
Locale number parser + full-input validation
           |
           v
BigDecimal("1234.50")
           |
           v
Domain validation: >=0, currency/scale/range...
           |
           v
Money(amount=1234.50, currency=EUR)
```

### Why Not Parse Directly Inside the Domain?

A domain model like `Money` can be constructed from a REST API, CSV import, database, batch job, desktop UI, or web form. If it accepted a string parsed with the JVM's default locale, different channels would inadvertently be forced into whatever format the server chose. Separating the parser at the **input boundary** keeps the domain consistent while each input channel has its own adapter.

### Java 17+ Example: Locale-Correct Parsing and Full-Input Validation

Create `LocalizedNumberInputDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocalizedNumberInputDemo {
    static BigDecimal parseAmount(String text, Locale locale) {
        if (text == null || text.isEmpty()) {
            throw new IllegalArgumentException("Empty amount");
        }

        NumberFormat base =
                NumberFormat.getNumberInstance(locale);
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException(
                    "DecimalFormat is required");
        }
        decimal.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number number = decimal.parse(text, pos);

        if (!(number instanceof BigDecimal exact)
                || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid localized amount");
        }
        return exact;
    }

    public static void main(String[] args) {
        Locale german = Locale.GERMANY;
        BigDecimal result =
                parseAmount("1.234,50", german);

        System.out.println("value: "
                + result.toPlainString());
        System.out.println("scale: " + result.scale());

        try {
            parseAmount("1.234,50oops", german);
        } catch (IllegalArgumentException ex) {
            System.out.println("suffix rejected");
        }

        try {
            parseAmount("1.234,50", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong locale rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LocalizedNumberInputDemo.java
java LocalizedNumberInputDemo
```

```text
value: 1234.50
scale: 2
suffix rejected
wrong locale rejected
```

**Key points:**

- `DecimalFormat` with `setParseBigDecimal(true)` preserves finite decimal values and the parsed string's scale.
- Standard `NumberFormat.parse(String)` can accept **just a prefix**; use `ParsePosition.getIndex()==text.length()` to detect trailing characters.
- `NaN`/infinity can return a `Double`, not a `BigDecimal`; `instanceof BigDecimal` helps reject values unsuitable for a money domain.
- Parsing the entire string **does not prove grouping follows strict rules**. `DecimalFormat` may accept misplaced grouping separators; if strict monetary fields are required, add lexical validation against your schema, scale, value range, and length limits.
- Do not change `Locale.setDefault(...)` per request; pass the confirmed locale from the profile/session/input format.
- If the currency is chosen separately on the form, the number parser must not guess the currency from the language tag.

## 10. Storage: Canonical Data, Not UI Text Snapshots

**Canonical data** is a value with a schema sufficient to be read back without guessing a locale.

| Domain value | Persistence/API recommendation | Should not be stored as source of truth |
| --- | --- | --- |
| `BigDecimal("1234.50")` | DECIMAL/NUMERIC column with clear precision/scale, or ungrouped decimal string | `"1.234,50"` in German locale |
| `Currency EUR` | `"EUR"` in an agreed ISO code column/field | `"€"` or `"Euro"` |
| `Instant` | Timestamp with UTC/offset contract, ISO 8601 | `"28/10/2026 08:30"` without zone |
| `OrderStatus.PAID` | Code `"PAID"` or schema-versioned enum mapping | `"Đã thanh toán"` |
| `Locale vi-VN` | BCP 47 language tag `"vi-VN"` | `"Tiếng Việt"` as an ID |
| `ZoneId` | Region ID such as `"Asia/Ho_Chi_Minh"` | Localized timezone display name |
| Product code | String code with its own rules | `NumberFormat` output with grouping added |

**Note on JSON:** A JSON number does not automatically guarantee every consumer will preserve precision/scale like `BigDecimal`; for exact monetary amounts, define a clear contract for type and representation (e.g., decimal string or a system-wide consistent JSON decimal format) rather than assuming every client parses numbers as decimals.

**Note on JDBC/DB:** The scale when storing `BigDecimal` depends on column schema and driver. A `DECIMAL(12,2)` column has constraints, rounding, and overflow rules that must be tested; do not assume data is valid just because the frontend displays two decimal digits.

### Java 17+ Example: Canonical Data and Round-Tripped Values

Create `CanonicalDataDemo.java`:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import java.util.Locale;

public class CanonicalDataDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("EUR");
        Instant paidAt =
                Instant.parse("2026-10-28T01:30:00Z");

        String storedAmount = amount.toPlainString();
        String storedCurrency = currency.getCurrencyCode();
        String storedInstant = paidAt.toString();

        BigDecimal amountBack = new BigDecimal(storedAmount);
        Currency currencyBack =
                Currency.getInstance(storedCurrency);
        Instant paidAtBack = Instant.parse(storedInstant);

        System.out.println("amount: " + storedAmount);
        System.out.println("currency: " + storedCurrency);
        System.out.println("instant: " + storedInstant);
        System.out.println("amount equals: "
                + amount.equals(amountBack));
        System.out.println("currency equals: "
                + currency.equals(currencyBack));
        System.out.println("instant equals: "
                + paidAt.equals(paidAtBack));
    }
}
```

```bash
javac CanonicalDataDemo.java
java CanonicalDataDemo
```

```text
amount: 1234.50
currency: EUR
instant: 2026-10-28T01:30:00Z
amount equals: true
currency equals: true
instant equals: true
```

For a `BigDecimal` with a negative scale, `toPlainString()` does not preserve all scale values when reconstructed; if exact scale must be preserved for **every** number, use `toString()` or store `unscaledValue + scale` per your schema. This example has scale 2 and round-trips to `equals` true.

Do not confuse storing **an issued document record** with storing **domain values**: an issued PDF invoice may require storing a snapshot for auditing; the domain record should still store amount, currency, date, line items, and the version of the content rules.

## 11. Domain Invariants Must Be Checked Before Presentation

For instance, a sales use case might specify:

- quantity must be a positive integer;
- unit price is non-negative;
- total = unit price × quantity;
- currencies across all lines must be compatible;
- tax or discount rounding follows a specific rule;
- timestamp is a valid point in time from the clock/service.

These rules **do not change when the user changes locale**. Do not treat strings like `"1,23"` or `"1.23"` as numeric values during calculations; those are input/output representations.

### Java 17+: Locale-Independent Domain Record Computing Total

Create `OrderDomainDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public class OrderDomainDemo {
    record OrderLine(BigDecimal unitPrice,
                     int quantity, Currency currency) {
        OrderLine {
            Objects.requireNonNull(unitPrice);
            Objects.requireNonNull(currency);
            if (unitPrice.signum() < 0 || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order line");
            }
        }

        BigDecimal total() {
            return unitPrice.multiply(
                    BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        OrderLine line = new OrderLine(
                new BigDecimal("411.50"),
                3, Currency.getInstance("EUR"));

        System.out.println("quantity: " + line.quantity());
        System.out.println("total: " + line.total().toPlainString());
        System.out.println("currency: "
                + line.currency().getCurrencyCode());
    }
}
```

```bash
javac OrderDomainDemo.java
java OrderDomainDemo
```

```text
quantity: 3
total: 1234.50
currency: EUR
```

Because the code calculates with `BigDecimal`, the result does not depend on the decimal separator of `vi-VN` or `de-DE`. `OrderLine` is a **simplified** model: a real system must also explicitly define tax, discount, quantity units, rounding, currency conversion, and non-negative monetary amount policies.

### Do Not Use Labels to Determine Status

**Wrong:**

```java
if (statusLabel.equals("Paid")) { /* process order */ }
```

**Right by responsibility layer:**

```java
if (order.status() == OrderStatus.PAID) {
    // language-independent business logic
}
```

This is **illustrative code** assuming a domain `order` variable and `OrderStatus` enum. The label `"Paid"`/`"Đã thanh toán"` is only produced after the use case already knows the status.

## 12. Independent Locale, Timezone, Currency, and UI Language

A user may select:

```text
display language: en-US
number format:    de-DE
time zone:        Asia/Ho_Chi_Minh
transaction money: USD
```

There is no contradiction. That user may prefer English, enter numbers using German conventions, view times in Vietnam time, and pay in USD. The application must resolve **each attribute** according to the product contract; do not use a single `Locale` to guess all preferences.

| Attribute | Possible sources | Meaning |
| --- | --- | --- |
| Message locale | Profile, app settings, supported `Accept-Language` values | Select translations/resources |
| Number input/output locale | User preference or explicitly defined form locale | Number parser/formatter |
| Zone ID | Profile, schedule setting, event region | Local date/time rules |
| Currency code | Order/price list/transaction contract | Business currency |
| Measurement unit | Domain/schema/controlled user preference conversion | kg/lb, km/mi, °C/°F |
| Calendar system | Business convention or presentation choice | ISO/Buddhist/Japanese calendar... |

**Do not use the server's `Locale.getDefault()` or `TimeZone.getDefault()` as a request's preference.** These defaults are JVM/process-level settings that may differ from the user and are unsafe to mutate repeatedly across concurrent requests.

If an internal application truly has only one fixed locale/zone, still make that choice an **explicit configuration**, so it can be tested and migrated.

## 13. DTO and API Design: Text Is Only a Projection

A machine-facing response and a UI-facing response may require different contracts.

### 13.1. API with Canonical Values

Illustrative JSON example:

```json
{
  "orderId": "ORD-2026-042",
  "status": "PAID",
  "amount": "1234.50",
  "currency": "EUR",
  "paidAt": "2026-10-28T01:30:00Z"
}
```

Here `amount` is a **decimal string per schema**, not a number with grouping separators; `paidAt` is an ISO instant. Consumers can produce translations in their own locale, and the API is not tied to English or Vietnamese separators.

### 13.2. UI Projection May Include Labels

For example, a view model might contain:

```json
{
  "orderId": "ORD-2026-042",
  "statusCode": "PAID",
  "statusLabel": "Đã thanh toán",
  "formattedTotal": "1.234,50 €",
  "formattedPaidAt": "28/10/2026 08:30"
}
```

The fields `statusLabel`, `formattedTotal`, and `formattedPaidAt` are **presentation data**, dependent on locale, zone, and active rules. Do not send them back to the API as authoritative data. If the backend provides a localized view model for the UI, still keep the **domain model and stable serialization** in the business layer.

### Avoid Double Formatting

If the backend already formatted a number using `de-DE` and the frontend calls an `en-US` formatter on that string, the output easily breaks or gets "double-formatted". It is best to decide clearly whether **formatting belongs to the server or the client**; when the client is responsible, send typed/schema-compliant raw amounts and locale preferences. When the server is responsible, send display text alongside the real code/value if the client needs to interact or submit.

## 14. Resource Keys Are Not Business Data

A resource key like `status.PAID` or `error.order.notFound` is a **message address**. It should remain stable in code and be managed via resource bundles. However, do not use a translated string as a key:

```java
// Unsafe when changing languages:
messageMap.get("Đơn hàng không tồn tại");
```

Better:

```java
messages.getString("error.order.notFound");
```

The key name describes meaning and usage location, while the actual content lives in locale-specific resources. If the wording changes from `"Không tìm thấy đơn hàng"` to `"Đơn hàng không tồn tại"`, the program still looks up the same key.

### Error Messages Must Separate Code and Message

For example, the domain/service returns:

```text
errorCode = ORDER_NOT_FOUND
orderId   = ORD-2026-042
```

The presentation layer can produce:

```text
vi-VN: Không tìm thấy đơn hàng ORD-2026-042.
en-US: Order ORD-2026-042 was not found.
```

API clients should handle errors by **error code**, not by comparing the displayed message string. Messages can change for copy improvements or locale switches without breaking logic.

## 15. The UI Owns Layout, Not the Domain

A longer translation may cause a button or label to need more space. **That is a UI responsibility**, not a reason to alter domain data.

The UI layer should:

- allow labels/containers to resize and wrap appropriately for the script/Unicode;
- choose fonts, line-height, alignment, accessibility, and overflow policy;
- support RTL/BiDi when required by the locale;
- preserve the underlying model's values and state when the user switches languages;
- never truncate product names or currency units in the domain layer just to fit a layout.

The string `"Đã thanh toán"` can be temporarily shortened to a separately authored short label in a narrow UI, while `OrderStatus.PAID` remains unchanged. If you need to store the exact wording of an issued document, that is an **audit/snapshot requirement** separate from domain data.

## 16. Anti-Examples That Couple Applications to a Language

### 16.1. Storing Formatted Numbers in the Database

```java
String stored = NumberFormat
        .getNumberInstance(Locale.GERMANY)
        .format(new BigDecimal("1234.50"));
```

The string may be `"1.234,5"` (not guaranteed to keep trailing zeros) and is **not a canonical decimal**. After upgrading locale providers, JDK versions, or when another process reads under a different locale, `stored` may fail to parse properly.

**Fix:** store DECIMAL/numeric or a schema-defined decimal string; format at render time.

### 16.2. Making Decisions Based on Button Text

```java
if (button.getText().equals("Delete")) {
    deleteRecord();
}
```

If the label becomes `"Xóa"`, the logic stops working. **Fix:** attach a business-meaningful action/command ID or event handler, rather than inferring the action from the button text.

### 16.3. Using Localized Date Strings as IDs

```text
"10/11/2026"
```

This string can mean November 10 or October 11 depending on region. **Fix:** pass `LocalDate` in ISO schema when it is a calendar date, or `Instant` when it is an absolute timestamp.

### 16.4. Mutating the Default Locale per Request

```java
Locale.setDefault(userLocale);
TimeZone.setDefault(userZone);
```

This is a JVM-wide change, not isolated to a single thread/request context. In a multi-user server, it easily causes race conditions. **Fix:** pass `Locale`/`ZoneId` explicitly into each formatter and use case; use dependency injection or a request context with clear ownership.

### 16.5. Using Display Names as Keys

```text
"Germany"     ← English country name
"Deutschland" ← German name
```

Both refer to country code `DE`. Storing display names as foreign keys causes language switches to break relationships. **Fix:** store an explicit domain code and present the name according to the display locale.

### 16.6. Using `String.equals` for Numeric or Date Concepts

```java
"1,234.50".equals("1.234,50") // false
```

That result is accurate for string comparison, but it says nothing about whether the two representations have the same **numerical value**. You must parse with the proper locale into `BigDecimal` and then compare by value. For `BigDecimal`, `equals` also checks **scale**; `compareTo(...) == 0` compares numerical value. Choose the comparison method that fits the business rule.

## 17. Designing Clear Boundaries for Multi-Channel Systems

A system may have web, mobile, batch import, CLI, and REST channels. Each channel need not share the same locale, yet all must produce **the same domain data types**.

```text
             Web form de-DE
               "1.234,50"
                     |
               Input adapter
                     |
Batch CSV canonical   |       REST JSON decimal string
     "1234.50"        |              "1234.50"
          \           |            /
           \          v           /
             BigDecimal(1234.50)
                     |
                Domain service
                     |
              Persistence decimal
                     |
               Presenter
              /     |     \
          de-DE   en-US   vi-VN
```

**Testable design:** parser adapters can be tested with `input + locale` pairs; domain services can be tested with typed objects **without installing JDK locales**; presenters can be tested with `domain + locale + zone`. Bugs can be isolated to clear boundaries.

### Do All Inputs Need to Keep Raw Strings?

Not necessarily. For a transaction amount field, after proper parsing and domain validation, storing only the numeric value and currency may suffice. If business rules require auditing exactly what the user typed, store the raw input **separately** with its source, timestamp, policy version, and security controls. Do not let raw form strings become the source of truth for calculations.

## 18. Testing: Vary the Locale, Keep the Domain Invariant

Do not merely snapshot every UI string. Test both **business invariants** and **expected presentation variations**.

### 18.1. Domain Data Tests

- Total amount does not change when display locale changes.
- Currency code does not change, even if the localized symbol differs.
- Status code does not change, even if the translated label differs.
- Epoch timestamp does not change, even if local wall-clock time differs.
- No business operation relies on `Locale.getDefault()`.

### 18.2. Parser Layer Tests

- Valid input for the given locale parses to the expected `BigDecimal`.
- Input with trailing suffixes, unexpected characters, or the wrong locale is rejected.
- Validation enforces precision, scale, bounds, and strict grouping if needed.
- Do not assume `parse(String)` returning a number means the entire input was parsed.
- Do not share mutable `NumberFormat` instances concurrently across threads.

### 18.3. Presentation Layer Tests

- Messages match `ResourceBundle` entries and placeholders are placed properly.
- Long labels wrap, scale, and are read completely by screen readers.
- Test CJK locales, RTL, non-ASCII Unicode grouping characters, and font fallback.
- JDK/CLDR updates may alter display strings; only write **literal** golden tests where an explicit contract requires it.
- The UI does not use labels as keys or for business decisions.

### Java 17+: An Executable Invariant Check

Create `DomainSeparationCheck.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.Locale;

public class DomainSeparationCheck {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("EUR");
        Instant created = Instant.parse("2026-10-28T01:30:00Z");

        String en = displayMoney(amount, currency, Locale.US);
        String de = displayMoney(amount, currency, Locale.GERMANY);

        if (en.equals(de)) {
            throw new AssertionError("Expected two display styles");
        }
        if (amount.compareTo(new BigDecimal("1234.50")) != 0
                || !currency.getCurrencyCode().equals("EUR")) {
            throw new AssertionError("Domain changed");
        }

        DateTimeFormatter fmt =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm", Locale.ROOT);
        String utc = fmt.withZone(ZoneId.of("UTC")).format(created);
        String tokyo = fmt.withZone(
                ZoneId.of("Asia/Tokyo")).format(created);
        if (utc.equals(tokyo)) {
            throw new AssertionError("Expected local times to differ");
        }
        if (!created.equals(
                Instant.parse("2026-10-28T01:30:00Z"))) {
            throw new AssertionError("Instant changed");
        }
        System.out.println("domain invariant: PASS");
        System.out.println("display variation: PASS");
    }

    static String displayMoney(
            BigDecimal amount, Currency currency, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(currency);
        return formatter.format(amount);
    }
}
```

```bash
javac DomainSeparationCheck.java
java DomainSeparationCheck
```

```text
domain invariant: PASS
display variation: PASS
```

This test confirms that **the same domain value** remains valid after rendering across multiple locales; it does not assert exact currency symbol placement per CLDR version. If a product has a strict contract on display strings, add presentation snapshot tests pinned to the version/provider.

## 19. Switching Locale at Runtime: Update the Presenter, Do Not Recreate the Domain

A common requirement is switching the UI language while the application is open.

Good flow:

1. Change the **UI/display locale** in session preferences or context.
2. The presenter reloads resources and reformats domain fields using the new locale/zone.
3. The UI updates text, layout direction, and wrapping.
4. Do not modify fields such as `order.total`, `order.currency`, `paidAt`, or `status`.
5. If a form currently has **unsubmitted text**, handle it separately: input typed under the old locale may no longer parse properly under the new locale. You can store the **parsed value** independently before re-rendering, or keep the source locale associated with that input until the user finishes; do not silently re-parse it with the new locale.

Never call the JVM's `Locale.setDefault(locale)` to switch language for a web session. Locale should belong to the UI/session/request context, with a clear source and no global state.

### Caution When Data Changes During Editing

Do not force a partially entered form string `"1.234,50"` into `"1,234.50"` merely by replacing characters: separators may be wrong, decimal input may be incomplete, and caret/selection positions or validation errors can break. Form design should clearly distinguish **raw draft**, **parsed value**, and **committed domain value** states.

## 20. Separating Business Data Also Improves Accessibility and Maintainability

The benefits extend beyond localization:

- **Easier testing:** domain services run on typed data without requiring a resource bundle system.
- **Easier translation:** translators only edit messages; they cannot alter enums/IDs or calculations.
- **Cross-platform flexibility:** web, Android, and desktop receive the same canonical data and choose their own renderers.
- **Safer migrations:** JDK/CLDR upgrades and translation edits do not break number/date schemas.
- **Reliable querying:** search keys and domain IDs stay stable; UI labels never become keys.
- **Cleaner auditing:** store timestamps, amounts, currencies, statuses, and rule version; UI snapshots can be stored independently when needed.
- **Better accessibility:** the UI chooses complete text, screen-reader labels, and alternative layouts without truncating domain data.
- **Stronger security:** output encoding and escaping happen at the presentation boundary in the right context, rather than letting translations affect HTML/SQL syntax.

However, **not everything in presentation can change freely without limits**. A transactional email or legally issued invoice may need to retain the exact wording that was sent. In that case, **the display snapshot is a separate versioned business artifact**, while the underlying data remains structured for calculation, reconciliation, and analytics.

## 21. Anti-Patterns and Alternatives

| Anti-pattern | Why it is dangerous | Alternative design |
| --- | --- | --- |
| `String total = "1.234,50 €"` as amount | Loses explicit decimal/currency types | `Money(BigDecimal, Currency)` |
| `double` for monetary amounts | Binary rounding errors | `BigDecimal` + domain rounding |
| Storing date `"28/10/2026"` and guessing | Ambiguous locale/timezone | `LocalDate`/`Instant` per schema |
| Using `statusLabel` as status | Changing translation breaks logic | Stable enum/code |
| Using `Currency.getSymbol` as currency ID | Symbols are not unique | ISO currency code |
| Using `Locale.getDisplayName` as key | Display names change with locale/CLDR | BCP 47 tag/code |
| Concatenating translated sentence fragments | Grammar order is hardcoded | Full message with placeholders |
| Calling `Locale.setDefault` per request | Race conditions on JVM default | Pass locale explicitly |
| Parsing input in domain using server locale | Adapter logic leaks into business layer | Localized input parser before domain |
| `parse(String)` without suffix check | Accepts malformed numbers or trailing junk | `ParsePosition` and validation |
| UI sending formatted strings back to API | Double-formatting or parse failures | Send canonical values per schema |
| Hardcoding text width for English | Translated text gets truncated | Responsive UI/wrapping |
| Sharing static mutable `NumberFormat` | Currency/locale leaks across threads | Separate formatter/clear lifecycle |
| Expecting `format → parse` to preserve exact number | Rounding/scale/pattern may lose data | Store domain data, not display text |
| Tests asserting only literal localized output | CLDR upgrades cause false failures | Separate domain invariant and display contract tests |
| Switching locale on uncommitted form and re-parsing | Input changes meaning | Manage raw draft/parsed/domain separately |

## 22. Self-Check Exercises

1. **If the same monetary amount displays as `€1,234.50` and `1.234,50 €`, which parts must be identical?** `BigDecimal amount=1234.50` and `Currency EUR`.
2. **Why shouldn't `"Đã thanh toán"` be used as a database status?** Because it is a translation; use a locale-independent code like `PAID`.
3. **Does `NumberFormat.getCurrencyInstance(Locale.GERMANY)` automatically know a transaction is in USD?** No. You must pass `Currency.getInstance("USD")` from the domain.
4. **Does `BigDecimal` solve all monetary rounding problems?** No; the domain must specify rounding/scale/precision rules.
5. **Can changing the display timezone modify the original `Instant`?** No; it only changes the local wall-clock representation.
6. **Are `Locale` and `ZoneId` the same setting?** No; language/formatting conventions and timezone are two independent dimensions.
7. **Is it valid for a user in Vietnam to prefer English while paying in EUR?** Yes; UI locale, timezone, and currency are independent.
8. **What should be done to convert `"1.234,50"` into domain money?** Parse using `de-DE`, verify the entire input and domain validation, then construct `BigDecimal`/`Money`.
9. **Why not use `Double.parseDouble` to read all localized forms?** It does not understand locale-specific separators and uses approximate binary floating-point types.
10. **If a translation resource changes `Paid` to `Payment received`, does `OrderStatus` need a migration?** No, when the status code is independent.
11. **What is the problem with an API sending `"1.234,50"` without a locale?** The string is ambiguous and depends on the recipient; use a canonical decimal schema.
12. **If an issued PDF invoice must preserve exact wording, does that conflict with separating domain and UI?** No; store a separate snapshot artifact alongside domain data.
13. **Is `MessageFormat` responsible for deciding monetary amounts?** No; it builds messages from existing values and locale-aware formatters.
14. **Why must switching locale while typing in a form be handled carefully?** Draft text may be formatted under the old locale; raw draft and parsed value must be managed separately.
15. **Should `Locale.getDefault()` be used in a multi-user server?** Not as the sole source of user context; pass locale explicitly.
16. **Why does layer separation make CI tests more stable?** Domain tests compare values unaffected by translations or CLDR updates; presentation tests verify their own separate responsibility.
17. **When should the domain store both zone and local time?** Future scheduled appointments defined in local time in a region, which can encounter DST gaps or overlaps.
18. **When should raw input be stored?** When required for audit/investigation or reconstructing exact input; store separately under retention and security policies.
19. **Why shouldn't the UI infer status from button text?** Text can change by locale or A/B test; action IDs/commands belong to logic.
20. **What must remain invariant when a user switches from `vi-VN` to `en-US`?** Values, status codes, currency, timestamps, IDs, and business rules.

## 23. Pre-Deployment Checklist

- [ ] Domain types have clear meaning: amount, currency, quantity, date/instant, status code.
- [ ] No business rule depends on a specific translation or a UI component's `getText()`.
- [ ] API/persistence uses canonical schemas, never the JVM's default formatted numbers/dates.
- [ ] Locale, zone, and currency are resolved separately from data sources and preferences.
- [ ] UI messages reside in `ResourceBundle` or an equivalent i18n system with stable keys.
- [ ] Messages contain placeholders so translators can reorder them for grammar.
- [ ] Input parsers know the source locale, check the full string, and enforce domain validation.
- [ ] Parsers and presenters have clear ownership; mutable formatters are never arbitrarily shared across threads.
- [ ] Switching locale does not mutate domain state; uncommitted form input is handled safely.
- [ ] UI supports long translations, RTL, wrapping, and accessibility.
- [ ] Domain tests do not depend on literal localized display strings.
- [ ] Presentation tests cover locales, fonts, JDK/CLDR providers, and timezones where required.
- [ ] Artifacts requiring verbatim preservation are stored as separate versioned snapshots rather than replacing domain data.

## References

- [Oracle Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-aware number and currency formatting/parsing, factory methods, currency configuration.
- [Oracle Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): decimal numbers, `setParseBigDecimal`, and grouping separator syntax.
- [Oracle Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency codes, symbols, and currency data fields.
- [Oracle Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal exactness, scale/precision, and rounding.
- [Oracle Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): locale/fallback resource lookup and classpath bundles.
- [Oracle Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholders, locale-specific subformats, and quoting rules.
- [Oracle Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): locale/zone-aware date-time formatting, immutable.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): absolute point in time.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale tags, defaults, and localizations.
- [Unicode CLDR Project](https://cldr.unicode.org/): locale data and version-to-version changes in number/date presentation.
