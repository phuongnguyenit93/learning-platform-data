# Priority Order Between User Choice and Default Configuration When Selecting a Locale

A Java application may receive multiple signals about language and region: the user just selected Vietnamese in the UI, their account stores English, the browser sends **Accept-Language: fr-FR**, system configuration sets **vi-VN**, while the JVM has locale **en-US**. If the program arbitrarily uses whichever signal it encounters first, the same user may see different screens in different languages.

This lesson builds a **clear priority order policy** for selecting **java.util.Locale** in a Core Java application, explains how to handle unsupported languages, fallbacks, and how to test selection. The topic focuses on the **locale selection decision**; looking up translations and formatting numbers and dates are simply steps that consume the decided locale.

## 1. Prerequisite: Knowing Which Locales the Application Supports

A **Locale** describes a language and may include region, script, variant, and extensions. For example:

| Language tag | Common Meaning |
| --- | --- |
| **vi-VN** | Vietnamese in Vietnam |
| **en-US** | English following United States conventions |
| **en-GB** | English following United Kingdom conventions |
| **fr-FR** | French in France |
| **zh-Hant-TW** | Traditional Chinese in Taiwan |

Java creates a locale from a BCP 47 language tag:

~~~java
import java.util.Locale;

public class LocaleBasics {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        System.out.println(locale.getLanguage());
        System.out.println(locale.getCountry());
        System.out.println(locale.toLanguageTag());
    }
}
~~~

Save as **LocaleBasics.java**, then run:

~~~bash
javac -encoding UTF-8 LocaleBasics.java
java LocaleBasics
~~~

Output:

~~~text
vi
VN
vi-VN
~~~

**Being able to construct a Locale object does not mean the application supports that locale.** Java can understand the tag **ja-JP** even when the product has no Japanese translations at all. The application needs a defined list, such as **vi-VN**, **en-US**, **fr-FR**, along with corresponding translations and formatting. That list is the reference baseline for all language request sources.

Distinguish these concepts:

- **Requested locale:** what the user or caller wants.
- **Supported locale:** a locale within the scope the application commits to support.
- **Resolved locale:** the final locale selected after applying priority and fallback rules.
- **Application default:** a fallback locale explicitly configured by the application; it should be a supported locale.
- **JVM default:** the value of **Locale.getDefault()**, which depends on the environment/JVM runtime policy and can change during process execution.

Do not treat locale and time zone as the same thing. **vi-VN** does not determine the time zone by itself; dates and times must still use separate **ZoneId** information. Similarly, an English UI does not prove that the user pays in USD.

## 2. Priority Order Must Be an Application Policy

Core Java does not prescribe a universal order between user choice, saved preferences, browser language, and product configuration. **Locale.getDefault()** also does not know whether a user just switched language in the UI or saved an account setting. Developers must define and enforce that policy.

A **sample policy** suitable for a multi-user application:

1. **Explicit choice in the current request/session:** the user just picked a language in the UI or passed a valid parameter permitted by the system.
2. **Saved user preference:** the language stored in the profile or account settings.
3. **Client-suggested language:** for example, the **Accept-Language** header from the browser, negotiated against the supported locales list.
4. **Tenant/organization-specific default locale:** if a multi-tenant system actually has this setting.
5. **Application default locale:** a supported locale declared in deployment configuration.
6. **JVM default:** used as a fallback source **only if the product actively chooses and tests it**; many production systems fix an application default instead of implicitly relying on the JVM environment.

The order above is a **changeable product decision**, not a mandatory Java standard. For example: a kiosk system may prioritize device configuration over a user profile; a multi-tenant system may enforce different supported locales lists per tenant. However, even when the policy differs, the order must be written down clearly, applied consistently, and be testable.

The key point is to distinguish a **valid choice** from **the mere presence of a requested string**. If a request specifies **xx-YY** but the application does not support that language, it cannot return the requested locale verbatim as a promise that the UI is translated. The application must choose a policy: try language-based matching, check the next priority source, use the default, or prompt the user to choose again.

## 3. Decision Model: Tiers and Fallback Conditions

You can visualize a simple flow:

~~~text
Start
  |
  v
Is there a valid, supported explicit choice?
  | Yes --> Use the corresponding locale
  | No
  v
Is there a supported account preference?
  | Yes --> Use the corresponding locale
  | No
  v
Does Accept-Language have a supported candidate?
  | Yes --> Use the negotiated candidate
  | No
  v
Is there a valid tenant default? (if applicable)
  | Yes --> Use tenant default
  | No
  v
Use verified application default
~~~

At each tier, the program must answer two independent questions: **is this source allowed to govern the decision?** and **can the source's value map to a supported locale?** Empty strings, syntactically invalid tags, unsupported tags, and missing sources must all be handled intentionally.

Example table with supported locales **vi-VN**, **en-US**, **fr-FR** and application default **vi-VN**:

| Current Choice | Saved | Accept-Language | Result | Reason |
| --- | --- | --- | --- | --- |
| **fr-FR** | en-US | vi-VN | **fr-FR** | Explicit choice has highest priority |
| None | **en-US** | fr-FR | **en-US** | Account configuration takes priority |
| None | None | **fr-FR, en-US;q=0.8** | **fr-FR** | Client language negotiation |
| None | None | None | **vi-VN** | Use application default |
| **es-ES** | en-US | fr-FR | **en-US** | Per sample policy: unsupported choice is skipped and the next source is evaluated |

The last row illustrates the sample policy rather than automatic Java behavior. For a direct language-change action, it may make more sense to **display an “unsupported language” error** instead of silently using the old preference; whereas when rendering a page, fallback rules still help the page display content. You should separate feedback for preference-update actions from the locale resolution algorithm used on read.

## 4. Priority Order Within a Single User's Scope

### 4.1. Explicit Choice in the Current Session

This is usually the signal that most clearly reflects the latest intent. For example, a user has profile **en-US**, but clicks to switch the UI to **vi-VN**. If the current request carries the choice **vi-VN**, the next screen should use **vi-VN** under the sample policy, even if the profile has not yet been updated.

Do not pass raw values directly to a formatter without validation. Only accept locales in the supported list, or apply explicitly described matching rules. A parameter like **?lang=vi-VN** is caller-supplied data; it is not a basis for deciding access control or authorization.

### 4.2. Saved Preference in the Profile

If the request does not specify a new choice, the application reads the user's saved value. This preserves a consistent experience when they log in from another device. When a user saves a language change, determine when the profile is updated and which caches/sessions must be invalidated to avoid the UI continuing to use the old choice.

For unauthenticated users, the language choice can be stored in a cookie/session. The order between cookies and Accept-Language must also be published in the policy. For logged-in accounts, if an old cookie differs from the profile, clearly decide which signal wins; do not let arbitrary data-reading order decide.

### 4.3. When There Is No User Decision

Browsers typically send **Accept-Language**, for example:

~~~http
Accept-Language: fr-CA, fr;q=0.9, en-US;q=0.7
~~~

This header is a **priority list**, not a single language tag. **q** is the quality weight between 0 and 1; if q is omitted, it is normally interpreted as 1.0. **fr-CA** may not belong to supported locales, while **fr** may match a French locale provided by the application.

Do not handle it by taking the string before the first comma and calling **Locale.forLanguageTag(...)**: that approach discards subsequent candidates, q weights, and negotiation rules. Core Java provides **Locale.LanguageRange.parse(...)**, **Locale.filter(...)**, and **Locale.lookup(...)** for these situations.

Some requests do not have Accept-Language, such as background jobs, API clients, or test requests. In that case, the program falls back to system configuration instead of guessing the language from an IP address.

## 5. Matching: How Should Requests Like “en”, “en-GB”, or “fr-CA” Be Handled?

Allowing only exact matching can be too strict: a user requests **en** while the application supports **en-US**. Yet allowing arbitrary language-only matching can also cause bugs: **zh-Hant** and **zh-Hans** use different writing scripts; **pt-BR** and **pt-PT** have vocabulary and display convention differences.

There are three common approaches:

| Matching Approach | Characteristics | When Suitable |
| --- | --- | --- |
| **Exact** | Accepts only locales identical to a supported element | Products requiring very specific selection |
| **Controlled language fallback** | If not exact, uses the same language when unambiguous and script-compatible | Products with one translation per language |
| **Negotiation via language ranges** | Parses a priority list with q weights and selects a matching result from supported locales | Handling Accept-Language and multi-candidate requests |

With **Locale.forLanguageTag(...)**, remember that the API may return a locale with part of the input handled leniently if the tag is malformed. When you need to detect invalid input, use **new Locale.Builder().setLanguageTag(tag)** and catch **IllformedLocaleException**. After parsing, you must still verify a non-empty language, the supported list, and the matching policy. Do not assume that because a tag is syntactically valid, the required translations, currency, time zone, or symbols exist in the application.

If supported locales contain both **en-US** and **en-GB**, a request with only **en** is insufficient to pick one under the “only one locale with the same language” rule. In that case, you can use a preferred variant from product configuration, a published order, or ask the user to choose a region. Do not randomly pick the first element of a collection without a stable order.

## 6. Java 17+: Complete Example of Self-Determined Priority Order

The example below is a **specific policy**, not assuming Java provides this policy automatically:

- Supported locales: **vi-VN**, **en-US**, **fr-FR**.
- A valid explicit choice comes before the saved value.
- Each single choice prioritizes exact match, then tries matching the same language if there is only **one** supported locale with that language and no script conflict.
- The Accept-Language header is processed by weight using Core Java APIs.
- If all sources are absent or unsuitable, use the preconfigured **vi-VN**.
- Do not read or modify **Locale.setDefault(...)** in this algorithm.

**File LocalePriorityDemo.java**

~~~java
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;

public class LocalePriorityDemo {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("fr-FR"));

    private static final Locale APP_DEFAULT =
            Locale.forLanguageTag("vi-VN");

    public static void main(String[] args) {
        show("1. Direct choice",
                resolve("fr-FR", "en-US", "vi-VN"));
        show("2. Unsupported at first tier",
                resolve("es-ES", "en-US", "fr-FR"));
        show("3. Using header",
                resolve(null, null, "fr-CA, fr;q=0.9"));
        show("4. Header weight",
                resolve(null, null, "en-US;q=0.6, vi-VN;q=0.9"));
        show("5. Using default",
                resolve(null, null, null));
        show("6. Language match",
                resolve("en", null, null));
    }

    private static void show(String scenario, Locale locale) {
        System.out.println(scenario + ": " + locale.toLanguageTag());
    }

    // Priority order is an application policy.
    static Locale resolve(
            String explicitChoice,
            String savedPreference,
            String acceptLanguageHeader) {

        Locale candidate = matchSingleTag(explicitChoice);
        if (candidate != null) {
            return candidate;
        }

        candidate = matchSingleTag(savedPreference);
        if (candidate != null) {
            return candidate;
        }

        candidate = matchHeader(acceptLanguageHeader);
        if (candidate != null) {
            return candidate;
        }

        return APP_DEFAULT;
    }

    private static Locale matchSingleTag(String rawTag) {
        if (rawTag == null || rawTag.isBlank()) {
            return null;
        }

        final Locale requested;
        try {
            requested = new Locale.Builder()
                    .setLanguageTag(rawTag.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            return null;
        }

        if (requested.getLanguage().isEmpty()) {
            return null;
        }

        // Exact match takes priority.
        for (Locale supported : SUPPORTED) {
            if (supported.equals(requested)) {
                return supported;
            }
        }

        // Allow same language/script if there is a unique candidate.
        Locale unique = null;
        for (Locale supported : SUPPORTED) {
            if (!supported.getLanguage()
                    .equals(requested.getLanguage())) {
                continue;
            }

            if (!requested.getScript().isEmpty()
                    && !requested.getScript()
                            .equals(supported.getScript())) {
                continue;
            }

            if (unique != null) {
                // Do not automatically choose between two regions with the same language.
                return null;
            }
            unique = supported;
        }
        return unique;
    }

    private static Locale matchHeader(String header) {
        if (header == null || header.isBlank()) {
            return null;
        }

        try {
            List<Locale.LanguageRange> preferences =
                    Locale.LanguageRange.parse(header);
            List<Locale> matches =
                    Locale.filter(preferences, SUPPORTED);
            return matches.isEmpty() ? null : matches.get(0);
        } catch (IllegalArgumentException ex) {
            // Malformed header: try lower-priority source.
            return null;
        }
    }
}
~~~

Save with the exact name **LocalePriorityDemo.java**. Run with Java 17+:

~~~bash
javac -encoding UTF-8 LocalePriorityDemo.java
java LocalePriorityDemo
~~~

Expected stdout:

~~~text
1. Direct choice: fr-FR
2. Unsupported at first tier: en-US
3. Using header: fr-FR
4. Header weight: vi-VN
5. Using default: vi-VN
6. Language match: en-US
~~~

**Explanation of each scenario:**

1. **fr-FR** is a direct request in the supported list, so it beats the saved **en-US** and **vi-VN** from the client.
2. **es-ES** is not supported by the application; under the example policy, it is skipped and **en-US** from the profile beats **fr-FR** in the header.
3. No direct/profile choice; the header prioritizes **fr-CA** then **fr**. Because the supported list has **fr-FR**, range **fr** matches and the result is **fr-FR**.
4. **vi-VN** has weight 0.9, higher than **en-US** at 0.6, so the negotiation result is **vi-VN**.
5. With no valid input data, it returns **APP_DEFAULT**, independent of the host machine's language.
6. The request **en** is mapped to **en-US** because the current list has only one English locale and no script conflict.

**Intentional limitations of the example:** it does not implement tenant defaults, profile storage, cookies, or an error-notification UI, as those are integration layers outside pure Java locale selection. When a tenant default exists, insert a check after header negotiation and before **APP_DEFAULT**. If product policy requires exact matching, remove the unique-language selection branch.

### 6.1. Why Use Locale.filter Instead of Splitting the Header Manually?

**Locale.LanguageRange.parse(header)** parses the list of languages and weights. **Locale.filter(preferences, SUPPORTED)** finds supported locales matching the language ranges. This avoids buggy code like:

~~~java
// Should NOT be used to handle the entire Accept-Language:
Locale requested = Locale.forLanguageTag(
        "fr-CA, fr;q=0.9".split(",")[0]);
~~~

The snippet above only takes **fr-CA** and loses candidate **fr**. **Locale.lookup(...)** is another API to find a single best match under lookup rules; its results and matching strategy can differ from filtering. Choose one clear mechanism, test region/script cases, and align with product policy.

The example uses **Locale.filter** for a supported list with one locale per language. For a product with multiple variants of the same language or complex region fallback policies, you must design additional resolution for unmatched/ambiguous cases.

### 6.2. Invalid Input and Exceptions

**IllformedLocaleException** is caught when parsing a single request; **IllegalArgumentException** is caught when parsing the negotiation header. Unsupported input does not crash the program: it returns **null** from the match method to try the next source. However, a real application should distinguish **missing**, **malformed**, and **unsupported** reasons for proper messaging and configuration monitoring, instead of only logging “locale null”.

If a user just requested switching to an unsupported locale, the preference-update service should return a clear validation error and not save the invalid choice. On the page-reading path, a predefined fallback helps avoid returning an empty UI.

## 7. Distinguishing Application Default and JVM Default

### 7.1. JVM Default Values

Java provides:

~~~java
Locale systemDefault = Locale.getDefault();
Locale formatDefault =
        Locale.getDefault(Locale.Category.FORMAT);
Locale displayDefault =
        Locale.getDefault(Locale.Category.DISPLAY);
~~~

This is an illustrative snippet requiring importing **java.util.Locale**. **getDefault()** returns the general default locale; the two categories distinguish data formatting and displaying locale/language names. The JVM default can originate from the operating system or JVM startup configuration, such as certain properties **user.language**, **user.country**. Those defaults can differ across developer laptops, CI, containers, and servers.

For example, a program that only calls **NumberFormat.getInstance()** or **DateTimeFormatter** without an explicit locale can produce different output depending on the environment. If business logic requires determinism, pass the resolved locale explicitly to APIs that consume language/region.

### 7.2. Why Not Use Locale.setDefault Per Request?

**Locale.setDefault(locale)** mutates shared JVM state. It is not a thread-local variable or per-user storage. On a server handling two concurrent requests:

~~~text
Request A (vi-VN): calls Locale.setDefault(vi-VN)
Request B (en-US): calls Locale.setDefault(en-US)
Request A: calls NumberFormat.getInstance() without passing a locale
Result for A may follow en-US because B just changed the JVM default
~~~

This depicts a race condition, not a fixed execution schedule. Even if each request tries to restore the old locale afterward, interleaving between requests can still corrupt results. A safer policy is to **resolve the locale into a value** and pass that value to the functions that need it.

~~~java
Locale selected = Locale.forLanguageTag("vi-VN");
NumberFormat formatter = NumberFormat.getNumberInstance(selected);
~~~

The snippet above requires importing **java.util.Locale** and **java.text.NumberFormat**. **formatter** is configured for a specific locale and does not depend on another request changing settings. **NumberFormat** itself has mutable state, so do not share a single instance across multiple threads by default.

### 7.3. When Is the JVM Default Considered a Priority Source?

For a desktop application serving a single user, relying on the OS locale on first launch can be reasonable. Yet as soon as the user picks another language, the chosen value must be applied according to policy.

For web services, APIs, and scheduled jobs, the application default should usually be an explicit configuration. If an organization has a rule **“app config → JVM default → fixed fallback”**, filter every candidate against supported locales and always end with a valid locale; do not trust that **Locale.getDefault()** is always in the product's translation list.

## 8. Other Default Tiers: Tenant, Application, and Environment

In a multi-tenant product, one tenant may default to **fr-FR**, while the system-wide application default is **vi-VN**. If a user has no personal choice and the header finds no locale supported by the tenant, the rule can fall back to the tenant default. However, **supported locales** may also depend on the tenant; in that case, every request must be checked against the verified list for the current tenant before deciding.

A clear way to configure this is a conceptual format:

~~~yaml
localization:
  supported-locales:
    - vi-VN
    - en-US
    - fr-FR
  default-locale: vi-VN
~~~

This is only a **configuration format example**, not an auto-loading feature of Core Java. Startup code needs to read configuration via the application's mechanism, validate language tags, and verify the default is in the supported list. If this condition fails, report a configuration error at startup rather than letting an arbitrary request select a locale without resources.

When there are multiple configuration layers, also distinguish **later-loaded configuration overriding earlier configuration** from **locale priority during request handling**. The two mechanisms may be related, but they are not identical. For example, the application default may be selected from an environment variable at startup, yet at request time it must still yield to the user's explicit choice.

## 9. After Resolution: Using the Locale Consistently with ResourceBundle and Formatters

The locale selection algorithm outputs only a **Locale** object. Downstream layers must consume this same value:

~~~java
Locale resolved = Locale.forLanguageTag("vi-VN");

ResourceBundle messages =
        ResourceBundle.getBundle("messages", resolved);
String greeting = messages.getString("greeting");

NumberFormat numbers =
        NumberFormat.getNumberInstance(resolved);

DateTimeFormatter dates =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(resolved);
~~~

The illustrative snippet requires importing **java.util.Locale**, **java.util.ResourceBundle**, **java.text.NumberFormat**, **java.time.format.DateTimeFormatter**, and **java.time.format.FormatStyle**; a resource bundle **messages** must exist on the classpath. The example only shows passing the same resolved locale, not a standalone program.

### 9.1. Two Fallback Layers Must Be Kept Separate

**Layer 1 – application locale selection:** the algorithm decides **fr-FR** or **vi-VN** based on user, header, supported list, and default.

**Layer 2 – resource lookup in ResourceBundle:** after receiving locale **fr-FR**, the lookup mechanism may try the specific bundle, language bundle, base bundle, and in some cases also use the JVM default when finding a bundle. This can lead to **resolvedLocale = fr-FR** yet a message coming from another locale's resource due to default API fallback.

If the application needs a resource fallback policy independent of the JVM default, for traditional classpath-based resource bundles it can be controlled with **ResourceBundle.Control**:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages",
        resolved,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES));
~~~

The snippet above is not standalone and requires importing **java.util.ResourceBundle**, the **resolved** variable, and resources on the classpath. **getNoFallbackControl** prevents the fallback step using the JVM default locale; candidate bundle and base bundle lookup rules still remain. **ResourceBundle.Control** has limitations when using named modules: do not assume the Control overload works identically across all module types; with named modules, apply supported resource/provider mechanisms and test actual fallback.

**Pragmatic rule:** the resolved locale, the actual selected translation, and the displayed content should follow a consistent convention. If the app prioritizes **vi-VN** but lacks a Vietnamese key, have a clear policy for falling back to the base language, warning on missing keys, and translation QA. Having the right locale does not automatically guarantee every message key has been translated.

### 9.2. Locale Does Not Replace Other Business Choices

- **Time zone:** obtain from the user, organization, or business rule, such as **ZoneId.of("Asia/Ho_Chi_Minh")**; do not infer from locale.
- **Currency:** the currency code used in a transaction must come from business logic; do not infer it from the UI language.
- **API data formats:** use deterministic contract formats like ISO for data exchange, while locale primarily serves human display/input.
- **Access permissions:** locale/headers/cookies are not proof of user identity or authorization.

## 10. User Selection, Caching, and Cross-Request Consistency

In a web service, the resolved locale can travel with the **request context**, session, or an object passed across processing layers. There is no need to mutate global JVM state to pass context. If using thread pools or async tasks, do not assume a **ThreadLocal** variable automatically transfers to the next processing thread; pass or set/clean up context explicitly according to the architecture.

When caching translated content, **locale usually must be part of the cache key**. For example:

~~~text
Wrong: cache["welcome"] = "Xin chào"
Right: cache[("welcome", "vi-VN")] = "Xin chào"
       cache[("welcome", "en-US")] = "Hello"
~~~

If the application uses per-tenant locales or translation versions, those factors may also need to be included in the cache key. Otherwise, an English request could receive a Vietnamese translation due to an overly generic cache key.

A user changing their selection from **en-US** to **vi-VN** needs to see it take effect within the promised scope: immediately on the current request, starting on the next request after saving, or after a page reload. Define clearly when profile, session, and cache are updated; avoid having the UI say “language changed” while subsequent parts still read the old locale.

## 11. Testing Priority Order as a Contract

A resolver is valuable when its behavior is verified with a case table. Do not test only the “happy path” language. For the policy in section 6, minimal cases include:

| Scenario | Expected Result |
| --- | --- |
| Explicit, saved, and header are all valid but differ | Explicit wins |
| Explicit is empty, saved and header differ | Saved wins |
| Explicit is unsupported, saved is valid | Saved is selected under the sample policy |
| First two tiers absent, header has q | Use the candidate with the appropriate negotiated priority |
| Malformed header | Does not break the request; moves on to default |
| No source present | Application default |
| Explicit is only **en**, only **en-US** supported | Maps to **en-US** if language fallback is permitted |
| Both **en-US** and **en-GB** supported, request is only **en** | Do not auto-pick a region under the unique-language rule |
| Tags with same language but different script | Do not automatically treat the two writing systems as identical |
| JVM default changes to another locale | Resolver still produces the same result for the same inputs and configuration |

You should also test strings with whitespace, misspelled tags, empty supported lists, a default configuration not in the supported list, stale cookies, unauthenticated accounts, and concurrent language changes across multiple devices.

When testing whether behavior is environment-invariant, set a different JVM default in **an isolated test**, then verify the resolver returns the same values for identical inputs. Do not call **Locale.setDefault** arbitrarily among tests running in parallel because it interferes across the whole process.

Distinguish **resolver testing** from **formatted output testing**: the resolver can be tested with exact **toLanguageTag()** checks; number separators/month names can be affected by JDK locale/CLDR data, so byte-for-byte comparison requires controlling the runtime version and data.

## 12. Common Pitfalls and How to Fix Them

### Pitfall 1: Always Using Locale.getDefault()

Symptom: on a developer's laptop the UI is Vietnamese; on the server or CI it is English. Cause: no explicit application default, or formatters read the environment locale. Fix: configure supported/default locales, resolve per request, and pass the resolved locale explicitly.

### Pitfall 2: Header Overrides Saved Preference

Symptom: the user set French, but when opening from a browser with **Accept-Language: en-US**, the UI reverts to English. Cause: middleware reads the header before the profile even though policy says the profile has higher priority. Fix: unify the exact processing order in a centralized resolver.

### Pitfall 3: Using Locale.forLanguageTag Without Checking Support

Symptom: the application receives tag **ko-KR**, yet has no Korean translations; the screen shows a mix of English/Vietnamese. Cause: confusing valid locale syntax with product support capability. Fix: verify the supported list and fallback policy; check resource bundle completeness.

### Pitfall 4: Taking Only the First Value of Accept-Language

Symptom: client sends **fr-CA, fr;q=0.9, en-US;q=0.7**, while the application only supports **fr-FR** and **en-US**; a manual algorithm can miss **fr-FR**. Fix: use the **Locale.LanguageRange** negotiation API and a tested matching rule.

### Pitfall 5: Changing Language with Locale.setDefault

Symptom: one user's request changes how another user's view is displayed. Cause: the default locale is shared JVM state. Fix: keep the locale in request/user context and create formatters per locale.

### Pitfall 6: Unclear or Inconsistent Fallback Across Screens

Symptom: product pages fall back to **vi-VN**, checkout pages fall back to **en-US**; some strings even fall through to the JVM default's resource. Cause: multiple components pick locales and look up bundles independently. Fix: centralize resolution policy, document resource fallback, and test the entire rendering flow.

### Pitfall 7: Mixing Language, Region, Time Zone, and Currency

Symptom: a user switches UI to English, causing timestamps to become US time or invoices to change currency symbol. Cause: treating locale as the entirety of regional settings. Fix: manage UI language locale, time zone, currency, and transaction rules separately.

## 13. Maintainable Design Pattern

In an application with multiple locale-using flows, a component responsible for **resolve** should receive access-checked data and be passed priority sources as parameters. Example design signature:

~~~java
Locale resolveLocale(
        String explicitChoice,
        String savedPreference,
        String acceptLanguageHeader,
        Locale tenantDefault,
        Locale applicationDefault);
~~~

This is an illustrative signature, not standalone code. Parameters can be grouped into an explicit **LocalePreferenceContext** data type if the application has many sources. Support checks and matching algorithms should be centralized; other presentation layers simply consume **resolvedLocale**.

A good contract clearly states:

1. **Input sources:** request, cookie/session, user profile, header, tenant, and app config.
2. **Priority order:** applied precisely when sources conflict.
3. **Supported locales:** single source of configuration or tenant-scoped policy.
4. **Matching:** exact, language fallback, script/region handling, Accept-Language q.
5. **Behavior on invalid values:** fallback or error response for update operations.
6. **Output:** a deterministic supported locale, optionally logging the selection reason.
7. **System effects:** pass locale explicitly, cache with proper context, never mutate JVM default per request.

If users must be supported in changing language directly in the UI, the change action should both **save the preference** as the user wishes and ensure the **current request** uses the newly confirmed choice. Avoid having two competing mechanisms when the page reloads.

## 14. Summary

**Prioritizing user choice over default configuration is an application policy, not an automatic order decided by java.util.Locale.** For multi-user systems, a common design is **explicit choice → saved preference → client negotiation → tenant default (if any) → application default**. Every candidate must be checked against the supported locales list and published matching rules; the JVM default should only be used if policy truly requires it.

Keep a single place responsible for deciding the locale, pass the result explicitly to ResourceBundle and formatters, avoid **Locale.setDefault** per request, and test conflict and fallback cases. That way users get the exact language they chose, and the application behaves reliably across different machines, browsers, and concurrent requests.
