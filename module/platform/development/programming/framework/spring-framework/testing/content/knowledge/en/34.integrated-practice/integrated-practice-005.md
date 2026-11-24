# Testing HTTP Success, Validation, and Error Mapping

A good HTTP API must be tested on both sides of its contract: valid requests must produce a successful response with the right status, headers, and body; invalid requests must be rejected before business logic executes and mapped to a consistent error response. With Spring MVC, `MockMvc` lets you test the entire request processing flow inside MVC without starting a real HTTP server.

This practice builds an endpoint for creating and looking up orders. We will combine `@Valid`, Jakarta Bean Validation, `@RestControllerAdvice`, `ProblemDetail`, and `MockMvc` to test:

- Valid requests and `201 Created` responses.
- Missing required fields or out-of-range values.
- Malformed JSON or unconvertible types.
- Invalid path variable types.
- Business errors such as a non-existent order or duplicate product code.
- Ensuring the service is not called when a request is rejected during binding/validation.

## 1. Understanding Request Processing Steps

Spring MVC processes a request through multiple steps. Identifying the exact step where an error arises helps you choose the right exception handler and write appropriate assertions.

```text
HTTP request
    |
    v
Mapping: path, HTTP method, consumes, produces
    |
    v
Read body / convert path variables and query parameters
    |
    v
Bind data to DTO or controller parameters
    |
    v
Bean Validation via @Valid / @Validated
    |
    v
Controller calls business service
    |
    v
Build success response
    |
    +---- exception at any step -----------+
                                           |
                                           v
                                Exception resolver / advice
                                           |
                                           v
                                HTTP error response
```

Common error types do not originate from the same source:

| Request or Situation | Detection Step | Common Exception | Typical Status |
|---|---|---|---:|
| Missing entire required body | Reading body | `HttpMessageNotReadableException` | 400 |
| Malformed JSON syntax | Deserializing body | `HttpMessageNotReadableException` | 400 |
| JSON contains value of wrong type | Deserializing body | `HttpMessageNotReadableException` | 400 |
| DTO missing field or violating constraint | Bean Validation | `MethodArgumentNotValidException` | 400 |
| Unconvertible path/query parameter | Argument conversion | `MethodArgumentTypeMismatchException` | 400 |
| Order not found | Business logic | `OrderNotFoundException` | 404 |
| Duplicate order code or product code | Business logic | `DuplicateOrderException` | 409 |
| Unsupported media type sent | Request mapping/converter | `HttpMediaTypeNotSupportedException` | 415 |

The status code is part of the HTTP contract. The error body adds details so clients understand the error type and can handle it appropriately. Do not return the same status for every case just because they all cause the request to fail.

## 2. Preparing Validation Dependencies

With Spring Boot, a Jakarta Bean Validation implementation must be on the classpath. Usually you add the following starter:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Without a validation provider, annotations such as `@NotBlank`, `@Min`, or `@Size` may not be enforced. Adding annotations to a DTO alone does not supply a validation implementation.

The examples use `jakarta.validation.*`, which matches Spring Framework 6 and Spring Boot 3 and later. Older Spring projects use `javax.validation.*` and must adjust packages according to their version.

## 3. Defining the DTO and Input Rules

Suppose the order creation API accepts a product code and a quantity. We use `Integer` instead of `int` for the required field to distinguish a missing field from the value `0`.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 20)
        String productCode,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

Each constraint has its own meaning:

| Constraint | Rule |
|---|---|
| `@NotNull` | Value must not be `null` |
| `@NotBlank` | String must not be null, empty, or whitespace-only |
| `@Size(max = 20)` | String has at most 20 characters |
| `@Min(1)` | Minimum quantity is 1, inclusive |
| `@Max(100)` | Maximum quantity is 100, inclusive |

If primitive `int` is used, a missing JSON field can default to `0`. In that case `@NotNull` cannot detect that the client omitted the field. The `Integer` wrapper allows the DTO to hold `null`, enabling validation to detect an omitted required field.

We define the response independently of the request DTO:

```java
import java.util.UUID;

public record OrderResponse(
        UUID id,
        String productCode,
        int quantity,
        String status
) {
}
```

Separating request and response lets the API strictly control what data clients can submit and what data the server exposes. For instance, clients cannot supply `status` or `id` if those are system-managed fields.

## 4. Defining the Service and Controller

The service is the business boundary invoked by the controller after the request has been bound and validated:

```java
import java.util.UUID;

public interface OrderApplicationService {
    OrderResponse create(CreateOrderRequest request);

    OrderResponse findById(UUID id);
}
```

The controller declares two endpoints. `POST /api/orders` creates an order and returns `201 Created` with a `Location` header. `GET /api/orders/{id}` looks up an order by UUID.

```java
import java.net.URI;
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderApplicationService orderService;

    OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderResponse created = orderService.create(request);
        URI location = URI.create("/api/orders/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        return orderService.findById(id);
    }
}
```

`@RequestBody` instructs Spring to read the body into `CreateOrderRequest`. `@Valid` triggers Bean Validation after deserialization succeeds. If validation fails, Spring handles the exception before calling `orderService.create(...)`.

`consumes = application/json` constrains the body format for the POST endpoint. If the client sends an unsupported media type, Spring can return `415 Unsupported Media Type` before invoking the controller.

## 5. Defining Business Exceptions

Business exceptions represent outcomes that the controller needs to translate into HTTP statuses:

```java
import java.util.UUID;

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(UUID id) {
        super("Order " + id + " was not found");
    }
}

class DuplicateOrderException extends RuntimeException {
    DuplicateOrderException(String productCode) {
        super("An order already exists for product " + productCode);
    }
}
```

Exceptions can hold details useful for logging or internal handling. You do not necessarily expose `getMessage()` verbatim to the client. Public error responses should use stable codes and controlled messages.

## 6. Mapping Errors with ProblemDetail

Spring Framework 6 and later provide `ProblemDetail` to represent Problem Details for HTTP APIs. Spring MVC serializes this object into a response with media type `application/problem+json`.

Standard properties:

| Field | Meaning |
|---|---|
| `type` | URI identifying the problem type |
| `title` | Short name of the problem type |
| `status` | Corresponding HTTP status |
| `detail` | Specific description of this occurrence |
| `instance` | URI referencing the request that caused the problem |

Additional custom fields such as `code` or `errors` can be added via `setProperty(...)`. Extension properties are serialized at the top level of the JSON.

Create a `@RestControllerAdvice` to centralize error handling:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleValidation(MethodArgumentNotValidException ex) {
        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "constraint", error.getCode()))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");
        problem.setType(URI.create(
                "https://api.example.test/problems/validation-error"));
        problem.setTitle("Request validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);
        return problem;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail handleUnreadableBody(HttpMessageNotReadableException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "The request body is missing or cannot be read.");
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-request-body"));
        problem.setTitle("Invalid request body");
        problem.setProperty("code", "INVALID_REQUEST_BODY");
        return problem;
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ProblemDetail handleInvalidParameter(MethodArgumentTypeMismatchException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "A request parameter has an invalid value.");
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-parameter"));
        problem.setTitle("Invalid request parameter");
        problem.setProperty("code", "INVALID_PARAMETER");
        return problem;
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested order does not exist.");
        problem.setType(URI.create(
                "https://api.example.test/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(DuplicateOrderException.class)
    ProblemDetail handleDuplicateOrder(DuplicateOrderException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "An order with the supplied product code already exists.");
        problem.setType(URI.create(
                "https://api.example.test/problems/duplicate-order"));
        problem.setTitle("Duplicate order");
        problem.setProperty("code", "DUPLICATE_ORDER");
        return problem;
    }
}
```

These handlers keep the response body consistent. Clients can branch on `code` or `type` without parsing exception messages. The validation handler also returns an `errors` list, where each item contains the field name and constraint code.

`error.getCode()` is typically a code such as `NotBlank`, `NotNull`, `Min`, `Max`, or `Size`. If the API needs business error codes that remain stable across validation provider versions, you can map these constraints to application-defined codes.

In the example, the `MissingServletRequestParameterException` import is unused and can be removed in a real file; the handlers only handle `MethodArgumentTypeMismatchException`. If the API has required query parameters, you can add a dedicated handler for the missing-parameter exception.

## 7. Setting Up the MockMvc Test Slice

`@WebMvcTest` creates an MVC slice rather than the full application. We import the exception advice and replace the service with a Mockito mock in the Spring context.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerHttpTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderApplicationService orderService;
}
```

`@MockitoBean` is available in Spring Framework 6.2 and later. With Spring Boot 3.4 and later, this is the modern replacement for the older `@MockBean`. If the project uses an older Spring Boot version without Spring Framework 6.2, replace the import and annotation with `org.springframework.boot.test.mock.mockito.MockBean`.

`@Import(ApiExceptionHandler.class)` ensures the advice is included in the MVC slice. If you omit the import and the advice is not loaded by the test configuration, failing requests may go through the default handler instead of the API's intended schema.

## 8. Testing a Successful Request

A success test should check multiple parts of the contract:

- HTTP status is `201 Created`.
- `Location` header points to the newly created resource.
- Response has JSON media type.
- Body has the exact `id`, `productCode`, `quantity`, and `status`.
- Service was called exactly once with the bound request.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void createsOrderAndReturnsResourceLocation() throws Exception {
    UUID id = UUID.fromString("d2b6d39e-7df4-4e2e-8fd3-40c11a2d79c0");
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);
    OrderResponse response = new OrderResponse(
            id, "BOOK-01", 2, "CREATED");

    when(orderService.create(request)).thenReturn(response);

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 2
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "Location", "/api/orders/" + id))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$.productCode").value("BOOK-01"))
            .andExpect(jsonPath("$.quantity").value(2))
            .andExpect(jsonPath("$.status").value("CREATED"));

    verify(orderService).create(request);
}
```

`MockMvc` runs the request through Spring MVC, binds JSON to the record, and invokes the controller. `@MockitoBean` provides a mock service so the test controls the response without a database.

`contentType(...)` describes the request body format. `accept(...)` describes the response format the client expects to receive. These two headers serve different purposes and should be declared accurately in tests.

## 9. Testing a Missing Required Field

When JSON omits `quantity`, Jackson can construct the DTO with `quantity == null` because the field type is `Integer`. `@NotNull` then detects the violation and Spring throws `MethodArgumentNotValidException`.

```java
import org.springframework.http.MediaType;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingRequiredQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/validation-error"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].constraint").value("NotNull"));

    verifyNoInteractions(orderService);
}
```

This test verifies both the response contract and processing order: the service is not called when the request is invalid. This is an important assertion if the service performs side effects such as writing to a database or calling an external system.

When a request produces multiple field errors, do not depend on index `[0]` because validation error order is not always part of the contract. Use a JSONPath filter by field or deserialize the error list and compare as a set. The example above triggers only one error, so checking the first element is clear.

## 10. Testing Out-of-Range Values

For `quantity` from 1 to 100, test both valid boundaries and the values immediately outside the bounds.

| Value | Expected Result | Constraint |
|---:|---|---|
| 0 | Rejected | `@Min(1)` |
| 1 | Accepted | Valid lower bound |
| 100 | Accepted | Valid upper bound |
| 101 | Rejected | `@Max(100)` |

Example testing quantity equal to 0:

```java
@Test
void rejectsQuantityBelowMinimum() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].constraint").value("Min"));

    verifyNoInteractions(orderService);
}
```

Testing string length:

```java
@Test
void rejectsProductCodeLongerThanTwentyCharacters() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "123456789012345678901",
                              "quantity": 1
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("productCode"))
            .andExpect(jsonPath("$.errors[0].constraint").value("Size"));
}
```

For valid boundary values, the test needs to stub the service and verify that the endpoint accepts `quantity=1` or `quantity=100`. Testing only invalid values does not prove whether the constraint was configured inclusively or exclusively.

## 11. Testing Malformed JSON or Wrong Value Types

Malformed JSON or values that cannot be converted to the Java type fail before Bean Validation. For example, `quantity` expects an integer, yet the client sends the string `"many"`:

```json
{
  "productCode": "BOOK-01",
  "quantity": "many"
}
```

Jackson cannot deserialize this value into `Integer`. Spring normally raises `HttpMessageNotReadableException`, not `MethodArgumentNotValidException`.

```java
@Test
void rejectsWrongJsonValueType() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": "many"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));

    verifyNoInteractions(orderService);
}
```

Syntactically invalid JSON is also handled at the body-reading step:

```java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("{\"productCode\":\"BOOK-01\",\"quantity\":}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Do not assert on the verbatim Jackson exception message. Exception wording can change across versions, configurations, or locales. Assert on the public error code and status committed by the API.

## 12. Testing a Completely Missing Body

`@RequestBody` defaults to `required = true`. If a request has no body, Spring cannot supply `CreateOrderRequest` to the controller and typically throws `HttpMessageNotReadableException`.

```java
@Test
void rejectsMissingRequestBody() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));

    verifyNoInteractions(orderService);
}
```

This case differs from valid JSON missing a field. An empty body is rejected during body reading; a body with a JSON object missing `quantity` can bind to the DTO and then be rejected by Bean Validation.

If the API allows an optional body using `@RequestBody(required = false)`, the contract is different. The controller must handle `null` deliberately and tests must reflect that policy.

## 13. Testing an Invalid Path Variable Type

The GET endpoint expects a `UUID`. When a client requests `/api/orders/not-a-uuid`, Spring cannot convert the path variable into a UUID and raises `MethodArgumentTypeMismatchException`.

```java
@Test
void rejectsInvalidOrderIdFormat() throws Exception {
    mockMvc.perform(get("/api/orders/not-a-uuid")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));

    verifyNoInteractions(orderService);
}
```

Note the distinction:

- `/api/orders/not-a-uuid`: path matches the route, but the value cannot be converted to UUID; typically `400`.
- `/api/orders`: the GET `/{id}` route does not match because the segment is missing; typically `404`.
- Valid UUID with no matching order: controller invokes service and service throws `OrderNotFoundException`; the API returns `404` per business mapping.

The three cases may feel like "order not found" from a client's perspective, yet they happen at different stages and carry different meanings.

## 14. Testing 404 and 409 Business Errors

When the UUID is valid but the order does not exist, the service throws `OrderNotFoundException`. The advice maps it to `404 Not Found`:

```java
import java.util.UUID;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@Test
void mapsMissingOrderToNotFoundProblem() throws Exception {
    UUID id = UUID.fromString("d2b6d39e-7df4-4e2e-8fd3-40c11a2d79c0");
    when(orderService.findById(id)).thenThrow(new OrderNotFoundException(id));

    mockMvc.perform(get("/api/orders/{id}", id)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/order-not-found"))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
```

When the service detects that the product code already has an order, it throws `DuplicateOrderException`. The advice maps it to `409 Conflict`:

```java
@Test
void mapsDuplicateOrderToConflictProblem() throws Exception {
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);
    when(orderService.create(request))
            .thenThrow(new DuplicateOrderException("BOOK-01"));

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 2
                            }
                            """))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/duplicate-order"))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("DUPLICATE_ORDER"));
}
```

These tests verify both the HTTP status and `status` inside the Problem Detail body. Both values should agree. `type` and `code` are more stable identifiers than `detail`, which is a human-readable message.

## 15. Testing Content Negotiation and Media Types

`Content-Type` and `Accept` solve two different questions:

| Header | Question |
|---|---|
| `Content-Type` | In what format is the request body being sent? |
| `Accept` | In what format does the client want to receive the response? |

For the order creation endpoint, the client sends JSON and therefore sets `Content-Type: application/json`. On success, the client can request `application/json`; on failure, the client can request `application/problem+json`.

If the endpoint declares `consumes = application/json` yet the client sends `text/plain`, Spring typically returns `415 Unsupported Media Type`. This is not a Bean Validation error because the body has not been bound to the DTO.

If the client sends an `Accept` header incompatible with the representations the endpoint can produce, Spring may return `406 Not Acceptable`. When designing an API, explicitly decide the supported success and error media types. Tests should send an `Accept` header matching the contract published by the endpoint.

## 16. Distinguishing Validation, Conversion, and Business Errors

These three error groups need separate tests because they are detected at different times.

| Group | Example | Is Service Called? | Key Assertion |
|---|---|---:|---|
| Validation | `quantity = 0`, missing `productCode` | No | `400`, `VALIDATION_FAILED`, field/constraint |
| Conversion/deserialization | `quantity = "many"`, malformed UUID | No | `400`, invalid body/parameter code |
| Business logic | Duplicate order code, order not found | Yes | `409` or `404`, business error code |

If a test only asserts status `400`, it does not prove the error was classified properly. JSON with the wrong type and a type-valid value violating `@Min` can both return `400`, yet the client may need different information to fix the request.

## 17. Verifying No Side Effects When a Request Is Rejected

A valuable assertion in validation tests is verifying that the service is not called. For example:

```java
@Test
void doesNotCallServiceWhenQuantityIsInvalid() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

This proves the request was blocked before reaching business logic. It is especially helpful when the service has side effects such as writing to a database, publishing events, or calling a payment system.

Do not use `verifyNoInteractions(...)` for business exception tests if the service itself is what throws the exception. In that case, verify the service was called once and assert that the response reflects the exception thrown by the service.

## 18. Structuring a Complete Test Class

A realistic test class can group cases according to the endpoint contract:

```java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerHttpTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderApplicationService orderService;

    @Test
    void createsOrder() throws Exception {
        // Stub service, send valid JSON, verify 201, Location, and body.
    }

    @Test
    void rejectsMissingQuantity() throws Exception {
        // Send JSON missing field, verify 400 and NotNull.
    }

    @Test
    void rejectsQuantityOutsideRange() throws Exception {
        // Send quantity = 0 or 101, verify Min/Max.
    }

    @Test
    void rejectsMalformedBody() throws Exception {
        // Send malformed JSON, verify INVALID_REQUEST_BODY.
    }

    @Test
    void rejectsInvalidUuid() throws Exception {
        // Send unconvertible path variable, verify INVALID_PARAMETER.
    }

    @Test
    void mapsMissingOrder() throws Exception {
        // Stub service to throw OrderNotFoundException, verify 404.
    }

    @Test
    void mapsDuplicateOrder() throws Exception {
        // Stub service to throw DuplicateOrderException, verify 409.
    }
}
```

The snippet above is an overall structure; in real tests, replace the comments with the concrete requests and expectations shown in earlier sections. Test names should describe observable behavior rather than relying on internal exception names if those exceptions are not part of the contract.

## 19. Common Mistakes When Writing Tests

| Practice | Problem | Better Practice |
|---|---|---|
| Only checking status `400` for all invalid inputs | Does not verify the error was classified correctly | Check `code`, `type`, field, and constraint |
| Using `int` for a required field and expecting `@NotNull` to catch missing fields | Primitives cannot represent `null` | Use a wrapper like `Integer` if missing fields must be distinguished |
| Assuming wrong JSON value type is a Bean Validation error | Deserialization fails before validation | Handle `HttpMessageNotReadableException` |
| Assuming malformed UUID is a 404 business error | Conversion fails before the service | Test `MethodArgumentTypeMismatchException` and status 400 |
| Returning raw exception messages in responses | Can expose internal data and change with implementation | Use stable error codes and public detail strings |
| Forgetting to import advice in the MVC slice | Test uses default handler instead of application error schema | `@Import(ApiExceptionHandler.class)` |
| Mocking service with `@Mock` while calling the Spring bean | Mock field does not replace the dependency in context | Use `@MockitoBean` or `@MockBean` per version |
| Only testing out-of-bounds values | Does not prove valid boundaries are accepted | Test values right at the boundary and outside the boundary |
| Comparing validation error list order | Order is not necessarily part of the contract | Find errors by field/code or normalize order |

## 20. When Are Additional Integration Tests Needed?

`@WebMvcTest` verifies the controller, binding, validation, advice, and response within the Spring MVC slice. It does not prove the entire application can connect to a database or broker.

If the goal is to verify the HTTP flow through the real service, repository, and PostgreSQL, add a broader test such as `@SpringBootTest` with Testcontainers. If you need to verify the server connector, port, or TLS, run the application on a real server with a random port and send requests through an HTTP client.

Test scope should match the risk:

| Risk | Appropriate Test |
|---|---|
| Controller binds wrong DTO or returns wrong status | `@WebMvcTest` + MockMvc |
| Validation is not enabled or advice is not applied | MVC slice with real validation provider and advice |
| Repository query/migration is wrong | Integration test with real database |
| HTTP transport/TLS/connector is wrong | Real server test |
| Pure business logic is wrong | Service/domain unit test |

You do not need `@SpringBootTest` for every controller test. Use slices for fast feedback, then add representative integration tests for the boundaries that need verification.

## 21. Checklist for an HTTP Endpoint

Before finalizing the test suite for an endpoint, verify:

- Valid requests return a success status matching HTTP semantics.
- `Location`, `Content-Type`, and important headers are checked.
- Response body contains the right fields and public data.
- Missing required fields are rejected.
- Empty strings, whitespace, and out-of-range values are tested against constraints.
- Malformed JSON or wrong value types map to body-reading errors.
- Unconvertible path/query parameters have appropriate error mapping.
- Business errors return matching status codes and error codes.
- Service is not called when a request is rejected before business logic.
- Error body does not leak stack traces or implementation details.
- MVC slice imports exception advice and uses the right mock bean.
- Real database/broker/server integration boundaries have tests at the right scope.

## 22. References

- [Spring Framework Reference — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): request body binding and validation in Spring MVC.
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Bean Validation integration.
- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, and exception handling.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): sending requests and asserting responses in Spring MVC Test.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices and Spring Boot testing support.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): Problem Details format for HTTP APIs.

Testing HTTP success, validation, and error mapping requires proving both valid requests and failure paths. Distinguish body-reading errors, conversion errors, Bean Validation violations, and business exceptions; then verify status, media type, and public error codes with MockMvc. When a request is rejected before business logic, verify that the service is not called to ensure there are no unintended side effects.
