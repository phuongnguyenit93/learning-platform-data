# Distinguishing Formatting Capabilities of Asciidoctor and Markdown

## Lesson Objectives

Spring REST Docs generates snippets from HTTP tests. Development teams can author documentation using **AsciiDoc and Asciidoctor** or **Markdown** depending on their project's documentation ecosystem. Both formats support headings, paragraphs, lists, tables, and code blocks, yet they differ in document authoring capabilities, extended syntax, and how snippets are brought into pages.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into build and CI workflows.

After this lesson, you will be able to:

- Distinguish Markdown, Markdown variants, and AsciiDoc.
- Understand Asciidoctor's role in processing AsciiDoc documents.
- Compare includes, attributes, admonitions, cross-references, tables, and code blocks.
- Choose a snippet format suited to your rendering tool and publishing platform.
- Avoid using Asciidoctor syntax inside plain Markdown without a matching processor.
- Design a test → snippet → assemble → render → publish pipeline.
- Keep REST Docs content test-verified while leveraging each document format's presentation features.

## 1. What Are Markdown, AsciiDoc, and Asciidoctor?

**Markdown** is a family of lightweight text markup syntaxes. Common standards and variants include CommonMark, GitHub Flavored Markdown (GFM), and Markdown extensions specific to each static site generator. Therefore, not every Markdown platform supports the exact same syntax.

**AsciiDoc** is a document markup language with richer syntax for technical documentation and books. Files typically carry the **.adoc** or **.asciidoc** extension.

**Asciidoctor** is the processor used to convert AsciiDoc into HTML, DocBook, and other supported formats through its tooling ecosystem. Asciidoctor understands features such as include directives, document attributes, cross-references, admonition blocks, source blocks, and many other document structures.

You can picture it as:

~~~text
Markdown source -- Markdown renderer / site generator --> HTML or site

AsciiDoc source -- Asciidoctor --------------------------> HTML / DocBook
                         |
                         +-- extensions / converters ----> other formats
~~~

A `.md` file does not run through Asciidoctor automatically just because both contain headings and code blocks. Likewise, a `.adoc` file does not become Markdown simply by changing its extension.

## 2. Basic Syntax That Looks Similar

Both formats can express familiar elements:

| Element | Typical Markdown | Typical AsciiDoc |
| --- | --- | --- |
| Level 1 heading | # Title | = Title |
| Level 2 heading | ## Section | == Section |
| Bold | **content** | **content** |
| Italic | *content* | __content__ |
| Inline code | Surrounded by backticks | Surrounded by backticks |
| Unordered list | - item | * item |
| Ordered list | 1. item | . item |
| Link | [Spring](https://spring.io) | https://spring.io[Spring] |
| Code block | Fenced code block | Source block or literal block |

Example of the same short guide.

**Markdown**

~~~~markdown
# Orders API

API for creating and looking up orders.

## Create order

Send a **POST** request to create an order.

~~~http
POST /api/orders
Content-Type: application/json
~~~
~~~~

**AsciiDoc**

~~~~asciidoc
= Orders API

API for creating and looking up orders.

== Create order

Send a *POST* request to create an order.

[source,http]
----
POST /api/orders
Content-Type: application/json
----
~~~~

Basic syntax can be converted relatively easily, but advanced documentation features do not have a one-to-one mapping.

## 3. Comparing Key Formatting Capabilities

| Capability | AsciiDoc/Asciidoctor | Markdown |
| --- | --- | --- |
| Headings, paragraphs, lists | Yes | Yes |
| Fenced/source code blocks | Source blocks and highlight options | Available in many flavors; highlighting varies by renderer |
| Tables | Multiple table styles and cell layouts | Pipe tables common in GFM; core CommonMark defines no pipe tables |
| File includes | Has include directive | No standard file include syntax in CommonMark |
| Document attributes/variables | Has attributes like :toc: and {attribute} | No unified variable mechanism in standard Markdown |
| Internal cross-references | Has anchors and xref | Typically uses heading anchors/links; anchor rules vary by renderer |
| Admonitions | Has NOTE, TIP, WARNING blocks | Typically requires blockquotes, HTML, or extensions |
| Conditional content | Has conditional directives by attribute | Depends on plugins/generators |
| Footnotes | Yes | Depends on flavor/extensions |
| Bibliography/index | Supported through AsciiDoc ecosystem | Typically relies on plugins or generators |
| Multi-page/book | Supports long document structures | Possible via site generators; Markdown itself defines no site structure |

The differences matter as REST API documentation grows. AsciiDoc is often convenient when snippet includes, shared attributes, cross-references, and book structure are needed. Markdown is often convenient when the project already uses GitHub, GitLab, a wiki, or a Markdown-based static site generator.

## 4. Including Snippets: The Most Common Difference

Spring REST Docs generates snippets using the default templates for your version and project configuration. With AsciiDoc, a doc page can include snippets via:

~~~asciidoc
== HTTP request

include::{snippets}/orders-create/http-request.adoc[]

== Request fields

include::{snippets}/orders-create/request-fields.adoc[]

== HTTP response

include::{snippets}/orders-create/http-response.adoc[]

== Response fields

include::{snippets}/orders-create/response-fields.adoc[]
~~~

The `{snippets}` attribute is typically configured in the build to point to the snippets directory. Asciidoctor processes includes when rendering documentation; this is not plain Markdown syntax.

For Markdown, there is no universal file include directive. Options include:

1. Use the plugin/include directive of the running static site generator.
2. Generate snippets using Markdown templates if supported by your REST Docs version, then use build-time assembly to insert fragments into pages.
3. Convert docs/snippets into an appropriate format via a verified build step.
4. Use Asciidoctor as the final processor if AsciiDoc's include and structural features are needed.

Never leave `include::{snippets}/...[]` inside `.md` expecting CommonMark or every Markdown renderer to read the file automatically. A renderer may display that line verbatim, ignore it, or process it according to a custom extension.

## 5. Attributes vs. Markdown Variables/Templates

AsciiDoc has **document attributes**. For example:

~~~asciidoc
:doctype: book
:toc: left
:sectnums:
:snippets: build/generated-snippets

include::{snippets}/orders-get/http-response.adoc[]
~~~

Documents can reference attributes via `{snippets}` or pass attributes from a build script/command line.

Standard Markdown has no unified variable mechanism. Some tools support front matter or template variables, for example:

~~~yaml
---
title: Orders API
description: Documentation for order management endpoints
---
~~~

Front matter is typically metadata for a static site generator; it is not a required part of CommonMark and does not automatically create shared variables across all platforms.

If a Markdown project needs variables such as `baseUrl`, `version`, or `snippetsDir`, select the generator's specific mechanism or inject values during the assembly step. Document the generator/version clearly in build docs so others can reproduce the build.

## 6. Tables: Layout Flexibility and Renderer Limits

### 6.1. Markdown Tables

GFM supports easy-to-write pipe tables:

~~~markdown
| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Customer ID |
| description | String | Order description |
~~~

Pipe tables are not part of core CommonMark syntax. If a Markdown renderer lacks a table extension, tables may render as paragraphs or plain text.

When custom templates generate Markdown tables:

- Escape pipes in cell content.
- Keep column counts consistent.
- Move long multiline content into paragraphs below.
- Keep code spans and HTML aligned with renderer rules.
- Inspect tables after rendering, not just in source files.

### 6.2. AsciiDoc Tables

AsciiDoc supports tables with flexible cell layouts and options:

~~~asciidoc
[cols="1,1,3", options="header"]
|===
|Path |Type |Description

|customerId
|Number
|Customer ID

|description
|String
|Order description
|===
~~~

AsciiDoc tables can be a better fit for multi-column tables, complex cells, or docs needing fine-grained layout control. However, richer syntax also requires authors to understand how the parser handles delimiters and nested blocks.

## 7. Admonitions and Callout Content

AsciiDoc has dedicated admonition syntax:

~~~asciidoc
[IMPORTANT]
====
Never include real access tokens in published snippets.
====

[TIP]
====
Use dedicated test fixtures for cookie and token values.
====
~~~

In Markdown, blockquotes can be used:

~~~markdown
> **Important**
>
> Never include real access tokens in published snippets.
~~~

Some renderers support custom admonition extensions, though rendering differs across tools. When using Markdown, choose a callout style supported by your publishing platform or stick to standard blockquotes for maximum compatibility.

## 8. Cross-References and Links Between Sections

AsciiDoc supports anchors and cross-references:

~~~asciidoc
[[create-order]]
== Create order

See also <<list-orders,List orders>>.

[[list-orders]]
== List orders
~~~

Markdown typically uses anchor links:

~~~markdown
## Create order

See also [List orders](#list-orders).

## List orders
~~~

Auto-generated heading anchors can vary across GitHub, GitLab, and static site generators. For critical links, check the actual ID after rendering or declare anchors using the platform's own mechanism.

AsciiDoc has an `xref` mechanism processed at build time, which is convenient when docs span multiple files or chapters. Markdown can achieve this with relative links, though link checking and version handling usually belong to the generator.

## 9. Code Blocks and Syntax Highlighting

Markdown typically uses fenced code blocks:

~~~~markdown
~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk());
~~~
~~~~

AsciiDoc typically uses source blocks:

~~~~asciidoc
[source,java]
----
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk());
----
~~~~

Both approaches display code cleanly. Highlighting depends on the renderer, highlighter configuration, and recognized language tag. When code contains long fences or matching delimiter sequences, choose a longer outer delimiter so the block does not close prematurely.

With REST Docs, code samples typically come from HTTP snippets such as `http-request` or `http-response`; there is no need to copy requests/responses into manual code blocks if snippets already provide full content.

## 10. Choosing a Format for Spring REST Docs

There is no single right choice for every project. Choose based on publishing needs and existing build capabilities:

| Criterion | Favors AsciiDoc/Asciidoctor | Favors Markdown |
| --- | --- | --- |
| Direct snippet includes | Need built-in include directive | Have generator/plugin include or build assembly ready |
| Long multi-chapter docs | Need TOC, attributes, xref, admonitions | Site generator already manages navigation and links |
| Publishing platform | Existing system supports AsciiDoc/Asciidoctor | Git hosting, docs site, or wiki prefers Markdown |
| REST Docs templates | Use existing AsciiDoc templates | REST Docs version/Markdown templates verified |
| Table/layout customization | Need complex table layouts | Simple tables, renderer supports right flavor |
| CI operation | Has Asciidoctor task in build | Has test → assembly → Markdown renderer |

An AsciiDoc workflow can be relatively direct:

~~~text
HTTP tests
   |
   v
Spring REST Docs snippets (.adoc)
   |
   v
AsciiDoc pages + include directives
   |
   v
Asciidoctor
   |
   v
HTML / documentation artifact
~~~

A Markdown workflow typically requires an assembly step or plugin:

~~~text
HTTP tests
   |
   v
Spring REST Docs snippets (Markdown template or converted)
   |
   v
Markdown include plugin / build-time assembly
   |
   v
Markdown site generator
   |
   v
HTML / documentation artifact
~~~

Verify which template formats your REST Docs version supports. Never assume every version has the same Markdown API, snippet names, or file extensions.

## 11. Example Choice for an Operation

Suppose an order creation test has document identifier `orders-create`, along with descriptors:

~~~java
document("orders-create",
    requestFields(
        fieldWithPath("customerId")
            .description("Customer ID"),
        fieldWithPath("description")
            .description("Order description")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Order ID"),
        fieldWithPath("status")
            .description("Order status")
    )
)
~~~

If using AsciiDoc, the page can include:

~~~asciidoc
== Create order

=== Request

include::{snippets}/orders-create/http-request.adoc[]

=== Request fields

include::{snippets}/orders-create/request-fields.adoc[]

=== Response

include::{snippets}/orders-create/http-response.adoc[]

=== Response fields

include::{snippets}/orders-create/response-fields.adoc[]
~~~

If using Markdown, build-time assembly can be chosen:

~~~text
build/generated-snippets/orders-create/
  http-request.md
  request-fields.md
  http-response.md
  response-fields.md

build/docs-markdown/orders-create.md
~~~

The assembly task must check that all four files exist, join them in order, and write UTF-8 output. If actual snippets are still `.adoc`, use Asciidoctor or a verified conversion step before assembling Markdown.

## 12. Common Conversion Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Markdown shows raw include directive | Asciidoctor directive passed to Markdown renderer | Choose Asciidoctor or a Markdown include plugin |
| Pipe table does not render | Markdown flavor lacks table extension | Use a GFM-capable renderer or switch to compatible syntax |
| Admonition loses callout styling | Markdown renderer lacks admonition extension | Use blockquotes or enable appropriate plugin |
| Broken cross-references | Auto-generated anchors differ across renderers | Verify heading IDs or declare explicit anchors |
| `{snippets}` attribute not substituted | Markdown renderer does not understand AsciiDoc attributes | Use generator config or build assembly |
| Code block has no syntax highlighting | Missing language tag/highlighter | Declare language and enable syntax highlighting |
| Include file missing in CI | Tests have not run or path differs from working dir | Wire dependencies and base paths on build directory |
| `.adoc` file renamed to `.md` fails to render | Only extension changed; syntax is still AsciiDoc | Generate Markdown templates or convert systematically |
| Content differs between local and CI | Different renderer/plugin versions or config | Pin versions and use the same build task |

## 13. Practice Exercise

Create documentation for two operations:

~~~text
POST /api/orders
GET /api/orders/{orderId}
~~~

Requirements:

1. Write MockMvc tests and use `document(...)` to generate request/response, parameter, and field snippets.
2. Build one version of the documentation in AsciiDoc, using attributes and include directives.
3. Build a Markdown version using your generator's include mechanism or build-time assembly.
4. Compare how tables, source blocks, admonitions, and cross-references render across both versions.
5. Explicitly record the REST Docs version, template format, and Markdown renderer.
6. Fail CI when required snippets are missing or internal links are invalid.
7. Cross-check request/response content between both versions to ensure no contract divergence.

**Completion criteria:** both pipelines render documentation; snippets come from the same tests; includes/attributes/cross-references work with their respective processors; field tables and HTTP exchanges do not contradict; CI validates output before publishing.

## Key Takeaways

AsciiDoc and Markdown both support basic document structure, yet differ in extensibility. **Asciidoctor** handles AsciiDoc includes, attributes, xrefs, and admonitions; Markdown depends on flavors and renderers, with no standard file include syntax in CommonMark. With Spring REST Docs, choose the snippet format and rendering tool based on your publishing platform: AsciiDoc is convenient when direct includes/attributes are needed; Markdown fits when the project has a clear generator or build assembly. Pin versions, validate fragments, and inspect post-render output to ensure documentation accurately reflects HTTP tests.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Asciidoctor Documentation](https://docs.asciidoctor.org/), [Asciidoctor Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/), [CommonMark Specification](https://commonmark.org/), and [GitHub Flavored Markdown Specification](https://github.github.com/gfm/).
