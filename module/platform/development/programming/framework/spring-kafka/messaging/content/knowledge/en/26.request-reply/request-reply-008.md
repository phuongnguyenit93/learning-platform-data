# Handling Wrongly Typed Replies

In Spring Kafka's request-reply pattern, a producer sends a request to a topic and awaits a response on a reply topic. Both sides must agree on the response contract: data type, schema, serializer/deserializer, and type identification metadata. If the requester expects `OrderReply` while the responder sends `ErrorReply` or an incompatible payload, failures can occur immediately during deserialization, during message conversion, or later when the application consumes the result.

The reliable approach is to define a clear response contract, configure deserializers to match that contract, and handle polymorphic responses using an intentional model. Do not force every reply into one class via casting and hope the data is compatible.

## 1. Request-Reply Needs a Clear Response Contract

Example of an order creation flow:

```text
Requester
  request: OrderRequest
  expected reply: OrderReply

Responder
  receives: OrderRequest
  returns: OrderReply

Kafka
  orders.requests
  orders.replies
```

Request and reply are two independent message contracts. The requester can send a valid request and still receive the wrong reply type if the responder returns the wrong DTO, the two services use different contract versions, or serializer/deserializer settings do not align.

Example response DTO:

```java
public record OrderReply(
        String orderId,
        String status,
        String message
) {
}
```

The requester should explicitly define `OrderReply` as the operation's result type. The responder should also return the published contract DTO rather than an internal implementation class or persistence entity.

A good contract defines:

- Field names and meanings.
- Data types, and whether fields are nullable or required.
- How success and failure states are represented.
- Schema or contract version.
- Compatibility rules when adding, renaming, or removing fields.
- How error responses are represented so the requester can understand them.

## 2. Common Forms of Wrongly Typed Replies

| Error Form | Example | Consequence |
|---|---|---|
| Responder returns wrong DTO | Requester expects `OrderReply`, responder returns `CustomerReply` | Deserialization or cast fails |
| Type header points to another class | Header contains `com.server.ErrorReply` | Deserializer tries to instantiate an unexpected type |
| Type header contains a class name absent on requester | Producer sends internal class name of another service | `ClassNotFoundException` or deserialization failure |
| Missing type header and wrong default type | `OrderReply` payload is read as `OrderRequest` | Mapping error or corrupted semantics |
| Incompatible field | `amount` changed from number to object | Jackson reports a mapping error |
| Generic response loses element type | Expects `List<OrderItemReply>` but declares raw `List` | Elements become `Map` instead of DTOs |
| Error reply uses a separate DTO | Success returns `OrderReply`, failure returns `ErrorReply` | A requester configured for one type may fail to read both |
| Listener method expects wrong type | Method declares `OrderReply` while converter produces another type | Message conversion or argument resolution fails |

Distinguish deserialization errors from business errors. If JSON parses into the DTO while a required field is null, the listener may still run; the error only surfaces when validation or business logic accesses that field. Thus, not every wrongly typed reply raises `SerializationException`.

## 3. How Spring Kafka Type Headers Affect Reply Types

Spring Kafka's `JsonSerializer` adds type information to Kafka headers by default; this behavior can be disabled via serializer configuration. The `__TypeId__` header typically indicates the value's class; complex structures may also carry key, content, or container type info.

`JsonDeserializer` uses type headers by default if present to decide which class to instantiate. Therefore, declaring `ReplyingKafkaTemplate<String, OrderRequest, OrderReply>` on the requester is not enough to guarantee payloads always deserialize into `OrderReply`: Java generics do not override the type headers used by the deserializer.

For example, the responder sends `OrderReply`, yet the type header points to `com.internal.server.OrderReply`. If that class does not exist in the requester, deserialization can fail even when the JSON fields match the requester's DTO.

There are three common design strategies:

1. **Single fixed reply type:** the requester ignores type headers and always deserializes values into the chosen DTO.
2. **Multiple controlled reply types:** use type mapping or a shared hierarchy/envelope contract.
3. **Payload independent of Java classes:** use `byte[]`, a JSON tree, or an envelope with `type` and `payload`, then dispatch in application code.

Pick one consistent strategy per reply topic. Do not mix multiple type header conventions that the requester cannot predict.

## 4. Configuring a Requester That Accepts Only One Reply Type

If every response for a request must be `OrderReply`, configure the reply consumer to always read values as that type. With `JsonDeserializer`, set a default type and disable reading type headers.

Example Spring Boot configuration:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-requester
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.contracts.OrderReply
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.contracts
```

Dotted properties are placed in bracket notation so Spring Boot preserves exact Kafka property names during binding.

Meaning:

- `spring.json.value.default.type` specifies the target class for values.
- `spring.json.use.type.headers=false` instructs the deserializer to ignore type headers when picking the class.
- `spring.json.trusted.packages` restricts packages allowed for deserialization.
- Keys remain deserialized with `StringDeserializer` in this example.

When instantiating `JsonDeserializer` directly in Java, equivalent configuration looks like:

```java
JsonDeserializer<OrderReply> replyDeserializer =
        new JsonDeserializer<>(OrderReply.class);

replyDeserializer.addTrustedPackages("com.example.contracts");
replyDeserializer.ignoreTypeHeaders();
```

Fluent APIs and constructors can vary across Spring Kafka versions. Avoid configuring the same property across constructor, setters, and property maps unless you are certain of precedence rules.

With a fixed-type strategy, an `ErrorReply` payload does not magically turn into `OrderReply` just because the deserializer ignored type headers. If the two DTOs have different shapes, mapping may fail or produce an incomplete object. Use a shared response contract if the requester needs to receive both successes and failures.

## 5. Configuring ReplyingKafkaTemplate with a Concrete Response Type

`ReplyingKafkaTemplate<K, V, R>` specifies the key, request value, and reply value at the API layer. The reply container must also be configured with type `R` to deserialize responses.

Example reply consumer configuration for `OrderReply`:

```java
@Bean
ConsumerFactory<String, OrderReply> orderReplyConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-requester"
    );
    properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
    );
    properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class
    );
    properties.put(
            JsonDeserializer.VALUE_DEFAULT_TYPE,
            OrderReply.class.getName()
    );
    properties.put(
            JsonDeserializer.USE_TYPE_INFO_HEADERS,
            false
    );
    properties.put(
            JsonDeserializer.TRUSTED_PACKAGES,
            "com.example.contracts"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
```

Creating the reply listener container and template:

```java
@Bean
ConcurrentMessageListenerContainer<String, OrderReply> orderReplyContainer(
        ConsumerFactory<String, OrderReply> orderReplyConsumerFactory) {

    ContainerProperties containerProperties =
            new ContainerProperties("orders.replies");

    containerProperties.setGroupId("orders-requester");

    return new ConcurrentMessageListenerContainer<>(
            orderReplyConsumerFactory,
            containerProperties
    );
}

@Bean
ReplyingKafkaTemplate<String, OrderRequest, OrderReply> orderRequestTemplate(
        ProducerFactory<String, OrderRequest> requestProducerFactory,
        ConcurrentMessageListenerContainer<String, OrderReply> orderReplyContainer) {

    return new ReplyingKafkaTemplate<>(
            requestProducerFactory,
            orderReplyContainer
    );
}
```

This example assumes a single requester instance using a fixed reply topic where every reply on that topic conforms to `OrderReply`. If deploying multiple requester instances sharing a reply topic, create a distinct group ID per instance as noted in the correlation/routing section below. In a Spring Boot application, ensure `KafkaProperties`, producer factory, imports, and listener container beans are configured compatibly with your version.

Sending a request and reading the reply:

```java
ProducerRecord<String, OrderRequest> requestRecord =
        new ProducerRecord<>(
                "orders.requests",
                request.orderId(),
                request
        );

RequestReplyFuture<String, OrderRequest, OrderReply> future =
        orderRequestTemplate.sendAndReceive(requestRecord);

ConsumerRecord<String, OrderReply> replyRecord =
        future.get(10, TimeUnit.SECONDS);

OrderReply reply = replyRecord.value();
```

The `OrderReply` type here is enforced by the reply consumer configuration, not merely by the template's generic parameter. If the responder sends an incompatible type, the error must be caught at the deserialization/contract boundary and routed into an observable error path.

## 6. The Responder Must Return the Agreed Contract

The request-handling listener should return the agreed response DTO. Example:

```java
@KafkaListener(
        topics = "orders.requests",
        groupId = "orders-service"
)
public OrderReply handle(OrderRequest request) {
    OrderResult result = orderService.create(request);

    return new OrderReply(
            result.orderId(),
            result.status(),
            result.message()
    );
}
```

For the listener to automatically send the response, configure the responder's listener container factory with a `KafkaTemplate` for publishing replies:

```java
factory.setReplyTemplate(responderReplyTemplate);
```

`ReplyingKafkaTemplate` on the requester attaches the reply topic and correlation ID to the request. The responder's listener container uses `responderReplyTemplate` to send the result back to the requested reply address; ensure the reply template and listener adapter preserve routing/correlation headers per application configuration. This is a standard `KafkaTemplate` on the responder, not the requester's `ReplyingKafkaTemplate`.

Never return JPA entities, Hibernate proxies, exception objects, or private responder implementation classes directly. Map them to contract DTOs before sending over Kafka. That keeps the requester decoupled from internal packages or persistence libraries of the responder.

If the responder needs to return a business error, represent it in the response contract, such as `OrderReply` with `status=REJECTED` and an appropriate `message`. Never use an arbitrary Java exception as a response payload.

## 7. When the Requester Must Accept Multiple Reply Types

Some APIs have multiple valid outcomes. For instance, a request may return `OrderAccepted` or `OrderRejected`. There are two common design patterns.

**Option A: A Common Envelope**

```java
public record OrderResponse(
        String responseType,
        String orderId,
        String status,
        String message
) {
}
```

Both success and failure use `OrderResponse`. The requester only needs one deserializer and inspects `responseType` or `status` to choose its branch.

```java
switch (response.responseType()) {
    case "ORDER_ACCEPTED" -> handleAccepted(response);
    case "ORDER_REJECTED" -> handleRejected(response);
    default -> throw new IllegalArgumentException(
            "Unsupported response type: " + response.responseType()
    );
}
```

This option fits when replies share common metadata and lifecycles. If payloads differ significantly across types, the envelope can include a `payload` field and a version, though you must clearly define how `payload` is deserialized per type.

**Option B: Using Type Mapping for Multiple DTOs**

Spring Kafka supports type mapping between stable tokens and Java classes. The producer maps a response class to a token; the requester maps that token back to its corresponding DTO class.

Example mapping configuration:

```properties
spring.json.type.mapping=accepted:com.example.contracts.OrderAccepted,rejected:com.example.contracts.OrderRejected
```

Both sides must agree on the token, while each service can map the token to classes in different packages. This reduces coupling to the sending service's fully qualified class names.

With multiple reply types, declare the template/deserializer with a common supertype or `Object`, then verify the concrete type before using it. The generic `R` does not validate all subtypes at runtime on its own.

Do not use type mapping as a mechanism to allow deserializing arbitrary classes. Only declare response types belonging to the permitted contract.

## 8. Generic Responses and Collection Types

Another cause is Java type erasure. If the requester declares a raw `List` type, Jackson does not know elements should be `OrderItemReply`; elements may be instantiated as `LinkedHashMap`.

Example to avoid:

```java
RequestReplyFuture<String, OrderRequest, List> rawListFuture =
        rawListReplyTemplate.sendAndReceive(requestRecord);
ConsumerRecord<String, List> replyRecord =
        rawListFuture.get(10, TimeUnit.SECONDS);

List items = replyRecord.value();
OrderItemReply item = (OrderItemReply) items.get(0);
```

Here the reply container uses `JsonDeserializer` with default type `List.class` and no element type metadata. Jackson may deserialize each element into `LinkedHashMap`; casting to `OrderItemReply` will fail.

Use a DTO with a concrete element type instead:

```java
public record OrderItemsReply(
        String orderId,
        List<OrderItemReply> items
) {
}

public record OrderItemReply(
        String sku,
        int quantity
) {
}
```

When a contract requires a top-level collection, configure Jackson with an appropriate `TypeReference`/`JavaType` and verify that your Spring Kafka version's `JsonDeserializer` supports that construction. An envelope DTO is usually simpler because it preserves element type info, metadata, and schema version in one clear contract.

Do not rely on `ReplyingKafkaTemplate`'s generic declaration to recover generic element types lost to type erasure.

## 9. Distinguishing Deserialization, Message Conversion, and Casting

A wrongly typed reply can fail at different layers:

| Layer | Example Error | Where to Check |
|---|---|---|
| Kafka deserializer | Unparseable JSON, class in type header does not exist | `JsonDeserializer`, type headers, `ErrorHandlingDeserializer` |
| Message converter | Message deserializes but cannot be converted to listener parameter | Record/message converter and method signature |
| Runtime cast | Actual value is `ErrorReply` but code casts to `OrderReply` | Contract, generic boundary, and validation |
| Business validation | DTO is the right class, but a required field is missing or status is invalid | Bean Validation and business rules |
| Correlation/routing | Reply does not match pending request | Correlation ID, reply topic, reply partition |

When debugging, first pinpoint which layer raised the error. Changing `trusted.packages` will not fix malformed JSON schemas; changing a DTO will not fix a lost correlation ID; increasing timeouts will not fix a failing response deserializer.

## 10. Handling Deserialization Errors on the Reply Consumer

If reply payloads may be malformed, wrap the deserializer with `ErrorHandlingDeserializer` to preserve the exception and raw bytes in headers. This gives the container diagnostic data and supports recovery paths.

Example configuration:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.contracts.OrderReply
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.contracts
```

However, `ReplyingKafkaTemplate`'s reply consumer has an additional requirement: deserialization failures must be observed and linked to the pending request. If an error handler merely logs and drops the record, the requester may never receive a valid response and eventually time out. Never treat a null value produced by a deserialization failure as a successful response.

For critical systems, define an explicit handling path: detect the deserialization error, emit logs/metrics with the correlation ID, store raw payloads or forward to an error topic per policy, and complete the request with an observable error if architecture permits. If the error cannot be mapped directly to a future failure, ensure timeouts and alerts exist so corrupted replies are not hidden.

## 11. Correlation ID and Reply Routing

Even when a response has the right type, the requester can still miss or misread replies if the correlation ID or reply destination is wrong.

`ReplyingKafkaTemplate` uses the correlation ID to pair responses with pending requests. A valid reply must:

- Carry a correlation ID matching a pending request.
- Be sent to the reply topic consumed by the reply container.
- Have compatible partition routing if the reply container only subscribes to certain partitions.
- Be serialized according to the response contract configured by the requester.

Do not generate or overwrite correlation IDs without reason. With custom responders, preserve the correlation header from request to response per Spring Kafka conventions. When multiple requester instances share a reply topic, each instance needs its own reply consumer group so every instance receives a copy of all replies and matches correlation IDs locally. Enable shared reply topic mode on the template:

```java
orderRequestTemplate.setSharedReplyTopic(true);
```

If instances share one consumer group, Kafka distributes each record to one instance; an instance not owning that correlation ID ignores the reply, and the pending request on another instance may time out. Only use a shared reply topic when all requesters follow `ReplyingKafkaTemplate`'s correlation mechanism.

With dynamic reply topics, requester and responder must agree on passing/reading `KafkaHeaders.REPLY_TOPIC` and `KafkaHeaders.REPLY_PARTITION`. With a fixed reply topic, ensure the reply container subscribes to the right topic and prevent multiple clients from competing to read replies awaited by another client.

## 12. Timeout Does Not Equal Wrongly Typed Reply

`ReplyingKafkaTemplate` can time out when no matching reply arrives within the wait period. Causes include an unresponsive responder, a reply sent to the wrong topic/partition, a mismatched correlation ID, or a reply consumer failing to deserialize the response.

Example future handling:

```java
try {
    ConsumerRecord<String, OrderReply> replyRecord =
            future.get(10, TimeUnit.SECONDS);

    OrderReply reply = replyRecord.value();
    validateReply(reply);
}
catch (TimeoutException exception) {
    throw new OrderReplyTimeoutException(
            "No valid reply received in time",
            exception
    );
}
catch (ExecutionException exception) {
    throw new OrderReplyFailedException(
            "Request-reply failed",
            exception.getCause()
    );
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new OrderReplyFailedException(
            "Waiting for the reply was interrupted",
            exception
    );
}
```

Distinguish timeouts, request send failures, reply deserialization failures, and business rejection responses. Do not automatically resend a request on timeout if the operation is not idempotent: the responder may have processed the request and only the reply was lost. Use a request ID/idempotency key to prevent creating duplicate orders or side effects.

## 13. Testing Wrongly Typed Replies

Tests should verify both contract-compliant responses and cases where the responder returns the wrong type or schema.

| Scenario | Expected Result to Verify |
|---|---|
| Responder returns valid `OrderReply` | Requester receives right DTO and correlation ID |
| Type header points to internal class missing on requester | Deserialization failure is observed |
| Type headers disabled and default type set | Payload is read as the fixed response DTO |
| Responder returns `ErrorReply` in a flow accepting only `OrderReply` | Contract violation is caught, not treated as success |
| Malformed JSON | Error handler records error; raw bytes may be retained |
| Missing required field | Validation catches it before using response |
| Reply sent to wrong topic | Request times out with diagnostic metrics |
| Mismatched correlation ID | Reply does not falsely complete a future |
| Two reply types via type mapping | Each token deserializes into the right DTO |
| Generic list | Elements deserialize into the right DTO, not `Map` |

With Embedded Kafka or Testcontainers:

1. Create the request topic and reply topic.
2. Start the requester with a real reply container and response deserializer.
3. Start a test responder capable of returning valid DTOs, wrong DTOs, and malformed JSON payloads.
4. Send requests with correlation IDs.
5. Verify a valid-type reply completes the future.
6. Send a wrongly typed reply and verify the error/timeout path matches design.
7. Verify logs/metrics include request ID or correlation ID without logging sensitive full payloads.
8. Test timeouts and retries to ensure no duplicate side effects occur.

## 14. Common Issues and Checklist

| Symptom | Cause | How to Fix |
|---|---|---|
| `ClassNotFoundException` reading reply | Type header contains class name existing only on responder | Use shared contract DTOs, type mapping, or ignore type headers |
| `ClassCastException` after receiving reply | Runtime value differs from expected code type | Check actual runtime type and avoid blind casting |
| `MessageConversionException` | Converter cannot convert payload to listener parameter | Align DTO, converter, and method signature |
| JSON parsing fails | Incompatible schema or JSON shape | Version contracts and run compatibility tests |
| Reply becomes `Map`/`LinkedHashMap` | Deserializer lacks target type or generic type was erased | Use a DTO/envelope or configure `JavaType` |
| Request times out despite responder processing | Reply sent to wrong topic/partition, lost correlation ID, or deserialization failure | Check reply headers, container, and error handler |
| Failed reply turns into null | Error handler swallowed deserialization failure | Do not treat null as success; emit metrics and fail the request |
| Deserialization rejected due to package | Package not in trusted packages | Add only trusted contract packages |
| Adding new field breaks older clients | Schema compatibility rules undefined | Make new fields optional/defaulted and test versions |

Pre-deployment checklist:

1. Lock down one response contract per request operation.
2. Use stable contract DTOs; never send entities or internal classes.
3. Decide explicitly whether the deserializer uses type headers or a fixed default reply type.
4. With multiple reply types, use an envelope or allowlisted type mapping.
5. Configure the minimal set of trusted packages needed.
6. Avoid raw collections or blind response casts.
7. Preserve correlation IDs and reply routing headers.
8. Distinguish deserialization failures, conversion failures, business rejections, and timeouts.
9. Design idempotency before retrying requests.
10. Test wrong classes, wrong schemas, malformed JSON, timeouts, and correlation mismatches.

A wrongly typed reply is a contract or serialization/deserialization configuration bug. When requester and responder agree on DTOs, type metadata, and reply routing, `ReplyingKafkaTemplate` exchanges responses reliably. For multiple result types, model polymorphism explicitly so the requester knows the exact response type it is handling.
