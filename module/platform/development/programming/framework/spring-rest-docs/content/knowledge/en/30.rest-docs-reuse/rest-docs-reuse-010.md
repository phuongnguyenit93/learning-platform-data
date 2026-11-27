# Keeping shared and specific descriptions separate

## 1. Why separate shared and specific parts?

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests generate snippets from actual requests and responses. When multiple endpoints share part of a contract, you can reuse descriptors to reduce duplication. However, if you lump every field, parameter, header, or link into one shared helper, one endpoint's description can be misapplied to another endpoint.

For example, Product and Order both have an id field, yet their meaning and format can differ. Both endpoints have a status query parameter, yet one filters product status and the other filters order status. Both have a Location header, yet the target URI points to different resources.

Principles:

- **Shared part** holds descriptions with identical meaning, path/location, and presence rules.
- **Specific part** holds semantics or behavior belonging only to one resource, endpoint, or response variant.
- **Composition** combines both parts into the exact descriptor set for a specific operation.

The goal is not to maximize the amount of shared code. The goal is to reuse only the genuinely shared part of the contract while keeping individual verification for each endpoint.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. Descriptor organization does not depend on MockMvc; WebTestClient and REST Assured can also use these factories.

## 2. Identifying the boundary between shared and specific

Before creating a helper, compare operations by contract:

| Component | Shareable when | Separate when |
| --- | --- | --- |
| JSON field | Same path, data type, meaning, and optionality rules | Same name but different meaning or structure |
| Path parameter | Same name and same identifying meaning | Same name but identifies a different resource |
| Query parameter | Same location, meaning, and value rules | Filters have resource-specific semantics |
| Header | Same header and same meaning to the client | Same name but value/meaning depends on endpoint |
| Hypermedia link | Same relation and same navigation capability | Specific relation or different presence condition |

A practical rule of thumb: if you have to add multiple if conditions, pass multiple boolean flags, or modify descriptions per endpoint after calling a factory, the abstraction is probably combining different contracts. Splitting factories usually makes tests easier to understand.

## 3. The composition model

An operation can be assembled from three parts:

```text
Common contract fragments
          +
Resource-specific descriptors
          +
Operation-specific descriptors
          |
          v
   document(operationId, ...)
          |
          v
   generated snippets
```

Example:

- Common: pagination queries page, size.
- Resource-specific: Product has query category; Order has query customerId.
- Operation-specific: Product export endpoint has query format; Product list endpoint does not.

Do not put format into a shared factory simply because another operation happens to use the same data type. Factory scope must reflect the contract, not code-assembly convenience.

## 4. Separating request field descriptors

Suppose Product create and Product import both accept name, description, and price. Import adds sourceSystem.

### Shared part

```java
public final class ProductCommonFields {
    private ProductCommonFields() {}

    public static List<FieldDescriptor> createFields() {
        return List.of(
            fieldWithPath("name").description("Product name"),
            fieldWithPath("description").description("Product description"),
            fieldWithPath("price").description("Selling price")
        );
    }
}
```

### Specific part and composition

```java
public final class ProductImportFields {
    private ProductImportFields() {}

    public static List<FieldDescriptor> requestFields() {
        List<FieldDescriptor> fields =
            new ArrayList<>(ProductCommonFields.createFields());
        fields.add(
            fieldWithPath("sourceSystem")
                .description("Source system of the record")
        );
        return fields;
    }
}
```

The create operation uses the shared part:

```java
document("products-create",
    requestFields(ProductCommonFields.createFields())
)
```

The import operation combines shared and specific parts:

```java
document("products-import",
    requestFields(ProductImportFields.requestFields())
)
```

The sourceSystem field is not required in the create request, and strict validation can still detect undocumented new fields in each payload.

## 5. Same field name, different semantics

Not every field with a matching name should share a descriptor:

| Resource | Field | Meaning |
| --- | --- | --- |
| Product | status | Commercial status: ACTIVE, DISCONTINUED |
| Order | status | Processing status: PENDING, PAID, SHIPPED |

Separate factories:

```java
static FieldDescriptor productStatusField() {
    return fieldWithPath("status")
        .description("Commercial status of the product");
}

static FieldDescriptor orderStatusField() {
    return fieldWithPath("status")
        .description("Order processing status");
}
```

If you use a single commonStatusField() with the description "Status", the documentation table loses crucial information for clients. Only share when business meaning is genuinely equivalent, not merely because JSON paths match.

## 6. Separating shared and specific parameters

### Shared pagination

```java
public final class CommonQueryParameters {
    private CommonQueryParameters() {}

    public static List<ParameterDescriptor> pagination() {
        return List.of(
            parameterWithName("page")
                .description("Page number, zero-based"),
            parameterWithName("size")
                .description("Number of items per page")
        );
    }
}
```

### Resource-specific filters

```java
static List<ParameterDescriptor> productSearch() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonQueryParameters.pagination());
    parameters.add(
        parameterWithName("category")
            .description("Product category")
    );
    parameters.add(
        parameterWithName("status")
            .description("Commercial status of the product")
    );
    return parameters;
}

static List<ParameterDescriptor> orderSearch() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonQueryParameters.pagination());
    parameters.add(
        parameterWithName("customerId")
            .description("Customer ID")
    );
    parameters.add(
        parameterWithName("status")
            .description("Order processing status")
    );
    return parameters;
}
```

Pagination is shared; filters remain tied to Product or Order. The two status descriptors are created separately because their semantics differ.

## 7. Separating shared and specific response headers

Several responses return JSON, so Content-Type can be shared:

```java
static HeaderDescriptor jsonContentType() {
    return headerWithName("Content-Type")
        .description("Media type of the response body");
}
```

However, Location should be described per resource:

```java
static List<HeaderDescriptor> productCreatedHeaders() {
    return List.of(
        jsonContentType(),
        headerWithName("Location")
            .description("URI of the newly created product")
    );
}

static List<HeaderDescriptor> orderCreatedHeaders() {
    return List.of(
        jsonContentType(),
        headerWithName("Location")
            .description("URI of the newly created order")
    );
}
```

While a generic Location description like "URI of the new resource" may be acceptable, dedicated factories usually make documentation clearer when resources have different semantics or URI rules.

## 8. Separating shared and specific hypermedia links

HAL resources commonly have self; Product adds orders, while Order adds customer and cancel:

```java
static List<LinkDescriptor> commonResourceLinks() {
    return List.of(
        linkWithRel("self")
            .description("Link to the current resource")
    );
}

static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(commonResourceLinks());
    links.add(
        linkWithRel("orders")
            .description("List of orders for the product")
    );
    return links;
}

static List<LinkDescriptor> orderLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(commonResourceLinks());
    links.add(
        linkWithRel("customer")
            .description("Customer for the order")
    );
    links.add(
        linkWithRel("cancel")
            .description("Cancel the order if its status allows")
    );
    return links;
}
```

Do not put orders, customer, and cancel into a shared list. A response should only be verified against relations required by that resource's contract.

## 9. Optional, ignored, and relaxed must stay properly scoped

A field may be required on POST but optional on PATCH. A next link exists only on collections. A header may be absent in a 204 response. Do not mutate a shared descriptor to handle these cases.

Create separate factories:

```java
static FieldDescriptor requiredDescription() {
    return fieldWithPath("description")
        .description("Product description");
}

static FieldDescriptor optionalDescription() {
    return fieldWithPath("description")
        .description("Product description")
        .optional();
}

static LinkDescriptor optionalNextLink() {
    return linkWithRel("next")
        .description("Next page")
        .optional();
}
```

Meaning:

| Configuration | Appropriate usage |
| --- | --- |
| Default | Contract requires the component to be present and documented |
| optional() | Component is allowed to be absent in a valid variant |
| ignored() | Component falls outside the current snippet's scope |
| Relaxed descriptor | Operation documents only a subset and accepts other components |

Strict mode detects newly added undocumented fields, parameters, headers, or links. Relaxed mode is helpful when a test has a narrow scope, but using it too broadly allows contract drift to go unnoticed.

## 10. Composition example in a MockMvc test

A Product creation operation can combine request fields, response headers, response fields, and links:

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
        requestFields(ProductCommonFields.createFields()),
        responseHeaders(ProductHeaderDescriptors.productCreatedHeaders()),
        responseFields(ProductResponseDescriptors.summaryFields()),
        links(ProductLinkDescriptors.productLinks())
    ));
```

This is a composition example. The controller must actually return the documented headers and HAL links; descriptors only record and verify the response rather than injecting headers or links into the application.

An Order operation will use the corresponding Order factories. Shared parts can be reused, while business relations and descriptions remain separate.

## 11. Naming conventions and helper organization

An easy-to-navigate layout:

```text
src/test/java/com/example/api/docs/
  common/
    CommonQueryParameters.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductCommonFields.java
    ProductImportFields.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderHeaderDescriptors.java
    OrderLinkDescriptors.java
```

Rules:

- Class names indicate the resource or contract scope.
- Method names indicate request/response and operation/variant.
- Only share descriptors that share path, location, meaning, and presence rules.
- Factories create fresh descriptors if optional/ignored state differs.
- Specific parts are composed in the operation or resource factory.
- Place helpers in test sources; only create a test-fixture module if multiple modules genuinely need to share them.

## 12. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Endpoint requires a field not in its payload | Overly broad shared factory used. | Separate specific fields and only compose genuinely shared contract parts. |
| Same-named field has an inaccurate description | Shared by name instead of semantics. | Create separate resource-specific descriptors. |
| status parameter has an ambiguous description | Shared factory used for both Product and Order. | Split filter factories by domain. |
| Location header describes the wrong resource | Generic description lacks sufficient context. | Create separate header factories if semantics differ. |
| Response requires relations belonging to another resource | One link list applied to every operation. | Split link factories by resource. |
| Another test gets affected by optional | Sharing a configured descriptor instance. | Have factories return fresh instances per operation. |
| Strict validation misses contract drift | Relaxed/ignored used too broadly. | Narrow relaxed usage and keep strict mode on primary operations. |
| Helper has many boolean flags | One factory is serving multiple distinct contracts. | Split into factories with clear names and semantics. |

## 13. Practice exercise

Build a Catalog API with Product and Order:

1. Both have pagination queries page and size.
2. Product has category and Product status filters; Order has customerId and Order status.
3. Both responses have JSON Content-Type; each resource has its own Location description on creation.
4. HAL Product has self/orders; HAL Order has self/customer/cancel.

Steps:

1. Create CommonQueryParameters for pagination.
2. Create ProductSearchParameters and OrderSearchParameters, combining pagination with specific filters.
3. Create CommonHeaderDescriptors for Content-Type and separate header factories for Product/Order Location.
4. Create a common self link and compose specific relations for Product and Order.
5. Write MockMvc tests passing the right factories to document(...) per operation.
6. Make a field optional in PATCH while required in POST; verify factories do not share state.
7. Intentionally add an undocumented parameter or relation to test strict validation.
8. Include snippets in Asciidoctor, run clean test, and build the documentation.

**Completion criteria:** distinguish shared and specific contracts; share only parts with identical semantics; compose descriptors per operation; keep optional/ignored/relaxed properly scoped; preserve strict validation to catch API changes.

## 14. References

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs API Documentation](https://docs.spring.io/spring-restdocs/docs/current/api/)
