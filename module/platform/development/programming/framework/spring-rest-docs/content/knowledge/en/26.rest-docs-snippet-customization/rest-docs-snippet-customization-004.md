# Adding extra information to snippets

## 1. Why add metadata to snippets?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. After a test sends a request and verifies the response, REST Docs generates snippets for requests, responses, payloads, parameters, headers, and hypermedia links. Snippets are compiled into Asciidoctor/Markdown and integrated into the build and CI pipeline.

Default descriptors contain technical details such as field paths, data types, and descriptions. Real-world documentation often needs extra context: a title for the table, API contract version, access permission notes, validation constraints for each field, or introductory text for a curl command.

Spring REST Docs allows passing **attributes** to add extra information to snippets and descriptors. Templates can read these attributes and present them according to project conventions. Because content is declared alongside tests, it can be reviewed and version-controlled together with HTTP examples.

## 2. Three scopes of information to distinguish

| Scope | Where attached | Example |
| --- | --- | --- |
| Snippet-level | Attributes passed to a snippet | Shared title, API version, note for the entire table |
| Descriptor-level | Attributes of a field, parameter, header, or link descriptor | Constraints, example values, unit of measure |
| Template-level | Placeholders and sections in Mustache | How title, version, note, and descriptor values are displayed |

For example: the request fields table has a title "Create user" at the snippet level; the email field has a constraint "Must be a valid email format" at the descriptor level; the template decides that the title sits above the table and the constraint sits in the last column.

Attributes do not modify requests/responses, create extra fields, or alter endpoint behavior. They are metadata supplied by tests for template presentation. If a value is not declared or the template does not read the matching key, the information will not appear as expected.

## 3. Creating attributes with Attributes.key(...)

Spring REST Docs provides a helper to create attributes:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;

key("title").value("Fields for user creation")
~~~

key("title") creates an attribute named title; value(...) supplies its value. You can pass multiple attributes in a single call:

~~~java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

attributes(
        key("title").value("Create user"),
        key("api-version").value("v1"),
        key("note").value("Email must be unique"))
~~~

Keys should have clear and consistent names. For multi-word keys, you can use kebab-case such as api-version, sample-value, or security-note. Avoid reusing a key that collides with an internal template variable for an unrelated meaning.

## 4. Adding extra information at the snippet level

A snippet can accept metadata that applies to the entire rendered block. For example, with requestFields(...), pass attributes before the list of field descriptors:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(
                key("title").value("Fields for user creation"),
                key("api-version").value("v1"),
                key("note").value("Email must be unique")),
        fieldWithPath("name").description("User name"),
        fieldWithPath("email").description("Email address"))
~~~

title, api-version, and note apply to this request fields table. They do not automatically propagate to curl-request, http-request, or other operations. To make another snippet display the same information, pass attributes to that specific snippet.

Example with a curl request:

~~~java
curlRequest(
        attributes(
                key("title").value("Example API call to create a user"),
                key("api-version").value("v1")))
~~~

Default snippets only display metadata if that snippet's template reads the corresponding keys. Passing attributes and overriding templates are two related but separate steps.

## 5. Adding extra information at the field descriptor level

A table often needs per-field metadata, such as constraints or example values. Attach attributes directly to the descriptor:

~~~java
requestFields(
        fieldWithPath("name")
                .description("User name")
                .attributes(key("constraints")
                        .value("Must not be blank; max 80 characters")),
        fieldWithPath("email")
                .description("Email address")
                .attributes(
                        key("constraints").value("Must be a valid email format"),
                        key("example").value("an@example.test")))
~~~

The name field has constraints metadata; the email field has both constraints and example. Templates can read each key on each element of fields.

| Key | Suggested meaning | Example |
| --- | --- | --- |
| constraints | Validation constraints | Must not be blank |
| example | Illustrative value | an@example.test |
| unit | Unit of measure | USD |
| format | Formatting rule | ISO-8601 |
| since | Version first supported | v2 |
| sensitivity | Data classification | Do not log real values |

These are project-defined keys; not all of them are standard attributes understood automatically by REST Docs. Templates must be written to read the chosen keys.

## 6. Displaying attributes with a Mustache template

Suppose you want to display title, API version, and note at the snippet level, plus Constraints and Example columns at the field level. Create a custom template at:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── asciidoctor/
        └── request-fields.snippet
~~~

Illustrative Mustache content:

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
|Path|Type|Description|Constraints|Example
{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
|{{example}}
{{/fields}}
|===
~~~

The title and note sections only appear when the attributes have values. The fields section iterates over each field descriptor. The constraints and example placeholders read the corresponding field attributes. Placeholder names must match the passed key names exactly.

## 7. Complete example: test passing metadata and generating snippets

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void createUserDocumentsExtraInformation() throws Exception {
    mockMvc.perform(post("/api/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "An",
                              "email": "an@example.test"
                            }
                            """))
            .andExpect(status().isCreated())
            .andDo(document("create-user",
                    requestFields(
                            attributes(
                                    key("title").value("Fields for user creation"),
                                    key("api-version").value("v1"),
                                    key("note").value("Email must be unique")),
                            fieldWithPath("name")
                                    .description("User name")
                                    .attributes(key("constraints")
                                            .value("Must not be blank")),
                            fieldWithPath("email")
                                    .description("Email address")
                                    .attributes(
                                            key("constraints")
                                                    .value("Must be a valid email format"),
                                            key("example")
                                                    .value("an@example.test")))));
}
~~~

Illustrative output:

| Path | Type | Description | Constraints | Example |
| --- | --- | --- | --- | --- |
| name | String | User name | Must not be blank | |
| email | String | Email address | Must be a valid email format | an@example.test |

Field types are inferred by Spring REST Docs from the documented payload. Constraints and example values are passed by the test. The template can be reused for other endpoints; each operation provides its own metadata.

## 8. Using extra information with other snippets

Snippet-level attributes are not limited to request fields. Snippet factories/constructors that support attributes can receive metadata in the same way. For example, a curl request might need a title and target audience:

~~~java
curlRequest(
        attributes(
                key("title").value("Call the endpoint with curl"),
                key("audience").value("API integrators")))
~~~

A custom curl template can display the metadata:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#audience}}
Audience: {{audience}}
{{/audience}}
{{{curlRequest}}}
~~~

The placeholder holding the curl content depends on the template model for your format and version. When customizing an existing snippet, start from the default template of the exact version and preserve the original placeholders. The example above illustrates adding metadata to a template, not a substitute for checking the actual model.

## 9. Metadata conventions to avoid inconsistent documentation

| Convention | Benefit |
| --- | --- |
| Use shared keys for the same meaning | Templates remain reusable |
| Short, clear key names | Reduces typos |
| Provide guidelines for optional keys | Authors know when to pass them |
| Do not declare two conflicting values | Avoids self-contradictory metadata |
| Use synthetic example values | Prevents exposing real data |
| Put business metadata in tests/descriptors | Makes contract changes easy to review |

You can standardize a shared set of keys such as title, api-version, note, constraints, example, and since. You do not need to attach every key to every snippet; only pass information that is useful to readers of that snippet type.

### Missing or empty attributes

Templates should handle cases where an attribute is not passed. Use Mustache sections to hide lines when no value is present:

~~~mustache
{{#note}}
NOTE: {{note}}
{{/note}}
~~~

If every field must have constraints, the team can adopt a review convention or descriptor helper to reduce missed metadata. Do not fill generic strings like N/A into every field if that value provides no information.

## 10. Attributes are not automatically extracted from Bean Validation

A common misconception is that Spring REST Docs automatically reads annotations like NotBlank, Email, or Size to populate a constraints column. Using attributes does not perform that step automatically.

If you want metadata to stay aligned with validation rules, you can:

1. Pass constraint content explicitly in the test descriptors.
2. Create a shared helper to map defined rules into attributes.
3. Build a custom snippet/template that reads project-supplied metadata.

Example of explicit declaration in a test:

~~~java
fieldWithPath("email")
        .description("Email address")
        .attributes(key("constraints")
                .value("@NotBlank, @Email"))
~~~

This is documentation content supplied by the author; it does not prove that the controller actually triggers validation. Tests still need to send invalid payloads and verify error responses if you want to verify those rules.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Attribute does not appear | Template does not read that key yet | Add the appropriate Mustache placeholder |
| Placeholder is empty | Key in template differs from passed key | Match the exact key name |
| Title appears on every table | Title attached at wrong scope or template lacks section check | Set snippet-level attributes and use conditional sections |
| Constraints on wrong field | Attribute attached to another descriptor | Check each field descriptor |
| Metadata missing from curl snippet | Attribute was only passed to requestFields | Pass the attribute to the target snippet and override its template |
| Validation metadata is stale | Manually written constraints not updated with code | Review metadata alongside validation changes and add tests |
| Special characters break the table | Content not escaped for target format | Handle special characters in template or data |
| Sensitive information leaks into docs | Real values used as example or note | Replace with synthetic data and review artifacts |

## 12. Hands-on exercises

1. Add title, api-version, and note to the request-fields snippet.
2. Attach constraints and example to different fields.
3. Create a Mustache template with conditional sections to hide omitted metadata.
4. Create a template for the curl request and display a custom title.
5. Remove an attribute from a test, re-run it, and verify that the template handles the missing value cleanly.
6. Add validation for email, then verify separately both the snippet metadata and the error response when sending an invalid email.
7. Inspect the snippet diff after changing metadata to confirm the content accurately reflects the test.

**Completion criteria:** distinguish snippet-level and descriptor-level attributes; pass data via Attributes.key(...).value(...); display metadata in Mustache; handle missing values; avoid confusing documentation metadata with API behavior verification.

## 13. Pre-commit checklist

- [ ] Every attribute has a clear purpose and scope.
- [ ] Snippet-level attributes are passed to the intended snippet.
- [ ] Descriptor-level attributes are attached to the right field/parameter/header/link.
- [ ] Key names match Mustache placeholders.
- [ ] Templates handle optional attributes without leaving awkward blank lines.
- [ ] Documented constraints match the current validation contract.
- [ ] Examples use synthetic values and contain no secrets or personal data.
- [ ] Snippet output has been regenerated from tests and inspected.
- [ ] Asciidoctor/Markdown build succeeds with the new templates.

**Key takeaway:** Extra information is passed via attributes at the snippet or descriptor level and rendered by templates. Clear metadata organization enriches snippets with context while keeping requests/responses and test assertions as the verified source of REST API documentation.
