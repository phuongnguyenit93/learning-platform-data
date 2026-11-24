# Validation at the Message-Receiving Boundary in Spring RSocket

## Objectives

When a peer sends a request over RSocket, the application receives data across another trust boundary. A payload may decode into the right Java type yet still contain invalid data: empty strings, negative numbers, lists missing elements, or nested fields violating rules. Validation at the message-receiving boundary rejects such data before business logic is invoked.

In Spring Framework, this flow is implemented through `RSocketMessageHandler`, `@MessageMapping` methods, payload decoders, and `PayloadMethodArgumentResolver`. Jakarta Bean Validation with `@Valid` or Spring's `@Validated` can be used, provided the handler is configured with an actual `Validator`.

## 1. Where does validation sit in the RSocket flow?

A request passes through the following high-level steps:

1. RSocket receives the frame and separates data and metadata.
2. Spring resolves the route and the matching `@MessageMapping` method.
3. A decoder in `RSocketStrategies` converts the data bytes into the declared Java type.
4. `PayloadMethodArgumentResolver` resolves the `@Payload` argument and runs validation if the parameter is annotated with `@Valid` or `@Validated`.
5. Only if the payload is valid does Spring invoke the handler method.
6. The handler runs business logic and produces a result or error according to the RSocket interaction contract.

The key point is that validation occurs after the payload is decoded into an object and before the logic inside the handler method executes. Consequently, there are two distinct categories of errors:

- **Protocol or decoding errors:** malformed frame, unreadable metadata, invalid JSON syntax, or inability to convert to the Java type. The decoder may raise an error before Bean Validation runs.
- **Data constraint errors:** the payload decoded into an object, but violates constraints such as `@NotBlank`, `@Positive`, or `@Size`. Spring Messaging reports validation errors with `MethodArgumentNotValidException`.

RSocket protocol validation and Bean Validation also serve different purposes. Protocol validation protects frame integrity; Bean Validation verifies data semantics and structure at the application level. A payload valid at the frame level can still be invalid at the business level.

## 2. `@Valid`, `@Validated`, and constraints

Place the validation annotation on the handler's payload parameter:

~~~java
@MessageMapping("orders.create")
public Mono<OrderAccepted> create(
        @Payload @Valid CreateOrder command) {
    // ...
}
~~~

- `@Valid` is a Jakarta annotation (`jakarta.validation.Valid`). It triggers validation using the default group and enables cascading validation into nested objects or elements annotated with `@Valid`.
- `@Validated` belongs to Spring (`org.springframework.validation.annotation.Validated`). Beyond triggering validation, it allows specifying validation groups, such as `@Validated(OnCreate.class)`.
- `@Payload` clarifies that the parameter extracts data from the message's data section. With `@MessageMapping`, this annotation may be omitted if the parameter type does not match another Spring-supported argument type; writing it explicitly is usually clearer and easier to maintain.

A DTO can use common constraints:

| Constraint | Meaning |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must be non-null and contain at least one non-whitespace character |
| `@NotEmpty` | String, collection, map, or array must not be empty |
| `@Size(min, max)` | Limits length or element count |
| `@Positive`, `@PositiveOrZero` | Number must be positive or non-negative |
| `@Min`, `@Max` | Bounds integer values |
| `@Email` | Basic email format check |
| `@Pattern` | Validates string against a regular expression |

Example DTO with nested validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public class CreateOrder {

    @NotBlank
    private String customerId;

    @NotEmpty
    @Valid
    private List<OrderLine> items;

    // getters and setters
}

public class OrderLine {

    @NotBlank
    private String sku;

    @Positive
    private int quantity;

    // getters and setters
}
~~~

`@NotEmpty` requires the `items` list to have elements. `@Valid` tells the validator to descend into each `OrderLine`, so `sku` and `quantity` are validated as well. With only `@NotEmpty`, constraints inside each line item would not cascade automatically.

You can create custom constraints with a `@Constraint` annotation and a class implementing `ConstraintValidator`. Use class-level constraints when rules span multiple fields, such as an end date having to be after a start date. Rules that depend on persisted data, permissions, inventory, or current state should be checked in the service/domain layer; they are not merely structural DTO validation.

## 3. Configuring Validator for RSocketMessageHandler

Having annotations on a DTO is not enough. The application must have a Bean Validation provider on the classpath and must supply a Spring `Validator` to the message handler.

Spring provides `LocalValidatorFactoryBean`, an adapter implementing both `jakarta.validation.Validator` and `org.springframework.validation.Validator`. It initializes the provider found on the classpath, such as Hibernate Validator.

Example configuration for Spring Framework 6.x with Jackson 2:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RSocketConfiguration {

    @Bean
    LocalValidatorFactoryBean rSocketPayloadValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies,
            @Qualifier("rSocketPayloadValidator")
            org.springframework.validation.Validator validator) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setValidator(validator);
        return handler;
    }
}
~~~

There are two independent configurations here:

- `RSocketStrategies` supplies encoders/decoders to convert between bytes and objects. Configure codecs matching the peer's actual MIME type and format.
- `RSocketMessageHandler.setValidator(...)` supplies the validator used to validate `@Payload` parameters.

When using Spring Boot, you can add `spring-boot-starter-validation` to bring a Bean Validation provider into the application. In a plain Spring Framework application, you need the Jakarta Bean Validation API along with a compatible provider, such as Hibernate Validator. `LocalValidatorFactoryBean` does not supply an implementation if no provider is on the classpath.

**Namespace and version note:** Spring Framework 6.x and later use `jakarta.validation.*`; Spring Framework 5.3 uses `javax.validation.*`. Do not mix annotation APIs with a provider from a different namespace. The codec example above uses Jackson 2, fitting Spring Framework 6.x. Spring Framework 7.0 supports Jackson 3 via `JacksonJsonEncoder` and `JacksonJsonDecoder`; `Jackson2JsonEncoder` and `Jackson2JsonDecoder` have been deprecated in favor of the new API. Choose the encoder/decoder pair matching your Spring and Jackson versions. Validator configuration does not depend on the Jackson choice.

If the application already has an `RSocketStrategies` or `RSocketMessageHandler` created by Spring Boot or shared configuration, attach the validator to the exact handler receiving requests. Creating another handler that is not used as the responder will not protect the actual endpoint. The handler must also be registered as the responder, for example via `RSocketServer.create(handler.responder())` or the active auto-configuration mechanism.

## 4. Handler validates payloads before business logic

Example order creation handler:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderResponder {

    private final OrderService orderService;

    public OrderResponder(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(
            @Payload @Valid CreateOrder command) {

        return orderService.create(command);
    }
}
~~~

When a peer sends the corresponding payload:

~~~json
{
  "customerId": "customer-42",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
~~~

the payload is decoded into `CreateOrder`, and then the constraints are checked. Only when validation succeeds does Spring invoke `create` and `orderService.create`.

If `customerId` is an empty string or `quantity` is 0, validation fails. The handler method is not invoked, so the service never receives malformed commands. This is the primary benefit of placing validation at the message-receiving boundary: every path calling the handler goes through the same check.

For validation groups, declare the group on the constraint:

~~~java
public interface OnCreate {}

public class CreateOrder {

    @NotBlank(groups = OnCreate.class)
    private String customerId;

    // ...
}
~~~

and select the group on the parameter:

~~~java
@MessageMapping("orders.create")
public Mono<OrderAccepted> create(
        @Payload @Validated(OnCreate.class) CreateOrder command) {
    return orderService.create(command);
}
~~~

If `@Valid` is used instead of `@Validated(OnCreate.class)`, the validator runs the default group. Constraints declared solely for `OnCreate` will not run during that validation pass.

## 5. Handling validation errors

For invalid payloads, Spring Messaging raises:

`org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`

This is a Spring Messaging exception. Do not confuse it with `org.springframework.web.bind.MethodArgumentNotValidException` commonly seen in Spring MVC; the two classes live in different packages and belong to two different processing pipelines.

Spring Messaging's exception can hold a `BindingResult`, containing object-level and field-level errors. You can convert them into a stable error structure for clients using `@MessageExceptionHandler`. Place the following handler method in the same controller that contains `@MessageMapping`:

~~~java
public record FieldViolation(String field, String message) {}

public record ValidationError(
        String code,
        List<FieldViolation> violations) {}

@MessageExceptionHandler
public Mono<ValidationError> handleInvalidPayload(
        MethodArgumentNotValidException exception) {

    BindingResult result = exception.getBindingResult();

    List<FieldViolation> violations =
            result == null
                    ? List.of()
                    : result.getFieldErrors().stream()
                            .map(error -> new FieldViolation(
                                    error.getField(),
                                    error.getDefaultMessage()))
                            .toList();

    return Mono.just(
            new ValidationError("INVALID_PAYLOAD", violations));
}
~~~

The records can be placed in separate files. The example above extracts field errors; if there are class-level constraints, include `getGlobalErrors()` in the response. `@MessageExceptionHandler` handles exceptions inside the controller and returns a result type via the message handling mechanism.

The example above illustrates turning an error into an application payload. The response contract must fit the interaction type and client. With Request-Response, the client can receive a structured error object. If the exception is not mapped, the error can terminate the RSocket interaction with an error signal. Fire-and-Forget has no response payload to return; in that case, define how errors are observed via logs, metrics, or a separate error channel.

When constructing errors returned to clients:

- Expose only controlled error codes, field names, and messages.
- Do not send stack traces, sensitive data, raw payload values, or internal validator details.
- Keep the error structure consistent across routes so clients can handle it easily.
- Distinguish decoding errors from constraint errors so clients know whether to fix the format or fix the values.

## 6. Stream payloads and metadata

RSocket supports interactions with a single payload or multiple payloads. In an annotated responder, `@MessageMapping` can accept synchronous payloads, `Mono<T>`, or `Flux<T>`; input and output cardinality determines the interaction type. Spring's reactive resolvers also support validation when the payload parameter is annotated with `@Valid` or `@Validated`.

For channels or streams, clearly define the data sequence format expected by the decoder, how an invalid element is handled, and whether the stream terminates or continues. Do not test only a single payload and assume a multi-element stream behaves properly on errors. Test valid elements, an invalid element mid-stream, and how the interaction terminates.

Payload and metadata are two different parts of an RSocket message:

- `@Payload` receives the data portion converted into an object by the decoder.
- `@Header` and `@Headers` receive metadata entries registered and extracted as headers.
- `@Valid` on a payload DTO does not automatically validate all metadata, route variables, or authentication credentials. Validate them through appropriate mechanisms while authenticating identity and verifying access permissions in the security layer.

Post-decode validation also does not replace frame size limits, memory limits, timeouts, or rate limits. An oversized payload can consume resources before an object is ever constructed for Bean Validation to inspect. Resource limits must be enforced at the transport, codec, and operational layers.

## 7. Testing validation at the boundary

Test at least three layers:

1. **DTO:** invoke the validator with valid and invalid objects to verify constraints, validation groups, and cascading validation work.
2. **Handler:** send an invalid payload and verify the service is not called. This proves invalid requests are blocked before business logic.
3. **RSocket end-to-end:** use `RSocketRequester` to send payloads over a real route, then verify the error response or error signal matches the designed contract.

A useful test matrix:

- Valid payload: `customerId = "customer-42"`, `quantity = 2`; service is called.
- Invalid payload: `customerId = " "`, `quantity = 0`; service is not called and client receives `INVALID_PAYLOAD` or an error signal as configured.
- Invalid JSON syntax: decoder reports an error; do not confuse this with `MethodArgumentNotValidException`.
- Payload with invalid nested element: verify `@Valid` actually cascades to each element.
- Stream payload with invalid element: verify exact stream and interaction behavior.

Do not test only the service directly or call the validator in a unit test and conclude the RSocket endpoint is protected. Handler configuration, decoder, and validator must all participate in integration tests.

## 8. Common errors

| Issue | Cause and Resolution |
| --- | --- |
| `@Valid` is present, yet invalid data reaches the handler | Bean Validation provider is not configured or `RSocketMessageHandler.setValidator` was not called; check the exact handler registered as responder |
| Outer DTO is validated, but nested objects are not | Missing `@Valid` on the field or element needing cascade |
| Malformed JSON syntax treated as constraint error | Decoder fails before Bean Validation; handle payload conversion errors separately |
| Imported wrong Spring MVC exception | Import the exception from package `org.springframework.messaging.handler.annotation.support` |
| Client validates so server skips validation | Client is not a trust boundary; the server must always validate received data |
| `@Valid` does not validate route or metadata | The annotation applies to the payload object; validate headers, routes, and security credentials separately |
| Using Bean Validation for database-dependent rules | Check state and permissions in the service/domain layer with proper concurrency and transaction handling |
| Oversized payloads spike load before validation | Bean Validation runs after decode; enforce frame/payload and resource limits at lower layers |

## 9. Implementation checklist

- [ ] Clear DTOs chosen for each route's payload.
- [ ] Appropriate constraints and `@Valid` added for nested objects.
- [ ] Bean Validation provider compatible with the Spring version is present.
- [ ] Spring `Validator` supplied to `RSocketMessageHandler` via `setValidator`.
- [ ] Decoder and MIME type match the payload format sent by clients.
- [ ] Error response or interaction termination defined for invalid payloads.
- [ ] Tested constraint errors, decode errors, and stream payloads.
- [ ] Service is not invoked when a payload violates constraints.
- [ ] Metadata, authorization, and resource limits handled at the proper layers.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): annotated responders, `@MessageMapping`, payloads, and interaction cardinality.
- [MessageMappingMessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): `setValidator` and the role of the reactive message handler.
- [PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/PayloadMethodArgumentResolver.html): payload decoding and validation with `@Valid`/`@Validated`.
- [MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html): Spring Messaging validation exception and `BindingResult`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): `LocalValidatorFactoryBean`, providers, and custom constraints.

