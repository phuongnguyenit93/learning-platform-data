# Keeping Request Data Close to the Real HTTP Contract

MockMvc lets you test Spring MVC without opening a real HTTP port. However, a test only reflects how clients actually use an API when the incoming data has a shape close to the HTTP request a real client constructs. If a test passes data in whatever way is easiest in Java yet differs from the HTTP contract, the test can stay green while the application fails on requests from browsers, mobile apps, or other services.

When writing MockMvc tests, describe requests using explicit HTTP parts: method, path, query string, headers, content type, body, cookies, and authentication info. For JSON, send real JSON. For forms, send form parameters. For uploads, send multipart parts. Each kind of data must pass through the exact binding mechanism the application uses in production.

## 1. What Does the HTTP Contract Include?

An HTTP request is more than a Java DTO object. Requests have structure at the protocol layer:

~~~text
POST /api/orders?source=mobile HTTP/1.1
Host: example.test
Accept: application/json
Content-Type: application/json
Idempotency-Key: 7c9f...

{
  "sku": "COFFEE-01",
  "quantity": 2,
  "deliveryDate": "2026-11-20"
}
~~~

Each part above has its own meaning:

| Component | Meaning in the request | How to express in MockMvc |
|---|---|---|
| HTTP method | Action requested by the client | `get`, `post`, `put`, `patch`, `delete` |
| Path | Resource or endpoint | URI passed to the request builder |
| Path variable | Identifier embedded in the path | URI template and replacement values |
| Query parameter | Filter, pagination, or option in the URL | `queryParam` or encoded URI |
| Header | Metadata, content negotiation, auth, request preconditions | `header`, `accept`, `contentType` |
| Body | Payload sent to the server | `content`, `contentType` |
| Form parameter | Form field | `param` with matching content type |
| Cookie/session | Client-side state or login session | `cookie`, `session` |
| Multipart part | File or individual upload part | `multipart` and `file` |

A controller may receive a Java object, yet that object is normally created only after Spring processes the HTTP components. For example, `@RequestBody` uses a message converter to read the body; `@RequestParam` reads request parameters; `@PathVariable` extracts values from the path; `@RequestHeader` reads headers. If a test bypasses these boundaries, it fails to verify the full contract clients must follow.

## 2. Sending JSON Like a Real Client

Suppose an order-creation API accepts JSON:

~~~java
public record CreateOrderRequest(
        String sku,
        int quantity,
        LocalDate deliveryDate,
        String note
) {
}
~~~

The controller accepts the body with `@RequestBody`:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.create(request);
        return ResponseEntity
                .created(URI.create("/api/orders/" + response.id()))
                .body(response);
    }
}
~~~

A JSON request should explicitly declare both content type and accept:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2,
                  "deliveryDate": "2026-11-20",
                  "note": "Deliver before noon"
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").isNotEmpty())
    .andExpect(jsonPath("$.sku").value("COFFEE-01"));
~~~

`contentType` describes the incoming body format. `accept` describes the response format accepted by the client. These two headers serve different directions; setting `accept` does not substitute for `contentType`.

Do not pass a Java DTO directly to `content(...)`. This method expects body content, typically a string or byte array. Send serialized JSON instead:

~~~java
String json = objectMapper.writeValueAsString(request);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(json));
~~~

`ObjectMapper` should be injected from the Spring test context when you want the exact Jackson configuration used by the application, such as naming strategies, Java Time modules, custom serializers, or date formats. This keeps the JSON sent by tests aligned with the application's active serialization settings.

However, if a test serializes a DTO with the application's own `ObjectMapper` and uses that output as the request, the test can mask JSON contract mismatches. For example, if both serializer and deserializer unexpectedly rename a property, the test may still pass. For key public API fields, keep JSON fixtures written to reflect the contract seen by clients:

~~~json
{
  "sku": "COFFEE-01",
  "quantity": 2,
  "deliveryDate": "2026-11-20",
  "note": null
}
~~~

Fixtures lock down field names, data types, and wire representation. You can place fixtures in `src/test/resources/http/requests/` and load them as classpath resources so multiple tests reuse the same input examples. When the contract changes intentionally, update the fixtures alongside API documentation and affected clients.

## 3. Choosing JSON Data That Reflects Exact Data Types

JSON has its own data types. Values that look similar in Java may not look the same over HTTP:

~~~json
{
  "quantity": 2,
  "unitPrice": 125000.50,
  "enabled": true,
  "sku": "000123",
  "note": null,
  "tags": ["gift", "fragile"]
}
~~~

- `quantity` is a number, not the string `"2"`.
- `unitPrice` is a number. For currency, the application should define explicit types and rounding rules; avoid comparing binary floating-point numbers with exact equality when decimal precision matters.
- `enabled` is a boolean, not `"true"`.
- `sku` is a string so leading zeros are preserved. Do not turn identifiers into numbers just because they contain digits.
- `note: null` differs from omitting the `note` field altogether. Depending on Jackson policy and the DTO, the two cases can be handled differently.
- `tags` is an array. If element order is significant, tests should preserve and assert that order.

For dates and times, use the format published by the API. For example:

~~~json
{
  "deliveryDate": "2026-11-20",
  "createdAt": "2026-11-13T02:30:00Z",
  "requestedAt": "2026-11-13T09:30:00+07:00"
}
~~~

`LocalDate` is typically represented as an ISO date such as `2026-11-20`. Instants requiring a timezone should include `Z` or an explicit offset. Do not use locale-dependent date strings like `11/20/2026` unless the API contract explicitly requires that format. Avoid relying on the test runner's default timezone because CI and developer machines may differ.

For enums, send the exact published wire value, such as `"PENDING"` or `"PAID"`. Do not assume clients can send a Java enum's numeric ordinal. If the API supports aliases or lowercase values, test each supported form and explicitly reject invalid values.

## 4. Putting Query Parameters and Path Variables in the Right Place

Suppose order lookup endpoints look like:

~~~text
GET /api/orders?status=PAID&page=0&size=20
GET /api/orders/{orderId}
~~~

Query parameters belong to the URL. You can use `queryParam` on the MockMvc request builder:

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("status", "PAID")
        .queryParam("page", "0")
        .queryParam("size", "20")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page").value(0));
~~~

Path variables must live in the path:

~~~java
UUID orderId = UUID.fromString(
        "4c6d8e10-1234-4567-8901-123456789abc");

mockMvc.perform(get("/api/orders/{orderId}", orderId)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()));
~~~

Do not turn a path variable into a query parameter simply because the controller ends up receiving a string. These two URLs represent two different contracts:

~~~text
/api/orders/4c6d8e10-1234-4567-8901-123456789abc
/api/orders?id=4c6d8e10-1234-4567-8901-123456789abc
~~~

If a query contains special characters such as spaces, plus signs, ampersands, or Unicode characters, verify encoding behavior. For instance, the search term `tea & coffee` must not be concatenated raw into the URL without encoding, because `&` separates query parameters. You can build the URI with `UriComponentsBuilder`:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/api/products")
        .queryParam("q", "{keyword}")
        .encode()
        .buildAndExpand("tea & coffee")
        .toUri();

mockMvc.perform(get(uri)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

When an API accepts multiple values for the same query key, pass multiple values rather than joining them into an arbitrary string:

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("status", "PAID", "SHIPPED")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

Only use commas as delimiters if the endpoint contract explicitly specifies CSV format. Just because Spring binds a list from query parameters does not automatically mean every client should send the same string format.

## 5. Distinguishing JSON Bodies from Form Parameters

JSON bodies and form parameters are two distinct ways of sending data.

JSON typically uses:

~~~http
POST /api/orders
Content-Type: application/json

{"sku":"COFFEE-01","quantity":2}
~~~

URL-encoded forms typically use:

~~~http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&remember-me=true
~~~

For forms, use `param(...)` and the matching content type:

~~~java
mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("username", "alice")
        .param("password", "correct-horse")
        .param("remember-me", "true"))
    .andExpect(status().is3xxRedirection());
~~~

Do not use `param(...)` to simulate a JSON body. Conversely, do not pass a JSON string in `content(...)` if the controller is designed to bind form fields via `@RequestParam` or `@ModelAttribute`.

For repeated fields, pass multiple values under the same name:

~~~java
mockMvc.perform(post("/preferences")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("categories", "books", "music", "travel"))
    .andExpect(status().isOk());
~~~

For forms with checkboxes, model how browsers actually send data. An unchecked checkbox usually omits its field entirely; a checked checkbox usually sends its value. Tests should cover both the absent-field and present-field cases if server logic depends on that distinction.

## 6. Sending Headers According to the Client's Role

Headers are part of the request contract. Common headers include:

- `Accept`: response format the client wants to receive.
- `Content-Type`: format of the body the client is sending.
- `Authorization`: authentication credentials per the API scheme.
- `If-Match` or `If-None-Match`: preconditions based on entity tags.
- `If-Modified-Since`: precondition based on last modification time.
- `Accept-Language`: client's preferred language.
- `Idempotency-Key`: key preventing duplicate processing when defined by the API.
- `X-Correlation-ID` or `traceparent`: log/tracing correlation metadata per system contract.

Example:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("Idempotency-Key", "order-request-2026-0001")
        .header("Accept-Language", "vi-VN")
        .header("X-Correlation-ID", "test-correlation-001")
        .content("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2,
                  "deliveryDate": "2026-11-20"
                }
                """))
    .andExpect(status().isCreated());
~~~

Protocol-level headers should be tested via the actual header. Do not move a token into the JSON body if the API requires `Authorization`. Do not substitute query parameters for headers just to make tests shorter.

If an endpoint requires a bearer token and the goal is to test the filter chain or authentication filter, send a properly formatted `Authorization` header:

~~~java
mockMvc.perform(get("/api/me")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

When using Spring Security test support such as `with(user("alice"))`, the test populates a principal in the test request's `SecurityContext`. This is useful for testing authorization at the MVC layer, yet it does not test reading and verifying a bearer token from the HTTP header. Choose the setup suited to the exact layer under test.

In applications with CSRF protection enabled, state-changing requests may require a CSRF token:

~~~java
mockMvc.perform(post("/web/orders")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"sku":"COFFEE-01","quantity":2}
                """))
    .andExpect(status().isCreated());
~~~

Add a CSRF token only when the request falls under the application's CSRF protection mechanism. If a test needs to prove that a request missing a token is rejected, write a separate case without `csrf()` and verify the expected status.

## 7. Cookies and Sessions

Cookies are sent by the client in the `Cookie` request header. With MockMvc, use `cookie(...)`:

~~~java
mockMvc.perform(get("/web/cart")
        .cookie(new Cookie("cart-id", "cart-001"))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

A session is server-side state bound to a session identifier. You can set session attributes to test controllers that depend on the session:

~~~java
MockHttpSession session = new MockHttpSession();
session.setAttribute("selectedStore", "store-hcm-01");

mockMvc.perform(get("/web/checkout")
        .session(session))
    .andExpect(status().isOk());
~~~

Cookies and sessions are related, not identical. When testing session creation or writing cookies to the response, perform the first request, extract the cookie/session from the result, and pass it into the next request. Do not simply pre-populate a session attribute if the goal is to verify that the application creates the session and issues the cookie properly.

## 8. Uploading Files with Multipart

An upload request normally has content type `multipart/form-data` with a client-generated boundary. Use `multipart(...)` and `MockMultipartFile`:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "invoice.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "%PDF-1.7 test content".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file)
        .param("documentType", "INVOICE")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated());
~~~

The part name `"file"` must match the parameter name expected by the controller, such as `@RequestPart("file")` or `@RequestParam("file")`. Filename, content type, and bytes can all affect server-side validation or processing.

Do not manually set a `Content-Type: multipart/form-data` header lacking a boundary. MockMvc's multipart request builder constructs a valid multipart request for the mock environment. If the endpoint also accepts a JSON part, create a separate part with JSON content type:

~~~java
MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {"documentType":"INVOICE","reference":"INV-2026-001"}
        """.getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated());
~~~

For uploads, include cases for empty files, wrong content types, incorrect part names, size-limit violations, missing metadata, and valid files. Limits enforced by a reverse proxy or real Servlet container may require dedicated integration tests.

## 9. Organizing JSON Fixtures and Shared Test Data

JSON fixtures are useful when requests have many fields or when maintaining a stable contract across code changes. They can be organized as:

~~~text
src/test/resources/
└── http/
    └── requests/
        ├── create-order-valid.json
        ├── create-order-missing-sku.json
        └── create-order-invalid-date.json
~~~

Load fixtures as classpath resources:

~~~java
private String readRequestFixture(String name) throws IOException {
    ClassPathResource resource =
            new ClassPathResource("http/requests/" + name);
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Use the fixture in tests:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(readRequestFixture("create-order-valid.json")))
    .andExpect(status().isCreated());
~~~

Fixture names should express their intent, such as `valid`, `missing-sku`, or `invalid-date`. Avoid creating one huge JSON file shared by all tests and mutating it with repeated string replacements; that makes tests hard to read and risks altering unrelated fields.

For fields that vary per test such as timestamps, UUIDs, or quantities, you can use `ObjectMapper` to serialize dynamic data or build JSON with `ObjectNode`. Still, keep contract-critical fields explicit. For instance, if the property name `deliveryDate` is part of what needs verification, the fixture should spell out that exact name rather than letting a DTO generate it implicitly.

Helpers such as `performJsonPost(...)` can reduce repetition:

~~~java
private ResultActions performJsonPost(String path, String body)
        throws Exception {
    return mockMvc.perform(post(path)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content(body));
}
~~~

Helpers should encapsulate only details genuinely shared across tests. If a helper silently attaches headers, tokens, query parameters, or default body fields that the test does not show, readers cannot tell what request was actually sent. Keep key contract parts visible in the test or pass them into the helper explicitly.

## 10. Testing Valid and Invalid Data

A request contract covers both accepted data and rejected data. For JSON bodies, test cases such as:

- Valid body with all required fields.
- Missing required field.
- Field with `null` value.
- Empty or whitespace-only string.
- Negative, zero, or out-of-range numbers.
- Wrong data type, e.g., sending `"quantity": "two"`.
- Malformed or invalid dates.
- Unsupported enum values.
- Unknown fields when the API policy requires rejecting unrecognized fields.
- Empty body, syntactically invalid JSON, or unsupported content type.

Example testing validation errors:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "",
                  "quantity": 0,
                  "deliveryDate": "2026-11-20"
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.errors").isArray());
~~~

Status codes and error structures must follow the application's actual contract. Do not assume every binding error returns 400 if the application has a custom exception handler. Verify the response status, content type, error codes, and field paths clients rely on to display errors.

For query parameters, test missing values, wrong types, pagination bounds, repeated values for the same key, and characters needing encoding. For headers, test missing required headers, invalid values, and repeated-header handling if specified by the endpoint.

## 11. A Complete Test from the HTTP Client Perspective

The example below illustrates a request with method, path, query parameter, header, JSON body, and response assertions:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderFromHttpRequest() throws Exception {
        UUID orderId = UUID.fromString(
                "4c6d8e10-1234-4567-8901-123456789abc");

        given(orderService.create(any(CreateOrderRequest.class)))
                .willReturn(new OrderResponse(
                        orderId, "COFFEE-01", "CREATED"));

        mockMvc.perform(post("/api/orders")
                        .queryParam("source", "mobile")
                        .header("Idempotency-Key", "mobile-order-001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "COFFEE-01",
                                  "quantity": 2,
                                  "deliveryDate": "2026-11-20",
                                  "note": null
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        "/api/orders/" + orderId))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(orderId.toString()))
                .andExpect(jsonPath("$.sku").value("COFFEE-01"))
                .andExpect(jsonPath("$.status").value("CREATED"));

        then(orderService).should().create(argThat(request ->
                request.sku().equals("COFFEE-01")
                        && request.quantity() == 2
                        && request.deliveryDate().equals(
                                LocalDate.of(2026, 11, 20))));
    }
}
~~~

This is an illustrative example; DTO, response, service names, and error structures must match your specific application. What matters is that the test sends the request in the shape a client uses and asserts both the HTTP response and the data bound into the business layer.

Do not merely verify that a mocked service was called with any arbitrary object. If a test uses `any()` for the entire request without asserting fields, binding bugs such as wrong JSON property names or misparsed dates can go undetected.

## 12. Limits of MockMvc and When Real HTTP Tests Are Needed

MockMvc invokes Spring MVC through a mock Servlet environment. It tests many important behaviors such as mapping, argument resolvers, message converters, validation, controller advice, and filters wired into the test context. However, MockMvc does not open sockets or transmit bytes over a network stack like a real HTTP client.

Accordingly, MockMvc is ideal for verifying contracts at the Spring MVC boundary, yet it does not replace all HTTP integration tests. Consider running the application on a random port and using `TestRestTemplate`, `WebTestClient`, or an appropriate HTTP client when you need to verify:

- Real interactions with the Servlet container or embedded server.
- Connector settings, header/body limits, and how the container parses requests.
- Behavior across reverse proxies, TLS, or the network.
- CORS configuration, compression, or server-specific characteristics.
- Container-level multipart uploads and real size limits.
- Client/server interoperability with a specific HTTP client.

You do not need to move every controller test to real HTTP. Use MockMvc for most fast, focused MVC tests; add a targeted set of integration tests for differences that only appear when running a real server.

## 13. Common Mistakes When Constructing MockMvc Requests

| Error-prone pattern | Issue | Proper representation |
|---|---|---|
| Passing a DTO directly to `content(...)` | `content` expects a string or byte body | Serialize to JSON or use a fixture |
| Sending JSON without `Content-Type` | Message converter may fail to select the right format | Set `contentType(APPLICATION_JSON)` |
| Using `Accept` instead of `Content-Type` | Confuses response format with request body format | Declare both separately when needed |
| Using `param` to simulate JSON | Test goes through request parameters instead of JSON converter | Use `content` with a JSON body |
| Putting a path variable in the query string | Request diverges from the endpoint contract | Place the value in the URI path |
| Concatenating query strings with `+` | Can corrupt special characters or encode improperly | Use `queryParam` or a URI builder |
| Sending identifiers with leading zeros as numbers | Loses identifier formatting | Send as a JSON string |
| Using locale-dependent dates | Results can differ across environments | Send the published ISO format |
| Manually setting multipart content type without a boundary | Multipart request lacks part-separation metadata | Use `multipart` and `MockMultipartFile` |
| Using a fake principal to conclude tokens work | Does not verify reading and validating the Authorization header | Send the token via header in filter/auth tests |
| Verifying only that the service mock was called | Misses binding errors or wrong data | Verify bound fields and HTTP response |

## 14. Principles for Designing Maintainable Request Tests

When adding a MockMvc test, define the request a client will send before writing Java test code. Then place each part of the request in its proper location:

1. Use the exact HTTP method and path.
2. Put resource identifiers in the path if the contract specifies path variables.
3. Put filters, pagination, and options in query parameters.
4. Declare `Accept`, `Content-Type`, and required business headers.
5. Send the body in the proper format: JSON, form, or multipart.
6. Choose sample data representing real wire types, including dates/times, enums, nulls, and identifiers.
7. Assert response status, headers, content type, and body.
8. Assert data bound into the controller/service when doing so helps catch contract drift.

A good test helps readers picture which request the client sends and what the server promises to return. When the HTTP contract is stated clearly in tests, changes to DTOs, Jackson configuration, validation, or controller mappings yield concrete evidence revealing their impact on clients.
