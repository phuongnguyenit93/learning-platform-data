# Creating a new snippet from the operation context in Spring REST Docs

## 1. When do you need a custom snippet?

Spring REST Docs provides built-in snippets for common aspects of an HTTP operation, such as request/response, headers, fields, parameters, links, and multipart parts. However, an API or product team sometimes needs documentation that is not available as a standard snippet, for example:

- An operation summary table showing HTTP method, URI, status, and Content-Type.
- A list of file parts with filename and media type for an upload endpoint.
- A standardized table for correlation headers, request IDs, or pagination details.
- A custom example block combining request and response details.
- Technical metadata to include in documentation for each operation.

In Spring REST Docs, every snippet is generated from an `Operation`. An operation represents a recorded API call, containing the operation name, request, response, and attributes. You can write a custom snippet to read data from the operation context, build a model, and render it with a Mustache template.

This lesson belongs to the **Snippet customization** chapter of **SPRING_REST_DOCS**. The module practices generating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating snippets for requests, responses, payloads, parameters, and headers, then compiling Asciidoctor/Markdown documentation into build/CI.

After this lesson, you will be able to:

- Understand `Operation` and the request/response data a snippet can access.
- Distinguish a custom snippet from a custom Mustache template for an existing snippet.
- Create a new snippet using `TemplatedSnippet`.
- Read method, URI, headers, status, and multipart parts from an operation.
- Build a template-safe model and name the output snippet properly.
- Register the snippet in `document(...)` and include it in Asciidoctor.
- Test, maintain, and protect sensitive data in custom snippets.

## 2. What is the operation context?

When a test is documented, Spring REST Docs creates an operation context describing the sent request and received response. The core APIs live in the `org.springframework.restdocs.operation` package.

`Operation` provides:

| API | Data |
| --- | --- |
| `getName()` | Operation name, typically the identifier passed to `document("...")` |
| `getRequest()` | The sent request |
| `getResponse()` | The received response |
| `getAttributes()` | Attributes attached to the operation |

`OperationRequest` provides details such as:

- `getMethod()`: HTTP method.
- `getUri()`: request URI.
- `getHeaders()`: HTTP request headers.
- `getContent()` or `getContentAsString()`: request body.
- `getParts()`: multipart parts if the request is multipart.
- `getCookies()`: cookies sent in the request.

`OperationResponse` provides:

- `getStatus()`: HTTP status code.
- `getHeaders()`: response headers.
- `getContent()` or `getContentAsString()`: response body.
- `getCookies()`: response cookies.

For multipart requests, each `OperationRequestPart` has `getName()`, `getSubmittedFileName()`, `getHeaders()`, `getContent()`, and `getContentAsString()`.

Overall model:

```text
HTTP test
   |
   v
DocumentFilter / document(...)
   |
   v
Operation
   +-- getName()
   +-- getAttributes()
   +-- getRequest()
   |     +-- method / URI / headers / body / parts
   |
   +-- getResponse()
         +-- status / headers / body / cookies
   |
   v
Custom Snippet
   |
   +-- read required data
   +-- build model Map
   +-- render Mustache template
   |
   v
build/generated-snippets/<operation-id>/<snippet-name>.adoc
```

The operation context holds information from the recorded HTTP call. It is the right source for a snippet meant to reflect test execution results, rather than reading fixture data through a separate path.

## 3. Distinguishing custom templates and custom snippets

These two mechanisms are related but solve different needs.

| Mechanism | When to use | Result |
| --- | --- | --- |
| Custom Mustache template for an existing snippet | Want to change the layout of `request-fields`, `response-headers`, `http-request`, etc. | Still the built-in snippet, rendered with a custom template |
| Custom snippet | Need to generate a new content/snippet type from the operation context | Produces an additional output file with a snippet name you define |
| Operation preprocessor | Want to transform request/response before snippets read them | Operation content is normalized before snippet generation |

Examples:
- Change columns in `request-fields.adoc`: override `request-fields.snippet`.
- Add an `operation-summary.adoc` file with method, URI, and status: create a custom `operation-summary` snippet.
- Mask tokens before writing request headers: use an appropriate preprocessor while also validating inputs to custom snippets.

There is no need to create a new snippet if you only want to change titles, column names, or presentation of an existing snippet.

## 4. Using `TemplatedSnippet` to create a new snippet

A convenient way to build a Mustache-based snippet is to extend `TemplatedSnippet` from the `org.springframework.restdocs.snippet` package.

This class connects the snippet name with a template, renders the template, and writes the output file. Subclasses supply the model by overriding:

```java
protected abstract Map<String, Object> createModel(Operation operation);
```

There are two commonly used constructor forms:

```java
TemplatedSnippet(String snippetName, Map<String, Object> attributes)

TemplatedSnippet(
    String snippetName,
    String templateName,
    Map<String, Object> attributes
)
```

- `snippetName` determines the name of the generated snippet file.
- `templateName` determines the template name looked up on the classpath.
- `attributes` is extra metadata added to the model during rendering.

If the snippet name and template name are identical, you can use the two-argument constructor. If they differ, use the three-argument constructor.

## 5. Example: creating an `operation-summary` snippet

Suppose you want an extra summary table for each operation:

| Property | Value |
| --- | --- |
| Operation | `orders-create` |
| Method | `POST` |
| URI | `/api/orders` |
| Status | `201` |
| Request Content-Type | `application/json` |
| Response Content-Type | `application/json` |

### 5.1. Writing the custom snippet class

```java
package com.example.docs;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.restdocs.operation.Operation;
import org.springframework.restdocs.snippet.TemplatedSnippet;

public class OperationSummarySnippet extends TemplatedSnippet {

    public OperationSummarySnippet() {
        super("operation-summary", "operation-summary", Map.of());
    }

    @Override
    protected Map<String, Object> createModel(Operation operation) {
        Map<String, Object> model = new LinkedHashMap<>();

        model.put("operationName", operation.getName());
        model.put("method", operation.getRequest().getMethod().name());
        model.put("uri", operation.getRequest().getUri().toString());
        model.put("status", operation.getResponse().getStatus().value());

        model.put(
                "requestContentType",
                operation.getRequest().getHeaders().getContentType()
        );
        model.put(
                "responseContentType",
                operation.getResponse().getHeaders().getContentType()
        );

        return model;
    }
}
```

Notable points:

- `operation.getName()` gets the operation identifier passed to `document(...)`.
- Request method and URI come from `operation.getRequest()`.
- HTTP status and response Content-Type come from `operation.getResponse()`.
- The model is a `Map<String, Object>`; keys become Mustache variables.
- `Map.of()` is used for initial attributes because this example does not need default metadata yet.

If your application targets a Java version older than Java 9, replace `Map.of()` with `Collections.emptyMap()`.

### 5.2. Creating the Mustache template

Create the file:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── operation-summary.snippet
```

Contents of `operation-summary.snippet`:

```adoc
.Operation summary
|===
|Property|Value

|Operation
|{{operationName}}

|Method
|{{method}}

|URI
|{{uri}}

|Status
|{{status}}

|Request Content-Type
|{{requestContentType}}

|Response Content-Type
|{{responseContentType}}
|===
```

The template name is `operation-summary`, matching the constructor:

```java
super("operation-summary", "operation-summary", Map.of());
```

The template must reside in the package for the active format ID. With default Asciidoctor, that is `org.springframework.restdocs.templates.asciidoctor`; if using Markdown, place the template in the `markdown` package and configure the format accordingly.

### 5.3. Registering the snippet in `document(...)`

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42,"items":[{"sku":"BOOK-001","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Customer ID"),
            fieldWithPath("items").description("List of line items"),
            fieldWithPath("items[].sku").description("Product SKU"),
            fieldWithPath("items[].quantity").description("Quantity ordered")
        )
    ));
```

`OperationSummarySnippet` is an additional snippet in the same operation. Spring REST Docs calls `document(operation)` on that snippet, builds the model from the operation, and renders the template.

After the test runs, the output can include:

```text
build/generated-snippets/
└── orders-create/
    ├── operation-summary.adoc
    └── request-fields.adoc
```

The output file name uses `snippetName`, while the template is looked up by `templateName`.

## 6. Reading multiple parts of the operation context

Custom snippets are useful when you need to combine request and response data in a single block. For example, you can build a summary table of status and key headers:

```java
@Override
protected Map<String, Object> createModel(Operation operation) {
    Map<String, Object> model = new LinkedHashMap<>();

    model.put("operationName", operation.getName());
    model.put("method", operation.getRequest().getMethod().name());
    model.put("uri", operation.getRequest().getUri().toString());
    model.put("requestContentLength", operation.getRequest().getContent().length);
    model.put("status", operation.getResponse().getStatus().value());
    model.put(
            "responseContentLength",
            operation.getResponse().getContent().length
    );

    return model;
}
```

You can also add selected headers:

```java
model.put(
    "requestAccept",
    operation.getRequest().getHeaders().getFirst("Accept")
);

model.put(
    "responseContentType",
    operation.getResponse().getHeaders().getContentType()
);
```

Choose headers that are meaningful to API consumers. Do not dump all headers into documentation if doing so risks exposing `Authorization`, `Cookie`, session identifiers, or infrastructure details.

### 6.1. Reading multipart parts

For upload operations, `OperationRequest.getParts()` returns a collection of `OperationRequestPart` instances:

```java
import org.springframework.restdocs.operation.OperationRequestPart;

List<Map<String, Object>> parts = new ArrayList<>();

for (OperationRequestPart part : operation.getRequest().getParts()) {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("name", part.getName());
    item.put("filename", part.getSubmittedFileName());
    item.put("contentType", part.getHeaders().getContentType());
    item.put("size", part.getContent().length);

    parts.add(item);
}

model.put("parts", parts);
```

The template can iterate over `parts`:

```adoc
|===
|Part|Filename|Content-Type|Bytes

{{#parts}}
|{{name}}
|{{filename}}
|{{contentType}}
|{{size}}

{{/parts}}
|===
```

This is a useful example for documenting file uploads alongside metadata. `filename` can be `null` for non-file parts; provide a fallback in the model or template so the table does not display confusing values.

Do not put raw file byte contents into the template. Usually only the part name, controlled filename, media type, and size are needed. If a filename could contain private data or unsafe paths, normalize it before building the model.

## 7. Passing metadata to a custom snippet

There are two sources of information available inside a custom snippet:

1. **Operation data**: operation name, request, response, and attributes.
2. **Attributes passed when instantiating the snippet**: metadata supplied by tests or configuration.

Example adding title and version:

```java
Map<String, Object> attributes = new HashMap<>();
attributes.put("title", "Operation summary");
attributes.put("apiVersion", "v1");

new OperationSummarySnippet(attributes);
```

Constructor:

```java
public OperationSummarySnippet(Map<String, Object> attributes) {
    super("operation-summary", "operation-summary", attributes);
}
```

`TemplatedSnippet` automatically includes passed attributes in the rendering model. The template can use:

```adoc
{{#title}}
.{{title}}
{{/title}}

.API version: {{apiVersion}}
```

There is no need to manually copy attributes into the map inside `createModel(...)`, unless you want to transform or override them intentionally. Avoid using the same key for operation data and custom metadata if the two sources could collide.

You can also pass operation-level attributes through the operation attributes of `document(...)` depending on the integration module. For basic examples, passing them directly into the custom snippet constructor is clear and easy to follow.

## 8. Detecting missing data and handling model creation errors

A custom snippet should handle cases where a request has no body, a response has no Content-Type, or an operation is not multipart. Never assume every operation contains every kind of data.

Example:

```java
@Override
protected Map<String, Object> createModel(Operation operation) {
    Map<String, Object> model = new LinkedHashMap<>();

    model.put("operationName", operation.getName());
    model.put("method", operation.getRequest().getMethod().name());
    model.put("uri", operation.getRequest().getUri().toString());
    model.put("status", operation.getResponse().getStatus().value());

    model.put(
        "requestContentType",
        operation.getRequest().getHeaders().getContentType() == null
            ? "—"
            : operation.getRequest().getHeaders().getContentType().toString()
    );

    model.put(
        "responseContentType",
        operation.getResponse().getHeaders().getContentType() == null
            ? "—"
            : operation.getResponse().getHeaders().getContentType().toString()
    );

    model.put("requestHasBody", operation.getRequest().getContent().length > 0);
    model.put("responseHasBody", operation.getResponse().getContent().length > 0);

    return model;
}
```

If data required by the snippet is missing, raise a clear error instead of generating an incorrect table or silently inserting fake values. `createModel(...)` can throw a runtime exception to halt snippet generation; if using the `ModelCreationException` API in your project's version, follow the constructor and contract of that version.

The template should include conditional branches:

```adoc
{{#requestHasBody}}
Request has a body.
{{/requestHasBody}}

{{^requestHasBody}}
Request has no body.
{{/requestHasBody}}
```

Mustache branches let the template represent with-body and without-body cases without maintaining two separate templates.

## 9. Testing custom snippets

A custom snippet is part of documentation tests. At minimum, verify:

- A successful request/response test creates the expected snippet file.
- The operation name, method, URI, and status in the snippet match the HTTP exchange.
- Requests without a body or responses without a Content-Type do not break the template.
- Multipart requests show the right part names and media types if the snippet displays parts.
- Present/absent attributes render with sensible fallbacks.
- Sensitive headers or secret contents do not appear in the output.

Example test verifying the snippet after MockMvc executes:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42}
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        new OperationSummarySnippet()
    ));
```

After the test, inspect the file:

```text
build/generated-snippets/orders-create/operation-summary.adoc
```

You can add test assertions on file contents if the project wants to lock down the snippet format. However, avoid brittle assertions on all whitespace or formatting details if templates change frequently; prioritize verifying key contract data.

## 10. Integrating with WebTestClient and REST Assured

Custom snippets are not tied exclusively to MockMvc. All three integration modules convert the recorded request/response into an `Operation` before invoking configured snippets.

### 10.1. WebTestClient

```java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestBody)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Customer ID")
        )
    ));
```

### 10.2. REST Assured

```java
given(this.spec)
    .filter(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Customer ID")
        )))
    .contentType("application/json")
    .body(requestBody)
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
```

Attaching a custom snippet works similarly; the difference lies in how each integration module captures the HTTP exchange. Ensure the custom snippet class and template are on the test classpath of the module running the tests.

## 11. Customizing snippets for Markdown

If the project uses the Markdown template format, configure the Markdown format and place the template in the corresponding package:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── markdown/
        └── operation-summary.snippet
```

Example content:

```markdown
### Operation summary

| Property | Value |
| --- | --- |
| Operation | {{operationName}} |
| Method | {{method}} |
| URI | {{uri}} |
| Status | {{status}} |
| Request Content-Type | {{requestContentType}} |
| Response Content-Type | {{responseContentType}} |
```

The snippet name remains `operation-summary`; the format ID determines the template package and output syntax. Choose one consistent format for all snippets in a documentation set to avoid accidentally mixing AsciiDoc and Markdown.

Format configuration is done via `SnippetConfigurer` inside `documentationConfiguration(...)` of the integration module. Check the API of your project's Spring REST Docs version before altering existing configuration.

## 12. Protecting data when reading the operation context

The operation context can contain sensitive content, so a custom snippet should extract only the exact data intended for publication.

Do not place the following information directly into public snippets:

- `Authorization`, `Cookie`, access tokens, or session IDs.
- Real emails, phone numbers, or personally identifiable data.
- Real uploaded files, internal storage paths, or filenames containing customer info.
- URLs containing secret query parameters.
- Response bodies containing production data.

If you need to display headers, only pull from an approved allowlist of headers. Use synthetic fixtures. Preprocessors can mask or replace certain values before writing snippets, yet custom snippets must also be designed not to inadvertently output other data from the operation.

For a custom part summary, extract only the part name, media type, and size if needed. Avoid calling `getContentAsString()` and dumping entire JSON or file contents into a general summary table.

## 13. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Custom snippet file is missing | Snippet was not added to `document(...)` | Register the instance in the snippets list |
| Template not found | Wrong template name or wrong format package | Align `templateName` and classpath path |
| Output file has unexpected name | Confused `snippetName` with `templateName` | Set both names explicitly in the constructor |
| Mustache cannot find variable | Model did not put key into map | Check `createModel(...)` and variable names |
| URI or status is empty | Read wrong object or operation differs from assumption | Use `getRequest()` and `getResponse()` |
| Snippet fails on multipart without files | Assumed every request has `getParts()` | Check for empty collections and create fallbacks |
| Table displays `null` | Optional value was not handled | Use fallbacks in the model or template |
| Custom snippet leaks tokens | Iterated and rendered all headers | Use an allowlist, synthetic tokens, and masking |
| Markdown template renders improperly | Used AsciiDoc syntax or wrong format ID | Create template in Markdown format and verify with renderer |
| Tests pass but snippet is wrong | Output contents were not verified | Add assertions for important operation data |
| Custom snippet grows too large to maintain | Mixed data collection, validation, and rendering in one class | Separate model builder, snippet, and template |

## 14. Asciidoctor and build/CI

In source documentation, include the new snippet just like standard snippets:

```adoc
= Orders API
:toc: left

== Create order

=== Operation summary
include::{snippets}/orders-create/operation-summary.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]
```

With Gradle and the Asciidoctor plugin configured:

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

CI workflow:

```text
MockMvc / WebTestClient / REST Assured test
                    |
                    v
             Operation context
                    |
                    v
              Custom Snippet
                    |
                    v
          Model + Mustache template
                    |
                    v
      build/generated-snippets/<operation>/
                    |
                    v
           Asciidoctor / Markdown
                    |
                    v
           Verify and publish
```

When modifying a custom snippet or template:
1. Run representative tests that generate the snippet.
2. Confirm the right output filename and operation ID.
3. Verify method, URI, status, headers, or part summary values.
4. Check that no sensitive data is exposed.
5. Run Asciidoctor to confirm includes work.
6. Review generated snippet diffs in the pull request.

Do not edit files in `build/generated-snippets` manually. Changes must be made in the custom snippet class, model builder, or Mustache template.

## 15. Hands-on exercises

Create a `POST /api/orders` endpoint and complete the following:

1. Write `OperationSummarySnippet` extending `TemplatedSnippet`.
2. Put operation name, HTTP method, URI, and response status into the model.
3. Create the `operation-summary.snippet` template and confirm `operation-summary.adoc` is generated.
4. Add request/response Content-Type and handle missing header cases.
5. Create another snippet displaying multipart part name, filename, Content-Type, and size.
6. Test requests without a body and non-multipart operations.
7. Pass `title` and `apiVersion` attributes when instantiating the snippet.
8. Create a Markdown template in the matching format package.
9. Run the same custom snippet with WebTestClient or REST Assured.
10. Add assertions verifying the snippet contains no Authorization tokens or file contents.

### Self-check questions

- What information about an API call does `Operation` store?
- How does `TemplatedSnippet` differ from a custom template for an existing snippet?
- What different roles do `snippetName` and `templateName` play?
- What is `createModel(Operation)` responsible for?
- How do you read the response status and request Content-Type?
- From which API can you retrieve multipart parts?
- Why should a custom snippet handle nulls and empty collections?
- When should you use a custom snippet instead of adding a column to an existing template?
- How do you verify output and prevent exposing sensitive data?

**Key takeaway:** `Operation` is the context of an API call recorded by a test. A custom snippet can read the request/response, build a model, and render with Mustache through `TemplatedSnippet`. Use a custom snippet when you need a new type of content; use a custom template when you only need to change how an existing snippet is displayed. Always restrict which operation data is exposed in public documentation.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates and attributes.
- [Spring REST Docs — `TemplatedSnippet` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/snippet/TemplatedSnippet.html): constructor, `createModel`, `document`, and snippet name.
- [Spring REST Docs — `Operation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/Operation.html): operation name, attributes, request, and response.
- [Spring REST Docs — `OperationRequest` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/OperationRequest.html): method, URI, headers, content, and multipart parts.
- [Spring REST Docs — `OperationRequestPart` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/OperationRequestPart.html): name, filename, headers, and content of each part.
