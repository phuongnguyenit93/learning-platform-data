# Embedding Individual Snippets

## 1. Why Include Individual Snippets?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Each operation is recorded with `document("operation-id", ...)` and can produce multiple separate snippets: request/response, headers, parameters, fields, links, or client command examples.

Asciidoctor provides the `include::` macro to embed a snippet file at an exact position in the document. Instead of including all snippets of an operation with `operation::id[]`, writers can choose precisely which files appear, set custom titles in Vietnamese, and add explanations tailored to each example.

Example:

```asciidoc
== Get book by ID

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

Individual includes are suitable when:

- You want to order request, headers, parameters, response, and fields in a specific reading flow.
- You need to explain meaning or business conditions right before/after a snippet.
- You only want to publish a subset of the generated output.
- You want to place custom titles, anchors, admonitions, or cross-references on individual sections.
- You need to combine auto-generated snippets with writer-managed examples, tables, or guides.

## 2. Basic Syntax and the `snippets` Attribute

Syntax to include a snippet:

```asciidoc
include::{snippets}/<operation-id>/<snippet-name>.adoc[]
```

Where:

| Component | Meaning |
| --- | --- |
| `{snippets}` | Attribute pointing to the root directory containing generated snippets. |
| `<operation-id>` | Identifier passed into `document("...", ...)` in the HTTP test. |
| `<snippet-name>.adoc` | Actual snippet filename, for example `http-request.adoc`. |
| `[]` | Optional attributes of the include macro; leave empty when no extra options are needed. |

Example operation in a test:

```java
filter(document("books-get",
        pathParameters(
                parameterWithName("id").description("Book ID")),
        responseFields(
                fieldWithPath("id").description("Book ID"),
                fieldWithPath("title").description("Book title"))))
```

The test writes snippets under the `books-get` operation directory. With the common Gradle convention, the full path is `build/generated-snippets/books-get/`; with Maven, it is typically `target/generated-snippets/books-get/`.

When `spring-restdocs-asciidoctor` is properly loaded into the Asciidoctor plugin, the extension can provide the `snippets` attribute according to the build tool. If the project does not use the extension or needs a custom output directory, configure the attribute from the build or in the source file:

```asciidoc
:snippets: ../../build/generated-snippets
```

Do not declare an absolute path tied to a personal machine. What matters is that where tests write snippets and the `{snippets}` value point to the exact same directory.

## 3. Including Request and Response

The two basic snippets are usually `http-request.adoc` and `http-response.adoc`:

```asciidoc
== Get book by ID

=== Request
include::{snippets}/books-get/http-request.adoc[]

=== Response
include::{snippets}/books-get/http-response.adoc[]
```

`http-request.adoc` shows the method, URI, headers, and body of the request recorded by the test. `http-response.adoc` shows the status, response headers, and body. These two snippets provide the complete HTTP picture before readers inspect detailed descriptor tables.

Explanations can be added between sections:

```asciidoc
=== Request
The client sends a GET request to the book URI. The ID is passed in the path.

include::{snippets}/books-get/http-request.adoc[]

=== Response
When the book is found, the server returns HTTP 200 and a JSON representation.

include::{snippets}/books-get/http-response.adoc[]
```

Descriptions must match the behavior verified by tests. Do not state a status or payload in prose that differs from the actual snippet.

## 4. Including Headers Separately

Spring REST Docs can generate `request-headers.adoc` and `response-headers.adoc` when tests declare header descriptors. Include them in dedicated sections if readers need quick lookup:

```asciidoc
=== Request headers
include::{snippets}/books-create/request-headers.adoc[]

=== Response headers
include::{snippets}/books-create/response-headers.adoc[]
```

Example test descriptors:

```java
filter(document("books-create",
        requestHeaders(
                headerWithName("Content-Type")
                        .description("Format of the submitted payload"),
                headerWithName("Accept")
                        .description("Response format accepted by the client")),
        responseHeaders(
                headerWithName("Content-Type")
                        .description("Response format"),
                headerWithName("Location")
                        .description("URI of the newly created book"))))
```

Not every operation produces header snippets. If the test does not pass `requestHeaders(...)` or `responseHeaders(...)`, the corresponding files may not exist. Include only files actually generated; do not assume every operation produces every snippet type.

## 5. Including Path/Query Parameters and Request Parameters

The parameter snippet path depends on the descriptor type declared in the test:

```asciidoc
=== Path parameters
include::{snippets}/books-get/path-parameters.adoc[]

=== Query parameters
include::{snippets}/books-list/query-parameters.adoc[]

=== Request parameters
include::{snippets}/legacy-search/request-parameters.adoc[]
```

Example:

```java
filter(document("books-list",
        queryParameters(
                parameterWithName("page").description("Page to retrieve"),
                parameterWithName("size").description("Number of items per page"))))
```

Path parameters, query parameters, and request parameters are distinct groups. Use the exact snippet matching the test's descriptor. For form parameters or multipart requests, filenames and descriptor types may differ depending on the Spring REST Docs API used; inspect the generated directory rather than guessing filenames.

## 6. Including Request/Response Body and Field Tables

Body snippets display the actual payload; field snippets describe the structure and meaning of each field. Both can be placed in sequence:

```asciidoc
=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response body
include::{snippets}/books-create/response-body.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
```

The two snippet types do not replace each other:

| Snippet | Content |
| --- | --- |
| `request-body.adoc` | Recorded sample request payload. |
| `request-fields.adoc` | Table of request fields and descriptions. |
| `response-body.adoc` | Recorded sample response payload. |
| `response-fields.adoc` | Table of response fields and descriptions. |

When payloads are large, the body section can provide a copyable JSON example; the fields table helps clarify field types and meanings. If the documentation needs to stay concise, you may include only one of the two, provided integrators still have enough information to use the API.

## 7. Including Hypermedia Links Separately

For HAL or Atom responses, `links.adoc` describes link relations and meanings. It can be placed alongside the HTTP response:

```asciidoc
=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]

=== Link relations
include::{snippets}/orders-get/links.adoc[]
```

`http-response.adoc` preserves `href` and metadata inside the payload; `links.adoc` provides a relation/description table. If the operation does not use `links(...)` in the test or no links are recognized by the extractor, `links.adoc` may not be generated.

## 8. Organizing a Complete Operation with Individual Includes

Example structure for a book creation page:

```asciidoc
== Create book

Creates a new resource. The client sends a JSON body; the server returns HTTP 201
and a Location header pointing to the newly created resource.

=== Request
include::{snippets}/books-create/http-request.adoc[]

=== Request headers
include::{snippets}/books-create/request-headers.adoc[]

=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response
include::{snippets}/books-create/http-response.adoc[]

=== Response headers
include::{snippets}/books-create/response-headers.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
```

This is an illustrative structure. Keep only the includes that tests actually generate. If a test does not declare header descriptors, omit the header table section; if the endpoint has no request body, omit request body and request fields.

## 9. Creating Anchors and Linking to Specific Snippets

When including individual snippets, you can place anchors to cross-reference from other sections:

```asciidoc
[[books_get_request]]
=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

[[books_get_response]]
=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

Linking from elsewhere:

```asciidoc
See examples <<books_get_request, request to get a book>> and
<<books_get_response, returned response>>.
```

Anchors let readers jump directly to the request or response section they want to inspect. Use stable anchor names that are unique across the entire document; do not reuse the same anchor for multiple operations.

## 10. Adjusting Presentation Around Snippets

Because each snippet is included individually, writers control headings and surrounding content:

```asciidoc
=== Request headers

The `If-None-Match` header allows the client to send its current validator to check
whether the resource has changed.

include::{snippets}/books-get/request-headers.adoc[]

NOTE: The client only sends this header when it has saved the ETag from a previous read.
```

You can use tables, admonitions, lists, source blocks, or cross-references. However, do not edit auto-generated snippet contents manually after each test run; adjust test descriptors, preprocessors, or templates if the generated content needs to change.

If you need to change a table's title/level or formatting, explicit includes make it possible to place headings and AsciiDoc attributes around the file. A structured snippet such as a table may carry default attributes inside the generated file itself; inspect the output before adding attributes to avoid producing invalid markup.

## 11. Selecting Snippets Instead of Including Everything

There is no need to include every snippet for every endpoint. Choose according to the questions readers need answered:

| Operation | Typically Useful Snippets |
| --- | --- |
| `GET /books/{id}` | `http-request`, `path-parameters`, `http-response`, `response-fields`. |
| `GET /books?page=...` | `http-request`, `query-parameters`, `http-response`, `response-fields`. |
| `POST /books` | `http-request`, `request-fields`, `http-response`, `response-headers`, `response-fields`. |
| `PATCH /books/{id}` | `http-request`, `path-parameters`, `request-fields`, `http-response`. |
| Hypermedia resource | `http-response`, `links`, `response-fields`. |

For example, a short API page might include only request, response, and fields; headers/parameters are added when they carry distinct semantics. Do not include a snippet solely because the file exists if it does not help readers understand the contract.

## 12. Organizing Multiple Operations into Separate Documentation Files

For large APIs, split each resource or operation into its own file:

```text
src/docs/asciidoc/
├── index.adoc
├── common/
│   └── authentication.adoc
└── operations/
    ├── books-get.adoc
    ├── books-create.adoc
    └── orders-get.adoc
```

`index.adoc` file:

```asciidoc
= Store API
:toc:
:snippets: ../../build/generated-snippets

include::common/authentication.adoc[]

== Books
include::operations/books-get.adoc[]
include::operations/books-create.adoc[]

== Orders
include::operations/orders-get.adoc[]
```

Example `operations/books-get.adoc`:

```asciidoc
=== Get book by ID
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]
```

Ensure the `{snippets}` attribute is properly configured and includes in nested files resolve relative to the file containing the include. In projects using `spring-restdocs-asciidoctor`, you can let the extension provide the attribute instead of hard-coding relative paths.

## 13. Avoiding Missing Snippets or Stale Output Includes

An include is a file-read operation; it does not check whether tests passed. If tests did not run or failed after the filter wrote snippets, stale files may remain in the generated-snippets directory.

Some useful rules:

- Clean generated output before a documentation build.
- Run tests before Asciidoctor and render only when tests succeed.
- Use separate identifiers for each scenario, such as `books-get-200` and `books-get-404`.
- Check that files exist before adding new includes.
- Do not commit manual edits inside the generated snippets directory.
- If a snippet is no longer generated, remove the include or update the test according to the new contract.

Example snippets for different statuses:

```asciidoc
== Successfully retrieve book
include::{snippets}/books-get-200/http-response.adoc[]

== Book not found
include::{snippets}/books-get-404/http-response.adoc[]
```

## 14. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `include file not found` | Wrong `{snippets}`, operation ID, or filename. | Check the output directory and compute the path from the current `.adoc` file. |
| Included a snippet type but the file is missing | Test did not declare the matching descriptor or did not generate that snippet. | Check `document(...)` and the output directory; include only files that exist. |
| Request/response appears but field table is missing | `requestFields(...)`/`responseFields(...)` not used. | Add descriptors and re-run tests. |
| Duplicate include of the same snippet | One file embedded in multiple sections or included via both macro and manual include. | Choose one primary location or clearly explain why it is repeated. |
| Included content belongs to the wrong scenario | Duplicate identifier or leftover stale snippets. | Use separate identifiers and clean output. |
| Path works in index but fails in an operation file | Relative path is computed from the file containing the macro. | Use `{snippets}` or recalculate from the operation file's location. |
| Titles/headings nested improperly | Snippet included inside a section with an unsuitable heading level. | Adjust outer headings and inspect the final HTML structure. |
| Docs published despite failing tests | Asciidoctor/publishing does not depend on test results. | Gate tasks/jobs: render and publish only after tests pass. |

## 15. Practice Checklist

- [ ] Identified the operation identifier from `document("...")`.
- [ ] Inspected generated snippets and selected the exact filenames to include.
- [ ] `{snippets}` attribute points to the exact current build directory.
- [ ] Included request/response to present the complete HTTP exchange.
- [ ] Selected header, parameter, body, field, or link snippets according to operation needs.
- [ ] Added headings, explanations, anchors, or cross-references as needed.
- [ ] No missing files or snippets from other scenarios are included.
- [ ] Separate identifiers per status/scenario to avoid overwriting.
- [ ] Clean build, tests pass before Asciidoctor runs.
- [ ] Final HTML/PDF has proper ordering, no missing includes, and no unintended duplicate content.

Embedding individual snippets provides exact control over API documentation content and layout. `{snippets}` supplies the root path; the operation identifier and filename specify the output to read. When combining request/response with appropriate headers, parameters, fields, and links tables, the documentation preserves test-generated HTTP examples while clearly explaining the contract to integrators.

## References

- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs – Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Asciidoctor – Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
