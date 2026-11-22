# Service Registration, Startup Configuration, and Capability Verification in Java Localization

## 1. Context: Writing a Provider Class Alone Is Not Enough for Java to Use It

Java provides multiple extensible localization services: number formatting, date/time formatting, locale names, time zone names, language-specific string collation, and text segmentation rules. A project may need to add data for a specialized locale or customize a formatter that the JDK's built-in data does not satisfy.

Suppose you write a class extending `java.text.spi.NumberFormatProvider`. Having the class **compile cleanly** does not mean `NumberFormat.getNumberInstance(locale)` will automatically invoke it. To extend the system properly, you must fulfill **three distinct responsibilities**:

1. **Service registration:** package the class and declare the service provider accurately on the **classpath** or **module path**.
2. **Startup configuration:** instruct the JDK to consider the `SPI` source in the proper order within `java.locale.providers`.
3. **Capability verification:** verify that the provider is discovered, advertises the right locales, is actually selected by the factory, falls back properly, and implements the service's semantics accurately.

These three steps are the core subject of this lesson in the **Packaging and Extensibility** group. A successful deployment must satisfy all three; having only a `META-INF/services` file or only a `-D` flag is not enough.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish **service type**, **implementation**, **service registry**, **provider preference**, and **selected provider**.
- Package a `NumberFormatProvider` with `META-INF/services` using `javac`/`jar` on Java 17+.
- Place `-Djava.locale.providers=SPI,CLDR` properly at JVM startup; understand why `CLDR,SPI` can yield different results.
- Use `ServiceLoader` as a registration check, while understanding why **discovered does not mean selected**.
- Use `getAvailableLocales()` and `isSupportedLocale(...)` to verify provider scope, including locale extension concerns.
- Verify fallback behavior with a locale unsupported by the custom provider.
- Know how to declare `provides ... with ...` in JPMS and distinguish classpath from module path.
- Diagnose registration, packaging, startup property, supported locale, provider semantics, and multi-source conflict bugs.
- Avoid depending on legacy `COMPAT` locale data after upgrading to JDK 23+.

## 2. Two Mechanisms to Understand: Java SPI and Locale Provider Order

### 2.1. Java SPI (Service Provider Interface)

An SPI is a contract allowing Java or an application to load pluggable implementations. In localization, the abstract provider classes reside in:

- `java.text.spi`: `NumberFormatProvider`, `DateFormatProvider`, `CollatorProvider`, `DecimalFormatSymbolsProvider`, and related SPIs.
- `java.util.spi`: `LocaleServiceProvider` (root class), `CurrencyNameProvider`, `LocaleNameProvider`, `TimeZoneNameProvider`, etc.

Example class:

```java
public final class PrefixNumberProvider
        extends NumberFormatProvider {
    // Must implement the required abstract methods.
}
```

This class alone will not be discovered. It must be declared via a **provider-configuration file** or module metadata. Its artifact must also be placed on the actual classpath/module path of the Java process running the application.

### 2.2. java.locale.providers Controls Source Precedence

`java.locale.providers` is a system property taking a comma-separated list of providers, for example:

```text
SPI,CLDR,COMPAT
```

On JDK 17, a common interpretation is:

1. `SPI`: try implementations installed by the application/libraries for matching services/locales.
2. `CLDR`: try the JDK's Unicode CLDR data if the previous step did not satisfy the request.
3. `COMPAT`: try legacy data, if the JDK still supports it and no earlier source matched.

**On JDK 23 and later, COMPAT/JRE data has been removed.** Keeping `COMPAT` in the configuration string will not bring legacy formatters back. For modern runtimes, a typical configuration is:

```bash
java -Djava.locale.providers=SPI,CLDR ...
```

**The two mechanisms are independent:** `META-INF/services` helps the JVM find the implementation; `java.locale.providers` instructs locale service lookup to evaluate the `SPI` source in order. Without registration, the provider is never discovered; without including `SPI` in the JDK's provider preference on the classpath, the implementation may be present yet never used by the factory.

### 2.3. Discovered and Selected Are Two Distinct States

| Question | How to verify | What it does not prove yet |
| --- | --- | --- |
| Is the provider class in the JAR? | `jar --list --file` or inspect artifact structure. | Does not prove service registry is right. |
| Is the `META-INF/services` file in the JAR? | Verify path and UTF-8 contents. | Does not prove the provider class can be loaded. |
| Does `ServiceLoader` see the class? | Iterate `ServiceLoader.load(NumberFormatProvider.class)`. | Does not prove the factory selected it. |
| Does the provider declare locale support? | `getAvailableLocales()`, `isSupportedLocale(locale)`. | Does not prove the formatter returns valid output or wins precedence. |
| Does the actual factory use the implementation? | Call `NumberFormat.getNumberInstance(locale)` under different startup configs; instrument methods if needed. | Does not guarantee every other service/locale uses SPI. |
| What happens when the provider does not support a locale? | Test out-of-scope locales. | Must verify fallback and compatibility policy. |

**Do not treat `ServiceLoader` returning an instance as sufficient proof.** A JAR can be loaded cleanly while the runtime still prefers CLDR if the startup option is `CLDR,SPI`, or if the method requests a locale the SPI declines.

## 3. Which Providers Are Typically Available in the JDK?

| Provider | Role | Limitations |
| --- | --- | --- |
| `CLDR` | Unicode Common Locale Data Repository data, widely used on modern JDKs. | Data can change across JDK versions; not every service uses a single source identically. |
| `SPI` | Providers installed by applications or libraries. | Requires implementation, registration, packaging, startup preference, and testing. |
| `HOST` | Certain locale data or custom settings from the OS. | OS/vendor-dependent; not available on all platforms. |
| `COMPAT` / alias `JRE` | Legacy data compatible with older JDKs. | Present in JDK 17; removed starting in JDK 23. |

The default on Oracle/OpenJDK 17 is equivalent to `CLDR,COMPAT`. On Java 23+, legacy `COMPAT` is gone and the dominant default source is `CLDR`.

When extending **a specific locale/service**, do not add `HOST` or `COMPAT` to the list just to have "more choices." Favor an explicit, deterministic configuration suited to your needs, then test on the target JDK.

## 4. Designing the Example: Extending NumberFormat for an Existing Locale

This example uses `Locale.FRANCE` so we can easily **observe precedence conflicts**: the JDK's CLDR already supports that locale; an SPI configured ahead of CLDR can override certain number-formatting behaviors for that very locale.

Demo behavior:

- `NumberFormat.getNumberInstance(Locale.FRANCE).format(12.5)` via the custom provider produces `SPI:12.50`.
- Under typical JDK CLDR French number formatting, the same number produces `12,5`.
- `Locale.US` is not declared supported by the custom provider, so it continues using the JDK formatter, producing e.g. `12.5`.
- The provider is discovered via `ServiceLoader` yet may **not be selected** when `CLDR` precedes `SPI`.

**Note:** the `SPI:` prefix and dot decimal separator in the example are **verification markers for this lab**, not French formatting conventions to ship in a product. A production custom provider must have genuinely locale-appropriate data and semantics without injecting test markers into user output.

### Sample Directory Tree

Create a standalone directory without needing Maven/Gradle:

```text
spi-demo/
├── src/
│   └── demo/
│       ├── PrefixNumberProvider.java
│       └── ProviderCheck.java
└── resources/
    └── META-INF/
        └── services/
            └── java.text.spi.NumberFormatProvider
```

Both classes are in package `demo`; the service registry file sits at `resources/META-INF/services/java.text.spi.NumberFormatProvider`. The file name **must match the fully qualified name of the SPI class**, not the implementation class name.

## 5. First File: The NumberFormatProvider Implementation

Save to `src/demo/PrefixNumberProvider.java`:

```java
package demo;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public final class PrefixNumberProvider
        extends NumberFormatProvider {

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { Locale.FRANCE };
    }

    @Override
    public boolean isSupportedLocale(Locale locale) {
        Objects.requireNonNull(locale, "locale");
        // Example accepts only exact fr-FR, without extensions.
        return Locale.FRANCE.equals(locale);
    }

    private static DecimalFormat create(String pattern) {
        return new DecimalFormat(
                pattern,
                DecimalFormatSymbols.getInstance(Locale.ROOT));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return create("'SPI:'#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        DecimalFormat format = create("'SPI:'#,##0");
        format.setParseIntegerOnly(true);
        return format;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                "'SPI:'¤#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.FRANCE));
        format.setCurrency(Currency.getInstance("EUR"));
        return format;
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        // The % sign in a DecimalFormat pattern carries multiply-by-100 semantics.
        return create("'SPI:'#,##0%");
    }
}
```

**This is a complete Java class compilable on JDK 17+.** It implements the four basic abstract methods of `NumberFormatProvider`. It is not a full production library: a real implementation would also need to handle all parsing, rounding, currencies, Unicode numbering systems, locale variants, and UI requirements.

### Why Does getAvailableLocales Matter?

`getAvailableLocales()` advertises the locales for which the provider supplies objects/data. In the example:

```java
return new Locale[] { Locale.FRANCE };
```

If you advertise a locale without a matching implementation, the runtime may pick the wrong provider and receive unexpected output. Never return all locales just to "get called more often."

### isSupportedLocale and Unicode Extensions

`LocaleServiceProvider.isSupportedLocale(locale)` by default compares available locales while **ignoring locale extensions**. Certain extensions (such as numbering system `u-nu-...`) can change number-formatting requirements. If an implementation does not support that extension, define clear handling rather than accepting and silently ignoring it.

This example overrides `isSupportedLocale` with `Locale.FRANCE.equals(locale)`, accepting only **exact fr-FR without extensions**. In real applications, define a support matrix for language tags, scripts, regions, Unicode extensions, and locale fallbacks rather than checking only country strings.

### Why Does the Factory Construct DecimalFormat Directly?

If inside `getNumberInstance(Locale.FRANCE)` you called:

```java
return NumberFormat.getNumberInstance(Locale.FRANCE);
```

while `SPI` has priority, that call could loop back into the same provider, causing recursion. The demo avoids this bug using `new DecimalFormat(pattern, symbols)` with `DecimalFormatSymbols.getInstance(Locale.ROOT)` for the test numeric case, without re-entering the `NumberFormat` factory for the served locale.

**Note:** other locale services can have their own SPIs. If your provider depends on another factory, analyze the dependency chain to prevent loops or unexpected data when multiple SPI services are active.

## 6. Second File: Probe to Verify Discovery and Selection

Save to `src/demo/ProviderCheck.java`:

```java
package demo;

import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;
import java.util.ServiceLoader;

public final class ProviderCheck {

    public static void main(String[] args) {
        System.out.println("configured="
                + System.getProperty(
                        "java.locale.providers", "<default>"));

        boolean found = false;
        for (NumberFormatProvider provider :
                ServiceLoader.load(NumberFormatProvider.class)) {

            if (provider.getClass().getName().equals(
                    "demo.PrefixNumberProvider")) {
                found = true;
                System.out.println("supportsFR="
                        + provider.isSupportedLocale(Locale.FRANCE));
                System.out.println("supportsUS="
                        + provider.isSupportedLocale(Locale.US));
            }
        }
        System.out.println("discovered=" + found);

        System.out.println("frNumber="
                + NumberFormat.getNumberInstance(
                        Locale.FRANCE).format(12.5));
        System.out.println("usNumber="
                + NumberFormat.getNumberInstance(
                        Locale.US).format(12.5));
    }
}
```

This program **does not assume `discovered=true` means the JDK selected the SPI**. It measures three distinct things:

1. Did `ServiceLoader` find `demo.PrefixNumberProvider`?
2. Does that class report supporting fr-FR while rejecting en-US?
3. Does the output of the **actual factory** change when provider order changes?

The iteration order of `ServiceLoader` can vary when multiple libraries are on the classpath; the demo prints details only for the named class and a single `discovered` line. If another library ships an SPI of the same type and locale, review precedence across implementations and deployment policies.

### Direct ServiceLoader Differs from Locale Service Lookup

`ServiceLoader.load(NumberFormatProvider.class)` finds registered service implementations; it does not require `java.locale.providers` to include `SPI` in order to **enumerate** them in the general `ServiceLoader` sense. By contrast, `NumberFormat.getNumberInstance(...)` is a locale-sensitive factory dispatched by the JDK according to provider preferences.

Thus, it is entirely possible to see:

```text
discovered=true
frNumber=12,5
```

This is **not a contradiction**. The provider was discovered, yet `CLDR` may have satisfied the request before reaching `SPI`.

## 7. Third File: Registration in META-INF/services

Create a plain text file **with no extension**:

```text
resources/META-INF/services/java.text.spi.NumberFormatProvider
```

Contents: **exactly one line**, the fully qualified provider class name:

```text
demo.PrefixNumberProvider
```

Per the `ServiceLoader` contract:

- The service file name must be the **fully qualified name** of the SPI: `java.text.spi.NumberFormatProvider`.
- Contents consist of one or more concrete class names, one per line.
- The file must be saved in **UTF-8**.
- The class must be loadable, accessible, and instantiable by the appropriate class loader.
- Blank lines and `#`-prefixed comments are ignored.
- Do not put `demo.ProviderCheck` instead of the provider; that is the test driver class, not an SPI implementation.
- Multiple providers can be listed on separate lines, but capability boundaries must be managed clearly without relying on arbitrary ordering when other JARs also register services.

**PowerShell 5.1 note:** certain text-writing methods like `Set-Content -Encoding UTF8` can prepend a UTF-8 BOM. The service registry expects UTF-8; a BOM can corrupt parsing of the first provider name in the file. Use an editor saving **UTF-8 without BOM** or a build-tool-controlled resource generator; do not save as UTF-16 or add a `.txt` extension.

### The JAR Must Contain Resources at the Exact Path

After packaging, the JAR must contain:

```text
META-INF/services/java.text.spi.NumberFormatProvider
demo/PrefixNumberProvider.class
demo/ProviderCheck.class
```

Having only class files without service metadata leaves `ServiceLoader` unable to find the implementation. Having only metadata without the class triggers `ServiceConfigurationError` when loading providers.

## 8. Compiling, Packaging, and Running from the Command Line

Run from the `spi-demo` directory containing `src` and `resources`.

### Step 1: Compile Both Classes

```bash
javac -encoding UTF-8 -d out src/demo/PrefixNumberProvider.java src/demo/ProviderCheck.java
```

`-encoding UTF-8` specifies the encoding of Java source files; it **does not automatically set all runtime data encodings**. `-d out` places `.class` files into the matching package directories under `out`.

### Step 2: Create a JAR Containing Classes and Resources

```bash
jar --create --file spi-demo.jar -C out . -C resources .
```

This JDK 17+ `jar` command packages both compiled classes and `META-INF/services` into the JAR. You can inspect the entry list:

```bash
jar --list --file spi-demo.jar
```

Verify that `META-INF/services/java.text.spi.NumberFormatProvider` and `demo/PrefixNumberProvider.class` are present. Listing entries only confirms presence, not that the service file contents are valid; if `discovered=false`, inspect the resource contents inside the artifact and any runtime errors separately.

### Step 3: Run in a **Fresh JVM** with SPI Prioritized

```bash
java -Djava.locale.providers=SPI,CLDR -cp spi-demo.jar demo.ProviderCheck
```

**Expected stdout** on JDK 17+ with active SPI and matching CLDR:

```text
configured=SPI,CLDR
supportsFR=true
supportsUS=false
discovered=true
frNumber=SPI:12.50
usNumber=12.5
```

The `frNumber` line containing `SPI:` proves the factory actually used the custom implementation in this test configuration; `usNumber` shows that other locales still use built-in JDK data.

### Step 4: Start Another Process with CLDR Prioritized

```bash
java -Djava.locale.providers=CLDR,SPI -cp spi-demo.jar demo.ProviderCheck
```

On runtimes where CLDR supports `fr-FR`, such as common modern JDKs, example output:

```text
configured=CLDR,SPI
supportsFR=true
supportsUS=false
discovered=true
frNumber=12,5
usNumber=12.5
```

Notice `discovered=true` remains unchanged, yet the `frNumber` factory output no longer carries the `SPI:` prefix. Because `CLDR` has precedence and supplies data for that service/locale, the custom implementation is not selected to format this number.

**Do not treat a specific CLDR output as a fixed protocol across all JDKs.** Locale data can change across JDK/vendor releases; however, on this environment, the test clearly demonstrates provider priority.

### Step 5: Run Without Putting the SPI JAR on the Classpath

If you want to observe the JDK formatter alone, create a standalone Java main class that does not reference the implementation and run without the provider JAR. **Do not run `demo.ProviderCheck` with an empty classpath**, because the main class itself lives inside `spi-demo.jar`. To simulate a missing SPI resource, build a separate test artifact **with the main class but without provider registration**, and observe `discovered=false`; do not delete or alter the original deployed artifact.

### Step 6: Repeat on the Target JDK and OS

Record the JDK vendor/version, `java.locale.providers`, tested locales/services, and per-process output. Across version upgrades, output shifts may originate from CLDR data or SPI rules; do not jump to blaming the compiler or encoding.

## 9. Placing Startup Configuration in the Right Spot

### 9.1. Order of JVM Options vs. Application Args

**Right:**

```bash
java -Djava.locale.providers=SPI,CLDR -cp spi-demo.jar demo.ProviderCheck
```

**Wrong:**

```text
java -cp spi-demo.jar demo.ProviderCheck -Djava.locale.providers=SPI,CLDR
```

The wrong line places `-D` **after the class name**, so it is passed as `args[]` to the application rather than as a JVM startup system property.

With an executable JAR specifying `Main-Class`:

```bash
java -Djava.locale.providers=SPI,CLDR -jar application.jar
```

**Set the property on the launcher of the actual running JVM**, not merely in the terminal used for compiling. Maven Surefire, Gradle Test, IDE Run/Debug configurations, Docker entrypoints, and application servers must all be checked against the specific JVM process they spawn.

### 9.2. Do Not Change via System.setProperty After Initialization

`java.locale.providers` is read at runtime startup; JDK 17 documentation notes that calling:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
```

**after the JVM is running does not change the selected provider order**. Therefore, to compare `SPI,CLDR` against `CLDR,SPI`, launch two separate processes rather than mutating the property mid-process and reformatting.

Similarly, `Locale.setDefault(Locale.FRANCE)` changes the JVM's default locale, not the provider property. In multi-user applications, pass explicit locales to factories instead of changing the JVM-wide default per request.

### 9.3. Configuration Across JDK Versions

- **JDK 17:** defaults to equivalent of `CLDR,COMPAT`; classpath SPIs require including `SPI` in preferences.
- **JDK 21–22:** `COMPAT/JRE` is deprecated for removal; prepare migration.
- **JDK 23+:** legacy `COMPAT/JRE` data has been removed. Configuring `SPI,CLDR` remains useful when a custom SPI is present and supported.
- **HOST:** platform-dependent and does not replace testing custom SPI providers.

When stable output is required for protocols, format data with schemas/ISO formats or explicit patterns; never treat CLDR output as an immutable storage key.

## 10. JPMS: Registering in a Named Module

If a project implements the provider inside a **Java named module**, instead of traditional classpath resources you can declare the provider in `module-info.java`:

```java
module custom.locale.provider {
    provides java.text.spi.NumberFormatProvider
        with demo.PrefixNumberProvider;
}
```

On the **consumer named module** side if using `ServiceLoader` directly:

```java
module locale.demo.app {
    uses java.text.spi.NumberFormatProvider;
}
```

These are **two separate module descriptors**; they do not replace each other inside one `module-info.java`. A main application calling `NumberFormat.getNumberInstance(...)` may not call `ServiceLoader` directly, so it does not necessarily need to declare `uses` merely to invoke Java core factories. However, if a consumer calls `ServiceLoader.load(NumberFormatProvider.class)` itself inside a named module, `uses` is required for the service dependency.

With modules, the provider must:

1. Have an implementation class meeting module/service-loader requirements.
2. Have `provides ... with ...` in the provider module.
3. Be placed on the module path and **resolved into the module graph** appropriately.
4. Be considered by JDK locale services when `SPI` is present in `java.locale.providers`.
5. Have tests verifying discovery on the actual Java CLI and in real packaging tools.

An illustrative module launch command:

```bash
java -Djava.locale.providers=SPI,CLDR --module-path mods -m locale.demo.app/demo.ProviderCheck
```

The command above is **illustrative syntax only**, assuming you have compiled both named modules into `mods`, configured `requires`/`provides`/`uses` properly, and ensured the provider module is resolved. It is **not the run command for the classpath JAR in section 8**.

### Should Both META-INF/services and provides Be Included Simultaneously?

Do not assume classpath and named-module packaging work identically. For **explicit named modules**, service provision should be declared in the module descriptor. For **classpath JARs**, `META-INF/services` is the traditional mechanism.

When a library supports both classpath and module path, build/deploy pipelines must test each mode to avoid duplicate services, unloaded services, or unresolved provider modules. `Automatic modules` and fat JARs/shading follow their own rules; do not rename extensions and assume service discovery keeps working.

## 11. Verifying "Supports Locale" Is Not the Same as "Is Selected"

### 11.1. Checking Provider-Local Capability

`getAvailableLocales()` returns the array of locales advertised by the provider. `isSupportedLocale(locale)` is a finer-grained check that can inspect Unicode extensions. Both verify **whether the provider claims support**.

`LocaleServiceProvider` documentation notes that the default `isSupportedLocale` typically ignores extensions. In our demo, we overrode it to accept exact `Locale.FRANCE`, avoiding claiming support for numbering extensions our implementation does not handle.

**Do not infer** that simply seeing `Locale.FRANCE` in `NumberFormat.getAvailableLocales()` means your custom SPI won. JDK CLDR also supports that locale; the method returns aggregated capability, not a trace of which provider was chosen.

### 11.2. Checking Discovery

`ServiceLoader.load(NumberFormatProvider.class)` confirms that the implementation is registered and loadable in the corresponding class loader/module context.

If `ServiceConfigurationError` occurs, check the file name, FQCN, constructor, class visibility, dependencies, module errors, and UTF-8 encoding. Do not catch broadly and silently return `false` in production: that hides critical packaging failures.

### 11.3. Checking Selection via Distinct Behavior and Instrumentation

Only when the factory actually executes custom behavior can you say the SPI was selected for the **tested service and locale**. The demo uses the `SPI:` prefix in output. In production, write tests using test-environment markers/spies or logging inside the provider implementation, rather than injecting test markers into user-facing output.

**Testing one locale does not prove every service uses that provider**: `NumberFormatProvider` does not control `DateFormat`, `DecimalFormatSymbolsProvider`, or `Collator`. Each service has its own lookup mechanism and support scope.

### 11.4. Checking Fallback

A provider declaring only fr-FR must not hijack en-US formatting. In the demo, `supportsUS=false` and the en-US factory uses JDK data. When production providers support many locales, add tests for unsupported locales to catch over-broad declarations or unexpected fallbacks.

### 11.5. Checking After JDK Upgrades

CLDR locale data can evolve across JDK versions; record exact code points when comparing Unicode whitespace. `12 345,67` may contain U+0020, U+00A0, or U+202F grouping spaces despite looking nearly identical. Never store formatted strings as the source of truth for numeric values.

## 12. Common Mistakes When Packaging SPIs

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| `discovered=false` | Missing `META-INF/services`, wrong FQCN, provider JAR not on classpath. | `jar --list --file`, inspect resource, check launcher. |
| `ServiceConfigurationError` | Invalid UTF-8 in service file, missing class name, unloadable provider, or missing valid constructor. | Inspect root cause exception and class/module dependencies. |
| `discovered=true` yet no `SPI:` prefix | `CLDR` precedes `SPI` or locale/service outside support scope. | Check `-Djava.locale.providers` and test factory with fr-FR. |
| `supportsFR=false` | `getAvailableLocales` or `isSupportedLocale` declared inaccurately. | Test `Locale.FRANCE`, extensions, and country/language directly. |
| `supportsUS=true` unexpectedly | Provider declared too broadly. | Constrain support matrix; test out-of-scope locales. |
| Maven/Gradle behaves differently from IDE | Different JVM options passed to processes. | Print `System.getProperty` inside the actual process. |
| Calling `System.setProperty` has no effect | Locale provider order was read at startup. | Launch a fresh JVM with `-D`. |
| Provider re-calls factory for same locale | Risk of recursion or unexpected looping. | Construct formatter directly or use non-reentrant dependencies. |
| Wrong currency/percent provider output | Fails corresponding formatter semantics. | Test percent, currency, negatives, grouping, rounding, and parsing. |
| Prefix works on one JDK but not another | Changed source order/vendor/data or deployment. | Record JDK version, provider options, and artifact registry. |
| Fat JAR loses service registry | Shading/assembly failed to merge `META-INF/services`. | Inspect final artifact and run integration tests. |
| Named module misses provider | Missing `provides`, `uses`, or unresolved provider module. | Check module descriptors, module path, and module graph. |
| CLDR output changed after JDK upgrade | CLDR data updated; `COMPAT` removed. | Run regression tests and use invariant formats where needed. |

### Do Not Violate Service Semantics

A provider can be discovered and invoked while still being **wrong**. A production `NumberFormatProvider` must return formatters that satisfy their purpose:

- `getNumberInstance`: standard locale number presentation.
- `getIntegerInstance`: integer formatting/parsing per contract.
- `getCurrencyInstance`: currency, symbol, placement, rounding, and currency units.
- `getPercentInstance`: ratios and percent semantics (typically multiplying values by 100).
- Parsing, negative signs, grouping, Unicode digits, and special values must be tested if the domain supports them.

Do not merely stub out the four methods to satisfy the compiler. **Support capability** is a behavioral commitment, not just an array of `Locale`s.

## 13. Testing and Accepting a Provider

Recommended test matrix:

| Test | How to test | What to prove |
| --- | --- | --- |
| Compile | `javac -encoding UTF-8` | Class/provider API valid for JDK 17+. |
| JAR registry | `jar --list --file` | Resource at right path, not stripped by build tool. |
| Discovery | `ServiceLoader` | Implementation loads on actual classpath/module path. |
| Capability | `getAvailableLocales`, `isSupportedLocale` | Matches advertised locales/extensions. |
| Selection | `SPI,CLDR` then `CLDR,SPI` in two processes | Source order dictates chosen provider when both support a locale. |
| Fallback | `Locale.US` outside custom scope | Does not hijack formatters for other locales. |
| Startup | Place `-D` before class/`-jar` | Configuration reaches the actual JVM. |
| Alternative startup | Try `System.setProperty` after init | Confirm mid-run chain mutation is not relied upon. |
| Formatter semantics | Negatives, currency, integer, percent, parse | Output genuinely matches formatter type. |
| Unicode locale | Locales with digits or extensions | Provider has explicit policy instead of faking support. |
| Upgrade | JDK 17, 21, 23+ | No reliance on legacy `COMPAT` in newer JDKs. |
| Concurrency | Multiple requests/threads | Mutable formatters are not unsafely shared. |
| Final artifact | Classpath JAR and named module if needed | Both deployment modes resolve the provider properly. |

### Beware Mutable NumberFormat Instances

`NumberFormat` and `DecimalFormat` are mutable and not inherently thread-safe. A provider should create a **new formatter instance** per factory call, or manage synchronization safely if pooling/caching. Never return one shared `static DecimalFormat` and let concurrent requests mutate currency/rounding without synchronization.

The demo class creates a new formatter each time, suited for testing. For high-throughput applications, benchmark the real workload and design safe reuse without sacrificing correctness.

### Choose Stable Contracts for Machine-to-Machine Data

When passing values to another service, never store `SPI:12.50` or `12,5` as the raw monetary value. Keep `BigDecimal`/typed numeric values alongside an explicit currency code; let the UI format by locale/provider. That way, changing providers or CLDR versions never alters the meaning of stored data.

## 14. Practice Exercises

**Exercise 1 — Standard registration:** build the `src/demo` and `resources/META-INF/services` layout shown in this lesson. Intentionally misname the registry file and run `ProviderCheck`. Observe `discovered=false`, fix the name, and run from the **final JAR**, not just the IDE.

**Exercise 2 — Checking order:** run `SPI,CLDR` and `CLDR,SPI` in two separate Java processes. Explain why `discovered=true` in both while `frNumber` can differ.

**Exercise 3 — Locale/extension support:** call `isSupportedLocale(Locale.FRANCE)`, `isSupportedLocale(Locale.US)`, and an fr-FR locale with Unicode extension `u-nu-thai` directly. Update the support check only if the provider genuinely handles that numbering system properly.

**Exercise 4 — Fallback:** using a provider supporting only `Locale.FRANCE`, test `Locale.US` and `Locale.forLanguageTag("vi-VN")`. Do not try to force the SPI to win every locale; verify what continues using CLDR/JDK.

**Exercise 5 — Fixing packaging errors:** omit the provider class from a test JAR while keeping the service file; observe `ServiceConfigurationError`. Build a separate test artifact rather than modifying a deployed JAR.

**Exercise 6 — NumberFormat semantics:** expand unit tests for `getIntegerInstance`, `getCurrencyInstance`, and `getPercentInstance`. Verify `0.125` formatted as a percent, negative numbers, grouping, rounding, and parsing. Distinguish syntactic validity from linguistically accurate formatting.

**Exercise 7 — Named modules:** build two independent modules; the provider declares `provides ... with ...`, and the consumer declares `uses ...` if calling `ServiceLoader` itself. Configure the module path properly and confirm the provider resolves.

**Exercise 8 — JVM startup:** test setting the property in your IDE, test forks, and an application server. Record JVM args, in-process properties, and JDK vendor/version. Explain why setting the property on a build tool's JVM does not necessarily apply to the application JVM.

**Exercise 9 — JDK migration:** compare an environment on JDK 17 (with `COMPAT`) against JDK 23+ (without `COMPAT`), verifying provider behavior under `SPI,CLDR` and fallback policies. Do not treat legacy data as mandatory across all Java 17+ environments.

### Completion Checklist

- [ ] Understand how SPI differs from implementation class and provider preference.
- [ ] Package UTF-8 `META-INF/services/java.text.spi.NumberFormatProvider` properly.
- [ ] Provide a public class implementing all abstract methods; know how to package the JAR.
- [ ] Place `-Djava.locale.providers=SPI,CLDR` in the right position at startup.
- [ ] Distinguish `ServiceLoader` discovery from factory selection.
- [ ] Use `getAvailableLocales`/`isSupportedLocale` for the support matrix.
- [ ] Test fallback with other locales and test the same locale with different provider orders.
- [ ] Know the `provides`/`uses` mechanism when using named modules.
- [ ] Never mutate the provider chain via `System.setProperty` after runtime initialization.
- [ ] Do not depend on `COMPAT/JRE` on JDK 23+.
- [ ] Test formatter semantics, locale extensions, concurrency, and the final packaged artifact.
- [ ] Never store display strings as machine-to-machine data protocols.

## 15. Official References

- **JDK 17 LocaleServiceProvider** — packaging, `getAvailableLocales`, `isSupportedLocale`, and `java.locale.providers`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- **JDK 17 NumberFormatProvider** — factory methods to implement: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html
- **JDK 17 ServiceLoader** — provider configuration and service discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **JDK 23 Migration — COMPAT removal**: https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html

**Conclusion:** extending localization in Java must follow the chain **correct service registration -> timely JVM configuration -> verified discovery, capability, selection, and fallback**. `ServiceLoader` seeing a class does not mean the locale factory selects it; having `SPI` in the property is not enough if the artifact or service file is wrong; `getAvailableLocales` is only a capability declaration, not proof of accurate formatting. Always test end-to-end on the **actual JAR/module and target JDK** before considering a provider operational.
