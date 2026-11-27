# Placing templates in src/test/resources

## 1. Why does template placement matter?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests execute requests, verify responses, and declare descriptors; Spring REST Docs uses operation data to generate snippets for requests, responses, fields, parameters, headers, and hypermedia links. These snippets are compiled into Asciidoctor/Markdown and integrated into the build and CI pipeline.

When you need to customize presentation, you can supply your own Mustache templates. Spring REST Docs looks up custom templates on the classpath following a specific convention. If you place a file in the wrong directory, under the wrong format ID, or with the wrong snippet name, the default template will continue to be used without necessarily throwing a clear error.

Because templates are typically only used for generating documentation in tests, the appropriate location is:

~~~text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
~~~

This path becomes the classpath resource:

~~~text
org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

The key point is that Spring REST Docs resolves templates as classpath resources, not via arbitrary paths from the current working directory.

## 2. What does the directory structure mean?

The template path has three main parts:

| Component | Role | Example |
| --- | --- | --- |
| Root package | Resource namespace Spring REST Docs uses to look up templates | org/springframework/restdocs/templates |
| Format ID | Selects the template set for the output format | asciidoctor or markdown |
| Snippet name | Selects the exact snippet type to override | request-fields.snippet |

General rule:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── {format-id}/
        └── {snippet-name}.snippet
~~~

Example:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   ├── response-fields.snippet
    │   ├── path-parameters.snippet
    │   ├── query-parameters.snippet
    │   ├── http-request.snippet
    │   ├── http-response.snippet
    │   └── links.snippet
    └── markdown/
        ├── request-fields.snippet
        ├── path-parameters.snippet
        └── links.snippet
~~~

You do not need to create all of these files. Only add the templates you genuinely want to change. Templates without an override continue to be loaded from the Spring REST Docs library.

## 3. Template names must match snippet names

The template name is the snippet name without the output extension, using the .snippet source suffix.

| Generated snippet | Template to place |
| --- | --- |
| request-fields | request-fields.snippet |
| response-fields | response-fields.snippet |
| path-parameters | path-parameters.snippet |
| query-parameters | query-parameters.snippet |
| request-headers | request-headers.snippet |
| response-headers | response-headers.snippet |
| links | links.snippet |
| curl-request | curl-request.snippet |
| http-request | http-request.snippet |
| http-response | http-response.snippet |

For example, when a test uses requestFields(...), Spring REST Docs generates the request-fields snippet. To change this table, create request-fields.snippet in the matching format directory. Creating fields.snippet or requestFields.snippet will not replace the template named request-fields.

Template file names follow the library's snippet naming convention. On Linux build systems, letter case in resource names also affects file lookup; keep the exact casing of snippet names.

## 4. Why place them in src/test/resources?

Gradle and Maven include resources in src/test/resources on the test runtime classpath. This is the right place for templates used only by documentation tests:

- Avoids packaging test-only templates into the production application artifact.
- Templates are committed alongside tests and can be reviewed like source code.
- Each module can have its own presentation rules without affecting other modules.
- When running tests, resource lookup finds the templates on the classpath.

Distinguishing the two locations:

| Location | Classpath | When appropriate |
| --- | --- | --- |
| src/main/resources | Application runtime classpath | Application resources needed in production |
| src/test/resources | Test runtime classpath | Templates used only to generate documentation in tests |

Do not place test templates in src/main/resources just to make lookup seem easier. Doing so can cause internal templates to be packaged into the application artifact and mixes documentation responsibilities with runtime code.

If a project intentionally shares templates across multiple modules or tools, it can package templates into test-fixtures or a dedicated test resource library. Even then, the resources must still appear on the documentation test classpath and follow the package/format/name convention.

## 5. Format configuration must match the template folder

Spring REST Docs provides built-in template formats such as Asciidoctor and Markdown. The format is selected in snippet configuration:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .build();
~~~

With this configuration, the override template directory must be:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/
~~~

When selecting Markdown:

~~~java
.snippets()
.withTemplateFormat(TemplateFormats.markdown())
~~~

The corresponding override directory is:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/
~~~

Placing request-fields.snippet in the markdown directory while tests still use TemplateFormats.asciidoctor() will not override the Asciidoctor render pass. Check the configuration of the exact test client generating the snippets, not just a shared configuration elsewhere.

## 6. Complete example: overriding request-fields

Suppose you want to add a Constraints column to the request fields snippet.

### Step 1: Create the file in the right location

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

### Step 2: Write the Mustache content

~~~mustache
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

This is a minimal example to illustrate the location and override mechanism. In a real project, you should copy the default request-fields template of your exact Spring REST Docs version and add the columns you need. That preserves built-in information such as optional, ignored, deprecated, or special metadata if supported by your version's template.

### Step 3: Pass metadata from descriptors

~~~java
requestFields(
        fieldWithPath("email")
                .description("Email address")
                .attributes(key("constraints")
                        .value("Must be a valid email format")),
        fieldWithPath("displayName")
                .description("Display name")
                .attributes(key("constraints")
                        .value("From 2 to 80 characters")))
~~~

The template reads constraints from each field's attributes. If that key has not been passed, the corresponding placeholder may be empty. Templates do not automatically infer constraints from controllers or Bean Validation.

### Step 4: Run documentation tests and verify output

After tests run, check the configured snippet directory, typically:

~~~text
build/generated-snippets/
└── users-create/
    └── request-fields.adoc
~~~

This is the common default output directory with Gradle; if your project configures a different output directory, check the configured path. The generated content should include the Constraints column and values from attributes.

## 7. Organizing templates across multiple modules

In a multi-module project, each module has its own test resources and test runtime classpath. For example:

~~~text
project/
├── api-users/
│   └── src/test/resources/
│       └── org/springframework/restdocs/templates/asciidoctor/
│           └── request-fields.snippet
├── api-orders/
│   └── src/test/resources/
│       └── org/springframework/restdocs/templates/asciidoctor/
│           └── request-fields.snippet
└── build.gradle
~~~

Two modules can use the same resource path with different template contents because each module runs tests with its own classpath. If a module's tests do not pick up an override, first verify that the file is located in that exact module's test resources.

When sharing templates across multiple modules:

1. Put shared templates in test-fixtures or a dedicated test resource artifact.
2. Add that artifact to each module's test runtime classpath.
3. Keep the exact package, format ID, and snippet names.
4. Ensure no other resource at the same path takes precedence on the classpath.
5. Run documentation tests in each module to verify output.

Do not assume a file in module A's src/test/resources is automatically present on module B's classpath. You must configure the corresponding test dependency.

## 8. Avoiding resource conflicts and verifying the classpath

Some projects have multiple libraries or test fixtures contributing resources under the org/springframework/restdocs/templates package. Multiple resources at the same path may exist. Check which resource the classloader actually sees.

You can use a small Java snippet in a test to list resources with the same name:

~~~java
Enumeration<URL> resources =
        Thread.currentThread()
                .getContextClassLoader()
                .getResources(
                        "org/springframework/restdocs/templates/asciidoctor/request-fields.snippet");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
~~~

If multiple results appear, check the order and origin of each resource. Do not rely on accidental classpath ordering to decide which template is used. Ideally, there should be only one intentional override per template name on a module's test runtime classpath.

You can verify whether the resource is found:

~~~java
URL template = Thread.currentThread()
        .getContextClassLoader()
        .getResource(
                "org/springframework/restdocs/templates/asciidoctor/request-fields.snippet");

assertThat(template).isNotNull();
System.out.println(template);
~~~

This snippet only confirms that the resource exists; whether REST Docs actually uses the template also depends on the selected format, snippet name, and rendering step. Combine classpath checks with inspecting generated snippet content.

## 9. Relationship between source templates and output snippets

Do not confuse source template files with rendered snippet files:

| File | Role | Example |
| --- | --- | --- |
| request-fields.snippet | Mustache template loaded from classpath | src/test/resources/.../asciidoctor/ |
| request-fields.adoc | Output snippet after running Asciidoctor tests | build/generated-snippets/users-create/ |
| request-fields.md | Output snippet when using Markdown format | Test output directory |

The template is the input to the rendering step; the snippet is the output written to the operation's output directory. Editing a template does not update old snippet files unless tests are re-run. Therefore, the documentation compilation task must depend on documentation tests.

The build flow should follow this order:

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Load template from test classpath
          |
          v
Render snippets to output directory
          |
          v
Run Asciidoctor / Markdown build
          |
          v
Verify documentation artifact
~~~

Do not edit generated .adoc or .md files directly to customize formatting. Modify the source template, re-run tests, and let the build regenerate the snippets.

## 10. Common mistakes when placing templates

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| Default template is still used | Override template has wrong path or is not on test classpath | Check resource URL via classloader and format ID folder |
| Asciidoctor override has no effect | Tests select Markdown or another format | Check withTemplateFormat(...) on the test adapter |
| Only one snippet type changes | Only created a template for one snippet name | Create separate files for request-fields, path-parameters, links, etc. to override |
| Template is not loaded in submodule | Resource is in a different module | Place in the right module's test resources or declare test fixture dependency |
| File with nearly right name is unused | Name does not match snippet name | Use the exact name format such as request-fields.snippet |
| Tests work locally but CI cannot find file | Resource path has wrong case or was not committed | Check file name and contents on the CI build environment |
| Template changed but old snippet unchanged | Documentation tests were not re-run or stale output was not cleaned | Run the snippet-generating test task and check the output directory |
| Two templates at the same path | Multiple dependencies put same-named resource on classpath | List resource URLs and eliminate conflicts |
| Document include cannot find snippet | Output extension or directory does not match | Check TemplateFormat, output directory, and include path |

When diagnosing, follow this order: confirm which format the tests use, confirm the template path on the classpath, confirm the snippet name, and then inspect the output. This pinpoints whether the issue is in lookup or rendering.

## 11. Hands-on exercises

1. Create request-fields.snippet under src/test/resources in the Asciidoctor format.
2. Run a documentation test and confirm the override resource is used in the output.
3. Also create path-parameters.snippet and query-parameters.snippet; verify each snippet is replaced independently.
4. Switch the test configuration to Markdown and create templates with the same names under the markdown directory.
5. Use the classloader to list resource URLs and confirm templates are on the test runtime classpath.
6. Create two separate test modules, place same-named templates with different contents, and observe independent classpaths.
7. Create a duplicate-path resource in a test fixture and diagnose the conflict; then remove the duplicate source.
8. Wire the snippet-generating task to the Asciidoctor/Markdown compilation task in CI.

**Completion criteria:** know the standard template path in src/test/resources; understand format ID and snippet name; distinguish source templates from output snippets; inspect classpath and avoid conflicts; organize templates in multi-module projects.

## 12. Pre-commit checklist for templates

- [ ] Template is in src/test/resources of the right module or test fixture dependency.
- [ ] Package path is org/springframework/restdocs/templates.
- [ ] Subdirectory matches the configured format ID.
- [ ] File name matches the exact snippet name.
- [ ] Only templates that genuinely need changes are overridden.
- [ ] Template is saved in UTF-8 and uses syntax compatible with the default Mustache engine.
- [ ] Test runtime classpath has only the intended override, with no duplicate resources from unclear sources.
- [ ] Documentation tests have been re-run to generate fresh snippets.
- [ ] Include paths match the output directory and file extensions.
- [ ] Build/CI produces the final documentation from the new snippets.

**Key takeaway:** Spring REST Docs looks up custom templates on the classpath by package, format ID, and snippet name. Placing files in the right module's src/test/resources ensures templates serve only documentation tests; combining classpath checks with inspecting generated output guarantees overrides work reliably both locally and in CI.
