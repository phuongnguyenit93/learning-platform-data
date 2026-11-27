# Setting Titles, Anchors, and Links to Operations

## Learning Objectives

After this lesson, you will be able to:

- Organize AsciiDoc headings according to the API documentation structure and name operations consistently.
- Create explicit anchor IDs to link to a resource, operation, request, response, or error scenario.
- Use cross-references within the same page and xref between AsciiDoc files.
- Distinguish navigation anchors/URLs from the document identifier that Spring REST Docs uses to write snippets.
- Create a table of contents and an overview page with links to operations.
- Avoid duplicate anchors, unstable auto-generated IDs, incorrect xref paths, and broken links during builds.

## 1. Headings and Navigation in API Documentation

A REST API document typically has multiple resources, each with multiple operations. Readers move from the overview page to a resource, open an operation, and inspect the request, response, or errors. Headings and links should reflect that structure.

Example:

```text
API Guide
├── Authentication
├── Orders
│   ├── List orders
│   ├── Get an order
│   ├── Create an order
│   └── Cancel an order
└── Error responses
```

In Asciidoctor:

- Document titles use one equals sign.
- Level-one sections use two equals signs; subsequent levels add one equals sign each.
- An anchor defines a target location to link to.
- A cross-reference takes readers to another anchor.
- An xref between files takes readers to another document.
- An external link opens an external resource such as an OAuth reference or support page.

Do not use headings merely to make text larger. Heading levels must accurately express content relationships so the table of contents and outline remain meaningful.

## 2. Distinguishing Three Types of Identifiers

Spring REST Docs and Asciidoctor both use identifier names, but each serves a different purpose.

| Identifier | Example | Where It Is Used |
| --- | --- | --- |
| Document identifier | orders-get | document("orders-get", ...); determines the generated snippet directory |
| Anchor ID | orders-get or orders-get-request | Links to a location in AsciiDoc/HTML |
| Target file/URL | orders/get.adoc or orders.html | Xref between pages or published documentation URL |

You can give a document identifier and an anchor ID the same string, but they do not link together automatically. The `generated-snippets/orders-get/` directory does not automatically create an `orders-get` anchor ID in HTML. Authors must place an appropriate anchor or heading in AsciiDoc.

Test example:

```java
andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Order ID")
    )
))
```

In AsciiDoc:

```asciidoc
[[orders-get]]
== Get order information

include::{snippets}/orders-get/http-request.adoc[]
```

The anchor orders-get is a navigation link; the document identifier orders-get is the snippet directory name. They are only related because the writer intentionally used the same name.

## 3. AsciiDoc Heading Structure

A typical AsciiDoc file has a document title at the top:

```asciidoc
= Orders API
:toc:
:toclevels: 3

== Overview

== Orders

=== Get order information

=== Create order

=== Cancel order
```

Meaning:

- = Orders API is the document title.
- == Overview and == Orders are level-one sections.
- The operations are subsections.
- toc enables the table of contents.
- toclevels limits the heading depth shown in the table of contents.

For large documents, standardize a convention: the overview file owns the main title and resource navigation; operation files are included or rendered as subpages following the predefined heading structure.

Do not skip heading levels just to achieve a desired font size. If an operation belongs under a resource, use a heading level that reflects that relationship.

## 4. Setting Explicit Anchor IDs

Asciidoctor can auto-generate IDs from headings, but explicit anchors let you control links and keep IDs stable when headings are edited.

### 4.1. Anchor Before a Section

Place the anchor right before the heading:

```asciidoc
[[orders]]
== Orders

[[orders-get]]
=== Get order information

[[orders-create]]
=== Create order
```

From anywhere in the same document, you can reference:

```asciidoc
<<orders-get,Get order information>>
```

Anchors must be unique within the scope of the rendered document. Do not copy the ID orders-get to two different operation sections on the same page.

### 4.2. Anchors for Subsections Inside an Operation

You can place anchors for the request, response, or error scenario:

```asciidoc
[[orders-get-request]]
==== Request

include::{snippets}/orders-get/http-request.adoc[]

[[orders-get-response]]
==== Response

include::{snippets}/orders-get/http-response.adoc[]

[[orders-get-not-found]]
==== Order not found

include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Detailed anchors are useful when an operation page is long, another page needs to link directly to a response/error, or a use-case index needs to bring readers straight to a specific example.

You do not need to put an anchor on every small heading. Only set an explicit ID when the location is likely to be referenced or needs a stable URL.

## 5. Anchor Naming Conventions

IDs should use lowercase letters, hyphens, and express the resource/action:

| Anchor ID | Location |
| --- | --- |
| authentication | Authentication section |
| orders | Orders endpoint group |
| orders-list | List operation |
| orders-get | Read-one-order operation |
| orders-get-request | Request of the read-order operation |
| orders-get-response | Success response |
| orders-get-not-found | 404 response |
| orders-create-validation-error | Validation error when creating an order |

Rules:

1. Use one consistent pattern across the entire module.
2. Prefix the ID with the resource to avoid collisions between groups.
3. Use suffixes describing the content part such as request, response, not-found, validation-error.
4. Do not use spaces, Vietnamese diacritics, or arbitrary characters in IDs.
5. Avoid putting build versions or test sequence numbers in anchors if they are not part of the navigation contract.

Anchor IDs become part of the URL when published as HTML. Changing an ID already shared with consumers can break bookmarks or other pages. Treat public IDs as a managed interface.

## 6. Linking Within the Same Page

Use a cross-reference to link to an anchor in the same document:

```asciidoc
<<orders-get,Get order information>>
```

You can also link without writing a custom label:

```asciidoc
<<orders-get>>
```

Or use the xref syntax:

```asciidoc
xref:orders-get[]
```

Prefer meaningful labels over just displaying the ID. For example:

```asciidoc
After creating successfully, the client receives the new order ID.
To read the resource again, see <<orders-get,Get order information>>.
```

Do not use full URLs for internal same-page links. Anchor references are shorter and work across different publishing base paths.

## 7. Xref Between AsciiDoc Files

When documentation is split across multiple files, use xref with a relative path:

```asciidoc
xref:orders/get.adoc[Details of get order operation]
```

Link to a specific anchor in another file:

```asciidoc
xref:orders/get.adoc#orders-get-response[Response of get order operation]
```

Example layout:

```text
docs/
├── index.adoc
├── authentication.adoc
└── orders/
    ├── index.adoc
    ├── list.adoc
    ├── get.adoc
    └── create.adoc
```

From index.adoc:

```asciidoc
== Resources

* xref:orders/index.adoc[Orders]
* xref:authentication.adoc[Authentication]
```

From orders/index.adoc:

```asciidoc
== Orders

* xref:list.adoc[List orders]
* xref:get.adoc#orders-get[Get order information]
* xref:create.adoc[Create order]
```

Cross-file xrefs work within the context of Asciidoctor and the built site. Do not point to `.adoc` files via an assumed web URL if the publishing pipeline uses different HTML names; use xref so the processor rewrites links according to configuration.

## 8. Embedding Operations and Snippets While Keeping Anchors

An operation may have multiple snippets. Anchors should be placed in the author-managed AsciiDoc part, with snippets included underneath.

```asciidoc
[[orders-get]]
=== Get order information

Returns an order by its identifier.

[[orders-get-parameters]]
==== Parameters

include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/query-parameters.adoc[]

[[orders-get-request]]
==== Request

include::{snippets}/orders-get/request-headers.adoc[]
include::{snippets}/orders-get/http-request.adoc[]

[[orders-get-response]]
==== Response

include::{snippets}/orders-get/response-headers.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
```

The overview page can point straight to the operation:

```asciidoc
== Orders

* xref:orders/get.adoc#orders-get[Get order information]
```

Anchors do not generate snippets and snippets do not automatically create anchors. Asciidoctor creates links to locations explicitly marked in the document.

## 9. Linking from an Operation to Security, Errors, and Other Resources

API documentation often has relationships between operations:

- An operation requires the authentication mechanism described under Authentication.
- POST creates a resource and returns Location pointing to the new resource.
- DELETE may return 204 with no response body.
- Operations share a common error format.

Example:

```asciidoc
[[orders-create]]
=== Create order

Endpoint requires permission to create orders. See <<authentication,Security and authentication>>.

After creating successfully, the API returns a Location header pointing to the new resource.
Clients can use <<orders-get,Get order information>> to read the resource.

When the payload is invalid, see <<errors-validation,Validation errors>>.
```

Since Location is the runtime URI of the resource, do not confuse that header with an Asciidoctor anchor. The Location header belongs to the HTTP response; xref/anchors are navigation inside the documentation. They are not the same address.

## 10. External Links

Use the link macro for resources outside the documentation set:

```asciidoc
link:https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/[Spring REST Docs Reference]
```

Example:

```asciidoc
For the Bearer token model, also see
link:https://www.rfc-editor.org/rfc/rfc6750[RFC 6750 - Bearer Token Usage].
```

External links should point to official/trusted sources, have labels describing the destination, avoid URLs containing tracking/session parameters, and be checked periodically.

Do not use xref for external web URLs. Use xref for documents within the Asciidoctor set; use link for external URLs.

## 11. Auto-Generated IDs from Headings and When to Avoid Depending on Them

Asciidoctor can generate IDs from section titles. Attributes such as idprefix and idseparator affect how auto-generated IDs are formed:

```asciidoc
:idprefix:
:idseparator: -

== Orders

=== Get order information
```

Auto-generated IDs can change when a heading is translated or edited, when idprefix/idseparator attributes change, or when duplicate headings appear and the processor has to disambiguate them.

If a section is linked from multiple pages or already shared with consumers, place an explicit anchor. Use auto-generated IDs only for internal headings unlikely to be referenced and not requiring stability guarantees.

The sectanchors and sectlinks attributes can assist in displaying links to section headings depending on the theme/output. They do not replace deliberately choosing IDs for important operations. Inspect the HTML output to see how the theme renders anchors.

## 12. Table of Contents and Operation Navigation Pages

For long documents, enable the TOC and limit its depth:

```asciidoc
= REST API Guide
:toc:
:toclevels: 3
:sectanchors:

[[overview]]
== Overview

[[authentication]]
== Authentication

[[orders]]
== Orders

[[orders-list]]
=== List orders

[[orders-get]]
=== Get order information

[[orders-create]]
=== Create order
```

The TOC helps navigate by headings. Explicit anchors allow other pages and prose to point to operations. The two mechanisms complement each other.

If a page has many subfiles, a resource index page can serve as a directory:

```asciidoc
= Orders

Operations:

* xref:list.adoc[List orders]
* xref:get.adoc#orders-get[Get order information]
* xref:create.adoc[Create order]

Shared errors:

* xref:../errors.adoc#errors-validation[Validation errors]
```

Check relative paths from the file containing the xref. Paths are calculated from the current AsciiDoc file, not always from the project root.

## 13. Anchor Rules Across the Entire Module

A convention you can apply:

| Content type | Suggested pattern | Example |
| --- | --- | --- |
| Resource | resource-name | orders |
| Operation | resource-action | orders-get |
| Request section | resource-action-request | orders-get-request |
| Response section | resource-action-response | orders-get-response |
| Error scenario | resource-action-error-name | orders-get-not-found |
| Shared concept | concept-name | authentication, pagination |

Document identifiers can follow a similar pattern:

| Test exchange | Document identifier |
| --- | --- |
| GET order succeeds | orders-get |
| GET order not found | orders-get-not-found |
| POST order succeeds | orders-create |
| POST order validation error | orders-create-validation-error |

Do not reuse the same ID for multiple anchors on one page. If two files are merged into one page via include, verify that their anchors remain unique after merging.

## 14. Verifying Links and Anchors in the Build

A broken link may not fail an HTTP test. It belongs to the documentation authoring step and must be caught during the build.

Workflow:

1. Run documentation tests to generate snippets.
2. Run Asciidoctor on all documentation entrypoints.
3. Configure invalid include/xref references to fail the build.
4. Check HTML: anchor IDs exist, are unique, and are in the right positions.
5. Check internal and external links according to project policy.
6. Open the rendered page, test the TOC and important links.

Gradle example:

```groovy
def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

The configuration above ensures the Asciidoctor task runs after tests and receives snippet output. It does not automatically check every external link or anchor uniqueness; a dedicated link checker/HTML validator can be added to the pipeline if the project requires it.

### 14.1. Manual Inspection Checklist

- Are anchor IDs in xrefs spelled correctly and pointing to the right file?
- Are there duplicate anchors after including subfiles?
- If a section heading changed, was the old anchor preserved?
- Are relative xrefs calculated from the exact source file?
- Do external links have clear labels and accurate URLs?
- Does the TOC display the right depth?
- Does a link to an operation take readers to the operation heading rather than the top of the page?

## 15. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Xref does not jump to the right section | Wrong anchor ID or the section lacks that anchor | Check the ID in AsciiDoc/HTML output |
| Renaming a heading breaks old bookmarks | Relying on auto-generated IDs from headings | Set explicit anchors and keep IDs stable |
| Two operations receive the same anchor | Copy/pasted ID without changing resource/action | Use the resource-action convention and check for duplicates |
| Cross-file link not found | Relative path calculated from the wrong location | Calculate the path from the file containing xref and re-run Asciidoctor |
| Xref points to an `.adoc` file not matching published URLs | Using fixed URLs instead of Asciidoctor cross-references | Use xref so the processor handles output targets |
| Snippet included properly but operation link is missing | Confusing document identifier with anchor | Create a separate anchor in AsciiDoc |
| TOC is too long | toclevels is larger than needed for the structure | Reduce toclevels and adjust heading hierarchy |
| Anchor duplicated after including partials | Multiple partials use the same ID | Namespace IDs by resource/operation |
| External link no longer works | Source documentation changed URL or redirected | Use official sources and check periodically |

## 16. Headings, Anchors, and Links Checklist

- [ ] Clear document title and heading hierarchy exist.
- [ ] Important operations have explicit anchor IDs.
- [ ] Anchor IDs use lowercase, hyphens, and are unique within the page.
- [ ] REST Docs document identifiers are not confused with anchor IDs.
- [ ] Same-page links use cross-references to the right anchor.
- [ ] Cross-file links use xref with accurate relative paths.
- [ ] External URLs use the link macro with clear descriptive labels.
- [ ] TOC depth fits the structure.
- [ ] Anchors remain stable when editing heading wording.
- [ ] Anchors/links checked after including subfiles.
- [ ] Documentation build fails when required includes are missing.

## 17. Practice Exercise

The Orders API documentation has three operations:

- GET /api/orders/{id}: reads an order.
- POST /api/orders: creates an order.
- DELETE /api/orders/{id}: cancels an order.

Perform the following:

1. Create the Orders API document title and enable TOC with an appropriate depth.
2. Place anchors orders-get, orders-create, and orders-delete for each operation.
3. Inside the GET operation, place separate anchors for the request, response, and 404 error.
4. Write an index page with xrefs to the three operations.
5. From the POST operation, link to the GET operation for reading the newly created resource.
6. Link to the shared authentication section from all three operations.
7. Use an external link to official documentation related to authorization.
8. Render with Asciidoctor, inspect HTML anchors, and test clicking links from the index page.

**Self-check question:** If a test uses document("orders-get"), does Asciidoctor automatically create a #orders-get link? No. The document identifier only determines where snippets are written. Anchors on the page must be created separately, such as [[orders-get]], before they can be referenced by xref or cross-reference.

## Conclusion

Headings, anchors, and links determine how readers navigate REST API documentation. Use headings to express structure, explicit anchors for operations and key sections, cross-references for locations on the same page, xrefs for other AsciiDoc documents, and links for external URLs. Distinguish anchor IDs from Spring REST Docs document identifiers: one navigates the page, the other groups snippets of an HTTP exchange. Keep ID conventions stable, check uniqueness after includes, and verify links on the rendered HTML. When the build catches broken includes/xrefs and the team reviews key paths, integrators can go from the overview directly to the right operation, request, response, or error without getting lost in the documentation.
