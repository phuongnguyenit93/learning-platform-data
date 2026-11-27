# Customizing templates for fields and parameters

## 1. Why do fields and parameters need separate templates?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests describe requests, responses, payloads, parameters, headers, and hypermedia links using descriptors. Spring REST Docs uses descriptors to generate snippets, then assembles them into Asciidoctor/Markdown and the build and CI pipeline.

Two snippet groups—fields and parameters—appear in almost every API:

- **Fields** describe JSON/XML payload structures: paths, data types, descriptions, and additional metadata.
- **Parameters** describe values in the URL: path parameters and query parameters, along with their meaning, requiredness, or format.

Default templates provide basic tables. Projects may need extra columns such as Constraints, Example, Format, Default, Required, or Since so API consumers know how to send data.

Each snippet type has its own template. Changing request-fields does not affect path-parameters or query-parameters. You must choose the exact template matching the snippet type your test generates.

## 2. Identifying fields and parameters snippets

| Snippet creation API | Asciidoctor output file | Source template |
| --- | --- | --- |
| requestFields(...) | request-fields.adoc | request-fields.snippet |
| responseFields(...) | response-fields.adoc | response-fields.snippet |
| pathParameters(...) | path-parameters.adoc | path-parameters.snippet |
| queryParameters(...) | query-parameters.adoc | query-parameters.snippet |
| formParameters(...) | form-parameters.adoc | form-parameters.snippet |

When using Markdown, the output extension is determined by TemplateFormat. The source template name still follows the snippet type and has the .snippet extension.

Override templates live on the test classpath under the package org/springframework/restdocs/templates/{format-id}. For Asciidoctor:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/asciidoctor/
    ├── request-fields.snippet
    ├── response-fields.snippet
    ├── path-parameters.snippet
    └── query-parameters.snippet
~~~

Only create the override files you actually need. Other snippets continue using the default templates of your active Spring REST Docs version.

## 3. Snippet-level and descriptor-level attributes

When customizing tables, determine which scope metadata belongs to:

| Scope | Where attached | Example |
| --- | --- | --- |
| Snippet-level | Map of attributes passed to requestFields, pathParameters, or queryParameters | Title, API version, general note |
| Descriptor-level | attributes(...) on FieldDescriptor or ParameterDescriptor | Constraint, example, unit, format, default |

For example, the request fields table has the title "Create order" at the snippet level; the quantity field has the constraint "Must be greater than 0" at the descriptor level. The template reads both scopes to render properly.

Attributes are metadata supplied by tests. Spring REST Docs does not automatically inspect Bean Validation or controller configuration to infer all constraints. If you want to document constraints, tests must pass them or use a custom helper.

## 4. Customizing the template for request fields

### 4.1. Passing metadata in tests

Use requestFields(...) with a snippet-level attributes map and attributes on each field:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(
                key("title").value("Fields for creating an order"),
                key("api-version").value("v1"),
                key("note").value("Quantity must be a positive integer")),
        fieldWithPath("productId")
                .description("Product ID")
                .attributes(
                        key("format").value("UUID"),
                        key("example").value("a4f8c960-1c2d-4e9b-8b35-0f8f3c1b5a20")),
        fieldWithPath("quantity")
                .description("Quantity ordered")
                .attributes(
                        key("constraints").value("Greater than or equal to 1"),
                        key("example").value("2")))
~~~

title, api-version, and note belong to the snippet. format, constraints, and example are attached to the corresponding field descriptors.

### 4.2. The request-fields template

Create the file src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#api-version}}
API version: {{api-version}}
{{/api-version}}
{{#note}}
NOTE: {{note}}
{{/note}}

|===
|Path|Type|Description|Constraints|Format|Example
{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
|{{format}}
|{{example}}
{{/fields}}
|===
~~~

The title, api-version, and note sections only appear when they have values. The fields section iterates over each field descriptor. Placeholders inside the section read metadata attached to each descriptor.

Start from the default template of your exact Spring REST Docs version and modify the table. This preserves standard variables already used by the template, such as optional field status or specific metadata.

## 5. Customizing the template for response fields

Request and response fields have separate templates. You can reuse column conventions, though content should suit the context.

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

responseFields(
        attributes(
                key("title").value("Returned order information"),
                key("api-version").value("v1")),
        fieldWithPath("id")
                .description("Order ID")
                .attributes(key("format").value("UUID")),
        fieldWithPath("status")
                .description("Order status")
                .attributes(key("example").value("PENDING")),
        fieldWithPath("total")
                .description("Total amount")
                .attributes(key("unit").value("VND")))
~~~

Create a separate response-fields.snippet template to format response fields. You can use the columns Path, Type, Description, Format, Example, and Unit. Make sure each placeholder has a matching attribute or is handled as an optional value.

Do not copy request-fields straight into response-fields and forget to update titles or metadata. Readers need to distinguish fields sent by the client from fields returned by the server.

## 6. Customizing the template for path parameters

Path parameters are variables inside a URI template, such as /api/orders/{orderId}. Spring REST Docs provides pathParameters(...) with an overload taking a snippet-level attributes map:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

pathParameters(
        attributes(
                key("title").value("Path parameters for the Orders API"),
                key("api-version").value("v1")),
        parameterWithName("orderId")
                .description("Order ID")
                .attributes(
                        key("format").value("UUID"),
                        key("example").value("d2f89a10-1bc8-44b0-8c48-7a2f58a1bd01")))
~~~

title and api-version apply to the entire path-parameters snippet; format and example belong to the orderId parameter.

### MockMvc example

~~~java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/{orderId}", "d2f89a10-1bc8-44b0-8c48-7a2f58a1bd01"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                pathParameters(
                        attributes(key("title").value("Order path parameters")),
                        parameterWithName("orderId")
                                .description("Order ID")
                                .attributes(key("format").value("UUID")))));
~~~

With MockMvc and Spring Framework 6.1 or earlier, to make path parameters available to REST Docs, requests must be built with RestDocumentationRequestBuilders instead of MockMvcRequestBuilders. For newer versions, check the documentation corresponding to the framework version in use.

### The path-parameters template

Create the file path-parameters.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#api-version}}
API version: {{api-version}}
{{/api-version}}
|===
|Name|Description|Format|Example
{{#parameters}}
|{{name}}
|{{description}}
|{{format}}
|{{example}}
{{/parameters}}
|===
~~~

The template model of a parameter snippet is not identical to a field snippet. Compare with the default path-parameters.snippet of the exact version to retain standard variables and parameter state representations.

## 7. Customizing the template for query parameters

Query parameters appear after the ? in the URL, such as /api/orders?status=PAID&page=0. Use queryParameters(...) to document them:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

queryParameters(
        attributes(
                key("title").value("Order filtering and pagination"),
                key("note").value("page starts at 0; max size is 100")),
        parameterWithName("status")
                .description("Filter by status")
                .attributes(
                        key("example").value("PAID"),
                        key("allowed-values").value("PENDING, PAID, CANCELLED")),
        parameterWithName("page")
                .description("Page number")
                .attributes(
                        key("default").value("0"),
                        key("constraints").value("Greater than or equal to 0")),
        parameterWithName("size")
                .description("Number of items per page")
                .attributes(
                        key("default").value("20"),
                        key("constraints").value("From 1 to 100")))
~~~

title and note describe the group of query parameters. Each parameter has its own metadata for example, allowed values, default, and limits.

### Calling queryParameters in MockMvc

~~~java
mockMvc.perform(get("/api/orders")
                .queryParam("status", "PAID")
                .queryParam("page", "0")
                .queryParam("size", "20"))
        .andExpect(status().isOk())
        .andDo(document("orders-search",
                queryParameters(
                        attributes(
                                key("title").value("Order filtering and pagination"),
                                key("note").value("page starts at 0")),
                        parameterWithName("status").description("Filter by status"),
                        parameterWithName("page").description("Page number"),
                        parameterWithName("size").description("Number of items per page"))));
~~~

### The query-parameters template

Create the file query-parameters.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#note}}
NOTE: {{note}}
{{/note}}
|===
|Name|Description|Default|Constraints|Example|Allowed values
{{#parameters}}
|{{name}}
|{{description}}
|{{default}}
|{{constraints}}
|{{example}}
|{{allowed-values}}
{{/parameters}}
|===
~~~

The query template can share some columns with path parameters, though default, allowed values, and constraints are usually more useful for filtering and pagination.

## 8. Adding metadata to parameter descriptors

ParameterDescriptor can also accept attributes. Some team-defined keys:

| Key | Meaning | Example |
| --- | --- | --- |
| format | Format or representation | UUID, ISO-8601 |
| example | Illustrative request value | PAID |
| default | Default API value | 20 |
| constraints | Value limits | 1 to 100 |
| allowed-values | Set of accepted values | PENDING, PAID, CANCELLED |
| since | Version first supported | v2 |

This is metadata for template rendering, not automatic runtime validation. Spring REST Docs checks actual parameters against descriptors according to snippet rules; default or allowed-values content must be verified against the API contract and dedicated tests if needed.

## 9. Required, optional, and ignored in parameter tables

Custom templates must preserve the parameter status information provided by descriptors:

- optional() marks a parameter that may be absent from a valid request.
- ignored() excludes a parameter from the snippet and from the corresponding strict check.
- Relaxed mode for path/query parameters allows requests to contain undocumented parameters without failing the test.

Example of an optional query parameter:

~~~java
parameterWithName("sort")
        .optional()
        .description("Result sort order")
~~~

Do not confuse optional() with a default value. A parameter can be optional while the server still applies a default; the two concepts should have separate metadata if documentation needs to show both.

If a template drops placeholders related to optional or ignored status, readers may misunderstand the contract. Start from the default template to retain those status representations, then add new columns.

## 10. Customizing for multiple formats

Template overrides are looked up by template format ID. For Asciidoctor:

~~~text
org/springframework/restdocs/templates/asciidoctor/
~~~

For Markdown:

~~~text
org/springframework/restdocs/templates/markdown/
~~~

If the project supports both formats, provide corresponding templates for each snippet:

~~~text
templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   ├── path-parameters.snippet
│   └── query-parameters.snippet
└── markdown/
    ├── request-fields.snippet
    ├── path-parameters.snippet
    └── query-parameters.snippet
~~~

Do not copy Asciidoctor templates to Markdown without changing table syntax and output formatting. The snippet file extension depends on the configured format; update includes or document embedding steps to match the generated files.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Request fields are customized but path parameters remain default | Only overrode request-fields.snippet | Create a separate path-parameters.snippet |
| Query parameters lack the new column | Query template does not read attributes yet | Add placeholders in query-parameters.snippet |
| Snippet-level metadata does not appear | Forgot to pass attributes map to snippet constructor | Use the snippet overload that accepts attributes |
| Field/parameter metadata does not display | Forgot to attach attributes or wrong key | Compare descriptor and Mustache placeholder |
| Template is not applied | Wrong format ID or file name | Check classpath and snippet name |
| Actual parameter is undocumented | Descriptor missing parameter in strict mode | Add descriptor or use relaxed mode intentionally |
| Optional parameter is interpreted as required | Template dropped status information | Keep status placeholders from the default template |
| Path parameter not recognized in MockMvc | Used a request builder that does not supply URI template parameters in an older framework | Use RestDocumentationRequestBuilders per your version guide |
| Include fails after switching to Markdown | Snippet file extension changed by format | Update includes and documentation tasks |

## 12. Hands-on exercises

1. Override request-fields.snippet to add Constraints and Example.
2. Override response-fields.snippet with a title and a Unit column for monetary values.
3. Create path-parameters.snippet with Format and Example; pass attributes at both snippet-level and parameter-level.
4. Create query-parameters.snippet with Default, Constraints, and Allowed values.
5. Write a test for an optional query parameter and ensure the template shows its status properly.
6. Switch the template format to Markdown, create Markdown templates, and verify include extensions.
7. Run documentation tests and build Asciidoctor/Markdown; inspect the diff of generated snippets.

**Completion criteria:** identify the right template by snippet type; pass attributes at snippet and descriptor levels; customize fields, path parameters, and query parameters separately; preserve optional/ignored information; align output with the documentation format.

## 13. Pre-commit checklist

- [ ] Override the right templates for request-fields, response-fields, path-parameters, and query-parameters as needed.
- [ ] Place templates in the right directory for the format ID.
- [ ] Pass snippet-level attributes via the appropriate overload.
- [ ] Attach descriptor-level attributes to the right field or parameter.
- [ ] Match Mustache placeholders to attribute keys.
- [ ] Preserve optional/ignored status and required standard information in templates.
- [ ] Document actual parameters or handle them with relaxed mode intentionally.
- [ ] Ensure Asciidoctor/Markdown templates have matching syntax and extensions.
- [ ] Have tests generate snippets before compiling documentation in CI.

**Key takeaway:** Fields and parameters have separate templates because each describes a different part of the API contract. Use snippet-level attributes for shared context, descriptor-level attributes for individual fields/parameters, and customize request-fields, response-fields, path-parameters, and query-parameters accordingly to build consistent tables while preserving Spring REST Docs verification.

## References

- Spring REST Docs - Customizing the Output: https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html
- Spring REST Docs - Path Parameters: https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html
- Spring REST Docs - Request and Response Payloads: https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html
- Spring REST Docs API - RequestDocumentation: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html
