# Naming Subsection Snippets by Operation in Spring REST Docs

## 1. Why Do We Need Snippet Naming Conventions?

**Spring REST Docs** generates REST API documentation from HTTP tests executed with **MockMvc**, **WebTestClient**, or **REST Assured**. Whenever a test calls `document(...)` with an identifier, REST Docs writes the corresponding snippets into that identifier's directory. When a payload has nested objects or arrays, `beneathPath(...)` can create additional body snippets or field tables dedicated to a subsection.

When an API has multiple operations—such as `GET /orders/{id}`, `POST /orders`, and `PATCH /orders/{id}`—each operation may share a `customer` or `items` branch. Consistent snippet naming helps authors:

- identify which operation a snippet belongs to;
- distinguish the overview table from each subsection's detailed table;
- avoid overwriting or referencing the wrong file when one operation has multiple fragments;
- keep `include` directives in Asciidoctor readable and maintainable;
- adjust presentation while keeping identifiers stable.

This lesson distinguishes the **operation identifier** from the **subsection ID**, establishes naming conventions, generates multiple snippets for the same operation, and references them in documentation.

## 2. Two Naming Levels: Operation and Subsection

Spring REST Docs uses two values with distinct responsibilities:

The **operation identifier** is the first argument to `document("orders-get", ...)`. It determines the directory where that documentation call's snippets are written. With the identifier `orders-get`, the default directory in Gradle is typically:

```text
build/generated-snippets/
└── orders-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
```

The actual snippets depend on which handlers were invoked. The identifier should represent the operation or documentation scenario, such as `orders-get`, `orders-create`, or `orders-cancel`.

The **subsection ID** is set on an extractor using `withSubsectionId("customer")` or `withSubsectionId("items")`. It determines the filename suffix of the extracted snippet. For example:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer"),
    fieldWithPath("id").description("Customer ID"),
    fieldWithPath("displayName").description("Display name")
)
```

Inside the `orders-get` directory, the handler above generates `response-fields-customer.adoc`. If you also call `responseBody(beneathPath("customer").withSubsectionId("customer"))`, the corresponding body snippet is named `response-body-customer.adoc`.

The combined structure is:

```text
build/generated-snippets/
└── orders-get/                    <- operation identifier
    ├── response-fields.adoc       <- overview table
    ├── response-fields-customer.adoc
    ├── response-body-customer.adoc
    ├── response-fields-items.adoc
    └── response-body-items.adoc
```

**Remember:** the operation identifier determines the *snippet group per operation/scenario*; the subsection ID determines the *documented branch within that group*. A subsection ID does not create a new directory.

## 3. Rules for Naming Operation Identifiers

Choose short identifiers that describe the endpoint and action without depending on prose sentences in the documentation. A straightforward convention is:

```text
<resource>-<operation>
```

Examples:

| HTTP method and endpoint | Suggested operation identifier | Meaning |
| --- | --- | --- |
| `GET /orders/{id}` | `orders-get` | Retrieve a single order |
| `GET /orders` | `orders-list` | List orders |
| `POST /orders` | `orders-create` | Create an order |
| `PATCH /orders/{id}` | `orders-update` | Partially update an order |
| `DELETE /orders/{id}` | `orders-delete` | Delete an order |
| `GET /orders/{id}/payments` | `orders-payments-list` | Retrieve payment transactions for an order |

The identifier is not part of the URL and is not required to follow a rigid framework structure. It is a documentation identifier chosen by the project team. What matters is that names are predictable, stable, and do not collide across snippet sets with different contents.

### 3.1. When the Same Operation Has Multiple Scenarios

An endpoint can have several meaningful scenarios:

- `GET /orders/{id}` returns success;
- the same endpoint returns `404 Not Found` when the order is missing;
- the same endpoint returns `403 Forbidden` when the user lacks permission.

If each scenario generates its own snippet set, you can use distinct identifiers:

| Scenario | Suggested identifier |
| --- | --- |
| Order exists | `orders-get-found` |
| Order not found | `orders-get-not-found` |
| Not authorized to view | `orders-get-forbidden` |

This keeps each HTTP example and its corresponding documentation in its own directory. If multiple tests write to the same identifier with the same snippet filenames, runs can overwrite content or make it hard to trace the source. Share an identifier only when intentionally building one unified documentation set and controlling snippet names across tests.

### 3.2. Do Not Put Long Descriptions in the Identifier

Names like `orders-get-customer-information-and-delivery-details` are long, hard to read, and prone to change when documentation copy is edited. Keep identifiers short like `orders-get`; explanations belong in `description(...)` and Asciidoctor prose.

## 4. Rules for Naming Subsection IDs

A subsection ID should reflect the extracted branch name or concept. Examples:

| JSON path | Suggested subsection ID | Field snippet name |
| --- | --- | --- |
| `customer` | `customer` | `response-fields-customer.adoc` |
| `delivery` | `delivery` | `response-fields-delivery.adoc` |
| `items` | `items` | `response-fields-items.adoc` |
| `payment` | `payment` | `response-fields-payment.adoc` |
| `items[].pricing` | `item-pricing` | `response-fields-item-pricing.adoc` |
| `delivery.address` | `delivery-address` | `response-fields-delivery-address.adoc` |

When choosing an ID:

1. **Stable:** prefer a short name that does not change merely because a descriptive sentence is reworded.
2. **Understandable:** use a name expressing the branch or concept in the payload.
3. **Unique within the operation:** if two extractors generate the same snippet type, assign different IDs so files do not collide.
4. **Consistent:** the field table and body snippet of the same fragment typically share the same subsection ID to produce predictable filename pairs.
5. **Easy to reference:** the ID should read cleanly in `include` directives, while business headings remain the place for full reader explanations.

`withSubsectionId("item-pricing")` affects only the snippet filename. The extractor path remains `items[].pricing`; it does not alter the JSON structure or how descriptors access fields.

## 5. Example: One Operation Generating Multiple Subsection Snippets

Suppose `GET /orders/{id}` returns:

```json
{
  "id": "ord-810",
  "status": "PAID",
  "customer": {
    "id": "cus-25",
    "displayName": "Hoa Le"
  },
  "delivery": {
    "recipient": "Hoa Le",
    "address": {
      "city": "Da Nang",
      "country": "VN"
    }
  },
  "payment": {
    "method": "CARD",
    "status": "CAPTURED",
    "amount": {
      "value": 300000,
      "currency": "VND"
    }
  }
}
```

The test can generate an overview table, three dedicated field tables, and one body fragment for `payment`:

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Order status"),
        subsectionWithPath("customer")
            .description("Customer information"),
        subsectionWithPath("delivery")
            .description("Delivery information"),
        subsectionWithPath("payment")
            .description("Payment processing outcome")
    ),
    responseFields(
        beneathPath("customer").withSubsectionId("customer"),
        fieldWithPath("id").description("Customer ID"),
        fieldWithPath("displayName").description("Display name")
    ),
    responseFields(
        beneathPath("delivery").withSubsectionId("delivery"),
        fieldWithPath("recipient").description("Recipient"),
        fieldWithPath("address.city").description("City"),
        fieldWithPath("address.country").description("Country code")
    ),
    responseFields(
        beneathPath("payment").withSubsectionId("payment"),
        fieldWithPath("method").description("Method"),
        fieldWithPath("status").description("Payment status"),
        fieldWithPath("amount.value").description("Monetary value"),
        fieldWithPath("amount.currency").description("Currency code")
    ),
    responseBody(
        beneathPath("payment").withSubsectionId("payment")
    )
));
```

Related snippets are stored under one operation identifier:

```text
build/generated-snippets/orders-get/
├── http-response.adoc
├── response-body.adoc
├── response-fields.adoc
├── response-fields-customer.adoc
├── response-fields-delivery.adoc
├── response-fields-payment.adoc
└── response-body-payment.adoc
```

Exact filenames depend on the snippet type and declared handlers. The example above shows handlers invoked in the same `document` call; the field tables have different subsection IDs and therefore distinct names, while the overview table uses the default name `response-fields.adoc`.

### 5.1. Same ID for a Fragment's Body and Field Table

You can use `withSubsectionId("payment")` for both `responseFields(...)` and `responseBody(...)`. The two snippet types have different prefixes:

- `response-fields-payment.adoc`
- `response-body-payment.adoc`

Thus they do not conflict. Conversely, if **two different response field tables** share the subsection ID `payment` within the same operation, both target the same filename `response-fields-payment.adoc`. Give each table its own ID or adjust how operation documents are organized.

## 6. Generating Request and Response Snippets Under the Same Convention

Subsection identification rules are not limited to responses. With `POST /orders`, the request contains `delivery` and `items`:

```json
{
  "customerId": "cus-25",
  "delivery": {
    "recipient": "Hoa Le",
    "address": {
      "city": "Da Nang",
      "country": "VN"
    }
  },
  "items": [
    {
      "sku": "BOOK-09",
      "quantity": 1
    }
  ]
}
```

You can use:

```java
.andDo(document("orders-create",
    requestFields(
        fieldWithPath("customerId").description("Customer ID"),
        subsectionWithPath("delivery").description("Delivery information"),
        subsectionWithPath("items").description("List of line items")
    ),
    requestFields(
        beneathPath("delivery").withSubsectionId("delivery"),
        fieldWithPath("recipient").description("Recipient"),
        fieldWithPath("address.city").description("City"),
        fieldWithPath("address.country").description("Country code")
    ),
    requestFields(
        beneathPath("items").withSubsectionId("items"),
        fieldWithPath("[].sku").description("Product SKU"),
        fieldWithPath("[].quantity").description("Quantity")
    ),
    requestBody(
        beneathPath("delivery").withSubsectionId("delivery")
    )
));
```

In the detailed snippet extracted with `beneathPath("delivery")`, paths start from the `delivery` branch: `recipient`, `address.city`, `address.country`. When extracting the `items` array, paths start from the root of the array; this example uses `[].sku` and `[].quantity` to reference array elements. Verify paths against the actual JSON structure and the project's REST Docs version.

Illustrative filenames:

```text
build/generated-snippets/orders-create/
├── request-fields.adoc
├── request-fields-delivery.adoc
├── request-fields-items.adoc
└── request-body-delivery.adoc
```

Thus, `orders-create` identifies the order creation operation, while `delivery` and `items` distinguish the request fragments of that operation.

## 7. Multiple Fragments of the Same Kind in One Operation: Avoiding Name Collisions

An easy mistake is using the same ID for two subsection extractors with different paths:

```java
responseFields(
    beneathPath("billingAddress").withSubsectionId("address"),
    fieldWithPath("city").description("Billing city")
),
responseFields(
    beneathPath("shippingAddress").withSubsectionId("address"),
    fieldWithPath("city").description("Shipping city")
)
```

Both attempt to write `response-fields-address.adoc` within the same operation. Content may be overwritten or conflict depending on configuration and execution. Name them by **business role** instead:

```java
responseFields(
    beneathPath("billingAddress").withSubsectionId("billing-address"),
    fieldWithPath("city").description("Billing city")
),
responseFields(
    beneathPath("shippingAddress").withSubsectionId("shipping-address"),
    fieldWithPath("city").description("Shipping city")
)
```

The outputs are cleanly separated:

- `response-fields-billing-address.adoc`
- `response-fields-shipping-address.adoc`

The subsection ID does not have to equal the raw JSON path. If two different paths represent related concepts, ID names should clarify meaning to readers and avoid collisions. Conversely, if the path is the same yet two tables serve different audiences or scopes, use IDs expressing the documentation purpose.

## 8. Linking Snippet Names in Asciidoctor

The operation identifier and subsection ID combine in the `include` path:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Look up an order by its identifier.

=== Overview Response

include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

=== Customer

Identifier and display name of the customer associated with the order.

include::{snippets}/orders-get/response-fields-customer.adoc[]

=== Delivery

The delivery branch describes the recipient and shipping address of the order.

include::{snippets}/orders-get/response-fields-delivery.adoc[]

=== Payment

The payment branch describes the processing outcome of the order's payment.

include::{snippets}/orders-get/response-body-payment.adoc[]
include::{snippets}/orders-get/response-fields-payment.adoc[]
```

The path structure is:

```text
{snippets}/{operation-identifier}/{snippet-name}
```

For example, `orders-get` is the directory; `response-fields-payment.adoc` is the snippet name inside that directory. Do not swap the two values or make the subsection ID part of the endpoint URL.

### 8.1. When Documentation Is Split Across Multiple Files

You can place details in separate Asciidoctor fragments and include them in the operation page:

```asciidoc
// orders.adoc
== GET /orders/{id}

include::{snippets}/orders-get/response-fields.adoc[]

include::fragments/order-customer.adoc[]
include::fragments/order-payment.adoc[]
```

```asciidoc
// fragments/order-payment.adoc
=== Payment

Payment represents the method, status, amount, and transaction reference
information of the payment associated with the order.

include::{snippets}/orders-get/response-body-payment.adoc[]
include::{snippets}/orders-get/response-fields-payment.adoc[]
```

In multi-page documentation, use the `xref`/anchor linking mechanism supported by your publishing system. A snippet ID does not automatically create a page anchor, and an operation identifier does not replace the endpoint heading.

## 9. Common Naming Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Include cannot find directory | Confused operation identifier with subsection ID | Check the first argument of `document(...)` |
| Include cannot find subsection file | Subsection ID in `include` differs from `withSubsectionId` | Align the snippet filename suffix |
| Two field tables write to the same file | Two extractors of the same kind share a subsection ID in one operation | Assign distinct IDs, e.g., `billing-address` and `shipping-address` |
| Body and field table assumed to conflict | Thought the same subsection ID causes all snippets to collide | Body and field have different prefixes; sharing an ID for a snippet pair of the same fragment is valid |
| Each operation unexpectedly outputs snippets to the same directory | Reused an operation identifier across independent documentation sets | Pick a distinct identifier for each operation/scenario |
| Filenames are long and hard to predict | Used full descriptive sentences as the subsection ID | Keep IDs short; move descriptions into `description(...)` and headings |
| Readers cannot tell what a fragment means | Only looked at snippet name and path | Write business descriptions in the parent table and prose in the detail section |
| Changed ID yet documentation page still uses old name | Forgot to update `include` directives | Search and update all references to the old snippet |

## 10. Organizing Tests and Builds with Gradle/CI

Example Gradle Groovy DSL configuration, assuming the project already applies the Asciidoctor plugin and has Spring REST Docs dependencies:

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

To keep snippet names maintainable in CI:

1. Organize operation identifiers by resource and action, e.g., `orders-get` and `orders-create`.
2. Name subsection IDs by fragment meaning, avoiding duplicates between two tables of the same kind in one operation.
3. Keep IDs stable; when changing an ID, update the corresponding `include` directives.
4. Do not let two independent scenarios write to the same operation identifier if they generate colliding snippet names.
5. Verify the build after changing an ID to catch non-existent `include` files.
6. Use dummy fixtures and avoid sensitive data in response or request snippets.

With Maven, snippet output typically goes to `target/generated-snippets`. The operation/subsection naming principles remain unchanged; only the root path of the `snippets` attribute changes with the build tool.

## 11. Practice Exercise

Apply the conventions above to the Orders API:

1. **Assign operation IDs:** create identifiers for `GET /orders/{id}`, `GET /orders`, and `POST /orders`. Explain why each snippet set belongs in its own directory.
2. **Assign subsection IDs:** in `orders-get`, extract `customer`, `delivery`, and `payment`. Use the same ID for both the body and field table of the same fragment.
3. **Avoid name collisions:** add two objects `billingAddress` and `shippingAddress`. Use distinct IDs `billing-address` and `shipping-address` and verify the output filenames.
4. **Distinguish operation and scenario:** write two `GET /orders/{id}` tests—one succeeding and one not found. Assign distinct identifiers if the two tests generate different response snippets.
5. **Update documentation:** add the corresponding `include` directives to Asciidoctor. Rename a subsection ID once, then find and fix the stale references.
6. **Verify build:** run `./gradlew clean test asciidoctor` in a configured project; confirm every referenced snippet exists.

**Completion criteria:** you can distinguish an operation identifier from a subsection ID, accurately predict snippet paths, choose non-colliding IDs for fragments of the same kind, and organize snippet sets by operation without making documentation pages hard to maintain.

## 12. Self-Check Questions

**1. What does `document("orders-get", ...)` determine?**

It determines the operation identifier—that is, the group/directory name holding the snippets generated by that documentation call.

**2. What does `withSubsectionId("payment")` determine?**

It identifies the subsection extractor and sets the suffix for the corresponding snippets, such as `response-fields-payment.adoc`.

**3. Can the same subsection ID be used for both a body snippet and a field table?**

Yes. `response-body-payment.adoc` and `response-fields-payment.adoc` have different prefixes, forming a matching snippet pair for the same fragment.

**4. When are different subsection IDs required?**

When multiple snippets of the same kind within the same operation need to be kept separate—for example, a billing address table and a shipping address table, which are both response field snippets.

**5. Does changing the subsection ID change the JSON path?**

No. The path is determined by `beneathPath(...)`; the subsection ID affects only the snippet identifier/filename and references to that file.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): using subsection extractors, field documentation, and assigning subsection IDs.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): configuring documentation operations, snippet output, and Asciidoctor/build integration.
