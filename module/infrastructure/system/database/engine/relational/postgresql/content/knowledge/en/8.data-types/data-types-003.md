# char, varchar, text, and String Length in PostgreSQL

In PostgreSQL, columns storing a customer name, product code, or description all hold **character strings**, yet your choice of data type affects how PostgreSQL enforces length, stores trailing spaces, compares values, builds indexes, and handles Unicode data.

The three most common data types are **`character(n)` / `char(n)`**, **`character varying(n)` / `varchar(n)`**, and **`text`**. Their names look similar, but `char(n)` **blank-pads strings to length n**, whereas `varchar(n)` stores shorter strings without padding and enforces a character-count limit. `text` does not require a length limit in its type declaration.

This lesson belongs to the *Data Types* chapter of the *Database Engine Relational PostgreSQL* module, focusing on choosing the semantically right type and determining **whether "string length" is being measured in characters, bytes, or storage size**.

After completing this lesson, you will be able to:

- Distinguish `char(n)`, `varchar(n)`, `varchar`, and `text` using executable SQL examples.
- Understand how PostgreSQL pads/ignores trailing spaces in `char(n)` and its impact on comparisons.
- Explain when exceeding `n` causes an error versus when it gets truncated during explicit casting.
- Use `char_length()`, `length()`, `octet_length()`, `bit_length()`, and `pg_column_size()` for their intended purposes.
- Work with UTF-8, multi-byte characters, and strings with combining diacritics.
- Design `CHECK`, `UNIQUE`, indexes, and safe column-length alteration plans.

The examples use standard PostgreSQL syntax; Unicode illustrations assume the database uses **UTF8**, which you can verify with `SHOW server_encoding;`. When discussing equality behavior for two `text` strings, we assume a standard **deterministic collation**, unless noted otherwise.

## 1. Which String Type to Choose? Quick Comparison Table

| SQL Type | Example Declaration | Max Length in Declaration | When String Is Shorter Than n | Typical Use Case |
|---|---|---|---|---|
| `character(n)`, `char(n)` | `CHAR(6)` | Up to n **characters** | Pads with spaces to reach n characters | Fixed-width codes per standards/legacy if padding semantics are acceptable |
| `character varying(n)`, `varchar(n)` | `VARCHAR(80)` | Up to n **characters** | Keeps exact original length, no padding | Names, codes, data needing a technical upper bound |
| `character varying`, `varchar` | `VARCHAR` | No limit n specified | No padding | String storage behavior similar to `TEXT` |
| `text` | `TEXT` | No limit n in declaration | No padding | Descriptions, content, names, codes when enforcing length via constraints |
| `character`, `char` without n | `CHAR` | Equivalent to `CHAR(1)` | Pads to 1 character | Very easy to pick by mistake thinking it is an unlimited string |

**Practical recommendation:** in most PostgreSQL applications, start with `text`, or `varchar(n)` when there is a genuine business limit. Only use `char(n)` when you understand and actively want its blank-padding semantics. `char(20)` is **not inherently faster** than `varchar(20)` or `text`.

### 1.1. Different Type Names Can Be the Same Type

PostgreSQL accepts:

```sql
CREATE TABLE demo_ten_kieu (
    a CHARACTER(10),
    b CHAR(10),
    c CHARACTER VARYING(10),
    d VARCHAR(10),
    e CHARACTER VARYING,
    f VARCHAR,
    g TEXT
);
```

In this table:

- `a` and `b` are the same `character(10)` type.
- `c` and `d` are the same `character varying(10)` type.
- `e` and `f` have no declared length limit and store values much like `text`.
- `g` uses PostgreSQL's `text` type.

Do not confuse SQL `CHAR(n)` with the internal type named **`"char"`** in PostgreSQL's catalog: that one-byte internal type is not designed for storing ordinary business strings.

## 2. Understanding n as Character Count, Not Byte Count

For `varchar(n)` and `char(n)`, `n` specifies the **number of characters as counted by PostgreSQL**, not the byte storage to allocate.

The following example runs on a database with UTF8 encoding:

```sql
SHOW server_encoding;

SELECT
    char_length('A')   AS so_ky_tu_ascii,
    octet_length('A')  AS so_byte_ascii,
    char_length('é')   AS so_ky_tu_e_dau,
    octet_length('é')  AS so_byte_e_dau,
    char_length('😀')  AS so_ky_tu_emoji,
    octet_length('😀') AS so_byte_emoji;
```

Expected results in UTF8:

| String | `char_length` | `octet_length` |
|---|---:|---:|
| `A` | 1 | 1 |
| `é` (precomposed character) | 1 | 2 |
| `😀` | 1 | 4 |

Thus, a `varchar(3)` column can hold three Unicode characters whose total byte count exceeds 3. When designing API transfer capacities, storage, or payload size limits, measure **bytes** separately.

### 2.1. A Unicode Character Is Not Always "One Visual Character"

An accented letter can be represented by:

1. A single **precomposed code point**, such as `é`.
2. The letter `e` plus a **combining acute accent** `U+0301`.

In PostgreSQL UTF8:

```sql
SELECT
    char_length('é') AS do_dai_dung_san,
    char_length(U&'e\0301') AS do_dai_to_hop,
    octet_length('é') AS byte_dung_san,
    octet_length(U&'e\0301') AS byte_to_hop;
```

Typical results:

| Representation | `char_length` | `octet_length` |
|---|---:|---:|
| `é` | 1 | 2 |
| `e` + combining acute accent | 2 | 3 |

Two strings can **look identical** while PostgreSQL counts different character lengths. `char_length` does not count *grapheme clusters* or "visual characters seen by the user". Strings with joined emojis and combining marks require explicit Unicode/normalization rules if the UI limits displayed character count.

### 2.2. Type Length Limits Are Not Fixed Disk Allocations

`varchar(100)` does not mean every row reserves exactly 100 bytes. PostgreSQL stores variable-length string data with necessary overhead; actual space consumed depends on the content's byte count, tuple layout, and storage mechanism.

Conversely, `char(100)` may have to store many padding spaces for a short string, making the data unnecessarily larger. Do not infer exact disk byte usage from the type name.

## 3. First Hands-On Exercise: Creating a Table with All Three Types

Create a dedicated schema to avoid touching application tables:

```sql
CREATE SCHEMA IF NOT EXISTS pg_string_lab;

CREATE TABLE pg_string_lab.loai_chuoi (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_co_dinh CHAR(6),
    ma_gioi_han VARCHAR(6),
    ghi_chu TEXT
);
```

Insert data:

```sql
INSERT INTO pg_string_lab.loai_chuoi
    (ma_co_dinh, ma_gioi_han, ghi_chu)
VALUES
    ('AB',   'AB',   'Short length test row'),
    ('XY12', 'XY12', 'Slightly longer code'),
    ('VN',   'VN',   'Unicode string: Vietnamese');
```

Query:

```sql
SELECT
    id,
    ma_co_dinh,
    ma_gioi_han,
    ghi_chu
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

Looking at the output in a terminal or GUI, the two code columns may look identical because many tools do not visibly render trailing spaces. **Do not conclude two types store data identically based solely on display output.**

### 3.1. Measuring Lengths Directly on Stored Data

```sql
SELECT
    id,
    char_length(ma_co_dinh) AS len_char,
    octet_length(ma_co_dinh) AS bytes_char,
    char_length(ma_gioi_han) AS len_varchar,
    octet_length(ma_gioi_han) AS bytes_varchar
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

Assuming the codes use ASCII characters as in the sample data:

| id | len_char | bytes_char | len_varchar | bytes_varchar |
|---:|---:|---:|---:|---:|
| 1 | 2 | 6 | 2 | 2 |
| 2 | 4 | 6 | 4 | 4 |
| 3 | 2 | 6 | 2 | 2 |

This is direct evidence:

- `CHAR(6)` is **space-padded to the declared length** in storage.
- `char_length` on a `character(n)` value **does not count trailing padding spaces**.
- `octet_length` includes the padded space bytes of `character(n)`.
- `VARCHAR(6)` keeps shorter data without auto-padding.

Note that these measurements use ASCII values where each character takes one byte in UTF8; with multi-byte characters, byte count no longer equals character count.

## 4. CHAR(n): Blank-Padded Strings

`CHAR(n)` (or `CHARACTER(n)`) is a **fixed-length character type under SQL semantics**.

Example:

```sql
SELECT
    'AB'::CHAR(5) AS gia_tri,
    char_length('AB'::CHAR(5)) AS so_ky_tu,
    octet_length('AB'::CHAR(5)) AS so_byte;
```

With ASCII and UTF8, the lengths are **2 characters** and **5 bytes**, respectively. PostgreSQL appended three spaces to reach the physical length of `CHAR(5)`.

### 4.1. Padding Spaces Are Generally Ignored in Equality Comparisons

Comparing two values both converted to `CHAR(5)`:

```sql
SELECT
    'AB'::CHAR(5) = 'AB   '::CHAR(5)
        AS co_bang_nhau_khong;
```

The result is **true**: trailing spaces in `character(n)` values are insignificant when PostgreSQL compares for equality under this type's semantics.

This can cause surprises with identifiers. With `CHAR(5)`, inputs `'AB'` and `'AB   '` can be treated as equal in comparisons, even though the inputs have different character counts.

### 4.2. Leading Spaces Remain Significant

```sql
SELECT
    'AB'::CHAR(5) = ' AB'::CHAR(5)
        AS co_bang_nhau_khong;
```

Under a standard collation, the result is **false** because one string has a **leading** space that the other lacks. Ignoring trailing spaces does not mean PostgreSQL automatically trims whitespace in all positions.

### 4.3. Casting CHAR(n) to TEXT/VARCHAR May Strip Trailing Spaces

When converting from `character(n)` to another string type, PostgreSQL strips trailing padding spaces:

```sql
SELECT
    char_length('AB'::CHAR(6)) AS len_char,
    octet_length('AB'::CHAR(6)) AS bytes_char,
    char_length(('AB'::CHAR(6))::TEXT) AS len_sau_cast_text,
    octet_length(('AB'::CHAR(6))::TEXT) AS bytes_sau_cast_text;
```

Illustrative results with ASCII:

| len_char | bytes_char | len_sau_cast_text | bytes_sau_cast_text |
|---:|---:|---:|---:|
| 2 | 6 | 2 | 2 |

Therefore, display or string-processing functions may behave differently from a direct byte measurement on a `CHAR(n)` value. Do not expect casting to `TEXT` to retain physical padding.

### 4.4. LIKE and Regular Expressions Do Not Behave Identically to Equals

Under `character(n)` semantics, trailing spaces can be ignored in **character value comparisons**, whereas **pattern matching** such as `LIKE` or regular expressions has its own rules where trailing spaces may still matter.

Therefore:

```sql
-- Do not infer LIKE results from the = operator.
SELECT
    ma_co_dinh,
    ma_co_dinh LIKE 'AB%' AS phu_hop_mau
FROM pg_string_lab.loai_chuoi
ORDER BY id;
```

When writing pattern filters, consider operand types, casts, padding length, collation, and business intent. For codes frequently queried with `LIKE`, `CHAR(n)` easily introduces extra subtleties to remember.

### 4.5. Do Not Choose CHAR(n) Just for "Optimization"

`CHAR(n)` offers no default speed advantage over `VARCHAR(n)` or `TEXT` in PostgreSQL. Blank-padding can increase storage size and add processing overhead. Systems using `CHAR(n)` typically do so because of legacy data standards, interoperability with older software, or explicit whitespace-semantics requirements.

If the requirement is **"the code must be exactly 6 characters"**, `CHAR(6)` **does not automatically substitute** for validating 6 meaningful characters, because shorter inputs still get padded. A `TEXT` or `VARCHAR(6)` paired with `CHECK (char_length(code) = 6)` often expresses the business rule much more clearly.

## 5. VARCHAR(n): Length-Limited Without Padding

`VARCHAR(n)` (or `CHARACTER VARYING(n)`) permits 0 to n characters if no other constraints apply, and preserves the actual stored string length.

```sql
SELECT
    'AB'::VARCHAR(5) AS gia_tri,
    char_length('AB'::VARCHAR(5)) AS so_ky_tu,
    octet_length('AB'::VARCHAR(5)) AS so_byte;
```

With ASCII, the result is **2 characters** and **2 bytes**, without the three padding spaces of `CHAR(5)`.

### 5.1. Trailing Spaces Are Part of the Value

```sql
SELECT
    'AB'::VARCHAR(5) = 'AB   '::VARCHAR(5)
        AS varchar_equal,
    'AB'::TEXT = 'AB   '::TEXT
        AS text_equal;
```

Under a standard deterministic collation, both results are **false**. `VARCHAR` and `TEXT` do not ignore trailing spaces in equality comparisons the way `CHAR(n)` does.

**Nondeterministic collations** can alter comparison rules for strings with differing bytes; see the collation section below. When strict code uniqueness is required, consider both collation and input normalization steps.

### 5.2. The Maximum Length Is n Characters, Not n Bytes

```sql
CREATE TABLE pg_string_lab.ma_san_pham (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(8) NOT NULL
);

INSERT INTO pg_string_lab.ma_san_pham (sku)
VALUES ('ABC123');
```

An input longer than 8 meaningful characters violates the limit:

```sql
-- Intentionally illustrates a statement that errors when run:
-- INSERT INTO pg_string_lab.ma_san_pham (sku)
-- VALUES ('ABCDEFGHI');
-- ERROR: value too long for type character varying(8)
```

Because this illustrates a failing statement, it is **commented out** so readers do not accidentally halt the entire practice script. Updates to a `VARCHAR(8)` column must also obey the length limit.

### 5.3. Length Limit Handling for Trailing Spaces per SQL Standard

PostgreSQL follows an SQL standard exception: when inserting into `VARCHAR(n)` or `CHAR(n)` and a string exceeds n characters, **if all excess characters are spaces**, they may be truncated so the value stores validly.

Example `VARCHAR(4)` column:

```sql
CREATE TABLE pg_string_lab.thu_do_dai (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gia_tri VARCHAR(4)
);

-- Input has 6 characters, but the two characters beyond 4 are both spaces.
INSERT INTO pg_string_lab.thu_do_dai (gia_tri)
VALUES ('ABCD  ');

SELECT gia_tri, char_length(gia_tri)
FROM pg_string_lab.thu_do_dai;
```

The stored value is `ABCD` with length 4. This is **not** evidence that `VARCHAR(4)` accepts arbitrarily long strings. If any character beyond the limit is not an ordinary space, the write will fail.

### 5.4. Explicit Casts Can Truncate Strings Silently Without Error

A **very important** exception: when a developer **explicitly casts** to `VARCHAR(n)` or `CHAR(n)`, PostgreSQL truncates the data to n characters instead of raising an error.

```sql
SELECT
    'ABCDEFGHI'::VARCHAR(4) AS sau_cast_varchar,
    'ABCDEFGHI'::CHAR(4) AS sau_cast_char;
```

Both evaluate to `ABCD`.

Thus, these two operations are not equivalent:

```sql
-- A: Writing a long string directly to a bounded column:
-- Generally errors if the excess part contains non-space characters.
-- INSERT INTO pg_string_lab.thu_do_dai(gia_tri)
-- VALUES ('ABCDEFGHI');

-- B: Casting first, then writing:
-- The value is already truncated to 4 characters before reaching the column.
INSERT INTO pg_string_lab.thu_do_dai(gia_tri)
VALUES ('ABCDEFGHI'::VARCHAR(4));
```

If an API must **reject oversized data** rather than silently dropping the tail, do not use explicit casts as a default pre-insert step. Validate raw input against business rules, and let constraints protect the data.

## 6. VARCHAR Without n and TEXT

In PostgreSQL, the declaration:

```sql
CREATE TABLE pg_string_lab.noi_dung (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tieu_de VARCHAR,
    mo_ta TEXT
);
```

defines two string columns **without an n limit in the type declaration**.

- `VARCHAR` without `(n)` imposes no typmod character limit.
- `TEXT` likewise imposes no n limit in the type name.
- Both are variable-length string types without blank-padding.
- Both remain subject to **PostgreSQL's technical size limit per value** and environment resource limits.

Do not interpret "without n" as an infinitely long string: in PostgreSQL, varlena data is subject to an internal size limit (practically around 1 GiB per value before other constraints), as well as RAM, disk, query, protocol, and operational limits.

### 6.1. Does Choosing TEXT Prevent Using Indexes?

No. PostgreSQL supports B-tree indexes and appropriate indexing mechanisms for both `TEXT` and `VARCHAR`. Choosing `VARCHAR(255)` over `TEXT` **does not automatically make indexes faster** or save storage for identical content.

Example:

```sql
CREATE INDEX noi_dung_tieu_de_idx
ON pg_string_lab.noi_dung (tieu_de);
```

Whether an index is useful depends on query patterns, selectivity, statistics, collation, operator types, and the execution plan. `LIKE '%chuoi%'` typically does not benefit from a standard B-tree the way equality queries do; another indexing approach, such as trigrams for substring-search workloads, may be needed.

### 6.2. When to Use TEXT vs. VARCHAR(n)?

Common choices:

| Business Column | Reasonable Choice | Why |
|---|---|---|
| Product description | `TEXT` | Content can be long; no fixed type-level limit needed |
| User display name | `TEXT` with `CHECK` or `VARCHAR(100)` | Business bound needs to be explicit |
| SKU up to 32 characters | `VARCHAR(32)` or `TEXT CHECK (...)` | Reject data exceeding contract length |
| Internal notes | `TEXT` | An n limit brings no benefit without a requirement |
| Two-letter ISO country code | `TEXT` + `CHECK`/foreign key, or `VARCHAR(2)` | Must validate against the code set, not just length |
| Machine-generated value, specialized ID | Dedicated type like `UUID` when UUID semantics apply | Do not turn everything into strings when dedicated types exist |

If the system requires an exact 2-character country code, `CHAR(2)` alone does not guarantee the input has two meaningful letters due to padding. Constraining the valid set of values is usually more important than using a fixed-length character type.

## 7. String Length Functions to Distinguish

PostgreSQL provides multiple length-related functions; each answers a different question.

| Function | What Does It Measure? | Example |
|---|---|---|
| `char_length(text)` | Number of characters as counted by PostgreSQL | `char_length('é')` can be 1 |
| `character_length(text)` | Equivalent to `char_length` | Closer to SQL standard syntax |
| `length(text)` | Number of characters; equivalent to `char_length` for typical strings | `length('ABC') = 3` |
| `octet_length(text)` | Number of bytes in the current encoding | UTF8 `octet_length('é') = 2` |
| `bit_length(text)` | Number of bits in the string representation | `bit_length('A') = 8` in UTF8 |
| `pg_column_size(value)` | Bytes used to store the value internally in the measured context | May include overhead/compression effects; not equal to characters |

### 7.1. A Query Comparing Measurements

```sql
SELECT
    'Tiếng Việt'::TEXT AS gia_tri,
    char_length('Tiếng Việt') AS so_ky_tu,
    octet_length('Tiếng Việt') AS so_byte,
    bit_length('Tiếng Việt') AS so_bit,
    pg_column_size('Tiếng Việt'::TEXT) AS kich_thuoc_noi_bo;
```

The actual value of `pg_column_size` should not be used as a "new definition of string length". Storage size can include metadata and varies with the physical storage format; large values may be compressed or moved out-of-line via TOAST.

### 7.2. Do char_length and length Differ?

For standard `TEXT` and `VARCHAR`:

```sql
SELECT
    char_length('ABC'::TEXT) AS a,
    character_length('ABC'::TEXT) AS b,
    length('ABC'::TEXT) AS c;
```

All three return **3**. What matters more is **whether the argument is `CHAR(n)`**, because its padding spaces carry special semantics.

### 7.3. Measuring a String with Real Trailing Spaces

```sql
SELECT
    char_length('AB  '::TEXT) AS text_len,
    octet_length('AB  '::TEXT) AS text_bytes,
    char_length('AB  '::VARCHAR(6)) AS varchar_len,
    octet_length('AB  '::VARCHAR(6)) AS varchar_bytes;
```

With ASCII, all four counts return **4**, because the two trailing spaces **are real data** in `TEXT`/`VARCHAR`.

For `CHAR(n)`, `char_length` excludes trailing spaces per character-type semantics. Therefore, do not use `char_length(char_col)` alone to determine how many spaces a user originally typed: the original input may have been padded or converted.

### 7.4. Trimming Whitespace Intentionally Before Measuring

```sql
SELECT
    char_length('  ABC  '::TEXT) AS len_goc,
    char_length(btrim('  ABC  '::TEXT)) AS len_sau_trim,
    char_length(rtrim('  ABC  '::TEXT)) AS len_sau_rtrim,
    char_length(ltrim('  ABC  '::TEXT)) AS len_sau_ltrim;
```

Results in ASCII characters:

| len_goc | len_sau_trim | len_sau_rtrim | len_sau_ltrim |
|---:|---:|---:|---:|
| 7 | 3 | 5 | 5 |

By default, `btrim` strips **ordinary space characters** from both ends. It is not synonymous with normalizing all Unicode whitespace or removing all invisible characters. If inputs may include tabs, non-breaking spaces, or zero-width characters, a more explicit policy is needed.

## 8. NULL, Empty Strings, and Whitespace-Only Strings

The following three values have distinct meanings in PostgreSQL:

```sql
SELECT
    NULL::TEXT AS khong_co_gia_tri,
    ''::TEXT AS chuoi_rong,
    '   '::TEXT AS ba_dau_cach;
```

| Value | Meaning | `char_length` | Compared to Empty String |
|---|---|---:|---|
| `NULL` | No value / unknown | `NULL` | Comparison yields unknown |
| `''` | String with 0 characters | 0 | Equal to empty string |
| `'   '` | String with three spaces | 3 | Not equal to empty string under standard deterministic collation |

Verify with:

```sql
SELECT
    NULL::TEXT IS NULL AS null_la_null,
    ''::TEXT IS NULL AS empty_la_null,
    char_length(''::TEXT) AS do_dai_empty,
    char_length('   '::TEXT) AS do_dai_spaces;
```

PostgreSQL **does not equate `''` with `NULL`**. When designing an API, explicitly define how omitted fields, `null` values, and empty strings are handled.

### 8.1. Why Is NOT NULL Not Enough?

```sql
CREATE TABLE pg_string_lab.nguoi_dung (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten_hien_thi TEXT NOT NULL
);
```

`NOT NULL` forbids `NULL`, yet **does not forbid empty strings**:

```sql
INSERT INTO pg_string_lab.nguoi_dung (ten_hien_thi)
VALUES ('');
```

If the rule states that a name must not be empty after trimming leading/trailing spaces, add a `CHECK` constraint or application-layer validation.

## 9. Using CHECK to Enforce Business-Accurate Lengths

Instead of thinking "every string column must be `VARCHAR(255)`", express the rule directly:

- Display name between 1 and 80 meaningful characters after trimming.
- Product SKU must be 3 to 20 characters with no leading or trailing spaces.
- Description content has no small business limit; use `TEXT`.
- Protocol field limited to at most 500 UTF-8 bytes, not 500 characters.

### 9.1. CHECK with char_length

```sql
CREATE TABLE pg_string_lab.ho_so (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    bio TEXT,
    CONSTRAINT chk_display_name_length
        CHECK (char_length(display_name) BETWEEN 1 AND 80),
    CONSTRAINT chk_display_name_not_blank
        CHECK (char_length(btrim(display_name)) > 0)
);
```

`char_length(display_name) BETWEEN 1 AND 80` caps the character count as measured by PostgreSQL, while `char_length(btrim(display_name)) > 0` blocks strings made solely of ordinary ASCII spaces.

Naming both constraints separately helps return clear error details by constraint name when the application translates database errors.

### 9.2. Requiring Exactly n Characters

Here is an approach for two-letter country codes:

```sql
CREATE TABLE pg_string_lab.quoc_gia (
    ma_quoc_gia TEXT PRIMARY KEY,
    ten_quoc_gia TEXT NOT NULL,
    CONSTRAINT chk_ma_quoc_gia_do_dai
        CHECK (char_length(ma_quoc_gia) = 2),
    CONSTRAINT chk_ma_quoc_gia_chu_hoa
        CHECK (ma_quoc_gia COLLATE "C" ~ '^[A-Z]{2}$')
);
```

`char_length = 2` enforces exact character length, while regex `^[A-Z]{2}$` under the `"C"` collation restricts to two uppercase ASCII letters for this **illustrative rule**. If the business uses real ISO codes, also validate membership against an approved list (via foreign key / reference table), not merely having two letters.

### 9.3. Requiring a Byte Limit

A protocol might enforce a `500-byte` payload limit:

```sql
CREATE TABLE pg_string_lab.thong_diep (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    CONSTRAINT chk_payload_bytes
        CHECK (octet_length(payload) <= 500)
);
```

A string of 300 multi-byte Unicode characters can exceed 500 bytes even though `char_length` is under 500. This is when `octet_length` must be used instead of `char_length`.

If the system transmits data in an encoding different from `server_encoding`, the transmitted byte count may differ from the internal byte count; evaluate against the actual wire encoding.

### 9.4. Should You Combine VARCHAR(n) and CHECK?

Yes, if the two checks test **different conditions**:

```sql
CREATE TABLE pg_string_lab.sku_hop_le (
    sku VARCHAR(20) PRIMARY KEY,
    CONSTRAINT chk_sku_not_blank
        CHECK (char_length(btrim(sku)) > 0),
    CONSTRAINT chk_sku_trimmed
        CHECK (sku = btrim(sku))
);
```

Here `VARCHAR(20)` caps length at 20 characters, while `CHECK` rejects blank space-only SKUs and prohibits leading/trailing spaces. Under standard deterministic collations, `sku = btrim(sku)` catches leading/trailing spaces; if exact byte-level checks are needed in special collation environments, design the check accordingly.

Note: for inputs longer than 20 where the excess consists solely of spaces, PostgreSQL may strip the excess before the constraint inspects the final value. If the business must reject **any** over-length input, validate raw input at the API/ingestion boundary and consider dedicated rules rather than relying purely on the column type.

## 10. Comparisons and Uniqueness: Watch Out for CHAR, Whitespace, and Collation

Choosing a string type is not just about storage space. It also affects whether two values are considered equal.

### 10.1. Comparing CHAR and TEXT

```sql
SELECT
    'A'::CHAR(4) = 'A   '::CHAR(4)
        AS char_equal,
    'A'::VARCHAR(4) = 'A   '::VARCHAR(4)
        AS varchar_equal,
    'A'::TEXT = 'A   '::TEXT
        AS text_equal;
```

Under a standard deterministic collation:

| char_equal | varchar_equal | text_equal |
|---|---|---|
| true | false | false |

When a business key must distinguish every space, `CHAR(n)` is generally unsuitable. If leading/trailing whitespace should not be accepted, normalize or reject at the application boundary and add matching constraints.

### 10.2. UNIQUE on CHAR(n) May Treat Space Variants as Duplicates

```sql
CREATE TABLE pg_string_lab.ma_co_dinh_duy_nhat (
    code CHAR(4) UNIQUE
);

INSERT INTO pg_string_lab.ma_co_dinh_duy_nhat (code)
VALUES ('AB');

-- Semantically, the value below compares equal to the stored value,
-- so UNIQUE may reject it:
-- INSERT INTO pg_string_lab.ma_co_dinh_duy_nhat (code)
-- VALUES ('AB  ');
```

Do not pick `CHAR(n)` to store a code where trailing spaces are meaningful in an external system and expect `UNIQUE` to allow both variants.

### 10.3. Collation Also Affects Comparisons

PostgreSQL supports collations that govern how strings are compared and sorted. In particular, **nondeterministic collations** can treat strings with differing bytes as equal (for example, under case-insensitive or accent-insensitive policies).

Therefore, the statement "`TEXT` distinguishes every byte-different string in `=`" is not unconditionally true under **all collations**. When uniqueness is critical:

1. Check the column/index collation.
2. Decide whether case, accents, or Unicode forms should be ignored.
3. Choose normalization rules before storage.
4. Test `UNIQUE` constraints with realistic data.

To inspect column metadata and collations attached to a schema, you can query `information_schema.columns` or the relevant system catalogs. Never change production collations simply "to make comparisons look nicer", as it can affect indexes and uniqueness.

### 10.4. Unicode Normalization Does Not Happen Automatically with VARCHAR

Two visually identical strings—one using a precomposed code point and the other using combining marks—can differ in bytes and length. `VARCHAR(n)` and `TEXT` do not automatically normalize all text into a single Unicode form.

If the business requires a unique Unicode code in a canonical form (NFC/NFKC depending on requirements), apply a consistent normalization policy and assess its impact on existing data. Do not substitute `lower()` or `btrim()` for Unicode normalization; each function solves a different problem.

## 11. Indexes for CHAR, VARCHAR, and TEXT

### 11.1. B-Tree Indexes Work for All Standard String Types

```sql
CREATE INDEX ma_san_pham_sku_idx
ON pg_string_lab.ma_san_pham (sku);

CREATE INDEX ho_so_display_name_idx
ON pg_string_lab.ho_so (display_name);
```

Given identical content and query predicates, declaring `VARCHAR(n)` instead of `TEXT` **does not magically turn a sequential scan into an index scan**. The query planner evaluates selectivity, statistics, I/O cost, collation, and filter predicates.

### 11.2. Exact Matches and Prefix Searches Are Different Needs

```sql
SELECT *
FROM pg_string_lab.ma_san_pham
WHERE sku = 'ABC123';

SELECT *
FROM pg_string_lab.ma_san_pham
WHERE sku LIKE 'ABC%';
```

An `=` query can normally use a standard B-tree with the default operator class. For `LIKE 'ABC%'`, whether a standard B-tree index can be used depends on the collation and operator class. For prefix-heavy workloads, you can consider `varchar_pattern_ops` on `VARCHAR` or `text_pattern_ops` on `TEXT` as needed:

```sql
CREATE INDEX ma_san_pham_sku_prefix_idx
ON pg_string_lab.ma_san_pham (sku varchar_pattern_ops);
```

Do not automatically create two indexes on every string column. Each index consumes disk space and adds write overhead; use `EXPLAIN` to test against real workloads.

### 11.3. Substring Searches and ILIKE

```sql
SELECT *
FROM pg_string_lab.noi_dung
WHERE mo_ta ILIKE '%khuyến mãi%';
```

Searching for a substring **in the middle** of text usually does not fit a basic B-tree. PostgreSQL offers the `pg_trgm` extension supporting GIN/GiST indexes for certain pattern searches, though installing extensions and creating indexes requires permissions, disk space, and proper evaluation.

This is a **text-search strategy** question, not a reason to abandon `TEXT` and turn everything into `VARCHAR(255)`.

## 12. Long String Storage, TOAST, and Performance

### 12.1. TEXT Does Not Mean All Content Sits Inline in One Page

PostgreSQL manages large string values via variable-length storage and can use **TOAST** (*The Oversized-Attribute Storage Technique*) to compress or move oversized values into an auxiliary storage table.

Key points:

- Both `TEXT` and `VARCHAR` can use TOAST when appropriate.
- `CHAR(n)` does not turn every value into a fixed-size physical structure regardless of content.
- Short strings are not necessarily compressed or moved to a TOAST table.
- Whether TOAST triggers depends on tuple size, storage strategy, and PostgreSQL's row layout—not merely one column's character count.

Inspect **memory, I/O, table size, and query plans** instead of guessing from type names.

### 12.2. Measuring Actual Table Size

```sql
SELECT
    pg_size_pretty(
        pg_table_size('pg_string_lab.loai_chuoi')
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('pg_string_lab.loai_chuoi')
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('pg_string_lab.loai_chuoi')
    ) AS total_size;
```

Table size includes overhead, metadata, partially filled pages, TOAST, and other storage components as defined by PostgreSQL. Do not treat `SUM(octet_length(column))` as the table's real on-disk file size.

### 12.3. Why Is VARCHAR(255) Not an "Optimal Benchmark" in PostgreSQL?

Some other platforms or DBMSs had specific limits or implementation quirks tied to 255. In PostgreSQL, `VARCHAR(255)` offers no universal performance advantage over `TEXT`. Choosing n should be based on the **data contract** (e.g., display names capped at 100 characters), not by applying a familiar number to every column.

### 12.4. Does CHAR(n) Actually Use Exactly n Bytes?

Never equate **n characters** with **n bytes** when data contains multi-byte Unicode. PostgreSQL appends padding spaces to reach **character** length n; actual characters may occupy 2–4 bytes in UTF8, and tuples also carry overhead.

For example, `CHAR(5)` holding two multi-byte accented letters has a different byte size than `CHAR(5)` holding two ASCII letters, even though both are padded to five characters.

## 13. Changing Column Types or Limits on Existing Data

A project might start with `VARCHAR(20)` and want to expand to `VARCHAR(100)`, or have `TEXT` and want to enforce a 30-character limit. Avoid data loss from explicit truncation casts or prolonged table locks.

### 13.1. Inspecting Data Before Tightening a Limit

Suppose `pg_string_lab.ho_so` already contains rows:

```sql
SELECT
    id,
    char_length(display_name) AS do_dai,
    display_name
FROM pg_string_lab.ho_so
WHERE char_length(display_name) > 30
ORDER BY do_dai DESC, id;
```

If rows are returned, altering to `VARCHAR(30)` will either fail or require a policy for handling over-length values. Do not blindly truncate inputs to 30 characters, as the discarded suffix may be important.

### 13.2. Altering Types with ALTER TABLE

In a practice environment:

```sql
ALTER TABLE pg_string_lab.ho_so
    ALTER COLUMN display_name TYPE VARCHAR(100);
```

This command only makes sense when existing data fits the new bound. On large tables, altering a type/typmod may acquire locks and in some cases require rewriting table data or indexes; check your PostgreSQL version and plan maintenance windows carefully.

**Note:** If later shrinking from `VARCHAR(100)` down to `VARCHAR(30)`, long rows must be identified and handled deliberately first. Not recommended:

```sql
-- Do not use as a default "data fix":
-- ALTER TABLE ... ALTER COLUMN display_name TYPE VARCHAR(30)
-- USING left(display_name, 30);
```

Because `left(...,30)` intentionally chops off the end without any business warning.

### 13.3. Keeping TEXT and Adding CHECK Can Express Rules More Cleanly

If the requirement is simply "no more than 100 characters":

```sql
ALTER TABLE pg_string_lab.noi_dung
ADD CONSTRAINT chk_tieu_de_max
CHECK (tieu_de IS NULL OR char_length(tieu_de) <= 100);
```

`TEXT` plus `CHECK` expresses rules as expressions, which is convenient when combining multiple conditions. However, adding a new constraint on a large table can scan existing rows and impact operations; `CHECK` is not "free". For migrations, choose an appropriate validation and rollout strategy.

### 13.4. Converting CHAR(n) to TEXT/VARCHAR Requires Caution

When converting data from `CHAR(n)` to a variable-length string type, PostgreSQL typically strips trailing spaces according to `CHAR(n)` cast semantics. If a legacy system intentionally encoded information using trailing spaces, **you cannot automatically recover the original input**: those spaces became indistinguishable from `CHAR(n)` padding.

Before migrating, verify expected post-conversion data and test queries, unique constraints, and indexes so key semantics do not shift silently.

## 14. Inspecting Column Types and Limits via System Catalogs

In real databases, engineers often do not have the original DDL files for every table. PostgreSQL provides catalogs for inspection.

### 14.1. information_schema.columns

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'pg_string_lab'
  AND table_name = 'loai_chuoi'
ORDER BY ordinal_position;
```

Expected output:

| column_name | data_type | character_maximum_length |
|---|---|---:|
| id | integer | `NULL` |
| ma_co_dinh | character | 6 |
| ma_gioi_han | character varying | 6 |
| ghi_chu | text | `NULL` |

`character_maximum_length IS NULL` on `TEXT` does not mean the column **cannot store data**: it simply means no n limit is declared in the data type.

### 14.2. pg_catalog.format_type

```sql
SELECT
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS declared_type,
    a.attnotnull AS not_null
FROM pg_attribute AS a
WHERE a.attrelid = 'pg_string_lab.loai_chuoi'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

`format_type` uses internal OID/typmod metadata to produce a readable type representation, such as `character(6)` or `character varying(6)`.

`atttypmod` is internal metadata—do not assume its raw number always equals n; use `format_type` or `information_schema.columns` to view declarations cleanly.

### 14.3. psql \d

In `psql`:

```text
\d pg_string_lab.loai_chuoi
```

This is a `psql` meta-command, not plain SQL to execute over JDBC. It is handy for inspecting column types, constraints, and indexes during hands-on work.

## 15. Designing String Data from a Java/JDBC Perspective

Java applications commonly use `String` to pass character data to PostgreSQL via `PreparedStatement`. However, **`String.length()` in Java counts UTF-16 code units**, whereas `char_length()` in PostgreSQL UTF8 counts characters according to the database's Unicode representation. For characters outside the BMP such as emojis, the two counts can differ.

### 15.1. Example of Length Mismatch Between Java and PostgreSQL

In Java:

```java
String emoji = "😀";

System.out.println(emoji.length());                  // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
```

In PostgreSQL UTF8:

```sql
SELECT
    char_length('😀') AS so_ky_tu,
    octet_length('😀') AS so_byte;
```

PostgreSQL reports 1 character and 4 bytes. Therefore, if an API enforces "at most 20 characters per PostgreSQL's `char_length`", relying solely on Java `String.length() <= 20` may reject valid inputs unnecessarily or fail to match Unicode rules.

Java offers `codePointCount` to align more closely with code-point counting; however, both still differ from "visible grapheme clusters" in strings with complex combining marks or joined emojis.

### 15.2. INSERT via PreparedStatement

Example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductRepository {
    public void insertProduct(
            Connection connection,
            String sku,
            String description
    ) throws SQLException {
        String sql = """
            INSERT INTO pg_string_lab.ma_san_pham (sku)
            VALUES (?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setString(1, sku);
            statement.executeUpdate();
        }
    }
}
```

`PreparedStatement` separates user data from SQL syntax, helping prevent SQL injection when parameters are bound properly. Regardless of Java validation, the `VARCHAR(8)` limit on the practice table is still enforced by PostgreSQL when the data is written.

The `description` parameter in this example signature is unused; if you want to store a description, add a corresponding column and bind the parameter, or remove the unused parameter for cleanliness. In real projects, keep method signatures and SQL aligned.

### 15.3. Handling Data-Too-Long Errors

When inserting a string exceeding `VARCHAR(n)` outside the trailing-space exception, PostgreSQL returns SQLSTATE **22001** (*string_data_right_truncation*).

The application should:

1. Validate length at input and return clear messages to users.
2. Keep DB constraints as the final safety net.
3. Catch the specific SQLSTATE when distinguishing validation failures from connection errors.
4. Avoid automatically using `substring` or `::varchar(n)` to truncate strings unless explicitly required by business rules.

Do not log full sensitive payloads just because of a length error; log the field name, expected limit, and appropriate diagnostic context.

## 16. Data Type Selection Scenarios

### 16.1. Order Codes Up to 20 Characters

If an order code must always stay under 20 characters with variable length:

```sql
CREATE TABLE pg_string_lab.don_hang (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(20) NOT NULL UNIQUE,
    note TEXT
);
```

`VARCHAR(20)` expresses the character cap and `UNIQUE` prevents duplicate codes under the active collation/operator semantics. If codes follow an exact pattern like `ORD-2026-00001`, also enforce a regex or controlled code generator.

### 16.2. Postal Codes Should Not Be INTEGER

For example, a postal code may start with `0`. Storing it as `INTEGER` strips the leading `0`.

```sql
CREATE TABLE pg_string_lab.dia_chi (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    postal_code TEXT,
    address_line TEXT NOT NULL
);
```

Store it as a string type, then validate length/format per country rather than treating every postal code as a computable number.

### 16.3. Long Descriptions

If a description can span multiple paragraphs, `TEXT` is generally more suitable than `CHAR(1000)`. Choosing `CHAR(1000)` for a 20-character description causes massive padding and unwanted comparison semantics.

### 16.4. Exact Two-Character Codes

If the rule strictly requires **exactly two uppercase ASCII letters**:

```sql
CREATE TABLE pg_string_lab.ma_vung (
    region_code TEXT PRIMARY KEY,
    CONSTRAINT chk_region_code
        CHECK (region_code COLLATE "C" ~ '^[A-Z]{2}$')
);
```

This regex enforces both format and length—far clearer than relying on `CHAR(2)` to pad a single-letter input. If valid codes follow different language/standard rules, adjust the regex to match the business domain.

## 17. Common Misconceptions

**1. "`VARCHAR(20)` reserves exactly 20 bytes for every row."** False. It is a 20-character limit; shorter values are stored with variable length.

**2. "`CHAR(20)` always takes exactly 20 bytes."** False with multi-byte Unicode and storage overhead; it means padding to character length n.

**3. "`CHAR(n)` guarantees the user entered exactly n characters."** False. Shorter strings are padded with spaces.

**4. "`CHAR(n)` has identical comparison semantics to `TEXT`."** False. Trailing spaces are treated differently in `character(n)` comparisons.

**5. "As long as a column is `VARCHAR(n)`, data can never be truncated."** False. PostgreSQL has an exception that trims excess trailing spaces, and explicit casts can truncate strings.

**6. "`VARCHAR(255)` is always faster than `TEXT`."** There is no such default advantage in PostgreSQL.

**7. "`TEXT` is unlimited."** False. It declares no n limit, yet remains bounded by internal value size and resource limits.

**8. "`CHAR` without n is also unlimited."** False. `CHAR` without n is equivalent to `CHAR(1)`.

**9. "`char_length` always equals `octet_length`."** False with multi-byte Unicode and with `CHAR(n)` padding spaces.

**10. "`char_length` counts visual characters on screen."** Not always. Unicode combining marks and joined emojis can consist of multiple code points for one symbol.

**11. "Java `String.length()` always equals PostgreSQL `char_length()`."** False for code points outside the BMP and certain Unicode representations.

**12. "`NOT NULL` blocks empty strings."** False. `''` is distinct from `NULL` in PostgreSQL.

**13. "`btrim` strips all types of Unicode whitespace."** No; the default form primarily strips ordinary space characters—more explicit rules are needed for other characters.

**14. "`UNIQUE` on `TEXT` always distinguishes all byte-different strings."** Not unconditionally under nondeterministic collations; comparison rules must be checked.

**15. "`VARCHAR(n)` makes `LIKE '%x%'` searches fast."** False. Index strategy depends on query patterns and operator classes/extensions.

**16. "Running `ALTER COLUMN TYPE VARCHAR(n)` is always safe."** No. Over-length rows, table locks, index rebuilds, or accidental truncation when casting can occur.

**17. "A `TEXT` column definitely uses more disk space than `VARCHAR(50)`."** No. Given the same content and storage conditions, both variable-length string types have similar overhead.

**18. "Padding spaces never affect queries."** False. They affect byte measurements, comparison semantics, and pattern matching/casting behavior.

## 18. Practice Exercises with Answers

### Exercise 1 — Counting Characters and Bytes

In a UTF8 database, predict:

```sql
SELECT
    char_length('é') AS a,
    octet_length('é') AS b,
    char_length('😀') AS c,
    octet_length('😀') AS d;
```

**Answer:** `a=1`, `b=2`, `c=1`, `d=4`. `CHAR_LENGTH` measures characters; `OCTET_LENGTH` measures bytes.

### Exercise 2 — Does CHAR(5) Pad?

```sql
SELECT
    char_length('AB'::CHAR(5)) AS a,
    octet_length('AB'::CHAR(5)) AS b;
```

**Answer:** With ASCII/UTF8, `a=2` and `b=5`. The character type includes space padding even though `char_length` excludes it.

### Exercise 3 — Comparing Strings with Trailing Spaces

```sql
SELECT
    'AB'::CHAR(4) = 'AB  '::CHAR(4) AS a,
    'AB'::TEXT = 'AB  '::TEXT AS b;
```

**Answer:** Under a standard deterministic collation, `a=true` and `b=false`.

### Exercise 4 — Storing Over-Length Values

A `VARCHAR(4)` column receives in turn:

1. `'ABCDE'`.
2. `'ABCD  '`.
3. `'ABCDE'::VARCHAR(4)`.

**Answer:** Case 1 raises a value-too-long error; Case 2 stores `ABCD` because all excess characters are spaces; Case 3 is truncated to `ABCD` during the explicit cast.

### Exercise 5 — Display Name Must Not Be Blank

**Requirement:** a `name` column of at most 80 characters, rejecting `NULL`, empty strings, or strings made only of ASCII spaces.

**Answer:**

```sql
CREATE TABLE pg_string_lab.profile_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    CONSTRAINT chk_profile_name
        CHECK (
            char_length(name) <= 80
            AND char_length(btrim(name)) > 0
        )
);
```

If tabs/Unicode whitespace must also be rejected or grapheme clusters limited, stronger validation rules are required.

### Exercise 6 — Exact Two-Character Code

**Requirement:** store a region code of exactly two ASCII letters `A–Z`, rejecting lowercase letters or spaces.

**Answer:** `TEXT` plus `CHECK (code COLLATE "C" ~ '^[A-Z]{2}$')`, or an appropriate string type with an equivalent constraint. `CHAR(2)` alone is insufficient to reject single-character inputs.

### Exercise 7 — Why VARCHAR Is Not a Speedup Trick

A team wants to change `description TEXT` to `VARCHAR(255)` solely to speed up `LIKE '%sale%'`.

**Answer:** An n limit does not alter leading-wildcard pattern matching. Analyze the query, choose an appropriate index/operator class or text-search solution, and also check whether descriptions exceeding 255 characters would be lost or cause errors.

### Exercise 8 — Fixing a Java Length Mismatch

Java reports `"😀".length() == 2` while PostgreSQL UTF8 reports `char_length('😀') == 1`.

**Answer:** Java `String.length()` counts UTF-16 code units; PostgreSQL `char_length()` counts characters/code points in the database encoding. Use `codePointCount` in Java if the contract specifies code points, or define dedicated logic if counting grapheme clusters.

### Exercise 9 — Checking Data Before Migration

**Requirement:** find `display_name` values longer than 30 characters before changing the column type to `VARCHAR(30)`.

**Answer:**

```sql
SELECT id, display_name, char_length(display_name) AS len
FROM pg_string_lab.ho_so
WHERE char_length(display_name) > 30
ORDER BY len DESC, id;
```

Do not truncate data just to force a migration through without a business rule.

### Exercise 10 — Measuring Trimmed Text Length

`'  ABC  '` is inserted into a `TEXT` column.

**Question:** What is `char_length` before and after `btrim`?

**Answer:** **7** before, **3** after. `btrim` by default strips ordinary spaces from both ends, not internal spaces.

### Exercise 11 — Why Is CHAR(2) Unsuitable for a Mandatory 2-Character Code?

A user enters `'A'` into `code CHAR(2)`, and PostgreSQL stores the padded form `'A '`.

**Answer:** `CHAR(2)` raises no error because strings shorter than n are valid; it pads them. When exactly two meaningful characters are required, validate length/format using `TEXT` or `VARCHAR` with appropriate constraints.

### Exercise 12 — TEXT or Unbounded VARCHAR?

**Requirement:** a notes column with no specific business limit n, ranging from a few words to several paragraphs.

**Answer:** `TEXT` is the natural choice in PostgreSQL. `VARCHAR` without n has the same unbounded variable-length storage behavior, yet `TEXT` is generally clearer and easier to read.

## 19. String Type Selection Checklist

When designing a new column, follow this process:

1. **Identify the nature of the data:** is it prose text, an identifier, email, UUID, timestamp, or another specialized semantic type?
2. **Define the bound:** max n characters, exact n characters, max n bytes, or max n grapheme clusters? These are distinct requirements.
3. **Choose whitespace semantics:** must leading/trailing spaces be preserved accurately? If yes, avoid the surprises of `CHAR(n)`.
4. **Pick the type:** use `TEXT` when no typmod is needed; `VARCHAR(n)` when a character limit is an explicit contract boundary; only use `CHAR(n)` when blank-padding is genuinely desired.
5. **Add constraints:** `NOT NULL`, `CHECK`, `UNIQUE`, and foreign keys reflecting data semantics. Do not expect a type name alone to handle all validation.
6. **Account for encoding and normalization:** in UTF8, byte count can exceed character count; combining Unicode sequences can affect length.
7. **Design indexing for queries:** equality, prefix, substring search, and collation require different strategies.
8. **Audit existing data before migrations:** avoid accidental truncation or altered uniqueness when migrating away from `CHAR(n)`.
9. **Align APIs/drivers:** Java `String.length()`, frontend limits, and PostgreSQL `char_length` may not measure the same unit.
10. **Benchmark realistically:** use `EXPLAIN`, size functions, and representative workloads; never optimize based on the myth that "VARCHAR(255) is faster than TEXT".

## 20. Summary

In PostgreSQL, **`CHAR(n)` is a blank-padded type**, whereas **`VARCHAR(n)` caps length at n characters without padding**; **`TEXT` and unbounded `VARCHAR`** store variable-length strings without a declared n limit. `CHAR(n)` has no default performance advantage over the other types.

**Length must be interpreted accurately according to your goal:**

- `char_length` / `length`: counts characters per function semantics and input type.
- `octet_length`: counts bytes in the active encoding.
- `bit_length`: counts bits.
- `pg_column_size`: measures physical storage size, not a business character limit.

When data requirements are strict, combine **an appropriate string type + `CHECK`/`UNIQUE` + normalization rules + boundary validation**. Watch out for **`CHAR(n)` trailing spaces**, **explicit casts that silently truncate**, **multi-byte Unicode**, and **collations** so invalid data never slips past successful SQL statements.

Official documentation references:

- [PostgreSQL — Character Types](https://www.postgresql.org/docs/current/datatype-character.html).
- [PostgreSQL — String Functions and Operators](https://www.postgresql.org/docs/current/functions-string.html).
- [PostgreSQL — Collation Support](https://www.postgresql.org/docs/current/collation.html).
- [PostgreSQL — TOAST Storage](https://www.postgresql.org/docs/current/storage-toast.html).
