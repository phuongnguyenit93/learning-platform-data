# Context Scope, Test Fixtures, and Isolation Between Operations

## 1. Why Do Scope and Isolation Matter?

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Each test executes an operation, verifies the response, and writes generated snippets such as HTTP request, HTTP response, request fields, response fields, headers, or links. These snippets are included in Asciidoctor/Markdown and published with the build.

When multiple tests run inside one JVM and share an application context, fixtures, or the generated snippets directory, you need to determine which data belongs to which test. When scope is unclear, common failures include:

- A test overwrites another operation's snippets because they share an identifier.
- Tests depend on execution order because they mutate the same fixture or database rows.
- A documentation context is created once and reused across multiple test invocations.
- Parallel tests write into the exact same file.
- Leftover mocks or mutable state remain from a prior operation.
- Individual tests pass in isolation, yet the full suite fails.
- Documentation is compiled from stale snippets or fixtures that do not match the operation.

This lesson distinguishes three scopes: **documentation context**, **test fixture**, and **snippet/output**. The practical rule is that one test documents one clearly named HTTP scenario, uses reproducible fixtures, produces non-conflicting snippets, and cleans up the state it owns.

## 2. What Is a Documentation Context?

REST Docs needs to know which test is generating snippets, along with context metadata and the output directory. With JUnit Jupiter, `RestDocumentationExtension` integrates into the extension lifecycle and provides `RestDocumentationContextProvider`.

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }
}
```

The provider is injected into the callback for the current test. MockMvc configuration uses that provider so `document(...)` calls are bound to the corresponding context.

Do not save a provider or documentation context from one test and arbitrarily reuse it for another test. Let the extension manage the lifecycle in Jupiter. For frameworks without built-in extension integration, `ManualRestDocumentation` requires explicitly calling `beforeTest(...)` and `afterTest()` for each test.

### 2.1. Documentation Context vs. Spring ApplicationContext

A Spring project can cache and reuse `ApplicationContext` across tests. That context holds application beans and configuration. The documentation context is a separate context dedicated to recording snippets.

| Scope | Holds/Coordinates | Lifecycle |
| --- | --- | --- |
| Spring `ApplicationContext` | Beans, controllers, services, converters, filters, security config | Can be cached and reused |
| REST Docs documentation context | Context for recording a test and generating snippets | Per test lifecycle |
| Test fixture | Inputs, test data, and supporting state | Created/reset per scenario |
| Snippet identifier | Output directory name for an operation | Unique for differing content |

A Spring application context can be shared if beans and environment are designed appropriately. That does not mean a mutable documentation context or mutable fixture state can also be safely shared.

## 3. Scoping Per Test Invocation

In JUnit Jupiter, `@BeforeEach` and `@AfterEach` run for every test method invocation. For parameterized tests, setup/cleanup applies to each invocation. This is the right place to prepare fixtures and configure the test client attached to the documentation provider.

```java
@ExtendWith(RestDocumentationExtension.class)
class AccountDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @AfterEach
    void tearDown() {
        // Release mutable resources created by the test, if any.
    }
}
```

You do not necessarily have to rebuild every application component for each test. You can use a cached Spring context, immutable fixtures, or shared factories. What matters is that mutable state has a clear owner and reset strategy.

| Element | Recommendation |
| --- | --- |
| Documentation context | Provisioned separately per test invocation |
| Snippet identifier | Distinct per operation/scenario with differing content |
| Request body and expected response | Explicit scenario-specific fixture |
| Mock expectations/history | Reset or create independent mocks |
| Database rows created by tests | Use isolated data or reset |
| Test clock/random seed | Fixed so output is reproducible |
| Immutable DTOs/constants | Safe to share |
| Immutable application context | Can use Spring TestContext caching |
| Mutable singleton state | Avoid or reset between tests |
| Generated snippet files | Never let two tests write to the same path |

`@BeforeAll` is suitable for expensive yet immutable resources. Never place mutable per-operation fixtures in `@BeforeAll` and let tests mutate them concurrently or sequentially.

## 4. One Operation, One Clear Fixture

Suppose an Orders API has the following operations:

| Operation | Request | Expected Result |
| --- | --- | --- |
| Get order | `GET /api/orders/42` | `200` with order representation |
| Create order | `POST /api/orders` | `201` with appropriate response/location |
| Cancel order | `POST /api/orders/42/cancel` | Contract-defined status, e.g. `204` |
| Not found | `GET /api/orders/404` | `404` with error representation |

Each scenario should have a fixture reflecting the exact state to document. Do not share one mutable object and mutate its status, items, and payment across order-dependent tests.

Example factory creating fresh fixtures:

```java
final class OrderFixtures {

    private OrderFixtures() {}

    static OrderResponse confirmedOrder() {
        return new OrderResponse(
                "ORD-42", "CONFIRMED", 250000,
                List.of(new OrderItem("BK-01", 2)));
    }

    static OrderResponse cancelledOrder() {
        return new OrderResponse("ORD-43", "CANCELLED", 0, List.of());
    }
}
```

Each factory call creates a new object. If a fixture uses mutable collections, create a fresh collection instead of returning a static list that can be mutated.

A good factory highlights the data that matters to the scenario. Avoid global builders with implicit state like `currentOrder` or `lastResponse`, because tests may end up depending on whichever test ran previously.

### 4.1. Immutable Fixtures

Records and immutable collections help prevent tests from accidentally mutating fixtures:

```java
record OrderItem(String sku, int quantity) {}

record OrderResponse(
        String orderId,
        String status,
        long totalAmount,
        List<OrderItem> items) {

    OrderResponse {
        items = List.copyOf(items);
    }
}
```

`List.copyOf` creates an unmodifiable snapshot of the list. If a test needs a different state, build a new fixture with a factory/builder rather than mutating a shared fixture.

## 5. Isolating Databases, Mocks, and External Dependencies

Generated snippets are only valuable when responses reflect the prepared test data accurately. When an endpoint calls repositories, message brokers, payment gateways, or other systems, clarify which layer the test targets:

- For isolated controller tests, mock services/repositories and define explicit return values.
- For integration tests, use an appropriate database/test container and prepare isolated data.
- For external APIs, use stubs/mock servers or test doubles; avoid calling real external systems unintentionally.
- Verify whether transaction rollback actually applies to the request. Requests running on another thread or server/client process may sit outside the test method's transaction.
- Clean up data or reset mocks after each test if fixtures could affect other tests.

Example service stub:

```java
private final OrderService orderService = mock(OrderService.class);

@BeforeEach
void prepareOrder() {
    reset(orderService);
    given(orderService.findById("42"))
            .willReturn(OrderFixtures.confirmedOrder());
}
```

The snippet above assumes Mockito and a matching test setup. If a mock is shared through the Spring context, reset interactions/behavior appropriately or re-stub explicitly. Never assume a mock bean in a cached context is automatically independent across methods.

## 6. Each Operation Needs Its Own Snippet Identifier

`document("...")` selects the snippet directory name. If two different tests both write `orders-get`, they may share the output path. The later write can overwrite the output so it no longer represents the intended scenario.

Name identifiers by resource + operation + outcome:

```java
.andDo(document("orders-get-success"))
```

```java
.andDo(document("orders-get-not-found"))
```

```java
.andDo(document("orders-create-validation-error"))
```

Identifiers should be stable, describe the operation/outcome, avoid timestamps or random UUIDs, and never collide across parallel tests.

Example directory layout:

```text
build/generated-snippets/
├── orders-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
├── orders-get-not-found/
│   ├── http-request.adoc
│   └── http-response.adoc
└── orders-create-validation-error/
    ├── http-request.adoc
    └── http-response.adoc
```

If multiple tests add snippets for the same operation, consolidate them into one clear test or give each scenario its own identifier. Never let two tests write to the same identifier with different responses.

## 7. MockMvc Example with Per-Operation Fixtures

The example below demonstrates two independent operations: fetching an existing order and fetching a missing order. Each test has its own fixture, assertions, and snippet identifier.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.springframework.http.HttpStatus.NOT_FOUND;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderOperationDocumentationTest {

    private final OrderService orderService = mock(OrderService.class);
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        reset(orderService);
        mockMvc = MockMvcBuilders.standaloneSetup(
                    new OrderController(orderService))
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void getExistingOrder() throws Exception {
        given(orderService.findById("42"))
                .willReturn(new OrderResponse("ORD-42", "CONFIRMED", 250000));

        mockMvc.perform(get("/api/orders/{id}", "42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andDo(document("orders-get-success",
                        responseFields(
                                fieldWithPath("orderId").description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order processing status"),
                                fieldWithPath("totalAmount")
                                        .description("Total amount in VND")
                        )));
    }

    @Test
    void getMissingOrder() throws Exception {
        given(orderService.findById("404")).willReturn(null);

        mockMvc.perform(get("/api/orders/{id}", "404")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andDo(document("orders-get-not-found"));
    }

    interface OrderService {
        OrderResponse findById(String id);
    }

    record OrderResponse(String orderId, String status, long totalAmount) {}

    @RestController
    static class OrderController {
        private final OrderService service;

        OrderController(OrderService service) {
            this.service = service;
        }

        @GetMapping("/api/orders/{id}")
        OrderResponse get(@PathVariable String id) {
            OrderResponse order = service.findById(id);
            if (order == null) {
                throw new ResponseStatusException(NOT_FOUND);
            }
            return order;
        }
    }
}
```

This is a structural illustration. In a real project, controllers/advice should use real implementations or appropriate test configurations. The key point is that the not-found test does not depend on the success test having run beforehand to set up data.

## 8. Parameterized Tests While Preserving Isolation

Parameterized tests are useful when the same operation needs to test multiple values. Each invocation is a separate run, so snippet identifiers must be derived from meaningful, normalized parameters.

```java
@ParameterizedTest
@CsvSource({
    "42, ORD-42",
    "43, ORD-43"
})
void getOrder(String id, String expectedOrderId) throws Exception {
    given(orderService.findById(id))
            .willReturn(OrderFixtures.order(expectedOrderId));

    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(expectedOrderId))
            .andDo(document("orders-get-" + id));
}
```

If parameters contain arbitrary data, do not use strings with unsafe path characters directly as identifiers. You can map each case to a static name via `Arguments` or a controlled scenario key.

Do not use the same identifier for all invocations. If multiple invocations only verify assertions and only one representative fixture should appear in documentation, extract a dedicated documentation test. Output will stay focused on scenarios valuable to readers.

## 9. Isolation During Parallel Test Execution

Parallel execution shortens suite duration, yet shared resources must be audited:

- Application contexts containing singleton beans with mutable state.
- Shared mocks and interaction history.
- Database schemas/tables or records sharing keys.
- Shared ports, files, or temporary directories.
- Snippet identifiers and generated output files.
- System properties, clocks, locales, or environment variables.
- Stateful static fixtures/builders.

Two tests with separate documentation contexts can still collide if they write the same snippet identifier. A separate documentation context does not automatically create a unique output namespace for every operation.

If isolation is not yet guaranteed, configure the documentation test group to run sequentially. Later improve it with independent fixtures, distinct identifiers, isolated resources, or controlled partitioned output directories. Do not turn on parallel execution simply because JUnit supports the feature.

### 9.1. When Can MockMvc Be Shared?

MockMvc can be reused if its configuration and dependencies are immutable. However:

- If MockMvc was created with a documentation configuration bound to a specific test's context, do not carry that instance into another test.
- If MockMvc uses a stable application context, it can be shared per Spring test setup; the documentation configurer/filter must match the test currently generating snippets.
- Never mutate shared interceptors, filters, or result handlers while another test is running.
- Never let shared mock/service/database state create dependencies between requests.

Prefer a clean setup: Spring-managed MockMvc when using a real application context; or build MockMvc inside `@BeforeEach` with the test's provider when per-invocation documentation contexts are needed.

## 10. ManualRestDocumentation and Manual Cleanup

With TestNG, Spock, or frameworks without a Jupiter extension, authors must keep the lifecycle explicit:

```java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation();

@BeforeMethod
public void before(Method method) {
    restDocumentation.beforeTest(getClass(), method.getName());
    // Create/configure HTTP client using this provider.
}

@AfterMethod(alwaysRun = true)
public void after() {
    restDocumentation.afterTest();
}
```

Never share an active `ManualRestDocumentation` across concurrent tests. Each test invocation needs its own context and a matching before/after pair. Cleanup must run even when assertions fail; use the framework's final cleanup hook and ensure teardown is never skipped.

One test context can generate multiple operation snippets, yet each `document("identifier")` call needs its own name. Context scope and operation identifier are two distinct levels.

## 11. Organizing Documentation and Builds Per Operation

Asciidoctor includes snippets by identifier:

```adoc
= Order API
:snippets: build/generated-snippets

== Get Order

=== Existing Order
include::{snippets}/orders-get-success/http-request.adoc[]
include::{snippets}/orders-get-success/http-response.adoc[]
include::{snippets}/orders-get-success/response-fields.adoc[]

=== Order Not Found
include::{snippets}/orders-get-not-found/http-request.adoc[]
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

The path assumes Gradle output in `build/generated-snippets`. With Maven it is usually `target/generated-snippets` or another configured location. Use a single consistent configuration source for tests and Asciidoctor.

The build should run snippet-generating tests before the documentation compilation task. CI should catch tests failing due to assertions/descriptors, duplicate identifiers, stale snippets from bad task ordering, unstable fixtures, and output race conditions.

Never hand-edit generated snippets to fix output. Fix the test, fixture, or descriptor and re-run the snippet-generating task.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Two operations overwrite snippets | Shared identifier | Separate identifiers by operation/outcome |
| Order-dependent tests | Mutable fixtures or unreset state | Create fresh fixtures / reset dependencies per test |
| Individual test passes, full suite fails | Shared mocks/database/static state | Isolate mutable state |
| Snippet captures previous scenario's response | Stub not reset | Reset and stub inside the corresponding test |
| Documentation context used by wrong test | Keeping provider/context outside lifecycle | Let extension manage it or call manual lifecycle per invocation |
| Parallel tests write to the same file | Duplicate identifier/output location | Partition output or run sequentially |
| Parameterized test overwrites snippets | Every invocation uses the same identifier | Generate unique identifiers or have a representative doc test |
| Cleanup only runs on success | Teardown placed inside test body | Use `@AfterEach` or an always-run hook |
| Fixtures vary across runs | Unpinned clock, random values, or data ordering | Fix clock/seed and test data |
| Asciidoctor uses stale snippets | Incorrect task dependency | Run snippet-generating tests before Asciidoctor |

## 13. Checklist for Designing an Operation Test

- [ ] What operation and outcome need to be documented?
- [ ] Which documentation context does the test invocation receive?
- [ ] Is the HTTP client configured with the corresponding context?
- [ ] Are request/response fixtures freshly created or immutable?
- [ ] Are mocks and external dependencies explicitly stubbed/reset?
- [ ] Are database state and transaction cleanup scoped properly to the request?
- [ ] Is the snippet identifier unique, stable, and non-colliding?
- [ ] Does the test include necessary status/headers/body assertions?
- [ ] Do descriptors accurately reflect the payload for that operation?
- [ ] Is the test safe when running in a suite or in parallel?
- [ ] Does Asciidoctor include the right identifier and have proper task dependencies?

Not every project needs to split a separate test class for each endpoint. What matters is that scope, state, and identifiers are cleanly delineated.

## 14. Practice

Use an Orders API with GET, POST, and cancel operations:

1. Create a Jupiter test using `RestDocumentationExtension` and configure MockMvc in `@BeforeEach`.
2. Create separate fixtures for CONFIRMED and CANCELLED orders; confirm changes to a fixture in one test do not affect the other.
3. Create two GET success/not-found tests using distinct snippet identifiers and include both in Asciidoctor.
4. Intentionally reuse the same identifier for two tests, observe the output conflict, and rename them by operation/outcome.
5. Write a parameterized test for multiple order IDs; ensure invocations get unique identifiers or extract a representative documentation test.
6. Run two tests in reverse order to verify no state depends on execution order.
7. If using a database, create isolated keyed data and verify whether transaction rollback covers request execution.
8. Enable parallel execution for a test group; inspect mocks, database, and snippet output. Keep parallelism only when there are no resource collisions.
9. Try `ManualRestDocumentation` with TestNG/Spock and ensure teardown runs when tests fail.
10. Run snippet-generating tests before Asciidoctor and verify the documentation page uses the latest output.

**Completion criteria:** you distinguish the application context from the REST Docs documentation context; create operation-independent fixtures; manage mock/database/external state; use unique snippet identifiers; understand resource-sharing limits under parallel execution; and maintain a reproducible documentation build.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): configuring the documentation context and HTTP test integrations.
- [Spring REST Docs — API Documentation](https://docs.spring.io/spring-restdocs/reference/index.html): generating snippets from MockMvc, WebTestClient, and REST Assured.
- [JUnit 5 User Guide — Test Lifecycle](https://junit.org/junit5/docs/current/user-guide/#writing-tests-test-lifecycle): before/after test callback scope and test instance lifecycle.
- [JUnit 5 User Guide — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution): enabling and controlling parallel execution.
