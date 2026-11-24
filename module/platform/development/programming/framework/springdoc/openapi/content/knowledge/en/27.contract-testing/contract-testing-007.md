# Validating Examples Against Their Target Schemas

Request and response examples are only useful when their data conforms to the schema of the right operation and media type. An example can be valid JSON yet still violate the contract: missing a required property, using a non-existent enum value, using the wrong date/time format, exceeding numeric bounds, or placing a response-only field into a request body.

With Spring Boot and springdoc-openapi, verify two separate things:

1. Examples sit at the right location in the OpenAPI document and attach to the right schema, parameter, response, and media type.
2. Example values actually satisfy the schema they reference or describe.

Swagger UI rendering an example does not mean the example has been validated. Springdoc can place annotations and metadata into the OpenAPI document, yet ensuring every Example Object matches its schema requires a dedicated validator or contract test.

## 1. Which Schema Does an Example Belong To?

An OpenAPI document can hold examples at multiple levels. Before validating data, identify what kind of value the example describes:

| Location | What the Example Describes | Schema to Validate Against |
|---|---|---|
| Schema Object | Sample value for a model or property | The schema at that exact location |
| Parameter Object | Value of a path, query, header, or cookie parameter | The parameter's schema and serialization rules |
| Request Body / Media Type Object | Body sent by the client | The schema under that exact media type |
| Response / Media Type Object | Body returned by the server for a status | The response's schema and media type |
| Header Object | Header value sent or returned | The header's schema |
| Components / Examples | Example reused across multiple operations | The schema at each reference site |

For instance, `Product` may appear in both requests and responses, yet not every case uses the same shape. A request may require `name` and `price`, while a response adds server-generated `id`, `createdAt`, and status fields. Validating a response example against a request schema will fail even though both talk about `Product`.

An example must be identified with full context: operation, data direction (request/response), status code, media type, and schema. Never just pick a similarly named schema and apply it to every example.

## 2. Distinguishing `example` in Schema Object vs. `examples` in Media Type Object

OpenAPI has two places commonly used to declare examples:

- A Schema Object can hold an example for that schema's data value.
- A Media Type Object can hold a single `example` or `examples` as a map of Example Objects.

Schema example:

~~~yaml
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
          minLength: 1
          maxLength: 80
          example: Ballpoint pen
        price:
          type: number
          exclusiveMinimum: 0
          example: 12500
~~~

Media type examples:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
      examples:
        standard:
          summary: Standard product
          value:
            name: Ballpoint pen
            price: 12500
        premium:
          summary: Higher-priced product
          value:
            name: Fountain pen
            price: 250000
~~~

A schema example typically illustrates a single value or property. Media type `examples` express full representations sent or received, each with its own name, summary, and description. When multiple real-world scenarios exist, use `examples` on the Media Type Object to distinguish each case.

Within the same Media Type Object, `example` and `examples` are mutually exclusive. Never declare both at the same location. When a media type declares `example` or `examples`, it overrides any example placed inside the schema for representation display.

## 3. Differences Between OpenAPI 3.0 and 3.1

When validating examples, know which OpenAPI version the document uses:

| Aspect | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Schema Object | Based on an OpenAPI-defined JSON Schema subset | Based on JSON Schema Draft 2020-12 and the OpenAPI vocabulary |
| Schema examples | Uses singular `example` keyword | Supports JSON Schema `examples`; singular `example` remains for compatibility |
| Nullable | Uses `nullable` keyword | Uses JSON Schema type union, e.g. `type: [string, "null"]` |
| Boolean schemas | More restricted | Usable per JSON Schema |
| Validator | Must support OpenAPI 3.0 schema dialect | Must support JSON Schema 2020-12 and OpenAPI dialect/keywords |

Do not run a default JSON Schema Draft 2020-12 validator blindly against OpenAPI 3.0 schemas. Conversely, do not ignore JSON Schema 2020-12 semantics when the document is OpenAPI 3.1.

The `examples` property inside an OpenAPI 3.1 Schema Object is a JSON Schema array. The `examples` field on a Media Type Object is a map of Example Objects keyed by example name. Both share the same name yet live at different levels with different semantics.

## 4. Example Objects with `value` or `externalValue`

An Example Object supports metadata and a data source:

| Field | Meaning |
|---|---|
| `summary` | Short title for the example |
| `description` | Explanation of context and usage |
| `value` | Example payload embedded in the OpenAPI document |
| `externalValue` | URI pointing to external example content |

`value` and `externalValue` are mutually exclusive. Use `value` for small, readable JSON that can be reviewed alongside code. Use `externalValue` when payloads are large, binary files, or hard to embed directly in YAML/JSON.

Embedded example:

~~~yaml
examples:
  validProduct:
    summary: Valid product
    description: Minimal body to create a product.
    value:
      name: Ballpoint pen
      price: 12500
      category: STATIONERY
~~~

External example:

~~~yaml
examples:
  productImportCsv:
    summary: CSV file for importing products
    externalValue: https://docs.example.com/examples/products-import.csv
~~~

When using `externalValue`, verify the URL is reachable in the documentation consumer's environment, its content is versioned, and the actual file matches the declared media type/schema. The OpenAPI document stores only the link; validators do not necessarily fetch and check external files.

## 5. Adding Request Examples with Springdoc Annotations

Springdoc reads Swagger annotations to build the OpenAPI document. For request bodies, use `@Content` and `@ExampleObject`:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Create a new product",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Information required to create a product.",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class),
            examples = {
                @ExampleObject(
                    name = "stationery",
                    summary = "Stationery product",
                    value = """
                        {
                          "name": "Ballpoint pen",
                          "price": 12500,
                          "category": "STATIONERY"
                        }
                        """
                ),
                @ExampleObject(
                    name = "notebook",
                    summary = "Notebook",
                    value = """
                        {
                          "name": "A5 Notebook",
                          "price": 32000,
                          "category": "NOTEBOOK"
                        }
                        """
                )
            }
        )
    )
)
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.created(
        URI.create("/api/products/" + created.id())
    ).body(created);
}
~~~

Note there are two annotations named `RequestBody`:

- `org.springframework.web.bind.annotation.RequestBody` on the controller parameter so Spring MVC reads the body.
- `io.swagger.v3.oas.annotations.parameters.RequestBody` describing the request body in OpenAPI.

In this example, the Swagger annotation is written with its full package name to avoid import confusion. When used via `@Operation.requestBody`, it defines documentation content and examples without changing how the controller reads requests.

Every `ExampleObject` must have a unique `name` within its `examples` map, a clear `summary`, and valid JSON in `value`. Avoid improperly escaped JSON strings or wrapping an entire object as a JSON string when the media type is `application/json` and the goal is an object example.

These Java snippets use text blocks for readability, requiring Java 15 or newer. For older Java versions, replace text blocks with properly escaped JSON strings or load examples from fixture files.

## 6. Adding Response Examples per Status Code

Response examples must match their corresponding response schemas—never reuse a success example for an error response:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class),
            examples = @ExampleObject(
                name = "createdProduct",
                summary = "Newly created product",
                value = """
                    {
                      "id": "7c1e2b3a-4d5f-6789-8abc-def012345678",
                      "name": "Ballpoint pen",
                      "price": 12500,
                      "category": "STATIONERY",
                      "createdAt": "2026-11-20T09:30:00Z"
                    }
                    """
            )
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ValidationProblem.class),
            examples = @ExampleObject(
                name = "invalidPrice",
                summary = "Invalid product price",
                value = """
                    {
                      "type": "https://api.example.com/problems/validation-error",
                      "title": "Request validation failed",
                      "status": 400,
                      "detail": "Price must be greater than zero.",
                      "errors": [
                        {
                          "field": "price",
                          "code": "Positive",
                          "message": "Price must be greater than zero."
                        }
                      ]
                    }
                    """
            )
        )
    )
})
~~~

The `201` example must satisfy `ProductResponse`; the `400` example must satisfy `ValidationProblem`. Never validate the `400` example against `ProductResponse` simply because both examples appear on the same operation.

If a `204` response has no body, do not attach a JSON example to it. If a response includes `Location`, `ETag`, or `Retry-After` headers, document and provide examples on the corresponding Header Object.

## 7. Examples for Path, Query, and Header Parameters

Parameter examples must match the schema and how values serialize on the HTTP request. Query parameter example:

~~~java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(
        name = "status",
        description = "Product status to filter by.",
        examples = {
            @ExampleObject(name = "active", value = "ACTIVE"),
            @ExampleObject(name = "archived", value = "ARCHIVED")
        }
    )
    @RequestParam(required = false) ProductStatus status
) {
    return productService.search(status);
}
~~~

Corresponding request URL example:

~~~http
GET /api/products?status=ACTIVE
Accept: application/json
~~~

For parameter objects, examples represent parameter values as they appear on the wire. If a parameter is an array using `form`, `pipeDelimited`, or `spaceDelimited`, verify the example serializes according to `style`/`explode`. A JSON array like `["ACTIVE","ARCHIVED"]` is not necessarily a valid wire example for a query parameter.

For header parameters, example values must follow valid header syntax. For path parameters, check special-character encoding and published formats.

## 8. Multipart and Form-Data Examples

Multipart examples must match both the overall schema and each part's encoding. Never use a plain JSON object as a multipart example if clients must actually send separate parts.

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
            $ref: '#/components/schemas/ProductImportMetadata'
          file:
            type: string
            format: binary
      encoding:
        metadata:
          contentType: application/json
        file:
          contentType: text/csv
      examples:
        importProducts:
          summary: Metadata for a CSV file
          value:
            metadata:
              category: STATIONERY
              replaceExisting: false
            file: products.csv
~~~

In a multipart example, the `file` value inside the Example Object merely illustrates a filename; the actual payload is a binary/text part sent inside a multipart boundary. To specify exact CSV contents, supply an `externalValue` file or dedicated example docs and describe each part's encoding and content type.

With `application/x-www-form-urlencoded`, each property serializes into a form field. Verify final string types, array serialization, Unicode characters, and percent-encoding. A nested JSON object does not automatically serialize into a form field identically across all clients.

## 9. Checking Examples Against Schema Constraints

When reviewing an example, check these constraint groups:

| Schema Constraint | What to Check in the Example |
|---|---|
| `type` | JSON value matches `string`, `number`, `integer`, `boolean`, `object`, or `array` |
| `required` | All required properties are present |
| `enum` / `const` | Value is in the allowed set or equals the constant |
| `format` | Dates/times, UUIDs, emails, URIs match the format |
| `minLength` / `maxLength` | Strings stay within length bounds |
| `pattern` | Strings match the regular expression |
| `minimum` / `maximum` | Numbers stay within bounds |
| `exclusiveMinimum` / `exclusiveMaximum` | Value does not hit excluded bounds |
| `multipleOf` | Number is a valid multiple |
| `minItems` / `maxItems` | Array item count is within bounds |
| `uniqueItems` | Array contains no duplicates when required |
| `items` | Every element satisfies the item schema |
| `properties` | Each property matches its type and constraints |
| `additionalProperties` | Whether unlisted fields are permitted |
| `oneOf` / `anyOf` / `allOf` | Value satisfies the required schema composition |
| `discriminator` | Discriminator value matches the sub-schema |

Merely checking that JSON parses is not enough. The following example parses as valid JSON yet violates the schema if `price` must exceed `0` and `category` only accepts published enum values:

~~~json
{
  "name": "Ballpoint pen",
  "price": -10,
  "category": "UNKNOWN"
}
~~~

Examples can also fail due to missing required fields, malformed `date-time` strings, forbidden extra properties, or confusing `number` vs. `integer`. Catch these before publishing examples in documentation.

## 10. Validating Schemas with `$ref` and Reused Schemas

OpenAPI frequently defines schemas in `components` and references them via `$ref`. Examples must be validated against the resolved schema, not just the object holding `$ref`.

~~~yaml
components:
  schemas:
    ProductCode:
      type: string
      pattern: '^[A-Z]{3}-[0-9]{4}$'
      example: PEN-1024
    CreateProductRequest:
      type: object
      required:
        - productCode
        - name
      properties:
        productCode:
          $ref: '#/components/schemas/ProductCode'
        name:
          type: string
          minLength: 1
          maxLength: 80

paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
            examples:
              valid:
                value:
                  productCode: PEN-1024
                  name: Ballpoint pen
~~~

The `valid` example satisfies `ProductCode` because the string matches the regex pattern. Values like `PEN-1` or `pen-1024` are invalid even though they are strings. If a validator fails to resolve local references, it may skip `ProductCode`'s constraints or throw an unresolved reference error; that is a test configuration bug, not proof the example is valid.

When using external references, pin schema sources and versions so tests remain reproducible. Never let CI fetch schemas arbitrarily from a mutable URL.

## 11. Validating `oneOf`, `anyOf`, `allOf`, and `discriminator`

Composed schemas commonly appear when an API supports multiple resource or payload variants. Examples must match the proper branch:

- `allOf`: value must satisfy all combined schemas.
- `anyOf`: value must satisfy at least one schema.
- `oneOf`: value must satisfy exactly one schema in the set.
- `discriminator`: selects the sub-schema by discriminator property; it does not waive the sub-schema's constraints.

Example:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
      discriminator:
        propertyName: method
        mapping:
          CARD: '#/components/schemas/CardPayment'
          BANK_TRANSFER: '#/components/schemas/BankTransfer'

    CardPayment:
      type: object
      required: [method, last4]
      properties:
        method:
          type: string
          enum: [CARD]
        last4:
          type: string
          pattern: '^[0-9]{4}$'

    BankTransfer:
      type: object
      required: [method, bankCode, accountNumber]
      properties:
        method:
          type: string
          enum: [BANK_TRANSFER]
        bankCode:
          type: string
        accountNumber:
          type: string
~~~

Valid card example:

~~~yaml
value:
  method: CARD
  last4: '1234'
~~~

Valid bank transfer example:

~~~yaml
value:
  method: BANK_TRANSFER
  bankCode: VCB
  accountNumber: '0123456789'
~~~

An example with `method: CARD` that includes `bankCode` and omits `last4` fails `CardPayment`. If sub-schemas permit additional properties, adding `bankCode` might not fail the card branch on its own; to reject extraneous fields, set `additionalProperties: false` or `unevaluatedProperties` according to your dialect.

With `oneOf`, an example accidentally matching two branches is invalid because `oneOf` demands exactly one match. With `anyOf`, matching multiple branches remains valid. This is an important distinction when validating polymorphic DTO examples.

## 12. Request and Response Examples with `readOnly`/`writeOnly`

OpenAPI supports `readOnly` and `writeOnly` to mark read-only or write-only properties:

- `readOnly`: property belongs to responses; clients do not send it in requests.
- `writeOnly`: property belongs to requests; the server does not return it in responses.

The `Product` schema below uses OpenAPI 3.1's numeric `exclusiveMinimum` syntax. For OpenAPI 3.0 documents, express the same bound with `minimum: 0` and `exclusiveMinimum: true`.

Example:

~~~yaml
components:
  schemas:
    Product:
      type: object
      required: [name, price]
      properties:
        id:
          type: string
          format: uuid
          readOnly: true
        name:
          type: string
          minLength: 1
        price:
          type: number
          exclusiveMinimum: 0
        internalNote:
          type: string
          writeOnly: true
~~~

Request example:

~~~yaml
name: Ballpoint pen
price: 12500
internalNote: Item requires seal inspection
~~~

Response example:

~~~yaml
id: 7c1e2b3a-4d5f-6789-8abc-def012345678
name: Ballpoint pen
price: 12500
~~~

Never put `id` in a request example when the contract marks `id` as `readOnly`. Never put `internalNote` in a response example when marked `writeOnly`. When sharing a single schema for requests and responses, check whether your validator understands message direction; many pure JSON Schema validators do not apply OpenAPI's request/response semantics automatically.

For critical APIs, separate request and response DTOs make examples and schemas clearer while preventing accidental exposure of internal fields.

## 13. Using Reusable Examples in `components`

When multiple operations share an example, place the Example Object under `components/examples` and reference it with `$ref`:

~~~yaml
components:
  examples:
    standardProduct:
      summary: Standard stationery product
      description: Example used in create and update product.
      value:
        name: Ballpoint pen
        price: 12500
        category: STATIONERY

paths:
  /api/products:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
            examples:
              standard:
                $ref: '#/components/examples/standardProduct'
~~~

Reusing examples cuts down copy/paste yet introduces coupling: if one operation's schema changes, the shared example may no longer be valid for that operation. An Example Object referenced from multiple sites must remain compatible with every target schema or be split into specialized examples.

Name examples after the scenario or intent, such as `standardProduct`, `invalidPrice`, or `archivedProduct`. Avoid generic names like `example1` or `data2` that make it hard to tell which case an example represents during review.

## 14. Error Response Examples Must Also Match Error Schemas

Success examples are not the only ones needing validation. Error examples must match error schemas and reflect accurate status codes and media types:

~~~yaml
components:
  schemas:
    ValidationProblem:
      type: object
      required: [type, title, status, errors]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
          enum: [400]
        detail:
          type: string
        errors:
          type: array
          items:
            $ref: '#/components/schemas/FieldViolation'
    FieldViolation:
      type: object
      required: [field, code, message]
      properties:
        field:
          type: string
        code:
          type: string
        message:
          type: string

paths:
  /api/products:
    post:
      responses:
        '400':
          description: Request validation failed
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ValidationProblem'
              examples:
                invalidPrice:
                  value:
                    type: https://api.example.com/problems/validation-error
                    title: Request validation failed
                    status: 400
                    detail: Price must be greater than zero.
                    errors:
                      - field: price
                        code: Positive
                        message: Price must be greater than zero.
~~~

Here, `status` inside the body is integer `400` and the response status is `'400'`. They operate at two layers yet must stay consistent. If the error schema lacks `errors` or types `status` as a string, the example will mismatch.

Under RFC 9457, standard members are `type`, `title`, `status`, `detail`, and `instance`; extension members such as `errors` must be defined by the API. When using `application/problem+json`, examples must be valid Problem Details JSON rather than arbitrary error objects lacking media type documentation.

## 15. Annotation Examples Do Not Replace Runtime Tests

`@ExampleObject` is metadata for the OpenAPI document. It does not send requests, execute Bean Validation, or prove the controller can handle payloads.

To verify examples against Java DTOs, deserialize and run Jakarta Bean Validation:

~~~java
class ProductExampleTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void productRequestExamplePassesBeanValidation() throws Exception {
        String example = """
            {
              "name": "Ballpoint pen",
              "price": 12500,
              "category": "STATIONERY"
            }
            """;

        CreateProductRequest request =
            objectMapper.readValue(example, CreateProductRequest.class);

        Set<ConstraintViolation<CreateProductRequest>> violations =
            validator.validate(request);

        assertThat(violations).isEmpty();
    }
}
~~~

This test checks the example against Jackson and Bean Validation on the Java DTO. It helps catch annotation mistakes or unparseable examples, yet does not prove the example matches the full OpenAPI Schema Object. Schemas can include constraints such as `oneOf`, `discriminator`, `additionalProperties`, or format assertions not fully represented by Bean Validation.

If your DTO uses custom Jackson modules, naming strategies, or deserializers, configure the test with the exact `ObjectMapper` used by the application. A fresh default `ObjectMapper` can deserialize differently from runtime, especially for Java Time, enums, polymorphism, and custom serializers.

## 16. Automated Validation of Example Values with JSON Schema

To verify data against schemas, use a JSON Schema validator supporting the dialect matching your OpenAPI document. One Java option is NetworkNT JSON Schema Validator, which supports JSON Schema Draft 2020-12 as well as OpenAPI 3.0/3.1 dialects.

Validation workflow:

1. Parse the OpenAPI document.
2. Locate each operation and media type.
3. Extract the request body or response schema.
4. Resolve local/external `$ref` entries from controlled sources.
5. Extract each `example.value` or payload from `externalValue`.
6. Select the validator/dialect matching the `openapi` version and schema dialect.
7. Validate the example instance.
8. Report failures with operation, direction, status code, media type, example name, and JSON path.

For example, the validator receives the `CreateProductRequest` schema and the `standard` example. If required `name` is missing or `price` is negative, the test must flag the example as invalid.

For a standalone JSON Schema Draft 2020-12 schema with no external references, a minimal check looks like:

~~~java
SchemaRegistry registry = SchemaRegistry.withDefaultDialect(
    SpecificationVersion.DRAFT_2020_12
);
Schema schema = registry.getSchema(schemaJson);

List<Error> errors = schema.validate(
    exampleJson,
    InputFormat.JSON,
    executionContext -> executionContext.executionConfig(
        config -> config.formatAssertionsEnabled(true)
    )
);

assertThat(errors).isEmpty();
~~~

This snippet illustrates a standalone JSON schema. When extracting schemas from OpenAPI, configure `SchemaRegistry` with the matching OpenAPI dialect, resolve references prior to validation, and apply `readOnly`/`writeOnly` rules per message direction. Never substitute plain Draft 2020-12 for OAS 3.0 or OAS 3.1 dialects.

### Notes on Using a JSON Schema Validator

- Never feed the whole OpenAPI document into the validator as if the entire document were a JSON Schema. Validate only the schema at the target node.
- Always resolve `$ref` and preserve the base URI so relative references work.
- For OpenAPI 3.0, use a dialect/adapter that understands `nullable` and OAS 3.0 differences.
- For OpenAPI 3.1, use JSON Schema 2020-12 with the appropriate OpenAPI dialect/vocabulary.
- Check whether format assertions are enabled; some validators only annotate formats by default instead of rejecting invalid values.
- Handle `readOnly`/`writeOnly` per request/response direction. Pure JSON Schema validators may be unaware of HTTP message direction.
- Fetch `externalValue` only from controlled sources and validate against media type; never fetch arbitrary URLs from untrusted documents.

Do not treat validator output as infallible if the validator lacks support for a specific keyword or dialect. Document limitations and validate with tools aligned with your project's OpenAPI version.

## 17. Verifying Examples Emitted by Springdoc

After adding annotations, call `/v3/api-docs` and assert that examples appear in the right locations. MockMvc example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiExamplesTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesRequestExamplesForJsonMediaType() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].schema.$ref"
            ).value("#/components/schemas/CreateProductRequest"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].examples.stationery.summary"
            ).value("Stationery product"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].post.requestBody.content['application/json'].examples.stationery.value.name"
            ).value("Ballpoint pen"));
    }
}
~~~

Response example:

~~~java
@Test
void publishesErrorExampleUnderItsOwnStatusAndMediaType() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['400'].content['application/problem+json'].examples.invalidPrice.value.status"
        ).value(400))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['201'].content['application/json'].examples.createdProduct.value.id"
        ).exists());
}
~~~

These JSONPaths assume example names `stationery`, `invalidPrice`, and `createdProduct` as annotated. If springdoc or swagger-core versions change how annotation values serialize to JSON nodes, inspect raw `/v3/api-docs` and adjust assertions to match the generated document. Never skip the test simply because Swagger UI displays an example; verify both the schema and example live under the intended media type and status.

## 18. Checking Examples Against Runtime Responses

An example in OpenAPI is illustrative documentation, not necessarily a fixed server response. Still, when an example illustrates a concrete response the API promises to return, add a corresponding runtime test:

~~~java
@Test
void createProductResponseHasTheDocumentedShape() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Ballpoint pen",
                  "price": 12500,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isCreated())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.name").value("Ballpoint pen"))
        .andExpect(jsonPath("$.price").value(12500))
        .andExpect(jsonPath("$.category").value("STATIONERY"))
        .andExpect(jsonPath("$.createdAt").isNotEmpty());
}
~~~

`id` and `createdAt` are generated at runtime, so they do not need to match fixed literal strings from the example. The test checks field types and presence. When an example illustrates a deterministic fixture or sandbox response, you can assert exact values.

For error responses, send a controlled failing request and inspect the error body. Never assume error examples are returned verbatim by exception handlers; they may simply illustrate one instance. What must hold is that live responses satisfy the same schema and semantics.

## 19. Validating Examples Against Schemas with an Independent Validator

An automated workflow should traverse every example in the document:

~~~text
OpenAPI document
       |
       v
Find operations and parameters
       |
       v
Find request/response media types
       |
       v
Resolve schema references
       |
       v
Read inline examples or controlled external examples
       |
       v
Validate each example against its schema
       |
       +---- invalid ----> report operation, media type, example, JSON path
       |
       +---- valid ------> continue
       |
       v
Run runtime contract tests
~~~

Details to include in error reports:

- HTTP method and path.
- Request or response; if response, include status code.
- Media type.
- Example name.
- Resolved schema.
- JSON path of the invalid node.
- Violated constraint and relevant value if safe to print.

Example actionable report: `POST /api/products, request, application/json, example premium, path $.price, violates exclusiveMinimum.` This format points documentation authors directly to the broken example instead of forcing them to dig through full validator stack traces.

Never validate all examples against a single shared schema. Extract each example from its exact OpenAPI site and check it against that site's schema. Never validate a `409` response example against a `201` response schema.

## 20. Checking External Examples and Sensitive Examples

External examples introduce several risks:

- `externalValue` URLs can break or return altered contents over time.
- Files may drift out of alignment with their declared media type.
- Sample data may contain real personal information or live secrets.
- Untrusted URLs can trick CI into fetching unintended data.

For `externalValue`:

1. Store example files in versioned repositories or artifacts.
2. Pin URLs or checksums when files live outside the repository.
3. Fetch only from allowlisted hosts in the pipeline.
4. Check HTTP status, content type, and size before parsing.
5. Validate contents against the corresponding schema.
6. Never include real credentials, tokens, cookies, emails/phone numbers, or customer data in examples.

When an example shows an API key or bearer token, use a clearly marked placeholder value. Never embed an expired production token in documentation examples.

## 21. Common Pitfalls When Validating Examples

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Swagger UI renders example yet type is wrong | `ExampleObject.value` mismatches schema | Validate `value` against the media type's schema |
| Request example contains server-generated `id` | Reused response example in request schema | Author a dedicated request example |
| Response example misses required fields | Copied request payload as response | Check against the response schema for that status |
| Example is valid JSON yet wrong enum | Only parsed JSON without schema validation | Validate `enum`/`const` and `discriminator` |
| Date/time example rejected | Wrong format or format assertions disabled | Use proper RFC 3339 format and enable format assertions |
| Parameter example looks like a JSON object | Ignored `style`/`explode` or serialization | Check the final wire representation |
| `example` and `examples` both declared | Used two mutually exclusive fields together | Pick one approach on the Media Type Object |
| Schema example overridden by media type example | Examples set at both levels | Decide which level owns the displayed example |
| `$ref` not resolved by validator | Missing base URI or reference loader | Configure resolver and pin schema sources |
| `oneOf` matches multiple branches | Sub-schemas overlap | Tighten discriminators/constraints or use `anyOf` if intended |
| Multipart example fails in clients | Used a JSON object instead of per-part payloads | Document each part's encoding and content type |
| Runtime accepts request yet example test fails | OpenAPI schema is stricter than Bean Validation | Decide canonical contract and align validation |
| `ExampleObject` `value` renders as a string | Media type or annotation value parsed unexpectedly | Inspect `/v3/api-docs` and format `value` appropriately |
| External example fails to download | Private URL, wrong path, or moved file | Place files in versioned storage and check links |

## 22. Pre-Merge Review Process for Examples

For each added or updated example, perform these checks:

1. Determine whether the example belongs to a request, response, parameter, or header.
2. Identify the exact operation, status code, and media type.
3. Locate the inline schema or resolve all `$ref` pointers.
4. Check `required`, `type`, `format`, `enum`, bounds, `pattern`, and composition.
5. Verify `readOnly`/`writeOnly` per request/response direction.
6. Verify serialization for path/query/header parameters and encoding for multipart/form.
7. Parse JSON/YAML or load `externalValue` from controlled sources.
8. Run a JSON Schema validator configured with the matching dialect.
9. Confirm springdoc emits the example at the intended path in `/v3/api-docs`.
10. Run runtime tests if the example represents executable request/response behavior.
11. Confirm the example contains no sensitive data or real credentials.
12. Review the OpenAPI diff to ensure schemas or sibling examples were not accidentally altered.

If an example cannot be validated automatically due to an external format or custom media type, document the manual verification steps and retain reproducible fixtures. Never silently suppress validator failures.

## 23. References

- [OpenAPI Specification 3.1.2 – Media Type Object](https://spec.openapis.org/oas/v3.1.html#media-type-object): schema, `example`/`examples`, media types, and override rules.
- [OpenAPI Specification 3.1.2 – Example Object](https://spec.openapis.org/oas/v3.1.html#example-object): `summary`, `description`, `value`, and `externalValue`.
- [OpenAPI Specification 3.1.2 – Working with Examples](https://spec.openapis.org/oas/v3.1.html#working-with-examples): example placement and semantics.
- [Swagger Core – ExampleObject annotation](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html): declaring examples for request/response content.
- [Swagger Core – Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Parameter.html): examples for path, query, header, and cookie parameters.
- [NetworkNT JSON Schema Validator](https://github.com/networknt/json-schema-validator): JSON Schema and OpenAPI 3.0/3.1 dialect support.
- [NetworkNT JSON Schema Validator – Quick Start](https://github.com/networknt/json-schema-validator/blob/master/doc/quickstart.md): loading schemas, resolving references, and validating instances.
- [Springdoc OpenAPI](https://springdoc.org/): generating OpenAPI documents from Spring Boot and Swagger annotations.

## 24. Summary

Validating examples against their target schemas is a core part of contract testing. Every example must attach to the right schema, request/response direction, status code, and media type. Examples must satisfy schema constraints after reference resolution while accurately reflecting actual HTTP wire representations.

In a Spring Boot project, annotations publish examples into OpenAPI; `MockMvc` or `WebTestClient` verifies both the generated document and runtime behavior; Bean Validation checks DTOs against Java constraints; and JSON Schema validators verify example values against OpenAPI schemas. Combining these verification layers catches broken examples before consumers copy them into real integrations.
