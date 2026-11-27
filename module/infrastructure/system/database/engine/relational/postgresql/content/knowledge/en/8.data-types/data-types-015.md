# Character Encoding, Collation, and Their Impact on Comparisons in PostgreSQL

## 1. Why Storing Vietnamese Correctly Is Not Enough for Accurate Comparisons

Suppose a PostgreSQL application manages customers with the following names:

- `Anh`
- `anh`
- `Ánh`
- `Bình`
- `Bình` — may look like "Bình" visually, yet is represented by a different sequence of Unicode code points

Users may expect "Anh" and "anh" to match during a case-insensitive search, or expect "Bình" to sort in natural Vietnamese alphabetical order rather than raw byte order. Meanwhile, a system checking for duplicate customer codes may want **exact character-by-character distinction**, refusing to treat visually similar strings as identical.

Two distinct concerns are involved:

1. **Character encoding**: which bytes are used to represent text for storage and network transmission?
2. **Collation**: which rules does PostgreSQL apply to compare, sort, and in some cases decide whether two strings are equal?

There is also **Unicode normalization**: whether different Unicode code point sequences that render identically are normalized into a single canonical form.

Three concepts must be clearly separated:

| Question | Domain | Example |
| --- | --- | --- |
| Which byte sequence represents the character `ế`? | Encoding | UTF-8 encodes `ế` across multiple bytes |
| Does `Anh` come before or after `Ánh`? | Collation | Depends on sorting rules |
| Are `Anh` and `anh` considered equal? | Collation and comparison rules | Depends on collation type / search design |
| Does precomposed `é` equal `e` + acute accent? | Unicode normalization and collation | Two code point sequences can look identical |
| How many "characters" count toward a `varchar(20)` limit? | PostgreSQL character representation | Normally counts characters, not bytes |

**Key takeaway:** having a UTF-8 database is a solid foundation for storing Vietnamese text, but it **does not automatically imply** case-insensitive search, accent-insensitive search, or natural language sorting.

## 2. What Is Encoding?

Computers store data as bytes. To store text strings, a mapping rule from **characters** to bytes and back is required. That rule is a *character encoding*.

In the Unicode ecosystem, **UTF-8** is widespread: basic ASCII characters typically occupy one byte; many Vietnamese characters require multiple bytes. Characters can also be composed from multiple Unicode code points, and UTF-8 encodes each code point into its corresponding bytes.

Example:

```sql
SELECT
    char_length('Tiếng Việt') AS characters,
    octet_length('Tiếng Việt') AS bytes,
    encode(convert_to('Tiếng Việt', 'UTF8'), 'hex') AS utf8_hex;
```

For a string written in standard precomposed Unicode form, `char_length('Tiếng Việt')` is **10 characters**, while the UTF-8 byte count is larger because accented characters occupy multiple bytes.

Functions:

- `char_length(text)` or `length(text)`: number of characters in the string according to PostgreSQL's encoding handling.
- `octet_length(text)`: number of **bytes** representing the string.
- `convert_to(text, 'UTF8')`: converts a string into `bytea` in the requested encoding.
- `encode(bytea, 'hex')`: displays `bytea` data as a hex string.

Do not confuse `char_length` with byte count, and do not assume PostgreSQL's character count always matches the number of visual characters a user perceives on screen. A single *grapheme cluster* can span multiple code points, such as a base letter plus combining marks or multi-part emoji.

### 2.1. How Does UTF-8 Represent Vietnamese?

UTF-8 is a variable-length encoding. Examples of character code points:

```text
'A'     -> U+0041 -> 1 byte UTF-8
'é'     -> U+00E9 -> 2 bytes UTF-8
'ế'     -> U+1EBF -> 3 bytes UTF-8
```

PostgreSQL does not need a "separate NVARCHAR column" just to store Vietnamese when the database uses UTF-8. The `text`, `varchar(n)`, and `char(n)` types all store data in the database's encoding.

When designing a new multilingual application, **UTF8** is usually the right choice, though you still must ensure that clients, drivers, import files, and export pipelines all use the right encoding.

### 2.2. Encoding Is Different from Display Fonts

A string may be stored cleanly in UTF-8 yet **display incorrectly** if a terminal lacks Vietnamese fonts or an application has a misconfigured locale. Conversely, if bytes are decoded with the wrong encoding before being written to the database, the text becomes corrupted (*mojibake*) and gets persisted permanently as **corrupted content**.

For instance, if an application reads a UTF-8 file as Windows-1252 and sends the misdecoded string to PostgreSQL, even a UTF-8 database will simply store the garbled text the application sent.

**Never try to fix display corruption by randomly changing collations**; first trace the byte path and encoding at every layer.

## 3. Server Encoding, Client Encoding, and Database Encoding

PostgreSQL distinguishes:

- **Database/server encoding**: how text strings are stored inside a database.
- **Client encoding**: the encoding a connection uses to exchange text with the server.

Check via SQL:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

Example output:

```text
 server_encoding
-----------------
 UTF8

 client_encoding
-----------------
 UTF8
```

If the server and client use different encodings for which PostgreSQL supports transcoding, PostgreSQL/libpq translates on the wire. Not every pair of encodings supports conversion; characters absent from the target character set will raise an error.

### 3.1. Configuring Client Encoding in psql

Inside a `psql` session:

```text
\encoding
\encoding UTF8
```

Or via SQL:

```sql
SET client_encoding TO 'UTF8';

SHOW client_encoding;
```

You can also use the `PGCLIENTENCODING` environment variable in libpq environments to specify the client encoding.

**Note:** setting `client_encoding = UTF8` does not magically fix a file saved in another byte encoding. If a file is actually Latin-1/Windows-1258 while the client claims UTF-8, data may be rejected or mis-encoded. Always verify the **true source encoding** before reading.

### 3.2. Encoding Is Decided at the Database Level

In PostgreSQL, a database is created with a specific encoding tied to the chosen locale and template. In standard PostgreSQL, **you cannot change an existing database's encoding with a simple `ALTER DATABASE ... SET ENCODING` statement**.

Before picking an encoding for a new database, consider:

- Languages that must be stored.
- Database locale/collation.
- Template used to create the database.
- Compatibility rules between encoding and locale.
- Application/driver Unicode handling capabilities.

Example query to inspect the current database:

```sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding_name,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
```

`datcollate` and `datctype` show database locale settings in the catalog for that version. On modern PostgreSQL versions, collation providers and ICU can supply additional locale properties, so do not treat those two columns as the entirety of collation metadata for every database.

### 3.3. A Note on `SQL_ASCII`

`SQL_ASCII` is not a "lighter" UTF-8 option. In an `SQL_ASCII` database, PostgreSQL treats high-bit byte sequences as raw uninterpreted data without validating a character set.

As a consequence, data can accumulate byte sequences that cannot be interpreted consistently when Unicode is needed, making encoding conversion, sorting, and searching unreliable.

For new multilingual applications, prefer **UTF8** unless a very specific compatibility requirement dictates otherwise and its limitations are well understood.

## 4. How Do `text`, `varchar(n)`, and `char(n)` Relate to Encoding?

The three common string types:

| Type | Key Characteristics | Recommended Use |
| --- | --- | --- |
| `text` | Variable-length string with no type-level character limit | General text, names, descriptions |
| `varchar(n)` | String of at most `n` characters per PostgreSQL rules | Fields with an explicit business length cap |
| `char(n)` / `character(n)` | Fixed-length declaration with blank-padding behavior | Only when required for specific format/legacy compatibility |

Example:

```sql
CREATE TABLE text_type_demo (
    title text NOT NULL,
    short_code varchar(12) NOT NULL,
    fixed_code char(4) NOT NULL
);
```

### 4.1. `varchar(n)` Does Not Mean At Most n Bytes

```sql
SELECT
    char_length('Tiếng Việt') AS char_count,
    octet_length('Tiếng Việt') AS byte_count;
```

If you declare `varchar(10)`, the limit counts **characters**, not 10 UTF-8 bytes. A 10-character Vietnamese string with diacritics occupies more than 10 bytes.

This is a classic design bug when migrating from ASCII-only systems to Unicode data. If an external protocol imposes a **byte limit**, enforce a dedicated byte-length check instead of relying solely on `varchar(n)`.

### 4.2. Character Counts Can Differ Even When Strings Look Identical

Two strings:

```sql
SELECT
    char_length(U&'\00E9') AS composed_characters,
    char_length(U&'e\0301') AS decomposed_characters,
    octet_length(U&'\00E9') AS composed_bytes,
    octet_length(U&'e\0301') AS decomposed_bytes;
```

- `U&'\00E9'` is the precomposed character `é` as a single code point.
- `U&'e\0301'` is `e` followed by a combining acute accent.

The two strings can **render virtually identically**, yet differ in character/code-point count and byte length.

Therefore, a `varchar(n)` constraint does not strictly guarantee "at most n human-perceived glyphs" in complex Unicode cases.

### 4.3. `char(n)` and Trailing Spaces

`char(n)` pads values with spaces to the declared width when necessary, and trailing spaces follow special comparison rules. Therefore, do not choose `char(n)` just because a field "usually has n characters."

For personal names, addresses, descriptions, and general Unicode text, `text` or `varchar(n)` is usually simpler. Column type selection is **orthogonal** to collation selection: you can use `text COLLATE ...` or `varchar(n) COLLATE ...` as needed.

## 5. What Is Collation?

A **collation** is a set of rules governing how character strings are sorted and compared. It answers questions like:

- Do accented characters sort near their base letter or elsewhere?
- Does uppercase vs. lowercase affect sort order?
- Are accented variants considered distinct at the comparison level in use?
- Are strings compared by linguistic rules rather than raw byte values?

Examples of differing expectations:

```text
Byte-order sorting:
  code points/bytes are compared under C rules

Linguistic sorting:
  letters and diacritics are tiered per locale rules

Case-insensitive search:
  may want "Anh" and "anh" to match

Identifier validation:
  may require "Anh" to differ from "anh" and "Ánh"
```

**Collation is not encoding.** Two columns both storing UTF-8 with different collations can produce different `ORDER BY` results.

### 5.1. `COLLATE` in SQL

PostgreSQL provides the `COLLATE` clause to request a specific collation where appropriate.

```sql
SELECT word
FROM (
    VALUES
        ('Anh'),
        ('anh'),
        ('Ánh'),
        ('Bình')
) AS t(word)
ORDER BY word COLLATE "C";
```

`"C"` is a standard PostgreSQL collation ordering by byte/code-point order in compatible encodings; it is useful when deterministic machine ordering is desired, **not** for Vietnamese linguistic sorting.

If you omit `COLLATE "C"`, PostgreSQL uses the collation derived from the expression or database default, which can yield a different order.

### 5.2. Collation Can Be Applied at Multiple Levels

A system can specify:

1. **Database default collation.**
2. **Column-level collation.**
3. **Explicit `COLLATE` inside a query or expression.**
4. **Custom collations created via `CREATE COLLATION`.**

Example column with an explicit collation:

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE TABLE encoding_lab.codes (
    code_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_code text COLLATE "C" NOT NULL
);
```

In this table, `raw_code` uses `"C"` collation. Queries can still specify another valid, compatible collation in `ORDER BY`.

Not every combination of text expressions and collations can be mixed freely. When conflicting explicit collations collide in a comparison expression, PostgreSQL raises a collation conflict error instead of guessing which rule you meant.

## 6. Inspecting Current Locale and Collation Configuration

General session/database settings:

```sql
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

`lc_collate` and `lc_ctype` reflect database locale settings; on versions using ICU, inspect the provider and ICU locale configuration as well.

You can list collations installed in the database:

```sql
SELECT
    n.nspname AS schema_name,
    c.collname AS collation_name,
    c.collprovider,
    c.collisdeterministic,
    c.collversion
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE n.nspname IN ('pg_catalog', 'public', 'encoding_lab')
ORDER BY n.nspname, c.collname
LIMIT 80;
```

In modern PostgreSQL:

- `collprovider` distinguishes the collation provider, such as libc or ICU.
- `collisdeterministic` indicates whether the collation is deterministic.
- `collversion` records the collation rule version when supplied by the provider.

System catalog column names and details can vary across versions; for instance, `collisdeterministic` exists in versions supporting nondeterministic collations. When working on older servers, verify against that release's documentation.

Check server version:

```sql
SHOW server_version;
```

### 6.1. Why Can Different Machines Sort Differently?

If two databases use different locales, or even the same locale name with different libc/ICU library versions, they can:

- Sort names differently.
- Place accented letters in different positions.
- Produce different comparison outcomes for collation-sensitive operations.
- Risk mismatches between existing index order and updated collation rules after library upgrades.

Therefore, **never treat a locale name alone as a permanent cross-platform sort contract** if identical ordering across servers/OS versions is required.

## 7. `libc`, `ICU`, and the `"C"` Collation

PostgreSQL supports multiple collation rule sources (*providers*). Common categories:

| Provider | Rule Source | Key Notes |
| --- | --- | --- |
| **libc** | OS C library / system locales | Depends on OS-installed locales and OS library versions |
| **ICU** | International Components for Unicode | Rich Unicode/locale rule support; requires PostgreSQL built with ICU |
| **C / POSIX** | Simple byte-order rules | Fast and predictable for technical codes; not linguistic sorting |

### 7.1. When to Use `"C"`?

Technical code example:

```sql
SELECT code
FROM (
    VALUES ('A-2'), ('A-10'), ('B-1'), ('a-1')
) AS t(code)
ORDER BY code COLLATE "C";
```

Sorting with `"C"` does not understand that "A-2 is numerically smaller than A-10." Nor does it perform linguistic case folding. For machine codes needing stable byte ordering, that predictability is an advantage.

To achieve natural numeric sorting like "A-2, A-10", you may need an ICU collation configured with numeric collation options or split codes into typed fields. Never expect default `ORDER BY code` to parse code structure automatically.

### 7.2. ICU Supports Language-Aware Comparisons

ICU lets you choose locale-specific rules along with options such as comparison strength (*collation strength*).

In general:

- **Primary strength** focuses on base character differences, often ignoring many accent and case differences depending on locale.
- **Secondary strength** typically considers accent differences while ignoring case differences per the applicable rules.
- **Tertiary strength** typically considers case differences as well.

Exact behavior depends on the locale and ICU rules; there is no universal "strip all Vietnamese diacritics" setting valid for every language.

If you need Vietnamese linguistic sorting, select an appropriate collation and **test it against a representative Vietnamese dataset** rather than assuming `"C"` sorts names naturally.

## 8. Deterministic vs. Nondeterministic Collations

This is an important distinction in modern PostgreSQL.

### 8.1. Deterministic Collations

With a **deterministic** collation, even if the provider deems two strings equal at the collation comparison level, PostgreSQL falls back to byte-level comparison as a tie-breaker to make equality deterministic.

Practical consequence: two strings that render identically yet have different UTF-8 bytes are still treated as **unequal**.

Example with `"C"`:

```sql
SELECT
    ('Anh' COLLATE "C" = 'anh' COLLATE "C")
        AS case_sensitive,
    (U&'\00E9' COLLATE "C" = U&'e\0301' COLLATE "C")
        AS representation_sensitive;
```

Both expressions return `false`: uppercase differs from lowercase, and precomposed `é` differs from `e + combining acute` at the byte level.

### 8.2. Nondeterministic Collations

In PostgreSQL builds supporting ICU nondeterministic collations (PostgreSQL 12+ built with ICU), you can define a collation that treats byte-distinct strings as equal when the selected ICU rules consider them equivalent.

Example in our test schema:

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE COLLATION encoding_lab.case_insensitive (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Meaning:

- `provider = icu`: uses ICU rules.
- `locale = 'und-u-ks-level2'`: neutral locale with ICU strength level 2, targeting case-insensitive comparison while still distinguishing many accent differences.
- `deterministic = false`: allows strings with different bytes that compare equal under the collation to evaluate as equal.

Example:

```sql
SELECT
    ('Anh' COLLATE encoding_lab.case_insensitive
      = 'anh' COLLATE encoding_lab.case_insensitive)
        AS same_ignoring_case,
    ('Anh' COLLATE encoding_lab.case_insensitive
      = 'Ánh' COLLATE encoding_lab.case_insensitive)
        AS accented_variant;
```

Under the ICU configuration shown, `same_ignoring_case` is expected to be `true`, while `accented_variant` is typically `false` because accent differences remain significant at secondary strength.

**Do not assume an ICU collation behaves identically across all ICU versions or locales.** This is an illustrative configuration; verify with real data and your PostgreSQL/ICU version.

### 8.3. Collations Ignoring Both Case and Many Accent Differences

Another example, **only when business logic explicitly intends to fold them**:

```sql
CREATE COLLATION encoding_lab.loose_comparison (
    provider = icu,
    locale = 'und-u-ks-level1',
    deterministic = false
);
```

Primary strength generally ignores both case and many accents. For many Latin pairs, `'resume'` and `'résumé'` can compare equal at this strength. However, accent folding must be a deliberate business decision: Vietnamese distinguishes distinct words via diacritics, so "convenient search" is not the same as "identifier uniqueness."

**Never apply an overly loose collation to primary keys, usernames, or legal identifiers without clearly defining what counts as a duplicate.**

### 8.4. Costs and Limitations

Nondeterministic collations can add overhead to certain comparisons and indexes and carry version-dependent limitations in PostgreSQL. Pattern matching operators such as `LIKE`, `ILIKE`, and regular expressions do not have uniform support with nondeterministic collations across all PostgreSQL releases; older versions reject some of these operations.

Do not attach `deterministic = false` to every text column simply for search convenience. First verify which operators, index types, and PostgreSQL version features you need.

## 9. Impact of Collation on `ORDER BY`

### 9.1. Sorting Personal Names

Sample data:

```sql
CREATE TABLE encoding_lab.people (
    person_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL
);

INSERT INTO encoding_lab.people (full_name)
VALUES
    ('Anh'),
    ('anh'),
    ('Ánh'),
    ('Bình'),
    ('Nguyễn'),
    ('Trần'),
    ('Lan');
```

Default sort:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name, person_id;
```

Sort using `"C"`:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE "C", person_id;
```

Sort using the custom ICU collation:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY
    full_name COLLATE encoding_lab.case_insensitive,
    person_id;
```

Row order can differ across these three queries because each applies different comparison rules.

### 9.2. Why Add `person_id` to `ORDER BY`?

Under a collation where `'Anh'` and `'anh'` compare equal, they **tie on the sort key**. Without a secondary tie-breaker, the relative order among tied rows is not guaranteed.

```sql
ORDER BY
    full_name COLLATE encoding_lab.case_insensitive,
    person_id
```

uses `person_id` as a tie-breaker, producing stable ordering for display and pagination.

**Pagination with `LIMIT/OFFSET` or keyset pagination requires deterministic ordering**, not merely sorting by a text column where a collation can treat multiple values as equal.

### 9.3. Collation Cannot Fix Corrupted Vietnamese Encoding

If a table holds mojibake text, `ORDER BY ... COLLATE ...` merely sorts the already-corrupted stored characters; it cannot recover the original names. First identify the encoding bug source and repair the data under a safe backup procedure.

## 10. Impact on `=`, `<>`, `<`, and `>`

String comparison expressions depend on collation.

### 10.1. Deterministic Comparison Under `"C"`

```sql
SELECT
    ('Anh' COLLATE "C" = 'anh' COLLATE "C") AS equal_case,
    ('abc' COLLATE "C" < 'abd' COLLATE "C") AS less_than,
    ('B' COLLATE "C" < 'a' COLLATE "C") AS lexical_order;
```

Under `"C"`, results follow byte code order; in UTF-8, ASCII uppercase letters precede lowercase letters.

### 10.2. Equality Under Nondeterministic Collations

```sql
SELECT
    ('Anh' COLLATE encoding_lab.case_insensitive =
     'anh' COLLATE encoding_lab.case_insensitive)
        AS equal_under_ci;
```

With our sample ICU collation, the result is expected to be `true`. This directly affects:

- `WHERE full_name = ...`
- `GROUP BY full_name`
- `DISTINCT full_name`
- `ORDER BY full_name`
- `UNIQUE` constraints on columns using that collation.

**Do not confuse "equal under collation rules" with "byte-identical."** With nondeterministic ICU, byte-distinct strings can belong to the same equivalence class.

### 10.3. Comparing Two Columns with Different Collations

If two columns declare different collations, comparing them can trigger a collation conflict error, especially when both specify conflicting explicit collations.

The fix is not random casting: **define the intended business comparison rule** and apply one deliberate collation:

```sql
-- Illustrates explicitly choosing a single rule:
SELECT
    ('Anh' COLLATE "C") = ('anh' COLLATE "C") AS exact_result;
```

When joining technical codes with user names, do not force both columns to share one collation if their data semantics differ.

## 11. Collations and `UNIQUE` Constraints

This is one of the most consequential effects of nondeterministic collations.

### 11.1. UNIQUE with Case-Sensitive Collation

```sql
CREATE TABLE encoding_lab.exact_codes (
    code text COLLATE "C" PRIMARY KEY
);

INSERT INTO encoding_lab.exact_codes (code)
VALUES ('ABC'), ('abc');
```

With `"C"`, the two values have different bytes and are treated as distinct; both can coexist because the primary key does not view them as duplicates.

That makes sense when `code` is a **machine identifier** where case is significant.

### 11.2. UNIQUE with Case-Insensitive Collation

```sql
CREATE TABLE encoding_lab.case_insensitive_names (
    name text COLLATE encoding_lab.case_insensitive
        NOT NULL UNIQUE
);

INSERT INTO encoding_lab.case_insensitive_names(name)
VALUES ('Anh');
```

If you insert:

```sql
-- Expected duplicate key error under case_insensitive collation:
INSERT INTO encoding_lab.case_insensitive_names(name)
VALUES ('anh');
```

PostgreSQL treats the two names as equal under the collation and rejects the second row due to `UNIQUE`.

**Consequence:** choosing a collation becomes a **data integrity rule**, not merely a display preference.

### 11.3. Choosing Collations for Usernames and Emails

Different systems enforce different identity policies. Some require:

- Usernames that are case-insensitive yet **accent-sensitive**.
- Customer codes that distinguish every byte.
- Display names that may repeat yet sort linguistically.
- Emails with specific comparison and canonicalization rules beyond simple `lower(email)`.

Keep these distinct:

| Data | Typical Requirement | Design Direction |
| --- | --- | --- |
| Technical code | Exact, byte-unambiguous | `text COLLATE "C"`, appropriate UNIQUE/PK |
| Display name | Linguistic sorting | Language-aware collation |
| Username | Dedicated registration rules | Normalized key + explicit constraint |
| Email | Defined canonicalization rules | Do not rely solely on one ICU collation |
| Convenience search | May ignore case or accents | Search engine / expressions / collation per version |

Do not apply a single "loose" collation to every column in a database just to write fewer string-processing expressions.

## 12. Unicode Normalization: Same Visual Appearance, Different Code Points

A Unicode string can be encoded in multiple canonically equivalent sequences. Two familiar forms:

- **NFC (*Normalization Form C*)**: prefers precomposed characters where defined.
- **NFD (*Normalization Form D*)**: decomposes characters into base plus combining marks where defined.

Example character `é`:

```text
Precomposed form:
  U+00E9
  é

Decomposed form:
  U+0065 U+0301
  e + combining acute accent
```

In UTF-8 PostgreSQL:

```sql
SELECT
    U&'\00E9' AS composed,
    U&'e\0301' AS decomposed,
    U&'\00E9' COLLATE "C" =
      U&'e\0301' COLLATE "C" AS same_bytes;
```

Both strings look identical, yet `same_bytes` is `false` under `"C"` comparison.

### 12.1. Using `normalize`

PostgreSQL provides the `normalize(...)` function when the database encoding is UTF8.

```sql
SELECT
    normalize(U&'\00E9', NFC) AS normalized_one,
    normalize(U&'e\0301', NFC) AS normalized_two,
    normalize(U&'\00E9', NFC) COLLATE "C"
      = normalize(U&'e\0301', NFC) COLLATE "C"
        AS equal_after_nfc;
```

`equal_after_nfc` is expected to return `true`. Normalization ensures canonical equivalence before performing exact comparisons.

Checking lengths:

```sql
SELECT
    char_length(U&'\00E9') AS nfc_characters,
    char_length(U&'e\0301') AS nfd_characters,
    octet_length(U&'\00E9') AS nfc_bytes,
    octet_length(U&'e\0301') AS nfd_bytes;
```

This example shows that normalization and encoding/collation are **related yet distinct concerns**.

### 12.2. When Should Input Be Normalized?

You can establish a normalization policy on write:

```sql
INSERT INTO encoding_lab.people(full_name)
VALUES (normalize(U&'B\0069\0300nh', NFC));
```

This example uses `Bình` with a combining grave accent. Under NFC normalization, the string converts to the corresponding precomposed representation.

If a system must preserve legal texts or byte-signed payloads verbatim, **never normalize blindly** without understanding the original-retention requirement. Normalization alters bytes and can invalidate hashes or digital signatures.

### 12.3. Normalization Is Not Accent Folding or Lowercasing

`normalize(..., NFC)` is not meant to "turn `Đặng` into `dang`" or "turn `Anh` into `anh`." It resolves Unicode representation equivalence. Case-insensitive or accent-insensitive search requires **separate rules** evaluated against business requirements.

## 13. Searching with `LIKE` and `ILIKE`

`LIKE` and `ILIKE` perform pattern matching and should not be treated as synonyms for collation.

### 13.1. `LIKE`: Pattern Matching

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name LIKE 'Ng%';
```

`%` matches any sequence of zero or more characters, while `_` matches a single character under PostgreSQL pattern matching.

`LIKE` is typically case-sensitive in common configurations. However, newer PostgreSQL releases have evolved support for nondeterministic collations; do not assume every PostgreSQL version shares identical pattern-matching behavior.

### 13.2. `ILIKE`: Locale-Aware Case-Insensitive Matching

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name ILIKE 'ng%';
```

`ILIKE` is a PostgreSQL extension for case-insensitive pattern matching using the appropriate locale rules.

**Important:** `ILIKE` does **not automatically strip accents**. A pattern `'nguyen%'` will not match `'Nguyễn'` because `ễ` is not `e`. If the application needs accent-insensitive search, design dedicated normalization/search handling and test with Vietnamese inputs.

### 13.3. Pattern Matching with Nondeterministic Collations

Support for `LIKE`, `ILIKE`, and regex operators with nondeterministic ICU collations **depends on the PostgreSQL version and the specific operator**. Older versions reject pattern matching on nondeterministic collations; newer versions added partial support.

To avoid production surprises:

1. Check `SHOW server_version`.
2. Test the exact `LIKE`/`ILIKE`/regex operators you need on that version.
3. Test with the declared collation.
4. If unsupported or slow, pick another strategy such as a normalized column, expression index, or search index.

Do not attach a case-insensitive collation to a column and assume every `ILIKE` query will work and use an index efficiently.

## 14. `lower`, `upper`, and Case-Normalization Expressions

A common approach for case-insensitive lookup is normalizing both sides with `lower`:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

`lower` and `upper` transform text according to locale/collation rules, not an "ASCII-only" mapping for all inputs. Results can differ in certain languages, such as Turkish dotted/dotless I variants.

### 14.1. Indexing on `lower(...)`

If queries frequently filter this way:

```sql
CREATE INDEX idx_people_full_name_lower
ON encoding_lab.people (lower(full_name));
```

PostgreSQL can consider this index for:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

The query expression must match the indexed expression; creating an index does not guarantee the planner picks it on tiny tables.

### 14.2. UNIQUE on `lower(...)`

If the rule forbids two usernames differing only by letter case:

```sql
CREATE TABLE encoding_lab.accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL
);

CREATE UNIQUE INDEX ux_accounts_username_lower
ON encoding_lab.accounts (lower(username));
```

Sample data:

```sql
INSERT INTO encoding_lab.accounts(username)
VALUES ('Alice');

-- Rejected because lower(username) collides:
INSERT INTO encoding_lab.accounts(username)
VALUES ('alice');
```

This enforces **consistency inside the database**. Still, `lower` does not solve every Unicode casefolding and normalization edge case. When global usernames follow complex canonicalization rules, design a dedicated identifier normalization pipeline rather than treating `lower` as a silver bullet.

### 14.3. `citext` as an Extension Option

PostgreSQL provides the `citext` extension for **case-insensitive** strings implemented roughly via `lower`-style comparisons.

If the server provides the extension and your role can install it:

```sql
CREATE EXTENSION IF NOT EXISTS citext;
```

You can use `citext` in custom designs, while weighing trade-offs:

- `citext` is an **extension**, not guaranteed on every managed server.
- Comparison behavior depends on locale case conversion rules.
- For complex Unicode rules, nondeterministic ICU collations can offer different and sometimes cleaner behavior.
- Never convert all `text` columns to `citext` blindly without checking uniqueness, indexes, and compatibility.

## 15. How Collation Affects B-Tree Indexes

A B-tree index on a text column relies on the comparison/sort rules of its collation and operator class. If a query uses a different collation on the expression, an existing index may not satisfy that `ORDER BY` or predicate under the new rule.

### 15.1. Index Using the Column's Default Collation

```sql
CREATE INDEX idx_people_name_default
ON encoding_lab.people (full_name);
```

This index uses `full_name`'s declared/schema collation.

Example:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name
LIMIT 20;
```

PostgreSQL may use the index to satisfy the sort depending on plan cost, table size, and selectivity.

### 15.2. Index with `"C"` for Specific Ordering

```sql
CREATE INDEX idx_people_name_c
ON encoding_lab.people (full_name COLLATE "C");
```

Matching query:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE "C", person_id
LIMIT 20;
```

This index supports sorting under `"C"`, whereas a column default or ICU collation does **not match** `"C"`. Additionally, because the query also sorts by `person_id`, the planner may need extra work for the second sort key; to let the index satisfy the entire order, consider a composite index:

```sql
CREATE INDEX idx_people_name_c_id
ON encoding_lab.people (full_name COLLATE "C", person_id);
```

This is a matching index candidate for `ORDER BY full_name COLLATE "C", person_id`, though keep only indexes genuinely justified by the workload.

### 15.3. Indexes with Nondeterministic Collations

```sql
CREATE INDEX idx_people_name_ci
ON encoding_lab.people (
    full_name COLLATE encoding_lab.case_insensitive
);
```

This index uses the ICU collation created earlier and can support comparisons/lookups using that collation. However, nondeterministic comparisons and index internals carry trade-offs, such as reduced B-tree deduplication capability. Measure performance overhead on real data and your target PostgreSQL version.

**Never use `EXPLAIN` on a seven-row table to conclude which index is faster in production.** The planner will naturally prefer a sequential scan when data is tiny.

## 16. Prefix Search, `text_pattern_ops`, and `pg_trgm`

### 16.1. Prefix `LIKE 'abc%'` Differs from Locale Sort Order

A query like:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name LIKE 'Ng%';
```

performs a **prefix search**. In databases using non-`"C"` collations, a standard text B-tree index does not always optimize prefix `LIKE` matching.

PostgreSQL provides the `text_pattern_ops` operator class:

```sql
CREATE INDEX idx_people_name_pattern
ON encoding_lab.people (full_name text_pattern_ops);
```

This index can help `LIKE 'Ng%'` prefix queries on columns with matching collations. It **does not replace** an index used for linguistic `ORDER BY` because it uses different comparison rules.

### 16.2. Using `lower(...)` for Case-Insensitive Prefix Search

Example query:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE lower(full_name) LIKE 'ng%';
```

Index candidate:

```sql
CREATE INDEX idx_people_lower_pattern
ON encoding_lab.people (
    (lower(full_name)) text_pattern_ops
);
```

The query expression must match the indexed expression, and locale casefolding behavior must align with business expectations.

For conditions with a leading wildcard like `'%ng%'`, a B-tree prefix index cannot accelerate lookups the way `'ng%'` does.

### 16.3. `pg_trgm` for Substring (Contains) Search

If the server provides the `pg_trgm` extension and your role can install it:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_people_name_trgm
ON encoding_lab.people
USING gin (full_name gin_trgm_ops);
```

A trigram index can assist queries like:

```sql
SELECT person_id, full_name
FROM encoding_lab.people
WHERE full_name ILIKE '%ng%';
```

However, very short patterns or patterns yielding few selective trigrams may not filter well; for instance `'%ng%'` has only two characters and may not leverage a trigram index effectively. Benchmark with real queries and `EXPLAIN`.

Moreover, `pg_trgm` does not strip Vietnamese diacritics automatically. If searching `"nguyen"` must match `"Nguyễn"`, build a dedicated accent-folding/normalization step rather than assuming `ILIKE` or trigram indexes handle it out of the box.

## 17. Collations with `DISTINCT`, `GROUP BY`, and `JOIN`

Collation affects not only `ORDER BY`, but also grouping and join semantics when comparing strings.

### 17.1. Case-Insensitive Grouping

```sql
SELECT
    full_name COLLATE encoding_lab.case_insensitive AS name_group,
    COUNT(*) AS how_many
FROM encoding_lab.people
GROUP BY full_name COLLATE encoding_lab.case_insensitive
ORDER BY name_group;
```

If data contains `Anh` and `anh`, they can be grouped together under a nondeterministic collation. Which representative casing is displayed for the group depends on row order and execution plan; do not treat the representative value's casing as a stable canonicalization rule.

If you need a deterministic display value, store a canonical value separately or define an explicit representative selection rule.

### 17.2. `DISTINCT`

```sql
SELECT DISTINCT
    full_name COLLATE encoding_lab.case_insensitive AS unique_name
FROM encoding_lab.people
ORDER BY unique_name;
```

The row count can be smaller than `DISTINCT full_name COLLATE "C"` because byte-distinct strings collapse under the nondeterministic ICU collation.

### 17.3. Joining on Names: Risk of False Matches

```sql
-- Illustrates a JOIN condition you should not use by default
-- to link two entities via display names:
SELECT p1.person_id, p2.person_id
FROM encoding_lab.people AS p1
JOIN encoding_lab.people AS p2
  ON p1.full_name COLLATE encoding_lab.case_insensitive
   = p2.full_name COLLATE encoding_lab.case_insensitive
WHERE p1.person_id < p2.person_id;
```

The query treats `Anh` and `anh` as equal. Yet **two people with the same name are not necessarily the same person**. In relational schemas, join entities by well-defined IDs/foreign keys, never by display names simply because a collation merges them.

Collation can assist name comparisons for search, but never replaces reliable identity keys.

## 18. What Happens When ICU or the OS Is Upgraded?

Sorting rules are not permanently immutable. After an upgrade:

- The ICU library may change how certain strings compare.
- The OS `libc` library may revise locale rules.
- Indexes built under older rules may become inconsistent with the new ordering.
- `UNIQUE` constraints depending on collations may need inspection because equality boundaries can shift.

### 18.1. Checking Collation Versions

An inspection query on supporting versions:

```sql
SELECT
    n.nspname,
    c.collname,
    c.collversion AS recorded_version,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
  ON n.oid = c.collnamespace
WHERE n.nspname = 'encoding_lab'
ORDER BY c.collname;
```

If `recorded_version` differs from `actual_version`, investigate every index, constraint, and object depending on that collation.

### 18.2. `REFRESH VERSION` Does Not Rebuild Indexes Automatically

PostgreSQL provides:

```sql
ALTER COLLATION encoding_lab.case_insensitive
    REFRESH VERSION;
```

However, **this command only updates recorded version metadata; it does not automatically rebuild indexes ordered by that collation**.

Operational procedure should:

1. Check database version, libc/ICU versions, and collation mismatch warnings.
2. Identify dependent indexes and constraints.
3. Assess the risk that keys previously treated as distinct now collide.
4. Schedule **REINDEX** for affected indexes using an appropriate strategy.
5. Verify data consistency and application behavior.
6. After proper maintenance, update version metadata as recommended by PostgreSQL.

Illustrative commands (run only after verifying dependent objects and having an operations plan):

```sql
REINDEX INDEX encoding_lab.idx_people_name_ci;

ALTER COLLATION encoding_lab.case_insensitive
    REFRESH VERSION;
```

For the **database default collation**, PostgreSQL versions provide dedicated checks and refresh commands such as `ALTER DATABASE ... REFRESH COLLATION VERSION`, alongside rebuilding dependent indexes.

**Never run `REINDEX` recklessly in production**: depending on method, it consumes heavy CPU/I/O, disk space, and locks. If new equality rules introduce duplicate keys, reindexing a unique index will fail and require data remediation per business policy.

### 18.3. Why Not Simply "Ignore the Warning"?

A B-tree index ordered by outdated rules can return wrong query results or compromise integrity once comparison rules change. Therefore, a collation version mismatch warning is an operational signal requiring action, not a cosmetic notice.

## 19. Import/Export: UTF-8 and CSV

In day-to-day operations, encoding issues frequently surface when importing files from spreadsheets, legacy systems, or external applications.

### 19.1. CSV Data Must Be Decoded with the Right Encoding

Suppose `people.csv` has UTF-8 content:

```csv
full_name
Nguyễn An
Trần Bình
Lê Chi
```

You can use `\copy` from `psql` to import a file on the client machine:

```text
\copy encoding_lab.people (full_name) FROM 'people.csv' WITH (FORMAT csv, HEADER true)
```

Here `encoding_lab.people` has an identity `person_id` column, so the ID column can be omitted from the CSV.

`\copy` is a **psql client** command: the file path is resolved on the machine running `psql`. SQL `COPY ... FROM '/server/path'` reads from the **server machine**, subject to server permissions and paths. Never confuse the two locations.

### 19.2. What If the File Is Not UTF-8?

A legacy file may use a different code page. In that case:

- Verify the file's actual encoding.
- Convert the file cleanly to UTF-8 using a trusted tool, **or**
- Configure supported `COPY ... ENCODING` conversion according to your PostgreSQL version and encoding pair.
- Never use `SET client_encoding = UTF8` as a way to "transcode" a source file that is not actually UTF-8.

Avoid running guesswork conversion commands on files of unknown encoding; misdecoding creates mojibake that is hard to reverse.

### 19.3. Verifying Data After Import

Useful checks:

```sql
SELECT
    person_id,
    full_name,
    char_length(full_name) AS characters,
    octet_length(full_name) AS bytes
FROM encoding_lab.people
ORDER BY person_id;
```

Searching for common artifacts of misdecoded UTF-8 (such as strange replacement characters) serves only as an **investigation hint**. Never run blind table-wide string replacements without verifying original source records and impact on real names.

### 19.4. Connection Encoding and Collation Are Not the Same Thing

When loading a CSV file into the database:

```text
CSV bytes
   |
   | Decode with proper file/client encoding
   v
Characters sent to PostgreSQL
   |
   | Convert to database encoding
   v
Text stored in column
   |
   | COLLATE applied during ORDER BY / compare
   v
Display / search results
```

If corruption occurs at the byte layer, collation cannot fix the stored text. Conversely, clean bytes paired with the wrong collation still produce unexpected sorting and matching behavior.

## 20. Full Lab: Comparing Across Rules

The following examples target a UTF8 test database. Creating ICU collations requires a server built with ICU and `CREATE` privilege in the schema. If your environment lacks ICU, you can still practice the `"C"`, Unicode normalization, and encoding sections.

### 20.1. Initialize Schema and Sample Data

```sql
CREATE SCHEMA IF NOT EXISTS encoding_lab;

CREATE TABLE encoding_lab.words (
    word_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word text NOT NULL
);

INSERT INTO encoding_lab.words(word)
VALUES
    ('Anh'),
    ('anh'),
    ('Ánh'),
    ('Bình'),
    (U&'Bi\0300nh'),
    ('Nguyễn'),
    ('Lan'),
    ('lan');
```

`'Bình'` and `U&'Bi\0300nh'` look identical when displayed, yet the second string uses a combining grave accent after `i`.

If you run this lab multiple times, the table already exists and `INSERT` adds duplicate rows. Use a dedicated database/schema for the exercise and avoid deleting unrelated data.

### 20.2. Compare Default Ordering vs. `"C"`

```sql
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word, word_id;
```

```sql
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word COLLATE "C", word_id;
```

Compare the ordering; do not memorize one universal order when the database's default collation is unspecified.

### 20.3. Compare Two Unicode Representations

```sql
SELECT
    U&'\00E9' COLLATE "C" =
        U&'e\0301' COLLATE "C" AS exact_equal,
    normalize(U&'\00E9', NFC) COLLATE "C" =
        normalize(U&'e\0301', NFC) COLLATE "C"
        AS normalized_equal;
```

Expected output:

| Column | Result |
| --- | --- |
| `exact_equal` | `false` |
| `normalized_equal` | `true` |

The difference stems from **Unicode representation**, not a lack of accented character support in the database.

### 20.4. Create a Case-Insensitive ICU Collation

```sql
CREATE COLLATION encoding_lab.ci_demo (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Run:

```sql
SELECT
    ('Anh' COLLATE encoding_lab.ci_demo =
     'anh' COLLATE encoding_lab.ci_demo) AS case_equal,
    ('Anh' COLLATE encoding_lab.ci_demo =
     'Ánh' COLLATE encoding_lab.ci_demo) AS accent_equal;
```

Expected per our sample rules: `case_equal` is true; `accent_equal` is normally false. If yours differs, check your ICU configuration/version and effective strength level.

### 20.5. Compare Impact on `GROUP BY`

```sql
SELECT
    word COLLATE encoding_lab.ci_demo AS word_group,
    COUNT(*) AS total
FROM encoding_lab.words
GROUP BY word COLLATE encoding_lab.ci_demo
ORDER BY word_group;
```

Contrast with:

```sql
SELECT
    word COLLATE "C" AS word_group,
    COUNT(*) AS total
FROM encoding_lab.words
GROUP BY word COLLATE "C"
ORDER BY word_group;
```

Under `ci_demo`, variants differing only in case collapse into the same group. Under `"C"`, they remain distinct.

### 20.6. Testing `UNIQUE`

```sql
CREATE TABLE encoding_lab.unique_ci_demo (
    word text COLLATE encoding_lab.ci_demo NOT NULL UNIQUE
);

INSERT INTO encoding_lab.unique_ci_demo(word)
VALUES ('Lan');
```

Next:

```sql
-- Expected duplicate key error if 'Lan' and 'lan'
-- are treated as equal by ICU collation ci_demo:
INSERT INTO encoding_lab.unique_ci_demo(word)
VALUES ('lan');
```

If you test an intentionally failing statement inside a larger transaction, PostgreSQL puts the transaction into an aborted state. Run failing tests in separate transactions or issue `ROLLBACK` before continuing.

### 20.7. Inspecting Execution Plans and Indexes

```sql
CREATE INDEX idx_words_c
ON encoding_lab.words (word COLLATE "C");

EXPLAIN
SELECT word_id, word
FROM encoding_lab.words
ORDER BY word COLLATE "C", word_id
LIMIT 20;
```

Because the sample table has very few rows, the planner may pick `Seq Scan + Sort`. That does not indicate a faulty collation or index: scanning and sorting a handful of rows is cheaper than traversing an index.

To evaluate real performance, test with a sufficiently large dataset, up-to-date statistics, representative queries, and write/index overhead measurements.

## 21. Common Mistakes

| Misconception | Why Is It Wrong? | Resolution |
| --- | --- | --- |
| "UTF-8 automatically sorts names in Vietnamese order." | Encoding defines bytes, not linguistic sort rules | Choose an appropriate collation |
| "Choosing an ICU collation fixes mojibake text." | The text was already misdecoded before storage | Inspect source encoding and recover the data |
| "`varchar(20)` holds at most 20 bytes." | Limit is in characters; UTF-8 is variable-length | Use `octet_length` when enforcing byte limits |
| "`char_length` always equals visible user characters." | One grapheme can span multiple code points | Understand Unicode normalization and counting rules |
| "`Anh` and `anh` are always unequal." | Nondeterministic ICU can treat them as equal | Verify collation and identifier policies |
| "`Anh` and `Ánh` are always equal when ignoring case." | Accents may still matter at secondary strength | Pick the right strength for business rules |
| "`lower` handles every Unicode language cleanly." | Case mapping/locales have edge cases | Design dedicated canonicalization if needed |
| "`ILIKE` automatically ignores Vietnamese accents." | It is not guaranteed to be accent-insensitive | Build a dedicated search pipeline |
| "A locale B-tree index always optimizes prefix LIKE." | Pattern matching and locale sorting follow different rules | Consider `text_pattern_ops` / appropriate indexes |
| "An index on `full_name` works for any `COLLATE`." | Indexes are bound to a specific collation | Verify index key collation and `EXPLAIN` |
| "Nondeterministic collations support all regex/LIKE on all PostgreSQL versions." | Support varies by version and operator | Check docs/version and test explicitly |
| "Collation only affects `ORDER BY`." | It also affects equality, UNIQUE, GROUP BY | Treat collation as a data-semantics decision |
| "`UNIQUE` with case-insensitive collation allows both `'Lan'` and `'lan'`." | Both values can collide under that collation | Verify uniqueness requirements |
| "NFC strips accents." | NFC normalizes composition, not diacritics | Distinguish normalization from accent folding |
| "You can change database encoding with ALTER TABLE." | Encoding belongs to the database and template rules | Plan database creation / migration properly |
| "ICU/OS upgrades require no attention." | Ordering/equality can shift and break indexes | Check versions and plan REINDEX |
| "REFRESH VERSION automatically runs REINDEX." | It only updates version metadata | Rebuild dependent indexes explicitly |
| "`ORDER BY name` is always stable across collation ties." | Multiple values can tie under a collation | Add a deterministic tie-breaker like ID |
| "Display names are safe for joining two people." | Identical names do not imply identical identity | Join on identity keys |
| "Using `"C"` on every column is simplest." | Fails user-facing linguistic sorting | Pick collations per column domain |
| "ICU is always installed on every server." | PostgreSQL may be compiled without ICU | Check environment and privileges |

## 22. Practice Exercises with Hints

### Exercise 1. Distinguishing Encoding and Collation

A database uses `UTF8`, yet a list of accented names sorts in an order unsuitable for Vietnamese. What should you inspect?

**Hint:** data may be stored cleanly in UTF-8 while using `"C"` or an unexpected collation. Check database default, column, and query collations and locale settings; never change encoding just to fix sort order.

### Exercise 2. Checking Bytes and Characters

```sql
SELECT
    char_length('Tiếng Việt'),
    octet_length('Tiếng Việt');
```

**Question:** why do these two numbers differ?

**Answer:** in UTF-8, many accented characters require multiple bytes. `char_length` counts characters, whereas `octet_length` counts bytes.

### Exercise 3. Why Does a String Not Fit in `varchar(1)`?

```sql
CREATE TEMP TABLE single_character (value varchar(1));

-- Intentionally cause a length error when inserting into the column:
INSERT INTO single_character(value) VALUES (U&'e\0301');
```

**Hint:** the string composed of `e` plus a combining acute accent has two code points/characters as PostgreSQL counts them, so it exceeds `varchar(1)` despite rendering as one `é`. Try again after applying `normalize(..., NFC)`. Note: **explicitly casting** to `varchar(n)` in PostgreSQL truncates characters instead of failing; this exercise uses `INSERT` into a bounded column to observe write-time length validation.

### Exercise 4. Two Names Differing by Case Must Group Together

Data contains `'Anh'` and `'anh'`, and you want `GROUP BY` to merge them into one group. What are your options?

**Hint:** use `GROUP BY lower(name)` if application case-mapping rules suit it, or use a verified nondeterministic ICU collation. Decide explicitly how to pick the representative display casing.

### Exercise 5. A Technical Code Column Must Distinguish Every Byte

If code `ABC` must differ from `abc`, which collation fits?

**Hint:** `text COLLATE "C"` combined with `UNIQUE`/`PRIMARY KEY` distinguishes values byte-for-byte. For critical identifiers, also add validation for format, whitespace, and input rules.

### Exercise 6. Case-Insensitive Lookup Needed

```sql
SELECT *
FROM encoding_lab.people
WHERE lower(full_name) = lower('ANH');
```

**Question:** when the table grows very large and this query runs repeatedly, which index can help?

**Answer:** an expression index on `lower(full_name)`, verified with `EXPLAIN` on representative data.

### Exercise 7. Can `ILIKE 'nguyen%'` Reliably Match `Nguyễn`?

**Answer:** no. `ILIKE` does not strip accents. You need dedicated accent-folding/normalization or language-appropriate search if required by the business.

### Exercise 8. Collation Version Mismatch Warning After ICU Upgrade

What should you do?

**Hint:** identify dependent collations and indexes, assess equality/sort changes and duplicate-key risks, plan an appropriate `REINDEX`, verify data integrity, and only then refresh version metadata. Never run `REFRESH VERSION` just to silence the warning.

### Exercise 9. `ORDER BY` Must Be Stable for Pagination

```sql
SELECT person_id, full_name
FROM encoding_lab.people
ORDER BY full_name COLLATE encoding_lab.case_insensitive
LIMIT 20;
```

**Question:** what risk exists here?

**Answer:** multiple names can tie under the collation. Add `person_id` as a secondary sort key for deterministic ordering:

```sql
ORDER BY full_name COLLATE encoding_lab.case_insensitive,
         person_id
```

### Exercise 10. Why Can `UNIQUE` Behave Differently on the Same Names?

**Answer:** `UNIQUE` on `text COLLATE "C"` and on `text COLLATE encoding_lab.case_insensitive` apply different equality rules. With a case-insensitive collation, `'Lan'` and `'lan'` collide as duplicates.

### Exercise 11. Prefix Search `'Ng%'` Not Using a B-Tree Index as Expected

**Hint:** inspect the collation, query expression, index key, selectivity, and `EXPLAIN` plan. For non-C collations, a `text_pattern_ops` index is a candidate for prefix `LIKE` queries when applicable.

### Exercise 12. Two Identical-Looking Unicode Literals Yield False for `=`

```sql
SELECT
    U&'\00E9' COLLATE "C" =
    U&'e\0301' COLLATE "C" AS equal_before,
    normalize(U&'\00E9', NFC) COLLATE "C" =
    normalize(U&'e\0301', NFC) COLLATE "C" AS equal_after;
```

**Answer:** `equal_before` is false due to different bytes/code points; `equal_after` is true because NFC normalizes both to the same representation.

### Exercise 13. UTF-8 Database Shows Garbled Text from CSV Import

**Hint:** inspect the file's actual encoding, how the client read the file, `client_encoding`, transcoding steps, and existing stored data. Do not switch collations to fix a decoding error.

### Exercise 14. When Not to Use an Accent-Insensitive Collation for Usernames?

If two usernames distinguished by diacritics can belong to two different people, an accent-insensitive collation treats them as duplicates, causing unwanted registration rejections or identity collisions. Use an approved, consistent canonicalization policy.

## 23. Design Checklist for Text Data

Before deploying a `text` or `varchar` column, answer:

| Question | Why Does It Matter? |
| --- | --- |
| Does the database use `UTF8`? | Ensures multilingual storage |
| What is the actual encoding of source files? | Prevents mojibake |
| Which encoding do clients/drivers send? | Prevents byte corruption before storage |
| Is this field a technical code or a human name? | Each needs different equality/sort rules |
| Is Vietnamese linguistic sorting required? | Guides locale/collation choice |
| Should comparisons be case-sensitive? | Affects `WHERE` and `UNIQUE` |
| Should comparisons be accent-sensitive? | Affects identity and search |
| Is Unicode normalization needed? | Prevents multiple representations of identical-looking strings |
| Are queries using `LIKE`, `ILIKE`, or substring search? | Determines operators and indexes |
| Does the collation use nondeterministic ICU? | Verify support, equality, and pattern matching |
| Are B-tree, `text_pattern_ops`, or trigram indexes needed? | Ensures suitable query plans |
| Is there a `UNIQUE` constraint on name/username? | Collation becomes an integrity rule |
| Are results paginated by name? | Add a deterministic tie-breaker key |
| Will the OS/ICU/libc be upgraded? | Requires a collation version and REINDEX plan |
| Is data shared with external systems? | Encoding/canonicalization contracts must align |

## 24. Summary

Core principles of **character encoding, collation, and string comparison in PostgreSQL**:

1. **Encoding governs bytes**, while **collation governs comparison and sorting rules**. UTF-8 does not automatically make searches case-insensitive or accent-insensitive.
2. **`server_encoding` and `client_encoding` play separate roles**. Ensure source data, connections, and import files are decoded cleanly.
3. **`text` and `varchar(n)` store strings in the database encoding**. `varchar(n)` caps character count, not simply byte count; Unicode graphemes can be more complex than code point counts.
4. **`"C"` suits technical codes requiring byte order**, whereas ICU/libc collations support linguistic sorting, including Vietnamese.
5. **Nondeterministic ICU collations can treat byte-distinct strings as equal**. This affects not only `ORDER BY`, but also `=`, `UNIQUE`, `GROUP BY`, and `DISTINCT`.
6. **Unicode normalization resolves representation equivalence**, not accent folding or lowercasing. Use `normalize(..., NFC)` when data rules and encoding permit.
7. **`LIKE`, `ILIKE`, `lower`, `citext`, and ICU collations are different tools**. Pattern matching support on nondeterministic collations varies by PostgreSQL version.
8. **Collation determines index usability**. An index using `"C"` does not automatically serve other `ORDER BY` collations; prefix search may need `text_pattern_ops`, and substring search may use `pg_trgm`.
9. **ICU/libc upgrades can alter ordering and equality**, affecting indexes and constraints. `REFRESH VERSION` does not rebuild indexes automatically.
10. **Design around data semantics**: identifiers need exact comparisons; display names need linguistic sorting; user-friendly search needs its own strategy; usernames/emails need explicit identity rules.

When working with Vietnamese text in PostgreSQL, ask the questions in the right order: **are the bytes encoded/decoded properly; does the text need Unicode normalization; should comparisons be exact, case-insensitive, or linguistic; and do your indexes and constraints enforce that same rule?** Answering these four questions consistently ensures your system both stores characters accurately and searches and validates data according to business intent.
