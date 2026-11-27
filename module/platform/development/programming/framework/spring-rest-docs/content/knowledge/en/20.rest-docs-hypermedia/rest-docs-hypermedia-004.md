# Required, Optional, and Ignored Links

## 1. Why distinguish hypermedia link types?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. In a hypermedia-driven API, responses do not only contain data; they also provide links so clients can discover resources and next actions. Spring REST Docs produces a snippet describing the relation, `href` address, and meaning of each link; the snippet is then included into Asciidoctor/Markdown and built in CI.

An illustrative HAL response:

~~~json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "_links": {
    "self": {"href": "/api/products/42"},
    "reviews": {"href": "/api/products/42/reviews"},
    "next": {"href": "/api/products?page=2"}
  }
}
~~~

Not every relation appears in every response. `self` is typically always present on an identified resource; `next` only appears if there is a next page; `reviews` may depend on whether the product publishes reviews. If the documentation describes every link as though it were required, tests will fail on valid responses that omit optional links.

Spring REST Docs lets you express three intents:

- **Required:** the link must be present in the documented operation.
- **Optional:** the link may be present or absent according to the contract.
- **Ignored:** the link is intentionally omitted when describing and validating the link set in the snippet.

These intents are expressed via `LinkDescriptor`, usually created with `linkWithRel(...)`, and passed into `links(...)` or `relaxedLinks(...)`.

## 2. Preparing descriptors for hypermedia links

Common static imports:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
~~~

A basic descriptor:

~~~java
linkWithRel("self").description("Current resource")
~~~

`linkWithRel("self")` selects the link based on the `self` relation; `description(...)` provides the content included in the snippet. Descriptors are passed to the `links` snippet:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self")
                                .description("Current product"),
                        linkWithRel("reviews")
                                .description("Product reviews"))));
~~~

This test assumes the actual response includes both `self` and `reviews` relations, and that MockMvc is integrated with Spring REST Docs and a HAL serializer. If a required relation is missing, snippet generation can fail. Therefore, you should clearly decide whether a link is required or optional based on the API contract.

## 3. Required links: default descriptors

When creating a descriptor with `linkWithRel(...)` without calling `optional()`, Spring REST Docs treats the relation as required for the documented operation.

~~~java
links(
        linkWithRel("self")
                .description("Current product"),
        linkWithRel("reviews")
                .description("List of reviews"))
~~~

In the default strict mode, Spring REST Docs checks that the documented relations are present in the response. If the response does not contain `reviews`, the `links` snippet cannot be generated as expected and the documentation test reports an error. This behavior is helpful when the API guarantees that every product exposes this relation.

Example:

~~~java
@Test
void productHasSelfAndReviewsLinks() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.reviews.href").exists())
            .andDo(document("products-get",
                    links(
                            linkWithRel("self")
                                    .description("Current product"),
                            linkWithRel("reviews")
                                    .description("Product reviews"))));
}
~~~

The two JSONPath matchers verify the response body before documenting; the descriptors proceed to generate the links table. Descriptors do not replace other business assertions such as status or payload.

### When should you use required links?

Choose a required descriptor when the API guarantees the relation is always present in this type of response, clients rely on the relation to understand the resource or next action, and the absence of the relation indicates a contract bug. That way CI detects if a controller accidentally deletes, renames, or stops emitting the relation.

## 4. Optional links with optional()

A relation may be absent in a valid response. For instance, `next` only appears when the current page is not the last page; `prev` does not appear on the first page. Mark the descriptor as optional:

~~~java
links(
        linkWithRel("self")
                .description("Current page"),
        linkWithRel("next")
                .optional()
                .description("Next page if more data is available"))
~~~

`optional()` tells Spring REST Docs that the descriptor might not be found in the operation. If the link appears, the descriptor still documents it; if the link is absent, missing that relation will not fail the snippet solely due to its absence.

### Pagination example

The first page has `self` and `next`, but no `prev`:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=1"}
  }
}
~~~

The last page has `self` and `prev`, but no `next`:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=5"},
    "prev": {"href": "/api/products?page=4"}
  }
}
~~~

A single descriptor set shared across both states:

~~~java
links(
        linkWithRel("self").description("Current page"),
        linkWithRel("prev").optional().description("Previous page"),
        linkWithRel("next").optional().description("Next page"))
~~~

If the API also has `first` and `last`, you can add them according to their appearance rules. Do not mark `self` as optional if the contract specifies that the link must always be present; doing so would mask bugs.

### optional() does not mean skipping the link when it appears

`optional()` only relaxes the **presence** requirement. When the relation appears in the response, it is still recognized and included in the links table according to its descriptor. Optional does not turn the link into a hidden element, nor does it mean a description is unnecessary.

## 5. Ignored links: recognized but omitted from documentation

Sometimes a response contains internal links or relations outside the scope of public documentation. You can declare an ignored descriptor:

~~~java
links(
        linkWithRel("self")
                .description("Current resource"),
        linkWithRel("internal-audit")
                .ignored())
~~~

`ignored()` marks a relation as intentionally omitted during documentation. This link is not presented as a regularly documented relation; the goal is to let the tool know its presence was accounted for, rather than treating it as an unintentionally undocumented relation.

Example response with an extra internal link:

~~~json
{
  "id": 42,
  "_links": {
    "self": {"href": "/api/products/42"},
    "internal-audit": {"href": "/internal/audit/products/42"}
  }
}
~~~

If the public documentation only needs `self`, you can configure:

~~~java
links(
        linkWithRel("self").description("Current product"),
        linkWithRel("internal-audit").ignored())
~~~

Do not use `ignored()` merely to make a test pass when an important public relation has not been documented yet. If clients need to know about the `reviews` link, describe that relation using `description(...)` so documentation readers understand its meaning.

### Distinguishing ignored and optional

| Configuration | Can the relation be absent? | When the relation is present |
| --- | --- | --- |
| Default descriptor | No, the relation is expected to be present | Documented in the snippet |
| optional() | Yes | Still documented if present |
| ignored() | Not required to appear | Omitted from description/link-set check |

The two options serve different intents. `optional()` says "it may or may not be present, but if present here is the link to document"; `ignored()` says "this relation is outside the scope of this snippet's description".

## 6. Strict links and relaxed links

Beyond the state of individual descriptors, Spring REST Docs also provides two ways to control the relation set: strict and relaxed.

### Strict links with links(...)

~~~java
links(
        linkWithRel("self").description("Current product"),
        linkWithRel("reviews").description("Product reviews"))
~~~

In strict mode, links present in the response must be handled by corresponding descriptors. If the response contains an additional undocumented relation, Spring REST Docs can report an error to prevent silently omitting part of the hypermedia contract.

For example, the response has `self`, `reviews`, and `seller`, while the descriptors only declare two links:

~~~json
{
  "_links": {
    "self": {"href": "/api/products/42"},
    "reviews": {"href": "/api/products/42/reviews"},
    "seller": {"href": "/api/sellers/7"}
  }
}
~~~

In strict mode, add a description for `seller` if it is a public relation:

~~~java
links(
        linkWithRel("self").description("Current product"),
        linkWithRel("reviews").description("Reviews"),
        linkWithRel("seller").description("Product seller"))
~~~

Or mark it `ignored` if the relation is outside the documented scope and intentionally omitted. Avoid switching to relaxed mode just to hide a new relation that the team has not reviewed yet.

### Relaxed links with relaxedLinks(...)

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

mockMvc.perform(get("/api/products/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                relaxedLinks(
                        linkWithRel("self")
                                .description("Current product"))));
~~~

`relaxedLinks(...)` allows the response to contain relations not described by descriptors. The snippet still records the declared links, but the test no longer requires all links in the response to be listed.

This is a suitable choice when the payload has many secondary relations, the documentation focuses on a subset, or the endpoint returns extended links depending on permissions, features, or state. On the downside, relaxed links reduces contract change enforcement: the API could add a relation without the documentation test raising a warning.

### Quick comparison

| Mode | Described relations | Present but undocumented relations |
| --- | --- | --- |
| links(...) strict | Must be declared, except ignored descriptors | Can cause the test to fail |
| relaxedLinks(...) | Only chosen relations need to be described | Allowed to exist without descriptors |
| optional() in strict | Still a described relation | Only allows that specific relation to be absent |
| ignored() in strict | Excluded from the description | Intentionally skipped by the tool |

Strict/relaxed is a snippet-level choice; optional/ignored is a per-descriptor status. Do not confuse these two levels.

## 7. MockMvc example for required and optional links

Suppose a product list endpoint always returns `self`, while `prev` and `next` vary by page. The test uses Spring Boot, Spring HATEOAS, and Spring REST Docs:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class ProductPageDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentFirstPage() throws Exception {
        mockMvc.perform(get("/api/products?page=0&size=2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.next.href").exists())
                .andDo(document("products-page-first",
                        links(
                                linkWithRel("self").description("Current page"),
                                linkWithRel("prev").optional().description("Previous page if available"),
                                linkWithRel("next").optional().description("Next page if available"))));
    }

    @Test
    void documentLastPage() throws Exception {
        mockMvc.perform(get("/api/products?page=5&size=2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next").doesNotExist())
                .andDo(document("products-page-last",
                        links(
                                linkWithRel("self").description("Current page"),
                                linkWithRel("prev").optional().description("Previous page if available"),
                                linkWithRel("next").optional().description("Next page if available"))));
    }
}
~~~

The URLs and page numbers are illustrative data; the real endpoint must return the corresponding relations. The last test confirms `next` does not exist on the last page, while the descriptor marks it optional so both valid states share the same description rules.

If the application does not use Spring Boot auto-configuration for REST Docs, replace the setup with `RestDocumentationExtension` and `documentationConfiguration(...)` on the MockMvc builder.

## 8. Including the links snippet into documentation

When calling `document("products-page-first", links(...))`, Spring REST Docs writes the `links.adoc` snippet under the corresponding identifier. An Asciidoctor page can include it:

~~~adoc
== First page

include::{snippets}/products-page-first/http-response.adoc[]
include::{snippets}/products-page-first/links.adoc[]

== Last page

include::{snippets}/products-page-last/http-response.adoc[]
include::{snippets}/products-page-last/links.adoc[]
~~~

`{snippets}` must point to the build's output directory, typically `build/generated-snippets/` for Gradle or `target/generated-snippets/` for Maven. If the documentation uses Markdown, a mechanism to convert or embed AsciiDoc snippets is needed as designed by the project.

You should include both HTTP response and `links.adoc` on the page. HTTP response shows readers the representation structure, while the links table explains the relations and meanings that clients should rely on.

## 9. Common errors and solutions

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Test reports missing `self` | Strict descriptor requires the link, but the response lacks it | Check representation, media type, serializer, and link builder; mark optional only if contract allows absence. |
| Last page fails due to missing `next` | `next` was declared as required | Use `optional()` if the last page validly omits the `next` link. |
| Test reports undocumented relation | Response contains a new relation not declared in strict descriptors | Describe the relation or mark it `ignored` when intentionally omitted. |
| Important relation missing from table | Descriptor is marked `ignored` or uses wrong `rel` | Remove `ignored` and use `linkWithRel(...)` with the right relation. |
| Using relaxed causes test to miss unexpected links | Relaxed snippet allows undocumented links | Switch to strict if full contract enforcement is needed. |
| Link present in JSON but unrecognized by extractor | Media type or hypermedia format is unsupported/unconfigured | Confirm Content-Type, HAL structure, and hypermedia configuration. |
| Links snippet not generated | Test stopped before `document` or did not call links snippet | Check test report, `andDo(document(...))`, and handler. |
| Asciidoctor missing `links.adoc` | Identifier or output path mismatch | Cross-check `document(...)`, snippet directory, and `{snippets}`. |

When an error occurs, inspect the actual response before relaxing descriptors. A missing relation might be a controller bug; a validly absent relation needs `optional()`; a relation outside documentation scope can use `ignored()` or a relaxed snippet depending on intent.

## 10. Practice exercises

1. Create a product endpoint with `self` and `reviews` relations; write a strict test with both descriptors.
2. Create paginated responses for the first and last pages; verify `next`/`prev` change and mark `optional` properly.
3. Add an `internal-audit` relation; use `ignored()` when public documentation does not describe this relation and explain why.
4. Let a new relation appear without adding a descriptor; observe how strict links detects the undocumented link.
5. Switch the test to `relaxedLinks(...)` and identify which changes will no longer be checked.
6. Compile Asciidoctor containing both `http-response.adoc` and `links.adoc` for first/last pages; chain the documentation task after the test step in CI.

**Completion criteria:** correctly distinguish required, optional, and ignored links; understand strict links versus relaxed links; use descriptors matching the contract; have tests for both present and absent link states; snippets are included at the right paths.

## 11. Checklist before publishing hypermedia links

- [ ] Identify which relations are required by the API contract.
- [ ] Use default descriptors for links that must be present.
- [ ] Use `optional()` only when a link may be absent in valid responses.
- [ ] Use `ignored()` when a relation has been considered but intentionally omitted from descriptions.
- [ ] Choose strict `links(...)` when controlling the relation set; only choose `relaxedLinks(...)` when documentation intentionally describes a subset.
- [ ] Assertions confirm status, media type, and important links.
- [ ] Describe relations in language easy for clients to understand.
- [ ] Verify `links.adoc`, identifier, and include paths.
- [ ] Build/CI generates fresh snippets before compiling and publishing documentation.

**Key takeaway:** A required link is a guarantee of the response; `optional()` allows a link to be absent while still documenting it if present; `ignored()` intentionally excludes a relation from description; `relaxedLinks(...)` permits other undocumented links. Choosing the right validation level ensures Spring REST Docs accurately reflects the hypermedia contract clients rely on.
