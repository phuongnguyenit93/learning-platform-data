# Rules for Selecting Parameter Sources and Limits on Reading the Request Body Multiple Times in Spring MVC

## 1. Why must request data sources be distinguished?

An HTTP request has **multiple locations carrying data**: path variables, query string, headers, cookies, form fields, multipart parts, JSON/XML bodies, request attributes, and session attributes. They serve different purposes. Spring MVC does not treat all data as one uniform bag of values; **annotations on handler parameters** specify where to read from and how to convert types.

Example request:

~~~http
POST /api/orders/42?notify=true HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-Trace-Id: abc-123
Cookie: locale=vi

{"sku":"BOOK-1","quantity":2}
~~~

The different sources are read as follows:

| Value | HTTP source | Explicit binding in Spring MVC |
| --- | --- | --- |
| `42` | URI template `/orders/{orderId}` | `@PathVariable("orderId") long orderId` |
| `true` | Query `?notify=true` | `@RequestParam("notify") boolean notify` |
| `abc-123` | Header `X-Trace-Id` | `@RequestHeader("X-Trace-Id") String traceId` |
| `vi` | Cookie `locale` | `@CookieValue("locale") String locale` |
| `{"sku":"BOOK-1","quantity":2}` | JSON request body | `@RequestBody OrderInput input` |

**Important:** `@RequestParam` in **Spring MVC (Servlet)** reads *Servlet request parameters*. That set can include both the query string **and** `application/x-www-form-urlencoded` form fields, not strictly query parameters alone. Spring WebFlux has a different convention for `@RequestParam` sources, so you must know which stack you are using.

Lesson objectives:
1. Identify the binding source by annotation and default rules when annotations are omitted.
2. Choose the right annotation for JSON, forms, and multipart; separate metadata from payload.
3. Understand why a request body is normally a single-consumption stream, and how that interacts with form parsing.
4. Structure validation, logging/filters, caching, and testing so the body is not consumed before reaching the controller.

Examples focus on **Spring MVC** with Java 17+, Spring Framework 6.x, and Spring Boot 3.x, using the Jakarta Servlet API (`jakarta.servlet`).

## 2. How does Spring select a resolver for a parameter?

Once `DispatcherServlet` locates a matching handler method, `RequestMappingHandlerAdapter` uses a chain of `HandlerMethodArgumentResolver`s to process each parameter. Whichever resolver supports the type/annotation produces the value for that parameter. Those resolvers may convert types, bind objects, decode the body, or raise errors if the data is invalid.

Conceptual diagram:

~~~text
HTTP request
    │
    ├── URL path / query ───────────────┐
    ├── headers / cookies ──────────────┤
    ├── body (JSON, form, multipart) ───┤
    ├── request attributes / session ───┤
    └── servlet context ────────────────┘
                                         ▼
                            HandlerMethodArgumentResolver
                            (checks annotation + Java type)
                                         │
                         ┌───────────────┼───────────────┐
                         ▼               ▼               ▼
                   URL/metadata     data binding    message converter
                         │               │               │
                  @PathVariable     @ModelAttribute   @RequestBody
                  @RequestParam      form/query       @RequestPart
                  @RequestHeader                      JSON/XML/part
                         └───────────────┬───────────────┘
                                         ▼
                                  Controller method
~~~

This is a mechanism diagram, not a fixed fallback order across **HTTP sources**. Annotations are handled by their dedicated resolvers; there is no general rule like "if missing from path, try header, then try JSON".

### 2.1. Source selection table

| Requirement | Controller parameter | Notes |
| --- | --- | --- |
| Resource ID inside the route | `@PathVariable("id") Long id` | Name must match `{id}` in the route |
| Single / multiple values from query or form | `@RequestParam("tag") List<String> tags` | Servlet params may combine query and form |
| HTTP header | `@RequestHeader("If-Match") String value` | HTTP header names are case-insensitive |
| Cookie | `@CookieValue("theme") String theme` | Cookies are client-sent data, not inherently trustworthy |
| Attribute set by filter/interceptor | `@RequestAttribute("requestId") String id` | Distinct from HTTP headers and query parameters |
| Value stored in HTTP session | `@SessionAttribute("cartId") String id` | Distinct from `@SessionAttributes` for model workflows |
| Form/query data bound into a DTO | `@ModelAttribute SearchForm form` | Data binding via constructor/setters |
| JSON/XML body into a DTO | `@RequestBody CreateOrder input` | `HttpMessageConverter` consumes the body |
| Both body and headers | `HttpEntity<CreateOrder> request` | Also reads the body via a converter |
| File in multipart | `@RequestParam("file") MultipartFile file` | Can also use `@RequestPart` |
| A JSON part in multipart | `@RequestPart("metadata") Metadata metadata` | Reads the *part* content with a converter |
| Raw Servlet data access | `HttpServletRequest`, `InputStream`, `Reader` | Must understand body consumption state |
| Context/framework objects | `Principal`, `Locale`, `HttpSession`, `Model` | Provided by Spring/Servlet, not bound from JSON |

Do not default to `@RequestBody` for all inputs: path, query, header, and cookie remain independent sources that can be received alongside **one** JSON DTO.

### 2.2. What if no annotation is declared?

Spring MVC still has fallback rules for parameters not claimed by specialized resolvers:
- Simple types per `BeanUtils.isSimpleProperty` (such as `String`, numbers, primitives, enums, and many compatible temporal types) are typically treated as `@RequestParam`.
- Complex types not handled by another resolver are typically treated as `@ModelAttribute`.

Example:

~~~java
@GetMapping("/search")
public String search(String q, SearchCriteria criteria) {
    // q is typically read from Servlet request parameters;
    // criteria is typically bound as @ModelAttribute.
    return "ok";
}
~~~

This is an **illustrative snippet**, where `SearchCriteria` must be a bindable type. Do not mistakenly think `SearchCriteria` automatically receives a JSON body; JSON requires `@RequestBody`. Write annotations explicitly on public APIs, especially when multiple data sources exist or AOT/native image is used. If you omit the name in an annotation, inferring the Java parameter name also depends on compile-time metadata; specifying names explicitly prevents errors when compiler settings change.

### 2.3. `required`, `defaultValue`, `Optional`, and type conversion

~~~java
@GetMapping("/catalog")
public String catalog(
        @RequestParam("q") String q,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestHeader(name = "X-Request-Id", required = false) String requestId) {
    return q + ":" + page + ":" + requestId;
}
~~~

Here `q` is required by default; omitting `q` typically causes Spring to return `400 Bad Request`. `page` has a default value and is converted from a string to `int`; entering a non-numeric value can trigger a binding error, typically `400`. Header `X-Request-Id` is optional, so it can receive `null`. For annotations that support `required`, an `Optional<T>` parameter also commonly expresses optionality. Choose clear names and constraints, then test actual requests.

Important limits:
- An unnamed `@RequestParam Map<String,String>` can collect multiple parameters; `MultiValueMap<String,String>` preserves multiple values for the same name.
- `@PathVariable` cannot be replaced by `@RequestParam` even though both values are convertible strings.
- If form and query share the same parameter name, retrieval behavior depends on how the Servlet container aggregates request parameters; never design an API relying on "query definitely beats form".
- A method signature using `@RequestBody Foo` with JSON must have a matching converter registered (Jackson is normally provided by `spring-boot-starter-web`). `Content-Type` and `Accept` also influence endpoint/converter selection.

## 3. Choosing the right reading mechanism by Content-Type

### 3.1. GET with query and path

~~~http
GET /api/products/15?sort=price&tag=java&tag=spring HTTP/1.1
Accept: application/json
~~~

Choose `@PathVariable("id") long id`, `@RequestParam("sort") String sort`, and `@RequestParam("tag") List<String> tags`. A request body is unnecessary for ordinary GETs. Do not put filter/sort criteria into a GET JSON body expecting all clients, proxies, and caches to handle it consistently.

### 3.2. POST JSON (`application/json`)

~~~http
POST /api/products?dryRun=true HTTP/1.1
Content-Type: application/json

{"name":"Spring Guide","price":100}
~~~

Choose **one `@RequestBody` DTO** for the JSON and `@RequestParam("dryRun")` for the query. The JSON decoder constructs the object from the body. By default `@RequestBody` has `required=true`; an empty body or malformed JSON typically causes a read error, leading to HTTP 400 unless a custom error handler applies.

**Source mismatch:** `@RequestParam("name") String name` does not automatically extract the `name` field inside JSON. JSON is a structured body, not Servlet form parameters.

### 3.3. Urlencoded form (`application/x-www-form-urlencoded`)

~~~http
POST /api/products/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Spring+Guide&quantity=2
~~~

Use `@RequestParam` for individual fields or `@ModelAttribute FormInput` to bind multiple fields into a DTO. With the Servlet API, accessing parameters can **trigger parsing of the POST form body**. Spring recommends handling forms this way instead of `@RequestBody` if request parameters will also be needed, because the body may already have been consumed by form parsing.

That is why you **cannot assume you can "re-read the raw form body"** after calling `request.getParameter("name")`. Mixing form parsing and direct stream reading yields behavior that depends on the Servlet container, execution order, and filters.

### 3.4. Multipart (`multipart/form-data`)

~~~text
Part "metadata" (Content-Type: application/json): {"source":"batch"}
Part "file"     (Content-Type: text/plain): file bytes
~~~

Choose `@RequestPart("metadata") Metadata meta` to convert the JSON part and `@RequestPart("file") MultipartFile file` or `@RequestParam("file") MultipartFile file` for the file. Each **part** has its own headers/body; do not try to use a single `@RequestBody CreateRequest` to receive an entire multipart payload as a JSON DTO.

The multipart resolver/container may parse the request before reaching the controller. Large file contents require size limits, temporary storage management, and proper streaming strategies; avoid forcing an entire multipart upload into a `byte[]` just to log it.

## 4. Runnable example: four input types in one controller

Example application using **Spring Boot 3.x, Java 17+**, with `spring-boot-starter-web` and `spring-boot-starter-test`. Root package `com.example.inputdemo`.

~~~text
src/main/java/com/example/inputdemo/
├── InputDemoApplication.java
└── web/InputController.java
src/test/java/com/example/inputdemo/web/
└── InputControllerTest.java
~~~

Application entry point at `src/main/java/com/example/inputdemo/InputDemoApplication.java`:

~~~java
package com.example.inputdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputDemoApplication.class, args);
    }
}
~~~

Controller at `src/main/java/com/example/inputdemo/web/InputController.java`:

~~~java
package com.example.inputdemo.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/input")
public class InputController {

    @GetMapping("/items/{id}")
    public ItemView find(
            @PathVariable("id") long id,
            @RequestParam(name = "mode", defaultValue = "summary") String mode,
            @RequestHeader(name = "X-Trace-Id", required = false) String traceId,
            @CookieValue(name = "lang", required = false) String lang) {
        return new ItemView(id, mode, traceId, lang);
    }

    @PostMapping(path = "/items", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CreatedItem create(
            @RequestParam(name = "source", defaultValue = "web") String source,
            @RequestBody NewItem input) {
        return new CreatedItem(input.title(), input.quantity(), source);
    }

    @PostMapping(path = "/forms",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public FormResult submit(@ModelAttribute FormInput form) {
        return new FormResult(form.getTitle(), form.getQuantity());
    }

    @PostMapping(path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResult upload(
            @RequestPart("metadata") ImportMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new UploadResult(metadata.source(), file.getSize());
    }

    public record ItemView(long id, String mode, String traceId, String lang) {}
    public record NewItem(String title, int quantity) {}
    public record CreatedItem(String title, int quantity, String source) {}
    public record FormResult(String title, int quantity) {}
    public record ImportMetadata(String source) {}
    public record UploadResult(String source, long bytes) {}

    // Dedicated JavaBean for form binding; do not expose JPA entities.
    public static class FormInput {
        private String title;
        private int quantity;

        public FormInput() {}

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }
}
~~~

Points to observe:
- `GET /api/input/items/{id}` reads no body: `id` from path, `mode` from request parameters, `traceId` from header, `lang` from cookie.
- `POST /api/input/items?source=mobile` can simultaneously receive a **query parameter** and a **JSON body**; the converter reads the body once into `NewItem`.
- `POST /api/input/forms` uses `@ModelAttribute`: Spring instantiates `FormInput` and binds `title`/`quantity` from parameters (in this case, form fields).
- `POST /api/input/uploads` uses `@RequestPart`: Spring decodes the JSON metadata of one part, while the file is accessed as `MultipartFile`; the example only returns `size` without saving the file.

The DTOs are intentionally minimal to illustrate binding sources. This sample **does not yet** declare validations such as `@NotBlank`, `@Positive`, or handle out-of-range/null values. In real applications, add `spring-boot-starter-validation`, `@Valid`, and constraints on request DTOs; do not rely solely on Java types to assume a request is valid.

### 4.1. Calling via HTTP and inspecting results

In a project configured with the Spring Boot Gradle plugin, run:

~~~bash
./gradlew bootRun
~~~

You can test with curl:

~~~bash
curl -s -H 'X-Trace-Id: t-1' -H 'Cookie: lang=vi' \
  'http://localhost:8080/api/input/items/7?mode=detail'

curl -s -X POST \
  'http://localhost:8080/api/input/items?source=mobile' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Java","quantity":2}'

curl -s -X POST 'http://localhost:8080/api/input/forms' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'title=Spring&quantity=3'

curl -s -X POST 'http://localhost:8080/api/input/uploads' \
  -F 'metadata={"source":"batch"};type=application/json' \
  -F 'file=@notes.txt;type=text/plain'
~~~

The first three responses for the inputs above are:

~~~json
{"id":7,"mode":"detail","traceId":"t-1","lang":"vi"}
~~~

~~~json
{"title":"Java","quantity":2,"source":"mobile"}
~~~

~~~json
{"title":"Spring","quantity":3}
~~~

The multipart example returns `{"source":"batch","bytes":N}`, where `N` equals the exact byte count of the actual `notes.txt` file; do not invent a fixed number when the file contents are unspecified.

If using Windows PowerShell, choose `curl.exe` for traditional curl syntax; PowerShell may alias `curl` to `Invoke-WebRequest` with different argument rules. When no Unix shell is available, use an HTTP client tool that supports forms/multipart to send the same requests.

## 5. The request body is a single-read stream: mechanics and consequences

### 5.1. Where does the stream live?

The body arrives at the Servlet container over the HTTP connection. At the Servlet layer, the request typically exposes `ServletInputStream` (`request.getInputStream()`) or `BufferedReader` (`request.getReader()`). **The Servlet API mandates choosing one or the other**: once a reader has been obtained, calling `getInputStream()` (or vice versa) can throw `IllegalStateException`. Reading to the end of the stream normally leaves subsequent reads seeing only EOF; the API does not guarantee a "rewind" button.

When a handler has:

~~~java
@PostMapping("/orders")
public void create(@RequestBody OrderInput input) {
    // Spring reads JSON from the body via HttpMessageConverter.
}
~~~

The snippet above only illustrates the mechanism (`OrderInput` is not declared in the snippet): decoding `@RequestBody` consumes the stream. Afterward, you cannot blindly call `request.getInputStream()` expecting to receive the original JSON again.

A handler having **two** `@RequestBody` parameters trying to extract two DTOs from the same JSON body is a common design mistake:

~~~java
// WRONG EXAMPLE — do not use:
@PostMapping("/broken")
public void broken(@RequestBody UserInput user, @RequestBody AuditInput audit) {}
~~~

Spring does not split a single JSON object into two independent reads. Usually the first converter has already consumed the body, causing the second parameter to fail with missing body or decoding errors. The right way: define **one wrapper DTO** for the payload, or bind once and pass the decoded data to services/validators/auditors.

~~~java
// CORRECT DESIGN EXAMPLE:
public record CreateUserRequest(UserInput user, AuditInput audit) {}

@PostMapping("/users")
public void create(@RequestBody CreateUserRequest request) {
    userService.create(request.user());
    auditService.record(request.audit());
}
~~~

These two fragments are design examples, **not standalone Java sources**: in a real app, declare `UserInput`, `AuditInput`, and the corresponding services.

### 5.2. Form parameter parsing can also consume the body

Specifically for `application/x-www-form-urlencoded`, the Servlet container may read/parse the body when code calls `getParameter()`/`getParameterMap()` or when Spring binds `@RequestParam`/`@ModelAttribute`. Therefore:
- A filter that reads `request.getInputStream()` early can leave an `@RequestBody` handler seeing an empty body.
- A filter calling `getParameterMap()` to log form data can make the raw body unavailable to read by other means.
- Reading the raw body first and then requesting form parameters can cause form parsing to fail or be incomplete.

Do not assume every Servlet container behaves identically after out-of-order operations. The reliable approach is to use the appropriate resolver for each `Content-Type` and avoid having two consumers on the same stream.

### 5.3. Observable errors

| Scenario | What can happen | How to fix |
| --- | --- | --- |
| Filter reads entire stream before controller | `@RequestBody` hits EOF, missing body error / HTTP 400 | Do not consume body in filter; use a caching wrapper or suitable API hook |
| Two `@RequestBody` parameters | Second parameter has no data left | Single request DTO, then split after decoding |
| `getReader()` then `getInputStream()` | `IllegalStateException` | Pick only one Servlet request API |
| `getParameterMap()` on form then reading raw body | Body already parsed, cannot reliably re-read | Bind forms with `@RequestParam` or `@ModelAttribute` |
| Using `@RequestParam` to read a key inside JSON | Parameter not found | Place the field in an `@RequestBody` DTO |
| JSON with incompatible `Content-Type` | Possible `415 Unsupported Media Type` | Send matching `Content-Type` / `consumes` mapping |
| Malformed JSON syntax | `HttpMessageNotReadableException`, typically HTTP 400 | Check JSON, DTO, converter, and error handler |
| Request exceeds server/proxy limit | Rejected per config, possibly HTTP 413 | Configure sensible limits; do not buffer unboundedly |

Some APIs can use `RequestBodyAdvice` to inspect/transform data **during the conversion process** and `HandlerInterceptor`/filters to attach metadata. Those hooks must still respect when and by whom the body is read.

## 6. What `ContentCachingRequestWrapper` helps with — and what it does NOT

Spring provides `org.springframework.web.util.ContentCachingRequestWrapper`: it retains a copy of bytes **that have already been read through the wrapper**; other code can inspect `getContentAsByteArray()` after the request is processed.

Three critical facts:
1. The wrapper **does not read** the body upon creation. If downstream code never consumes the body, the cache can remain empty.
2. `getContentAsByteArray()` retrieves the cached copy for inspection, subject to a size limit. It **does not make `getInputStream()` a replayable stream** for a second reader.
3. If a filter logs the body before `chain.doFilter(...)`, the cache will likely still be empty; you normally inspect the cache **after** the controller/converter has read it. With async processing, account for dispatch completion timing.

### 6.1. Filter example observing the number of bytes read

This is a compilable file in a Spring Boot 3.x application with `spring-boot-starter-web`. It logs only the **number of cached bytes** to avoid logging sensitive data.

`src/main/java/com/example/inputdemo/web/BodyAuditFilter.java`:

~~~java
package com.example.inputdemo.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@Component
public class BodyAuditFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(BodyAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        ContentCachingRequestWrapper cached =
                new ContentCachingRequestWrapper(request, 8192);

        try {
            chain.doFilter(cached, response);
        } finally {
            log.debug("HTTP {} {}: bytes cached = {}",
                    request.getMethod(),
                    request.getRequestURI(),
                    cached.getContentAsByteArray().length);
        }
    }
}
~~~

Analysis:
- `chain.doFilter(cached, response)` passes the wrapper down to Spring MVC. When the controller decodes JSON, the wrapper copies the bytes that flowed through it; the controller still consumes the body normally.
- After `chain.doFilter`, the example logs only the cached byte count. The `8192` cache limit is a **copy retention limit**, not a rule rejecting requests larger than 8192 bytes.
- If no downstream component reads the body, `bytes cached = 0` is a valid outcome.
- Do not use this wrapper as a second-body-read mechanism; nor does it replace request size limit policies.
- If payloads must be logged for debugging, bound the size, mask tokens/passwords/cookies/PII, restrict log access, and handle encoding carefully. Never dump raw request bodies containing secrets into production logs.

### 6.2. What if you genuinely need to read multiple times?

Design priority order:

1. **Read and decode exactly once** in the controller; pass the resulting DTO/`byte[]` to multiple services, validators, or components. This is the simplest approach.
2. If multiple components need to inspect the decoded body, consider `RequestBodyAdvice` or passing the parsed object in an application-owned context instead of re-reading the Servlet stream.
3. If multiple middleware components *strictly require* independent stream reads, consider a custom `HttpServletRequestWrapper`: read the body **once, very early**, enforce a size limit, store a `byte[]`, and return a fresh `ServletInputStream` over that same `byte[]` whenever `getInputStream()` is called. You must then properly implement `getReader()` with charset handling, non-blocking methods/notifications (`ReadListener`, `isReady`, `isFinished`), async dispatch, error paths, filter ordering, and interactions with form/multipart parsing.
4. For large payloads, streaming, file uploads, or sensitive data, avoid caching everything in the heap; switch to streaming read/write, controlled temporary files, or a single-consumption API design.

A custom replay wrapper **is not simply** wrapping with `ContentCachingRequestWrapper` and calling `getInputStream()` again. Nor should you buffer every request into a large `byte[]` before authenticating or validating limits; doing so increases memory consumption and DoS risk.

## 7. Testing data sources with MockMvc

`src/test/java/com/example/inputdemo/web/InputControllerTest.java`:

~~~java
package com.example.inputdemo.web;

import jakarta.servlet.http.Cookie;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputController.class)
class InputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void pathQueryHeaderAndCookieAreIndependent() throws Exception {
        mvc.perform(get("/api/input/items/7")
                        .param("mode", "detail")
                        .header("X-Trace-Id", "t-1")
                        .cookie(new Cookie("lang", "vi")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.mode").value("detail"))
                .andExpect(jsonPath("$.traceId").value("t-1"))
                .andExpect(jsonPath("$.lang").value("vi"));
    }

    @Test
    void jsonBodyAndQueryCanBeReadTogether() throws Exception {
        mvc.perform(post("/api/input/items")
                        .param("source", "mobile")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Java\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Java"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.source").value("mobile"));
    }

    @Test
    void urlEncodedFormBindsThroughModelAttribute() throws Exception {
        mvc.perform(post("/api/input/forms")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("title", "Spring")
                        .param("quantity", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring"))
                .andExpect(jsonPath("$.quantity").value(3));
    }

    @Test
    void multipartJsonPartAndFileHaveTheirOwnSources() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                "application/json",
                "{\"source\":\"batch\"}".getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "notes.txt", "text/plain", new byte[] {65, 66});

        mvc.perform(multipart("/api/input/uploads")
                        .file(metadata)
                        .file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value("batch"))
                .andExpect(jsonPath("$.bytes").value(2));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

This test class uses the Spring MVC test slice and JSON converters typically provided by `spring-boot-starter-test`/`spring-boot-starter-web`. It verifies that path/query/header/cookie, JSON body, form binding, and two multipart parts are properly distinguished. There are no database/service dependencies because the demo controller handles data directly. If the project adds Spring Security, custom filters, advice, or custom MVC configuration, adjust test context/credentials accordingly.

**About form tests:** `MockMvcRequestBuilders.post(...).param(...)` simulates Servlet form parameters. To accurately test behavior when a request carries an encoded byte body, add integration tests running against a real container. Do not rely on mock requests to assume every container behaves the same when a filter reads the raw stream before form parsing.

Error tests to include in real projects:
- Missing required `@RequestParam` or required `@RequestHeader`: verify `400`.
- `id` is a string that cannot convert to `long`: verify the error response.
- `Content-Type: text/plain` sent to a JSON-only endpoint: verify `415`.
- Malformed JSON syntax or missing body: verify `400` and intentional error format.
- Multipart missing `metadata`, wrong JSON part content type, oversized file: verify policy.
- Test a custom filter with/without a caching wrapper to catch premature body reads before the controller, without relying on behavior unique to `MockHttpServletRequest`.

## 8. Validation, security, and limits to make explicit

**Choose the right DTO per transport.** `@ModelAttribute` for form/query binding can assign properties via setters; never bind domain/JPA entities directly when they have sensitive fields like `role`, `isAdmin`, or `ownerId`. Use dedicated web DTOs or constructor binding to control allowed fields. If property binding must be used, apply `@InitBinder` with `setAllowedFields(...)` for the allowed list.

**Validate inputs:** 
- `@Valid @RequestBody CreateOrder input`: applies Bean Validation to deserialized data when the DTO has constraints and a validation library is configured.
- `@Valid @ModelAttribute FormInput input`: validates after form/query binding; can accept `BindingResult` immediately after the validated parameter to handle errors manually.
- `@Valid @RequestPart("metadata") Metadata metadata`: validates the JSON part.
- Failures from `@Valid`, constraints directly on method parameters, or conversion errors can go through different exception types; never hardcode a default Spring error message in clients.

**Size and cost:** enforce request/upload and resource limits at the reverse proxy, Servlet container, and application layers. Full-body caching consumes memory linearly with size; several concurrent large requests can spike heap usage. `ContentCachingRequestWrapper` only caps the wrapper's internal copy, not global upload protection.

**Avoid reading/logging secrets:** queries can appear in access logs, headers/cookies can carry tokens, JSON can contain passwords, and uploads can be private files. Prefer logging trace IDs, methods, normalized paths, duration, and error status; avoid logging payloads by default.

**Ensure HTTP compatibility:** distinguish `Content-Type` (what body format the client is sending) and `Accept` (what response format the client wants). With `consumes` and `produces` routing, sending the wrong media type can produce `415`/`406` before the handler runs.

## 9. Practical decision tree

~~~text
Where does the value come from in the HTTP request?
|
+-- Inside a {variable} segment of the path? --> @PathVariable
|
+-- A query / application/x-www-form-urlencoded field?
|      +-- Few simple fields?                     --> @RequestParam
|      +-- Many fields into an object?            --> @ModelAttribute + DTO
|
+-- A header?                                     --> @RequestHeader
+-- A cookie?                                     --> @CookieValue
+-- Placed on the request by filter/interceptor?  --> @RequestAttribute
+-- Already stored in the HTTP session?           --> @SessionAttribute
|
+-- Inside the raw HTTP body?
       +-- JSON/XML document?                     --> @RequestBody + DTO
       +-- Multipart JSON part?                   --> @RequestPart + DTO
       +-- Multipart file?                        --> MultipartFile/@RequestPart
       +-- Large/specialized stream?              --> consider Servlet streaming,
                                                      size limits, and read
                                                      ownership
~~~

Whenever you think "I need to read the body a second time", first check **where the data has already been parsed**. In most cases, you simply pass the decoded DTO down to a service or audit component. If an existing filter reads raw JSON to log before the controller runs, change the observation mechanism to inspect at request-processing time, enforce cache limits, and re-test `@RequestBody` endpoints.

## 10. Quick diagnostic checklist

1. Verify `@RequestMapping`/HTTP method, `Content-Type`, and `Accept` of the request.
2. For each handler parameter, note its source: path, Servlet parameters, header, cookie, body, multipart part, or request/session attribute.
3. Check Java types, converters/formatters, explicit parameter names, `required`, default values, and validation.
4. Do not mix form and JSON sources. For JSON, prefer a single `@RequestBody` DTO; for forms, use `@RequestParam`/`@ModelAttribute`.
5. Audit filters, interceptors, custom resolvers, and advice: which component reads `getInputStream()`/`getReader()`/`getParameterMap()` before the handler?
6. If using `ContentCachingRequestWrapper`, distinguish caching already-read bytes for inspection from a replayable wrapper (two different mechanisms).
7. Test with MockMvc for source selection; test against a Servlet container for form parsing, filter ordering, and upload limits.
8. Restrict bindable fields and request sizes; avoid logging sensitive data.

## 11. Official references

- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): resolvers and supported parameter types.
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): Servlet request parameters, query/form, required/optional, maps, and lists.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): `HttpMessageConverter` and warnings about form parameter parsing interactions.
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor/property binding, validation, untrusted input data.
- [Spring Framework — Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `@RequestPart`, files, JSON parts.
- [Spring Framework — `ContentCachingRequestWrapper` API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): caches only already-read bytes, cache limit, does not consume the body itself.
- [Jakarta Servlet — `ServletRequest` API](https://javadoc.io/static/jakarta.servlet/jakarta.servlet-api/6.0.0/jakarta.servlet/jakarta/servlet/ServletRequest.html): `getInputStream()`, `getReader()`, and request parameter parsing.

**Key takeaway:** data sources are governed by parameter contracts and Spring MVC's resolver system; a body should have **only one consumer** in normal request processing. Decoded data can be shared at the object level; the raw HTTP stream does not automatically become infinitely re-readable.
