# Limits of Arbitrary Code in Contracts

## Lesson Objectives

**Spring Cloud Contract** allows producers and consumers to agree on HTTP or messaging behavior using **Groovy DSL** or **YAML DSL**. From that contract, the tooling can generate **producer-side** tests and stubs for the **consumer** side to run via **Stub Runner**; CI uses those results to detect incompatible API changes.

One characteristic to understand clearly: a Groovy contract file is typically a **Groovy script evaluated when the tool processes the contract**. Thus, at the language level, an author could write variables, functions, conditionals, or Java/Groovy API calls outside DSL structures. However, being *able to write code* does not mean that code *belongs in the contract*.

After this lesson, you will be able to:

- Distinguish **code describing integration behavior** from **implementation or test logic**.
- Explain why arbitrary code in a Groovy contract can make builds non-reproducible, hard to review, or introduce security risks.
- Place sample data, matchers, dynamic DSL expressions, and base-test-class methods in their proper locations.
- Rewrite a contract that depends on time, environment variables, or machine state into a stable specification.
- Incorporate completeness checks for producer tests, stubs, and consumer tests into CI.

## 1. "Groovy DSL" Is a Specification in Groovy, Not a Place for Arbitrary Logic

A simple HTTP contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Retrieve status of a paid order"

    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header "Accept", "application/json"
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID"
        )
    }
}
~~~

The contract above expresses an **observable commitment**: when the consumer calls GET /api/orders/ORD-1001, the producer returns HTTP 200 and JSON containing id and status with the agreed values. It does not describe which controller, database, repository, or algorithm the producer uses.

Technically, this snippet is a Groovy script calling **Contract.make**. When the plugin loads it to build the contract model, necessary Groovy expressions are evaluated. This differs from simply reading a pure data configuration file.

**Principle:** use Groovy's expressiveness to state **what the consumer has a right to expect**; do not turn the contract into a program that drives the build, executes business logic, or accesses external systems.

## 2. "Limits of Arbitrary Code" Has Two Layers

| Layer | Nature | What to Do |
| --- | --- | --- |
| **Technical capability of Groovy/JVM** | Groovy can express many statements outside the DSL; whether they execute depends on the plugin's environment and classpath | Do not assume `.groovy` files are inert data or completely sandboxed |
| **Design boundary of a contract** | A specification should state only the behavior and data to verify between producer and consumer | Avoid unnecessary logic, I/O, unstable data, and implementation dependencies |

Therefore, claiming "Spring Cloud Contract forbids arbitrary code" is **oversimplified and misleading**. A Groovy file can contain operations that contract authors have no business using. The key boundary here is **design discipline and execution control**, alongside the specific constraints of the DSL API.

### Three Execution Moments to Distinguish

~~~mermaid
flowchart TD
    A["Contract file .groovy"] --> B["Plugin loads/evaluates script<br/>to build contract model"]
    B --> C["Generate producer tests"]
    B --> D["Generate stubs/mappings"]
    C --> E["Run tests on producer"]
    D --> F["Package/publish stubs"]
    F --> G["Consumer tests via Stub Runner"]
~~~

There are three **distinct** kinds of actions:

1. **Code running when loading the contract:** such as string concatenation expressions, reading environment variables, or calling functions outside DSL blocks. Effects of this code occur immediately during contract processing.
2. **Producer test logic:** fixtures, HTTP client initialization, or methods in the base test class that run when the generated test executes.
3. **Stub behavior:** the stub receives requests and returns responses according to the generated mappings. A consumer calling the stub does not mean the stub re-runs the entire original Groovy script.

Some special Spring Cloud Contract features generate method calls **in the generated test**. You must know the exact execution side and timing of each DSL mechanism. Never treat every Groovy snippet or every dynamic expression as the same kind of operation.

## 3. Anti-Pattern: Using Environment Variables to Decide the Contract

~~~groovy
// Anti-pattern: DO NOT use to define a fixed API.
import org.springframework.cloud.contract.spec.Contract

def orderId = System.getenv("CONTRACT_ORDER_ID") ?: "ORD-1001"
def expectedStatus = System.getenv("CONTRACT_STATUS") ?: "PAID"

Contract.make {
    request {
        method GET()
        url("/api/orders/" + orderId)
    }
    response {
        status OK()
        body(
            id: orderId,
            status: expectedStatus
        )
    }
}
~~~

This script can produce **two different contracts from the same commit** if producer CI and consumer CI have different environment variables:

- Reviewers see PAID in Git while the pipeline evaluates a different status.
- Producer and consumer may generate tests/stubs with mismatched URLs or bodies.
- Re-running a build no longer guarantees producing the same contract if environment variables change.
- A CI PASS does not prove the producer keeps a specific public behavior stable.

If the goal is to describe a specific paid order case, state it explicitly:

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
        body(id: "ORD-1001", status: "PAID")
    }
}
~~~

If the producer supports multiple business states, define **intentional scenarios** or use appropriate matcher mechanisms. Never use build-machine variables to silently decide which scenario the consumer receives.

## 4. Types of Code to Restrict and Better Alternatives

| Code Type in Groovy Contract | Risk | Better Way to Express It |
| --- | --- | --- |
| Reading environment variables to alter response/path | Contract depends on the runner machine | Fix the public promise or split scenarios explicitly |
| Reading external local files for expected body | Depends on files outside the contract source | Version fixtures, use declarative data and controlled test setup |
| Making HTTP/database calls while loading DSL | Build requires network/infra; can cause side effects | Prepare fixtures in base test class or integration test setup |
| Using current date, UUID/random for expected values | Non-reproducible tests/stubs | Use fixed sample data or format-based matchers |
| Calling producer service/repository to compute expected response | Expected value may mirror implementation bugs | Write independent expectations from consumer requirements |
| Generating many contracts with complex loops/conditionals | Hard to review verified scenarios | Split named scenarios and group contracts clearly |
| Spawning processes, reading secrets, or writing files on load | Build security risk | Only execute reviewed contract sources, restrict CI permissions |

Not **every Groovy variable** is wrong. A clear constant with no side effects can help avoid mistyping the same value:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

def orderId = "ORD-1001"

Contract.make {
    request {
        method GET()
        url("/api/orders/" + orderId)
    }
    response {
        status OK()
        body(id: orderId, status: "PAID")
    }
}
~~~

The constant above is fully visible in reviews and produces identical results when re-processed. Still, if a contract is only a few lines long, writing literals inline usually lets readers understand the contract faster.

## 5. Dynamic Data: Prefer Matchers Over Random Generation

A misguided example:

~~~groovy
// Anti-pattern: values change every time Groovy is processed.
def createdAt = java.time.Instant.now().toString()
def orderId = java.util.UUID.randomUUID().toString()
~~~

If the consumer only needs a valid timestamp, hardcoding *build time* into the expected response causes tests to fail whenever the producer returns another valid timestamp. The same contract revision could also generate multiple stubs with differing contents.

Distinguish three cases:

- **Deterministic data:** e.g., ORD-1001 and 2026-01-01T10:00:00Z, used when testing a fixed scenario with corresponding fixtures.
- **Format rules:** id must follow a structure, timestamp must be ISO-8601, a numeric field must fall within a valid range. Use **matchers** supported by the DSL.
- **Business semantics:** e.g., status PAID means paid; an arbitrary regex cannot substitute for this business rule.

Spring Cloud Contract supports matchers, regexes, and differing consumer/producer values in certain scenarios. Exact syntax, applicability, and helpers must be verified for your version; an overly broad matcher can let tests PASS even when the producer returns a value the consumer cannot handle.

**Do not generate random values in Groovy for "more coverage"**: data variety should be designed in appropriate tests with reproducible seeds or fixtures. Contracts must express conditions agreed upon by both sides.

## 6. Put Setup in the Base Test Class, Keep the Contract as a Commitment

Generated producer-side tests need a callable application or HTTP context and matching data. Preparing these belongs in the **base test class** or test infrastructure, not in the Groovy script evaluated at load time.

Contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Query a paid order"
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(id: "ORD-1001", status: "PAID")
    }
}
~~~

A base test class **sketch** showing data responsibility (not yet a complete Spring Boot test):

~~~java
abstract class OrderContractTestBase {

    @BeforeEach
    void prepareFixture() {
        // Ensure ORD-1001 has status PAID
        // in the test environment's database/mock.
    }
}
~~~

A real base class also configures the test context and client (such as Rest Assured Mock MVC, MockMvc, or the corresponding integration mode). The main point is that fixtures have a clear lifecycle independent of production data. The contract says **what the producer must return**; test setup determines **how to create the state to verify it**.

### A Controlled Exception: Methods Referenced by the DSL

For messaging contracts, a generated test may need to call a method to trigger an event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label "order_paid_event"
    input {
        triggeredBy("triggerOrderPaid()")
    }
    outputMessage {
        sentTo("order-events")
        body(eventType: "ORDER_PAID", orderId: "ORD-1001")
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

The method **triggerOrderPaid()** must be defined in the producer test context, invoked via the generated test mechanism, and trigger the behavior under verification. The **triggeredBy(...)** line is a DSL construct; **it does not mean Stub Runner will execute that string when the consumer receives a message**.

Similarly, certain DSL expressions like **execute(...)** supply dynamic values or call methods in generated tests, depending on context. When using them, know precisely **which side executes**, where the method lives, and whether data stays stable. This is not a license to put arbitrary business logic or I/O into the contract.

## 7. Expected Values Must Be Independent of the Code Under Test

Suppose the producer calculates an order total. A contract that calls **the very service under test** to compute its own expectation is a weak design:

~~~groovy
// Anti-pattern pseudocode: computing expectation using real implementation.
def expectedTotal = orderPricingService.calculateTotal("ORD-1001")
~~~

If the implementation miscalculates, expectedTotal receives that exact wrong result, and the test PASSES even though the consumer gets an unpromised value. A meaningful contract must have **independent expectations**:

1. Both sides agree on input data and public rules.
2. The contract specifies the amount, currency unit, and response structure the consumer depends on.
3. Fixtures create controlled test data.
4. The generated test calls the producer and checks against the defined expected response.

Complex business calculations deserve dedicated unit or integration tests. Contracts focus on compatibility of the **producer–consumer interface**.

## 8. Groovy Code Can Expand the Security Risk Surface

Because `.groovy` contracts can be evaluated by the build process, never treat Groovy received from an arbitrary source as **harmless data to load**. Depending on process permissions, classpath, and how the plugin evaluates code, a script could reach JVM APIs or data readable by CI.

Risks to manage:

- Code in contracts accessing or leaking environment variables, configuration details, or build secrets.
- Code reading/writing files or calling external systems during test/stub generation.
- A helper or import hiding side-effecting behavior so review diffs show only a few lines.
- Builds depending on a live host, wall-clock time, or execution order.

Never assume Maven, Gradle, or Spring Cloud Contract **automatically sandboxes all Groovy code**. Use trusted contract sources, review changes as executable code, restrict CI permissions and secrets, and lock tool/dependency versions per project policy.

**YAML DSL** is often easier to review for contracts that are mostly data structures and reduces the temptation to write direct code. However, using YAML does not automatically make the entire pipeline safe: plugins, custom converters, test fixtures, and dependencies are still executable code.

## 9. Choosing Groovy DSL or YAML DSL

The same HTTP commitment above can be declared in YAML:

~~~yaml
description: "Retrieve status of a paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

| Criterion | Groovy DSL | YAML DSL |
| --- | --- | --- |
| Form | Groovy script using the Contract API | Declarative structured data |
| Expressiveness | Flexible; supports many Groovy helpers and expressions | Readable, sufficient for many HTTP/message scenarios |
| Risk of hidden logic | Higher when imports, loops, functions, and I/O are abused | Typically less direct arbitrary code |
| Diff review | Requires understanding executed expressions | Usually easy to spot changed fields |
| Best fit | Groovy DSL features are genuinely useful and the team controls reproducibility | Commitments are mostly fixed structures easy to express declaratively |

Do not pick Groovy just to run loops generating tests or query databases. If complex setup is needed, use **test setup**; if business logic needs testing, use **unit/integration tests**; if an integration rule needs expression, prefer directly supported **matchers/DSL**.

## 10. Four Questions When Reviewing a Groovy Contract

For any code outside declarative DSL calls, reviewers should ask:

1. **Does this snippet change public behavior?** If so, consumers need to understand the impact and agree.
2. **Do the same revision and inputs produce the same contract?** If not, is the source of variation truly part of the commitment?
3. **When does this code run?** At DSL load time, when the generated producer test runs, or when the consumer calls the stub?
4. **Can a matcher be used instead, or can it move to fixtures/base test class?** If so, the contract is usually easier to understand and verify.

Example decisions:

| Change | Assessment |
| --- | --- |
| Change HTTP 404 to HTTP 200 for missing orders | Public interface change; must review compatibility |
| Extract constant orderId variable with same value | Usually preserves behavior, still verify generated output |
| Add System.getenv to choose status | Unsuitable for a commitment that needs stability |
| Use standard matcher for ID format | Reasonable when format itself is the commitment |
| Use triggeredBy to call message trigger method in base class | Reasonable if producer setup and behavior are properly verified |
| Query database at contract load time to build expected body | Move to fixtures and declare expectations independently |

In addition, check imports/helpers, timezone/locale dependencies, randomness, and network usage; verify scripts do not silently change URLs, statuses, or schemas across environments.

## 11. CI Must Verify Both Contracts and Generated Outputs

~~~mermaid
flowchart TD
    A["Review Groovy/YAML changes"] --> B["Load contracts in least-privilege build env"]
    B --> C["Generate producer tests and stubs"]
    C --> D{"All contracts discovered?"}
    D -->|No| X["BLOCK / investigate"]
    D -->|Yes| E["Run producer contract tests"]
    E --> F{"PASS?"}
    F -->|No| X
    F -->|Yes| G["Package versioned stub"]
    G --> H["Consumer tests via Stub Runner"]
    H --> I{"PASS with exact revision?"}
    I -->|No| X
    I -->|Yes| J["Publish evidence within verified scope"]
~~~

Key steps:

- **Review before loading:** treat `.groovy` as executable code, especially when sourced from external repositories.
- **Reproducibility:** the same revision must yield equivalent contracts/tests/stubs under controlled build conditions.
- **Completeness:** verify contracts are discovered and generated tests **actually execute**, avoiding silent skips due to wrong paths.
- **Artifact traceability:** new stubs must tie back to verified contracts and producer builds.
- **Consumer tests:** use the exact stub version via Stub Runner; passing against an older stub does not prove a new producer is compatible.

Example **project-designed** verification record (not a format auto-generated by Spring Cloud Contract):

~~~yaml
contract_revision: "contracts@a1b2c3"
producer_revision: "order-service@d4e5f6"
discovered_contracts:
  - get_paid_order
  - get_missing_order
producer_generated_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_version: "checkout:1.9.0"
stub_runner_tests: PASS
~~~

In real usage, also store CI report links and artifact checksums. The illustrative values above are **not actual executed test results**.

## 12. Practical Scenario: A "Clever" Yet Unstable Contract

The Order API team prepares to release producer 2.4.0. One member proposes:

~~~groovy
// Anti-pattern: DO NOT use.
import org.springframework.cloud.contract.spec.Contract

def state = System.getenv("ORDER_TEST_STATE") ?: "PAID"
def id = "ORD-" + (1000 + new Random().nextInt(9000))

Contract.make {
    request {
        method GET()
        url("/api/orders/" + id)
    }
    response {
        status OK()
        body(id: id, status: state)
    }
}
~~~

Producer CI A may generate a contract using ORD-1234 and PAID; elsewhere, the contract evaluates with ORD-8765 or CANCELLED. Parties are no longer testing **the same scenario** despite sharing the same commit.

How to fix:

1. Lock down the business scenario, e.g., GET order ORD-1001 returns PAID.
2. Write constants and responses clearly in the contract; test fixtures prepare the corresponding state.
3. If the ID is genuinely dynamic, use a matcher describing its format rather than calling random inside the script.
4. If CANCELLED must be tested, write a separate scenario with a clear name and expected response.
5. Regenerate producer tests and stubs, and run tests on both sides using explicitly versioned artifacts.

After fixing, readers understand **the promise made to the consumer** without having to reconstruct a full CI environment just to tell what data the script will generate.

## 13. Self-Practice Exercises

### Exercise 1 — Put Code in the Right Place

Classify the following operations:

| Operation | Recommended Location |
| --- | --- |
| Declare GET /api/orders/ORD-1001 returning 200 and status PAID | Groovy DSL |
| Insert ORD-1001 into test database | Base test class / fixture |
| Call production API to fetch ID during build | Remove from contract processing |
| Use DSL matcher to constrain ID format | Groovy DSL |
| Trigger event via method in generated test | DSL hook + base test class method |
| Read env var to silently rename status field | Remove; replace with agreed interface change |

### Exercise 2 — Why Is a Green Build Not Enough?

A commit adds a contract with System.getenv to switch expected status. Producer CI PASSES and publishes a stub. Consumer CI PASSES, but uses last week's stub.

**Question:** Why can we not yet declare the new producer compatible? What evidence do you need?

**Hint:** The contract is unstable across environments; the consumer has not run against the stub from the new build. Remove unnecessary sources of variation, re-run producer tests, publish a stub with clear provenance, and test the consumer with that artifact.

### Exercise 3 — Is the Message Contract Truly Verified?

A contract uses triggeredBy("sendOrderPaid()") to emit an ORDER_PAID event. The base class has that method, yet it only calls a mock publisher without verifying the real producer flow emitting events in a real context.

**Question:** What does the generated test currently prove, and what setup change is needed?

**Hint:** Identify the real boundary being called and verified. A mock matching expectations does not necessarily prove the real producer creates the public message. Adjust setup so generated tests verify producer behavior within the committed boundary.

## 14. Checklist Before Accepting Groovy DSL

- [ ] Contract focuses on HTTP/message behavior observable by the consumer.
- [ ] No I/O, file, network, process, or secret access outside controlled setup.
- [ ] No clock, random, UUID, or environment variables silently altering the commitment.
- [ ] Fixtures live in test setup; expected responses are independent of the implementation under test.
- [ ] Dynamic values use DSL matchers/expressions matching consumer requirements.
- [ ] Every triggeredBy/execute hook is reviewed for execution side and timing, with clear test methods.
- [ ] `.groovy` files are reviewed as executable code; CI permissions and contract sources are controlled.
- [ ] Plugin discovers all contracts and generates corresponding tests.
- [ ] Generated producer tests PASS on the exact build intended for release.
- [ ] Stubs are packaged from the exact verified contracts and producer build.
- [ ] Consumers test against a specific stub version via Stub Runner.
- [ ] Compatibility claims cover only the versions and behaviors actually backed by evidence.

**Key takeaway:** Groovy DSL offers flexible contract expression, yet **a good contract is a clear, independent, reproducible commitment**, not the "cleverest" script possible. Keep specifications focused on producer–consumer behavior, move setup to the appropriate test layer, and cross-check producer tests, stubs, and consumer tests in CI against the exact contract revision.
