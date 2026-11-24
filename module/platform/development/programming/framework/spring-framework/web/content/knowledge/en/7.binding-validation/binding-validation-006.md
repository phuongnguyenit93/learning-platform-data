# Bean Validation with @Valid, @Validated, and Validation Groups in Spring MVC

## 1. Goal and Scope

A web application must validate input data before using it in business logic. Spring MVC integrates **Jakarta Bean Validation** so rules can be declared directly on objects and validation can be triggered when binding data into controller parameters.

After this lesson, you will be able to:

1. Distinguish **binding**, **validation**, and **business validation**.
2. Understand the roles of `@Valid`, `@Validated`, and constraint annotations such as `@NotBlank`, `@NotNull`, and `@Size`.
3. Define `Create` and `Update` groups, choose the right groups per endpoint, and understand the role of the `Default` group.
4. Validate nested objects using cascade validation and avoid unintentionally skipping groups.
5. Read errors with `BindingResult`, and distinguish `MethodArgumentNotValidException` from `HandlerMethodValidationException` in Spring MVC 6.1+.
6. Write integration tests with `MockMvc` for both valid and invalid inputs.

The scope is **Spring MVC on the Servlet stack**, using Java 17+, Spring Boot 3.x, and the `jakarta.validation` namespace. Spring WebFlux, custom validators outside Bean Validation, and data-layer business rules may involve additional flows; do not extrapolate the exact same exception behavior to every framework or version.

## 2. At Which Step Does Spring MVC Validate Data?

Suppose a client sends JSON:

```http
POST /api/users HTTP/1.1
Content-Type: application/json

{"name":"","email":"not-an-email","password":"abc"}
```

Simplified processing flow:

```text
HTTP request
     |
DispatcherServlet -> select controller/handler
     |
@RequestBody -> HttpMessageConverter (e.g., Jackson)
     |          convert JSON into Java object
     v
WebDataBinder / Validator
     |          apply @Valid or @Validated and constraints
     +---- errors -> handle validation errors (typically HTTP 400)
     |
     v
Controller method -> business processing -> HTTP response
```

Distinct concepts:

| Stage | Responsibility | Example |
| --- | --- | --- |
| **Binding / conversion** | Reads body/form/query, converts types, assigns into Java object | JSON string into `UserPayload`; `"7"` into `long` |
| **Bean Validation** | Evaluates declared constraints | `@NotBlank`, `@Email`, `@Size(min=8)` |
| **Business validation** | Checks rules depending on system state and transactions | Whether email already exists in DB, whether user can modify record |
| **Persistence constraints** | Database constraints safeguarding final consistency | `UNIQUE(email)`, `NOT NULL`, foreign keys |

**Bean Validation does not replace DB constraints or authorization.** Across two concurrent requests, both can pass an "email does not exist yet" check, so the database still needs a unique constraint and the application must handle conflict errors.

### Related Components

- `jakarta.validation` defines the standard annotations, `Validator`, `ConstraintViolation`, groups, and contract.
- **Hibernate Validator** is a widely used implementation of Jakarta Bean Validation, typically selected by Spring Boot via `spring-boot-starter-validation`. It is not synonymous with Hibernate ORM/JPA.
- `org.springframework.validation.Validator` is Spring's validation interface. `LocalValidatorFactoryBean` bridges Jakarta Bean Validation with Spring's `SmartValidator` and `Errors`.
- `@Valid` is defined by **Jakarta Validation**: `jakarta.validation.Valid`.
- `@Validated` is defined by **Spring Framework**: `org.springframework.validation.annotation.Validated`.

If a project only adds the API annotations without a **Validator implementation**, declaring constraints is not enough to ensure they are actually evaluated. In Spring Boot 3.x, declare the validation starter explicitly.

## 3. Core Constraints and Practical Semantics

| Constraint | Purpose | Things to remember |
| --- | --- | --- |
| `@NotNull` | Value is not `null` | Empty strings `""` and `"   "` are still valid |
| `@NotEmpty` | Not `null` and not empty: suitable for strings/collections/maps/arrays | Whitespace-only strings may still be valid |
| `@NotBlank` | String is not `null` and contains at least one non-whitespace character | Use for required text fields |
| `@Size(min=…, max=…)` | String length or collection/map/array size | `null` is usually considered valid; combine with `@NotNull`/`@NotBlank` when required |
| `@Email` | Checks email syntax per validator | Does not prove the email exists or belongs to the sender; often paired with `@NotBlank` |
| `@Min` / `@Max` | Integer/numeric bounds | For decimals, check `@DecimalMin`/`@DecimalMax` |
| `@Positive` / `@PositiveOrZero` | Strictly positive / non-negative number | Does not forbid `null` |
| `@Pattern(regexp="…")` | Checks regex on a string | Suitable only for well-bounded formats; avoid error-prone complex regexes |
| `@Past` / `@Future` | Date/time relative to current instant | Involves clock/time zone; test with an appropriate clock |
| `@Null` | Requires value to be `null` | Useful for server-generated IDs on creation requests |
| `@AssertTrue` | Boolean value must be true | Does not replace database-dependent business rules |

Example:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

record ProductRequest(
        @NotBlank String title,
        @Positive long stockQuantity,
        @NotBlank @Email String contactEmail,
        @Size(max = 200) String description) {
}
```

This is a **sample DTO** without an HTTP endpoint. Two things require care:

- `@Positive long stockQuantity` rejects `0`, whereas many domains allow zero stock; in that case use `@PositiveOrZero`.
- `@Size(max=200)` does not make `description` required. If optional, `null` is valid; if required, add a separate constraint.

Annotations only take effect at **validation trigger points**: Spring MVC does not automatically validate every object instantiated with `new`, populated via setters, or loaded from the DB.

## 4. How Do `@Valid` and `@Validated` Differ?

### `@Valid` — Marks an Object for Validation and Cascade

`@Valid` is a Jakarta Validation annotation. On an MVC parameter DTO, it instructs Spring to validate the object where appropriate. It defaults to the **`Default` group**. Placing `@Valid` on a nested object reference causes validation to descend into that object (cascade).

```java
@PostMapping("/users")
public void create(@Valid @RequestBody UserPayload body) {
    // Only enters the method when validation/binding succeeds
    // or when a BindingResult is present to handle errors actively.
}
```

This method snippet is illustrative. With `@Valid` alone as above, constraints declared **solely with `groups=Create.class`** are not automatically selected. Furthermore, `@Valid` **accepts no `groups` attribute**: syntax like `@Valid(Create.class)` is invalid.

`@Valid` itself **is not a non-null constraint**. To require a nested object to be present, combine `@NotNull` and `@Valid`.

### `@Validated` — Spring Selects Validation Groups

Spring's `@Validated` extends integration by accepting one or more groups:

```java
@PostMapping("/users")
public void create(@Validated(Create.class) @RequestBody UserPayload body) {
    // Evaluates constraints belonging to the Create group.
}
```

Selecting `Create.class` alone **does not automatically evaluate constraints belonging only to `Default`**. To run both common rules and creation rules, declare:

```java
@Validated({Default.class, Create.class})
```

`Default` here is `jakarta.validation.groups.Default`. Selecting multiple groups **does not guarantee evaluation order**; if ordering is required, use `@GroupSequence`.

### Quick Comparison Table

| Aspect | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation` | `org.springframework.validation.annotation` |
| Common purpose on MVC parameters | Triggers DTO validation with Default; cascades on nested properties | Triggers DTO validation with chosen groups |
| Selecting `Create`, `Update` directly on annotation | No | Yes, e.g., `@Validated(Update.class)` |
| Cascades into nested objects when placed on a field | **Yes** | **Does not replace `@Valid` on fields** |
| Placed at class level to enable AOP method validation on Spring beans | Not as a Spring AOP marker | Yes, with `MethodValidationPostProcessor` |
| On Framework 6.1+ controllers | Still used for objects | Use on **parameters to pick groups**; avoid class-level if using Spring MVC native method validation |

For HTTP input DTOs, you typically **pick one of the two** annotations on the parameter. There is no need to place both `@Valid` and `@Validated` on the same parameter just to select groups; nested DTOs still need `@Valid` at the cascade site.

## 5. Validation Groups

A validation group is a marker interface used to tie individual constraints to scenarios. One DTO can serve multiple actions with different rules.

Example:

- **Create**: body must not yet contain an ID; password is required and long enough.
- **Update**: body must have a valid ID; password is optional; name/email are still checked.
- **Common rules**: non-blank name, syntactically valid email, valid nested address.

Group declarations:

```java
public interface Create {}
public interface Update {}
```

Above are **two illustrative interface declarations**; each public interface must reside in its own Java file if written verbatim. In the complete application example later, they are package-private interfaces in a single file.

Attaching groups to constraints:

```java
record UserPayload(
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        Long id,

        @NotBlank String name,

        @NotBlank @Email String email,

        @NotBlank(groups = Create.class)
        @Size(min = 8, groups = Create.class)
        String password) {
}
```

When a constraint has no `groups` or `groups={}`, it belongs to **`Default`**. In this snippet:

| Constraint | Group |
| --- | --- |
| `id` must be `null` | `Create` |
| `id` must not be `null` | `Update` |
| `name` non-blank | `Default` |
| `email` non-blank, valid syntax | `Default` |
| `password` non-blank, at least 8 characters | `Create` |

Result:

| Activated group(s) | Checks executed |
| --- | --- |
| `Default` only, e.g., `@Valid` | Name and email |
| `Create` only | ID must be null; password required/min length |
| `Update` only | ID must not be null |
| `Default` + `Create` | Name/email + ID must be null + password |
| `Default` + `Update` | Name/email + ID required |

Warning: `@Validated(Create.class)` **does not automatically run Default**. This is a common design mistake when "adding groups" accidentally disables shared constraints.

If `@Validated` receives a group interface **extending `Default`**, rules from the parent group are included per Bean Validation semantics. However, passing `{Default.class, Create.class}` is the clearest to read when both groups are needed.

### Groups Select Rules, Not Fields for JSON Serialization

Bean Validation groups **do not determine by default which fields Jackson accepts, returns, or allows updating**. Omitted fields can still deserialize to `null` and then be evaluated by the group. Do not use validation groups as a mechanism to "hide sensitive fields" from responses; use dedicated DTOs/views/security policies.

## 6. Complete Application: Creating and Updating Users

The following example uses **Spring Boot 3.2+ with Spring Framework 6.1+**, Java 17+, Spring MVC Servlet, and Jakarta Validation. This baseline is chosen to demonstrate both DTO validation and Spring MVC 6.1+ **native method validation**. It assumes no database or repository.

### Dependencies

In a Gradle project already configured with the Spring Boot plugin, repositories, and test runtime, add:

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

This is a `build.gradle` snippet, not a standalone build file. In Maven, the two runtime dependencies are likewise `spring-boot-starter-web` and `spring-boot-starter-validation`, plus the test starter with scope `test`.

### Source Code

Create **`src/main/java/demo/validation/ValidationApplication.java`**:

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}

interface Create {}
interface Update {}

record Address(@NotBlank String city) {}

record UserPayload(
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        @Positive(groups = Update.class)
        Long id,

        @NotBlank String name,

        @NotBlank @Email String email,

        @NotBlank(groups = Create.class)
        @Size(min = 8, groups = Create.class)
        String password,

        @Valid @NotNull Address address) {
}

@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<Map<String, String>> create(
            @Validated({Default.class, Create.class})
            @RequestBody UserPayload body) {

        // Validation demo; a real app must persist to DB and hash passwords.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("name", body.name()));
    }

    @PutMapping("/{id}")
    Map<String, Object> update(
            @PathVariable long id,
            @Validated({Default.class, Update.class})
            @RequestBody UserPayload body) {

        // Structural validation does not automatically ensure path ID == body ID.
        if (!Long.valueOf(id).equals(body.id())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "path id differs from body id");
        }

        return Map.of("id", id, "name", body.name());
    }

    @GetMapping("/page")
    Map<String, Integer> page(@RequestParam @Min(1) int number) {
        return Map.of("number", number);
    }
}
```

This code is **a structurally valid single Java file**: only `ValidationApplication` is public; the interfaces, records, and controller are package-private. Place it in a Boot project as described and run via the Boot plugin; do not run `javac ValidationApplication.java` without supplying the Spring/Jakarta classpath.

### Endpoint Breakdown

**`POST /api/users`**

- `@Validated({Default.class, Create.class})` activates shared constraints and creation constraints.
- `id` must be `null` due to `@Null(groups=Create.class)`.
- `name` and `email` are required; `email` must also match valid email format.
- `password` must be non-blank and at least 8 characters.
- `address` is required (`@NotNull`), and `address.city` is checked via `@Valid` cascade; because `Default` is selected, `city`'s `@NotBlank` constraint applies.
- Valid input returns 201 with JSON `{"name":"An"}`. This is a demo API: there is no DB, no password storage, and no new ID returned.

**`PUT /api/users/{id}`**

- `@Validated({Default.class, Update.class})` runs shared constraints and update constraints.
- Body `id` must be non-null and positive (`@NotNull`, `@Positive` in `Update`).
- `password` may be `null` because its constraints belong only to `Create`.
- Name, email, and address are still checked because `Default` is included.
- The controller **explicitly checks** that the URL path ID matches the JSON body ID. Single-field Bean Validation cannot automatically infer a relationship between a path variable and this DTO.
- Valid input with ID 7 returns 200 with JSON containing `"id":7` and `"name":"An"`.

**`GET /api/users/page?number=…`**

- `@RequestParam @Min(1) int number` validates a **constraint directly on a controller parameter**, not on a DTO.
- With Spring Framework 6.1+ and a Bean Validation provider, this uses **built-in method validation**; violations can produce `HandlerMethodValidationException`.
- The controller in this example **does not put `@Validated` on the class**, allowing native MVC to handle method constraints. Prior to Spring Framework 6.1, validation for such parameters worked differently and typically relied on class-level AOP `@Validated`.

## 7. Running and Reading Results

In a standard configured Gradle project, run:

```bash
./gradlew bootRun
```

Use Bash/curl in another terminal (assuming the application runs on `localhost:8080`):

```bash
curl -i -X POST http://localhost:8080/api/users \
  -H 'Content-Type: application/json' \
  -d '{"id":null,"name":"An","email":"an@example.com","password":"secret123","address":{"city":"Ha Noi"}}'

curl -i -X POST http://localhost:8080/api/users \
  -H 'Content-Type: application/json' \
  -d '{"id":10,"name":"","email":"invalid-email","password":"abc","address":{"city":""}}'

curl -i -X PUT http://localhost:8080/api/users/7 \
  -H 'Content-Type: application/json' \
  -d '{"id":7,"name":"An","email":"an@example.com","address":{"city":"Ha Noi"}}'

curl -i 'http://localhost:8080/api/users/page?number=0'
```

**Expected results in the sample app** (without custom security/filters):

| Call | HTTP status | Why |
| --- | --- | --- |
| Valid POST | 201 Created | Both `Default` and `Create` pass |
| POST with ID, blank name, bad email, short password, blank city | 400 Bad Request | Violates multiple `Create` and `Default` constraints |
| Valid PUT with ID 7, no password | 200 OK | `Update` does not require password |
| GET number=0 | 400 Bad Request | `@Min(1)` on method parameter is violated |
| GET number=2 | 200 OK | Returns `{"number":2}` |

Error body format **is not fixed** unless you design a `@ControllerAdvice`: it may be `ProblemDetail`, Boot's default error structure, or output from a custom exception handler; do not infer from status 400 that JSON listing every field will appear. Bean Validation also **does not guarantee error ordering**.

The demo code does not handle real passwords. In production systems, never store or log plain-text passwords; hash them with a proper mechanism (such as a password encoder in your authentication setup) and enforce consistent security policies.

## 8. Cascade Validation — Validating Nested Objects

Constraints on fields of a nested DTO **are evaluated only when validation descends into that object**. `@Valid` performs the cascade:

```java
record Address(@NotBlank String city) {}

record OrderRequest(
        @NotBlank String reference,
        @NotNull @Valid Address shippingAddress) {
}
```

- `@NotNull` verifies `shippingAddress` is present.
- `@Valid` descends into `Address` when the object is non-null, thereby validating `city`.
- Omitting `@Valid` means `@NotNull` on the parent **does not validate** `city` on the child object.
- Omitting `@NotNull` means `shippingAddress=null` is normally skipped by `@Valid` cascade.
- When validation groups are requested, those groups also apply during cascade; a child constraint belonging only to `Default` will not automatically run if the parent selects only `Create` (unless group inheritance/conversion/sequences apply).

For containers in Bean Validation 2.0+/Jakarta Validation:

```java
record BulkOrder(
        @NotNull
        @Size(min = 1)
        java.util.List<@Valid OrderRequest> orders) {
}
```

Non-null `OrderRequest` elements are cascaded. If **null elements must be forbidden**, place the appropriate constraint on the element type:

```java
java.util.List<@NotNull @Valid OrderRequest> orders
```

In both snippets above, these are **illustrative DTO declarations** without endpoints. Container element validation behavior depends on the provider and valid metadata; there must be a trigger invoking the validator on `BulkOrder`.

### `@ConvertGroup` When Outer and Inner Groups Do Not Match

Suppose when creating an `Order`, you need to validate the address under group `AddressChecks` even though the outer call uses group `Create`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;

record OrderPayload(
        @Valid
        @ConvertGroup(from = Create.class, to = AddressChecks.class)
        AddressPayload destination) {
}

interface AddressChecks {}

record AddressPayload(
        @NotBlank(groups = AddressChecks.class) String city) {
}
```

When a request selects `Create.class`, cascading into `destination` converts the group to `AddressChecks.class`. `@ConvertGroup` **only has meaning on a cascade with `@Valid`**; it does not automatically apply to all fields of the parent DTO and does not change the parent group.

This section uses simple interface/record names to illustrate the mechanism; if placed in the same project as other examples with duplicate type names, rename them or separate packages.

## 9. `@GroupSequence` — Ordering Group Evaluation

When passing multiple groups to `@Validated({A.class, B.class})`, Jakarta Bean Validation **does not guarantee** `A` is checked before `B`. This matters when one group checks basic conditions and a subsequent group runs heavier logic.

Declaring a sequence:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface OrderedChecks {}
```

When `OrderedChecks.class` is requested, the validator:

1. Evaluates `Default` group constraints first.
2. If any violation occurs in `Default`, **stops without running** `ExpensiveChecks`.
3. If `Default` passes, then evaluates `ExpensiveChecks`.

Controller usage as a fragment:

```java
@PostMapping("/verify")
public void verify(
        @Validated(OrderedChecks.class) @RequestBody SomeDto body) {
}
```

`SomeDto` must be an application-defined DTO with constraints in the corresponding groups; the snippet above is a fragment, not a standalone runnable example. Do not use `@GroupSequence` merely to sort **field errors** returned to clients; its purpose is **group evaluation order** and short-circuiting between groups.

**Do not confuse two ways of using sequences:**

- `@GroupSequence` on a **group interface** (like `OrderedChecks`) creates an ordered composite group.
- `@GroupSequence` on a **DTO class** can **redefine `Default` for that class**. When redefining, the sequence must include the **DTO class itself** in place of `Default.class` in the class-level list; misconfiguration can throw `GroupDefinitionException`. Redefining Default is local to that class and does not automatically propagate the redefinition to child objects.

To avoid unnecessary complexity, start with `Default` and a few clear marker groups. Use sequences only when staged evaluation makes sense.

## 10. `BindingResult` and Handling Errors Directly in Controllers

Not every endpoint should throw an exception immediately when a DTO violates constraints. In traditional MVC form-rendering flows, a controller may need to preserve inputs and display errors on the view:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "register-form";
    }

    return "redirect:/registered";
}
```

This assumes `RegisterForm` is a JavaBean with declared constraints and the template view `register-form` exists. This is a **view-rendering controller fragment**, not standalone code from the REST sample app in Section 6.

Key points:

- `BindingResult` or `Errors` must sit **immediately after the validated parameter** it represents.
- You can inspect `bindingResult.getFieldErrors()`, `getGlobalErrors()`, and `hasErrors()` to display appropriate errors.
- Without `BindingResult`, input validation errors are normally turned by Spring into an exception and HTTP 400 per default error handling.
- With `@RequestBody`, you can also place `BindingResult` right after the DTO for custom handling; however, in REST APIs many teams prefer a centralized error handler for uniform responses.
- JSON parsing or type conversion errors usually occur **before validation**, so they do not always appear in `BindingResult`. For instance, a malformed body can throw `HttpMessageNotReadableException`.
- With **method validation** when constraints sit directly on controller parameters, Spring MVC 6.1+ coordinates with `Errors`/`BindingResult`: the method is invoked only if **every validation error pertains to parameters with `Errors` immediately following them**; if another parameter also fails, `HandlerMethodValidationException` is thrown.

## 11. DTO Input Validation vs. Method Validation in Spring MVC 6.1+

Spring MVC has two distinct paths that must be recognized to configure error handling accurately.

### Path 1 — Validating DTO Arguments

Example:

```java
@PostMapping("/users")
public void create(@Valid @RequestBody UserPayload body) {
}
```

When only validating an object argument via `@RequestBody`/`@ModelAttribute`'s own mechanism without direct constraints triggering method validation, Spring typically throws **`MethodArgumentNotValidException`** on invalid input when no `BindingResult` immediately follows.

### Path 2 — Validating Constraints Directly on Parameters / Return Values

Example:

```java
@GetMapping("/page")
public int page(@RequestParam @Min(1) int number) {
    return number;
}
```

`@Min(1)` is a direct constraint on a method parameter. Starting in **Spring Framework 6.1**, Spring MVC has **built-in method validation** to evaluate such constraints; on failure, it typically throws **`HandlerMethodValidationException`**. Direct constraints like `@NotNull` on a method parameter (even one annotated with `@Valid`) can route the entire handler through method validation, including DTO validation.

**`@Valid` itself is not a constraint**, so adding `@Valid` on a DTO does not trigger method validation by itself. This differs from `@NotNull`, `@Min`, or `@Size` placed directly on method parameters.

### Why Not Put Class-Level `@Validated` on New Controllers?

Spring Framework 6.1 added built-in method validation for MVC handlers. If a controller is annotated with **`@Validated` at the class level**, method validation may run through an **AOP proxy** instead of the native MVC mechanism. To leverage the `HandlerMethodValidationException` error API and Spring's recommended integration, **omit `@Validated` at the controller class level** when adopting the new path; keep `@Validated(Group.class)` on DTO parameters to select groups.

For **service beans**, class-level `@Validated` remains a common way to enable Spring AOP method validation via `MethodValidationPostProcessor`, provided the application has an appropriate proxy/validator. Proxy mechanisms are affected by self-invocation, public methods/proxy types, and annotation combinations; do not assume `new Service()` or intra-bean calls go through AOP.

### Version Milestones

| Platform | Key takeaway |
| --- | --- |
| Spring 5.x / Boot 2.x | Typically uses `javax.validation`; MVC validates object arguments, while method validation usually requires separate AOP setup. |
| Spring 6.0 / Boot 3.0–3.1 | Migrated to `jakarta.validation`; lacks Spring MVC 6.1's native method validation mechanism. |
| Spring 6.1+ / Boot 3.2+ | Spring MVC supports native method validation with `HandlerMethodValidationException`; avoid class-level `@Validated` on controllers when wanting native behavior. |

This table shows **common baselines**. Always check the actual `spring-webmvc` and validation provider versions in your dependency tree, especially if the project overrides BOMs or declares custom dependencies.

## 12. Exception Handling and Clear HTTP Error Design

In REST APIs, callers need to know which fields failed, without responses leaking stack traces or implementation details.

Sample handler for DTO errors (`MethodArgumentNotValidException`):

```java
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, List<String>>> invalidBody(
            MethodArgumentNotValidException ex) {

        List<String> messages = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error ->
                        error.getField() + ": " + error.getDefaultMessage())
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of("errors", messages));
    }
}
```

This is a **complete class that must be placed inside a Spring project**, illustrating only one exception type. If placed in the same package as the sample controller in Section 6, it changes the error body structure to an object containing `errors` (list order remains unguaranteed).

In Spring MVC 6.1+, you can handle `HandlerMethodValidationException` via `@ExceptionHandler` or by overriding the corresponding method in `ResponseEntityExceptionHandler`. Example fragment:

```java
@ExceptionHandler(HandlerMethodValidationException.class)
ResponseEntity<Map<String, Object>> invalidMethod(
        HandlerMethodValidationException ex) {

    List<String> messages = ex.getAllValidationResults().stream()
            .flatMap(result -> result.getResolvableErrors().stream())
            .map(error -> error.getDefaultMessage())
            .toList();

    return ResponseEntity.status(ex.getStatusCode())
            .body(Map.of("errors", messages));
}
```

This fragment requires imports `org.springframework.web.method.annotation.HandlerMethodValidationException`, `java.util.List`, `java.util.Map`, and `org.springframework.http.ResponseEntity`, placed **inside a `@RestControllerAdvice`**. `HandlerMethodValidationException` can represent both parameter violations and **return-value violations**; the status is typically **400 for input** and **500 for return-value errors**. Do not hardcode 400 for every case and accidentally mask server bugs.

In production systems, add handling for malformed JSON (`HttpMessageNotReadableException`), type conversion errors, business errors, validator group/metadata errors, and a standard response format (e.g., RFC 9457 `ProblemDetail`) along with correlation IDs where appropriate.

Constraint messages may contain developer-authored text; avoid exposing secret values inside rejected values to JSON or logs. For i18n, Spring provides `MessageSource`/message codes and Bean Validation message interpolation for localized messages.

## 13. Integration Tests You Can Add to the Sample Project

Create **`src/test/java/demo/validation/ValidationApplicationTests.java`**, using the declared `spring-boot-starter-test`:

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createAcceptsDefaultAndCreateGroups() throws Exception {
        mvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"An",
                      "email":"an@example.com",
                      "password":"secret123",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("An"));
    }

    @Test
    void createRejectsInvalidDefaultAndCreateConstraints() throws Exception {
        mvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id":10,
                      "name":"",
                      "email":"invalid",
                      "password":"abc",
                      "address":{"city":""}
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void updateDoesNotRequireCreateOnlyPassword() throws Exception {
        mvc.perform(put("/api/users/7")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id":7,
                      "name":"An",
                      "email":"an@example.com",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void updateRequiresId() throws Exception {
        mvc.perform(put("/api/users/7")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"An",
                      "email":"an@example.com",
                      "address":{"city":"Ha Noi"}
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directMethodConstraintIsValidated() throws Exception {
        mvc.perform(get("/api/users/page").param("number", "0"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/users/page").param("number", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value(2));
    }
}
```

Run:

```bash
./gradlew test
```

The test suite expects **5 passing methods** on the Boot 3.2+ / Spring 6.1+ baseline with the Jakarta provider enabled and no custom security/filters. Assertions focus on HTTP statuses and deterministic bodies from the example, **without relying on constraint violation order or default error schemas**.

To strengthen test coverage, add cases for:

- Create missing `address`: 400 due to `@NotNull`.
- `address.city=""`: 400 thanks to `@Valid` cascade.
- Create with `id=7`: 400 via `Create`; update with `id=null`: 400 via `Update`.
- Temporarily removing `@Valid` on `address` in a branch test: proves `city` errors are no longer caught by cascade (while `@NotNull` on address still runs).
- Using `@Validated(Create.class)` instead of `@Validated({Default.class,Create.class})` in an isolated test: demonstrates `Default`-only constraints are skipped.
- Putting `@NotNull` directly on a handler parameter under test: verifies when errors flow through `HandlerMethodValidationException`.
- When using a custom `@ControllerAdvice`, asserting the body schema, message codes, localization, and proper status for return-value failures.

## 14. Programmatic Validation in Services Without Depending on HTTP

Bean Validation is not exclusive to controllers. You can invoke `jakarta.validation.Validator` at appropriate data boundaries:

```java
package demo.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.util.Set;

public class StandaloneValidation {
    record Invoice(@NotBlank String customer, @Positive int total) {}

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Invoice invoice = new Invoice("", -2);
            Set<ConstraintViolation<Invoice>> errors =
                    validator.validate(invoice);

            System.out.println(errors.size());
        }
    }
}
```

This is **a standalone Java 17+ file independent of Spring MVC**, though compiling/running requires `jakarta.validation-api` and an implementation (such as Hibernate Validator) along with its runtime dependencies on the classpath. Create `src/main/java/demo/validation/StandaloneValidation.java` inside the Boot project from Section 6 (which already has the validation starter); run it via your IDE with the Gradle classpath or an appropriate `JavaExec` task.

When both `@NotBlank` and `@Positive` constraints on `Invoice("", -2)` are evaluated by a compliant provider, stdout is:

```text
2
```

Do not rely on the iteration order of `Set<ConstraintViolation<Invoice>>` when building responses. To validate specific groups:

```java
validator.validate(invoice, Default.class, Create.class);
```

This call is a fragment within a scope having `validator`, `invoice`, and the `Default`/`Create` types. `Validator#validate(object)` defaults to `Default`; passing groups evaluates only the specified groups and related inheritance/sequences/conversions.

For **method validation on services**, you can place class-level `@Validated` and `@NotNull`/`@Min` directly on method parameters inside a Spring-managed bean. Distinguish this from `Validator#validate(bean)` (which checks object state constraints); the standard validator also provides `ExecutableValidator` for inspecting method parameters/return values programmatically if needed.

## 15. Common Pitfalls to Avoid

1. **Missing implementation**: adding only `jakarta.validation-api` and expecting `@Valid` to run; with Boot use `spring-boot-starter-validation`.
2. **Wrong namespace imports**: Boot 3.x uses `jakarta.validation.*`, not `javax.validation.*` from the Boot 2.x era.
3. **Confusing `@Valid` with a required constraint**: `@Valid` only triggers/cascades; a `null` child object needs `@NotNull` if required.
4. **Assuming `@Validated(Create.class)` implies `Default`**: explicit groups do not automatically pull in `Default`.
5. **Annotating constraints on DTOs while forgetting to trigger validation at the boundary**: a deserialized body is not validated automatically.
6. **Using `@NotNull` for required strings**: `""` still passes; consider `@NotBlank`.
7. **Forgetting `@Valid` on nested fields / collection elements**: child constraints will not run as expected.
8. **Misplacing `BindingResult`**: Spring requires it immediately after the corresponding validated parameter.
9. **Handling all errors as one exception**: Spring MVC 6.1+ has both `MethodArgumentNotValidException` and `HandlerMethodValidationException`; parse/type errors throw other exceptions.
10. **Putting class-level `@Validated` on a controller while expecting native MVC method validation**: class-level may route via AOP, producing a different exception than expected.
11. **Thinking groups protect security/business rules**: roles, ownership, uniqueness, and concurrency must still be checked in the proper layer.
12. **Assuming error lists have a fixed order**: by default neither order nor first error is guaranteed; if group order matters, use `@GroupSequence`.
13. **Relying on input validation instead of DB constraints**: protect persistence too and handle race conditions.
14. **Returning sensitive rejectedValue data to clients**: be cautious with passwords/tokens/logs.
15. **Overloading one DTO for too many actions**: when groups get tangled, separate use-case DTOs are clearer and safer.

## 16. Choosing `@Valid`, `@Validated`, or Separate DTOs?

| Scenario | Suggestion |
| --- | --- |
| Single DTO with one shared rule set | `@Valid @RequestBody Dto` |
| Different constraints between create/update with very similar shape | `@Validated({Default.class,Create.class})` or `{Default.class,Update.class}` |
| Object containing child objects/lists with constraints | Add `@Valid` at the cascade site; add `@NotNull` if required |
| Groups must run in stages | `@GroupSequence` on a group interface, test short-circuiting |
| Inputs differ sharply in shape, editable fields, or requiredness | Create separate DTOs like `CreateUserRequest` and `UpdateUserRequest` |
| Validating direct scalar controller parameters, Framework 6.1+ | `@Min`, `@NotBlank`, etc. + native MVC method validation |
| Validating service bean methods | Class-level `@Validated`, proper AOP method validation config |
| Rules depending on DB, authenticated user, or system state | Business validation in service/domain + transaction/database constraints |

Practical mindset: define the **endpoint input contract** first; place constraints on the right DTO; select groups intentionally; ensure nested validation; handle errors consistently; and write tests for both happy and failing paths.

## 17. Self-Check Exercises

1. Create `OrderRequest` with `quantity` greater than 0, required `email`, and non-blank `shippingAddress.city`. Apply `@Valid` to the body: is a missing `shippingAddress` blocked if only `@Valid` is on the field? Why?
2. Add a `Publish` group requiring `description` to be at least 30 characters on publish. Why might `@Validated(Publish.class)` skip the default `@NotBlank` on `title`? Fix the parameter annotation.
3. Build a sequence running `Default` then `Publish`. If `title` is blank, does `Publish` run? Write a test proving it.
4. Given `GET /products?page=0` and `@Min(1)` on a controller parameter in Framework 6.1+, which exception can be thrown? If `@Valid @RequestBody` is also added, what must exception handling account for?
5. Write tests for updating a user: omitted password is valid, blank email must fail, body ID differing from path ID must fail business validation. Distinguish those three rule types.
6. In a controller method with `BindingResult` right after a DTO, if another `@RequestParam @Min(1)` parameter fails validation, is the controller guaranteed to be invoked? Explain native method validation.
7. Write a `@RestControllerAdvice` returning stable error codes without leaking rejected passwords for both common validation exceptions.

## 18. Official Documentation

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): distinguishing argument validation from native method validation, `@Valid`, `@Validated`, `BindingResult`, exceptions.
- [Spring Framework — Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/annotation/Validated.html): validation groups and AOP method validation.
- [Spring Framework — Spring MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): supported controller arguments.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): milestone introducing built-in MVC method validation.
- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): standard constraints, `Default`, groups, cascading, `@GroupSequence`, `@ConvertGroup`.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): auto-configuration and method validation for Spring beans.
