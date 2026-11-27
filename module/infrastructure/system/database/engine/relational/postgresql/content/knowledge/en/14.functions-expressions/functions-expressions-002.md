# String Functions, Concatenation, and Whitespace Handling in PostgreSQL

String data appears in nearly every application: customer names, emails, phone numbers, addresses, product codes, notes, display labels, and report contents. However, real-world data is rarely as clean as textbook examples. A name may contain leading/trailing whitespace, an email may contain uppercase letters and spaces, a field may be `NULL` instead of an empty string, and a Vietnamese string may occupy more bytes than the number of characters the user sees.

PostgreSQL provides many operators and functions for working with strings: **`||`**, **`concat()`**, **`concat_ws()`**, **`trim()`**, **`btrim()`**, **`ltrim()`**, **`rtrim()`**, **`length()`**, **`lower()`**, **`upper()`**, **`substring()`**, **`replace()`**, **`regexp_replace()`**, **`string_agg()`**, and many more tools.

This lesson belongs to the **Functions and Expressions** chapter of the PostgreSQL module. We will learn how to combine these functions to build display strings, normalize data, detect abnormal whitespace, split/join components, aggregate multiple rows into one string, and design queries with appropriate performance. Each example also clarifies **`NULL` semantics**, the difference between an empty string and a missing value, as well as pitfalls when working with Vietnamese and Unicode.

Key takeaway: **display strings, comparison keys, and raw data are not necessarily the same thing**. When cleaning or concatenating strings, determine the purpose before transforming values.

## 1. Common String Types in PostgreSQL

PostgreSQL has the following basic string types:

| Type | Meaning | Use Case |
|---|---|---|
| `text` | Variable-length string without a declared length limit | Names, descriptions, content |
| `varchar(n)` | Variable-length string limited to at most `n` characters | Data requiring a schema-level length limit |
| `varchar` | Variable-length string without a specified limit | Similar to `text` in many cases |
| `char(n)` / `character(n)` | Fixed-length string, blank-padded | Legacy data or protocols strictly requiring fixed width |

Example:

~~~sql
CREATE TABLE string_types_demo (
    description TEXT,
    short_code VARCHAR(20),
    fixed_code CHAR(5)
);
~~~

### 1.1. TEXT Does Not Mean Slower Than VARCHAR

In PostgreSQL, `text` and unbounded `varchar` generally have equivalent storage/performance behavior for many applications. Do not blindly set `varchar(255)` for every column just out of habit from another DBMS.

If the business truly requires a length limit, you can use `varchar(n)` or a constraint:

~~~sql
CREATE TABLE display_labels (
    label_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label_text TEXT NOT NULL,
    CONSTRAINT chk_label_length
        CHECK (char_length(label_text) <= 120)
);
~~~

The limit of 120 here is a business example, not a default PostgreSQL technical limit.

### 1.2. Notes on CHAR(n) and Trailing Space Padding

`char(n)` is padded with spaces to the declared length and has special rules during comparisons and casts; trailing padding spaces are generally not treated the same as meaningful spaces in `text`.

Therefore, if the application needs to preserve the **exact text entered by the user**, `text` or `varchar` is usually better suited than `char(n)`. Do not choose `char(10)` just to "align codes."

### 1.3. Empty String and NULL Are Two Different Values

~~~sql
SELECT
    ''::text IS NULL AS empty_is_null,
    NULL::text IS NULL AS null_is_null,
    char_length(''::text) AS empty_length;
~~~

Result:

| empty_is_null | null_is_null | empty_length |
|---|---|---:|
| false | true | 0 |

An empty string `''` has length 0 but is **not NULL**. A string `'   '` has three space characters and is also not NULL.

If the system needs to distinguish "not filled in", "intentionally left blank", and "whitespace only", reflect that rule in the API and schema rather than relying on one function to cover every case.

## 2. Concatenating Strings with the || Operator

The **`||`** operator is a direct way to concatenate strings, often easy to read with a few fixed components:

~~~sql
SELECT
    'Postgre' || 'SQL' AS database_name,
    'Hello, ' || 'An' AS greeting;
~~~

Result:

~~~text
database_name = PostgreSQL
greeting      = Hello, An
~~~

It preserves every character in each operand. PostgreSQL **does not automatically insert spaces**:

~~~sql
SELECT 'Nguyễn' || 'Văn' || 'An' AS no_separator;
~~~

The result is `NguyễnVănAn`.

To have spacing, you must add it explicitly:

~~~sql
SELECT
    'Nguyễn' || ' ' || 'Văn' || ' ' || 'An'
    AS full_name;
~~~

### 2.1. Using Deliberate Separators

~~~sql
SELECT
    'ORD-' || '000123' AS order_code,
    'Hanoi' || ', ' || 'Vietnam' AS location_label,
    'key=' || 'value' AS pair_label;
~~~

The spaces in `', '`, `' '`, or `' - '` are simply characters you explicitly asked to concatenate; the operator does not understand address formatting on its own.

### 2.2. Concatenating Non-Text Values

If the data has numeric or date types, choose an explicit way to convert to string:

~~~sql
SELECT
    'Order #' || 123::text AS order_label,
    'Total: ' || 150000::text AS amount_label;
~~~

There are operator overloads allowing `text` to be concatenated with non-string types in appropriate contexts, but **explicit casting** is usually easier to understand when writing examples or stable SQL APIs.

To format currency, dates, or timestamps in a controlled way, use `to_char()` or the presentation layer instead of defaulting to casting to `text`:

~~~sql
SELECT
    'Date: ' || to_char(
        DATE '2026-11-14',
        'DD/MM/YYYY'
    ) AS formatted_day;
~~~

### 2.3. NULL Propagates Through ||

A critically important point:

~~~sql
SELECT
    'Hello ' || NULL::text AS greeting_with_null;
~~~

The result is `NULL`, **not** the string "Hello ".

Similarly:

~~~sql
SELECT
    'An' || ' ' || NULL::text AS full_name;
~~~

The entire expression returns NULL.

This frequently breaks display labels when a middle name, city, or secondary address line is optional.

## 3. CONCAT(): Concatenating Multiple Values and Ignoring NULL

PostgreSQL provides the `concat()` function:

~~~sql
SELECT
    concat('Postgre', 'SQL') AS db_name,
    concat('Order ', 123, ' - ', DATE '2026-11-14')
        AS order_description;
~~~

`concat()` can take multiple arguments and convert compatible values to string form for concatenation.

### 3.1. Difference Between CONCAT and ||

~~~sql
SELECT
    'Hello ' || NULL::text AS by_operator,
    concat('Hello ', NULL::text) AS by_function;
~~~

Meaning:

| Expression | Result |
|---|---|
| `'Hello ' || NULL::text` | NULL |
| `concat('Hello ', NULL::text)` | `'Hello '` |

In PostgreSQL, `concat()` **ignores NULL arguments**. By contrast, `||` typically returns NULL when one operand is NULL.

### 3.2. CONCAT Does Not Automatically Add Spaces

~~~sql
SELECT concat('Nguyễn', 'Văn', 'An') AS result;
~~~

The result is still `NguyễnVănAn`.

To include spaces:

~~~sql
SELECT concat('Nguyễn', ' ', 'Văn', ' ', 'An');
~~~

Or use `concat_ws()` in the next section when there are multiple optional parts.

### 3.3. NULL and Empty Strings in CONCAT

The function skips `NULL`, but an **empty string** is still a valid non-NULL argument, even though it adds no characters:

~~~sql
SELECT
    concat('A', NULL::text, 'B') AS skip_null,
    concat('A', ''::text, 'B') AS empty_component;
~~~

Both display `AB`, yet the input data has different meanings. If you need to know which components the user actually entered, do not use the concatenated label as the source of truth.

### 3.4. Be Careful When CONCAT Hides Missing Data

If the system requires a customer code but the code is NULL, `concat('KH-', customer_code)` can produce the label `KH-`. It **does not signal that required data is missing**.

Therefore, `concat()` is good for presentation, not a substitute for `NOT NULL`, `CHECK`, or application validation.

## 4. CONCAT_WS(): Concatenating with a Separator

`concat_ws(separator, value1, value2, ...)` stands for *concatenate with separator*.

~~~sql
SELECT concat_ws(
    ' ',
    'Nguyễn',
    'Văn',
    'An'
) AS full_name;
~~~

Result: `Nguyễn Văn An`.

### 4.1. Automatically Inserting Separators Between Non-NULL Arguments

~~~sql
SELECT
    concat_ws(', ', 'Hanoi', 'Vietnam')
        AS address_label,
    concat_ws(' / ', '2026', '11', '14')
        AS formatted_parts;
~~~

Corresponding results:

~~~text
Hanoi, Vietnam
2026 / 11 / 14
~~~

### 4.2. Skips NULL but Does Not Automatically Skip Empty Strings

~~~sql
SELECT
    concat_ws(' - ', 'A', NULL::text, 'C') AS skip_null,
    concat_ws(' - ', 'A', ''::text, 'C') AS keep_empty;
~~~

Result:

| skip_null | keep_empty |
|---|---|
| `A - C` | `A -  - C` |

Difference:

- `NULL`: contributes no component and produces no separator for that component.
- `''`: is still a **non-NULL** component, so separators appear before/after it.

If a form submits empty strings for optional fields, decide whether to convert them to NULL before concatenating.

### 4.3. Combining NULLIF to Omit Empty Strings

~~~sql
SELECT concat_ws(
    ', ',
    NULLIF(btrim(' 123 Nguyễn Huệ '), ''),
    NULLIF(btrim('   '), ''),
    NULLIF(btrim('Ho Chi Minh City'), '')
) AS address_label;
~~~

Meaningful result:

~~~text
123 Nguyễn Huệ, Ho Chi Minh City
~~~

A useful pattern:

~~~sql
concat_ws(
    ', ',
    NULLIF(btrim(address_line1), ''),
    NULLIF(btrim(address_line2), ''),
    NULLIF(btrim(city), '')
)
~~~

The example above only runs when the columns `address_line1`, `address_line2`, and `city` exist in the query.

### 4.4. When Separator Is NULL

`concat_ws()` requires a meaningful separator. In PostgreSQL, a NULL separator causes the result to return NULL; do not assume it behaves like an empty string by default.

~~~sql
SELECT concat_ws(
    NULL::text,
    'A',
    'B'
) AS unknown_separator;
~~~

Choose an explicit separator matching the desired format.

### 4.5. When All Components Are Missing

When all components after the separator are NULL, you can get an empty string instead of a meaningful label. If you want to represent "no label" as NULL:

~~~sql
SELECT NULLIF(
    concat_ws(
        ', ',
        NULL::text,
        NULL::text
    ),
    ''
) AS optional_label;
~~~

Converting an empty-string result to NULL should be an **intentional business rule**.

## 5. Quick Comparison of ||, CONCAT, and CONCAT_WS

| Feature | `||` | `concat()` | `concat_ws()` |
|---|---|---|---|
| Purpose | Join operands | Join multiple arguments | Join with separator |
| Automatic separator | No | No | Yes |
| NULL in component | Usually makes result NULL | Ignores NULL | Ignores NULL in components |
| NULL in separator | No separate parameter | No separate parameter | Result is NULL |
| Empty string | Preserved | Preserved | Empty component still affects separators |
| Good fit | Structured prefix/suffix | Simple label assembly | Names/addresses with optional parts |

### 5.1. Which One Should You Choose?

- Use `||` when every part is required and you want NULL to propagate explicitly.
- Use `concat()` when joining multiple parts and intentionally skipping NULLs.
- Use `concat_ws()` when inserting a separator between optional parts.

For example, a multi-part address usually fits `concat_ws(', ', ...)`; a SKU code assembled from mandatory parts may fit `||` along with constraints on those parts.

## 6. Whitespace in Real-World Data

"Whitespace" is not just a single character type. Some examples:

| Kind | Meaning | Example |
|---|---|---|
| Regular space | Space character U+0020 | Between two words |
| Tab | U+0009 | Text copied from a spreadsheet |
| Newline | LF or CR/LF | Line break |
| Non-breaking space | U+00A0 | HTML content, copied text |
| Other Unicode characters | Various spaces and formatting characters | Content from external documents |

Therefore, "remove whitespace" should be clarified as:

1. Remove only leading/trailing spaces?
2. Also remove leading/trailing tabs and newlines?
3. Collapse multiple internal spaces into a single space?
4. Preserve meaningful line breaks within content?
5. Handle non-breaking spaces?
6. Preserve Unicode characters in personal names and addresses?

Different answers lead to **different transformations**.

### 6.1. Leading/Trailing Whitespace vs. Between Words

~~~text
"   Nguyễn   Văn An   "
 ^^^        ^^^     ^^^
 lead    internal  trail
~~~

`trim()` or `btrim()` normally handles **leading/trailing edges**, without automatically collapsing spaces between words.

## 7. TRIM(): Removing Characters from Both Ends of a String

Standard SQL syntax:

~~~sql
TRIM([LEADING | TRAILING | BOTH] [characters] FROM string)
~~~

Basic example:

~~~sql
SELECT
    trim('   PostgreSQL   ') AS normalized;
~~~

Result: `PostgreSQL`.

### 7.1. BOTH, LEADING, TRAILING

~~~sql
SELECT
    trim(BOTH FROM '  ABC  ') AS both_sides,
    trim(LEADING FROM '  ABC  ') AS left_only,
    trim(TRAILING FROM '  ABC  ') AS right_only;
~~~

Meaningful results:

| both_sides | left_only | right_only |
|---|---|---|
| `ABC` | `ABC  ` | `  ABC` |

Spaces in displayed columns may not be obvious if a SQL client formats output; you can combine `quote_nullable()` or check `length()` to observe accurately.

### 7.2. Specifying Characters to Remove

~~~sql
SELECT
    trim(BOTH '-' FROM '---ABC---') AS without_hyphens,
    trim(LEADING '0' FROM '000123') AS no_leading_zeroes;
~~~

Results are `ABC` and `123`, respectively.

### 7.3. TRIM Does Not Search and Delete Content in the Middle

~~~sql
SELECT trim(BOTH '-' FROM '--A-B--') AS result;
~~~

The result is `A-B`, because the `-` inside is not at the edges.

### 7.4. Caution When Stripping Leading Zeros from Identifiers

Example:

~~~sql
SELECT trim(LEADING '0' FROM '000123') AS altered_code;
~~~

Result `123`. If `000123` is a customer code where leading zeros **carry meaning**, this operation alters the identifier.

**Do not trim characters just to "clean up" if those characters are part of business data.**

## 8. BTRIM(), LTRIM(), and RTRIM()

PostgreSQL has three commonly used functions:

- `btrim(text [, characters])`: removes characters from both ends.
- `ltrim(text [, characters])`: removes characters from the left end.
- `rtrim(text [, characters])`: removes characters from the right end.

Example:

~~~sql
SELECT
    btrim('  ABC  ') AS trimmed,
    ltrim('  ABC  ') AS left_trimmed,
    rtrim('  ABC  ') AS right_trimmed;
~~~

### 8.1. Specifying a Character Set

~~~sql
SELECT
    btrim('xy--Hello--yx', 'xy-') AS both,
    ltrim('00ABC00', '0') AS left_zeroes,
    rtrim('00ABC00', '0') AS right_zeroes;
~~~

Result:

| both | left_zeroes | right_zeroes |
|---|---|---|
| `Hello` | `ABC00` | `00ABC` |

### 8.2. The characters Argument Is a Set of Characters, Not a Substring

A common pitfall:

~~~sql
SELECT btrim('abcXYZcba', 'abc') AS result;
~~~

The result is `XYZ` because any contiguous `a`, `b`, or `c` characters at either end are stripped.

The function **does not require the edge to contain the exact sequence "abc" in order**.

If you need to strip a specific prefix/suffix conditionally, use `starts_with()`, `left()`, `right()`, `substring()`, or an appropriate regex instead of misusing `trim(..., characters)`.

### 8.3. Example of Stripping Edge Delimiters

~~~sql
SELECT
    btrim('///api/v1/customers///', '/') AS route_body;
~~~

Result: `api/v1/customers`. The `/` characters in the middle are kept.

For real URLs/paths, distinguish structurally meaningful slashes before normalizing. A single `btrim` call is not a URL parser.

## 9. Default TRIM Does Not Remove Every Kind of Whitespace

In typical usage, `trim()`, `btrim()`, `ltrim()`, and `rtrim()` without a character-set argument remove **ordinary spaces** at the edges, not automatically every Unicode character classified as whitespace.

Checking with tabs:

~~~sql
SELECT
    char_length(E'\tABC\t') AS original_length,
    char_length(btrim(E'\tABC\t')) AS default_trim_length,
    char_length(btrim(E'\tABC\t', E' \t\n\r'))
        AS explicit_trim_length;
~~~

Meaning:

- The initial string has tabs at both ends.
- Default `btrim(...)` does not necessarily remove tabs.
- `btrim(..., E' \t\n\r')` is explicitly instructed to strip space, tab, LF, and CR at the edges.

### 9.1. E'' Is an Escape String Literal

In PostgreSQL:

~~~sql
SELECT
    E'\t' AS tab_character,
    E'\n' AS newline_character;
~~~

`E'...'` lets you represent escapes like `\t` and `\n` explicitly. For external user input, pass typed parameters rather than building escaped literals manually.

### 9.2. Using btrim with an Explicit Character Set

~~~sql
SELECT
    btrim(
        E'\t \n  Hello \r\n ',
        E' \t\n\r'
    ) AS cleaned_edges;
~~~

Meaningful result: `Hello`.

However, if this is multi-line text where leading/trailing newlines carry meaning, removing them may be undesirable. Not every `TEXT` column is a "single-line label."

## 10. Non-Breaking Space and Unicode Whitespace

Data copied from HTML, office documents, or chat apps can contain a **non-breaking space (NBSP, U+00A0)**. It looks nearly identical to an ordinary space, but it is a different character.

In a UTF-8 database, you can produce NBSP using:

~~~sql
SELECT chr(160) AS nbsp_character;
~~~

An example:

~~~sql
SELECT
    char_length('A' || chr(160) || 'B') AS length_in_characters,
    octet_length('A' || chr(160) || 'B') AS length_in_bytes;
~~~

On a UTF-8 database, the string has 3 characters, yet NBSP occupies more bytes than an ASCII space.

### 10.1. Converting NBSP to Space When Business Rules Allow

~~~sql
SELECT
    replace(
        '  Nguyễn' || chr(160) || 'Văn  ',
        chr(160),
        ' '
    ) AS normalized_spaces;
~~~

If you want to strip outer spaces after replacing:

~~~sql
SELECT
    btrim(
        replace(
            '  Nguyễn' || chr(160) || 'Văn  ',
            chr(160),
            ' '
        )
    ) AS display_name;
~~~

Result: `Nguyễn Văn`.

### 10.2. Should You Replace All Unicode Whitespace?

Not always. Some whitespace characters have linguistic, typographic, or formatting meaning; some invisible formatting characters are **not even part of ordinary whitespace**.

Blindly "deleting every invisible character" can break international text, proper names, or data needed for reconciliation. Define the list of characters to normalize per field: email, name, address, description, or free-form content.

### 10.3. Regex Whitespace Depends on Character Classes and Environment

PostgreSQL supports POSIX character classes such as `[[:space:]]` in regular expressions. The set of recognized characters can be influenced by character classification/collation and version. **Do not assume this regex always handles every rare Unicode character** without an agreed data policy.

For a known NBSP, `replace(value, chr(160), ' ')` is a more explicit and understandable transformation.

## 11. Collapsing Whitespace Between Words with REGEXP_REPLACE

`trim` only handles edges, leaving internal whitespace intact:

~~~sql
SELECT btrim('  Trần   Thị   Bình  ') AS still_has_multiple_spaces;
~~~

Result: `Trần   Thị   Bình`.

To replace each consecutive run of matching whitespace characters with a single space:

~~~sql
SELECT regexp_replace(
    '  Trần   Thị   Bình  ',
    '[[:space:]]+',
    ' ',
    'g'
) AS normalized_runs;
~~~

### 11.1. Why Use the 'g' Flag?

By default, `regexp_replace` replaces only the first match in its standard signature; the `'g'` flag requests replacing **all matches**.

~~~sql
SELECT
    regexp_replace('A   B   C', '[[:space:]]+', ' ')
        AS first_match_only,
    regexp_replace('A   B   C', '[[:space:]]+', ' ', 'g')
        AS all_matches;
~~~

Only the form with `'g'` ensures whitespace runs throughout the entire string are replaced as intended.

### 11.2. Combining Regex and Trim

~~~sql
SELECT btrim(
    regexp_replace(
        '  Trần   Thị   Bình  ',
        '[[:space:]]+',
        ' ',
        'g'
    )
) AS normalized_full_name;
~~~

Result: `Trần Thị Bình`.

Meaningful workflow:

1. Each whitespace run is replaced with a single space.
2. Remaining leading/trailing spaces are removed by `btrim`.

### 11.3. Regex Is Not the Default Choice for Every Field

In product descriptions or multi-paragraph notes, multiple newlines preserve content structure. Collapsing all whitespace to one space destroys formatting.

This regex pattern fits **single-line labels** with a clear policy, not every `TEXT` column.

## 12. LENGTH, CHAR_LENGTH, and OCTET_LENGTH

To measure how long a string is, distinguish **character count** from **byte count**.

~~~sql
SELECT
    length('PostgreSQL') AS length_1,
    char_length('PostgreSQL') AS length_2,
    octet_length('PostgreSQL') AS byte_length;
~~~

For the ASCII string `PostgreSQL`, all three are 10.

### 12.1. With Vietnamese, Characters Can Occupy Multiple Bytes

~~~sql
SELECT
    char_length('Việt') AS characters,
    octet_length('Việt') AS bytes,
    bit_length('Việt') AS bits;
~~~

In a UTF-8 database, the string `Việt` using precomposed `ệ` typically has:

| characters | bytes | bits |
|---:|---:|---:|
| 4 | 6 | 48 |

`V`, `i`, and `t` are ASCII characters at 1 byte each; `ệ` is a Unicode character that can occupy 3 bytes in UTF-8.

### 12.2. LENGTH and CHAR_LENGTH Mean "Character Count"

On ordinary `text` or `varchar` columns:

~~~sql
SELECT
    length('Hà Nội') AS by_length,
    char_length('Hà Nội') AS by_char_length;
~~~

Both measure length in characters of the string, not in storage bytes.

### 12.3. One User-Perceived Character Can Consist of Multiple Code Points

Unicode allows the same accented letter to be represented as:

- A single precomposed code point.
- A base letter plus one or more combining marks.

Illustrative example:

~~~sql
SELECT
    char_length('é') AS precomposed,
    char_length(U&'e\0301') AS combining_sequence;
~~~

Visually, the two representations can look identical, yet the code point counts can be 1 and 2. `char_length()` is not a complete counter of user-perceived characters (*grapheme clusters*).

### 12.4. UI Limits and Payload Bytes

If an API needs to enforce a 120-character input limit, `char_length()` may be more appropriate than `octet_length()` in many cases; however, with complex Unicode, "120 user-visible characters" needs additional handling in the application.

If a system limits byte size when sending over an external protocol, `octet_length()` has its own distinct role. Do not substitute the two functions arbitrarily.

## 13. Detecting Empty Strings and Whitespace-Only Strings

Three basic cases:

~~~sql
SELECT
    NULL::text AS missing_value,
    ''::text AS empty_value,
    '   '::text AS whitespace_value;
~~~

### 13.1. Checking Non-Empty After Trim

~~~sql
SELECT
    btrim('   ') = '' AS only_spaces,
    btrim('  An  ') = '' AS nonblank_name;
~~~

Results: `true` and `false`.

### 13.2. NULLIF to Convert Empty Strings to NULL

~~~sql
SELECT
    NULLIF(btrim('   '), '') AS missing_after_trim,
    NULLIF(btrim(' An '), '') AS name_after_trim;
~~~

Meaning:

- `NULLIF(btrim('   '), '')` returns NULL.
- `NULLIF(btrim(' An '), '')` returns `An`.

This pattern is very useful before `concat_ws()`, before storing a value into an optional column, or when marking fields where the user provided no meaningful input.

### 13.3. NULLIF Does Not Normalize All Unicode Whitespace Automatically

If a string consists only of NBSPs, default `btrim` may not strip that character. A normalization policy must explicitly account for character types and data sources.

### 13.4. Row-Level Constraint

Example of a required name column:

~~~sql
CREATE TABLE people_names (
    person_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    CONSTRAINT chk_full_name_not_blank
        CHECK (btrim(full_name) <> '')
);
~~~

This constraint prevents NULL names via `NOT NULL` and prevents strings made entirely of ordinary spaces via `CHECK`. If data must also block tabs or NBSPs at the edges, expand the rule accordingly.

The application should still validate upfront and show messages such as "Name must not be blank."

## 14. LOWER, UPPER, and INITCAP

PostgreSQL supports case transformations:

~~~sql
SELECT
    lower('PostgreSQL') AS lower_case,
    upper('PostgreSQL') AS upper_case,
    initcap('hello world') AS title_case;
~~~

With ASCII data, the results are typically:

~~~text
postgresql
POSTGRESQL
Hello World
~~~

### 14.1. LOWER for Comparison Keys

When searching emails under a product-defined case-insensitive matching rule:

~~~sql
SELECT lower(btrim('  An@Example.COM  ')) AS normalized_email_key;
~~~

The result is typically `an@example.com`.

However, note: email addresses have complex real-world rules, and case handling in the local part cannot be mechanically standardized across every system. **Define the product's canonicalization rule** before using `lower()` as a unique key.

### 14.2. LOWER/UPPER Can Depend on Locale/Collation

Transforming accented letters and certain languages does not always follow ASCII rules. Results can depend on locale/collation configuration as well as the PostgreSQL or collation library version.

Do not assume "one uppercase character always maps to exactly one lowercase character" in every language. When designing cross-system normalization keys, align Unicode handling, collation, and application processing.

### 14.3. INITCAP Is Not a Universal Name Normalizer

~~~sql
SELECT initcap('nguyễn văn an') AS display_guess;
~~~

The function can be useful for some labels, but proper names, acronyms, company names, and different languages have complex capitalization rules. Do not bulk-rewrite real names using `initcap()` without clear requirements and policy.

### 14.4. Do Not Overwrite Raw Data When You Only Need Search

You can store verified personal names as entered and generate comparison keys in queries/indexes. Transforming for **comparison** does not have to mean overwriting user-entered values.

## 15. Unicode Normalization: Two Identical-Looking Strings Can Still Differ

Two representations of an accented character can render identically while containing different sequences of code points. This affects:

- String comparison.
- Exact search.
- Uniqueness.
- Length calculation.
- Hash/checksum.
- Synchronization between application and database.

PostgreSQL provides the `normalize()` function for Unicode normalization on databases using UTF-8 encoding, in supported versions.

~~~sql
SELECT
    normalize(U&'e\0301', NFC) AS normalized_nfc,
    normalize('é', NFD) AS normalized_nfd;
~~~

`NFC` moves toward precomposed canonical forms where possible; `NFD` moves toward canonically decomposed forms.

### 15.1. NFC Does Not Strip Vietnamese Accents

Normalization does not mean removing diacritics. Standard Unicode normalization forms **preserve accented characters' meaning** while reorganizing code point representation.

If you need accent-insensitive search, that is a different requirement from normalization and requires dedicated search/collation design.

### 15.2. Do Not Apply NFKC Blindly

Compatibility forms like `NFKC` can alter the representation of certain compatible characters. They are useful in some comparison-key problems, but can lose distinctions that raw data needs to preserve.

Distinguish between:

~~~text
Raw text:
    data as entered or displayed

Comparison key:
    data normalized according to search/uniqueness rules
~~~

You should not necessarily overwrite raw text with the comparison key.

## 16. SUBSTRING and SUBSTR: Extracting Part of a String

PostgreSQL supports the syntax:

~~~sql
SELECT
    substring('PostgreSQL' FROM 1 FOR 4) AS prefix,
    substring('PostgreSQL' FROM 5 FOR 3) AS middle;
~~~

Result:

| prefix | middle |
|---|---|
| `Post` | `gre` |

### 16.1. Starting Position Is 1-Based

In PostgreSQL SQL, the first character position is **1**, not 0 like array indexes in many programming languages.

~~~sql
SELECT substr('ABCDEFG', 2, 3) AS fragment;
~~~

Result: `BCD`.

### 16.2. Slicing Does Not Validate a Code

Suppose a product code has the form `SKU-12345`:

~~~sql
SELECT substring('SKU-12345' FROM 5) AS code_part;
~~~

Result: `12345`.

However, if the input is `WRONG-12345`, taking a substring from a fixed offset does not verify that the prefix is valid. Validate code structure if it is critical data, rather than blindly slicing and trusting the output.

### 16.3. With Unicode, Slicing Characters Differs from Slicing Bytes

`substring()` on `text` operates on character positions rather than arbitrary UTF-8 bytes. Still, slicing by code point can split a grapheme cluster consisting of a base letter and combining marks if not handled properly at the presentation layer.

## 17. LEFT and RIGHT: Taking the Start or End of a String

~~~sql
SELECT
    left('PostgreSQL', 4) AS first_four,
    right('PostgreSQL', 3) AS last_three;
~~~

Results: `Post` and `SQL`.

### 17.1. Extracting Display Parts from a Code

~~~sql
SELECT
    left('ORD-2026-000123', 3) AS code_prefix,
    right('ORD-2026-000123', 6) AS serial;
~~~

Results: `ORD` and `000123`.

If codes vary in length or structure, fixed-length slicing from the ends can fail. For business codes, use an explicit parser/constraint.

### 17.2. Do Not Use RIGHT to Take "n Visible Letters" in Every Language

If a string contains multi-code-point Unicode sequences, `right(text, n)` slices on code point boundaries rather than necessarily on grapheme boundaries. This is the same issue as with `substring()`.

## 18. POSITION and STRPOS: Finding Substring Position

~~~sql
SELECT
    position('gre' IN 'PostgreSQL') AS pos_1,
    strpos('PostgreSQL', 'gre') AS pos_2;
~~~

Both return starting position **5**.

### 18.1. When Not Found

~~~sql
SELECT
    position('XYZ' IN 'PostgreSQL') AS missing_pos;
~~~

The result is `0`, not NULL.

Therefore:

~~~sql
SELECT
    strpos('alpha@example.com', '@') > 0
        AS contains_at_symbol;
~~~

returns true. However, having an `@` character **does not prove an email is valid**.

### 18.2. Finding Position Is Not Fuzzy Search

`strpos()` searches for a literal substring under exact matching conditions; it does not strip accents, fold case, or fix typos.

If you need flexible search, look at `ILIKE`, regex, full-text search, or trigram indexing depending on the problem.

## 19. REPLACE: Replacing Substrings Literally

`replace(source, from, to)` replaces occurrences of the **substring** `from` with `to`.

~~~sql
SELECT
    replace('a-b-c', '-', '/') AS changed_separator,
    replace('Hello Hello', 'Hello', 'Hi')
        AS changed_words;
~~~

Results:

~~~text
a/b/c
Hi Hi
~~~

### 19.1. REPLACE Does Not Use Regex

~~~sql
SELECT replace('a   b', '  ', ' ') AS result;
~~~

This merely replaces two literal spaces with one space. It has no concept of "any whitespace sequence of arbitrary length" like regex does.

### 19.2. Removing a Substring

~~~sql
SELECT
    replace('ABC-123-XYZ', '-', '') AS no_hyphens;
~~~

Result: `ABC123XYZ`.

If hyphens are part of the data's identity, removing them alters the identifier. Use only when normalization rules permit.

### 19.3. Replacing NBSP Characters

~~~sql
SELECT replace(
    'Hà' || chr(160) || 'Nội',
    chr(160),
    ' '
) AS normalized_city;
~~~

Displayed result: `Hà Nội`.

This is more explicit than hoping a generic regex catches every whitespace character.

## 20. TRANSLATE: Character-by-Character Mapping

`translate(source, from_characters, to_characters)` replaces characters by **corresponding position** between two character sets.

~~~sql
SELECT translate('abc', 'abc', 'xyz') AS mapped;
~~~

Result: `xyz`.

### 20.1. Difference from REPLACE

~~~sql
SELECT
    replace('a-b-c', '-', '') AS by_replace,
    translate('a-b-c', '-', '') AS by_translate;
~~~

Both can produce `abc` when removing `-`, but the model differs:

- `replace` searches for a **substring**.
- `translate` maps **individual characters**.

If the target string in `translate` is shorter than the source character list, source characters without a corresponding replacement character are removed.

### 20.2. Do Not Use TRANSLATE for General Vietnamese Transliteration

Stripping Vietnamese accents involves more than a few ASCII character mappings. It requires understanding Unicode, letter casing, and combining forms. Simple `translate` does not replace a full language processor.

## 21. REGEXP_REPLACE: Pattern-Based Replacement

PostgreSQL supports regular expressions for transformations more complex than `replace`.

~~~sql
SELECT regexp_replace(
    'A---B----C',
    '-+',
    '-',
    'g'
) AS normalized_dashes;
~~~

Result: `A-B-C`.

### 21.1. The [[:space:]]+ Pattern

~~~sql
SELECT btrim(
    regexp_replace(
        E'  Nguyễn \t Văn \n An  ',
        '[[:space:]]+',
        ' ',
        'g'
    )
) AS normalized_name;
~~~

Meaning: runs of whitespace recognized by regex are replaced with a single space, and then leading/trailing spaces are stripped.

### 21.2. Pattern Intended Only for Single-Line Data

If a note has three paragraphs, collapsing every newline into a space destroys paragraph breaks. Set rules per field type:

| Field | Commonly Considered Policy |
|---|---|
| Email | Edge trimming and canonicalization per policy |
| Display name | Edge trimming, collapse whitespace if permitted |
| Address | Keep meaningful components and characters |
| Multi-line description | Preserve newlines intentionally |
| SKU code | Do not alter characters if it is an identifier |
| HTML/Markdown content | Use an appropriate parser or sanitizer, not regex alone |

### 21.3. Regex Replace Is Not a SQL Injection Defense

Removing single quotes or semicolons from strings with regex **is not a safe way to assemble SQL**. Queries accepting user input must use typed parameters, such as JDBC `PreparedStatement`, and whitelist/quote identifiers when dynamic SQL is required.

## 22. Splitting Strings with SPLIT_PART

`split_part(source, delimiter, field_number)` returns one field from a string, counting from position 1.

~~~sql
SELECT
    split_part('A|B|C', '|', 1) AS first_part,
    split_part('A|B|C', '|', 2) AS second_part,
    split_part('A|B|C', '|', 3) AS third_part;
~~~

Results: `A`, `B`, `C`.

### 22.1. Non-Existent Part

~~~sql
SELECT split_part('A|B', '|', 3) AS missing_field;
~~~

When requesting a field beyond the available parts, the result can be an **empty string**. Do not treat it as equivalent to NULL if you need to distinguish structural errors.

### 22.2. Do Not Use SPLIT_PART('@') as a Full Email Parser

~~~sql
SELECT split_part('alice@example.com', '@', 2) AS apparent_domain;
~~~

The result is `example.com` for this simple example. However, real email syntax is complex; this is not a standard validator or parser for all valid email addresses.

### 22.3. When Should You Use It?

- Splitting data codes that have a stable, validated delimiter.
- Parsing simple log strings under a clear contract.
- Reading one segment from a system-generated structured code.

If data can contain arbitrary delimiters in its content, naive splitting can break structure. Use proper formats and parsers like CSV/JSON instead of manual delimiter joining when values can contain the separator.

## 23. STRING_TO_ARRAY and ARRAY_TO_STRING

If you need to split a string into an array:

~~~sql
SELECT string_to_array('red,green,blue', ',') AS colors;
~~~

The result is a text array of three elements.

Joining an array into a string:

~~~sql
SELECT array_to_string(
    ARRAY['red', 'green', 'blue'],
    ', '
) AS color_label;
~~~

Result: `red, green, blue`.

### 23.1. Arrays Do Not Solve Every Delimiter Case

If an item contains a comma in its name like `"Ward 1, District 5"`, joining elements with commas and splitting them back loses the original boundaries.

When data needs safe serialization, use JSON, typed arrays, or a proper CSV parser; do not pick a delimiter and assume it will never appear in the data.

### 23.2. NULLs in Arrays

`array_to_string` has specific behavior for NULL elements and an optional NULL-replacement argument depending on how it is called. When you need to display "no data" clearly, test directly against real sample data and pick an explicit policy rather than assuming NULL behaves like an empty string.

## 24. STRING_AGG: Concatenating Multiple Rows into One String

So far, the functions mainly concatenated values **within the same row**. `string_agg()` is an **aggregate** that can concatenate values from **multiple rows** in the same group.

~~~sql
SELECT string_agg(name, ', ') AS names
FROM (
    VALUES ('An'), ('Bình'), ('Cường')
) AS people(name);
~~~

Meaningfully, the result is a string of three names, but if you need a **deterministic order**, you must add `ORDER BY` inside the aggregate.

### 24.1. Ordering Inside STRING_AGG

~~~sql
SELECT string_agg(name, ', ' ORDER BY name) AS names
FROM (
    VALUES ('Bình'), ('An'), ('Cường')
) AS people(name);
~~~

The result is concatenated in the specified sort order.

**Do not assume natural scan order** is the concatenation order, even if running the query a few times happens to return the same order.

### 24.2. GROUP BY to Produce One List per Group

~~~sql
SELECT
    category,
    string_agg(product_name, ' | ' ORDER BY product_name)
        AS product_names
FROM products
GROUP BY category
ORDER BY category;
~~~

This example expects a `products` table with `category` and `product_name`; a later lab section creates a suitable table.

### 24.3. Removing Duplicates Only When Actually Needed

~~~sql
SELECT string_agg(
    DISTINCT tag,
    ', ' ORDER BY tag
) AS unique_tags
FROM (
    VALUES ('sql'), ('postgres'), ('sql')
) AS t(tag);
~~~

Result: `postgres, sql`.

Use `DISTINCT` only when duplicate values carry no business meaning. If a list needs to show that a tag was attached three times, deduplicating loses information.

### 24.4. STRING_AGG Ignores NULL Values

~~~sql
SELECT string_agg(
    item,
    ' + ' ORDER BY item
) AS result
FROM (
    VALUES ('A'::text), (NULL::text), ('B'::text)
) AS t(item);
~~~

Result: `A + B`. NULL values do not produce a displayed element.

### 24.5. When There Are No Valid Values

If there are no rows or every expression to concatenate is NULL, `string_agg` typically returns NULL, not an empty string. Distinguish this from `concat` over arguments in the same row.

### 24.6. STRING_AGG Is Not Suitable for Very Large Sets

Concatenating hundreds of thousands or millions of values into a single string increases result size, can consume heavy memory, and is awkward for APIs to consume. If an application actually needs a structured list, consider `array_agg`, `json_agg`, pagination, or querying individual rows.

## 25. FORMAT: Formatting Strings from Templates

PostgreSQL provides the function:

~~~sql
format(format_string, arguments...)
~~~

An example:

~~~sql
SELECT format(
    'Customer: %s, order: %s',
    'An',
    123
) AS message;
~~~

Result: `Customer: An, order: 123`.

### 25.1. Common Placeholders

| Placeholder | Meaning |
|---|---|
| `%s` | Inserts value as a string |
| `%I` | Quotes value as a **SQL identifier** |
| `%L` | Quotes value as a **SQL literal** |
| `%%` | Literal percent character |

Example:

~~~sql
SELECT
    format('Hello %s', 'An') AS normal_text,
    format('Column name: %I', 'order total') AS sql_identifier,
    format('Literal: %L', 'O''Reilly') AS sql_literal,
    format('Progress: 90%%') AS literal_percent;
~~~

### 25.2. %I and %L Are for Controlled Dynamic SQL

Suppose you need to generate an illustrative statement:

~~~sql
SELECT format(
    'SELECT %I FROM %I WHERE %I = %L',
    'display_name',
    'customers',
    'customer_id',
    'CUST-001'
) AS sql_preview;
~~~

`%I` quotes table/column names with proper identifier syntax. `%L` quotes data with literal syntax.

**Important:** Having `format` does not mean every dynamic SQL statement is business-safe. Table/column names should be restricted via a whitelist; user data in application queries should be passed via **typed parameters** rather than textual SQL concatenation.

### 25.3. %s Does Not Replace %I or %L

Wrong for identifier/literal context:

~~~sql
-- Illustrates a dangerous pattern only:
-- format('SELECT %s FROM customers', user_supplied_column)
~~~

`%s` does not quote column names or literals per SQL rules. In PL/pgSQL code with dynamic SQL, use `format('%I', identifier)` and `EXECUTE ... USING` for parameter values where appropriate.

### 25.4. Do Not Use FORMAT for All UI Needs

Formatting currency, numbers, or dates has locale-specific requirements. `format()` is convenient for assembling templates, not a complete solution for i18n, pluralization, or country-specific currency formatting. The application layer may be better suited for user-facing messages.

## 26. REPEAT, LPAD, and RPAD

Several functions generate strings of controlled length.

### 26.1. REPEAT

~~~sql
SELECT
    repeat('*', 5) AS five_stars,
    repeat('ab', 3) AS repeated_pair;
~~~

Result:

~~~text
*****
ababab
~~~

Do not generate huge strings from unbounded user input, as that can consume excessive memory.

### 26.2. LPAD

~~~sql
SELECT
    lpad('7', 3, '0') AS padded_number,
    lpad('42', 5, '0') AS padded_code;
~~~

Results: `007` and `00042`.

### 26.3. RPAD

~~~sql
SELECT
    rpad('AB', 5, '.') AS right_padded;
~~~

Result: `AB...`.

### 26.4. LPAD/RPAD Can Truncate Strings

If the target length is **shorter** than the input value, padding functions can **truncate** the string rather than raising a length error.

~~~sql
SELECT lpad('123456', 4, '0') AS shortened;
~~~

Do not use `lpad`/`rpad` as a substitute for length validation on critical codes. If a code exceeds the limit, the application/schema should usually reject it instead of silently truncating characters.

## 27. OVERLAY: Replacing a Region by Position

PostgreSQL supports the syntax:

~~~sql
SELECT overlay(
    'PostgreSQL'
    PLACING 'gres'
    FROM 5
    FOR 3
) AS example;
~~~

This expression illustrates replacing a segment at a specified position. You can use `overlay()` when content has a fixed positional format.

### 27.1. Distinguish from replace

- `replace()`: replaces based on matching substring occurrences.
- `overlay()`: replaces based on specified **character positions**.

With variable-structure data, positional offsets are error-prone. Do not use `overlay` to edit arbitrary content when a format-aware parser is needed.

## 28. Counting and Finding Abnormal Whitespace

A practical task: identifying rows that need cleaning before modifying any data.

### 28.1. Comparing a String Against Its Trimmed Version

~~~sql
SELECT
    raw_value,
    btrim(raw_value) AS trimmed_value
FROM (
    VALUES
        ('  An  '::text),
        ('Bình'::text),
        (E'\tCường\t'::text)
) AS t(raw_value)
WHERE raw_value IS DISTINCT FROM btrim(raw_value);
~~~

This SQL query detects cases that differ after default `btrim`. However, tabs might not have been stripped; choose a character set matching your target.

### 28.2. Detecting Leading/Trailing Spaces

~~~sql
SELECT raw_value
FROM (
    VALUES
        ('  An'::text),
        ('Bình'::text),
        ('Cường  '::text)
) AS t(raw_value)
WHERE raw_value <> btrim(raw_value);
~~~

The result includes rows modified by trimming.

### 28.3. Detecting Multiple Consecutive Whitespace Characters

~~~sql
SELECT raw_value
FROM (
    VALUES
        ('Nguyễn   Văn An'::text),
        ('Trần Thị Bình'::text)
) AS t(raw_value)
WHERE raw_value ~ '[[:space:]]{2,}';
~~~

The regex here looks for runs of at least two characters belonging to the recognized whitespace class. When applying this to real Unicode data, verify your character policy.

### 28.4. Observing Length Before/After

~~~sql
SELECT
    raw_value,
    char_length(raw_value) AS length_before,
    char_length(btrim(raw_value)) AS length_after
FROM (
    VALUES
        ('  An  '::text),
        ('Bình'::text)
) AS t(raw_value);
~~~

Measuring length like this helps uncover hidden spaces when SQL tools do not visually highlight them.

## 29. PostgreSQL Lab: Storing Unnormalized String Data

Practice in a **test PostgreSQL database** where you have permission to create schemas. Do not run on production. If the `string_lab` schema already exists, use another database or schema name instead of deleting existing data.

### 29.1. Create Schema

~~~sql
CREATE SCHEMA string_lab;
~~~

### 29.2. Create Contacts Table

~~~sql
CREATE TABLE string_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT,
    email_raw TEXT,
    city TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Here, `display_name` and `email_raw` intentionally allow NULL/empty values to observe string handling. A production table may need stricter constraints, though you should not silently alter user input on write without agreed rules.

### 29.3. Insert Sample Data

~~~sql
INSERT INTO string_lab.contacts (
    display_name,
    email_raw,
    city
)
VALUES
    ('  Nguyễn Văn An  ', '  An@Example.COM  ', 'Hà Nội'),
    (E'\tTrần   Thị Bình  \t', 'binh@example.com  ', 'Đà Nẵng'),
    ('', '  ', NULL),
    (NULL, NULL, 'Huế');
~~~

The data intentionally includes:

- Leading/trailing spaces.
- Leading/trailing tabs.
- Multiple spaces between words.
- Uppercase letters in email.
- Empty strings.
- NULL values.

### 29.4. Inspect Raw Data and Lengths

~~~sql
SELECT
    contact_id,
    display_name,
    char_length(display_name) AS name_length,
    octet_length(display_name) AS name_bytes,
    email_raw,
    city
FROM string_lab.contacts
ORDER BY contact_id;
~~~

For NULL rows, length functions on NULL expressions normally return NULL. For Vietnamese, the byte count can exceed the character count.

### 29.5. Trim Only Regular Spaces

~~~sql
SELECT
    contact_id,
    btrim(display_name) AS trim_spaces_only,
    btrim(email_raw) AS clean_email_edges
FROM string_lab.contacts
ORDER BY contact_id;
~~~

The name row with leading/trailing tabs may still keep its tabs because default `btrim()` does not strip every kind of whitespace.

### 29.6. Trim Space, Tab, CR, LF

~~~sql
SELECT
    contact_id,
    btrim(
        display_name,
        E' \t\r\n'
    ) AS trimmed_edges
FROM string_lab.contacts
ORDER BY contact_id;
~~~

This query strips only characters from the explicitly listed set at **both ends** of the string. The multiple spaces between "Trần", "Thị", and "Bình" remain.

### 29.7. Normalize a Single-Line Name

~~~sql
SELECT
    contact_id,
    NULLIF(
        btrim(
            regexp_replace(
                display_name,
                '[[:space:]]+',
                ' ',
                'g'
            )
        ),
        ''
    ) AS normalized_name
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Goals of this example:

- Collapse whitespace runs matched by regex.
- Strip outer spaces.
- Turn empty strings after normalization into NULL.

This is a **read-only test expression**, without updating the raw data.

### 29.8. Simple Email Key Normalization

~~~sql
SELECT
    contact_id,
    email_raw,
    lower(
        NULLIF(btrim(email_raw), '')
    ) AS email_key
FROM string_lab.contacts
ORDER BY contact_id;
~~~

The first row gets key `an@example.com`, the second gets `binh@example.com`, and empty/NULL rows yield a NULL key.

This is an example of normalization under a simple policy, not an email ownership verifier or a complete canonicalization algorithm for every mail system.

### 29.9. Building a Contact Label with Optional Parts

~~~sql
SELECT
    contact_id,
    NULLIF(
        concat_ws(
            ' | ',
            NULLIF(
                btrim(
                    regexp_replace(
                        display_name,
                        '[[:space:]]+',
                        ' ',
                        'g'
                    )
                ),
                ''
            ),
            NULLIF(btrim(city), '')
        ),
        ''
    ) AS contact_label
FROM string_lab.contacts
ORDER BY contact_id;
~~~

The labels can be:

~~~text
Nguyễn Văn An | Hà Nội
Trần Thị Bình | Đà Nẵng
NULL
Huế
~~~

The third row has no meaningful parts, so it ends up returning NULL. The fourth row has a city but no name, so the label is just `Huế`.

If the business **requires a customer name**, concatenation that skips NULL does not replace validation; a row with only a city may represent missing data that needs handling.

## 30. Lab: Searching with Normalized Keys

A common need: finding an email ignoring letter case or outer spaces under a simple policy.

~~~sql
SELECT
    contact_id,
    email_raw
FROM string_lab.contacts
WHERE lower(btrim(email_raw))
      = lower(btrim(' an@example.com '));
~~~

The expected result is An's contact.

### 30.1. Functions in WHERE and Indexes

If there are many contacts, the query:

~~~sql
WHERE lower(btrim(email_raw)) = 'an@example.com'
~~~

applies an expression to the column. A plain B-tree index on `email_raw` does not necessarily serve this expression predicate as effectively as a direct column comparison.

PostgreSQL supports **expression indexes**:

~~~sql
CREATE INDEX idx_contacts_normalized_email
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

Then:

~~~sql
SELECT
    contact_id,
    email_raw
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

The planner may consider the matching index depending on table size, statistics, and selectivity. On a lab table with only a few rows, a sequential scan remains normal.

### 30.2. Expression Index for UNIQUE When Business Rules Allow

If canonical emails must be unique within a defined scope, you can use a unique index on the expression after **agreeing on the rules and cleaning duplicate data**.

Illustrative syntax example:

~~~sql
CREATE UNIQUE INDEX uq_contacts_email_key
ON string_lab.contacts (lower(btrim(email_raw)))
WHERE NULLIF(btrim(email_raw), '') IS NOT NULL;
~~~

With the current demo data, each meaningful email is distinct; empty/NULL rows fall outside the predicate.

**Do not create unique indexes in production before investigating duplicates, email policy, tenant scope, and soft deletion.** In multi-tenant applications, you may need to include `tenant_id` in the unique key.

### 30.3. Lower/Trim Needs Consistent Policy on Write and Read

If the backend normalizes using a different Unicode library while the database uses `lower(btrim())`, the two layers can produce different keys. Establish a versioned canonicalization contract and test it.

## 31. Lab: Building Product Lists with STRING_AGG

Create table:

~~~sql
CREATE TABLE string_lab.products (
    product_id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    product_name TEXT NOT NULL,
    tags TEXT[]
);

INSERT INTO string_lab.products (
    product_id,
    category,
    product_name,
    tags
)
VALUES
    (1, 'Book', 'PostgreSQL Basics', ARRAY['sql', 'database']),
    (2, 'Book', 'Practical SQL', ARRAY['sql', 'practice']),
    (3, 'Toy',  'Building Blocks', ARRAY['gift', 'creative']),
    (4, 'Toy',  'Alphabet Set', ARRAY['gift', 'education']),
    (5, 'Book', 'Query Optimization', ARRAY[]::TEXT[]);
~~~

### 31.1. Product List by Category

~~~sql
SELECT
    category,
    COUNT(*) AS product_count,
    string_agg(
        product_name,
        ' | ' ORDER BY product_name
    ) AS product_names
FROM string_lab.products
GROUP BY category
ORDER BY category;
~~~

Thanks to `ORDER BY product_name` inside `string_agg`, the concatenated string order is meaningfully determined according to the active collation.

### 31.2. Unique Tag List by Category

~~~sql
SELECT
    p.category,
    string_agg(
        DISTINCT t.tag,
        ', ' ORDER BY t.tag
    ) AS tags
FROM string_lab.products AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
GROUP BY p.category
ORDER BY p.category;
~~~

`unnest(p.tags)` emits one row per tag. `string_agg(DISTINCT ...)` removes duplicate tags within each category.

### 31.3. CROSS JOIN LATERAL Can Drop Products Without Tags

The product `Query Optimization` has an empty tag array so it does not appear in the row-level `CROSS JOIN LATERAL unnest(tags)` output.

If you need to keep tagless products as well:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    t.tag
FROM string_lab.products AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
    ON TRUE
ORDER BY p.product_id, t.tag NULLS LAST;
~~~

Every product still has at least one output row; a tagless product has `tag IS NULL`.

### 31.4. Do Not Aggregate Overly Large Lists If Clients Need Structure

With millions of products, a single `string_agg` string can exhaust resources and be difficult to consume. If an API needs a list with separate fields, returning structured JSON/arrays or paginating may be better than concatenating into text.

## 32. LIKE, ILIKE, and String Searching

Although the core topic is **string functions, concatenation, and whitespace handling**, matching operations often go hand in hand with normalization.

### 32.1. LIKE

~~~sql
SELECT
    'PostgreSQL' LIKE 'Post%' AS starts_with_post,
    'PostgreSQL' LIKE '%SQL' AS ends_with_sql;
~~~

`%` matches any character sequence (including empty), and `_` matches a single character per `LIKE` semantics.

### 32.2. ILIKE

PostgreSQL provides `ILIKE` for case-insensitive pattern matching according to the relevant locale/collation rules.

~~~sql
SELECT
    'PostgreSQL' ILIKE 'post%' AS case_insensitive_match;
~~~

Use `ILIKE` when pattern matching is required, without having to lowercase an entire column just to test a pattern.

### 32.3. starts_with

~~~sql
SELECT starts_with('PostgreSQL', 'Post') AS has_prefix;
~~~

The function returns a boolean. It differs from using `LIKE 'Post%'` when checking a literal prefix, especially if user-supplied prefixes can contain wildcard characters like `%` or `_`.

### 32.4. ILIKE Does Not Remove Accents

Case-insensitive matching is not the same as accent-insensitive Vietnamese matching. If you want `"Da Nang"` to match `"Đà Nẵng"`, you need a dedicated search policy, possibly based on the `unaccent` extension, an appropriate collation, or a search engine.

## 33. The UNACCENT Extension: When Accent-Insensitive Search Is Needed

PostgreSQL has the `unaccent` extension module, if installed and permitted.

On a **test database**, a user with appropriate privileges can run:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Example:

~~~sql
SELECT unaccent('Đà Nẵng') AS without_accents;
~~~

The purpose is to convert accented text into a form more convenient for certain search patterns.

### 33.1. Do Not Treat unaccent as Safe Normalization for All Data

"Accent-free" can cause different words or names to collide. That may be desirable for search, but you **should not overwrite real personal names, addresses, or legal names** with accent-stripped versions.

If accent-insensitive search is needed:

~~~text
Display data: "Đà Nẵng"
Search key:   form processed according to policy
~~~

Preserve the raw data and separate the search-key policy from the display value.

### 33.2. Extensions and Deployment Privileges

`CREATE EXTENSION` may require appropriate privileges and the module being provided in the PostgreSQL installation. Do not use it if the environment disallows it or lacks an operational plan. In large systems, evaluate its impact on indexes and query execution.

## 34. Collation Affects Comparison and Sorting

Strings are not just bytes; comparison and sorting results can be affected by **collation**.

~~~sql
SELECT
    product_name
FROM string_lab.products
ORDER BY product_name;
~~~

Ordering depends on the collation rules applied to the expression. Do not assume every database sorts Vietnamese names under identical rules.

### 34.1. Distinguishing Three Requirements

1. **Byte equality:** do two strings have identical byte representations?
2. **Search equivalence:** are two strings considered a match under search rules?
3. **Display order:** sorted according to which alphabet/locale?

These requirements may need different tools. `lower()`, Unicode normalization, collation, and `unaccent` are not fully interchangeable.

### 34.2. Collation and Uniqueness

If creating a unique index on a string key, matching semantics must align with the product contract. An unsuitable collation can make two "similar-looking" strings still count as distinct, or vice versa.

Do not change the collation of production data just to alter sort output without checking the impact on indexes and unique constraints.

## 35. Clean Data in SELECT or UPDATE?

There are two approaches:

### 35.1. Cleaning on Read

~~~sql
SELECT
    contact_id,
    NULLIF(btrim(display_name), '') AS display_name_clean
FROM string_lab.contacts;
~~~

Pros:

- Does not alter raw values.
- Easy to compare before/after.
- Good while testing rules.

Cons:

- Every query must use a consistent expression.
- Searching/indexing on raw values may not match the cleaned key.
- Multiple APIs might define slightly different expressions.

### 35.2. Normalizing on Write

The application can canonicalize input before INSERT/UPDATE or maintain a normalized key column according to an agreed rule.

Pros:

- Stored data is more consistent with the contract.
- Read queries are simpler.
- Constraints/unique indexes can be placed directly on the normalized key.

Risks:

- Can lose the user's original input if overwritten.
- Normalization rules may change across versions.
- Cannot easily undo if meaningful characters were stripped.

### 35.3. Raw Data and Normalized Key

One design stores two components:

~~~text
display_name_raw    = string confirmed by the user
display_name_search = key used for search
~~~

However, storing both requires synchronization, migrations, and tests ensuring the search key is derived from raw data under the current policy.

Do not add a redundant normalized column just because you can; consider an expression index or generated column depending on your PostgreSQL version and the properties of the functions used.

## 36. Do Not Collapse Whitespace in Every Field Type

A policy to "collapse multiple spaces into one" sounds good, yet can cause harm:

### 36.1. Proper Names

Collapsing input typos like `'Nguyễn   Văn An'` into `'Nguyễn Văn An'` can work, but consider names in other languages, nicknames, or combining-accent representations.

### 36.2. Identifiers

`'AB  123'` can differ from `'AB 123'` if the code was issued with significant spaces. Never alter codes on contracts or invoices just to make them look neat.

### 36.3. Multi-Line Notes

~~~text
Line 1

Line 3
~~~

Two newlines can separate paragraphs. Collapsing all whitespace to one space erases structure.

### 36.4. Legal Text or Digitally Signed Documents

Changing even a single character, including a space, changes the hash/signature. If you must verify signed copies, **do not normalize signed content** before verification.

### 36.5. Security Strings

Never trim/mutate passwords, tokens, or secrets using display-name rules. Whitespace can be a valid character in a secret. Altering it before verification breaks the security contract.

## 37. String Concatenation in SQL Is Different from Structured Data

A label:

~~~sql
SELECT concat_ws(
    ' | ',
    'ORD-001',
    'An',
    'Delivered'
) AS order_label;
~~~

is fine for display. But if an API needs to parse it back:

~~~text
ORD-001 | An | Delivered
~~~

problems arise if the name or status contains a `|` character.

### 37.1. Do Not Use Concatenated Labels as a Structured Exchange Format

It is better to return separate fields:

~~~json
{
  "orderCode": "ORD-001",
  "customerName": "An",
  "status": "delivered"
}
~~~

The presentation layer can build strings in the user's language and appropriate UI format.

### 37.2. When Structured Aggregate Results Are Needed

PostgreSQL supports aggregates such as `json_agg()`, `jsonb_agg()`, or `array_agg()`. If a report genuinely needs a machine-readable list, structured types are generally better than `string_agg()`.

### 37.3. When to Use string_agg?

- Descriptive strings for text reports.
- Short lists of labels in a display column.
- Exporting a formatted field under an explicit contract.
- Displaying short tags on a listing page.

For lists that can grow very large, adopt a size-limiting strategy or return structured/paginated results.

## 38. Working with Dynamic SQL and Security

In application code, concatenating strings to build SQL from user input can cause **SQL injection**.

Wrong:

~~~java
String sql = "SELECT * FROM customers WHERE email = '"
           + emailFromUser + "'";
~~~

If the data contains single quotes or malicious content, the SQL statement can break or change meaning.

### 38.1. Use PreparedStatement with Parameters

~~~java
String sql = """
    SELECT contact_id, display_name, email_raw
    FROM string_lab.contacts
    WHERE lower(btrim(email_raw)) = lower(btrim(?))
    """;

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, emailFromUser);
    try (var rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("contact_id");
            String name = rs.getString("display_name");
            // Process results appropriately.
        }
    }
}
~~~

This Java/JDBC snippet assumes `connection` is already initialized and `emailFromUser` is a string received from an API.

`PreparedStatement` passes values as data rather than splicing them into SQL syntax.

### 38.2. Identifiers Are Not Data Parameters

You cannot use a `?` placeholder directly in place of a table or column name in arbitrary SQL positions. If you truly need dynamic SQL by column name:

- Use a whitelist of allowed column names.
- Build the SQL in a trusted layer.
- Quote identifiers properly when using dynamic SQL in PostgreSQL/PL/pgSQL.
- Never take an arbitrary user-supplied identifier and splice it with `%s`.

### 38.3. TRIM or REPLACE Does Not Prevent Injection

Stripping `'` from values is not a security method, and can also break names like `O'Reilly`. The proper solution is parameterized queries, not mutating data to dodge SQL syntax.

## 39. Regex and Query Performance

String-processing expressions have CPU cost and can affect index usage.

### 39.1. Functions on Columns in WHERE

~~~sql
SELECT
    contact_id,
    display_name
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

On a large table, PostgreSQL may have to compute the expression across many rows if no matching index exists.

Expression index:

~~~sql
CREATE INDEX idx_contacts_email_search
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

The lab may have already created a similar index earlier. Do not create duplicate indexes in production simply because they appear in different examples.

### 39.2. B-Tree Does Not Help Every LIKE/ILIKE

Search conditions like `LIKE 'abc%'` may have certain optimization possibilities depending on collation and operator class/index, whereas `ILIKE '%abc%'` or regexes with leading wildcards typically cannot leverage a standard B-tree the way equality does.

PostgreSQL has the **`pg_trgm`** extension supporting trigram indexes for certain search patterns:

~~~sql
-- Only when the test environment permits and there is a real need:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX idx_contacts_name_trgm
-- ON string_lab.contacts
-- USING gin (display_name gin_trgm_ops);
~~~

Do not create trigram indexes on every text column by default. Extra indexes consume disk space and INSERT/UPDATE maintenance overhead; measure the workload.

### 39.3. Using EXPLAIN

~~~sql
EXPLAIN
SELECT contact_id
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

`EXPLAIN` shows the estimated plan. When test data is safe:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

`EXPLAIN ANALYZE` actually runs the `SELECT` to measure timing/rows. With DML statements, it also executes the write unless rolled back appropriately.

### 39.4. Normalize Once or on Every Read?

With only a few hundred rows, writing `lower(btrim())` directly may suffice. For large tables and frequent queries, an expression index or dedicated search key can help. Prioritize correctness first, measure performance second, and avoid breaking normalization rules just to hit an index.

## 40. PostgreSQL Regex Does Not Replace Dedicated Parsers

Some developers try using regex to parse:

- Every valid email form.
- International postal addresses.
- HTML.
- JSON.
- CSV with quotes and escapes.
- Nested structured strings.

These formats have complex grammars or rules. Regex can help **match simple patterns** or **normalize a known field**, but should not replace a dedicated parser for arbitrary formats.

### 40.1. Example with CSV

~~~text
"Nguyễn, Văn An",Hà Nội
~~~

If you only run `split_part(line, ',', 1)`, the first part will be an incomplete string. CSV allows commas inside quoted fields, so use a CSV parser or `COPY ... CSV` as appropriate.

### 40.2. Example with JSON

~~~json
{"fullName":"Nguyễn Văn An","city":"Hà Nội"}
~~~

Do not split strings by `:` and `,` to extract properties. PostgreSQL has `json/jsonb` types and structural access operators when the data is truly JSON.

## 41. Normalizing Data for Matching and Deduplication

Suppose a database contains the names:

~~~text
" Nguyễn Văn An"
"Nguyễn Văn An "
"Nguyễn   Văn An"
"NGUYỄN VĂN AN"
~~~

You may want to treat them as similar during search, yet **that does not prove they are the same person**.

### 41.1. Creating a Comparison Key to Suggest Duplicates

~~~sql
SELECT
    display_name,
    lower(
        btrim(
            regexp_replace(
                display_name,
                '[[:space:]]+',
                ' ',
                'g'
            )
        )
    ) AS comparison_key
FROM string_lab.contacts;
~~~

This is a **simple comparison key**, not a real-world person identifier. Two people with the same name can still be two different individuals.

### 41.2. Deduplication Requires Multiple Fields and Rules

When detecting duplicate customers, you may also need to compare:

- System customer ID.
- Verified email.
- Verified phone number.
- Data source.
- Tenant.
- Merge history.
- Consent / data-processing rules.

Never automatically `DELETE` records just because `lower(btrim(name))` matches.

### 41.3. Unicode Normalization and Case Sensitivity

If synchronizing data between Java, PostgreSQL, and a search service, version your normalization/collation rules so every layer agrees on equivalence. A unique index is only accurate relative to the semantics of the expression/collation used in the database.

## 42. Common String Concatenation Mistakes

### 42.1. Using || with Optional Fields

~~~sql
SELECT 'An' || ' - ' || NULL::text;
~~~

Result: NULL. If missing components should be omitted, use `concat_ws` and appropriate `NULLIF` rules.

### 42.2. Assuming CONCAT Automatically Adds Spaces

~~~sql
SELECT concat('Nguyễn', 'Văn', 'An');
~~~

The result is joined with no spaces. Insert separators explicitly or use `concat_ws(' ', ...)`.

### 42.3. Assuming CONCAT_WS Skips Empty Strings

`concat_ws('-', 'A', '', 'B')` still has an empty element and can produce `A--B`. To omit it, use `NULLIF(btrim(value),'')`.

### 42.4. Assuming TRIM Collapses Multiple Spaces Between Words

`btrim('  A   B  ')` returns `A   B`. To collapse internal whitespace, use an appropriate regex rule.

### 42.5. Assuming Default TRIM Removes Tabs and NBSP

No. Know the exact character set being stripped and the Unicode rules.

### 42.6. Assuming btrim(text, 'abc') Removes the Exact Substring 'abc'

No. It removes any `a`, `b`, or `c` characters at the edges.

### 42.7. Assuming REPLACE Understands Regex

No. `replace` uses literal substrings; regex uses `regexp_replace`.

### 42.8. Forgetting the g Flag in regexp_replace

Without it, only the first match may be replaced, leaving other whitespace runs untouched.

### 42.9. Using LENGTH to Measure Bytes

`char_length` measures characters; `octet_length` measures bytes.

### 42.10. Assuming One Grapheme Is Always One Character

An accented letter with combining marks can consist of multiple code points; `char_length` is not a full grapheme counter.

### 42.11. Using LOWER on All Names and Codes

This can destroy meaningful capitalization, corrupting identifiers or legal text.

### 42.12. Using INITCAP to Fix All Proper Names

There is no single capitalization rule across all languages and nicknames.

### 42.13. Taking Substrings from Fixed Offsets Without Validating Format

This can mis-slice malformed codes or codes whose length changed.

### 42.14. Using split_part for Complex CSV Data

CSV supports quotes/escapes; manual comma splitting can fail.

### 42.15. Omitting ORDER BY Inside STRING_AGG

Concatenation order is not guaranteed to match your intent.

### 42.16. Using DISTINCT to Mask Duplicate Data

Deduplicating can discard occurrence counts; verify the business requirement.

### 42.17. Assuming string_agg on an Empty Set Returns an Empty String

This aggregate can return NULL, unlike row-level concatenation functions.

### 42.18. Using %s to Interpolate Arbitrary Table Names into SQL

`%s` does not quote identifiers; whitelist and quote properly when building dynamic SQL.

### 42.19. Using REPLACE to "Prevent SQL Injection"

No. Use prepared statements, least privilege, and controlled dynamic SQL handling.

### 42.20. Assuming an Expression Index Will Always Be Used

The planner relies on statistics and cost estimates. On small tables, sequential scan can be faster.

### 42.21. Assuming Whitespace Normalization Never Loses Data

Whitespace can be part of secrets, multi-line formatting, or digitally signed content.

### 42.22. Using a Concatenated Display Label as Source Data to Split Back

Separators can appear in raw components; store and return structured fields instead.

## 43. Practice Exercises

### Exercise 1 — Simple Concatenation

Write SQL to produce `PostgreSQL` from the two strings `Postgre` and `SQL`.

**Hint:**

~~~sql
SELECT 'Postgre' || 'SQL';
~~~

### Exercise 2 — Concatenating a Name with Spaces

Build `Nguyễn Văn An` from three separate strings.

**Hint:**

~~~sql
SELECT concat_ws(' ', 'Nguyễn', 'Văn', 'An');
~~~

### Exercise 3 — NULL in ||

Predict:

~~~sql
SELECT 'A' || NULL::text;
~~~

**Hint:** NULL.

### Exercise 4 — NULL in CONCAT

Predict:

~~~sql
SELECT concat('A', NULL::text, 'B');
~~~

**Hint:** `AB`.

### Exercise 5 — Empty String in CONCAT_WS

Why can:

~~~sql
SELECT concat_ws('-', 'A', '', 'B');
~~~

return `A--B`?

**Hint:** An empty string is a non-NULL component.

### Exercise 6 — Omitting an Empty Component

Fix Exercise 5 to return `A-B` when the middle component is empty.

**Hint:**

~~~sql
SELECT concat_ws('-', 'A', NULLIF('', ''), 'B');
~~~

### Exercise 7 — Trimming Both Ends

~~~sql
SELECT btrim('   Hà Nội   ');
~~~

What is the result?

**Hint:** `Hà Nội`.

### Exercise 8 — Left and Right Trimming

Write two expressions that strip only leading spaces and only trailing spaces.

**Hint:** `ltrim(text)` and `rtrim(text)`.

### Exercise 9 — BTRIM Character Set

Result:

~~~sql
SELECT btrim('abcXYZcba', 'abc');
~~~

**Hint:** `XYZ`, because any `a`/`b`/`c` characters at the edges are removed.

### Exercise 10 — Leading Tabs

Why does `btrim(E'\tAn\t')` not guarantee tabs were removed?

**Hint:** Default trim mainly removes spaces; specify `E' \t\n\r'` if those are the characters you want to remove.

### Exercise 11 — NBSP

Write SQL replacing NBSP with a regular space.

~~~sql
SELECT replace('Hà' || chr(160) || 'Nội', chr(160), ' ');
~~~

### Exercise 12 — Collapsing Multiple Spaces

Turn `'  Trần   Thị  Bình  '` into `'Trần Thị Bình'`.

**Hint:** Combine `regexp_replace(..., '[[:space:]]+', ' ', 'g')` and `btrim()`.

### Exercise 13 — Vietnamese Length

Why can `char_length('Việt')` be smaller than `octet_length('Việt')`?

**Hint:** A Unicode character can occupy multiple UTF-8 bytes.

### Exercise 14 — Empty String vs. NULL

What is the difference between `''` and `NULL`?

**Hint:** An empty string is a value of length 0; NULL represents missing/unknown.

### Exercise 15 — NULLIF After Trim

Predict:

~~~sql
SELECT NULLIF(btrim('   '), '');
~~~

**Hint:** NULL.

### Exercise 16 — Normalizing an Email Key

Write an expression turning `'  An@Example.COM  '` into lowercase with no edge spaces.

**Hint:**

~~~sql
SELECT lower(btrim('  An@Example.COM  '));
~~~

### Exercise 17 — SUBSTRING

Extract the first four characters from `PostgreSQL`.

~~~sql
SELECT substring('PostgreSQL' FROM 1 FOR 4);
~~~

### Exercise 18 — LEFT and RIGHT

Extract the prefix `ORD` and serial `000123` from the code `ORD-2026-000123`.

**Hint:** `left(code,3)` and `right(code,6)`.

### Exercise 19 — STRPOS

Find the position of `gre` in `PostgreSQL`.

**Hint:** Position 5.

### Exercise 20 — REPLACE

Turn `a-b-c` into `a/b/c`.

~~~sql
SELECT replace('a-b-c', '-', '/');
~~~

### Exercise 21 — TRANSLATE

Use `translate` to map `a,b,c` to `x,y,z` respectively.

**Hint:**

~~~sql
SELECT translate('abc', 'abc', 'xyz');
~~~

### Exercise 22 — Full-String REGEXP_REPLACE

How does the result differ with and without the `'g'` flag on `'A   B   C'`?

**Hint:** With `g`, every matched whitespace group is replaced.

### Exercise 23 — SPLIT_PART

Extract the second part of `BOOK|001|VN`.

~~~sql
SELECT split_part('BOOK|001|VN', '|', 2);
~~~

**Hint:** `001`.

### Exercise 24 — ARRAY_TO_STRING

Join the array `{red,green,blue}` with separator `', '`.

**Hint:**

~~~sql
SELECT array_to_string(
    ARRAY['red', 'green', 'blue'],
    ', '
);
~~~

### Exercise 25 — STRING_AGG

Produce a list of product names per category from `string_lab.products`.

**Hint:** `string_agg(product_name, ', ' ORDER BY product_name)` with `GROUP BY category`.

### Exercise 26 — STRING_AGG and NULL

Why does a row with a NULL tag not produce `', NULL'` in the joined list?

**Hint:** `string_agg` ignores expressions that evaluate to NULL.

### Exercise 27 — DISTINCT in STRING_AGG

If a category has tags `sql, practice, sql` and you only want distinct tags, what should you use?

**Hint:** `string_agg(DISTINCT tag, ', ' ORDER BY tag)`.

### Exercise 28 — FORMAT

When generating dynamic SQL in PL/pgSQL, which placeholders are used for identifiers and literals?

**Hint:** `%I` and `%L`; prefer `EXECUTE ... USING` for data values where appropriate.

### Exercise 29 — LPAD

Turn the code `42` into `00042`.

~~~sql
SELECT lpad('42', 5, '0');
~~~

### Exercise 30 — Risk of Truncating Codes

Why should you not use `lpad('123456',4,'0')` as a length validation check?

**Hint:** The function can shorten the string, losing characters without raising a validation error.

### Exercise 31 — Expression Index

A query commonly uses:

~~~sql
WHERE lower(btrim(email_raw)) = 'an@example.com'
~~~

Suggest an appropriate index.

**Hint:**

~~~sql
CREATE INDEX idx_contacts_email_key_example
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

If a similar index was already created in the lab, do not create a duplicate index in real deployments.

### Exercise 32 — Protecting SQL Against Injection

Why should you never concatenate `emailFromUser` into SQL with `+` or `||`?

**Hint:** Data can alter SQL syntax; use PreparedStatement/parameterized queries.

### Exercise 33 — Display Strings Differ from Structured Data

Why should you not store `'ORD-001 | An | Delivered'` as the primary source and split it back when needed?

**Hint:** The separator can appear in raw data and break structure; store separate fields.

### Exercise 34 — Personal Names and Normalization

Should you automatically run `initcap(lower(full_name))` and overwrite all customer names?

**Hint:** Not by default. Proper-name/language rules are complex; you need a policy and the ability to preserve raw data.

### Exercise 35 — Accent-Insensitive Search

Does `lower()` guarantee `"Da Nang"` matches `"Đà Nẵng"`?

**Hint:** No. Stripping accents is a separate requirement that may need `unaccent`, collation, or a search layer.

## 44. Quick Reference Table

| Need | PostgreSQL |
|---|---|
| Concatenate two required strings | `a || b` |
| Concatenate multiple parts, skip NULL | `concat(a,b,c)` |
| Concatenate with separator | `concat_ws(', ',a,b,c)` |
| Exclude empty strings from concat_ws | `NULLIF(btrim(value),'')` |
| Strip spaces at both ends | `trim(value)` or `btrim(value)` |
| Strip leading spaces | `ltrim(value)` |
| Strip trailing spaces | `rtrim(value)` |
| Strip chosen set of characters | `btrim(value, characters)` |
| Strip edge spaces/tabs/newlines | `btrim(value,E' \t\n\r')` |
| Collapse internal whitespace runs | `regexp_replace(value,'[[:space:]]+',' ','g')` |
| Replace NBSP with space | `replace(value,chr(160),' ')` |
| Character count | `char_length(value)` |
| Byte count | `octet_length(value)` |
| Bit length | `bit_length(value)` |
| Lowercase | `lower(value)` |
| Uppercase | `upper(value)` |
| Simple title case | `initcap(value)` |
| Unicode NFC | `normalize(value,NFC)` |
| Slice substring | `substring(value FROM start FOR count)` |
| First n characters | `left(value,n)` |
| Last n characters | `right(value,n)` |
| Substring position | `strpos(value,substring)` |
| Replace literal substring | `replace(value,from,to)` |
| Character-by-character mapping | `translate(value,from_chars,to_chars)` |
| Regex replacement | `regexp_replace(value,pattern,replacement,'g')` |
| Extract field by delimiter | `split_part(value,delimiter,n)` |
| Split into array | `string_to_array(value,delimiter)` |
| Join array | `array_to_string(array,delimiter)` |
| Join multiple rows | `string_agg(value,separator ORDER BY value)` |
| Join multiple distinct rows | `string_agg(DISTINCT value,separator ORDER BY value)` |
| Format message from template | `format('Hello %s',value)` |
| Quote identifier in dynamic SQL | `format('%I',identifier)` |
| Quote literal in dynamic SQL | `format('%L',value)` |
| Left pad | `lpad(value,n,pad)` |
| Right pad | `rpad(value,n,pad)` |
| Repeat string | `repeat(value,n)` |
| Literal prefix check | `starts_with(value,prefix)` |
| Case-insensitive pattern search | `ILIKE` |
| Index on lower/trim | Expression index on `lower(btrim(column))` |
| Pass data into SQL safely | Typed parameters/PreparedStatement |

---

## Conclusion

PostgreSQL provides a rich toolkit for **concatenating strings, transforming text, and handling whitespace**. The **`||`** operator concatenates directly with `NULL`-propagation behavior; **`concat()`** ignores NULL components; **`concat_ws()`** inserts a separator between non-NULL components but does not automatically skip empty strings. Combining **`NULLIF(btrim(value),'')`** helps distinguish optional components when constructing display labels.

The **`trim/btrim/ltrim/rtrim`** family handles edge characters, while **`regexp_replace`** is appropriate when replacing internal whitespace runs by pattern. For Vietnamese and Unicode, distinguish **characters, bytes, code points, visible graphemes, NBSP, and normalization**, rather than assuming every whitespace or accented character is stored like ASCII.

Functions such as **`substring`**, **`left/right`**, **`position/strpos`**, **`replace/translate`**, **`split_part`**, and **`string_agg`** support many string-processing needs, yet they do not replace schemas, format parsers, or business validation. When querying large tables, an **expression index** can support normalized keys; when accepting user input, always use **parameterized SQL** instead of string concatenation to build queries.

The final principle is: **preserve meaningful raw data, normalize only according to defined rules, and always separate display strings from source data**. Following this lets PostgreSQL process text accurately and prevents NULL bugs, hidden whitespace, lost Unicode characters, and subtle discrepancies in search or reporting.
