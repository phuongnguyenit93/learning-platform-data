# Including Snippets in Markdown Documentation

## Lesson Objectives

Spring REST Docs generates snippets from HTTP tests. When a development team publishes documentation in **Markdown**, those verified snippets need to be placed in the right positions on the page so readers see requests, responses, payloads, headers, and parameters alongside explanatory prose. The key point to remember is that **plain Markdown does not define a standard file include syntax**. Therefore, the snippet assembly process must be handled by the project's documentation tooling or build.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into build and CI workflows.

After this lesson, you will be able to:

- Distinguish Asciidoctor's include syntax from plain Markdown.
- Choose a strategy to bring REST Docs snippets into Markdown pages.
- Configure REST Docs to generate snippets using the Markdown template format if your version supports it.
- Use the documentation builder's own include directive when supported by the project.
- Assemble Markdown content and snippets using a controlled build task.
- Keep snippets test-generated without manually editing them inside the output directory.
- Connect tests, documentation assembly, link checking, and CI.

## 1. Why Is an Include Mechanism Needed?

A REST Docs test typically generates multiple files for one operation, for example:

~~~text
build/generated-snippets/
└── orders-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
~~~

A Markdown page might contain author-written explanations:

~~~markdown
# Get Order by ID

Endpoint returns information for a single order.

## Request

## Path parameters

## Response
~~~

The request/response/descriptor sections need to come from test-generated snippets. If copied manually into Markdown, content can become stale after the API or tests change. An include or build-time assembly mechanism ensures documentation always uses snippets from the current test run.

## 2. Plain Markdown Has No Standard Include Syntax

Markdown specifies how to write headings, paragraphs, links, lists, tables, and fenced code blocks. It does not define a universal directive to read another file's contents. For example:

~~~text
include::build/generated-snippets/orders-get/http-request.adoc[]
~~~

is **Asciidoctor's include syntax**, not plain Markdown. An ordinary Markdown renderer will display this line as text or handle it according to custom rules; it will not automatically open the snippet file.

Similarly, shortcodes or HTML comments such as the following are not universal include syntax:

~~~markdown
{{< include "orders-get/http-request.md" >}}
<!-- include: build/generated-snippets/orders-get/http-request.md -->
~~~

Some documentation platforms provide their own plugins or directives, but they only work when the corresponding page builder is configured.

Before choosing an include approach, determine **where Markdown is rendered**:

| Documentation Environment | Include Capability |
| --- | --- |
| Plain Markdown, basic renderer | No standard file include |
| Asciidoctor | Has include directive in AsciiDoc documents |
| Static site generator | May provide its own include directive/plugin |
| Custom build task assembling files | Can insert snippets into complete Markdown before rendering |
| Documentation management platform | Depends on extensions and content import mechanism |

Do not add a static site generator's directive before confirming that the project actually uses that generator.

## 3. Option One: Generating Snippets Using the Markdown Template Format

Spring REST Docs focuses on generating snippets from tested operations. Versions supporting the Markdown template format can generate snippet content in Markdown format instead of AsciiDoc. Check your project's API and dependency version before configuring.

Example default configuration with the Markdown template format, when the REST Docs version in use provides the corresponding API:

~~~java
import static org.springframework.restdocs.templates.TemplateFormats.markdown;

mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .snippets()
        .withTemplateFormat(markdown()))
    .build();
~~~

This is a configuration example for guidance. Exact package names, builder methods, and configuration style depend on the Spring REST Docs version. Check the Javadoc of the dependency in use; do not copy `markdown()` if your current version does not provide that template format. Some projects configure the template format on individual snippets or in documentation configuration.

When using the Markdown template format, generated snippets are still **fragment files**. Switching from AsciiDoc snippets to Markdown snippets does not automatically insert fragments into main Markdown pages.

For example, the output directory may become:

~~~text
build/generated-snippets/
└── orders-get/
    ├── http-request.md
    ├── http-response.md
    ├── path-parameters.md
    └── response-fields.md
~~~

Specific filenames and extensions depend on the snippets/templates configured by the project. Inspect the actual output rather than assuming every snippet always changes `.adoc` to `.md`.

### 3.1. When to Choose Markdown Snippets?

Choose Markdown snippets when final documentation is rendered by a Markdown renderer, Markdown templates satisfy formatting needs, and the project already has a fragment include/assembly mechanism. Do not choose it solely because target files have a `.md` extension; verify both snippet generation and assembly.

## 4. Option Two: Using the Markdown Platform's Include Directive

Some documentation builders extend Markdown with an include directive or plugin. With this approach, the workflow has two parts:

1. Configure REST Docs to generate snippets as Markdown or convert snippets to Markdown.
2. Use the include directive with the exact syntax of the tool rendering the pages.

Illustrative example of a platform-specific hypothetical directive:

~~~markdown
## Request

<!-- include: build/generated-snippets/orders-get/http-request.md -->

## Response

<!-- include: build/generated-snippets/orders-get/http-response.md -->
~~~

The HTML comments above are only examples, not an include syntax that works by default. The renderer must have a plugin that understands and processes them. Without the plugin, the comments may be ignored and snippets will not appear.

When setting up an include plugin:

- Confirm which file or root directory relative paths are resolved against.
- Ensure snippets already exist before the static site generator runs.
- Check whether the plugin allows including files outside the content directory.
- Avoid arbitrary filesystem includes if the tool enforces security restrictions.
- Determine how the tool handles fenced code, HTML, and relative links inside fragments.
- Inspect the actual rendered page; leaving the directive intact in source does not prove content was included.

There is no single syntax across all Markdown renderers. Follow the documentation of the exact generator/plugin in your project and document that requirement in the build documentation.

## 5. Option Three: Build-Time Assembly

If a project wants to keep Markdown broadly compatible, static prose and snippets can be assembled into a complete Markdown file before rendering:

~~~text
src/docs/markdown/
├── orders-intro.md
└── customers-intro.md

build/generated-snippets/
└── orders-get/
    ├── http-request.md
    ├── http-response.md
    ├── path-parameters.md
    └── response-fields.md

build/docs-markdown/
└── orders.md
~~~

The assembly task reads fragments in a declared order, inserts snippet contents, and writes the resulting file to `build/docs-markdown`. Do not write generated files into `src/` since every build can regenerate output.

### 5.1. Static Content

File `src/docs/markdown/orders-intro.md`:

~~~markdown
# Orders API

API for managing orders.

## Get Order by ID

Endpoint returns an order by its identifier.
~~~

The list of snippets to assemble can be managed by a dedicated manifest for the build task, for example:

~~~text
SNIPPET: orders-get/path-parameters.md
SNIPPET: orders-get/http-request.md
SNIPPET: orders-get/response-fields.md
SNIPPET: orders-get/http-response.md
~~~

The manifest is an input to assembly, not Markdown content to publish verbatim.

### 5.2. Assembly Rules

A good assembly task should:

1. Run after tests that generate snippets.
2. Accept the list of source files and snippets in a deterministic order.
3. Report a clear error when a required snippet does not exist.
4. Preserve UTF-8 encoding.
5. Insert appropriate headings or whitespace so fragments do not run into each other.
6. Write output to the build directory.
7. Never modify test sources or original snippet files.

An example final output might look like:

~~~~markdown
# Orders API

API for managing orders.

## Get Order by ID

Endpoint returns an order by its identifier.

## Path parameters

| Name | Description |
| --- | --- |
| orderId | Order ID |

## Request

~~~http
GET /api/orders/42
Accept: application/json
~~~

## Response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"OPEN"}
~~~
~~~~

This illustrates the shape of the final file. Request, response, and descriptor table contents in a real product must come from REST Docs snippets of the corresponding build, not be hand-written like the example.

## 6. Example Gradle Task for Assembly

A custom Gradle task can be implemented to assemble Markdown. The following example illustrates the task structure; adjust paths and snippet sets for your project:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')
def markdownSourceDir = layout.projectDirectory.dir('src/docs/markdown')
def assembledDocsDir = layout.buildDirectory.dir('docs-markdown')

tasks.register('assembleMarkdownDocs') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    inputs.dir markdownSourceDir
    outputs.dir assembledDocsDir

    doLast {
        def outputDir = assembledDocsDir.get().asFile
        outputDir.mkdirs()

        def output = new File(outputDir, 'orders.md')
        def intro = new File(markdownSourceDir.asFile, 'orders-intro.md')
        def requestSnippet = new File(
            snippetsDir.get().asFile,
            'orders-get/http-request.md'
        )
        def responseSnippet = new File(
            snippetsDir.get().asFile,
            'orders-get/http-response.md'
        )

        [intro, requestSnippet, responseSnippet].each { file ->
            if (!file.isFile()) {
                throw new GradleException(
                    "Required documentation input not found: ${file}"
                )
            }
        }

        output.setText(
            intro.getText('UTF-8') +
            '\n\n## Request\n\n' +
            requestSnippet.getText('UTF-8') +
            '\n\n## Response\n\n' +
            responseSnippet.getText('UTF-8') +
            '\n',
            'UTF-8'
        )
    }
}
~~~

The sample task assembles three fixed files for illustration. A real project should manage required snippets via configuration or a manifest instead of writing one huge task containing paths for every operation. If there are multiple API pages, declare separate outputs per page and avoid two tasks writing to the same file.

### 6.1. Wiring the Task into the Build Flow

If there is a separate Markdown rendering task, set the dependency:

~~~groovy
tasks.named('renderMarkdownDocs') {
    dependsOn tasks.named('assembleMarkdownDocs')
}
~~~

If using a documentation plugin, wire `assembleMarkdownDocs` into that plugin's content-processing task. Do not assume every plugin has a task named `renderMarkdownDocs`; task names depend on the tool in use.

Overall flow:

~~~mermaid
flowchart TD
    A[HTTP tests: MockMvc / WebTestClient / REST Assured] --> B[Spring REST Docs generates snippets]
    B --> C[Validate required snippets]
    C --> D[Assemble Markdown pages]
    D --> E[Render Markdown site]
    E --> F[Check links and publish artifact]
~~~

## 7. Example Test Generating Operation Snippets

Suppose a MockMvc test uses document identifier `orders-get`:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        pathParameters(
            parameterWithName("orderId")
                .description("Order ID to look up")
        ),
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Order status")
        )
    ));
~~~

With a Markdown template format configuration appropriate to your version, the assembly task can consume the corresponding fragments. If the project still uses AsciiDoc snippets, do not manually rename file extensions to `.md`. Convert them with tooling or configure generation with the proper template before assembly.

Snippet-generating tests and assembly have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| document("orders-get", ...) | Associates snippets with the tested operation |
| pathParameters(...) | Verifies and describes `orderId` |
| responseFields(...) | Verifies and describes response fields |
| Template format | Determines the format of generated snippets |
| Assembly task/include plugin | Inserts snippets into Markdown pages |
| Markdown renderer | Converts final Markdown to HTML or target format |

## 8. Organizing Snippets and Paths

A documentation system should follow a stable path convention:

~~~text
src/
└── docs/
    └── markdown/
        ├── orders-intro.md
        └── customers-intro.md

build/
├── generated-snippets/
│   ├── orders-get/
│   └── customer-get/
└── docs-markdown/
    ├── orders.md
    └── customers.md
~~~

Notes:

- The document identifier is the key assembly uses to locate the right snippet.
- Changing an identifier requires updating the manifest or assembly references.
- Snippet paths are build outputs; do not commit old copies as the source of truth.
- Do not include a snippet from a different operation just because filenames match.
- If a snippet is used across multiple pages, clearly establish which page is canonical and which references it.
- If output is split by API version, include the version in the path or identifier.

## 9. Links, Images, and Code Fences in Fragments

When assembling Markdown snippets, avoid formatting errors:

**Code fences:** snippets may contain fenced code blocks. The assembly page must not wrap the entire snippet inside another code fence, or the renderer will display the whole snippet as plain text.

**Headings:** if a snippet template has its own headings, check heading levels during assembly so TOC structure is not broken.

**Links and images:** relative paths inside snippets may resolve relative to the fragment file or the final page depending on the tool. Inspect rendered output to ensure assets are found.

**Encoding:** use UTF-8 for Markdown sources and snippets. Vietnamese content, JSON, or headers containing Unicode characters must render properly.

**Whitespace:** insert blank lines between fragments so paragraphs, tables, or code blocks do not merge together.

**Front matter:** if the static site generator requires YAML front matter, add it only on the final page per the generator's convention. Do not repeat fragment front matter in the middle of the page.

## 10. Verifying Documentation After Assembly

A passing build does not guarantee Markdown pages render properly. Verification should confirm:

1. All required snippets exist.
2. Final pages contain requests, responses, parameters, and fields for the right operations.
3. No raw Asciidoctor include lines remain in plain Markdown.
4. No unprocessed plugin include directives remain.
5. Code fences are balanced and tables do not attach to preceding paragraphs.
6. Relative links and assets work after rendering.
7. No tokens, session IDs, or sensitive test data appear in snippets.
8. Content is regenerated from the current test run, not reused from an old build.

Required files can be checked before rendering. PowerShell example:

~~~powershell
$required = @(
    'build/generated-snippets/orders-get/http-request.md',
    'build/generated-snippets/orders-get/http-response.md',
    'build/generated-snippets/orders-get/path-parameters.md'
)

$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing.Count -gt 0) {
    throw "Missing REST Docs snippets: $($missing -join ', ')"
}
~~~

Adjust extensions based on actual output. If generated snippets are `.adoc`, the check must not silently expect `.md`.

## 11. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Markdown displays raw include line | Using Asciidoctor syntax in plain Markdown | Use an Asciidoctor renderer or a Markdown include/assembly mechanism |
| Include directive does not run | Plugin/generator not installed or not enabled | Verify the right renderer and plugin |
| `.adoc` snippet included as `.md` | Wrong template format or manual extension rename | Configure Markdown template or perform controlled conversion |
| Page missing request/response | Snippet not generated or wrong identifier | Check `document(...)`, output directory, and manifest |
| Stale snippet content | Assembly runs before tests or reuses old output | Wire test → assembly dependency and refresh output per build strategy |
| Broken code fences | Nesting snippet inside another fence or unbalanced fragment | Assemble fragments intact and check rendered page |
| Markdown table sticks to previous paragraph | Missing blank lines when joining fragments | Insert explicit newlines between fragments |
| Links/images not found | Base path changes when fragments are assembled | Normalize relative asset paths |
| Include path works locally but fails in CI | Depends on working directory or absolute paths | Use paths based on project/build directory |
| Page contains real tokens/sessions | HTTP snippet recorded sensitive test values | Use fake fixtures and preprocessors; inspect output |
| Assembler ignores missing snippets | Task skips non-existent files | Treat required snippets as inputs and fail early when missing |

## 12. Practice Exercise

Document two operations:

~~~text
GET /api/orders/{orderId}
POST /api/orders
~~~

Requirements:

1. Write MockMvc tests generating snippets for both operations with identifiers `orders-get` and `orders-create`.
2. Describe the path parameter for GET and request/response fields for POST.
3. Configure REST Docs to generate Markdown snippets if your version supports the Markdown template format; otherwise, choose an explicit conversion step.
4. Create source page `orders-intro.md` explaining the API.
5. Write an assembly task placing `http-request`, `http-response`, `path-parameters`, `request-fields`, and `response-fields` into the appropriate sections.
6. Fail the build when a required snippet is missing.
7. Render the final page and inspect headings, code fences, tables, links, and UTF-8.
8. Connect tests → assembly → renderer in CI.

**Completion criteria:** the final Markdown page contains test-generated snippets; no unprocessed include directives remain; content is refreshed on every build; missing snippets fail the pipeline; rendered page has no structural errors.

## Key Takeaways

Plain Markdown has no standard file include syntax. Spring REST Docs can generate snippets using a version-appropriate template format, but fragments still must be brought into final pages via a platform include plugin or build-time assembly. Do not use Asciidoctor's `include::...[]` as if every Markdown renderer understands it. Connect snippet-generating tests to the assemble/render step, verify required files, code fences, links, encoding, and sensitive data before publishing. That way Markdown content is assembled from exact evidence produced by HTTP tests.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Template Formats API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/templates/TemplateFormats.html), [Asciidoctor include directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/), and [CommonMark Specification](https://commonmark.org/).
