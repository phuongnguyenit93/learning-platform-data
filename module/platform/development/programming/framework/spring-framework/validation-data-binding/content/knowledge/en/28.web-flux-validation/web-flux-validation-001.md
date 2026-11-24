# WebExchangeDataBinder and Data from ServerWebExchange in Spring WebFlux

## 1. Goals and Context

A request sent to Spring WebFlux can carry data in many locations: query string in the URL, URL-encoded form body, multipart body, URI template variables, headers, and JSON. When a controller receives a **model attribute**, Spring needs to gather matching values, convert types, and assign them to a Java object. The component responsible for binding on the reactive stack is `WebExchangeDataBinder` (and its extended variant), working with the `ServerWebExchange` request context.

Example request:

~~~http
POST /registrations?age=21 HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

name=Lan&tags%5B0%5D=java
~~~

A Java form can receive:

~~~java
public class RegistrationForm {
    private String name;
    private Integer age;
    private List<String> tags = new ArrayList<>();
    // Corresponding getters/setters.
}
~~~

Desired result after property binding: `name == "Lan"`, `age == 21`, and `tags.get(0).equals("java")`. The query parameter `age` and form fields `name`, `tags[0]` participate together, while `ConversionService`/property editors help convert the string `"21"` into `Integer`.

**Key takeaways of this lesson:**

- `ServerWebExchange` represents **one HTTP interaction**: request, response, attributes, session, form data, and multipart data via a reactive API.
- `WebExchangeDataBinder` extends `WebDataBinder`/`DataBinder` and knows how to extract bindable values from `ServerWebExchange`.
- `bind(exchange)` returns **`Mono<Void>`**: it completes after the required data is read and binding occurs. You should not call it and discard the publisher.
- `BindingResult` holds binding/conversion errors; **validation** with `@Valid`/`@Validated` is a separate step.
- `@ModelAttribute` in **Spring WebFlux** uses data binding, which is completely different from `@RequestBody` JSON decoded via `HttpMessageReader`.
- Request field names are controlled by the client. Use a dedicated input DTO, `allowedFields`, size limits, authorization checks, and do not bind directly into sensitive domain entities.

Content is based on Spring Framework 6.2/Java 17. The runnable example uses Spring Boot 3.5.7 and **`spring-boot-starter-webflux`**, not `spring-boot-starter-web` of Servlet MVC.

## 2. Participating Objects

### 2.1. What is `ServerWebExchange`?

The `org.springframework.web.server.ServerWebExchange` interface wraps the request–response interaction of WebFlux. Typical APIs:

| API | Data | Characteristics |
| --- | --- | --- |
| `getRequest()` | `ServerHttpRequest` | Request URI, method, headers, `getQueryParams()` |
| `getResponse()` | `ServerHttpResponse` | HTTP status, response headers, and body |
| `getAttributes()` | `Map<String,Object>` | Exchange-scoped data, not default input fields |
| `getFormData()` | `Mono<MultiValueMap<String,String>>` | `application/x-www-form-urlencoded` body |
| `getMultipartData()` | `Mono<MultiValueMap<String,Part>>` | `multipart/form-data` body and configured multipart media types |
| `getSession()` | `Mono<WebSession>` | Accesses the session via a reactive contract |
| `getPrincipal()` | `Mono<Principal>` | The request's principal, if present |
| `getLocaleContext()` | `LocaleContext` | The request's localization context |

`exchange.getRequest().getQueryParams()` returns `MultiValueMap<String,String>` **synchronously** because the query is already in the URI. Conversely, `getFormData()` and `getMultipartData()` return `Mono` because the body content is read and parsed through reactive message readers.

Example of reading a form reactively:

~~~java
public Mono<String> readName(ServerWebExchange exchange) {
    return exchange.getFormData()
            .map(form -> form.getFirst("name"))
            .defaultIfEmpty("");
}
~~~

This is **an illustrative method**, not a complete class with imports. Note that `defaultIfEmpty` only handles the case where the publisher emits no value; if `getFirst("name")` is `null`, Reactor's `map` does not allow returning `null`. In application code, absent field names must be handled safely, for example:

~~~java
public Mono<String> readNameSafely(ServerWebExchange exchange) {
    return exchange.getFormData()
            .map(form -> form.getFirst("name") == null
                    ? ""
                    : form.getFirst("name"));
}
~~~

The second snippet demonstrates exact null-handling. By contract, `ServerWebExchange.getFormData()` returns a map (possibly empty) once form data is resolved. Form data is read and parsed in full and then **the map is cached**, so calling `getFormData()` again on the same exchange does not re-read the raw body; however, it still requires an appropriate memory budget.

For multipart, metadata about parts is cached in `getMultipartData()`, but **the content of each `Part` is not cached for arbitrary repeated reading**. Reading uploads must handle the stream/lifecycle properly.

### 2.2. What is `WebExchangeDataBinder`?

Class:

~~~java
org.springframework.web.bind.support.WebExchangeDataBinder
~~~

Inheritance hierarchy:

~~~text
DataBinder
   └── WebDataBinder
           └── WebExchangeDataBinder
                   └── ExtendedWebExchangeDataBinder
                       (variant used in WebFlux controllers)
~~~

`DataBinder` provides binding into JavaBeans/constructors, converters, validators, and `BindingResult`. `WebDataBinder` adds field markers/defaults handling and mechanisms suited for web forms. `WebExchangeDataBinder` specializes in **extracting values from a reactive `ServerWebExchange`** to assign to an object.

Important API signatures on Spring Framework 6.2:

~~~java
// Abbreviated Spring library signatures, DO NOT redefine.
new WebExchangeDataBinder(target);
new WebExchangeDataBinder(target, "registrationForm");

Mono<Void> bind(ServerWebExchange exchange);
Mono<Void> construct(ServerWebExchange exchange); // Available since Spring 6.1.
Mono<Map<String, Object>> getValuesToBind(ServerWebExchange exchange);
static Mono<Map<String, Object>>
    extractValuesToBind(ServerWebExchange exchange);
~~~

- The constructor takes `target`, the bean to bind. `objectName` helps attach error names to the right model attribute.
- `bind(exchange)` serves **property binding** on an existing object, e.g., calling form setters.
- `construct(exchange)` creates the target via constructor binding when the binder is configured with an appropriate target type, rather than simply calling `new` for any class. When building `@ModelAttribute` handlers, Spring typically orchestrates object creation.
- `getValuesToBind(exchange)` retrieves the map of bindable data, defaulting to calling the static method `extractValuesToBind(exchange)`.
- `getBindingResult()`, inherited from `DataBinder`, exposes binding errors. When calling `bind` manually, `@Valid` **does not run automatically** just because the target has annotations.

### 2.3. What is `ExtendedWebExchangeDataBinder` for?

`WebExchangeDataBinder.extractValuesToBind` primarily gathers **query parameters, form fields, and multipart fields/parts**. In the `@ModelAttribute` flow of a WebFlux controller, Spring uses the extended binder `ExtendedWebExchangeDataBinder`, which can add **URI template variables** and **request headers** as binding candidates when they are not overridden by request parameters.

Example:

~~~http
POST /owners/42/profile?name=Lan HTTP/1.1
X-Region: south
Content-Type: application/x-www-form-urlencoded

city=Hanoi
~~~

An `@ModelAttribute ProfileForm` can receive `name` from the query, `city` from the body, and `ownerId` from the path variable if the route template is `/owners/{ownerId}/profile` and has a matching property. For headers, Spring processes header names to suit property binding (including stripping hyphens) and only adds them when not claimed by request parameters. **Do not rely on headers/path variables as a substitute for authorization**; the client can manipulate part of this data.

Important: **do not equate the static `WebExchangeDataBinder.extractValuesToBind(exchange)` with all additional sources that `ExtendedWebExchangeDataBinder` may add in a handler.** When manually creating a base binder via `new WebExchangeDataBinder(...)`, you are selecting the core query/form/multipart mechanism; do not expect path variables/headers to be automatically populated just like MVC annotation resolution.

## 3. Which Data Sources Are Bound?

### 3.1. Query parameters

~~~http
GET /search?name=Lan&age=21 HTTP/1.1
~~~

`getQueryParams()` retrieves key → list of values from the URI. With `@ModelAttribute`, this is one source for property binding. Query names can be nested/indexed paths such as `tags[0]` or `address.city` if the DTO supports them.

In **WebFlux**, `@RequestParam` primarily reads **query parameters**. Do not assume WebFlux's `@RequestParam` will read form bodies the same way habits from Servlet MVC might suggest. For HTML form objects, use `@ModelAttribute` or the `ServerWebExchange#getFormData()` API as intended.

### 3.2. Form URL-encoded

~~~http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&age=21&tags%5B0%5D=java
~~~

`getFormData()` returns `Mono<MultiValueMap<String,String>>`. `WebExchangeDataBinder` can extract form fields and merge them into the bind map. Values start as strings; converters transform them to the property type (`Integer`, `LocalDate`, enum, etc.) when the binder is suitably configured.

**You do not need to call `getFormData()` manually in an annotated handler before declaring `@ModelAttribute`**. Spring performs that step during argument resolution.

### 3.3. Multipart

~~~text
multipart/form-data
  field "name" -> text part
  field "avatar" -> file part
~~~

`getMultipartData()` returns `Mono<MultiValueMap<String,Part>>`. `WebExchangeDataBinder` supports multipart form data in binding; part contents are represented as `Part` or compatible types depending on binding configuration.

When handling **actual file uploads**, it is usually clearer to use `@RequestPart FilePart` or access `Part.content()`/`FilePart.transferTo(...)` via the reactive API, rather than assuming the binder will turn every uploaded file into an in-memory `byte[]`.

Very large multipart requests can consume resources when parsing all metadata/part lists; appropriate codec, server, and storage policy limits must be configured.

### 3.4. JSON does not go through form property binding

~~~http
POST /registrations-json HTTP/1.1
Content-Type: application/json

{"name":"Lan","age":21,"tags":["java"]}
~~~

In an `@RequestBody RegistrationForm` handler, JSON is typically read by `HttpMessageReader`/Jackson (in Spring WebFlux), **not by parsing HTML form field names like `tags[0]` through `WebExchangeDataBinder.bind(exchange)`**.

`@InitBinder#setAllowedFields(...)` controls **property binding**, not a replacement for JSON deserialization whitelisting. For JSON, you still need a dedicated request DTO, proper Jackson configuration, validation, and authorization.

### 3.5. Multiple values with the same name

`MultiValueMap` supports multiple values for one key:

~~~text
tag=java&tag=reactor
~~~

During extraction, the binder converts those values into a shape suited for property/constructor conversion. **Do not assert that every multi-valued key always becomes a `String` or a `List<String>`**; the outcome depends on value shape, target property type, and converters. When you need multiple elements with explicit indices for a model attribute, use `tags[0]`, `tags[1]` and test the actual structure.

## 4. Reactive Contract: `Mono<Void>` Must Be Executed

`WebExchangeDataBinder#bind(ServerWebExchange)` returns `Mono<Void>`. This Mono describes the work of reading relevant data sources and binding into the target. You cannot just write:

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");
binder.bind(exchange); // Wrong when ignoring the publisher.
return Mono.just(form);
~~~

The snippet above **illustrates a bug**, not code to deploy. Merely creating a publisher does not guarantee the work executes. You must return the publisher into the reactive chain or subscribe through an appropriate subscriber. Do not call `block()` on the WebFlux event loop.

Correct example in a helper/handler that has `form` and `exchange`:

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");

binder.setAllowedFields("name", "age", "tags[*]");

return binder.bind(exchange)
        .then(Mono.fromSupplier(() -> {
            if (binder.getBindingResult().hasErrors()) {
                return "binding-error";
            }
            return form.getName();
        }));
~~~

**This is a logic snippet to place inside a method returning `Mono<String>`**, with `import reactor.core.publisher.Mono`, not a standalone Java file. `then(...)` waits for binding to complete before reading the target. `Mono.fromSupplier(...)` defers reading the form until the downstream publisher is actually subscribed.

In standard annotated handlers, Spring manages the bind/validate chain for `@ModelAttribute`; you do not have to manually instantiate `WebExchangeDataBinder` in every endpoint. Manual binders are useful when writing infrastructure, adapters, or unit tests for binding behavior.

### `bind` does not automatically mean `validate`

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");
binder.setAllowedFields("name", "age");

// Wait for bind to complete before calling steps that use target.
Mono<Void> work = binder.bind(exchange);
~~~

The binder can record **conversion/typeMismatch errors**. However, constraint annotations like `@NotBlank`, `@Min` require a configured `Validator`, then calling `validate()` at the right moment, or using `@Valid` in an annotated controller for Spring to trigger. Do not treat `WebExchangeDataBinder` as a Bean Validation provider.

With `@Valid @ModelAttribute`, Spring runs validation according to the handler lifecycle and reports errors via `BindingResult` or the appropriate exception.

## 5. Runnable Spring Boot 3.5.7 Project

The following example keeps a focused scope:
- WebFlux (not Servlet MVC).
- `@ModelAttribute` receiving a URL-encoded form, including query + body.
- `@InitBinder` allowing only valid fields.
- `WebTestClient` verifying HTTP-level behavior.
- `MockServerWebExchange` and `WebExchangeDataBinder` verifying manual binder behavior without a server.
- Jakarta Validation for `@NotBlank`/`@Min`; `BindingResult` handling field errors.

Uses **Java 17**, Maven, and Spring Boot **3.5.7**. Structure:

~~~text
pom.xml
src/main/java/com/example/webfluxbind/
  WebFluxBindingApplication.java
  RegistrationForm.java
  RegistrationController.java
src/test/java/com/example/webfluxbind/
  RegistrationControllerTest.java
  WebExchangeDataBinderTest.java
~~~

### 5.1. Maven dependencies

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-exchange-binding</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-webflux` uses Reactor Netty and WebFlux controllers by default when the MVC starter is absent. `spring-boot-starter-validation` adds the Jakarta Bean Validation provider, `reactor-test` provides `StepVerifier`, and `spring-boot-starter-test` provides JUnit 5 / Spring test infrastructure.

If a project has **both `spring-boot-starter-web` and `spring-boot-starter-webflux`**, Spring Boot may default to the **Servlet MVC** application type. For this exercise to actually run WebFlux, add only the webflux starter as above, without mixing in the Servlet starter.

### 5.2. Main application

~~~java
// src/main/java/com/example/webfluxbind/WebFluxBindingApplication.java
package com.example.webfluxbind;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxBindingApplication.class, args);
    }
}
~~~

### 5.3. Form DTO

~~~java
// src/main/java/com/example/webfluxbind/RegistrationForm.java
package com.example.webfluxbind;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.ArrayList;
import java.util.List;

public class RegistrationForm {

    @NotBlank(message = "Name must not be blank")
    private String name;

    @NotNull(message = "Age is required")
    @Min(value = 18, message = "Minimum age is 18")
    private Integer age;

    private List<@NotBlank String> tags = new ArrayList<>();

    // Intentionally includes a property users are not allowed to modify.
    private boolean admin;

    public RegistrationForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
~~~

This form uses a mutable JavaBean with a default constructor and getters/setters to illustrate **property binding**. `List<@NotBlank String>` allows validating each element when validation runs; for `List`, the Bean Validation provider usually has a built-in value extractor.

`admin` is only used to demonstrate the *mass assignment/over-posting* risk and how `allowedFields` prevents clients from updating it. In production code, a better approach is to **avoid sensitive properties on request DTOs altogether**.

### 5.4. Controller using `@ModelAttribute` and `@InitBinder`

~~~java
// src/main/java/com/example/webfluxbind/RegistrationController.java
package com.example.webfluxbind;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "tags[*]");
        binder.setAutoGrowCollectionLimit(10);
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> register(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            Map<String, Object> payload = Map.of("invalidFields", fields);
            return Mono.just(ResponseEntity.badRequest().body(payload));
        }

        Map<String, Object> payload = Map.of(
                "name", form.getName(),
                "age", form.getAge(),
                "tags", form.getTags(),
                "admin", form.isAdmin()
        );
        return Mono.just(ResponseEntity.ok(payload));
    }

    // Unlike the method above: NO BindingResult after the object.
    @PostMapping(path = "/strict",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> strict(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form) {
        return Mono.just("accepted:" + form.getName());
    }
}
~~~

`@InitBinder("registrationForm")` applies only to the binder associated with that exact object name, not to every argument. `setAllowedFields` is the whitelist for **property binding**. Here, the client may bind `name`, `age`, and each `tags[i]`, but **cannot bind `admin`**.

`setAutoGrowCollectionLimit(10)` limits list/array auto-growth when setter property binding uses indexed paths. This is **not an HTTP request size limit** or an overall form field count limit.

In `register`:
- `BindingResult` is placed **immediately after** the `@ModelAttribute` parameter, so the handler can safely return the list of field errors.
- On error, it returns 400 with field names, without returning sensitive rejected values.
- When valid, it returns a JSON summary; `Mono.just` suffices for an example with no asynchronous business logic, while binding at the argument resolution layer has already been completed by the framework before the method is invoked.

In `strict`, there is no `BindingResult`. If validation of `RegistrationForm` fails, WebFlux typically throws `WebExchangeBindException` and defaults to returning HTTP 400 before running the controller body.

There is no need to create `new WebExchangeDataBinder(...)` inside `RegistrationController`: the WebFlux argument resolver already manages the binder and validation.

### 5.5. HTTP-level tests with `WebTestClient`

~~~java
// src/test/java/com/example/webfluxbind/RegistrationControllerTest.java
package com.example.webfluxbind;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class RegistrationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bindsQueryAndFormAndSuppressesAdmin() {
        client.post()
                .uri("/registrations?age=21")
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("tags[0]", "java")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(21)
                .jsonPath("$.tags[0]").isEqualTo("java")
                .jsonPath("$.admin").isEqualTo(false);
    }

    @Test
    void reportsBeanValidationFieldErrors() {
        client.post()
                .uri("/registrations")
                .body(BodyInserters.fromFormData("name", " ")
                        .with("age", "16"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields").isArray()
                .jsonPath("$.invalidFields[0]").isEqualTo("age")
                .jsonPath("$.invalidFields[1]").isEqualTo("name");
    }

    @Test
    void reportsConversionErrorForAge() {
        client.post()
                .uri("/registrations")
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "not-a-number"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("age");
    }

    @Test
    void strictFormWithoutBindingResultReturnsBadRequest() {
        client.post()
                .uri("/registrations/strict")
                .body(BodyInserters.fromFormData("name", " ")
                        .with("age", "16"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

`BodyInserters.fromFormData(...)` creates an `application/x-www-form-urlencoded` request body, so it directly exercises WebFlux's form reading path instead of JSON. Spring Boot test auto-configures `WebTestClient` bound to the WebFlux application context.

What is verified:
1. Query `age` and body `name/tags` both populate `RegistrationForm`.
2. Client sends `admin=true` but the response is `false` due to `allowedFields`.
3. Bean Validation with `@NotBlank`/`@Min` produces field errors `age` and `name`.
4. A string that cannot convert to `Integer` produces a binding error for `age`.
5. An endpoint without `BindingResult` returns HTTP 400 for an invalid form.

In test 2, field names are sorted by the controller, so index 0 is `age` and index 1 is `name`. Do not enforce internal error ordering inside `BindingResult` (it is not a critical contract); only the ordering **explicitly sorted by the controller** is deterministic.

### 5.6. Reading `ServerWebExchange` directly and calling `WebExchangeDataBinder`

This lesson distinguishes between "WebFlux automatically binding via `@ModelAttribute`" and "explicitly using `WebExchangeDataBinder`". The following test does not start an HTTP server; instead it creates a mock exchange and inspects target state once `Mono<Void>` completes.

~~~java
// src/test/java/com/example/webfluxbind/WebExchangeDataBinderTest.java
package com.example.webfluxbind;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.bind.support.WebExchangeDataBinder;
import reactor.test.StepVerifier;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebExchangeDataBinderTest {

    private MockServerWebExchange newExchange() {
        return MockServerWebExchange.from(
                MockServerHttpRequest.post("/registrations?age=21")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body("name=Lan&tags%5B0%5D=java&admin=true"));
    }

    @Test
    void bindReturnsMonoAndUpdatesObjectWhenSubscribed() {
        RegistrationForm form = new RegistrationForm();
        WebExchangeDataBinder binder =
                new WebExchangeDataBinder(form, "registrationForm");

        binder.setAllowedFields("name", "age", "tags[*]");

        StepVerifier.create(binder.bind(newExchange()))
                .verifyComplete();

        assertEquals("Lan", form.getName());
        assertEquals(21, form.getAge());
        assertEquals("java", form.getTags().get(0));
        assertFalse(form.isAdmin());
        assertArrayEquals(
                new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields()
        );
    }

    @Test
    void extractionCanBeObservedBeforeBinding() {
        StepVerifier.create(
                WebExchangeDataBinder.extractValuesToBind(newExchange()))
                .assertNext(values -> {
                    assertEquals("Lan", values.get("name"));
                    assertEquals("21", values.get("age"));
                    assertTrue(values.containsKey("tags[0]"));
                    assertTrue(values.containsKey("admin"));
                })
                .verifyComplete();
    }

    @Test
    void bindDoesNotImplicitlyRunBeanValidation() {
        RegistrationForm form = new RegistrationForm();
        WebExchangeDataBinder binder =
                new WebExchangeDataBinder(form, "registrationForm");
        binder.setAllowedFields("name", "age");

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.post("/registrations?age=16")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body("name=%20"));

        StepVerifier.create(binder.bind(exchange))
                .verifyComplete();

        // Both " " and 16 can be converted: no binding error.
        assertEquals(" ", form.getName());
        assertEquals(16, form.getAge());
        assertFalse(binder.getBindingResult().hasErrors());

        // @NotBlank and @Min only run when there is a validator/validation step.
    }
}
~~~

In test 2, `extractValuesToBind(...)` is the API for observing the map **before whitelisting and property assignment**. The presence of the `admin` key in the source map **does not mean** it must be allowed to bind; `setAllowedFields` governs the subsequent bind step.

**A note on extraction tests:** Javadoc confirms the returned map contains values for binding; how Spring represents scalars versus lists/arrays can depend on how many times a key appears. In this fixture each key appears only once, so `name`/`age` are expected to be single strings. When upgrading the framework/provider or changing fixtures with multiple values, test **property-level behavior** rather than depending on every internal map detail.

Run all tests:

~~~bash
mvn test
~~~

**Expected result:** 7 JUnit tests PASS (4 `RegistrationControllerTest` + 3 `WebExchangeDataBinderTest`). This states the expected outcome based on the presented API and code, **not an actual execution log**. Maven/Surefire may format test order and stdout differently.

Start the server to try with curl:

~~~bash
mvn spring-boot:run
~~~

After the server starts:

~~~bash
curl -i -X POST "http://localhost:8080/registrations?age=21" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "tags[0]=java" \
  --data-urlencode "admin=true"
~~~

Expected JSON response (key order not guaranteed):

~~~json
{
  "name": "Lan",
  "age": 21,
  "tags": ["java"],
  "admin": false
}
~~~

The example does not persist data to a database; `admin=false` is a whitelist result, not standalone proof of a complete authorization system.

## 6. Validation and Binding Errors in WebFlux

### 6.1. Conversion/binding errors

When a request sends:

~~~text
age=not-a-number
~~~

and the DTO has `Integer age`, the converter fails to produce a value. `BindingResult` records a `FieldError` for `age`; the error code is typically `typeMismatch`. This error occurs during **binding**, not from `@Min(18)`.

When sending:

~~~text
age=16
~~~

conversion succeeds, but `@Min(18)` detects a value below the threshold once Jakarta Bean Validation is triggered.

In an annotated handler, use:

~~~java
@PostMapping("/example")
public Mono<String> save(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just("invalid");
    }
    return Mono.just("ok");
}
~~~

This is **a separate illustrative method**, not present in `RegistrationController` of the runnable project. `BindingResult` **must immediately follow `@ModelAttribute`**; otherwise, Spring may not associate errors with the right argument.

### 6.2. `WebExchangeBindException`

For an `@Valid @ModelAttribute` form without a `BindingResult` immediately following it, when validation fails, WebFlux typically raises:

~~~java
org.springframework.web.bind.support.WebExchangeBindException
~~~

This exception holds `getBindingResult()` with `FieldError`/`ObjectError` and is normally mapped to HTTP **400 Bad Request**.

Do not confuse WebFlux's `WebExchangeBindException` with `MethodArgumentNotValidException` commonly seen in Servlet MVC. In Spring WebFlux 6.1+, **if a controller has direct method constraints** like `@RequestParam @Min(1)` on other arguments or a return constraint, method validation may take precedence and raise `HandlerMethodValidationException`. Error handling code should account for both types according to the handler signature.

### 6.3. Model attribute with a reactive wrapper

WebFlux allows:

~~~java
// Illustrative method belonging to a @RestController.
@PostMapping("/reactive")
public Mono<String> submitReactive(
        @Valid @ModelAttribute("registrationForm")
        Mono<RegistrationForm> formMono) {

    return formMono
            .map(form -> "ok:" + form.getName())
            .onErrorResume(
                    WebExchangeBindException.class,
                    error -> Mono.just("invalid"));
}
~~~

This approach lets you handle errors inside the reactive chain. **Do not declare `BindingResult` immediately after `Mono<RegistrationForm>`**: according to WebFlux documentation, using `BindingResult` directly requires the `@ModelAttribute` argument **not to be wrapped in a reactive type**. When using a reactive wrapper, handle validation errors via `onErrorResume`/`onErrorMap` or an appropriate error handling mechanism.

When building an HTTP response, do not simply return the string `"invalid"` with status 200 as in the snippet above if the API requires a 400 error. In real code, return `ResponseEntity.badRequest()` or handle exceptions globally; this snippet only demonstrates the reactive error-handling branch.

### 6.4. Method-level constraints since Spring Framework 6.1

You can write:

~~~java
@GetMapping("/lookups")
public Mono<String> lookup(@RequestParam @NotBlank String key) {
    return Mono.just(key);
}
~~~

In WebFlux 6.1+, a direct constraint `@NotBlank` on a method parameter triggers built-in **method validation**; an invalid value can raise `HandlerMethodValidationException`. This mechanism differs from object-only `@Valid @ModelAttribute`.

Note: class-level `@Validated` on a controller can route method validation through the AOP proxy path. When you want to use built-in method validation in WebFlux 6.1+, do not add class-level `@Validated` solely to enable a mechanism the framework already provides.

## 7. Constructor Binding and `construct(exchange)`

Since Spring Framework 6.1, `DataBinder`/`WebExchangeDataBinder` supports **constructor binding**, which is useful for immutable objects. Unlike property binding that uses setters, constructor binding finds a primary/single constructor whose parameters match request values and invokes it after type conversion.

~~~java
public record RegistrationCommand(
        String name,
        Integer age,
        List<String> tags
) {
}
~~~

This is an **alternative DTO** for illustration, not part of the mutable source code running in section 5.

In `@ModelAttribute RegistrationCommand command`, the framework can construct the record from query/form data; `@BindParam` can be used to map a request name that differs from the constructor parameter name. Constructor binding supports lists/maps/arrays through converted strings or indexed/keyed names like `tags[0]` and `accounts[2].name`.

API for infrastructure builders:

~~~java
Mono<Void> construct(ServerWebExchange exchange);
~~~

**You cannot replace it with `new WebExchangeDataBinder(null).bind(exchange)` to create a record** and expect Spring to infer which class is needed: the binder must know the target type/constructor to instantiate, and after construction you must check `getBindingResult()`. In annotated controllers, let the framework do this unless you are genuinely building a custom argument resolver.

Methods `setAutoGrowNestedPaths` and `setAutoGrowCollectionLimit` are meant for **property binding** when assigning JavaBean properties; they do not govern every aspect of constructor binding by default. Therefore, replacing a mutable DTO with a record is a decision that requires testing input names, conversion, constructor errors, and validation separately.

### Protecting constructor/property binding

Spring recommends models tailored for web input or constructor binding where appropriate. If you still must property-bind an object with many fields, use `setAllowedFields(...)` as a whitelist. `setDeclarativeBinding(true)` can be used to favor constructor binding and permit property binding only for allowed fields; however, you must still ensure the constructor accepts only what the caller is authorized to supply.

## 8. Data Sources Story: Query, Form, URI Variables, and Headers

A model attribute handler can combine:
- Query parameters.
- URL-encoded form fields or multipart fields/parts.
- URI template variables.
- Request headers after name normalization.

**Precedence matters:** Spring WebFlux documentation describes that form data and query parameters take precedence over URI variables/headers. Do not rely on "request headers are more authoritative than forms" for a property with the same name. If you need a route value with access-control significance like `userId`, use a separate `@PathVariable` and enforce authorization in the service, **do not hide it inside a form DTO with a setter**.

Example:

~~~java
@PostMapping("/customers/{customerId}")
public Mono<String> update(
        @PathVariable long customerId,
        @Valid @ModelAttribute CustomerForm form) {
    // customerId is used separately for authorization/lookup;
    // CustomerForm only contains fields the client is allowed to edit.
    return Mono.just("received");
}
~~~

The method above illustrates architecture, not a component of the project in section 5. `CustomerForm` is assumed to be a DTO with appropriate web-input properties.

Do not arbitrarily feed all exchange attributes/session/principal into the binder. Those attributes serve dedicated purposes; security context data should be authenticated and provided by Spring Security, not taken from form headers self-declaring as "admin".

### Limits when reading the body

`ServerWebExchange.getFormData()` parses **the entire** URL-encoded body to build a `MultiValueMap` and caches the result. `getMultipartData()` similarly collects a map of part metadata. That **does not mean** WebFlux can process arbitrarily large forms without memory cost—it only means the I/O API is reactive.

To block oversized requests or excessive parts:
- Configure codec `maxInMemorySize` and multipart handling suited to your deployment.
- Limit request body size at the reverse proxy/server gateway.
- Validate total field count, list/map element count, and nested path depth.
- Reject or cap file uploads by type/size/quota before passing them to business processing.
- With file streaming, consume/store `Part` according to the reactive contract; do not re-read `Part.content()` once it has been consumed.

## 9. Security: `setAllowedFields` and Mass Assignment

When property binding accepts user-supplied key names, names such as:

~~~text
admin=true
account.ownerId=another-user
roles[0]=ADMIN
settings.billingEnabled=true
~~~

can mutate the object graph if the target has setters and the binder permits them. This is a *mass assignment* and *over-posting* issue, not a format validation error.

### 9.1. Whitelisting as a line of defense

~~~java
@InitBinder("registrationForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "tags[*]");
}
~~~

The `admin` field is not in the whitelist, so it is **suppressed** when the property binder extracts values from the request. You can inspect:

~~~java
String[] ignored = binder.getBindingResult().getSuppressedFields();
~~~

If you are inside an annotated controller and only have `BindingResult errors`, you can use `errors.getSuppressedFields()` since the `BindingResult` interface exposes this API. Do not confuse suppressed fields with `FieldError`: a field blocked by the whitelist **is not necessarily a validation error**.

### 9.2. Separating DTOs from domain entities

It is better not to have setters for `admin`, `role`, `ownerId`, `approved`, `paid` on public input DTOs. In practice:
1. Parse/bind into a small DTO containing only expected fields.
2. Validate format, size, constraints, and semantics.
3. Authenticate principal and check authorization.
4. Let the service verify domain invariants and map to the entity.
5. Never take role/owner solely from request body/query/header.

Do not bind `@ModelAttribute` directly onto sensitive JPA entities/aggregates with many nested properties.

### 9.3. Indexed paths and auto-grow

`tags[0]` is a normal property path, but a malicious request can send `tags[999999]` to force the binder to allocate many elements or hit an exception. Use `setAutoGrowCollectionLimit(10)` in the example to cap list auto-growth to the form's scale.

**Auto-grow limits do not replace request size limits**; do not assume every out-of-bounds index automatically turns into a `FieldError` or HTTP 400 consistently. Ensure proper boundary checks, parameter count limits, and error handling in production.

### 9.4. Validation is not authorization

`@Min(18)` checks minimum age; it does not verify whether the user is authorized to register for another `accountId`. `@NotBlank` checks name; it does not stop a user from spoofing an email. Even when a DTO is completely valid, all access control and state transition rules must still be verified by trusted system logic.

## 10. Common Pitfalls and Fixes

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| `bind(exchange)` is called but target does not change | Did not subscribe/compose `Mono<Void>` | Return the publisher in the reactive chain or use `StepVerifier` in tests |
| Application blocks the event loop while binding | Called `block()` in handler | Use `then`, `flatMap`, `map`, and non-blocking callbacks |
| `@ModelAttribute` does not receive JSON body | JSON does not go through form property binder | Use `@RequestBody`/Jackson |
| `@RequestParam` does not read form fields | WebFlux `@RequestParam` reads query params | Use `@ModelAttribute` or `getFormData()` |
| `age=oops` fails to bind to `Integer` | Type conversion failure | Read `BindingResult`, error code `typeMismatch` |
| `name=" "` binds successfully despite `@NotBlank` | Bean Validation did not run | Use `@Valid`/`@Validated` in controller or configure and call binder.validate() |
| `BindingResult` missing in handler | Placed in wrong position or form wrapped in `Mono<T>` | Place immediately after non-reactive `@ModelAttribute`, or handle reactive errors |
| `WebExchangeBindException` is thrown | Invalid model attribute without immediate `BindingResult` | Add error handling or `BindingResult` |
| `HandlerMethodValidationException` raised instead of `WebExchangeBindException` | Direct method constraint triggers method validation | Check handler signature and exception policy |
| `admin` property changes via request | Over-posting, missing DTO/allowed fields | Use a dedicated DTO and whitelist |
| Route/header key overwritten by form | Source precedence of annotated binding | Separate `@PathVariable`/`@RequestHeader` from form for trusted handling |
| Multipart `Part` can only be read once | Content stream is not cached | Consume `Part.content()`/transferTo once |
| `tags[999999]` causes error or allocation | Auto-grow/index out of bounds | Configure limit, reject request early, check element count |
| Spring Boot app actually runs MVC | Both MVC and WebFlux starters present | Use only `spring-boot-starter-webflux` for demo, check web application type |
| Using `HttpServletRequest` in WebFlux | Confusing Servlet stack with reactive stack | Use `ServerWebExchange`/`ServerHttpRequest` |
| Mock exchange test behaves differently from real HTTP | Codecs/headers/body format mismatch | Use `WebTestClient` for integration, unit binder tests with matching Content-Type |

### Scenario: same key sent in both query and form

For example, a request has `name=Query` in the URL and `name=Form` in the body. Do not base critical business logic on assuming one source always beats the other across all framework layers and versions. You can:
- Disallow clients from sending the same field in both sources.
- Read the specific source directly via `exchange.getRequest().getQueryParams()` or `exchange.getFormData()` if the business contract requires it.
- Write integration tests for duplicate-key cases and document precedence clearly in the API contract.
- Never use client-modifiable sources as proof of authentication/authorization.

### Scenario: which field has the error?

`BindingResult#getFieldErrors()` contains `FieldError#getField()` as the field name, which may be `age` or an indexed path like `tags[0]`. If the application returns an API response, expose controlled field names and error codes; do not return raw `getRejectedValue()` if the data may be sensitive.

## 11. When to Instantiate `WebExchangeDataBinder` Manually?

**Most annotated WebFlux controllers do not need to create a binder manually**. Using `@ModelAttribute`, `@InitBinder`, `@Valid`, and `BindingResult` is sufficient; the framework handles lifecycle, body reading, and model setup.

Use a binder manually when:
- Writing a component/test that needs to bind data from `ServerWebExchange` into a target you instantiate yourself.
- Needing custom binding infrastructure outside the annotated controller path.
- Needing to inspect the exact extraction/binding/conversion phase.
- Building a custom argument resolver, with clear understanding of constructor/target types, validation, and lifecycle.

Manual checklist:

~~~text
1. Identify target bean/type and objectName.
2. Choose allowed fields, conversion, auto-grow, validators.
3. Obtain a ServerWebExchange from a valid context.
4. Call binder.bind(exchange) or construct(exchange) as appropriate.
5. Compose the Mono into the reactive chain, without dropping subscription.
6. After completion, inspect BindingResult and the target.
7. If Bean Validation is needed, trigger it explicitly—do not rely on implicit bind.
8. Do not return raw request values or sensitive information.
~~~

## 12. Summary and Practice Exercises

**Remember:**

- `WebExchangeDataBinder` turns query/form/multipart input from `ServerWebExchange` into property/constructor values for a Java object.
- `ServerWebExchange` is the reactive context of an HTTP interaction; `getFormData()`/`getMultipartData()` return `Mono` and must be consumed following the lifecycle.
- `WebExchangeDataBinder.bind(exchange)` returns `Mono<Void>`, which does not mean "already bound as soon as the call is written".
- `@ModelAttribute` is the standard approach; `@RequestBody` JSON goes through `HttpMessageReader`, not the same property binder.
- Spring WebFlux has `WebExchangeBindException` for object-only validation and `HandlerMethodValidationException` when method constraints require method validation.
- `BindingResult` must be placed immediately after a **non-reactive `@ModelAttribute`** if you want to handle errors inside the handler.
- Binding security requires dedicated input DTOs, whitelists, and resource limits—not just field constraints.

**Exercises:**
1. Add a `country` field with a converter from codes `VN`/`SG` to an enum; test valid/invalid conversion.
2. Add `tags[1]` and `tags[2]` in the request, verify order and `@NotBlank` error on an empty element.
3. Replace `RegistrationForm` with an immutable record and compare constructor binding with property binding.
4. Try sending `admin=true`, `tags[9999]`, and a very large body; clearly explain which mechanism blocks each case.
5. Try a `Mono<RegistrationForm>` handler and handle `WebExchangeBindException` in the reactive chain; compare with `BindingResult` immediately after a non-reactive form.
6. Send multipart data and process a `FilePart` via reactive transfer while keeping the form DTO free of any allowed field holding file bytes.

## 13. References

- Spring Framework 6.2 — WebFlux `@ModelAttribute` (data sources, constructor/property binding, reactive wrappers, errors): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — WebFlux `@InitBinder` and data binding security: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2 — WebFlux validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 — Reactive Core, form and multipart data: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — `ServerWebExchange` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2 — `WebExchangeDataBinder` Javadoc (6.2.6): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/support/WebExchangeDataBinder.html
- Spring Framework 6.2 — `WebExchangeBindException`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html
- Spring Boot 3.5 — Testing with `WebTestClient`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
