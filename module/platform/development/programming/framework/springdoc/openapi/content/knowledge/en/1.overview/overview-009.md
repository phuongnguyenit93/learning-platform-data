# Terminology Map: Operation, Parameter, Request Body, Schema, and Response

When using **springdoc-openapi**, we typically start from a Spring Boot controller and inspect the generated OpenAPI document. To read and customize that document accurately, five core concepts must be distinguished: **operation**, **parameter**, **request body**, **schema**, and **response**.

These concepts describe different parts of an API call:

- **Operation** identifies an HTTP action on a path, such as retrieving book details or creating a new book.
- **Parameter** passes data through the path, query string, header, or cookie.
- **Request body** describes content sent in the body of a request, typically JSON.
- **Schema** describes the structure and constraints of data.
- **Response** describes the results returned by the API per HTTP status code.

springdoc-openapi reads Spring MVC mappings, data types, and annotations alongside OpenAPI annotations to build the specification. Swagger UI uses that specification to render docs and allow interactive API testing. Therefore, understanding the terminology map helps you know where to place information and why a section of the document appears the way it does.

## 1. From a Controller to an Operation in OpenAPI

In OpenAPI, a **path** is a resource's relative route, such as **/api/books/{bookId}**. A **path item** groups operations sharing the same path. Each HTTP method and path pair defines an operation.

Example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(@PathVariable long bookId) {
        // ...
    }

    @PostMapping
    public BookResponse createBook(@RequestBody CreateBookRequest request) {
        // ...
    }
}
~~~

The controller above produces two operations:

| HTTP Method and Path | Meaning |
|---|---|
| **GET /api/books/{bookId}** | Retrieve a book by ID |
| **POST /api/books** | Create a book from submitted data |

These are two distinct operations even though they live in the same controller. Conversely, a single path can contain multiple operations if the application supports multiple HTTP methods on the same route.

~~~mermaid
flowchart TD
    A["Spring MVC controller"] --> B["Mapping: HTTP method + path"]
    B --> C["OpenAPI path item"]
    C --> D["Operation: GET"]
    C --> E["Operation: POST"]
    D --> F["Parameters"]
    D --> G["Responses"]
    E --> H["Request body"]
    E --> I["Responses"]
    F --> J["Schema of each value"]
    H --> K["Schema of payload"]
    G --> L["Schema of returned data"]
    I --> L
~~~

The diagram shows that an operation is the convergence point for input and output descriptions. Parameters, request bodies, and responses are not standalone operations; they are components nested inside an operation.

## 2. Operation: A Callable HTTP Action

An **Operation** is the complete description of an action exposed by the API. It is bound to an HTTP method on a path, such as **GET /api/books/{bookId}**. An operation typically includes:

- Display title and explanation: summary, description.
- Operation identifier: operationId.
- Grouping labels: tags.
- Input parameters and request body.
- List of responses by status code.
- Security details, deprecation flag, and other metadata if declared.

In springdoc-openapi, the **@Operation** annotation adds or overrides operation-level information:

~~~java
@Operation(
    summary = "Get book information",
    description = "Returns information for a single book by ID.",
    operationId = "getBookById",
    tags = {"Books"}
)
@GetMapping("/{bookId}")
public BookResponse getBook(@PathVariable long bookId) {
    // ...
}
~~~

Fields to distinguish:

| Field | Role |
|---|---|
| **summary** | Short title helping readers identify the operation |
| **description** | Explains behavior, preconditions, or caveats when calling |
| **operationId** | Unique identifier for the operation in the document; often used by client generators to name functions |
| **tags** | Groups operations in the document, typically rendered as sections in Swagger UI |

**operationId** is neither a URL nor required to match the Java method name. If you need stable function names when generating SDKs, set operationId explicitly, keep it unique, and avoid changing it casually. If omitted, springdoc can infer an identifier automatically; exact results depend on naming and configuration.

An endpoint is often thought of as the address clients call. In an OpenAPI document, look at both method and path: **GET /api/books/{bookId}** and **DELETE /api/books/{bookId}** are two different operations despite sharing the same path.

## 3. Parameter: Data Outside the Request Body

A **Parameter** is an input value passed through one of four locations:

| OpenAPI Location | Example | Common Spring MVC Annotation |
|---|---|---|
| **path** | **/books/42** | **@PathVariable** |
| **query** | **/books?page=2&size=20** | **@RequestParam** |
| **header** | **X-Request-Id: abc-123** | **@RequestHeader** |
| **cookie** | Session login cookie | **@CookieValue** |

Each parameter is identified by its name and location (**name** + **in**). Its description may include data type, whether it is required, explanatory text, example values, and constraints.

~~~java
@Operation(summary = "Search books with pagination")
@GetMapping
public List<BookResponse> searchBooks(
    @Parameter(description = "Page number, zero-based", example = "0")
    @RequestParam(defaultValue = "0") int page,

    @Parameter(description = "Number of items per page", example = "20")
    @RequestParam(defaultValue = "20") int size,

    @Parameter(description = "Optional language code", example = "vi")
    @RequestParam(required = false) String locale
) {
    // ...
}
~~~

Here, **page**, **size**, and **locale** are query parameters. They are not a JSON body. springdoc can typically infer locations and data types from Spring MVC annotations; **@Parameter** adds descriptions, examples, or OpenAPI details where needed.

### Rules for required

- Parameters in the **path** location are always required because their value is part of the URL path.
- Query, header, and cookie parameters can be required or optional. For instance, **@RequestParam(required = false)** denotes an optional query parameter.
- Default values in Spring (**defaultValue**) and the **required** attribute relate to how clients use the API, yet should not substitute for business descriptions. Inspect the generated document to verify required and schema match the intended contract.

Avoid cramming a large JSON payload into multiple parameters just to avoid a request body. Parameters suit identifiers, filters, pagination, or small metadata. Structured data sent in the request body should be modeled as a request body.

### Parameter Object

When an endpoint has many query filters, you can group them into a DTO or filter object. For eligible object types, springdoc-openapi's **@ParameterObject** expands properties into query parameters instead of describing them as a JSON object inside a request body.

~~~java
public class BookSearchCriteria {
    private String title;
    private String author;
    private Integer page;
    private Integer size;

    // getters and setters
}

@GetMapping("/search")
public List<BookResponse> search(
    @ParameterObject BookSearchCriteria criteria
) {
    // ...
}
~~~

Use this approach when the fields are genuinely query parameters. If the API expects a JSON object in the request body, use a request body.

## 4. Request Body: Data Sent in the Body of a Request

**Request body** describes content placed in the HTTP request body. In REST APIs, a JSON payload is commonly mapped to a DTO using Spring MVC's **@RequestBody**.

~~~java
public record CreateBookRequest(
    String title,
    String author,
    Integer publicationYear
) {}

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse createBook(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
}
~~~

In this example:

- Spring MVC's **@RequestBody** instructs Spring to read the request body and convert it into **CreateBookRequest**.
- **consumes = application/json** declares the media type accepted by the endpoint.
- **CreateBookRequest** is the payload's data type; its structure is represented by a schema.
- **@Valid** triggers checks on Bean Validation constraints declared on the DTO, if the application has corresponding validation configured.

A request body in OpenAPI has these key elements:

| Element | Meaning |
|---|---|
| **required** | Whether the client must send a request body |
| **content** | Media types accepted by the operation |
| **schema** | Data structure for each media type |
| **example / examples** | Sample payloads helping users understand how to send data |

For JSON payloads, the content section typically uses the **application/json** key. An operation can also accept multiple formats, such as JSON and multipart form data, if supported by the controller and application configuration.

### Distinguishing Two Annotations Named RequestBody

In Spring Boot code, two annotations are easily confused:

- **org.springframework.web.bind.annotation.RequestBody** belongs to Spring MVC and binds the HTTP body to a method parameter.
- **io.swagger.v3.oas.annotations.parameters.RequestBody** belongs to OpenAPI and describes the request body in documentation.

Usually only the Spring MVC annotation is needed for springdoc to infer the request body. When wanting to specify details such as description, required, media type, or an explicit schema, you can add the OpenAPI annotation. If using both in the same method, write clear imports or use fully qualified names to avoid collisions.

~~~java
@Operation(summary = "Create book")
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public BookResponse createBook(
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
}
~~~

Do not declare a request body for an operation merely because a Java method has a parameter. Determine whether that parameter is passed via path, query, header, cookie, or request body, then choose the appropriate annotation. For **GET**, conventional design passes filters via query parameters; request bodies on **GET** are not consistently supported across clients, proxies, or tools.

## 5. Schema: A Description of Data Structure

A **Schema** describes the shape and constraints of a value. A schema can represent:

- A primitive value such as string, integer, number, or boolean.
- An object composed of multiple properties.
- An array of elements of the same type.
- A constrained set of choices such as an enum.
- Nested data types or references to other schemas.

Schemas can appear in parameters, request bodies, and responses. Thus, schema is not synonymous with request body; request body is the transport location of input data, whereas schema describes the structure of data carried at that location.

DTO example:

~~~java
public record CreateBookRequest(
    @NotBlank
    @Schema(description = "Book title", example = "Spring in Action")
    String title,

    @NotBlank
    @Schema(description = "Author name", example = "Craig Walls")
    String author,

    @Min(1)
    @Schema(description = "Publication year", example = "2024", minimum = "1")
    Integer publicationYear
) {}
~~~

~~~java
@Schema(name = "BookResponse", description = "Book information returned to the client")
public record BookResponse(
    @Schema(description = "Book ID", example = "42")
    Long id,

    @Schema(description = "Book title", example = "Spring in Action")
    String title,

    @Schema(description = "Author name", example = "Craig Walls")
    String author
) {}
~~~

**@Schema** from swagger-annotations lets you describe names, meanings, examples, types, or representations of schemas and properties. Bean Validation constraints such as **@NotBlank** and **@Min** can also be reflected into schemas when supported by the relevant libraries and settings. After generating documentation, inspect the actual output rather than assuming every annotation translates identically across all versions.

### Schema Objects and components/schemas

OpenAPI typically places reusable schemas in **components/schemas**. Operations can reference this schema using **$ref**. This organization allows multiple operations to share a single definition without repeating structures.

~~~yaml
components:
  schemas:
    BookResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
          example: 42
        title:
          type: string
          example: Spring in Action
        author:
          type: string
          example: Craig Walls
~~~

When a controller returns **BookResponse**, springdoc typically infers the schema from the Java type and can generate a reference to the corresponding component. Component names and inline schema extraction depend on configuration, annotations, and library version.

### required Differs from nullable

These two concepts answer two different questions:

- **required**: must the property appear in the object?
- **nullable**: if present, is the property allowed to hold a **null** value?

A property may be optional yet must have a non-null value when sent; or it may be required to appear while allowing a **null** value, depending on the OpenAPI version and declared schema. Do not infer nullable solely because a Java field uses a reference type. Inspect the generated OpenAPI JSON/YAML and pick the representation matching the OpenAPI version your project uses.

## 6. Response: Outcomes Returned by Status Code

**Response** describes the outcomes an operation can return. In OpenAPI, each response is keyed by an HTTP status code or the **default** key. A response can describe:

- The status code, such as **200**, **201**, **400**, **404**, or **500**.
- Explanatory text via **description**.
- Returned data by media type and schema.
- Headers or examples if needed.

For example, creating a book may return **201 Created** with the new book details; if input data is invalid, the API may return **400 Bad Request** with error details.

~~~java
@Operation(
    summary = "Create book",
    description = "Creates a new book and returns the newly created information."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Book created successfully",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid input data",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<BookResponse> createBook(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
}
~~~

In this example, **ApiError** is an application-defined error DTO. If the project uses **ProblemDetail** or another error structure, document the exact type actually returned by the exception handler.

springdoc can infer part of a response from the method return type, such as **BookResponse** or **ResponseEntity<BookResponse>**. However, Java return types do not automatically describe every error case, every status code, or every media type. Declare **@ApiResponse** / **@ApiResponses** when the contract needs to make those cases explicit.

Commonly used annotations:

- **@ApiResponse**: describes a specific response.
- **@ApiResponses**: groups multiple responses on an operation.
- **@Content**: describes content by media type.
- **@Schema**: points to the content's data structure.
- **@ExampleObject**: supplies concrete examples for content.

Avoid documenting only success responses. Clients also need to know predictable error outcomes to handle them properly, such as validation failures, resource not found, or insufficient permissions.

## 7. Reading the Generated OpenAPI Output

The concepts above connect together inside the document. The condensed example below illustrates a book retrieval operation:

~~~yaml
paths:
  /api/books/{bookId}:
    get:
      operationId: getBookById
      summary: Get book information
      parameters:
        - name: bookId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        "200":
          description: Book retrieved successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
        "404":
          description: Book not found
components:
  schemas:
    BookResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        title:
          type: string
        author:
          type: string
~~~

You can read it from the outside in:

1. **paths** holds the resource path.
2. **get** is the operation exposed on that path.
3. **parameters** describes the **bookId** value in the path.
4. **responses** lists possible returned outcomes by status code.
5. **content** specifies the media type; **schema** describes the response data.
6. **$ref** points to the shared definition under **components/schemas**.

If the operation accepts a JSON body, the **requestBody** section sits at the same level as **parameters** and **responses** inside the operation. Within **requestBody.content.application/json.schema**, you again find the schema describing the payload.

## 8. Map of Common Annotations in Spring Boot

| Goal | Spring MVC / Java | Supplementary OpenAPI Annotation |
|---|---|---|
| Define operation | **@GetMapping**, **@PostMapping**, **@PutMapping**, **@DeleteMapping**, **@RequestMapping** | **@Operation** |
| Path parameter | **@PathVariable** | **@Parameter** |
| Query parameter | **@RequestParam** | **@Parameter**, **@ParameterObject** |
| Header parameter | **@RequestHeader** | **@Parameter** |
| Cookie parameter | **@CookieValue** | **@Parameter** |
| Request body | **@RequestBody** | **@io.swagger.v3.oas.annotations.parameters.RequestBody** |
| DTO and property structure | Java types, records, Bean Validation | **@Schema**, **@ArraySchema** |
| Response | Return type, **ResponseEntity<T>** | **@ApiResponse**, **@ApiResponses**, **@Content**, **@ExampleObject** |

Spring MVC annotations express controller runtime behavior. OpenAPI annotations add API contract descriptions. springdoc combines both sources to generate documentation. When multiple annotations describe the same detail, inspect the generated output to ensure there are no contradictory declarations or unintended overrides.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| One controller equals one operation | One controller can contain multiple operations; each HTTP method on a path is a distinct operation |
| Parameters and request body are the same | Parameters live in path, query, header, or cookie; request body lives in the HTTP body |
| A schema is simply the Java DTO | A DTO is a type in source code; a schema is the exported contract description and can be customized |
| Having a return type fully describes responses | Return types help infer success responses, yet do not necessarily describe all error codes, headers, and media types |
| **required** means **nullable: false** | required states whether the property must appear; nullable states whether the value can be null |
| **operationId** is the endpoint URL | operationId is the operation identifier, typically used for client generation and referencing |

A helpful principle when designing documentation: ask where the data lives first, then pick the OpenAPI concept. If it defines an action, it belongs to operation; if passed via URL/header/cookie, it is a parameter; if placed in the HTTP body, it is a request body; to describe data shape, use schema; if it is an API outcome, describe it with response.

## 10. Verifying the Contract After Generating Documentation

After adding or modifying annotations, inspect the OpenAPI specification generated by springdoc, usually at **/v3/api-docs**; if YAML output is enabled, inspect **/v3/api-docs.yaml**. Swagger UI is typically configured at **/swagger-ui/index.html** or the project's configured path.

For every important operation, verify:

- Do method and path match the controller mapping?
- Do parameters have the right locations, data types, and required states?
- Does the request body have the right media type, schema, and required flag?
- Does the schema include all properties, types, enums, examples, and needed constraints?
- Do responses cover all status codes, descriptions, media types, and schemas for both success and errors?
- Is operationId unique and stable?

Swagger UI helps humans read and try the API, while the OpenAPI JSON/YAML file is the contract that can be validated automatically, used to generate clients, or integrated with other tools. Therefore, do not look only at Swagger UI: inspect the generated specification directly, especially after changing DTOs, generic responses, exception handlers, or annotations.

## Conclusion

Five concepts form a unified structure: **operation** describes an HTTP action; **parameter** and **request body** describe two ways of passing inputs; **schema** describes data structure; **response** describes outcomes by status code. springdoc-openapi connects Spring Boot controller structures to these concepts to generate OpenAPI documentation and feed Swagger UI. Classifying each piece of information properly and inspecting the output specification ensures API documentation reflects the contract clients actually need to use.
