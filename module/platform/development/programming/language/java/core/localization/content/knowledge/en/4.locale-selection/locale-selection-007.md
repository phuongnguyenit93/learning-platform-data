# Handling No Matching Locale with an Explicit Policy in Java

A system may receive requests to render in `ja-JP`, `fr-CA`, or `vi-VN`, while in reality it only has translations and formatting configuration for `vi-VN`, `en-US`, and `fr-FR`. After language negotiation, the critical question is: **if no matching locale is found, what must the application do?**

You should not leave the outcome randomly dependent on the JVM's default locale, data ordering, or a library's hidden fallback behavior. You must define a **no-match policy**, apply it consistently, and make it testable.

This lesson belongs to the **Locale Selection** topic and focuses on handling the no-match situation. Language priority selection is mentioned only enough to understand where a no-match arises.

## 1. What Does “No Matching Locale” Mean?

A locale selection workflow has three basic inputs:

1. **User or client request:** the locale selected in a profile, API parameter, or `Accept-Language` preference list.
2. **List of locales actually supported by the application:** for example, `[vi-VN, en-US, fr-FR]`.
3. **Selection algorithm:** this may be exact matching, `Locale.lookup`, a custom fallback rule set, or a framework's negotiator.

**No match** means the algorithm ran on valid data and **found no candidate meeting the criteria**. This differs from no request being sent, invalid input syntax, or a missing translation resource repository.

| Situation | Example | Interpretation | Reaction to Define |
| --- | --- | --- | --- |
| No preference supplied | No `Accept-Language`, no language selected yet | Missing input, not a match failure | Use default or ask user to choose |
| No supported candidate | Only `vi-VN`, `en-US` supported; client requests `ja-JP` | No match | Fall back, ask to re-select, or reject |
| Invalid input syntax | Header `en_US` in a language-range parser | Malformed input | Return a clear error or apply a separate corrupted-data policy |
| Matched, but translation missing | `fr-FR` selected, yet a message key is missing | Resource error, not a match error | Resource fallback / fix translation as specified |
| Broken application configuration | Default `en-US` is not in the supported list | Operational error | Report configuration error, do not silently continue |
| Tag has valid syntax, locale unsupported | `de-DE` accepted by parser, app has no translations | Syntactically valid, unsupported | Apply no-match policy |

This distinction matters when monitoring errors, returning HTTP statuses, and explaining to users why the UI appears in another language.

## 2. Start with an Explicit Supported Locales List

Example of an application with only three languages/regions:

~~~java
import java.util.List;
import java.util.Locale;

List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("fr-FR")
);
Locale applicationDefault = Locale.forLanguageTag("en-US");
~~~

This is an **illustrative code snippet**, placed inside a method of a class that has imported the types. The list above is the **application's support commitment**, not the list of all `Locale`s the JDK can parse.

`Locale.getAvailableLocales()` provides the locales known to the runtime and locale service providers; that **does not mean** the application has complete screens, message bundles, content, or business policies for all of those locales.

Three invariants must be defined:

- The `supported` list is non-empty and has a controlled ordering/selection rule.
- The default must be a supported locale, unless a special design has a clear reason.
- Locales advertised as “supported” must genuinely have sufficient essential resources or a transparent resource fallback policy.

Configuration can vary the list and default per product/tenant, but validity should be checked at startup rather than waiting until the first request fails.

## 3. Detecting No-Match from Java APIs

### `Locale.lookup()` Can Return `null`

Java provides `Locale.LanguageRange.parse()` to parse weighted language ranges like `Accept-Language`, and `Locale.lookup()` to find a result under RFC 4647 lookup mechanics.

~~~java
List<Locale.LanguageRange> preferences =
        Locale.LanguageRange.parse("ja-JP,ko-KR;q=0.8");
Locale matched = Locale.lookup(preferences, supported);

if (matched == null) {
    // No locale matched yet: hand off to the no-match policy.
}
~~~

This is an illustrative snippet within a scope where `supported` is declared and `java.util.List`, `java.util.Locale` are imported. **`null` is a normal result when no match is found**, so do not immediately dereference it with `matched.toLanguageTag()`.

An easily misunderstood case: `Locale.lookup(Locale.LanguageRange.parse("fr-CA"), supported)` can return `null` even if the list contains `fr-FR`. The lookup algorithm does not automatically decide that “all regional variants of the same language are equivalent”. If the product wants `fr-CA` to fall back to `fr-FR`, there must be an approved **language-level fallback rule**, or an appropriate matching list/algorithm design. Do not arbitrarily replace `CA` with `FR` and treat it as an exact match.

In addition, a value containing only the wildcard `*` may not yield a specific choice from `Locale.lookup`; in Java, the wildcard is not treated as a command forcing selection of the first locale. When the request is “accept any”, the system still needs a default choice or specific priority rule.

### `Locale.filter()` Differs from `Locale.lookup()`

`Locale.filter()` returns a **list** of matching locales per filtering mechanics; it does not share the same contract as `lookup()`. With filter, the no-result case normally produces an empty list. Corresponding handling:

~~~java
List<Locale> matches = Locale.filter(preferences, supported);
if (matches.isEmpty()) {
    // Apply the no-match policy.
}
~~~

Do not mechanically replace `lookup` with `filter`: matching rules, result breadth, and language-range behavior differ. First decide whether the product needs **a single locale** or **a set of acceptable locales**.

### Syntax Errors Are Not No-Match

`Locale.LanguageRange.parse(...)` can throw `IllegalArgumentException` if the value is not a valid list of language ranges. Avoid catching every exception and silently treating them all as no-match. For instance, a misconfigured `"en_US"` should be reported properly as an input error or handled according to a documented corrupted-data policy.

For a **single language tag** in configuration, `Locale.forLanguageTag()` is a lenient parser; if strict validation is required, use `new Locale.Builder().setLanguageTag(tag).build()`. For headers containing multiple tags and weights, use the `Locale.LanguageRange` parser, and do not pass the entire header into `Locale.forLanguageTag()`.

## 4. Selectable No-Match Handling Policies

There is no single universally right choice for every product. Policy must follow from how strict language requirements are and the nature of the content.

| Policy | Behavior When Unmatched | Suitable When | What to Clarify |
| --- | --- | --- | --- |
| **Use published default** | Pick `en-US` or the configured product locale | Websites, multilingual documentation pages, general UIs | UI may differ from preference; notify user of choice when needed |
| **Reject / prompt to re-select** | Return a specific error or show a language picker | APIs with strict locale requirements, legal documents, content bound to exact language | Error code, message, supported list, and how to re-select |
| **Try controlled fallback** | E.g. `fr-CA` → `fr-FR` if translations permit | Content requiring only language-level approximation | Rules per language, region, and content type |
| **Use neutral locale** | Use language-independent content or technical codes | Machine data without translations | Must not turn into a confusing “languageless” UI |

Note: `Locale.ROOT` represents the root/neutral locale in Java, but it does not automatically create human-friendly fallback translations. When friendly messages must be returned, a **real default language** is usually needed.

### Priority Order Must Be Written as a Contract

A contract might be:

1. If the user explicitly chose a **supported** locale, keep that choice.
2. If there is no explicit choice, negotiate `Accept-Language` against the supported list.
3. If there is no match, apply the feature's policy: use default, reject, or controlled fallback.
4. Record the final locale and selection reason for diagnostics.

This is an **example policy**, not a mandatory Java order. For a product that prioritizes headers over profiles, the order may differ; align UI, API, documentation, and tests.

If a **direct locale selection** request was explicitly sent by the user but is unsupported, you should not necessarily switch silently to a language from the header. The product must define whether an explicit choice takes absolute precedence, falls back, or must return an error.

## 5. Designing Locale Selection Results with Clear Reasons

To avoid confusing a true match with a fallback, record the decision source alongside the final `Locale`:

- `MATCHED`: found a locale according to configured criteria.
- `MISSING_FALLBACK`: client supplied no preference, default was used.
- `UNMATCHED_FALLBACK`: valid preference existed but did not match, default was used.

When the system rejects, it must provide a meaningful error instead of continuing to return `null`. A decision-source model helps measure fallback counts, spot language support gaps, and verify whether the UI displays the right message.

Do not log entire raw headers or user details without a clear purpose. Logging normalized codes or counting by result type, according to the product's data protection policy, is usually sufficient.

## 6. Complete Java 17+ Example: `USE_DEFAULT` or `REJECT`

The program below illustrates two **explicitly selected** policies. The locale list and default are fixed so results are easy to verify. Syntactically invalid data is separated from the no-match case.

Create file **`LocaleNoMatchDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class LocaleNoMatchDemo {
    enum Policy {
        USE_DEFAULT,
        REJECT
    }

    enum Decision {
        MATCHED,
        MISSING_FALLBACK,
        UNMATCHED_FALLBACK
    }

    record Resolution(Locale locale, Decision decision) {}

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("fr-FR")
    );
    private static final Locale DEFAULT = Locale.forLanguageTag("en-US");

    private static Resolution noMatch(Policy policy, Decision reason) {
        if (policy == Policy.REJECT) {
            throw new IllegalArgumentException(
                    reason == Decision.MISSING_FALLBACK
                            ? "Missing locale preference"
                            : "No supported locale matches");
        }
        return new Resolution(DEFAULT, reason);
    }

    static Resolution resolve(String acceptLanguage, Policy policy) {
        Objects.requireNonNull(policy, "policy");

        if (!SUPPORTED.contains(DEFAULT)) {
            throw new IllegalStateException(
                    "Default locale is not supported");
        }
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return noMatch(policy, Decision.MISSING_FALLBACK);
        }

        List<Locale.LanguageRange> requested;
        try {
            requested = Locale.LanguageRange.parse(acceptLanguage);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Malformed language preference", ex);
        }

        Locale matched = Locale.lookup(requested, SUPPORTED);
        return matched != null
                ? new Resolution(matched, Decision.MATCHED)
                : noMatch(policy, Decision.UNMATCHED_FALLBACK);
    }

    private static void show(String label, Resolution resolution) {
        System.out.println(label + ": "
                + resolution.locale().toLanguageTag()
                + " (" + resolution.decision() + ")");
    }

    public static void main(String[] args) {
        show("Supported",
                resolve("vi-VN,fr-FR;q=0.8", Policy.USE_DEFAULT));

        show("Unsupported",
                resolve("ja-JP", Policy.USE_DEFAULT));

        show("Missing",
                resolve(null, Policy.USE_DEFAULT));

        show("Region differs",
                resolve("fr-CA", Policy.USE_DEFAULT));

        try {
            resolve("ja-JP", Policy.REJECT);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        try {
            resolve("en_US", Policy.USE_DEFAULT);
        } catch (IllegalArgumentException ex) {
            System.out.println("Malformed: " + ex.getMessage());
        }
    }
}
~~~

Compile with Java 17 or higher:

~~~bash
javac -encoding UTF-8 LocaleNoMatchDemo.java
java LocaleNoMatchDemo
~~~

Standard output of the program (verified against Java API behavior):

~~~text
Supported: vi-VN (MATCHED)
Unsupported: en-US (UNMATCHED_FALLBACK)
Missing: en-US (MISSING_FALLBACK)
Region differs: en-US (UNMATCHED_FALLBACK)
Rejected: No supported locale matches
Malformed: Malformed language preference
~~~

### Explanation of Each Branch

- **Supported:** `vi-VN` matches the supported list and takes precedence over `fr-FR` with weight `q=0.8`. Decision `MATCHED`.
- **Unsupported:** `ja-JP` is valid but absent from the supported set; under `USE_DEFAULT`, the application selects `en-US`.
- **Missing:** no input; the default policy also selects `en-US`, but the reason is `MISSING_FALLBACK`, differing from an unsatisfied request.
- **Region differs:** `fr-CA` is not implicitly equivalent to candidate `fr-FR` under `Locale.lookup`; fallback selects `en-US`. To pick `fr-FR`, an intentional rule must be added.
- **Rejected:** the `REJECT` policy reports a clear error when input is valid yet unmatched; the caller can map it to an HTTP response or prompt the user to choose again.
- **Malformed:** `en_US` violates language range syntax; the parser throws an error and the program does not silently treat it as an unmatched request.

This pattern uses a `record Resolution` (officially supported since Java 16) to hold the locale along with the selection reason. `Objects.requireNonNull` blocks a `null` policy; checking `SUPPORTED.contains(DEFAULT)` is a configuration guard. In a production system, check this invariant once at startup, configure HTTP errors at the API layer, and limit input header length.

**Scope of the example:** `resolve` takes only the header content or language range list and does not implement user-profile locale preferences. It intentionally rejects syntactically invalid input for both policies. If a product wants to treat a malformed header as “no header sent”, a different policy must be written explicitly and tested.

## 7. If You Want Language-Level Fallback, Specify It Explicitly

Many products want to display a French UI even when a user requests `fr-CA` and the app only has `fr-FR`. This can be a reasonable choice, yet it cannot be applied by default to every language or every dataset.

Example of an **additional business rule** (not present in the runnable program in section 6):

~~~text
request: fr-CA
exact lookup: no match
authorized fallback map: fr-CA -> fr-FR
final locale: fr-FR
reason: LANGUAGE_POLICY_FALLBACK
~~~

When adding rules, clarify:

- Which mapping list is permitted, potentially scoped per language/region.
- Whether differing spelling, units of measure, currency, legal terms, or conventions are acceptable.
- Whether the user needs to be notified of the change.
- If the target mapping is also unsupported, whether to fall back to default or reject.
- Priority order among exact match, language fallback, tenant default, and global default.

For example, `pt-PT` and `pt-BR` are both Portuguese yet distinct variants; legal text, currency, or medical content may not be arbitrarily substituted. Likewise, `zh-Hans` and `zh-Hant` use different scripts. **Fallback must be permitted according to content and context**, not merely based on matching language codes.

Do not use `Locale.getLanguage()` to pick an arbitrary first element from `supported` without controlling order, because when the list changes, the outcome can silently change.

## 8. Locale Outcome and `ResourceBundle` Are Two Separate Layers

Selecting a locale does not mean all translation messages already exist. For instance, the app selects `fr-FR`, yet the resource bundle for some screens only has English.

`ResourceBundle.getBundle(...)` has its own resource search and fallback mechanism (including potentially using the JVM default locale on some paths). If you only call `Locale.lookup` without controlling resource loading, the UI may not fully obey the published policy.

Clearly distinguish:

1. **Locale resolution:** the application chooses a locale from the supported set based on user preferences.
2. **Resource resolution:** the application locates actual messages for the chosen locale.
3. **Missing-key policy:** when a key is missing, the application falls back in a permitted order, logs a data error, or halts rendering if completeness is mandatory.

If you need to avoid JVM-default fallback when using `ResourceBundle` in a suitable classpath setup, study `ResourceBundle.Control.getNoFallbackControl(...)` alongside how base bundles are arranged. `ResourceBundle.Control` has limitations depending on how bundles are loaded and Java modules; do not apply it mechanically to every environment. Crucially, test the **final rendered text**, not just `locale.toLanguageTag()`.

Align the locale of messages, number/date formatting, and business context. If defaulting to `en-US`, the UI should not show English labels while arbitrarily formatting numbers/dates with the server's `Locale.getDefault()` when the product expects a single unified context.

## 9. Behavior at the API and UI Layers

### Websites and General Content

Normally, the public default can be used when a client sends no language or no matching language exists. If the UI is authenticated and has a personal language setting, decide whether that choice takes precedence over headers. When falling back, a language switcher can be shown so the user can actively switch to a supported language.

If returned content varies by `Accept-Language`, caching must be designed accordingly; with HTTP, the `Vary: Accept-Language` header may be required for cached responses negotiated via headers. Also account for cookies/user profiles to avoid serving one user's translation to another.

### APIs with Strict Locale Requirements

An endpoint generating documents in a chosen legal language may not be allowed to silently use a default. When unsupported, return an error defined in the API contract, such as asking the client to re-select a locale. If the error is an invalid parameter, `400 Bad Request` may be used; if it relates to providing a representation under content negotiation, `406 Not Acceptable` may fit depending on the contract. Do not choose a status code solely because `Locale.lookup()` returned `null`: HTTP `Accept-Language` is a client preference, and not every unmatched situation warrants 406.

A helpful error response should state the requested locale (in a form safe to display), the reason, and the list of supported codes. Never return exception stack traces to end users.

### Sensitive or Legally Bound Content

When the exact language/regional version is required to prevent misinterpretation, a `REJECT` policy or requiring confirmation to switch languages is usually easier to control than silent fallback. The decision must follow business requirements and be tested, rather than being a blanket default for every product.

## 10. Designing Decision-Table Tests

Test both the **returned locale** and the **reason**. With supported list `vi-VN`, `en-US`, `fr-FR`, default `en-US`, and the example policy from section 6:

| Input | Policy | Expected |
| --- | --- | --- |
| `vi-VN` | USE_DEFAULT | `vi-VN / MATCHED` |
| `fr-FR,vi-VN;q=0.7` | USE_DEFAULT | `fr-FR / MATCHED` |
| `ja-JP` | USE_DEFAULT | `en-US / UNMATCHED_FALLBACK` |
| `ja-JP` | REJECT | Error `No supported locale matches` |
| `fr-CA` | USE_DEFAULT | `en-US / UNMATCHED_FALLBACK` under the current algorithm |
| `null` or `""` | USE_DEFAULT | `en-US / MISSING_FALLBACK` |
| `null` or `""` | REJECT | Error `Missing locale preference` |
| `en_US` | USE_DEFAULT | Error `Malformed language preference` |
| Default not in supported list | Any | Configuration error before negotiation |

Other scenarios to include in real-world test suites: newly added or removed languages; wildcard `*`; requests with `q` weights, including `q=0` exclusions; language-only tags; languages with scripts; differing region names; long/unusual headers; a user profile locale that is no longer supported; and caches returning the right language variant.

With `q=0` (client marks a language range as unacceptable), test the behavior of the specific negotiation mechanism and verify the final fallback policy does not violate mandatory application constraints. If the default is rejected by the user yet the API mandates an exact language, consider choosing `REJECT` instead of silently defaulting.

Run tests in JVMs with different default locales (for example, a server configured for English and CI configured for Vietnamese) to prove the decision does not implicitly depend on `Locale.getDefault()`.

## 11. Common Design Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Calling `Locale.lookup(...).toLanguageTag()` immediately | `NullPointerException` when unmatched | Handle `null` with an explicit policy |
| Unconditionally using `Locale.getDefault()` | Behavior changes across servers/containers | Configure a product default |
| Accepting every locale the parser understands | UI is selected yet lacks translations | Maintain an actual supported list |
| Treating malformed headers as no-match | Hides client errors, hard to observe | Classify invalid/missing/unmatched |
| Auto-mapping all locales with the same language | Wrong region, script, or context | Approved fallback table |
| Testing only locale matching and skipping bundles | Mixed-language UI results | Test resource resolution |
| Returning `406` for every unmatched header | Hard to use for clients merely stating preferences | Per contract, allow default when appropriate |
| Relying on arbitrary order of a locale collection | Non-deterministic results | Deterministic priority list/rules |
| Not recording the decision source | Unknown fallback rate | Store controlled decision categories |
| Mutating `Locale.setDefault` per request | Global state causes cross-request interference | Pass per-request locale explicitly |

## 12. Self-Check and Practice

**Question 1.** An application supports only `vi-VN` and `en-US`. A client requests `ja-JP`, while the product is an informational website with default `vi-VN`. Should an exception be thrown immediately?

**Hint:** If the contract prioritizes preferences while allowing a default, return `vi-VN` with reason `UNMATCHED_FALLBACK`. An exception is only appropriate when policy strictly requires a match or another business rule demands rejection.

**Question 2.** Why is `fr-CA` not automatically replaced with `fr-FR` in every system?

**Answer:** The two locales share a language but differ in region. The `lookup` algorithm does not guarantee arbitrary region substitution; content equivalence is a business decision that must be defined separately.

**Question 3.** Should `Locale.lookup()` returning `null` and `Locale.LanguageRange.parse()` throwing `IllegalArgumentException` share the same error code?

**Answer:** They should not be conflated. The first is no match from parsed input; the second is syntactically invalid input. Both may end in a fallback if clearly designed, but they should be classified separately for handling and diagnostics.

**Exercise.** Modify `LocaleNoMatchDemo` to add a `TENANT_DEFAULT` configuration, then write a test asserting that the tenant's default must belong to the tenant's supported locales list. Add a `LANGUAGE_POLICY_FALLBACK` branch allowing only the mapping `fr-CA → fr-FR`, ensuring remaining locales retain the existing policy. Write tests both before and after the change.

**Remember:** No-match is a **valid outcome of the selection process**, not an invitation to randomly use the server's configuration. Define the supported list, default, fallback or rejection rules, decision reasons, and test cases before implementing.
