# Distinguishing Binding Errors, Bean Validation Errors, and Business Errors in Spring Boot

## 1. Three Distinct Data Processing Layers

An incoming HTTP request in Spring Boot can fail at three independent layers:

1. **Binding, conversion, deserialization:** the framework cannot extract or convert HTTP data into the Java values requested by the controller. For example, query parameter seats=abc when the parameter is int, or JSON containing seats="many" when the DTO expects Integer.
2. **Bean Validation:** the framework constructed data of the appropriate types, but the data violates constraints such as @NotBlank, @NotNull, @Min, @Size, or a custom constraint. For example, seats=0 converts to Integer successfully but violates @Min(1).
3. **Business errors:** the data is of valid types and satisfies constraints, yet violates the current domain state. For example, an event is sold out, an email already exists, inventory is insufficient, or an order is already canceled.

General flow:

~~~text
HTTP request
    |
    v
Route, method, Content-Type, HTTP body
    |
    v
Binding / type conversion / JSON deserialization
    |---- fails ----> typically 400
    v
Bean Validation / method validation
    |---- fails ----> typically 400
    v
Service / domain rules
    |---- conflict ---> 409 or other status per API contract
    v
Transaction / persistence / response
~~~

**Not every HTTP 400 is Bean Validation.** Syntactically invalid JSON cannot reach @Min if the DTO cannot be constructed; whereas 0 is a valid Integer that can violate a constraint. Similarly, input satisfying @Min may still be rejected due to insufficient inventory.

This lesson uses **Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Validation, and Java 17+**. The full example uses Spring MVC/Servlet, and the end includes a comparison table with WebFlux.

## 2. Comparing the Three Error Types by Scenario

Suppose POST /api/bookings receives JSON:

~~~json
{"eventId":"EVENT-10","seats":2}
~~~

The DTO requires eventId to be non-blank and seats to be at least 1. The service rules that eventId "sold-out" has no seats left.

| Input / Condition | Error Category | Cause | HTTP in Example API |
|---|---|---|---|
| seats="many" | JSON decode/type conversion | String cannot be converted to Integer | 400 |
| Body missing JSON brace | JSON parse | Malformed body syntax | 400 |
| seats=0 | Bean Validation | Violates @Min(1) | 400 |
| seats=null or omitted | Bean Validation | Violates @NotNull | 400 |
| eventId="" | Bean Validation | Violates @NotBlank | 400 |
| eventId="sold-out", seats=2 | Business rule | Valid data, but sold out | 409 |
| eventId="EVENT-10", seats=2 | Success | Passed all three layers | 201 |

Do not infer the failing layer solely from the status code. Both are 400, yet the client must fix the type or format for a binding error, whereas a validation error requires adjusting field values to satisfy constraints.

**Important exception:** A BindingResult can contain both a FieldError from binding failure and a FieldError from a constraint. Therefore, you cannot classify the entire error response purely from the exception name without inspecting the details inside.

## 3. Binding, Conversion, and Deserialization

Spring reads HTTP input from @PathVariable, @RequestParam, @RequestHeader, @CookieValue, @ModelAttribute, or @RequestBody. The framework then converts types via the appropriate ConversionService, PropertyEditor, HttpMessageConverter, or HttpMessageReader.

Example:

~~~java
@GetMapping("/estimate")
public Map<String, Integer> estimate(@RequestParam int seats) {
    return Map.of("estimatedCost", seats * 100);
}
~~~

GET /estimate?seats=abc cannot convert "abc" to int. With Spring MVC and a simple @RequestParam, this situation normally results in MethodArgumentTypeMismatchException and HTTP 400. The controller method is not invoked.

GET /estimate?seats=-1 is different: "-1" converts to int successfully. Without @Min or explicit checks, the parameter still reaches the method body. A negative value is **not a binding error** simply because it does not match business intent.

### HTTP Input Errors to Distinguish

| Scenario | Typical MVC Exception | Typical HTTP |
|---|---|---|
| @RequestParam cannot convert type | MethodArgumentTypeMismatchException | 400 |
| Missing required @RequestParam | MissingServletRequestParameterException | 400 |
| Malformed JSON syntax, field cannot decode | HttpMessageNotReadableException | 400 |
| Required @RequestBody is missing | HttpMessageNotReadableException | 400 |
| Unsupported Content-Type | HttpMediaTypeNotSupportedException | 415 |
| Unsupported HTTP method | HttpRequestMethodNotSupportedException | 405 |
| Cannot produce response per Accept | HttpMediaTypeNotAcceptableException | 406 |

These cases occur before business logic. However, they are not the same kind of validation either. Do not catch all of them and return a generic "Invalid data" message if API clients need concrete details to fix their requests.

### @ModelAttribute Can Record Type Conversion Errors in BindingResult

For a form/query object, WebDataBinder binds each field and collects errors. Example class:

~~~java
public class SearchForm {
    private Integer minSeats;

    public Integer getMinSeats() {
        return minSeats;
    }

    public void setMinSeats(Integer minSeats) {
        this.minSeats = minSeats;
    }
}
~~~

Illustrative controller:

~~~java
@GetMapping("/search")
public ResponseEntity<?> search(
        @ModelAttribute SearchForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(error -> error.getField())
                        .toList());
    }
    return ResponseEntity.ok(form);
}
~~~

These are two illustrative snippets requiring imports and classes in an application, not a standalone Java file. With /search?minSeats=abc, a typeMismatch error can be recorded in BindingResult; the handler can explicitly return HTTP 400.

**BindingResult must be placed immediately after the parameter it tracks.** Placing it after an unrelated parameter does not guarantee Spring associates it with the intended target.

## 4. Distinguishing FieldErrors from Binding vs. Validation

Spring FieldError holds metadata about a failing field. Useful methods:

- getField(): field name.
- getCode()/getCodes(): error codes per Spring's MessageCodesResolver mechanism.
- getDefaultMessage(): default message.
- isBindingFailure(): **true** when the error is a binding failure such as typeMismatch; **false** when caused by validation.
- getRejectedValue(): the rejected input value, which may be sensitive—**do not put it directly into HTTP responses or logs**.

Example:

~~~java
for (FieldError error : result.getFieldErrors()) {
    String kind = error.isBindingFailure()
            ? "binding"
            : "constraint";
    System.out.println(error.getField() + ": " + kind);
}
~~~

This code requires importing org.springframework.validation.FieldError. It is a reliable way to distinguish error details when BindingResult holds multiple kinds of errors.

**A MethodArgumentNotValidException does not necessarily contain only Bean Validation errors.** In some object binding flows, both type conversion errors and constraint violations appear in the result. Conversely, @RequestBody with invalid JSON syntax usually cannot construct the DTO and leads to HttpMessageNotReadableException at the decoding step.

## 5. What Is Bean Validation?

Jakarta Bean Validation allows declaring constraints on DTOs, method parameters, properties, and return values. With Spring Boot 3.5, add the validation starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Use the jakarta.validation package, not javax.validation on Spring Boot 3.x.

Example DTO:

~~~java
public record CreateBookingRequest(
        @NotBlank String eventId,
        @NotNull @Min(1) Integer seats
) {}
~~~

- @NotBlank is for CharSequence, checking null, empty, or whitespace-only.
- @NotNull forces a reference to be non-null.
- @Min(1) requires the number to be at least 1; null alone does not violate @Min, so add @NotNull if the field is required.
- @Size checks length or element count of supported types; **not equivalent to byte request size**.
- @Email checks format, without proving the email can receive mail or does not already exist in the database.
- @Valid triggers cascade validation for child objects when appropriate; **@Valid itself is not a constraint**.

Bean Validation fits conditions verifiable from the input/DTO: requiredness, length, range, format, nested constraints, and cross-field relationships via properly written custom constraints.

It does not know inventory state, bank balances, sold-out events, or concurrent transactions updating the same data. Those rules belong to the service/domain and usually require transactions or database constraints.

## 6. Object Validation and Method Validation in Spring MVC 6.2

Modern Spring MVC has two primary validation paths:

**Object validation** is normally triggered when an @ModelAttribute, @RequestBody, or @RequestPart uses @Valid/@Validated appropriately, and no direct method constraints switch the validation path. The error is usually MethodArgumentNotValidException (or supplied via BindingResult if declared right next to it).

~~~java
@PostMapping("/bookings")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateBookingRequest request) {
    return ResponseEntity.ok().build();
}
~~~

**Method validation** applies when @Min, @NotBlank, or other constraints are placed directly on controller method parameters or return values. Spring MVC 6.1+ has built-in support. The error is usually HandlerMethodValidationException.

~~~java
@GetMapping("/guarded-estimate")
public Map<String, Integer> guardedEstimate(
        @RequestParam @Min(1) int seats) {
    return Map.of("estimatedCost", seats * 100);
}
~~~

GET /guarded-estimate?seats=0 succeeds at int conversion, then violates the method constraint.

**Two easy mistakes:**

1. @Valid on a DTO does not guarantee every error will be MethodArgumentNotValidException. If the method has other direct constraints, method validation may cover nested constraints too.
2. Class-level @Validated on a controller can trigger the older AOP-based method validation, taking a different exception path from built-in controller validation. When using built-in 6.2 method validation, check upgrade guides and remove class-level @Validated on controllers where appropriate.

HandlerMethodValidationException.getStatusCode() is normally **400 for input constraint violations** and **500 for return-value constraint violations**. A server returning a response that violates its own constraint is not the client request's fault.

## 7. Business Errors Belong to the Service/Domain Layer

A request with valid eventId and seats formats can still be rejected:

- Event is sold out.
- Customer already made a duplicate booking.
- Order is canceled or already delivered.
- Insufficient balance.
- Insufficient stock when concurrent transactions execute.
- Voucher is syntactically valid but expired.
- Resource state does not permit the operation.

Example:

~~~java
if (event.isSoldOut()) {
    throw new BookingConflictException(
            "Event is fully booked");
}
~~~

This illustrative snippet requires event and a domain-defined exception class. Do not turn every stateful rule into a custom @Constraint that queries the database. State can change between validation and commit, creating a race condition.

**Recommended layering:** request DTOs and Bean Validation protect the input contract; service/domain protects invariants; database unique constraints, locking, or transactions protect against concurrency. ControllerAdvice translates domain exceptions into the HTTP status defined by the API contract.

A database error is not always a business conflict. Map a unique constraint violation to 409 only when verified against the specific constraint and domain context; do not catch every DataIntegrityViolationException and blindly report "duplicate data".

## 8. HTTP Status: Not a Rigid Formula

| Issue | Typically Reasonable Status | Notes |
|---|---|---|
| Binding/query/path fails type conversion | 400 Bad Request | Client fixes format/type |
| Malformed JSON or cannot deserialize | 400 Bad Request | DTO has not been validated yet |
| Bean Validation input failure | 400 Bad Request | Can return fieldErrors |
| Missing authentication | 401 Unauthorized | Not validation |
| Insufficient permission | 403 Forbidden | Security/permission |
| Resource not found | 404 Not Found | Distinguish API route from domain entity |
| Unsupported HTTP method | 405 Method Not Allowed | Do not turn into validation 400 |
| State/uniqueness conflict | 409 Conflict | Client needs to change or refresh state |
| Semantic request unprocessable per API contract | 422 Unprocessable Content | Not mandatory for all business rules |
| Unexpected internal server error | 500 | Do not blame the client |

**Business errors do not default to HTTP 422.** Status 409 fits conflicting resource states, 422 fits syntactically/media-type valid payloads that cannot be fulfilled under semantic rules chosen by the contract, 403 fits permissions, and 404 applies when a resource does not exist. Maintain a consistent, documented policy.

Do not catch RuntimeException and return 400 to "standardize the format". That hides programming/DB bugs and skews monitoring.

## 9. ProblemDetail and Stable Error Codes

Spring Framework 6.x provides org.springframework.http.ProblemDetail, representing HTTP problem responses under the Problem Details model. Extension fields such as code and fieldErrors can be added.

Illustrative JSON example:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request violates input constraints",
  "code": "VALIDATION_ERROR",
  "fieldErrors": [
    {"field": "eventId", "kind": "constraint", "message": "must not be blank"},
    {"field": "seats", "kind": "constraint", "message": "must be greater than or equal to 1"}
  ]
}
~~~

Messages depend on locale/validation provider. Clients should rely on stable codes and field names rather than parsing English text strings.

Conflict example:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Event is fully booked",
  "code": "BOOKING_CONFLICT"
}
~~~

This is a **custom-defined API contract**, not a default body Spring is guaranteed to return in every application.

| Example API Code | Classification | What the Client Can Do |
|---|---|---|
| BINDING_ERROR | Invalid query/path parameter | Fix type or add missing parameter |
| BODY_PARSE_ERROR | Invalid JSON syntax/type | Resend body matching schema |
| VALIDATION_ERROR | DTO constraint | Fix fieldErrors |
| METHOD_VALIDATION_ERROR | Direct method parameter constraint | Fix parameter |
| BOOKING_CONFLICT | Domain conflict | Refresh state or choose another resource |
| INTERNAL_ERROR | Server error | Do not treat as invalid input |

Do not include raw rejectedValue, passwords, tokens, SQL exceptions, Java stack traces, or raw JSON decoder root causes in responses sent to clients.

## 10. Runnable Spring Boot 3.5.x / Java 17+ Project

### 10.1. Dependencies and Structure

Create a Maven project with Spring Boot parent/BOM, adding:

~~~xml
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
~~~

This is the dependencies section inside a pom.xml already configured with Spring Boot dependency management, not a full pom.xml.

Files:

~~~text
src/main/java/example/validation/
    DemoApplication.java
    CreateBookingRequest.java
    BookingResponse.java
    BookingConflictException.java
    BookingService.java
    BookingController.java
    BookingErrorAdvice.java
src/test/java/example/validation/
    BookingControllerTest.java
~~~

### 10.2. Application

File DemoApplication.java:

~~~java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. Request and Response DTOs

File CreateBookingRequest.java:

~~~java
package example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateBookingRequest(
        @NotBlank String eventId,
        @NotNull @Min(1) Integer seats
) {}
~~~

File BookingResponse.java:

~~~java
package example.validation;

public record BookingResponse(
        String bookingId,
        String eventId,
        int seats
) {}
~~~

Uses Integer to distinguish missing/null from 0 via @NotNull and @Min. @NotBlank ensures eventId has non-whitespace characters, yet does not guarantee the event exists in the domain.

### 10.4. Domain Exception and Service

File BookingConflictException.java:

~~~java
package example.validation;

public class BookingConflictException extends RuntimeException {

    public BookingConflictException(String message) {
        super(message);
    }
}
~~~

File BookingService.java:

~~~java
package example.validation;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    public BookingResponse create(CreateBookingRequest request) {
        if ("sold-out".equalsIgnoreCase(request.eventId())) {
            throw new BookingConflictException(
                    "Event is fully booked");
        }

        // Demo does not persist to a database; bookingId is a sample constant.
        return new BookingResponse(
                "BKG-DEMO-001",
                request.eventId(),
                request.seats());
    }
}
~~~

Here the business conflict is thrown after the controller receives valid input. In real products, services must also enforce invariants independently of controllers, transactions, concurrency, and database constraints.

### 10.5. Controller Demonstrating Three Paths

File BookingController.java:

~~~java
package example.validation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookingResponse> create(
            @Valid @RequestBody CreateBookingRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request));
    }

    @GetMapping("/estimate")
    public Map<String, Integer> estimate(
            @RequestParam int seats) {
        return Map.of("estimatedCost", seats * 100);
    }

    @GetMapping("/guarded-estimate")
    public Map<String, Integer> guardedEstimate(
            @RequestParam @Min(1) int seats) {
        return Map.of("estimatedCost", seats * 100);
    }
}
~~~

POST /api/bookings validates the DTO, then calls the service and may trigger a business conflict. GET /estimate?seats=abc fails during conversion. GET /guarded-estimate?seats=0 succeeds at conversion but violates the direct constraint. Do not place @Validated at the class level on this controller if following Spring Framework 6.2 built-in MVC method validation.

## 11. @RestControllerAdvice Classifying Exceptions and Producing ProblemDetail

File BookingErrorAdvice.java:

~~~java
package example.validation;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class BookingErrorAdvice {

    private static ResponseEntity<ProblemDetail> problem(
            HttpStatusCode status, String code, String detail) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }

    @ExceptionHandler({
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class
    })
    public ResponseEntity<ProblemDetail> binding(Exception ex) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "BINDING_ERROR",
                "A required request parameter is missing or has an invalid type");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> bodyParse(
            HttpMessageNotReadableException ex) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "BODY_PARSE_ERROR",
                "Request body is missing, malformed, or incompatible with the expected type");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> dtoValidation(
            MethodArgumentNotValidException ex) {

        List<Map<String, String>> fields =
                ex.getBindingResult().getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message", error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage(),
                                "kind", error.isBindingFailure()
                                        ? "binding"
                                        : "constraint"))
                        .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request violates input constraints");
        body.setProperty("code", "VALIDATION_ERROR");
        body.setProperty("fieldErrors", fields);
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException ex) {

        HttpStatusCode status = ex.getStatusCode();
        boolean serverError = status.is5xxServerError();

        return problem(
                status,
                serverError
                        ? "INTERNAL_ERROR"
                        : "METHOD_VALIDATION_ERROR",
                serverError
                        ? "Server response contract failed"
                        : "Request method parameter constraints failed");
    }

    @ExceptionHandler(BookingConflictException.class)
    public ResponseEntity<ProblemDetail> conflict(
            BookingConflictException ex) {
        return problem(
                HttpStatus.CONFLICT,
                "BOOKING_CONFLICT",
                ex.getMessage());
    }
}
~~~

Note the paths:

- Wrong query type or missing parameter: BINDING_ERROR / 400.
- Undecodable HTTP body: BODY_PARSE_ERROR / 400.
- DTO @Valid failure: VALIDATION_ERROR / 400, containing FieldErrors. The isBindingFailure flag distinguishes binding vs constraint errors inside the result.
- Direct method parameter constraint: METHOD_VALIDATION_ERROR / 400 when input is invalid.
- Return-value constraint violation: status may be 500; the example preserves 5xx rather than blaming the client.
- Domain BookingConflictException: BOOKING_CONFLICT / 409.

In a real API, include getGlobalErrors() if DTOs have class-level/cross-field constraints. The example maps only FieldErrors to focus on the three layers. Other exceptions such as HTTP 415, 405, or 406 can be handled by default infrastructure unless custom handlers are declared.

Do not write a global @ExceptionHandler(Exception.class) returning 400 for everything. It hides programming bugs and breaks HTTP semantics. Do not put rejectedValue or raw ex.getCause() into responses; they may contain sensitive data.

## 12. Testing with MockMvc

File src/test/java/example/validation/BookingControllerTest.java:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryTypeMismatchIsBindingError() throws Exception {
        mvc.perform(get("/api/bookings/estimate")
                        .param("seats", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"));
    }

    @Test
    void wrongJsonFieldTypeIsBodyParseError() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"EVENT-10\",\"seats\":\"many\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_PARSE_ERROR"));
    }

    @Test
    void invalidDtoConstraintsAreValidationError() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"\",\"seats\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fieldErrors").isArray());
    }

    @Test
    void directParameterConstraintUsesMethodValidation()
            throws Exception {
        mvc.perform(get("/api/bookings/guarded-estimate")
                        .param("seats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"));
    }

    @Test
    void soldOutEventIsBusinessConflict() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"sold-out\",\"seats\":2}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_CONFLICT"));
    }

    @Test
    void validRequestIsCreated() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"EVENT-10\",\"seats\":2}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.bookingId")
                        .value("BKG-DEMO-001"))
                .andExpect(jsonPath("$.seats").value(2));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

MockMvc executes requests inside the Spring MVC test context without opening an HTTP socket. Each test asserts a specific error code rather than just checking that all return 400. If the app uses Spring Security, configure test users and policies; a Filter returning 401/403 does not indicate broken validation mapping.

Projects customizing Jackson ProblemDetail serialization will need to adjust JSONPath expressions to their real API contract. Under standard Boot 3.5, the code extension property is serialized into the problem response.

## 13. Quick Verification with curl

After starting the application via ./mvnw spring-boot:run, assuming default port 8080:

~~~bash
# Conversion: query cannot be converted to int.
curl -i "http://localhost:8080/api/bookings/estimate?seats=abc"

# JSON decode: seats is a string that cannot be converted to Integer.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":"many"}'

# Bean Validation: seats has valid type but value is less than 1.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":0}'

# Business: event is sold out.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"sold-out","seats":2}'

# Success.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":2}'
~~~

Corresponding statuses: 400, 400, 400, 409, and 201. These are expected per the code, not guaranteed identical stdout across every Spring Boot version. Logs, headers, and JSON field ordering vary by runtime.

## 14. Service Validation and Misclassification Risks

Spring can run method validation on services when @Validated and the corresponding mechanism are applied:

~~~java
@Service
@Validated
public class PaymentService {

    public void transfer(@NotNull TransferCommand command) {
        // Maintain method invariant when service is invoked.
    }
}
~~~

This is an illustrative snippet requiring TransferCommand and imports. @NotNull on a reference does not automatically cascade into nested fields without @Valid.

**A method constraint error in a service is not always an HTTP client input error.** A scheduled job or internal class may call the service against its contract. Spring may throw ConstraintViolationException or MethodValidationException depending on configuration, and does not require mapping that exception to HTTP 400.

Do not catch every ConstraintViolationException globally and return 400 by default. Determine who violated the contract, which layer threw it, and whether the client can fix it.

The same applies to @NotNull violations on return values or a service returning null unexpectedly: that is normally a server bug, not a client query parameter error.

## 15. Business State, Transactions, and Race Conditions

Bean Validation normally does not need external state. Business checks such as "are 2 seats still available?" must inspect data at execution time and often require transactions.

Example:

~~~text
Request A checks 1 seat remaining
Request B checks 1 seat remaining
Request A books 1 seat
Request B books 1 seat
~~~

Without locking or transactional invariants, both can see one seat left and oversell. Putting a custom @AvailableSeats constraint on the DTO does not solve the race condition.

Appropriate approaches depending on the domain:

- Optimistic locking with a version column and clear retry policy.
- Pessimistic locking when required.
- Atomic conditional updates checking quantities.
- Unique indexes to protect uniqueness.
- Idempotency keys to avoid duplicating operations on client retries.
- Separating expected domain conflicts from unexpected DB infrastructure failures.

Once a transaction detects a conflict, the service can translate it into a clear domain exception; the web layer maps it per API contract. Controllers do not need to know SQL constraint names, deadlock codes, or the database vendor.

## 16. Comparison with Spring WebFlux

WebFlux shares the same three conceptual layers but uses a reactive pipeline and different exception types:

| Issue | Spring MVC | Spring WebFlux |
|---|---|---|
| Query/path conversion | MethodArgumentTypeMismatchException or matching conversion error | ServerWebInputException / input resolution error |
| Undecodable JSON | HttpMessageNotReadableException | ServerWebInputException / decoding error |
| @Valid object in @RequestBody | MethodArgumentNotValidException | WebExchangeBindException |
| Direct method constraint | HandlerMethodValidationException | HandlerMethodValidationException |
| Domain rule | Domain exception, handled via advice | Domain exception inside Mono/Flux, handled via advice/handler |
| Error pipeline | HandlerExceptionResolver / ResponseEntityExceptionHandler | Reactive exception handling / WebExceptionHandler |

These are **common paths**, not a guarantee that every method signature or version throws the exact same exception class.

Example reactive signature:

~~~java
@PostMapping("/bookings")
public Mono<BookingResponse> create(
        @Valid @RequestBody Mono<CreateBookingRequest> body) {
    return body.flatMap(reactiveService::create);
}
~~~

This is illustrative only; reactiveService.create must return Mono<BookingResponse>. Do not take a synchronous MVC BookingService and call it "reactive". In WebFlux, object validation of a request body can raise WebExchangeBindException; when using direct method constraints, HandlerMethodValidationException can also occur.

Do not import Servlet MVC's HttpMessageNotReadableException as a general solution for WebFlux. When an exception happens inside Mono/Flux, handling must keep the error signal inside the reactive chain. Never call block() on the event loop to catch exceptions imperatively.

If a custom constraint or business rule executes blocking JDBC calls, it can block the event loop; use reactive I/O or isolate blocking work appropriately with timeouts.

## 17. I18n, Security, and Error Messages

Spring has MessageSource and MessageCodesResolver to generate codes like NotBlank.createBookingRequest.eventId, Min.createBookingRequest.seats, or typeMismatch.searchForm.minSeats. Exact object names depend on the DTO and binding setup.

Example messages_vi.properties:

~~~properties
NotBlank.createBookingRequest.eventId=Mã sự kiện không được để trống
Min.createBookingRequest.seats=Số ghế phải từ 1 trở lên
typeMismatch.searchForm.minSeats=Số ghế tối thiểu phải là số nguyên
~~~

This is a resource bundle example. Inspect actual getCodes() values before hardcoding keys, as object names can vary with configuration.

A good error response has status, a stable code, field, user-friendly message, and an appropriate correlation ID. Never send raw rejectedValue, passwords, tokens, stack traces, SQL syntax, or raw exception causes to clients.

Likewise, do not couple client logic to English strings like "must not be blank". Localized text can change; clients should rely on error codes and field lists.

## 18. Retry Policy by Error Type

- **400 binding:** normally requires fixing type, format, query, or JSON; identical retries will not help.
- **400 validation:** fix fields violating constraints; UI can show errors next to the relevant fields.
- **409 business:** refresh state, choose another resource, or wait for state changes; automatic retries may still conflict.
- **422 semantic:** per contract, the client must alter content or workflow rather than repeating the same request.
- **500/503:** may be server-side; retry only when allowed by method/idempotency policy and with backoff.

An HTTP 409 from a resource state conflict is fundamentally different from an HTTP 400 because seats is not a number. Proper classification improves UX and prevents pointless retries.

## 19. QA Checklist Before Promoting an API to Production

1. Tests cover query/path type mismatches.
2. Tests cover malformed JSON or fields that fail deserialization.
3. Tests cover missing required parameters and missing request bodies.
4. Tests cover @NotBlank, @NotNull, @Min, and nested @Valid if used.
5. Tests cover direct method constraints and corresponding exception mappings.
6. If using BindingResult, verify placement immediately after the argument and FieldError.isBindingFailure().
7. Tests cover domain conflicts and success responses.
8. Tests cover database uniqueness/concurrency if those are real invariants.
9. Error responses have stable codes and never leak rejectedValue/stack traces.
10. No catch-all 400 for every exception.
11. If the API supports WebFlux, test WebExchangeBindException and the reactive exception pipeline.
12. Clear documentation for 400/409/422, retries, and idempotency contracts.

## 20. Official Documentation

- [Spring MVC 6.2 – Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring WebFlux 6.2 – Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 – Data Binding, Type Conversion and Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework – FieldError Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring MVC 6.2 – Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring WebFlux 6.2 – Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Boot 3.5 – Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)

**Conclusion:** Binding handles converting HTTP input into Java types. Bean Validation checks constraints on objects and methods. Business errors reflect domain state and policies. Classify by root cause rather than just HTTP status or exception class name; separate domain rules from DTO validation, maintain stable error codes, and test exception-to-response mapping.