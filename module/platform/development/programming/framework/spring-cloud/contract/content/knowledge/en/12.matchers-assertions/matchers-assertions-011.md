# Escaping Regex Across DSL, JSON, and Java Layers

## Lesson Objectives

**Spring Cloud Contract** uses **Groovy DSL** or **YAML DSL** contracts to describe HTTP or messaging behavior between a **producer** and a **consumer**. From a contract, the tooling can generate producer-side tests, package stubs for consumers to run via **Stub Runner**, and integrate checks into CI to detect incompatible API changes.

When data varies while conforming to a format, we commonly use **regular expressions (regex)** in matchers. A very frequent mistake is a conceptually sound regex that is **under- or over-escaped** in Groovy, YAML, JSON, or generated Java files. The result can be parse errors, failing tests, or worse: stubs/tests matching incorrectly without anyone noticing.

After this lesson, you will be able to:

- Distinguish **the characters the regex engine must receive** from how they are written in each source string format.
- Convert the same pattern across Groovy DSL, YAML DSL, JSON strings, and Java string literals without doubling or dropping `\` characters.
- Write matchers with JSONPath for requests and responses and understand their role in stubs and producer tests.
- Spot error-prone cases: `\d`, `\.`, `\\`, `$`, GStrings, JSONPath, and regex inside nested JSON.
- Verify outcomes using positive/negative tests, inspecting generated tests/stubs, and running CI rather than looking solely at source code.

## 1. Fundamental Rule: One Regex Can Pass Through Multiple Representation Layers

Suppose an order code must look like **ORD-** followed by four digits, e.g., `ORD-2048`. The regex that the **regex engine** needs to receive is:

~~~regex
^ORD-\d{4}$
~~~

Meaning of each component:

| Component | Meaning |
| --- | --- |
| `^` | Start of string |
| `ORD-` | Fixed literal characters |
| `\d` | A digit according to regex engine rules |
| `{4}` | Repeat exactly four times |
| `$` | End of string |

In this pattern, `\` is **a regex character**. Yet when a regex is written inside a **string literal**, the host language itself may use `\` as an escape character. Therefore, authors must distinguish:

1. **Regex layer**: the regex engine must receive `^ORD-\d{4}$`.
2. **Source representation layer**: Groovy, YAML, JSON, or Java must produce that exact string.
3. **Code-generation layer**: Spring Cloud Contract converts the contract into generated tests/stubs, which may need to escape the string once more to produce valid target source code.
4. **Execution layer**: tests or stubs apply the final value to match inputs/outputs.

~~~mermaid
flowchart TD
    A["Business-meaningful regex"] --> B["String in Groovy DSL<br/>or YAML DSL"]
    B --> C["Spring Cloud Contract model"]
    C --> D["Generated Java test<br/>Java source string"]
    C --> E["Stub mapping<br/>JSON string"]
    D --> F["Regex engine or producer test assertion"]
    E --> G["Stub / Stub Runner matcher"]
~~~

**A backslash appearing twice in source code does not necessarily mean two backslashes in the final regex.** Always ask: *which layer* is this string currently at?

## 2. Quick Conversion Table for the Same Pattern

The same rule `^ORD-\d{4}$` is represented differently across layers:

| Where Written | Representation | Why |
| --- | --- | --- |
| Received by regex engine | `^ORD-\d{4}$` | Needs one `\` before `d` |
| Groovy **single-quoted** string | `'^ORD-\\d{4}$'` | Groovy processes `\\` to yield one `\` |
| Java string literal | `"^ORD-\\d{4}$"` | Java processes `\\` to yield one `\` |
| YAML **single-quoted** scalar | `'^ORD-\d{4}$'` | YAML single quotes do not use `\` for escaping |
| YAML **double-quoted** scalar | `"^ORD-\\d{4}$"` | YAML double quotes have their own escape rules |
| JSON string | `"^ORD-\\d{4}$"` | JSON requires `\\` to hold one `\` |

**Warning:** this table describes **strings with identical meaning after parsing**. It does not mean Spring Cloud Contract places all of them in the same locations or supports every matcher method in every version. Always inspect actual generated output.

### Counting `\` Characters Properly

Example using `\d`:

~~~text
Intended regex:           ^ORD-\d{4}$
Groovy single quote:      '^ORD-\\d{4}$'
YAML single quote:        '^ORD-\d{4}$'
YAML double quote:        "^ORD-\\d{4}$"
JSON string:              "^ORD-\\d{4}$"
Java string literal:      "^ORD-\\d{4}$"
~~~

When the Java compiler reads source `"^ORD-\\d{4}$"`, the runtime string value contains **one `\`**. The regex engine then interprets `\d` as the digit character class.

If Java source writes `"^ORD-\d{4}$"`, `\d` is not a valid Java string escape, so the code may fail to compile. In YAML double-quoted scalars, `"\d"` is likewise invalid for passing a backslash to regex.

## 3. Escaping in Groovy DSL: Single Quotes, Double Quotes, and Slashy Strings

Groovy supports several string syntaxes. In contracts, **single quotes** usually make regexes easier to read by avoiding accidental variable interpolation, though backslashes still follow Groovy escaping rules.

### 3.1. Groovy Single-Quoted Strings

~~~groovy
// String value after Groovy evaluates is ^ORD-\d{4}$
def orderIdPattern = '^ORD-\\d{4}$'
~~~

This snippet has **two `\` characters in source**, corresponding to **one `\` in the runtime string**. That is what the regex engine needs.

Another example: a literal dot in a version code.

~~~groovy
// Want to accept "v2.1", reject "v2x1":
def versionPattern = '^v\\d+\\.\\d+$'
~~~

In the final regex, `\.` matches a **literal dot**; using `.` alone lets the regex dot match any character. Two escaping layers interact here:

- `\\.` in Groovy source produces `\.` in the regex string.
- `\.` in the regex string tells the regex engine to match a literal period character.

### 3.2. Groovy Double-Quoted Strings and GStrings

~~~groovy
// Without variable interpolation, still yields a string with one backslash:
def pattern = "^ORD-\\d{4}$"
~~~

Groovy double quotes support **interpolation** when encountering `$` expressions. In regex, `$` is also the end-of-string anchor. Be extra careful writing complex expressions inside double-quoted strings, especially when symbols combine with variable names or curly braces.

To reduce confusion, prefer **single-quoted** strings for static regexes in Groovy contracts; if interpolation is genuinely used, ensure it is intentional and the final string matches the pattern agreed by consumer and producer.

### 3.3. Slashy Strings Are Not a Universal DSL Rule

Groovy also offers **slashy string** syntax:

~~~groovy
def pattern = /^\d{4}$/
~~~

Inside a slashy string, `\` before `d` can often be written closer to raw regex syntax. However, `/` may require escaping because it is the delimiter, and interpolation rules must be understood.

Furthermore, Spring Cloud Contract APIs may expect specific **strings** or **matcher types**. Do not assume a Groovy `Pattern` created via `~/.../` can directly replace a `regex(...)` call everywhere. For exercises and CI, using matcher syntax explicitly supported by the DSL is safer.

## 4. Escaping in YAML DSL: Single Quotes Differ from Double Quotes

YAML is often chosen to keep contracts readable as declarative data. However, quote style directly affects backslashes.

### 4.1. Single Quotes: Ideal for Static Regexes

~~~yaml
# A single backslash in YAML source is preserved verbatim:
value: '^ORD-\d{4}$'
~~~

In a YAML **single-quoted scalar**, backslash is not an escape character. The parsed string keeps **one `\`** before `d`. Writing `'^ORD-\\d{4}$'` in YAML single quotes yields **two `\` characters** before `d` after parsing. The regex engine may then interpret it differently—for example, matching a literal backslash rather than a digit.

To represent a literal single quote inside a YAML single-quoted string, YAML's own escape rule is **writing two single quotes**, not using a backslash:

~~~yaml
example: 'It''s a test value'
~~~

### 4.2. Double Quotes: Backslashes Must Be Escaped

~~~yaml
# Two backslashes in YAML source produce one backslash in the string:
value: "^ORD-\\d{4}$"
~~~

YAML double quotes enable escape sequences such as `\n` and `\t`. Thus, to pass `\d` to the regex engine, you must write `\\d`. A string like `"\d"` may cause the YAML parser to report an invalid escape error.

**Quick rule of thumb:** static regexes in YAML single quotes usually look closest to the expression to match; YAML double quotes align closely with JSON/Java in `\` counts.

### 4.3. Avoid Arbitrary Unquoted Scalars

A short pattern can sometimes be written as a YAML plain scalar, yet characters like `:`, `#`, spaces, or special syntax can cause YAML to interpret them structurally rather than as data. When authoring contracts with regexes, pick a **consistent quoting convention** to avoid subtle bugs.

## 5. JSON Strings Always Have JSON's Own Escaping Layer

If a regex is stored in JSON as a string field—such as a stub mapping file or matcher descriptor—it must obey JSON escaping.

~~~json
{
  "pattern": "^ORD-\\d{4}$"
}
~~~

When a JSON parser reads the snippet above, the **pattern** field's value becomes `^ORD-\d{4}$`. Seeing two backslashes in the JSON file is **correct**; do not jump to concluding the regex is double-escaped.

JSON distinguishes:

~~~json
{
  "regexWithDigit": "^ORD-\\d{4}$",
  "regexWithLiteralDot": "^v\\d+\\.\\d+$"
}
~~~

Where:

- `\\d` in **JSON source** becomes `\d` in the string received by the regex engine.
- `\\.` in JSON source becomes `\.`; the regex engine treats this as a literal dot.

**Never write a JSON string like this:**

~~~text
{"pattern":"^ORD-\d{4}$"}
~~~

Because JSON permits only specific escape sequences; `\d` is not a valid JSON escape. Any standards-compliant JSON parser will reject it.

### 5.1. When Regex Lives Inside JSON Generated by Java or Groovy

There can be an extra layer:

~~~text
Desired regex value:          ^ORD-\d{4}$
Java source string:           "^ORD-\\d{4}$"
JSON written by serializer:   {"pattern":"^ORD-\\d{4}$"}
Parsed JSON value:            ^ORD-\d{4}$
~~~

Do not manually **double backslashes an extra time** before passing a string to a standard JSON serializer: the serializer already handles JSON escaping. Pre-escaping manually leads to **double escaping**.

In Spring Cloud Contract, generated stub mappings are usually in JSON format. When inspecting generated mappings, distinguish **the text displayed in the file** from **the value the parser passes to the matcher**.

## 6. Generated Java Source: Seeing Two `\` Characters Is Not Automatically a Bug

Generated producer tests may be in Java. For example, a Java test can validate an ID format with regex like this:

~~~java
import java.util.regex.Pattern;

class OrderIdFormatExample {
    static boolean validOrderId(String value) {
        return value != null
                && Pattern.matches("^ORD-\\d{4}$", value);
    }
}
~~~

In Java source code, `"^ORD-\\d{4}$"` is the right way to create a pattern with **one `\`** before `d`. Never edit generated source to `"^ORD-\d{4}$"`: Java rejects that escape.

If Spring Cloud Contract generated test code shows more backslashes than you expected, verify:

1. Is this **Java source**, **JSON text**, or a **runtime string**?
2. What actual string is passed to the matcher?
3. Does the generated test actually pass positive examples and fail negative ones?

Do not hand-edit generated tests to "fix escaping." Those files are typically regenerated; the source to fix is the **DSL**, configuration, or matcher definition.

## 7. Comparing Three Easily Confused Regex Patterns

### 7.1. Digit `\d`

Goal: `ORD-0001` valid, `ORD-ABCD` invalid.

~~~text
Regex engine:    ^ORD-\d{4}$
Groovy source:   '^ORD-\\d{4}$'
YAML single:     '^ORD-\d{4}$'
YAML double:     "^ORD-\\d{4}$"
JSON string:     "^ORD-\\d{4}$"
Java source:     "^ORD-\\d{4}$"
~~~

### 7.2. Literal Dot `\.`

Goal: `v2.1` valid, `v2x1` invalid.

~~~text
Regex engine:    ^v\d+\.\d+$
Groovy source:   '^v\\d+\\.\\d+$'
YAML single:     '^v\d+\.\d+$'
YAML double:     "^v\\d+\\.\\d+$"
JSON string:     "^v\\d+\\.\\d+$"
Java source:     "^v\\d+\\.\\d+$"
~~~

Very common mistake: omitting `\` before the dot and writing `^v\d+.\d+$`. Then the dot acts as **any character** per regex rules, letting unintended values match.

### 7.3. Literal Backslash in Data

Goal: check a data string containing **one `\`** between `A` and `B`, such as a technical code `A\B`.

For the regex engine to match a **literal backslash**, the regex itself needs two backslashes:

~~~text
Data value:            A\B
Regex engine:          ^A\\B$
Groovy source:         '^A\\\\B$'
YAML single:           '^A\\B$'
YAML double:           "^A\\\\B$"
JSON string:           "^A\\\\B$"
Java source:           "^A\\\\B$"
~~~

Reason: the **regex layer** uses `\\` to match one literal backslash. Then Java/Groovy string literals or JSON/YAML double quotes must escape **each backslash** of the regex.

If the **JSON data itself** should contain the string `A\B` (not a regex), the JSON body must write:

~~~json
{"code": "A\\B"}
~~~

Do not confuse **escaping JSON data** with **escaping a pattern used to match JSON data**; those are two separate interpretation steps.

## 8. JSONPath and Regex Are Two Different Languages

In Spring Cloud Contract, a matcher typically combines **JSONPath to select a field** and **regex to check the field's value**.

Example JSON response:

~~~json
{
  "order": {
    "id": "ORD-2048",
    "version": "v2.1"
  }
}
~~~

Here:

- JSONPath `$.order.id` selects the **id** field.
- Regex `^ORD-\d{4}$` checks **id's value**.
- JSONPath `$.order.version` selects the **version** field.
- Regex `^v\d+\.\d+$` checks **version's value**.

JSONPath begins with `$`, yet `$` at the **end of a regex** means something else. Do not apply identical escaping rules to both:

| Symbol | In JSONPath | In Regex |
| --- | --- | --- |
| `$` | Root of the JSON document | End-of-string anchor (when placed appropriately) |
| `.` | Separates property levels, e.g., `$.order.id` | Matches any single character |
| `[0]` | Selects first array element | Character class in square brackets with different meaning |
| `\` | May relate to escaping in property names depending on JSONPath syntax | Regex escape |

Example:

~~~groovy
bodyMatchers {
    jsonPath('$.order.id', byRegex('^ORD-\\d{4}$'))
}
~~~

`jsonPath` takes **two strings with different roles**: a path selecting data location and a string expressing the match rule. Only the regex `'^ORD-\\d{4}$'` needs `\\d` because this is Groovy source.

## 9. Writing Request Matchers in Groovy DSL

Suppose a consumer calls POST /api/orders with a three-digit customer ID and an `orderCode` formatted like ORD-0001. We want producer tests to send a stable sample request while the stub accepts any valid codes.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with regex-validated identifiers"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: "CUS-101",
            orderCode: "ORD-2048",
            quantity: 2
        )
        bodyMatchers {
            jsonPath('$.customerId', byRegex('^CUS-\\d{3}$'))
            jsonPath('$.orderCode', byRegex('^ORD-\\d{4}$'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-2048", status: "CREATED")
    }
}
~~~

**Checks to verify:**

1. `\\` in Groovy source must reach the matcher as `\d`.
2. Producer test sends the sample request such as **CUS-101**, **ORD-2048**.
3. The stub uses the request matchers to recognize calls from the consumer.
4. Regex for customer ID does not verify that the customer exists; `quantity: 2` does not test all valid quantities.

If a matcher is too broad, the stub may return success for requests the real producer rejects. If a regex is mis-escaped, the stub may reject completely valid requests. Test with both **accepted** and **must-be-rejected** values.

## 10. Response Matchers in Groovy DSL

For responses, the consumer stub needs sample values for consumer processing, while producer tests validate actual returned data.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-2048"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-2048",
            status: "PAID"
        )
        bodyMatchers {
            jsonPath('$.orderId', byRegex('^ORD-\\d{4}$'))
        }
    }
}
~~~

Within response matchers, generated producer tests can verify that returned **orderId** satisfies the rule; the stub can still return a sample value like **ORD-2048**. Exact details of how the generator combines fixed body values, matchers, and two-sided constructs depend on version, so inspect generated tests and actual stub mappings.

If the producer uses dynamic UUID order IDs, use a matcher matching the **published format** or controlled ID fixtures rather than locking onto a production record. Nor does a regex prove the newly created ID exists in the database or can be queried afterward: that behavior needs additional tests.

## 11. YAML DSL Matchers: Watch Quoting When Converting from Groovy

The same `customerId` rule can be written in YAML DSL as:

~~~yaml
description: "Create order with properly formatted customer ID"
name: create_order_customer_pattern
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-101"
    quantity: 2
  matchers:
    body:
      - path: $.customerId
        type: by_regex
        value: '^CUS-\d{3}$'
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-2048"
    status: CREATED
~~~

Here `value: '^CUS-\d{3}$'` is YAML **single-quoted**, so it preserves one backslash. If switching to YAML double quotes, write:

~~~yaml
value: "^CUS-\\d{3}$"
~~~

Across different Spring Cloud Contract versions/configurations, matcher capabilities and stub/test generation should be verified against actual DSL output; never just tweak `\` counts in source without observing the output.

**Note:** A YAML matcher using `by_regex` is a declarative data structure, not a Java string literal. Copying `'\\d'` verbatim from Groovy single quotes into YAML single quotes alters the string's content.

## 12. Escaping Mistakes Go Beyond Backslashes

### 12.1. Confusing JSONPath Dots with Regex Dots

~~~text
JSONPath: $.customer.email
Regex:    ^[^@]+@example\.test$
~~~

In JSONPath, dots separate object nesting levels. In regex, matching the literal dot in domain `example.test` requires `\.`. In a Groovy string, write `\\.`; in YAML single quotes, write `\.`.

### 12.2. Confusing `$` with GString Interpolation

Regex `^ORD-\d{4}$` ends with `$`. In Groovy double-quoted strings, `$` triggers interpolation when followed by matching expressions. Prefer **single quotes** for static regexes to avoid unintended GStrings.

If you truly need to interpolate dynamic parts into a regex, restrict the input, escape regex special characters in the interpolated data, and inspect the result. Never inject raw user input or environment variables directly into a regex without escaping, as their contents can alter pattern meaning.

### 12.3. Confusing Actual Newlines with Regex `\n`

When matching a **newline character**, distinguish:

- An actual newline character in data.
- A string containing two literal characters `\` and `n`.
- Writing `\n` in a regex vs. in a string literal.

JSON example:

~~~json
{"message":"First line\nSecond line"}
~~~

In a JSON file, `\n` represents **a single newline character after parsing**, not two literal characters in runtime data. If you need a literal backslash followed by `n`, JSON must contain `\\n`. That is distinct from a JSON string storing a **regex pattern** that checks for a newline.

### 12.4. Using Overly Powerful Regexes for Structured Data

JSONPath can select exact fields, so there is no need for a giant regex matching an entire serialized JSON payload. Full-body regexes easily break on key ordering, whitespace, and serialization style. Model JSON as maps/objects and place matchers on the specific fields that need flexibility.

## 13. Common Errors When Translating Between DSL and Java/JSON

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| Generated Java test fails to compile | Invalid escape leaked into Java string literal | Inspect DSL source and generated Java source; never hand-edit generated files |
| YAML parser reports unknown escape | Used `"\d"` inside YAML double quotes | Use `"\\d"` or `'\d'` |
| Stub does not match `ORD-1234` | Regex was over-escaped and may match literal backslashes | Check JSON mapping and run positive/negative requests |
| Stub accepts `v2x1` instead of only `v2.1` | Missing `\` before regex dot | Use `\.` at regex engine; escape per source language |
| JSON mapping fails to parse | JSON contains invalid escape like `\d` | Write `\\d` in JSON source |
| Groovy contract yields different output across CI runs | Interpolation or environment dependency creates dynamic pattern | Use stable constants/matchers and review final strings |
| JSONPath fails to find field | Wrong nesting level or confused with regex | Verify JSONPath and sample body separately |
| Tests still PASS with invalid data | Overly broad matcher or missing negative assertions | Add non-matching examples |
| Consumer test PASSES yet producer broke API | Consumer still uses stale stub artifact | Pin versions/revisions and re-test against new stubs |

**Merely counting `\` characters in a stub file is not enough to declare a bug.** You must know whether the file is JSON source, Java source, a Groovy string, or an already-parsed value.

## 14. Testing Regexes with Positive and Negative Examples

A solid pattern cleanly separates accepted from rejected inputs. For `^ORD-\d{4}$`:

| Value | Expected | Why |
| --- | --- | --- |
| `ORD-2048` | Match | Exact prefix and four digits |
| `ORD-0001` | Match | Leading zeros permitted if format allows |
| `ORD-123` | No match | Missing one digit |
| `ORD-12345` | No match | One extra digit |
| `ORD-ABCD` | No match | Letters instead of digits |
| `XORD-2048` | No match | Extra leading character |
| `ORD-2048X` | No match | Extra trailing character |
| `ORD-\d{4}` | No match | Literal characters, not a valid order code |

The Java snippet below illustrates **testing the regex itself** before putting it into a contract:

~~~java
import java.util.regex.Pattern;

public class OrderIdRegexExample {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile("^ORD-\\d{4}$");
        String[] valid = {"ORD-2048", "ORD-0001"};
        String[] invalid = {
            "ORD-123", "ORD-12345", "ORD-ABCD",
            "XORD-2048", "ORD-2048X", "ORD-\\d{4}"
        };

        for (String value : valid) {
            if (!pattern.matcher(value).matches()) {
                throw new AssertionError("Must match: " + value);
            }
        }
        for (String value : invalid) {
            if (pattern.matcher(value).matches()) {
                throw new AssertionError("Must not match: " + value);
            }
        }
    }
}
~~~

This standalone Java example clarifies how a Java string passes a pattern to the regex engine. In a real project, put these checks in unit tests for custom matchers or contract/stub tests as appropriate.

**Note:** positive/negative regex checks **do not replace** running Spring Cloud Contract Verifier; they only prove the written pattern itself matches the chosen strings. Test/stub generation can introduce another escaping layer, and business rules may impose constraints beyond format.

## 15. Verifying in Both Producer Tests and Stub Runner

With Spring Cloud Contract, verify across the entire lifecycle:

1. **Contracts discovered:** Groovy/YAML is valid and located in the source directory scanned by the plugin.
2. **Code generated:** generated producer tests have valid Java strings and matchers are placed properly.
3. **Producer tests execute:** the producer app returns compliant responses; tests actually run without being skipped.
4. **Stub mappings accurate:** when mappings are JSON, strings may display more backslashes than the regex engine receives. Verify actual matching behavior.
5. **Consumer tests with Stub Runner:** valid requests match, malformed requests are rejected per stub scenarios/behavior, and the consumer handles responses accurately.
6. **Version and provenance:** stubs used by consumer tests must match the exact verified contract revision and producer build; avoid unpinned stale artifacts.

~~~mermaid
flowchart TD
    A["Regex in Groovy/YAML"] --> B["Generate tests/stubs"]
    B --> C{"Generated test compiles?"}
    C -->|No| X["BLOCK: inspect escaping"]
    C -->|Yes| D["Run producer tests"]
    D --> E{"PASS with expected test count?"}
    E -->|No| X
    E -->|Yes| F["Inspect stub mapping"]
    F --> G["Test positive/negative requests against stub"]
    G --> H{"Matcher accurate?"}
    H -->|No| X
    H -->|Yes| I["Consumer tests via Stub Runner"]
    I --> J["Record scoped compatibility evidence"]
~~~

**Never conclude "the regex works" solely because the build is green**: contracts might not have been discovered, tests might have been skipped, old stubs might still be in use, or no negative cases existed to catch an overly broad pattern.

For complex regexes, keep a few expected-match and expected-mismatch examples right next to the tests; focus on **interface semantics** rather than producer implementation internals.

## 16. Hands-on Exercises

### Exercise A — Representation Conversion

The regex engine needs the pattern `^CUS-\d{3}$`. Write the same pattern for:

1. Groovy single-quoted string.
2. YAML single-quoted scalar.
3. YAML double-quoted scalar.
4. JSON string.
5. Java string literal.

**Suggested Answer:**

~~~text
Groovy:      '^CUS-\\d{3}$'
YAML single: '^CUS-\d{3}$'
YAML double: "^CUS-\\d{3}$"
JSON:        "^CUS-\\d{3}$"
Java:        "^CUS-\\d{3}$"
~~~

### Exercise B — Spot the Escaping Bug

A YAML file contains:

~~~yaml
value: '^ORD-\\d{4}$'
~~~

The author wants to accept `ORD-2048` yet the stub does not match. Explain why the YAML **single-quoted** value above fails to produce the intended regex.

**Hint:** backslashes in YAML single quotes are not unescaped; `\\` stays two characters and the regex engine may interpret them as an escaped literal backslash. Fix it to `'^ORD-\d{4}$'`, then inspect the generated stub and run positive/negative examples.

### Exercise C — Dot in Version Codes

The consumer sends `v3.12`. Write a regex accepting only `v`, one or more digits, a literal dot, and one or more digits. Provide at least three strings that must not match.

**Hint:** regex engine pattern `^v\d+\.\d+$`. Strings `v3x12`, `v3`, and `v3.12x` must be rejected. When writing in Groovy, add escaping per Groovy string rules.

### Exercise D — JSONPath or Regex?

Body:

~~~json
{
  "customer": {"id": "CUS-101"},
  "items": [{"sku": "BOOK-001", "quantity": 2}]
}
~~~

Select JSONPaths to the customer ID and first SKU; apply regex only to the code formats, without using a regex to match the entire serialized JSON body.

**Hint:** `$.customer.id` and `$.items[0].sku` are the JSONPath expressions. Their syntax is not a regex; regex applies to the **values** selected by those paths.

### Exercise E — Positive and Negative Tests in CI

A team changes the order-code matcher from `^ORD-\d{4}$` to a broader expression and CI stays green. Propose a positive/negative input set and verification steps across generated tests, stub mappings, and consumer Stub Runner tests.

**Hint:** use the valid/invalid codes from Section 14, confirm tests are generated and executed, pin the new stub artifact, and check that the stub does not return success for malformed requests. Then evaluate whether the change widened the interface unexpectedly.

## 17. Checklist When Adding Regexes to Contracts

- [ ] Clearly wrote **what string the regex engine must receive** before choosing representation syntax.
- [ ] Distinguished Groovy single/double quotes, YAML single/double quotes, JSON strings, and Java string literals.
- [ ] For `\d`, `\.`, and `\\`, counted escaping layers accurately.
- [ ] Static regexes in Groovy avoid unintended GString interpolation.
- [ ] JSONPath is used to **select fields**, and regex is used to **check field values**.
- [ ] Avoided overly broad regexes or matching entire serialized JSON when structured object matching works.
- [ ] Included positive and negative examples covering allowed boundaries.
- [ ] Generated producer tests compile, execute, and verify intended scenarios.
- [ ] Stub mappings are verified by **parsed values** and real requests, not merely counting `\` characters.
- [ ] Consumer tests run through Stub Runner with pinned stub version and contract revision.
- [ ] Never skipped failing matcher tests to turn CI green; fixed the DSL or source configuration instead.
- [ ] Claimed compatibility only for the consumers, versions, and behaviors actually verified.

**Takeaway:** Regexes do not mysteriously "add extra escape layers" on their own; **every language hosting a regex has its own string rules**. For Spring Cloud Contract to generate accurate tests and stubs, first determine the pattern the regex engine must receive, write it cleanly for the Groovy/YAML/JSON/Java layer, and verify with positive/negative tests on both producer and consumer sides. That prevents matcher and assertion bugs from letting CI miss incompatible API changes.
