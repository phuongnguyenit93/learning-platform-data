# jlink --include-locales and Checking Remaining Locale Data in a Java Runtime

## 1. Problem: a smaller runtime without losing localization

When packaging a Java application into a **custom runtime image** with `jlink`, teams often want to shrink distribution size by keeping only the Java modules truly needed. For multilingual applications, trimming modules or locale data can leave the UI running while dates, numbers, currencies, or month names **stop formatting in the right language**.

Suppose an application needs Vietnamese, Japanese, French, and English. On a full development JDK, those locales may be supported. A runtime image with only `java.base`, however, holds far less locale data. Without care, formatting `1234.5` for `vi-VN` can yield English-style grouping/decimal marks instead of Vietnamese conventions—**without throwing any exception**.

Java provides the plug-in:

```text
jlink --include-locales=<langtag>[,<langtag>]*
```

This option **selects the subset of locale data packaged from the `jdk.localedata` module** when building a runtime image. It is not an input-method installer, does not change the OS language, does not modify `Locale.getDefault()`, and does not automatically add every module your application uses.

Lesson goals:

1. Understand `jlink`, `java.base`, and `jdk.localedata` in the locale data model.
2. Combine `--add-modules` and `--include-locales` properly.
3. Understand how to specify BCP 47 language tags/ranges and the filtering mechanism.
4. Write a Java 17+ program checking **which locales remain advertised** in the image.
5. Verify formatting outputs of specific APIs and spot silent fallbacks.
6. Design QA and packaging steps so localization works beyond developer machines.

## 2. Which modules hold locale data?

Modern JDKs separate data and APIs across several layers:

| Component | Role |
|---|---|
| `java.base` | Core APIs (`Locale`, `NumberFormat`, `DateFormat`, `DateTimeFormatter`, `ResourceBundle`, etc.) and baseline locale data |
| `jdk.localedata` | Module containing supplementary localization data, typically used by the CLDR locale provider |
| `java.desktop` | Desktop APIs such as AWT/Swing; needed only when the app actually uses them |
| Application and library modules | Code plus resource bundles supplied by the project and dependencies |
| `jlink` | Tool linking modules into a runtime image smaller than a full JDK |

**Key point:** `java.base` does not mean "zero locales." A `java.base`-only runtime image can still format certain baseline locales, notably English/root options. However, you must not assume it retains the full JDK's complete dataset.

`jdk.localedata` is not an implementation of `NumberFormat` that you import like a package. It is a **data module** consumed by locale-sensitive APIs. When the runtime lacks this module or a locale's resources were filtered out, identical API calls may return fallback-driven outputs.

### CLDR data and locale providers

Java has the **locale service providers** mechanism. Modern JDKs typically use **CLDR** (Unicode Common Locale Data Repository) data for many services. Final behavior depends on JDK version, provider order, and packaged datasets.

You can set the property when testing:

```bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

This lets you test explicitly with the CLDR provider, yet **it does not create missing locale data**. If the image stripped `de-DE` data, setting the provider to CLDR will not conjure that locale back into existence.

When a product includes application-provided providers via SPI or other means, outputs can also be affected. Tests must reflect the provider/configuration used in production, not only a developer workstation's state.

## 3. What does jlink do and where does --include-locales filter?

`jlink` reads compiled Java modules and their dependencies to build a runtime image. Example of an image with only base Java and locale data:

```bash
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --output runtime-l10n
```

This example uses `\` line continuations for shells such as Bash. On Windows PowerShell, use a single-line command to avoid syntax differences.

Single-line equivalent:

```powershell
jlink --add-modules java.base,jdk.localedata --include-locales=en,ja,vi,fr --output runtime-l10n
```

Meaning:

- `--add-modules java.base,jdk.localedata`: includes both modules in the image graph. `java.base` is the base module; `jdk.localedata` is added **explicitly**.
- `--include-locales=en,ja,vi,fr`: instructs the plug-in to retain only locale resources inside `jdk.localedata` matching the chosen language ranges.
- `--output runtime-l10n`: output directory for the image. The target directory must not already exist (or must satisfy jlink rules); never overwrite an image in active use.

**You cannot pass `--include-locales` while omitting `jdk.localedata`.** When tested on the JDK used for this lesson, the command:

```bash
jlink --add-modules java.base --include-locales=ja --output runtime-wrong
```

reports:

```text
Error: jdk.localedata module was not specified with --add-modules option
```

This is an **image-creation configuration error**, not a date-parsing or number-formatting error in the application.

In production, `--add-modules` will rarely consist of just these two modules. If your app needs `java.logging`, `java.sql`, `java.net.http`, `java.desktop`, your own application modules, or other dependencies, ensure they are also added per the module graph. `--include-locales` **does not replace dependency analysis**.

## 4. BCP 47 standard and matching scope

The plug-in syntax shown by `jlink --list-plugins`:

```text
--include-locales <langtag>[,<langtag>]*
BCP 47 language tags separated by a comma,
allowing locale matching defined in RFC 4647.
e.g.: en,ja,*-IN
```

Entries are comma-separated. Examples:

| Expression | Selection intent |
|---|---|
| `en` | Data matching the English language range |
| `vi` | Data matching the Vietnamese language range |
| `ja` | Data matching the Japanese language range |
| `fr` | Data matching the French language range |
| `en,ja,vi,fr` | Combines all four ranges |
| `vi-VN` | Specifically targets Vietnamese in Vietnam |
| `*-IN` | Example wildcard range matching locales for region IN per supported matching rules |

BCP 47 **language tags** use hyphens, such as `vi-VN` or `en-US`; do not confuse them with underscore forms used by legacy `Locale` constructors.

**Do not treat `en,ja,vi,fr` as "literally four Locale objects."** Language ranges can match many regional variants, and jlink may retain additional supporting data. The exact number of locales appearing after linking depends on the JDK/provider and underlying data.

Likewise, do not assume `*-IN` pulls in every language library worldwide; it only selects available data matching the plug-in's rules.

### Checking that the plug-in exists in your JDK

Before creating an image:

```bash
jlink --version
jlink --list-plugins
```

Look for `--include-locales`. If the tool lacks this plug-in, check your JDK version/distribution rather than passing an unrecognized option.

A pattern matching no locales can cause jlink to fail. On the tested JDK, this command:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=zz-ZZ --output runtime-none
```

returns:

```text
Error: No matching locales found for "zz-ZZ". Check the specified pattern.
```

Do not treat `zz-ZZ` as a real hypothetical locale; it merely tests a **non-matching language range**.

## 5. Environment requirements when creating a runtime image

You need a **JDK containing the `jlink` tool and corresponding JMODs**, not merely a JRE or slim runtime image. Normally `jlink` uses the JDK's `jmods` directory when `--module-path` is omitted, though you should explicitly control which JDK build packages the image.

Check:

```bash
java -version
javac -version
jlink --version
java --list-modules
```

The list from the image-building JDK must contain `jdk.localedata`. On a suitable JDK, inspect the module:

```bash
java --describe-module jdk.localedata
```

To specify the module path explicitly, for example in Bash:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --output runtime-l10n
```

In Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,jdk.localedata --include-locales=en,ja,vi,fr --output runtime-l10n
```

Practical notes:

- `JAVA_HOME` must point to a **JDK** with matching JMOD files.
- Do not mix the module path of a different JDK version with the running `jlink`.
- When packaging your app inside the image, add the **application module path** and corresponding root modules.
- Generated images are platform/architecture-specific and are not universally portable across operating systems.
- After linking, the image typically includes `bin/java` (or `bin\java.exe` on Windows), but **do not assume it includes `javac` or `jlink`**. Compile your program with the full JDK before running the probe inside the image.

Never alter global `JAVA_HOME` or `PATH` solely to test an image; invoke the executable path inside the image directly.

## 6. Java 17+ program to check remaining locales

A basic QA approach checks **two layers**:

1. Is the `jdk.localedata` module present in the image?
2. Does the required service (`NumberFormat` in this example) **still advertise the target locales?**

`Locale.forLanguageTag("vi-VN")` only **creates a locale descriptor object**; it does not prove the runtime holds Vietnamese data.

Create `LocaleDataProbe.java`:

```java
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class LocaleDataProbe {
    public static void main(String[] args) {
        List<Locale> available =
                Arrays.asList(NumberFormat.getAvailableLocales());

        boolean hasModule = ModuleLayer.boot()
                .findModule("jdk.localedata")
                .isPresent();

        System.out.println("jdk.localedata=" + hasModule);

        for (String tag : new String[] {
                "en-US", "ja-JP", "vi-VN",
                "fr-FR", "de-DE", "ar-EG"
        }) {
            Locale locale = Locale.forLanguageTag(tag);
            System.out.println(
                    tag + "=" + available.contains(locale));
        }

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        String shown = NumberFormat.getNumberInstance(vietnamese)
                .format(1234.5);

        System.out.println("vi-number=" + shown);
    }
}
```

Compile with the full JDK:

```bash
javac LocaleDataProbe.java
```

Run with the generated image. Linux/macOS:

```bash
./runtime-l10n/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

Windows PowerShell:

```powershell
.\runtime-l10n\bin\java.exe "-Djava.locale.providers=CLDR" -cp . LocaleDataProbe
```

Verified output on the test JDK and an image built with `--include-locales=en,ja,vi,fr`:

```text
jdk.localedata=true
en-US=true
ja-JP=true
vi-VN=true
fr-FR=true
de-DE=false
ar-EG=false
vi-number=1.234,5
```

Reading the output:

- `jdk.localedata=true` shows the module is present, **not that every locale retains data**.
- All four requested locales are advertised by `NumberFormat`.
- `de-DE` and `ar-EG` are absent from `NumberFormat.getAvailableLocales()` in the test image.
- `vi-number=1.234,5` shows that in the tested runtime, `vi-VN` still follows the expected numeric punctuation rules under the CLDR provider.

**These values reflect a specific JDK/image, not an invariant across all Java 17+ releases.** CLDR data and locale lists can change across JDK versions. Unit/CI tests should assert **required locales and formatting behavior**, not a fixed total locale count as the sole criterion.

## 7. Comparing full JDK, java.base-only image, and filtered image

A useful practical check is running **the exact same probe** on three runtimes:

1. **Full JDK**: usually contains comprehensive locale data.
2. **Minimal `java.base`-only image**: contains baseline locale data.
3. **Image with `jdk.localedata` plus `--include-locales` keeping only needed language ranges**.

Example creating the minimal image:

```bash
jlink --add-modules java.base --output runtime-base
```

Then run:

```bash
./runtime-base/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

On the test JDK, the `java.base` image advertised only **5** locales via `NumberFormat.getAvailableLocales()`, whereas the `en,ja,vi,fr`-filtered image advertised **166** and the full JDK advertised **1146**. **Do not hardcode these three numbers:** they simply illustrate the clear impact of modules/filters on one specific JDK.

Notably, `java.base` can still return a formatted number string when asked for an unlisted locale. Requesting `vi-VN` on a minimal image may yield `1,234.5` instead of `1.234,5`. That is **fallback**, not proof the system still carries Vietnamese data.

Testing workflows must never rely on "`format(...)` did not throw an exception," because fallback happens silently.

## 8. Why can a runtime keep the module yet lose data for certain locales?

`java --list-modules` proves only that the module is present in the image; **it does not list individual retained locale data entries**.

If:

```bash
./runtime-l10n/bin/java --list-modules
```

contains:

```text
java.base@...
jdk.localedata@...
```

then the data module was linked. However, creating the image with `--include-locales` may have trimmed resource bundles inside `jdk.localedata`.

Therefore, you cannot conclude:

```text
jdk.localedata is present => every full JDK locale is present
```

The right practice is to **verify the specific service and locales** inside the target image itself.

If you only assert `ModuleLayer.boot().findModule("jdk.localedata").isPresent()`, labeling a runtime "supports French" can still be false if the `jlink` command omitted French data.

## 9. Checking Locale.getAvailableLocales and specific services

Java offers several APIs advertising locale lists:

```java
Locale.getAvailableLocales();
NumberFormat.getAvailableLocales();
DateFormat.getAvailableLocales();
Collator.getAvailableLocales();
```

These calls are **in-method code fragments** requiring corresponding imports.

Choose APIs based on product features:

| Feature | What to check |
|---|---|
| Number, percent, currency formatting | `NumberFormat.getAvailableLocales()` and formatted output |
| `java.text`-style date/time formatting | `DateFormat.getAvailableLocales()` and date/time output |
| Language-sensitive text sorting | `Collator.getAvailableLocales()` and real comparison pairs |
| General locale selection | `Locale.getAvailableLocales()` as an initial signal |
| Month/weekday names, `java.time` formatting | Test `DateTimeFormatter` with the exact locale/style used |
| App-provided UI languages | Check the app's own `ResourceBundle`, not just `jdk.localedata` |

**Never treat a single locale list as proof every service has deep support.** A locale can appear in one API while outputs still depend on the service provider and specific dataset.

`Locale.getAvailableLocales()` is a broad indicator; when the app uses number/date/collation features, test each service directly. If the app only uses `DateTimeFormatter`, do not rely on `NumberFormat` checks as the sole criterion for date-time support.

## 10. Test formatting behavior, not just support lists

Supported locale lists are helpful for catching filtered-out locales, yet final QA must ask: **does the product actually render content accurately?**

Examples:

- **Vietnamese:** `1234.5` per app settings, grouping/decimal separators, and date representation.
- **French:** numbers using the grouping/decimal conventions and corresponding symbols/whitespace in the JDK/provider.
- **Japanese:** month display, Japanese era names if the app uses the Japanese calendar, yen currency, and relevant patterns.
- **Arabic:** digits, grouping marks, decimal marks, text direction, and font/rendering behavior for desktop apps.

**Do not hardcode every locale output to a single CLDR version's exact text.** Regional/linguistic updates may reflect valid standards evolutions. Tests should combine soft checks (locale must be present) with critical cases evaluated against the production JDK build.

A solid testing flow:

```text
Target locale present?
   |
   +-- No  -> FAIL BUILD
   |
   +-- Yes -> format real data
                  |
                  +-- Fails business requirements -> FAIL QA
                  |
                  +-- Passes -> check UI/fonts if applicable
```

If locale date data is missing, the app can silently fall back to another format; this is why formatting QA must execute **using the image's own executable**, not merely the compilation JDK.

## 11. Distinguish JDK data from application resource bundles

`--include-locales` is a plug-in selecting locales for **`jdk.localedata`**. It is not a command filtering all translation files in your project or modifying your localization management system.

For example, suppose an application has:

```text
messages.properties
messages_vi.properties
messages_fr.properties
```

These files are **application resource bundles**. They are packaged into outputs/runtimes via the app's module/JAR/resource packaging. Having `vi-VN` in `jdk.localedata` **does not guarantee** `messages_vi.properties` was packaged into the application artifact.

Conversely, even if the app ships `messages_vi.properties`, the runtime image could still lack JDK locale data used by `DateFormat`, `NumberFormat`, or `Collator`.

Verify two independent tracks:

1. **JDK locale data:** module + include-locales + formatting/collation APIs.
2. **App translations:** resource bundle files and `ResourceBundle.getBundle(...)` fallback.

Note that `ResourceBundle` has its own lookup/fallback mechanism, so a returned bundle is **not necessarily the bundle for the exact requested locale**. When verifying translations, inspect the bundle's actual locale alongside key strings to catch unintended fallback.

## 12. Do not infer support from Locale.forLanguageTag()

The statement:

```java
Locale locale = Locale.forLanguageTag("de-DE");
```

does not prove German data is present in the image. `Locale` is largely a **language/region and extension descriptor**, not something that fetches locale resource bundles over the network.

Hence, checks like these are insufficient:

```java
System.out.println(locale.toLanguageTag()); // de-DE
System.out.println(locale.getLanguage());    // de
```

They prove the object holds the locale tag, not that the number-formatting algorithm has `de-DE` data.

Nor can you rely on `NumberFormat.getInstance(locale)` returning non-null: the API can fall back to another locale. It is better to check `NumberFormat.getAvailableLocales()` **and** format values capable of exposing differences across locales.

For example, `1234.5` is a convenient test number because US (`1,234.5`) and vi-VN (`1.234,5`) representations differ in punctuation. A small integer like `12`, however, can produce identical output across many locales, making the test too weak to detect stripped data.

## 13. include-locales does not set the default Locale

After running:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=ja,vi --output runtime
```

you **must not conclude**:

```text
Locale.getDefault() == vi-VN
```

The option only selects packaged data; **it does not set the JVM's default language**. The default locale comes from the OS, environment, or other runtime settings.

A call omitting the locale:

```java
NumberFormat.getNumberInstance();
```

uses the default locale, which may not be one the product intends to use. If the runtime lacks data for that default, fallback can produce unexpected outputs.

Rather than letting server defaults dictate output, format intentionally:

```java
Locale userLocale = Locale.forLanguageTag("vi-VN");
NumberFormat formatter =
        NumberFormat.getNumberInstance(userLocale);
```

In multi-user applications, the locale must come from user selection, request context, or data contracts, never mutated globally via `Locale.setDefault(...)` per request.

To check the actual default locale when running the image:

```java
System.out.println(Locale.getDefault().toLanguageTag());
```

And separately verify the locale passed into each formatting API.

## 14. Mind locale extensions and variants

BCP 47 supports language, script, region, variant, and Unicode locale extensions. Examples:

```text
en-US
zh-Hant-TW
th-TH
ar-EG-u-nu-latn
```

Extensions can control desired service behavior, such as numbering systems in certain APIs/providers.

However, **do not treat `--include-locales` as automatically guaranteeing every numbering system, calendar, and extension is supported**. Locale data, language variants, and API extension handling can vary across JDKs. Test the **exact locale tags used by your application**, including extensions when meaningful.

For instance, if your product contract allows `th-TH-u-nu-thai` or `ar-EG-u-nu-latn`, do not test only `th` or `ar` and assume all digit rendering will work.

Conversely, if the app uses no regional variants or extensions, do not include random ones: derive the locale set from **actual product requirements**.

## 15. Integrating jlink into the build pipeline

A reliable release workflow:

1. **Define supported locales:** from product requirements, not arbitrarily picked just to shrink the image.
2. **Analyze app modules:** application root modules and dependencies. Use `jdeps` where appropriate to assist analysis.
3. **Include `jdk.localedata` in the graph:** add it to `--add-modules` whenever using `--include-locales`.
4. **Run `jlink` with a pinned JDK build:** create the image in a fresh directory.
5. **Run probes using `runtime/bin/java`:** check modules, API available locales, and essential locales.
6. **Run integration tests:** number/date/currency formatting, text collation, and resource bundles on the image.
7. **Test target platforms:** especially for desktop apps or features needing fonts, timezones, and OS integration.
8. **Package the image with the app:** ensure the real classpath/module path and launcher invoke the exact tested image.
9. **Record metadata:** store JDK vendor/version, jlink flags, locale scope, artifact hashes, and QA results.
10. **Re-verify on JDK upgrades:** CLDR data, providers, and locale outputs can change.

Example CI commands (Bash):

```bash
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --no-header-files \
  --no-man-pages \
  --output runtime-l10n

javac LocaleDataProbe.java
./runtime-l10n/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleDataProbe
```

`--no-header-files` and `--no-man-pages` trim image contents; **they do not govern locale lists**. If a production build requires additional modules, include them in the actual command.

On Windows, use `runtime-l10n\bin\java.exe`. Properly quote paths containing spaces, especially for `--module-path` and `--output`.

## 16. Using jlink and jdeps in their proper roles

`jdeps` discovers which modules a Java application depends on via class/module references; it cannot deduce **all locales users will request at runtime**.

For example, an application may call:

```java
NumberFormat.getNumberInstance(userLocale);
```

At build time, `userLocale` is unknown if it arrives from requests. Even though `jdeps` detects the need for `java.base`, it has no way of knowing the product requires `vi-VN`, `fr-FR`, or `ar-EG`.

Therefore, two distinct decisions are required:

- **Technical dependencies:** which modules are needed for the code to execute?
- **Supported regions/languages:** which locale data is needed for features to behave **semantically correctly**?

`--include-locales` solves the second decision for `jdk.localedata`, not the first. Never run `jdeps` once and assume localization packaging is finished.

## 17. Shrinking size while controlling quality

There is no universal "best" language list for all products. A US-English-only app might not need the full locale dataset. An app serving users in Vietnam, Japan, France, and elsewhere must keep corresponding data.

Trade-offs:

| Decision | Benefit | Risk |
|---|---|---|
| `java.base` only | Smallest image | Missing locale data for many languages |
| Include full `jdk.localedata` | Broadest locale coverage | Larger image |
| Include `jdk.localedata` + `--include-locales` | Balances size and locale scope | Easy to omit locales/extensions if requirements are unclear |
| Test only `Locale.forLanguageTag` | Fast test | Proves nothing about real data |
| Test outputs under the image | Catches silent fallbacks and real bugs | Requires maintaining test cases across JDK versions |

Never optimize solely for ZIP size or megabytes at the expense of locale correctness. A "minimal" runtime image that prints invoices with wrong decimal separators can cause far greater business harm than the disk space saved.

## 18. Troubleshooting: typical errors

### Error A — Missing jdk.localedata in --add-modules

Symptom during the jlink step:

```text
Error: jdk.localedata module was not specified with --add-modules option
```

Fix: add `jdk.localedata` to the root modules list. Then inspect the resulting image rather than stopping simply because the link command exited cleanly.

### Error B — Include range matches no JDK data

Symptom:

```text
Error: No matching locales found for "zz-ZZ". Check the specified pattern.
```

Fix: inspect the language tag/range, spelling, and JDK/provider. Do not treat raw user-entered locale tags as guaranteed available.

### Error C — Module is present yet formatting uses the wrong locale

Symptom: `java --list-modules` lists `jdk.localedata`, yet `NumberFormat` for a mandatory locale displays English-style fallback.

Check: initial `--include-locales`, `NumberFormat.getAvailableLocales()`, locale provider properties, and actual formatted output. Add the missing range and **build a new image** rather than patching resources inside an already-shipped image without a supported process.

### Error D — Running the probe with the full JDK instead of the image

Symptom: local tests pass, while production shows wrong locales.

Common cause: tests invoked `java` from `PATH` (full JDK) instead of `runtime-l10n/bin/java`. In CI, invoke an **explicit/absolute path** to the image binary to eliminate ambiguity.

### Error E — Locale data exists yet UI translations are missing

`NumberFormat` works for `vi-VN`, yet `messages_vi.properties` is missing in the app. This is an app resource-packaging issue, not `--include-locales`. Check resource paths/JARs/modules, `ResourceBundle` fallback, and translation bundles.

### Error F — Default locale differs from expectations

The app calls `NumberFormat.getInstance()` without passing a locale; on the server the default is `en-US`, so English formatting persists. Fix: pass `Locale` explicitly from business context rather than merely adding `vi` to the image.

### Error G — Outputs differ after a JDK upgrade

The newer JDK updated locale/CLDR data. Grouping separators, region names, or other formatting details may change even with identical flags. Fix: pin JDK builds per release, run regression tests, and update expected outputs after evaluating the standards change.

## 19. QA checklist for release images

| Check | Passing condition |
|---|---|
| `jlink --list-plugins` | `--include-locales` is available in the JDK build |
| JDK modules | `jdk.localedata` can be linked |
| Link command | Includes `--add-modules ... ,jdk.localedata` and required ranges |
| Modules in image | `bin/java --list-modules` shows `jdk.localedata` |
| Locale APIs | Mandatory locales appear in relevant service APIs |
| Number formatting | Grouping/decimal/precision match business cases |
| Date/time | Dates and month names match locale; timezones verified separately |
| Currency | Symbols, fractional digits, and rounding policy match requirements |
| Collation | Key test strings sort per locale rules |
| Application bundles | UI translations exist in the app artifact |
| Image executable | Tests run via the image's `bin/java`, not the full JDK |
| Locale extensions | Actual BCP 47 tags used are supported and tested |
| Build reproducibility | Pin JDK/providers, record jlink flags and test results |
| Fallback | Locales excluded from the image are caught rather than silently accepted |

Keep the **minimum mandatory locale list** as part of release configuration. If users can switch UI languages and a language is not packaged, the application should block/restrict that choice or warn explicitly rather than silently reverting to an unapproved format.

## 20. Common pitfalls when learning and deploying

1. **Writing `--include-locales=vi` while forgetting `jdk.localedata`.** The plug-in requires the data module in `--add-modules`.
2. **Thinking `--include-locales` sets the JVM's default language.** It only filters retained data.
3. **Thinking `Locale.forLanguageTag("vi-VN")` proves Vietnamese locale data is present.** It only creates a descriptor object.
4. **Thinking `NumberFormat.getInstance(locale)` not throwing means full locale data exists.** Providers can fall back silently.
5. **Checking only `java --list-modules`.** Having `jdk.localedata` does not prove a specific locale remains in the image.
6. **Running tests with `java` from PATH.** You may accidentally invoke the full JDK rather than the linked image.
7. **Hardcoding total locale counts to a fixed number.** Locale sets vary by JDK/provider.
8. **Confusing JDK data with the app's `messages_*.properties`.** They are two independent resource sources.
9. **Using invalid langtag syntax or unverified wildcards.** BCP 47 language ranges must be accepted by jlink and match real data.
10. **Relying on `jdeps` to decide which languages to package.** Dependency analysis does not know runtime locale needs.
11. **Stripping all locale data for image size.** The app may keep running while displaying wrong values.
12. **Skipping date, currency, and Collator tests.** A single numeric probe does not validate the full localization experience.
13. **Skipping tests against the actual production provider.** Same module with different providers/configs can yield different results.
14. **Ignoring BCP 47 extensions.** Numbering systems or calendars in extended locales may need dedicated tests.
15. **Assuming a runtime image works on every OS.** Built images are platform-dependent.
16. **Upgrading the JDK and reusing old CLDR expectations without testing.** Locale data evolves.
17. **Treating a successful link as completed QA.** The runtime must execute and have real outputs verified.
18. **Overlooking ResourceBundle fallback.** Wrong-language text can appear even when JDK date/number locales are intact.

## 21. Self-check questions

**Q1.** Why must `jdk.localedata` be added to `--add-modules` when using `jlink --include-locales`?  
**Answer:** The plug-in filters locale data from `jdk.localedata`; omitting that module is an invalid link configuration in the tested JDK.

**Q2.** Does `--include-locales=en,ja,vi,fr` mean the image advertises literally four `Locale` instances?  
**Answer:** No. Those are language ranges; they can match multiple regional variants and retain baseline locales. Counts depend on the JDK.

**Q3.** If an image contains `jdk.localedata`, are all locales from the development JDK still present?  
**Answer:** No. `--include-locales` may have filtered resources per options; specific locales must be checked.

**Q4.** Can you rely on `Locale.forLanguageTag("vi-VN")` to conclude Vietnamese data is available?  
**Answer:** No. You must test APIs/services and actual formatted output in the runtime image.

**Q5.** Why can an image lacking `de-DE` still format numbers for `de-DE` without errors?  
**Answer:** Locale providers can apply fallback rules. Not throwing an error does not mean the locale is properly supported.

**Q6.** Why must tests invoke `./runtime-l10n/bin/java` instead of just `java`?  
**Answer:** To ensure tests execute on the newly built image; `java` on PATH may point to the full JDK.

**Q7.** If `messages_vi.properties` is omitted from the application JAR, will `--include-locales=vi` generate it?  
**Answer:** No. That is an application resource, not part of `jdk.localedata`.

**Q8.** To verify dates, currencies, and collation, is `NumberFormat.getAvailableLocales()` enough?  
**Answer:** No. You need to test the APIs and representative values for each service.

**Q9.** If a locale test suite passes on JDK 17 but fails after upgrading to a newer JDK, what should you inspect?  
**Answer:** JDK vendor/version, CLDR/provider version, jlink flags, module graph, language ranges, and actual app outputs.

**Q10.** When should extra locales be kept instead of shrinking the image?  
**Answer:** Whenever the product requires supporting those languages/regions. Localization correctness must be a quality gate, not optional.

## 22. Summary

`jlink --include-locales` is a vital tool for balancing **runtime footprint** and **localization coverage** in modular Java. To use it properly:

- Add `jdk.localedata` to `--add-modules` alongside the actual modules your application needs.
- Select BCP 47 language ranges matching the locales your product supports.
- Verify **inside the target image**: module presence, `getAvailableLocales()` for relevant services, and real number/date/currency outputs.
- Detect **silent fallbacks**: a running formatter does not mean the right locale's data is being used.
- Separately test application resource bundles, default locales, timezones, providers, and JDK upgrades.

A release principle worth remembering: **"Build a smaller image, but prove locale correctness using the linked runtime itself."**

**Official references:** [Java SE 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html) · [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — DateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html) · [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252).
