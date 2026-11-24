# HandlerMethodArgumentResolver and Argument Resolution in Spring MVC

## 1. Lesson Objectives

In Spring MVC, an HTTP request does not automatically turn into Java controller parameters. Spring Framework must **find the right handler method**, understand each parameter in its method signature, extract data from path/query/header/body/session/request context, and convert it into objects of the corresponding types. That mechanism relies on `HandlerMethodArgumentResolver`s.

After this lesson, you will be able to:

- Explain where `HandlerMethodArgumentResolver` fits in the `DispatcherServlet` → `RequestMappingHandlerAdapter` → controller invocation flow.
- Distinguish `supportsParameter` and `resolveArgument`, how resolvers are selected, and how resolvers are cached per parameter.
- Recognize Spring MVC's built-in resolvers: `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@RequestBody`, `@ModelAttribute`, `Principal`, `HttpServletRequest`, `BindingResult`, etc.
- Write and register a custom resolver via `WebMvcConfigurer.addArgumentResolvers`, and test both success and failure cases.
- Choose the right tool among a resolver, `Converter`, `HttpMessageConverter`, `WebDataBinder`, validation, `@RequestAttribute`, and Spring Security.
- Avoid Spring MVC/WebFlux compatibility pitfalls, misusing resolvers for authentication, or accidentally replacing default resolvers.

Runnable example scope: **Spring Boot 3.5.x + Spring MVC + Java 17+** (Servlet/Jakarta), using Maven and JUnit Jupiter. These foundational APIs remain in newer Spring Framework lines, though starters, packages, and test configuration in Boot 4.x may differ; always consult documentation for your exact version.

## 2. How It Works in the Request Processing Flow

Suppose we have a controller:

~~~java
@GetMapping("/orders/{orderId}")
String read(@PathVariable("orderId") long orderId,
            @RequestParam(name = "verbose", defaultValue = "false") boolean verbose,
            @RequestHeader("X-Trace-Id") String traceId) {
    return orderId + ":" + verbose + ":" + traceId;
}
~~~

An HTTP request might look like:

~~~http
GET /orders/42?verbose=true HTTP/1.1
Host: localhost:8080
X-Trace-Id: req-123
~~~

Before invoking `read(42L, true, "req-123")`, Spring MVC must resolve the three arguments in turn, including converting `"42"` to `long` and `"true"` to `boolean`.

Simplified flow:

~~~text
HTTP request
    |
    v
DispatcherServlet
    |
    v
HandlerMapping (typically RequestMappingHandlerMapping)
    | identifies HandlerMethod from URL, HTTP method, etc.
    v
RequestMappingHandlerAdapter
    |
    v
ServletInvocableHandlerMethod
    |
    v
HandlerMethodArgumentResolverComposite
    |-- parameter 0 -> resolver for @PathVariable -> 42L
    |-- parameter 1 -> resolver for @RequestParam  -> true
    |-- parameter 2 -> resolver for @RequestHeader -> "req-123"
    |
    v
Invoke Java method read(...)
    |
    v
Appropriate HandlerMethodReturnValueHandler / HttpMessageConverter
    |
    v
HTTP response
~~~

**Distinguish two tasks:** `HandlerMapping` selects the **controller method**; `HandlerMethodArgumentResolver` produces **argument values for the selected method**. These are two distinct phases of Spring MVC. `HandlerMethodReturnValueHandler` processes the **return** value, not inputs.

`RequestMappingHandlerAdapter` is the common component orchestrating `@RequestMapping`/`@GetMapping` controllers. It supplies multiple resolvers combined into a `HandlerMethodArgumentResolverComposite`, then uses that composite when preparing handler method arguments.

## 3. The HandlerMethodArgumentResolver Contract

The MVC interface resides at:

~~~java
org.springframework.web.method.support.HandlerMethodArgumentResolver
~~~

It has two main methods (shown abbreviated, omitting version-dependent nullability annotations):

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

### 3.1. supportsParameter: Determine Whether This Resolver Handles the Parameter

`supportsParameter(MethodParameter)` inspects **parameter metadata**, not a specific request:

- Java type: `TenantId.class`, `String.class`, `Principal.class`, etc.
- Annotations: `@RequestParam`, `@RequestBody`, custom annotations like `@CurrentTenant`.
- Generic declarations, nested types, parameter index, and enclosing method when needed.

For example, a resolver dedicated to `@CurrentTenant TenantId` should return `true` only when the parameter **has that annotation and is of type `TenantId`**. If it simply returns `true` for every `String`, it will easily hijack parameters on unrelated controllers.

This method should be **fast, based solely on the method signature, and free of side effects**. Do not attempt to read headers inside `supportsParameter`: no `NativeWebRequest` is passed in, and resolver selection is not meant to be repeated per request like argument creation.

### 3.2. resolveArgument: Create the Java Object for the Current Request

Once a resolver is chosen, `resolveArgument(...)` produces the **actual value**:

- `parameter`: metadata of the parameter being resolved.
- `mavContainer`: model/view state while processing the handler method, useful for model-related resolvers.
- `webRequest`: access to headers, query parameters, locale, request attributes, and the underlying native Servlet request when needed.
- `binderFactory`: creates a `WebDataBinder` for binding/conversion/validation in resolvers that require it; **not every resolver needs to use it**.

The resolver returns an `Object` matching the declared parameter type; some resolvers may return `null` when allowed by the contract and nullability. If input data is invalid, throw an appropriate exception so the request ends with a predictable HTTP error instead of passing bad objects into the controller.

A stateless custom resolver is typically shared across many requests. **Never store request data in resolver instance fields**: doing so risks cross-request data leaks and race conditions under concurrent threads.

## 4. How the Composite Picks a Resolver and Ordering Behavior

`HandlerMethodArgumentResolverComposite` iterates through an ordered list of resolvers. For each `MethodParameter`, it picks the first resolver whose `supportsParameter(...)` returns `true`; that resolver is then called to resolve the argument.

Current implementations cache the **method parameter → selected resolver** association to avoid repeating the search on subsequent requests. This cache **does not** cache request input values, so a cached resolver still reads fresh headers inside `resolveArgument` each time.

Consequences:

1. `supportsParameter` must reflect **type/annotation capability**, independent of per-request user, session, or HTTP headers.
2. If two resolvers both claim the same parameter, the **earlier resolver** wins; the later one never gets a chance to handle that parameter.
3. If no resolver matches, Spring MVC may report an unsupported parameter error or fall back to simple-type/`@ModelAttribute` resolvers. Do not assume an unannotated parameter is guaranteed to be ignored.
4. If a resolver accepts a parameter and `resolveArgument` fails, the framework does not automatically fall back to another resolver to "retry"; handle exceptions appropriately.

In default MVC configuration, resolvers for built-in annotations like `@RequestParam` and `@PathVariable` are prioritized per framework rules. Custom resolvers added via `WebMvcConfigurer.addArgumentResolvers` are meant for **new parameter types**, not for replacing built-in annotation resolvers. Altering built-in behavior operates at the `RequestMappingHandlerAdapter` level, is complex, and must be tested separately.

## 5. Arguments Supported Out of the Box by Spring MVC

| Controller parameter | Data source / how argument is created | Notes |
|---|---|---|
| `@PathVariable("id") Long id` | Path variable from URI template | Converts `String → Long`; invalid format can return 400 |
| `@RequestParam("page") int page` | Query parameter or form parameter in Servlet request | Supports `defaultValue`, `required`, `Optional` |
| `@RequestHeader("X-Id") String id` | HTTP header | Supports type conversion for many types |
| `@CookieValue("lang") String lang` | HTTP cookie | Supports `required`/`defaultValue` |
| `@RequestBody CreateOrder body` | HTTP request body via `HttpMessageConverter` | JSON is usually read by a Jackson-based converter |
| `@RequestPart("file") MultipartFile file` | A multipart part | `@RequestPart` can use a message converter on a part's body |
| `@ModelAttribute SearchForm form` | Model and Servlet data binding | Binds to object, validates if configured |
| `HttpServletRequest request` | Native Servlet request | Servlet/MVC only; no annotation needed |
| `Principal principal` | Current principal | Depends on authentication/security configuration |
| `Locale locale` | Request's locale resolver | Not just reading a raw header |
| `Model model` or `BindingResult errors` | MVC model and binding status | `BindingResult` must immediately follow the bound/validated argument |
| `@RequestAttribute("x") Object x` | Attribute added to the request by filter/interceptor/server | Often enough if you just need an existing context attribute |

Example using multiple built-in resolvers:

~~~java
@GetMapping("/search/{group}")
public String search(
        @PathVariable("group") String group,
        @RequestParam(name = "page", defaultValue = "1") int page,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId,
        java.util.Locale locale) {
    return group + ":" + page + ":" + traceId + ":" + locale.toLanguageTag();
}
~~~

This is an **illustrative method excerpt**, not a standalone runnable program. It shows that a single request can combine multiple resolvers; you do not have to write custom resolvers for every data type.

### Type Conversion, Binding, and Validation Are Not the Same Mechanism

- **`HandlerMethodArgumentResolver`** decides how to *extract and prepare* an argument.
- **`ConversionService`/`Converter`/`Formatter`** converts values, such as query string `"42"` to `Long`. A resolver like `RequestParamMethodArgumentResolver` can invoke a binder/conversion service to finish its work.
- **`WebDataBinder`** binds request values onto objects, handles conversion errors, and populates `BindingResult`.
- **`HttpMessageConverter`** reads bodies by content type and deserializes them, such as JSON into `CreateOrder` for `@RequestBody`.
- **Bean Validation** checks constraints after binding/deserialization under Spring MVC–supported conditions, such as `@Valid @RequestBody`.

`@RequestBody` is not synonymous with `@ModelAttribute`. For JSON, `@RequestBody` uses HTTP message conversion; for forms/query/path and model objects, `@ModelAttribute` follows data binding. `@Valid` does not "turn" a custom resolver into an auto-validator; if a resolver creates an object itself, explicitly decide whether manual validation or `Validator` integration is required.

## 6. When Should You Write a Custom HandlerMethodArgumentResolver?

Valid use cases:

- Controllers repeat significant logic extracting and converting **request context** into a well-defined domain type.
- You want to pass objects like `@CurrentTenant TenantId`, `@CurrentUser UserContext`, or `@ClientLocale ClientLocale` without duplicating boilerplate in every controller.
- An argument needs to combine multiple HTTP sources or request attributes, run conditional checks, or perform a controlled lookup.
- You want centralized syntax validation, consistent 400 error responses, and less coupling between controllers and the Servlet API.

Before writing a custom resolver, check whether a built-in mechanism works:

| Goal | Usually simpler solution |
|---|---|
| Read a String header | `@RequestHeader` |
| Convert an ID string into a value object | `Converter<String, ID>` + appropriate source annotation |
| Bind form/query into a DTO | `@ModelAttribute`, `WebDataBinder` |
| Deserialize JSON | `@RequestBody` + `HttpMessageConverter` |
| Read a request attribute set by a filter | `@RequestAttribute` |
| Get the authenticated user | `Principal`, `Authentication`, `@AuthenticationPrincipal` (Spring Security) |
| Block unauthenticated requests | Spring Security filter chain, not a replacement resolver |

In the next example, reading a single header could actually be done with `@RequestHeader`. A custom resolver is used primarily to demonstrate encapsulating logic and producing a custom argument type. **Never trust a client-supplied header to grant access to tenant resources**; authenticate identity and tenant membership at the proper security layer.

## 7. Spring Boot 3.5 + Java 17+ Example: @CurrentTenant Annotation

Build the endpoint:

~~~http
GET /api/tenants/42/message?text=hi HTTP/1.1
Host: localhost:8080
X-Tenant-Id: acme_01
~~~

The controller accepts `@CurrentTenant TenantId tenant`, even though no built-in Spring annotation named `@CurrentTenant` exists. The custom resolver reads `X-Tenant-Id`, validates syntax, constructs a `TenantId` record, and passes it to the controller. This example **performs no authentication**; the header is purely input data and must not be used for authorization.

### 7.1. pom.xml

Create a Maven project and save `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>argument-resolver-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example pins the parent to 3.5.0 to explain a consistent API set; real projects should use a **tested patch release with security updates** from the chosen line. The Maven parent manages compatible dependencies without requiring explicit versions on each starter.

### 7.2. Entry Point

File `src/main/java/com/example/resolverdemo/ResolverDemoApplication.java`:

~~~java
package com.example.resolverdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResolverDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResolverDemoApplication.class, args);
    }
}
~~~

### 7.3. Custom Annotation

File `src/main/java/com/example/resolverdemo/CurrentTenant.java`:

~~~java
package com.example.resolverdemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {
}
~~~

`ElementType.PARAMETER` restricts placement; `RetentionPolicy.RUNTIME` lets Spring inspect the annotation via reflection on `MethodParameter`.

### 7.4. Target Argument Type

File `src/main/java/com/example/resolverdemo/TenantId.java`:

~~~java
package com.example.resolverdemo;

public record TenantId(String value) {
}
~~~

`record` is available in Java 17. An immutable object is ideal for passing syntax-checked data to controllers; being wrapped in a record **does not mean it is security-verified**.

### 7.5. Resolver Implementation

File `src/main/java/com/example/resolverdemo/CurrentTenantArgumentResolver.java`:

~~~java
package com.example.resolverdemo;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;

public final class CurrentTenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
                && TenantId.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest webRequest,
            WebDataBinderFactory binderFactory) {

        String raw = webRequest.getHeader("X-Tenant-Id");
        if (raw == null || raw.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Missing X-Tenant-Id");
        }

        String normalized = raw.trim();
        if (!normalized.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,31}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid X-Tenant-Id");
        }

        return new TenantId(normalized);
    }
}
~~~

Points to observe:

1. `supportsParameter` relies solely on **annotation + Java type**, never on the current request.
2. `resolveArgument` receives `NativeWebRequest` and extracts the header **per request**.
3. Checks that the header is non-blank and matches 1–32 ASCII characters per the regex above; values like `acme_01` pass, while `tenant with spaces` fails.
4. `ResponseStatusException(HttpStatus.BAD_REQUEST, ...)` triggers 400 when missing or invalid. Exact error response body depends on Boot version and error-handling config.
5. `mavContainer` and `binderFactory` are unused because this logic needs neither model nor data binding. That is valid under the interface.
6. Neither `raw` nor `normalized` is stored in instance fields; the resolver holds no per-request state.

In a real multi-tenant system, never rely on reading this header directly to determine access rights. Instead, read the authenticated tenant from the Spring Security context or a request attribute set by a trusted gateway/filter, and **always enforce tenant access checks**.

### 7.6. Registering with WebMvcConfigurer

File `src/main/java/com/example/resolverdemo/ResolverWebConfig.java`:

~~~java
package com.example.resolverdemo;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ResolverWebConfig implements WebMvcConfigurer {

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new CurrentTenantArgumentResolver());
    }
}
~~~

This is the Spring MVC–supported integration path for **custom controller method argument types**. In Spring Boot, do not add `@EnableWebMvc` for this example; adding that annotation hands default MVC configuration control over to the application, easily disabling auto-configured conveniences unintentionally.

`addArgumentResolvers` **adds** resolvers; it does not remove `@RequestParam`, `@RequestBody`, `@PathVariable`, or other standard resolvers. Thus controllers can freely combine `@CurrentTenant` with built-in parameters.

### 7.7. Controller Using Both Custom and Built-In Resolvers

File `src/main/java/com/example/resolverdemo/TenantMessageController.java`:

~~~java
package com.example.resolverdemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantMessageController {

    @GetMapping("/api/tenants/{id}/message")
    public String message(
            @CurrentTenant TenantId tenant,
            @PathVariable("id") long id,
            @RequestParam(name = "text", defaultValue = "hello") String text,
            HttpServletRequest request) {

        return text + " | tenant=" + tenant.value()
                + " | id=" + id
                + " | method=" + request.getMethod();
    }
}
~~~

In a single call:

- `@CurrentTenant TenantId` → `CurrentTenantArgumentResolver`.
- `@PathVariable("id") long` → path variable resolver and type conversion.
- `@RequestParam("text") String` → request parameter resolver.
- `HttpServletRequest` → built-in Servlet API resolver.

No code in the controller manually parses `X-Tenant-Id`. The controller focuses on business logic with prepared Java arguments.

### 7.8. Run and Verify Results

Install JDK 17+ and Maven; run from the project directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If the project has Maven Wrapper, use `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`). Once the server listens on default port 8080 and is not blocked by another process:

~~~bash
curl -sS -H "X-Tenant-Id: acme_01" "http://localhost:8080/api/tenants/42/message?text=hi"
~~~

Exact response body:

~~~text
hi | tenant=acme_01 | id=42 | method=GET
~~~

The body returned by the controller has no trailing newline; the shell may print the prompt right afterward. Spring Boot log lines and response headers may vary by environment.

Test missing header:

~~~bash
curl -i "http://localhost:8080/api/tenants/42/message"
~~~

Expect HTTP **400 Bad Request**, without entering the controller method body because the resolver threw `ResponseStatusException`.

Test malformed header:

~~~bash
curl -i -H "X-Tenant-Id: tenant with spaces" "http://localhost:8080/api/tenants/42/message"
~~~

Expect HTTP **400 Bad Request**. When query parameter `text` is omitted, default `hello` is used; header `X-Tenant-Id` has no default because the resolver enforces it as required.

## 8. MockMvc Testing: Confirming the Resolver Is Actually Invoked

`MockMvc` executes the Spring MVC pipeline without opening a real TCP port. With the Boot 3.5 project created above, `spring-boot-starter-test` provides the required test tools.

File `src/test/java/com/example/resolverdemo/TenantMessageControllerTest.java`:

~~~java
package com.example.resolverdemo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TenantMessageControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void resolvesCustomAndBuiltInArguments() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message")
                        .header("X-Tenant-Id", "acme_01")
                        .param("text", "hi"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "hi | tenant=acme_01 | id=42 | method=GET"));
    }

    @Test
    void rejectsMissingTenantHeader() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidTenantHeader() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message")
                        .header("X-Tenant-Id", "tenant with spaces"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

If the project has Maven Wrapper, use `./mvnw test` or `mvnw.cmd test`. The three tests verify respectively: (1) the resolver creates the right `TenantId` alongside built-in resolvers; (2) missing header causes 400; (3) invalid header format causes 400.

**Test scope:** these tests verify syntax validation, registration, and resolver execution, **not multi-tenant security**. Testing authentication/authorization requires adding Spring Security, real principals, and cases where a user lacks access to another tenant.

## 9. Interaction with @ModelAttribute, @RequestBody, and Validation

### 9.1. @RequestBody Reads the Body by Content Type

Example:

~~~java
@PostMapping("/orders")
ResponseEntity<Void> create(@Valid @RequestBody CreateOrder request) {
    // Runs after HttpMessageConverter reads JSON and framework runs validation
    return ResponseEntity.noContent().build();
}
~~~

This is an **illustrative method**, not part of the complete project in section 7. It requires the `CreateOrder` class, Spring/Validation imports, and Bean Validation dependencies (such as starter validation) in a real project.

`RequestResponseBodyMethodProcessor` is one of the argument resolvers Spring MVC uses for `@RequestBody`; it collaborates with `HttpMessageConverter` to deserialize the body and can then apply validation. Do not write a custom resolver just to read an ordinary JSON DTO, as you would end up reimplementing content-type handling, encoding, validation, and HTTP errors.

An `HttpMessageConverter` differs from a `HandlerMethodArgumentResolver`: the converter knows **how to read/write representations**, while the resolver decides **which Java parameter receives that representation**.

### 9.2. @ModelAttribute and WebDataBinder

Example:

~~~java
@GetMapping("/orders")
String list(@ModelAttribute OrderFilter filter, BindingResult errors) {
    if (errors.hasErrors()) {
        return "invalid";
    }
    return filter.toString();
}
~~~

This is also a method excerpt requiring an `OrderFilter` class. `@ModelAttribute` creates/binds an object from request parameters and relevant sources via `WebDataBinder`. `BindingResult` or `Errors` must appear **immediately after** the bound/validated parameter so the framework attaches error state properly.

Spring MVC can treat unannotated complex arguments as implicit `@ModelAttribute`, but writing the annotation explicitly is clearer and safer, especially in applications targeting native-image/AOT. For security, avoid binding directly into entities with sensitive fields; use dedicated request DTOs, constructor binding, or allowed fields if property binding is used.

### 9.3. Validation and Parameter Errors

With `@Valid @RequestBody` or `@Valid @ModelAttribute`, normal validation errors typically trigger `MethodArgumentNotValidException` and HTTP 400, or populate `BindingResult` when declared right afterward. When constraints are placed directly on method parameters, Spring MVC provides method validation and `HandlerMethodValidationException`.

Custom resolvers do not automatically gain the same validation behavior as built-in resolvers. For instance, `CurrentTenantArgumentResolver` manually checks a regex and throws `ResponseStatusException(400)`. For a value object with complex constraints, explicitly decide where validation occurs and define a clear error contract instead of assuming `@Valid` runs automatically.

## 10. Design and Security Considerations

### 10.1. Never Treat Request Headers as Trusted Identity

`X-Tenant-Id` in the example is entirely client-supplied. An attacker can spoof the header arbitrarily unless authenticated/bound elsewhere. In production applications:

- Authenticate via Spring Security, tokens, or sessions per system architecture.
- Verify that the requested tenant ID is authorized for the authenticated principal.
- If passing info from a gateway, establish a clear trust boundary and strip/overwrite untrusted headers at the gateway.
- You may read `SecurityContextHolder`/`@AuthenticationPrincipal` or request attributes **already verified by the security layer**; a resolver only turns context into an argument, never replacing authorization.

### 10.2. Thread Safety

Resolvers are typically singletons shared across many concurrent requests. Keep only thread-safe/immutable dependencies in fields; never store tenant ID, tokens, locale, payloads, or current requests in mutable fields. Read per-request info from `NativeWebRequest`.

### 10.3. Do Not Swallow or Arbitrarily Consume the Body

Use `@RequestBody` so the framework handles the request body. If a custom resolver reads `InputStream` directly and the controller also uses `@RequestBody`, the body may already be consumed, causing parse failures or an empty body. With form data, the Servlet API also has parameter parsing rules affecting the stream; do not mix manual stream reading arbitrarily.

### 10.4. Watch Out for @EnableWebMvc in Spring Boot

Simply declaring `@Configuration implements WebMvcConfigurer` is normally enough to add custom resolvers while retaining Boot's MVC auto-configuration. Adding `@EnableWebMvc` shifts most MVC configuration responsibility to the application, potentially disabling other Boot defaults unexpectedly. Do not use `@EnableWebMvc` just to register a resolver.

### 10.5. Spring MVC Is Not Spring WebFlux

This lesson covers **Servlet MVC**: `org.springframework.web.method.support.HandlerMethodArgumentResolver` and `WebMvcConfigurer`. Spring WebFlux has its own reactive SPIs and lifecycle, including resolvers returning publishers and `ServerWebExchange`. Do not copy an MVC implementation into WebFlux expecting it to be invoked.

### 10.6. Test Configuration Changes Across Spring Boot Versions

The examples in sections 7–8 target Boot 3.5 so `@AutoConfigureMockMvc`, `@SpringBootTest`, test starters, and imports stay consistent. In Boot 4.x, some modules/starters and auto-configuration/test packages were reorganized; always check the reference docs and Javadoc for your exact version rather than copying blindly.

## 11. Common Issues, Symptoms, and Troubleshooting Steps

| Symptom | Common cause | How to fix |
|---|---|---|
| Resolver is never called | `supportsParameter` returns false; annotation lacks runtime retention; config not scanned | Check `@Retention(RUNTIME)`, generics/types, package, and `WebMvcConfigurer` |
| Controller gets object as form/model instead of custom | Resolver not registered, so implicit `@ModelAttribute` claims complex parameter | Register custom resolver, use dedicated annotation, test target controller |
| Custom resolver hijacks other methods | `supportsParameter` too broad, e.g., matching all `String`s | Match both annotation + specific Java type |
| Overriding `@RequestParam` fails | `addArgumentResolvers` is not designed to replace built-in annotation resolvers | Prefer custom `Converter`/`Formatter`; only customize `HandlerAdapter` in special cases |
| 400 error parsing input | Type conversion/binding/validation or exception thrown by resolver | Inspect parameter, header, path, error logs, and exception type |
| HTTP 415 Unsupported Media Type | `Content-Type` incompatible with `HttpMessageConverter` for `@RequestBody` | Send correct JSON/`Content-Type` or configure converter |
| HTTP 400 on malformed JSON body | `@RequestBody` cannot deserialize | Inspect JSON, DTO, and exception handler |
| Validation does not run on custom value object | Resolver constructs object directly without integrating validator | Enforce constraints in code or integrate `Validator` explicitly |
| Tenant data from request A appears in B | Request data stored in shared resolver field | Make resolver stateless, read only current request |
| `BindingResult` does not work | Parameter not placed right after target object or wrong flow | Place immediately after corresponding `@ModelAttribute`/`@RequestBody` |
| Native-image/AOT binding failure | Implicit `@ModelAttribute`, missing reflection hints | Use explicit annotations and check AOT configuration |
| Boot MVC config heavily altered | Added `@EnableWebMvc` just to register custom resolver | Remove `@EnableWebMvc`, use `WebMvcConfigurer` |

To debug resolver selection, place breakpoints in `supportsParameter`, `resolveArgument`, and `HandlerMethodArgumentResolverComposite.getArgumentResolver`, or enable relevant loggers; verify breakpoints in your custom resolver before investigating how the framework falls back to `@ModelAttribute`.

## 12. Checklist Before Introducing a Custom Argument Resolver

1. Does the controller really need a **new argument type**, or are `@RequestHeader`, `@RequestAttribute`, `Converter`, or `@AuthenticationPrincipal` sufficient?
2. Is `supportsParameter` narrowed tightly by annotation/type/generics and independent of the request?
3. Does `resolveArgument` return the expected type, handle missing/invalid data, and hold no mutable request state?
4. Are you using `WebMvcConfigurer.addArgumentResolvers` without enabling `@EnableWebMvc` unnecessarily?
5. Is identity/tenant data authenticated and authorized at the security layer rather than trusting client input?
6. Have you tested valid requests, missing data, invalid format, and unrelated endpoints?
7. Have you avoided reading the request body twice, avoided unnecessary heavy/blocking work, and measured performance if the resolver calls services?
8. Have you checked your Spring Boot/Framework version and kept Servlet MVC distinct from WebFlux?

**Summary:** `HandlerMethodArgumentResolver` is the link that turns **handler parameter metadata** and **per-request data** into the **Java values** a controller receives. Spring MVC provides strong built-in resolvers; custom resolvers should express new application-domain parameter types with clear selection contracts, consistent error handling, and thorough tests.

## Official Documentation

- Spring Framework — MVC Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — `@RequestBody` and `HttpMessageConverter`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@ModelAttribute` & binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Controller Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `WebMvcConfigurer` API, `addArgumentResolvers`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework — MVC Configuration (`@EnableWebMvc`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Framework — `HandlerMethodArgumentResolver` API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolver.html
- Spring Framework — `HandlerMethodArgumentResolverComposite` API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolverComposite.html
- Spring Boot 3.5 — Servlet Web Applications and `WebMvcConfigurer`: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html