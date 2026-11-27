# Verifying that a request actually sends form parameters in Spring REST Docs

## 1. Objective

When testing an endpoint that accepts `application/x-www-form-urlencoded`, having the controller read a parameter is not enough to conclude that the client sent a proper **form body**. In the Servlet API, parameters can come from either the query string or the form body. A test might add values directly to the parameter map, allowing the controller to receive data even when the HTTP body contains none of the `name=value` pairs a real client would send.

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Spring REST Docs creates snippets for requests, responses, payloads, parameters, and headers; those snippets are then compiled into Asciidoctor/Markdown and integrated into the build/CI pipeline. If a test only populates a simulated Servlet parameter, the `form-parameters.adoc` table may have the right field names while the HTTP request example fails to prove a form body was actually sent.

This lesson distinguishes query parameters in the URL, form parameters in the body, and the Servlet request parameter map, and demonstrates how to build a real form body in MockMvc and verify the recorded content.

## 2. Three concepts not to conflate

### 2.1. Query parameters vs. form parameters

```http
POST /registrations?campaign=spring HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=mai%40example.com&plan=pro
```

| Data | Location | Meaning |
| --- | --- | --- |
| `campaign=spring` | Query string after `?` | Query parameter |
| `email=mai%40example.com` | HTTP body | Form parameter |
| `plan=pro` | HTTP body | Form parameter |

They may both be read as request parameters in the Servlet API, yet documentation must classify them by their **actual source**: `queryParameters(...)` for the query string and `formParameters(...)` for the form body.

### 2.2. Form body

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=pro
```

The body consists of name/value pairs separated by `&`. Each name and value must be form-encoded: `@` becomes `%40`, spaces typically become `+`, literal plus signs become `%2B`, and `&` inside values becomes `%26`.

### 2.3. Servlet parameter map

A Spring MVC controller reads parameters via `@RequestParam`, but `HttpServletRequest` only exposes the parsed set of request parameters. If a test calls `.param("email", "mai@example.com")`, it adds the value directly to `MockHttpServletRequest`'s parameter map; that alone does not mean the body contained `email=mai%40example.com`.

- Tests using `.param(...)` are useful when you want to verify that the controller receives parameters.
- When the goal is to verify the **form body**, construct a real URL-encoded body.
- Check both the request snippet and server behavior; do not infer a valid wire format simply because `@RequestParam` bound successfully.

## 3. MockMvc: building a form body properly

### 3.1. Using only `.param(...)` does not prove a body exists

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "mai@example.com")
        .param("plan", "pro"))
    .andExpect(status().isCreated());
```

This adds `email` and `plan` to the parameter map. `Content-Type` may declare URL-encoded form data, yet `.param(...)` by itself does not serialize those pairs into the request body. Therefore, this test does not prove the client sent the body `email=mai%40example.com&plan=pro`.

### 3.2. Raw body via `.content(...)`

`MockHttpServletRequestBuilder.content(...)` sets the request body content. When `Content-Type` is `application/x-www-form-urlencoded`, MockMvc parses the content and populates the request parameter map with the form pairs:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated());
```

With special characters:

```java
String formBody = "email=mai%40example.com"
        + "&displayName=Mai+Nguy%E1%BB%85n"
        + "&note=C%2B%2B+%26+Java";

mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content(formBody))
    .andExpect(status().isCreated());
```

The server receives `email` as `mai@example.com`, `displayName` as `Mai Nguyễn`, and `note` as `C++ & Java` after decoding. Do not pass an already-joined body string containing `&` and `=` into an encoder; encode each name and value individually before joining them.

### 3.3. `.formField(...)` and `.formFields(...)`

Spring Framework **6.1.7 and later** provides `formField(String, String...)` and `formFields(MultiValueMap<String, String>)` on the request builder. These APIs populate both the form body **and** the request parameter map:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .formField("email", "mai@example.com")
        .formField("plan", "pro")
        .formField("topics", "java", "spring"))
    .andExpect(status().isCreated());
```

With `MultiValueMap`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "mai@example.com");
form.add("plan", "pro");
form.add("topics", "java");
form.add("topics", "spring");

mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .formFields(form))
    .andExpect(status().isCreated());
```

`formField(...)` was introduced in Spring Framework 6.1.7. If a project uses an older version, use `.content(...)` with a URL-encoded body or upgrade dependencies in a planned manner; do not call APIs absent from your compile version.

### 3.4. Verifying the raw body and parameter map separately

```java
MvcResult result = mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated())
    .andReturn();

MockHttpServletRequest request = result.getRequest();
assertThat(request.getContentAsString())
    .isEqualTo("email=mai%40example.com&plan=pro");
assertThat(request.getContentType())
    .startsWith(MediaType.APPLICATION_FORM_URLENCODED_VALUE);
assertThat(request.getParameter("email")).isEqualTo("mai@example.com");
assertThat(request.getParameter("plan")).isEqualTo("pro");
```

These assertions check two distinct things: the raw content holds the URL-encoded form pairs, and the request parameter map parsed the expected values. Checking only `getParameter(...)` proves the application saw the parameter, not that the data came from the body.

## 4. Creating REST Docs examples that reflect the real body

Illustrative controller:

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
@RequestMapping("/registrations")
public class RegistrationController {
    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String email,
            @RequestParam String plan) {
        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

The controller is kept minimal for the example. In a real application, use validation matching business rules; `email.contains("@")` is not a complete email validator.

### 4.1. Test writing snippets from a raw form body

Gradle dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

MockMvc test:

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormWireDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsUrlEncodedBody() throws Exception {
        String formBody = "email=mai%40example.com&plan=pro";
        MvcResult result = mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .accept(MediaType.APPLICATION_JSON)
                .content(formBody))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form-wire",
                formParameters(
                    parameterWithName("email")
                        .description("Registration email; sent in the form body"),
                    parameterWithName("plan")
                        .description("Subscription plan; basic or pro")
                )
            ))
            .andReturn();

        MockHttpServletRequest request = result.getRequest();
        assertThat(request.getContentAsString()).isEqualTo(formBody);
        assertThat(request.getParameter("email")).isEqualTo("mai@example.com");
        assertThat(request.getParameter("plan")).isEqualTo("pro");
    }
}
```

This test supplies a URL-encoded body via `.content(formBody)`, uses `formParameters(...)` to generate the field table, and then asserts both the raw body and parsed values. The example assumes AssertJ is available via Spring Boot Test and the controller has no other dependencies. If the application enables Security/CSRF, add the appropriate test configuration.

The snippet uses the `registrations/create-form-wire` identifier; the output directory typically contains:

```text
build/generated-snippets/
└── registrations/
    └── create-form-wire/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

`form-parameters.adoc` describes the field-name contract. `http-request.adoc` shows the exact request captured by Spring REST Docs. Review both when inspecting documentation.

## 5. Query parameters and a form body in the same request

```java
mockMvc.perform(post("/registrations?campaign=spring")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated())
    .andDo(document("registrations/create-form-with-campaign",
        queryParameters(
            parameterWithName("campaign")
                .description("Campaign source in the query string")
        ),
        formParameters(
            parameterWithName("email")
                .description("Registration email in the form body"),
            parameterWithName("plan")
                .description("Subscription plan in the form body")
        )
    ));
```

This example requires a static import for `queryParameters` from `RequestDocumentation`. The URL query carries `campaign`; the raw body carries `email` and `plan`. Avoid using `.param(...)` for both groups, as doing so blurs their origin in the test setup. If a query parameter and a form parameter share the same name, the Servlet API may merge them; it is best to avoid reusing identical names across both sources unless truly necessary.

## 6. WebTestClient and REST Assured

### 6.1. WebTestClient

```java
webTestClient.post()
    .uri("/registrations")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("email", "mai@example.com")
        .with("plan", "pro"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-form",
        formParameters(
            parameterWithName("email").description("Registration email"),
            parameterWithName("plan").description("Plan basic or pro")
        )
    ));
```

`BodyInserters.fromFormData(...)` builds the form body. In WebFlux, handlers may read form data via `ServerWebExchange.getFormData()` or an appropriate binding; test against the exact handler type in use.

### 6.2. REST Assured

```java
given(specification)
    .filter(document("registrations/rest-assured-form",
        formParameters(
            parameterWithName("email").description("Registration email"),
            parameterWithName("plan").description("Plan basic or pro")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("plan", "pro")
    .when()
    .post("/registrations")
    .then()
    .statusCode(201);
```

`.formParam(...)` is REST Assured's API for sending form data. Use `http-request.adoc`/curl snippets to inspect the recorded request and test against a real HTTP server in an integration environment when wire-level verification is needed.

## 7. Useful assertions when verifying forms

| Aspect | How to check | What it proves |
| --- | --- | --- |
| Media type | `request.getContentType()` | Request declares URL-encoded format |
| Raw body | `request.getContentAsString()` | Body contains encoded form data |
| Form parsing | `request.getParameter("email")` | Servlet parameter map received parsed values |
| Controller binding | Response/status or service mock | Controller processes parameters properly |
| Documentation | `formParameters(...)` and `http-request.adoc` | Snippets document field names and sample request |
| Encoding | Fixtures with `+`, `%2B`, `%26`, Unicode | Special data is decoded as expected |

Example encoding verification:

```java
String body = "displayName=Mai+Nguy%E1%BB%85n&note=C%2B%2B+%26+Java";
MvcResult result = mockMvc.perform(post("/preferences")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding("UTF-8")
        .content(body))
    .andReturn();

MockHttpServletRequest request = result.getRequest();
assertThat(request.getContentAsString()).isEqualTo(body);
assertThat(request.getParameter("displayName")).isEqualTo("Mai Nguyễn");
assertThat(request.getParameter("note")).isEqualTo("C++ & Java");
```

The `/preferences` path is an illustrative endpoint and must exist in the actual test context. The test should add response assertions appropriate for the application.

## 8. Including snippets in documentation and CI

Example Asciidoctor page:

```adoc
= Registrations API

== Create registration with URL-encoded form

Requests must send Content-Type: application/x-www-form-urlencoded.

=== Form parameters
include::{snippets}/registrations/create-form-wire/form-parameters.adoc[]

=== Actual HTTP request in test
include::{snippets}/registrations/create-form-wire/http-request.adoc[]

=== HTTP response
include::{snippets}/registrations/create-form-wire/http-response.adoc[]
```

The `snippets` attribute must point to the root snippets directory, such as `build/generated-snippets`. `include::...[]` is Asciidoctor syntax, not an automatic include syntax in standard Markdown renderers. Markdown pages can link to rendered HTML or use an explicit conversion step in the pipeline.

With Gradle Groovy DSL and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI can run:

```bash
./gradlew test asciidoctor
```

Ensure tests generate snippets before Asciidoctor runs. For builds requiring reproducibility, use a clean workspace or clear build outputs via standard tasks so stale snippets do not make documentation appear freshly verified.

## 9. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Controller reads parameter but body is empty | Test only used `.param(...)` | Use `.content(...)` or `.formField(...)` from Spring Framework 6.1.7+ |
| `form-parameters.adoc` has table, sample request has no form body | Parameter map was populated separately from raw content | Inspect `http-request.adoc`, raw body, and `Content-Type` |
| `+` in value becomes a space | Form encoding treats plus signs as spaces | Encode literal plus signs as `%2B` |
| Query parameter mistakenly documented as form parameter | Test used `.param(...)` for both sources | Keep URL query and raw body separate; document query/form appropriately |
| MockMvc does not parse form body | Missing or wrong `Content-Type` | Set `application/x-www-form-urlencoded` before providing `.content(...)` |
| `formField(...)` does not compile | Spring Framework older than 6.1.7 | Use raw `.content(...)` or upgrade dependencies intentionally |
| Test passes yet real client request differs | Only checked mock parameter map | Use HTTP clients/REST Assured and integration tests when needed |
| Asciidoctor cannot find snippet | Wrong identifier or include path | Match `document(...)`, output directory, and `include` |

## 10. Practice exercise

Create a `POST /subscriptions` endpoint accepting a form with required `email`, `topics` repeated 1 to 3 times, and optional `note` that may contain Vietnamese characters and plus signs.

1. Write a test using only `.param(...)`; observe the parameter map and raw body.
2. Write a test using `.content("email=...&topics=...")` with `Content-Type: application/x-www-form-urlencoded`; assert the raw body and parsed values.
3. If the project uses Spring Framework 6.1.7+, rewrite it using `.formField(...)` or `.formFields(...)`.
4. Add a request with query parameter `source=web` to distinguish `queryParameters(...)` from `formParameters(...)`.
5. Use REST Assured or WebTestClient to send an equivalent form; generate `http-request.adoc` and `form-parameters.adoc`.
6. Embed the snippets in Asciidoctor and configure CI to run tests before documentation rendering.

**Pass criteria:** tests prove the actual body carries URL-encoded data, values parse properly, query and form parameters are classified accurately, and Spring REST Docs snippets reflect the request clients must send.

## References

- [Spring Framework 6.1 MockHttpServletRequestBuilder API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/web/servlet/request/MockHttpServletRequestBuilder.html) — `content`, `param`, `formField`, and `formFields` APIs.
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
