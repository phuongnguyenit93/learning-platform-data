# Content Type, Charset, and Body Data

## 1. Three Parts to Verify in an HTTP Message

When testing Spring MVC, a request or response can be examined across three related yet distinct aspects:

- **Content type** specifies the format of the body, such as `application/json`, `text/plain`, or `application/xml`.
- **Charset** specifies how characters and bytes are converted for text content, such as `UTF-8`.
- **Body** is the actual data sent or returned: plain text, JSON, XML, an image, a file, or another byte sequence.

A response can return valid JSON while declaring the wrong `Content-Type`. A response can declare `text/plain;charset=UTF-8` while its body was encoded into bytes using a different charset. A test that checks only the status code will miss these bugs.

In Spring MVC, `MockMvc` lets you verify all three parts using matchers from `MockMvcResultMatchers.content()` and header matchers.

## 2. Distinguishing Content-Type and Accept

These two headers often appear together but describe opposite directions:

| Header | Direction | Meaning |
|---|---|---|
| `Content-Type` | Request or response | The format in which the current body is represented |
| `Accept` | Request | The format the client wants the server to return |

Example where the client sends JSON and asks the server to return JSON:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"productCode":"BOOK-01","quantity":2}
```

`Content-Type: application/json` describes the request body so Spring can choose how to read the data, typically via an `HttpMessageConverter`. `Accept: application/json` expresses the response format the client accepts.

On the response side, the server might return:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"...","status":"CREATED"}
```

`Content-Type` in the response describes the body that the server actually sends. It is not a mechanical copy of `Accept`; the server selects a representation based on the mapping, available converters, and content negotiation.

In Spring MVC, two mapping attributes help constrain this contract:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse(
                UUID.randomUUID(), request.productCode(), "CREATED");
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

`consumes` restricts the media types that the endpoint accepts for the request body. `produces` restricts the media types that the endpoint can produce for the response. When a request does not satisfy `consumes`, Spring typically returns `415 Unsupported Media Type`. When a client requests a response type incompatible with `produces`, Spring typically returns `406 Not Acceptable`.

## 3. Verifying Response Content-Type with MockMvc

The `content().contentType(...)` matcher checks the response media type against the expected value, including parameters. The `content().contentTypeCompatibleWith(...)` matcher checks media type compatibility, which is suitable when parameters such as `charset` may vary.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsJsonForCreateOrder() throws Exception {
        String requestBody = """
                {
                  "productCode": "BOOK-01",
                  "quantity": 2
                }
                """;

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestBody))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
    }
}
```

The example above confirms the response is JSON without forcing the test to depend on whether the server adds parameters. If the API contract requires a media type with a specific parameter, you can check it strictly:

```java
.andExpect(content().contentType(
        MediaType.parseMediaType("text/plain;charset=UTF-8")))
```

Avoid using the exact matcher if parameters are not part of the contract. For example, a test that only needs to verify a JSON response should usually use `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`.

You can also inspect the header directly with `header()`:

```java
.andExpect(header().string(
        HttpHeaders.CONTENT_TYPE,
        startsWith(MediaType.APPLICATION_JSON_VALUE)))
```

However, when the goal is to verify the media type, the `contentType` matcher expresses intent more clearly than manual header string matching.

## 4. Verifying Charset for Text Content

Charset matters when the body contains text. The same characters can be encoded into different byte sequences depending on the charset. If the sender and receiver use different encodings, text can suffer corrupted accents/diacritics or turn into unexpected characters.

A text response can declare its charset directly in `Content-Type`:

```http
Content-Type: text/plain;charset=UTF-8
```

In a controller, you can produce a response with a media type explicitly specifying UTF-8:

```java
@GetMapping(value = "/greeting", produces = "text/plain;charset=UTF-8")
public ResponseEntity<String> greeting() {
    return ResponseEntity.ok()
            .contentType(new MediaType(
                    "text", "plain", StandardCharsets.UTF_8))
            .body("Xin chào Spring MVC");
}
```

The test can verify both the media type and the charset:

```java
@Test
void returnsUtf8Text() throws Exception {
    mockMvc.perform(get("/greeting"))
            .andExpect(status().isOk())
            .andExpect(content().contentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)))
            .andExpect(content().encoding(StandardCharsets.UTF_8))
            .andExpect(content().string("Xin chào Spring MVC"));
}
```

`content().encoding(...)` checks the encoding declared on the response for its content. `content().string(...)` checks the body after reading it as a string. When an endpoint contract requires UTF-8, asserting both catches mismatches between the header and the actual content.

Do not assume that every JSON response must include a `charset=UTF-8` parameter in its header. JSON is exchanged across systems in UTF-8; Spring's JSON converters typically write JSON as UTF-8 and may return `Content-Type: application/json` without adding a charset parameter. Therefore, check JSON media type by compatibility and verify content by JSON structure. Only assert `content().encoding(...)` when the charset is explicitly advertised by the endpoint or is part of a contract you need to protect.

## 5. Sending Request Bodies with a Specific Charset

For text requests, the client needs to encode the body into bytes using a charset the server understands. You can pass `Content-Type` with a charset and configure the request encoding in MockMvc:

```java
@Test
void acceptsUtf8PlainText() throws Exception {
    byte[] body = "Xin chào Nguyễn An".getBytes(StandardCharsets.UTF_8);

    mockMvc.perform(post("/api/messages")
                    .contentType(new MediaType(
                            "text", "plain", StandardCharsets.UTF_8))
                    .characterEncoding(StandardCharsets.UTF_8.name())
                    .content(body))
            .andExpect(status().isCreated());
}
```

`content(byte[])` sends the exact byte sequence created. This is a clear way for a test to control request encoding precisely. `characterEncoding(...)` sets the encoding on the mock request; the charset in the media type also describes the encoding of the text body. The two values should match.

For JSON, generate bytes in UTF-8 and declare `application/json`:

```java
String json = """
        {"name":"Nguyễn An","city":"Hồ Chí Minh"}
        """;

mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json.getBytes(StandardCharsets.UTF_8)))
        .andExpect(status().isCreated());
```

There is no need to append `charset=UTF-8` to `application/json` just to prove the request uses UTF-8. Ensure the bytes are encoded in UTF-8 and let the JSON converter handle JSON according to the format rules.

If you use `.content(String)`, converting the string to bytes depends on the mock request's encoding and configured charset. When a test focuses on exact bytes or non-ASCII characters, `.content(byte[])` removes ambiguity about the test-side encoding step.

## 6. Choosing the Right Matcher for the Body Type

`MockMvcResultMatchers.content()` provides multiple ways to assert the body. Choose a matcher based on the data structure committed to by the endpoint.

| Matcher | Purpose | When to Use |
|---|---|---|
| `content().string(...)` | Compare body as a string | Plain text, HTML content, or content requiring verbatim comparison |
| `content().bytes(...)` | Compare a byte sequence | Images, PDFs, file downloads, or binary content |
| `content().json(...)` | Compare JSON content | Verify JSON independent of whitespace and formatting |
| `content().xml(...)` | Compare XML content | Verify XML responses |
| `jsonPath(...)` | Verify a subset of JSON data | Assert fields, values, data types, or required structure |

### 6.1. Comparing Text with `string()`

```java
mockMvc.perform(get("/greeting"))
        .andExpect(status().isOk())
        .andExpect(content().string("Xin chào Spring MVC"));
```

This matcher compares the string content, so spaces, line breaks, and characters can all affect the result. Use it when the exact text content is part of the contract.

### 6.2. Comparing Bytes with `bytes()`

```java
byte[] expected = Files.readAllBytes(
        Path.of("src/test/resources/sample-image.png"));

mockMvc.perform(get("/files/sample-image"))
        .andExpect(status().isOk())
        .andExpect(content().contentType(MediaType.IMAGE_PNG))
        .andExpect(content().bytes(expected));
```

For binary data, never convert bytes into a `String` for comparison. Arbitrary decoding can alter or corrupt the data. Checking bytes directly preserves the exact content to be verified.

### 6.3. Comparing JSON with `json()`

```java
String expectedJson = """
        {
          "productCode": "BOOK-01",
          "quantity": 2,
          "status": "CREATED"
        }
        """;

mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .andExpect(status().isCreated())
        .andExpect(content().json(expectedJson));
```

Structural JSON comparison avoids depending on whitespace, indentation, or formatting style. Matcher overloads let you choose the comparison mode; if array element order or the exact set of fields is required, select the appropriate mode and write the test to express that requirement.

### 6.4. Verifying Fields with `jsonPath()`

```java
mockMvc.perform(get("/api/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(2));
```

`jsonPath()` is ideal when only part of the response matters to the test. It keeps the test focused on the contract being protected rather than copying an entire sample payload. If you need to verify every field or the overall JSON structure, combine it with `content().json(...)`.

## 7. Testing Content Negotiation and Media Type Errors

Content negotiation is the process by which Spring selects a representation matching the request, especially the `Accept` header and `produces` declarations.

Example endpoint returning only JSON:

```java
@GetMapping(value = "/api/orders/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse find(@PathVariable UUID id) {
    return orderService.find(id);
}
```

Test case where the client accepts JSON:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
```

Test case where the client requests a format not provided by the endpoint:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaType.TEXT_PLAIN))
        .andExpect(status().isNotAcceptable());
```

This is `406 Not Acceptable`: the server could not find a representation matching the formats accepted by the client.

For the request body, an endpoint may accept only JSON:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Void> create(@RequestBody CreateOrderRequest request) {
    orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Test sending an incompatible media type:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .content("productCode=BOOK-01"))
        .andExpect(status().isUnsupportedMediaType());
```

This is `415 Unsupported Media Type`: the endpoint does not accept the media type of the incoming request body. Distinguish `406` from `415`: `406` concerns the response format accepted by the client; `415` concerns the request body format accepted by the server.

## 8. Verifying Empty Responses and Responses Without a Body

Not every endpoint returns a body. For example, a delete operation may return `204 No Content`:

```java
@DeleteMapping("/api/orders/{id}")
public ResponseEntity<Void> delete(@PathVariable UUID id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
```

The test should verify the status and empty body:

```java
mockMvc.perform(delete("/api/orders/{id}", orderId))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

For responses without a representation, do not force the test to require `Content-Type` if the endpoint contract does not demand it. `Content-Type` describes the representation of the body; a response without a body does not need to declare a content type.

## 9. A Complete Test Example for JSON Requests and Responses

The following example combines status, request media type, response media type, and body content:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createsCustomerAndReturnsJson() throws Exception {
        String requestJson = """
                {
                  "name": "Nguyễn An",
                  "email": "an@example.com"
                }
                """;

        mockMvc.perform(post("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestJson.getBytes(StandardCharsets.UTF_8)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.name").value("Nguyễn An"))
                .andExpect(jsonPath("$.email").value("an@example.com"))
                .andExpect(jsonPath("$.id").isNotEmpty());
    }
}
```

This test verifies Vietnamese data passing through the request as UTF-8 bytes, while asserting that the response is JSON and key fields have the expected values. It does not require the JSON response to carry a `charset` parameter, because that parameter is unnecessary for determining UTF-8 encoding in JSON.

## 10. Common Mistakes When Verifying Content Type, Charset, and Body

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JSON test fails because `Content-Type` differs from expected string | Response has parameters or a compatible media type that is not strictly equal | Use `contentTypeCompatibleWith()` when parameters are not part of the contract |
| Request returns `415` | `Content-Type` does not match `consumes`, or no converter can read that body | Check media type, converters, and mapping `consumes` |
| Request returns `406` | `Accept` is incompatible with `produces` or available representations | Send an appropriate `Accept` header or adjust endpoint representations |
| Vietnamese diacritics are corrupted | Bytes were encoded and decoded using different charsets | Verify request/response charsets and encode bytes using the same charset |
| JSON matcher fails even though data looks right | Field, data type, or JSON structure differs from expectation | Use `jsonPath()` to pinpoint the wrong field or compare JSON against a clear expected body |
| String comparison fails due to line breaks or whitespace | `content().string()` compares exact string content | Use JSON/XML matchers for structured data; compare verbatim only when required |
| Binary body is corrupted when converted to String | Data is non-text or decoded with an arbitrary charset | Use `content().bytes(...)` |
| Test sees no body despite right status | Endpoint intentionally returns `204`, a redirect, or a response without a representation | Confirm the endpoint contract and assert appropriate status/headers |

When diagnosing failures, check step by step: whether the request sends the right `Content-Type`, whether `Accept` is appropriate, what `consumes`/`produces` the controller mapping declares, which converter handles the body, and whether the matcher checks the representation or decoded data.

## 11. Choosing Assertions Based on the API Contract

- For JSON: verify `contentTypeCompatibleWith(APPLICATION_JSON)` and use `json()` or `jsonPath()` to assert the body.
- For text with an explicitly specified charset: verify the media type, `encoding()`, and content using `string()`.
- For binary data: verify the media type and compare bytes using `bytes()`.
- For request bodies: set `contentType(...)`; set `accept(...)` when testing content negotiation.
- For endpoints with `consumes` or `produces`: test both valid cases and `415`/`406` errors when that behavior is part of the contract.
- For responses without a body: focus on status and meaningful headers; do not add content type assertions if the response has no representation.

Verifying content type, charset, and body ensures MVC tests confirm that responses are in a format clients can process, while guaranteeing text and binary data are transmitted properly. When matchers accurately reflect the endpoint contract, tests catch bugs across representation selection, character encoding, and data conversion.
