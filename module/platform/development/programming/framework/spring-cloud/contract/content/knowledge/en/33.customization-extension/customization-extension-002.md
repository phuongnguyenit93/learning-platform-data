# Custom Assertions and Helpers in Base Tests

## Lesson Objectives

**Spring Cloud Contract** lets you describe HTTP or message behavior using a **Groovy/YAML DSL**, generate producer-side tests, and publish stubs for consumers via **Stub Runner**. Most conditions should be expressed with declarative matchers: status, headers, JSONPath, literal values, data types, or regular expressions. When a more complex business invariant arises, a team can add **custom assertions** and helper methods in the **base test class**.

The lesson **“Custom Assertions and Helpers in Base Tests”** belongs to the **Customization and Extension** chapter. The focus is not on writing lots of custom code, but on knowing **when to extend**, how the generator invokes methods, how to ensure helpers **verify real values**, and how to prove they do not produce false PASSes.

After this lesson, you will be able to:

- Distinguish between contract DSL, generated tests, base tests, assertion helpers, and stub artifacts.
- Choose declarative matchers or custom assertions based on actual requirements.
- Understand the role of **`byCommand(...)`** in Groovy response body matchers for supported versions.
- Build Java helpers with explicit type checking, null checks, boundary handling, and clear failure messages.
- Configure a producer base test with MockMvc and connect it to generated tests.
- Separate result-verification helpers from fixture-setup or message-trigger helpers.
- Inspect generated source, verify method signatures, and write unit tests for helpers.
- Audit side effects, security, and CI evidence before declaring producer–consumer compatibility.

## 1. What Problem Do Custom Assertions Solve?

Suppose Order Service returns a response:

~~~json
{
  "orderId": "ORD-12045",
  "status": "PAID",
  "amount": 125000,
  "currency": "VND"
}
~~~

Simple requirements such as `status = PAID` or `currency = VND` can be verified directly in the DSL. However, if `orderId` must follow a custom format plus a business checksum, or `amount` has unit, precision, or range constraints, basic matchers may not express them clearly enough.

That is where **custom assertions** help: the generated producer test can receive the actual value and call a Java method to verify the invariant. Still, helpers bring extra code and dependencies; they should not be the default choice for every field.

**Selection rule:** use DSL matchers whenever conditions can be described directly; use custom assertions when an invariant is hard to express clearly and protects an observable API guarantee.

| Condition | Usually Suitable Tool |
| --- | --- |
| HTTP status is 200 | `response.status` |
| `Content-Type` header is JSON | `response.headers` |
| `status` field equals `PAID` | Body literal/JSONPath equality |
| `orderId` matches published regex | Regex matcher |
| `orderId` needs a specialized validation algorithm | Custom assertion |
| `amount` must be positive with exact precision | Specialized matcher or helper |
| `total = subtotal + tax` | Additional test on full response or verified multi-value mechanism |
| Request actually writes a record | Integration assertion against test database |
| Message is published to the right destination | Message contract and producer message test |

Never use helpers to hide an underspecified contract. If the consumer relies on `status = PAID`, do not replace that assertion with a vague call like `checkResponse(response)` where reviewers cannot tell what is being verified.

## 2. Flow from Contract to Assertion

~~~mermaid
flowchart TD
    C["Contract Groovy/YAML"] --> G["Contract Verifier generates test"]
    G --> T["Generated producer test"]
    B["Base test class"] --> T
    H["Custom assertion helper"] --> B
    T --> P["Producer implementation"]
    P --> R["Actual response / message"]
    R --> T
    T --> A{"Matcher / helper passes?"}
    A -->|Yes| OK["Producer test PASS"]
    A -->|No| FAIL["Producer test FAIL"]
    C --> S["Generate stub artifact"]
    S --> ST["Stub Runner"]
    ST --> CT["Consumer tests"]
~~~

Two branches must remain distinct:

- **Producer verification:** generated tests check whether the producer implementation satisfies the contract. This is where the base test and custom assertions may be invoked.
- **Consumer stub tests:** Stub Runner returns sample responses/mappings for consumer testing. Custom Java helpers in the producer base test are **not automatically converted into consumer validation code**.

An HTTP stub may return `ORD-12045`, while the generated test accepts any ID matching a pattern or checksum. Consumer tests must still include their own assertions if they want to verify that the consumer handles that ID properly.

## 3. What Is a Base Test Class?

A base test class is typically the class that **generated producer tests extend** or that is configured as the foundation in the test generation mechanism of your Spring Cloud Contract version.

It can provide:

- Spring test context and MockMvc/HTTP client setup.
- Fixtures for databases or mock dependencies.
- Methods to trigger producer messages.
- Helpers to assist with verifying responses and headers.
- Setup/teardown scoped per test, per suite, or for a shared environment.

Project layout example:

~~~text
order-service/
├── pom.xml
├── src/test/resources/contracts/orders/get_paid_order.groovy
├── src/test/java/com/example/orders/contract/
│   ├── OrderContractBase.java
│   ├── OrderContractAssertions.java
│   └── OrderContractAssertionsTest.java
└── target/
    ├── generated-test-sources/...
    └── ...
~~~

Directories under `target` are illustrative; exact paths vary by plugin, version, and configuration.

A class named `OrderContractBase` sitting in test sources is **not used automatically**. The build plugin must be informed via `baseClassForTests` or an equivalent base class mapping mechanism.

## 4. Configuring the Base Class in Maven

Illustrative POM snippet:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>${spring-cloud-contract.version}</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.OrderContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`spring-cloud-contract.version` is a property that should be managed with a version compatible with your project's Spring Boot/Spring Cloud versions; this snippet is not a complete POM.

For multiple contract groups, several versions support configuring **base class mappings** instead of a single base class. How mappings, regex/packages, and selection precedence are written depends on the plugin version. **Never guess which base class a generated test extends; read the generated source.**

In Gradle, the idea is similar: specify the contract DSL root and base class in the plugin configuration for your current version. Do not copy Maven property names blindly into Gradle without checking the plugin's DSL.

## 5. HTTP Base Test with Spring MVC and RestAssuredMockMvc

Skeleton example for a producer using **Spring MVC**, **JUnit 5**, and **MockMvc**:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
public abstract class OrderContractBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void setUpHttp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }

    public void assertValidOrderId(Object actual) {
        OrderContractAssertions.requireValidOrderId(actual);
    }

    public void assertPositiveAmount(Object actual) {
        OrderContractAssertions.requirePositiveAmount(actual);
    }
}
~~~

Assumptions: generated tests are configured to use RestAssuredMockMvc, and the project includes the required test dependencies. This is not a universal base class for every producer. For WebFlux, WebTestClient, RestAssured against a live server, or messaging, the setup differs.

In this example:

- `@SpringBootTest` provides the Spring test context.
- `@AutoConfigureMockMvc` configures MockMvc.
- `@BeforeEach` wires RestAssuredMockMvc to MockMvc.
- The two `public` methods act as helper entry points accessible to the generated subclass.
- A dedicated helper class holds business rules so the base test does not become overloaded with assertions.

**Do not mock the entire controller so that it returns the exact sample body from the contract.** Doing so can make generated tests PASS while the real producer implementation returns a different structure. Only fake external dependencies that must be isolated, keeping the core logic path under test.

## 6. Pure Java Helpers and Clear Failure Messages

A standalone helper:

~~~java
package com.example.orders.contract;

import java.math.BigDecimal;
import java.util.regex.Pattern;

public final class OrderContractAssertions {

    private static final Pattern ID_PATTERN =
        Pattern.compile("^ORD-[0-9]{4,}$");

    private OrderContractAssertions() {}

    public static void requireValidOrderId(Object actual) {
        if (!(actual instanceof String)) {
            throw new AssertionError(
                "orderId must be a JSON string, got type " +
                typeName(actual)
            );
        }

        String id = (String) actual;
        if (!ID_PATTERN.matcher(id).matches()) {
            throw new AssertionError(
                "orderId does not match format ORD-<digits>"
            );
        }
    }

    public static void requirePositiveAmount(Object actual) {
        if (!(actual instanceof Number)) {
            throw new AssertionError(
                "amount must be a JSON number, got type " +
                typeName(actual)
            );
        }

        BigDecimal amount =
            new BigDecimal(actual.toString());

        if (amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new AssertionError(
                "amount must be greater than 0"
            );
        }
    }

    private static String typeName(Object actual) {
        return actual == null
            ? "null"
            : actual.getClass().getSimpleName();
    }
}
~~~

These design choices are deliberate:

1. The helper accepts `Object` so it can explicitly check the type returned by JSONPath.
2. `orderId` is valid only as a `String` matching the pattern; it does not coerce a `Number` to a string.
3. `amount` must be numeric, not treating the string `"125000"` as equivalent to the JSON number `125000`.
4. When the invariant fails, the helper throws `AssertionError`—causing the test framework to report FAIL.
5. It does not write to databases, make network calls, generate tokens, or mutate producer state.
6. It avoids dumping the full response, reducing the risk of leaking sensitive data in CI logs.

The regex and numeric constraints in this example are meaningful only if **agreed upon by producer and consumer**; they are not universal rules for every Order API.

### Why Not Use a Method Returning Boolean?

If the generated test simply invokes:

~~~java
checkOrderId(actual);
~~~

and the method returns `false`, JUnit **does not fail automatically** unless the generator wraps that return value in an assertion. Using a `void` helper that throws `AssertionError` on failure is explicit and reliable for the verified custom command model.

## 7. Defining Custom Matchers in the Groovy DSL

In Spring Cloud Contract versions supporting **`byCommand(...)`** in response body matchers, you can reference methods from the base test.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Fetch a paid order with a valid ID"

    request {
        method GET()
        url "/api/orders/ORD-12045"
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-12045",
            status: "PAID",
            amount: 125000,
            currency: "VND"
        )

        bodyMatchers {
            jsonPath('$.orderId',
                byCommand('assertValidOrderId($it)'))
            jsonPath('$.amount',
                byCommand('assertPositiveAmount($it)'))
        }
    }
}
~~~

How to read this:

- `jsonPath('$.orderId', ...)` selects the value from the actual JSON response.
- `byCommand('assertValidOrderId($it)')` specifies a custom command so the generator emits the corresponding helper call.
- `$it` is the custom command syntax placeholder; you **do not need to declare** a Java/Groovy variable with this name.
- `assertValidOrderId` and `assertPositiveAmount` must exist with signatures compatible with the generated invocation.
- The `body` still supplies **sample values** for generating stub responses.

**Version note:** details of how the generator substitutes `$it`, generated parameter types, and which DSL locations support `byCommand` must be checked against your Spring Cloud Contract version. This example demonstrates the approach for Groovy response body matchers and does not imply every YAML field or message matcher shares the exact same API.

### Why Use Single-Quoted Strings?

~~~groovy
jsonPath('$.orderId', byCommand('assertValidOrderId($it)'))
~~~

Single-quoted Groovy strings preserve the placeholder token literally for the generator. A common mistake is accidentally introducing Groovy string interpolation or Java expressions, producing invalid generated syntax.

## 8. Custom Matchers Can Alter Contract Semantics

Suppose before customization the contract had:

~~~groovy
body(orderId: "ORD-12045", status: "PAID")
~~~

If the test previously required **equality** of `orderId` with `ORD-12045`, replacing it with a helper that only checks the `^ORD-[0-9]{4,}$` pattern allows `ORD-99999` as well.

This is not merely a test implementation change: it **changes the strictness of the contract**.

| Verification Method | Meaning |
| --- | --- |
| Exact equality | Must be one exact value, suited for fixed fixtures |
| Regex pattern | Accepts any value matching the format |
| Custom helper | Accepts whatever values the helper defines as valid |
| No assertion | Does not detect changes on that field |

If the consumer requires that **the returned ID match the ID in the request**, a helper checking only the format is insufficient. You must verify the request–response relationship using supported DSL capabilities or an appropriate supplementary test.

**Never relax a matcher just to make a producer test PASS.** Reviewers should check which constraint became weaker and whether any consumer depends on the stricter rule.

## 9. Inspect Generated Source Instead of Guessing

Once the Maven plugin is configured, you can run:

~~~bash
./mvnw clean test
~~~

Or run through the verify phase to execute quality gates bound in the project:

~~~bash
./mvnw clean verify
~~~

These commands only work properly when plugin goals, generated test source sets, and the test runner are configured. `BUILD SUCCESS` **does not by itself prove** your custom assertion was called.

In the generated source, look for a call equivalent in meaning to:

~~~java
// Sketch, not verbatim generator output.
Object actualId =
    /* extract JSONPath $.orderId from actual response */;
assertValidOrderId(actualId);
~~~

Things to verify:

1. Was the contract discovered by the plugin?
2. Was the generated test source actually created?
3. Does the generated test extend the right base class?
4. Is there a call to `assertValidOrderId` with the right method name?
5. What concrete Java type is passed into the method?
6. Did the test runner execute the generated test and record a report?
7. When intentionally supplying invalid input in a **negative check**, does the helper make the test FAIL?

The last step is crucial: it catches cases where the helper exists but is **never invoked**.

## 10. Write Dedicated Unit Tests for Helpers

Example using JUnit 5:

~~~java
package com.example.orders.contract;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderContractAssertionsTest {

    @Test
    void validIdPasses() {
        assertDoesNotThrow(() ->
            OrderContractAssertions.requireValidOrderId(
                "ORD-12045"
            )
        );
    }

    @Test
    void invalidIdFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requireValidOrderId(
                "INVALID"
            )
        );
    }

    @Test
    void wrongIdTypeFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requireValidOrderId(
                12045
            )
        );
    }

    @Test
    void positiveAmountPasses() {
        assertDoesNotThrow(() ->
            OrderContractAssertions.requirePositiveAmount(
                125000
            )
        );
    }

    @Test
    void zeroAmountFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requirePositiveAmount(
                0
            )
        );
    }

    @Test
    void numericStringFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requirePositiveAmount(
                "125000"
            )
        );
    }
}
~~~

Unit tests verify **helper logic**, whereas generated producer tests verify **that the helper is wired properly to producer behavior**. The two complement each other; neither replaces the other.

### Boundary Cases Matter Too

For the `ORD-` format followed by at least four digits, test cases might include:

~~~text
Valid:
ORD-0000
ORD-12045

Invalid:
ORD-12
ord-12045
ORD-12A4
null
12045 (JSON number)
~~~

If the real contract adds a checksum or upper bound, test those rules as well. Testing only `ORD-12045` and assuming the helper works for all strings is insufficient.

## 11. JSONPath Types and Method Signatures

A JSONPath evaluation may return:

- `String` for JSON strings.
- `Integer`, `Long`, `BigDecimal`, or another number type.
- `Boolean` for booleans.
- `List` or `Map` for arrays/objects.
- `null` when a field is missing, depending on the library/access method.

Therefore, a helper with the signature:

~~~java
public void assertPositiveAmount(String amount)
~~~

may not match the numeric type returned by the JSON parser. If generated code casts incorrectly, the test may throw `ClassCastException` before the assertion runs.

### Solutions

- Inspect generated code and actual response values.
- Use `Object` as the boundary parameter if you need explicit dynamic type checks.
- Validate type and null explicitly before converting to a domain type.
- Avoid converting every value to `String`, which hides schema type errors.
- For decimals, use `BigDecimal` with appropriate precision/rounding rules; avoid arbitrary `double` equality checks when financial precision matters.

A data-type mismatch **must FAIL the test**; never silently convert numeric strings into numbers and mask a breaking change.

## 12. Distinguishing `byCommand`, `execute`, and `triggeredBy`

These three mechanisms serve different purposes:

| Mechanism | Primary Role | Key Consideration |
| --- | --- | --- |
| **`byCommand(...)`** | Custom matching/assertion command in supported DSL positions | Helper must be invoked by generated tests with the exact signature |
| **`execute(...)`** | References a method computing/supplying dynamic test values depending on DSL/version context | Not synonymous with verifying output |
| **`triggeredBy(...)`** | Specifies the method that triggers the producer to emit a message | Performs an action and may cause side effects |
| **Declarative matchers** | Exact/type/regex/JSONPath conditions | Usually easier to review than custom code |
| **Fixture/setup helpers** | Prepares state before execution | Must not mask producer behavior |

Conceptual example:

~~~text
createOrderId()             -> supplies test input data
assertValidOrderId(actual)  -> verifies received output data
markTestOrderAsPaid()       -> triggers producer to emit a message
~~~

Do not swap `byCommand` and `execute` merely because both involve custom code. Whenever the DSL separates consumer vs. producer sides of dynamic values, verify **which side executes the code** and what stub gets generated.

## 13. HTTP Base Tests Differ from Message Base Tests

A producer may both serve HTTP endpoints and publish messages. Do not assume a single base class should initialize every adapter for every generated test.

Example layout:

~~~text
src/test/resources/contracts/
  orders-http/get_paid_order.groovy
  orders-message/order_paid.yml

src/test/java/com/example/contract/
  HttpOrderContractBase.java
  OrderMessageContractBase.java
  OrderContractAssertions.java
~~~

- HTTP base tests configure MockMvc/HTTP test clients and HTTP fixtures.
- Message base tests provide trigger methods, test binders/brokers, and verify output messages.
- Pure assertion helpers can be reused whenever semantics are genuinely shared.

In many plugin versions, **base class mappings** separate contract groups. Inspect the specific configuration and generated class packages; do not guess property names or generated Java class names.

### Why Not Put Everything in One Base Class?

A single shared class might boot a database, broker, HTTP server, and background schedulers even for a test needing only a simple JSON matcher. That makes tests slow, flaky, and prone to side effects. Splitting base classes by **test scope** avoids unnecessary dependencies.

## 14. Message Contracts and Trigger Methods

YAML example:

~~~yaml
description: "Paid order emits ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: ORD-12045
    schemaVersion: 2
  headers:
    correlationId: CONTRACT-CORR-12045
~~~

`markTestOrderAsPaid()` is a method in the producer test environment that **triggers the real behavior under verification**. It is not an assertion.

Example method in the base class:

~~~java
// Illustrative; services/fixtures belong to the project.
public void markTestOrderAsPaid() {
    // Invoke the real application service with test data.
    // Environment uses a test DB and test broker/binder.
    // Never send production emails, payments, or events.
}
~~~

For producer message tests to be meaningful:

1. The trigger must execute the real message-publishing code path.
2. Output messages are captured by an appropriate test adapter.
3. Tests assert destination, body, and headers per the contract.
4. Out-of-scope dependencies are isolated.
5. Consumers must still be tested separately via Stub Runner or equivalent infrastructure.

**Do not confuse `label` with topic name**; `sentTo` is a logical destination resolved by the adapter and messaging configuration. A passing message contract does not automatically prove production broker exactly-once delivery, ordering, retention, or routing.

## 15. Multi-Field Assertions

A response:

~~~json
{
  "subtotal": 100000,
  "tax": 10000,
  "total": 110000
}
~~~

needs to satisfy:

~~~text
total = subtotal + tax
~~~

Do not assume `$it` in `jsonPath('$.total', ...)` automatically includes `subtotal` and `tax`. The placeholder typically refers to **the value selected by that JSONPath**.

Your options are:

1. Declarative DSL matchers if your version supports an expression with sufficient context.
2. A supplementary producer integration test parsing the **entire JSON body**.
3. A custom command only if generated tests can genuinely pass all required arguments through a mechanism supported by your version.

Pure helper example taking all fields:

~~~java
public static void requireValidTotal(
        long subtotal, long tax, long total) {
    if (subtotal < 0 || tax < 0) {
        throw new AssertionError(
            "subtotal and tax must not be negative"
        );
    }

    long expected;
    try {
        expected = Math.addExact(subtotal, tax);
    } catch (ArithmeticException e) {
        throw new AssertionError(
            "subtotal + tax overflowed", e
        );
    }

    if (total != expected) {
        throw new AssertionError(
            "total must equal subtotal + tax"
        );
    }
}
~~~

This is a Java helper usable from a **handwritten producer integration test**. Do not blindly plug a three-argument call into `byCommand` without verifying whether the generator passes all three values.

## 16. Writing Good Failure Messages in Assertions

A custom assertion should throw errors that are **informative enough** to diagnose failures without exposing sensitive data.

| Pattern | Assessment |
| --- | --- |
| `throw new AssertionError()` | Does not explain which invariant failed |
| `orderId does not match format ORD-<digits>` | Clearer, minimal data exposure |
| `amount must be JSON number; actual was String` | Clearly identifies schema mismatch |
| Dumping full Authorization/response body | Risks leaking secrets or personal data |

Best practices:

- Include the field/JSONPath or invariant name.
- Distinguish between missing/null, wrong type, and wrong value.
- Never swallow exceptions.
- Never modify responses/DBs to make an assertion PASS.
- Log summarized sample values only when confirmed safe.
- Use test framework assertion utilities where appropriate, keeping behavior compatible with the generator.

If a helper checks too many unrelated conditions, consider splitting it into separate matchers so CI reports clearly pinpoint which field failed.

## 17. Side-Effect Risks in Custom Helpers

Naming a method `assertValidOrderId` does not make it read-only. It can still make network calls, access databases, or read secrets using the CI process's privileges.

| Anti-pattern | Problem | Replacement |
| --- | --- | --- |
| Assertion calls a production API | Causes external I/O and availability coupling | Inspect only the captured response |
| Helper calls repository `save` to “fix” data | Produces false-green tests | Separate setup; assertions stay read-only |
| Catching `AssertionError` and only logging | Hides test FAILs | Let the error propagate to the test runner |
| `contains("PAID")` across raw JSON | Can match debug fields | Parse exact `$.status` |
| `System.setProperty` inside helper | Mutates global state for other tests | Configure per instance |
| Fixed `Thread.sleep` | Flaky, slows CI | Poll with predicate and bounded timeout |
| Logging raw request headers | Leaks Authorization/Cookies | Redact sensitive headers |
| Disabling hostname verification | Masks TLS failures | Configure test certificates and truststores |
| Fetching scripts from a URL to validate | Expands build trust boundary | Eliminate I/O, pin dependencies, review code |
| Calling a service to “look up expected response” | Expected values depend on external state | Deterministic fixtures/contracts |

Not all **integration assertions with I/O** are wrong—for instance, a POST must create the right record in the **test DB**. Just name and scope them clearly, document allowed resources, and never hide I/O inside an ID-formatting helper.

## 18. Setup, Assertion, and Cleanup Must Remain Separate

Recommended flow:

~~~text
SETUP:
  verify isolated test environment
  seed synthetic fixture in test database
  configure test-only external clients

ACT:
  generated test invokes producer endpoint/message logic

ASSERT:
  DSL matchers + custom pure helpers inspect actual output
  explicit integration checks inspect allowed side effects

CLEANUP:
  stop async work
  delete only records/resources owned by this test
~~~

Why:

- If an assertion writes expected state before reading, it **no longer verifies the producer**.
- If cleanup wipes an entire shared table/topic, parallel tests can break one another.
- If side effects happen on another thread or server transaction, `@Transactional` on the test does not automatically roll everything back.
- If a scheduler or message consumer keeps running after `@AfterEach`, subsequent tests may see spillover effects.

For CI running parallel tests, use isolated namespaces/IDs, dedicated test DBs/brokers, or strong isolation mechanisms, and verify thread safety of HTTP test clients.

## 19. Sources of False PASS Beyond Helper Logic

A passing test can still lack value when:

1. Generated tests were never generated.
2. `0 tests` executed yet the build stayed green.
3. The base class is not actually extended by the generated tests.
4. The command failed or emitted code that never invokes the helper.
5. The helper returns `boolean false` without the framework asserting it.
6. A fixture/mock returns the hardcoded sample body without exercising producer logic.
7. Matchers were relaxed so far that schema changes go undetected.
8. Consumer tests run against an **older version** of the stub artifact.
9. Test data is too trivial to cover boundary or error cases.
10. Retries or shared mutable state mask failures.

### Negative Checks

An essential technique is intentionally injecting an invalid value in a **controlled isolated test fixture**:

~~~text
orderId = "INVALID"

Expected:
generated producer test FAILS
message: orderId does not match format ORD-<digits>
~~~

If the test still PASSes, inspect the `byCommand` mapping, generated source, and test execution. **Never alter production producer behavior to force a test failure** outside a controlled verification environment.

## 20. When Helpers Become Maintainable Software

Once widely adopted, a custom assertion becomes a dependency for many contract tests. Apply software engineering discipline:

- Name methods after the invariant: `assertValidOrderId` rather than `check`.
- Keep signatures simple with explicit null/type policies.
- Avoid coupling to internal implementation structures outside the contract.
- Maintain independent unit tests and boundary tests.
- Require changelog/review when matcher semantics change.
- Keep state and network I/O out of pure assertion methods.
- Ensure compatibility with the producer's Java, test runner, and plugin versions.
- Avoid creating a monolithic `CommonHelpers` class spanning unrelated domains.

In particular, **changing a helper can alter dozens of contract tests** without touching a single DSL file. Review helpers as **part of the contract surface**, not merely internal utility code.

### When a Helper Is Changed to Accept More Values

If `assertValidOrderId` previously accepted only `ORD-1234` format and is later relaxed to accept any non-empty string, contract validation may silently weaken across every DSL referencing it.

Proper review requires finding all configured callers, comparing old vs. new semantics, and re-running producer tests plus relevant consumer-impact tests.

## 21. Common Errors and Diagnostic Path

| Symptom | Common Cause | First Check |
| --- | --- | --- |
| `cannot find symbol assertValidOrderId` | Base class unused, wrong name/visibility | What does the generated test extend? |
| `ClassCastException` | JSONPath returned a different type | Method signature and actual runtime type |
| JSONPath is always null | Wrong path or missing field | Response body and matcher path |
| Custom helper never fails test | Never invoked or error swallowed | Negative test + generated source |
| Test FAILS before HTTP request | Context/setup error | Spring context, bean startup, fixtures |
| Stub Runner ignores helper | Helpers run on producer side only | Do consumer tests have their own assertions? |
| Message trigger missing | `triggeredBy` points to wrong method | Base test / message test generator |
| Event hits shared broker | Wrong test profile | URL, credentials, binder config |
| Local PASS, CI FAIL | Different runner/plugin/toolchain, flaky fixture | Effective configuration and reports |
| Maven green with `0 generated tests` | Goals/test execution skipped | Plugin logs and Surefire/Failsafe reports |
| CI PASS with stale stub | Version/cache mismatch | Downloaded GAV/classifier/checksum |

Helpful inspection order: **contract discovered → generated source → base class → helper call → test execution → producer behavior → artifact provenance → consumer verification**.

Do not change DSL matchers when the real problem is that the test class failed to compile or CI skipped generated tests.

## 22. CI and Evidence to Retain

~~~mermaid
flowchart TD
    A["Commit DSL + base helper"] --> B["Helper unit tests"]
    B --> C{"PASS?"}
    C -->|No| X["BLOCK"]
    C -->|Yes| D["Generate producer tests"]
    D --> E{"Helper call present?"}
    E -->|No| X
    E -->|Yes| F["Run producer tests"]
    F --> G{"PASS, none skipped?"}
    G -->|No| X
    G -->|Yes| H["Generate/publish stub artifact"]
    H --> I["Pin GAV/version/checksum"]
    I --> J["Consumer Stub Runner tests"]
    J --> K{"Consumer assertions PASS?"}
    K -->|No| X
    K -->|Yes| L["Store evidence and evaluate release"]
~~~

A CI record might capture:

~~~yaml
# Project-defined metadata, not default SCC output.
producer_commit: "abc123_FULL_COMMIT"
contract_revision: "def456_FULL_COMMIT"
helper_tests:
  status: PASS
generated_producer_tests:
  executed: true
  skipped: 0
  status: PASS
stub_artifact:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "SHA256_COMPUTED_FROM_JAR"
consumer_tests:
  stub_coordinate: "com.example.orders:order-service:2.5.0:stubs"
  status: PASS
~~~

Values are illustrative placeholders; CI must compute checksums from actual files and parse real test reports. **Never treat `BUILD SUCCESS` as sole proof** if generated tests were skipped.

## 23. Hands-on Exercises

### Exercise A — Choosing Matchers

A response has `status = PAID` and `orderId` matching regex `^ORD-[0-9]{4,}$`.

**Prompt:** Which conditions should use DSL matchers, and when is a custom helper needed?

**Hint:** Declarative equality/regex suffices here—no helper needed; use a helper only for custom checksums or domain invariants.

### Exercise B — Writing an Amount Helper

`amount` must be a positive JSON number, never a numeric string.

**Prompt:** Write a helper accepting `Object` along with tests for 0, negative numbers, null, strings, and positive numbers.

**Hint:** Check `instanceof Number`, then convert to `BigDecimal` for comparison.

### Exercise C — Wrong Method Signature

The DSL has `byCommand('assertValidOrderId($it)')`, while the base test only has `private boolean checkId(String value)`.

**Prompt:** Analyze errors in method name, visibility, and return type.

**Hint:** Provide an accessible method with the exact name; throw `AssertionError` on failure.

### Exercise D — Helper Never Executed

The generated test still PASSes with `orderId = INVALID`.

**Prompt:** Create a diagnostic checklist.

**Hint:** Inspect generated source, base class mapping, JSONPath, skip flags, and run a negative unit test.

### Exercise E — Relaxed Matcher

Previously the ID had to equal the fixture's `ORD-12045`; the new helper checks only the `ORD-` prefix.

**Prompt:** Assess the risk of false PASSes.

**Hint:** Check whether request correlation is required; relaxing the format can drop an essential constraint.

### Exercise F — Message Trigger

The contract has `triggeredBy: markTestOrderAsPaid()`; the helper simply returns `true` without invoking the producer.

**Prompt:** Why does this fail to verify the message producer?

**Hint:** The trigger must exercise the real publishing path against an isolated test binder/broker.

### Exercise G — Assertion Making Network Calls

`assertValidOrderId` calls a production API to verify the ID exists.

**Prompt:** Rewrite the verification strategy.

**Hint:** Keep helpers pure; isolate separate integration checks strictly to authorized test environments.

### Exercise H — Three-Field Relationship

The response includes `subtotal`, `tax`, and `total`.

**Prompt:** Does `$it` in JSONPath `$.total` automatically provide all three fields? How should this be tested?

**Hint:** Not by default; use a test assertion reading the full response or a verified supported API.

### Exercise I — Skipped Producer Tests

The consumer PASSes with Stub Runner, yet the producer Maven build skips generated tests.

**Prompt:** Is there sufficient evidence of API compatibility?

**Hint:** No; the producer implementation has not been verified against the contract.

### Exercise J — Splitting Base Classes

One `ContractBase` boots MockMvc, Kafka, and schedulers for every HTTP contract.

**Prompt:** Redesign for faster tests and fewer side effects.

**Hint:** Split base classes by HTTP/message scope and reuse pure helper classes.

## 24. Pre-Merge Checklist for Custom Assertions

### Design

- [ ] Concrete justification exists for using a helper over declarative matchers.
- [ ] The helper condition represents an invariant consumers care about.
- [ ] Constraints were not unintentionally weakened.
- [ ] Null, wrong-type, and boundary behaviors are clearly defined.
- [ ] The helper has a descriptive name and clear failure messages.

### Base Test and Test Generation

- [ ] Base class mapping matches the package, and generated tests extend/load the right class.
- [ ] Method is accessible, with name and signature matching the generated call.
- [ ] `byCommand` syntax verified for the actual plugin version.
- [ ] Generated source contains the helper invocation.
- [ ] The helper has standalone unit tests.
- [ ] A negative test causes the generated producer test to FAIL as expected.
- [ ] Generated tests compile, execute, and are not skipped.
- [ ] The base test does not mock out the producer output under verification.

### Safety and Operations

- [ ] Helpers never mutate data just to PASS.
- [ ] No network calls or secret access inside pure assertions.
- [ ] Side effects of integration assertions are documented and isolated.
- [ ] Fixtures are synthetic, deterministic, and cleaned up within test scope.
- [ ] No shared mutable state causing parallel test failures.
- [ ] No logging of Authorization headers, PII, or raw sensitive payloads.
- [ ] Message triggers target test binders/brokers, never production.
- [ ] `@Transactional` is not relied upon as a blanket guarantee for all side-effect rollbacks.

### Compatibility Evidence

- [ ] Contract revision and producer commit are recorded.
- [ ] Generated producer tests genuinely PASS.
- [ ] Stub JAR has the exact artifactId/version/classifier and checksum.
- [ ] Consumer Stub Runner downloads the exact new artifact.
- [ ] Consumer tests include their own business assertions.
- [ ] CI reports state scope and limitations without claiming all production behaviors were tested.

## Conclusion

**Custom assertions** and **helpers in base tests** extend Spring Cloud Contract's verification power when declarative matchers cannot adequately capture a business invariant. Sound design keeps contracts explicit, helpers pure and unit-tested, base classes focused strictly on environment setup, and generated producer tests genuinely calling helpers against **actual producer output**.

Never equate a passing producer-side custom assertion with full consumer compatibility. Stub Runner must still run against the properly versioned artifact, and consumers must maintain their own assertions. CI conclusions are trustworthy only when **producer verification + stub provenance + consumer verification** align on the same revision.

**Remember:** *Prefer declarative matchers when sufficient; use custom helpers deliberately; inspect generated source to confirm invocation; and never use assertions to hide producer bugs or produce false-green tests.*
