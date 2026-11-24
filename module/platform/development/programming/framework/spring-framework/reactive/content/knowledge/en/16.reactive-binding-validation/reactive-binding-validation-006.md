# WebExchangeBindException and HandlerMethodValidationException in Spring WebFlux

Spring WebFlux supports Bean Validation for request data and method validation for constraints placed directly on handler parameters or return values. The two mechanisms have different scopes, so two exceptions can arise: **WebExchangeBindException** and **HandlerMethodValidationException**.

**WebExchangeBindException** usually represents a binding or validation error on a single command object such as a request body, model attribute, or request part with @Valid/@Validated. **HandlerMethodValidationException** represents a validation error at the method level, for example a @Min or @NotBlank constraint on a parameter, or a constraint on the return value. Simply seeing @Valid in a controller signature is not enough to conclude which exception will appear.

This lesson belongs to the **Binding and validation** group and focuses on the conditions under which they arise, the error data, HTTP status codes, centralized handling, and testing these two exceptions.

## 1. Learning objectives

After this lesson, you can:

- Distinguish data binding, Bean Validation, and method validation.
- Determine when WebFlux raises WebExchangeBindException or HandlerMethodValidationException.
- Understand the roles of @Valid, @Validated, direct constraints, and BindingResult.
- Read field errors, global errors, and errors grouped by method parameter.
- Distinguish input violations (400) from return-value violations (500).
- Handle both exceptions with @RestControllerAdvice.
- Configure validators, messages, and safe error responses.
- Write a Java 17+ application with Spring Boot WebFlux and WebTestClient to verify both exceptions.

## 2. Three processing stages

A request can pass through three stages:

1. **Read and convert data:** the body, path variable, query parameter, or header is converted into Java types.
2. **Validate the object:** constraints on the object's fields/properties are checked.
3. **Validate the method:** Spring checks constraints attached directly to the handler's parameters or return value; nested objects are checked when there is cascade validation via @Valid.

~~~text
HTTP request
     |
     v
Argument resolution / data binding
     |
     +---- JSON parse or type conversion fails
     |          +---- request reading/binding error
     |
     v
Bean Validation on a single command object?
     +---- WebExchangeBindException
     |
     v
Method validation triggered?
     +---- HandlerMethodValidationException
~~~

Do not lump every HTTP 400 into a validation error. Malformed JSON, failed string-to-number conversion, a missing request value, and a constraint violation are different situations. The exact exception depends on the failing step and the handler signature.

## 3. WebExchangeBindException

WebExchangeBindException represents a binding or validation error on an object bound from the request. This class:

- Extends ServerWebInputException.
- Implements BindingResult and Errors.
- Implements ErrorResponse.
- Provides field errors, global errors, the object name, and the binding result.

The exception usually appears when Spring validates a single command object marked with @Valid or @Validated individually, such as a @ModelAttribute, @RequestBody, or @RequestPart parameter. The usual condition is that the parameter is not a container such as Map/Collection, has no Errors or BindingResult immediately after it, and method validation is not triggered for the method.

Example:

~~~java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> request) {
    return request.map(service::create);
}
~~~

This is a fragment that needs the DTO and service. If a field in CreateAccountRequest violates a constraint, WebFlux can raise WebExchangeBindException. With a Mono request body, the error occurs during reactive processing; controller advice can still handle the error at the web layer.

### Reading errors from WebExchangeBindException

Commonly used methods:

- getAllErrors(): gets both global errors and field errors.
- getFieldErrors(): gets errors attached to fields.
- getGlobalErrors(): gets object-level errors.
- getFieldError("name"): gets the first error of a field.
- getBindingResult(): accesses the wrapped BindingResult.
- getObjectName(): the name of the bound object.
- getFieldValue("name"): the current field value or the rejected value during binding.

~~~java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<ApiError> handleBinding(
        WebExchangeBindException exception) {

    List<String> messages = exception.getFieldErrors().stream()
        .map(error -> error.getField() + ": " + error.getDefaultMessage())
        .toList();

    return ResponseEntity.badRequest()
        .body(new ApiError("INVALID_OBJECT", messages));
}
~~~

This is a fragment that needs the ApiError declaration and imports. When building a response for the client, return only controlled field names and messages. Do not echo back the raw rejectedValue because it can contain passwords, tokens, personal data, or large payloads.

## 4. HandlerMethodValidationException

HandlerMethodValidationException was added in Spring Framework 6.1 to represent method validation on a handler method. This class:

- Extends ResponseStatusException.
- Implements MethodValidationResult and ErrorResponse.
- Has getParameterValidationResults() to get errors grouped by each method parameter.
- Has getAllErrors() to get the combined list of errors.
- Has visitResults(Visitor) to classify errors by parameter kind.
- Has isForReturnValue() to determine whether the error belongs to the return value.
- Has getStatusCode() to get the corresponding HTTP status.

Method validation is triggered when constraints such as @Min, @NotBlank, @Positive, or @NotNull are placed directly on a method parameter, or when a constraint is placed on the method to check the return value. When method validation runs, it covers both constraints on parameters and nested objects marked with @Valid.

Example:

~~~java
@GetMapping("/search")
public Mono<List<AccountResponse>> search(
        @RequestParam @NotBlank String query,
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return service.search(query, page);
}
~~~

This is a fragment that needs the service and DTO. @NotBlank and @Min are attached directly to the method parameters. If query is empty or page is less than 1, Spring usually raises HandlerMethodValidationException.

### @Valid does not trigger method validation by itself

@Valid is a marker requesting nested object validation (cascade validation). @Valid itself is not a constraint annotation.

~~~java
@GetMapping("/items")
public Flux<Item> find(
        @Valid @ModelAttribute SearchCriteria criteria) {
    return service.find(criteria);
}
~~~

The signature above can use individual validation for the command object and raise WebExchangeBindException.

When adding a constraint directly on a parameter:

~~~java
@GetMapping("/items")
public Flux<Item> find(
        @Valid @ModelAttribute SearchCriteria criteria,
        @RequestParam @Min(1) int page) {
    return service.find(criteria, page);
}
~~~

The @Min constraint triggers method validation. Validation then covers both page and the criteria object cascaded through @Valid; errors are reported via HandlerMethodValidationException.

## 5. Comparing the two exceptions

| Criterion | WebExchangeBindException | HandlerMethodValidationException |
| --- | --- | --- |
| Scope | A single object bound/validated individually | The entire handler method |
| Common condition | @Valid/@Validated on a command object | Direct constraint on a parameter or method return value |
| Standalone @Valid | Can trigger object validation | Does not trigger method validation by itself |
| Error data | BindingResult, field errors, global errors | MethodValidationResult, parameter validation results |
| Error reading API | getFieldErrors(), getGlobalErrors(), getAllErrors() | getParameterValidationResults(), getAllErrors(), visitResults() |
| Inheritance | ServerWebInputException | ResponseStatusException |
| Usual status | 400 Bad Request | 400 for input; 500 for return-value validation |
| Available since | Spring Framework 5.0 | Spring Framework 6.1 |

Practical rules:

- A @RequestBody object with @Valid, and no other direct constraint triggering method validation: usually WebExchangeBindException.
- A @RequestParam with @Min or @NotBlank: usually HandlerMethodValidationException.
- A method with a direct constraint on a parameter and a @Valid object: method validation can replace individual validation; the object's errors are also placed in HandlerMethodValidationException.
- A method with a constraint on the return value: HandlerMethodValidationException can report a server-side error with status 500.
- Having BindingResult/Errors immediately after the validated parameter: Spring can pass errors into that parameter so the method handles them itself according to the framework's conditions.

## 6. Status 400 for input and 500 for return value

HandlerMethodValidationException distinguishes two types of violations:

- **Input violation:** data supplied by the client fails a constraint; the status is 400 Bad Request.
- **Return-value violation:** the handler produces a value violating a constraint declared by the server; the status is 500 Internal Server Error.

The client is responsible for sending input that matches the contract. An invalid return value is a server bug.

~~~java
if (exception.isForReturnValue()) {
    // The handler produced a result violating a constraint: server error.
} else {
    // A request parameter violated a constraint: client error.
}

HttpStatusCode status = exception.getStatusCode();
return ResponseEntity.status(status).body(apiError);
~~~

Do not always force every HandlerMethodValidationException to 400. Doing so can hide server-side implementation bugs.

## 7. BindingResult and Errors

Spring allows declaring Errors or BindingResult immediately after the parameter to be validated so the controller can read errors itself.

~~~java
@PostMapping("/accounts/manual")
public Mono<ResponseEntity<?>> createManually(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest()
            .body("Invalid account request"));
    }

    return service.create(request)
        .map(saved -> ResponseEntity.ok(saved));
}
~~~

This is a fragment that needs the service, DTO, and imports. When BindingResult stands immediately after the validated parameter, the controller can be invoked with the error information instead of throwing an exception immediately for individual object validation. With this pattern, the request body must be resolved before calling the method; do not use Mono<CreateAccountRequest> if you want to receive BindingResult directly in that way.

With method validation, Errors/BindingResult can also be combined. However, the controller is invoked only if all validation errors are on parameters that have Errors immediately after them. If there is an error on another parameter not handled that way, Spring raises HandlerMethodValidationException.

Do not put BindingResult at the end of the method and expect it to receive errors for every parameter. Adjacent placement is part of the argument resolution rule.

## 8. Reading errors by method parameter

HandlerMethodValidationException does not store just a single BindingResult. It provides results per parameter:

- getParameterValidationResults(): list of ParameterValidationResult.
- getAllErrors(): combined list of MessageSourceResolvable.
- getValueResults() and getBeanResults(): distinguish errors on parameter values from cascaded errors on objects.
- getCrossParameterValidationResults(): errors from constraints checking multiple parameters together.
- visitResults(Visitor): handle by parameter kind such as request header, request param, model attribute, or other groups.
- isForReturnValue(): indicates whether the error belongs to the return value.

General reading example:

~~~java
@ExceptionHandler(HandlerMethodValidationException.class)
public ResponseEntity<ApiError> handleMethodValidation(
        HandlerMethodValidationException exception) {

    List<String> messages = exception.getAllErrors().stream()
        .map(error -> error.getDefaultMessage() == null
            ? "Invalid value"
            : error.getDefaultMessage())
        .toList();

    return ResponseEntity.status(exception.getStatusCode())
        .body(new ApiError(
            exception.isForReturnValue()
                ? "INVALID_SERVER_RESULT"
                : "INVALID_INPUT",
            messages));
}
~~~

When you need a richer contextual response, use visitResults to identify whether the error belongs to a query parameter, header, path variable, or model attribute. Do not infer parameter names from list position yourself; use the MethodParameter metadata of the validation result.

## 9. Centralized handling with @RestControllerAdvice

REST APIs usually want to return a consistent error response regardless of whether the exception comes from object validation or method validation.

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> handleObjectValidation(
            WebExchangeBindException exception) {

        return ResponseEntity.badRequest().body(
            new ApiError("INVALID_OBJECT", messages(exception.getAllErrors())));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        String code = exception.isForReturnValue()
            ? "INVALID_SERVER_RESULT"
            : "INVALID_INPUT";

        return ResponseEntity.status(status).body(
            new ApiError(code, messages(exception.getAllErrors())));
    }

    private List<String> messages(
            List<? extends MessageSourceResolvable> errors) {
        return errors.stream()
            .map(error -> Objects.requireNonNullElse(
                error.getDefaultMessage(), "Invalid value"))
            .toList();
    }
}
~~~

Response model:

~~~java
import java.util.List;

public record ApiError(String code, List<String> errors) {
}
~~~

The example above needs the Bean Validation provider dependency to enforce constraints. The two handlers have separate responsibilities: object validation returns 400; method validation preserves the status determined by Spring. Multilingual applications can resolve messages by locale. The response contains only chosen messages, without sending raw error objects or rejected values outside.

### ResponseEntityExceptionHandler

Spring WebFlux has ResponseEntityExceptionHandler in the org.springframework.web.reactive.result.method.annotation package. Since Spring Framework 6.1, this class has hooks to customize WebExchangeBindException and HandlerMethodValidationException along with other HTTP errors.

Use this class when you want to centralize handling of multiple standard WebFlux exceptions. If you only need two simple responses, two separate @ExceptionHandler methods are easy to read and sufficient. Do not confuse the reactive class with Spring MVC's ResponseEntityExceptionHandler in the servlet package.

## 10. Class-level @Validated can change the mechanism

Spring Framework 6.1 added built-in method validation for annotated controllers. If a controller is annotated with @Validated at the class level, method validation may be applied through an AOP proxy instead of the handler adapter's built-in mechanism.

This can make the exception and handling path differ, for example the AOP mechanism might raise ConstraintViolationException depending on configuration. If you want to use Spring WebFlux 6.1+'s built-in method validation, you usually omit @Validated at the controller class level.

@Validated is still useful for validation groups on suitable parameters. Distinguish the group-selecting annotation on a parameter from enabling AOP method validation at the class level. Do not remove @Validated mechanically if another service or bean relies on AOP validation.

## 11. Global and local Validators, and validation groups

If a Bean Validation provider is on the classpath, WebFlux can register a global validator to use for @Valid and @Validated on controller method arguments. In Spring Boot, the spring-boot-starter-validation dependency usually provides a provider such as Hibernate Validator.

You can customize validators in two scopes:

- **Global:** configure the Validator through WebFluxConfigurer.
- **Local:** use @InitBinder in @Controller or @ControllerAdvice to add validators for appropriate data binding.

Global configuration example:

~~~java
@Configuration
public class WebValidationConfig implements WebFluxConfigurer {

    private final Validator validator;

    public WebValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
~~~

This is a fragment; depending on the Spring Boot setup, the validator may already be auto-configured and not need to be declared again.

### Validation groups

You can apply different sets of rules when creating and when updating:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}

public record AccountRequest(
    @NotBlank(groups = {CreateChecks.class, UpdateChecks.class})
    String name,

    @NotBlank(groups = CreateChecks.class)
    String initialPassword
) {
}
~~~

Use @Validated(CreateChecks.class) on the command object parameter to select the group. If method validation is triggered by a direct constraint on a parameter, group selection and cascade scope need to be designed consistently. Test the actual controller signature instead of assuming @Validated and @Valid always produce the same handling path.

## 12. Distinguishing validation from parse and conversion errors

Not every HTTP 400 comes from these two exceptions.

| Situation | Nature | How to handle |
| --- | --- | --- |
| Malformed JSON | Decoder cannot read the body | Decoding error / corresponding ServerWebInputException |
| Query page=abc when parameter is int | Type conversion fails | Argument conversion/type mismatch |
| name="" with @NotBlank | Constraint on the object | Usually WebExchangeBindException if validated individually |
| page=0 with direct @Min(1) | Method validation | HandlerMethodValidationException |
| Return value violates constraint | Server-side contract bug | HandlerMethodValidationException, status 500 |
| Missing required request body | Missing request input | Appropriate request binding error |

Example body:

~~~json
{"name":"Alice","age":"not-a-number"}
~~~

If age in the DTO is int, the JSON decoder can fail before Bean Validation has a valid object to check. Conversely:

~~~json
{"name":"","age":15}
~~~

The JSON can decode into an object, but @NotBlank and @Min fail when validation runs. This is a validation error.

## 13. A runnable Java 17+ example with Spring Boot WebFlux

The complete example has two endpoints:

- POST /accounts: validates the request object with @Valid @RequestBody Mono<...>; errors are handled via WebExchangeBindException.
- GET /accounts/search: validates query parameters with direct @NotBlank and @Min; errors are handled via HandlerMethodValidationException.

### Project structure

~~~text
webflux-validation-demo/
├── pom.xml
└── src
    ├── main/java/com/example/validation
    │   ├── ValidationDemoApplication.java
    │   ├── AccountController.java
    │   ├── CreateAccountRequest.java
    │   ├── AccountResponse.java
    │   ├── ApiError.java
    │   └── ValidationAdvice.java
    └── test/java/com/example/validation
        └── AccountControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>webflux-validation-demo</artifactId>
  <version>1.0.0</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

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

Spring Boot 3.3.5 uses Spring Framework 6.1.x, which has HandlerMethodValidationException and built-in controller method validation. The spring-boot-starter-validation dependency provides the Bean Validation provider. Spring Boot manages compatible versions; there is no need to set Spring Framework or Reactor versions manually.

### ValidationDemoApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

### CreateAccountRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
    @NotBlank(message = "Name must not be blank")
    String name,

    @Email(message = "Email format is invalid")
    String email,

    @Min(value = 18, message = "Age must be at least 18")
    int age
) {
}
~~~

### AccountResponse.java

~~~java
package com.example.validation;

public record AccountResponse(
    String id,
    String name,
    String email,
    int age
) {
}
~~~

### ApiError.java

~~~java
package com.example.validation;

import java.util.List;

public record ApiError(
    String kind,
    List<String> errors
) {
}
~~~

### AccountController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/accounts")
public class AccountController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<AccountResponse> create(
            @Valid @RequestBody Mono<CreateAccountRequest> request) {

        return request.map(body ->
            new AccountResponse(
                "account-1",
                body.name(),
                body.email(),
                body.age()));
    }

    @GetMapping("/search")
    public Mono<String> search(
            @RequestParam("q") @NotBlank String query,
            @RequestParam(defaultValue = "1") @Min(1) int page) {

        return Mono.just("query=" + query + ",page=" + page);
    }
}
~~~

Do not place class-level @Validated on this controller. That way, Spring Framework 6.1+'s method validation can handle constraints on query parameters directly.

### ValidationAdvice.java

~~~java
package com.example.validation;

import java.util.List;
import java.util.Objects;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> handleObjectValidation(
            WebExchangeBindException exception) {

        return ResponseEntity.badRequest().body(
            new ApiError("body-object", messages(exception.getAllErrors())));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        String kind = exception.isForReturnValue()
            ? "return-value"
            : "method-parameters";

        return ResponseEntity.status(status).body(
            new ApiError(kind, messages(exception.getAllErrors())));
    }

    private List<String> messages(
            List<? extends MessageSourceResolvable> errors) {

        return errors.stream()
            .map(error -> Objects.requireNonNullElse(
                error.getDefaultMessage(), "Invalid value"))
            .toList();
    }
}
~~~

The two handlers share a common response format while preserving the error kind and status determined by Spring. In production, you can resolve messages by locale or return an error structure with explicit fields/parameters.

### AccountControllerTests.java

~~~java
package com.example.validation;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
@Import(ValidationAdvice.class)
class AccountControllerTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void invalidBodyUsesWebExchangeBindException() {
        webTestClient.post()
            .uri("/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "name", "",
                "email", "not-an-email",
                "age", 15))
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.kind").isEqualTo("body-object")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void invalidQueryUsesHandlerMethodValidationException() {
        webTestClient.get()
            .uri("/accounts/search?q=alice&page=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.kind").isEqualTo("method-parameters")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void validBodyCreatesAccount() {
        webTestClient.post()
            .uri("/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "name", "Alice",
                "email", "alice@example.com",
                "age", 24))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").isEqualTo("account-1")
            .jsonPath("$.name").isEqualTo("Alice");
    }

    @Test
    void validQueryPassesMethodValidation() {
        webTestClient.get()
            .uri("/accounts/search?q=alice&page=2")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("query=alice,page=2");
    }
}
~~~

Run tests in the directory containing pom.xml:

~~~bash
mvn -q test
~~~

If the four tests pass, Maven exits with exit code 0. The first test verifies that the request object goes through WebExchangeBindException. The second test verifies that direct constraints on query parameters go through HandlerMethodValidationException. The remaining two tests check that valid data still reaches the handler and receives the right status/body.

## 14. Return-value validation and server-side errors

Method validation can also check the handler's return value. General example:

~~~java
@GetMapping("/internal-code")
@NotBlank
public String internalCode() {
    return "";
}
~~~

If Bean Validation and method validation apply this return-value constraint, an empty value violates @NotBlank. HandlerMethodValidationException can be raised with isForReturnValue() == true and status 500. This is an error caused by the server producing a response that fails to meet the declared constraint.

This is an illustrative example of a return constraint. For reactive wrapper types such as Mono<T>, check the semantics of the exact version and return type; do not assume a constraint placed on Mono<T> will cascade into the emitted T value. If you need to validate objects inside a publisher, design a suitable validator/service boundary and test it in practice.

## 15. Messages, locales, and error responses

Bean Validation supports message templates and message bundles:

~~~java
@NotBlank(message = "{account.name.required}")
String name;
~~~

You can provide bundles by locale and let Spring's MessageSource resolve messages. Spring WebFlux also supports customizing error responses for exceptions through the message source and locale.

A good error response API should:

- Have a stable error code for the client to handle.
- Have a clear list of errors, possibly including the field or parameter name.
- Use messages suited to the user's language when needed.
- Not return stack traces, sensitive rejected values, or authentication data.
- Not depend on error ordering if ordering is not specified.
- Distinguish input violations from return-value violations.

Do not take exception.getMessage() and return it verbatim as an API contract. Diagnostic messages can change between versions or contain internal details.

## 16. Common mistakes and how to fix them

1. **Assuming every @Valid produces HandlerMethodValidationException.** @Valid itself is not a constraint; individual validation of a command object usually produces WebExchangeBindException.
2. **Putting @Min directly on a query parameter while handling only WebExchangeBindException.** Method validation can raise HandlerMethodValidationException; handle both.
3. **Handling only HandlerMethodValidationException and ignoring body validation.** A request object can still go through WebExchangeBindException.
4. **Always returning 400 for HandlerMethodValidationException.** Return-value violations are server bugs and have status 500.
5. **Confusing JSON parse errors with Bean Validation.** The decoder can fail before there is an object to validate.
6. **Placing BindingResult not immediately after the validated parameter.** Spring does not pass errors into that parameter according to the expected pattern.
7. **Using BindingResult after Mono<DTO>.** With the pattern for receiving errors directly in the method, the body must be resolved first; use a direct command object and BindingResult right after.
8. **Adding class-level @Validated and expecting 6.1's built-in method validation.** AOP validation can change the exception path; understand the configuration clearly.
9. **Forgetting the validation provider dependency.** Constraint annotations can exist without a validator implementation to enforce them.
10. **Not validating nested objects with @Valid.** Constraints on child objects do not run automatically if cascade validation is not enabled.
11. **Treating @Valid and @Validated as always identical.** @Validated also supports validation groups.
12. **Returning rejected values in the response.** Can leak passwords, tokens, or personal data.
13. **Lumping all errors into one general message and losing the field/parameter.** Makes it hard for the client to point out which input part to fix.
14. **Using error order as a rigid test criterion.** Order can vary by provider.
15. **Creating controller validation with AOP without checking the proxy.** The AOP mechanism depends on proxies and bean configuration.
16. **Not distinguishing parameter errors from return-value errors.** Can misreport client/server responsibility.
17. **Swallowing errors with onErrorResume and returning success.** This hides validation errors and misleads the client into thinking the data was accepted.
18. **Only unit-testing error formatting helpers.** You need WebTestClient to check that requests actually take the right validation path.

## 17. Deployment checklist

- **Version:** Does Spring Framework support HandlerMethodValidationException? Built-in method validation is available since 6.1.
- **Provider:** Is a Bean Validation dependency such as spring-boot-starter-validation present?
- **Object validation:** Does the command object have @Valid/@Validated on the right parameter?
- **Method validation:** Are direct constraints on parameters/return values intentional?
- **Cascade:** Do nested objects have @Valid in the necessary places?
- **Groups:** If using validation groups, are the selected groups right for create/update?
- **BindingResult:** Is it placed immediately after the corresponding parameter and using an appropriate body type?
- **Class-level @Validated:** Does it unexpectedly switch method validation to AOP?
- **Exception coverage:** Does the advice handle both WebExchangeBindException and HandlerMethodValidationException?
- **HTTP status:** Input 400, return-value violation 500?
- **Error body:** Is the message stable, containing necessary fields/parameters and not leaking rejected values?
- **Localization:** Do the message source and locale match the requirements?
- **Parse errors:** Are JSON decoding and type conversion errors handled separately?
- **Tests:** Does WebTestClient prove both exception paths and the valid case?
- **Observability:** Do logs include correlation ID, endpoint, and error code without logging sensitive payloads?

## 18. Self-check exercises

**Exercise 1.** A method receives @Valid @RequestBody Mono<CreateUserRequest>; the object has a @NotBlank field, and the method has no other direct constraints. What is the usual exception?  
**Answer:** WebExchangeBindException, because this is individual validation on the command object.

**Exercise 2.** A method receives @RequestParam @Min(1) int page, and the client sends page=0. What is the usual exception?  
**Answer:** HandlerMethodValidationException, because the constraint is directly on the method parameter.

**Exercise 3.** Why does a standalone @Valid not trigger method validation by itself?  
**Answer:** @Valid is a marker for cascade validation, not a constraint annotation. Constraints such as @Min, @NotBlank, or @NotNull on a parameter are what trigger method validation.

**Exercise 4.** A method has @Min(1) on a query parameter and @Valid on a body DTO. If the body has an invalid field, which exception may be raised?  
**Answer:** HandlerMethodValidationException, because method validation is triggered and covers nested constraints through @Valid.

**Exercise 5.** Is HandlerMethodValidationException always HTTP 400?  
**Answer:** No. Input violations are 400; return-value violations are 500.

**Exercise 6.** Which APIs does WebExchangeBindException provide to read field errors?  
**Answer:** getFieldErrors(), getFieldError(...), getAllErrors(), and getBindingResult().

**Exercise 7.** Which APIs does HandlerMethodValidationException provide to read errors by parameter?  
**Answer:** getParameterValidationResults(), getAllErrors(), getValueResults(), getBeanResults(), and visitResults(...).

**Exercise 8.** Does a syntactically malformed JSON body necessarily produce WebExchangeBindException?  
**Answer:** No. The decoder can raise a parse/binding error before Bean Validation runs.

**Exercise 9.** Can you place BindingResult at the end of the parameter list to receive errors for every parameter?  
**Answer:** No. It must be placed immediately after the parameter needing to receive errors; with method validation, errors must satisfy Spring's adjacent Errors rule.

**Exercise 10.** Why can class-level @Validated change the exception?  
**Answer:** It can trigger method validation via an AOP proxy instead of Spring Framework 6.1+'s built-in handler method validation.

**Exercise 11.** If a controller produces a value violating a constraint on the return value, who is responsible?  
**Answer:** The server; this is return-value validation and the corresponding status is 500.

**Exercise 12.** Why should you not put FieldError.getRejectedValue() into the JSON response?  
**Answer:** The rejected value can contain sensitive data; the response should reveal only the necessary field/message.

## 19. Key takeaways

**WebExchangeBindException** represents failed binding or validation on an individually bound object. It extends ServerWebInputException and provides BindingResult, so you can read field errors and global errors. **HandlerMethodValidationException** represents validation at the handler method level; it provides results per parameter, supports a visitor, and distinguishes input errors from return-value errors.

The common decision rule: @Valid on a command object, with no method constraints changing the mechanism, leads to WebExchangeBindException. Direct constraints such as @Min or @NotBlank on a parameter/return value trigger method validation and lead to HandlerMethodValidationException. @Valid can participate in cascading within method validation when the method has already been triggered by another constraint. Handle both exceptions, keep status 400 for input and 500 for return-value violations, and test the real handling path with WebTestClient.

### References

- Spring Framework, [WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html).
- Spring Framework, [WebFlux Request Body](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html).
- Spring Framework Javadoc, [WebExchangeBindException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html).
- Spring Framework Javadoc, [HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html).
- Spring Framework, [WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework, [WebFlux Configuration and Validator](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
