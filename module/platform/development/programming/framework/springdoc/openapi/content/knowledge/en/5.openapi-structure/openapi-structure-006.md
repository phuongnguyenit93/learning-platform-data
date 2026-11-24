# Tags and Organizing Operations by Topic

Tags are a way to group operations by topic within an OpenAPI document. They help developers find endpoints by resource or business area, understand API boundaries, and navigate Swagger UI more easily. A tag does not create a new route, does not filter access permissions, and does not split the API into separate documents.

In springdoc-openapi, you can declare tags at the controller level with `@Tag`, assign tags to individual operations with `@Operation(tags = ...)`, or describe the global tag list with `@OpenAPIDefinition`. When designing, keep tag names consistent, choose the right level of granularity, and distinguish tags from `GroupedOpenApi`.

This article guides you through designing a tag taxonomy for a Spring Boot API, applying annotations, handling multi-tag operations, sorting in Swagger UI, inspecting OpenAPI JSON, and avoiding common organizational mistakes.

## 1. What Problem Do Tags Solve?

An API can contain dozens or hundreds of operations. If every operation appears in one long flat list, users struggle to find related functionality.

Tags create topical groups for readers to navigate:

~~~text
OpenAPI document
|
+-- Orders
|   +-- GET    /api/orders
|   +-- POST   /api/orders
|   +-- GET    /api/orders/{id}
|   +-- PATCH  /api/orders/{id}
|
+-- Customers
|   +-- GET    /api/customers
|   +-- POST   /api/customers
|
+-- Payments
    +-- POST   /api/payments
    +-- GET    /api/payments/{id}
~~~

In this example, `Orders`, `Customers`, and `Payments` are tags. Each HTTP method/path remains a separate operation under `paths`.

Tags group operations sharing a topic, reduce endpoint lookup time, clarify business scope, keep navigation consistent across controllers, and help API portals present documentation cleanly. A tag is documentation-organization metadata; it does not change how Spring maps URLs or handles requests.

## 2. Tags in an OpenAPI Document Have Two Related Parts

OpenAPI represents tags in two places:

1. The `tags` list at the root document level, used to declare general tag metadata.
2. The `tags` property inside each Operation Object, used to assign the operation to one or more groups.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
tags:
  - name: Orders
    description: Order management
  - name: Customers
    description: Customer management
paths:
  /api/orders:
    get:
      tags:
        - Orders
      summary: List orders
      responses:
        "200":
          description: Success
~~~

`tags[0].name` at the root level is the group name, and `paths./api/orders.get.tags` references that group. The root tag list can supply descriptions, external documentation, and other metadata. Operation tags merely assign an operation to a group.

Declaring only root tags without assigning tags to operations may not produce the desired grouping of operations. Conversely, an operation can declare a tag name while missing a shared description at the root.

## 3. A Tag Is Not a Path, Controller, or API Version

| Component | Role |
|---|---|
| Path | HTTP resource address, e.g., `/api/orders/{id}` |
| HTTP method | Action on the path, e.g., GET, POST, PATCH |
| Controller | Spring component handling a group of requests |
| Tag | Topical grouping of operations inside an OpenAPI document |
| GroupedOpenApi | Creates a separate OpenAPI document based on filtering criteria |
| API version | Contract version published for consumers |

One controller can contribute operations to multiple tags. One tag can also gather operations from multiple controllers. You do not need to create a new controller just to add another tag.

Renaming a tag from `Orders` to `Order Management` does not change URLs, request schemas, or response schemas. It is a documentation organization change, not a routing change.

## 4. Choosing a Taxonomy by Resource and Business Domain

An intuitive taxonomy usually uses nouns representing resources or business capabilities:

- Orders
- Customers
- Payments
- Inventory
- Shipping
- Reports

For resource-oriented REST APIs, using resource names is usually a good starting point.

Avoid creating tags per individual action:

~~~text
CreateOrder
GetOrder
UpdateOrder
DeleteOrder
~~~

These names fragment a single resource into many tiny groups, forcing users to jump back and forth to find operations related to Orders. The action is already conveyed by the HTTP method and operation summary; tags should remain high-level topics.

## 5. Tag Naming Rules

Standardize naming conventions across the entire document:

- Use clear nouns or capability names.
- Keep capitalization consistent, e.g., Pascal Case or Title Case.
- Use one consistent language throughout the API.
- Avoid overly generic names like Common, Other, Misc, or Default.
- Avoid embedding HTTP methods in tag names.
- Avoid adding versions to tag names when versioning is already represented in the document or path.
- Do not create two tags differing only by letter case.
- Do not use internal names that are obscure to consumers.

| Topic | Tag |
|---|---|
| Orders | Orders |
| Customers | Customers |
| Payments | Payments |
| Inventory | Inventory |
| Shipping | Shipping |

Tag names must match exactly between the root declaration and operation references. Treat a tag as an identifier in the document, not free-form text that each controller spells differently.

## 6. Choosing the Right Level of Granularity

Overly broad tags produce groups with too many operations. Overly narrow tags make the group list long and fragmented.

For example, an e-commerce API can start with:

~~~text
Orders
Customers
Payments
Products
Inventory
Shipping
~~~

If `Orders` grows to include many operations belonging to genuinely independent capabilities, consider `Orders`, `Order Fulfillment`, and `Order Returns`. Split only when consumers have distinct search needs or functional groupings. Never split tags merely because a controller has many methods.

A practical test: readers should be able to predict which tag holds the operation they need without knowing the server's Java package layout.

## 7. Avoiding Tags Named After Classes or Teams

Class names like `OrderController`, `OrderAdminController`, or `OrderQueryController` reflect code organization. API consumers do not need to know those class names. Team names like Team A or Backend Squad do not describe API capabilities either.

Instead of splitting by controller names, you can use `Orders`, `Order Administration`, or `Order Search`. However, if all operations fall under the same `Orders` topic, a single `Orders` tag may already suffice.

Controller names should not automatically become the official taxonomy if the team wants a contract that remains stable across code refactorings.

## 8. Using @Tag at the Controller Level

The most common approach in Spring Boot is placing `@Tag` on the controller:

~~~java
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Operations for creating, looking up, and updating orders"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

springdoc uses this metadata to organize the controller's operations under the `Orders` tag. `name` is the group name; `description` explains what capabilities the group holds.

Placing `@Tag` at the controller level works well when most operations in the controller belong to the same topic. If a controller mostly covers one domain yet has a couple of special operations, you can assign separate tags at the operation level.

## 9. Attaching @Operation(tags = ...) at the Method Level

When an operation needs to be grouped under a tag different from the controller or needs multiple tags, declare it on `@Operation`:

~~~java
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Find order by ID",
    tags = {"Orders", "Order Search"}
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

The `tags` attribute accepts a list of tag names. Every name must follow the document's taxonomy.

An operation can carry multiple tags if it genuinely serves multiple topics. Swagger UI and other consumers may show the operation under multiple navigation groups, while OpenAPI still describes a single operation.

Do not attach multiple tags just to make an operation look important. Each added tag should help a group of readers locate the operation for a concrete reason.

## 10. Complete Controller Example

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Order lifecycle management"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(summary = "List orders")
    @GetMapping
    List<OrderResponse> list() {
        // ...
    }

    @Operation(summary = "Create order")
    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }

    @Operation(
        summary = "Look up order",
        description = "Find an order by its identifier"
    )
    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable String id) {
        // ...
    }
}
~~~

Here `@Tag` defines the topic for the controller. Each operation has its own summary describing its action.

There is no need to repeat `tags = {"Orders"}` on every `@Operation` if the controller-level tag already expresses the intent and springdoc's actual output matches.

## 11. Using @OpenAPIDefinition to Declare Shared Tags

When you want to describe the list of tags at the document level, use `@OpenAPIDefinition`:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Commerce API", version = "1.0.0"),
    tags = {
        @Tag(name = "Orders", description = "Order management"),
        @Tag(name = "Customers", description = "Customer management"),
        @Tag(name = "Payments", description = "Payment processing")
    }
)
class OpenApiConfiguration {
}
~~~

The `tags` list here provides document-wide metadata. Controllers or methods still need to assign operations to the corresponding tags.

Place this configuration in a class discovered by Spring, such as `@Configuration`. If the class is not component-scanned or does not participate in the context, the metadata may not be applied.

## 12. Adding External Documentation to a Tag

A Tag Object can contain an external documentation link:

~~~java
@Tag(
    name = "Payments",
    description = "Create and look up payment transactions",
    externalDocs = @ExternalDocumentation(
        description = "Payment integration guide",
        url = "https://docs.example.com/payments"
    )
)
~~~

This link is useful when a group of operations needs deeper business documentation than an OpenAPI description, such as reconciliation rules, transaction states, or refund workflows.

Only include URLs that are published and accessible to the documentation's audience. Do not use `externalDocs` to link to sensitive internal documentation in a public OpenAPI document.

## 13. Organizing Operations from Multiple Controllers into the Same Tag

A tag is not limited to a single controller.

~~~java
@Tag(name = "Orders", description = "Order management")
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // CRUD operations
}
~~~

~~~java
@Tag(name = "Orders", description = "Order management")
@RestController
@RequestMapping("/api/order-items")
class OrderItemController {
    // Operations on order items
}
~~~

Both controllers can contribute operations to the `Orders` group if that organization suits consumers.

If `description` is declared in multiple places, keep the text consistent. Even better, manage shared tag metadata in one place and assign only the tag name on other controllers/methods.

Avoid declaring the same tag name with different descriptions across multiple classes. The merge outcome may be unpredictable or produce duplicate metadata depending on library behavior.

## 14. Operations Belonging to Multiple Tags

An operation may relate to multiple topics:

~~~java
@Operation(
    summary = "Look up payment status of an order",
    tags = {"Orders", "Payments"}
)
@GetMapping("/api/orders/{id}/payment")
PaymentStatusResponse paymentStatus(@PathVariable String id) {
    // ...
}
~~~

This allows readers browsing either `Orders` or `Payments` to find the operation.

Use this selectively. If most operations carry three or four tags, the taxonomy stops providing clear categorization. Assign one primary tag for the topic that owns the operation. Add secondary tags only when there is a real navigation need.

## 15. Tagging an Operation Does Not Create Extra Endpoints

Consider an operation with:

~~~yaml
paths:
  /api/orders/{id}/payment:
    get:
      tags:
        - Orders
        - Payments
      summary: Look up payment status
~~~

This is still a single GET operation at `/api/orders/{id}/payment`. Attaching two tags does not create two routes, duplicate the controller method, or alter request mappings.

Swagger UI may display the operation under two groups. Other tools may choose their own presentation, yet the contract still contains only one path/method.

Do not use multi-tagging as a way to create endpoint aliases. If you need two different URLs, declare two routes or design the API accordingly.

## 16. Declaring Tags in the OpenAPI Model via a Customizer

If the taxonomy is centrally managed or depends on configuration, you can add Tag Objects via `OpenApiCustomizer`:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.models.tags.Tag;

@Configuration
class OpenApiTagConfiguration {

    @Bean
    OpenApiCustomizer tagMetadata() {
        return openApi -> openApi.addTagsItem(
            new Tag()
                .name("Orders")
                .description("Order management")
        );
    }
}
~~~

The customizer modifies the OpenAPI model before the document is serialized. Ensure you do not add duplicate tags with the same name each time the document is generated.

When using multiple `GroupedOpenApi` documents, determine clearly whether the customizer applies to the default document or individual groups. Use a global customizer or a group-attached customizer matching the intended scope, then inspect each document endpoint.

## 17. Maintaining a Consistent Tag List

As a document grows, manage tags as a governed taxonomy:

| Tag | Operation Scope | Excluded Topics |
|---|---|---|
| Orders | Create, read, update, and cancel orders | Standalone payments |
| Customers | Customer profiles and contact details | Authentication |
| Payments | Transactions, refunds, payment status | Shipping |
| Inventory | Stock levels and quantity adjustments | Product catalog |
| Shipping | Delivery addresses, shipments, and tracking | Internal order fulfillment |

When adding controllers or operations, the development team picks from existing tags before introducing a new tag. A new tag should be added only when there is a clear topic with enough operations or navigation value to stand on its own.

## 18. Tags and GroupedOpenApi Are Different

This is an important distinction when organizing large documentation sets:

- Tags group operations inside a single OpenAPI document.
- `GroupedOpenApi` produces separate documents, typically based on path, package, or filter configuration.

A single document can contain the entire API yet divide it into `Orders`, `Customers`, and `Payments`. That is organizing with tags.

`GroupedOpenApi` can generate `/v3/api-docs/public` and `/v3/api-docs/internal`, each having different paths and operations.

| Criterion | Tags | GroupedOpenApi |
|---|---|---|
| Purpose | Group operations by topic | Split documentation into separate document groups |
| Document count | Does not increase document count | Generates a separate document per group |
| Path/package filtering | No | Yes |
| Separate document URL | No | Yes |
| Hide operations from other docs | No | Can filter out of a group |
| Swagger UI navigation | Yes | Allows selecting document/group |

Do not use tags as a substitute for security or filtering. If an internal operation must not be published in the public document, create an appropriate group/filter and enforce access control on the endpoint itself.

## 19. GroupedOpenApi Combined with Tags Example

You can declare a separate public document:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

The two documents expose endpoints:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

Each document can still use tags like `Orders`, `Customers`, or `Administration` to group operations inside it.

A tag can appear in multiple groups. The group decides which operations belong to a document; tags decide how operations are organized within that document.

## 20. Tags Are Not a Security Mechanism

You cannot protect an endpoint by changing its tag or hiding a tag in Swagger UI.

For example, an operation tagged `Internal`:

~~~java
@Operation(tags = {"Internal"})
@GetMapping("/admin/rebuild-index")
void rebuildIndex() {
    // ...
}
~~~

The tag name `Internal` does not make the endpoint private. Any client that knows the URL and has network access can still send requests.

Protect endpoints with Spring Security, authorization rules, network policies, or a gateway. If you do not want an operation published in the public OpenAPI document, use an appropriate filter/group while ensuring the actual endpoint enforces access control.

## 21. Hiding Operations Differs from Assigning Tags

You can hide an operation from documentation using `@Hidden` or `@Operation(hidden = true)`:

~~~java
@Operation(hidden = true)
@PostMapping("/internal/reindex")
void reindex() {
    // ...
}
~~~

Hiding affects only the generated document. It does not disable the route.

If an API has public and internal documentation, consider creating two `GroupedOpenApi` beans with explicit filters instead of relying only on a tag named `Internal`.

Never use tags such as `Hidden`, `Private`, or `Secret` expecting Swagger UI to secure the content automatically.

## 22. Sorting Tags in Swagger UI

Swagger UI can sort tags alphabetically:

~~~yaml
springdoc:
  swagger-ui:
    tags-sorter: alpha
~~~

Or in `application.properties`:

~~~properties
springdoc.swagger-ui.tagsSorter=alpha
~~~

This option affects how groups are displayed in Swagger UI. It does not alter tag names, does not change the OpenAPI contract, and does not sort every tag in the JSON/YAML itself.

If you want to preserve business ordering, declare tags in the desired order in the root document and verify UI behavior when no sorter is configured. If `tags-sorter: alpha` is set, the UI order will be alphabetical even if the root list has a different order.

## 23. Sorting Operations Inside a Tag

Swagger UI provides the `operationsSorter` property:

~~~yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
~~~

Or:

~~~properties
springdoc.swagger-ui.operationsSorter=alpha
~~~

Common options:

- `alpha`: sort operations by path.
- `method`: sort by HTTP method.
- Custom JavaScript function: when the UI is configured to accept a suitable sorter function.

Operation sorting differs from tag sorting. `tags-sorter` controls group order; `operations-sorter` controls operation order inside a group.

This is a UI presentation setting. Do not treat it as proof that the OpenAPI JSON is canonically ordered or that semantic diffs are stabilized.

## 24. Maintaining Intentional Tag Order

If you need a custom tag order, you can declare root tags in the desired order inside `@OpenAPIDefinition`:

~~~java
@OpenAPIDefinition(
    tags = {
        @Tag(name = "Orders", description = "Order management"),
        @Tag(name = "Payments", description = "Payment processing"),
        @Tag(name = "Customers", description = "Customer management")
    }
)
~~~

Or sort the model in a customizer:

~~~java
@Bean
OpenApiCustomizer stableTagOrder() {
    return openApi -> {
        if (openApi.getTags() != null) {
            openApi.getTags().sort(
                Comparator.comparing(
                    Tag::getName,
                    Comparator.nullsLast(String::compareTo)
                )
            );
        }
    };
}
~~~

Sort alphabetically only when that is the team's convention. If you want to prioritize `Orders`, `Payments`, `Customers` along the business journey, use an explicit order rather than alphabetical order.

If Swagger UI has its own sorter, it can override the order provided by the document in the UI. Verify both the JSON file and the UI according to your goal.

## 25. Tags and Controller Inheritance

Some projects use base controllers or interfaces to share endpoint metadata. When annotations exist on interfaces, superclasses, and concrete controllers, verify how Spring and `swagger-core` read annotations in that hierarchy.

Do not assume every annotation on an interface is inherited like a standard Java annotation. The outcome also depends on annotation targets, retention, and how springdoc discovers handler methods.

If a tag is missing or duplicated:

1. Check which class is actually registered as a controller.
2. Check where `@Tag` is placed.
3. Check `@Operation.tags` on the method.
4. Inspect the output OpenAPI JSON.
5. Avoid declaring the same tag metadata on multiple classes unnecessarily.

For critical API contracts, a test verifying each operation's tags helps catch regressions during controller refactoring.

## 26. Organizing Tags for Large APIs

For APIs spanning multiple domains, start from the bounded contexts or capabilities recognized by consumers:

~~~text
Accounts
Customers
Orders
Payments
Inventory
Shipping
Notifications
Reports
~~~

If one group grows too large, analyze operations by usage purpose. You might separate `Order Fulfillment` from `Orders` if it is a distinct capability with different consumers and workflows.

Avoid creating multi-level nested tag trees such as:

~~~text
Commerce
  Orders
    Create
    Update
  Payments
    Refund
    Capture
~~~

The OpenAPI Tag Object defines no standard hierarchical taxonomy. Spaces, slashes, or prefixes merely produce flat tag names, not a tree structure with shared semantics.

If you need hierarchical navigation, use an API portal that supports its own taxonomy or split into multiple OpenAPI groups.

## 27. Tags for Shared Operations

Operations such as health checks, metadata, or authentication may not belong to a primary domain resource. You can choose a group like `System`, `Authentication`, `Metadata`, or `Administration`.

The name must accurately describe the functionality and make sense to consumers. Do not dump every hard-to-categorize operation into `Common`.

If an endpoint only serves health probes and is not meant for API consumers, consider excluding it from the public document or placing it in a separate operations document.

## 28. Tags Across Multiple API Versions

If a document covers multiple API versions, decide whether tag names remain unchanged across versions.

~~~text
v1:
  Orders
  Payments

v2:
  Orders
  Payments
  Fulfillment
~~~

Keeping tag names stable helps readers compare documentation across versions. If a capability's scope changes significantly, a new tag name may be warranted, provided it is documented in migration notes.

Do not embed `v1` or `v2` into every tag if the version is already expressed via paths, servers, or document metadata. Doing so easily creates duplicate taxonomies.

## 29. Tags and Code Generation

Some API portals and client generators use tags to group operations or generate API classes per tag. For example, a generator might produce `OrdersApi` and `PaymentsApi` from the corresponding tags.

Consequently, renaming a tag can affect class names or method groupings in the generated SDK even though HTTP routes remain unchanged.

Before renaming a tag in a published API:

- Check the generator in use.
- Compare the generated SDK output before and after.
- Determine whether source compatibility breaks for consumers.
- Write migration notes if class/API groupings change.
- Keep `operationId` stable whenever possible.

Tags are not just UI decoration; parts of the toolchain treat them as metadata for structuring generated code.

## 30. Inspecting Tags in OpenAPI JSON

After running the application, download the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

View the root tag list:

~~~bash
jq '.tags' target/openapi.json
~~~

View an operation's tags:

~~~bash
jq '.paths["/api/orders"].get.tags' target/openapi.json
~~~

List all tags currently used by operations:

~~~bash
jq -r '.paths[] | to_entries[] | .value.tags[]? ' target/openapi.json |
  sort -u
~~~

The command above helps verify actual tag names in the document. Compare them against the agreed taxonomy to spot inconsistent casing, leftover old names, or unintended groups.

## 31. Checking for Unused Root Tags

You can cross-check the root `tags` list against tags assigned to operations:

~~~bash
jq -r '.tags[]?.name' target/openapi.json | sort -u
~~~

~~~bash
jq -r '.paths[] | to_entries[] | .value.tags[]?' target/openapi.json |
  sort -u
~~~

If a root tag is unused by any operation, consider removing it or confirming it is intentionally kept for documentation.

If an operation uses a tag lacking a root declaration, consider adding a Tag Object to provide consistent `description` and `externalDocs`. Tools may still display tags without root metadata, but the document is clearer when fully declared.

## 32. Testing Tags with WebTestClient

Example testing operation tags:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiTagsTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void assignsOrdersTagToOrderOperations() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/orders'].get.tags[0]")
                .isEqualTo("Orders")
            .jsonPath("$.paths['/api/orders'].post.tags[0]")
                .isEqualTo("Orders");
    }
}
~~~

This test assumes the operation's `tags` array has `Orders` at index 0. If an operation has multiple tags or ordering is not part of the contract, parse the JSON and assert containment rather than relying on index position.

Also test root tag metadata:

~~~java
@Test
void publishesOrdersTagDescription() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.tags[?(@.name == 'Orders')].description")
        .isEqualTo("Order lifecycle management");
}
~~~

JSONPath filter support can vary across test libraries. If an expression behaves unexpectedly, parse the document into a `JsonNode` and look up the element by `name`.

## 33. Testing Multiple Groups

If you use `GroupedOpenApi`, verify tags inside each document:

~~~text
/v3/api-docs/public
/v3/api-docs/internal
~~~

Groups may contain different operation sets while sharing a taxonomy.

Tests should confirm that public operations carry expected tags, internal operations do not leak into the public document, root tag metadata appears in the required groups, customizers apply to the proper scope, and no extra or duplicate tags exist.

Do not test only the default document if production distributes multiple groups.

## 34. Common Mistakes

| Symptom | Cause to Check |
|---|---|
| Swagger UI shows near-duplicate tags | Names differ by casing, spacing, or singular/plural form |
| Operation appears under an unexpected tag | Controller `@Tag` or `@Operation.tags` is inconsistent |
| Root tag has a description but empty group | No operation references that tag |
| Operation has a tag without description | Tag Object is not declared at the root level |
| Operation shows up in multiple groups | Multiple tag names listed in `@Operation.tags` |
| Renaming a tag alters the SDK | Generator uses tags to group classes/APIs |
| Swagger UI sorts differently from JSON | `tags-sorter` or `operations-sorter` alters UI display |
| Tagged `Internal` yet endpoint is callable | Tags are not a security mechanism |
| Used tags to separate public/internal yet both appear | Need `GroupedOpenApi` or filters |
| Duplicate tags after splitting controllers | Multiple classes declare conflicting metadata |
| Tags disappear after refactoring | Annotations on interfaces/base classes were not discovered as expected |
| Too many tags | Taxonomy was split by method or controller names |

## 35. Taxonomy Design and Review Workflow

When designing tags for a new API:

1. List the resources and capabilities recognizable to consumers.
2. Pick short, consistent nouns or business names.
3. Define the operation scope for each tag.
4. Put `@Tag` on controllers when an entire controller shares one topic.
5. Use `@Operation.tags` for special operations or multi-topic operations.
6. Declare shared descriptions in `@OpenAPIDefinition` when needed.
7. Verify root tags and operation tags in the generated JSON.
8. Configure UI sorting intentionally with `tags-sorter`/`operations-sorter`.
9. Test each `GroupedOpenApi` separately if multiple documents exist.
10. Review impacts on the API portal and generated SDKs before renaming a tag.

During pull request reviews, ask the author to explain what search need a new tag serves. Without a clear answer, the new tag may be adding unnecessary complexity to the taxonomy.

## 36. Checklist

- [ ] Tags describe topics or capabilities, not HTTP methods.
- [ ] Tag names are consistent in casing, singular/plural form, and language.
- [ ] Per-operation tags are avoided unless clearly needed.
- [ ] Root Tag Objects have appropriate descriptions.
- [ ] Operation tags reference exact tag names.
- [ ] `@Tag` is placed on controllers sharing a single topic.
- [ ] `@Operation(tags = ...)` is used only when overriding or assigning multiple topics.
- [ ] Tags are not confused with paths, controllers, or API versions.
- [ ] Tags are not used as a security mechanism.
- [ ] `GroupedOpenApi` is used when separate documents or path filtering are needed.
- [ ] Multi-tagging does not dilute the taxonomy.
- [ ] UI ordering is intentionally configured via `tags-sorter`/`operations-sorter`.
- [ ] Generated OpenAPI JSON has been inspected.
- [ ] Root tags and operation tags have been verified.
- [ ] Every `GroupedOpenApi` has been tested if present.
- [ ] Impact of tag renames on API portals and SDK generators has been evaluated.

## 37. References

- [OpenAPI Specification – Tags Object](https://spec.openapis.org/oas/latest.html#tag-object)
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger Core – OpenAPI 3 Annotations](https://github.com/swagger-api/swagger-core/wiki/Annotations)

Tags provide a navigation taxonomy for operations inside an OpenAPI document. Use `@Tag` to describe groups on controllers or at the document level, `@Operation(tags = ...)` to assign operations to one or more groups, and `GroupedOpenApi` when separate documents are required. Keep tag names stable because API portals and SDK generators may use them to organize output; always verify root tags, operation tags, and UI rendering after generating the document.
