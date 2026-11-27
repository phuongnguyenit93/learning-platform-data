# String Functions: SUBSTR, INSTR, LENGTH, TRIM, and REPLACE in Oracle Database

When processing business data, strings often need to be split, searched for positions, measured for length, stripped of leading/trailing whitespace, or have parts of their content replaced. Oracle Database provides many SQL functions for these operations. The five foundational functions to master are **`SUBSTR`, `INSTR`, `LENGTH`, `TRIM`, and `REPLACE`**.

These functions can be combined in a `SELECT` statement, `WHERE` clause, computed column expression, `UPDATE` statement, or data-loading pipeline. However, knowing the syntax alone is not enough: SQL authors must distinguish **characters from bytes**, starting positions from occurrence counts, regular spaces from special whitespace characters, and empty strings from `NULL` under Oracle semantics.

This lesson uses an illustrative table containing product codes, email addresses, file names, and strings with Vietnamese diacritics. The examples focus on practical SQL while explaining how to avoid errors when data arrives from different applications, encodings, or NLS settings.

## 1. Overview of the five functions

| Function | Purpose | Short Example | Result |
|---|---|---|---|
| `SUBSTR(char, position [, length])` | Extract part of a string by position | `SUBSTR('ORACLE', 2, 3)` | `RAC` |
| `INSTR(char, substring [, position [, occurrence]])` | Find the position of a substring | `INSTR('A-B-C', '-', 2)` | `4` |
| `LENGTH(char)` | Count length in characters | `LENGTH('ORACLE')` | `6` |
| `TRIM([LEADING \| TRAILING \| BOTH] [trim_char] FROM char)` | Remove specified characters from string edges | `TRIM('  SQL  ')` | `SQL` |
| `REPLACE(char, search_string [, replacement_string])` | Replace all occurrences of a substring | `REPLACE('A-B-A', 'A', 'X')` | `X-B-X` |

Common characteristics:

- These are **character string processing functions**; they do not validate the business meaning of a string on their own.
- Oracle provides byte-based or Unicode-unit variants such as `SUBSTRB`, `INSTRB`, `LENGTHB`, along with `C`, `2`, and `4` variants in certain function groups.
- Results depend on input data types, character sets, and sometimes collation/NLS rules.
- Oracle currently treats zero-length character strings as `NULL` in standard SQL. Therefore, `LENGTH('')` returns `NULL`, not 0.
- Use bind variables and appropriate data types; never concatenate raw user input directly into SQL statements.

## 2. Preparing the practice table

Create a small table in a lab schema:

```sql
CREATE TABLE string_lab (
    item_id       NUMBER(10) CONSTRAINT pk_string_lab PRIMARY KEY,
    product_code  VARCHAR2(40 CHAR),
    customer_name VARCHAR2(100 CHAR),
    email_address VARCHAR2(160 CHAR),
    file_name     VARCHAR2(160 CHAR),
    note_text     VARCHAR2(300 CHAR)
);

INSERT INTO string_lab VALUES (
    1,
    'PRD-2026-001',
    '  Nguyễn An  ',
    'an.nguyen@example.test',
    'invoice_2026_11.csv',
    'Oracle SQL string functions'
);

INSERT INTO string_lab VALUES (
    2,
    'PRD-2026-002',
    'Trần Bình',
    'binh.tran@example.test',
    'report.final.v2.xlsx',
    'Học SQL với dữ liệu tiếng Việt'
);

INSERT INTO string_lab VALUES (
    3,
    'SRV-DB-015',
    'Lê Chi',
    'chi@example.test',
    'README',
    'No file extension'
);

INSERT INTO string_lab VALUES (
    4,
    'PRD-2026-010',
    'Đỗ Dung',
    'dung@example.test',
    'archive.tar.gz',
    'Two dots in file name'
);

COMMIT;
```

The names and emails use the `example.test` domain for illustration, not real contact addresses. Strings with diacritics help demonstrate the difference between character counts and byte counts in multi-byte character sets like AL32UTF8.

View the data:

```sql
SELECT item_id, product_code, customer_name, email_address, file_name
FROM string_lab
ORDER BY item_id;
```

## 3. SUBSTR — extracting part of a string

### 3.1. Syntax and parameters

```sql
SUBSTR(char, position [, substring_length])
```

- `char`: source string.
- `position`: starting position, 1-based from the beginning of the string.
- `substring_length`: number of characters to extract; if omitted, Oracle extracts from the starting position to the end of the string.

Example:

```sql
SELECT SUBSTR('ORACLE DATABASE', 1, 6) AS part_1,
       SUBSTR('ORACLE DATABASE', 8, 8) AS part_2,
       SUBSTR('ORACLE DATABASE', 8) AS rest
FROM dual;
```

Result:

| PART_1 | PART_2 | REST |
|---|---|---|
| `ORACLE` | `DATABASE` | `DATABASE` |

### 3.2. Positive position, negative position, and position 0

Oracle counts positions starting from 1:

```sql
SELECT SUBSTR('DATABASE', 1, 4) AS from_start,
       SUBSTR('DATABASE', 5, 4) AS from_middle,
       SUBSTR('DATABASE', -4, 4) AS from_end,
       SUBSTR('DATABASE', -4) AS rest_from_end
FROM dual;
```

| Expression | Result | Explanation |
|---|---|---|
| `SUBSTR('DATABASE', 1, 4)` | `DATA` | Starts at the first character |
| `SUBSTR('DATABASE', 5, 4)` | `BASE` | Starts at the 5th character |
| `SUBSTR('DATABASE', -4, 4)` | `BASE` | Counts starting position backward from the end of the string |
| `SUBSTR('DATABASE', -4)` | `BASE` | Extracts from the 4th character from the end to the end |
| `SUBSTR('DATABASE', 0, 4)` | `DATA` | Oracle treats position 0 the same as position 1 |

The negative-position rule is useful when extracting a suffix without knowing the exact prefix length, such as a file extension:

```sql
SELECT file_name,
       SUBSTR(file_name, -3) AS last_three_chars
FROM string_lab
ORDER BY item_id;
```

However, taking the last three characters is **not equivalent** to extracting a file extension based on the last dot. For instance, `report.final.v2.xlsx` has the extension `xlsx`, whereas the last three characters are `lsx`. Use `INSTR` combined with `SUBSTR` when parsing by delimiter.

### 3.3. Invalid length or exceeding the end of the string

```sql
SELECT SUBSTR('ORACLE', 4, 20) AS beyond_end,
       SUBSTR('ORACLE', 4, 0) AS zero_length,
       SUBSTR('ORACLE', 4, -2) AS negative_length
FROM dual;
```

- If the length exceeds the remaining string, the function returns the remaining substring.
- If `substring_length` is less than 1, `SUBSTR` returns `NULL`.
- A negative length does not mean "go backward"; to start from the end, use a **negative position**, while keeping length positive.

In SQL, a function returning `NULL` can cause string concatenation or filter predicates to behave unexpectedly. If inputs are user-supplied, validate both position and length before using them.

### 3.4. Extracting code segments by delimiter

For code `PRD-2026-001`:

```sql
SELECT product_code,
       SUBSTR(product_code, 1, 3) AS product_group,
       SUBSTR(product_code, 5, 4) AS product_year,
       SUBSTR(product_code, 10, 3) AS sequence_no
FROM string_lab
WHERE item_id = 1;
```

Illustrative result:

| PRODUCT_GROUP | PRODUCT_YEAR | SEQUENCE_NO |
|---|---|---|
| `PRD` | `2026` | `001` |

This works when the code format is fixed. If delimiters or segment lengths vary, do not hardcode positions; use `INSTR`, a parsing rules table, or an appropriate regular expression function.

### 3.5. SUBSTR with multi-byte strings

`SUBSTR` counts characters in the input character set, not UTF-8 bytes. For example:

```sql
SELECT SUBSTR('Tiếng Việt', 1, 5) AS first_five_chars,
       LENGTH('Tiếng Việt') AS char_length,
       LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
```

On an AL32UTF8 database, accented characters can occupy multiple bytes. `SUBSTR('Tiếng Việt', 1, 5)` still extracts five characters by character semantics without splitting inside a UTF-8 code point. When interfacing with byte-oriented systems, distinguish `SUBSTR` from `SUBSTRB`.

## 4. INSTR — finding the position of a substring

### 4.1. Syntax

```sql
INSTR(
    string,
    substring
    [, position
    [, occurrence]]
)
```

- `string`: the string to search within.
- `substring`: the substring to locate.
- `position`: starting search position; defaults to 1.
- `occurrence`: which occurrence to return; defaults to 1.

The result is the **1-based starting position** of the requested occurrence. If not found, the function returns **0**.

Example:

```sql
SELECT INSTR('ORACLE DATABASE', 'A') AS first_a,
       INSTR('ORACLE DATABASE', 'A', 1, 2) AS second_a,
       INSTR('ORACLE DATABASE', 'Z') AS missing_z
FROM dual;
```

| FIRST_A | SECOND_A | MISSING_Z |
|---:|---:|---:|
| 3 | 10 | 0 |

The second result is 10 because the letter `A` appears for the second time at position 10 in the source string.

### 4.2. Finding delimiters

Get the position of `@` in an email address:

```sql
SELECT email_address,
       INSTR(email_address, '@') AS at_position
FROM string_lab
ORDER BY item_id;
```

Get the positions of the first and last dots in a file name:

```sql
SELECT file_name,
       INSTR(file_name, '.') AS first_dot,
       INSTR(file_name, '.', -1) AS last_dot
FROM string_lab
ORDER BY item_id;
```

For `archive.tar.gz`, the first and last dots are at different positions. That is why you should specify **occurrence** or use a negative position when extracting an extension after the last dot.

### 4.3. Negative position: searching backward from the end

If `position` is negative, Oracle counts backward from the end of the string and searches toward the beginning. The returned value is still the position counted from the start of the string:

```sql
SELECT INSTR('ONE-TWO-THREE', '-', 1, 2) AS second_from_left,
       INSTR('ONE-TWO-THREE', '-', -1, 1) AS first_from_right,
       INSTR('ONE-TWO-THREE', '-', -1, 2) AS second_from_right
FROM dual;
```

| SECOND_FROM_LEFT | FIRST_FROM_RIGHT | SECOND_FROM_RIGHT |
|---:|---:|---:|
| 7 | 7 | 4 |

For the string `ONE-TWO-THREE`:

- The first hyphen is at position 4.
- Is the second hyphen at position 8? Let's count accurately: `O(1) N(2) E(3) -(4) T(5) W(6) O(7) -(8) T(9) H(10) R(11) E(12) E(13)`.
- Therefore, the expressions return positions 8 and 4, respectively.

For this example, the result table should be read against the actual character positions (1-based); do not confuse "second from the left" with "position counted from the end".

### 4.4. INSTR returns 0 when not found — watch out when combining with SUBSTR

A common bug:

```sql
SELECT SUBSTR(email_address, 1, INSTR(email_address, '@') - 1)
       AS email_user
FROM string_lab;
```

If an email has no `@`, `INSTR` returns 0; the length passed to `SUBSTR` becomes -1, yielding `NULL`. This can inadvertently make malformed data look like missing data. Check for the delimiter first:

```sql
SELECT email_address,
       CASE
           WHEN INSTR(email_address, '@') > 1
           THEN SUBSTR(
                    email_address,
                    1,
                    INSTR(email_address, '@') - 1
                )
           ELSE NULL
       END AS email_user
FROM string_lab;
```

This only splits the part before `@`; **it is not full email validation**. An address with multiple `@` characters, misplaced dots, or a nonexistent domain still requires dedicated validation rules.

### 4.5. INSTR and case sensitivity

Under standard matching rules, `INSTR` is case-sensitive:

```sql
SELECT INSTR('Oracle Database', 'oracle') AS lower_match,
       INSTR(LOWER('Oracle Database'), LOWER('ORACLE')) AS normalized_match
FROM dual;
```

The first expression returns 0 under default case-sensitive matching; the second matches because both sides are normalized to lowercase. For languages with complex casing rules, do not rely on `LOWER` as a universal linguistic normalizer; consider collation/NLS settings and actual comparison requirements.

## 5. LENGTH — measuring string length

### 5.1. LENGTH counts characters

```sql
LENGTH(char)
```

Example:

```sql
SELECT LENGTH('ORACLE') AS length_ascii,
       LENGTH('Tiếng Việt') AS length_vietnamese,
       LENGTH('A B') AS length_with_space
FROM dual;
```

`LENGTH` returns the number of characters using character-set semantics; embedded spaces and trailing spaces are counted. For `VARCHAR2`, stored space characters are part of the data and are included in the count.

### 5.2. LENGTHB counts bytes

```sql
SELECT LENGTH('ABC') AS chars_abc,
       LENGTHB('ABC') AS bytes_abc,
       LENGTH('Tiếng Việt') AS chars_vietnamese,
       LENGTHB('Tiếng Việt') AS bytes_vietnamese
FROM dual;
```

In an AL32UTF8 database, ASCII letters typically take 1 byte, whereas accented Vietnamese characters can take multiple bytes. Therefore, `LENGTH` and `LENGTHB` can differ.

| Function | Counts By | When Does It Matter? |
|---|---|---|
| `LENGTH` | Characters | Text length limits measured in characters |
| `LENGTHB` | Bytes | Storage or transport size limits in bytes |
| `LENGTHC` | Unicode complete characters | When counting complete characters per Oracle's Unicode semantics |
| `LENGTH2` | UCS2 code points | When interfacing with systems using UCS-2 units |
| `LENGTH4` | UCS4 code points | When counting in UCS-4 units |

The `C`, `2`, and `4` variants serve specialized purposes; most standard SQL applications should start with `LENGTH` and switch to another variant only when an encoding contract requires it. Some variants have restrictions on `CLOB`/`NCLOB`; check Oracle documentation for your LOB types and database version.

### 5.3. CHAR and VARCHAR2 can yield unexpected lengths

`CHAR(n)` is a fixed-length type and is blank-padded according to SQL rules; `VARCHAR2(n)` stores variable-length strings. Example:

```sql
SELECT LENGTH(CAST('SQL' AS CHAR(10))) AS char_length,
       LENGTH(CAST('SQL' AS VARCHAR2(10))) AS varchar_length
FROM dual;
```

A `CHAR(10)` value can be padded with spaces to length 10, whereas `VARCHAR2` holds only the three characters `SQL`. Thus, when inspecting legacy data, check the column data type before concluding a string has "extra trailing spaces".

### 5.4. Empty strings and NULL

In Oracle SQL, a zero-length character string is treated as `NULL`:

```sql
SELECT LENGTH('') AS empty_length,
       LENGTH(NULL) AS null_length,
       LENGTH(' ') AS one_blank_length
FROM dual;
```

The first two expressions return `NULL`; the last returns 1. This matters when writing:

```sql
WHERE LENGTH(product_code) = 0
```

This predicate will not find empty strings as it might in some other RDBMSs; use `IS NULL` to check for NULL values:

```sql
WHERE product_code IS NULL
```

### 5.5. Length of LOB strings

For `CLOB`/`NCLOB`, `LENGTH` can return the character count of the LOB content as supported by Oracle. `LENGTHB` is not a general-purpose choice for LOBs in multi-byte character set environments. When working with large LOBs, look at `DBMS_LOB.GETLENGTH` and LOB APIs rather than trying to convert the entire content to `VARCHAR2`.

Example:

```sql
SELECT DBMS_LOB.GETLENGTH(document_body) AS document_length
FROM document_store
WHERE document_id = :document_id;
```

The unit and semantics of the length depend on the LOB type; for CLOB, the result is in characters, whereas for BLOB it is in bytes.

## 6. TRIM — removing leading or trailing characters

### 6.1. Syntax

```sql
TRIM(
    [LEADING | TRAILING | BOTH]
    [trim_character]
    FROM source_string
)
```

- `BOTH`: removes characters from both ends; this is the default.
- `LEADING`: removes only from the beginning.
- `TRAILING`: removes only from the end.
- `trim_character`: a single character to remove; if omitted, Oracle uses a standard space.

Example:

```sql
SELECT TRIM('  Oracle SQL  ') AS both_sides,
       TRIM(LEADING FROM '  Oracle SQL  ') AS leading_only,
       TRIM(TRAILING FROM '  Oracle SQL  ') AS trailing_only,
       TRIM(BOTH '-' FROM '---A-100---') AS hyphen_trimmed
FROM dual;
```

Result:

| BOTH_SIDES | LEADING_ONLY | TRAILING_ONLY | HYPHEN_TRIMMED |
|---|---|---|---|
| `Oracle SQL` | `Oracle SQL  ` | `  Oracle SQL` | `A-100` |

`TRIM` only strips characters from the edges. It does not remove matching characters in the middle of the string: `TRIM('A-B-A')` does not remove the middle hyphens.

### 6.2. Trimming a specific character

Example stripping leading and trailing `0` characters from a code:

```sql
SELECT TRIM(BOTH '0' FROM '0001234000') AS trimmed_code,
       TRIM(LEADING '0' FROM '0001234000') AS leading_zero_removed,
       TRIM(TRAILING '0' FROM '0001234000') AS trailing_zero_removed
FROM dual;
```

The results are `1234`, `1234000`, and `0001234`, respectively. This differs from `REPLACE`, which removes or replaces every occurrence, including those in the middle of the string.

In SQL `TRIM` syntax, the trim character must be **a single character**; if you need to strip a set of multiple distinct characters from the edges, use `LTRIM`/`RTRIM`. Do not write `TRIM(BOTH 'abc' FROM ...)` expecting to "remove any a, b, or c"; `TRIM` does not accept a character set like `LTRIM`/`RTRIM`.

### 6.3. TRIM does not mean stripping all whitespace

By default, `TRIM` removes standard spaces (blanks). It does not automatically remove every character that looks like whitespace to the human eye, including tabs, line feeds, carriage returns, non-breaking spaces, or other Unicode whitespace characters.

Example:

```sql
SELECT LENGTH(' A ') AS before_length,
       LENGTH(TRIM(' A ')) AS after_length,
       LENGTH('A' || CHR(9)) AS tab_length,
       LENGTH(TRIM('A' || CHR(9))) AS tab_after_trim
FROM dual;
```

A trailing tab is not treated as a standard space by default `TRIM`. If data arrives from files or external systems, identify the exact characters that need normalization.

You can strip edge tabs/CR/LF by nesting functions:

```sql
SELECT TRIM(
           BOTH CHR(9) FROM
           TRIM(
               BOTH CHR(10) FROM
               TRIM(BOTH CHR(13) FROM source_text)
           )
       ) AS normalized_edges
FROM imported_text;
```

This illustrates handling specific ASCII control characters; it is not a general Unicode trimmer, and nesting order can matter when characters are interleaved. For NBSP, specify the character explicitly using a character-set-appropriate expression such as `UNISTR('\00A0')`, and handle it per the data contract.

### 6.4. How LTRIM and RTRIM differ from TRIM

`LTRIM` and `RTRIM` accept a **set of characters** to strip consecutively from the edges:

```sql
SELECT LTRIM('000ABC', '0') AS left_zero_removed,
       RTRIM('ABCxxx', 'x') AS right_x_removed,
       LTRIM('xyxyABC', 'xy') AS left_set_removed
FROM dual;
```

In `LTRIM('xyxyABC', 'xy')`, Oracle strips leading characters belonging to the set `x` or `y` until another character is encountered. It does not match and remove the exact substring `'xy'` pairwise.

| Function | Behavior |
|---|---|
| `TRIM(BOTH 'x' FROM s)` | Strips a single character `x` from both ends |
| `LTRIM(s, 'xyz')` | Strips consecutive leading characters in the set `x`, `y`, `z` |
| `RTRIM(s, 'xyz')` | Strips consecutive trailing characters in the set `x`, `y`, `z` |

If the requirement is to remove an **exact multi-character string** from the start or end, combine `SUBSTR`/`INSTR` or another approach; do not confuse it with the character-set behavior of `LTRIM`/`RTRIM`.

## 7. REPLACE — replacing all occurrences

### 7.1. Syntax

```sql
REPLACE(char, search_string [, replacement_string])
```

- `char`: source string.
- `search_string`: substring to search for.
- `replacement_string`: replacement string; if omitted or NULL, all matching occurrences are removed from the string.

Example:

```sql
SELECT REPLACE('A-B-A-B', 'A', 'X') AS replace_a,
       REPLACE('A-B-A-B', '-', '/') AS replace_delimiter,
       REPLACE('A-B-A-B', 'A') AS remove_a
FROM dual;
```

| REPLACE_A | REPLACE_DELIMITER | REMOVE_A |
|---|---|---|
| `X-B-X-B` | `A/B/A/B` | `-B--B` |

`REPLACE` replaces **all** matching occurrences of the substring, not just the first one. It does not support an occurrence parameter like `INSTR`.

### 7.2. Removing or normalizing delimiters

Example normalizing a code by removing hyphens:

```sql
SELECT product_code,
       REPLACE(product_code, '-', '') AS compact_code
FROM string_lab
ORDER BY item_id;
```

Or replacing multiple characters by nesting calls:

```sql
SELECT REPLACE(
           REPLACE(note_text, CHR(13), ' '),
           CHR(10),
           ' '
       ) AS one_line_note
FROM string_lab;
```

Nesting `REPLACE` can be readable when there are only a few fixed rules. If dozens of replacements or pattern-based rules are needed, consider `REGEXP_REPLACE` or a dedicated normalization pipeline; regular expressions carry higher cost and complexity, so they are unnecessary for every simple case.

### 7.3. Case sensitivity and replacement characters

Example:

```sql
SELECT REPLACE('Oracle oracle ORACLE', 'oracle', 'DB')
       AS replace_lowercase
FROM dual;
```

Under standard matching rules, `REPLACE` is case-sensitive. If you want to normalize case before replacing:

```sql
SELECT REPLACE(LOWER('Oracle oracle ORACLE'), 'oracle', 'db')
       AS normalized
FROM dual;
```

The result does not preserve original casing; therefore, apply this only when business rules allow losing case information. Language-specific or collation-specific comparison requirements must be designed and tested against your Oracle configuration.

### 7.4. NULL and empty strings in REPLACE

Because Oracle treats empty strings as NULL:

- If the source string is NULL, the result is NULL.
- If `search_string` is NULL, the function returns the source string per Oracle semantics.
- If `replacement_string` is NULL or an empty string, matched occurrences are removed.

Example:

```sql
SELECT REPLACE('A-B-A', 'A', NULL) AS remove_a,
       REPLACE('A-B-A', NULL, 'X') AS null_search,
       REPLACE(NULL, 'A', 'X') AS null_source
FROM dual;
```

Do not use `REPLACE(col, 'x', '')` to "write an empty string distinct from NULL" in standard Oracle SQL; empty strings and NULL behave the same here. If business logic must distinguish "none", "unknown", and "blank string", use a separate status column or another data convention.

### 7.5. REPLACE is not REGEXP_REPLACE

`REPLACE` searches for a literal substring. For example, `REPLACE(phone, '-', '')` removes hyphens. It does not understand patterns such as "all digits" or "all non-alphabetic characters".

If the requirement is pattern-based:

```sql
SELECT REGEXP_REPLACE('AB-123-CD', '[^A-Z]', '') AS letters_only
FROM dual;
```

then `REGEXP_REPLACE` is a different function that uses regular expressions. Do not use regex for a simple literal substitution when `REPLACE` is already clear and sufficient.

## 8. Combining INSTR and SUBSTR to split fields

### 8.1. Extracting the part before @ in an email

```sql
SELECT email_address,
       SUBSTR(
           email_address,
           1,
           INSTR(email_address, '@') - 1
       ) AS local_part
FROM string_lab
WHERE INSTR(email_address, '@') > 1;
```

`INSTR` finds the delimiter; `SUBSTR` extracts the portion before it. The `WHERE` predicate filters out cases with a missing `@` or `@` at the very first position. This is a string-parsing example, not an RFC-compliant email validator.

### 8.2. Extracting the domain after @

```sql
SELECT email_address,
       SUBSTR(
           email_address,
           INSTR(email_address, '@') + 1
       ) AS domain_part
FROM string_lab
WHERE INSTR(email_address, '@') > 0;
```

### 8.3. Extracting a file extension using the last dot

```sql
SELECT file_name,
       CASE
           WHEN INSTR(file_name, '.', -1) > 0
           THEN SUBSTR(
                    file_name,
                    INSTR(file_name, '.', -1) + 1
                )
           ELSE NULL
       END AS extension
FROM string_lab
ORDER BY item_id;
```

For `archive.tar.gz`, the result is `gz`; for `report.final.v2.xlsx`, the result is `xlsx`; for `README`, there is no dot so the result is `NULL`.

If a file name is `.env`, this logic returns `env` even though some systems treat `.env` as a hidden file rather than a file with an extension. For `archive.`, the result may be an empty string/NULL. Add business rules if you need to distinguish those cases.

### 8.4. Extracting the first and last parts of a code

For codes formatted as `REGION-TYPE-SEQUENCE`, you can extract the first and last tokens:

```sql
SELECT product_code,
       SUBSTR(product_code, 1, INSTR(product_code, '-') - 1)
           AS first_token,
       SUBSTR(product_code, INSTR(product_code, '-', -1) + 1)
           AS last_token
FROM string_lab
WHERE INSTR(product_code, '-') > 0;
```

This works when at least one hyphen exists. If the string structure varies or the delimiter can appear inside data values, verify occurrence counts and define the data contract before parsing.

### 8.5. Extracting a token between two delimiters

Suppose the string is `A|B|C` and you need the second token:

```sql
WITH source_data AS (
    SELECT 'A|B|C' AS text_value FROM dual
),
positions AS (
    SELECT text_value,
           INSTR(text_value, '|', 1, 1) AS first_delim,
           INSTR(text_value, '|', 1, 2) AS second_delim
    FROM source_data
)
SELECT SUBSTR(
           text_value,
           first_delim + 1,
           second_delim - first_delim - 1
       ) AS second_token
FROM positions
WHERE first_delim > 0
  AND second_delim > first_delim;
```

The result is `B`. Splitting tokens with `INSTR`/`SUBSTR` is very useful for simple formats with unambiguous delimiters. If fields are quoted and can contain delimiters themselves—such as CSV containing `"Nguyễn, An"`—this splitting method is insufficient; use a proper CSV parser or external table access parameters.

## 9. Cleaning and normalizing string data

### 9.1. Removing whitespace at both ends

Data from forms, CSV files, or copy/paste may contain leading or trailing spaces:

```sql
SELECT customer_name,
       TRIM(customer_name) AS normalized_name
FROM string_lab
ORDER BY item_id;
```

This can be used in an update statement:

```sql
UPDATE string_lab
SET customer_name = TRIM(customer_name)
WHERE customer_name IS NOT NULL;
```

This DML modifies real data; execute it only in a lab environment or after proper validation, backup, and transaction controls. Do not run bulk updates on production merely because you spotted a few values with extra spaces.

### 9.2. Normalizing product codes

If the code convention forbids hyphens and leading/trailing spaces:

```sql
SELECT item_id,
       REPLACE(TRIM(product_code), '-', '') AS canonical_code
FROM string_lab
ORDER BY item_id;
```

If codes are case-insensitive per business rules:

```sql
SELECT UPPER(REPLACE(TRIM(product_code), '-', ''))
       AS normalized_code
FROM string_lab;
```

Do not automatically change case for personal names, free-form text, or case-sensitive codes. Normalization must be a business rule agreed upon across all systems.

### 9.3. Separating valid and invalid data

Suppose a required code column must be between 5 and 20 characters long and contain a hyphen:

```sql
SELECT product_code,
       CASE
           WHEN product_code IS NULL THEN 'MISSING'
           WHEN LENGTH(TRIM(product_code)) < 5 THEN 'TOO_SHORT'
           WHEN LENGTH(TRIM(product_code)) > 20 THEN 'TOO_LONG'
           WHEN INSTR(product_code, '-') = 0 THEN 'NO_SEPARATOR'
           ELSE 'CANDIDATE'
       END AS validation_status
FROM string_lab;
```

This is a basic structural check. It does not prove the code exists in the catalog or conforms to rules for a specific product type. Critical business constraints should be enforced via constraints, foreign keys, or testable validation logic.

## 10. Character semantics, byte semantics, and Unicode

### 10.1. BYTE and CHAR in VARCHAR2 declarations

When declaring:

```sql
CREATE TABLE name_byte_lab (
    name_value VARCHAR2(20 BYTE)
);

CREATE TABLE name_char_lab (
    name_value VARCHAR2(20 CHAR)
);
```

The two columns impose different limits:

- `VARCHAR2(20 BYTE)` limits size in bytes.
- `VARCHAR2(20 CHAR)` limits by character count (still subject to the data type's and database configuration's maximum byte limit).

In AL32UTF8, a single character can take from 1 to multiple bytes. A 20-character Vietnamese string with diacritics may not fit within a 20-byte limit, even though it fits within 20 CHAR.

### 10.2. Character functions and B/C/2/4 variants

Oracle provides variants to specify the unit of operation:

| Group | By Character | By Byte | By Unicode Complete Character / UCS |
|---|---|---|---|
| Measure | `LENGTH` | `LENGTHB` | `LENGTHC`, `LENGTH2`, `LENGTH4` |
| Search | `INSTR` | `INSTRB` | `INSTRC`, `INSTR2`, `INSTR4` |
| Extract | `SUBSTR` | `SUBSTRB` | `SUBSTRC`, `SUBSTR2`, `SUBSTR4` |

Never mix byte-based positions with character-based positions. For instance, `INSTRB` can return a byte offset; passing that directly into `SUBSTR` (which counts characters) will fail on strings containing multi-byte characters. If you start processing by bytes, keep all calculations consistent and ensure you never slice in the middle of a multi-byte character.

### 10.3. Comparison example

```sql
SELECT LENGTH('Đặng') AS char_count,
       LENGTHB('Đặng') AS byte_count,
       SUBSTR('Đặng', 1, 2) AS first_two_chars
FROM dual;
```

The exact byte count depends on the database character set. On AL32UTF8, accented Vietnamese letters can take multiple bytes; never hardcode expected byte counts without confirming `NLS_CHARACTERSET`.

A DBA can check the character set:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

`NLS_CHARACTERSET` reports the database character set; `NLS_NCHAR_CHARACTERSET` applies to NCHAR/NVARCHAR2/NCLOB types. Do not use `NLS_SESSION_PARAMETERS` to infer the database's storage character set.

### 10.4. A Unicode code point is not always a user-perceived character

A displayed character can be represented by a single code point or a sequence of multiple code points (such as a base letter and a combining diacritic). `LENGTH`/`SUBSTR` operate on character units supported by Oracle, which do not always equal the number of "grapheme clusters" a user sees on screen.

For complex Unicode text, if the requirement is never to split inside a displayed character cluster, handle it in a Unicode-aware application layer (such as Java with appropriate libraries) and test with real data. Do not assume `SUBSTR` always equals "take N user-visible characters".

## 11. NULL, whitespace, and comparison behavior

### 11.1. TRIM does not turn NULL into a populated string

`TRIM(NULL)` returns NULL; `TRIM('   ')` returns an empty string, which Oracle SQL treats as NULL. Therefore:

```sql
SELECT CASE
           WHEN TRIM(customer_name) IS NULL THEN 'EMPTY_OR_BLANK'
           ELSE 'HAS_TEXT'
       END AS name_state
FROM string_lab;
```

classifies blank-only strings and NULL values into the same group. If business rules must distinguish "not entered" from "entered as spaces only", record the raw source state before normalizing.

### 11.2. Comparing CHAR and VARCHAR2

Oracle uses blank-padded comparison semantics for certain comparisons between two CHAR values, and nonpadded semantics when VARCHAR2/NVARCHAR2 are involved. As a result, CHAR data may compare equal to a shorter string in situations the author did not anticipate.

When normalizing input data, use appropriate data types, length constraints, and explicit trim rules. Avoid mechanically wrapping every comparison in `TRIM`, as it can alter the meaning of codes where spaces are significant.

### 11.3. Functions returning NULL and WHERE predicates

Example:

```sql
SELECT item_id
FROM string_lab
WHERE INSTR(product_code, 'XYZ') = 0;
```

This predicate finds strings that do not contain `XYZ`. If `product_code` is NULL, `INSTR` also returns NULL, and `NULL = 0` does not evaluate to TRUE; that row is omitted. If NULL values should be included in the "does not contain XYZ" group, write it explicitly:

```sql
SELECT item_id
FROM string_lab
WHERE product_code IS NULL
   OR INSTR(product_code, 'XYZ') = 0;
```

This is SQL three-valued logic: TRUE, FALSE, UNKNOWN. Check for NULL explicitly whenever string functions appear in filter predicates.

## 12. Performance: applying functions to columns in WHERE

### 12.1. Wrapping a column in a function can prevent standard index usage

Suppose there is a B-tree index:

```sql
CREATE INDEX ix_string_lab_code
ON string_lab(product_code);
```

The condition:

```sql
SELECT *
FROM string_lab
WHERE TRIM(product_code) = 'PRD-2026-001';
```

applies `TRIM` to the column value. A regular index on `product_code` stores the raw column values, not `TRIM(product_code)`. Consequently, the optimizer may not use that index for this comparison, or may choose a different plan depending on statistics and cost.

If data always needs trimming, consider normalizing upon ingestion or creating a **function-based index** when genuinely warranted:

```sql
CREATE INDEX ix_string_lab_trim_code
ON string_lab(TRIM(product_code));
```

Then a predicate matching the index expression can use the index in the execution plan. Creating indexes requires privileges, space, and DML overhead evaluation; do not create function-based indexes indiscriminately just to patch individual SQL queries.

### 12.2. Function-based indexes and NULL

Example of a case-normalized index:

```sql
CREATE INDEX ix_string_lab_email_lower
ON string_lab(LOWER(email_address));

SELECT item_id
FROM string_lab
WHERE LOWER(email_address) = LOWER(:email);
```

Oracle can use a function-based index when the expression, statistics, selectivity, and cost align. For index expressions that evaluate to NULL, indexing behavior depends on the index structure and type; consult documentation and inspect the actual execution plan.

### 12.3. INSTR vs. LIKE

The predicate:

```sql
WHERE INSTR(product_code, '2026') > 0
```

searches for a substring at any position. A standard B-tree index is generally unsuitable for arbitrary substring matching.

If business logic only needs a prefix match:

```sql
WHERE product_code LIKE 'PRD-2026%'
```

it can be much friendlier to a B-tree index under compatible collation/configuration conditions. There is no guarantee every LIKE query uses an index; a leading wildcard such as `LIKE '%2026%'` typically prevents B-tree range scans.

For full-text search or complex token matching, consider Oracle Text or a dedicated search structure rather than nesting multiple `INSTR` calls on large tables.

### 12.4. Measure the execution plan instead of guessing

```sql
EXPLAIN PLAN FOR
SELECT item_id
FROM string_lab
WHERE TRIM(product_code) = 'PRD-2026-001';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan; when actual runtime verification is needed, inspect runtime statistics with `DBMS_XPLAN.DISPLAY_CURSOR` according to environment privileges and policies. Small lab tables with few rows may rightly cause the optimizer to choose a full table scan as cheaper than an index scan.

## 13. Using string functions in UPDATE, INSERT, and MERGE

### 13.1. Normalizing before storing

A code ingestion pipeline:

```sql
INSERT INTO product_catalog (
    product_code,
    product_name
)
SELECT UPPER(REPLACE(TRIM(raw_code), ' ', '')),
       TRIM(raw_name)
FROM product_import_stage
WHERE raw_code IS NOT NULL;
```

This example trims both ends, strips standard spaces anywhere in the code, and converts to uppercase. It is only valid if the product contract states spaces in codes have no meaning. Do not apply the same logic to personal names, addresses, or free-form text.

### 13.2. Conditional updates

```sql
UPDATE string_lab
SET email_address = LOWER(TRIM(email_address))
WHERE email_address IS NOT NULL;
```

Lowercasing emails may fit application policy, but you must understand the system's identity rules and collation. Technically, parts of an email address have different case semantics under standards; many business systems choose case-insensitive matching by policy. Never alter historical data without team agreement.

### 13.3. Never build SQL by concatenating user input

Do not write:

```sql
-- Dangerous pattern when the value comes from user input:
sql_text := 'SELECT ... WHERE name = ''' || user_input || '''';
```

Use bind parameters:

```sql
SELECT item_id
FROM string_lab
WHERE customer_name = :name;
```

`TRIM`/`REPLACE` functions are not a substitute for SQL injection protection. If input needs normalization, perform it in the appropriate data layer and bind the value; never concatenate dynamic SQL simply because you are manipulating text.

## 14. Combining with other functions when needs go beyond the five basics

| Need | Potentially Suitable Function / Mechanism |
|---|---|
| Complex pattern matching | `REGEXP_INSTR`, `REGEXP_SUBSTR` |
| Regex-based replacement | `REGEXP_REPLACE` |
| Case conversion | `UPPER`, `LOWER`, `INITCAP` |
| String concatenation | `||`, `CONCAT` |
| Splitting/reading large LOBs | `DBMS_LOB` and LOB APIs |
| Formatting numbers/dates into explicit text | `TO_CHAR` with format mask |
| Unicode normalization | Unicode-aware application pipeline or purpose-built tools |
| Parsing JSON | JSON SQL functions, not slicing JSON strings with SUBSTR |

Do not use `SUBSTR` to parse JSON/XML or complex CSV when Oracle provides dedicated parsers. Splitting by commas breaks when quoted fields contain commas; slicing JSON by braces breaks when string values contain escaped characters.

## 15. End-to-end example: normalizing and splitting input codes

Suppose the system receives code strings such as:

```text
  prd-2026-001
PRD-2026-002
srv-db-015
invalidcode
```

We want to:

1. Trim leading and trailing whitespace.
2. Convert to uppercase.
3. Verify there are at least two hyphens.
4. Extract group, year, and sequence number according to the product code format.

```sql
WITH normalized AS (
    SELECT item_id,
           UPPER(TRIM(product_code)) AS code
    FROM string_lab
),
positions AS (
    SELECT item_id,
           code,
           INSTR(code, '-', 1, 1) AS dash_1,
           INSTR(code, '-', 1, 2) AS dash_2
    FROM normalized
)
SELECT item_id,
       code,
       CASE
           WHEN dash_1 > 1
            AND dash_2 > dash_1 + 1
            AND INSTR(code, '-', 1, 3) = 0
           THEN SUBSTR(code, 1, dash_1 - 1)
       END AS code_group,
       CASE
           WHEN dash_2 > dash_1 + 1
           THEN SUBSTR(code, dash_1 + 1, dash_2 - dash_1 - 1)
       END AS code_year,
       CASE
           WHEN dash_2 > 0
            AND INSTR(code, '-', 1, 3) = 0
           THEN SUBSTR(code, dash_2 + 1)
       END AS sequence_no,
       CASE
           WHEN dash_1 > 1
            AND dash_2 > dash_1 + 1
            AND INSTR(code, '-', 1, 3) = 0
           THEN 'STRUCTURE_OK'
           ELSE 'INVALID_STRUCTURE'
       END AS validation_result
FROM positions
ORDER BY item_id;
```

This is a preliminary structural check. If the year must be exactly four digits, the sequence three digits, and the group strictly A–Z letters, additional validation is needed. For complex format patterns, `REGEXP_LIKE` can be more readable:

```sql
SELECT product_code
FROM string_lab
WHERE REGEXP_LIKE(
    UPPER(TRIM(product_code)),
    '^[A-Z]{3}-[0-9]{4}-[0-9]{3}$'
);
```

`REGEXP_LIKE` only confirms the pattern; it does not prove the code exists in the catalog, the year makes business sense, or the sequence number is unused. Uniqueness constraints and catalog references still require separate design.

## 16. Common errors and pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `SUBSTR` returns NULL | Length < 1, source is NULL/empty, or position yields no valid slice | Validate position, length, and NULL before slicing |
| `SUBSTR` mis-slices Vietnamese characters | Using byte-based variants or mixing byte offsets with character offsets | Use character-based `SUBSTR`, verify character set |
| `INSTR` returns 0 | Substring not found | Check for delimiter before subtracting positions or passing length to SUBSTR |
| `INSTR` misses expected uppercase/lowercase matches | Case-sensitive matching in current context | Normalize both sides or select an appropriate collation |
| `LENGTH` does not equal LENGTHB | Multi-byte characters | Distinguish character limits from byte limits |
| `LENGTH('')` does not return 0 | Oracle treats empty strings as NULL | Use `IS NULL` and clear data-state conventions |
| `TRIM` fails to remove tabs/line breaks | Default trim handles standard blanks only | Handle specific control characters explicitly |
| `TRIM(BOTH 'abc' FROM ...)` errors | TRIM's trim_character is a single character, not a set | Use LTRIM/RTRIM or custom logic |
| `REPLACE` removes more occurrences than intended | REPLACE replaces all occurrences | Choose the right logic/pattern; never assume first-only |
| `REPLACE` skips uppercase matches | Case differs from stored data | Normalize case if business rules permit |
| Query slows down after wrapping column in TRIM/LOWER | Standard index does not match expression | Normalize data at write time, use function-based index, inspect plan |
| Parsing CSV with INSTR/SUBSTR breaks | Delimiter appears inside quoted fields or newlines | Use a proper CSV parser or external table format |
| Results differ across environments | Different NLS, character set, collation, or column types | Inspect DDL and environment parameters |

## 17. Guided lab exercises

Run these in a lab schema. If you already created `STRING_LAB` earlier, reuse it; otherwise run the setup section first.

### Exercise 1 — SUBSTR and negative positions

Run:

```sql
SELECT SUBSTR('DATABASE', 1, 4) AS a,
       SUBSTR('DATABASE', 5) AS b,
       SUBSTR('DATABASE', -4) AS c,
       SUBSTR('DATABASE', 0, 3) AS d
FROM dual;
```

Record the results and explain position 0 and negative positions. Test lengths 0 and -1 to observe NULL output.

### Exercise 2 — INSTR and occurrence

```sql
SELECT INSTR('A-B-C-D', '-', 1, 1) AS first_delimiter,
       INSTR('A-B-C-D', '-', 1, 3) AS third_delimiter,
       INSTR('A-B-C-D', '-', -1, 2) AS second_from_right,
       INSTR('A-B-C-D', 'X') AS not_found
FROM dual;
```

Map out each character position and verify the 1-based index results. Experiment with different negative `position` and `occurrence` values so you do not confuse search direction with occurrence count.

### Exercise 3 — Counting characters and bytes

```sql
SELECT LENGTH('ABC') AS ascii_chars,
       LENGTHB('ABC') AS ascii_bytes,
       LENGTH('Đặng') AS viet_chars,
       LENGTHB('Đặng') AS viet_bytes
FROM dual;
```

Check the database character set and explain why byte counts depend on encoding.

### Exercise 4 — TRIM, LTRIM, RTRIM

```sql
SELECT TRIM('  00123  ') AS default_trim,
       TRIM(LEADING '0' FROM '000123') AS trim_leading_zero,
       TRIM(TRAILING '-' FROM 'ABC---') AS trim_trailing,
       LTRIM('xyxyABC', 'xy') AS trim_character_set
FROM dual;
```

Explain why `LTRIM` with set `'xy'` strips individual characters from the set rather than matching the exact substring `'xy'`. Test tabs using `CHR(9)`.

### Exercise 5 — REPLACE

```sql
SELECT REPLACE('A-B-A-B', 'A', 'X') AS replace_all,
       REPLACE('A-B-A-B', '-') AS remove_delimiter,
       REPLACE('Oracle ORACLE oracle', 'oracle', 'DB') AS case_result
FROM dual;
```

Note the number of replacements and why uppercase/lowercase variants are not replaced together.

### Exercise 6 — Splitting email addresses and file names

```sql
SELECT email_address,
       SUBSTR(email_address, 1, INSTR(email_address, '@') - 1)
           AS local_part,
       SUBSTR(email_address, INSTR(email_address, '@') + 1)
           AS domain_part
FROM string_lab
WHERE INSTR(email_address, '@') > 0;

SELECT file_name,
       CASE
           WHEN INSTR(file_name, '.', -1) > 0
           THEN SUBSTR(file_name, INSTR(file_name, '.', -1) + 1)
       END AS extension
FROM string_lab;
```

Add test cases with a missing `@`, a file name without a dot, `.env`, and `archive.` to define your parsing policy.

### Exercise 7 — Conditional code normalization

```sql
SELECT product_code,
       UPPER(REPLACE(TRIM(product_code), '-', '')) AS normalized_code,
       LENGTH(TRIM(product_code)) AS code_chars
FROM string_lab;
```

Identify which rules are purely technical processing and which require business decisions. Never update live tables until confirming that normalization does not collapse two distinct codes into the same value.

### Exercise 8 — Evaluating indexes and function-based indexes

Create an index on `product_code`, then run a standard equality query and a `TRIM(product_code)` query. Use `DBMS_XPLAN` to inspect the plans. Next, create a function-based index on `TRIM(product_code)` in the lab and check whether the optimizer picks it.

Record:

- DDL / index expression.
- Plans before and after.
- Table row count and statistics.
- Why the optimizer might still choose a full table scan on a small table.

Do not conclude that a function-based index always improves speed; it increases storage usage and DML overhead.

## 18. Best practices for string-handling SQL

1. **Identify column data types before processing.** CHAR, VARCHAR2, NCHAR, NVARCHAR2, CLOB, and NCLOB differ in padding, character set, and limits.
2. **Choose consistent units.** Use character-based LENGTH/SUBSTR/INSTR for text; use `B` variants only when a byte-level contract requires them.
3. **Check INSTR before computing SUBSTR lengths.** Not found returns 0, which can yield negative lengths.
4. **Be explicit about trimming.** Space, tab, newline, and NBSP are not the same character.
5. **Understand NULL.** Oracle treats empty strings as NULL; NULL function results affect WHERE clauses and concatenation.
6. **Do not confuse REPLACE with regex.** Use REPLACE for literal substrings; use REGEXP_REPLACE only when pattern matching is truly needed.
7. **Avoid implicit conversions.** Converting numbers/dates to strings requires explicit format masks and NLS settings.
8. **Preserve meaningful data.** Never arbitrarily trim, strip diacritics, or fold case if those characters are part of an identifier or name.
9. **Evaluate indexing.** Functions on columns may require function-based indexes or normalization prior to storage.
10. **Use bind variables.** String functions are no substitute for parameter binding and SQL injection prevention.
11. **Separate parsing from validation.** Extracting a token does not prove the token is valid under business rules.
12. **Test with Unicode and edge cases.** Include empty strings, NULLs, missing/repeated delimiters, multi-byte characters, control characters, and very long strings.

## 19. Self-check questions

1. Does `SUBSTR` count positions from 0 or 1? How does Oracle treat position 0?
2. How does a negative position in `SUBSTR` differ from a negative length?
3. What does `INSTR` return when a substring is not found? Why must you check it before extracting a substring by delimiter?
4. What does the `occurrence` parameter in `INSTR` mean? How does a negative position change search direction?
5. How do `LENGTH` and `LENGTHB` differ under AL32UTF8?
6. Why does `LENGTH('')` return NULL while `LENGTH(' ')` returns 1?
7. How can `CHAR(10)` and `VARCHAR2(10)` differ when measuring length?
8. What character does `TRIM` remove by default? Why might tabs or NBSP remain?
9. How does `TRIM` differ from `LTRIM`/`RTRIM` when stripping a set of characters?
10. Does `REPLACE` replace the first occurrence or all occurrences? What happens if the replacement string is NULL?
11. When should you use `REGEXP_REPLACE` instead of `REPLACE`?
12. Why can `TRIM(column)` in a WHERE clause prevent a standard index from being used?
13. How do you split the parts before and after `@` without failing when the delimiter is missing?
14. Why should you avoid parsing CSV containing quoted delimiters using only `SUBSTR` and `INSTR`?
15. What differences between Unicode characters and grapheme clusters should be kept in mind when slicing strings?

Mastering these five functions covers most everyday string operations in SQL: **`SUBSTR` to slice, `INSTR` to locate, `LENGTH` to measure, `TRIM` to clean edges, and `REPLACE` to substitute**. When bringing them into production systems, check character sets, byte semantics, NULLs, delimiters, and execution plans; those details determine whether data is processed accurately and with acceptable performance.
