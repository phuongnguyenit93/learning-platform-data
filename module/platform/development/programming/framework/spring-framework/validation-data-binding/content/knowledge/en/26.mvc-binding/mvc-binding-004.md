# Placing BindingResult Immediately After the Bound Parameter in Spring MVC

## 1. Mandatory rule in the controller signature

When Spring MVC maps HTTP data into an object (data binding), for example via `@ModelAttribute`, the framework records type conversion errors and may perform validation with `@Valid` or `@Validated`. If you want to **handle errors directly inside the controller**, place the `BindingResult` or `Errors` parameter **immediately after the bound object**, with no other parameter in between:

```java
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "orderForm";
    }
    // Process business logic only if the data is valid.
    return "redirect:/orders/success";
}
```

This is an illustrative snippet, not a standalone Java application. Parameter pair to remember:

```text
@Valid @ModelAttribute("order") OrderForm form
                         ↓ place IMMEDIATELY AFTER
                    BindingResult result
                         ↓
                    Model, Locale, other parameters
```

**Wrong position:**

```java
// Violates the rule because Model sits between form and BindingResult.
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        Model model,
        BindingResult result) {
    // ...
}
```

The Java compiler can still compile this signature, but Spring MVC does not treat `result` as the error-handling parameter paired with `form`. When a binding/validation error occurs, argument resolution may throw an exception instead of invoking the handler with the errors as intended. **Simply declaring a `BindingResult` somewhere in the method is not enough.**

This is a rule of Spring MVC handler argument resolution, **not** a Java syntax rule and not a requirement imposed by Jakarta Bean Validation itself.

## 2. What is BindingResult and what errors does it store?

`org.springframework.validation.BindingResult` extends `org.springframework.validation.Errors`. It holds the outcome of binding a specific object, including errors:

- **Binding/type-conversion:** the HTTP request sends the string `"abc"` while the Java field has type `Integer`; the error usually has code `typeMismatch`.
- **Validation:** the request binds onto the object, but a field violates `@NotBlank`, `@Min`, `@Size`, or another constraint.
- **Object-level:** rules involving multiple properties together or rules added by a validator via `reject(...)`.
- **Manually added errors:** a controller/service adapter may record additional errors via `rejectValue(...)` or `reject(...)` when required by the application's contract.

Commonly used methods:

| Method | Meaning |
| --- | --- |
| `hasErrors()` | Whether there is at least one error |
| `getErrorCount()` | Number of errors |
| `getFieldErrors()` | All field-level errors (`FieldError`) |
| `getFieldError("quantity")` | One error for field `quantity`, if any |
| `getGlobalErrors()` | Object-level errors (`ObjectError`) |
| `getAllErrors()` | Combined field and global errors |
| `getObjectName()` | Model attribute name, e.g., `order` |
| `getFieldValue("quantity")` | Field value from the binding perspective, useful when re-rendering forms |
| `rejectValue(field, code, ...)` | Adds a field error |
| `reject(code, ...)` | Adds an object-level error |
| `getSuppressedFields()` | List of fields blocked from binding by allowed/disallowed field restrictions |

`FieldError` contains the field name, set of error codes, default message, and information about the rejected value. Do not put raw `getRejectedValue()` values into logs or responses if they could contain passwords, tokens, or private information.

`BindingResult` is not a “request-wide error aggregator”. It is tied to the **single** command object immediately preceding it.

## 3. Why must it be immediately adjacent?

A handler can accept multiple bound objects. Spring MVC produces binding and validation results for each object in the order of handler parameter resolution. Declaring a `BindingResult` immediately after an object tells the framework you want to capture the result of that specific object inside the handler, rather than letting the framework raise an error via the default flow.

Example of two valid pairs:

```java
@PostMapping("/checkout")
public String checkout(
        @Valid @ModelAttribute("buyer") BuyerForm buyer,
        BindingResult buyerErrors,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult shippingErrors,
        Model model) {

    if (buyerErrors.hasErrors() || shippingErrors.hasErrors()) {
        return "checkoutForm";
    }
    return "redirect:/checkout/complete";
}
```

This is illustrative integration code; assume `BuyerForm`, `ShippingForm`, and the views already exist.

The following signature is **incorrect**:

```java
// Two model attributes followed by two BindingResults: mismatched pairs.
@PostMapping("/checkout")
public String checkout(
        @Valid @ModelAttribute("buyer") BuyerForm buyer,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult buyerErrors,
        BindingResult shippingErrors) {
    // ...
}
```

Spring does not match results by variable names like `buyerErrors` or `shippingErrors`. **Adjacency is the contract.** When adding `Model`, `Locale`, `HttpServletRequest`, or `Principal`, do not insert them between an object and the `BindingResult` of the same pair.

An easy mental model: **each command object has an “error slot” immediately to its right**.

## 4. Processing flow: binding first, validation second

With `@ModelAttribute`, a typical processing flow is:

1. The framework looks up or instantiates the command object; e.g., `OrderForm` named `order`.
2. `WebDataBinder` takes request parameters, converts types via converters/formatters/property editors, and sets the corresponding properties.
3. If type conversion fails, the binder records an error such as `typeMismatch` instead of forcing the handler to throw a `NumberFormatException`.
4. When `@Valid` or `@Validated` and a suitable provider/validator are present, the framework runs validation on the bound object.
5. Results are recorded in the corresponding `BindingResult`.
6. If a `BindingResult` immediately follows the object, the controller can inspect and handle errors. If not, the framework applies the exception flow appropriate for the parameter/validation type.

Suppose the DTO is:

```java
public class OrderForm {

    @NotBlank
    private String itemCode;

    @Min(1)
    private Integer quantity;

    // getters/setters
}
```

If a request sends `itemCode=` and `quantity=abc`:

- An empty string is assigned to `itemCode`, which violates `@NotBlank`.
- The string `"abc"` cannot be converted to `Integer` for `quantity`; the binder records `typeMismatch`.
- Both errors can appear together in the `BindingResult` of `OrderForm`.

If a request sends `quantity=0`, type conversion succeeds but `@Min(1)` fails. If `quantity` is `null`, `@Min` permits `null` under the Bean Validation contract; to require a value, add `@NotNull`.

**A binding error is not the same as a validation error.** `BindingResult` exposes both, but they originate from different stages and require appropriate error messages.

## 5. Java 17, Spring Boot 3.5.6, Maven, and HTTP form example

This complete example creates a `POST /orders` endpoint using `@Valid @ModelAttribute` with an immediately following `BindingResult`. It returns appropriate HTTP status codes and a body containing sorted error codes for easy verification. No database or template engine is needed.

### 5.1. File structure

```text
binding-result-demo/
├── pom.xml
└── src/main/java/demo/
    ├── BindingResultApplication.java
    └── OrderController.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>binding-result-demo</artifactId>
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
```

`spring-boot-starter-web` provides Spring MVC/embedded server; `spring-boot-starter-validation` provides the Jakarta Bean Validation provider.

### 5.3. BindingResultApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingResultApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingResultApplication.class, args);
    }
}
```

### 5.4. OrderController.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class OrderController {

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + simpleCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest().body("INVALID|" + details);
        }

        return ResponseEntity.ok(
            "ACCEPT|" + form.getItemCode() + "|" + form.getQuantity());
    }

    // FieldError.getCodes() may contain object- and field-specific codes.
    // Pick the last general code for easy output comparison.
    private static String simpleCode(FieldError error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
            ? "unknown"
            : codes[codes.length - 1];
    }

    public static class OrderForm {

        @NotBlank
        private String itemCode;

        @Min(1)
        private Integer quantity;

        public OrderForm() {
        }

        public String getItemCode() {
            return itemCode;
        }

        public void setItemCode(String itemCode) {
            this.itemCode = itemCode;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }
}
```

For easy observation, the controller explicitly converts errors into `"INVALID|..."` and returns `400 Bad Request`. **This is the controller's decision**, not `BindingResult` choosing an HTTP status by itself.

`OrderForm` is a DTO dedicated to web binding, with a public no-arg constructor and JavaBean getters/setters. Only when the data is valid does the controller read the fields and return the result. The code picks the last code in `FieldError#getCodes()` rather than using `getCode()` directly, because the first code usually includes object and field prefixes generated by `MessageCodesResolver`.

### 5.5. Running and verifying output

In the `binding-result-demo` directory, with Java 17+ and Maven 3.x:

```bash
mvn -q spring-boot:run
```

By default, the server listens on `localhost:8080` if the port is free. From another bash/zsh/WSL terminal, send requests:

**Valid data:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=PEN-1' \
  --data-urlencode 'quantity=2'
```

HTTP `200 OK`, body:

```text
ACCEPT|PEN-1|2
```

**Quantity violating constraint:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=PEN-1' \
  --data-urlencode 'quantity=0'
```

HTTP `400 Bad Request`, body:

```text
INVALID|quantity:Min
```

**One validation error and one binding error:**

```bash
curl -s -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'itemCode=' \
  --data-urlencode 'quantity=abc'
```

HTTP `400 Bad Request`, body:

```text
INVALID|itemCode:NotBlank,quantity:typeMismatch
```

Both types of errors are held in the same `BindingResult` for `order`. The printed line does not depend on the order in which the validator discovers errors because the controller calls `sorted()`. `curl -s` prints only the body without adding a trailing newline; the blocks above display the body on its own for readability. Server/Maven startup logs are not part of the response.

If you **omit `BindingResult` from the signature** in the `@Valid @ModelAttribute` case, Spring MVC typically throws `MethodArgumentNotValidException` on error rather than letting the controller handle it inline. If you want a custom response in that mode, use an appropriate `@ExceptionHandler` or `@ControllerAdvice`.

## 6. BindingResult placement with @RequestBody and @RequestPart

The “place immediately after the object” rule does not apply only to form binding.

### @Valid @RequestBody

`@RequestBody` uses `HttpMessageConverter` to read JSON/XML into an object. For a DTO that deserializes successfully yet violates constraints, validation can be handled directly inside the handler:

```java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody AccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid account");
    }
    return ResponseEntity.ok().build();
}
```

This is an **illustrative integration snippet**: it requires the `AccountRequest` DTO, imports, and Spring MVC/Jackson setup. **Malformed** JSON syntax, unreadable bodies, or deserialization failures can raise `HttpMessageNotReadableException` **before** the framework has a DTO to validate. An adjacent `BindingResult` is not responsible for catching such parser errors.

### @Valid @RequestPart

For multipart request metadata:

```java
@PostMapping("/attachments")
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") MetadataRequest metadata,
        BindingResult metadataErrors,
        @RequestPart("file") MultipartFile file) {

    if (metadataErrors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid metadata");
    }
    // ... process valid file
    return ResponseEntity.ok().build();
}
```

This is also an **illustrative snippet**, not a standalone runnable example. `BindingResult` sits immediately after `metadata`, **before** `file`. Missing parts, oversized files, or multipart read failures have their own exception branches and do not become `FieldError`s on `metadata`.

### Comparison table

| Handler parameter | Uses adjacent `BindingResult` pair? | Typical errors |
| --- | --- | --- |
| `@Valid @ModelAttribute Form form` | Yes | Conversion + validation |
| `@Validated @ModelAttribute Form form` | Yes | Binding + group-based validation |
| `@Valid @RequestBody Dto dto` | Yes, for post-deserialization validation errors | Constraints on DTO |
| `@Valid @RequestPart Dto dto` | Yes, for validation of the parsed part | Constraints on metadata |
| `@RequestParam Integer page` | Not under this command-object rule | Missing parameter, type conversion |
| `@PathVariable Long id` | No | Path variable type conversion |
| `@RequestHeader String token` | No | Missing/invalid header per argument resolver |

Do not place `BindingResult` after `@RequestParam` expecting it to behave like `@ModelAttribute`. Each parameter type has its own `HandlerMethodArgumentResolver` and error-handling policy.

## 7. Spring MVC 6.1+ method validation: an important limitation

Starting in Spring Framework 6.1, Spring MVC includes **built-in method validation** for controllers with constraints placed directly on method parameters or return values, such as `@Min` or `@NotBlank`. When method validation is triggered, `HandlerMethodValidationException` may be thrown instead of `MethodArgumentNotValidException`.

Example:

```java
@GetMapping("/orders")
public String list(
        @Valid @ModelAttribute("filter") FilterForm filter,
        BindingResult filterErrors,
        @RequestParam @Min(1) int page) {
    // ...
    return "orders";
}
```

This illustrative example assumes `FilterForm` and imports exist. The `filter, filterErrors` pair is positioned correctly and can handle errors on `filter`. However, `@Min(1)` on `page` is a **method-level constraint** on another parameter. If `page` is invalid, Spring MVC may throw `HandlerMethodValidationException` and skip invoking the handler even though `filterErrors` is present.

Under the MVC contract, when method validation applies and `Errors`/`BindingResult` parameters are present, the handler **is invoked only if all validation errors belong to parameters that have an immediately following `Errors`**. Even a single error on a parameter without a local error slot is enough for the exception to be raised.

Distinction:

- **Standard object validation:** `@Valid @ModelAttribute`, `@Valid @RequestBody`, or `@Valid @RequestPart` on a command object; when no adjacent `BindingResult` exists and errors occur, `MethodArgumentNotValidException` is typically raised.
- **Direct method validation:** constraints on method parameters/return values; errors not fully captured at the handler raise `HandlerMethodValidationException`.
- `@Valid` itself is **not a direct constraint**. It only marks cascading onto the object. Adding `@NotNull` onto a `@Valid` parameter can trigger method validation.

Spring MVC 6.1+ recommends **omitting class-level `@Validated` on controllers** if you want to use built-in method validation. Class-level `@Validated` can activate the Spring AOP method validation path, with different exception types and interception points. A form's `BindingResult` does not automatically catch errors from AOP service/controller validation.

## 8. BindingResult in HTML forms and the view model

When returning data to a view so the user can fix errors, the model can hold both the object and its binding/validation result under a conventional key:

```text
org.springframework.validation.BindingResult.<attributeName>
```

For example, with `@ModelAttribute("order")`:

```text
org.springframework.validation.BindingResult.order
```

The prefix is provided by Spring via `BindingResult.MODEL_KEY_PREFIX`. A template engine like Thymeleaf can use `th:field` and `th:errors` to re-display values and field-specific errors:

```html
<!-- Thymeleaf fragment inside a form bound to the order object -->
<input type="text" th:field="*{itemCode}">
<div th:errors="*{itemCode}">Error message</div>
```

This is a **template fragment**, not a standalone HTML file. `BindingResult` also preserves information needed to re-display the value the user typed when a converter fails to produce a valid Java value.

For a REST API, map `FieldError` into a stable public error structure—such as `field`, `code`, `message`—instead of serializing the entire `BindingResult` directly; messages and input values can be sensitive.

## 9. Customizing and securing binding

A controller can add domain errors to the corresponding `BindingResult`:

```java
// Inside handler, after binding completes and basic errors are checked:
if (form.getItemCode() != null &&
        form.getItemCode().startsWith("FORBIDDEN-")) {
    errors.rejectValue(
        "itemCode", "invalidItemCode", "Item code is not allowed");
}

if (errors.hasErrors()) {
    return "orderForm";
}
```

This is an illustrative snippet. Do not execute queries or business logic with side effects if `errors.hasErrors()` is already `true` due to failed binding.

When designing web input objects:

- Prefer dedicated request DTOs rather than binding directly onto entities containing administrative fields or sensitive data.
- When using property binding, consider `WebDataBinder#setAllowedFields(...)` to restrict which properties clients may write.
- You can inspect `getSuppressedFields()` to see fields rejected by the binder; they **do not automatically become `FieldError`s** unless the application explicitly enforces that.
- Do not skip authentication/authorization, resource ownership checks, or critical business invariants simply because `BindingResult` is present.
- Do not expose `FieldError#getRejectedValue()` or raw `getArgument()` values from other mechanisms to untrusted clients.

## 10. Common errors and how to fix them

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `BindingResult` is present yet an exception is thrown before the handler runs | `Model` or another parameter sits between the object and result | Place `BindingResult` immediately after the bound argument |
| Two forms exist but errors are associated incorrectly | Each pair is not declared adjacently | `form1, errors1, form2, errors2` |
| Invalid request still returns HTTP 200 | Handler accepts errors without checking `hasErrors()` | Return a view/status reflecting the errors |
| Malformed JSON is not caught by `BindingResult` | Error occurs in the converter before validation | Handle `HttpMessageNotReadableException` separately |
| `@Min` does not reject `null` | `@Min` permits `null` | Add `@NotNull` when required |
| `hasErrors()` lacks expected constraints | Missing `@Valid`, provider, validator, or matching group | Check configuration and constraint metadata |
| `@RequestParam @Min` causes an error despite form's result | MVC method validation failed on another parameter | Handle `HandlerMethodValidationException` |
| Type conversion error causes service to receive invalid data | Result not checked before dispatching | Return early when `hasErrors()` is true |
| Error messages lack context or are hard to localize | Parsing exception strings/`getMessage()` or hardcoding | Use `FieldError`, message codes, and `MessageSource` |
| Form binds too many fields | DTO is too broad or binder permits mass assignment | Dedicated DTO, `allowedFields`, and server-side authorization |

## 11. Testing checklist

1. Valid request enters the controller and `result.hasErrors() == false`.
2. Empty string field with `@NotBlank` produces a validation error.
3. Numeric field receiving `"abc"` produces a binding/type mismatch error, without the handler treating it as a valid number.
4. With multiple objects, each `BindingResult` binds to the right object name.
5. Placing `Model` between an object and its result must be treated as a signature bug to fix, not a supported pattern.
6. `@Valid @RequestBody` receiving parseable JSON that violates constraints can be handled locally via the result.
7. Broken JSON: the controller cannot receive a DTO yet; converter errors go through the appropriate handler.
8. Direct constraints on another MVC parameter: test the `HandlerMethodValidationException` branch.
9. On error, business services are not called and success is not returned accidentally.
10. Rejected values or internal details are not exposed in public responses.

## 12. Summary

**`BindingResult` must be declared immediately after the bound and validated object, in matching pairs.** It collects errors associated with that command object so the controller can handle them locally, from type conversion errors to Bean Validation failures. Never insert `Model`, `Locale`, request objects, or a second command object between the two members of a pair.

Distinguish this from JSON/multipart parsing failures, standalone `@RequestParam` errors, and built-in method validation introduced in Spring MVC 6.1. Proper placement lets you receive the errors, while **choosing messages, HTTP status codes, views, and whether to proceed with business logic** remains the handler's design responsibility.

## References

- Spring Framework 6.2 — *Method Arguments*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework 6.2 — `@ModelAttribute` and `BindingResult` pairing: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@RequestBody` and local validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — *Validation*, `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring 6.2 Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/BindingResult.html
- Spring 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/FieldError.html