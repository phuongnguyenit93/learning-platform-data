# Replacing @ApiModel and @ApiModelProperty with @Schema Descriptions

Springfox Swagger 2 and springdoc-openapi use two different generations of annotations to describe API models. When migrating a project to springdoc-openapi, @ApiModel and @ApiModelProperty in the io.swagger.annotations package must be replaced with @Schema in the io.swagger.v3.oas.annotations.media package.

@ApiModel typically describes a model's name and meaning; @ApiModelProperty describes individual properties such as content, examples, types, allowable values, required status, or read/write capability. In OpenAPI 3, @Schema handles most of these roles and supplies additional metadata aligned with the Schema Object.

Replacing annotations should not be a simple import rename. You need to review each attribute's semantics, distinguish runtime validation from documentation descriptions, inspect request/response DTOs, and verify the OpenAPI document after migration.

## 1. Identify old and new annotations

| Purpose | Springfox / Swagger 2 | Swagger Core / OpenAPI 3 |
|---|---|---|
| Describe model class | @ApiModel | @Schema |
| Describe property/field | @ApiModelProperty | @Schema |
| Model name | @ApiModel(value = ...) | @Schema(name = ...) |
| Model description | @ApiModel(description = ...) | @Schema(description = ...) |
| Property description | @ApiModelProperty(value = ...) | @Schema(description = ...) |
| Example | @ApiModelProperty(example = ...) | @Schema(example = ...) |
| Required field | @ApiModelProperty(required = true) | @Schema(requiredMode = Schema.RequiredMode.REQUIRED) |
| Hide field | @ApiModelProperty(hidden = true) | @Schema(hidden = true) |
| Read-only | @ApiModelProperty(readOnly = true) | @Schema(accessMode = Schema.AccessMode.READ_ONLY) |
| Write-only | Corresponding access config | @Schema(accessMode = Schema.AccessMode.WRITE_ONLY) |

The new annotations belong to Swagger Core v3, commonly used by springdoc-openapi to generate OpenAPI documents. Importing the right package is the first step:

~~~java
// Swagger 2 / Springfox
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;

// OpenAPI 3 / springdoc-openapi
import io.swagger.v3.oas.annotations.media.Schema;
~~~

Do not keep both old and new annotations on the same DTO expecting springdoc to understand both. springdoc focuses on OpenAPI 3 annotations; Springfox annotations may be ignored.

## 2. Replace @ApiModel at the class level

Old model example:

~~~java
import io.swagger.annotations.ApiModel;

@ApiModel(
        value = "Customer",
        description = "Customer information"
)
public class Customer {
    private String code;
    private String name;
}
~~~

After migrating to @Schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "Customer",
        description = "Customer information"
)
public class Customer {
    private String code;
    private String name;
}
~~~

Commonly used attributes:

| @ApiModel | @Schema | Notes |
|---|---|---|
| value | name | Schema name under components.schemas |
| description | description | Model description |
| discriminator | discriminatorProperty | Property name used to distinguish subtypes |
| subTypes | oneOf or subTypes | Choose the appropriate way to describe polymorphism |

Not every attribute of @ApiModel has a direct replacement. For example, if a model uses discriminator and subtypes, redesign the schema for OpenAPI 3 using oneOf/allOf and discriminator mapping rather than merely renaming the annotation.

## 3. Replace standard @ApiModelProperty descriptions

Old model:

~~~java
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;

@ApiModel(value = "CreateCustomerRequest")
public class CreateCustomerRequest {

    @ApiModelProperty(
            value = "Customer code",
            example = "CUS-100",
            required = true
    )
    private String code;

    @ApiModelProperty(
            value = "Customer display name",
            example = "Nguyen Van An"
    )
    private String displayName;
}
~~~

Post-migration model:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "CreateCustomerRequest",
        description = "Data used to create a customer"
)
public class CreateCustomerRequest {

    @Schema(
            description = "Customer code",
            example = "CUS-100",
            requiredMode = Schema.RequiredMode.REQUIRED
    )
    private String code;

    @Schema(
            description = "Customer display name",
            example = "Nguyen Van An"
    )
    private String displayName;
}
~~~

In @ApiModelProperty, value is typically used as the description. With @Schema, use description to explain the property's meaning. Do not confuse name with description: name renames the property in the schema, whereas description only adds explanatory text.

## 4. Distinguish between name and description

name is used when the OpenAPI property name needs to differ from the Java field name or when pinning the schema name. Example:

~~~java
@Schema(
        name = "customerName",
        description = "Customer display name"
)
private String displayName;
~~~

If Jackson already renames the JSON property via @JsonProperty, check the final name generated by springdoc. Do not set @Schema(name = ...) merely to repeat the Java name when Jackson already provides the accurate wire-format name.

Keep property names consistent with the actual JSON request/response. If the documentation describes customerName while the server expects displayName, clients generated from OpenAPI may send invalid payloads.

## 5. Replace required with requiredMode

Springfox often uses:

~~~java
@ApiModelProperty(required = true)
private String email;
~~~

In Swagger Core v3, use:

~~~java
@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
private String email;
~~~

Key values of RequiredMode:

| Value | Meaning |
|---|---|
| REQUIRED | Marks the property as required in the schema |
| NOT_REQUIRED | Marks the property as not required |
| AUTO | Lets the library infer based on metadata and configuration |

Required only states whether a property must be present in the object. It does not specify whether the value may be null. For example, a property can be required to appear while the schema still permits null if described that way.

For runtime validation to take effect, use Bean Validation annotations such as @NotNull, @NotBlank, or @NotEmpty and configure validation for the application. @Schema(requiredMode = REQUIRED) only describes the OpenAPI contract; it does not validate requests at runtime.

## 6. Combine @Schema with Bean Validation

A DTO often needs both OpenAPI metadata and runtime constraints:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(name = "CreateCustomerRequest")
public record CreateCustomerRequest(
        @Schema(
                description = "Customer email address",
                example = "an@example.com",
                requiredMode = Schema.RequiredMode.REQUIRED
        )
        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @Schema(
                description = "Display name",
                example = "Nguyen Van An"
        )
        @Size(max = 120)
        String displayName
) {}
~~~

In the example:

- @Schema adds a description and example for OpenAPI.
- @NotBlank requires a non-null string with at least one non-whitespace character when validation runs.
- @Email validates email format using the configured validator.
- @Size enforces length limits.

springdoc can read Bean Validation constraints to infer required flags or matching bounds in the schema. However, exact inference depends on the version, where annotations are placed, and project settings. Inspect the generated document instead of assuming every constraint is reflected.

## 7. Replace example and allowableValues

Springfox:

~~~java
@ApiModelProperty(
        value = "Account status",
        example = "ACTIVE",
        allowableValues = "ACTIVE,INACTIVE,SUSPENDED"
)
private String status;
~~~

OpenAPI 3:

~~~java
@Schema(
        description = "Account status",
        example = "ACTIVE",
        allowableValues = {
                "ACTIVE",
                "INACTIVE",
                "SUSPENDED"
        }
)
private String status;
~~~

If the value set is a fixed domain in Java, consider using an enum:

~~~java
public enum AccountStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
~~~

Then use AccountStatus as the property type. This keeps the code data type and OpenAPI enum from a single source of truth. If individual enum values need separate descriptions, add schema metadata or describe enum values as supported by your Swagger Core version.

allowableValues in annotations is documentation metadata. It does not automatically reject unlisted values at runtime; use enums, Bean Validation, or business logic to enforce it.

## 8. Replace dataType with the actual Java type

Some legacy models use dataType to force the documented type:

~~~java
@ApiModelProperty(dataType = "java.lang.Long")
private String customerId;
~~~

This is usually a sign that the Java type and documentation are out of sync. Prefer changing the property type to Long if the value is genuinely numeric:

~~~java
@Schema(
        description = "Customer ID",
        format = "int64",
        example = "10001"
)
private Long customerId;
~~~

If you cannot change the Java type due to wire-format contracts or backward compatibility, only override the schema after verifying what type JSON actually serializes to. You can use type, format, or implementation on @Schema when needed, but do not force the schema to integer if Jackson still sends a string.

The rule is that types in OpenAPI must reflect actual data over HTTP, not merely developer intent.

## 9. Replace hidden

Springfox:

~~~java
@ApiModelProperty(hidden = true)
private String internalNote;
~~~

OpenAPI 3:

~~~java
@Schema(hidden = true)
private String internalNote;
~~~

hidden instructs springdoc to omit the property from the generated schema per its configuration. This is a documentation presentation choice, not a data-protection mechanism.

If a field holds confidential information, remove it from the response DTO or configure serialization and authorization properly. Do not rely on hidden to prevent the server from returning sensitive data.

## 10. Replace readOnly and writeOnly

Springfox may use the readOnly attribute to mark a read-only field. OpenAPI 3 uses accessMode:

~~~java
@Schema(
        description = "System-assigned customer ID",
        accessMode = Schema.AccessMode.READ_ONLY
)
private UUID id;
~~~

Write-only field:

~~~java
@Schema(
        description = "Password used during account creation",
        accessMode = Schema.AccessMode.WRITE_ONLY
)
private String password;
~~~

Modes:

| AccessMode | Meaning |
|---|---|
| READ_ONLY | Read-only, typically sent in responses |
| WRITE_ONLY | Write-only, typically accepted in requests |
| READ_WRITE | Readable and writable |
| AUTO | Let the library infer |

readOnly/writeOnly are schema metadata. They do not alter Jackson serialization, strip fields from objects, or replace access control checks. For APIs with differing request/response payloads, splitting CreateRequest and Response DTOs is usually clearer and safer than sharing one class.

## 11. Replace notes and long descriptions

Springfox:

~~~java
@ApiModelProperty(
        value = "Phone number",
        notes = "Use country code, e.g. +84901234567"
)
private String phone;
~~~

OpenAPI 3:

~~~java
@Schema(
        description = "Phone number. Use country code, e.g. +84901234567",
        example = "+84901234567"
)
private String phone;
~~~

@Schema uses description for explanatory content. For long descriptions, specify formatting rules, units, time zones, or business rules. Never put secrets, real personal data, or inappropriate public content into examples.

## 12. Replace position and property ordering

@ApiModelProperty has a position attribute in some Springfox versions. @Schema has no equivalent position attribute to guarantee property display order.

Do not treat field ordering in Swagger UI as part of the API contract. Clients must rely on property names and schemas, not display position.

If you need to control actual JSON ordering, that is a Jackson serialization concern, such as @JsonPropertyOrder. Distinguish:

- Property order in JSON serialization.
- Display order in documentation.
- Schema semantics used by clients.

Do not add annotations solely to preserve an old display order if that order has no meaning to consumers.

## 13. Replace model discriminator and subtypes

For polymorphic models, @ApiModel can declare a discriminator and subtypes. OpenAPI 3 expresses this relationship with discriminator, oneOf, anyOf, or allOf.

Payment model example:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "Payment",
        description = "Payment details",
        discriminatorProperty = "kind",
        oneOf = {
                CardPayment.class,
                BankTransferPayment.class
        }
)
public interface Payment {
}
~~~

Subtypes:

~~~java
@Schema(name = "CardPayment")
public record CardPayment(
        @Schema(example = "card")
        String kind,
        String last4
) implements Payment {}

@Schema(name = "BankTransferPayment")
public record BankTransferPayment(
        @Schema(example = "bank")
        String kind,
        String bankCode
) implements Payment {}
~~~

The example above describes two branches of Payment. For production contracts, verify discriminator mapping and how Jackson selects subtypes when deserializing. You may need @JsonTypeInfo/@JsonSubTypes or corresponding polymorphic serialization configuration.

Do not assume an OpenAPI discriminator automatically makes Jackson recognize subtypes. Both must be configured in sync.

## 14. Separate request DTOs and response DTOs

Some older Springfox models reuse one class for both requests and responses, marking fields with readOnly or writeOnly. Migrating to OpenAPI 3 is a good opportunity to review whether DTOs should be separated.

Example:

~~~java
@Schema(name = "CreateCustomerRequest")
public record CreateCustomerRequest(
        @Schema(description = "Customer name", requiredMode = Schema.RequiredMode.REQUIRED)
        String name,
        @Schema(description = "Email", requiredMode = Schema.RequiredMode.REQUIRED)
        String email
) {}

@Schema(name = "CustomerResponse")
public record CustomerResponse(
        @Schema(description = "Customer ID", format = "uuid")
        UUID id,
        String name,
        String email,
        Instant createdAt
) {}
~~~

Requests contain only data clients are allowed to submit. Responses contain only data the server is allowed to return. This separation makes schemas easier to understand, reduces the risk of leaking internal fields, and avoids complex readOnly/writeOnly annotations.

## 15. Attributes without a one-to-one mapping

Do not mechanically convert every attribute of @ApiModelProperty to @Schema. Some old attributes need reinterpretation:

| Old attribute | Migration approach |
|---|---|
| value | Move to description |
| name | Move to name only if schema renaming is genuinely needed |
| dataType | Prefer fixing the Java type; only override type/format/implementation with good reason |
| required | Use requiredMode and/or Bean Validation |
| allowableValues | Use an enum or allowableValues; add runtime validation |
| readOnly | Use accessMode READ_ONLY |
| hidden | Use hidden, while controlling data via DTOs/serialization |
| position | No direct equivalent in @Schema |
| notes | Merge relevant content into description |
| allowEmptyValue | Usually parameter metadata; review using @Parameter or an appropriate schema |
| reference | Review $ref usage in OpenAPI 3 instead of keeping old reference strings |

If an old attribute no longer has an equivalent, identify its original intent and pick the right OpenAPI construct. Never invent fake annotations or stuff constraints into description text.

## 16. Related Swagger 2 annotations to review

When migrating from Springfox to springdoc, DTOs are not the only place with old annotations. Common annotations have OpenAPI 3 counterparts:

| Springfox / Swagger 2 | OpenAPI 3 |
|---|---|
| @Api | @Tag |
| @ApiOperation | @Operation |
| @ApiParam | @Parameter |
| @ApiImplicitParam | @Parameter |
| @ApiResponse | @ApiResponse |
| @ApiResponses | @ApiResponses |
| @ApiModel | @Schema |
| @ApiModelProperty | @Schema |

Note that Swagger 2 and OpenAPI 3 @ApiResponse share the same simple name but differ in package and attribute structure. OpenAPI 3 defines responseCode, description, and content more explicitly.

Do not import the wrong one:

~~~java
// Swagger 2
import io.swagger.annotations.ApiResponse;

// OpenAPI 3
import io.swagger.v3.oas.annotations.responses.ApiResponse;
~~~

After migration, search the entire source for io.swagger.annotations imports and decide how to replace each annotation. Do not remove the old dependency before resolving all remaining references.

## 17. Complete DTO conversion example

Before migration:

~~~java
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

@ApiModel(value = "UserProfile", description = "User profile")
public class UserProfile {

    @ApiModelProperty(
            value = "User ID",
            readOnly = true,
            example = "d290f1ee-6c54-4b01-90e6-d701748f0851"
    )
    private UUID id;

    @ApiModelProperty(
            value = "Login email",
            required = true,
            example = "user@example.com"
    )
    @NotBlank
    @Email
    private String email;

    @ApiModelProperty(
            value = "Display name",
            example = "Minh Anh",
            allowableValues = "Minh Anh,Thanh Ha"
    )
    private String displayName;
}
~~~

After migration:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

@Schema(
        name = "UserProfile",
        description = "User profile"
)
public class UserProfile {

    @Schema(
            description = "User ID",
            accessMode = Schema.AccessMode.READ_ONLY,
            example = "d290f1ee-6c54-4b01-90e6-d701748f0851"
    )
    private UUID id;

    @Schema(
            description = "Login email",
            requiredMode = Schema.RequiredMode.REQUIRED,
            example = "user@example.com"
    )
    @NotBlank
    @Email
    private String email;

    @Schema(
            description = "Display name",
            example = "Minh Anh"
    )
    private String displayName;
}
~~~

In the example, allowableValues is removed from displayName because a list of sample names is not a fixed valid value domain. If business logic genuinely restricts names to an enumerated set, model it as an enum or explicit constraint.

## 18. Update dependencies and package imports

Springfox and springdoc have different dependencies and auto-configuration. When completing the migration:

- Remove the Springfox starter if nothing still uses it.
- Add the springdoc starter matching Spring MVC or WebFlux.
- Replace io.swagger.annotations imports with io.swagger.v3.oas.annotations.
- Verify no Swagger 2 dependency pulls in an old conflicting swagger-model version.
- Use one consistent annotation generation across DTOs and controllers.

For Spring Boot 3, springdoc 2.x is the corresponding starter line. Spring Boot 2 typically uses the springdoc 1.x line. Select the exact version according to the official compatibility matrix of springdoc and Spring Boot in your project.

Do not simply add the springdoc starter while leaving all Springfox configuration intact. The two libraries integrate and generate documents differently; keeping both can cause duplicate endpoints, unpredictable config, or dependency conflicts.

## 19. Verify the OpenAPI document after migration

After replacing annotations, start the application and fetch:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Check the schema:

~~~bash
jq '.components.schemas.UserProfile' openapi.json
~~~

Check key points:

- Schema name is still UserProfile.
- Model and property descriptions are preserved.
- Field id has the right readOnly/accessMode.
- Field email has the right required flag and constraints.
- Examples are not lost or turned into invalid data.
- Property names match actual JSON after Jackson serialization.
- No duplicate schema names or broken component references exist.
- Operation requests and responses reference the right schemas.

If using Swagger UI, verify the displayed model and try sample requests. However, the UI is only one consumer; still parse and validate the document with OpenAPI tools.

## 20. Test runtime behavior alongside documentation

@Schema annotations do not replace validation or serialization. After migration, run tests for real payloads:

~~~java
@Test
void createUserRejectsMissingEmail() {
    webTestClient.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                    {
                      "displayName": "Minh Anh"
                    }
                    """)
            .exchange()
            .expectStatus().isBadRequest();
}
~~~

Also verify responses do not include write-only fields or internal data. If a DTO is shared between request and response, confirm Jackson and validation work correctly in both directions.

An annotation migration can change documentation without changing runtime behavior. Even so, client generators reading the new document may emit different types or methods, so verify SDK compatibility.

## 21. Common errors when replacing annotations

| Symptom | Possible cause | Resolution |
|---|---|---|
| @Schema is not recognized | Wrong package imported or missing Swagger Core via springdoc starter | Use io.swagger.v3.oas.annotations.media.Schema and check dependencies |
| Schema still has no description | Old annotation left behind or @Schema placed where not introspected | Check field/getter/record component and OpenAPI output |
| Required field disappeared | Switched required to wrong annotation or validation not picked up | Use requiredMode and check Bean Validation |
| Nullable field treated as optional | Confused required with nullable | Verify required and nullability separately |
| Property name changed unexpectedly | @Schema(name) mismatches Jackson | Align @JsonProperty and schema name |
| Data type in docs mismatches runtime | Forced dataType/type while Java/Jackson serializes another type | Use the real Java type or verified override |
| Hidden field still appears in runtime JSON | Confused hidden with serialization/security | Use DTOs or Jackson to exclude data |
| readOnly does not block client from sending field | readOnly is only OpenAPI metadata | Validate and handle requests on the server |
| Enum does not reflect allowableValues | Old value was descriptive string, not a real enum set | Use an enum or exact constraint |
| Discriminator fails to deserialize properly | Configured OpenAPI only without Jackson polymorphism | Align @JsonTypeInfo/@JsonSubTypes |
| Duplicate annotation package conflict | Same @ApiResponse name from Swagger 2 and OpenAPI 3 | Delete old imports and use v3 package |
| Springfox and springdoc both generate docs | Old dependency not removed | Remove Springfox starter/config after migrating annotations |

## 22. Migration checklist

- [ ] Identified all classes using @ApiModel.
- [ ] Identified all fields/getters using @ApiModelProperty.
- [ ] Updated package imports to Swagger Core v3.
- [ ] Changed value to description and mapped value/name per their intended purpose.
- [ ] Reviewed required, nullable, and Bean Validation separately.
- [ ] Migrated meaningful examples and allowableValues.
- [ ] Migrated hidden and readOnly/writeOnly with awareness of runtime limits.
- [ ] Handled dataType and actual Java/Jackson types.
- [ ] Reviewed discriminators and subtypes.
- [ ] Decided how to handle position and attributes without equivalents.
- [ ] Searched for remaining related Swagger 2 annotations.
- [ ] Removed Springfox dependencies once no longer used.
- [ ] Verified /v3/api-docs and components.schemas.
- [ ] Executed runtime tests and contract tests.

## 23. Design principles

- Use @Schema at the class level to name and describe models.
- Use @Schema on fields, getters, or record components to describe properties.
- Use description for explanatory text and name for schema/property names.
- Use requiredMode to express required fields and Bean Validation to enforce at runtime.
- Use enums or real constraints instead of decorative allowableValues.
- Use accessMode for readOnly/writeOnly, without treating it as a security control.
- Never force documented types that differ from serialized JSON types.
- Review discriminators and Jackson polymorphism together.
- Separate request and response DTOs when they have differing responsibilities or fields.
- Verify both the OpenAPI document and runtime payloads after migration.

## Conclusion

When migrating from Springfox Swagger 2 to springdoc-openapi, replace @ApiModel with @Schema at the class level and @ApiModelProperty with @Schema at the property level. Common attributes such as name, description, example, required, hidden, and readOnly have corresponding expressions, though not every legacy attribute has a one-to-one mapping. In particular, required differs from nullable, hidden/readOnly do not protect runtime data, and dataType must reflect the JSON serialized by Jackson. Complete the migration by removing unused Springfox imports and dependencies, verifying /v3/api-docs, and running tests for both the contract and the live API.

## References

- [springdoc-openapi documentation](https://springdoc.org/)
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [OpenAPI Specification: Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Spring Boot Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
