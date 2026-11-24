# Processing Chain from Handler to Operation and Schema

When a request enters a Spring Boot application, Spring MVC finds the matching handler, binds request data to method parameters, invokes the controller, and converts the result into an HTTP response. springdoc-openapi reads the controller structure and related metadata to describe that same endpoint in the OpenAPI specification. Thus, one endpoint has two related processing chains serving two different goals: the **request execution chain** and the **API documentation build chain**.

Understanding the relationship between handler, operation, and schema answers common questions: why a method appears or does not appear in Swagger UI, why a parameter becomes a query parameter or a request body, why a DTO becomes a shared schema, and at which step to customize when documentation does not yet reflect the contract accurately.

## 1. Distinguishing Handler, Operation, and Schema

These three concepts belong to three different layers:

| Concept | Layer | Role |
|---|---|---|
| **Handler / HandlerMethod** | Spring MVC at runtime | Component that receives and handles a request matching a mapping |
| **Operation** | OpenAPI | Describes an HTTP action on a path, including inputs and outcomes |
| **Schema** | OpenAPI | Describes the structure, types, and constraints of data passed or returned |

Controller example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(
        @PathVariable UUID bookId
    ) {
        // ...
        return null;
    }
}
~~~

Spring MVC treats the getBook method as a handler mapped to GET on path /api/books/{bookId}. In OpenAPI, springdoc describes that mapping as a GET operation under path item /api/books/{bookId}. The bookId parameter becomes a path parameter; type UUID is represented by a string schema with format uuid. Return type BookResponse is analyzed to build a schema for the response.

A handler is not an operation. A handler method may be mapped to one or more mapping conditions, and an OpenAPI path item may contain multiple operations for different HTTP methods. Likewise, a schema is not a Java DTO: a DTO is a data type in source code, while a schema is the contract description exported from that type along with annotations and conversion rules.

## 2. Spring MVC Request Execution Chain

In a Spring MVC application using DispatcherServlet, a request passes through these main components:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DispatcherServlet"]
    B --> C["HandlerMapping"]
    C --> D["HandlerExecutionChain"]
    D --> E["HandlerAdapter"]
    E --> F["Argument resolvers"]
    F --> G["Controller handler method"]
    G --> H["Service / business logic"]
    H --> I["Return value handlers"]
    I --> J["HttpMessageConverter"]
    J --> K["HTTP response"]
~~~

### DispatcherServlet and HandlerMapping

**DispatcherServlet** is Spring MVC's front controller. It receives requests and orchestrates handler lookup. **HandlerMapping** matches requests against registered mappings, such as those declared with @RequestMapping, @GetMapping, @PostMapping, and variants.

Handler selection can depend on multiple conditions: HTTP method, path, query parameters, headers, Content-Type, or Accept. When a matching mapping is found, Spring builds a **HandlerExecutionChain**, containing the handler and interceptors applicable to the request.

If no mapping matches, the request may end with a 404 or corresponding mapping error. If multiple mappings conflict or conditions cannot be resolved, Spring may report configuration or request errors. These errors occur in the HTTP execution chain.

### HandlerAdapter and Argument Resolvers

**HandlerAdapter** knows how to invoke the discovered handler type. For typical controllers, the handler is a Spring MVC HandlerMethod—a method on a Spring-managed bean.

Before invoking the method, Spring must produce values for each parameter. **HandlerMethodArgumentResolver** implementations handle this. For example:

| Method Parameter | Typical Spring MVC Component |
|---|---|
| @PathVariable UUID bookId | PathVariableMethodArgumentResolver |
| @RequestParam int page | RequestParamMethodArgumentResolver |
| @RequestHeader String requestId | RequestHeaderMethodArgumentResolver |
| @CookieValue String locale | ServletCookieValueMethodArgumentResolver |
| @RequestBody CreateBookRequest body | RequestResponseBodyMethodProcessor with HttpMessageConverter |
| @ModelAttribute SearchCriteria criteria | ModelAttributeMethodProcessor |

The resolver names in the table help illustrate internal roles; normal applications do not call these classes directly. Spring also has resolvers for principals, sessions, request objects, model attributes, and many other parameter types.

For @RequestBody, Spring selects an HttpMessageConverter based on media type and target type, then reads the request content into a Java object. Jackson typically handles JSON if the application has an appropriate Jackson configuration. This process can trigger validation when the parameter is annotated with @Valid or @Validated under the corresponding mechanism.

### Invoking the Handler and Building the Response

After parameters are resolved, HandlerAdapter invokes the controller method. The controller usually delegates to a service for business logic. The method's return value is processed by **HandlerMethodReturnValueHandler** implementations.

With @ResponseBody or @RestController, Spring typically uses an HttpMessageConverter to write the object into HTTP response content. The converter chooses serialization based on return type and negotiated media type. With ResponseEntity, the controller can also specify status code and headers.

The runtime chain therefore decides what the application actually accepts and returns. It does not automatically ensure the OpenAPI document describes every case completely; that is the responsibility of the specification build chain.

## 3. Springdoc-OpenAPI Documentation Build Chain

springdoc-openapi integrates with Spring Boot and Spring MVC to discover documentable endpoints, read parameter and return types, merge OpenAPI annotations, and construct the OpenAPI object. Depending on configuration and version, the specification may be prepared during initialization or generated/refreshed when the documentation endpoint is requested; do not assume controllers are invoked to generate documentation.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Spring MVC handler mappings"]
    B --> C["Handler methods and mapping metadata"]
    C --> D["Create PathItem and Operation"]
    C --> E["Read method parameters"]
    E --> F["Parameters / RequestBody"]
    C --> G["Read return type"]
    G --> H["Responses"]
    F --> I["Model / schema resolution"]
    H --> I
    J["OpenAPI annotations and configuration"] --> D
    J --> F
    J --> H
    I --> K["Components / schemas and $ref"]
    D --> L["OpenAPI document"]
    F --> L
    H --> L
    K --> L
    L --> M["/v3/api-docs"]
    M --> N["Swagger UI or client tools"]
~~~

The steps can be understood conceptually as follows:

1. Spring creates the ApplicationContext and registers controllers, mappings, and configuration beans.
2. springdoc accesses Spring MVC's mapping metadata to learn which handlers can be documented and which path maps to which HTTP method.
3. From the mapping and HandlerMethod, springdoc builds the corresponding path item and operation.
4. Method parameters, Spring MVC annotations, and OpenAPI annotations are analyzed to determine parameters or request bodies.
5. Return types and response descriptions are used to build the response list.
6. Java types, Jackson metadata, Bean Validation, and @Schema are used during schema resolution.
7. Reusable schemas are placed in components/schemas and referenced via $ref.
8. Global, group-level, or operation-level customizations are applied to the specification.
9. The JSON document is served via the OpenAPI endpoint; Swagger UI reads it for display.

This is a conceptual architectural flow. Internal class details and exact build timing can vary by springdoc line and application configuration.

### springdoc Reads Metadata, It Does Not Run Business Logic

When generating documentation, springdoc does not send real requests to every endpoint, does not call services to produce sample data, does not query databases, and does not execute controller logic just to observe responses. It primarily uses metadata available from the Spring context, method signatures, Java types, and annotations.

This has two consequences:

- A controller can be documented even when the database has no data yet, provided the application starts and required metadata is present.
- Runtime-only behaviors such as data-dependent status codes, dynamically generated headers, or custom error payloads may not be fully inferred. They need to be described with annotations or customizers and verified with tests.

Thus, OpenAPI is a contract declared and generated from metadata, not an automatic recording of every runtime outcome.

## 4. From HandlerMethod to Path Item and Operation

Spring MVC mappings provide paths and HTTP methods. springdoc translates them into OpenAPI structures:

- A **PathItem** represents a path, such as /api/books/{bookId}.
- Each supported HTTP method on the path can create an **Operation**, such as get, put, or delete.
- An Operation holds summary, description, operationId, tags, parameters, requestBody, responses, security, and other metadata.

Example of one path with two handlers:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse get(@PathVariable UUID bookId) {
        // ...
        return null;
    }

    @DeleteMapping("/{bookId}")
    public ResponseEntity<Void> delete(@PathVariable UUID bookId) {
        // ...
        return ResponseEntity.noContent().build();
    }
}
~~~

The specification will have one path item /api/books/{bookId} with a get operation and a delete operation. It does not create two path items just because there are two Java methods. If two handlers declare the same method and path with different mapping conditions, inspect the generated output carefully because some Spring MVC conditions lack a direct equivalent in OpenAPI.

### Operation Metadata

The @Operation annotation adds content at the operation level:

~~~java
@Operation(
    summary = "Get book information",
    description = "Find a book by identifier.",
    operationId = "getBookById",
    tags = {"Books"}
)
@GetMapping("/{bookId}")
public BookResponse get(@PathVariable UUID bookId) {
    // ...
    return null;
}
~~~

@Operation does not create a Spring MVC endpoint. Spring MVC mappings determine which endpoints actually exist; @Operation enriches how that endpoint is presented in the OpenAPI contract. Placing @Operation without a valid mapping does not create an HTTP route on its own.

operationId should be unique within the document. Client generators often use it as the function name. If operationId changes between releases, regenerated SDKs may rename methods and impact client code.

## 5. From Handler Parameters to Parameter or RequestBody

springdoc combines Spring MVC binding locations with OpenAPI metadata to classify inputs:

| Annotation / Parameter Type | OpenAPI Component Typically Generated |
|---|---|
| @PathVariable | Parameter with in: path |
| @RequestParam | Parameter with in: query |
| @RequestHeader | Parameter with in: header |
| @CookieValue | Parameter with in: cookie |
| @RequestBody | RequestBody |
| @ModelAttribute or @ParameterObject | Usually represented as query parameters matching properties |

Example:

~~~java
@GetMapping("/{bookId}/search")
public List<BookResponse> search(
    @PathVariable UUID bookId,
    @RequestParam(required = false) String title,
    @RequestHeader(name = "X-Client-Version", required = false)
    String clientVersion
) {
    // ...
    return List.of();
}
~~~

In the example, the path template has placeholder bookId, so @PathVariable binds that value; title is a query parameter and X-Client-Version is a header parameter. In real code, placeholder names and bound names must match, and each parameter should be classified according to where the client sends data.

For request bodies, example:

~~~java
public record CreateBookRequest(
    String title,
    String author
) {}

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
    return null;
}
~~~

springdoc can create a requestBody with content type application/json and a schema referencing CreateBookRequest. To specify required status, media types, examples, or schemas different from default inference, add OpenAPI annotations @RequestBody, @Content, and @Schema.

Not every method parameter is client-supplied data. For instance, HttpServletRequest, Principal, Authentication, or objects injected by Spring via special mechanisms should not be mistaken for query parameters. springdoc has rules recognizing many special parameter types; if a custom type is misdocumented, apply appropriate annotations or hide the parameter from docs after confirming runtime behavior.

## 6. From Java Types to Schemas

Schemas describe data structures. springdoc uses Java types along with related metadata to build schemas:

- Primitives and wrappers map to boolean, integer, number, or string.
- UUID, dates, and timestamps can be represented with corresponding formats.
- Enums typically become a set of enum values.
- Collections and arrays become array schemas with items schemas.
- Maps typically become objects with additionalProperties.
- DTOs or records become objects with properties.
- Generic types such as ResponseEntity<BookResponse> are analyzed to extract the inner data type when resolvable.

Example:

~~~java
@Schema(name = "BookResponse", description = "Book information")
public record BookResponse(
    @Schema(description = "Book ID", example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001")
    UUID id,

    @Schema(description = "Book title", example = "Spring in Action")
    String title,

    @Schema(description = "Publication year", example = "2024")
    Integer publicationYear
) {}
~~~

The specification may contain a schema like:

~~~yaml
components:
  schemas:
    BookResponse:
      type: object
      description: Book information
      properties:
        id:
          type: string
          format: uuid
          description: Book ID
          example: 8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001
        title:
          type: string
          description: Book title
          example: Spring in Action
        publicationYear:
          type: integer
          format: int32
          description: Publication year
          example: 2024
~~~

The YAML example above illustrates structure, not a guaranteed snapshot identical across all configurations. In an actual specification, a UUID example should be a valid UUID string; a year example should be an integer. When authoring docs, always pick examples matching the declared types.

### How Jackson and Bean Validation Affect Schemas

Jackson governs how Java objects are serialized to and read from JSON. Annotations such as @JsonProperty, @JsonIgnore, @JsonPropertyOrder, naming strategies, and ObjectMapper configuration can affect property names, readability/writability, and the shape of documented data.

Bean Validation provides constraints like @NotNull, @NotBlank, @Size, @Min, @Max, @Email, and @Pattern. springdoc can use some of this metadata to add required flags or bounds to schemas when supported by the integration and version. Do not assume every constraint translates perfectly or that Java constraints are enforced simply because the schema displays them.

@Schema can add description, example, allowableValues, minimum, maximum, minLength, maxLength, format, and other metadata. Use it when Java type inference does not capture the full contract.

### Component Schemas and $ref References

When multiple operations use the same DTO, OpenAPI typically places the definition in components/schemas and uses $ref to reference it. This avoids duplicating schemas and keeps operations consistent.

~~~yaml
paths:
  /api/books:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookRequest"
      responses:
        "201":
          description: Book created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
        author:
          type: string
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

Do not rely on auto-generated component names if the name is part of a contract that must stay stable. Use @Schema(name = "...") to set explicit names. When renaming a component or changing DTO structure, assess the impact on documentation, SDKs, and integrated clients.

## 7. From Return Types to Responses

A handler's return type is a key input for springdoc to infer success responses. Example:

~~~java
@GetMapping("/{bookId}")
public ResponseEntity<BookResponse> get(
    @PathVariable UUID bookId
) {
    // ...
    return ResponseEntity.ok(null);
}
~~~

springdoc can infer the response body from BookResponse inside ResponseEntity. However, the return type does not necessarily indicate every status code that can occur. Controllers can return different statuses conditionally, exception handlers can convert errors into distinct responses, and filters or security layers can return errors before the handler is invoked.

When the contract must be explicit, document responses using @ApiResponse and @ApiResponses:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Book found",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Book not found"
    )
})
@GetMapping("/{bookId}")
public ResponseEntity<BookResponse> get(
    @PathVariable UUID bookId
) {
    // ...
    return ResponseEntity.ok(null);
}
~~~

If the application has shared @ControllerAdvice or @ExceptionHandler components, decide how global errors should be reflected in the contract. Do not assume responses returned by filters, gateways, security frameworks, or reverse proxies are inferred from controller methods. Use appropriate annotations, OpenApiCustomizer, or project-wide documentation configuration to describe shared responses.

## 8. Customizing at the Right Layer in the Documentation Build Chain

springdoc offers multiple extension points. Picking the right one keeps changes cleanly scoped:

| Extension Point | Scope | When to Use |
|---|---|---|
| Spring MVC annotations | Actual routing and binding behavior | Changing mappings, requiredness, or accepted data types |
| @Operation, @Parameter, @Schema, @ApiResponse | A specific handler or part of the contract | Adding descriptions, examples, schemas, responses |
| OpenAPI bean | Global document metadata and config | API name, version, servers, security schemes, license |
| OperationCustomizer | Each built operation | Adding metadata per operation or shared rules |
| OpenApiCustomizer | The document's OpenAPI object | Modifying document structure after generation |
| GroupedOpenApi | An endpoint group and separate document | Splitting public/internal or grouping by path/package |

Global metadata example:

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI bookApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Book API")
                .version("v1")
                .description("Book management API"));
    }
}
~~~

Operation customization example:

~~~java
@Bean
OperationCustomizer operationIdPrefix() {
    return (operation, handlerMethod) -> {
        if (operation.getOperationId() != null) {
            operation.setOperationId("books_" + operation.getOperationId());
        }
        return operation;
    };
}
~~~

Document customization example:

~~~java
@Bean
OpenApiCustomizer addCommonTag() {
    return openApi -> openApi.addTagsItem(
        new Tag().name("Books").description("Operations with books")
    );
}
~~~

The snippets above illustrate springdoc and swagger-models customization APIs; ensure imports and dependencies match your version. Customizers alter the generated documentation, not how Spring MVC selects handlers or binds requests. To change endpoint behavior, modify mappings or application logic.

For multiple independent documents, GroupedOpenApi lets you choose matching paths or packages for each group. Each group then gets its own documentation endpoint. Check which groups customizers apply to so you do not accidentally expose internal endpoints in public docs or omit operations.

## 9. Example Tracing an Endpoint from Handler to Schema

Consider the DTOs and controller:

~~~java
public record CreateBookRequest(
    @NotBlank
    @Schema(description = "Book title", example = "Spring in Action")
    String title,

    @NotBlank
    @Schema(description = "Author", example = "Craig Walls")
    String author
) {}

public record BookResponse(
    UUID id,
    String title,
    String author
) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    @Operation(
        summary = "Create book",
        operationId = "createBook",
        tags = {"Books"}
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Book created",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookResponse.class)
            )
        )
    })
    @PostMapping
    public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request
    ) {
        // ...
        return ResponseEntity.status(HttpStatus.CREATED).body(null);
    }
}
~~~

This can be traced as follows:

| Source in Code | Output in OpenAPI |
|---|---|
| @RequestMapping("/api/books") | Path item /api/books |
| @PostMapping | Operation post |
| @Operation(summary, operationId, tags) | summary, operationId, and tags |
| @RequestBody CreateBookRequest | requestBody |
| Default or declared consumes on mapping | Media type in requestBody.content |
| CreateBookRequest | Schema for request payload |
| @NotBlank and @Schema | Constraints, descriptions, or examples if supported and inferred |
| ResponseEntity<BookResponse> | Body schema for success response |
| @ApiResponse(responseCode = "201") | Response 201 with explicit description |

Abbreviated OpenAPI example:

~~~yaml
paths:
  /api/books:
    post:
      operationId: createBook
      summary: Create book
      tags:
        - Books
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookRequest"
      responses:
        "201":
          description: Book created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
          description: Book title
          example: Spring in Action
        author:
          type: string
          description: Author
          example: Craig Walls
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

This is a simplified diagram for tracing the relationship between handler, operation, and schema. The actual specification may add required flags, content types, default responses, and other metadata depending on configuration and version.

## 10. Why Might an Endpoint or Schema Not Appear as Expected?

When documentation differs from expectations, locate the issue at the right layer:

| Symptom | Layer to Inspect | Resolution |
|---|---|---|
| Endpoint missing from /v3/api-docs | Mappings and documentation filters | Check @RequestMapping, HTTP method, package/path filters, groups, and @Hidden |
| Path exists but operation is missing | Method mapping or mapping conditions | Check method mappings, conflicting mappings, and OpenAPI expressibility |
| Parameter appears in the wrong location | Argument binding | Cross-check @PathVariable, @RequestParam, @RequestHeader, @CookieValue, and path template |
| Object unexpectedly expanded into multiple query parameters | Model attribute / parameter object | Confirm binding intent; use @RequestBody if data belongs in the body |
| Request body missing schema | Message body and model resolution | Check @RequestBody, media types, generic types, and hidden annotations |
| Schema property missing or misnamed | Jackson and schema metadata | Check @JsonProperty, @JsonIgnore, naming strategy, and @Schema |
| Enum or collection has wrong shape | Java type and serialization | Check enum, item schema, style, explode, and actual binding |
| Response missing error codes | Exception handling and response metadata | Declare @ApiResponse or customize docs for global errors |
| Duplicate documentation or conflicting operationId | Mappings and operation customization | Check duplicate routes, groups, and operationId rules |

Specifically, distinguish documentation errors from runtime errors. If a handler is not registered by Spring MVC, adding @Operation will not create a route. If the handler runs fine but the schema is wrong, check model resolution and descriptive annotations. If the schema is right yet the server serializes differently, inspect Jackson and converters.

## 11. Verifying the Documentation Build Chain End-to-End

After the application starts, access the OpenAPI JSON endpoint, typically /v3/api-docs. If YAML is enabled, /v3/api-docs.yaml can be used. Swagger UI usually reads this endpoint to render documentation at /swagger-ui/index.html or the configured path.

For a sample endpoint, verify in order:

1. **Mapping:** does the endpoint have the right path and HTTP method in Spring MVC?
2. **Handler:** is the controller method registered by Spring and reachable?
3. **Input binding:** is each parameter read from path, query, header, cookie, or body?
4. **Operation:** does OpenAPI have the right path item, HTTP method, operationId, summary, and tags?
5. **Input schema:** do request body and parameters have the right types, formats, required flags, enums, and examples?
6. **Response:** do status codes, media types, headers, and schemas reflect API outcomes?
7. **Serialization:** do Jackson and HttpMessageConverter produce actual payloads compatible with the schema?
8. **Customization:** do customizers and groups unexpectedly alter or filter the document?

Automated checks should exist for critical contracts. You can fetch JSON from /v3/api-docs in tests, parse the structure, or compare against an approved snapshot. If OpenAPI is used as input to generate SDKs, verify operationId and schema compatibility before releasing.

## 12. Principles for Picking the Right Fix Point

When spotting a discrepancy, identify the question to solve:

- **Wrong route or binding behavior:** fix Spring MVC annotations and mappings.
- **Unclear endpoint description:** use @Operation or @Parameter.
- **DTO does not reflect the contract:** fix Java types, Jackson metadata, Bean Validation, or @Schema.
- **Missing status codes or errors:** add @ApiResponse or configure shared response documentation.
- **Wrong API-wide metadata:** use an OpenAPI bean.
- **Rule needed across many operations:** consider OperationCustomizer or OpenApiCustomizer.
- **Need to split docs into groups:** use GroupedOpenApi and check path/package filters.

A change in the documentation layer does not change server behavior. Conversely, changing DTO types or mappings can alter the generated specification. Therefore, every edit should verify both the generated documentation and actual requests/responses.

## Conclusion

Spring MVC handles requests by finding handlers, resolving parameters, invoking methods, and converting return values into responses. springdoc-openapi uses mapping metadata, HandlerMethod, Java types, and annotations to build path items, operations, parameters, requestBody, responses, and schemas. A handler is the execution point in the application; an operation is the HTTP action description; a schema is the data contract. By pinpointing the exact layer causing a discrepancy, you can pick the right annotation, model, or customizer and verify the documentation against runtime behavior.
