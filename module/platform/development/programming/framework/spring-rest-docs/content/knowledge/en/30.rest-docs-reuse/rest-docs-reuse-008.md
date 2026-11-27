# Creating factories for commonly used descriptor sets

## 1. Purpose of descriptor factories

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests both verify the API and generate snippets for requests, responses, and hypermedia. As the number of operations grows, tests can end up repeating descriptions for fields, parameters, headers, and links. If each test constructs descriptors on its own, the team easily runs into issues:

- The same field or header gets different descriptions across similar endpoints.
- Contract changes require editing many tests.
- Shared descriptors get mixed with operation-specific fields.
- Optional/ignored states are accidentally shared across tests.
- Overly generic helpers leave readers unsure which payload a descriptor fits.

A factory is a function that constructs descriptors for a specific contract. Instead of maintaining one static description table, you organize small factories by resource or contract group. Each operation calls the factories it needs and combines them with its own descriptors.

Spring REST Docs provides descriptors for many parts of HTTP:

| Component | Descriptor API | Snippet |
| --- | --- | --- |
| JSON request fields | fieldWithPath(...), requestFields(...) | request-fields.adoc |
| JSON response fields | fieldWithPath(...), responseFields(...) | response-fields.adoc |
| Path parameters | parameterWithName(...), pathParameters(...) | path-parameters.adoc |
| Query parameters | parameterWithName(...), queryParameters(...) | query-parameters.adoc |
| Form parameters | parameterWithName(...), formParameters(...) | form-parameters.adoc |
| Request headers | headerWithName(...), requestHeaders(...) | request-headers.adoc |
| Response headers | headerWithName(...), responseHeaders(...) | response-headers.adoc |
| Hypermedia links | linkWithRel(...), links(...) | links.adoc |

The goal of a factory catalog is not to stuff every descriptor into one huge list. The goal is to provide small, clearly named building blocks that produce the right descriptors for one slice of a contract and can be composed per operation.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. Descriptor factories do not depend on MockMvc; WebTestClient and REST Assured can reuse them as well.

## 2. Design principles

### Group by resource and contract

Group helpers by resource or contract slices with shared meaning:

```text
src/test/java/com/example/catalog/docs/
  common/
    CommonPaginationDescriptors.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductFieldDescriptors.java
    ProductParameterDescriptors.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderLinkDescriptors.java
```

You do not need a separate class for every single descriptor. Group factories that share scope and potential for reuse.

### Factory names must state what they produce

Names like fields() or common() do not tell which operation a list fits. Prefer names describing the payload or contract:

```java
productCreateRequestFields()
productSummaryResponseFields()
productSearchQueryParameters()
productResponseHeaders()
productHypermediaLinks()
```

When reading a test, the factory name should help reviewers understand which descriptor group is being applied.

### Share by meaning, not merely by name

Two fields with the same name do not necessarily share the same meaning. For example, status on Product is the commercial status; status on Order is the order processing status. Do not share a description just because the path matches.

Similarly, the Location header on a product creation endpoint points to the product resource, while on an order creation endpoint it points to the order resource. You can share descriptor construction if the description is neutral enough, or use dedicated factories to describe the context.

### Create fresh instances when state may vary

Descriptors have configuration methods such as optional() and ignored(). If one operation requires a field while another allows it to be absent, the factory should create fresh descriptors for each case. Avoid holding a static instance and mutating it per test.

## 3. Factories for request and response fields

Create a Product helper class:

```java
package com.example.catalog.docs;

import java.util.ArrayList;
import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static List<FieldDescriptor> productCreateRequestFields() {
        return List.of(
            fieldWithPath("name").description("Product name"),
            fieldWithPath("description").description("Product description"),
            fieldWithPath("price").description("Selling price")
        );
    }

    public static List<FieldDescriptor> productSummaryResponseFields() {
        return List.of(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name"),
            fieldWithPath("price").description("Selling price")
        );
    }

    public static List<FieldDescriptor> productDetailResponseFields() {
        List<FieldDescriptor> fields =
            new ArrayList<>(productSummaryResponseFields());
        fields.add(fieldWithPath("description")
            .description("Detailed product description"));
        fields.add(fieldWithPath("inventory.available")
            .description("Available quantity for sale"));
        return fields;
    }
}
```

Requests and responses have separate factories because even though both have name and price fields, they are two distinct contracts. Summary and detail responses share part of their structure; the detail factory creates a new list and appends its specific fields.

Usage:

```java
document("products-create",
    requestFields(ProductFieldDescriptors.productCreateRequestFields())
);

document("products-summary",
    responseFields(ProductFieldDescriptors.productSummaryResponseFields())
);

document("products-detail",
    responseFields(ProductFieldDescriptors.productDetailResponseFields())
);
```

## 4. Factories for parameters and headers

### Pagination query parameters

```java
public final class CommonPaginationDescriptors {
    private CommonPaginationDescriptors() {}

    public static List<ParameterDescriptor> queryParameters() {
        return List.of(
            parameterWithName("page")
                .description("Page number, zero-based"),
            parameterWithName("size")
                .description("Number of items per page")
        );
    }
}
```

The Product endpoint appends category:

```java
static List<ParameterDescriptor> productSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonPaginationDescriptors.queryParameters());
    parameters.add(parameterWithName("category")
        .description("Product category"));
    return parameters;
}
```

The Order endpoint can append customerId and status. Although both endpoints have status, the description must match the respective domain:

```java
static List<ParameterDescriptor> orderSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonPaginationDescriptors.queryParameters());
    parameters.add(parameterWithName("customerId")
        .description("Customer ID"));
    parameters.add(parameterWithName("status")
        .description("Order status"));
    return parameters;
}
```

Use the factory with queryParameters(...). Do not reuse the same factory for path/form if parameter location and semantics differ.

### Response headers

If multiple endpoints return JSON, you can create a shared Content-Type descriptor:

```java
public final class CommonHeaderDescriptors {
    private CommonHeaderDescriptors() {}

    public static HeaderDescriptor jsonContentType() {
        return headerWithName("Content-Type")
            .description("Media type of the response body");
    }
}
```

A resource-creation endpoint adds Location:

```java
static List<HeaderDescriptor> productCreateResponseHeaders() {
    return List.of(
        CommonHeaderDescriptors.jsonContentType(),
        headerWithName("Location")
            .description("URI of the newly created product")
    );
}
```

If the same header has different descriptions by context, create resource-specific factories. If a header may be absent in one response variant, create a separate factory with optional() instead of mutating a shared descriptor.

## 5. Factories for hypermedia links

Many HAL resources have self and profile relations:

```java
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

Product adds orders:

```java
static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    links.add(linkWithRel("orders")
        .description("List of orders for the product"));
    return links;
}
```

Collections have pagination relations:

```java
static List<LinkDescriptor> productCollectionLinks() {
    return List.of(
        linkWithRel("self").description("Current collection"),
        linkWithRel("next").description("Next page").optional(),
        linkWithRel("prev").description("Previous page").optional()
    );
}
```

Do not use one link set for every response. next may be optional in a collection, but makes no sense on a resource detail. Separate factories accurately express each representation's contract.

## 6. Composing factories in operation documentation

An operation can use multiple descriptor groups simultaneously:

```java
mockMvc.perform(
        post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Keyboard",
                  "description": "Mechanical keyboard",
                  "price": 89.5
                }
                """)
    )
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(ProductFieldDescriptors.productCreateRequestFields()),
        responseHeaders(ProductHeaderDescriptors.createResponseHeaders()),
        responseFields(ProductFieldDescriptors.productSummaryResponseFields()),
        links(ProductLinkDescriptors.productLinks())
    ));
```

This shows how to compose descriptor groups. In an actual test, the response must include the documented headers and hypermedia relations; passing descriptors does not automatically generate headers or links in the application.

Choose a stable operation ID and use that ID in Asciidoctor includes. When a contract changes, the test will fail on the corresponding descriptor section.

## 7. Designing extensible factories

### Returning List or varargs?

Returning List from factories is convenient when groups need to be combined:

```java
List<FieldDescriptor> fields = new ArrayList<>(commonFields());
fields.addAll(endpointSpecificFields());
```

Varargs works well for small fixed groups and concise call sites. When combining multiple groups, List clearly expresses order and scope. Use overloads supported by your Spring REST Docs version; if an API accepts varargs, convert the list to an array of the proper descriptor type.

### Using prefixes for identical structures

Shipping and billing addresses share the same fields but have different paths:

```java
static List<FieldDescriptor> addressFields(String prefix, String label) {
    return List.of(
        fieldWithPath(prefix + ".street")
            .description("Street for " + label),
        fieldWithPath(prefix + ".city")
            .description("City for " + label),
        fieldWithPath(prefix + ".postalCode")
            .description("Postal code for " + label)
    );
}
```

A prefix-accepting factory should only be used when the schemas are truly identical. If one address has different fields or rules, split into separate factories so contract differences are not hidden.

### Do not turn factories into a framework

Avoid building a generic DSL or reflection registry just to create a few descriptors. A small Java factory with a clear name returning a new list is usually easier to read. Only introduce heavier structure when multiple tests/modules genuinely share the same contract and maintenance costs justify it.

## 8. Strict, optional, ignored, and relaxed

Factories must preserve REST Docs verification guarantees:

| Configuration | Effect |
| --- | --- |
| Default descriptor | Field/parameter/header/link is documented and verified |
| optional() | Component may be absent |
| ignored() | Component is excluded from the table and normal descriptor checks |
| relaxed descriptor | Allows components outside the documented list to appear |

Do not create a generic factory named allFields() and mark most fields ignored just to reuse it across multiple payloads. That disables strict validation's ability to catch contract drift.

If description is required on POST but optional on PATCH, create two factories. If a next link only exists on a collection, place optional on the collection factory rather than a shared resource factory. If a response header may be absent in one variant, create a header factory for that variant.

## 9. Package organization and scope control

Place helpers in the test source set:

```text
src/test/java/com/example/catalog/docs/
  common/
    CommonPaginationDescriptors.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductFieldDescriptors.java
    ProductParameterDescriptors.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderLinkDescriptors.java
```

Descriptors used for testing and documentation belong in test sources. Do not make production code depend on Spring REST Docs if the runtime application does not need it. If multiple modules need to share them, consider a test-fixture module and only export factories with stable contracts.

## 10. MockMvc example using a factory catalog

A search test can combine factories:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void searchProducts() throws Exception {
        mockMvc.perform(
                get("/api/products")
                    .queryParam("page", "0")
                    .queryParam("size", "20")
                    .queryParam("category", "keyboard")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-search",
                queryParameters(
                    ProductParameterDescriptors.productSearchParameters()
                ),
                responseFields(
                    ProductFieldDescriptors.productSearchResponseFields()
                )
            ));
    }
}
```

When you need to document request headers, response headers, or links, add the corresponding factories to document(...). Do not include snippets that an operation does not generate.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| One field has different descriptions across similar endpoints | Tests declare descriptors independently in multiple places. | Create a shared factory when semantics truly match. |
| Shared descriptor requires a nonexistent field | Overly broad descriptor set used for different payloads. | Split factories by request/response shape. |
| Other tests are affected by optional/ignored | Sharing a configured descriptor instance. | Have factories create fresh descriptors per operation. |
| Combined list has duplicate paths/relations | Both common and endpoint factories add the same element. | Define clear ownership and inspect combined lists. |
| Wrong parameter/header meaning in description | Shared purely by name without checking context. | Split factories by resource or contract. |
| Strict validation misses new fields | Overly broad use of relaxed/ignored. | Narrow relaxed usage and keep strict mode for full-contract operations. |
| Helpers are hard to locate | Putting all descriptors into one massive class. | Organize by resource and contract group. |
| Tests depend on a production module | Placing REST Docs helpers in the main source set. | Move helpers to test sources or a test-fixture module. |

## 12. Practice exercise

Build a Catalog API with operations for creating products, searching products, and searching orders.

1. Create ProductFieldDescriptors for create request, summary response, and detail response.
2. Create CommonPaginationDescriptors and compose it into ProductParameterDescriptors and OrderParameterDescriptors.
3. Create CommonHeaderDescriptors for JSON Content-Type; create a dedicated header factory for product creation responses containing Location.
4. Create CommonLinkDescriptors for self/profile; compose specific relations for product and order.
5. Write MockMvc tests using the factory catalog inside document(...).
6. Make fields optional in PATCH while required in POST; verify the two factories do not share state.
7. Intentionally add an undocumented field or relation to observe strict validation.
8. Include generated snippets in Asciidoctor and run clean test asciidoctor.

**Completion criteria:** group descriptors by resource/contract; name factories clearly; compose shared groups with specific parts; avoid unintended descriptor state sharing; preserve strict validation and generate includable documentation snippets.

## 13. References

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs API Documentation](https://docs.spring.io/spring-restdocs/docs/current/api/)
