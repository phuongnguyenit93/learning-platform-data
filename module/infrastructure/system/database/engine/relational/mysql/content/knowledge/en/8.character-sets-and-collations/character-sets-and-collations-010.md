# Vietnamese Sorting and Searching by Business Requirements

A customer management application needs to sort names in Vietnamese order and find customers when users type without diacritics, while still strictly distinguishing different names during duplicate checks. Meanwhile, an online store needs case-insensitive product search while SKU codes must be compared exactly. These requirements cannot be solved with a single comparison rule for every column.

In MySQL, the **character set** determines how characters are encoded; the **collation** determines how strings belonging to that character set are compared and sorted. To handle Vietnamese properly, determine whether the business domain needs accent sensitivity, case sensitivity, Vietnamese dictionary ordering, or only general Unicode comparison. Only then should you choose collations, design indexes, and build the corresponding search logic.

## 1. How do character sets and collations differ?

### 1.1. Character set: how are characters encoded?

A character set defines the repertoire of characters and how they are represented as bytes. For modern Vietnamese data, use `utf8mb4` to store full Unicode, including accented letters, extended characters, and emojis.

In MySQL, the name `utf8` was historically an alias for `utf8mb3`, supporting at most three bytes per Unicode character. `utf8mb4` supports up to four bytes and is the choice to use for new schemas. Do not pick `utf8` just because its name looks equivalent to Unicode's UTF-8.

For example, the string `Tiếng Việt – Đặng` must travel through the client, connection, and column using compatible character sets. If the client sends UTF-8 bytes while the connection interprets them under another character set, the data can become corrupted even if the target column uses `utf8mb4`.

### 1.2. Collation: how are strings compared and sorted?

A collation is a set of rules for comparing strings within a character set. It affects:

- Comparisons using `=`, `<>`, `IN`, and other string comparisons.
- Sorting and grouping via `ORDER BY`, `GROUP BY`, and `DISTINCT`.
- Searching via `LIKE` and certain string comparisons in expressions.
- `UNIQUE INDEX` uniqueness, because two strings considered equal under a collation may have different bytes.
- Index usability when a query uses a collation compatible with the column's index.

For example, a case-insensitive collation can treat `An` and `AN` as equal. An accent-insensitive collation can treat `hoa` and `hòa` as equal in a given comparison. This can be helpful for broad searches, yet causes business bugs if applied to identifier keys or names requiring accent distinction.

Character sets and collations can be specified at the server, database, table, column, connection, or expression level. Each level has its own defaults and inheritance rules; when certainty is required, check the actual collation of the column and expression rather than looking only at server configuration.

## 2. Important nuances when handling Vietnamese

### 2.1. Tone marks and vowel diacritics change meaning

Vietnamese uses tone marks and many accented letters. The strings below are distinct words with different meanings:

| String | Distinction |
|---|---|
| `ma` | Unaccented |
| `má` | Acute (sắc) |
| `mà` | Grave (huyền) |
| `mả` | Hook above (hỏi) |
| `mã` | Tilde (ngã) |
| `mạ` | Dot below (nặng) |
| `a`, `ă`, `â` | Distinct letters in the Vietnamese alphabet |
| `d`, `đ` | Two distinct letters |

An accent-insensitive search can help users who type `Nguyen` still find `Nguyễn`. Yet if the same collation is used for uniqueness checks, the system may treat values that the business considers distinct as duplicates. Test tone marks, vowel diacritics, and the letter `đ`; do not infer full behavior solely from a collation's name.

### 2.2. Case sensitivity is a separate requirement

Person names generally need case-insensitive comparison: `NGUYỄN AN`, `Nguyễn An`, and `nguyễn an` can be considered the same name for searching. However, displayed content should preserve the capitalization entered by the user.

Identifiers, SKU codes, or tokens may require case sensitivity. For example, `sku-a1` and `SKU-A1` can be two distinct codes if system conventions dictate so. Do not apply a person-name collation to every string column.

### 2.3. Dictionary order differs from byte order

Sorting strings by UTF-8 bytes does not produce Vietnamese dictionary order. Unicode collations use comparison weights to determine ordering. Language-tailored collations can adjust letter ordering to align better with that language's rules.

If business logic requires a list of names in Vietnamese dictionary order, choose a Vietnamese collation if provided by the server and test with a dataset covering `a`, `ă`, `â`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư` along with tone marks. A general Unicode collation may sort accurately per generic Unicode rules without producing the exact order Vietnamese users expect.

## 3. Discovering available character sets and collations

Do not guess which collations are installed on the server. First query the supported list:

```sql
SHOW CHARACTER SET LIKE 'utf8mb4';

SHOW COLLATION LIKE 'utf8mb4%';

SHOW COLLATION LIKE '%vietnamese%';

SHOW COLLATION LIKE 'utf8mb4_vi_0900%';
```

You can query metadata:

```sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    IS_COMPILED,
    SORTLEN
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
```

To inspect settings across levels:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

Key variables to note:

| Variable | Meaning |
|---|---|
| `character_set_server` | Server-level default character set |
| `collation_server` | Server-level default collation |
| `character_set_database` | Default character set of the current database (usage depends on version) |
| `collation_database` | Default collation of the current database |
| `character_set_client` | Character set the client uses to send statements |
| `character_set_connection` | Character set MySQL uses when processing statement input strings |
| `character_set_results` | Character set used to return results to the client |
| `collation_connection` | Collation used for string expressions at the connection level |

To inspect the actual properties of an expression:

```sql
SELECT
    CHARSET('Tiếng Việt'),
    COLLATION('Tiếng Việt'),
    CHARSET(_utf8mb4'Đặng'),
    COLLATION(_utf8mb4'Đặng');
```

`CHARSET()` and `COLLATION()` help identify how MySQL interprets an expression. For existing columns, use `SHOW FULL COLUMNS` or `INFORMATION_SCHEMA.COLUMNS` to inspect the column's own charset/collation.

## 4. Understanding collation suffixes

In many MySQL 8.0 Unicode collations, names include suffixes indicating sensitivity:

| Suffix | Meaning |
|---|---|
| `ai` | Accent-insensitive: ignores certain accent differences per collation rules |
| `as` | Accent-sensitive: distinguishes accent differences |
| `ci` | Case-insensitive: does not distinguish uppercase/lowercase |
| `cs` | Case-sensitive: distinguishes uppercase/lowercase |
| `bin` | Compares by binary character/byte values per binary collation |

Common examples in MySQL 8.0:

- `utf8mb4_0900_ai_ci`: accent-insensitive and case-insensitive.
- `utf8mb4_0900_as_ci`: accent-sensitive, case-insensitive.
- `utf8mb4_0900_as_cs`: accent-sensitive and case-sensitive.
- `utf8mb4_0900_ai_cs`: accent-insensitive, case-sensitive.

The `0900` family is based on Unicode Collation Algorithm 9.0 and is available in MySQL 8.0 and later. For non-binary collations, if the name does not explicitly include `_ai` or `_as`, the `_ci` suffix implies accent-insensitive and `_cs` implies accent-sensitive. However, language tailoring rules and UCA versions can still alter outcomes; test on the exact server.

MySQL 8.0 includes UCA 9.0 Vietnamese collations such as `utf8mb4_vi_0900_ai_ci` (accent- and case-insensitive) and `utf8mb4_vi_0900_as_cs` (accent- and case-sensitive). Some versions also have the older `utf8mb4_vietnamese_ci` collation, which relies on older Unicode rules. In particular, UCA 4.0-based Unicode collations such as `utf8mb4_unicode_ci` have incomplete support for combining marks; this affects Vietnamese when an accented letter is represented as a precomposed character versus a base character plus combining marks. Prefer `vi_0900` collations where available and normalize Unicode consistently.

If you need accent-sensitive yet case-insensitive comparison, the general `utf8mb4_0900_as_ci` collation is worth testing; if you need Vietnamese tailoring and accept case sensitivity, you can test `utf8mb4_vi_0900_as_cs`. No single choice satisfies every combination of requirements. If the server lacks a suitable collation, consider building a dedicated sort key using a locale-aware library in the application layer.

## 5. Choosing collations by business goal

No single collation is optimal for all scenarios. Separate at least three questions: how sorting should work, how broad searches should be, and what the duplicate rules are.

| Business case | Typical requirement | Selection direction |
|---|---|---|
| Sorting Vietnamese names | Dictionary order suitable for Vietnamese, preserving accents | Test `utf8mb4_vi_0900_as_cs` on MySQL 8.0; verify letter ordering and real names |
| Searching accented names accurately | Case-insensitive but accent-sensitive | Accent-sensitive, case-insensitive collation such as `utf8mb4_0900_as_ci` if supported by version |
| Accent-insensitive name search | Allow omitting accents for broad lookup | Accent-insensitive collation or separate normalized search column; evaluate false positives |
| SKU/token codes | Usually requires exact comparison | Binary collation or explicit uppercase/lowercase normalization rules |
| Email/account | Depends on identity policy | Clearly define case, accent, and unique key rules; do not strip Vietnamese diacritics automatically |
| Searching long content | Keyword search, multiple words, and ranking | FULLTEXT or a dedicated search engine, after testing Vietnamese tokenization |

### 5.1. Person names: accent-sensitive but case-insensitive

For person names, accents should generally remain a meaningful distinction. You can pick an accent-sensitive, case-insensitive collation:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci NOT NULL,
    PRIMARY KEY (id),
    KEY idx_full_name (full_name)
) ENGINE=InnoDB;
```

This collation is an example for MySQL 8.0. If Vietnamese dictionary order is required, evaluate the Vietnamese collations available on your server and use one if it meets both the comparison and sorting needs of your application.

### 5.2. Accent-insensitive search

A simple approach is using an accent-insensitive collation for the search expression:

```sql
SELECT id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'Nguyen An' COLLATE utf8mb4_0900_ai_ci;
```

Results can include matching accented names per the collation's rules. However, for Vietnamese, ignoring accents can return many words with different meanings. If a user searches for `ma` and does not want `má`, `mà`, `mả`, `mã`, or `mạ`, do not use accent-insensitive matching for that requirement.

A cleaner design is keeping `full_name` intact and adding an application-generated normalized search column. Normalization rules must be explicitly defined: lowercasing, stripping only tone marks or all diacritics, how `đ` is handled, and how whitespace and Unicode forms are normalized. No single accent-stripping function fits every domain.

Model example:

```sql
CREATE TABLE customer_search (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(200)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL,
    search_key VARCHAR(200)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_search_key (search_key)
) ENGINE=InnoDB;
```

`search_key` is generated by the application per agreed rules and updated in the same transaction as the original name. Multiple search keys can be maintained if different modes are needed, such as accented search and unaccented search. Measure length after normalization to prevent column truncation.

### 5.3. Identifiers and unique keys

For SKU codes, record codes, or tokens, decide clearly whether uppercase and lowercase are equivalent. If codes must be distinguished strictly, use a binary collation or store them in an appropriate byte representation. If codes are case-insensitive, normalize to a canonical form (such as uppercase ASCII) at the application layer and place a unique index on the normalized value.

Do not use an accent-insensitive collation for every unique key. A unique index on a name column with an accent-insensitive collation can reject two names that business rules need to store separately. Before changing a collation, always check whether existing values would become duplicates under the new rules.

## 6. Sorting Vietnamese names in MySQL

### 6.1. ORDER BY uses the expression's collation

Example of sorting names:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name, id;
```

MySQL uses `full_name`'s collation to compare and sort. Adding `id` as a secondary sort key ensures deterministic ordering when multiple names share the same collation weight. This is especially important for pagination.

If you want to test another collation without altering the column definition:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name COLLATE utf8mb4_0900_as_ci, id;
```

This is useful for testing sort order, but do not overuse ad-hoc `COLLATE` across production queries. If the column is indexed under a different collation, changing collation in the expression can prevent the existing index from satisfying the sort order or filter condition directly.

### 6.2. Testing Vietnamese sort order

Create a small dataset containing easily confused cases:

```sql
CREATE TEMPORARY TABLE vietnamese_sort_test (
    value VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci
);

INSERT INTO vietnamese_sort_test (value) VALUES
    ('An'), ('Ân'), ('Ăn'), ('Ba'), ('Bà'), ('Bá'),
    ('Da'), ('Đa'), ('Dung'), ('Dũng'),
    ('Hoa'), ('Hòa'), ('Huệ'), ('Hương'), ('Ưng');

SELECT value
FROM vietnamese_sort_test
ORDER BY value;
```

Re-run the query with a Vietnamese collation if provided by the server:

```sql
SELECT value
FROM vietnamese_sort_test
ORDER BY value COLLATE utf8mb4_vi_0900_as_cs;
```

Compare the output against the business sort order required by the product. Your test dataset should cover special letters, tone marks, mixed case, equal-weight names, and strings with spaces. Do not check just a few common names and assume the collation fits.

### 6.3. Deterministic ordering during pagination

If two names are considered equal by the collation, `ORDER BY full_name` does not guarantee their relative order. Add a unique key:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name, id
LIMIT 50 OFFSET 100;
```

For large tables and deep pagination, you can use keyset pagination on the `(full_name, id)` tuple. Ensure the continuation predicate uses the exact same collation and ordering as `ORDER BY`; otherwise, rows may be skipped or duplicated.

## 7. Searching Vietnamese with LIKE and comparison operators

### 7.1. Exact search and prefix search

Searching with `=` or `LIKE` is governed by the expression's collation. Example:

```sql
-- Compare using the column's collation.
SELECT id, full_name
FROM customers
WHERE full_name = 'Nguyễn An';

-- Search by prefix.
SELECT id, full_name
FROM customers
WHERE full_name LIKE 'Nguyễn%';
```

If the column's collation is case-insensitive, case variants can match. If the collation is accent-insensitive, accented variants can match unaccented keywords. Test with real data before publishing search behavior to users.

### 7.2. Substring search and B-tree limitations

```sql
SELECT id, full_name
FROM customers
WHERE full_name LIKE '%An%';
```

A pattern starting with `%` usually cannot use a B-tree index to locate the start of a range, so it may scan many rows. With a prefix pattern such as `'Nguyễn%'`, MySQL can use an index if the collation, data type, and conditions permit.

Do not wrap columns in functions like `LOWER(full_name)` if you want to use a standard index, unless a corresponding functional index or generated column has been designed. It is better to choose a case-insensitive collation directly on the column when that reflects the business rule.

### 7.3. Whitespace and punctuation

Collations can differ in how they handle trailing spaces (PAD SPACE or NO PAD) and punctuation. Thus, `name = 'An'` can behave differently from an exact byte comparison. Check collation attributes and test cases such as `'An'`, `'An '`, and strings with multiple spaces when business logic requires exact matching.

If whitespace carries no meaning, normalize whitespace in the application layer before saving. Do not rely on implicit collation behavior to clean data.

## 8. Searching long content with FULLTEXT

For product descriptions, articles, or support content, keyword search can fit a FULLTEXT index:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (id),
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Searching in natural language mode:

```sql
SELECT
    id,
    title,
    MATCH(title, body) AGAINST ('cơ sở dữ liệu MySQL' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('cơ sở dữ liệu MySQL' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, id;
```

FULLTEXT is not the same as `LIKE`. The engine tokenizes content into tokens and applies stopwords, token length limits, parsers, and collation rules. Vietnamese has many compound words made of multiple space-separated syllables; searching for a phrase may not behave identically to searching for a single word. Test with real content and configure an appropriate parser.

FULLTEXT is useful for keyword search and relevance ranking, yet does not automatically solve typos, synonyms, domain-specific accent removal, or fuzzy matching. If type-ahead suggestions, spell correction, advanced Vietnamese word segmentation, or complex ranking are needed, consider a dedicated search service or an application-level NLP layer.

## 9. Collations and indexes

### 9.1. Indexes store order according to collation

A string index is organized according to the comparison rules of the collation at the time the index is created. If a query uses the same collation as the column/index, MySQL can use the index for matching comparisons, ranges, or ordering.

Example:

```sql
CREATE INDEX idx_customer_name
ON customers (full_name);

EXPLAIN
SELECT id, full_name
FROM customers
WHERE full_name LIKE 'Nguyễn%'
ORDER BY full_name, id;
```

Inspect `key`, `type`, `rows`, and `Extra` in the plan. An index is never guaranteed to be chosen; the optimizer weighs cost, selectivity, row count, and index column order.

### 9.2. Forcing COLLATE in a query can affect index usage

The following example changes collation directly inside the expression:

```sql
SELECT id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'nguyen an' COLLATE utf8mb4_0900_ai_ci;
```

If `full_name`'s index uses a different collation, MySQL may have to convert the expression and fail to use the index as desired. Verify with `EXPLAIN`. If this is a common query, consider a dedicated search column indexed with the appropriate collation instead of forcing collation in every SQL query.

### 9.3. Unique indexes depend on collation

Example of a login-name column with a unique index under a case-insensitive collation:

```sql
CREATE TABLE account_names (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_name VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_login_name (login_name)
) ENGINE=InnoDB;
```

Under this collation, two values differing only in letter case can be treated as duplicates. Switching to an accent-insensitive collation can expand the set of values treated as duplicates. This is a change in data rules, not just display formatting.

## 10. Testing collation behavior before applying

### 10.1. Comparing several Vietnamese pairs

```sql
SELECT
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_ai_ci AS ignores_diacritics,

    _utf8mb4'NGUYỄN' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci AS ignores_case,

    _utf8mb4'ma' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'má' COLLATE utf8mb4_0900_as_ci AS distinguishes_tone;
```

Results must be verified on your exact server and version. Expand the test set to include `a/ă/â`, `d/đ`, all tone marks, mixed case, whitespace, and combining Unicode characters.

### 10.2. Inspecting comparison weights

`WEIGHT_STRING()` can help investigate how a collation converts a string into comparison weights:

```sql
SELECT
    HEX(WEIGHT_STRING(_utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci)) AS w1,
    HEX(WEIGHT_STRING(_utf8mb4'NGUYỄN' COLLATE utf8mb4_0900_as_ci)) AS w2;
```

If two strings have identical weights under a collation, they can be treated as equal in comparisons using that collation. `WEIGHT_STRING()` is a diagnostic tool; do not expose it as a business API or persist these weights as stable keys across MySQL upgrades.

### 10.3. Checking duplicates before changing collation

Suppose you want to switch `login_name` to an accent- and case-insensitive collation. First, find groups of values that would become duplicates:

```sql
SELECT
    login_name COLLATE utf8mb4_0900_ai_ci AS normalized_value,
    COUNT(*) AS duplicate_count
FROM account_names
GROUP BY login_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

If the query returns rows, creating a unique index or changing the collation can fail. Decide how to handle each group based on business rules rather than deleting a record automatically.

## 11. Unicode normalization and Vietnamese data

A displayed character can be represented by a precomposed code point or by a base character combined with combining marks. For instance, an accented letter can arrive from a data source in NFC (precomposed form) or NFD (decomposed form). Some older MySQL UCA 4.0 collations do not handle combining marks completely; two visually equivalent representations can therefore compare differently.

Two strings can look identical yet have different bytes. To keep data consistent across web, mobile, APIs, and MySQL, normalize Unicode at the application boundary, typically choosing NFC for stored text data. This normalization differs from stripping accents: NFC preserves content and only standardizes equivalent Unicode representations.

Example in Java:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Do not arbitrarily apply NFD and strip all combining marks unless business logic calls for accent-insensitive search. That approach can lose distinctions between Vietnamese vowels. If generating a `search_key`, explicitly define transformation rules and keep the original string for display.

## 12. Application connections and character sets

Even when columns use `utf8mb4`, data can still be corrupted if the connection does not declare the right character set. Check:

```sql
SHOW VARIABLES LIKE 'character_set_client';
SHOW VARIABLES LIKE 'character_set_connection';
SHOW VARIABLES LIKE 'character_set_results';
SHOW VARIABLES LIKE 'collation_connection';
```

In a test session, you can set:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_as_ci;
```

`SET NAMES` sets client, connection, and results character sets and connection collation for the session. In applications, configure the charset via the driver/connector so it is initialized when opening connections and avoid repeating it manually on every request.

Example with the mysql client:

```bash
mysql --default-character-set=utf8mb4 -h 127.0.0.1 -u app_user -p shop
```

When inspecting stored data, use `HEX()` alongside `CHAR_LENGTH()` and `LENGTH()`:

```sql
SELECT
    full_name,
    HEX(full_name) AS stored_bytes,
    CHAR_LENGTH(full_name) AS character_count,
    LENGTH(full_name) AS byte_count
FROM customers
LIMIT 10;
```

`CHAR_LENGTH()` counts characters according to the character set; `LENGTH()` counts bytes. With `utf8mb4`, a character can take from one to four bytes. The results help detect improperly encoded or truncated strings.

## 13. Safe collation conversion

Changing a table's collation can affect sort order, search results, unique indexes, and query plans. Before making changes:

1. **Record the current state:** MySQL version, and charset/collation for server, database, table, column, and connection.
2. **Define requirements:** which columns need Vietnamese sorting, which need accent-insensitive search, and which need exact comparison.
3. **Inspect data:** check for corrupted bytes, strings with differing Unicode forms, trailing spaces, and value groups that could collide under the new collation.
4. **Test on a copy:** run search queries, sorting, unique checks, and `EXPLAIN` with the target collation.
5. **Evaluate indexes:** changing collation may require rebuilding indexes; check DDL duration, storage, locks, and online DDL support for your version/engine.
6. **Plan the rollout:** back up, pick an appropriate window, monitor application errors, and prepare a rollback plan.
7. **Verify post-change:** check DDL, Vietnamese data, search results, ordering, unique constraints, and performance.

Changing a charset and changing a collation are two separate actions. `CONVERT TO CHARACTER SET` can convert data and column types; `COLLATE` selects comparison rules. Read the DDL and verify source encoding before converting to avoid turning mojibake into validly encoded yet corrupted text.

Example of changing a table's default charset/collation and converting string columns:

```sql
ALTER TABLE customers
CONVERT TO CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_as_ci;
```

This command can alter string column types/lengths and rebuild data/indexes. Do not run it directly in production without evaluating table size, index limits, lock duration, and the collation's impact on unique keys.

## 14. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Vietnamese turns into `?` or garbled characters | Wrong client/connection charset, or data replaced before storage | Check charsets at client, connection, and column; inspect `HEX()` |
| `Illegal mix of collations` error | String expression uses incompatible collations | Identify each expression's collation; unify schema/connection or force `COLLATE` intentionally |
| Searching `Nguyen` does not find `Nguyễn` | Active collation is accent-sensitive | Pick a collation or search key column for accent-insensitive search per requirements |
| Searching `ma` returns too many results | Accent-insensitive collation merges distinct words | Use exact accented search or separate broad search mode |
| Name sorting does not match expected dictionary order | General collation lacks suitable Vietnamese tailoring | Test Vietnamese collations, sample data, or use an application sort key |
| Unique index creation hits duplicates | New collation treats byte-different strings as equal | Group duplicates by target collation and resolve data before creating index |
| Queries slow down after adding COLLATE | Collation conversion prevents direct index usage | Inspect `EXPLAIN`, consider a suitable search key column/index |
| Results differ across environments | Different MySQL versions, collations, or Unicode data | Record versions, check `SHOW COLLATION`, and run the same test suite |

## 15. Checklist for choosing Vietnamese sorting and searching rules

- Are database, table, column, and connection character sets consistently `utf8mb4`?
- Is Vietnamese dictionary order needed, or is general Unicode order sufficient?
- Should searches distinguish tone marks and the letters `ă`, `â`, `đ`, `ê`, `ô`, `ơ`, `ư`?
- Is case sensitivity required?
- Is accent-insensitive search needed as a separate mode?
- Could the search rule collapse distinct words into the same result?
- Could unique keys hit conflicts when changing collations?
- Are columns indexed with the right collation, and do queries use the index?
- Does FULLTEXT have tokenization and stopwords suited to real Vietnamese content?
- Does the application normalize Unicode NFC and whitespace per policy?
- Have real data, execution plans, and migrations been tested on a copy?

## Conclusion

To sort and search Vietnamese properly in MySQL, separate requirements for dictionary ordering, accent sensitivity, case sensitivity, accent-insensitive lookup, and duplicate checks. Use `utf8mb4` for Unicode data; pick a collation verified on your server version; retain the original string and create a dedicated search key if accent stripping is needed; and inspect indexes and unique constraints before making changes. For person names, products, and identifiers, comparison rules must reflect concrete business semantics rather than applying one generic collation to every column.
