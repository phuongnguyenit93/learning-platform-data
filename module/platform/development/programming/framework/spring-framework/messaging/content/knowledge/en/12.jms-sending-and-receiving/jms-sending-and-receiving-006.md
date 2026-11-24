# Choosing a JMS JSON Converter for Your Version

> Goal: configure a JSON converter to send and receive DTOs over JMS; understand the difference between `MappingJackson2MessageConverter` and `JacksonJsonMessageConverter`; choose the right API for the Spring Framework/Jackson versions present in your dependency tree; and manage type IDs, content metadata, encoding, and deserialization safety.

## 1. Why Does JMS Need a MessageConverter?

JMS works with message types such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. Meanwhile, applications typically work with Java DTOs such as `OrderCreated`. A `MessageConverter` translates between the two models:

- **Outbound:** Java DTO → JSON bytes or text → JMS message.
- **Inbound:** JMS message → read JSON → typed Java DTO.

`JmsTemplate.convertAndSend()` and `receiveAndConvert()` use `org.springframework.jms.support.converter.MessageConverter`. The default converter `SimpleMessageConverter` fits basic JMS types such as `String`, `byte[]`, and `Map`; to send DTOs as JSON, you need to configure a Jackson converter. <https://docs.spring.io/spring-framework/reference/integration/jms/sending.html>

Do not confuse the JMS converter interface with `org.springframework.messaging.converter.MessageConverter`. The two interfaces live in different packages and serve different purposes. `JmsTemplate` uses the converter in `org.springframework.jms.support.converter`; `JmsMessagingTemplate` and `JmsClient` work with the Spring Messaging abstraction and its corresponding converter.

## 2. Choosing a Converter by Spring and Jackson Version

The class name to choose depends on the actual resolved Spring Framework version, not solely on the Jackson version you intend to use:

| Platform | JMS JSON Converter | Notes |
|---|---|---|
| Spring Framework 5.x + Jackson 2 | `MappingJackson2MessageConverter` | Uses `javax.jms`; examples must change JMS imports from `jakarta.jms` to `javax.jms` |
| Spring Framework 6.x + Jackson 2 | `MappingJackson2MessageConverter` | Uses `jakarta.jms`; fits Spring 6 and Spring Boot 3 applications |
| Spring Framework 7.0 + Jackson 3 | `JacksonJsonMessageConverter` | New converter using Jackson 3 and the `tools.jackson` package; this is the recommended path |
| Spring Framework 7.0 + Jackson 2 | `MappingJackson2MessageConverter` | Still present in 7.0, but deprecated as of 7.0 and marked for removal |

Spring Framework 7.0 introduces `JacksonJsonMessageConverter` to use Jackson 3. `MappingJackson2MessageConverter` is deprecated as of 7.0 in favor of the new converter. Jackson 3 uses the `tools.jackson.*` package, unlike Jackson 2's `com.fasterxml.jackson.*` package. <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html> <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html>

If the project is on Spring Framework 6.2, use `MappingJackson2MessageConverter`. If the project has upgraded to Spring Framework 7.0 and uses Jackson 3, switch to `JacksonJsonMessageConverter`. Do not import the Spring 7 converter into a Spring 6 project because that class does not exist in version 6.

### Checking which dependencies are actually resolved

With Maven, inspect the dependency tree of the relevant modules:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-jms,com.fasterxml.jackson.core:jackson-databind,tools.jackson.core:jackson-databind
```

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Check both directly declared dependencies and dependencies pulled in by the Spring Boot BOM or dependency management. Avoid forcing a single `spring-jms` module onto a different version from the rest of Spring Framework. When using Spring Boot, prefer letting Boot's BOM manage Spring and Jackson versions together.

## 3. DTOs and the JSON Contract

Start with a simple DTO that has an explicit schema:

```java
package com.example.messaging;

public record OrderCreated(
        String orderId,
        int itemCount,
        int schemaVersion
) {}
```

Corresponding JSON example:

```json
{
  "orderId": "ORD-100",
  "itemCount": 2,
  "schemaVersion": 1
}
```

Message DTOs should represent the exchange contract between producer and consumer. Avoid directly sending JPA entities, objects holding lazy relationships, services, or objects tied to an application's internal state. Use stable data types and clearly define required fields, optional fields, default values, and compatibility rules when adding fields.

JSON only defines data syntax. It does not by itself define event type or schema version. Separate them cleanly:

- `contentType`: representation, for example `application/json`.
- `eventType`: event kind, for example `order-created-v1`.
- `schemaVersion`: payload structure version, for example `1`.

## 4. Configuration for Spring Framework 6.x and Jackson 2

`org.springframework.jms.support.converter.MappingJackson2MessageConverter` uses Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`). The converter can read `TextMessage` or `BytesMessage`; on send, it defaults to creating a `BytesMessage`. If you want a text body that is easy to inspect and interoperate with other systems, set the target type to `MessageType.TEXT`. The default encoding is UTF-8. <https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html>

The example below uses Spring Framework 6.2.19+ APIs to get `setTrustedPackages`:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConverterConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsJsonMessageConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
                "order-created-v1", OrderCreated.class
        ));
        converter.setTrustedPackages("com.example.messaging");
        return converter;
    }
}
```

Meaning:

- `setTargetType(MessageType.TEXT)` tells the converter to send JSON in a `TextMessage`. If omitted, the converter defaults to `BytesMessage` (`MessageType.BYTES`).
- `setTypeIdPropertyName("eventType")` selects the JMS property carrying the payload type identifier.
- `setTypeIdMappings(...)` maps the stable ID `order-created-v1` to the `OrderCreated` class.
- `setTrustedPackages(...)` restricts which Java packages are allowed during deserialization.

`setTrustedPackages` was added in Spring Framework 6.2.19. If the project is on Spring 6.0, 6.1, or Spring 6.2 older than 6.2.19, this method does not exist yet; do not copy the example verbatim into such a project. When this API is unavailable, prefer explicit type ID mapping, do not send raw Java class names, do not enable polymorphic default typing for untrusted messages, and consider upgrading to a Spring version that supports trusted packages.

If you need to use a preconfigured `ObjectMapper`, Spring Framework 6.1 and later provide a constructor accepting `ObjectMapper`; earlier versions can use the default constructor and `setObjectMapper(...)` setter if the running version's API supports it.

## 5. Configuration for Spring Framework 7.0 and Jackson 3

For Spring Framework 7.0 and Jackson 3, use `org.springframework.jms.support.converter.JacksonJsonMessageConverter`. This class uses `tools.jackson.databind.json.JsonMapper`, reads `TextMessage` and `BytesMessage`, and defaults to sending `BytesMessage`. You can choose `MessageType.TEXT` if the contract requires a text body.

Example for Spring Framework 7.0.8+:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConverterConfiguration {

    @Bean
    JacksonJsonMessageConverter jmsJsonMessageConverter() {
        var converter = new JacksonJsonMessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
                "order-created-v1", OrderCreated.class
        ));
        converter.setTrustedPackages("com.example.messaging");
        return converter;
    }
}
```

`JacksonJsonMessageConverter` was introduced in Spring Framework 7.0. `setTrustedPackages` was added in 7.0.8; if using Spring 7.0.0 through 7.0.7, omit this call and use explicit type ID mapping, upgrading when possible. The default constructor creates a `JsonMapper` and automatically discovers Jackson modules via Spring's mechanism; if a custom mapper is needed, the converter also has constructors accepting a `JsonMapper` or builder. <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html>

Do not mix Jackson 2's `com.fasterxml.jackson.databind.ObjectMapper` with Jackson 3's `tools.jackson.databind.json.JsonMapper`. They are two distinct API generations.

## 6. Wiring the Converter into JmsTemplate and the Listener Container

Creating the converter bean alone is not enough. Both producer and consumer must use converters compatible with the JSON contract.

Wiring example using the JMS converter interface so implementations can be swapped by version:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
class JmsInfrastructureConfiguration {

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MessageConverter jmsJsonMessageConverter) {
        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(jmsJsonMessageConverter);
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter jmsJsonMessageConverter) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jmsJsonMessageConverter);
        return factory;
    }
}
```

This is an illustrative configuration for Spring 6.x/7.x using `jakarta.jms`. Spring Framework 5.x uses `javax.jms`, so imports and provider dependencies must share the same namespace. If Spring Boot already auto-configures `JmsTemplate` or the listener factory, configure the converter on the actual bean/factory in use rather than creating duplicate beans.

Sending a DTO:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.incoming", event);
    }
}
```

Receiving a DTO:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(OrderCreated event) {
        processOrder(event);
    }
}
```

The listener method declares the `OrderCreated` type, making the input contract explicit. The converter and listener adapter must agree on how the target type is determined. If receiving multiple event types from the same destination, test type ID mapping and method argument conversion with the exact Spring/provider versions.

## 7. Type ID Mapping and Cross-Application Compatibility

The converter can write a JMS message property carrying a type ID. Without configured mappings, some converters may fall back to raw Java class names; that couples the contract to the producer's package and class names.

Use stable IDs instead of class names:

```java
converter.setTypeIdPropertyName("eventType");
converter.setTypeIdMappings(Map.of(
        "order-created-v1", OrderCreated.class,
        "payment-captured-v1", PaymentCaptured.class
));
```

Producer and consumer must agree on the ID values. When renaming packages or refactoring Java classes, the external ID can stay unchanged. When making breaking schema changes, issue a new ID/version or design an explicit migration.

Do not use class names received from messages as the basis for arbitrary deserialization. Do not enable Jackson default typing on queues whose producers are not fully trusted. Only permit known payload types via type ID mapping and restrict trusted packages where supported by your Spring version.

## 8. TextMessage, BytesMessage, and Encoding

Both JMS Jackson converters described above support converting JSON via `TextMessage` or `BytesMessage`:

| JMS Form | Characteristics | When to Consider |
|---|---|---|
| `TextMessage` | Body is a character string; easy to read when inspecting the broker and convenient for text-based consumers | Integrating with systems handling JSON text |
| `BytesMessage` | Body is a byte sequence; suitable when representing payloads as bytes | Integrations with binary conventions or transport optimization |

JMS Jackson converters default to creating `BytesMessage` via `MessageType.BYTES`; to create `TextMessage`, set `MessageType.TEXT`. The default encoding for text is UTF-8. If two systems use different encoding settings, align on encoding and test with Unicode data.

Do not assume selecting `MessageType.TEXT` automatically sets an HTTP-style `Content-Type` header. JMS has `JMSType`, but that field is not equivalent to a MIME `Content-Type`. If non-Java consumers need to know the representation, agree on a separate JMS property, such as `contentType=application/json`.

Properties can be attached after the converter creates the message using a `MessagePostProcessor`:

```java
jmsTemplate.convertAndSend("orders.incoming", event, message -> {
    message.setStringProperty("contentType", "application/json");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
```

JMS properties must use data types supported by JMS. Producer and consumer need to agree on property names, data types, and semantics.

## 9. Schema Evolution and Validation

The converter is responsible for turning JSON into a Java object. It does not automatically validate all business rules or guarantee producer and consumer are using the same schema.

When designing schemas:

- Add new fields in a backward-compatible way with clear default or optional rules.
- Do not change the type of a field currently used by consumers without a migration.
- Use `schemaVersion` or event type versioning for breaking structural changes.
- Keep field names and enums stable; agree on how to handle new enum values.
- Validate required fields, ranges, and invariants after deserialization.
- Do not directly serialize entities with cyclic relationships or internal fields outside the contract.

Jackson 2's `MappingJackson2MessageConverter` customizes certain defaults, including disabling `FAIL_ON_UNKNOWN_PROPERTIES`. That can help older consumers ignore new fields, but does not replace schema validation. If a strict contract is required, configure an appropriate `ObjectMapper` and write tests for invalid payloads. Jackson 3 mapper behavior should be verified against the mapper/modules and settings of the version in use.

## 10. Conversion Errors and How to Handle Them

Common errors include:

- **No suitable converter:** the application uses `SimpleMessageConverter`, so DTOs are not converted to JSON as expected.
- **Wrong JMS message type:** the consumer receives an `ObjectMessage` or another message type when the converter only supports text/bytes.
- **Wrong type ID:** the property is missing, the ID is absent from the mapping, or the two sides use different ID names.
- **Wrong encoding:** Unicode characters are corrupted when bytes are read with a different encoding.
- **Invalid JSON:** the payload is truncated, malformed, or contains data types that cannot be deserialized.
- **Incompatible schema:** valid JSON, but fields/enums/structure do not match the consumer DTO.
- **Missing dependencies or version mismatch:** converter missing from the classpath, incompatible Jackson module, or `javax.jms` mixed with `jakarta.jms`.

Spring represents conversion failures with `MessageConversionException` in JMS converters. Errors can occur before the `@JmsListener` method is invoked. Configure an error handler, transactions, redelivery, and dead-letter policies so poison messages are not retried indefinitely.

## 11. Testing Converters and Two-Way Contracts

A good test suite should verify both the broker representation and the received object:

1. Send a DTO and verify the generated JMS message is `TextMessage` or `BytesMessage` as configured.
2. Read the body and confirm the JSON has the expected fields, encoding, and schema version.
3. Check JMS properties carrying the type ID and content metadata if required by the contract.
4. Receive the message via the consumer's converter and verify the DTO holds the expected values.
5. Test unknown type IDs, missing type IDs, malformed JSON, wrong field types, and unsupported schema versions.
6. Test producer/consumer compatibility across different application versions.
7. Run integration tests with a real JMS provider or corresponding test broker to verify property mapping and listener container behavior.

Converter unit tests can verify serialize/deserialize logic; integration tests prove that the provider, message type, property mapping, transactions, and listener container work together properly.

## 12. Common Configuration Mistakes

- **Using `MappingJackson2MessageConverter` on Spring 7 as a greenfield choice:** the class is deprecated as of 7.0; prefer `JacksonJsonMessageConverter` when using Jackson 3.
- **Using `JacksonJsonMessageConverter` on Spring 6:** the class does not exist in Spring 6; use the Jackson 2 converter.
- **Confusing Jackson 2 and Jackson 3 packages:** `com.fasterxml.jackson.*` and `tools.jackson.*` imports are not interchangeable.
- **Forgetting to attach the converter to both sender and listener container:** producer sends JSON while consumer still uses the default converter.
- **Assuming the converter creates TextMessage by default:** both JMS Jackson converters described above default to `BytesMessage`; set `MessageType.TEXT` if text is desired.
- **Omitting type IDs for polymorphic flows:** the converter cannot determine the target class when it must be inferred from the message.
- **Sending Java class names instead of stable type IDs:** producer and consumer become tightly coupled to package/class names.
- **Widening trusted packages too far or using wildcards:** unnecessarily increases the deserialization attack surface.
- **Confusing `JMSType` with `Content-Type`:** if MIME type is needed, define a dedicated JMS property and document it.
- **Not checking resolved versions:** dependency management may pull in a different version than what is written directly in the build file.
- **Treating successful deserialization as successful validation:** DTOs still require data and business rule validation.

## 13. Selection and Rollout Process

1. Identify the actual Spring Framework and Jackson versions from the dependency tree.
2. Choose `MappingJackson2MessageConverter` for Spring 5/6 with Jackson 2; choose `JacksonJsonMessageConverter` for Spring 7 with Jackson 3.
3. Verify the JMS namespace: `javax.jms` in Spring 5 and `jakarta.jms` in Spring 6/7.
4. Define DTOs and JSON schemas independently of internal entities.
5. Choose `TextMessage` or `BytesMessage` per the integration contract; standardize on UTF-8.
6. Configure the converter, type ID property, and stable ID mappings; restrict trusted packages if supported by the version.
7. Attach the converter to the `JmsTemplate` and listener containers used by the application.
8. Define `contentType`, event type, and schema version properties if non-Java consumers need metadata.
9. Test round-trip conversion, type IDs, schema compatibility, encoding, poison messages, and dead-letter behavior.
10. Upgrade Spring/Jackson synchronously via the BOM and check deprecations before every version bump.

## 14. Conclusion

JMS JSON converters turn Java DTOs into `TextMessage` or `BytesMessage`, and convert JMS messages back into objects. For Spring Framework 5/6 with Jackson 2, use `MappingJackson2MessageConverter`; for Spring Framework 7 with Jackson 3, prefer `JacksonJsonMessageConverter`. Choose based on your project's actual resolved dependencies and JMS namespace.

For long-term producer and consumer compatibility, use stable DTOs/schemas, explicit type ID mappings, consistent encoding, agreed-upon metadata, and post-deserialization validation. Configure the same converter on `JmsTemplate` and listener containers, test both directions with a real broker, and handle conversion failures via bounded retries and a dead-letter policy.