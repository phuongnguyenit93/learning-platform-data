# Limitations of Values Executed via Test-Side Code

## Lesson Objectives

In **Spring Cloud Contract**, an HTTP or message contract can be used to generate **producer-side tests** and **consumer-side stubs**. Groovy DSL supports defining two values for the same piece of data: one serving the consumer (client) side, and one serving the producer (server) side. Beyond fixed values and regular expressions, certain contexts also allow using **test-side code or methods** to verify dynamic values.

This capability is useful when a producer returns identifiers, timestamps, or data that cannot be compared against a fixed string. However, **code running in generated tests does not become behavior executed by the stub itself**, and test methods should not be used to recompute results using the very producer logic under verification.

After this lesson, you will be able to:

- Distinguish **client/consumer** and **server/producer** values in requests and responses.
- Identify when a value is verified by an expression, matcher, or test-provided method.
- Understand the scope and limitations of **execute(...)** and **byCommand(...)** in Groovy DSL.
- Organize test methods, fixtures, and base classes to verify dynamic values reproducibly.
- Recognize risks arising from stubs and generated tests checking different things.
- Combine producer tests, stubs, Stub Runner, and CI results into compatibility conclusions with a clear scope.

## 1. Why Does the Same Data Field Need Values on Both Sides?

Suppose Checkout sends an order creation request and Order Service returns a server-generated ID:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":"CUS-TEST-1001","quantity":2}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"ORD-4821","status":"CREATED"}
~~~

In production, **orderId** may change across calls. The consumer needs a valid sample ID to test the downstream flow, while the producer test needs to verify that the actual ID has the right shape or characteristics. Hardcoding every response to be **ORD-4821** can defeat the purpose of the test.

Spring Cloud Contract resolves this difference by allowing **two-sided values** in a contract. Two commonly seen names are:

- **consumer(...)**, which also has the client-perspective equivalent **client(...)**.
- **producer(...)**, which also has the server-perspective equivalent **server(...)**.

These helpers indicate **which side will use the value**, not where a Groovy method is immediately executed.

### Key Mapping Table

| Location in Contract | Consumer/Client-Side Value | Producer/Server-Side Value |
| --- | --- | --- |
| **Request** | Concrete data sent by the generated producer test | Request condition the stub uses to match consumer calls |
| **Response** | Data the stub returns to the consumer | Expectation or matcher the generated producer test uses to verify the real response |

This is the core understanding of two-sided values in Spring Cloud Contract. Because requests and responses travel in opposite directions, **the role of each value in generated tests and stubs also reverses**. Remembering only "consumer is always stub" or "producer is always test" without considering request/response makes mistakes very likely.

~~~mermaid
flowchart LR
    A["Two-sided contract"] --> B["Request"]
    A --> C["Response"]
    B --> D["consumer: input for producer test"]
    B --> E["producer: stub matcher"]
    C --> F["consumer: sample stub output"]
    C --> G["producer: response check in producer test"]
~~~

## 2. Two-Sided Value Example with a Dynamic Request

The consumer can send many customer IDs following a format. The producer test needs a specific ID to set up data, while the stub should not accept only a single customer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with formatted customer ID"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: value(
                consumer("CUS-TEST-1001"),
                producer(regex("CUS-[A-Z0-9-]+"))
            ),
            quantity: 2
        )
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

In the request context:

1. **The generated producer test** uses sample value CUS-TEST-1001. Test setup must prepare appropriate data or controlled behavior for the sample customer.
2. **The stub** can use the regular expression to match other codes of the same format.
3. A producer test passing with CUS-TEST-1001 **does not prove** the producer properly handles every string accepted by the regex.
4. A regex only checks ID shape; **it does not prove the customer exists or is authorized to place orders**.

When choosing a regex, avoid setting an overly broad condition just to make the stub match easily. If the real producer only accepts a narrower set of formats, the stub could accept requests that the real producer would reject.

### Two-Sided Values in YAML DSL

YAML DSL can also declare matching rules and dynamic values, though the structure is not identical to Groovy calls. For nested request data, one option is **request.matchers.body**:

~~~yaml
description: "Create order with formatted customer ID"
name: create_order_customer_pattern
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    quantity: 2
  matchers:
    body:
      - path: $.customerId
        type: by_regex
        value: "CUS-[A-Z0-9-]+"
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
~~~

This is an example of a **declarative matcher**. Do not assume a Groovy option like execute(...) can be rewritten with the exact same syntax in YAML. Verify features and syntax against your actual DSL version.

## 3. Dynamic Response: Stub Needs an Example, Producer Test Needs Verification

In the response, both sides have needs opposite to the request:

- The consumer test through the stub needs a **concrete** value to simulate the server.
- The generated producer test needs to verify the **actual value** produced by the producer.

Groovy DSL example with a response containing a dynamic ID:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(customerId: "CUS-TEST-1001", quantity: 2)
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: value(
                consumer("ORD-TEST-9001"),
                producer(regex("ORD-[A-Z0-9-]+"))
            ),
            status: "CREATED"
        )
    }
}
~~~

For the response:

- The stub can return **ORD-TEST-9001** to the consumer.
- The producer test verifies the actual ID matches the regex format; **it does not require** the server to always generate the same ID.
- The consumer test must verify application logic handling the returned ID; a test checking only that the stub endpoint returns 201 is insufficient.

This expression still has limits: a matching regex does not prove the newly generated code is **unique**, saved in the database, queryable later, or tied to the right customer. Those behaviors need other contracts/scenarios or suitable integration tests.

## 4. What Is a Value Executed via Test-Side Code?

When regexes and declarative matchers cannot express enough conditions, Spring Cloud Contract Groovy DSL can support **referencing test-side code calls**, commonly known through **execute(...)** or the **byCommand(...)** matcher in supported contexts.

Points to distinguish:

| Mechanism | What Is It Used For? | Where Execution Method Is Needed |
| --- | --- | --- |
| Fixed value | Matches one concrete value | No separate method needed |
| Regex, byType, or declarative matchers | Checks type, shape, or rules supported by the DSL | Test/stub generation tool handles matcher |
| **execute(...)** | References a call inserted into the generated test at the appropriate side and position | Generated test context, typically via base test class |
| **byCommand(...)** | Uses a custom check command or method for the selected body part | Testing context of the generated producer test |

Not every place accepting **value(...)** allows arbitrary code snippets, and not every combination of execute/matcher is supported identically across versions, generators, and DSLs. Inspect the **generated test code** to confirm syntax and execution timing.

**Important:** execute(...) in a contract **does not** turn WireMock/Stub Runner into a runner of Java methods inside the producer application. Stubs generated from contracts are typically collections of pre-built mappings, matchers, and responses.

### Why Be Cautious?

If a test uses a method provided by the producer itself to compute the expected value, both the real response and the expectation can be wrong together. Such a test can pass without truly verifying the commitment to the consumer.

On the other hand, test methods have access to the classpath and test environment. If a method reads the network, system clock, production database, or unstable environment variables, test results become hard to reproduce and no longer reflect an independent contract.

## 5. Suitable Case for byCommand: Verifying a Complex Value

Suppose an API returns an order ID that must start with **ORD-**, have a suffix following business rules, and not be empty. First ask: is a declarative matcher sufficient? If a regex expresses the exact condition to check, **a regex is usually simpler and easier to review**.

When the rule is more complex, a test-side verification method can be used on the producer test. Illustrating the idea with a matcher:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-1001", status: "PAID")
        bodyMatchers {
            jsonPath('$.orderId', byCommand('isValidOrderId($it)'))
        }
    }
}
~~~

In some test generation modes, **$it** represents the actual value extracted from the response at the selected JSONPath. The command or method **isValidOrderId(...)** must be declared with the exact signature and return type/assertion style expected by the generator.

A test base class can hold pure verification logic. Example **illustrating the method's responsibility**:

~~~java
public abstract class OrderContractTestBase {

    protected boolean isValidOrderId(String actual) {
        return actual != null
            && actual.matches("ORD-[0-9]{4}");
    }
}
~~~

How to configure the base test class, method location, parameter types, and generator-produced code format must be verified in a real project. If the test expects the method to **assert** rather than return a boolean, use the matching signature and make sure the assertion actually fails the test on invalid values.

This is not a mechanism confirming that orderId has a corresponding record in production. The illustrative method checks only a format condition. If the contract needs to prove the ID can be queried afterward, write an additional HTTP scenario or dedicated integration test.

### Why Must You Never Write a Method That Always Returns True?

~~~java
// Counterexample: makes the test meaningless.
protected boolean isValidOrderId(String ignored) {
    return true;
}
~~~

With such a method, the producer can return an invalid ID and the test still passes. Therefore, test code should have clear negative conditions, invalid cases must lead to **test failure**, and there should be tests for the helper itself if the rule is complex enough.

## 6. execute(...) Does Not Replace Fixtures and Matchers

Another case is when the producer test's expected value must be obtained from **controllable fixture state**, such as an order ID set up by the test. Spring Cloud Contract can support referencing a method via execute(...) in the producer-side value within corresponding contexts.

The snippet below illustrates the **purpose of two-sided values**; verify how your current generator interprets execute and method signatures:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID",
            processedAt: value(
                consumer("2026-01-15T08:00:00Z"),
                producer(execute("expectedProcessedAt()"))
            )
        )
    }
}
~~~

In the example:

- **consumer(...)** gives the stub a sample timestamp, sufficient for the consumer to handle the response.
- **producer(execute(...))** expresses the intent that the generated producer test uses an existing method to verify or retrieve the expected value as supported by the generator.
- The **expectedProcessedAt()** method must exist in the test context, yield stable results, and not rely arbitrarily on current wall-clock time.
- If the actual timestamp cannot be known in advance and only format matters, consider a **response regex/matcher** rather than building a complex execute mechanism.

Never obtain expectations by calling the exact endpoint under test and using that response as expected. Doing so makes the check nearly self-validating and easily misses bugs.

### Reasonable Boundaries of a Test Method

| Do | Do Not |
| --- | --- |
| Compare actual value against an independent business rule | Pull expected directly from the output of the service under test |
| Use versioned fixtures or precomputed values from fixed inputs | Read random numbers, real clock, or uncontrolled environments |
| Cause assertion failure when the contract is violated | Swallow exceptions and return PASS |
| Check format and consistency across agreed fields | Tightly couple to repository call order or internal class structure |
| Keep helpers small, pure, easy to review, and reproducible | Make production HTTP calls or access real data |

## 7. Distinguishing Groovy Code Evaluated at DSL Load Time from Code in Generated Tests

A common confusion is writing Java/Groovy code directly inside the contract file and assuming every snippet executes when the producer test runs.

For example:

~~~groovy
// Counterexample: variable created when the Groovy contract is processed.
def generatedNow = java.time.Instant.now().toString()
~~~

If this variable is used as the response body, the generated contract may depend on build time. It is fundamentally different from a **method call that the generated test will execute** via the execute/byCommand mechanism.

~~~mermaid
sequenceDiagram
    participant D as Groovy DSL
    participant B as Build/Verifier
    participant T as Generated producer test
    participant S as Stub Runner
    participant C as Consumer
    D->>B: Evaluate script and contract model
    B->>T: Generate tests with matchers/helper calls
    B->>S: Generate mappings/stubs
    T->>T: Run assertions/helpers in test environment
    C->>S: Send request
    S-->>C: Return configured stub data
~~~

Specifically:

1. **During test generation:** the plugin evaluates Groovy DSL and produces artifacts. Arbitrary Groovy code at this stage can cause side effects right on the build machine.
2. **During test execution:** calls present in the generated test only run if the method exists, the signature matches, and the test environment is configured.
3. **During stub execution:** the consumer usually communicates solely over HTTP/messaging with generated mappings. It has no authority to call arbitrary methods in the producer's base test class.

Therefore, an execute call is not magic "dynamic data synchronization" between two processes or repositories. Design **sample values for the stub** and **verification rules for the producer** so both reflect the real commitment.

## 8. Compilation and Environment Limits of Test Methods

To use code-executed mechanisms, consider at least five technical conditions:

1. **DSL/generator support.** Different request/response positions, matcher types, and test generators may accept different feature sets.
2. **Method signature.** Name, parameter count, parameter types, visibility, and return type must fit the actual generated test snippet.
3. **Base class context.** Generated tests must extend or access the properly configured base test class.
4. **Input data.** JSONPath values can arrive as String, Number, List, or null; helpers must handle types and missing values deliberately.
5. **Determinism.** Helpers must return the same result for the same data, unless variation itself is a verifiable part of the contract.

A seemingly correct helper can fail if JSONPath points to an array while the method expects a string, or the method takes an integer while the parser supplies another numeric type. Inspect generated sources and run tests to verify those details at the appropriate build/QA stage.

Never edit generated tests by hand to "fit" signatures. **The source to fix** is the DSL, base class, generator config, or fixture. Regenerated tests will overwrite any manual edits.

## 9. Conceptual Limit: Code-Based Checks Must Not Obscure the Contract

A contract can be syntactically valid yet weak in meaning:

~~~text
Producer returns JSON
    |
    v
Generated test calls customCheck(response)
    |
    v
customCheck() uses implementation to decide pass/fail
~~~

When the entire rule sits inside **customCheck(...)**, contract reviewers cannot tell exactly what the producer has committed to. Worse, if the helper invokes the producer's own business logic, the test checks an output using the exact algorithm that created it.

A clearer design direction:

- Important fields, types, HTTP statuses, error codes, and enum values are declared directly in the contract.
- Declarative regexes/matchers express simple, visible rules.
- Custom verification code is used only for rules that cannot reasonably be described by standard matchers.
- Method names, documentation, and assertions clearly state **the condition that must hold**.
- Verification logic stays independent of producer implementation logic as far as possible.

For example, if the consumer only requires orderId to match **ORD-** and four digits, a regex is already a transparent contract. If the consumer requires a complex checksum with a published algorithm, a helper may make sense, provided there are separate tests for invalid checksum cases.

## 10. Impact on Stubs and Stub Runner

Differences between the two sides often surface in consumer CI:

| What Producer Test Verifies | What Stub Can Simulate | Limit to Watch Out For |
| --- | --- | --- |
| orderId has valid format | Returns a sample orderId | Stub does not prove that ID exists in a real database |
| Timestamp follows rule | Returns a fixed sample timestamp | Stub does not prove the producer's clock is accurate |
| Error code when order not found | Returns 404 for sample request | Real producer tests and critical error branches are needed |
| Checked by custom method | Returns packaged data/mappings | Stub does not execute producer verification methods |
| Values spanning multiple requests | May require purpose-built stubs/scenarios | A single mapping does not guarantee cross-request state |

If the consumer uses Stub Runner and receives response **ORD-TEST-9001**, that is simulated data serving consumer tests. It **does not assert** the real producer will return that exact ID. The producer must be verified by appropriate generated tests.

A CI pipeline can:

~~~mermaid
flowchart TD
    A["Reviewed Groovy/YAML contract"] --> B["Generate producer tests"]
    A --> C["Generate stub"]
    B --> D["Run tests with base class/helpers"]
    D --> E{"PASS and enough tests?"}
    E -->|No| X["BLOCK"]
    E -->|Yes| F["Package fixed-version stub"]
    C --> F
    F --> G["Consumer tests via Stub Runner"]
    G --> H{"PASS with right stub?"}
    H -->|No| X
    H -->|Yes| I["Record scoped compatibility evidence"]
~~~

If a producer test uses execute/byCommand but cannot invoke the helper, the pipeline must fail. Never skip tests or alter matchers to **always true** just so stub artifacts get published.

## 11. Common Mistakes When Using Code-Executed Values

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Generated test fails to compile | Method or signature mismatch | Inspect generated test source and base test class |
| Test always passes even on wrong response | Helper too broad, always true, or missing assertion | Run with controlled bad data; verify test must FAIL |
| Flaky tests | Uses real clock, random values, or network dependencies | Create fixed fixtures; switch to matchers |
| Stub lacks expected dynamic computation | Treated execute as stub code | Distinguish consumer sample response from producer assertion |
| Same contract gives two outcomes across CI | Helper/DSL relies on environment variables or external data | Lock down config, data, and contract source |
| Data type error in test | JSONPath extracts Number/List while helper takes String | Check actual type and method signature |
| Producer test passes but consumer hits bugs | Stub too simplistic, consumer lacks logic tests or missing scenarios | Add consumer tests and necessary contract scenarios |
| Old stub still passes | Consumer CI did not pick up new artifact | Pin stub version and checksum published |

Another mistake is using **test code with side effects** to mutate production data or shared environments. Generated tests must run in a test environment with appropriate permissions and data, never reading or mutating production state to verify dynamic values.

## 12. How to Decide Whether to Use execute/byCommand

Ask these questions in order:

1. **Can a fixed value be used?** If it is a scenario with stable fixtures, a fixed value is usually simplest.
2. **Can a declarative matcher be used?** If you only need ID format, type, length, or an enum value, prefer supported DSL syntax.
3. **Is verifying a complex rule genuinely a public commitment?** If yes, consider an independent helper with tests for both true and false conditions.
4. **Where will the method execute?** Make sure generated producer tests can invoke the method; stubs do not share the same execution environment.
5. **Do the same fixture and input yield consistent results?** If not, redesign the data or matcher.
6. **Is it verified that the method fails the test when the producer violates it?** If not, the helper is not a reliable assertion yet.

A useful rule is **keep contracts as declarative as possible and use custom code only for the minimum truly necessary**.

## 13. Scenario Exercises

### Exercise A — Choosing Value Sides

A POST /api/orders contract uses a fixed customerId **CUS-TEST-1001** for the generated producer test, while the stub needs to accept many customerIds via regex. Determine which side should receive the sample value and which side should receive the regex.

**Hint:** In a request, the **consumer(...)** value is the data sent by the test; **producer(...)** can hold the stub matcher used to accept consumer requests.

### Exercise B — ID in Response

The producer generates orderId dynamically. The consumer test only needs a sample ID to verify storage/navigation logic. The producer test needs to check that the ID is properly formatted.

**Requirement:** write the response body part using a fixed consumer value and a producer regex. Explain why a passing producer test does not prove the ID can be queried afterward.

**Hint:** use a response with consumer("ORD-TEST-9001") and producer(regex("ORD-[A-Z0-9-]+")). Proving the ID works in subsequent calls requires dedicated integration tests for that flow.

### Exercise C — Always-True Helper

A team uses byCommand to call **validateAmount(...)**. The method returns true for any number, including negatives. The producer test always passes.

**Requirement:** rewrite the business rule, add counterexample values, and decide what belongs in the contract versus unit tests.

**Hint:** if the value must be non-negative, the helper must reject negative numbers and missing values; suitable matchers and negative tests can be used. More detailed pricing rules can be unit tested separately.

### Exercise D — Stub and Executable Code

A consumer test via Stub Runner expects the stub to call **expectedProcessedAt()** to get the timestamp on every request, yet the stub always returns a fixed timestamp.

**Requirement:** explain that behavior, and describe how to test the consumer appropriately.

**Hint:** test-side functions are used within supported generated test contexts, not executed automatically inside stubs. Use a sample response with an appropriate format and test consumer logic; simulating multiple responses requires separate stubs/scenarios.

### Exercise E — Compatibility Conclusion

Generated producer tests PASS with the orderId regex, and consumer CI PASSES using an old stub version. Is there enough evidence to declare the new producer compatible?

**Hint:** not yet. You must tie together the same contract revision, verified producer build, new stub artifact, and consumer tests using that exact artifact. Conclusions cover only the verified scenarios.

## 14. Checklist When Using Code-Executed Values

- [ ] Distinguished consumer/client and producer/server by request or response.
- [ ] Consumer-side sample values let stubs/generated tests run without containing production data.
- [ ] Declarative matchers are preferred whenever sufficient to express the condition under test.
- [ ] Only use execute/byCommand in contexts supported by the DSL/generator in use.
- [ ] Inspected generated tests to confirm method, parameters, return type, and execution timing.
- [ ] Base test class is configured properly and every referenced method actually exists.
- [ ] Assertions/helpers fail on invalid data rather than always returning true.
- [ ] Expected values and verification logic stay independent of producer implementation within required scope.
- [ ] No production I/O, randomness, real clock, or uncontrolled secrets inside helpers.
- [ ] Verified contracts/stubs are generated from the same reviewed revision.
- [ ] Producer tests run and PASS against the release candidate build.
- [ ] Consumer tests use the exact stub version via Stub Runner and verify consumer logic.
- [ ] Compatibility conclusions are scoped strictly to the version pairs and scenarios actually tested.

**Key takeaway:** Spring Cloud Contract's two-sided values allow **stubs to use concrete examples** while **generated producer tests verify real data with appropriate expectations**. execute(...) and byCommand(...) extend verification power but are bounded by test generation context, method signatures, reproducibility, and assertion quality. They do not put producer code inside stubs; contracts are trustworthy only when both producer tests and consumer tests verify the exact agreed commitment.
