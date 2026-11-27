# Snippet template format and the default engine

## 1. Two components that determine how snippets are generated

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. After a test executes a request and verifies the response, REST Docs collects operation data, combines descriptors and attributes, and generates snippets for requests, responses, payloads, parameters, headers, or hypermedia links. These snippets are fed into Asciidoctor/Markdown and the build and CI pipeline.

The rendering process has two distinct concepts:

- **TemplateFormat** defines the output format: the format identifier, the snippet file extension, and the location where matching templates are looked up.
- **TemplateEngine** reads and compiles the template, receives the data model, and renders it into snippet content.

In a typical setup, the development team chooses a built-in template format and uses the default Mustache template engine. Understanding the role of both components helps keep Asciidoctor/Markdown configuration consistent and makes it clear when to switch the format versus when to just replace a template.

~~~text
HTTP operation + descriptors + attributes
                  |
                  v
             Snippet model
                  |
                  v
          TemplateFormat
      (format ID / extension)
                  |
                  v
            TemplateEngine
        (compile / render)
                  |
                  v
          Generated snippet
                  |
                  v
       Asciidoctor / Markdown build
~~~

## 2. What is TemplateFormat?

TemplateFormat represents the snippet format. A format tells REST Docs which template group to look up on the classpath and which file extension to use for generated files. The format contains no HTTP verification logic and does not decide which operations are documented.

Spring REST Docs provides common built-in formats:

| Format | Configuration | Purpose |
| --- | --- | --- |
| Asciidoctor | TemplateFormats.asciidoctor() | Generates snippets suitable for AsciiDoc/Asciidoctor documentation |
| Markdown | TemplateFormats.markdown() | Generates snippets in Markdown format |

The format also provides an ID used in the template lookup path. For Asciidoctor, override templates live under the directory with ID asciidoctor; for Markdown, use the directory with ID markdown. The template file name matches the snippet name, typically with the .snippet source extension. The output file extension is determined by the format.

An illustrative resource layout:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   └── http-response.snippet
    └── markdown/
        ├── request-fields.snippet
        └── http-response.snippet
~~~

You only need to provide override templates for the snippets you actually want to change. Other templates continue to use the default resources from Spring REST Docs. The layout above illustrates the lookup mechanism; the project does not need to copy all default templates into test resources.

## 3. What does the default TemplateEngine do?

TemplateEngine is the component that processes template content. Functionally, the engine:

1. Locates and loads the template by snippet name and the resource path of the selected format.
2. Compiles the template syntax so it can be reused.
3. Receives the snippet's data model, containing fields such as path, type, description, or attributes.
4. Renders the model into the template to produce the output text.

Spring REST Docs uses **Mustache** as its default template engine. Mustache syntax uses placeholders and sections, for example:

~~~mustache
|Path|Type|Description
{{#fields}}
|{{path}}|{{type}}|{{description}}
{{/fields}}
~~~

In this example, fields is an iterable collection; path, type, and description are taken from each field descriptor's model. The engine does not automatically infer business details such as validation rules. If you need a constraints column, the test must pass the corresponding attribute and the template must read that attribute.

Key point to remember: TemplateFormat does not render content; TemplateEngine does not determine the HTTP contract. Descriptors and operations supply the data; the format selects the template/output type; the engine performs the rendering.

## 4. Choosing a format in MockMvc configuration

The format is selected through RestDocumentationConfigurer when configuring MockMvc:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                    .snippets()
                    .withTemplateFormat(TemplateFormats.asciidoctor()))
            .build();
}
~~~

To generate Markdown snippets:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

If no format is configured explicitly, Spring REST Docs uses the default format of the corresponding configuration, usually Asciidoctor. Declaring the format explicitly helps test readers understand the expected output and prevents documentation includes from pointing to the wrong extension.

## 5. Choosing a format with WebTestClient and REST Assured

The template format is part of snippet configuration and is not tied solely to MockMvc. Other test adapters also accept documentation configuration.

With WebTestClient, configure the format in the filter:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

With REST Assured, apply the REST Docs configuration in the filter:

~~~java
given(this.spec)
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .when()
        .get("/api/products/42")
        .then()
        .statusCode(200)
        .apply(document("products-get"));
~~~

These examples illustrate where to place the configuration; how RequestSpecification, RestDocumentationContextProvider, and imports are initialized depends on the project's test setup. Regardless of the adapter used, the operation and descriptors determine what content is documented; TemplateFormat determines the snippet format.

## 6. Template lookup paths by format

When a format is selected, Spring REST Docs uses the format's ID as a subdirectory when looking up override templates. For the Asciidoctor format:

~~~text
org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

For the Markdown format:

~~~text
org/springframework/restdocs/templates/markdown/request-fields.snippet
~~~

For an override to be found, verify all of the following:

- The resource is on the classpath of the tests that run documentation.
- The package path starts at org/springframework/restdocs/templates.
- The format directory matches the configured format.
- The template name matches the snippet type to replace, e.g., request-fields.snippet.
- The resource has valid encoding and content for the template engine.

If tests select Markdown but the custom template is only placed in the asciidoctor directory, that override template will not be used for the Markdown render pass. When you need to support both formats, create templates in both directories using output syntax appropriate for each format.

## 7. TemplateFormat and snippet file extensions

The format affects both the content syntax and the snippet file extension. For example, for the same products-get operation, an Asciidoctor configuration might produce:

~~~text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
~~~

When using Markdown, the corresponding file names carry the Markdown extension provided by the format:

~~~text
build/generated-snippets/
└── products-get/
    ├── http-request.md
    ├── http-response.md
    └── response-fields.md
~~~

The snippet names may be the same, while template content and file extensions differ. When changing formats, synchronize:

1. The withTemplateFormat(...) configuration in tests.
2. The location and syntax of override templates.
3. The names of generated snippet files.
4. Include paths in Asciidoctor or the snippet embedding step in Markdown.
5. Build tasks and published documentation artifacts.

Changing only the format in tests while keeping includes pointing to .adoc can cause documentation compilation to fail because the output files have changed to .md.

## 8. TemplateEngine and TemplateFormat can change independently

In most projects, you only need to choose TemplateFormats.asciidoctor() or TemplateFormats.markdown() and keep the default engine. If you want to adjust tables, headings, or presentation, overriding the corresponding Mustache file is usually sufficient.

| Need | Component to change |
| --- | --- |
| Switch snippets from AsciiDoc to Markdown | TemplateFormat |
| Change how a snippet is presented while keeping Asciidoctor output | Template override |
| Add custom metadata to fields | Descriptor attributes and template |
| Change the template compilation/rendering mechanism | TemplateEngine, when the default engine is insufficient |
| Change template syntax while still producing the same output format | TemplateEngine and matching template set if implemented by the project |

Do not write a custom TemplateEngine just to add a column or change a title. Implementing a custom engine increases maintenance overhead: you must handle resource lookup, compilation, rendering, encoding, and template errors consistently with the pipeline.

## 9. When do you need a custom TemplateEngine?

A custom engine is only worth considering if the project has requirements that the default Mustache engine cannot solve, for example:

- Integrating another template system that is already an organizational standard.
- Needing complex rendering logic or helpers beyond the capabilities of Mustache templates.
- Wanting to manage and cache templates with a custom mechanism.
- Having multiple output types or special escaping rules that require centralized control.

Before implementing one, check the API of the exact Spring REST Docs version you are using: the TemplateEngine type, how Template instances are created, the resource provision mechanism, and the method for registering the engine on the snippet configuration can change across versions.

Do not copy an engine implementation example from another version and assume it is compatible. For standard requirements, keeping the default engine and customizing templates/attributes takes advantage of the resource lookup and rendering behavior already supported by Spring REST Docs.

## 10. Encoding and output stability

Templates are text resources. With Vietnamese content, ensure that template files and output are handled consistently using UTF-8. If garbled characters appear in snippets, check:

- The encoding of template files in the repository.
- The encoding configured for the rendering process if customized by the project.
- The encoding used by the Asciidoctor/Markdown build when reading snippets.
- Whether special characters in the output syntax are escaped appropriately.

Templates should also avoid depending on environment-specific data such as host, port, tokens, or personal information. Dynamic data belongs to the operation; documentation should only display stable placeholder values or preprocessed data.

When upgrading Spring REST Docs, default templates and model attributes may change. Treat the default templates of the exact version as a technical contract to compare your overrides against. Keeping override files minimal helps reduce differences during upgrades.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Override template is not used | Wrong format ID or package path | Place the template under org/springframework/restdocs/templates/{format-id} on the test classpath. |
| Using Asciidoctor template but tests generate Markdown | The selected format is Markdown | Create the template in the markdown directory or change the configured format. |
| Include cannot find snippet after format change | File extension changed | Check the new output and update includes/documentation tasks. |
| Template does not render placeholder | Variable name is missing from the model or attributes were not passed | Compare the template with the snippet model and descriptor attributes. |
| Template syntax is rendered literally | Template engine does not understand the syntax used | Use Mustache syntax with the default engine or configure a compatible engine. |
| Vietnamese characters are garbled | Inconsistent encoding | Standardize templates and the pipeline on UTF-8. |
| Some snippets still use the old format | Another test or adapter has its own snippet configuration | Check the configuration of each test client and documentation test. |
| Template fails after version upgrade | Default model or template changed | Compare the new version's template, update the override, and inspect the output diff. |

## 12. Hands-on exercises

1. Run a documentation test with TemplateFormats.asciidoctor() and observe the snippet extensions and content.
2. Switch the test to TemplateFormats.markdown(); inspect the generated files and adjust include paths.
3. Create two separate request-fields.snippet templates for Asciidoctor and Markdown; keep the field data identical while changing table syntax per format.
4. Pass a constraints attribute into a field descriptor and display it using a Mustache template.
5. Check whether MockMvc and WebTestClient tests are using the same format; unify the format across the same documentation set.
6. Try placing a template in the wrong format folder, run the test, and observe signs that the default template was used.
7. Inspect the snippet diff after switching formats to ensure request/response content is preserved.

**Completion criteria:** explain the distinct roles of TemplateFormat and TemplateEngine; choose Asciidoctor/Markdown format; identify the correct template resource path; understand the default Mustache engine; synchronize snippet file extensions with the documentation compilation step.

## 13. Template format configuration checklist

- [ ] Choose an output format compatible with the documentation compilation tool.
- [ ] Configure the format consistently across documentation tests.
- [ ] Place override templates in the right directory for the format ID.
- [ ] Match template names with the snippets to customize.
- [ ] Use template syntax compatible with the active engine.
- [ ] Pass all required attributes from descriptors/snippets.
- [ ] Maintain UTF-8 encoding throughout.
- [ ] Match includes and extensions with generated snippet files.
- [ ] Have build/CI generate snippets before compiling and verify the final artifact.

**Key takeaway:** TemplateFormat determines the snippet type and where templates are looked up; the default TemplateEngine relies on Mustache to compile and render operation data into text. In most cases, choosing the right format and customizing templates is enough; only replace the engine when you have genuinely different rendering requirements.

## References

- Spring REST Docs - Snippet Template Format: https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html
- Spring REST Docs - Customizing the Output: https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html
- Spring REST Docs API - TemplateFormat: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/templates/TemplateFormat.html
- Spring REST Docs API - TemplateEngine: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/templates/TemplateEngine.html
