# JSON, XML, and Binary Request Bodies

## 1. Request Bodies in MockMvc

When testing an endpoint that accepts data in the HTTP request body, MockMvc allows setting the body content directly on the request built by `MockHttpServletRequestBuilder`. Two commonly used methods are:

- `content(String)`: passes string content, suited for JSON or XML written inline in the test.
- `content(byte[])`: passes a byte array, suited for already-serialized data or binary payloads such as images, files, and custom protocol data.

A request with a body usually needs to declare `Content-Type` so Spring MVC knows the format of the incoming data. The desired response format can be declared via the `Accept` header.

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {"customerId":"C-100","quantity":2}
                """))
    .andExpect(status().isCreated());
```

In this example, `Content-Type` describes the request body; `Accept` describes the content type the client wants to receive in the response. The two headers serve different purposes. If the endpoint accepts only JSON but the test sends `application/xml`, Spring MVC can return `415 Unsupported Media Type`. If the endpoint cannot produce a response matching the type requested by `Accept`, the result can be `406 Not Acceptable`.

The examples in this article assume `mockMvc` is already configured. It can be obtained from `@AutoConfigureMockMvc` in Spring Boot tests, from `MockMvcBuilders.webAppContextSetup(...)`, or built with `MockMvcBuilders.standaloneSetup(...)` when testing a single controller.

## 2. Sending a JSON Body

JSON is a common format for HTTP APIs. Spring MVC controllers typically receive JSON with `@RequestBody`; an `HttpMessageConverter` reads the request bytes and converts the JSON into a Java object.

Example of an endpoint receiving an order creation request:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse("O-100", request.customerId());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record CreateOrderRequest(String customerId, int quantity) {}

record OrderResponse(String orderId, String customerId) {}
```

You can send a JSON literal to control the exact wire format content:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "customerId": "C-100",
                  "quantity": 2
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value("O-100"))
    .andExpect(jsonPath("$.customerId").value("C-100"));
```

`jsonPath` verifies the structure and values in the JSON response. The expression `$.orderId` navigates from the root element to the `orderId` property. You can verify array elements, numeric values, booleans, nested properties, or field existence using the corresponding JSONPath expressions.

If a request DTO already exists, the test can also use the application's `ObjectMapper` to serialize the object:

```java
CreateOrderRequest request = new CreateOrderRequest("C-100", 2);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(objectMapper.writeValueAsBytes(request)))
    .andExpect(status().isCreated());
```

`writeValueAsBytes` produces a UTF-8 byte array suitable for passing to `content(byte[])`. Using the `ObjectMapper` configured in the application context ensures the test follows the application's serializer settings such as naming strategies, custom modules, and date-time formatting. When you want to check exact field names, data types, or the payload an actual client sends, a JSON literal often makes the test's intent clearer.

Declare `Content-Type` explicitly in tests. If the body lacks a content type matching the `consumes` mapping or a converter capable of reading the target Java type, the request may not be processed as expected.

## 3. Sending an XML Body

MockMvc sends XML in a similar way to JSON: set `Content-Type` to `application/xml` and pass the XML content via `content(...)`. To guarantee consistent encoding, convert the string to UTF-8 bytes explicitly.

```java
import java.nio.charset.StandardCharsets;

String xml = """
        <order>
            <customerId>C-100</customerId>
            <quantity>2</quantity>
        </order>
        """;

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content(xml.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_XML));
```

If the controller accepts `@RequestBody String`, Spring can convert the body into a string for the application to handle manually. If the controller accepts a Java DTO, the application needs an `HttpMessageConverter` that supports XML and that DTO type. For example, `MappingJackson2XmlHttpMessageConverter` uses Jackson XML; the `jackson-dataformat-xml` library must be on the classpath and the converter must be registered in the MVC configuration. Spring Boot can auto-configure the corresponding converter when this dependency is present. Another option is a JAXB-based converter if the application already uses JAXB.

Example mapping XML to a DTO with Jackson XML:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class XmlOrderRequest {

    private String customerId;
    private int quantity;

    public XmlOrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

The controller can declare:

```java
@PostMapping(path = "/api/orders/xml",
             consumes = MediaType.APPLICATION_XML_VALUE,
             produces = MediaType.APPLICATION_XML_VALUE)
ResponseEntity<XmlOrderResponse> createXml(@RequestBody XmlOrderRequest request) {
    // Process the request and return the response DTO.
}
```

In the test, the same XML literal above can be used. The converter reads the XML elements and assigns them to the DTO properties. If you want to build the body from an object, use Jackson XML's `XmlMapper`:

```java
XmlMapper xmlMapper = new XmlMapper();
XmlOrderRequest request = new XmlOrderRequest();
request.setCustomerId("C-100");
request.setQuantity(2);

byte[] body = xmlMapper.writeValueAsBytes(request);

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .content(body))
    .andExpect(status().isOk());
```

In real applications, prefer using the already-configured `XmlMapper` or the application's serializer bean if custom modules or naming rules exist. A test constructing a default `XmlMapper` might generate a payload different from production configuration.

You can verify an XML response using XPath matchers:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content(xml.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(xpath("/receipt/orderId").string("O-100"));
```

XPath inspects XML content by element structure. If the XML uses namespaces, the expression and the matcher's namespace configuration must reflect those namespaces; a path without namespaces may fail to locate elements even when the response contains data.

## 4. Sending Binary Content

For binary bodies, do not convert data into a `String`, because the conversion can alter bytes, especially for non-text data or sequences containing invalid bytes under an encoding. Pass `byte[]` directly to `content(byte[])`.

Example of an endpoint accepting binary data:

```java
@RestController
class ImportController {

    @PostMapping(path = "/api/import",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    ResponseEntity<Void> importData(@RequestBody byte[] payload) {
        // Process the binary payload.
        return ResponseEntity.accepted().build();
    }
}
```

The test sends the byte array directly:

```java
byte[] payload = new byte[] {
        0x00, 0x01, 0x02, (byte) 0x80, (byte) 0xFF
};

mockMvc.perform(post("/api/import")
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .content(payload))
    .andExpect(status().isAccepted());
```

`MediaType.APPLICATION_OCTET_STREAM` represents generic binary data. If the API expects a specific format, such as PDF or PNG, use the corresponding media type when the API contract specifies it. This header helps the endpoint and converter identify what kind of payload is being sent.

### Verifying Binary Responses

A file-download endpoint might return `ResponseEntity<byte[]>` or an appropriate resource type. Tests should compare actual bytes instead of converting the response to a string:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

byte[] expected = new byte[] { 0x10, 0x20, (byte) 0xFE };

MvcResult result = mockMvc.perform(get("/api/export")
        .accept(MediaType.APPLICATION_OCTET_STREAM))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_OCTET_STREAM))
    .andReturn();

assertArrayEquals(expected, result.getResponse().getContentAsByteArray());
```

`getContentAsByteArray()` preserves the raw response bytes. `assertArrayEquals` verifies both length and each byte in exact order. You can use `content().bytes(expected)` inside the `andExpect` chain if you want to write the assertion directly on the MockMvc result.

## 5. Distinguishing Raw Body and Multipart Upload

A request with a binary body is not the same as a multipart upload request. `application/octet-stream` usually sends a single binary payload. `multipart/form-data` splits the request into multiple parts—for example, one part as a file and another part as a description or metadata.

For multipart, use the `multipart(...)` request builder and `MockMultipartFile`:

```java
import org.springframework.mock.web.MockMultipartFile;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

byte[] fileBytes = new byte[] { 0x01, 0x02, (byte) 0xFF };
MockMultipartFile file = new MockMultipartFile(
        "file", "sample.bin", "application/octet-stream", fileBytes);

mockMvc.perform(multipart("/api/files")
        .file(file)
        .param("description", "sample payload"))
    .andExpect(status().isOk());
```

Multipart controllers typically receive `MultipartFile` via `@RequestParam` or `@RequestPart`, depending on the endpoint contract. Do not use `.content(fileBytes)` to simulate multipart if the controller actually expects named parts.

## 6. Content-Type, Accept, and Message Converters

Spring MVC uses `HttpMessageConverter` to convert between HTTP bodies and Java types. The converter is selected based on the parameter or return type, the media type, and the registered converters.

| Component | Meaning in request tests | Example |
|---|---|---|
| `contentType(...)` | Indicates the format of the body sent to the server. | `APPLICATION_JSON`, `APPLICATION_XML`, `APPLICATION_OCTET_STREAM` |
| `accept(...)` | Indicates which response formats the client accepts. | `APPLICATION_JSON`, `APPLICATION_XML` |
| `content(String)` | Sets a text-based body. | JSON literal, XML literal |
| `content(byte[])` | Sets the body as bytes. | Serialized JSON/XML, images, PDFs, binary payloads |
| `jsonPath(...)` | Verifies a JSON response. | `$.data.id` |
| `xpath(...)` | Verifies an XML response. | `/receipt/orderId` |
| `getContentAsByteArray()` | Retrieves raw response bytes. | Comparing file content |

`Content-Type` does not transform the body by itself. If you send a JSON string while declaring `text/plain`, the server will process the request under that media type; the JSON converter may not be selected. Similarly, `Accept` does not alter the request body, but influences how Spring chooses a response representation.

For JSON, Spring MVC typically uses `MappingJackson2HttpMessageConverter` when Jackson is present. For XML, an appropriate XML converter such as Jackson XML or JAXB is needed. For `byte[]`, Spring has a converter supporting byte arrays. If using `standaloneSetup`, make sure the required converters are registered; the full MVC configuration in an application context can differ from a standalone controller setup.

## 7. Common Errors When Sending Bodies

| HTTP status or symptom | Common cause | What to check |
|---|---|---|
| `415 Unsupported Media Type` | `Content-Type` is not in `consumes`, or no converter can read the media type and parameter type. | Check `contentType(...)`, `consumes`, and registered converters. |
| `400 Bad Request` with JSON | Malformed JSON syntax, data type mismatch with DTO, empty body, or body read failure. | Check payload, field names, field types, and exception logs such as `HttpMessageNotReadableException`. |
| `400 Bad Request` with XML | Invalid XML, mismatched structure, or converter cannot deserialize DTO. | Check well-formed XML, root element, namespaces, and XML converter configuration. |
| `406 Not Acceptable` | Response has no representation matching `Accept`. | Check `accept(...)`, `produces`, and response-writing converters. |
| JSON assertion cannot find field | JSON response structure differs from JSONPath expression or response is not JSON. | Check status, Content-Type, and actual response content. |
| XPath cannot find element | Wrong XPath path or XML uses namespaces not handled in the matcher. | Inspect actual XML response and configure appropriate namespaces. |
| Response bytes differ from expected | Data converted through `String`, encoded/decoded unintentionally, or wrong expected content. | Send and read as `byte[]`; compare with `assertArrayEquals`. |
| POST returns `403 Forbidden` in a Spring Security app | CSRF protection is enabled and the test request lacks a valid CSRF token. | If the endpoint requires CSRF, use the `csrf()` request post-processor in the test and inspect the security configuration. |

When diagnosing, check status first, then Content-Type and the response body. A body conversion error can occur before the controller is invoked, so a breakpoint inside the controller method might not be hit.

## 8. Example Testing Three Formats in the Same Class

The snippet below illustrates organizing tests so each format has its own request builder and assertions. The endpoints `/api/orders`, `/api/orders/xml`, and `/api/import` are examples; they must exist in the application under test and have corresponding converters configured.

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

class RequestBodyFormatTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void sendsJsonBody() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"customerId":"C-100","quantity":2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderId").value("O-100"));
    }

    @Test
    void sendsXmlBody() throws Exception {
        String xml = "<order><customerId>C-100</customerId><quantity>2</quantity></order>";

        mockMvc.perform(post("/api/orders/xml")
                .contentType(MediaType.APPLICATION_XML)
                .accept(MediaType.APPLICATION_XML)
                .content(xml.getBytes(StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andExpect(xpath("/receipt/orderId").string("O-100"));
    }

    @Test
    void sendsBinaryBody() throws Exception {
        byte[] payload = new byte[] { 0x00, 0x01, (byte) 0xFE };

        mockMvc.perform(post("/api/import")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .content(payload))
            .andExpect(status().isAccepted());
    }
}
```

The example class focuses on how to construct requests. In a real project, place the test in an appropriate Spring test context, such as `@WebMvcTest` or `@SpringBootTest` combined with `@AutoConfigureMockMvc`, and inject `MockMvc` as a dependency. If the controller depends on services, `@WebMvcTest` usually needs those dependencies mocked. No real HTTP server needs to be started to test these requests.

## 9. Checklist When Building Request Bodies

- Identify whether the endpoint accepts JSON, XML, raw binary, or multipart.
- Set `Content-Type` to match the body format and the `consumes` mapping.
- Set `Accept` according to the response representation to verify.
- Use `content(String)` for text; use `content(byte[])` when byte-level control or binary data is needed.
- For XML DTOs, confirm an XML `HttpMessageConverter` is present and configured in the MockMvc context.
- Verify JSON with JSONPath, XML with XPath, and binary via byte-array comparison.
- When testing errors, pinpoint whether the failure happens during mapping, message conversion, validation, security, or controller processing.

MockMvc allows testing HTTP body content directly inside a mock Servlet environment. Choosing the right body type, media type, and assertions helps tests accurately verify the API's request/response contract without sending requests over a network or launching a real server.
