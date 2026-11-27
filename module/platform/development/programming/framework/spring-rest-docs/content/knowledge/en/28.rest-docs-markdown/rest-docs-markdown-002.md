# Limitations of Markdown Compared to Asciidoctor

## 1. Objectives and Context

Spring REST Docs supports generating snippets in both Asciidoctor and Markdown formats. This allows teams to choose the format that fits their existing documentation system. However, **being able to generate Markdown snippets does not mean Markdown has the full technical documentation authoring capabilities of Asciidoctor**.

Markdown is concise, popular, and supported by many platforms. Asciidoctor provides a richer document processing system: includes, attributes, conditional directives, cross references, admonitions, book structure, and extensibility. When API documentation has many endpoints, modules, versions, and test-generated snippets, this difference directly affects how documentation is organized and built.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generating snippets for requests, responses, payloads, parameters, and headers; authoring documentation and integrating it into build/CI.

After this lesson, you will be able to distinguish the Markdown snippet format from a complete authoring system; compare includes, attributes, cross references, directives, tables, and custom templates; identify limitations when documentation scales; choose Markdown, Asciidoctor, or a hybrid approach; and design a reliable render/publish pipeline.

> Markdown is not an inferior choice in all situations. It fits well when documentation needs are moderate and the rendering platform is already clear. Asciidoctor has an advantage when structured technical documentation, includes, and large-scale reuse are required.

## 2. Three Layers in the REST Docs Workflow

Three layers should be separated:

1. **HTTP tests and REST Docs:** execute operations, assertions, and record requests/responses.
2. **Snippet templates:** format output into Asciidoctor or Markdown.
3. **Authoring/publishing system:** assemble snippets into pages, handle links, structure documentation, render HTML/PDF, and publish.

Spring REST Docs supports Markdown at the snippet layer. The tooling at the third layer depends on your team's documentation system.

Example Markdown configuration:

~~~java
documentationConfiguration(restDocumentation)
    .snippets()
    .withTemplateFormat(TemplateFormats.markdown());
~~~

Switching to Markdown does not change tests, endpoints, or HTTP semantics. It selects the template format used to render snippets.

~~~mermaid
flowchart LR
    A["HTTP tests"] --> B["REST Docs operation"]
    B --> C["Snippet templates"]
    C --> D["Markdown or Asciidoctor snippets"]
    D --> E["Authoring / include / navigation"]
    E --> F["Renderer"]
    F --> G["Publish"]
~~~

Problems usually appear at the authoring step: Markdown itself does not provide a rich, consistent set of authoring directives across renderers.

## 3. High-Level Comparison

| Capability | Markdown | Asciidoctor |
| --- | --- | --- |
| Generate snippets from Spring REST Docs | Yes, via Markdown template format | Yes, default format. |
| Basic syntax | Concise, easy to read in source | Has dedicated document structure. |
| Tables | Depends on dialect/extension | Has built-in table syntax. |
| File includes | No standard syntax in CommonMark | Has include directive. |
| Reusable attributes | No equivalent standard mechanism | Has document attributes/substitutions. |
| Conditional content | Depends on plugins/build tooling | Has conditional directives. |
| Cross references | Markdown links; anchors depend on renderer | Has anchors and cross references. |
| Admonitions | Depends on extensions/conventions | Has admonition blocks. |
| Reusable partials | Depends on static site generator/plugins | Has includes and attributes. |
| Renderer | Many dialects/platforms | Asciidoctor toolchain has clear rules. |
| Onboarding | Usually easy for those familiar with Markdown | Requires learning AsciiDoc. |
| Large technical docs | Requires choosing a supporting ecosystem | Well-suited for multi-part, reusable docs. |

These are not absolute limitations of every Markdown platform. A static site generator may add includes, admonitions, tabs, versioning, or cross references. The difference is that these features belong to a specific ecosystem, not standard Markdown syntax supported uniformly everywhere.

## 4. First Limitation: No Universal Standard for Including Snippets

REST Docs can generate these files:

~~~text
build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-body.md
    ├── response-body.md
    └── request-fields.md
~~~

With Asciidoctor, the final page can include them directly:

~~~asciidoc
= Orders API

== Create Order

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
~~~

That syntax is an Asciidoctor directive. Markdown has no equivalent standard include syntax understood by all renderers.

A Markdown page can mark where snippets should be inserted:

~~~markdown
# Orders API

## Create Order

### HTTP request

<!-- Build tool needs to assemble orders-create/http-request.md here -->

### Request fields

<!-- Build tool needs to assemble orders-create/request-fields.md here -->
~~~

Comments do not automatically read snippet files. Another tool is needed to perform the assembly:

- A static site generator that supports includes/partials.
- An include plugin for the Markdown renderer in use.
- A custom build task that reads snippets and inserts them into pages.
- A preprocessing step that produces complete Markdown before the renderer runs.

Each option has its own configuration, syntax, and limitations. When switching documentation platforms, the old system's include directives may stop working.

### 4.1. Maintenance Cost of Custom Includes

If you write your own snippet-assembly script, you must handle:

- Relative and absolute paths.
- Non-existent files or ungenerated snippets.
- Nested includes and circular includes.
- UTF-8 encoding.
- Code fences inside snippets.
- Escaping content and preserving newlines.
- Error messages clear enough for CI to identify which page is missing a snippet.

A simple string-replacement script may suffice for small docs, but easily breaks with nested partials or multiple modules. At scale, choose a widely used and battle-tested include tool.

## 5. Second Limitation: Attributes and Reusable Content

Asciidoctor supports document attributes:

~~~asciidoc
:api-version: v2
:snippets: build/generated-snippets

This documentation describes API version {api-version}.

include::{snippets}/orders-create/http-request.adoc[]
~~~

When changing the API version or snippet root, you update the attribute in one place. Plain Markdown has no equivalent document variable mechanism.

In Markdown, teams typically use front matter or static site generator configuration, template variables, includes/partials, or token-replacement scripts. Those mechanisms differ across Jekyll, Docusaurus, MkDocs, Hugo, VuePress, and Git hosting. As a result, Markdown sources can become tightly coupled to the renderer in use.

### 5.1. Reusing API Descriptions

An authentication explanation may appear on multiple pages. Asciidoctor can include the same fragment in multiple places. In Markdown, the team must choose a shared partial mechanism or duplicate content.

Copy/pasting causes content to drift. If partials are used, ensure both the renderer and local preview support that exact syntax.

## 6. Third Limitation: Conditional Content and Multiple API Versions

API documentation sometimes needs to display different content by version:

- API v1 uses field `customerName`.
- API v2 replaces it with object `customer`.
- A header only appears starting in a newer version.
- An operation is deprecated in the next release.

Asciidoctor has conditional directives and attributes:

~~~asciidoc
ifdef::api-v2[]
API v2 uses the customer object.
endif::api-v2[]

ifndef::api-v2[]
API v1 uses customerName.
endif::api-v2[]
~~~

Plain Markdown has no standard conditional directives. Templates or a static site generator can be used to produce multiple versions, but conditional logic shifts into build configuration.

With multiple versions, you need clear decisions on: whether each version has separate source pages or one conditional page; whether snippet output is separated by version; whether CI builds all versions or only the active development version; whether links between versions are checked; and how long deprecated operations are kept.

Do not share a single snippet output directory across multiple versions if a later task can overwrite an earlier task.

## 7. Fourth Limitation: Cross References and Navigation

Markdown supports links:

~~~markdown
[Authentication](authentication.md#bearer-token)
~~~

How heading anchors are generated can vary by renderer, especially for headings with Vietnamese diacritics, special characters, or duplicate headings. A link that works on one platform may not behave identically on another.

Asciidoctor lets you define anchors and reference them by ID:

~~~asciidoc
[[bearer-token]]
== Bearer token

See also <<error-responses,Error responses>>.
~~~

For large API docs, you need to maintain links from endpoints to authentication and error conventions; links from schemas to enums/data types; links between CRUD operations; links between versions; tables of contents and sidebars.

Markdown can meet these needs when supported by the renderer/site generator. Anchor generation, link validation, and sidebars usually belong to the renderer, not basic Markdown.

## 8. Fifth Limitation: Tables, Admonitions, and Document Structure

Spring REST Docs Markdown templates use tables in the **Markdown Extra** dialect. Minimal parsers supporting only CommonMark may not render tables as intended.

~~~markdown
|Path|Type|Description|
|---|---|---|
|id|Number|Order ID|
|status|String|Order status|
~~~

Asciidoctor has built-in tables and supports column configuration, spans, or complex content. In Markdown, complex tables can be hard to read in source and are not portable across renderers.

Admonitions are another example:

~~~asciidoc
[WARNING]
====
Do not send access tokens in URL query strings.
====
~~~

Plain Markdown has no unified admonition syntax. Renderers may use blockquotes, extensions, or components:

~~~markdown
> **Warning:** Do not send access tokens in URL query strings.
~~~

Blockquotes work more broadly, but their semantic role and warning styling may not be as rich as a dedicated admonition block.

## 9. Sixth Limitation: Custom Snippet Templates

Spring REST Docs uses Mustache templates to generate snippets. The Markdown format has its own templates; the Asciidoctor format also has its own templates.

If you want to add a Constraint column to `request-fields`, you must:

1. Attach metadata to descriptor attributes.
2. Override the appropriate fields template for the active format.
3. Ensure the template reads the attribute.
4. Run tests to verify the actual snippet output.
5. Verify the final renderer supports the generated table and syntax.

Do not copy Asciidoctor templates directly into Markdown because table syntax, escaping, code blocks, and inline markup differ.

Markdown templates must also conform to the dialect understood by the target renderer. If a template uses Markdown Extra while the site generator only supports CommonMark, output can break even though REST Docs generated the file successfully.

## 10. Seventh Limitation: Renderers and Portability

Markdown is often considered portable, but portability depends on dialects and extensions:

| Feature | Potential Differences |
| --- | --- |
| Tables | Parser may or may not have a table extension. |
| Heading anchors | Slug generation for Vietnamese text or duplicate headings. |
| Admonitions | Custom syntax per plugin/renderer. |
| Tabs | Custom component, not part of standard Markdown. |
| Includes | Directive specific to a static site generator. |
| Front matter | YAML metadata understood by certain systems. |
| Code highlighting | Languages/themes depend on the renderer. |
| Relative links | Base URL and paths depend on site build. |

Before choosing Markdown, lock down the renderer/site generator, version, and list of extensions. Having local preview and CI render with the same configuration helps avoid discrepancies between developer machines and the pipeline.

Asciidoctor also needs a toolchain to render, but its document model and directives are more centrally defined within the Asciidoctor toolchain.

## 11. Comparing a Real-World API Documentation Project

Suppose documentation has 80 endpoints, 5 resource groups, 3 API versions, a shared authentication fragment, and multiple response schemas.

| Need | Plain Markdown | Markdown + Site Generator | Asciidoctor |
| --- | --- | --- | --- |
| Generate snippets from REST Docs | Yes | Yes | Yes |
| Automatically assemble snippets | Needs custom build | Possible via partials | Has include |
| Version/snippet root variables | Needs templates/build | Available per generator | Has document attributes |
| Conditional content | Needs preprocessing | Possible via templates/plugins | Has directives |
| Reuse auth/error fragments | Copy or custom mechanism | Has partials | Has includes |
| Large navigation | Manual | Managed by site generator | Has book/TOC structure via toolchain |
| Consistent renderer | Not guaranteed automatically | Must pin generator/plugins | Pin Asciidoctor toolchain |
| Portability | Depends on dialect | Depends on generator | Depends on Asciidoctor toolchain |

Markdown remains viable if the team already has a stable site generator, includes/partials, versioning, and a link checker. If not, the total cost of assembling these features yourself can outweigh the benefit of concise source syntax.

## 12. When Should You Choose Markdown?

Markdown is a good fit when:

- The project already uses Markdown as its standard.
- The Git hosting/static site platform has a well-defined renderer.
- Documentation is straightforward with minimal nested includes.
- There is little need for conditional content or multi-version books.
- Contributors are familiar with Markdown and need easy source reviews.
- A reliable plugin/build task is already available to assemble snippets.

Try a vertical slice first: one request/response endpoint, one fields table, one cross link, one custom template, and one rendered page in CI. If that loop is simple, you can scale it up.

## 13. When Should You Choose Asciidoctor?

Asciidoctor is usually a better fit when:

- Documentation has many chapters, endpoints, and reusable fragments.
- Snippets need to be included directly from the output directory.
- Attributes are needed to reuse API versions, base URLs, or snippet paths.
- Content is conditional by version/edition.
- Cross references with stable IDs, admonitions, or book structures are needed.
- The team wants a unified documentation toolchain instead of stitching together multiple Markdown plugins.

Asciidoctor has richer syntax, though the team must learn and maintain its toolchain. Do not switch formats just because Asciidoctor has more features if your current documentation is simple and the Markdown workflow is already working well.

## 14. Hybrid Models

A team may use REST Docs Markdown snippets and build the main reference docs in a Markdown system, or use Asciidoctor snippets in a separate workflow. Only do this when the pipeline has a clear format contract at each step.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B["REST Docs snippets"]
    B --> C{"Selected output format"}
    C -->|Markdown| D["Markdown snippets"]
    C -->|Asciidoctor| E["Asciidoctor snippets"]
    D --> F["Markdown site generator"]
    E --> G["Asciidoctor build"]
    F --> H["Published API docs"]
    G --> H
~~~

Do not generate both formats just as a fallback if nobody maintains both outputs. The two formats can drift due to custom templates and different renderers. If both are needed in parallel, the same test source must be the source of truth and CI must build both.

## 15. Integrating Format Choice into CI

CI must verify not only that tests pass, but also that documentation actually renders properly:

1. Run HTTP tests to generate snippets.
2. Verify the output directory and identifiers.
3. Assemble snippets into pages using the chosen tool.
4. Render documentation with pinned toolchain versions.
5. Run a link checker and check for required snippets.
6. Review diffs of generated output.
7. Only publish after all steps succeed.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Assertions pass?"}
    B -->|No| X["Fail CI"]
    B -->|Yes| C["Generate REST Docs snippets"]
    C --> D["Assemble pages"]
    D --> E["Render Markdown or Asciidoctor"]
    E --> F["Check links, includes and missing snippets"]
    F --> G{"All checks pass?"}
    G -->|No| X
    G -->|Yes| H["Review and publish"]
~~~

Pin the versions of REST Docs, the renderer/site generator, extensions, and template overrides. When a Markdown plugin upgrade changes anchor/table/include behavior, CI should catch it via rendering and link checking.

### 15.1. Minimum Verification Matrix

| Check | Markdown pipeline | Asciidoctor pipeline |
| --- | --- | --- |
| HTTP tests pass | Required | Required |
| Snippet files exist | Required | Required |
| Include/partial resolution | Per generator/plugin | Asciidoctor include processor |
| Table rendering | Verify Markdown dialect | Verify Asciidoc tables |
| Cross links | Site link checker | Appropriate link validation |
| Custom templates | Correct Markdown format ID | Correct Asciidoctor format ID |
| UTF-8 | Required | Required |
| Publish gate | After render passes | After render passes |

## 16. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Markdown snippets generated successfully but page is empty | Missing include/file assembly step | Configure plugin or build task. |
| Fields table breaks when deployed | Renderer does not support Markdown Extra | Lock dialect and enable table extension. |
| Local links work but production links break | Different base URL/relative paths | Pin site config, run link checker. |
| Shared content drifts out of sync | Copy/paste or inconsistent partials | Standardize on a single partial mechanism. |
| Old API version content appears | No clear version strategy | Separate sources or use generator/directives. |
| Warning block renders as plain quote | Renderer lacks admonition extension | Use supported syntax or clear blockquote. |
| Unstable Vietnamese anchors | Slug depends on renderer | Set manual anchors or stable IDs. |
| Markdown templates differ from Asciidoctor | Template format/dialect differs | Maintain separate templates and test output. |
| CI differs from developer machine | Renderer/plugin/locale not pinned | Pin toolchain and use the same command. |
| Switching to Asciidoctor breaks links | Link/anchor syntax differs from Markdown | Migrate with validation and review. |

## 17. Practice Exercise

An API module has 20 endpoints, 2 versions, a shared authentication fragment, request/response field tables, and multiple cross links.

Steps to perform:

1. Configure one REST Docs endpoint to generate Markdown snippets and one endpoint to generate Asciidoctor snippets.
2. Assemble each type into a test documentation page.
3. For Markdown, use a site generator/include plugin and render field tables.
4. For Asciidoctor, use attributes for snippet root/version and direct includes.
5. Create a shared authentication fragment; compare reuse approaches.
6. Add conditional content by API version and check cross links.
7. Render both pipelines in CI, run a link checker, and check for missing snippets.
8. Record configuration costs, plugin/build steps, and reviewability to choose a format for the module.

**Completion criteria:** can explain the difference between a snippet format and an authoring system; identify practical limitations of Markdown; choose a renderer/extensions; assemble snippets reliably; and demonstrate correct CI rendering.

## References

- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor — Document Attributes](https://docs.asciidoctor.org/asciidoc/latest/attributes/document-attributes/)
- [CommonMark Specification](https://commonmark.org/)
- [Markdown Extra](https://michelf.ca/projects/php-markdown/extra/)
