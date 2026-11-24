# Kotlin: Nullability, Data Classes, and Default Parameters

When using Springdoc in a Spring Boot application written in Kotlin, Kotlin data types carry important information for the API contract: `String` does not accept `null`, `String?` can accept `null`, and constructor parameters with default values can be omitted when constructing an object. These differences affect how Jackson reads JSON requests and how Springdoc describes schemas in OpenAPI.

Three concepts must be understood separately:

1. **Nullability** indicates whether a property's value can be `null`.
2. **Requiredness** in OpenAPI indicates whether the client is required to send that property.
3. **Default value** indicates which value the server uses when the property is omitted, if the constructor/deserializer supports that default value.

A property can be non-nullable yet still optional because a Kotlin constructor has a default value. Conversely, a property can be required to appear while allowing a `null` value if the API contract calls for it. These three concepts should not be used interchangeably.

## 1. Preparing Dependencies for Kotlin and Springdoc

Spring Boot supports Kotlin through the Kotlin standard library and Kotlin reflection. Jackson needs `jackson-module-kotlin` to read/write Kotlin constructors and data classes according to Kotlin metadata. Springdoc uses model information alongside Jackson/Spring to generate OpenAPI schemas.

Gradle Kotlin DSL example for Spring MVC:

```kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    kotlin("jvm") version "<kotlin-version>"
    kotlin("plugin.spring") version "<kotlin-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:<springdoc-version>")
    implementation(kotlin("reflect"))
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

For WebFlux, use `spring-boot-starter-webflux` and the corresponding Springdoc WebFlux starter, such as `springdoc-openapi-starter-webflux-ui`. If only the OpenAPI endpoint is needed without Swagger UI, choose the `*-api` starter matching the web stack.

Spring Boot typically manages compatible Jackson versions through dependency management. Avoid manually upgrading `jackson-module-kotlin` to a different major/minor version than Jackson Databind managed by Spring Boot. Version placeholders in the example must be replaced with versions compatible with your project.

`kotlin("reflect")` provides reflection metadata that many frameworks need to inspect Kotlin types and constructors. `jackson-module-kotlin` adds serialization/deserialization support for Kotlin classes, including data classes and constructors with default parameters. Springdoc v2 also requires adding the Jackson Kotlin module for full Kotlin type support.

`kotlin("plugin.spring")` opens Spring-annotated classes so they can be proxied. This plugin is helpful for Kotlin components/configurations/services because Kotlin classes are `final` by default; it does not replace the Jackson Kotlin module and does not determine OpenAPI schemas.

## 2. Data Classes as Suitable DTOs for Requests and Responses

Kotlin `data class`es are commonly used as DTOs because the primary constructor declares properties directly while the compiler generates `equals`, `hashCode`, `toString`, `copy`, and component functions.

Example:

```kotlin
data class CreateCustomerRequest(
    val name: String,
    val email: String,
    val nickname: String? = null,
    val marketingOptIn: Boolean = true
)
```

The Jackson Kotlin module can instantiate objects from the primary constructor without requiring a no-argument constructor as in legacy Java bean approaches. Property names are typically inferred from constructor parameters and Kotlin metadata.

For request DTOs, properties in the primary constructor are usually the fields clients send in JSON. For response DTOs, properties are the fields the server returns. Separate request and response DTOs when the two directions have different requirements, for example when requests must not let clients send `id` while responses always return `id`.

```kotlin
data class CustomerResponse(
    val id: Long,
    val name: String,
    val email: String,
    val nickname: String?
)
```

Do not use JPA entities directly as request/response models just because entities are also Kotlin classes. Entities may contain lazy relationships, internal fields, proxies, or attributes that should not be published. DTOs provide clearer control over schemas and the API contract.

## 3. Kotlin Nullability and OpenAPI Nullable

Kotlin expresses nullability directly in the type:

```kotlin
val displayName: String       // Non-nullable
val nickname: String?        // Nullable
val age: Int                  // Non-nullable
val secondaryPhone: String?  // Nullable
```

Springdoc supports Kotlin types. When Kotlin metadata is read properly, nullable properties can be described as nullable in OpenAPI. The exact representation depends on the emitted OpenAPI version:

**OpenAPI 3.0** typically represents it as:

```yaml
type: string
nullable: true
```

**OpenAPI 3.1** uses a JSON Schema type union:

```yaml
type:
  - string
  - 'null'
```

`nullable` or a union containing `null` only states that `null` is an accepted value. It does not specify whether the property can be omitted from JSON. Whether a property must be present is expressed by the object schema's `required` list.

For example, a schema can require `name` while allowing `nickname` to be null:

```yaml
type: object
properties:
  name:
    type: string
  nickname:
    type: string
    nullable: true
required:
  - name
```

In this example, `name` must be present and non-null; `nickname` can be omitted or sent with a `null` value. If `nickname` must be present while still allowing a `null` value, include `nickname` in `required` and keep the schema nullable. These are two independent rules.

## 4. Required Property and Nullable Property Are Not the Same

The table below helps distinguish common cases:

| Kotlin property | Can be null? | Can be omitted from JSON request? | Typical meaning |
|---|---:|---:|---|
| `val name: String` | No | No | Required, value must be non-null |
| `val nickname: String? = null` | Yes | Yes | Optional, defaults to null |
| `val pageSize: Int = 20` | No | Yes | Optional, defaults to 20 |
| `val middleName: String?` | Yes | Must be clarified per deserializer/contract | Nullable without an explicit Kotlin default |

The first two cases are the most common in request DTOs. `String? = null` lets clients omit the field or send null; `Int = 20` lets clients omit the field but forbids sending null under Kotlin's null-safety.

The case of `String?` without a default must be tested with your Jackson module and version. Kotlin requires an argument when calling the constructor directly, whereas the Jackson Kotlin module has specific rules for nullable parameters when a property is absent. Do not infer JSON requiredness solely from a Kotlin constructor lacking `= null`; check runtime requests and the generated OpenAPI.

## 5. Default Parameters in Data Classes

Kotlin allows placing default values directly in the primary constructor:

```kotlin
data class CreateOrderRequest(
    val productId: Long,
    val quantity: Int = 1,
    val note: String? = null
)
```

With the Jackson Kotlin module, when a property is absent from JSON, the constructor can use the Kotlin default value:

| JSON request | Values in object |
|---|---|
| `{"productId": 501}` | `productId = 501`, `quantity = 1`, `note = null` |
| `{"productId": 501, "quantity": 3}` | `quantity = 3`, `note = null` |
| `{"productId": 501, "note": "Morning delivery"}` | `quantity = 1`, `note = "Morning delivery"` |
| `{"productId": 501, "quantity": null}` | Invalid for non-null `Int` under typical default null handling |
| `{"quantity": 2}` | Missing required `productId`; no default to substitute |

A default value handles the case where a property is omitted from JSON. It does not make the property nullable. For example, `quantity: Int = 1` can be omitted, yet `quantity: null` remains invalid for a non-nullable `Int`.

The Jackson Kotlin module has configuration options governing how explicit `null` is handled for parameters with defaults, such as `NullIsSameAsDefault`. Behavior can change if the application enables that option or uses a custom deserializer. Therefore, document the contract based on the actual `ObjectMapper` configuration.

## 6. Distinguishing an Omitted Property from an Explicit Null

For the DTO:

```kotlin
data class UpdateProfileRequest(
    val displayName: String,
    val nickname: String? = null,
    val locale: String = "vi-VN"
)
```

The following two requests can produce the same `nickname = null` value:

```json
{
  "displayName": "Minh"
}
```

```json
{
  "displayName": "Minh",
  "nickname": null
}
```

With the DTO above, code after deserialization cannot tell whether the client omitted `nickname` or sent an explicit null, because both become `null`.

This matters greatly for PATCH. Many APIs need to distinguish:

- Field omitted: keep the current value.
- Field sent as null: clear the current value.
- Field sent with a value: update to the new value.

A nullable property defaulting to null cannot represent all three states. You can use a wrapper representing presence, `JsonNode`, a custom deserializer, or a dedicated patch DTO with states `Absent`, `Null`, and `Value`. Document the semantics clearly in OpenAPI and test all three cases.

Example PATCH contract:

| JSON | Business meaning |
|---|---|
| `{}` | Do not change nickname |
| `{"nickname": null}` | Clear nickname |
| `{"nickname": "Mimi"}` | Set nickname to Mimi |

Do not use `String? = null` if the service must distinguish the first case from the second without an additional presence-tracking mechanism.

## 7. Configuring Kotlin Support in Springdoc

Springdoc v2 supports Kotlin types and includes configuration to enable Kotlin support. In current versions, `springdoc.enable-kotlin` is enabled by default. If the application needs to disable Kotlin-specific handling for a compatibility reason, you can configure this property; normally it should remain enabled.

```yaml
springdoc:
  enable-kotlin: true
  nullable-request-parameter-enabled: true
```

`springdoc.nullable-request-parameter-enabled` controls support for nullable request parameters in Kotlin. Its default value in Springdoc v2 configuration is `true`. This property relates to request parameters, such as query/path/header parameters, and does not replace designing nullability for request body DTOs.

Springdoc v2 has the property `springdoc.model-converters.kotlin-nullable-property-customizer.enabled` to control marking Kotlin nullable model properties as nullable in schemas. It is enabled by default in documented configurations. If you must disable it for legacy schema compatibility, assess the impact across all Kotlin DTOs and inspect the output afterward.

```yaml
springdoc:
  model-converters:
    kotlin-nullable-property-customizer:
      enabled: true
```

Do not copy properties that only exist in newer versions into an older Springdoc application without checking version documentation. If a property is unsupported, Spring Boot may ignore it or fail binding depending on setup.

## 8. Using Annotations with Kotlin Use-Site Targets

A Kotlin property can generate a field, getter, setter, and constructor parameter on the JVM. A Java annotation may be placed on one of those elements. Therefore, when attaching Swagger or Bean Validation annotations to properties, use explicit use-site targets so the annotation reaches the element read by the library.

Example:

```kotlin
import io.swagger.v3.oas.annotations.media.Schema
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

data class CreateCustomerRequest(
    @field:NotBlank
    @field:Size(max = 80)
    @field:Schema(
        description = "Customer name",
        example = "Nguyen An"
    )
    val name: String,

    @field:Schema(
        description = "Optional display name; may be null",
        example = "An"
    )
    val nickname: String? = null,

    @field:Schema(
        description = "Whether to receive promotional communications",
        defaultValue = "true",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    val marketingOptIn: Boolean = true
)
```

`@field:Schema` attaches the annotation to the backing field; `@get:Schema` attaches it to the getter. Choose the target matching the library and how Springdoc/Jackson inspect models. For data class DTOs, using `@field:` explicitly is clear and easy to verify.

Kotlin 2.2 changes default rules for propagating annotations to parameters/properties/fields and provides the compiler flag `-Xannotation-default-target=param-property`. Using explicit use-site targets avoids relying on compiler default rules.

If an annotation does not appear in OpenAPI or validation does not run, check the use-site target before adding a customizer. The compiler may have placed the annotation on the constructor parameter while the library reads the field/getter, or vice versa.

## 9. Controlling Schema Requiredness with `@Schema`

Springdoc can infer schemas from Kotlin metadata, yet sometimes the contract needs to be expressed more explicitly. `@Schema` supports `requiredMode` to specify whether a property is required.

Example of a non-nullable property with a default value:

```kotlin
data class SearchRequest(
    val keyword: String,

    @field:Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED)
    val pageSize: Int = 20
)
```

If your Springdoc version does not infer default parameters as desired, the annotation helps express contract intent. Conversely, if a property must be required, you can use `requiredMode = Schema.RequiredMode.REQUIRED`.

However, Kotlin nullability and annotation requiredness can be processed by different model converters across Springdoc/Swagger Core versions. Some versions or inheritance cases may behave differently when annotations sit on fields, getters, or constructor parameters. Do not rely solely on annotations in source code; verify the generated JSON schema.

`requiredMode` controls whether the property appears in the `required` list; it does not alter the Kotlin type and does not on its own make runtime accept or reject `null`. Bean Validation, Jackson, and application logic still determine which requests are valid.

## 10. Bean Validation on Data Classes

Kotlin null-safety controls `null` values, but does not replace business constraints such as non-blank strings, length limits, minimum numbers, or email format.

```kotlin
import jakarta.validation.constraints.Email
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

data class RegisterAccountRequest(
    @field:NotBlank
    @field:Size(max = 100)
    val fullName: String,

    @field:Email
    val email: String,

    @field:Min(18)
    val age: Int,

    val referralCode: String? = null
)
```

Controller:

```kotlin
import jakarta.validation.Valid
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

@RestController
class AccountController(
    private val accountService: AccountService
) {

    @PostMapping("/api/accounts")
    fun register(
        @Valid @RequestBody request: RegisterAccountRequest
    ): ResponseEntity<AccountResponse> {
        return ResponseEntity.ok(accountService.register(request))
    }
}
```

In Kotlin, validation annotations should usually use `@field:NotBlank`, `@field:Email`, `@field:Min` to attach to the field read by Bean Validation. `@Valid` on the controller parameter instructs Spring to trigger validation on the request body. The `spring-boot-starter-validation` dependency is required.

Springdoc can use certain validation annotations to populate schema constraints such as `minLength`, `maxLength`, `minimum`, or `format`. However, schema validation does not replace runtime validation; keep annotations and test actual requests.

## 11. Jackson Property Naming and Annotations on Kotlin Data Classes

JSON property names can differ from Kotlin property names due to `@JsonProperty`, naming strategies, or `@JsonIgnore`. OpenAPI must describe the actual JSON names read and written by Jackson.

```kotlin
import com.fasterxml.jackson.annotation.JsonProperty
import io.swagger.v3.oas.annotations.media.Schema

data class CustomerProfile(
    @field:JsonProperty("display_name")
    @field:Schema(description = "Customer display name")
    val displayName: String,

    @field:JsonProperty("phone_number")
    val phoneNumber: String?
)
```

JSON requests/responses use `display_name` and `phone_number`. When inspecting `/v3/api-docs`, schema properties must also reflect those configured JSON names. If the documentation still shows `displayName`, check Jackson annotation targets, naming strategies, and the Springdoc version.

Do not include internal fields in schemas if Jackson ignores them:

```kotlin
data class CustomerResponse(
    val id: Long,
    val name: String,
    @field:com.fasterxml.jackson.annotation.JsonIgnore
    val internalNote: String
)
```

When using `@JsonIgnore`, `@JsonProperty(access = READ_ONLY/WRITE_ONLY)`, or `@JsonInclude`, inspect request and response schemas separately. A single model used in both directions can carry different semantics; separate DTOs are usually easier to document accurately.

## 12. Request and Response Data Classes Have Different Defaults

Default values matter most on request bodies: the server uses the default when the client omits the field. On responses, the server normally constructs the object explicitly and serializes all fields per Jackson configuration; a constructor default is not necessarily a default clients can treat as omitted.

Example:

```kotlin
data class CreateProductRequest(
    val name: String,
    val active: Boolean = true
)

data class ProductResponse(
    val id: Long,
    val name: String,
    val active: Boolean
)
```

In the request, `active` may be omitted and the server uses `true`. In the response, the server returns `active` from the created object; clients do not send this field. Using separate DTOs helps OpenAPI document requiredness accurately in each direction.

If a response has a nullable property:

```kotlin
data class ProductResponse(
    val id: Long,
    val description: String?
)
```

`description` can be serialized as JSON `null` or omitted from JSON if Jackson is configured with `NON_NULL`. Those two behaviors differ for clients. Check `ObjectMapper`/`@JsonInclude` settings and ensure the response schema reflects how the server actually emits JSON.

## 13. Nullable and Default Kotlin Request Parameters

Nullability of request parameters such as query parameters is separate from nullability of DTO properties.

Example:

```kotlin
import io.swagger.v3.oas.annotations.Parameter
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
class CustomerSearchController(
    private val customerService: CustomerService
) {

    @GetMapping("/api/customers")
    fun search(
        @Parameter(description = "Search keyword", required = false)
        @RequestParam(required = false)
        keyword: String?
    ): List<CustomerResponse> {
        return customerService.search(keyword)
    }
}
```

`String?` allows the Kotlin variable to receive `null`; `@RequestParam(required = false)` tells Spring MVC the query parameter may be absent. Springdoc has the `springdoc.nullable-request-parameter-enabled` property to support nullable request parameters in Kotlin.

When using a default value on an HTTP parameter, declare it explicitly on the Spring annotation:

```kotlin
@GetMapping("/api/orders")
fun list(
    @RequestParam(defaultValue = "20") size: Int
): List<OrderResponse> = orderService.list(size)
```

`@RequestParam(defaultValue = "20")` is Spring's HTTP parameter binding rule. It differs from a default argument in a Kotlin function signature. Do not assume a Kotlin default argument automatically creates a query parameter default in Spring MVC and OpenAPI.

The Springdoc FAQ notes that a query parameter with `defaultValue` can be marked required under certain inference paths. If the contract needs the query parameter to be optional, inspect the document and add `@Parameter(required = false)` when appropriate. Always verify both runtime binding and the schema.

## 14. Complete Example: Kotlin Data Class and OpenAPI Schema

DTO:

```kotlin
import io.swagger.v3.oas.annotations.media.Schema
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

@Schema(name = "CreateOrderRequest", description = "Order creation details")
data class CreateOrderRequest(
    @field:NotBlank
    @field:Schema(description = "Product code", example = "501")
    val productCode: String,

    @field:Min(1)
    @field:Schema(
        description = "Quantity; defaults to 1 if omitted",
        defaultValue = "1",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    val quantity: Int = 1,

    @field:Size(max = 200)
    @field:Schema(description = "Optional note; may be omitted or null")
    val note: String? = null
)
```

Controller:

```kotlin
import jakarta.validation.Valid
import io.swagger.v3.oas.annotations.Operation
import io.swagger.v3.oas.annotations.media.Content
import io.swagger.v3.oas.annotations.media.Schema
import io.swagger.v3.oas.annotations.responses.ApiResponse
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController

@RestController
class OrderController(
    private val orderService: OrderService
) {

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        summary = "Create order",
        responses = [
            ApiResponse(responseCode = "201", description = "Order created"),
            ApiResponse(
                responseCode = "400",
                description = "Invalid request",
                content = [Content(schema = Schema(implementation = ApiError::class))]
            )
        ]
    )
    fun create(
        @Valid @RequestBody request: CreateOrderRequest
    ): OrderResponse {
        return orderService.create(request)
    }
}
```

Minimal request:

```json
{
  "productCode": "SKU-501"
}
```

After Jackson instantiates the object, `quantity` is `1` and `note` is `null`. The request can also send:

```json
{
  "productCode": "SKU-501",
  "quantity": 3,
  "note": "Deliver during business hours"
}
```

The expected OpenAPI contract should show `productCode` as a required property, `quantity` as optional with default `1`, and `note` as nullable and optional. Nullability serialization may be `nullable: true` in OpenAPI 3.0 or a type union containing `null` in OpenAPI 3.1.

If actual output marks `quantity` required or fails to mark `note` nullable, check the Springdoc version, Kotlin support, Jackson Kotlin module, and annotation use-site targets. Do not change runtime behavior merely to fit an inaccurately inferred schema; first confirm the JSON contract the endpoint actually accepts.

## 15. Inspecting Runtime JSON and OpenAPI Schemas

Once the application is running, open `/v3/api-docs` and inspect the component schema:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest'
```

Inspect the required property list:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest.required'
```

Inspect the schema of `note`:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest.properties.note'
```

In OpenAPI 3.0, look for `nullable: true`. In OpenAPI 3.1, verify `type` includes `null`. Also check `required` separately; do not conclude a property is optional just because it is nullable.

Verify runtime requests with cURL:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"productCode":"SKU-501"}'
```

Then test an explicit null for a non-null property:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"productCode":"SKU-501","quantity":null}'
```

The second request is normally rejected when the Jackson Kotlin module keeps default null-safety. The exact status depends on exception handlers and Spring MVC configuration. Record the actual response so the `400` error documentation matches reality.

## 16. Testing Default Parameters with the Jackson Kotlin Module

You can directly test the `ObjectMapper` configured by Spring Boot:

```kotlin
import com.fasterxml.jackson.module.kotlin.readValue
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import com.fasterxml.jackson.databind.ObjectMapper

@SpringBootTest
class KotlinRequestDeserializationTest {

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @Test
    fun `missing fields use Kotlin constructor defaults`() {
        val request = objectMapper.readValue<CreateOrderRequest>(
            """{"productCode":"SKU-501"}"""
        )

        assertThat(request.quantity).isEqualTo(1)
        assertThat(request.note).isNull()
    }

    @Test
    fun `explicit null is accepted for nullable property`() {
        val request = objectMapper.readValue<CreateOrderRequest>(
            """{"productCode":"SKU-501","note":null}"""
        )

        assertThat(request.note).isNull()
    }
}
```

The test above verifies actual Jackson behavior rather than just calling the Kotlin constructor. You can add tests confirming `quantity: null` is rejected and missing `productCode` fails to construct the request. If the application customizes `ObjectMapper`, tests must use that exact runtime bean.

## 17. Testing the OpenAPI Contract for Kotlin DTOs

Keep contract tests to detect when upgrading Springdoc, Kotlin, or Jackson alters requiredness/nullability. Example with MockMvc:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class KotlinOpenApiSchemaTest {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Test
    fun `openapi describes Kotlin request model`() {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk)
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.required")
                    .value(org.hamcrest.Matchers.hasItem("productCode"))
            )
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.properties.quantity")
                    .exists()
            )
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.properties.note")
                    .exists()
            )
    }
}
```

This test checks that the properties are present and `productCode` is in the `required` list. You can add assertions confirming `quantity` is not required and `note` is nullable; nullability assertions should handle both OpenAPI 3.0 (`nullable`) and 3.1 (`type` containing `null`) if the project may switch document versions.

Beyond schema tests, verify actual request bodies using `MockMvc`/`WebTestClient`. Schemas only describe the contract; Jackson and Bean Validation decide whether requests deserialize and validate successfully.

## 18. Common Pitfalls When Upgrading Kotlin or Springdoc

| Symptom | Possible cause | Fix |
|---|---|---|
| Kotlin data class fails to deserialize | Missing `jackson-module-kotlin` or Jackson/Kotlin incompatibility | Add the module and use versions managed by Spring Boot |
| Nullability missing from schema | Missing Kotlin metadata/reflection, disabled converter, or version difference | Check `kotlin-reflect`, `springdoc.enable-kotlin`, and nullable property customizer |
| Property with default still marked required | Springdoc does not infer default constructor parameter as expected or wrong annotation target | Inspect output; use `@field:Schema(requiredMode = NOT_REQUIRED)` when appropriate |
| Non-null property not marked required | Model converter difference or version regression | Check version, contract tests, and declare `requiredMode = REQUIRED` if needed |
| `@Schema` has no effect on Kotlin property | Annotation attached to constructor parameter instead of field/getter read by library | Use `@field:Schema` or `@get:Schema` appropriately |
| Omitting field with default causes error | Jackson Kotlin module not registered or custom ObjectMapper dropped module | Check the actual ObjectMapper and Jackson module registration |
| Sending null to non-null field is accepted | Jackson configured with non-default null handling/coercion | Review `KotlinModule` options and contract tests |
| PATCH cannot distinguish absent from null | DTO uses a nullable property defaulting to null | Use a presence wrapper or custom deserializer |
| OpenAPI property name differs from runtime JSON | `@JsonProperty`, naming strategy, or annotation target not recognized | Align Jackson metadata and inspect `/v3/api-docs` |
| Null response fields omitted from JSON | `JsonInclude.NON_NULL` or global inclusion policy | Align response schema with actual JSON serialization |
| Nullable query parameter marked required | Different inference between Spring request binding and Springdoc | Declare `required = false` and check `nullable-request-parameter-enabled` |

## 19. Checklist for Designing Kotlin DTOs for OpenAPI

- [ ] `kotlin-reflect` and `jackson-module-kotlin` compatible with Spring Boot/Jackson are present.
- [ ] Use data class DTOs instead of exposing entities directly when contracts need separate control.
- [ ] Use `Type` and `Type?` accurately to match runtime JSON nullability.
- [ ] Distinguish nullable properties from properties that can be omitted.
- [ ] Treat default constructor parameters as optional only after verifying Jackson deserialization and OpenAPI output.
- [ ] Clarify how explicit `null` differs from an omitted property.
- [ ] For PATCH, provide a mechanism to distinguish absent, null, and value if business logic requires it.
- [ ] Use `@field:` or `@get:` on Swagger/Validation annotations when explicit targets are needed.
- [ ] Bean Validation constraints reflect actual business rules.
- [ ] `@JsonProperty`, `@JsonIgnore`, and `@JsonInclude` match the OpenAPI schema.
- [ ] Separate request and response DTOs when semantics differ.
- [ ] Verify OpenAPI 3.0 `nullable` or OpenAPI 3.1 `type` union containing `null`.
- [ ] Inspect the `required` list independently of nullability.
- [ ] Test `ObjectMapper` with omitted properties, explicit null, and concrete values.
- [ ] Add contract tests for `/v3/api-docs` after upgrading Kotlin/Jackson/Springdoc.

Kotlin lets you express nullability and default values directly in data classes, while Springdoc translates model metadata into OpenAPI schemas. `String?` expresses nullability; constructor defaults describe object instantiation when properties are omitted; the `required` list describes properties clients must send. The Jackson Kotlin module and `kotlin-reflect` help runtime understand Kotlin constructors, while Springdoc should be verified via `/v3/api-docs` to ensure schemas match actual JSON. When DTO design, annotation targets, validation, and contract tests are all explicit, API documentation reflects the Kotlin application's behavior far more accurately.

## References

- [Springdoc OpenAPI v2 – Kotlin support](https://springdoc.org/v2/#kotlin-support)
- [Springdoc OpenAPI v2 – Configuration properties](https://springdoc.org/v2/properties.html)
- [Spring Boot – Kotlin support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Jackson Kotlin Module – README](https://github.com/FasterXML/jackson-module-kotlin)
- [Kotlin – Null safety](https://kotlinlang.org/docs/null-safety.html)
- [Kotlin – Classes and constructors](https://kotlinlang.org/docs/classes.html)
- [OpenAPI Specification 3.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
