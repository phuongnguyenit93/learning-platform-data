# The Two Categories `Locale.Category.DISPLAY` and `Locale.Category.FORMAT` in Java

In a multilingual application, a user might want to **read language/country names in Vietnamese** while **displaying numbers and dates according to German conventions**. These two needs do not necessarily have to use the same `Locale`. Java provides two default categories in `java.util.Locale.Category`: `DISPLAY` and `FORMAT`.

Core takeaway of this lesson: **`DISPLAY` controls the default locale for operations that produce display names**, while **`FORMAT` controls the default locale for formatting operations designed to use this category**. Both are **JVM-level** default settings, not per-user or per-HTTP-request configurations.

## 1. Why Does Java Need Two Default Categories?

Consider a settings screen with the following parts:

- A list of countries/languages: `Germany`, `France`, `Vietnamese`, or equivalent names in the UI language.
- A numeric value: `12345.67`, which may be displayed using regional thousand/decimal separators.
- A date: 28/10/2026, which may be presented using regionally appropriate order, wording, and symbols.

The language used to **name** a country is one choice; the rules used to **present** numbers and dates are another choice. A JVM also has a **general default locale** for APIs that do not specify a category. Therefore, you must know which call actually reads which default.

| Value/default | Reading API | Primary purpose | Usage examples |
| --- | --- | --- | --- |
| **General default** (no category) | `Locale.getDefault()` | Common default for APIs using the general default | `ResourceBundle.getBundle("messages")` uses the general default when no locale is passed |
| **DISPLAY** | `Locale.getDefault(Locale.Category.DISPLAY)` | Preferred language/region for *expressing names* in display-name APIs | `target.getDisplayName()`, `getDisplayLanguage()`, `getDisplayCountry()` |
| **FORMAT** | `Locale.getDefault(Locale.Category.FORMAT)` | Preferred regional conventions when *formatting* via supported APIs | `NumberFormat.getNumberInstance()`, `NumberFormat.getCurrencyInstance()` |

`Locale.Category` is an enum with two constants: `DISPLAY` and `FORMAT`. They **categorize the purpose of the default**, rather than being two new kinds of locale objects: all three `getDefault(...)` calls still return ordinary `Locale` objects.

### Viewing It as a Selection Flow

```text
                 JVM
                  |
        +---------+----------+
        |         |          |
 general default  DISPLAY    FORMAT
        |         |          |
  APIs using    Language/   Numbers, money,
  general       region      dates & times
  default       display     (respective APIs)
        |       names        |
        |         |          |
  getDefault()  getDisplayName()  NumberFormat.getNumberInstance()
```

Not every localization-related API automatically uses `DISPLAY` or `FORMAT`. You must check the contract of **each method**. If an explicit `Locale` is passed, APIs normally prioritize the passed object over the global defaults.

## 2. Reading Each Category's Default

The three calls below can return **three different locales**:

```java
Locale base = Locale.getDefault();

Locale display = Locale.getDefault(
        Locale.Category.DISPLAY);

Locale format = Locale.getDefault(
        Locale.Category.FORMAT);
```

This is a **code snippet inside a method**, requiring `import java.util.Locale;`. Do not treat `Locale.getDefault()` as a guaranteed alias for `Locale.getDefault(Locale.Category.FORMAT)` or `DISPLAY`: they may match in one environment, but there is no requirement that they always match.

Java 17+ program that prints the three active locales — file `InspectDefaultLocale.java`:

```java
import java.util.Locale;

public class InspectDefaultLocale {
    public static void main(String[] args) {
        Locale general = Locale.getDefault();
        Locale display = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale format = Locale.getDefault(
                Locale.Category.FORMAT);

        System.out.println("General: " + general.toLanguageTag());
        System.out.println("DISPLAY: " + display.toLanguageTag());
        System.out.println("FORMAT: " + format.toLanguageTag());
        System.out.println("DISPLAY == FORMAT: "
                + display.equals(format));
    }
}
```

```bash
javac InspectDefaultLocale.java
java InspectDefaultLocale
```

This example **has no fixed stdout** because defaults are established by the JVM at startup based on host/environment configuration. One machine may print the same tag on all three lines; another machine may print different ones. The last line compares `Locale` values, not object identity with `==`.

When inspecting the actual state on a server, always observe each category directly. Do not conclude `DISPLAY` and `FORMAT` are the same just because `Locale.getDefault()` returns a familiar value.

## 3. DISPLAY: Language for Expressing a Locale's Name

The target object whose name is requested and the locale used to express that name play **two different roles**:

```java
Locale target = Locale.forLanguageTag("ja-JP");
Locale uiLocale = Locale.forLanguageTag("vi-VN");

String implicitLabel = target.getDisplayName();
String explicitLabel = target.getDisplayName(uiLocale);
```

- `target` is the locale being named: Japanese in Japan.
- `target.getDisplayName()` defaults to expressing the name using `Locale.getDefault(Locale.Category.DISPLAY)`.
- `target.getDisplayName(uiLocale)` expresses the name in `vi-VN` according to the runtime's localization data, **independent** of the current DISPLAY default.
- Both only retrieve a string for display; they **do not modify** `target` and do not turn a Japanese locale into a Vietnamese locale.

In the same group of no-argument methods: `getDisplayLanguage()`, `getDisplayScript()`, `getDisplayCountry()`, `getDisplayVariant()`. The overloads taking a `Locale inLocale` parameter allow choosing a specific display language.

**Note:** display labels can vary across JDK versions, locale providers/CLDR data, and fallbacks when a translation is absent. The value of `getDisplayName()` is **presentation data** and should not be used as an ID, database key, or persistent value of a preference. Store `target.toLanguageTag()` when an identifier is needed.

### Example

Suppose the DISPLAY default is `en-US` and `target` is `fr-CA`:

```java
Locale target = Locale.forLanguageTag("fr-CA");
String label = target.getDisplayName();
```

The string may be equivalent to “French (Canada)” in English; with a DISPLAY default of `vi-VN`, the label is expressed in Vietnamese when supporting data is available. Naming a locale **does not determine** how thousands are grouped or how currency is displayed, as that is the formatter's responsibility.

## 4. FORMAT: Regional Conventions for Formatting

`NumberFormat` methods without a locale parameter use the `FORMAT` default. According to Java's contract:

```java
NumberFormat byDefault = NumberFormat.getNumberInstance();

NumberFormat equivalent =
        NumberFormat.getNumberInstance(
                Locale.getDefault(Locale.Category.FORMAT));
```

Both formatters use the same effective locale at creation time, so when formatting the same number under the default configuration, the resulting strings must be equal. The returned formatter objects are not necessarily the same instance.

Commonly used API examples:

| Purpose | Uses FORMAT default | Specifies explicit Locale |
| --- | --- | --- |
| Regular numbers | `NumberFormat.getNumberInstance()` | `NumberFormat.getNumberInstance(locale)` |
| Currency | `NumberFormat.getCurrencyInstance()` | `NumberFormat.getCurrencyInstance(locale)` |
| Percentages | `NumberFormat.getPercentInstance()` | `NumberFormat.getPercentInstance(locale)` |
| `java.text` date formatting | `DateFormat.getDateInstance()` | `DateFormat.getDateInstance(style, locale)` |
| `java.time` date formatting | `DateTimeFormatter.ofLocalizedDate(style)` reads the FORMAT default when creating the formatter | `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)` |

When using `java.time`, passing an explicit locale keeps date formatting clear and consistent with the user's request. `FORMAT` **is not a time zone**; actual date-times also need a `ZoneId` when an instant in time is involved.

Data can be formatted in the same language but a different region: `en-US` and `en-GB` may differ in date and currency presentation; `de-DE` and `en-US` differ in number rules. Do not hard-code a single example output string as a contract across all JDK versions and all locale data providers.

### FORMAT Does Not Choose the Transaction Currency

`NumberFormat.getCurrencyInstance(formatLocale)` normally selects the default currency associated with the region; the **business currency** (USD, EUR, VND...) must be passed/managed independently. For real monetary values, you can configure `formatter.setCurrency(Currency.getInstance("USD"))` after choosing the presentation style. Decimal places, rounding, and currency policies must be handled according to business requirements, not inferred from the locale.

## 5. Example Verifying the Two Categories Work Independently

**File `CategoryDefaultsDemo.java`, runnable on Java 17+:**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CategoryDefaultsDemo {
    public static void main(String[] args) {
        Locale oldGeneral = Locale.getDefault();
        Locale oldDisplay = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale oldFormat = Locale.getDefault(
                Locale.Category.FORMAT);

        Locale enUS = Locale.forLanguageTag("en-US");
        Locale deDE = Locale.forLanguageTag("de-DE");
        Locale target = Locale.forLanguageTag("fr-CA");

        try {
            Locale.setDefault(Locale.Category.DISPLAY, enUS);
            Locale.setDefault(Locale.Category.FORMAT, deDE);

            System.out.println("General unchanged: "
                    + Locale.getDefault().equals(oldGeneral));
            System.out.println("DISPLAY: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("FORMAT: "
                    + Locale.getDefault(
                            Locale.Category.FORMAT).toLanguageTag());

            String implicitName = target.getDisplayName();
            String explicitName = target.getDisplayName(enUS);
            System.out.println("Name uses DISPLAY: "
                    + implicitName.equals(explicitName));

            String implicitNumber =
                    NumberFormat.getNumberInstance()
                            .format(12345.67);
            String explicitNumber =
                    NumberFormat.getNumberInstance(deDE)
                            .format(12345.67);
            System.out.println("Number uses FORMAT: "
                    + implicitNumber.equals(explicitNumber));
        } finally {
            Locale.setDefault(oldGeneral);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
        }
    }
}
```

Compile/run:

```bash
javac CategoryDefaultsDemo.java
java CategoryDefaultsDemo
```

**Exact stdout** when the example runs single-threaded and no external code concurrently alters JVM defaults:

```text
General unchanged: true
DISPLAY: en-US
FORMAT: de-DE
Name uses DISPLAY: true
Number uses FORMAT: true
```

**Analysis:**

1. `setDefault(DISPLAY, enUS)` updates *only the DISPLAY category default*.
2. `setDefault(FORMAT, deDE)` updates *only the FORMAT category default*.
3. General `getDefault()` keeps its initial value because the `setDefault(Locale)` overload was not called.
4. `target.getDisplayName()` is equivalent to requesting the name in `en-US` — **the DISPLAY default**.
5. `NumberFormat.getNumberInstance()` is equivalent to a formatter created for `de-DE` — **the FORMAT default**.
6. `finally` restores the three defaults so the demo program does not intentionally leave the new configuration active afterward.

This is an **illustrative example in an isolated process**. Changing default locales is a **JVM-wide** operation, unsafe to use as a per-HTTP-request language selection mechanism. Even with restoration in `finally`, another thread running **concurrently** can still observe the temporary values. In tests, avoid running examples that mutate globals in parallel with tests that depend on defaults; ideally run in a separate process if isolation is required.

## 6. Differences Between `setDefault(Locale)` and `setDefault(Category, Locale)`

Java provides two ways to set defaults:

```java
Locale.setDefault(newLocale);
Locale.setDefault(Locale.Category.DISPLAY, displayLocale);
Locale.setDefault(Locale.Category.FORMAT, formatLocale);
```

Here `newLocale`, `displayLocale`, and `formatLocale` are `Locale` variables already declared in context — this shows **usage signatures**, not a standalone program.

| Method | General default | DISPLAY | FORMAT |
| --- | --- | --- | --- |
| `Locale.setDefault(newLocale)` | Updated | Updated | Updated |
| `Locale.setDefault(DISPLAY, locale)` | Unchanged | Updated | Unchanged |
| `Locale.setDefault(FORMAT, locale)` | Unchanged | Unchanged | Updated |

Because `setDefault(Locale)` overwrites **both categories**, setting `DISPLAY=en-US` and `FORMAT=de-DE` first and then calling `Locale.setDefault(Locale.forLanguageTag("fr-FR"))` will turn all three into `fr-FR`. Do not use the general overload if you only want to change one category.

**Standalone example — `ResetCategoriesDemo.java`:**

```java
import java.util.Locale;

public class ResetCategoriesDemo {
    public static void main(String[] args) {
        Locale oldBase = Locale.getDefault();
        Locale oldDisplay = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale oldFormat = Locale.getDefault(
                Locale.Category.FORMAT);

        try {
            Locale.setDefault(
                    Locale.Category.DISPLAY,
                    Locale.forLanguageTag("en-US"));
            Locale.setDefault(
                    Locale.Category.FORMAT,
                    Locale.forLanguageTag("de-DE"));

            Locale.setDefault(Locale.forLanguageTag("fr-FR"));

            System.out.println(Locale.getDefault().toLanguageTag());
            System.out.println(Locale.getDefault(
                    Locale.Category.DISPLAY).toLanguageTag());
            System.out.println(Locale.getDefault(
                    Locale.Category.FORMAT).toLanguageTag());
        } finally {
            Locale.setDefault(oldBase);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
        }
    }
}
```

```bash
javac ResetCategoriesDemo.java
java ResetCategoriesDemo
```

Stdout:

```text
fr-FR
fr-FR
fr-FR
```

This explains a common configuration bug: initializing `DISPLAY`/`FORMAT` separately and then calling `setDefault(Locale)` in another library or bootstrap code, unintentionally wiping out the two configured choices.

### Formatter Creation Timing

Defaults are read **when the API uses them**. For example, `NumberFormat.getNumberInstance()` creates a formatter with the locale in effect at the time of the call. Changing `FORMAT` afterward is not a command instructing all existing formatters to update themselves. You must recreate or reconfigure the appropriate formatter; also avoid sharing a stateful mutable `java.text.NumberFormat` across multiple threads.

## 7. Initial Setup at JVM Startup

When the JVM starts, Java establishes the default locale based on environment configuration and relevant system properties. Beyond base properties such as `user.language` and `user.country`, Java also has category-specific components such as:

- `user.language.display`, `user.country.display` for the DISPLAY category.
- `user.language.format`, `user.country.format` for the FORMAT category.

Example command line launching the program from section 2 with the requested values (exact handling of properties depends on JDK initialization rules):

```bash
java -Duser.language=en -Duser.country=US -Duser.language.display=vi -Duser.country.display=VN -Duser.language.format=de -Duser.country.format=DE InspectDefaultLocale
```

With a JDK that follows these initialization properties, the configuration intent is: general default `en-US`, DISPLAY `vi-VN`, FORMAT `de-DE`. Do not guess the actual default in a specific runtime without checking via `Locale.getDefault(...)`.

**Important:** changing `System.setProperty("user.language.format", "de")` **after the JVM has initialized its defaults** is not a reliable mechanism for changing the active default `Locale`. If there is a need to switch defaults at runtime, the corresponding API is `Locale.setDefault(...)`. However, because of its process-wide effect, an application serving multiple users should normally pass locales **explicitly** and only configure defaults at a controlled bootstrap point.

Additionally, locale does not determine `ZoneId.systemDefault()` or each user's time zone. Language/region and time zone must be managed as independent choices.

## 8. How to Write Multi-User Applications: Pass Explicit Locales

For a web server, handling two consecutive requests with different `uiLocale` and `formatLocale` **should not modify JVM defaults** before rendering each page. Instead, determine the two locales from the user/request settings and pass them into each API.

**File `ExplicitLocalePerRequestDemo.java` — Java 17+:**

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.List;
import java.util.Locale;

public class ExplicitLocalePerRequestDemo {
    record View(String user, Locale display, Locale format) {}

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("fr-CA");
        double amount = 12345.67;
        LocalDate date = LocalDate.of(2026, 10, 28);

        List<View> views = List.of(
                new View(
                        "A",
                        Locale.forLanguageTag("vi-VN"),
                        Locale.forLanguageTag("de-DE")),
                new View(
                        "B",
                        Locale.forLanguageTag("en-GB"),
                        Locale.forLanguageTag("en-US")));

        for (View view : views) {
            String name = target.getDisplayName(view.display());

            NumberFormat numberFormat =
                    NumberFormat.getNumberInstance(view.format());
            String number = numberFormat.format(amount);

            String dateText = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.MEDIUM)
                    .withLocale(view.format())
                    .format(date);

            System.out.println("User: " + view.user());
            System.out.println("Display locale: "
                    + view.display().toLanguageTag());
            System.out.println("Format locale: "
                    + view.format().toLanguageTag());
            System.out.println("Locale name: " + name);
            System.out.println("Number: " + number);
            System.out.println("Date: " + dateText);
        }
    }
}
```

```bash
javac ExplicitLocalePerRequestDemo.java
java ExplicitLocalePerRequestDemo
```

The program always prints **12 lines**: 6 lines for A, followed by 6 lines for B. The headers and locale tags are fixed:

```text
User: A
Display locale: vi-VN
Format locale: de-DE
...
User: B
Display locale: en-GB
Format locale: en-US
...
```

The `...` in the block above **only indicates the omission of the three name/number/date lines for each user, not the complete stdout**. The remaining three lines are prefixed with `Locale name:`, `Number:`, and `Date:` with values generated by the JDK according to its current locale data. Do not hard-code localized number/date strings across different JDKs/CLDR versions. The main benefit is that requests do not write to global defaults, do not interfere with one another, and the code states responsibilities clearly: names via `display`, formatting via `format`.

In a larger application, you can group the request's choices in an immutable context object and pass it to the rendering service; if two separate choices are not needed, both fields can hold the same locale. When a request lacks a preference, apply the defined **application fallback**, rather than defaulting every user to the server's locale.

## 9. APIs Commonly Misunderstood Regarding Categories

You cannot guess a method's category from its class name thinking "it looks UI-related so it uses DISPLAY". For example:

| Call | Which default does it read? | Recommendation |
| --- | --- | --- |
| `locale.getDisplayName()` | DISPLAY | Use `getDisplayName(uiLocale)` when the viewer's locale is known |
| `locale.getDisplayLanguage()` | DISPLAY | Language name, not the `getLanguage()` code |
| `NumberFormat.getInstance()` | FORMAT | Use `getInstance(formatLocale)` when the formatting locale is known |
| `NumberFormat.getCurrencyInstance()` | FORMAT | Remember transaction currency is separate |
| `DateFormat.getDateInstance()` | FORMAT | Use the locale-taking overload when rendering per user |
| `ResourceBundle.getBundle("messages")` | **General** default | Use `getBundle("messages", uiLocale)` when selecting resources per user |
| `Locale.getDefault()` | General | Does not replace DISPLAY/FORMAT defaults |
| `Locale.forLanguageTag("de-DE")` | Does not use JVM defaults to pick this tag | Creates an explicit locale |

`ResourceBundle` is an important example: even though it supplies UI display strings, the `getBundle(baseName)` overload uses the general `Locale.getDefault()`, **not automatically DISPLAY**. Thus, setting `Locale.Category.DISPLAY` does not automatically ensure all application messages switch to that language. Translation resources must be selected explicitly according to the application's i18n and fallback mechanism.

Another mistake is treating date formatting as if it also carries a time zone. For a pure calendar date `LocalDate`, formatting only changes the presentation style; for an `Instant`, a `ZoneId` time zone must be selected before presenting local time. `FORMAT` and `DISPLAY` do not store instant or time zone information.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Assuming `getDefault()`, `getDefault(DISPLAY)`, and `getDefault(FORMAT)` are always equal | Categories can be configured independently | Inspect and pass the right category |
| Calling `setDefault(Locale)` just to change FORMAT | This overload also changes the general default and DISPLAY | If you must change one category's default, use the `Category` overload |
| Changing `Locale.setDefault(...)` inside each HTTP request | JVM-wide effect; other threads may read another request's value | Pass explicit locales |
| Believing `getDisplayName()` uses the target locale's own language | It uses the DISPLAY default | Call `getDisplayName(target)` if you truly want an endonym (self-name) |
| Assuming `DISPLAY` governs `ResourceBundle.getBundle(baseName)` | The no-locale overload uses the general default | Pass the locale to `getBundle` |
| Calling `NumberFormat.getNumberInstance()` and expecting it to follow DISPLAY | It uses FORMAT | Pass `formatLocale` explicitly or configure FORMAT properly |
| Changing the default and expecting old formatters to update | Already-created formatters have their own state | Recreate with the appropriate locale |
| Using translated display names as IDs | Display names can change by language/JDK | Store `toLanguageTag()` |
| Assuming FORMAT determines the time zone | Locale and timezone are two distinct concepts | Manage `ZoneId` separately |
| Writing tests asserting exact localized strings across all JDKs | Locale/provider data can change | Test behavior/selected locale; pin runtime if snapshots are mandatory |
| Incomplete restoration of defaults in tests | Can skew subsequent tests | Record general, DISPLAY, and FORMAT and restore them in `finally`; do not run in parallel |

## 11. Recommended Tests to Implement

A meaningful test suite for an i18n application should verify:

1. When DISPLAY is set to `en-US` and FORMAT to `de-DE`, `getDisplayName()` matches the overload with `en-US`, while `NumberFormat.getNumberInstance()` matches the overload with `de-DE`.
2. Setting the DISPLAY category alone does not change the value read from general `getDefault()` or FORMAT, and likewise for FORMAT.
3. Calling `setDefault(Locale)` causes general, DISPLAY, and FORMAT to all receive the new locale.
4. When passing explicit locales per request, two users A and B can view names in different languages while formatting the same value according to their own regions; neither needs to alter defaults.
5. When testing code that alters global defaults, restore the values in `finally` and control parallel execution. Example tests do not replace process-isolated tests on real systems.
6. Test startup default locales and the message translation system separately: code calling `ResourceBundle.getBundle(baseName)` and code calling `getDisplayName()` may use two different defaults.

### Practice Exercises

**Exercise 1.** Write a program that prints `getDefault()`, `getDefault(DISPLAY)`, and `getDefault(FORMAT)`; use startup options to request different locales. Observe on the runtime you are using and explain why the three values may not be identical.

**Exercise 2.** Given `target=Locale.forLanguageTag("ja-JP")`, retrieve its name in display locales `vi-VN` and `en-US`, while formatting the same number in `de-DE` and `en-US`. Do not change `Locale.setDefault`. Explain which API takes the display locale and which API takes the format locale.

**Exercise 3.** Fix a hypothetical web program that calls `Locale.setDefault(userLocale)` inside a request handler. Refactor the design into two parameters `displayLocale` and `formatLocale` passed to a renderer. Write a test proving two requests with different locales do not write to the global default.

**Principle solutions:** Exercise 1 checks each category individually; Exercise 2 passes explicit `Locale` arguments to `getDisplayName` and `NumberFormat`; Exercise 3 separates user context from JVM defaults without mutating process-wide state.

## 12. Reference Documentation

- [JDK 21 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Category`, `getDefault`, `setDefault`, `getDisplayName`.
- [JDK 21 — `java.text.NumberFormat`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): factories using the `FORMAT` default and overloads taking `Locale`.
- [JDK 21 — `java.util.ResourceBundle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): bundle selection using the default locale or an explicitly passed locale.

## 13. Key Takeaway

**`DISPLAY` answers “which language/region should be used to name locales?”; `FORMAT` answers “which regional conventions should be used to present data?”**. Java also has a **general** default, so you must choose the right API overload. `Locale.setDefault(Locale)` changes all three; `setDefault(Category, Locale)` changes only one group, yet still affects the entire JVM. In multi-user applications, pass explicit `Locale` values to display and formatting APIs so each request stays independent, easy to test, and deterministic in behavior.
