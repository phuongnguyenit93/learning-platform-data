# Do Not Apply the Same Case Policy to Every Data Field

In multilingual applications, the strings `"Lan"`, `"LAN"`, and `"lan"` may represent **the same username** if the product defines usernames as case-insensitive. However, for **passwords, access codes, signature strings, case-sensitive identifiers**, or user-entered names, those three strings can carry **different meanings**. Therefore, applying `toLowerCase()` or `equalsIgnoreCase()` uniformly to every column is a data design flaw, not a way to make an application "localization-friendly".

This Knowledge lesson belongs to the **Uppercase and Lowercase** topic of Java Core Localization. The focus is on **choosing and enforcing case mapping / comparison / storage policies according to each field's semantics**, rather than routing all data through a single generic normalization function. The lesson uses **Java 17+**, runnable code, and scenarios covering Turkish `I`/`ı`, German `ß`, Unicode NFC, identifier keys, display content, emails, and data requiring exact preservation.

**Foundational principle:** Before changing case, determine **what this data is, who defines equivalence rules, whether the original spelling must be preserved, whether it is used for display or as a lookup key, and whether that rule is consistent across systems**.

## 1. Three operations often lumped into one

There are three distinct needs:

1. **Transforming spelling for display** (*case conversion*): e.g., rendering a heading in uppercase according to the viewer's language.
2. **Case-insensitive comparison** (*case-insensitive comparison*): e.g., matching two usernames defined as equivalent.
3. **Generating stable data keys** (*canonical key/identity policy*): e.g., ensuring every valid variant of the same user code looks up the same record.

Not every operation is properly solved by a `String.toLowerCase(...)`. For personal names, titles, and prose, changing case can affect linguistic rules; for protocol keys, locale-independent conventions are needed and only **ASCII** may be allowed; for passwords or tokens, changing any single code point can alter the value completely.

| Data | Question to answer first | Illustrative behavior |
| --- | --- | --- |
| Display name | Must user spelling be preserved? | Keep `Nguyễn Thị Lan` verbatim; search uses a separate index |
| Username | Does the rule distinguish case? | If the product chooses case-insensitive, `Lan_01` and `LAN_01` share a key |
| Password/passphrase | Does the auth protocol allow changing characters? | Do not auto-change case |
| Access token, API key | Is it an exact byte/character-sensitive string? | Preserve exact data, compare per protocol |
| ASCII protocol code | Does the standard define uppercase conventions? | ISO currency codes like `USD`; validate against valid code set |
| Email | Do local part and domain share the same rule? | Do not auto-lowercase the entire address |
| Filename, path | Does the OS/filesystem distinguish case? | Do not impose one policy across all platforms |
| Search text | Should case, diacritics, Unicode variants be ignored? | Dedicated search policy, without necessarily altering original content |

Important conclusion: **"case-insensitive" must be part of a data field's contract**, not a "convenience feature" bolted on after data has already been used as keys.

## 2. Which APIs does Java have and what are their limits?

Common operations:

```java
String a = "TITLE";
String lower = a.toLowerCase(Locale.ROOT);
String upper = a.toUpperCase(Locale.ROOT);
boolean equal = a.equalsIgnoreCase("title");
```

This is a **fragment** inside a method where `java.util.Locale` is imported.

| API | Meaning | What must not be implicitly assumed |
| --- | --- | --- |
| `String.toLowerCase()` | Lowercase using the **JVM's default locale** | Unstable output if environments have different locales |
| `String.toUpperCase()` | Uppercase using the **JVM's default locale** | Unsuitable as a standard for environment-independent machine keys |
| `toLowerCase(Locale)` | Case mapping for the specified locale | Not always a one-to-one mapping |
| `toUpperCase(Locale)` | Case mapping for the specified locale | Resulting string can be longer than the original |
| `equalsIgnoreCase(String)` | Case-insensitive comparison per `String` algorithm, **accepts no Locale** | Not full linguistic comparison or Unicode full case folding |
| `compareToIgnoreCase(String)` | Case-insensitive ordering using Java `String` rules | Does not replace locale-aware text sorting |
| `java.text.Collator` | Locale-based text comparison supporting configurable case/accent sensitivity | Not a general identifier rule for tokens/API keys |
| `java.text.Normalizer` | Canonical/compatibility Unicode normalization | Does not perform case conversion or full case folding |

**Version note:** this lesson relies only on APIs available in **Java 17**. When more comprehensive Unicode case folding or an identifier security profile is desired, examine libraries/standards implementing them, such as ICU4J or Unicode identifier/security profiles; do not assume `equalsIgnoreCase` equals that entire system.

## 3. The default locale can corrupt internal keys

Java documentation states clearly that `toLowerCase()` is equivalent to `toLowerCase(Locale.getDefault())`. This is dangerous for protocol identifiers, keywords, config field names, or usernames if the key contract does not follow the server's language.

For example, Turkish has **`I`** and **`ı`** (dotless i); when lowercased in the `tr-TR` locale, ASCII `I` does not become the familiar ASCII `i`.

**Standalone program — `DefaultLocaleTrapDemo.java`:**

```java
import java.util.Locale;

public class DefaultLocaleTrapDemo {
    public static void main(String[] args) {
        String input = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");

        String rootKey = input.toLowerCase(Locale.ROOT);
        String trKey = input.toLowerCase(turkish);

        System.out.println("ROOT key: " + rootKey);
        System.out.println("Turkish equals title: "
                + trKey.equals("title"));
        System.out.println("Turkish contains dotless i: "
                + trKey.contains("\u0131"));
        System.out.println("Same key: "
                + rootKey.equals(trKey));
    }
}
```

```bash
javac -encoding UTF-8 DefaultLocaleTrapDemo.java
java DefaultLocaleTrapDemo
```

Stdout:

```text
ROOT key: title
Turkish equals title: false
Turkish contains dotless i: true
Same key: false
```

This example **passes an explicit locale**, without mutating the JVM-wide locale, so running on systems with different default locales still demonstrates the exact same comparison.

**How should you choose?** For **product-defined machine codes permitting ASCII only**, `Locale.ROOT` is a more stable choice than the default locale when case conversion is needed. However, `Locale.ROOT` is **not** a substitute definition for all Unicode case-folding rules; for usernames supporting Unicode, define a fuller policy covering character sets, normalization, case equivalence, collisions, and testing target languages.

Do not call `Locale.setDefault(...)` to switch language per HTTP request. The default locale is shared JVM state; when multiple users act concurrently, changing it can affect other requests. **Pass the request's `Locale` into where it is actually needed.**

## 4. Uppercase/lowercase do not always have equal lengths

Case mapping in Unicode is not required to replace each character with exactly one character. For example, in German, **`ß`** can become **`SS`** when calling `String.toUpperCase(Locale.ROOT)`. Latin capital I with dot `İ` can lowercase under `Locale.ROOT` to **`i` + combining dot**, increasing the code point count.

**File `CaseExpansionDemo.java`:**

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String sharpS = "\u00DF";
        String expanded = sharpS.toUpperCase(Locale.ROOT);

        System.out.println("Sharp S upper: "
                + expanded.equals("SS"));
        System.out.println("Sharp S lengths: "
                + sharpS.length() + " -> " + expanded.length());

        String dottedI = "\u0130";
        String rootLower = dottedI.toLowerCase(Locale.ROOT);
        System.out.println("Dotted I ROOT length: "
                + rootLower.length());

        String trLower = dottedI.toLowerCase(
                Locale.forLanguageTag("tr-TR"));
        System.out.println("Dotted I Turkish equals i: "
                + trLower.equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Stdout:

```text
Sharp S upper: true
Sharp S lengths: 1 -> 2
Dotted I ROOT length: 2
Dotted I Turkish equals i: true
```

**Consequence:** Do not produce a lowercased/uppercased string and assume `length()` and UTF-8 byte count stay unchanged. If a database index limits key length or a protocol forbids certain characters, **recheck length and character set after transformation**. If case mapping creates collisions, two distinct inputs can collapse into a single key.

Technically, `String.length()` is the number of UTF-16 code units, not necessarily the number of code points or user-perceived characters (*grapheme clusters*). For multilingual text, specify the exact unit when enforcing length limits.

## 5. Personal name fields and display content: preserve original spelling

A name like `Đặng`, `McDonald`, `van Gogh`, or a brand with specific capitalization should not be forced to uppercase/lowercase merely for "data normalization". Moreover, case conversion can depend on the language the user entered, not necessarily matching the language currently viewing the UI.

Reasonable policies depend on the product:

- **Store the original:** keep names/text as entered by the user when meaningful in legal, cultural, or personal-expression contexts.
- **Optionally normalize Unicode NFC when the contract permits:** NFC normalizes *canonical equivalence* such as two ways of encoding the same accented letter; it **does not** automatically convert uppercase to lowercase.
- **Create a separate search field:** if case-insensitive/diacritic-insensitive search is needed, build a separate key or index while keeping the original content for display.
- **Output casing** only when required by UI design, using appropriate locale/editorial rules. Word-by-word "title case" via `split(" ")` then `toUpperCase` is incorrect across many languages and proper names.

You cannot infer the language required for a name solely from the server's `Locale` or country of residence. Users may set an interface language different from the language of their name.

**Fragment illustrating storing a name and a separate canonical matching key:**

```java
String originalName = "Đặng";
String canonicalForMatching = java.text.Normalizer.normalize(
        originalName,
        java.text.Normalizer.Form.NFC);
// Store/display originalName per policy; do not auto-uppercase/lowercase.
```

NFC normalization helps match strings with the same Unicode letters encoded differently. However, if case-insensitive search is wanted, NFC is **not enough** and a separate explicitly designed policy is needed.

## 6. Usernames: choose an identity policy before registering accounts

A username is an **identifier**, not just a display string. There are two different valid designs, depending on requirements:

**A. Case-sensitive username.** `Lan_01` and `LAN_01` are two distinct values. The system must align login, profile URLs, cache keys, database `UNIQUE` constraints, and APIs with that rule.

**B. Case-insensitive username.** Those two values represent one identity. In that case, the system must define **how to build the canonical key**, apply the same policy across registration, login, lookup, updates, and migration, and decide whether to keep an original `displayHandle` or display the canonical key itself.

A **simple and controllable** configuration for internal usernames is **restricting to ASCII** and then lowercasing with `Locale.ROOT`. This is an *application rule*, not a universal standard for all usernames worldwide.

### Runnable example: ASCII username with explicit rules

Save **`UsernamePolicyDemo.java`**:

```java
import java.util.Locale;

public class UsernamePolicyDemo {
    public static String key(String raw) {
        if (raw == null
                || !raw.matches("[A-Za-z][A-Za-z0-9_]{2,15}")) {
            throw new IllegalArgumentException(
                    "Invalid username syntax");
        }
        return raw.toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String first = key("Lan_01");
        String second = key("LAN_01");

        System.out.println("First: " + first);
        System.out.println("Second: " + second);
        System.out.println("Same identity: "
                + first.equals(second));

        try {
            key("Lăn_01");
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Non-ASCII rejected by this policy");
        }
    }
}
```

```bash
javac -encoding UTF-8 UsernamePolicyDemo.java
java UsernamePolicyDemo
```

Stdout:

```text
First: lan_01
Second: lan_01
Same identity: true
Non-ASCII rejected by this policy
```

**Reading the example's boundaries accurately:** This product **intentionally** does not support Unicode in usernames, while it may support Unicode in `displayName`. Do not claim Unicode usernames are wrong in general; products allowing Unicode must design a dedicated identifier profile covering normalization, case folding, confusables handling, and uniqueness.

The regex limits to 3–16 ASCII characters, starting with an ASCII letter. Business rules may also ban system-reserved names, sensitive words, recycled old names, and require storing the original display form. Do not rely on regex alone as the entire account policy.

## 7. Collisions: changing case policy can create identity ambiguity

If two users already exist with `Lan_01` and `LAN_01` in a case-sensitive database, switching to case-insensitive without checking existing data maps both to `lan_01`. A unique index on the new key will hit conflicts; worse, login code could select the wrong account if collisions are handled carelessly.

**File `CaseCollisionDemo.java`:**

```java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class CaseCollisionDemo {
    public static void main(String[] args) {
        String[] existing = {
                "Lan_01", "LAN_01", "Minh_2"
        };

        Map<String, String> firstByKey = new LinkedHashMap<>();
        for (String raw : existing) {
            String key = raw.toLowerCase(Locale.ROOT);
            String prior = firstByKey.putIfAbsent(key, raw);
            if (prior == null) {
                System.out.println(raw + ": accepted");
            } else {
                System.out.println(raw
                        + ": conflict with " + prior);
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 CaseCollisionDemo.java
java CaseCollisionDemo
```

Stdout:

```text
Lan_01: accepted
LAN_01: conflict with Lan_01
Minh_2: accepted
```

This program **only detects** collisions; it does not resolve identity disputes by itself. A real migration must clearly decide key ownership, how to contact account owners, updating foreign keys/URLs, login history, caches, policy versioning, and rollback if needed.

A **consistent policy** matters more than choosing lower or upper: if registration uses `Locale.ROOT` while login uses `Locale.getDefault()`, or backend and database use different collations, the system may accept accounts that cannot be found later or mix up accounts.

## 8. Passwords, passphrases, tokens: do not alter characters automatically

Authentication-related fields typically carry a contract to **preserve the exact value sent by the user or protocol**. Therefore:

- Do not automatically `trim()`, `toLowerCase()`, `toUpperCase()`, or Unicode-normalize **passwords** unless the system/protocol authentication policy defines that transformation.
- Do not redisplay passwords or log them to "compare case".
- Do not use `equalsIgnoreCase` when verifying **access tokens, API secrets, or cryptographic signatures**, unless a specific standard genuinely defines case-insensitive comparison (do not assume).
- Passwords should be processed using **salted password hashing/KDF with appropriate security parameters**, never stored in plaintext. Any choice of Unicode normalization/encoding for passwords must adhere to the authentication system's standard and compatibility history.
- String tokens must follow **specific formats**: for instance, Base64/Base64URL is case-sensitive. If a server changes the case of a token like `aB0`, it is no longer the same input string.

**Do not equate "typed on a keyboard" with "safe to auto-convert by locale".** Systems may ask users to re-enter for confirmation, but should never secretly alter authentication inputs.

For sensitive data, also consider memory retention time, logging, TLS transport, key/secret protection, and secure comparison mechanisms from security libraries. `String.equalsIgnoreCase` is definitely not a password verifier.

## 9. Email: domain and local part do not necessarily share the same rule

An email address looks like a single field `user@domain.example`, yet actually has two distinct parts:

1. **Domain:** DNS domain names are case-insensitive during DNS lookup. They can be canonicalized per chosen domain and IDNA rules; for example, ASCII `Example.COM` and `example.com` typically refer to the same DNS name.
2. **Local part:** under the SMTP protocol model, the part before `@` *can in principle be case-sensitive*; real-world providers have varying policies. Do not assume `Sales@example.com` and `sales@example.com` always reach the same mailbox on every server.

Therefore **do not lowercase the entire email address** and treat it as a safe canonical identity. Applications handling addresses from a provider they control may apply provider-specific rules, but those must be defined by the provider and product, not by intuition.

Variants like dots in the local part, `+` subaddressing tags, or Unicode in EAI/IDN also depend on standards and providers. Even more reason not to strip dots, drop everything after `+`, or lowercase entire emails with one shared helper when building a multi-provider signup system.

### Recommended data organization

- Store the **user-supplied address** per policy so mail can be delivered back to the right place.
- Validate format with an appropriate parser/validator; do not simply `split("@")` to handle all valid email syntax cases.
- You may maintain a **lookup key** per product contract, without claiming it uniquely identifies every mailbox on the Internet.
- Use **email ownership verification** and anti-duplicate account policies; do not treat lowercasing or dot removal as proof that two addresses belong to the same person.
- When applying IDN, distinguish Unicode domains from ASCII labels (IDNA/Punycode) and use corresponding libraries/rules. Simple case conversion **does not replace** IDNA.

## 10. Protocol codes, enums, JSON keys, and configuration names

For data defined by a **protocol or schema**, follow the exact contract:

| Field | What is the right policy? | Example |
| --- | --- | --- |
| ISO 4217 currency code | Use registered codes with ASCII conventions; validate against valid code set | `USD`, `VND` |
| Language/locale code | BCP 47 with language/script/region casing conventions | `vi-VN`, `zh-Hant-TW` |
| API enum | Per schema: may be case-sensitive or have documented aliases | `"PAID"` differs from `"paid"` if schema says so |
| JSON object key | A string; by default must match schema exactly | `"userId"` is not automatically synonymous with `"userid"` |
| HTTP field name | Per HTTP standard, header names are case-insensitive | `Content-Type` and `content-type` |
| ResourceBundle key | Match key name declared in bundle; do not auto-lowercase on lookup | `message.title` |
| Textual UUID | Follow UUID parser/serialization and API contract | Do not apply generic lowercasing to every ID type |

Do not infer that "Internet standards mean everything is case-insensitive". **HTTP header names** are case-insensitive, yet **header values** can have their own rules. JSON keys are usually matched by exact schema name; systems must not merge `userID` and `userId` unless the contract allows it.

### Choosing controlled ASCII code normalization

If a field accepts a **three-letter ASCII currency code** and the product wants to accept lowercase input, a pipeline can:

1. Validate syntax `[A-Za-z]{3}` (disallowing spaces, diacritics, or digits).
2. Uppercase using `Locale.ROOT`.
3. Verify the code **actually exists/is valid** per business rules and supported currencies.
4. Store the standard code, rather than treating every three-letter string as a currency.

**File `ProtocolCodeDemo.java`:**

```java
import java.util.Currency;
import java.util.Locale;

public class ProtocolCodeDemo {
    private static String currencyCode(String raw) {
        if (raw == null || !raw.matches("[A-Za-z]{3}")) {
            throw new IllegalArgumentException("Bad syntax");
        }
        String uppercase = raw.toUpperCase(Locale.ROOT);
        return Currency.getInstance(uppercase).getCurrencyCode();
    }

    public static void main(String[] args) {
        System.out.println("Code: " + currencyCode("usd"));
        System.out.println("Language tag: "
                + Locale.forLanguageTag("EN-us").toLanguageTag());

        try {
            currencyCode("u$d");
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid syntax rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 ProtocolCodeDemo.java
java ProtocolCodeDemo
```

Stdout:

```text
Code: USD
Language tag: en-US
Invalid syntax rejected
```

For `Locale`, the `toLanguageTag()` API handles BCP 47 tag formatting better than `String.toLowerCase(Locale.ROOT)`; parts like region follow uppercase conventions. For APIs that must reject malformed BCP 47 tags, use `Locale.Builder.setLanguageTag(...)` along with supported-locale checks, since `Locale.forLanguageTag(...)` handles inputs relatively leniently.

## 11. Filenames and paths: system-dependent, not a single Java rule

Filesystems and platforms can differ on whether `Report.csv` and `report.csv` refer to the same path. Even within the same OS, filesystem type or volume configuration can dictate how names are compared. Therefore:

- Do not use `path.toString().toLowerCase()` as a "canonical path across all machines".
- When checking extensions like `.CSV`, you can pick a **rule specifically for the extension** if the product permits. Do not auto-alter the entire directory/file name because that can break real paths.
- When using paths from user input, guard against path traversal and enforce permission checks; changing case does not mitigate these risks.
- If file paths are exposed in APIs or stored in a database, consider storing a **file ID** separated from display name and search rules whenever possible.
- Do not conclude a path is safe simply because two spellings are treated as equal by `equalsIgnoreCase`.

Similarly, a URL has multiple distinct components: the **host** follows domain name rules, while **path/query** are defined by the target service. Use a URI parser and each component's protocol rules rather than lowercasing the entire URL and treating it as the same resource.

## 12. equalsIgnoreCase, Locale.ROOT, and Unicode case folding are not synonymous

Three strategies have different scopes and purposes:

- `equalsIgnoreCase`: compares case-insensitively per `String`'s algorithm. **Takes no locale** and does not guarantee equivalence with linguistic comparison.
- `toLowerCase(Locale.ROOT)` then `equals`: produces two locale-independent lowercased keys, yet **is not a complete Unicode full case folding definition**.
- **Unicode full case folding**: defined by Unicode for case-insensitive matching under broader rules, potentially involving multi-code-point mappings and requiring appropriate implementation mechanisms.

The German example shows the difference: `"Straße"` contains `ß`, whereas `"STRASSE"` uses two `S` letters. `equalsIgnoreCase` should not be treated as producing a complete equivalence key in such expansion cases.

**Program `ComparisonStrategiesDemo.java`:**

```java
import java.text.Normalizer;
import java.util.Locale;

public class ComparisonStrategiesDemo {
    public static void main(String[] args) {
        String a = "Stra\u00DFe";
        String b = "STRASSE";

        System.out.println("equalsIgnoreCase: "
                + a.equalsIgnoreCase(b));
        System.out.println("Upper strings equal: "
                + a.toUpperCase(Locale.ROOT)
                        .equals(b.toUpperCase(Locale.ROOT)));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("Raw ignore case composed: "
                + composed.equalsIgnoreCase(decomposed));

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC exact equal: "
                + nfcA.equals(nfcB));
    }
}
```

```bash
javac -encoding UTF-8 ComparisonStrategiesDemo.java
java ComparisonStrategiesDemo
```

Stdout:

```text
equalsIgnoreCase: false
Upper strings equal: true
Raw ignore case composed: false
NFC exact equal: true
```

**Do not use the line "Upper strings equal: true" as an excuse to normalize every identifier via uppercasing.** It proves **one specific example pair** can match via uppercasing, not that uppercasing is full case folding or an identity policy suitable for all scripts.

`Normalizer` handles canonical/compatibility Unicode equivalence yet **does not change case**. For Unicode identifiers used across multiple services and languages, design a specific profile (such as one defined by Unicode/UTS #39 or provided by a library), control the Unicode version, handle collisions, and integrate with database collation.

## 13. Collator is for linguistic comparison, not a substitute for identity rules

`java.text.Collator` provides text comparison by **Locale**. Depending on strength, results can be sensitive or insensitive to diacritics and case:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("fr-FR"));
collator.setStrength(Collator.PRIMARY);
int comparison = collator.compare(left, right);
```

This is a **fragment**, requiring declared variables `left` and `right`. `Collator.PRIMARY` typically prioritizes base letters over accent/case distinctions, though exact behavior depends on locale/provider rules. Do not claim all accented letters equal unaccented letters across all locales.

**When to use Collator?** When **sorting lists or searching text** according to the user's linguistic conventions. For instance, ordering personal names or product names naturally for readers. For identifier keys used in caches, database `UNIQUE` constraints, or APIs, using Collator comparison with the default locale can cause behavior shifts across environments, Unicode/CLDR versions, or JDK upgrades.

When linguistic text comparison is needed, use the **Locale chosen for that operation**, not an arbitrary server locale. Someone may sort Vietnamese names differently from English rules, yet order codes must maintain a language-independent machine-readable policy.

## 14. Design data field contracts before writing utilities

A design-level policy table might include:

| Field | Store original? | Comparison/lookup rule | Locale used | Risks to check |
| --- | --- | --- | --- | --- |
| `displayName` | Yes | Separate search index if needed | Locale for UI/search | Losing name spelling, mixing up diacritics |
| ASCII `username` | Can keep display | Lowercase ASCII key after validation | `Locale.ROOT` | Collisions during registration/migration |
| `password` | Never store plaintext | Verify per password-hashing protocol | Do not arbitrarily use locale | Loss of input exactness |
| `accessToken` | Per protocol/secure storage | Exact matching | None | Rejecting valid tokens or accepting wrong ones |
| `currencyCode` | Store canonical | ASCII uppercase + valid code | `Locale.ROOT` for casing | Unregistered codes, currency mix-up |
| `localeTag` | Store BCP 47 | Parse/serialize via `Locale` | BCP 47 APIs | Malformed tags, unsupported locales |
| `email` | Should keep verified input | Verify mailbox/provider policy | Do not lowercase whole address | Mailbox confusion |
| `orderId` | Per schema | Exact or system-defined alias | Usually none | ID collisions, breaking signatures/URLs |
| `searchQuery` | Can keep query | Collation/index/search policy | Search locale | Linguistically inappropriate results |
| `filePath` | Per filesystem | OS/filesystem-specific | Do not infer from locale | File not found |
| `resourceKey` | Exact spelling | Exact match per resource system | Do not alter automatically | Missing key |

The contract must also answer: **how null/empty/whitespace are handled, which characters are permitted, whether NFC/NFKC normalization is used, whether comparison uses string matching or DB collation, which Unicode version, which API version, and which error to return on conflicts**.

Not every field needs its own separate policy table in code. However, groups with different semantics **must not be forced into a single generic `normalize(String)`** that just runs `trim().toLowerCase()`.

## 15. Small service example: each field has its own policy

Instead of creating a `normalizeAllFields` function, define operations by purpose. The example below has explicit policies:

- `displayName`: preserve casing; apply NFC at input only when the application contract permits.
- `username`: ASCII-only and canonical lowercase `Locale.ROOT`.
- `currencyCode`: ASCII, uppercase, and validated against real currency codes.
- `orderId`: preserve verbatim if schema defines it as case-sensitive.
- `secret`: **unmodified**, and never print sensitive contents.

**File `FieldSpecificPolicyDemo.java`:**

```java
import java.text.Normalizer;
import java.util.Currency;
import java.util.Locale;

public class FieldSpecificPolicyDemo {
    static String displayName(String text) {
        return Normalizer.normalize(text, Normalizer.Form.NFC);
    }

    static String usernameKey(String input) {
        if (!input.matches("[A-Za-z][A-Za-z0-9_]{2,15}")) {
            throw new IllegalArgumentException("Bad username");
        }
        return input.toLowerCase(Locale.ROOT);
    }

    static String currencyCode(String input) {
        if (!input.matches("[A-Za-z]{3}")) {
            throw new IllegalArgumentException("Bad currency code");
        }
        return Currency.getInstance(
                input.toUpperCase(Locale.ROOT))
                .getCurrencyCode();
    }

    static String orderId(String input) {
        return input;
    }

    static String secretUnmodified(String input) {
        return input;
    }

    public static void main(String[] args) {
        System.out.println("Display: " + displayName("Đặng"));
        System.out.println("Username: "
                + usernameKey("LAN_01"));
        System.out.println("Currency: "
                + currencyCode("vnd"));
        System.out.println("Order ID: "
                + orderId("Ab-07"));

        String providedSecret = "SeCrEt!";
        System.out.println("Secret unchanged: "
                + secretUnmodified(providedSecret)
                        .equals(providedSecret));
    }
}
```

```bash
javac -encoding UTF-8 FieldSpecificPolicyDemo.java
java FieldSpecificPolicyDemo
```

Stdout on Java 17+ with a UTF-8 console:

```text
Display: Đặng
Username: lan_01
Currency: VND
Order ID: Ab-07
Secret unchanged: true
```

This is a **policy-teaching model**, not a complete authentication service. For secret data in real products, never store/log plaintext; apply password hashing or secret management in the right context. Similarly, `Normalizer.normalize` throws on null input; the methods above have a **non-null** input contract requiring validation at API boundaries.

**Why not call `displayName(...).toLowerCase(ROOT)`?** Because original capitalization carries display meaning. **Why not lowercase `orderId`?** Because this example assumes order IDs are case-sensitive; change only if that code's schema specifies otherwise. **Why not lowercase `secret`?** Because it is data that must be preserved verbatim per protocol. The same Java `String` type with different business roles leads to different policies.

## 16. Databases, indices, and systems do not share one single rule

Policies in Java do not automatically guarantee that databases, caches, or external systems compare strings identically. A database using a **case-insensitive collation** may consider two strings equal, while `String.equals` does not. Another database may distinguish accents or use a different Unicode version. Therefore:

1. Define the **canonical key rule** for identity fields.
2. Create a **lookup key column** with the policy enforced at write boundaries, if needed.
3. Place a **unique constraint** consistently with the policy; review collation and index length.
4. Check for collisions when changing policies or upgrading Unicode/libraries/DBs.
5. Use the same key across register/login/find/update/cache, rather than duplicating normalization via different functions.
6. Preserve the **display original** when required; do not turn canonical keys into user-facing name text.

For example, legacy records `Lan_01` and `LAN_01` representing two distinct accounts cannot simply be merged after converting to `lan_01`. A verified migration, collision-resolution decisions, and auditing are required, rather than running an SQL `LOWER(username)` and calling it done.

**Limits of case mapping:** `toLowerCase(Locale.ROOT)` in JDK 17 and `LOWER(...)` in a database do not necessarily rely on the same Unicode version or collation rules. If an identity policy must remain stable long-term, define an explicit profile and store its version when needed; test across all runtimes/DBs the product supports.

## 17. APIs, JSON, and versioning: do not silently change field semantics

Suppose an API documents `"username"` as case-insensitive while `"orderId"` is case-sensitive. If a backend upgrade lowercases both without updating the contract, clients can hit failures:

- Old links or cache keys fail to look up order IDs.
- Two previously distinct values collide into duplicates.
- Payload digital signatures fail verification because bytes changed.
- Users see display names lose their entered capitalization.
- Search filters behave differently between mobile apps and web.

Therefore, a **contract** must define each field's case policy; changing the policy can be a **breaking change** rather than a minor formatting tweak.

Specifically for JSON:

- **Property names** like `userId` and `userID` are meaningful to schemas and parsers; do not blindly lowercase all keys.
- **String values** carry semantics defined by the field itself; JSON does not impose case-insensitivity on its own.
- For signed/hashed/canonical JSON fields, any case conversion must follow the signing profile and happen in the exact specified order.
- Use the framework's standard serializer/parser; do not manually concatenate JSON or run `replaceAll` regexes to force lowercase on raw payloads.

**Locale tags** are the opposite example: data with an international syntax and standard API. Use `Locale.forLanguageTag(...)` or `Locale.Builder` to parse, and `toLanguageTag()` to serialize. Do not blindly lowercase `en-US` into `en-us` and treat that as the canonical stored representation (language and region have their own casing conventions).

## 18. QA: test by data category, not only ASCII

A test suite should cover the following groups:

| Field | Inputs to test | What to verify |
| --- | --- | --- |
| ASCII Username | `Lan_01`, `LAN_01` | Both inputs share a key if the product is case-insensitive |
| Unicode Username | `Lăn_01` | Rejected **per published ASCII policy**, not assuming all usernames must be ASCII |
| Locale-sensitive casing | `TITLE` in ROOT and tr-TR | Server default does not alter keys |
| Case expansion | `ß`, `İ` | String after case mapping can change length |
| Display name | `Đặng`, `McDonald` | Capitalization preserved |
| Names with Unicode decomposition | `é` and `e` + U+0301 | NFC canonical equivalence if contract permits |
| Email | `Sales@example.com`, `sales@example.com` | Local part not merged by default |
| Token/secret | Strings differing only by case | Unchanged and not compared ignore-case outside protocol |
| Currency code | `usd`, `USD`, `u$d` | ASCII uppercase rule + existing code validation |
| Locale tag | `EN-us`, `zh-hant-tw` | Parsed/serialized via BCP 47 APIs |
| File path | `Report.csv`, `report.csv` | Do not assume all filesystems behave identically |
| JSON property | `userId`, `userid` | Parser/schema handles exact field names |
| DB collision | Two existing differently cased keys | Migration detects duplicates when changing policy |
| Cache/index | Same identity with case variants | Uses a single policy-compliant key |
| Unicode confusable | Visually similar Latin/Cyrillic letters | Do not treat case conversion as sufficient security |

**Testing default locale changes:** run critical technical tests in JVMs started with different locales, e.g. English and Turkish, to prove canonical keys do not depend on `Locale.getDefault()`. Do not continuously flip the JVM default across concurrently running tests.

**Post-upgrade testing:** if upgrading the JDK, database collation, or Unicode libraries, rerun equivalence, uniqueness, and login tests. A long-lived identity policy requires higher stability than ordinary UI utilities.

## 19. Common mistakes to avoid

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Lowercasing every `String` on save | Loses name spelling, breaks tokens/case-sensitive IDs | Define per field |
| Using parameterless `toLowerCase()` for keys | Depends on default locale, Turkish I bug | Use environment-independent policy for keys |
| Thinking `Locale.ROOT` is full Unicode case folding | Does not cover all Unicode equivalences | Choose case-fold/normalization profile if needed |
| Using `equalsIgnoreCase` for passwords or access tokens | May accept invalid strings | Exact semantics per protocol |
| Assuming all emails are case-insensitive | Can merge wrong mailboxes | Verify provider and local-part rules |
| Lowercasing entire URLs | Alters meaningful paths/queries | Parse URI, handle each component individually |
| Lowercasing all filenames/paths | Fails to find files on case-sensitive filesystems | Follow platform rules, keep original names |
| Lowercasing JSON field names | Breaks schema | Use exact contract key names |
| Converting all display names to Title Case | Breaks proper names and multilingual rules | Keep original name or format per explicit requirement |
| Making a lowercased column unique without scanning legacy data | Collisions and identity mix-ups | Pre-migration collision audit |
| Trusting DB collation matches Java `String` | May compare differently and lose uniqueness | Integration/JDBC tests, proper schema |
| Applying NFC and thinking case is ignored | Normalizer is not case folding | Separate canonical Unicode and case policies |
| Lowercasing/uppercasing currency codes without validation | May accept nonexistent codes | Use `Currency`/supported-code validation |
| Writing regex over raw JSON payloads | Corrupts data or escape sequences | Parse JSON via schema/typed DTOs |
| Changing policy between register and login | Registration succeeds yet account cannot be found | Share a single versioned canonicalizer |
| Truncating strings after case conversion without checking | Can split code points or violate key length | Validate before and after, clear length units |

## 20. Applied exercises

**Exercise 1 — Field classification.** Given an object with `displayName`, `username`, `password`, `email`, `currencyCode`, `orderId`, and `localeTag`, write a policy for each field: whether to keep original input, what case comparison to use, which locale to pick, whether to use Unicode normalization, and how collisions are handled.

**Exercise 2 — Testing Turkish I.** Use `"TITLE".toLowerCase(Locale.ROOT)` and `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`. Compare code points/`String.equals`. Explain why using the default locale on the backend can break technical keys.

**Exercise 3 — Length changes.** Use `"\u00DF"` and `"\u0130"`. Test `toUpperCase(Locale.ROOT)`/`toLowerCase(Locale.ROOT)` and check UTF-16 lengths before/after. If a key has a 16-character limit, at which step should length be checked?

**Exercise 4 — Collisions.** Given a table where `Lan_01` and `LAN_01` already exist. Switch to lowercase ASCII usernames: identify collisions and design a migration plan without hijacking accounts.

**Exercise 5 — Distinguishing matching strategies.** Compare `"Straße"` with `"STRASSE"` using `equalsIgnoreCase` then ROOT uppercase. Next compare `"\u00E9"` with `"e\u0301"` and NFC. From there explain why a single comparison function cannot serve search, tokens, and identity.

**Exercise 6 — API contract.** Design a JSON schema for `username` (case-insensitive ASCII), `orderId` (case-sensitive), and `localeTag` (BCP 47). Write tests with payloads changing case on each field, documenting which fields are treated as the same value.

## 21. Official documentation

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toLowerCase()`, `toUpperCase(Locale)`, `equalsIgnoreCase`; warnings on default locale/Turkish I.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, `forLanguageTag`, `toLanguageTag`, and language/script/region rules.
- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html): locale-based text comparison and strength.
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD for Unicode normalization, not identical to case folding.
- [Unicode Standard — Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/#G33992): Unicode case mappings/case folding and contextual differences.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/): Unicode security profiles and confusable identifiers.

## 22. Takeaways

**There is no single case policy valid for every `String`.** Display names may need to retain original spelling; usernames are case-insensitive only when the product explicitly specifies a canonical key; passwords, tokens, identifiers, and signatures usually must remain exact; emails must separate the local part from the domain; currency codes and BCP 47 have their own standards; search and sorting need different locale policies from identifier keys.

For **machine-readable ASCII codes** defined by the application itself, `Locale.ROOT` avoids JVM default dependence during case conversion. For **multilingual text**, you must understand case expansion, canonical Unicode normalization, case folding, collation, and data-domain semantics. Design per-field policies, preserve originals when needed, check for collisions, stay consistent across Java/database/API/cache, and test cases beyond ASCII alone.
