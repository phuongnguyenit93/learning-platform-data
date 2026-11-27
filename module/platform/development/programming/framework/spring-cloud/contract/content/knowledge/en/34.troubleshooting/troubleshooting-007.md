# Regex or JSONPath Looks Right in Concept, Fails Once Generated

In **Spring Cloud Contract**, you can describe a very sensible HTTP contract: order IDs start with `ORD-`, `amountMinor` must be a number, emails have a valid format, and an element in the `items` array must carry a specific `sku`. Yet after the plugin **generates producer verification tests** or **WireMock stub mappings**, the outcome can surprise you: test compilation fails on backslashes, generated assertions cannot find a JSONPath, a regex matcher compares a string against a number, or Stub Runner returns 404 even though the consumer's request looks right.

This class of failure is especially tricky to diagnose because an expression can be **right in concept** while **breaking in one of several interpretation layers**. Groovy/YAML is where the expression is written; Spring Cloud Contract parses the DSL and generates test/mapping code; the Java or Groovy compiler parses string literals; JSONPath evaluates the path against JSON; the regex engine performs matching; and WireMock evaluates the consumer's request. **Just one incorrect escape or type coercion** can distort the original intent.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_CONTRACT** module. The module scope covers HTTP/messaging contracts with Groovy/YAML DSL, producer test generation, publishing `stubs`, using Stub Runner, and CI/CD to detect incompatible API changes. The goal of this lesson is to locate the **exact layer where the error originates**, inspect generated output, build a minimal reproducer, and fix the **source contract** rather than patching generated code.

The examples below mainly use **Spring Cloud Contract 4.x with Groovy/YAML DSL, JUnit 5, and HTTP JSON**. DSL signatures and how generators, JSONPath, AssertJ/Hamcrest, or WireMock evaluate matchers can vary by version. When showing generated code or mappings, this lesson uses **illustrative forms**, without claiming every version emits those exact Java/JSON lines.

## 1. Understand the Entire Pipeline Before Editing a Regex

~~~mermaid
flowchart TD
    A["Source Groovy/YAML contract"] --> B["DSL parser and contract model"]
    B --> C["Generate producer verification test"]
    B --> D["Convert to WireMock stub mapping"]
    C --> E["Compile Java/Groovy test"]
    E --> F["JSONPath + regex/assertion on real producer response"]
    D --> G["Stub Runner loads mappings"]
    G --> H["WireMock matches consumer request"]
    H --> I["Return sample response to real client"]
    F --> J["Producer CI PASS/FAIL"]
    I --> K["Consumer CI PASS/FAIL"]
~~~

A failure can appear at:

| Layer | Typical Symptom | What to Inspect |
| --- | --- | --- |
| **DSL parse** | Plugin does not recognize matcher, invalid YAML. | Source Groovy/YAML, quoting, DSL schema for your version. |
| **Generation** | Generated test lacks expected assertion or path was altered. | Generated source, converted JSON mapping. |
| **Compilation** | `illegal escape character`, bad string literal, or missing import. | Generated Java/Groovy line, compiler/SDK versions. |
| **JSONPath evaluation** | Key not found, returns list instead of scalar, wrong type. | Actual JSON response and exact JSONPath used by generated test. |
| **Regex evaluation** | Pattern matches wrongly or fails on seemingly valid data. | Post-escape pattern, value type, full-match/substring semantics. |
| **Stub request matching** | WireMock fails to match request, returns 404 no-match. | Stub mapping and request journal, not just generated producer test. |
| **Consumer decoding** | Stub returns expected response, DTO fails deserialization. | Wire bytes/JSON types, `Content-Type`, client DTO, and producer stub version. |

**Do not start by loosening a regex “to make it green.”** First determine **which test failed and at which layer**: producer verification, stub matching, consumer deserialization, or test generation/compilation itself.

## 2. The Two Sides of Matchers Are Asymmetric

Spring Cloud Contract supports `bodyMatchers` on both **request** and **response**:

| Location in DSL | Primary Purpose in HTTP Contracts | Risk If Misunderstood |
| --- | --- | --- |
| `request.bodyMatchers` | Describes how **requests** should be matched, especially in generated stubs. | Overly strict WireMock causes 404 no-match; overly loose accepts bad requests. |
| `response.bodyMatchers` | Describes how **generated producer tests** verify the **producer response**. | Pinning dynamic values causes false failures; type-only checks miss business bugs. |
| `request.headers/queryParameters` | Defines required request headers/query params. | Consumer omits a header yet stub returns 200 if mapping is too loose. |
| `response.headers` | Verifies metadata the producer promises to return. | Byte-for-byte comparison of trivial values or omitting critical headers. |
| Consumer test assertions | Verifies the **real client** understands and handles stub data. | Asserting only 200 without verifying DTOs, error handling, or side effects. |

A response matcher `jsonPath('$.orderId', byRegex(...))` does not mean Stub Runner will invent a random new `orderId` per request. **Stubs return the sample response in the contract**; response-side regexes primarily let generated verification tests check the **real producer**.

Conversely, request matchers govern how WireMock decides **whether to return a stub response**. A 404 no-match is not necessarily a business 404 response from the producer.

## 3. Running Example: Order API

Suppose **Order Service** is the producer and **Billing Service** is the consumer:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Valid response:

~~~json
{
  "id": 42,
  "orderId": "ORD-0042",
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "createdAt": "2026-11-24T04:00:00Z",
  "metadata": {
    "trace.id": "trace-abc123"
  },
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": 1}
  ]
}
~~~

The contract carries distinct semantics:

- `id` corresponds to request `/42`, so an **exact 42** assertion makes sense.
- `orderId` must follow `ORD-` plus digits, yet may vary across different fixtures.
- `status=PAID`, `currency=VND`, and `amountMinor=125000` are **business values** for this fixture.
- `createdAt` is a dynamic timestamp and should not always equal one fixed instant.
- Key `trace.id` **contains a dot in its name**, rather than being a nested `trace` object holding key `id`.
- `items` is an array; selecting **one element**, **all elements**, or a **filtered list** requires different matcher styles.

We will reuse this same JSON to isolate errors rather than switching examples at every step.

## 4. A First Groovy Contract That Can Generate Tests

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            orderId: 'ORD-0042',
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND',
            createdAt: '2026-11-24T04:00:00Z',
            metadata: ['trace.id': 'trace-abc123'],
            items: [
                [sku: 'SKU-42', quantity: 2],
                [sku: 'SKU-99', quantity: 1]
            ]
        )
        bodyMatchers {
            jsonPath('$.orderId',
                byRegex('^ORD-[0-9]{4}$'))
            jsonPath('$.createdAt',
                byRegex(
                    '^[0-9]{4}-[0-9]{2}-[0-9]{2}' +
                    'T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
                ))
            jsonPath('$["metadata"]["trace.id"]',
                byRegex('^trace-[A-Za-z0-9-]+$'))
        }
    }
}
~~~

Intentional details in this example:

1. `orderId` is a **string** with a length-bounded regex.
2. `createdAt` uses a regex checking **UTC timestamp** shape without verifying calendar validity.
3. The dotted key is accessed via **bracket notation**.
4. `id`, `status`, `amountMinor`, and `currency` keep fixture-exact expected values.
5. `items` has no custom matcher yet, because ordering and element-count requirements must be decided first.

In a real project, the plugin still needs proper dependencies, a base test, JUnit/test mode, and contract source path. Never treat a valid-looking Groovy DSL snippet as proof that generated tests were created and executed.

## 5. Four Escaping Layers That Easily Change a Regex's Meaning

A regex string typically passes through multiple layers:

~~~text
Intended regex:      \d{4}
Groovy source:       '\\d{4}'  (single-quoted string)
Value after Groovy:  \d{4}
Java generated code: "\\d{4}" (if generator emits Java String literal)
Regex engine:        \d{4}
~~~

At each layer, `\` can be either a **string-literal escape** or **part of regex syntax**. Common mistakes:

| Source Expression | Potential Issue |
| --- | --- |
| `'\d{4}'` in Groovy string | Single backslash is not escaped at the string layer; syntax/behavior depends on parser. |
| `'\\d{4}'` in Groovy single-quoted | Produces regex containing `\d{4}` when escaping applies as expected. |
| `"\\d{4}"` in Java string literal | Supplies regex `\d{4}` to `Pattern`. |
| `'\d{4}'` in YAML single-quoted scalar | `\` is preserved literally; YAML single quotes do not use Java-style escapes. |
| `"\d{4}"` in YAML double-quoted scalar | Can be **invalid YAML** since `\d` is not a valid YAML escape sequence. |
| `"[0-9]{4}"` | Avoids backslashes altogether and stays clear when ASCII digits are needed. |

**Do not count backslashes by eye and guess.** Compare **source DSL → generated source → actual regex value**. When only ASCII digits are needed, `[0-9]` is easier to review than `\d` and avoids ambiguity around Unicode digit classes.

### 5.1. Groovy Single Quotes, Double Quotes, and Slashy Strings

In Groovy:

~~~groovy
def singleQuoted = '\\d{4}'
def doubleQuoted = "\\d{4}"
def slashy = /\d{4}/
~~~

All three can deliver `\d{4}` to the regex engine, yet their **escaping/interpolation mechanisms differ**. Slashy strings are convenient for backslash-heavy regexes, though patterns containing `/` or `$` require understanding Groovy's slashy/GString rules.

When contracts use Groovy DSL, **prefer single-quoted strings** for regexes that need no interpolation, or use character classes like `[0-9]` to cut down escaping layers. Avoid concatenating fragments if that makes the final pattern harder for reviewers to read.

### 5.2. YAML Single Quotes Are Usually Simpler for Regexes

~~~yaml
matchers:
  body:
    - path: $.orderId
      type: by_regex
      value: '^ORD-[0-9]{4}$'
    - path: $.createdAt
      type: by_regex
      value: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
~~~

YAML single-quoted scalars treat `\` as a literal character; if you need an apostrophe `'`, YAML single quotes escape it using **two consecutive apostrophes**. In YAML **double-quoted** strings, backslashes act as escapes.

**Do not copy a Java literal `\\d` into YAML assuming the result is identical.** The required number of backslashes depends on the string syntax layer.

## 6. Syntactically Valid Regex, Wrong Data Domain

Suppose an Order code requires `ORD-` followed by **exactly four ASCII digits**.

| Regex | `ORD-0042` | `ORD-42` | `XORD-0042-OLD` | Notes |
| --- | --- | --- | --- | --- |
| `ORD-[0-9]+` | May match | May match | May match **substring** if engine searches | No length or boundary limits. |
| `^ORD-[0-9]{4}$` | Match | No | No | Checks the entire string with boundaries. |
| `^ORD-[0-9]{1,4}$` | Match | Match | No | Accepts 1–4 digits. |
| `^.*ORD-.*$` | Match | Match | Match | Far too loose. |

**Matching operations can differ**:

- `Pattern.matcher(value).matches()` normally requires the **entire string** to match.
- `Pattern.matcher(value).find()` looks for **any matching substring**.
- Some DSL/JSONPath/WireMock matchers apply version-specific behavior or flags.

Therefore, when the contract expects the **entire string** to conform, use `^...$` anchors where appropriate and inspect **generated assertions/mappings**. Do not assume every library uses `matches()` or every version uses `find()`.

**Anchor caveat:** `$` has subtleties with trailing newlines and Java regex flags. For strict inputs, check how the generator evaluates full-string matches and test edge cases with newlines rather than trusting anchors blindly.

## 7. Regex on a JSON Number Differs from Regex on a String

JSON example:

~~~json
{
  "amountMinor": 125000,
  "orderId": "ORD-0042"
}
~~~

A JSON parser distinguishes:

- `$.amountMinor` → **JSON number** (represented by the JSONPath engine as `Integer`/`Long`/`BigDecimal` depending on parser).
- `$.orderId` → **JSON string**.

If you write:

~~~groovy
bodyMatchers {
    jsonPath('$.amountMinor', byRegex('[0-9]+'))
}
~~~

you are applying a **regular expression to a JSON number**. Depending on the generated assertion, the library may **convert the number to a String**, require a String-typed matcher, or fail on a type mismatch. Some setups will pass while **losing JSON number type checking**, since `"125000"` as a string also matches `[0-9]+`.

Better choices per requirement:

| Requirement | Verification Approach |
| --- | --- |
| `amountMinor` equals exact `125000` for fixture | Keep numeric expected JSON and equality assertion. |
| `amountMinor` varies yet **must be a number** | Use `byType()` per JSONPath/type support, plus range/business assertions. |
| `amountMinor` is a non-negative integer | Check JSON numeric type and value bounds with an assertion or custom command. |
| `orderId` is a formatted string | Use `byRegex(...)` on the string. |

**Rule:** regular expressions validate **character strings**. If the consumer relies on **JSON type**, never use a regex as the sole substitute for a type assertion.

## 8. JSONPath Is Not Just a Plain Field Name String

With the sample JSON:

~~~json
{
  "metadata": {
    "trace.id": "trace-abc123"
  },
  "items": [
    {"sku": "SKU-42"},
    {"sku": "SKU-99"}
  ]
}
~~~

Correct paths:

| JSONPath | Expected Result |
| --- | --- |
| `$.metadata` | A JSON object. |
| `$.metadata['trace.id']` | String `trace-abc123`. |
| `$['metadata']['trace.id']` | String `trace-abc123`. |
| `$.metadata.trace.id` | Looks up `metadata.trace.id` across **two nested keys**, not literal key `trace.id`. |
| `$.items[0].sku` | Scalar `SKU-42`. |
| `$.items[*].sku` | **List** `["SKU-42","SKU-99"]`. |
| `$.items.length()` | Support depends on JSONPath engine/expression; verify before relying on it. |

**Dot notation** traverses nested keys; **bracket notation** selects keys containing dots, spaces, hyphens, or special characters that dot notation cannot express safely.

This is a very common failure when a JSONPath looks “right” in code review yet evaluates to **no value** after generation.

### 8.1. Root Object vs. Root Array

The path:

~~~text
$.items[0].sku
~~~

is valid only when the JSON root is an **object** holding an `items` property. If the API returns an array directly at the root:

~~~json
[
  {"sku": "SKU-42"},
  {"sku": "SKU-99"}
]
~~~

then the path starts with:

~~~text
$[0].sku
~~~

**Do not apply a flat response's JSONPath to a wrapped object.** Many test failures happen because the producer returns `{"data": {...}}` or `{"result": [...] }`, so the path is wrong right from the root.

## 9. Does JSONPath Return a Scalar or a List?

This distinction is often obscured by the DSL:

~~~groovy
bodyMatchers {
    jsonPath('$.items[0].sku', byRegex('^SKU-[0-9]+$'))
    jsonPath('$.items[*].sku', byRegex('^SKU-[0-9]+$'))
}
~~~

The first expression typically selects **one string**. The second selects **a list**. If the generator feeds that list into a regex matcher designed for a String, you may see:

~~~text
Expected: a string matching ^SKU-[0-9]+$
Actual:   [SKU-42, SKU-99]
~~~

This is an **illustrative message**, not a fixed Spring Cloud Contract error string.

Options based on contract intent:

1. To check only the **first element**, use `$.items[0].sku`, understanding it **does not verify subsequent elements**.
2. To check **every element**, use a matcher/JSONPath supporting **each element**, or write an iterating assertion in an appropriate test.
3. To check **presence of a specific SKU**, use a JSONPath filter supported by the engine or verify list membership in consumer tests.
4. To check **count/uniqueness**, add size/multiplicity assertions.

Never “fix” a type mismatch by changing the pattern to `.*SKU.*` so it matches `list.toString()`. That depends on Java's list formatting and can pass even when individual elements are wrong.

## 10. JSONPath Filters: Quotes and Data Types

Suppose:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": 1}
  ]
}
~~~

Intent: select the entry with `sku=SKU-42`. A common JSONPath filter:

~~~text
$.items[?(@.sku == 'SKU-42')]
~~~

When placing a filter inside **Groovy DSL**, watch quotes:

~~~groovy
// Single-quoted Groovy containing single quotes in the filter:
jsonPath('$.items[?(@.sku == \'SKU-42\')]', byType())

// More readable with double-quoted Groovy
// when no interpolation is needed:
jsonPath("$.items[?(@.sku == 'SKU-42')]", byType())
~~~

Once the string passes through the Groovy parser, verify the resulting JSONPath still preserves `'SKU-42'`. JSONPath engines differ in **filter syntax, scalar vs. list results, and numeric coercion**; avoid overly complex filters unless your plugin/generator version handles them accurately.

**Do not write:** `@.quantity == '2'` when the actual JSON contains number `2` and you want numeric equality. Some libraries coerce types while others do not; match the actual JSON type:

~~~text
$.items[?(@.quantity == 2)]
~~~

For a business invariant like `quantity > 0` across **all items**, a filter selecting matching elements **does not prove every element is valid**. Assert that **no violating item exists** or iterate over the collection in an appropriate test.

## 11. Missing, `null`, and Empty Must Not Be Conflated

Compare:

~~~json
{}
~~~

~~~json
{"note": null}
~~~

~~~json
{"note": ""}
~~~

~~~json
{"note": "ship before Friday"}
~~~

A JSONPath `$.note` may:

- **Not exist**, throwing `PathNotFoundException` or returning a default depending on config.
- **Exist with JSON `null`**, typically represented as Java `null` or `NullNode`.
- **Exist with an empty string**.
- **Exist with a non-empty string**.

A matcher like `byRegex('.*')` can obscure these distinctions because a string regex cannot decide **whether the field was present** if the framework coerced missing/null to a string or applied an unintended default.

Write the **contract policy** first:

| Policy | What Must Be Checked |
| --- | --- |
| `note` required, non-null string | Path exists, non-null, right type. |
| `note` optional, string if present | Missing allowed; `null` disallowed unless policy permits. |
| `note` nullable | Distinguish `null` from missing when semantics require it. |
| PATCH: missing leaves unchanged, `null` clears | **Two distinct behavior branches** need separate contracts/tests. |

If built-in DSL matchers do not distinguish these fully, add targeted unit/integration tests or intentional custom assertions. **Never loosen a matcher merely because “`null` broke the test” without clarifying the nullability contract.**

## 12. JSONPath on Decimals, Booleans, and Enums

Payload:

~~~json
{
  "paid": true,
  "amount": 1250.50,
  "currency": "VND",
  "status": "PAID"
}
~~~

Distinct outcomes:

| Path | JSON Type | What to Protect |
| --- | --- | --- |
| `$.paid` | Boolean | `true` differs from string `"true"`. |
| `$.amount` | Number | Decimal value, business precision/scale policy. |
| `$.currency` | String | ISO format or fixture equality. |
| `$.status` | String | Supported enum set; not “any arbitrary string.” |

For money, prefer transmitting **integer minor units** where domain rules allow; when using decimals, state rounding/precision rules explicitly instead of relying solely on a decimal-string regex.

**Java numeric classes are not JSON numeric types.** A JSON number may be returned by parsers as `Integer`, `Long`, `Double`, or `BigDecimal` depending on magnitude and settings. If a generated test compares `Integer(42)` with `Long(42)` and fails, check **coercion and matchers in generated code**; never convert the contract field to a string just to “make types match.”

## 13. Do Not Confuse JSON Type with Regex Presentation

An error-prone pattern:

~~~groovy
response {
    body(
        orderId: 'ORD-0042',
        amountMinor: '125000'
    )
    bodyMatchers {
        jsonPath('$.amountMinor', byRegex('[0-9]+'))
    }
}
~~~

Here the contract defines `amountMinor` as a **JSON string** because the sample is `'125000'`, whereas consumers may expect a **number**. A passing regex does not prove the type is right.

Fix the **data model first**:

~~~groovy
response {
    body(
        orderId: 'ORD-0042',
        amountMinor: 125000
    )
    bodyMatchers {
        jsonPath('$.orderId', byRegex('^ORD-[0-9]{4}$'))
        jsonPath('$.amountMinor', byEquality())
    }
}
~~~

If `amountMinor` is genuinely dynamic, use a type-checking matcher plus dedicated range assertions. **Never pick regex simply because it is easy to type**; choose tools based on **type and semantics**, not how simple the generated test looks.

## 14. Inspect Generated Test Source, Not Just the DSL

When a test fails, the single highest-value step is **opening the file generated by the plugin**. In many Maven setups, generated sources live under:

~~~text
target/generated-test-sources/
~~~

In Gradle, generated sources typically live under:

~~~text
build/generated-test-sources/
~~~

**Subdirectories and task names depend on plugin version and project config.** Check Maven/Gradle logs to locate the **actually configured directory**; do not assume every version uses the exact same folder.

Inside the generated test, inspect:

1. The test method matching the contract `name` or file.
2. Outgoing request `method`, `url`, headers, and body.
3. The JSONPath literal **after generator escaping**.
4. The regex literal **after Java/Groovy compiler interpretation**.
5. Whether the matcher implementation uses `equals`, `matches`, `find`, or another helper.
6. Whether JSON parsing yields a scalar or a collection.
7. Which assertion handles missing/null/JSON numbers.
8. The actual base test class and test mode.

Example **shape** of a generated assertion:

~~~java
// PSEUDOCODE: exact generator and assertion library may differ.
Object actual = JsonPath.read(
    responseBody, "$.orderId"
);
assertThat(actual.toString())
    .matches("^ORD-[0-9]{4}$");
~~~

There is no guarantee your generator emits this exact form. Focus on the **semantics of the generated code**, not just the filename or a “Generating contracts” log line.

## 15. Inspect the Converted WireMock Mapping

For request contracts with body matchers, the plugin typically emits mappings using WireMock `bodyPatterns`/JSONPath or equivalent matchers:

~~~json
{
  "request": {
    "method": "POST",
    "urlPath": "/api/orders",
    "bodyPatterns": [
      {
        "matchesJsonPath": "$.clientRequestId"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {"Content-Type": "application/json"},
    "body": "{\"id\":42,\"status\":\"CREATED\"}"
  }
}
~~~

**This is a simplified illustrative mapping**, not necessarily the exact output of `byRegex(...)`: Spring Cloud Contract may emit a compound JSONPath expression or another matcher checking the value as well.

In WireMock, some expressions check **path existence** while others check **evaluated values**; `matchesJsonPath` must not be assumed by default to “validate a regex on every leaf string.”

**What to verify:** do invalid hypothetical requests (wrong `clientRequestId`, missing required field, wrong body type) **fail to match**, while valid requests match? Inspecting a `matchesJsonPath` snippet and guessing its behavior is not enough.

### 15.1. The Stub JAR Might Not Match What Was Just Generated

If you edit the Groovy DSL and run consumer tests with:

~~~text
com.acme:order-service:1.4.1:stubs
~~~

before packaging/publishing the new stub, Stub Runner will still read the **old version's mappings**. Verify:

- Maven coordinates `groupId:artifactId:version:stubs`.
- `StubsMode.LOCAL` vs `REMOTE`, `repositoryRoot`, and local Maven cache.
- Checksum/contents of the loaded JAR.
- Contract source Git SHA matching the artifact.
- WireMock request journal on the exact instance called by the consumer.

**Changing a matcher on the producer without updating the artifact used by consumer tests** is a classic reason for “I fixed it and still get 404.”

## 16. Request `bodyMatchers`: Dynamic Values and 404 No-Match

Suppose Billing sends:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "C-42",
  "quantity": 2,
  "clientRequestId": "req-xyz-2026"
}
~~~

In the contract, we might write:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldCreateOrder'
    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2,
            clientRequestId: 'req-example'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('^req-[A-Za-z0-9-]+$'))
        }
    }
    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'CREATED')
    }
}
~~~

The request matcher lets `clientRequestId` vary per format. However, it **does not mean**:

- Any `customerId` is accepted in **this stub scenario**.
- `quantity=-99` is valid if validation requires positive numbers.
- The consumer can omit `Content-Type` or change the URL without impact.

If WireMock returns 404, verify **method/path/headers/body** match the real mapping before loosening regexes. A 404 no-match is not a business 404; create a dedicated 404 contract if the client needs to test nonexistent orders.

## 17. Comparison Table: Is the Failure on the Producer or Consumer Side?

| Symptom | Producer Generated Test | Consumer Stub Runner Test | Layer to Investigate |
| --- | --- | --- | --- |
| Compiler reports `illegal escape` | **Fails before running** | Likely unaffected yet | Generated Java/Groovy source and DSL escaping. |
| JSONPath `$.items[*].sku` yields list yet regex expects string | **Fails assertion** | Stub may still return sample | Response matcher/type in generated test. |
| `orderId` response violates format | **Fails** if matcher is effective | Stub may still return valid sample | Producer implementation or broken matcher. |
| Consumer POST sends dynamic ID, WireMock no-match | Producer test may PASS | **404** | Request body matcher/mapping. |
| Consumer DTO fails reading `amountMinor` | Producer may PASS with loose matcher | **Fails deserialization** | JSON type, contract, and DTO. |
| Same contract source, consumer loads old stub JAR | Producer test PASSES after fix | Consumer test stays broken | Stub version/artifact/cache. |
| Test gets JSON `null` when expecting missing | Depends on matcher | Depends on DTO | Nullability and JSONPath config. |
| Producer security 401 returns 200 | **Fails** if negative contract holds | Not necessarily detected | Auth test context and contract status. |

**Do not treat “green producer tests” as a guarantee consumer tests will be green** when request mappings, stub versions, or client DTOs are misaligned. Both suites serve distinct purposes yet must share the **same effective contract**.

## 18. Controlled Minimal Reproducer Workflow

When a regex or JSONPath breaks after generation, create **one small contract and response**:

~~~json
{
  "orderId": "ORD-0042",
  "amountMinor": 125000,
  "items": [
    {"sku": "SKU-42"},
    {"sku": "SKU-99"}
  ]
}
~~~

Add a single matcher:

~~~groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('^ORD-[0-9]{4}$'))
}
~~~

Then increase complexity step by step:

1. Test `$.orderId` against the JSON fixture with the actual JSONPath library.
2. Test the regex standalone with `Pattern` or the exact matcher library version.
3. Generate the producer test, read the source, and confirm JSONPath/pattern remain intact.
4. Run just that one test method.
5. Add `$.items[0].sku`; confirm scalar result.
6. Add `$.items[*].sku`; observe the list result and choose collection-appropriate assertions.
7. Add the dotted key using bracket notation.
8. Add null/missing branches before merging back into the full contract.

**Building a minimal reproducer separates parser/escaping bugs from application business bugs.** If the minimal test fails immediately on the matcher, there is no need to debug the database, JWTs, or the whole Kafka setup.

## 19. Test the Pattern Independently with the Java Regex Engine

In Java, you can write a small test:

~~~java
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RegexContractTest {
    @Test
    void orderIdHasFourDigits() {
        Pattern pattern = Pattern.compile("^ORD-[0-9]{4}$");

        assertThat(pattern.matcher("ORD-0042").matches())
            .isTrue();
        assertThat(pattern.matcher("ORD-42").matches())
            .isFalse();
        assertThat(pattern.matcher("XORD-0042-OLD").matches())
            .isFalse();
    }
}
~~~

If this pattern passes while the generated assertion fails, the difference likely lies in the **generated literal**, **JSONPath returning a non-String type**, or **matcher semantics**. If the standalone pattern fails, fix the regex itself before touching Spring Cloud Contract.

### 19.1. Test `\d` Escaping Separately

~~~java
Pattern digits = Pattern.compile("^ORD-\\d{4}$");

assertThat(digits.matcher("ORD-0042").matches()).isTrue();
~~~

In a Java string literal, `\\d` produces regex escape `\d`. Writing `"\d"` directly in Java source is an invalid escape sequence. When a regex travels from Groovy/YAML through the generator, the final source must preserve the right escaping layers.

**Never edit generated Java to add extra backslashes and commit it**: the next generation run will overwrite your edit. Fix the literal in **Groovy/YAML DSL** and inspect regenerated code.

## 20. Isolate JSONPath Testing from Regex in a Small Test

Example using Jayway JsonPath (commonly present in the toolchain):

~~~java
import com.jayway.jsonpath.JsonPath;
import java.util.List;

String json = """
    {"items":[
      {"sku":"SKU-42"},
      {"sku":"SKU-99"}
    ]}
    """;

String first = JsonPath.read(json, "$.items[0].sku");
List<String> all = JsonPath.read(json, "$.items[*].sku");

assertThat(first).isEqualTo("SKU-42");
assertThat(all).containsExactly("SKU-42", "SKU-99");
~~~

This example uses Java text blocks (**JDK 15+**) and AssertJ, assuming full imports/dependencies. It shows that **the same JSON** queried with different JSONPaths yields **two different result types**.

To test a dotted key:

~~~java
String metadata = """
    {"metadata":{"trace.id":"trace-abc123"}}
    """;

String trace = JsonPath.read(
    metadata, "$['metadata']['trace.id']");
assertThat(trace).isEqualTo("trace-abc123");
~~~

If the standalone JSONPath library succeeds while the generated assertion fails, inspect **JSONPath parser configuration, path literal, type conversion, and library versions** in the build. Many error messages omit lost quotes, so printing the evaluated path in diagnostic logs (without sensitive data) is very helpful.

## 21. Inspecting Generated Tests with Maven and Gradle

With the Maven plugin bound to the lifecycle:

~~~shell
./mvnw clean test
~~~

If you need to split phases while investigating (for illustration):

~~~shell
./mvnw generate-test-sources
./mvnw test
~~~

**Note:** running individual goals/phases does not replace a full producer verification build. Verify the plugin actually generates tests before `test-compile` and Surefire runs them, rather than relying solely on `BUILD SUCCESS`.

With the Gradle plugin:

~~~shell
./gradlew tasks --all
./gradlew generateContractTests
./gradlew test
~~~

Task names and behavior can differ in customized setups. `generateContractTests` is common; inspect the task graph and generated directory of your **actual project**.

A concrete investigation sequence:

1. Clear old output with `clean` to eliminate stale generated sources/stub mappings.
2. Enable appropriate logging to see **discovered contract files** and generated test counts.
3. Open the generated test file containing the suspect matcher.
4. Compare JSONPath/regex patterns between source DSL and generated code.
5. Run a narrow test and retain **redacted** stack traces/actual JSON.
6. For request matchers, open the JSON mapping from plugin conversion or the `stubs` JAR.
7. Run the consumer test and inspect the request journal on the exact WireMock instance.

**Do not leave unbounded debug logging enabled** when CI handles secrets, bearer tokens, or real customer data. Prefer synthetic contract fixtures, test/regex paths, and build metadata.

## 22. Pitfalls Specific to JSONPath Filters and Array Order

A filter selecting elements:

~~~text
$.items[?(@.quantity > 1)]
~~~

is not equivalent to asserting:

> Every element must have quantity greater than 1.

A filter merely selects **elements matching the condition**. If invalid elements exist, the filtered result can still be non-empty, letting an “at least one valid item exists” test pass while the array as a whole is broken.

Example:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": -5}
  ]
}
~~~

Filter `quantity > 1` still returns one element. To verify **all quantities are positive**, assert that no violating element exists or iterate over the array in an invariant test:

~~~java
List<Integer> quantities =
    JsonPath.read(json, "$.items[*].quantity");

assertThat(quantities).allMatch(q -> q > 0);
~~~

**A JSONPath that selects data does not automatically express a universal invariant across an entire array.** For complex business rules, separate contract shape from domain-level assertions rather than cramming every invariant into one unreadable expression.

### 22.1. Ordered vs. Unordered Arrays

If `history` promises an ascending timeline, use an ordered assertion. If `tags` is a set, compare order-insensitively while preserving multiplicity:

~~~java
assertThat(historyStates)
    .containsExactly("CREATED", "PAID", "SHIPPED");

assertThat(tags)
    .containsExactlyInAnyOrder("fragile", "insured");
~~~

A recursive JSONPath `$..status` pulling statuses across the whole tree may return a **list** lacking the ordering or context the consumer needs. Prefer explicit paths over recursive descent `..` whenever results could widen unexpectedly.

## 23. Headers, Charsets, and Formats: Avoid Misblaming JSONPath

Not every response-body test failure is caused by JSONPath. Suppose the producer returns:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

while a header matcher compares the raw string:

~~~text
application/json
~~~

If the consumer only requires a JSON media type, `charset` may be allowed by protocol/config. Fix the **header matcher** semantically instead of altering a body JSONPath to “work around” a header assertion.

Other causes to rule out:

- Response is an HTML error page from a security filter, not JSON.
- App returns `204 No Content` while the contract expects a JSON body.
- `Instant` serialization changed format or timezone.
- Jackson naming strategy turned `orderId` into `order_id`.
- API added a `data` wrapper, shifting `$.orderId` to `$.data.orderId`.
- Content encoding/compression left the test helper unable to decode the body.

**Inspect actual HTTP status, `Content-Type`, and body before editing matchers.** If the producer returns 500 with an error page, tweaking the `orderId` regex will never fix the real root cause.

## 24. Messaging: Which Abstraction Does JSONPath Run On?

A messaging contract may define:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-0042',
            amountMinor: 125000
        )
        bodyMatchers {
            jsonPath('$.eventId',
                byRegex('^evt-[A-Za-z0-9-]+$'))
        }
    }
}
~~~

If the generated message test fails on `$.eventId`, check **what payload `MessageVerifierReceiver` actually returns**:

- A Java/Groovy `Map`?
- A JSON `String`?
- `byte[]` containing UTF-8 JSON?
- An envelope object holding a `payload` field?
- A binary Avro/Protobuf record?

JSONPath works only when applied to the **JSON structure expected by the matcher**. If an adapter returns the entire envelope as the payload:

~~~json
{
  "payload": {
    "eventId": "evt-00042"
  }
}
~~~

then `$.eventId` does not exist, even though `$.payload.eventId` does. However, **do not rewrite the contract to `$.payload.eventId`** if the envelope is merely an internal adapter wrapper rather than the wire contract. Fix the **adapter/serialization boundary** so generated tests receive the payload at the right abstraction.

For messaging, also check **destination, header types, serializer/schema registry, broker/test binder**, and timeouts. A JSONPath regex passing against a test `Map` does not prove real consumers can decode Kafka/queue bytes; add codec/transport integration tests when there is risk.

## 25. Error Matrix and Responsible Fixes

| Symptom | Most Likely Cause | Right Fix |
| --- | --- | --- |
| Groovy parse error on regex with `\d` | Unescaped string layer. | Use `[0-9]` or escape Groovy literal properly; inspect generated code. |
| YAML reports unknown escape `\d` | Bad escape in double-quoted scalar. | Switch to YAML single quotes or escape per YAML rules. |
| Generated Java `illegal escape character` | Generator/literal left an invalid `\` in Java string. | Fix source DSL, inspect generated source; check version if generator bug. |
| Regex matches unintended substrings | Missing anchors or `find()` matcher used. | Clarify semantics, use full-string pattern and mutation cases. |
| Regex matches `"125000"` when number expected | Checks only digits, ignores JSON type. | Keep numeric sample body and type/equality assertions. |
| JSONPath `$.metadata.trace.id` not found | Actual key is literal `trace.id`. | Use bracket notation. |
| `$.items[*].sku` yields list when matcher expects String | Indefinite/collection path. | Use scalar path or collection matcher/loop. |
| Filter `?(@.quantity > 0)` passes despite negative item | Filter proves at least one matches, not all. | Assert all elements or zero violating elements. |
| Missing and `null` treated alike | JSONPath defaults/path config. | Define presence/nullability policy and test separately. |
| JSON number 42 fails equality with expected 42 | Parser/generator uses different Java numeric class or strict equality. | Check JSON numeric semantics, type/coercion per version. |
| Date regex passes day `99` | Regex checks shape only, not calendar rules. | Combine with `Instant.parse`/validator where needed. |
| Producer test green, Stub Runner POST returns 404 | Response matcher right, request body matcher misaligned. | Inspect WireMock mapping, journal, and dynamic IDs. |
| DSL fixed yet Stub Runner uses old mapping | Old stub JAR/version/local cache. | Rebuild/publish and pin artifact checksum/version. |
| Test fails JSONPath yet actual response is HTML | Wrong status/security/`Content-Type`. | Fix producer bug or fixture, not JSONPath. |
| Generated matcher completely absent | DSL in wrong scope, unsupported plugin version, or skipped. | Check source DSL, plugin logs, and generated code. |
| Tests pass after putting `byType()` on every field | Matcher too loose. | Restore equality/invariants for business fields, run mutation tests. |
| Messaging JSONPath cannot find key | Adapter returns envelope/`byte[]` at wrong abstraction. | Normalize payload properly, add codec/broker tests. |
| Consumer gets WireMock 404 instead of `ORDER_NOT_FOUND` | No-match 404 mistaken for business 404. | Check matched mapping, request, and error body contract. |

**Diagnostic rule:** if a failure appears only **after generation**, inspect **generation outputs**. If it appears only **when Stub Runner runs**, inspect the **artifact and WireMock mappings** Stub Runner actually loaded.

## 26. Adding Quality Gates in CI/CD

~~~mermaid
flowchart TD
    A["PR modifies Groovy/YAML contract"] --> B["Parse/generate producer tests"]
    B --> C{"Does generated code compile?"}
    C -->|No| D["Fail: check escaping and plugin version"]
    C -->|Yes| E["Review JSONPath/patterns in generated tests"]
    E --> F["Run producer verification on real implementation"]
    F --> G{"Semantics correct?"}
    G -->|No| H["Fail: fix contract or implementation intentionally"]
    G -->|Yes| I["Convert stubs and inspect mappings"]
    I --> J["Consumer Stub Runner tests with real client"]
    J --> K{"Request matches and DTO valid?"}
    K -->|No| L["Check WireMock journal, artifact, and client"]
    K -->|Yes| M["Publish/promote immutable stubs + CI report"]
~~~

A high-quality pipeline should:

1. **Generate tests from real contracts**; fail if required contracts are not discovered.
2. **Compile tests**, never hiding escaping/JSONPath errors behind skip flags.
3. **Run producer verification**; report test counts and scenario names.
4. **Run small mutations** on critical contracts (valid case PASSES, incompatible change FAILS), especially when editing complex matchers.
5. **Inspect stub mappings** for request matchers or new endpoints.
6. **Run consumer Stub Runner** with pinned artifact/version and the real client.
7. **Record Git SHA, plugin versions, stub coordinates/checksums, and test reports** for reproducibility.
8. **Block publishing** if generated tests were skipped, 0 tests ran unexpectedly, or regressions remain unresolved.

**Never treat “fixed the regex, build is green” as sufficient proof.** An overly broad regex turns tests green by stopping them from catching bugs. Always verify in reverse that a breaking change still FAILS.

## 27. Hands-on Exercise: From JSONPath Error to Fixing the Right Contract

Practice on the Order Service producer and Billing Service consumer using a Spring Cloud Contract version compatible with your project's Spring Boot release.

1. **Create a Groovy contract** for `GET /api/orders/42` returning the JSON from section 3, including `orderId`, `amountMinor`, `metadata["trace.id"]`, and `items`.
2. **Write a simple regex** `^ORD-[0-9]{4}$` for `$.orderId`. Run a standalone Java regex test and verify valid/invalid cases.
3. **Try a `\d` regex** in Groovy/YAML using different quoting styles; compare source DSL, generated Java literal, and actual regex value. Note any parse/compile errors.
4. **Create a deliberately wrong JSONPath** `$.metadata.trace.id`, then fix it to `$['metadata']['trace.id']` after observing the JSONPath result.
5. **Use `$.items[*].sku` with a string-expecting matcher**, note the list/type mismatch, then switch to a collection matcher or per-item assertion matching requirements.
6. **Create a `quantity > 0` filter**, demonstrate it only selects matching items without guaranteeing **all quantities are positive**, and add a proper invariant test.
7. **Keep `amountMinor` as a JSON number**, test regex vs `byType()`, and choose the option preserving the consumer's type/value semantics.
8. **Test missing `note`, `note:null`, and `note:""`**, documenting the API policy and needed assertions.
9. **Regenerate producer tests**, inspect generated files (without hand-editing), run `mvn clean test` or equivalent Gradle task, and observe the exact failure.
10. **Intentionally break the producer**: change `orderId` format, turn the JSON number into a string, change status 200 to 500; generated tests must FAIL.
11. **Test a valid change**: vary a valid trace ID or valid timestamp; tests must not FAIL for permitted dynamic metadata.
12. **Write a POST contract with dynamic request `clientRequestId`**; inspect the converted WireMock mapping and run consumer tests via Stub Runner.
13. **Have the client call the wrong path**, observe WireMock 404 no-match, and distinguish it from a business 404 error contract.
14. **Package a new `stubs` artifact version**, inspect the JAR/mapping, and ensure consumer tests use the exact new version rather than a stale local cache entry.
15. **Add a messaging contract** with `eventId` and `eventType` header; if using a custom messaging adapter, confirm the payload is not wrapped in an unintended envelope that shifts JSONPath's root.
16. **Write a short summary**: source matcher, generated assertion, actual request/response, root cause, and fix; enforce it in the CI gate.

**Pass criteria:** learners can **separate DSL escaping, generated code, JSONPath path/result types, regex engine, stub request matchers, and consumer decoding**, fix at the exact source, prove a valid case **PASSES** and a contract-breaking change **FAILS**, without bypassing producer verification to force a green build.

## 28. Self-Check Questions

1. Which escaping layers can a regex pass through from Groovy DSL to the Java regex engine?
2. Why is `[0-9]{4}` often easier to work with than `\d{4}` when debugging Groovy/YAML DSL?
3. How do YAML single quotes and double quotes differ in handling backslashes?
4. How does `Pattern.matcher(...).matches()` differ from `find()`?
5. Why can regex `ORD-[0-9]+` be too loose when exactly four digits are required?
6. Can `byRegex('[0-9]+')` alone prove `amountMinor` is a JSON number?
7. How does `$.metadata.trace.id` differ from `$['metadata']['trace.id']` when the key is `trace.id`?
8. What type does `$.items[0].sku` return, versus `$.items[*].sku`?
9. Does a JSONPath filter selecting items with `quantity > 0` prove every item is positive?
10. Are missing, JSON `null`, and empty string always equivalent?
11. When a JSON parser returns `Long` while the expected matcher uses `Integer`, what should you inspect?
12. Why must generated producer test code be read when the DSL matcher looks fine?
13. Why should you never hand-edit generated test code?
14. How do `request.bodyMatchers` and `response.bodyMatchers` differ in their impact on stubs/tests?
15. Why does a WireMock 404 not prove the producer defines a business 404 error?
16. After editing the source contract while Stub Runner still behaves wrongly, why inspect JAR version/checksum?
17. If the actual response is an HTML error page, will editing JSONPath fix it?
18. For an ordered array, why avoid an order-ignoring matcher?
19. Does a timestamp shape regex prove a timestamp is calendar-valid?
20. For messaging contracts, should JSONPath target the payload or an adapter's internal envelope?
21. After loosening a matcher so tests pass, which mutations should you test to confirm regressions are still caught?
22. What artifacts/metadata must CI store to reproduce a post-generation failure?

## 29. Desk-Side Debugging Checklist

| Check | Question to Answer |
| --- | --- |
| **Contract source** | Is it the right Groovy/YAML file and right `bodyMatchers` scope? |
| **Parser** | Did DSL/YAML parse cleanly with quotes/backslashes right for that layer? |
| **Generator** | Are generated test sources/mappings the latest rather than stale output? |
| **Literal** | Do generated JSONPath/regex patterns preserve original intent? |
| **JSON type** | Does JSONPath yield String, Number, Boolean, Null, Map, or List? |
| **JSONPath result** | Does the path exist with the right root and bracket notation? |
| **Regex semantics** | Full match vs substring, anchors/flags/character classes right? |
| **Business rules** | Are exact, type, regex, and invariants chosen at the right strictness? |
| **Generated tests** | Did tests compile, get discovered by the runner, and execute? |
| **Stub mapping** | Are request method/path/header/body matchers accurate and strict enough? |
| **Stub artifact** | Are Maven coordinates, classifier, version, and checksum exact? |
| **Consumer client** | Does it send the real request properly and parse the response? |
| **Messaging adapter** | Does it alter envelopes, serializers, or header types? |
| **CI evidence** | Are test reports, source SHA, plugin version, and reproducible FAIL cases captured? |

**Key takeaway:** **A regex or JSONPath that “looks right on paper” is only truly right once it survives the DSL parser, generated source, matcher runtime, and stub mapping with its meaning intact.** With Spring Cloud Contract, keep **WireMock request matchers** separate from **producer verification response matchers**, verify regex escaping across Groovy/YAML/Java layers, test JSONPath against real JSON, and distinguish scalars from lists, missing from `null`, and numbers from strings. When things fail, read the **generated test code and mappings from the active `stubs` artifact**, fix the **source contract** rather than generated outputs, and run both producer and consumer tests. Valid changes should **PASS** and breaking changes must **FAIL**—that is the real proof of a trustworthy contract in CI/CD.
