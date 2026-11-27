# Customizing generated snippets

## 1. Why customize snippets?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests execute requests and verify responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, headers, and hypermedia links. These snippets are compiled into Asciidoctor/Markdown and included in the build and CI pipeline.

The default snippets produce a consistent structure, but each project may need its own presentation style:

- Add a **Constraints** column to request/response fields tables to show validation rules.
- Add a title or explanatory text for each table.
- Change the snippet format from Asciidoctor to Markdown.
- Adjust how HTTP requests, responses, or curl commands are displayed according to documentation standards.
- Add default snippets to every operation without repeating calls in every test.

Spring REST Docs allows customization using Mustache templates and additional attributes. The data still comes from the tested operation; the template determines how that data is presented.

## 2. How Spring REST Docs generates snippets

Spring REST Docs uses **Mustache templates** to render snippet content. Each snippet type has a corresponding template: request-fields, curl-request, links, http-request, response-fields, etc.

~~~text
MockMvc / WebTestClient / REST Assured
                 |
                 v
          HTTP operation
                 |
                 v
       Snippet descriptor + attributes
                 |
                 v
          Mustache template
                 |
                 v
      Generated snippet file
                 |
                 v
       Asciidoctor / Markdown build
~~~

Customization can be done in three places:

| Location | Adjustment | Example |
| --- | --- | --- |
| Template | Structure, headers, tables, and layout | Add a Constraints column to request-fields |
| Descriptor attributes | Metadata of each field or descriptor | constraints, example, format |
| Snippet-level attributes | Shared metadata of a snippet | Title Fields for user creation |

Combining these parts allows templates to be reused across multiple operations while each operation still provides its own descriptive data.

## 3. Where to place custom templates

Templates are loaded from the classpath under the org.springframework.restdocs.templates package plus the name of the template format in use. The default format is Asciidoctor, which has the ID asciidoctor, so Asciidoctor templates reside under:

~~~text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
~~~

The template file name corresponds to the snippet name. For example, to replace the template for the curl-request.adoc snippet, create a curl-request.snippet file in the Asciidoctor template directory above. For request-fields, the template name is request-fields.snippet.

Rules to remember:

- Keep the exact classpath package org/springframework/restdocs/templates.
- The subdirectory must match the template format ID.
- The file name must match the name of the snippet to override.
- Use the .snippet extension for Mustache source templates.
- Place templates in test resources if they are only used for generating documentation from tests.

A custom template with the same name will be used to generate the corresponding snippet. Other snippets continue to use the default templates if you do not provide an override.

## 4. Changing snippet format: Asciidoctor or Markdown

Spring REST Docs generates snippets in Asciidoctor format by default. Markdown is also supported. With MockMvc, configure the format through RestDocumentationConfigurer:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                    .snippets()
                    .withTemplateFormat(TemplateFormats.markdown()))
            .build();
}
~~~

If you want to keep the default Asciidoctor format, you can configure it explicitly:

~~~java
.snippets()
.withTemplateFormat(TemplateFormats.asciidoctor())
~~~

With WebTestClient:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

The chosen format affects the templates looked up on the classpath and the file extension of the generated snippet files. When overriding templates for Markdown, use the directory with ID markdown:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/request-fields.snippet
~~~

Changing the template format does not automatically convert manually written documentation from AsciiDoc to Markdown. The final compilation step must read the right type of generated snippets. If the project uses Asciidoctor includes, keep using AsciiDoc snippets; if using Markdown, update the snippet inclusion mechanism accordingly.

## 5. Adding information to snippets using attributes

Spring REST Docs provides two places to pass extra information to a template:

1. Attach attributes to a descriptor using attributes(...).
2. Pass attributes at the snippet level when calling requestFields(...), curlRequest(...), httpRequest(...), httpResponse(...), and corresponding snippets.

These attributes are passed into the template rendering process. The Mustache template can read them and display the additional content.

### 5.1. Field-level attributes

For example, each request field has a constraint:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        fieldWithPath("name")
                .description("User name")
                .attributes(key("constraints").value("Must not be blank")),
        fieldWithPath("email")
                .description("Email address")
                .attributes(key("constraints")
                        .value("Must be a valid email format")))
~~~

constraints is custom-defined metadata. Spring REST Docs does not automatically infer validation details from Bean Validation annotations to populate this attribute; the test author must pass the values to be documented.

### 5.2. Snippet-level attributes

You can add a shared title for the request fields table:

~~~java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(key("title").value("Fields for user creation")),
        fieldWithPath("name")
                .description("User name")
                .attributes(key("constraints").value("Must not be blank")),
        fieldWithPath("email")
                .description("Email address")
                .attributes(key("constraints")
                        .value("Must be a valid email format")))
~~~

title applies to the snippet as a block; constraints applies to each individual field. The two attribute levels have different scopes, so do not share the same name for unrelated meanings.

## 6. Overriding the request-fields template to add a Constraints column

Here is a practical example. The goal is to create a table with four columns: Path, Type, Description, and Constraints.

### 6.1. Placing the template

Create the file:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

Mustache content:

~~~mustache
.{{title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
~~~

The template uses:

- {{title}}: snippet title.
- {{#fields}} ... {{/fields}}: iterates over the list of field descriptors.
- {{path}}, {{type}}, {{description}}: built-in data for each field.
- {{constraints}}: custom attribute provided by the test.

### 6.2. Passing attributes in the test

~~~java
@Test
void createUser() throws Exception {
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
                            attributes(key("title")
                                    .value("Fields for user creation")),
                            fieldWithPath("name")
                                    .description("User name")
                                    .attributes(key("constraints")
                                            .value("Must not be blank")),
                            fieldWithPath("email")
                                    .description("Email address")
                                    .attributes(key("constraints")
                                            .value("Must be a valid email format")))));
}
~~~

Illustrative output:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| name | String | User name | Must not be blank |
| email | String | Email address | Must be a valid email format |

The field type is inferred by Spring REST Docs from the documented payload. The constraints content is passed in by the test. The template can be reused across other endpoints; each operation provides its own title and constraints.

## 7. Customizing other snippets

The template override principle applies to many snippet types:

| Snippet | Content |
| --- | --- |
| curl-request | Curl command to call the API |
| http-request | HTTP request |
| http-response | HTTP response |
| httpie-request | HTTPie command |
| request-body | Request body |
| response-body | Response body |
| request-fields | Request fields table |
| response-fields | Response fields table |
| path-parameters | Path parameters |
| query-parameters | Query parameters |
| request-headers | Request headers |
| response-headers | Response headers |
| links | Hypermedia links |

For example, to change how the curl request is displayed, create:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/curl-request.snippet
~~~

This template is used instead of the default template when the active format is Asciidoctor and the operation generates the curl-request snippet. Available model attributes depend on the snippet type. When overriding, you should start from the corresponding default template of the exact Spring REST Docs version and modify only the necessary parts. This avoids missing variables or Mustache structures used by the default template.

Similarly, you can create links.snippet to change how the hypermedia links table is displayed or response-fields.snippet to add columns describing the response.

Do not override every template just because you can. Each override makes the project own an extra piece of output formatting and requires review when upgrading Spring REST Docs versions.

## 8. Keeping default snippets and adding default snippets

SnippetConfigurer lets you configure the snippets generated by default for each operation:

- withDefaults(...): sets the list of default snippets to generate.
- withAdditionalDefaults(...): appends default snippets to the existing list.

If you only want to add a default snippet, prefer withAdditionalDefaults(...):

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withAdditionalDefaults(new CustomDefaultSnippet()))
        .build();
~~~

CustomDefaultSnippet is a project-defined snippet class and must be implemented according to the Spring REST Docs API. If you use withDefaults(...), you are explicitly replacing the default list; you must provide again any snippets you still want generated, such as request, response, or curl. Misusing withDefaults(...) can remove snippet files that existing documentation pages currently include.

| Need | API |
| --- | --- |
| Only add a snippet to the default set | withAdditionalDefaults(...) |
| Define the exact set of snippets to generate | withDefaults(...) |

## 9. Creating a custom snippet for the project

When default snippets cannot express the required information, you can create a custom snippet and attach it to the operation. Spring REST Docs provides the Snippet abstraction for extension.

Conceptually, a custom snippet needs to:

1. Receive the executed operation.
2. Build a data model from the request/response or operation attributes.
3. Render the corresponding template using a template engine.
4. Write the file to the operation's output directory.

Skeleton describing the responsibilities:

~~~java
public final class ApiSummarySnippet implements Snippet {

    @Override
    public void document(Operation operation) throws IOException {
        // Read data from the operation.
        // Build the model for the template.
        // Render the template and write the snippet to the output directory.
    }
}
~~~

This is a skeleton, not a class that can compile as-is: the rendering part must be implemented using the TemplateEngine/template resource resolver corresponding to your Spring REST Docs version. When you only need to change how an existing snippet is displayed, overriding the Mustache template is usually simpler and easier to maintain.

An operation can use the custom snippet:

~~~java
mockMvc.perform(get("/api/users/{id}", 5))
        .andExpect(status().isOk())
        .andDo(document("users-get",
                new ApiSummarySnippet()));
~~~

The custom snippet class can be added to the default list via withAdditionalDefaults(...) if you want it to run for every operation under that MockMvc configuration.

## 10. Notes on template maintenance

Snippet customization is source code of the documentation workflow. It needs to be managed as part of the project:

- **Version synchronization:** when upgrading Spring REST Docs, check whether the default templates and the model passed to Mustache have changed.
- **Preserve essential data:** override templates must keep the necessary columns/placeholders so request or field information is not accidentally dropped.
- **Escape content:** payload data may contain special characters; use rendering/escaping appropriate for the target syntax to avoid generating invalid AsciiDoc/Markdown.
- **Avoid unnecessary coupling:** do not embed environment names, internal URLs, or sensitive data into shared templates.
- **Reusability:** put shared rules in the template; put endpoint-specific data in descriptor attributes.
- **Verify output:** compare newly generated snippets against expected output after tests run.

If a template is not found, check the package path, template format ID, snippet name, and whether test resources are on the test classpath. If an attribute does not appear in the output, verify that the Mustache key name matches the exact key name passed in attributes(...).

## 11. Build and CI integration

~~~text
Run documentation tests
          |
          v
Render snippets using project templates
          |
          v
Verify generated-snippets output
          |
          v
Asciidoctor / Markdown build
          |
          v
Publish documentation artifact
~~~

In CI, you should:

1. Run clean and documentation tests to generate snippets from current tests.
2. Compile the documentation after the tests complete.
3. Fail the build if a template fails to render or an included file is missing.
4. Store custom templates in version control alongside the tests that use them.
5. When upgrading Spring REST Docs, re-run the test suite and inspect the snippet diff.

A single template change can affect many snippet files at once. Review the diff to confirm that changes only affect presentation, without losing information or altering verified content.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Custom template is not applied | Wrong package path or format ID | Place under org/springframework/restdocs/templates/{format-id} on the test classpath. |
| Wrong snippet overridden | Template name does not match snippet name | Use the exact name, e.g. request-fields.snippet. |
| Attribute does not appear in snippet | Mustache key name differs from descriptor key | Match the constraints key with the constraints placeholder. |
| Constraints column is empty | Field descriptor has no attribute attached | Add attributes(key("constraints").value(...)) to that field. |
| Markdown template not loaded | Still using Asciidoctor format or file in wrong directory | Configure TemplateFormats.markdown() and use the markdown folder. |
| Default snippets disappeared | Used withDefaults(...) and replaced the entire list | Use withAdditionalDefaults(...) if the goal is only to append. |
| Template breaks after version upgrade | Default model or template changed | Compare the new version's default template and update the override. |
| Documentation fails to build after template change | Generated content is invalid for Asciidoctor/Markdown | Open the generated snippet, fix the template, and re-run tests and the document build. |

## 13. Hands-on exercises

1. Create a request-fields.snippet template in the Asciidoctor directory and add a Constraints column.
2. Pass title at the snippet level and constraints at the individual field level; run the test and inspect the output table.
3. Create the corresponding template in the markdown directory, configure TemplateFormats.markdown(), and compare the output.
4. Override curl-request.snippet to add a title or explanation according to your team's conventions.
5. Use withAdditionalDefaults(...) to add a default snippet; verify that the old request/response snippets are still generated.
6. Try withDefaults(...) with a small list, observe which snippets no longer appear, and restore the required list.
7. Modify a template and inspect the output diff in CI to verify that only formatting changed.

**Completion criteria:** identify the correct template location by format ID; override a default snippet with Mustache; pass and display custom attributes; switch between Asciidoctor/Markdown; distinguish withDefaults(...) and withAdditionalDefaults(...); verify output through the build.

## 14. Pre-commit checklist for templates

- [ ] Template is in the right classpath package and format ID.
- [ ] Template file name matches the snippet name to override.
- [ ] Mustache placeholders use the right model and attributes.
- [ ] Field-level and snippet-level attributes are clearly distinguished.
- [ ] Template still displays all important information from the original snippet.
- [ ] Asciidoctor/Markdown format matches test configuration and documentation pipeline.
- [ ] withDefaults(...) is only used when intentionally replacing the entire default snippet list.
- [ ] Snippet-generating tests were run and output file contents verified.
- [ ] Documentation build succeeds from the newly generated snippets.

**Key takeaway:** Customizing generated snippets is mainly about replacing Mustache templates and adding attributes. Placing templates in the right classpath/format ID, passing metadata from descriptors, and letting tests regenerate snippets lets a project change presentation while preserving the data verified by Spring REST Docs.

## References

- [Spring REST Docs - Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html)
- [Spring REST Docs - Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs API - SnippetConfigurer](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/config/SnippetConfigurer.html)
