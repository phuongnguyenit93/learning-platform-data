# Configuring Content Negotiation and Avoiding Unwanted Format Inference in Spring MVC

## 1. What Is Content Negotiation?

**Content negotiation** is the mechanism for selecting an HTTP resource representation that matches the client's request and the server's capabilities. The same business data can be represented as JSON, XML, HTML, or plain text; however, an application does not necessarily have to support every format.

Example:

```http
GET /api/books/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

The client indicates that it wants JSON. If the endpoint can produce JSON, a typical response is:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Java"}
```

**Goal of safe configuration:** The response format must be determined explicitly, remain testable, and never be surprised by a file extension, query parameter, or untrusted header into switching the application to a data type the product did not intend to support.

In Spring MVC, distinguish at least three concerns:

- **Format accepted by the client:** typically read from the `Accept` header.
- **Format of the request body sent to the server:** read from the `Content-Type` header.
- **Format the server can actually produce:** depends on `@RequestMapping(produces=...)`, `HttpMessageConverter`, `ViewResolver`, and application configuration.

Content negotiation does not magically turn any Java object into every MIME type, nor does it mean the server must return a requested format if it lacks the capability to produce it.

## 2. Accept, Content-Type, produces, and consumes

| Concept | Data Direction | Meaning |
|---|---|---|
| `Accept: application/json` | Client → server, request metadata | Client wants a response with the JSON media type |
| `Content-Type: application/json` in request | Client → server | The request body being sent is JSON |
| `produces = "application/json"` | Handler declaration | Handler is only selected for declared compatible response media types |
| `consumes = "application/json"` | Handler declaration | Handler requires a request with a compatible input media type |
| `Content-Type` in response | Server → client | Actual format of the response |
| `HttpMessageConverter` | Spring MVC runtime | Converts object ↔ HTTP request/response body according to supported capabilities |

Example controller:

```java
@PostMapping(
    path = "/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public Book create(@RequestBody Book book) {
    return book;
}
```

- `consumes` checks the **request `Content-Type`**.
- `produces` checks **`Accept` / media types requested by the client**.
- `@RequestBody` relies on `HttpMessageConverter` to read input data.
- `@ResponseBody` (or `@RestController`) relies on a converter to produce the response body.

If the client wants XML while the handler only has `produces=application/json`, Spring MVC can return **406 Not Acceptable**. If the client sends `Content-Type: text/plain` to a handler that only has `consumes=application/json`, the typical error is **415 Unsupported Media Type**.

Do not swap these two statuses: 406 relates to the **output representation**, whereas 415 relates to the **input media type**.

## 3. How Spring MVC Selects a Representation

High-level flow:

```text
HTTP Request
   |
   |-- URL + HTTP method + Content-Type + Accept
   v
DispatcherServlet
   |
   v
HandlerMapping
   |-- matches mapping, consumes, produces
   v
HandlerAdapter -> Controller method
   |
   |-- @ResponseBody or ResponseEntity?
   |       |
   |       v
   |   HttpMessageConverter
   |   (selects compatible media type, serializes body)
   |
   |-- Returns view name / ModelAndView?
           |
           v
       ViewResolver / View
       (selects and renders corresponding representation)
   |
   v
HTTP Response
```

A key component in determining which media type the client wants is `ContentNegotiationManager`. It aggregates `ContentNegotiationStrategy` instances (such as a header strategy or parameter strategy). In modern Spring MVC, the baseline default relies on the **`Accept` header**; it does not infer formats from URL suffixes.

There are two important response paths:

1. **REST/response body:** `@RestController`, `@ResponseBody`, or `ResponseEntity` is handled by `HttpMessageConverter` implementations such as the Jackson converter for JSON. Only when a converter can write data in the appropriate media type is the response generated in that format.
2. **Server-side rendered view:** `@Controller` returning a view name like `"reports/summary"` can pass through `ViewResolver` and `View`. `ContentNegotiatingViewResolver` (if configured) can also participate in selecting a view by media type. This is not the default flow of a JSON `@RestController` endpoint.

Content negotiation affects handler and converter/view selection, yet it is **not an authentication, authorization, input validation, or primary application routing mechanism**.

## 4. Spring MVC Defaults: Prefer Accept, Avoid URL Suffixes

In Spring Framework 6.x and Spring Boot 3.5 documentation, the default content strategy relies on the `Accept` header; inferring formats from file extensions in URLs is discouraged.

Example request:

```http
GET /api/books/42.json HTTP/1.1
Accept: application/json
```

Do not assume `.json` at the end of a path means Spring MVC will invoke the `/api/books/42` mapping and automatically switch the representation to JSON. The path `/api/books/42.json` is a different path. It may fail to match any mapping, or it may match path variable `{id}` and trigger a type conversion error if the controller declares `long id` — there is no single fixed status across all mapping structures.

**Reasons to avoid URL extension inference:**

- URLs containing dots in identifiers, domain names, or version numbers are not necessarily requests to change media type.
- Suffix pattern matching can cause a route to unintentionally match extra URLs.
- Relying on extensions can cause APIs and the security layer to interpret URLs inconsistently.
- Certain data reflection and download patterns can increase **Reflected File Download (RFD)** risks if an application accepts arbitrary extensions and returns uncontrolled content.
- Caches/proxies may store responses with the wrong representation if request headers affecting output are not distinguished.

According to Spring Framework documentation, `ContentNegotiationConfigurer.favorPathExtension(...)` was deprecated in Spring Framework 5.2.4; this mechanism has been disabled by default since 5.3. In new applications, **do not re-enable it** to accommodate clients that fail to send `Accept` properly. If URL-based selection is genuinely required, an allowlisted query parameter is a far less ambiguous solution.

Likewise, Spring Boot does not enable suffix pattern matching by default. Do not configure `/resource.*` wildcards to simulate negotiation without a real requirement and thorough testing.

## 5. Safest Configuration: Accept Header + Explicit produces

For a JSON-only API:

```java
@GetMapping(
    path = "/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public Book findById(@PathVariable long id) {
    return new Book(id, "Java");
}
```

Expected behavior when the Jackson JSON converter is present:

| Request Accept | Expected Outcome |
|---|---|
| `application/json` | Endpoint can return JSON |
| `application/*` | Can receive JSON because it is compatible |
| `*/*` | Can receive JSON because the client accepts any type |
| No `Accept` header sent | Endpoint can return JSON; no need to guess from `.json` |
| `application/xml` | Incompatible with `produces=application/json`; typically returns 406 |
| `text/html` | Incompatible with `produces=application/json`; typically returns 406 |

`produces` defines the **output contract**, though serialization still depends on converters. Do not accidentally add an XML converter to the classpath and assume it is an expected output; if XML support is desired, declare and test that media type explicitly.

For response bodies requiring a pinned `Content-Type`, you can build a `ResponseEntity` with a concrete media type; converter support and matching mappings are still required. For JSON APIs, `produces` is usually the clearest first-level constraint.

**Avoid inadvertently specifying `produces={"application/json","text/html"}` when the endpoint actually produces only JSON.** Advertising extra formats misleads consumers about the contract and can lead to inconsistent representation selection.

## 6. Spring Boot 3.5 + Java 17 Example Application

This example uses Spring MVC with an API that only accepts and produces JSON. Create a Spring Boot 3.5, Java 17 project with the `spring-boot-starter-web` dependency (which typically includes the Jackson JSON converter).

In `pom.xml`, include the following dependency, assuming a Spring Boot parent or dependency management is already configured:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Source directory layout:

```text
src/main/java/com/example/negotiation/
  NegotiationApplication.java
  BookController.java
src/main/resources/
  application.properties
```

### 6.1. Application Entry Point

File `src/main/java/com/example/negotiation/NegotiationApplication.java`:

```java
package com.example.negotiation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NegotiationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NegotiationApplication.class, args);
    }
}
```

### 6.2. Controller with produces and consumes

File `src/main/java/com/example/negotiation/BookController.java`:

```java
package com.example.negotiation;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Book find(@PathVariable long id) {
        return new Book(id, "Java");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Book create(@RequestBody Book book) {
        return book;
    }

    public record Book(long id, String title) {
    }
}
```

Java 17's `record Book` is supported by Jackson in compatible projects. `@RestController` ensures the `Book` return value is written to the response body via the JSON converter, bypassing `ViewResolver`.

This is a learning example: `create` echoes back the received payload to clarify conversion; real applications need validation, services, persistence, error handling, and authorization checks. Do not treat this as a complete data-storage API.

### 6.3. Configuring application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.contentnegotiation.favor-parameter=false
```

This setting is unnecessary when parameter negotiation is already disabled by default; it is written explicitly to affirm the policy: responses are chosen primarily via `Accept`, and `?format=xml` does not change the response type.

In a Maven project with Maven Wrapper:

```bash
./mvnw spring-boot:run
```

`curl` commands to observe the differences:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/books/42
```

Expected response body:

```json
{"id":42,"title":"Java"}
```

Normal status is `200`, with response `Content-Type` compatible with `application/json`.

Client requests XML:

```bash
curl -i -H 'Accept: application/xml' http://localhost:8080/api/books/42
```

Because the handler only has `produces=application/json`, the typical result is **406 Not Acceptable**. Error body content may vary depending on Spring Boot configuration, `ProblemDetail`, error handling, and error-response content negotiation; do not treat the error body as a fixed string.

Client POSTs wrong `Content-Type`:

```bash
curl -i -X POST -H 'Content-Type: text/plain' -H 'Accept: application/json' --data 'hello' http://localhost:8080/api/books
```

The mapping only has `consumes=application/json`, so the typical result is **415 Unsupported Media Type**.

POST valid JSON:

```bash
curl -i -X POST -H 'Content-Type: application/json' -H 'Accept: application/json' --data '{"id":7,"title":"Spring"}' http://localhost:8080/api/books
```

If the body is valid, the response typically returns status **201 Created**, and JSON body:

```json
{"id":7,"title":"Spring"}
```

Note: `-i` prints both status and response headers in curl. The bodies shown above are expected illustrations, not full transcripts of entire responses.

## 7. When to Use a Format Query Parameter?

Some clients, such as browsers, legacy API gateways, or export tools, have difficulty controlling the `Accept` header. In such cases, you may allow selecting formats via a query parameter, for example:

```text
GET /api/export?format=json
GET /api/export?format=txt
```

This must be an **intentional design decision**. Never enable negotiation from arbitrary query parameters or random extensions.

Spring Boot 3.5 supports configuring:

```properties
spring.mvc.contentnegotiation.favor-parameter=true
spring.mvc.contentnegotiation.parameter-name=format
spring.mvc.contentnegotiation.media-types.json=application/json
spring.mvc.contentnegotiation.media-types.txt=text/plain
```

Equivalent YAML:

```yaml
spring:
  mvc:
    contentnegotiation:
      favor-parameter: true
      parameter-name: format
      media-types:
        json: application/json
        txt: text/plain
```

When `favor-parameter=true` is enabled, Spring MVC can prioritize the format requested via `?format=...` before `Accept` according to strategy order. Because this applies across the entire MVC context, check other endpoints relying on `Accept` to avoid unintended behavioral changes.

Registering `json` or `txt` only tells Spring how to map **parameter value → media type**; it does not automatically create a converter or a handler capable of emitting `text/plain`. If a handler only declares `produces=application/json`, a request with `?format=txt` can still lack a matching representation and return 406.

**Design recommendation:** If only a single export endpoint needs multiple formats, create explicit routes such as `/export.json` and `/export.txt`, or read the `format` parameter in that specific controller and validate against an allowlist, instead of changing the negotiation policy for the whole application. With URLs containing extensions, declare routes **explicitly** rather than relying on automatic suffix matching.

## 8. Programmatic Configuration with WebMvcConfigurer

When Java configuration is needed, Spring MVC provides `WebMvcConfigurer.configureContentNegotiation`.

Example for Spring Boot 3.x and Spring Framework 6.x, file `MvcNegotiationConfig.java`:

```java
package com.example.negotiation;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcNegotiationConfig implements WebMvcConfigurer {

    @Override
    public void configureContentNegotiation(
            ContentNegotiationConfigurer configurer) {
        configurer
            .favorParameter(true)
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN)
            .useRegisteredExtensionsOnly(true)
            .ignoreAcceptHeader(false);
    }
}
```

Explanation:

- `favorParameter(true)`: enables the query parameter reading strategy.
- `parameterName("format")`: uses the exact parameter `format`.
- `mediaType("json", ...)`, `mediaType("txt", ...)`: maps key values to registered media types.
- `useRegisteredExtensionsOnly(true)`: requires the parameter strategy to use only registered mappings, avoiding guessing unregistered media types.
- `ignoreAcceptHeader(false)`: still considers `Accept` when needed according to strategy configuration.

This example **is an alternative** to declaring the same settings in `application.properties`, not a requirement to configure both places. Avoid having multiple configuration sources define conflicting negotiation policies.

**Do not add `@EnableWebMvc` just to adjust content negotiation** in a Spring Boot application. `WebMvcConfigurer` can normally extend the auto-configured MVC setup; `@EnableWebMvc` alters auto-configuration mode and may force you to configure many other components manually.

If a strictly header-based API is required, remove the configuration bean above and keep `spring.mvc.contentnegotiation.favor-parameter=false` or leave it unconfigured.

## 9. Why Should You Not Enable Inference by File Extension?

Legacy APIs often relied on URLs like:

```text
/api/books/42.json
/api/books/42.xml
/api/books/42.pdf
```

and automatically mapped extensions to media types without explicit routes. This approach is typically hard to maintain because:

1. **Ambiguous routing:** dots can be part of an ID, filename, or identifying data.
2. **Security mismatch:** proxies/security layers and controllers may not evaluate extended URLs under the same rules.
3. **RFD:** Reflected File Download can occur in certain setups when reflected content is downloaded under a dangerous filename.
4. **Format surprise:** adding a converter to the classpath can unintentionally expand the response formats an endpoint can produce.
5. **Cache confusion:** multiple representations at the same URL require explicit cache policies.

Spring MVC applies RFD defenses in certain cases, such as adding `Content-Disposition: inline;filename=f.txt` when a path has an unsafe or unregistered extension. This is a risk-mitigation feature of the framework, **not a substitute** for safe URL and media type design.

For new APIs, choose one of two approaches:

- Use `Accept` + explicit `produces` when one URL can have multiple representations.
- Use **explicit URLs/routes** for export/download operations: `/reports/{id}/download`, `/reports/{id}/csv`, or another officially registered route, returning `Content-Disposition` and the appropriate media type.

Do not use `favorPathExtension(true)` to fix a 406 error without understanding the root cause.

## 10. Accept with Quality Factors, Wildcards, and Defaults

`Accept` can contain multiple media types and priorities:

```http
Accept: application/json;q=0.9, text/plain;q=0.5
```

The client declares that JSON is preferred over plain text. Another example:

```http
Accept: application/*;q=0.8, */*;q=0.1
```

Key things to remember:

- `q` is the **preference weight** from 0 to 1 per HTTP semantics; media types with `q=0` are treated as unacceptable.
- Wildcards such as `*/*` indicate the client accepts many formats, **not that the server must return one specific format**.
- If `Accept` is omitted, the client generally places no restriction on representation at the header level.
- When `Accept` is missing, do not guess `application/json` merely because the URL ends in `.json`; rely on the endpoint contract and converter/view capabilities.
- Representation selection order also depends on `produces`, serialization capability, and Spring MVC's media type selection algorithm. Do not claim the `Accept` list alone always determines the outcome, especially when the server offers multiple response formats.

If an API **only supports JSON**, declaring `produces=application/json` is a clearer choice than trying to alter a global `defaultContentType`.

Spring Boot 3.5 added `spring.mvc.contentnegotiation.default-content-types` to configure default content types when no specific requirement is given. Only use it when you genuinely want a global fallback policy, have read the version-specific documentation, and have verified its impact on HTML views, problem responses, and other endpoints.

## 11. Distinguishing Content Negotiation from Internal Data Formats

Content negotiation is a contract at the **HTTP representation layer**. It does not mean:

- Changing Java/domain model types.
- Automatically creating XML, PDF, or CSV converters when the project lacks the corresponding serializers.
- Translating content into the user's language; that involves `Accept-Language` and locale.
- Changing request routing or authentication.
- Accepting every client MIME type without validation.
- Guessing file formats from the extension of a filename inside a JSON body.

Similarly, adding a Jackson XML dependency can give Spring an XML-capable converter, yet **that does not mean every endpoint should emit XML**. `produces` limits which media types are advertised. Do not depend on the accidental presence of a converter to define an API contract.

For HTML view responses, do not simply change `Content-Type` to `application/json` and expect a template to render valid JSON. When JSON is needed, design a handler using `@ResponseBody` or `ResponseEntity` with an appropriate converter.

## 12. 406, 415, 400, and 404: Distinguishing Them While Debugging

| Status | Typical Meaning | Example |
|---|---|---|
| **406 Not Acceptable** | No representation compatible with `Accept` / `produces` | Client requests XML, endpoint only returns JSON |
| **415 Unsupported Media Type** | Request body media type incompatible with `consumes` or read converters | POST `text/plain` to a JSON-only endpoint |
| **400 Bad Request** | Invalid syntax, data, or parameter type | URL `/books/42.json` matches `long` `{id}`, but conversion fails |
| **404 Not Found** | No matching mapping/resource | Request to an unmapped path |

Exact statuses can depend on other mapping conditions, exception handlers, or proxies, so inspect the actual exception. Do not assume every 406 is due to missing Jackson or every 415 is caused by `Accept`.

To make valid media types clear to clients, document them in OpenAPI and cover them with automated tests rather than relying on clients probing formats.

## 13. Testing Content Negotiation with MockMvc

With Spring Boot 3.5 and `spring-boot-starter-test`, you can test `BookController`'s contracts.

File `src/test/java/com/example/negotiation/BookControllerTest.java`:

```java
package com.example.negotiation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void jsonRequestReturnsJson() throws Exception {
        mvc.perform(get("/api/books/42").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Java"));
    }

    @Test
    void xmlAcceptIsNotAvailable() throws Exception {
        mvc.perform(get("/api/books/42").accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void plainTextBodyIsNotAllowed() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validJsonBodyIsCreated() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"id\":7,\"title\":\"Spring\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring"));
    }
}
```

Note that this test class requires the matching package and `spring-boot-starter-test` dependency for a Spring Boot 3.5 project. In Spring Boot 4.x, package names and MVC test starters may change; use the documentation and test dependencies for that release.

Run in the Maven project:

```bash
./mvnw test
```

The tests verify separately:

- Client with `Accept: application/json` receives JSON.
- Client accepting only XML receives 406 when the endpoint only supports JSON.
- POST with wrong `Content-Type` receives 415.
- POST with valid JSON receives 201.

If the application enables `favor-parameter=true` as in Sections 7 or 8, add tests for `?format=json`, `?format=txt`, unregistered formats, and conflicts with `Accept`. That is a **different** policy from the default test example, so do not combine conflicting configuration snippets in the same test without updating expectations.

## 14. Caching, Proxies, and the Vary Header

If the same URL can return different representations based on `Accept`, caches at a CDN or reverse proxy must separate cache keys by that header. HTTP provides `Vary` to declare which request headers change the representation:

```http
Vary: Accept
```

When responses at the same URL differ depending on `Accept`, this is an important signal for shared caches. If the response also varies by `Accept-Language` or another header, the `Vary` policy and cache keys must include those headers too.

However, do not assume every Spring MVC endpoint automatically adds `Vary: Accept` exactly as desired in every scenario. Inspect actual responses and CDN/proxy configuration. Responses containing personal data also require appropriate `Cache-Control` policies; `Vary` does not replace data-protection policies.

With `?format=json` and `?format=txt`, caches normally distinguish URLs by query string, though depending on proxy configuration query parameters may be ignored. Verify cache keys instead of assuming.

## 15. Response Format Safety and Content-Type Headers

Avoiding "format surprise" behaviors also includes:

1. **Never reflect arbitrary `Accept` or `format` values into `Content-Type`** without a registered mapping.
2. **Do not use overly broad wildcards** in `produces` if the API contract only supports one data type.
3. **Never render untrusted data as HTML without escaping**, even if the client sends `Accept: text/html`.
4. **Do not enable unnecessary XML serialization** merely because a converter was added, especially if data/serializers have dangerous configurations.
5. **Do not enable suffix inference** to work around legacy client issues without evaluating security.
6. **Set explicit `Content-Type`** on responses; for browser frontends, use `X-Content-Type-Options: nosniff` as an additional defense layer (often provided by default Spring Security configuration).
7. **For file downloads**, set `Content-Disposition` and safe filenames, controlling generated file types; never infer downloads arbitrarily from user-supplied extensions.

Controls such as CSRF, CORS, and authentication are separate protection layers and cannot be replaced by content negotiation alone.

## 16. Practical Implementation and Debugging Workflow

When an API returns an unexpected `Content-Type`, check in order:

1. **Identify the endpoint.** Read `@GetMapping`, `@PostMapping`, `@RequestMapping`, especially `produces` and `consumes`.
2. **Capture the request.** Inspect actual `Accept`, `Content-Type`, `format` query, and path; note that proxies may modify headers.
3. **Review MVC policy.** Check `spring.mvc.contentnegotiation.favor-parameter`, `parameter-name`, `media-types.*`, and `WebMvcConfigurer.configureContentNegotiation`.
4. **Identify converters/views.** Does the application have Jackson JSON/XML converters, String converters, Thymeleaf, or `ContentNegotiatingViewResolver`?
5. **Cross-check mapping and types.** If only JSON is supported, do not accidentally advertise HTML/XML in `produces`.
6. **Read status and exceptions.** 406 differs from 415; 404/400 may come from paths and binding.
7. **Inspect paths with extensions.** Confirm the actual route declared rather than relying on legacy inference.
8. **Test matrix.** Try `Accept: application/json`, `Accept: application/xml`, `Accept: */*`, no `Accept` header, allowed/disallowed query parameters, and paths containing dots.
9. **Check cache/proxy.** Verify `Vary`, cache keys, `Content-Type`, `Content-Disposition`, and security response headers.
10. **Lock down the contract.** Document the media types clients may send/receive and include tests in CI.

### Short Checklist

- [ ] Default to `Accept`, without inferring from URL extensions.
- [ ] Declare `produces` when endpoints must fix response media types.
- [ ] Declare `consumes` for request bodies requiring specific formats.
- [ ] If enabling `?format=`, register media types and restrict allowed values.
- [ ] Do not enable suffix pattern matching/path-extension negotiation just because a client omits `Accept`.
- [ ] Test 200, 406, 415, and invalid path/query cases thoroughly.
- [ ] Do not treat adding a converter as automatically authorizing every output format.
- [ ] Verify `Vary`, cache keys, and response security headers.
- [ ] Use `WebMvcConfigurer` instead of adding `@EnableWebMvc` unnecessarily in Spring Boot.

## 17. Conclusion

**Content negotiation is a media-type contract, not a file-format guessing mechanism.** In Spring MVC, the safest and most maintainable approach for REST APIs is relying on `Accept`, declaring `produces`/`consumes` matching actually supported formats, and having corresponding converters. Do not enable URL extension inference. If a `format` query parameter is needed, enable it only with registered mappings and test conflicting or unsupported cases.

Key points to remember:

- `Accept` selects the **response**; request `Content-Type` describes the **input**.
- `406` relates to an incompatible output representation; `415` relates to input media types.
- `ContentNegotiationManager` resolves the media type the client requests; it does not create converters on its own.
- `@ResponseBody`/REST uses `HttpMessageConverter`; MVC views use `ViewResolver`/`View` accordingly.
- Suffix path inference introduces route/security ambiguity risks; allowlisted queries or explicit routes are safer.

## 18. References

- Spring Framework 6.2 — Content Types and Content Negotiation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework — Request Mapping, produces/consumes, suffix match, and RFD: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — ContentNegotiationConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/servlet/config/annotation/ContentNegotiationConfigurer.html
- Spring Boot 3.5 — Servlet Web Applications (MVC content negotiation): https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 Release Notes — default-content-types property: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes
- RFC 9110 — HTTP Semantics, Accept, Content-Type, and status codes: https://www.rfc-editor.org/rfc/rfc9110
