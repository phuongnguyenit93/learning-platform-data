# Customizing templates for requests and responses in Spring REST Docs

## 1. Why do you need a template set for both requests and responses?

Spring REST Docs generates snippets from HTTP tests. For an operation, the request side describes what the client sends; the response side describes what the server returns. The two sides often share similar structures while carrying different meanings:

- Request fields describe the data the client must send, including required fields, optional fields, and input rules.
- Response fields describe the data the server returns, including identifiers, statuses, timestamps, or links that clients can follow.
- Request body and response body provide raw payload examples.
- HTTP request and HTTP response show the method, URI, headers, status, and content on the wire.

Default templates produce readable tables. When API documentation needs consistent wording, custom titles, extra columns, or presentation rules matching a design system, you can override templates per snippet using Mustache.

In **SPRING_REST_DOCS**, snippets are generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Template customization only changes how data is presented; descriptors are still used to verify actual payloads against the documented contract. This lesson focuses on organizing parallel templates for requests and responses, passing metadata to each side, and checking output before Asciidoctor renders the documentation.

After this lesson, you will be able to:

- Identify which templates correspond to request and response snippets.
- Override `request-fields.snippet` and `response-fields.snippet` on the right classpath.
- Use descriptor attributes and snippet attributes for presentation data.
- Create consistent titles, columns, and field ordering while accurately conveying the semantics of each side.
- Extend the approach to request body, response body, and HTTP message snippets.
- Verify templates with documentation tests and integrate output into build/CI.

## 2. Common request/response snippets

When calling `document(...)`, Spring REST Docs can generate many snippets. Each snippet has its own role and template.

| Side | Snippet | Purpose |
| --- | --- | --- |
| Request | `http-request.adoc` | HTTP request sent: method, URI, headers, and body |
| Request | `request-body.adoc` | Raw request body |
| Request | `request-fields.adoc` | Table describing payload fields |
| Request | `request-headers.adoc` | Table describing HTTP request headers |
| Request | `request-parameters.adoc` | Table describing request parameters |
| Response | `http-response.adoc` | HTTP response received: status, headers, and body |
| Response | `response-body.adoc` | Raw response body |
| Response | `response-fields.adoc` | Table describing response payload fields |
| Response | `response-headers.adoc` | Table describing HTTP response headers |

Not every operation generates all snippets. For example, `request-fields.adoc` is only generated when the test configures `requestFields(...)`; `response-fields.adoc` requires `responseFields(...)`.

Template file names match snippet names without the output extension. For example:

- `request-fields.adoc` is generated from `request-fields.snippet`.
- `response-fields.adoc` is generated from `response-fields.snippet`.
- `http-request.adoc` is generated from `http-request.snippet`.
- `http-response.adoc` is generated from `http-response.snippet`.

Therefore, if you want the request and response tables to have distinct appearances, create two corresponding templates instead of trying to force a single template file for all snippets.

## 3. Template lookup mechanism by format

Spring REST Docs uses Mustache to render snippets. Templates are looked up on the classpath under the package:

```text
org/springframework/restdocs/templates/<format-id>/
```

With the default Asciidoctor format, the format ID is `asciidoctor`. To override both field tables, create:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    ├── request-fields.snippet
                    └── response-fields.snippet
```

These files are placed on the test classpath when running snippet-generating tests. When Spring REST Docs looks up the `request-fields` template, the template in test resources can replace the corresponding default content.

If the project uses another format, the package must use that format's exact format ID. Do not place Markdown templates in the `asciidoctor` directory or Asciidoctor templates in the `markdown` directory.

An extensible layout:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   ├── response-fields.snippet
│   ├── request-body.snippet
│   ├── response-body.snippet
│   ├── http-request.snippet
│   └── http-response.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

Only create templates for snippets that genuinely need customization. Overriding `request-fields.snippet` does not automatically change `response-fields.snippet`; the two templates are independent.

## 4. Distinguishing request and response data

`requestFields(...)` and `responseFields(...)` both accept `FieldDescriptor`, but the data being matched belongs to two different payloads.

For example, endpoint `POST /api/orders` receives:

```json
{
  "customerId": 42,
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ],
  "note": "Deliver after 5 PM"
}
```

Response:

```json
{
  "orderId": "ORD-2026-0042",
  "status": "CREATED",
  "totalAmount": 250000,
  "createdAt": "2026-11-17T09:30:00Z"
}
```

Request descriptors:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Customer ID creating the order"),
    fieldWithPath("items")
        .description("List of line items"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Quantity ordered"),
    fieldWithPath("note")
        .description("Delivery note")
        .optional()
);
```

Response descriptors:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Created order ID"),
    fieldWithPath("status")
        .description("Current order status"),
    fieldWithPath("totalAmount")
        .description("Total order amount, in VND"),
    fieldWithPath("createdAt")
        .description("Order creation timestamp in ISO-8601 format")
);
```

Requests and responses can share the same core columns `Path`, `Type`, and `Description`, while titles and extra columns should reflect their true meaning:

- Requests can add `Required` or `Constraints`.
- Responses can add `Nullable`, `Example`, or `Stability` if the team actively maintains that metadata.
- Do not add a shared column without data or clear conventions.

The path must always retain the real JSON key name so Spring REST Docs can match the payload. Labels, notes, or constraints are solely metadata for templates.

## 5. Using attributes per field and per snippet

There are two metadata levels.

### 5.1. Descriptor-level attributes

Attach per-field information using `.attributes(...)`:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("customerId")
    .description("Customer ID creating the order")
    .attributes(
        key("label").value("Customer ID"),
        key("constraints").value("Positive integer")
    );
```

For responses:

```java
fieldWithPath("orderId")
    .description("Order identifier")
    .attributes(
        key("label").value("Order ID"),
        key("example").value("ORD-2026-0042")
    );
```

Templates read these exact keys via Mustache, such as `{{label}}`, `{{constraints}}`, and `{{example}}`. If a descriptor lacks a custom attribute, the template should have a fallback or leave the cell blank.

### 5.2. Snippet-level attributes

You can pass attributes for the entire snippet via overloads of `requestFields(...)` and `responseFields(...)`:

```java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
    attributes(key("title").value("Client-submitted data")),
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of line items")
);

responseFields(
    attributes(key("title").value("Server-returned data")),
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("status").description("Order status")
);
```

`title` belongs to the entire snippet. Each template can read `{{title}}` to render different titles for the request and response tables.

You can adopt a shared metadata convention such as `title`, `label`, `constraints`, and `example`, while only including columns in each template that are truly meaningful.

## 6. Creating a template for request fields

File:

`src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet`

Example:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Request Field|JSON Path|Type|Description|Constraints

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Explanation:

- `{{#title}}...{{/title}}` displays the title only when the attribute is present.
- `{{#fields}}...{{/fields}}` iterates over the field descriptors.
- `{{label}}` is the readable name attached by the test.
- `{{^label}}...{{/label}}` is the fallback branch when no label is set.
- `{{path}}`, `{{type}}`, and `{{description}}` are standard field description data.
- `{{constraints}}` is custom metadata and does not automatically run validation.

The request template uses column headers "Request Field" and "Constraints" to emphasize what the client must provide. For optional fields, you can note optionality in constraints or add a dedicated attribute such as `presence` if the project follows a consistent convention.

Do not replace `path` with `label`. If clients need to know the exact JSON to send, the technical path must remain in the table.

## 7. Creating a template for response fields

File:

`src/test/resources/org/springframework/restdocs/templates/asciidoctor/response-fields.snippet`

Example:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Response Field|JSON Path|Type|Description|Example

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{example}}

{{/fields}}
|===
```

The response template can replace the `Constraints` column with `Example`, because clients typically need to understand the format of returned data. Examples can be attached to descriptors:

```java
fieldWithPath("orderId")
    .description("Created order ID")
    .attributes(key("label").value("Order ID"))
    .attributes(key("example").value("ORD-2026-0042"));

fieldWithPath("totalAmount")
    .description("Total order amount, in VND")
    .attributes(key("label").value("Total amount"))
    .attributes(key("example").value("250000"));
```

This is documentation metadata maintained by the team. Spring REST Docs does not automatically infer business examples from every response and does not verify whether `example` still matches production data. Choose safe, stable example values representative of the contract.

### 7.1. When you want both tables to look identical

If the design system requires requests and responses to share the same columns, use a shared column set:

```adoc
|Field Name|JSON Path|Type|Description|Notes
```

However, values in the `Notes` column should differ by side:
- Request: required status, length, range, or constraints.
- Response: nullability, status meaning, format, or example.

Having the same layout in both templates does not mean requests and responses share the same semantics.

## 8. Overriding templates for request body and response body

`request-body.adoc` and `response-body.adoc` hold the raw body captured from the operation. If you want to add titles or formatting to the body sections, you can create:

```text
request-body.snippet
response-body.snippet
```

in the same format directory:

```text
org/springframework/restdocs/templates/asciidoctor/
```

Body templates must be designed around the body data Spring REST Docs supplies to each respective snippet. Before overriding, inspect the default template for your exact dependency version to keep required variables and structures. Do not copy a template from another snippet because the data model can differ between `request-body` and `response-body`.

Similarly, to change how the overall HTTP message is presented, you can override:

```text
http-request.snippet
http-response.snippet
```

These templates have a broader scope than field tables: they render the HTTP message and may contain method/status, URI, headers, and body content. Override them only when truly necessary; if you only want to change field table titles, editing `request-fields.snippet` and `response-fields.snippet` has a narrower impact.

## 9. MockMvc example using both request and response templates

Assume the `POST /api/orders` endpoint accepts a JSON request and returns a JSON response with status `201 Created`.

```java
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
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderRequestResponseDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                    {
                      "customerId": 42,
                      "items": [
                        { "sku": "BOOK-001", "quantity": 2 }
                      ]
                    }
                    """))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(
                                attributes(key("title")
                                        .value("Client-submitted information")),
                                fieldWithPath("customerId")
                                        .description("Customer ID creating the order")
                                        .attributes(
                                                key("label").value("Customer ID"),
                                                key("constraints").value("Positive integer")
                                        ),
                                fieldWithPath("items")
                                        .description("List of line items")
                                        .attributes(key("label").value("List of line items")),
                                fieldWithPath("items[].sku")
                                        .description("Product SKU")
                                        .attributes(key("label").value("Product SKU")),
                                fieldWithPath("items[].quantity")
                                        .description("Quantity ordered")
                                        .attributes(
                                                key("label").value("Quantity"),
                                                key("constraints").value("Integer greater than 0")
                                        )
                        ),
                        responseFields(
                                attributes(key("title")
                                        .value("Server-returned information")),
                                fieldWithPath("orderId")
                                        .description("Created order ID")
                                        .attributes(
                                                key("label").value("Order ID"),
                                                key("example").value("ORD-2026-0042")
                                        ),
                                fieldWithPath("status")
                                        .description("Order status")
                                        .attributes(
                                                key("label").value("Status"),
                                                key("example").value("CREATED")
                                        ),
                                fieldWithPath("totalAmount")
                                        .description("Total order amount, in VND")
                                        .attributes(
                                                key("label").value("Total amount"),
                                                key("example").value("250000")
                                        )
                        )
                ));
    }
}
```

The imports and response body are illustrative; replace them with your project's actual endpoint, JSON fixture, and response. The goal is to demonstrate generating two snippet types from the same operation while using distinct attributes.

After the test passes, the output can include:

```text
build/generated-snippets/
└── orders-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

`request-fields.adoc` is rendered by `request-fields.snippet`; `response-fields.adoc` is rendered by `response-fields.snippet`. Each template uses the metadata from its corresponding side.

## 10. Using WebTestClient or REST Assured

Templates are loaded from the test classpath by format, not tightly coupled to MockMvc. If tests use WebTestClient or REST Assured with the same template format selected, the templates are reused seamlessly.

WebTestClient example:

```java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestBody)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-create",
        requestFields(
            attributes(key("title").value("Client-submitted information")),
            fieldWithPath("customerId").description("Customer ID")
        ),
        responseFields(
            attributes(key("title").value("Server-returned information")),
            fieldWithPath("orderId").description("Order ID")
        )
    ));
```

REST Assured example:

```java
given(this.spec)
    .filter(document("orders-create",
        requestFields(
            attributes(key("title").value("Client-submitted information")),
            fieldWithPath("customerId").description("Customer ID")
        ),
        responseFields(
            attributes(key("title").value("Server-returned information")),
            fieldWithPath("orderId").description("Order ID")
        )))
    .contentType("application/json")
    .body(requestBody)
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
```

Full test structure and how `document(...)` is attached depend on the integration module. The template customization principle stays the same: descriptor and snippet attributes are supplied in snippet calls; Mustache templates on the test classpath control rendering.

## 11. Controlling undocumented fields and custom metadata

Visual customization does not reduce payload verification responsibilities. Strict `requestFields(...)` and `responseFields(...)` still verify fields against descriptors as before:

- A field present in the payload but undocumented can fail the test.
- A required descriptor missing from the payload can fail the test.
- `.optional()` allows a documented field to be absent from the sample payload.
- `.ignored()` recognizes a field without displaying a corresponding row in the table.

Attributes like `label`, `constraints`, or `example` only provide extra data for template rendering. They do not change the path, make a field optional, or execute Bean Validation.

Example of an optional field in a request:

```java
fieldWithPath("note")
    .description("Delivery note")
    .optional()
    .attributes(
        key("label").value("Notes"),
        key("constraints").value("Max 500 characters")
    );
```

Response fields typically do not need the same requiredness rules as requests. If a response has nullable fields, clearly document nullability in the description or dedicated metadata and make sure the template reflects the convention accurately.

Do not create a `Required` or `Nullable` column and leave it blank or guess from a single sample payload. Derive metadata from the real contract and keep it synchronized with validation/schemas whenever possible.

## 12. Escaping data when rendering tables

When an Asciidoctor template builds a table, a `|` character inside a description may be interpreted as a column separator. Templates must handle cell content properly. With Asciidoctor templates, you can use the `tableCellContent` lambda for text cells:

```adoc
|{{#tableCellContent}}{{description}}{{/tableCellContent}}
```

If you add `label`, `constraints`, or `example`, consider escaping those values the same way:

```adoc
|{{#tableCellContent}}{{label}}{{/tableCellContent}}
|{{#tableCellContent}}{{constraints}}{{/tableCellContent}}
```

The exact escaping mechanism depends on the template format. For Markdown, check your project's renderer and escape pipes in tables according to your Markdown flavor. Do not assume an Asciidoctor lambda exists in another format.

Beyond pipe characters, also check:
- Content containing line breaks or inline markup.
- Characters like `<`, `>`, or brackets in descriptions.
- Whether values supplied by test fixtures contain sensitive data.
- Whether the template has a fallback when an attribute is absent.

## 13. Organizing and maintaining templates

An easy-to-manage layout:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   ├── response-fields.snippet
    │   ├── request-body.snippet
    │   └── response-body.snippet
    └── markdown/
        ├── request-fields.snippet
        └── response-fields.snippet
```

Key principles:

1. **Keep request and response separate.** This allows each table to have titles, columns, and fallbacks suited to its semantics.
2. **Share attribute conventions.** For example, `label`, `example`, and `constraints` need clear definitions so teams use them consistently.
3. **Provide fallbacks.** A descriptor without a label must still show its path; a field without an example must not break the table.
4. **Do not copy templates blindly.** When upgrading Spring REST Docs versions, default templates may change. Compare overrides against the new dependency version.
5. **Override only the necessary scope.** If you only need extra columns in field tables, do not override `http-request` or `http-response`.
6. **Review templates like source code.** Modifying a Mustache block can affect every operation using the same format on the test classpath.

If the project has multiple modules, place templates in the test resources of the specific modules that need them. Avoid putting overly specific templates in a shared library if modules follow different documentation conventions.

## 14. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Request table changed but response table stayed default | Only overrode `request-fields.snippet` | Create a separate `response-fields.snippet` |
| Template not loaded | Wrong format ID package or file name | Check `templates/asciidoctor` and snippet names |
| Label does not appear | Attribute key and Mustache variable differ | Align `key("label")` with `{{label}}` |
| Title does not appear | Snippet attribute `title` not passed or template does not render it | Pass `attributes(key("title")...)` and add a Mustache block |
| Example column is empty | Some fields lack example metadata | Use a fallback or leave blank intentionally |
| Table columns are misaligned | Cell count in header and each row do not match | Check every column and the `fields` block |
| Description containing `|` breaks the table | Cell content is unescaped | Use `tableCellContent` with Asciidoctor |
| Response mistakenly uses request constraint column | Copied template verbatim without considering semantics | Design response columns around the contract |
| Body template does not work | Copied Mustache variables from fields template | Check the default template for the exact snippet and version |
| Markdown template is not used | Placed in Asciidoctor folder or Markdown format not selected | Use the right format ID and configure matching templates |
| Tests still pass but docs show wrong labels | Attributes entered manually and became stale | Review metadata alongside API contract changes |
| CI build uses stale output | Snippets not regenerated before Asciidoctor | Ensure documentation task depends on tests |

## 15. Asciidoctor and build/CI

Source documentation can include request and response snippets side by side:

```adoc
= Orders API
:toc: left

== Create order

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]

=== Response fields
include::{snippets}/orders-create/response-fields.adoc[]
```

If the template already renders a title inside the snippet, avoid adding a duplicate title right before the include. If titles are managed in Asciidoctor, place the title before the include using valid syntax.

With Gradle and the Asciidoctor plugin configured, the documentation task must depend on snippet-generating tests:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Ensure the `spring-restdocs-asciidoctor` plugin and snippets attribute are configured according to your project's build guide.

CI workflow:

```text
HTTP tests
    |
    +--> requestFields / requestHeaders / requestParts
    |
    +--> responseFields / responseHeaders
    |
    v
Request & response descriptors + attributes
    |
    v
Mustache request/response templates
    |
    v
Generated snippets
    |
    v
Asciidoctor / Markdown builder
    |
    v
Verify and publish documentation
```

Whenever a template changes, re-run at least representative documentation tests covering both requests and responses. Check cases with and without attributes, nested fields, optional fields, and content containing special characters. Do not edit files in `build/generated-snippets` by hand; update descriptors or source templates instead.

## 16. Hands-on exercises

Using the `POST /api/orders` operation:

1. Create `request-fields.snippet` with columns `Request Field`, `Path`, `Type`, `Description`, `Constraints`.
2. Create `response-fields.snippet` with columns `Response Field`, `Path`, `Type`, `Description`, `Example`.
3. Attach `label` and `constraints` to request descriptors.
4. Attach `label` and `example` to response descriptors.
5. Pass two different `title` values to `requestFields(...)` and `responseFields(...)`.
6. Run tests and compare `request-fields.adoc` and `response-fields.adoc`.
7. Remove the `label` attribute from one field; verify that the fallback still shows the path.
8. Add a `|` character to a description and confirm that the table does not break.
9. Create Markdown templates in the matching format package and regenerate snippets in that format.
10. Include both request and response snippets in Asciidoctor, run build/CI, and review the generated output.

### Self-check questions

- Why do requests and responses have separate templates?
- Which snippet does `request-fields.snippet` generate?
- How do descriptor-level attributes differ from snippet-level attributes?
- Why must templates be placed by format ID on the test classpath?
- Can `requestFields(...)` and `responseFields(...)` share the same set of attributes?
- Why must `label` not replace the JSON path?
- When should you override `http-request.snippet` instead of only `request-fields.snippet`?
- How should fields without custom metadata be handled?
- Why should templates be verified for both requests and responses in CI?

**Key takeaway:** Requests and responses are two sides of the same contract with different purposes. Use separate `request-fields.snippet` and `response-fields.snippet` templates to convey accurate semantics; use descriptor attributes for individual fields and snippet attributes for shared titles or metadata. Templates control presentation, while tests and descriptors continue verifying the actual payloads.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates, template classpath, and extra attributes.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `responseFields`, payload, and fields snippets.
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html): default snippets and configuring snippet generation.
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): preprocessors for requests and responses before writing snippets.
