# jdk.localedata and Datasets in Custom Runtimes

## 1. Problem: the same program formats locales differently across runtimes

A Java program can run properly on a development machine using a full JDK, yet after packaging into a slim runtime with `jlink`, how it prints dates, numbers, currencies, or localized names can change. Instead of `28 tháng 10, 2026`, the system may use a fallback style; instead of French month names, you might see data from a parent locale or the root locale.

That is not necessarily a bug in `DateTimeFormatter`, `NumberFormat`, or `Locale`. The cause may be that **the runtime image does not contain the locale data the formatter needs**.

Java 9+ separates much of its localization data into a module named **`jdk.localedata`**. When using `jlink` to build a **custom runtime image**, you decide whether to include or exclude that module; the `--include-locales` option lets you pick a smaller subset of locales inside the module.

This lesson explains:

1. How `java.base`, `jdk.localedata`, and locale data are split.
2. Why a valid `Locale` **does not prove** translations/formatting for it are available.
3. How to build a custom runtime with `jlink --add-modules` and `--include-locales`.
4. How to inspect `DateTimeFormatter`, `NumberFormat`, `DateFormat`, currency names, and available locale lists.
5. How to compare behavior between a full JDK and a minimal runtime, detect fallbacks, write tests, and avoid wrong deployment assumptions.

The scope of this lesson lies within **JDK Locale Data**. This is about **data resources packaged inside the runtime**, not a guide to downloading translations from the Internet or specifying a `Locale` in source code.

## 2. Locale is not a bundle of translation data

`java.util.Locale` is primarily an **identifier object for language/region/script/extensions**, for example:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

This statement creates an object describing the Vietnamese locale (Vietnam region). It **does not** automatically fetch month names, number symbols, currency names, or date patterns.

When you call:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
~~~

the formatting API looks up **locale data sources/providers available in the runtime** to select patterns and corresponding words. If data for the exact locale is missing, fallback can produce unexpected output.

Distinguish three questions:

| Question | What is being verified |
| --- | --- |
| Does `Locale.forLanguageTag("vi-VN")` construct an object? | The locale identifier can be represented in Java |
| Does the runtime include the `jdk.localedata` module? | Whether the image contains the extended locale data module |
| Does the formatting service for `vi-VN` have real data? | Whether the chosen provider actually supplies data for that service/context |

The three questions are **not equivalent**. A successfully constructed `Locale` does not prove `DateTimeFormatter` will print Vietnamese month names or `Currency.getDisplayName(locale)` will have the localized name you expect.

## 3. What roles do `java.base` and `jdk.localedata` play?

### 3.1. `java.base`: the foundational module

Every Java runtime image always requires `java.base`, as it is the mandatory base module of the Java platform. This module includes APIs such as:

- `java.util.Locale`;
- `java.text.NumberFormat`, `DateFormat`;
- `java.time.format.DateTimeFormatter`;
- `java.util.Currency`.

The existence of those APIs **does not mean the runtime ships with all localization data**.

In documented Oracle/OpenJDK builds, `java.base` carries baseline locale data, including **US English and parent locales such as `ROOT`**. Data for many other locales resides in `jdk.localedata`.

### 3.2. `jdk.localedata`: supplementary locale data

`jdk.localedata` is a **JDK-specific module** containing extended localization data for locale-sensitive services, such as language-specific date, number, currency, or display name representations.

This module is not a class you import when writing `DateTimeFormatter`. Most programs still use APIs in `java.base`; it is the **module graph and runtime data sources** that decide whether extended data is present.

Examples of features that may be affected when corresponding locale data is omitted:

- Month names, weekday names, and date/time patterns via `DateTimeFormatter` or `DateFormat`.
- Decimal separators, grouping separators, and percent representations via `NumberFormat`.
- Display names of locales, countries, and currencies via their respective APIs.
- Certain formatting/comparison rules supplied by the runtime's locale service providers.

**Do not overgeneralize:** omitting `jdk.localedata` does not mean all Unicode features, UTF-8, `Locale`, `java.time`, or all timezones vanish. Its scope is **extended locale data**; other components of `java.base` remain intact.

### 3.3. Locale data vs. application-specific resources

`ResourceBundle` or `messages_vi.properties` files **provided by the application itself** do not automatically live inside `jdk.localedata`. They must be packaged and loaded according to your application and module setup.

Conversely, having complete UI translations in your `ResourceBundle` **does not guarantee** `NumberFormat` or `DateTimeFormatter` has the right CLDR data for that locale in the runtime.

Two separate resource tracks must be tested independently: **application localization data** and **JDK locale data**.

## 4. Full JDK vs. a runtime created with jlink

When installing a **full JDK**, the distribution usually includes the `jdk.localedata` module and extended locale data. Therefore, testing with `vi-VN`, `fr-FR`, and `ja-JP` on a developer machine may succeed.

With `jlink`, developers assemble a **custom runtime image** containing only the required set of modules. A minimal image might contain only `java.base`; in that case, much of the extended locale data will be absent.

Visualize it:

~~~text
Full JDK
  java.base          -> APIs + baseline locale data
  jdk.localedata     -> extended locale data
  other modules      -> other APIs/tools/services

Minimal custom image
  java.base          -> APIs are still present
  (no jdk.localedata)
  => many locales lack full formatting data
~~~

Another image might contain:

~~~text
Selectively supported custom image
  java.base
  jdk.localedata (filtered by --include-locales)
  modules required by the app
  => data present for the selected locale group
~~~

`jlink` **does not change the semantics of `Locale.forLanguageTag`**; it changes **the modules and resources bundled in the runtime**, which in turn affects services requiring locale data.

Do not treat "the program ran without throwing an error" as proof of complete locale data. Fallback often **throws no exception**, instead simply producing date/time or number strings that differ from the intended user experience.

## 5. Inspection tools on the development machine

Before building an image, verify the source JDK being used:

~~~bash
java -version
jlink --version
java --list-modules
~~~

The `java --list-modules` command lists the modules present in the runtime. You can look for `jdk.localedata` in this list.

In Windows PowerShell, you can filter:

~~~powershell
java --list-modules | Select-String 'jdk.localedata'
~~~

In Linux/macOS shells, for example:

~~~bash
java --list-modules | grep 'jdk.localedata'
~~~

**Note:** these commands only show that **the module exists in the runtime image**, not that every locale was retained. An image with `jdk.localedata` filtered via `--include-locales` may still lack the locales you need.

If your application or deployment tooling uses `JAVA_HOME`, ensure `java` and `jlink` are invoked from the **target JDK version and architecture**. When testing a shipped runtime image, run **that image's `java` binary**, rather than accidentally invoking the system JDK command.

## 6. Building an image with only the minimal module

Example `jlink` command for a compatible JDK:

~~~bash
jlink --add-modules java.base --output image-base
~~~

This is an **example of creating a minimal custom runtime image for comparison**. It creates the `image-base` directory containing a runtime with `java.base`; it is not an automatic build containing all modules needed by an arbitrary application.

After creation, inspect the image using the Java launcher inside it.

Linux/macOS:

~~~bash
./image-base/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\image-base\bin\java.exe --list-modules
~~~

The list will include `java.base` and will not contain `jdk.localedata` in a `java.base`-only image.

That **does not mean every non-US locale will throw an exception**. Services may fall back or operate using baseline data. Hence, never rely on an exception as the sole condition for detecting missing locale data.

`jlink` also requires whatever modules the application actually uses. If the app needs `java.logging`, `java.sql`, `java.xml`, or other modules, include those dependencies at build time. Do not copy a `java.base`-only command into production if it does not match your application's module graph.

## 7. Adding jdk.localedata to the image

To carry the extended locale data module:

~~~bash
jlink --add-modules java.base,jdk.localedata --output image-full-locale
~~~

On many JDKs, without `--include-locales` filtering, the module is packaged with the locale dataset bundled in that JDK. The image will be larger than a `java.base`-only build, while enabling broader localization services.

Verify:

~~~bash
./image-full-locale/bin/java --list-modules
~~~

On Windows, replace the launcher path with `.\image-full-locale\bin\java.exe`.

The listed modules must include `jdk.localedata`. However, **module presence alone is not proof that your formatting services pick the right provider or carry every expected translation**. Run an additional check program verifying dates, numbers, and currencies across each key locale.

Do not look solely at whether `jlink` exits with code 0: a module-valid image can still miss the product's **actual locale requirements**.

## 8. `--include-locales`: filtering data by language/region list

`jlink`'s `include-locales` plug-in lets you restrict packaged locale data:

~~~bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales=vi-VN,fr-FR,ja-JP \
      --output image-selected-locales
~~~

This syntax example assumes a shell supporting `\\` line continuation. On Windows PowerShell, use **a single line** to avoid line-continuation syntax differences:

~~~powershell
jlink --add-modules java.base,jdk.localedata --include-locales=vi-VN,fr-FR,ja-JP --output image-selected-locales
~~~

**Two important points about `include-locales`:**

1. When using `--include-locales`, you **must add the `jdk.localedata` module** to the modules included in the image. The plug-in does not act as a request to "download languages automatically."
2. The list `vi-VN,fr-FR,ja-JP` consists of BCP 47 **language tags**. The plug-in applies locale-matching rules; language/region patterns like `en,ja,*-IN` can be used as shown in Oracle doc examples. Do not assume `vi` and `vi-VN` always behave identically across every dataset and service; check the actual locale set after building.

`--include-locales` **must not be understood as a filter over all application Strings or ResourceBundles**. It filters corresponding locale data inside the image's `jdk.localedata` module. Nor does it translate user data files into Vietnamese, French, or Japanese.

Filtering locales is appropriate only when you know the exact list of locales the **product must support**; balance image size against localization quality.

## 9. Java 17+ example: probing modules, locales, and formatted outputs

Module presence/absence is only the first signal. You need to **verify real execution outputs** using the product's APIs.

Create `LocaleDataProbe.java`:

~~~java
import java.lang.module.ModuleFinder;
import java.text.DateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Arrays;
import java.util.Locale;

public class LocaleDataProbe {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale fr = Locale.FRANCE;
        LocalDate day = LocalDate.of(2026, 10, 28);

        boolean hasModule = ModuleFinder.ofSystem()
                .find("jdk.localedata").isPresent();

        System.out.println("module present: " + hasModule);
        System.out.println("date vi available: "
                + Arrays.asList(DateFormat.getAvailableLocales())
                        .contains(vi));
        System.out.println("date fr available: "
                + Arrays.asList(DateFormat.getAvailableLocales())
                        .contains(fr));

        DateTimeFormatter longDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

        System.out.println("vi: "
                + longDate.withLocale(vi).format(day));
        System.out.println("fr: "
                + longDate.withLocale(fr).format(day));
        System.out.println("us: "
                + longDate.withLocale(Locale.US).format(day));
    }
}
~~~

Compile with JDK 17+:

~~~bash
javac -encoding UTF-8 LocaleDataProbe.java
~~~

Run on the full JDK:

~~~bash
java LocaleDataProbe
~~~

Example stdout verified on OpenJDK 24 with extended locale data:

~~~text
module present: true
date vi available: true
date fr available: true
vi: 28 tháng 10, 2026
fr: 28 octobre 2026
us: October 28, 2026
~~~

When running on a filtered runtime image or one without `jdk.localedata`, **outputs can differ**; in particular, never copy the full JDK's stdout verbatim as a fixed expectation for a slimmed image.

Analyzing the signals:

- `ModuleFinder.ofSystem().find("jdk.localedata")` checks whether the module **exists in the current system module set**. It does not prove the module was resolved in the boot layer, nor does it count locales retained after filtering.
- `DateFormat.getAvailableLocales()` lists locales advertised as available by the `DateFormat` service; it **does not** guarantee `java.time`, currency, and number services share the same data level or that every display string matches expectations.
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(...)` tests **actual formatting behavior** for the chosen date and locale.
- Date strings can change across JDK/CLDR providers; verify semantics and target environments rather than assuming localized strings stay immutable forever.

An available module might still be absent from the application's **resolved module graph**; inspect launcher flags and module resolution if a provider goes unused. In practice, testing outputs directly is indispensable.

## 10. Running the same class across multiple runtimes to compare

After compiling `LocaleDataProbe.java` to `LocaleDataProbe.class` in your working directory, run **the exact same class** with different launchers:

Linux/macOS:

~~~bash
java -cp . LocaleDataProbe
./image-base/bin/java -cp . LocaleDataProbe
./image-full-locale/bin/java -cp . LocaleDataProbe
./image-selected-locales/bin/java -cp . LocaleDataProbe
~~~

Windows PowerShell:

~~~powershell
java -cp . LocaleDataProbe
.\image-base\bin\java.exe -cp . LocaleDataProbe
.\image-full-locale\bin\java.exe -cp . LocaleDataProbe
.\image-selected-locales\bin\java.exe -cp . LocaleDataProbe
~~~

**Ensure the JDK version used to compile is compatible with the Java launcher inside the image.** If the class was compiled for Java 24 while the image runs Java 17, the program can throw `UnsupportedClassVersionError`; that is not a locale bug.

When comparing, hold constant:

1. Program bytecode, input date/time, and input numbers.
2. Explicitly passed `Locale`.
3. JDK/CLDR version where possible.
4. Provider selection, module graph, runtime environment, and relevant config variables.

Then vary **only the runtime image** to observe the effect of the locale data packaging. If you change both the JDK version and `java.locale.providers` simultaneously, attributing the cause of an output difference becomes very difficult.

## 11. Why doesn't fallback always throw an error?

A formatting service may fall back from a specific locale to a parent locale, another available data source, or root data per API/provider mechanics. If a user requests `vi-VN` on an image lacking matching data, you may see:

- Month/weekday names in an unexpected language.
- Date patterns with altered field order or punctuation.
- Different number grouping, decimal separators, or currency symbols.
- Country/currency display names reverting to codes or names in another locale.
- One service producing normal-looking output while another lacks localization.

**Never assert a single deterministic fallback string** across all JDK versions or providers. Exact outputs must be verified on the actual image.

The fact that `Locale.forLanguageTag("vi-VN")` succeeds, or that ISO date `2026-10-28` still formats, does not prove Vietnamese month names are present. A purely numeric formatter can mask missing locale data. Test parts that **genuinely must be localized**, such as `MMMM` or `FormatStyle.LONG`.

## 12. Testing NumberFormat and Currency on the image

Dates are not the only subject of locale data. A financial application should also verify number formatting and currency presentation.

Create `LocaleNumberProbe.java`:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class LocaleNumberProbe {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale fr = Locale.FRANCE;
        Currency usd = Currency.getInstance("USD");

        NumberFormat viNumber = NumberFormat.getNumberInstance(vi);
        NumberFormat frNumber = NumberFormat.getNumberInstance(fr);

        System.out.println("vi number: "
                + viNumber.format(1234.5));
        System.out.println("fr number: "
                + frNumber.format(1234.5));
        System.out.println("USD name vi: "
                + usd.getDisplayName(vi));
        System.out.println("USD name fr: "
                + usd.getDisplayName(fr));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocaleNumberProbe.java
java LocaleNumberProbe
~~~

**Do not prescribe a fixed stdout for this example**: number formats, whitespace (which may be NBSP/narrow NBSP), currency display names, and providers can differ across JDK/CLDR releases. The goal is to run **the same class on both images** and compare behavior.

Do not rely on visual comparison when special Unicode spaces are involved. If a test fails even though outputs look nearly identical, print code points (e.g., via `String.codePoints()`) to detect `U+00A0` or `U+202F`.

**Distinguish currency metadata from translated names:** the existence of `Currency.getInstance("USD")` does not prove its Vietnamese name or expected symbol is present in the runtime. When one API uses unit metadata and another uses locale-specific display data, module/locale presence must still be checked for the right service.

## 13. Locale providers and `java.locale.providers`

Java has a **Locale Service Provider** architecture. Locale data can come from different providers depending on version, runtime, and configuration. The modern JDK ecosystem relies broadly on **CLDR** data for localization.

The `java.locale.providers` system property configures the prioritized order/types of providers in supported releases. Example running the probe with CLDR:

~~~bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
~~~

When comparing, keep the exact same provider configuration on both the full JDK and the `jlink`-built image.

**Common traps:**

- Changing the provider property **does not restore** locale data that was stripped from the image.
- Legacy providers or valid configuration names can differ across JDK generations; do not blindly apply an old JDK's provider list to every new runtime.
- Adding a provider does not prove every service/locale is backed by that same provider.
- Changing the property too late at runtime might not switch already-initialized services; configure it at JVM startup when needed.

When diagnosing, record the Java version, module list, provider property, and actual formatted outputs before drawing conclusions.

## 14. True runtime customization: image vs. application

A custom runtime image is **distinct** from your application `.jar` or modules. `jlink` produces a runtime directory containing the Java launcher, modular system image, and associated resources. You still must distribute your application (or integrate via another packaging tool) according to your build model.

Common scenarios:

- **Modular applications** with `module-info.java`: the image needs the application module and its dependencies.
- **Classpath applications**: you can build an image with the needed JDK modules and run the classpath using the image's Java launcher.
- **Desktop applications**: `jpackage` can build on top of a custom runtime and platform installer.
- **Container/server applications**: the container's runtime image must contain the exact JDK modules needed, including `jdk.localedata` if non-base locale data is required.

Never treat `jlink --add-modules java.base,jdk.localedata` as a complete recipe for every real-world app. It merely illustrates locale data inclusion; application modules, service bindings, and dependencies must be determined separately.

A frequent mistake is having full `jdk.localedata` on the CI JDK while missing it in the Docker runtime image or desktop release bundle. Therefore, localization tests must run against the **final artifact**, not only on the build machine.

## 15. Image size and locale selection strategy

Packaging all of `jdk.localedata` generally yields a larger image than a minimal build. Filtering locales with `--include-locales` reduces bundled data, but filtering too aggressively triggers fallbacks whenever the app serves additional languages.

How to choose:

1. List the locales the product **commits to supporting**, including full language tags and region/script subtags where needed.
2. Identify used APIs: date/time, numbers/currencies, country names, collators, and app resources.
3. Account for **parent locales**, regions, and relevant extensions; consult `jlink` matching docs and verify empirically.
4. Add `jdk.localedata` and apply `--include-locales` appropriately.
5. Run probes on the new image and verify services per locale.
6. Measure image size, startup time, and localization quality; optimize only after ensuring correctness.
7. Whenever the product adds a locale, update the `jlink` configuration and regression tests together.

**Never assume** simply setting UI language to `vi` covers every formatting need for `vi-VN`, locale extensions, or other regions. At the same time, there is no need to ship all locales if the product genuinely serves and tests a small set.

## 16. A QA strategy for CI/CD

You can build an automated test suite with these steps:

### 16.1. Module check

Run the image's launcher:

~~~bash
./image-selected-locales/bin/java --list-modules
~~~

Confirm `jdk.localedata` appears when the image is required to support extended locale data.

### 16.2. Locale coverage check

Use `DateFormat.getAvailableLocales()` or the corresponding service's `getAvailableLocales()` API. Verify the list contains mandatory locales and flag any missing ones.

### 16.3. Actual output check

Format a fixed date `2026-10-28`, a number `1234.5`, and a specific currency using the requested locales. For Vietnamese, verify the month name is actually Vietnamese per product policy; for French, verify French month names.

**Do not check only string length or "no exception thrown."** A service experiencing fallback can still succeed while returning an unintended language.

### 16.4. Test the actual release image

In CI/CD, run tests **after creating the image** and before publishing. When shipping multiple images (Linux, Windows, macOS, or multiple architectures), test each target artifact; `jlink` normally produces runtimes tied to the source JDK's platform.

### 16.5. Archive build evidence

Record JDK version, module list, chosen language tags, build tool version, and probe outputs. When upgrading the JDK, CLDR data can change without source changes; review those diffs intentionally.

## 17. Misconceptions to avoid

| Misconception | Reality | How to handle |
| --- | --- | --- |
| `Locale.forLanguageTag` succeeding means data is present | It only constructs a locale identifier | Test providers and outputs |
| `java.base` contains all translations | Only baseline locale data in many JDKs | Add `jdk.localedata` when needed |
| Having `jdk.localedata` means having all locales | May have been filtered by `--include-locales` | Check actual locale coverage |
| Missing the module makes all locale APIs fail | APIs can still fall back | Inspect actual formatted outputs |
| `--include-locales` downloads/generates data | It selects data already inside the JDK | Build from an appropriate source JDK |
| `--include-locales` works without adding `jdk.localedata` | The plug-in requires the module | Add the module and verify outputs |
| App `ResourceBundle` files live in `jdk.localedata` | They are separate application resources | Package and test separately |
| `getAvailableLocales` guarantees full resources across all services | Each service/provider has its own traits | Test the specific APIs used |
| A missing locale always throws an exception | Fallback is usually silent | Check month names and number symbols |
| ISO dates/numbers working means full locale support | Numeric-only outputs hide missing data | Test month names and currencies |
| Provider property restores stripped data | The property only adjusts provider selection | Include the data in the image |
| Passing tests on a full JDK is sufficient | Release images have different modules/data | Run tests on the final artifact |
| JDK upgrades do not affect localized outputs | CLDR/data updates across versions | Pin/test runtimes when needed |
| Locale equals timezone | Locale and `ZoneId` are independent | Configure each context properly |

## 18. Practical checklist

1. **Source JDK:** verify `java -version` and `jlink --version` belong to the intended JDK build.
2. **Modules:** run `java --list-modules` on the custom image; check `jdk.localedata`.
3. **Jlink config:** when using `--include-locales`, include `jdk.localedata` in `--add-modules`.
4. **Languages:** list `vi-VN`, `fr-FR`, `ja-JP`, or other mandatory BCP 47 tags.
5. **Providers:** record `java.locale.providers` and avoid provider settings absent on the target JDK.
6. **Dates:** test month/weekday names and localized styles rather than only numeric ISO formats.
7. **Numbers:** test decimal separators, grouping, percentages, and negative numbers.
8. **Currencies:** test localized symbols/display names and proper precision.
9. **Locale listing:** call `getAvailableLocales` on the exact service under test.
10. **Fallback:** when a locale is missing, verify intended behavior or fail the release.
11. **ResourceBundle:** confirm application-provided bundles exist in the artifact.
12. **Packaged software:** verify the exact runtime invoked by the real launcher.
13. **Trial runs:** run the same probe class on both the full JDK and the slim image.
14. **Determinism:** use fixed test inputs rather than the current date/time.
15. **CLDR:** on JDK upgrades, distinguish expected data updates from missing-module bugs.
16. **Release:** automate testing against the shipped artifact, not solely source code or the CI host.

### Exercises

- Build a `java.base`-only image and run `LocaleDataProbe`. Compare the module list and `vi-VN` formatting against the full JDK.
- Build a `java.base,jdk.localedata` image without `--include-locales`. Compare with an image selecting `vi-VN,fr-FR`.
- Use `--include-locales=vi-VN` to build a Vietnam-focused image, then test `Locale.FRANCE` and explain the fallback.
- For `NumberFormat.getNumberInstance(Locale.FRANCE)`, print the code points of the formatted string to spot non-ASCII grouping spaces.
- Design a test for `Currency.getDisplayName(Locale.forLanguageTag("vi-VN"))` on the image and compare against the full JDK.
- Add `en-US`, `ja-JP`, and `vi-VN` to a test matrix, specifying which are product commitments and which fallbacks are acceptable.
- Write a build pipeline that fails if the release image lacks the module or fails formatting checks for required locales.

## 19. Conclusion

`java.base` provides core APIs and baseline locale data; **`jdk.localedata` supplies extended locale data** in documented JDK releases. When building custom runtime images with `jlink`, include `jdk.localedata` if localization beyond the baseline set is required, and optionally filter data via **`--include-locales`** to reduce footprint.

**An existing `Locale` does not guarantee formatting data exists.** Therefore, do not stop at verifying the code runs—verify the image's own launcher, module list, available locale set, and actual date/number/currency formatting outputs. At the same time, keep application translation resources separate from JDK data and maintain consistent runtime/CLDR versions during testing.

The right choice is not "package every locale" at any cost, but rather **package the exact locales your product commits to supporting and test directly on the shipped runtime image**.

## Official references

- [Oracle JDK 17 — Supported Locales, Locales and Modules](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html)
- [Oracle Java 21 — jlink command and include-locales plug-in](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Oracle Java 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html)
- [Oracle Java 21 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [OpenJDK — jlink: The Java Linker (JEP 282)](https://openjdk.org/jeps/282)
