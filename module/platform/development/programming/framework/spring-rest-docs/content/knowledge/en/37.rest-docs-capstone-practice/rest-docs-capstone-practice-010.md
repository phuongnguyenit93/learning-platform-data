# Writing Markdown Documentation with Multiple Operations

## 1. Practice Objectives

A real-world API has multiple operations belonging to a single resource: list, get details, create, update, delete, and search. Each operation generates its own group of snippets from documentation tests. This lesson guides you through organizing those snippets into unified Markdown documentation with a readable structure that can be rebuilt in CI.

Spring REST Docs produces verifiable snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests verify requests/responses and descriptors; Markdown documentation brings the results together as a reference for API consumers. The focus is designing layouts for multiple operations, managing include paths, avoiding duplication, and verifying that all referenced snippets exist.

## 2. Building an Operation Inventory

Before writing documentation, create an inventory table to see which snippets each operation requires:

| Operation ID | Method and endpoint | Request snippets | Response snippets |
| --- | --- | --- | --- |
| `products-list` | `GET /api/products` | `http-request`, `query-parameters` | `http-response`, `response-fields` |
| `products-get` | `GET /api/products/{id}` | `http-request`, `path-parameters` | `http-response`, `response-fields` |
| `products-create` | `POST /api/products` | `http-request`, `request-fields` | `http-response`, `response-fields` |
| `products-update` | `PATCH /api/products/{id}` | `http-request`, `path-parameters`, `request-fields` | `http-response`, `response-fields` |
| `products-delete` | `DELETE /api/products/{id}` | `http-request`, `path-parameters` | `http-response` |

This is a sample inventory. Operation IDs must match the strings passed to `document(...)` in tests. Never add includes for snippets that an operation does not generate.

For each operation, identify the HTTP method and URI, path/query parameters, headers, request body, response status/media type, response body, and documented fields/links. The inventory serves as a contract between documentation tests and authored documentation.

## 3. Choosing a Single-Page Markdown Structure

For small or medium APIs, a single Markdown file can be organized as follows:

~~~text
product-api.md
├── Introduction
├── General conventions
├── Authentication and headers
├── Products
│   ├── List products
│   ├── Get product
│   ├── Create product
│   ├── Update product
│   └── Delete product
├── Error codes
└── Running documentation tests
~~~

Place shared information at the top of the page so it does not repeat in every operation. Within each operation, keep a consistent order: purpose; request line and parameters; request headers/body; response status/headers; response fields or links; and related errors.

For large APIs, split into multiple files by resource or bounded context. Choose boundaries according to how API consumers look up information.

## 4. Snippet Output Conventions

Spring REST Docs writes snippets by operation identifier inside the output directory, for example:

~~~text
build/generated-snippets/
├── products-list/
│   ├── http-request.adoc
│   ├── query-parameters.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
├── products-get/
│   ├── http-request.adoc
│   ├── path-parameters.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
└── products-create/
    ├── http-request.adoc
    ├── request-fields.adoc
    ├── http-response.adoc
    └── response-fields.adoc
~~~

Snippet names and file extensions depend on configured snippets and template format. Asciidoctor normally generates `.adoc` files; the Markdown format can generate `.md` files. Choose stable, clear, and unique operation IDs to prevent output overwrites.

## 5. Including Snippets in Documentation

If the project uses Asciidoctor to process includes, the syntax is:

~~~adoc
include::{snippets}/products-get/http-request.adoc[]
~~~

Example AsciiDoc page assembling multiple operations:

~~~adoc
= Product API
:toc:
:sectnums:

== Introduction

API for managing the product lifecycle in the catalog.

== List products

=== Request
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/query-parameters.adoc[]

=== Response
include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/response-fields.adoc[]

== Get product

=== Request
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]

=== Response
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Create product

=== Request
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/request-fields.adoc[]

=== Response
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]
~~~

This example uses AsciiDoc as the source so Asciidoctor resolves snippets. If the final output is pure Markdown, use a static site generator's include mechanism or a build script. Do not assume every Markdown renderer understands Asciidoctor's include syntax.

## 6. Organizing Pure Markdown

Pure Markdown has no universal snippet include syntax across all renderers. Two approaches are commonly used:

1. Use Markdown as hand-authored documentation and synchronize snippet contents after tests generate them. If copying manually, include a drift check step to prevent stale content.
2. Generate Markdown via a task/script that reads snippet outputs and merges them into placeholders by operation ID. The script must fail when a required file is missing rather than silently skipping the include.

Example layout after snippets are inserted:

~~~markdown
# Product API

## Introduction

API for managing products in the catalog.

## List products

### Request

#### HTTP request

Content synchronized from products-list/http-request.

#### Query parameters

Content synchronized from products-list/query-parameters.

### Response

Content synchronized from products-list/http-response and response-fields.
~~~

The descriptive lines above are illustrative placeholders. In published documentation, replace them with actual snippet content or links to published artifacts.

## 7. Headings, Table of Contents, and Anchors

Use consistent headings for each operation:

~~~markdown
## List products
## Get product
## Create product
## Update product
## Delete product
~~~

Table of contents example:

~~~markdown
## Table of Contents

- [List products](#list-products)
- [Get product](#get-product)
- [Create product](#create-product)
- [Update product](#update-product)
- [Delete product](#delete-product)
~~~

Rules for generating anchors from headings can differ across renderers. Test links on the publishing platform; if stability across multiple renderers is needed, use explicit anchors supported by your tooling.

## 8. Keeping Shared Sections at the Document Level

A multi-operation page usually has conventions that apply API-wide: base URL/version, authentication scheme, content types, timestamp format, currency, error format, pagination, and correlation IDs.

Example:

~~~markdown
## General conventions

- Base path: `/api`.
- JSON requests and responses use `application/json`.
- Timestamps use ISO-8601 UTC.
- Prices include a `currency` field.
- Validation errors use stable error codes.
~~~

Only document conventions confirmed in the API contract or tests. If a specific operation has an exception, state it clearly inside that operation's section.

## 9. Synchronizing Operation IDs with Documentation Tests

The operation ID is used in both tests and documentation:

~~~java
mockMvc.perform(get("/api/products/{id}", "p-42"))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                pathParameters(
                        parameterWithName("id").description("Product ID"))));
~~~

Documentation references the same identifier:

~~~adoc
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]
include::{snippets}/products-get/http-response.adoc[]
~~~

When renaming `products-get` to another name, update every include referencing the old identifier. There is no need to generate a `response-fields` snippet for a `DELETE` returning 204 because the response has no body.

## 10. Verifying Include Paths

Documentation builds should fail if a required snippet does not exist. With Asciidoctor, missing includes usually fail or report errors in the build; avoid configuring it to allow missing includes when complete documentation is required.

If using a task/script to assemble Markdown, verify each file before writing output:

~~~text
for each operation in inventory:
    for each required snippet:
        verify file exists
        append snippet content
    if file missing:
        fail documentation task
~~~

This is pseudocode. An actual script needs to read UTF-8, resolve the exact output directory, and report an error naming both the operation ID and missing snippet.

Errors to catch include wrong operation ID, wrong snippet name, wrong extension, includes pointing to a stale output directory, tests not yet run, and accidentally duplicated snippet includes.

## 11. Integrating into Gradle and CI

General workflow:

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Verify operation inventory
          |
          v
Resolve or assemble Markdown includes
          |
          v
Build documentation artifact
          |
          v
Publish or archive
~~~

If using Asciidoctor:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir layout.buildDirectory.dir('generated-snippets')
}
~~~

If using pure Markdown, create a custom task depending on `test` and declare generated snippets as inputs and the assembled Markdown file as output. This helps Gradle understand dependencies and re-run the task only when inputs change. Ensure the task does not read stale output after a failed test run.

In CI, archive the HTML or Markdown artifact with the build so reviewers can compare changes when operations or templates change. Publish only after both documentation tests and include checks pass.

## 12. Checking Consistency Across Operations

| Check | Question |
| --- | --- |
| Operation names | Do headings clearly state the action and resource? |
| HTTP method/path | Do they match the controller and tests? |
| Parameters | Are path/query parameters fully documented with accurate optionality? |
| Request body | Does it list only fields the client actually sends? |
| Response | Do status, media type, and body match tests? |
| Error cases | Do key errors have examples and schemas? |
| Snippet includes | Do all paths exist after documentation tests? |
| Shared conventions | Are shared rules duplicated or contradictory? |

Do not copy descriptors verbatim just because two operations share a field name. Required/optional status and field semantics must accurately reflect each endpoint.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| An operation section lacks response details | Forgot to include `http-response` or `response-fields` | Cross-check inventory and output folder |
| Markdown renderer displays raw include directive | Renderer does not support Asciidoctor syntax | Use Asciidoctor or a task converting snippets to Markdown |
| Include cannot find file | Wrong operation ID, snippet name, or extension | Compare against `generated-snippets` |
| Operation content is duplicated | Included the same snippet multiple times | Check layout and include list |
| Table of contents anchor does not work | Renderer generates a different slug than expected | Test anchors on the publishing platform |
| Documentation retains stale snippets | Output directory was not cleaned | Clean output and declare proper inputs/outputs |
| One operation uses inconsistent terminology | Descriptors declared separately without alignment | Reuse factories for genuinely shared semantics |
| `DELETE` includes `response-fields` but file is missing | Operation has no response body | Remove the field snippet include and document status 204 |

## 14. Capstone Exercise

Create multi-operation Product API documentation:

1. Write the introduction, base path, authentication, and content types.
2. Build an operation inventory for list, get, create, update, and delete.
3. Write documentation tests with stable identifiers for each operation.
4. Include appropriate request, parameters, request fields, response, and response fields snippets.
5. Add a table of contents and anchors to each operation.
6. Add an error responses section and shared pagination conventions.
7. Use Asciidoctor includes or a Markdown assembly task to build the final document.
8. Add a step verifying that all required snippets exist.
9. Run a clean build in CI and archive the artifact.

**Completion criteria:** every operation has a documentation section; includes match identifiers and generated files; shared sections are not duplicated; bodyless operations do not reference `response-fields`; navigation works on the target renderer; the build fails if any required snippet is missing.

## 15. Checklist Before Adding to CI

- [ ] An operation inventory exists with method, path, identifier, and required snippets.
- [ ] Identifiers in `document(...)` match include paths.
- [ ] Each operation has a consistent heading and content order.
- [ ] Base URL, authentication, and content types are written once at the document level.
- [ ] Query/path parameters and request/response fields match the contract.
- [ ] No ungenerated snippets are included.
- [ ] The Markdown renderer supports the chosen include mechanism.
- [ ] Anchors and table of contents are verified on the target renderer.
- [ ] The assembly task depends on documentation tests.
- [ ] CI cleans old output, verifies includes, and archives the final artifact.

**Remember:** Multi-operation Markdown documentation needs a clear inventory, consistent section structure, and a reliable snippet synchronization mechanism. Using stable operation IDs, including only files actually generated, and letting CI verify include paths keeps combined documentation aligned with HTTP tests.
