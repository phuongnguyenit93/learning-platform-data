# @Schema at Class, Property, and Parameter Levels

In OpenAPI, a **schema** describes the shape and constraints of data: which properties an object has, what type each property has, which values are accepted, and which fields the client must send. springdoc-openapi typically infers schemas from Java types, Jackson, and Bean Validation. When the inferred information is not clear enough, the **@Schema** annotation from swagger-annotations lets you supplement descriptions directly on a DTO class, property, or data usage site within an operation.

The key point is placing annotations at the right layer. **@Schema** describes the data structure; **@Parameter** describes an HTTP parameter; and Spring MVC annotations such as **@RequestParam**, **@PathVariable**, and **@RequestBody** determine how the request is bound. Combining these layers properly helps OpenAPI reflect the contract that clients actually need to use.

## 1. Where Are Schemas Generated From?

Consider a simple DTO:

~~~java
public class BookResponse {
    private UUID id;
    private String title;
    private String author;

    // constructors, getters and setters
}
~~~

When a controller returns BookResponse, springdoc analyzes the Java type to create an object schema. Each property gets its corresponding type; UUID is typically represented as a string with format uuid, while title and author become string.

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(@PathVariable UUID bookId) {
        // ...
        return null;
    }
}
~~~

Part of the generated OpenAPI output may look like:

~~~yaml
components:
  schemas:
    BookResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
        author:
          type: string
~~~

The generated schema does not depend solely on the class name. springdoc and swagger-core also consider Java types, generic types, Jackson configuration, Jackson annotations, Bean Validation, and OpenAPI annotations. Therefore, the same DTO can produce different schemas if serialization behavior or metadata is changed.

@Schema helps control parts that Java types cannot fully express, such as display names, business descriptions, examples, valid values, numeric bounds, length limits, required status, or data direction.

## 2. @Schema at the Class Level

Place **@Schema** on a class or record to describe the entire model. Commonly used attributes:

| Attribute | Purpose |
|---|---|
| **name** | Sets the schema name in the documentation, typically appearing under components/schemas |
| **title** | Human-readable title of the schema |
| **description** | Explains what data the model represents |
| **example** | Illustrative example of the entire model |
| **requiredProperties** | Lists required property names at the schema level |
| **additionalProperties** | Indicates whether the object allows dynamic properties beyond the declared list |
| **additionalPropertiesSchema** | Specifies the schema type of dynamic property values |
| **deprecated** | Marks the schema as outdated and discouraged for new designs |
| **hidden** | Excludes the schema from documentation in applicable cases |

Example with a class:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "BookResponse",
    title = "Book information",
    description = "Book data returned to client applications",
    example = """
        {
          "id": "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
          "title": "Spring in Action",
          "author": "Craig Walls"
        }
        """
)
public record BookResponse(
    UUID id,
    String title,
    String author
) {}
~~~

Here:

- **name** controls the model name described in OpenAPI. This name can be referenced from a request body or response using $ref.
- **title** is a human-readable label, while **description** explains the meaning and scope of the model.
- **example** illustrates a complete object. The example must match the data types and property structure.

Do not rename schemas arbitrarily if the OpenAPI document is saved as a contract or used for SDK generation. Renaming a component can alter $ref paths and impact downstream tools, even when the HTTP endpoint does not change.

### Schema Naming and Reuse

If name is not set, the component name is usually inferred from the class name. You can use name to create a stable name that is easier to understand than an internal class name:

~~~java
@Schema(name = "CustomerSummary", description = "Summary customer information")
public record CustomerSummaryResponse(
    UUID id,
    String displayName
) {}
~~~

When multiple operations use the same Java type, springdoc typically creates a shared component schema and references it with $ref. If two different classes are assigned the same schema name, conflicts may occur or model resolution must be configured accordingly. Keep component names unique in the document and only reuse names when clearly intended.

### Class-level schema is not an operation

@Schema on a class describes a data model. It does not create an endpoint, set an HTTP method, bind a path, replace @Operation, or replace @Tag. A DTO can be used across multiple operations while keeping the same schema description.

## 3. @Schema at the Property Level

When you need to describe individual fields, place **@Schema** on a field, getter, or record component recognized by the project's model resolution mechanism. Commonly used attributes:

- **description**: meaning of the property.
- **example**: illustrative value for the property.
- **type** and **format**: type or wire format when overriding inference.
- **allowableValues**: list of valid values, commonly used for enums or strings with a fixed set of values.
- **minimum**, **maximum**, **exclusiveMinimum**, **exclusiveMaximum**: numeric bounds.
- **minLength**, **maxLength**, **pattern**: string constraints.
- **requiredMode**: specifies whether the property is required.
- **accessMode**: indicates whether the property is read-only, write-only, or read/write.
- **deprecated**: marks the property as outdated.

Example:

~~~java
@Schema(
    name = "CreateBookRequest",
    description = "Data sent by the client to create a book"
)
public record CreateBookRequest(
    @Schema(
        description = "Book title",
        example = "Spring in Action",
        minLength = 1,
        maxLength = 200,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String title,

    @Schema(
        description = "Author name",
        example = "Craig Walls",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String author,

    @Schema(
        description = "Publication year",
        example = "2024",
        minimum = "1",
        maximum = "9999"
    )
    Integer publicationYear
) {}
~~~

The schema can represent similar constraints:

~~~yaml
components:
  schemas:
    CreateBookRequest:
      type: object
      required:
        - title
        - author
      properties:
        title:
          type: string
          description: Book title
          minLength: 1
          maxLength: 200
          example: Spring in Action
        author:
          type: string
          description: Author name
          minLength: 1
          maxLength: 120
          example: Craig Walls
        publicationYear:
          type: integer
          format: int32
          description: Publication year
          minimum: 1
          maximum: 9999
~~~

The YAML example illustrates the contract output; the exact structure may vary depending on OpenAPI, swagger-core, and springdoc versions and model resolution configuration.

### requiredMode and requiredProperties

In modern versions of swagger-annotations, use **requiredMode** instead of the deprecated **required** attribute:

- **Schema.RequiredMode.REQUIRED**: the property must appear in the object.
- **Schema.RequiredMode.NOT_REQUIRED**: the property is optional.
- **Schema.RequiredMode.AUTO**: lets the library infer from available metadata.

At the class level, **requiredProperties** allows listing required property names. Avoid declaring the same rule in multiple places where they might conflict. When the contract requires precision, placing requiredMode directly on the property usually makes the intent clearest to readers.

**Required** answers whether a property must appear. It is not synonymous with whether the value is allowed to be null. How null is represented also depends on the OpenAPI version: OpenAPI 3.0 has the nullable keyword, whereas OpenAPI 3.1 is based on JSON Schema and union-type representations. Verify the output specification against the version your application publishes.

### Bean Validation and @Schema

Bean Validation annotations such as @NotNull, @NotBlank, @Size, @Min, @Max, and @Pattern can provide constraints for springdoc to include in the schema when supported by dependencies and versions:

~~~java
public record CreateAuthorRequest(
    @NotBlank
    @Size(max = 100)
    @Schema(description = "Author name", example = "Ursula K. Le Guin")
    String name,

    @Email
    @Schema(description = "Contact email", example = "author@example.test")
    String email
) {}
~~~

@Schema supplements metadata for the contract; Bean Validation defines constraints enforced at runtime when the application enables appropriate validation. For Spring to validate body data, @Valid or @Validated at the binding point and corresponding validation configuration are typically required. Seeing minLength or required in OpenAPI alone does not prove the server enforces that constraint.

If Bean Validation and @Schema annotations conflict, the documentation can become misleading. Unify the source of rules and inspect the generated JSON/YAML. For example, @Size(max = 100) should not be paired with @Schema(maxLength = 200) if the runtime contract only accepts 100 characters.

## 4. Data Types and Formats

OpenAPI has basic types such as string, integer, number, boolean, object, and array. **format** adds a specific interpretation for a type. Typically springdoc infers them from Java types:

| Java Type | Common Schema |
|---|---|
| String | type: string |
| Integer / int | type: integer, format: int32 |
| Long / long | type: integer, format: int64 |
| BigDecimal | type: number, usually with a format appropriate to the library |
| Boolean / boolean | type: boolean |
| UUID | type: string, format: uuid |
| LocalDate | type: string, format: date |
| Instant / OffsetDateTime | type: string, format: date-time |
| Enum | type: string with enum values |
| List<T> / T[] | type: array, items is the schema of T |

Only override type or format when there is a clear reason, such as a custom Java type serialized as a string. If the declared type is incompatible with actual JSON, client generators may produce wrong data types.

Example of a product code stored in Java as a String where the contract only accepts strings matching a pattern:

~~~java
public record ProductCode(
    @Schema(
        description = "Product code consisting of two letters and six digits",
        example = "AB123456",
        pattern = "^[A-Z]{2}[0-9]{6}$",
        minLength = 8,
        maxLength = 8
    )
    String value
) {}
~~~

If this is a DTO property, the schema describes a string and a pattern. However, pattern in the documentation does not validate values at runtime; use Bean Validation or domain logic if the server needs to reject invalid data.

## 5. Enums and Allowed Value Sets

For Java enums, springdoc can usually infer the list of values:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookResponse(
    UUID id,
    String title,
    BookStatus status
) {}
~~~

The corresponding schema might be:

~~~yaml
status:
  type: string
  enum:
    - DRAFT
    - PUBLISHED
    - ARCHIVED
~~~

When using @Schema(allowableValues = {...}) on a String property, you can describe the set of allowed values for a string without using a Java enum:

~~~java
@Schema(
    description = "Display language",
    allowableValues = {"vi", "en", "ja"},
    example = "vi"
)
private String locale;
~~~

If an enum is serialized under different names via Jackson, such as @JsonValue or a custom serializer, verify whether the enum values in OpenAPI match the actual JSON values. Java enum constant names are not necessarily the values sent over HTTP.

## 6. Read-Only, Write-Only Properties, and Sensitive Data

A model may contain fields that only appear in responses or are only sent in requests. Use **accessMode** to express the usage direction:

~~~java
@Schema(name = "UserProfile", description = "User profile information")
public record UserProfile(
    @Schema(
        description = "Server-assigned profile ID",
        accessMode = Schema.AccessMode.READ_ONLY,
        example = "42"
    )
    Long id,

    @Schema(
        description = "Display name",
        example = "Minh Anh"
    )
    String displayName,

    @Schema(
        description = "Recovery code sent only on creation or update",
        accessMode = Schema.AccessMode.WRITE_ONLY
    )
    String recoveryCode
) {}
~~~

- **READ_ONLY** indicates that clients only read the field from responses; the server does not expect clients to send that field as part of normal input data.
- **WRITE_ONLY** indicates that the field is sent in requests but not returned in responses.
- **READ_WRITE** indicates that the field can appear in both directions.

These attributes describe the OpenAPI contract. They do not automatically strip properties from JSON, encrypt data, or replace access control. If a sensitive field must not appear in responses, ensure the actual serializer and DTO do not return it; do not rely solely on accessMode or hidden.

In many APIs, using separate DTOs for requests and responses is clearer than sharing one model:

~~~java
public record CreateUserRequest(
    @NotBlank String displayName,
    @NotBlank String password
) {}

public record UserResponse(
    UUID id,
    String displayName
) {}
~~~

Two separate DTOs ensure input and output contracts accurately reflect the fields actually received and returned. @Schema continues to supplement descriptions for each model.

## 7. @Schema at the Operation Parameter Level

An HTTP parameter has two parts: the location and name of the parameter, and the schema describing the data type passed. For parameters in path, query, header, or cookie, use **@Parameter** to describe the parameter; the **schema** attribute inside @Parameter takes an **@Schema** to describe the value's type and constraints.

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        name = "keyword",
        description = "Search keyword by book title or author",
        example = "Spring",
        required = true,
        schema = @Schema(
            type = "string",
            minLength = 2,
            maxLength = 80
        )
    )
    @RequestParam(name = "keyword")
    String query
) {
    // ...
    return List.of();
}
~~~

There are two metadata layers here:

- **@RequestParam(name = "keyword")** tells Spring MVC which query key binds to the query variable.
- **@Parameter** describes the name, location inferred from the mapping, meaning, example, and required status in the documentation.
- **@Schema** inside @Parameter.schema describes the string type along with length limits.

The Java variable name is query; the public query parameter name is keyword. If the explicit name in @RequestParam is omitted, the application needs parameter name metadata such as -parameters for Spring to infer the right name.

### Path parameter

~~~java
@GetMapping("/{bookId}")
public BookResponse get(
    @Parameter(
        description = "Book UUID",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
        schema = @Schema(type = "string", format = "uuid")
    )
    @PathVariable("bookId") UUID id
) {
    // ...
    return null;
}
~~~

Path parameters are always required according to OpenAPI. Do not declare required=false for a parameter in the path location; if a value can be absent, the URL design should typically use a query parameter or a different route.

### Numeric query parameter

~~~java
@GetMapping
public List<BookResponse> list(
    @Parameter(
        description = "Page number, zero-based",
        example = "0",
        schema = @Schema(
            type = "integer",
            format = "int32",
            minimum = "0",
            defaultValue = "0"
        )
    )
    @RequestParam(name = "page", defaultValue = "0")
    int page
) {
    // ...
    return List.of();
}
~~~

The default value in the Spring MVC annotation determines binding behavior when the client omits the query key. defaultValue in the schema documents the contract for readers. Keep them consistent; if only one side is updated, Swagger UI may guide clients differently from the server.

### Header and cookie parameters

~~~java
@GetMapping("/preferences")
public PreferenceResponse preferences(
    @Parameter(
        description = "UI language",
        example = "vi",
        schema = @Schema(
            type = "string",
            allowableValues = {"vi", "en", "ja"}
        )
    )
    @RequestHeader(name = "X-Preferred-Language", required = false)
    String language
) {
    // ...
    return null;
}
~~~

For cookies:

~~~java
@GetMapping("/settings")
public SettingsResponse settings(
    @Parameter(
        description = "Language selection cookie",
        schema = @Schema(type = "string", example = "vi")
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    // ...
    return null;
}
~~~

Do not use @Schema to declare path/query/header/cookie location. Location belongs to the Parameter Object and is usually inferred by springdoc from Spring MVC annotations; if you need to describe it explicitly, set **in** inside @Parameter.

## 8. @Schema for Request Body and Response Content

For a request body, the schema is usually inferred from the @RequestBody parameter type. You can declare it explicitly when choosing a specific implementation type or describing complex requests/responses:

~~~java
@Operation(summary = "Create book")
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Book information to create",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateBookRequest.class)
        )
    )
    @org.springframework.web.bind.annotation.RequestBody
    @Valid CreateBookRequest request
) {
    // ...
    return null;
}
~~~

In the example, there are two annotations named RequestBody: one from Spring MVC to bind JSON and one from OpenAPI to describe the request body in documentation. When using both, use fully qualified names or intentional imports to avoid confusion.

For responses:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Book information",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookResponse.class)
    )
)
@GetMapping("/{bookId}")
public BookResponse get(@PathVariable UUID bookId) {
    // ...
    return null;
}
~~~

**implementation** specifies which class is used to build the schema. This is useful when the return type is a wrapper, interface, or generic, or when you want to explicitly identify the model in documentation. Do not use implementation to describe a type different from the JSON that the endpoint actually returns.

## 9. Collections, Nested Objects, and Element Schemas

For collections, OpenAPI needs to describe the schema of elements inside the array. Example:

~~~java
public record BookCollectionResponse(
    @Schema(description = "Books in the result")
    List<BookResponse> items,

    @Schema(description = "Total number of records", example = "120")
    long total
) {}
~~~

The schema of items is array and the items schema references BookResponse. If you need to describe an array directly in request or response content, swagger-annotations provides **@ArraySchema** to describe the container and the schema of each element:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Book list",
    content = @Content(
        array = @ArraySchema(
            schema = @Schema(implementation = BookResponse.class)
        )
    )
)
~~~

Do not set @Schema(type = "array") and omit the element schema if clients need to know the item structure. For nested objects, use separate DTOs to describe each part of the data; springdoc can reuse them via $ref.

## 10. Jackson and Property Names in Schemas

Jackson determines how Java objects are converted to JSON. Annotations such as @JsonProperty, @JsonIgnore, @JsonAlias, @JsonFormat, @JsonInclude, and naming strategies can affect property names or presence in JSON.

Example:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_id")
    @Schema(description = "Customer ID", example = "C-1024")
    private String id;

    @JsonProperty("display_name")
    @Schema(description = "Display name", example = "Nguyen An")
    private String name;

    @JsonIgnore
    private String internalNote;

    // getters and setters
}
~~~

The public schema should reflect JSON names such as customer_id and display_name. internalNote is ignored by Jackson during serialization, so it should not appear as a public property in the response schema. When controlling names or representations, check the actual OpenAPI output because annotation placement on fields/getters and `ObjectMapper` configuration can affect model resolution.

@Schema does not replace Jackson. For instance, changing description or example does not rename a JSON property. Conversely, @JsonProperty can change the JSON name without automatically providing a business description.

## 11. Hiding Schemas or Properties and Limitations of Hiding

@Schema(hidden = true) can be used to exclude a schema or property from documentation in appropriate cases:

~~~java
public record InternalBookData(
    UUID id,
    String title,
    @Schema(hidden = true)
    String internalClassification
) {}
~~~

Hiding from OpenAPI only changes the documentation. It does not prevent Jackson from serializing the property, does not strip data from the response, and does not secure the endpoint. If data must not appear in the response, use an appropriate DTO, configure Jackson properly, and test the actual payload. Do not treat hidden as a security measure.

## 12. Common Mistakes When Using @Schema

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Schema has no description | Annotation placed on a member not recognized by the model resolver or missing annotation | Place on an appropriate field/getter/record component and inspect JSON |
| Property missing from docs | Jackson ignores the property or schema is hidden | Check @JsonIgnore, visibility, and @Schema(hidden) |
| Component name changes unexpectedly | Class name or model resolution config changed | Use @Schema(name = "...") when a stable name is needed |
| required behaves unexpectedly | Inferred from Bean Validation or requiredMode differs from intent | Set requiredMode explicitly and check OpenAPI version |
| Example has wrong type | Example value is incompatible with schema | Fix example and verify JSON/YAML |
| Constraints in docs differ from runtime validation | @Schema and Bean Validation are out of sync | Synchronize constraints and test validation |
| HTTP parameter does not bind despite valid schema | Only @Schema/@Parameter declared, missing appropriate Spring MVC annotation | Fix @RequestParam, @PathVariable, @RequestHeader, or @CookieValue |
| Schema displays wrong type vs JSON | Overrode type/format inconsistently with serializer | Cross-check real payload and Jackson configuration |
| Sensitive field still appears in response | Only used hidden or writeOnly in documentation | Remove field from response DTO or configure serializer, then test |

## 13. Inspecting Schemas Generated by Springdoc

After running the application, open the OpenAPI JSON endpoint, typically **/v3/api-docs**; if YAML is enabled, you can inspect **/v3/api-docs.yaml**. Swagger UI is typically served at **/swagger-ui/index.html** or the configured path.

For each important DTO or parameter, verify:

1. **Schema name:** Does components/schemas have a stable, unique name?
2. **Description:** Do description and title accurately explain the business meaning?
3. **Properties:** Do property names match JSON after Jackson serialization?
4. **Type and format:** Are string, integer, number, boolean, object, array, and format accurate?
5. **Constraints:** Do required, enum, minimum, maximum, minLength, maxLength, and pattern reflect the contract?
6. **Data direction:** Are readOnly/writeOnly accurate for requests and responses?
7. **Operation parameters:** Are name, in, required, and schema consistent with Spring MVC annotations?
8. **Runtime payload:** Do actual requests/responses conform to the schema and examples?

Example quick schema inspection with jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.CreateBookRequest'
~~~

Inspecting parameters of an operation:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books/search"].get.parameters'
~~~

If Swagger UI renders incorrectly, inspect the JSON first. Swagger UI presents the generated documentation; it does not fix invalid schemas and does not prove runtime payload compatibility.

## 14. Rules for Choosing the Right Annotation

| Need | Appropriate Annotation |
|---|---|
| Name and describe a DTO model | @Schema on class or record |
| Describe property, example, enum, constraints | @Schema on field, getter, or record component |
| Describe query/path/header/cookie parameter | @Parameter; use nested @Schema to describe type |
| Determine binding location of query/path/header/cookie | @RequestParam, @PathVariable, @RequestHeader, @CookieValue |
| Bind JSON body data | Spring MVC @RequestBody |
| Describe request body in OpenAPI | swagger-annotations RequestBody, @Content, and @Schema |
| Describe response schema | @ApiResponse, @Content, and @Schema |
| Describe array or collection elements | @ArraySchema with @Schema |
| Enforce data validation | Bean Validation and @Valid/@Validated as configured |

When information is accurately inferred from Java types and Spring annotations, you do not need to add @Schema to every property. Only add metadata when it makes the contract clearer or when you need to control a detail that default inference does not capture accurately.

## Summary

**@Schema** describes data structure at multiple levels: on a class to name and explain a model; on a property to describe type, examples, constraints, and data direction; inside **@Parameter** to describe the schema of an HTTP value. Spring MVC determines where data is bound from, @Parameter describes the operation parameter, and @Schema describes the data shape. Synchronize OpenAPI metadata with Jackson, Bean Validation, and actual payloads, then inspect JSON/YAML at /v3/api-docs to ensure an accurate contract.
