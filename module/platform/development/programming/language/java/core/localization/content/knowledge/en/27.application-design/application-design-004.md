# Managing Resource Keys, Resource Versions, and Parameter Contracts in Java Localization

A multilingual Java application cannot run reliably simply by translating English sentences into `messages_vi.properties`. In an evolving system, the same message may be invoked by multiple screens, translations may change while older app versions are still running, and a parameter may change from a quantity to a monetary amount or gain a tracking code. Changes that appear to affect only text can break callers, display wrong data, or cause hard-to-detect deployment bugs.

**Three design pillars to manage together:**

1. **Resource key:** a stable identifier for a *meaning*, not the wording itself.
2. **Catalog version:** a snapshot of the keys, translations, and contracts used by the application.
3. **Parameter contract:** defines each placeholder variable's position, type, meaning, unit, requiredness, and formatting rules.

This lesson belongs to the **Application Design** section of the **Java core - localization** module, using **Java 17+**, `ResourceBundle`, `MessageFormat`, and `.properties` files. The examples can run standalone when you create the specified files. Java provides resource loading and message formatting mechanisms, but **does not build versioning systems, argument-type contract checkers, or translation approval workflows out of the box**; those must be designed at the application level.

## 1. Distinguishing Message Code, Resource Key, and Display Text

Suppose the backend detects a payment failure. The three values below have different responsibilities:

| Layer | Example | Purpose |
| --- | --- | --- |
| Business status code | `PAYMENT_DECLINED` | API communication, error classification, logic handling |
| Resource key | `checkout.payment.declined` | Looking up the message pattern in the catalog |
| Display text | `Thanh toán không thành công.` | Presenting to the user in their locale |

Do not store the translation `Thanh toán không thành công.` as the stable value of a `payment_status` column, because a single wording edit breaks consistency with previously stored records. Store the business code or typed status, then render the message in the presentation layer.

**A key is an internal calling contract.** When a developer renames a key without updating callsites, `ResourceBundle.getString(key)` can throw `MissingResourceException`. When a translator replaces `{0}` with `{1}`, the code may still run while inserting the wrong data into the sentence. Both are contract violations, not mere typos.

### Data Flow Diagram

```text
Business event: ORDER_SUMMARY
  orderId = "A-7"
  itemCount = 3
      |
      v
Key: checkout.summary
Contract: {0}:String orderId, {1}:Number itemCount
      |
      v
ResourceBundle(locale) -> message/pattern
      |
      v
MessageFormat(pattern, locale) + typed arguments
      |
      v
Đơn A-7: 3 món (vi-VN user)
```

## 2. Naming Semantic Keys for Their Purpose

Keys should reveal *context and intent*:

```properties
account.signIn.title=Sign in
account.signIn.submit=Continue
checkout.pay.cta=Pay now
checkout.summary=Order {0}: {1,number,integer} items
checkout.payment.declined=Payment declined.
profile.displayName.label=Display name
```

Recommended rules:

- Use names like `feature.screen.intent` or `domain.event.variant`; adopt one consistent convention across the project.
- Split keys by **semantics**. The same English word "Open" can be a verb (open a file) or a status (currently open); many languages do not translate both the same way.
- Reuse a key only when it truly shares the same message, grammatical role, and parameter contract.
- Assign key ownership: the module/team responsible when editing, deleting, or migrating to a new version.
- Never use verbatim English text like `Payment failed` as a key, because editorial copy changes.
- Never use `msg001` or `error2`, which lack context, are hard to search, and invite accidental misuse.
- Never construct dynamic keys from untrusted strings without an allowlist of allowed keys.
- Never change key casing arbitrarily: `ResourceBundle` key lookups are case-sensitive.
- Never use a resource key as a database key for business values unrelated to display.

**Editing wording does not mean changing the key:** a translation can fix typos, punctuation, or phrasing while keeping the contract intact. **Changing parameter meaning or types is a larger change** and may require a separate key during migration.

## 3. Defining the Root Catalog and Locale Translations

Create this exact structure on the classpath for the example:

```text
example/
  messages.properties
  messages_vi.properties
  BundleLookupDemo.java
```

**`messages.properties`**:

```properties
welcome=Hello, {0}!
checkout.summary=Order {0}: {1,number,integer} items
checkout.failed=Payment failed.
checkout.pay.cta=Pay now
```

**`messages_vi.properties`**:

```properties
welcome=Xin chào, {0}!
checkout.summary=Đơn {0}: {1,number,integer} món
checkout.pay.cta=Thanh toán
```

The base bundle name in this example is `messages`. For `vi-VN`, the runtime can try `messages_vi_VN.properties`, `messages_vi.properties`, and then `messages.properties` along the candidate list. The root file is the final fallback in the appropriate parent chain.

**Java 17 encoding note:** since Java 9, `PropertyResourceBundle` reads `.properties` files as UTF-8 by default, falling back to ISO-8859-1 if invalid UTF-8 byte sequences are encountered (unless overridden via the relevant system property). Thus UTF-8 Vietnamese files match standard Java 17 configurations. Do not confuse this API with `Properties.load(InputStream)`, which follows traditional ISO-8859-1 rules. Builds and CI should standardize on UTF-8, validate file contents, and avoid mixed-encoding files.

**`checkout.failed` is intentionally omitted from the `vi` file** to demonstrate fallback in the next example—not as a quality standard for released products.

## 4. Java 17 Example: Looking Up and Formatting from `ResourceBundle`

Save **`BundleLookupDemo.java`** alongside the two `.properties` files:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    private static ResourceBundle catalog(Locale locale) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        return ResourceBundle.getBundle("messages", locale, control);
    }

    private static String render(
            ResourceBundle bundle, Locale locale,
            String key, Object... args) {
        return new MessageFormat(
                bundle.getString(key), locale).format(args);
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = catalog(vi);

        System.out.println(render(bundle, vi, "welcome", "Lan"));
        System.out.println(render(
                bundle, vi, "checkout.summary", "A-7", 3));
        System.out.println(bundle.getString("checkout.failed"));

        ResourceBundle root = catalog(Locale.ROOT);
        System.out.println(render(
                root, Locale.ROOT, "welcome", "Lan"));
    }
}
```

```bash
javac -encoding UTF-8 BundleLookupDemo.java
java BundleLookupDemo
```

Stdout (with UTF-8 console support):

```text
Xin chào, Lan!
Đơn A-7: 3 món
Payment failed.
Hello, Lan!
```

**How it works:**

- `ResourceBundle` locates the pattern for the matching key; calling `getString` **does not automatically substitute** `{0}` or `{1}`.
- `MessageFormat` takes the pattern and `Locale` to format arguments for that locale.
- `getNoFallbackControl(FORMAT_PROPERTIES)` disables **falling back to the JVM's default locale** but **does not remove the parent/root resource chain**; hence `checkout.failed` comes from root.
- `{0}` is the order ID; `{1,number,integer}` formats the integer item count in the sentence.
- Nothing depends on the server's `Locale.getDefault()` when rendering per user.

**JPMS limitation:** `ResourceBundle.getBundle` overloads accepting `ResourceBundle.Control` are not supported inside Java 17 **named modules** and can throw `UnsupportedOperationException`. This example intentionally runs on the **classpath/unnamed module**. For named-module applications, use a JPMS-compatible provider/bundle lookup mechanism rather than copying the example without heeding this restriction.

## 5. Fallback Does Not Mean a Complete Translation

In the example, `bundle.containsKey("checkout.failed")` can return `true` because the key is **inherited from root**, even though `messages_vi.properties` does not contain it. Therefore:

- **Runtime fallback** can prevent blank UI text for users.
- **Translation coverage** must inspect **each individual language file** or translation-tool metadata, not merely check `containsKey`.
- **Localization acceptance** may require every legal, payment, and safety message to have an approved translation rather than silently falling back to English.
- **Observability** should log the key, requested locale, catalog version, and fallback level while avoiding personal data from arguments in logs.

Two distinct concepts in `ResourceBundle.Control`:

1. **Candidate/parent chain** such as `vi-VN -> vi -> root`.
2. **Fallback to default locale** when no matching bundle exists, controlled by `getFallbackLocale`. `getNoFallbackControl` disables this second step.

### Missing-Key Failure

A key completely absent across the entire parent chain causes `getString` to throw `MissingResourceException`. Do not expect Java to return `null` or echo the key name automatically.

**`MissingKeyDemo.java`**, using the same two `.properties` files:

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingKeyDemo {
    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle vi = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"), control);

        System.out.println("Inherited key: "
                + vi.containsKey("checkout.failed"));
        System.out.println("Unknown key: "
                + vi.containsKey("checkout.unknown"));

        try {
            vi.getString("checkout.unknown");
            System.out.println("Unexpected success");
        } catch (MissingResourceException ex) {
            System.out.println("Missing key detected");
        }
    }
}
```

```bash
javac -encoding UTF-8 MissingKeyDemo.java
java MissingKeyDemo
```

Stdout:

```text
Inherited key: true
Unknown key: false
Missing key detected
```

When designing runtime error handling, decide which keys may fall back, which must block a release, and how to respond when a translation is still missing. Never write `catch(Exception)` and return `"?"` for all failures: that hides serious data bugs.

## 6. Parameter Contracts Are Part of the Message API

A message with placeholders is **a small API**. For `checkout.summary`, document the schema clearly:

| Position | Business name | Java type | Meaning | Constraints |
| --- | --- | --- | --- | --- |
| `{0}` | `orderId` | `String` | Display order ID | Required; not translated |
| `{1}` | `itemCount` | `Number`/`Integer` | Number of items | Non-negative integer |
| Format style | `{1,number,integer}` | Number formatter | Count presentation | Locale chosen by viewer |

Specify **name, position, type, nullability, meaning, unit, formatting, sensitivity**, and whether plural/gender rules apply. Simply writing "two parameters" is insufficient when one is currency and another is a ratio or calendar date.

**Positional parameters:** standard Java 17 `MessageFormat` uses indices `0`, `1`, ...; it does not directly understand named placeholders like `{orderId}`. Applications can build a typed facade for callers, but Java method parameter names are not automatically mapped into translations by `MessageFormat`.

**Reordering is allowed; swapping roles is not:** translators may place `{1}` before `{0}` for natural phrasing. However, translators must never reassign `{0}` to mean quantity if the contract defines it as the order ID.

## 7. Example: Reordering Parameters Across Languages

File **`ArgumentOrderDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentOrderDemo {
    public static void main(String[] args) {
        Object[] values = {"A-7", 3};

        String en = "Order {0}: {1,number,integer} items";
        String vi = "Có {1,number,integer} món trong đơn {0}";

        System.out.println("EN: "
                + new MessageFormat(en, Locale.US).format(values));
        System.out.println("VI: "
                + new MessageFormat(
                        vi, Locale.forLanguageTag("vi-VN"))
                        .format(values));
    }
}
```

```bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
```

Stdout:

```text
EN: Order A-7: 3 items
VI: Có 3 món trong đơn A-7
```

The same `values`, same indices, and same meanings appear in a different order. This example uses **quantity 3**; the English pattern `items` does not cover singular/plural across all counts. In production products, design proper locale-aware pluralization.

## 8. Parameter Types and Cases `MessageFormat` Does Not Automatically Guard

Main subformats in Java 17:

| Placeholder | Expected type / effect |
| --- | --- |
| `{0}` | Inserts `Object`; for `String`, uses string content |
| `{1,number}` | Expects a `Number` compatible with `NumberFormat` |
| `{1,number,integer}` | `Number` formatted as an integer for display |
| `{1,number,currency}` | `Number` with locale-attached currency subformat |
| `{1,number,percent}` | `Number` with percent subformat |
| `{2,date,short}` | Usually requires `java.util.Date`/type supported by date subformat |
| `{2,time,short}` | Locale-specific date/time |
| `{0,choice,...}` | Legacy `ChoiceFormat`, typically `Number`-based |

**`java.time` differs from `java.util.Date`:** `LocalDate`, `Instant`, and `ZonedDateTime` are not accepted by default by legacy `MessageFormat` date subformats. Pick types based on business semantics, then convert/format via `DateTimeFormatter` or a controlled adapter with `ZoneId` when needed.

**Currency:** `{1,number,currency}` may choose the currency unit from the locale, whereas the actual transaction uses a different currency code. The transaction contract must carry both `amount` and business `currencyCode`; never treat the viewer's locale as the payment currency.

**Missing arguments do not necessarily throw:** `MessageFormat` may leave literal `{1}` in place if the caller omits that index. Testing only "does not throw" is therefore insufficient.

### ParameterTypeDemo.java

```java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class ParameterTypeDemo {
    public static void main(String[] args) {
        MessageFormat f = new MessageFormat(
                "Order {0}: {1,number,integer} items",
                Locale.US);

        System.out.println("Argument slots: "
                + f.getFormatsByArgumentIndex().length);
        System.out.println("Arg 1 numeric: "
                + (f.getFormatsByArgumentIndex()[1]
                        instanceof NumberFormat));
        System.out.println("Correct: "
                + f.format(new Object[]{"A-7", 3}));

        try {
            f.format(new Object[]{"A-7", "3"});
            System.out.println("Wrong type accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong type rejected");
        }

        System.out.println("Missing: "
                + f.format(new Object[]{"A-7"}));
    }
}
```

```bash
javac -encoding UTF-8 ParameterTypeDemo.java
java ParameterTypeDemo
```

Stdout:

```text
Argument slots: 2
Arg 1 numeric: true
Correct: Order A-7: 3 items
Wrong type rejected
Missing: Order A-7: {1} items
```

**Validator warning:** `getFormatsByArgumentIndex` helps inspect whether a subformat exists at an index, yet unused slots can be `null` and the array length matches the highest index. Do not use **array length alone** to prove all parameters are used, correctly typed, and semantically valid. A strong contract requires a schema/linter plus render tests.

## 9. Single Quotes and Braces Are Syntax, Not Just Text

`MessageFormat` uses single quotes to quote literals. To output a literal `'`, a pattern normally needs **two consecutive quotes `''`**. Translators can accidentally disable placeholder substitution by writing single quotes incorrectly.

File **`ApostrophePatternDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ApostrophePatternDemo {
    public static void main(String[] args) {
        MessageFormat first = new MessageFormat(
                "It''s time for {0}.", Locale.US);
        MessageFormat second = new MessageFormat(
                "Click ''Save'' to {0}.", Locale.US);

        System.out.println(first.format(
                new Object[]{"Lan"}));
        System.out.println(second.format(
                new Object[]{"continue"}));
    }
}
```

```bash
javac -encoding UTF-8 ApostrophePatternDemo.java
java ApostrophePatternDemo
```

Stdout:

```text
It's time for Lan.
Click 'Save' to continue.
```

`.properties` syntax and `MessageFormat` syntax are **two separate layers**: Java processes `.properties` escapes first, and then `MessageFormat` parses `{index}`, format types, and quotes. A valid `.properties` file can still hold an **invalid `MessageFormat` pattern**, or a pattern that parses without throwing while no longer substituting the intended placeholder.

**Do not parse complex `MessageFormat` patterns with naive regexes.** `ChoiceFormat` can contain nested patterns, and `'` alters the meaning of braces. A real validator needs a proper parser and message metadata; `new MessageFormat(pattern, locale)` is only a syntax check and cannot know that `{1}` must mean `itemCount`.

## 10. Plurals, Gender, and Text Context Must Be Modeled

Do not build English sentences with `count + " item" + (count == 1 ? "" : "s")` and assume every language can be localized that way. Many languages have different singular/plural rules; grammatical gender, honorifics, or word roles may also require variants.

Java's `ChoiceFormat` can handle a few numeric branches, **but it does not provide full CLDR plural rules out of the box**. For rich multilingual needs, consider a message system with proper plural/select support (such as ICU MessageFormat) and test across actual target locales.

Provide translators with **sentence context** and parameter specifications. If a message includes a count, split it into variants or use a pluralization tool. If a message includes a person's name, do not force grammatical gender onto names. Two contexts sharing the exact same English wording under one key may still require separate keys in other languages.

## 11. Resource Versioning: Which Artifact Contains What?

There are multiple versioning layers:

| Version type | Role |
| --- | --- |
| Application version | Java code/API callsites and UI |
| Catalog version | Snapshot of keys, patterns, and translations |
| Contract version | Semantics and parameter schema for a key |
| API version | Shape of message codes/data received by clients |
| JDK/CLDR version | Locale data used to format dates, numbers, and currency |
| Translation tooling version | Parser/linter governing translation changes |

Example: build `2026.10.28` ships with `catalogVersion=3`, where `checkout.summary` is on contract 1. Later the UI needs to add `deliveryDate`, making the new contract incompatible with older callers. Do not mutate the existing pattern directly so that older clients suddenly require `{2}`.

**Immutable snapshots:** ideally every build uses a validated catalog with a known version or hash. When a bug report says "wrong translation", you need **app version, catalog version, requested locale, and key** to reproduce it. With dynamic translation services, swap catalogs atomically only after full validation—never update key by key, leaving the system half v1 / half v2.

### When Should a Key Change?

- **Keep the key** when fixing typos, punctuation, or phrasing while meaning and parameters stay identical.
- **You may keep the key** when a translation reorders `{0}`/`{1}` while preserving the contract.
- **Change the key or contract version** when a required parameter is added, removed, changes type, or changes meaning.
- **Change the semantic key** when the message no longer describes the same action or state.
- **Do not bump a `v2` suffix for every copy edit**, as that bloats the catalog needlessly.

## 12. Example: Two Contracts Coexisting During a Rolling Deployment

Suppose v1 only needs an order ID; v2 requires both an order ID and a tracking code. While servers and clients are not upgraded simultaneously, keep both patterns:

```properties
purchase.confirmed.v1=Confirmed order {0}.
purchase.confirmed.v2=Confirmed order {0} with tracking {1}.
```

**VersionedMessageDemo.java**:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.Map;

public class VersionedMessageDemo {
    public static void main(String[] args) {
        Map<String, String> patterns = Map.of(
                "purchase.confirmed.v1",
                "Confirmed order {0}.",
                "purchase.confirmed.v2",
                "Confirmed order {0} with tracking {1}.");

        String old = new MessageFormat(
                patterns.get("purchase.confirmed.v1"),
                Locale.US).format(new Object[]{"A-7"});

        String newer = new MessageFormat(
                patterns.get("purchase.confirmed.v2"),
                Locale.US).format(new Object[]{"A-7", "T-9"});

        System.out.println("V1: " + old);
        System.out.println("V2: " + newer);
    }
}
```

```bash
javac -encoding UTF-8 VersionedMessageDemo.java
java VersionedMessageDemo
```

Stdout:

```text
V1: Confirmed order A-7.
V2: Confirmed order A-7 with tracking T-9.
```

The `v1/v2` suffix here expresses **two incompatible contracts coexisting concurrently**, not a rule that every key needs a version suffix. Use v2 for new callers; keep v1 while legacy clients remain supported, then clean up once observability confirms zero remaining usage.

## 13. Rollout: Add First, Migrate Gradually, Remove Last

A safe strategy:

1. Define the schema, types, and semantics of the new contract; specify the minimum catalog version required by new callers.
2. Add the new key/pattern to the **root catalog and required locales**, reviewing grammar and parameters.
3. Run CI linting and preview across locales before release.
4. Deploy new resources **before or together with new callers** using your product's atomic/compatible mechanism.
5. Keep old keys long enough for offline mobile apps, background jobs, notification queues, and supported versions.
6. Monitor usage frequency of old keys and missing/failed renders by version and locale.
7. Once the compatibility window closes, remove old keys along with dependent code and keep a rollback plan.

When sending errors over an API, return **status codes and typed data** rather than only a localized message. Clients can then use the catalog matching their locale and version. If the server returns a `localizedMessage`, document clearly who owns translation and what happens if the user switches language afterward.

### Caching and `ResourceBundle` Lifecycle

`ResourceBundle` is **cached** by the lookup mechanism; editing a file outside runtime does not guarantee a running JVM immediately reloads it. `ResourceBundle.Control.getTimeToLive`, `needsReload`, and `ResourceBundle.clearCache` have specific roles, yet **clearing the cache does not guarantee the deployment artifact already contains the new file**. Do not change `System.setProperty` or edit `.properties` files between requests expecting all clients to see a consistent catalog. With named modules, verify the control/provider behavior in your actual environment.

`MessageFormat` is **mutable**, so never share an instance across threads calling `applyPattern`/`setFormat` without synchronization. Create a dedicated formatter per render or clone/copy in a controlled manner.

## 14. Checking Which File Actually Lacks Translations

`ResourceBundle.containsKey` sees inherited keys; to measure coverage **of the `vi` file itself**, read both files and compare key sets directly in CI.

**BundleCoverageDemo.java** (using the `.properties` files from Section 3):

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.Set;
import java.util.TreeSet;

public class BundleCoverageDemo {
    private static Properties read(String name) throws Exception {
        Properties properties = new Properties();
        try (Reader input = Files.newBufferedReader(
                Path.of(name), StandardCharsets.UTF_8)) {
            properties.load(input);
        }
        return properties;
    }

    public static void main(String[] args) throws Exception {
        Properties root = read("messages.properties");
        Properties vi = read("messages_vi.properties");

        Set<String> missing = new TreeSet<>(
                root.stringPropertyNames());
        missing.removeAll(vi.stringPropertyNames());

        Set<String> unexpected = new TreeSet<>(
                vi.stringPropertyNames());
        unexpected.removeAll(root.stringPropertyNames());

        System.out.println("Missing vi: " + missing);
        System.out.println("Unexpected vi: " + unexpected);
    }
}
```

```bash
javac -encoding UTF-8 BundleCoverageDemo.java
java BundleCoverageDemo
```

Stdout:

```text
Missing vi: [checkout.failed]
Unexpected vi: []
```

This matches the two example files: the `vi` file lacks `checkout.failed`. In real projects, some fallbacks may be permitted while mandatory translations fail the build. The program above **only compares keys**: it does not verify translation accuracy, duplicate keys, or parameter/type consistency.

**Note:** `Properties.load(Reader)` reads characters already decoded by the `Reader`; the example uses `Files.newBufferedReader(..., UTF_8)` to avoid relying on an implicit encoding. `Properties` silently overwrites duplicate keys without warning, so catching duplicates in source files requires a dedicated linter.

## 15. Linting Patterns and Type Contracts

A catalog entry can be accompanied by metadata:

```yaml
key: checkout.summary
description: Summary of item count in a purchase order
contractVersion: 1
arguments:
  - index: 0
    name: orderId
    type: string
    required: true
  - index: 1
    name: itemCount
    type: integer-number
    required: true
localesRequired: [en, vi]
```

This is an **application-defined example schema**, not a YAML format natively understood by `ResourceBundle` or `MessageFormat`.

A reliable CI suite should:

- Verify required keys exist in the root catalog and all mandatory locales.
- Detect duplicate keys, orphaned keys with no callsites, and invalid string/type definitions.
- Parse `MessageFormat` patterns per locale and catch malformed quotes/braces.
- Verify **required** placeholders are actually used, with no stray indices and proper format styles per index.
- Test inputs `0`, `1`, `3`, large numbers, dates, names containing single quotes, Unicode, and RTL languages where relevant.
- Check for long translations overflowing the UI, out-of-context messages, and plural/gender requirements.
- Avoid logging sensitive payloads; log key + locale + version when debugging.
- Run against the exact same resource version/data packaged in the application.
- Test fallbacks, reload/cache behavior, and older clients calling v1 keys.

**Limitation:** `new MessageFormat(pattern, locale)` provides useful syntax validation, but it does not know whether `{0}` means `orderId` or `username`. A regex like `\\{(\\d+)\\}` cannot fully parse subformats with quotes or nested patterns. CI must therefore rely on schemas and proper parsers/validators rather than naive regex matching.

## 16. A Typed Facade Reduces Callsite Mistakes

Java callers often only see `render(String key, Object... args)`, making parameter order and types easy to mix up. A business-level wrapper makes the contract explicit:

```java
// Fragment inside a class that already defines render(key, Object... args).
public String checkoutSummary(String orderId, int itemCount) {
    if (itemCount < 0) {
        throw new IllegalArgumentException(
                "itemCount must not be negative");
    }
    return render("checkout.summary", orderId, itemCount);
}
```

This is a **fragment**, not a standalone program. It lets the compiler enforce `String` and `int` at callsites with a clear business name and validation. However, **it still does not guarantee translators keep placeholders intact**: a translation can drop `{1}` with no compile error. Typed-facade tests and catalog checks must therefore run side by side.

Large organizations may generate typed methods from message schemas via code generation, though **core Java does not auto-generate contracts from `.properties` files**. Treat code generation as supplementary architecture, not as a built-in `ResourceBundle` feature.

## 17. Distinguishing `MessageFormat` from HTML Escaping and Security

Arguments are **data** to format; `MessageFormat` **is not an XSS filter, HTML escaper, or SQL escaper**. For example, a person's name containing `<script>` rendered unescaped into an HTML output sink can create a vulnerability. Use context-appropriate HTML templating/output encoding, and construct messages from **trusted** catalog keys/patterns.

Never concatenate user input directly into a **pattern** passed to `new MessageFormat(...)`, because `'`, `{`, and `}` characters alter template syntax. Instead, use vetted catalog patterns and pass user data solely as arguments.

For emails, notifications, and machine-readable errors, separate **event semantics** from phrasing. If an API payload carries `"code": "PAYMENT_DECLINED"` and typed data, the presentation layer can render in any language without changing logic.

## 18. Workflow for Developers, Translators, and Reviewers

A lean yet complete workflow:

1. Developer declares a **semantic key**, owner, context description, and expected parameters.
2. Contract reviewer confirms types, nullability, units, plural/gender needs, locale/timezone, and contract version.
3. Translator receives the pattern + context; may reorder placeholders, but must not change indices or types.
4. Tooling validates UTF-8, `.properties` syntax, `MessageFormat` patterns, missing keys, coverage, duplicate keys, and placeholder contracts.
5. Reviewer inspects sentences in the actual UI, checking layout and phrasing across counts and contexts.
6. CI tests all required locales plus v1/v2 and fallback scenarios.
7. Build bundles an immutable catalog snapshot/version with the binary or updates resources atomically.
8. Deployment preserves compatibility across web/mobile/backend/batch during transitions.
9. Monitoring tracks missing-key/fallback metrics by key, locale, and `catalogVersion` without logging secrets.
10. Old keys are removed only when no supported clients remain and a rollback plan exists.

If translators only see `"Order {0}: {1} items"`, they can misinterpret parameters. A better note is: `{0} is the order ID, do not translate; {1} is the non-negative integer item count in the order; appears on the cart screen`.

## 19. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using English sentences as keys | Changing copy breaks lookup | Use semantic keys |
| Reusing a key for another meaning | Wrong translation/context | Split keys by intent |
| Renaming a key without updating callers | `MissingResourceException` | Typed facade, static scan, tests |
| Treating `containsKey` as "translated" | Root fallback hides missing locale keys | Compare locale files directly |
| Swapping `{0}` and `{1}` by mistake | Wrong data shown in UI | Schema/index QA |
| Caller passes `"3"` for a `number` slot | Runtime error | Pass typed `Number` args |
| Missing argument fails silently | Literal `{1}` printed in UI | Required-args validation |
| Unescaped single quote in pattern | Placeholders fail to format | Test `MessageFormat` |
| Assuming `MessageFormat` has full CLDR plurals | Unnatural grammar | Use proper pluralization tooling |
| Adding required parameter to existing key | Breaks older clients | Version contract / parallel keys |
| Deleting old key immediately on backend deploy | Older mobile/jobs still use it | Track compatibility window |
| Not attaching catalog version to builds | Hard to reproduce translation bugs | Track snapshot/version/hash |
| Relying on server default `Locale` | Displays wrong user language | Pass `Locale` explicitly |
| Assuming `getNoFallbackControl` blocks root | Misunderstands candidate chain | Distinguish default fallback vs parent |
| Using `Control` inside a named module | `UnsupportedOperationException` | Use JPMS-compatible design |
| Editing files while forgetting bundle caching | Runtime keeps stale text | Manage cache/version lifecycle |
| Sharing mutable `MessageFormat` across threads | Races/inconsistency | Per-render instance |
| Treating `MessageFormat` as HTML escaping | XSS at output sink | Context-aware escaping |
| Testing only English translations | Quote/locale bugs slip through | QA all required locales |

## 20. Practice Exercises

**Exercise 1 — Meaningful keys:** design semantic keys for a sign-in screen, account errors, shopping cart, and checkout. Explain when the exact same English phrase still requires two separate keys.

**Exercise 2 — Parameters:** write a schema for `checkout.summary` with `orderId`/`string` and `itemCount`/`number`. Translate into two languages with different parameter orders, and verify the output using `ArgumentOrderDemo`.

**Exercise 3 — Fallback:** run `BundleLookupDemo` and `MissingKeyDemo`. Observe `checkout.failed` coming from root and `checkout.unknown` throwing an error. Explain why the UI should still monitor missing translations even when fallback works.

**Exercise 4 — Coverage check:** run `BundleCoverageDemo`, add a translation for `checkout.failed` to the `vi` file, and verify the missing set becomes `[]`.

**Exercise 5 — Syntax trap:** run `ApostrophePatternDemo`; replace `It''s` with `It's` and observe the behavior. Design a linter rule to catch improperly quoted strings.

**Exercise 6 — Wrong type / missing argument:** using `ParameterTypeDemo`, replace `Integer` `3` with `String` `"3"` and test omitting an argument. Why is catching exceptions insufficient to confirm a template is valid?

**Exercise 7 — Version lifecycle:** catalog v1 has `purchase.confirmed.v1`, and v2 adds tracking. Plan the rollout across offline mobile clients and backend, criteria for removing v1, and rollback testing.

**Exercise 8 — Security:** test a person's name containing HTML markup and single quotes. Distinguish pattern parsing, argument formatting, HTML escaping, and sensitive-data logging.

## 21. References

- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): lookup, fallback, `keySet`/`containsKey`, caching.
- [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): `getNoFallbackControl`, candidate locales, TTL, and named-module limitation.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8 and ISO-8859-1 fallback.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholders, number/date subformats, quoting, missing arguments, and `getFormatsByArgumentIndex`.
- [Java SE 17 — MissingResourceException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/MissingResourceException.html): missing bundle/key.
- [Unicode CLDR](https://cldr.unicode.org/): locale data and plural rules guiding advanced localization requirements.

## 22. Key Takeaways

**A resource key is a semantic contract; a message catalog is a versioned artifact; a placeholder is a typed, semantic API.** Name keys for function rather than wording, keep them during copy edits, and introduce a new contract for incompatible changes. Use `ResourceBundle` to select content by locale and `MessageFormat` to substitute parameters, while designing versioning, typed schemas, coverage checks, and CI validation yourself.

A safe release **adds new keys first, lets versions coexist, monitors usage, and removes old keys last**. Inspect actual locale files alongside fallbacks; never mistake `containsKey` for a complete translation. Always verify translators have not broken indices, types, quotes, plurals, or argument semantics. Reliable systems keep **business data and error codes independent of display sentences**, so changing languages never alters logic.
