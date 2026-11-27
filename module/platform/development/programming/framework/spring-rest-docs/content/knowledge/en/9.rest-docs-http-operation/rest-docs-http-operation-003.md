# The `curl-request` Snippet for Reproducing Requests

## 1. Purpose and Position in HTTP Operations

Once a REST API has HTTP tests, readers of the documentation often want to **retry the exact request tested** using a command-line tool. In Spring REST Docs, the `curl-request.adoc` snippet serves that need: it presents a `curl` command generated from the request information actually executed by the test.

This belongs to the **HTTP operation** chapter of `SPRING_REST_DOCS`. The module's goal is to generate verifiable REST API documentation from HTTP tests via **MockMvc, WebTestClient, or REST Assured**; generate snippets for requests, responses, payloads, parameters, and headers; and then author Asciidoctor/Markdown documentation and integrate it into build and CI pipelines.

After this lesson, you will be able to:

- Explain the components of a `curl-request` snippet and how it relates to an HTTP operation.
- Generate `curl-request.adoc` from a MockMvc test with clear assertions.
- Read and adjust the URL, method, headers, query string, and body in a `curl` command.
- Distinguish **reproducing request syntax** from **reproducing the exact result** in another environment.
- Use snippets in Asciidoctor documentation, handle sensitive data, and configure an automated update pipeline.

> **Scope:** `curl-request` is a sample command for documentation and manual invocation. It is not a byte-for-byte wire capture, does not supply environment data on its own, and does not replace automated tests that verify responses.

## 2. Where Does `curl-request` Come From?

An **HTTP operation** in Spring REST Docs contains request and response information captured from a test. From that, REST Docs can generate several default snippets, typically including:

| Snippet | Purpose |
| --- | --- |
| `curl-request.adoc` | A `curl` command representing the request so readers can easily replay it. |
| `httpie-request.adoc` | An equivalent command in HTTPie syntax. |
| `http-request.adoc` | Representation of the HTTP request with method, URI, headers, and body. |
| `http-response.adoc` | Representation of the status line, response headers, and body. |
| `request-body.adoc` | Only the request body content. |
| `response-body.adoc` | Only the response body content. |

The list above applies to the standard default snippet configuration; it can change if a project customizes generated snippets, templates, or output paths. Tabular descriptive snippets such as `request-fields.adoc`, `request-headers.adoc`, and `query-parameters.adoc` only appear when the corresponding descriptors are declared.

Flow for producing a `curl-request` snippet:

~~~mermaid
flowchart LR
    A["HTTP test sends request"] --> B["Endpoint returns response"]
    B --> C["Test verifies result"]
    C --> D["REST Docs records HTTP operation"]
    D --> E["curl-request.adoc"]
    E --> F["API documentation page"]
    F --> G["Reader replays using curl"]
~~~

In MockMvc test examples, the `document(...)` step should be placed after key assertions. That way, if an assertion fails, snippet generation at the end of the chain does not execute. With other test clients, when the operation is recorded and when assertions run may differ; the pipeline must still require **all tests to pass**.

## 3. Reading a `curl` Command

Suppose the API has a book creation endpoint:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: docs-001

{"title":"Spring in Action","price":199000}
~~~

An **illustrative** `curl-request.adoc` snippet might look like this:

~~~bash
curl 'https://api.example.com/api/books' -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Request-Id: docs-001' \
  -d '{"title":"Spring in Action","price":199000}'
~~~

The syntax, option order, quotes, line breaks, and choice of `-d`/`--data` are **illustrative**. The actual file depends on the version, `curl-request` template, test client, and preprocessors in use. Open the generated snippet after running your test to inspect the exact output.

| Component | Example | Meaning |
| --- | --- | --- |
| `curl` | `curl 'https://...'` | Sends an HTTP request to the specified URL. |
| URL | `https://api.example.com/api/books` | Scheme, host, port if any, and request target. |
| `-i` | `-i` | Prints response headers in output, helpful for inspecting status and headers. |
| `-X POST` | `-X POST` | Specifies the HTTP method. |
| `-H` | `-H 'Accept: application/json'` | Adds a request header; can appear multiple times. |
| `-d` | `-d '{"title":...}'` | Sends request body data, suitable for small JSON like in this example. |
| Trailing `\` | Backslash | Line-continuation character in POSIX-style shells; not part of the HTTP request. |

**Distinguishing `-i` and `-I`:** `-i` prints response headers along with the response body; `-I` (uppercase I) requests **headers only**, typically sending a `HEAD` request. Do not mechanically replace `-i` with `-I`, as doing so changes the operation being tested.

### Body Data and HTTP Method

Key points when reading or editing the command:

- `-X POST` explicitly sets the method; `-d` also causes `curl` to default to `POST` if no method is specified, though keeping the method explicit is good practice in API documentation.
- `-d` sends request data, but handles bytes and files differently from `--data-binary`. When a payload needs exact preservation of newlines or file contents, choose the appropriate option.
- `Content-Type: application/json` tells the server how to interpret the body. Using `-d` alone does not automatically guarantee the JSON media type required by the API contract.
- `Accept: application/json` specifies the response format desired by the client; it serves a different role from `Content-Type`.
- The body can be empty for `GET`/`DELETE`, though the HTTP method alone does not dictate every body rule of a specific API.

### Query Strings Must Be in the URL

For a listing endpoint, an illustrative command is:

~~~bash
curl 'https://api.example.com/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

Both query parameters `page` and `size` appear on the URL. The `&` character must be protected by quotes in many shells, because leaving it unquoted can be interpreted as a shell operator. For values containing spaces, `&`, or special characters, apply proper URL encoding rather than concatenating strings arbitrarily. When entering parameters manually, `curl --get --data-urlencode 'search=Spring REST Docs'` can help safely encode query strings.

## 4. Generating `curl-request.adoc` with MockMvc

### 4.1. Dependencies and Assumptions

The example below uses Spring Boot 3.x, Spring MVC, JUnit 5, and Java 17+. The project requires Spring Boot's test dependency and the MockMvc REST Docs integration module:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Assume the application already has a `POST /api/books` endpoint accepting JSON:

~~~json
{
  "title": "Spring in Action",
  "price": 199000
}
~~~

and, upon successful creation, returns `201 Created`. This is an **assumed contract for illustration**, not an endpoint automatically created by Spring REST Docs. Test fixtures must prepare the appropriate data and state.

### 4.2. Complete Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class BookApiDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "docs-001")
                .content("""
                    {"title":"Spring in Action","price":199000}
                    """))
            .andExpect(status().isCreated())
            .andDo(document("books-create"));
    }
}
~~~

Points to observe:

1. `post("/api/books")` determines the request method and request target.
2. `contentType(...)`, `accept(...)`, and `header(...)` represent the request headers used.
3. `content(...)` defines the JSON body of the operation; REST Docs records this body to build the `curl` command.
4. `andExpect(status().isCreated())` forces the HTTP test to confirm `201` before running `document(...)`.
5. `document("books-create")` is the identifier used as the folder name containing the operation's snippets.
6. `@AutoConfigureRestDocs(...)` specifies the output directory and the scheme, host, and port values used when **rendering URIs in documentation**. The value `api.example.com` is an illustrative host; it is not deployed as a live server by this test.

The configuration above uses Spring Boot's compatible MockMvc auto-configuration. For projects configuring REST Docs manually, provide the corresponding extension/configurer instead of this annotation.

### 4.3. Inspecting Output Files

After the test passes, a typical structure is:

~~~text
build/generated-snippets/
└── books-create/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
~~~

Open the file directly:

~~~text
build/generated-snippets/books-create/curl-request.adoc
~~~

Inside will be the `curl` command corresponding to the request MockMvc sent, formatted by the active template. Do not treat the exact text in the earlier illustrative example as a guaranteed byte-for-byte result.

**Warning on replayability:** `MockMvc` tests send requests within the Spring test environment and do not necessarily start a real HTTP server on `api.example.com` or port `443`. Therefore, even though the `curl` command is syntactically valid, you can only actually replay it when replacing the URL with an **accessible endpoint** that has matching data and permissions.

## 5. Generating Snippets for `GET` with Query Parameters

Suppose the API has a `GET /api/books?page=0&size=10` operation returning `200 OK`. Inside the test class above, you can add:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// Method placed in BookApiDocumentationTest class
@Test
void documentListBooks() throws Exception {
    mockMvc.perform(get("/api/books")
            .queryParam("page", "0")
            .queryParam("size", "10")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("books-list",
            queryParameters(
                parameterWithName("page")
                    .description("Page index, starting from 0"),
                parameterWithName("size")
                    .description("Maximum number of books per page")
            )
        ));
}
~~~

The command in `books-list/curl-request.adoc` may take the form:

~~~bash
curl 'https://api.example.com/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

The `query-parameters.adoc` snippet adds a table explaining the meaning of the parameters. The two snippets serve different purposes: `curl-request` shows readers how to send the request; `query-parameters` helps them understand why and which values are accepted.

In MockMvc, use `queryParam(...)` or a URI with an explicit query string when you want query parameters to appear on the URL. Do not assume all `param(...)` calls are represented identically as query strings in snippets.

### Path Variables in URLs

A concrete request to book `42` may display:

~~~bash
curl 'https://api.example.com/api/books/42' -i -X GET
~~~

The notation `/api/books/{id}` is normally a **URI template**, while `/api/books/42` is the **actual URI called by the test**. If you want to generate a `path-parameters` table, use a request builder that retains URI template information along with the `pathParameters(...)` descriptor. `curl-request` must still render a concrete URL so readers can replay it.

## 6. Distinguishing Request Reproducibility from Response Results

Understand "reproducing" accurately in this lesson's title: `curl-request` aims to express **how to send an equivalent request**. It cannot guarantee receiving the same status, headers, or body when run in a different environment.

| Factor | What the test has | What must be prepared when running `curl` |
| --- | --- | --- |
| HTTP server | MockMvc may run inside the test application without opening a port | A real server or accessible service address |
| URL | Host/scheme/port set per documentation config | Valid URL for local, staging, or target test environment |
| Data | Test fixtures may have preloaded books/users | Corresponding data exists or a creation step runs first |
| Authentication | Test may mock users or security context | Valid cookies, tokens, or credentials for the environment |
| State | Test may roll back or reset the database | The live environment may have been modified by prior requests |
| Time | Test may use a fixed clock or ID | Timestamps, IDs, and data ordering may vary |
| Response | Test assertions verify specific conditions | Inspect status, headers, and body of the actual call |

For example, a `POST` command to create a book might return `201` on the first call and `409 Conflict` on the next if the system forbids duplicate book codes/titles. The replay command is still correct in how the request is sent; **the outcome differs** because system state changed.

Documentation should have two layers:

- **Action:** `curl-request` displays the tested method, URI, headers, and body.
- **Contract:** `http-response`, response fields tables, status descriptions, and test assertions explain expected outcomes.

To check results from the command line, `-i` helps observe response headers and body; `-v` is useful for debugging connections/TLS, though it can print sensitive information and should be used cautiously.

## 7. Running Snippets in a Real Environment

### 7.1. Checking Parameters Before Running

Suppose the generated file contains `https://api.example.com` as an illustrative host. To test locally, you can change it to:

~~~bash
curl 'http://localhost:8080/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

This is **editing the command when reading documentation**, not altering generated snippets to pretend the test called localhost. If you want snippets across the entire documentation to display a public host, configure REST Docs accordingly at the documentation generation source.

Before running a `POST` command, verify:

1. The URL points to the intended environment and endpoint.
2. The method matches the documented operation.
3. The query string, request headers, and JSON body are appropriate.
4. Any placeholders such as `{token}` or `{id}` have been replaced with valid values.
5. Whether the request creates, updates, or deletes data; use test data when needed.
6. The account or token has the required permissions.

### 7.2. Inspecting Status and Response

Example in a local environment:

~~~bash
curl 'http://localhost:8080/api/books/42' -i -X GET \
  -H 'Accept: application/json'
~~~

Output might include:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":42,"title":"Spring in Action","price":199000}
~~~

This output is illustrative only. To determine whether the command succeeded functionally, you cannot rely solely on `curl`'s process exit code: by default, `curl` can return a zero exit code even when the server responds with HTTP `404` or `500`. Always **check the HTTP status**, headers, and body; for automation, consider `--fail-with-body` on `curl` versions that support it (this flag maps many HTTP errors to non-zero exit codes, though business rules must still be verified).

### 7.3. Using a File for Long JSON Payloads

For multi-line JSON bodies, sending from a file improves readability and avoids shell escaping errors:

~~~json
{
  "title": "Spring in Action",
  "price": 199000
}
~~~

Assuming the content above is saved as `book.json`, the command is:

~~~bash
curl 'http://localhost:8080/api/books' -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '@book.json'
~~~

`--data-binary '@book.json'` reads the body from the file and preserves bytes exactly as in the file. The file `book.json` is a hands-on file prepared by the user; Spring REST Docs does not generate this body file automatically in the example.

### 7.4. Shell Differences

`curl` snippets usually use syntax suited to POSIX-style shells such as Bash or zsh. A trailing `\` continues a command in those shells; it cannot be pasted verbatim into every environment.

On Windows PowerShell, explicitly invoke `curl.exe` to avoid hitting the `curl` alias pointing to `Invoke-WebRequest` in Windows PowerShell 5.1. Example one-line command:

~~~powershell
curl.exe -i -X GET "http://localhost:8080/api/books?page=0&size=10" -H "Accept: application/json"
~~~

For a `POST` containing JSON with many double quotes, using a `book.json` file with `--data-binary "@book.json"` is easier to control than copying Unix shell syntax into PowerShell:

~~~powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@book.json"
~~~

Do not confuse quoting/escaping differences between terminals with a change in the HTTP method or endpoint contract.

## 8. Displayed URI in Documentation vs. Actual Test URL

In MockMvc, a `post("/api/books")` request can run entirely within the test process. Without further configuration, REST Docs typically uses a test-environment base URI when generating request snippets. For public-facing examples, stabilize the **displayed** URI, for instance:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

These attributes make documentation examples easier to understand, but do not prove that the endpoint at `https://api.example.com` is deployed and reachable.

If using a client running against a real HTTP server, REST Docs can record the specific host/port of the test environment. Preprocessors can normalize the URI displayed in request snippets. For example:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Inside the MockMvc chain, replace the existing document(...) call:
.andDo(document("books-list",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
));
~~~

This is a **replacement example** for the previous `document(...)` call. If the test also generates `query-parameters.adoc` or other descriptive snippets, keep the required descriptors in the same `document(...)` call.

A helpful rule: the URL in a snippet should fit the **target environment the documentation aims to guide**, while clearly noting sample hosts or instructing readers to substitute an accessible environment. Never configure a hostname/port just to make a command look "pretty" without explaining how to run it.

## 9. Authentication and Sensitive Data

The `curl-request` snippet can include all request headers and the body sent by the test. If a test uses real data, generated documentation risks leaking tokens, API keys, cookies, user information, or private fields.

**First principle:** use only dummy fixtures and placeholder secrets in documentation tests. Illustrative example:

~~~http
Authorization: Bearer <access-token>
~~~

The line above is an instructional placeholder. Readers must substitute a valid token when practicing; it does not mean Spring REST Docs issues tokens or automatically replaces real tokens with sample values.

When needed, use `preprocessRequest(...)` to **remove or replace data written to snippets**. For example, removing headers unsuitable for public docs:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Replace the document(...) call at the end of the test with:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

Keep in mind:

- Once authentication headers are stripped, the command is **no longer a complete copy of the sent request** and may return `401` when replayed; documentation should instruct readers to provide valid authentication.
- When you want to preserve structure while avoiding exposing secrets, consider dummy token fixtures and value-masking/replacement mechanisms in snippets. Ensure replaced tokens cannot be mistaken for real ones.
- Never write real tokens into documentation, CI artifacts, or public logs.
- Do not use `-k`/`--insecure` to bypass TLS checks just because a snippet hits certificate errors; fix trusted certificate configuration in the test environment instead.
- `POST`, `PUT`, `PATCH`, and `DELETE` commands can modify data. Test against an appropriate environment and resources to avoid unintended side effects.

`preprocessRequest` only modifies the **record used to generate snippets**; it does not alter the request processed by the controller and does not replace assertions. When you need to prove the system authenticates properly, write dedicated authentication/authorization tests.

## 10. WebTestClient and REST Assured Also Generate `curl-request`

Despite different test syntax, Spring REST Docs still captures operation details to generate `curl-request.adoc` when the client is properly integrated.

### 10.1. WebTestClient

With `WebTestClient` **configured for Spring REST Docs**, a listing operation might look like this:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/books?page=0&size=10")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("books-list-webtestclient"));
~~~

After the test passes, inspect the snippet at the path corresponding to WebTestClient's output directory and identifier `books-list-webtestclient`. The integration module is `spring-restdocs-webtestclient`; how REST Docs is wired with WebTestClient depends on the test style and Spring version used.

### 10.2. REST Assured

REST Assured records operations via a **filter** provided by Spring REST Docs. Example with a `RequestSpecification` configured for the server and REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec must already be configured for the test server and Spring REST Docs.
given(spec)
    .filter(document("books-list-restassured"))
    .accept("application/json")
.when()
    .get("/api/books?page=0&size=10")
.then()
    .statusCode(200);
~~~

Use the `spring-restdocs-restassured` module and set up `RestAssuredRestDocumentationConfigurer` or the configuration method supported by your version. The filter records the operation when sending the request; the `statusCode(200)` assertion happens in `then()`. Therefore, the pipeline must confirm all tests pass before publishing documentation.

### 10.3. Client Comparison

| HTTP test client | Selecting the operation | Documentation point |
| --- | --- | --- |
| MockMvc | `perform(post("/api/books"))` | `andDo(document("books-create"))` |
| WebTestClient | `webTestClient.get().uri(...)` | `expectBody().consumeWith(document("..."))` |
| REST Assured | `given(spec)...when().get(...)` | Filter `document("...")` on the request |

Common principle: **the `curl` command must originate from a request executed in a test**, not from a hand-typed cURL sample claimed to be generated by REST Docs.

## 11. Including `curl-request` in Asciidoctor Documentation

Under standard default configuration, Spring REST Docs outputs snippets with the `.adoc` extension. An Asciidoctor page can include multiple operations:

~~~asciidoc
= Books API

== Create Book

Send POST /api/books with a valid title and price.

=== Try with curl

include::{snippets}/books-create/curl-request.adoc[]

=== HTTP response

include::{snippets}/books-create/http-response.adoc[]

== List Books

=== Try with curl

include::{snippets}/books-list/curl-request.adoc[]

=== Query parameters

include::{snippets}/books-list/query-parameters.adoc[]
~~~

The Asciidoctor `snippets` attribute needs to be defined by the build to point to the appropriate snippet path, such as `build/generated-snippets`. Absolute or relative paths must align with the build configuration and source doc location.

When writing Markdown documentation, `include::{snippets}/...[]` syntax does not work automatically across every Markdown renderer. Projects need a conversion step or corresponding templating/inclusion mechanism. The goal is to **use snippet content generated by tests**, rather than maintaining an error-prone, hand-written `curl` command.

### Build and CI Integration

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Assertions pass?"}
    B -->|No| C["CI fails, do not publish"]
    B -->|Yes| D["Generate curl-request and other snippets"]
    D --> E["Build Asciidoctor/Markdown"]
    E --> F{"Docs build passes?"}
    F -->|No| C
    F -->|Yes| G["Package or publish documentation"]
~~~

Configure the documentation task to depend on the test task that generates snippets, and fail on test failures or invalid includes. If reusing an output directory with stale snippets, including a leftover file can make docs "look up-to-date". Control artifacts, dependencies, and test scope so the documentation build reflects current test results.

A change to an endpoint path, method, or JSON body should be reflected by **updating tests + assertions + regenerating snippets**. Editing a hand-written `curl` line directly on the doc page bypasses Spring REST Docs' verification benefits.

## 12. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `curl-request.adoc` is missing | `document(...)` not attached, test stopped before recording, wrong output directory/identifier, or customized default snippets | Verify the test executes completely and check the correct snippet directory. |
| `curl` calls a non-existent host | MockMvc test has no HTTP server at the displayed URL; host is configured as an example | Replace the host with a real server or clarify the test environment URL. |
| Command returns `401` when replayed | Test uses mock security/session, auth header was masked, or user lacks a token | Provide valid credentials; do not put secrets in documentation. |
| Unexpected HTTP method | Test mistakenly called `get`/`post` or included the wrong identifier | Check the builder, assertions, and `http-request.adoc` for that operation. |
| JSON body breaks when copied | Quoting/escaping differences across Bash, PowerShell, and CMD | Use a JSON file with `--data-binary @file` or adapt syntax for the shell. |
| Query parameters lost or mangled | URI/query string not built properly, shell interpreted `&`, or unencoded values | Use `queryParam(...)` in tests; quote URLs and encode values when running. |
| `curl` exits 0 despite HTTP `404` | `curl` distinguishes transport errors from HTTP errors by default | Check status via `-i`, or use appropriate HTTP status handling for automation. |
| First `POST` returns `201`, next returns `409` | Resource already exists or test data state changed | Reset fixtures or use fresh test data; document non-idempotent behavior. |
| Command contains a real token or cookie | Sensitive test fixture or preprocessing not configured | Replace test data with dummy values, mask, or remove headers before generating snippets. |
| Docs page shows an outdated cURL command | Docs build does not depend on tests; included a file from a previous build | Fix task dependencies, snippet source paths, and CI failure conditions. |

## 13. Verified Hands-on Practice

Suppose you are building a book API with the following endpoints:

| Operation | Expected status | Suggested identifier |
| --- | --- | --- |
| `POST /api/books` with JSON `title`, `price` | `201 Created` | `books-create` |
| `GET /api/books?page=0&size=10` | `200 OK` | `books-list` |
| `GET /api/books/42` | `200 OK` | `books-get-one` |
| `DELETE /api/books/42` | `204 No Content` | `books-delete` |

Perform these steps:

1. Write an individual test for each operation. Assert the exact status; add body/header assertions where required by the contract.
2. Attach `document(...)` with distinct identifiers. Run the tests and inspect the four `curl-request.adoc` files.
3. Compare `curl-request` and `http-request` for each operation: do the method, URI, query, headers, and body match?
4. Choose a local/staging server with test data, adjust the URL/credentials for that environment, and replay at least one `GET` and one `POST` command.
5. Compare the real response against `http-response` and test assertions; explain any differences caused by environment or data.
6. Include snippets in Asciidoctor; confirm build/CI does not publish when a test fails or a snippet is missing.

### Completion Criteria

You have completed this lesson when you can **explain each part of a `curl` command**, generate snippets from tests instead of writing them manually, replay requests against an accessible server, distinguish environment differences from API contract bugs, and integrate snippets into documentation built after tests pass.

## References

- [Spring REST Docs Reference — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs Reference — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/)
- [curl — Everything curl](https://everything.curl.dev/)
- [curl command-line options](https://curl.se/docs/manpage.html)
