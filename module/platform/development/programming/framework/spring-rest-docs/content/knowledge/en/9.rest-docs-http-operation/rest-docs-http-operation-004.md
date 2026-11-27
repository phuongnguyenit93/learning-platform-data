# The `httpie-request` Snippet and Choosing a Command-Line Tool

## 1. Objectives and Context

In the **HTTP operation** chapter of `SPRING_REST_DOCS`, each time a test sends a request and receives a response, it can generate documentation fragments (snippets) based on that exact HTTP exchange. While `http-request.adoc` presents the request as plain HTTP text and `curl-request.adoc` presents a `curl` command, **`httpie-request.adoc` generates an HTTPie command example** so readers can easily call the API from a terminal.

This lesson serves Spring REST Docs' goal: **generating verifiable REST API documentation** from MockMvc, WebTestClient, or REST Assured tests; producing snippets for requests, responses, payloads, parameters, and headers; and then integrating Asciidoctor/Markdown documentation into build and CI pipelines.

After this lesson, you will know:

- What `httpie-request` is, when it is generated, and where it lives in test output.
- How to read an HTTPie command and distinguish HTTP method, URL, request headers, query parameters, and JSON body.
- How to verify a request with MockMvc and generate `httpie-request.adoc` along with supporting snippets.
- How to choose between HTTPie, `curl`, or raw HTTP representation for different documentation audiences.
- How to test commands against a live environment, avoid leaking secrets, and keep docs updated in CI.

> **Note:** the HTTPie command in the snippet is a **representation of an HTTP request executed by a test**. That command does not start a server, create fixtures, authenticate on the user's behalf, or guarantee that running against another environment will produce the exact same response as the test.

## 2. How Does `httpie-request` Appear?

Spring REST Docs records an **HTTP operation**, consisting of a request and a response. Under standard configuration, when a test calls `document("identifier")`, REST Docs creates snippets in a directory named after that identifier:

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

These are the **six default snippets** of Spring REST Docs when the snippet set has not been customized. The root directory name depends on the output directory configuration and build tool (for example, Gradle typically uses `build/generated-snippets`, while Maven may use `target/generated-snippets`).

| Snippet | Question answered |
| --- | --- |
| **`httpie-request.adoc`** | "How can I try this request using HTTPie's `http` command?" |
| `curl-request.adoc` | "What is the equivalent `curl` command to send this request?" |
| `http-request.adoc` | "What method, URI, headers, and body does the request have?" |
| `http-response.adoc` | "What status, headers, and body did the actual response in the test return?" |
| `request-body.adoc` | "What is the request body content on its own?" |
| `response-body.adoc` | "What is the response body content on its own?" |

Tabular snippets such as `request-fields.adoc`, `request-headers.adoc`, or `query-parameters.adoc` are generated when the test declares the corresponding descriptors, not simply because `httpie-request` was created.

~~~mermaid
flowchart LR
    A["HTTP test: MockMvc / WebTestClient / REST Assured"] --> B["HTTP operation"]
    B --> C["document(identifier)"]
    C --> D["httpie-request.adoc"]
    C --> E["curl-request.adoc"]
    C --> F["http-request.adoc"]
    C --> G["http-response.adoc"]
    D --> H["API Documentation"]
    E --> H
    F --> H
    G --> H
~~~

In MockMvc examples, we place `document(...)` after assertions. This ensures snippets are written only after expected conditions pass verification; the pipeline only publishes when **all relevant tests succeed**.

## 3. What Is HTTPie and What Syntax Does It Use?

[HTTPie](https://httpie.io/) is a command-line HTTP client designed for calling and exploring APIs with syntax close to how humans describe a request. The command is usually `http` (or `https` if the installation provides that shortcut).

A simple resource request:

~~~bash
http GET https://api.example.com/api/books/42 Accept:application/json
~~~

Components:

| Component | Value | Meaning |
| --- | --- | --- |
| Executable | `http` | The HTTPie CLI installed on the machine. |
| Method | `GET` | HTTP method sent to the server; writing it explicitly keeps docs clear. |
| URL | `https://api.example.com/api/books/42` | Scheme, host, path, and query string if present. |
| Header | `Accept:application/json` | Requests the desired media type for the response. |

Use `http --version` to check whether the tool is installed. The examples in this lesson illustrate common HTTPie CLI syntax; depending on your HTTPie version and shell, quotes, flags, or formatting may vary slightly.

### 3.1. Key Request Item Separators

HTTPie uses separators with distinct meanings:

| Syntax | Example | How HTTPie handles it |
| --- | --- | --- |
| `Name:Value` | `Accept:application/json` | Request header. |
| `field=value` | `title='Spring in Action'` | Data field; defaults to a string property in a JSON object when sending a structured body. |
| `field:=json` | `price:=199000`, `available:=true` | Raw JSON value: number, boolean, null, object, or array in valid JSON syntax. |
| `name==value` | `page==0`, `size==10` | Query string parameter on the URL. |
| `field@file` | `cover@cover.png` | File sent as form/multipart when using the appropriate mode. |
| `--raw` | `--raw='{"title":"Spring"}'` | Entire raw request body; not combined with structured data fields. |
| `--form` or `-f` | `--form POST ...` | Sends form data instead of the default JSON. |

**Example with different data types:**

~~~bash
http POST https://api.example.com/api/books \
  title='Spring in Action' \
  price:=199000 \
  available:=true \
  tags:='["java","spring"]'
~~~

In HTTPie syntax, `title` is a string; `price` is a number; `available` is a boolean; `tags` is an array. The `:=` separator is not just a fancier `=`: replacing `price:=199000` with `price=199000` changes the JSON value sent from a number to a **string**.

For the command above, the structurally equivalent JSON body is:

~~~json
{
  "title": "Spring in Action",
  "price": 199000,
  "available": true,
  "tags": ["java", "spring"]
}
~~~

Fields are serialized by HTTPie in the chosen format. Even if the JSON is semantically equivalent, property ordering or whitespace may differ from the original request; if you need to preserve the exact **body bytes**, use an appropriate raw body option.

### 3.2. Default Method

HTTPie typically infers:

- `GET` when there is no request body;
- `POST` when body data is present.

API documentation should still **write the method explicitly**: `http GET ...`, `http POST ...`, `http PATCH ...`. That prevents a reader from adding a data field and accidentally changing the request's HTTP method.

## 4. Reading an Operation's `httpie-request` Snippet

Suppose the application exposes `POST /api/books` with this request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: docs-001

{"title":"Spring in Action","price":199000}
~~~

An **illustrative** HTTPie command for the request above:

~~~bash
http POST https://api.example.com/api/books \
  Content-Type:application/json \
  Accept:application/json \
  X-Request-Id:docs-001 \
  --raw='{"title":"Spring in Action","price":199000}'
~~~

This is a valid HTTPie command in common syntax; **there is no guarantee that every quote, argument order, or body representation matches the exact snippet generated by Spring REST Docs**. REST Docs may pass the raw request body or use a different command-line format depending on its formatter/template and version. When you need the exact generated output, open `httpie-request.adoc` produced by your test.

You can rewrite the command above to build JSON from data items:

~~~bash
http POST https://api.example.com/api/books \
  Accept:application/json \
  X-Request-Id:docs-001 \
  title='Spring in Action' \
  price:=199000
~~~

HTTPie defaults to JSON for structured data items unless configured otherwise. The two commands can produce **semantically equivalent** payloads here, but do not assume bodies, headers, and bytes are identical in all cases. If an API requires a body-based signature, preserve the exact format the client must send.

### Why Is `--raw` Sometimes Needed?

Some request bodies are hard or unsuitable to express via `field=value`, such as a top-level JSON array or string, XML data, plain text, bodies with special whitespace, or signed payloads. Using `--raw`, piping from stdin, or passing the body from a file is clearer.

With a prepared JSON file, HTTPie supports reading the request body from a file:

~~~bash
http POST https://api.example.com/api/books \
  Content-Type:application/json \
  @book.json
~~~

Here `@book.json` means **raw body from file**, unlike the `cover@cover.png` request item used for file uploads. The `book.json` file must exist in the environment where the command runs. No file is automatically created by Spring REST Docs just by generating such a command.

## 5. Writing a MockMvc HTTP Test to Generate the Snippet

### 5.1. Setup

The example uses Spring Boot 3.x, Spring MVC, JUnit 5, and Java 17+. The project needs the Spring Boot test dependency and Spring REST Docs MockMvc.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Let Spring Boot's dependency management/BOM select compatible library versions for your project.

Assume the `POST /api/books` endpoint already exists, accepts JSON with `title` and `price`, and returns `201 Created` on success. This is an **illustrative** contract; Spring REST Docs does not create controllers, data, or servers on its own.

### 5.2. Test Example

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
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
            .andDo(document("books-create",
                requestFields(
                    fieldWithPath("title").description("Book title"),
                    fieldWithPath("price").description("Book price in VND")
                )
            ));
    }
}
~~~

Explanation:

1. `post("/api/books")` creates an HTTP request with method `POST` and path `/api/books`.
2. `contentType(...)`, `accept(...)`, `header(...)`, and `content(...)` supply actual headers and body.
3. `andExpect(status().isCreated())` verifies that the response returns `201` before generating documentation.
4. `document("books-create", ...)` records the operation and generates default snippets, including `httpie-request.adoc`.
5. `requestFields(...)` generates a field description table in `request-fields.adoc`; these descriptors also verify the documented payload.
6. `@AutoConfigureRestDocs(...)` uses the sample hostname `api.example.com` to render URIs in documentation; it does **not** deploy the endpoint at that host.

After the test passes, you can inspect:

~~~text
build/generated-snippets/books-create/httpie-request.adoc
build/generated-snippets/books-create/curl-request.adoc
build/generated-snippets/books-create/http-request.adoc
build/generated-snippets/books-create/http-response.adoc
build/generated-snippets/books-create/request-fields.adoc
~~~

These snippets share the same identifier and therefore describe **one operation**. If the project customizes the default snippet set, one or more files might not appear.

> **Do not mix "illustrative examples" with "test output":** the HTTPie commands shown in this lesson help explain syntax; `httpie-request.adoc` on disk is what your project's configuration actually generated.

## 6. `GET`, Query Strings, and HTTPie Syntax Choices

For `GET /api/books?page=0&size=10`, a readable HTTPie command is:

~~~bash
http GET 'https://api.example.com/api/books?page=0&size=10' \
  Accept:application/json
~~~

HTTPie also supports declaring query parameters using request items:

~~~bash
http GET https://api.example.com/api/books \
  page==0 \
  size==10 \
  Accept:application/json
~~~

Both commands send query parameters `page=0` and `size=10`. However, **do not add `page==0` to a command that already has `?page=0`** unless you intend to produce duplicate parameters.

In a MockMvc test, use `queryParam(...)` to make the query string explicit and generate the corresponding description table. Place the snippet below inside the same test class configured in the previous section (add static imports as needed):

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

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

The output typically includes:

~~~text
build/generated-snippets/books-list/httpie-request.adoc
build/generated-snippets/books-list/query-parameters.adoc
~~~

`httpie-request` helps **send the request**, while `query-parameters` explains **parameter meaning** and whether each parameter is required. Do not treat a CLI command as a complete API contract specification table.

### URI Path Parameters

For `GET /api/books/42`, the request uses a concrete URI:

~~~bash
http GET https://api.example.com/api/books/42
~~~

When introducing the endpoint in documentation, you can write the template `/api/books/{id}`; however, an executable command must contain a real value like `42`. To generate `path-parameters.adoc` with MockMvc, use a request builder that preserves URI template information alongside the `pathParameters(...)` descriptor.

## 7. Choosing HTTPie, `curl`, or Raw HTTP Requests

No single command-line tool fits every documentation reader equally well. Spring REST Docs generates both `httpie-request` and `curl-request` so documentation teams can serve different preferences from the same operation.

| Criterion | HTTPie (`http`) | `curl` | Plain `http-request` |
| --- | --- | --- | --- |
| Audience | Developers who want to test APIs and read JSON in the terminal | Developers, ops, scripts, and automation environments | Readers who want to understand the exact HTTP structure |
| Syntax | Concise for headers, query params, and JSON objects | Very flexible; flags `-X`, `-H`, `-d`, etc. | Request line, headers, and body |
| JSON | `field=value`, `field:=json`, `--raw` | Passes body via `--data`/`--data-binary` or file | Displays the recorded payload |
| Output display | Defaults to human-readable responses; formatted and colored | Usually prints response body, optional flags for headers | Documentation only, not an executable command |
| Automation use | Supported with status-checking and output-control flags | Ubiquitous in shell scripts and build environments | Not directly executable |
| Installation requirement | Requires HTTPie CLI | Requires `curl` for the environment | No CLI needed to read |
| Request byte fidelity | Depends on how body is built and `--raw`/file flags | Depends on how body is passed, encoding, and flags | Describes only the request as represented by REST Docs |

**Choose HTTPie when:**

- Documentation guides developers to test JSON APIs with easy-to-read, easy-to-edit parameters.
- Readers frequently work in the terminal and want formatted responses right away.
- The goal is API exploration or semantically equivalent operation replay.

**Choose `curl` when:**

- Your team's environment already uses `curl` in shell scripts or CI.
- Documentation needs examples compatible with a wide range of environments where `curl` is preinstalled.
- Specific flags are needed for data transfer, connection diagnostics, or automation.

**Include both in documentation when** your user base includes both developers who prefer HTTPie and ops teams accustomed to `curl`. Two auto-generated snippets keep both examples maintained from the same test, reducing drift between commands.

Never claim HTTPie **always** produces a byte-for-byte identical request to `curl`. The two clients may differ in default headers, User-Agent, Content-Length, Accept-Encoding, header ordering, JSON serialization, or redirect handling. API contracts generally require equivalence in **method, URI, relevant headers, and payload content**, not identical bytes everywhere.

## 8. Inspecting Results and Debugging with HTTPie

HTTPie not only sends requests, it also offers flags to inspect HTTP exchanges and results from the command line:

| Flag | Purpose |
| --- | --- |
| `--headers` or `-h` | Print response headers. |
| `--body` or `-b` | Print response body. |
| `--verbose` or `-v` | Show both request and response for debugging. |
| `--print=Hh` | Selectively print request headers (`H`) and response headers (`h`). |
| `--print=HhBb` | Print request headers/body along with response headers/body. |
| `--offline` | Build and print the request **without sending over the network**; useful for checking syntax. |
| `--check-status` | Use the HTTP status to determine the exit code, useful in scripts. |
| `--follow` | Follow redirects when needed; understand its impact on HTTP method and target URL. |

Example of checking request syntax without calling a server:

~~~bash
http --offline POST https://api.example.com/api/books \
  Content-Type:application/json \
  title='Spring in Action' price:=199000
~~~

The `--offline` command builds the request locally for inspection without creating a book. It only verifies **CLI syntax**, not whether the endpoint exists or complies with the API contract.

To view both request and response when calling a real server:

~~~bash
http --print=HhBb GET http://localhost:8080/api/books/42
~~~

To use in scripts and receive an exit code reflecting HTTP errors:

~~~bash
http --check-status GET http://localhost:8080/api/books/42
~~~

Normally HTTPie may exit with a success code even when the HTTP response is an error if status checking is not enabled. With `--check-status`, HTTPie returns an error exit code for HTTP error statuses (and unfollowed redirects according to CLI behavior); business verification still requires inspecting the status and payload.

### Do Not Confuse Exit Codes with Spring REST Docs Assertions

- `.andExpect(status().isOk())` in MockMvc verifies the exact status required by the test.
- `--check-status` in HTTPie only helps scripts detect **error status groups**.
- A `200` response containing wrong data still lets both `curl` and HTTPie finish normally. For reliability, combine tests with header/body assertions or appropriate JSON checks.

## 9. Reproducing Requests in a Real Environment

Snippets generated from tests may contain illustrative URLs like `https://api.example.com`. Especially with MockMvc, tests can run **in-process**, without opening an HTTP port on that hostname.

To test with HTTPie, ensure an accessible real server is running:

~~~bash
http GET http://localhost:8080/api/books/42 Accept:application/json
~~~

If no server is running at `localhost:8080`, the command fails with a connection error. Changing the URL when testing manually is normal, but distinguish illustrative URLs from the actual URI tested.

Factors that change outcomes:

| Factor | In the test | When running HTTPie outside tests |
| --- | --- | --- |
| Server | May be MockMvc without sockets | Requires an active host/port |
| Database | Fixtures loaded and rolled back/reset | Contains current environment data |
| Authentication | May use mock users or security context | Requires valid credentials |
| Newly created resources | Fixture/ID may be fixed | May allocate a new ID or hit conflicts |
| Clock/timestamp | May be fixed in the test | Values may vary |
| Headers | Test client/REST Docs records one header set | HTTPie adds its own default headers |
| Response | Assertions verify defined conditions | Result depends on environment and data |

For example, a `POST` to create a book may return `201` in the test but `409 Conflict` when replayed if that book already exists under business rules. That may simply be a difference in data state, not enough to conclude the snippet is wrong.

To make documentation **reproducible**, also provide environment setup instructions, test accounts, prerequisite data, and required operation order. Never place real credentials in documentation.

## 10. Authentication Headers, Cookies, and Sensitive Data

An HTTPie command can include headers like this:

~~~bash
http GET https://api.example.com/api/books/42 \
  'Authorization:Bearer <access-token>'
~~~

`<access-token>` here is merely a **placeholder**. It must be replaced with a valid test token where used. Shells and command history may store typed commands verbatim; avoid pasting real tokens into docs, CI logs, or shared command history.

If tests contain sensitive data, use dummy fixtures or a Spring REST Docs request preprocessor to remove/normalize what appears in snippets:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Example replacing the .andDo(document(...)) call in a test:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

This example **replaces the `document(...)` call**; it is not an extra call added to a test that already uses the same identifier. If the test also uses `requestFields(...)` or other descriptors, keep them in this same `document(...)` call.

Key points to remember:

1. Stripping authentication headers from snippets avoids exposing secrets, but the generated command may **fail on endpoints requiring authentication**. Explain how readers should supply valid credentials.
2. When you want to keep the header in sample commands, replace the value with a safe placeholder rather than putting real tokens into fixtures. Note the difference between the processed request and the request represented in documentation.
3. Never commit HTTPie session files containing tokens/cookies. HTTPie supports `--session`, and session files can hold credentials, so treat them as sensitive data.
4. Avoid disabling TLS verification just to "make the command run"; fix certificates or trusted environments instead of lowering security.
5. `POST`, `PUT`, `PATCH`, and `DELETE` methods can modify data. Instruct readers to use test resources and permitted environments.

## 11. Standardizing URLs and Snippet Content

In the MockMvc example above:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

These attributes tell REST Docs to display URIs in snippets with the desired hostname, scheme, and port. They **do not change how the tested application processes requests** and do not guarantee `api.example.com` is a real server.

When you need to display a public hostname different from the operation's hostname, use the `modifyUris()` preprocessor for the documented request record:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Example replacing document(...) at the end of the test chain:
.andDo(document("books-list",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
));
~~~

If `books-list` needs to generate `query-parameters.adoc` as in section 6, keep `queryParameters(...)` inside the same `document(...)` call. The example configurations above do not require using both the annotation and the preprocessor together; a project can pick whichever approach keeps URIs consistent.

Spring REST Docs also lets you customize snippet templates or the default snippet set. When you only want to keep needed CLI examples, configure default snippets via `RestDocumentationConfigurer` using snippets such as `CliDocumentation.httpieRequest()` or `CliDocumentation.curlRequest()`. Changing default snippets affects auto-generated files, so update `include` directives in documentation to match the remaining files.

## 12. WebTestClient and REST Assured

HTTPie snippets are not limited to MockMvc. Spring REST Docs provides integration modules for WebTestClient and REST Assured; as long as the client is properly configured to record operations, it generates request, response, and CLI snippets.

### 12.1. WebTestClient

Example for a client already configured with Spring REST Docs:

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

`expectStatus().isOk()` verifies the `200` response, while `consumeWith(document(...))` generates snippets for the operation under identifier `books-list-webtestclient`. This integration uses `spring-restdocs-webtestclient` and REST Docs configuration on the client.

### 12.2. REST Assured

With REST Assured, Spring REST Docs records operations via a **filter**:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec is configured with base URI/port and Spring REST Docs.
given(spec)
    .filter(document("books-list-restassured"))
    .accept("application/json")
.when()
    .get("/api/books?page=0&size=10")
.then()
    .statusCode(200);
~~~

This integration requires `spring-restdocs-restassured` and appropriate filter/output context configuration. The filter may write snippets when the request executes, before the `statusCode(200)` assertion completes. Therefore, **CI must require tests to PASS** before treating documentation as valid.

### 12.3. Comparing Documentation Hooks

| Client | How request is sent | How operation is recorded |
| --- | --- | --- |
| MockMvc | `mockMvc.perform(get(...))` | `.andDo(document("..."))` |
| WebTestClient | `webTestClient.get().uri(...).exchange()` | `.expectBody().consumeWith(document("..."))` |
| REST Assured | `given(spec).when().get(...)` | Filter `document("...")` in the request specification |

Do not write a `http POST ...` line by hand and claim it is verified REST Docs output. Run the tests and inspect the actual `httpie-request.adoc` file generated by the operation.

## 13. Including `httpie-request` in Asciidoctor/Markdown

An Asciidoctor API document can include HTTPie snippets directly in endpoint usage sections:

~~~asciidoc
= Books API

== Create Book

Send POST /api/books to create a book.

=== Try with HTTPie
include::{snippets}/books-create/httpie-request.adoc[]

=== Try with curl
include::{snippets}/books-create/curl-request.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response
include::{snippets}/books-create/http-response.adoc[]

== List Books

=== Try with HTTPie
include::{snippets}/books-list/httpie-request.adoc[]

=== Query parameters
include::{snippets}/books-list/query-parameters.adoc[]
~~~

The `snippets` attribute must be configured to point to the actual output directory (e.g., `build/generated-snippets`) during Asciidoctor rendering. An `.adoc` file containing these include directives will not know where to find snippets if the build has not defined the attribute.

If you want to author documentation in **Markdown**, choose a Markdown template or an appropriate snippet conversion/embedding step. Standard Markdown renderers **do not natively understand** Asciidoctor's `include::{snippets}/...[]` directive. The goal remains sourcing examples from tests rather than maintaining stale standalone HTTPie commands.

### Wiring into Build and CI

~~~mermaid
flowchart TD
    A["Run HTTP tests"] --> B{"Assertions pass?"}
    B -->|No| C["Pipeline fails"]
    B -->|Yes| D["Generate httpie-request and other snippets"]
    D --> E["Build Asciidoctor/Markdown"]
    E --> F{"Include and render succeed?"}
    F -->|No| C
    F -->|Yes| G["Publish documentation"]
~~~

Configure the documentation build task to **depend on tests** so snippets are generated during the current run. Avoid situations where an `httpie-request.adoc` from a prior build still gets included when a new test didn't run or no longer generates that identifier.

When an endpoint changes (method, path, headers, request body), update the corresponding code and tests, re-run the tests, and let Spring REST Docs regenerate snippets. That is the primary benefit of verifiable documentation compared to copying an HTTPie command and editing it manually on a web page.

## 14. Common Issues and How to Handle Them

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `httpie-request.adoc` is missing | Missing `document(...)`, test failed before recording, wrong identifier/output directory, or default snippets disabled | Check tests, REST Docs configuration, and folder matching the identifier. |
| `http` command does not run | HTTPie CLI not installed or not on PATH | Install HTTPie CLI for your environment; verify with `http --version`. |
| `http POST ...` returns `401` | Endpoint requires authentication; test mocks user or snippet masked the header | Supply valid test credentials; never put real tokens in source/docs. |
| Numeric body field turned into string | Used `price=199000` instead of `price:=199000` | Use `:=` for JSON number/boolean/array/object values. |
| API receives form data instead of JSON | Used `--form` or mismatched headers/body | Check `Content-Type` and how data items are passed. |
| Query parameters missing or duplicated | Confused `=` with `==` or appended params to a URL that already has a query string | Inspect `http-request`; use only one mechanism per query parameter. |
| Command fails on PowerShell | Trailing `\` line continuation, quoting, or incompatible shell syntax | Use a one-line command or adapt line continuation/escaping for the current shell. |
| `--offline` returns no book data | That flag does not send a network request | Remove `--offline` when calling a real server. |
| Replaying returns `409` instead of `201` | Data already exists or server state changed | Check fixtures, environment, and the API contract. |
| CI reports success despite HTTP error response | `--check-status` not used in scripts, or missing assertions in tests | Add status, header/body checks, and pipeline failure conditions. |
| Docs contain real secrets or cookies | Real fixtures used or headers not masked before generating snippets | Use dummy data, preprocessing, or safe placeholders. |
| Doc page references stale snippets | Build does not re-run tests or includes the wrong identifier | Make docs build depend on tests, manage output dir, and verify newly generated files. |

## 15. Hands-on Exercise

Write documentation for a hypothetical order API consisting of three HTTP operations:

| Operation | Expected result | Identifier |
| --- | --- | --- |
| `GET /api/orders?page=0&size=5` | `200 OK` | `orders-list` |
| `POST /api/orders` with JSON `productId` and `quantity` | `201 Created` | `orders-create` |
| `GET /api/orders/101` | `200 OK` | `orders-get-one` |

Tasks to perform:

1. Write separate tests for the three operations using MockMvc, WebTestClient, or REST Assured; verify HTTP statuses and key response fields.
2. Attach `document(...)` with the corresponding identifiers and run the tests. Open the three newly generated `httpie-request.adoc` files.
3. For the create-order operation, compare `quantity=2` vs. `quantity:=2` in HTTPie; check whether the payload matches the API JSON schema.
4. For the list operation, test both query styles: URL containing `?page=0&size=5` and HTTPie request items `page==0 size==5`. Inspect the request sent.
5. Compare the same operation across `httpie-request.adoc`, `curl-request.adoc`, and `http-request.adoc`. Explain what is equivalent and what may differ by client.
6. Run `--offline` to inspect the constructed request, then call only a local/staging server with test data. Compare the real response with test assertions.
7. Include snippets in Asciidoctor documentation and configure CI to run tests before building/publishing.

**Completion criteria:** you can read HTTPie commands, choose the right method/URL/headers/query/body, generate snippets from verified operations, choose between HTTPie and `curl` based on reader needs, and handle environment differences and sensitive data when reproducing requests.

## References

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Configuring Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [HTTPie CLI — Usage](https://httpie.io/docs/cli/usage)
- [HTTPie CLI — Request Items](https://httpie.io/docs/cli/request-items)
- [HTTPie CLI — Raw JSON](https://httpie.io/docs/cli/raw-json)
- [HTTPie CLI — Offline Mode](https://httpie.io/docs/cli/offline-mode)
