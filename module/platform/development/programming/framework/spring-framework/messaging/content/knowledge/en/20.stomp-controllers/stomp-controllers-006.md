# Payload Conversion and Validation with @Valid or @Validated

This guide focuses on STOMP controllers using Spring Messaging. When a client sends a STOMP message to a method annotated with @MessageMapping, Spring extracts the payload, converts it to the parameter's Java type, runs Bean Validation if the parameter is annotated appropriately, and only then invokes the method. Understanding this sequence helps distinguish JSON/type errors from business constraint violations.

## 1. Payload Processing Flow in STOMP

A message enters a controller through the following main steps:

1. The client sends a STOMP SEND frame over WebSocket. The frame has a destination and typically a content-type describing the body format.
2. Spring decodes the frame into a Spring Message, places it onto clientInboundChannel, and routes the destination to the matching @MessageMapping method.
3. The argument resolver extracts the payload. For a parameter annotated with @Payload, Spring uses the parameter type as the target type. If no other annotation handles the parameter, it is also assumed to be the payload by default; writing @Payload explicitly usually makes the method signature easier to read.
4. A MessageConverter converts the raw data to the target Java type. For example, JSON is converted into CreateOrderCommand by a JSON converter such as MappingJackson2MessageConverter.
5. If the parameter has @Valid or @Validated and Spring has an active Validator, Spring checks constraints on the newly converted object.
6. If both conversion and validation succeed, Spring invokes the controller method. The return value can be converted into an outbound payload and sent to the broker via the default destination or @SendTo/@SendToUser.

Therefore, conversion occurs before validation. The validator inspects an already instantiated Java object; it does not fix malformed JSON or automatically convert invalid strings into numbers.

## 2. Payload Conversion and content-type

In STOMP, @Payload extracts the message body and converts it to the parameter type. A converter is selected based on the payload, target type, and content type information. For JSON, clients should send content-type:application/json and a body whose structure matches the DTO.

Example of a STOMP SEND frame sent to an application destination:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"customerId":"C-001","quantity":2,"note":"Deliver during business hours"}
~~~

If the application destination prefix is configured as /app, the remaining destination /orders.create is matched against @MessageMapping("/orders.create"). This is an application handler destination; /topic and /queue are typically used for broker destinations that clients subscribe to.

A minimal configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The configuration above illustrates endpoints and destination prefixes. A real application must configure origins, authentication, authorization, and a broker suited to its deployment environment. A JSON converter must be present in the configured converter list; in typical Spring setups, Jackson can be used through MappingJackson2MessageConverter.

## 3. Enabling Bean Validation

With Spring Boot, you can add the following starters (versions are managed by Spring Boot dependency management):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

spring-boot-starter-validation brings the Bean Validation API and a compatible provider onto the classpath. If using Spring Framework directly, you need the appropriate messaging/websocket dependencies, a JSON library if using JSON, the Jakarta Validation API, and an implementation such as Hibernate Validator. Having only the annotation API without a provider is not enough to enforce constraints.

In a standard STOMP setup, Spring looks for a custom Validator first, may then reuse an existing MVC validator, or creates an OptionalValidatorFactoryBean if a Bean Validation implementation is found on the classpath. If no suitable validator is available, the default configuration may use a no-op Validator; in that case @Valid/@Validated appears in the signature but constraints are not actually checked. If you build your own message handler, argument resolver, or custom factory, ensure the Validator is passed into that configuration.

Spring Framework 6 and later use the Jakarta namespace, such as jakarta.validation.Valid and jakarta.validation.constraints.NotBlank. Spring Framework 5.x uses the corresponding javax.validation namespace. Do not mix javax annotation APIs with a Jakarta provider/stack or vice versa; use the namespace matching your project's Spring version and dependencies.

## 4. Declaring Constraints on DTOs

Receive client data using a dedicated DTO rather than binding directly to a JPA entity or internal object. Constraints describe data requirements at the message boundary.

~~~java
package com.example.messaging;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class CreateOrderCommand {

    @NotBlank(message = "customerId must not be blank")
    private String customerId;

    @NotNull(message = "quantity is required")
    @Positive(message = "quantity must be greater than 0")
    private Integer quantity;

    @Size(max = 200, message = "note must contain at most 200 characters")
    private String note;

    public CreateOrderCommand() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Commonly used constraints:

- @NotNull: value must not be null.
- @NotBlank: string must not be null and must contain at least one non-whitespace character.
- @NotEmpty: string, collection, or map must not be null and must not be empty.
- @Size(min, max): constrains string length or collection/map size.
- @Positive and @PositiveOrZero: checks for positive or non-negative numbers.
- @Min and @Max: constrains integer numeric values.
- @Email: checks email format according to the validator.
- @Pattern: checks string against a regular expression.

For numeric fields that may be omitted in JSON, a wrapper such as Integer is usually more useful than int: when the client omits the field, Integer can be null so @NotNull catches it; int receives the default value 0 and cannot distinguish a missing field from a field explicitly sent as 0.

Constraints on fields or getters can both be read by Bean Validation depending on provider configuration. Keep a consistent convention in your DTOs. For nested objects, place @Valid on the property that needs cascaded validation, for example:

~~~java
@NotNull
@Valid
private ShippingAddress address;
~~~

Without @Valid on the nested property, the validator may check that address is non-null without descending into the constraints inside ShippingAddress.

## 5. Using @Valid on @MessageMapping Parameters

@Valid is the standard Jakarta Validation annotation. Place it on the payload parameter to instruct Spring to validate the object after conversion succeeds.

~~~java
package com.example.messaging;

import jakarta.validation.Valid;
import java.util.List;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;

@Controller
public class OrderMessageController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(@Valid @Payload CreateOrderCommand command) {
        // Execute the use case after the payload has passed validation.
        return new OrderCreated(command.getCustomerId(), command.getQuantity());
    }

    @MessageExceptionHandler(MethodArgumentNotValidException.class)
    @SendToUser("/queue/errors")
    public ValidationError handleInvalidPayload(MethodArgumentNotValidException ex) {
        BindingResult result = ex.getBindingResult();

        List<FieldViolation> violations = result == null
                ? List.of()
                : result.getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getDefaultMessage()))
                    .toList();

        return new ValidationError("INVALID_PAYLOAD", violations);
    }

    public record OrderCreated(String customerId, Integer quantity) {
    }

    public record FieldViolation(String field, String message) {
    }

    public record ValidationError(String code, List<FieldViolation> violations) {
    }
}
~~~

When a client sends a valid message, the controller is invoked and the result is sent to /topic/orders. When the payload converts successfully but violates a constraint, Spring throws MethodArgumentNotValidException from the org.springframework.messaging.handler.annotation.support package; the create method is not executed. An exception handler in the same controller can turn the error into a stable response sent to the user destination /user/queue/errors. Clients must subscribe to this destination to receive errors.

Pay attention to importing MethodArgumentNotValidException from Spring Messaging as shown in the example. This is a different package from the identically named exception in Spring Web MVC. Do not mistakenly import org.springframework.web.bind.MethodArgumentNotValidException when handling parameter errors for STOMP messages.

## 6. Differences Between @Valid and @Validated

| Annotation | Origin | Primary Usage |
| --- | --- | --- |
| @Valid | Jakarta Validation | Triggers validation for the default group; also used to cascade validation into nested objects |
| @Validated | Spring Framework | Triggers validation and allows specifying validation groups or using meta-annotations |

If you only need to check constraints in the default group, using @Valid is the simplest choice:

~~~java
@MessageMapping("/orders.create")
public void create(@Valid @Payload CreateOrderCommand command) {
    // ...
}
~~~

When a DTO has different rules depending on the operation, you can declare groups and use @Validated:

~~~java
public interface OnCreate {
}

public class CreateOrderCommand {

    @NotBlank(groups = OnCreate.class)
    private String customerId;

    @NotNull(groups = OnCreate.class)
    @Positive(groups = OnCreate.class)
    private Integer quantity;

    // Constructor/getter/setter
}
~~~

~~~java
@MessageMapping("/orders.create")
public void create(
        @Validated(OnCreate.class) @Payload CreateOrderCommand command) {
    // Only proceed when constraints in OnCreate pass.
}
~~~

Constraints assigned specifically to OnCreate do not run automatically when using @Valid with the default group alone. When using groups, ensure the method selects the right group and constraints are assigned to the right group. If you want a constraint to run in multiple groups, declare multiple groups on that constraint. For nested objects, @Valid is still needed on the property to cascade; groups propagate according to Bean Validation group conversion rules if configured.

## 7. Distinguishing Conversion Errors from Validation Errors

These two error categories happen at two different stages:

| Scenario | Outcome |
| --- | --- |
| Malformed JSON | MessageConverter fails to instantiate the DTO; typically a conversion error such as MessageConversionException |
| JSON has quantity as a string that cannot be converted to Integer | Conversion fails before validation |
| Valid JSON, quantity = -2 | DTO is instantiated; @Positive fails and throws MethodArgumentNotValidException |
| Valid JSON, customerId is an empty string | DTO is instantiated; @NotBlank fails |
| All fields valid | Controller method is invoked |

For example, the following body is valid JSON and can be converted into the DTO, but fails constraint checks:

~~~json
{
  "customerId": " ",
  "quantity": -2,
  "note": "Data validation test"
}
~~~

In this example, @NotBlank and @Positive detect the violations. Conversely, if quantity is "two" while the DTO declares Integer, the converter cannot construct an object of the right type; Bean Validation has no valid object yet to inspect. You can write a separate @MessageExceptionHandler for MessageConversionException if you want to return a uniform error format, but you should not merge parse/conversion errors and constraint errors into the same technical message.

## 8. Error Handling and Response Design

With STOMP, validation errors do not automatically become an HTTP 400 like some @RequestBody flows in Spring MVC. Decide how to respond appropriately for your application protocol:

- Use @MessageExceptionHandler to handle exceptions from message handler methods.
- Use @SendToUser("/queue/errors") when errors should be returned to a user/session-specific queue; clients typically subscribe to /user/queue/errors.
- Return a stable error code and a list of displayable fields/messages. Never send stack traces, SQL, internal class names, or sensitive details to clients.
- If you want to handle conversion errors, register a separate handler for MessageConversionException and return a code such as INVALID_MESSAGE_FORMAT.
- If you need error handling across multiple controllers, consider advice mechanisms supported by Spring Messaging in your version; verify the actual scope of exception handlers rather than assuming a handler inside one controller applies application-wide.

Default Bean Validation error messages can vary by provider, locale, and message bundle. In a stable API, define explicit messages or error codes and map them into your application's response DTO.

## 9. Common Pitfalls and How to Check

1. Annotations are present yet invalid data still slips through: check whether a Bean Validation provider is on the classpath, whether the jakarta/javax namespace matches your version, and whether the Validator is actually wired into the message handler/resolver.
2. Only @Valid on the parameter, so child objects are not validated: add @Valid to the nested property; also ensure the child object has constraints.
3. @Validated does not run expected constraints: check the groups on the annotation and the group passed to @Validated. Constraints in Default do not run automatically when only a custom group is requested.
4. JSON fails to map to the DTO: check STOMP content-type, whether a converter supports that MIME type, JSON property names, data types, and DTO constructors/accessors.
5. Validation misses absent fields: use wrapper types with @NotNull if you need to distinguish null from primitive default values.
6. Client does not receive errors: check that @MessageExceptionHandler handles the right exception, the response is sent to the right destination, and the client subscribed to /user/queue/errors.
7. Using entities directly as payloads: avoid letting clients control internal fields such as id, owner, role, or status. Use command DTOs and verify permissions in the service layer.

## 10. Testing

Test conversion, validation, and error-response paths separately:

- Valid payload: controller is invoked exactly once and the result is sent to the expected destination.
- Missing customerId or whitespace-only string: @NotBlank fails.
- Missing quantity: @NotNull fails.
- quantity equal to 0 or negative: @Positive fails.
- note exceeds limit: @Size fails.
- Malformed JSON or quantity cannot convert to Integer: conversion handler is called; validation handler is not blamed.
- DTO with nested object: inner constraints are only checked when cascaded with @Valid.
- Validation groups: only constraints belonging to the selected group are enforced as configured.
- Validation error: response includes a stable code, offending field, and clear message; no internal details leak.

Client-side validation only improves input UX. The server must still validate every payload because clients can bypass or spoof UI checks. Bean Validation also does not replace authentication, authorization, or business rules that require querying data; conditions such as whether the sender has permission to edit an order or whether the order is still in an updatable state must be checked in the service/domain layer.

## 11. References

- [Annotated Controllers — Spring Framework, STOMP](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html): supported arguments in @MessageMapping, payload conversion, and @Valid/@Validated support.
- [PayloadMethodArgumentResolver — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html): how the resolver converts and validates payloads.
- [MethodArgumentNotValidException — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html): exception and BindingResult for validation errors in Spring Messaging.
- [AbstractMessageBrokerConfiguration — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/simp/config/AbstractMessageBrokerConfiguration.html): how the Validator is configured for message handler payloads.
- [Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): Validator fundamentals and validation in Spring.
