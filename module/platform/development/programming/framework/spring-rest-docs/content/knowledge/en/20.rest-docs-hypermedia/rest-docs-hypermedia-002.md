# links and linkWithRel to Describe Relations

## 1. Hypermedia links in the API contract

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. In addition to status, headers, and payload, a hypermedia-driven API exposes links so clients can discover resources and next actions. Spring REST Docs produces a separate snippet for links; the snippet is included into Asciidoctor/Markdown and built in CI alongside request/response examples.

Example HAL response:

~~~json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "_links": {
    "self": {"href": "https://api.example.com/products/42"},
    "product": {"href": "https://api.example.com/products/42"},
    "reviews": {"href": "https://api.example.com/products/42/reviews"}
  }
}
~~~

The relations `self`, `product`, and `reviews` describe the current resource and related resources. Clients can use the relation together with `href` to navigate instead of constructing URLs from implicit path conventions.

Spring REST Docs provides the following API group:

- links(...): creates a snippet describing the hypermedia links of an operation.
- linkWithRel("..."): identifies a link by its relation (rel).
- linkWithHref("..."): identifies a link by its target URI when needed.
- description(...): explains the meaning of the relation to clients.

After this lesson, you will be able to describe relations such as `self`, `reviews`, and `next` with `links(...)` and `linkWithRel(...)`, validate required/optional links, handle undocumented links, and include snippets into your documentation.

## 2. How do links(...) and linkWithRel(...) work?

In a MockMvc test, hypermedia descriptors are typically passed to `document(...)`:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;

mockMvc.perform(get("/api/products/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Current product"),
                        linkWithRel("reviews").description("List of reviews"))));
~~~

| Component | Role |
| --- | --- |
| links(...) | Creates a snippet descriptor to validate and record links in an HTTP operation. |
| linkWithRel("reviews") | Selects the link by the relation with value `reviews`. |
| description(...) | Records the meaning of the relation in the snippet table. |
| document("products-get", ...) | Attaches the links snippet to the operation with identifier `products-get`. |

With a HAL response, the relation is typically the key inside `_links`, while `href` is the navigation target. The descriptor `linkWithRel("reviews")` identifies the link by `rel`; there is no need to hardcode the target URL if the URL can vary by host, environment, or resource ID.

Documentation generation flow:

~~~text
MockMvc request
      |
      v
HTTP response containing HAL _links
      |
      v
andExpect(status / body / headers)
      |
      v
andDo(document("products-get", links(linkWithRel(...))))
      |
      v
Spring REST Docs detects hypermedia format
      |
      v
links.adoc in generated-snippets
      |
      v
Asciidoctor / Markdown
~~~

`links(...)` does not generate links in the response. The controller or representation model must emit the proper links; REST Docs only verifies and documents the links actually present in the response.

## 3. Preparing the project and hypermedia representation

The examples use Java 17+, Spring Boot 3.x, Spring MVC, Spring HATEOAS, JUnit Jupiter, and Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management should manage compatible versions of Spring HATEOAS and Spring REST Docs. Projects not using a BOM need to explicitly choose versions matching the Spring Framework version in use.

An endpoint can return `EntityModel<Product>`:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class ProductController {

    @GetMapping(value = "/api/products/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<Product> getProduct(@PathVariable long id) {
        Product product = new Product(id, "Mechanical keyboard");
        return EntityModel.of(product,
                linkTo(methodOn(ProductController.class).getProduct(id)).withSelfRel(),
                linkTo(methodOn(ReviewController.class).getReviews(id)).withRel("reviews"));
    }
}
~~~

The snippet above illustrates how a controller builds a representation and links; `Product`, `ReviewController`, and `getReviews(...)` are types that need to be defined in the application. `EntityModel` combines entity data and links; the HAL serializer converts them into the `_links` structure.

When testing with MockMvc, use the actual Spring MVC/HATEOAS configuration so the response has the corresponding media type and serializer. Common setup in a Spring Boot application:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class ProductDocumentationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

This is a concise setup: `SpringBootTest` loads the application configuration, `AutoConfigureMockMvc` provides `MockMvc`, and `AutoConfigureRestDocs` integrates Spring REST Docs via Boot configuration. If using `RestDocumentationExtension` together with manual `webAppContextSetup(...)`, apply `documentationConfiguration(restDocumentation)` on the builder.

## 4. Describing links by relation with linkWithRel

A test can assert the status and content type, then describe the relations:

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
class ProductDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentProductLinks() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andDo(document("products-get",
                        links(
                                linkWithRel("self").description("Current product"),
                                linkWithRel("reviews").description("Reviews for the product"))));
    }
}
~~~

The endpoint must actually return the `self` and `reviews` relations; if `reviews` is missing from the response, the default descriptor will report a missing relation. When the target URI is part of the contract that needs verification, you can add a corresponding JSONPath assertion.

### Reading the links snippet

The generated snippet has the default name `links.adoc` under the identifier. The links table is built from the declared relations and descriptions:

| Rel | Description |
| --- | --- |
| self | Current product |
| reviews | Reviews for the product |

`description(...)` provides human-readable content for API consumers; `rel` expresses the relation type, while the target URL is extracted from the response.

## 5. Using linkWithRel for common relations

Relations reflect navigation semantics, not simply URL names:

~~~java
links(
        linkWithRel("self").description("Current resource"),
        linkWithRel("profile").description("Resource structure description"),
        linkWithRel("search").description("Search resources"),
        linkWithRel("next").description("Next page of results"),
        linkWithRel("prev").description("Previous page of results"),
        linkWithRel("create").description("Create a related resource"))
~~~

This example is only suitable when the actual response contains all of the above relations. Each API can choose its own relations based on its contract and media type. Standard relations like `self`, `next`, and `prev` have widely understood meanings; custom relations like `reviews` or `create` should be described consistently across the API.

### Pagination links

A list response might contain:

~~~json
{
  "_embedded": {
    "products": [
      {"id": 41, "name": "Mouse"},
      {"id": 42, "name": "Keyboard"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=1"},
    "first": {"href": "/api/products?page=0"},
    "prev": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=2"},
    "last": {"href": "/api/products?page=8"}
  }
}
~~~

The test can describe each relation:

~~~java
.andDo(document("products-list",
        links(
                linkWithRel("self").description("Current page"),
                linkWithRel("first").description("First page"),
                linkWithRel("prev").description("Previous page"),
                linkWithRel("next").description("Next page"),
                linkWithRel("last").description("Last page"))))
~~~

The snippet above chains onto `perform(...)` and the matchers. On the first or last page, `prev` or `next` may be absent; document their optionality accurately instead of assuming every page contains every link.

## 6. Required links, optional links, and ignored links

Spring REST Docs validates the links declared with `links(...)`. There are different ways to express this:

### Required relations

~~~java
links(
        linkWithRel("self").description("Current resource"),
        linkWithRel("reviews").description("Reviews"))
~~~

Default descriptors expect the documented relations to appear in the operation. If the API accidentally drops `reviews`, the documentation test can fail and report that the relation was not found. This protects the contract of required links.

### Relations that may be absent

~~~java
links(
        linkWithRel("self").description("Current resource"),
        linkWithRel("next")
                .optional()
                .description("Next page if more data is available"))
~~~

`optional()` is suitable when a relation may be absent in certain valid responses, such as `next` on the last page. When the link is present, it is still documented; when absent, the descriptor does not fail the test merely because the optional relation is missing.

### Relations recognized but excluded from the table

~~~java
links(
        linkWithRel("self").description("Current resource"),
        linkWithRel("internal-audit").ignored())
~~~

`ignored()` is used when a relation may appear but is intentionally excluded from the description table. Only ignore a link when there is a clear reason; if the relation belongs to the public API and clients need to know about it, document it.

### Relaxed links

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

.andDo(document("products-get",
        relaxedLinks(
                linkWithRel("self").description("Current product"))))
~~~

`relaxedLinks(...)` is suitable when documenting only a subset of links in a large response. Relations that are not described will not be treated as errors. In exchange, the test no longer strictly validates all links; if an unexpected new relation appears, the documentation may not warn you.

| Declaration | Link must be present? | Undocumented links |
| --- | --- | --- |
| linkWithRel("x") | Yes | May fail strict test |
| linkWithRel("x").optional() | No | Other relations remain under strict mode |
| linkWithRel("x").ignored() | Not required in table | Recognized and omitted from description |
| relaxedLinks(...) | Per descriptor | Allows undocumented links |

Choose the mode based on the API contract. For public endpoints, strict links ensure the documentation accurately reflects the exact set of relations clients are permitted to use.

## 7. Using linkWithHref when identifying by target URL

Usually, the relation is the most stable and meaningful way to identify a link:

~~~java
linkWithRel("reviews").description("Reviews for the product")
~~~

If you need to select a link by its `href` itself, Spring REST Docs also provides `linkWithHref(...)`:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithHref;

links(
        linkWithHref("/api/products/42")
                .description("Product detail page"))
~~~

This approach is useful when a response contains target links that must be identified by a specific URI. However, URLs can change by host, port, version, or data; using relations generally produces documentation that is less environment-dependent. Avoid hardcoding absolute addresses if the operation runs across multiple environments.

## 8. Hypermedia formats and link detection

Spring REST Docs uses a hypermedia link extraction mechanism appropriate for the response format, such as HAL. With HAL, link data resides in `_links`; the relation is the key name and `href` is the target address. Spring HATEOAS can also produce other representations depending on configuration and media type.

Some diagnostic notes:

- Check that the response Content-Type matches the hypermedia media type declared by the endpoint, e.g. `application/hal+json`, not merely `application/json`.
- Check that the actual body has a link structure the extractor can recognize.
- If the API uses a custom hypermedia format, configure an appropriate extractor instead of assuming the HAL extractor reads every structure.
- If the serializer does not emit `_links`, `linkWithRel(...)` cannot find the relation merely because the controller attached links to an object that was not properly serialized.

Example matchers for HAL:

~~~java
.andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
.andExpect(jsonPath("$._links.self.href").exists())
~~~

These are two matchers chained after `perform(...)`. The JSONPath assertion confirms that the link is actually serialized in the response; `links(...)` continues to validate and generate the relation description table.

## 9. Including the links snippet into Asciidoctor

Suppose the test records the operation with identifier `products-get`. Spring REST Docs generates the `links.adoc` snippet in the corresponding directory. An Asciidoctor page can reference it:

~~~adoc
= Products API

== View product

include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

=== Hypermedia relations

include::{snippets}/products-get/links.adoc[]
~~~

`{snippets}` must point to the build's snippet output directory, typically `build/generated-snippets/` for Gradle or `target/generated-snippets/` for Maven, unless the project configures a different path.

If the response has multiple relations:

~~~adoc
== Product list

include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/links.adoc[]
~~~

The `links.adoc` snippet is a relation table; the HTTP response snippet remains useful so readers can see the full data and link representation. Both parts complement each other: the response illustrates the payload, while the links table explains the relations from a client's perspective.

With Markdown, the default snippets are usually AsciiDoc. You must convert or embed the content according to the build mechanism chosen by the project; do not assume a Markdown renderer can directly process every `include::` syntax.

## 10. Common errors when describing hypermedia links

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `links.adoc` not generated | Test did not call `links(...)`, handler did not run, or test stopped before the document step | Check test report, `andDo(document(...))`, and identifier. |
| Relation `self` not found | Response lacks `_links.self`, wrong media type, or serializer does not emit HAL | Check body, Content-Type, HATEOAS converter, and representation model. |
| Missing `next` relation on last page | Descriptor treats an optional link as required | Use `optional()` if the link is allowed to be absent per contract. |
| Test reports undocumented link | Response contains a new relation not declared in strict descriptor | Add descriptor or use relaxed links when documenting only a subset. |
| Link present in response but missing from table | Descriptor uses wrong `rel` or is marked `ignored()` | Cross-check relation names in `_links` and descriptor. |
| URI in snippet differs from expected | Host/base URI or link builder produces a different URL by environment | Check URI configuration, proxy/base path, and link construction. |
| Correct `href` but wrong relation | Link was attached with the wrong relation in the representation | Fix `withRel(...)`/`withSelfRel()` or update doc expectations per actual contract. |
| Asciidoctor reports missing `links.adoc` | Include uses wrong identifier/snippet name or test did not generate the file | Check actual `generated-snippets` and `{snippets}` path. |
| Standalone test does not recognize HAL links | Required converter/ObjectMapper/HATEOAS support not registered | Use web application context or configure appropriate converters. |

## 11. Practice exercises

1. Create an endpoint returning `EntityModel<Product>` with relations `self` and `reviews`; write a MockMvc test using `links(linkWithRel(...))`.
2. Add a paginated list endpoint with `first`, `prev`, `next`, `last`. Mark relations that may be absent with `optional()` according to the page state.
3. Add a `profile` relation pointing to schema documentation; explain the meaning of the relation in the descriptor.
4. Try adding a relation to the response without adding a descriptor; observe how strict links catches the undocumented link.
5. Separate out a test using `relaxedLinks(...)` and compare it with strict mode. Decide which mode fits a public endpoint.
6. Include `links.adoc` alongside `http-response.adoc` in Asciidoctor, run tests before compiling, and verify the include.

**Completion criteria:** know how to build links in a representation, verify the response contains hypermedia, describe relations with `linkWithRel`, handle required/optional/ignored links, understand strict and relaxed links, and compile snippets with the correct paths.

## 12. Checklist before publishing the links table

- [ ] The endpoint actually returns a hypermedia representation with the proper media type.
- [ ] Relations declared in descriptors exist in the response or are reasonably marked optional.
- [ ] Each relation has a description explaining its meaning to clients.
- [ ] `ignored()` is only applied to relations that do not need to be published; relaxed links are used intentionally.
- [ ] `linkWithRel(...)` aligns with the contract; use `linkWithHref(...)` only when identification by URI is necessary.
- [ ] Assertions confirm status/content type and important links.
- [ ] The identifier and `links.adoc` file match the include path.
- [ ] Build/CI runs tests to generate snippets before compiling and publishing documentation.

**Key takeaway:** `links(...)` creates a snippet describing the hypermedia links of an HTTP operation; `linkWithRel(...)` selects the relation that clients use to understand and navigate the API. Combining descriptors, assertions, and the `links.adoc` snippet allows documentation to express not only the returned data, but also how clients discover subsequent resources.
