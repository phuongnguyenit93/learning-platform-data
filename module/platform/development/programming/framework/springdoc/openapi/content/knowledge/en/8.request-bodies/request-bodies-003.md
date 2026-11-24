# Describing `application/json` with `@Content` and `@Schema`

When a REST API accepts JSON data, the client sends the payload in the HTTP request body typically with the `application/json` media type. Spring MVC uses `@RequestBody` to convert JSON into a Java object. Springdoc relies on the DTO type and OpenAPI metadata to describe the request body in the documentation; when you need explicit control over media types, schemas, examples, and requiredness, you can use `@Content` and `@Schema`.

The key point is to distinguish the two responsibilities: Spring annotations control how the application receives actual requests, whereas OpenAPI annotations describe the contract for clients. Both parts must reflect the same behavior. Documentation might declare a required request body and a very detailed schema, yet the controller must still accept and validate the data according to that contract.

## 1. JSON request body in HTTP and OpenAPI

A request to create a book might be sent as follows:

```http
POST /api/books HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "title": "Spring Boot Fundamentals",
  "publicationYear": 2025
}
```

In this request:

- `POST /api/books` identifies the operation being called.
- `Content-Type: application/json` informs the server of the request body's format.
- `Accept: application/json` indicates that the client wants a JSON response.
- The JSON section contains the book creation data.

In OpenAPI 3, the request body is described in the `requestBody` property of the operation. Media types are declared inside `requestBody.content`, while the schema describes the data structure:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateBookRequest'
```

`required: true` indicates that the client must send a request body. `application/json` specifies the content format. `$ref` points to the schema defined under `components.schemas`.

## 2. Receiving JSON with Spring's `@RequestBody`

In Spring MVC, `@org.springframework.web.bind.annotation.RequestBody` instructs Spring to read the body and convert it into the corresponding Java type. Example:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
        @RequestBody CreateBookRequest request) {
    // Process request data.
    return new BookResponse(1L, request.title());
}
```

Spring uses an `HttpMessageConverter` to convert JSON into `CreateBookRequest`. Jackson is typically the default converter in a Spring Boot Web application. The DTO type provides the base structure from which Springdoc infers the request body schema.

The `consumes` attribute on `@PostMapping` restricts the media types the endpoint accepts. When `consumes = application/json` is set, the client needs to send a request with a matching `Content-Type: application/json`. If `consumes` is omitted, Spring can still accept JSON via the converter, though declaring it explicitly makes the contract and mapping clearer.

## 3. Declaring DTOs and schemas with `@Schema`

The DTO describes the fields a client can send. `@Schema` belongs to OpenAPI 3 annotations and is used to add names, descriptions, examples, formats, and constraints to the schema.

Example `CreateBookRequest.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(description = "Data sent by the client to create a new book")
public record CreateBookRequest(

    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Book title, must not be blank and at most 120 characters",
        example = "Spring Boot Fundamentals"
    )
    String title,

    @Min(1)
    @Schema(
        description = "Publication year, if provided",
        example = "2025"
    )
    Integer publicationYear
) {}
```

In this example:

- `@Schema` on the record describes the entire object.
- `@Schema` on each component explains its meaning and provides an example.
- `@NotBlank` requires `title` to have non-empty text.
- `@Size(max = 120)` limits the length of the book title.
- `@Min(1)` requires the publication year, if provided, to be at least 1.

Springdoc can read common Bean Validation annotations to include constraints in the OpenAPI schema. However, validation is only enforced when the application enables validation—for example, having the `spring-boot-starter-validation` dependency and annotating the controller parameter with `@Valid`. Do not assume that merely adding `@Schema` will cause Spring to validate the data.

## 4. Describing the request body with `@Content` and `@Schema`

Springdoc can infer the request body from the `@RequestBody` parameter and DTO type. When you need to explicitly specify the media type, description, or examples, declare the OpenAPI request body inside `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Create a new book",
    description = "Accepts JSON data and creates a book record",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Details of the book to create",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateBookRequest.class),
            examples = @ExampleObject(
                name = "NewBook",
                summary = "Book creation data",
                value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse create(
        @RequestBody CreateBookRequest request) {
    return new BookResponse(1L, request.title());
}
```

The snippet uses two annotations named `RequestBody` from two different packages:

- `org.springframework.web.bind.annotation.RequestBody` is placed on the method parameter so Spring reads the HTTP body.
- `io.swagger.v3.oas.annotations.parameters.RequestBody` sits inside `@Operation` to describe the request body in the OpenAPI contract.

The example uses the fully qualified name for the OpenAPI annotation to avoid import confusion. `@Content` specifies the content per media type; `@Schema(implementation = CreateBookRequest.class)` points to the DTO class used as the schema; `@ExampleObject` provides a sample payload for Swagger UI to display.

`required = true` in the OpenAPI annotation must be consistent with the controller's behavior. For a Spring `@RequestBody` parameter, `required` defaults to `true`. If the endpoint allows omitting the body, adjust both the Spring annotation and OpenAPI metadata, and handle `null` in code.

## 5. Role of `@Content`

`@Content` describes the content sent or received for a given media type. In a request body, it is usually placed inside the OpenAPI `@RequestBody` annotation and can contain a schema, examples, or encoding.

Commonly used attributes:

| Attribute | Role |
| --- | --- |
| `mediaType` | Content type, such as `application/json` |
| `schema` | Data structure of the content |
| `examples` | One or more payload examples |
| `example` | Simple example for the content |
| `encoding` | Encoding rules for properties, typically useful with multipart/form-data |

For standard JSON APIs, `mediaType = MediaType.APPLICATION_JSON_VALUE` and the DTO schema are usually sufficient. There is no need to create a separate `@Content` if Springdoc already infers the content accurately from `@RequestBody` and the parameter type. Add explicit configuration when you want exact control over media type, description, or examples.

A request body can support multiple media types. For example, an API might accept JSON and another format. In that case, declare multiple `@Content` entries in the OpenAPI request body's `content` array, each with its appropriate `mediaType` and schema. The Spring mapping must also actually support those formats; merely adding a media type to the documentation does not make a converter handle the new format.

## 6. Role of `@Schema(implementation = ...)`

`@Schema` describes the data structure. When setting `implementation = CreateBookRequest.class`, you instruct OpenAPI to use that class's schema for the request content.

Short example:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateBookRequest.class)
)
```

Springdoc will create or reference the corresponding schema in `components.schemas`, usually using `$ref` instead of repeating the entire structure in every operation. This allows multiple endpoints to reuse the same DTO and keeps the documentation consistent.

Some common `@Schema` attributes:

| Attribute | Meaning |
| --- | --- |
| `name` | Display name or schema name depending on context |
| `description` | Description of the object or field |
| `example` | An illustrative value |
| `type` | OpenAPI data type when explicitly specified |
| `format` | Detailed format such as `date`, `date-time`, `email` |
| `implementation` | Java class used as the schema |
| `requiredMode` | Determines how a required field is marked in the schema |
| `accessMode` | Indicates whether the field is read-only, write-only, or read/write |

For DTOs, let Springdoc infer data types from Java and only specify useful metadata explicitly. If `type` or `implementation` is set to something inconsistent with the actual type, the schema may conflict with the JSON that Jackson serializes/deserializes.

## 7. Complete controller example with validation

The following example combines a DTO, Spring `@RequestBody`, `@Valid`, `@Content`, `@Schema`, and response metadata:

```java
package com.example.books;

import com.example.books.dto.CreateBookRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
        summary = "Create a new book",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Book details in JSON format",
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateBookRequest.class)
            )
        )
    )
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Book created successfully"),
        @ApiResponse(responseCode = "400", description = "Invalid JSON or data failed validation")
    })
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookResponse response = new BookResponse(
            1L,
            request.title(),
            request.publicationYear()
        );

        return ResponseEntity.status(201).body(response);
    }

    public record BookResponse(
        long id,
        String title,
        Integer publicationYear
    ) {}
}
```

The controller returns `201 Created` when creation succeeds. For malformed JSON or data failing validation, Spring typically returns `400 Bad Request` when using the default error handling configuration or a corresponding exception handler. If the project has a custom error format, describe the error response using the actual error schema instead of only a generic description.

Ensure the project includes the validation dependency, for example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Do not add this dependency solely to generate documentation; it is needed when you want validation annotations like `@NotBlank`, `@Size`, or `@Min` to be enforced.

## 8. Required request bodies, optional bodies, and schema `required`

Two different `required` concepts must be distinguished:

- `requestBody.required`: indicates whether the entire body must appear in the request.
- `schema.required`: the list of required field names inside the JSON object.

Example of a required body where the `publicationYear` field is optional:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - title
        properties:
          title:
            type: string
          publicationYear:
            type: integer
            format: int32
```

The request must contain a JSON body, though `publicationYear` is not required. The `title` field must appear in the object. When using records or DTO classes, validation annotations, data types, and `@Schema(requiredMode = ...)` settings can influence the generated schema. Verify the resulting OpenAPI document rather than assuming from constructors or Java types alone.

If the body is genuinely optional, Spring can declare:

```java
public ResponseEntity<Void> updateNote(
        @RequestBody(required = false) UpdateNoteRequest request) {
    // Handle null request per contract.
    return ResponseEntity.noContent().build();
}
```

In that case, the OpenAPI request body annotation also needs `required = false`. If one side specifies required and the other permits omitting the body, the documentation becomes misleading and may cause clients to integrate incorrectly.

## 9. JSON examples and `@ExampleObject`

Payload examples help Swagger UI users understand what data to send. You can declare a single example:

```java
@Content(
    mediaType = MediaType.APPLICATION_JSON_VALUE,
    schema = @Schema(implementation = CreateBookRequest.class),
    examples = @ExampleObject(
        name = "CreateBook",
        summary = "Create book with publication year",
        value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
    )
)
```

Or declare multiple examples for different scenarios:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateBookRequest.class),
    examples = {
        @ExampleObject(
            name = "WithYear",
            summary = "With publication year",
            value = "{\"title\":\"Spring Boot Fundamentals\",\"publicationYear\":2025}"
        ),
        @ExampleObject(
            name = "WithoutYear",
            summary = "Without publication year",
            value = "{\"title\":\"Practical REST API\"}"
        )
    }
)
```

Examples must be valid JSON and match the schema. Never include tokens, passwords, personal data, or real customer information in examples. If there are multiple validation scenarios, provide clear valid examples and document rejected conditions separately.

## 10. Generated OpenAPI structure

After starting the application, visit `/v3/api-docs` and locate the POST operation. A condensed result may look like the following structure:

```yaml
paths:
  /api/books:
    post:
      requestBody:
        description: Book details in JSON format
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookRequest'
      responses:
        '201':
          description: Book created successfully
        '400':
          description: Invalid JSON or data failed validation
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
          description: Book title
          example: Spring Boot Fundamentals
        publicationYear:
          type: integer
          format: int32
          example: 2025
```

This is an illustrative structure. Actual schema names, required lists, descriptions, and examples depend on your DTO, annotations, Jackson configuration, Bean Validation, and Springdoc version.

In Swagger UI, the POST operation will have a Request body section with the `application/json` media type and corresponding schema. Users can click **Try it out**, edit the payload, and send a request if the server permits it.

## 11. Common errors when describing JSON request bodies

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Request body missing in OpenAPI | Method lacks Spring `@RequestBody`, parameter is recognized as another parameter type, or metadata override is incorrect | Inspect controller signature and `/v3/api-docs` |
| Swagger UI displays an empty schema | DTO is not recognized, complex generic type, or `@Schema(implementation = ...)` points to wrong class | Inspect schema in `components.schemas` |
| Wrong media type displayed | `consumes` or `@Content.mediaType` mismatch | Synchronize Spring mapping and OpenAPI metadata |
| Docs say body is required but server allows omitting it | `requestBody.required` does not match `@RequestBody(required = false)` | Synchronize both annotations |
| Valid JSON yet request returns `400` | Data type cannot be converted or Bean Validation rejects data | Inspect error response, DTO, and constraints |
| Required fields are not represented properly | Missing validation or appropriate schema required mode | Inspect schema `required` and DTO annotations |
| Example does not appear or has wrong format | JSON in `@ExampleObject` is invalid or mismatches schema | Check JSON string and generated OpenAPI output |
| API supports multiple formats but docs only show JSON | Only one `@Content` declared or mapping lacks `consumes` | Declare each media type and verify actual converters |

When an issue arises, inspect the OpenAPI JSON first and compare it against controller behavior. If the specification is accurate but actual requests fail, focus on mapping, converters, DTOs, and validation. If requests work properly but the documentation is wrong, inspect the OpenAPI annotations and how Springdoc infers the schema.

## 12. Checklist for describing `application/json`

- [ ] Controller uses Spring `@RequestBody` for the JSON parameter.
- [ ] `consumes` reflects the media types the endpoint actually supports.
- [ ] DTO has data types and field names matching the real JSON.
- [ ] `@Schema` describes the object, fields, and necessary examples.
- [ ] `@Content` declares `application/json` and the right schema when explicit description is needed.
- [ ] OpenAPI `@RequestBody.required` matches the behavior of Spring `@RequestBody`.
- [ ] Distinguish a required request body from required fields inside the schema.
- [ ] JSON examples are valid and contain no sensitive data.
- [ ] Bean Validation is enabled if the contract has constraints to enforce.
- [ ] Verified `/v3/api-docs` and the Request body section in Swagger UI.
- [ ] Error responses reflect the application's actual error format.

`@Content` defines the media type and content of a request body, while `@Schema` describes the JSON structure. Combining these two annotations with Spring's `@RequestBody` and clear DTOs helps Springdoc generate an understandable contract, letting clients know exactly what data to send, in what format, and which fields are required.
