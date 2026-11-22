# Distinguishing Application Locale Selection from the `ResourceBundle` Fallback Mechanism

## 1. Two Different Decisions Often Confused as One

A Java application supporting multiple languages typically has to answer **two questions** before displaying a message:

1. **Which locale does the application choose for the current user/request?** For example, based on the user's saved language, the `Accept-Language` header, the locales the product actually supports, and the product-defined default locale.
2. **Given the chosen locale, which resource file does `ResourceBundle` load and where does a key come from?** Java searches candidate bundles, may try the JVM's default locale, and inherits keys from parent bundles.

The first question is **application policy** (application locale selection/negotiation); the second is a **resource lookup mechanism** (resource-bundle lookup/fallback). They are related, yet do not replace each other.

For example: a user requests Canadian French (`fr-CA`), while the product only provides `vi-VN` and `en-US`. The application can intentionally choose `vi-VN` as the product fallback. If you skip this step and call `ResourceBundle.getBundle("Messages", Locale.CANADA_FRENCH)` directly, Java may resolve resources using the server's default locale, such as `en-US`. These are **two decisions leading to two different outcomes**.

> **Principle:** The UI locale must be decided at the application layer; the bundle found is the vehicle that supplies translation data. Do not infer backward “which locale the application is using” merely from the loaded bundle file.

## 2. Four Layers to Distinguish

| Layer | Input | Decision | Example |
| --- | --- | --- | --- |
| User preference | Account settings, HTTP request | Which language the user **wants** | `fr-CA` |
| Application locale selection | Preferences + supported locales list + product fallback | Which locale the UI **will use** | `vi-VN` |
| `ResourceBundle` selection | Base name, application locale, classpath/module, and lookup rules | Which bundle **gets loaded** | `Messages_vi.properties` |
| Key lookup in bundle | `getString("button.save")` | Value from current bundle or parent bundle | `Messages.properties` |

An illustrative flow:

```text
User preference: fr-CA
          |
          v
[APPLICATION POLICY]
Supported: vi-VN, en-US
No fr -> product fallback: vi-VN
          |
          v
Application locale: vi-VN
          |
          v
[RESOURCEBUNDLE LOOKUP]
Messages_vi_VN? (no)
Messages_vi?    (yes) ---> select vi bundle
Messages?       (yes) ---> parent for missing keys
          |
          v
getString("greeting")   -> from Messages_vi
getString("button.save")-> from Messages (base)
```

Here there are **three kinds of fallback** to name accurately:

- **Product locale selection fallback:** from an unsupported preference to a locale the application declares supported; defined by the application.
- **Bundle selection fallback:** from a specific candidate locale (`vi-VN`) to a broader locale (`vi`), possibly to the base bundle, and with default `getBundle` there is also the rule of trying the JVM default locale.
- **Key value fallback:** when the selected bundle lacks `button.save`, `getString` can walk the parent bundle chain to find the key.

The event “selected `Messages_vi`” does not prove the application changed locale `vi-VN` into `vi`. It only indicates the most specific resource available for that content.

## 3. The Application Layer Decides the Locale Before Loading Resources

An application must explicitly define **supported locales** (the locales it can serve) and **product fallback locale** (the product's default locale). This data **does not appear automatically** simply by calling `ResourceBundle.getBundle`.

Common preference sources, under product-specific policy:

1. A language choice saved in the account or temporarily selected in the UI.
2. Client-sent preferences, such as `Accept-Language: fr-CA,fr;q=0.9,en-US;q=0.7`.
3. A default locale configured for the product, such as `vi-VN`.

The application can prioritize explicit choices over headers, but it must define and test the priority order itself. `Accept-Language` is a **weighted priority list**, not a single BCP 47 language tag; therefore, do not pass the entire header string into `Locale.forLanguageTag(...)`.

A simple application algorithm:

```text
1. Read user preferences (possibly multiple locales).
2. Normalize / parse valid syntax.
3. Compare against the product's supported locales list.
4. If exact match, select that locale.
5. If policy allows, match an appropriate language or script.
6. If unmatched, choose the published product fallback.
7. Pass the final locale to the i18n/message service and formatters.
```

For example, the product supports `en-US` while the user requests `en-GB`. The application **may** select `en-US` for sharing English if policy permits. However, this can lose regional distinction when formatting dates; in complex applications, **UI language locale** and **formatting locale** can be managed separately.

For regions with multiple languages, do not automatically infer language from `Locale.getCountry()`. Also do not automatically change currency or time zone when choosing a display locale: they are independent data and policies.

### 3.1. Standard Priority Matching

Java supports `Locale.LanguageRange.parse(...)` to parse priority lists and `Locale.lookup(...)` or `Locale.filter(...)` to match supported locales. These methods perform a style of search per RFC 4647, yet **the final fallback selection policy** is still decided by the application.

Illustrative example **inside a method**:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en-US;q=0.7");

List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US")
);

Locale matched = Locale.lookup(priorities, supported);
Locale appLocale = matched != null
        ? matched
        : Locale.forLanguageTag("vi-VN");
```

With the list above, `en-US` is present in supported locales and in the preference list, so `matched` is `en-US`. If the preference list had only `fr-CA` and `fr`, `lookup` finds no supported choice and returns `null`; the application selects `vi-VN` from fallback configuration.

Do not assume `Locale.lookup` understands translation quality, business intent, or that “fr definitely converts to en”. It is strictly a language identifier matching algorithm.

## 4. What Does `ResourceBundle` Do After Receiving a Locale?

Suppose a `Messages` resource group has these files on the classpath:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en.properties
Messages_en_US.properties
```

When requesting `vi-VN`, the typical candidates (when the locale has language+region and no script/variant) are:

```text
Messages_vi_VN
Messages_vi
Messages              (base bundle, Locale.ROOT)
```

Java can load a specific bundle and link less specific bundles as parents. If `Messages_vi_VN` exists and is selected, a key missing there can be looked up in `Messages_vi` and then `Messages`. When `vi_VN` is absent, Java can pick `Messages_vi` as the returned bundle. If both `vi_VN` and `vi` bundles are missing, behavior **differs** between the default overload and a `Control` that forbids trying the JVM fallback locale.

This is the simple model for language/region. Tags with scripts, variants, or special cases can yield longer candidate lists and different ordering. To observe the exact list for a locale in a classpath environment, you can use `ResourceBundle.Control.getCandidateLocales(...)`.

BCP 47 names like `vi-VN` use hyphens, whereas `.properties` file suffixes normally use `_vi_VN`. Do not treat `Messages_vi_VN` as a language tag.

### 4.1. The True Nature of “Fallback to JVM Default”

With `ResourceBundle.getBundle("Messages", requestedLocale)` in default mode, the search mechanism may:

1. Try candidate bundles for the requested locale (from most specific to broadest).
2. If **no non-base bundle was found** for the requested locale, try candidates corresponding to the JVM's default locale.
3. If still no more-specific bundle exists, use the base bundle (`Messages.properties`) if found; if no bundle is available, throw `MissingResourceException`.

Therefore, **the base bundle is not necessarily returned immediately upon being found**: it may be held back while Java tries the JVM's default locale. Default behavior depends on base name, existing resources, requested locale, default locale, providers/caching, and module/classpath environment.

Example: the server's default locale is `en-US`, `Messages.properties` and `Messages_en_US.properties` exist, and neither `Messages_fr` nor `Messages_fr_CA` exists. Calling `getBundle("Messages", fr-CA)` can return `Messages_en_US`, **not `Messages.properties`**. This is a **bundle loader** fallback, not proof that the application intentionally chose English.

If `Messages_fr.properties` already exists, Java finds a non-base bundle for `fr-CA` and will not need to try the `en-US` branch just to pick a bundle. A missing key in `Messages_fr` is a matter of **key inheritance** along the parent chain, not searching for a new bundle using the default locale.

### 4.2. Which Exact Fallback Does `getNoFallbackControl` Eliminate?

When the application runs on the classpath / unnamed module, Java 17 supports:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", selectedLocale, control);
```

`getNoFallbackControl(...)` makes `Control.getFallbackLocale(...)` return `null`. It **prevents the step of switching to the JVM default locale** when no specific bundle is found for the target locale.

It **does not** mean:

- `Messages_vi` cannot be used when `vi-VN` is selected.
- `Messages.properties` (the base bundle) cannot be used.
- Keys cannot be inherited from parent bundles.
- Complete translations are guaranteed for every key.
- Negotiation is automatically performed to pick a locale in the supported list.

The name is misleading: “no fallback” here applies only to **the fallback locale provided by `Control.getFallbackLocale`**, not every layer of resource fallback.

**Java Module System (JPMS) note:** The `getBundle(..., ResourceBundle.Control)` overloads are unsupported when called from a **named module** and can throw `UnsupportedOperationException`. The next example runs a simple Java application on the classpath (unnamed module). With named modules, design using `ResourceBundleProvider`/module resource rules instead of copying `Control` usage verbatim.

## 5. Runnable Java 17 Example: Same Request, Three Fallback Outcomes

This example **intentionally** simulates a JVM default locale of `en-US` in a standalone CLI app to illustrate the risk. Never call `Locale.setDefault` per request in a multi-user service because it is a JVM-wide mutation.

Create these exact four files in the same directory:

```text
LocaleFallbackDemo.java
Messages.properties
Messages_vi.properties
Messages_en_US.properties
```

**`Messages.properties`**

```properties
greeting=Base greeting
button.save=Save
```

**`Messages_vi.properties`**

```properties
greeting=Xin chào
```

**`Messages_en_US.properties`**

```properties
greeting=Howdy
```

**`LocaleFallbackDemo.java`**

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleFallbackDemo {
    private static final Locale PRODUCT_FALLBACK =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            PRODUCT_FALLBACK,
            Locale.forLanguageTag("en-US")
    );

    private static Locale chooseAppLocale(Locale requested) {
        // Simple illustrative policy: accept exact matches only.
        return SUPPORTED.contains(requested)
                ? requested
                : PRODUCT_FALLBACK;
    }

    public static void main(String[] args) {
        Locale originalDefault = Locale.getDefault();

        try {
            // Used only in this isolated demo to reproduce JVM fallback.
            Locale.setDefault(Locale.US);

            Locale requested = Locale.CANADA_FRENCH; // fr-CA
            Locale appLocale = chooseAppLocale(requested);

            ResourceBundle.Control noJvmFallback =
                    ResourceBundle.Control.getNoFallbackControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES);

            ResourceBundle fromAppPolicy =
                    ResourceBundle.getBundle(
                            "Messages", appLocale, noJvmFallback);

            ResourceBundle fromNaiveLookup =
                    ResourceBundle.getBundle("Messages", requested);

            ResourceBundle fromStrictLookup =
                    ResourceBundle.getBundle(
                            "Messages", requested, noJvmFallback);

            System.out.println("requested=" + requested.toLanguageTag());
            System.out.println("appLocale=" + appLocale.toLanguageTag());
            System.out.println("appBundle=" +
                    fromAppPolicy.getLocale().toLanguageTag());
            System.out.println("appGreeting=" +
                    fromAppPolicy.getString("greeting"));

            System.out.println("naiveBundle=" +
                    fromNaiveLookup.getLocale().toLanguageTag());
            System.out.println("naiveGreeting=" +
                    fromNaiveLookup.getString("greeting"));

            System.out.println("strictBase=" +
                    fromStrictLookup.getLocale().equals(Locale.ROOT));
            System.out.println("appSave=" +
                    fromAppPolicy.getString("button.save"));
        } finally {
            Locale.setDefault(originalDefault);
        }
    }
}
```

Compile and run on the classpath with JDK 17 or later, saving the files as UTF-8:

```bash
javac -encoding UTF-8 LocaleFallbackDemo.java
java -cp . LocaleFallbackDemo
```

**Expected stdout:**

```text
requested=fr-CA
appLocale=vi-VN
appBundle=vi
appGreeting=Xin chào
naiveBundle=en-US
naiveGreeting=Howdy
strictBase=true
appSave=Save
```

Analysis of each result:

- `requested=fr-CA`: input preference, **not yet** a locale accepted by the product.
- `appLocale=vi-VN`: result from `chooseAppLocale`, decided by **application policy** because `fr-CA` is not in the supported list.
- `appBundle=vi`: without `Messages_vi_VN.properties`, Java uses `Messages_vi.properties` for appLocale `vi-VN`. It is valid for these two locales to differ: one is the application's choice, the other is the granularity of available translation data.
- `appGreeting=Xin chào`: key `greeting` is present in `Messages_vi`.
- `naiveBundle=en-US` and `naiveGreeting=Howdy`: calling `getBundle` directly with `fr-CA` without application locale selection; Java finds no French bundle and moves to **JVM default `en-US`**.
- `strictBase=true`: same requested locale `fr-CA` but with no-JVM-fallback control, no French bundle exists, so Java receives the base bundle `Messages.properties`; `getLocale()` equals `Locale.ROOT`.
- `appSave=Save`: `Messages_vi` lacks key `button.save`, so `getString` retrieves it from parent `Messages.properties`. This is **key fallback**, independent of bundle selection. An incomplete Vietnamese translation can expose English text even when the app properly selected `vi-VN`.

Note: `try/finally` is used solely to restore the JVM default after the demo; `Locale.setDefault(...)` still mutates process-wide state and is unsuitable in concurrent server applications. The demo assumes no other `Messages_fr*` or `Messages_en*` files on the classpath and no matching `Messages` class. Adding files with the same base name will intentionally alter bundle ordering/selection.

## 6. Important Rule: Finding a Bundle Differs from Finding a Key

Consider:

```properties
# Messages.properties
menu.open=Open
menu.close=Close
```

```properties
# Messages_vi.properties
menu.open=Mở
```

If `vi-VN` is chosen and Java selects `Messages_vi`:

| Call | Result | Source |
| --- | --- | --- |
| `bundle.getLocale()` | `vi` | Selected bundle |
| `bundle.getString("menu.open")` | `Mở` | `vi` bundle |
| `bundle.getString("menu.close")` | `Close` | Parent/base bundle |
| `bundle.getString("menu.exit")` | `MissingResourceException` | Absent in the bundle chain |

There is no event where “`getString` switches the application locale to English”; it merely returns the string from the parent when a key is missing. Any application wanting full Vietnamese support must **test key coverage**, not just check that `getBundle` loads.

Another risk: a translated string may use parameters `{0}`, `{1}` or different grammar; fallback pulls a string from base while formatters, numbers, or dates still follow the requested locale. Therefore, avoid inadvertently mixing strings across languages; establish a content fallback policy and test rendering with parameters.

## 7. Behavior Table for Common Call Patterns

Assume the JVM default locale is `en-US`, files `Messages.properties`, `Messages_vi.properties`, and `Messages_en_US.properties` exist, and no `fr` or `fr_CA` exists:

| Request | Call | Returned Bundle | Why |
| --- | --- | --- | --- |
| `vi-VN` | `getBundle("Messages", viVN)` | `vi` | Closest language-level match exists |
| `vi-VN` | `getBundle("Messages", viVN, noJvmFallback)` | `vi` | No need to try JVM default |
| `fr-CA` | `getBundle("Messages", frCA)` | `en-US` | No French version, so tries JVM default |
| `fr-CA` | `getBundle("Messages", frCA, noJvmFallback)` | `ROOT` (base) | Does not try JVM default; base remains |
| `vi-VN` after app fallback from `fr-CA` | `getBundle("Messages", selectedViVN, noJvmFallback)` | `vi` | Product chose the locale before looking up |

If `Messages.properties` is also removed and no matching bundle remains under search rules, Java throws `MissingResourceException`. `getNoFallbackControl` **does not guarantee** data will always be found; it only changes the strategy for trying the JVM's fallback locale.

In a system with more than two locale components, script/variant expand the candidate list; the table above describes the exact **assumed file set** and is not a general lookup table for every possible locale.

## 8. Why `getBundle().getLocale()` Should Not Be Used as the Whole Application's Locale

Suppose a user is assigned `vi-VN`, yet only `Messages_vi.properties` exists in the system. `bundle.getLocale()` returns `vi` because that is the bundle found. If you then do:

```java
Locale wrongFormattingLocale = bundle.getLocale();
```

the application accidentally loses the `VN` region information from the original selection. Monetary amounts, dates, language, and regional conventions may be formatted with an overly generic locale. Likewise, `getBundle(... fr-CA ...)` might return the `en-US` bundle due to JVM default; `getLocale()` at that point does not reflect the user's intent.

The design should keep two variables explicit:

```java
Locale uiLocale = Locale.forLanguageTag("vi-VN");

ResourceBundle labels = ResourceBundle.getBundle(
        "Messages", uiLocale,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES)
);

// uiLocale is the chosen application locale.
// labels.getLocale() only tells which specific bundle was returned.
```

This is an illustrative snippet placed inside a class or method. Formatters should be given the **decided presentation locale**, which may be `uiLocale` or a separate `formattingLocale` depending on product design. Do not use `labels.getLocale()` to overwrite the user's locale state.

## 9. Multi-User Service Design

On a Java backend, requests can arrive concurrently:

```text
Request A: user vi-VN ─┐
                       ├── same JVM ── shared resources, multiple locales
Request B: user en-US ─┘
```

If request A runs `Locale.setDefault(viVN)` and request B runs `Locale.setDefault(enUS)`, the two requests can overwrite shared state and cause erratic results. The right approach is to pass the locale per request:

```java
String renderGreeting(Locale uiLocale) {
    ResourceBundle bundle =
            ResourceBundle.getBundle("Messages", uiLocale);
    return bundle.getString("greeting");
}
```

This is an illustrative snippet inside a class. For policies requiring avoiding JVM-default fallback, on the classpath you can use the `Control` overload as before; in named modules you need an appropriate provider mechanism.

Typical layers:

- **Locale resolver:** picks `uiLocale` from profile and request, checks the supported list, returns product fallback if needed.
- **Message service:** loads the bundle with the selected `uiLocale`, retrieves keys and formats placeholders; strictly controls fallback.
- **Formatter:** creates `NumberFormat`/`DateTimeFormatter` with the presentation locale, selects `ZoneId` independently.
- **Validation/error boundary:** emits **stable error codes** for the system, translates messages on display, and never treats localized text as a business identifier.

JVM default locale configuration remains useful for single-user CLI apps or when the environment intentionally defines a default. Yet for multi-user servers, never use it as an unpublished product fallback decision.

## 10. How Can the Two Fallback Policies Be Combined?

### Policy A: Allow Users Only Product-Supported Locales

For example, supported `vi-VN, en-US`, product fallback `vi-VN`. The UI selects the locale by profile/`Accept-Language`; then looks up the bundle. When a corresponding resource is missing, the system treats it as a deployment bug or uses the base resource per defined rules. Advantage: clear behavior, controllable user experience.

### Policy B: Allow Broader Locales While Falling Back Translations

An application might accept `fr-CA` for **formatting** dates, times, and numbers even without a French translation; meanwhile, **message language** explicitly falls back to English or Vietnamese. To do this cleanly, separate `formattingLocale` from `messageLocale`, or provide a fallback strategy for the message resolver; there is no need to force all data to follow whichever bundle happened to load.

One model is:

```text
User preference: fr-CA
      ├── formattingLocale = fr-CA
      └── messageLocale    = en-US (published product fallback)
                                   │
                                   └── Messages_en_US / Messages_en / base
```

Both policies can be valid depending on the product. The key is to **specify and test them clearly**, rather than letting the JVM default silently decide which language the user sees.

### Should `Messages.properties` Be Used as the “Default Translation”?

It can, if it contains translations in the product's fallback language. However, the base bundle is the final resource in the parent chain and **does not replace selecting a product locale**. An English base file can leak English onto a screen that selected Vietnamese when the Vietnamese file lacks a key. Therefore:

1. Define the base bundle's language by project convention.
2. Ensure every locale declared supported has all critical keys and placeholders.
3. Permit key fallback only per published policy; consider failing fast in test environments for missing translations.
4. Do not rely on the JVM default locale to fill in missing translations.

## 11. How to Inspect, Diagnose, and Verify

When a user reports “selected Vietnamese yet saw English”, separate each piece of evidence:

| What to Know | What to Observe |
| --- | --- |
| What user preference was read? | Language tag or `Accept-Language` list |
| What did the app ultimately choose? | Log `uiLocale.toLanguageTag()` after the locale resolver |
| What is the JVM default? | `Locale.getDefault()`, for diagnostics only |
| Which bundle was loaded? | `bundle.getLocale()` and base name |
| Which bundle is the key coming from? | Inspect the current bundle file and parent files; `getLocale()` alone does not show where each individual key came from |
| Does the translation have all keys? | Coverage and placeholder tests in build/test |
| How was `getBundle` called? | Was `Control` or a provider used? Classpath or named module? |
| Are caches/deployments mixing versions? | Check cache lifecycle, class loader, and deployed resources |

**Do not log sensitive user content** just to diagnose localization. Logging the locale, key name, error code, and selected bundle when needed is usually sufficient.

`ResourceBundle` caches bundles. When replacing `.properties` files while the JVM is running, read results may not change due to caching. Depending on architecture, redeploy, configure TTL/`needsReload`, or call `ResourceBundle.clearCache(...)`; do not assume editing a file immediately updates all bundles. Also, multiple JARs on the classpath may contain the same base bundle, so verify where files are actually packaged.

## 12. Testing Behavior at the Right Layer

The test suite should separate **two groups**:

**Group 1 — locale resolver (application policy)**

- Profile selects `vi-VN`, request header selects `en-US`: algorithm prioritizes user settings per product rules.
- Unsupported preference `fr-CA`: app chooses product fallback, independent of JVM default locale.
- Preference `en-GB` with supported `en-US`: test policy with or without language-level fallback.
- Multi-tag header with `q`: parses/looks up in proper priority order without passing the entire header string to `forLanguageTag`.

**Group 2 — resource lookup (Java runtime / actual files)**

- `Messages_vi_VN` exists: returns `vi-VN` bundle.
- `Messages_vi_VN` absent but `Messages_vi` exists: returns `vi` bundle.
- No bundle for `fr-CA`: compare the default overload with `getNoFallbackControl` in an environment with default `en-US`.
- File `vi` misses a key: confirm key comes from parent bundle or detect omission under coverage policy.
- No satisfying bundle exists: throws `MissingResourceException`.
- Same `selectedLocale` with changed JVM default: result must not cause the application to choose a different product locale.

Tests that mutate `Locale.setDefault` must run in isolation to avoid breaking concurrent tests. The demo restores the default in `finally`, yet still should not run in parallel with other tests that depend on the global default.

### 12.1. Small Exercise to Observe Candidate Locales

The following snippet is standalone and runs with JDK 17:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class CandidateLocalesDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (Locale candidate :
                control.getCandidateLocales("Messages", requested)) {
            System.out.println(candidate.equals(Locale.ROOT)
                    ? "(base)" : candidate.toLanguageTag());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CandidateLocalesDemo.java
java CandidateLocalesDemo
```

Exact stdout in Java 17:

```text
vi-VN
vi
(base)
```

The code above only **lists candidate locales**; it does not attempt to find `Messages` files, nor does it show fallback to the JVM default: JVM fallback is an additional search step determined by `getFallbackLocale`, not part of the candidate list for `vi-VN`.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `getBundle(requested)` automatically picks a supported product locale | It looks up bundles per Java's algorithm; supported locales are an app policy |
| `Locale.getDefault()` is the user-chosen language | It is JVM default state; it can differ from every request |
| `getNoFallbackControl` forbids all fallbacks | It forbids the fallback locale provided by `getFallbackLocale`; candidate/base/parent still apply |
| If `Messages.properties` exists, Java always uses base before JVM default | Base may be held back while searching bundles for the JVM default |
| `bundle.getLocale()` always equals the requested locale | This value reflects the bundle actually returned |
| A missing key makes Java “switch to the JVM default bundle” | Key lookup walks the parent chain of the selected bundle; do not confuse with bundle selection |
| `Messages_vi` existing means Vietnamese translations are complete | Must test all keys and placeholders |
| Selecting an app locale is enough to decide time zone and currency | `ZoneId` and `Currency` are separate decisions |
| `ResourceBundle.Control` works identically on classpath and named modules | `Control` overloads are unsupported when called from named modules |
| Changing default locale per HTTP request is safe | Default is JVM-shared state, easily affecting other requests |

## 14. Self-Practice Questions and Answers

**Question 1.** A user sends `fr-CA`, and the app supports only `vi-VN` and `en-US`. The server defaults to `ja-JP`. Who decides that the UI renders in Vietnamese?

**Answer:** The application's locale resolver with a product fallback rule to `vi-VN`. `ResourceBundle` cannot deduce this solely from `fr-CA` and JVM default `ja-JP`.

**Question 2.** The app selected `vi-VN`, and the returned bundle has locale `vi`. Is this a bug?

**Answer:** Not necessarily. If `Messages_vi_VN` does not exist yet `Messages_vi` does, Java picking the language-level file is valid. You should still keep `vi-VN` for formatters if that is the decided presentation locale.

**Question 3.** Does `getNoFallbackControl` prevent fetching `button.save` from `Messages.properties` when `Messages_vi.properties` is missing the key?

**Answer:** No. It only prevents searching for a **fallback locale** via `Control.getFallbackLocale`, not walking the parent bundle chain.

**Question 4.** Base bundle and `en-US` bundle exist, JVM default is `en-US`, and request `fr-CA` has no French bundle. What does the default overload usually return?

**Answer:** `en-US` because Java tries the default locale before concluding to use base; trying `getNoFallbackControl` will return base under the file set assumed in this lesson.

**Question 5.** The app shows English for a single key in the middle of a Vietnamese screen, yet `bundle.getLocale()` is still `vi`. What should be checked?

**Answer:** Check whether that key exists in `Messages_vi` or only in parent/base; then add the translation and coverage tests. Do not rush to change the locale resolver since the bundle was selected correctly.

## 15. Summary of Key Takeaways

- **Locale selection**: a product decision for each user or request, based on preferences, supported locales, and explicit fallback.
- **Bundle selection**: Java's algorithm to find a matching resource for the passed locale, involving candidate locales, base bundle, and potentially falling back to the JVM default locale in the default overload.
- **Key inheritance**: when the selected bundle lacks a key, `getString` looks up parent bundles; this is not re-selecting the application locale.
- **`getNoFallbackControl`**: blocks fallback to the JVM default locale when using `ResourceBundle.Control` on the classpath, while still allowing candidate and base/parent lookup.
- **Stable design**: keep the application's locale explicit, log the bundle locale as diagnostic info, test missing keys, and never call `Locale.setDefault` per request.

Official documentation references for Java 17:

- [`ResourceBundle` — Resource Bundle Search and Loading Strategy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`ResourceBundle.Control` — `getCandidateLocales` and `getNoFallbackControl`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [`Locale` — Language Ranges and Matching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
