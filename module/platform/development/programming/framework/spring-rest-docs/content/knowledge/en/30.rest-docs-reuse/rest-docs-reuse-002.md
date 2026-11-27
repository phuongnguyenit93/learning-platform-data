# Reusing response field descriptors

## 1. Why reuse response field descriptors?

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests generate snippets from actual responses and use field descriptors to describe the payload contract. Many endpoints often return the same structure or a shared portion of data: product details, user information, addresses, pagination metadata, or error objects. If each test redeclares the fields on its own, documentation easily diverges in wording, becomes inconsistent, and takes extra effort to maintain.

Spring REST Docs represents JSON response descriptions using FieldDescriptor. The responseFields(...) methods accept descriptors, generate the response-fields.adoc snippet, and validate the payload structure recorded by the test. You can group shared fields into factory methods and then append operation-specific fields for each endpoint.

For example, many APIs return:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

The id, name, and price fields can share descriptions. However, a detail endpoint may additionally return description and inventory; a search endpoint may return a list of products along with page metadata. Reusing descriptors must preserve the exact payload scope of each operation.

After this lesson, you will be able to:

- Create shared response FieldDescriptor sets for multiple operations.
- Use factory methods returning new descriptors to avoid unintended state sharing.
- Combine shared fields with response-specific fields.
- Reuse descriptors for nested objects, arrays, and response envelopes.
- Handle optional, ignored, and relaxed response fields.
- Keep strict validation to detect response changes that have not been updated in documentation.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. With WebTestClient or REST Assured, the client calls differ, but organizing FieldDescriptors can still be shared.

## 2. responseFields(...) and FieldDescriptor

A JSON response:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true
}
```

Can be documented with:

```java
responseFields(
    fieldWithPath("id").description("Product ID"),
    fieldWithPath("name").description("Product name"),
    fieldWithPath("price").description("Selling price"),
    fieldWithPath("active").description("Whether the product is active for sale")
)
```

Each FieldDescriptor describes a path in the response along with details such as description, type, optional, ignored, or attributes. responseFields(...) uses these descriptors to:

1. Generate the field table for the documentation.
2. Verify the actual fields in the response.
3. Detect undocumented fields or required descriptors missing from the payload.

As a result, descriptors are not just presentation data. They also help tests enforce the contract between server and client.

## 3. Creating factory methods for shared response fields

Place documentation support descriptors in the test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductResponseDescriptors {
    private ProductResponseDescriptors() {}

    public static List<FieldDescriptor> productSummaryFields() {
        return List.of(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name"),
            fieldWithPath("price").description("Selling price")
        );
    }
}
```

Usage in an operation:

```java
document("products-find",
    responseFields(ProductResponseDescriptors.productSummaryFields())
)
```

Each call to the factory creates a new list and new FieldDescriptors. List.of(...) does not allow adding or removing elements, preventing unintended structural modifications to the descriptor set.

### Why is a factory more useful than a static instance?

FieldDescriptor provides configuration methods such as optional() and ignored(). These methods configure the descriptor instance they are called on. If you keep a static instance and mutate its state in a test, one operation can affect the descriptor used by another operation.

A factory method avoids sharing an instance already configured for a specific context. This is the right choice when a field is required in response A but may be absent in response B.

## 4. Combining shared fields with specific fields

One endpoint may return summary fields while another returns additional metadata or related information. Create a new list and append the specific fields:

```java
static List<FieldDescriptor> productDetailFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductResponseDescriptors.productSummaryFields());

    fields.add(
        fieldWithPath("description")
            .description("Detailed product description")
    );
    fields.add(
        fieldWithPath("inventory.available")
            .description("Available quantity for sale")
    );
    return fields;
}
```

Usage:

```java
document("products-detail",
    responseFields(productDetailFields())
)
```

Another endpoint might additionally return publication status:

```java
static List<FieldDescriptor> productAdminFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductResponseDescriptors.productSummaryFields());
    fields.add(
        fieldWithPath("published")
            .description("Whether the product is published")
    );
    fields.add(
        fieldWithPath("createdAt")
            .description("Product creation timestamp")
    );
    return fields;
}
```

Do not lump every field of every response into a single global descriptor set. Doing so forces each operation to describe fields that do not belong to its response, or forces overly broad use of ignored/relaxed. Reuse the genuinely shared contract and keep specific fields in dedicated factories.

## 5. Reusing nested object descriptors

Responses may share nested objects such as addresses, creator details, or monetary values. For example:

```json
{
  "shippingAddress": {
    "street": "1 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  },
  "billingAddress": {
    "street": "2 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  }
}
```

Descriptor paths must include a prefix to distinguish positions:

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

static List<FieldDescriptor> checkoutResponseFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.addAll(addressFields("shippingAddress", "shipping address"));
    fields.addAll(addressFields("billingAddress", "billing address"));
    return fields;
}
```

A factory taking a prefix reuses how fields are described while generating distinct paths for each object. If you only want to treat a subtree as a single unit, you can use subsectionWithPath(...). Once a subsection is documented, avoid also listing all child fields redundantly in the same table if that makes the documentation repetitive.

## 6. Reusing descriptors for arrays and collections

Collection responses typically contain an array:

```json
{
  "items": [
    {"id": 42, "name": "Keyboard", "price": 89.5},
    {"id": 43, "name": "Mouse", "price": 29.0}
  ],
  "totalElements": 2
}
```

Descriptors can document fields inside elements using wildcard paths:

```java
static List<FieldDescriptor> productItemFields(String prefix) {
    return List.of(
        fieldWithPath(prefix + "id").description("Product ID"),
        fieldWithPath(prefix + "name").description("Product name"),
        fieldWithPath(prefix + "price").description("Selling price")
    );
}

static List<FieldDescriptor> productSearchResponseFields() {
    List<FieldDescriptor> fields = new ArrayList<>(
        productItemFields("items[].")
    );
    fields.add(
        fieldWithPath("totalElements")
            .description("Total number of matching products")
    );
    return fields;
}
```

In Spring REST Docs JSON paths, the wildcard syntax [] represents array elements. Verify the actual path and REST Docs version when applying this to nested arrays or complex structures. Descriptors must match the response data received by the test.

Another approach is using a subsection descriptor for the array if the documentation only needs to acknowledge that elements exist as a group without a table of every field. Choose the level of detail suited to API consumers.

## 7. Organizing shared response envelopes

Many APIs wrap data inside a response envelope:

```json
{
  "data": {
    "id": 42,
    "name": "Keyboard"
  },
  "meta": {
    "requestId": "req-test-01"
  }
}
```

If every endpoint uses the same data/meta structure, you can create factories with prefixes:

```java
static List<FieldDescriptor> responseMetadataFields() {
    return List.of(
        fieldWithPath("meta.requestId")
            .description("Request ID for tracing")
    );
}

static List<FieldDescriptor> productEnvelopeFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.add(fieldWithPath("data.id").description("Product ID"));
    fields.add(fieldWithPath("data.name").description("Product name"));
    fields.addAll(responseMetadataFields());
    return fields;
}
```

If the data structure varies across endpoints, split the factories accordingly. Do not assume every response shares the same payload just because they are wrapped in the same envelope.

## 8. MockMvc example reusing response descriptors

Suppose two endpoints return a product, where the detail endpoint includes description and inventory:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetail find(@PathVariable long id) {
        return new ProductDetail(
            id, "Mechanical Keyboard", 89.5,
            "Mechanical keyboard", 12
        );
    }

    @GetMapping("/{id}/summary")
    ProductSummary summary(@PathVariable long id) {
        return new ProductSummary(id, "Mechanical Keyboard", 89.5);
    }

    record ProductSummary(long id, String name, double price) {}
    record ProductDetail(
        long id, String name, double price,
        String description, int available
    ) {}
}
```

Test:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductResponseDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void productSummary() throws Exception {
        mockMvc.perform(get("/api/products/{id}/summary", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("products-summary",
                responseFields(
                    ProductResponseDescriptors.productSummaryFields()
                )
            ));
    }

    @Test
    void productDetail() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("products-detail",
                responseFields(productDetailFields())
            ));
    }
}
```

The two operations reuse the descriptions for id, name, and price; the detail operation adds description and available. Each operation has its own ID, so response-fields.adoc snippets are generated in separate folders. If the server adds a field outside the descriptors, strict validation fails so the documentation gets updated.

## 9. Optional, ignored, and relaxed response fields

A response may vary depending on resource state or user permissions. A field can be optional:

```java
fieldWithPath("publishedAt")
    .description("Publication timestamp")
    .optional()
```

An internal field can be excluded from the table:

```java
fieldWithPath("internalVersion")
    .ignored()
```

These options have different meanings:

| Usage | Meaning |
| --- | --- |
| Default descriptor | Field is documented and verified in strict mode |
| optional() | Field may be absent |
| ignored() | Field is omitted from the table and not verified as a documented field |
| relaxedResponseFields(...) | Allows other fields to exist outside the descriptor set |

Do not share a single FieldDescriptor instance across multiple tests if any test needs to alter its optional/ignored state. Create fresh descriptors in a factory so each operation has an independent configuration.

Relaxed mode is useful when a response contains many fields outside the current documentation scope or when documentation focuses on only part of the payload. However, if every response uses relaxed mode, the server can change or add fields without tests reminding the team to update the documentation.

## 10. Splitting descriptors by response variant

An endpoint may return multiple response shapes depending on the state:

- Success: full object.
- Not found: problem detail.
- No content: 204 No Content.
- Unauthenticated or unauthorized: error response with its own structure.

Do not use one response field descriptor set for completely different payloads. Create separate operation IDs for each important scenario and corresponding descriptor factories:

```java
document("products-find-success",
    responseFields(productSummaryFields())
);

document("products-find-not-found",
    responseFields(problemDetailFields())
);
```

If a 204 response has no body, do not call responseFields(...) just to generate an empty table. Use the HTTP response snippet along with status/header assertions to record the contract accurately.

## 11. Organizing helper classes

Helpers can be placed in the test source set:

```text
src/
  test/
    java/
      com/example/catalog/
        docs/
          ProductResponseDescriptors.java
          AddressResponseDescriptors.java
          ProblemResponseDescriptors.java
        ProductResponseDocumentationTest.java
```

Guidelines:

- Split helpers by resource or response group sharing the same contract.
- Method names should describe the payload, such as productSummaryFields() and productDetailFields().
- Factories should return new descriptors whenever optional/ignored differs.
- Keep specific fields in dedicated helpers for each response variant.
- Only share fields with the same path and meaning; do not share simply because field names happen to match.
- Do not let test documentation helpers depend on production services/controllers.

A status field can carry different meanings between a domain response and an HTTP status code. Descriptors only document JSON paths, so write clear descriptions so readers do not confuse a body field with an HTTP status.

## 12. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Duplicate response field | Combining two factories that create the same path. | Inspect paths and establish a single descriptor source. |
| One test affects another test's optional state | Sharing a FieldDescriptor instance and mutating its state. | Have factories create fresh instances per operation. |
| Detail endpoint is missing field descriptors | Using only the summary factory. | Append the detail response's specific fields. |
| Test reports an undocumented field | New payload includes a field outside descriptors in strict mode. | Update the contract/descriptors or use scoped relaxed mode. |
| Test reports a required field is missing | Descriptor is not optional, yet the response omits the field. | Fix the implementation or mark optional if allowed by the contract. |
| Nested path mismatch | Wrong prefix or JSON path. | Check the response body and use the full path. |
| Array descriptor mismatch | Wrong wildcard or nested array structure. | Check path notation and actual test payload. |
| Table is too long or repetitive | Documenting every subtree field when only an overview is needed. | Use a subsection descriptor or split pages/operations. |

## 13. Practice exercise

Build a Catalog API with three responses:

1. GET /api/products/{id}/summary returns id, name, and price.
2. GET /api/products/{id} returns summary fields plus description and inventory.available.
3. GET /api/products returns an items array along with totalElements.

Steps:

1. Create ProductResponseDescriptors.productSummaryFields() returning fresh descriptors.
2. Create productDetailFields() by combining summary fields with detail fields.
3. Create a factory accepting a prefix to document nested addresses in shippingAddress and billingAddress.
4. Create descriptors for items[] and totalElements in the collection response.
5. Write MockMvc tests using responseFields(...) with separate operation IDs.
6. Try optional, ignored, and relaxedResponseFields; note the differences in strict validation.
7. Run clean test and Asciidoctor; compare response-fields.adoc across summary, detail, and collection.

**Completion criteria:** reuse response descriptors without duplicating descriptions; properly append response-specific fields; handle nested paths and arrays; keep optional/ignored independent; strict validation catches unintended contract changes.

## 14. References

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/FieldDescriptor.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
