# Distinguishing Display Text, Search Keys, and Identifiers in Java

In multilingual applications, the same object can have **display text** (`displayName`), a **search key** (`searchKey`), and an **identifier** (`id`). These three elements are related yet carry different responsibilities. Confusing them causes renames to break links, searches to fail on Unicode characters, case handling to depend on server configuration, or two accounts with similar names to merge accidentally.

This lesson belongs to the **Uppercase and Lowercase** group of Java Core localization, helping you design these three data layers, choose intentional case transformations, and recognize the limits of `String.toLowerCase`, Unicode normalization, and linguistic comparison tools in Java 17+.

## 1. Three core concepts

| Component | Purpose | Example | Properties |
| --- | --- | --- | --- |
| Display text (`displayName`) | Used in UI, emails, profiles | `Éclair Café` | Mutable; must preserve user-permitted spelling |
| Search key (`searchKey`) | Improves matching capability | `éclair café` | Derived per policy, regenerable |
| Identifier (`id`) | Uniquely identifies entity, foreign keys, permissions | UUID `11111111-1111-4111-8111-111111111111` | Stable, independent of locale and name spelling |

Example record:

~~~text
id:          11111111-1111-4111-8111-111111111111
displayName: Éclair Café
searchKey:   éclair café
~~~

If the user renames to `Cafe Nouveau`, the system updates `displayName` and recomputes `searchKey`, while **keeping `id` unchanged**. An order, post, friend relationship, or access permission does not become a different entity just because its name changed.

**Principle:** a name is a mutable attribute; a search key is a retrieval tool; an ID is a technical identity. Never use any accent-stripped or case-converted string as a default ID.

## 2. Why must display text preserve exact spelling?

Personal names, brands, and natural text contain diacritics, mixed case, multiple scripts, combining characters, and spelling choices decided by users or editors:

~~~text
Đặng Thị Mai
İstanbul
Éclair Café
Αλέξανδρος
李明
~~~

Saving them directly as lowercase or uppercase can alter the spelling the user intended. Therefore:

- Store `displayName` per input contract, optionally applying Unicode normalization if there is an **explicit policy**.
- Do not overwrite original content merely because search indexing needs a lowercased key.
- If the UI wants uppercase formatting, do it **only in the presentation layer** and in the appropriate language; do not turn presentation formatting into an identity change.
- Handle HTML escaping, SQL parameterization, validation, control characters, and security requirements separately; normalization/casing does not replace those steps.

In some cases, applications must keep the exact original for auditing, signatures, legal names, or user-authored content. Unicode normalization must also be evaluated at the right data boundary rather than silently altering all text without notice.

## 3. Case conversion in Java depends on Locale

Zero-argument `String.toLowerCase()` and `String.toUpperCase()` use the **JVM's default locale**. That is a source of bugs if used to build stable machine keys:

~~~java
String code = "TITLE";
String unsafe = code.toLowerCase(); // depends on Locale.getDefault()
String stableExample = code.toLowerCase(Locale.ROOT);
~~~

This is an illustrative snippet requiring `import java.util.Locale;`.

Under a Turkish locale, `I` can be lowercased to `ı` (dotless i), differing from `i` in many English contexts.

~~~text
"TITLE".toLowerCase(Locale.ROOT)  → "title"
"TITLE".toLowerCase(tr-TR)        → "tıtle"
~~~

Turkish conversion has pairs that must be distinguished:

| Character | Unicode | Role |
| --- | --- | --- |
| `I` | U+0049 | Uppercase of `ı` in Turkish |
| `ı` | U+0131 | Dotless lowercase i |
| `İ` | U+0130 | Dotted uppercase I |
| `i` | U+0069 | Dotted lowercase i |

**From this follow two different decisions:**

1. For **Turkish natural text**, consider case-mapping rules matching the content's language.
2. For **language-independent protocol keys**, choose an explicit policy (typically deterministic ASCII syntax or `Locale.ROOT` handling when appropriate), instead of relying on the server's default locale.

There is no rule that "`Locale.ROOT` is right for every type of data". In Unicode search and identifiers, it is a tool, not a complete contract.

### One character can turn into multiple characters

Java `String.toUpperCase(Locale)` can change string length, for example in German:

~~~java
"straße".toUpperCase(Locale.GERMAN); // "STRASSE" in the tested JDK
~~~

If source code assumes case conversion is always 1:1 per `char`, it can mishandle length, offsets, or data constraints. Do not allocate a fixed buffer of size `original.length()` assuming the uppercased result always keeps the old length.

## 4. Locale.ROOT is not Unicode full case folding

An interesting comparison:

~~~java
"straße".toLowerCase(Locale.ROOT); // "straße"
"STRASSE".toLowerCase(Locale.ROOT); // "strasse"
~~~

These two strings are **not equal** under `String.equals`, even though `straße` when uppercased can become `STRASSE`.

Therefore, separate:

- **Case conversion:** converting uppercase to lowercase, or vice versa, for presentation/processing purposes.
- **Case folding:** a Unicode algorithm for a case-insensitive matching policy; has different application modes and variants.
- **Case-insensitive comparison:** comparing per requirements of a data field or language.
- **Collation:** comparing and sorting strings per linguistic rules.

`toLowerCase(Locale.ROOT)` does not automatically perform every full case folding mapping. `String.equalsIgnoreCase` is not a complete locale-aware comparison solution either; Java documentation recommends `Collator` for linguistically sensitive comparison problems.

Do not take the output of a single lowercasing step and declare all multilingual usernames/search safely canonicalized.

## 5. Unicode normalization is an independent layer from casing

Two strings can both display `é` while containing different code points:

~~~text
U+00E9            → é (precomposed form)
U+0065 U+0301     → e + combining acute accent
~~~

Unnormalized `String.equals` treats them as different. `Normalizer.normalize(text, Normalizer.Form.NFC)` can bring canonically equivalent representations to a consistent form.

An **illustrative** search pipeline could be:

~~~text
displayName
   ↓ NFC
canonical string
   ↓ toLowerCase(Locale.ROOT)
lowercased string
   ↓ NFC again
searchKey
~~~

The second NFC pass is helpful because case mapping can produce strings with combining marks. However, the pipeline above **does not strip diacritics** and is not a full casefolder/search engine for all languages. It must be designed for the set of languages the product supports.

Do not confuse:

- **UTF-8/UTF-16**: encoding of bytes or UTF-16 code units.
- **NFC/NFD**: Unicode canonical equivalence normalization.
- **NFKC/NFKD**: normalization adding compatibility equivalence, which can lose formatting distinctions.
- **Case conversion**: converting uppercase/lowercase.
- **Translation/transcription/transliteration**: other linguistic tasks.

### Accent-insensitive search is a separate requirement

Vietnamese users may want to find `"Đặng"` by searching `"Dang"`. NFC or lowercasing does not automatically turn `đ` into `d`, and stripping diacritics from NFD is often insufficient for every character too. If you generate an accent-stripped alias, that is **lossy search data**, and the display source must be preserved.

For example, `ma`, `má`, `mà`, `mạ`, `mã`, `mả` can all collapse to the same alias `ma` when stripped. This may be acceptable for **returning multiple search candidates**, but cannot be used to conclude they are the same person or to grant login access.

## 6. Generating searchKey: policy, source, and versioning

A search key is **data derived from a source**. It should maintain these invariants:

- Same input and same policy version yield identical output.
- Every ingestion path (UI, API, import, batch) applies the same policy.
- Queries and indexed data are processed compatibly.
- When `displayName` changes, `searchKey` is regenerated.
- If the policy or Unicode data is upgraded, the **index can be rebuilt** from the source.
- Entities sharing the same `searchKey` can still have two distinct IDs.

An easy-to-understand structure:

~~~text
id:                stable UUID
displayName:       "Đặng Thị Mai"
searchKeyExact:    NFC + chosen case policy
searchIndexLoose:  alias for accent-insensitive search (if needed)
~~~

This is **one model**, not a requirement that every system maintain three index types. Name search, full-text search, autocomplete/suggestions, fuzzy matching, or multilingual search may require dedicated analyzers and libraries.

### Do not expose searchKey as an arbitrarily editable field

In many APIs, the client only needs to send `displayName`. The backend must compute `searchKey` per policy rather than trusting a client-supplied `searchKey` that could be spoofed or inconsistent. If search indexing is asynchronous, the product should define acceptable lag; **ID must never depend on whether the index has updated yet**.

### Policy changes can create collisions

If policy v1 uses only NFC and v2 adds accent-stripping/case-folding, previously distinct strings may yield the same `searchKey`. The search index must tolerate multiple hits or apply ranking; never merge entities automatically. When improving search, version the policy, rebuild data, compare collisions, and test migrations.

## 7. IDs and usernames are two distinct problems

A stable identifier can be:

- An integer ID assigned by the database.
- A UUID (in Java, `java.util.UUID`, e.g., `UUID.randomUUID()`).
- An immutable business key issued by an authoritative system.

Unlike `displayName`, an ID does not need to rely on language. In a system where multiple people share a name, two people still have **two distinct IDs**. If a name changes, the ID and all foreign keys, relationships, and logs must remain intact.

### URL slugs are not IDs by default

A friendly URL may include a slug `san-pham-mua-he` generated from the name `Sản phẩm mùa hè`. However, a slug can change when the name changes and can collide when two items have similar names. Slugs must be managed as aliases/routes with uniqueness and redirect policies if exposed externally. A design can include both an immutable ID and a display slug in the URL, yet a slug does not automatically replace a primary key.

### Usernames require a dedicated canonical policy

`username` may be a login name remembered by users, yet it has stricter **uniqueness and security** requirements than `searchKey`:

- Is Unicode allowed or ASCII only?
- Preserve case sensitivity or compare case-insensitively?
- If Unicode is supported, which NFC/NFKC, casefold, and profile are used?
- Must confusables, invisible characters, or mixed scripts be blocked?
- Is length limited by Unicode characters, UTF-16, bytes, or graphemes?
- Are there reserved names and a rename policy?
- When a username changes, is an alias retained or the old login locked?

A model might include:

~~~text
userId:             UUID, immutable
displayName:        Text seen by the user
usernameDisplay:    Displayed login username
usernameCanonical:  Representation accepted by the identity policy
searchKey:          Name lookup key, may collide with others
~~~

Not every application needs all of these fields, yet **never use a lossy `searchKey` function as a canonical username without an explicit specification**.

### Uniqueness must be enforced at the database level

Running a `SELECT` to check if a username exists before `INSERT` does not prevent race conditions. Two requests can both pass the check and create the same canonical key. You need a policy-aligned unique constraint/index in the storage layer and controlled conflict handling.

When changing a username's canonical policy, if two old names now collapse onto one key, **do not automatically merge accounts**. Plan collision detection/resolution while preserving ownership and history.

## 8. Complete Java 17+ example: three data layers

The program below uses a fixed UUID for easy testing; it demonstrates preserving `displayName`, matching search when Unicode uses combining marks, keeping `id` unchanged on rename, and showing the limits of locale casing.

Create **`DisplaySearchIdDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.UUID;

public class DisplaySearchIdDemo {
    record Profile(UUID id, String displayName, String searchKey) {}

    static String makeSearchKey(String displayName) {
        String canonical = Normalizer.normalize(
                displayName, Normalizer.Form.NFC);
        String lowered = canonical.toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lowered, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        UUID id = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");

        String displayed = "\u00c9clair Caf\u00e9";
        Profile first = new Profile(
                id, displayed, makeSearchKey(displayed));

        String query = "E\u0301CLAIR CAFE\u0301";
        System.out.println("Display preserved: "
                + first.displayName().equals(displayed));
        System.out.println("Search match: "
                + first.searchKey().equals(makeSearchKey(query)));

        Profile renamed = new Profile(
                first.id(), "Cafe Nouveau",
                makeSearchKey("Cafe Nouveau"));

        System.out.println("ID stable after rename: "
                + first.id().equals(renamed.id()));
        System.out.println("Search key changed: "
                + !first.searchKey().equals(renamed.searchKey()));

        String title = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");
        System.out.println("Turkish differs from ROOT: "
                + !title.toLowerCase(turkish)
                        .equals(title.toLowerCase(Locale.ROOT)));
        System.out.println("ROOT is title: "
                + title.toLowerCase(Locale.ROOT).equals("title"));

        System.out.println("German lowercase equals: "
                + "\u00dftest".toLowerCase(Locale.ROOT)
                        .equals("SSTEST".toLowerCase(Locale.ROOT)));
        System.out.println("German uppercase same: "
                + "stra\u00dfe".toUpperCase(Locale.GERMAN)
                        .equals("STRASSE"));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 DisplaySearchIdDemo.java
java DisplaySearchIdDemo
~~~

Verified stdout:

~~~text
Display preserved: true
Search match: true
ID stable after rename: true
Search key changed: true
Turkish differs from ROOT: true
ROOT is title: true
German lowercase equals: false
German uppercase same: true
~~~

**Explaining the output:**

1. `Display preserved: true` — display text was not silently lowercased when generating `searchKey`.
2. `Search match: true` — the query uses `E + U+0301` and uppercase, whereas `displayName` has precomposed `É`; NFC + lowercasing applied on both sides makes them match in this test case.
3. `ID stable after rename: true` — the profile's UUID does not change when name and `searchKey` change.
4. `Search key changed: true` — the index must update alongside the name change.
5. `Turkish differs from ROOT: true` — letter `I` rules differ between Turkish and ROOT.
6. `ROOT is title: true` — in this English key example, `Locale.ROOT` avoids JVM locale dependence.
7. `German lowercase equals: false` — `String.toLowerCase(Locale.ROOT)` is not full Unicode case folding.
8. `German uppercase same: true` — case mapping can turn one character into multiple characters, such as ß into SS.

`Profile` is an illustrative Java 17 record, **not a production login system**. It lacks null validation, length limits, uniqueness, authentication, a security profile, and a versioning policy. `makeSearchKey` is only appropriate as an example or tested starting point within a specific scope.

## 9. Linguistic comparison and search are not synonymous

`java.text.Collator` can compare/sort strings per locale. Example:

~~~java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

int order = collator.compare(leftDisplayText, rightDisplayText);
~~~

This is an **illustrative snippet**, requiring imports for `java.text.Collator`, `java.util.Locale`, and two declared input `String`s. Choosing `strength`/`decomposition` per requirements affects how case, diacritics, and other differences are evaluated.

However, **`Collator` is for linguistic comparison**; do not use `collator.compare(a,b)==0` by default to decide whether two usernames or two accounts are the same person. Identity relationships require a dedicated identity policy.

If a product needs advanced multilingual search, ICU4J or a search engine with appropriate analyzers and Unicode/locale rules may be required. Pick tools by requirements rather than assuming a single `toLowerCase` solves everything.

## 10. Unicode security and visually similar characters

Characters from two scripts can look alike without being canonically equivalent. For instance, a Latin `a` and a visually similar Cyrillic letter are not necessarily merged by NFC. Unicode normalization and lowercasing do not automatically eliminate all **confusables/homoglyph attacks**.

For usernames, domains, human-entered identifiers, or permission-affecting fields:

- Specify allowed character sets, scripts, and normalization/case-folding.
- Check for control characters or invisible characters per the field type's standard.
- Apply an appropriate identifier security profile rather than trusting that `NFC + Locale.ROOT` is always safe.
- Do not use "fuzzy" search hits or accent-stripped aliases to grant permissions.
- Base access relationships on immutable IDs and approved canonical username policies.
- Render text with escaping; parameterize SQL queries; normalization does not replace injection prevention.

Two people having the same `displayName` can be completely valid. Problems arise when a system uses a **non-unique `searchKey`** in place of identity. Return multiple search results and disambiguate with permitted public metadata instead of assuming two records are one.

## 11. Database and API design

A conceptual SQL schema:

~~~sql
CREATE TABLE customer_profile (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(256) NOT NULL,
    search_key VARCHAR(512) NOT NULL
);

CREATE INDEX idx_customer_search
    ON customer_profile(search_key);
~~~

This is conceptual SQL; databases can differ in native UUID types, collation behavior, string lengths, and index types. **Do not put a `UNIQUE` constraint on `search_key`** if users can share names. If there is a `username_canonical`, place a separate unique constraint on that column per verified policy and collation.

APIs returning data to clients usually only need:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "displayName": "Éclair Café"
}
~~~

`searchKey` is server-side index data; it does not have to be a user-editable field. Within the same name-update transaction, you can update the index synchronously or emit an event for asynchronous indexing with idempotence and clear latency expectations. Regardless of indexing approach, the ID must remain the source of entity identity.

### When changing search policy versions

A safe roadmap is:

1. Version and clearly define the current indexing pipeline.
2. Build the new policy and test each locale, especially Turkish I, German ß, and accented Vietnamese.
3. Compare collisions and recall, avoiding accidental changes to ownership or uniqueness.
4. Rebuild the new index from stored `displayName`, potentially running in parallel before switching traffic.
5. Switch the query pipeline in sync with the new index.
6. Keep IDs and foreign keys intact; do not treat search migration as identity migration.

If Unicode/JDK data or search libraries are upgraded, check case mappings and index behavior that could shift on edge characters.

## 12. Common pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Lowercasing and overwriting personal names | Loses display spelling | Keep `displayName`; create separate `searchKey` |
| Using locale-less `toLowerCase()` for machine keys | Depends on JVM locale, e.g. Turkish I | Deterministic machine policy; `Locale.ROOT` if appropriate |
| Treating `Locale.ROOT` as full casefold | Fails on complex Unicode mappings | Use an appropriate algorithm/profile |
| Using `displayName` as a foreign key | Renaming breaks links | Use immutable ID |
| Building IDs via accent-stripping/lowercasing | Distinct names become same ID | Issue IDs independently |
| Using slug as primary key without alias management | Slug collisions or broken links on rename | ID and slug are separate responsibilities |
| Normalizing only data side, not query side | Misses matches when combining marks differ | Process both sides compatibly |
| Arbitrarily using NFKC instead of NFC | Loses some character distinctions | Define per field |
| Merging results with the same `searchKey` | Confuses people/entities | `searchKey` can collide; return multiple candidates |
| Using accent-stripped `searchKey` as canonical username | Collisions and permission risks | Separate username policy |
| Checking duplicate username only before insert | Race condition | DB unique constraint |
| Using `equalsIgnoreCase` as multilingual collation | Wrong in some languages | Appropriate `Collator`/engine |
| Believing lowercase removes all homoglyphs | Vulnerable to Unicode spoofing | Dedicated identifier security profile |
| Not rebuilding index after policy change | Inconsistent search results | Versioned migration |
| Converting case then assuming unchanged length | Broken constraints/offsets | Test 1:n mappings |
| Using client locale to alter ID | ID depends on request | Locale-independent ID/canonical contract |

## 13. Testing checklist

- **Unicode:** precomposed `Éclair` vs `E + combining acute`; raw values differ, NFC search keys match.
- **Turkish casing:** `TITLE` in `tr-TR` and `Locale.ROOT` yield different lowercased outputs.
- **German casing:** `straße` and `STRASSE` show simple lowercasing is insufficient for full case folding.
- **Vietnamese:** `Ma`, `Má`, `Mà` are not merged by NFC; accent-free aliases are for search only if product needs them.
- **Identity:** changing `displayName` once or multiple times does not change `id`.
- **Search:** multiple entities sharing a `searchKey` remain distinct; search returns a list of results.
- **Uniqueness:** two concurrent requests registering the same canonical username are enforced by the DB.
- **Security:** check confusables, invisible characters, long inputs, or invalid Unicode per profile.
- **Persistence:** DB collation and Java `String.equals` may differ; do not infer uniqueness from isolated Java tests.
- **Migration:** changing search rules does not alter foreign keys and allows index rebuilding.
- **Defaults:** different JVM/host locales do not alter machine codes defined under fixed policies.
- **Presentation:** UI case formatting does not overwrite source text.

An important property-based test: for any record with a given ID, changing `displayName` and regenerating `searchKey` **does not alter ID referential relationships**.

## 14. Self-check questions

**Question 1.** Why not use `displayName.toLowerCase()` as a primary key?

**Answer:** Names can change and collide; parameterless lowercasing depends on the default locale. An ID must be immutable and unique within the system.

**Question 2.** Does `Locale.ROOT` solve every Unicode case-insensitive comparison problem?

**Answer:** No. It avoids the default locale for case conversion, yet is neither full case folding nor a substitute for collation or normalization.

**Question 3.** Two people named "Má" and "Mà" share the search key "ma" if accents are stripped. Are they the same account?

**Answer:** No. Search keys lose information; IDs and canonical username policies must remain independent.

**Question 4.** After renaming, which fields should change?

**Answer:** `displayName` changes per user input; `searchKey` is recomputed; `id` stays unchanged.

**Question 5.** When supporting case-insensitive Unicode usernames, is `toLowerCase(Locale.ROOT)` alone sufficient?

**Answer:** Not yet. You need policies for character sets, Unicode normalization/casefold, confusables, and atomic uniqueness, tested across supported languages.

**Practical exercise:** Extend `DisplaySearchIdDemo` with a repository storing two people with the same `displayName` but different UUIDs; querying by `searchKey` must return multiple results, while `findById` returns exactly one object. Add an accent-free alias strictly for search. Then separately design a `usernameCanonical` with a uniqueness policy and test that renaming preserves ownership.

## 15. Official documentation

- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toUpperCase(Locale)`, and `equalsIgnoreCase`, Turkish/German examples.
- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFKC and Unicode normalization.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`.
- [UUID — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): UUID keys.
- [Collator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): linguistic string comparison/sorting.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): Unicode normalization.
- [Unicode Case Folding](https://www.unicode.org/Public/UCD/latest/ucd/CaseFolding.txt): case-folding data distinct from case conversion.
- [Unicode Technical Standard #39](https://unicode.org/reports/tr39/): Unicode security/confusables.

**Conclusion:** **Display text is for humans; searchKey serves retrieval; ID is durable identity.** Case conversion must match the locale and data role. NFC, case folding, accent stripping, collation, and identifier rule sets are distinct concepts. Store display names per field policy, build regenerable search keys, and keep IDs independent so the system remains safe during renames and multilingual expansion.
