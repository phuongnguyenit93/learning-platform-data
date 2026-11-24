# Avoiding Volatile Data Dependencies When Building Contracts

OpenAPI is a contract describing an API that clients rely on for integration, code generation, and testing. The contract must remain stable across a release: the same application version and deployment configuration should produce identical operations, schemas, parameters, responses, and examples. If document generation depends on current database records, the current clock time, the logged-in user, or responses from an external service, the contract can change unexpectedly.

springdoc-openapi builds documentation from controllers, DTOs, annotations, and customizers. Therefore, keep contract descriptions separated from runtime business data. Describe data types, rules, and representative cases with deliberate metadata; use static, sanitized examples; and let business endpoints return live data when clients call the API.

## 1. API Contracts and Runtime Data Serve Different Purposes

The contract describes the shape and rules of requests and responses. Runtime data consists of the concrete values of a specific API call.

| Element | Belongs to the Contract | Belongs to Runtime |
| --- | --- | --- |
| orderId type | string, pattern, or format if applicable | ORD-10482 of a specific order |
| Order status | Stable set of values if genuinely bounded by business rules | Current status of each individual order |
| createdAt | string with date-time format | Actual creation timestamp of an order |
| Total result count | integer type and meaning description | Number of records matched at query time |
| Current page | page parameter of type integer | Specific request's value page=3 |
| API URL | Server URL per deployment environment | Internal host of a request traversing a specific proxy |
| Response example | Synthetic data representative of the contract | Customer or order rows from the database |

For example, OpenAPI should describe createdAt as an ISO 8601 date-time. It must not call Instant.now() during document generation and turn application startup time into a field's default value.

## 2. Data Sources That Easily Destabilize Contracts

The following sources should normally never be queried while building OpenAPI:

- Databases: current lists of categories, statuses, products, tenants, or latest records.
- External services: live prices, exchange rates, provider statuses, or remote API configurations.
- System clock: current time, deployment date, or startup timestamp.
- Random generators: UUIDs, sequence numbers, transaction IDs, or faker data regenerated on every run.
- Current request: user, tenant, headers, host, locale, or query parameters of whoever is viewing the documentation.
- Feature flags that vary by user or time.
- Environment variables not governed per release or differing across replicas.

If a customizer calls a repository, WebClient, or Instant.now() to populate schemas or examples, the document can differ between restarts, across instances, or across requests. That creates noisy contract diffs and risks leaking real data into public documentation.

## 3. Documenting Stable DTOs Instead of Exposing Persistence Entities as Contracts

Do not tie public schemas directly to database table structures or persistence entities. Entities often contain lazy relationships, internal fields, audit columns, and properties shaped by storage concerns.

Create dedicated DTOs for the API:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

@Schema(name = "OrderResponse", description = "Order information returned to the client.")
public record OrderResponse(
    @Schema(
        description = "System-assigned order identifier.",
        example = "ORD-10482",
        pattern = "^ORD-[0-9]{5}$"
    )
    String orderId,

    @Schema(
        description = "Current status of the order.",
        example = "PROCESSING",
        allowableValues = {"PENDING", "PROCESSING", "SHIPPED", "CANCELLED"}
    )
    String status,

    @Schema(
        description = "Timestamp when the order was created, in ISO 8601 UTC.",
        type = "string",
        format = "date-time",
        example = "2030-04-15T09:30:00Z"
    )
    Instant createdAt
) {
}
~~~

DTOs clarify the external contract. The database can add columns, change relationships, or alter storage layouts without forcing OpenAPI schemas to change when the API contract remains constant.

Include only fields clients need in response DTOs. Never let springdoc accidentally expose password hashes, internal notes, database keys, internal audit fields, or sensitive data merely because the entity contains those fields.

## 4. Using Enums Only When Value Sets Are Genuinely Stable

Enums fit when a value set is part of the contract and governed alongside the API lifecycle, such as fixed order statuses.

Do not query the database to construct allowableValues from existing rows. Catalogs can change, paginate, vary by tenant, or be edited by administrators. A document generated this morning could list a different set of values by this afternoon.

| Data | Appropriate Description |
| --- | --- |
| Order status with a fixed set controlled in code | Enum or allowableValues |
| Country codes from a versioned standard list | Enum if the API strictly bounds values to that list version |
| Product categories added/removed by admins | String or schema referencing a code; document a category lookup endpoint |
| Tenant ID or user ID | String with format/pattern if governed by a stable rule |
| Externally configured provider names | String; do not turn runtime lists into enums |

If clients need to discover dynamic allowed values, provide a discovery endpoint such as /api/categories or /api/configuration/options. The discovery endpoint's contract stays stable while the returned list varies with business data.

## 5. Distinguishing example from default

These two concepts are not interchangeable:

| Attribute | Meaning |
| --- | --- |
| example / examples | Illustrative values helping readers understand usage |
| default | Schema-defined default value used when no value is supplied, if specified by the API |

Do not put current database values or the current timestamp into default merely so Swagger UI displays a nice-looking value. default may be interpreted by client generators or other tools as a semantically binding fallback.

Correct example: parameter page has default 0 when the API genuinely uses page zero whenever clients omit the parameter:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@Parameter(
    name = "page",
    description = "Zero-based page index.",
    schema = @Schema(type = "integer", defaultValue = "0", minimum = "0"),
    example = "2"
)
~~~

Here defaultValue = "0" reflects the API's default behavior; example = "2" merely illustrates a request with a different page index.

If the server always requires clients to pass page, do not declare default just because the backend currently picks a value internally. Describe actual API behavior accurately.

## 6. Using Static, Representative Examples Free of Real Data

Examples in OpenAPI should:

- Hold fixed values so subsequent document builds do not change.
- Represent normal cases and important edge cases.
- Never copy production records or personal data.
- Never contain access tokens, API keys, real emails, real addresses, or secrets.
- Match the schema and validation rules.
- Include a summary/description explaining the scenario illustrated.

Response example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@Operation(
    operationId = "getOrderById",
    summary = "Get order details",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Order was found.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class),
            examples = @ExampleObject(
                name = "processingOrder",
                summary = "Order currently being processed",
                value = """
                    {
                      "orderId": "ORD-10482",
                      "status": "PROCESSING",
                      "createdAt": "2030-04-15T09:30:00Z"
                    }
                    """
            )
        )
    )
)
~~~

This example does not depend on any order existing in the database. It illustrates the response shape and stays identical across builds.

## 7. Never Generate Examples Using Runtime Data

Avoid practices like the following in OpenApiCustomizer, OperationCustomizer, or configuration code:

~~~java
// Avoid: example changes over time and with the database.
openApi.getComponents()
    .getSchemas()
    .get("OrderResponse")
    .setExample(orderRepository.findTopByOrderByCreatedAtDesc());

// Avoid: the same build can generate different documents.
schema.setExample(UUID.randomUUID().toString());
schema.setDefault(Instant.now().toString());
~~~

Instead, put fixed examples in annotations or fixtures versioned alongside source code:

~~~java
schema.setExample("ORD-10482");
~~~

When providing multiple examples, name them by scenario such as processingOrder, shippedOrder, and cancelledOrder. When business rules change and examples need updating, those updates appear clearly in code review and contract diffs.

Do not call repositories or remote services from customizers to fetch sample data. Customizers should transform the OpenAPI model using configuration and stable metadata, not execute business logic.

## 8. Do Not Use Dynamic Data to Determine Schemas

A contract should not change shape based on rows currently present in storage:

- Do not add or remove properties based on which columns happen to hold values in the database.
- Do not change a field's type from string to number based on current records.
- Do not infer enums from statuses currently observed in a table.
- Do not construct response schemas from the first item of a collection.
- Do not omit a field from OpenAPI simply because the current tenant lacks data for that field.
- Do not alter the required list based on null values seen across a few records.

Schemas must reflect the API's capabilities and rules, not a point-in-time data snapshot.

For instance, if discountCode may be absent or null depending on the order, document its optional/nullable nature in the contract. Do not drop the property from the schema just because existing orders in the database have not used a discount code yet.

## 9. Pagination and Volatile Metrics

Pagination is a classic example of runtime data. Total record count, page count, and first items can change on every call.

Response schemas should describe types and semantics:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "PageMetadata")
public record PageMetadata(
    @Schema(description = "Zero-based page index.", example = "0")
    int page,

    @Schema(description = "Page size.", example = "20")
    int size,

    @Schema(description = "Total number of elements matching the query.", example = "135")
    long totalElements,

    @Schema(description = "Total number of pages at query time.", example = "7")
    int totalPages
) {
}
~~~

135 and 7 are static examples explaining the response. Never query actual total row counts from the database at startup to populate OpenAPI.

When a collection is empty, the API still returns the same schema with an empty items array and corresponding counts. Never invent a separate schema simply because the database currently has no rows.

## 10. Timestamps, IDs, and Auto-Generated Values

Fields whose values naturally change on every request:

| Field | How to Describe |
| --- | --- |
| UUID | type string, format uuid; fixed example if needed |
| Timestamp | type string, format date-time; fixed UTC example |
| Date | type string, format date |
| Transaction code | String and pattern if governed by a stable format |
| Random values | Describe type/range and origin; never use a random value as default |
| Current balance or price | Number with appropriate precision/range; example is purely illustrative |

Example:

~~~java
@Schema(
    description = "Unique identifier of the transaction.",
    type = "string",
    format = "uuid",
    example = "8f14e45f-ea2d-4a3f-9b12-1a2b3c4d5e6f"
)
private UUID transactionId;

@Schema(
    description = "Timestamp when the transaction was recorded.",
    type = "string",
    format = "date-time",
    example = "2030-04-15T09:30:00Z"
)
private Instant recordedAt;
~~~

Never use UUID.randomUUID() or Instant.now() when constructing schemas or examples. Live values are generated during business execution; the contract only describes format and meaning.

## 11. Keeping operationId and Schema Names Stable

OpenAPI tooling often uses operationId to generate method names in client SDKs. If operationId changes across builds, generated client code may rename methods even when the endpoint has not changed.

Declare operationId explicitly:

~~~java
@Operation(
    operationId = "getOrderById",
    summary = "Get order by ID"
)
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrderById(@PathVariable String orderId) {
    return orderService.findById(orderId);
}
~~~

Similarly, give schemas stable names when needed via @Schema(name = "OrderResponse") on DTOs. Avoid generating operationIds from timestamps, random values, proxy class names, or runtime data. Do not rename schemas merely because an internal package changed if the external contract should remain unchanged.

OpenAPI requires operationId to be unique across all operations in a document. Verify uniqueness in contract tests.

## 12. Metadata and Server URLs Should Come from Deployment Configuration

Info.version, contact, license, and server URLs must remain stable within a given release/environment. Never use the current time or arbitrary request values as the version.

The `openapi` field at the top of the document specifies the OpenAPI Specification version, whereas `Info.version` specifies the application's API contract version. The two values are independent; never use build time or current timestamps as `Info.version` unless explicitly defined by your release convention.

When environments have different public URLs, use deployment configuration:

~~~yaml
app:
  public-api-url: https://api.example.test
~~~

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class ApiDocumentationConfig {

    @Bean
    OpenAPI apiDocumentation(Environment environment) {
        String publicApiUrl =
            environment.getRequiredProperty("app.public-api-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicApiUrl)
                    .description("Public API")
            ));
    }
}
~~~

URLs can differ between dev and production, yet each deployment has a single explicitly configured value. Do not derive `servers` from arbitrary request Host headers without an appropriate forwarded-header trust boundary.

## 13. Do Not Vary Documentation Unintentionally by User or Tenant

If a customizer filters paths, schemas, or examples based on the logged-in user, the same `/v3/api-docs` URL can return different contracts to different callers. This breaks caching, gateways, contract tests, and client generators; in some configurations it also risks leaking a document generated for one caller to another.

When serving multiple audiences:

- Use GroupedOpenApi with fixed group names and scopes.
- Protect each group's documentation endpoint with appropriate access controls.
- Never alter shared schemas based on current tenant data.
- If per-tenant documentation is genuinely required, explicitly define cache keys, access permissions, isolation, and lifecycle; never use the default OpenAPI cache as a per-tenant cache.

Normally, tenants differ in data and permissions rather than contract structure. Express permission differences through security schemes, scopes, and response codes; tenant-specific data is returned when calling the API.

## 14. Understanding springdoc's OpenAPI Cache Properly

According to the springdoc FAQ, the OpenAPI description is computed once and cached by default. This cache avoids scanning controllers and rebuilding the document on every request.

Property:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

false is the default in documented springdoc releases. When caching must be disabled:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

The FAQ notes one special case: when the same Swagger UI is served through both internal and external proxies and server URLs must be recomputed per HTTP request. In that scenario, disabling caching can be considered after configuring forwarded headers and trust boundaries properly.

Never disable caching simply so examples, enums, or schemas pulled from a database keep updating continuously. That turns the contract into runtime-dependent output, increases document-generation overhead, and makes builds hard to reproduce. If a value represents business data, serve it from a business endpoint response rather than the OpenAPI document.

## 15. Ordering Output Deterministically for Review

You can enable key ordering when serializing the document:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
~~~

This property makes output key ordering predictable, aiding diffs and reviews. It does not stabilize dynamic data: a fresh timestamp, database-backed example, or shifting server URL will still produce diffs.

When comparing OpenAPI in CI, normalize JSON first:

~~~bash
curl -sS http://localhost:8080/v3/api-docs | jq -S . > openapi.json
~~~

Then compare against the previous release artifact. Review diffs semantically:

- Operations or HTTP methods added/removed.
- Required fields or data types changed.
- Enums/formats/ranges changed.
- Response statuses or schemas changed.
- Security requirements or server URLs changed.
- Examples changed unintentionally.

Never blindly approve every snapshot diff. Examples and descriptions are part of the integration experience; changes to them should be reviewed even when they do not break wire compatibility.

## 16. Testing Determinism of the OpenAPI Document

You can write an integration test calling the documentation endpoint twice in the same test context and comparing the outputs:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiStabilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentDoesNotChangeBetweenRequests() throws Exception {
        MvcResult first = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        MvcResult second = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        assertThat(first.getResponse().getContentAsString())
            .isEqualTo(second.getResponse().getContentAsString());
    }
}
~~~

This test catches sources of instability such as timestamps or random values generated inside customizers. If the document derives server URLs from forwarded headers, both test requests must pass identical forwarded headers; otherwise URL differences may reflect intentional configuration.

Beyond comparing full JSON payloads, add targeted assertions for key invariants:

1. operationId values are unique.
2. Schema names and properties do not change unintentionally.
3. Examples conform to schemas.
4. default is declared only when genuinely meaningful.
5. No credentials or personal data appear in examples, descriptions, or extensions.
6. No values fetched from databases/runtime appear in metadata.

## 17. Checking Examples for Sensitive Data

A test suite or CI check can scan fields prone to containing secrets:

- example, examples, and default.
- description, summary, and externalDocs.
- servers.url.
- components.securitySchemes.
- Extensions starting with x-.

Do not search only for Bearer strings; API keys, cookies, client secrets, real emails, and internal URLs can also appear in documentation. Use clearly synthetic data such as user@example.test, api.example.test, and dummy order codes.

If you ever need to share a production-generated document for debugging, inspect and sanitize it before archiving the artifact or sending it externally. Never assume an OpenAPI document is harmless just because it is JSON/YAML.

## 18. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| OpenAPI changes on every call | Customizer generates timestamps/UUIDs or queries runtime data | Use fixed metadata and static examples |
| Enums in documentation miss new values | Enum was built from current DB rows | Use a general type or versioned reference list |
| Swagger UI displays real customer data | Examples copied from production rows | Replace with synthetic fixtures and sanitize artifacts |
| Client generator renames methods | operationId derived from unstable method/class names | Declare explicit operationIds and keep them stable |
| default changes over time | Current time or latest data used as default | Declare default only for actual API behavior |
| Document differs across users/tenants | Customizer depends on security context or tenant | Use fixed groups; separate documentation access permissions |
| Documentation fails to update after config change | Cache holds previously built document | Check caching and restart/config refresh lifecycle |
| Disabling cache slows down the app | Recomputes OpenAPI on every request | Disable cache only for valid reasons like proxy server URLs |
| Snapshots always differ despite unchanged contract | Key ordering or volatile data | Enable order-by-keys, normalize, and eliminate dynamic sources |
| servers contains internal hosts | URL inferred from misconfigured request/proxy | Use configured public URL or trusted forwarded headers |

## 19. Workflow for Building Stable Contracts

1. Define public DTOs and schemas independently of persistence entities.
2. Specify types, formats, required flags, nullability, ranges, and patterns per API rules.
3. Use enums only for stable value sets; look up dynamic catalogs via dedicated endpoints.
4. Use fixed, synthetic examples that match schemas.
5. Declare default only when the API genuinely applies a default value.
6. Never query databases, remote APIs, clocks, or random generators inside customizers to build schemas/examples.
7. Keep operationId, schema names, tags, and Info.version stable.
8. Supply server URLs via deployment configuration; compute per request only for explicit proxy needs with proper caching/trust design.
9. Keep default caching enabled unless there is a clear technical reason to disable it.
10. Export JSON/YAML in CI, normalize output, and review contract diffs.
11. Audit examples, server URLs, descriptions, and extensions to ensure no real data leaks.

A sound contract describes what the API guarantees, not what the database happens to hold at the moment documentation is generated. When schemas, metadata, and examples are managed as stable code, clients can rely on the documentation across deployments without surprises from runtime data.

## References

- [springdoc-openapi – FAQ: OpenAPI cache and server URLs](https://springdoc.org/faq.html)
- [springdoc-openapi – Configuration Properties: cache and writer ordering](https://springdoc.org/properties.html)
- [OpenAPI Specification – Schema Object and examples](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object)
- [OpenAPI Specification – Operation Object and operationId](https://spec.openapis.org/oas/latest.html#operation-object)
- [Swagger Annotations – @Schema](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Swagger Annotations – @ExampleObject](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html)
