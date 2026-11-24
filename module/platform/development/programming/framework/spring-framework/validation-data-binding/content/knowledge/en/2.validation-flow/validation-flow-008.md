# Reading Validation Results and Deciding Whether to Proceed with Business Logic

In Spring Framework, binding data into a Java object **does not mean the data is valid**, and an object passing validation **does not mean the business operation is definitely permitted**. At the end of the input-processing flow, the application must read the results, block the invalid branch, and only then invoke the state-changing use case or service.

This article aims to answer three questions: **where to read the result**, **what to read**, and **how to decide whether to stop or proceed based on that result**. The scope is Spring Validation/Data Binding (specifically `DataBinder`, `Errors`, `BindingResult`, and Spring MVC); deeper business rules still belong to the application/domain layer.

## 1. Processing Order and Decision Boundaries

~~~text
User input
    |
    v
Decode/read request and bind into DTO (may produce type conversion errors)
    |
    v
Apply appropriate validators (may produce constraint errors)
    |
    v
Read Errors / BindingResult
    |
    +-- Has errors? -- Yes --> Return suitable error response; STOP write use case
    | 
    +-- No
          |
          v
    Check business rules and authorization
          |
          +-- Not met --> Reject with appropriate business outcome
          |
          +-- Met --> Execute service / transaction --> Return success result
~~~

Distinguish between:

- **Read/conversion errors**: the string `"abc"` cannot be converted to `Integer`, JSON is malformed, or the request format is invalid. Not every error reaches the same `BindingResult`: a JSON decoding failure can prevent the controller from even being invoked.
- **Validation errors**: data was readable, but violates constraints such as required fields, length, value range, or cross-field relationships. These are typically recorded as `FieldError` or `ObjectError`.
- **Business/authorization errors**: input is structurally valid, but inventory is exhausted, a code already exists in the system, a quota is exceeded, permissions are insufficient, or the order state forbids the operation. These must be checked at the proper layer rather than turning everything into input errors by default.

Core principle: **only invoke branches with side effects after all input errors have been handled**. Reading a DTO or calling getters is safe; saving to the DB, sending emails, deducting funds, publishing events, or calling write APIs before checking for errors causes hard-to-undo consequences.

## 2. Reading `BindingResult` Correctly

`org.springframework.validation.Errors` provides error checks and error inspection; `BindingResult` extends `Errors`, typically supplied by `DataBinder` or Spring MVC. After calling `binder.bind(...)` and `binder.validate()`, retrieve the result via `binder.getBindingResult()`. In MVC, declare a `BindingResult` or `Errors` parameter **immediately after** the parameter being bound/validated.

| API | Meaning and usage |
| --- | --- |
| `hasErrors()` | Primary decision gate: if there is at least one bind/validation error, do not execute the use case. |
| `getErrorCount()` | Total error count; useful for metrics/observation, not a substitute for individual error details. |
| `getFieldErrors()` / `getFieldError("quantity")` | Errors tied to fields; provides field name, error code, and default message. |
| `getGlobalErrors()` | Object-level errors, such as an invalid start/end date range. |
| `getAllErrors()` | Combines field errors and object-level errors when building a response. |
| `hasFieldErrors("quantity")` | Quick check for whether a specific field has errors, e.g., to highlight under its input. |
| `getSuppressedFields()` | List of fields excluded from binding when binding restrictions apply; inspect separately, do not treat as equivalent to `hasErrors()`. |

`FieldError` extends `ObjectError`. `getCode()` returns the specific error code; `getCodes()` may hold multiple codes in priority order for locale-based message lookup; `getDefaultMessage()` is the default message, which can be `null`. Do not couple business flow to localized message text; use meaningful codes/statuses while reserving messages for users.

`hasErrors()` is a sufficient condition to **block proceeding**, but `!hasErrors()` only tells you that **the checks that actually ran** reported no errors. It does not by itself guarantee access rights, DB uniqueness, or business invariants.

## 3. Runnable Java 17 Example: Two Branches from One Result

This example uses Spring `DataBinder` directly, with no HTTP server needed. The input handler binds `customer` and `quantity`, runs `OrderValidator`, checks `BindingResult`, and only then allows `OrderService` to save. Project structure:

~~~text
validation-decision/
├── pom.xml
└── src/main/java/demo/ValidationDecisionDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-decision</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.ValidationDecisionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/demo/ValidationDecisionDemo.java`:

~~~java
package demo;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationDecisionDemo {
    public static final class OrderInput {
        private String customer;
        private Integer quantity;

        public String getCustomer() {
            return customer;
        }

        public void setCustomer(String customer) {
            this.customer = customer;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static final class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return OrderInput.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderInput input = (OrderInput) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "customer", "customer.required",
                    "Customer name is required");

            if (input.getQuantity() == null || input.getQuantity() <= 0) {
                errors.rejectValue(
                        "quantity", "quantity.positive",
                        "Quantity must be greater than 0");
            }
        }
    }

    public static final class OrderService {
        private int saved;

        public void create(OrderInput order) {
            saved++;
            System.out.println(
                    "SAVED: " + order.getCustomer() + " x" + order.getQuantity());
        }
    }

    private static void handle(Map<String, String> raw, OrderService service) {
        OrderInput input = new OrderInput();
        DataBinder binder = new DataBinder(input, "order");
        binder.setValidator(new OrderValidator());

        binder.bind(new MutablePropertyValues(raw));
        binder.validate();

        BindingResult result = binder.getBindingResult();
        if (result.hasErrors()) {
            System.out.println("REJECTED: " + result.getErrorCount());
            result.getFieldErrors().forEach(error ->
                    System.out.println(
                            error.getField() + ": " + error.getDefaultMessage()));
            return; // Do not call the service when data is invalid.
        }

        service.create(input);
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();

        handle(Map.of("customer", "Mai", "quantity", "2"), service);
        handle(Map.of("customer", "   ", "quantity", "0"), service);

        System.out.println("TOTAL_SAVED=" + service.saved);
    }
}
~~~

With **JDK 17+** and **Maven** inside the `validation-decision` directory, run:

~~~bash
mvn -q compile exec:java
~~~

Standard output:

~~~text
SAVED: Mai x2
REJECTED: 2
customer: Customer name is required
quantity: Quantity must be greater than 0
TOTAL_SAVED=1
~~~

Step-by-step explanation:

1. `DataBinder` converts the string `"2"` to `Integer` and sets properties via setters; then `validate()` calls `OrderValidator`. Without calling `validate()` in this manual example, `OrderValidator`'s rules are not checked.
2. The first call has no errors, so `service.create(input)` executes once.
3. The second call has whitespace-only `customer` and `quantity = 0`, so the validator registers two `FieldError`s. The `return` statement cuts off the branch, preventing `service.create(...)`.
4. `TOTAL_SAVED=1` illustrates the invariant to protect: rejected input creates no extra record. `OrderService` here only counts and prints to stdout; in a real application, DB persistence occurs inside the service/transaction.

If the quantity string fails conversion (for example `"abc"`), binding may register a `typeMismatch` error in `BindingResult`. When writing validators, account for properties potentially still being `null` and avoid dereferencing them in a way that causes `NullPointerException` or duplicate error messages. Normally, only proceed to business logic if **all** binding and validation errors have been cleared.

## 4. Decision Branches in Spring MVC

For HTML forms (bound into `@ModelAttribute`), the standard handling is to **return the form with errors** and not invoke the service:

~~~java
// Excerpt from a @Controller; OrderForm and orderService
// are defined in the rest of the application.
@PostMapping("/orders/form")
public String submit(@Valid @ModelAttribute("order") OrderForm form,
                     BindingResult result) {
    if (result.hasErrors()) {
        return "orders/form";
    }
    orderService.create(form);
    return "redirect:/orders";
}
~~~

The mandatory requirement of that method signature is that `BindingResult` sits **immediately after** `@Valid @ModelAttribute("order") OrderForm`. Templates can read field errors to highlight invalid fields and preserve valid entered values. Returning the form view is a controller choice, not automatic behavior of `BindingResult`.

For REST JSON, you can intercept at the controller and return a structured `400 Bad Request` instead of proceeding to create the resource:

~~~java
// Illustrative excerpt; requires Spring MVC, a Bean Validation provider,
// OrderApplicationService, and corresponding imports in the application.
record CreateOrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer quantity) {}

record InputIssue(String field, String message) {}

@RestController
class OrderController {
    private final OrderApplicationService service;

    OrderController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest input,
                             BindingResult result) {
        if (result.hasErrors()) {
            var issues = result.getAllErrors().stream()
                    .map(error -> new InputIssue(
                            error instanceof FieldError field
                                    ? field.getField() : "_global",
                            error.getDefaultMessage()))
                    .toList();
            return ResponseEntity.badRequest().body(issues);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(input));
    }
}
~~~

`@Valid` requires a configured Bean Validation provider (with Spring Boot 3.x, typically the `spring-boot-starter-validation` dependency). Annotations in the example use the `jakarta.validation.*` namespace. The REST sample above is an **illustrative controller snippet**, not a standalone runnable Java file; the `DataBinder` example in section 3 is the complete runnable program.

With `@Valid @RequestBody` or `@Valid @ModelAttribute`, if no adjacent `Errors`/`BindingResult` parameter is declared and single-parameter validation fails, Spring MVC usually throws `MethodArgumentNotValidException`; by default, request body validation failures result in HTTP 400. You can handle it consistently with `@RestControllerAdvice` and `@ExceptionHandler`. If constraints are declared directly on method parameters so **method validation** applies, Spring MVC may throw `HandlerMethodValidationException`; centralized error handling must account for both cases.

A request containing malformed JSON, a field whose value cannot deserialize to its target type, or a missing body when required can fail **before the controller receives `BindingResult`** (e.g., `HttpMessageNotReadableException`). Therefore, an "`if (result.hasErrors())`" check inside the controller does not replace exception handling at the request mapping/conversion layer.

## 5. Which Decisions Belong to Validation, and Which Belong to Business Logic?

`BindingResult` itself records check/binding errors; it is **not a free pass for every operation**. Separate handling into clear layers:

| Situation | Decision | Typical handling location |
| --- | --- | --- |
| Missing `customer` or `quantity <= 0` | Stop; return per-field errors | Bean Validation/Spring `Validator`, controller |
| String `quantity = "abc"` fails to bind | Stop; report data type error | Binding/conversion or JSON conversion handler |
| `startDate > endDate` | Stop; return object-level or related field error | Multi-field validator |
| Valid data, but product is out of stock | Do not create order; return business conflict/unmet condition | Application/domain service |
| Code must be unique, but collides under concurrent requests | Reject conflicting operation; enforce constraint in DB | Domain/service + unique constraint/transaction |
| User is not authorized to create order | Reject per authentication/authorization rules | Security/application service |

HTTP 400 is the common choice for invalid requests. HTTP 409 is often reasonable for state/uniqueness conflicts; HTTP 403 for insufficient permissions; HTTP 422 may be agreed upon for certain semantic request errors. Codes 409/422 are **application API policies**, not statuses Spring Validation automatically infers from `hasErrors()`.

If a validator checks external data (e.g., querying the DB to verify an account name does not exist yet), you must still enforce the necessary constraints and checks at the service/DB layer: "not duplicate" at validation time may no longer hold at write time. Transactions help protect certain invariants, though exact conflict handling depends on the storage layer.

## 6. Designing Error Responses So Callers Can Fix Inputs

An API should return errors with a stable structure, for example:

~~~json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "customer",
      "code": "customer.required",
      "message": "Customer name is required"
    },
    {
      "field": "quantity",
      "code": "quantity.positive",
      "message": "Quantity must be greater than 0"
    }
  ]
}
~~~

This is an **application contract sample**, not a default body generated automatically by Spring. For object-level errors, you can use `field: null` or a convention like `"_global"` and document that convention for the frontend. Keep `code` stable for programmatic handling; `message` can be localized. Do not expose stack traces, internal class names, secrets, or full rejected values in responses.

For forms, the goal is to re-render inputs and attach messages to the right fields. For REST, the goal is an accurate status, stable error codes, and an error list detailed enough for the client to know what to fix. In both cases, **guaranteeing no side effects occur before the rejection branch** matters more than formatting.

## 7. Common Implementation Mistakes

- **Binding without validating**: in manual `DataBinder` flows, `binder.bind(...)` does not substitute for `binder.validate()`; `hasErrors() == false` then only indicates binding reported no errors.
- **Misplacing `BindingResult`**: in Spring MVC, `BindingResult` must sit right after its corresponding object. Otherwise, the controller may not capture errors as expected.
- **Calling the service before checking `hasErrors()`**: can mutate state or emit events even though the final HTTP response reports an error.
- **Checking only `getFieldErrors()`**: misses `getGlobalErrors()` from cross-field constraints; use `getAllErrors()` when responses need complete error coverage.
- **Equating "valid" with "authorized/business success"**: validation does not replace permission, state, inventory, and DB invariant checks.
- **Assuming every bad request reaches the controller**: body-reading/JSON conversion failures can occur earlier and require exception handlers.
- **Using `getDefaultMessage()` as a status code**: that string can change due to localization; use explicit codes/statuses.
- **Logging entire `getRejectedValue()` or raw requests**: can leak passwords, tokens, or personal data; log only minimal information with sensitive data redacted.
- **Binding all entity properties directly**: creates risk of modifying unintended fields. Use dedicated DTOs, restrict bindable fields when appropriate, and map in a controlled way to domain models.

## 8. Testing a Complete Flow

When testing a controller/use case, observe both **the returned result** and **the count of side effects**:

| Input/condition | Expected result | Is write service called? |
| --- | --- | --- |
| Well-formed, passes validation, permitted to execute | Success, e.g., `201 Created` on creation | Yes, exactly once |
| Missing required field | Field error, typically `400` | No |
| Wrong type or unreadable JSON body | Input/conversion error, typically `400` | No |
| Invalid relationship between fields | Object/field-level error, typically `400` | No |
| Passes validation but violates business invariant | Business rejection result, e.g., `409` | No success state created |
| Two operations racing on a unique value | One succeeds, the other receives an appropriate conflict | No duplicate record |

You can mock the service to assert `verifyNoInteractions(service)` in invalid-input branches; in integration tests, verify the DB remains unchanged. This directly confirms the purpose of the "read result and decide" step: **errors are stopped before business logic executes**.

## 9. Takeaways When Applying

A reliable implementation order is **bind → validate → read `BindingResult` → stop if errors exist → check business rules/permissions → execute**. In controllers, the rejection branch must appear before service calls; in services, business invariants must remain enforced even after requests pass validation. When the controller is not invoked due to conversion errors or method validation errors, let exception handlers respond consistently.

Official Spring documentation for API details and activation conditions:

- [Validation and `DataBinder`](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [`@ModelAttribute` and `BindingResult` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [`@RequestBody` and validation error handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Distinguishing argument validation and method validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
