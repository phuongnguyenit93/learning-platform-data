# Building an API Selection Matrix and Self-Assessing Common Localization Bugs

## 1. Objectives and How to Use This Practice

In Java, "localization" is not a single function. Translating a message, formatting a monetary amount, sorting names alphabetically, handling accented Unicode, and rendering right-to-left text are **different problems**. Choosing the wrong API can yield output that looks fine on a developer's laptop yet fails on a user's machine—or worse, corrupts business data.

This Knowledge article builds an **API decision matrix** for Java 17+, then uses **anti-pattern vs. proper design scenarios**, **runnable code**, **self-scored exercises**, and **testing checklists** to evaluate a localization design. It is a comprehensive synthesis guide: learners should be able to apply the decision matrix when reading legacy code, reviewing pull requests, and designing new features.

After studying this lesson, you should be able to answer:

1. When to use **Locale**, **ResourceBundle**, or **MessageFormat**?
2. Why don't **NumberFormat**, **Currency**, **BigDecimal**, and exchange rates substitute for one another?
3. When to use **LocalDate**, **Instant**, **ZoneId**, and **DateTimeFormatter**?
4. When is **String.compareTo** inappropriate and when should **Collator** be used?
5. When are **Normalizer**, **BreakIterator**, **Character**, or **Bidi** needed?
6. Why does a valid `Locale` not imply the application actually has translations?
7. How to detect bugs caused by default `Locale`, fallback, Unicode spaces, thread safety, or time zones?
8. How to write tests that avoid pinning outcomes tied to a single CLDR/JDK version?
9. How to assess severity and prioritize localization bug fixes using objective criteria?
10. How to separate typed data from display strings so monetary amounts and timestamps are never corrupted?

## 2. First: Identify the Right Problem Category

Divide requirements into seven categories. If you do not yet know which category a requirement belongs to, hold off on picking an API.

| Category | Practical Question | Example |
| --- | --- | --- |
| **Language** | Which sentences, buttons, errors, and content have translations? | `"Thanh toán" / "Pay"` |
| **Formatting** | How is the same value written for a region? | `1,234.50` vs. `1.234,50` |
| **Calendar/Time** | In which region is a date or instant displayed? | Order timestamp in Vietnam vs. the US |
| **Text Comparison** | Sort names by technical code units or reader's dictionary order? | `An`, `Ánh`, `Đào` |
| **Normalization & Segmentation** | How are Unicode encodings, word boundaries, and graphemes handled? | `é` vs. `e` + combining acute |
| **Layout & Text Direction** | How are LTR/RTL text, numbers, and punctuation rendered? | Order ID inside an Arabic sentence |
| **Business Logic & Security** | Do values, IDs, units, or permissions change with locale? | EUR, account ID, access policy |

Some requirements span **multiple categories simultaneously**. For example, an invoice email needs: selecting messages by language, formatting currency by region, converting an `Instant` to the recipient's `ZoneId`, and rendering HTML with escaping/bidi. That does not mean creating one giant `"LocaleUtils"` class holding all logic; each part needs a clear contract.

**Guiding principle:** store typed values and logical ordering; call locale APIs to produce **representations** when needed; never parse representations back without a formal input contract.

## 3. Java 17+ API Selection Matrix by Requirement

The table below is your primary lookup reference. The "Avoid confusing with" column is just as important as the API column.

| Need | Suitable API / Feature | Avoid Confusing With |
| --- | --- | --- |
| Represent language/region/script | **java.util.Locale**, `Locale.forLanguageTag` | Constructing a `Locale` does not guarantee translations exist |
| Pick one locale from browser preferences | **Locale.LanguageRange.parse**, `Locale.lookup`/`filter` | Do not populate app menus with all available locales |
| Query locales advertised by the JDK | **Locale.getAvailableLocales()** | Does not prove every service or UI supports them |
| Query number-formatter locales | **NumberFormat.getAvailableLocales()** | Do not infer from `Collator`'s list |
| Query collation locales | **Collator.getAvailableLocales()** | Do not use `NumberFormat`'s list to conclude support |
| Look up messages by key/language | **ResourceBundle.getBundle**, `getString` | Do not auto-translate domain identifiers |
| Substitute arguments per sentence grammar | **MessageFormat** | Do not concatenate fixed prefix + amount + suffix |
| Format regular numbers | **NumberFormat.getNumberInstance(locale)** | Do not use `Double.toString` for UI formatting |
| Format ratio `0.125` → `12.5%` per region | **NumberFormat.getPercentInstance(locale)** | Do not pass `12.5` if input is a fraction |
| Format money per region | **NumberFormat.getCurrencyInstance(locale)** | Does not replace exchange rates or source `Currency` |
| Model currency unit | **Currency.getInstance("EUR")** | `Currency` is not an amount and does not convert money |
| Exact decimal arithmetic | **BigDecimal** | Do not call `new BigDecimal(double)` casually |
| Explicit grouping/decimal symbols | **DecimalFormatSymbols**, `DecimalFormat` | Do not use to replace all locale tailoring |
| Pure calendar date, no timezone | **LocalDate** | Never treat `LocalDate` as an `Instant` |
| Absolute point in time | **Instant** | Never treat `Instant` as local wall-clock time |
| Local time-zone rules | **ZoneId**, `ZonedDateTime` | Never infer timezone from `Locale` |
| Java 17+ date/time formatting | **DateTimeFormatter**, `FormatStyle`, `withLocale` | Avoid shared mutable `SimpleDateFormat` |
| Technical ISO formatting | **DateTimeFormatter.ISO_...**, contracted `toString` | Never send localized strings in machine APIs |
| Sort names linguistically | **Collator.getInstance(locale)** | Do not use `String.compareTo` as dictionary order |
| Technical UTF-16 comparison | **String.compareTo** | Not locale-aware |
| Canonical Unicode normalization | **Normalizer** with `NFC`/`NFD` | Not equivalent to accent stripping, search, or collation |
| Intentional compatibility normalization | **Normalizer** with `NFKC`/`NFKD` | Can introduce collisions across distinct characters |
| Word/sentence/grapheme boundaries | **BreakIterator** | Do not use `split(" ")` for every language |
| Inspect character category/direction/code point | **Character** and `String.codePoints` | Do not assume every `char` is a full code point |
| Bidirectional text analysis | **java.text.Bidi**, renderer text layout | Never reverse RTL strings |
| Locale-sensitive casing | **String.toLowerCase(locale)** under clear policy | Does not replace `Collator` or full case folding |
| Preserve UTF-8 when reading/writing | **StandardCharsets.UTF_8**, explicit charset readers/writers | Do not rely on OS default charset or strip accents as a workaround |
| Paginating sorted names in a database | **DB** collation + consistent ID tie-breaker | Do not sort each page independently on the client |
| Protect HTML containing user arguments | Template autoescaping / contextual escaping | `ResourceBundle`/`MessageFormat` do not prevent XSS |

**How to use:** before implementing any feature, locate its "Need" row, write down the input data type and correctness criteria, and then pick the collaborating APIs. Never choose a class solely because its name sounds similar to a word in the requirements.

## 4. Data → Representation → Testing Matrix

Choosing the right API is only step one. You must explicitly define what is allowed to vary when switching locales.

| Source Value | Type to Preserve | Allowed to Vary | Invariant to Assert |
| --- | --- | --- | --- |
| `1234567.89` | `BigDecimal` | Grouping/decimal separators, digit glyphs | Numeric value unchanged |
| `1234.50 EUR` | `BigDecimal` + `Currency` | Currency symbol, symbol placement, spacing | Amount and currency code unchanged |
| `0.125` | `BigDecimal` ratio | `12.5%` phrasing, `%` placement | Ratio remains `0.125` |
| `2026-10-28` | `LocalDate` | Day/month ordering, month names | Underlying calendar date unchanged |
| `2026-10-28T02:30:00Z` | `Instant` | Local date/time and formatting | `Instant`/epoch unchanged |
| `ORD-1028` | `String` ID | May need isolation inside RTL sentences | Logical content of ID unchanged |
| Person's name | Unicode `String` | Locale-based sort and layout | Never silently strip diacritics |
| `order.confirmed` | Message key | Translated text, placeholder order | Key and business meaning unchanged |

If a "localization" operation alters the amount, ID, `Instant`, or currency unit, that is almost always a sign of **mixing presentation with business logic**. Explicitly specified exceptions are genuine **currency conversion** or **business calendar conversion** features, where changing values is a dedicated, rule-governed operation—never a formatter side effect.

## 5. API Selection: Messages and Language Choice

### 5.1. Locale Is Only a Language/Region Identity

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

This snippet requires `import java.util.Locale;`. It identifies a locale—it **does not mean** the UI has Vietnamese translations. An application may support two languages while the JDK ships locale data for hundreds more.

Maintain a product-tested and published **`supportedLocales`** list. For priority-based matching, use `Locale.LanguageRange` and `Locale.lookup`. Never mutate `Locale.setDefault` per server request; it is global JVM state with broad side effects.

### 5.2. ResourceBundle Fetches Content, MessageFormat Builds Sentences

`ResourceBundle` returns patterns by key. `MessageFormat` fills `{0}`, `{1}` placeholders in the order arranged by translators. Example:

~~~properties
order.summary=Đơn {0} có tổng {1}.
~~~

English version:

~~~properties
order.summary=Order {0} totals {1}.
~~~

Sentence patterns can swap argument positions across languages. Never hardcode fixed prefix + amount + suffix concatenation. Preformatted money/date strings can be passed in as arguments.

**MessageFormat pitfall:** single quotes act as quoting syntax in patterns. To output a literal apostrophe, you generally must write **''**. QA every pattern across every locale; having a key does not guarantee valid pattern syntax.

**ResourceBundle pitfall:** fallback may load the base bundle or another language. A successful `getBundle` call does not prove the `vi-VN` translation is complete. Test suites must compare key sets and detect partial translations per application policy.

### 5.3. What Does Not Belong in the Message Service?

`ResourceBundle` does **not** decide exchange rates, rounding, ISO currency codes, time zones, or access permissions. If a display key translates to `"Pay"`, never use that translated text itself as the action ID; use a stable identifier like `payment.submit`. The message service must never mutate domain objects.

## 6. API Selection: Numbers, Currency, and Percentages

### 6.1. NumberFormat and Typed Numeric Data

~~~java
BigDecimal amount = new BigDecimal("1234.50");
Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat number =
        NumberFormat.getNumberInstance(locale);
NumberFormat money =
        NumberFormat.getCurrencyInstance(locale);
NumberFormat percentage =
        NumberFormat.getPercentInstance(locale);
~~~

This snippet requires importing `java.math.BigDecimal`, `java.util.Locale`, and `java.text.NumberFormat` inside a method.

**`getNumberInstance`:** grouping/decimals. **`getCurrencyInstance`:** adds currency formatting rules (symbol, placement, fraction digits). **`getPercentInstance`:** scales a fraction for `%` display. Never collapse them into one formatter and swap characters manually.

### 6.2. Currency Is Not an Exchange Rate

~~~java
Currency unit = Currency.getInstance("EUR");
money.setCurrency(unit);
String shown = money.format(amount);
~~~

This snippet requires importing `Currency` and the `money`/`amount` variables above. The amount remains `1234.50 EUR`; `setCurrency` does **not** convert it to VND or USD. If business logic requires conversion, you need an exchange rate, effective timestamp, rounding, audit trail, and a calculation step prior to formatting.

A formatter may default to the locale's regional currency—such as USD for `en-US`. When order data specifies EUR, set EUR explicitly; never let the viewer's default currency overwrite the transaction's true currency code.

### 6.3. BigDecimal and Rounding

Use **`new BigDecimal("0.1")`** to preserve exact specified decimals; never use **`new BigDecimal(0.1)`** when expecting exact `0.1`. `Currency.getDefaultFractionDigits()` helps standard presentation, yet **is insufficient as a financial calculation rounding policy**. In financial domains, distinguish storage precision, calculation precision, and display precision.

### 6.4. Unicode Spaces Are Not Formatter Bugs

Some locales insert **U+00A0 NBSP** or **U+202F NNBSP** between numbers and currency symbols or as grouping separators. Inspect with `String.codePoints()` rather than blindly calling `trim` or `replaceAll` on formatted output. Two strings that look identical yet hold different code points are completely normal in localized data.

### 6.5. Parsing User-Entered Input

Never parse a string with `vi-VN` grouping separators using `Locale.US`. `NumberFormat.parse` may consume only **a valid prefix**; when strictness is required, verify **`ParsePosition.getIndex() == input.length()`** and handle errors. For exact money, `DecimalFormat` supports **`setParseBigDecimal(true)`**; understand your active provider and configuration. Machine-to-machine communication should use typed values or fixed technical formats instead of localized strings.

## 7. API Selection: Dates, Times, and Time Zones

### 7.1. LocalDate, Instant, and ZoneId Have Distinct Meanings

- **`LocalDate`:** pure calendar date, such as a birthday or delivery date `2026-10-28`, with no time component.
- **`Instant`:** absolute point on the UTC timeline, such as a payment timestamp.
- **`ZoneId`:** regional time-zone rule set, such as `Asia/Ho_Chi_Minh` or `America/Los_Angeles`.
- **`ZonedDateTime`:** a local date-time viewed in a zone, carrying enough context to map to an `Instant` when valid.
- **`DateTimeFormatter`:** converts typed temporal values into text by pattern, `FormatStyle`, and `Locale`.

**`Locale` is not `ZoneId`.** An English-UI user can be located in Asia; `Locale.US` is insufficient to determine local time.

### 7.2. Display Formatting vs. Machine Formatting

~~~java
DateTimeFormatter display =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.LONG).withLocale(locale);
~~~

This snippet requires importing `DateTimeFormatter` and `FormatStyle`, with `locale` defined.

**UI:** use localized formatting. **Machine APIs:** use ISO 8601 or a fixed contracted format. Never return `"28 tháng 10 năm 2026"` and force a client to parse it with `MM/dd/yyyy`.

### 7.3. Instant First, Display Afterward

~~~java
Instant instant =
        Instant.parse("2026-10-28T02:30:00Z");
ZonedDateTime shown =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

This snippet requires importing `Instant`, `ZonedDateTime`, and `ZoneId`. The `Instant` never changes when viewed in another `ZoneId`, whereas **local date and time can change**, even shifting to the previous or next calendar day.

### 7.4. SimpleDateFormat or DateTimeFormatter?

In modern Java 17+ code, prefer `java.time`/`DateTimeFormatter` because the API is strongly typed and formatters are immutable and thread-safe. **`SimpleDateFormat`** is a legacy mutable API; never share an instance across server threads without synchronization or isolation. When interfacing with legacy `Date`/`java.util.Calendar`, define explicit conversion boundaries and avoid dropping time zones.

## 8. API Selection: Sorting, Normalization, and Text Segmentation

### 8.1. String.compareTo Is Not Collator

~~~java
int codeUnitOrder = "Z".compareTo("a");
~~~

**`String.compareTo`** compares **UTF-16 `char`s** left to right, not according to local dictionary order. For example, `Z` precedes `a` in technical code units, whereas personal name lists typically group upper/lowercase letters near one another. Use **`Collator.getInstance(locale)`** when reader-friendly name ordering is needed.

`Collator` offers **`PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL`** strengths plus decomposition modes. Certain case or diacritic differences may compare equal at lower strengths; never assume **`collator.compare(a, b) == 0`** implies **`a.equals(b)`**.

**Specifically:** if a comparator returns `0` for two distinct `String`s, **`TreeSet`/`TreeMap`** will treat them as the same key. Key identity by business ID, and optionally append a tie-breaker when a total ordering is required.

### 8.2. Normalizer Handles Canonical Unicode, Not Dictionary Order

The letter **é** can be encoded as **U+00E9** or **U+0065 + U+0301**. When checking canonical equivalence, normalize both to **`NFC`** or **`NFD`**. They can look identical yet fail `String.equals` prior to normalization.

**`NFKC`/`NFKD`** go further into compatibility normalization, folding certain symbols, fullwidth forms, and ligatures together. Choose deliberately, especially when handling IDs, access controls, or data where collisions are dangerous. **`Normalizer` is not a linguistic sorting tool**, not a full search engine, and does not replace `Collator`.

### 8.3. BreakIterator Finds Text Boundaries, Not split(" ")

Use **`BreakIterator.getWordInstance(locale)`**, **`getSentenceInstance(locale)`**, or **`getCharacterInstance(locale)`** to determine boundaries via runtime rules. In some writing systems, word splitting cannot rely on spaces at all. Test real emojis, combining marks, and sentences; "character instance" does not automatically solve every complex UI grapheme scenario across every Unicode version.

### 8.4. Accented Characters and Supplementary Code Points

**`String.length()`** counts UTF-16 code units; a Unicode code point outside the BMP can require two `char`s. Use **`String.codePoints()`** when debugging code-point sequences; **`StringBuilder.reverse()`** is not a solution for RTL layout, canonical normalization, or grapheme-safe editing.

## 9. API Selection: Bidi, Fonts, and Rendering

For content mixing LTR Latin, RTL Arabic/Hebrew, digits, and punctuation, the Unicode Bidirectional Algorithm determines visual ordering from the logical string. **`java.text.Bidi`** provides analysis of base direction, embedding levels, and directional runs.

However, **`Bidi` is not a font shaping engine** and does not draw glyphs. A UI still requires a renderer supporting shaping and line breaking. Never reverse Strings with `reverse()` to "fix" RTL text, as that corrupts product codes, phone numbers, parentheses, and logical order.

In HTML embedding an RTL user name inside an LTR sentence, use **`bdi dir="auto"`** or platform direction/isolation primitives. **HTML escaping remains mandatory**: `ResourceBundle`, `MessageFormat`, and `bdi` do not replace XSS protection.

**Security note:** directional overrides such as `U+202E` can make text appear visually different from its logical order, so code review tools, filenames, and audit logs need clear warning/escaping policies. Never blindly ban legitimate RTL text.

## 10. Anti-Pattern and Fix Matrix

| Symptom | Root Cause | Safe Fix |
| --- | --- | --- |
| Vietnamese UI, but numbers format like server | Using default `Locale` | Pass `formatLocale` explicitly |
| Menu lists 500 languages, app translated two | Using `Locale.getAvailableLocales` for UI menu | Maintain dedicated `appSupportedLocales` list |
| Mixed languages across sentences | Uncontrolled `ResourceBundle` fallback | QA coverage and explicit fallback policy |
| Apostrophe patterns drop words | Improper `MessageFormat` quoting | Double `'` in patterns and test |
| USD appears on an EUR order | Default currency inferred from viewer locale | Set the transaction's actual `Currency` |
| Monetary amount off by `0.1` | Using `BigDecimal(double)` | Construct `BigDecimal` from strings/exact sources |
| `12.5` displays as `1,250%` | Confusing fraction with percentage value | Pass `0.125` for `12.5%` |
| Date off by one day | `Instant` not converted through proper `ZoneId` | Resolve zone before formatting |
| `dd/MM/yyyy` confuses US users | Hardcoded UI date format | Use localized `DateTimeFormatter` |
| Concurrent requests corrupt each other's formatters | Sharing mutable `NumberFormat` | Create per request or isolate |
| Capitalized/accented names sort strangely | Using `String.compareTo` for UI | Use locale-specific `Collator` |
| Distinct names vanish in `TreeSet` | Low `Collator` strength yields `compare == 0` | Use IDs and comparator tie-breakers |
| Precomposed and decomposed `é` fail to match | Missing normalization policy | Apply `Normalizer` `NFC`/`NFD` where appropriate |
| Thai words split improperly | Using `split(" ")` | Use `BreakIterator` and test rules |
| Order ID inside RTL sentence looks scrambled | Reversing strings or missing isolation | Use bidi/layout isolation properly |
| Tests break after JDK upgrade | Unpinned CLDR snapshots | Separate invariant tests from locale-data tests |
| API sends `"1.234,50"` to another service | Using localized display text as wire format | Use typed numbers/ISO per contract |
| HTML displaying user names suffers XSS | Raw string insertion | Use template autoescaping |
| A–Z pagination scrambles entries across pages | DB and UI use different comparators | Use one global sort + ID tie-breaker |
| Garbled charsets/emojis on export | Uncontrolled UTF-8/fonts | Enforce UTF-8 and glyph-capable renderers/fonts |

**Key reviewer question:** is the bug in stored data, locale selection, formatter configuration, bundle lookup, or purely the renderer? Before applying a quick `String.replace` patch, pinpoint the exact boundary at fault.

## 11. Runnable Example: API Invariant Self-Check Suite

**File LocalizationSelfCheck.java**

This example feeds in typed values and asserts conditions **independent of CLDR-formatted strings**: app locale selection, `BigDecimal`, currency code, UTC date, Unicode normalization, raw UTF-16 order, and `MessageFormat` quoting. Every `PASS` line verifies an invariant guaranteed by Java 17 APIs.

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class LocalizationSelfCheck {
    private static void check(String name, boolean condition) {
        System.out.println(name + "="
                + (condition ? "PASS" : "FAIL"));
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        List<Locale> supported = List.of(vi, Locale.US);
        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8");

        Locale chosen = Locale.lookup(ranges, supported);
        check("locale", vi.equals(chosen));

        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.10");
        check("decimal", a.compareTo(b) == 0);

        Currency money = Currency.getInstance("EUR");
        check("currency",
                "EUR".equals(money.getCurrencyCode()));

        Instant event = Instant.parse(
                "2026-10-28T02:30:00Z");
        LocalDate atUtc =
                event.atZone(ZoneId.of("UTC")).toLocalDate();
        check("utcDate",
                LocalDate.of(2026, 10, 28).equals(atUtc));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        check("nfc", Normalizer.normalize(
                composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        check("rawOrder", "Z".compareTo("a") < 0);

        MessageFormat pattern = new MessageFormat(
                "User {0}: it''s ready", Locale.US);
        check("message",
                "User Lan: it's ready".equals(
                        pattern.format(new Object[] {"Lan"})));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LocalizationSelfCheck.java
java LocalizationSelfCheck
~~~

Exact stdout:

~~~text
locale=PASS
decimal=PASS
currency=PASS
utcDate=PASS
nfc=PASS
rawOrder=PASS
message=PASS
~~~

### Explanation of Checks

- **locale:** `Locale.lookup` receives a supported set containing `vi-VN`; since `vi-VN` has the highest priority, it selects `vi-VN`.
- **decimal:** `BigDecimal.compareTo` treats `0.1` and `0.10` as numerically equal, unlike `equals` which also checks scale.
- **currency:** `EUR` is explicitly constructed from its ISO currency code, independent of region.
- **utcDate:** `Instant` is converted with `ZoneId` `UTC` rather than relying on the server's time zone.
- **nfc:** two canonically equivalent strings normalize to the identical NFC form.
- **rawOrder:** reminds that `compareTo` uses UTF-16 order rather than local dictionary order.
- **message:** doubled single quotes inside the `MessageFormat` pattern output one literal apostrophe.

**Intentional limitation:** this program does not validate product translations. It verifies core API invariants and semantics, not whether `vi-VN` has complete translations or formatting coverage on your runtime.

## 12. Runnable Example: Auditing Localized Output Without Guessing Stdout

**File LocaleFormatAudit.java**

This second program prints the same `BigDecimal`/`Currency`/`LocalDate`/`Instant` across three locales. It is an audit tool for observing **actual values produced by the running JDK** rather than pinning one exact stdout string across all CLDR versions. However, the final four lines print verifiable source values:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class LocaleFormatAudit {
    private static void show(
            Locale locale,
            BigDecimal amount,
            Currency currency,
            LocalDate day,
            Instant event) {

        NumberFormat number =
                NumberFormat.getNumberInstance(locale);
        NumberFormat money =
                NumberFormat.getCurrencyInstance(locale);
        money.setCurrency(currency);

        DateTimeFormatter date =
                DateTimeFormatter.ofLocalizedDate(
                        FormatStyle.LONG).withLocale(locale);

        ZoneId zone = ZoneId.of("UTC");
        DateTimeFormatter moment =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.MEDIUM).withLocale(locale);

        System.out.println("locale="
                + locale.toLanguageTag());
        System.out.println("  number="
                + number.format(amount));
        System.out.println("  money="
                + money.format(amount));
        System.out.println("  date="
                + date.format(day));
        System.out.println("  time="
                + moment.format(event.atZone(zone)));
        System.out.println("  currencyCode="
                + currency.getCurrencyCode());
    }

    public static void main(String[] args) {
        BigDecimal amount =
                new BigDecimal("1234.50");
        Currency euro = Currency.getInstance("EUR");
        LocalDate date = LocalDate.of(2026, 10, 28);
        Instant event =
                Instant.parse("2026-10-28T02:30:00Z");

        show(Locale.forLanguageTag("vi-VN"),
                amount, euro, date, event);
        show(Locale.US, amount, euro, date, event);
        show(Locale.GERMANY, amount, euro, date, event);

        System.out.println("sourceAmount="
                + amount.toPlainString());
        System.out.println("sourceCurrency="
                + euro.getCurrencyCode());
        System.out.println("sourceDate=" + date);
        System.out.println("sourceInstant=" + event);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LocaleFormatAudit.java
java LocaleFormatAudit
~~~

The program prints three blocks beginning with **locale=vi-VN**, **locale=en-US**, and **locale=de-DE**. Within each block, **number/money/date/time** are computed by the active runtime; avoid defining one universal "golden" snapshot across every JDK release. Still, the last four lines are verifiable source values:

~~~text
sourceAmount=1234.50
sourceCurrency=EUR
sourceDate=2026-10-28
sourceInstant=2026-10-28T02:30:00Z
~~~

**Success criteria:** source data never mutates across the three locales, currency remains `EUR`, and `Instant` remains the exact same moment. Differences in digits, decimal points, spaces, or month names are purely **presentation**. If exact per-locale snapshots are required, pin the runtime/provider and inspect code points—especially NBSP/NNBSP.

## 13. Quick Diagnostic Drill: Which API to Choose?

Read all 15 scenarios; before checking the answer table, write down the **primary API + secondary API (if any) + one pitfall to avoid**.

| Code | Scenario |
| --- | --- |
| A1 | User selects `vi-VN` UI while the server runs in `en-US` |
| A2 | Translate a sentence containing customer name and order total |
| A3 | Format `1234567.89` with `fr-FR` grouping separators |
| A4 | Order for `1234.50 EUR` is viewed from the United States |
| A5 | Display `12.5%` from ratio `0.125` |
| A6 | Display birth date `2026-10-28` across multiple regions |
| A7 | Display the same payment instant in Hanoi and California |
| A8 | Sort a list of names with `ă`, `â`, `đ`, and tone marks |
| A9 | Detect two Unicode encodings of the letter `é` |
| A10 | Select the next word on double-click in a multilingual document |
| A11 | Display order ID `ORD-1028` inside an Arabic sentence |
| A12 | A `TreeSet` drops names differing only by case |
| A13 | `Locale.getAvailableLocales` lists languages the app has not translated |
| A14 | Two requests print wrong currencies when sharing a `NumberFormat` |
| A15 | Number parser read a valid prefix and ignored trailing garbage |

### 13.1. Answers and Rationale

| Code | Chosen API / Design | Pitfall to Avoid |
| --- | --- | --- |
| A1 | `LocaleResolver` + `supportedLocales`, pass `Locale` explicitly | Never call `Locale.setDefault` per request |
| A2 | `ResourceBundle` + `MessageFormat`, format values separately | Never hardcode one fixed word order |
| A3 | `NumberFormat.getNumberInstance(Locale.FRANCE)` | Never replace separators manually with regex |
| A4 | `BigDecimal` + `Currency` EUR + currency `NumberFormat` with viewer locale | Never convert EUR to USD automatically |
| A5 | `NumberFormat.getPercentInstance(locale)` with input `0.125` | Never pass `12.5` instead of the ratio |
| A6 | `LocalDate` + localized `DateTimeFormatter` | Never attach a fake timezone to a pure calendar date |
| A7 | `Instant` + each viewer's `ZoneId` + `DateTimeFormatter` | Never use the server's timezone |
| A8 | `Collator.getInstance(vi-VN)`, test with real names | Never use `String.compareTo` as dictionary order |
| A9 | `Normalizer` `NFC` or `NFD` per policy | Never apply `NFKC` blindly to every ID |
| A10 | Locale-appropriate `BreakIterator` | Never use `split(" ")` globally |
| A11 | Renderer bidi/direction/isolation; `java.text.Bidi` when analyzing | Never reverse Strings or swap parentheses manually |
| A12 | Comparator aligned with ID equality, proper strength/tie-breaker | Never equate `compare == 0` with `String.equals` |
| A13 | App `supportedLocales` + coverage QA | Never populate UI menus from all available locales |
| A14 | Create formatter per request or isolate | Never share mutable `NumberFormat` and mutate `Currency` |
| A15 | `ParsePosition`/strict validation, locale-matched parser | Never treat partial parse success as full-string validity |

**Scoring:** each scenario is worth **2 points**: 1 point for naming the right API group, 1 point for naming the pitfall. Maximum **30 points**. If you picked the right API but proposed "reversing strings," "stripping accents," or "swapping currency symbols without converting values," deduct the pitfall point.

## 14. Code Review Exercise: Spot Bugs Before Fixing

The following snippet **intentionally contains bugs** and is not runnable production code:

~~~java
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance();

void show(Order order, Locale locale) {
    Locale.setDefault(locale);
    SHARED.setCurrency(Currency.getInstance(locale));
    String amount = SHARED.format(order.amount());
    String day = order.createdAt().toString();
    String text = "Order " + order.id()
            + ": " + amount + ", " + day;
    System.out.println(text);
}
~~~

Assume `Order` is a domain type exposing `amount()`, `createdAt()`, and `id()`. Focus on reviewing the logic rather than treating it as standalone code. Issues to flag:

1. **`Locale.setDefault(locale)`** mutates global JVM state across other requests.
2. **`SHARED`** is a mutable `NumberFormat`, creating race conditions.
3. **`getCurrencyInstance()` omits the locale**, binding to the default locale at initialization time rather than the active request.
4. **`Currency.getInstance(locale)`** guesses currency from the viewer's region instead of the order's currency; some locales also lack sufficient region data to resolve a currency.
5. **`setCurrency`** only relabels the currency unit without applying an exchange rate.
6. **`createdAt().toString()`** may output a technical `Instant` string rather than local date/time in the recipient's `ZoneId`.
7. **`"Order " + ...`** hardcodes English wording and sentence order.
8. No fallback policy is defined if the app lacks translations.
9. No fraction-digits or rounding policy is defined.
10. No output-channel escaping is applied if the text goes into HTML or email.

### 14.1. Separation-of-Responsibilities Fix

A cleaner design can define clear types and contracts:

~~~java
record PresentationContext(
        Locale uiLocale,
        Locale formatLocale,
        ZoneId zoneId) {}

interface MessageService {
    String render(Locale locale,
                  String key,
                  Object... arguments);
}

interface FormattingService {
    String money(BigDecimal amount,
                 Currency currency,
                 Locale locale);
    String moment(Instant instant,
                  ZoneId zone,
                  Locale locale);
}
~~~

These are **illustrative declarations** requiring imports for `Locale`, `ZoneId`, `BigDecimal`, `Currency`, and `Instant`. They do not form a standalone program. The domain holds **`Order.amount + Order.currency + Order.createdAt`**. A presenter uses the recipient's context to call formatters, then `MessageService` builds the sentence by key. Mutable formatters are created or isolated per call, and the JVM default locale is never modified.

The fix is not just "swapping one method call"—it **enforces boundaries between data, locale selection, formatting, and translation**.

## 15. Ten-Criterion Self-Assessment

Score **0 / 1 / 2 points** per criterion:

- **0:** not met or clear risk present.
- **1:** partially met, missing tests, contracts, or fallback.
- **2:** clean design, tested, and free of implicit environment dependencies.

| Criterion | Self-Assessment Question | Score |
| --- | --- | --- |
| **1. Locale policy** | Does the app have a translated, explicitly selected/fallback locale list? | 0–2 |
| **2. Data model** | Are Amount, Currency, LocalDate, and Instant stored in typed forms? | 0–2 |
| **3. Messages** | Do `ResourceBundle`/`MessageFormat` keys have coverage and placeholder QA? | 0–2 |
| **4. Numbers/money** | Do formatters receive explicit `Locale`, accurate `Currency`, and rounding policy? | 0–2 |
| **5. Date/time** | Are `LocalDate`/`Instant`/`ZoneId` distinguished without using server timezone? | 0–2 |
| **6. Unicode/text** | Are normalization, collation, and boundaries matched to the right problems? | 0–2 |
| **7. RTL/render** | Are bidi, isolation, fonts, and escaping tested where product needs dictate? | 0–2 |
| **8. Concurrency** | Are mutable formatters isolated without setting JVM-wide defaults? | 0–2 |
| **9. Tests** | Are invariants, multi-locale integration, and CLDR/JDK version behavior tested? | 0–2 |
| **10. Operations** | Are metrics/logs tracking missing keys, fallbacks, JDK upgrades, and error reports? | 0–2 |

**Maximum total: 20 points.** Suggested interpretation:

- **0–7:** foundational bugs remain; insufficient basis to claim multi-locale support.
- **8–13:** structure exists but significant risks remain; prioritize financial and temporal areas.
- **14–17:** fairly solid; close remaining testing and operational gaps.
- **18–20:** passes lesson-level assessment; still requires real-world QA per locale, channel, and content.

This scoring is a **training rubric**, not a security/quality certification or substitute for product testing.

### 15.1. Using the Rubric in Pull Requests

During a PR review, reviewers can:

1. List the supported locales affected.
2. Trace the source/type of amounts, timestamps, and message keys.
3. Check whether called APIs receive explicit `Locale`/`ZoneId`/`Currency`.
4. Verify translations exist for new keys and pattern syntax is valid.
5. Search for shared `NumberFormat`/`SimpleDateFormat` singletons.
6. Require tests exercising at least two locales and two time zones.
7. Score against the rubric and list concrete action items for any criterion below 2.

**Never treat 20/20 as covering all accessibility, legal, or linguistic translation requirements.** This checklist catches common technical localization defects and must pair with local content QA.

## 16. Classifying Bug Severity

Not all localization bugs carry equal priority.

| Severity | Examples | Impact |
| --- | --- | --- |
| **Critical** | Swapping currency code without exchange-rate conversion; leaking user data via message cache; injection vulnerabilities | Wrong money / security breach |
| **High** | Wrong payment date due to timezone; dropped records from `TreeSet` comparator; misparsed monetary separators | Broken business logic or data loss |
| **Medium** | `ResourceBundle` falls back to wrong language; confusing negative/unit formatting; scrambled RTL punctuation | User confusion, poor usability |
| **Low** | Unnatural label phrasing, minor spacing or capitalization inconsistency against style guide | UX polish and consistency |

**Actual severity depends on the application.** A date bug on a personal calendar might be Medium, whereas a date bug on a payment deadline or medication schedule can be Critical. Judge by business impact and likelihood, not by API name alone.

Never patch a Critical bug with a quick `String.replace` while ignoring the data contract. Fix it at the proper source layer and add regression tests.

## 17. Combined Test Matrix

| Scenario | Input | Stable Assertion | Runtime QA Check |
| --- | --- | --- | --- |
| `vi-VN` vs. `en-US` | `BigDecimal("1234.50")` | Underlying value preserved | Grouping/decimal separators |
| EUR in `en-US` | EUR amount | Currency code `EUR` | Symbol and placement |
| Tax | Ratio `0.125` | `0.125` unchanged | `%` and digit count |
| Pure date | `LocalDate` `2026-10-28` | `LocalDate` unchanged | Pattern/month name |
| Instant in two zones | Fixed `Instant` | `toInstant()` equal | Local time per `tzdb` |
| Unicode NFC | `é` and `e` + combining | NFC forms match | Fonts not asserted as data |
| `Collator` `vi-VN` | Names with `ă`/`â`/`đ` | Valid comparator contract | Exact rule-driven order |
| `BreakIterator` | Text with diacritics/emojis | Valid boundary indices | Linguistic boundaries |
| Bidi | LTR ID in RTL sentence | Logical string intact | Renderer/punctuation |
| `ResourceBundle` | Present/missing keys | Explicit fallback policy | Translated copy |
| HTML | Untrusted user name | Properly escaped | Direction/font rendering |
| JDK/CLDR upgrade | Same dataset | Source values unchanged | Locale output updates |
| Multithreading | Multiple locales/currencies | No shared mutable formatters | Concurrent output parity |

### 17.1. Avoid Snapshotting Every Character Unnecessarily

When formatting an amount in `fr-FR`, spacing can be **U+00A0** or **U+202F** depending on runtime data. Asserting **`String.equals`** makes sense when a product pins runtime versions and requires exact byte-for-byte output; however, if a test only intends to prove the source `Currency` stayed intact, never tie that invariant test to a CLDR-dependent string snapshot.

Split tests into:

- **Business unit tests:** `BigDecimal`, `Currency`, `Instant`, `LocalDate`.
- **Locale selection unit tests:** `supportedLocales` and fallback.
- **Service integration tests:** `NumberFormat`, `DateTimeFormatter`, `Collator`, `BreakIterator`.
- **Localization QA:** bundle coverage, grammar, text expansion, placeholder structure.
- **Visual/accessibility QA:** fonts, RTL, punctuation, HTML/PDF/email.
- **Security tests:** escaping, bidi controls in technical IDs, user input handling.

## 18. Multiple-Choice Self-Assessment Quiz

Pick the single best answer for each question. Answers appear in the next section.

**Question 1.** An app supports `vi-VN` and `en-US`; the user requests `fr-CA`, which has no translation. What is the best behavior?

A. Call `Locale.setDefault(fr-CA)` so everything translates automatically.

B. Select a supported locale according to an explicit, documented fallback policy.

C. Call `Locale.getAvailableLocales()` to treat `fr-CA` as already translated.

D. Prepend a French prefix to every English sentence.

**Question 2.** An order records `100 EUR`, and the viewer is in the United States. What is the right action?

A. Automatically change `Currency` to `USD` because of `Locale.US`.

B. Keep the transaction's `EUR` `Currency` and format it under `Locale.US` if appropriate.

C. Call `Currency.getInstance(Locale.US)` and overwrite the source data.

D. Strip `Currency` and print only `100`.

**Question 3.** You need to sort a list of names in Vietnamese dictionary order. What should you choose?

A. `String.compareTo`.

B. `StringBuilder.reverse`.

C. `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` with tests.

D. `Integer.parseInt` on the Strings.

**Question 4.** A UTC timestamp converted to California time can fall on a different calendar date; what should you use?

A. `LocalDate.toString` without a zone.

B. `Instant` + `ZoneId` + `DateTimeFormatter`.

C. `Locale.setDefault(Locale.US)`.

D. `Currency.getInstance`.

**Question 5.** Precomposed `é` and decomposed `e` + combining acute need canonical-equivalence comparison; what should you use?

A. `Normalizer` NFC on both strings, then compare.

B. `String.compareToIgnoreCase` suffices for all Unicode.

C. Strip all accents before storing.

D. Merely change the font.

**Question 6.** A `static` singleton `NumberFormat` has `setCurrency` called per request; what is the main issue?

A. `NumberFormat` is immutable, so there is no issue.

B. Locales have no `Currency`.

C. Mutable formatters suffer race conditions and cross-request configuration leaks.

D. The JVM always rejects any `Currency` other than default.

**Question 7.** A numeric input form uses `NumberFormat.parse`; what else must be verified?

A. Parsing a valid prefix is sufficient for any input.

B. All NBSP characters must be banned globally.

C. `ParsePosition` consumes the full input per policy, plus numeric precision and returned type.

D. Replace the parser with `String.compareTo`.

**Question 8.** An Arabic name segment inside an English sentence scrambles surrounding parentheses. What should you do?

A. Reverse the String.

B. Mutate the data by swapping every `'('` to `')'`.

C. Use proper paragraph direction/isolation and bidi-capable rendering.

D. Swap `NumberFormat`.

**Question 9.** `ResourceBundle.getBundle` returns the base bundle for `fr-CA`; what does that prove?

A. The app has complete `fr-CA` translations.

B. Only that a resource was found via lookup/fallback.

C. The default timezone is in Canada.

D. The currency must be `CAD`.

**Question 10.** Technical order IDs must be compared in a fixed protocol-defined order regardless of viewer dictionary rules. What should you choose?

A. Use `Collator` with the viewer's `Locale` for all IDs.

B. Use the protocol-defined technical comparison, such as `String.compareTo` or byte order per contract.

C. Use `MessageFormat`.

D. Strip all digits.

### 18.1. Answers with Explanations

| Question | Answer | Rationale |
| --- | --- | --- |
| 1 | **B** | App-supported languages are a product policy, not whatever the JDK contains |
| 2 | **B** | `EUR` is the transaction's unit; `Locale.US` governs only presentation |
| 3 | **C** | `Collator` applies linguistic order; `compareTo` compares UTF-16 code units |
| 4 | **B** | `Instant` captures the moment; `ZoneId` yields local wall-clock time |
| 5 | **A** | `NFC` resolves canonical equivalence |
| 6 | **C** | `NumberFormat` is mutable and must not be mutated concurrently |
| 7 | **C** | Parsing may stop early or lose precision without explicit checks |
| 8 | **C** | Bidi/layout handles visual direction without corrupting logical order |
| 9 | **B** | `ResourceBundle` fallback never proves translation completeness |
| 10 | **B** | Technical IDs require a stable contract independent of the viewer |

**Score 1 point per question**, out of 10. If you missed questions 2, 4, 6, or 7, prioritize reviewing **data correctness**, since those bugs cause worse damage than visual layout glitches.

## 19. Real-Project Review Checklist

### Data and Contracts

- [ ] Monetary values are stored as `BigDecimal` + `Currency`, never as localized Strings.
- [ ] `Currency` and `ZoneId` are never inferred solely from `Locale`.
- [ ] Pure calendar dates and absolute instants use the proper distinct types.
- [ ] IDs and business codes retain logical character order when displayed.
- [ ] Machine data uses documented technical formats rather than arbitrarily parsing localized display strings.

### Language, Formatting, and Unicode

- [ ] App-supported locales have real translations and QA, not the entire JDK available list.
- [ ] `Locale` is passed explicitly to formatters without mutating JVM default per request.
- [ ] `ResourceBundle` has an explicit fallback policy plus key/placeholder checks.
- [ ] `MessageFormat` patterns properly handle apostrophes, braces, and argument ordering.
- [ ] `NumberFormat`/`Currency`/percentages receive proper inputs and rounding policies.
- [ ] `DateTimeFormatter`/`ZoneId` match pure-date vs. instant needs accurately.
- [ ] `Collator`/`Normalizer`/`BreakIterator` are matched to their respective problems.
- [ ] RTL text uses proper layout/isolation rather than reversing Strings.
- [ ] Unicode NBSP/NNBSP and special code points are tested where relevant.

### Operations and Security

- [ ] Mutable `NumberFormat`/`MessageFormat` instances are never shared and mutated concurrently.
- [ ] Messages containing user-specific data are never cached solely by translation key.
- [ ] Proper escaping is applied for HTML/email/URL sinks rather than mistaking `MessageFormat` for sanitization.
- [ ] Tests cover multiple locales, time zones, and threads.
- [ ] Regression tests run for JDK/CLDR/`tzdb` upgrades.
- [ ] Pagination and database queries use consistent collation and tie-breakers.
- [ ] Logs/metrics surface missing translations, fallbacks, and formatting errors.

## 20. Applying the Matrix in a New Design

A six-step workflow:

**Step 1 — Define source data.** Specify exact amount/ratio, `Currency`, `LocalDate`/`Instant`, IDs, and message keys. Avoid identifying business values from localized strings.

**Step 2 — Define recipient context.** Capture `uiLocale`, `formatLocale`, `ZoneId`, and rendering channel (web/email/PDF); never collapse them into a single attribute.

**Step 3 — Consult the API matrix.** Pick the right API for each value and operation. When a sentence includes names and money, you need `Collator` for sorting, `NumberFormat` for formatting, and `ResourceBundle`/`MessageFormat` for assembling the message—never conflate their roles.

**Step 4 — Define fallback and failure behavior.** Specify upfront how missing translations, unsupported locales, malformed patterns, and incomplete parses behave.

**Step 5 — Test at two levels.** Assert invariant data and deterministic API behaviors with exact stdout; verify locale-specific outputs on the target runtime/provider. Pair with visual tests for Unicode and bidi.

**Step 6 — Review risks.** Score using the 0–20 rubric, prioritizing wrong money/dates, corrupted identifiers, and security bugs over cosmetic polish. Add regression tests before release.

## 21. Summary

**Choosing the right localization API in Java means matching the semantics of the problem.** **`Locale`** identifies language/region; **`ResourceBundle`/`MessageFormat`** assemble messages; **`NumberFormat`/`Currency`/`BigDecimal`** preserve numbers and money; **`LocalDate`/`Instant`/`ZoneId`/`DateTimeFormatter`** handle dates and instants; **`Collator`/`Normalizer`/`BreakIterator`** address distinct text-processing concerns; and **`Bidi`** plus renderers handle visual direction.

The API matrix prevents misusing convenient methods in the wrong layer; exercises, answers, and the rubric help you spot recurring mistakes on your own. The success of a multilingual product lies not in how many APIs it calls, but in **keeping business data exact, prose natural for users, fallbacks transparent, Unicode intact, and tests reproducible on the real deployment environment**.
