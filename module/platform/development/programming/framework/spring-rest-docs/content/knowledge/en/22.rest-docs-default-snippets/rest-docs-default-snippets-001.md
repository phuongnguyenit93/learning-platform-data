# List of Default Snippets in Spring REST Docs

## 1. What Is a Snippet and When Is It Generated?

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests generate small documentation fragments called *snippets*. They describe the request, response, payload, parameters, and headers executed by the test, and are then assembled into Asciidoctor or Markdown documentation and included in the build/CI.

Spring REST Docs does not automatically scan all endpoints to generate complete documentation. A test must call the documentation API, typically `document(...)`, after performing a request. When an operation is recorded, REST Docs generates the basic HTTP snippets. Tables describing path parameters, headers, JSON fields, or links are only generated when the test declares the corresponding descriptors.

With the default AsciiDoc format, six common basic HTTP snippets are:

| File Name | Content |
| --- | --- |
| curl-request.adoc | cURL command that can be used to reproduce the request. |
| httpie-request.adoc | HTTPie command corresponding to the request. |
| http-request.adoc | Request in HTTP message format. |
| http-response.adoc | HTTP response received by the test. |
| request-body.adoc | Body sent by the client. |
| response-body.adoc | Body returned by the server. |

These files record the operation observed by the test. They do not explain business logic on their own, do not replace assertions, and do not prove that the entire API has been tested. To document fields, parameters, headers, or links, the test must add the appropriate descriptors.

## 2. Six Basic HTTP Snippets

### curl-request.adoc

This snippet generates a cURL command so API integrators can resend the request from a terminal.

```bash
curl 'http://localhost:8080/api/products/42' \
  -i \
  -H 'Accept: application/json'
```

The actual command depends on the request performed by the test: HTTP method, URI, headers, and body. When using RANDOM_PORT, the URI may contain a dynamic port if a dedicated display URI for snippets has not been configured. When publishing documentation, configure the URI so that snippets reflect the host and scheme readers need to use.

### httpie-request.adoc

This snippet represents the same request using HTTPie syntax:

```bash
http GET :8080/api/products/42 Accept:application/json
```

This is an alternative representation, not a second request, nor does it mean the test executed the HTTPie program. REST Docs generates the illustrative command from the recorded operation.

### http-request.adoc

This snippet describes the request as an HTTP message:

```http
GET /api/products/42 HTTP/1.1
Host: api.example.com
Accept: application/json
```

It is useful when you need to read the method, path, and headers at the protocol level. For requests with a body, the headers and body are reflected in the corresponding snippets.

### http-response.adoc

This snippet describes the HTTP response received by the test:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Mechanical Keyboard"}
```

The status and headers serve as evidence from the executed operation. If the response changes, assertions and descriptors can detect that change.

### request-body.adoc

This snippet contains the body sent by the client, typically JSON, form data, or another payload:

```json
{
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

If the operation has no request body, the snippet content may be empty or contain nothing significant. To describe the meaning of each field and validate the payload structure, you need to add requestFields(...).

### response-body.adoc

This snippet contains the body returned by the server:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

It helps readers view a sample payload. To produce a field description table and check for unexpected fields, declare responseFields(...).

## 3. Additional Snippets Generated from Descriptors

REST Docs provides many other snippet types beyond the six basic HTTP snippets. They appear when the test passes the corresponding descriptors or configuration into document(...).

| Category | Commonly Used Descriptor/API | Common Snippet Name | Information |
| --- | --- | --- | --- |
| Path parameter | pathParameters(...) | path-parameters.adoc | Variables in a URI template, e.g., {id}. |
| Request parameter | requestParameters(...) or the client's equivalent API | request-parameters.adoc | Parameters sent with the request as supported by the client/API. |
| Request header | requestHeaders(...) | request-headers.adoc | Headers sent by the client. |
| Response header | responseHeaders(...) | response-headers.adoc | Headers returned by the server. |
| Request field | requestFields(...) | request-fields.adoc | Fields of the request payload. |
| Response field | responseFields(...) | response-fields.adoc | Fields of the response payload. |
| Hypermedia link | links(...) | links.adoc | Link relations and link targets in a hypermedia payload. |

Descriptor names and support depend on the client module (MockMvc, WebTestClient, or REST Assured) and the Spring REST Docs version. Choose the corresponding documentation API; do not apply a MockMvc import to WebTestClient.

### Path parameter

Example endpoint GET /api/products/{id}:

```java
mockMvc.perform(get("/api/products/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("products-find",
        pathParameters(
            parameterWithName("id").description("Product ID")
        )
    ));
```

With MockMvc, use RestDocumentationRequestBuilders.get(...) when you need to preserve the URI template for path parameter extraction. If the builder does not preserve the template, REST Docs may not be able to identify the name {id} from the expanded URI.

### Request header and response header

```java
document("products-find",
    requestHeaders(
        headerWithName("Accept")
            .description("Desired response format")
    ),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Returned payload format")
    )
)
```

Header descriptors allow the documentation to clearly state what each header means. For authentication credentials, do not let real tokens or cookies appear in snippets; use dummy data dedicated to tests and redact them before saving documentation.

### Request and response fields

```java
document("products-create",
    requestFields(
        fieldWithPath("name").description("Product name"),
        fieldWithPath("price").description("Selling price")
    ),
    responseFields(
        fieldWithPath("id").description("Created product ID"),
        fieldWithPath("name").description("Product name"),
        fieldWithPath("price").description("Selling price")
    )
)
```

Field descriptors both generate tabular snippets and validate the payload against the declared descriptions. If the JSON contains an undocumented field, the test may fail. Clearly decide which fields are optional, which parts are intentionally ignored, and update descriptors when the contract changes.

## 4. Snippet Directory Structure

The subdirectory name is determined by the operation ID passed to document("..."); the root directory is determined by Spring REST Docs/Spring Boot or outputDir.

Default Gradle example:

```text
build/
  generated-snippets/
    products-find/
      curl-request.adoc
      httpie-request.adoc
      http-request.adoc
      http-response.adoc
      request-body.adoc
      response-body.adoc
      path-parameters.adoc
      request-headers.adoc
      response-headers.adoc
      response-fields.adoc
```

With Maven, the default root directory is usually target/generated-snippets/. Not every operation has all the listed files: snippets depend on the request type, body, descriptors, and client module. You should not look at the output of a GET and assume a POST or bodyless operation has the same set of files.

If the test configures outputDir to build/custom-snippets, the products-find operation resides under build/custom-snippets/products-find/. Asciidoctor must read from this exact directory instead of continuing to pull from build/generated-snippets.

## 5. AsciiDoc and Markdown

Spring REST Docs uses AsciiDoc templates by default, so snippet files typically have the .adoc extension. When configuring TemplateFormats.markdown(), snippets can be generated as .md; the root directory and operation ID still follow the same rules.

Example Markdown template configuration for MockMvc:

```java
@TestConfiguration(proxyBeanMethods = false)
class RestDocsMarkdownConfiguration
        implements RestDocsMockMvcConfigurationCustomizer {

    @Override
    public void customize(MockMvcRestDocumentationConfigurer configurer) {
        configurer.snippets()
            .withTemplateFormat(TemplateFormats.markdown());
    }
}
```

Load the configuration using @Import(RestDocsMarkdownConfiguration.class) into the test context. If you switch to Markdown, you must update the document assembly tool and include paths; Asciidoctor `include ... .adoc` syntax does not automatically convert to Markdown includes.

| Format | File Extension | Assembly Tool |
| --- | --- | --- |
| Default AsciiDoc | .adoc | Asciidoctor |
| Markdown | .md | Markdown processor/static site generator supporting includes or a custom assembly mechanism |

## 6. Including Snippets in Asciidoctor

The AsciiDoc source file can select which snippets to present:

```asciidoc
= Catalog API
:toc: left

== Find product

=== HTTP request
include::{snippets}/products-find/http-request.adoc[]

=== cURL
include::{snippets}/products-find/curl-request.adoc[]

=== Path parameters
include::{snippets}/products-find/path-parameters.adoc[]

=== Response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

The snippets attribute must point to the root directory. With Gradle, the default path is usually build/generated-snippets; with Maven, it is usually target/generated-snippets. If tests use a custom outputDir, the build must use that exact path.

There is no need to include every snippet on every page. Integration guides might prioritize cURL and response fields; internal debugging docs might show raw request/response messages and headers. Select the appropriate fragments to keep pages readable.

## 7. Build and CI

With Gradle, declare snippets as an output of test and an input of Asciidoctor:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

Run from a clean state:

```bash
./gradlew clean test asciidoctor
```

With Maven, run tests before the Asciidoctor step and set the snippets attribute to point to the directory under target/generated-snippets. If snippets are only generated by integration tests in Failsafe, the documentation step must run after those tests.

CI should generate snippets and documentation in the same pipeline. Do not skip tests if required snippets are only generated by tests; do not publish HTML if tests or Asciidoctor fail. Use a clean build when verifying the pipeline to avoid stale snippets left over from previous runs.

## 8. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| The REST Docs dependency automatically generates all snippets when tests run. | An operation must be recorded with document(...). |
| Every operation has every snippet file. | Snippets depend on the request type, body, descriptors, and client module. |
| response-body.adoc explains the JSON schema. | It displays the body; a field description table requires responseFields(...). |
| http-request.adoc is equivalent to curl-request.adoc. | One file is an HTTP message, while the other is a cURL command to reproduce the request. |
| The folder name is automatically inferred from the URL/controller. | The operation ID passed to document(...) determines the subfolder. |
| Switching templates to Markdown only changes the file extension. | You also need to change how documentation is assembled and update the corresponding includes. |
| A snippet with a production URL means the test called production. | The URI can be configured/preprocessed separately; the test can still call localhost. |

## 9. Hands-on Exercise

Create two operations for the Catalog API:

1. GET /api/products/{id}: record the request, response, path parameter, request header, and response fields.
2. POST /api/products: record the request body, request fields, Location response header, and response fields.
3. Run the tests, open the output directory, and classify the files into basic HTTP snippets and descriptor snippets.
4. Write AsciiDoc including http-request, curl-request, http-response, and the field tables for each operation.
5. Remove one descriptor and rerun the tests to observe the change in the corresponding snippet and contract validation.
6. Change the operation ID and outputDir, update the snippets attribute in the build, and run a clean build.
7. Optional: change the template format to Markdown and design a step to assemble .md snippets into the documentation.

**Completion criteria:** name and explain the six basic HTTP snippets; know which descriptor snippet appears when declaring the corresponding API; identify the correct output folder and operation ID; assemble snippets into Asciidoctor; CI generates documentation from snippets of the current test run.

## 10. References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Boot 3.5 — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
