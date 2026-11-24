# Distinguishing example, examples, and default by Declaration Location

In OpenAPI, both examples and default values help integrators understand how to send data, yet they serve different meanings. **example** illustrates a single value; **examples** provides multiple named samples for readers to choose by scenario; **default** describes the default value of a schema when no explicit value is supplied. With Spring MVC, **defaultValue** attributes on binding annotations can also change actual request-handling behavior.

In springdoc-openapi, the declaration location determines where metadata is generated: **@Schema** describes a model or data type, **@Parameter** describes a path/query/header/cookie parameter, and **@Content** describes data by media type for a request body or response. The **@ExampleObject** annotation is used to create named examples inside a Parameter or Content.

This article distinguishes each location, shows the corresponding annotation, and explains how to verify the output JSON so documentation examples are not confused with server default behavior.

## 1. Three concepts to distinguish

| Concept | Meaning | Does it automatically alter runtime requests? |
|---|---|---|
| **example** | A single illustrative value for a schema, parameter, or media type content | No |
| **examples** | A collection of named examples, each able to have its own summary, description, and value | No |
| **default** | The documented default value for a schema when no explicit value is provided | Not automatically |
| **Spring defaultValue** | The fallback value Spring MVC uses when the request omits or sends an empty value at a supported location | Yes |

Example of a pagination query parameter:

~~~java
@RequestParam(name = "size", defaultValue = "20")
int pageSize
~~~

In this example, Spring MVC uses 20 when the client does not send `size` or sends an empty value. That is runtime behavior. If the documentation has:

~~~java
@Schema(defaultValue = "20", example = "10")
~~~

then **defaultValue** and **example** only describe two aspects in the schema: the published default value is 20, while 10 is an illustrative value. **@Schema** does not cause Spring to automatically replace the input value with 20.

A single example is usually enough when everyone uses the same data shape. Use multiple examples when you want to illustrate different scenarios, such as print books and e-books, or a valid request and a request with different options.

## 2. example at the schema level: describing a property or model

The **@Schema(example = "...")** annotation fits when a property or data type has a representative example that can be reused across multiple operations.

Property-level example:

~~~java
public record CreateBookRequest(
    @Schema(
        description = "Book title",
        example = "Spring in Action"
    )
    String title,

    @Schema(
        description = "ISBN-13 code",
        example = "9781617297571",
        pattern = "^[0-9]{13}$"
    )
    String isbn,

    @Schema(
        description = "Publishing format",
        example = "PRINT",
        allowableValues = {"PRINT", "EBOOK"}
    )
    String format
) {}
~~~

The generated schema may contain:

~~~yaml
CreateBookRequest:
  type: object
  properties:
    title:
      type: string
      description: Book title
      example: Spring in Action
    isbn:
      type: string
      description: ISBN-13 code
      pattern: ^[0-9]{13}$
      example: "9781617297571"
    format:
      type: string
      description: Publishing format
      enum: [PRINT, EBOOK]
      example: PRINT
~~~

A class-level example illustrates a complete object:

~~~java
@Schema(
    name = "BookResponse",
    description = "Book information returned to the client",
    example = """
        {
          "id": "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
          "title": "Spring in Action",
          "published": true
        }
        """
)
public record BookResponse(
    UUID id,
    String title,
    boolean published
) {}
~~~

**Scope:** the example is attached to the schema and can be used wherever that schema is referenced. If an operation needs an example different from the shared DTO example, declare the example at the parameter or media type level of that operation.

**@Schema(example = ...)** does not:

- Create default values for Java constructors or fields.
- Populate data automatically when Jackson deserializes JSON missing a property.
- Validate whether a value matches a pattern or bounds.
- Create multiple named choices for Swagger UI.

To describe multiple scenarios on a request body or response, use **@ExampleObject** at the **@Content** level.

## 3. default at the schema level: published default value

An OpenAPI Schema Object can describe a default value using the **default** keyword. In swagger-annotations, this can be declared via **@Schema(defaultValue = "...")**:

~~~java
public record SearchOptions(
    @Schema(
        description = "Display language",
        defaultValue = "vi",
        example = "en"
    )
    String locale,

    @Schema(
        description = "Maximum number of results",
        defaultValue = "20",
        example = "10",
        minimum = "1",
        maximum = "100"
    )
    Integer limit
) {}
~~~

Here:

- **defaultValue = "vi"** publishes the default for `locale` in the schema.
- **example = "en"** illustrates another valid value.
- **defaultValue = "20"** publishes the default for `limit`.
- **example = "10"** is an illustrative choice.

`default` in a Schema Object is contract metadata. Under JSON Schema/OpenAPI semantics, it is not a directive forcing the server or client to automatically assign that value when a property is omitted. The application must implement the corresponding fallback behavior if it wants to actually apply that value.

Example output at the schema level:

~~~yaml
type: integer
default: 20
example: 10
minimum: 1
maximum: 100
~~~

Clients read that the default is 20 and an illustrative value is 10. The schema does not force the client to send 20 or the server to fill in 20 inside the request body.

### Default on a property is not the same as a query parameter default

A property in a request body and a query parameter can share the name `limit` yet follow different processing flows:

- For a JSON body, the default value must be implemented by a constructor, application logic, Jackson configuration, or another suitable mechanism.
- For a query parameter, Spring MVC has the **defaultValue** attribute on **@RequestParam** to apply a fallback before invoking the controller.

Do not merely place **@Schema(defaultValue = "20")** and expect Spring to automatically use 20 when the client omits the property or query parameter.

## 4. @Parameter.example and @Parameter.examples for path, query, header, cookie

The **@Parameter** annotation describes an HTTP parameter. It has an **example** attribute for a single illustrative value and **examples** for multiple named Example Objects.

A query parameter example:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        description = "Publishing status",
        example = "PUBLISHED"
    )
    @RequestParam(name = "status", required = false)
    BookStatus status
) {
    // ...
    return List.of();
}
~~~

When multiple choices are needed:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        description = "Status to filter by",
        examples = {
            @ExampleObject(
                name = "published",
                summary = "Published book",
                value = "PUBLISHED"
            ),
            @ExampleObject(
                name = "draft",
                summary = "Draft",
                value = "DRAFT"
            ),
            @ExampleObject(
                name = "archived",
                summary = "Archived book",
                value = "ARCHIVED"
            )
        }
    )
    @RequestParam(name = "status", required = false)
    BookStatus status
) {
    // ...
    return List.of();
}
~~~

Named examples help readers understand each case. For scalar parameters, `value` is usually the text value that the client sends in the URL or header. Choose values that fit the schema and actual binding type.

### Example for a path parameter

~~~java
@GetMapping("/{bookId}")
public BookResponse getBook(
    @Parameter(
        description = "Book UUID",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001"
    )
    @PathVariable("bookId") UUID bookId
) {
    // ...
    return null;
}
~~~

Path parameters are always required in OpenAPI. The example only illustrates a valid UUID; it does not provide a default value when the client omits the segment in the URL.

### Example for a header parameter

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @Parameter(
        description = "Preferred response language",
        examples = {
            @ExampleObject(name = "vietnamese", value = "vi"),
            @ExampleObject(name = "english", value = "en")
        }
    )
    @RequestHeader(name = "X-Locale", required = false)
    String locale
) {
    // ...
    return List.of();
}
~~~

### Example for a cookie parameter

~~~java
@GetMapping("/preferences")
public PreferenceResponse preferences(
    @Parameter(
        description = "Cookie storing the UI language",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    // ...
    return null;
}
~~~

For a parameter that has both a schema and examples, make sure `value` matches the schema. For example, a UUID must follow the proper format; an integer must be numeric; an enum must use an allowed value.

## 5. @ExampleObject: structure of a named example

**@ExampleObject** is the annotation that describes an individual example. Commonly used attributes:

| Attribute | Meaning |
|---|---|
| **name** | Identifier key of the example in the `examples` map |
| **summary** | Short title to help readers select an example |
| **description** | Explanation of the scenario or usage |
| **value** | Sample content declared inline |
| **externalValue** | URL pointing to example content located outside the document |
| **ref** | Reference to an Example Object defined elsewhere |

Example:

~~~java
@ExampleObject(
    name = "minimal",
    summary = "Minimal request",
    description = "Provide only the required fields",
    value = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
)
~~~

**name** should be unique within the `examples` set of the same parameter or media type. **value** must be formatted appropriately for its declaration location. If the content type is `application/json`, `value` must be valid JSON; if `text/plain`, `value` can be plain text.

You can use **externalValue** when an example is large or managed as a separate file. In that case, the URL must be accessible to documentation readers. Do not declare `value` and `externalValue` as two alternative contents at the same time for one Example Object.

Do not put real access tokens, session cookies, passwords, personal data, or internal IDs into examples. Use synthetic data that still satisfies the schema's format and constraints.

## 6. Distinguishing example and examples at the Parameter Object level

The OpenAPI Parameter Object supports two attributes:

- **example**: a single value.
- **examples**: a map of multiple named examples.

These two attributes are mutually exclusive within the same Parameter Object. In annotations, choose one of the two approaches:

~~~java
@Parameter(example = "PUBLISHED")
~~~

or:

~~~java
@Parameter(
    examples = {
        @ExampleObject(name = "published", value = "PUBLISHED"),
        @ExampleObject(name = "draft", value = "DRAFT")
    }
)
~~~

Do not assign both `example` and `examples` to the same parameter. When multiple choices are needed, use `examples` and name each scenario clearly.

A Parameter Object can use `schema` to describe the data type:

~~~java
@Parameter(
    name = "page",
    description = "Page number, starting from 0",
    examples = {
        @ExampleObject(name = "firstPage", value = "0"),
        @ExampleObject(name = "thirdPage", value = "2")
    },
    schema = @Schema(
        type = "integer",
        format = "int32",
        minimum = "0"
    )
)
@RequestParam(name = "page", defaultValue = "0")
int page
~~~

In this example, `schema` specifies that `page` is a non-negative integer; `examples` provides two concrete values. Spring MVC `defaultValue` still determines the value the server uses when the query parameter is absent or empty.

In OpenAPI JSON/YAML, this list sits inside the `examples` property of the Parameter Object. Each key is an example name, and the value is an Example Object:

~~~yaml
parameters:
  - name: page
    in: query
    schema:
      type: integer
      format: int32
      minimum: 0
    examples:
      firstPage:
        summary: First page
        value: 0
      thirdPage:
        summary: Third page
        value: 2
~~~

## 7. example and examples at the @Content level for a request body

A request body can have multiple examples per media type. The OpenAPI **@Content** annotation supports **example** for a single sample content and **examples** for multiple named Example Objects.

Example of a request body with a single sample:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Book information to create",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class),
        example = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
    )
)
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
    @org.springframework.web.bind.annotation.RequestBody
    @Valid CreateBookRequest request
) {
    // ...
    return null;
}
~~~

When multiple scenarios are needed, replace `example` with `examples`:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Book information to create",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class),
        examples = {
            @ExampleObject(
                name = "printedBook",
                summary = "Printed book",
                value = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\",\"format\":\"PRINT\"}"
            ),
            @ExampleObject(
                name = "ebook",
                summary = "E-book",
                value = "{\"title\":\"Cloud Native Java\",\"isbn\":\"9781617294129\",\"format\":\"EBOOK\"}"
            )
        }
    )
)
~~~

This is the OpenAPI `RequestBody` annotation, distinct from Spring MVC's **@RequestBody**. The Spring MVC annotation binds JSON to the method parameter; the OpenAPI annotation adds description, schema, and examples for documentation.

When exported to OpenAPI, `examples` sits under the media type:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateBookRequest"
      examples:
        printedBook:
          summary: Printed book
          value:
            title: Spring in Action
            isbn: "9781617297571"
            format: PRINT
        ebook:
          summary: E-book
          value:
            title: Cloud Native Java
            isbn: "9781617294129"
            format: EBOOK
~~~

If a request body supports multiple media types, each `@Content` can have its own matching schema and examples. JSON and XML examples should not share the same `value` if their structures or syntax differ.

## 8. example and examples at the @Content level for a response

A response can have a single representative example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Book details",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookResponse.class),
        example = "{\"id\":\"8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001\",\"title\":\"Spring in Action\",\"published\":true}"
    )
)
~~~

Or multiple named examples:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Search results",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookSearchResponse.class),
        examples = {
            @ExampleObject(
                name = "oneResult",
                summary = "One book found",
                value = "{\"items\":[{\"id\":\"8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001\",\"title\":\"Spring in Action\"}],\"total\":1}"
            ),
            @ExampleObject(
                name = "noResult",
                summary = "No results",
                value = "{\"items\":[],\"total\":0}"
            )
        }
    )
)
~~~

Response examples help readers understand the payload returned by the server. They do not generate runtime responses, change status codes, or replace the controller implementation.

## 9. @Schema.example and @Content.examples have different scopes

A DTO can be used across multiple operations. Placing **@Schema(example = ...)** on the DTO creates an example attached to the model. When an operation needs business-specific examples, place **@ExampleObject** inside **@Content** of the request body or response.

~~~java
@Schema(
    name = "CreateBookRequest",
    example = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
)
public record CreateBookRequest(
    String title,
    String isbn,
    String format
) {}
~~~

An operation for importing books from a supplier might need its own example:

~~~java
@PostMapping("/api/books/import")
public BookResponse importBook(
    @org.springframework.web.bind.annotation.RequestBody
    CreateBookRequest request
) {
    // ...
    return null;
}
~~~

On this operation, **@Content(examples = ...)** can provide supplier-import examples. Thus:

- **@Schema.example** describes a representative sample of the model.
- **@Content.examples** describes concrete payloads for an operation's media type.
- **@Parameter.examples** describes different values of an HTTP parameter.

They are not three interchangeable ways to write the same thing; each location has its own scope and OpenAPI shape.

## 10. Runtime defaults in Spring MVC

Spring MVC provides **defaultValue** on several binding annotations. These values affect request binding:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @RequestParam(name = "page", defaultValue = "0")
    int page,

    @RequestParam(name = "size", defaultValue = "20")
    int size,

    @RequestHeader(name = "X-Locale", defaultValue = "vi")
    String locale,

    @CookieValue(name = "currency", defaultValue = "VND")
    String currency
) {
    // ...
    return List.of();
}
~~~

In Spring MVC, `@RequestParam`'s `defaultValue` is applied when the parameter is absent or its value is an empty string; when `defaultValue` is set, `required` defaults to `false`. `@RequestHeader` and `@CookieValue` have a similar fallback mechanism when the value is not supplied or is empty.

This differs from documentation examples:

~~~java
@Parameter(example = "2")
@RequestParam(name = "page", defaultValue = "0")
int page
~~~

Clients see example `2` in the documentation, while the server uses `0` when the client omits `page`. The example does not override the runtime default.

springdoc can infer `defaultValue` from Spring MVC annotations and place it into the parameter's schema depending on the binding type and version. If you need to verify the exact published contract, inspect `/v3/api-docs` instead of looking only at the source code.

### Request body has no defaultValue like a query parameter

Spring MVC **@RequestBody** has no `defaultValue` attribute similar to `@RequestParam`. If the body is absent, behavior depends on `required` and binding configuration; if a property inside the body is missing, the deserialized value depends on the DTO, constructor, Jackson, and application logic.

To provide a fallback for a JSON property, implement it explicitly in the DTO or application layer. **@Schema(defaultValue = "...")** only documents the default; it does not automatically populate the property during deserialization.

Path variables also do not have a conventional `defaultValue`. A path parameter must be present in the URL according to the path template and OpenAPI.

## 11. Declaration location and OpenAPI result

The following table helps choose the right annotation:

| Data location | Single example | Multiple examples | Documented default | Runtime default |
|---|---|---|---|---|
| DTO class/property | @Schema(example = "...") | Depends on OpenAPI/JSON Schema version; named examples are usually placed at media type level | @Schema(defaultValue = "...") | Constructor, Jackson, or application logic |
| Path/query/header/cookie parameter | @Parameter(example = "...") | @Parameter(examples = @ExampleObject(...)) | @Parameter(schema = @Schema(defaultValue = "...")) | Spring MVC annotation `defaultValue` at supported locations |
| Request body media type | @Content(example = "...") | @Content(examples = @ExampleObject(...)) | Body schema can declare `default` for properties | DTO/deserialization/application logic |
| Response media type | @Content(example = "...") | @Content(examples = @ExampleObject(...)) | Schema describes `default` if meaningful | Controller/service determines actual payload |

Points to remember:

- **Parameter Object** and **Media Type Object** can have either `example` or `examples`; these two fields are mutually exclusive at the same location.
- **@ExampleObject** defines each named example; `name` must be unique within the corresponding `examples` set.
- **@Schema.defaultValue** produces schema metadata; Spring MVC **defaultValue** produces binding behavior.
- **@Schema.example** attaches an example to a data type; **@Parameter.example** attaches an example to an HTTP parameter; **@Content.examples** attaches multiple payloads per media type.
- If an annotation lacks the attribute needed for your goal, do not try to misuse an annotation from another layer as a workaround. Choose the right location or use a customizer when genuinely needed.

## 12. Differences between OpenAPI 3.0 and 3.1

Where examples are declared must also be understood according to the specification version:

- In OpenAPI 3.0, the Schema Object has a single `example` property; Parameter Object and Media Type Object support `example` or `examples`.
- In OpenAPI 3.1, the Schema Object is based on JSON Schema. JSON Schema has an array-typed **examples** keyword; the legacy **example** property on Schema Object is marked deprecated in the OpenAPI 3.1 specification.
- Parameter Object and Media Type Object still retain the `examples` mechanism with named Example Objects. This is not the same as the array-typed `examples` keyword in JSON Schema.

`swagger-annotations` and `springdoc` may keep annotations compatible across versions. Therefore, **@Schema(example = ...)** may still be supported in Java code while the output depends on the OpenAPI version the application emits. When a project migrates from OpenAPI 3.0 to 3.1, check the JSON/YAML schema and how client tooling handles examples.

Do not confuse:

- **Schema examples** from JSON Schema, which are illustrative values at the schema level.
- **Parameter.examples**, which is a map of Example Objects for an HTTP parameter.
- **Content.examples**, which is a map of Example Objects for a media type.

These structures share similar names, yet their locations and data structures differ.

## 13. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Set `@Schema(example)` but Swagger UI shows no multiple choices | Schema `example` is a single sample, not a list of named examples | Use `@ExampleObject` inside `@Content.examples` or `@Parameter.examples` |
| Put `examples` on DTO but want operation-specific examples | Example is attached at the model level, not a specific media type | Declare `examples` on `@Content` of the operation |
| Set `@Parameter(example)` but server does not use it when query is omitted | `example` is metadata only | Use `@RequestParam(defaultValue = "...")` if runtime fallback is needed |
| Set `@Schema(defaultValue)` but DTO still receives `null` | Schema `default` does not automatically populate Java values | Implement the default in the constructor, Jackson, or application logic |
| Declared both `example` and `examples` on the same Parameter/Content | The two fields are mutually exclusive in OpenAPI | Choose the appropriate single field |
| Invalid JSON example | `value` does not match the media type or schema | Check syntax and sample data types |
| Enum example is rejected | Value is not in `enum`/`allowableValues` | Use the exact value sent on the wire |
| Multiple `ExampleObject` entries share the same `name` | Keys in the `examples` map are not unique | Assign unique, descriptive names |
| Schema example no longer fits a modified DTO | Sample was not updated alongside the model | Sync the example and re-check the payload |
| Displayed default differs from runtime | `@Schema.defaultValue` and Spring `defaultValue` differ | Align metadata and test binding |
| OpenAPI 3.1 displays schema example differently than expected | Difference between Schema Object and JSON Schema `examples` | Check the version, generated output, and rendering tool |

## 14. Verifying examples and defaults in /v3/api-docs

After the application starts, open **/v3/api-docs** or the configured YAML endpoint. Inspect the exact locations:

1. **components.schemas**: check `example`/`default` of the class or property.
2. **paths → operation → parameters**: check `example` or `examples` of path/query/header/cookie parameters.
3. **requestBody → content → application/json**: check `example` or `examples` of the request payload.
4. **responses → status → content**: check response examples for each status code and media type.
5. **schema**: check property `default` and its accompanying data type.

You can use `jq` for quick inspection:

~~~bash
# DTO schema
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.CreateBookRequest'

# Query parameter examples
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books/search"].get.parameters'

# Request body examples
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books"].post.requestBody.content["application/json"]'

# Response examples
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books"].post.responses["201"].content["application/json"]'
~~~

If Swagger UI renders differently than expected, inspect the generated JSON first. Swagger UI only displays the OpenAPI document; how examples are rendered also depends on the Swagger UI version and specification structure.

## 15. Testing runtime defaults separately from documentation examples

For a query parameter with a default, send requests covering at least three cases:

~~~http
GET /api/books
GET /api/books?page=2
GET /api/books?page=
~~~

Verify:

- Missing `page`: the controller receives the default value.
- `page=2`: the controller receives the value sent by the client.
- Empty `page`: Spring applies `defaultValue` according to `@RequestParam` rules.

For a request body, test missing properties, `null` property values, and concrete property values. Do not infer behavior from `@Schema.defaultValue`; inspect the deserialized object and runtime response.

Documentation examples should be verified separately:

- `example` must be valid against the schema.
- `examples` must have sufficiently distinct names and descriptions.
- Published `default` values must match runtime behavior if the documentation states it is the endpoint's default.
- Response examples must match the actual JSON returned by the controller/service.

## 16. Rules for choosing example, examples, and default

- Use **@Schema(example)** for a reusable representative value or object on a DTO.
- Use **@Parameter(example)** for a single sample value on a path, query, header, or cookie parameter.
- Use **@Content(example)** for a single payload on a request body or response media type.
- Use **@ExampleObject** inside **@Parameter(examples)** or **@Content(examples)** when multiple named samples selectable by scenario are needed.
- Use **@Schema(defaultValue)** to publish a default at the schema level.
- Use **@RequestParam(defaultValue)**, **@RequestHeader(defaultValue)**, or **@CookieValue(defaultValue)** when Spring MVC needs to apply an actual fallback.
- For request bodies, implement defaults in the DTO or application logic; OpenAPI annotations do not assign values automatically.
- Keep examples aligned with schemas, enums, formats, media types, and runtime payloads.
- When using OpenAPI 3.1, distinguish JSON Schema's `examples` keyword from the `examples` map of Parameter/Media Type Object.

## Conclusion

**example** is an illustrative sample; **examples** is a collection of named samples; **default** is the default value described in the schema. **@Schema**, **@Parameter**, and **@Content** place metadata in different locations, while **@ExampleObject** defines each named sample. Spring MVC's **defaultValue** is the actual runtime fallback mechanism for the parameter bindings that support it. Choose annotations by data location, keep documented defaults synchronized with server behavior, and verify `/v3/api-docs` alongside real requests before publishing the API contract.
