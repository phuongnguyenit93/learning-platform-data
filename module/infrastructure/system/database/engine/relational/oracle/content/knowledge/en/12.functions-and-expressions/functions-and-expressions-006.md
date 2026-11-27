# REGEXP_LIKE, REGEXP_SUBSTR, REGEXP_REPLACE, and Usage Limits in Oracle Database

Oracle Database provides regular expressions to validate, extract, and transform strings. Three commonly used features are:

- **`REGEXP_LIKE`**: a filter condition testing whether a string matches a pattern.
- **`REGEXP_SUBSTR`**: extracts the portion of a string matching a pattern or a capture group within it.
- **`REGEXP_REPLACE`**: replaces portions of a string matching a pattern with other content.

These functions are useful when data does not follow a completely fixed structure, such as order codes, phone numbers, log strings, or input imported from multiple systems. However, regex is not a replacement for every search operation. For simple conditions such as prefix matching, `=` or `LIKE` is usually easier to read and more efficient. Overly complex expressions are also hard to maintain, CPU-intensive, and prone to unintended matches.

This lesson explains Oracle's syntax, pattern components, match parameters, capture groups, extraction and replacement techniques, technical limits, `NULL` handling, performance, and security. Examples target Oracle Database 19c and later, using SQL*Plus, SQLcl, or a compatible SQL client.

## 1. What are regular expressions used for in Oracle?

### 1.1. Comparing LIKE and REGEXP

`LIKE` works well with two basic wildcards:

- `%`: zero or more characters.
- `_`: exactly one character.

Example:

```sql
SELECT product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';
```

If you need to verify a code has an exact structure such as three letters, a hyphen, and four digits, `LIKE` can be written for it, but it is awkward to express precisely. Regex expresses this naturally:

```sql
SELECT product_code
FROM   demo_products
WHERE  REGEXP_LIKE(product_code, '^[[:alpha:]]{3}-[[:digit:]]{4}$');
```

The pattern above requires the entire string to have the form:

```text
ABC-1234
```

Here `^` marks the start of the string, `$` marks the end of the string, `[[:alpha:]]{3}` matches three letters, and `[[:digit:]]{4}` matches four digits.

| Need | Usually Appropriate Tool |
| --- | --- |
| Exact equality to a single value | `=` |
| Membership in a list of values | `IN` |
| Starts with a simple prefix | `LIKE 'ABC%'` |
| Contains a simple substring | `LIKE '%ABC%'` |
| Complex structure validation | `REGEXP_LIKE` |
| Extracting a substring by pattern | `REGEXP_SUBSTR` |
| Normalizing/replacing substrings by pattern | `REGEXP_REPLACE` |

Do not use regex merely because it looks more powerful. Choose the simplest expression that accurately captures the requirement.

### 1.2. Three functions solving three distinct tasks

| Feature | Role | Result |
| --- | --- | --- |
| `REGEXP_LIKE(source, pattern, ...)` | Condition check | TRUE/FALSE/UNKNOWN in SQL context |
| `REGEXP_SUBSTR(source, pattern, ...)` | Search and extract | Matched substring, or `NULL` if not found |
| `REGEXP_REPLACE(source, pattern, replacement, ...)` | Search and replace | String with replacements applied |

**`REGEXP_LIKE` is a SQL condition**, typically appearing in `WHERE`, `CASE WHEN`, or `CHECK`. It is not a string-returning function like `REGEXP_SUBSTR`.

## 2. REGEXP_LIKE syntax

### 2.1. General syntax

```sql
REGEXP_LIKE(
    source_char,
    pattern
    [, match_param]
)
```

- `source_char`: character expression to evaluate, such as a `VARCHAR2` column.
- `pattern`: regular expression to match.
- `match_param`: optional matching behavior flags, such as case sensitivity or newline handling.

Example:

```sql
SELECT employee_id, email
FROM   employees
WHERE  REGEXP_LIKE(email, '^[[:alnum:]_.+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}$', 'i');
```

This is a **basic email shape check**, not a full RFC-compliant email validator. It may reject certain valid edge-case addresses or accept addresses that do not actually exist. Real email verification usually requires additional business rules and mail-system confirmation.

### 2.2. Regex searches anywhere in the string by default

Without `^` and `$` anchors, Oracle can match a substring anywhere inside the source string.

Example:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Order AB-2048 shipped',
                          '[[:alpha:]]{2}-[[:digit:]]{4}')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

The result is `MATCH`, because the string contains the segment `AB-2048`.

If the **entire string** must match the format, use anchors:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('AB-2048',
                          '^[[:alpha:]]{2}-[[:digit:]]{4}$')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

### 2.3. Distinguishing REGEXP_LIKE from LIKE

`LIKE` uses `%` and `_` as wildcards. In regex, the symbols differ:

| Goal | LIKE | Regex |
| --- | --- | --- |
| Any sequence of characters | `%` | `.*` |
| Any single character | `_` | `.` |
| Start of string | Prefix pattern such as `'ABC%'` | `^` |
| End of string | Suffix pattern such as `'%XYZ'` | `$` |
| Any digit | No concise equivalent | `[[:digit:]]` |
| Repeat 3 to 5 times | No quantifier | `{3,5}` |
| Either of two options | Multiple conditions | `(A|B)` |

Never carry LIKE patterns directly into REGEXP or vice versa. For example, `REGEXP_LIKE(code, 'A%')` does not mean `code LIKE 'A%'`: in regex, `%` is a literal percent sign, whereas `.*` represents an arbitrary suffix.

## 3. Basic pattern components

Oracle supports POSIX regular expressions, Unicode regular expression guidelines, and several Perl-influenced extensions. Do not assume every syntax feature from PCRE, Java, or JavaScript works in Oracle.

### 3.1. Anchors and wildcards

| Symbol | Meaning |
| --- | --- |
| `^` | Start of string; in multiline mode, matches the start of each line |
| `$` | End of string; in multiline mode, matches the end of each line |
| `.` | Any single character, excluding newline by default |
| `\` | Escapes special characters or denotes certain supported character classes |

Example matching codes starting with `INV-`:

```sql
SELECT order_code
FROM   orders
WHERE  REGEXP_LIKE(order_code, '^INV-');
```

Example matching codes ending with four digits:

```sql
SELECT order_code
FROM   orders
WHERE  REGEXP_LIKE(order_code, '[[:digit:]]{4}$');
```

### 3.2. Character classes and bracket expressions

Use square brackets to match one character from a set:

| Pattern | Meaning |
| --- | --- |
| `[ABC]` | A single character: A, B, or C |
| `[A-Z]` | A letter in the range A through Z under the active matching rules |
| `[0-9]` | An ASCII digit from 0 to 9 |
| `[^0-9]` | A character not in the digit set |
| `[[:digit:]]` | A character in the POSIX digit class |
| `[[:alpha:]]` | A character in the alphabetic class |
| `[[:alnum:]]` | An alphanumeric character |
| `[[:space:]]` | A whitespace character |
| `[[:lower:]]` | A lowercase character |
| `[[:upper:]]` | An uppercase character |

Example accepting only codes consisting of uppercase letters and digits:

```sql
SELECT code
FROM   demo_codes
WHERE  REGEXP_LIKE(code, '^[[:upper:][:digit:]]+$');
```

POSIX character classes express intent by character category. For multilingual data, results also depend on character set, collation, and environment Unicode rules; do not treat ranges like `A-Z` or `0-9` as universal representations of every letter or digit worldwide.

### 3.3. Quantifiers: repetition counts

| Symbol | Meaning |
| --- | --- |
| `*` | 0 or more times |
| `+` | 1 or more times |
| `?` | 0 or 1 time |
| `{m}` | Exactly m times |
| `{m,}` | At least m times |
| `{m,n}` | Between m and n times |

Examples:

```sql
-- One or more digits.
REGEXP_LIKE(code, '[[:digit:]]+')

-- Exactly 8 digits.
REGEXP_LIKE(code, '^[[:digit:]]{8}$')

-- Between 2 and 4 letters.
REGEXP_LIKE(code, '^[[:alpha:]]{2,4}$')
```

A quantifier applies to the immediately preceding element. To repeat a sequence, enclose it in parentheses:

```sql
-- One or more groups of two digits.
REGEXP_LIKE(code, '^([[:digit:]]{2})+$')
```

### 3.4. Alternation and grouping

- `|` represents logical OR alternation.
- `(...)` groups part of a pattern; the group can also serve as a capture group for extraction/replacement.

Example matching codes starting with `INV` or `CRN`, followed by a hyphen and six digits:

```sql
SELECT document_code
FROM   documents
WHERE  REGEXP_LIKE(
         document_code,
         '^(INV|CRN)-[[:digit:]]{6}$'
       );
```

This pattern accepts `INV-123456` and `CRN-987654`, while rejecting `ABC-123456` or `INV-123`.

### 3.5. Escaping special characters

To match a literal dot, escape it because `.` in regex matches any character.

```sql
SELECT host_name
FROM   server_inventory
WHERE  REGEXP_LIKE(host_name, '\.example\.com$');
```

This pattern matches strings ending in `.example.com`. Inside Oracle SQL string literals, backslashes are not processed as string escapes like in Java; here, the backslash acts directly as the regex escape character.

If the pattern is embedded inside a Java string, JSON payload, or another configuration layer, you must also handle escaping for that outer layer's syntax.

### 3.6. Greedy matching and match scope

Standard quantifiers are greedy, matching as much text as possible while allowing the pattern to succeed. Example:

```sql
SELECT REGEXP_SUBSTR(
         'A<one><two>B',
         '<.*>'
       ) AS matched_text
FROM dual;
```

The pattern `<.*>` matches from the first `<` to the last `>`, returning `<one><two>`.

To capture only the first short tag, constrain the pattern so it cannot cross `>`:

```sql
SELECT REGEXP_SUBSTR(
         'A<one><two>B',
         '<[^>]*>'
       ) AS first_tag
FROM dual;
```

The result is `<one>`. Constraining the allowed character class is often clearer and more predictable than relying on non-greedy syntax that may behave differently across regex engines.

## 4. The match_param parameter

Oracle lets you pass an optional parameter string to alter matching behavior.

| Flag | Effect |
| --- | --- |
| `'i'` | Case-insensitive matching |
| `'c'` | Case-sensitive matching |
| `'n'` | Dot `.` matches newline characters as well |
| `'m'` | `^` and `$` match start/end of each line in multiline strings |
| `'x'` | Ignores whitespace in the pattern (extended matching mode) |

### 4.1. i and c: case sensitivity

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database', '^oracle', 'i')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS insensitive_result
FROM dual;
```

With `'i'`, letter case is ignored during matching.

To enforce case sensitivity explicitly:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database', '^oracle', 'c')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS sensitive_result
FROM dual;
```

Although case-sensitive matching is typically the default, passing `'c'` or `'i'` explicitly makes business intent clear. Collation settings can also influence matching.

### 4.2. n: dot matches newline

By default, `.` does not match newline characters. Add `'n'` to change this:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'first line' || CHR(10) || 'second line',
                'first.*second',
                'n'
              )
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS newline_result
FROM dual;
```

`CHR(10)` inserts a line feed. With `'n'`, `.` can match across the newline character according to Oracle rules.

### 4.3. m: per-line anchors

`m` changes how `^` and `$` behave on multiline strings:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'header' || CHR(10) || 'ERROR: disk full',
                '^ERROR:',
                'm'
              )
         THEN 'FOUND'
         ELSE 'NOT FOUND'
       END AS multiline_result
FROM dual;
```

In multiline mode, `^ERROR:` matches the start of the second line, not only the start of the entire string.

Distinguish clearly:

- `m` controls whether `^`/`$` anchors match line boundaries.
- `n` controls whether `.` matches newline characters.

These two flags do not substitute for each other.

### 4.4. x: ignore whitespace in the pattern

`x` mode improves readability of long patterns by ignoring whitespace inside the pattern itself:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'INV-123456',
                '^ [[:alpha:]]{3} - [[:digit:]]{6} $',
                'x'
              )
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS extended_result
FROM dual;
```

When using `x`, note that spaces inside the pattern are no longer matched literally. If you genuinely need to match whitespace, express it explicitly using a character class such as `[[:space:]]`.

### 4.5. Combining flags

Match parameter flags can be combined:

```sql
REGEXP_LIKE(log_message, '^error:.*timeout', 'in')
```

This pattern is case-insensitive and allows `.` to span newlines. Keep flag strings concise and intentional, and document non-obvious patterns for maintainers.

## 5. REGEXP_SUBSTR: extracting pattern matches

### 5.1. Syntax

```sql
REGEXP_SUBSTR(
    source_char,
    pattern
    [, position
       [, occurrence
          [, match_param
             [, subexpr]
          ]
       ]
    ]
)
```

| Parameter | Meaning |
| --- | --- |
| `source_char` | Source string |
| `pattern` | Pattern to locate |
| `position` | Starting search position, defaults to 1 |
| `occurrence` | Which occurrence to extract, defaults to 1 |
| `match_param` | Matching flags such as `i`, `c`, `n`, `m`, `x` |
| `subexpr` | Capture group to return; 0 returns the whole match, 1–9 returns the corresponding group |

If no match is found, the function returns `NULL`. `position` is measured in characters per function semantics; do not convert it manually to a byte offset.

### 5.2. Extracting the first occurrence

```sql
SELECT REGEXP_SUBSTR(
         'Order AB-2048 shipped',
         '[[:alpha:]]+-[[:digit:]]+'
       ) AS order_code
FROM dual;
```

Result:

```text
AB-2048
```

Beyond literals, it is commonly applied directly to table columns:

```sql
SELECT log_id,
       REGEXP_SUBSTR(message, '[[:alpha:]]+-[[:digit:]]+') AS order_code
FROM   application_logs;
```

### 5.3. Extracting the nth occurrence

```sql
SELECT REGEXP_SUBSTR(
         'red,green,blue,yellow',
         '[^,]+',
         1,
         3
       ) AS third_item
FROM dual;
```

The result is `blue`.

Here:

- `position = 1`: start at the first character.
- `occurrence = 3`: extract the third match.
- `[^,]+`: one or more non-comma characters.

The function searches for the next occurrence after the previous match, rather than merely advancing one character. This makes it handy for extracting sequential tokens.

**Note:** `[^,]+` skips empty tokens. For `'red,,blue'`, the second match is `blue`, not an empty string between the two commas. If empty fields in CSV data must be preserved, use a more appropriate parsing strategy rather than relying blindly on `[^,]+`.

### 5.4. Extracting a capture group with subexpr

Suppose the string is `Order AB-2048 shipped` and you only want the numeric part:

```sql
SELECT REGEXP_SUBSTR(
         'Order AB-2048 shipped',
         '([[:alpha:]]+)-([[:digit:]]+)',
         1,
         1,
         'c',
         2
       ) AS order_number
FROM dual;
```

The result is `2048`.

The pattern defines two groups:

1. `([[:alpha:]]+)`: the letters `AB`.
2. `([[:digit:]]+)`: the digits `2048`.

`subexpr = 2` instructs the function to return the second capture group instead of the entire match `AB-2048`. The default `subexpr = 0` returns the entire match.

### 5.5. Extracting multiple fields from a single string

Example parsing code `INV-2026-00125`:

```sql
SELECT
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 1
    ) AS document_type,
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 2
    ) AS document_year,
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 3
    ) AS document_sequence
FROM dual;
```

Conceptual result:

| DOCUMENT_TYPE | DOCUMENT_YEAR | DOCUMENT_SEQUENCE |
| --- | --- | --- |
| INV | 2026 | 00125 |

The sequence is returned as a string, preserving leading zeros. Converting it to NUMBER would turn `00125` into 125 and lose its original representation.

### 5.6. Using REGEXP_SUBSTR to split tokens

For words separated by one or more spaces:

```sql
SELECT REGEXP_SUBSTR(
         'Oracle   Database SQL',
         '[^[:space:]]+',
         1,
         2
       ) AS second_word
FROM dual;
```

The result is `Database`.

For comma-delimited data:

```sql
SELECT REGEXP_SUBSTR(
         'A12,B34,C56',
         '[^,]+',
         1,
         LEVEL
       ) AS token
FROM dual
CONNECT BY REGEXP_SUBSTR(
             'A12,B34,C56',
             '[^,]+',
             1,
             LEVEL
           ) IS NOT NULL;
```

This example illustrates generating multiple rows from sequential occurrences. On large datasets, evaluate the cost of repeated expression evaluation and choose a splitting approach suited to your application architecture.

### 5.7. When does REGEXP_SUBSTR return NULL?

Common situations:

- No part of the source string matches the pattern.
- The source string is `NULL`.
- `position` starts past the searchable portion of the string.
- The requested `occurrence` exceeds the actual number of matches.

When the result is `NULL`, you cannot automatically conclude the source string itself was NULL. The source may contain data that simply did not match the pattern.

## 6. REGEXP_REPLACE: pattern-based replacement

### 6.1. Syntax

```sql
REGEXP_REPLACE(
    source_char,
    pattern
    [, replace_string
       [, position
          [, occurrence
             [, match_param]
          ]
       ]
    ]
)
```

- `source_char`: input string.
- `pattern`: pattern to search for.
- `replace_string`: replacement string; may contain backreferences.
- `position`: starting search position, defaults to 1.
- `occurrence`: which match to replace; **0 means replace all occurrences**, and 0 is the default.
- `match_param`: matching flags such as `i`, `c`, `n`, `m`, `x`.

If no match is found, the function returns the source string unchanged; it does not erase the entire source.

### 6.2. Collapsing multiple whitespace characters

```sql
SELECT REGEXP_REPLACE(
         'Oracle     Database   SQL',
         '[[:space:]]+',
         ' '
       ) AS normalized_text
FROM dual;
```

Result:

```text
Oracle Database SQL
```

To also strip leading and trailing spaces, combine with `TRIM`:

```sql
SELECT TRIM(
         REGEXP_REPLACE(
           '   Oracle     Database   SQL   ',
           '[[:space:]]+',
           ' '
         )
       ) AS normalized_text
FROM dual;
```

`TRIM` strips spaces from both ends after regex collapses consecutive whitespace sequences into a single space.

### 6.3. Removing non-digit characters

Example normalizing a phone number to digits only:

```sql
SELECT REGEXP_REPLACE(
         '+84 (912) 345-678',
         '[^[:digit:]]',
         ''
       ) AS digits_only
FROM dual;
```

The illustrative result is `84912345678`.

This is only **character normalization**; it does not prove the phone number is valid, has a valid country code, or is active. Phone validation requires separate country- and domain-specific rules.

### 6.4. Replacing only the nth occurrence

With `occurrence` equal to 0, Oracle replaces all matches:

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#'
       ) AS replace_all
FROM dual;
```

Result: `a# b# c#`.

To replace only the second occurrence:

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#',
         1,
         2
       ) AS replace_second
FROM dual;
```

Result: `a1 b# c3`. The other digits remain untouched.

### 6.5. Using capture groups to reorder components

Suppose names are stored as `Smith, John` and you want `John Smith`:

```sql
SELECT REGEXP_REPLACE(
         'Smith, John',
         '^([^,]+),[[:space:]]*(.+)$',
         '\2 \1'
       ) AS display_name
FROM dual;
```

The pattern contains:

- `([^,]+)`: group 1, everything before the comma.
- `,`: literal comma.
- `[[:space:]]*`: zero or more whitespace characters.
- `(.+)`: group 2, the remainder of the name.
- `'\2 \1'`: replace with group 2, a space, then group 1.

Result: `John Smith`.

Backreferences in Oracle replacement strings use `\1` through `\9` for the corresponding capture groups. Do not blindly use `$1` syntax from other regex engines.

### 6.6. Masking part of a string

Example masking the leading digits of a card number while keeping the last four digits:

```sql
SELECT REGEXP_REPLACE(
         '1234567890123456',
         '^([[:digit:]]{12})([[:digit:]]{4})$',
         '************\2'
       ) AS masked_value
FROM dual;
```

Result:

```text
************3456
```

This is purely a string-transformation illustration. Masking data in query output does not replace data protection policies, access controls, encryption, auditing, or secure storage of raw values.

### 6.7. Deleting all matched substrings

If `replace_string` is an empty string under Oracle semantics, matched segments are removed. Example:

```sql
SELECT REGEXP_REPLACE(
         'INV-2026-00125',
         '[^[:alnum:]-]',
         ''
       ) AS cleaned_code
FROM dual;
```

Here, an empty replacement strips characters that are neither alphanumeric nor hyphens. Oracle treats standard empty strings `''` as `NULL`, so keep Oracle's empty-string semantics in mind when designing expressions.

## 7. Capture groups and backreferences

### 7.1. What is a capture group?

A capture group is a subpattern enclosed in parentheses `(...)`. Oracle can use these groups to:

- Return a specific portion via the `subexpr` parameter of `REGEXP_SUBSTR`.
- Reference matched group text inside the replacement string of `REGEXP_REPLACE`.

Example pattern:

```text
^([[:alpha:]]{3})-([[:digit:]]{4})$
```

There are two groups:

| Group | Content |
| ---: | --- |
| 1 | First three letters |
| 2 | Last four digits |

### 7.2. Extracting and rearranging groups

```sql
SELECT
    REGEXP_SUBSTR('ABC-1234',
                  '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                  1, 1, 'c', 1) AS prefix,
    REGEXP_SUBSTR('ABC-1234',
                  '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                  1, 1, 'c', 2) AS sequence_no,
    REGEXP_REPLACE('ABC-1234',
                   '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                   '\2/\1') AS rearranged
FROM dual;
```

Result:

| PREFIX | SEQUENCE_NO | REARRANGED |
| --- | --- | --- |
| ABC | 1234 | 1234/ABC |

### 7.3. Group limits

`REGEXP_SUBSTR` accepts `subexpr` values from 0 to 9; 0 returns the full match, and positive integers select the corresponding capture group. When designing patterns with multiple groups, number and document them clearly. Replacement strings in `REGEXP_REPLACE` support backreferences within Oracle's limits, commonly `\1` through `\9`.

Avoid creating patterns with unnecessary capture groups. Nested groups make numbering harder to follow and increase maintenance cost.

## 8. Practical examples for data tasks

### 8.1. Validating employee code structure

Requirement: employee code starts with `EMP-`, followed by six digits:

```sql
SELECT employee_id, employee_code
FROM   employees
WHERE  REGEXP_LIKE(
         employee_code,
         '^EMP-[[:digit:]]{6}$'
       );
```

Regex validates string structure, but does not confirm the code exists in the HR system or belongs to an active employee.

### 8.2. Splitting order codes into type and number

Sample data: `SO-2026-000123`.

```sql
SELECT
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 1) AS order_type,
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 2) AS order_year,
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 3) AS order_sequence
FROM   sales_orders;
```

Keeping the sequence as a string preserves leading zeros. If arithmetic is needed, convert separately and only when the data is guaranteed valid.

### 8.3. Normalizing whitespace in names

```sql
SELECT customer_id,
       TRIM(
         REGEXP_REPLACE(
           customer_name,
           '[[:space:]]+',
           ' '
         )
       ) AS normalized_name
FROM   customers;
```

This is a read-only expression. If live table data must be updated, preview the output, back up data or use appropriate transaction controls before running `UPDATE`.

### 8.4. Detecting strings with disallowed characters

Suppose a code permits only letters, digits, and hyphens:

```sql
SELECT product_code
FROM   products
WHERE  REGEXP_LIKE(product_code, '[^[:alnum:]-]');
```

The negated bracket expression finds **at least one character outside the allowed set**. Use it to spot suspect data before normalizing.

To verify the entire string contains only allowed characters, use anchors and `+`:

```sql
WHERE REGEXP_LIKE(product_code, '^[[:alnum:]-]+$')
```

Decide explicitly whether empty strings are permitted. With `+`, at least one character must match; `*` has different semantics if empty values are allowed.

### 8.5. Finding log lines containing ERROR or FATAL

```sql
SELECT log_id, log_message
FROM   application_logs
WHERE  REGEXP_LIKE(
         log_message,
         '(^|[[:space:]])(ERROR|FATAL)(:|[[:space:]])',
         'i'
       );
```

This pattern looks for status words bounded by specific whitespace or delimiters. It improves on `'%ERROR%'` when you do not want to match longer words that happen to contain ERROR. Actual rules must match the application's log format.

### 8.6. Normalizing delimiters

Suppose input uses semicolons, commas, or extra spaces as separators:

```sql
SELECT REGEXP_REPLACE(
         'A12;   B34, C56',
         '[;,][[:space:]]*',
         ','
       ) AS normalized_list
FROM dual;
```

Output: `A12, B34, C56`. This example only normalizes strings; it is not a full CSV parser. Real CSV allows commas inside quoted fields, escaped quotes, and embedded newlines, requiring a dedicated CSV parser rather than simple regex.

## 9. Technical limits of Oracle regular expressions

### 9.1. 512-byte maximum pattern length

Oracle limits a **regular expression pattern to 512 bytes**. This is a byte limit, not necessarily 512 characters—especially for patterns containing multi-byte characters.

Consequences:

- Very long patterns may be rejected even when the visible character count seems modest.
- Dynamically generated patterns from configuration or user input must be size-bounded.
- An enormous regex usually signals that logic should be split, moved to a lookup table, or handled in a more appropriate layer.

Do not cram an entire business dictionary, code list, or hundreds of alternatives into one pattern. Use `IN` or reference tables for lists of values, and design proper data models for large rule sets.

### 9.2. Not full PCRE, Java Pattern, or JavaScript RegExp

Oracle implements regex according to POSIX standards and Unicode guidelines with select extensions. It is not identical to full PCRE or Java's regex engine.

Do not copy advanced features such as lookarounds, named capture groups, inline flags, or engine-specific syntax verbatim without verifying support in your target Oracle version. In Oracle, `match_param` is the standard way to toggle modes like `i`, `c`, `n`, `m`, and `x`.

If a pattern must be portable across engines, stick to the common subset, test on the exact Oracle Database release, and consult official documentation.

### 9.3. Capture group limits

`REGEXP_SUBSTR` limits `subexpr` to 0–9; backreferences in `REGEXP_REPLACE` are likewise constrained by Oracle's supported group limits. Do not design a regex with dozens of capture groups expecting arbitrary extraction or substitution.

To parse complex multi-field structures, consider:

- Multiple small, testable expressions.
- `JSON_VALUE`/`JSON_TABLE` if the source is JSON.
- `XMLTABLE` if the source is XML.
- A dedicated parser in the application layer if the data follows a complex grammar.

### 9.4. Regex does not replace format parsers

A regex can match `2026-02-31` against `YYYY-MM-DD`, yet that calendar date **does not exist** in the Gregorian calendar. Regex checks structural shape; converting to DATE/TIMESTAMP is required to validate real calendar dates.

Similarly:

- Email regex does not prove a mailbox exists.
- Phone regex does not prove a number is active.
- Raw regex on JSON does not replace a JSON parser.
- CSV regex does not properly handle quoted fields and embedded newlines.
- XML regex does not replace an XML parser.

Use the right tool for data semantics.

### 9.5. Character sets, Unicode, and collation

Expressions like `[[:alpha:]]`, `[[:digit:]]`, and case-insensitive matching must be understood in the context of Oracle's character set, collation, and Unicode rules. A pattern tested only on ASCII data may behave differently on accented Vietnamese text, combining characters, or supplementary characters.

For multilingual data:

- Confirm the Unicode normalization form of source data.
- Test uppercase/lowercase and Vietnamese diacritics.
- Do not treat the ASCII range `A-Z` as covering all letters.
- Consult the collation and regular expression documentation for your exact Oracle release.

## 10. NULLs and source data types

### 10.1. REGEXP_LIKE with NULL

If `source_char` is `NULL`, the regex condition does not evaluate to TRUE. In `WHERE`, rows with NULL sources are excluded:

```sql
SELECT customer_id, email
FROM   customers
WHERE  REGEXP_LIKE(email, '^[^@]+@[^@]+$');
```

To classify missing emails separately:

```sql
SELECT customer_id,
       CASE
         WHEN email IS NULL THEN 'MISSING'
         WHEN REGEXP_LIKE(email, '^[^@]+@[^@]+$') THEN 'SHAPE_OK'
         ELSE 'INVALID_SHAPE'
       END AS email_status
FROM customers;
```

`SHAPE_OK` only means the string matches a basic pattern, not that the email address is verified.

### 10.2. REGEXP_SUBSTR when no match is found

```sql
SELECT REGEXP_SUBSTR(
         'ABC-123',
         '[[:alpha:]]{4}'
       ) AS extracted_value
FROM dual;
```

The result is `NULL` because there is no run of four consecutive letters matching the pattern. Distinguish this case from a NULL source when compiling data quality metrics.

### 10.3. REGEXP_REPLACE and NULL

If the source is NULL, the result generally remains NULL per SQL semantics. Never use regex to replace NULL-handling mechanisms; write `CASE`, `NVL`, or `COALESCE` when business logic calls for defaults.

Oracle treats empty strings `''` in character types as `NULL` in SQL. Therefore, empty-string and NULL checks usually belong under the same data policy.

### 10.4. Using with CLOB and long strings

Regex functions work with Oracle-supported character types, including certain LOB types. However, return types, pattern limits, character-set conversions, and processing costs depend on the function signature of your database version. Do not assume the 512-byte pattern limit also limits the source string to 512 bytes; pattern size and source length are separate concerns.

On very large CLOBs, running regex over the entire content can consume significant CPU and I/O. If you only need a short segment, constrain the starting position/length, split processing, or use an appropriate text search engine.

## 11. Performance and responsible usage

### 11.1. Regex is usually more expensive than simple predicates

Compare:

```sql
WHERE status = 'ACTIVE'
```

against:

```sql
WHERE REGEXP_LIKE(status, '^ACTIVE$')
```

Both conditions express the same intent on simple data, yet regex adds pattern parsing and state-machine evaluation overhead. Use equality when the requirement is exact equality.

Similarly:

```sql
WHERE product_code LIKE 'ABC%'
```

is typically easier for the optimizer to optimize than the equivalent regex:

```sql
WHERE REGEXP_LIKE(product_code, '^ABC')
```

Never assume Oracle converts every regex into a B-tree range scan like `LIKE`.

### 11.2. Avoid overly broad patterns

Unanchored patterns or patterns starting with wildcards may have to evaluate multiple positions per string. For instance, `.*ERROR.*` can be written more simply as `REGEXP_LIKE(message, 'ERROR')`, since regex does not require matching the whole string by default.

Long patterns with nested branches, quantifiers, and heavy backtracking can drive up CPU cost. Tailor patterns to real data structures and benchmark with production-like row counts, string lengths, and concurrency.

### 11.3. Never run REGEXP_REPLACE across an entire table just to preview

A statement like:

```sql
UPDATE customer_data
SET    phone = REGEXP_REPLACE(phone, '[^[:digit:]]', '');
```

modifies data in bulk. Before running it:

1. Use `SELECT` to preview before and after values.
2. Count the affected rows.
3. Inspect NULLs, empty strings, Unicode values, and edge cases.
4. Confirm formatting policy with business owners.
5. Follow your environment's transaction, backup, and deployment procedures.
6. Verify the results after updating.

Preview example:

```sql
SELECT customer_id,
       phone AS original_phone,
       REGEXP_REPLACE(phone, '[^[:digit:]]', '') AS normalized_phone
FROM   customer_data
WHERE  phone IS NOT NULL;
```

Do not put an automatic `COMMIT` in transformation scripts without proper verification steps.

### 11.4. Inspect the execution plan and measure actual runtime

You can inspect the estimated plan:

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM   customers
WHERE  REGEXP_LIKE(email, '@example\.com$');

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` only shows an estimated plan. When investigating executed queries, review the cursor plan and runtime metrics, cross-checking statistics, actual row counts, CPU, and wait events.

There is no blanket rule that regex is always slow or can never use an index. Evaluate the specific SQL statement, data, indexes, optimizer, and Oracle version.

### 11.5. Consider alternatives

| Problem | Solution to Consider |
| --- | --- |
| Equality or inequality to a value | `=`, `<>` |
| Simple prefix match | `LIKE 'ABC%'` |
| Large set of allowed values | Lookup table, staging table, join |
| Parsing real CSV | Dedicated CSV parser |
| Reading JSON | `JSON_VALUE`, `JSON_TABLE` |
| Reading XML | `XMLTABLE` |
| Full-text search | Oracle Text or a dedicated search engine |
| Validating real calendar dates | `TO_DATE`/`TO_TIMESTAMP` with explicit format and error handling |
| Complex business rules | Business-layer validation paired with necessary constraints |

## 12. Security when patterns come from users

### 12.1. Bind variables prevent SQL injection but do not make patterns literal

Example:

```sql
SELECT customer_id, email
FROM   customers
WHERE  REGEXP_LIKE(email, :pattern);
```

Bind variables pass the pattern as data, mitigating the risk of SQL syntax injection. However, `:pattern` is still interpreted by Oracle as a **regex pattern**. A user can deliberately supply an overly broad or complex pattern, causing heavy resource usage or matching broader data than intended.

If a feature should only search for a literal substring, escape regex metacharacters before passing the string into the pattern. Binding and escaping solve two different problems.

### 12.2. Constrain dynamic patterns

If users are allowed to enter regex patterns:

- Limit pattern length.
- Restrict allowed syntax constructs.
- Prevent unauthorized users from querying restricted data sources.
- Enforce resource and timeout limits in the application and database per policy.
- Test patterns against long and multiline strings.
- Log/report invalid pattern syntax errors without leaking sensitive details.

Oracle's 512-byte limit is a technical ceiling, **not a safe default input limit**. Even a short pattern can become expensive depending on its structure and the input data.

### 12.3. Do not treat regex validation as a security boundary

For example, a column check:

```sql
CHECK (REGEXP_LIKE(account_code, '^[[:alnum:]-]+$'))
```

enforces character format on the column, but it does not replace access control, authentication, SQL injection protection, row-level authorization, or sensitive-data safeguards.

For critical data, combine input validation with constraints, database privileges, and business logic in the appropriate layers.

## 13. Common errors and troubleshooting

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Pattern does not match even though string looks valid | Missing/wrong anchor, bad escaping, case mismatch, hidden characters | Inspect raw data, pattern, `match_param` |
| `REGEXP_LIKE` returns too many rows | Missing anchors or overly broad quantifiers | Decide whether to match a substring or the whole string |
| `REGEXP_SUBSTR` returns NULL | No matching occurrence or NULL source | Check match count, `position`, `occurrence` |
| `REGEXP_SUBSTR` grabs too much text | Greedy `.*` over-matching | Restrict character class, anchors, or group structure |
| `REGEXP_REPLACE` replaces every match | `occurrence=0` or default | Pass a positive `occurrence` if targeting a single match |
| Extracted capture group is wrong | Miscounted `(...)` groups | Number `(...)` left to right, check `subexpr` |
| Dot `.` does not cross newlines | Missing `'n'` match parameter | Add `'n'` when intended |
| Anchors ignore individual lines | Multiline mode not enabled | Add `'m'` |
| Pattern too long error | Exceeded 512-byte limit | Shorten pattern or split logic |
| Regex runs slowly | Broad/complex pattern, large source, many rows | Check plan/runtime; consider LIKE, indexes, or another parser |
| Errors after copying regex from Java | Engine and escaping differences | Verify Oracle syntax, SQL literals, and outer string escaping |
| Vietnamese text matches unexpectedly | Character set, Unicode, collation, normalization | Test with real data and linguistic rules |

### 13.1. Test patterns incrementally

Instead of writing one huge regex up front, test piece by piece:

```sql
SELECT
    CASE WHEN REGEXP_LIKE('INV-2026-00125', '^INV-')
         THEN 'Y' ELSE 'N' END AS prefix_ok,
    CASE WHEN REGEXP_LIKE('INV-2026-00125', '[[:digit:]]{4}')
         THEN 'Y' ELSE 'N' END AS year_present,
    CASE WHEN REGEXP_LIKE('INV-2026-00125',
                          '^INV-[[:digit:]]{4}-[[:digit:]]+$')
         THEN 'Y' ELSE 'N' END AS full_pattern_ok
FROM dual;
```

This helps isolate exactly where a pattern fails. For multi-format data, maintain test cases covering valid values, invalid values, NULL, empty strings, Unicode characters, and boundary lengths.

### 13.2. Handling invalid patterns

Syntactically invalid patterns raise runtime regex errors. When patterns are built dynamically, validate inputs against policy before executing queries on large datasets.

Do not catch all errors and silently report "no match found" without logging the cause; a pattern syntax error is fundamentally different from a valid pattern finding zero matches.

## 14. Comprehensive practice exercises

The following examples use literals and dummy data without altering business tables.

### Exercise 1 — REGEXP_LIKE code validation

```sql
SELECT CASE
         WHEN REGEXP_LIKE('EMP-123456',
                          '^EMP-[[:digit:]]{6}$')
         THEN 'VALID SHAPE'
         ELSE 'INVALID SHAPE'
       END AS result
FROM dual;
```

**Expected:** `VALID SHAPE`.

Try changing the string to `EMP-12345X` and `XEMP-123456` to observe the effect of the digit class and anchors.

### Exercise 2 — Case-insensitive REGEXP_LIKE

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database',
                          '^ORACLE',
                          'i')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

**Expected:** `MATCH`.

### Exercise 3 — REGEXP_SUBSTR extracting the second token

```sql
SELECT REGEXP_SUBSTR(
         'alpha,beta,gamma',
         '[^,]+',
         1,
         2
       ) AS token
FROM dual;
```

**Expected:** `beta`.

### Exercise 4 — REGEXP_SUBSTR extracting a capture group

```sql
SELECT REGEXP_SUBSTR(
         'INV-2026-00125',
         '^(INV)-([[:digit:]]{4})-([[:digit:]]+)$',
         1, 1, 'c', 3
       ) AS sequence_no
FROM dual;
```

**Expected:** `00125`, preserved as a string.

### Exercise 5 — REGEXP_REPLACE collapsing whitespace

```sql
SELECT TRIM(
         REGEXP_REPLACE(
           '  Oracle     SQL   Regex  ',
           '[[:space:]]+',
           ' '
         )
       ) AS cleaned_text
FROM dual;
```

**Expected:** `Oracle SQL Regex`.

### Exercise 6 — REGEXP_REPLACE replacing only the second match

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#',
         1,
         2
       ) AS result
FROM dual;
```

**Expected:** `a1 b# c3`.

### Exercise 7 — Reordering with backreferences

```sql
SELECT REGEXP_REPLACE(
         'Nguyen, An',
         '^([^,]+),[[:space:]]*(.+)$',
         '\2 \1'
       ) AS full_name
FROM dual;
```

**Expected:** `An Nguyen`.

### Exercise 8 — Dot and newlines

```sql
SELECT
    CASE WHEN REGEXP_LIKE(
                    'line1' || CHR(10) || 'line2',
                    'line1.*line2'
                  )
         THEN 'MATCH' ELSE 'NO MATCH' END AS default_mode,
    CASE WHEN REGEXP_LIKE(
                    'line1' || CHR(10) || 'line2',
                    'line1.*line2',
                    'n'
                  )
         THEN 'MATCH' ELSE 'NO MATCH' END AS dot_matches_newline
FROM dual;
```

**Expected:** by default, `.` does not match across a newline; `'n'` mode allows it to match.

### Exercise 9 — Checking for disallowed characters

```sql
SELECT CASE
         WHEN REGEXP_LIKE('AB-1234', '^[[:alnum:]-]+$')
         THEN 'ONLY_ALLOWED_CHARS'
         ELSE 'HAS_OTHER_CHAR'
       END AS result
FROM dual;
```

**Expected:** `ONLY_ALLOWED_CHARS`.

### Exercise 10 — Testing the pattern length limit

Intentionally create a long pattern in a test environment and observe the 512-byte limit. Do not test this in production; the goal is to see that the limit is measured in bytes and multi-byte patterns hit the ceiling at fewer visible characters.

## 15. Pre-production checklist for regex

| Question | What to Verify |
| --- | --- |
| Is regex really needed? | For exact equality, prefixes, or simple ranges, use basic operators |
| Partial or full-string match? | Decide whether `^` and `$` are needed |
| Does case matter? | Specify `'i'` or `'c'` and check collation |
| Do strings contain newlines? | Check `'n'` and `'m'` |
| Do you need capture groups? | Number capture groups and verify `subexpr` |
| Replace one or all occurrences? | Pass `occurrence` explicitly in `REGEXP_REPLACE` |
| Can data contain NULLs? | Handle `NULL` and no-match outcomes separately |
| Unicode / Vietnamese text involved? | Test character set, normalization, and collation |
| Could the pattern exceed limits? | Stay well below 512 bytes |
| Is the pattern user-supplied? | Bind, restrict syntax/length, escape if literal search is intended |
| Can LIKE or a dedicated parser work? | Pick the right tool for the data format |
| Has performance been measured? | Inspect execution plans and runtime on representative data |

## 16. Self-check questions

1. Does `REGEXP_LIKE` return a string or act as a SQL condition?
2. Does pattern `'ABC'` require the whole string to equal ABC? What must you add to enforce a full-string match?
3. In Oracle regex, which symbol matches any single character? Which matches 0 or more characters?
4. Why are `LIKE 'A%'` and `REGEXP_LIKE(col, 'A%')` not equivalent?
5. How do the `'i'` and `'c'` flags differ?
6. When do you need `'n'` and when do you need `'m'`?
7. In `REGEXP_SUBSTR`, what does `occurrence=3` mean?
8. What does `subexpr=0` return? What does `subexpr=2` return?
9. In `REGEXP_REPLACE`, what does `occurrence=0` mean?
10. Are backreferences in Oracle replacements written `\1` or `$1`?
11. What is the common Oracle byte limit for a regex pattern?
12. Can a regex accept `2026-02-31` as structurally valid? Why is it insufficient to validate real dates?
13. Does a bind variable turn a user-supplied pattern into literal text?
14. When you only need to match prefix `ABC`, why is `LIKE 'ABC%'` usually preferable to regex?
15. Why should you avoid using simple regex to parse arbitrary CSV files or perform full email validation?

**Answer key:**

1. It is a SQL condition, commonly used in `WHERE`.
2. No; without anchors it matches substrings anywhere. Use `^ABC$`.
3. `.` matches one character; `.*` matches zero or more characters.
4. In LIKE, `%` is a wildcard; in regex, `%` is a literal percent sign.
5. `i` is case-insensitive; `c` is case-sensitive.
6. `n` lets `.` match newlines; `m` makes `^`/`$` match per-line boundaries.
7. Extracts the third matching occurrence.
8. `0` returns the entire match; `2` returns the second capture group.
9. Replaces all occurrences.
10. `\1` through `\9` in Oracle syntax.
11. 512 bytes.
12. It matches the numeric shape, yet that date does not exist in the calendar; real date parsing/validation is required.
13. No; binding prevents SQL syntax injection, but the pattern is still evaluated as regex. Escape metacharacters for literal searches.
14. LIKE is simpler, easier to read, and often has better opportunities to use index range scans.
15. CSV and emails follow grammars and business rules broader than simple patterns; dedicated parsers or validators are more appropriate.

## 17. Oracle reference documentation

- [Oracle Database SQL Language Reference — Regular Expression Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Regular-Expression-Support.html): POSIX foundation, Unicode support, and Oracle regex rules.
- [Oracle Database SQL Language Reference — REGEXP_LIKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_LIKE.html): condition syntax and match parameters.
- [Oracle Database SQL Language Reference — REGEXP_SUBSTR](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_SUBSTR.html): position, occurrence, and capture groups.
- [Oracle Database SQL Language Reference — REGEXP_REPLACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_REPLACE.html): pattern replacement and backreferences.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): Unicode, character sets, and linguistic rules.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): evaluating execution plans and SQL performance.

When using regular expressions in Oracle, clearly determine **whether your goal is validation, extraction, or replacement**; add anchors when validating full strings; select explicit match flags; manage capture groups carefully; and respect the 512-byte limit. Reserve regex for tasks that genuinely need pattern matching, and stick to basic SQL operators for simple filters so statements remain readable, optimizable, and maintainable.
