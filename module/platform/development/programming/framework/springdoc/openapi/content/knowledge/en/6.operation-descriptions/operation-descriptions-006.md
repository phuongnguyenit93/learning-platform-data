# Markdown Content, Code Blocks, and Display Limits

## 1. Why Should Operation Descriptions Be Well-Formatted?

OpenAPI does not merely list paths and data types. A good operation also explains its purpose, conditions of use, sequence of actions, business rules, possible errors, and examples so clients can integrate correctly.

Springdoc OpenAPI generates a document from controllers, DTOs, annotations, Jackson metadata, and validation. Description fields in the document can contain Markdown following OpenAPI's CommonMark rules. Swagger UI reads those fields and renders formatted content on the API reference page.

In the SPRINGDOC_OPENAPI module, describing requests, responses, schemas, security, document groups, JSON/YAML, contract testing, and documentation distribution all benefit from readable content. A short yet clear description is usually more helpful than a long block of text that repeats structure already present in schemas.

This lesson focuses on how to write Markdown in descriptions, how to place code blocks, how to provide structured examples, how to handle multiline strings in Java annotations, and how to keep content rendering well in Swagger UI.

## 2. Where Does Markdown Live in an OpenAPI Document?

OpenAPI has many text fields that can hold descriptions. Common locations include:

| Location | Purpose |
|---|---|
| info.description | Introduces the API at the document level |
| tags[].description | Explains an operation group |
| operation.description | Guides usage of an operation |
| parameter.description | Explains a path, query, header, or cookie parameter |
| requestBody.description | Explains the submitted payload |
| responses[status].description | Explains an outcome or error scenario |
| schema.description | Explains a model or property |
| header.description | Explains a response/request header |

The summary field is typically used as a short label in the operation list. Keep summary concise and scannable; place workflows, preconditions, and examples in description.

Not every text field in OpenAPI carries the same meaning. For instance, example is structured sample data; description is explanatory prose for readers. Do not use description as a substitute for schemas or examples.

## 3. Markdown in OpenAPI Follows CommonMark

The OpenAPI Specification stipulates that description fields support CommonMark. Commonly used constructs include:

- Headings with hash marks.
- Paragraphs.
- Ordered and unordered lists.
- Bold and italic formatting.
- Links.
- Inline code.
- Fenced code blocks.
- Blockquotes.

Example of an operation description:

~~~~markdown
### Usage Conditions

- Caller must have permission to read orders.
- Order ID must exist.
- Order belongs to the current tenant.

**Note:** This endpoint returns summary data only.

See [pagination rules](https://developer.example.com/pagination).
~~~~

Renderers may differ on extensions outside CommonMark. Therefore, content meant for multiple tools should favor standard CommonMark syntax instead of relying on features specific to a single renderer.

## 4. summary and description Serve Different Roles

Summary is a short label for the operation. Description provides context and guidance.

~~~java
@Operation(
    operationId = "getOrderById",
    summary = "Get order by ID",
    description = """
        Returns order details by identifier.

        Caller must have permission to read orders belonging to the current tenant.
        If the order is not found, the API returns 404.
        """
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(
        @PathVariable String orderId) {
    return orderService.getOrder(orderId);
}
~~~

Summary should help readers recognize the operation immediately in the list. Description can explain:

- When to call the operation.
- Preconditions before calling.
- Authorization or tenant rules.
- Special input data.
- Important responses.
- Links to related workflows.

Do not repeat summary verbatim at the start of description if that sentence adds no new context. Repeated content makes the documentation page longer without adding information.

## 5. Using Markdown in @Operation

The @Operation annotation has a String description attribute. You can pass a multiline string using a Java text block when the project uses Java 15 or later:

~~~java
@Operation(
    summary = "Create order",
    description = """
        Creates a new order for the current customer.

        ### Rules

        - Customer must be active.
        - Product list must not be empty.
        - Quantity on each line must be greater than 0.

        ### Outcome

        The API returns the new order ID and initial status.
        """
)
@PostMapping
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Text blocks preserve natural line breaks and avoid concatenating multiple strings with the plus operator. The content remains a static String value so it can be used in annotations.

For older Java versions, use concatenated strings or newline characters:

~~~java
@Operation(
    summary = "Create order",
    description = "Creates a new order.\n\n"
        + "### Rules\n\n"
        + "- Customer must be active.\n"
        + "- Product list must not be empty."
)
~~~

When using regular strings, double quotes, backslashes, and newlines must be escaped according to Java syntax. Text blocks reduce escaping errors, though you should still inspect the Markdown content after Springdoc generates the document.

## 6. Describing Parameters with Concise Markdown

A parameter description should explain that single parameter. Do not put the entire operation guide inside every parameter.

~~~java
@GetMapping
public Page<OrderResponse> searchOrders(
    @Parameter(
        description = """
            Search keyword by order ID or customer name.

            To search strictly by ID, send the full order ID.
            """
    )
    @RequestParam(required = false) String keyword,

    @Parameter(
        description = "Page number, starting from 0.",
        example = "0"
    )
    @RequestParam(defaultValue = "0") int page
) {
    return orderService.search(keyword, page);
}
~~~

A good parameter description answers:

- What data does the parameter represent?
- Is it required or optional?
- What is the default value?
- What is the unit of measure or format?
- Are there limits or validation rules?
- Is there a valid example?

Required flags and schema constraints should be declared with the corresponding OpenAPI constructs. Description only elaborates; it does not replace the required flag, type, format, minimum, or maximum.

## 7. Describing Request Bodies and Responses

The request body description explains the payload sent by the client. Response descriptions explain the outcome for each HTTP status.

~~~java
@PostMapping
@Operation(
    summary = "Create order",
    description = """
        Creates an order from the product list.

        Inventory checks are performed before confirming the order.
        """
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created successfully"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid payload"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Insufficient inventory to create order"
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse result = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(result);
}
~~~

Each response description should explain the meaning of the status, the conditions under which it occurs, and the body structure if needed. Do not just write "Success" or "Error" for every response.

If a response uses a shared error schema, declare the schema via @Content and @Schema. Description cannot replace the ApiError model that clients need to deserialize.

## 8. Using Headings to Structure Long Content

A description covering multiple topics should use headings so readers can scan quickly:

~~~~markdown
### Purpose

Creates a payment request for an order.

### Conditions

- Order has been confirmed.
- Total amount is greater than 0.
- Caller has payment permission.

### Workflow

1. Client submits the order ID.
2. Server checks the order status.
3. Server creates the payment request.
4. API returns the transaction ID.

### Possible Errors

- 404: Order not found.
- 409: Order has already been paid.
- 422: Payment data is invalid.
~~~~

Use a logical heading hierarchy. When the entire text sits inside an operation description, level-three headings are usually enough to group sections. Avoid skipping heading levels just to get larger font sizes.

Do not overuse headings for single sentences. Each heading should represent a meaningful section of content.

## 9. Fenced Code Blocks

Fenced code blocks display formatted examples and preserve whitespace. Use three backticks or three tildes to open and close a block.

HTTP request example:

~~~~markdown
~~~http
POST /api/orders
Content-Type: application/json
Authorization: Bearer <token>

{
  "customerId": "CUS-1001",
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
~~~
~~~~

A language identifier after the opening fence helps renderers apply syntax highlighting. Common labels include:

| Label | Content |
|---|---|
| json | JSON payload |
| yaml | OpenAPI or YAML configuration |
| http | HTTP request/response |
| bash | Shell commands |
| java | Java code |
| xml | Maven POM or XML |
| text | Plain text |
| sql | SQL query |

If a renderer does not recognize the label, the code block must still be readable as plain monospace text. Do not rely on syntax colors to convey meaning.

## 10. Code Block Examples in Java Annotations

When placing Markdown inside annotations, ensure Markdown delimiters are not mishandled by the Java string parser.

With a text block:

~~~~java
@Operation(
    summary = "Search orders",
    description = """
        Submits a search query via query parameters.

        Example:

        ~~~http
        GET /api/orders?status=NEW&page=0
        Accept: application/json
        ~~~

        Results are paginated.
        """
)
~~~~

Backticks or tildes inside a text block are ordinary characters. You do not need to escape them in Java syntax.

If using regular strings, double quotes in code examples must be escaped, and line breaks require \n or string concatenation. For longer snippets, text blocks are usually easier to maintain.

Inspect the JSON document after Springdoc generates it to ensure delimiters and line breaks remain intact.

## 11. Using Appropriate Delimiters for Nested Code Fences

If the documentation itself demonstrates how to write a fenced code block, the outer fence must use more delimiters or a different delimiter character.

For example, the outer block uses four tildes and the inner block uses three tildes:

~~~~markdown
~~~json
{
  "status": "NEW"
}
~~~
~~~~

When a description contains multiple levels of code fences, pick a longer outer delimiter to avoid closing the block prematurely. A missing closing fence can cause the rest of the description to render as code or break Markdown structure.

## 12. Markdown Code Blocks Are Not OpenAPI Examples

A code block inside description is merely formatted prose. It does not automatically become the request body example used by Swagger UI when a user clicks Try it out.

To provide structured sample data, declare example or examples inside OpenAPI content.

Response example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order found",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class),
        examples = @ExampleObject(
            name = "confirmedOrder",
            summary = "Confirmed order",
            value = """
                {
                  "id": "ORD-1001",
                  "status": "CONFIRMED"
                }
                """
        )
    )
)
~~~

ExampleObject is attached to a media type and schema. Swagger UI can use it to illustrate payloads depending on configuration and version.

Description explains meaning and workflows. Example provides structured sample data readable by tooling. Use both for their intended purposes.

## 13. Using @Schema(example) for Properties

For a simple sample value, you can place example on the schema:

~~~java
public record CreateOrderRequest(
    @Schema(
        description = "Customer ID",
        example = "CUS-1001"
    )
    @NotBlank
    String customerId,

    @Schema(
        description = "Product quantity",
        example = "2",
        minimum = "1"
    )
    @Min(1)
    int quantity
) {
}
~~~

An example on a property displays a sample value for that field. It does not describe the entire request object.

For complex payloads, use @ExampleObject at the Media Type or content level. Do not stuff multiline JSON into a description field when the real goal is providing a request example.

Examples must match the schema and actual serialization. An example with a mistyped field can cause integrators to send failing requests even though the document looks complete.

## 14. Distinguishing example and examples

OpenAPI supports both a single example and named examples.

- example fits when only one sample value is needed.
- examples fits when multiple scenarios or named samples are needed.
- ExampleObject can have summary, description, value, or externalValue per supported structure.
- Do not declare both example and examples on the same Media Type Object if the OpenAPI Specification forbids that combination.

Two-scenario example:

~~~java
@Content(
    mediaType = "application/json",
    examples = {
        @ExampleObject(
            name = "newOrder",
            summary = "New order",
            value = """
                {"status":"NEW"}
                """
        ),
        @ExampleObject(
            name = "cancelledOrder",
            summary = "Cancelled order",
            value = """
                {"status":"CANCELLED"}
                """
        )
    }
)
~~~

Examples should represent scenarios clients actually encounter. Avoid creating multiple examples that differ only in meaningless values.

## 15. When to Use Links Instead of Inlining All Content?

If a workflow is too long or requires explaining many business steps, description should summarize and link to in-depth documentation.

~~~~markdown
### Payment Workflow

1. Create a payment intent.
2. Redirect the user to the payment gateway.
3. Receive the result via webhook.
4. Verify the status before completing the order.

See the [payment integration guide](https://developer.example.com/payments)
for the full flow and retry scenarios.
~~~~

Links must be stable, have appropriate access permissions, and not point to internal docs that public clients cannot view.

Do not use links to replace essential information needed directly on the operation. Clients must still know the minimum request, primary responses, and critical errors without opening multiple other pages.

## 16. Do Not Overuse HTML in Descriptions

OpenAPI descriptions support CommonMark. Some renderers can process partial HTML, yet capabilities and sanitization policies vary.

Do not rely on complex raw HTML for layout. Avoid scripts, iframes, event handlers, or executable content. Some renderers strip or escape such content; others handle it differently.

Prefer Markdown headings, lists, links, fenced code, and blockquotes. If you need a richly formatted documentation page, use a developer portal or dedicated website instead of turning operation descriptions into embedded HTML pages.

Do not place secrets, tokens, personal information, or production data in descriptions, code blocks, or examples.

## 17. Markdown Tables and Renderer Compatibility

Tables are useful for comparing status codes, parameters, or error cases. However, GitHub Flavored Markdown tables are not core CommonMark syntax.

Some Swagger UI versions or renderers support tables; other tools may render them differently. If the document needs compatibility across many clients, you can replace tables with labeled lists.

Compatible list format example:

~~~~markdown
**200 — Success:** Returns order details.

**404 — Not Found:** Order ID does not exist.

**409 — Conflict:** Order is not in a state that permits updates.
~~~~

If using tables, test on the exact Swagger UI version and portals your organization supports. Avoid nested tables or overly wide tables that hurt readability on small screens.

## 18. Character Limits for description

The OpenAPI Specification does not impose a universal character limit across all description fields. However, that does not mean descriptions should grow arbitrarily long.

Practical limits can arise from:

- OpenAPI JSON/YAML response size.
- Reverse proxy or API gateway response-size limits.
- Browser memory and parse time.
- Swagger UI rendering performance.
- Searchability and scrolling inside long operations.
- Document storage or import systems.
- Internal API catalog governance rules.
- Reading experience on small screens and accessibility support.

Do not invent an arbitrary number like 500 or 1,000 characters and treat it as an OpenAPI standard limit. If your organization has an internal limit, explicitly document it as a governance rule and enforce it with a custom lint rule.

Keep summary short. For description, break content into headings, move payloads into examples, and move deep workflows to linked documentation.

## 19. Swagger UI Display Limits

Swagger UI can collapse or expand operations and tags. Expansion settings affect how much content is visible right when the page loads.

Example:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
~~~

The value none keeps operations collapsed initially. Other expansion options depend on the property and Swagger UI/Springdoc version in use.

Other UI settings that help readers find operations:

~~~yaml
springdoc:
  swagger-ui:
    filter: true
    display-operation-id: true
    operations-sorter: alpha
    tags-sorter: alpha
~~~

Check the property reference for your Springdoc version before applying. Property names in YAML map to the corresponding Swagger UI configuration.

The doc expansion setting only changes how the UI expands operations. It does not truncate descriptions in the OpenAPI document and does not shrink the document.

## 20. Organizing Descriptions by Priority

A readable operation description can follow this structure:

1. One or two sentences stating the purpose.
2. Required preconditions or permissions.
3. Special business rules.
4. Calling workflow if multi-step.
5. Important error scenarios.
6. Links to deeper documentation if needed.

Not every operation needs all six sections. A simple GET may only need a purpose and an access permission note.

Example:

~~~~markdown
Retrieves the processing status of an order.

### Conditions

Caller must have permission to view orders belonging to the current tenant.

### Outcome

Returns the current status, last updated timestamp, and order ID.

### Errors

- 404: Order not found.
- 403: No permission to view the order.
~~~~

A consistent structure helps users switch between operations without re-learning how to read each page.

## 21. Keeping Descriptions in Sync with Schemas and Runtime

Markdown can state one thing while the schema or runtime exhibits another. For example:

- Description says a parameter is optional, yet OpenAPI marks it required.
- Description says timestamps are in UTC, yet actual JSON has no timezone.
- Description mentions status 201, yet the controller returns 200.
- Code block uses an old field removed from the DTO.
- Example uses an enum value that is no longer valid.
- Description promises a response field that Jackson ignores.

Therefore, when editing descriptions, re-verify required, nullable, type, format, enum, validation constraints, media types, HTTP statuses, Jackson serialization, and security requirements.

Explanatory text must describe actual behavior and must never become a parallel contract diverging from the OpenAPI schema.

## 22. Inspecting Markdown Output Generated by Springdoc

After running the application, download the OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output target/openapi.json
~~~

Find the operation and inspect description in the document. You can use jq:

~~~bash
jq -r '.paths["/api/orders"].post.description' \
  target/openapi.json
~~~

If description contains newlines, code fences, or Markdown, verify JSON escaping is proper and parsed output retains line breaks accurately.

Do not inspect only source annotations. Springdoc may combine multiple annotations/customizers, and the final result in the document is what Swagger UI receives.

With multiple document groups, verify description in each group endpoint. A customizer may apply to the default document without applying as expected to a group.

## 23. Testing Descriptions with MockMvc

You can verify the emitted description in OpenAPI JSON:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OperationDescriptionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldPublishOperationDescription() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.summary"
            ).value("Create order"))
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.description"
            ).value(org.hamcrest.Matchers.containsString(
                "Conditions"
            )));
    }
}
~~~

JSONPath must match the actual path, method, and content. If description contains Markdown headings, tests can verify a distinctive substring rather than comparing the entire text.

You can also test examples:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/orders'].post.responses['201']"
        + ".content['application/json'].examples.confirmedOrder.value.id"
    ).value("ORD-1001"));
~~~

This test verifies the example is present in the document. It does not prove Swagger UI renders correctly across every browser; run dedicated UI smoke tests if the UI is a supported deliverable.

## 24. Common Issues When Rendering Markdown and Code Blocks

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Description renders as one long paragraph | Missing blank lines or newlines lost in Java string | Use a text block or explicit newlines |
| Code fence does not close | Missing delimiter or conflicting nested delimiter | Check open/close pairs and use a longer outer delimiter |
| JSON example does not appear in Try it out | JSON is inside description instead of OpenAPI examples | Use @ExampleObject or schema example |
| Quotes are missing | Incorrect Java string escaping | Check values after Springdoc emits the document |
| Markdown table does not render | Renderer does not support table extension | Use CommonMark lists or check UI version |
| Link does not work | Relative URL or wrong origin | Use a stable URL and test in a browser |
| HTML is stripped | Renderer sanitization or CSP | Use standard Markdown instead of raw HTML |
| Operation is too long and hard to read | Description includes the entire overview guide | Split with headings, examples, and links |
| UI expands too many operations | doc expansion setting | Adjust doc-expansion |
| Summary is truncated in list | Summary too long or narrow layout | Shorten summary, move details into description |
| Swagger UI misses updated content | Reading another document group or stale cache | Check endpoint and cache |
| Description does not match DTO | Manual text not updated after refactoring | Compare schema, example, and runtime |

When debugging, inspect in order: Java annotation, OpenAPI JSON, then Swagger UI. That lets you pinpoint whether the issue lies in the source string, document generation, or renderer.

## 25. Checklist Before Finalizing an Operation Description

Before committing an operation description:

- Summary is short and states the primary action.
- Description explains purpose and conditions of use.
- Markdown uses common CommonMark syntax.
- Headings follow a logical hierarchy and are not overused.
- Lists clearly present conditions or workflows.
- Fenced code blocks have matching closing delimiters.
- Code blocks include language labels where appropriate.
- Request/response samples use OpenAPI examples when tooling needs to read them.
- Examples match schemas and runtime JSON.
- Links are stable and do not point to content outside the audience.
- No secrets, tokens, or real personal data are present.
- Content does not duplicate information already in the schema.
- Description is not overly long and uses headings if covering multiple topics.
- Swagger UI displays properly against the actual document.
- CI checks the document if the operation is a critical contract.

## 26. Principles for Writing Markdown and Code Blocks in Operations

When writing content for Springdoc OpenAPI:

1. Use summary for short labels and description for guidance.
2. Use CommonMark Markdown to keep content compatible across renderers.
3. Use headings, paragraphs, and lists to organize information.
4. Use fenced code blocks for requests, responses, and illustrative commands.
5. Use @ExampleObject or schema example for structured sample data.
6. Do not confuse code blocks inside description with OpenAPI examples.
7. Use Java text blocks for multiline descriptions when the source level supports them.
8. Keep descriptions synchronized with schemas, validation, and runtime.
9. Do not assume OpenAPI has a fixed description character limit.
10. Control length based on readability, document size, and renderers.
11. Use doc-expansion to adjust how Swagger UI opens operations, not as a content limit.
12. Inspect OpenAPI JSON/YAML after Springdoc generation and test critical operations.

A good operation description helps integrators understand how to use the API without guessing from method names or DTOs. Markdown explains the workflow; schemas and examples describe machine-readable data. When both stay synchronized and content is verified in the actual document, Swagger UI becomes a clear, searchable, and trustworthy documentation interface.

## 27. References

- OpenAPI Specification — Description fields and CommonMark: https://spec.openapis.org/oas/latest.html
- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc configuration properties: https://springdoc.org/properties.html
- Swagger UI configuration: https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- Swagger Core annotations: https://github.com/swagger-api/swagger-core

