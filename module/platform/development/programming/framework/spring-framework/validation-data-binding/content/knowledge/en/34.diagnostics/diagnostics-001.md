# Constraints Not Running Due to Missing Provider or Missing Trigger Point

A very common issue in Spring Framework is when code already has `@NotBlank`, `@Min`, `@NotNull`, or `@Valid`, the application still starts up, yet clearly invalid data **produces no validation errors**. For example, a client sends `{"title":"","quantity":0}` and the endpoint still processes it; or a service method accepts an empty string even though the parameter declares `@NotBlank`.

We must distinguish **two groups of causes**:

1. **Missing or unloadable Bean Validation provider**: the code sees the `jakarta.validation.*` API annotations, but the runtime has no compatible implementation—such as Hibernate Validator—or mixes legacy `javax.validation` libraries with the Jakarta API.
2. **Provider present, but missing trigger point**: for example, a controller omits `@Valid` on `@RequestBody`; a service lacks class-level `@Validated` or is not called through a Spring AOP proxy; a nested DTO lacks `@Valid`; a custom Spring `Validator` is not registered/invoked; or the validation group does not contain the expected constraint.

There are also cases where **validation did run, but errors were mishandled**: the handler declares `BindingResult` and ignores `hasErrors()`, or `@RestControllerAdvice` turns a 400 error into a success response. Therefore, a diagnostic workflow is needed to separate **provider → constraint metadata → trigger → result/exception → HTTP mapping**.

This article belongs to the **Diagnostics** section of the **Spring Framework — validation-data-binding** module. Examples use **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Validation, and Spring MVC Servlet**. These versions are chosen for API consistency; they are not assumed to be the latest versions in every project.

## 1. Cause Diagram

~~~text
Annotation: @NotBlank, @Min, @Valid
             |
             v
[1] Namespace + classpath
    Correct jakarta.validation.* version?
             |
             v
[2] Provider
    Hibernate Validator/implementation available?
             |
             v
[3] Entry point
    MVC: @Valid/@Validated on argument?
    Service: @Validated + Spring proxy?
    Manual: jakartaValidator.validate(...)?
             |
             v
[4] Group + cascade + type
    Default/Custom Group?
    @Valid on nested property?
    Constraint supports field type?
             |
             v
[5] ConstraintValidator execution
    Any actual violation?
             |
             v
[6] Spring adaptation
    BindingResult, MethodArgumentNotValidException,
    HandlerMethodValidationException,
    ConstraintViolationException...
             |
             v
[7] Response/logging
    Does handler swallow errors or return HTTP 200?
~~~

**Annotations are not executable Java checks.** Having `@NotNull` on a field does not mean the JVM will automatically run it when calling a setter or constructing a record. There must be a runtime Bean Validation provider and a call through the right entry point.

### Quick Triage Table

| Symptom | Most Likely Cause | Check Step |
|---|---|---|
| No Jakarta constraints produce violations | Missing/incompatible provider | Runtime dependencies, direct Jakarta validator test |
| Direct provider test PASSES, invalid HTTP still gets through | Missing `@Valid` on MVC argument | Controller signature, MockMvc |
| Invalid root field errors, invalid nested email does not | Missing nested `@Valid` | DTO property/record component |
| Service method does not block invalid input | `@Validated`/AOP/proxy not triggered | Inject Spring-managed service bean |
| Self-invocation produces no exception | Internal method bypasses proxy | Test external vs internal call |
| HTTP 400 occurs even though provider did not run | Parse/conversion failure | Actual exception type |
| `@Size` does not report error on null | Null is valid for this constraint | Add `@NotNull` |
| Custom constraint does not run | Wrong `@Constraint`, retention, target, groups | Metadata and provider bootstrap |
| `javax.validation` annotation in Boot 3 | Legacy namespace | Switch to `jakarta.validation` |
| Handler is invoked despite invalid form | `BindingResult` present, unhandled | `errors.hasErrors()` |

## 2. Distinguishing the Three Types of Validators

### Jakarta Bean Validation API

~~~java
jakarta.validation.Validator
~~~

Has the method `validate(T object, Class<?>... groups)` returning `Set<ConstraintViolation<T>>`. It is executed by a provider; `@NotBlank`/`@Min` annotations are metadata for the provider to process.

### Spring Validator

~~~java
org.springframework.validation.Validator
~~~

Has `supports(Class<?>)` and `validate(Object, Errors)`. Developers write the logic themselves and call `errors.rejectValue(...)` or `errors.reject(...)`. It **does not automatically scan all Jakarta annotations** unless wrapped by an appropriate adapter.

### Spring LocalValidatorFactoryBean

~~~java
org.springframework.validation.beanvalidation.LocalValidatorFactoryBean
~~~

This is the adapter integrating Spring and Jakarta Bean Validation: it provides Jakarta `Validator`/`ValidatorFactory` capabilities and supports Spring validation contracts, translating `ConstraintViolation` into `FieldError`/`ObjectError` via `Errors`. Spring MVC can register a global validator when a provider is present.

**Interface mix-up mistake:** if a unit test calls `jakartaValidator.validate(badDto)` expecting a `Set<ConstraintViolation<...>>`, do not import `org.springframework.validation.Validator` and expect a method with the same signature. Sharing the short name `Validator` does not mean the two contracts are identical.

## 3. API Alone Is Not Enough: A Provider Is Required

A Spring Boot 3.5 project uses:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-validation` brings a common provider such as Hibernate Validator into the runtime dependency graph aligned with the Boot BOM. The `jakarta.validation-api` library alone only provides annotations and interfaces, and **is not enough to prove a runnable implementation is present**.

Check with Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency hibernate-validator
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency hibernate-validator
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate.validator
~~~

Focus on the **runtimeClasspath of the exact deployed module**, not just the compileClasspath of a library containing DTOs. If the provider is in `testImplementation` but missing from production runtime, unit tests may pass while the deployed application lacks the dependency. If it is marked `compileOnly`, there is also a risk that the runtime lacks the provider.

### Provider Bootstrap

~~~java
try (jakarta.validation.ValidatorFactory factory =
        jakarta.validation.Validation
            .buildDefaultValidatorFactory()) {

    jakarta.validation.Validator validator =
        factory.getValidator();

    // validator.validate(invalidFixture)
}
~~~

This is an in-method snippet. When no provider is available at runtime, bootstrapping may throw `NoProviderFoundException` (from `jakarta.validation`), or another `ValidationException` if the provider configuration is broken.

**Do not assume every application missing a provider throws the same exception at startup.** Behavior depends on the setup and whether Bean Validation initialization is required. Some MVC configurations have an optional validator that skips validation; the reliable approach is to **test direct provider bootstrap using a fixture guaranteed to be invalid**.

### Verifying the Provider Actually Takes Effect

~~~java
public record Sample(
    @jakarta.validation.constraints.NotBlank
    String name) {
}

Sample bad = new Sample("");
var violations = validator.validate(bad);
~~~

This is a snippet assuming an appropriate `validator` variable. If the provider works and the Default group is used, `violations` contains one error for `name`. If the result is still empty, inspect the metadata/namespace/group and provider; do not immediately blame Spring MVC.

## 4. Spring Boot 2 to 3: `javax` Differs from `jakarta`

With **Spring Boot 3 / Framework 6**, the corresponding annotations belong to:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
~~~

The Spring Boot 2 generation used:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Do not keep legacy `javax.validation-api` in Boot 3 expecting a Jakarta provider to automatically understand every javax constraint. During migration, you must update **all** DTOs, controllers, custom constraints, `ConstraintValidator`s, tests, validation groups, and transitive dependencies.

**Legacy code may still compile** because both APIs happen to be on the classpath; that does not prove the Spring Boot 3 runtime is processing legacy annotations.

### Migration Checklist

- Check the import of `@Valid` on handlers.
- Check imports of constraint annotations on DTOs.
- Check imports of `Constraint`, `Payload`, `ConstraintValidator` in custom annotations.
- Verify the Hibernate Validator version selected by the BOM.
- Remove or isolate incompatible Jakarta/Javax dependencies.
- Confirm a smoke test `jakarta.validation.Validator.validate(invalidDto)` runs on the final build artifact.

## 5. Trigger Points in Spring MVC

### `@Valid` Present on Controller Argument

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @Valid @RequestBody TicketRequest request) {
    // ...
}
~~~

When the JSON request is read and converted into `TicketRequest`, Spring MVC can run Jakarta validation because of `@Valid` on the **argument**. If the DTO is invalid, the argument validation path typically produces `MethodArgumentNotValidException` when there is no local `BindingResult` handling it.

### Forgetting `@Valid`

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @RequestBody TicketRequest request) {
    // ...
}
~~~

Without another trigger requiring method validation, this is a parsed Java object that **does not automatically validate constraint metadata**. `@RestController`/`@RequestBody` does not mean "automatically validate every DTO."

### `@Validated` Can Replace `@Valid` and Select Groups

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @Validated(Create.class)
        @RequestBody TicketRequest request) {
    // ...
}
~~~

`@Validated(Create.class)` selects the Create group during binding/validation on the corresponding argument; `Create` and the constraint groups must be defined properly. Do not replace `@Valid` with a custom group without verifying that constraints belong to that group.

### Do Not Only Put `@Validated` on the DTO Class

~~~java
@Validated
public record TicketRequest(
    @NotBlank String title) {
}
~~~

An annotation on the DTO class **does not** guarantee that every endpoint using the DTO will validate it. The trigger point must still be the handler parameter, a manual validator, or the corresponding method-validation service proxy.

### `BindingResult` Allows the Handler to Still Run

~~~java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("ticket") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
~~~

This snippet assumes `TicketForm` is declared. `BindingResult` must appear **immediately after** the validated argument. If errors occur, the controller may still be invoked to handle them itself. Thus, the handler being invoked **does not mean validation did not run**; the issue may be that the controller **did not read `errors.hasErrors()`**.

## 6. Direct Method Constraints Differ from `@Valid`

When Spring MVC 6.1+ runs built-in method validation, direct constraints on method parameters have their own mechanism:

~~~java
@GetMapping("/quota")
public Map<String,Integer> quota(
        @RequestParam("count") @Min(1) int count) {
    return Map.of("count", count);
}
~~~

With `count=0`, type conversion succeeds; `@Min(1)` fails and Spring MVC typically uses `HandlerMethodValidationException`.

With `count=abc`, converting the string to `int` fails; typically `MethodArgumentTypeMismatchException` is raised **before** `@Min` can be evaluated.

| Input | Issue | Common Exception |
|---|---|---|
| JSON `{"title":""}`, `@Valid @RequestBody` | Jakarta constraint | `MethodArgumentNotValidException` |
| `count=0`, `@Min(1) int` | Direct method constraint | `HandlerMethodValidationException` |
| `count=abc`, `int` | Argument conversion | `MethodArgumentTypeMismatchException` |
| Body `{` | JSON parsing | `HttpMessageNotReadableException` |
| `@Valid` omitted on body, no other trigger | DTO annotations not requested to validate | Handler may continue |

**Testing only HTTP status 400 is not enough to conclude validation ran.** Check `BindingResult.getFieldErrors()` and the exception class in diagnostic tests.

### Controller Class-Level `@Validated`

Spring 6.2 documentation indicates that if a controller has `@Validated` at the **class level**, method validation may be applied via an **AOP proxy**. To use the built-in MVC method validation introduced in Spring 6.1, you should **omit class-level `@Validated` on the controller**.

This rule **does not apply directly to services**: service beans typically need class-level `@Validated` to activate AOP method validation.

## 7. Nested Object Missing Cascade

DTO:

~~~java
public record Contact(
    @NotBlank String email) {
}

public record TicketRequest(
    @NotBlank String title,
    Contact contact) {
}
~~~

Even when the controller has `@Valid @RequestBody TicketRequest`, validation of the nested `contact.email` **does not necessarily run** if the `contact` property lacks cascade `@Valid`.

Fix:

~~~java
public record TicketRequest(
    @NotBlank String title,
    @NotNull @Valid Contact contact) {
}
~~~

The two annotations have different roles:

- `@NotNull` on contact: contact must not be null.
- `@Valid` on contact: if an object is present, validate constraints inside Contact.

**`@Valid` itself does not require the object to be non-null.** A null nested object is skipped by cascade under standard semantics. Therefore, add `@NotNull` if it is required.

For collections:

~~~java
public record TicketBatch(
    @NotEmpty
    List<@Valid TicketRequest> tickets) {
}
~~~

You need to validate nested elements while also bounding element count/memory. `@Valid` does not replace `@Size(max=...)` or body byte limits.

## 8. Not Every Value Violates Every Constraint

| Constraint | Null | Blank/empty | Notes |
|---|---|---|---|
| `@NotNull` | Invalid | May be valid | Only checks null |
| `@NotBlank` | Invalid | Invalid for blank CharSequence | For strings |
| `@NotEmpty` | Invalid | Invalid for empty string/collection/map/array | Not identical to non-whitespace |
| `@Size(min=1)` | Usually valid | Empty string invalid | Combine with NotNull if null is disallowed |
| `@Pattern` | Usually valid | Depends on regex | Does not require input by default |
| `@Min(1)` | Usually valid | Not applicable to arbitrary strings | Combine with NotNull if needed |
| `@Valid` | Skips null nested | Not a direct constraint | Only requests cascade |

A test using `name=""` to verify `@NotNull` will not produce a violation because an empty string is not null. Conversely, placing `@NotBlank` on an `Integer` is an unsupported type and may cause `UnexpectedTypeException`; that is not a "provider did not run" failure.

**Diagnostic tip:** use a fixture guaranteed to fail, such as `@NotBlank String title=""`, before expanding to complex annotations, null semantics, and custom validators.

## 9. Service Method Validation and Spring Proxy

A valid service:

~~~java
@Service
@Validated
public class TicketService {

    public TicketReceipt submit(
            @NotBlank String source,
            @Valid TicketRequest request) {
        // ...
    }
}
~~~

When Spring Boot has a provider and appropriate method validation auto-configuration, a call **through the Spring-managed bean proxy** can throw `jakarta.validation.ConstraintViolationException` if `source=" "` violates `@NotBlank`.

### Calling via `new` Has No Proxy

~~~java
TicketService service = new TicketService();
service.submit(" ", validRequest);
~~~

This is just a manually instantiated Java object, without a method-validation proxy. The `@NotBlank` annotation does not automatically inject validation code into the method body.

### Self-Invocation

~~~java
public void outer() {
    inner(" "); // Internal call.
}

public void inner(@NotBlank String input) {
    // ...
}
~~~

This is an illustrative snippet. When using proxy-based AOP, `this.inner(...)` typically **bypasses the interceptor**. Calling from another bean into the proxy is the expected path. Similarly, final/private methods or unsuitable proxy class configurations can restrict interception.

### Things to Verify

- Does the service have `@Service`/`@Component` and reside within component scan?
- Is class-level `@Validated` present on the service?
- Is the method interceptable by the proxy?
- Does the caller/other bean inject the service via Spring rather than using `new`?
- Is it free from self-invocation?
- Is Spring `MethodValidationPostProcessor`/auto-configuration enabled and not excluded or overridden?
- Is a compatible Jakarta provider active?

If `jakartaValidator.validate(dto)` PASSES but the service proxy test fails, **do not add random annotations to the DTO**; inspect the AOP path.

## 10. Validation Groups Causing a Constraint to Disappear

Example:

~~~java
public interface Create {
}

public record GroupedTicket(
    @NotBlank(groups = Create.class)
    String title) {
}
~~~

When calling:

~~~java
validator.validate(request);
~~~

by default the `Default` group is validated. The constraint on `title` belongs only to `Create` and is therefore not selected.

To check:

~~~java
validator.validate(request, Create.class);
~~~

In Spring MVC:

~~~java
public void create(
        @Validated(Create.class)
        @RequestBody GroupedTicket request) {
}
~~~

These are illustrative snippets requiring imports/definitions when placed into your own project. If a group sequence or inheritance is configured, how constraints are collected may differ.

**Common mistake:** switching a handler from `@Valid` to `@Validated(SomeGroup.class)` and assuming all constraints in the Default group still run; you must check the specific `groups`/`@GroupSequence` declarations.

## 11. Custom Constraints: Checking Metadata and Usage Points

A custom constraint requires an annotation with runtime metadata:

~~~java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = CodeValidator.class)
public @interface ValidCode {
    String message() default "Invalid code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is a snippet, not a standalone file: it requires `java.lang.annotation.*`, `jakarta.validation.Constraint`/`Payload` imports, and the `CodeValidator` implementation. The provider can only run it when the annotation is defined/placed on a valid type/target, `validatedBy` points to the right `ConstraintValidator<ValidCode,T>`, the group is selected, and an entry point exists.

For a custom `ConstraintValidator` that needs injected Spring dependencies, `LocalValidatorFactoryBean` typically configures `SpringConstraintValidatorFactory`. Creating a plain Jakarta `ValidatorFactory` in a unit test **does not automatically autowire Spring dependencies** into your custom validator. Separate testing of validator logic from DI/wiring tests, or use the application context when needed.

Common causes:

- `@Retention` is not RUNTIME.
- `@Target` does not include FIELD, METHOD, PARAMETER, or TYPE matching where the annotation is placed.
- `@Constraint(validatedBy=...)` is omitted or points to the wrong class.
- Importing `javax.validation.ConstraintValidator` in a Jakarta project.
- The validator's generic target type is incompatible with the property type.
- The group is not selected.
- The annotation is placed on a different property from the object actually being validated.
- The annotation was defined properly, but validation was never triggered at all.

Do not rush to scatter logs throughout `isValid`; first run a direct provider test on an invalid instance and inspect `getConstraintsForClass(...)`.

## 12. Custom Spring Validator Does Not Trigger Automatically

In addition to Jakarta Bean Validation, there is:

~~~java
public final class TicketPolicyValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return TicketRequest.class.isAssignableFrom(type);
    }

    @Override
    public void validate(
            Object target,
            org.springframework.validation.Errors errors) {
        // Call rejectValue or reject when needed.
    }
}
~~~

This snippet requires `TicketRequest` and appropriate imports. Simply creating the class or adding `@Component` **does not guarantee MVC will automatically invoke** this custom Spring Validator.

It must be registered:

~~~java
@InitBinder("ticketRequest")
void configure(WebDataBinder binder) {
    binder.addValidators(new TicketPolicyValidator());
}
~~~

This is a snippet inside a controller; the object name must match. Validation must then be triggered at the right time. Using `binder.setValidator(...)` instead of `addValidators(...)` may replace another validator you need to keep.

Manual DataBinder:

~~~java
DataBinder binder = new DataBinder(target, "ticketRequest");
binder.setValidator(customValidator);
binder.bind(propertyValues);
binder.validate();

BindingResult result = binder.getBindingResult();
~~~

Here `bind` only binds input; **`validate()`** is what instructs the validator to run. A standalone Spring `BeanPropertyBindingResult` only stores errors and does not invoke validators on its own.

## 13. Sample Project: Spring Boot 3.5 / Java 17+

Create a Spring Initializr project with **Spring Web + Validation**; add the test starter for testing. This example distinguishes provider, MVC argument validation, and service method AOP.

Common package: `com.example.validationdiagnosis`.

### 13.1. Gradle Dependencies

In a project that already has the Spring Boot Gradle plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Do not separately add `javax.validation-api` to this project. The code requires Java 17+ and Spring Boot 3.5 dependency management.

### 13.2. `ValidationDiagnosisApplication.java`

`src/main/java/com/example/validationdiagnosis/ValidationDiagnosisApplication.java`:

~~~java
package com.example.validationdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ValidationDiagnosisApplication.class, args);
    }
}
~~~

### 13.3. `CreateTicketRequest.java`

`src/main/java/com/example/validationdiagnosis/CreateTicketRequest.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateTicketRequest(
    @NotBlank String title,
    @NotNull @Min(1) Integer quantity,
    @NotNull @Valid Contact contact
) {
    public record Contact(
        @NotBlank String email
    ) {
    }
}
~~~

If `title=""`, the root constraint reports an error. If `quantity=0`, `Min` reports an error. If `contact.email=""`, the nested constraint reports an error thanks to `@Valid` cascade. If `contact=null`, `@NotNull` reports an error without requiring the provider to descend into a nonexistent object.

### 13.4. `TicketService.java`

`src/main/java/com/example/validationdiagnosis/TicketService.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class TicketService {

    public TicketReceipt submit(
            @NotBlank String source,
            @Valid CreateTicketRequest request) {

        return new TicketReceipt(
            "ACCEPTED", request.title());
    }

    public record TicketReceipt(
        String status, String title) {
    }
}
~~~

Class-level `@Validated` enables service method validation when called through a Spring proxy. The method is designed to be **public, non-final** and does not manually check `source` with an `if`, so tests reveal the difference between an external-proxy call and a direct Java call.

### 13.5. `TicketController.java`

`src/main/java/com/example/validationdiagnosis/TicketController.java`:

~~~java
package com.example.validationdiagnosis;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {

    private final TicketService tickets;

    public TicketController(TicketService tickets) {
        this.tickets = tickets;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<TicketService.TicketReceipt> create(
            @Valid @RequestBody CreateTicketRequest request) {

        TicketService.TicketReceipt receipt =
            tickets.submit("web", request);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(receipt);
    }

    @GetMapping("/quota")
    public Map<String, Integer> quota(
            @RequestParam("count") @Min(1) int count) {
        return Map.of("count", count);
    }
}
~~~

**There is no class-level `@Validated` on the controller**, so that Spring 6.1+ built-in MVC method validation is used. `TicketService` has its own `@Validated` because AOP service validation is a different boundary.

### 13.6. Running HTTP Checks

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Valid request:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"Repair","quantity":2,"contact":{"email":"a@example.org"}}'
~~~

Expect HTTP **201 Created** and body:

~~~json
{
  "status": "ACCEPTED",
  "title": "Repair"
}
~~~

Request with invalid title:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"","quantity":2,"contact":{"email":"a@example.org"}}'
~~~

Expect HTTP **400 Bad Request** due to `@NotBlank`. The exact default error body **is not fixed here** because Spring Boot config/ProblemDetail/advice may vary; tests will assert the exception class and field path.

Request with invalid nested email:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"Repair","quantity":2,"contact":{"email":""}}'
~~~

Expect HTTP 400, with a `FieldError` having path `contact.email`.

Direct `@Min` request:

~~~bash
curl -i \
  "http://localhost:8080/api/tickets/quota?count=0"
~~~

Expect HTTP 400 due to `@Min(1)`. With `count=1`, HTTP 200:

~~~json
{"count":1}
~~~

If `count=abc` is sent, that is a type conversion error rather than a `@Min` violation; HTTP 400 does not prove the direct constraint ran.

## 14. MockMvc Tests: Verifying Validation Triggers for Real

`src/test/java/com/example/validationdiagnosis/TicketValidationMvcTest.java`:

~~~java
package com.example.validationdiagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TicketValidationMvcTest {

    @Autowired
    private MockMvc mvc;

    private static String json(
            String title, String quantity, String email) {
        return "{\"title\":\"" + title
            + "\",\"quantity\":" + quantity
            + ",\"contact\":{\"email\":\"" + email
            + "\"}}";
    }

    @Test
    void validTicketIsCreated() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "2", "a@example.org")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("ACCEPTED"))
            .andExpect(jsonPath("$.title").value("Repair"));
    }

    @Test
    void blankTitleTriggersRequestBodyValidation()
            throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("", "2", "a@example.org")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("title"));
            });
    }

    @Test
    void zeroQuantityTriggersMin() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "0", "a@example.org")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("quantity"));
            });
    }

    @Test
    void nestedBlankEmailIsValidated() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "2", "")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("contact.email"));
            });
    }

    @Test
    void missingContactIsRejected() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"title\":\"Repair\",\"quantity\":2,"
                    + "\"contact\":null}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("contact"));
            });
    }

    @Test
    void minOnRequestParamTriggersMethodValidation()
            throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void validCountPasses() throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(1));
    }

    @Test
    void conversionFailureIsNotMinViolation()
            throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                MethodArgumentTypeMismatchException.class,
                result.getResolvedException()));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest());
    }
}
~~~

The nine tests above demonstrate the MVC boundary: provider/trigger presence, nested cascade, direct method constraints, and the difference between validation, conversion, and JSON parsing. The `json(...)` helper only concatenates synthetic test strings; for data containing arbitrary quotes/backslashes, use Jackson `ObjectMapper` instead of manual concatenation.

## 15. Testing Jakarta Provider and Service AOP Separately

### `ProviderDiagnosticsTest.java`

`src/test/java/com/example/validationdiagnosis/ProviderDiagnosticsTest.java`:

~~~java
package com.example.validationdiagnosis;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ProviderDiagnosticsTest {

    @Autowired
    private Validator jakartaValidator;

    @Test
    void providerFindsRootAndNestedViolations() {
        CreateTicketRequest bad = new CreateTicketRequest(
            "", 0,
            new CreateTicketRequest.Contact(""));

        Set<ConstraintViolation<CreateTicketRequest>> violations =
            jakartaValidator.validate(bad);

        Set<String> paths = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());

        assertTrue(paths.contains("title"));
        assertTrue(paths.contains("quantity"));
        assertTrue(paths.contains("contact.email"));
    }

    @Test
    void providerFindsConstraintMetadata() {
        assertTrue(jakartaValidator
            .getConstraintsForClass(CreateTicketRequest.class)
            .isBeanConstrained());
    }
}
~~~

If both of these tests PASS, the provider and basic metadata are working; if the same DTO passes through MockMvc without producing errors, focus on controller triggers/configuration.

### `TicketServiceValidationTest.java`

`src/test/java/com/example/validationdiagnosis/TicketServiceValidationTest.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TicketServiceValidationTest {

    @Autowired
    private TicketService tickets;

    private static CreateTicketRequest good() {
        return new CreateTicketRequest(
            "Repair", 2,
            new CreateTicketRequest.Contact("a@example.org"));
    }

    @Test
    void springProxyRejectsBadDirectArgument() {
        assertThrows(
            ConstraintViolationException.class,
            () -> tickets.submit(" ", good()));
    }

    @Test
    void springProxyValidatesNestedDto() {
        CreateTicketRequest bad = new CreateTicketRequest(
            "", 2,
            new CreateTicketRequest.Contact("a@example.org"));

        assertThrows(
            ConstraintViolationException.class,
            () -> tickets.submit("web", bad));
    }

    @Test
    void newObjectDoesNotInvokeSpringInterceptor() {
        TicketService direct = new TicketService();

        assertDoesNotThrow(
            () -> direct.submit(" ", good()));
    }
}
~~~

**Total 14 test methods**: 9 MockMvc + 2 provider + 3 service. The final test proves that creating an object with `new` bypasses the Spring proxy; this is a technical observation, **not a recommendation to bypass validation**.

### How to Run

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the provider smoke test:

~~~bash
./gradlew test \
  --tests "com.example.validationdiagnosis.ProviderDiagnosticsTest"
~~~

These tests are **designed to PASS with Spring Boot 3.5 and the configuration described above**. This article only statically inspects the code and API documentation; **it does not claim Gradle was executed**.

If the provider test FAILS because the context cannot start, examine the first root cause and dependency graph. If the provider PASSES but the service fails, check `@Validated`/MethodValidationPostProcessor/proxy. If both provider and service PASS but MVC fails, check `@Valid`/global MVC validator/handler exception resolution.

## 16. If–Then Diagnostic Decision Tree

~~~text
A. Are Jakarta imports correct?
  |-- No: migrate javax -> jakarta, fix deps
  |-- Yes
      |
      v
B. Is a provider on runtimeClasspath?
  |-- No: starter-validation/provider
  |-- Yes
      |
      v
C. Does jakartaValidator.validate(badFixture) report errors?
  |-- No:
  |     - Check group/constraint semantics
  |     - Check nested @Valid
  |     - Check custom @Target/@Retention/@Constraint
  |     - Check provider initialization
  |
  |-- Yes:
        |
        v
D. Which boundary is the code running through?
   |-- Spring MVC:
   |     - @Valid/@Validated on DTO argument?
   |     - Direct method constraint?
   |     - BindingResult immediately after?
   |     - Is MVC getValidator() overridden?
   |
   |-- Service:
   |     - @Validated on service type?
   |     - Spring bean/proxy?
   |     - Self-invocation/new/final?
   |
   |-- Manual:
         - Was validator.validate(...) called?
         - Was DataBinder.validate() called?
        |
        v
E. Violations/exceptions occurred, yet HTTP still returns success?
   |-- Read BindingResult.hasErrors()
   |-- Check @ControllerAdvice/catch-all mapping
   |-- Distinguish type mismatch vs validation
~~~

This workflow pinpoints the root cause instead of adding or modifying annotations by guesswork.

## 17. `@Valid` Present but Handler Does Not Throw: Check BindingResult

~~~java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("ticket") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
~~~

This snippet requires defining `TicketForm`. If `BindingResult` appears **immediately after the argument**, Spring MVC may still invoke the handler when the form has errors. Do not confuse "the handler ran" with "the constraint did not run." To inspect, check `errors.getFieldErrors()`/`getGlobalErrors()` and decide the response.

A handler that ignores errors and returns `200 OK` is a bug in the **error-handling policy**, even when the provider correctly detected violations.

If a method has direct constraints on other parameters, whole-method validation may use `HandlerMethodValidationException`. One DTO's `BindingResult` does not automatically collect errors from all other parameters.

## 18. Custom Global MVC Validator Accidentally Replaces Jakarta Validator

Spring MVC typically integrates `LocalValidatorFactoryBean` when Bean Validation is on the classpath. If an application overrides:

~~~java
@Configuration
public class CustomMvcConfig implements WebMvcConfigurer {

    @Override
    public org.springframework.validation.Validator getValidator() {
        return new MyCustomValidator();
    }
}
~~~

This is an illustrative snippet; `MyCustomValidator` must be defined separately. If the custom global validator **does not run Jakarta Bean Validation**, `@NotBlank`/`@Min` in MVC may no longer be applied as before.

Instead of overriding the global validator indiscriminately:

- Keep the default Jakarta validator pipeline if Bean Validation is still needed.
- Add custom Spring Validators at a targeted scope using `@InitBinder` and `binder.addValidators(...)` where appropriate.
- If a custom global configuration is needed, ensure the adapter/provider is still used.
- Write a MockMvc regression test with a DTO guaranteed to be invalid.

An `OptionalValidatorFactoryBean` may handle a missing provider by **not executing validation**; do not treat it as a guarantee that constraints run. If a provider is mandatory for data integrity, a smoke test should fail when the provider is inactive.

## 19. Why Errors Seem "Hidden" Even Though Constraints Ran

Validation may have created `ConstraintViolation`/`FieldError`, yet:

- Catch-all advice swallows the exception and returns a default response.
- The controller accepts `BindingResult` without checking `hasErrors()`.
- The frontend does not read the current error body/schema.
- The message code lacks a corresponding translation in `MessageSource`.
- A new group/field path does not match the error mapper.
- Global/object errors are dropped because the mapper only reads `getFieldErrors()`.
- The test only inspects HTTP status without checking the resolved exception.

### `MessageSource` Does Not Decide Whether Constraints Run

`MessageSource` only resolves **message codes → localized text**. It is not responsible for bootstrapping the provider, triggering `@Valid`, or running `ConstraintValidator`. A missing translation can make a message fall back to the default message or fail lookup, but that is a **message display** issue, not proof that the constraint was not evaluated.

A `FieldError` carries candidate codes (e.g., `NotBlank.ticket.title`, `NotBlank.title`, `NotBlank.java.lang.String`, `NotBlank`). `MessageSource.getMessage(error,locale)` attempts to resolve these keys. Distinguish **recording errors in `BindingResult`** from **rendering errors** in the response/view.

### Do Not Expose Sensitive Data

When debugging, `ConstraintViolation.getInvalidValue()` or `FieldError.getRejectedValue()` may contain passwords, tokens, or PII. Use dummy fixtures in tests; in production, log codes/counts/route templates rather than logging raw input. Do not return stack traces or internal class/method names via the API.

## 20. Troubleshooting Table

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| Provider bootstrap throws `NoProviderFoundException` | No runtime provider | Gradle dependencyInsight, packaging |
| Boot 3 but still importing `javax.validation` | Wrong namespace | Scan imports, migrate to Jakarta |
| `@NotBlank` compiles yet invalid DTO passes through | No MVC trigger | Check `@Valid @RequestBody` |
| Valid root DTO test PASSES, invalid nested skipped | Missing `@Valid` on nested property | Test `contact.email` path |
| Nested `@Valid` present yet null passes | Missing `@NotNull` | Add appropriate null constraint |
| `@Size` does not reject null | Expected semantics | Also use `@NotNull` |
| `@NotNull` does not reject `""` | Blank is still non-null | Use `@NotBlank` |
| `@Validated(Create.class)` skips Default rules | Different groups | Compare groups |
| Custom constraint does not invoke `isValid` | Metadata/trigger/provider | Check @Retention/@Target/@Constraint |
| Service does not throw exception | Missing @Validated/proxy | Test bean via Spring |
| Same-class call does not validate | Self-invocation | Separate bean boundary |
| Call via `new` does not validate | Bypasses Spring AOP | Inject Spring-managed bean |
| Custom Spring Validator does not run | Not registered/`validate()` not called | @InitBinder/DataBinder test |
| HTTP 400 returned but `@Min` missing | Type mismatch/parse error | Check exception class |
| HTTP 200 despite errors in BindingResult | Controller ignores errors | Assert hasErrors/response |
| Global MVC validator replaced | Custom getValidator() | Inspect WebMvcConfigurer |
| Service provider PASSES yet HTTP fails | Different boundary | MockMvc exception/field tests |
| Wrong localization yet constraint errored | MessageSource config | Test codes and locale |
| Constraints "disappear" after software update | BOM/dependency/exclusion changed | Test provider in exact artifact |

## 21. Self-Check Exercises

**1.** `jakarta.validation-api` is present without a provider; do annotations run automatically? — No.

**2.** Direct provider test produces violations but MVC does not; what to check first? — `@Valid`/`@Validated` on the handler argument and MVC validator wiring.

**3.** `@Valid @RequestBody` misses errors inside nested contact; why? — Usually because the nested property lacks `@Valid` or has wrong group/metadata.

**4.** Why are both `@NotNull` and `@Valid` needed on nested contact? — One rejects null, the other requests cascading into the present bean.

**5.** Service has `@Validated` yet `new Service()` still accepts invalid input; why? — There is no Spring proxy/interceptor.

**6.** Does `this.inner()` inside the same bean trigger AOP method validation? — Usually not, because self-invocation bypasses the proxy.

**7.** Does `@Min(1)` reject `null`? — Usually not; use `@NotNull` if null is invalid.

**8.** Does `@NotNull` reject `""`? — No; an empty string is still non-null.

**9.** Does HTTP 400 when `count=abc` prove `@Min` ran? — No; that can be a conversion failure.

**10.** Does `@Validated(Create.class)` skip Default constraints? — Possibly, depending on group membership/group sequence.

**11.** Does using `MessageSource` automatically trigger `@Valid`? — No; it only resolves messages from error codes.

**12.** Which test distinguishes provider issues from Spring MVC wiring? — Direct Jakarta validator test followed by MockMvc with the same invalid DTO.

**13.** A handler accepts `BindingResult` and returns success without checking errors: is the provider definitely dead? — No; errors may have been recorded and ignored by the handler.

**14.** Why must a proxy service test inject the bean from Spring? — To execute through `MethodValidationPostProcessor`/AOP interception.

## 22. Deployment and QA Checklist

- [ ] `spring-boot-starter-validation` is included in the runtime module requiring validation.
- [ ] Correct `jakarta.validation.*` imports are used with Spring Boot 3.
- [ ] Direct provider test uses a fixture guaranteed to be invalid.
- [ ] Do not treat an arbitrary HTTP 400 as proof a constraint ran.
- [ ] `@Valid`/`@Validated` is placed properly on the MVC argument.
- [ ] Nested objects have `@Valid`; add `@NotNull` if required.
- [ ] Direct constraints use the proper MVC method validation path.
- [ ] Do not place class-level `@Validated` on controllers when built-in MVC method validation is needed.
- [ ] Services have type-level `@Validated` and are called through a Spring proxy.
- [ ] Watch out for `new`, self-invocation, and final/private methods.
- [ ] Verify Default/custom groups and group sequences.
- [ ] Audit custom constraint metadata: target, retention, validatedBy.
- [ ] Custom Spring Validators must be registered/called.
- [ ] Manual DataBinder must call `binder.validate()`.
- [ ] Do not replace the global MVC validator with a no-op.
- [ ] Handlers with BindingResult must check `hasErrors()`.
- [ ] Handle `MethodArgumentNotValidException`, `HandlerMethodValidationException`, and conversion errors appropriately.
- [ ] Use `MessageSource` for its intended purpose of translating errors.
- [ ] Do not log or return sensitive rejected values.
- [ ] Include provider, MVC, and service-proxy integration tests.
- [ ] Verify runtimeClasspath, build artifacts, and CI after upgrades.
- [ ] Run `./gradlew test` before claiming tests executed successfully.

**Conclusion:** When constraints do not run, do not look only at the annotation. Verify **correct API → compatible provider → validation entry point → groups/cascade → result/exception → HTTP response**. In Spring MVC, check `@Valid`/`@Validated` on parameters; in services, check class-level `@Validated` and calls through the Spring AOP proxy; in manual code, `validate(...)` must be called. **Direct provider test + MockMvc test + service proxy test** is the trio that locates the fault fastest.

## Official References

- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Spring MVC Validator Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — Spring Validator Interface](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Hibernate Validator — Documentation](https://hibernate.org/validator/documentation/)
