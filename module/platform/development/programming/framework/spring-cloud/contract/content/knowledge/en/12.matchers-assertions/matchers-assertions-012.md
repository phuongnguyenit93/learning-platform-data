# Evaluating Generated Assertions Instead of Looking Only at the Source Contract

## Learning Objectives

In the **Matchers and Assertions** chapter of **Spring Cloud Contract**, contracts written in **Groovy/YAML DSL** serve as inputs for the tool to generate **producer-side tests** and **stubs** for the consumer to use with **Stub Runner**. However, looking at the DSL file and seeing rules that appear reasonable **is not enough** to conclude that generated assertions will catch the right bugs.

After this lesson, you will be able to:

- Distinguish **intent in the source contract**, **assertions in generated producer tests**, and **conditions in stub mappings**.
- Locate and read critical assertions covering HTTP status, headers, JSON bodies, data types, regexes, required fields, and lists.
- Explain why `byType()`, `byRegex(...)`, and exact matching have different bug-detection power.
- Recognize when tests can pass **falsely from a business perspective** because assertions are too loose, missing branches, or placed on the wrong side.
- Build a review checklist and CI gates ensuring the producer truly satisfies the contract while the consumer tests against the right stub.

## 1. Four Questions When Evaluating Contract Test Quality

Suppose **Catalog Service** is the producer of a product pricing API, and **Checkout Service** is the consumer using prices to calculate orders. The producer publishes:

~~~http
GET /api/prices/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "price": 125000,
  "currency": "VND",
  "updatedAt": "2026-01-15T08:30:00Z"
}
~~~

The Checkout team relies on:

1. `200 OK` for an existing SKU.
2. `sku` accurately reflects the requested product.
3. `price` is a number representing the amount in the unit published by the API.
4. `currency` is currency code `VND` in this example scenario.
5. `updatedAt` is a valid timestamp in the agreed format; its value may change on each update.

Now distinguish four questions:

| Question | Where to Look? | Why Does It Matter? |
|---|---|---|
| What behavior did the author *intend* to protect? | Groovy/YAML contract | Clarifies intent and fields the consumer relies on |
| Which assertions did the generator *produce*? | Generated producer test | Verifies status, headers, and real body are checked tightly enough |
| What will the stub *accept and return*? | WireMock mapping / stub artifact | Verifies the consumer can send the right request and receive the right sample response |
| Which tests did both sides *execute*? | Build logs and CI reports | Ensures producer and consumer tests actually ran on the same contract/stub version |

**You cannot treat "the DSL contains the `price` field" as proof that generated tests verified a positive price, matching currency, or cross-field relationships.** Read the generated assertions and compare them against business needs.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Generated producer test"]
    A --> C["Stub mapping / stub artifact"]
    B --> D{"Do assertions catch needed bugs?"}
    C --> E["Consumer test via Stub Runner"]
    D -->|Yes| F["Run against real producer in test environment"]
    D -->|Not yet| G["Fix DSL, matcher, or add tests"]
    G --> A
    F --> H{"Producer test passes?"}
    E --> I{"Consumer test passes with exact stub?"}
~~~

## 2. Write the Source Contract, Then Predict the Assertions

Example file `src/test/resources/contracts/prices/priceForSku101.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return price for SKU-101'

    request {
        method 'GET'
        url '/api/prices/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            price: 125000,
            currency: 'VND',
            updatedAt: '2026-01-15T08:30:00Z'
        )
        bodyMatchers {
            jsonPath('$.price', byType())
            jsonPath(
                '$.updatedAt',
                byRegex('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z')
            )
        }
    }
}
~~~

This is **an illustrative contract** for Spring Cloud Contract Groovy DSL. Depending on version, generator, and test mode settings, generated test code may differ in class names, HTTP invocation helpers, and assertion libraries. Yet the verification intent still comprises:

| Property | Value/Matcher in DSL | Expected Assertion Meaning |
|---|---|---|
| `status` | `200` | HTTP response must have status 200 |
| `Content-Type` | `application/json` | Response uses JSON |
| `sku` | `SKU-101` | Response value for this scenario must match the fixed sample |
| `currency` | `VND` | Producer must not unilaterally change currency code in this scenario |
| `price` | `byType()` | Producer must return a value whose **type** matches the sample body, not necessarily exact 125000 |
| `updatedAt` | `byRegex(...)` | Timestamp string must match the described UTC date-time regex |

Easy-to-miss detail: `byType()` on `price` checks **type**, without checking `price > 0`, price within a valid range, or discount formula accuracy. The timestamp regex above likewise checks **character structure** only; it does not prove an arbitrary date like `2026-19-99` is calendar-valid.

### Sample Values and Matchers Are Not the Same Thing

In the contract above, `price: 125000` serves as a useful **sample value** for stub generation. When declaring `jsonPath('$.price', byType())`, the generated producer test verifies the actual value by **data type** instead of forcing exact equality to `125000`.

Similarly, `updatedAt` has a stable sample value for the stub to return to the consumer, while the producer may return a different timestamp as long as it matches the regex. Do not conclude the producer must return exact `2026-01-15T08:30:00Z` merely because it appears in `body`; the matcher defines the actual constraint level.

## 3. Read Generated Producer Tests by Evidence, Not Guesswork

Once the producer project is configured with Spring Cloud Contract Verifier and the corresponding Maven/Gradle plugin, the build generates tests from the DSL. Common locations:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Exact paths, class names, generated test language, and test APIs depend on plugin version and configuration. Rely on **build logs and actual project artifacts** rather than checking only the path above and concluding "no tests exist."

### Reading Tests in Five Layers

When opening a generated test, look sequentially for:

1. **Setup and actual call:** how does the test boot the application, fake, or HTTP test mode? Is the `GET` request sent to `/api/prices/SKU-101`?
2. **Status assertion:** is `200` checked, or only the body?
3. **Header assertion:** are `Content-Type` and headers needed by the consumer checked?
4. **Body assertion:** is each field checked by equality, regex, type, or another way? Are JSONPaths accurate?
5. **Missing critical constraints:** does the test catch missing `price`, wrong currency code, negative price, or timestamps violating business rules?

### Pseudocode Illustrating What to Look For

The snippet below is **readable pseudocode**, not verbatim Java output from a specific generator version:

~~~text
GIVEN producer test environment is ready

WHEN
  GET /api/prices/SKU-101
  Accept: application/json

THEN
  assert HTTP status == 200
  assert Content-Type is compatible with application/json

  parse JSON response body
  assert $.sku == "SKU-101"
  assert $.currency == "VND"
  assert $.price has the type expected by the contract
  assert $.updatedAt matches "[0-9]{4}-[0-9]{2}-..."
~~~

**The single most important review check is confirming actual output performs these exact steps.** The generator may emit `RestAssuredMockMvc`, `RestAssured`, `WebTestClient`, or another tool; those wrappers do not change what must be verified.

Never edit generated test files to "fix" assertions: the next generation overwrites them. When assertions are missing or wrong, fix the **DSL, matchers, fixtures, or test-generation config**, regenerate, and re-read the output.

## 4. Comparing Assertion Types by Example

| Check Type | Goal | What It Catches | What It May Miss |
|---|---|---|---|
| Exact value match | `currency == "VND"` | Change from `VND` to `USD` | Currency usage on other endpoints |
| Type match | `price` is number | Producer returns string `"125000"` instead of number | Negative or wrong price that is still numeric |
| Regex | `reservationId` matches `RSV-[0-9]+` | Malformed ID | Well-formatted ID that does not exist or duplicates |
| JSONPath | `$.price` or `$.items[0].id` | Checks named path/field | Other fields or branches not described |
| HTTP status | `200`, `400`, `404` | Response returns unexpected status | Body holds wrong data while status is right |
| Header assertion | `Content-Type`, `Location` when promised | Missing or wrong critical header | Business values inside the body |
| XML XPath | An XML node or attribute | Wrong value at selected location | Other XML structure outside the XPath |
| Supplementary business test | `price >= 0`, cross-field relationships | Invariants simple matchers cannot express | Covers only tested scenarios |

From this table, the design rule is that **every assertion must tie directly to a specific consumer dependency**. Avoid hardcoding every dynamic value, and avoid replacing all comparisons with broad matchers like `.*`.

### Negative Price Case: An Example of "Green Yet Wrong"

Actual response:

~~~json
{
  "sku": "SKU-101",
  "price": -500,
  "currency": "VND",
  "updatedAt": "2026-01-15T08:30:00Z"
}
~~~

If the generated test checks only that `price` is a number via `byType()`, **-500 is still a number**. The test passes even though Checkout must never compute a negative order total.

This is a **gap at the assertion level**, not proof that Spring Cloud Contract "ignored" a declared requirement. Agree between producer and consumer that `price` is non-negative; then add the appropriate check in the contract if the DSL has a matcher expressing the constraint, or a **dedicated business test** for the invariant. Never assume `byType()` means "business-valid number."

### Invalid Calendar Date Timestamp Case

Response:

~~~json
{
  "updatedAt": "2026-19-99T08:30:00Z"
}
~~~

The regex `[0-9]{4}-[0-9]{2}-[0-9]{2}T...Z` **matches this text**. To prove valid time, use a date-time parser with matching rules or supplementary tests. Regex checks shape, not calendar or timezone semantics.

### JSON Type Change Case

Response:

~~~json
{
  "price": "125000",
  "currency": "VND"
}
~~~

`"125000"` is a string, distinct from the number `125000`. That can be a **breaking change** for a consumer deserializing into a numeric type. Therefore, when reviewing generated tests, verify assertions preserve the **JSON type** rather than only comparing text after coercion.

## 5. Checking Body Coverage: Missing Fields, Nulls, Arrays, and Objects

A JSON body may look similar to the fixture yet differ structurally in ways the consumer relies on.

### Missing Field Differs from Null Value

~~~json
{
  "sku": "SKU-101",
  "currency": "VND"
}
~~~

The response above **omits** the `price` key. Another response:

~~~json
{
  "sku": "SKU-101",
  "price": null,
  "currency": "VND"
}
~~~

Here `price` is present with JSON `null`. If the consumer requires a mandatory number, neither case meets its need. Read generated assertions to confirm required fields and value types are actually enforced, instead of assuming so just because `price` appears in the DSL.

### Empty Arrays and Shape Changes

Suppose `GET /api/prices` has a contract returning a list:

~~~json
[
  {
    "sku": "SKU-101",
    "price": 125000
  }
]
~~~

The consumer must distinguish:

- `[]`: empty list, usually a valid search result per agreed API.
- `{}`: empty object, **not** an array.
- `null`: JSON null, **not** an empty array.
- `{"items":[]}`: paginated/wrapped object, a **different shape** from a root array.

A matcher checking only `$[0].sku` for a populated case does not automatically protect the empty-list case. Write a dedicated contract for `200 []` if the consumer depends on that behavior. When **element count**, ordering, or per-element types must be verified, confirm the corresponding matchers/tests appear in generated output.

### Extra Fields and Key Ordering

Changing JSON object key order normally has no effect if the consumer parses JSON per standard rules. Adding optional fields can also be compatible **if** the consumer ignores unknown fields; however, consumers with strict deserializers may fail. Thus, never rely solely on green generated producer tests to declare a change compatible with **every** consumer.

## 6. Distinguishing Request-Side and Response-Side Assertions

In Spring Cloud Contract, not every matcher compiles into producer-side assertions in the same way.

Suppose a contract has dynamic `request.body.requestId` and dynamic `response.body.reservationId`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create reservation'

    request {
        method 'POST'
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            requestId: $(
                consumer(regex('REQ-[0-9]{4}')),
                producer('REQ-1001')
            ),
            sku: 'SKU-101'
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: $(
                consumer('RSV-1001'),
                producer(regex('RSV-[0-9]+'))
            ),
            accepted: true
        )
    }
}
~~~

Read **both sides** accurately:

| Location | Generated Producer Test | Stub Mapping for Consumer |
|---|---|---|
| `request.requestId` | **Sends** `REQ-1001` from `producer(...)` | **Matches** request ID against regex from `consumer(...)` |
| `response.reservationId` | **Asserts** response ID matches regex from `producer(...)` | **Returns** sample ID `RSV-1001` from `consumer(...)` |
| `response.accepted` | Checks boolean `true` | Returns boolean `true` |

This is a frequent source of confusion when reading DSL alone: **request matchers mainly govern how the stub matches requests**, while **response matchers mainly govern producer-side assertions**. To know whether a regex actually became a producer assertion, check where it was declared and inspect the generated test file.

### With YAML DSL

YAML expresses the corresponding intent using **sample values** in `body` and separate matchers:

~~~yaml
description: 'Create reservation'
request:
  method: POST
  url: '/api/reservations'
  headers:
    Content-Type: 'application/json'
  body:
    requestId: 'REQ-1001'
    sku: 'SKU-101'
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    accepted: true
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

Mapping to remember:

- `request.body.requestId` is the example **sent by the generated producer test**.
- `request.matchers.body` is the **matching rule used by the stub** for incoming consumer requests.
- `response.body.reservationId` is the example **returned by the stub**.
- `response.matchers.body` is the **rule the generated producer test asserts** against the real response.

Use the YAML schema of your active Spring Cloud Contract version; never paste Groovy matcher syntax directly into YAML.

## 7. Why Inspect Stub Mappings When This Lesson Focuses on Assertions?

Generated tests show what the producer is verified against; **stub mappings** show what examples the consumer actually receives. A contract can have sound assertions yet an unusable stub due to a wrong request matcher.

Illustrative WireMock mapping (**abbreviated for explanation, not required verbatim output from the generator**):

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "bodyPatterns": [
      {
        "matchesJsonPath": "$[?(@.requestId =~ /REQ-[0-9]{4}/)]"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "RSV-1001",
      "accepted": true
    }
  }
}
~~~

When cross-checking, ask:

1. Does the mapping **match** the real request the consumer sends?
2. Does the stub response include every field the consumer needs?
3. Is `accepted` a boolean or a string?
4. When multiple contracts share an endpoint, which mapping gets picked? Do request conditions overlap?
5. Was the stub in tests generated from **the exact contract revision just reviewed**?

If a mapping demands one fixed request ID while the consumer sends varying valid IDs, consumer tests may fail with "no matching stub mapping" even though the producer implementation is solid. Yet that is a **stub matcher** issue, not a producer response assertion issue. Inspecting both artifacts pinpoints exactly where to fix.

## 8. Identifying Overly Strict and Overly Loose Assertions

| Problem Type | Example | Consequence | Improvement |
|---|---|---|---|
| **Too strict** | Producer must return exact `updatedAt = 2026-01-15T08:30:00Z` | Tests fail on other valid timestamps | Format matcher, or fix clock if exact value is required |
| **Too strict** | Array forced to always have one element | Tests fail when valid data has more results | Assert cardinality per committed guarantee |
| **Too strict** | Space-by-space XML match when API makes no whitespace promise | Tests fail when serializer changes formatting | XPath with needed constraints |
| **Too loose** | Regex `.*` for error code | Permits empty or malformed error codes | Specific pattern or exact match on stable error code |
| **Too loose** | `byType()` on price without checking negative amounts | Test passes with `price=-500` | Test business invariants |
| **Too loose** | Asserting only status 200 | Wrong body fields/types slip through | Assert fields the consumer actually uses |
| **Missing branch** | Only success case exists | Leaves `404`, `400`, empty data untested | Add contracts per test matrix |
| **Wrong side** | ID regex put on stub response side instead of producer assertion | Stub lacks stable sample response value | Read and fix `consumer/producer` placement |

Contract quality lies in **accurate constraint levels**, not matcher quantity. Adding 20 unnecessary JSONPaths can bloat maintenance while still missing one behavior the consumer genuinely depends on.

## 9. Do Not Overlook Error Branches and Empty-Data Cases

The pricing API may also have two more cases:

### Non-Existent SKU

~~~http
GET /api/prices/SKU-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"PRICE_NOT_FOUND","message":"Price is unavailable"}
~~~

Groovy DSL can define a separate contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Price for non-existent SKU'
    request {
        method 'GET'
        url '/api/prices/SKU-404'
        headers {
            accept(applicationJson())
        }
    }
    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'PRICE_NOT_FOUND',
            message: 'Price is unavailable'
        )
    }
}
~~~

The corresponding generated test needs assertions for `404` and `code == "PRICE_NOT_FOUND"`, not just calling the endpoint and checking "got a response." If `message` may be localized or revised, both sides should decide whether to constrain it verbatim or check type/format only while keeping `code` stable.

### Empty Price List

Another API, `GET /api/prices?category=no-match`, if published as returning a list, may agree on:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

Inspect the generated test to confirm `200` **and an empty JSON array** are verified. `[]` differs from `{}`, `null`, the string `"[]"`, and `204 No Content`. If the consumer expects a list shape, changing shapes can break the client even while status remains 200.

**Why not merge everything into one contract?** Each scenario needs unambiguous request and response conditions so producer tests and stubs stay clear. The goal is protecting critical behavioral branches, not mechanically multiplying files.

## 10. Assessing Assertion Quality by Consumer Risk

When reviewing, start from **what action the consumer will perform**:

| Consumer Action | Risk When Producer Changes | Minimum Assertion to Consider |
|---|---|---|
| Compute order total | `price` disappears or turns into string | Field exists, correct numeric type |
| Display currency unit | Wrong `currency` code or mismatch with price | Check currency per convention and related semantic tests |
| Branch on "price found / not found" | Changes `404` to `200` with error body | Check status and error code |
| Store reservation reference | Malformed `reservationId` | Specific regex and verify stub sample value |
| Render empty list | `200 []` changes to `204` or `null` | Check status and list shape |
| Process `PriceChanged` message | Payload drops required field | Schema/critical-field assertions, test consumer handler |
| Parse timestamp | `updatedAt` changes format or timezone | Check format, type, and business parsing if needed |

Whether a change counts as a **breaking change** also depends on deployed consumers. Adding an optional field is usually safe for lenient parsers ignoring unknown fields, yet can break strict deserializers. A generated producer test proves only that the implementation fits the **new contract**, not automatically that the new contract stays compatible with all existing consumers.

## 11. A Repeatable Review Process for Generated Tests

### Step 1: Write Down Expectations Before Generating Tests

From the source contract and consumer needs, jot down a quick table:

~~~text
Contract: priceForSku101

Producer test must:
  - Send GET /api/prices/SKU-101, Accept: application/json
  - Assert HTTP status 200
  - Assert response Content-Type JSON
  - Assert sku is SKU-101
  - Assert currency is VND
  - Assert price has numeric type
  - Assert updatedAt matches published pattern

Consumer test with stub must:
  - Send exact HTTP request used by application
  - Parse sample response with price 125000, currency VND
  - Handle timestamp in agreed format
~~~

Writing expectations **before** inspecting output prevents reviewers from confusing "what the generator did" with "what they wanted it to do."

### Step 2: Generate and Run Producer-Side Tests

Reference Maven command if the module has plugins fully configured:

~~~bash
./mvnw verify
~~~

With Gradle, run the contract test generation and execution tasks provided by **your plugin version and project build**. Inspect logs to see which DSL files were read, which generated tests compiled, and which tests actually ran. A green build that discovered zero contracts is not test evidence.

### Step 3: Open the Actual Generated Tests

Do not stop at test counts. Read at least one representative test covering **fixed values**, **regexes**, **type matchers**, **error statuses**, and **lists** if present in your contracts.

Reading checklist:

- Does the test call the real producer in the test environment rather than calling a stub?
- Do request path, query, headers, and body match the scenario?
- Are status/header assertions sufficient?
- Do JSONPaths/XPaths point to the right locations?
- Do regexes and type matchers uphold consumer requirements?
- Which sensitive fields, data types, and business relationships remain unverified?
- Is any test disabled, skipped, or failing during setup?

### Step 4: Open the Actual Mapping / Stub Artifact

A common Maven layout:

~~~text
target/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
target/<artifactId>-<version>-stubs.jar
~~~

These are **example paths**; projects can customize output directories. Inspect request matchers, status, headers, and response JSON in the mapping; verify that the stub **was generated from the exact contract/revision** just reviewed.

### Step 5: Run Consumer Tests with Stub Runner

The consumer points its real client at the stub started by Stub Runner. For each critical branch, verify:

- Consumer sends requests matching the contract.
- Stub selects the right mapping without falling into another mapping.
- Consumer parses data and executes the expected business decision.
- Tests use **the exact candidate stub version**, not a stale version from the local Maven cache or artifact repository.

If producer tests pass while consumer tests fail, that may signal an incompatible change, an inaccurate stub mapping, or a consumer assumption never captured in the contract. Investigate root cause rather than merely editing expected values to force a pass.

### Step 6: Record Evidence in the Pull Request

Consider recording:

- DSL and fixture revision.
- Path/name of reviewed generated tests.
- Generated assertions for critical fields.
- Exact stub artifact: group, artifact, version, classifier/build ID.
- Which consumer tests ran against that artifact.
- Uncovered cases and follow-up plans.

## 12. Integrating Assertion Evaluation into CI

A pipeline can be structured as follows:

~~~mermaid
sequenceDiagram
    participant Dev as PR/Developer
    participant Gen as SCC Generator
    participant Prod as Producer tests
    participant Stub as Candidate stub
    participant Cons as Consumer tests
    Dev->>Gen: Update Groovy/YAML DSL
    Gen->>Prod: Generate contract tests
    Prod->>Prod: Run assertions against real implementation
    alt Producer test passes
        Gen->>Stub: Build stub at same revision
        Stub->>Cons: Stub Runner pulls exact artifact
        Cons->>Cons: Verify consumer logic
    else Producer test fails
        Prod-->>Dev: Block merge/release
    end
    Cons-->>Dev: Compatibility result
~~~

Beyond running tests, CI or reviewers should check these **quality gates**:

1. **Contracts discovered:** generator read the intended DSL files; never accept a green build caused by finding zero contracts.
2. **Generated tests not skipped:** assertions actually executed inside the job.
3. **Generated assertion diffs inspected on sensitive DSL changes:** especially when changing matchers, fields, statuses, types, or shapes.
4. **Valid fixtures and matchers:** neither overly rigid causing false failures nor overly loose missing behavior.
5. **Traceable stub versions:** consumer tests use the same candidate revision.
6. **Backward compatibility checked:** when altering meaning, removing fields, changing types, or changing HTTP status/message schemas, evaluate older consumers.

**You do not necessarily have to commit all generated tests to Git.** If the team does not commit generated code, preserve CI artifacts/logs and inspect them as needed. What is mandatory is being able to **inspect the assertions actually generated and executed**, rather than mechanically trusting file existence.

## 13. Exercise: Tests Are Green, Yet Which Assertions Are Missing?

### Problem

An API returns:

~~~json
{
  "sku": "SKU-101",
  "price": -1,
  "currency": "USD",
  "updatedAt": "2026-19-99T08:30:00Z"
}
~~~

The contract requires `sku=SKU-101`, `currency=VND`; `price` must be a **non-negative** number and `updatedAt` must be a valid instant per API standard.

A reviewer reads an abbreviated generated test and sees:

~~~text
assert HTTP status == 200
assert sku == "SKU-101"
assert price is of numeric type
assert updatedAt matches "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
~~~

**Questions:**

1. Which assertion can catch `price=-1`?
2. Is `currency=VND` being checked yet?
3. Does the timestamp regex automatically guarantee day `19`, `99` are valid?
4. If the consumer actually receives `USD` and computes money assuming VND, which tests must be added?
5. Should you just add `byRegex('.*')` to every field to reduce failing tests?

### Suggested Solution

1. **None yet.** `price` is numeric, so the type check still passes. Enforce the `price >= 0` business rule via a dedicated test or appropriate matcher.
2. **No.** The abbreviated generated test lacks an assertion for `currency`. If that field is genuinely missing in actual output, inspect the DSL or test-generation config to protect the currency code.
3. **No.** Regex checks only string *shape*; date-time validity must be verified according to calendar rules.
4. You need **producer contract tests** confirming published behavior and **consumer tests** confirming the client calculates/displays currency accurately; if conversion rules exist, add dedicated business tests.
5. **No.** Regex `.*` is overly broad and eliminates value-error detection. Loosen matchers only for contract-backed reasons.

### Extension Exercise: Spotting Wrong-Side Placement

In a Groovy contract for the reservation creation API:

~~~groovy
body(
    reservationId: $(
        consumer('RSV-1001'),
        producer(regex('RSV-[0-9]+'))
    )
)
~~~

Explain why the **generated producer test** should check the regex while the **stub response** should return `RSV-1001`. Then locate the corresponding sections in the generated test file and WireMock mapping of a sample project.

## 14. Quick Checklist Before Accepting Contract Changes

- [ ] Source contract explicitly states behaviors the consumer relies on.
- [ ] Generated tests are actually created and executed against the right producer implementation.
- [ ] Status, headers, and important body fields all have assertions.
- [ ] JSONPath/XPath and matchers are in the right place, on the right side, and check the right data types.
- [ ] Exact matching is used only when values genuinely must stay fixed.
- [ ] Regexes are tight enough; `byType()` is not mistaken for checking all business rules.
- [ ] Missing fields, nulls, array/object shapes, and empty data are evaluated per requirements.
- [ ] Important success and error branches have matching contracts/tests.
- [ ] Stub mappings do not overlap unexpectedly, and sample responses have accurate types.
- [ ] Consumer runs with Stub Runner against the exact generated stub version.
- [ ] CI preserves evidence of generated tests, candidate stubs, and consumer test results.
- [ ] Changes that could break existing consumers were reviewed with a migration plan.

## 15. Takeaways

**Evaluating contract tests must start from the assertions actually generated and executed, not stop at the source Groovy/YAML file.** A matcher may be syntactically valid yet overly loose, placed on the wrong side, or fail to protect an invariant the consumer relies on. Cross-check **DSL → generated producer test → stub mapping → consumer test with Stub Runner**, while verifying artifact versions in CI.

Spring Cloud Contract helps catch incompatible HTTP or messaging changes **within the scope of declared and executed scenarios**. Verification quality depends on choosing the right fields to constrain, applying sufficiently tight assertions, and actually reviewing generator output whenever contracts change.
