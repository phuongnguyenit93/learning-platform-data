# @Operation: summary, description, tags, and deprecated

In OpenAPI, each endpoint is represented by an **Operation Object** attached to an HTTP method under a path. For example, GET /api/orders/{id} is an operation. With springdoc-openapi, the **@Operation** annotation allows adding metadata so the documentation explains what the endpoint does, which group it belongs to, and whether it is still recommended for use.

The four most commonly used attributes are:

- **summary**: a short title that helps readers identify the operation.
- **description**: a detailed explanation of behavior, preconditions, and notes when calling the API.
- **tags**: groups operations by topic or business domain.
- **deprecated**: marks an operation as outdated or no longer recommended for new integrations.

These attributes enrich the API contract and the Swagger UI interface. They do not change the HTTP method, URL, access permissions, or controller business logic.

## 1. @Operation Associates Metadata with an Endpoint

**@Operation** belongs to the swagger-annotations library and is read by springdoc when generating the OpenAPI specification. Place the annotation on the controller method corresponding to the endpoint you want to describe:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    @Operation(
        summary = "List orders",
        description = "Returns the list of orders the current user is permitted to view."
    )
    public List<OrderResponse> listOrders() {
        // Call service to retrieve data.
        return List.of();
    }
}
~~~

In this example, **@GetMapping** determines Spring's HTTP mapping; **@Operation** adds descriptive content to the OpenAPI contract. If @Operation is removed, the endpoint still functions according to Spring's mapping, though its description may only be inferred from default information.

An Operation Object can contain many other attributes besides these four, such as **operationId**, **parameters**, **requestBody**, **responses**, **security**, and **externalDocs**. Each attribute serves a specific purpose. This lesson focuses on metadata that helps users understand and navigate the documentation.

## 2. Writing a Short and Recognizable summary

**summary** is the short title of the operation. It usually appears right next to the method and path in Swagger UI, allowing readers to scan the endpoint list without opening the long description.

Example:

~~~java
@Operation(summary = "Find order by ID")
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

A good summary should clearly state the action and target object:

| Summary | Assessment |
|---|---|
| **Get order by ID** | States the specific action and target object |
| **Create refund request** | Indicates creating a request |
| **Update shipping address** | Clearly specifies the data being modified |
| **Order API** | Too generic, does not say what the operation does |
| **Process data** | Does not specify which data or result |

Use a single short sentence and avoid putting full business rules, JSON examples, or error code lists into summary. Those details belong in description, requestBody, and responses.

There is no need to repeat the HTTP method or path in summary if they are already displayed right beside it. For example, the summary "GET /orders: get orders" repeats already available information; "Get order by ID" is more useful.

## 3. Using description to Explain Behavior

**description** is the detailed explanation of the operation. OpenAPI allows description content to use CommonMark, so you can format paragraphs, lists, links, or emphasis.

Example:

~~~java
@Operation(
    summary = "Find order by ID",
    description = """
        Look up an order by identifier.

        - Users can only view orders within their authorized scope.
        - If the order is not found, the API returns HTTP 404.
        - The items field is only returned when the caller has permission to view details.
        """
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

This is a Java text block, which requires Java 15 or higher. If the project uses an older Java version, you can concatenate strings or use a simple string.

Description should answer questions that the endpoint name cannot convey:

- What purpose does the operation serve?
- According to what rules is data read or modified?
- Are there special business conditions, limits, or access permissions?
- Under what circumstances does it return an empty result, an error, or another status?
- Are there side effects such as creating a transaction, sending notifications, or publishing events?
- What should integrators note regarding idempotency, pagination, or processing order?

Only describe the actual behavior of the endpoint. Annotations do not automatically guarantee that the controller implements what is written. If description says the API returns 404 while the implementation returns 200 with an empty body, documentation and behavior have diverged.

## 4. Distinguishing summary and description

Both attributes describe an operation, yet serve two different reading levels.

| Criterion | summary | description |
|---|---|---|
| Goal | Quickly identify the operation | Understand how the operation works |
| Length | Short, usually one sentence | Can span multiple paragraphs |
| Content | Action and target object | Rules, conditions, notes, examples |
| Display | Title of the operation | Detailed section when expanding the operation |
| Formatting | Should be short, direct text | Can use CommonMark |

Complete example:

~~~java
@Operation(
    summary = "Create order",
    description = """
        Create a new order from the current shopping cart.

        The API checks inventory and pricing at creation time.
        If a product no longer has sufficient quantity, the request is rejected
        and the response contains business validation error details.
        """
)
@PostMapping
public ResponseEntity<OrderResponse> createOrder(
    @RequestBody CreateOrderRequest request
) {
    // Handle order creation.
    return ResponseEntity.accepted().build();
}
~~~

Summary tells users they are creating an order. Description explains the data source, checks performed, and cases where it may be rejected. Response codes and error schemas should still be described with **@ApiResponse** or corresponding metadata; do not use description to replace the entire response contract.

## 5. Using tags to Group Operations

**tags** is a list of group names attached to an operation. Swagger UI typically groups operations sharing the same tag into one section so readers can easily browse by functional domain.

You can attach a tag directly on an operation:

~~~java
@Operation(
    summary = "Find order by ID",
    tags = {"Orders"}
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

Multiple operations can share the **Orders** tag. When a document covers multiple business domains, use consistent tag names such as **Orders**, **Customers**, **Payments**, and **Inventory**.

An operation can have multiple tags:

~~~java
@Operation(
    summary = "Create order from shopping cart",
    tags = {"Orders", "Checkout"}
)
@PostMapping
public OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

When it has multiple tags, the operation may appear in multiple UI groups. Only use multiple tags when the operation genuinely relates to those groups; if too many tags are attached, users have trouble telling which group is primary.

Tag names must be consistent in casing, singular/plural form, and naming style. For example, **Orders**, **Order**, and **orders** may be treated as distinct names by OpenAPI readers. Choose one spelling and use it throughout the document.

## 6. Declaring Tag Descriptions with @Tag

**@Tag** defines the name and description of an operation group. It can be placed on a controller to describe the API group belonging to that controller:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Operations for looking up and managing orders"
)
class OrderController {
    // Order endpoints.
}
~~~

Operations inside the controller can use the **Orders** tag. If a method needs to be placed into another group or multiple groups, declare **tags** on @Operation and inspect the generated JSON to confirm the result for the springdoc version in use.

You can declare tag metadata at the document level using **@OpenAPIDefinition**:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "v1",
        description = "Sales system API"
    ),
    tags = {
        @Tag(
            name = "Orders",
            description = "Look up, create, and manage orders"
        ),
        @Tag(
            name = "Customers",
            description = "Customer information and profiles"
        ),
        @Tag(
            name = "Payments",
            description = "Payments and refunds"
        )
    }
)
class OpenApiDocumentationConfiguration {
}
~~~

Here, **@OpenAPIDefinition.tags** defines tag metadata at the document level. **@Operation.tags** attaches tag names to each operation. Both sides must match so the documentation has clear group descriptions.

If an operation uses a tag that has not been declared in global metadata, the tag name can still appear from the operation; however, the group will lack a shared description. Declaring tags at the document level helps keep names and descriptions consistent.

## 7. Marking an Operation as deprecated

The **deprecated** attribute in @Operation indicates that the operation is outdated or no longer recommended for new integrations. In OpenAPI, this is a boolean flag on the Operation Object.

Example:

~~~java
@Operation(
    summary = "Find order using legacy ID",
    description = """
        This endpoint is retained for compatibility with legacy clients.

        Please migrate to GET /api/v2/orders/{orderId}.
        The legacy endpoint is scheduled to be sunset in the next API version.
        """,
    tags = {"Orders"},
    deprecated = true
)
@Deprecated(since = "2.0", forRemoval = false)
@GetMapping("/legacy/orders/{id}")
public OrderResponse getLegacyOrder(@PathVariable String id) {
    return orderService.getByLegacyId(id);
}
~~~

The two annotations serve different purposes:

- **@Operation(deprecated = true)** records the deprecated status in OpenAPI metadata.
- Java's **@Deprecated** helps source code readers and IDEs recognize that the Java method is no longer recommended. The **since** and **forRemoval** attributes provide information in the Java source code.

Placing both annotations keeps source code information and API documentation consistent. Check for **deprecated: true** in the generated JSON to confirm the metadata has been published.

Marking deprecated does not automatically:

- Remove the endpoint from the application.
- Return HTTP 410 or redirect to the new endpoint.
- Prevent clients from continuing to call the API.
- Change the response or access permissions.
- Schedule the removal of the endpoint.

Those are decisions in the implementation and API lifecycle management process. If you want to discontinue service, the team must implement the corresponding changes and notify clients of the timeline.

## 8. Describing the Replacement Path for Legacy Endpoints

A deprecated operation should explain what users should do next. Description should state the replacement endpoint, request/response differences, and the expected sunset time if a decision has been made.

Example controller with new and legacy endpoints:

~~~java
@RestController
@RequestMapping("/api")
@Tag(name = "Orders", description = "Look up and manage orders")
class OrderController {

    @Operation(
        summary = "Find order by ID",
        description = "Current API for looking up an order.",
        tags = {"Orders"}
    )
    @GetMapping("/v2/orders/{orderId}")
    public OrderResponse getOrder(
        @PathVariable String orderId
    ) {
        return orderService.getById(orderId);
    }

    @Operation(
        summary = "Find order using legacy ID",
        description = """
            Deprecated. Clients should migrate to
            GET /api/v2/orders/{orderId}.

            This endpoint continues to serve legacy integrations during the transition period.
            """,
        tags = {"Orders"},
        deprecated = true
    )
    @Deprecated(since = "2.0")
    @GetMapping("/legacy/orders/{id}")
    public OrderResponse getLegacyOrder(@PathVariable String id) {
        return orderService.getByLegacyId(id);
    }
}
~~~

In a deprecation plan, the API team should specify:

1. The new endpoint replacing the legacy endpoint.
2. How to migrate path, query, header, and request body fields.
3. Differences in response schema or HTTP status codes.
4. The version in which deprecation begins.
5. The parallel support window and expected removal date.
6. Notification channels for integrating client teams.

Do not publish a sunset date if no agreed decision exists. An inaccurate timeline can cause client teams to plan their migration incorrectly.

## 9. Inspecting summary, description, tags, and deprecated in JSON

After the application is running, call the documentation endpoint:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

An operation described in JSON might look like:

~~~json
{
  "paths": {
    "/api/orders/{orderId}": {
      "get": {
        "summary": "Find order by ID",
        "description": "Look up an order by identifier.",
        "tags": [
          "Orders"
        ],
        "deprecated": false,
        "responses": {
          "200": {
            "description": "Order found"
          }
        }
      }
    },
    "/api/legacy/orders/{id}": {
      "get": {
        "summary": "Find order using legacy ID",
        "description": "Deprecated. Please migrate to API v2.",
        "tags": [
          "Orders"
        ],
        "deprecated": true,
        "responses": {
          "200": {
            "description": "Order found"
          }
        }
      }
    }
  },
  "tags": [
    {
      "name": "Orders",
      "description": "Look up and manage orders"
    }
  ]
}
~~~

You can use jq to inspect individual attributes:

~~~bash
# View the full operation of a path
jq '.paths["/api/orders/{orderId}"].get' openapi.json

# List summary and tags of operations
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | "\(.key | ascii_upcase) \($path) | \(.value.summary // "(no summary)") | \((.value.tags // []) | join(", "))"
' openapi.json

# Find deprecated operations
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | select(.value.deprecated == true)
  | "\(.key | ascii_upcase) \($path) | \(.value.summary // "")"
' openapi.json
~~~

If **deprecated** does not appear in JSON, according to OpenAPI that operation defaults to not deprecated. To verify a legacy endpoint, check the exact path and method rather than only searching for the string deprecated elsewhere in the document.

## 10. Display in Swagger UI

Swagger UI reads the Operation Object and presents the metadata to users:

- **summary** serves as the short title of the operation.
- **description** displays the explanatory section when expanding operation details.
- **tags** groups operations into navigation sections.
- **deprecated** is typically shown with a visual style or warning indicator so users recognize legacy operations.

The exact visual appearance depends on the Swagger UI version and UI configuration. Therefore, when verifying results, compare both the JSON at **/v3/api-docs** and how it renders in Swagger UI.

A document with a good summary but messy tags is still hard to use. Conversely, clear tag groups with a description missing business conditions are not enough for clients to integrate safely. Review all four attributes in the context of the complete operation.

## 11. Common Documentation Mistakes

| Symptom | Causes to Check |
|---|---|
| Summary does not appear as expected | @Operation is not placed on the right method, another annotation overrides it, or the app is serving documentation from a different configuration. |
| Description appears but line breaks are wrong | Check the Java string, text block, and Markdown/CommonMark being used. |
| One operation appears in multiple groups | The operation has multiple tags assigned; inspect the tags list and keep only genuinely needed groups. |
| Multiple near-identical groups exist | Tag names differ in casing or inconsistent naming style. |
| Tag has no description | Metadata was not declared via @Tag or @OpenAPIDefinition.tags. |
| Legacy endpoint is not marked deprecated | Check @Operation(deprecated = true) and the operation's deprecated field in JSON. |
| Swagger UI still calls the deprecated endpoint | The deprecated flag only describes status; it does not block requests. |
| Description says endpoint is replaced but gives no new path | Add the specific method, path, and migration instructions. |

When multiple annotations describe the same operation, verify the final output in OpenAPI JSON. Do not just read the source code and assume the library generated the right metadata.

## 12. Metadata Writing Conventions for an API Team

A team with multiple developers should agree on conventions before adding annotations:

| Attribute | Recommended Convention |
|---|---|
| **summary** | Use an action verb and a specific target object; keep it short and consistent in style |
| **description** | Describe purpose, preconditions, access permissions, side effects, and notable edge cases |
| **tags** | Use an agreed list of business domains; avoid near-identical names |
| **deprecated** | Enable when an endpoint is no longer recommended; state the replacement endpoint and migration path in description |

Example tag catalog for an e-commerce system:

- **Catalog**: categories and products.
- **Customers**: customer profiles and information.
- **Orders**: creating and managing orders.
- **Payments**: payments, refunds, and transactions.
- **Inventory**: stock levels and product reservations.

Tag names should reflect business domains rather than just Java class names or developer team names. If you rename a tag already used by clients or internal docs, treat it as a structural documentation change that requires communication.

## 13. Checklist for Checking @Operation

- [ ] Each important operation has a short summary that accurately describes the action.
- [ ] Description explains necessary preconditions, business rules, and notes.
- [ ] Description content does not contradict controller behavior.
- [ ] Tag names are consistent across controllers and operations.
- [ ] Tag metadata is declared when a shared group description is needed.
- [ ] Operations only carry tags that are genuinely relevant.
- [ ] Outdated endpoints have deprecated: true in JSON.
- [ ] Description of a deprecated endpoint clearly points to the replacement endpoint and how to migrate.
- [ ] The deprecated flag is not confused with the endpoint being disabled.
- [ ] Swagger UI renders groups and metadata as expected.
- [ ] Final content has been verified at /v3/api-docs.

## 14. References

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – Tag Object](https://spec.openapis.org/oas/latest.html#tag-object)
- [OpenAPI Specification – Root Object](https://spec.openapis.org/oas/latest.html#oas-object)
- [Swagger Annotations – API documentation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/index.html)
- [springdoc-openapi – official documentation](https://springdoc.org/)

OpenAPI defines the meaning of the summary, description, tags, and deprecated fields. springdoc-openapi reads the annotations and produces the corresponding Operation Object. Whenever you change library versions or controller organization, inspect the generated JSON and Swagger UI to ensure the documentation accurately reflects the running API.
