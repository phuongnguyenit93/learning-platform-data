# Regular Expressions and Pattern Extraction in PostgreSQL

## 1. Why Use Regular Expressions in SQL?

A PostgreSQL table can store many kinds of text strings: order codes, emails, system logs, phone numbers, filenames, descriptions, or attribute strings imported from external systems. When processing them, we often want to:

- Find strings matching a specific **shape**, such as the code `INV-2026-0042`.
- Check whether a string **starts** with a valid prefix and **ends** with a valid suffix.
- Extract the **year** and **sequence number** separately from an invoice code.
- Extract **multiple codes** appearing inside a block of text.
- Replace segments matching a pattern with another string.
- Split tag lists or log entries into multiple parts.
- Filter malformed input before a normalization step.

If we only use equality:

```sql
WHERE invoice_code = 'INV-2026-0042'
```

we only match one exact value. If we use:

```sql
WHERE invoice_code LIKE 'INV-%'
```

we know the string starts with `INV-`, but **we have not verified** whether what follows has exactly four year digits, a hyphen, and four sequence digits.

Regular expressions (**regex**) allow us to describe that pattern:

```sql
WHERE invoice_code ~ '^INV-[0-9]{4}-[0-9]{4}$'
```

Meaning:

- `^`: start of the string.
- `INV-`: literal fixed text.
- `[0-9]{4}`: exactly four ASCII digits.
- `-`: hyphen.
- `[0-9]{4}`: exactly four more digits.
- `$`: end of the string.

Because both `^` and `$` are present, the condition requires the **entire string** to have that exact shape, not merely contain a matching substring.

> **Remember:** Regex is a tool for describing and extracting **text shape**, not for verifying all business rules on its own. The string `INV-9999-0000` matches the four-digit year pattern, yet regex cannot determine whether that invoice exists or whether the business year is valid.

In PostgreSQL, regular expressions are supported directly through the operators `~`, `~*`, `!~`, `!~*` and functions such as `regexp_match`, `regexp_matches`, `regexp_replace`, and `regexp_split_to_array`.

## 2. Lesson Objectives

After this lesson, you will be able to:

1. Distinguish `LIKE`, `ILIKE`, `SIMILAR TO`, and PostgreSQL regex.
2. Use `~`, `~*`, `!~`, and `!~*` to filter text.
3. Read and write patterns with anchors, character classes, quantifiers, groups, and alternation.
4. Extract **a single match** with `regexp_match` and `substring(... FROM pattern)`.
5. Extract **all matches** with `regexp_matches(..., 'g')`.
6. Replace text with `regexp_replace`, with or without **capture groups**.
7. Split strings with `regexp_split_to_array` and `regexp_split_to_table`.
8. Handle `NULL`, non-matching data, and **disappearing rows caused by set-returning functions**.
9. Use additional regex functions introduced in PostgreSQL 15+ when supported by your version.
10. Understand limitations around Unicode, collation, performance, and untrusted input.

## 3. Practice Data

This lesson uses a separate `regex_lab` schema. Run these table-creation statements in a **test** database, not production.

### 3.1. Create the Contacts Table

```sql
CREATE SCHEMA IF NOT EXISTS regex_lab;

CREATE TABLE regex_lab.contacts (
    contact_id bigint PRIMARY KEY,
    full_name text NOT NULL,
    email text,
    phone text,
    note text NOT NULL
);
```

Insert six rows:

```sql
INSERT INTO regex_lab.contacts
    (contact_id, full_name, email, phone, note)
VALUES
    (
        1, 'An', 'an@example.com', '090-123-4567',
        'INV-2026-0042; tag=SQL; tag=Java'
    ),
    (
        2, 'Bình', 'Binh@Example.COM', '+84 912 345 678',
        'INV-2026-0101; tag=PostgreSQL'
    ),
    (
        3, 'Chi', 'chi.example.com', 'abc',
        'No invoice code found'
    ),
    (
        4, 'Dung', NULL, NULL,
        'Error codes #42 and #103'
    ),
    (
        5, 'Em', 'em+sales@example.org', '0912345678',
        'INV-2025-1234; tag=SQL; tag=SQL'
    ),
    (
        6, 'Phúc', 'phuc@sample.vn', '012-345-6789',
        'INV-2026-0200; follow up later'
    );
```

The table intentionally contains:

- Emails with mixed uppercase/lowercase letters.
- An email missing the `@` symbol.
- `NULL` values for `email` and `phone`.
- Phone numbers with hyphens, spaces, a plus sign, and invalid text.
- Multiple invoice codes, `tag=...` labels, and `#`-prefixed error codes.

**Note:** This data is solely for demonstrating regex and does not represent verified phone numbers or emails. Running `INSERT` again after loading the data will raise a primary key error.

### 3.2. Create the Logs Table

```sql
CREATE TABLE regex_lab.logs (
    log_id bigint PRIMARY KEY,
    log_line text NOT NULL
);

INSERT INTO regex_lab.logs (log_id, log_line)
VALUES
    (101, 'INFO order=1001 amount=125.50'),
    (102, 'WARN order=1002 amount=0'),
    (103, 'ERROR code=E42 details=timeout'),
    (104, 'INFO order=1003 amount=78.25'),
    (105, 'DEBUG no order information');
```

We will extract:

- Log level: `INFO`, `WARN`, `ERROR`.
- Order ID `order=1001`.
- Amount `amount=125.50`.
- Error code `code=E42`.

## 4. How Do `LIKE`, `ILIKE`, and Regex Differ?

PostgreSQL offers several pattern-matching mechanisms:

| Mechanism | Example Pattern | Capability |
| --- | --- | --- |
| `=` | `email = 'an@example.com'` | Value equality comparison |
| `LIKE` | `full_name LIKE 'A%'` | Simple pattern matching with `%` and `_` |
| `ILIKE` | `full_name ILIKE 'a%'` | Like `LIKE`, case-insensitive per locale handling |
| `~` | `note ~ 'INV-[0-9]{4}'` | Regex, case-sensitive |
| `~*` | `note ~* 'inv-[0-9]{4}'` | Regex, case-insensitive |
| `SIMILAR TO` | `code SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}'` | SQL-syntax pattern combining LIKE/regex, usually requires full-string match |
| `regexp_match` | `regexp_match(note, '(INV-[0-9]+)')` | Extracts data from the first match |

### 4.1. `LIKE` Uses Different Wildcards Than Regex

In `LIKE`:

- `%`: zero or more characters.
- `_`: exactly one character.

```sql
SELECT
    'INV-2026-0042' LIKE 'INV-%' AS like_prefix,
    'INV-2026-0042' LIKE 'INV-____-____' AS like_fixed_width;
```

Both expressions return `TRUE`. However, `_` can match letters or other characters, not necessarily digits.

In regex:

- `.`: any single character per regex mode.
- `.*`: zero or more characters.
- `[0-9]`: one ASCII digit.
- `{4}`: exactly four times.

```sql
SELECT
    'INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS exact_shape,
    'INV-ABCD-WXYZ' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS invalid_shape;
```

Results: `TRUE` and `FALSE`.

**Do not translate `LIKE 'A%'` directly into regex `'A%'`.** In regex, a plain `%` just means a literal percent sign; to express "starts with A", use `'^A'`.

### 4.2. `SIMILAR TO` Matches the Entire String

```sql
SELECT
    'INV-2026-0042'
        SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}' AS similar_valid,
    'prefix INV-2026-0042 suffix'
        SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}' AS similar_not_full;
```

`SIMILAR TO` blends features of SQL `LIKE` and regex, but its rules differ from POSIX regex operators. It suits certain standard SQL contexts; when you need capture groups, replacement, or flexible extraction, PostgreSQL's dedicated regex functions are usually more convenient.

## 5. The Four Regex Matching Operators in PostgreSQL

| Operator | Meaning | Example |
| --- | --- | --- |
| `~` | Matches regex, case-sensitive | `name ~ '^A'` |
| `~*` | Matches regex, case-insensitive | `name ~* '^a'` |
| `!~` | Does not match regex, case-sensitive | `name !~ '^A'` |
| `!~*` | Does not match regex, case-insensitive | `name !~* '^a'` |

### 5.1. `~`: Finding Strings Containing a Pattern

```sql
SELECT contact_id, full_name, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

The result includes `contact_id` **1, 2, 5, 6**, because those four contacts' notes contain a code of the described shape.

A common point of confusion:

```sql
SELECT
    'abc INV-2026-0042 xyz' ~ 'INV-[0-9]{4}-[0-9]{4}'
        AS contains_pattern,
    'abc INV-2026-0042 xyz' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS entire_string_matches;
```

- `contains_pattern` is `TRUE`.
- `entire_string_matches` is `FALSE`.

Without anchors, regex can match **anywhere inside the string**. With `^` and `$` anchors, it requires the pattern to span the entire string in standard mode.

### 5.2. `~*`: Case-Insensitive Matching

```sql
SELECT contact_id, full_name, email
FROM regex_lab.contacts
WHERE email ~* '@example\.com$'
ORDER BY contact_id;
```

The result includes contacts **1** and **2**:

- `an@example.com`
- `Binh@Example.COM`

`~*` allows case-insensitive comparison. `\.` is a **literal dot**; if written unescaped as `.`, it can match any character.

### 5.3. `!~` and `!~*`

```sql
SELECT contact_id, full_name, note
FROM regex_lab.contacts
WHERE note !~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

In the sample data, the results are **3** and **4** because their notes do not contain an invoice code of this shape.

For `NULL` values, regex comparison expressions normally return `NULL`, even when using the negated operators:

```sql
SELECT
    NULL::text ~ '^A' AS null_matches,
    NULL::text !~ '^A' AS null_does_not_match;
```

Both evaluate to `NULL`, not FALSE or TRUE. In `WHERE`, only TRUE results are retained.

### 5.4. Finding Non-Matching Rows, Including NULL

If the business requirement is "email **does not match the pattern or was not provided**":

```sql
SELECT contact_id, full_name, email
FROM regex_lab.contacts
WHERE email IS NULL
   OR email !~* '^[^@[:space:]]+@[^@[:space:]]+$'
ORDER BY contact_id;
```

On the sample table, the query returns contacts **3** and **4**: one address missing `@`, and one NULL address.

This is a **very basic shape check**, not a full email validator. In particular, never claim that "matching a regex" means the address exists or can receive mail.

## 6. Core Regex Syntax: Reading Patterns Left to Right

PostgreSQL uses a regular expression engine supporting POSIX syntax and **Advanced Regular Expressions (ARE)** extensions. It is not Java's `java.util.regex`, JavaScript's `RegExp`, or PCRE, even though many symbols look similar.

### 6.1. Literal Characters and Special Characters

| Pattern | Meaning | Example |
| --- | --- | --- |
| `abc` | Exact literal text `abc` | Matches `xabcx` |
| `.` | Any single character per matching mode | `a.c` can match `abc` |
| `^` | Start of string, affected by certain newline modes | `^INV` |
| `$` | End of string, affected by certain newline modes | `[0-9]$` |
| `[abc]` | One character from set a, b, c | `[ABC]` |
| `[^abc]` | One character not in set a, b, c | `[^0-9]` |
| `[0-9]` | One ASCII digit from 0 to 9 | `[0-9]{4}` |
| `(abc)` | Capturing group | `(INV)-[0-9]+` |
| `a\|b` | Alternation choosing one of two branches | `(INFO\|ERROR)` |
| `\` | Escape or start of extended regex syntax | `\.` to match a literal dot |

In the Markdown table above, `\|` is escaped so the pipe symbol displays properly; in actual SQL statements, the alternation operator is an unescaped `|`.

Alternation example:

```sql
SELECT
    'ERROR code=E42' ~ '^(INFO|WARN|ERROR)' AS supported_level,
    'TRACE details' ~ '^(INFO|WARN|ERROR)' AS unsupported_level;
```

Results: `TRUE` and `FALSE`.

### 6.2. Character Classes

```sql
SELECT
    'A7' ~ '^[A-Z][0-9]$' AS alpha_then_digit,
    'a7' ~ '^[A-Z][0-9]$' AS lowercase_not_allowed,
    'a7' ~* '^[A-Z][0-9]$' AS lowercase_allowed_with_casefold;
```

The pattern `[A-Z]` expresses a letter range according to regex/collation rules; when strict ASCII input is required, test behavior in your target environment and define the data contract clearly. For accented Vietnamese text, `[A-Za-z]` is **not** a complete description of alphabetic characters.

### 6.3. POSIX Character Classes

PostgreSQL supports character classes of the form:

| Class | General Meaning |
| --- | --- |
| `[[:digit:]]` | Digit character per corresponding class |
| `[[:alpha:]]` | Alphabetic character |
| `[[:alnum:]]` | Letter or digit |
| `[[:space:]]` | Whitespace character |
| `[[:lower:]]` | Lowercase letter |
| `[[:upper:]]` | Uppercase letter |
| `[[:punct:]]` | Punctuation |
| `[[:xdigit:]]` | Hexadecimal digit |

Example:

```sql
SELECT
    'INV2026' ~ '^[[:alpha:]]+[[:digit:]]+$'
        AS letter_digit_sequence,
    'ABC-12' ~ '^[[:alnum:]]+$'
        AS alphanumeric_only,
    'ABC12' ~ '^[[:alnum:]]+$'
        AS alphanumeric_valid;
```

The results are `TRUE`, `FALSE`, and `TRUE` respectively in common environments.

The `[[:alpha:]]` class and case-folding behavior can depend on locale/collation and PostgreSQL's Unicode support. Do not use a simple ASCII regex to validate multilingual personal names.

### 6.4. Hyphens, Dots, and Square Brackets

Some characters have special meaning in regex and require careful handling.

- Literal dot: `\.`.
- Literal opening bracket typically needs `\[`.
- A hyphen inside `[...]` can form a **range**; place it in an unambiguous position or escape it.

Example:

```sql
SELECT
    'a.b' ~ '^a\.b$' AS literal_dot,
    'axb' ~ '^a\.b$' AS not_literal_dot,
    'a-b' ~ '^a[-]b$' AS literal_hyphen;
```

Results: `TRUE`, `FALSE`, `TRUE`.

**Watch out for two syntax layers:** the regex is written **inside a SQL string literal**. SQL single-quote escaping and regex character escaping are two separate layers.

## 7. Quantifiers: Repetition Counts for Pattern Parts

| Quantifier | Meaning | Example |
| --- | --- | --- |
| `*` | 0 or more times | `a*` |
| `+` | 1 or more times | `a+` |
| `?` | 0 or 1 time | `a?` |
| `{n}` | Exactly n times | `[0-9]{4}` |
| `{n,}` | At least n times | `[0-9]{2,}` |
| `{n,m}` | From n to m times | `[0-9]{2,5}` |

### 7.1. Distinguishing `*` and `+`

```sql
SELECT
    '' ~ '^a*$' AS empty_matches_star,
    '' ~ '^a+$' AS empty_matches_plus,
    'aaa' ~ '^a+$' AS repeated_a;
```

Results:

- `a*` accepts an **empty string**.
- `a+` requires at least one `a` character.
- `aaa` matches `a+`.

This matters when validating a column that must contain at least one valid character.

### 7.2. Standard Five-Digit Code

```sql
SELECT
    '00123' ~ '^[0-9]{5}$' AS valid_code,
    '123' ~ '^[0-9]{5}$' AS too_short,
    '123456' ~ '^[0-9]{5}$' AS too_long;
```

Results: `TRUE`, `FALSE`, `FALSE`.

If the code must **not be 00000**, the regex above is not enough: it checks shape only, not value domain. Add an explicit business condition or parse into an appropriate type if needed.

### 7.3. Greedy and Non-Greedy

Many quantifiers in PostgreSQL ARE default to **greedy** behavior: trying to match the longest substring satisfying the rule.

```sql
SELECT
    substring('<a>first</a><b>second</b>' FROM '<.*>')
        AS greedy_fragment,
    substring('<a>first</a><b>second</b>' FROM '<.*?>')
        AS nongreedy_fragment;
```

In ARE regex, `.*?` is the **non-greedy** form, typically stopping at the first `>` rather than extending to the last `>`.

Even though non-greedy quantifiers are supported, **do not arbitrarily use regex to parse nested HTML/XML structures**. For HTML/XML/JSON, use dedicated structural parsers to avoid bugs with quotes, escapes, and nested content.

## 8. Anchors: Matching Start and End

### 8.1. Patterns With and Without Anchors

```sql
SELECT
    'abcINV-2026-0042xyz'
        ~ 'INV-[0-9]{4}-[0-9]{4}' AS found_inside,
    'abcINV-2026-0042xyz'
        ~ '^INV-[0-9]{4}-[0-9]{4}$' AS valid_whole_value;
```

Results: `TRUE` and `FALSE`.

When checking the **format of an entire column** like an order code, usually use `^...$`. When searching for **a code embedded inside a long note**, usually omit anchors at both ends.

### 8.2. Line Start Differs from String Start Under Newline Modes

A multi-line log string:

```text
INFO start
ERROR failed
INFO end
```

If the goal is to find a line starting with `ERROR`, you need to understand the engine's **newline-handling mode**. PostgreSQL provides flags controlling how anchors and dots behave with newline characters (covered in Section 15).

Do not assume every regex engine treats `^` and `$` as start/end of each line in a multi-line string. Specify the mode you intend to use.

### 8.3. Limitations When Using Anchors to Validate

```sql
SELECT 'test@example.com' ~ '^[^@[:space:]]+@[^@[:space:]]+$';
```

This pattern only guarantees one `@` and no spaces in either part. It still accepts many strings that are not real email addresses. **A simple regex is a shape filter, not a comprehensive email validator**.

## 9. Groups and Alternation: The Foundation of Pattern Extraction

Parentheses `(...)` in regex serve two roles:

1. Grouping components to apply `|` or quantifiers.
2. **Capturing** matched text so extraction functions can retrieve individual parts.

### 9.1. Grouping Log Levels

```sql
SELECT log_id, log_line
FROM regex_lab.logs
WHERE log_line ~ '^(INFO|WARN|ERROR)[[:space:]]'
ORDER BY log_id;
```

The result includes logs **101, 102, 103, 104**; log 105 starts with DEBUG so it does not match.

### 9.2. Grouping Invoice Code Parts

The pattern:

```regex
^([A-Z]+)-([0-9]{4})-([0-9]{4})$
```

has three capture groups:

| Group | Pattern | Example |
| --- | --- | --- |
| 1 | `([A-Z]+)` | `INV` |
| 2 | `([0-9]{4})` | `2026` |
| 3 | `([0-9]{4})` | `0042` |

Example:

```sql
SELECT regexp_match(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$'
) AS captured_parts;
```

The result is a **text array**:

```text
{INV,2026,0042}
```

In PostgreSQL, array indexes normally start at **1**, not 0.

### 9.3. Non-Capturing Groups

Some groups are only for alternation and do not need to be extracted. In PostgreSQL ARE, you can use a **non-capturing group** `(?:...)`:

```sql
SELECT regexp_match(
    'WARN order=1002',
    '^(?:INFO|WARN|ERROR)[[:space:]]order=([0-9]+)'
) AS only_order_id;
```

The expected result is an array containing `1002`, because `(?:INFO|WARN|ERROR)` does not create a capture group.

This avoids having to track shifting group indexes simply because you added parentheses for syntactic grouping.

## 10. `regexp_match`: Extracting the First Match

`regexp_match(string, pattern [, flags])` returns:

- A **`text[]`** containing the capture groups if there is a match.
- `NULL` if there is no match.
- If the regex **has no capture groups**, the array typically contains **the entire matched substring**.

This function returns **one value per input row**, making it convenient in an ordinary `SELECT`.

### 10.1. Extracting Invoice Codes from Notes

```sql
SELECT
    contact_id,
    full_name,
    regexp_match(
        note,
        '(INV-[0-9]{4}-[0-9]{4})'
    ) AS invoice_match
FROM regex_lab.contacts
ORDER BY contact_id;
```

Result summary:

| contact_id | invoice_match |
| ---: | --- |
| 1 | `{INV-2026-0042}` |
| 2 | `{INV-2026-0101}` |
| 3 | NULL |
| 4 | NULL |
| 5 | `{INV-2025-1234}` |
| 6 | `{INV-2026-0200}` |

Rows 3 and 4 **remain in the result**, with only the extracted column being NULL.

### 10.2. Extracting Year and Sequence Number

```sql
SELECT
    contact_id,
    (regexp_match(
        note,
        'INV-([0-9]{4})-([0-9]{4})'
    ))[1] AS invoice_year,
    (regexp_match(
        note,
        'INV-([0-9]{4})-([0-9]{4})'
    ))[2] AS invoice_sequence
FROM regex_lab.contacts
ORDER BY contact_id;
```

Example for contact 1:

```text
invoice_year     = 2026
invoice_sequence = 0042
```

These values are **text**, because they were extracted from a string. Keeping `0042` as text is meaningful if the invoice code must preserve **leading zeros**. Casting to an integer turns `0042` into `42` and loses the original code formatting.

### 10.3. Avoiding Repeated Regex Calls with LATERAL

If you want multiple groups, you can run the extraction once per row:

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS invoice_year,
    m.parts[2] AS invoice_sequence
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL (
    SELECT regexp_match(
        c.note,
        'INV-([0-9]{4})-([0-9]{4})'
    ) AS parts
) AS m
ORDER BY c.contact_id;
```

`regexp_match` returns **one array or NULL**, so this scalar subquery produces one row per contact even when there is no match; in that case `parts` is NULL.

The advantage is cleaner SQL and reusing `m.parts[1]`/`m.parts[2]` without repeating a long pattern.

### 10.4. When There Are No Capture Groups

```sql
SELECT
    regexp_match(
        'x=123',
        '[0-9]+'
    ) AS whole_match_without_groups,
    regexp_match(
        'x=123',
        'x=([0-9]+)'
    ) AS group_only;
```

Both produce an array with `123` in this example, but for different reasons:

- The first pattern has no groups -> the array holds **the whole matched substring** `123`.
- The second pattern has a group -> the array holds **the group's content** `123`, not the entire `x=123`.

If you want both the prefix and the value, use two groups:

```sql
SELECT regexp_match(
    'x=123',
    '([[:alpha:]]+)=([0-9]+)'
);
```

Result: `{x,123}`.

## 11. `substring(text FROM pattern)`: A Concise Extraction Form

PostgreSQL supports the form:

```sql
substring(string FROM pattern)
```

where **pattern is a POSIX regular expression**.

### 11.1. Extracting a Code Embedded in a String

```sql
SELECT
    substring(
        'Notice: INV-2026-0042 created',
        'INV-[0-9]{4}-[0-9]{4}'
    ) AS invoice_code;
```

Result:

```text
INV-2026-0042
```

If there is no matching substring, the result is `NULL`.

### 11.2. Capturing Parentheses Change What `substring` Returns

```sql
SELECT
    substring(
        'INV-2026-0042',
        'INV-([0-9]{4})-[0-9]{4}'
    ) AS extracted_year;
```

The result is `2026`, because when the pattern contains capturing parentheses, `substring(... FROM pattern)` returns **the substring matched by the first capturing group**.

This differs from the previous example, which had no groups and returned the entire match.

### 11.3. When to Use `substring` vs. `regexp_match`?

| Need | Suggestion |
| --- | --- |
| Extract a single substring by simple pattern | `substring(... FROM regex)` |
| Extract one specific group | `substring` if the first group fits; `regexp_match` for clarity |
| Extract multiple groups at once | `regexp_match` |
| Extract all occurrences | `regexp_matches(..., 'g')` or appropriate function |
| Only need a match/no-match check | `~`/`~*` or `regexp_like` |

In applications extracting multiple components, `regexp_match` is often easier to read than adding several separate `substring` calls.

## 12. `regexp_matches`: Multiple Results and Key Differences from `regexp_match`

The two function names look very similar, yet their **cardinality** differs:

- `regexp_match`: returns **one array or NULL** per call.
- `regexp_matches`: returns a **set of rows** (*set of text[]*). If there is **no match**, it returns **0 rows**; with the `g` flag, each match emits a row.

### 12.1. Single Match Without `g`

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java',
    'tag=([[:alpha:]]+)'
);
```

Without `g`, only the first match is returned:

```text
{SQL}
```

### 12.2. All Matches with the `g` Flag

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java',
    'tag=([[:alpha:]]+)',
    'g'
);
```

Result of two rows:

```text
{SQL}
{Java}
```

`g` stands for **global matching**: finding subsequent matches, not just the first one.

### 12.3. Extracting All Tags Across Contacts

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS tag
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    'tag=([[:alpha:]]+)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, tag;
```

Result summary:

| contact_id | full_name | tag |
| ---: | --- | --- |
| 1 | An | Java |
| 1 | An | SQL |
| 2 | Bình | PostgreSQL |
| 5 | Em | SQL |
| 5 | Em | SQL |

Contacts without `tag=...` **have no rows** in the `CROSS JOIN LATERAL` result. Contact 5 has `tag=SQL` twice and therefore produces two rows.

Note that `ORDER BY c.contact_id, tag` sorts by tag value, **not preserving order of appearance in `note`**. If you need exact occurrence order, collect match positions or use ordinality on a suitable set-returning structure with appropriate order verification.

### 12.4. No Match -> 0 Rows, Not a NULL Row

```sql
SELECT *
FROM regexp_matches(
    'no tags here',
    'tag=([[:alpha:]]+)',
    'g'
);
```

The result is **0 rows**.

If used in a context that alters row multiplicity, you can accidentally drop source records. That is a crucial design difference compared to `regexp_match`.

### 12.5. Preserving All Contacts with `LEFT JOIN LATERAL`

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS tag
FROM regex_lab.contacts AS c
LEFT JOIN LATERAL regexp_matches(
    c.note,
    'tag=([[:alpha:]]+)',
    'g'
) AS m(parts)
    ON TRUE
ORDER BY c.contact_id, tag NULLS LAST;
```

With `LEFT JOIN LATERAL`, contacts without tags still appear as **one row with `tag NULL`**.

Comparison:

| JOIN Approach | When a Contact Has No Match |
| --- | --- |
| `CROSS JOIN LATERAL regexp_matches` | Contact disappears |
| `LEFT JOIN LATERAL regexp_matches ... ON TRUE` | Contact is kept, match column is NULL |

**This is a very common trap when extracting regex matches across multiple rows.** Choose the JOIN type based on whether non-matching records must be preserved.

## 13. From Matches to Structured Rows

Regex extraction is often the first step in turning text logs into structured data.

### 13.1. Extracting `key=value` Pairs from Logs

```sql
SELECT
    l.log_id,
    m.parts[1] AS key,
    m.parts[2] AS value
FROM regex_lab.logs AS l
CROSS JOIN LATERAL regexp_matches(
    l.log_line,
    '([[:alpha:]_]+)=([[:alnum:]._-]+)',
    'g'
) AS m(parts)
ORDER BY l.log_id, key;
```

For example, log 101:

```text
INFO order=1001 amount=125.50
```

is extracted into:

| log_id | key | value |
| ---: | --- | --- |
| 101 | amount | 125.50 |
| 101 | order | 1001 |

This is a form of **key-value extraction**. It does not fully handle values containing spaces or escape characters. To parse production logs reliably, it is best to emit **structured logs from the source**, such as JSON, rather than trying to cover every variation with a regex.

### 13.2. Extracting Error Codes Like `#42`, `#103`

```sql
SELECT
    c.contact_id,
    m.parts[1] AS error_number_text
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]+)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, error_number_text;
```

Contact 4 has two error codes:

```text
42
103
```

Because `error_number_text` is text, lexicographical sorting puts `103` before `42`. If **numeric** ordering is needed, cast to integer after validating a safe value range.

### 13.3. Avoiding Unchecked Casts

If `[0-9]+` matches a very long digit string, casting to `integer` can raise `integer out of range`.

For example, allowing at most 9 ASCII digits keeps values within the positive 32-bit integer range:

```sql
SELECT
    c.contact_id,
    m.parts[1]::integer AS error_number
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]{1,9})([^0-9]|$)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, error_number;
```

This pattern requires a non-digit or end of string after the digits, avoiding taking a prefix from an overly long digit sequence in typical cases.

**However**, regex validation and casting are only part of input handling: if requirements are strict, check policies on leading zeros, signs, value bounds, and error reporting. In normalized schemas, typed numeric columns and `CHECK` constraints are more reliable than reparsing raw strings on every query.

## 14. `regexp_replace`: Pattern-Based Search and Replace

Basic syntax:

```sql
regexp_replace(source, pattern, replacement)
regexp_replace(source, pattern, replacement, flags)
```

The function returns the replaced string. Key point: **without the `g` flag, only the first match is replaced**; with `g`, all non-overlapping matches found are replaced.

### 14.1. Replacing the First Match Only

```sql
SELECT regexp_replace(
    'A   B    C',
    '[[:space:]]+',
    ' '
) AS only_first_group;
```

Result summary:

```text
A B    C
```

Only the first whitespace group is replaced.

### 14.2. Replacing All Matches with `g`

```sql
SELECT regexp_replace(
    'A   B    C',
    '[[:space:]]+',
    ' ',
    'g'
) AS normalized_spacing;
```

Result:

```text
A B C
```

This operation is commonly used to normalize spaces in user-entered strings. Note, however, that `[[:space:]]+` can also match tabs or newlines; if line breaks must be preserved, write a narrower pattern.

### 14.3. Normalizing Phone Numbers to Digits Only

```sql
SELECT
    contact_id,
    phone,
    regexp_replace(
        phone,
        '[^0-9]',
        '',
        'g'
    ) AS digits_only
FROM regex_lab.contacts
ORDER BY contact_id;
```

Examples:

| phone | digits_only |
| --- | --- |
| `090-123-4567` | `0901234567` |
| `+84 912 345 678` | `84912345678` |
| `abc` | empty string |
| NULL | NULL |
| `0912345678` | `0912345678` |

**Warning:** "keeping only digits" is not the same as **verifying a phone number**. Country codes, leading zeros, and length rules depend on country, carrier, and system rules. Do not treat every digit-containing string as a validated phone number.

### 14.4. Avoid Destructive Transformations That Lose Original Data

For instance, the statement:

```sql
UPDATE regex_lab.contacts
SET phone = regexp_replace(phone, '[^0-9]', '', 'g');
```

will **overwrite original values** if executed. In practice exercises, use `SELECT` to inspect results rather than modifying the entire table.

If an application genuinely needs to normalize data:

- Keep raw data if needed for reconciliation/auditing.
- Define the target structure clearly.
- Test NULL, empty-string, and invalid-input cases.
- Run controlled migrations with a rollback plan.

### 14.5. Capture Groups in the Replacement String

In the replacement argument of `regexp_replace`, you can reference capture groups with `\1`, `\2`, etc., and use `\&` for the entire matched substring.

Example changing code separators:

```sql
SELECT regexp_replace(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    '\1/\2/\3'
) AS reformatted_invoice;
```

Result:

```text
INV/2026/0042
```

Example masking part of a token:

```sql
SELECT regexp_replace(
    'TOKEN-12345678',
    '^(TOKEN-)[0-9]{4}([0-9]{4})$',
    '\1****\2'
) AS masked_token;
```

Result:

```text
TOKEN-****5678
```

**Do not treat regex character masking as a complete security measure.** Never log or transmit sensitive data in ways that expose the raw string in other layers; maintain dedicated redaction and access-control policies.

### 14.6. Case-Sensitive vs. Case-Insensitive Replacement

```sql
SELECT
    regexp_replace(
        'sql SQL Sql',
        'sql',
        'PostgreSQL',
        'g'
    ) AS case_sensitive_replacement,
    regexp_replace(
        'sql SQL Sql',
        'sql',
        'PostgreSQL',
        'gi'
    ) AS case_insensitive_replacement;
```

In this example:

- `g`: replaces all lowercase `sql` matches.
- `gi`: replaces all matches case-insensitively.

The order of flag characters generally does not affect behavior for these flags, though keeping a consistent convention across your project is good practice.

## 15. Flags: Modifying Regex Behavior

Many regex functions accept a `flags` text parameter.

Notable flags:

| Flag | Practical Meaning |
| --- | --- |
| `i` | Case-insensitive |
| `c` | Case-sensitive |
| `g` | Global: applies to functions supporting multiple matches/replacements |
| `n` | Newline-sensitive matching |
| `p` | Partial newline-sensitive variant |
| `w` | Inverse partial newline-sensitive variant with its own rules |
| `s` | Single-line / non-newline-sensitive mode as defined by PostgreSQL |
| `x` | Expanded syntax: allows more readable pattern layout, with specific rules |

**Note:** Not every function accepts every flag. In particular, **`g` cannot be used to get "all matches" from `regexp_match`** because that function only returns a single array; for global extraction use `regexp_matches(...,'g')`.

### 15.1. The `i` Flag

```sql
SELECT regexp_match(
    'ERROR code=E42',
    '^error',
    'i'
) AS case_insensitive_match;
```

The result is an array containing `ERROR`, even though the pattern was written in lowercase.

### 15.2. The `x` Flag for Readable Patterns

A long regex can be hard to inspect:

```sql
SELECT regexp_match(
    'INV-2026-0042',
    '^
      ([A-Z]+)       # Code prefix
      -
      ([0-9]{4})     # Year
      -
      ([0-9]{4})     # Sequence number
    $',
    'x'
) AS readable_match;
```

In expanded mode, whitespace used for layout and syntax comments are handled differently from ordinary regex mode. Therefore, to match a **literal space** inside an expanded pattern, write it explicitly, such as `[[:space:]]` or an appropriate escape.

For regexes reviewed in code reviews, breaking out structure and comments makes missing anchors or wrong capture groups much easier to spot.

### 15.3. Newlines and Anchors

With a multi-line string:

```sql
SELECT
    'INFO start' || chr(10) || 'ERROR failed'
        ~ '^ERROR' AS default_anchor,
    regexp_match(
        'INFO start' || chr(10) || 'ERROR failed',
        '^ERROR',
        'n'
    ) AS newline_sensitive_match;
```

The `n` flag changes how PostgreSQL handles newlines for constructs like anchors. Depending on the requirement, it allows `^` to match at the start of a line within multi-line text.

Do not translate flags directly from JavaScript/PCRE to PostgreSQL based on familiar letters like `m`/`s` without checking: **PostgreSQL's flag set and newline rules have their own definitions**.

### 15.4. Check Server Version When Using Advanced Flags

`SHOW server_version;` reports the PostgreSQL version. Newer features and collation interactions can depend on version, build, and locale. For high-reliability applications, test patterns on your target database version and keep regression tests for edge cases.

## 16. Escaping at Two Layers: SQL String and Regex

This is a frequent source of confusion when copying patterns between application code and PostgreSQL.

### 16.1. SQL Uses Single Quotes

For example, searching for a single quote:

```sql
SELECT
    'It''s OK' ~ '''' AS contains_apostrophe;
```

Inside a standard SQL string literal, writing a literal `'` requires doubling it as `''`.

Regex syntax, meanwhile, uses **backslashes** to escape metacharacters such as dots.

### 16.2. `standard_conforming_strings`

Check with:

```sql
SHOW standard_conforming_strings;
```

In modern PostgreSQL installations, the default is `on`. In that mode, an ordinary literal like:

```sql
'\d+'
```

preserves the backslash so the regex engine interprets `\d` according to ARE syntax.

Example:

```sql
SELECT 'code=123' ~ '\d+' AS contains_digits;
```

If you use an **escape string literal** `E'...'`, you must escape the backslash at the **SQL layer**:

```sql
SELECT
    'code=123' ~ E'\\d+' AS contains_digits;
```

Both forms mean the same regex when `standard_conforming_strings = on`.

**Beginner recommendation:** prefer `[0-9]` or `[[:digit:]]` in simple SQL examples if you are not yet comfortable tracking backslash counts. In real projects, understand both escaping layers so you do not accidentally alter the pattern.

### 16.3. Backslashes in Java/JDBC Add Another Layer

In Java, source code:

```java
String regex = "\\d+";
```

creates a string containing the characters `\d+` at runtime. When passed as a bind parameter:

```java
String sql = "SELECT ? ~ ?";
```

the SQL driver sends the regex value cleanly via parameter binding, avoiding hand-written SQL literals with multiple layers of quotes and backslashes.

Never concatenate user input directly into a SQL string to "solve" escaping issues; that creates SQL injection risk.

## 17. `regexp_split_to_array`: Splitting a String into an Array

Function:

```sql
regexp_split_to_array(source, pattern [, flags])
```

uses a regex as the **delimiter** and returns `text[]`.

### 17.1. Splitting on Commas or Semicolons

```sql
SELECT regexp_split_to_array(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) AS tokens;
```

Result:

```text
{SQL,Java,PostgreSQL}
```

How the pattern works:

- `[,;]`: a comma or semicolon.
- `[[:space:]]*`: optional whitespace on both sides of the delimiter.

### 17.2. Empty Elements

```sql
SELECT regexp_split_to_array(
    'A,,B',
    ','
) AS tokens_with_empty_piece;
```

The result contains an **empty string element** in the middle because two consecutive delimiters have nothing between them.

Do not assume a split function strips empty elements automatically. If input allows repeated delimiters, decide whether to keep empty slot markers or filter them out after splitting.

### 17.3. Number of Elements in the Array

```sql
SELECT cardinality(
    regexp_split_to_array(
        'SQL, Java; PostgreSQL',
        '[[:space:]]*[,;][[:space:]]*'
    )
) AS token_count;
```

The result is `3`.

When storing multi-tag data, it is usually better to consider a one-to-many relational table instead of comma-separated text in a single column. Regex splitting is helpful for data import/transformation, not a substitute for proper relational modeling.

## 18. `regexp_split_to_table`: Splitting a String into Multiple Rows

`regexp_split_to_table` works like splitting to an array, but returns a **set of text rows**.

### 18.1. Basic Example

```sql
SELECT token
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) AS s(token);
```

Result of three rows:

```text
SQL
Java
PostgreSQL
```

### 18.2. Using `CROSS JOIN LATERAL` with a Source Table

```sql
WITH raw_tags(contact_id, tags) AS (
    VALUES
        (1, 'SQL, Java'),
        (2, 'PostgreSQL, SQL'),
        (3, '')
)
SELECT
    r.contact_id,
    x.tag
FROM raw_tags AS r
CROSS JOIN LATERAL regexp_split_to_table(
    r.tags,
    '[[:space:]]*,[[:space:]]*'
) AS x(tag)
WHERE x.tag <> ''
ORDER BY r.contact_id, x.tag;
```

The result contains the non-empty tags for contacts 1 and 2. Contact 3 has no valid tags so it does not appear after `WHERE x.tag <> ''`.

If you want to **keep contacts without tags as well**, use `LEFT JOIN LATERAL ... ON TRUE` and plan how to filter empty tokens without dropping the left-side row.

### 18.3. Preserving Element Position with `WITH ORDINALITY`

```sql
SELECT
    x.position,
    x.tag
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

`WITH ORDINALITY` appends a sequence number to the generated elements, useful when input order must be preserved.

This is a capability of set-returning functions in PostgreSQL, not the regex automatically determining the "most important" value.

## 19. Additional Functions in PostgreSQL 15 and Later

PostgreSQL 15 added regex functions suited to common usage patterns. On older servers, some of the functions below may not exist.

Check with:

```sql
SHOW server_version;
```

### 19.1. `regexp_like`: Returns a Boolean

```sql
SELECT regexp_like(
    'INV-2026-0042',
    '^INV-[0-9]{4}-[0-9]{4}$'
) AS valid_invoice_shape;
```

Returns `TRUE` for strings matching the pattern.

Flags can also be passed:

```sql
SELECT regexp_like(
    'inv-2026-0042',
    '^INV-[0-9]{4}-[0-9]{4}$',
    'i'
) AS valid_ignoring_case;
```

This function is convenient when you want a `regexp_like(text, pattern, flags)` API, though in longstanding PostgreSQL codebases `~`/`~*` remain very common.

### 19.2. `regexp_count`: Counting Matches

```sql
SELECT regexp_count(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=[[:alpha:]]+'
) AS tags_count;
```

Result: `3`.

`regexp_count` counts matching substrings under the function's rules, which differs from counting tokens after a split when the string contains malformed parts.

### 19.3. `regexp_instr`: Finding Match Position

```sql
SELECT regexp_instr(
    'abc123xyz',
    '[0-9]+'
) AS first_digit_group_position;
```

The result is `4` because the first digit group begins at the fourth character (PostgreSQL uses **1-based** character positions for this function).

When the pattern is not found, the function returns position 0 per `regexp_instr` semantics, rather than a NULL array like `regexp_match`.

### 19.4. `regexp_substr`: Returning the Matched Substring

```sql
SELECT regexp_substr(
    'ref=INV-2026-0042; ok',
    'INV-[0-9]{4}-[0-9]{4}'
) AS invoice_code;
```

Result: `INV-2026-0042`.

This function returns a text substring rather than an array; it can be handy when logic only needs the matched substring.

### 19.5. Extracting a Capture Group with the `subexpr` Parameter

On PostgreSQL versions supporting the full signature, `regexp_substr` can extract a specific group via its sixth parameter:

```sql
SELECT regexp_substr(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    1,  -- Starting search position
    1,  -- First occurrence
    '', -- Flags
    3   -- Third capture group
) AS invoice_sequence;
```

Result: `0042`.

This usage is handy when only one capture group is needed. For multiple groups simultaneously, `regexp_match` can be cleaner.

### 19.6. Do Not Confuse Position and Match Count

| Function | Result Meaning |
| --- | --- |
| `regexp_like` | Boolean: does it match? |
| `regexp_count` | How many matches exist? |
| `regexp_instr` | At which character position does the match appear? |
| `regexp_substr` | Which text substring matched? |
| `regexp_match` | Text array of capture groups from the first match |
| `regexp_matches` | Set of text arrays for one or more matches |

Do not swap function names simply because their syntax looks similar: return types and row counts can differ substantially.

## 20. Full Log Extraction

Text log data typically contains multiple fields. You can extract parts with regex, but treat this as an **unstructured-data transformation step**, not the best way to design logs.

### 20.1. Extracting the Log Level

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        '^(INFO|WARN|ERROR|DEBUG)[[:space:]]'
    ))[1] AS log_level
FROM regex_lab.logs
ORDER BY log_id;
```

For the five sample lines, the results are INFO, WARN, ERROR, INFO, DEBUG respectively.

### 20.2. Extracting the Order ID

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'order=([0-9]+)'
    ))[1] AS order_id_text
FROM regex_lab.logs
ORDER BY log_id;
```

Logs 101, 102, and 104 have an order ID; 103 and 105 return NULL.

### 20.3. Extracting the Amount

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text
FROM regex_lab.logs
ORDER BY log_id;
```

Pattern breakdown:

- `amount=`: fixed prefix.
- `[0-9]+`: at least one digit in the integer part.
- `(?:\.[0-9]+)?`: optional decimal part; uses `(?:...)` because a second capture group is not needed.
- The outer capture extracts the numeric text, such as `125.50` or `0`.

**Control where the pattern ends** if logs come from untrusted input: the regex above can match the prefix of a longer invalid string such as `amount=12.34.56`. For strictly formatted logs, add token boundaries or use a structured parser.

### 20.4. Extracting Multiple Fields in One SELECT

```sql
SELECT
    l.log_id,
    (regexp_match(
        l.log_line,
        '^(INFO|WARN|ERROR|DEBUG)'
    ))[1] AS log_level,
    (regexp_match(
        l.log_line,
        'order=([0-9]+)'
    ))[1] AS order_id_text,
    (regexp_match(
        l.log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text,
    (regexp_match(
        l.log_line,
        'code=([[:alnum:]]+)'
    ))[1] AS error_code
FROM regex_lab.logs AS l
ORDER BY l.log_id;
```

Descriptive result:

| log_id | log_level | order_id_text | amount_text | error_code |
| ---: | --- | --- | --- | --- |
| 101 | INFO | 1001 | 125.50 | NULL |
| 102 | WARN | 1002 | 0 | NULL |
| 103 | ERROR | NULL | NULL | E42 |
| 104 | INFO | 1003 | 78.25 | NULL |
| 105 | DEBUG | NULL | NULL | NULL |

Once fields are cleanly separated, subsequent steps can cast types, populate a normalized events table, and add constraints. For high-volume production logs, consider **emitting structured JSON logs at the source** to avoid repeated regex cost.

## 21. Data Normalization: Regex Is Only One Processing Layer

### 21.1. Emails: Regex Does Not Replace Real Verification

You can check basic shape:

```sql
SELECT
    contact_id,
    email,
    email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
        AS basic_email_shape
FROM regex_lab.contacts
ORDER BY contact_id;
```

This pattern catches obviously malformed inputs; it does **not** cover full standard email syntax and does not check DNS, mailboxes, deliverability, or domain policies.

For account registration, combine:

- Application/API validation.
- Business-defined normalization rules.
- Length and dangerous-input checks.
- Confirmation emails if deliverability must be proven.
- Unique constraints aligned with identity policies.

### 21.2. Order Codes: Store Normalized Data

If invoice codes always follow:

```text
INV-YYYY-NNNN
```

you can choose:

- A text column `invoice_code` with a regex `CHECK` constraint to protect shape.
- Typed numeric columns `invoice_year` and `sequence`, plus a mechanism to format the display code.
- Or a combination of both with consistency constraints.

Example:

```sql
CREATE TABLE regex_lab.invoices (
    invoice_code text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_invoice_code_format
        CHECK (
            invoice_code ~ '^INV-[0-9]{4}-[0-9]{4}$'
        )
);
```

This rejects malformed strings such as `INV-26-42`. However, it does **not** check business dates/years, issuance uniqueness rules, or sequence continuity.

### 21.3. Why Are Separate `NOT NULL` and `CHECK` Constraints Still Needed?

A constraint:

```sql
CHECK (email ~ '...')
```

can allow a `NULL` value through because `CHECK` only rejects **FALSE**, whereas expressions involving NULL evaluate to UNKNOWN.

If an email is required:

```sql
CREATE TABLE regex_lab.required_emails (
    user_id bigint PRIMARY KEY,
    email text NOT NULL,
    CONSTRAINT chk_required_email_basic_shape
        CHECK (
            email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
        )
);
```

`NOT NULL` requires presence; `CHECK` validates shape. The two constraints enforce **two distinct rules**.

### 21.4. Avoid Losing Accents and Unicode

A dangerous "cleanup" expression:

```sql
regexp_replace(full_name, '[^A-Za-z ]', '', 'g')
```

can **strip accented Vietnamese letters** like `Đ`, `ă`, `ê`. When processing personal names or international content, do not assume `A-Z` covers the entire alphabet.

If personal names need normalization, apply carefully designed Unicode, normalization, and business rules; simple ASCII regexes are usually inappropriate.

## 22. How Do Unicode, Locale, and Collation Affect Regex?

### 22.1. UTF-8 Stores Characters; Regex Describes Patterns

If the database uses `UTF8`, PostgreSQL can store many languages simultaneously. However, the regex `[A-Za-z]` does not automatically treat accented Latin letters or non-Latin scripts as letters.

`[[:alpha:]]` is often more useful when matching system-recognized alphabetic characters, though exact results should be verified against your PostgreSQL locale/collation and version.

Check with:

```sql
SHOW server_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

### 22.2. Case-Insensitive Does Not Mean Accent-Insensitive

```sql
SELECT
    'Bình' ~* 'bình' AS case_insensitive,
    'Bình' ~* 'binh' AS accent_automatically_removed;
```

In typical setups, the first expression matches and the second does not. Do not treat `~*` as a way to strip Vietnamese accents.

If a product requires `binh` to match `Bình`, define an accent/normalization policy and choose suitable tooling; you may need a normalized search column or dedicated, tested search extensions/algorithms.

### 22.3. Unicode Normalization and Combining Sequences

Identical-looking characters can have different code point sequences, such as precomposed `é` versus `e` plus combining acute.

```sql
SELECT
    U&'\00E9' COLLATE "C" =
      U&'e\0301' COLLATE "C" AS equal_before,
    normalize(U&'\00E9', NFC) COLLATE "C" =
      normalize(U&'e\0301', NFC) COLLATE "C" AS equal_after_nfc;
```

Under UTF8:

- `equal_before` is FALSE under `"C"`.
- `equal_after_nfc` is TRUE because both forms have been normalized to NFC.

Regex, `substring`, and `length` may count code points differently from **user-perceived characters**. If inputs contain combining marks, establish a normalization policy before validating character counts.

### 22.4. Nondeterministic Collations and Regex

PostgreSQL supports nondeterministic ICU collations for non-bytewise comparison rules. However, **regex and several pattern-matching operations are not supported identically with nondeterministic collations** in modern versions; you may receive an error instead of results like with deterministic collations.

Verify the column's collation, PostgreSQL version, and operators used. If you need regex filtering, you may need to run it on an expression with a suitable **deterministic collation**, such as a separate processed/normalized text column, rather than relying on a case/accent-insensitive collation everywhere.

Do not force every query to `COLLATE "C"` mechanically: doing so changes casing and international character semantics. Choose rules based on data requirements.

## 23. Regex and Data Type Accuracy

### 23.1. Do Not Use Regex to Replace Numeric/Date Types

A string:

```text
2026-02-31
```

matches the pattern:

```sql
'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
```

yet **February 31 does not exist**.

If the data represents a date, store `date` in the table, validate/convert with proper date logic, and handle input errors explicitly.

Similarly:

- Money: `numeric(p,s)`.
- Quantities: `integer`/`bigint`.
- Timestamps: `timestamptz`.
- Fixed-set statuses: `CHECK` or lookup table.

Regex is suitable for **recognizing text input structure** before converting to a proper type, not for replacing data type constraints.

### 23.2. Validate Bounds Before Casting Extracted Values

Suppose `amount=125.50` is extracted as text; before casting to `numeric(12,2)`, check:

- Are negative signs allowed?
- Are thousand separators allowed?
- How many decimal digits are permitted?
- Can the value exceed precision/scale?
- What is the currency unit?
- What are the exchange-rate and rounding rules?

Do not assume that because `regexp_match` returned a match, the subsequent cast is guaranteed to be safe.

## 24. Performance: Regex Can Be More Expensive Than Simple Comparisons

Regex is powerful because it expresses rich patterns, yet it carries cost:

- The engine must evaluate the pattern across text strings.
- Patterns with complex branches or repetitions can require significant work.
- Over millions of rows, running regex on every row increases CPU usage.
- Combining with global extraction can generate many intermediate rows.
- Patterns without selective literals can force PostgreSQL to scan most of the table.

### 24.1. Do Not Replace Equality with Regex Unnecessarily

Avoid:

```sql
SELECT *
FROM regex_lab.contacts
WHERE email ~ '^an@example\.com$';
```

when the business only needs exact email equality and case/collation are already settled. Equality:

```sql
WHERE email = 'an@example.com'
```

is clearer and more easily supported by a B-tree index.

Regex belongs where **the condition is truly pattern-based**, such as structured codes or logs containing tokens to extract.

### 24.2. Use `LIKE` for Simple Prefixes

When searching for notes starting with `INV-`:

```sql
WHERE note LIKE 'INV-%'
```

is generally clearer than:

```sql
WHERE note ~ '^INV-'
```

Depending on collation and operator class, a B-tree index can support `LIKE 'prefix%'` prefix searches. Simple anchored regexes can sometimes be optimized too, but **never assume every regex uses a B-tree**.

### 24.3. `pg_trgm` Can Accelerate Regex Search

PostgreSQL provides the `pg_trgm` extension for trigram-based search, including certain `LIKE`, `ILIKE`, and `~`/`~*` regex conditions.

If your environment permits creating extensions:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_contacts_note_trgm
ON regex_lab.contacts
USING gin (note gin_trgm_ops);
```

A query that may benefit:

```sql
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

Effectiveness depends on:

- Whether the pattern contains **useful trigrams** extractable from the regex.
- Selectivity.
- Row count and value distribution.
- GIN index maintenance cost.
- The PostgreSQL planner's choice.

Very broad patterns or those with few fixed literal characters may yield few useful trigrams; the index may still go unused.

### 24.4. Measure with `EXPLAIN`

```sql
EXPLAIN
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

On a six-row sample table, PostgreSQL will very likely pick `Seq Scan`; that does not mean the regex or index is wrong.

On real data, consider:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

`EXPLAIN ANALYZE` actually executes the `SELECT`. On write statements like `UPDATE` or `DELETE`, it modifies data, so run only under controlled procedures.

### 24.5. Move Repeatedly Parsed Text into Structured Columns

If millions of queries must extract `order_id` from `log_line`, it may be better to emit structured logs or load values into dedicated columns upfront:

```text
log_id | log_level | order_id | amount | message
```

Instead of repeating `regexp_match` in every `SELECT`, the application can query and index `order_id` directly. That is often a data-model improvement rather than just a regex optimization.

## 25. Safety: SQL Injection and Untrusted Regex Are Two Different Risks

### 25.1. Bind Parameters to Prevent SQL Injection

Do not concatenate input directly:

```java
// Unsafe:
String sql =
    "SELECT contact_id FROM regex_lab.contacts " +
    "WHERE note ~ '" + userPattern + "'";
```

If `userPattern` contains quotes or malicious SQL, the statement can change meaning or fail.

Use `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class ContactRegexSearch {
    public void search(Connection conn, String pattern)
            throws SQLException {
        String sql =
            "SELECT contact_id, note " +
            "FROM regex_lab.contacts " +
            "WHERE note ~ ? " +
            "ORDER BY contact_id";

        try (PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setString(1, pattern);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("contact_id");
                    String note = rs.getString("note");
                    System.out.println(id + ": " + note);
                }
            }
        }
    }
}
```

Here `?` is bound as a **regex value**, not spliced into SQL syntax. This addresses **SQL injection**, but does not eliminate risks from a malicious or overly complex regex.

### 25.2. CPU-Exhausting Regexes (*Regular Expression DoS*)

A regex pattern with complex branching and repetition can cause an engine to take a long time on carefully crafted inputs.

Therefore, if users can supply their own regexes to search large tables:

- Limit regex length.
- Limit matched text size where reasonable.
- Limit row counts and query duration.
- Offer structured/approved patterns instead of arbitrary user regexes when possible.
- Enforce `statement_timeout` at the application/session/transaction level per policy.
- Monitor queries consuming abnormal CPU.
- Restrict data permissions so regex cannot scan sensitive or huge tables unnecessarily.

Example of a time-bounded transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SELECT contact_id
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';

COMMIT;
```

`SET LOCAL` applies only within the transaction. If the query times out and the transaction enters an error state, `ROLLBACK` before continuing. A timeout is a **safety guardrail**, not a replacement for controlling patterns and data volume.

### 25.3. Do Not Treat Regex Input as JavaScript/PCRE Code

PostgreSQL regex does not support all syntax from other engines. A pattern valid in JavaScript/PCRE may:

- Produce different results.
- Be unsupported.
- Interpret escapes differently.
- Have different execution cost.

If an application accepts user-supplied regexes, **define the supported regex dialect** explicitly. Do not vaguely claim "supports all regexes."

### 25.4. Do Not Leak Sensitive Data via Extraction

Regex can locate and extract emails, identifiers, tokens, and phone numbers. Never automatically dump extracted results to logs/debug output or return them to callers without authorization.

Extracting card numbers or tokens from sensitive text also creates extra copies of the data, expanding access-control and retention scope. If the real need is just a **yes/no** check, use a boolean match instead of returning the sensitive substring.

## 26. Common PostgreSQL Regex Mistakes

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `LIKE 'A%'` changed to `~ 'A%'` and fails to match | `%` is not a regex wildcard | Use `'^A'` or keep `LIKE` |
| Dot matches any character | `.` is a metacharacter | Use `\.` for a literal dot |
| Regex matches part of an invalid string | Missing `^` and `$` | Anchor the full string when validating |
| Longer-than-expected code still matches | Pattern lacks token boundaries | Add appropriate anchors/boundaries |
| `regexp_match` returns only one match | Designed for first match only | Use `regexp_matches(...,'g')` |
| `regexp_matches` drops source rows | Set-returning function yields 0 rows on no match | `LEFT JOIN LATERAL` or `regexp_match` |
| `regexp_match` returns an array instead of text | Return type is `text[]` | Index `[1]`, `[2]` or use `regexp_substr` |
| Group index shifted | Added new capturing parentheses | Use `(?:...)` when capture is unneeded |
| `regexp_replace` replaces only one occurrence | Missing `g` flag | Pass `'g'` to replace all |
| `regexp_replace` strips accents from names | Pattern accepts ASCII only | Design Unicode-aware patterns |
| `~*` fails to match unaccented text | Does not strip accents automatically | Use a normalization/search strategy |
| `CHECK (text ~ pattern)` lets NULL through | CHECK does not reject UNKNOWN | Add `NOT NULL` if required |
| `email !~ regex` misses NULL emails | `NULL !~ regex` is NULL | `IS NULL OR email !~ regex` |
| Splitting `A,,B` yields empty elements | Consecutive delimiters | Define how empty tokens are handled |
| `regexp_substr` does not exist | Older PostgreSQL version | Use `substring`/`regexp_match` or upgrade |
| Interpolating regex into SQL string | SQL injection | Use `PreparedStatement`/bind parameters |
| Slow regex query | Full-table scan / complex pattern | Pre-filter, index appropriately, `EXPLAIN` |
| Assuming B-tree accelerates every regex | Regex is not a simple range check | Consider `pg_trgm` and measure |
| Different results from Java Regex | Different dialect/escaping/locale | Test directly on target PostgreSQL |
| Nondeterministic ICU collation errors on regex | Pattern matching support limits | Check collation and use suitable deterministic rules |
| Regex parses a "valid" date but cast fails | Regex checks shape only | Validate calendar dates and use `date` type |
| Regex extracts money then integer cast overflows | Input exceeds integer range | Check range; use `numeric`/`bigint` appropriately |
| Regex runs slowly on unusual input | Complex pattern / large input | Cap length, timeout, permissions, monitor |

## 27. Practice Exercises with Hints and Answers

The exercises use `regex_lab.contacts` and `regex_lab.logs` from the beginning of the lesson.

### Exercise 1. Find notes containing an invoice code

```sql
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

**Answer:** contacts 1, 2, 5, and 6.

### Exercise 2. Verify whether a code matches the full-string format

```sql
SELECT
    'INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS correct_code,
    'prefix INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS incorrect_code;
```

**Answer:** `TRUE` and `FALSE`. Anchors make the difference.

### Exercise 3. Find emails ending with example.com, case-insensitively

```sql
SELECT contact_id, email
FROM regex_lab.contacts
WHERE email ~* '@example\.com$'
ORDER BY contact_id;
```

**Answer:** contacts 1 and 2.

### Exercise 4. Find missing emails or emails failing a basic shape check

```sql
SELECT contact_id, email
FROM regex_lab.contacts
WHERE email IS NULL
   OR email !~* '^[^@[:space:]]+@[^@[:space:]]+$'
ORDER BY contact_id;
```

**Answer:** contacts 3 and 4. This is a shape check only, not real email verification.

### Exercise 5. Extract invoice year from notes

```sql
SELECT
    contact_id,
    (regexp_match(
        note,
        'INV-([0-9]{4})-[0-9]{4}'
    ))[1] AS invoice_year
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Answer:** contact 1 -> 2026; 2 -> 2026; 5 -> 2025; 6 -> 2026; the two contacts without codes return NULL.

### Exercise 6. Extract the full invoice code with `substring`

```sql
SELECT
    contact_id,
    substring(
        note FROM 'INV-[0-9]{4}-[0-9]{4}'
    ) AS invoice_code
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Answer:** the known codes on the four contacts; non-matching rows remain visible with NULL.

### Exercise 7. Extract two groups from an invoice code

```sql
SELECT
    regexp_match(
        'INV-2026-0042',
        '^INV-([0-9]{4})-([0-9]{4})$'
    ) AS groups;
```

**Answer:** array `{2026,0042}`. Group 1 is the year, group 2 is the sequence number.

### Exercise 8. Find all tags in a string

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=([[:alpha:]]+)',
    'g'
);
```

**Answer:** three rows containing arrays `{SQL}`, `{Java}`, `{SQL}`. Both SQL tags are kept because there are two matches.

### Exercise 9. Why does `regexp_matches` drop contacts without tags?

**Answer:** because it is a **set-returning function**: no match -> returns **0 rows**. With `CROSS JOIN LATERAL`, source rows with no right-side rows are eliminated. To preserve them, use `LEFT JOIN LATERAL ... ON TRUE` or `regexp_match` for a single match.

### Exercise 10. Extract both error codes from Dung's note

```sql
SELECT m.parts[1] AS error_id
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]+)',
    'g'
) AS m(parts)
WHERE c.contact_id = 4;
```

**Answer:** two text values `42` and `103`.

### Exercise 11. Normalize whitespace

```sql
SELECT regexp_replace(
    'A   B     C',
    '[[:space:]]+',
    ' ',
    'g'
);
```

**Answer:** `A B C`.

### Exercise 12. Remove hyphens, spaces, and plus signs from phone numbers

```sql
SELECT
    contact_id,
    regexp_replace(phone, '[^0-9]', '', 'g') AS digits_only
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Answer:** digit-only strings; `phone NULL` stays NULL. **Do not** conclude every result is a valid phone number.

### Exercise 13. Reformat an invoice code using backreferences

```sql
SELECT regexp_replace(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    '\1/\2/\3'
);
```

**Answer:** `INV/2026/0042`.

### Exercise 14. Split a list into an array

```sql
SELECT regexp_split_to_array(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
);
```

**Answer:** `{SQL,Java,PostgreSQL}`.

### Exercise 15. Split a list into rows with positions

```sql
SELECT x.position, x.tag
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

**Answer:** `(1,SQL)`, `(2,Java)`, `(3,PostgreSQL)`.

### Exercise 16. Find all logs starting with INFO or WARN

```sql
SELECT log_id, log_line
FROM regex_lab.logs
WHERE log_line ~ '^(INFO|WARN)[[:space:]]'
ORDER BY log_id;
```

**Answer:** logs 101, 102, and 104.

### Exercise 17. Extract order ID from logs

```sql
SELECT
    log_id,
    (regexp_match(
        log_line, 'order=([0-9]+)'
    ))[1] AS order_id_text
FROM regex_lab.logs
ORDER BY log_id;
```

**Answer:** 101 -> 1001; 102 -> 1002; 104 -> 1003; other logs have `order_id_text NULL`.

### Exercise 18. Extract amount from logs

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text
FROM regex_lab.logs
ORDER BY log_id;
```

**Answer:** 101 -> 125.50; 102 -> 0; 104 -> 78.25; remaining logs NULL. The result is text.

### Exercise 19. Count tags with `regexp_count`

*Requires PostgreSQL 15 or later.*

```sql
SELECT regexp_count(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=[[:alpha:]]+'
) AS total_tags;
```

**Answer:** `3`.

### Exercise 20. Extract match with `regexp_substr`

*Requires PostgreSQL 15 or later.*

```sql
SELECT regexp_substr(
    'ref INV-2026-0042 done',
    'INV-[0-9]{4}-[0-9]{4}'
);
```

**Answer:** `INV-2026-0042`.

### Exercise 21. Why does `CHECK (col ~ pattern)` not force `col` to have a value?

**Answer:** if `col` is NULL, the regex expression evaluates to UNKNOWN. PostgreSQL `CHECK` does not reject UNKNOWN; to require a non-null value, add `NOT NULL`.

### Exercise 22. Distinguish `'g'` and `'i'`

```sql
SELECT
    regexp_replace('sql SQL Sql', 'sql', 'X', 'g')
        AS only_same_case,
    regexp_replace('sql SQL Sql', 'sql', 'X', 'gi')
        AS all_cases;
```

**Answer:** `'g'` replaces all matches with matching default case; `'gi'` is both global and case-insensitive.

### Exercise 23. Why should you not use `[A-Za-z]+` to validate Vietnamese full names?

**Answer:** many accented Vietnamese letters fall outside the ASCII `A-Z`/`a-z` range. The pattern can reject valid data or strip accents if used for replacement. A proper Unicode/locale and business strategy is required.

### Exercise 24. Why does regex not replace the `date` type?

```sql
SELECT '2026-02-31' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    AS correct_shape;
```

**Answer:** it can return TRUE because the shape matches, yet February 31 is not a valid calendar date. Validate/parse with proper date logic and store `date` when the data represents a date.

### Exercise 25. Which regex query should consider `pg_trgm`?

Suppose a table has millions of notes and users frequently search for `INV-YYYY-NNNN` codes appearing in the middle of strings.

**Hint:** consider a GIN trigram index on the searched column, check whether the pattern has sufficiently selective fixed parts, and measure with `EXPLAIN (ANALYZE, BUFFERS)`. Do not assume an index speeds up every regex, especially wildcard-heavy patterns without useful trigrams.

### Exercise 26. Is a user-supplied regex completely safe once passed as a bound parameter?

**Answer:** no. Parameter binding prevents SQL injection, yet the regex input can still be overly long, have CPU-intensive backtracking/repetition structure, or be used to scan data beyond what is intended. Enforce pattern limits, search scope, timeouts, and access permissions.

## 28. Practical Checklist Before Adding Regex to an Application

Before shipping a regex in a migration, API, or report, ask yourself:

| Question | What to Confirm |
| --- | --- |
| Match the full string or a substring? | `^...$` vs. unanchored pattern |
| Need only a simple prefix? | `LIKE` may be clearer than regex |
| Should case matter? | `~` / `~*` or `i` flag |
| Are `NULL` values possible? | Don't forget UNKNOWN in `WHERE`/`CHECK` |
| Need one match or all matches? | `regexp_match` vs. `regexp_matches(...,'g')` |
| Keep non-matching rows? | `regexp_match` or `LEFT JOIN LATERAL` |
| Multiple capture groups? | Verify `[1]`, `[2]` indexing |
| Group only for quantifiers/alternation? | Use `(?:...)` when capture is unneeded |
| Any literal regex metacharacters? | Escape dots, brackets, special chars |
| Mixing SQL and regex escaping layers? | Check `standard_conforming_strings` / `E'...'` |
| Handling Unicode/Vietnamese? | Do not assume `[A-Za-z]` covers all letters |
| Need accent-insensitive matching? | `~*` does not strip accents automatically |
| Parsing numbers or dates after match? | Validate value bounds, not just shape |
| Running PostgreSQL older than 15? | Check `regexp_like/count/instr/substr` availability |
| Using nondeterministic collation? | Verify regex support |
| User-supplied regex input? | Bind parameters, limit complexity, enforce timeouts |
| Querying millions of rows? | Pre-filter, consider `pg_trgm`, measure `EXPLAIN` |
| Extracting fields frequently? | Consider storing structured columns |
| Regex extracts sensitive data? | Restrict permissions, masking, logging |
| Tested edge cases? | Empty strings, NULL, accented chars, escapes, repeated matches |

## 29. Summary

**Regular expressions and pattern extraction** in PostgreSQL help work with semi-structured strings: order codes, logs, tags, and text imported from external systems.

Key takeaways:

1. **`~` and `~*`** test whether a string matches a regex; `!~` and `!~*` test the negation. These operators **do not require a full-string match** unless anchored.
2. **`^`, `$`, character classes, and quantifiers** describe structure, such as `^INV-[0-9]{4}-[0-9]{4}$`.
3. **Capture groups `(...)`** extract individual parts; `(?:...)` groups syntax without capturing.
4. **`regexp_match`** returns one `text[]` array or NULL; **`regexp_matches`** is a set-returning function and the `g` flag emits one row per match.
5. **`LEFT JOIN LATERAL`** is essential when extracting multiple matches while **preserving non-matching source rows**.
6. **`substring(... FROM pattern)`** and `regexp_substr` extract a single matched substring; check PostgreSQL 15+ availability for `regexp_substr`, `regexp_count`, `regexp_instr`, and `regexp_like`.
7. **`regexp_replace`** replaces matches; the `g` flag replaces all occurrences, and backreferences `\1`/`\2` reuse capture groups in the replacement.
8. **`regexp_split_to_array` and `regexp_split_to_table`** turn delimited strings into arrays or rows.
9. **Regex is not a complete business validator**: valid email shape does not prove an email exists; valid date shape does not prove a valid calendar date; valid digits do not guarantee values fit a type's range.
10. **SQL escaping and regex escaping are separate layers.** Use prepared statements/bind parameters to pass patterns safely instead of concatenating input into SQL.
11. **Unicode, locale, and collation** affect character classes and case-insensitive matching; `~*` does not remove Vietnamese accents.
12. **Performance and security** must be controlled when regex runs over large datasets or accepts user patterns. `pg_trgm` can help some workloads, but always measure.

An easy workflow to apply:

```text
Input text
       |
       v
Identify goal:
  Matches?       -> ~ / ~*
  One match?     -> regexp_match / substring
  Many matches?  -> regexp_matches(..., 'g')
  Replace?       -> regexp_replace
  Split tokens?  -> regexp_split_to_array / regexp_split_to_table
       |
       v
Handle NULL, non-matches, Unicode
       |
       v
Validate business rules and cast types
       |
       v
Store structured data / query / report
```

**Rule of thumb:** use regex to **recognize and extract text patterns**, use **PostgreSQL data types and constraints** to protect data meaning, and use **proper JOIN/NULL handling** so extracting multiple matches never corrupts row counts.
