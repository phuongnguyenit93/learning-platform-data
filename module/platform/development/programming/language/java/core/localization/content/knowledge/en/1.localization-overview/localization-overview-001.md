# What Are Internationalization (i18n) and Localization (l10n)?

## 1. The Problem: One Application, Many Languages and Markets

Suppose a Java application serves users in Vietnam and the United States. For the same data, users may expect different interfaces and presentations:

| Component | Vietnam (example) | United States (example) |
| --- | --- | --- |
| Greeting | Xin chào | Hello |
| Date | 28/10/2026 | 10/28/2026 |
| Number | 1.234,5 | 1,234.5 |
| Displayed currency | VND, typically no decimal digits | USD, typically two decimal digits |

The representations above are illustrative; separators, spacing, currency symbols, and component order may vary according to the locale data standard of the runtime environment. The application must also consider time zones, forms of address, reading direction, translation length, and local regulations.

If every UI string, date format, and currency format is hardcoded directly into business logic, each new market will require changing many places. **Internationalization** and **localization** help separate market-specific parts from core logic.

## 2. Definitions and Relationship

**Internationalization (i18n)** is the process of **designing and building software so that it can adapt to multiple languages, regions, and cultural conventions without rewriting business logic for each market**. The abbreviation “i18n” consists of the letter *i*, 18 letters in between, and the letter *n*.

i18n work typically includes:

- Separating text from source code and placing it in resources that can be replaced per language.
- Representing language/region choices using `Locale` or BCP 47 language tags.
- Using appropriate APIs to format dates, times, numbers, percentages, currencies, and to compare/sort text.
- Designing interfaces for longer text, multiple scripts, and right-to-left reading direction; supporting Unicode.
- Defining mechanisms for selecting a language, a default language, and handling missing translations.

**Localization (l10n)** is the process of **preparing and testing a specific experience for a target language, region, or market** on top of software that already supports i18n. The abbreviation “l10n” consists of the letter *l*, 10 letters in between, and the letter *n*.

l10n work typically includes:

- Translating messages into Vietnamese, English, Japanese… and reviewing terminology in context.
- Choosing representations for dates, numbers, currencies, units of measurement, addresses, and personal names suitable for the target audience.
- Adapting images, guides, legal content, or phrasing to match relevant culture and regulations.
- Testing translations in the real UI, especially with long text, Vietnamese diacritics, and grammar.

**Relationship:** i18n creates **adaptability**; l10n provides and verifies **content/experience for each market**. An application can be well internationalized without having a Vietnamese translation yet; conversely, translating a few lines into Vietnamese does not mean it is properly internationalized if dates, numbers, or error messages are still hardcoded.

| Criterion | i18n | l10n |
| --- | --- | --- |
| Primary question | “Does the system support multiple locales?” | “Is the experience right for this locale?” |
| Timing | From design and development | When preparing or maintaining each local version |
| Example | Code calls `ResourceBundle` to fetch messages | File `messages_vi.properties` contains translations |
| Another example | Using `NumberFormat` by locale | Checking number/currency display for Vietnamese users |
| Result | A reusable application foundation | A tested localization |

## 3. What Information Is `Locale` in Java?

`java.util.Locale` describes elements of a language and region such as **language**, **script**, **region**, and **variant** when present. For example:

- `vi-VN`: Vietnamese, Vietnam region.
- `en-US`: English, United States region.
- `en-GB`: English, United Kingdom region; still English, but some conventions may differ from `en-US`.
- `zh-Hant-TW`: Chinese, Traditional script, Taiwan region.

In Java, `Locale.forLanguageTag("vi-VN")` creates a locale from a BCP 47 language tag. `Locale` **does not automatically translate strings** and **does not contain a time zone**. `ZoneId` must be managed separately when displaying an instant according to the user's location; for example, the Vietnamese language does not imply that the user is in Vietnam's time zone.

You should use a locale explicitly chosen based on user configuration or a valid selection from the request. `Locale.getDefault()` only reflects the runtime environment's default; on a server it may differ from each user's preferred language. Avoid changing `Locale.setDefault(...)` process-wide to serve individual requests because concurrent requests can interfere with one another.

## 4. Java 17+ Example: Same Code, Two Localizations

The following example uses `ResourceBundle` for messages, `NumberFormat` for currency, and `DateTimeFormatter` for dates. Create **four files in the same directory** with the following contents (save files in UTF-8).

**`messages.properties`** — base fallback messages:

```properties
welcome=Welcome
```

**`messages_vi.properties`** — Vietnamese translation:

```properties
welcome=Xin chào
```

**`messages_en.properties`** — English translation:

```properties
welcome=Hello
```

**`DemoI18n.java`**:

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class DemoI18n {
    public static void main(String[] args) {
        show(Locale.forLanguageTag("vi-VN"));
        show(Locale.forLanguageTag("en-US"));
    }

    private static void show(Locale locale) {
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);
        NumberFormat currency = NumberFormat.getCurrencyInstance(locale);
        DateTimeFormatter date = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

        System.out.println(locale.toLanguageTag() + " | "
                + messages.getString("welcome"));
        System.out.println("  money: " + currency.format(1234567.5));
        System.out.println("  date: " + date.format(LocalDate.of(2026, 10, 28)));
    }
}
```

Compile and run from the directory containing all four files:

```bash
javac -encoding UTF-8 DemoI18n.java
java -cp . DemoI18n
```

The two greeting lines are guaranteed to have the form **`vi-VN | Xin chào`** and **`en-US | Hello`** (each followed by `money` and `date` lines). The currency and date parts will have different representations depending on the locale; symbols, spacing, and date phrasing may depend on the JDK/CLDR, so do not assume a fixed stdout for those parts.

Here, **i18n** lies in the code reading resource bundles and using formatting APIs by `locale`; **l10n** lies in the contents of each `.properties` file and deciding which translation is appropriate. Changing the locale does not require modifying the `show` logic.

**Note on currency:** `getCurrencyInstance(locale)` uses the currency convention associated with the locale's region. The example only demonstrates formatting, **not currency exchange conversion between VND ↔ USD**; a transactional system must store the value, actual currency code, and conversion logic independently.

## 5. Lookup and Fallback Mechanism of `ResourceBundle`

With base name `messages` and locale `vi-VN`, `ResourceBundle` searches for matching candidates, such as `messages_vi_VN.properties`, then `messages_vi.properties`. The base bundle `messages.properties` can serve as a fallback. The full algorithm also considers the default locale and `ResourceBundle.Control` rules, so you should not assume there is only a single fallback chain in every configuration.

Practical principles:

1. Use **stable keys** such as `login.button`, `error.required`; do not use full translated sentences as keys.
2. Provide translations with the same meaning across locales; if a locale is missing a key, explicitly verify the fallback path. If a key is missing in every selected bundle, `getString` may throw `MissingResourceException`.
3. Avoid concatenating sentences from translated fragments (`"Hello " + name + "!"`) when grammatical structure may vary. Use parameterized messages so translators can adjust component order.
4. Do not use `Locale.toString()` as the standard for exchanging language tags over HTTP/API; prefer `toLanguageTag()` and `forLanguageTag(...)` for BCP 47.
5. On Java 9+, `ResourceBundle` reads `.properties` as UTF-8 by default (with compatibility behavior for handling legacy files). When working with legacy systems or custom packaging tools, still verify the actual encoding.

Parameterized message example:

```properties
order.summary=Order {0}: {1} items
```

You can use `java.text.MessageFormat` to substitute parameters by locale. Pay attention to single quotes in `MessageFormat` syntax, parameter formatting, and singular/plural differences. Standard Java `MessageFormat` does not automatically provide full plural/gender rules for all languages; if a product needs complex grammatical messages, consider a library supporting ICU MessageFormat or a tested mechanism.

## 6. Things That Should Not Be Confused

**Language, region, and time zone are three separate decisions.** A user who selects Vietnamese in London may still want dates/times in `Europe/London`. `LocalDate` is a calendar date; for an event with an absolute point in time, you must use `Instant`/ `ZonedDateTime` with the appropriate `ZoneId` before formatting. Selecting a locale alone does not convert time zones.

**Formatting is not the same as parsing data.** `NumberFormat` can format and parse strings according to a locale; commas `,` and periods `.` can have different meanings across markets. In APIs and data storage, use structured data types such as numbers and currency codes, and convert to localized strings only at the UI boundary.

**Text comparison is not always the same as byte/character comparison.** If a list of displayed names needs locale-dependent ordering, see `java.text.Collator`. Case conversion has language-specific edge cases (for example Turkish), so distinguish user-facing operations from technical identifiers that require stable rules such as `Locale.ROOT`.

**Unicode is necessary, not sufficient.** UTF-8 lets you store many scripts, but the UI must also have suitable fonts, avoid clipping characters with diacritics, avoid fixed English-based widths, and handle right-to-left text if required by product scope. For searching/matching personal names, you may need intentional Unicode normalization and locale rules.

**Translating words accurately does not guarantee proper localization.** For example, address entry instructions, full name formatting, measurement units, payment confirmation text, and tone of address may require dedicated editing for the target market.

## 7. Process for Applying This in a Java Project

1. **Identify the supported locales** and locale selection rules (user preference, application configuration, or `Accept-Language` when appropriate); define the fallback locale.
2. **Extract UI strings and error messages** into resource files. Name keys clearly, use parameters instead of string concatenation, and include translation context.
3. **Use the right APIs at display time**: `ResourceBundle` for messages; `NumberFormat` for numbers/percentages/currencies; `DateTimeFormatter` with locale for dates; `Collator` if language-aware text sorting is needed.
4. **Keep canonical logic and data independent of translations**: store numbers as numeric types, money with a currency code, and instants with appropriate time information. Do not use formatted strings as calculation values.
5. **Perform context-aware l10n**: translate, review terminology, and check parameterized cases, long text, diacritics, and regional requirements.
6. **Test a locale matrix**: test at least two locales with different separators; missing keys and fallback; number/date formatting; time zone selection; UI with long text; special characters. For automated tests, pass fixed locales/time zones to avoid depending on the runner's defaults.

### Common Mistakes and How to Avoid Them

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Hardcoding `"dd/MM/yyyy"` for all users | Displays incorrect local conventions | Use `DateTimeFormatter` by locale when displaying |
| Thinking `Locale` automatically translates text | UI remains in a single language | Provide resources/translations for the locale |
| Relying on the server's default locale | Users receive the wrong language | Pass the locale explicitly per operation |
| Treating locale as a time zone | Event date/time has the wrong location | Manage `ZoneId` separately |
| Treating currency formatting as currency conversion | Incorrect transaction amounts | Handle currency codes and exchange rates in business logic |
| Concatenating translated sentences from multiple fragments | Grammar errors in other languages | Use parameterized messages and l10n review |
| Testing only `en-US` | Misses diacritic, font, number, and date bugs | Test locales with different conventions and real translations |

## 8. Key Takeaways

- **i18n**: build an architecture that allows changing languages and presentation conventions by `Locale`, avoiding business-logic edits for each market.
- **l10n**: create, edit, and test suitable content/experiences for **a** specific locale or market.
- In Java, `Locale`, `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`, and when needed `Collator` are foundational tools. They handle formatting, resource selection, and language rules; translation quality and cultural decisions still require human and l10n-process verification.
