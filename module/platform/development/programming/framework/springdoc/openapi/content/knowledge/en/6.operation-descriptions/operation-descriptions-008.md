# Handlers Sharing a Path with Different consumes or produces

Spring MVC allows multiple handlers to process the same path and HTTP method when mapping conditions distinguish requests, such as `consumes` or `produces`. This organization is useful when an endpoint accepts multiple payload formats or returns multiple representation types. When generating documentation with springdoc-openapi, keep an additional OpenAPI constraint in mind: each path and HTTP method pair has only one operation. Runtime handlers must therefore be reflected as one unified operation contract, with multiple media types in the request body or responses as appropriate.

## 1. Why Can Multiple Handlers Share the Same Path and HTTP Method?

Spring does not select handlers solely by URL and HTTP method. A request mapping can also include conditions such as:

- `params`: conditions on query parameters.
- `headers`: conditions on request headers.
- `consumes`: accepted media types in the request body.
- `produces`: media types the handler can produce for the response.
- Other routing conditions supported by Spring.

Thus, two methods can both map to `POST /api/imports` while accepting different payloads:

```java
@RestController
@RequestMapping("/api/imports")
class ImportController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ImportResult importJson(@RequestBody ImportJsonRequest request) {
        return importService.importJson(request);
    }

    @PostMapping(consumes = "text/csv")
    ImportResult importCsv(@RequestBody String csv) {
        return importService.importCsv(csv);
    }
}
```

Both handlers share the same path and method, yet their `consumes` conditions differ. Spring uses the request's `Content-Type` to choose the matching handler:

| Request | Selected Handler |
|---|---|
| `POST /api/imports` with `Content-Type: application/json` | `importJson` |
| `POST /api/imports` with `Content-Type: text/csv` | `importCsv` |

When mappings are clearly distinguished, Spring can register both handlers. If two mappings match on all conditions, the application may fail with a duplicate mapping error at startup. If conditions overlap and a request matches multiple handlers with equal specificity, Spring may fail to resolve a unique handler.

## 2. consumes Distinguishes Request Body Formats

`consumes` declares the media types a handler accepts. Spring compares this condition against the request's `Content-Type` header. This is a common way to separate handlers accepting JSON, XML, CSV, or multipart at the same URL.

Example of two data formats sent to one endpoint:

```http
POST /api/imports HTTP/1.1
Content-Type: application/json
Accept: application/json

{"source":"warehouse-a","items":[{"sku":"P-01","quantity":4}]}
```

```http
POST /api/imports HTTP/1.1
Content-Type: text/csv
Accept: application/json

sku,quantity
P-01,4
P-02,2
```

Corresponding mapping example:

```java
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importJson(@Valid @RequestBody ImportJsonRequest request) {
    return importService.importJson(request);
}

@PostMapping(
    consumes = "text/csv",
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importCsv(@RequestBody String csv) {
    return importService.importCsv(csv);
}
```

Here both handlers return `ImportResult` as JSON, but the request bodies have different schemas. `ImportJsonRequest` is a JSON object; CSV is structured text following column conventions. For CSV, the application needs a suitable parser to validate headers, data types, and rows. `consumes` only selects the handler by media type; it does not automatically parse or validate CSV content.

If a client sends a `Content-Type` matching no mapping, Spring typically returns `415 Unsupported Media Type`. This differs from malformed JSON: JSON with an accepted media type whose body fails deserialization leads to a request-reading error, typically `400 Bad Request`.

### One handler accepting multiple media types

If formats can be handled in the same flow with the same Java parameter model, you can declare multiple media types in one mapping:

```java
@PostMapping(
    path = "/api/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "text/csv"
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importData(@RequestBody String payload) {
    // Determine format from Content-Type and parse payload accordingly.
    return importService.importPayload(payload);
}
```

For this example to work, the application must have a converter able to read `String` for those media types and the handler must know how to interpret each format. With structurally distinct JSON DTOs and CSV strings, two separate handlers are usually clearer. Do not add a media type to `consumes` if converters or processing logic do not support it yet.

## 3. produces Distinguishes Response Representations

`produces` declares the media types a handler can generate. Spring evaluates the request's `Accept` header alongside mapping conditions to select the matching handler. This lets the same resource be returned as JSON or CSV.

Example:

```java
@RestController
@RequestMapping("/api/products")
class ProductExportController {

    @GetMapping(value = "/export", produces = MediaType.APPLICATION_JSON_VALUE)
    List<ProductResponse> exportJson() {
        return productService.findAll();
    }

    @GetMapping(value = "/export", produces = "text/csv")
    ResponseEntity<String> exportCsv() {
        String csv = productExportService.toCsv(productService.findAll());
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .body(csv);
    }
}
```

Clients can request each representation:

```http
GET /api/products/export HTTP/1.1
Accept: application/json
```

```http
GET /api/products/export HTTP/1.1
Accept: text/csv
```

Spring selects the corresponding handler via `produces`. Once a handler is chosen, a compatible `HttpMessageConverter` must still be able to write the return value as that media type. Writing `produces = "text/csv"` does not automatically install a CSV parser or writer. You can use a CSV library, a custom converter, or build the CSV string and return it with the exact `Content-Type`.

If a client requests `Accept: application/xml` while the endpoint only supports JSON and CSV, the server typically returns `406 Not Acceptable`. Cases where a client sends `Accept: */*` or omits `Accept` must be tested separately: multiple representations may qualify, and the final choice depends on mapping specificity and content negotiation configuration. Do not rely on Java method declaration order to select a default format.

## 4. consumes and produces Can Be Combined

A mapping can constrain both request and response formats at once. When multiple handlers share a path/method, they can be distinguished by either or both conditions:

```java
@PostMapping(
    path = "/api/conversions",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ConversionResult convertJson(@RequestBody JsonConversionRequest request) {
    return conversionService.convertJson(request);
}

@PostMapping(
    path = "/api/conversions",
    consumes = "text/csv",
    produces = "text/csv"
)
ResponseEntity<String> convertCsv(@RequestBody String csv) {
    String converted = conversionService.convertCsv(csv);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType("text/csv"))
        .body(converted);
}
```

Corresponding conditions:

| Handler | Accepted `Content-Type` | Published `Accept`/Response |
|---|---|---|
| `convertJson` | `application/json` | `application/json` |
| `convertCsv` | `text/csv` | `text/csv` |

Spring can select handlers using both sides. However, note that `consumes` evaluates the request body format while `produces` evaluates the response format. They are not interchangeable: a request sending JSON can request a CSV response if the endpoint and handlers are designed to support that combination.

## 5. Mapping Conditions Must Be Unambiguous

Multiple handlers on the same path/method are only safe when handler selection conditions are unambiguous. Consider the following cases:

| Configuration | Risk | How to Handle |
|---|---|---|
| Two handlers share path/method and the same `consumes`/`produces` | Duplicate mapping or inability to distinguish handlers | Merge logic or add meaningful distinguishing conditions |
| One handler accepts `application/json`, another accepts `application/*` | Conditions may overlap for JSON requests | Avoid broad wildcards or design more specific conditions |
| Two handlers have different `produces`, yet client sends `Accept: */*` | Both representations qualify | Define a clear default representation and test wildcards |
| `consumes` lists multiple media types but only one converter exists | Request matches mapping, yet body cannot be read | Configure converters or restrict published media types |
| `produces` lists a media type without a response-writing converter | Handler is chosen, yet response fails serialization | Add a converter or use an appropriate return type |
| Mappings differ by custom header, yet docs omit the header | Clients do not know the handler selection condition | Declare header parameters and explain the condition |

Media type conditions can use wildcards or suffixes, such as `application/*` or `application/*+json`. Broad conditions support more formats yet increase overlap risk. Only use wildcards when the handler genuinely handles the entire corresponding media type group.

When Spring finds no matching mapping due to `Content-Type`, the result is usually `415`. When no representation matches `Accept`, the result is usually `406`. If multiple mappings match and none is more specific, an ambiguous handler error may occur. Check logs and test requests with realistic header combinations.

## 6. OpenAPI Path Item Model Limitations

OpenAPI describes resources under `paths`. Each path has one Path Item Object, and each Path Item has only one operation per HTTP method such as `get`, `post`, `put`, or `delete`.

Therefore, the document cannot declare two independent `post` keys for the same `/api/imports` merely because Spring has two Java methods. Instead, request formats are described together inside `requestBody.content`, and response formats are described inside `responses.<status>.content`.

Example of one operation accepting JSON or CSV and returning JSON:

```yaml
paths:
  /api/imports:
    post:
      summary: Import product data
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ImportJsonRequest'
          text/csv:
            schema:
              type: string
              description: CSV content with sku and quantity columns
      responses:
        '200':
          description: Import result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ImportResult'
        '415':
          description: Unsupported request media type
```

This example accurately reflects two handlers with different `consumes`: they are two ways of submitting the request body for the same operation. Each media type can use its own schema.

With two handlers differing in `produces`, the response can list multiple representations:

```yaml
paths:
  /api/products/export:
    get:
      summary: Export product list
      responses:
        '200':
          description: Product list in the requested format
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Product'
            text/csv:
              schema:
                type: string
                description: CSV content
        '406':
          description: No representation matches Accept header
```

In this example, `Accept` indicates whether the client wants JSON or CSV; `Content-Type` in the response indicates which format the server returned.

## 7. OpenAPI Cannot Express Every Request-to-Response Relationship

`requestBody.content` and `responses.content` describe independent media type sets. They do not directly express rules like: "if the request is JSON then the response must be JSON, whereas if the request is CSV then the response must be CSV."

For example, the two handlers below form two format pairs:

| Request | Response |
|---|---|
| `application/json` | `application/json` |
| `text/csv` | `text/csv` |

If OpenAPI lists both JSON and CSV in `requestBody.content`, and both JSON and CSV in response `content`, readers might infer the operation supports cross combinations. Standard OpenAPI has no general construct to bind each request media type to one exact response media type.

When this relationship matters to clients, choose one of the following options:

1. **Use separate URLs for each business representation.** For example `/api/imports/json` and `/api/imports/csv`, if these are genuinely distinct contracts requiring explicit client choice.
2. **Use one operation with a unified response.** For instance, both JSON and CSV requests return `ImportResult` in JSON.
3. **Document the rule clearly in description or examples.** This works when keeping the same URL while needing to explain supported combinations.
4. **Use an organization-specific extension.** Only use this if internal tools understand the extension; standard OpenAPI clients may ignore it.

If two handlers differ only in how the same resource is serialized, one operation with multiple media types is usually a natural contract. If they differ in semantics, access permissions, status codes, or business workflows, consider designing separate endpoints so the contract is unambiguous.

## 8. How Does Springdoc Generate Operations for Overlapping Path/Method Mappings?

Springdoc reads Spring mappings to generate OpenAPI, yet the OpenAPI structure still allows only one operation per path/method pair. Thus, do not assume every controller method becomes an independent operation when they share `POST /api/imports` or `GET /api/products/export`.

When multiple handlers exist, the documentation output must be verified on the project's exact springdoc version. Depending on how the library collects mappings and metadata, media types may be aggregated or the document may omit part of another handler's schema, response, or description. Overlapping `@Operation` annotations with different content can also produce unpredictable metadata.

Recommended workflow:

1. Start the application with all handlers active.
2. Fetch `/v3/api-docs` and locate the exact path and HTTP method.
3. Verify all required media types appear in `requestBody.content` and response `content`.
4. Verify each media type's schema, status codes, descriptions, and security requirements.
5. If details are incomplete, centralize OpenAPI metadata or use an `OpenApiCustomizer` to standardize the final operation.

Do not annotate each handler as if OpenAPI allowed multiple operations for the same method. Treat the handlers as runtime execution branches of one operation and ensure the published operation describes all branches completely.

## 9. Describing Multiple Media Types with OpenAPI Annotations

If an operation can be documented directly on one handler or a representative method, Swagger annotations let you list multiple media types in the request body:

```java
@Operation(
    summary = "Import product data",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ImportJsonRequest.class)
            ),
            @Content(
                mediaType = "text/csv",
                schema = @Schema(type = "string",
                    description = "CSV content with sku and quantity")
            )
        }
    )
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Data imported successfully",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ImportResult.class)
        )
    ),
    @ApiResponse(responseCode = "415", description = "Unsupported media type")
})
```

For responses supporting multiple formats, declare multiple `@Content` entries in the same response:

```java
@ApiResponse(
    responseCode = "200",
    description = "Exported data",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductListResponse.class)
        ),
        @Content(
            mediaType = "text/csv",
            schema = @Schema(type = "string", description = "CSV content")
        )
    }
)
```

OpenAPI annotations only describe the documentation. Spring handlers must still have matching `consumes` and `produces`, converters must be able to read/write the content, and the controller must actually return the published representations. If metadata is placed on one representative handler, confirm springdoc preserves it in the final operation.

## 10. Standardizing Operations with OpenApiCustomizer

When multiple separate Java handlers must be kept yet springdoc does not fully aggregate their content, you can use `OpenApiCustomizer` to adjust the final operation. This works well when ensuring `requestBody.content` or response `content` contains all media types and schemas.

The example below adds two request formats for the `POST /api/imports` operation:

```java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.RequestBody;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ImportOpenApiConfiguration {

    @Bean
    OpenApiCustomizer importRequestContent() {
        return openApi -> {
            PathItem pathItem = openApi.getPaths().get("/api/imports");
            if (pathItem == null || pathItem.getPost() == null) {
                return;
            }

            Operation operation = pathItem.getPost();
            RequestBody requestBody = operation.getRequestBody();
            if (requestBody == null) {
                requestBody = new RequestBody().required(true);
            }

            Content content = requestBody.getContent();
            if (content == null) {
                content = new Content();
            }

            content.addMediaType(
                "application/json",
                new MediaType().schema(
                    new Schema<>().$ref("#/components/schemas/ImportJsonRequest")
                )
            );
            content.addMediaType("text/csv", new MediaType().schema(new StringSchema()));

            requestBody.setContent(content);
            operation.setRequestBody(requestBody);
        };
    }
}
```

The snippet uses Swagger Core models to modify the document after springdoc creates the operation. If the application uses multiple `GroupedOpenApi` beans, attach the customizer to the appropriate document group or configuration to avoid modifying the wrong document. Path names in the customizer must match the path appearing in OpenAPI, including any context mapping springdoc includes in the document.

Response `content` can be added following the same pattern by retrieving the response from `operation.getResponses()`, creating or fetching `Content`, adding media types and schemas, and setting it back. When editing, preserve existing statuses, descriptions, headers, and schemas. A customizer only alters the published contract; it does not change request mappings or controller behavior.

## 11. Testing Mapping Branches with MockMvc

For handlers differing by `consumes`, send each `Content-Type` to verify Spring chooses the right method and returns the expected result:

```java
@WebMvcTest(ImportController.class)
class ImportControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsJsonImport() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"source":"warehouse-a","items":[]}
                    """))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
    }

    @Test
    void acceptsCsvImport() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType("text/csv")
                .accept(MediaType.APPLICATION_JSON)
                .content("sku,quantity\nP-01,4"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
    }

    @Test
    void rejectsUnsupportedContentType() throws Exception {
        mockMvc.perform(post("/api/imports")
                .contentType(MediaType.TEXT_PLAIN)
                .content("unsupported"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

For handlers differing by `produces`, check both `Accept` and response `Content-Type`:

```java
@Test
void exportsJsonWhenJsonIsAccepted() throws Exception {
    mockMvc.perform(get("/api/products/export")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON));
}

@Test
void exportsCsvWhenCsvIsAccepted() throws Exception {
    mockMvc.perform(get("/api/products/export")
            .accept("text/csv"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.parseMediaType("text/csv")));
}
```

These examples are test templates; configure mocks/services, DTOs, and status codes to match your actual controller. Add tests for `Accept: */*`, missing `Accept`, media types with charset parameters, wildcards, and cases with no matching representation. These cases help uncover overlapping mapping conditions or ambiguous default selections.

## 12. Inspecting the OpenAPI Document and Swagger UI

After starting the application, fetch `/v3/api-docs` or `/v3/api-docs.yaml`. For a path sharing a method, verify the following points:

1. The path has only one operation for the corresponding HTTP method.
2. `requestBody.content` lists all media types accepted by the `consumes` handlers.
3. Each request media type points to the right schema, such as a JSON object and a CSV string.
4. `responses.<status>.content` lists all representations that `produces` handlers can return.
5. Error status codes and schemas such as `406` or `415` are described if published by the API.
6. Summary, description, operationId, tags, and security requirements are neither lost nor conflicting across handlers.

In Swagger UI, choose each request body media type and try calling the endpoint. For operations returning multiple formats, select the corresponding `Accept` value if supported by the UI. Inspect the request in the Network tab and confirm the response carries the right `Content-Type`. Swagger UI merely reflects OpenAPI; the UI does not prove the controller actually supports a media type.

You can test the generated document in a dedicated integration test. For example, with MockMvc you can call `/v3/api-docs` and assert JSONPath for the `content` keys:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/imports'].post.requestBody.content['application/json']"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/imports'].post.requestBody.content['text/csv']"
    ).exists());
```

Document tests should run with the application's real springdoc configuration, because `@WebMvcTest` may not load full OpenAPI configurations, customizer beans, or other controllers.

## 13. When Should Endpoints Be Split?

Sharing a path and method is beneficial when handlers perform the same business operation and differ only in representation format. For example, the same import action accepting JSON or CSV, or the same list export supporting JSON and CSV.

Consider separate paths when:

- Each format has different business rules, access permissions, or lifecycles.
- Requests and responses have format-dependent relationships that OpenAPI cannot clearly express.
- Clients frequently hit errors due to default `Accept` headers or cannot reliably select a representation.
- Two handlers have significantly different status codes, error payloads, or side effects.
- Mapping configuration accumulates more wildcards or overlapping conditions.

For example, `/api/imports/json` and `/api/imports/csv` make the format choice explicit in the URL. This is an API design decision, not a mandatory technical requirement. When sharing the same path, keep semantics unified and document all media types thoroughly in one operation.

## 14. Design and Review Workflow

When creating multiple handlers sharing a path and method, proceed in order:

1. Identify the shared business operation and the representations clients need to send or receive.
2. Choose `consumes` conditions for request bodies and `produces` conditions for responses.
3. Ensure mappings do not duplicate completely and do not overlap in ways that cause ambiguous handlers.
4. Confirm an `HttpMessageConverter` can read/write each media type and corresponding Java type.
5. Test `415`, `406`, requests without headers, and wildcard `Accept`.
6. Fetch OpenAPI and merge runtime branches into a single operation with complete request/response `content`.
7. Add annotations or an `OpenApiCustomizer` if springdoc does not yet publish all schemas and media types.
8. Test both HTTP behavior and JSON/YAML documentation before release.

Spring MVC chooses handlers via request mapping conditions; springdoc turns those handlers into an OpenAPI contract. Good design ensures both models agree: every published media type must be genuinely handled at runtime, and every handler branch must be represented in the single operation clients consume.

## 15. References

- [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `consumes`, `produces`, `headers`, `params` conditions, and handler selection.
- [Spring Framework: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converters reading request bodies and writing response bodies.
- [Springdoc OpenAPI](https://springdoc.org/): generating OpenAPI documentation from Spring Boot and customizing the document.
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object): path structure and permitted operations.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): describing request bodies by media type.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): describing responses and content by status code.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotations for describing operations, request bodies, and responses.
