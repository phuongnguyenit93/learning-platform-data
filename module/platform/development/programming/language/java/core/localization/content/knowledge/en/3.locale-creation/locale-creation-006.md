# Display Names with `Locale.getDisplayName()` and the Locale Used to Display Names

When a Java application displays a list of languages or regions for users to choose from, it needs to turn codes like `en-US`, `fr-CA`, or `zh-Hant-TW` into **human-readable names**. Java provides `java.util.Locale.getDisplayName()` for that task. The most important point: **the Locale being named** and **the Locale used as the display language** play two different roles.

For example, the same `Locale.forLanguageTag("de-DE")` object can be presented in German in a German UI or in English in an English UI. The locale object still represents the German language in Germany; only the language of the **display label** changes.

## 1. Two Roles of Locale: The Subject Being Described and the Describing Language

Suppose:

- **Target / subject locale:** `fr-CA`, meaning French in the Canada region. This is the object whose name we want to obtain.
- **Display locale (`inLocale`):** `en-US`, meaning asking Java to express that name in English according to supported local conventions.

The code snippet:

```java
Locale target = Locale.forLanguageTag("fr-CA");
Locale displayLocale = Locale.forLanguageTag("en-US");

String label = target.getDisplayName(displayLocale);
```

is **an illustrative snippet**, which must be placed inside a method and have `import java.util.Locale;` to compile. It means: “get the name of `fr-CA` for display in the language/region of `en-US`”. The call **does not mutate** `target`, nor does it convert the object's translated content or region into `en-US`.

Mental model:

```text
Target locale:       fr-CA        (The object being named)
Display locale:      en-US        (Language expressing the label)
                    ↓
target.getDisplayName(displayLocale)
                    ↓
Readable display name in English, such as French (Canada)
```

The phrase “such as” above is intentional: the exact wording of the display name depends on locale/provider data in the JDK.

**Distinguishing three kinds of values:**

| Retrieval Method | Purpose | Depends on Display Locale? |
| --- | --- | --- |
| `target.toLanguageTag()` | BCP 47 code for storage or transmission, e.g., `fr-CA` | No |
| `target.getLanguage()` and `target.getCountry()` | Language/region component codes, e.g., `fr`, `CA` | No |
| `target.getDisplayName(displayLocale)` | User-friendly name | Yes: depends on `displayLocale` and JDK data |
| `target.getDisplayName()` | Name using the JVM's **default DISPLAY locale** | Yes: depends on the process default |

**Usage rule:** for identifier data use `toLanguageTag()` or the `Locale` object; for content presented in the UI use `getDisplayName(...)`.

## 2. Two Overloads of `getDisplayName`

`Locale` has two central methods:

```java
String getDisplayName();
String getDisplayName(Locale inLocale);
```

These are **illustrative API signatures**, not a standalone Java program.

### `getDisplayName()` — Uses the Default Locale for Display

The no-argument method uses the **default locale of category `Locale.Category.DISPLAY`**. Because a JVM can run on different machines, under different configurations, or be changed by another part of the application, two runs in different environments can produce labels in different languages.

```java
Locale target = Locale.forLanguageTag("de-DE");
String label = target.getDisplayName();
```

If the DISPLAY default is English, the label may be in English; if the DISPLAY default is French, the label may be in French. Do not assume calling `target.getDisplayName()` means “display in German itself” or “display in the current accessing user's language”.

### `getDisplayName(Locale inLocale)` — Uses an Explicit Display Locale

The parameterized version expresses the name of the **receiver object** according to `inLocale`. This is usually the clearer choice for an interface serving multiple users concurrently on one server:

```java
Locale target = Locale.forLanguageTag("de-DE");
Locale viewer = Locale.forLanguageTag("vi-VN");
String labelForViewer = target.getDisplayName(viewer);
```

The application can switch `viewer` to `en-GB` or `fr-FR` for another request without changing global settings. If `inLocale` lacks corresponding localization data, the JDK may fall back, including to names from another language or untranslated codes; therefore **it is not guaranteed** that every locale has a polished name in every language.

## 3. Runnable Java 17+ Example: One Locale, Multiple Display Languages

Create the file `LocaleDisplayNameDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleDisplayNameDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("fr-CA");

        Locale english = Locale.forLanguageTag("en-US");
        Locale french = Locale.forLanguageTag("fr-FR");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        System.out.println("Stored tag: " + target.toLanguageTag());
        System.out.println("Language code: " + target.getLanguage());
        System.out.println("Region code: " + target.getCountry());

        for (Locale displayLocale : List.of(
                english, french, vietnamese)) {
            System.out.println("Display locale: "
                    + displayLocale.toLanguageTag());
            System.out.println("Display name: "
                    + target.getDisplayName(displayLocale));
        }

        System.out.println("Stored tag after display: "
                + target.toLanguageTag());
    }
}
```

Run commands in the directory containing the file:

```bash
javac LocaleDisplayNameDemo.java
java LocaleDisplayNameDemo
```

Lines **with fixed output** determined by the values constructed in code:

```text
Stored tag: fr-CA
Language code: fr
Region code: CA
Display locale: en-US
Display locale: fr-FR
Display locale: vi-VN
Stored tag after display: fr-CA
```

The actual program prints **three additional `Display name: ...` lines**, each immediately following its corresponding `Display locale` line. They are typically in different languages; do not hardcode a single translation as universal stdout across all JDKs and locale providers. The key result to verify is that `target.toLanguageTag()` remains `fr-CA` before and after the calls: this is a **name-reading** operation that does not mutate the locale.

> If you need to illustrate English output, a name like `French (Canada)` is a common rendering of `fr-CA`. However, that string is only suitable as a UI example, not as a fixed API contract across all JDK versions/data.

## 4. DISPLAY Default Differs from FORMAT Default

Java distinguishes at least two default categories often important for localization:

- `Locale.Category.DISPLAY`: used when obtaining locale display names through no-argument methods such as `getDisplayName()`, `getDisplayLanguage()`, and `getDisplayCountry()`.
- `Locale.Category.FORMAT`: the default serving locale-aware formatting APIs, such as certain number/date formatting operations when no explicit locale is passed.

Do not infer that because “the user is viewing language labels in French”, numbers, dates, or currencies must also follow French conventions. In an international application, these two choices can be configured separately per product requirements.

**Example demonstrating `getDisplayName()` follows the DISPLAY default** — file `DisplayCategoryDemo.java`:

```java
import java.util.Locale;

public class DisplayCategoryDemo {
    public static void main(String[] args) {
        Locale original =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale target = Locale.forLanguageTag("de-DE");

        try {
            Locale english = Locale.forLanguageTag("en-US");
            Locale french = Locale.forLanguageTag("fr-FR");

            Locale.setDefault(Locale.Category.DISPLAY, english);
            System.out.println("Default: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("Matches explicit: "
                    + target.getDisplayName()
                            .equals(target.getDisplayName(english)));

            Locale.setDefault(Locale.Category.DISPLAY, french);
            System.out.println("Default: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("Matches explicit: "
                    + target.getDisplayName()
                            .equals(target.getDisplayName(french)));
        } finally {
            Locale.setDefault(Locale.Category.DISPLAY, original);
        }
    }
}
```

```bash
javac DisplayCategoryDemo.java
java DisplayCategoryDemo
```

Exact stdout of the example in a single-threaded process with no concurrent actor modifying defaults:

```text
Default: en-US
Matches explicit: true
Default: fr-FR
Matches explicit: true
```

This program **intentionally changes global settings for demonstration** and restores them in `finally`. `Locale.setDefault(...)` affects the entire JVM process and can impact other threads/requests, so **never call it per request** on a web server. In real applications, obtain `displayLocale` from the user context and pass it explicitly to `getDisplayName(displayLocale)`.

Additional note: `Locale.getDefault()` without a category and `Locale.getDefault(Locale.Category.DISPLAY)` are two APIs with different semantics; do not substitute one for the other casually when writing code that depends on a specific category.

## 5. Getting Names of Individual Components: language, script, country, variant

`getDisplayName(...)` is the **composite name** of a locale. When a UI wants separate fields for “Language”, “Script”, “Region”, and “Variant”, use the specialized methods:

| Component | Technical Code | Human-Readable Name |
| --- | --- | --- |
| Language | `getLanguage()` | `getDisplayLanguage(displayLocale)` |
| Script | `getScript()` | `getDisplayScript(displayLocale)` |
| Region | `getCountry()` | `getDisplayCountry(displayLocale)` |
| Variant | `getVariant()` | `getDisplayVariant(displayLocale)` |
| Composite name | `toLanguageTag()` for the code | `getDisplayName(displayLocale)` |

Each display-name API also has a **no-argument** overload, in which case it uses the default DISPLAY locale. Individual methods may return an empty string if the component is undeclared; for instance, `Locale.forLanguageTag("en").getDisplayCountry(Locale.ENGLISH)` returns an empty string because that locale has no region code.

**Java 17+ Example** — file `LocaleComponentsDemo.java`:

```java
import java.util.Locale;

public class LocaleComponentsDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("zh-Hant-TW");
        Locale display = Locale.ENGLISH;

        System.out.println("Tag: " + target.toLanguageTag());
        System.out.println("Language code: " + target.getLanguage());
        System.out.println("Script code: " + target.getScript());
        System.out.println("Region code: " + target.getCountry());
        System.out.println("Language label: "
                + target.getDisplayLanguage(display));
        System.out.println("Script label: "
                + target.getDisplayScript(display));
        System.out.println("Region label: "
                + target.getDisplayCountry(display));
        System.out.println("Full label: "
                + target.getDisplayName(display));
    }
}
```

```bash
javac LocaleComponentsDemo.java
java LocaleComponentsDemo
```

The three technical-code lines have stable output:

```text
Tag: zh-Hant-TW
Language code: zh
Script code: Hant
Region code: TW
```

The four `... label:` lines use JDK localization data and are not required to be identical across all environments. Calling this is useful because `getDisplayName` can include language, script, region, and variant names; which components appear depends on `target`'s configuration. For languages that need a script to distinguish writing styles, do not call `getDisplayLanguage()` alone and lose `Hans`/`Hant`.

**Note on variants:** a variant does not always have a common translated name. If Java has no localized name for the variant, a code-like value may appear. Unicode locale extensions and other extensions in a BCP 47 tag also do not mean `getDisplayName` will provide a complete explanation of every extension choice; design dedicated UI for special options if needed.

## 6. Displaying a Language Selection List Appropriately to Users

A locale list has two common label styles:

1. **Name in the UI's current language (localized name):** `option.getDisplayName(uiLocale)`, e.g., when the UI uses Vietnamese, labels are expressed in Vietnamese where possible.
2. **Name in the language the option itself represents (native/autonym):** `option.getDisplayName(option)`. This is helpful in a language-picker screen because users who cannot read the current UI language still have a chance to recognize their own language.

Both approaches are valid but serve different experiences. For lists with multiple regions of the same language, preserve region/script in the option locale and display labels clear enough to distinguish them.

**Program generating selection data — `LanguageMenuDemo.java`:**

```java
import java.util.List;
import java.util.Locale;

public class LanguageMenuDemo {
    public static void main(String[] args) {
        Locale uiLocale = Locale.forLanguageTag("vi-VN");

        List<Locale> supported = List.of(
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-CA"),
                Locale.forLanguageTag("de-DE"),
                Locale.forLanguageTag("zh-Hant-TW"));

        for (Locale option : supported) {
            String value = option.toLanguageTag();
            String labelForUi = option.getDisplayName(uiLocale);
            String nativeLabel = option.getDisplayName(option);

            System.out.println("value=" + value);
            System.out.println("  uiLabel=" + labelForUi);
            System.out.println("  nativeLabel=" + nativeLabel);
        }
    }
}
```

```bash
javac LanguageMenuDemo.java
java LanguageMenuDemo
```

The example prints **5 groups**, each consisting of a `value=...` line and two lines `uiLabel=...`, `nativeLabel=...`. The `value=` entries in exact order are:

```text
value=en-US
value=en-GB
value=fr-CA
value=de-DE
value=zh-Hant-TW
```

In real stdout, each `value=` line is followed by two labels computed by the JDK. This is not an example whose consecutive stdout consists only of the 5 lines above. When the user chooses an option, **store `value` as the language tag**, not `uiLabel` or `nativeLabel`: labels can change when switching UI languages or upgrading JDK data.

### Should `option.getDisplayName(option)` Be Used for Every Menu?

Not necessarily. Autonyms are helpful but have limitations:

- If display-name data in that language itself is incomplete, the label may fall back to another name or code.
- Multiple regions of the same language can be hard to tell apart if the UI only shows `getDisplayLanguage`; include region or script.
- When needing to comply with brand naming, product policy, or market-sensitive naming, the application can maintain an **editorially curated label table**. `getDisplayName` supplies standard runtime data, not a substitute for UI copy approval.
- Different scripts require font support and character rendering capabilities; a correctly returned name does not guarantee the system has a font to render it.

## 7. Do Not Use Display Names as Identifiers or Processing Logic

Consider three completely different tasks:

| Task | Appropriate API/Data | Why? |
| --- | --- | --- |
| Recording form value for the `en-GB` option | `locale.toLanguageTag()` | Code is more stable than localized names |
| Showing label to a user using `vi-VN` | `locale.getDisplayName(uiLocale)` | Label matches the UI language |
| Checking whether region `GB` was selected | `locale.getCountry()` or locale comparison | Independent of translations or country-name phrasing |

Do not parse the string returned by `getDisplayName()` to extract a region code. Composite name formatting (parentheses, commas, order of region/script, etc.) can change with locale data. Likewise, do not use `getDisplayName` as a `Map` key, database key, route, API query, or HTML `<option value>`.

Conceptually wrong example:

```java
// Poor design: labels translated to another language lose a stable key.
String savedLocale = option.getDisplayName(uiLocale);
```

Proper design for durable data:

```java
// Store the tag; each render can generate the label with the viewer's locale.
String savedLocale = option.toLanguageTag();
Locale restored = Locale.forLanguageTag(savedLocale);
String label = restored.getDisplayName(uiLocale);
```

Both snippets above must be used **inside a context where `option` and `uiLocale` are already declared**; they merely illustrate data selection, not standalone Java files.

## 8. Limitations of JDK Display Names

### Dependence on Runtime Localization Data

Java has multiple locale datasets, JDK versions, and locale provider configurations. Translations, region name spellings, and component ordering in names can change. A snapshot test comparing **exact** `getDisplayName(Locale)` strings sometimes fails when changing JDKs or locale providers even when application code is still correct.

For resilient tests, verify properties independent of translation phrasing (e.g., stored tag matches original, label is non-empty for selected locales, UI uses the right display locale). When the product strictly requires exact labels, store application-controlled labels and test that label table. Do not call `Locale.getAvailableLocales()` and infer the application automatically has UI translations for all of them: the list of runtime locales with supporting data is **not** the list of locales the application has translated.

### Distinguishing Language Name and Language Code

`getDisplayLanguage(displayLocale)` can return a language name yet **not show the full** script and region. For example, two options `en-US` / `en-GB` have the same language name when expressed in English, whereas the full `getDisplayName(displayLocale)` helps present the region as well to tell them apart. If the goal is a language-and-region picker menu, inspect each actual locale and add controlled annotations if labels look too similar.

### Do Not Confuse Display Locale with Formatting Locale

A user may view language names in Vietnamese while formatting currency/dates according to another market's conventions. `getDisplayName(uiLocale)` only determines the **language used to name locales** in this case; you do not need to and should not force all formatters to switch to `uiLocale` if application policy calls for a different formatting locale. Time zone is also a separate setting (`ZoneId`) and must not be inferred from `getDisplayName`.

### Do Not Treat Display Names as a General Text Translation Tool

`getDisplayName` only returns the localized name of a **`Locale` object**; it does not translate arbitrary messages such as greetings or page content. UI translation resources require an appropriate message source, such as `ResourceBundle` or the i18n system used by the application. A valid locale does not guarantee the application has translations ready for it.

## 9. Testing and Practice

**A conceptual test suite should include:**

- **Two display locales for one target:** for `fr-CA`, get names in `en-US` and `fr-FR`; verify the target locale stays `fr-CA` and labels aim at the intended languages.
- **Two regions of the same language:** `en-US`, `en-GB`; ensure stored codes differ, the UI can distinguish them, and region info is not dropped.
- **Cases with script:** `zh-Hans-CN` and `zh-Hant-TW`; verify tags preserve scripts and UI labels are sufficiently clear.
- **Locale without region:** `fr`; `getDisplayCountry(Locale.ENGLISH)` must be empty and the UI must not invent a region.
- **DISPLAY default:** demonstrate `getDisplayName()` uses the default DISPLAY category; production code switches to the parameterized overload to avoid global dependence.
- **Switching UI language:** when `uiLocale` changes, `value=` identifiers remain unchanged; only labels update.
- **Different runtimes:** avoid asserting fixed translated strings across JDKs/providers when the product makes no verbatim-text guarantee.

### Exercise 1: UI-Language Label and Autonym Label

Create a list containing `pt-BR`, `pt-PT`, `es-ES`, and `es-MX`. Set `uiLocale` to `vi-VN` and `en-US` in turn. For each locale, print `toLanguageTag()`, `getDisplayName(uiLocale)`, and `getDisplayName(option)`. Answer:

1. Which code stays unchanged when the UI language changes?
2. Can you reliably deduce the exact region code by parsing the display name?
3. When should you display both the UI-language label and the autonym label?

**Hint:** base it on the loop in `LanguageMenuDemo`. Labels are presentation data; BCP 47 codes serve to identify the selection.

### Exercise 2: Avoiding Dependence on the Default Locale

A web service is accessed concurrently by many users. The snippet below has a flawed design:

```java
Locale regionChoice = Locale.forLanguageTag("fr-CA");
String name = regionChoice.getDisplayName();
```

If user A's request uses English, user B's uses Vietnamese, and the server changes the DISPLAY default, the displayed name may fail to reflect each user's language. Replace with:

```java
Locale regionChoice = Locale.forLanguageTag("fr-CA");
Locale uiLocale = Locale.forLanguageTag("vi-VN"); // Example obtained from user/request
String name = regionChoice.getDisplayName(uiLocale);
```

In practice, `uiLocale` must come from the valid settings/context of the **current request** or application policy; these two snippets are examples inside a method, not standalone programs. Do not call `Locale.setDefault` per request.

## 10. Key Takeaways

- **`getDisplayName()`** retrieves the name using the JVM's **default `Locale.Category.DISPLAY`**; results can differ when the default environment changes.
- **`getDisplayName(inLocale)`** retrieves the target locale's name expressed in the **specified display locale**. This is the API to use for UIs with an explicit viewer locale.
- **`getDisplayName(locale)`** is the composite name; `getDisplayLanguage/Script/Country/Variant(locale)` provide labels for individual components.
- **`getDisplayName(option)`** helps display a name in the option's own language, useful for language selection menus, though fallback, script, and region still need checking.
- **`toLanguageTag()` is the identifier for storage/transmission**, while display names are only for human readers. Never use translated name text as an ID.
- Name content depends on JDK locale/provider data; test semantics properly and control labels with application resources when fixed wording is required.

Whenever expressing a locale to a user, always ask two questions: **which locale is being named?** and **whose language should that name be in?** The two answers correspond to the receiver of `getDisplayName` and the `inLocale` argument.