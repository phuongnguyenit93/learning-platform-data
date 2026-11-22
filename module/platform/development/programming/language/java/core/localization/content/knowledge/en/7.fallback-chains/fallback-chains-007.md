# Defining an Environment-Independent Fallback Policy

In Java Core, an internationalized application typically has multiple language-specific message sets, such as **messages_vi.properties**, **messages_fr.properties**, and **messages.properties**. When a user requests a locale with no translation, or a key is missing in a translation, the program must decide what fallback content to use. Without a clearly defined policy, results can be influenced by the **JVM default Locale**: the same request might receive different messages on a developer machine, CI, and production servers.

This lesson explains how to **define a deterministic, predictable, and testable fallback chain**, independent of the runtime environment's defaults. The focus is on locale selection, resource bundle lookup, handling missing keys, and verifying result consistency using Java 17+ APIs.

## 1. What Does "Environment-Independent" Mean?

A deterministic fallback policy must return the exact same result given the same:

1. **User input**: requested locale or saved preference.
2. **Application configuration**: supported locale list, default locale, translation selection strategy.
3. **Deployed resource set**: bundle files and keys inside them.
4. **Processing rules**: candidate order, missing-bundle or missing-key behavior.

It must **not** silently depend on the OS account's language, the CI runner's locale, or another library calling **Locale.setDefault(...)** in the same JVM.

For example, in a system supporting **vi-VN** and **fr-FR**, with application default **vi-VN**:

| Input | Locale selection result under the sample policy |
| --- | --- |
| User requests **fr-FR** | **fr-FR** |
| User requests **vi-VN** | **vi-VN** |
| User requests **es-ES** (unsupported) | **vi-VN** |
| No preference provided | **vi-VN** |
| Server JVM set to **en-US** | Does not change the results above |
| CI JVM set to **de-DE** | Does not change the results above |

You must distinguish the **locale selection result** from **individual message contents**. Selecting **fr-FR** does not guarantee every key in the French bundle is translated. Therefore, a practical fallback policy has **two tiers** that must be defined separately.

## 2. Two Commonly Confused Fallback Tiers

### Tier A – Selecting the Application's Effective Locale

This answers the question: **"For this request, which locale does the application commit to using?"**

A sample policy:

~~~text
User-selected locale directly
   ↓ if missing, invalid, or unsupported
Account saved locale
   ↓ if missing, invalid, or unsupported
Client-negotiated locale
   ↓ if no suitable match exists
Application's own default locale (vi-VN)
~~~

This is a **product decision**, not a built-in rule of **java.util.Locale**. Some applications choose to reject unsupported locales with an error immediately; others ignore them and move down to the next source. What matters is that the rule is documented as a contract and tested.

### Tier B – Finding a Translation for a Key

After selecting **fr-FR**, the application still needs to look up key **checkout.submit** in resource bundles. Example chain:

~~~text
messages_fr_FR.properties
   ↓ if bundle or key is missing
messages_fr.properties
   ↓ if no matching value exists
messages.properties (root resource)
   ↓ if key still does not exist
Report missing key per policy
~~~

This reflects ResourceBundle's **candidate chain and parent lookup** model, assuming the root file exists and the policy selects the corresponding candidates. **messages.properties** is the root resource whose contents are deliberately authored; it does **not automatically match** the language of the application default.

If **application default = vi-VN** while **messages.properties** contains English, a **fr-FR** request may find the French locale for some keys and fall back to English for others. That is a choice that must be governed, not proof that the wrong locale was chosen.

**Key rule:** never state vaguely "use default if missing" without specifying **Tier A's default** vs. **Tier B's root resource**.

## 3. Why Default ResourceBundle Behavior Can Depend on the JVM

Java provides multiple overloads of **ResourceBundle.getBundle**:

~~~java
ResourceBundle.getBundle("messages");
ResourceBundle.getBundle("messages", requestedLocale);
~~~

These are two illustrative calls requiring **java.util.ResourceBundle** imported, a **requestedLocale** variable, and bundle files on the classpath.

- **getBundle(baseName)** picks the JVM's default locale as the initial requested locale.
- **getBundle(baseName, locale)** takes an explicit requested locale, yet under the **default ResourceBundle.Control** mechanism can still perform a fallback pass to **Locale.getDefault()** when no matching bundle is found and the default policy allows it.

For example, suppose only **messages_en.properties** and **messages_de.properties** exist, with no root bundle. When requesting **fr-FR**, a machine with default **en-US** may load the English bundle, while a machine with default **de-DE** may load German. Because the application defined no policy, the environment inadvertently decided the response language.

Even though both machines received the same **Locale.FRANCE** argument, the results can still differ. Passing a locale to **getBundle** is necessary, yet **not sufficient** if you want strict control over fallback when resources are missing.

**How to avoid this:** the application must actively decide supported locales and per-request fallback, and control ResourceBundle fallback explicitly through a clear mechanism.

## 4. Declare the Fallback Contract Before Writing Code

A policy can be documented as follows:

| Rule | Example policy |
| --- | --- |
| Supported locales | Only **vi-VN**, **fr-FR** |
| Application default | **vi-VN** |
| Valid but unsupported requested locale | Try next preference source; if none, use **vi-VN** |
| Malformed locale | Reject as effective locale; report error or fall back safely depending on context |
| Matching strategy | Exact match against supported list; do not guess region or script |
| Resource bundle | **messages** files on classpath, UTF-8 |
| JVM default fallback | **Disallowed** |
| Regional bundle absent | Try language-level bundle, then root bundle per candidate chain |
| Key missing in translation | Try bundle parent per policy |
| Key missing across entire chain | **MissingResourceException** or controlled application error |
| Root resource | Canonical content defined in **messages.properties** |
| All environments | Same config, same resources and rules; never read JVM default when deciding locale |

Supported locale metadata must reflect languages that **actually have reviewed resources**. The API **Locale.forLanguageTag("es-ES")** can construct a Spanish locale, yet does not magically create Spanish translations.

If the application is multi-tenant, the supported locale list and app default may be per-tenant configuration. Even then, **the current tenant's config must come from business data**, never from the server host locale. If a tenant's configured default locale is not in its supported list, the application should detect the configuration error at startup or request validation.

## 5. ResourceBundle.Control: Eliminating Fallback to the JVM Default

In Java applications running on the traditional classpath, **ResourceBundle.Control** provides a factory for a control that does not use the JVM default locale for fallback:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "messages", selectedLocale, control);
~~~

This snippet requires importing **java.util.ResourceBundle**, a resolved **selectedLocale** variable, and the **messages** resource. With this control, **getFallbackLocale(...)** returns **null**: after checking the requested locale's candidate chain, lookup does not move on to the JVM default locale as an extra fallback pass.

**What stays unchanged**: the control still allows the region/language candidate chain and the root resource by default; keys can still be looked up in parent bundles. So **getNoFallbackControl(...)** does not mean "no fallback of any kind".

Two common options:

- **FORMAT_PROPERTIES:** requires bundles in **.properties** format.
- **FORMAT_DEFAULT:** allows both class-based bundles and .properties per the default mechanism.

If you only want properties format, **FORMAT_PROPERTIES** makes the contract clearer. Keep resources on the classpath in a tested structure, or an equivalent packaging layout.

**API limitation:** With **named modules** (JPMS), **ResourceBundle.getBundle** overloads taking **Control** may not be supported the traditional classpath way and can throw **UnsupportedOperationException**. When using named modules, choose the corresponding bundle/provider mechanism and test in place; do not copy Control solutions without accounting for packaging. The lab below uses **classpath/unnamed module**, where this overload applies.

## 6. Complete Example: Identical Output Despite Different JVM Defaults

This Java 17+ example has **one root resource set**, **two translations**, and **one resolver**. The program intentionally changes the JVM default inside an **isolated console process** to prove bundle resolution remains deterministic. Never mutate default that way in a multi-user server.

### 6.1. File Structure

Place four files in the same directory:

~~~text
LocaleFallbackDemo.java
messages.properties
messages_vi.properties
messages_fr.properties
~~~

**File messages.properties** – root resource, intentionally in English to illustrate key fallback:

~~~properties
greeting=Hello, {0}!
status=Status: ready.
~~~

**File messages_vi.properties**:

~~~properties
greeting=Xin chào, {0}!
status=Trạng thái: sẵn sàng.
~~~

**File messages_fr.properties** – intentionally missing the **status** key:

~~~properties
greeting=Bonjour, {0}!
~~~

Since Java 9, **PropertyResourceBundle** reads byte streams as UTF-8 by default, with an ISO-8859-1 fallback for invalid byte sequences. With Java 17+, save the three properties files in **UTF-8**. This differs from **Properties.load(InputStream)**, which follows ISO-8859-1 rules; do not apply one API's charset rule to the other.

### 6.2. Standalone Java Code

**File LocaleFallbackDemo.java**:

~~~java
import java.text.MessageFormat;
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleFallbackDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");
    private static final Locale FR =
            Locale.forLanguageTag("fr-FR");

    private static final List<Locale> SUPPORTED =
            List.of(VI, FR);

    private static final Locale APP_DEFAULT = VI;

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    public static void main(String[] args) {
        Locale oldGlobal = Locale.getDefault();
        Locale oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            for (Locale runtime : List.of(
                    Locale.US, Locale.GERMANY)) {
                // Only do this in a standalone console demo.
                Locale.setDefault(runtime);

                printCase("fr-FR");
                printCase("es-ES");
            }
        } finally {
            Locale.setDefault(oldGlobal);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
        }
    }

    // Select the effective locale per application config,
    // without using Locale.getDefault().
    private static Locale resolve(String requestedTag) {
        if (requestedTag == null || requestedTag.isBlank()) {
            return APP_DEFAULT;
        }

        final Locale requested;
        try {
            requested = new Locale.Builder()
                    .setLanguageTag(requestedTag.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            return APP_DEFAULT;
        }

        for (Locale supported : SUPPORTED) {
            if (supported.equals(requested)) {
                return supported;
            }
        }
        return APP_DEFAULT;
    }

    private static void printCase(String requestedTag) {
        Locale selected = resolve(requestedTag);
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", selected, CONTROL);

        MessageFormat formatter = new MessageFormat(
                bundle.getString("greeting"), selected);
        String greeting =
                formatter.format(new Object[] {"Mai"});

        String status = bundle.getString("status");

        System.out.println(
                "runtime=" + Locale.getDefault().toLanguageTag()
                + " | requested=" + requestedTag
                + " | selected=" + selected.toLanguageTag()
                + " | " + greeting
                + " | " + status);
    }
}
~~~

**Run the program:**

~~~bash
javac -encoding UTF-8 LocaleFallbackDemo.java
java -cp . LocaleFallbackDemo
~~~

**Exact stdout for the provided files:**

~~~text
runtime=en-US | requested=fr-FR | selected=fr-FR | Bonjour, Mai! | Status: ready.
runtime=en-US | requested=es-ES | selected=vi-VN | Xin chào, Mai! | Trạng thái: sẵn sàng.
runtime=de-DE | requested=fr-FR | selected=fr-FR | Bonjour, Mai! | Status: ready.
runtime=de-DE | requested=es-ES | selected=vi-VN | Xin chào, Mai! | Trạng thái: sẵn sàng.
~~~

**Detailed explanation:**

1. **fr-FR** is in the supported list, so the resolver returns **fr-FR**. **messages_fr.properties** has key **greeting** yet lacks **status**. ResourceBundle looks up **status** in parent resource **messages.properties**, hence returning **Status: ready.**
2. **es-ES** is not in the supported list, so the resolver returns **vi-VN** per **APP_DEFAULT**; ResourceBundle then finds **messages_vi.properties** and gets both Vietnamese sentences.
3. Switching the JVM default between **en-US** and **de-DE** changes only the printed **runtime** field. The same requested tag still resolves to the exact same locale and content.
4. **MessageFormat** also receives **selected** explicitly. If the pattern has date/number arguments, this prevents another hidden dependency on the default locale.
5. **finally** restores the original defaults within the demo program's scope. That does not make **Locale.setDefault** safe for concurrent requests; this is strictly a controlled test.

Getting English **Status: ready.** when French is selected is **intentional root-resource fallback**, not accidental fallback to the JVM default. If the product forbids mixed-language UIs, you need a different key-tier policy or full translation validation.

## 7. Do Not Confuse "No JVM Fallback" with "Complete Translations"

**ResourceBundle.getBundle("messages", fr, CONTROL)** returns a bundle per the candidate chain. When reading **getString("status")**, the system still looks up keys in the parent chain. There are several cases:

| Case | Behavior to specify |
| --- | --- |
| Requested bundle has key | Return text from that bundle |
| That bundle lacks key, parent has it | Key can be fetched from parent along bundle chain |
| Entire chain lacks key | **MissingResourceException** on **getString** |
| No matching bundle or root resource | **MissingResourceException** when no bundle can be found |
| Requested locale unsupported, yet root exists | Without checking supported locales upfront, **getBundle** may still return root without reflecting true support |

Hence an application with a policy "show French only if 100% translated, otherwise show the entire screen in Vietnamese" **cannot be achieved merely by** **getNoFallbackControl**. That is an extra business-layer requirement: check completeness of the translation set, or select the fallback language wholesale before rendering.

A system can choose one of these contracts:

- **Per-key fallback:** lets each missing key fall back to parent resource content. Easy to implement, yet multiple languages may appear on the same screen.
- **Strictly complete translations:** the build pipeline checks every key; translation sets missing required keys are not published. At bundle load/read time, a missing key is an error to handle.
- **Per-screen/message-group fallback:** if a bundle falls below required completeness, pick the fallback locale for the entire screen or message group. Requires a completeness checker and custom design; ResourceBundle's default lookup does not perform "all or nothing" transactions.

Decide which contract fits the product, encode it in tests, and communicate it to the localization team. **Do not let default ResourceBundle behavior decide UX rules by accident.**

## 8. Choosing the Locale Candidate Chain Explicitly

### 8.1. Language, Region, and Script

These locales show different specificity levels:

~~~text
fr-FR
fr
(root)
~~~

An application may have **messages_fr_FR.properties**, **messages_fr.properties**, and **messages.properties**. ResourceBundle constructs the candidate chain according to Control rules, generally prioritizing specific variant/region before language and root.

However, do not assume **every locale sharing a language is equivalent**. For some languages, script is critical—for example **zh-Hans** vs. **zh-Hant**. A policy that blindly maps **zh-Hant-TW** to **zh-Hans-CN** just because they share a language code can yield a broken experience.

If an application supports both **en-US** and **en-GB**, a bare **en** request can be ambiguous; you need a configured preferred variant or must prompt the user to pick a region. Never accidentally pick the "first element" from an unordered set.

### 8.2. Do Not Delegate Locale Selection to ResourceBundle

**ResourceBundle** is a resource-lookup API, not a product policy engine. If a user sends **es-ES** while the product only supports **vi-VN** and **fr-FR**, determine **selected = vi-VN** upfront per contract before looking up bundles. Do not call **getBundle("messages", Locale.forLanguageTag("es-ES"))** and treat whatever it returns as proof the system supports Spanish.

To parse a user-supplied tag, **new Locale.Builder().setLanguageTag(...)** can catch syntax errors via **IllformedLocaleException**. Even for syntactically valid tags, still validate against a whitelist; being able to construct a Locale does not mean resources exist.

### 8.3. Avoid Hard-to-Control Fallback Loops

For complex requests, sketch the complete sequence with a concrete example:

~~~text
User requests fr-CA
    ↓ application only supports fr-FR, vi-VN
Does the application allow same-language matching?
    ├─ No   → selected = vi-VN
    └─ Yes  → selected = fr-FR (if mapping is configured)
                  ↓
ResourceBundle selects messages_fr.properties
                  ↓
Missing keys fetched from messages.properties (if policy permits)
                  ↓
Never automatically switch to the JVM's locale
~~~

Do not let request locale resolution and resource fallback logic overlap in ways that are hard to explain. And do not confuse Java's resource candidate order with the list of UI locales the application claims to support.

## 9. Application Defaults Must Be Stable and Valid

A policy configuration could be described in YAML:

~~~yaml
localization:
  supported-locales:
    - vi-VN
    - fr-FR
  default-locale: vi-VN
  unsupported-request: use-app-default
  bundle-base-name: messages
  jvm-default-fallback: false
  missing-key: use-parent-bundle
~~~

This is an **illustrative configuration**, not properties Java Core reads automatically. The application must load, validate, and implement the fields itself.

At startup, verify:

1. **default-locale** belongs to supported locales.
2. Every language tag is valid; no two entries collide after normalization.
3. Bundles exist on the classpath under the right names/packages per policy.
4. The root resource exists if the policy depends on root.
5. Mandatory keys in the default language are present, without duplicates or omissions.
6. The key-fallback strategy never drops critical messages such as security errors, transaction confirmations, or legal notices.

A configuration mistake caught at deploy time is far easier to handle than a **MissingResourceException** surfacing only when a user opens a rarely visited page in production.

## 10. Eliminating Remaining Default Dependencies

Controlling ResourceBundle is not enough if other APIs continue reading the default locale:

~~~java
NumberFormat number = NumberFormat.getNumberInstance();
String report = String.format("%.2f", 1234.5);
~~~

These are illustrative snippets requiring **java.text.NumberFormat** imported. Both calls omit a locale, so they may use the **FORMAT** default. For a consistent application:

~~~java
NumberFormat number =
        NumberFormat.getNumberInstance(selectedLocale);

String report = String.format(
        selectedLocale, "%.2f", 1234.5);
~~~

Here **selectedLocale** must come from the policy-enforcing resolver. For machine-readable reports with a technical contract, you may need fixed formatting like **Locale.ROOT** or a language-independent standard; user-facing data should use the user's own locale.

For dates and times, **DateTimeFormatter.withLocale(selectedLocale)** sets language/conventions, yet the **time zone** must be chosen separately via **ZoneId**. Never infer a time zone from a language. For upper/lowercasing technical identifiers, **String.toLowerCase(Locale.ROOT)** may be appropriate to avoid system-locale case-mapping rules.

**Locale.setDefault(...)** mutates JVM-wide shared state, not per-request state. On a multi-request server, calling it to "switch language for this user" can cause other requests to format numbers or look up bundles incorrectly. Always pass the resolved locale directly to consuming APIs.

## 11. Testing Environment Independence

### 11.1. Testing a Pure Resolver

Locale resolution should be an easily testable function: same input and same config → same **selectedLocale**. Example minimal test cases when supported is **vi-VN**, **fr-FR**, and default is **vi-VN**:

| Request | Selected | Notes |
| --- | --- | --- |
| vi-VN | vi-VN | Directly supported |
| fr-FR | fr-FR | Directly supported |
| es-ES | vi-VN | Unsupported, uses app default |
| null | vi-VN | No preference |
| malformed string | vi-VN or input error | Per published contract |
| fr-CA | vi-VN | Per exact-matching policy in the example |
| fr | vi-VN | Does not auto-map to fr-FR under exact policy |

Across that same test suite, changing **Locale.getDefault()** among **en-US**, **de-DE**, and **tr-TR** must not change `selected`. This tests a **property of the resolver**, not the list of languages Java supports.

### 11.2. Testing the Resource Chain

Test separately:

- Requested bundle exists and key exists.
- Region bundle missing, yet language bundle exists.
- Language bundle missing, yet root exists.
- Specific bundle exists but lacks key; parent has key.
- Key absent in every parent: receive **MissingResourceException** at the right place or defined application error.
- Locale has no bundle while JVM default has another bundle: must **not** jump to the JVM bundle if policy forbids it.
- Code running on classpath/unnamed module vs. named module uses the supported provider/control API properly.

Do not attach an assertion "always returns Vietnamese" to every case when the root resource is in another language, because those are two independent contracts. If policy requires every key in the chosen language to be complete, check completeness directly rather than relying on parent fallback.

### 11.3. Do Not Pollute Parallel Tests

A test can simulate different defaults via **Locale.setDefault** and restore in **finally**, yet default is JVM-wide state. If tests run in parallel, test A and test B can interfere with each other, causing flaky failures. The solid approach is to **run each scenario in a separate JVM/process**, or restrict such tests to run sequentially in an isolated process.

With a compiled program, you can pass JVM properties when launching diagnostic runs:

~~~bash
java -Duser.language=en -Duser.country=US LocaleFallbackDemo
java -Duser.language=de -Duser.country=DE LocaleFallbackDemo
~~~

These two commands start two processes initialized with different startup defaults. Note that **LocaleFallbackDemo** itself sets both defaults internally for illustration; in real production tests, use a test suite/entry point that does not mutate default itself so you accurately isolate startup configuration effects.

### 11.4. Comparing Deployment Environments

There are two stability tiers:

- **Default-locale independence:** use explicit configured locales and fallback, without letting JVM default participate in decisions.
- **Byte-for-byte reproducible display output:** also requires controlling **JDK version, CLDR data set, resource packages, timezone data**, and related formatters.

Even when two machines both use **vi-VN**, locale data across different JDK versions can still alter symbols, date formats, or spacing. A deterministic fallback policy solves **bundle selection order**; it does not freeze all runtime localization data.

## 12. Detecting and Handling Missing-Translation Errors

**ResourceBundle.getString(key)** can throw **MissingResourceException** when a key is not found. Error handling also needs a policy:

- For **mandatory messages** (payments, safety warnings, legal confirmations), verify keys exist and are approved at build/deploy time.
- For **low-criticality content**, fallback to root may be permitted; monitor missing keys so translations can be added promptly.
- If choosing to display **[missing:key]** as a marker in dev environments, decide what happens in production: raw placeholders may be inappropriate for end users.
- Do not expose full stack traces or resource paths on the UI to explain missing translations; record them in logs at an appropriate level.
- Consider alerting when the selected locale's bundle is missing and root is used completely, as that may indicate a broken deployment package.

An automated test can validate **key sets** across translations and the root bundle, allowing an explicit allowlist of keys justified for fallback. That turns the policy into a testable constraint instead of an informal agreement.

For **.properties** files, duplicate keys within the same file are not automatically caught as a Java compile error; your resource validation pipeline should detect and warn on overlapping keys where appropriate.

## 13. Common Design Mistakes

### Mistake 1 – Using the Default Overload of ResourceBundle

~~~java
ResourceBundle bundle = ResourceBundle.getBundle("messages");
~~~

Identical code selects different bundles under different JVM defaults. Fix with an **application resolver**, explicit locale passing, and controlled fallback when bundles are missing.

### Mistake 2 – Assuming getBundle(baseName, locale) Eliminates Environment Dependence

Passing a locale only sets the initial input; the default **ResourceBundle.Control** can still fall back to the JVM default in certain missing-bundle scenarios. Fix with **getNoFallbackControl** or a verified resolver/provider mechanism for your packaging model.

### Mistake 3 – Failing to Distinguish Missing Keys from Unsupported Locales

One locale may be supported by the application while missing a few keys; another locale may be completely outside the supported scope. These two errors have different root causes and remedies. You cannot solve both simply by "letting ResourceBundle fall back".

### Mistake 4 – Deriving Application Default from the OS

If the application default is implicitly assigned from **Locale.getDefault()**, CI and production servers may pick different translations. Fix with an explicit **application default** config, validated against the supported list and used consistently.

### Mistake 5 – Depending on Arbitrary Data-Structure Iteration Order

When multiple locales share a language, a selector picking the "first element" of an unordered **Set** can make different decisions across runs. If **fr-CA → fr-FR** or **en → en-US** fallback exists, it must be a published, tested mapping—not an accidental tie-breaker.

### Mistake 6 – Allowing Unbounded or Silent Fallback

Chains like request locale → tenant locale → app default → bundle root → JVM default → placeholder can mask bugs completely. Decide the **stopping point**: an explicit bundle, a chosen default value, or a monitorable missing-resource error.

### Mistake 7 – Not Checking Resources in CI

Code runs fine when translations are complete, yet adding a new locale missing mandatory keys causes production failures later. Validate key sets against the source version; the root translation set can serve as the canonical key list.

## 14. Checklist When Designing a Fallback Policy

Before shipping a localization system, verify:

1. **Supported locales** are declared and their corresponding resources are checked.
2. **Application default** is a valid, supported locale, independent of the environment.
3. **Priority order** among user choice, account setting, client header, and organization config is clear.
4. **Mapping rules** across language/region/script are stated explicitly; no ad-hoc concatenation.
5. **Bundle base name**, resource type, and classpath/module packaging are verified.
6. **JVM default fallback** is deliberately permitted or disabled per contract.
7. **Key/parent fallback** is defined, including the language of the root resource.
8. **Missing-key/bundle errors** have appropriate handling and observability.
9. **Other formatters** also receive an explicit locale; do not focus solely on ResourceBundle.
10. **Tests** cover at least two JVM defaults, multiple requested locales, missing keys, missing bundles, and total absence.
11. **CI** verifies resources and JDK/CLDR versions when deterministic presentation is required.
12. **Never mutate JVM default per request**, avoiding cross-user or parallel-test interference.

## 15. Conclusion

**An environment-independent fallback chain must be defined at both the locale-selection tier and the translation-lookup tier.** The application should decide supported locales, application default, priority order, unsupported-locale handling, and missing-key/bundle behavior. For classpath ResourceBundles, **ResourceBundle.Control.getNoFallbackControl(...)** removes the JVM default-locale fallback step while preserving the intended candidate/parent chain.

A clean resolver paired with a reviewed root resource and tests across two different default environments ensures the same request gets the same translation choice. That is the foundation for predictable Java localization across developer machines, CI, and production.
