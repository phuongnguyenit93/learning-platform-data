# Organizing Multiple Operations in a Single Markdown File

## 1. Objectives and Context

A REST API typically has multiple operations on the same resource: create, read, update, delete, search, and business actions. If every operation lives on a separate page, readers must jump around across many pages. If all of them are dumped into a single Markdown file without structure, the page becomes long, hard to navigate, and prone to including the wrong snippets.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; authors Asciidoctor/Markdown documentation and integrates it into build and CI.

After this lesson, you will be able to design a page containing multiple operations, define stable headings/anchors, organize snippets by identifier, assemble fragments into a final page, prevent collisions, and verify navigation in CI.

> "A single Markdown file" refers to a single published documentation page. Its content can still be assembled from multiple fragments and snippets for maintainability.

## 2. When Should You Group Multiple Operations into One Page?

A shared page works well when operations serve the same resource or workflow, sharing authentication, error conventions, and domain vocabulary.

Orders API example:

| Group | Operation | Purpose |
| --- | --- | --- |
| Collection | **GET /api/orders** | List/search orders. |
| Collection | **POST /api/orders** | Create an order. |
| Item | **GET /api/orders/{orderId}** | Get a single order. |
| Item | **PUT /api/orders/{orderId}** | Update an order. |
| Item | **DELETE /api/orders/{orderId}** | Delete/cancel per contract. |
| Action | **POST /api/orders/{orderId}/confirm** | Confirm an order. |

Split pages if operations follow vastly different workflows, the documentation becomes overly long, API versions target different audiences, or the docs platform does not navigate long pages well. The criterion for grouping is the relationship readers need to understand, not merely that endpoints use the same HTTP protocol.

## 3. Designing the Structure of a Markdown Page

Reference structure:

~~~markdown
# Orders API

## Overview
## Authentication and conventions
## Error responses

## Orders collection
### List orders
### Create order

## Single order
### Get order
### Update order
### Delete order

## Business operations
### Confirm order

## Schemas and enums
## Changelog
~~~

The structure has three layers:

1. **Shared information:** base path, authentication, content types, pagination, error format.
2. **Operations:** method/path, description, parameters, request, response, status, and snippets.
3. **Reference information:** schemas, enums, limits, and changelog.

Keep shared conventions at the top of the page. Within each operation, only call out exceptions to those rules.

### 3.1. Table of Contents and Anchors

For long pages, add a table of contents:

~~~markdown
## Table of contents

- [Overview](#overview)
- [Authentication](#authentication-and-conventions)
- [Error responses](#error-responses)
- [Orders collection](#orders-collection)
  - [List orders](#list-orders)
  - [Create order](#create-order)
- [Single order](#single-order)
  - [Get order](#get-order)
  - [Update order](#update-order)
- [Business operations](#business-operations)
  - [Confirm order](#confirm-order)
~~~

Automatic anchors depend on the Markdown renderer. Vietnamese slugs, punctuation, and duplicate headings may be handled differently across platforms. Verify anchors after rendering or set explicit IDs using the renderer's mechanism. The table of contents must be updated when operations are added or changed; CI can validate target anchors.

## 4. Naming Operations and Snippet Identifiers

REST Docs records an operation with an identifier:

~~~java
.andDo(document("orders-create", ...))
~~~

The identifier creates the operation folder inside generated snippets:

~~~text
build/generated-snippets/
├── orders-list/
├── orders-create/
├── orders-get/
├── orders-update/
├── orders-delete/
└── orders-confirm/
~~~

Good conventions:

- Lowercase, hyphen-separated, namespaced by resource/module.
- State the action and scenario; avoid vague names like `test1`.
- Remain stable even if test methods are renamed.
- Separate success/error identifiers when outputs differ.
- Never reuse the same identifier for two tests writing different responses to the same file.

| Scenario | Identifier |
| --- | --- |
| List succeeds | orders-list |
| Create succeeds | orders-create |
| Create with invalid body | orders-create-invalid |
| Get order | orders-get |
| Not found | orders-get-not-found |
| Update conflict | orders-update-conflict |

The identifier is the contract between tests and documentation pages. When changing an identifier, related snippet paths must be updated.

## 5. Consistent Template for an Operation

Using the same structure helps readers know where information lives:

~~~markdown
### Create order

**POST** /api/orders

Creates a new order for the current customer.

**Authentication:** Bearer token.

**Request headers:** Content-Type: application/json.

**Responses:**
- 201 Created: Order created.
- 400 Bad Request: Invalid request.
- 401 Unauthorized: Unauthenticated.
- 409 Conflict: Business conflict.

#### HTTP request
[Snippet assembled here]

#### Request fields
[Snippet assembled here]

#### HTTP response
[Snippet assembled here]

#### Response fields
[Snippet assembled here]
~~~

Omit irrelevant parts if already explained in shared conventions. For special parameters or responses, document them explicitly so clients do not have to guess.

Recommended order: HTTP method/path; purpose and permissions; parameters/headers; request body/fields/constraints; response statuses; response body/fields; error cases and side effects. Maintain consistent ordering across operations.

## 6. Assembling Multiple Snippets into a Single Markdown Page

Spring REST Docs generates Markdown snippets, but plain Markdown has no standard file include syntax. To produce one final page containing multiple operations, choose an assembly mechanism:

- A static site generator supporting includes/partials.
- An include plugin of the existing renderer.
- A build task/preprocessor reading snippet files and inserting them into the page.
- Structured sources generating one aggregated Markdown page.

Example source page with custom markers:

~~~markdown
# Orders API

## Orders collection

### List orders
<!-- snippet: orders-list/http-request.md -->
<!-- snippet: orders-list/http-response.md -->

### Create order
<!-- snippet: orders-create/http-request.md -->
<!-- snippet: orders-create/http-response.md -->
<!-- snippet: orders-create/request-fields.md -->

## Single order

### Get order
<!-- snippet: orders-get/http-request.md -->
<!-- snippet: orders-get/http-response.md -->
~~~

The comments are **illustrative markers**, not standard Markdown directives. They only work if a build preprocessor is configured to resolve paths, validate files, and insert content. If using a plugin/site generator, replace them with that tool's own include syntax.

### 6.1. Partials by Operation

A source structure might look like:

~~~text
docs/
├── pages/
│   └── orders.md
└── partials/
    └── orders/
        ├── intro.md
        ├── list.md
        ├── create.md
        ├── get.md
        └── update.md
~~~

The main page includes each partial in order. Operation partials can include snippet files in the generated snippets directory if the tool permits. This keeps the published output as a single page while allowing individual operations to be reviewed separately.

Verify whether the tool supports nested includes and paths outside the source directory. Do not assume every Markdown engine supports the same syntax.

### 6.2. Preprocessor Requirements

If writing your own assembly step, at minimum it must:

- Resolve the snippet root from a single configuration.
- Block path traversal outside the generated snippets directory.
- Fail if a required snippet does not exist.
- Preserve code fences, newlines, and UTF-8.
- Detect duplicate markers or unexpected nested includes.
- Write the final page to the build directory, without overwriting source pages.
- Run deterministically so identical sources/snippets yield identical output.

Avoid uncontrolled regex replacement if markers can appear inside code examples or user content.

## 7. Illustrative Orders API Page Layout

~~~markdown
# Orders API

## Overview

The Orders API allows authenticated users to manage orders.

**Base path:** /api/orders

**Authentication:** Bearer token.

**Media type:** application/json.

### Common conventions

- IDs are server-assigned.
- Timestamps follow ISO-8601 in the contract.
- Errors follow the shared error schema.
- Pagination starts at page 0.

## Error responses

| Status | Meaning |
| --- | --- |
| 400 | Invalid request/parameter. |
| 401 | Missing or invalid authentication. |
| 403 | Forbidden. |
| 404 | Resource not found. |
| 409 | State conflict. |

## Orders collection

### List orders

**GET** /api/orders

Returns a list filtered and paginated.

#### HTTP request
<!-- snippet: orders-list/http-request.md -->

#### HTTP response
<!-- snippet: orders-list/http-response.md -->

#### Query parameters
<!-- snippet: orders-list/query-parameters.md -->

#### Response fields
<!-- snippet: orders-list/response-fields.md -->

### Create order

**POST** /api/orders

Creates a new order.

#### HTTP request
<!-- snippet: orders-create/http-request.md -->

#### Request fields
<!-- snippet: orders-create/request-fields.md -->

#### HTTP response
<!-- snippet: orders-create/http-response.md -->

#### Response fields
<!-- snippet: orders-create/response-fields.md -->

## Single order

### Get order

**GET** /api/orders/{orderId}

#### Path parameters
<!-- snippet: orders-get/path-parameters.md -->

#### HTTP request
<!-- snippet: orders-get/http-request.md -->

#### HTTP response
<!-- snippet: orders-get/http-response.md -->

#### Response fields
<!-- snippet: orders-get/response-fields.md -->

## Changelog

| Version | Changes |
| --- | --- |
| v1 | Initial documentation version. |
~~~

This is an illustrative layout. Markers must be replaced by real snippets by the build tool or the build must fail; if markers appear verbatim in the final page, the assembly step is incomplete.

## 8. Reusing Shared Descriptions

Many operations share authentication, content type, pagination, error schemas, enums, idempotency, and versioning conventions. Place shared content at the top of the page or in a partial.

Do not copy/paste long paragraphs into every operation because when rules change, copies quickly drift. However, operation-specific exceptions must be stated right inside the operation.

| Type of Information | Location |
| --- | --- |
| Bearer token as the common mechanism | Authentication at top of page. |
| Operation requires `orders:approve` scope | Specific operation. |
| Shared error schema | Error responses. |
| Domain-specific error on confirm | Confirm operation. |
| Pagination starts at 0 | Common conventions; query descriptors if needed. |

## 9. Multiple Scenarios for the Same Operation

An endpoint may have success, validation error, not found, forbidden, or conflict cases. Separate headings and identifiers so the wrong response is never included:

~~~markdown
### Get order

**GET** /api/orders/{orderId}

#### Success — 200 OK
<!-- snippet: orders-get/http-response.md -->

#### Not Found — 404 Not Found
<!-- snippet: orders-get-not-found/http-response.md -->

#### Forbidden — 403 Forbidden
<!-- snippet: orders-get-forbidden/http-response.md -->
~~~

Use a `resource-operation-outcome` convention. You do not need to rename already stable identifiers just to follow a rigid pattern; what matters is uniqueness, clarity, and consistency.

## 10. Operation Index Table

An index table near the top of the page enables quick selection:

| Method | Path | Description | Section |
| --- | --- | --- | --- |
| GET | /api/orders | List | Orders collection |
| POST | /api/orders | Create | Orders collection |
| GET | /api/orders/{orderId} | Get details | Single order |
| PUT | /api/orders/{orderId} | Update | Single order |
| DELETE | /api/orders/{orderId} | Delete/cancel | Single order |
| POST | /api/orders/{orderId}/confirm | Confirm | Business operations |

The index can be hand-written or auto-generated. If hand-written, adding an operation requires updating both the index and headings. CI can verify every row points to an existing anchor. The index should contain method/path/purpose/section, rather than stuffing entire schemas into an overly wide table.

## 11. Ordering and Consistency

A grouping rule can be collection operations, item operations, nested resources, business actions, and then webhooks/admin operations. Within a group, typically order list, create, read, update, delete, then actions. Another order can be chosen if it fits the domain workflow more naturally; what matters is consistency and predictability.

Each operation should include the core headings: purpose, parameters, request, responses. Omit irrelevant sections or state clearly that none apply if readers might misunderstand. Do not let the first operation have response fields while a later operation lacks them simply because an include was forgotten.

## 12. Multi-Person Collaboration and Source Fragments

One final page can be assembled from fragments:

~~~text
docs/
├── pages/
│   └── orders.md
└── partials/
    └── orders/
        ├── intro.md
        ├── list.md
        ├── create.md
        ├── get.md
        └── errors.md
~~~

Generated snippets should generally live in the build directory for regeneration, not necessarily under source docs. When multiple developers collaborate, divide work by operation, prevent two tests from writing to the same identifier, use separate partials, and assemble the combined page after merging. This reduces merge conflicts compared to everyone editing one long page.

## 13. CI: Verifying the Page Contains All Operations

~~~mermaid
flowchart TD
    A["Run REST Docs HTTP tests"] --> B{"Tests pass?"}
    B -->|No| X["Fail CI"]
    B -->|Yes| C["Generate snippets per identifier"]
    C --> D["Assemble one Markdown page"]
    D --> E["Check required snippet references"]
    E --> F["Check anchors and links"]
    F --> G["Render Markdown"]
    G --> H{"All checks pass?"}
    H -->|No| X
    H -->|Yes| I["Review and publish"]
~~~

CI should verify:

- Every operation in the index has a corresponding heading/anchor.
- Identifiers in sources are generated by current tests.
- Required snippets exist; missing includes must fail.
- No identifier collisions or unintended file overwrites occur.
- Operation ordering follows conventions.
- Table of contents/index links are unbroken.
- Tables, fenced code blocks, and Vietnamese text render accurately.
- Assembled pages contain no unprocessed markers.
- Clean builds regenerate the exact page without relying on stale artifacts.

File existence alone does not prove a snippet belongs to the right operation. If an identifier is reused, a test may overwrite it while CI still sees a file. For large documentation, also verify HTTP method/path inside snippets or review generated diffs.

## 14. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Page is too long, hard to navigate | Missing heading groups/table of contents | Split collection/item/action and add an index. |
| Wrong response included | Reused identifier across multiple scenarios | Separate success/error identifiers. |
| Snippets overwritten | Multiple tests use one identifier | Assign unique identifiers. |
| New operation missing from index | Manual index not updated | Generate index or check anchors in CI. |
| Include markers left intact | Preprocessor/plugin did not run | Check tooling and fail if markers remain. |
| Broken TOC links | Slug differs by renderer or heading changed | Check after rendering, use stable IDs. |
| Authentication duplicated and drifted | Copy/pasted multiple times | Move common rules to shared section/partial. |
| Operation missing parameters/headers | Incomplete template | Use a unified descriptor checklist. |
| Success/error scenarios mixed up | No separate subheadings/identifiers | Separate outcomes. |
| Frequent merge conflicts | Multiple people editing one page | Split partials by operation. |
| Local and CI differ | Plugins/renderers or versions not pinned | Use the same configuration. |
| Stale snippets after clean build | Wrong output directory/task dependency | Manage outputs and run the proper test task. |

## 15. Practice Exercise

Create a **Customers API** Markdown page with these operations:

- **GET /api/customers**
- **POST /api/customers**
- **GET /api/customers/{customerId}**
- **PATCH /api/customers/{customerId}**
- **DELETE /api/customers/{customerId}**

Include at least one success scenario per operation; important operations should include not found or validation error scenarios.

Steps to perform:

1. Design the heading tree, table of contents, and operation index.
2. Write REST Docs HTTP tests with stable identifiers for each operation/scenario.
3. Generate snippets and verify filenames/extensions match the template format.
4. Choose partials, an include plugin, or a preprocessor.
5. Assemble a single Markdown page containing shared information and all operations.
6. Reuse authentication/error conventions, documenting exceptions per operation.
7. Verify every index entry points to an existing anchor.
8. Verify markers are resolved and no required snippets are missing.
9. Render in CI; run a clean build to confirm no dependency on stale artifacts.
10. Add a new operation and confirm index, headings, identifier, and final page all update.

**Completion criteria:** one Markdown page can navigate to all operations; each operation uses the right snippets from HTTP tests; scenarios are cleanly separated; shared content is reused; CI catches include, link, identifier, and render errors.

## References

- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [CommonMark Specification](https://commonmark.org/)
- [Markdown Guide — Extended Syntax](https://www.markdownguide.org/extended-syntax/)
- [MkDocs — Content and Navigation](https://www.mkdocs.org/user-guide/writing-your-docs/)
- [Docusaurus — Markdown Features](https://docusaurus.io/docs/markdown-features)
