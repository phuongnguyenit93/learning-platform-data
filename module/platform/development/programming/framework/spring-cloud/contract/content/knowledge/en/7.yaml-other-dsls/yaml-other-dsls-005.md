# YAML Quoting, Escaping, and Data-Type Rules

## Learning Objectives

In **Spring Cloud Contract**, contracts between a **producer** (the party providing an API or emitting messages) and a **consumer** (the party calling the API or consuming messages) can be written in **YAML DSL** or **Groovy DSL**. Spring Cloud Contract uses contracts to generate producer-side tests and build stubs for the consumer to run with **Stub Runner**; CI can detect when the two sides become incompatible.

This lesson belongs to the **YAML and Other DSLs** chapter and focuses on an easily overlooked source of bugs: *YAML looks like plain text, but its parser turns it into concrete data types*. An improperly quoted string can turn into a number, boolean, or null. A backslash inside double quotes can cause a parse failure. These discrepancies directly affect requests, bodies, matchers, generated tests, and stubs.

After this lesson, you will be able to:

- Distinguish **plain scalars**, **single-quoted scalars**, and **double-quoted scalars**.
- Write special characters such as `:`, `#`, quotes, backslashes, newlines, and regular expressions accurately.
- Control **string, number, boolean, null, mapping, and sequence** types in contracts.
- Distinguish an **empty list**, **empty object**, **JSON null**, and **absent body**.
- Spot the difference between a **YAML error** and a **syntactically valid contract with wrong semantics**.
- Review YAML changes before generating tests, publishing stubs, and running CI.

## 1. Where Does YAML Fit in the Spring Cloud Contract Flow?

A YAML contract file typically looks like this:

~~~yaml
description: Return inventory by SKU
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 12
~~~

In this example:

| Element | YAML type | Meaning for the contract |
|---|---|---|
| `request`, `response`, `headers`, `body` | Mapping (key–value) | Groups properties of the request/response |
| `method`, `url`, `description` | String | Textual metadata of the contract |
| `status: 200` | Number | HTTP status 200 |
| `available: true` | Boolean | JSON boolean field `true` |
| `quantity: 12` | Number | Numeric JSON field |
| `sku: 'SKU-101'` | String | Identifier, must not be parsed as a number |

You can visualize the processing pipeline:

~~~mermaid
flowchart LR
    A["YAML contract file"] --> B["YAML parser<br/>determines structure and types"]
    B --> C["Spring Cloud Contract<br/>reads DSL"]
    C --> D["Generated producer tests"]
    C --> E["HTTP / message stubs"]
    E --> F["Stub Runner / consumer tests"]
~~~

A file that is syntactically valid YAML is **not necessarily** valid under Spring Cloud Contract's **DSL schema**. For instance, `response.statusCode` may be a valid YAML key, yet not the key expected by your version of the DSL. Conversely, a schema-valid field can still hold the wrong type, causing generated tests or stubs not to reflect the behavior the consumer relies on.

We therefore need to check **two layers**: YAML syntax and data types first, followed by contract semantics at the producer–consumer boundary.

## 2. Three Scalar Styles: Plain, Single-Quoted, Double-Quoted

A **scalar** is a single value in YAML, such as a string, number, boolean, or null. How you write it affects both parsing and type inference.

| Style | Example | Interpretation and purpose |
|---|---|---|
| **Plain scalar** (unquoted) | `method: GET` | Handy for simple strings, though certain words may be typed differently depending on parser/schema |
| **Single-quoted** | `sku: '00123'` | Forces string type; backslashes do not act as escapes |
| **Double-quoted** | `message: "Line 1\nLine 2"` | Forces string type and supports YAML-defined escape sequences |

Examples:

~~~yaml
# All three represent strings in standard cases.
namePlain: Java
nameSingle: 'Java'
nameDouble: "Java"

# Intentionally different types.
quantityNumber: 12
quantityString: '12'
enabledBoolean: true
enabledString: 'true'
~~~

### When should you quote?

Use quotes whenever a value **must remain a string** or contains confusing characters:

- SKU codes, phone numbers, postal codes, codes with leading zeros: `'00123'`.
- Word-like statuses such as `'on'`, `'off'`, `'yes'`, `'no'`: type inference varies across YAML parsers.
- Strings that look like numbers, dates, timestamps, or null but must stay literal: `'2026-11-24'`, `'1e3'`, `'null'`.
- URLs, messages, JSONPaths, and complex regexes: quote for readability and independence from plain-scalar rules.
- Strings containing `: ` (colon followed by space) or ` #` (space followed by hash): quote to avoid being parsed as a mapping or comment.

Error examples and fixes:

~~~yaml
# Invalid syntax or unintended meaning:
# message: Stock status: out of stock
# note: Please retry # after checking

# Clear:
message: 'Stock status: out of stock'
note: 'Please retry # after checking'
~~~

Not every `:` or `#` strictly requires quoting. For instance, `http://example.test` has `:` without an immediately following space; `SKU#123` has no space before `#`. Still, consistent quoting on values the consumer depends on reduces mistakes when editing files.

## 3. Single Quotes: The Safe Choice for Regexes and Backslashes

Inside a **single-quoted scalar**, the backslash `\` is **literal**. To represent a single quote inside the string, **double** the quote mark:

~~~yaml
message: 'Producer''s response is ready'
regex: '^[A-Z]{3}-\d{4}$'
windowsPath: 'C:\contracts\inventory.yml'
~~~

The parsed values are respectively:

- `Producer's response is ready`.
- Regex `^[A-Z]{3}-\d{4}$`, where `\d` stays intact for the regex engine to interpret.
- A Windows path with `\`, without producing newlines or tabs.

Do not use JavaScript or Java escaping inside YAML single quotes:

~~~yaml
# Wrong intent: \ stays literal and does not "escape" the single quote.
# message: 'Producer\'s response'
~~~

For regex patterns, single quotes are usually easiest to read because you do not juggle two escaping layers: YAML escaping and regex escaping.

## 4. Double Quotes: Escapes Work, But Must Follow YAML Rules

Inside a **double-quoted scalar**, YAML processes valid escapes such as:

| Written in YAML | Resulting value |
|---|---|
| `\n` | Newline character |
| `\t` | Tab character |
| `\"` | Double quote character |
| `\\` | Single backslash |
| `\u0041` | Unicode character `A` |

Valid examples:

~~~yaml
message: "Line 1\nLine 2"
quotedText: "Producer said: \"OK\""
path: "C:\\contracts\\inventory.yml"
regex: "^SKU-\\d{3}$"
~~~

Pay special attention to **regular expressions**:

~~~yaml
# Invalid: \d is not a valid YAML double-quote escape.
# regex: "^\d{3}$"

# Valid: YAML preserves a single backslash after parsing.
regexSingle: '^\d{3}$'
regexDouble: "^\\d{3}$"
~~~

Both valid expressions above yield the same regex string. However, if you use double quotes and forget to escape, the parser may raise a **YAML error** before Spring Cloud Contract even generates tests.

For JSONPaths in matchers, paths like `$.items[0].id` can typically be single-quoted to keep the text intact:

~~~yaml
jsonPathExample: '$.items[0].id'
regexExample: '^SKU-[0-9]{3}$'
~~~

The keys `jsonPathExample` and `regexExample` are standalone YAML string examples; they are **not** Spring Cloud Contract matcher keys. Inside a contract, place strings in the matcher fields supported by the DSL.

### Do not confuse multiple escaping layers

If a producer sends a JSON field containing backslashes, multiple layers may come into play:

1. **YAML source** describing the value.
2. **Value after the YAML parser**.
3. **JSON serialization** of the response body.
4. **Content the consumer actually receives and deserializes**.

Example:

~~~yaml
body:
  filePath: 'C:\data\stock.csv'
~~~

YAML provides a **string containing literal backslashes**. When serialized to JSON, backslashes in JSON text are escaped per JSON rules. What matters is that the consumer decodes the right path string; do not count `\` characters in raw generated JSON while ignoring the encoding layer.

## 5. Type Inference: String, Number, Boolean, Null

Unquoted values can be converted by the YAML parser into another type before the DSL sees them. Typical cases include:

| Intent | Recommended form | Reason |
|---|---|---|
| HTTP status 200 (number) | `status: 200` | Numeric type |
| Remaining quantity 0 (number) | `quantity: 0` | Numeric type, not string `"0"` |
| In-stock flag (boolean) | `available: false` | True boolean type |
| SKU code `00123` (string) | `sku: '00123'` | Preserves leading zeros and string type |
| Literal text `true` (string) | `literal: 'true'` | Prevents conversion to boolean |
| Status `on` (string) | `state: 'on'` | Avoids differences across YAML schemas/parsers |
| YAML null value | `value: null` or `value: ~` | Structural YAML null |
| Literal text `null` (string) | `value: 'null'` | Exact four characters `n-u-l-l` |
| Date treated as ID or text | `dateCode: '2026-11-24'` | Avoids timestamp/date auto-typing in some loaders |
| Scientific-looking string | `raw: '1e3'` | Keeps literal string |

**YAML 1.1 and YAML 1.2 differ in how they infer booleans and certain numbers.** Some libraries or loader versions still treat `yes`, `no`, `on`, `off` as booleans, while YAML 1.2 changed this interpretation. Spring Cloud Contract also depends on the parser bundled with your project's specific version. The safest, most predictable practice is:

- Booleans: use unquoted `true`/`false` when you genuinely want booleans.
- Text: quote `'yes'`, `'no'`, `'on'`, `'off'`, `'true'`, `'false'` when you want **strings**.
- Identifiers and numbers with leading zeros: always quote.
- Date/time values: quote if you want to preserve **strings**; do not rely on YAML auto-converting to a date type.

### Same characters, different type means a different contract

~~~yaml
# If the consumer expects available to be boolean:
body:
  sku: '00123'
  available: true
  quantity: 0
~~~

Differs from:

~~~yaml
# These are string "true" and string "0".
body:
  sku: '00123'
  available: 'true'
  quantity: '0'
~~~

A consumer deserializing into a Java record with `boolean available` and `int quantity` can behave very differently across these two cases depending on JSON deserializer settings. Contract tests must protect the committed type rather than just checking visually that `true` and `0` appear in the file.

## 6. Mappings and Sequences: Objects vs. Arrays

YAML uses:

- **Mappings** (key–value) to describe objects, e.g. `body:` with keys `sku`, `quantity`.
- **Sequences** (`-` markers) to describe arrays/lists, e.g. a list of items.
- **Scalars** to describe single values.

Example response body as an object:

~~~yaml
body:
  sku: 'SKU-101'
  available: true
  quantity: 12
~~~

Response body as a list of two objects:

~~~yaml
body:
  - sku: 'SKU-101'
    quantity: 12
  - sku: 'SKU-202'
    quantity: 0
~~~

Response body as an **empty array**:

~~~yaml
body: []
~~~

Response body as an **empty object**:

~~~yaml
body: {}
~~~

These four examples have **different shapes**. A consumer expecting a JSON array cannot automatically handle a JSON object; likewise, `[]` and `{}` are not interchangeable. When a list has zero items, if the API specifies `200 OK` with an empty JSON array, the contract must preserve `body: []`.

### Distinguishing YAML null, JSON null, and no response body

The following three constructs must not be treated as identical:

~~~yaml
# No body property declared in response.
response:
  status: 204
~~~

~~~yaml
# Body declared with YAML null value.
response:
  status: 200
  body: null
~~~

~~~yaml
# Body is a string containing the word "null".
response:
  status: 200
  body: 'null'
~~~

At the YAML level, `body: null` is a **null scalar**, `body: 'null'` is a **string**, and omitting `body` is a **missing key**. How Spring Cloud Contract handles each variant when generating HTTP responses/stubs depends on the DSL schema and body resolution; **do not swap them interchangeably to represent JSON null without checking the actual response**.

With HTTP `204 No Content`, a response in principle has no body. With HTTP `200` and JSON literal `null`, that is a different protocol representation and usually requires explicit configuration and verification on real stubs/producers.

## 7. Using YAML Block Scalars for Multi-Line Content

YAML offers two common block scalar styles:

- `|` (**literal**): preserves newlines inside the content.
- `>` (**folded**): folds single newlines into spaces, subject to YAML block-folding rules.

Examples:

~~~yaml
literalMessage: |
  Line 1
  Line 2

foldedMessage: >
  Line 1
  Line 2
~~~

Typically, `literalMessage` holds two lines, while `foldedMessage` equates to "Line 1 Line 2" (with trailing newline handling governed by block scalar rules). **Both are strings**, not mappings or sequences.

### Controlling trailing newlines with `-` and `+`

| Indicator | Typical meaning |
|---|---|
| `|` | Keeps a single trailing newline (clip) |
| `|-` | Strips trailing newlines (strip) |
| `|+` | Keeps all trailing newlines (keep) |
| `>`, `>-`, `>+` | Same trailing behavior, using folded style for content |

Example:

~~~yaml
withoutTrailingNewline: |-
  PRODUCT_NOT_FOUND

withTrailingNewline: |
  PRODUCT_NOT_FOUND
~~~

The two values **differ**: the second usually has an extra newline at the end. For contracts matching exact response bodies or messages, that extra character can cause tests to fail.

### When should you use block scalars in contracts?

For a JSON response, you should usually use **YAML mappings/sequences** so inner data types are represented explicitly:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
~~~

If you truly need to describe **multi-line plain text**, block scalars preserve the content cleanly:

~~~yaml
exampleTextBody: |-
  Validation failed:
  - SKU missing
  - Quantity invalid
~~~

`exampleTextBody` here is an independent YAML example, **not a Spring Cloud Contract key**. When putting a block scalar into `response.body`, remember the parser yields **a single string**, unlike a JSON mapping with typed fields. Pick based on your API's content type and body schema, then verify the actual output produced by generated tests and stubs.

## 8. Indentation, List Bullets, and Special Syntax

YAML relies on **indentation** to convey structure. Use **spaces**, never tabs, for indentation.

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    products:
      - id: 'P-101'
        price: 10
      - id: 'P-102'
        price: 20
~~~

The `-` starts a list item; keys belonging to the **same item** must align properly. Misaligning `price` can create the wrong structure or a parse error.

### Characters to watch at the start of plain scalars

Certain characters have special syntactic meaning when starting an unquoted value, such as `#` (comment), `*` (alias), `&` (anchor), `!` (tag), `[` and `{` (flow collection), `|`/`>` (block style), and `-` followed by whitespace. Quote them if they are **literal text**.

~~~yaml
# Intended as literal text, not comments, aliases, or collections.
code: '#NOT_FOUND'
patternText: '*inventory*'
literalArrayText: '[one, two]'
description: '- item is missing'
~~~

For URLs and query strings, quoting typically keeps files readable:

~~~yaml
request:
  method: GET
  url: '/api/products?category=books&page=0'
~~~

The example above is **URL text** for the request. `&page=0` inside quotes is not a YAML anchor, and `:` inside the string will not split into a mapping.

### Duplicate keys and comments

Avoid repeating keys inside the same mapping:

~~~yaml
# Avoid:
# response:
#   status: 200
#   status: 404
~~~

Some parsers reject duplicate keys; others keep the first or last value. Because behavior varies, never rely on it. Likewise, comments starting with `#` outside quoted values are not data sent to the consumer:

~~~yaml
response:
  status: 200 # internal note for YAML readers
~~~

Comments clarify configuration, but **do not appear in the response body**.

## 9. Complete Spring Cloud Contract YAML Example

Suppose the producer is **Inventory Service** and the consumer is **Checkout Service**. Checkout needs to call `GET /api/inventory/00123` and receive a string SKU (preserving leading zeros), boolean `available`, and numeric `quantity`.

The file may reside at `src/test/resources/contracts/inventory/stockAvailable.yml` in the producer (when the project configures Spring Cloud Contract to read contracts there):

~~~yaml
description: 'Return stock for SKU starting with zero'
request:
  method: GET
  url: '/api/inventory/00123'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: '00123'
    available: true
    quantity: 12
    tags:
      - 'featured'
      - 'same-day'
~~~

**Why quote this way?**

- `url` is an HTTP path string. Quote for clarity.
- `sku` is string `00123`, preserving leading zeros.
- `available` is boolean; writing `'true'` would turn it into a string.
- `quantity` is a number; writing `'12'` would turn it into a string.
- `tags` is a sequence of strings; the consumer receives a list/array structure.
- `headers` is a mapping; header names and string values are written explicitly.

Illustrative HTTP response per the contract:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "00123",
  "available": true,
  "quantity": 12,
  "tags": ["featured", "same-day"]
}
~~~

Depending on plugin configuration, Spring Cloud Contract creates **generated producer-side tests** from this file. Tests verify the producer implementation against the request and expected response. The corresponding stub is used by the consumer via **Stub Runner**. Only when both producer tests and consumer tests against the matching stub run properly do we have evidence for both sides.

### Contract for an empty list

For a search API returning a **list**, if no matching products are found and the agreement is `200` with an empty JSON array, express it directly:

~~~yaml
description: 'Valid product search with no results'
request:
  method: GET
  url: '/api/products?category=no-match'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body: []
~~~

`body: []` differs from `body: '[]'` in **YAML-level data type** (an empty sequence versus a two-character string). Check how your Spring Cloud Contract version actually constructs responses from both forms; pick a verified form rather than changing it arbitrarily.

### Error contract with colons and quotes in the message

~~~yaml
description: 'Response when SKU does not exist'
request:
  method: GET
  url: '/api/inventory/UNKNOWN'
response:
  status: 404
  headers:
    Content-Type: 'application/json'
  body:
    code: 'SKU_NOT_FOUND'
    message: "SKU 'UNKNOWN' was not found: check the code"
~~~

The `: ` in the message sits inside double quotes, so it is not interpreted as a key–value pair. If using single quotes, double the single quotes around `'UNKNOWN'`:

~~~yaml
message: 'SKU ''UNKNOWN'' was not found: check the code'
~~~

Both forms produce the exact same string. When error messages may be localized or contain dynamic data, consumers should rely on a **stable error code** (such as `SKU_NOT_FOUND`), rather than branching on the entire `message` text.

## 10. Regex Matchers: Quoting Rule Strings Properly

Spring Cloud Contract supports matcher types to avoid literal matching on dynamic data. The YAML parser must preserve the **regex string** intact before Spring Cloud Contract evaluates the matcher.

Example response contract where `sku` must match `SKU-` followed by three digits:

~~~yaml
description: 'Return properly formatted SKU'
request:
  method: GET
  url: '/api/inventory/SKU-101'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
  matchers:
    body:
      - path: '$.sku'
        type: by_regex
        value: '^SKU-\d{3}$'
~~~

**Read both value types carefully**:

- `body.sku` is the sample string the stub can provide.
- `matchers.body[].value` is the **regex string** for generated tests to validate real values against the rule, not a new JSON field returned to the consumer.
- `\d` stays intact thanks to **single quotes**. Switching to double quotes without writing `\\d` can cause a YAML parse error.
- `path: '$.sku'` is a JSONPath string, not shell or build-tool interpolation.

Verify exact matcher structures and support for array sizes, data types, regexes, or request/response semantics against the **Spring Cloud Contract version used by your project**. Do not copy Groovy DSL schemas verbatim into YAML DSL: they express similar goals with different syntax.

## 11. From YAML to Consumer: What Should You Check?

A small YAML diff can drastically alter a contract:

~~~diff
 response:
   status: 200
   body:
-    sku: '00123'
-    available: true
-    quantity: 12
+    sku: 00123
+    available: 'true'
+    quantity: '12'
~~~

Even though a reviewer still "sees" familiar values, the types have changed:

- `sku` is no longer guaranteed to be a string preserving its leading zeros.
- `available` became a string instead of a boolean.
- `quantity` became a string instead of a number.

**Producer:** generated contract tests should catch an implementation returning the wrong type under covered scenarios. However, if a team edits both the contract and producer with the same wrong types, the newly generated tests could still pass.

**Consumer:** tests using **Stub Runner** with the **candidate stub of the exact revision** must verify response consumption: deserializing `sku`, handling `available`, and computing with `quantity`. Testing against an old stub will miss the new breaking change.

**CI:** combine YAML/DSL validation, generating and running producer tests, packaging stubs at the same revision, running affected consumer tests, and checking compatibility before publishing artifacts. Never treat "YAML parses cleanly" as enough to approve a data-type change.

### YAML Pull Request Review Checklist

- [ ] Identifiers, timestamps, and numeric-looking strings are properly quoted.
- [ ] Booleans use unquoted `true/false` when truly boolean.
- [ ] Regexes containing `\` prefer single quotes or properly escaped double quotes.
- [ ] Strings containing `: `, ` #`, or syntax characters are properly quoted.
- [ ] No tab indentation, duplicate keys, or block scalars with unintended trailing newlines.
- [ ] Body maintains exact mapping/sequence/null/absent shape per the API.
- [ ] DSL is accepted by the current **Spring Cloud Contract** parser and plugin version.
- [ ] Generated producer tests and Stub Runner consumer tests use the same candidate contract/stub revision.
- [ ] If a type change is compatible, consumers depending on older types have been evaluated with an upgrade plan.

## 12. Practice Exercise: Find the Bugs in YAML

Someone wrote a contract for a SKU check endpoint as follows:

~~~yaml
description: Check stock
request:
  method: GET
  url: /api/inventory/00123
response:
  status: 200
  body:
    sku: 00123
    available: on
    quantity: '0'
    errorMessage: Stock status: empty
    pattern: "^\d{3}$"
~~~

Business requirements:

- `sku` must be string `00123`.
- `available` must be boolean `false` (out of stock).
- `quantity` must be number `0`.
- `errorMessage` is just a descriptive string containing `:`.
- `pattern` is a regex string containing `\d`.

**Identify the problems before looking at the solution.**

### Reference Solution

~~~yaml
description: 'Check stock'
request:
  method: GET
  url: '/api/inventory/00123'
response:
  status: 200
  body:
    sku: '00123'
    available: false
    quantity: 0
    errorMessage: 'Stock status: empty'
    pattern: '^\d{3}$'
~~~

Analysis:

1. `sku: 00123` can be inferred as a number or parsed inconsistently across parsers; quote it to preserve the exact identifier.
2. `available: on` is ambiguous between text and boolean depending on the YAML loader; the requirement calls for boolean `false`, so write `false` explicitly.
3. `quantity: '0'` is a string; change it to `0` to represent a number.
4. `errorMessage: Stock status: empty` contains `: ` inside a plain scalar, risking syntax errors; quote the entire message.
5. `pattern: "^\d{3}$"` uses `\d`, which is not a valid YAML double-quote escape; use single quotes or double quotes with `\\d`.

**Follow-up:** if `pattern` is matcher metadata rather than a response field the API should expose, do not put `pattern` inside `response.body`. Move the rule into **`matchers`** using your project's Spring Cloud Contract syntax. Contracts must describe the exact data consumers see, avoiding leaking test metadata into JSON responses.

## 13. Key Takeaways

**YAML quoting and escaping are part of contract design, not just formatting.** Wrong quoting can turn strings into numbers/booleans/null, break regexes, or drop/add newlines; confusing mappings with sequences changes the JSON shape the consumer reads. When writing YAML DSL for Spring Cloud Contract, verify parsed data types, request/response semantics, matchers, generated producer tests, and the stubs Stub Runner serves to consumers. Managing revisions and running checks in CI catches incompatible interface changes early.
