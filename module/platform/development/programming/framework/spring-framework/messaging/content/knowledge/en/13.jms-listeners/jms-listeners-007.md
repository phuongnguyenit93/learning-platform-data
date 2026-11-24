# @Payload, @Header, @Headers, and Input Validation in a JMS Listener

When you use **@JmsListener**, Spring JMS receives the message from the destination, converts the body and metadata into the Spring Messaging model, and then resolves the parameters of the listener method. The three annotations **@Payload**, **@Header**, and **@Headers** help the method receive exactly the data it needs to process without reading each field from a jakarta.jms.Message yourself.

To handle input safely, you need to distinguish three things:

1. **Conversion:** turning the JMS body into the Java type the listener requests.
2. **Binding:** putting the payload and each header into the correct method parameter.
3. **Validation:** checking whether the converted data satisfies the application's constraints.

If a step fails, the listener method may not be called. Therefore, configuring the converter, header mapping, and validator is part of the message-receiving contract.

## 1. The Processing Flow Before the Listener Is Called

For an annotation-based listener, Spring creates a message listener container and an adapter to receive messages. A common flow:

~~~text
JMS Provider / Broker
       |
       | jakarta.jms.Message
       v
JMS MessageConverter
       |
       | body -> Java payload
       | JMS headers / properties -> Spring headers
       v
Spring Message<?>
       |
       | Method argument resolution
       | @Payload / @Header / @Headers
       v
Validation (@Valid / @Validated)
       |
       v
@JmsListener method
~~~

Each step has its own responsibility:

- **JMS MessageConverter** converts the body of a TextMessage, BytesMessage, MapMessage, or ObjectMessage into a Java object.
- **JmsHeaderMapper** maps the JMS headers and properties into Spring message headers.
- **@Payload** takes the payload from the Spring Message.
- **@Header** takes a specific header by name.
- **@Headers** takes all the headers after the mapper has processed them.
- **Validator** checks the constraints on the payload before the method handles the business logic.

Remember that **@Payload does not parse JSON by itself**. JSON must be converted into a Java type by the converter configured on the listener container factory. Similarly, **@Header** does not read an arbitrary property from the raw JMS message by itself; that property must be put into the Spring headers by the mapper.

## 2. @Payload: Taking the Main Data of the Message

**org.springframework.messaging.handler.annotation.Payload** marks the parameter that receives the payload. This is the body part that has been converted by the converter.

Example of a listener receiving a string:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload String body) {
    System.out.println("body=" + body);
}
~~~

If the converter has converted JSON into a DTO, the listener can receive the DTO directly:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload OrderCreated order) {
    orderService.process(order);
}
~~~

In a listener method, a parameter that is not marked as a special type such as the Spring Message or the JMS Session is usually treated as the payload even without @Payload. Writing the annotation explicitly helps the reader recognize which parameter is the body.

### The required Attribute

The payload is required by default. If the flow allows a message without a payload, you can use:

~~~java
public void receive(@Payload(required = false) String body) {
    if (body == null) {
        return;
    }
    // process the body
}
~~~

For business messages such as an order-creation command, the payload should usually be required. If the body is empty or cannot be converted, handle it as invalid input according to the consumer's policy.

### Payload DTO and Converter

If the listener declares OrderCreated but the converter returns a String, Spring does not automatically turn the JSON string into a DTO just because the parameter type is OrderCreated. You need to configure a compatible JSON converter.

With Spring JMS and Jackson 2, the converter commonly used is **org.springframework.jms.support.converter.MappingJackson2MessageConverter**. This is a Spring JMS converter, different from the converter of the same name in the Spring Messaging package.

## 3. @Header: Taking a Specific Piece of Metadata

**org.springframework.messaging.handler.annotation.Header** is used to bind a message header to a method parameter.

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload String body,
        @Header("eventType") String eventType
) {
    System.out.println("eventType=" + eventType);
    System.out.println("body=" + body);
}
~~~

Here, eventType is a custom JMS property that the header mapper converts into a Spring header of the same name. If the producer does not send that property, the parameter is required by default, so parameter resolution will fail before the method runs.

### Required Headers, Optional Headers, and Default Values

A header is required by default. You can change the behavior:

~~~java
public void receive(
        @Header(name = "eventType") String eventType,
        @Header(name = "tenantId", required = false) String tenantId,
        @Header(name = "source", defaultValue = "unknown") String source
) {
    // tenantId may be null; source uses the default value if missing.
}
~~~

- **required = true** is the default. A missing header prevents Spring from resolving the parameter.
- **required = false** allows the header to be absent; use a reference type such as String or Long if the value can be null.
- **defaultValue** provides a replacement value when the header is absent. This is a suitable choice when the application has a clear default value.

Spring can convert the header type through the ConversionService. For example, a numeric value is mapped to an Integer or Long parameter if a suitable converter exists. If the value cannot be converted, binding the parameter fails.

### Standard JMS Headers via JmsHeaders

Spring JMS maps the standard JMS headers into Spring message headers using the names defined in **org.springframework.jms.support.JmsHeaders**.

| Constant | Meaning |
|---|---|
| **JmsHeaders.MESSAGE_ID** | The ID assigned to the message by the JMS provider. |
| **JmsHeaders.CORRELATION_ID** | JMSCorrelationID, used to link request/reply or related messages. |
| **JmsHeaders.REPLY_TO** | The reply destination of the message. |
| **JmsHeaders.DESTINATION** | The Queue or Topic that received the message. |
| **JmsHeaders.TIMESTAMP** | The send time recorded by the provider. |
| **JmsHeaders.DELIVERY_MODE** | Persistent or non-persistent. |
| **JmsHeaders.PRIORITY** | The JMS priority level. |
| **JmsHeaders.EXPIRATION** | The time the message expires. |
| **JmsHeaders.REDELIVERED** | Indicates the message has been redelivered. |
| **JmsHeaders.TYPE** | The JMS message type label. |

Prefer the constants over writing the header name strings yourself:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(name = JmsHeaders.MESSAGE_ID, required = false) String messageId
) {
    // correlationId and messageId are taken from the mapped JMS metadata.
}
~~~

Some JMS headers are read-only values managed by the provider. Reading them through the Spring headers does not mean the producer can freely overwrite them.

## 4. @Headers: Receiving All Message Headers

**org.springframework.messaging.handler.annotation.Headers** binds all the Spring message headers to a parameter of a type compatible with Map.

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload String body,
        @Headers Map<String, Object> headers
) {
    Object eventType = headers.get("eventType");
    Object correlationId = headers.get(JmsHeaders.CORRELATION_ID);

    System.out.println("eventType=" + eventType);
    System.out.println("correlationId=" + correlationId);
}
~~~

The Map contains the headers the Spring Message carries after the JMS header mapper has performed the mapping. It can include:

- Standard JMS metadata such as message ID, correlation ID, destination, and timestamp.
- Custom JMS properties set by the producer.
- Internal metadata or metadata added by the adapter during processing.

You can receive **MessageHeaders** or the Spring **Message<?>** directly if you want to access the payload and headers at the same time:

~~~java
public void receive(Message<OrderCreated> message) {
    OrderCreated order = message.getPayload();
    Object correlationId = message.getHeaders().get(JmsHeaders.CORRELATION_ID);
}
~~~

Use @Header when the method only needs a few clear fields. Use @Headers when you need to inspect a lot of metadata or write generic logic. Do not log the entire Map by default because the headers may contain identifying information, tenant information, or sensitive data.

## 5. Distinguishing Payload, JMS Headers, and JMS Properties

A JMS message has a body, headers, and properties. Spring maps them into the Spring Message by different rules:

| Part of JMS | Example | How to access in the listener |
|---|---|---|
| Body | JSON in a TextMessage | @Payload DTO or String after conversion |
| Standard JMS header | JMSCorrelationID | @Header(JmsHeaders.CORRELATION_ID) |
| Custom JMS property | eventType, tenantId, schemaVersion | @Header("eventType"), @Headers Map |
| All mapped metadata | JMS headers + properties | @Headers Map or MessageHeaders |

Example of a producer creating a message with:

~~~text
Body:
  {"orderId":"ORD-1001","total":125.50,"currency":"USD"}

JMS headers:
  JMSCorrelationID = checkout-001

JMS properties:
  eventType = OrderCreated
  tenantId = tenant-42
  schemaVersion = 1
  _type = order-created
~~~

The listener can receive the body as OrderCreated, get the correlation ID using JmsHeaders.CORRELATION_ID, and get eventType or tenantId by the property name.

Do not confuse a custom JMS property with a field in the JSON. If eventType is only in the JSON body, @Header("eventType") will not find it. If you want to use @Header, the producer must set the property or an adapter must create the corresponding Spring header.

## 6. Input Validation with @Valid

**@Valid** from Jakarta Bean Validation asks Spring to check the constraints on the payload object before calling the listener method.

Example DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal total,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency
) {
}
~~~

Listener:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload @Valid OrderCreated order) {
    orderService.process(order);
}
~~~

The constraints are checked before the method runs:

- orderId must not be null, empty, or only whitespace.
- total must have a value and be greater than or equal to 0.01.
- currency must consist of three uppercase letters per the convention in the example.

If the DTO has nested objects, place @Valid on the nested property so validation goes deep into that object:

~~~java
public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @Valid Customer customer
) {
}

public record Customer(
        @NotBlank String customerId,
        @NotBlank String email
) {
}
~~~

### Configuring a Validator for the JMS Listener

Spring uses **DefaultMessageHandlerMethodFactory** to resolve the parameters of @JmsListener methods. You can configure a Validator for the factory using **JmsListenerConfigurer**.

Example:

~~~java
@Configuration
@EnableJms
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean jmsValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            org.springframework.validation.Validator validator
    ) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();
        factory.setValidator(validator);
        return factory;
    }

    @Bean
    public JmsListenerConfigurer jmsListenerConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory
    ) {
        return new JmsListenerConfigurer() {
            @Override
            public void configureJmsListeners(
                    JmsListenerEndpointRegistrar registrar
            ) {
                registrar.setMessageHandlerMethodFactory(methodFactory);
            }
        };
    }
}
~~~

A Jakarta Bean Validation implementation must be on the classpath, such as Hibernate Validator. **LocalValidatorFactoryBean** connects the Bean Validation provider with the Spring Validator; **DefaultMessageHandlerMethodFactory** uses that validator to check the payload parameter marked with @Valid or @Validated.

If the project uses Spring Framework 6.x, the validation import is **jakarta.validation.Valid** and the constraints belong to **jakarta.validation.constraints**. Spring Framework 5.3 projects use the **javax.validation** namespace; do not mix the two namespaces in the same configuration.

### @Valid and @Validated

- **@Valid** triggers validation per Jakarta Bean Validation on the payload.
- **@Validated** from Spring supports specifying validation groups, for example the Create or Update group, when the application has declared the corresponding groups.

Payload validation in a message handler method needs to be configured through the message handler method factory as in the example above. Do not assume that merely adding the validation dependency makes every JMS listener automatically use the application's custom validator.

## 7. Header Validation and Business Validation

@Valid usually checks the payload object. Binding a header has its own rules:

- A required header is checked by the default required of @Header.
- An optional header needs required = false or defaultValue.
- A header whose data type cannot be converted causes an error when Spring resolves the parameter.
- Business rules for a header, such as eventType having to belong to an allowed list, need to be checked explicitly in the listener or in a dedicated validator/service.

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload @Valid OrderCreated order,
        @Header("eventType") String eventType,
        @Header(name = "tenantId", defaultValue = "public") String tenantId
) {
    if (!"OrderCreated".equals(eventType)) {
        throw new IllegalArgumentException("Unsupported eventType");
    }

    if (tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId must not be blank");
    }

    orderService.process(order, tenantId);
}
~~~

If you need Bean Validation for method parameters such as headers, you can configure separate method validation using Spring method validation and the corresponding constraints. Do not assume that @Valid on the payload automatically applies the same rules to every @Header parameter.

## 8. Configuring a JSON Converter and Validation in a JMS Listener

The example below uses Java 17, Spring Framework 6.2.19, Jackson 2, and Hibernate Validator. The Jackson converter turns a JSON TextMessage into a DTO; the validator checks the DTO; the listener receives the payload and metadata through the three annotations.

### Maven dependencies

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-listener-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
        </dependency>

        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>

        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>
</project>
~~~

A real application also needs the JMS provider client and a ConnectionFactory configuration suited to the broker in use. Spring Framework 6.x uses the Jakarta namespace jakarta.jms.

### DTO: OrderCreated.java

~~~java
package com.example.messaging;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal total,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency
) {
}
~~~

### Configuration: JmsConfiguration.java

~~~java
package com.example.messaging;

import java.util.Map;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public MappingJackson2MessageConverter orderMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created", OrderCreated.class)
        );

        return converter;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter
    ) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        return template;
    }

    @Bean
    public LocalValidatorFactoryBean jmsValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            Validator validator
    ) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();

        factory.setValidator(validator);
        return factory;
    }

    @Bean
    public JmsListenerConfigurer jmsListenerConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory
    ) {
        return new JmsListenerConfigurer() {
            @Override
            public void configureJmsListeners(
                    JmsListenerEndpointRegistrar registrar
            ) {
                registrar.setMessageHandlerMethodFactory(methodFactory);
            }
        };
    }
}
~~~

The converter uses a **TextMessage** for JSON and the property **_type** to identify the DTO type. The mapping uses the logical type ID order-created instead of passing the Java class name through the broker. When receiving a message, the converter uses that mapping to restore OrderCreated.

### Listener: OrderListener.java

~~~java
package com.example.messaging;

import java.util.Map;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

import jakarta.validation.Valid;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(
            @Payload @Valid OrderCreated order,
            @Header("eventType") String eventType,
            @Header(name = JmsHeaders.CORRELATION_ID, required = false)
            String correlationId,
            @Header(name = "tenantId", defaultValue = "public")
            String tenantId,
            @Headers Map<String, Object> headers
    ) {
        if (!"OrderCreated".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported eventType");
        }

        if (!Integer.valueOf(1).equals(headers.get("schemaVersion"))) {
            throw new IllegalArgumentException("Unsupported schemaVersion");
        }

        System.out.printf(
                "accepted order=%s total=%s currency=%s eventType=%s correlation=%s tenant=%s%n",
                order.orderId(),
                order.total(),
                order.currency(),
                eventType,
                correlationId,
                tenantId
        );
    }
}
~~~

### Producer Sending the Message: OrderPublisher.java

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish() {
        OrderCreated event = new OrderCreated(
                "ORD-1001",
                new java.math.BigDecimal("125.50"),
                "USD"
        );

        jmsTemplate.convertAndSend(
                "orders.queue",
                event,
                message -> {
                    message.setStringProperty("eventType", "OrderCreated");
                    message.setStringProperty("tenantId", "tenant-42");
                    message.setIntProperty("schemaVersion", 1);
                    message.setJMSCorrelationID("checkout-001");
                    return message;
                }
        );
    }
}
~~~

The producer sends a JSON body along with the JMS properties:

- **_type = order-created** created by MappingJackson2MessageConverter.
- **eventType = OrderCreated** so the listener can classify the event.
- **tenantId = tenant-42** to identify the tenant.
- **schemaVersion = 1** to check the contract version.
- **JMSCorrelationID = checkout-001** to trace the business flow.

When the listener receives the message, Spring converts the JSON into OrderCreated, maps the properties into headers, checks the DTO's constraints, and only then calls receive. If all checks succeed, the sample output is:

~~~text
accepted order=ORD-1001 total=125.50 currency=USD eventType=OrderCreated correlation=checkout-001 tenant=tenant-42
~~~

This is an integration example that requires a running JMS broker, with the ConnectionFactory and the queue orders.queue configured. The output only appears when a message is actually sent and the listener receives it successfully; it cannot be run standalone with just javac/java without a provider.

## 9. What Happens When the Input Is Invalid?

You need to classify errors by stage to choose how to handle them:

| Stage | Example | Result |
|---|---|---|
| JMS conversion | Malformed JSON, missing type ID, body of the wrong type | The converter throws an error; the listener method is not yet called. |
| Payload binding | The payload cannot be converted to the parameter type | Spring cannot resolve the parameter; the method is not yet called. |
| Header binding | A required eventType is missing or a header cannot be converted | Parameter resolution fails; the method is not yet called. |
| Bean Validation | orderId is empty or total is invalid | @Valid detects the constraint violation before the method runs. |
| Business validation | eventType is not supported or schemaVersion is wrong | The method has run and the business-check logic proactively rejects it. |

In the example configuration, the listener container uses a transacted session. When an error is thrown during processing, the transaction may roll back according to the container configuration. The provider decides redelivery according to the configured policy. You need a redelivery limit and a dead-letter queue/quarantine for malicious or unfixable messages; do not endlessly retry a payload with the wrong schema.

Validation does not replace exception handling. Log in a controlled manner, keep the correlation ID, classify transient errors versus data errors, and avoid logging the entire payload or sensitive headers.

## 10. Common Misconceptions

1. **“@Payload parses JSON by itself.”** Incorrect. The JMS MessageConverter must convert the body into the DTO before the listener receives the payload.
2. **“@Header directly reads every field in the JSON body.”** Incorrect. @Header reads the Spring message header that the mapper created from a JMS header/property or other metadata.
3. **“@Headers receives the body along with the headers.”** Incorrect. It receives a Map containing metadata; the body belongs to @Payload or Message.getPayload().
4. **“@Headers can be used with any parameter type.”** Incorrect. The parameter must be compatible with Map; MessageHeaders or Message<?> are other ways to access metadata.
5. **“A missing @Header always returns null.”** Incorrect. required defaults to true. Use required=false or defaultValue when the header is truly optional.
6. **“@Valid runs automatically just because Hibernate Validator is present.”** You need to configure a validator for DefaultMessageHandlerMethodFactory or use a suitable listener configuration.
7. **“@Valid on the payload also validates all headers.”** Incorrect. Payload validation and header binding are two separate things; header rules need required/defaultValue, business checks, or separate method validation.
8. **“A conversion error and a validation error are the same.”** Incorrect. Conversion creates the object; validation checks the constraints on the created object.
9. **“The @Headers Map is always safe to log.”** Incorrect. The Map can contain correlation, tenant, and sensitive metadata.
10. **“Just putting the property in the JSON lets @Header read it.”** Incorrect. The property must be sent by the producer as JMS properties or mapped by an adapter into a Spring header.
11. **“A validation failure automatically sends the message to the dead-letter queue.”** Incorrect. Redelivery and DLQ are policies of the listener container/provider/broker and need separate configuration.
12. **“Spring 6 still uses javax.validation.”** Incorrect. Spring Framework 6 uses the Jakarta namespace jakarta.validation; Spring 5.3 uses javax.validation.

## 11. Key Takeaways

- **@Payload** takes the body that the JMS MessageConverter has converted into a Java type.
- **@Header** takes one piece of metadata by name; a header is required by default.
- **@Headers** takes all the Spring message headers into a Map.
- **JmsHeaders** provides the standard names for correlation ID, message ID, destination, reply-to, timestamp, and other JMS attributes.
- **JmsHeaderMapper** converts JMS headers/properties into Spring headers; a custom property can be accessed by its name.
- **@Valid** checks the constraints on the payload; a Validator must be configured for DefaultMessageHandlerMethodFactory.
- Conversion, header binding, Bean Validation, and business validation are different layers of checking.
- With Spring 6.x, use jakarta.jms and jakarta.validation; the JMS JSON converter belongs to the package org.springframework.jms.support.converter.
- When validation or conversion fails, handle the transaction, redelivery, and DLQ according to the broker/container policy.

When building a JMS listener, clearly determine what type the body is converted into, which metadata is required, which is optional, and which constraints must be checked before the business logic. A listener with a clear input contract helps detect errors early and keeps the consumer safe when receiving messages from many producers.

## References

- [Spring Framework 6.2.19 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2 — JmsHeaders API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [Spring Framework — MappingJackson2MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [Spring Framework — DefaultMessageHandlerMethodFactory API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
