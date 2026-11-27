# Anonymizing Data and Eliminating Production Information

## Lesson Objectives

In **Spring Cloud Contract**, Groovy/YAML DSL contracts describe HTTP or messaging behavior between **producer** and **consumer**. From these contracts, the system generates producer-side tests, builds stubs for the consumer to use via **Stub Runner**, and runs CI checks before releasing API changes.

Contracts, sample data, generated tests, stubs, and logs can appear across multiple repositories, artifact repositories, and execution environments. Copying raw production payloads as examples can leak personal data, tokens, business data, or internal identifiers into places that are not authorized to store them.

Therefore, a good contract must **preserve the exact meaning and data formats the consumer needs** while **containing no real production data**. This topic is part of the **Contract Data** chapter and spans the lifecycle of producer tests, stubs, Stub Runner, and CI.

After this lesson, you will be able to:

- Identify categories of data that must never appear in contracts, fixtures, or stubs.
- Distinguish **anonymized**, **pseudonymized**, **masked/redacted**, and **synthetic** data.
- Write HTTP and message contracts with safe sample values while still verifying schemas, types, and behavior.
- Choose matchers to verify formats or types instead of hardcoding sensitive identifiers.
- Establish review workflows to keep production information out of source control, generated tests, stub JARs, and CI logs.
- Understand the limits of using tests/stubs to prove API compatibility.

## 1. Why Must Contract Data Be Controlled?

An example used in a lesson or test can outlive a single test run:

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts<br/>in repository"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Generated stubs"]
    C --> E["Producer CI logs and reports"]
    D --> F["Stub artifact repository"]
    F --> G["Consumer uses Stub Runner"]
    G --> H["Consumer test logs / CI artifacts"]
~~~

If a real email, phone number, address, token, or order record is copied into a contract, it can persist inside generated sources, stub mappings, JARs, failure logs when matchers fail, CI caches, and artifacts downloaded onto consumer machines. **Deleting the value in one source file does not erase previously published copies.**

Data protection here serves two goals:

1. **Security and privacy:** prevent real data from appearing in docs, source control, artifacts, and logs with broader access than production systems.
2. **Test reliability:** create stable, readable, reproducible sample data rather than coupling contracts to customer accounts, databases, or expiring production tokens.

Keeping real data sometimes makes tests feel more “realistic”, yet usually ties them to uncontrolled state. Deliberately designed synthetic data protects privacy and yields far more stable test results.

## 2. What Information Must Stay Out of Contracts?

Before placing any value into Groovy/YAML DSL, separate the **API structure to verify** from **concrete values taken from a real environment**.

| Data category | Examples | Recommended handling |
| --- | --- | --- |
| Personally identifiable information | Real customer names, emails, phone numbers, shipping addresses | Replace with schema-compliant synthetic data |
| Real transaction data | Order IDs, totals, item details, or real customer histories | Create dedicated test orders, amounts, and items |
| Authentication secrets | API keys, access tokens, refresh tokens, passwords, session cookies, signing keys | Never store in contracts/stubs; supply test credentials securely when needed |
| Payment data | Real card numbers, sensitive payment info, identifiable payment records | Use test data supported by payment systems and follow organizational data policies |
| Non-public internal data | Production hostnames, admin URLs, real tenant IDs, internal IPs, private resource names | Use mock values or test environment configuration |
| Sensitive business data | Non-public pricing, customer-specific discounts, partner lists | Create synthetic business scenarios without reproducing confidential info |
| Public technical data | Field names, HTTP methods, error codes, data types, published enum values | Preserve verbatim when consumers depend on them |

For instance, a consumer may need to send JSON containing **customer.email**. The field name and email-format rule are part of the contract; **a specific real customer's email address is not**.

Likewise, public status names like **PAID**, **CANCELLED**, or error code **ORDER_NOT_FOUND** must not be changed arbitrarily if consumers rely on them. Anonymize **data values**, without breaking the **behavior and schema** under test.

## 3. How Do Anonymization, Pseudonymization, Masking, and Synthetic Data Differ?

These terms are often used interchangeably yet have distinct properties:

| Approach | Description | Key limitation to remember |
| --- | --- | --- |
| **Anonymization** | Transforms data so individuals can no longer be reasonably identified in context | Hard to achieve when remaining fields link to other datasets; changing names alone is not enough |
| **Pseudonymization** | Replaces identifiers with alternate codes, potentially with a lookup table or linking key | Data may still qualify as personal data if re-identification is possible |
| **Masking/redaction** | Obscures or strips parts of data, e.g., hiding tokens in logs | Remaining fields may remain identifiable; originals may exist elsewhere |
| **Synthetic data** | Generates fictional data matching desired rules and structures | Must verify values do not accidentally collide with real ones and cover required business cases |

In common contracts and stubs, **synthetic data created from scratch** is usually safer and cleaner than copying production JSON and redacting a few fields.

Example:

~~~json
{
  "customerId": "CUS-TEST-1001",
  "email": "buyer@example.test",
  "address": {
    "city": "Test City",
    "street": "Sample Street 1"
  },
  "orderId": "ORD-TEST-9001"
}
~~~

In this example:

- **CUS-TEST-1001** and **ORD-TEST-9001** are intentionally crafted test codes.
- **example.test** is a reserved test domain; emails will never route to a real customer inbox.
- The address is illustrative data, not drawn from any real delivery record.
- Field names, data types, and object structure still match the exact interface the consumer uses.

**Never assume data that looks “fake” is automatically non-sensitive.** An unsalted hash of a real email, for example, can still be reversed using common email lists. A record whose name was replaced yet retains real birthdate, address, and transaction history can still be linked back to an individual.

## 4. Choosing Contract Sample Data Without Copying Production Records

Suppose Checkout needs to create an order and verify the producer returns an order ID and status. An appropriate sample request:

~~~json
{
  "customer": {
    "id": "CUS-TEST-1001",
    "email": "buyer@example.test"
  },
  "items": [
    {
      "sku": "SKU-TEST-BOOK",
      "quantity": 2,
      "unitPrice": 15000
    }
  ],
  "delivery": {
    "city": "Test City",
    "method": "STANDARD"
  }
}
~~~

Sample response:

~~~json
{
  "orderId": "ORD-TEST-9001",
  "status": "CREATED",
  "totalAmount": 30000
}
~~~

To make examples useful as contract data, check:

1. **Format:** `customer.id` and `orderId` follow the published API identifier types and rules. If the production API allows only UUIDs, the fixture must use a valid synthetic UUID instead of an arbitrary string.
2. **Consistency:** two items at 15,000 each total 30,000 in this scenario. If tests check totals, the body must maintain coherent relationships.
3. **JSON types:** `quantity` and `totalAmount` are numbers, `email` is a string, `items` is an array.
4. **Reproducibility:** the same contract, fixture, and producer build produce the same test expectations.
5. **Data scope:** do not add full names, phone numbers, card numbers, or real addresses if the consumer does not rely on them.

When a contract requires UUID identifiers, you can use a **fixed synthetic UUID** conforming to the schema, such as:

~~~text
00000000-0000-4000-8000-000000000001
~~~

Never grab a UUID from a real record simply because it has the right format. Test data can be format-valid while remaining completely independent of production.

## 5. Groovy DSL HTTP Contract with Synthetic Data

In Spring Cloud Contract Groovy DSL, requests and responses can be declared directly using maps/lists:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with synthetic data"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            header("Accept", "application/json")
        }
        body(
            customer: [
                id: "CUS-TEST-1001",
                email: "buyer@example.test"
            ],
            items: [
                [sku: "SKU-TEST-BOOK", quantity: 2, unitPrice: 15000]
            ],
            delivery: [city: "Test City", method: "STANDARD"]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-TEST-9001",
            status: "CREATED",
            totalAmount: 30000
        )
    }
}
~~~

This contract needs no real tokens, real accounts, or production connections to express behavior. When the generated producer test runs, the **test environment** is responsible for preparing data and logic so the producer returns the declared response.

If the real producer generates random `orderId` values, enforcing exact **ORD-TEST-9001** may be too strict. Use a format-appropriate matcher or a fixture with a controllable ID mechanism; never call a production API to fetch a real ID to paste into the contract.

### Same behavior in YAML DSL

~~~yaml
description: "Create order with synthetic data"
name: create_order_with_synthetic_data
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customer:
      id: "CUS-TEST-1001"
      email: "buyer@example.test"
    items:
      - sku: "SKU-TEST-BOOK"
        quantity: 2
        unitPrice: 15000
    delivery:
      city: "Test City"
      method: STANDARD
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
    totalAmount: 30000
~~~

YAML DSL files must also be reviewed as a source of generated tests and stubs. A YAML file with no executable code can still **contain real production data** if an author pastes a live response into the body.

## 6. Using Matchers to Enforce Rules Without Pinning Sensitive IDs

Synthetic data satisfies producer tests, yet consumers may send many different valid values. A contract can describe **format rules** instead of matching one exact identifier.

Groovy DSL example for a request body:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customer: [id: "CUS-TEST-1001"],
            items: [[sku: "SKU-TEST-BOOK", quantity: 2]]
        )
        bodyMatchers {
            jsonPath('$.customer.id', byRegex('CUS-[A-Z0-9-]+'))
            jsonPath('$.items[0].quantity', byType())
        }
    }
    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-TEST-9001", status: "CREATED")
    }
}
~~~

This example uses common Spring Cloud Contract matchers; verify the exact syntax and generated stub mappings against **your project's DSL version**.

**Points to get right:**

- Sample value **CUS-TEST-1001** serves one reproducible test case.
- **byRegex(...)** expresses an input code pattern the stub can match. It **does not replace data anonymization**.
- **byType()** checks type; it does not prove quantity is greater than 0 or that the SKU exists.
- Response values can also be checked with suitable matchers when the producer generates dynamic IDs, depending on your DSL version and mechanism.
- Only use matchers on genuinely varying fields; overly loose constraints cause the stub to succeed on requests the real producer rejects.

Never pick a matcher merely to “hide” an identifier. **Contracts should contain synthetic data from the start**, and matchers should express the data rules the consumer relies on.

## 7. Preserving Structure and Data Relationships When Anonymizing

A common mistake is stripping sensitive details in a way that destroys business relationships.

For example, an event has `customerId` and `orderId`; the consumer uses `customerId` to join the event with a previously loaded profile. Replacing **every customerId with one identical string** can cause tests to miss customer mix-ups or key-collision bugs.

Instead, create distinct yet deterministic synthetic codes within the same scenario:

~~~json
{
  "customerId": "CUS-TEST-1001",
  "orders": [
    {"orderId": "ORD-TEST-9001", "customerId": "CUS-TEST-1001"},
    {"orderId": "ORD-TEST-9002", "customerId": "CUS-TEST-1001"}
  ]
}
~~~

If a scenario involves two customers, use two distinct synthetic codes. Cross-field links stay intact, with zero linkage to real identifiers.

When generating large fixtures, you can use a synthetic generator with a fixed seed and consistent rules. **A seed is not a data-protection mechanism** if the algorithm takes predictable real inputs; for contracts, build completely fictional datasets from scratch.

Principles to maintain:

| Principle | How to apply |
| --- | --- |
| Valid schema | Preserve fields, types, objects/arrays, and formats required by the API |
| Valid relationships | Link records using consistent synthetic IDs |
| Valid business boundaries | Represent min/max quantities, missing fields, and error states in dedicated scenarios |
| Non-identifiable | Avoid combining real attributes that could enable re-identification |
| Reproducible | Fixtures remain stable across test runs |
| Easy to review | Clear names like CUS-TEST, SKU-TEST, test addresses, and `.test` domains |

## 8. Keeping Authentication Secrets Out of DSLs and Stubs

An example that must never appear in a repository:

~~~yaml
# ANTI-PATTERN: do not put real token or password values in files.
request:
  headers:
    Authorization: "Bearer <TOKEN_FROM_PRODUCTION>"
~~~

Even when the producer requires an `Authorization` header, **real secret values** are not part of the published contract. Separate:

1. **Interface commitment:** verifying which authentication scheme an endpoint expects or how a specific claim/role affects the response.
2. **Test credential provisioning:** a dedicated test identity and credential issued by the test environment and managed through test infrastructure/secret stores when needed.
3. **Artifact protection:** never generate stub mappings, expected bodies, or logs containing real bearer tokens or session cookies.

For contracts testing only JSON shape and business responses, test at an appropriate layer with controlled mock authentication. When real authentication must be tested, add dedicated **security/integration tests** rather than placing production tokens in fixtures.

**Never print tokens** into logs on assertion failure. Logger and test-report redaction matters because headers can leak into stack traces, request dumps, or Stub Runner failure logs.

## 9. Message Payloads Also Need Production Data Removed

Message-based contracts carry the same sensitive-data risks as HTTP contracts. For instance, a consumer might only need to know which order was just paid and when the event occurred, without needing the buyer's name, phone number, or shipping address.

A minimal synthetic payload:

~~~json
{
  "eventType": "ORDER_PAID",
  "eventId": "EVT-TEST-0001",
  "orderId": "ORD-TEST-9001",
  "occurredAt": "2026-01-15T08:00:00Z"
}
~~~

Example **Groovy DSL** contract for a producer-emitted message:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Publish payment event with synthetic data"
    label "order_paid"

    input {
        triggeredBy("publishTestOrderPaid()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            eventId: "EVT-TEST-0001",
            orderId: "ORD-TEST-9001",
            occurredAt: "2026-01-15T08:00:00Z"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

This is an illustrative scenario: the producer test must provide **publishTestOrderPaid()** in the test context alongside an appropriate message verification mechanism. There is no need to emit a real production event to gather contract evidence.

When a consumer needs an email or customer code because the public interface requires it, test it using synthetic data. At the same time, consider **minimizing payloads**: do not include addresses, phone numbers, or payment info in an event simply because the producer happens to have them.

In messaging environments, sensitive info can also appear in **headers**, routing keys, message keys, trace metadata, and dead-letter queues. Redacting a single payload field may not be enough; inspect the entire message flow and test logs.

## 10. Anonymization Must Not Alter Contract Semantics

When replacing production data with test data, preserve the characteristics the consumer genuinely relies on:

| Must preserve | Can replace with synthetic data |
| --- | --- |
| HTTP method, URL, status code | Real record IDs in examples |
| Field names, nesting structure | Real emails/addresses/names |
| Published data types and formats | Specific transaction values and totals when the scenario does not pin them |
| Business-meaningful enum values | Customer names or phone numbers |
| Consistency rules across IDs in a scenario | Real tenant names or account codes |
| Error branches handled by the consumer | Error messages containing real customer details |

**Data type example:** if an API expects monetary amounts as integer minor units, do not turn them into text strings just to hide values. Keep the numeric type and use a meaningful synthetic amount.

**Datetime example:** if the consumer expects an ISO-8601 timestamp with timezone, use a fixed fake instant or format-compliant matcher; do not paste timestamps tied to real customer transaction histories.

**Error example:** if the consumer branches on error code **ORDER_NOT_FOUND**, preserve that code; there is no need to keep message prose that previously leaked real IDs or emails from production logs.

Anonymization is **not a reason to alter the API schema**. If producer and consumer rely on a sensitive field, use synthetic data for that field in tests; removing a field from the real interface must be evaluated as a separate contract change.

## 11. Common Anonymization Mistakes

### Changing only names while keeping other identifying attributes

For example, replacing “Buyer A” with “Test User” while keeping real birthdates, phone numbers, rare postal codes, or real transaction histories. Combining multiple attributes can still re-identify the original person.

**Fix:** build an independent synthetic dataset; drop unnecessary fields and evaluate linkability across remaining fields.

### Directly hashing real emails or phone numbers

Hashing is rarely synonymous with anonymization. Over predictable input spaces, attackers can test candidate values to recover the original. If a mapping table or linking key remains, the data may still count as pseudonymized.

**Fix:** do not start from real data when writing contracts. Generate synthetic IDs with the right format and zero mapping to real accounts.

### Using random values as contract data

Generating random UUIDs or timestamps when the plugin evaluates Groovy can cause a single contract revision to produce different tests/stubs on every run.

**Fix:** use fixed synthetic fixtures or matchers describing dynamic values; generate rule-based test data inside test setup when truly necessary.

### “Redacting” a token in one file while leaving it in logs/artifacts

Replacing a token with a dummy value in YAML does not purge tokens already stored in Git history, CI artifacts, caches, screenshots, or old test reports.

**Fix:** handle secret exposure according to your organization's incident process, including revoking/rotating secrets as needed, auditing where it propagated, and restricting access. Editing the source file is necessary, yet not the complete remedy.

### Using a single dummy value for every record

If every customer, order, or event uses the exact same `TEST` code, tests can miss entity-distinction bugs, duplicate keys, or one-to-many relationships.

**Fix:** create a distinct, consistent, reproducible set of synthetic identifiers.

## 12. Controls Across Each Stage of Spring Cloud Contract

Reviewing Groovy/YAML files alone is insufficient when the system also generates tests, builds stubs, stores artifacts, and runs CI.

~~~mermaid
flowchart TD
    A["Design synthetic fixtures"] --> B["Review Groovy/YAML"]
    B --> C["Generate tests and stubs"]
    C --> D["Run producer contract tests"]
    C --> E["Inspect stub artifact contents"]
    D --> F["Review logs/test reports"]
    E --> G["Publish verified stub"]
    G --> H["Consumer uses Stub Runner"]
    H --> I["Review consumer CI logs"]
    F --> J["Release decision within verified scope"]
    I --> J
~~~

| Stage | Control check |
| --- | --- |
| Authoring contracts | Sample data is synthetic; no production IDs/emails/tokens/addresses |
| Pull request review | Reviewers inspect bodies, headers, referenced fixtures, and data changes |
| Generating producer tests | Generated tests do not embed production data from DSL, helpers, or fixtures |
| Running producer tests | Tests use test databases and test identities; never access unauthorized production sources |
| Building stubs | Mappings/response files contain no secrets or real personal data |
| Publishing stubs | Artifact versions and checksums are traceable; only verified artifacts are published |
| Stub Runner & consumer CI | Tests use exact stub versions; logs redact headers and sensitive fields |
| Retention & cleanup | Artifacts/logs/history have appropriate access controls and retention limits |

**Especially for stubs:** a passing producer test run does not prove the stub was audited for sensitive data. Stubs can contain raw bodies and headers copied from contracts; inspect packaged contents directly or use automated artifact scanning.

## 13. Integrating Sensitive-Data Checks into CI

A reference CI pipeline might include:

1. Scan contract files, fixtures, and related diffs using a project-approved secret scanner.
2. Apply sensitive-data rules across request/response examples, message payloads, headers, and test files.
3. Generate producer tests and stubs from the exact revision.
4. Run generated producer tests; halt release on failure.
5. Scan the packaged stub artifact for tokens, production domains, and unwanted data.
6. Publish the versioned stub and run consumer tests with Stub Runner.
7. Archive test evidence, inspect published logs/artifacts, and claim compatibility only within the verified scope.

A **pseudocode** representation of a release gate:

~~~yaml
# Conceptual pipeline template, not a directly runnable CI configuration.
contract_security_gate:
  require:
    - reviewed_synthetic_fixtures
    - no_known_secrets_in_contracts
    - no_production_identifiers_in_contract_examples
    - producer_contract_tests_pass
    - stub_artifact_scanned
    - consumer_stub_tests_pass
    - logs_and_artifacts_access_reviewed
~~~

**Secret scanning does not automatically catch all personal data.** A real email can look like an example email, and a synthetic string can trigger a false-positive regex alert. Combine automated scanning with content reviews, synthetic-data conventions, and access controls.

Never print **discovered secret values** into scanner logs or PR reports. When a scanner flags an issue, report the issue category, file, line/location, and remediation workflow without echoing the sensitive literal.

### A CI failure mode to avoid

Producer CI builds a stub from a contract containing a real email address; consumer CI runs tests against that stub. Both pipelines PASS, yet the published artifact contains data that should never have been shared.

**Passing contract tests does not mean passing data governance.** Release gates must require all three simultaneously:

- Producer behavior matches the contract.
- Consumer properly handles stubs from the verified version.
- Contracts, fixtures, and artifacts do not leak production data beyond authorized boundaries.

## 14. Practice Scenarios

### Exercise A — Data classification

You are preparing a `POST /api/orders` contract. The sample request contains: real `customerId`, real email, `PAID` status, quantity `2`, database table name, API key, and total amount.

**Task:** classify which items must stay as interface rules, which must be replaced with synthetic data, and which must be excluded from the contract.

**Hint:** keep field names, types, public enum values, and business relationships; replace `customerId`/email/sample amounts with synthetic values; exclude API keys and internal table names if they are not part of the public interface.

### Exercise B — Relational fixture design

A consumer must process two orders for one customer and one order for another customer. Design three **synthetic** `orderId`s and two `customerId`s, preserving consistent one-to-many relationships across the fixture.

**Hint:** use names like `CUS-TEST-1001`, `CUS-TEST-1002`, and `ORD-TEST-9001`/`9002`/`9003`; assign the same customer ID to the two related orders and the second customer ID to the third order.

### Exercise C — Contract with dynamic identifiers

The producer generates dynamic `orderId` values so a contract expecting fixed **ORD-TEST-9001** fails; a teammate suggests grabbing a real `orderId` from production to record it.

**Task:** explain why that suggestion is inappropriate and how to fix the contract.

**Hint:** use an `orderId` format matcher if appropriate, or set up fixtures/tests with a controllable generator. Use synthetic data and verify the actual generated matcher mechanism; there is zero reason to pull IDs from production.

### Exercise D — Stub leaking data

A published stub JAR contains a real token in a mapping header. The source contract file has now been edited to replace the token with a test string.

**Task:** list remaining issues and propose actions before continuing releases.

**Hint:** audit where the exposed secret exists across artifact repositories, caches, logs, and downloads; execute secret revocation/rotation as needed; verify and republish a clean artifact. Editing source alone does not clean up old copies.

### Exercise E — Checking limits of evidence

Producer tests PASS with a body containing `customerId` `CUS-TEST-1001`. Stub Runner also returns a success response for that exact body.

**Task:** can you conclude every `customerId` is valid, or that all production data has been eliminated? What additional checks are needed?

**Hint:** no. One illustrative test verifies only the executed scenario. You need appropriate matchers/validation for input variants and independent checks across data, artifacts, and logs.

## 15. Checklist Before Saving and Publishing Contracts

- [ ] Every sample value's origin is verified; freshly created synthetic data is preferred.
- [ ] No real customer names, emails, addresses, phone numbers, or identifiers exist.
- [ ] No access tokens, API keys, passwords, session cookies, signing keys, or production credentials exist.
- [ ] No real transaction details, card numbers, or sensitive business data exist.
- [ ] Synthetic identifiers have valid, consistent formats and are clearly recognizable as test data.
- [ ] Field names, data types, JSON structures, enums, and public error codes remain accurate.
- [ ] Dynamic data has appropriate matchers or test setup without relying on production IDs or timestamps.
- [ ] Record relationships are tested with consistent synthetic fixtures.
- [ ] Headers, message payloads, metadata, fixtures, and error payloads are also reviewed.
- [ ] Generated producer tests actually run with appropriate test data.
- [ ] Packaged stub artifacts are inspected before publishing, not just DSL sources.
- [ ] Stub Runner and consumer CI use the exact verified stub version.
- [ ] Logs, CI artifacts, and access permissions are controlled; scanners never echo secrets.
- [ ] Any sensitive data exposed in artifacts/history is handled via incident procedures, not just by editing new files.
- [ ] Compatibility claims cover only behaviors, versions, and consumers backed by test results.

**Takeaway:** Spring Cloud Contract definitions must express **compatible behavior and data structures**, not copies of production records. Purpose-built synthetic data, reproducible fixtures, well-chosen matchers, and verification across generated tests/stubs/CI catch incompatible API changes early without introducing sensitive information into the contract lifecycle.
