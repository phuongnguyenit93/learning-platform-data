# Switching Between MockMvc, WebTestClient, and REST Assured

## Lesson Objectives

Spring REST Docs can generate documentation from multiple HTTP test harnesses. A project may start with **MockMvc**, then switch to **WebTestClient** when the application uses WebFlux or needs reactive stack testing; or adopt **REST Assured** when testing APIs over HTTP with a fluent syntax. Switching is not merely changing imports or dependencies: building requests, awaiting responses, configuring documentation, and representing operations all differ.

This lesson belongs to the **Upgrade** chapter of the **SPRING_REST_DOCS** module: generating verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; producing snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation; and integrating it into the build and CI.

After this lesson, you will be able to:

- Understand the roles and limitations of the three test harnesses.
- Choose the right integration for your application architecture and testing goals.
- Identify which dependencies, setups, and documentation configurers need to change.
- Migrate requests, assertions, and REST Docs descriptors for each API.
- Preserve document identifiers, contracts, and the published snippet structure.
- Compare outputs between the old and new harnesses to catch discrepancies.
- Upgrade incrementally and keep the documentation pipeline stable in CI.

## 1. Understanding the Three Test Harnesses

All three options can execute HTTP operations and integrate with Spring REST Docs, but they test at different layers.

| Criterion | MockMvc | WebTestClient | REST Assured |
| --- | --- | --- | --- |
| Typical foundation | Spring MVC | Spring WebFlux; can also bind to a mock server | Fluent HTTP test client, used with a running server or suitable setup |
| Execution mode | Calls the Spring MVC request pipeline in tests without starting a real HTTP server | Can bind to an application context/controller or call a server over HTTP | Sends requests over HTTP to a base URI/server |
| API style | Fluent request builder and result matchers | Fluent reactive client, exchange() | Given/When/Then |
| Response | MvcResult and MockMvc matchers | EntityExchangeResult/exchange result and expectations | Response and response assertions |
| REST Docs integration | spring-restdocs-mockmvc | spring-restdocs-webtestclient | spring-restdocs-restassured |
| Best suited for | In-process controller/API tests in Spring MVC | Reactive endpoints or testing via WebTestClient | Integration/API tests over HTTP with fluent assertion syntax |

There is no single best harness for every project. Choose based on your goals:

- Spring MVC application wanting fast in-process controller tests: MockMvc is usually suitable.
- WebFlux/reactive application needing to test reactive flows or already using WebTestClient: WebTestClient fits well.
- Need to call APIs over HTTP, test against a booted server, or prefer Given/When/Then: REST Assured is suitable.

If the goal is to verify real behavior of a reverse proxy, TLS, browser cookies, or a network gateway, you need tests against a real server/infrastructure. MockMvc does not simulate all those layers; binding WebTestClient directly to an application context is likewise not equivalent to calling over the network.

## 2. Scoping the Migration Before Editing Tests

Before switching harnesses, record a baseline for a representative operation:

| Component | What to Record |
| --- | --- |
| HTTP operation | Method, URI, query/path parameters |
| Request | Headers, cookies, content type, body |
| Response | Status, headers, body |
| Assertions | Status, JSON fields, headers, cookies, and errors |
| REST Docs | Document identifier, descriptors, preprocessors |
| Snippet output | File names, template format, output directory |
| Build | Test tasks, Asciidoctor/Markdown assembly tasks |

Pick at least one GET with path/query parameters and one POST with a request body if the project has both. Representative operations help uncover differences in encoding, bodies, headers, and descriptors.

Keep the contract and document identifier unchanged during the initial migration. If you change identifiers, templates, and API content at the same time, comparing snippets makes it hard to identify root causes.

## 3. Dependencies and REST Docs Configuration

Each harness has a corresponding integration artifact. Gradle example:

~~~groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:<version>'
    // Or:
    // testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient:<version>'
    // testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:<version>'
}
~~~

Only add the integration actually in use. Keep Spring REST Docs artifacts at the same version according to the release guide and project dependency management. Do not copy all three dependencies just to experiment with switching if the test suite does not need them.

With Maven, replace the artifact in the relevant dependency and keep scope test. After making changes, inspect the dependency tree to catch mismatched core/integration module versions.

Shared components that usually stay intact:

- spring-restdocs-core brought in transitively via the integration dependency.
- Document identifiers inside document(...).
- Payload descriptors such as requestFields(...), responseFields(...).
- Custom snippets, attributes, and template formats if compatible.
- AsciiDoc/Markdown documentation and the publishing workflow.

What typically changes is the test harness, how the documentation filter/configurer is attached, and how responses are retrieved/asserted.

## 4. From MockMvc to WebTestClient

### 4.1. Configuring WebTestClient

REST Docs provides WebTestClientRestDocumentation.documentationConfiguration(...) to attach documentation to WebTestClient. Conceptual configuration example:

~~~java
import org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(applicationContext)
    .configureClient()
    .filter(
        WebTestClientRestDocumentation.documentationConfiguration(
            restDocumentation
        )
    )
    .build();
~~~

This snippet illustrates binding to an application context and attaching the documentation filter. If tests use a WebFlux controller slice, router function, or running server, pick the bind mode matching that fixture. Do not change the bind mode mechanically when existing tests are verifying network behavior.

### 4.2. Migrating Requests and Assertions

MockMvc:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get"));
~~~

WebTestClient:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(
        WebTestClientRestDocumentation.document("orders-get")
    );
~~~

The document identifier remains orders-get, preserving links to existing documentation pages. Assertions must be migrated completely; do not keep only the status check and drop JSON path, header, or cookie checks from the old MockMvc test.

### 4.3. Migrating Descriptors

REST Docs descriptors can usually be reused:

~~~java
.consumeWith(
    WebTestClientRestDocumentation.document(
        "orders-get",
        pathParameters(
            parameterWithName("id")
                .description("Order ID")
        ),
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Order status")
        )
    )
)
~~~

Descriptors describe operation data; they do not depend on whether requests are built with MockMvc or WebTestClient. However, how snippets/documentation are hooked into the chain depends on the integration and where the result is consumed.

## 5. From MockMvc to REST Assured

### 5.1. Configuring the Documentation Filter

REST Assured integrates with Spring REST Docs via RestAssuredRestDocumentation. Tests commonly use a shared RequestSpecification to attach the filter:

~~~java
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

RequestSpecification documentationSpec =
    new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation))
        .build();
~~~

In practice, include the corresponding REST Assured and RestDocumentationContextProvider imports. Configure the output directory and snippet defaults in the documentation configuration or build setup according to the version in use.

### 5.2. Migrating Requests and Assertions

MockMvc:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

REST Assured:

~~~java
given(documentationSpec)
    .accept(ContentType.JSON)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}", 42)
    .then()
    .statusCode(200)
    .body("id", equalTo(42));
~~~

REST Assured typically uses the document(...) filter to record the operation. Ensure the filter is attached to the right request and executed in the chain. If an assertion fails, the test must fail as before; do not let snippet generation mask API failures.

### 5.3. Using Descriptors

Descriptors can be passed into the REST Assured documentation filter:

~~~java
.filter(document("orders-get",
    pathParameters(
        parameterWithName("id")
            .description("Order ID")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Order status")
    )
))
~~~

Payload, header, parameter, and link descriptors follow the corresponding REST Docs API. Verify static imports and overloads in the current version; do not assume every helper or preprocessing method has the exact same signature across integrations.

## 6. Migrating Request Bodies

Request bodies are where differences frequently arise due to differing request-building APIs.

MockMvc:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42,"description":"Keyboard"}
            """))
    .andExpect(status().isCreated());
~~~

WebTestClient:

~~~java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "customerId", 42,
        "description", "Keyboard"
    ))
    .exchange()
    .expectStatus().isCreated();
~~~

REST Assured:

~~~java
given(documentationSpec)
    .contentType(ContentType.JSON)
    .body(Map.of(
        "customerId", 42,
        "description", "Keyboard"
    ))
    .filter(document("orders-create",
        requestFields(
            fieldWithPath("customerId").description("Customer ID"),
            fieldWithPath("description").description("Order description")
        )
    ))
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
~~~

When switching from a JSON string to an object/Map, serialization may produce different field ordering, number representation, or escaping. JSON objects generally do not enforce field order, though snippet diffs may change. If documentation requires stable payloads, use explicit fixtures and compare JSON structurally rather than relying on key order.

## 7. Migrating Preprocessors and Sensitive Data

REST Docs preprocessors normalize the request/response captured in snippets. When changing integrations, keep the same policies:

- Pretty-print JSON if needed.
- Remove or replace Authorization values.
- Mask cookies/sessions/tokens.
- Normalize dynamic timestamps or UUIDs if they are not part of the contract.
- Keep Content-Type, Location, and meaningful headers.

MockMvc can configure default preprocessors on MockMvcRestDocumentationConfigurer. WebTestClient and REST Assured have their own documentation configurations; port equivalent policies to the corresponding configurer/filter using the API of the version in use.

Do not assume a MockMvc configuration can be passed verbatim to WebTestClient or REST Assured. If an API expects a different request/response preprocessor type, write an adapter/helper returning the exact type required by that integration.

After migrating, verify both of the following:

1. The application still receives real requests with required headers/cookies and test behavior remains accurate.
2. Snippets do not contain sensitive values.

Preprocessors only modify what REST Docs records; they are not an endpoint protection mechanism or a replacement for security filters.

## 8. Keeping Document Identifiers and Snippet Contracts Stable

If the documentation currently includes:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
~~~

preserve the orders-get identifier when switching harnesses if the operation represents the same API. This reduces churn across documentation files.

However, do not assume every snippet will be byte-for-byte identical. Factors that can alter output include:

- URI encoding or query parameter serialization.
- Default headers added by the client.
- Header ordering.
- Pretty-printing or the JSON serializer.
- Representation of multipart, form data, or cookies.
- Template format and REST Docs version.

Compare snippets by HTTP/contract semantics first, then decide whether exact formatting needs to be preserved. Only update documentation when differences are intentional.

## 9. Quick Migration Reference Table

| Task | MockMvc | WebTestClient | REST Assured |
| --- | --- | --- | --- |
| GET request | mockMvc.perform(get(...)) | webTestClient.get().uri(...) | given().when().get(...) |
| POST body | .content(...) | .bodyValue(...) or body publisher | .body(...) |
| Execution | perform(...) | .exchange() | .when() |
| Status assertion | .andExpect(status().isOk()) | .expectStatus().isOk() | .statusCode(200) |
| JSON assertion | jsonPath(...) matcher | .expectBody().jsonPath(...) | .body(path, matcher) |
| Record REST Docs | .andDo(document(...)) | .consumeWith(documentation(...)) | .filter(document(...)) |
| Documentation setup | documentationConfiguration(...) | WebTestClientRestDocumentation.documentationConfiguration(...) | documentationConfiguration(...) filter |

This table is a conceptual map, not an automatic line-by-line replacement. Exact signatures and setup depend on the versions of Spring REST Docs, Spring Framework, and REST Assured.

## 10. Parity Testing After Migration

To confirm the new harness generates equivalent documentation, select an operation and run both the old and new tests during the transition period.

Check:

| Group | Comparison |
| --- | --- |
| Request line | Method, path, query string |
| Request headers | Content-Type, Accept, custom headers |
| Request body | JSON structure, encoding, null/optional fields |
| Response | Status and body structure |
| Headers | Location, Content-Type, cache/security headers |
| Parameters | Names, values, and encoding |
| Descriptors | Field paths, descriptions, optional/subsection |
| Preprocessors | Masking, pretty-print, normalization |
| Snippet output | Identifier, file names, template format |

For JSON, compare structurally instead of as plain text if property order is not part of the contract. For headers, consider which headers are order-independent. For query strings and cookies, verify encoding since differences here can affect clients.

Only remove the old test harness once parity is achieved and it is no longer used elsewhere. Do not delete old tests simply because a new test compiles.

## 11. Organizing a Phased Migration

A risk-reducing plan:

1. Pick a simple operation and save baseline snippets.
2. Add the required integration dependency while keeping versions synchronized.
3. Create new tests with the target harness and preserve document identifiers.
4. Migrate requests, assertions, and REST Docs descriptors.
5. Migrate preprocessors, custom snippets, and output configuration.
6. Generate snippets into a clean directory and compare against the baseline.
7. Render documentation and check includes and links.
8. Expand to operations with bodies, multipart, cookies, and error responses.
9. Run the full test suite and CI.
10. Remove the old integration once no tests depend on it.

If migrating from Spring MVC to WebFlux at the same time, that is an application architecture change rather than just a test harness swap. Controllers/routers, serialization, exception handling, and reactive behavior must be tested separately.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| WebTestClient tests generate no snippets | Documentation filter not attached or consumeWith not called | Check configurer and where the result is consumed |
| REST Assured calls API but produces no snippets | Document filter not attached to the request specification | Attach filter to the executed request |
| Body snippet differs after migration | Different serializer or body construction | Use consistent fixtures and compare JSON structurally |
| Query parameters encoded differently | Clients handle URI templates/parameters differently | Assert final URI and inspect wire representation |
| Extra headers appear | Client adds default headers automatically | Separate contract headers from harness-added headers |
| Old assertions lost | Only migrated the document call | List all assertions and migrate every one |
| Preprocessors not working | Old harness configuration was not migrated | Create equivalent configuration for the new integration |
| Snippet include fails | Document identifier or file name changed | Keep the ID and verify actual output |
| WebTestClient test hangs/behaves differently | Wrong bind mode or reactive chain handling | Choose the proper bind mode and complete exchange/assertions |
| REST Assured cannot use mock application context | REST Assured sends HTTP calls via client | Boot server/test environment or choose an appropriate bind harness |
| CI does not generate documentation | Task only runs old tests or dependency is missing | Update task/test filters and check dependency graph |

## 13. Hands-On Exercise

Select endpoints:

~~~text
POST /api/orders
GET /api/orders/{id}
~~~

Requirements:

1. Take an existing MockMvc test suite and record document identifiers, assertions, descriptors, and preprocessors.
2. Migrate both operations to WebTestClient or REST Assured.
3. Preserve status, body, header, parameter, and cookie assertions.
4. Preserve document identifiers so existing documentation pages continue working.
5. Generate snippets from both old and new harnesses into two separate directories.
6. Compare HTTP exchanges, field tables, and post-preprocessing output.
7. Render Asciidoctor/Markdown using the current pipeline.
8. Run the full CI; only remove the old integration after confirming no tests depend on it.

**Completion criteria:** the new test harness verifies the same contract; REST Docs generates all snippets; output differences are explained; documentation renders cleanly; CI runs stably without losing old assertions.

## Key Takeaways

Switching between MockMvc, WebTestClient, and REST Assured changes the test harness, how requests/responses are constructed, and where the documentation filter/configurer attaches. REST Docs descriptors and document identifiers can generally be preserved, while request serialization, headers, URI encoding, and snippet formatting must be re-verified. Migrate operation by operation, preserve assertions and preprocessing, generate snippets into a separate directory, and verify parity before retiring the old harness. If switching from MVC to a reactive stack simultaneously, treat it as a broader architectural change and test application behavior separately.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring WebTestClient Reference](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html), [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage), and [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases).
