# @WebMvcTest and the Scope of Controller, Advice, Converter, and Filter in Spring Boot

## 1. Goal: Testing the Spring MVC Layer Without Loading the Entire Application

When building a REST API with Spring Boot, the controller is responsible for receiving HTTP requests, mapping URLs and parameters, reading the JSON request body, triggering validation, calling a service, and then producing the HTTP status/headers/JSON response. These behaviors can fail **even when service unit tests are green**: for example, a wrong `@PathVariable`, failed type conversion, a forgotten `@Valid`, an exception returning 500 instead of 404, or a filter blocking a request before the controller is called.

`@WebMvcTest` is a **test slice** dedicated to the Spring MVC layer. Instead of starting the entire application, it configures an `ApplicationContext` focused on the web components needed to run the controller via `MockMvc`:

- The selected controller(s) and related MVC components.
- `@ControllerAdvice`/`@RestControllerAdvice` for handling exceptions or applying shared processing.
- Type conversion for request parameters and JSON HTTP message converters according to the loaded configuration.
- `Filter`, `HandlerInterceptor`, `WebMvcConfigurer`, and other supporting web components depending on the scan/configuration scope.
- Spring MVC infrastructure, such as `DispatcherServlet`, argument resolvers, and validation when an appropriate provider is present.

**Important limitation:** `@WebMvcTest` does not automatically load `@Service`, `@Repository`, and the entire business/data layer like `@SpringBootTest` does. Controller dependencies usually need to be replaced with mocks/fakes or explicitly registered. A passing `@WebMvcTest` proves the **HTTP contract/MVC path within the loaded slice**; it does not by itself prove that SQL, the database, transactions, or the whole system work properly.

## 2. Request Processing Flow in an MVC Slice

A test request can pass through the following layers:

```text
MockMvc.perform(GET /api/products/42)
        |
        v
Servlet Filter chain              <-- if registered with MockMvc
        |
        v
DispatcherServlet
        |
        +--> HandlerMapping selects @Controller/@GetMapping
        |
        +--> ArgumentResolver + Converter
        |      (path/query/header/body -> Java parameters)
        |
        +--> Validation (if @Valid, with matching provider)
        |
        +--> Real ProductController
        |         |
        |         +--> Mock ProductService (if bean is overridden)
        |
        +--> @ControllerAdvice if an exception occurs
        |
        +--> HttpMessageConverter (Java object <-> JSON)
        |
        v
HTTP status + headers + response body
```

The diagram illustrates the stages that can occur, **not a guarantee that a specific filter/interceptor is always loaded**. For example, a filter participates only if a bean/filter registration is discovered and `MockMvc` is configured to use it. A security filter can stop the request before the controller, and `@ExceptionHandler` handles only the exceptions permitted by configuration.

In a test, you should distinguish three outcomes:

1. **The request is dispatched successfully:** the URL, HTTP method, and parameters reach the right handler.
2. **The controller contract is correct:** status, headers, JSON, validation, and exception mapping are right.
3. **Dependencies are invoked properly:** using Mockito `verify(...)` to confirm the controller passes the expected input to the mock service.

All three **do not automatically prove that the real business service ran**, because a mock can return data programmed via `when(...).thenReturn(...)`.

## 3. Which Beans Does @WebMvcTest Select?

A common declaration:

```java
@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebMvcTest {
    // @Autowired MockMvc ...
}
```

This snippet is a declaration pattern: `ProductController` must exist and the test must have the corresponding Spring Boot test dependency. Specifying `controllers` restricts the **selected controllers** instead of scanning every controller; it does not mean the context contains literally only one bean. Infrastructure and web components permitted by the slice's filters can still be present.

### 3.1. Components Typically Included in the Web Slice

| Component | Role | Scope Notes |
|---|---|---|
| `@Controller`, `@RestController` | Maps HTTP requests to handler methods | Can be restricted via `controllers = ...` |
| `@ControllerAdvice`, `@RestControllerAdvice` | `@ExceptionHandler`, shared handling and rules | Relevant advice may be discovered even when selecting a single controller |
| `Converter`, `GenericConverter` | Converts request strings, path/query parameters to Java types | Must be registered with the `ConversionService` used by MVC |
| `HttpMessageConverter` | Reads/writes bodies, e.g. JSON via Jackson | Depends on the classpath and loaded Boot/MVC configuration |
| `@JsonComponent` | Custom Jackson serializer/deserializer | Applies only if the component is discovered/registered in the slice |
| `Filter`, `FilterRegistrationBean` | Servlet logic before/after `DispatcherServlet` | Distinguish between a bean in the context and a filter actually attached to `MockMvc` |
| `HandlerInterceptor` | Before/after controller handler execution | Registered via the appropriate MVC config |
| `HandlerMethodArgumentResolver` | Binds a controller parameter using custom rules | May require `WebMvcConfigurer`/registration |
| `WebMvcConfigurer` | Customizes formatters, converters, interceptors, CORS, etc. | Takes effect only if the configuration is loaded |
| `SecurityFilterChain` if Spring Security is present | HTTP authentication/authorization | Can cause requests to return 401/403 before reaching the controller |

These are **the types of components that the Spring Boot MVC slice can retain**, not a guarantee that every bean appears in every project and every version. Conditions such as component scanning, exclude/include filters, `@Import`, test configuration, classpath, and auto-configuration determine the final context.

### 3.2. Parts Not Included in the Web Slice by Default

- `@Service`, `@Repository`, and business `@Component` classes are not among the retained components.
- JPA `EntityManager`, transaction manager, `DataSource`, and real repositories are not loaded automatically just because the controller references them.
- A real HTTP server socket is **not** started for `MockMvc`; dispatching happens inside the test application.
- The entire `@SpringBootApplication` along with business configuration is not loaded as a full application context.
- Behavior of external HTTP services, databases, message brokers, and file storage is not verified if replaced by mocks.

If the controller constructor requires `ProductService` but the slice lacks that bean, Spring may fail with `UnsatisfiedDependencyException` or `NoSuchBeanDefinitionException` **before entering the `@Test` method**. The usual solution is to declare the corresponding mock or fake, rather than reflexively switching all web tests to `@SpringBootTest`.

## 4. Choosing @MockitoBean, @MockBean, or a Fake for Your Version

In **Spring Boot 3.4+ with Spring Framework 6.2+**, you can use:

```java
@MockitoBean
ProductService products;
```

Import: `org.springframework.test.context.bean.override.mockito.MockitoBean`.

This annotation creates/replaces a bean with a Mockito mock in the **Spring TestContext**, so the real controller receives it via Dependency Injection. The test defines the service outcome using `when(...)` and checks the controller's call using `verify(...)`.

Distinction:

| Mocking Approach | Automatically Injected into Spring Controller? | Best Fit |
|---|---|---|
| `@Mock` in a JUnit Mockito unit test | **Not automatically** in a Spring context | Instantiating the controller via `new Controller(mockService)` in plain Java tests |
| `@MockitoBean` | Yes, via Spring TestContext bean override | `@WebMvcTest`/Spring context tests on supported versions |
| Legacy `@MockBean` from Spring Boot | Yes, in corresponding Boot versions | Older Boot projects; marked deprecated in Boot 3.4 |
| `@TestConfiguration` + `@Bean` fake service | Yes, if configuration is loaded | Stateful fakes or custom behavior without needing Mockito |

Do not mix imports of the new Spring Framework `@MockitoBean` into an older Boot project that lacks that annotation. The runnable example below **intentionally targets Spring Boot 3.4/3.5 with Java 17+**; for other versions, check the API and dependency coordinates. If multiple implementations share the same type, use an explicit bean name/qualifier; mocking the wrong bean can prevent the test from hitting the intended dependency.

**Do not mock the controller itself when testing MVC mappings.** When the controller is a mock, the real annotations/handler code might no longer execute as intended; the goal of an MVC slice is to keep the real controller and double the business dependencies behind it.

## 5. Complete Java 17+ Example: Controller + Advice + Converter + Filter

### 5.1. API Contract to Protect

A product management API provides:

- `GET /api/products/{id}` returns `200` and product JSON if it exists.
- When the service reports not found, `@RestControllerAdvice` returns `404` with JSON `{"code":"PRODUCT_NOT_FOUND"}`.
- `GET /api/products/sku/{code}` receives a SKU in the path; `Converter<String, Sku>` normalizes it to uppercase before calling the service.
- `POST /api/products` accepts JSON `{"name":"Keyboard","price":75000}`, requires a non-blank name and positive price, and returns `201` with the created product JSON.
- Data-invalid JSON (`name` blank / `price <= 0`) must return `400`; the service must not be called.
- An MVC slice `Filter` adds the response header `X-Slice-Filter: applied` so the test confirms the filter actually ran.

The example uses `spring-boot-starter-web`, `spring-boot-starter-validation`, and `spring-boot-starter-test`. **Do not include the Spring Security starter in this minimal example**: if the security dependency is added, authentication/CSRF/filter chain handling must be configured properly (Section 9); otherwise, anonymous requests may be blocked before the controller.

### 5.2. Test Dependency Configuration

Illustrative Gradle Groovy DSL snippet in a project that already has the Spring Boot plugin, dependency management, Java 17+, and Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.4/3.5 uses `jakarta.validation` and `jakarta.servlet`; do not mistakenly use `javax.validation`/`javax.servlet` from older generations. The example uses `@MockitoBean`, so it requires Spring Framework 6.2+.

Source structure:

```text
src/main/java/com/example/webslice/
    WebSliceDemoApplication.java
    ProductController.java
    ProductService.java
    ProductView.java
    CreateProductRequest.java
    Sku.java
    SkuConverter.java
    ProductNotFoundException.java
    ApiExceptionAdvice.java
    SliceMarkerFilter.java

src/test/java/com/example/webslice/
    ProductControllerWebMvcTest.java
```

### 5.3. Spring Boot Application Class

File `src/main/java/com/example/webslice/WebSliceDemoApplication.java`:

```java
package com.example.webslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSliceDemoApplication.class, args);
    }
}
```

This class helps Spring Boot locate the base package for component scanning. **`@WebMvcTest` still restricts the slice** and does not automatically apply the full bean scanning used when running the real application.

### 5.4. DTOs, Service Contract, and Business Exception

File `src/main/java/com/example/webslice/ProductView.java`:

```java
package com.example.webslice;

public record ProductView(long id, String name, int price) {}
```

File `src/main/java/com/example/webslice/CreateProductRequest.java`:

```java
package com.example.webslice;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive int price) {}
```

File `src/main/java/com/example/webslice/ProductService.java`:

```java
package com.example.webslice;

public interface ProductService {
    ProductView findById(long id);
    ProductView findBySku(String sku);
    ProductView create(CreateProductRequest request);
}
```

File `src/main/java/com/example/webslice/ProductNotFoundException.java`:

```java
package com.example.webslice;

public final class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(String message) {
        super(message);
    }
}
```

These are **real** data types, not mocks. `ProductService` only defines the contract; in the web slice it is replaced by `@MockitoBean`. Records generate value-based `equals`, which is useful when calling `verify(products).create(new CreateProductRequest(...))`.

### 5.5. SKU Type and Converter for @PathVariable

File `src/main/java/com/example/webslice/Sku.java`:

```java
package com.example.webslice;

public record Sku(String value) {}
```

File `src/main/java/com/example/webslice/SkuConverter.java`:

```java
package com.example.webslice;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class SkuConverter implements Converter<String, Sku> {

    @Override
    public Sku convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("SKU is blank");
        }
        return new Sku(source.trim().toUpperCase(Locale.ROOT));
    }
}
```

`Converter<String, Sku>` serves the **conversion service** when MVC binds path/query parameter strings to the `Sku` type. It is not a Jackson `HttpMessageConverter` and is not responsible for parsing JSON bodies.

In this example, the converter is a web-related component that the MVC slice can discover and register. If a project applies different scan rules or needs a custom converter outside the base package, you must add `@Import(SkuConverter.class)` or an appropriate `WebMvcConfigurer#addFormatters` and verify that the test actually uses that converter. Do not claim that every arbitrary `@Component` is scanned in `@WebMvcTest`.

### 5.6. Real Controller

File `src/main/java/com/example/webslice/ProductController.java`:

```java
package com.example.webslice;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    public ProductView findById(@PathVariable("id") long id) {
        return products.findById(id);
    }

    @GetMapping("/sku/{code}")
    public ProductView findBySku(@PathVariable("code") Sku sku) {
        return products.findBySku(sku.value());
    }

    @PostMapping
    public ResponseEntity<ProductView> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductView created = products.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Distinction:
- `@GetMapping("/{id}")` reads the path segment and converts it to `long`.
- `@GetMapping("/sku/{code}")` converts the path segment to `Sku`, and then the controller passes `sku.value()` to the service.
- `@Valid @RequestBody` triggers Bean Validation **when a validation provider is present** and the request object binds successfully; not simply because the annotation is present.
- `ResponseEntity.status(CREATED)` requests `201`; the fields of `ProductView` are serialized into the response body by the appropriate HTTP message converter (usually Jackson JSON).

There is no `@Service` implementation in this example: `ProductService` is an interface, and `@MockitoBean` will supply a mock bean for the controller in the test context.

### 5.7. Controller Advice: 404 and Validation Error 400

File `src/main/java/com/example/webslice/ApiExceptionAdvice.java`:

```java
package com.example.webslice;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            MethodArgumentNotValidException exception) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }
}
```

`@RestControllerAdvice` is `@ControllerAdvice` combined with `@ResponseBody`. It centralizes error responses. In the example, the JSON error contains only `code` so the test has a clear contract; a real application might need `message`, field validation details, a trace ID, or Problem Details.

`@WebMvcTest(ProductController.class)` can automatically load `@ControllerAdvice` beans within the web scan scope, **including shared application-wide advice**. As a result, an unrelated global advice can introduce extra dependencies or mapping conflicts into the test context. If the needed advice lies outside the scan scope, `@Import(ApiExceptionAdvice.class)` is one way to register it explicitly.

Do not write a test that only calls `new ApiExceptionAdvice().notFound(...)` directly and then conclude that Spring MVC maps the exception properly; the test must go through `MockMvc` to verify that `@ExceptionHandler` is actually used.

### 5.8. Filter: Observing a Response Header from the Servlet Chain

File `src/main/java/com/example/webslice/SliceMarkerFilter.java`:

```java
package com.example.webslice;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SliceMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        response.setHeader("X-Slice-Filter", "applied");
        filterChain.doFilter(request, response);
    }
}
```

`OncePerRequestFilter` is Spring's convenient Servlet filter base class. A filter discovered in the MVC slice can be auto-registered with `MockMvc`. The example **keeps filters enabled** (the default configuration of `@AutoConfigureMockMvc`) and asserts the header on the response, because having a filter bean in the context is **not enough** to prove the filter ran along the `MockMvc.perform` path.

Also note: a filter can change the status, write the response, require a token, or call an external dependency. If a test only wants controller mapping, you sometimes need to control filters; however, disabling the entire filter chain changes the scope of evidence and must not be hidden inside tests meant to protect security.

### 5.9. Complete Test with MockMvc and Mock Service

File `src/test/java/com/example/webslice/ProductControllerWebMvcTest.java`:

```java
package com.example.webslice;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService products;

    @Test
    void getUsesJsonMessageConverterAndRunsFilter() throws Exception {
        when(products.findById(41L)).thenReturn(
                new ProductView(41L, "Mouse", 125_000));

        mvc.perform(get("/api/products/41")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Slice-Filter", "applied"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.name").value("Mouse"))
                .andExpect(jsonPath("$.price").value(125_000));

        verify(products).findById(41L);
    }

    @Test
    void customPathVariableConverterNormalizesSku() throws Exception {
        when(products.findBySku("AB-7")).thenReturn(
                new ProductView(7L, "Adapter", 19_000));

        mvc.perform(get("/api/products/sku/ab-7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.name").value("Adapter"));

        verify(products).findBySku("AB-7");
    }

    @Test
    void adviceMapsDomainExceptionTo404() throws Exception {
        when(products.findById(404L)).thenThrow(
                new ProductNotFoundException("missing product"));

        mvc.perform(get("/api/products/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(
                        "PRODUCT_NOT_FOUND"));

        verify(products).findById(404L);
    }

    @Test
    void invalidBodyReturns400BeforeServiceCall() throws Exception {
        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","price":0}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        verifyNoInteractions(products);
    }

    @Test
    void postDeserializesJsonAndReturnsCreatedDto() throws Exception {
        when(products.create(any(CreateProductRequest.class)))
                .thenReturn(new ProductView(
                        72L, "Keyboard", 75_000));

        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Keyboard","price":75000}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(72))
                .andExpect(jsonPath("$.name").value("Keyboard"))
                .andExpect(jsonPath("$.price").value(75_000));

        verify(products).create(
                new CreateProductRequest("Keyboard", 75_000));
    }
}
```

### 5.10. What Do the Assertions Prove?

| Test Method | Real Behavior Tested | What Is Not Proven Yet |
|---|---|---|
| `getUsesJsonMessageConverterAndRunsFilter` | GET mapping, JSON serialization, content type, and Filter execution | That the real service queries the database properly |
| `customPathVariableConverterNormalizesSku` | MVC converts `ab-7` to `AB-7` before calling the service | That real product lookup by SKU works |
| `adviceMapsDomainExceptionTo404` | Exception from mock service goes through advice, producing 404 status and JSON | Whether the real repository throws the expected exception type |
| `invalidBodyReturns400BeforeServiceCall` | JSON body is bound, Bean Validation rejects data, and advice returns 400 | Database constraints or validation in the real service |
| `postDeserializesJsonAndReturnsCreatedDto` | JSON request → record, service invocation, HTTP 201, and response JSON | That the product creation transaction committed |

In the configuration described above (Spring Boot 3.4/3.5, Spring MVC Servlet stack, validation provider/Jackson on the classpath, no security starter, and components scanned in the same package), **all five tests are designed to pass**. There is no `System.out.println`, so no synthetic stdout is shown; to draw an actual conclusion, run the test class and inspect the report.

**Important:** `@WebMvcTest` does not start an embedded HTTP server listening on a real port. `MockMvc` sends simulated requests through Spring MVC infrastructure **within the test process**, so this is an MVC slice test, not an end-to-end HTTP network test.

### 5.11. Commands to Run the Tests

Gradle (Linux/macOS):

```bash
./gradlew test --tests "com.example.webslice.ProductControllerWebMvcTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.webslice.ProductControllerWebMvcTest"
```

Maven (Linux/macOS):

```bash
./mvnw -Dtest=ProductControllerWebMvcTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ProductControllerWebMvcTest test
```

Use the project's wrapper and make sure the build includes the Spring Boot plugin/dependency management, JUnit Jupiter runner, and Java 17+. Gradle convention usually writes the report to `build/reports/tests/test/index.html`; Maven Surefire writes to `target/surefire-reports/`. For multi-module projects, check the report of the module that ran.

## 6. Advice in the Web Slice: Scan Scope, Ordering, and Exception Testing

`@ControllerAdvice` can provide:

- `@ExceptionHandler` mapping exceptions to HTTP responses.
- `@ModelAttribute` or `@InitBinder` shared across multiple controllers.
- `ResponseBodyAdvice` and body-related interceptors if registered.

In a large application, multiple advice classes might catch overlapping exceptions. Processing order depends on match specificity, advice selectors, and `@Order`/precedence in Spring MVC. If a test returns an unexpected status code, check **which exception handler was chosen**; do not infer solely from annotations on a single class.

When declaring `@WebMvcTest(controllers = ProductController.class)`, the `controllers` parameter limits controllers, not necessarily all global advice beans. An advice in another package outside the scan base might not appear. You can use `@Import(SpecificAdvice.class)` for explicit control when needed.

**Do not assert only the status.** If the error contract requires `{"code":"PRODUCT_NOT_FOUND"}`, assert the JSON code, content type, and required public fields as well. Avoid asserting internal exception messages that could leak sensitive data or change during refactoring.

Validation typically occurs during argument resolution **before the controller body runs**. `MethodArgumentNotValidException` usually relates to `@Valid @RequestBody` with violated constraints, whereas malformed JSON can throw `HttpMessageNotReadableException`. These are two distinct paths: if the API requires the same error schema, handle and test both; the example in Section 5 defines advice only for validation and domain not-found.

## 7. MVC Converters vs. HttpMessageConverter

Two similar names are easy to confuse:

| Type | Input/Output | Use Case |
|---|---|---|
| Spring Core `Converter<String, T>` | One Java value → another Java type | `@PathVariable`, `@RequestParam`, field binding |
| `GenericConverter` | Flexible conversion based on source/target descriptors | Multi-type binding or custom conversion rules |
| `HttpMessageConverter` | HTTP request/response body ↔ Java object | JSON request body to DTO, DTO to JSON response |
| Jackson `JsonSerializer`/`JsonDeserializer` | Controls JSON representation of a type | Custom JSON formatting/semantics |

For example, `SkuConverter` performs `String -> Sku` **for a path parameter**, whereas the `CreateProductRequest` record is deserialized by Jackson from the JSON body. `@WebMvcTest` with `MockMvc` can test both paths with proper configuration.

If a controller has `@RequestParam LocalDate date`, Spring can use standard formatters/converters or a custom formatter. A unit test calling `controller.find(date)` directly will **not run MVC argument resolvers or the conversion service**, so it will not catch request parsing bugs. This is why a web slice test is needed when the bug belongs to the HTTP contract.

**Registration note:** A `Converter` annotated with `@Component` within MVC scan scope can be picked up and applied by Boot; however, if you define a custom `ConversionService` or complex `WebMvcConfigurer`, verify that the configuration is actually loaded into the slice. Tests should assert the **post-conversion value passed to the mock service**, such as `verify(products).findBySku("AB-7")`, rather than only asserting a 200 response.

## 8. Filters in MockMvc: Bean Presence Does Not Guarantee Filter Execution

A Servlet `Filter` sits at the boundary before `DispatcherServlet`. It can read/assign a correlation ID, check headers, set character encoding, handle CORS, or block a request before the controller is invoked. Tests must distinguish:

- **Filter bean present in the context:** means Spring created/registered the bean.
- **Filter included in the MockMvc filter chain:** depends on `MockMvc` configuration, registration, and filter selection.
- **Filter actually executing for the request:** proven only by a response header, captured invocation, or observable request state.

`@WebMvcTest` combined with `@AutoConfigureMockMvc` normally auto-configures `MockMvc`, which by default can register Servlet filters from the context. Use `@AutoConfigureMockMvc(addFilters = false)` when you want to **intentionally** test controller mapping while skipping filters; this does not mean the filter beans are removed from the context.

Example configuration **intentionally skipping filter execution** (not a filter-protecting test):

```java
@WebMvcTest(ProductController.class)
@AutoConfigureMockMvc(addFilters = false)
class ControllerMappingOnlyTest {
    // ...
}
```

The snippet above requires imports, a controller, and test bodies; it is not a standalone file. If you are writing tests for security, authentication, an audit filter, or a correlation ID, **do not use `addFilters = false`** and then conclude the filter behaves properly.

Filters can also execute on error/async request dispatches depending on configuration. `OncePerRequestFilter` helps control execution by dispatch type; it does not simply mean every overall HTTP request gets at most one callback in every scenario. When behavior involves async/error dispatches, test those cases separately.

## 9. When Spring Security Is Present: Why Do API Tests Suddenly Return 401/403?

In a project with Spring Security on the classpath and a matching security configuration, `@WebMvcTest` can auto-configure security and register `SecurityFilterChain` with `MockMvc`. When that happens:

- Unauthenticated GET requests may return **401** or redirect to login instead of 200.
- POST requests without a CSRF token may receive **403** (especially with default session-based CSRF), even if the test already has `@WithMockUser`.
- Requests are blocked by filters before the controller, so `verifyNoInteractions(service)` might pass yet **not prove that validation ran**.
- Replacing the controller's dependency with a mock service does not mean the filter chain and method security are tested like production.

Testing strategies:

1. **Test the MVC contract under real security:** Keep filters enabled, configure proper authentication/authorities, and supply CSRF for state-changing requests. You can use `spring-security-test` with `@WithMockUser` or `SecurityMockMvcRequestPostProcessors.user(...)` / `csrf()` where supported. Do not assume `@WithMockUser` replaces all real JWT/OAuth2/custom filter policies.
2. **Focus solely on mapping/JSON in a separate test class:** You may deliberately use `@AutoConfigureMockMvc(addFilters = false)`, clearly marking the scope as **not verifying security/filters**, while maintaining separate security tests.
3. **Controllers relying on `Authentication`, `Principal`, or `@AuthenticationPrincipal`:** Must supply the security context/mock data in the expected shape; blindly disabling filters can pass `null` to the controller and distort the test.
4. **Method security on the real service:** If `@MockitoBean` replaces the whole service, the test does not automatically prove `@PreAuthorize` on the service implementation works. Write a separate test keeping the real service with method security enabled.

**Illustrative snippet** when the Spring Security test dependency is present:

```java
mvc.perform(post("/api/products")
        .with(user("editor").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"name":"Keyboard","price":75000}
                """))
    .andExpect(status().isCreated());
```

Required imports include `SecurityMockMvcRequestPostProcessors.user` and `csrf`; the request reaches `201` only if the security rules, bean dependencies, and service stubbing allow it. This is **not a standalone example**; do not assume it always passes with every `SecurityFilterChain`.

To test that the controller properly returns 403 when permissions are missing, let the actual filter chain process the request, supply a user with or without sufficient authorities, and assert both the status and whether the controller/service was called as required.

## 10. How Do @WebMvcTest and @SpringBootTest Differ?

| Question | @WebMvcTest | @SpringBootTest |
|---|---|---|
| Goal | Controller HTTP contract within the MVC slice | Broader multi-layer/Boot application integration |
| Controller and DispatcherServlet | Yes, for selected components | Yes, with an appropriate web environment/config |
| MockMvc | Usually auto-configured | Requires `@AutoConfigureMockMvc` in MockMvc MVC tests |
| @ControllerAdvice | Can be loaded within slice scope | Can be loaded across the application context |
| Converters and Jackson | Relevant MVC infrastructure/beans | Fuller MVC configuration according to the app |
| Filters/Security | May be present; depends on config and MockMvc registration | May be present according to the application context |
| @Service/@Repository | Not by default | Usually present if provided by component scan/auto-config |
| JPA transactions/database | Not by default | May be present with appropriate dependencies/datasource |
| Real HTTP server | No | Only with `RANDOM_PORT`/`DEFINED_PORT` |
| Speed/scope | Usually faster and easier to isolate failures | Usually broader with higher startup cost |
| Proof of real business logic | Only if needed implementations are explicitly loaded/called | Can be verified, depending on which beans are kept real vs. mocked |

If you want to test the **JSON response when the service returns specific data**, `@WebMvcTest` fits well. If you want to prove **controller → service → repository → database** works with real JPA mappings and transactions, use an integration test with a datasource, typically `@SpringBootTest` with an appropriate test database. If you need to verify the end-to-end HTTP stack over a socket, use `webEnvironment = RANDOM_PORT` and an HTTP client.

Do not use `@SpringBootTest` for every test just because `@WebMvcTest` reports a missing `ProductService`; replace dependencies intentionally. Conversely, do not force-load dozens of real services and repositories into a slice just to avoid writing an integration test.

## 11. Common Pitfalls When @WebMvcTest Does Not Behave as Expected

| Symptom | Possible Cause | Verification Step |
|---|---|---|
| `Failed to load ApplicationContext`, missing `ProductService` | Service is outside the slice; controller needs constructor dependency | Add `@MockitoBean` or fake bean of the right type/name |
| GET returns 404 instead of 200 | Controller not selected, wrong `@GetMapping`, wrong URL, different context path/route | Check selected controllers and MockMvc URL |
| POST returns 403 instead of 201 | Security filter/CSRF, not a JSON error | Check authentication, CSRF, and filter chain |
| GET returns 401/redirect | Spring Security requires login | Add appropriate security context or separate filter-free test scope |
| Invalid body passes validation | Missing `@Valid`, missing provider, misplaced DTO annotations | Check starter-validation, `@RequestBody`, constraints |
| Valid-looking JSON request returns 400 | Jackson deserialization failure, content-type, DTO constructor, unknown type | Read `HttpMessageNotReadableException`/nested cause |
| Business exception returns 500 | Advice not scanned/imported, `@ExceptionHandler` mismatch, mapping conflict | Confirm advice bean and actual JSON/status |
| Custom converter does not run | `Converter` not registered, MVC config excluded, wrong route | Assert the post-conversion argument received by service, import converter if needed |
| Filter header missing | Filter not added to MockMvc, `addFilters=false`, different registration | Check filter bean/registration and response |
| Web slice loads too many beans | Broad component scan, `@Import`/custom config pulls extra dependencies | Trim configuration, mock dependencies, avoid scanning whole app |
| `@MockitoBean` annotation not recognized | Spring Framework version too old | Use the annotation compatible with your Boot version |
| Web test passes but real endpoint fails on DB | Service was mocked and persistence never ran | Add an integration test at the proper layer |
| Single test passes alone but fails in suite | Shared context/mutable beans, conflicting filter/security config, stubbing/caching | Isolate fixtures and manage test context/caching properly |

Context startup failures happening **before a test method runs** may involve bean overrides, filters needing dependencies, advice constructors, or auto-configuration. Look for the deepest actionable `Caused by` rather than tweaking assertions before the controller is even created.

## 12. Writing a Reliable MVC Slice Test Suite

A practical strategy combines multiple verification angles, each checking a specific part of the HTTP interface:

- **Happy path:** Required GET/POST/PUT/PATCH/DELETE calls; assert HTTP status, content type, headers, and JSON fields.
- **Mapping and binding:** Path variables, query parameters, enum/date/UUID/custom converters; verify the arguments received by the mock service.
- **Validation:** Missing/blank/negative/out-of-range fields, error payload, and ensuring the service is not invoked when the request is invalid.
- **Exception advice:** Not-found, conflict, and business errors; assert status and error schema without relying on stack traces in the response.
- **JSON converters:** Serialization/deserialization of records/DTOs, date/time formatting, snake_case/camelCase, nullable fields, and Jackson customizers per contract.
- **Filters/interceptors:** When in scope, assert observable effects; do not just assert that a filter bean exists.
- **Security:** Separate anonymous/authorized/forbidden/CSRF cases using the real `SecurityFilterChain`; do not disable filters in tests claiming to verify security.
- **Isolation:** Mock dependencies with per-test data, do not mock the controller, and avoid accidentally loading a database or out-of-scope schedulers.

An endpoint that returns `200` with wrong JSON fields or a skipped filter can still break clients. Conversely, a test that only runs `verify(service).findById(41L)` does not prove the JSON response is right. **Combining assertions on the HTTP response and inbound service interactions** is how you thoroughly evaluate an MVC slice.

## 13. Checklist Before Concluding a @WebMvcTest Passes

- [ ] Selected the right controller(s) in `@WebMvcTest(controllers=...)` and know which MVC-related beans are loaded.
- [ ] The controller is the real implementation; out-of-slice dependencies are supplied via version-appropriate `@MockitoBean`/fakes.
- [ ] Verified URLs, HTTP methods, path/query binding, and JSON requests/responses via `MockMvc.perform`.
- [ ] Distinguished `Converter` for request parameters from `HttpMessageConverter` for HTTP bodies.
- [ ] Verified `@RestControllerAdvice` maps exceptions to the right status and error JSON.
- [ ] Validation has `@Valid`, constraints, and a provider; tested that invalid input does not invoke the service.
- [ ] If a filter is part of the contract, verified that the filter **executes**, not merely that its bean exists.
- [ ] If Spring Security is present, configured filter chain, authentication, and CSRF; did not accidentally set `addFilters=false` in security tests.
- [ ] Did not treat mock service results as proof of real business/database/transaction behavior.
- [ ] Separated out-of-slice risks into integration tests such as `@SpringBootTest`, JPA tests, or end-to-end HTTP tests.
- [ ] Ran the right test class and checked the build runner report before claiming PASS on the real project.

**Conclusion:** `@WebMvcTest` focuses on testing **how Spring MVC handles a request**: controller mapping, argument conversion, JSON message conversion, validation, exception advice, and registered filters. Keeping the **real controller**, mocking/faking **out-of-slice dependencies**, and asserting both the response and service calls yields fast, clear, and trustworthy tests. However, whether advice/converters/filters are present depends on actual configuration scope; security may intercept requests before the controller; and database, transaction, or real HTTP server behavior requires separate integration tests.