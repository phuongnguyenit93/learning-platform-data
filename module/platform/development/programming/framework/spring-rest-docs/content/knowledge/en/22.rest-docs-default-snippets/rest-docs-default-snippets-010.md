# links and Hypermedia Snippets

## 1. Hypermedia in REST APIs

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests not only record requests and responses but can also verify navigation links returned by the server. In a hypermedia-driven API, the response contains resource data along with link relations indicating where the client can navigate next or which actions it can perform.

Spring REST Docs provides the links(...) descriptor to document link relations in responses. When a test records an operation with document(...) and passes link descriptors, REST Docs generates the links.adoc snippet.

HAL JSON example:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "https://api.example.test/products/42"},
    "orders": {"href": "https://api.example.test/products/42/orders"}
  }
}
```

In this example, self is the relation pointing to the current resource; orders leads to the list of related orders; href is the target URI provided by the server; _links is where HAL places links in the JSON representation.

Link relations and hrefs have different meanings. A relation describes a relationship or affordance; href is the address for the client to navigate to. Clients should read relations rather than constructing URLs from hardcoded path conventions.

## 2. The links.adoc Snippet

### 2.1. Basic Descriptors

Use linkWithRel(...) to identify a relation and description(...) to explain it:

```java
links(
    linkWithRel("self")
        .description("Link to the current product"),
    linkWithRel("orders")
        .description("List of orders for the product")
)
```

The snippet is generated under the operation folder, for example:

```text
build/generated-snippets/products-find/links.adoc
```

The link table typically displays the relation, description, and URI/template extracted from the response. Readers learn which links the API provides without manually reading the entire HAL payload.

### 2.2. Standard Relations and Custom Relations

| Relation | Common Meaning |
| --- | --- |
| self | Current resource |
| next | Next page in a collection |
| prev / previous | Previous page |
| first | First page |
| last | Last page |
| item | An item in a collection |
| collection | Collection containing the resource |
| create | Link to a resource creation operation if the API uses this relation |

APIs can also use domain-specific custom relations, such as orders, cancel, approve, or download. Name relations consistently and accurately describe the action the client can perform. Do not infer the meaning of a relation solely from its URL.

## 3. HAL Example with MockMvc

### 3.1. Sample Response

Suppose an endpoint returns product details along with two relations:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "/api/products/42"},
    "orders": {"href": "/api/products/42/orders"}
  }
}
```

### 3.2. Test and Link Descriptors

Example using Spring MVC, MockMvc, and REST Docs:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductHypermediaDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-find",
                links(
                    linkWithRel("self")
                        .description("Link to the current product"),
                    linkWithRel("orders")
                        .description("List of orders for the product")
                )
            ));
    }
}
```

Commonly used static imports:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
```

The example uses MediaTypes.HAL_JSON to request a HAL representation. The controller must actually return the right content type and corresponding link structure; if the response does not contain a valid HAL structure, link extraction can fail.

### 3.3. Output Result

With operation ID products-find, the snippet structure can include:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    links.adoc
```

Basic HTTP snippets are generated with the operation; links.adoc is added when the test declares links(...) descriptors. The subdirectory comes from the operation ID, while the root directory comes from REST Docs/Spring Boot or outputDir configuration.

## 4. Optional, Ignored, and Relaxed Links

### 4.1. Optional Links

A relation may not appear in every response. For example, only in-stock products have a purchase link:

```java
links(
    linkWithRel("self").description("Current product"),
    linkWithRel("purchase")
        .description("Purchase product")
        .optional()
)
```

optional() indicates that the relation is allowed to be absent. If the API requires the link to be present in every response, do not mark it optional; the test needs to detect when the server omits a required link.

### 4.2. Ignored Links

A HAL response may contain infrastructure relations such as curies or links that the current documentation page does not need to display. Use ignored() to exclude that relation from the table:

```java
links(
    linkWithRel("self").description("Current product"),
    linkWithRel("curies").ignored()
)
```

Ignored differs from optional: optional allows a link to be absent while still documenting it when present; ignored removes the link from the snippet and skips documentation checks for that relation.

### 4.3. Relaxed Links

In strict mode, a relation present in the response without a descriptor can fail the test. This helps detect when the server adds or changes links not yet mentioned in documentation.

If a test only wants to document a subset of links, use relaxedLinks(...):

```java
relaxedLinks(
    linkWithRel("self")
        .description("Current product")
)
```

relaxedLinks(...) ignores undocumented relations. Use it for narrow-scoped documentation or when other links are documented elsewhere; avoid using it by default for every operation because the API could change links without tests warning you.

## 5. URI Templates and CURIEs

### 5.1. URI Templates

A link can contain a URI template:

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

Clients need to know this is a templated link and substitute the appropriate variables rather than calling the raw string as a complete URL. In documentation, preserve the template marker and explain variable meanings if necessary.

### 5.2. CURIEs in HAL

HAL can declare CURIEs to shorten custom relations:

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
    "self": {"href": "/api/products/42"},
    "ex:reviews": {"href": "/api/products/42/reviews"}
  }
}
```

The ex:reviews relation has prefix ex, declared in the curies CURIE. Custom relations can be documented as:

```java
links(
    linkWithRel("self").description("Current product"),
    linkWithRel("ex:reviews").description("Product reviews"),
    linkWithRel("curies").ignored()
)
```

CURIE defines how to expand the relation name; the ex:reviews link is the relation tied to viewing reviews.

## 6. Hypermedia Formats and LinkExtractor

Spring REST Docs extracts links from responses using a LinkExtractor matching the hypermedia format. Common configurations include HAL and Atom. If the response does not use a format recognized by the extractor, the link snippet may not be generated properly.

Points to check:

- Response Content-Type matches the representation, e.g., application/hal+json for HAL JSON.
- JSON has the standard link structure, e.g., HAL uses _links.
- The test uses the right hypermedia module/API and extractor for the format in use.
- Relation names in descriptors match the relations returned by the server.
- Links may be templated, optional, or organized under CURIEs; document those traits accurately.

If the application uses a custom format, configure a matching LinkExtractor for REST Docs rather than assuming the HAL extractor can read any JSON containing a links field.

## 7. Combining Link Snippets with Payload Fields

Link snippets describe navigation, whereas payload field snippets describe resource data. Detailed documentation may need both:

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

With HAL, _links is the link section of the representation. Use link descriptors to document relations and field descriptors for resource data; do not treat href URLs as ordinary business fields.

## 8. Including links.adoc in Asciidoctor

In src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Find product

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== Response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

The snippets attribute must point to the snippet root directory. The path after it must match the operation ID. If tests use a custom outputDir, update the attribute in the build.

Do not include links.adoc for operations that have not declared links(...) or whose response lacks matching links. If an included file does not exist, Asciidoctor will fail when compiling the documentation.

## 9. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| links.adoc not generated | Operation did not call links(...) or test did not reach document. | Check test report and link descriptors. |
| Link extractor finds no links | Wrong Content-Type, invalid HAL structure, or unsuitable extractor. | Inspect response representation and LinkExtractor. |
| Strict mode reports undocumented link | Response has an undeclared relation. | Add descriptor, ignore intentionally, or use relaxedLinks when appropriate. |
| Test reports missing required relation | Descriptor is not optional while response lacks the link. | Fix server or mark optional if contract permits. |
| Custom relation not recognized | Wrong relation name or confused CURIE prefix. | Check keys in _links and CURIE declaration. |
| URL template treated as a fixed URL | Ignoring templated property or failing to explain variables. | Preserve URI template and describe how clients fill variables. |
| Asciidoctor cannot find links.adoc | Wrong operation ID, outputDir, or include path. | Verify actual file under generated snippets. |
| Payload fields and links mixed up | Used field descriptors instead of hypermedia descriptors. | Use links(...) for relations, field descriptors for resource data. |

## 10. Hands-on Exercise

Create a Catalog API returning HAL JSON:

1. GET /api/products/{id} returns product info and self, orders links.
2. GET /api/products returns a collection with self, next, prev links when applicable.
3. Add a custom relation ex:reviews along with CURIE ex.
4. Write MockMvc tests and use links(...) to document the relations.
5. Mark next optional on the last page; mark curies ignored if it does not need to be displayed.
6. Use a strict test to detect an undocumented new relation; use relaxedLinks in a test focused solely on self.
7. Include links.adoc and http-response.adoc in Asciidoctor, run clean test, and build the documentation.

**Completion criteria:** distinguish relations from hrefs; explain HAL _links, URI templates, and CURIEs; generate links.adoc using descriptors; properly use optional/ignored/relaxed; documentation is assembled from snippets generated by tests.

## 11. References

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [IANA — Link Relations](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
