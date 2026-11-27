# Reusing request field descriptors

## 1. Why reuse FieldDescriptors?

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests generate request/response snippets and descriptors to document the API contract. When multiple endpoints accept payloads with similar structures, rewriting the same group of field descriptors makes tests long, hard to update, and prone to inconsistent descriptions.

For example, endpoints for creating a product, importing products from a file, and updating a product all share common fields such as name, price, and description. If each test declares those fields on its own, a change in meaning or description must be edited in multiple places.

Spring REST Docs represents payload descriptions with FieldDescriptor. The requestFields(...) methods accept descriptors to generate the request-fields.adoc snippet and validate the actual payload against the descriptions. You can organize descriptors into constants, factory methods, or shared lists, and then combine them with each endpoint's own fields.

After this lesson, you will be able to:

- Identify shared field descriptors across multiple requests.
- Organize descriptors using factory methods that return new lists.
- Combine shared fields with operation-specific fields.
- Reuse descriptions for nested objects and subsections.
- Avoid accidentally sharing optional/ignored state across tests.
- Keep strict validation to detect payload changes that have not been updated in documentation.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. If you use WebTestClient or REST Assured, the client calls differ, but the FieldDescriptor lists can still be organized in a similar way.

## 2. FieldDescriptor and requestFields(...)

A request payload can be JSON:

```json
{
  "name": "Mechanical Keyboard",
  "description": "Mechanical keyboard for office use",
  "price": 89.5
}
```

Each field is described using fieldWithPath(...):

```java
requestFields(
    fieldWithPath("name").description("Product name"),
    fieldWithPath("description").description("Product description"),
    fieldWithPath("price").description("Selling price")
)
```

Each FieldDescriptor has a path, a description, and metadata such as optional, ignored, type, or attributes. requestFields(...) uses descriptors to:

1. Generate the field table for the documentation.
2. Match the descriptors against the request payload recorded by the test.
3. Fail if the payload contains an undocumented field or if a required descriptor is missing.

That is why reusing descriptors is better than copying a description table manually: the tests still enforce contract checking for each operation.

## 3. Approach 1: shared descriptor constants

If fields are identical in path and description, you can place them in a test helper class:

```java
package com.example.catalog.docs;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

import org.springframework.restdocs.payload.FieldDescriptor;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static final FieldDescriptor PRODUCT_NAME =
        fieldWithPath("name").description("Product name");

    public static final FieldDescriptor PRODUCT_DESCRIPTION =
        fieldWithPath("description").description("Product description");

    public static final FieldDescriptor PRODUCT_PRICE =
        fieldWithPath("price").description("Selling price");
}
```

Usage:

```java
document("products-create",
    requestFields(
        PRODUCT_NAME,
        PRODUCT_DESCRIPTION,
        PRODUCT_PRICE
    )
)
```

This approach is clear when descriptors share the same path, description, and optional/ignored state. However, FieldDescriptor has configuration methods such as optional() or ignored() that mutate the descriptor. You should not take a shared static instance and configure it differently across individual tests. A test marking a descriptor as optional can unintentionally affect another operation that uses the same instance.

If the same field is required at endpoint A but optional at endpoint B, a factory method that creates fresh descriptors for each operation is safer.

## 4. Approach 2: factory methods returning new descriptors

This is the preferred approach when descriptors have different states across endpoints. Each factory call creates new FieldDescriptor instances:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static List<FieldDescriptor> commonProductRequestFields() {
        return List.of(
            fieldWithPath("name").description("Product name"),
            fieldWithPath("description").description("Product description"),
            fieldWithPath("price").description("Selling price")
        );
    }
}
```

Usage:

```java
document("products-create",
    requestFields(ProductFieldDescriptors.commonProductRequestFields())
)
```

The requestFields(List<FieldDescriptor>) overload accepts a list of descriptors. List.of(...) returns a list to which elements cannot be added or removed; the factory creates fresh descriptors on every call.

### Creating different descriptor sets per contract

Suppose POST requires all fields, while PATCH allows individual fields to be absent:

```java
public static List<FieldDescriptor> productCreateFields() {
    return List.of(
        fieldWithPath("name").description("Product name"),
        fieldWithPath("description").description("Product description"),
        fieldWithPath("price").description("Selling price")
    );
}

public static List<FieldDescriptor> productUpdateFields() {
    return List.of(
        fieldWithPath("name").description("Product name").optional(),
        fieldWithPath("description").description("Product description").optional(),
        fieldWithPath("price").description("Selling price").optional()
    );
}
```

Each method creates new descriptors and clearly expresses the operation's contract. Do not take a shared list and call optional() on its descriptors in one test.

## 5. Combining shared fields with specific fields

Many endpoints share a common set of fields while still having specific fields. For example, creating a product has an additional initialStock; importing a product has an additional sourceSystem.

You can combine them using an ArrayList:

```java
static List<FieldDescriptor> productCreateWithStockFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductFieldDescriptors.commonProductRequestFields());

    fields.add(
        fieldWithPath("initialStock")
            .description("Initial stock quantity")
    );
    return fields;
}
```

Pass the combined list:

```java
document("products-create-with-stock",
    requestFields(productCreateWithStockFields())
)
```

Or add multiple specific fields:

```java
static List<FieldDescriptor> productImportFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductFieldDescriptors.commonProductRequestFields());
    fields.add(fieldWithPath("sourceSystem")
        .description("Source system of the record"));
    fields.add(fieldWithPath("externalId")
        .description("Product ID in the source system"));
    return fields;
}
```

Name factory methods after the operation or contract group so readers understand which list is being applied. Do not create a single list containing every field of every endpoint; strict validation loses its value if an operation has to describe fields that do not belong to its payload.

## 6. MockMvc example reusing descriptors across multiple operations

Suppose a controller has two endpoints for creating and importing products:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @PostMapping
    ProductResponse create(@RequestBody ProductRequest request) {
        return new ProductResponse(42L, request.name(), request.price());
    }

    @PostMapping("/import")
    ProductResponse importProduct(@RequestBody ProductImportRequest request) {
        return new ProductResponse(43L, request.name(), request.price());
    }

    record ProductRequest(String name, String description, BigDecimal price) {}
    record ProductImportRequest(
        String name, String description, BigDecimal price, String sourceSystem
    ) {}
    record ProductResponse(long id, String name, BigDecimal price) {}
}
```

Tests can share descriptors:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductRequestDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createProduct() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Keyboard",
                      "description": "Mechanical keyboard",
                      "price": 89.5
                    }
                    """))
            .andExpect(status().isOk())
            .andDo(document("products-create",
                requestFields(
                    ProductFieldDescriptors.commonProductRequestFields()
                )
            ));
    }

    @Test
    void importProduct() throws Exception {
        mockMvc.perform(post("/api/products/import")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Keyboard",
                      "description": "Mechanical keyboard",
                      "price": 89.5,
                      "sourceSystem": "ERP"
                    }
                    """))
            .andExpect(status().isOk())
            .andDo(document("products-import",
                requestFields(productImportFields())
            ));
    }
}
```

In this example, both operations share the descriptions for name, description, and price; the import operation adds sourceSystem. Each operation has its own ID, so snippets are written to separate folders. Descriptors still validate each respective payload; an undocumented import field causes the strict-mode test to fail.

## 7. Reusing descriptors for nested objects

A group of fields may repeat under different objects:

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

You cannot use the same street path for both objects in one payload because the path must identify the location. Create a factory that accepts a prefix:

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

static List<FieldDescriptor> checkoutFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.addAll(addressFields("shippingAddress", "shipping address"));
    fields.addAll(addressFields("billingAddress", "billing address"));
    return fields;
}
```

The factory generates different paths while reusing how the fields are described. If you want to document a nested object as a subsection instead of individual fields, consider subsectionWithPath(...). Once a subsection is documented, avoid duplicating both the entire subtree and individual child fields in the same descriptor list.

## 8. Organizing helpers in test sources

Documentation descriptors are typically only needed during tests, so you can place helpers in the test source set:

```text
src/
  test/
    java/
      com/example/catalog/
        docs/
          ProductFieldDescriptors.java
          AddressFieldDescriptors.java
        ProductRequestDocumentationTest.java
        ProductImportDocumentationTest.java
```

It is not necessary to create a helper for every single field. Organize by resource/aggregate or shared payload group. The goal is for test authors to find descriptors easily, understand their scope of use, and avoid maintaining overly complex abstractions.

Guidelines:

- Name methods after the payload or operation, such as commonProductRequestFields() and productImportFields().
- Use factories returning new lists if descriptors have different states across operations.
- Only share fields that have the same path, meaning, and optional/ignored rules.
- Keep operation-specific fields in that operation's corresponding factory.
- Avoid having test helpers depend on production controllers or services.
- Only create a test-fixture module if multiple test modules genuinely need to share them.

## 9. Strict validation, optional, and ignored when reusing

Reusing descriptors should not weaken contract checks:

| State | Meaning |
| --- | --- |
| Default | The field is expected in the payload and must be documented |
| optional() | The field may be absent |
| ignored() | The field is excluded from the table and descriptor checks |
| relaxedRequestFields(...) | Allows undocumented payload fields outside the descriptor list |

If a field is required on the create endpoint but optional on the update endpoint, do not share the same FieldDescriptor instance on which optional() was called. Create two separate lists using factories so state is not shared.

Only use ignored for fields genuinely outside the current documentation scope. Use relaxed mode when a test has a narrow scope; do not switch the entire suite to relaxed mode just to hide newly added undocumented fields.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Duplicate field in request-fields snippet | Two lists both add the same path. | Check paths before combining lists and keep a single source per field. |
| One test causes another test to treat a field as optional | Sharing a FieldDescriptor instance and mutating its state. | Create fresh descriptors via a factory for each operation. |
| Import endpoint reports an undocumented field | Used only the basic field list and forgot specific fields. | Append the specific descriptors to the shared list. |
| Create endpoint requires a field absent from the payload | Using one descriptor set for different request shapes. | Create factories tailored to each operation's contract. |
| Nested field is not recognized | Path is missing a prefix or does not match JSON structure. | Use the full path such as shippingAddress.street. |
| Documentation fails to detect new fields | Using relaxedRequestFields too broadly. | Return to strict mode or narrow the relaxed descriptors. |
| Helper class is hard to understand | Putting every field of every resource into one class. | Split helpers by payload/resource and name them by scope. |

## 11. Practice exercise

Build a Catalog API with three request shapes:

1. POST /api/products: accepts name, description, price.
2. POST /api/products/import: accepts the fields above plus sourceSystem.
3. PATCH /api/products/{id}: accepts updatable fields that may be absent.

Steps:

1. Create a ProductFieldDescriptors helper with a factory returning the basic fields.
2. Use the factory in the create and import tests; append sourceSystem for the import operation.
3. Create a separate factory for update, marking fields optional according to the PATCH contract.
4. Run the tests and compare request-fields.adoc across the three operations.
5. Try sharing a descriptor instance and calling optional in one operation; observe the risk of state leakage, then replace it with a factory creating new instances.
6. Add shippingAddress and billingAddress, using a factory that takes a prefix to create path descriptors.
7. Run clean test and Asciidoctor; verify that snippets are generated per operation and strict validation still catches undocumented fields.

**Completion criteria:** organize shared descriptors without duplicating definitions; combine endpoint-specific fields; reuse nested path structures; avoid leaking optional/ignored state across operations; preserve contract checks and generate documentation from tests.

## 12. References

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/FieldDescriptor.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
