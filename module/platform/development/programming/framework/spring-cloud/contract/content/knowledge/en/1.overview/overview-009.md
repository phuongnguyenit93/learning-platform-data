# Bugs That Can Be Caught and Guarantees That Cannot Be Inferred

## 1. Understanding the True Scope of Contract Testing

In a multi-service system, a **producer** (provider) implements an API or emits messages; a **consumer** (caller/subscriber) sends requests, receives responses, or consumes those messages. Both sides are typically developed and released independently. A seemingly minor change in the producer, such as renaming a JSON field, can stop the consumer from working even while each side's unit tests remain green.

**Spring Cloud Contract** helps specify interactions expected by both sides using contracts written in **Groovy DSL or YAML DSL**. From a contract, the tool can generate tests to run against the producer and generate **stubs** simulating responses or messages for the consumer. **Stub Runner** lets the consumer use those stubs in integration tests; CI can block changes when corresponding tests fail.

A boundary to remember from the start:

> **A passing contract test run only proves that the tested implementation satisfies the interactions and conditions expressed, executed, and verified in the test suite at the time of execution.** It does not by itself prove that the entire API is correct, that all consumers are compatible, or that the deployed build outside the test environment works properly.

A contract is a **set of intentional expectations**, not an exhaustive description of every possible system state.

## 2. Example: A Change That Contract Tests Can Catch

Suppose an order service exposes an endpoint to fetch order details. The consumer needs the order ID, status, and HTTP status code to display the result. The team agrees on a Spring Cloud Contract in YAML:

~~~yaml
description: "Get a paid order"
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

The contract above describes **one concrete scenario**: upon receiving `GET /api/orders/42`, the producer must return HTTP 200, JSON content, and the stated values. During the build, Spring Cloud Contract can generate producer-side tests from this contract. When tests actually boot the required application components, send the request, and match the response, the following changes can fail the test:

- The endpoint changes to `/api/v2/orders/42` and the old path no longer returns the expected result.
- The producer returns `404` or `500` instead of `200` in the defined scenario.
- The producer renames `status` to `state`, removes `id`, or returns `CANCELLED` instead of `PAID`.
- The producer returns a different `Content-Type` than constrained in the contract.

Detection capability depends on **the generated assertions, test configuration, and how the application is booted**. If a field, header, or input scenario is omitted from the contract or not checked, you cannot assume drift in it will be caught.

For example, the contract above says **nothing** about `GET /api/orders/43`, a missing token scenario, or an unpaid order. Endpoint 42 passing tests tells you nothing about whether those other cases work or fail.

## 3. Categories of Bugs That Can Be Caught

| Bug Category | Example | Condition to Detect |
|---|---|---|
| Wrong HTTP route or method | Consumer expects `GET /api/orders/42`, producer drops old path | Contract declares exact request; producer test sends matching request |
| Wrong status code | Expected `200` but returns `404` | Contract specifies expected status and test asserts it |
| Wrong header or content type | Missing `Content-Type: application/json` | Header is included in asserted expectations |
| Wrong response structure or data | Remove `status`, rename `id`, return invalid value | Body and matchers are specific enough to constrain that property |
| Producer accepts requests differently | Changed query parameter, required header, or request body structure | Contract exists for the affected input and test exercises that scenario |
| Wrong message format | Changed payload field, header, or message type needed by consumer | Messaging contract exists and producer/consumer tests are configured and triggered properly |
| Consumer misuses agreed interface | Consumer fails to parse stub payload, calls wrong method or path | Consumer runs tests with the exact stub and asserts protected behavior |

When contracts are consumer-contributed or agreed upon by both sides, the listed changes can be caught **before deployment**, provided tests are wired into the pipeline and failures break the build. This is the core benefit: shortening the feedback loop when interfaces change.

However, the concrete outcome is not always "a change will be blocked." For example, adding an optional JSON field may be compatible with clients that ignore unknown fields, yet fail in a consumer using a strict deserializer. You must look at client expectations and actual tests; compatibility cannot be inferred merely from adding or removing a field.

## 4. Two Sides of Testing Prove Two Different Things

~~~mermaid
flowchart TB
    C["Agreed contract"] --> P["Generate producer-side tests"]
    C --> S["Generate stub"]
    P --> PT["Run tests against producer"]
    S --> SR["Stub Runner"]
    SR --> CT["Run tests against consumer"]
    PT --> PC["Catch drift between producer and contract"]
    CT --> CC["Catch consumer bugs when using simulated interface"]
~~~

**Producer-side tests** verify whether a specific implementation satisfies the declared requirements. If the producer changes a response against the contract and the relevant test runs, the test can fail. Tests only protect the request patterns, matchers, and scenarios they actually cover.

**Consumer-side tests with Stub Runner** run the consumer against a simulated service generated from the contract. This is useful for verifying API-calling logic, status handling, and deserialization without standing up a real producer. However, **a stub is simulated behavior from a contract version**, not an automatic snapshot of a running producer. A consumer passing against a stub is not enough to conclude that the current producer or the version serving production returns what the stub returns.

For example, the producer accidentally renames `status` to `state`. The consumer may **still pass** when using an old stub containing `status`. Producer tests covering the relevant contract will catch the drift, but only if executed successfully against the real producer source code and failures are not ignored. Both testing branches complement each other rather than replacing each other.

With **message contracts**, the principle is similar: tests can verify payloads, headers, and described emit or receive conditions. That does not guarantee the entire delivery path through a broker, topic/queue configuration, access permissions, delivery ordering, or retry mechanisms in a real environment, unless those factors are also tested separately.

## 5. Guarantees That Cannot Be Automatically Inferred

| Common Misconception | Why Contract Tests Are Not Enough | Additional Verification Needed |
|---|---|---|
| "Every endpoint is compatible" | Only requests and scenarios with contracts/tests are checked | API inventory, contract matrix by consumer and use case |
| "All inputs and error branches work" | One contract for a valid order does not cover bad input, nulls, pagination, or limits | Unit tests, integration tests, and contracts for key error cases |
| "Business logic is correct" | A properly formatted response can still miscalculate taxes, totals, entitlements, or state rules | Business logic and domain rule testing |
| "Data was persisted properly" | A matching response may be returned before a transaction fails | Integration tests with database, verifying side effects and transactions |
| "System is fast and stable enough" | Contracts do not measure load, latency, resource contention, retries, or timeouts at real scale | Performance, load, and resilience testing |
| "API is secure" | Valid JSON does not prove authentication, authorization, leak prevention, or secret protection | Security testing, authorization tests, and configuration reviews |
| "System works well after deploy" | Test environments may differ in DNS, networking, gateways, brokers, secrets, and production config | Smoke tests, end-to-end tests, and post-release monitoring |
| "All active consumers are protected" | Unlisted clients, older versions, or uncontracted clients may exist | Consumer registry, version management, and deprecation policies |
| "Deployed version matches tested version" | CI may test commit A while an environment runs artifact B or an old stub version | Bind contract/stub versions to builds, verify provenance and releases |
| "Changes with the same data type are compatible" | `amount: 100` can change meaning from dollars to cents; JSON shape stays identical | Semantic agreements, business tests, and change reviews |

The key point is that **structural compatibility does not equal semantic compatibility**. For example, a contract only constrains `total` to be a number; the producer returns the value in a different unit while still being a valid number. The test may not notice that the meaning changed. Rules about units, time zones, ordering, null handling, uniqueness, value bounds, and enum meanings must be documented explicitly and tested at the appropriate layer.

**Compatibility guarantees are also directional**: an old client calling a new producer is a different question from a new client calling an old producer. One green producer/consumer pair only represents the tested versions and scenarios. When multiple versions coexist, test the actual supported combinations.

## 6. Four Scenarios to Distinguish Real Signals from False Confidence

### Scenario A — Producer Drops a Field Used by Consumer

Consumer reads `response.status` to display order status. The contract includes `status`; the producer renames it to `state`.

- **Producer contract test:** can fail because the response differs from the contract.
- **Consumer test with old stub:** can stay green because the stub still returns `status`.
- **Conclusion:** you must run and require passing producer tests on the release commit; relying on consumer tests alone is insufficient.

### Scenario B — Producer Adds an Optional Field

Producer adds `promotionCode` to the JSON response while keeping existing fields unchanged.

- **Producer contract test:** usually should not fail if the contract and matchers allow extra fields.
- **Consumer test:** a lenient client works normally; a client forbidding unknown fields can fail.
- **Conclusion:** verify how consumers handle extended data. "Adding a field" does not automatically mean safe or breaking.

### Scenario C — API Has Valid Format but Wrong Semantics

Producer still returns `{ "id": 42, "status": "PAID" }` even though the transaction has not actually been paid.

- **Contract test:** may pass because output matches the prepared fixture or because the contract does not verify database state.
- **Additional testing needed:** test payment workflow, state transitions, transactions, and reconciliation with real data.
- **Conclusion:** a contract is evidence about communication, not proof of business correctness.

### Scenario D — Stub and Artifact Are Not the Same Version

Consumer tests against stub `1.4.0`; producer deploys version `1.5.0` with an unexpected change.

- **Consumer test:** can still pass against stub `1.4.0`.
- **Risk:** test results do not reflect the running producer build.
- **Conclusion:** manage stub/contract versions, run producer verification for the artifact intended for release, and test the consumer versions that require support.

## 7. Making Contract Tests a Useful CI Quality Gate

A practical workflow with Spring Cloud Contract can include these steps:

1. **Agree on expectations meaningful to consumers.** Describe requests, responses, or messages for key flows; choose appropriate fixed values and matchers. For variable fields such as IDs, timestamps, or transaction codes, set constraints strong enough to protect clients without tying tests to random data.
2. **Generate and run producer-side tests.** Configure the build so tests generated from Groovy/YAML DSL actually run against the producer implementation. Test failures must fail the CI job. When intentionally changing a contract, update the contract and implementation in the same review process.
3. **Generate and publish versioned stubs.** Publish stub artifacts from verified contracts. Preserve version traceability so consumers know which interface version they are testing against.
4. **Run consumer tests with Stub Runner.** The consumer calls the stub in realistic usage scenarios; assertions must verify how the client handles data, status codes, errors, and critical fields. Test against the stub versions matching your support policy.
5. **Block releases when verified incompatibility occurs.** Combine producer test results, required consumer tests, and artifact provenance checks. For systems with multiple versions, explicitly define the protected compatibility matrix.
6. **Keep other testing layers.** Add unit tests for business logic, integration tests for databases/brokers, end-to-end tests for service chains, plus security, load, and operational observability checks.

**Example CI gate:** a pull request renames `status` to `state`. If the contract still requires `status`, producer tests fail and CI blocks merging or releasing. If this change is intentional, teams must agree on a migration strategy: keep the old field during a compatibility window, add the new field, upgrade relevant consumers, and only remove the old field after verifying no client still needs it.

A pipeline that only **generates** tests or stub artifacts without **running** tests, catching failure states, or tying releases to verified builds creates an illusion of protection without the matching evidence.

## 8. Checklist for Interpreting a "PASS" Result

Before declaring an API change safe, answer these questions:

- **Which consumer, which interaction, and which version** does this contract protect?
- Have all critical requests, responses, messages, headers, data fields, values, and matchers been described?
- Were the tests generated from contracts **run against the exact producer/artifact** about to be released? Do discrepancies actually fail CI?
- Has the consumer tested API calls and data deserialization against **the right stub version**?
- Are there negative cases (4xx/5xx), missing data, boundary data, timeouts, or asynchronous interactions left untested?
- Where are risks outside interface shape—business rules, data, security, load, brokers, networking, deployment—being verified?

When any question lacks evidence, report accurately **what was actually verified** instead of broadly claiming "100% API compatibility."

## 9. Key Takeaways

Spring Cloud Contract is most valuable when contracts accurately express what consumers need, producer tests run in CI, and consumers test realistic behavior against versioned stubs. This mechanism catches many **HTTP and message interface** bugs early, especially changes that drift the producer away from the agreed contract.

A green result is **bounded evidence** for the verified interactions. It does not automatically extend to guarantees about full business behavior, performance, security, deployment environments, every client, or every live version. Clearly defining that boundary helps teams use contract tests in their proper role within a multi-layered testing strategy.
