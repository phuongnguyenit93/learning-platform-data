# Binding, Bean Validation, and Input Error Identification in Spring WebFlux

## 1. Goal: From Untrusted HTTP Input to Actionable Errors

In a Spring WebFlux API, clients can send data via **JSON body, query string, path variables, headers, form fields, or multipart parts**. Before creating a resource, the system must clearly distinguish these stages:

1. **Route matching:** whether the request reaches the right handler by path/method/content type.
2. **Binding and conversion:** HTTP string/byte inputs are converted into Java objects, numbers, enums, records, or form objects.
3. **Bean Validation:** whether structurally valid Java values satisfy `@NotBlank`, `@Size`, `@Email`, `@Min`, custom constraints, and validation groups.
4. **Business validation:** whether the resource already exists, whether the user is authorized to create it, and whether domain state permits the operation.
5. **Error representation:** returning the right HTTP status and error code/field without leaking rejected input, tokens, or stack traces.
6. **Reactive lifecycle:** validation on `Mono<T>` can fail **when subscription occurs**; you must understand error propagation through the pipeline and avoid accidentally swallowing errors with an overly broad `onErrorResume`.

This article explains **Spring Framework 6.2 / Spring Boot 3.5, Java 17+**, in the **WebFlux Controllers** module. APIs, exceptions, and binding behavior may differ from Servlet MVC. The examples use `org.springframework.web.bind.annotation` for controllers and **`org.springframework.web.reactive`** for infrastructure, without mistakenly using MVC's `HttpMessageConverter` or `MethodArgumentNotValidException`.

### Practical Objectives

- Bind data via `@RequestBody`, `@RequestParam`, `@PathVariable`, `@ModelAttribute`, and `@RequestPart`.
- Declare Jakarta Bean Validation and know when validation **actually runs**.
- Distinguish **`WebExchangeBindException`** from **`HandlerMethodValidationException`**, as well as non-Bean-Validation decode/conversion errors.
- Know when `BindingResult`/`Errors` can be placed immediately after a model attribute or non-reactive request body, and when to use `Mono<T>.onError*`.
- Format consistent error JSON/ProblemDetail responses, localize messages, and preserve proper HTTP status codes.
- Guard against mass assignment, nested validation gaps, validation group pitfalls, unbounded input sizes, and error responses that leak secrets.
- Build a runnable application with `WebTestClient` tests covering valid/invalid/path/form/body cases.

## 2. Three Layers Often Lumped Together as “Validation”

### 2.1. HTTP/Body Decoding: Can the Data Even Be Read?

Request:

```http
POST /api/notes HTTP/1.1
Content-Type: application/json

{"title":
```

This is **incomplete JSON**. Jackson/the HTTP codec cannot deserialize it into a DTO; the problem occurs **before** `@NotBlank` on the title field is ever checked.

Similar errors:

- Malformed JSON syntax, wrong field types (e.g., object instead of string).
- `Content-Type` incompatible with the media types accepted by the endpoint.
- Missing required body, missing request parameter, or missing header.
- Query/path value cannot be converted to `int`/`UUID`/`enum`.
- Body or a single JSON record exceeds the codec `maxInMemorySize` limit.
- Malformed form field number/format or invalid multipart syntax.

Do not lump all of the above together as “Bean Validation failed.” They originate from different stages and may be mapped by WebFlux exception infrastructure to 400, 413, 415, etc., depending on the scenario and configuration.

### 2.2. Data Binding: Mapping Field Names to Properties/Constructors

Suppose a form sends:

```text
term=reactor&page=2
```

Spring uses `WebDataBinder` and the conversion service to construct/populate a model attribute with properties `term` and `page`. If `page` is `"abc"` while the target type is `int`, a **binding/type mismatch** occurs even before `@Min(1)` is evaluated.

`BindingResult` can hold both **binding errors** and **validation errors**. These differ from domain exceptions (such as a duplicate note title in the database).

### 2.3. Bean Validation: Well-Typed Object Violating Constraints

Example:

```json
{
  "title": " ",
  "contact": {
    "email": "not-an-email"
  }
}
```

The JSON is syntactically valid and Jackson can instantiate the object; however, `@NotBlank` and `@Email` can trigger violations. Bean Validation uses annotations from **`jakarta.validation`**, commonly implemented by **Hibernate Validator** via `spring-boot-starter-validation`.

> Distinguish the **validation contract** from **security authorization**. A DTO with a valid title length does not mean the user is permitted to create the resource or access another tenant's records.

## 3. Dependencies and Namespace for Spring Boot 3.5

In a Gradle project already configured with the Spring Boot 3.5 plugin, repositories, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a standalone build file. `spring-boot-starter-validation` supplies the Bean Validation provider the project needs; having annotations in code alone does not guarantee a runtime validator if the dependency is missing.

Core imports:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
```

Use **`jakarta.validation.*`** on Boot 3/Framework 6; do not copy `javax.validation.*` from Boot 2. `jakarta.validation.Valid` is a cascade marker, not a direct constraint like `@NotNull`.

### 3.1. How Spring Finds the Validator

When a Bean Validation provider is on the classpath, WebFlux can register a global `LocalValidatorFactoryBean`; `WebFluxConfigurer#getValidator()` allows providing a different validator. `@InitBinder` lets you configure validators or binding options for a narrow controller scope.

**Do not add `@EnableWebFlux` just to enable validation in a Boot application.** It can prevent Boot's WebFlux auto-configuration from working as default; use the starter and standard Boot configuration.

## 4. Input Data Classification by Annotation

| Input source | Annotation/method | Conversion mechanism | Typical errors |
| --- | --- | --- | --- |
| JSON request body | `@RequestBody DTO` or `Mono<DTO>` | `HttpMessageReader` + Jackson | Decode error, `WebExchangeBindException` |
| Query parameter | `@RequestParam` | `ConversionService` | Missing value, type mismatch, method constraint |
| Path segment | `@PathVariable` | `ConversionService` | Missing/unparseable, method constraint |
| HTTP header | `@RequestHeader` | Type conversion | Missing, format error, method constraint |
| Form/query/URI/header into object | `@ModelAttribute` | `WebDataBinder`, constructor/property binding | BindingResult or `WebExchangeBindException` |
| Multipart JSON metadata | `@RequestPart` | Part reader/codec | Decode failure, `WebExchangeBindException` |
| Functional WebFlux endpoint | `ServerRequest.bodyToMono(...)` | Codecs | Decode failure; Bean Validation does not apply automatically like controller annotations |
| Response/return value method constraint | Constraint directly on return | Method validation | `HandlerMethodValidationException`, typically server error on invalid return |

With **`@ModelAttribute`**, Spring WebFlux can bind from **form data, query parameters, URI variables, and request headers**. Form/query values usually take precedence on name collisions. Never use a persistence entity with setters for sensitive fields as a public model attribute, as this risks **mass assignment**. Design dedicated DTOs and restrict `allowedFields` if using property binding.

## 5. Common Bean Validation Annotations

| Constraint | Main meaning | Important notes |
| --- | --- | --- |
| `@NotNull` | Value is non-null | Empty strings can still pass |
| `@NotEmpty` | Collection/string/map is non-null and non-empty | Whitespace-only strings can still pass |
| `@NotBlank` | `CharSequence` is non-null and contains non-whitespace | Suitable for titles, names |
| `@Size(min,max)` | Length/size of string/collection/map/array | Does not block null unless paired with `@NotNull` |
| `@Min` / `@Max` | Numeric bounds | Suitable for page, quantity |
| `@Positive` / `@PositiveOrZero` | Positive / non-negative number | Does not prevent null on its own |
| `@Email` | Email address syntax per validator | Does not prove address existence or ownership |
| `@Pattern` | String matches regex | Does not block null on its own; overly complex regexes can cause CPU pressure |
| `@Past` / `@Future` | Temporal constraint | Watch clocks and time zones |
| `@Valid` | Cascades validation into nested objects/elements | Does not forbid null on its own |
| `@Validated(Group.class)` | Selects validation groups | Spring-specific annotation; group semantics must be explicit |

Java 17 DTO example using **record components**:

```java
record Contact(
        @NotBlank @Email String email) {}

record CreateNote(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}
```

If a client sends:

```json
{"title":"  ","contact":{"email":"bad-mail"}}
```

Jackson constructs `CreateNote`, yet validation reports errors on `title` and `contact.email`. When `contact=null`, `@NotNull` reports the error; `@Valid` **does not fail on null by itself**.

### 5.1. Field Violation Order Is Not an API Contract

Bean Validation providers may return multiple `ConstraintViolation`/`FieldError` entries in different orders across versions. In tests, assert the **set of field names and error codes** rather than requiring a specific order unless the API explicitly guarantees sorting.

### 5.2. DTO Validation vs Business Validation

`@Email` checks approximate format. It does not query DNS, send verification emails, or check whether the user owns the address. Likewise, `@Size(max=80)` does not check whether a title is duplicated, contains profanity, violates domain-specific character rules, or whether the user has permission to create the resource.

Never add network/DB operations inside a custom Bean Validation constraint if it would block the Reactor Netty event loop. For rules requiring I/O, implement them in the **reactive service layer**, returning `Mono.error(domainException)` on violation.

## 6. `@Valid @RequestBody Mono<T>` and Reactive Errors

Spring WebFlux allows:

```java
@PostMapping("/api/notes")
Mono<Note> create(
        @Valid @RequestBody Mono<CreateNote> body) {
    return body.map(this::save);
}
```

This is a fragment; `save` and the DTO must exist in the controller/service. The framework reads the body via HTTP codecs, validates the decoded object when the publisher is consumed, and only then emits the valid item to `map`. If validation fails, the pipeline **emits `onError(WebExchangeBindException)`** and `map(this::save)` does not execute for that item.

**WebFlux characteristic:** the controller may be invoked and return the publisher before decoding/validation finishes. Therefore, do not assume every Bean Validation failure happens synchronously upon entering the Java method.

### 6.1. Catching Errors Locally in the Reactive Chain

```java
return body
        .map(this::save)
        .onErrorResume(WebExchangeBindException.class, ex ->
            Mono.error(ex));
```

This fragment only illustrates type-specific handling; rethrowing here is redundant in a real application. If you want to build a JSON response directly inside the reactive chain, change the return type accordingly (`Mono<ResponseEntity<?>>` or a custom envelope), match `WebExchangeBindException` specifically, and never catch every `Throwable` and turn database failures into 400.

A more meaningful example for adding an audit metric:

```java
return body
        .map(this::save)
        .doOnError(WebExchangeBindException.class, ex ->
            metrics.incrementInvalidInput());
```

This fragment assumes `metrics` is already declared. Never log raw rejected bodies or credentials. If a `@RestControllerAdvice` already returns standard JSON, let exceptions flow through the error-handling infrastructure instead of repeating `onErrorResume` in every endpoint.

### 6.2. `BindingResult` and Reactive Wrappers

Spring docs allow:

```java
@PostMapping("/items")
ResponseEntity<?> submit(
        @Valid @RequestBody CreateNote body,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid input");
    }
    return ResponseEntity.ok("ok");
}
```

This is a **fragment**: when the request body is a **non-Mono-wrapped object** and `BindingResult` sits **immediately after** the validated argument, the controller can inspect errors itself. Conversely:

```java
// Do not place BindingResult immediately after Mono<DTO> as if the DTO
// were decoded synchronously:
void submit(
        @Valid @RequestBody Mono<CreateNote> body,
        BindingResult errors) { /* not a standard pattern */ }
```

With `Mono<DTO>`, use reactive error operators or global advice. **`BindingResult` cannot be placed arbitrarily at the end of the parameter list**; it must immediately follow the corresponding argument per framework support.

## 7. When Does WebFlux Throw `WebExchangeBindException`?

This is the primary error when **validating/binding a single command object** (e.g., `@RequestBody`, `@ModelAttribute`, `@RequestPart`) with `@Valid` or `@Validated`, provided:

- The target is not a `Map`/`Collection` container as distinguished in the docs.
- No valid `Errors`/`BindingResult` parameter is declared immediately after the parameter for local handling.
- The method does not fall under **method validation** (see next section).

`WebExchangeBindException` exposes `BindingResult`:

```java
@ExceptionHandler(WebExchangeBindException.class)
ResponseEntity<?> invalidBody(WebExchangeBindException ex) {
    List<String> fields = ex.getFieldErrors().stream()
            .map(FieldError::getField)
            .distinct()
            .toList();

    return ResponseEntity.badRequest()
            .body(Map.of(
                    "code", "INPUT_VALIDATION",
                    "fields", fields));
}
```

This fragment requires imports for the exception, ResponseEntity, List, and FieldError. It returns only field names, **not echoing rejected values**. Actual error sets may include object-level errors (`getGlobalErrors`) in addition to field-level errors; production code should construct an appropriate error representation.

**Do not confuse `WebExchangeBindException` with MVC's `MethodArgumentNotValidException`.** The two stacks use different exception classes.

## 8. Method Validation and `HandlerMethodValidationException`

Spring Framework 6.1+ includes **built-in method validation** for annotated controller methods; Spring 6.2 retains both validation levels.

Example:

```java
@GetMapping("/page")
Mono<Page> page(
        @RequestParam("number") @Min(1) @Max(20) int number) {
    return Mono.just(new Page(number));
}
```

`@Min` and `@Max` apply **directly to the method parameter**, so the framework validates at the method level. On failure, the typical exception is **`HandlerMethodValidationException`**, not `WebExchangeBindException`.

### 8.1. Classification Rules

| Method signature | Typical mechanism | Exception |
| --- | --- | --- |
| `create(@Valid @RequestBody Mono<CreateNote> body)` | Validate single body object | `WebExchangeBindException` |
| `form(@Valid @ModelAttribute Form form)` | Bind/validate single object | `WebExchangeBindException` |
| `upload(@Valid @RequestPart("meta") Metadata meta)` | Validate single part DTO | `WebExchangeBindException` |
| `page(@RequestParam @Min(1) int page)` | **Method validation** | `HandlerMethodValidationException` |
| `create(@NotNull @Valid @RequestBody CreateNote body)` | Has direct constraint `@NotNull` → method validation | May be `HandlerMethodValidationException` |
| Method with `@NotNull`/`@Positive` on return value | Method return validation | `HandlerMethodValidationException`; server-side invariant |

**`@Valid` itself is not a constraint annotation that triggers method validation**. Adding `@NotNull` directly on the parameter can switch the whole method onto the method validation path; the framework then applies both direct constraints and nested `@Valid`.

Do not write global advice that catches only one exception type. Changing a controller method signature can switch the exception branch even when the business DTO stays unchanged.

### 8.2. Class-Level `@Validated` on Controllers: A Common Source of Confusion

Spring docs recommend **omitting `@Validated` at the controller class level** when using built-in controller method validation (since Spring Framework 6.1). The reason: class-level `@Validated` can activate method validation via an **AOP proxy**, with different semantics and exception paths.

Distinguish:

- **Controller:** direct method validation can be applied by WebFlux **without** `@Validated` on the class.
- **Service bean:** to enable method constraints via Bean Validation AOP, e.g., `@Service @Validated`, understand proxy limitations and provider dependencies.
- **Parameter DTO:** `@Validated(SomeGroup.class)` on the argument is appropriate for selecting object validation groups.

Avoid adding `@Validated` to every controller "just in case," as it can alter test behavior and error mappings.

### 8.3. Inspecting Method Errors by Parameter

`HandlerMethodValidationException` provides:

```java
List<ParameterValidationResult> results =
        ex.getParameterValidationResults();
```

Each `ParameterValidationResult` exposes the method parameter, the argument (handle carefully as it may be sensitive), and `getResolvableErrors()`. When a nested object has errors, the result may be a `ParameterErrors` instance providing field-level information.

Spring also provides the **`HandlerMethodValidationException.Visitor`** to dispatch by annotation type (`requestParam`, `requestHeader`, `modelAttribute`, ...). This is safer than guessing parameter indices on multi-parameter endpoints.

**Never return `getArgument()` or raw invalid values in JSON or logs.** If method validation fails on a **return value**, that is usually a server bug/invariant violation—handle it as a server error rather than blaming the client.

## 9. Type Conversion, JSON Decode, and Missing Input Errors

Bean Validation runs only after the binder/decoder creates a value of the target type. Compare:

```http
GET /api/page?number=abc
```

`number` cannot be converted to `int`; this is not a `@Min(1)` violation. It triggers an input/binding error before the method validator runs.

```http
GET /api/page?number=0
```

`number=0` converts to `int` successfully, then `@Min(1)` fails → **method validation**.

```http
POST /api/notes
Content-Type: application/json

{"title":
```

This is a JSON parse error, not a `WebExchangeBindException` from `@NotBlank`.

### 9.1. Exceptions to Recognize

| Error source | WebFlux class/reality | Typical HTTP status |
| --- | --- | --- |
| DTO validation | `WebExchangeBindException` | 400 |
| Method constraint | `HandlerMethodValidationException` | 400 for parameters, 500 for invalid return |
| JSON parse/type conversion in body | `ServerWebInputException` or wrapped codec exceptions | 400 per contract |
| Missing request param/header/path variable | WebFlux input value exceptions | 400 |
| Unsupported Content-Type | `UnsupportedMediaTypeStatusException` | 415 |
| Unsupported Accept | `NotAcceptableStatusException` | 406 |
| Codec body/record too large | `DataBufferLimitException` (may be wrapped) | Per policy, typically 413 for oversized payloads |
| Well-formed resource ID not found | Business/domain exception | 404 |
| Domain conflict (duplicate identifier) | Domain exception | 409 |
| Unauthenticated / unauthorized | Spring Security | 401/403 |
| Database unavailable / internal bug | Server exception | 5xx |

**Do not rely solely on class names to determine absolute status codes.** Spring can wrap exceptions, and default error handlers or reverse proxies can alter responses. Write tests against the API contract.

## 10. `@ModelAttribute` in WebFlux: Data Binding and BindingResult

Example form/search request:

```http
GET /api/notes/search?term=spring&page=2
```

A form DTO:

```java
class SearchForm {
    @NotBlank
    private String term;

    @Min(1)
    private int page = 1;

    public String getTerm() { return term; }
    public void setTerm(String term) { this.term = term; }

    public int getPage() { return page; }
    public void setPage(int page) { this.page = page; }
}
```

In an annotated WebFlux controller:

```java
@GetMapping("/search")
ResponseEntity<?> search(
        @Valid @ModelAttribute SearchForm form,
        BindingResult binding) {

    if (binding.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "FORM_INVALID"));
    }

    return ResponseEntity.ok(
            Map.of("term", form.getTerm(), "page", form.getPage()));
}
```

Here `BindingResult` sits immediately after the **non-reactive `@ModelAttribute`**. The controller can choose to re-render an HTML form with field errors or return a 400 JSON API error.

### 10.1. Binding Errors Differ from Constraint Violations

For example:

- `page=abc` → cannot convert to int; `BindingResult` records a type mismatch.
- `page=0` → converts to int successfully, yet fails `@Min(1)`.
- `term=` → empty string, fails `@NotBlank`.

All three can be displayed to the user as field errors, yet **their origin and remediation differ**. Never echo raw exception messages or raw rejected values in the response.

### 10.2. Mass Assignment Protection

`@ModelAttribute` can combine constructor binding and property binding. If you use an entity with setters:

```java
class AccountEntity {
    private boolean admin;
    private String displayName;
    // getters/setters...
}
```

A client can send `admin=true` if the binder permits property binding. **Bean Validation is not mass-assignment protection.** Solutions:

- Use a **request DTO** containing only allowed fields.
- Prefer immutable constructor-bound DTOs when suitable.
- If property binding must be used, configure `WebDataBinder#setAllowedFields(...)` and never bind directly to an entity.
- Never allow clients to write `id`, `tenantId`, `role`, `ownerId`, or `isAdmin` unless business rules explicitly permit it.
- Verify permissions using server-side identity rather than client-declared fields.

### 10.3. `@InitBinder` Restricting Bindable Fields

Fragment:

```java
@InitBinder("searchForm")
void initSearchBinder(WebDataBinder binder) {
    binder.setAllowedFields("term", "page");
}
```

Requires importing `org.springframework.web.bind.WebDataBinder` and `@InitBinder`. The attribute name must match (e.g., using `@ModelAttribute("searchForm")`); if unsure of naming conventions, declare the name explicitly in the controller. Setting allowed fields is defense-in-depth; dedicated DTOs are still required.

## 11. `@RequestPart` and Validating Multipart Metadata

WebFlux allows:

```java
@PostMapping(
    path = "/uploads",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<?>> upload(
        @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    // Validate metadata before saving the file.
    return metadata.map(meta ->
            ResponseEntity.accepted().build());
}
```

This is a **method fragment**, not a production upload system. To bind the JSON part to `UploadMetadata`, the client must send the `metadata` part with an appropriate Content-Type. `FilePart` must be properly consumed/transferred/released; the snippet above intentionally explains only the signature—**do not use that pattern to store files**.

`@Valid`/`@Validated` on a `@RequestPart` DTO can produce `WebExchangeBindException`. Multipart also introduces other failure modes: oversized files, missing parts, spoofed MIME types, disk quotas, path traversal, and malware. Bean Validation on metadata **does not verify binary file content**.

Example record:

```java
record UploadMetadata(
        @NotBlank String description,
        @Min(1) int retentionDays) {}
```

If metadata has `retentionDays=0`, that is a validation error; if the file is an EXE disguised as a JPG, that is a file-content/risk-policy check that must run separately.

## 12. Validation Groups and Create/Update Flows

Different operations may require different constraints. For example, create requires a password or title, whereas update allows omitting fields while still bounding length if provided.

Declare marker interfaces:

```java
interface OnCreate {}
interface OnUpdate {}

record NoteCommand(
        @NotBlank(groups = OnCreate.class)
        @Size(max = 80, groups = {
                OnCreate.class, OnUpdate.class})
        String title) {}
```

Select the group at the parameter:

```java
@PostMapping("/commands")
Mono<Void> create(
        @Validated(OnCreate.class)
        @RequestBody Mono<NoteCommand> body) {
    return body.then();
}
```

And:

```java
@PatchMapping("/commands/{id}")
Mono<Void> update(
        @Validated(OnUpdate.class)
        @RequestBody Mono<NoteCommand> body) {
    return body.then();
}
```

These are **method fragments** illustrating group selection, not a complete runnable controller. `@Validated(Group.class)` is a Spring annotation supporting validation hints/groups, while `@Valid` triggers default cascade validation.

Notes:

- If you validate only group `OnUpdate`, constraints in the **Default** group do not run automatically unless group sequences are properly configured/included.
- `@NotBlank` for create will not apply to update if omitted from OnUpdate; however, if a client **sends title=""**, `@Size(max=80)` alone may let it pass. When you need "if present, must not be blank," add a constraint or distinguish null vs empty.
- PATCH has distinct **absent vs null vs blank** semantics. Standard DTOs may not distinguish an omitted property from a JSON `null` property; design an appropriate patch model.
- Do not use validation groups as a substitute for authorization or domain state machines.

### 12.1. Nested Group Conversion

When validating nested structures, `@ConvertGroup(from=Default.class,to=OnCreate.class)` can be placed on a cascade field to switch groups for the nested bean. This is an advanced Bean Validation feature; use it when the model clearly requires it and test nested group behavior, rather than adding it out of habit.

## 13. Custom Validators: When Single Annotations Are Not Enough

For example, a form with `startDate <= endDate` or requiring at least one of two fields to be populated. Cross-field rules typically require a **class-level constraint** or a Spring `Validator`.

### 13.1. Spring Validator

```java
class SearchFormValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return SearchForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchForm form = (SearchForm) target;
        if (form.getTerm() != null
                && form.getTerm().length() > 100) {
            errors.rejectValue("term", "term.tooLong",
                    "Search term is too long");
        }
    }
}
```

This is a **class fragment** requiring `org.springframework.validation.Validator`, `Errors`, and `SearchForm`. You can register the validator via `@InitBinder`/`WebDataBinder#addValidators` as appropriate. If `@Size(max=100)` is already present, do not duplicate the constraint in two places and give users two conflicting errors.

### 13.2. Jakarta Custom Constraint

A custom constraint typically consists of:

1. An `@Constraint(validatedBy=...)` annotation with `@Target`, `@Retention(RUNTIME)`, and `message/groups/payload`.
2. A `ConstraintValidator<MyConstraint,T>` class implementing `isValid`.
3. Tests for null, empty, boundaries, nested cascade, and validation groups.
4. No mutable per-request state stored in a singleton validator.
5. No blocking database queries or synchronous HTTP calls inside `isValid` on the event loop.

When async uniqueness is needed, write:

```java
return repository.existsByTitle(input.title())
        .flatMap(exists -> exists
                ? Mono.error(new NoteConflictException())
                : repository.save(new NoteEntity(input.title())));
```

This is a **fragment**, assuming reactive repository and domain exceptions are declared. It does not solve the "check then insert" race condition across concurrent requests; you need a **DB unique constraint** and proper conflict mapping, not just a pre-check.

## 14. Returning Contract-Compliant Validation Errors Without Masking Server Errors

When a DTO is rejected, the client should receive a **status** and a **stable error code**, optionally alongside a sanitized list of invalid fields. Two sound choices are an application-defined JSON envelope or RFC 9457 `ProblemDetail`.

```json
{
  "code": "INPUT_VALIDATION",
  "errors": [
    {"field": "title", "message": "must not be blank"}
  ],
  "requestId": "server-generated-correlation"
}
```

This is a **contract sample**, not Spring's default output. With `WebExchangeBindException`, extract only safe, publishable field names/error codes; never echo raw rejected values as they may contain secrets. With `HandlerMethodValidationException`, determine whether the error belongs to request input or a return-value invariant before choosing the status; never turn server bugs or DB outages into 400.

`ProblemDetail` is a model with standard fields like `type`, `title`, `status`, `detail`, and `instance`. You may add an extension property `code` per policy. Do not invent ad-hoc schemas by concatenating raw exception messages or stack traces into responses; keep error contracts consistent across controllers, filters, and gateways wherever possible.

**Incorrect** example:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<String> all(Exception ex) {
    return ResponseEntity.badRequest().body("invalid input");
}
```

This turns programming bugs, storage/DB failures, and upstream timeouts into HTTP 400. The next article on `@ExceptionHandler`, `@RestControllerAdvice`, and `ProblemDetail` covers Spring `ErrorResponse`, error handler precedence, security/filter boundaries, and already-committed responses in detail; this article focuses on distinguishing **invalid input data** from **server failures**.

## 15. Runnable Example: Java 17 + Spring Boot 3.5 WebFlux

The demo includes:

- `POST /api/notes` accepting `@Valid @RequestBody Mono<CreateNote>`, validating the nested contact, and returning 201 with the ID in the URL.
- `GET /api/notes/{id}` returning 200/404 by ID.
- `GET /api/notes/page?number=...` applying `@Min`/`@Max` **directly on the parameter** to demonstrate method validation.
- `GET /api/notes/search?term=...&page=...` using `@Valid @ModelAttribute` + `BindingResult` to distinguish form binding errors.
- `@RestControllerAdvice` mapping the two validation exceptions to distinct JSON payloads and mapping input decode errors to 400 without leaking raw input.
- `WebTestClient` tests against a real HTTP server (`RANDOM_PORT`).

This is an **in-memory demo** application. It has no Spring Security, persistent DB, cross-node conflict handling, rate limits, full localization, or audit logs; do not use it directly in production.

### 15.1. Project Structure

```text
webflux-validation-demo/
├─ build.gradle                         (Spring Initializr + dependencies)
└─ src/
   ├─ main/
   │  ├─ java/demo/input/
   │  │  └─ InputValidationApplication.java
   │  └─ resources/
   │     └─ application.properties
   └─ test/
      └─ java/demo/input/
         └─ InputValidationApplicationTests.java
```

In `src/main/resources/application.properties` you can put:

```properties
spring.application.name=webflux-validation-demo
# Do not enable raw request-body/headers logging.
logging.level.org.springframework.web=INFO
```

Do not add `spring-boot-starter-web` to the demo build, because having both MVC and WebFlux starters causes Boot 3.x to select the Servlet MVC application type by default.

### 15.2. Complete Java Source

Create **`src/main/java/demo/input/InputValidationApplication.java`**:

```java
package demo.input;

import java.net.URI;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class InputValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputValidationApplication.class, args);
    }
}

record Contact(
        @NotBlank @Email String email) {}

record CreateNote(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}

record Note(long id, String title, String contactEmail) {}

record PageInfo(int number) {}

record SearchResult(String term, int page) {}

record Violation(String field, String message) {}

record ApiError(String code, List<Violation> errors) {}

class SearchForm {
    @NotBlank
    private String term;

    @Min(1)
    private int page = 1;

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}

@RestController
@RequestMapping("/api/notes")
class NoteController {
    private final AtomicLong sequence = new AtomicLong(100);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Note>> create(
            @Valid @RequestBody Mono<CreateNote> input) {

        return input.map(body -> {
            long id = sequence.incrementAndGet();
            Note created = new Note(
                    id, body.title().trim(),
                    body.contact().email());

            notes.put(id, created);

            URI location = URI.create("/api/notes/" + id);
            return ResponseEntity.created(location).body(created);
        });
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Note> find(@PathVariable long id) {
        return Mono.justOrEmpty(notes.get(id))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Note not found")));
    }

    @GetMapping(path = "/page",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<PageInfo> page(
            @RequestParam("number")
            @Min(1) @Max(20) int number) {
        return Mono.just(new PageInfo(number));
    }

    @GetMapping(path = "/search",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> search(
            @Valid @ModelAttribute("searchForm")
            SearchForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(new ApiError(
                        "FORM_BINDING",
                        errors.getFieldErrors().stream()
                            .map(error -> new Violation(
                                error.getField(), "invalid"))
                            .distinct()
                            .toList()));
        }

        return ResponseEntity.ok(new SearchResult(
                form.getTerm(), form.getPage()));
    }
}

@RestControllerAdvice
class InputErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ApiError> objectValidation(
            WebExchangeBindException error) {

        List<Violation> fields =
                error.getFieldErrors().stream()
                    .map(f -> new Violation(
                            f.getField(), "invalid"))
                    .distinct()
                    .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INPUT_VALIDATION", fields));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ApiError> methodValidation(
            HandlerMethodValidationException error) {

        // Do not expose raw validated argument values.
        // If return-value validation fails, it is a server invariant,
        // not a 400 error attributed to the caller.
        if (error.isForReturnValue()) {
            return ResponseEntity.status(
                    HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError(
                    "SERVER_VALIDATION", List.of()));
        }

        return ResponseEntity.badRequest()
                .body(new ApiError(
                    "METHOD_VALIDATION",
                    List.of(new Violation(
                            "request", "invalid"))));
    }

    @ExceptionHandler(ServerWebInputException.class)
    ResponseEntity<ApiError> inputDecode(
            ServerWebInputException error) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                    "INPUT_DECODE",
                    List.of(new Violation(
                            "request", "malformed input"))));
    }
}
```

This is a **structurally valid single Java 17 file**: only `InputValidationApplication` is public; records, models, the controller, and advice are package-private in `demo.input`. Spring component scanning finds the controller and advice because they are in the same package under the application class.

Key takeaways:

1. **`create`** accepts `Mono<CreateNote>`; validation occurs during decoding/publisher consumption. If title/email is invalid, the body emits a validation error and **`notes.put` does not execute**.
2. `@NotNull @Valid Contact contact` ensures the nested contact is non-null and cascades down to email. If email is whitespace, `@NotBlank` fails; if format is invalid, `@Email` fails.
3. `notes` is an in-memory map, so GET on another node can return 404. There is no transaction/DB.
4. `URI.create("/api/notes/"+id)` creates a **relative Location** suited to a demo at the context root. In production with a context path or gateway version prefix, use a URI builder or trusted public URL strategy to construct Location properly.
5. **`page`** has direct `@Min/@Max` → built-in method validation. Do not place class-level `@Validated` on the controller.
6. **`search`** uses non-reactive `SearchForm` + `BindingResult` immediately after the argument; WebFlux supports this. The success body is an object, without needing to return `Mono<?>` when processing is non-blocking.
7. `InputErrorAdvice` uses **two separate handlers** for WebExchangeBindException and HandlerMethodValidationException. On JSON decode errors, the third handler returns **INPUT_DECODE** per contract without reflecting parser exceptions.
8. `Violation.message` is static text `"invalid"` so it does not leak rejected values, though a product UI may want localized default constraint messages; see section 18.
9. `@Min/@Max` on path/query is not authorization. If the app uses Security, protect endpoints per business policy.

### 15.3. Running the Example and Expected Output

Start the app:

```bash
./gradlew bootRun
```

**Valid POST:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"WebFlux validation","contact":{"email":"reader@example.org"}}'
```

If this is the first create request, expected response:

```http
HTTP/1.1 201 Created
Location: /api/notes/101
Content-Type: application/json

{"id":101,"title":"WebFlux validation","contactEmail":"reader@example.org"}
```

ID 101 is only an example when the counter starts at 100. The Location is a **relative path**, making no assumptions about host/proxy/port. GET `/api/notes/101` will return the resource in the same instance until restart.

**POST with constraint violations:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":" ","contact":{"email":"not-an-email"}}'
```

Expected **400 Bad Request**, code `INPUT_VALIDATION`, and errors on `title` and `contact.email`; field order is not guaranteed:

```json
{
  "code": "INPUT_VALIDATION",
  "errors": [
    {"field":"title","message":"invalid"},
    {"field":"contact.email","message":"invalid"}
  ]
}
```

**Method constraint failure:**

```bash
curl -i 'http://localhost:8080/api/notes/page?number=0'
```

Expected 400 and:

```json
{
  "code":"METHOD_VALIDATION",
  "errors":[{"field":"request","message":"invalid"}]
}
```

**Valid type but form validation error:**

```bash
curl -i 'http://localhost:8080/api/notes/search?term=&page=0'
```

Expected 400 and code `FORM_BINDING`, fields `term` and `page` (order not fixed).

**Unparseable form page:**

```bash
curl -i 'http://localhost:8080/api/notes/search?term=spring&page=abc'
```

`BindingResult` records the type mismatch and returns 400 `FORM_BINDING`, instead of the controller failing ambiguously.

**Malformed JSON syntax:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

Expected 400 **INPUT_DECODE** under the demo configuration; do not conclude that `@NotBlank` ran.

The outputs above represent the **expected contract of the reviewed sample code**, **not observed test execution results**.

## 16. Testing with WebTestClient on a Real HTTP Server

Create **`src/test/java/demo/input/InputValidationApplicationTests.java`**:

```java
package demo.input;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InputValidationApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void validBodyCreatesResource() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "title": "Reactive API",
                  "contact": {"email": "a@example.org"}
                }
                """)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Reactive API")
            .jsonPath("$.contactEmail")
                .isEqualTo("a@example.org");
    }

    @Test
    void blankTitleAndBadEmailFailObjectValidation() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "title": " ",
                  "contact": {"email": "wrong-address"}
                }
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_VALIDATION")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void missingContactFailsNestedNotNullConstraint() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {"title":"Valid title"}
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_VALIDATION");
    }

    @Test
    void directQueryConstraintTriggersMethodValidation() {
        client.get()
            .uri("/api/notes/page?number=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("METHOD_VALIDATION");
    }

    @Test
    void validPageWorks() {
        client.get()
            .uri("/api/notes/page?number=5")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.number").isEqualTo(5);
    }

    @Test
    void formBindingAndValidationErrorsHandledLocally() {
        client.get()
            .uri("/api/notes/search?term=&page=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("FORM_BINDING");
    }

    @Test
    void malformedFormIntegerProducesBindingError() {
        client.get()
            .uri("/api/notes/search?term=reactor&page=abc")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("FORM_BINDING");
    }

    @Test
    void validFormReturnsConvertedValues() {
        client.get()
            .uri("/api/notes/search?term=reactor&page=2")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.term").isEqualTo("reactor")
            .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void malformedJsonIsDecodeErrorNotBeanValidation() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_DECODE");
    }
}
```

Run:

```bash
./gradlew test
```

**Nine tests are designed to pass** on Spring Boot 3.5 WebFlux + Jakarta Validation provider. This is the expectation from reviewing APIs and flow, **not a report of an executed Gradle run**.

What the tests verify:

- Codec + Bean Validation participate together when processing `@RequestBody Mono<CreateNote>`.
- Nested cascade + `@NotNull` are not skipped.
- Method-level direct `@Min` is classified separately.
- `@ModelAttribute` with `BindingResult` handles both type mismatches and constraint violations.
- Malformed JSON is not mistaken for a field validation error.
- HTTP status/body contracts are observed on the embedded Netty server, not just by calling controller methods directly.

**Limitations:** these tests do not verify DB persistence, Security filters, multipart parsers, proxy size caps, default error serialization, race conditions, or localization. Add corresponding integration tests as those layers are introduced.

## 17. Cases Where Bean Validation Must Not Be Your Only Tool

### 17.1. Uniqueness and Transactions

A controller receiving valid input can still fail if the title collides with a database key. Never access a synchronous DB inside `ConstraintValidator` on the event loop. Use a reactive repository, unique DB constraints, and translate conflicts into HTTP 409 to prevent race conditions.

### 17.2. Authorization and Tenant Boundaries

`@NotNull Long ownerId` does not prove the user is authorized to specify that ownerId. Derive the owner from the authenticated principal/server-side context and validate access via the security service/DB. Never trust client-sent `role=admin` or `tenantId` fields.

### 17.3. Content Security and Uploads

`@Size(max=100)` on a filename does not check for path traversal, MIME spoofing, malware, or archive bombs. For multipart using `FilePart`/`PartEvent`, enforce upload byte/disk/part limits, file format validation, and quarantine/AV scanning as required by the business.

### 17.4. Rate Limits and Resource Exhaustion

A JSON array of millions of elements can overwhelm decoders and services even if every item passes `@Valid`. Configure `spring.http.codecs.max-in-memory-size` appropriately for Boot 3.5, body size caps, pagination, query complexity/timeouts, and rate limits. Bean Validation is not DDoS protection.

### 17.5. Reactive Cancellation

If a client disconnects while validation or a DB operation is in flight, the publisher may receive a cancel signal. Release resources and verify transaction cancellation semantics; `@Valid` does not handle resource cleanup, rollback, or idempotency.

## 18. Localization and Error Codes

Default Bean Validation messages can be resolved by the Spring/Bean Validation interpolator via `MessageSource` and locale. You can use:

```properties
# src/main/resources/messages_vi.properties
NotBlank.createNote.title=Tiêu đề không được để trống
Size.createNote.title=Tiêu đề phải có độ dài hợp lệ
```

This is an **example of the message bundle mechanism**, not a guarantee of exact message codes for every binding object naming scheme; real code should inspect `FieldError#getCodes()` to choose keys and test localization.

An annotation with a message template:

```java
@NotBlank(message = "{note.title.required}")
String title
```

can be resolved by the configured message source/validator. Localized messages must avoid leaking rejected values or template injection. For public APIs, stable **machine-readable error codes** should be language-independent, while human-readable messages depend on locale/`Accept-Language`.

### 18.1. Should You Return the Exact defaultMessage?

You can, if policy confirms the message is safe, properly escaped/encoded, and contains no sensitive data. Standard Bean Validation messages (`must not be blank`, `size must be between...`) are generally helpful. However, a custom validator can produce messages containing raw user input; **never blindly log or return every message**. The runnable example intentionally returns `"invalid"` to preserve a strict security boundary.

## 19. ProblemDetail / RFC 9457 in WebFlux

Spring Framework 6.2 supports `ProblemDetail` and `ErrorResponse` to represent HTTP errors as `application/problem+json`. For complex APIs, you can construct an error:

```java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
problem.setTitle("Input validation failed");
problem.setDetail("One or more fields are invalid");
problem.setProperty("code", "INPUT_VALIDATION");
```

This is a **fragment** requiring `org.springframework.http.ProblemDetail`/`HttpStatus` imports; use it inside `@ExceptionHandler` and add vetted extension fields as needed.

A body such as:

```json
{
  "type": "about:blank",
  "title": "Input validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "INPUT_VALIDATION"
}
```

is an illustrative representation, **not an automatic default that every WebFlux app returns identically**. Choose **one** consistent error schema for an API version or provide a migration plan, rather than endpoint A returning `{"code":...}` and endpoint B returning HTML/stack traces depending on the error.

## 20. Differences from Servlet Spring MVC

| Topic | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| HTTP body converter | `HttpMessageConverter` | `HttpMessageReader`/`HttpMessageWriter` |
| Input object annotations | `@RequestBody`, `@ModelAttribute` | Both available, with reactive wrapper support |
| Bean validation namespace on Spring 6 | `jakarta.validation` | `jakarta.validation` |
| Object validation exception | `MethodArgumentNotValidException` | **`WebExchangeBindException`** |
| Method validation exception | `HandlerMethodValidationException` | **`HandlerMethodValidationException`** |
| Bind form errors | `BindingResult` after non-reactive argument | Similar; reactive model attributes also supported |
| Mono body | MVC supports some reactive types, yet Servlet writer differs | Native `Mono<DTO>` and `Flux<DTO>` pipeline |
| Error infrastructure | MVC `HandlerExceptionResolver`, advice | WebFlux reactive exception infrastructure/advice |
| Server threads | Servlet worker threads | Reactor Netty event loops/non-blocking I/O |
| Blocking DB | Typically fits worker threads depending on load | Avoid blocking the event loop; R2DBC or boundedElastic |

**Never use MVC exception classes to catch WebFlux body binding errors**, and do not assume a `@ControllerAdvice` written for Servlet MVC works verbatim in a reactive app.

Spring Framework 6.1/6.2 built-in controller method validation means that when upgrading from Spring 5.x/Boot 2.x, both exception types and class-level `@Validated` semantics may differ. Read the migration guide and test controller signatures.

## 21. Troubleshooting: Symptom → Cause → Fix

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `@Valid` does not run | Missing Hibernate Validator/provider on classpath | Add `spring-boot-starter-validation`, test invalid DTO |
| `@Email` allows null | Constraint does not imply required | Pair with `@NotBlank` or `@NotNull` |
| Nested DTO not validated | Missing `@Valid` on nested field | Add cascade annotation and test nested DTO |
| POST malformed JSON skips WebExchangeBindException handler | Decode error occurs before Bean Validation | Handle `ServerWebInputException`/codec errors separately |
| Query number=0 returns 400 yet object validation handler misses it | Direct `@Min` triggers method validation | Handle `HandlerMethodValidationException` |
| Controller has class `@Validated` and method validation behaves differently from docs | AOP proxy path | Remove class-level `@Validated` to use built-in WebFlux validation |
| `BindingResult` misses errors with `Mono<DTO>` | Misusing reactive wrapper | Use `onError*`/advice, or non-reactive DTO + adjacent result |
| Form has page=abc yet API returns 500 | Type mismatch not handled as client input | Use BindingResult/proper error mapping |
| Spring binds isAdmin=true automatically | Mass assignment into entity | Use DTO + allowedFields/constructor binding |
| Title uniqueness validated only via pre-check | Race condition across requests | Database unique constraint, map to 409 |
| Error body leaks password/rejectedValue | Logging/returning raw BindingResult | Expose only safe field/code/messages |
| Validation runs yet service still saves invalid record | Validation annotations on wrong parameter/group | Test exact signature, group, and provider |
| One field reports multiple errors in changing order | Validator/provider order not guaranteed | Assert set of fields/codes; sort if API requires |
| `@Size` allows null | `@Size` does not imply required | Add `@NotNull`/`@NotBlank` |
| Method validation reports 500 for return value | Server invariant violation | Fix code/business logic; do not return 400 to caller |
| Default 400 response differs from API schema | Missing centralized error handling | `@RestControllerAdvice`/ProblemDetail |
| Upstream HTTP call from validator slows down app | Blocking on event loop | Move business rules into reactive service |
| Validation applies to JSON body only, skipping multipart metadata | Missing `@Valid @RequestPart` | Validate metadata, enforce file limits separately |
| Unit tests pass yet WebTestClient fails | Codec/binding differs over HTTP | `RANDOM_PORT` integration tests |
| JSON size limit behaves unexpectedly | Boot codec/config/total request limits differ | Use right property + gateway caps and test |

## 22. Pre-Release Checklist for WebFlux APIs

- [ ] Separate request DTOs from entities; bind only permitted fields.
- [ ] Use `jakarta.validation.*` with an actual runtime provider in the build.
- [ ] Omit `@Validated` on controller classes when using built-in method validation.
- [ ] `@Valid` cascades into nested DTOs; add `@NotNull` when the nested object is required.
- [ ] Distinguish missing/invalid type/decode errors from Bean Validation violations.
- [ ] Both `WebExchangeBindException` and `HandlerMethodValidationException` have clear policies.
- [ ] Return-value validation errors are handled as server invariants.
- [ ] Method parameter constraints like `@Min/@Max` are tested through the WebFlux handler pipeline.
- [ ] Form binding `BindingResult` immediately follows non-reactive `@ModelAttribute`/body when used.
- [ ] Reactive `Mono<DTO>` preserves error signaling; never "subscribe and drop errors."
- [ ] Create/update/patch validation groups are clear and tested for absent/null/empty.
- [ ] DB/business validation runs in the reactive service without blocking the event loop.
- [ ] Error responses use consistent codes and statuses without leaking rejected values or stack traces.
- [ ] Content-Type/Accept/malformed JSON/missing params have explicit error contracts.
- [ ] Upload metadata validation does not substitute for file content scanning/size/quota enforcement.
- [ ] Neither CORS nor Bean Validation is treated as authentication/authorization.
- [ ] Codec/max request/timeout/rate/multipart limits are configured at multiple layers.
- [ ] `WebTestClient` integration tests cover invalid/success, nested bodies, form conversion, and method validation.
- [ ] Observability tracks route templates/error codes without logging PII or tokens.
- [ ] Dependencies/providers/Spring Framework versions and Bean Validation groups are verified on upgrade.

## 23. Self-Assessment Exercises

1. In JSON `{"title":"  "}`, is the error JSON syntax, binding conversion, or Bean Validation? Which annotations does it depend on?
2. Why does `@Email` not prove an email exists, and why must you add `@NotBlank` when a value is required?
3. When a client sends `page=abc` for `int page`, has `@Min` run yet? Distinguish conversion from method validation.
4. Compare `@Valid @RequestBody Mono<CreateNote>` with `@Valid @RequestBody CreateNote, BindingResult`.
5. Why must `BindingResult` appear immediately after the model attribute? Should it be placed after `Mono<DTO>`?
6. A method has `@Valid` on a DTO, and then `@NotNull` is added to the same parameter. How can the validation mechanism and exception change?
7. Why should global WebFlux advice handle both `WebExchangeBindException` and `HandlerMethodValidationException`?
8. How does class-level `@Validated` on a WebFlux controller affect Spring 6.2 controller method validation?
9. Does `@Valid` on a null nested field fail automatically? What must be added?
10. For a record DTO with `title` and `contact.email`, design tests asserting both field violations without depending on order.
11. Why can `@ModelAttribute` binding an entity with an `isAdmin` setter be dangerous? How do you use DTOs/allowedFields?
12. Design `OnCreate`/`OnUpdate` validation groups: how do you allow an omitted title on update while rejecting a blank string?
13. A custom ConstraintValidator calls blocking JDBC; what risk does the WebFlux event loop face, and how do you move it to a reactive service?
14. If a URL path has a non-existent ID, should you return 400 or 404? What if the path ID has an invalid format?
15. If a title duplicates a DB record, why must you use 409 and a DB unique constraint rather than just `@Pattern`?
16. A client POSTs multipart with valid JSON metadata, yet the file contains malware. Is Bean Validation enough?
17. An error handler returns `ex.getRejectedValue()` in JSON responses: what security risk does this create?
18. Use `ProblemDetail` to construct a 400 error with a stable `code` field and localized detail.
19. When an application runs Boot 3.5 without `spring-boot-starter-validation`, why might annotations not be enforced at runtime?
20. When passing a `Flux<DTO>` into a controller, how do per-item validation and stream errors differ from `Mono<DTO>`?
21. Write `WebTestClient` cases for invalid JSON syntax vs valid JSON with a blank title; compare the error codes.
22. When a streaming response has already sent status 200 and bytes, can a subsequent validation/business error still switch the status to HTTP 400?
23. User-submitted data contains a secret in a message; design error/field violation logging without leaking the secret.
24. For an API with an annotated method return constraint, why is an invalid return value a server error rather than a 400?
25. Outline a migration path from Boot 2/Framework 5 to Boot 3.5: javax→jakarta, runtime provider, method validation, WebFlux exception mapping, and tests.

## 24. Official Documentation

- [Spring Framework 6.2 — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): distinguishing object validation from method validation and the two exception types.
- [Spring Framework 6.2 — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `@Valid`, `Mono<DTO>`, `WebExchangeBindException`, `Errors`.
- [Spring Framework 6.2 — @ModelAttribute WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html): binding, `BindingResult`, security.
- [Spring Framework 6.2 — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `@RequestPart` validation and FilePart.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, validation error messages.
- [Spring Framework 6.2 — WebFlux Config Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): global `Validator`/`WebFluxConfigurer`/`@InitBinder`.
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html): validation starter/provider, service method validation, MessageSource.
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): parameter results/visitor/return value errors.
- [Spring Framework 6.2 — WebExchangeBindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html): BindingResult/field errors.
- [Spring Framework 6.2 — ParameterValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html): field and method parameter errors.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux HTTP binding, validation statuses, and bodies.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested validation, groups, Bean Validation semantics.
