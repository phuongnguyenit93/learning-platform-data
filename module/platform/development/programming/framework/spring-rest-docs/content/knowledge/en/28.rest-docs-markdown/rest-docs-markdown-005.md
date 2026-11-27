# Embedding Requests, Responses, and Field Tables

## Lesson Objectives

Spring REST Docs creates snippets from HTTP tests. A **Markdown** API page typically needs four pieces of evidence: the HTTP request, the HTTP response, the request fields table, and the response fields table. Assembling these parts properly helps readers understand how to call the endpoint, what payload to send, and what data they will receive.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into build and CI workflows.

After this lesson, you will be able to:

- Identify the snippets needed to describe an operation.
- Distinguish **http-request**, **http-response**, **request-fields**, and **response-fields**.
- Generate field tables from test-verified descriptors.
- Place the four snippet types into the right sections of a Markdown page.
- Choose an include plugin or build-time assembly suited to your renderer.
- Verify code fences, tables, JSON, content types, and sensitive data after assembly.
- Connect snippet-generating tests to the Markdown rendering step in CI.

## 1. Four Components of an API Operation Page

Suppose you have endpoints for getting and creating orders. A complete documentation page can present:

| Component | Typical REST Docs Snippet | Content |
| --- | --- | --- |
| HTTP request | **http-request** | Recorded method, URI, request headers, and body |
| HTTP response | **http-response** | Status, response headers, and body |
| Request fields table | **request-fields** | Field name, type, description, and optional/constraints status if supported by template |
| Response fields table | **response-fields** | Response field name, type, and meaning per descriptor |

REST Docs generates AsciiDoc files by default. When configured with the Markdown template format or custom templates, file extensions and structures may differ. The filenames below illustrate four Markdown fragments:

~~~text
build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-fields.md
    └── response-fields.md
~~~

Do not change `.adoc` to `.md` by renaming files. Content must be rendered with the proper Markdown template or converted through a controlled step.

## 2. Understanding the Role of Each Snippet

### 2.1. HTTP request: How the Client Calls the Endpoint

The **http-request** snippet answers:

- Which HTTP method is used?
- Which URI is called, and how are path/query parameters passed?
- Which headers such as **Content-Type** or **Accept** are required?
- What is the structure and value of the request body?

Illustrative content shape:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "customerId": 42,
  "description": "Keyboard"
}
~~~

This is an illustrative example; real snippets must come from operation tests. If tests send tokens, cookies, or personal data, use fake fixtures or preprocessing before writing snippets.

### 2.2. HTTP response: What the Server Returns

The **http-response** snippet shows the status, headers, and response body:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/731

{
  "id": 731,
  "status": "CREATED"
}
~~~

Readers see that the request creates a new resource, the status is **201 Created**, and the resource URI is in **Location**. If the API has business errors, dedicate separate operations or tests to document error responses.

### 2.3. request-fields: Table Describing the Client Request Body

The **request-fields** snippet is generated from **requestFields(...)** and **fieldWithPath(...)**. The table typically describes field paths, data types, and meanings.

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | ID of the customer owning the order |
| description | String | Short description of the order |

Exact columns depend on the snippet template. Descriptors are the source for this table; do not write a separate manual table whose descriptions can drift out of sync with tests.

### 2.4. response-fields: Table Describing the Server Response Body

The **response-fields** snippet is generated from **responseFields(...)**:

| Path | Type | Description |
| --- | --- | --- |
| id | Number | Identifier of the created order |
| status | String | Current status of the order |

When responses have nested objects or arrays, use REST Docs field path syntax, such as **customer.name** or **items[].sku**. Verify paths against the real payload and describe the full structure clients need to consume.

## 3. Generating Field Tables from Test Descriptors

Do not hand-write request/response field tables and treat them as test evidence. Declare descriptors inside **document(...)** so REST Docs validates them against the operation's payload.

Example MockMvc test:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 42,
              "description": "Keyboard"
            }
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        requestFields(
            fieldWithPath("customerId")
                .description("ID of the customer owning the order"),
            fieldWithPath("description")
                .description("Short description of the order")
        ),
        responseFields(
            fieldWithPath("id")
                .description("Identifier of the created order"),
            fieldWithPath("status")
                .description("Current status of the order")
        )
    ));
~~~

Common static imports:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

The test snippet illustrates descriptor placement. In a real running test, the controller must return a JSON response matching both **id** and **status**, and assertions should verify status/body per the contract. When using strict field descriptors, REST Docs helps detect undocumented payload fields or descriptors that do not match the payload.

### 3.1. Optional Fields and Nested Fields

If a request has optional fields, describe them explicitly:

~~~java
requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    fieldWithPath("description")
        .description("Order description"),
    fieldWithPath("note")
        .optional()
        .description("Additional note, may be omitted")
)
~~~

For nested JSON:

~~~java
requestFields(
    fieldWithPath("customer.id")
        .description("Customer ID"),
    fieldWithPath("customer.name")
        .description("Customer name"),
    fieldWithPath("items[].sku")
        .description("Product SKU in each order line"),
    fieldWithPath("items[].quantity")
        .description("Quantity of each product")
)
~~~

Do not use **optional()** to legitimize a field that is always required in the API. Descriptors must reflect real schema and validation rules.

### 3.2. Responses with Nested Objects or Arrays

Example response:

~~~json
{
  "id": 731,
  "customer": {
    "id": 42,
    "name": "Lan"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 1
    }
  ]
}
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.name").description("Customer name"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Quantity")
)
~~~

If you need to document parent objects like **customer** or **items**, consider **subsectionWithPath(...)** depending on your REST Docs version's capabilities. Avoid documenting the same JSON region at both parent and child levels in ways that cause overlapping descriptors.

## 4. Placing the Four Snippets into a Markdown Page

Plain Markdown has no universal file include syntax. Thus, two implementation patterns are common:

1. Use the include directive of the static site generator/plugin your project actually uses.
2. Create a **build-time assembly** task to assemble fragments into a complete Markdown file before rendering.

If snippets are still AsciiDoc, you can continue using Asciidoctor to render docs, or convert snippets to Markdown via a dedicated process. Do not place Asciidoctor's **include::...[]** in Markdown expecting every renderer to understand it.

### 4.1. Recommended Directory Structure

~~~text
src/docs/markdown/
└── orders-intro.md

build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-fields.md
    └── response-fields.md

build/docs-markdown/
└── orders.md
~~~

The **orders-intro.md** file contains team-authored explanations:

~~~markdown
# Orders API

API for creating and looking up orders.

## Create Order

The client sends customer details and an order description. The server returns the order ID and initial status.
~~~

The assembly task combines static content with the four snippets in the exact order. Files in **build/docs-markdown** are outputs for rendering or publishing; do not manually edit snippets in **build/generated-snippets**.

### 4.2. Shape of the Markdown Page After Assembly

~~~~markdown
# Orders API

API for creating and looking up orders.

## Create Order

The client sends customer details and an order description.

### HTTP request

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":42,"description":"Keyboard"}
~~~

### Request fields

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Customer ID |
| description | String | Order description |

### HTTP response

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":731,"status":"CREATED"}
~~~

### Response fields

| Path | Type | Description |
| --- | --- | --- |
| id | Number | Order ID |
| status | String | Status |
~~~~

This illustrates the page shape, not actual REST Docs snippets generated in a repository. When implemented, all four sections must be read from real test outputs.

## 5. Gradle Task to Assemble the Four Snippets

The example task below assumes tests generate Markdown snippets with the exact filenames listed, the intro lives at **src/docs/markdown/orders-intro.md**, and the project uses Gradle Groovy DSL:

~~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')
def sourceDir = layout.projectDirectory.dir('src/docs/markdown')
def outputDir = layout.buildDirectory.dir('docs-markdown')

tasks.register('assembleOrdersMarkdown') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    inputs.file(sourceDir.file('orders-intro.md'))
    outputs.dir outputDir

    doLast {
        def intro = sourceDir.file('orders-intro.md').asFile
        def operationDir = new File(
            snippetsDir.get().asFile,
            'orders-create'
        )
        def names = [
            'http-request.md',
            'request-fields.md',
            'http-response.md',
            'response-fields.md'
        ]
        def headings = [
            '### HTTP request',
            '### Request fields',
            '### HTTP response',
            '### Response fields'
        ]
        def snippets = names.collect { name ->
            new File(operationDir, name)
        }

        def missing = ([intro] + snippets).findAll { !it.isFile() }
        if (!missing.isEmpty()) {
            throw new GradleException(
                'Required documentation inputs not found: ' +
                missing.collect { it.path }.join(', ')
            )
        }

        def result = new StringBuilder()
        result.append(intro.getText('UTF-8').trim()).append('\n\n')
        snippets.eachWithIndex { file, index ->
            result.append(headings[index])
                .append('\n\n')
                .append(file.getText('UTF-8').trim())
                .append('\n\n')
        }

        def destination = outputDir.get().file('orders.md').asFile
        destination.parentFile.mkdirs()
        destination.setText(result.toString(), 'UTF-8')
    }
}
~~~~

The sample task assembles one operation for readability. With many operations, manage required snippets in a manifest or data structure containing headings, identifiers, and file lists; avoid duplicating nearly identical tasks. Verify Gradle syntax against your project's wrapper before integrating.

### 5.1. If Using a Markdown Include Plugin

With a specific include plugin, replace the assembly task with the directive supported by that plugin. The example illustrates desired placement; comments are not directives that work by default:

~~~markdown
### HTTP request

<!-- plugin-specific include for orders-create/http-request.md -->

### Request fields

<!-- plugin-specific include for orders-create/request-fields.md -->

### HTTP response

<!-- plugin-specific include for orders-create/http-response.md -->

### Response fields

<!-- plugin-specific include for orders-create/response-fields.md -->
~~~

Consult your renderer/plugin documentation for exact syntax, path resolution, and security rules. Inspect generated HTML to confirm fragments were actually included.

## 6. Configuring REST Docs to Generate Snippets

### 6.1. Markdown Template Format

If the Spring REST Docs version in your project supports the Markdown template format, configure this format for snippets:

~~~java
import static org.springframework.restdocs.templates.TemplateFormats.markdown;

mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .snippets()
        .withTemplateFormat(markdown()))
    .build();
~~~

This example uses an API that may vary across versions. Check the Javadoc of your installed dependency before using **TemplateFormats.markdown()** and **withTemplateFormat(...)**. If your version does not support it, you can use custom snippet templates or convert AsciiDoc to Markdown through a verified step.

The template format determines how each snippet is rendered. It does not automatically assemble the four fragments into **orders.md**.

### 6.2. Standard Snippets and Custom Snippets

When customizing templates:

- Preserve field names and descriptor meanings.
- Do not omit undocumented fields to make documentation appear artificially complete.
- Keep request/response sections containing all necessary HTTP information.
- Ensure Markdown tables escape **|** characters in content if they appear.
- Check code fences when bodies contain nested Markdown or code samples.

If templates change, tests must still validate operation data; templates only control presentation.

## 7. Verifying Requests, Responses, and Field Tables

Before publishing, check each operation page:

| Check | What to Confirm |
| --- | --- |
| Request snippet | Method, URI, headers, and body match test |
| Request fields | Every required field has a descriptor |
| Response snippet | Status, headers, and body match contract |
| Response fields | Field names, types, and descriptions match payload |
| Required/optional | Optional fields marked accurately; required fields not missed |
| Nested fields | Object/array paths match actual JSON |
| Content type | JSON/XML/form body described with right type |
| Sensitive data | No real tokens, session IDs, or PII |

A common mistake is having a complete request-fields table while the request body in the snippet came from an old test. Ensure all snippets for an operation come from the same execution and identifier, never mixing files from two tests or two API versions.

### 7.1. Checking for Missing or Extra Descriptors

With REST Docs field descriptors, strict validation detects:

- Actual payload fields that are undocumented.
- Descriptors declaring fields that do not exist.
- Optional fields mislabeled as required or vice versa.
- JSON structure changes without updated field tables.

If the API allows dynamic fields or extra metadata, consider **subsectionWithPath(...)** or relaxed fields appropriately; only use relaxed descriptors intentionally and clearly explain the portion of the payload not documented in detail.

## 8. Formatting Errors When Embedding Snippets

**Code fences:** Never wrap a snippet that already contains fenced code blocks inside another fence of the same length. If an assembly page must illustrate Markdown containing inner code fences, use an outer fence longer than the inner fences.

**Tables:** Leave blank lines before and after tables. If a description contains **|**, escape it according to Markdown rules or the appropriate template.

**JSON:** Keep JSON snippets intact; do not manually pretty-print or edit response bodies after tests generate them, unless a managed and tested transform step is used.

**Headings:** The four fragments usually do not need their own headings if templates only output table/code content. Place headings on the main page to avoid duplicate TOC entries or wrong heading levels.

**Paths:** Links/images inside fragments may resolve relative to the fragment location or the final page depending on the renderer. Inspect the rendered page rather than just checking source.

**UTF-8:** Maintain UTF-8 encoding across tests, snippets, assembly, and renderer so Vietnamese content and Unicode JSON display correctly.

## 9. Integrating test → assembly → render in CI

The build flow should follow this order:

~~~mermaid
flowchart TD
    A["Run HTTP tests"] --> B["REST Docs generates four snippets"]
    B --> C["Validate snippets exist"]
    C --> D["Assemble Markdown page"]
    D --> E["Render Markdown"]
    E --> F["Check links, tables and code fences"]
    F --> G["Publish documentation artifact"]
~~~

The assembly task must depend on tests. The renderer must depend on assembly. The publish step runs only when all preceding checks pass.

With Gradle:

~~~groovy
tasks.named('assembleOrdersMarkdown') {
    dependsOn tasks.named('test')
}

tasks.named('renderMarkdownDocs') {
    dependsOn tasks.named('assembleOrdersMarkdown')
}
~~~

The name **renderMarkdownDocs** is an example; replace it with the actual task of your static site generator or documentation tool. Do not declare circular dependencies between tests, assembly, and renderer.

In CI, add checks:

1. All required **http-request**, **http-response**, **request-fields**, and **response-fields** files exist.
2. Final Markdown pages have all four sections for each operation.
3. No unprocessed include directives remain.
4. Internal links and assets resolve.
5. No sensitive values appear in request/response snippets.
6. Final artifacts are built from outputs of the same test run.

## 10. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| HTTP request exists but request-fields table is missing | **requestFields(...)** not declared or assembly skipped snippet | Add descriptors and include fragment in manifest |
| Field table does not match payload | Stale descriptor or wrong operation identifier used | Check test, JSON, and document ID |
| Response body is right but response-fields is missing | **responseFields(...)** not declared | Add descriptors for response fields |
| Markdown displays raw include directive | Using Asciidoctor syntax in a plain Markdown renderer | Use platform-appropriate include plugin or assembly |
| `.adoc` snippet embedded as Markdown | Markdown template/conversion not configured | Perform controlled conversion or render with Asciidoctor |
| Table columns broken | Description has unescaped **|** character | Fix template or escape character |
| JSON renders as hard-to-read text | Template or snippet does not format body | Choose appropriate template; keep output synced with tests |
| Snippets from two tests mixed together | Shared identifier or stale output | Use unique IDs and manage output per operation |
| Page has duplicate fields | Combined manual table and generated snippet | Choose only one source for field tables |
| CI cannot find snippet | Assembly ran before tests or wrong path | Configure task dependencies and validate paths |
| Page leaks token/session | HTTP snippet recorded real test values | Use fake fixtures or preprocessing; review output |

## 11. Practice Exercise

Document the create order operation:

~~~text
POST /api/orders
~~~

Request:

~~~json
{
  "customerId": 42,
  "description": "Keyboard"
}
~~~

Response:

~~~json
{
  "id": 731,
  "status": "CREATED"
}
~~~

Requirements:

1. Write a MockMvc test sending the request and asserting status/response body.
2. Declare **requestFields(...)** for **customerId**, **description**.
3. Declare **responseFields(...)** for **id**, **status**.
4. Generate **http-request**, **http-response**, **request-fields**, and **response-fields** under the same document identifier.
5. Configure Markdown templates or convert snippets via an explicit workflow.
6. Assemble the four snippets into **orders.md** in the order: request, request fields, response, response fields.
7. Fail assembly if any required fragment is missing.
8. Render the page and verify tables, JSON code fences, headings, UTF-8, and links.
9. Connect test → assembly → render in CI.

**Completion criteria:** four fragments are generated from the same operation test; field tables match payloads; request and response reflect the true HTTP exchange; the final Markdown page renders error-free and is regenerated in CI.

## Key Takeaways

An operation page typically needs four pieces of evidence: **http-request**, **request-fields**, **http-response**, and **response-fields**. HTTP snippets show the actual exchange; field snippets describe schemas through REST Docs-verified descriptors. Declare **requestFields(...)** and **responseFields(...)** in the same operation test, then place fragments into corresponding sections of the Markdown page via an include plugin or build-time assembly. Verify complete snippets, field paths, code fences, tables, and sensitive data before rendering/publishing. Connect test → assembly → renderer in CI so documentation always stays synchronized with tested contracts.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Payload Documentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html), [Spring REST Docs Template Formats API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/templates/TemplateFormats.html), [Asciidoctor include directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/), and [CommonMark Specification](https://commonmark.org/).
