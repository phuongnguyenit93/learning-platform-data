# Helper Functions and Expressions in Groovy DSL

## 1. Role of Helper Functions in Spring Cloud Contract

**Spring Cloud Contract** helps producers and consumers verify compatibility by describing HTTP or messaging behavior in contracts. When using **Groovy DSL**, you do not just write fixed values like `method 'GET'` or `status 200`; you also use **helper functions** and **expressions** to express rules:

- Which requests from the consumer are considered valid for the **stub** to return a result?
- Which exact values must the producer actually return, versus which only need to match a format?
- When JSON contains UUIDs, timestamps, or dynamically generated values, how do you avoid false test failures?
- When the response must echo request data, how can you express that relationship?
- When basic matchers are not enough, can you call a custom verification function from the generated test?

These rules work in two directions: **Spring Cloud Contract Verifier** generates producer verification tests and generates stubs (typically WireMock mappings for HTTP); **Stub Runner** brings stubs into the consumer's tests. Placing an expression on the wrong side can cause the stub to reject valid requests or cause the generated test to mischeck the producer's response.

This lesson belongs to the **Groovy DSL** chapter and focuses on common helpers, expression syntax, matcher selection principles, and easily confused scenarios. YAML DSL remains a valid choice in Spring Cloud Contract, though the `value()`, `$()`, `execute()`, and `fromRequest()` examples below target Groovy DSL.

## 2. Groovy DSL Skeleton and Foundational Helpers

A minimal HTTP contract can be written as follows:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return details of a paid order'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header 'Accept', 'application/json'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            currency: 'VND'
        )
    }
}
```

`Contract.make { ... }` creates a contract description; `request`, `response`, and `headers` are configuration blocks (Groovy *closures*). Calls like `method GET()`, `status OK()`, and `contentType(applicationJson())` are DSL helpers processed when the contract is compiled to generate tests and stubs.

| Group | Common Calls | Meaning and Notes |
|---|---|---|
| HTTP method | `GET()`, `POST()`, `PUT()`, `DELETE()`, or `method 'GET'` | Specifies the HTTP method; direct strings are also valid |
| URL | `url '/api/orders/42'`, `urlPath('/api/orders') { ... }` | `urlPath` lets you describe query parameters separately for easier review |
| Query | `queryParameters { parameter('page', 1) }` | Placed inside the URL/URL path closure when the contract uses query parameters |
| HTTP status | `OK()`, `NOT_FOUND()`, `status 201` | Helper returns the corresponding status code; raw integers are also valid |
| Header | `header('X-Client', 'checkout')` | Declares header and value to verify or return |
| Content type | `contentType(applicationJson())` | Shorthand for `Content-Type: application/json` |
| Body | `body(id: 42, state: 'PAID')` | Groovy map describing a JSON object |
| Metadata | `description '...'`, `name '...'`, `priority 1` | Expresses purpose, identifier, or stub selection priority when needed |

Groovy calls can be written with or without parentheses, such as `method 'GET'` and `method('GET')`. Pick a consistent style across the repository. `description` is documentation for readers, while `name` helps identify the test case; avoid overly generic names like `test1`.

### 2.1. Query Parameters: A Readable Example

```groovy
request {
    method GET()
    urlPath('/api/orders') {
        queryParameters {
            parameter('state', 'PAID')
            parameter('limit', 10)
        }
    }
}
```

With this structure, changing `limit` or adding filter criteria is reviewed right where query parameters are described. Only use flexible matchers when business logic allows multiple values; if the consumer actually sends `state=PAID`, checking that exact value is usually easier to maintain than an overly broad regex.

## 3. Dynamic Expressions: `value()` and `$()`

### 3.1. Two Sides of a Value

A key feature of Groovy DSL is that **a single field can be described differently for the consumer and the producer**:

```groovy
value(consumer(...), producer(...))
$(consumer(...), producer(...))

// Equivalent aliases:
$(c(...), p(...))
$(stub(...), test(...))
$(client(...), server(...))
```

Both `value(...)` and `$(...)` serve the same purpose. `c` is an alias for `consumer`; `p` is an alias for `producer`. The names `stub`/`test` remind you of the execution environment, though **the meaning of each value depends on whether it sits in `request` or `response`**.

| Location | Consumer / Stub Side | Producer / Test Side |
|---|---|---|
| **Request** | Request matching condition accepted by the stub, e.g., order ID regex | Concrete request value the generated test sends to the producer |
| **Response** | Concrete response value the stub returns to the consumer | Condition/assertion the generated test uses to verify the real response |

Why split the two sides? Suppose the consumer sends an order ID matching `ORD-[0-9]+`. The stub should accept any code matching that pattern, while the producer test still needs **one deterministic sample value** to prepare fixtures. Conversely, the producer may generate a random tracking code; the test only needs to verify it matches the expected format, while the stub still has to send a concrete sample value for the consumer to test with.

### 3.2. Request: Consumer Uses Regex, Producer Uses Sample Value

```groovy
request {
    method GET()
    url value(
        consumer(regex('/api/orders/[0-9]+')),
        producer('/api/orders/42')
    )
}
```

This produces two behaviors:

1. **The consumer-side stub** can accept `GET /api/orders/42`, `GET /api/orders/71`, etc., if the URL matches the regex.
2. **The producer-side test** sends `GET /api/orders/42` so the test setup has a concrete input for which it can prepare fixture data.

Do not interpret a consumer-side regex as requiring the producer to "auto-generate every possible URL." It is the stub's request-matching rule. The producer test only executes the concrete scenario generated by the DSL; to test business logic for other IDs, write separate scenarios.

**Watch stub consistency:** if the regex allows any ID while the response is hardcoded to order `42`, the stub may return order `42`'s data for a `/api/orders/71` request. Only widen matchers when the sample response remains valid for all accepted requests, or use `fromRequest()` or multiple scenarios to preserve the link between request ID and response data. In tests that require exact order matching, matching a specific ID is usually safer.

### 3.3. Response: Consumer Receives Sample Value, Producer Is Checked with Regex

```groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 42,
        state: 'PAID',
        trackingId: $(
            consumer('TRK-A1B2C3D4'),
            producer(regex('TRK-[A-Z0-9]{8}'))
        )
    )
}
```

The stub will return `trackingId: "TRK-A1B2C3D4"` so the consumer has predictable data. The generated producer test will accept codes like `TRK-9A8B7C6D` as long as they match the committed format. Meanwhile `state: 'PAID'` is a business value that must stay exact, so do not relax it to `.*`.

**Common trap:** swapping the two sides to `consumer(regex(...))` and `producer('TRK-A1B2C3D4')` inside a *response*. That forces the producer test to demand a fixed code while requiring the stub to synthesize a sample from a regex. Check the request/response table before picking sides.

## 4. Helpers for Regex and Data Types

### 4.1. `regex(...)`, `~/.../`, and Full-String Matching

Groovy DSL can use:

```groovy
regex('[A-Z]{3}-[0-9]{4}')

// Groovy Pattern syntax, e.g. for a path:
~/\/api\/orders\/[0-9]+/
```

Regexes can be placed in `consumer(...)`, `producer(...)`, or `byRegex(...)` depending on context. The matcher uses **full-string matching** in many places, so `[0-9]{3}` is not equivalent to "a string containing three digits anywhere." To match strings containing a substring, describe the full expected structure, while avoiding uncontrolled `.*`.

The difference between Groovy string types also matters:

- `'...'` is a plain string with no Groovy expression interpolation; well suited for most regexes and JSONPaths.
- `"..."` creates a GString and interpolates when it contains variables or expressions; useful when you truly need dynamic text, though error-prone with `$` characters.
- For JSONPaths like `'$.orderId'`, single quotes easily prevent accidental interpolation.
- Regexes containing slashes, backslashes, or special characters must have escaping verified for both **Groovy** and **regex**; they are two separate representation layers.

### 4.2. Built-in Pattern Helpers

Spring Cloud Contract provides many built-in regex generators:

| Helper | Purpose | Example Use Case |
|---|---|---|
| `onlyAlphaUnicode()`, `alphaNumeric()` | Alphabetic or alphanumeric strings | Display codes, reference codes |
| `number()`, `anInteger()`, `positiveInt()`, `aDouble()` | Numeric types | Quantities, numeric IDs, amounts |
| `anyBoolean()` | Boolean values | Result flags |
| `uuid()`, `uuid4()` | UUID format | Correlation IDs |
| `email()`, `hostname()`, `ipAddress()` | Common formats | Email, host/IP fields |
| `isoDate()`, `isoDateTime()`, `isoTime()`, `iso8601WithOffset()` | Dates and times | Timestamp fields |
| `nonEmpty()`, `nonBlank()` | Non-empty or non-whitespace-only strings | Required names/notes |

Beyond helpers returning **patterns**, there are utilities generating **dynamic values** prefixed with `any...`, such as `anyNumber()`, `anyInteger()`, `anyPositiveInt()`, `anyUuid()`, `anyDateTime()`, `anyNonBlankString()`, and `anyOf('PAID', 'PENDING')`. They help when the DSL needs to auto-generate an example matching a constraint.

```groovy
response {
    status OK()
    body(
        correlationId: $(anyUuid()),
        count: $(anyPositiveInt())
    )
}
```

In the example above, utility functions reduce manual regex writing. However, **accepting data does not equal business correctness**: if `state` may only be `PAID` or `PENDING`, never replace it with an arbitrary non-empty string.

### 4.3. Types When Using Regex

Inside `bodyMatchers`, a regex describes the expected value and can carry type information:

```groovy
bodyMatchers {
    jsonPath('$.count', byRegex(anInteger()).asInteger())
    jsonPath('$.totalAmount', byRegex(number()).asDouble())
    jsonPath('$.active', byRegex(anyBoolean()).asBooleanType())
}
```

Avoid using regexes that only check string shapes when the consumer relies on the **actual JSON type**. A JSON number and a JSON string containing digits can behave very differently on the client. For monetary amounts, types and value bounds (non-negative, precision, unit) must match business commitments.

### 4.4. Overly Broad vs. Overly Strict Matchers

| Field | Error-Prone Matcher | Better Matcher |
|---|---|---|
| `orderId` like `ORD-42` | `.*` | `ORD-[0-9]+` |
| `state` strictly `PAID` in a specific scenario | Any string | Fixed value `PAID` |
| `totalAmount` must be a positive integer | `[0-9]*` allowing empty string | `positiveInt()` or business-appropriate bounds |
| `trackingId` with 8 uppercase alphanumeric chars after prefix | Fixed sample value for producer test | `TRK-[A-Z0-9]{8}` |
| `createdAt` generated at runtime | Comparing exact timestamp every run | `byTimestamp()`/`isoDateTime()` matching committed format |

If relying on automatic **string generation from regex**, be mindful of the generator's limitations; in particular, avoid putting `^`/`$` in patterns used for automatic sample generation when your library version does not handle them reliably. The safest approach for critical scenarios is to specify a valid sample value explicitly and use a regex on the side that needs matching.

## 5. `bodyMatchers` and JSONPath Helpers

Placing matchers inline inside `body` is convenient for simple cases; when many properties need individual rules, `bodyMatchers` makes matching targets clearer. Crucially, the same `bodyMatchers` syntax plays different roles:

- Inside **`request`**, it describes **stub matchers** to distinguish incoming requests sent by the consumer to the stub.
- Inside **`response`**, it describes **test matchers** for the generated producer test to verify the real response.

### 5.1. Complete Example Using Matchers on Both Sides

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create order and return a formatted reference code'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2
        )
        bodyMatchers {
            // Stub accepts multiple customerIds matching the format.
            jsonPath('$.customerId', byRegex('C-[0-9]+').asString())
            jsonPath('$.quantity', byRegex(positiveInt()).asInteger())
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            state: 'CREATED',
            trackingId: 'TRK-A1B2C3D4',
            generatedAt: '2026-11-24T01:02:03'
        )
        bodyMatchers {
            jsonPath('$.state', byEquality())
            jsonPath('$.trackingId', byRegex('TRK-[A-Z0-9]{8}'))
            jsonPath('$.generatedAt', byTimestamp())
        }
    }
}
```

Point-by-point explanation:

1. The producer test still sends the sample request with `customerId = C-42` and `quantity = 2`. Producer fixtures must satisfy this input.
2. The stub can match `customerId` values conforming to `C-[0-9]+` and valid quantities per the matcher, rather than only one exact JSON payload.
3. `state` is verified with `byEquality()` because `CREATED` is the exact business outcome of this scenario.
4. `trackingId` is verified with a regex and `generatedAt` with a timestamp helper, allowing the producer to generate fresh values on each run.
5. The stub returns the recorded sample body values so the consumer can run repeatable tests.

### 5.2. Table of Common Matchers

| Matcher | Meaning | Usage |
|---|---|---|
| `byEquality()` | Equals the value described in the body | Business statuses, constants |
| `byRegex('...')` | Matches a regular expression | IDs, reference codes, structured strings |
| `byDate()` | Matches ISO date format supported by the verifier | `yyyy-MM-dd` |
| `byTime()` | Matches time format | Time of day |
| `byTimestamp()` | Matches timestamp in a supported format | Creation timestamps |
| `byType()` | Checks field type against sample value | Numbers, strings, lists/objects |
| `byType { minOccurrence(...); maxOccurrence(...) }` | Constrains element count in a collection context | Result lists |
| `byNull()` | Field has value null | When the API commits to JSON null |
| `byCommand('method($it)')` | Calls a custom verification helper in generated tests | Business conditions hard to express in regex |

**Support scope varies:** `byEquality`, `byRegex`, `byDate`, `byTime`, and `byTimestamp` work in request/response matchers according to verifier capabilities. Matchers like `byCommand` and `byNull` are intended for **producer response** verification; do not arbitrarily place them in requests expecting Stub Runner to execute Java code from the base test.

### 5.3. Checking Collection Type and Length

```groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        items: [
            [id: 42, state: 'PAID']
        ]
    )
    bodyMatchers {
        jsonPath('$.items', byType {
            minOccurrence(1)
            maxOccurrence(20)
        })
    }
}
```

`byType` infers the expected type from the sample value in `body`; for collections, the matcher can specify `minOccurrence` and `maxOccurrence`. When using JSONPath pointing into nested structures, understand how elements are flattened in the matcher engine so you do not assert the wrong size. If element-counting rules are particularly complex, use `byCommand` with a dedicated verification method.

**Distinguish null from missing fields:** `byNull()` represents the value `null`, which does not necessarily mean the property is completely absent. Confirm what behavior the consumer actually relies on before writing the matcher.

## 6. `optional()` and Optional Values

Sometimes an interface allows a field to be either present or absent. Groovy DSL provides the `optional(...)` helper:

```groovy
request {
    method POST()
    url '/api/customers'
    headers {
        contentType(applicationJson())
    }
    body(
        email: $(
            consumer(optional(regex(email()))),
            producer('demo@example.test')
        )
    )
}
```

`optional()` has a specific scope: **the stub side of a request** and **the test side of a response**. It represents an optional part in matching logic; do not assume that wrapping with `optional` automatically verifies every "JSON property completely absent" case per business intent. If "field present" and "field absent" lead to two distinct behaviors, consider splitting them into separate contracts for clear testing.

In this example, the producer test still uses the sample email `demo@example.test`. The producer test **does not automatically exercise both branches** (email present vs. absent); protecting both behaviors requires corresponding tests or scenarios.

## 7. Referencing Request Data in Responses with `fromRequest()`

When an API echoes part of a request or propagates a correlation ID from request to response, hardcoding the value in both places makes contracts brittle when editing data. `fromRequest()` expresses the **relationship between request and response**:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/echo'
        headers {
            contentType(applicationJson())
            header('X-Request-Id', 'req-123')
        }
        body(
            orderId: 42,
            action: 'CONFIRM'
        )
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: fromRequest().body('$.orderId'),
            requestId: fromRequest().header('X-Request-Id'),
            path: fromRequest().path()
        )
    }
}
```

In this scenario, the response must reflect the actual `orderId`, `X-Request-Id`, and path of the request. This is valuable for preventing the producer from returning mismatched reference data without tying the response to an independent literal.

| Function | Meaning |
|---|---|
| `fromRequest().url()` | Request URL including query parameters |
| `fromRequest().path()` | Path without query string |
| `fromRequest().path(index)` | A path segment by index |
| `fromRequest().query('key')` | First query value for `key` |
| `fromRequest().query('key', index)` | Query value by index when multiple values share the same name |
| `fromRequest().header('Header-Name')` | First header value for the matching name |
| `fromRequest().body()` | Entire request body |
| `fromRequest().body('$.field')` | Value extracted from JSON body via JSONPath |

On the HTTP stub side, this mechanism can be translated into **WireMock response templating**. When setting up the repository and Stub Runner, ensure the WireMock version and configuration are compatible with the generated templates. In YAML DSL, the equivalent mechanism typically uses Handlebars and corresponding helpers instead of calling `fromRequest()` directly.

## 8. `execute()` and `byCommand()`: Calling Methods in the Base Test

Regexes cannot express every constraint. For instance, an organization may have complex rules for pricing, access tokens, or payload signatures. In those cases, verification logic can live in the **generated test's base class** and be referenced from the DSL.

### 8.1. `byCommand()`: Verifying Values Received from the Producer

In the Groovy contract:

```groovy
response {
    status OK()
    body(
        totalAmount: 120000
    )
    bodyMatchers {
        jsonPath('$.totalAmount', byCommand('assertPositiveAmount($it)'))
    }
}
```

In the Java base test inherited by generated tests:

```java
public abstract class ContractVerifierBase {

    protected void assertPositiveAmount(Number value) {
        if (value == null || value.doubleValue() <= 0) {
            throw new AssertionError("totalAmount must be positive");
        }
    }
}
```

`$it` is a placeholder representing the value extracted via JSONPath in the generated test code; it is **not a Groovy variable you declare in the contract file**. Validate the input type in the helper, since JSONPath may pass a `String`, `Number`, `Map`, or `List` depending on the expression. The method in the base test must be accessible to generated tests; the snippet above illustrates only the validation logic and must be paired with proper HTTP/Spring setup.

Use `byCommand` only when verification genuinely requires custom logic. For a "positive number" check, type/regex matchers or simple assertions are usually easier to read; this example mainly illustrates how to invoke a function. Do not use custom methods to hide an overly complex contract.

### 8.2. `execute()`: Obtaining Test Data from a Custom Method

For a **request body** on the producer test side, you may need to fetch a prepared payload from the base class:

```groovy
request {
    method POST()
    url '/api/orders'
    headers {
        contentType(applicationJson())
    }
    body(
        $(consumer('{"customerId":"C-42"}'),
          producer(execute('contractRequestBody()')))
    )
}
```

`contractRequestBody()` is a method defined in the base test returning an appropriate payload for the HTTP request. `consumer(...)` supplies the sample data for the stub, while `producer(execute(...))` tells the generated test to call the corresponding method. For request bodies written this way, `execute` applies **to the entire body**, not just one part of it.

Do not concatenate strings with an `execute` call like `'Bearer ' + execute('token()')` expecting the DSL to stitch values together properly. If you need a dynamic Authorization header, have the method return the full header value and use `header('Authorization', execute('authorizationHeader()'))` where supported by the DSL.

Use custom helpers in moderation: contracts should show reviewers meaningful data, while the base test should hold only setup work or assertions that are awkward to express in the DSL.

## 9. Messaging Contracts Also Use Helpers and Expressions

Spring Cloud Contract does not check HTTP alone; systems using message brokers can describe **input** and **outputMessage**. Example illustrating a message emitted when an order is paid:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldPublishOrderPaid'
    label 'order_paid'

    input {
        triggeredBy('publishOrderPaid()')
    }

    outputMessage {
        sentTo('orders.paid')
        headers {
            header('eventType', 'OrderPaid')
        }
        body(
            orderId: 42,
            state: 'PAID',
            eventId: $(consumer('f26d1437-54a3-4f5b-9f81-2a7107c05441'),
                       producer(regex(uuid())))
        )
    }
}
```

In this example, `triggeredBy('publishOrderPaid()')` links the scenario to a trigger method on the test side; `sentTo('orders.paid')` identifies the channel/destination described in the contract. The UUID helper lets the producer generate valid IDs without pinning a single ID. The base test configuration and messaging framework determine how the test actually triggers, captures, and verifies the message.

The channel name `orders.paid` and method `publishOrderPaid()` are purely illustrative. Do not infer "exactly-once" delivery, ordering guarantees, or transactional delivery merely from a contract describing a message. Those properties must be designed and tested according to your system's specifics.

## 10. Common Mistakes When Writing Groovy DSL

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Stub only accepts one ID even though API allows many | Literal placed in consumer request, or missing regex | Use `consumer(regex(...))` in request; keep producer test value concrete |
| Producer test fails because timestamp/UUID differs each run | Literal placed in producer response | Use `producer(regex(...))` or response `bodyMatchers` with appropriate format |
| Consumer receives unexpected value from stub | Matcher placed instead of sample in consumer response | Provide a concrete sample `consumer('...')` |
| JSONPath cannot find field | Wrong path, wrong nesting level, or field absent | Inspect JSON body structure and `'$.field'` path |
| Regex matches one string but not a longer one | Library may enforce full-string matching | Describe pattern matching the entire expected input format |
| Generated test cannot call custom method | Wrong `baseClassForTests`, method name, or parameter type | Ensure method is declared and accessible from generated test class |
| `byNull()` does not express "property absent" | Confusing JSON null with missing field | Choose assertions/scenarios expressing exact consumer behavior |
| `optional()` does not test both branches | Mistaking an optional matcher for two executed tests | Add a separate contract for the absent case if business-critical |
| DSL runs but tests lack meaning | Using `.*` or `byType()` on everything | Strictly match values that drive consumer behavior |
| Groovy syntax error | Unintended `$` in GString, quote mismatch, regex escaping | Separate regex into clear literals, test contract generation/compilation in build |

A useful rule during review is to ask: **"From this contract, what causes the stub to accept or reject a request; what causes the producer test to pass or fail?"** If you cannot answer with a concrete example, rewrite the expression more clearly.

## 11. Synthesis Practice: Handling an API Change Scenario

**Requirement:** `checkout-service` calls `GET /api/orders/{id}`. The producer returns `state` (must be `PAID` in this scenario) and a dynamically generated `receiptId` formatted as `RCT-` followed by eight digits.

**Proposed contract:**

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Consumer retrieves receipt for a paid order'

    request {
        method GET()
        url '/api/orders/42'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            receiptId: $(
                consumer('RCT-00001234'),
                producer(regex('RCT-[0-9]{8}'))
            )
        )
    }
}
```

**How to verify the result:**

1. Run the generated producer contract test. The producer must return `200`, `id=42`, `state=PAID`, and a `receiptId` matching the pattern.
2. Package/publish the stub artifact for the producer version. Stub Runner serves the stub to the consumer and returns sample `RCT-00001234` when the request matches.
3. Consumer tests use the application's HTTP client to verify receipt display logic when `state=PAID` and consume `receiptId`.
4. Try changing the producer to return `receiptId: "invoice-123"`: the generated producer test must fail for violating the format.
5. Try changing `state` to `COMPLETED` while the consumer still depends on `PAID`: the generated producer test must also fail, even though the HTTP status is still `200`.

**Self-check questions:**

- If you change the request to `$(consumer(regex('/api/orders/[0-9]+')), producer('/api/orders/42'))`, what should you watch out for? — The stub may accept `/api/orders/71` while still returning the hardcoded body `id: 42`; narrow the matcher or bind the response to the request ID.
- If you change the response side to `producer('RCT-00001234')`, what is the risk? — The producer test gets locked to a fixed code even though the real system can validly generate other codes.
- Should `state` be changed to `producer(regex('.*'))`? — **No**; then the test stops catching changes to critical business values.

## 12. Checklist When Reviewing Helpers and Expressions

- [ ] Clearly separate stub input and producer test input in `request`.
- [ ] Clearly separate stub sample and producer assertion in `response`.
- [ ] Fixed business values use equality; dynamic data uses bounded matchers.
- [ ] Regexes match the whole expected value; JSON types and committed formats are not ignored.
- [ ] `bodyMatchers` are on the right side; `byCommand` is only used where appropriate generated producer tests exist.
- [ ] Producer fixtures align with literals in `request`.
- [ ] `fromRequest()` is used only when the response truly depends on request data.
- [ ] `execute()` has a matching method in the base test and is not concatenated incorrectly.
- [ ] Optional values have explicit test scenarios instead of relying solely on `optional()`.
- [ ] The build generates producer tests, packages stubs, and tests with Stub Runner in CI to detect incompatible APIs.

Groovy DSL helpers are only useful when they **accurately express the commitment to the consumer**. Writing contracts purposefully with `value()`, `$()`, regex, and JSONPath keeps tests resilient as dynamic producer data changes, while immediately alerting you when critical behaviors such as field names, error codes, data types, or business states change.

### References

- Spring Cloud Contract Reference, *Contract DSL*: https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html
- Spring Cloud Contract Reference, *Dynamic properties*: https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html
