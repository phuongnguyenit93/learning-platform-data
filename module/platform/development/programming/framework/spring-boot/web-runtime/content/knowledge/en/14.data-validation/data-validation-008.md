# Method Validation and Support Mechanism Changes Across Spring Versions

## 1. Context: Data Validation Does Not Stop at DTOs

In a Spring Boot application, input data validation can occur at multiple boundaries: when binding JSON into @RequestBody, when converting query strings into @RequestParam, when receiving an @ModelAttribute object, and right before invoking a Java method. There are also cases requiring validation of a method's **return value**, especially when a service must always guarantee a contract invariant.

Examples:

- An order-creation DTO must have a non-empty product name: @NotBlank on a field or record component, triggered via @Valid @RequestBody.
- Query parameter page must be >= 1: @Min(1) placed directly on the controller's @RequestParam parameter.
- Service transfer(amount) must be called with a positive amount, even when the caller is not HTTP: @Positive placed on the service parameter using method validation.
- Function findRequired() must never return null: @NotNull on the method's **return value**.
- A method with multiple parameters must obey a combined rule: cross-parameter validation or explicit domain checks.

These scenarios are not checked with the exact same mechanism across all Spring Framework versions. In particular, **Spring Framework 6.1** introduced **built-in method validation directly inside Spring MVC and WebFlux controllers**. Before that, developers commonly used **class-level @Validated to trigger an AOP proxy** for validation on controller parameters/return values. This shift affects exception types, error handling, and how code is migrated.

This lesson clearly explains the differences among:

1. Bean Validation on **a single parameter object**;
2. Bean Validation on **an entire method**;
3. Method validation via **Spring AOP** on services/components;
4. **Built-in** method validation in MVC/WebFlux since Spring Framework 6.1;
5. Behavioral changes when upgrading Spring Boot/Spring Framework versions.

The goal is not to sprinkle annotations everywhere, but to place validation at the right layer, know when exceptions are produced, and avoid accidentally returning HTTP 500 for input errors that should be 400.

## 2. Terminology and Easily Confused Classes

| Concept | Role | Key Point to Remember |
|---|---|---|
| Bean Validation (Jakarta Validation) | Specification for constraints on beans, parameters, and return values | Annotations are contracts; an execution provider like Hibernate Validator is required |
| @NotNull, @NotBlank, @Min, @Positive, @Size | Constraint annotations | Check values directly; null has specific rules per constraint |
| @Valid | Triggers object validation/cascading | **Not** a constraint by itself |
| @Validated | Spring annotation supporting validation groups and AOP method validation | Placing at class level on services is common; placing at class level on 6.1+ controllers can switch to AOP |
| @RequestBody / @ModelAttribute / @RequestPart | Sources for binding an input object | Have per-argument validation mechanisms |
| BindingResult / Errors | Lets controllers handle binding/validation errors locally | Parameter position must be immediately after the target object |
| MethodArgumentNotValidException | MVC exception for single-argument object validation | Typically paired with @Valid @RequestBody when method validation is unnecessary |
| WebExchangeBindException | WebFlux exception for single-argument object binding/validation | Conceptual equivalent to MVC's MethodArgumentNotValidException |
| HandlerMethodValidationException | Exception for built-in controller method validation since Framework 6.1 | Contains per-parameter validation results; input is normally HTTP 400, return value normally HTTP 500 |
| ConstraintViolationException | Jakarta Validation exception commonly seen with AOP method validation | Not automatically synonymous with HTTP 400 |
| MethodValidationException | Spring exception wrapping adapted validation results when configured | Differs from web controllers' HandlerMethodValidationException |
| MethodValidationPostProcessor | Infrastructure creating AOP proxies for Spring method validation | Suited for @Validated services/components |
| Validator / LocalValidatorFactoryBean | Bridge between Spring and the Bean Validation provider | Can be auto-configured when a provider is on the classpath |
| ResponseEntityExceptionHandler | Supports MVC/WebFlux exception handling per stack | Provides hooks to customize responses |
| @ControllerAdvice / @RestControllerAdvice | Applies error handling logic across controllers | Must handle the right exception types and HTTP statuses |

**Method validation** is validation at the method-invocation scope: checking constraints directly on parameters, checking nested constraints via cascade @Valid, and optionally checking return values. It differs from merely validating a single DTO object at request-binding time.

## 3. How Do @Valid, @Validated, and Constraints Differ?

### 3.1. What Is a Constraint Really?

Annotations such as @NotNull, @NotBlank, @Min, and @Positive belong to Jakarta Validation and are meta-annotated to describe constraints. A provider evaluates them when validation is triggered.

Example request DTO:

~~~java
public record CreateProduct(
        @NotBlank String name,
        @NotNull @Min(1) Integer quantity) {}
~~~

Here:
- @NotBlank checks that name is non-null, non-empty, and not whitespace-only.
- @NotNull ensures quantity is present after binding.
- @Min(1) rejects quantity less than 1, yet on its own, numeric constraints like @Min normally let null pass. Thus @NotNull and @Min complement each other.

The record snippet requires importing jakarta.validation.constraints and running in a project with a provider. Annotations alone do not execute unless a code path triggers validation.

### 3.2. @Valid Is Not a Direct Constraint

~~~java
@PostMapping("/products")
ProductView create(@Valid @RequestBody CreateProduct request) {
    // ...
}
~~~

@Valid tells Spring/the validator to check the contents of the CreateProduct object and any cascaded nested objects. It does not mean an arbitrary Java parameter must be non-null.

For example, placing only @Valid on a String does not require the String to contain characters. If a non-blank String is needed, use @NotBlank on the appropriate parameter or field.

Illustration of the difference:

~~~java
// Insufficient to require term to be non-blank:
@GetMapping("/a")
String a(@RequestParam @Valid String term) {
    return term;
}

// Has a direct constraint on the method parameter:
@GetMapping("/b")
String b(@RequestParam @NotBlank String term) {
    return term;
}
~~~

These are two controller method snippets. In Framework 6.1+, method b triggers built-in method validation for the direct @NotBlank, provided class-level @Validated does not switch it to AOP.

### 3.3. Spring's @Validated Has Two Roles

- **Validation groups:** @Validated(Create.class) on an object argument selects constraint groups for bound data.
- **AOP method validation:** @Validated at the bean/class level such as @Service gives MethodValidationPostProcessor a pointcut to check method parameters/return values when calls go **through the Spring proxy**.

The exact same annotation in different positions triggers different mechanisms. Notably, in Spring Framework 6.1+ controllers, if you want the new built-in validation, Spring documentation instructs **removing class-level @Validated from controllers**. Do not remove @Validated from services, because services still rely on AOP method validation.

### 3.4. Validation Groups Are Not Automatic Optional-Field Semantics

A DTO can have Create and Update groups with different constraints, yet placing @Validated(Create.class) does not automatically distinguish omitted JSON properties from explicit nulls in every PATCH scenario. Validation checks the already-bound object; if presence semantics are needed, the DTO must track field presence or use structures like JsonNode.

## 4. Validation on Individual Argument Objects

Spring MVC normally validates an argument object via @Valid/@Validated when:

1. The controller has a supported @RequestBody, @ModelAttribute, or @RequestPart parameter.
2. That parameter is a suitable command object, rather than a Map/Collection treated as a container under these rules.
3. There is no Errors or BindingResult **immediately after** the argument for the controller to handle errors itself.
4. No other direct method constraints cause Spring to switch to method validation.

Example:

~~~java
@PostMapping("/products")
ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProduct request) {
    // ...
}
~~~

When the request body has an empty name or quantity under 1, MVC normally throws MethodArgumentNotValidException. It carries a BindingResult with field errors, object errors, and details useful for constructing error responses.

In WebFlux, the equivalent scenario normally raises WebExchangeBindException. The two exception classes differ because WebFlux uses reactive request processing rather than Servlet MVC.

### 4.1. BindingResult Immediately After the Argument

In MVC, errors can be handled directly:

~~~java
@PostMapping("/manual")
ResponseEntity<?> manual(
        @Valid @RequestBody CreateProduct request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Invalid product");
    }

    return ResponseEntity.ok("Accepted");
}
~~~

This is a method snippet; CreateProduct and imports are needed. BindingResult must sit immediately after the relevant argument. If direct method constraints exist on other parameters and validation errors cannot all be handled via Errors/BindingResult parameters per web framework rules, Spring can still throw HandlerMethodValidationException instead of invoking the method.

Therefore, do not treat adding BindingResult as a “flag disabling all validation exceptions”.

### 4.2. Binding/Deserialization Errors Differ from Bean Validation

Before the provider checks @NotBlank, the framework must decode JSON and convert types. Malformed JSON, unsupported media types, unconvertible path variables, or non-numeric query ints can throw binding/HTTP message-reading errors rather than entering the same validation exception path.

An error handler catching only MethodArgumentNotValidException will not cover all 400 Bad Requests. A well-designed API builds appropriate error responses for parsing, conversion, missing request bodies, missing request parameters, and Bean Validation.

## 5. Method Validation and the Major Change in Spring Framework 6.1

### 5.1. What Triggers Method Validation in 6.1+ Controllers?

When an annotated MVC or WebFlux controller method has a **direct constraint** on a parameter or return value, Spring Framework 6.1+ validates the method using the web framework's built-in mechanism without needing a dedicated AOP proxy for the controller.

Example:

~~~java
@GetMapping("/page")
Map<String, Integer> page(
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return Map.of("page", page);
}
~~~

@Min(1) sits directly on the method parameter. For GET /page?page=0, page has a valid int=0 type, yet violates the constraint. In a controller using Framework 6.1+ built-in method validation, standard behavior is HandlerMethodValidationException and HTTP 400.

Common direct constraints:

- @Min, @Max, @Positive, @Negative on numbers.
- @NotBlank, @Size, @Pattern on Strings.
- @NotNull for nullable parameters or return values.
- Custom constraints declared with @Constraint.
- Constraints on a method's return value when required by contract.

**@Valid alone does not trigger method validation.** It requests cascade validation of an object. If you add @NotNull directly onto that same @Valid argument, that becomes a direct constraint, so method validation can be selected.

### 5.2. Method Validation Subsumes Nested Validation

Suppose a method has @Min placed directly on page and an @Valid @RequestBody DTO:

~~~java
@PostMapping("/products/check")
ResponseEntity<String> check(
        @RequestParam @Min(1) int page,
        @Valid @RequestBody CreateProduct request) {
    return ResponseEntity.ok("Accepted");
}
~~~

In Framework 6.1+ built-in configuration, method validation covers both the direct constraint on page **and** the nested constraints on CreateProduct. It supersedes standalone per-argument @Valid body validation when method-level validation is required.

This can **change the exception type** after adding an annotation to a method: previously a method with only an @Valid body threw MethodArgumentNotValidException; after adding @Min on a query param, violations can go through HandlerMethodValidationException. Error handlers and tests must not hardcode the assumption that every @Valid @RequestBody throws only one exception type.

### 5.3. HandlerMethodValidationException for Input and Output

When web controller method validation fails, HandlerMethodValidationException carries results grouped by method parameter or return value. For input constraint violations, the default HTTP status is **400**. When the controller violates a **return-value constraint**, the default HTTP status is **500**, because the server violated its own contract.

Illustrative return-value constraint example:

~~~java
@GetMapping("/display")
@NotNull
public String display(@RequestParam(defaultValue = "false") boolean fail) {
    return fail ? null : "ready";
}
~~~

This is a method snippet for Framework 6.1+; if fail=true, the method returns null, violating @NotNull on the return value. That is a server-side implementation/logic bug, **not a request validation error caused directly by the client**. Do not catch every HandlerMethodValidationException and force HTTP 400.

In real applications, prevent returning contract-violating nulls, test method return values, and monitor server errors separately from input errors.

### 5.4. Validation Results Grouped by Parameter

HandlerMethodValidationException exposes a list of ParameterValidationResult (and ParameterErrors for objects) along with method parameter metadata and constraint errors. The framework provides a Visitor to categorize parameters such as @RequestParam, @RequestHeader, @ModelAttribute, and others.

Advantage of this approach: API error handlers can build clean per-parameter error structures rather than calling ex.getMessage() and trying to parse field names out of a string whose format may change.

Also avoid placing raw rejected values in responses/logs if they may contain passwords, tokens, or personal data.

## 6. Legacy Mechanism: Class-Level @Validated and AOP

Before Spring Framework 6.1 added built-in controller method validation, the standard way to check direct constraints on controller methods was class-level @Validated combined with MethodValidationPostProcessor via an AOP proxy.

Legacy style example:

~~~java
@RestController
@Validated
@RequestMapping("/legacy")
class LegacyController {

    @GetMapping("/page")
    String page(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
~~~

This is an illustrative class requiring imports and a validation environment. Before 6.1, this setup allowed MethodValidationInterceptor to validate around method calls.

From 6.1 onward, keeping @Validated at the controller level can still route validation through an AOP proxy instead of the built-in web mechanism. Spring recommends **removing class-level @Validated on controllers** to adopt built-in 6.1 support. Otherwise, handlers for HandlerMethodValidationException may not receive errors as expected; you may see ConstraintViolationException or AOP-configured method validation exceptions instead.

### 6.1. Why Does AOP Differ from Built-In Controller Validation?

| Criterion | Class-Level @Validated + AOP | Web Built-In Since Framework 6.1 |
|---|---|---|
| Activation | Class/bean is proxied and calls pass through proxy | Web framework dispatches annotated controller method |
| Scope | Many Spring beans: services, components, controllers | Controllers dispatched by MVC/WebFlux |
| Typical error | ConstraintViolationException; MethodValidationException depending on config | HandlerMethodValidationException |
| HTTP parameter awareness | Not the focus; AOP sees Java methods | Tied to web method parameters and HTTP error handling |
| Return-value validation | Yes, when supported by provider and interceptor | Yes |
| Self-invocation limitation | Yes, with standard proxies | Web handler invocation does not depend on AOP proxies under the new mechanism |
| Enabling on new controllers | Class-level @Validated not needed | Direct constraints + provider, per version |
| Enabling on services | Class-level @Validated still normally needed | Does not replace service AOP method validation |

**Do not delete @Validated from every class when upgrading to Spring Framework 6.1.** The change documented by Spring specifically targets **controllers using built-in method validation**. Services/components needing proxy validation still typically require type-level @Validated.

### 6.2. Self-Invocation Can Bypass the Proxy

Service example:

~~~java
@Service
@Validated
public class PriceService {

    public int quote(@Min(1) int quantity) {
        return quantity * 100;
    }

    public int quoteInternally() {
        // Internal call via this: does not pass through AOP proxy.
        return quote(0);
    }
}
~~~

If an external Spring bean calls the proxied PriceService.quote(0), AOP method validation intercepts it. Yet when quoteInternally() calls quote(0) inside the same object via this, the call bypasses the proxy so the validator **is not triggered via standard interception**.

This is a limitation of Spring AOP proxies, not a bug in @Min. Better solutions are moving the validated method into a separate bean called through a proxy, or enforcing the invariant explicitly in domain/method code; never rely solely on annotations when internal self-calls occur.

AOP proxies also have constraints around visibility, final methods, and JDK/CGLIB proxying. If method validation does not trigger, first verify that the bean is Spring-managed and the call actually traverses the proxy.

## 7. Spring and Spring Boot Version Comparison Table

**Always check the actual Spring Framework version running**, not just a Spring Boot version number in docs or project diagrams. Spring Boot manages dependencies via a BOM; if a team overrode the Framework version, behavior can differ from expectations.

| Version Line | Key Points |
|---|---|
| Spring Framework 5.x / Spring Boot 2.x | Common Bean Validation API is still javax.validation; direct method constraints on controllers usually rely on class-level @Validated/AOP |
| Spring Framework 6.0 / Spring Boot 3.0–3.1 | Moves to jakarta.validation; lacks Framework 6.1's new built-in controller method validation; AOP still usually required for direct constraints |
| Spring Framework 6.1 / Spring Boot 3.2–3.3 | Built-in method validation for @RequestMapping methods in MVC/WebFlux; HandlerMethodValidationException introduced; remove class-level @Validated on controllers adopting the new mechanism |
| Spring Framework 6.2 / Spring Boot 3.4–3.5 | 6.1 built-in mechanism remains foundational; check exact docs/Javadoc and binding/error-handling updates |
| Newer Spring Framework lines | Do not extrapolate from 6.1 examples; check version docs, migration notes, error-handling APIs, and test with real dependencies |

For newer projects using Java 17+, Spring Boot 3.2/3.3 with Framework 6.1 is a clear milestone for understanding these changes. Spring Boot 3.x uses the **jakarta.validation** namespace; never copy javax.validation imports from a Boot 2.x blog post.

### 7.1. Errors Commonly Seen Right After Upgrading

1. Legacy controller keeps class-level @Validated and runs via AOP proxy, while newer code expects to handle HandlerMethodValidationException.
2. Controller with @Valid @RequestBody gains @Min on an @RequestParam, switching validation failures from per-argument to method validation.
3. @ControllerAdvice catches only MethodArgumentNotValidException, missing HandlerMethodValidationException.
4. Unit/integration tests assert exact exception class names instead of HTTP behavior, or fail to cover both types.
5. @Validated is deleted from a service after following a controller-specific guide, disabling service method validation.
6. Leftover javax.validation imports after migrating Boot 2.x to Boot 3.x.
7. A return-value constraint failure is mapped to HTTP 400 instead of 500.
8. AOP method validation with self-invocation fails to guard internal call paths as expected.
9. Legacy code manually declaring MethodValidationPostProcessor or Validator beans conflicts with Boot auto-configuration.
10. Tests run with a different dependency tree from production, leading to different validation handlers.

**Avoid “catch Exception and return 400”**: it hides server bugs, persistence errors, code flaws, and return-value violations. Clearly separate input errors from server contract errors.

## 8. Error Handling Models in Spring MVC

MVC has two important scenarios:

**Scenario A: Validating a single object argument**

~~~java
@PostMapping("/products")
ProductView create(@Valid @RequestBody CreateProduct dto) {
    // ...
}
~~~

If CreateProduct fails constraints and the method has no direct constraints activating method validation, the error is typically **MethodArgumentNotValidException** (or BindingResult if handled inline in the right position).

**Scenario B: Method validation**

~~~java
@GetMapping("/products")
List<ProductView> list(
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    // ...
}
~~~

With Framework 6.1+ built-in validation, @Min errors normally become **HandlerMethodValidationException**. This is not merely a renamed MethodArgumentNotValidException; handlers must know about both.

If a project uses AOP @Validated on controller classes, also account for ConstraintViolationException or MethodValidationException per AOP configuration.

### 8.1. Building a Consistent Error Response

Spring supports @RestControllerAdvice and ResponseEntityExceptionHandler. With Spring Framework 6.1.x, you can override the corresponding methods to map validation errors to a shared JSON schema while preserving appropriate status codes.

Standalone example class in an MVC project:

~~~java
package dev.example.methodvalidation;

import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiValidationAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return handleExceptionInternal(
                ex,
                Map.of("error", "INVALID_BODY", "status", status.value()),
                headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = ex.isForReturnValue()
                ? "INVALID_SERVER_RETURN"
                : "INVALID_METHOD_INPUT";

        return handleExceptionInternal(
                ex,
                Map.of("error", code, "status", status.value()),
                headers, status, request);
    }
}
~~~

This class illustrates branching on the two exception types in Spring MVC Framework 6.1+. JSON fields such as "error" are a custom contract, not a mandatory Spring Boot error format.

**Note:** do not unconditionally force HandlerMethodValidationException to 400. In the example, handleExceptionInternal preserves the status passed by Spring—400 on input errors and 500 on return-value errors. In production, add request correlation IDs, standardized message codes, client-safe validation errors, and avoid leaking sensitive data.

To return detailed field errors, use BindingResult from MethodArgumentNotValidException and the ParameterValidationResult list from HandlerMethodValidationException. Choose stable annotation/property mappings rather than parsing ex.getMessage(), which can change across versions.

### 8.2. HandlerMethodValidationException Visitor

The framework provides a visitor to classify errors by HTTP parameter kind. Conceptual overview:

~~~text
HandlerMethodValidationException
  -> getAllValidationResults()
      -> ParameterValidationResult for @RequestParam
      -> ParameterValidationResult for @RequestHeader
      -> ParameterErrors for @ModelAttribute/@RequestBody object
  -> visitResults(visitor)
      -> requestParam(...)
      -> requestHeader(...)
      -> modelAttribute(...)
      -> other(...)
~~~

This is an API diagram, not compilable Java code. When aggregating errors by field, consult the exact Javadoc for your Spring version, as parameter annotation types, visitor callbacks, and nullability annotations can vary.

### 8.3. Do Not Catch AOP Exceptions in This Advice and Force Client Blame

ConstraintViolationException thrown by AOP validation on a service is not always a client error. It can stem from a controller bug calling a service improperly, an internal job, or a return-value violation. If handled, inspect context and return 400 only when API policy confirms client input violated the boundary. Internal invariant failures should normally be reported as server errors with metrics/alerts.

## 9. Complete Java 17+ and Spring Boot 3.3 Example: Three Validation Modes

This example uses **Spring MVC**, embedded Tomcat, Spring Boot 3.3.x / Spring Framework 6.1.x, Java 17+.

In a Gradle project with the Spring Boot plugin and Maven Central repository, dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The spring-boot-starter-validation dependency brings the Bean Validation API and typical provider (Hibernate Validator). Without a provider, do not assume annotations on the classpath suffice to execute constraints.

File structure:

~~~text
src/main/java/dev/example/methodvalidation/
    MethodValidationApplication.java
    ValidationDemoController.java
    PriceService.java
    ApiValidationAdvice.java
src/main/resources/
    application.yml
src/test/java/dev/example/methodvalidation/
    ValidationDemoControllerTest.java
~~~

### 9.1. Main Class

File src/main/java/dev/example/methodvalidation/MethodValidationApplication.java:

~~~java
package dev.example.methodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodValidationApplication.class, args);
    }
}
~~~

### 9.2. Controller: DTO Validation and Built-In Method Validation

File src/main/java/dev/example/methodvalidation/ValidationDemoController.java:

~~~java
package dev.example.methodvalidation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ValidationDemoController {

    public record CreateProduct(
            @NotBlank String name,
            @NotNull @Min(1) Integer quantity) {}

    public record ProductView(String name, int quantity) {}

    @PostMapping("/products")
    public ResponseEntity<ProductView> create(
            @Valid @RequestBody CreateProduct body) {

        ProductView result =
                new ProductView(body.name(), body.quantity());

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam(defaultValue = "1")
            @Min(1) int page) {

        return Map.of("page", page);
    }

    @PostMapping("/products/checked")
    public ResponseEntity<ProductView> createChecked(
            @RequestParam @Min(1) int tenant,
            @Valid @RequestBody CreateProduct body) {

        ProductView result =
                new ProductView(body.name(), body.quantity());

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping("/contract")
    @NotNull
    public String contract(
            @RequestParam(defaultValue = "false") boolean broken) {

        return broken ? null : "valid";
    }
}
~~~

Do **not place @Validated at the class level on ValidationDemoController** in this example. That is intentional so Framework 6.1+ built-in method validation is used.

Four endpoints illustrate the differences:

1. POST /api/products: only @Valid @RequestBody, so DTO errors normally produce MethodArgumentNotValidException.
2. GET /api/page?page=0: direct @Min on parameter, so errors normally produce HandlerMethodValidationException.
3. POST /api/products/checked?tenant=0: direct @Min selects method validation; nested constraints of the @Valid body also participate in method validation per 6.1+ rules.
4. GET /api/contract?broken=true: @NotNull on return value is violated, so built-in method validation detects a server-side error, usually HTTP 500.

### 9.3. Service: Still Uses @Validated + AOP

File src/main/java/dev/example/methodvalidation/PriceService.java:

~~~java
package dev.example.methodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class PriceService {

    @NotNull
    public Integer quote(@Min(1) int quantity) {
        return quantity * 100;
    }
}
~~~

The service does not handle HTTP requests directly. When another Spring bean injects PriceService and calls quote(0) **through the proxy**, AOP method validation normally throws ConstraintViolationException. When calling quote(2), the returned integer is 200.

The service uses int multiplication purely for illustration. In real billing applications, never use int with overflow risk for prices/currency; use BigDecimal with currency, rounding, and proper business rules.

**Do not add @Validated to controllers simply because it was added to services.** The two validation paths have different purposes and exception-handling mechanisms.

### 9.4. application.yml and Running

Create src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Run in the project directory containing Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Test valid requests:

~~~bash
curl -i "http://localhost:8080/api/page?page=2"
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","quantity":2}'
~~~

Key outputs to confirm: GET returns HTTP 200 and JSON {"page":2}; POST returns HTTP 201 and JSON {"name":"Keyboard","quantity":2}. Date, Content-Length, and other HTTP headers vary by environment.

Test invalid requests:

~~~bash
curl -i "http://localhost:8080/api/page?page=0"
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"","quantity":2}'
curl -i -X POST \
  "http://localhost:8080/api/products/checked?tenant=0" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","quantity":2}'
~~~

All three cases expect HTTP 400 in the demo configuration, yet **do not necessarily share the same exception type**. If ApiValidationAdvice from section 8.1 is added to the project, responses include distinct codes INVALID_BODY or INVALID_METHOD_INPUT respectively.

Return-value validation:

~~~bash
curl -i "http://localhost:8080/api/contract?broken=true"
~~~

Expected server-side error and HTTP 500 under built-in method validation. Never leave an endpoint intentionally breaking contracts like this in production; it exists only to illustrate why not every validation error should be forced to HTTP 400.

## 10. MockMvc Tests: Checking Behavior Instead of a Single Exception Name

With the section 9 project having spring-boot-starter-test, create src/test/java/dev/example/methodvalidation/ValidationDemoControllerTest.java:

~~~java
package dev.example.methodvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validQuerySucceeds() throws Exception {
        mvc.perform(get("/api/page").param("page", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(2));
    }

    @Test
    void directParameterConstraintReturns400() throws Exception {
        mvc.perform(get("/api/page").param("page", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void objectArgumentValidationReturns400() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\",\"quantity\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void combinedMethodValidationReturns400() throws Exception {
        mvc.perform(post("/api/products/checked")
                .param("tenant", "0")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Keyboard\",\"quantity\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validBodyReturnsCreatedProduct() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Keyboard\",\"quantity\":2}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(2));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These tests verify public HTTP behavior without relying on exact exception message strings. For version-compatibility tests, assertions on exception types can be added when intentionally **monitoring validation mechanism changes**; however, when upgrading the framework, those tests must be updated alongside intentional shifts.

To inspect exception types in a dedicated Spring MVC test, you can use MockMvc andExpect(result -> ...) to read result.getResolvedException(); just avoid turning your entire regression suite into implementation-detail tests when the goal is the HTTP contract.

### 10.1. Testing Service Validation Properly

Calling new PriceService().quote(0) is insufficient. An object instantiated with new is not a Spring AOP proxy, so the method validation interceptor will not trigger.

Tests should inject the PriceService bean from the ApplicationContext and invoke public methods through that bean:

~~~java
@Autowired
PriceService service;

@Test
void serviceRejectsZeroQuantity() {
    assertThrows(
            jakarta.validation.ConstraintViolationException.class,
            () -> service.quote(0));
}
~~~

This snippet must sit inside a test class with a Spring test context and JUnit's static assertThrows import. If the application customizes MethodValidationPostProcessor to adapt constraint violations into MethodValidationException, update the expected exception to match actual config.

### 10.2. Testing Invalid Data Cannot Replace Testing Missing/Malformed Data

@Min(1) can only be evaluated after page has been converted to int. With page=abc, binding/type conversion fails before method validation. With page omitted and different required/default settings, a missing-parameter error can occur. Test all three:

- Missing.
- Wrong type.
- Right type, constraint violated.

Testing only page=0 and concluding “validation handles all request errors” is incomplete.

## 11. WebFlux: Same Core Ideas, Different Exception for Object Validation

Spring WebFlux also provides built-in method validation on @RequestMapping methods since Framework 6.1. It uses DispatcherHandler/HandlerAdapter in a reactive pipeline instead of Servlet DispatcherServlet.

Key scenarios:

| WebFlux Case | Typical Error Type |
|---|---|
| @Valid @RequestBody command object, no direct method constraints | WebExchangeBindException |
| Direct @Min/@NotBlank on controller parameter in Framework 6.1+ | HandlerMethodValidationException |
| Return-value method constraint violated | HandlerMethodValidationException with server error |
| Class-level @Validated using AOP proxy | ConstraintViolationException or MethodValidationException depending on config |
| Malformed JSON/unsupported media type | Dedicated body-read/codec/HTTP message error |

### 11.1. WebFlux Controller Example

In a **separate Spring Boot WebFlux project** with spring-boot-starter-webflux, spring-boot-starter-validation, and spring-boot-starter-test, create src/main/java/dev/example/reactive/ReactiveValidationController.java:

~~~java
package dev.example.reactive;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/rx")
public class ReactiveValidationController {

    public record Payload(@NotBlank String name) {}

    @GetMapping("/page")
    public Mono<Map<String, Integer>> page(
            @RequestParam(defaultValue = "1")
            @Min(1) int page) {

        return Mono.just(Map.of("page", page));
    }

    @PostMapping("/payload")
    public Mono<Map<String, String>> payload(
            @Valid @RequestBody Mono<Payload> input) {

        return input.map(
                p -> Map.of("name", p.name()));
    }
}
~~~

Do not place @Validated at the controller class level when aiming for 6.1+ built-in method validation. In WebFlux, @Valid @RequestBody Mono<Payload> can validate nested objects when the reactive body is decoded; object validation failures typically surface as WebExchangeBindException under WebFlux.

### 11.2. WebTestClient Testing

Create src/test/java/dev/example/reactive/ReactiveValidationControllerTest.java:

~~~java
package dev.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ReactiveValidationController.class)
class ReactiveValidationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void directMethodConstraintReturns400() {
        client.get().uri("/rx/page?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validPageReturnsJson() {
        client.get().uri("/rx/page?page=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void invalidPayloadReturns400() {
        client.post().uri("/rx/payload")
                .bodyValue(Map.of("name", ""))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

To run the WebFlux example, you need an @SpringBootApplication class in a parent package of the controller and matching dependencies. @WebFluxTest uses a test slice, so it does not necessarily open a real HTTP socket. For controllers with injected services, provide mocks/test config; do not mix the MVC and WebFlux example projects into the same build without checking which web application type Boot selects.

### 11.3. Notes on Reactive Data and AOP Method Validation

AOP method validation on reactive services interacts with when a Publisher is created vs. when the Publisher actually emits data; how arguments/return values are checked depends on framework/version support and proxy mechanisms. Do not assume every nested Mono<T> is validated at the exact same moment as a synchronous Java parameter.

For WebFlux controllers, prefer the built-in mechanism of your version; when Publisher contents need validation, check @Valid argument binding, codecs, and WebFlux validation documentation. Never call .block() on the event loop just to force validation to run.

## 12. Services, Application Layer, and Non-HTTP Entry Points

Controller method validation targets HTTP requests. Yet business rules must still hold if the same service is invoked from:

- Scheduled jobs.
- Message listeners.
- CLI/batch imports.
- Unit/integration tests.
- GraphQL, gRPC, or an API that does not pass through annotated Spring MVC/WebFlux handlers.
- Event handlers or another service within the same application.

Therefore, services can use @Validated to guard constraints on method parameters and return values. It is an **additional line of defense**, not a replacement for HTTP-boundary validation.

For instance, an API should reject quantity=0 right at the controller (HTTP 400); if the same quantity=0 arises from a logic bug when a service is called internally, that may be a software defect warranting alerts/500 rather than automatically turning into a 400 user error.

### 12.1. Cross-Parameter Constraints

A method may need rules like “startDate <= endDate” or “one of the two identifiers must be present”. Some Bean Validation providers support cross-parameter constraints on executables using appropriate custom @Constraint/ConstraintValidator definitions.

However, for straightforward cases, a command object with @AssertTrue or a custom class-level constraint is often easier to understand because it groups all related data into a single DTO. Either way, clarify the boundary: HTTP request validation vs. service/domain invariants, and choose error mappings based on the error source.

### 12.2. Validation Does Not Run Automatically If the Object Is Not Spring-Managed

AOP method validation requires calls to pass through the Spring proxy. Calling new Service() in application code or tests without a context, calling private methods, or self-invocation can bypass interception. Never see @Min on a method and assume every call path is guarded.

For critical invariants, consider enforcing checks explicitly in domain code inside the method or value-object constructor rather than relying solely on AOP. Annotations clarify the contract, yet do not erase proxy limits or transaction boundaries.

## 13. Validation Groups and Nested Constraints

A CREATE API may require email while UPDATE allows omitting it. Marker interfaces can be defined:

~~~java
public interface CreateGroup {}
public interface UpdateGroup {}
~~~

And a DTO uses groups in annotations:

~~~java
public record UserInput(
        @NotBlank(groups = CreateGroup.class) String email,
        @Size(min = 3, max = 40) String displayName) {}
~~~

These are Java snippets requiring jakarta.validation.constraints imports inside an appropriate project. When @Validated(CreateGroup.class) is used on @RequestBody UserInput in the controller, Spring enforces CreateGroup as configured.

**Note:** When selecting only CreateGroup, constraints in the Default group may not run automatically unless selected or sequenced accordingly. If @Size should evaluate in both create and update, configure groups explicitly instead of assuming Default is always merged automatically.

Using @Validated on **an argument** to pick a group differs from placing @Validated at the **controller class level** to trigger AOP. When upgrading to 6.1+, do not accidentally delete valid argument-level group validation while removing class-level @Validated from controllers.

For PATCH APIs, validation groups do not preserve **missing vs. explicit null** distinctions after deserialization. Choose dedicated DTO/presence representations when the contract requires distinguishing them.

## 14. Missing Parameters, Null, and Non-Interchangeable Constraints

### 14.1. required Flag and @NotNull

@RequestParam(required=true) controls whether a request parameter is mandatory at the HTTP binding layer. @NotNull is a Bean Validation constraint on the Java value.

Example:

~~~java
@GetMapping("/report")
String report(
        @RequestParam(name = "year", required = false)
        @NotNull Integer year) {
    return "year=" + year;
}
~~~

With 6.1+ built-in method validation, @NotNull evaluates when year is omitted and the resolver supplies null. Yet if required=true is set, missing requests can be rejected right in the argument resolver before method validation checks @NotNull.

These two mechanisms can produce different exception types even though both result in HTTP 400. Thus test each situation: missing, empty, invalid type, and out-of-range.

### 14.2. @Valid Only Cascades; It Does Not Require @RequestBody Presence

@RequestBody has its own required flag; required=true by default. An entirely missing body can raise an error before @Valid inspects the DTO. Adding @NotNull directly on an @Valid DTO parameter can trigger method validation, but is not the standard replacement for @RequestBody(required=true).

If a DTO has @NotBlank name and the JSON field name is missing, Bean Validation catches it after deserialization; if JSON is malformed, a reader/codec error occurs before validation. Handling all cases via one single exception type is incorrect.

### 14.3. Return-Value Constraints Are Not Input Validation

A method with @NotNull return that actually returns null is a server-generated contract violation, normally resulting in 500 under built-in framework handling. Do not send raw stack traces to clients; return a generic server error and record technical details in controlled logs/metrics.

## 15. What to Do When Changing Spring Boot Versions?

A migration checklist is far more reliable than bulk find-and-replace on @Validated:

1. Confirm actual Spring Boot version, Spring Framework version, Java baseline, and Hibernate Validator provider.
2. Check whether the spring-boot-starter-validation dependency is present.
3. For Boot 2.x -> 3.x, replace javax.validation.* with jakarta.validation.* and audit Jakarta-compatible libraries.
4. Classify @Validated usages by location: controller class, controller argument group, service class, custom interceptor.
5. For MVC/WebFlux controllers on Framework 6.1+, try removing **class-level @Validated** to adopt built-in validation.
6. Verify direct constraints on @RequestParam/@PathVariable and return values execute.
7. Verify @Valid DTO binding/validation still works normally when methods have no direct constraints.
8. If controllers combine @Valid DTOs and @Min query params, test HandlerMethodValidationException and response schemas.
9. Add or update @ControllerAdvice to handle MethodArgumentNotValidException and HandlerMethodValidationException (MVC), or WebExchangeBindException and HandlerMethodValidationException (WebFlux).
10. Do not remove @Validated on services if MethodValidationPostProcessor/AOP is still needed.
11. Audit manual HTTP 400 returns to ensure they are not masking server invariant violations.
12. Check self-invocation/final/private methods in services whenever annotations appear ineffective.
13. Run tests for invalid input, invalid return values, invalid nested DTOs, missing/malformed inputs, and validation groups.
14. Run integration tests with real production dependencies; inspect logs and metrics after deployment.
15. Upgrade versions or retire legacy handlers only after QA; never infer runtime behavior solely from compilation succeeding.

Do not hack manual validate() calls into every controller when the framework already supports validation. Using standard mechanisms reduces boilerplate, keeps argument binding consistent, and yields richer validation results.

## 16. Common Errors and Diagnostics

### Error 1 — Placing @Validated on a Spring 6.1+ Controller and Wondering Why HandlerMethodValidationException Is Missing

If class-level @Validated routes calls through an AOP proxy, the exception may be ConstraintViolationException/MethodValidationException instead of built-in HandlerMethodValidationException. Check class annotations, AOP proxies, and framework version; remove class-level @Validated on controllers when targeting built-in web validation.

### Error 2 — Removing @Validated from Services While Fixing Controllers

Service AOP method validation normally relies on class-level @Validated. Once removed, constraints may stop running when the service is called. Apply the instruction to remove class-level @Validated only to controllers targeting 6.1+ built-in support; keep service configuration intentional.

### Error 3 — @Valid @RequestBody Throws a Different Exception After Adding @Min to the Method

Adding a direct constraint selects method validation. HandlerMethodValidationException may replace MethodArgumentNotValidException on violations. Update advice and tests to cover both.

### Error 4 — Assuming @Valid on String Makes It Required

@Valid is not a direct constraint. @NotBlank or @NotNull expresses the requirement. Choose annotations based on what must be checked.

### Error 5 — @Min(1) on Integer Still Lets null Pass

Numeric range constraints such as @Min normally treat null as valid. If the field is required, add @NotNull or an appropriate required flag. Primitives cannot hold null, though missing request values can still fail binding before validation.

### Error 6 — Forgetting the Bean Validation Provider

Having only jakarta.validation-api does not ensure runtime validation. In Spring Boot 3.x, spring-boot-starter-validation normally supplies Hibernate Validator. If annotations “do nothing”, inspect the dependency tree, auto-configuration, and Validator bean.

### Error 7 — Instantiating a Service with new and Expecting AOP Checks

new PriceService() does not pass through a Spring proxy; service method constraints will not execute. Test with beans injected from ApplicationContext or enforce explicit domain checks.

### Error 8 — Calling this.quote(0) Inside the Same @Validated Service

Self-invocation bypasses proxy interception in standard AOP. Refactor the call path or guard the invariant explicitly inside the method.

### Error 9 — Catching ConstraintViolationException and Returning 400 for All Sources

If the exception stems from a service bug or return contract, the fault is on the server. Map to client errors only when clearly determined that client input violated the HTTP boundary contract.

### Error 10 — Mapping Return-Value Violations to 400

HandlerMethodValidationException in 6.1+ built-in validation distinguishes input from return values; return violations are typically 500. Error handlers must preserve status or branch on isForReturnValue().

### Error 11 — Testing Only Valid Requests

Valid data does not prove validation is active. Write negative tests for negative queries, missing body fields, invalid nested objects, null returns, and proxied service calls.

### Error 12 — Confusing MVC with WebFlux

MVC uses MethodArgumentNotValidException for object arguments; WebFlux uses WebExchangeBindException. Both share built-in method validation since Framework 6.1, yet pipelines and error handlers differ. Use the classes/packages matching your stack.

### Error 13 — Confusing @Validated Groups with Class-Level AOP

@Validated(Group.class) on an argument selects validation groups rather than enabling a class proxy. Do not remove argument-level group validation when migrating class-level @Validated off controllers.

### Error 14 — Collapsing All 400 Errors into One Unstructured Generic Message

Input conversion, missing fields, Bean Validation, and policy violations have different causes. Return a consistent error schema while safely categorizing codes/fields so clients know what to fix.

### Error 15 — Duplicate or Misconfigured MethodValidationPostProcessor

Spring Boot already auto-configures validation infrastructure when a provider is on the classpath. Manually declaring a mismatched processor can stack proxies or alter exception types. If custom configuration exists, verify its purpose and re-test after upgrades.

### Error 16 — Ignoring Timeouts and Asynchronous/Reactive Return Values

Method validation does not automatically handle every rule when a Publisher emits items after the handler returns. In WebFlux, consult validation docs for reactive @RequestBody and return types, plus whether errors occur before or after the response commits.

## 17. Minimum Testing Matrix

| Test Case | Mechanism Under Test | Expected Outcome |
|---|---|---|
| GET /api/page?page=2 | Direct @Min, valid | 200 + page=2 |
| GET /api/page?page=0 | Direct @Min, 6.1+ built-in | 400, HandlerMethodValidationException |
| GET /api/page?page=abc | Type conversion | 400, not necessarily method validation |
| POST /api/products valid JSON | @Valid @RequestBody | 201 |
| POST /api/products name="" | Standalone @Valid DTO | 400, usually MethodArgumentNotValidException |
| POST /api/products quantity=0 | @Min on DTO | 400, usually MethodArgumentNotValidException |
| POST /api/products/checked tenant=0 | Direct method constraint and @Valid DTO | 400, usually HandlerMethodValidationException |
| GET /api/contract?broken=true | @NotNull return value | 500, server-side violation |
| PriceService bean proxy.quote(0) | Service AOP validation | ConstraintViolationException or adapted type per config |
| new PriceService().quote(0) | Bypasses AOP | Do not use as a test verifying AOP constraints |
| this.quote(0) inside same service | Self-invocation | Can bypass interception |
| WebFlux GET /rx/page?page=0 | Built-in reactive controller method validation | 400 |
| WebFlux POST invalid @Valid body | Object argument validation | 400, usually WebExchangeBindException |
| Controller still has class-level @Validated | Legacy AOP behavior | Exception type may differ from built-in |
| Missing Bean Validation provider | Runtime validation activation | Check dependencies/config; never assume annotations run |
| CreateGroup on DTO | Validation groups | Only constraints in the selected group(s) |

This matrix separates data errors, validation configuration errors, return-contract violations, and AOP pitfalls. During version upgrades, HTTP status/body tests verify external behavior, while exception-class tests intentionally verify the active mechanism.

## 18. Production Design Rules

**Boundary validation:** Validate request format, required fields, lengths, numeric ranges, and allowlists near the HTTP boundary to return clear 4xx responses. Never trust queries/bodies merely because they converted into Java objects.

**Service validation:** Use @Validated/AOP on services when methods are invoked from multiple entry points. Understand proxy limitations and avoid entrusting critical invariants solely to an annotation bypassable via self-invocation.

**Domain validation:** Rules that must hold under all circumstances, such as amount > 0, valid state transitions, or aggregate invariants, should also be guarded inside domain/value-object/service code.

**Error contract:** Maintain a consistent response schema distinguishing 400 input errors from 500 server errors. Avoid exposing stack traces, sensitive rejected values, or internal model details.

**Version-aware configuration:** Choose @Validated placement according to Framework version and class role. Framework 6.1+ controllers prefer built-in support when appropriate; services may still require @Validated AOP. Audit the classpath and Jakarta migration when upgrading Boot.

**Testing and observability:** Test invalid queries, invalid bodies, combined constraints, missing/malformed inputs, return validation, and proxied services. Track 400/500 rates and watch for misclassified validation errors.

## 19. Self-Check Questions

**Question 1. Is @Valid a @Constraint annotation?**  
No. @Valid triggers cascade validation on objects; direct constraints such as @Min/@NotBlank/@NotNull express value-checking rules.

**Question 2. Does invalid @Valid @RequestBody data always throw MethodArgumentNotValidException?**  
No. That is the common case when validating only a single object argument in MVC. When the method requires direct method validation, HandlerMethodValidationException can be used from Framework 6.1+.

**Question 3. What did Spring Framework 6.1 change for controllers?**  
It added built-in method validation in MVC/WebFlux for @RequestMapping methods without needing the legacy controller AOP proxy; it introduced HandlerMethodValidationException to report results.

**Question 4. Should all @Validated annotations be deleted when upgrading from Boot 3.1 to 3.2?**  
No. Consider removing class-level @Validated only from controllers adopting built-in validation. Services using AOP method validation still normally require @Validated.

**Question 5. Does @Min(1) on Integer make the field required?**  
No. Null usually passes @Min; add @NotNull or an appropriate required flag if mandatory.

**Question 6. Why isn't ConstraintViolationException from a service automatically HTTP 400?**  
Because it may reflect an internal bug rather than an HTTP input error. Status mapping must reflect boundaries and error semantics.

**Question 7. Why can return-value method validation produce 500?**  
Because the server itself returned a value violating the method contract. HandlerMethodValidationException distinguishes return violations from input violations.

**Question 8. Does a @Validated service run checks on new PriceService() or self-invocation?**  
Not under standard AOP proxy mechanics, because those calls do not pass through the proxy.

**Question 9. Does WebFlux use MethodArgumentNotValidException for DTOs like MVC?**  
No. WebFlux uses WebExchangeBindException for object-argument validation; built-in method validation can use HandlerMethodValidationException.

## 20. Summary

To understand **method validation and how support changes across Spring versions**, keep four distinctions clear:

1. **Object argument validation:** @Valid/@Validated on a DTO, producing MethodArgumentNotValidException in MVC or WebExchangeBindException in WebFlux when applicable.
2. **Built-in web method validation since Spring Framework 6.1:** direct constraints on controller method parameters/return values; HandlerMethodValidationException; typically 400 for invalid input and 500 for return-value violations.
3. **AOP method validation on Spring beans:** @Validated at the service/component level, MethodValidationPostProcessor and proxies; typically ConstraintViolationException, or MethodValidationException if configured to adapt.
4. **Version migration:** Boot 2.x uses javax.validation; Boot 3.x uses jakarta.validation; prior to 6.1 controllers often needed class-level @Validated/AOP, whereas from 6.1 controllers have built-in support and should omit class-level @Validated to use it.

A durable solution is not scattering annotations everywhere. Identify whether data belongs to an HTTP argument or a service contract, understand exception types per Framework version, check both inputs and returns, and write tests proving validation executes in the right place at the right time.

## 21. Official Documentation

- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Spring WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — Jakarta Bean Validation and AOP Method Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — AOP Proxying and Self-Invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring Framework 6.1 Javadoc — HandlerMethodValidationException: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework Javadoc — MethodValidationPostProcessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework — Web MVC Controller Method Validation Change Introduced in 6.1: https://spring.io/blog/2023/07/13/spring-framework-6-1-m2-released/
