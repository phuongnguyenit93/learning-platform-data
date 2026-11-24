# Testing Schema Compatibility, Authorization, and Invalid Data

> Scope: testing message contracts in Spring Framework Messaging, especially with RSocket and Project Reactor. The goal is to detect schema changes that break consumers, ensure only authorized principals can invoke routes, and reject malformed payloads or business-rule violations before causing side effects.

## 1. Why Must These Three Layers Be Tested Separately?

A message passes through multiple stages: receiving a frame or message, authenticating and authorizing, decoding the payload, checking the contract, validating data, and only then executing business logic. Each stage has different failure types and testing boundaries.

- **Schema compatibility** answers: do producers and consumers on different versions understand the same message?
- **Authorization** answers: is the authenticated identity allowed to invoke this route or perform this action?
- **Data validation** answers: does the payload conform to the required structure, required fields, types, value ranges, and business invariants?

Do not lump every error case into a single "message failed" test. If a test merely asserts that a request produced an error, a consumer might reject a new schema due to a parse failure, or reject an authorized user due to a validation failure, while the test still passes. Each test must verify both the root cause and the expected outcome.

A typical checking flow:

1. Transport receives payload and metadata.
2. Spring Security authenticates and applies access policies for the RSocket exchange/route.
3. Codec decodes data into Java objects.
4. Message argument resolver validates payloads annotated with `@Valid` or `@Validated`.
5. Handler calls service; service further enforces business permissions and required invariants.
6. Results or errors are returned to the requester according to the communication contract.

In RSocket, data and metadata are two separate sections. Metadata may contain routes or security tokens; data carries the payload. Therefore, JSON payload tests and authentication metadata tests must cover both parts. RSocket supports Request-Response, Request-Stream, Channel, and Fire-and-Forget; tests must use the exact interaction model of the handler. A Fire-and-Forget call only confirms the message was sent, not that the handler processed it successfully.

## 2. Testing Schema Compatibility

### 2.1. Compatibility Is a Relationship Between Producer and Consumer

Do not test only whether a JSON payload deserializes into the current DTO. Test all version combinations that the system must actually support.

| Producer | Consumer | Test Question |
|---|---|---|
| Old version | New consumer | Can the new consumer read previously stored messages? |
| New version, added optional field | Old consumer | Does the old consumer ignore the new field per published policy? |
| New version | New consumer | Does the new consumer understand the new field, type, and semantics? |
| Breaking version | Old consumer | Does the old consumer reject it explicitly instead of misinterpreting it? |
| Replayed payload from storage | Current consumer | Can historical messages still be decoded and processed properly? |

For a compatible change such as adding an optional field, older consumers usually need to ignore unknown fields, while newer consumers must tolerate the new field being absent in older messages. This must be an intentional policy of the serializer and schema, not an accidental library default.

For breaking changes, bump the major/schema version per system conventions and reject unsupported versions. Do not guess new schemas by deserializing with old DTOs.

### 2.2. Changes That Need Testing

- Adding optional fields and required fields.
- Removing fields or renaming fields.
- Changing types, such as number to string or timestamp to epoch.
- Changing units or business meaning while keeping the same field name.
- Changing nullability, default, or enum rules.
- Changing nested structures, collections, or generic types.
- Changing serialization of dates/times, decimals, UUIDs, and binary data.
- Old payloads stored in databases, outboxes, brokers, or dead-letter queues.
- Consumers running concurrently with multiple producer versions during rolling deployments.

Adding a field can often be structurally compatible, yet not automatically semantically compatible. For example, adding `currency` is safe when old consumers can ignore it and new consumers have clear defaults/validation. Changing `amount` from "pre-tax" to "post-tax" without changing the name or version breaks the contract even though the JSON still parses.

### 2.3. Using Fixed Fixtures

Store representative messages in `src/test/resources/contracts/`, for example:

- `order-created-v1.json`: payload emitted by the old producer.
- `order-created-v1-with-note.json`: same schema version, with a new optional field.
- `order-created-v2-breaking.json`: new version with incompatible changes.
- `order-created-invalid.json`: syntactically valid JSON that is missing or has invalid business data.

Fixtures should be reviewed as part of the API contract. Do not generate fixtures with the very serializer class under test and immediately deserialize them back; doing so can mask breaking changes when producer and consumer drift together in the wrong direction.

### 2.4. Compatibility Testing with Jackson 3

The example below uses Jackson 3, the default JSON mapper in Spring Boot 4.x. The mapper is explicitly configured to allow older consumers to ignore extra fields. DTO V1 lacks the `note` field; DTO V2 has it while accepting old data when the field is absent.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import static org.junit.jupiter.api.Assertions.*;

class MessageSchemaCompatibilityTests {

    private final JsonMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    record OrderCreatedV1(String orderId, BigDecimal total) {}

    record OrderCreatedV2(
        String orderId,
        BigDecimal total,
        String note
    ) {}

    private static final String V1 = """
        {
          "schemaVersion": 1,
          "messageId": "evt-1001",
          "occurredAt": "2026-11-07T14:00:00Z",
          "data": {
            "orderId": "ORD-1001",
            "total": 125000.00
          }
        }
        """;

    private static final String V1_WITH_OPTIONAL_FIELD = """
        {
          "schemaVersion": 1,
          "messageId": "evt-1002",
          "occurredAt": "2026-11-07T14:01:00Z",
          "data": {
            "orderId": "ORD-1002",
            "total": 99000.00,
            "note": "gift wrap"
          }
        }
        """;

    private static final String V2_BREAKING = """
        {
          "schemaVersion": 2,
          "messageId": "evt-2001",
          "occurredAt": "2026-11-07T14:02:00Z",
          "data": {
            "id": "ORD-2001",
            "total": "125000.00"
          }
        }
        """;

    @Test
    void newConsumerReadsMessageFromOldProducer() throws Exception {
        JsonNode envelope = mapper.readTree(V1);

        assertSupportedVersion(envelope.get("schemaVersion").asInt());

        OrderCreatedV2 data = mapper.readValue(
            envelope.get("data").toString(),
            OrderCreatedV2.class
        );

        assertEquals("ORD-1001", data.orderId());
        assertEquals(0, data.total().compareTo(new BigDecimal("125000.00")));
        assertNull(data.note());
    }

    @Test
    void oldConsumerIgnoresAnAddedOptionalField() throws Exception {
        JsonNode envelope = mapper.readTree(V1_WITH_OPTIONAL_FIELD);

        assertSupportedVersion(envelope.get("schemaVersion").asInt());

        OrderCreatedV1 data = mapper.readValue(
            envelope.get("data").toString(),
            OrderCreatedV1.class
        );

        assertEquals("ORD-1002", data.orderId());
        assertEquals(0, data.total().compareTo(new BigDecimal("99000.00")));
    }

    @Test
    void consumerRejectsAnUnsupportedBreakingVersion() throws Exception {
        JsonNode envelope = mapper.readTree(V2_BREAKING);

        assertThrows(
            UnsupportedSchemaVersionException.class,
            () -> assertSupportedVersion(envelope.get("schemaVersion").asInt())
        );
    }

    private static void assertSupportedVersion(int version) {
        if (version != 1) {
            throw new UnsupportedSchemaVersionException(version);
        }
    }

    static class UnsupportedSchemaVersionException extends RuntimeException {
        UnsupportedSchemaVersionException(int version) {
            super("Unsupported message schema version: " + version);
        }
    }
}
~~~

In this example, the `note` field is added while keeping `schemaVersion = 1` because it is optional and the compatibility policy allows both sides to read it. Version 2 represents a breaking contract change, so the V1 consumer rejects it before attempting to interpret the payload. In real systems, version-bumping rules must be defined consistently: some organizations bump the version for every schema change, while others bump only the major version for incompatible changes.

Jackson 3 defaults differ from Jackson 2 on certain features. Configure the mapper used in tests identically to the production mapper; do not rely on a custom test mapper whose configuration differs from the real RSocket codec.

## 3. Testing Message Authorization

### 3.1. Authentication and Authorization Are Two Different Checks

- **Authentication** verifies who the caller is, such as validating a JWT or login credentials.
- **Authorization** decides whether the authenticated principal has permission to perform the action on a specific route/resource.

A valid JWT does not mean the caller is permitted to invoke every route. Test invalid tokens, expired tokens, principals without authorities, wrong roles, and valid roles.

Never read a user ID or role from the payload as proof of access rights. Clients can forge payloads. Identity and permissions must come from the `SecurityContext`/`Authentication` verified by Spring Security.

### 3.2. Route-Based RSocket Authorization

Spring Security supports `authorizePayload` to apply rules to RSocket exchanges. Rules are evaluated in order; the first matching rule applies. Place specific rules before fallback rules and deny by default.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.interceptor.PayloadSocketAcceptorInterceptor;
import org.springframework.security.config.Customizer;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(RSocketSecurity rsocket) {
        rsocket
            .authorizePayload(authorize -> authorize
                .route("orders.create").hasRole("ORDER_WRITER")
                .route("orders.read").hasRole("ORDER_READER")
                .anyRequest().denyAll()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

JWT configuration requires a `ReactiveJwtDecoder` matching the system's issuer or verification keys. If using Simple Authentication, configure `simpleAuthentication` and the corresponding encoder instead of `jwt`.

In this example:

- `orders.create` is allowed only for principals with authority `ROLE_ORDER_WRITER`.
- `orders.read` is allowed only for principals with authority `ROLE_ORDER_READER`.
- Other requests are denied under the allowlist policy.
- Exchanges matching no rule are denied.

Do not forget to authorize secondary exchanges such as channels or metadata pushes if they can cause side effects. The `anyRequest` rule matches only request-type payloads; `anyExchange` is the broader fallback.

### 3.3. Credentials in SETUP or Per Request?

RSocket can authenticate when opening a connection or on individual requests:

- If a connection belongs to a single user, authentication in SETUP may be appropriate.
- If multiple users share one connection to a service, credentials must be attached to each request so the server distinguishes each user's principal.
- Some systems authenticate the client/service in SETUP and the end user on each request.

Tests must mirror the real model. If production sends tokens in request metadata while tests authenticate only in SETUP, tests do not cover the real credential path.

Example of sending a bearer token in request metadata:

~~~java
MimeType authenticationMimeType = MimeType.valueOf(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

BearerTokenMetadata token = new BearerTokenMetadata(jwt);

Mono<OrderAccepted> response = requester
    .route("orders.create")
    .metadata(token, authenticationMimeType)
    .data(command)
    .retrieveMono(OrderAccepted.class);
~~~

If credentials are sent in SETUP, use `setupMetadata(token, authenticationMimeType)` when building the requester. Do not log tokens or commit real tokens in repository fixtures.

### 3.4. Testing Reactive Method Security

Route authorization and service authorization are two distinct layers. Services can be protected with `@PreAuthorize` to prevent an internal caller or alternative call path from bypassing route rules.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class OrderCommandService {

    @PreAuthorize("hasAuthority('orders:write')")
    Mono<String> create(String orderId) {
        return Mono.just(orderId);
    }
}
~~~

Enable reactive method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Test permissions with `@WithMockUser` and `StepVerifier`:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
    MethodSecurityConfiguration.class,
    OrderCommandService.class
})
class OrderCommandServiceSecurityTests {

    @Autowired
    OrderCommandService service;

    @Test
    void anonymousCallerIsDenied() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(authorities = "orders:read")
    void readerCannotCreateOrder() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(authorities = "orders:write")
    void writerCanCreateOrder() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectNext("ORD-1001")
            .verifyComplete();
    }
}
~~~

With reactive method security, the security context propagates via the Reactor Context. Use `StepVerifier` to subscribe to the publisher in tests. Do not call `block()` before checking the security context because that can drop the context the test needs to verify.

`@WithMockUser` above tests method security. It does not by itself test the JWT decoder, RSocket metadata, `PayloadSocketAcceptorInterceptor`, or route matchers. Those components require integration tests through a real RSocket server and requester.

## 4. Testing Invalid Data

### 4.1. Distinguishing Syntax Errors, Schema Errors, and Business Errors

| Error Type | Example | Detecting Layer |
|---|---|---|
| Invalid JSON/codec | JSON missing brace, number cannot convert to target type | Decoder/MessageConverter |
| Invalid schema structure | Missing required field, wrong type, unsupported version | Schema/contract validation |
| Invalid data constraints | Blank ID, negative amount, malformed currency | Bean Validation |
| Invalid business invariants | Order already closed, account does not belong to user | Domain/service validation |
| Unauthorized | Caller lacks permission to create an order | Spring Security |

A payload can be valid JSON yet still be invalid in business terms. For example, `{"orderId":"","amount":-10}` parses into an object, yet must not enter the order-creation service.

### 4.2. Bean Validation for Message DTOs

Use Jakarta Bean Validation to declare constraints directly on the DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record CreateOrder(
    @NotBlank
    String orderId,

    @NotNull
    @DecimalMin("0.01")
    BigDecimal amount,

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    String currency
) {
}
~~~

Meaning of the constraints:

- `@NotBlank`: string is non-null, non-empty, and contains non-whitespace characters.
- `@NotNull`: required field must have a value.
- `@DecimalMin`: amount must be greater than or equal to the specified threshold.
- `@Pattern`: currency consists of three uppercase letters in this example.

Bean Validation does not decide every business rule by itself. For instance, `amount` may need to be greater than 0, while the maximum cap depends on account tier or transaction type; that rule may need to be checked inside the service.

### 4.3. Validating @MessageMapping Payloads

Spring Messaging supports validation when a handler's payload parameter is annotated with `@Valid` or `@Validated`. When validation fails, `PayloadMethodArgumentResolver` raises `MethodArgumentNotValidException`.

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class OrderRSocketController {

    private final OrderCommandService service;

    OrderRSocketController(OrderCommandService service) {
        this.service = service;
    }

    @MessageMapping("orders.create")
    Mono<OrderAccepted> create(@Valid @Payload CreateOrder command) {
        return service.create(command);
    }
}
~~~

Ensure the RSocket message handler is configured with a Spring `Validator`/Bean Validation provider. For manually configured handlers, `MessageMappingMessageHandler.setValidator(...)` is the configuration point for validating `@Payload` parameters. Spring Boot can provide the corresponding infrastructure when the validation dependency is present, while custom handlers must have their actual configuration verified.

Validation occurs at the handler boundary before calling the service. If data is invalid, do not write to the database, emit events, or call external systems. Tests should verify both the returned error and that the service was not called.

### 4.4. Unit Testing Constraints Directly

You can test DTOs with the Jakarta Validator without starting an RSocket server:

~~~java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CreateOrderValidationTests {

    @Test
    void rejectsBlankIdNegativeAmountAndMalformedCurrency() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            CreateOrder invalid = new CreateOrder(
                " ",
                new BigDecimal("-10.00"),
                "US"
            );

            Set<String> invalidFields = validator.validate(invalid)
                .stream()
                .map(error -> error.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertTrue(invalidFields.contains("orderId"));
            assertTrue(invalidFields.contains("amount"));
            assertTrue(invalidFields.contains("currency"));
        }
    }
}
~~~

This test verifies constraints on the DTO. It does not yet prove that the Spring RSocket handler actually attaches the validator to its argument resolver. Therefore, at least one integration test is still needed to send an invalid payload over RSocket and confirm that the handler/service produces no side effects.

## 5. RSocket Integration Tests for Authorization and Payloads

An important integration test should start the RSocket server on a dedicated test port, connect via `RSocketRequester`, send authentication metadata, and invoke routes just like a production client.

Use a test matrix:

| Principal/Token | Route | Expected Result | Side Effect |
|---|---|---|---|
| No token | `orders.create` | Rejected | Service not invoked |
| Bad signature/expired token | `orders.create` | Authentication fails | Service not invoked |
| Role `ORDER_READER` | `orders.create` | Authorization denied | No order written |
| Role `ORDER_WRITER` | `orders.create` | Valid request processed | Exactly one order created |
| Role `ORDER_READER` | `orders.read` | Read permitted | No write side effects |
| Valid role | Undeclared route | Rejected by fallback | Handler not invoked |
| Role `ORDER_WRITER` | `orders.create`, invalid payload | Validation fails | No order written |
| Role `ORDER_WRITER` | `orders.create`, valid payload | Succeeds | Accurate data written |

Example test pattern for a requester built with a read-only user's token:

~~~java
@Test
void readerCannotCreateOrder() {
    RSocketRequester readerRequester = requesterFor(readerToken);

    StepVerifier.create(
        readerRequester
            .route("orders.create")
            .data(validCreateOrder)
            .retrieveMono(OrderAccepted.class)
    )
    .expectError()
    .verify();

    verify(orderCommandService, never()).create(any());
}
~~~

`requesterFor` is a test helper that connects to the test port and attaches the token exactly as configured by the application: in SETUP or in per-request metadata. A complete test needs to initialize the server, decoder/encoder, valid test tokens, mock or spy services, and close the requester/server after each test.

Do not check only the exception. Verify that the service was not called or the database did not change when the caller is rejected. This catches cases where a handler accidentally performs side effects before permissions are checked.

### 5.1. Testing Invalid Payloads Over RSocket

Send a syntactically valid JSON payload that violates Bean Validation, such as a negative amount. Verify:

- The request returns an error matching the application's error contract.
- The error can be classified as a validation failure.
- The handler/service performs no write operations.
- No stack traces, SQL, tokens, or internal details are returned to the caller.

Then send malformed JSON or a wrong type, such as `amount` as an object instead of a decimal. This error happens during decode/conversion, prior to Bean Validation. Test these two cases separately to avoid turning decode failures into a generic "invalid business data" message.

RSocket does not return HTTP status codes for requests like REST does. Verify the RSocket error frame/application error code and error payload defined by the application. On the test client, exceptions may be wrapped by RSocket/Reactor layers; assert stable error types or error codes promised by the API rather than fragile internal message strings.

## 6. Testing Layer Ordering and Independence

Tests must prove the following:

- An unauthorized user cannot cause side effects even with a valid payload.
- An authorized user is still rejected if the payload is invalid.
- A valid payload does not make an unauthorized user authorized.
- Unsupported schema versions are rejected explicitly, even if the inner payload happens to parse.
- Retried/redelivered messages do not duplicate side effects when idempotency is required.
- Validation failures are not retried like transient network errors.
- Authorization failures are not turned into success fallbacks.
- Error handlers do not leak sensitive payload contents or SecurityContext details.

It is not necessary to rigidly lock down internal ordering across every interceptor if the framework may vary it. Verify the security boundaries and observable contract: callers are denied access, services do not run, data remains unchanged, and returned errors belong to the right category.

## 7. Organizing the Test Suite

Tests should be grouped by speed and purpose:

1. **DTO unit tests**: Bean Validation, constructor invariants, enums, decimals, timestamps, and size limits.
2. **Schema contract tests**: old/new producer fixtures, supported versions, added fields, removed fields, and incompatible changes.
3. **Service authorization tests**: `@PreAuthorize`, read/write permissions, anonymous callers, and principals with wrong authorities.
4. **Handler tests**: `@MessageMapping`, `@Valid`, exception mapping, and skipping service calls when validation fails.
5. **RSocket integration tests**: real connections, route metadata, credentials, codecs, and error frames.
6. **Persistence/consumer tests**: deduplication, transaction rollback, retries, outbox, and historical fixture replay.

Run fast unit tests on every change; run integration tests in CI before merge or release. Contract fixtures should be verified in CI for both producers and consumers if the two projects deploy independently.

### 7.1. Basic Test Dependencies with Spring Boot 4.1.x

A Spring Boot module can use the parent's dependency management to align versions:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
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

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot 4 uses Jackson 3 as the default JSON mapper. If the application still uses Jackson 2 or a custom codec, use the exact mapper and decoder used in production RSocket in your contract tests. Testing with a differently configured mapper can yield results that diverge from runtime behavior.

## 8. Common Mistakes When Writing Tests

1. **Testing only serialization and deserialization of the same DTO.** Both sides change together, masking producer/consumer version drift. Use fixed fixtures from prior versions.
2. **Testing only the happy path.** Add tests for missing tokens, wrong roles, unsupported versions, malformed JSON, and constraint violations.
3. **Using `@WithMockUser` and concluding RSocket JWT works.** This annotation mocks the security context for method security; it does not test token metadata, JWT decoders, or RSocket interceptors.
4. **Asserting only that an exception occurred.** Assert the error type/code and verify no side effects happened.
5. **Trusting a `userId` field inside the message.** Use the authenticated principal to identify the user; enforce resource permissions using server-side data.
6. **Ignoring unknown fields without a policy.** Ignoring unknown fields enables additive compatibility, yet can hide typos. Use contract tests, schema validation, and appropriate logs/metrics.
7. **Checking permissions only on the client.** The client UI can hide buttons, yet the server must still enforce authorization.
8. **Using broad roles for every route.** Separate read, write, admin, and per-resource permissions as business rules require.
9. **Validating only at the transport layer.** Internal consumers, replays, or batch jobs may call services without going through RSocket handlers. Keep key invariants at the service/domain boundary.
10. **Putting the entire payload in error messages.** Log safely using message ID, route, error category, and field path; mask or omit sensitive data.

## 9. Pre-Release Message Contract Checklist

- [ ] Fixtures exist for every still-supported schema version.
- [ ] New consumers can read old messages according to compatibility policy.
- [ ] New producers do not break old consumers when adding compatible fields only.
- [ ] Consumers reject unsupported schema versions.
- [ ] Tests exist for malformed JSON, wrong types, and missing required fields.
- [ ] Tests exist for Bean Validation and business invariants.
- [ ] Tests exist for anonymous callers, invalid tokens, wrong roles, and valid roles.
- [ ] Integration tests verify metadata authentication on real RSocket routes.
- [ ] Unauthorized requests do not invoke services or cause side effects.
- [ ] Invalid payloads do not write to the database, emit events, or call downstream systems.
- [ ] Retries/redeliveries do not cause duplicate processing when idempotency is required.
- [ ] Error responses do not expose tokens, stack traces, or sensitive data.
- [ ] Tests use the exact same codecs/mappers and security configuration as production.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, annotated responders, data, and metadata.
- [Spring Framework Javadoc — PayloadMethodArgumentResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html): validation for `@Valid` or `@Validated` payloads, and `MethodArgumentNotValidException`.
- [Spring Framework Javadoc — MessageMappingMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): configuring Validator for `@Payload`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Bean Validation and LocalValidatorFactoryBean.
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/rsocket.html): authentication metadata, route authorization, and authorizePayload.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/7.0/reactive/test/method.html): testing reactive method security with `@WithMockUser` and `StepVerifier`.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/): test support, JUnit Jupiter, and testing dependencies.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3 and configuring JsonMapper.
