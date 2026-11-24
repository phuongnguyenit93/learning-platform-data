# Inferred Error Codes or Content Types Differing from Actual Responses

Springdoc-openapi inspects controllers, annotations, return types, and Spring configuration to generate the `responses` section in OpenAPI. This section describes the HTTP status codes, response content, and media types a client may receive. When metadata does not capture all runtime branches, Swagger UI may display `200 OK` while the application actually returns `201 Created`, `204 No Content`, or `404 Not Found`. Similarly, the document may list `application/json` while Spring actually returns `application/problem+json`, `text/csv`, or another content type.

These discrepancies commonly arise when methods use `ResponseEntity` to pick status codes conditionally, when `@ControllerAdvice` handles exceptions, when `@ApiResponse` is missing for error branches, or when `produces`/`consumes` mismatch content negotiation. The right fix is determining the actual HTTP response first, then making OpenAPI metadata describe every case the API commits to supporting.

## Objectives

After this lesson, you will be able to:

- Distinguish status codes inferred from annotations vs status codes chosen at runtime.
- Determine when to use `@ResponseStatus`, `ResponseEntity`, or `@ApiResponse`.
- Document success responses, error responses, empty-body responses, and file download responses.
- Synchronize `@ControllerAdvice` with OpenAPI-generated responses.
- Understand `springdoc.override-with-generic-response` and its effect.
- Distinguish `Content-Type`, `Accept`, `consumes`, and `produces`.
- Declare multiple response media types with `@Content`.
- Document `ProblemDetail` with `application/problem+json`.
- Diagnose `406 Not Acceptable` and `415 Unsupported Media Type` errors.
- Test actual statuses, headers, and bodies with MockMvc.
- Inspect OpenAPI JSON to verify `responses` and `content`.

## 1. Recognizing Symptoms

Common signs:

| Symptom | What is happening |
|---|---|
| Swagger UI only shows `200` yet API returns `201` | Springdoc lacks static metadata for the runtime branch status |
| API returns `204` yet docs show a JSON schema | Response is documented as having a body even though runtime sends none |
| Swagger UI displays `Undocumented` after calling API | Runtime status has no matching response entry in OpenAPI |
| Docs state `application/json` yet response header is `application/problem+json` | Error body media type is not described accurately |
| API returns `406` when client sends `Accept: application/xml` | Server has no representation matching the requested media type |
| API returns `415` when sending JSON | Request `Content-Type` mismatches `consumes` mapping or converters |
| Some endpoints show repeated error responses | `@ControllerAdvice` responses are merged globally alongside local declarations |
| File download endpoint is described as JSON object | Return type or `@Content` does not express binary media type |

Do not start by tweaking Swagger UI. Collect the actual response first: status line, `Content-Type`, `Content-Disposition`, and body. Only then compare against the OpenAPI document.

## 2. Distinguishing Static Descriptions from Runtime Responses

Springdoc builds OpenAPI from information observable when analyzing the Spring application context. The application itself decides the actual response while handling each request.

| Information source | What it can describe |
|---|---|
| Controller return type | Expected body type, e.g. DTO, collection, or `ProblemDetail` |
| `@ResponseStatus` | Fixed HTTP status attached to a handler |
| `ResponseEntity` | Status, headers, and body returned by code at runtime |
| `@ApiResponse` | Status, description, headers, and media types declared explicitly in OpenAPI |
| `@ControllerAdvice` / `@ExceptionHandler` | Response when handling exceptions |
| `@RequestMapping` / `@GetMapping` | Mapping conditions, including method, `consumes`, and `produces` |
| `HttpMessageConverter` | How the body is converted into an HTTP representation |
| `Accept` and `Content-Type` | Representation the client requests and representation the request sends |

For example, a method with return type `OrderResponse` does not guarantee it only returns `200`. If code can return `201` on creation, `202` for asynchronous processing, and `409` on duplicate data, all three cases must be described.

Spring Framework uses `ResponseEntity` to return status, headers, and body; the body is typically converted into a representation by registered `HttpMessageConverter` instances. Therefore, looking only at a generic type like `ResponseEntity<OrderResponse>` is not enough to determine all runtime responses. <Link url="https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html" title="Spring Framework: ResponseEntity"/>.

## 3. Incorrectly Inferred HTTP Status Codes

### 3.1. Using `@ResponseStatus` for a Fixed Status

If an endpoint always returns one status, declare it directly with `@ResponseStatus`:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Here, status `201 Created` is a fixed part of the handler. Springdoc can use this metadata to describe the response. This works well when the status does not depend on processing branches.

### 3.2. Documenting Every Branch of `ResponseEntity`

If the status varies conditionally, declare responses explicitly:

~~~java
@Operation(summary = "Create or accept order request")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created immediately",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "202",
        description = "Request accepted for asynchronous processing",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderAcceptedResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Order with duplicate business key",
        content = @Content(
            mediaType = "application/problem+json",
            schema = @Schema(implementation = ProblemDetail.class)
        )
    )
})
@PostMapping
ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
    if (orderService.isDuplicate(request)) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(problemForDuplicate(request));
    }

    if (orderService.requiresAsyncProcessing(request)) {
        return ResponseEntity.accepted()
            .body(orderService.enqueue(request));
    }

    return ResponseEntity.status(HttpStatus.CREATED)
        .body(orderService.create(request));
}
~~~

The example uses `ResponseEntity<?>` to clarify that the body may vary by branch. In real code, you can use a sealed interface or response wrapper if that fits your domain model. Even if the return type expresses a union type, each status code and schema must still be declared so OpenAPI represents the contract accurately.

Do not rely on a single happy-path test to infer all responses. List every status the endpoint can genuinely return, including validation, conflict, authentication, and rate-limit errors if they belong to the contract.

### 3.3. Responses Without a Body

For `204 No Content` or bodyless `404`, declare `content = @Content` to avoid generating a body schema:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Resource deleted",
    content = @Content
)
~~~

The Springdoc FAQ also recommends using `content = @Content` or a hidden schema to describe an empty response. Do not declare a DTO just because a method returns a wrapper type when runtime sends no body. <Link url="https://springdoc.org/faq.html" title="Springdoc FAQ: response with empty content"/>.

## 4. Synchronizing `@ControllerAdvice` and Error Responses

Springdoc can include responses from `@ControllerAdvice` in generated operations. The property `springdoc.override-with-generic-response` defaults to `true`; when enabled, `@ControllerAdvice` responses are automatically added to generated responses. <Link url="https://springdoc.org/core-properties.html" title="Springdoc core properties"/>.

Example of an error handler with a fixed status:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            exception.getMessage()
        );
    }
}
~~~

For Springdoc to recognize error statuses automatically from exception handlers, declare the HTTP code with `@ResponseStatus` on handler methods. This guidance is documented in Springdoc's error handling section. <Link url="https://springdoc.org/features.html" title="Springdoc Features: Error Handling for REST"/>.

If the handler returns `ResponseEntity` and the status is picked dynamically inside the method body, verify the document includes all statuses. When unsure whether Springdoc infers every branch, declare the response on the operation with `@ApiResponse`.

### 4.1. When Global Responses Repeat or Overwrite

If an error response appears on every operation even though it only applies to certain routes, review this setting:

~~~yaml
springdoc:
  override-with-generic-response: true
~~~

Setting `false` stops automatically adding `@ControllerAdvice` responses to all operations:

~~~yaml
springdoc:
  override-with-generic-response: false
~~~

When disabled, explicitly declare common errors on the appropriate operations or via an appropriate customizer. Do not disable the property merely to hide duplicate responses without checking which global error descriptions the API would be missing.

If using a customizer, add responses to the existing `ApiResponses` by response code. Avoid replacing the entire `responses` map because that can erase success responses or custom responses already declared via annotations.

## 5. Documented Media Types Differing from Actual `Content-Type`

### 5.1. Distinguishing `Content-Type` and `Accept`

These two headers point in opposite directions:

| Header | Meaning |
|---|---|
| `Content-Type` | Data format of the request body sent by the client to the server |
| `Accept` | Representation format the client wants to receive from the server |

In Spring mappings:

- `consumes` constrains the request body media type and is typically matched against `Content-Type`.
- `produces` constrains the response media type and is matched against `Accept`.

For example:

~~~java
@PostMapping(
    path = "/imports",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importFile(@RequestPart MultipartFile file) {
    return importService.importFile(file);
}
~~~

If a client sends `Content-Type: application/json` to a mapping that only accepts multipart, Spring may return `415 Unsupported Media Type`. If a client requests `Accept: application/xml` while the endpoint only produces JSON, Spring may return `406 Not Acceptable`. The `consumes` and `produces` attributes of Spring mappings govern request matching and allowed response representations. <Link url="https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html" title="Spring Framework: Request Mapping"/>.

### 5.2. Declaring Response Media Types with `@Content`

`@ApiResponse` describes a response code and the list of representations inside `content`. Example endpoint supporting JSON and XML:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order information",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        ),
        @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        )
    }
)
~~~

Listed media types must match representations the application can genuinely produce. Adding XML to OpenAPI does not magically give Spring an XML converter; the application still needs the corresponding converter and mapping.

### 5.3. Springdoc Default Media Types

Springdoc's two default properties are:

| Property | Default | Purpose |
|---|---|---|
| `springdoc.default-consumes-media-type` | `application/json` | Default request media type |
| `springdoc.default-produces-media-type` | `*/*` | Default response media type |

Consult the official core properties reference. <Link url="https://springdoc.org/core-properties.html" title="Springdoc core properties reference"/>.

You can configure these when the application has consistent defaults:

~~~yaml
springdoc:
  default-consumes-media-type: application/json
  default-produces-media-type: application/json
~~~

Do not set the global default to JSON if the application has many routes returning CSV, binary, XML, or Problem Details. For specialized routes, declare `produces` and `@ApiResponse(content = ...)` explicitly. Defaults are only fallback values when mapping metadata omits media types; they do not change how `HttpMessageConverter` actually serializes bodies.

## 6. Describing `ProblemDetail` and `application/problem+json`

Spring Framework supports Problem Details for HTTP APIs per RFC 9457. `ProblemDetail` carries `status`, `title`, `detail`, `type`, `instance`, and extension properties. When Spring serializes `ProblemDetail` with Jackson, the preferred media type is `application/problem+json`; if a corresponding XML converter is present, the media type is `application/problem+xml`. <Link url="https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html" title="Spring Framework: Error Responses"/>.

Therefore, `ProblemDetail`-shaped error responses should be described with the proper media type:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Order not found",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
~~~

If OpenAPI only lists `application/json`, client generators may select the wrong decoder or Swagger UI may display response content differing from the runtime header. `application/problem+json` is the dedicated media type for Problem Details even though the payload uses JSON syntax.

### 6.1. Error Response per RFC 9457

An actual response may look like:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Order ORD-42 not found",
  "instance": "/api/orders/ORD-42"
}
~~~

Do not describe this response as a custom error DTO if the actual body is `ProblemDetail`. If the application extends `ProblemDetail` with fields like `code` or `violations`, use a corresponding extended schema or define a subclass and test that JSON serializes properly.

### 6.2. Exception Handlers with Multiple Media Types

Spring Framework allows `@ExceptionHandler` methods to declare producible media types via the `produces` attribute in supported versions. For example, an exception can return JSON to API clients and HTML to browsers:

~~~java
@ExceptionHandler(
    value = IllegalArgumentException.class,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ApiError> handleJson(IllegalArgumentException exception) {
    return ResponseEntity.badRequest()
        .body(new ApiError("INVALID_INPUT", exception.getMessage()));
}

@ExceptionHandler(
    value = IllegalArgumentException.class,
    produces = MediaType.TEXT_HTML_VALUE
)
String handleHtml(IllegalArgumentException exception, Model model) {
    model.addAttribute("message", exception.getMessage());
    return "error";
}
~~~

The `produces` attribute on `@ExceptionHandler` was introduced in Spring Framework 6.2. Content negotiation during exception handling picks the handler matching `Accept`. On older Spring Framework versions, do not use this example; use a handler with fixed status/media type or dispatch manually inside a single handler. <Link url="https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html" title="Spring Framework 6.2: ExceptionHandler API"/>.

If an API endpoint has multiple error representations, document each media type and schema in OpenAPI. If HTML is solely for browser views and not part of the API contract, clearly separate web routes/views from REST APIs rather than publishing it as a representation for API clients.

### 6.3. Distinguishing HTTP Status from Business Error Codes

An HTTP status is a protocol code such as `400`, `404`, or `409`. A business error code is a value inside the body such as `ORDER_NOT_FOUND` or `ORDER_ALREADY_EXISTS`. These two values serve different purposes:

~~~json
{
  "code": "ORDER_ALREADY_EXISTS",
  "message": "Order already exists",
  "details": {
    "orderNumber": "ORD-42"
  }
}
~~~

In OpenAPI, declare `responseCode = "409"` for the HTTP status and describe the body schema containing the `code` field. Do not put the string `ORDER_ALREADY_EXISTS` in `responseCode`, because OpenAPI's response map uses HTTP codes or the `default` key.

If error codes are a stable set of values, define an enum in the schema so clients can generate constants:

~~~java
public enum ApiErrorCode {
    ORDER_NOT_FOUND,
    ORDER_ALREADY_EXISTS,
    INVALID_ORDER_STATE
}

public record ApiError(
    ApiErrorCode code,
    String message,
    Map<String, Object> details
) {
}
~~~

In the snippet above, also import `java.util.Map`.

Declare the response schema:

~~~java
@ApiResponse(
    responseCode = "409",
    description = "Order state conflict",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

When using RFC 9457, you can put the business code in an extension property of `ProblemDetail` or use a subclass with an explicit schema. Check the actual JSON because Jackson renders `ProblemDetail`'s `properties` map as top-level properties.

## 7. Mismatched Request `consumes` and Response `produces`

Content negotiation errors often start from confusing `Content-Type` with `Accept` or declaring overly narrow mappings.

| Client sends | Spring mapping | Common outcome |
|---|---|---|
| `Content-Type: application/json` | `consumes = application/json` | Request body is read by the JSON converter |
| `Content-Type: text/plain` | `consumes = application/json` | `415 Unsupported Media Type` |
| `Accept: application/json` | `produces = application/json` | Matching JSON response |
| `Accept: application/xml` | `produces = application/json` | `406 Not Acceptable` if no compatible representation exists |
| No specific `Accept` sent | Default mapping and converters | Spring selects a writable representation |

Inspect mappings at both class and method levels. For `produces`, method-level mappings can override class-level lists; do not assume the two lists are always merged. Check the mapping rules for your Spring Framework version.

### 7.1. Multiple `consumes` on the Same Operation

If the same path and HTTP method accept multiple request media types with the same semantics, declare:

~~~java
@PostMapping(
    path = "/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importData(@RequestBody ImportRequest request) {
    return importService.importData(request);
}
~~~

When mappings are split across multiple overloaded methods with the same path and HTTP method, Springdoc may produce a single OpenAPI operation. Springdoc documentation recommends placing `@Operation` on one appropriate method rather than duplicating differing metadata across every overload; inspect the generated document to verify no information is lost. <Link url="https://springdoc.org/faq.html" title="Springdoc FAQ: multiple consuming media types"/>.

## 8. File, Binary, and Non-JSON Responses

File download endpoints typically return `ResponseEntity<Resource>` or `ResponseEntity<byte[]>` along with a `Content-Disposition` header. If docs display an object or JSON schema, describe the response as binary:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Report file",
    content = @Content(
        mediaType = "application/pdf",
        schema = @Schema(type = "string", format = "binary")
    )
)
~~~

Controller example:

~~~java
@GetMapping(
    path = "/reports/{id}/download",
    produces = "application/pdf"
)
ResponseEntity<Resource> download(@PathVariable String id) {
    Resource file = reportService.loadPdf(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment()
                .filename("report-" + id + ".pdf")
                .build()
                .toString()
        )
        .body(file);
}
~~~

If the endpoint returns CSV, images, ZIP, or streams, use the exact media type and schema matching the actual representation. Do not let Springdoc's JSON default determine the schema of a file response.

## 9. Properties to Check

| Property | Default | When to review |
|---|---|---|
| `springdoc.default-consumes-media-type` | `application/json` | Default request media type when mapping does not declare one |
| `springdoc.default-produces-media-type` | `*/*` | Default response media type when mapping does not declare one |
| `springdoc.override-with-generic-response` | `true` | Automatically adds `@ControllerAdvice` responses to operations |
| `springdoc.api-docs.enabled` | `true` | Check whether the docs endpoint is enabled to read JSON |

Do not confuse `springdoc.produces-to-match` with `springdoc.default-produces-media-type`. The first filters operations by media type condition during scanning; the second sets the default media type for descriptions. Likewise, `springdoc.consumes-to-match` is a filter condition, not a way to alter runtime `Content-Type`.

If properties are set across multiple profiles, check the effective configuration of the running profile. A staging profile might return JSON while production uses Problem Details or binary responses due to different beans/customizers; OpenAPI must be generated from the exact context being published.

## 10. Be Careful When Customizing OpenAPI in Code

An `OpenApiCustomizer` can add shared responses such as rate limits or system errors. When adding responses, preserve existing responses and add only missing entries:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import io.swagger.v3.oas.models.responses.ApiResponses;
~~~

~~~java
@Bean
OpenApiCustomizer addRateLimitResponse() {
    return openApi -> openApi.getPaths().values().forEach(pathItem ->
        pathItem.readOperations().forEach(operation -> {
            ApiResponses responses = operation.getResponses();
            if (responses == null) {
                responses = new ApiResponses();
                operation.setResponses(responses);
            }

            if (!responses.containsKey("429")) {
                responses.addApiResponse(
                    "429",
                    new io.swagger.v3.oas.models.responses.ApiResponse()
                        .description("Rate limit exceeded")
                );
            }
        })
    );
}
~~~

This example only adds a response description. If rate-limit middleware actually returns JSON or `ProblemDetail`, add content schema and media type matching the body. Do not declare `429` if the application/gateway cannot actually return that status for the route.

A customizer applied to the default document may not automatically apply to all `GroupedOpenApi` beans. If the same metadata is needed across groups, use a global customizer appropriate for your Springdoc version and inspect each group document.

Do not use a customizer to force every operation to the same response code or media type when controllers have distinct semantics. Shared metadata should only contain what is genuinely true for every operation receiving it.

## 11. Errors and Fixes Table

| Symptom | Possible cause | How to fix |
|---|---|---|
| Only `200` visible in Swagger UI | Missing metadata for `201`/`202` chosen dynamically by `ResponseEntity` | Declare each `@ApiResponse` or fixed status via `@ResponseStatus` |
| `204` response has a body schema | Operation is documented as having content | Use `content = @Content` |
| Runtime returns `404` but OpenAPI lacks `404` | Exception handler lacks status metadata or generic responses disabled | Add `@ResponseStatus` and check `override-with-generic-response` |
| Every operation includes unrelated errors | `@ControllerAdvice` merged into all operations | Narrow handler scope or consider `springdoc.override-with-generic-response=false` |
| Docs only list application/json | `@Content` or mapping omits Problem Details | Declare `application/problem+json` and `ProblemDetail` schema |
| Runtime returns JSON but docs say `*/*` | Default produces not configured for uniform contract | Declare `produces` or appropriate default property |
| `415 Unsupported Media Type` | `Content-Type` mismatches `consumes` or converter | Check mapping and request header |
| `406 Not Acceptable` | `Accept` mismatches `produces`/converter | Check negotiation and supported representations |
| Swagger UI displays file response as JSON | Missing binary schema and media type | Use `type = "string", format = "binary"` and proper media type |
| Response code appears without body schema | `@ApiResponse` only has description | Add `content` and `@Schema(implementation = ...)` |
| Response content type duplicated or wrong after customizer | Customizer replaces response/content map improperly | Merge by response code and media type |
| Default docs right yet group docs wrong | Customizer runs only on default document or group filter differs | Check each `GroupedOpenApi` and global customizer |
| Runtime tests pass yet Swagger UI stays wrong | Missing assertions on `/v3/api-docs` | Add contract tests inspecting response maps and media types |

## 12. Comprehensive Practice Exercise

Build an order management API with varied responses:

1. Create a POST endpoint returning `201 Created` when an order is created immediately.
2. Add a branch returning `202 Accepted` when the request is queued.
3. Add a `409 Conflict` error branch with business error code `ORDER_ALREADY_EXISTS`.
4. Create a GET endpoint that fails to find an order and returns `ProblemDetail` with `404`.
5. Create a DELETE endpoint returning `204 No Content`.
6. Create a PDF report download endpoint returning `application/pdf` and `Content-Disposition`.
7. Declare `@ResponseStatus` for fixed statuses.
8. Declare `@ApiResponses` for `ResponseEntity` branches.
9. Define `@ControllerAdvice` and check `springdoc.override-with-generic-response`.
10. Declare `consumes`/`produces` matching actual representations.
11. Call each endpoint via curl with varying `Accept` and `Content-Type` headers.
12. Inspect `/v3/api-docs` and verify each response code, content type, and schema.
13. Write MockMvc tests for actual statuses/headers/bodies.
14. Write OpenAPI contract tests for response maps.
15. If using multiple groups, repeat verification for every group.

### Completion Criteria

- [ ] Distinguish HTTP status from business error codes.
- [ ] Explain why return types alone do not capture all runtime statuses.
- [ ] Use `@ResponseStatus` for fixed statuses.
- [ ] Use `@ApiResponse` for dynamic response branches.
- [ ] Describe responses from `@ControllerAdvice`.
- [ ] Understand the effect of `springdoc.override-with-generic-response`.
- [ ] Distinguish `Content-Type`, `Accept`, `consumes`, and `produces`.
- [ ] Describe `application/problem+json` properly for `ProblemDetail`.
- [ ] Describe empty and binary responses properly.
- [ ] Diagnose `406` and `415`.
- [ ] Have MockMvc tests verifying status, media type, and body.
- [ ] Have contract tests verifying response codes and content types in OpenAPI.

## 13. Layered Diagnostic Procedure

When status codes or media types in Swagger UI mismatch the server, follow this order:

1. Send a request directly to the endpoint using the exact method, path, body, and headers the client uses.
2. Record HTTP status, `Content-Type`, `Content-Disposition`, and response body.
3. Repeat requests with different `Accept` and `Content-Type` values if the endpoint supports multiple representations.
4. Check controller mappings: `@ResponseStatus`, `ResponseEntity`, `consumes`, and `produces`.
5. Check exception handlers: which exceptions are caught, which status is returned, and which body is serialized.
6. Fetch `/v3/api-docs` or the corresponding group document.
7. Compare the operation's `responses`, each response code, each media type, and schema.
8. Adjust metadata or Springdoc default configuration.
9. Re-run runtime tests and contract tests to verify both sides.

### 9.1. Capturing Actual Responses with curl

Successful JSON request:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"productCode":"BOOK-01","quantity":2}' \
  http://localhost:8080/api/orders
~~~

Error-triggering request:

~~~bash
curl -i \
  -H "Accept: application/problem+json" \
  http://localhost:8080/api/orders/unknown
~~~

Request asking for an unsupported media type:

~~~bash
curl -i \
  -H "Accept: application/xml" \
  http://localhost:8080/api/orders/unknown
~~~

Read the status line and response headers before inspecting the body. If the server returns `406` or `415`, check mapping conditions and converters; adding `@ApiResponse` to OpenAPI does not fix runtime errors.

### 9.2. Inspecting OpenAPI JSON

Download the document:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
~~~

Inspect the operation's responses with `jq`:

~~~bash
jq '.paths["/api/orders"].post.responses' openapi.json
~~~

Inspect a specific content type:

~~~bash
jq '.paths["/api/orders"].post.responses["409"].content' openapi.json
~~~

The output should have the right media type keys, such as `application/problem+json`. If the operation resides in a group, fetch the corresponding `/v3/api-docs/{group}` URL; do not mistakenly check the default document.

### 9.3. Inspecting Response Content in OpenAPI

A response with a JSON body typically has this structure:

~~~json
{
  "responses": {
    "201": {
      "description": "Order created",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/OrderResponse"
          }
        }
      }
    },
    "409": {
      "description": "Order already exists",
      "content": {
        "application/problem+json": {
          "schema": {
            "$ref": "#/components/schemas/ProblemDetail"
          }
        }
      }
    }
  }
}
~~~

In OpenAPI, each response code is an entry inside `responses`. `content` is a map from media type to the corresponding representation's schema and examples. Responses without a body can omit `content` or declare empty content.

## 14. Testing Runtime Responses with MockMvc

Contract tests should verify both real HTTP responses and the OpenAPI document. Example testing status and media type:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderResponseContractTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderReturns201Json() throws Exception {
        CreateOrderRequest request =
            new CreateOrderRequest("BOOK-01", 2);

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }

    @Test
    void missingOrderReturnsProblemJson() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "missing")
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.status").value(404));
    }
}
~~~

These tests verify the status and media type Spring actually returns. For APIs supporting multiple branches, create separate tests per branch, including validation, conflict, not found, no content, and binary responses.

## 15. Testing OpenAPI Response Metadata

You can fetch `/v3/api-docs` with MockMvc and assert response codes and content types:

~~~java
@Test
void openApiDocumentsOrderResponseCodesAndMediaTypes() throws Exception {
    String json = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode document = objectMapper.readTree(json);
    JsonNode createOperation = document
        .path("paths")
        .path("/api/orders")
        .path("post");

    JsonNode responses = createOperation.path("responses");
    assertThat(responses.has("201")).isTrue();
    assertThat(responses.has("409")).isTrue();

    assertThat(
        responses.path("201").path("content")
            .has("application/json")
    ).isTrue();

    assertThat(
        responses.path("409").path("content")
            .has("application/problem+json")
    ).isTrue();
}
~~~

Required imports:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Adjust path, method, response codes, and media types for your real API. If using multiple `GroupedOpenApi` beans, run assertions for each group document. Contract tests reading only the document do not replace runtime tests; keep both to catch cases where docs are right yet handlers fail, or handlers work yet docs lack metadata.

## Continuing Study

After this lesson, combine response metadata with contract testing, error handling, and client generation. An operation is only accurately described when status codes, media types, schemas, and runtime bodies agree; every change to exception handlers or content negotiation should be verified with both HTTP tests and the OpenAPI document.

## References

- [Springdoc Features – Error Handling for REST using @ControllerAdvice](https://springdoc.org/features.html)
- [Springdoc FAQ – Response with empty content and media types](https://springdoc.org/faq.html)
- [Springdoc Core Properties Reference](https://springdoc.org/core-properties.html)
- [Spring Framework – Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework – ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework 6.2 – ExceptionHandler produces attribute](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html)
- [Spring Framework – Error Responses and ProblemDetail](https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
