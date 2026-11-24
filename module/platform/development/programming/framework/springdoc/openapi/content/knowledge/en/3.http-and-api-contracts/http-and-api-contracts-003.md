# Content Types via Content-Type, Accept, consumes, and produces

An HTTP API can receive and return data in multiple formats. To ensure clients and servers interpret exchanged data the same way, HTTP uses headers such as `Content-Type` and `Accept`; Spring MVC uses `consumes` and `produces` conditions to select the appropriate handler. Springdoc-openapi brings these capabilities into the OpenAPI contract so API consumers know which format requests must send and which formats responses can be received in.

## 1. Media Types Describe Data Formats

In HTTP, content types are typically represented by a **media type** of the form `type/subtype`, optionally accompanied by parameters:

```text
application/json
text/plain; charset=UTF-8
multipart/form-data; boundary=----WebKitFormBoundary...
```

`type` indicates the general category of data; `subtype` identifies the specific format. Parameters after the semicolon add information needed to interpret the content, such as charset or boundary.

Some media types commonly used in APIs:

| Media type | Common purpose | Example content |
|---|---|---|
| `application/json` | Exchange objects or structured data in JSON | `{"id":12,"name":"Pen"}` |
| `application/problem+json` | Describe HTTP errors using Problem Details in JSON | `{"type":"about:blank","title":"Not Found","status":404}` |
| `application/xml` | Exchange XML data | `<item><id>12</id></item>` |
| `text/plain` | Plain text | `Order created` |
| `text/csv` | CSV-formatted data | `id,name\n12,Pen` |
| `application/octet-stream` | Generic binary data | File contents |
| `application/x-www-form-urlencoded` | Form fields encoded as key-value pairs | `name=An&active=true` |
| `multipart/form-data` | Multipart form, commonly used to send files and metadata | One part is a file, another part is JSON or text |

A media type is a label for how content should be interpreted. It does not automatically validate whether the data conforms to a business schema. For example, a body with `Content-Type: application/json` can still contain malformed JSON or miss required fields.

## 2. Content-Type Describes the Body Format

`Content-Type` describes the format of the body currently being sent. This header can appear in either a request or a response.

In a request, the client uses `Content-Type` to inform the server of the payload format:

```http
POST /api/products HTTP/1.1
Host: example.test
Content-Type: application/json

{"name":"Pen","price":12000}
```

The server relies on the media type to choose how to read the body. If an endpoint only accepts JSON and the client sends XML or `text/plain`, the request does not meet the endpoint's content condition.

In a response, the server uses `Content-Type` to inform the client of the body format it is about to receive:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":12,"name":"Pen","price":12000}
```

Do not confuse `Content-Type` with `Content-Encoding`. `Content-Type` describes the content format, whereas `Content-Encoding` describes how the content representation is encoded or compressed, such as `gzip`.

## 3. Accept Indicates Which Response Type the Client Wants

`Accept` is a header sent by the client to state the media types the client can process in the response. It is commonly used when an endpoint can return multiple formats.

Example:

```http
GET /api/reports/12 HTTP/1.1
Host: example.test
Accept: application/json, application/xml;q=0.8, */*;q=0.1
```

In this example, the client prefers JSON; XML is accepted with lower priority; other media types can be accepted with even lower priority. The `q` parameter ranges from `0` to `1` and represents the preference weight. `q=0` means the client does not accept that type.

Some common value patterns:

| Accept value | Meaning |
|---|---|
| `application/json` | Specifies JSON as the accepted format |
| `application/json, application/xml` | Accepts both JSON and XML |
| `application/*` | Accepts subtypes under the `application` group |
| `*/*` | Accepts any media type |
| `application/json;q=1, application/xml;q=0.5` | Prefers JSON over XML |

If the client does not send `Accept`, the server is usually allowed to choose a format suited to the endpoint and configuration. `Accept: */*` indicates the client places no restriction on media type. When the server cannot produce any representation matching the `Accept` requirement, the typical result is `406 Not Acceptable`.

`Accept` in this lesson concerns response **media types**. Headers such as `Accept-Language` and `Accept-Encoding` address natural language and compression, which are separate aspects of content negotiation.

## 4. Distinguishing Content-Type and Accept

The two headers often appear together but answer two different questions:

| Header | Question answered | Data direction | Example |
|---|---|---|---|
| `Content-Type` | What format is the body being sent? | Describes the body of the current message | Request sending JSON: `Content-Type: application/json` |
| `Accept` | In what format does the client want the response? | Client states a requirement for the response | `Accept: application/json` |

A resource creation request often includes both headers:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Pen","price":12000}
```

Here, `Content-Type` states that the request payload is JSON; `Accept` states that the client wants the response in JSON. The two values can differ. For instance, a client might send JSON while wanting to download the result as CSV if the endpoint supports it.

For requests without a body, such as a typical `GET`, `Content-Type` is usually unnecessary. However, `Accept` remains useful because a `GET` response has a body.

## 5. consumes and produces in Spring MVC

Spring MVC provides two attributes on `@RequestMapping` and shorthand annotations such as `@GetMapping` and `@PostMapping`:

- `consumes` restricts the media types that the handler accepts in the **request body**. Spring matches this condition against the request's `Content-Type`.
- `produces` restricts the media types that the handler can generate for the **response**. Spring uses this condition when evaluating the request's `Accept` header.

Example:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @ResponseStatus(HttpStatus.CREATED)
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return new ProductResponse(12L, request.name(), request.price());
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse get(@PathVariable long id) {
        return new ProductResponse(id, "Pen", 12000);
    }
}
```

With the `POST` mapping above:

- The request must have a `Content-Type` compatible with `application/json`.
- The body is read into `CreateProductRequest` via the appropriate message converter.
- The handler declares a JSON response; requests with an incompatible `Accept` header may be rejected during handler selection or response negotiation.

Shorthand annotations allow declaring conditions directly:

```java
@PostMapping(
    path = "/import",
    consumes = MediaType.TEXT_PLAIN_VALUE,
    produces = MediaType.TEXT_PLAIN_VALUE
)
String importText(@RequestBody String content) {
    return "Received " + content.length() + " characters";
}
```

When multiple formats are needed, a set of media types can be declared:

```java
@GetMapping(
    value = "/{id}/export",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
ProductExport export(@PathVariable long id) {
    return loadExport(id);
}
```

The declaration above only describes the formats the handler permits. The application also needs the corresponding `HttpMessageConverter` to actually serialize JSON or XML. To return XML, an appropriate XML converter and library configuration must be present; adding `application/xml` to `produces` does not automatically install XML serialization capability.

## 6. How Does Spring Convert the Body?

In Spring MVC, implementations of `HttpMessageConverter` read the request body into Java parameters and write Java objects into the response body. Converter selection depends on the Java type, media type, and configured converters.

Some examples:

| Java data | HTTP content | Common converter |
|---|---|---|
| DTO or object | `application/json` | `MappingJackson2HttpMessageConverter` in a Jackson-based configuration |
| `String` | `text/plain` | `StringHttpMessageConverter` |
| `byte[]` | Binary data | `ByteArrayHttpMessageConverter` |
| `Resource` | File or resource contents | `ResourceHttpMessageConverter` |
| DTO or object | `application/xml` | XML converter if the application has added and configured XML support |

`@RequestBody` instructs Spring to read the body through a matching converter. `@ResponseBody` and `@RestController` instruct Spring to write the return value to the response body through a converter. Therefore, three conditions must be considered together: the message media type, the Java type of the parameter/return value, and the converters available in the application.

Not every parameter is read from the body. `@PathVariable` extracts data from the URL; `@RequestParam` retrieves query or form parameters using Spring's binding mechanism; `@RequestHeader` reads headers. Using the proper annotation avoids the misconception that `Content-Type` controls all input data.

## 7. Form and File Upload Examples

### Form URL Encoded

A simple form can send:

```http
POST /api/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=an&rememberMe=true
```

In Spring MVC, form-formatted data is typically bound via `@RequestParam` or `@ModelAttribute`:

```java
@PostMapping(
    path = "/login",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
LoginResult login(
    @RequestParam String username,
    @RequestParam(defaultValue = "false") boolean rememberMe
) {
    return authenticate(username, rememberMe);
}
```

### Multipart Upload

`multipart/form-data` splits the body into multiple parts. Each part can have its own headers, such as field name, filename, and the part's media type:

```java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
UploadResult upload(
    @RequestPart("file") MultipartFile file,
    @RequestPart("metadata") UploadMetadata metadata
) {
    return store(file, metadata);
}
```

A client can send the `file` part as `application/pdf` and the `metadata` part as `application/json`. The request-level media type is `multipart/form-data`; each part's media type describes that individual part's content. When using browser `FormData`, let the browser generate the `Content-Type` header along with the `boundary`; manually setting `multipart/form-data` without a boundary can prevent the server from parsing the parts.

## 8. Representing Content-Type and Accept in OpenAPI

OpenAPI describes media types per operation. Two key locations are `requestBody.content` and `responses.<status>.content`.

Example of an operation receiving JSON and returning JSON:

```yaml
paths:
  /api/products:
    post:
      summary: Create a product
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Product created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
        '400':
          description: Invalid request
```

The `application/json` keys inside `content` are media types. Clients use `requestBody.content` to know which body formats can be sent; response content indicates which formats can be received for each status code. In the HTTP protocol, the client expresses response preference via `Accept`, while the server indicates the actual returned format via `Content-Type`.

Springdoc typically infers media type information from `consumes` and `produces` mappings, parameter types, and return types. When more explicit documentation is needed, Swagger/OpenAPI annotations can be used:

```java
@Operation(
    summary = "Create a product",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
@ApiResponse(
    responseCode = "201",
    description = "Product created",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
@ResponseStatus(HttpStatus.CREATED)
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ProductResponse create(@RequestBody CreateProductRequest request) {
    // ...
}
```

Annotation imports can use wildcards or specific imports from `io.swagger.v3.oas.annotations.*`; the example above specifies the `RequestBody` type explicitly to distinguish it from `org.springframework.web.bind.annotation.RequestBody`.

OpenAPI annotations document the contract. They do not configure `HttpMessageConverter`, alter runtime mapping, or enable a controller to accept a media type that the application does not yet support. Keep documentation annotations synchronized with `consumes`, `produces`, and the endpoint's actual behavior.

## 9. Using Swagger UI to Verify the Contract

After the application starts, open Swagger UI and select the operation to inspect. For operations with a request body, the UI displays the media types documented in `requestBody.content`. For responses, the UI displays the media types documented per status code.

When clicking **Try it out**, inspect the actual request in the browser's Network tab:

- `Content-Type` must match the selected body format.
- `Accept` must reflect the response format desired by the client.
- The body must match the schema structure and media type encoding.
- The response `Content-Type` must accurately describe the format returned by the server.

Swagger UI relies on the published OpenAPI document. If the document specifies `application/xml` but the controller lacks an XML converter, test invocations may fail even though the UI displays the XML option. Therefore, verify both the generated document and real requests/responses.

## 10. Common Error Codes When Media Types Mismatch

| HTTP code | Common scenario | How to check |
|---|---|---|
| `400 Bad Request` | Malformed body, deserialization failure, or data cannot bind to the Java type | Check body, schema, field types, and parse error message |
| `406 Not Acceptable` | Server cannot produce a response matching the client's `Accept` header or `produces` condition | Check `Accept`, `produces`, and response-writing converters |
| `415 Unsupported Media Type` | Request `Content-Type` is not accepted by the endpoint or no converter can read that content type | Check `Content-Type`, `consumes`, and request-reading converters |
| `404 Not Found` | No mapping matches path/method; in some situations mapping conditions also prevent handler selection | Check URL, HTTP method, and other mapping conditions |

For example, an endpoint declaring only `consumes = application/json` receiving `Content-Type: text/plain` from a client typically results in `415`. Conversely, an endpoint producing only JSON receiving `Accept: application/xml` from a client can result in `406` if the server has no matching XML representation.

Do not conclude that every `400`, `406`, or `415` error stems from a single header. An application may customize exception handlers and converter configurations, so read the response body, logs, and actual mappings to identify the root cause.

## 11. Testing with curl and MockMvc

### Sending JSON and Requesting JSON

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Pen","price":12000}'
```

The command above verifies both request and response directions: the body is JSON, and the client requests JSON. Observe the status code and `Content-Type` in the response.

### Sending an Unsupported Media Type to Verify consumes

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data 'name=Pen'
```

If the mapping only accepts JSON, this request must be rejected due to an incompatible media type.

### Checking an Unsupported Accept Header

```bash
curl -i http://localhost:8080/api/products/12 \
  -H 'Accept: application/xml'
```

If the endpoint only produces JSON and has no XML option, inspect the content negotiation result, typically `406`.

### Testing with MockMvc

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductAsJson() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Pen","price":12000}
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("name=Pen"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

This is an illustrative example of how to test; real tests need mock/service configuration and status codes matching the controller. Additional tests can cover `Accept`, XML converters, multipart, and error responses to ensure the OpenAPI document reflects actual behavior.

## 12. Workflow for Designing and Reviewing Media Types

When designing an endpoint, clearly answer the following questions:

1. Does the request have a body? If so, which media types is the client allowed to send?
2. Which Java type is the body bound to, and which converter will read it?
3. Which representations can the endpoint return for each status code?
4. How does `Accept` behave when the client requests an unsupported format?
5. Do `consumes` and `produces` in the Spring mapping match `requestBody.content` and `responses.content` in OpenAPI?
6. Do Swagger UI and HTTP tests confirm the actual headers and payloads?

For public APIs, choose common and consistent media types, document request/response formats clearly in OpenAPI, and test both valid cases and unsupported media type cases. This approach helps clients integrate with the right formats and enables the development team to catch discrepancies between controllers, converters, and API documentation early.

## 13. References

- [MDN: Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Type): meaning of the header describing a representation's media type.
- [MDN: Accept](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept): media range syntax, wildcards, and `q` weights in content negotiation.
- [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `consumes`, `produces` conditions and request mapping declarations.
- [Spring Framework: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): mechanism for reading and writing bodies via `HttpMessageConverter`.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): structure of `requestBody`, `responses`, and `content` in the API contract.
- [Swagger Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): how to use annotations to document operations, request bodies, and responses.
