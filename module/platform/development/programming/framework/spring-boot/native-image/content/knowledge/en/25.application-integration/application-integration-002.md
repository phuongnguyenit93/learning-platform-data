# Jackson, Bean Validation, and Error Handling for Types That Appear Only at Runtime

A Spring Boot application typically receives JSON over HTTP, converts that JSON into DTOs, validates the data, and only then invokes business logic. With GraalVM Native Image, this processing chain needs careful attention when a type is chosen only after reading the payload, when a subtype is determined by a discriminator, or when the application invokes Jackson through `RestClient` or `WebClient` inside a method body.

There are three independent steps:

1. **Jackson binding:** parses JSON and builds the right object graph. If the JSON is syntactically invalid, misses a type ID, or chooses an unsupported subtype, the object cannot be fully constructed.
2. **Bean Validation:** checks constraints on the bound object. `@Valid` triggers nested validation; constraints like `@NotBlank` or `@Positive` define validity conditions.
3. **HTTP error handling:** translates parse errors, validation errors, and business errors into responses with stable status codes and structures.

Native Image adds one requirement: every type the application might access dynamically must be discovered and retained at build time. **A type selected at runtime can still be used in native if it is already on the classpath at build time and supported by AOT/reachability metadata.** A new class installed after the executable has been built does not automatically become deserializable.

This lesson uses an order creation API with multiple payment methods to illustrate Jackson polymorphic binding, nested Bean Validation, `ProblemDetail`, runtime hints, and testing on both the JVM and native.

## 1. Request Processing Flow and Boundaries Between Error Types

A request goes through these steps in order:

~~~mermaid
flowchart TD
    A["HTTP JSON request"] --> B["Jackson reads JSON"]
    B --> C{"DTO and subtype constructed?"}
    C -->|No| D["HttpMessageNotReadableException"]
    C -->|Yes| E["Bean Validation"]
    E --> F{"Constraints valid?"}
    F -->|No| G["MethodArgumentNotValidException or HandlerMethodValidationException"]
    F -->|Yes| H["Controller and business logic"]
    H --> I{"Business logic succeeded?"}
    I -->|No| J["Domain exception / ErrorResponse"]
    I -->|Yes| K["Response DTO -> Jackson JSON"]
    D --> L["ProblemDetail HTTP 400"]
    G --> L
    J --> M["ProblemDetail by business error"]
    K --> N["HTTP response"]
~~~

Do not lump every error into "validation failed":

| Stage | Example | Typical Outcome |
| --- | --- | --- |
| JSON parsing | Missing brace, wrong data type | HttpMessageNotReadableException |
| Polymorphic deserialization | kind not in the subtype list | HttpMessageNotReadableException |
| Bean Validation on request object | blank name, negative quantity | MethodArgumentNotValidException |
| Method validation | Constraint placed directly on a method parameter | HandlerMethodValidationException in modern Spring MVC |
| Service validation via AOP | `@Validated` service has a constraint violation | Typically ConstraintViolationException |
| Business logic | Order already exists, limit exceeded | Domain exception, can map to HTTP 409 or appropriate status |

Jackson must be able to instantiate the object before Bean Validation can inspect that object. For example, if JSON has `kind` set to `crypto` while the application only declares `card` and `bank-transfer`, Jackson cannot select a subtype, so the controller never receives a DTO to validate.

## 2. Declaring Jackson and Bean Validation

In Spring Boot MVC, `spring-boot-starter-web` provides HTTP and JSON mapping infrastructure. Add a Bean Validation provider with the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Use `jakarta.validation.*` annotations in modern Spring Boot applications. Do not mix legacy `javax.validation.*` with `jakarta.validation.*`.

Spring Boot automatically configures Jackson when the corresponding JSON library is on the classpath and provides a `Validator` when a Bean Validation provider is present. If direct inspection or customization is needed, Spring can expose `jakarta.validation.Validator` via `LocalValidatorFactoryBean`.

### DTOs Should Describe the Data Contract

HTTP DTOs should represent the data the client is allowed to send. Do not accept JPA entities or internal objects containing sensitive fields directly. Separating request DTOs helps clearly control:

- Which fields the client can send.
- Which fields must have values.
- Which fields are allowed per subtype.
- Which fields are generated exclusively by the server.
- What data must never appear in error responses or logs.

## 3. Using Safe Discriminators for Subtypes Selected at Runtime

Suppose an order can be paid by card or bank transfer. JSON includes a `kind` field to indicate the subtype:

~~~json
{
  "orderId": "ORD-1001",
  "payment": {
    "kind": "card",
    "token": "tok_test_123",
    "lastFour": "4242"
  }
}
~~~

Or:

~~~json
{
  "orderId": "ORD-1002",
  "payment": {
    "kind": "bank-transfer",
    "accountReference": "BANK-REF-88"
  }
}
~~~

Declare the interface and the list of subtypes:

~~~java
package com.example.orders.api;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPaymentDetails.class,
                name = "card"
        ),
        @JsonSubTypes.Type(
                value = BankTransferDetails.class,
                name = "bank-transfer"
        )
})
public sealed interface PaymentDetails
        permits CardPaymentDetails, BankTransferDetails {
}
~~~

The two implementations:

~~~java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CardPaymentDetails(
        @NotBlank String token,
        @NotBlank
        @Pattern(regexp = "\\d{4}")
        String lastFour
) implements PaymentDetails {
}
~~~

~~~java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;

public record BankTransferDetails(
        @NotBlank String accountReference
) implements PaymentDetails {
}
~~~

Request DTO:

~~~java
package com.example.orders.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String orderId,
        @NotNull @Valid PaymentDetails payment
) {
}
~~~

Example response DTO used in the controller signature:

~~~java
public record OrderResponse(String orderId, String status) {
}
~~~

Here `Id.NAME` maps a logical name like `card` to a specific declared class. The client does not send a full Java class name. This is far safer and more suitable for public APIs than enabling default typing or using `JsonTypeInfo.Id.CLASS` on untrusted data.

### Runtime Selection Is Not Runtime Class Definition

Two concepts must be separated:

- **Runtime selection:** the program chooses one of `CardPaymentDetails` or `BankTransferDetails` based on `kind`. Both classes are already on the classpath at build time, so Native Image can include them in the executable.
- **Runtime class definition:** the program receives a new JAR or bytecode after building and attempts to create a class that did not exist during native-image compilation. This is a different model and is not guaranteed by registering reflection hints.

With Native Image, use a finite, controlled, and tested list of subtypes. Never turn client-supplied data into a class name and call `Class.forName` arbitrarily.

## 4. Bean Validation on Nested Object Graphs

`@Valid` instructs the validator to traverse into the referenced object to validate its constraints. It does not by itself enforce a "non-null" constraint; therefore, the request uses both `@NotNull` and `@Valid`:

~~~java
public record CreateOrderRequest(
        @NotBlank String orderId,
        @NotNull @Valid PaymentDetails payment
) {
}
~~~

Meaning:

- `@NotBlank` requires `orderId` to have content after trimming.
- `@NotNull` requires `payment` to have a value.
- `@Valid` triggers cascade validation on the actual object instantiated by Jackson.
- If `payment` is `CardPaymentDetails`, that record's constraints are checked.
- If `payment` is `BankTransferDetails`, the bank-transfer subtype's constraints are checked.

If `@Valid` is omitted, the validator may check that `payment` is non-null without descending into it to check `token`, `lastFour`, or `accountReference`.

### Constraints on Collections and Maps

For lists of items, you can combine container element constraints and cascade validation:

~~~java
public record BulkOrderRequest(
        @NotEmpty
        List<@NotNull @Valid CreateOrderRequest> orders
) {
}
~~~

Each element must be non-null and validated according to `CreateOrderRequest` constraints. For maps, constraints can be applied to keys/values and cascade validation to values if values are nested objects.

### Validation Groups

When a DTO has different rules depending on create vs. update operations, validation groups can be used. Declare groups explicitly, activate the right group at the call site, and test each mode. Do not use groups merely to bypass constraints in native; metadata for constraints and validators must still be supported in the executable.

## 5. Custom Constraints and ConstraintValidator

Bean Validation allows defining custom constraints. For example, a payment reference code must follow a business format:

~~~java
package com.example.orders.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PaymentReferenceValidator.class)
public @interface ValidPaymentReference {

    String message() default "Payment reference is invalid";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
package com.example.orders.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class PaymentReferenceValidator
        implements ConstraintValidator<ValidPaymentReference, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        if (value == null || value.isBlank()) {
            return true;
        }

        return value.matches("[A-Z0-9-]{6,40}");
    }
}
~~~

Using the constraint on a DTO:

~~~java
public record BankTransferDetails(
        @NotBlank
        @ValidPaymentReference
        String accountReference
) implements PaymentDetails {
}
~~~

In Spring, `LocalValidatorFactoryBean` integrates `SpringConstraintValidatorFactory`, allowing custom `ConstraintValidator` implementations to receive dependency injection like Spring beans. A validator should have deterministic logic and avoid calling the network or database for every field unless explicitly required.

### When Validators or Constraints Are Discovered Dynamically

If the validator is referenced directly in `@Constraint(validatedBy = ...)` and the DTO is part of the AOT model, the framework has a basis to analyze that relationship. However, if the application loads mappings from `validation.xml`, properties files, plugins, or class names read from the runtime environment, AOT may not infer all required classes/resources.

In that case:

- Ensure mapping files are included in the image via resource hints if read from the classpath.
- Ensure the validator implementation is on the classpath at build time.
- Register reflection for types actually invoked via reflection if the framework does not automatically provide hints.
- Test every constraint on the native executable.

Do not assume that simply adding `@Valid` guarantees all custom validators and dynamic mappings are handled.

## 6. When Does Spring AOT Automatically Infer Hints?

Spring AOT can infer many reflection hints from the application structure. In particular, when request/response types appear directly in the method signatures of a `@RestController`, Spring usually detects the types needed for JSON binding.

Example:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        // ...
    }
}
~~~

In this case, `CreateOrderRequest` and `OrderResponse` appear explicitly in the controller signature. Spring AOT can infer the metadata needed for binding.

However, types may not appear in controller signatures, for instance:

- DTOs serialized/deserialized by `RestClient` or `WebClient` directly inside a method body.
- Concrete subtypes chosen only via a discriminator or custom deserializer.
- DTOs passed through a third-party library that uses reflection.
- Types read from configuration or mappings that Spring cannot analyze at build time.

In those situations, verify actual hints instead of assuming AOT always sees every class.

## 7. Registering Reflection Hints for DTOs and Subtypes

Spring provides `@RegisterReflectionForBinding` to register reflection metadata for binding. This annotation covers constructors, fields, properties, and record components of the specified types; it also registers types referenced transitively via properties/record components.

Example of registering the root DTO and subtypes chosen via discriminator:

~~~java
package com.example.orders.config;

import com.example.orders.api.BankTransferDetails;
import com.example.orders.api.CardPaymentDetails;
import com.example.orders.api.CreateOrderRequest;
import com.example.orders.api.OrderResponse;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        CreateOrderRequest.class,
        CardPaymentDetails.class,
        BankTransferDetails.class,
        OrderResponse.class
})
public class OrderJsonBindingConfiguration {
}
~~~

If the types are only used in a `@RestController`, this annotation might be redundant because Spring already infers the hints. The example above intentionally declares the concrete subtypes to make explicit the polymorphic type set supported by the API.

### When Using RestClient or WebClient Directly

Example client calling a partner service and binding the response into a DTO:

~~~java
@Component
@RegisterReflectionForBinding({
        PartnerCommand.class,
        PartnerResult.class
})
public class PartnerClient {

    private final RestClient restClient;

    public PartnerClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    public PartnerResult submit(PartnerCommand command) {
        return restClient.post()
                .uri("/commands")
                .body(command)
                .retrieve()
                .body(PartnerResult.class);
    }
}
~~~

The DTOs do not appear in a controller signature, so Spring AOT will not necessarily infer every binding requirement from inbound HTTP flows. Placing the annotation near the component that needs the hints keeps metadata tied to the right part of the application.

If using a custom `RuntimeHintsRegistrar` instead of annotations, you can register reflection via `RuntimeHints` and activate the registrar with `@ImportRuntimeHints`. Choose one approach intentionally; avoid registering an entire package if only a few DTOs need binding.

## 8. Verifying Generated Hints and Metadata

There are two things to verify:

1. Spring AOT has collected the hints contributed by the application.
2. Native Image has received the metadata and retained the types needed at runtime.

`@RegisterReflectionForBinding` takes effect only when the annotated element participates in Spring context/AOT processing. Placing the annotation on a class that is not discovered by Spring or not imported can prevent the expected hints from taking effect.

If contributing hints programmatically, you can use `BindingReflectionHintsRegistrar` to generate binding hints and `RuntimeHintsPredicates` to test them:

~~~java
import org.springframework.aot.hint.BindingReflectionHintsRegistrar;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void registersBindingHintsForPaymentSubtypes() {
    RuntimeHints hints = new RuntimeHints();

    new BindingReflectionHintsRegistrar().registerReflectionHints(
            hints.reflection(),
            CardPaymentDetails.class
    );

    assertThat(
            RuntimeHintsPredicates.reflection()
                    .onType(CardPaymentDetails.class)
    ).accepts(hints);
}
~~~

This is a unit-level check of hint contribution. It does not prove that the metadata was included in the native executable or that every Jackson runtime path works. End-to-end testing on the native binary is required.

### Reachability Metadata JSON

Native Image can also consume JSON metadata in `META-INF/native-image/<groupId>/<artifactId>/`. With the modern reachability metadata format, the reflection section can declare the required types and members. Illustrative example:

~~~json
{
  "reflection": [
    {
      "type": "com.example.orders.api.CardPaymentDetails",
      "allDeclaredConstructors": true,
      "allDeclaredFields": true,
      "allDeclaredMethods": true
    },
    {
      "type": "com.example.orders.api.BankTransferDetails",
      "allDeclaredConstructors": true,
      "allDeclaredFields": true,
      "allDeclaredMethods": true
    }
  ]
}
~~~

Do not copy broad metadata like this if Spring already generates sufficient hints. The required member categories depend on how Jackson/the validator accesses the DTO and on library versions. Prefer `@RegisterReflectionForBinding` for binding DTOs; use JSON metadata only for a specific reason and review it against the schema of your GraalVM version.

## 9. Distinguishing Jackson Errors, Validation Errors, and Business Errors

### JSON Cannot Be Deserialized

Cases:

- Malformed JSON syntax.
- String value cannot be converted to a number/date type.
- Missing or invalid discriminator `kind`.
- Subtype not in the allowed list.
- Custom deserializer throws an exception.

Spring MVC typically translates request body read errors into `HttpMessageNotReadableException`. Bean Validation has not run yet because the object was not successfully bound.

### Object Bound Successfully but Constraints Invalid

For example, `orderId` is blank or `lastFour` is not four digits. The controller receives the DTO, yet validation fails before invoking the method body. Spring MVC can throw `MethodArgumentNotValidException` for per-object parameter validation.

### Method-Level Validation

If constraints are placed directly on method parameters or return values, modern Spring MVC may apply method validation and throw `HandlerMethodValidationException`. This is a different exception from `MethodArgumentNotValidException`.

If using Spring-driven method validation on a service annotated with `@Validated`, the mechanism typically relies on an AOP proxy and may throw `ConstraintViolationException`. Determine whether validation is triggered at the controller or the service before writing exception handlers.

### Business Errors

For example, duplicate order ID or rejected payment method. These are not Jackson or Bean Validation errors. Use dedicated business exceptions and map them to appropriate status codes, such as `409 Conflict` or `422 Unprocessable Content` per the API contract.

## 10. Returning Structured Errors with ProblemDetail

Spring supports `ProblemDetail` per RFC 9457 for HTTP APIs. An error response can include standard fields such as `type`, `title`, `status`, `detail`, `instance`, plus extension properties.

Example `@RestControllerAdvice`:

~~~java
package com.example.orders.api;

import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail handleUnreadableBody(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body is malformed or contains an unsupported value."
        );
        problem.setTitle("Invalid JSON request");
        problem.setProperty("code", "REQUEST_BODY_INVALID");
        return problem;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleInvalidBody(
            MethodArgumentNotValidException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid."
        );
        problem.setTitle("Request validation failed");
        problem.setProperty(
                "errors",
                exception.getBindingResult().getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", Objects.toString(error.getCode(), "invalid"),
                                "message", Objects.toString(
                                        error.getDefaultMessage(),
                                        "Invalid value"
                                )
                        ))
                        .toList()
        );
        return problem;
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                exception.getStatusCode(),
                "One or more method parameters failed validation."
        );
        problem.setTitle("Method validation failed");

        return ResponseEntity
                .status(exception.getStatusCode())
                .body(problem);
    }
}
~~~

The validation error response structure might look like:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "errors": [
    {
      "field": "payment.token",
      "code": "NotBlank",
      "message": "must not be blank"
    }
  ]
}
~~~

For an invalid discriminator error, the response should only state that the request contains an unsupported type. Never return raw stack traces, internal class names, payment tokens, or sensitive payload contents to the client.

### Avoiding Duplicate Handling of Built-In Exceptions

Spring Boot can enable Problem Details for built-in MVC errors via configuration:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

If you write a custom `@ControllerAdvice` handling the same exceptions, understand advice ordering and avoid competing handlers. You can extend `ResponseEntityExceptionHandler` when you need to customize many built-in MVC exceptions, or keep a dedicated advice that handles only the errors the application intentionally owns.

## 11. Jackson 2, Jackson 3, and Version Differences

Spring Boot 3.x typically uses Jackson 2, where databind APIs live under the `com.fasterxml.jackson.databind` package.

Spring Boot 4 moves to Jackson 3 as the default choice. Jackson 3 changes the main group/package from `com.fasterxml.jackson` to `tools.jackson`, while `jackson-annotations` retains the `com.fasterxml.jackson.annotation` package for compatibility. Therefore, annotations in the examples such as `@JsonTypeInfo` and `@JsonSubTypes` still use `com.fasterxml.jackson.annotation`; custom serializers/deserializers and mapper APIs must be checked against the version in use.

Notes when upgrading:

- Do not accidentally mix Jackson 2 and Jackson 3 modules.
- Check whether third-party libraries require a specific major version.
- When writing custom serializers/deserializers, use the API of the major version managed by Spring Boot.
- Retest default behaviors, coercion, unknown properties, and polymorphic handling after upgrading.
- Do not take a Jackson 2 `ObjectMapper` example and assume the packages/APIs remain identical in Boot 4.

Native Image metadata also depends on the integration and version. Spring AOT can infer hints for standard binding paths, but additional JSON libraries or custom modules may need separate metadata.

## 12. Testing Valid Payloads, Validation Errors, and the Native Runtime

You should have tests for every discriminator branch. A test sending only `kind: "card"` does not prove `bank-transfer` works.

### Minimum Test Case Suite

| Payload/Scenario | Expected Outcome | Layer Tested |
| --- | --- | --- |
| `kind` is `card` with valid token | Creates `CardPaymentDetails` | Jackson subtype binding |
| `kind` is `bank-transfer` with valid account reference | Creates `BankTransferDetails` | Jackson subtype binding |
| Missing `kind` | Rejected if config requires type ID | Jackson |
| `kind` is `unknown` | HTTP 400, business logic not called | Jackson |
| Blank `orderId` | HTTP 400 with field error | Bean Validation |
| Malformed `card.lastFour` | HTTP 400 with nested field error | Cascade validation |
| Blank `bank.accountReference` | HTTP 400 with nested field error | Cascade validation |
| Malformed JSON syntax | HTTP 400 | Message conversion |
| Business rule rejects order | Defined business status | Exception mapping |
| Calling `RestClient`/`WebClient` with DTO | Request/response bound successfully | Programmatic JSON binding |

### Testing on the JVM

Use `MockMvc` or integration tests to verify:

- Both subtypes.
- Invalid discriminator.
- Constraints on the root DTO and nested DTOs.
- Malformed JSON.
- Error responses have the right status and extension fields.
- No tokens or secrets appear in error responses.

### Testing on the Native Executable

Build native using your project's toolchain:

~~~bash
# Maven project with native profile configured.
./mvnw -Pnative native:compile

# Gradle project with Native Build Tools configured.
./gradlew nativeCompile
~~~

Run the native executable and resend the same payloads from the table above. In particular, test subtypes selected via discriminator and DTOs used via `RestClient`/`WebClient`.

If native reports missing reflection registration:

1. Identify the exact class/member accessed by Jackson or the validator.
2. Verify that the class is on the classpath at build time.
3. Verify whether Spring AOT discovered the controller/client/DTO.
4. Add `@RegisterReflectionForBinding` for the root DTO and any subtypes not inferred.
5. Rebuild native and rerun the exact test that failed.

The Tracing Agent can run the application on the JVM with `-Dspring.aot.enabled=true` to capture dynamic accesses not yet recognized by static analysis or Spring. Exercise all subtype branches and client calls, then review the metadata before committing it into the build.

Do not conclude success merely because the native executable starts up. You must invoke the actual endpoints and polymorphic branches.

## 13. Security in Deserialization and Error Handling

JSON polymorphism is an input boundary. Restrict subtypes to an explicit logical list:

- Use `JsonTypeInfo.Id.NAME` and `JsonSubTypes` or an equivalent allowlist registry.
- Do not enable broad Jackson default typing for untrusted payloads.
- Do not take a class name from JSON and load it with `Class.forName`.
- Do not allow clients to pick internal implementations, validators, or plugins by class name.
- Limit request body size and object graph depth according to API needs.
- Check for sensitive data before logging; never put tokens into `ProblemDetail`.
- Separate validation errors that may be shown to clients from system errors that belong in internal logs.

Native Image does not eliminate an application's deserialization risks. Reachability metadata only retains the components needed at runtime; it does not turn an unsafe deserialization policy into a safe one.

## 14. Diagnosing Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JVM deserializes fine, but native reports missing registration | DTO/subtype needing reflection was not retained | Check AOT hints, add `@RegisterReflectionForBinding` |
| REST controller works in native, but `RestClient` fails | DTO used only in method body; Spring did not infer from controller signature | Register request/response DTOs on the client bean |
| Only one subtype fails | Concrete subtype not declared or lacks metadata | Register and test that subtype specifically |
| Jackson reports invalid type ID | `kind` is missing or does not match logical name | Check JSON and `@JsonSubTypes` list |
| Controller does not receive request, validation does not run | Jackson parse/binding failed earlier | Inspect root cause of `HttpMessageNotReadableException` |
| Nested field is invalid, yet request passes | Missing `@Valid` on parent field/parameter | Add cascade validation and retest |
| Custom validator is not invoked | Constraint not placed on right field/type, missing provider, or mapping not loaded | Check annotation, starter, and validator provider |
| Validator works on JVM, fails in native | Validator/mapping loaded dynamically or missing metadata/resources | Identify class/resource and register specific hints |
| Method validation throws unexpected exception | MVC method validation and service AOP validation are two different mechanisms | Identify where the constraint is placed and handle the right exception |
| Error response leaks internal details | Handler returns raw exception message/stack trace | Map to `ProblemDetail` with a stable message |

## 15. Hands-On Exercise: Order API with Two Payment Methods

Create a Spring Boot REST API with a `POST /orders` endpoint. Use the `CreateOrderRequest`, `PaymentDetails`, `CardPaymentDetails`, `BankTransferDetails`, and `OrderResponse` classes as in the examples above.

Steps:

1. Add `spring-boot-starter-validation`.
2. Declare subtypes using `@JsonTypeInfo(use = Id.NAME)` and `@JsonSubTypes`.
3. Use `@NotBlank`, `@NotNull`, `@Pattern`, and `@Valid` to validate both root and nested DTOs.
4. Create a controller accepting `@Valid @RequestBody CreateOrderRequest`.
5. Create a `@RestControllerAdvice` returning `ProblemDetail` for JSON and validation errors.
6. Add `@RegisterReflectionForBinding` for subtypes if they are not inferred by Spring AOT in the actual flow.
7. If a client calls a partner API via `RestClient`, register the client's request/response DTOs separately.
8. Run JVM tests with valid card, valid bank transfer, unsupported subtype, and invalid nested fields.
9. Build the native executable and resend the same payloads.
10. Verify that error responses contain no stack traces, internal class names, or payment tokens.
11. Record which classes were inferred automatically by Spring AOT, which required extra hints, and why.

### Self-Check Questions

1. Why must Jackson be able to instantiate the object before Bean Validation checks nested fields?
2. How does `@Valid` differ from `@NotNull`?
3. Why is `JsonTypeInfo.Id.NAME` with an explicit subtype list more appropriate than letting clients send class names?
4. Where does Spring AOT typically infer hints for `@RestController` DTOs?
5. When do DTOs used with `RestClient` or `WebClient` require `@RegisterReflectionForBinding`?
6. Why must concrete subtypes be registered if they appear only via a discriminator?
7. How does `MethodArgumentNotValidException` differ from `HandlerMethodValidationException`?
8. Why should malformed JSON errors and Bean Validation errors be classified separately?
9. Can Native Image deserialize a class installed after the executable has been built?
10. Why do passing JVM tests not prove that polymorphic binding works in native?

**Acceptance Criteria:** build polymorphic DTOs with a controlled subtype list; properly cascade Bean Validation across the object graph; classify Jackson, validation, and business errors; return stable `ProblemDetail` responses; correctly determine when Spring AOT generates hints automatically and when `@RegisterReflectionForBinding` is needed; and finally verify every subtype and error branch on the native executable.

## Official Documentation

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — JSON support: https://docs.spring.io/spring-boot/reference/features/json.html
- Spring Framework — Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses and ProblemDetail: https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html
- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
