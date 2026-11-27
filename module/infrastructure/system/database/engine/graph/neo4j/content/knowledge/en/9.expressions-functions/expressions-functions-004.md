# String Functions, Regular Expressions, and Text Normalization in Cypher

In the **property graph** model, text data appears in many places: user names on nodes, product codes, document titles, classification labels, review text on relationships, and data imported from CSV. These fields frequently need to be concatenated, trimmed, converted to lowercase or uppercase, searched by keyword, validated for format, or Unicode-normalized before use.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The module focuses on using Neo4j to model connected data, query relationships and paths with Cypher, and integrate with the Java Driver and Spring Data Neo4j. Therefore, this lesson not only introduces syntax, but also shows how to process text accurately from a data perspective and choose queries that can be optimized with indexes.

## 1. Learning Objectives

After completing this lesson, you will be able to:

- Use common string functions such as `trim()`, `toLower()`, `toUpper()`, `substring()`, `left()`, `right()`, `replace()`, `split()`, `size()`, and `toString()`.
- Distinguish string concatenation, `null` handling, and `STARTS WITH`, `ENDS WITH`, and `CONTAINS` predicates.
- Write regular expressions with the `=~` operator using character classes, quantifiers, start/end anchors, and case-insensitive flags.
- Understand the difference between **Unicode normalization** and **lowercasing**, **Vietnamese accent stripping**, and **fuzzy search**.
- Use `normalize()` and `IS NORMALIZED` when supported by your Neo4j version.
- Design parameterized data-cleansing workflows, search indexes, and text processing from Java applications.
- Avoid common pitfalls when searching names, identifiers, and optional properties on nodes or relationships.

## 2. Sample Data for Practice

Examples starting with `RETURN` or `WITH` can run standalone. To run the `MATCH` examples, initialize the following dataset in a **practice database** and avoid running it on live production data.

~~~cypher
MERGE (book:StringDemoProduct {sku: 'STR-001'})
SET book.name = 'Cypher Book',
    book.category = 'Books',
    book.price = 320000,
    book.description = 'Learn graph querying with Cypher'

MERGE (course:StringDemoProduct {sku: 'STR-002'})
SET course.name = '  Neo4j Course  ',
    course.category = 'Courses',
    course.price = 850000,
    course.description = 'Introduction to NEO4J and the property graph model'

MERGE (coffee:StringDemoProduct {sku: 'STR-003'})
SET coffee.name = 'Cà phê dữ liệu',
    coffee.category = 'Beverages',
    coffee.price = 95000,
    coffee.description = 'Product for testing Vietnamese Unicode'

MERGE (guide:StringDemoProduct {sku: 'STR-004'})
SET guide.name = 'Java Guide',
    guide.category = 'Books',
    guide.price = 180000
REMOVE guide.description

MERGE (an:StringDemoCustomer {customerId: 'CUS-001'})
SET an.name = 'An', an.email = 'AN@example.com'

MERGE (binh:StringDemoCustomer {customerId: 'CUS-002'})
SET binh.name = 'Binh'
REMOVE binh.email

MERGE (an)-[review:STRING_DEMO_REVIEWED]->(book)
SET review.comment = '  Nội dung rất hữu ích!  ',
    review.rating = 5;
~~~

The graph contains four products, two customers, and one review relationship. The data is intentionally structured as follows:

| Property | Special Data | Purpose |
| --- | --- | --- |
| `course.name` | Has leading and trailing spaces | Test `trim()` |
| `course.description` | Contains uppercase `NEO4J` | Test case-insensitive search |
| `coffee.name` | Contains Vietnamese diacritics | Test Unicode handling |
| `guide.description` | Property does not exist | Test `null` handling |
| `an.email` | `AN@example.com` | Test email normalization and regex |
| `review.comment` | Surrounded by whitespace | Test string functions on relationships |

**Note:** all examples use the labels `StringDemoProduct`, `StringDemoCustomer`, and the relationship `STRING_DEMO_REVIEWED`, keeping them isolated from other graph exercises.

## 3. STRING Type, String Literals, and Concatenation

### 3.1. Strings in Cypher

`STRING` is the type representing text. You can write string literals with single or double quotes:

~~~cypher
RETURN
  'Neo4j' AS singleQuoted,
  "Cypher" AS doubleQuoted,
  '' AS emptyString;
~~~

The empty string `''` has length 0 but is **different from `null`**. `null` represents a missing or unknown value. When a property does not exist, accessing it generally evaluates to `null`.

To include quotes inside a string, use the appropriate escape syntax for Cypher literals:

~~~cypher
RETURN 'Neo4j is a \"graph\" database' AS description;
~~~

Above, the double quotes are part of the text content. When using special characters such as quotes or backslashes inside regex, distinguish the two syntax layers: the **Cypher string** and the **regex pattern** inside that string.

### 3.2. String Concatenation with ||

Cypher supports the `||` string concatenation operator; `+` can also concatenate strings, but `||` expresses intent more clearly:

~~~cypher
RETURN
  'Neo' || '4j' AS productName,
  'Code: ' || 'STR-001' AS skuLabel,
  'Price: ' || toString(320000) AS priceLabel;
~~~

The results are `Neo4j`, `Code: STR-001`, and `Price: 320000`, respectively. When concatenating a number with a string, explicitly convert the number using `toString()`.

To format output from the graph:

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  p.sku,
  trim(p.name) || ' (' || p.sku || ')' AS displayName
ORDER BY p.sku;
~~~

For `STR-002`, `displayName` becomes `Neo4j Course (STR-002)` because extra spaces have been trimmed.

### 3.3. Null in Functions and Concatenation

String expressions typically propagate `null`:

~~~cypher
RETURN
  toLower(null) AS a,
  trim(null) AS b,
  'Value: ' || null AS c,
  coalesce(null, 'Not provided') AS d;
~~~

The first three columns receive `null`; column `d` receives `Not provided`. To display a description even for products missing the `description` property:

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  p.sku,
  coalesce(p.description, 'No description') AS description
ORDER BY p.sku;
~~~

For `STR-004`, the description column shows `No description`. This is a **value in the query result**, and does not overwrite the missing property on the node.

## 4. Common String Processing Functions

### 4.1. Quick Reference Table

| Function | Meaning | Example | Result |
| --- | --- | --- | --- |
| `trim(s)` | Remove leading and trailing whitespace | `trim('  Neo4j  ')` | `'Neo4j'` |
| `ltrim(s)` | Remove leading whitespace | `ltrim('  Neo4j')` | `'Neo4j'` |
| `rtrim(s)` | Remove trailing whitespace | `rtrim('Neo4j  ')` | `'Neo4j'` |
| `toLower(s)` | Convert to lowercase | `toLower('Neo4j')` | `'neo4j'` |
| `toUpper(s)` | Convert to uppercase | `toUpper('Neo4j')` | `'NEO4J'` |
| `left(s, n)` | Extract first `n` characters | `left('Cypher', 3)` | `'Cyp'` |
| `right(s, n)` | Extract last `n` characters | `right('Cypher', 3)` | `'her'` |
| `substring(s, start, len)` | Slice from `start` (0-based) | `substring('Cypher', 1, 3)` | `'yph'` |
| `replace(s, old, new)` | Replace all `old` substrings with `new` | `replace('a-b-c', '-', '/')` | `'a/b/c'` |
| `split(s, separator)` | Split string into a list | `split('a,b', ',')` | `['a','b']` |
| `reverse(s)` | Reverse character order | `reverse('abc')` | `'cba'` |
| `size(s)` | String length in character units | `size('Cypher')` | `6` |
| `toString(x)` | Convert a compatible value to string | `toString(42)` | `'42'` |

Some functions accept optional arguments or extended syntax depending on the version. For example, `trim` can specify side and characters to strip. Within this lesson, the simple form is most common for cleaning whitespace.

### 4.2. trim, ltrim, rtrim

~~~cypher
RETURN
  trim('  Neo4j  ') AS bothSides,
  ltrim('  Neo4j  ') AS leftSide,
  rtrim('  Neo4j  ') AS rightSide;
~~~

Results:

- `bothSides = 'Neo4j'`;
- `leftSide = 'Neo4j  '`;
- `rightSide = '  Neo4j'`.

Example with a property:

~~~cypher
MATCH (p:StringDemoProduct {sku: 'STR-002'})
RETURN
  p.name AS rawName,
  trim(p.name) AS cleanedName,
  size(p.name) AS rawLength,
  size(trim(p.name)) AS cleanedLength;
~~~

The original name has extra spaces, so `cleanedLength` is four units smaller than `rawLength` (two spaces on each side). If the string is `null`, `trim(null)` remains `null`; if the string contains only whitespace, `trim(...)` returns an empty string.

### 4.3. toLower and toUpper

~~~cypher
RETURN
  toLower('Neo4j CYPHER') AS lowerName,
  toUpper('neo4j cypher') AS upperName;
~~~

Results: `neo4j cypher` and `NEO4J CYPHER`.

These two functions are useful for case-insensitive text comparisons:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS 'neo4j'
RETURN p.sku, p.name, p.description;
~~~

The result includes `STR-002`. However, applying a function to a property in a filter can alter index usability. The end of this lesson shows an alternative design for large datasets.

**Distinction:** changing letter case is not the same as stripping Vietnamese diacritics, converting accented letters to unaccented ASCII, or normalizing all Unicode equivalents.

### 4.4. left, right, and substring

~~~cypher
RETURN
  left('STR-001', 3) AS prefix,
  right('STR-001', 3) AS suffix,
  substring('STR-001', 4, 3) AS numericPart,
  substring('Cypher', 3) AS fromIndex3;
~~~

Results: `STR`, `001`, `001`, and `her`. The starting index for `substring` is **0-based**. The third argument specifies the number of characters to extract; omitting it returns the remainder of the string.

String-slicing functions are useful for identifiers with a well-defined format. Even so, with real data, check length first if business rules require a minimum character count:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku IS NOT NULL AND size(p.sku) >= 7
RETURN p.sku, substring(p.sku, 4, 3) AS sequenceCode;
~~~

Do not use fixed character positions to split data with unstable formats, such as user names or free-form addresses.

### 4.5. replace: Literal Substring Replacement

~~~cypher
RETURN
  replace('Neo 4j', ' ', '') AS withoutSpace,
  replace('db.graph.neo4j', '.', '-') AS dashed,
  replace('a-b-c', '-', '_') AS underscored;
~~~

Results: `Neo4j`, `db-graph-neo4j`, `a_b_c`. `replace()` replaces **literal substrings** and does not interpret the search argument as a regex. For example, `replace(s, '.', '')` only removes actual periods, not arbitrary characters.

If regex-based replacement is required, use a version-compatible approach (processing in Java/ETL or a dedicated regex function in versions that support one). Do not mistake `replace()` for a universal regex-replace function.

### 4.6. split: Splitting into a List

~~~cypher
RETURN
  split('Neo4j,Cypher,Graph', ',') AS topics,
  split('STR-001', '-') AS skuParts;
~~~

The results are `['Neo4j', 'Cypher', 'Graph']` and `['STR', '001']`, respectively.

You can combine `split` with `UNWIND` to turn each list element into a row:

~~~cypher
WITH 'graph,neo4j,cypher' AS rawTags
UNWIND split(rawTags, ',') AS tag
RETURN toUpper(trim(tag)) AS tag
ORDER BY tag;
~~~

The result is three rows: `CYPHER`, `GRAPH`, `NEO4J`. When splitting multi-delimiter data, define formatting rules beforehand; a comma inside quoted text can make simple splitting with `split` unsuitable for full CSV parsing.

### 4.7. size and Checking for Empty Data

~~~cypher
RETURN
  size('Neo4j') AS a,
  size('') AS b,
  size(trim('   ')) AS c,
  size(null) AS d;
~~~

Results: `a = 5`, `b = 0`, `c = 0`, `d = null`. Distinguish **string length** from **UTF-8 byte count**. In Unicode text, accented characters can take multiple bytes; different Unicode representations can also yield different character-unit counts before normalization.

To detect descriptions without meaningful content:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.description IS NULL
   OR trim(p.description) = ''
RETURN p.sku, p.name;
~~~

The result includes `STR-004` because `description` is missing. The second condition also catches whitespace-only descriptions if any appear later.

## 5. String Search Operators

### 5.1. STARTS WITH, ENDS WITH, CONTAINS

These three operators return a Boolean expression (`true`, `false`, or `null`) and are commonly used in `WHERE`:

| Operator | Meaning | Example |
| --- | --- | --- |
| `STARTS WITH` | Begins with | `p.sku STARTS WITH 'STR-'` |
| `ENDS WITH` | Ends with | `p.name ENDS WITH 'Guide'` |
| `CONTAINS` | Contains substring | `p.name CONTAINS 'Cypher'` |

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku STARTS WITH 'STR-'
  AND trim(p.name) ENDS WITH 'Guide'
RETURN p.sku, p.name;
~~~

The result is `STR-004`.

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.description CONTAINS 'property graph'
RETURN p.sku, p.description;
~~~

The result is `STR-002`. For a non-existent property, the match generally evaluates to `null`; that row does not pass `WHERE`.

### 5.2. String Operators Are Case-Sensitive

~~~cypher
RETURN
  'Neo4j' CONTAINS 'neo' AS a,
  'Neo4j' CONTAINS 'Neo' AS b,
  'Neo4j' STARTS WITH 'Neo' AS c;
~~~

Results: `a = false`, `b = true`, `c = true`. Therefore, to perform a case-insensitive string search, normalize both sides using the same rule:

~~~cypher
WITH 'neo4j' AS keyword
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS toLower(keyword)
RETURN p.sku, p.description;
~~~

The result is `STR-002`. Note that lowercasing both sides still does **not** make `'cafe'` match `'cà phê'`.

### 5.3. Parameters Do Not Use % Like SQL LIKE

When searching by a keyword received from the Java Driver:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.name CONTAINS $keyword
RETURN p.sku, p.name;
~~~

The `$keyword` parameter must be a string, such as `'Cypher'`. You do not need to wrap `%` or `*` around it as in SQL `LIKE` syntax; `CONTAINS` checks substrings automatically. If a user enters `%` or `*`, they are treated as literal characters in `CONTAINS`.

## 6. Regular Expressions (Regex) with the =~ Operator

### 6.1. What Is Regex and When Is It Needed?

A regex describes a **character pattern**, useful for validating string structure or matching multiple variants of a format. In Cypher, the `=~` operator matches a string against a regex pattern using **Java regular expressions** syntax:

~~~cypher
RETURN
  'STR-001' =~ 'STR-[0-9]{3}' AS validSku,
  'STR-12' =~ 'STR-[0-9]{3}' AS invalidSku,
  'Neo4j' =~ '(?i)neo4j' AS caseInsensitiveMatch;
~~~

Results: `true`, `false`, `true`.

With `=~`, the pattern is matched against the **entire string**. If you only want to detect a substring inside a string, add `.*` on both sides or use `CONTAINS` when regex power is unnecessary.

### 6.2. Key Regex Elements to Remember

| Element | Meaning | Example |
| --- | --- | --- |
| `.` | Any single character (except line terminators by default) | `a.b` |
| `*` | Repeat 0 or more times | `ab*` |
| `+` | Repeat 1 or more times | `ab+` |
| `?` | Preceding element is optional | `colou?r` |
| `{n}` | Repeat exactly `n` times | `[0-9]{3}` |
| `[0-9]` | A digit from 0 to 9 | `[0-9]+` |
| `[A-Z]` | An uppercase Latin letter from A to Z | `[A-Z]+` |
| `(a\|b)` | Match either pattern | `(Neo4j\|Cypher)` |
| `^` | Start-of-string anchor | `^STR-` |
| `$` | End-of-string anchor | `[0-9]$` |
| `(?i)` | Case-insensitive matching flag | `(?i)neo4j` |

The `^` and `$` anchors remain useful when writing patterns so readers clearly see start/end boundaries, even though `=~` inherently requires matching the whole string.

Example validating product codes that have the prefix `STR-` followed by exactly three digits:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku =~ 'STR-[0-9]{3}'
RETURN p.sku, trim(p.name) AS name
ORDER BY p.sku;
~~~

All four sample products satisfy this. A product with code `STR-12X` or `STR-1234` would not match.

### 6.3. Checking Prefixes and Suffixes with Regex

~~~cypher
RETURN
  'STR-001' =~ '^STR-.*' AS startsWithStr,
  'STR-001' =~ '.*[0-9]$' AS endsInDigit,
  'Neo4j Course' =~ '(?i).*neo4j.*' AS containsNeo4j;
~~~

All three return `true`. However, when only checking fixed prefixes, suffixes, or substrings, `STARTS WITH`, `ENDS WITH`, and `CONTAINS` are usually easier to read and can leverage appropriate indexes.

### 6.4. Regex Flags: (?i), (?m), (?s)

Java regex supports flags such as:

- `(?i)`: case-insensitive matching.
- `(?m)`: multiline mode, changing the meaning of `^` and `$` anchors in strings with newlines.
- `(?s)`: dotall mode, allowing `.` to match newline characters.

~~~cypher
RETURN
  'neo4j' =~ '(?i)NEO4J' AS ignoreCase,
  'Neo4j' =~ '(?i)neo4j' AS ignoreCaseAgain;
~~~

Both return `true`. For multilingual text, keep in mind the distinction between case-insensitive matching and Unicode matching rules. Do not assume a regex flag will also strip diacritics, transliterate, or handle every Vietnamese spelling variant.

### 6.5. Two Layers of Escaping in Regex

In regex, the dot `.` is a wildcard, not a literal period. To match domain names ending in `.com`, the dot must be escaped in regex syntax. Because the pattern is written inside a **Cypher string literal**, the `\` character also needs escaping:

~~~cypher
RETURN
  'an@example.com' =~ '.*\\.com' AS correctDomain,
  'an@exampleXcom' =~ '.*.com' AS overlyBroadPattern;
~~~

Both expressions may return `true`: the second matches the `X` character because the dot is unescaped in regex. Inside a Cypher string, `'\\.'` passes `\.` to the regex engine.

A clearer way to avoid confusion when checking literal suffixes is:

~~~cypher
RETURN
  'an@example.com' ENDS WITH '.com' AS expected,
  'an@exampleXcom' ENDS WITH '.com' AS rejected;
~~~

Results: `expected = true` and `rejected = false`.

When using escapes like `\d`, `\s`, `\b`, or `\p{L}`, account for both Cypher string escaping and regex escaping. In simple examples, `[0-9]` avoids double-escaping complexity.

### 6.6. Regex on Relationship Data

Text can reside on relationships, not just on nodes:

~~~cypher
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
WHERE trim(r.comment) =~ '(?i).*hữu ích.*'
RETURN
  c.name AS reviewer,
  trim(p.name) AS product,
  trim(r.comment) AS comment;
~~~

The result includes An's review for `Cypher Book`. Cypher reads the `comment` property from relationship `r`, then applies `trim` and regex before returning.

### 6.7. Regex Is Not a Complete Data Validator

A simple regex like:

~~~cypher
RETURN
  'an@example.com' =~ '[^@ ]+@[^@ ]+\\.[^@ ]+' AS emailLike;
~~~

can identify **some** email-like strings, but does not guarantee that the email address exists, conforms to all RFC rules, or can receive mail. Similarly, regex format validation does not guarantee uniqueness; uniqueness should be enforced with an appropriate constraint when the data model requires it.

For user-entered text, do not arbitrarily concatenate input into Cypher expressions. Use **parameters** to separate data from the query:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku =~ $skuPattern
RETURN p.sku, p.name;
~~~

With `$skuPattern = 'STR-[0-9]{3}'`, the query behaves like the earlier example. However, **user-supplied regex patterns still carry risks regarding pattern semantics and execution cost**. Control regex length/complexity or restrict allowed patterns; if you only need substring matching, prefer `CONTAINS $keyword`.

## 7. Text Normalization: Easily Confused Concepts

### 7.1. Why Can Visually Identical Text Differ?

Unicode can represent an accented character in equivalent ways. For example, the character `é` can appear as:

- A single precomposed code point: `U+00E9`.
- The letter `e` (`U+0065`) plus a combining acute accent (`U+0301`).

Both **render identically**, yet the underlying sequences of code points differ. This affects comparisons of names, keywords, and matching keys when data originates from multiple systems.

### 7.2. Unicode Normalization Forms

| Form | Primary Meaning | When Used |
| --- | --- | --- |
| **NFC** | Canonical equivalence, preferring composed form | Standard text storage and comparison |
| **NFD** | Canonical decomposition into base and combining characters | Analyzing combining marks or text preprocessing |
| **NFKC** | Compatibility decomposition followed by canonical composition | Merging certain compatibility characters with different appearances |
| **NFKD** | Compatibility decomposition | Specialized preprocessing per application policy |

NFC and NFD preserve **canonical equivalence**. NFKC and NFKD also apply **compatibility equivalence**, which may discard formatting or semantic distinctions an application wants to retain. Therefore, do not default to NFKC/NFKD for fields such as proper names or legal text.

### 7.3. normalize() and IS NORMALIZED

Neo4j versions supporting this feature (the `normalize()` function and `IS NORMALIZED` operator were added in **Neo4j 5.17**) allow Unicode normalization directly in Cypher:

~~~cypher
RETURN
  '\u0065\u0301' = '\u00E9' AS equalBefore,
  normalize('\u0065\u0301', NFC) = '\u00E9' AS equalAfter,
  '\u0065\u0301' IS NORMALIZED AS normalizedBefore,
  normalize('\u0065\u0301') IS NORMALIZED AS normalizedAfter;
~~~

In a supported environment, the results are:

| Column | Result |
| --- | --- |
| `equalBefore` | `false` |
| `equalAfter` | `true` |
| `normalizedBefore` | `false` |
| `normalizedAfter` | `true` |

The two literals `'\u0065\u0301'` and `'\u00E9'` are the decomposed and precomposed representations of `é`, respectively. `normalize(input)` defaults to **NFC**; you can write `normalize(input, NFC)` explicitly. The argument `NFC`, `NFD`, `NFKC`, or `NFKD` is a **normalization keyword**, not an ordinary string value.

You can check a specific normalization form:

~~~cypher
RETURN
  '\u00E9' IS NFC NORMALIZED AS isNfc,
  '\u00E9' IS NFD NORMALIZED AS isNfd,
  normalize('\u00E9', NFD) IS NFD NORMALIZED AS afterNfd;
~~~

Results: `true`, `false`, `true`. If deploying on Neo4j older than 5.17, normalize text at the data ingestion or application layer before sending queries.

### 7.4. NFC Does Not Strip Vietnamese Diacritics

~~~cypher
RETURN
  normalize('Cà phê', NFC) AS preservedAccent,
  normalize('Cà phê', NFC) = 'Ca phe' AS sameAsUnaccented;
~~~

`preservedAccent` remains `Cà phê`; `sameAsUnaccented` is `false`. Unicode normalization preserves diacritics via canonical equivalence rather than converting Vietnamese text to unaccented ASCII.

If an application needs `'Ca phe'` to match `'Cà phê'`, design a separate **accent-insensitive search pipeline**, for example in Java/ETL: normalize to NFD, strip combining marks, apply a specific rule for `đ/Đ`, and lowercase. That is a business choice and should not destructively alter original display data.

### 7.5. Three Common Normalization Layers

A keyword processing pipeline often consists of:

1. **Surface cleanup:** strip leading/trailing whitespace with `trim()`.
2. **Case folding:** `toLower()` per lookup policy.
3. **Unicode normalization:** `normalize(..., NFC)`.

~~~cypher
WITH '  NEO4J  ' AS rawKeyword
RETURN
  rawKeyword,
  trim(rawKeyword) AS trimmed,
  toLower(trim(rawKeyword)) AS lowercase,
  normalize(toLower(trim(rawKeyword)), NFC) AS normalized;
~~~

The final result is `'neo4j'`. This pipeline is useful for **case-insensitive matching across canonical Unicode encodings**, though it does not strip diacritics, collapse multiple internal spaces, or fix typos.

### 7.6. Do Not Apply Lossy Transformations to Source Data Unnecessarily

For personal names, place names, and Vietnamese content, preserving the original form is critical. For example, `'Lê'` and `'Le'` can be completely different names. An accent-stripped search field should only be used to **suggest candidate matches**, not as a unique key for entity resolution or merging.

In a property graph integrating multiple sources, you can store separate properties:

| Property | Content | Usage |
| --- | --- | --- |
| `p.name` | Original accented name for accurate display | UI, reports, manual review |
| `p.searchName` | Name normalized according to policy | Searching, filtering |
| `p.sku` | Business identifier | Exact matching and constraints if needed |

Do not replace `p.name` with an unaccented string merely to make `CONTAINS` queries easier to write.

## 8. Graph Search Normalization Workflow

### 8.1. Creating a Dedicated Search Property

Suppose the system adopts a policy: strip leading/trailing whitespace, lowercase, and apply NFC normalization. In a practice database running Neo4j 5.17+, you can run:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.name IS NOT NULL
SET p.searchName = normalize(toLower(trim(p.name)), NFC)
RETURN p.sku, p.name, p.searchName
ORDER BY p.sku;
~~~

For example, `STR-002.searchName` becomes `'neo4j course'`. `STR-003.searchName` becomes `'cà phê dữ liệu'`: Vietnamese diacritics are preserved.

**Practice warning:** this `SET` statement **adds a new property**. Whenever source data changes, the application must also update `searchName` using the same rule; otherwise, the search field becomes stale.

### 8.2. Searching Using a Keyword Normalized with the Same Policy

~~~cypher
WITH normalize(toLower(trim($keyword)), NFC) AS keyword
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS keyword
RETURN p.sku, p.name, p.searchName
ORDER BY p.sku;
~~~

With `$keyword = '  NEO4J '`, the result is `STR-002`. The query only normalizes the parameter keyword, while the property was normalized **ahead of time**. This is a solid pattern when many queries share the same matching policy.

Note: if `$keyword` is `null`, string functions return `null` and `WHERE` retains no rows. The application should decide explicitly whether an empty keyword means “return all”, “return none”, or “invalid request”.

### 8.3. Normalizing Spaces Between Words

`trim()` only handles leading and trailing spaces. In `'Neo4j    Cypher'`, the spaces between words remain:

~~~cypher
RETURN
  trim('  Neo4j    Cypher  ') AS trimmed,
  replace('Neo4j    Cypher', '    ', ' ') AS simpleReplacement;
~~~

`replace` above only replaces **exactly four** consecutive spaces; it does not handle arbitrary runs of whitespace. If you need to collapse any whitespace run into a single space, handle it in ETL/Java or use a regex replacement function if supported by your Neo4j version.

For systems supporting free-text search, test normalization against Vietnamese text containing spaces, punctuation, newlines, and `null` cases.

## 9. Indexed Search and Choosing Query Types

### 9.1. Why Expression Structure Affects Index Usage

Compare:

~~~cypher
// Function executed directly on the property inside WHERE.
MATCH (p:StringDemoProduct)
WHERE toLower(p.name) CONTAINS 'neo4j'
RETURN p.sku, p.name;
~~~

with:

~~~cypher
// Filtering directly on a pre-normalized property.
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS 'neo4j'
RETURN p.sku, p.name;
~~~

When data is properly prepared, both can return identical results. However, the second applies the predicate directly to `searchName`, giving the optimizer an opportunity to use a suitable index if present. Wrapping `p.name` in a function does not automatically give Neo4j an index over that computed expression.

### 9.2. Range Index, Text Index, and Full-Text Index

| Requirement | Typical Best Fit | Key Consideration |
| --- | --- | --- |
| Exact code lookup `sku = $sku` | Range index or uniqueness constraint on code | Prefer a stable identifier key |
| Prefix name search | `STARTS WITH` condition and suitable index | Inspect actual execution plan |
| Substring / suffix search | Text index supporting `CONTAINS`, `ENDS WITH` | Index usage depends on query plan |
| Keyword search on documents with relevance scoring | Full-text index | Tokenization/analyzer differs from literal string matching |
| Complex regex filtering | `=~` | Can be expensive; do not assume index usage |

Example creating a text index in a practice database:

~~~cypher
CREATE TEXT INDEX string_demo_search_name IF NOT EXISTS
FOR (p:StringDemoProduct) ON (p.searchName);
~~~

After creating the index, inspect the plan with `EXPLAIN` or `PROFILE` on a representative dataset:

~~~cypher
EXPLAIN
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS $keyword
RETURN p.sku, p.name;
~~~

In the plan, index access operators may appear as `NodeIndexContainsScan`. The optimizer decides whether to use an index based on index type, statistics, data size, and query shape. On a four-node dataset, a node scan may be entirely reasonable.

Do not assume a text index equals a full-text index: a text index serves specific string predicates, whereas a full-text index is built for term search with dedicated analyzers, tokenization, and relevance scoring.

### 9.3. An Approach to Accelerating Accent-Insensitive Search

If typing `'ca phe'` must return `'Cà phê dữ liệu'`, compute `searchNameAscii` at the ingestion or Java application layer using a chosen accent-stripping rule. Then query:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.searchNameAscii CONTAINS $normalizedKeyword
RETURN p.sku, p.name;
~~~

**Prerequisite:** nodes must already have `searchNameAscii` populated, and `$normalizedKeyword` must be normalized with the **same** algorithm. The query will not return expected results if the search field has not been generated. The property name `searchNameAscii` is merely an implementation example, not a built-in auto-generated Neo4j feature.

## 10. Combining Text Across Nodes and Relationships

### 10.1. Formatting Graph Query Output

~~~cypher
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
RETURN
  c.name AS customer,
  trim(p.name) AS product,
  toUpper(p.category) AS category,
  trim(r.comment) AS cleanedComment,
  c.name || ' reviewed ' || trim(p.name) AS summary;
~~~

With the sample data, `summary` is `An reviewed Cypher Book`. The concatenation combines properties from **two nodes**, while `trim()` operates on a **relationship** property.

### 10.2. Finding Relationships Whose Comments Contain a Keyword

~~~cypher
WITH 'HỮU ÍCH' AS rawTerm
WITH toLower(trim(rawTerm)) AS term
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
WHERE toLower(r.comment) CONTAINS term
RETURN c.name, p.name, trim(r.comment) AS comment;
~~~

The result includes An's review. In this example, `toLower()` handles case-insensitive comparison, while the diacritics in `'hữu ích'` are preserved.

### 10.3. OPTIONAL MATCH and Potentially Missing Text

~~~cypher
MATCH (c:StringDemoCustomer)
OPTIONAL MATCH (c)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
RETURN
  c.name AS customer,
  coalesce(trim(r.comment), 'No review yet') AS commentLabel,
  coalesce(trim(p.name), 'No product yet') AS productLabel
ORDER BY c.name;
~~~

An has a review, while Binh receives the fallback values. `OPTIONAL MATCH` keeps Binh even without a `STRING_DEMO_REVIEWED` relationship. If you used a mandatory `MATCH` on that relationship, Binh would disappear from the results.

## 11. Integrating Text Processing with the Java Driver and Spring Data Neo4j

### 11.1. Parameterized Queries from the Java Driver

In a Java application, use parameters for keywords, product SKU patterns, and name values. The example below illustrates usage with a preconfigured `Driver driver`:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;
import java.util.List;

String keyword = "neo4j";

try (Session session = driver.session()) {
    List<String> names = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:StringDemoProduct)
            WHERE toLower(trim(p.name)) CONTAINS toLower($keyword)
            RETURN trim(p.name) AS name
            ORDER BY name
            """,
            Values.parameters("keyword", keyword)
        ).list(row -> row.get("name").asString())
    );

    names.forEach(System.out::println);
}
~~~

The output prints `Neo4j Course`. This example intentionally uses only `toLower()` and `trim()` for broad compatibility across Neo4j environments. On large systems with a pre-normalized search property, replace the predicate with `p.searchName CONTAINS $keyword` and ensure `keyword` is normalized beforehand.

When using Spring Data Neo4j with `@Query`, the same principles apply: pass values via parameters, assign clear aliases to outputs, and map `null` to nullable DTO/projection fields.

### 11.2. Unicode Normalization and Accent-Insensitive Search in Java

Java provides `java.text.Normalizer` for Unicode normalization forms. Example of an **accent-insensitive** search normalizer under a specific policy:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchText {
    private SearchText() {}

    public static String withoutVietnameseAccents(String input) {
        if (input == null) {
            return null;
        }

        String decomposed = Normalizer.normalize(
            input.strip().toLowerCase(Locale.ROOT),
            Normalizer.Form.NFD
        );

        return decomposed
            .replaceAll("\\p{M}+", "")  // Remove combining diacritical marks.
            .replace('đ', 'd')            // NFD does not automatically convert đ.
            .replaceAll("\\s+", " ");   // Collapse whitespace.
    }
}
~~~

~~~java
System.out.println(
    SearchText.withoutVietnameseAccents("  Cà  phê dữ liệu ")
);
// ca phe du lieu
~~~

This function **intentionally discards diacritic information**, so it should only be used for **search fields**. Never overwrite original display names with its output. In production, add tests covering Unicode edge cases, punctuation, special characters, proper names, and multilingual inputs.

### 11.3. Normalizing Input Data Before Writing to the Graph

A typical ingestion pipeline:

~~~mermaid
flowchart LR
    A[Input data: CSV or API] --> B[Check null and length]
    B --> C[Trim and normalize Unicode]
    C --> D[Create search field by policy]
    D --> E[MERGE node by stable key]
    E --> F[Store original name and searchName]
    F --> G[Query with parameters and index]
~~~

The key point is to **MERGE by an identifier key** (such as SKU), not by an accent-stripped name if the algorithm could collapse two genuinely different names into the same string. In a graph model, erroneously merging nodes also affects every relationship attached to those nodes.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `CONTAINS` is case-insensitive | Fails to find `NEO4J` when searching `neo4j` | Standardize on `toLower()` or a normalized search field |
| Assuming `normalize()` strips Vietnamese diacritics | `Cà phê` still differs from `Ca phe` | Implement a dedicated accent-stripping step if needed |
| Using `replace(s, '.*', '')` like regex replace | Does not replace arbitrary characters | `replace()` performs literal substring replacement |
| Using `=~ 'neo4j'` to find a word inside a string | Fails to match `Neo4j Course` | Write `'(?i).*neo4j.*'` or use `CONTAINS` |
| Forgetting to escape dots in regex | `.` matches non-dot characters too | Escape at both the regex and Cypher string layers |
| Passing raw user input into complex regex constructs | Hard-to-control patterns and high CPU cost | Limit regex usage, parameterize, and restrict patterns |
| Using `trim()` to remove all spaces inside a string | Internal spaces remain | Add a whitespace-collapsing step |
| Treating `size()` as UTF-8 byte count | Miscalculates byte limits of external systems | Distinguish Unicode characters from bytes |
| Ignoring `null` before string concatenation | Formatted result evaluates to `null` | Use `coalesce` according to business rules |
| Overwriting original names with unaccented text | Loses accurate display and risks collisions | Store a separate search property |
| Assuming regex always uses a text index | Query may scan many records | Check `EXPLAIN` / `PROFILE` and choose suitable operators |
| Normalizing stored data without normalizing search input | Same names still fail to match | Apply the same algorithm on both sides |
| Using normalized names as unique keys | May merge two distinct entities | Use a business identifier and appropriate constraint |

## 13. Practice Exercises with Solutions

### Exercise 1. Clean Input Text

Given the string `'   NEO4J Cypher   '`, strip leading/trailing whitespace and convert it to lowercase.

~~~cypher
WITH '   NEO4J Cypher   ' AS rawText
RETURN toLower(trim(rawText)) AS cleaned;
~~~

**Solution:** `cleaned = 'neo4j cypher'`.

### Exercise 2. Split an SKU into Two Parts

Given `STR-001`, produce two columns `prefix` and `sequence`.

~~~cypher
WITH 'STR-001' AS sku
RETURN
  split(sku, '-')[0] AS prefix,
  split(sku, '-')[1] AS sequence;
~~~

**Solution:** `prefix = 'STR'`, `sequence = '001'`. This assumes SKUs always follow `prefix-sequence`; for real-world data with varied formats, validate before indexing into the list.

### Exercise 3. Validate Code Format with Regex

Codes must begin with `STR-` followed by exactly three digits. Filter valid codes:

~~~cypher
UNWIND ['STR-001', 'STR-09', 'STR-ABC', 'STR-100'] AS sku
WITH sku
WHERE sku =~ 'STR-[0-9]{3}'
RETURN sku
ORDER BY sku;
~~~

**Solution:** `STR-001` and `STR-100`.

### Exercise 4. Compare Unicode Before and After Normalization

Check whether two representations of `é` become equal after normalization:

~~~cypher
RETURN
  '\u0065\u0301' = '\u00E9' AS rawEqual,
  normalize('\u0065\u0301', NFC) =
    normalize('\u00E9', NFC) AS normalizedEqual;
~~~

**Solution on Neo4j 5.17+:** `rawEqual = false` and `normalizedEqual = true`. The result reflects canonical Unicode equivalence; it does not mean two differently accented proper names represent the same entity.

### Exercise 5. Find Names by Prefix After Trimming

Requirement: find products whose name starts with `Neo4j`, even if the stored data has extra whitespace:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE trim(p.name) STARTS WITH 'Neo4j'
RETURN p.sku, trim(p.name) AS name;
~~~

**Solution:** `STR-002`. On large datasets, store pre-cleaned names to avoid calling `trim(p.name)` in search predicates on every query.

### Exercise 6. Case-Insensitive Description Search

~~~cypher
WITH '   neo4j  ' AS input
WITH toLower(trim(input)) AS keyword
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS keyword
RETURN p.sku, trim(p.name) AS name;
~~~

**Solution:** `STR-002`. Product `STR-004` has no description, so the check on `p.description` does not evaluate to `true`.

### Exercise 7. Count Products Missing a Meaningful Description

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  count(*) AS totalProducts,
  sum(
    CASE
      WHEN p.description IS NULL OR trim(p.description) = ''
      THEN 1
      ELSE 0
    END
  ) AS missingDescription;
~~~

**Solution:** `totalProducts = 4` and `missingDescription = 1`. Missing data is distinguished from non-empty descriptions.

### Exercise 8. Design an Accent-Insensitive Search

Requirement: allow users to type `ca phe` to find `Cà phê dữ liệu` in the graph. Describe a solution that keeps the original data safe.

**Suggested solution:** Keep `p.name = 'Cà phê dữ liệu'`. In the Java/ETL layer, generate `p.searchNameAscii = 'ca phe du lieu'` using an agreed-upon normalization rule. Normalize user keywords with the **same** rule, then run:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.searchNameAscii CONTAINS $keyword
RETURN p.sku, p.name;
~~~

With `$keyword = 'ca phe'`, the expected result is `STR-003`, **after** `searchNameAscii` has been populated for the product. Index search fields based on query needs; never overwrite original names with unaccented strings or merge nodes by normalized names.

## 14. Summary and Key Takeaways

- `trim()`, `toLower()`, `toUpper()`, `left()`, `right()`, `substring()`, `replace()`, `split()`, and `size()` clean and process text on both nodes and relationships.
- `STARTS WITH`, `ENDS WITH`, and `CONTAINS` handle prefix, suffix, and substring checks; by default, they are case-sensitive.
- `=~` uses Java-style regex and matches the entire string; manage flags, special characters, and escaping across both the Cypher string and regex layers.
- `normalize()` and `IS NORMALIZED` support Unicode normalization starting in Neo4j 5.17. **NFC does not strip Vietnamese diacritics** and does not replace fuzzy/accent-insensitive search.
- `null` differs from an empty string; use `IS NULL`, `coalesce()`, and clear business rules before concatenating or displaying text.
- For large datasets, consider storing a **dedicated search property**, choosing the right text/full-text index, and inspecting plans with `EXPLAIN` or `PROFILE`.
- With the Java Driver or Spring Data Neo4j, pass inputs as parameters, apply consistent normalization between stored data and search keywords, and keep original accented names for accurate display.

Proper text processing ensures Cypher queries locate connected data reliably, prevents erroneous entity merging during ingestion, and establishes a solid foundation for search features in Neo4j graph systems.

### Official References

- [Neo4j Cypher Manual – String functions](https://neo4j.com/docs/cypher-manual/current/functions/string/)
- [Neo4j Cypher Manual – String operators and regular expressions](https://neo4j.com/docs/cypher-manual/current/expressions/predicates/string-operators/)
- [Neo4j Cypher Manual – Search performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual – Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
