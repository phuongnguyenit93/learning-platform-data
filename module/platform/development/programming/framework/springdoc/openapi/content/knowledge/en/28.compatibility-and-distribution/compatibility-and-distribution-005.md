# Keeping `operationId` and Schema Names Stable Across Releases

An OpenAPI document describes more than URLs, HTTP methods, and JSON payloads. It also contains identifiers that SDK generators, mock servers, documentation portals, and contract tests may rely on. Two sets of names that must be kept stable are the **`operationId`** of each operation and **schema names** inside `components.schemas`.

In Spring Boot, `springdoc-openapi` typically infers `operationId` from the request-handler method name when no explicit ID is declared. Similarly, component schema names can be inferred from Java types. When refactoring classes or methods, inferred names can change even when the HTTP contract remains intact. Clients regenerated from OpenAPI may then rename methods or models, causing consumer code to fail compilation.

To keep the contract stable, treat `operationId` and schema names as public API identifiers. Declare them explicitly using `swagger-core` annotations, inspect the generated document, and track changes across releases.

## 1. Distinguishing HTTP compatibility and SDK compatibility

A change in OpenAPI might not alter requests on the wire yet still affect applications using auto-generated SDKs.

| Changed Element | Impact on HTTP Contract | Impact on SDK/Code Generation |
| --- | --- | --- |
| URL or HTTP method | May cause old API clients to fail | Generated client method may change |
| JSON property name | Changes wire payload | Model field/property may change |
| Property type or `required` | Changes valid data | Data types or method signatures may change |
| `operationId` | Usually does not change URL or payload | Client method name may change |
| Name in `components.schemas` | Does not necessarily change JSON payload | Generated model/class name may change |
| `summary` or `description` | Does not change HTTP behavior | Mainly affects documentation and generated comments |

For example, changing `operationId` from `getOrderById` to `findOrder` does not necessarily alter the `/api/orders/{orderId}` endpoint. However, an SDK may rename its method from `getOrderById(...)` to `findOrder(...)`. Consumers calling the old method will have to update source code and rebuild.

Similarly, changing a component key from `OrderResponse` to `OrderDto` may not change the JSON response, yet an SDK may generate class `OrderDto` instead of `OrderResponse`. Imports and type declarations in consumer applications will be affected.

Therefore, compatibility assessments must consider both the wire contract and SDK source compatibility.

## 2. `operationId` is the public identifier of an operation

In OpenAPI, each Operation Object can declare an `operationId`. This is a unique string identifying the operation within an API document. Values are case-sensitive; tools and libraries can use it to identify the operation. OpenAPI recommends following common programming naming conventions.

Example:

~~~yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Retrieve order by ID
      responses:
        '200':
          description: Success
~~~

`operationId` is not a URL, a controller name, or a mandatory Java method name. It is a stable identifier for tools to reference the operation.

Important rules:

- If declared, `operationId` must be unique across the entire API document.
- `operationId` comparisons are case-sensitive.
- Use short, meaningful names following a consistent convention.
- Do not reuse an old `operationId` for an operation with a different meaning.
- Do not treat `operationId` as an API version or endpoint URL.

If an application exposes multiple grouped OpenAPI documents, verify uniqueness within each exported document. For easier SDK management, keep the same `operationId` for an operation across all groups where it appears.

## 3. Why Java method names can cause `operationId` to change

When `@Operation(operationId = ...)` is omitted, `springdoc` may use the Spring handler method name as the `operationId`. Consequently, renaming a method during refactoring can alter the documentation.

Initial example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    public OrderResponse findOrder(@PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
~~~

Without an explicit `operationId`, the document may use `findOrder`. Later, the development team renames the method to unify naming:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable UUID orderId) {
    return orderService.getById(orderId);
}
~~~

The inferred `operationId` may change to `getOrder`. The URL and HTTP logic are unchanged, yet method names in the SDK can change accordingly.

To decouple API names from Java method names, declare `operationId` explicitly. You can then refactor internal method names while preserving public identifiers.

## 4. Pinning `operationId` with `@Operation`

The `io.swagger.v3.oas.annotations.Operation` annotation has an `operationId` attribute. Set the ID on the controller method:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    @Operation(
        operationId = "getOrderById",
        summary = "Retrieve order by ID"
    )
    public OrderResponse getOrder(
            @PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
~~~

Even if the method is renamed to `findOne`, `operationId` remains `getOrderById`:

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Retrieve order by ID"
)
public OrderResponse findOne(@PathVariable UUID orderId) {
    return orderService.getById(orderId);
}
~~~

Java method names serve source code organization. `operationId` is the API identifier seen by consumers. Keeping the two independent allows internal refactoring without changing SDKs. Controller examples focus on annotations and assume DTOs, services, and Spring dependencies are already declared in the application.

## 5. Choosing an `operationId` naming convention

A readable convention uses an action verb plus a resource noun. Examples:

| Action | Suggested `operationId` |
| --- | --- |
| List orders | `listOrders` |
| Get a single order | `getOrderById` |
| Create an order | `createOrder` |
| Update an order | `updateOrder` |
| Cancel an order | `cancelOrder` |
| List order items | `listOrderItems` |

Keep consistent rules:

- Use camelCase for `operationId` if your project's SDK convention uses that style.
- Start with a verb describing the action.
- Use business names consumers understand, not internal service or repository names.
- Distinguish operations with different meanings, even when they share the same HTTP method.
- Keep singular/plural forms and abbreviations consistent.

Avoid overly generic names like `get`, `process`, `execute`, `handleRequest`, or names tied to implementation details like `orderControllerGet`. Such names fail to convey intent and easily cause collisions.

Do not append arbitrary suffixes like `V2`, `New`, or `Final` merely because a Java method was refactored. If the API truly has a semantically distinct operation, assign a separate ID reflecting the new action. If only the implementation changed, keep the old ID.

## 6. Avoiding duplicate `operationId` values

Two different operations must not share the same `operationId` within one document. The following example is a design bug:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: getOrders
  /api/orders/{orderId}:
    get:
      operationId: getOrders
~~~

Name them by behavior instead:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
~~~

Do not rely on some generators automatically appending suffixes to resolve duplicate names. Collision handling varies across tools and versions; SDKs may generate awkward names or generation may fail.

When using `GroupedOpenApi`, inspect every operation in each document. If an operation belongs to multiple groups, keep the same `operationId` so consumers recognize it as the same API operation.

## 7. Keeping component schema names stable with `@Schema(name)`

Models referenced in OpenAPI are usually placed in `components.schemas`. Example:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        orderId:
          type: string
          format: uuid
~~~

Operations reference the schema via `$ref`:

~~~yaml
responses:
  '200':
    description: Success
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

The name `OrderResponse` is the schema's component key. Many tools use this key as the model or class name when generating SDKs.

In Java, use `@Schema(name = "...")` at the class/record level to set the public schema name:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(
    name = "OrderResponse",
    description = "Order information returned to client"
)
public record OrderResponse(
    UUID orderId,
    String status,
    BigDecimal totalAmount
) {}
~~~

When the Java class is renamed, the annotation preserves the component key `OrderResponse` as long as `springdoc` continues discovering the model the same way.

For example, suppose the team wants to rename the internal class:

~~~java
@Schema(name = "OrderResponse")
public record OrderView(
    UUID orderId,
    String status,
    BigDecimal totalAmount
) {}
~~~

The Java class name is `OrderView`, while the public schema name remains `OrderResponse`. This lets you refactor class names without forcing consumers to rename generated models.

## 8. Distinguishing schema names from JSON property names

`@Schema(name = "...")` can name either a schema or a property depending on where the annotation is placed. At the class/record level, the target is usually the component schema name. JSON property names are a separate part of the contract and are typically controlled by Jackson, such as `@JsonProperty`.

Example:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

@Schema(name = "OrderResponse")
public record OrderResponse(
    @JsonProperty("order_id")
    UUID orderId,

    String status
) {}
~~~

OpenAPI may produce:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        order_id:
          type: string
          format: uuid
        status:
          type: string
~~~

Here:

- `OrderResponse` is the schema name in `components.schemas`.
- `order_id` is the property name in the JSON payload.
- `orderId` is the Java component name.

Renaming the Java field while keeping `@JsonProperty("order_id")` can preserve the JSON property. Changing `@Schema(name = "OrderResponse")` can change the component key. Changing `@JsonProperty` can change the wire payload. Check the exact naming layer you intend to preserve.

## 9. Naming schemas by API role

A domain often has several models with similar fields but different purposes. Do not force every case to share a single schema just to reduce component count.

Examples:

| Role | Suggested Schema Name |
| --- | --- |
| Order creation payload | `CreateOrderRequest` |
| Order update payload | `UpdateOrderRequest` |
| Returned order details | `OrderResponse` |
| Order summary data | `OrderSummaryResponse` |
| Line item in an order | `OrderItemResponse` |
| API error | `ApiErrorResponse` |

Names should describe the public contract, not persistence or implementation layers. For instance, `OrderEntity`, `OrderJpaModel`, or `OrderRepositoryProjection` are usually poor public schema names because they expose internal structure and change readily during refactoring.

If two DTOs share the same simple Java name yet belong to different domains, component keys can cause confusion or collisions. Use clearly scoped names:

- `CustomerOrderResponse`
- `WarehouseOrderResponse`
- `AdminOrderResponse`

Schema names must be unique inside `components.schemas` of the same document. Do not rely on tooling automatically prepending packages or suffixes to resolve name collisions.

## 10. Keeping schema names stable when changing DTOs or packages

A refactoring may change a package or Java class name without altering the contract:

~~~text
Before:
com.example.shop.order.dto.OrderResponse

After:
com.example.shop.api.orders.model.OrderView
~~~

Without controlling component names, the document may switch from `OrderResponse` to `OrderView`. Consumers may have to update imports and types in their SDKs.

Preserve the public name via annotation:

~~~java
@Schema(name = "OrderResponse")
public record OrderView(
    UUID orderId,
    String status
) {}
~~~

When moving a DTO to another package, keep the annotation and verify the component key in the generated document. Do not let Java package names become part of the public API convention unless the project intentionally designs for it.

## 11. Managing shared schemas vs. distinct schemas

If two operations return the exact same data structure with the same meaning, sharing a single component schema keeps documentation readable and avoids generating two near-identical models.

If two operations have different semantics or lifecycles, use separate schemas even if their current fields look identical. For example:

- `CreateOrderRequest` contains only fields clients may supply on creation.
- `UpdateOrderRequest` may make fields optional for partial updates.
- `OrderResponse` may include `createdAt`, `status`, and `totalAmount`.

Do not merge models solely because they currently share the same three fields. As business logic evolves, requests and responses may diverge independently. Meaningful schema names help consumers understand intent and keep future changes tightly scoped.

Conversely, avoid creating multiple schemas with different names for the exact same concept just because Java classes were named differently across modules. Unify component names for the same public concept.

## 12. Notes on generics, wrappers, and enums

Generic wrappers, page models, and enums can also appear in `components.schemas`. If a generator derives names automatically from type parameters or class names, changing generic type arguments can alter component names.

For instance, `PageResponse<OrderResponse>` and `PageResponse<CustomerResponse>` may need distinct schemas depending on how the resolver creates components. If component names are part of a public SDK, check the actual generated names and consider creating concrete wrappers:

~~~java
@Schema(name = "OrderPageResponse")
public record OrderPageResponse(
    List<OrderResponse> items,
    int page,
    int size,
    long totalElements
) {}
~~~

For enums, keep both the component name and enum values stable. Renaming a component can rename the enum type in SDKs; changing enum values can affect consumer mapping logic.

When using `@Schema(enumAsRef = true)` to extract an enum into its own component schema, verify the key in `components.schemas` after generation. Do not assume the Java enum name is always the desired public name.

## 13. Discriminators and polymorphism also depend on schema names

Schema names can also be referenced from `discriminator.mapping` or other `$ref` pointers. When renaming a component key, update all corresponding references.

Example:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'
      discriminator:
        propertyName: paymentType
        mapping:
          card: '#/components/schemas/CardPayment'
          bank_transfer: '#/components/schemas/BankTransferPayment'
~~~

If `CardPayment` is renamed to `CardPaymentResponse`, every `$ref` and mapping using the old name must be updated. Otherwise, the document may point to a non-existent component or code generators may produce broken models.

Keeping component keys stable reduces the number of places that must change when refactoring classes or reorganizing packages.

## 14. Setting `operationId` and schema names in `RouterFunction`

For Spring WebFlux or MVC functional endpoints, `springdoc` uses `@RouterOperation` to describe routes. `operationId` should be declared inside the nested `@Operation` annotation.

The abbreviated annotation snippet below illustrates the OpenAPI metadata to attach to the `@Bean` method declaring the actual `RouterFunction`:

~~~java
@RouterOperation(
    path = "/api/orders/{orderId}",
    produces = "application/json",
    method = RequestMethod.GET,
    operation = @Operation(
        operationId = "getOrderById",
        summary = "Retrieve order by ID",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Success",
                content = @Content(
                    schema = @Schema(
                        name = "OrderResponse",
                        implementation = OrderResponse.class
                    )
                )
            )
        }
    )
)
~~~

With functional endpoints, there is no controller-style handler method for `springdoc` to reliably infer an operation name from. Declaring `operationId` explicitly keeps route identifiers stable and avoids depending on bean method names.

## 15. Keeping names stable when using `OpenApiCustomizer`

Applications can add to or modify the OpenAPI model using `OpenApiCustomizer` or an `OpenAPI` bean. When constructing operations programmatically, set `operationId` explicitly. This snippet illustrates setting the ID; attaching the `PathItem` to `OpenAPI` is omitted:

~~~java
@Bean
OpenApiCustomizer loginOperationCustomizer() {
    return openApi -> {
        Operation operation = new Operation()
            .operationId("login")
            .summary("Sign in");

        // Attach the operation to the corresponding PathItem.
    };
}
~~~

Do not generate `operationId` using dynamic values such as timestamps, random UUIDs, internal class names, or reflection-derived method names if your goal is a stable contract.

If a customizer renames a component schema, update every `$ref` pointing to that component as well. Avoid writing customizers that rename schemas based on packages or class-iteration order, as results may shift across refactorings or library upgrades.

With `GroupedOpenApi` configurations, you can apply separate customizers per group. Ensure the same public schema does not accidentally receive different names across groups when consumers expect a shared model.

## 16. Testing `operationId` and schema names with `MockMvc`

Do not only verify that the controller returns the right JSON. Test the OpenAPI document generated by `springdoc`, because that is what Swagger UI, SDK generators, and contract tools read.

Integration test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiNamingContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsPublicOperationAndSchemaNames() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{orderId}'].get.operationId"
            ).value("getOrderById"))
            .andExpect(jsonPath(
                "$.components.schemas.OrderResponse"
            ).exists())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{orderId}'].get.responses['200'].content['application/json'].schema['$ref']"
            ).value("#/components/schemas/OrderResponse"));
    }
}
~~~

This test catches cases where:

- A Java method was renamed and `operationId` was inferred as the new name.
- A DTO was renamed, changing the component key.
- The response no longer references the expected component schema.
- A controller or model was not included in the document by `springdoc` as expected.

This test assumes API docs are accessible in the test security context. If Spring Security protects `/v3/api-docs`, configure appropriate test authentication or access permissions.

## 17. Checking for duplicate `operationId` values

Beyond asserting individual IDs, add a uniqueness check across all operations in the document. You can parse OpenAPI JSON with Jackson, traverse path items, and collect the `operationId` of each HTTP operation.

Example check logic:

~~~java
Set<String> operationIds = new HashSet<>();

for (PathItem pathItem : openAPI.getPaths().values()) {
    for (Operation operation : pathItem.readOperations()) {
        String operationId = operation.getOperationId();
        assertNotNull(operationId, "Operation must have an operationId");
        assertTrue(
            operationIds.add(operationId),
            "Duplicate operationId: " + operationId
        );
    }
}
~~~

This snippet assumes the test has loaded and parsed the OpenAPI document into an `io.swagger.v3.oas.models.OpenAPI` model. If your project permits operations without an `operationId`, remove the `assertNotNull` assertion while still verifying uniqueness of declared IDs. For projects generating SDKs, require every public operation to have an explicit ID.

When using multiple groups, run the check on every document. One document may be valid while another group still contains duplicate `operationId` values.

## 18. OpenAPI snapshots and diffs in CI

A reviewed OpenAPI snapshot helps catch unintended changes to public names.

Suggested workflow:

1. Start the application with the export profile.
2. Fetch OpenAPI JSON/YAML from the configured endpoint.
3. Verify the document parses cleanly and `operationId` values have no duplicates.
4. Compare `operationId` values and keys in `components.schemas` against the snapshot or baseline from the previous release.
5. Run breaking-change detection tools for contract modifications.
6. Review every method/model name change prior to release.

You can extract identifier lists from JSON using `jq`:

~~~bash
# List operationIds
jq -r '.. | objects | .operationId? // empty' openapi.json | sort

# Find duplicate operationIds
jq -r '.. | objects | .operationId? // empty' openapi.json \
  | sort | uniq -d

# List component schema names
jq -r '.components.schemas | keys[]' openapi.json | sort
~~~

Snapshots should not be the only way to assess compatibility. A full-document diff can contain ordering, description, or metadata changes that do not affect runtime. Combine:

- Assertions for critical `operationId` and schema keys.
- OpenAPI diff or compatibility checkers to surface contract changes.
- Manual review of intentional changes.
- SDK generator tests if the project publishes client libraries.

## 19. Renaming when genuinely necessary

Sometimes an initial public name is misleading or can no longer be used. In that case, renaming an `operationId` or schema key is a change that can affect source compatibility.

Before renaming:

1. Identify which consumers use SDKs generated from the document.
2. Check method/model names produced by generators across supported languages.
3. Determine whether this is purely a rename or also changes behavior, payloads, and semantics.
4. Announce the change and migration instructions.
5. If old clients must remain supported, consider releasing a new API/document version instead of silently renaming within the same contract.

OpenAPI Generator offers mapping options such as `operationIdNameMappings` and `modelNameMappings` to adjust names on the generator side. These are SDK customization measures, not substitutes for keeping identifiers stable in OpenAPI. Mappings also depend on the specific generator and must be tested.

Never reuse an old `operationId` for a different action after removing the old operation. Doing so misleads consumers or tooling into treating two operations as the same identifier.

## 20. Common mistakes

**Refactoring a controller method name changes the SDK method name.** `springdoc` may use the handler method name as the default `operationId`. Set `@Operation(operationId = "...")` explicitly.

**Two endpoints share the same `operationId`.** Pick distinct IDs by action and test uniqueness across the entire document.

**Renaming a DTO changes the component schema.** Place `@Schema(name = "...")` at the model level to preserve the public component key.

**Changing `@Schema(name)` leaves JSON fields unchanged.** This happens because component keys and JSON properties are two different names. Use `@JsonProperty` to manage JSON field names.

**Renaming a Java property unexpectedly alters the JSON payload.** Check the Jackson naming strategy and `@JsonProperty`; preserve the wire property name when only refactoring Java fields.

**Two packages have classes with the same name, causing component collisions.** Assign distinct, domain-clear schema names unique within the document.

**Schema renamed while `$ref` or `discriminator.mapping` still references the old name.** Inspect all component references and mappings in OpenAPI JSON.

**One group has a different `operationId` than another group.** Use the same ID for the same operation across all documents where it appears, then test each group.

**Checking only that Swagger UI renders.** Swagger UI can render a document even when `operationId` or schema keys changed. Add integration tests and snapshot/diff checks.

**Using generator mappings to mask every change.** Mappings can aid temporary migrations, yet do not stabilize the OpenAPI contract itself. Manage IDs and schema names at the source.

## 21. Checklist for keeping identifiers stable

- [ ] Declare `operationId` explicitly for public operations.
- [ ] Follow a consistent, business-meaningful `operationId` naming convention.
- [ ] Ensure `operationId` values are unique and case-sensitive within each document.
- [ ] Do not rely on Java method names as SDK identifiers.
- [ ] Use `@Schema(name = "...")` on public component schemas whose names must stay stable.
- [ ] Distinguish component schema names from JSON property names.
- [ ] Use unique schema names clear in domain and request/response role.
- [ ] Do not expose internal entity/repository names in the public contract.
- [ ] Check `$ref`, `discriminator.mapping`, and enum components.
- [ ] Keep identical names for equivalent operations/schemas across groups.
- [ ] Inspect OpenAPI JSON/YAML after refactoring.
- [ ] Include uniqueness tests and regression tests for `operationId`/schema keys.
- [ ] Review OpenAPI diffs and generated SDKs before every release.
- [ ] Prepare a migration plan whenever public identifiers must be renamed.

## 22. Conclusion

`operationId` and schema names in `components.schemas` are identifiers that OpenAPI tools and SDK generators use to create methods, models, and references. `springdoc` can infer `operationId` from handler method names if not explicitly declared; model names can also shift when refactoring Java classes. Use `@Operation(operationId = "...")` and `@Schema(name = "...")` to anchor public names while keeping component names distinct from JSON property names. Finally, verify uniqueness, `$ref` targets, snapshots, and generated SDKs in CI to catch unintended changes before release.

## 23. References

- [OpenAPI Specification 3.1.2 — Operation Object](https://spec.openapis.org/oas/v3.1.2.html#operation-object): uniqueness rules, case sensitivity, and identification purpose of `operationId`.
- [springdoc-openapi FAQ v2](https://springdoc.org/v2/faq.html): examples of creating operations with `OpenApiCustomizer` and how `springdoc` builds component schemas.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html): `@RouterOperation` configuration and requirements for declaring `operationId` on functional endpoints.
- [swagger-core — Operation annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html): the `operationId` attribute of `@Operation`.
- [swagger-core — Schema annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): schema/property naming and schema override capabilities of `@Schema`.
- [OpenAPI Generator — Customization](https://openapi-generator.tech/docs/customization/): `operationId` and model name mappings during SDK generation.
- [springdoc-openapi AbstractRequestService](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/service/AbstractRequestService.java): how `springdoc` uses declared `operationId` or falls back to handler method names.
