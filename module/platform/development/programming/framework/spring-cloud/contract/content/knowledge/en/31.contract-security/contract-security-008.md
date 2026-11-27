# Reviewing Side Effects of Base Tests and Custom Assertions

## Lesson objectives

**Spring Cloud Contract** allows producers and consumers to describe HTTP or messaging behavior using **Groovy DSL** or **YAML DSL**, generate producer-side tests, create stubs for consumers to use via **Stub Runner**, and integrate compatibility checks into CI. When a contract looks like it merely reads an HTTP response, many assume testing is a harmless operation. In reality, **base test classes**, the Spring test context, fixtures, and **custom assertions/helpers** can run code with side effects: writing to databases, sending network requests, publishing messages, creating files, logging sensitive information, or mutating shared state across tests.

Within the **Contract Security** chapter, the lesson **"Reviewing side effects of base tests and custom assertions"** centers on one principle:

> **Contract tests must be real enough to prove producer behavior, yet privilege-bounded, side-effect-isolated, and free of information leaks when running in CI.**

After this lesson, you will be able to:

- Distinguish **Contract DSL**, **generated tests**, **base test classes**, **test fixtures**, and **custom assertions** by execution time.
- Build a threat model for paths that can cause side effects, including during **Spring context startup**.
- Review calls to **databases, HTTP, brokers, filesystems, caches, schedulers**, and real services.
- Keep custom assertions focused on checking outcomes while avoiding I/O, networking, and state mutation.
- Configure isolated test environments, fake data, low privileges, and negative checks.
- Spot cases where a test "PASSES" due to misplaced mocks or assertions hiding bugs.
- Design review checklists and CI gates for HTTP contracts, message contracts, and consumer stub tests.

## 1. Contracts, generated tests, and base tests are not the same thing

A simple producer layout might look like:

~~~text
order-service/
├── src/test/resources/contracts/orders/get_paid_order.yml
├── src/test/java/com/example/orders/contract/OrderContractBase.java
├── src/main/java/com/example/orders/...
└── pom.xml
~~~

The YAML contract file describes behavior:

~~~yaml
description: "Get paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

The Spring Cloud Contract Maven/Gradle plugin can generate tests from the contract, and those tests invoke the producer under the configured mode. The **base test class** provides the setup that generated tests extend or reference. **Custom assertions** are additional verification methods or logic, sometimes called from generated tests or team-written test code.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Contract Verifier<br/>generates tests"]
    A --> C["Converts contract into<br/>stub mappings"]
    B --> D["Generated producer test"]
    E["Base test + fixture + helper"] --> D
    D --> F["Producer implementation<br/>Spring test context"]
    F --> G["DB, outbound HTTP,<br/>broker, cache, filesystem"]
    D --> H["Assertions and test reports"]
    C --> I["Stub JAR / Stub Runner"]
~~~

Distinctions to keep clear:

| Component | Primary job | Can it cause side effects? |
| --- | --- | --- |
| Contract DSL | Specifies request/response or input/output message | Potentially, if Groovy code/extensions are allowed to execute during processing |
| Generated producer test | Exercises specified behavior and checks results | Yes, because the test invokes producer code |
| Base test class | Boots Spring context, configures HTTP/message tests, sets up data | **Yes**, including before and after each test |
| Fixture/helper | Prepares IDs, state, fake data, and dependencies | **Yes**, depending on implementation |
| Custom assertion | Checks conditions after calling producer | **Yes if written with I/O**; never assume it is "read-only" |
| Stub Runner/WireMock | Simulates dependencies for consumer | Can mutate request journal/scenario state; extensions are code too |
| CI runner | Compiles and executes all components above | Can reach any resource the job has permission to access |

**Test code has the same impact capabilities as any other Java code**, bounded only by the privileges of the process running it. Class names containing `Test`, `@BeforeEach` annotations, or `assert...` method names do not create a security sandbox.

## 2. Threat model: which assets and boundaries need protection?

Before reviewing, identify:

- **Assets to protect:** user data, production databases, cloud storage, real queues/topics, CI secrets, Maven repository credentials, logs, and build artifacts.
- **Execution paths:** Groovy contract processing; build plugins; Spring context startup; test setup; HTTP/message producer code; assertions; teardown; stub extensions.
- **Triggers:** PRs modifying contracts/base classes/helpers, new dependencies, CI configuration, environment variables, test profiles, or producer code with side effects.
- **Trust boundary:** repository code permitted to run in CI does not mean it is permitted to reach production or hold publish/deploy rights.

A risk table:

| Side-effect path | Example | Consequence |
| --- | --- | --- |
| **Outbound HTTP** | Fixture calls a real service to "fetch sample data" | Creates real transactions, leaks metadata, ties tests to network |
| **Database** | `@BeforeEach` inserts/deletes against wrong datasource | Mutates data in a shared environment |
| **Message broker** | `triggeredBy` publishes event to staging/production broker | Real consumers process test events |
| **Scheduler/background job** | Spring context starts a job sending emails/payments | Side effects happen even if test only sends GET |
| **Filesystem** | Assertion writes to shared directory, deletes non-test data | Data loss or CI races |
| **Secrets/logs** | Prints HTTP Authorization, tokens, or raw payloads | Leaks into console/artifact reports |
| **Global mutable state** | Test alters static config, JVM system properties, timezone | Alters outcomes of other tests |
| **Unsafe TLS config** | Test disables certificate/hostname verification JVM-wide | Hides security bugs, affects other clients |
| **Custom assertion** | Helper calls another API to verify data | Outcomes depend on external services, can trigger new side effects |
| **Groovy contract code** | Script executes during build instead of pure declarative DSL | Expands code execution under CI permissions |

Thus "side effects" do not mean only database `INSERT`s. **Reading secrets and logging them to unauthorized places are also critical side effects.**

## 3. When can a base test execute code?

A test can trigger side effects **before the first assertion even runs**.

~~~mermaid
sequenceDiagram
    participant CI as CI job
    participant SC as Spring context
    participant BT as Base test
    participant GT as Generated test
    participant EXT as Database / broker / HTTP
    CI->>SC: Initialize application context
    SC->>EXT: Bean startup / lifecycle / schedulers may call outward
    SC->>BT: Instantiate/inject base test
    BT->>EXT: BeforeEach / fixture setup (if present)
    GT->>SC: Send request or trigger message
    SC->>EXT: Business logic may write/read/publish
    GT->>BT: Invoke custom assertion/helper
    BT->>EXT: Helper can do I/O if written unsafely
    BT->>EXT: AfterEach / cleanup (if present)
    GT-->>CI: PASS/FAIL result + logs
~~~

Points to review:

1. **Static initializers** or constructors in test/base classes.
2. `@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll`.
3. Spring bean lifecycle: `@PostConstruct`, `ApplicationRunner`, `CommandLineRunner`, listeners, schedulers.
4. Test configurations and bean overrides.
5. Test fixtures and database/cache resets.
6. Methods invoked from the DSL or generated tests.
7. Assertion helpers, logging interceptors, RestAssured filters.
8. `@Transactional`, test retries, and teardown.
9. Async tasks still running **after the test completes**.

**Special hazard:** starting a Spring context can activate real listeners or jobs. A test sending only `GET` does not prove the whole execution is read-only.

## 4. Designing HTTP base tests: test the real controller while isolating external dependencies

A common pattern for HTTP producer contract tests runs a Spring Boot test context with MockMvc. **Illustrative** example:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public abstract class OrderContractBase {

    @Autowired
    MockMvc mvc;

    @BeforeEach
    void configureContractClient() {
        RestAssuredMockMvc.mockMvc(mvc);
    }

    @AfterEach
    void clearContractClient() {
        RestAssuredMockMvc.reset();
    }
}
~~~

This snippet assumes the producer uses **Spring MVC** and generated tests are configured compatibly with **RestAssuredMockMvc**; packages, dependencies, lifecycle, and base class mappings must match your project's Spring Cloud Contract/Spring Boot versions. If using WebFlux or another test mode, use the corresponding setup rather than copying this example mechanically.

**Important security point:** `webEnvironment = MOCK` does not open a real HTTP server, yet **does not automatically block outbound HTTP, DB, or broker calls** made by producer beans. MockMvc only simulates the inbound HTTP boundary; internal dependencies still require isolation.

### Good design: mock at the system boundary

Suppose the Order controller calls a service, and the service calls an **external payment gateway**. To protect the test environment:

- Keep the critical controller/service path **executing for real**.
- Replace the client talking to the real payment gateway with a **fake/recording client** in the test profile.
- Use a **test-dedicated** database/schema or test DB container.
- Prevent out-of-scope schedulers, email senders, and broker producers from emitting real events.
- Ensure data setup never calls a public API to "create a sample order".

If you mock the HTTP controller method directly to return hardcoded JSON, producer tests can PASS while the real implementation returns a different response. The goal is to **isolate dangerous resources at outbound boundaries**, not mock away the behavior under verification.

## 5. Be careful with annotations and transactions assumed to be "safe"

Several annotations are very useful yet **are not absolute security boundaries**:

| Mechanism | What does it usually do? | What does it NOT guarantee? |
| --- | --- | --- |
| `@SpringBootTest` | Boots application context for test | Does not auto-block real networks, schedulers, brokers, or DBs |
| `webEnvironment = MOCK` | Uses mock web environment instead of real HTTP server | Does not isolate outbound HTTP or bean startup |
| `@Transactional` on test | Can roll back DB changes in the test's own transaction | Does not roll back other threads' transactions, real server requests, or published messages |
| `@DirtiesContext` | Requests refreshing Spring context | Does not undo side effects in external systems |
| Mockito mocks/test fakes | Replaces a dependency per configuration | Does not stop other beans from calling production |
| `@Sql` setup/cleanup | Runs SQL per test scripts | Dangerous if datasource points to wrong DB or cleanup is too broad |
| Testcontainers | Launches isolated test resources | Does not forbid code from calling other URLs or using production credentials |
| `@ActiveProfiles("test")` | Selects profile/test configuration | Does not guarantee every dangerous property is overridden |

### Limits of rollback

Suppose a `@Transactional` test calls the producer over a real HTTP server on a random port. The request executes on a different thread/transaction than the test method. Rolling back the test transaction **is not guaranteed to roll back** database writes committed by that HTTP handler thread.

Likewise, a message already published to an external broker **cannot be undone** by a database rollback.

**Rule:** before relying on `@Transactional` or teardown, verify the exact **execution path, threads, and transaction boundaries** of the behavior being isolated.

## 6. Setting up test data: deterministic, idempotent, and scoped

A safe fixture should:

- Create data in a **test datasource** explicitly verified before writing.
- Use namespaced synthetic IDs: `CONTRACT-ORD-1001`, `TEST-CORR-1001`.
- Never use real user emails, addresses, or tokens.
- Be repeatable without depending on leftovers from a previous job.
- Delete only test-owned records, never run commands wiping entire shared tables/systems.
- Manage transactions, cleanup, and async work deliberately.
- Enforce timeouts when awaiting events or eventual consistency.

Pseudocode example:

~~~text
BeforeEach:
    assert effectiveEnvironment == ISOLATED_TEST
    seed order with ID "CONTRACT-ORD-1001" into test database
    clear only this test's recorded outbound calls

Generated producer test:
    GET /api/orders/CONTRACT-ORD-1001
    assert 200 and agreed JSON response

AfterEach:
    remove records whose owner == current test namespace
    verify no unexpected outbound call was recorded
~~~

This is an **illustrative workflow**, not built-in Spring Cloud Contract API functions. Most importantly, the precondition `effectiveEnvironment == ISOLATED_TEST` must be checked against real configuration, not a self-assigned label unused by the system.

### Avoid out-of-scope state resets

A test sharing a test DB with other jobs that runs `DELETE FROM orders` can break concurrent tests. Using per-job Testcontainers or per-job schemas yields far clearer isolation boundaries.

Similarly, never purge an entire shared topic or directory to clean up one scenario. Use isolated namespaces or short-lived infrastructure per test suite.

## 7. Locking down outbound networking of the test process

An HTTP contract may test only GET, yet the Spring context can still instantiate HTTP clients pointing to payment processors, notification gateways, telemetry endpoints, or service discovery.

Review goals:

1. Inspect **effective base URLs** received by the test process from application properties, system properties, and environment variables.
2. Forbid tests from using production/staging URLs outside the test allowlist.
3. Where possible, run CI with **default-deny egress**, opening only required destinations.
4. Replace external clients with corresponding test doubles, MockWebServer, or WireMock.
5. Record permitted outbound calls and assert **zero unexpected calls**.
6. Ensure retries never accidentally send the same test request to a real endpoint.
7. Never place production tokens inside untrusted PR CI jobs.

### Warning about localhost

`localhost` is safe only within its context. Inside a CI container, it points to that container itself; in Docker Compose, another WireMock container needs its service hostname. A client calling the wrong localhost usually fails, yet if another process happens to listen on the same port, tests can interact with the wrong target.

**Network allowlists and test fixtures must jointly fix the final endpoint**, rather than relying solely on property names like `test.payment.url`.

### Should you use "network calls for assertions"?

A custom assertion calling a production endpoint `GET /orders/{id}` to check "whether the data is real" opens another outbound path. Even a GET can:

- Read sensitive data.
- Trigger rate limiting or audit side effects.
- Depend on external environment availability.
- Break test reproducibility.
- Be exploited via URLs constructed from uncontrolled test data.

If cross-checking an external system is genuinely required, **separate it into a dedicated integration test** with approved permissions/environment rather than hiding it inside a contract test assertion helper.

## 8. Database and persisted state: risks of data leaks and lost isolation

A test can write to a DB through many paths:

- `@BeforeEach` creating fixture rows.
- `POST/PUT/PATCH/DELETE` requests in generated tests triggering producer logic.
- Bean startup running migrations, data initializers, or background workers.
- Custom assertions querying repositories and accidentally triggering updates.
- Overly broad cleanup deletions.
- Retries repeating non-idempotent requests.

### Restricting via test architecture

- Use a dedicated test database or managed-lifecycle test container.
- Use an account granted only test-database permissions, with zero read rights to production.
- Separate schemas per CI job when running in parallel.
- Run migrations only against test DBs, never using real-environment credentials.
- Establish clear test transaction boundaries.
- Assert both **permitted** and **prohibited** side effects.

For example, a valid producer POST test may create one test record. That is an **intentional** side effect in an isolated environment; you should not mechanically forbid all DB writes. What matters is bounded blast radius and proper cleanup.

## 9. Message contracts: triggeredBy can invoke real behavior

Spring Cloud Contract supports message-based contracts. Illustrative YAML example:

~~~yaml
description: "Successful payment emits ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: CONTRACT-ORD-1001
  headers:
    correlationId: TEST-CORR-1001
~~~

In this example:

- `triggeredBy` is the method called by the **generated producer test** to trigger behavior.
- `outputMessage.sentTo` is the logical destination where the producer must send the message per configured adapter/binder.
- `label` helps identify or trigger the stub in consumer tests when integrated properly.
- **Do not mistake** `label` for a topic name or assume the DSL automatically creates a safe broker.

### What to review in trigger methods

A method `markTestOrderAsPaid()` might:

1. Mutate the order database.
2. Call a real payment gateway.
3. Publish `ORDER_PAID` to the configured broker.
4. Invoke email/SMS notifiers.
5. Trigger other listeners in the application.

If `spring.kafka.bootstrap-servers` or the broker URL accidentally points to a shared environment, the test can emit unwanted messages.

**Safety requirement:** use a dedicated test broker/binder, test topic namespace, or controlled fake adapter; document clearly how producer messaging is verified. If using an in-memory binder, never claim full production broker semantics were verified.

### Async side effects outliving the test

A JUnit method finishes while an async consumer or scheduled retry keeps running. Cleanup might delete fixtures before the task ends, or test events might travel onward to another service.

Reviews must check:

- Bounded timeouts and conditional waiting.
- Task/thread lifecycles and shutdown hooks.
- Dedicated event namespaces.
- Topic/consumer-group isolation.
- Cleanup when tests FAIL or CI is canceled.

## 10. Custom assertions should be observation functions, not actions

A name like `assertOrderIsPaid` may lull reviewers into assuming the method is safe. Yet custom assertions are plain Java/Groovy code; they can do anything the test process is permitted to do.

### Design anti-pattern example

~~~text
assertOrderIsPaid(orderId):
    call external payment API to "verify" payment
    update test database to PAID if response differs
    print entire Authorization header on failure
    return true
~~~

The flaw here is not only the external call. The method:

- Mutates state to make outcomes appear as expected.
- Mixes **setup/repair** with **assertion**.
- Masks real producer bugs.
- Risks leaking secrets on failure.
- Can make tests PASS because the assertion fixed the data before comparing.

**Desired design:** an assertion receives **collected outputs**, verifies invariants, and throws an assertion failure when violated — never mutating state to reach the expected outcome.

## 11. Pure custom assertion example with Jackson

A helper checking a JSON response already received from the producer:

~~~java
package com.example.orders.contract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;

public final class OrderResponseAssertions {
    private static final ObjectMapper JSON = new ObjectMapper();

    private OrderResponseAssertions() {}

    public static void assertPaidOrder(String responseBody,
                                       String expectedId) {
        final JsonNode root;
        try {
            root = JSON.readTree(responseBody);
        } catch (IOException e) {
            throw new AssertionError("Response is not valid JSON", e);
        }

        if (root == null || !root.isObject()) {
            throw new AssertionError("Response must be a JSON object");
        }
        if (!expectedId.equals(root.path("id").asText(null))) {
            throw new AssertionError("Order ID does not match contract");
        }
        if (!"PAID".equals(root.path("status").asText(null))) {
            throw new AssertionError("Status is not PAID");
        }
    }
}
~~~

This helper has strong qualities:

- Input is the **already-received response body**, requiring no URLs, databases, or credentials.
- Makes no network calls and writes no files.
- Mutates no producer state.
- Only reads data and throws errors when invariants fail.
- Does not log raw response bodies (which could hold sensitive data).
- Outcomes depend strictly on inputs and are easy to unit test.

**Note:** a custom assertion may be invoked from a handwritten test or from a generated test if your DSL/extension/version supports helper references. Integration syntax varies across Spring Cloud Contract versions; this example illustrates only **safe helper implementation**, without claiming a Java method is invoked automatically by the generator.

### Must a static ObjectMapper always be forbidden?

A standard `ObjectMapper` can be reused once configured and performing thread-safe serialization/deserialization under normal usage—specifically without mutating its configuration after initialization. If a custom assertion alters mapper settings while tests run in parallel, that becomes shared mutable state needing review.

## 12. Do not use assertions to house setup and cleanup logic

A clean separation:

~~~text
Fixture/Setup:
    create test data in an isolated environment
    configure fake dependencies

Act:
    generated test calls endpoint or triggers message

Assert:
    verify response/event and permitted side effects

Cleanup:
    remove test-owned resources
~~~

If an assertion must query a database to verify the effect of a POST, it is an **integration assertion** with I/O, not a pure function. It can still be valid when:

- It accesses only a verified **test database**.
- It reads only records belonging to the current test namespace.
- It never mutates data or triggers further business workflows.
- It uses bounded timeouts and appropriate eventual-consistency handling.
- It puts no raw sensitive data into errors or logs.
- Its I/O is explicitly documented in the test and during review.

In other words, not every assertion with I/O is forbidden; however, **never hide those effects** or cite them as evidence without stating the exact environment.

## 13. Custom assertions must not hide errors or create false PASSes

Common anti-patterns:

| Anti-pattern | Why dangerous | Replace with |
| --- | --- | --- |
| `try/catch` swallowing exceptions | Test can PASS without verifying anything | Re-throw or fail with context |
| `contains("PAID")` across entire JSON | Can match error text or unrelated fields | Parse JSON and check the exact path |
| Deleting/overwriting state before asserting | Hides broken behavior | Assertions only observe; setup stays separate |
| Retrying until any HTTP 200 arrives | Can ignore wrong responses or hit wrong service | Bounded retry with clear endpoint and predicate |
| Logging full payload + headers on FAIL | Leaks tokens, PII | Redact and log only non-sensitive fields |
| Reading `System.getenv("TOKEN")` to verify responses | Pulls secrets into test code paths | Use narrowly scoped test data/credentials |
| Fixed `Thread.sleep` | Flaky, masks race conditions | Awaitility/conditional polling for async cases |
| Mutating system properties/global timezone | Affects other tests | Per-instance clocks/client configs |
| Disabling TLS hostname verification | False greens, widens trust | Dedicated test certificates + truststores |
| Catching `AssertionError` and only logging | Hides failures | Let the test framework report FAIL |
| Embedding business decisions in arbitrary matchers | Hard to review, adds side effects | Clear Contract DSL; minimal pure helpers |

### A passing test can still fail to check the right behavior

If `assertPaidOrder` only checks whether `"PAID"` appears somewhere, this response:

~~~json
{
  "id": "ORD-1001",
  "status": "PENDING",
  "debug": "Last previous status was PAID"
}
~~~

causes the weak assertion to PASS. Section 11's helper checks `status` at the exact JSON path and catches the discrepancy.

**Security and correctness are linked:** weak tests can miss an authorization regression or an unauthorized sensitive field in a response.

## 14. Checking for sensitive data in assertion failures

A test may be functionally correct yet log on FAIL:

~~~text
Request headers:
Authorization: Bearer <token>
Cookie: <session>
Response:
<full payload containing personal data>
~~~

Even with test-environment tokens, storing them in CI logs/artifacts still poses risks, especially on shared infrastructure.

Conventions:

- Never log raw `Authorization`, `Cookie`, API keys, or credentials.
- Never dump full requests/responses when sensitive data may appear; extract only safe fields.
- Redact headers/bodies in test logging filters and exception handlers.
- Never embed secrets in snapshots, Golden Masters, or stub responses.
- Protect test report access and enforce appropriate retention.
- Use synthetic data instead of production data to limit blast radius if logs are shared.
- Verify **redaction actually works** via tests or log inspection, not merely a `// redacted` comment.

### Never use real secret values as expected assertions

A contract must not check responses by embedding a production access token in the DSL. When authentication/authorization behavior needs verifying, use test-only credentials/tokens and a test environment with appropriate permissions.

**Never use `spring.cloud.contract...` configurations or test helpers to force generators to print secret values** for "easier debugging".

## 15. Groovy DSL can execute code during the build

When using Groovy DSL, a contract file is not static YAML data: it is processed in a Groovy/JVM environment per plugin mechanics. Arbitrary calls, imports, extensions, or code can carry varying capabilities across versions and configurations.

Risks to consider:

- A PR modifying the DSL introduces code executing unintended operations.
- Build plugins/extensions fetch network resources automatically.
- Groovy expressions invoke helpers with I/O.
- CI holds production credentials or publish privileges while running unreviewed PRs.

**Never treat Groovy files in untrusted PRs as "just documentation".** The build executes code and dependencies with the CI job's privileges.

Mitigations:

1. Run PR builds in environments restricting secrets/credentials, especially for untrusted sources.
2. Enforce appropriate network egress policies.
3. Require code-level review of DSL changes.
4. Restrict allowed helpers/extensions and audit dependencies.
5. Never run publish/deploy jobs on contract PRs before approved review.
6. Trace contract revisions alongside artifacts and producer verification.

### Is YAML DSL completely harmless?

YAML is typically a declarative representation, yet it can trigger **generated tests, expressions/helpers, and producer code** when executed. Thus, YAML data alone does not turn the entire pipeline into read-only execution.

## 16. When are custom execution/matchers justified?

Spring Cloud Contract supports matchers and dynamic value expressions. Depending on version, features may exist to invoke test helper code or expressions.

Selection principles:

- **Prefer declarative DSL matchers** when conditions are JSONPath, regex, type, status, or simple header checks.
- Use helpers only when a meaningful business invariant **cannot be expressed clearly** with built-in matchers.
- Keep helpers short, pure, independently unit-tested, and free of network calls.
- When producer side effects must be verified, write an **explicitly documented integration assertion** with restricted access to test resources.
- Never put complex arbitrary code into contracts to replace a dedicated service-level integration test.

### Illustrating an explicit matcher

~~~yaml
description: "Get an order with a specific status"
name: get_paid_order
request:
  method: GET
  url: /api/orders/CONTRACT-ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CONTRACT-ORD-1001
    status: PAID
~~~

This example verifies `status` accurately without needing an I/O-heavy custom assertion. If IDs vary per test, use a suitable matcher while still protecting the format/semantics the consumer depends on.

### Distinguish matchers from mocks

A response body matcher checking producer output differs from a stub returning a sample response. If a generated producer test supplies a sample response via a mock controller and then asserts that same sample, the test risks **proving itself** rather than verifying the implementation.

## 17. Classifying side effects: permitted, must-isolate, or prohibited

Do not adopt a blanket rule that "every side effect in tests is wrong". For example, a POST contract creating an Order requires the producer to write to a DB to prove business behavior. The real question is whether **the side effect is intentional and isolated**.

| Side effect | Suggested classification | Conditions |
| --- | --- | --- |
| Writing records to a test DB container | Acceptable | Test privileges, isolation, cleanup, and explicit assertions |
| Emitting events to an in-memory test binder | Acceptable | Proves payload/headers; document limits vs real broker |
| Sending HTTP to a WireMock test service | Acceptable | Exact URL, network isolation, no unexpected requests |
| Creating files in a test temp directory | Acceptable | Strictly within granted path, scoped cleanup |
| Reading non-sensitive test config | Usually acceptable | No secret logging or global mutations |
| Calling a real payment gateway | Unacceptable in isolated contract tests | Replace with test double; if external integration needed, separate approved test |
| Writing to production/staging DB | Unacceptable | Block via credentials and network restrictions |
| Publishing to a real shared broker topic | Unacceptable if it affects others | Dedicated test topic/broker |
| Printing credentials/PII to CI logs | Unacceptable | Redact, use fake data |
| Assertion mutating results to PASS | Unacceptable | Separate setup, pure assertions |
| Disabling TLS verification JVM-wide | Unacceptable as a valid test practice | Test-specific SSLContext with narrow trust material |

**Exceptions for integration tests** must be evaluated separately: an e2e test might intentionally call an isolated staging environment; it must never be quietly mixed into default contract verification.

## 18. How to test permitted side effects without dangerous side effects

A producer POST may need to verify:

- HTTP status `201`.
- Response body contains `id`.
- Test database contains exactly one Order.
- Exactly one `ORDER_CREATED` event was produced on the test binder.
- Zero unexpected outbound email/payment calls occurred.

One model:

~~~mermaid
flowchart TD
    A["Fixture creates dedicated test environment"] --> B["Generated producer test: POST /orders"]
    B --> C["Real producer controller + service"]
    C --> D["Test database"]
    C --> E["Test event binder"]
    C --> F["Mock external payment client"]
    D --> G["Assert exact test-owned record"]
    E --> H["Assert exact event"]
    F --> I["Verify no unexpected external call"]
    G --> J["Bounded PASS"]
    H --> J
    I --> J
~~~

Key points:

- Do not mock the controller to return status 201 if the goal is testing producer implementation.
- Never use a real DB outside test scope.
- Never treat a fake binder as proof that production brokers enforce routing/exactly-once semantics.
- Assertions verify **intended effects** and confirm **no unlisted effects occurred** when safety is an acceptance criterion.

## 19. Test isolation under parallel runs and CI retries

A contract test can PASS alone yet FAIL or cause unintended effects when run in parallel:

- Test A mutates static `RestAssuredMockMvc` configuration; Test B picks it up accidentally.
- Two tests share the same Order ID and delete each other's fixtures.
- One test purges a topic while another is still awaiting a message.
- A background job keeps running past `@AfterEach`.
- Retries resend a non-idempotent POST repeatedly.
- CI jobs share a local Maven repository, causing consumers to load the wrong stub revision.
- JVM-wide properties like `javax.net.ssl.trustStore` are mutated between tests.

### Ways to reduce risk

1. Prefer **per-instance client configuration**, avoiding global mutable state.
2. Use per-test IDs/namespaces and ownership-scoped cleanup.
3. Use separate test brokers/databases per job or suite when needed.
4. Never retry side-effecting requests unless idempotency is defined.
5. Manage lifecycles of async tasks and resources.
6. Restrict parallelism on tests still sharing state until refactored.
7. Run tests **both isolated and in parallel** to catch races.
8. Tag artifacts and reports with build ID, contract revision, and checksum.

### Retries cannot erase an already-executed side effect

A test sending a POST that times out and retries can create **two** records if the endpoint is not idempotent. A final PASS HTTP result does not guarantee zero duplicate side effects.

If the contract requires idempotency, document headers/tokens and repeat-request scenarios explicitly; otherwise avoid unreviewed automatic retries.

## 20. CI sandbox: never place secrets where unreviewed code can read them

If a PR can edit Groovy contracts or base test classes, the PR build **executes unmerged code**. Never grant sensitive privileges to that job.

A safe CI policy might enforce:

- PR verification runs with restricted test credentials and zero production cloud tokens.
- Untrusted PR builds receive no deploy/release publish permissions.
- Network egress is restricted; repository/download endpoints are allowlisted as needed.
- Test databases/brokers are ephemerally provisioned and self-destructing.
- Test reports and artifacts are scanned/redacted before broad sharing.
- Stubs publish only after code/contracts are reviewed and producer verification PASSES.
- Audit trails record which job published which artifacts and from which commit.

**Containers are not automatically absolute sandboxes.** Mounting host credentials, the Docker socket, or cloud admin roles into a test container still lets code inside cause broad damage. Evaluate real permissions, not merely whether tests run "in Docker".

## 21. Reviewing dependencies and plugin extensions

Beyond custom-written code, test dependencies or extensions can also introduce side effects during:

- Class static initialization.
- Test framework extensions.
- Logging filters.
- HTTP client interceptors.
- Custom ObjectMapper serializers/deserializers.
- Spring `@TestConfiguration`, bean factories, and lifecycles.
- Build plugins or contract DSL helper libraries.

Conventions:

1. Pin plugin/library versions via BOM/build policy.
2. Review new dependencies when they run in CI holding credentials.
3. Ensure test code never downloads mutable scripts or artifacts at runtime.
4. Never assume every test plugin only reads files.
5. Verify different classpaths/test profiles do not accidentally enable production connectors.
6. If extensions process contracts, document execution boundaries and permitted side effects.

When test behavior looks abnormal, inspect plugins/versions and effective configuration before editing the contract.

## 22. What cannot be concluded just because tests PASS

A passing generated producer contract test indicates:

- The configured test implementation satisfies the **generated scenario**.
- Assertions for that scenario ran and found no violations.
- The test environment's fixtures and dependencies allowed that execution path.

However, it **does not automatically prove**:

- The Spring context caused zero side effects outside observed paths.
- No secrets were logged in another test.
- No outbound calls to production happen in other environments.
- All authorization rules or security policies were tested.
- Custom assertions are guaranteed side-effect-free.
- Old consumers handle the new stub.
- TLS/mTLS, broker delivery semantics, and rolling deployments are all safe.
- Generated tests covered every API/path.

Therefore, two separate yet related sets of evidence are required:

1. **Contract correctness:** producer and consumer conform to agreed behavior.
2. **Test-environment safety:** processes are privilege-bounded, resources are isolated, and zero unauthorized side effects occur.

## 23. Sample review matrix for base tests and assertion helpers

A team-maintained table:

| Component | Trigger | Has I/O? | Resource | Permitted? | How verified |
| --- | --- | --- | --- | --- | --- |
| Spring context startup | Each test context | Possible | HTTP, broker, DB | Test resources only | Review bean startup, egress audit |
| `@BeforeEach seedOrder` | Each generated test | Yes | Test DB | Conditionally | Verify datasource + cleanup |
| `markTestOrderAsPaid` | Message `triggeredBy` | Yes | DB + binder | Conditionally | Test broker isolation, event assertions |
| `assertPaidOrder` | After HTTP response | No | In-memory JSON | Yes | Unit tests for helper |
| `assertOrderPersisted` | After POST | Read I/O | Test DB | Conditionally | Read-only query, test namespace |
| Logging filter | Each HTTP test | Yes | CI logs | Restricted | Redaction tests |
| Stub Runner setup | Consumer test | Network/file | Maven repo + local stub | Conditionally | Pin artifact, checksum, port |
| Teardown | After test | Yes | DB/files/topic | Conditionally | Ownership-scoped cleanup |

Reviewers can require authors to fill in **"Has I/O?"** and **"Resource"** rather than merely writing "safe helper".

### Distinguishing action types

- **Read:** can expose sensitive data or generate audit logs.
- **Write:** mutates state; needs cleanup and low privileges.
- **Outbound call:** can exfiltrate data or issue unwanted commands.
- **Async side effect:** effects can occur outside the test window.
- **Global state mutation:** causes cascading errors across tests.

## 24. Automated CI checklist to catch violations

A pipeline cannot prove "zero side effects anywhere" using static checks alone, yet can detect many warning signs.

| Check gate | What to verify |
| --- | --- |
| Preflight environment | URLs/DSNs point to test resources, zero production credentials |
| Network policy | Outbound egress outside allowlist is blocked |
| Contract discovery | Exact expected set of DSLs discovered |
| Generated test execution | Tests actually run, not skipped or 0 tests |
| Base test review | Setup/teardown and bean startup reviewed |
| Assertion unit tests | Pure helpers give consistent outputs for inputs |
| Side-effect verification | Zero unlisted outbound calls; DB/event changes strictly scoped |
| Secret scanning | Zero credentials/PII in DSLs, fixtures, artifacts |
| Log redaction check | Authorization/Cookie/tokens unexposed when tests FAIL |
| Artifact provenance | Stub GAV/version/classifier and checksum match producer build |
| Consumer CI | Stub Runner uses exact artifact; consumer assertions PASS |
| Parallel/isolation | No shared state/races when CI runs concurrently |

These are **CI governance recommendations**, not features automatically enabled by Spring Cloud Contract.

## 25. Practice exercises

### Exercise A — GET contract with production side effect

Base test uses `@SpringBootTest`. An `ApplicationRunner` bean in the application context sends emails at startup, even though generated tests only run GET.

**Task:** identify when the side effect occurs, how to isolate it, and required review evidence.

**Hint:** Spring context startup; replace email sender with a test fake, isolate credentials/egress, assert zero outbound sends.

### Exercise B — Test using the wrong datasource

`@BeforeEach` runs `DELETE FROM orders`. The developer assumes `@Transactional` protects it, yet the active datasource points to staging.

**Task:** assess the risk and redesign the fixture.

**Hint:** enforce test-only datasources/credentials, test-specific schemas/containers, and fail-fast environment checks; never rely on rollback to permit dangerous operations.

### Exercise C — Custom assertion mutating state itself

`assertOrderPaid` calls `updateOrderStatus("PAID")` before re-reading the record.

**Task:** why is this an invalid assertion? Write an alternative approach.

**Hint:** setup creates fixtures, act calls producer, assert only reads post-act state; never mutate data to make tests PASS.

### Exercise D — Token leak when test FAILS

A logging filter prints raw `Authorization` and response body upon receiving 401.

**Task:** propose logging rules and a way to verify redaction.

**Hint:** log method/path and status, redact sensitive headers, use test-only tokens; inspect logs of a controlled failing test.

### Exercise E — Message trigger sending to real broker

A message contract has `triggeredBy: markTestOrderAsPaid()`. The method emits `ORDER_PAID` to a broker URL read from a shared laptop environment variable.

**Task:** specify how to block this risk before execution.

**Hint:** dedicated test binder/broker, test-only profiles and credentials, egress isolation, verify actual target, clean up/stop async tasks.

### Exercise F — Transaction rollback not covering HTTP request

A test has `@Transactional` and sends a request to the producer running an HTTP server on another thread. Afterward, the DB still holds a new Order.

**Task:** explain why and propose suitable isolation/cleanup.

**Hint:** rolling back the test thread does not automatically roll back server-thread transactions; use a dedicated test DB, namespaces, or controlled cleanup.

### Exercise G — Weak regex/assertion

The response contains `status: PENDING` and `debug: "Previously PAID"`; a custom assertion checks whether the response JSON string contains `PAID`.

**Task:** fix the assertion to check the exact JSON field and explain why the old checker gave a false PASS.

**Hint:** parse JSON and compare `status` accurately; never log raw payloads on FAIL.

### Exercise H — Contract PR from an untrusted source

A PR adds a Groovy contract and custom helper; PR CI has credentials to deploy to a remote Maven repository.

**Task:** identify the trust boundary and permissions that must be separated.

**Hint:** PR verification must hold no deploy/production credentials; restrict egress, review Groovy as code, and publish via a separate approved job.

### Exercise I — Parallel CI corrupting state

Two generated tests share an Order ID; the first deletes the fixture before the second finishes.

**Task:** provide two ways to keep tests from interfering with one another.

**Hint:** per-test namespaces or DB/transaction isolation; avoid global cleanup and manage thread lifecycles.

### Exercise J — Production verification or mock verification?

The base test mocks `OrderController` directly to return JSON from the contract DSL, whereas the real producer might return different fields.

**Task:** why is a passing generated test meaningless here? At which layer is mocking more appropriate?

**Hint:** keep the real controller/service path; fake external gateways/networks/brokers at dangerous boundaries, never mock the very output under verification.

## 26. Review checklist before running and releasing contract tests

### Environment and permissions

- [ ] Build/test processes use **test-only credentials** with low privileges.
- [ ] Zero production URLs/databases/brokers appear in effective test configuration.
- [ ] For unreviewed PRs, CI withholds sensitive secrets and publish privileges.
- [ ] Network egress is restricted; unexpected outbound calls are detected.
- [ ] Test DB/broker/storage has clear isolation, naming, and cleanup.
- [ ] `@Transactional` is never relied upon to claim all external side effects roll back.
- [ ] Background jobs, schedulers, and app startup hooks are reviewed.

### Base tests and fixtures

- [ ] Base test class maps accurately to generated producer tests.
- [ ] Spring test mode (MockMvc/WebFlux/real server) is properly understood.
- [ ] Setup/teardown never accesses resources outside test scope.
- [ ] No cleanup deletes data outside the test's ownership.
- [ ] Fixtures are deterministic, synthetic, and reproducible.
- [ ] No shared static mutable state interferes with other tests.
- [ ] Retries of non-idempotent requests are evaluated.
- [ ] Async tasks are awaited/stopped in a controlled manner.

### Custom assertions and DSL

- [ ] Custom assertions prefer **pure functions** taking observed results.
- [ ] If a helper performs I/O, resources and access rights are explicitly documented.
- [ ] Assertions never mutate state to force tests to PASS.
- [ ] `AssertionError` is never swallowed; matchers are not overly broad.
- [ ] Assertions check exact JSON paths/fields/semantics needed by consumers.
- [ ] Tokens, Cookies, raw PII, and sensitive responses are never logged on FAIL.
- [ ] Groovy DSL/extensions are reviewed as code executable during the build.
- [ ] No custom helper downloads unpinned scripts/artifacts.

### Producer, stub, and consumer evidence

- [ ] Generated producer tests actually generate and execute PASS.
- [ ] No required tests are skipped or silently count 0 tests.
- [ ] Base test invokes the producer code under verification, without mocking endpoint outputs.
- [ ] Stub mappings/JARs are generated from the exact contract revision.
- [ ] Artifact GAV/classifier/version/checksum are recorded.
- [ ] Consumer Stub Runner fetches the exact producer-verified artifact.
- [ ] Consumer tests include business assertions, not merely checking that stubs booted.
- [ ] CI logs, reports, and artifacts contain no sensitive data.
- [ ] Limits of HTTP/message tests, TLS, brokers, and production deployment are stated clearly.

## Conclusion

**Base tests and custom assertions are executable code**, not harmless contract accessories. They can touch databases, send HTTP requests, emit messages, read secrets, write files, or mutate shared state across tests. Consequently, security review cannot stop at checking whether the DSL looks clean: inspect **the entire execution path from plugin/generator to Spring context, fixtures, producer implementation, assertions, and teardown**.

The right practice is keeping **the producer behavior under verification** as real as possible while isolating **dangerous boundaries** via test-only credentials, dedicated DBs/brokers, network policies, deterministic fixtures, and narrowly scoped helpers. A PASS result must be backed by evidence that tests genuinely ran, stub artifacts came from the right origin, and consumer verification ran appropriately.

**Remember:** *An assertion should never modify what it is verifying; a base test must not gain privileges to impact production merely because it carries "test" in its name; and a green pipeline does not mean safety if side effects remain uncontrolled.*
