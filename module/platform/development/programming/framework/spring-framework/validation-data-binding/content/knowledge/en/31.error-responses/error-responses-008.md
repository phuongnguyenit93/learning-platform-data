# `ParameterValidationResult` and Parameter-Grouped Errors in Spring Framework

In Spring Framework 6.1+, when **method validation** detects multiple invalid constraints on a method's parameters, Spring does not force every violation into a single message string. Instead, Spring provides the **`MethodValidationResult`** model composed of **`ParameterValidationResult`** entries: each result identifies a validated parameter/value and the errors associated with it.

Example HTTP request to a controller:

~~~http
GET /api/quotes/0?limit=9 HTTP/1.1
Host: localhost:8080
X-Channel: other
~~~

with handler:

~~~java
@GetMapping("/api/quotes/{id}")
public QuoteView get(
        @PathVariable("id") @Min(1) long id,
        @RequestParam("limit") @Min(1) @Max(5) int limit,
        @RequestHeader("X-Channel")
        @Pattern(regexp = "web|mobile") String channel) {
    return new QuoteView(id, limit, channel);
}
~~~

All three arguments **convert to their Java types successfully** yet violate constraints: `id=0` violates `@Min(1)`, `limit=9` violates `@Max(5)`, and `channel="other"` violates `@Pattern`. In Spring MVC 6.1+ with built-in handler method validation, this typically produces **one `HandlerMethodValidationException` carrying three `ParameterValidationResult` groups**, each describing its corresponding parameter.

**Do not equate three error groups with three constraints in every scenario.** A `@Valid` DTO parameter can hold multiple field errors while still occupying **one group**; conversely, a collection parameter with multiple invalid elements can produce **multiple groups for different elements of the same parameter**.

This lesson belongs to the **Error Responses** group of the Spring Framework — validation/data binding module. Focus areas: reading `ParameterValidationResult`, distinguishing direct errors from nested DTO errors via `ParameterErrors`, group vs. violation counts, `List`/`Map`, cross-parameter errors, return values, i18n, and HTTP error response design. The hands-on section uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, and Servlet Spring MVC**.

## 1. Class model and key terminology

| API | Role |
|---|---|
| `org.springframework.validation.method.MethodValidationResult` | Interface holding method-level validation results, both the list of groups and target/method metadata |
| `org.springframework.validation.method.ParameterValidationResult` | One error group associated with a validated method parameter or container element |
| `org.springframework.validation.method.ParameterErrors` | Subclass of `ParameterValidationResult` that also implements `Errors` to represent field/object errors on a nested bean |
| `org.springframework.web.method.annotation.HandlerMethodValidationException` | Exception for built-in handler method validation in Spring MVC/WebFlux; implements `MethodValidationResult` and carries HTTP status |
| `org.springframework.validation.method.MethodValidationException` | Exception carrying adapted results in certain non-MVC method validation setups, such as AOP services |
| `org.springframework.context.MessageSourceResolvable` | Represents an error with message codes, arguments, and a default message resolvable via `MessageSource` |
| `org.springframework.core.MethodParameter` | Metadata descriptor for a Java method parameter or return value |
| `org.springframework.validation.FieldError` / `ObjectError` | Field-level and object-level errors accessible through `ParameterErrors` |

Relationships:

~~~text
MethodValidationResult
|
+-- target, method, isForReturnValue
+-- getParameterValidationResults()
|     |
|     +-- ParameterValidationResult
|     |      +-- MethodParameter
|     |      +-- argument
|     |      +-- List<MessageSourceResolvable>
|     |      +-- container / index / key if applicable
|     |
|     +-- ParameterErrors extends ParameterValidationResult
|            +-- implements Errors
|            +-- getFieldErrors()
|            +-- getGlobalErrors()
|
+-- getCrossParameterValidationResults()
      +-- errors from a constraint spanning multiple parameters

HandlerMethodValidationException
    implements MethodValidationResult
    +-- HTTP status, ErrorResponse/ProblemDetail
~~~

`ParameterValidationResult` is **not** a raw Jakarta Validation `ConstraintViolation<?>`. Spring has **adapted** the provider's output into a structure that integrates cleanly with Spring `MessageSource` and error handling. Never blindly cast items in `getResolvableErrors()` to `ConstraintViolation<?>`.

### Three distinct counting concepts

1. **Group count**: `ex.getParameterValidationResults().size()`. Each element is a `ParameterValidationResult`.
2. **Errors within a group**: `result.getResolvableErrors().size()`. One parameter can contribute multiple errors.
3. **Distinct Java parameter positions**: the count of distinct `getMethodParameter().getParameterIndex()` values in the list; this can be **smaller than the group count** when one parameter has multiple invalid `List`/`Map` elements.

In addition, `getCrossParameterValidationResults()` stores **cross-parameter errors separately**; do not fold them into "parameter group count" if your response field specifically means parameter groups.

## 2. Distinguishing method validation from single-argument validation

Spring MVC supports two common paths:

### 2.1. Validation of a single DTO

~~~java
@PostMapping("/accounts")
public AccountReply create(
        @Valid @RequestBody AccountRequest request) {
    return service.create(request);
}
~~~

When only `@Valid` appears on the body object and **no other direct constraint requires method validation**, DTO errors are typically thrown as **`MethodArgumentNotValidException`**. This exception carries a `BindingResult` for the request DTO, exposing `getFieldErrors()` and `getGlobalErrors()`.

`@Valid` itself is a marker requesting **cascaded validation**; it is not a direct constraint annotation like `@Min` or `@NotBlank`.

### 2.2. Method-level validation

~~~java
@PostMapping("/accounts")
public AccountReply create(
        @Valid @RequestBody AccountRequest request,
        @RequestParam("source")
        @Pattern(regexp = "web|mobile") String source) {
    return service.create(request);
}
~~~

`@Pattern` on `source` is a **direct constraint on a method parameter**. Spring MVC 6.1+ can apply **built-in method validation** to the handler, covering both direct constraints and cascading inside `@Valid AccountRequest`. On failure, `HandlerMethodValidationException` holds `ParameterValidationResult` entries, where a DTO with nested errors can be represented as `ParameterErrors`.

**Recommendation:** if you want MVC built-in method validation from Spring 6.1+, **do not put class-level `@Validated` on the controller**. That annotation can route method validation through a **Spring AOP proxy**, producing different exception types and behavior. Using Spring `@Validated` at the argument level when validation groups are needed is a separate case.

### 2.3. Type conversion errors before validation

~~~text
GET /api/quotes/not-a-number?limit=2
~~~

`@PathVariable long id` cannot accept the string `not-a-number`. The framework fails during **argument resolution/type conversion**, typically throwing `MethodArgumentTypeMismatchException`, before a `long id` exists for `@Min(1)` to check. Do not expect a `ParameterValidationResult` with `Min` for this input.

Similarly, syntactically invalid JSON raises `HttpMessageNotReadableException`. Distinguish **unreadable requests** from **readable requests that violate constraints**.

| Scenario | Typical processing path | Expected exception |
|---|---|---|
| Only `@Valid @RequestBody Dto` has invalid fields | Argument-level validation | `MethodArgumentNotValidException` |
| `@Min @RequestParam int limit`, value below min | Built-in MVC method validation | `HandlerMethodValidationException` |
| `@Pattern @RequestHeader String channel`, string fails pattern | Built-in MVC method validation | `HandlerMethodValidationException` |
| `@NotNull` on method return value returns `null` | Built-in return-value validation | `HandlerMethodValidationException`, HTTP 500 |
| `@RequestParam int limit`, sends `xyz` | Type conversion | `MethodArgumentTypeMismatchException` |
| Unparseable JSON | HTTP body decoding | `HttpMessageNotReadableException` |
| `@Validated` service bean invoked through AOP | Service method validation | Typically `ConstraintViolationException` by default |
| AOP with `adaptConstraintViolations` enabled | Adapted service method validation | `MethodValidationException` carrying `MethodValidationResult` |

This table reflects typical configurations. Custom `@ControllerAdvice`, global validators, proxies, and framework versions can alter behavior; when debugging, identify the **actual exception origin path**.

## 3. Reading `MethodValidationResult` and API versions

`MethodValidationResult` exposes:

~~~java
Object getTarget();
Method getMethod();
boolean isForReturnValue();
List<ParameterValidationResult> getParameterValidationResults();
List<MessageSourceResolvable>
    getCrossParameterValidationResults();
~~~

These are abbreviated Spring 6.2 signatures describing the API, not a class to copy into your project. The API also offers convenience methods:

- `getValueResults()` — groups with errors **directly on parameter values**.
- `getBeanResults()` — groups of type **`ParameterErrors`**, holding nested bean field/object errors.
- `getAllErrors()` — all errors as `MessageSourceResolvable` instances per the version's contract.
- `hasErrors()` — indicates whether the result contains any errors.
- `getParameterValidationResults()` — all value results and bean results per group.
- `getCrossParameterValidationResults()` — separate cross-parameter results.

**Important version milestone:** In **Spring Framework 6.2**, `getParameterValidationResults()` is the preferred API name. `getAllValidationResults()` may still exist but is **marked deprecated for removal**; avoid it in new code. When reading code running on Spring 6.1, check the matching Javadoc because the API evolved between 6.1 and 6.2.

In Spring MVC:

~~~java
HandlerMethodValidationException ex = /* caught exception */;

boolean returnFailure = ex.isForReturnValue();
int groupCount = ex.getParameterValidationResults().size();
int crossParameterErrorCount =
    ex.getCrossParameterValidationResults().size();
int httpStatus = ex.getStatusCode().value();
~~~

This is a **snippet inside an exception handler**, not a standalone Java method. `ex.getStatusCode()` returns:

- **400 Bad Request** for **input parameter** validation failures.
- **500 Internal Server Error** for **return-value** validation failures.

Reason: invalid input is a client fault, whereas a return value breaking its contract is a server fault. When designing error responses, never "coerce" every `HandlerMethodValidationException` to HTTP 400.

## 4. `ParameterValidationResult` APIs

This class exposes the following key details:

| API | Contents | Watch out |
|---|---|---|
| `getMethodParameter()` | `MethodParameter` describing the parameter or method return | Inspects index, Java type, and annotations |
| `getArgument()` | The validated Java value | **Never return directly** in APIs, as it may hold sensitive data |
| `getResolvableErrors()` | List of `MessageSourceResolvable` for the group | One group may hold multiple error entries |
| `getContainer()` | The enclosing container of the validated element, if any | Do not serialize into public JSON |
| `getContainerIndex()` | Element index in a `List`/array, if applicable | May be `null` for non-container parameters |
| `getContainerKey()` | Element key in a `Map`, if applicable | May hold private input; filter before returning |
| `unwrap(...)` | Accesses underlying validation metadata when available | Use only when genuinely needed; depends on provider/contract |

Example reading group metadata:

~~~java
for (ParameterValidationResult result
        : ex.getParameterValidationResults()) {

    MethodParameter methodParameter =
        result.getMethodParameter();

    int javaParameterIndex =
        methodParameter.getParameterIndex();

    int errorsInGroup =
        result.getResolvableErrors().size();

    Integer elementIndex =
        result.getContainerIndex();

    Object elementKey =
        result.getContainerKey();
}
~~~

This is an **illustrative snippet where `ex` is in scope**, requiring imports for `ParameterValidationResult` and `MethodParameter`. Never log `result.getArgument()` or `result.getContainer()` just for debugging; they can contain request DTOs, tokens, or large object graphs.

### `MethodParameter` and parameter names

`methodParameter.getParameterIndex()` returns the Java method parameter index; indices normally start at **0** following the signature order. For a return-value descriptor, the index represents the return slot (Spring `MethodParameter` uses **-1**). This is **Java metadata**, not an automatic index into a frontend JSON array.

`getParameterName()` is not always populated if bytecode lacks parameter metadata or no `ParameterNameDiscoverer` is active. For request-facing APIs, prefer explicit names in annotations:

~~~java
@RequestParam("limit")
@PathVariable("id")
@RequestHeader("X-Channel")
~~~

and controlled mappings, rather than relying entirely on compiler-retained Java variable names.

### Annotations determine input source

You can classify a method parameter via:

~~~java
if (methodParameter.hasParameterAnnotation(
        RequestParam.class)) {
    // QUERY or form parameter depending on contract
}
~~~

Similarly for `PathVariable.class`, `RequestHeader.class`, `RequestBody.class`, `ModelAttribute.class`. Each source type means something different to clients; do not label everything as `fieldErrors` of a body DTO.

## 5. Counting accurately: parameter groups vs. violation count

Consider three signatures:

### Case A — three independent parameters, each failing one constraint

~~~java
@GetMapping("/a/{id}")
public String a(
        @PathVariable @Min(1) long id,
        @RequestParam @Max(5) int limit,
        @RequestHeader("X-Channel")
        @Pattern(regexp = "web|mobile") String channel) {
    return "ok";
}
~~~

If all three fail, there are typically **three `ParameterValidationResult` groups**, each with one `MessageSourceResolvable`. Total groups = 3, total direct errors = 3, distinct Java parameter indices = 3.

### Case B — one parameter failing two constraints simultaneously

~~~java
@GetMapping("/b")
public String b(
        @RequestParam("code")
        @NotBlank
        @Size(min = 3) String code) {
    return "ok";
}
~~~

With `code=""`, both `@NotBlank` and `@Size(min=3)` can emit violations. The result is typically **one group** for `code` containing **two errors in `getResolvableErrors()`**. Do not assume the provider guarantees `NotBlank` precedes `Size`.

### Case C — one DTO with multiple invalid fields

~~~java
public record CreateQuote(
    @NotBlank String code,
    @Min(1) int quantity) {
}
~~~

If `code=""` and `quantity=0`, a `@Valid CreateQuote` in a handler using method validation can produce **one `ParameterErrors`** holding **two `FieldError`s**. `getParameterValidationResults().size()` increases by one group, while the DTO's field error count is two.

| Scenario | `ParameterValidationResult` groups | Errors in group | Notes |
|---|---:|---:|---|
| Three parameters, one error each | 3 | 1+1+1 | Distinct indices 0/1/2 |
| One parameter violating 2 annotations | 1 | 2 | One argument, two messages |
| One DTO with 2 field errors | 1 `ParameterErrors` | 2 | Nested field errors, not 2 parameters |
| One container with 2 invalid elements | Can be 2 | Per element | Same method index, different container index/key |
| One cross-parameter constraint violated | Can be 0 parameter groups | Errors in cross-parameter list | Not pinned to a single parameter |
| Invalid return value | Return-value group | 1 or more errors | HTTP 500, not input 400 |

**Do not name a JSON field `violationCount` if you pass `getParameterValidationResults().size()`.** Better names are `affectedGroups` or `parameterGroups`. If you need a total error count, sum across groups and add cross-parameter errors under an explicit policy.

## 6. `ParameterErrors`: nested errors in an object/DTO

`ParameterErrors` lives in:

~~~java
org.springframework.validation.method.ParameterErrors
~~~

This class **extends `ParameterValidationResult`** and **implements `org.springframework.validation.Errors`**. When a method argument is a bean validated via cascading `@Valid`, Spring can represent its nested errors through `ParameterErrors`.

Example:

~~~java
public record QuoteRequest(
    @NotBlank String code,
    @Min(1) int quantity) {
}

@PostMapping("/mixed")
public QuoteView mixed(
        @Valid @RequestBody QuoteRequest request,
        @RequestParam("source")
        @Pattern(regexp = "web|mobile") String source) {
    // ...
}
~~~

`@Pattern` is a direct method constraint, while `@Valid` validates nested properties of `request`. If the body is `{"code":"","quantity":0}` and `source` is `other`, you can get:

~~~text
HandlerMethodValidationException
|
+-- ParameterErrors: Java parameter #0 (QuoteRequest)
|      +-- FieldError("code", "NotBlank")
|      +-- FieldError("quantity", "Min")
|
+-- ParameterValidationResult: Java parameter #1 (source)
       +-- MessageSourceResolvable("Pattern")
~~~

That is **two groups**, yet **three errors**. Do not create a separate parameter group for every field of the DTO.

### `ParameterErrors`-specific APIs

Because it implements `Errors`, you can call:

~~~java
if (result instanceof ParameterErrors errors) {
    int all = errors.getErrorCount();
    int fields = errors.getFieldErrorCount();
    int globals = errors.getGlobalErrorCount();

    for (FieldError field : errors.getFieldErrors()) {
        String path = field.getField();
        String code = field.getCode();
    }

    for (ObjectError object : errors.getGlobalErrors()) {
        String code = object.getCode();
    }
}
~~~

This snippet sits inside a method with `ParameterValidationResult result` in scope. `FieldError extends ObjectError`, while `getGlobalErrors()` separates object-level errors from field errors.

**Never call `((ParameterErrors) result).getFieldErrors()` without a type check**: direct-constraint groups are normally plain `ParameterValidationResult` instances and do not implement `Errors`. Use `instanceof ParameterErrors`.

### Bean errors in `getResolvableErrors()`

`ParameterValidationResult.getResolvableErrors()` returns errors suitable for `MessageSource`. On the `ParameterErrors` subclass, this list corresponds to errors on the bean; if you need **field paths**, use the `Errors.getFieldErrors()` API. Therefore:

- Use `getResolvableErrors()` for group totals and messages.
- Use `ParameterErrors.getFieldErrors()` for field paths.
- Use `ParameterErrors.getGlobalErrors()` for object-level errors.

Never force the frontend to parse field names out of message strings; the structures above provide machine-readable data.

## 7. Containers: one Java parameter can produce multiple groups

`ParameterValidationResult`'s Javadoc highlights `@Valid` on multi-element containers such as:

~~~java
List<@Valid ItemDto> items
Map<String, @Valid ItemDto> itemsByKey
ItemDto[] items
~~~

This Java/Jakarta Validation syntax illustrates **method-parameter containers**, not three separate controller handler methods. When several elements fail, Spring can emit **one `ParameterValidationResult`/`ParameterErrors` per failing element**.

Example method (with method validation appropriately enabled):

~~~java
public void submit(
        @Valid List<ItemDto> items) {
    // ...
}
~~~

Suppose `items[0]` and `items[2]` fail; both results reference the **same Java method parameter** index 0, yet:

~~~text
ParameterErrors A
  parameterIndex = 0
  containerIndex = 0
  fieldErrors = ["sku"]

ParameterErrors B
  parameterIndex = 0
  containerIndex = 2
  fieldErrors = ["quantity"]
~~~

`getParameterValidationResults().size()` can be 2 even though the Java signature has only **one** argument. If code uses `Map<String, ItemDto>`, `getContainerKey()` can identify the element's key. `getContainerIndex()` only applies when an index makes sense; `Set` or unordered containers may not provide an index.

**Do not assume `@RequestBody List<@Valid ItemDto>` automatically produces these method-level results in every MVC configuration.** Whether this mechanism activates depends on resolvers and how method validation is triggered; the diagram explains the **shape of `ParameterValidationResult` when container results occur**.

### Building paths for the frontend

An API might represent this as:

~~~json
{
  "parameterIndex": 0,
  "source": "BODY",
  "containerIndex": 2,
  "fieldErrors": [
    {
      "field": "sku",
      "message": "SKU must not be blank"
    }
  ]
}
~~~

The frontend can display the error at `items[2].sku`, provided the contract specifies that the container is `items` and the index matches request order. Never naively construct paths by string concatenation across arbitrary `Map`/`Set` cases. Map keys can contain dots, brackets, or sensitive data; apply escaping, allowlisting, and security review before exposing them.

### Never serialize `getContainer()`

`getContainer()` can return the entire `List`/`Map` containing DTOs. Writing it straight to error JSON can leak request data and bloat responses. Expose only sanitized indices/paths, error codes, and safe messages.

## 8. Cross-parameter constraints do not belong to a single group

A constraint can validate the **relationship between multiple method arguments** rather than one individual argument. For instance, a method taking `startDate` and `endDate` where end must follow start.

Jakarta Validation supports **cross-parameter validation** (via `ConstraintValidator<A, Object[]>` and an appropriate validation target). When Spring adapts this result, `MethodValidationResult.getCrossParameterValidationResults()` exposes errors attached to the **parameter tuple/group**.

Example shape:

~~~text
MethodValidationResult
|
+-- parameterValidationResults = []
|
+-- crossParameterValidationResults
       +-- "endDate must be after startDate"
~~~

If the same request also violates a direct constraint, both lists can be non-empty simultaneously. Therefore, never write:

~~~java
int errors = ex.getParameterValidationResults().size();
~~~

to conclude **total errors equal 0** when a cross-parameter violation exists.

One way to count **adapted error entries** across both lists (not distinct fields):

~~~java
int parameterEntries = ex.getParameterValidationResults()
    .stream()
    .mapToInt(r -> r.getResolvableErrors().size())
    .sum();

int crossEntries =
    ex.getCrossParameterValidationResults().size();

int totalEntries = parameterEntries + crossEntries;
~~~

This is a snippet inside an exception handler. When designing the error contract, place cross-parameter errors in `crossParameterErrors[]` or a clearly scoped `objectErrors[]`; **never assign them arbitrarily to parameter #0**.

Do not confuse this with **class-level Bean Validation** on a DTO with two fields; that normally sits inside the DTO's `ParameterErrors` (as a bean global/object error), not as a method-wide Jakarta cross-parameter constraint.

## 9. Return-value validation: status 500 and the return descriptor group

Beyond inputs, Spring can also validate the **return value** of a controller method:

~~~java
@GetMapping("/api/broken")
@NotNull
public String broken() {
    return null;
}
~~~

When Spring MVC built-in method validation is active, the method runs and returns `null`, violating `@NotNull` on the return value. `HandlerMethodValidationException` reports:

~~~java
ex.isForReturnValue() == true
ex.getStatusCode().value() == 500
~~~

These are **illustrative value assertions**, not standalone Java statements.

**Why 500 instead of 400?** The client did not submit the return value; the server broke its own method contract. Never return a list of "request field errors" telling the client to fix input when the bug is on the server.

### Separating public responses from internal logs

For input failures, you can return parameter names, error kinds, and safe messages so the client can fix the request. For return-value failures:

- Keep HTTP **500**.
- Never expose internal method names, stack traces, object values, Java class names, or sensitive return data.
- Write server logs/tracing with a correlation ID at an appropriate level.
- Return a generic message such as `INTERNAL_CONTRACT_VIOLATION` if needed, never instructing the user to edit an input field when the fault is server-side.

If the method persisted DB changes before return validation failed, **do not** assume all side effects rolled back; that depends on transaction boundaries and commit timing.

### Return descriptor and index

`MethodParameter` uses convention **-1** for the method return type/descriptor; regular input parameters have indices 0, 1, 2... Never build a public API that makes clients look up a field named `-1`. When `isForReturnValue()` is true, emit a dedicated server-error response.

## 10. `HandlerMethodValidationException.Visitor`

When building distinct responses for query/path/header/body, Spring provides a visitor that classifies results by the annotation on the handler argument:

~~~java
ex.visitResults(
    new HandlerMethodValidationException.Visitor() {

        @Override
        public void requestParam(
                RequestParam annotation,
                ParameterValidationResult result) {
            // @RequestParam error.
        }

        @Override
        public void pathVariable(
                PathVariable annotation,
                ParameterValidationResult result) {
            // @PathVariable error.
        }

        @Override
        public void requestHeader(
                RequestHeader annotation,
                ParameterValidationResult result) {
            // @RequestHeader error.
        }

        @Override
        public void requestBody(
                RequestBody annotation,
                ParameterErrors errors) {
            // Can read getFieldErrors/getGlobalErrors.
        }

        @Override
        public void other(ParameterValidationResult result) {
            // Other argument types.
        }
    }
);
~~~

This is an **illustrative snippet inside a handler with `ex` in scope**, not a complete Java class. It requires imports for `HandlerMethodValidationException`, `ParameterValidationResult`, `ParameterErrors`, and web binding annotations. The interface also defines other callbacks such as `modelAttribute` and `requestPart`. Some annotations passed into callbacks can be `null` when Spring infers the argument kind without an explicit annotation; avoid blind dereferencing.

The visitor is useful when:

- You must distinguish `source = "QUERY"`, `"PATH"`, `"HEADER"`, `"BODY"`.
- Body/model-attribute DTOs need field errors, whereas primitive request params only need messages.
- You have many controller signatures and want annotation-driven dispatch.

If you only need to **group by Java parameter index**, a `for` loop over `getParameterValidationResults()` is simpler and easier to test. Do not use `Visitor` if every callback just duplicates the same line of code.

## 11. Designing parameter-grouped error JSON

A REST API might choose this illustrative schema:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedGroups": 3,
  "crossParameterErrorCount": 0,
  "groups": [
    {
      "parameterIndex": 0,
      "source": "PATH",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 1,
      "source": "QUERY",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 2,
      "source": "HEADER",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    }
  ]
}
~~~

This is a **contract defined by the example**, **not Spring Framework's default response**. In production, you can include error codes and localized messages, or use RFC 9457 `ProblemDetail` with extension properties.

Field explanations:

| Field | Meaning |
|---|---|
| `code` | Application-defined stable response code |
| `status` | HTTP status echoed in body; must match actual status |
| `returnValue` | Separates input validation from server return-value violations |
| `affectedGroups` | Number of `ParameterValidationResult` entries; **not equal to total violations** |
| `crossParameterErrorCount` | Count of separate cross-parameter errors |
| `groups[]` | List of result groups |
| `parameterIndex` | Java parameter position; **not a frontend field path** |
| `source` | Input source type (`PATH`/`QUERY`/`HEADER`/`BODY`/...) |
| `errorCount` | Number of `MessageSourceResolvable` items in the group |
| `fieldErrorCount` | For `ParameterErrors`, number of nested field errors |
| `globalErrorCount` | For `ParameterErrors`, number of nested object-level errors |
| `containerIndex` | Element index inside a container, if applicable |

**Two important lists omitted from this minimal schema** are field path messages and cross-parameter message details. The runnable sample favors a **stable counting and grouping schema** independent of translations/locales, while Section 13 shows how to upgrade it to include safe messages.

### Do not rely on group ordering unless contracted

Do not hardcode on the frontend that `groups[0]` is always `id` and `groups[1]` is always `limit` in every scenario. Even though Spring normally emits results in parameter order, with containers, multiple constraints, and version upgrades, the UI should match by `parameterIndex` and `source` rather than treating JSON array position as an identifier.

If snapshot tests or clients require deterministic ordering, **explicitly sort** results in the mapper by parameter index and container index with documented tie-breakers.

## 12. Complete Spring Boot 3.5 / Java 17+ program

The application demonstrates four scenarios:

1. `GET /api/quotes/{id}`: direct constraints on `@PathVariable`, `@RequestParam`, and `@RequestHeader`.
2. `POST /api/quotes/mixed`: `@Valid @RequestBody` DTO combined with `@Pattern` on `@RequestParam` to produce **`ParameterErrors` and `ParameterValidationResult`** in the same exception.
3. `POST /api/quotes/dto-only`: `@Valid` only on the DTO to compare against **`MethodArgumentNotValidException`**.
4. `GET /api/quotes/broken`: return-value `@NotNull` intentionally violated to test **HTTP 500**.

A `@RestControllerAdvice` overrides the built-in extension points in `ResponseEntityExceptionHandler`. There is no class-level `@Validated` on the controller; the goal is **built-in MVC method validation**, not AOP service validation.

All Java files live in package `com.example.paramgroups`, using **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17+**.

### 12.1. Gradle dependencies

In a Spring Boot project with the Boot Gradle plugin and dependency management configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-web` provides Servlet MVC; `spring-boot-starter-validation` provides the Jakarta Validation provider needed for constraints to run; the test starter provides JUnit and `MockMvc`. Do not compile with plain `javac` without the Spring/Boot classpath.

If using Spring Boot 4 / Spring Framework 7, re-check modules, dependencies, and APIs for that version before copying the template verbatim.

### 12.2. `ParameterGroupsApplication.java`

Create `src/main/java/com/example/paramgroups/ParameterGroupsApplication.java`:

~~~java
package com.example.paramgroups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParameterGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParameterGroupsApplication.class, args);
    }
}
~~~

### 12.3. `QuoteRequest.java`

Create `src/main/java/com/example/paramgroups/QuoteRequest.java`:

~~~java
package com.example.paramgroups;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record QuoteRequest(
    @NotBlank String code,
    @Min(1) int quantity
) {
}
~~~

Payload:

~~~json
{"code":"","quantity":0}
~~~

produces **two nested field errors** under Bean Validation, because empty `code` violates `@NotBlank` and `quantity` 0 violates `@Min(1)`. One object having multiple field errors does not mean multiple Java method parameters.

### 12.4. `QuoteController.java`

Create `src/main/java/com/example/paramgroups/QuoteController.java`:

~~~java
package com.example.paramgroups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping("/{id}")
    public QuoteView get(
            @PathVariable("id") @Min(1) long id,
            @RequestParam("limit")
            @Min(1) @Max(5) int limit,
            @RequestHeader("X-Channel")
            @Pattern(regexp = "web|mobile") String channel) {

        return new QuoteView(id, limit, channel);
    }

    @PostMapping("/mixed")
    public QuoteView mixed(
            @Valid @RequestBody QuoteRequest request,
            @RequestParam("source")
            @Pattern(regexp = "web|mobile") String source) {

        return new QuoteView(
            1, request.quantity(), source);
    }

    @PostMapping("/dto-only")
    public QuoteView dtoOnly(
            @Valid @RequestBody QuoteRequest request) {

        return new QuoteView(
            1, request.quantity(), "web");
    }

    @GetMapping("/broken")
    @NotNull
    public String broken() {
        return null; // Intentionally violates the return-value contract.
    }

    public record QuoteView(
        long id,
        int limit,
        String channel
    ) {
    }
}
~~~

Explanation:

- Constraints placed **directly** on `id`/`limit`/`channel` cause `get` to use built-in method validation.
- Method `mixed` has a `@Valid` DTO and a direct `@Pattern` constraint; nested DTO violations and the direct `source` violation are grouped together in `HandlerMethodValidationException`.
- Method `dtoOnly` has only the `@Valid` cascade marker on the body, with no direct constraints. On invalid DTOs, the normal path is `MethodArgumentNotValidException`.
- `broken` has return constraint `@NotNull`; returning `null` is a **500** server contract violation.
- **Do not** add class-level `@Validated`: doing so can switch validation to an AOP proxy instead of MVC built-in handler method validation.

### 12.5. `ValidationAdvice.java` — grouping errors into JSON

Create `src/main/java/com/example/paramgroups/ValidationAdvice.java`:

~~~java
package com.example.paramgroups;

import java.util.List;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ValidationAdvice
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<ParameterIssue> groups =
            ex.getParameterValidationResults()
                .stream()
                .map(this::toIssue)
                .toList();

        MethodProblem body = new MethodProblem(
            "METHOD_VALIDATION",
            status.value(),
            ex.isForReturnValue(),
            groups.size(),
            ex.getCrossParameterValidationResults().size(),
            groups
        );

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ArgumentProblem body = new ArgumentProblem(
            "ARGUMENT_VALIDATION",
            status.value(),
            ex.getBindingResult().getFieldErrorCount(),
            ex.getBindingResult().getGlobalErrorCount()
        );

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    private ParameterIssue toIssue(
            ParameterValidationResult result) {

        MethodParameter method =
            result.getMethodParameter();

        int fieldErrors = 0;
        int globalErrors = 0;

        if (result instanceof ParameterErrors nested) {
            fieldErrors = nested.getFieldErrorCount();
            globalErrors = nested.getGlobalErrorCount();
        }

        return new ParameterIssue(
            method.getParameterIndex(),
            location(method),
            result.getResolvableErrors().size(),
            fieldErrors,
            globalErrors,
            result.getContainerIndex()
        );
    }

    private String location(MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(
                PathVariable.class)) {
            return "PATH";
        }
        if (parameter.hasParameterAnnotation(
                RequestParam.class)) {
            return "QUERY";
        }
        if (parameter.hasParameterAnnotation(
                RequestHeader.class)) {
            return "HEADER";
        }
        if (parameter.hasParameterAnnotation(
                RequestBody.class)) {
            return "BODY";
        }
        if (parameter.hasParameterAnnotation(
                ModelAttribute.class)) {
            return "MODEL";
        }
        return "OTHER";
    }

    public record MethodProblem(
        String code,
        int status,
        boolean returnValue,
        int affectedGroups,
        int crossParameterErrorCount,
        List<ParameterIssue> groups
    ) {
    }

    public record ParameterIssue(
        int parameterIndex,
        String source,
        int errorCount,
        int fieldErrorCount,
        int globalErrorCount,
        Integer containerIndex
    ) {
    }

    public record ArgumentProblem(
        String code,
        int status,
        int fieldErrorCount,
        int globalErrorCount
    ) {
    }
}
~~~

**Design notes:**

1. The advice extends `ResponseEntityExceptionHandler`; the framework already supplies the central `@ExceptionHandler`. We **override protected hooks** instead of adding a duplicate `@ExceptionHandler(HandlerMethodValidationException.class)` in the same subclass.
2. `status.value()` is supplied by Spring: **400** on invalid input, **500** on invalid return value. Never hardcode 400 for every method validation exception.
3. `groups.size()` is **`affectedGroups`**; `result.getResolvableErrors().size()` is the number of errors inside that group.
4. For `ParameterErrors`, the code also reads `getFieldErrorCount()` and `getGlobalErrorCount()`, without casting plain `ParameterValidationResult` instances to `ParameterErrors`.
5. `getCrossParameterValidationResults().size()` is reported in its own field.
6. `getContainerIndex()` preserves index metadata when present; `containerKey` is omitted because it could contain sensitive data.
7. `location(...)` classifies by **annotations**, not `getParameterName()` (which may lack compiler metadata).
8. The advice never exposes `result.getArgument()`, `result.getContainer()`, rejected values, internal method names, or Java stack traces.
9. The response body is application-designed to **test grouping**. It is not standard `ProblemDetail`; upgrading is discussed in Section 14.

**Example limitation:** It returns only **counts and group metadata**, without user-facing messages. Production APIs need localized messages/codes and proper field path mappings; an extension pattern is shown in Section 13.

### 12.6. Running the demo

From the Spring Boot project root with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Assume the app listens on the default port 8080.

Valid request:

~~~bash
curl -i "http://localhost:8080/api/quotes/10?limit=2" \
  -H "X-Channel: web"
~~~

Expected HTTP **200 OK**:

~~~json
{
  "id": 10,
  "limit": 2,
  "channel": "web"
}
~~~

Request with **three invalid parameters**:

~~~bash
curl -i "http://localhost:8080/api/quotes/0?limit=9" \
  -H "X-Channel: other"
~~~

Expected HTTP **400 Bad Request** and JSON containing three groups, for example:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedGroups": 3,
  "crossParameterErrorCount": 0,
  "groups": [
    {
      "parameterIndex": 0,
      "source": "PATH",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 1,
      "source": "QUERY",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 2,
      "source": "HEADER",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    }
  ]
}
~~~

This reflects one group per parameter. **Do not treat element order in JSON arrays as an API identifier** when real code uses different sorting or container groups.

Request where both a DTO and a direct constraint fail:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/quotes/mixed?source=other" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Expected HTTP **400** with `code="METHOD_VALIDATION"`, typically containing **two affected groups**:

- Group for parameter index 0, `source="BODY"`, subtype `ParameterErrors` with **2 field errors** (`code` and `quantity`).
- Group for parameter index 1, `source="QUERY"`, with **1 direct violation** (`Pattern`).

**Total groups is 2; total errors across both groups is 3.** `affectedGroups` cannot be used as the total error count.

Compare with DTO-only:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/quotes/dto-only" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Expected HTTP **400** with:

~~~json
{
  "code": "ARGUMENT_VALIDATION",
  "status": 400,
  "fieldErrorCount": 2,
  "globalErrorCount": 0
}
~~~

Finally, return-value constraint:

~~~bash
curl -i "http://localhost:8080/api/quotes/broken"
~~~

Expected HTTP **500 Internal Server Error**, `code="METHOD_VALIDATION"`, and `returnValue=true`. Never log this as a query-parameter error since the request had no invalid input; the server returned a value violating `@NotNull`.

## 13. Adding message codes, localization, and field paths

The response in Section 12 is useful for **learning grouping**, though real frontends typically need to know what each error says. `ParameterValidationResult.getResolvableErrors()` already converts errors into `MessageSourceResolvable`, translatable via:

~~~java
String message = messageSource.getMessage(
    resolvable, locale);
~~~

Example in a mapper with `MessageSource messageSource` and `Locale locale`:

~~~java
List<String> messages =
    result.getResolvableErrors()
        .stream()
        .map(error -> messageSource.getMessage(
            error, locale))
        .toList();
~~~

This is a snippet inside a method with `result` in scope. In Spring MVC, `Locale` can come from the request context, such as `LocaleContextHolder.getLocale()` in an exception handler, or from a `Locale locale` controller parameter when handled inline.

### Direct constraint message codes

Spring can generate codes from the annotation, method, and parameter name/type, e.g., for `@Max`:

~~~text
Max.myObject#myMethod.myParameter
Max.myParameter
Max.int
Max
~~~

That is an **illustrative Javadoc example**; exact application codes depend on object/method/parameter metadata. Never hardcode method signature names or rely on English-interpolated messages to classify errors.

### DTO errors with `ParameterErrors`

When `result instanceof ParameterErrors nested`:

~~~java
List<String> fieldPaths = nested.getFieldErrors()
    .stream()
    .map(FieldError::getField)
    .toList();

List<String> objectCodes = nested.getGlobalErrors()
    .stream()
    .map(ObjectError::getCode)
    .toList();
~~~

If multiple errors can occur on the same field, keep a **list** rather than a `Map<String,String>` holding only one message per key. Keep object-level errors in their own scope; do not assign a synthetic field like `"_global"` unless the public contract explicitly adopts that convention.

### Separating messages from business codes

You can emit:

~~~json
{
  "parameterIndex": 0,
  "source": "BODY",
  "fields": [
    {
      "field": "code",
      "code": "NotBlank",
      "message": "Quote code must not be blank."
    },
    {
      "field": "quantity",
      "code": "Min",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

This is an **application-defined JSON extension**. `FieldError.getCode()` values like `NotBlank`/`Min` are helpful while learning, though production APIs often map them to more stable codes (`REQUIRED_FIELD`, `VALUE_BELOW_MIN`) so clients are decoupled from Jakarta constraint names.

### Never leak input values when localizing messages

`result.getArgument()`, `FieldError.getRejectedValue()`, and annotation arguments may inadvertently contain sensitive data. If a message template includes placeholders referencing rejected values, audit translations before exposing them in public responses. Log only minimal needed details plus a correlation ID; never log full bodies or tokens.

## 14. `ProblemDetail` and standard error response design

`HandlerMethodValidationException` implements `ErrorResponse` and provides `ProblemDetail` support; `ResponseEntityExceptionHandler` supports **RFC 9457 Problem Details**.

A response can be built on `ProblemDetail`:

~~~java
ProblemDetail body =
    ProblemDetail.forStatus(ex.getStatusCode());

body.setTitle(
    ex.isForReturnValue()
        ? "Server contract violation"
        : "Invalid request parameters");

body.setProperty(
    "code",
    ex.isForReturnValue()
        ? "INTERNAL_CONTRACT_ERROR"
        : "METHOD_VALIDATION");

if (!ex.isForReturnValue()) {
    body.setProperty("parameterGroups", groups);
}
~~~

This is an illustrative snippet inside an exception handler where `groups` has been safely mapped. For return-value errors, never return raw details or parameter values to clients.

In Spring MVC, `ResponseEntityExceptionHandler.handleHandlerMethodValidationException(...)` is a protected extension point. It already integrates `MessageSource`, `ErrorResponse`, and `ProblemDetail`, so if you want RFC 9457 compliance, you can **extend the default `ProblemDetail`** instead of designing a completely custom JSON schema from scratch.

**Never register duplicate handlers.** When subclassing `ResponseEntityExceptionHandler`, override `handleHandlerMethodValidationException(...)`; do not add `@ExceptionHandler(HandlerMethodValidationException.class)` in the same subclass when the base class already handles that type.

### Should you return grouped or flattened errors?

Both have valid uses:

- **Grouped representation** preserves method parameter context, nested fields, and container indices—ideal for UIs with multiple input sources and analytics/debugging.
- **Flattened representation** such as `errors:[{source,path,code,message}]` is easy for many frontends to consume, but requires careful mapping so object-level/cross-parameter context is not lost.

A clean design can provide `parameterGroups[]` or a normalized error list derived from those groups, avoiding two conflicting representations. Mapper unit tests should verify totals and error kinds are not double-counted when flattening.

## 15. `BindingResult` and local error handling rules

Spring MVC allows `Errors`/`BindingResult` immediately after an object method argument so the controller can handle validation errors inline, yet when **method validation** applies:

- If **all** errors belong to parameters that have a matching `Errors`/`BindingResult` right after them, the handler can still be invoked to process them.
- If an error occurs on **another parameter** lacking an `Errors` argument, Spring can throw `HandlerMethodValidationException` and skip invoking the handler.

Illustrative **snippet**:

~~~java
@PostMapping("/preview")
public String preview(
        @Valid @ModelAttribute("form") PreviewForm form,
        BindingResult errors,
        @RequestParam("count") @Min(1) int count) {

    if (errors.hasErrors()) {
        return "preview-form";
    }
    return "preview-ok";
}
~~~

`BindingResult` stands **immediately after `form`** and covers only errors for that form. If `form` is invalid while `count=2` is valid, the method can handle the form errors. If `count=0`, the direct `@Min(1)` constraint on `count` fails; `form`'s `BindingResult` does **not** capture `count`'s error, and the framework can throw `HandlerMethodValidationException`.

This explains why a project using `@Valid` and `BindingResult` can still throw an exception once `@RequestParam @Min` is added to the handler signature. Inspect the **entire method signature**, not just the DTO.

## 16. Testing with `MockMvc`

To verify that `ParameterValidationResult` is actually produced by the Spring MVC pipeline, test through Spring MVC rather than calling `new QuoteController().get(...)` directly. Direct Java calls bypass argument resolvers, Jakarta Validator, `HandlerMethodValidator`, and exception advice.

Create `src/test/java/com/example/paramgroups/ParameterGroupsMvcTest.java`:

~~~java
package com.example.paramgroups;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterGroupsMvcTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validDirectConstraintsPass() throws Exception {
        mvc.perform(get("/api/quotes/10")
                .param("limit", "2")
                .header("X-Channel", "web"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(10))
            .andExpect(jsonPath("$.limit").value(2))
            .andExpect(jsonPath("$.channel").value("web"));
    }

    @Test
    void threeInvalidArgumentsCreateThreeGroups()
            throws Exception {

        mvc.perform(get("/api/quotes/0")
                .param("limit", "9")
                .header("X-Channel", "other"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedGroups")
                .value(3))
            .andExpect(jsonPath("$.returnValue")
                .value(false))
            .andExpect(result -> {
                HandlerMethodValidationException ex =
                    assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());

                assertTrue(
                    ex.getParameterValidationResults()
                        .stream()
                        .allMatch(r ->
                            r.getResolvableErrors().size() == 1));
            });
    }

    @Test
    void nestedDtoAndDirectParamAreTwoGroups()
            throws Exception {

        mvc.perform(post("/api/quotes/mixed")
                .param("source", "other")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedGroups")
                .value(2))
            .andExpect(result -> {
                HandlerMethodValidationException ex =
                    assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());

                assertTrue(
                    ex.getParameterValidationResults()
                        .stream()
                        .anyMatch(r ->
                            r instanceof ParameterErrors nested
                            && nested.getFieldErrorCount() == 2));
            });
    }

    @Test
    void dtoOnlyUsesArgumentLevelValidation()
            throws Exception {

        mvc.perform(post("/api/quotes/dto-only")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ARGUMENT_VALIDATION"))
            .andExpect(jsonPath("$.fieldErrorCount")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                MethodArgumentNotValidException.class,
                result.getResolvedException()));
    }

    @Test
    void invalidReturnValueKeepsHttp500()
            throws Exception {

        mvc.perform(get("/api/quotes/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.returnValue")
                .value(true))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void typeMismatchIsNotMinViolation()
            throws Exception {

        mvc.perform(get("/api/quotes/not-a-number")
                .param("limit", "2")
                .header("X-Channel", "web"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredHeaderIsResolutionError()
            throws Exception {

        mvc.perform(get("/api/quotes/10")
                .param("limit", "2"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validMixedDtoPasses() throws Exception {

        mvc.perform(post("/api/quotes/mixed")
                .param("source", "mobile")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"ABC\",\"quantity\":2}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.limit").value(2))
            .andExpect(jsonPath("$.channel").value("mobile"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Under Spring Boot 3.5 + Spring Framework 6.2 with Web + Validation starters, no class-level `@Validated` on the controller, and no other custom advice/proxies, **all 8 tests are expected to PASS**. This is the expected outcome from the sample code, **not a claim that Gradle was executed**.

The tests do not rely solely on JSON shape. They verify the **actual exception classes**:

- `HandlerMethodValidationException` for direct method constraints.
- `ParameterErrors` when nested DTO errors occur inside method-level validation.
- `MethodArgumentNotValidException` for DTO-only validation.
- Return-value errors preserving HTTP 500.
- Type mismatch and missing header returning 400 without being misclassified as direct constraint violations.

Do not assert that the violation order inside `getResolvableErrors()` is fixed across providers. Tests check only essential counts and structure. In projects with Spring Security, POST tests may require CSRF/mock authentication setup.

## 17. Pattern for inspecting total errors and groups in real code

You can compute metrics inside an exception handler:

~~~java
List<ParameterValidationResult> results =
    ex.getParameterValidationResults();

int groups = results.size();

long distinctJavaPositions = results.stream()
    .map(r -> r.getMethodParameter().getParameterIndex())
    .distinct()
    .count();

int adaptedErrors = results.stream()
    .mapToInt(r -> r.getResolvableErrors().size())
    .sum();

int crossParameterErrors =
    ex.getCrossParameterValidationResults().size();
~~~

This is a snippet in scope with `ex`. These metrics are **not a single number** and should not be renamed arbitrarily:

- `groups` is the number of parameter/element groups recorded.
- `distinctJavaPositions` is the count of distinct method parameter positions; for return validation it means something else, so separate before reporting.
- `adaptedErrors` is the sum of error entries across groups.
- `crossParameterErrors` is the count of errors not attributable to a single parameter.
- Total entries across both lists is `adaptedErrors + crossParameterErrors`, which does not equal the count of distinct input fields.

### Which metrics should be logged?

For observability, log **status**, error code, group count, and input source type; avoid logging argument values and container keys. Add constraint/method names, request ID, and route templates only for controlled internal diagnostics.

### Should method parameter indices be exposed in public APIs?

Indices are useful for debugging and unit tests, but they are implementation details. If a method signature refactor inserts a parameter before `limit`, `parameterIndex` shifts. For long-lived public APIs, map to published identifiers such as:

~~~text
PATH:id
QUERY:limit
HEADER:X-Channel
BODY:quote.code
BODY:quote.quantity
~~~

and keep that mapping in one unified layer so the frontend never depends on Java method parameter ordering.

## 18. Notes on validation groups and AOP service validation

### Validation groups

Jakarta Validation supports constraint groups. You can use `@Validated(SomeGroup.class)` on a DTO argument in Spring or configure corresponding group behavior in method validation. When a group excludes a constraint, never assume every annotation on the object was evaluated.

`ParameterValidationResult` reflects only errors emitted after the validator runs with the selected groups. Never infer from zero errors that an object is valid across **all** groups.

### AOP method validation on services

Example:

~~~java
@Service
@Validated
public class QuoteService {

    public void approve(@NotBlank String code) {
        // ...
    }
}
~~~

This is an illustrative snippet requiring imports and a Spring bean/proxy. `MethodValidationPostProcessor`/`MethodValidationInterceptor` can enforce constraints when a method is invoked **through a Spring AOP proxy**. By default, the exception is typically Jakarta's `ConstraintViolationException`. When `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` is enabled, Spring can throw `MethodValidationException` carrying `MethodValidationResult` and `ParameterValidationResult`s.

Thus, **`ParameterValidationResult` is not exclusive to Spring MVC**. It is Spring's general method-validation model used both for MVC handler errors and adapted service method validation. However, the HTTP-aware `HandlerMethodValidationException` and its 400/500 status belong specifically to the web handler pipeline.

**Never cast every `ConstraintViolationException` to `HandlerMethodValidationException`.** Service AOP, proxy self-invocation, controller `@Validated`, and validation groups can take different paths. Design error boundaries per layer.

## 19. Handling edge cases in error responses

### No direct constraints, only `@Valid`

A DTO-only `@Valid @RequestBody` typically uses `MethodArgumentNotValidException`. If your error handler only overrides `handleHandlerMethodValidationException`, you still need to handle that path to keep responses uniform.

### Direct constraints alongside a `@Valid` DTO

When built-in method validation applies, DTO errors can surface as `ParameterErrors` inside the same groups list as direct parameter errors. Avoid validating twice and double-counting errors.

### `BindingResult` immediately after an argument

Spring MVC only invokes the handler for inline error handling if **all** errors belong to parameters that have a corresponding `Errors` argument. If any other parameter fails, `HandlerMethodValidationException` can still be raised.

### Container Map keys and indices

`getContainerKey()` can hold untrusted keys from the request, possibly sensitive ones. Never put raw keys into public responses, logs, or JSON paths without escaping and allowlisting. `Set` normally lacks stable indices like `List`.

### Cross-parameter errors

These are not in `getParameterValidationResults()`; always inspect `getCrossParameterValidationResults()` if your application uses multi-parameter constraints. Avoid pinning a cross-parameter error to a single field if the constraint does not identify one.

### Return-value validation

`isForReturnValue()` and HTTP 500 carry different operational meaning from input violations. Never expose raw return values or parameter data to "help clients debug".

### `MessageSource` and locale

`MessageSourceResolvable` carries fallback codes and a default message; method parameter names may depend on compiler metadata. Never rely on message text to determine stable machine codes. Never depend by default on a validation provider's built-in English or Vietnamese strings across all locales.

### JSON responses and `ProblemDetail`

The example uses custom JSON records; Spring provides RFC 9457 `ProblemDetail`. If your application wants a shared standard alongside domain errors, document one schema clearly. Do not claim `application/problem+json` compliance for a custom record that does not actually follow `ProblemDetail`.

## 20. Common implementation mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `affectedGroups=1` yet DTO has 2 field errors | One `ParameterErrors` holds multiple `FieldError`s | Count nested errors separately |
| `affectedGroups=2` yet only one Java parameter failed | Two container elements belong to the same method parameter | Check `getContainerIndex()/getContainerKey()` |
| API misses cross-parameter errors | Iterating only `getParameterValidationResults()` | Read `getCrossParameterValidationResults()` separately |
| `ClassCastException` casting result to `ParameterErrors` | Direct-constraint groups do not implement `Errors` | Use `instanceof ParameterErrors` |
| No `ParameterValidationResult` for DTO-only endpoint | Argument-level validation, not method-level | Handle `MethodArgumentNotValidException` |
| `limit=abc` has no `Min` violation | Type conversion failed first | Handle type mismatch separately |
| Validation HTTP 500 forced to 400 by advice | Violates return-value contract | Respect `isForReturnValue()/getStatusCode()` |
| Controller with class-level `@Validated` throws a different exception | AOP proxy method validation | Remove class-level `@Validated` if built-in MVC 6.1+ is desired |
| Calling `getAllValidationResults()` in 6.2 | API deprecated for removal | Use `getParameterValidationResults()` |
| Messages not translated for locale | Using `getDefaultMessage()` instead of `MessageSource` | Resolve `MessageSourceResolvable` |
| API leaks rejected password/token | Serializing `getArgument()/getContainer()` | Map only safe fields |
| Parameter name is null in JSON | Bytecode lacks parameter name metadata | Use explicit annotation names or a stable fallback |
| Field path does not match frontend | Nested/collection DTO naming differs from client | Define a tested mapping |
| Visitor skips expected callback | Implicit annotation or different argument type | Implement `other` fallback; check visitor contract |
| Unit test calling Java method directly throws no exception | Bypasses Spring MVC handler validation | Use `MockMvc`/HTTP integration tests |
| Adding `@NotBlank` on `@RequestParam` changes DTO exception type | Triggers method validation | Handle both paths |
| `@Valid` error on container has no index | Unindexed container or different mechanism | Inspect actual metadata; do not fabricate indices |
| GET missing required header produces a different 400 | Argument resolution failure before method validation | Do not confuse with `Pattern` violations |
| API always returns only `fieldErrors` | Drops direct parameter and cross-parameter errors | Design groups + scope |
| All errors expose raw internal code names | Lacks i18n/error-code mapping | Use `MessageSource` and stable public codes |

### Debugging checklist

1. Is the app running Spring MVC 6.1+, WebFlux, or AOP service validation?
2. Does the handler have direct constraints like `@Min`/`@Pattern`, or only `@Valid` on a DTO?
3. Did argument resolution and type conversion succeed?
4. Is the actual exception `HandlerMethodValidationException`, `MethodArgumentNotValidException`, or another type?
5. Is `isForReturnValue()` true or false? Is the HTTP status preserved?
6. What is `getParameterValidationResults().size()`?
7. Are there `ParameterErrors` entries in the list? What are the nested field/object errors?
8. Are container indices/keys causing the same Java index to appear multiple times?
9. Are there any cross-parameter errors?
10. Does the mapper expose sensitive data or drop field errors?
11. Do `@ControllerAdvice` and overrides collide on `@ExceptionHandler` mappings?
12. Do `MockMvc` tests assert both exception classes and response schemas?

## 21. Self-study questions

**1. What question does `ParameterValidationResult` answer?**

It identifies **which method parameter or container element** failed and provides its `MessageSourceResolvable` errors along with parameter/argument/container metadata.

**2. Does one argument violating two annotations always create two groups?**

No. It can produce **one `ParameterValidationResult` containing two errors**.

**3. How does `ParameterErrors` differ from `ParameterValidationResult`?**

`ParameterErrors` is a subclass implementing **`Errors`**, letting you read `getFieldErrors()` and `getGlobalErrors()` from a cascade-validated bean.

**4. Is `getParameterValidationResults().size()` the number of invalid fields?**

No. It is the number of result groups; one DTO group can contain multiple field errors, and one container can produce multiple groups for the same Java parameter.

**5. With a `List` having two invalid elements, can two results share the same `getParameterIndex()`?**

Yes, differing by `getContainerIndex()`; that is why `groupCount` can exceed the number of distinct Java parameter indices.

**6. Where does a cross-parameter violation live?**

In `getCrossParameterValidationResults()`, not inside a single argument's `ParameterValidationResult`.

**7. What is the HTTP status for a return-value validation failure in `HandlerMethodValidationException`?**

HTTP **500**, with `isForReturnValue()==true`, because the server broke the return-value contract.

**8. Which exception is typically thrown for a failing DTO-only `@Valid @RequestBody`?**

`MethodArgumentNotValidException` when no other direct method constraint triggers built-in method validation.

**9. Why should `result.getArgument()` not be returned through an API?**

It can contain personal data, passwords, tokens, or large object graphs; mappers should extract only safe codes, locations, and messages.

**10. In Spring 6.2, should you use `getAllValidationResults()` or `getParameterValidationResults()`?**

Use `getParameterValidationResults()`; `getAllValidationResults()` is marked deprecated for removal.

**11. Why does `MethodArgumentTypeMismatchException` not emit an `@Min` error for `id=abc`?**

Because the input never converted to a valid Java type, so the numeric constraint could not be evaluated.

**12. How should grouping behavior be tested?**

Send requests through `MockMvc`, asserting `HandlerMethodValidationException`, group count, `ParameterErrors` subtype, and HTTP status/body—never just direct Java method calls.

## 22. Implementation checklist

- [ ] Pick the right Spring Framework version and web stack; understand built-in MVC 6.1+ vs. service AOP.
- [ ] Use `getParameterValidationResults()` on Spring 6.2, avoiding deprecated APIs.
- [ ] Count groupCount, per-group errorCount, and distinct Java parameter indices separately.
- [ ] When `result instanceof ParameterErrors`, read both nested field and global errors.
- [ ] Never cast every result to `ParameterErrors`.
- [ ] For containers, inspect index/key when available; never assume each Java parameter yields only one group.
- [ ] Read `getCrossParameterValidationResults()` when cross-parameter constraints exist.
- [ ] Keep 500 return-value errors separate from 400 input errors.
- [ ] Handle DTO-only `MethodArgumentNotValidException` and type-conversion errors separately.
- [ ] Omit class-level `@Validated` on controllers when built-in MVC method validation is desired.
- [ ] Consider `Visitor` when responses need to distinguish annotations/sources.
- [ ] When using `MessageSource`, resolve `MessageSourceResolvable` per locale and keep API codes stable.
- [ ] Never expose `getArgument()`, raw containers/keys, rejected values, or stack traces.
- [ ] Allow multiple nested errors within one group and multiple groups for the same container parameter.
- [ ] Never depend on group/violation ordering unless contracted; sort explicitly when needed.
- [ ] Use `ResponseEntityExceptionHandler` hook overrides to avoid duplicate exception mappings.
- [ ] Use `ProblemDetail` when RFC 9457 is needed; never label a custom record as standard `ProblemDetail`.
- [ ] Test valid requests, three failing direct constraints, mixed nested+direct, DTO-only, 500 return-value, and type mismatch.
- [ ] When upgrading Boot/Spring, re-verify Javadocs and tests before changing exception mappers.

**Remember:** `ParameterValidationResult` is the **error-grouping unit** of Spring method validation, **not the unit of a single constraint**. Direct errors appear as `MessageSourceResolvable` items; nested DTO errors appear via `ParameterErrors` with `FieldError`/`ObjectError`. Container elements and cross-parameter violations require extra care when counting and displaying. When designing APIs, keep **source, parameter index/path, groups, error counts, HTTP status, and i18n** structured, while never exposing argument values.

## Official references

- [Spring Framework 6.2 — MethodValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/MethodValidationResult.html)
- [Spring Framework 6.2 — ParameterValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — ParameterErrors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html)
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — HandlerMethodValidationException.Visitor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.Visitor.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
