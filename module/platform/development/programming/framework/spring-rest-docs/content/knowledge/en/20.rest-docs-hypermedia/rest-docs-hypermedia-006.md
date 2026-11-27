# Documenting Embedded Resources and Nested Links

## 1. Embedded resources and nested links in HAL

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. With hypermedia APIs, a response can contain data for the current resource, embedded resources, and links allowing clients to navigate between them. Snippets document both the payload and link structure; they are then assembled into Asciidoctor/Markdown and run in build and CI.

In HAL, two key data regions are:

- _embedded: holds resources directly embedded within the current representation.
- _links: holds navigation links at that representation level.

Example store list response:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Central Store",
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      },
      {
        "id": 12,
        "name": "East Store",
        "_links": {
          "self": {"href": "/api/stores/12"},
          "products": {"href": "/api/stores/12/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"},
    "next": {"href": "/api/stores?page=1"}
  }
}
~~~

The response has multiple levels:

| Location | Content | Example relations/links |
| --- | --- | --- |
| Root representation | Store collection | self, next |
| Each embedded store | Data for one store | id, name |
| _links of each store | Navigation from that store | self, products |

If you only document root links, the documentation skips relations inside each `_embedded.stores` element. If you only describe nested links, clients miss the collection's pagination links. You need to identify the exact data levels you want to document.

## 2. Describing payload and links separately per level

For nested HAL responses, split the work into two parts:

1. Use payload descriptors to describe embedded resources: fields, data types, and subsections.
2. Use link descriptors to describe relations at the root and on each embedded resource.

Commonly used APIs:

| API | Purpose |
| --- | --- |
| subsectionWithPath("_embedded.stores") | Describes the entire embedded region as a subsection in the fields table. |
| beneathPath("_embedded.stores[]") | Shifts the description context into each store element in the array. |
| fieldWithPath("id") | Describes a field inside the current subsection. |
| links(...) | Describes links at the operation root. |
| links(beneathPath(...), ...) | Describes links inside a payload subsection. |
| linkWithRel("products") | Selects a relation by `rel` name at the level being extracted. |

Important point: `beneathPath(...)` does not create an embedded resource and does not alter the response. It only establishes a sub-extraction context so the snippet describes the relevant portion of the payload. Similarly, link descriptors only read links already present in the response.

## 3. Preparing the Spring HATEOAS representation

The examples use Java 17+, Spring Boot 3.x, Spring MVC, Spring HATEOAS, JUnit Jupiter, and Spring REST Docs:

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

Spring Boot dependency management should manage compatible versions of Spring HATEOAS and Spring REST Docs. Projects not using a BOM need to pick versions matching the Spring Framework version in use.

A collection representation can be built with a `CollectionModel` containing `EntityModel` instances:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class StoreController {

    @GetMapping(value = "/api/stores", produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<EntityModel<Store>> listStores() {
        EntityModel<Store> first = EntityModel.of(
                new Store(11L, "Central Store"),
                linkTo(methodOn(StoreController.class).getStore(11L)).withSelfRel(),
                linkTo(methodOn(ProductController.class).listByStore(11L))
                        .withRel("products"));

        EntityModel<Store> second = EntityModel.of(
                new Store(12L, "East Store"),
                linkTo(methodOn(StoreController.class).getStore(12L)).withSelfRel(),
                linkTo(methodOn(ProductController.class).listByStore(12L))
                        .withRel("products"));

        return CollectionModel.of(List.of(first, second),
                linkTo(methodOn(StoreController.class).listStores()).withSelfRel());
    }
}
~~~

This example illustrates the concept; `Store`, `getStore(...)`, and `ProductController.listByStore(...)` must be defined in the application. You can add pagination links at the root with `withRel("next")` when a next page exists. Each `EntityModel` holds the links for its embedded store; `CollectionModel` holds the links for the collection.

For the serializer to return HAL, the endpoint needs the HAL media type and appropriate Spring HATEOAS configuration. In tests, verify the actual `Content-Type` before declaring descriptors.

## 4. Documenting embedded fields with beneathPath(...)

Suppose the response has this structure:

~~~json
{
  "_embedded": {
    "stores": [
      {"id": 11, "name": "Central Store"},
      {"id": 12, "name": "East Store"}
    ]
  }
}
~~~

You can describe each element in the array using a payload subsection extractor:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
        beneathPath("_embedded.stores[]"),
        fieldWithPath("id").description("Store ID"),
        fieldWithPath("name").description("Store name"))
~~~

`beneathPath("_embedded.stores[]")` causes the `id` and `name` descriptors to be resolved relative to each store element. As a result, the fields snippet focuses on the embedded item's structure instead of repeating the full path in every descriptor.

### Describing a subsection as a single block

If you only want to indicate that the response has an embedded region without listing every field:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
        subsectionWithPath("_embedded.stores")
                .description("List of stores embedded in the response"))
~~~

This example illustrates describing a subsection at the root; other descriptors must be added to cover the full actual response structure when using strict mode. `subsectionWithPath(...)` describes a region as a unit. It does not replace detailed examples when readers need to know the fields inside each store.

### Choosing the right description approach

| Documentation goal | Usage |
| --- | --- |
| Only indicate an embedded collection exists | `subsectionWithPath("_embedded.stores")` |
| List fields of each element | `beneathPath("_embedded.stores[]")` with `fieldWithPath(...)` |
| Describe deep fields inside an item | Use relative descriptors like `address.city` after selecting the right subsection |
| Describe the full root response | Combine root descriptors and subsections/fields matching the actual JSON structure |

## 5. Describing links at root and embedded resource levels

In the example response, the root has `self` and `next`; each store has `self` and `products`. The root links table can be declared separately:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;

links(
        linkWithRel("self").description("Store collection"),
        linkWithRel("next").optional()
                .description("Next page if more data is available"))
~~~

For links inside each embedded item, select the subsection containing the items before describing relations. Spring REST Docs provides an overload of `links(...)` accepting a `PayloadSubsectionExtractor`:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Current store"),
        linkWithRel("products").description("Products of the store"))
~~~

When called this way, `linkWithRel("self")` and `linkWithRel("products")` are looked up in the link map of each element beneath `_embedded.stores[]`, rather than the link map at the root. Consequently, relations with the same name can be described independently at both levels when the response actually contains that relation in both places.

### Do not confuse root links with embedded links

For example, the root has a `next` relation:

~~~json
{
  "_links": {
    "self": {"href": "/api/stores?page=0"},
    "next": {"href": "/api/stores?page=1"}
  },
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  }
}
~~~

If you use `links(linkWithRel("next")...)` at the root, the descriptor describes collection pagination. If you use `links(beneathPath("_embedded.stores[]"), ...)`, the descriptor describes links on each store. Picking the wrong level leads to missing relation errors or misleading documentation.

## 6. MockMvc example for embedded resources and nested links

The following test assumes the `/api/stores` endpoint returns HAL with root relations `self` and `next`, and each store has `self` and `products`. The test documents payload and links at both levels:

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
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class StoreDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentStoreCollection() throws Exception {
        mockMvc.perform(get("/api/stores")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.stores[0].id").value(11))
                .andExpect(jsonPath("$._embedded.stores[0]._links.products.href").exists())
                .andDo(document("stores-list",
                        links(
                                linkWithRel("self").description("Store collection"),
                                linkWithRel("next").optional().description("Next page")),
        links(
                beneathPath("_embedded.stores[]").withSubsectionId("stores"),
                                linkWithRel("self").description("Current store"),
                                linkWithRel("products").description("Products of the store")),
                        responseFields(
                beneathPath("_embedded.stores[]").withSubsectionId("stores"),
                                fieldWithPath("id").description("Store ID"),
                                fieldWithPath("name").description("Store name"))));
    }
}
~~~

The test uses three descriptor groups:

1. The first `links(...)` extracts relations at the root response, i.e., the stores collection.
2. `links(beneathPath("_embedded.stores[]"), ...)` extracts relations inside each embedded store.
3. `responseFields(beneathPath("_embedded.stores[]"), ...)` describes fields of each store.

The example focuses on subsection snippets. If you need to fully document root fields and `_embedded` in a strict `responseFields` table, declare the root fields or appropriate subsections matching the actual JSON. Do not assume a child descriptor set automatically covers every root field.

## 7. Multi-level nested subsections

An embedded resource may contain nested objects or collections. For example, a store contains an address:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Central Store",
        "address": {
          "city": "Ho Chi Minh City",
          "district": "District 1"
        },
        "_links": {
          "self": {"href": "/api/stores/11"}
        }
      }
    ]
  }
}
~~~

To describe fields inside `address` for each store:

~~~java
responseFields(
        beneathPath("_embedded.stores[]"),
        fieldWithPath("id").description("Store ID"),
        fieldWithPath("name").description("Store name"),
        fieldWithPath("address.city").description("City"),
        fieldWithPath("address.district").description("District"))
~~~

In this example, field paths are resolved relative to each store element. If you want to document only `address`, you can drill deeper with the corresponding extractor:

~~~java
responseFields(
        beneathPath("_embedded.stores[].address"),
        fieldWithPath("city").description("City"),
        fieldWithPath("district").description("District"))
~~~

For nested arrays, such as each store having embedded departments, clearly identify the paths and collection boundaries:

~~~text
_embedded
  └── stores[]
       └── _embedded
            └── departments[]
                 ├── id
                 └── name
~~~

Each level can be documented with its own snippet, using a subsection extractor targeting the exact region to present. This keeps field tables from turning into very long, hard-to-read lists of paths.

## 8. Distinguishing embedded resources, association links, and collection links

| Type | HAL structure | Meaning |
| --- | --- | --- |
| Embedded resource | _embedded.stores[] | Resource data placed directly inside the current response. |
| Association link | _links.products inside a store | Navigates from a store to the related products collection. |
| Collection navigation link | _links.next at root | Navigates between pages of the stores collection. |

A resource can be both embedded and have its own links. Embedded data gives clients partial information directly in the response; links allow clients to access the full representation or other relations. Do not assume an embedded object makes the object's `self` link unnecessary.

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Central Store",
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"}
  }
}
~~~

Clients can read the store name from the embedded resource, use the `self` link to retrieve the standalone store resource, or use `products` to discover the store's products. Documentation should describe these three capabilities according to the API design.

## 9. Optional, ignored, and strict/relaxed on nested links

The rules for required/optional/ignored still apply to nested link descriptors; the difference is that the extractor must point to the right level:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Current store"),
        linkWithRel("products").optional()
                .description("Products if supported by the store"))
~~~

Here `self` is required for each store; `products` may be absent. If an internal relation exists inside each embedded store and should not be included in documentation:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Current store"),
        linkWithRel("internal-audit").ignored())
~~~

If each store has many other undocumented links, consider relaxed links for that subsection. Check whether your project's Spring REST Docs version provides the corresponding overload for `relaxedLinks(PayloadSubsectionExtractor, ...)`; if not, organize tests with appropriate snippets instead of assuming every overload exists identically.

Do not use `optional` to hide a required relation missing on some items. If the contract guarantees every store has `products`, use a required descriptor so tests catch items missing the relation.

## 10. Including embedded fields and links snippets into Asciidoctor

An operation can generate multiple snippets covering different aspects. Depending on descriptors and configuration, the `stores-list` directory may contain:

~~~text
build/generated-snippets/
└── stores-list/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── links.adoc
    ├── response-fields-stores.adoc
    └── links-stores.adoc
~~~

Snippet names for subsections depend on the subsection ID/configuration declared by the project; the tree above is illustrative. Inspect the actual generated files before writing includes.

An Asciidoctor page can present them hierarchically:

~~~adoc
= Stores API

== Store list

include::{snippets}/stores-list/http-request.adoc[]
include::{snippets}/stores-list/http-response.adoc[]

=== Collection links

include::{snippets}/stores-list/links.adoc[]

=== Embedded store

include::{snippets}/stores-list/response-fields-stores.adoc[]
include::{snippets}/stores-list/links-stores.adoc[]
~~~

With the subsection ID `stores` set in the example, `response-fields-stores.adoc` and `links-stores.adoc` are generated according to the subsection identifier. Final filenames also depend on snippet type and version; check the actual output directory before using includes.

With Markdown, default snippets are usually AsciiDoc. An appropriate conversion/embedding mechanism is needed before publishing; do not assume a Markdown renderer processes `include::` directly.

## 11. Common errors when documenting embedded resources

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Subsection not found | Path in `beneathPath(...)` is wrong or differs from actual JSON | Check the response body, especially `_embedded` and collection relation names. |
| `id` descriptor does not match | Descriptor is at root instead of the item subsection | Move the extractor into `_embedded.stores[]` or use the full path matching the context. |
| `products` link not found | Link is inside each store, while descriptor reads at root | Use `links(beneathPath("_embedded.stores[]"), ...)`. |
| Root `next` missing from snippet | Confused root extractor with item subsection | Describe root links with a separate `links(...)`. |
| Field in embedded item undocumented | Strict response fields still has undeclared fields | Add field descriptors or describe the appropriate subsection. |
| An item misses a required relation | Real contract does not guarantee the relation on every item | Only use `optional` when the API allows it; otherwise, fix the response. |
| Subsection snippet filename differs from include | Subsection ID or snippet config differs from assumption | Check the output directory and adjust the include to the real name. |
| Body has embedded data but lacks `_links` | Representation did not create association links or serializer did not emit HAL links | Check `EntityModel`, `CollectionModel`, and HATEOAS configuration. |
| Media type is plain JSON | Endpoint does not return HAL or negotiation is misconfigured | Check `Accept`, `produces`, and `Content-Type`. |

When errors occur, print the actual response and determine which level the subsection/link resides at before changing descriptors. Do not switch the entire snippet to relaxed just to avoid path or relation errors.

## 12. Practice exercises

1. Create a HAL collection response with two embedded stores, each having `self` and `products`; describe fields using `beneathPath("_embedded.stores[]")`.
2. Add a root `next` link for pagination and describe it with `links(...)` at the root.
3. Describe the nested `products` link inside each store using a link subsection extractor.
4. Add an `address` object inside embedded stores; document `address.city` and `address.district`.
5. Make the `products` link optional on some stores; write tests covering both items with and without the link.
6. Include HTTP response, root links, embedded fields, and nested links into Asciidoctor; verify the documentation task in CI.

**Completion criteria:** distinguish root representation from embedded items; select the right path extractor for payloads and links; describe association links per item; do not mix pagination links with nested links; snippets and includes match the actual output.

## 13. Checklist before publishing embedded resources

- [ ] Confirmed the actual response uses the published hypermedia format and media type.
- [ ] Identified the path of the embedded collection inside `_embedded`.
- [ ] Used `beneathPath(...)` for field descriptors relative to embedded items.
- [ ] Used `subsectionWithPath(...)` when needing to describe a region as a block.
- [ ] Documented root `_links` separately from `_links` inside embedded resources.
- [ ] Used a link subsection extractor when describing relations inside each item.
- [ ] Required/optional/ignored accurately reflects the contract of each relation.
- [ ] Set a subsection ID and checked actual snippet filenames before writing includes.
- [ ] Asciidoctor/Markdown compiles after snippet-generating tests succeed.

**Key takeaway:** An embedded resource is data placed into `_embedded`; nested links are relations inside `_links` of that resource itself. Using payload subsection extractors and link subsection extractors at the proper levels allows Spring REST Docs to produce clear documentation for both the data structure and how clients navigate between nested resources.
