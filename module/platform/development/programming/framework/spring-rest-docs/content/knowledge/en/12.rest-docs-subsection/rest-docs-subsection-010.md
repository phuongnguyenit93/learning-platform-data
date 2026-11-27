# Reusing a Subsection Across Multiple Operations in Spring REST Docs

## 1. When Should You Reuse a Subsection?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. Each test executes an HTTP exchange and generates snippets describing the request, response, payload, headers, or parameters. The snippets are compiled into Asciidoctor/Markdown documentation and integrated into the build and CI pipeline.

In an API, the same data structure often appears across multiple operations. For example, a `customer` object may appear in:

- `GET /orders/{id}`: customer information for the order;
- `GET /invoices/{id}`: customer information recorded on the invoice;
- `POST /orders`: customer information sent in the order creation request;
- `PATCH /customers/{id}`: part of the customer information being updated.

If those operations genuinely share the same schema, rewriting descriptors in every test creates duplication, makes synchronization harder, and makes it easy to miss updates when the contract changes. You can extract the field descriptions into a reusable helper.

This lesson focuses on:

- reusing a subsection's descriptors across multiple operations;
- creating fresh descriptors via a helper/factory to avoid unintended shared state;
- separating the shared schema from operation-specific extractor paths and operation identifiers;
- sharing structures across requests or responses when their respective contracts match;
- organizing snippets by operation while maintaining strict verification;
- recognizing cases where you should not reuse descriptors because the schema or business meaning differs.

**Foundational principle:** reuse schema descriptions when contracts match; keep paths, operations, and contextual explanations separate per endpoint.

## 2. Example: A `customer` Object Appearing Across Multiple Operations

Suppose APIs share the same customer structure:

```json
{
  "id": "cus-42",
  "displayName": "Ha Nguyen",
  "contact": {
    "email": "ha@example.test",
    "phone": "0900000000"
  }
}
```

In the order response, the object sits at `customer`. In the invoice response, it also sits at `customer`, whereas in another operation it might sit at `buyer` or `accountHolder`.

A detailed field table for the customer object might describe:

| Relative Path in Object | Meaning |
| --- | --- |
| `id` | Customer ID |
| `displayName` | Display name |
| `contact.email` | Contact email |
| `contact.phone` | Contact phone number |

If all operations commit to this schema, a factory can produce the shared descriptor set. Each test still selects the subsection with its own path:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    customerFields()
)
```

For invoices, the same schema is used with its own operation identifier:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    customerFields()
)
```

The two calls look identical for the fragment, yet are placed inside distinct `document("orders-get", ...)` and `document("invoices-get", ...)` calls. Snippets are written into each operation's own directory; filenames can be identical without overwriting each other.

## 3. Separating Three Components for Reuse

When designing a helper, distinguish:

| Component | Example | Can Be Shared? |
| --- | --- | --- |
| Fragment field schema | `id`, `displayName`, `contact.email` | Yes, if contract and field meanings match |
| Path in root payload | `customer`, `buyer`, `accountHolder` | Not by default; declare per operation |
| Operation identifier | `orders-get`, `invoices-get` | Each snippet set needs an identifier matching the operation/scenario |
| Subsection ID | `customer`, `buyer` | Can match across two operations in different directories; within the same operation avoid colliding snippet types |
| Business description prose | "Customer placing the order", "Buyer on the invoice" | Usually needs to be tailored to context, even when schemas match |

This separation keeps the helper focused on a single responsibility: describing the child schema. It should not decide which endpoint is being documented, which path points to the fragment, or which business context readers need.

### 3.1. Relative Paths and `beneathPath`

A helper contains paths relative to the fragment root:

```java
fieldWithPath("id")
fieldWithPath("displayName")
fieldWithPath("contact.email")
fieldWithPath("contact.phone")
```

When extracting `customer`, use:

```java
beneathPath("customer")
```

When extracting `buyer`, use:

```java
beneathPath("buyer")
```

Do not include `customer.` in the helper if you intend to reuse it for different paths. If absolute paths are hardcoded inside the helper, the same helper cannot be applied to `buyer`.

### 3.2. Operation Identifier and Subsection ID

`document("orders-get", ...)` determines the operation's snippet directory. `withSubsectionId("customer")` sets the suffix for the subsection snippet inside that directory. Two different operations can both generate `response-fields-customer.adoc` without overwriting each other:

```text
build/generated-snippets/
├── orders-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
└── invoices-get/
    ├── response-fields.adoc
    └── response-fields-customer.adoc
```

However, within the **same operation**, two handlers of the same kind using subsection ID `customer` will target the same filename. If they describe different content, assign distinct meaningful IDs such as `billing-customer` and `shipping-customer`.

## 4. Building a Helper That Creates Shared Descriptors

A straightforward approach is to write a factory returning a `FieldDescriptor` array:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

final class CustomerDocumentation {

    private CustomerDocumentation() {
    }

    static FieldDescriptor[] customerFields() {
        return new FieldDescriptor[] {
            fieldWithPath("id")
                .description("Customer ID"),
            fieldWithPath("displayName")
                .description("Display name"),
            fieldWithPath("contact.email")
                .description("Contact email address"),
            fieldWithPath("contact.phone")
                .optional()
                .description("Contact phone number, if available")
        };
    }
}
```

The factory creates **fresh descriptors on every call**. This makes it clear that each snippet can configure descriptions, optionality, or types as needed without depending on a descriptor array already used in another test.

Do not bundle operation identifiers, extractor paths, and document headings into this helper class. Keep the helper focused on the shared field schema.

### 4.1. Using It in the GET Orders Operation

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id")
            .description("Order ID"),
        fieldWithPath("status")
            .description("Order status"),
        subsectionWithPath("customer")
            .description("Customer associated with the order"),
        subsectionWithPath("total")
            .description("Total order value")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        CustomerDocumentation.customerFields()
    )
));
```

### 4.2. Using It in the GET Invoices Operation

```java
.andDo(document("invoices-get",
    responseFields(
        fieldWithPath("id")
            .description("Invoice ID"),
        fieldWithPath("number")
            .description("Invoice number"),
        subsectionWithPath("customer")
            .description("Customer recorded on the invoice"),
        subsectionWithPath("amount")
            .description("Total invoice amount")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        CustomerDocumentation.customerFields()
    )
));
```

Both operations use the same factory, yet the parent table's description remains context-specific: one describes the customer associated with the order, and the other describes the customer recorded on the invoice. This keeps the schema consistent while keeping the documentation accurate to each operation.

## 5. Complete MockMvc Example with Two Operations

The following example illustrates a test class using two endpoints and the same helper. Requirements: Java 17+, JUnit 5, Spring MVC Test, and `spring-restdocs-mockmvc` on the test classpath.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SharedCustomerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderCustomer() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-901")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-42"))
                .andDo(document("orders-get",
                        responseFields(
                                fieldWithPath("id").description("Order ID"),
                                fieldWithPath("status").description("Order status"),
                                subsectionWithPath("customer")
                                        .description("Customer associated with the order")
                        ),
                        responseFields(
                                beneathPath("customer").withSubsectionId("customer"),
                                customerFields()
                        )
                ));
    }

    @Test
    void documentInvoiceCustomer() throws Exception {
        mockMvc.perform(get("/invoices/{id}", "inv-901")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-42"))
                .andDo(document("invoices-get",
                        responseFields(
                                fieldWithPath("id").description("Invoice ID"),
                                fieldWithPath("number").description("Invoice number"),
                                subsectionWithPath("customer")
                                        .description("Customer recorded on the invoice")
                        ),
                        responseFields(
                                beneathPath("customer").withSubsectionId("customer"),
                                customerFields()
                        )
                ));
    }

    private static FieldDescriptor[] customerFields() {
        return new FieldDescriptor[] {
            fieldWithPath("id").description("Customer ID"),
            fieldWithPath("displayName").description("Display name"),
            fieldWithPath("contact.email").description("Contact email"),
            fieldWithPath("contact.phone").optional()
                    .description("Phone number if available")
        };
    }

    @RestController
    static class SampleController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> order(@PathVariable("id") String id) {
            if (!"ord-901".equals(id)) {
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {
                          "id": "ord-901",
                          "status": "PAID",
                          "customer": {
                            "id": "cus-42",
                            "displayName": "Ha Nguyen",
                            "contact": {
                              "email": "ha@example.test",
                              "phone": "0900000000"
                            }
                          }
                        }
                        """);
        }

        @GetMapping(value = "/invoices/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> invoice(@PathVariable("id") String id) {
            if (!"inv-901".equals(id)) {
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {
                          "id": "inv-901",
                          "number": "INV-901",
                          "customer": {
                            "id": "cus-42",
                            "displayName": "Ha Nguyen",
                            "contact": {
                              "email": "ha@example.test",
                              "phone": "0900000000"
                            }
                          }
                        }
                        """);
        }
    }
}
```

In the example, `customerFields()` is a private method on the test class to illustrate the point of reuse. For a large project, move the factory into its own class like `CustomerDocumentation` so multiple test classes can call it. The two operations generate snippets in different directories, so sharing the subsection ID `customer` causes no collision.

## 6. When Paths Differ but the Schema Matches

A customer structure might sit at different paths in different responses:

- `orders-get`: `customer`;
- `shipments-get`: `recipient.customer`;
- `invoices-get`: `buyer`.

If the leaf object's schema is the same, the factory can still be reused. Only the extractor changes:

```java
responseFields(
    beneathPath("recipient.customer")
        .withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

or:

```java
responseFields(
    beneathPath("buyer")
        .withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

The helper contains only the object's relative paths. Do not hardcode root path prefixes inside each descriptor. This allows the same schema set to be reused across different response structures.

However, verify that the objects at those paths share **the same contract**. If `recipient.customer` lacks `contact.phone` or `buyer` adds a required `taxId`, reusing the factory verbatim can cause strict tests to fail. That is a signal to split the schema or model a variant rather than automatically relaxing everything.

## 7. Reusing a Schema for Request and Response

`PayloadDocumentation` uses field descriptors in both `requestFields(...)` and `responseFields(...)`, so the same object structure can be documented in both requests and responses when their schemas genuinely match.

For example, `customer` in an order creation request:

```java
requestFields(
    beneathPath("customer").withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

And in an order retrieval response:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    CustomerDocumentation.customerFields()
)
```

Using the same factory does not mean every system should share request and response schemas. Contracts often differ:

- A request may only require `id` and `displayName`, whereas the response returns `contact` as well.
- A request may contain an editable note field; the response has server-generated audit fields.
- A response may mask sensitive information, whereas a request carries tokens or different input fields.
- A read-only or write-only field must be described according to its data direction.

In those cases, clearly separate `customerRequestFields()` and `customerResponseFields()`. You can share a small sub-helper for genuinely identical fields, but do not force both into one shared schema solely to save lines of code.

## 8. Reusing Descriptions While Preserving Separate Context

Even when field descriptors are shared, the parent table's description can vary by operation:

```java
// Orders
subsectionWithPath("customer")
    .description("Customer who owns the order")

// Invoices
subsectionWithPath("customer")
    .description("Buyer information recorded on the invoice")
```

This is not a contradiction if the object's role in the two contracts differs. However, if two descriptions express substantially different semantics, revisit whether they truly share a common business schema.

You can create helpers for field descriptors and separate helpers for subsections in some cases, but avoid hiding context-dependent prose inside a shared factory such that readers lose sight of what the operation is describing.

A useful rule of thumb:

- **Field schema:** reuse when field names, types, optionality, and semantics match.
- **Extractor path:** declare at each operation.
- **Parent description:** write according to the fragment's role in that endpoint.
- **Operation ID:** assign separately per HTTP action/scenario.
- **Subsection ID:** use consistently for the fragment type, provided snippet names of the same kind do not collide within one operation.

## 9. When Should You Not Reuse?

Do not share a helper merely because two JSON payloads share an object name.

| Situation | Sign | How to Handle |
| --- | --- | --- |
| Different schemas | One object has a required field the other lacks | Split factories or create explicit variant factories |
| Different semantics | `status` in customer means account status, elsewhere means moderation status | Describe separately; consider separate schemas |
| Request/response differences | One side has write-only fields, the other read-only | Separate request descriptors and response descriptors |
| Different API versions | V1 lacks `contact.phone`, V2 includes it | Maintain versioned contracts; avoid one helper masking differences |
| Different optionality | One operation requires phone, another allows omitting it | Separate factories or explicit configuration per contract |
| Different nesting structure | One object uses `contact.email`, the other uses `emailAddress` | Separate mappings/descriptors; do not force a shared path |

If you have two contract versions, you can name helpers by version:

```java
customerV1Fields()
customerV2Fields()
```

If the difference is only a single optional field while remaining semantics match, you can build a base helper and an extended factory. Still, prioritize clarity of the contract over an overly generic, hard-to-read helper suite.

## 10. Snippet Naming and Avoiding Overwrites

The operation identifier creates the snippet directory, while the subsection ID creates the file suffix. For example:

```text
build/generated-snippets/
├── orders-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
├── invoices-get/
│   ├── response-fields.adoc
│   └── response-fields-customer.adoc
└── shipments-get/
    ├── response-fields.adoc
    └── response-fields-customer.adoc
```

Snippet names can match across different operation directories. Within the same directory, however, two field tables of the same kind must not accidentally share a subsection ID:

```java
// Avoid: both write response-fields-customer.adoc
responseFields(beneathPath("billingCustomer")
    .withSubsectionId("customer"), billingCustomerFields());

responseFields(beneathPath("shippingCustomer")
    .withSubsectionId("customer"), shippingCustomerFields());
```

Use `billing-customer` and `shipping-customer` if both tables must coexist in the same operation.

Body and field snippets have different prefixes, so a body snippet and a field table can share a subsection ID—for example, `response-body-customer.adoc` and `response-fields-customer.adoc`.

## 11. Asciidoctor: Reusing Descriptors Does Not Mean Reusing Include Paths

Although the same factory generates schemas for multiple operations, each operation has its own snippet directory. For example:

```asciidoc
== GET /orders/{id}

include::{snippets}/orders-get/response-fields-customer.adoc[]

== GET /invoices/{id}

include::{snippets}/invoices-get/response-fields-customer.adoc[]
```

You can create a shared Asciidoctor fragment if both pages genuinely need the exact same content and context. However, if the explanation of `customer` differs by operation, write two separate explanatory paragraphs and reuse only the appropriate schema table portion.

Never write a hardcoded `include` path using only the subsection ID while forgetting the operation identifier. The filename `response-fields-customer.adoc` alone is not enough to locate the snippet; the operation directory is also required.

## 12. Build and CI

Example Gradle Groovy DSL configuration, assuming the Asciidoctor plugin is applied and REST Docs is configured to write snippets to `build/generated-snippets`:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Run:

```bash
./gradlew clean test asciidoctor
```

In CI:

1. Run all operation tests that use the shared schema.
2. Ensure each operation's fixture reflects the same contract that the helper describes.
3. Verify strict tests catch undocumented new fields across all relevant operations.
4. Confirm snippets are generated in the right operation directory and subsection ID name.
5. Run Asciidoctor after tests to catch missing `include` files.
6. Review factory changes whenever a shared contract changes; avoid an edit silently altering documentation for multiple endpoints without verification.

Reusing a helper means a single schema change can affect multiple operations. That is an advantage when the contract is truly shared, and it also means CI must execute all tests using the helper. With Maven, snippets are typically saved in `target/generated-snippets`, and the documentation build step must run after tests.

## 13. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Helper cannot be used for an object at another path | Descriptors hardcoded the `customer.` prefix | Use relative paths in the helper and select `beneathPath` outside |
| Invoice operation test fails when using customer helper | Invoice schema is not identical to order customer | Verify the contract, split helpers, or model a variant |
| Two operations overwrite snippets | Shared the same operation identifier directory for different doc sets | Assign distinct identifiers per operation/scenario |
| Two fragments in one operation write to the same file | Duplicate subsection ID for two snippets of the same kind | Assign distinct IDs by role |
| Request test fails because response descriptors don't match | Request and response differ in schema or optionality | Separate request and response factories |
| Detailed table misses a new field in one operation | That operation's test did not run or used relaxed mode | Run all strict tests and check the pipeline |
| Fragment descriptions look alike but context is wrong | Shared an overly generic parent description | Write descriptions per operation; share only field schemas |
| `include` cannot find snippet | Missing operation folder or wrong subsection suffix | Check identifier, ID, and actual output |

## 14. Practice Exercise

Create a helper for the `customer` schema and use it in two operations, `orders-get` and `invoices-get`:

1. **Create the factory:** write `customerFields()` returning descriptors for `id`, `displayName`, `contact.email`, and `contact.phone`.
2. **Use in two operations:** create MockMvc tests for `GET /orders/{id}` and `GET /invoices/{id}`; both call the factory while using distinct operation identifiers.
3. **Change the path:** in the second test, simulate the object located at `buyer`. Keep the helper using relative paths and change `beneathPath("customer")` to `beneathPath("buyer")`.
4. **Test schema drift:** add `customer.segment` only to the orders response. Confirm the orders test catches the new field while the invoices test is unaffected if the invoice response did not change.
5. **Test optionality differences:** make `phone` required in one contract and optional in the other. Decide whether two separate factories are needed and explain based on semantics.
6. **Check filenames:** open both operation directories in `build/generated-snippets` and confirm both contain `response-fields-customer.adoc` without overwriting one another.
7. **Compile docs:** include the customer table from both operations in their respective documents and run `./gradlew clean test asciidoctor`.

**Completion criteria:** you can reuse descriptors without hardcoding root paths, distinguish shared schemas from operation-specific context, and have tests proving every operation using the helper is checked when the contract changes.

## 15. Self-Check Questions

**1. Can the same set of field descriptors be reused across multiple operations?**

Yes, if the schema, semantics, optionality, and data types are genuinely identical. Use a factory that creates fresh descriptors for each snippet.

**2. Should the subsection path be placed inside the helper?**

No, if you want to reuse it across multiple locations. Keep relative paths inside field descriptors and select the root path with `beneathPath(...)` in each operation.

**3. Why can two operations use the same subsection ID without file collisions?**

Because they reside in two different operation directories. Within the same operation, however, avoid two snippets of the same kind sharing the same suffix.

**4. Should request and response descriptors be shared?**

Only when the bidirectional contract is truly identical. If there are read-only, write-only, or differing optional fields, separate the descriptor sets.

**5. Does reusing a helper make strict tests run automatically for every operation?**

No. Every operation test using the helper still needs to run in the build/CI. The helper only shares description code; it does not replace executing the tests.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, subsection extraction, and documenting request/response payloads.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): MockMvc, WebTestClient, REST Assured configuration, snippet generation, and Asciidoctor/build integration.
