# Tests as the Source of Evidence for Requests and Responses

Hand-written REST API documentation can describe an endpoint very clearly and still be wrong compared to the running application: the status code may have changed, a header may no longer appear, or the JSON may have an extra field missing from the documentation table. In **Spring REST Docs**, the solution is to use **executable HTTP tests** as the source for generating request/response examples and API description tables. When the implementation changes, both tests and documentation can be re-verified in the same build pipeline.

This lesson belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The scope of the module is to produce verifiable REST API documentation from HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; generate snippets for requests, responses, payloads, parameters, and headers; and compile Asciidoctor/Markdown documentation in build and CI. The focus here is understanding precisely **what evidence tests provide, how that evidence turns into documentation, and where its limits lie**.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between **HTTP observation**, **assertions**, and **contract descriptions** in a documentation test.
2. Write HTTP tests that both verify outcomes and generate Spring REST Docs snippets.
3. Explain why request/response snippets have stronger verifiable backing than hand-typed examples, while identifying what a test has **not** yet proven.
4. Write separate tests for success and failure scenarios, ensuring examples never mix up responses.
5. Organize fixtures, assertions, operation names, and CI so documentation is regenerated from the current source code.

## 2. What Does “Evidence” Mean in Spring REST Docs?

Consider hand-written documentation for creating a support ticket:

```http
POST /api/tickets HTTP/1.1
Content-Type: application/json

{"subject":"Cannot log in"}
```

An author might write by hand that the server returns `201 Created`, a `Location` header, and a JSON object containing `id`, `subject`, and `status`. Without running a test, that is merely **a claim in the documentation**.

With Spring REST Docs, a test actually sends a request to the system configured for testing, receives a response, and then:

- **Records** the HTTP facts of the exchange (method, URI, headers, payload, status).
- **Asserts** expected behavior using assertions (for example: status is `201`, `Location` has the right value, `status` field equals `OPEN`).
- **Describes** the structure and meaning of parameters/headers/fields via descriptors (for example: `subject` is the user-entered topic).
- **Generates snippets** from the tested operation for inclusion in the documentation.

Data flow:

```text
               HTTP test with deterministic input data
                                  │
                                  ▼
                  Send request to test application
                                  │
                                  ▼
                   Receive actual HTTP response
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
           Assertions                          Descriptors
    check status/headers/JSON           describe path, query, payload
                │                                   │
                └─────────────────┬─────────────────┘
                                  ▼
                 Spring REST Docs document(...)
                                  │
                                  ▼
                      generated-snippets/
                       ├─ http-request.adoc
                       ├─ http-response.adoc
                       ├─ request-fields.adoc
                       ├─ response-fields.adoc
                       └─ response-headers.adoc
                                  │
                                  ▼
                  Asciidoctor/Markdown + CI
```

Three kinds of information cannot replace one another:

| Component | Question it answers | If missing |
| --- | --- | --- |
| **Observed request/response** | What did the system under test actually receive and return? | HTTP examples may be guesses or stale copy-pastes |
| **Assertions** | What behavior must hold for the test to pass? | The test might record an incorrect response without catching a business bug |
| **Spring REST Docs descriptors** | What are the names, types, and meanings of fields/parameters/headers? | HTTP examples lack contract explanations, making them hard to use and hiding structural drift |

**A passing test does not mean the entire API has been proven correct.** It only confirms the behaviors checked under the conditions and scope established. For instance, a test using a fake controller or mocked service does not verify the database, network, authorization, or production configuration.

## 3. Choosing the Test Level: Evidence Depends on What Runs

Spring REST Docs supports several ways to produce requests and responses. Choose the tool and test scope based on what you want to prove.

| Testing approach | How the request runs | What it verifies well | Limits to keep in mind |
| --- | --- | --- | --- |
| **MockMvc standalone** | Instantiates the controller and partial MVC config right inside the test | Request mapping, request/response formatting, controller logic in that setup | Does not automatically cover filters, security, converters, or the rest of the app config |
| **MockMvc with WebApplicationContext** | Runs through the Spring MVC stack from the test context | HTTP behavior across a more realistic MVC setup, depending on context scope | Still does not open a real HTTP server; beans/mocks in the context affect results |
| **WebTestClient** | Bound to an in-memory app or connected to a running server | HTTP assertions on WebFlux/MVC according to the chosen binding | Evidence differs between in-memory and network modes |
| **REST Assured** | Typically makes HTTP calls to a test server; also has MVC test integration | Request/response over a real HTTP layer when calling a real server | Requires managing ports, data, environment, and server lifecycle |

Therefore, the phrase “documentation generated from integration tests” should only be used when tests actually exercise the integrated components that phrase implies. With MockMvc standalone, documentation reflects the contract returned by the tested controller in standalone configuration; that is very useful, yet narrower in scope than a call over a real server and real database.

Each tool also has its own Spring REST Docs integration. The detailed examples below use **MockMvc** because it makes the connection between assertions and `document(...)` easy to observe. The mindset of evidence sources, descriptors, and snippet generation applies equally to WebTestClient and REST Assured.

## 4. Practical Example: A Small, Testable API Contract

Design an API for creating support tickets:

- `POST /api/tickets` accepts JSON with a `subject` field.
- If `subject` is non-blank: returns `201 Created`, a `Location` header, and JSON of the created ticket.
- If `subject` is blank: returns `400 Bad Request` with an error JSON.
- To keep the example reproducible, the ID is fixed at `501`. This is illustrative data, not how IDs should be assigned in a production system.

### 4.1. Controller Used in the Test

```java
@RestController
@RequestMapping("/api/tickets")
class TicketController {

    record CreateTicketRequest(String subject) {}
    record TicketView(long id, String subject, String status) {}
    record ApiError(String code, String message) {}

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<?> create(@RequestBody CreateTicketRequest request) {
        if (request.subject() == null || request.subject().isBlank()) {
            return ResponseEntity.badRequest().body(
                new ApiError(
                    "INVALID_SUBJECT",
                    "subject must not be blank"
                )
            );
        }

        TicketView created =
            new TicketView(501L, request.subject(), "OPEN");

        return ResponseEntity
            .created(URI.create("/api/tickets/501"))
            .body(created);
    }
}
```

This is a minimal controller using Java `record` (Java 17+) and Spring Web classes. The project needs the corresponding imports such as `java.net.URI`, `RestController`, `RequestMapping`, `PostMapping`, `RequestBody`, `ResponseEntity`, and `MediaType`. The controller intentionally omits a database and authentication: the test below only proves the HTTP response from the controller with the configured MockMvc setup.

### 4.2. Setting Up the Documentation Test

```java
@ExtendWith(RestDocumentationExtension.class)
class TicketDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new TicketController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    // The @Test methods are shown in the next two sections.
}
```

`RestDocumentationExtension` hooks Spring REST Docs into the JUnit 5 lifecycle; `documentationConfiguration(provider)` attaches the operation-recording mechanism to MockMvc. When using Spring Boot test or a full context, how MockMvc is built may differ, but the test still needs configuration so Spring REST Docs records requests/responses and knows where to output snippets.

### 4.3. Success Test: Assertions Before Generating Snippets

Add the following method to the `TicketDocumentationTest` class:

```java
@Test
void createTicket_success() throws Exception {
    mockMvc.perform(
            post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"subject":"Cannot log in"}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(
            header().string("Location", "/api/tickets/501")
        )
        .andExpect(
            content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
        )
        .andExpect(jsonPath("$.id").value(501))
        .andExpect(
            jsonPath("$.subject").value("Cannot log in")
        )
        .andExpect(jsonPath("$.status").value("OPEN"))
        .andDo(document("tickets-create-success",
            requestHeaders(
                headerWithName("Content-Type")
                    .description("JSON media type of the request"),
                headerWithName("Accept")
                    .description("Expected response media type")
            ),
            requestFields(
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description("Support ticket subject")
            ),
            responseHeaders(
                headerWithName("Location")
                    .description("URI of the newly created ticket")
            ),
            responseFields(
                fieldWithPath("id")
                    .type(JsonFieldType.NUMBER)
                    .description("Ticket ID returned by the server"),
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description("Ticket subject"),
                fieldWithPath("status")
                    .type(JsonFieldType.STRING)
                    .description("Current status of the ticket")
            )
        ));
}
```

In this example, `post` is either Spring REST Docs' builder or Spring MVC Test's builder; because this endpoint has no path variables, either approach works for this request. Key static imports:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
```

Other types such as `MockMvc`, `MockMvcBuilders`, `RestDocumentationContextProvider`, `RestDocumentationExtension`, and `JsonFieldType` must be imported from their respective libraries. The example uses Spring REST Docs 3.x-style APIs, JUnit Jupiter, and a Spring/Jackson environment that supports records.

This exact test verifies that **for a request containing `subject="Cannot log in"`**, the controller returns `201`, `Location`, and specific JSON values. That claim is backed by executable assertions. At the same time, Spring REST Docs generates snippets containing the HTTP example and field description tables.

The identifier `tickets-create-success` names a **documentation operation**. Do not name it after random ID values or environment-dependent data, because the include address in the documentation page must remain stable.

### 4.4. Failure Test: Evidence for the 400 Case

An API can return multiple responses for the same method and path. To assert error behavior, you must test it:

```java
@Test
void createTicket_invalidSubject() throws Exception {
    mockMvc.perform(
            post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"subject":""}
                    """)
        )
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.code").value("INVALID_SUBJECT")
        )
        .andExpect(
            jsonPath("$.message")
                .value("subject must not be blank")
        )
        .andDo(document("tickets-create-invalid",
            requestFields(
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description(
                        "Subject; must not be empty or whitespace-only"
                    )
            ),
            responseFields(
                fieldWithPath("code")
                    .type(JsonFieldType.STRING)
                    .description("Business error code"),
                fieldWithPath("message")
                    .type(JsonFieldType.STRING)
                    .description("Message explaining the error")
            )
        ));
}
```

The two tests hit the same endpoint with different inputs and expectations. Consequently, they generate **two independent snippet groups**:

```text
generated-snippets/
├── tickets-create-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-fields.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── tickets-create-invalid/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

These are the representative files to inspect; Spring REST Docs can also generate default snippets such as `curl-request.adoc`, `httpie-request.adoc`, and body snippets depending on configuration. The `400` case is not documented with the success snippet because the body differs and `Location` is absent.

## 5. What Is Actually Verified?

Suppose the `createTicket_success` test passes. You should read the outcome in two layers: **concrete scope of proof** and **assumptions outside the test**.

| Statement | Does the sample test verify it? | Why? |
| --- | --- | --- |
| Sending JSON with a valid `subject` returns `201` | **Yes, within the test setup** | It has `status().isCreated()` |
| Response includes `Location: /api/tickets/501` | **Yes** | It has an exact header assertion |
| JSON has `id = 501` and `status = OPEN` | **Yes** | It has `jsonPath` assertions |
| Request/response in snippets come from an actual run | **Yes** | `document(...)` processes the executed operation |
| Every valid `subject` value always creates a ticket | **Not yet** | The test only uses one valid input |
| IDs are always unique when multiple clients create tickets | **Not yet** | The sample controller uses a hardcoded ID |
| The database persists data accurately | **Not yet** | The controller does not use a database |
| The endpoint is protected by authentication and authorization | **Not yet** | The test does not configure security or identities |
| Production returns the exact same output as the test environment | **Not guaranteed** | Configuration, data, and infrastructure may differ |

In other words, Spring REST Docs does not guarantee an endpoint's correctness by itself: it **binds documentation to behavior observed in a test suite**, while helping detect mismatches between descriptions and the payloads actually used. Confidence increases when the test suite covers sufficient scenarios, assertions are meaningful, and the test setup represents the system to be published.

### 5.1. Stronger Assertions Than Checking Status Alone

The following example can pass even if the server returns wrong data:

```java
.andExpect(status().isCreated())
.andDo(document("tickets-create-success"))
```

If the response body contains `"status":"CLOSED"` instead of `"OPEN"`, the status check still passes and the documentation could record that wrong JSON. Therefore, assert important business fields, not just the HTTP status. When the contract requires header values, media types, or error structures, add the corresponding assertions.

Do not turn tests into copies of a huge JSON snapshot devoid of business meaning. Prioritize the public rules and invariants that clients actually rely on, while using Spring REST Docs descriptors to document structure.

### 5.2. Descriptors Check Structure, Not Every Value

In strict field-documentation mode, `requestFields(...)` and `responseFields(...)` can fail a test when a payload contains an undocumented field or lacks a field required by a descriptor. For instance, if the controller adds a `priority` field while the response descriptors still list only `id`, `subject`, and `status`, the documentation test can fail and force the author to review the contract.

However, `fieldWithPath("status").type(JsonFieldType.STRING)` does not assert that status equals `OPEN`; you need an assertion such as `jsonPath("$.status").value("OPEN")`. Mark fields with `optional()` when they can genuinely be absent. Use `relaxedResponseFields(...)` for partial documentation only as a deliberate choice, because it does not require every field in the response to be documented.

Complex rules such as `email` formatting, `subject` length limits, `status` enums, or monetary amounts must be verified by dedicated assertions or tests if they are part of the contract.

## 6. Fixtures and Repeatability Determine Evidence Quality

An operation recorded from a test loses practical value if each run's result depends on leftover DB data, test execution order, or an unstable external service.

Key practices:

- **Arrange initial state:** create needed resources in fixtures, and clarify caller permissions and data relationships.
- **Use deterministic data:** IDs, timestamps, and display strings should be fixed or normalized before writing snippets when appropriate.
- **Keep tests independent:** clean up state at the right scope or use transactions/reproducible fixtures so one test never depends on another.
- **Never hide failures:** assertions must fail when behavior drifts from the contract; do not replace every field with overly broad matchers just to make documentation generation succeed.
- **Protect sensitive data:** do not let real tokens, session cookies, passwords, user emails, or personal data end up in published snippets.

For example, if the application generates random timestamps, you can validate ISO-8601 format in the test and normalize the timestamp in **the exported example** using a preprocessor when documentation stability is needed. Always distinguish **actual observed values** from **values substituted for presentation**.

### 6.1. Preprocessors Do Not Replace Assertions

Spring REST Docs supports `preprocessRequest(...)`, `preprocessResponse(...)`, and functions like `prettyPrint()` to make examples easier to read. For example, adding preprocessor arguments to `document(...)`:

```java
.andDo(document("tickets-create-success",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("subject")
            .description("Support ticket subject")
    ),
    responseFields(
        fieldWithPath("id").description("Ticket ID"),
        fieldWithPath("subject").description("Subject"),
        fieldWithPath("status").description("Status")
    )
));
```

This is **an illustrative variation of the `andDo(...)` block**, not an invitation to add a second `andDo` to the same test without considering the output. `preprocessRequest`, `preprocessResponse`, and `prettyPrint` are provided by `org.springframework.restdocs.operation.preprocess.Preprocessors`.

Even when prettifying JSON before writing snippets, keep assertions checking real behavior in the test body. If filtering or replacing sensitive headers/data for publication, ensure the presentation does not misrepresent what the client actually needs to send or expect.

## 7. From Test Evidence to Asciidoctor/Markdown Documentation

The snippet directory of the success operation can be included in an AsciiDoc documentation page:

```asciidoc
[[tickets-create]]
=== Create a support ticket

Send a subject to create a new support ticket.
subject must be a non-empty string.

==== Success: HTTP 201

.Request
include::{snippets}/tickets-create-success/http-request.adoc[]

.Request fields
include::{snippets}/tickets-create-success/request-fields.adoc[]

.Response
include::{snippets}/tickets-create-success/http-response.adoc[]

.Response headers
include::{snippets}/tickets-create-success/response-headers.adoc[]

.Response fields
include::{snippets}/tickets-create-success/response-fields.adoc[]

==== Invalid data: HTTP 400

.Request
include::{snippets}/tickets-create-invalid/http-request.adoc[]

.Response
include::{snippets}/tickets-create-invalid/http-response.adoc[]

.Error fields
include::{snippets}/tickets-create-invalid/response-fields.adoc[]
```

The `{snippets}` attribute must be configured in the Asciidoctor compilation step to point to the test output, typically `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven). These paths signify: **a prose documentation section pointing to a group of snippets generated from a specific test**.

If outputting Markdown, do not assume the `include::{snippets}/...[]` syntax is understood by a Markdown compiler; you need a snippet conversion tool, a supported include step, or an appropriate Markdown generation pipeline.

Complete documentation still needs author-written explanations, such as who is allowed to create tickets, `subject` limits, status meanings, and how to handle `400`. A test can prove the response for one scenario; it cannot know the full business policy that has not yet been described.

## 8. Build and CI: How to Keep Evidence from Going Stale

A proper pipeline must regenerate documentation from current tests in sequence:

```text
Clean source checkout
       │
       ▼
Compile + run HTTP documentation tests
       │
       ├── Assertion fail? → pipeline fails
       ├── Descriptor fail? → pipeline fails
       └── PASS → generated-snippets/
                       │
                       ▼
             Compile documentation
                       │
                       ├── Missing include? → report error
                       └── PASS → output HTML/PDF/Markdown
```

With Gradle, the documentation task should depend on the test task that generates snippets and declare the `generated-snippets` directory as an input. With Maven, bind test execution and the documentation plugin to the appropriate lifecycle phases. If tests are skipped while the page pulls snippets from a previous build, the result is no longer evidence of the current code; therefore CI should run from a clean output directory and verify that the expected documentation tests actually ran.

**A useful CI criterion:** when a change causes a response status or field to no longer match the tested contract, the build must fail during tests or snippet generation; when the author updates the contract and tests, the documentation must regenerate cleanly from the new code.

Note that **publishing** documentation should happen only after both tests and compilation succeed. An HTML file that builds on its own is not enough to prove the documentation reflects the code version about to be released.

## 9. Anti-Patterns: Weak Evidence That Easily Misleads

| Symptom | Why it is weak | Better practice |
| --- | --- | --- |
| Test calls `document(...)` with no assertions | Can capture a wrong response | Assert status, headers, and key business values |
| Checking only `status().isOk()` for GET | Body could contain incorrect data | Add `jsonPath`/assertions matching the contract |
| Mock service returns hardcoded expected JSON | Proves controller routing, not the real backend | State the scope clearly and add integration tests when needed |
| Success test used for error docs | Scenario and response do not match | Create separate operations for meaningful `4xx`/`5xx` cases |
| Test uses random data and varies with run order | Snippets fluctuate unpredictably | Fix fixtures, control time/IDs, or normalize examples |
| Response field table uses `optional()` everywhere | Fails to catch missing contract fields | Mark optional only for fields that can genuinely be absent |
| Using `relaxedResponseFields` API-wide without reason | Newly added fields may go undocumented | Prefer strict checks for public schemas |
| Docs pull stale snippets when tests fail or are skipped | No evidence from the current commit | CI regenerates snippets and requires passing tests before rendering |
| Snippets leak tokens, internal hosts, or real data | Docs may expose sensitive information | Use safe fixtures and appropriate preprocessors |

### When Should You Add More Tests?

Coverage cannot be decided solely from a list of HTTP status codes. Choose **behaviors that API callers need to rely on**. For example, with `POST /api/tickets`, if the API requires authentication, add a `401` test; if a user lacks permission to create a ticket in a workspace, add a `403` test; if the `subject` field has a length limit, test valid and invalid boundaries. Those tests are only valuable when the application actually enforces the corresponding rules.

Adding too many tests that merely repeat the same response without increasing contract coverage creates maintenance overhead. Prioritize representativeness, clarity, and the significance of each operation.

## 10. Hands-On Exercise: Testing “Claims” with Tests

Suppose a team announces:

> `POST /api/tickets` with a valid `subject` returns `201`, a `Location` header, and a body containing status `OPEN`. If `subject` is empty, the API returns `400` with error code `INVALID_SUBJECT`.

Turn that description into reproducible evidence:

1. Write two clearly named HTTP tests: `createTicket_success` and `createTicket_invalidSubject`.
2. For each test, prepare fixed input, send the request with MockMvc, and assert the status along with key response values.
3. Attach `document(...)` with two distinct identifiers and their corresponding descriptors.
4. Run the tests, open `http-request.adoc` and `http-response.adoc`, and cross-check them against the assertions.
5. Include the snippets in an AsciiDoc page; ensure both `201` and `400` scenarios have prose explanations.
6. Temporarily change the controller to return `"status":"CLOSED"` on creation success. Confirm that `createTicket_success` **fails**. Then revert the experiment and rerun.
7. Try adding a public JSON field to the response without documenting it. Confirm that strict field documentation detects the mismatch; update tests and docs when that is an intentional contract change.

**Completion criteria:** tests protect important public claims, every published example traces back to an identified operation, and the pipeline can regenerate the documentation page from a clean output directory.

## 11. Takeaways

- Tests are **the source of evidence for executed HTTP interactions**, not a blanket certificate for every API behavior.
- Recorded requests/responses supply observed facts; **assertions** confirm expected outcomes; **descriptors** explain and check structure used to generate snippets.
- A success scenario and an error scenario are distinct **documentation operations**, even when sharing the same HTTP method and route.
- Evidence strength depends on **test scope**, fixtures, assertion quality, and coverage of API rules.
- Wiring **tests → snippets → Asciidoctor/Markdown → build/CI** helps detect documentation that no longer matches current code and ensures examples trace back to a concrete test.
