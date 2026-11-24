# Conversion Errors, Missing Parameters, and Validation

In Spring MVC, an HTTP request is converted into Java parameters before the controller executes business logic. Spring reads path variables, query parameters, headers, the body, and form data; it then performs type conversion, data binding, and validation as configured. If any step fails, the controller may never be invoked. Understanding which step raises an error helps you choose the right HTTP status, error format, and testing approach.

Three common error categories are:

- **Missing required data:** the client omits a request parameter, header, or body required by the endpoint.
- **Conversion/binding errors:** the data is present but cannot be converted to the Java type, such as sending `page=abc` when the controller expects `Integer page`.
- **Validation errors:** the data was read and bound successfully, but violates input rules, such as a quantity of 0 or a blank customer name.

These errors are typically returned as 4xx responses. The goal of the controller and exception handler is to explain the error clearly enough for the client to fix the request, while keeping the response structure stable so clients can handle it programmatically.

## 1. What Steps Does Spring Take to Process a Request?

A request passes through several components before reaching the controller body:

~~~text
HTTP request
    |
    v
HandlerMapping finds endpoint
    |
    v
HandlerMethodArgumentResolver reads each parameter
    |
    +--> Path variable / query parameter / header / cookie
    |
    +--> HttpMessageConverter reads request body
    |
    v
ConversionService / data binding converts types
    |
    v
Bean Validation checks constraints (if requested)
    |
    v
Controller method
    |
    v
Service / business logic
~~~

For example, with the following method:

~~~java
@PostMapping("/api/orders")
public OrderResponse create(
        @RequestParam String source,
        @RequestHeader("X-Client-Version") String clientVersion,
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Spring must locate the `source` request parameter, read the `X-Client-Version` header, convert the body into `CreateOrderRequest`, and run validation before invoking the method. If a required parameter is missing, the JSON is unreadable, or the object violates validation, the method body may not run at all.

Do not lump every failure under a single "validation error" concept. A conversion error means the data is not of the expected type; a validation error means the data has a valid type but violates a rule. The client-side fix differs, and the error codes should reflect that distinction.

## 2. Missing Request Parameters and Headers

### 2.1. Required Request Parameters

With `@RequestParam`, the `required` attribute defaults to `true`:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> findByStatus(
        @RequestParam("status") OrderStatus status) {
    return orderService.findByStatus(status);
}
~~~

Valid request:

~~~http
GET /api/orders?status=PAID
~~~

If a client sends `GET /api/orders` without the `status` parameter, Spring throws `MissingServletRequestParameterException`. Under Spring MVC's default handling, this is an invalid request and typically returns HTTP 400 Bad Request.

If a parameter is genuinely optional, declare that in the method signature:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam(name = "status", required = false)
        OrderStatus status) {
    return orderService.find(status);
}
~~~

With reference types, the value can be `null` when the client omits the parameter. `Optional` can be used to express presence/absence explicitly:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam Optional<OrderStatus> status) {
    return orderService.find(status.orElse(null));
}
~~~

Do not use `required = false` merely to make tests pass if the business logic truly requires that value. When data is mandatory, keep the mandatory contract and test the 400 response.

### 2.2. Default Values

If an endpoint has a sensible default value, use `defaultValue`:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> search(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return orderService.search(page, size);
}
~~~

When `defaultValue` is set, Spring treats the parameter as optional and uses the default value when the parameter is absent or empty. This is useful for pagination or filters with clear defaults. Do not arbitrarily assign defaults for identifiers or mandatory business fields, because a request missing information will silently turn into a different request that the client did not intend to send.

If you need to distinguish "not sent" from "sent an empty string", do not apply `defaultValue` mechanically; define the endpoint's policy and test both cases separately.

### 2.3. Required Headers

`@RequestHeader` also has a `required` attribute:

~~~java
@GetMapping("/api/profile")
public ProfileResponse profile(
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return profileService.findForTenant(tenantId);
}
~~~

A missing `X-Tenant-Id` header typically results in HTTP 400. If the header is optional, you can set `required = false` or `defaultValue` when a valid default exists. Authentication, tenant, or correlation headers defined by the system contract should not be replaced by query parameters or body fields just for testing convenience.

## 3. Data Type Conversion Errors

### 3.1. Query Parameters and Path Variables

Spring frequently converts string values from the URL into Java parameter types:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> search(
        @RequestParam int page,
        @RequestParam int size) {
    return orderService.search(page, size);
}
~~~

The request `?page=1&size=20` can be converted into two integers. However, `?page=first&size=20` cannot convert `first` into an `int`. Spring raises a conversion error, typically manifested as `MethodArgumentTypeMismatchException` and handled as HTTP 400.

Path variables also require type conversion:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderResponse get(@PathVariable UUID orderId) {
    return orderService.get(orderId);
}
~~~

If the path matches the route but the value is not a valid UUID, Spring cannot bind the parameter and the request typically receives 400. A path that does not match the route at all is a different situation and typically results in 404.

### 3.2. Enums

With an enum:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
~~~

A controller can accept it:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> find(
        @RequestParam OrderStatus status) {
    return orderService.findByStatus(status);
}
~~~

The value `status=PAID` is converted to `OrderStatus.PAID` by the default converter. Values like `status=paid` or `status=UNKNOWN` are not automatically valid; without a custom converter, they typically cause a conversion error and return 400.

Decide whether the contract is case-sensitive or case-insensitive. If the API accepts lowercase, write an explicit converter and test both valid and invalid values. Never catch the exception and fall back to an arbitrary default enum, as that turns an invalid request into a different business action.

### 3.3. Formatted Dates, Times, and Numbers

For query parameters or form fields, you can declare the format with `@DateTimeFormat`:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> findCreatedAfter(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return orderService.findCreatedAfter(date);
}
~~~

Clients send `?date=2026-11-13` in ISO date format. An improperly formatted string or invalid date can cause a conversion error. For locale-formatted numbers, `@NumberFormat` can be useful for forms or web apps; public APIs should generally use stable machine-readable formats, avoiding locale-dependent thousands/decimal separators.

For JSON bodies, reading dates and times is typically handled by Jackson and its modules, not the same mechanism used for query parameter conversion. Therefore, query parameter formats and JSON body formats may be configured in different layers. Tests must send the appropriate format for each location.

### 3.4. Avoid Primitives When Missing vs. Default Value Matters

An integer JSON field can be bound into:

~~~java
public record CreateOrderRequest(int quantity) {
}
~~~

If the `quantity` property is omitted from the JSON, the primitive value can become `0`. The application can then no longer distinguish a missing field from a client intentionally sending 0. If you need to distinguish them, use a reference type:

~~~java
public record CreateOrderRequest(
        @NotNull @Positive Integer quantity
) {
}
~~~

`@NotNull` requires the field to have a value; `@Positive` requires a number greater than 0. With a reference type, a request missing the field or sending `null` will be flagged by validation according to the contract. Note that most Bean Validation constraints treat `null` as valid unless `@NotNull` is also present; do not assume `@Positive` rejects null on its own.

## 4. Validation with Jakarta Bean Validation

### 4.1. Defining Constraints on Request DTOs

Spring MVC integrates Jakarta Bean Validation. With Spring Boot 3.x, the annotations reside in the `jakarta.validation.*` package:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 80)
        String customerName,
        @NotBlank
        String sku,
        @NotNull
        @Positive
        Integer quantity,
        @Email
        String contactEmail
) {
}
~~~

Some commonly used constraints:

| Constraint | Meaning |
|---|---|
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null, empty, or whitespace-only |
| `@NotEmpty` | String/collection/map/array must not be null or empty |
| `@Size(min, max)` | Limits length or element count |
| `@Positive` / `@PositiveOrZero` | Positive or non-negative number |
| `@Min` / `@Max` | Integer bounds |
| `@DecimalMin` / `@DecimalMax` | Decimal bounds |
| `@Email` | Checks email address syntax |
| `@Pattern` | Checks against a regular expression |
| `@Past` / `@Future` | Temporal constraints in the past or future |

Constraints should reflect actual input rules. For example, `@Email` checks address format rather than proving a mailbox exists; `@Pattern` should not replace a dedicated parser if the format is complex.

### 4.2. Triggering Validation with @Valid

For a request body:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity
                .created(URI.create("/api/orders/" + created.id()))
                .body(created);
    }
}
~~~

`@Valid` instructs Spring to validate the object after the body is converted into the DTO. If any constraint is violated and there is no `Errors` or `BindingResult` parameter immediately following the validated parameter, Spring throws `MethodArgumentNotValidException`. The controller method is not called, so the service is not executed.

For `@ModelAttribute`, Spring binds request parameters into the object and runs validation when `@Valid` or `@Validated` is present. Both type-binding errors and constraint errors can be recorded in `BindingResult`.

### 4.3. Nested Validation and Collections

If a DTO contains a child object, add `@Valid` to trigger cascading validation:

~~~java
public record AddressRequest(
        @NotBlank String line1,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}

public record CreateCustomerRequest(
        @NotBlank String name,
        @Valid @NotNull AddressRequest address,
        @NotEmpty List<@Valid ContactRequest> contacts
) {
}
~~~

Without `@Valid` on the nested property, constraints inside the child object may not be executed via cascade validation. For collections, you can use container element constraints like `List<@NotBlank String>` to validate each element, and `List<@Valid ContactRequest>` to validate each object.

### 4.4. @Valid and @Validated

`@Valid` is the standard Jakarta annotation for triggering cascade validation. `@Validated` is a Spring annotation that, in addition to triggering validation, supports specifying validation groups:

~~~java
public interface Create {}
public interface Update {}

public record UserRequest(
        @NotBlank(groups = {Create.class, Update.class})
        String name,
        @NotBlank(groups = Create.class)
        String initialPassword
) {
}
~~~

You can place `@Validated(Create.class)` on a parameter to run the corresponding group. Only introduce groups when creation and update rules genuinely differ; otherwise, group configuration complicates both DTOs and tests unnecessarily.

## 5. Method Parameter Validation and Spring Framework 6.1

In addition to validating DTOs with `@Valid @RequestBody`, Spring MVC can validate controller parameters directly:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> search(
        @RequestParam @Min(0) int page,
        @RequestParam @Min(1) @Max(100) int size) {
    return orderService.search(page, size);
}
~~~

Spring Framework 6.1 added built-in method validation support in Spring MVC. When parameters or return values of a handler method have constraints, Spring can throw `HandlerMethodValidationException` on violation. This differs from the conversion error `page=abc`: that case fails before a numeric value is created, whereas `page=-1` converts successfully but violates `@Min(0)`.

For controllers running on Spring MVC 6.1 or later, avoid placing class-level `@Validated` on the controller if you want to use Spring MVC's built-in method validation mechanism. Class-level `@Validated` can trigger method validation via an AOP proxy and alter the error handling path. Choose one mechanism deliberately to match your Spring version and test the actual exception produced.

Service-layer validation is a separate boundary. If a service uses method validation via a proxy, the error may be `ConstraintViolationException`. Do not treat every `ConstraintViolationException` as if it always came from an HTTP request; that exception can also originate from internal calls.

## 6. BindingResult and Handling Errors Directly in the Controller

When a controller needs to decide how to handle binding/validation errors itself, place `BindingResult` immediately after the validated parameter:

~~~java
@PostMapping("/web/orders")
public String submit(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult bindingResult,
        Model model) {

    if (bindingResult.hasErrors()) {
        return "orders/create";
    }

    orderService.create(form);
    return "redirect:/web/orders";
}
~~~

Spring only populates errors into `BindingResult` when this parameter sits immediately after the corresponding object. Placing another parameter in between can cause the exception to be thrown out and routed to an exception resolver.

For REST APIs, many applications let exceptions escape the controller and handle them centrally with `@RestControllerAdvice`. This keeps controllers focused on business logic and gives endpoints a uniform error structure. For HTML-returning MVC forms, returning the view along with error data in the model is usually more appropriate.

## 7. Distinguishing Common Exceptions

| Situation | Common exception | Typical default HTTP status |
|---|---|---|
| Missing `@RequestParam(required=true)` | `MissingServletRequestParameterException` | 400 |
| Missing `@RequestHeader(required=true)` | `MissingRequestHeaderException` | 400 |
| Query/path/header value cannot be converted | `MethodArgumentTypeMismatchException` | 400 |
| Malformed JSON, empty required body, or unreadable body | `HttpMessageNotReadableException` | 400 |
| `@Valid` DTO violates constraints | `MethodArgumentNotValidException` | 400 |
| `@ModelAttribute` binding/validation failure | `BindException` or corresponding validation error | 400 |
| Constraint directly on handler parameter in Spring MVC 6.1+ | `HandlerMethodValidationException` | 400 for input errors |
| `Content-Type` not supported by endpoint | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept` has no matching representation | `HttpMediaTypeNotAcceptableException` | 406 |

These are common cases, not a substitute for checking the actual configuration. Controller advices, custom converters, exception resolvers, and Spring versions can change the exception or response body. When diagnosing issues, inspect the underlying exception and active MVC configuration instead of guessing solely from the status code.

Several key distinctions:

- A missing required query parameter is different from sending a wrong-typed value for that query parameter.
- Malformed JSON is different from valid JSON whose field violates a constraint.
- A missing JSON field is generally not `MissingServletRequestParameterException`; it may become null or a default value in the DTO and then be checked by validation.
- `404 Not Found` typically indicates a missing route or resource, not a standard way to report all conversion errors.
- `415` means the submitted body format is unsupported; `406` means the server cannot produce a representation matching `Accept`.

## 8. Designing Stable Error Responses with @RestControllerAdvice

If every endpoint builds a different error JSON, clients must write many branches and easily become coupled to internal details. A unified error contract can include a stable error code, a displayable message, and a list of field-level errors.

Example error DTOs:

~~~java
public record ApiError(
        String code,
        String message,
        String path,
        List<FieldViolation> violations
) {
}

public record FieldViolation(
        String field,
        String code,
        String message
) {
}
~~~

An advice can map common errors:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MissingServletRequestParameterException.class)
    ResponseEntity<ApiError> missingParameter(
            MissingServletRequestParameterException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "MISSING_PARAMETER",
                "A required request parameter is missing.",
                request.getRequestURI(),
                List.of(new FieldViolation(
                        ex.getParameterName(),
                        "REQUIRED",
                        "This parameter is required."))
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "INVALID_PARAMETER",
                "A request parameter has an invalid value.",
                request.getRequestURI(),
                List.of(new FieldViolation(
                        ex.getName(),
                        "TYPE_MISMATCH",
                        "The value has an unsupported format."))
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validationFailed(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<FieldViolation> violations =
                ex.getBindingResult().getFieldErrors().stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getCode(),
                                error.getDefaultMessage()))
                        .toList();

        ApiError body = new ApiError(
                "VALIDATION_FAILED",
                "One or more request fields are invalid.",
                request.getRequestURI(),
                violations
        );
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> unreadableBody(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "INVALID_REQUEST_BODY",
                "The request body is missing or cannot be read.",
                request.getRequestURI(),
                List.of()
        );
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

This is a minimal example to illustrate the mapping pattern. Real applications must standardize error codes, message wording, localization, and handling for all exception types exposed by the API. For validation errors, field errors can be extracted from `BindingResult`; avoid echoing raw rejected values in the response because those values could be passwords, tokens, or personal data.

If you want to customize standard Spring MVC exceptions while retaining full default handling behavior, you can extend `ResponseEntityExceptionHandler` and override the relevant hooks such as validation, missing parameter, or type mismatch handling. Note that this class already handles many MVC exceptions; do not declare duplicate handlers for the same exception in a way that causes mapping conflicts. With Spring's `ProblemDetail` support, you can use the problem detail structure to standardize error responses in your chosen system format.

Never return stack traces, internal class names, SQL, file paths, or configuration details in public responses. Technical details should be logged on the server alongside a correlation ID for operations teams to investigate.

## 9. Testing Missing Parameters and Conversion Errors with MockMvc

`MockMvc` allows sending missing or malformed data just like a real client:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsBadRequestWhenRequiredStatusIsMissing() throws Exception {
        mockMvc.perform(get("/api/orders/by-status"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("status"));

        then(orderService).shouldHaveNoInteractions();
    }

    @Test
    void returnsBadRequestWhenPageCannotBeConverted() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .param("page", "first"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("page"));

        then(orderService).shouldHaveNoInteractions();
    }
}
~~~

The endpoint paths and response structure in the example must match your application's controller and advice. If the application uses a different error response, adjust the JSONPath expressions to match that contract. What matters is verifying the status, error code, failing field, and that the controller does not invoke the service when the request is invalid.

For dates or enums, test invalid values in the same way:

~~~java
mockMvc.perform(get("/api/orders")
        .param("date", "31-31-2026"))
    .andExpect(status().isBadRequest());

mockMvc.perform(get("/api/orders/by-status")
        .param("status", "UNKNOWN"))
    .andExpect(status().isBadRequest());
~~~

Do not assert only status 400. If the error contract is part of the API, assert both the error code and the field. This helps catch accidental changes to exception mapping that would prevent clients from recognizing the error.

## 10. Testing Request Body Validation

A test can send syntactically valid JSON that violates constraints:

~~~java
@Test
void rejectsInvalidOrderFields() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "   ",
                              "sku": "COFFEE-01",
                              "quantity": 0,
                              "contactEmail": "not-an-email"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[*].field",
                    hasItems("customerName", "quantity", "contactEmail")));

    then(orderService).shouldHaveNoInteractions();
}
~~~

Distinguish this test from syntactically invalid JSON:

~~~java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_REQUEST_BODY"));
}
~~~

The first test proves Jackson successfully parsed the JSON into the DTO, but Bean Validation rejected the data. The second test proves the body could not be parsed into an object. Both errors may share status 400, yet they should have distinct error codes or details so the client knows how to fix the request.

For required fields, test at least three cases: field absent, field set to `null`, and field set to an empty value. Depending on the DTO and Jackson configuration, binding behavior may differ. For primitive fields, also check whether default values could mask a missing field.

## 11. Testing BindingResult in MVC Forms

For a form controller, you can assert both the redisplayed page and the model errors:

~~~java
@WebMvcTest(OrderFormController.class)
class OrderFormControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void redisplaysFormWhenQuantityCannotBeConverted() throws Exception {
        mockMvc.perform(post("/web/orders")
                        .param("sku", "COFFEE-01")
                        .param("quantity", "many"))
                .andExpect(status().isOk())
                .andExpect(view().name("orders/create"))
                .andExpect(model().attributeHasFieldErrors(
                        "form", "quantity"));
    }
}
~~~

Here Spring cannot convert the string `many` into the numeric type of the `quantity` field. The error is recorded in `BindingResult` and the controller returns the view so the user can correct it. If the form controller lacks `BindingResult` immediately after the model attribute, the exception may go through an exception resolver and return an error page instead of rendering the form as expected.

For REST APIs, do not return view names. Use structured JSON responses with appropriate HTTP statuses.

## 12. Errors in MVC Asynchronous Requests

In Spring MVC, a controller can return `Callable`, `DeferredResult`, or `CompletionStage` to complete the response after asynchronous processing. Distinguish input errors from errors occurring inside the asynchronous task:

~~~text
HTTP request
    |
    v
Bind parameters + read body + validation
    |
    +--> input error: exception resolver returns error response
    |
    v
Controller returns Callable / DeferredResult
    |
    v
Async task runs
    |
    +--> success: async dispatch to write response
    |
    +--> exception: async dispatch, exception resolver handles error
~~~

Example:

~~~java
@GetMapping("/api/reports")
public Callable<ReportResponse> report(
        @RequestParam
        @Pattern(regexp = "daily|weekly|monthly")
        String period) {

    return () -> reportService.generate(period);
}
~~~

Validation of `period` happens when Spring prepares to invoke the controller method. If the value is invalid, the controller never creates a `Callable` and does not start background work. If the method returns a valid `Callable` but `reportService.generate(...)` throws an exception while running, Spring MVC completes the async cycle and re-dispatches the request so exception handling can process the error. The error handler must be able to map errors that occur after the controller has already returned.

If using Spring MVC 6.1's built-in method validation, constraint errors directly on handler parameters may be represented by `HandlerMethodValidationException`. If using `@Valid @RequestBody` only, DTO errors are typically `MethodArgumentNotValidException`. Test the actual exception according to your controller signature and framework version.

### 12.1. Testing Async Dispatch

With `MockMvc`, the first call may only confirm that the request started asynchronous processing. You need to capture `MvcResult` and then use `asyncDispatch(...)` to assert the final response:

~~~java
MvcResult result = mockMvc.perform(get("/api/reports")
                .param("period", "daily"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.period").value("daily"));
~~~

When testing an error from the background task, stub the service to throw an exception and assert the status and error contract after async dispatch:

~~~java
given(reportService.generate("daily"))
        .willThrow(new ReportGenerationException("report unavailable"));

MvcResult result = mockMvc.perform(get("/api/reports")
                .param("period", "daily"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("REPORT_UNAVAILABLE"));
~~~

This test assumes the application advice maps `ReportGenerationException` to 503. For input validation errors, do not expect `asyncStarted()` because the controller has not returned an async task; assert status 400 directly on the first request.

## 13. When to Use 400, 404, 409, 415, and 422?

The status must reflect the problem category per the API contract:

| Status | Use when | Example |
|---|---|---|
| 400 Bad Request | Request is missing required data, malformed, wrong type, or fails input validation | page=abc, missing status, non-positive quantity |
| 404 Not Found | Requested route or resource is not found | No order exists with that id |
| 409 Conflict | Request is syntactically valid but conflicts with current state | Order code already exists or state forbids update |
| 415 Unsupported Media Type | Endpoint does not support the Content-Type | Sending XML to a JSON-only endpoint |
| 406 Not Acceptable | Server cannot produce a response matching Accept | Client only accepts an unsupported representation |
| 422 Unprocessable Content | API explicitly distinguishes syntactically valid content that cannot be processed under business rules | Some APIs use it for domain validation errors |

There is no mandatory rule that every validation error must be 422. Spring MVC commonly uses 400 for binding and Bean Validation errors. If a product chooses 422 for a group of business errors, document it clearly in the API contract and apply it consistently. Never change a status code solely because a test expects a different number.

## 14. Common Design and Testing Mistakes

- **Catching every exception and returning 400:** database errors, programming bugs, or dependency failures are not bad client requests. Mis-mapping statuses makes it hard for clients to tell whether to fix the request or retry.
- **Returning raw exception messages:** messages can include class names, rejected values, SQL, or internal details. Craft safe messages for clients and log details on the server.
- **Using primitives for fields that must distinguish missing from 0:** an absent field can become a default value. Use wrapper types with appropriate constraints.
- **Assuming @Positive also catches null:** many Bean Validation constraints allow null. Combine with `@NotNull` if the field is required.
- **Confusing conversion errors with validation errors:** `page=abc` cannot be bound to a number; `page=-1` binds but violates a range constraint.
- **Forgetting @Valid:** constraints on a DTO do not run automatically just because the DTO has annotations. Ensure the controller triggers validation.
- **Misplacing BindingResult:** it must sit immediately after the parameter being bound/validated.
- **Testing only the status code:** error codes, fields, and response structure are also part of the API contract.
- **Using defaultValue to mask missing required data:** only set defaults when the domain genuinely has a default value.
- **Testing only the synchronous path:** exceptions inside `Callable`/`DeferredResult` must be tested via async dispatch.
- **Echoing rejected values in error responses:** this can leak sensitive data; return only field names and appropriate messages.

## 15. Testing Workflow for Each Error Type

When adding or modifying an endpoint, you can build a test suite in sequence:

1. Send a valid request to verify the endpoint works.
2. Omit a required parameter/header and assert the missing-data error code.
3. Send an unconvertible value, such as a string for a number or a nonexistent enum value.
4. Send malformed JSON or an empty body to test the message converter.
5. Send syntactically valid JSON that violates constraints.
6. Assert field errors, error code, and status according to the contract.
7. Verify the service is not invoked when the error occurs before the controller/service.
8. For async endpoints, test both errors before async starts and exceptions after async dispatch.
9. Verify the response does not leak rejected values or internal details.

A good request-error test proves more than just that Spring returns 400. It shows which data was rejected, at which step the failure occurred, what the client must fix, and whether the application prevents business logic from running with invalid data.
