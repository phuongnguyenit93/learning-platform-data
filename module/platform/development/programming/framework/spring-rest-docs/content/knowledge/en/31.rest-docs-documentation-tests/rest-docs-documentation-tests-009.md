# Testing Hypermedia Links and Resource Relations

## 1. Goals of Hypermedia Testing

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Documentation Tests** chapter, HTTP tests both verify endpoint behavior and generate snippets for documentation. For hypermedia APIs, responses not only contain resource data but also provide link relations so clients can discover related resources or next actions.

A hypermedia test should verify:

- HTTP status and `Content-Type` match the published representation.
- The response has the expected link format, such as HAL JSON using `_links`.
- Required relations like `self` are present and point to an appropriate URI.
- Business relations like `orders`, `cancel`, or `reviews` are clearly described.
- Optional relations are marked `optional` only when the contract permits absence.
- `links(...)` descriptors match the response so `links.adoc` can be generated.

Spring REST Docs uses `LinkExtractor` to extract links from the response and `LinkDescriptor` to describe relations. In strict mode, a relation present in the response without a descriptor can fail the test; a required descriptor missing from the response can also fail the test. This mechanism catches contract drift at the hypermedia layer.

Examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. Testing principles are similar with WebTestClient and REST Assured, even though the request APIs differ.

## 2. HAL Responses and Link Relations

Example HAL response:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "https://api.example.test/products/42"},
    "orders": {"href": "https://api.example.test/products/42/orders"},
    "profile": {"href": "https://api.example.test/profiles/product"}
  }
}
```

| Component | Role |
| --- | --- |
| _links | Container holding hypermedia links in HAL |
| self | Relation pointing to the current resource itself |
| orders | Relation pointing to related orders |
| profile | Relation pointing to the representation profile description |
| href | Target URI of the link |

A relation describes a relationship or capability; `href` is the address provided by the server. Clients should locate links by relation instead of constructing URLs from IDs or internal path conventions.

## 3. Configuring Hypermedia Tests with MockMvc

### 3.1. Dependencies

Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Spring HATEOAS provides representation types and helpers for creating HAL links. Spring REST Docs provides MockMvc integration and hypermedia descriptors.

### 3.2. Illustrative Controller

```java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @GetMapping(path = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<ProductResponse> find(@PathVariable long id) {
        ProductResponse product = new ProductResponse(id, "Mechanical Keyboard");
        return EntityModel.of(product,
            linkTo(methodOn(ProductController.class).find(id)).withSelfRel(),
            linkTo(methodOn(ProductController.class).orders(id)).withRel("orders")
        );
    }

    @GetMapping("/{id}/orders")
    CollectionModel<OrderResponse> orders(@PathVariable long id) {
        return CollectionModel.empty();
    }

    record ProductResponse(long id, String name) {}
    record OrderResponse(long id) {}
}
```

The controller demonstrates two relations: `self` and `orders`. A real application should return the `orders` collection from appropriate data; test fixtures should be stable so URIs and responses are verifiable.

## 4. Writing `links(...)` Tests and Generating `links.adoc`

### 4.1. Relation Descriptors

```java
links(
    linkWithRel("self").description("Link to the current product"),
    linkWithRel("orders").description("List of orders for the product")
)
```

Static imports:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
```

### 4.2. Complete Test

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductHypermediaDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void findProductDocumentsLinks() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(containsString("/api/products/42")))
            .andExpect(jsonPath("$._links.orders.href")
                .value(containsString("/api/products/42/orders")))
            .andDo(document("products-find",
                links(
                    linkWithRel("self").description("Link to the current product"),
                    linkWithRel("orders").description("List of orders for the product")
                )
            ));
    }
}
```

JSONPath assertions check the actual links, while `links(...)` validates and records relations into snippets. Assertions verify specific URIs; descriptors ensure relations are documented.

### 4.3. Output

With operation ID `products-find`, snippets may include:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    links.adoc
```

`links.adoc` is generated when the operation declares `links(...)`. Basic HTTP snippets depend on configuration and templates.

## 5. Strict Link Validation

Strict mode helps detect:

1. A response includes a relation that the test has not described yet.
2. A descriptor declares a required relation, but the response omits it.

For example, the server unexpectedly adds a `reviews` relation. A strict test describing only `self` and `orders` can fail because `reviews` is undocumented. This signals the team to decide whether the new relation belongs to the public contract and update documentation accordingly.

Conversely, if a descriptor includes `cancel` while the response lacks that link, the test also fails. If `cancel` is only provided when an order has not shipped yet, document that condition accurately and test the corresponding response variants.

### Optional Relation

```java
links(
    linkWithRel("self").description("Current resource"),
    linkWithRel("next").description("Next page").optional()
)
```

`optional()` allows a relation to be absent; if present, it is still documented. Only mark a relation optional when the contract permits it.

### Ignored Relation

```java
links(
    linkWithRel("self").description("Current resource"),
    linkWithRel("curies").ignored()
)
```

`ignored` excludes the relation from the snippet and skips descriptor validation for it. Do not ignore business relations just to make tests pass.

### Relaxed Links

```java
relaxedLinks(
    linkWithRel("self").description("Current resource")
)
```

Relaxed mode ignores undescribed relations. It fits narrowly scoped documentation pages when other relations are documented elsewhere. Do not use relaxed mode for every operation because new relations can appear without tests prompting documentation updates.

## 6. Testing Collection and Pagination Links

A HAL collection may return `self`, `next`, `prev`, `first`, and `last`:

```json
{
  "_embedded": {
    "products": [
      {"id": 42, "name": "Keyboard"},
      {"id": 43, "name": "Mouse"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=1"},
    "first": {"href": "/api/products?page=0"},
    "prev": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=2"},
    "last": {"href": "/api/products?page=4"}
  },
  "page": {"size": 2, "number": 1, "totalElements": 10}
}
```

Descriptors:

```java
links(
    linkWithRel("self").description("Current collection page"),
    linkWithRel("first").description("First page"),
    linkWithRel("prev").description("Previous page").optional(),
    linkWithRel("next").description("Next page").optional(),
    linkWithRel("last").description("Last page")
)
```

Tests should cover the first page, middle page, and last page if link conditions differ:

| Case | Links that may be absent |
| --- | --- |
| First page | prev |
| Middle page | Usually has both prev and next |
| Last page | next |
| Empty or single-page collection | Per contract, may lack both prev and next |

Do not infer links solely from page numbers if the server has custom pagination rules. Assert actual responses via JSONPath or HAL link matchers, then use descriptors to document relations.

## 7. Custom Relations, URI Templates, and CURIEs

### Custom Relation

```java
mockMvc.perform(get("/api/orders/{id}", 9001)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists())
    .andDo(document("orders-cancellable",
        links(
            linkWithRel("self").description("Current order"),
            linkWithRel("cancel").description("Cancel order")
        )
    ));
```

Another test for a shipped order can verify `cancel` does not exist and use descriptors matching that response variant. When an API only exposes `cancel` if permitted, the link serves as a capability signal to clients.

### URI Template

```json
{
  "_links": {
    "search": {
      "href": "/api/products{?category,page,size}",
      "templated": true
    }
  }
}
```

Tests should verify `href` and the `templated` attribute if clients rely on templates. Do not treat a URI template as a fully expanded URL with variables already filled.

### CURIE

```json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://docs.example.test/rels/{rel}",
        "templated": true
      }
    ],
    "ex:reviews": {"href": "/api/products/42/reviews"}
  }
}
```

Descriptors:

```java
links(
    linkWithRel("ex:reviews").description("Product reviews"),
    linkWithRel("curies").ignored()
)
```

Tests can verify that the `ex:reviews` key exists in `_links`; `curies` explains how to expand the prefix, while `ex:reviews` is the business relation to document.

## 8. LinkExtractor and Content-Type

Spring REST Docs extracts links via a `LinkExtractor` matching the representation. Common formats have built-in extractors, such as HAL and Atom. If a response uses a custom format, default extractors may fail to recognize links.

When a test reports no links found, check:

1. The response has the right `Content-Type`, such as `application/hal+json`.
2. The HAL payload has a properly structured `_links` object.
3. The test requests the right representation via the `Accept` header.
4. Relation keys in descriptors match response keys.
5. For custom formats, an appropriate `LinkExtractor` has been configured.

Do not assume any JSON with a `links` field is HAL. `Content-Type` and representation structure determine whether an extractor can read the links.

## 9. Combining Links with Response Fields

Link descriptors validate relations; response field descriptors validate resource data:

```java
document("products-find",
    links(
        linkWithRel("self").description("Current product"),
        linkWithRel("orders").description("Related orders")
    ),
    responseFields(
        fieldWithPath("id").description("Product ID"),
        fieldWithPath("name").description("Product name")
    )
)
```

With HAL, `_links` is the hypermedia portion of the representation. Use `links(...)` for relations and field descriptors for resource data. Do not use field descriptors as a substitute for link relations.

## 10. Including `links.adoc` in Asciidoctor

Example `src/docs/asciidoc/products.adoc` file:

```asciidoc
= Products API
:toc: left

== Find Product

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== HTTP response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

The `snippets` attribute must point to the generated snippets root directory. The remainder of the path must match the operation ID. If the operation did not generate `links.adoc`, the include will fail when Asciidoctor runs.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `links.adoc` is not generated | `links(...)` not called or test did not reach `document` | Inspect test report and descriptors |
| `LinkExtractor` finds no relations | Wrong `Content-Type` or representation structure | Check HAL/Atom format and extractor |
| Strict mode reports undocumented link | Response contains an undescribed relation | Add descriptor or intentionally use relaxed |
| Test reports missing required relation | Descriptor is not optional while response lacks link | Fix server or mark optional per contract |
| Link appears in the wrong state | Controller emits links invalid for resource capability | Check business rules and response variants |
| Custom relation not recognized | Wrong relation name or CURIE prefix | Compare keys in `_links` and CURIE declaration |
| URI template treated as fixed URL | `templated` flag or variables unchecked | Assert `href` and `templated` attribute |
| Asciidoctor cannot find snippet | Wrong operation ID, `outputDir`, or include path | Check generated snippets directory |

## 12. Hands-On Exercise

Build a Catalog API returning HAL JSON:

1. `GET /api/products/{id}` returns `self`, `orders`, and `profile`.
2. `GET /api/products` returns a collection with `self`, `first`, `prev`, `next`, and `last`.
3. `GET /api/orders/{id}` returns `self` and `cancel` when the order status allows cancellation.
4. Write MockMvc tests checking status, `Content-Type`, and relation URIs.
5. Use `links(...)` to describe relations; mark `prev`/`next` optional when allowed by contract.
6. Create a strict test to detect newly added undescribed relations; use `relaxedLinks(...)` in a test focused solely on `self`.
7. Test a response containing a CURIE or URI template.
8. Include `links.adoc` and `http-response.adoc` in Asciidoctor, run a clean test pass, and build the documentation.

**Completion Criteria:** verify relations and URIs in HAL; distinguish relation from `href`; apply strict/optional/ignored/relaxed per contract; understand `LinkExtractor` and `Content-Type`; generate and include `links.adoc` from tests.

## 13. References

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [Spring HATEOAS — Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL Specification](https://stateless.group/hal_specification.html)
