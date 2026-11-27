# Reusing link descriptors

## 1. Why reuse link descriptors?

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests record responses and the hypermedia links provided by the server. Many resources share familiar relations such as self, profile, collection, or next. Repeatedly declaring relation descriptions in every test makes documentation hard to maintain and prone to inconsistency.

Spring REST Docs uses LinkDescriptor to document links. Descriptors are passed to links(...) to generate the links.adoc snippet and verify the relations present in the response. You can organize shared relations into factory methods, then append specific relations for each resource or operation.

HAL example:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "/api/products/42"},
    "profile": {"href": "/api/profiles/product"},
    "orders": {"href": "/api/products/42/orders"}
  }
}
```

A relation describes a relationship or capability; href is the target URI provided by the server. Clients should rely on relations to discover needed capabilities rather than manually constructing URLs from a hardcoded path convention.

After this lesson, you will be able to create shared LinkDescriptors, combine shared relations with specific relations, handle optional/ignored/relaxed links, and keep strict validation to detect new or missing relations.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. With WebTestClient or REST Assured, the HTTP calls differ, but hypermedia descriptor helpers can still be organized and shared.

## 2. LinkDescriptor and links(...)

Basic descriptors:

```java
links(
    linkWithRel("self")
        .description("Link to the current resource"),
    linkWithRel("profile")
        .description("Description of the resource structure"),
    linkWithRel("orders")
        .description("List of orders for the product")
)
```

linkWithRel(...) creates a descriptor for a relation. description(...) explains the meaning of the relation to clients. links(...) adds the descriptors to the operation documentation, generates links.adoc, and verifies the response against the descriptors.

Some common relations:

| Relation | Meaning |
| --- | --- |
| self | The current resource |
| profile | Description of the representation structure |
| collection | Collection containing the resource |
| item | An item within a collection |
| next / prev | Next page / previous page |
| first / last | First page / last page |

APIs can also use domain-specific custom relations such as orders, customer, cancel, approve, or download. Descriptions should reflect the actual action; do not infer a relation's meaning from the URL alone.

## 3. Creating a factory for shared relations

If multiple resources share self and profile with the same meaning, create a helper in the test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.hypermedia.LinkDescriptor;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;

public final class CommonLinkDescriptors {
    private CommonLinkDescriptors() {}

    public static List<LinkDescriptor> resourceLinks() {
        return List.of(
            linkWithRel("self")
                .description("Link to the current resource"),
            linkWithRel("profile")
                .description("Description of the resource structure")
        );
    }
}
```

Use in an operation:

```java
document("products-find",
    links(CommonLinkDescriptors.resourceLinks())
)
```

The factory method creates fresh descriptors on every call. List.of(...) disallows adding or removing elements, which is convenient for keeping the relation group structure stable.

### Constant or factory?

A descriptor constant is only suitable when the relation always has the exact same description and state across all operations. LinkDescriptor has configuration methods such as optional() and ignored(). Do not share a static instance and mutate its state in individual tests. A factory is better suited when the same relation is required in one operation but optional in another.

## 4. Combining shared relations with specific relations

The product endpoint has an orders relation; the order endpoint has customer and cancel. Both have self/profile:

```java
static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> descriptors =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    descriptors.add(
        linkWithRel("orders")
            .description("List of orders for the product")
    );
    return descriptors;
}

static List<LinkDescriptor> orderLinks() {
    List<LinkDescriptor> descriptors =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    descriptors.add(
        linkWithRel("customer")
            .description("Customer who placed the order")
    );
    descriptors.add(
        linkWithRel("cancel")
            .description("Cancel the order if its status allows")
    );
    return descriptors;
}
```

Usage:

```java
document("products-find", links(productLinks()));
document("orders-find", links(orderLinks()));
```

Factories keep shared relations in one place while documenting business relations on the right resource. Do not lump every relation of every resource into one giant list and apply it to all operations; responses would be required to provide links that do not belong to them.

## 5. Relations for collections and pagination

Collections often include pagination navigation links:

```json
{
  "_embedded": {
    "products": [
      {"id": 42, "name": "Keyboard"},
      {"id": 43, "name": "Mouse"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=1"},
    "profile": {"href": "/api/profiles/product-collection"}
  },
  "page": {"size": 20, "number": 0, "totalElements": 45}
}
```

Factory for collections:

```java
static List<LinkDescriptor> collectionLinks() {
    return List.of(
        linkWithRel("self").description("Current collection page"),
        linkWithRel("profile").description("Description of the collection structure"),
        linkWithRel("next").description("Next page").optional(),
        linkWithRel("prev").description("Previous page").optional()
    );
}
```

next may be absent on the last page and prev may be absent on the first page. Optional descriptors reflect this condition. Do not mark every relation optional if the contract requires them to always be present; keeping self required helps tests detect responses missing primary links.

## 6. Optional, ignored, and relaxed links

| Usage | Meaning |
| --- | --- |
| Default | Relation is documented and expected to be present |
| optional() | Relation may be absent; if present, it is still documented |
| ignored() | Relation is excluded from the table and skipped in descriptor checks |
| relaxedLinks(...) | Allows the response to contain additional relations outside the descriptors |

Do not create a shared relation where test A calls optional() while test B expects the relation to be required. Create context-specific factories:

```java
static LinkDescriptor requiredSelfLink() {
    return linkWithRel("self")
        .description("Link to the current resource");
}

static LinkDescriptor optionalNextLink() {
    return linkWithRel("next")
        .description("Next page")
        .optional();
}

static LinkDescriptor requiredNextLink() {
    return linkWithRel("next")
        .description("Next page");
}
```

Strict links help catch relations present in the response that have not been documented. If a test focuses only on self while secondary links are documented elsewhere, use:

```java
relaxedLinks(
    linkWithRel("self").description("Current resource")
)
```

Relaxed mode ignores relations outside the descriptor list. Do not enable it by default for every operation because new business-meaningful links could appear without tests alerting the team to update the documentation.

## 7. Custom relations, URI templates, and CURIEs

### Custom relations

```json
{
  "_links": {
    "self": {"href": "/api/orders/9001"},
    "cancel": {"href": "/api/orders/9001/cancellation"},
    "invoice": {"href": "/api/orders/9001/invoice"}
  }
}
```

Document according to business semantics:

```java
static List<LinkDescriptor> orderActionLinks() {
    return List.of(
        linkWithRel("self").description("Current order"),
        linkWithRel("cancel").description("Cancel the order"),
        linkWithRel("invoice").description("Retrieve the order invoice")
    );
}
```

If cancel is only returned when the order has not shipped yet, the documentation should state this condition or document the corresponding response variant.

### URI templates

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

This is a URI template, not a complete URL to call verbatim. The search relation indicates search capability; templated: true tells the client it needs to fill in variables. When reusing descriptors, do not overlook the distinction between a plain relation and a relation pointing to a URI template.

### CURIEs in HAL

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

You can document the custom relation and ignore the CURIE infrastructure link if the page does not need to display it:

```java
static List<LinkDescriptor> productHypermediaLinks() {
    return List.of(
        linkWithRel("self").description("Current product"),
        linkWithRel("ex:reviews").description("Product reviews"),
        linkWithRel("curies").ignored()
    );
}
```

ex:reviews is the custom relation; curies defines how to expand the ex prefix. Do not use CURIE in place of the target relation.

## 8. MockMvc example sharing link descriptors

Test example for two HAL responses:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class HypermediaDocumentationTest {

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
                links(productLinks())
            ));
    }

    @Test
    void findOrder() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/orders/{id}", 9001)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("orders-find",
                links(orderLinks())
            ));
    }
}
```

Static imports:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;
```

Both tests share the helper for self/profile while each operation has its own links. The controller must return a HAL response with the appropriate Content-Type and _links structure; if using another hypermedia format, a corresponding LinkExtractor is needed.

## 9. Organizing helper classes

Place descriptor helpers in the test source set:

```text
src/
  test/
    java/
      com/example/api/docs/
        CommonLinkDescriptors.java
        ProductLinkDescriptors.java
        OrderLinkDescriptors.java
        CollectionLinkDescriptors.java
```

Conventions:

- Factory names express the relation group, such as resourceLinks(), productLinks(), and collectionLinks().
- Only share relations when both name and meaning agree.
- Create fresh descriptors if optional/ignored state differs across operations.
- Keep business relations in the corresponding resource's helper.
- Avoid a single global link list applied to every response.
- Use separate operation IDs for response variants that have different link contracts.

Only move helpers into a test-fixture module if multiple test modules genuinely need to share them. Do not place test documentation helpers in the main source set if the runtime application does not need a Spring REST Docs dependency.

## 10. Including links.adoc in Asciidoctor

Example src/docs/asciidoc/products.adoc file:

```asciidoc
= Catalog API
:toc: left

== Find product

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== HTTP response
include::{snippets}/products-find/http-response.adoc[]

== Find order

=== Hypermedia links
include::{snippets}/orders-find/links.adoc[]
```

The snippets attribute must point to the root generated snippets directory. The path after it matches the operation ID. If tests use a custom outputDir, update the attribute in the Asciidoctor configuration. Do not include links.adoc for an operation that has not declared links(...) or a response without matching links.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Duplicate relation in table | Two factories both produce the same relation. | Inspect the combined list and keep a single descriptor source. |
| One test makes another test's relation optional | Sharing a LinkDescriptor configured with optional(). | Have factories create fresh descriptors per operation. |
| Response missing required link | Server does not return the documented relation. | Fix the implementation or mark optional if the contract allows. |
| Test reports undocumented link | Strict mode detects a newly added undocumented relation. | Add a descriptor or use relaxed mode with a clear scope. |
| Reused description has wrong semantics | Relations share a name but have different meanings across resources. | Split factories by domain/resource. |
| Link template treated as a fixed URL | Overlooking the templated attribute or template variables. | Document the relation and how clients fill variables. |
| CURIE documented as a business link | Confusing the relation prefix with the expanded relation. | Document the custom relation and ignore CURIE if appropriate. |
| links.adoc is not generated | links(...) not declared, test did not run, or wrong outputDir. | Check the operation and snippet directory. |
| LinkExtractor cannot read response | Incompatible Content-Type/representation. | Check HAL/Atom format or provide a custom extractor. |

## 12. Practice exercise

Create a Catalog API returning HAL:

1. GET /api/products/{id} has self, profile, and orders.
2. GET /api/orders/{id} has self, profile, customer, and cancel.
3. GET /api/products has self, profile, next, and prev.
4. Create CommonLinkDescriptors for self/profile; create separate factories for product, order, and collection.
5. Mark next/prev optional depending on the page; keep self required.
6. Create a strict operation to detect new relations and a relaxedLinks operation when only self needs to be documented.
7. Add CURIE relation ex:reviews; verify descriptors match keys in HAL _links.
8. Include links.adoc in Asciidoctor, run clean test, and build documentation.

**Completion criteria:** reuse link descriptors without mixing up relation semantics; combine shared and specific links; manage optional/ignored/relaxed; explain relation, href, URI templates, and CURIEs; generate links.adoc from tests and include the right operations.

## 13. References

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [IANA — Link Relations](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
