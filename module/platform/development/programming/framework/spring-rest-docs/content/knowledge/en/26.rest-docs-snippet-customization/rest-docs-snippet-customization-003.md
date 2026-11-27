# Formatting field names and table titles in Spring REST Docs

## 1. Why customize field names and titles?

Spring REST Docs generates snippets from HTTP tests. For JSON payloads, `requestFields(...)` or `responseFields(...)` produces a table containing the path, data type, and description. The default table has a clear structure, but sometimes it does not match the presentation style of product documentation:

- JSON names like `customerId` and `shippingAddress.postalCode` fit code well but are harder for business users to read.
- Some teams want to add display labels, rules, or constraints for each field.
- Default titles such as "Request fields" do not clearly state whether the payload is for creating an order, updating a profile, or filtering a report.
- Request and response tables need consistent column naming, wording, and information order.

Spring REST Docs lets you customize presentation via **Mustache snippet templates** and **attributes**. You can keep `FieldDescriptor` as the test-verified description source, then add readable labels, extra columns, and operation-specific titles.

This lesson belongs to the **Snippet customization** chapter of **SPRING_REST_DOCS** — a module for generating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then compiling snippets in Asciidoctor/Markdown and integrating them into build/CI.

After this lesson, you will be able to:

- Understand which parts of a snippet table are controlled by descriptors and which are determined by templates.
- Add display names for paths while keeping the actual JSON paths intact.
- Rename columns, add a constraints column, and reorder table contents.
- Set custom titles per snippet or operation.
- Override templates for Asciidoctor and Markdown on the right classpath.
- Maintain consistent customizations without losing Spring REST Docs payload verification.

## 2. Separating descriptive data from presentation

There are three components to distinguish:

| Component | Role | Example |
| --- | --- | --- |
| `FieldDescriptor` | Defines path, type, description, optional, ignored, and field metadata | `fieldWithPath("customerId")` |
| Snippet attributes | Adds metadata for the entire snippet | Title `Order creation fields` |
| Mustache template | Defines how data is rendered into a table | Rename `Path` column to `Field Name`, add `Constraints` |

Example descriptor:

```java
fieldWithPath("customerId")
    .type(JsonFieldType.NUMBER)
    .description("Customer ID");
```

The path `customerId` is the JSON key name used to match against the actual request. If you only want the table to display a friendly label such as "Customer ID", you should not change the path to a display string. Keep the technical path so REST Docs continues verifying the real payload, and add a separate attribute for the display label.

Recommended model:

```text
Actual JSON request
       |
       v
FieldDescriptor
  path = customerId
  type = NUMBER
  description = ...
  label = "Customer ID"
       |
       v
Mustache template
       |
       v
Documentation table:
Field Name | Path | Type | Description
Customer ID | customerId | NUMBER | ...
```

This separation lets you change the language or presentation style without altering the HTTP contract.

## 3. Adding display names for each field

### 3.1. Attaching attributes to `FieldDescriptor`

Spring REST Docs lets you use `.attributes(...)` to attach custom data to a descriptor. For example, using `label` as a display name:

```java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("customerId")
    .description("Customer ID creating the order")
    .attributes(key("label").value("Customer ID"));
```

For nested objects:

```java
fieldWithPath("shippingAddress.postalCode")
    .description("Postal code of the shipping address")
    .attributes(key("label").value("Postal code"));
```

`path` still remains `shippingAddress.postalCode`; `label` only provides content for the template.

You can define descriptors in an array for reuse:

```java
private static final FieldDescriptor[] ORDER_FIELDS = {
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("Customer ID creating the order")
        .attributes(key("label").value("Customer ID")),

    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("List of line items")
        .attributes(key("label").value("Product list")),

    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Product identifier")
        .attributes(key("label").value("Product SKU")),

    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Quantity ordered")
        .attributes(key("label").value("Quantity"))
};
```

Import `FieldDescriptor`, `JsonFieldType`, and the static methods `fieldWithPath` and `key` as appropriate for your project. REST Docs still uses the descriptors to validate the sample request; the `label` attribute is only used when requested by the template.

### 3.2. Should you replace path with the display label?

Typically you should show both the path and the label if readers need to copy JSON or cross-reference the request directly:

| Display Name | JSON Path | Description |
| --- | --- | --- |
| Customer ID | `customerId` | Customer ID creating the order |
| Product SKU | `items[].sku` | Product identifier |
| Quantity | `items[].quantity` | Quantity ordered |

If the documentation targets technical API consumers, the JSON path should always be easy to find. If it targets business users, you can prioritize the label while keeping the path in a separate column or detail section.

Do not use the label attribute as a way to "rename" fields in the request. The key sent over HTTP is still the real JSON path.

## 4. Renaming columns and adding columns in Mustache templates

Spring REST Docs uses Mustache templates to generate snippets. The default template for the Asciidoctor format is loaded from the classpath under the package:

```text
org/springframework/restdocs/templates/asciidoctor/
```

To override the request fields table, create the file:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
```

Custom template defining the table layout:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Field Name|JSON Path|Type|Description|Constraints

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Meaning:

- `{{#title}}...{{/title}}`: displays the title if the snippet has a `title` attribute.
- `{{#fields}}...{{/fields}}`: iterates over the list of field descriptors.
- `{{label}}`: custom attribute on the descriptor.
- `{{^label}}...{{/label}}`: uses `path` as a fallback value if the descriptor has no `label`.
- `{{constraints}}`: custom attribute added at the field level.

In Mustache, variable names must match the attribute key. Therefore, if Java sets `key("label")`, the template reads `{{label}}`; if it uses `key("constraints")`, the template reads `{{constraints}}`.

### 4.1. Adding a Constraints column

Attach metadata to each descriptor:

```java
fieldWithPath("customerId")
    .description("Customer ID creating the order")
    .attributes(
        key("label").value("Customer ID"),
        key("constraints").value("Positive integer")
    );

fieldWithPath("email")
    .description("Email address for confirmation")
    .attributes(
        key("label").value("Email"),
        key("constraints").value("Valid email format")
    );
```

The template can use `constraints` to render the column:

```adoc
|Field Name|JSON Path|Type|Description|Constraints
{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
{{/fields}}
```

The extra column makes the table more informative. However, `constraints` values are supplied manually by the author; they do not automatically run Bean Validation and do not replace validation tests.

### 4.2. A more minimal template

If you do not need a separate display name and only want to rename columns:

```adoc
|===
|JSON Field|Data Type|Meaning

{{#fields}}
|{{path}}
|{{type}}
|{{description}}

{{/fields}}
|===
```

Custom templates can omit or reorder columns, though you should keep path, type, and description if API clients need them.

## 5. Setting custom titles for individual snippet tables

There are two common title levels: titles generated inside the snippet via attributes, and titles placed in Asciidoctor at the include site.

### 5.1. Snippet-level `title` attribute

Spring REST Docs lets you pass attributes for the entire snippet using the `requestFields(attributes(...), descriptors...)` overload:

```java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

.andDo(document("orders-create",
    requestFields(
        attributes(key("title").value("Order creation fields")),
        fieldWithPath("customerId")
            .description("Customer ID creating the order"),
        fieldWithPath("items")
            .description("List of line items")
    )
));
```

The `request-fields.snippet` template can read `{{title}}`:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description

{{#fields}}
|{{path}}
|{{type}}
|{{description}}

{{/fields}}
|===
```

The `title` attribute is not a mandatory field on `FieldDescriptor`; it is metadata applied to the snippet generated by calling `requestFields(...)`.

### 5.2. Titles placed in Asciidoctor before the include

If you prefer to keep the template unchanged, you can place the title in the `.adoc` document:

```adoc
=== Create order

.Request fields when creating an order
include::{snippets}/orders-create/request-fields.adoc[]
```

A line starting with a period sets the block title for the following table in Asciidoctor syntax. This approach works well when titles are managed centrally by documentation authors.

### 5.3. Changing titles when using the `operation` macro

If you use the `operation::...[]` macro from the Spring REST Docs Asciidoctor extension, you can customize section titles using document attributes named:

```adoc
:operation-request-fields-title: Input fields
:operation-response-fields-title: Response fields

operation::orders-create[]
```

Attribute names follow the pattern `operation-{snippet}-title`. The example above replaces the section titles corresponding to `request-fields` and `response-fields` when the macro includes snippets.

This is the title mechanism of the `operation` macro. If you include snippets manually with `include::...[]`, place the title directly before the include or let a custom template render the title.

## 6. Complete example: custom-labeled request fields table

The example below uses MockMvc and Spring REST Docs. Assume the `POST /api/orders` endpoint returns `201 Created` when the request is valid.

### 6.1. Test declaring attributes

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

@Test
void documentCreateOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
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
                attributes(key("title").value("Order creation information")),
                fieldWithPath("customerId")
                    .description("Customer ID creating the order")
                    .attributes(
                        key("label").value("Customer ID"),
                        key("constraints").value("Positive integer")
                    ),
                fieldWithPath("items")
                    .description("List of line items")
                    .attributes(key("label").value("Product list")),
                fieldWithPath("items[].sku")
                    .description("Product identifier")
                    .attributes(key("label").value("Product SKU")),
                fieldWithPath("items[].quantity")
                    .description("Quantity ordered")
                    .attributes(
                        key("label").value("Quantity"),
                        key("constraints").value("Integer greater than 0")
                    )
            )
        ));
}
```

The imports and endpoint here are illustrative; add the static imports for `post`, `content`, `contentType`, `status`, and `MediaType` according to your actual test class. The sample payload must match the descriptors for the snippet to be generated successfully.

### 6.2. Expected table output

With a five-column template, the table can render as:

| Field Name | JSON Path | Type | Description | Constraints |
| --- | --- | --- | --- | --- |
| Customer ID | `customerId` | NUMBER | Customer ID creating the order | Positive integer |
| Product list | `items` | ARRAY | List of line items | |
| Product SKU | `items[].sku` | STRING | Product identifier | |
| Quantity | `items[].quantity` | NUMBER | Quantity ordered | Integer greater than 0 |

This is the expected shape of the snippet after the template is applied. The exact content depends on the actual JSON and descriptors passed by the test.

## 7. Using custom templates for Markdown

Spring REST Docs supports multiple template formats; besides Asciidoctor, Markdown can also be configured. Each format has its own ID, and templates are loaded from the corresponding classpath package.

For the Markdown format, override templates live under the package:

```text
src/test/resources/org/springframework/restdocs/templates/markdown/
```

Example `request-fields.snippet`:

```markdown
{{#title}}
### {{title}}
{{/title}}

| Field Name | JSON Path | Type | Description |
| --- | --- | --- | --- |
{{#fields}}
| {{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}} | `{{path}}` | {{type}} | {{description}} |
{{/fields}}
```

To make REST Docs use the Markdown template format, configure `SnippetConfigurer` when setting up MockMvc:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import org.springframework.restdocs.templates.TemplateFormats;

this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .snippets().withTemplateFormat(TemplateFormats.markdown()))
    .build();
```

Exact API names and configuration details must match your project's Spring REST Docs version. You can configure the equivalent for WebTestClient or REST Assured via the integration module's `documentationConfiguration(...)`.

Do not place Markdown template files inside the `asciidoctor` directory or vice versa. The format ID determines the classpath package where REST Docs looks up templates.

## 8. Special characters and safety when rendering tables

When a field name or description contains a `|` character, Asciidoctor uses that character itself to delimit cells. For example, a description:

```text
Value can be A | B
```

If placed directly into a table without escaping, columns may be split incorrectly. The default Spring REST Docs template uses the Mustache lambda `tableCellContent` to escape pipe characters inside cells.

Custom templates should consider using:

```adoc
|{{#tableCellContent}}{{description}}{{/tableCellContent}}
```

Apply the same approach to `label` or `constraints` attributes if they can contain `|`.

For Markdown tables, escaping rules depend on the renderer and Markdown flavor in use. Verify the output with your project's exact documentation build tool; do not assume all Markdown renderers handle tables identically.

In addition:

- Do not put secrets or real user values into attributes just for display.
- Keep technical paths as contract data; treat labels purely as presentation labels.
- Normalize line breaks and special characters in descriptions.
- Do not include arbitrary HTML in templates if the publishing pipeline does not need to support it.

## 9. Organizing templates and avoiding unintended impact

Templates placed in `src/test/resources` are normally included on the test classpath and used during snippet generation. A template file with the same name as a snippet can override how that snippet is generated for all tests using the same format and classpath.

Example organization:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   └── response-fields.snippet
    └── markdown/
        ├── request-fields.snippet
        └── response-fields.snippet
```

Pay attention to the following:

1. Overriding `request-fields.snippet` does not automatically override `response-fields.snippet`; each snippet has its own template.
2. Shared templates must be able to handle descriptors that lack custom attributes; provide fallback values.
3. If multiple modules share the same test classpath, a template may affect a broader scope than intended. Organize resources per module and control dependencies/classpath.
4. When upgrading Spring REST Docs versions, check custom templates against the data fields provided by the new version.

If only one operation needs a different label, descriptor-level attributes are usually enough. If all operations need different column structures or header wording, a template is the right place.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Label does not appear | Forgot `.attributes(key("label")...)` or template does not read `{{label}}` | Check the key and Mustache variable |
| JSON path replaced by label | Mistakenly used label instead of descriptor path | Keep the real path; display the label in a separate column |
| New column is empty | Attributes not set on each descriptor | Attach `constraints` to fields needing data or provide a fallback |
| Title does not appear | Custom template does not read `{{title}}` | Add a `{{#title}}...{{/title}}` section |
| Asciidoctor title is not above table | Title placed in wrong location or wrong document attribute used | Place `.Title` directly before the include or use the operation macro with valid syntax |
| Template override has no effect | Wrong format package or template name | Check `templates/asciidoctor` and `request-fields.snippet` |
| Markdown mistakenly uses AsciiDoc syntax | Template format and directory do not match | Configure `TemplateFormats.markdown()` and `markdown` templates |
| Table breaks when description contains `\|` | Pipe character is unescaped | Use `tableCellContent` in Asciidoctor templates |
| Request template is right but response is wrong | Forgot to override `response-fields.snippet` | Create a separate response template if needed |
| Displayed constraints do not match validation | Attributes entered manually and became stale | Review alongside Bean Validation and business tests |
| Running tests does not show new snippets | Build uses stale output or tests did not run | Check output directory and task dependencies |

## 11. Integrating with Asciidoctor and build/CI

Custom templates must be on the test classpath when tests generate snippets. Source documentation files include the generated output:

```adoc
= Orders API
:toc: left

== Create order

include::{snippets}/orders-create/request-fields.adoc[]
```

If the template already renders a title inside the snippet, there is no need to add a duplicate title in the source document. If you choose to let Asciidoctor set the title, write:

```adoc
.Input fields when creating an order
include::{snippets}/orders-create/request-fields.adoc[]
```

With Gradle and the Asciidoctor plugin configured, the documentation task should depend on tests:

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

Ensure `spring-restdocs-asciidoctor` is configured according to your project's build guide so the `snippets` attribute is set. Templates are loaded when tests run; Asciidoctor only includes the generated snippet files.

CI workflow:

```text
HTTP tests (MockMvc / WebTestClient / REST Assured)
                    |
                    v
      FieldDescriptor + snippet attributes
                    |
                    v
       Mustache template by format
                    |
                    v
     request-fields.adoc / request-fields.md
                    |
                    v
             Asciidoctor / Markdown builder
                    |
                    v
            Verify and publish
```

When changing labels or columns, re-run tests to regenerate snippets and compile the documentation. Do not edit generated output manually because the next run will overwrite it.

## 12. Hands-on exercises

Using the `POST /api/orders` operation:

1. Add `label` to `customerId`, `items`, `items[].sku`, and `items[].quantity`.
2. Create `request-fields.snippet` for Asciidoctor, renaming columns to "Field Name", "JSON Path", "Type", and "Description".
3. Add `constraints` for `quantity` and render it in a separate column.
4. Pass the `title` attribute as "Order creation information" and display it in the template.
5. Remove the `label` attribute from one descriptor; confirm that the fallback still displays the path.
6. Add a description containing the `|` character; verify that the template uses `tableCellContent` so the Asciidoctor table does not break.
7. Create a Markdown template and configure `TemplateFormats.markdown()`. Compare the output of both formats.
8. Change the template for request fields without changing response fields; inspect both tables and decide whether a unified style is needed.
9. Run tests and Asciidoctor in CI; review the generated output instead of editing output files directly.

### Self-check questions

- How does a `FieldDescriptor` path differ from a display label?
- What is the difference between descriptor-level attributes and snippet-level attributes?
- Why must templates be overridden under the exact format ID?
- What is the template file name to override request fields?
- What roles do `{{#fields}}` and `{{#title}}` play?
- Can you set a table title in Asciidoctor without modifying the template?
- Why should `request-fields.snippet` and `response-fields.snippet` be managed separately?
- How do you keep a table from breaking when a description contains a `|` character?

**Key takeaway:** Keep the JSON path as the contract key, add labels for friendly display, and use Mustache templates to customize columns, order, and titles. Attributes provide the data; templates decide how it is presented. This way, Spring REST Docs still verifies real requests/responses in tests while documentation tables follow your product's language and conventions.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates, custom attributes, and adding columns to snippets.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): include snippets, table columns, and table titles.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): format IDs, Asciidoctor and Markdown templates.
- [Spring REST Docs — `SnippetConfigurer` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/config/SnippetConfigurer.html): configuring template format and encoding.
