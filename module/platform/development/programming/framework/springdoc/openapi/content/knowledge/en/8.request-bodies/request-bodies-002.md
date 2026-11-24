# Request Body Object and the `required` Flag

## 1. What is a request body in an HTTP API contract?

A request body is the data payload sent by a client in the body of an HTTP request. It is commonly used when creating or updating resources, sending business commands, or uploading files to the server. For example, when creating a product, the client sends JSON containing a name, price, and category; the controller receives that JSON and converts it into a Java object for processing.

In OpenAPI, this part is described by the **Request Body Object**. The object tells consumers:

- Which media type the request content is sent in, such as **application/json** or **multipart/form-data**.
- How the data is structured via its schema.
- Whether the body must be present.
- What readers need to know about sending the data through description and examples.

In Spring Boot, Springdoc OpenAPI usually infers the request body from a controller parameter annotated with **@RequestBody**, its DTO type, and the endpoint mapping. OpenAPI annotations add extra descriptions when finer control over documentation content is needed.

A request body differs from parameters in the path, query, header, or cookie. Those values are described by the Parameter Object; data in the body of the request is described by the Request Body Object.

## 2. Structure of the Request Body Object

Inside an Operation Object, the **requestBody** field holds the Request Body Object. Its core structure consists of three properties:

| Property | Role |
|---|---|
| **description** | Explains the purpose, rules, or conditions of the submitted data |
| **content** | Maps media types to schemas, examples, and content encoding rules |
| **required** | Indicates whether the request is required to include a body |

Among these, **content** is the required property of the Request Body Object. **description** and **required** are optional; per OpenAPI, **required** defaults to false if omitted.

Example of an operation accepting JSON:

~~~yaml
paths:
  /api/products:
    post:
      summary: Create product
      requestBody:
        description: New product details
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        "201":
          description: Product created
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
        price:
          type: number
~~~

This example demonstrates two distinct levels of requiredness:

- **requestBody.required: true** requires the client to send a request body.
- **schema.required: [name, price]** requires the JSON object to contain the name and price properties.

These two rules are independent. A request body can be required to appear while still allowing an empty object; conversely, if the body is optional, the schema still governs which properties must be present whenever the client does send a body.

## 3. Properly understanding the Request Body `required` flag

The **required** flag on the Request Body Object determines the presence of the entire request body.

- **required: true**: the client must send a body in one of the media types declared in content.
- **required: false** or omitted: the client may omit the body.
- When a body is sent, its content must still conform to the corresponding schema and media type.

Example:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        properties:
          comment:
            type: string
~~~

The body must be present, but the schema above does not require the comment property because there is no required list at the schema level.

Conversely:

~~~yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        type: object
        required:
          - comment
        properties:
          comment:
            type: string
~~~

The client may omit the body. If a body is sent, the object must include the comment property.

### 3.1. Distinguishing body required from property required

This is a common point of confusion when reading OpenAPI:

| Configuration | Meaning |
|---|---|
| **requestBody.required** | Whether the entire HTTP request body is required |
| **schema.required** | Which properties are required inside the object |
| **schema.properties.name** | Describes the type and constraints of a single property |
| **nullable** or a type containing null | Allows a null value depending on the OpenAPI version and schema |

For example, if name is in schema.required, the client must send the name property when sending the object. That does not automatically imply that name's value is allowed to be null; nullability must be described separately in the schema.

### 3.2. Distinguishing `required` from `nullable`

The following three cases have different meanings:

1. The body is not sent.
2. The body is sent, but a property is absent.
3. The body is sent, and the property is present with a null value.

In OpenAPI 3.0, a schema can use **nullable: true** to allow null alongside the declared type. In OpenAPI 3.1, null can be represented via a JSON Schema type union, such as **type: [string, "null"]**. Whether a property must be present is still decided by the object's **required** list.

Do not use nullable to represent an optional body. Likewise, do not omit requestBody.required just because a few DTO properties can be null.

## 4. RequestBody Object and Spring's `@RequestBody`

Spring MVC uses the **org.springframework.web.bind.annotation.RequestBody** annotation to read the HTTP request body and convert its content into a Java type via an HttpMessageConverter.

Example:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Spring reads the JSON from the request body, converts it to CreateProductRequest, and passes it to the controller method. Springdoc inspects the method signature, DTO type, and mapping to generate the Request Body Object in OpenAPI.

There are two similarly named annotations with different roles:

| Annotation | Package | Role |
|---|---|---|
| Spring **@RequestBody** | org.springframework.web.bind.annotation | Binds HTTP body content to a Java parameter |
| OpenAPI **@RequestBody** | io.swagger.v3.oas.annotations.parameters | Adds metadata for the Request Body Object |

The Spring annotation controls runtime behavior. The OpenAPI annotation describes the contract. Both can be used on the same parameter when detailed documentation is needed.

To avoid import confusion, you can write the fully qualified name of the OpenAPI annotation as in this example:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @Valid
    @org.springframework.web.bind.annotation.RequestBody
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Information required to create a product",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
    CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Explicit OpenAPI declarations are helpful when you need to specify description, media type, schema, or required. If Springdoc already infers everything accurately from the controller, repeating all metadata is unnecessary.

## 5. How Spring `@RequestBody` handles `required`

The Spring annotation has a **required** attribute. By default, Spring MVC's **@RequestBody** has **required = true**, meaning the request must contain body content for binding to succeed.

Example:

~~~java
@PostMapping("/api/comments")
public CommentResponse createComment(
    @RequestBody(required = false) CreateCommentRequest request
) {
    if (request == null) {
        return commentService.createDefault();
    }

    return commentService.create(request);
}
~~~

In this case, the application allows requests without a body. When no body is provided, Spring can pass null into the parameter, and the controller must handle that case safely. The corresponding OpenAPI contract should reflect **requestBody.required: false**.

If the body is required, you can keep the default or declare it explicitly:

~~~java
@RequestBody(required = true) CreateProductRequest request
~~~

Do not change only **@io.swagger.v3.oas.annotations.parameters.RequestBody(required = false)** to make the docs claim the body is optional while Spring still requires a body. In that situation, Swagger UI might allow submitting an empty body while the application still returns a runtime error.

Conversely, if Spring allows omitting the body but OpenAPI states required true, clients may misunderstand the contract and always send unnecessary data. Keep both metadata layers synchronized.

## 6. Describing the request body schema

The schema defines the data structure that the client must send. In Spring Boot, Springdoc typically infers the schema from the DTO and related annotations.

Example DTO:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(
        description = "Product name",
        example = "Mechanical keyboard"
    )
    String name,

    @NotNull
    @Positive
    @Schema(
        description = "Selling price in VND",
        example = "1290000"
    )
    BigDecimal price,

    @Schema(
        description = "Category ID",
        example = "12"
    )
    Long categoryId
) {}
~~~

Controller:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @Valid
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc can use Java types, **@Schema** annotations, and certain Bean Validation constraints to build the schema under components.schemas. When clients open Swagger UI, they can view the JSON structure, examples, and fields to enter.

Distinguish the sources of information:

- Java types define the structure and data types being bound.
- Bean Validation annotations such as **@NotBlank** and **@Positive** validate data on the backend when validation is enabled.
- **@Schema** adds descriptions, examples, formats, and documentation metadata.
- **@Valid** activates validation for the request object per Spring's configuration.

Documentation is only accurate when published constraints match actual validation. For instance, if OpenAPI marks price as required but the backend does not validate it or allows it to be missing, the two contracts diverge.

## 7. Declaring multiple media types in `content`

The **content** property of the Request Body Object is a map. Each key is a media type; the corresponding value is a Media Type Object, which can contain schema, examples, and encoding.

An endpoint can accept multiple formats:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateProductXml'
~~~

The client selects a format using the **Content-Type** HTTP header. For example, to send JSON, the request needs:

~~~http
Content-Type: application/json
~~~

To send XML:

~~~http
Content-Type: application/xml
~~~

The server must actually have a corresponding HttpMessageConverter or handling mechanism. Merely adding a media type to OpenAPI does not make Spring Boot automatically support parsing that format.

In Spring MVC, the mapping can advertise accepted media types via the **consumes** attribute:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc can use the mapping information and parameter type to generate documentation content. Inspect the OpenAPI JSON to confirm each media type has an appropriate schema. The **produces** attribute describes response media types; do not use it in place of request consumes.

## 8. Adding descriptions and request examples

A schema with accurate data types can still be hard to use without examples. The Request Body Object can contain a description; each Media Type Object can contain **example** or **examples**.

YAML example:

~~~yaml
requestBody:
  description: Product details to create. Price is in VND.
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
      examples:
        validProduct:
          summary: Valid product
          value:
            name: Mechanical keyboard
            price: 1290000
            categoryId: 12
~~~

Examples can also be declared via annotations:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Product details to create",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateProductRequest.class),
        examples = @ExampleObject(
            name = "validProduct",
            summary = "Valid product",
            value = """
                {
                  "name": "Mechanical keyboard",
                  "price": 1290000,
                  "categoryId": 12
                }
                """
        )
    )
)
~~~

The annotation snippet above supplements a controller parameter that has Spring's **@RequestBody**. The example value must be valid JSON and conform to the schema. If the DTO has required fields, the example should supply all of them; if there are enums, formats, or limits, the example should use valid values.

Use examples representative of common scenarios. Never put real tokens, personal data, or production information in documentation examples.

## 9. Request bodies with multipart and file uploads

When a client uploads a file alongside metadata, the request usually uses the **multipart/form-data** media type. Each part of the multipart message can have its own content type.

Example controller:

~~~java
@PostMapping(
    path = "/api/products/import",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ImportResult importProduct(
    @RequestPart("metadata") @Valid CreateProductRequest metadata,
    @RequestPart("file") MultipartFile file
) {
    return productService.importProduct(metadata, file);
}
~~~

A corresponding OpenAPI representation can look like:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - metadata
          - file
        properties:
          metadata:
            $ref: '#/components/schemas/CreateProductRequest'
          file:
            type: string
            format: binary
~~~

The file schema example above uses the representation common in OpenAPI 3.0 documents. If your project outputs OpenAPI 3.1, verify the schema against the JSON Schema dialect the document uses and check the output Springdoc generates before standardizing the contract.

Here, **metadata** is a data object; **file** is binary content. If you need to specify a content type or headers for individual parts, the Media Type Object can use the **encoding** property.

Springdoc usually infers part of the schema from **@RequestPart**, the DTO, and **MultipartFile**. However, inspect the OpenAPI JSON to confirm part names, requiredness, and binary format. Do not rely solely on Swagger UI displaying a file picker button.

## 10. Reusing Request Bodies via `components`

If multiple operations accept the same request structure, OpenAPI allows defining a shared Request Body Object under **components.requestBodies** and referencing it with **$ref**.

Example:

~~~yaml
components:
  requestBodies:
    CreateProductBody:
      description: Product details to create
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'

paths:
  /api/products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        "201":
          description: Product created

  /api/products/import-preview:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        "200":
          description: Data validated
~~~

Reuse avoids duplicating schemas and descriptions. However, share a definition only when both endpoints genuinely share the exact same contract. If one endpoint requires an extra field, has different required rules, or accepts different media types, define a separate Request Body Object so the documentation remains accurate.

Springdoc can generate shared schemas under **components.schemas** when multiple DTOs or types are referenced. Creating shared Request Body Objects typically requires appropriate OpenAPI configuration or model customization; do not assume every repeated DTO will automatically be extracted into components.requestBodies.

## 11. When a request has no body

Not every operation needs a Request Body Object. For example, GET requests for looking up resources typically pass criteria via path or query parameters and do not need a body. DELETE normally does not need a body either unless the contract explicitly defines a dedicated payload.

HTTP has cases where bodies are permitted with various methods, but clients, proxies, and frameworks do not always handle them consistently. For GET, prefer query parameters for search criteria to maximize compatibility.

If an endpoint does not accept a body, omit **requestBody** in OpenAPI. If an endpoint accepts a body optionally, declare a Request Body Object with **required: false** and clearly describe the behavior when the body is absent.

Do not confuse a response with no body with an optional request body. A 204 No Content response describes what the server returns; it does not determine whether the client must send a request body.

## 12. Verifying `required` and `content` in generated docs

After declaring the controller and annotations, fetch the OpenAPI document:

~~~http
GET /v3/api-docs
~~~

Locate the operation and check:

- A requestBody field is present when the endpoint actually accepts a body.
- requestBody.required matches **@RequestBody(required = ...)** and runtime behavior.
- content contains the exact media types accepted by the endpoint.
- The schema references the right DTO or data structure.
- Required properties within the schema are accurately described.
- Examples are valid data conforming to the schema.
- Multipart parts have the right names, types, and requiredness.
- No request body is declared for endpoints that do not accept a body.

Some common issues:

| Symptom | Cause to check |
|---|---|
| Swagger UI does not display request body | Controller is missing Spring @RequestBody, mapping, or annotation is not recognized by Springdoc |
| Body is marked with wrong required flag | Spring and OpenAPI annotation required values are inconsistent |
| Missing schema or overly generic schema | DTO is not inferred as expected or @Schema(implementation = ...) is missing |
| Wrong media type | consumes, content type, and HttpMessageConverter configuration do not match |
| Optional body yet server still returns error | Spring @RequestBody is still required or controller does not handle null |
| Required body yet schema allows empty object | requestBody.required is correct but schema lacks a required property list |
| File upload lacks file picker button | Multipart schema does not describe the file property as string/binary or part name mismatches |

Verifying the OpenAPI document should go hand in hand with integration tests sending real requests. Test requests with a valid body, missing body, wrong Content-Type, missing required fields, and mistyped payloads. Resulting status codes and error responses must match the published contract.

## 13. Design principles for Request Body Objects

When using Springdoc OpenAPI to describe request bodies, follow these rules:

1. Use Spring @RequestBody to bind HTTP body content to Java parameters.
2. Use the Request Body Object to describe content, media types, schema, description, and required.
3. Synchronize OpenAPI's required flag with Spring's runtime behavior.
4. Distinguish body required from required properties inside the schema.
5. Distinguish absent data from data with a null value.
6. Use consumes and HttpMessageConverters matching the published media types.
7. Use @Schema, Bean Validation, and examples to describe structure, constraints, and sample data.
8. Use multipart/form-data and binary schemas for file uploads.
9. Reuse Request Body Objects only when endpoints share the exact same actual contract.
10. Verify OpenAPI JSON/YAML alongside runtime requests after every change.

The Request Body Object tells clients exactly what data to send, in what format, and whether the body can be omitted. When the required flag, schema, and Spring binding align, Swagger UI renders accurate forms and clients have a reliable basis for API integration.

