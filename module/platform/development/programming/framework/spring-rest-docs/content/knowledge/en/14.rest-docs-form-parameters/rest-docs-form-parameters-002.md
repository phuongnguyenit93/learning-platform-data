# Content type `application/x-www-form-urlencoded` in Spring REST Docs

## 1. Why is it necessary to understand request media types?

In a REST API, the same action of "submitting form data" can be represented using several HTTP body formats. The `Content-Type` header tells the server **which format the body is encoded in**; from there, the framework chooses how to read and bind the data. When building documentation with **Spring REST Docs** (`SPRING_REST_DOCS`), understanding the media type accurately helps you:

- Create test requests equivalent to real client requests.
- Use the right tool to document form parameters instead of confusing them with query strings or JSON fields.
- Detect incompatible changes between how clients send data and how the API receives data.
- Generate request, response, parameter, and header snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured, then include them in Asciidoctor/Markdown and CI.

`application/x-www-form-urlencoded` is the common media type for **form data**. It typically appears when a browser submits an HTML form using the POST method, though it can also be sent directly by HTTP clients.

For example, a client creates an order:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

sku=BK-42&quantity=2&note=Giao+h%C3%A0ng+tr%C6%B0%E1%BB%9Bc+17h
```

The body consists of three name/value pairs. After UTF-8 and form-encoding decoding, the server receives:

| Name | Decoded value | Meaning |
| --- | --- | --- |
| `sku` | `BK-42` | Item SKU |
| `quantity` | `2` | Quantity, sent as a string |
| `note` | `Giao hàng trước 17h` | Note containing spaces and Vietnamese characters |

**Key point:** this body is a sequence of encoded key/value pairs, **not JSON** and **not in the URL**.

## 2. Encoding rules for `application/x-www-form-urlencoded`

### 2.1. Basic syntax

The body typically has the form:

```text
name1=value1&name2=value2&name3=value3
```

Each entry is separated by `&`, while `=` separates the name from the value. Characters with special meaning in the data are encoded according to form encoding rules:

| Character in original value | Wire representation | Explanation |
| --- | --- | --- |
| Space ` ` | `+` | Characteristic of form encoding |
| Plus sign `+` | `%2B` | Distinguished from the space symbol |
| Ampersand `&` | `%26` | Prevents interpretation as a parameter separator |
| Equals sign `=` | `%3D` | Prevents interpretation as a name/value separator |
| At sign `@` | `%40` | Commonly seen in email addresses |
| Character `à` with UTF-8 | `%C3%A0` | Each UTF-8 byte is encoded as `%HH` |

For example, the original value `quà tặng: A+B & C` is encoded as:

```text
qu%C3%A0+t%E1%BA%B7ng%3A+A%2BB+%26+C
```

The server decodes the body sequentially according to form rules. If a client sends a raw `+` character inside a value, the decoder usually interprets it as a **space**; to transmit a literal plus sign, the client must encode it as `%2B`.

### 2.2. Charset and Unicode data

When a form contains Vietnamese or other Unicode characters, both client and server should agree on UTF-8. The header can declare:

```http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

For instance, `Hà Nội` when form-encoded with UTF-8 becomes `H%C3%A0+N%E1%BB%99i`. Specifying `charset=UTF-8` clarifies how bytes should be interpreted, though consistent character encoding configuration is still needed at the HTTP/server layer. Do not assume every client, proxy, and test environment uses the same default charset.

In Java, `URLEncoder` provides **form encoding** for a single name or value:

```java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String original = "quà tặng: A+B & C";
String encoded = URLEncoder.encode(original, StandardCharsets.UTF_8);
// qu%C3%A0+t%E1%BA%B7ng%3A+A%2BB+%26+C

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
// quà tặng: A+B & C
```

**Encode only each individual name/value** before joining them into `name=value&...`. Do not apply `URLEncoder` to the entire URL or an already assembled body string, as doing so will also encode the structural `=` and `&` delimiters.

### 2.3. Repeated parameter names, empty parameters, and missing parameters

A form can contain multiple values for the same name:

```text
tag=spring&tag=rest-docs&tag=testing
```

The server can read this into a list of values, such as `List<String> tag` or a `MultiValueMap`, depending on the binding mechanism. Conversely, `note=` represents the `note` parameter being **present with an empty value**; if there is no `note=...` pair at all, the `note` parameter is **absent**. These two situations can lead to different behavior when a controller declares default values or applies validation.

Do not assume that form encoding supports numbers, booleans, or nested lists via a universal schema. Values on the wire are strings; type conversion rules belong to the framework and application.

## 3. Distinguishing from query, JSON, and multipart

| Data format | Example | Where data is placed | How to document with Spring REST Docs |
| --- | --- | --- | --- |
| URL-encoded form | `sku=BK-42&quantity=2` | Body, `Content-Type: application/x-www-form-urlencoded` | `formParameters(...)` |
| Query parameter | `/orders?channel=mobile` | URL query string | `queryParameters(...)` |
| JSON | `{"sku":"BK-42","quantity":2}` | Body, `Content-Type: application/json` | `requestFields(...)` |
| Multipart | Form with image files and text fields | Parts in the body, `multipart/form-data` | `requestParts(...)` and appropriate part documentation |

The following two examples have the same parameter names but different locations and semantics:

```http
GET /orders?sku=BK-42&quantity=2 HTTP/1.1
```

```http
POST /orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

sku=BK-42&quantity=2
```

In Spring MVC, `@RequestParam` can access request parameters from Servlet-supported sources, so looking at the controller signature alone is not enough to infer whether the client sends a query string or a form body. When writing Spring REST Docs tests, construct the **exact HTTP request** and declare the matching snippet type.

The `Accept` header serves a different purpose: it describes the response media type the client wants to receive. For example, a request that sends a URL-encoded form while accepting a JSON response is completely valid:

```http
Content-Type: application/x-www-form-urlencoded
Accept: application/json
```

Do not use `Accept: application/x-www-form-urlencoded` as a substitute for the request body's `Content-Type`.

## 4. Example Spring MVC endpoint accepting a URL-encoded form

Suppose the application has an order creation endpoint requiring `sku`, defaulting `quantity` to `1`, and having an optional `note`.

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(required = false) String note) {

        if (sku.isBlank() || quantity < 1) {
            return ResponseEntity.badRequest().build();
        }

        // Minimal example: a real system should create and persist the order.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

`@PostMapping(consumes = ...)` declares and restricts the media type that the handler accepts. If a client sends JSON instead of a URL-encoded form, Spring MVC typically returns `415 Unsupported Media Type` when no other handler accepts that type. If a form is sent without `sku`, the framework may return `400 Bad Request` due to the missing required `@RequestParam`.

Note: `@RequestParam String sku` by default requires the **presence** of the parameter; it does not automatically guarantee a non-blank string. The `sku.isBlank()` check in the controller illustrates this distinction. Documentation must accurately describe the business rules actually implemented, rather than inferring them mechanically from annotations.

## 5. Writing MockMvc tests to generate documentation

### 5.1. Dependencies and test configuration

For Spring Boot using Gradle Groovy DSL, test dependencies typically include:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

This example assumes the project has configured a Spring Boot version and dependency management compatible with Spring REST Docs. If not using Spring Boot, you must manually register `RestDocumentationExtension`/`RestDocumentationContextProvider` with MockMvc.

### 5.2. Test creating a form request and `form-parameters.adoc`

```java
package example.docs;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createOrderFromUrlEncodedForm() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding(StandardCharsets.UTF_8.name())
                .param("sku", "BK-42")
                .param("quantity", "2")
                .param("note", "quà tặng: A+B & C"))
            .andExpect(status().isCreated())
            .andDo(document("orders/create-form",
                formParameters(
                    parameterWithName("sku")
                        .description("Item SKU; required, must not be blank"),
                    parameterWithName("quantity")
                        .optional()
                        .description("Positive integer quantity; defaults to 1"),
                    parameterWithName("note")
                        .optional()
                        .description("Customer note, may contain Unicode")
                )
            ));
    }

    @Test
    void rejectJsonWhenOnlyFormIsSupported() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"BK-42\",\"quantity\":2}"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectInvalidQuantity() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("sku", "BK-42")
                .param("quantity", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void acceptOmittedOptionalFields() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("sku", "BK-42"))
            .andExpect(status().isCreated());
    }
}
```

Breakdown of the key steps:

1. `contentType(MediaType.APPLICATION_FORM_URLENCODED)` declares the **body type** the endpoint accepts; this is essential when verifying media type handling.
2. `characterEncoding("UTF-8")` makes the test's character encoding choice explicit, especially when fixtures contain Vietnamese. For real clients, verify the actual headers and body bytes sent.
3. `param(...)` supplies request parameters to MockMvc. For URL-encoded form POST requests, Spring MockMvc provides form-building support for testing. Inspect the generated `http-request.adoc` snippet to ensure the payload on the wire matches what real clients send.
4. `andExpect(status().isCreated())` asserts that the endpoint handles the request successfully. Spring REST Docs only produces useful documentation when behavior is verified.
5. `formParameters(...)` declares the names and meanings of the **body parameters**; `.optional()` permits their absence in the test. It does not automatically check that `sku` is non-blank or that `quantity` is positive; behavioral tests cover that part.

If the application uses Spring Security with CSRF protection, POST requests in tests need a valid CSRF token or appropriate test configuration; that is a separate security requirement, not a property of form encoding.

### 5.3. Generated snippets and documentation

After `createOrderFromUrlEncodedForm` passes, an example output directory looks like:

```text
build/generated-snippets/
└── orders/
    └── create-form/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── curl-request.adoc
        └── ...
```

`form-parameters.adoc` contains descriptions for `sku`, `quantity`, and `note`; `http-request.adoc` shows the tested request, including method, URL, headers, and body. These two snippets complement each other: **one explains the data contract, while the other shows the concrete HTTP request**.

The following table illustrates the *informational content* of the form snippet; the actual layout is determined by the Asciidoctor template:

| Parameter | Description |
| --- | --- |
| `sku` | Item SKU; required, must not be blank |
| `quantity` | Positive integer quantity; defaults to 1 |
| `note` | Customer note, may contain Unicode |

Inspect special characters in `http-request.adoc`: on the wire, a `+` inside a value must be encoded properly and distinguished from a space symbol. Do not manually edit generated snippets to make examples look "prettier"; fix the request construction or endpoint logic and re-run the tests.

## 6. Sending an equivalent request with an HTTP client

With `curl` in a shell supporting Bash syntax, you can submit the form as follows:

```bash
curl -i -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'sku=BK-42' \
  --data-urlencode 'quantity=2' \
  --data-urlencode 'note=quà tặng: A+B & C'
```

`--data-urlencode` encodes form values and joins parameters. This avoids errors from manually concatenating a body with `&` when data contains spaces, plus signs, or Unicode characters. The URL assumes the application is running on `localhost:8080`; it is not required to run the MockMvc tests.

An equivalent HTML form example:

```html
<form action="/orders" method="post" accept-charset="UTF-8">
  <label>SKU <input name="sku" required></label>
  <label>Quantity <input name="quantity" type="number" min="1" value="1"></label>
  <label>Note <input name="note"></label>
  <button type="submit">Create order</button>
</form>
```

When `enctype` is unspecified, an HTML form submitted via POST uses `application/x-www-form-urlencoded` by default. `enctype="multipart/form-data"` is used when uploading files; REST Docs documentation for multipart requests must use a different set of snippets.

## 7. Applying with WebTestClient and REST Assured

Spring REST Docs integrates with multiple HTTP testing tools. In each tool, the request must carry the proper form body and media type.

### 7.1. WebTestClient

This example assumes `webTestClient` is already configured with Spring REST Docs and a WebFlux endpoint is written to read form data:

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/orders")
    .body(BodyInserters.fromFormData("sku", "BK-42")
        .with("quantity", "2")
        .with("note", "quà tặng: A+B & C"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders/webtestclient-form",
        formParameters(
            parameterWithName("sku").description("Item SKU"),
            parameterWithName("quantity").optional()
                .description("Quantity, defaults to 1"),
            parameterWithName("note").optional()
                .description("Note")
        )
    ));
```

`BodyInserters.fromFormData(...)` builds a URL-encoded body and sets the appropriate media type when no other `Content-Type` overrides it. In WebFlux, handlers typically read form data via `ServerWebExchange.getFormData()` or an appropriate binding mechanism; do not assume Spring MVC's `@RequestParam` example works identically in every WebFlux handler.

### 7.2. REST Assured

This example assumes a running server and `specification` configured with `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("orders/rest-assured-form",
        formParameters(
            parameterWithName("sku").description("Item SKU"),
            parameterWithName("quantity").optional()
                .description("Quantity, defaults to 1"),
            parameterWithName("note").optional()
                .description("Note")
        )))
    .contentType(ContentType.URLENC)
    .formParam("sku", "BK-42")
    .formParam("quantity", "2")
    .formParam("note", "quà tặng: A+B & C")
    .when()
    .post("/orders")
    .then()
    .statusCode(201);
```

`ContentType.URLENC` and `formParam(...)` tell REST Assured to produce a form request. Check the client's charset configuration when using Unicode. Do not use `.body("{...}")` with `ContentType.JSON` and expect REST Docs to generate a corresponding `form-parameters.adoc`.

## 8. Including snippets in Asciidoctor, Markdown, and CI

### 8.1. AsciiDoc page

Example `src/docs/asciidoc/index.adoc` file:

```adoc
= Orders API

== Create order with URL-encoded form

The request uses `Content-Type: application/x-www-form-urlencoded`.

=== HTTP request example
include::{snippets}/orders/create-form/http-request.adoc[]

=== Form parameters
include::{snippets}/orders/create-form/form-parameters.adoc[]

=== HTTP response example
include::{snippets}/orders/create-form/http-response.adoc[]
```

The `{snippets}` attribute must point to the root snippets directory (for example, `build/generated-snippets`), not the `orders/create-form` subdirectory. The `include::{snippets}/...[]` syntax belongs to Asciidoctor; standard Markdown renderers do not understand this directive.

When a project needs Markdown output, you can link to the HTML generated by Asciidoctor or configure an appropriate conversion step in the pipeline. Do not assume that embedding `.adoc` files directly in Markdown will automatically render as tables.

### 8.2. Build and CI integration

In a project using Gradle with the Asciidoctor plugin installed, you can configure the relationship between the test and documentation rendering tasks (Groovy DSL):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI can then run, for example:

```bash
./gradlew test asciidoctor
```

This workflow ensures:

1. Tests create URL-encoded requests, verify HTTP status codes, and document form parameters.
2. Spring REST Docs writes `form-parameters.adoc`, `http-request.adoc`, and the default snippets in the configured directory.
3. Asciidoctor reads the newly generated snippets to produce HTML or another configured output format.
4. If a required parameter changes, tests or snippet checks detect the mismatch; CI blocks publishing outdated documentation.

For real assurance, the pipeline should also verify that the final HTML file is generated and published to the intended location. Do not treat a leftover `generated-snippets` directory from an older build as proof that documentation is still accurate.

## 9. Common errors

| Symptom | Likely cause | Verification and fix |
| --- | --- | --- |
| POST returns `415 Unsupported Media Type` | Client sent JSON or omitted `Content-Type` while the endpoint only accepts URL-encoded forms | Inspect the request and handler's `consumes`; set `Content-Type: application/x-www-form-urlencoded` |
| Value `A+B` becomes `A B` | Raw `+` is interpreted as a space | Encode the plus sign as `%2B` or let the HTTP client encode parameters |
| Vietnamese characters are garbled | Inconsistent bytes/charset | Use UTF-8 consistently; inspect the actual body/charset in the request snippet |
| Value `A&B` splits into two parameters | Manually concatenated strings without encoding values | Encode `&` as `%26`; use the library's form encoder |
| Test gets 400 when data is missing | Omitted a required `@RequestParam` field, or type conversion failed | Check parameter names, request contents, and binding rules |
| `formParameters(...)` reports missing/unexpected field | Descriptors do not match the request's set of form names | Update descriptors or fixtures; only use `.optional()` for genuinely optional fields |
| Test passes but snippet has a different body than real requests | Misused MockMvc parameters or differed from client method/charset | Compare `http-request.adoc` with real HTTP requests and integration tests |
| Sent a file via `application/x-www-form-urlencoded` | Confused with multipart upload | Use `multipart/form-data` and document the appropriate request parts |
| Parameter table does not render | Snippets not generated or `{snippets}` path is wrong | Run tests before Asciidoctor; verify snippet identifier and filename |

**Data protection:** HTTP request snippets may contain the entire body, including test input values. Use only dummy data and strictly avoid putting passwords, tokens, card numbers, real emails, or personal data in sample requests meant for publication.

## 10. Practice exercise

Design a `POST /registrations` endpoint that only accepts URL-encoded forms with three fields:

- `email`: required, must not be empty.
- `newsletter`: optional, accepts `true` or `false`, defaults to `false`.
- `displayName`: optional, may contain Vietnamese characters and `+` signs.

Complete the steps in order:

1. Send a request using `curl --data-urlencode` with the name `Mỹ Anh + Team`; write down the expected encoded body string and verify the request after sending.
2. Write a MockMvc test declaring `Content-Type`, generate `form-parameters.adoc` using `formParameters(...)`, and assert a successful HTTP status.
3. Write a test missing `email`; write a test sending JSON to verify the response when the media type is incompatible.
4. Test `displayName` both absent and empty to evaluate the controller's actual difference in behavior.
5. Include both `http-request.adoc` and `form-parameters.adoc` in Asciidoctor and build the documentation in CI.

**Completion criteria:** the body is encoded properly, the server reads the parameters accurately, required/optional fields are tested, snippets are generated from passing tests, and the final documentation page uses those exact snippets.

## References

- [Spring REST Docs — Documenting Your API: Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documenting Your API: Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [MDN — `<form>`: HTML form element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/form)
- [WHATWG HTML Standard — URL-encoded form data](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#url-encoded-form-data)
