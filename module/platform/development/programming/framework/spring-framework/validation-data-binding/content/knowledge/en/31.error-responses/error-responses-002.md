# Keeping Error Codes, Paths, Parameters, and Messages Essential in Spring Validation Responses

## 1. The problem: returning HTTP 400 alone is not enough for the client to fix the right field

Suppose a user submits an order with two line items:

~~~json
{
  "customerName": "",
  "items": [
    {"sku": "PEN", "quantity": 0},
    {"sku": "", "quantity": 2}
  ]
}
~~~

If the API only returns:

~~~json
{"error": "Validation failed"}
~~~

the frontend does not know which field failed, which line item it belongs to, what threshold is required, or what message to show. On the other hand, if the backend returns raw `exception.getMessage()` or `exception.toString()`, it risks exposing class names, method names, rejected user values, and internal details; moreover, the error string is hard to keep stable when upgrading Spring or the Jakarta provider.

A more useful response:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Fix the listed fields.",
  "code": "REQUEST_VALIDATION_FAILED",
  "issues": [
    {
      "code": "NotBlank",
      "path": "customerName",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {},
      "message": "Customer name is required"
    },
    {
      "code": "Min",
      "path": "items[0].quantity",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {"minimum": 1},
      "message": "Quantity must be at least 1"
    },
    {
      "code": "NotBlank",
      "path": "items[1].sku",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {},
      "message": "SKU is required"
    }
  ]
}
~~~

In this example:

- **`code` at the response level** is a stable business code for the request failure category: `REQUEST_VALIDATION_FAILED`.
- **`issues[*].code`** is the specific error code (`NotBlank`, `Min`, `typeMismatch`…). Clients use it for branching, analytics, and multi-language support.
- **`path`** preserves the property/index path: `items[0].quantity` identifies line item index 0 accurately.
- **`location`** indicates where the input came from (`body`, `form`, `query`, `header`, …), avoiding ambiguity between same-named fields from different sources.
- **`parameterIndex`** identifies the parameter position in the handler method signature, useful with method validation.
- **`parameters`** holds essential public constraint attributes, such as `minimum=1`, so the UI can display the rule.
- **`message`** is human-readable text resolved for the target locale; clients **should not rely on message text to make logic decisions**.

That is the core focus of this lesson: **keep enough information for the client to act, without exposing raw exception objects**. The example uses **Problem Details / RFC 9457** with custom extension fields `code` and `issues`. This is an application-designed API contract, not fields (`issues`, `location`, `parameters`) that Spring generates by default.

This lesson uses **Java 17**, **Spring Boot 3.5.7 / Spring Framework 6.2**, the `jakarta.validation.*` namespace, and a **Spring MVC** demo. The metadata principles also apply to WebFlux, though exception binding and HTTP lifecycle differences are noted separately.

## 2. Six pieces of data in a validation issue

### 2.1. Stable error code

An error code must represent the **violation category**, not the entire message sentence.

Examples:

| Common source code | Meaning | How the client uses it |
| --- | --- | --- |
| `NotBlank` | String cannot be null/empty/whitespace-only | Mark the input as required |
| `NotNull` | Value is required | Require a non-null value |
| `NotEmpty` | Collection/string cannot be empty | Require at least one item |
| `Min` | Value must be at or above a threshold | Display the `minimum` threshold |
| `Size` | Length/size within bounds | Display `minLength`/`maxLength` when public |
| `typeMismatch` | Type conversion during binding failed | Prompt for valid format |
| `INVALID_VALUE` | Application-defined fallback | Display generic error without leaking internals |

In Spring, `FieldError#getCode()` typically returns a general code like `NotBlank` or `typeMismatch`. `FieldError#getCodes()` returns **a list of codes at varying specificity**, such as `NotBlank.orderForm.customerName`, `NotBlank.customerName`, `NotBlank.java.lang.String`, `NotBlank` (exact list depends on the resolver). Do not expose the entire list in a public API: it can leak class names, object names, or internal details.

A solid strategy: **deliberately whitelist source codes** and normalize them into a public contract; if unrecognized, return `INVALID_VALUE`. If your application has custom codes like `inventory.insufficient`, register them in a public mapping table and write stability tests instead of passing arbitrary internal codes straight to clients.

### 2.2. Path (`path`)

`path` identifies **the target object and error location**:

~~~text
customerName
shippingAddress.city
items[0].quantity
items[1].sku
labels[priority]
contacts[support].email
~~~

`FieldError#getField()` holds the exact `BindingResult` field path. For lists/arrays, indices in `[0]`, `[1]` matter; for maps, keys in `[priority]` can matter. **Do not strip indices** or keep only the leaf such as `quantity`, because the frontend will not know which row needs fixing.

Distinguish between:

- **Field error**: has a specific property path.
- **Object/global error**: applies to the whole object or cross-field relationships, and may have no single field path. The API should allow `path=""` or `path=null` per an agreed contract, paired with an object-level code.
- **Method parameter error**: has the request argument name or parameter index.
- **Cross-parameter error**: involves multiple arguments at once and should not be arbitrarily pinned to a single field.

A path like `items[0].quantity` uses Spring property path syntax; it is **not** a JSON Pointer `/items/0/quantity`. If the frontend requires JSON Pointer, the backend needs a tested path converter (handling dots, map keys, and escaping), rather than naively replacing brackets with slashes.

### 2.3. Source location (`location`)

`path="id"` could refer to a query parameter, path variable, or JSON body field. Add `location`:

~~~json
{"location":"query","path":"id"}
~~~

Or:

~~~json
{"location":"body","path":"id"}
~~~

Do not use Spring class names such as `RequestParamMethodArgumentResolver` as public locations; clients only need a stable vocabulary such as `query`, `path`, `header`, `body`, `form`, `crossParameter`.

### 2.4. Method parameter index

When Spring MVC 6.1+ method validation is triggered by `@Min` or `@NotBlank` directly on a parameter, `HandlerMethodValidationException#getParameterValidationResults()` groups errors by `MethodParameter`.

From that you get:

~~~java
int index = result.getMethodParameter().getParameterIndex();
~~~

This is the **zero-based index in the Java handler method**, not the HTML form input order. You can include `parameterIndex` for debugging or mapping in clients with a fixed contract. However, when a controller is refactored or parameters are added, the index changes; for a **stable public name**, prefer declaring `@RequestParam(name="units")` explicitly and using `units` as `path`.

### 2.5. Constraint parameters

For example, `@Min(1)` has attribute `value=1`; `@Size(min=2,max=20)` has `min=2, max=20`. This metadata helps clients render UI hints:

~~~json
{
  "code": "Min",
  "path": "items[0].quantity",
  "parameters": {"minimum": 1}
}
~~~

Jakarta `ConstraintViolation#getConstraintDescriptor().getAttributes()` contains **a lot of information**: `message`, `groups`, `payload`, and other custom attributes. **Do not serialize the entire attributes map**. Whitelist what the client should know, such as `minimum`, `minLength`, `maxLength`. For custom constraints holding sensitive metadata (policy identifiers, secret regexes, tenant limits), never expose attributes wholesale.

### 2.6. Localized message

`message` is the user-facing prompt:

~~~text
vi: Số lượng phải từ 1 trở lên
en: Quantity must be at least 1
~~~

Do not force clients to parse phrases like `"phải từ"` or `"at least"` to infer thresholds; use `code` and `parameters`. The language can be selected via `Accept-Language`, `LocaleResolver`, user account settings, or product rules. Align localization workflows across server and client to avoid double translation.

## 3. Where does Spring get these pieces of data?

### 3.1. `MethodArgumentNotValidException`: errors on an object argument

When a handler has:

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // ...
}
~~~

If `OrderRequest` has constraints and the JSON request fails them, Spring MVC typically throws `MethodArgumentNotValidException`. This exception provides:

~~~java
BindingResult result = ex.getBindingResult();

List<FieldError> fields = result.getFieldErrors();
List<ObjectError> globals = result.getGlobalErrors();
~~~

For each `FieldError`:

~~~java
String field = error.getField();
String code = error.getCode();
String message = error.getDefaultMessage();
Object[] args = error.getArguments();
~~~

`getArguments()` provides arguments used when resolving message codes and is **not guaranteed to be a public constraint-parameter schema**. It can contain `MessageSourceResolvable` objects, field names, constraint values, and other items. Do not return raw `args` to the client.

`FieldError#getRejectedValue()` may contain user input, including tokens, document numbers, or private content. **Do not expose rejected values in public error JSON** just because the UI wants to "re-populate" a form; the frontend already has the input it just submitted.

### 3.2. `HandlerMethodValidationException`: errors directly on a method

With Spring MVC 6.1+:

~~~java
@GetMapping("/quote")
public String quote(
        @RequestParam(name = "units")
        @Min(1) int units) {
    return "units=" + units;
}
~~~

Violating `units=0` goes through built-in method validation and typically throws `HandlerMethodValidationException` with HTTP 400. Key APIs:

~~~java
ex.getParameterValidationResults();
ex.getCrossParameterValidationResults();
ex.isForReturnValue();
ex.getStatusCode();
ex.visitResults(...);
~~~

Each `ParameterValidationResult` has:
- `getMethodParameter()`: the relevant Java method parameter.
- `getResolvableErrors()`: the `MessageSourceResolvable` instances for direct violations.
- `getContainerIndex()` and `getContainerKey()`: index/key if validation targeted a collection/map element.
- `unwrap(resolvable, ConstraintViolation.class)`: available since Spring Framework 6.2 to retrieve Jakarta constraint metadata on applicable errors.

If the result is a `ParameterErrors` (subclass), you also have the `Errors` interface to read `getFieldErrors()`/`getGlobalErrors()` for a nested object. Do not assume every method-validation result is a `FieldError`.

### 3.3. `BindingResult` separates field errors and object errors

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError field) {
        // field.getField()
    } else {
        // Object-level error: no specific field path.
    }
}
~~~

Use `getAllErrors()` when you must **not miss object-level violations**. Reading only `getFieldErrors()` can drop constraints that validate multiple properties of the same object from the response.

### 3.4. Conversion errors differ from constraint violations

For example, a form submits:

~~~text
items[0].quantity=abc
~~~

The Java property is `Integer`, so `WebDataBinder` cannot convert `abc` to a number. `FieldError#getCode()` is typically `typeMismatch`. There is no corresponding Jakarta `ConstraintViolation`, because the error came from type conversion **before validation**.

By contrast:

~~~text
items[0].quantity=0
~~~

converts to `Integer` successfully; `@Min(1)` detects the failure and raises a constraint violation. Both can appear in `BindingResult` with different origins; the response mapper must handle both **without assuming every `FieldError` can unwrap to a Jakarta `ConstraintViolation`**.

### 3.5. Errors occurring before binding

- Invalid JSON: `HttpMessageNotReadableException`.
- Missing required query parameter: `MissingServletRequestParameterException`.
- Query `units=abc` when the method expects `int`: `MethodArgumentTypeMismatchException`.
- Unsupported media type: `HttpMediaTypeNotSupportedException`.

These are not necessarily `MethodArgumentNotValidException`. If the product needs a unified error contract, write corresponding handlers and populate `location/path/code/message` from what each exception provides; **do not assume `FieldError` always exists**.

## 4. Designing `ProblemDetail` and the frontend contract

Spring Framework 6.x includes `org.springframework.http.ProblemDetail` supporting RFC 9457. Standard fields:

| Field | Meaning |
| --- | --- |
| `type` | URI identifying the problem type |
| `title` | Short error type name |
| `status` | HTTP status |
| `detail` | General explanation |
| `instance` | Request instance URI if set |

Spring lets you add custom properties via `ProblemDetail#setProperty(String,Object)`; Spring's Jackson mixin renders them as top-level JSON properties. We add:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Fix the listed fields.",
  "code": "REQUEST_VALIDATION_FAILED",
  "issues": []
}
~~~

**Contract principles:**

1. `code` is for programmatic logic; `message` is only for display.
2. Keep **all valid issues**: if a field violates two constraints, do not collapse them to one error unless the product explicitly decides to.
3. Sort issues when you want a deterministic response; do not rely on the iteration order of `Set<ConstraintViolation<?>>`.
4. Do not send raw `ConstraintViolation`, `FieldError`, or `Throwable` directly through Jackson.
5. Do not use `getRejectedValue()` or `getArgument()` as public `parameters`.
6. For return-value validation, the fault is on the server: **do not leak information about internal responses or methods** and keep HTTP 500.
7. Cap the maximum number of issues in public APIs if a form could produce thousands of errors; document any truncation policy explicitly with `truncated`/`total` if the product needs it.

Example showing two issues on the same field is valid:

~~~json
{
  "issues": [
    {"code":"NotBlank","path":"customerName","message":"Required"},
    {"code":"Size","path":"customerName","message":"At most 30 characters"}
  ]
}
~~~

This is a minimal design illustration (other fields omitted for brevity). It shows that **an issue is not dropped just because of a duplicate path**; the frontend decides whether to display all of them or only the first.

### When an API wants JSON Pointer

`items[0].quantity` is convenient when the frontend also uses indexed form names. Some UI/schema libraries prefer JSON Pointer instead:

~~~text
/items/0/quantity
~~~

Do not blindly replace dots and brackets with regex if map keys can contain dots, `~`, `/`, or special characters. JSON Pointer (RFC 6901) has `~0` and `~1` escaping rules; mapping from a Spring property path to a JSON tree requires a reliable parser/canonicalizer. Until you have one, keep Spring's `path` and document its grammar in the API contract.

## 5. Maven Java 17 + Spring Boot 3.5.7 example

This project demonstrates a **unified error format** across three sources:
1. JSON body `@Valid @RequestBody` with a nested list.
2. HTML/form URL-encoded `@Valid @ModelAttribute`, including `typeMismatch` errors.
3. Query `@RequestParam @Min`, using Spring MVC 6.1+ built-in method validation.

It also includes an endpoint with an intentionally failing **return-value constraint** to prove internal details are not leaked.

### 5.1. Directory tree

~~~text
pom.xml
src/main/java/com/example/errors/
  ErrorResponseApplication.java
  LineItemInput.java
  OrderRequest.java
  OrderController.java
  ApiIssue.java
  ValidationErrorAdvice.java
src/main/resources/
  messages.properties
  messages_vi.properties
src/test/java/com/example/errors/
  ValidationErrorAdviceTest.java
~~~

### 5.2. Maven `pom.xml`

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
    <artifactId>structured-validation-errors</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-web` runs Spring MVC; `spring-boot-starter-validation` provides the Jakarta Bean Validation provider; `spring-boot-starter-test` includes JUnit 5 and `MockMvc`. Do not add the WebFlux starter in this project, to avoid mixing Servlet and reactive stack exception types.

### 5.3. Main application

~~~java
// src/main/java/com/example/errors/ErrorResponseApplication.java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorResponseApplication.class, args);
    }
}
~~~

### 5.4. List element DTO

~~~java
// src/main/java/com/example/errors/LineItemInput.java
package com.example.errors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class LineItemInput {

    @NotBlank(message = "{order.sku.required}")
    private String sku;

    @NotNull(message = "{order.quantity.required}")
    @Min(value = 1, message = "{order.quantity.min}")
    private Integer quantity;

    public LineItemInput() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

`quantity=0` passes conversion but violates `@Min(1)`; `quantity=abc` in a **form** causes `typeMismatch` before validation. For JSON, Jackson has its own deserialization mechanism; if JSON sends a value that cannot be parsed as an `Integer`, it can lead to `HttpMessageNotReadableException` instead of a `FieldError`. Do not apply identical conversion error expectations to both input paths.

### 5.5. Request DTO with a nested list

~~~java
// src/main/java/com/example/errors/OrderRequest.java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

import java.util.ArrayList;
import java.util.List;

public class OrderRequest {

    @NotBlank(message = "{order.customer.required}")
    private String customerName;

    @NotEmpty(message = "{order.items.required}")
    private List<@Valid LineItemInput> items = new ArrayList<>();

    public OrderRequest() {}

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public List<LineItemInput> getItems() {
        return items;
    }

    public void setItems(List<LineItemInput> items) {
        this.items = items;
    }
}
~~~

`@Valid` on the list element type requests validation of `LineItemInput.sku` and `LineItemInput.quantity`. When the provider bridges errors into Spring `BindingResult`, nested paths are typically `items[0].sku`, `items[0].quantity`. `@NotEmpty` on the list itself catches an order with zero line items.

Using `List<@Valid LineItemInput>` declares cascading validation directly on the element type. For a non-list DTO, `@Valid` on a nested object property behaves similarly. Do not treat `@Valid` as a standalone constraint — it is a cascading directive.

### 5.6. Controller: JSON, form, query, and return

~~~java
// src/main/java/com/example/errors/OrderController.java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class OrderController {

    @InitBinder("orderForm")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "items[*].sku",
                "items[*].quantity");
        binder.setAutoGrowCollectionLimit(16);
    }

    @PostMapping(path = "/api/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> createJson(
            @Valid @RequestBody OrderRequest request) {

        return Map.of(
                "accepted", true,
                "itemCount", request.getItems().size());
    }

    @PostMapping(path = "/api/orders/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> createForm(
            @Valid @ModelAttribute("orderForm") OrderRequest form) {

        return Map.of(
                "accepted", true,
                "itemCount", form.getItems().size());
    }

    @GetMapping("/api/quotes")
    public String quote(
            @RequestParam(name = "units")
            @Min(value = 1, message = "{order.units.min}")
            int units) {

        return "units=" + units;
    }

    @GetMapping("/api/broken")
    @NotBlank
    public String brokenReturn() {
        return ""; // Intentionally violates the server postcondition.
    }
}
~~~

Do not place class-level `@Validated` on the controller: Spring MVC 6.1+ has built-in handler method validation. Adding class-level `@Validated` can switch to an AOP proxy and produce a different exception type; this example keeps `HandlerMethodValidationException` consistent.

`@InitBinder("orderForm")` applies to **form property binding**; `setAllowedFields` is not a JSON deserialization filter for `@RequestBody`. In production, use input DTOs containing only public fields and enforce ownership and authorization in the service layer. Here, success responses stay minimal so the focus remains on errors.

### 5.7. A record representing each issue

~~~java
// src/main/java/com/example/errors/ApiIssue.java
package com.example.errors;

import java.util.Map;

public record ApiIssue(
        String code,
        String path,
        String location,
        Integer parameterIndex,
        Map<String, Object> parameters,
        String message) {
}
~~~

A Java 17 `record` is an immutable carrier; Jackson in Spring Boot 3.5 serializes its components as JSON properties. `parameters` holds only **whitelisted metadata**. Never put `Object rejectedValue`, `Throwable cause`, or `Object[] arguments` in this record.

`path` uses `""` for object-level or cross-parameter errors when there is no specific field. `parameterIndex` may be null when an error is not tied to a single parameter. In this project's code, both body and form errors come from handler argument index 0, so `parameterIndex=0` is recorded.

### 5.8. Advice: mapping Spring errors into a safe `ProblemDetail`

~~~java
// src/main/java/com/example/errors/ValidationErrorAdvice.java
package com.example.errors;

import jakarta.validation.ConstraintViolation;
import org.springframework.core.MethodParameter;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestControllerAdvice
public class ValidationErrorAdvice {

    // Framework/constraint codes approved for public exposure.
    private static final Set<String> PUBLIC_CODES = Set.of(
            "NotBlank", "NotNull", "NotEmpty",
            "Min", "Size", "typeMismatch");

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidObject(
            MethodArgumentNotValidException ex) {

        String location = ex.getParameter()
                .hasParameterAnnotation(ModelAttribute.class)
                ? "form" : "body";
        int parameterIndex =
                ex.getParameter().getParameterIndex();

        List<ApiIssue> issues = new ArrayList<>();

        // getAllErrors() includes both field and object-level errors.
        for (ObjectError error :
                ex.getBindingResult().getAllErrors()) {

            String path = error instanceof FieldError field
                    ? field.getField() : "";

            issues.add(new ApiIssue(
                    publicCode(error.getCode()),
                    path,
                    location,
                    parameterIndex,
                    safeParameters(error),
                    safeMessage(error.getDefaultMessage())));
        }
        return problem(HttpStatus.BAD_REQUEST,
                "REQUEST_VALIDATION_FAILED", issues);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> invalidMethod(
            HandlerMethodValidationException ex) {

        // Postcondition failure is a server error: do not expose contract details.
        if (ex.isForReturnValue()) {
            return problem(HttpStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_CONTRACT_ERROR", List.of());
        }

        List<ApiIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            int index =
                    result.getMethodParameter().getParameterIndex();

            if (result instanceof ParameterErrors beanErrors) {
                // Nested errors inside a @Valid DTO.
                for (ObjectError error : beanErrors.getAllErrors()) {
                    String path =
                            error instanceof FieldError field
                                    ? field.getField() : "";

                    issues.add(new ApiIssue(
                            publicCode(error.getCode()),
                            path,
                            "body",
                            index,
                            safeParameters(error),
                            safeMessage(error.getDefaultMessage())));
                }
                continue;
            }

            // Direct parameter constraints: @Min, @NotBlank, ...
            String basePath =
                    requestParameterName(result.getMethodParameter());
            String path = withContainerPath(basePath, result);

            for (MessageSourceResolvable error :
                    result.getResolvableErrors()) {

                issues.add(new ApiIssue(
                        publicCode(error.getCodes()),
                        path,
                        "query",
                        index,
                        safeParameters(result, error),
                        safeMessage(error.getDefaultMessage())));
            }
        }

        // Cross-parameter constraints: do not mistakenly assign to a single field.
        for (MessageSourceResolvable error :
                ex.getCrossParameterValidationResults()) {
            issues.add(new ApiIssue(
                    publicCode(error.getCodes()),
                    "",
                    "crossParameter",
                    null,
                    Map.of(),
                    safeMessage(error.getDefaultMessage())));
        }

        return problem(ex.getStatusCode(),
                "REQUEST_VALIDATION_FAILED", issues);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> invalidQueryType(
            MethodArgumentTypeMismatchException ex) {

        ApiIssue issue = new ApiIssue(
                "typeMismatch",
                ex.getName(),
                "query",
                ex.getParameter().getParameterIndex(),
                Map.of(),
                "Query parameter has an invalid type");

        // Do not expose ex.getValue() or Throwable details.
        return problem(HttpStatus.BAD_REQUEST,
                "REQUEST_VALIDATION_FAILED", List.of(issue));
    }

    private static ResponseEntity<ProblemDetail> problem(
            HttpStatusCode status,
            String code,
            List<ApiIssue> issues) {

        ProblemDetail body = ProblemDetail.forStatus(status);
        boolean internal = status.is5xxServerError();

        body.setType(URI.create(internal
                ? "urn:problem:internal-contract"
                : "urn:problem:invalid-request"));
        body.setTitle(internal ? "Internal error" : "Invalid request");
        body.setDetail(internal
                ? "Server could not produce a valid result."
                : "Fix the listed fields.");
        body.setProperty("code", code);

        List<ApiIssue> sorted = issues.stream()
                .sorted(Comparator.comparing(ApiIssue::location)
                        .thenComparing(ApiIssue::path)
                        .thenComparing(ApiIssue::code))
                .toList();
        body.setProperty("issues", sorted);

        return ResponseEntity.status(status).body(body);
    }

    private static String safeMessage(String message) {
        return message == null || message.isBlank()
                ? "Invalid value" : message;
    }

    // Keep contracted general code; never expose class/method names.
    private static String publicCode(String code) {
        return code != null && PUBLIC_CODES.contains(code)
                ? code : "INVALID_VALUE";
    }

    private static String publicCode(String[] codes) {
        if (codes == null) {
            return "INVALID_VALUE";
        }
        // Spring provides codes from most specific to most general.
        for (int i = codes.length - 1; i >= 0; i--) {
            if (PUBLIC_CODES.contains(codes[i])) {
                return codes[i];
            }
        }
        return "INVALID_VALUE";
    }

    private static String requestParameterName(
            MethodParameter parameter) {

        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);

        if (annotation != null) {
            String explicit = annotation.name().isBlank()
                    ? annotation.value() : annotation.name();
            if (!explicit.isBlank()) {
                return explicit;
            }
        }

        String javaName = parameter.getParameterName();
        return javaName != null
                ? javaName
                : "arg" + parameter.getParameterIndex();
    }

    private static String withContainerPath(
            String path,
            ParameterValidationResult result) {

        if (result.getContainerIndex() != null) {
            return path + "[" + result.getContainerIndex() + "]";
        }
        Object key = result.getContainerKey();
        if (key != null) {
            // Allow only short keys formatted like public identifiers.
            String text = String.valueOf(key);
            return text.matches("[A-Za-z0-9_-]{1,40}")
                    ? path + "[" + text + "]"
                    : path + "[key]";
        }
        return path;
    }

    // FieldError/ObjectError may wrap a ConstraintViolation
    // or a conversion error; never assume unwrap always succeeds.
    private static Map<String, Object> safeParameters(
            ObjectError error) {
        try {
            ConstraintViolation<?> violation =
                    error.unwrap(ConstraintViolation.class);
            return safeConstraintAttributes(violation);
        } catch (IllegalArgumentException unavailable) {
            return Map.of();
        }
    }

    private static Map<String, Object> safeParameters(
            ParameterValidationResult result,
            MessageSourceResolvable error) {
        try {
            ConstraintViolation<?> violation =
                    result.unwrap(error, ConstraintViolation.class);
            return safeConstraintAttributes(violation);
        } catch (IllegalArgumentException unavailable) {
            return Map.of();
        }
    }

    private static Map<String, Object> safeConstraintAttributes(
            ConstraintViolation<?> violation) {

        String kind = violation.getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName();
        Map<String, Object> attributes =
                violation.getConstraintDescriptor().getAttributes();
        Map<String, Object> safe = new LinkedHashMap<>();

        // Do not expose raw message, groups, payload, or regex.
        if ("Min".equals(kind)
                && attributes.get("value") instanceof Number min) {
            safe.put("minimum", min.longValue());
        }
        if ("Size".equals(kind)) {
            if (attributes.get("min") instanceof Number min) {
                safe.put("minLength", min.intValue());
            }
            if (attributes.get("max") instanceof Number max) {
                safe.put("maxLength", max.intValue());
            }
        }
        return safe;
    }
}
~~~

**Important note on runnability:** this file targets **Spring Framework 6.2**. The `ParameterValidationResult.unwrap(error, ConstraintViolation.class)` API was introduced in Spring 6.2; if compiling against 6.1, adjust how metadata is retrieved and avoid calling a non-existent API. `getParameterValidationResults()` is the preferred API in 6.2 replacing deprecated methods. All imports, the `ApiIssue` type, and Spring Boot dependencies are declared so the example compiles as a complete project.

**Clarified code limitations:**
- `PUBLIC_CODES` is an allowlist for the public contract; other errors fall back to `INVALID_VALUE`. Real projects should expand the list according to registered constraints.
- `getDefaultMessage()` preserves messages already resolved for the locale by Bean Validation/Spring. If you need locale-specific Spring `MessageSource` resolution for custom `MessageSourceResolvable` instances, inject `MessageSource` and call `getMessage(resolvable,locale)`.
- `safeConstraintAttributes` exposes only appropriate numeric thresholds rather than serializing the full `ConstraintDescriptor`.
- `ParameterErrors` uses `getAllErrors()` to keep both field and global errors.
- Cross-parameter errors are given `location=crossParameter` and `path=""`, never arbitrarily assigned to one argument.
- Return-value errors intentionally return 500 with `issues=[]` and a generic server code; in a real system, log securely internally for investigation.
- In the demo, direct method constraints only exist on query parameter `units`, so `location=query` is accurate. If you add direct constraints on `@PathVariable`, `@RequestHeader`, or body, **classify by annotation**, for example via `HandlerMethodValidationException.Visitor`, rather than hardcoding `query` for everything.
- For `ParameterErrors`, the demo sets `location=body` because the DTO comes from a JSON body. If you add method-validated form DTOs or multipart arguments, determine the exact annotation/argument source in the contract.
- `withContainerPath` uses available indices/keys while replacing unusual keys with a placeholder to avoid exposing arbitrary map keys containing sensitive characters.

### 5.9. Resource bundles for localized messages

**`src/main/resources/messages.properties`:**

~~~properties
order.customer.required=Customer name is required
order.items.required=At least one line item is required
order.sku.required=SKU is required
order.quantity.required=Quantity is required
order.quantity.min=Quantity must be at least {value}
order.units.min=Units must be at least {value}
~~~

**`src/main/resources/messages_vi.properties`:**

~~~properties
order.customer.required=Tên khách hàng không được trống
order.items.required=Cần ít nhất một dòng hàng
order.sku.required=Mã hàng không được trống
order.quantity.required=Số lượng là bắt buộc
order.quantity.min=Số lượng phải từ {value} trở lên
order.units.min=Số đơn vị phải từ {value} trở lên
~~~

Spring Boot integrates the application `MessageSource` with constraint message interpolation when the provider is configured. `{value}` in `@Min(value=1)` is a constraint attribute resolved by the Bean Validation provider, not a standard `MessageFormat {0}` placeholder. To switch locale per request in MVC, clients can send `Accept-Language: vi` when an appropriate locale resolver is used.

## 6. Testing with MockMvc: do not assert only HTTP status

### 6.1. Integration test suite

~~~java
// src/test/java/com/example/errors/ValidationErrorAdviceTest.java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationErrorAdviceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonErrorsKeepCodeAndExactIndexedPaths() throws Exception {
        mvc.perform(post("/api/orders")
                .locale(Locale.ENGLISH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerName":"",
                      "items":[
                        {"sku":"PEN","quantity":0},
                        {"sku":"","quantity":2}
                      ]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("REQUEST_VALIDATION_FAILED"))
            .andExpect(jsonPath("$.issues.length()").value(3))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("customerName")))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("items[0].quantity")))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("items[1].sku")));
    }

    @Test
    void minConstraintKeepsItsPublicThreshold() throws Exception {
        mvc.perform(post("/api/orders")
                .locale(Locale.ENGLISH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"Lan",
                     "items":[{"sku":"PEN","quantity":0}]}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("Min"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("items[0].quantity"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("body"))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Quantity must be at least 1"));
    }

    @Test
    void formTypeMismatchKeepsIndexedFieldPath() throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", "Lan")
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("items[0].quantity"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("form"));
    }

    @Test
    void directQueryConstraintKeepsNameAndParameterIndex()
            throws Exception {
        mvc.perform(get("/api/quotes")
                .locale(Locale.ENGLISH)
                .param("units", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("Min"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("units"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"))
            .andExpect(jsonPath("$.issues[0].parameterIndex")
                    .value(0))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1));
    }

    @Test
    void malformedQueryNumberStillHasSafeError() throws Exception {
        mvc.perform(get("/api/quotes").param("units", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("units"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"));
    }

    @Test
    void invalidServerReturnDoesNotLeakInternals()
            throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("INTERNAL_CONTRACT_ERROR"))
            .andExpect(jsonPath("$.issues.length()").value(0));
    }

    @Test
    void validJsonAndValidQueryStillWork() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"Lan",
                     "items":[{"sku":"PEN","quantity":2}]}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemCount").value(1));

        mvc.perform(get("/api/quotes").param("units", "2"))
            .andExpect(status().isOk());
    }

    @Test
    void vietnameseMessageDoesNotChangeStableCode()
            throws Exception {
        mvc.perform(get("/api/quotes")
                .locale(Locale.forLanguageTag("vi"))
                .param("units", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("Min"))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Số đơn vị phải từ 1 trở lên"));
    }
}
~~~

**Expected outcome:** 8 JUnit tests PASS (one test contains two valid requests). This is the expected result based on the contract and code, not a claim that Maven has been executed in a build environment. `jsonPath("$.issues.length()")` uses Spring test's JSONPath expression, and the errors are sorted by the advice before serialization.

### 6.2. Running tests and the server

~~~bash
mvn test
mvn spring-boot:run
~~~

Example failing JSON request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"customerName":"","items":[{"sku":"PEN","quantity":0}]}'
~~~

You can verify the HTTP 400 response with the stable `code` `REQUEST_VALIDATION_FAILED`, the issue paths, and `minimum=1`. The order of JSON object keys is not part of the contract, so clients must not depend on property ordering; the `issues` array is sorted by the application.

If running in PowerShell, watch JSON quoting rules for your shell. For automated verification, use `MockMvc` rather than relying on `curl`/running server calls.

## 7. Classifying errors and preserving HTTP semantics

Not every error with "validation" in its name belongs to the same responsibility.

| Situation | Error category | Typical HTTP status | Expose metadata? |
| --- | --- | --- | --- |
| `@NotBlank` on a JSON DTO field | Invalid input | 400 | Code, path, message, safe params |
| `@Min` on `@RequestParam` | Invalid method parameter | 400 | Query name, parameterIndex, threshold |
| `typeMismatch` in a form DTO | Data binding | 400 | Code, path; no rejected value |
| Unparseable query number | Argument conversion | 400 | Parameter name, `typeMismatch` code |
| Invalid JSON syntax | Deserialization | 400 | `INVALID_JSON` code, no raw body/parser trace |
| Missing required parameter | Resolution | 400 | `MISSING_PARAMETER` code, public parameter name |
| Unsatisfied custom business invariant | Domain validation | 400 or 409/422 per API contract | Stable business code |
| Unsatisfied constraint on controller return value | Server error | 500 | Server code only, no return value leaked |
| Provider/configuration failure `ConstraintDeclarationException` | Server bug/config | 500 | Generic server code |

**Do not turn every validation exception into 400.** Spring's `HandlerMethodValidationException` separates **input errors (400)** from **return-value errors (500)** via `isForReturnValue()`/`getStatusCode()`. If application advice unconditionally returns `ResponseEntity.badRequest()` for this exception, it can mask server bugs and break both alerting and the HTTP contract.

For domain rules, HTTP 422 is sometimes used for syntactically valid content that violates business rules; HTTP 409 is used for state conflicts. These are API design choices, **not automatic codes from Jakarta Bean Validation**. Consistency and documenting the contract matter more than forcing one status across every use case.

## 8. Important additions for production APIs

### 8.1. Do not miss object-level constraints

A custom constraint may check `startDate <= endDate` across the whole class. It can place the error in `BindingResult#getGlobalErrors()` instead of `getFieldErrors()`. If you only iterate over field errors, you lose this rule.

In the API, represent it as:

~~~json
{
  "code": "DATE_RANGE_INVALID",
  "path": "",
  "location": "body",
  "parameterIndex": 0,
  "parameters": {},
  "message": "End date must not be before start date"
}
~~~

When using a custom code such as `DATE_RANGE_INVALID`, **add it to the public codes allowlist** and write an integration test. Otherwise, `ValidationErrorAdvice` defaults to returning `INVALID_VALUE`. Do not let an empty field path be mistaken for a forgotten field; the contract should explicitly state that it represents a whole-object error.

### 8.2. Multi-field constraints

When a rule spans two fields, there are two options:
- Keep a single **object-level issue** with its own code and a `relatedPaths` structure if needed.
- Inside `ConstraintValidatorContext`, explicitly attach the violation to one or more fields if the UX contract requires it.

Do not automatically generate two identical-message errors on both fields simply because the constraint inspects two fields. That can clutter the frontend UI and skew error counts.

### 8.3. Validation groups

`@Validated(SomeGroup.class)` changes the set of constraints evaluated. The API error response **does not need** to expose Java group class names publicly. Only the code, path, public parameters, and message of violations that actually occurred are needed.

If the same rule applies to Create and Update with different messages or limits, test each endpoint and each group; do not hardcode `minimum=1` across every context. In the example, the threshold comes from the `ConstraintDescriptor` that produced the violation, so annotation changes are reflected accurately when tests run.

### 8.4. Container index and Map key

`ParameterValidationResult#getContainerIndex()` and `getContainerKey()` identify **which element** of a method parameter container failed. Do not try to guess the index/key from `MessageSourceResolvable#getDefaultMessage()`.

When client-supplied Map keys might contain emails, tokens, or sensitive data, do not echo raw keys without a policy. You can:
- Allow only keys belonging to a whitelist/public vocabulary.
- Replace keys with ordinal/canonical identifiers.
- Use a normalized `path` with a placeholder and expose `containerIndex`/`containerKey` only when safe.

The demo uses `withContainerPath` for simple keys; complex Map structures need dedicated parsing and escaping.

### 8.5. Messages and `parameters` are not the same data layer

`MessageSourceResolvable#getArguments()` may carry metadata/arguments for rendering messages, but **it does not automatically become a public `parameters` contract**. Beyond constraint attributes, it can contain Spring message resolution arguments, field labels, or error-specific values. Never serialize raw `args`.

The sample code uses `ConstraintViolation#getConstraintDescriptor().getAttributes()` when unwrapping succeeds and exposes only `minimum`/`minLength`/`maxLength` from known constraints. For conversion errors, `parameters={}` because there is no Jakarta descriptor. If you need `expectedType="integer"`, design a whitelist aligned with your DTO schema rather than exposing raw `Class<?>` or exception target types.

### 8.6. Spring `MessageSource` localization

A Bean Validation message template looks like:

~~~java
@Min(value=1, message="{order.quantity.min}")
~~~

`messages_vi.properties` can contain:

~~~properties
order.quantity.min=Số lượng phải từ {value} trở lên
~~~

The server interpolates this into a Vietnamese message while `code="Min"` and `parameters={"minimum":1}` remain unchanged. This lets the frontend preserve consistent behavior across locales.

For **binding errors** such as `typeMismatch`, messages can go through Spring's `MessageSource` and `MessageCodesResolver`; that is a separate translation path from Bean Validation. For a complete multilingual experience, add and test the corresponding `typeMismatch`/missing-parameter keys. In the demo, the code and path of `typeMismatch` errors are preserved, while the text can be supplied by Spring or defined by the advice.

## 9. Why should you not expose raw `FieldError` or `ConstraintViolation`?

### 9.1. Data leakage

Framework objects may hold:
- User-submitted values (`rejectedValue`, `invalidValue`, `getArgument()`).
- Full property paths containing keys with private data.
- Bean/object names, Java class names, method parameter types.
- Raw error arguments and cause chains.
- Constraint descriptor attributes such as regexes, group classes, and payloads.

Serializing them directly can break the API schema across framework versions or leak sensitive data. The purpose of a public issue DTO is to **translate raw internals into safe client-facing semantics**.

### 9.2. Do not log all values

Even in internal logs, avoid logging raw form bodies, headers, or rejected values unless explicitly required under data-protection policies. Prefer: correlation ID, trace ID, API route, public issue code, sanitized path, issue count, and HTTP status. For server errors needing debugging, store stack traces in secure internal logs and never return them to clients.

### 9.3. Untrusted data in `path` and `message`

`path` may contain client-controlled Map keys; `message` from custom validators may contain interpolated input. If the frontend renders them directly as HTML, XSS risks arise. The UI must escape output, the server should avoid interpolating raw input into messages, and keys/paths should be constrained or encoded. **`ProblemDetail` does not prevent XSS on its own**; it is merely a JSON structure.

## 10. Combining `ResponseEntityExceptionHandler` and `@ControllerAdvice`

In Spring MVC, `ResponseEntityExceptionHandler` provides built-in hooks such as:
- `handleMethodArgumentNotValid(...)`.
- `handleHandlerMethodValidationException(...)`.
- `handleTypeMismatch(...)`.
- `handleHttpMessageNotReadable(...)`.

You can **extend `ResponseEntityExceptionHandler`** and override the appropriate hooks to build consistent `ProblemDetail` payloads. This is very useful when a project needs to standardize many built-in exceptions, and it also supports `MessageSource` for `type`/`title`/`detail`. The runnable example uses `@RestControllerAdvice` with three separate `@ExceptionHandler` methods to stay focused on preserving metadata.

**Do not mix the two patterns recklessly:** if an advice class extends `ResponseEntityExceptionHandler`, Spring registers its built-in exception handlers. Adding `@ExceptionHandler(MethodArgumentNotValidException.class)` in the same class can cause **ambiguous exception mappings**. Choose one approach and test handler registration.

Spring `ProblemDetail` defines standard fields, while `issues` is our added extension. Clients that only understand basic RFC 9457 can still read `status`/`title`/`detail`; application clients can read `issues` as well.

## 11. What is different in WebFlux?

The metadata principles are the same, but the exception classes and reactive pipeline differ:

- With WebFlux `@Valid @ModelAttribute`, object-only validation typically produces **`WebExchangeBindException`**, which exposes `getBindingResult()` for field/global errors.
- With Spring WebFlux 6.1+ and direct method constraints, **`HandlerMethodValidationException`** can also occur. It contains similar `ParameterValidationResult` objects, though the handler response must fit the WebFlux lifecycle.
- With WebFlux `@RequestBody`, JSON is read via `HttpMessageReader`/Jackson; conversion failures do not automatically become `FieldError` entries.
- Use the reactive stack's `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` or `@RestControllerAdvice` with reactive-compatible signatures.
- Do not copy `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` (Servlet MVC) into a WebFlux application.

In applications returning `Mono<ResponseEntity<ProblemDetail>>`, construct responses from the exception/validation metadata provided by the framework without blocking the event loop on database lookups inside exception handlers. For localization and trace metadata, use the appropriate reactive context; do not assume `ThreadLocal` propagates across Reactor boundaries.

## 12. Checklist and common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Client only sees "Validation failed" | Backend omits code/path/details | Return issues with a stable schema |
| UI cannot tell which line item failed | Backend strips `items[0].quantity` down to `quantity` | Preserve indexed field paths |
| One of two errors on the same field is lost | Backend uses `Map<path,message>` that overwrites | Use `List<ApiIssue>` |
| Object-level error does not appear | Iterating only `getFieldErrors()` | Use `getAllErrors()` and empty path for globals |
| `@Min` has code but no threshold | Not preserving constraint metadata | Whitelist `value` as `minimum` |
| API leaks group/payload/regex | Serializing all `ConstraintDescriptor.attributes` | Extract only public parameters |
| API leaks user input | Exposing `rejectedValue`/`getArgument()` | Never echo raw invalid values |
| `Min` shows up as a Java class name | Exposing the full `getCodes()` array | Select a single public error code |
| Query `units=abc` bypasses validator | Converter fails before method validation | Handle `MethodArgumentTypeMismatchException` |
| Wrong JSON type produces no `FieldError` | Jackson throws deserialization error | Handle `HttpMessageNotReadableException` separately |
| Return-value error returns 400 | Advice treats all `HandlerMethodValidationException` alike | Use `isForReturnValue()`/`getStatusCode()` |
| Locale change breaks client logic | Client parses `message` text | Branch on `code` and `parameters` |
| Raw `getContainerKey()` exposed verbatim | Map keys can hold sensitive data | Canonicalize/whitelist keys |
| Request has multiple issues but only first is kept | Calling `getFieldError()` once | Collect all errors and sort |
| `BindingResult` missing in handler | Not placed immediately after validated argument | Fix handler signature; test framework flow |
| Compiling on Spring 6.1 fails on missing `unwrap` | `unwrap` on `ParameterValidationResult` was added in 6.2 | Upgrade to 6.2 or adapt the mapper |
| WebFlux uses MVC advice | Mixed servlet/reactive packages | Use the exception handler for the active stack |

### Pre-release API checklist

1. Define `type`/`status`/response-level `code` and a versioning strategy.
2. Restrict `issues[*].code` to a published, long-lived allowlist.
3. Preserve exact nested property/index `path` values and conventions for object-level errors.
4. Distinguish `location` (`body`/`form`/`query`/`header`/`path`/`cross-parameter`) where applicable.
5. Treat `parameterIndex` as zero-based, and prefer public request names so API refactors do not break clients.
6. Populate `parameters` solely with whitelisted public data from constraint attributes.
7. Resolve `message` for the locale and ensure clients never parse it for logic.
8. Never expose raw invalid/rejected values, exception causes, stack traces, or internal class names.
9. Keep HTTP 400 for input validation and HTTP 500 without internals for return-value violations.
10. Test JSON binding, form conversion, direct method constraints, object/global errors, localization, and other error categories.
11. Establish policies for maximum issue counts, deterministic sorting, duplicate issues, and path escaping.
12. Write regression tests for the error response contract before upgrading Spring or the Jakarta provider.

## 13. References

- Spring Framework 6.2 — Spring MVC Validation, `MethodArgumentNotValidException` and `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error Responses, `ProblemDetail` and RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — `ObjectError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — `ParameterValidationResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 — `ParameterErrors` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring Framework 6.2 — `HandlerMethodValidationException` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Validation 3.1 specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
