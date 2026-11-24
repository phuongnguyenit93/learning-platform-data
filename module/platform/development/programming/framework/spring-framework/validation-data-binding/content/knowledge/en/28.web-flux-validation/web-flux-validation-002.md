# Binding @ModelAttribute in the Reactive Stack (Spring WebFlux)

## Lesson Objectives

Spring WebFlux is Spring Framework's reactive web stack, typically running on Reactor Netty. When receiving an HTML form, an application still needs to map field names and values from HTTP into a Java object, convert types, run Bean Validation, and report errors. Spring provides `@ModelAttribute` along with `WebDataBinder` to do this. **The difference from Spring MVC is not abandoning data binding, but that WebFlux can resolve models/arguments through a reactive stream and accept `Mono<Form>` directly.**

After this lesson, you can:

- Understand where `@ModelAttribute` gets data in WebFlux, and how it differs from `@RequestParam` and `@RequestBody`.
- Describe constructor/property binding, type conversion, nested property names, and validation.
- Use two handler styles: **plain object + `BindingResult`** and **`Mono<DTO>` + `onErrorResume(...)`**.
- Inspect `WebExchangeBindException`, distinguishing binding/validation errors from `HandlerMethodValidationException`.
- Write a Spring Boot 3 / Java 17+ example running on WebFlux, featuring two endpoints with the same data rules but two error-handling styles.
- Test via `WebTestClient` and avoid blocking, mass assignment, losing rejected values, or confusing forms with JSON.

## 1. What Does @ModelAttribute Do in WebFlux?

Example HTTP client request:

~~~http
POST /forms/plain
Content-Type: application/x-www-form-urlencoded

name=Lan&age=22&address.city=Ha+Noi
~~~

The target object has these properties:

~~~java
class SignupForm {
    String name;
    Integer age;
    Address address;
}

class Address {
    String city;
}
~~~

`@ModelAttribute("signup")` tells Spring WebFlux to create/retrieve the corresponding object and bind matching named data:

| Request field | Java property | Action |
| --- | --- | --- |
| `name=Lan` | `SignupForm.name` | Assign string |
| `age=22` | `SignupForm.age` | Convert `"22"` to `Integer 22` |
| `address.city=Ha Noi` | `SignupForm.address.city` | Traverse nested property and assign string |
| `age=abc` | `Integer age` | Conversion fails; record `typeMismatch` error |
| `name=` | `String name` with `@NotBlank` | Binds empty string, but violates constraint |

In WebFlux, `@ModelAttribute` on a handler argument supports form data, query parameters, URI path variables, and matching request headers. When multiple sources share the same name, **form/query parameters take precedence over path variables and headers**; header names undergo their own normalization. Do not treat this as permission for clients to write arbitrary properties: design dedicated DTOs and allowlists.

Logical flow:

~~~text
HTTP request
   |--- query parameters
   |--- application/x-www-form-urlencoded body
   |--- path variables / request headers
   v
WebFlux annotated controller argument resolution
   v
@ModelAttribute("signup")
   |--- retrieve existing model attribute / session if configured
   |--- or instantiate object via matching constructor
   v
WebDataBinder
   |--- constructor binding / property binding
   |--- ConversionService, Formatter, PropertyEditor
   |--- record FieldError if conversion/binding fails
   v
@Valid / @Validated (if declared)
   |--- validate bean constraints
   |--- cascade along @Valid edges
   v
BindingResult or WebExchangeBindException
   v
handler response / view / reactive pipeline
~~~

WebFlux uses reactive types to coordinate I/O without requiring the application to manually call `subscribe()` or `block()`. However, **do not assume Bean Validation or Java property binding automatically become asynchronous tasks**: type conversions, metadata checks, and many validators still execute synchronously once the data is ready. Do not put JDBC or blocking network calls into validators or handlers on the event loop.

## 2. Relevant Differences Between WebFlux and Spring MVC

| Topic | Spring MVC (Servlet stack) | Spring WebFlux (reactive stack) |
| --- | --- | --- |
| Server foundation | Servlet API, typically Tomcat | Reactive server API, typically Reactor Netty |
| `@ModelAttribute SignupForm form` | Supported | Supported |
| `@ModelAttribute Mono<SignupForm> formMono` | Not a standard MVC pattern | Supported |
| Model containing `Mono<Profile>` | Not via native WebFlux mechanism | Supported; can be resolved before handler/view |
| `BindingResult` immediately after plain object | Yes | Yes |
| `BindingResult` immediately after `Mono<Form>` | Not appropriate | **Not supported**: requires non-wrapped argument |
| `@RequestParam` with form body | Servlet merges query/form into request parameters | `@RequestParam` mainly reads **query parameters only** |
| Form fields + query bound into command object | Yes | Yes |
| JSON body | `@RequestBody` + message converter | `@RequestBody` + reactive HTTP message reader/codecs |
| Unhandled individual `@ModelAttribute` validation error | Usually `MethodArgumentNotValidException` | Usually **`WebExchangeBindException`** |
| Handling errors at the end of a reactive pipeline | Servlet exception handling | Additionally supports `Mono.onErrorResume(...)` or `@ExceptionHandler` |

**Key point to remember:** `@RequestParam` in WebFlux reads **query parameters**, not form body field names the way Servlet API merges them. If you need to bind multiple fields of an `application/x-www-form-urlencoded` form, use `@ModelAttribute` (or `ServerWebExchange.getFormData()` when raw control is needed). Do not turn a form into `@RequestBody Mono<Form>` expecting Jackson to read form data as JSON.

## 3. Two Valid Handler Signatures

### 3.1. Plain object and BindingResult

~~~java
@PostMapping("/plain")
public Mono<String> handle(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just("signup-form");
    }
    return Mono.just("redirect:/forms/success");
}
~~~

This is a **snippet depicting a view-rendering handler**, assuming a DTO, template, and matching controller exist. `BindingResult` must come **immediately after** `SignupForm`. When errors occur, the controller can re-render the form within the same HTTP request. `Mono<String>` is the handler's return type; it does not mean the argument must be `Mono<Form>`.

`BindingResult` holds both conversion and validation errors. For example, if `age=abc` while `age` is an `Integer`, the Java bean may receive `null`, whereas `errors.getFieldError("age").getRejectedValue()` and `errors.getFieldValue("age")` can still preserve `"abc"` for re-display.

### 3.2. Reactive wrapper and onErrorResume

~~~java
@PostMapping("/wrapped")
public Mono<String> handleReactive(
        @Valid @ModelAttribute("signup")
        Mono<SignupForm> formMono) {

    return formMono
            .flatMap(form -> Mono.just("redirect:/forms/success"))
            .onErrorResume(
                    WebExchangeBindException.class,
                    ex -> Mono.just("signup-error"));
}
~~~

This snippet illustrates **in-pipeline handling**, not a standalone handler from section 5's demo. When using `Mono<SignupForm>`, **do not place `BindingResult` immediately after the Mono**: Spring only allows a `BindingResult` parameter when the preceding `@ModelAttribute` is a **non-reactive object**. With a wrapped form, a binding/validation failure can be emitted as an `onError` signal; you can use `onErrorResume(WebExchangeBindException.class, ...)` to map it to an appropriate response or view.

This example returns a generic error view; if you actually want to re-render **the entered values**, you must properly transfer the object and errors from `ex.getBindingResult()`/`ex.getModel()` into the view model, or choose the simpler plain-object + `BindingResult` style. Do not just return a new view name assuming the Mono's data is automatically preserved in the model.

### 3.3. What is incorrect

~~~java
// WRONG: BindingResult cannot be paired with Mono<Form>
@PostMapping("/broken")
Mono<String> broken(
        @Valid @ModelAttribute("signup") Mono<SignupForm> form,
        BindingResult errors) {
    return Mono.just("signup-form");
}
~~~

This is an **anti-pattern** that violates the documented contract. Do not mechanically apply the "always put BindingResult right after the form" rule while ignoring the reactive wrapper type.

## 4. How Does Spring WebFlux Receive Forms?

### 4.1. Form URL-encoded

Common content type for HTML forms:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

The request body consists of URL-encoded `name=value` pairs. Spring reads that data via appropriate APIs and binds it by property names on the command object. For example, `address.city` is a nested property name. Do not send a JSON object in this body expecting `@ModelAttribute` to deserialize it with Jackson.

### 4.2. Query and path variables

`@ModelAttribute` can pull values from query/path/headers alongside form fields. With `POST /owners/42/edit?name=Lan`, `name` can be bound from the query; only when the model has a matching property is the value applied. When a field with the same name appears in multiple sources, form/query takes precedence over path/header. Binding policies must be enforced so attackers cannot abuse alternate data sources.

In a handler needing **a single query parameter**, `@RequestParam("page") int page` is appropriate. However, WebFlux's `@RequestParam("name")` alone **does not** read the form body under Spring MVC conventions. This is a major source of confusion when migrating apps from Servlet to the reactive stack.

### 4.3. Multipart

WebFlux handles multipart with dedicated infrastructure (e.g., `FilePart`/`Part`). Data binding can pull form fields and parts into a command object where appropriate, but for large files use streaming-aware APIs and upload/file-size policies; avoid holding entire files in a Java bean just to fit `@ModelAttribute` when a better mechanism exists.

### 4.4. JSON takes a different path

With:

~~~http
POST /api/orders
Content-Type: application/json

{"name":"Lan","age":22}
~~~

Controllers normally choose `@RequestBody OrderDto` or `@RequestBody Mono<OrderDto>`. Spring WebFlux reads the content through codecs/message readers. Therefore:

- `@ModelAttribute`: targets form/query/path/header data binding into a command object.
- `@RequestBody`: targets decoding the HTTP body by media type, such as JSON.
- `@RequestParam`: individual query parameter in WebFlux.

Choose the annotation based on **data source and format**, not merely on whether the handler's return type is `Mono`.

## 5. Java 17+ / Spring Boot 3.5.7 Example: Two Binding Paths

This example uses **WebFlux with REST-style text responses** to clearly show the status, values, and errors of both handler styles without depending on a template engine. Section 7 then explains how to use the same data to render an HTML form. The example uses no Spring MVC, no database, and never blocks threads with `block()`.

### 5.1. Project structure

~~~text
webflux-modelattribute-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/webflux/
    │       ├── FormsApplication.java
    │       ├── SignupForm.java
    │       └── FormController.java
    └── test/
        └── java/com/example/webflux/
            └── FormControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
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
    <artifactId>webflux-modelattribute-demo</artifactId>
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

`spring-boot-starter-webflux` selects WebFlux with Reactor Netty under standard Boot defaults. `spring-boot-starter-validation` provides the Jakarta Bean Validation provider; `spring-boot-starter-test` supports JUnit and WebTestClient.

**Do not add `spring-boot-starter-web` out of Spring MVC habit.** When both MVC and WebFlux starters are present in a Spring Boot application, Boot defaults to the Servlet/MVC application type unless explicitly overridden; that can make you think you are running WebFlux when you are not. This demo intentionally includes only the WebFlux starter.

### 5.3. FormsApplication.java

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormsApplication.class, args);
    }
}
~~~

### 5.4. SignupForm.java — form DTO

~~~java
package com.example.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @Valid
    private Address address = new Address();

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

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public static class Address {
        @NotBlank
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
~~~

Three rules:

1. `name` must contain non-whitespace text (`@NotBlank`).
2. `age` must be present and at least 18 (`@NotNull` + `@Min(18)`).
3. `address.city` must be non-blank **because** `address` is annotated with `@Valid`, causing the validator to descend into the child object.

`address` is initialized so property binding can populate `address.city`. `@Valid` alone skips a null object; if business logic requires `address` to be non-null, also put `@NotNull` on that field. For HTML forms, using mutable JavaBean properties in the DTO keeps the example easy to follow; in production code, consider constructor binding/immutable DTOs where appropriate.

### 5.5. FormController.java — plain and wrapped

~~~java
package com.example.webflux;

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
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

import java.util.stream.Collectors;

@RestController
@RequestMapping("/forms")
public class FormController {

    @InitBinder("signup")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "name", "age", "address.city");
    }

    private static String fields(BindingResult errors) {
        return errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static String summary(SignupForm form) {
        return form.getName()
                + "/" + form.getAge()
                + "/" + form.getAddress().getCity();
    }

    @PostMapping(
            path = "/plain",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> plain(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body("invalid:" + fields(errors)));
        }

        return Mono.just(ResponseEntity.ok(
                "accepted:" + summary(form)));
    }

    @PostMapping(
            path = "/wrapped",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> wrapped(
            @Valid @ModelAttribute("signup")
            Mono<SignupForm> formMono) {

        return formMono
                .map(form -> ResponseEntity.ok(
                        "accepted:" + summary(form)))
                .onErrorResume(
                        WebExchangeBindException.class,
                        ex -> Mono.just(
                                ResponseEntity.badRequest().body(
                                        "invalid:" + fields(ex))));
    }
}
~~~

**Analysis:**

- `plain(...)` uses a plain object with `BindingResult` right after it so the handler can explicitly check `hasErrors()`. The return type is `Mono<ResponseEntity<String>>` because the response follows the reactive handler contract.
- `wrapped(...)` takes `Mono<SignupForm>`, **without adding `BindingResult`**. If binding/validation fails, the error is handled via `onErrorResume(WebExchangeBindException.class, ...)`.
- `WebExchangeBindException` exposes the `BindingResult` APIs, so the `fields(BindingResult)` helper works for both modes. `FieldError.getField()` returns field names like `age` or `address.city`.
- `distinct().sorted()` keeps responses deterministic when one field has multiple errors (`@NotNull`, `typeMismatch`, etc.) or the provider emits errors in varying order.
- `summary(form)` is only called after the form passes validation; the demo outputs only non-sensitive values. Do not expose raw `getInvalidValue()` or `rejectedValue` in production HTTP responses.
- `@InitBinder("signup")` allows binding strictly those three properties and blocks arbitrary writes to other fields. This complements DTO design rather than replacing validation.
- There is no `Thread.sleep(...)`, `block()`, or blocking I/O in the handler. For real persistence, use reactive APIs (e.g., R2DBC) instead of blocking the event loop with JDBC.

In this code `@RestController` was chosen **solely to output easily testable text**. `@ModelAttribute` works in both HTML-rendering `@Controller` and `@RestController`; the response type does not alter binding rules.

### 5.6. Run commands and expected results

In the `pom.xml` directory, using JDK 17+ / Maven:

~~~bash
mvn spring-boot:run
~~~

In another terminal, submit a URL-encoded form:

~~~bash
curl -i -X POST "http://localhost:8080/forms/plain" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "age=22" \
  --data-urlencode "address.city=Ha Noi"
~~~

Expected response: HTTP **200**, exact response body:

~~~text
accepted:Lan/22/Ha Noi
~~~

Try a type mismatch:

~~~bash
curl -i -X POST "http://localhost:8080/forms/plain" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "age=abc" \
  --data-urlencode "address.city=Ha Noi"
~~~

Expected response: HTTP **400**, body:

~~~text
invalid:age
~~~

Change the URL to `/forms/wrapped` with the same valid/invalid data: you get 200/400 and the corresponding body. The difference lies in **where error handling lives in code**, not in the data constraints or HTTP contract.

If you send `address.city=` with the remaining fields valid, the response body will be:

~~~text
invalid:address.city
~~~

This example may produce startup logs; do not rely on exact Boot stdout because logs/ports/timestamps vary. The **HTTP response bodies** above are defined directly by the demo controller.

## 6. Testing WebFlux with WebTestClient

WebFlux should use `WebTestClient` to verify status, headers, and body, rather than `MockMvc` (a tool meant for Spring MVC/Servlet).

Create `src/test/java/com/example/webflux/FormControllerTest.java`:

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@AutoConfigureWebTestClient
class FormControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void plainValid() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("accepted:Lan/22/Ha Noi");
    }

    @Test
    void plainTypeMismatch() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "abc")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:age");
    }

    @Test
    void plainNestedValidation() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", ""))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:address.city");
    }

    @Test
    void wrappedValid() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("accepted:Lan/22/Ha Noi");
    }

    @Test
    void wrappedValidationFailure() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:name");
    }

    @Test
    void wrappedTypeMismatch() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "abc")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:age");
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Six tests demonstrate these cases:

1. Plain object binds the form properly and returns HTTP 200.
2. `age=abc` is recorded as a binding error, and the handler returns 400.
3. Child bean error `address.city` is caught via `@Valid`.
4. Mono-wrapped argument accepts a valid form.
5. `@NotBlank` on `name` emits an error signal handled by `onErrorResume`.
6. Mono-wrapped argument still captures conversion errors.

`BodyInserters.fromFormData(...)` sends proper URL-encoded form data, preventing tests from accidentally sending JSON labeled as a form. `@AutoConfigureWebTestClient` connects WebTestClient to the WebFlux application context during testing without launching a browser.

## 7. Rendering an HTML Form with @Controller Instead of Text Responses

If your app uses Thymeleaf or a WebFlux-compatible template engine, you can keep the plain object + `BindingResult` pattern:

~~~java
@Controller
@RequestMapping("/signup")
class SignupPageController {

    @GetMapping
    String form(Model model) {
        model.addAttribute("signup", new SignupForm());
        return "signup";
    }

    @PostMapping
    Mono<String> submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just("signup");
        }

        // After validation, a reactive service can be called.
        return Mono.just("redirect:/signup/success");
    }
}
~~~

This is an **illustrative snippet**, not in the runnable files of section 5. To run it, you would need `spring-boot-starter-thymeleaf`, imports, a `signup.html` template, a success route, and proper response/security handling. When the form is invalid, returning the same view (same request) preserves the model object and `BindingResult` for the template.

With Thymeleaf:

~~~html
<form th:action="@{/signup}"
      th:object="${signup}"
      method="post">

    <input type="text" th:field="*{name}">
    <span th:errors="*{name}"></span>

    <input type="text" inputmode="numeric"
           th:field="*{age}">
    <span th:errors="*{age}"></span>

    <input type="text" th:field="*{address.city}">
    <span th:errors="*{address.city}"></span>

    <button type="submit">Sign Up</button>
</form>
~~~

This is a **template snippet**, without `html/head/body`. `th:object`, `th:field`, and `th:errors` use the binding status; if `age=abc` cannot convert to `Integer`, `BindingResult.getFieldValue("age")` returns the user-entered string, allowing the template to re-display it instead of relying on `form.getAge()` (which may be `null`).

Do not replace the model attribute with an empty object on error. Do not automatically `redirect:/signup` after an invalid form unless both the object and `BindingResult` are carried across via proper state: a redirect opens a new request and can lose inputs and error messages. Standard pattern: **return the view on error, redirect after success**.

### When the model contains Mono<T>

A WebFlux-specific capability is that controllers can provide model attributes as reactive publishers:

~~~java
@ModelAttribute
void loadProfile(@RequestParam String id, Model model) {
    model.addAttribute(
            "profile",
            profileService.findById(id)); // Mono<Profile>
}

@PostMapping("/profile/save")
Mono<String> save(
        @ModelAttribute("profile") Profile profile,
        BindingResult errors) {
    // ...
    return Mono.just("profile");
}
~~~

This is an **architectural snippet**, assuming `profileService`, `Profile`, and an `id` query parameter; it is not standalone runnable code. WebFlux can resolve publishers in the model before passing the object to a **non-wrapped** handler, and resolve publisher values before rendering a view. Never call `subscribe()` manually to "push" data into the model.

If the method argument itself is `Mono<Profile>`, you must handle errors in the pipeline instead of using a trailing `BindingResult`. Clearly distinguish an **asynchronously populated model attribute** from a **reactively declared argument**.

## 8. Validation and Exceptions in WebFlux

### 8.1. @Valid and @Validated on @ModelAttribute

~~~java
@Valid @ModelAttribute("signup") SignupForm form
~~~

Spring runs Bean Validation using the default group on the object after binding. Constraints such as `@NotBlank`, `@Min`, and cascades through `@Valid` on nested fields appear in `BindingResult` or are thrown as exceptions if unhandled.

If groups are needed:

~~~java
@Validated({Default.class, FinalStep.class})
@ModelAttribute("signup") SignupForm form
~~~

`Default` comes from `jakarta.validation.groups.Default`, and `FinalStep` is a custom business marker interface. Custom groups only run when selected; `@Valid` has no attribute to select groups at the usage site. Putting `@Validated` at the controller class level for AOP method validation differs from placing `@Validated` directly on the form argument.

### 8.2. WebExchangeBindException

When an `@ModelAttribute` object is bound/validated without an immediately following `BindingResult`, Spring WebFlux by default can throw **`org.springframework.web.bind.support.WebExchangeBindException`**. This exception provides `BindingResult` data such as `getFieldErrors()`, `getFieldValue()`, `getAllErrors()`, `getModel()`, and an appropriate response status (typically **400 Bad Request** for input errors).

Important APIs:

~~~java
for (FieldError field : ex.getFieldErrors()) {
    String name = field.getField();
    Object rejected = field.getRejectedValue();
    boolean bindingProblem = field.isBindingFailure();
    String code = field.getCode();

    // name, code, and error type aid debugging/mapping;
    // do not log sensitive values.
}
~~~

This snippet assumes `ex` is a `WebExchangeBindException` or a compatible `BindingResult`; it is not standalone.

In a controller receiving `Mono<Form>`, you can handle that exception right inside the pipeline:

~~~java
return formMono
        .flatMap(service::save) // assumes save returns Mono<Result>
        .onErrorResume(WebExchangeBindException.class, ex -> {
            // Map to an appropriate error response.
            return fallback(ex);
        });
~~~

This is an illustrative pattern; `service`/`fallback` are not part of the demo. When using `onErrorResume`, pick a specific exception type so you do not swallow system errors as 400 form errors.

### 8.3. HandlerMethodValidationException

Since Spring Framework 6.1, if a controller method has a **direct constraint** such as `@Min(1)` on a parameter or a constraint on the return value, native method validation can run for the whole signature:

~~~java
@PostMapping("/check")
Mono<String> check(
        @Valid @ModelAttribute("signup") SignupForm form,
        @RequestParam @Min(1) int page) {
    return Mono.just("ok");
}
~~~

This snippet assumes appropriate imports. When method validation reports errors that cannot be completely handled by `Errors`/`BindingResult` arguments immediately following the respective parameters, WebFlux can throw `HandlerMethodValidationException`. **`@Valid` by itself is not a direct constraint**, so it does not trigger method validation by default. `@NotNull` on the method parameter itself can switch the execution path.

| Case | Typical Behavior |
| --- | --- |
| `@Valid @ModelAttribute Form form, BindingResult errors` | Handler receives errors and renders/responds explicitly |
| `@Valid @ModelAttribute Form form` without BindingResult | `WebExchangeBindException` if bean is invalid |
| `@Valid @ModelAttribute Mono<Form> formMono` | `WebExchangeBindException` can be handled in the reactive pipeline |
| Method has direct constraint requiring whole-method validation | `HandlerMethodValidationException` when errors are not handled at arguments |
| Server/validator configuration error | Should not be turned into an input error just because "validation" appears in the name |

In some signatures, method validation can cooperate with `Errors`; the handler is only invoked if **all** violations belong to parameters that have corresponding `Errors`/`BindingResult` arguments. If another parameter fails with nowhere to capture its error, the framework throws an exception rather than invoking the handler normally.

### 8.4. Responses and error schema

For real REST APIs, you can use `@RestControllerAdvice` or `@ExceptionHandler` to normalize WebFlux errors into JSON/`ProblemDetail` containing fields, codes, messages, and status. Never serialize the raw `WebExchangeBindException` or target bean directly to clients: they may expose sensitive data. `MessageSource` can resolve codes from `FieldError.getCodes()` for localization.

For HTML forms, validation errors usually offer a better UX by re-rendering the view with the model/binding state. Only after the form is valid should you proceed to a redirect or reactive service call.

## 9. Data Binding, Constructor Binding, and Security

### 9.1. Constructor and property binding

In modern Spring versions, `@ModelAttribute` can use constructor binding (e.g., immutable records, constructors with parameter names) and/or property binding with setters. WebFlux still uses `WebDataBinder` and conversion infrastructure. When using constructor binding in Java, parameter names must be preserved in bytecode (e.g., compiler `-parameters`) or mapped appropriately via `@BindParam`.

Conceptual immutable DTO example:

~~~java
public record SignupInput(
        String name,
        Integer age) {
}
~~~

This snippet illustrates constructor binding; if validation is needed, place appropriate constraints on record components and choose groups per business needs. A form does not have to be a mutable JavaBean, though section 5 uses a JavaBean to clearly demonstrate nested property binding.

### 9.2. Restricting writable properties

**Never bind HTTP requests directly to entities containing fields like `role`, `isAdmin`, `accountBalance`, `approved`.** Attackers may submit unexpected field names. Use dedicated DTOs and control property binding, for example:

~~~java
@InitBinder("signup")
void configure(WebDataBinder binder) {
    binder.setAllowedFields(
            "name", "age", "address.city");
}
~~~

This snippet appears in the complete program above. With constructor binding, only matching constructor parameters are accepted; you must still verify ownership, authentication, authorization, and domain rules in the service layer.

### 9.3. Reactive does not automatically mean blocking-safe

Data binding typically performs bean instantiation, reflection, formatting/conversion, and Bean Validation synchronously during argument resolution. That is not inherently an architectural flaw; brief in-memory operations are normal. However, custom converters/validators calling JDBC, blocking remote HTTP, or `Thread.sleep` can block the event loop and degrade throughput for the entire WebFlux server. Keep binding-time checks fast and side-effect free; I/O-bound checks belong in the reactive service layer executed at the appropriate lifecycle stage, rather than throwing a blocking call into `ConstraintValidator.isValid()`.

Never call `Mono.block()` in a WebFlux controller to "wait for binding to finish". WebFlux argument resolvers, Reactor, and the framework coordinate subscription and demand according to contract.

## 10. Common Pitfalls and Resolutions

| Symptom | Cause | Solution |
| --- | --- | --- |
| Form fields do not populate the object | Migrated from MVC to WebFlux but used `@RequestParam` for form body | Use `@ModelAttribute` for command objects |
| Sending JSON to a form handler fails to bind | `@ModelAttribute` is not a JSON message reader | Use `@RequestBody` for JSON |
| `BindingResult` after `Mono<Form>` does not work | Signature unsupported by WebFlux | Use plain Form + BindingResult or Mono + onErrorResume |
| Bean has `@NotBlank` but is not rejected | Missing `@Valid`/`@Validated` or Jakarta Validation provider | Add annotations and the validation starter |
| Child field invalid with no error reported | Missing `@Valid` on the `address` relation | Declare cascading on the right edge |
| `age=abc` becomes null on the model | Conversion to `Integer` failed | Read rejected value from BindingResult instead of relying on getter |
| Form cleared after error | Controller redirected or replaced model attribute | Render the same view and preserve binding state |
| Unexpected `HandlerMethodValidationException` | Direct constraint on method parameter or return value | Check method signature and distinguish from individual bean validation |
| Tests use MockMvc in WebFlux | Wrong test suite for the web stack | Use `WebTestClient` |
| Error output order varies | Error list/collection has no stable UI order | Sort fields/messages using explicit rules |
| Handler does not run on error | Missing BindingResult or error emitted in Mono | Handle the error path with BindingResult/onErrorResume |
| Both MVC and WebFlux dependencies present | Boot picks Servlet app type instead of reactive | Check dependency tree and application type |
| App stalls under load | Blocking APIs called on the event loop | Use reactive drivers or offload blocking tasks to a bounded scheduler |
| Sensitive field modified unexpectedly | Mass assignment via property binding | Use DTOs, allowedFields, and access checks |
| Calling `subscribe()` in controller | Detaches lifecycle from the framework | Return Mono/Flux for WebFlux to manage |

### Practical debugging

1. Verify request method/URL, `Content-Type`, and actual payload via browser DevTools or WebTestClient.
2. Confirm the app runs WebFlux, not accidentally Servlet/MVC due to a `spring-boot-starter-web` dependency.
3. Confirm the handler has an explicit `@ModelAttribute`, matching model attribute name, and matching field names.
4. Check that the DTO has bindable constructors/properties, initialized nested objects (if using setters), and allowed fields.
5. Distinguish conversion errors (`typeMismatch`, `isBindingFailure()==true`) from constraint validation (`@NotBlank`, `@Min`).
6. If using a plain object, verify `BindingResult` sits immediately after it; if using Mono-wrapped, check `onErrorResume` in the active chain.
7. If seeing method-level errors, look for direct `@Constraint` annotations on handler parameters/return values.
8. If rendering HTML, inspect the model and `BindingResult.MODEL_KEY_PREFIX + attributeName`, and verify `th:object`/`th:field`.
9. Check logs for blocking calls, and avoid logging personal values when debugging binding.
10. Write WebTestClient tests for valid input, type mismatch, nested validation, and both wrapped/plain modes.

## 11. Self-Check Exercises

**Exercise 1 — Data sources:** In WebFlux, why is `@RequestParam("name")` insufficient to bind an HTML POST form? Because it only accesses query parameters; to gather form fields, use `@ModelAttribute` with a command object.

**Exercise 2 — Two parameter styles:** Explain the difference between `@Valid @ModelAttribute SignupForm form, BindingResult errors` and `@Valid @ModelAttribute Mono<SignupForm> formMono`. Why can you not place `BindingResult` right after Mono? WebFlux supports a direct `BindingResult` parameter only for **non-wrapped** model attributes.

**Exercise 3 — Conversion:** When sending `age=abc`, which part is a binding error and which is a validation error? Why cannot Java `Integer age` hold `"abc"`? How do you retrieve the rejected update from `FieldError`?

**Exercise 4 — Nested:** Remove `@Valid` from `SignupForm.address` and submit `address.city=`. Predict what happens and explain the cascading mechanism.

**Exercise 5 — Reactive error handling:** Remove `onErrorResume(WebExchangeBindException.class, ...)` from `wrapped(...)`. On invalid input, the error propagates to WebFlux exception handlers; the default is a 400 response, though the error body will no longer be customized by your controller.

**Exercise 6 — View:** Create a `@Controller` rendering `signup.html` via Thymeleaf; use `BindingResult` to retain values on error and redirect on success. Why is returning the view within the same request easier than redirecting immediately on error?

**Exercise 7 — Validation groups:** Add marker group `FinalStep` and `@NotBlank(groups=FinalStep.class)` to a field. Use `@Validated({Default.class, FinalStep.class})` on the final submission endpoint; try `@Validated(FinalStep.class)` to observe how `Default` constraints can be skipped.

**Exercise 8 — Security:** Try sending an extra `role=ADMIN` in the POST form. Why are a separate DTO and `setAllowedFields(...)` safer than binding directly to an entity?

**Exercise 9 — Blocking:** If a custom validator invokes synchronous JDBC in WebFlux, what risk arises? Move I/O-bound checks to an appropriate reactive service while keeping in-memory constraints at the boundary.

## Conclusion

`@ModelAttribute` on WebFlux **remains data binding into an object** from form/query/path/headers. The standout difference from MVC is support for **reactive model values and model attribute arguments**, such as `Mono<SignupForm>`. Choose one of two clear error models:

~~~text
@Valid @ModelAttribute SignupForm form
    + BindingResult immediately after
    → check errors.hasErrors() inside handler

@Valid @ModelAttribute Mono<SignupForm> formMono
    → handle via Mono.onErrorResume(WebExchangeBindException.class, ...)
    → do not place BindingResult after Mono
~~~

`WebExchangeBindException` is WebFlux's specific exception for argument binding/validation failures; `HandlerMethodValidationException` can occur when native method validation applies to the whole signature. Use `WebTestClient`, allowlisted DTOs, properly typed constraints, and avoid blocking the event loop for a form-handling pipeline that is both correct and easy to test.

## References

- [Spring Framework 6.2 — WebFlux @ModelAttribute method argument](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — WebFlux model and reactive model attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-modelattrib-methods.html)
- [Spring Framework — WebFlux validation and exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
- [Spring Framework — WebFlux @RequestParam applies only to query](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html)
- [Spring Framework 6.2 — WebFlux @RequestBody and HTTP message readers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework API — WebExchangeBindException](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework — WebFlux data binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html)
- [Spring Framework — WebTestClient testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
