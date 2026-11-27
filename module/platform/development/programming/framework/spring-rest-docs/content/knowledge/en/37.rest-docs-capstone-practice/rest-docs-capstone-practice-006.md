# Documenting HATEOAS Links and Embedded Resources

## 1. How HATEOAS Changes API Response Documentation

In a conventional REST API, the response contains data and the client must already know the URLs for follow-up actions. With HATEOAS, the response also provides **links** so clients can discover actions or related resources. The HAL JSON media type can also group related resources inside an **embedded resources** section.

Example HAL response:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {"href": "https://api.example.test/orders/42"},
    "cancel": {"href": "https://api.example.test/orders/42/cancel"},
    "customer": {"href": "https://api.example.test/customers/7"}
  },
  "_embedded": {
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2,
        "_links": {
          "product": {"href": "https://api.example.test/products/BOOK-01"}
        }
      }
    ]
  }
}
~~~

The response has three groups of information to document:

- Business fields at the resource level: `id`, `status`.
- Links in `_links`: `self`, `cancel`, `customer`.
- Embedded resources in `_embedded`: the `items` list, where each item has its own fields and links.

Spring REST Docs has a dedicated API for links. Use `links(...)` to document link relations; use payload field descriptors to describe embedded resources and remaining data fields. Do not document a link merely as an arbitrary JSON string if the goal is to help clients understand relation semantics.

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured generate verifiable snippets. When an API uses HATEOAS, documentation needs to explain both link relations and embedded data structures so consumers know how to navigate and read resources.

## 2. The Links Snippet in Spring REST Docs

### 2.1. Using `links(...)` and `linkWithRel(...)`

Spring REST Docs provides `linkWithRel(...)` to document a link by relation name. MockMvc example:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        links(
            linkWithRel("self").description("Link to this order"),
            linkWithRel("cancel").description("Cancel the order if its status permits"),
            linkWithRel("customer").description("Customer resource for the order")
        )
    ));
~~~

This operation generates `links.adoc`, describing the relation, target link, and description provided by the test. The snippet helps readers understand what the `cancel` relation means instead of guessing from the URL.

With HAL, REST Docs recognizes links inside the `_links` structure. Ensure the response has an appropriate content type, such as `application/hal+json`, so REST Docs uses the corresponding hypermedia parser.

### 2.2. Documenting Required and Optional Links

By default, link descriptors are required. If a relation only appears in certain resource states, mark it `optional`:

~~~java
links(
    linkWithRel("self").description("Link to the order"),
    linkWithRel("cancel").optional()
        .description("Present only when the order can still be canceled")
)
~~~

If the response contains a link that does not need to be documented in the current snippet, you can ignore that link:

~~~java
links(
    linkWithRel("self").description("Link to the order"),
    linkWithRel("cancel").description("Cancel the order"),
    linkWithRel("customer").ignored()
)
~~~

| Descriptor | Meaning |
| --- | --- |
| Without `optional()` | The link must exist in the response |
| `optional()` | The link may be absent |
| `ignored()` | The link is outside the scope of this snippet; REST Docs does not require documenting it |

Do not use `ignored()` to hide an important relation you forgot to document. For public APIs, clearly document all relations clients are expected to use.

### 2.3. `relaxedLinks(...)` for Partial Documentation

`links(...)` verifies that all links in the response are documented, helping detect when the API adds a relation that documentation has not updated. During exploration or when intentionally documenting only a subset, you can use `relaxedLinks(...)`:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get",
        relaxedLinks(
            linkWithRel("self").description("Link to the order")
        )
    ));
~~~

`relaxedLinks(...)` does not require every link in the response to have a descriptor. This is convenient for partial documentation, though it reduces contract-change verification for links. For full contract documentation, prefer `links(...)` and declare all necessary relations explicitly.

## 3. Embedded Resources in the Payload

HAL typically uses `_embedded` to hold related resources:

~~~json
{
  "_embedded": {
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      }
    ]
  }
}
~~~

`_embedded.items` is an array of embedded resources. It is not a link relation inside `_links`; therefore `links(...)` does not document fields like `sku` or `quantity`.

Use `responseFields(...)` to document the JSON structure:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    fieldWithPath("_embedded.items").description("List of embedded items"),
    fieldWithPath("_embedded.items[].sku").description("Product SKU"),
    fieldWithPath("_embedded.items[].quantity").description("Quantity")
)
~~~

Array descriptors use `[]` in the path to denote elements. If the API has more fields inside each element, document them as corresponding child paths.

## 4. Using `subsectionWithPath(...)` for Embedded Subtrees

When you want to document a JSON section as a block without listing every field directly in the response-level snippet, use `subsectionWithPath(...)`:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    subsectionWithPath("_embedded.items")
        .description("List of embedded product resources")
)
~~~

A subsection descriptor indicates that the entire `_embedded.items` subtree belongs to a documented payload region. This approach works well when you only need to introduce the embedded collection at a high level, or want to extract detailed field descriptions into a separate snippet.

If you use `subsectionWithPath("_embedded.items")`, do not also declare child fields of the same subtree in the same descriptor set in an overlapping manner. Choose one level of description: either describe the subtree as a block or list the child fields.

### 4.1. Separating Field Documentation with `beneathPath(...)`

When you want to document fields inside an embedded resource in detail, you can use `beneathPath(...)` to scope the payload snippet to a portion of the response:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    beneathPath("_embedded.items[]")
        .withSubsectionId("order-items")
        .and()
        .description("Fields of an item in the order"),
    fieldWithPath("sku").description("SKU code"),
    fieldWithPath("quantity").description("Quantity")
)
~~~

`beneathPath(...)` generates a payload snippet from the selected portion instead of the entire response. With an embedded collection, verify that the payload is sliced according to the actual structure and that the path syntax is supported by your REST Docs version. When descriptors apply to each array element, the field snippet should describe a representative item without confusing relative paths with response-level paths.

Another option is to keep full field paths inside `responseFields(...)`:

~~~java
responseFields(
    fieldWithPath("_embedded.items[].sku").description("SKU code"),
    fieldWithPath("_embedded.items[].quantity").description("Quantity")
)
~~~

This approach is direct and easy to cross-check against the root JSON; `beneathPath(...)` is useful when documentation separates a subtree into an independent field table.

## 5. Combining Links and Response Fields in One Operation

In a HAL response, links and payload fields are complementary. Both snippets can be generated in the same operation:

~~~java
mockMvc.perform(get("/orders/42")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        links(
            linkWithRel("self").description("Link to the order"),
            linkWithRel("cancel").optional()
                .description("Cancel the order if its status permits"),
            linkWithRel("customer").description("Customer of the order")
        ),
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Status"),
            subsectionWithPath("_embedded.items")
                .description("Items in the order")
        )
    ));
~~~

The result typically produces separate snippets:

~~~text
orders/get/
├── http-request.adoc
├── http-response.adoc
├── links.adoc
└── response-fields.adoc
~~~

Snippet names may vary if custom snippet templates are used. Check the actual generated directory after tests run and include the exact filenames.

## 6. HATEOAS Controller Example

A Spring HATEOAS API can return `EntityModel` or `CollectionModel`. Abbreviated example:

~~~java
@GetMapping(value = "/orders/{id}", produces = "application/hal+json")
EntityModel<Order> getOrder(@PathVariable long id) {
    Order order = orderService.getById(id);
    return EntityModel.of(order,
        linkTo(methodOn(OrderController.class).getOrder(id)).withSelfRel(),
        linkTo(methodOn(OrderController.class).cancelOrder(id)).withRel("cancel"),
        linkTo(methodOn(CustomerController.class).getCustomer(order.customerId()))
            .withRel("customer")
    );
}
~~~

This example uses Spring HATEOAS to create `self`, `cancel`, and `customer` relations. In a real application, the cancel link may only be added when the user has permission and the order is in an eligible status. In that case, tests should cover at least two scenarios:

- Cancelable order: the `cancel` relation is present.
- Non-cancelable order: the `cancel` relation is absent.

REST Docs can verify both contracts with required and optional descriptors depending on the test. If you want to ensure a link disappears in the appropriate state, write a dedicated test for the response without that link; do not simply mark it `optional` and skip testing the behavior.

## 7. MockMvc Test for HAL Responses

Illustrative test example:

~~~java
@WebMvcTest(OrderController.class)
@ExtendWith(RestDocumentationExtension.class)
class OrderHateoasDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void documentsOrderLinksAndEmbeddedItems() throws Exception {
        given(orderService.getById(42L)).willReturn(sampleOrder());

        mockMvc.perform(get("/orders/42")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andDo(document("orders/get-hateoas",
                links(
                    linkWithRel("self").description("Link to the order"),
                    linkWithRel("cancel").description("Cancel the order"),
                    linkWithRel("customer").description("Customer")
                ),
                responseFields(
                    fieldWithPath("id").description("Order ID"),
                    fieldWithPath("status").description("Order status"),
                    subsectionWithPath("_embedded.items")
                        .description("List of embedded items")
                )
            ));
    }
}
~~~

This is a skeleton example: `sampleOrder()`, `OrderService`, the controller, and Spring HATEOAS configuration must be provided in the project. Relation names and JSON paths must match the actual response received by the test. If the response uses the `orders` relation instead of `items`, adjust the descriptors and AsciiDoc to match the real contract.

## 8. Documenting Collections of Embedded Resources

With a HAL collection, the response may contain multiple resources of the same type:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {"href": "/orders/42"}
        }
      },
      {
        "id": 43,
        "status": "PENDING",
        "_links": {
          "self": {"href": "/orders/43"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/orders"},
    "profile": {"href": "/profile/orders"}
  }
}
~~~

Document links at the collection level:

~~~java
links(
    linkWithRel("self").description("List of orders"),
    linkWithRel("profile").description("Profile description of the collection")
)
~~~

Document the embedded collection:

~~~java
responseFields(
    subsectionWithPath("_embedded.orders")
        .description("List of embedded orders")
)
~~~

Or document the fields in detail:

~~~java
responseFields(
    fieldWithPath("_embedded.orders[].id").description("Order ID"),
    fieldWithPath("_embedded.orders[].status").description("Order status")
)
~~~

`self` links inside each collection element may need to be documented separately according to the response's hypermedia structure. Check the test's `links` snippet output and configure descriptors for the exact relations recognized by REST Docs at the embedded resource level; do not assume element-level links are always equivalent to root-level links.

## 9. Asciidoctor: Including Links and Embedded Fields

After tests generate snippets:

~~~text
build/generated-snippets/
└── orders/
    └── get-hateoas/
        ├── http-response.adoc
        ├── links.adoc
        └── response-fields.adoc
~~~

Include them in the documentation:

~~~adoc
== Get Order Details

=== HTTP response
include::{snippets}/orders/get-hateoas/http-response.adoc[]

=== Hypermedia links
include::{snippets}/orders/get-hateoas/links.adoc[]

=== Response fields
include::{snippets}/orders/get-hateoas/response-fields.adoc[]
~~~

The links section explains how clients navigate via relations. The response fields section explains business data and embedded subtrees. Readers can combine both to build clients without hard-coding every URL.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `links.adoc` not generated | `links(...)` was not called or response not recognized as hypermedia | Check content type, HAL payload, and REST Docs configuration |
| Newly added link causes test failure | Using `links(...)` without documenting the new relation | Add a descriptor or intentionally ignore it |
| Optional link causes test failure | Descriptor does not call `optional()` | Mark optional and write tests for both states |
| Links are not verified | Using `relaxedLinks(...)` | Use `links(...)` when a strict contract is required |
| `_embedded` missing from fields snippet | Field or subsection not declared | Use `subsectionWithPath` or full field paths |
| Duplicate child field descriptor | Describing both the subtree and child fields at the same level | Choose either the subtree or list child fields |
| Confusion over paths in embedded arrays | Mixing up response-level paths and relative paths | Use `[]` and inspect the sample payload |
| Missing descriptions for links in embedded items | Documenting only root links | Inspect links inside each resource and document at the appropriate level |
| Asciidoctor cannot find `links` snippet | Include has wrong identifier or filename | Check `generated-snippets` after tests |

## 11. Practice Exercise

Build a `GET /orders/{id}` endpoint returning HAL:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {"href": "/orders/42"},
    "customer": {"href": "/customers/7"}
  },
  "_embedded": {
    "items": [
      {"sku": "BOOK-01", "quantity": 2}
    ]
  }
}
~~~

Tasks:

1. Build the response using Spring HATEOAS `EntityModel` or an equivalent HAL structure.
2. Write a MockMvc test accepting `application/hal+json`.
3. Use `links(...)` and `linkWithRel(...)` to document `self` and `customer`.
4. Use `responseFields(...)` with `subsectionWithPath("_embedded.items")` to document the embedded collection.
5. Write an additional test documenting `sku` and `quantity` in detail using full field paths or `beneathPath(...)`.
6. If a relation only appears in certain states, use `optional()` and test both responses with and without that relation.
7. Include `http-response.adoc`, `links.adoc`, and `response-fields.adoc` in Asciidoctor.
8. Run tests and render documentation; cross-check snippets against the actual JSON.

**Completion criteria:** Link relations are documented with the `links` snippet; embedded resources are documented with payload fields/subsections; tests detect unexpected contract changes; documentation enables readers to understand both navigation and data structure.

## References

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring HATEOAS — Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring REST Docs — MockMvc](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
