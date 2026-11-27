# Configuring Serializers with Native Encoding

## Objectives

Spring Cloud Stream allows applications to send Java payloads through an output binding without interacting directly with the Kafka Producer API. In normal conversion mode, the framework uses message converters and content types to transform payloads into a transportable representation. When you need to control the wire format via the Kafka client, the producer binding can enable **native encoding** to delegate encoding to a configured Kafka Serializer.

Native encoding is useful when a producer needs to use a JSON serializer, Avro/Protobuf serializer, schema registry, or a format compatible with non-Java systems. It is important to configure the right serializers for both key and value, understand the boundary between message conversion and serialization, and test the actual bytes written to the topic.

After this lesson, you will be able to:

- Explain Kafka binder native encoding.
- Enable use-native-encoding on an output binding.
- Configure Kafka key serializer and value serializer separately.
- Choose the right serializer for String, JSON, byte array, or schema-based formats.
- Understand the impact of type headers and content type.
- Test the wire format and readability from consumers in other languages.
- Avoid configuring serializers incompatible with the data the producer sends.

## 1. Message conversion and native serialization

In normal mode, Spring Cloud Stream receives a Java payload and then uses a message converter based on content type to convert the payload before the binder sends the data. For example, a POJO can be converted into JSON bytes when the binding uses application/json.

When native encoding is enabled, the Kafka binder uses the Kafka client's serializer to encode the key/value. Spring Cloud Stream's default payload conversion path is bypassed for the corresponding encoding; the outgoing payload type must be compatible with the configured serializer.

High-level processing flow:

    Java object / Spring Message
        -> Is native encoding enabled?
            -> No: Spring Cloud Stream MessageConverter
            -> Yes: Kafka key/value Serializer
        -> Kafka binder / Producer
        -> Kafka record bytes
        -> Kafka topic

The two approaches can be summarized as:

| Mode | Payload encoding component | How format is chosen |
|---|---|---|
| Framework conversion | Spring MessageConverter | Content type and payload type |
| Native encoding | Kafka client Serializer | key.serializer and value.serializer |

Native encoding does not disable all Spring Messaging features. The application can still construct a Message, attach application headers, and send through a binding. The main change is that the Kafka client serializer becomes responsible for encoding the key/value according to the native configuration.

## 2. Enabling native encoding on an output binding

The use-native-encoding property is placed under the output binding's producer configuration:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true

In this example:

- paymentEvents-out-0 is the output binding of the paymentEvents function.
- payments.captured is the target Kafka topic.
- use-native-encoding: true instructs the Kafka binder to use native serializers for producer data.
- The actual serializers are configured under the Kafka binder namespace.

Enabling native encoding without configuring appropriate serializers can cause the application to fail on startup or fail when sending messages. Configure the serializers at the same time and verify the payload type the function actually returns.

### Configuring serializers per binding

The Kafka binder lets you set client properties specifically for a producer binding:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    key.serializer: org.apache.kafka.common.serialization.StringSerializer
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
                    spring.json.add.type.headers: false

This configuration uses:

- StringSerializer for the record key.
- Spring Kafka JsonSerializer for the record value.
- spring.json.add.type.headers: false to omit Spring Kafka's proprietary type information headers from the record; useful when the JSON wire format needs to be consumed by clients not using Spring Kafka.

Property names and classes must be compatible with the Kafka client/Spring Kafka version in the application. If using Confluent, Apicurio, or another schema library's serializer, swap in that serializer class and provide the corresponding schema registry properties.

## 3. Key and value serializers are two separate configurations

A Kafka record can contain both a key and a value. The Kafka client encodes these two parts independently, so two different serializers can be used.

| Record part | Application type | Common serializer |
|---|---|---|
| Key | String, e.g., order-42 | StringSerializer |
| Value | Event POJO | Spring Kafka JsonSerializer |
| Key | UUID or custom type | Serializer matching the agreed wire format |
| Value | byte[] | ByteArraySerializer |
| Value | Avro/Protobuf | Corresponding schema/registry-integrated serializer |

Example event:

    public record PaymentCaptured(
            String eventId,
            String orderId,
            long amountMinor,
            String currency
    ) {}

Function producing the payload:

    @Bean
    Supplier<PaymentCaptured> paymentEvents(PaymentEventSource source) {
        return source::next;
    }

With JsonSerializer, the value is a Java object and the serializer converts it into JSON bytes. If ByteArraySerializer is configured, the outgoing payload must be a byte[]; this serializer does not automatically convert a POJO into JSON.

### Setting the Kafka record key

The key can be set via the Kafka message header supported by the Kafka binder/Spring Kafka. Example with Spring Kafka:

    import org.springframework.kafka.support.KafkaHeaders;
    import org.springframework.messaging.Message;
    import org.springframework.messaging.support.MessageBuilder;

    Message<PaymentCaptured> message = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.orderId())
            .build();

    streamBridge.send("paymentEvents-out-0", message);

KafkaHeaders.KEY is metadata specifying the record key; it is not part of the JSON value. The key serializer must accept the value type placed in the header. In this example, the key is a String, so StringSerializer is used.

If the application does not need a key, configure and verify null-key behavior according to partitioning requirements. Do not configure a serializer expecting a UUID and then send a String key, or vice versa.

## 4. Common serializer choices

### StringSerializer

Use when the key or value is a string:

    value.serializer: org.apache.kafka.common.serialization.StringSerializer

The payload must be a String. If the application sends a POJO, StringSerializer will not automatically invoke Jackson to turn the POJO into JSON. Convert it to a string explicitly or choose an appropriate serializer.

### ByteArraySerializer

Use when the application already produces bytes in the target wire format:

    value.serializer: org.apache.kafka.common.serialization.ByteArraySerializer

This approach works well when another library has already encoded JSON, Avro, or Protobuf into a byte array. Ensure encoding, schema, and version are agreed upon between producer and consumer.

### Spring Kafka JsonSerializer

Use when the payload is a POJO and you want Spring Kafka/Jackson to produce JSON bytes:

    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer

JsonSerializer serializes Java objects to JSON. Type header configuration is a compatibility decision:

- Spring Kafka type headers can help Spring Kafka JsonDeserializer determine the target class.
- Python, Go, or Java consumers not using Spring Kafka can ignore Kafka headers and parse the JSON value using their own schema.
- If consumers do not rely on type headers, you can disable them and declare the target type/schema on the receiving side.
- Do not treat producer-sent type headers as trusted proof for deciding which classes are allowed to be deserialized.

In polyglot systems, the JSON contract should be defined independently of Java class names. Do not require consumers to know the producer's package or class names.

### Avro, Protobuf, and schema registry

For Avro or Protobuf, serializers typically integrate with a schema registry to store schemas/versions and encode records in that ecosystem's wire format. Configuration typically requires:

- The serializer class matching the schema platform.
- Schema registry URL and credentials.
- Subject naming strategy or schema registration rules.
- Compatibility policy.
- The schema/record type sent by the producer.

The example below only illustrates where to declare properties; exact property names depend on the serializer/registry:

    spring:
      cloud:
        stream:
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                    schema.registry.url: https://schema-registry.example

Do not use the class or property names from this example if the corresponding dependencies are not present in your application. A schema registry is not automatically activated merely by enabling native encoding.

## 5. Native encoding and content type

content-type in Spring Cloud Stream describes the payload format at the framework abstraction level and helps select message converters. When native encoding is enabled, the Kafka serializer is what determines the key/value bytes.

Example:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-out-0:
              content-type: application/json
              producer:
                use-native-encoding: true

When native encoding is enabled, do not rely on content-type to replace value.serializer. If the serializer is Avro while content type is declared as JSON, the configuration will mislead readers and may cause consumers to pick the wrong decoding mechanism.

Align these three elements:

1. The Java type produced by the function.
2. The serializer actually used to produce the Kafka record bytes.
3. The wire format/schema expected by consumers.

Content type may still appear in the Spring Message or metadata depending on configuration, but it does not turn one serializer into another. If a consumer needs to use Spring MessageConverter, explicitly check whether the consumer binding uses native decoding or framework conversion.

## 6. Native encoding vs. native decoding

Native encoding is a **producer binding** decision. Native decoding is a separate **consumer binding** decision.

| Property | Location | Function |
|---|---|---|
| use-native-encoding | bindings.<name>.producer | Uses Kafka serializer to encode records when sending |
| use-native-decoding | bindings.<name>.consumer | Uses Kafka deserializer to decode records when receiving |

Example of a consumer using native decoding:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-in-0:
              destination: payments.captured
              group: billing-service
              consumer:
                use-native-decoding: true
          kafka:
            bindings:
              paymentEvents-in-0:
                consumer:
                  configuration:
                    value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                    spring.json.value.default.type: com.example.events.PaymentCaptured
                    spring.json.trusted.packages: com.example.events

This is a consumer-side configuration illustrating the independence of both sides. A consumer can use native decoding while another producer uses framework conversion, as long as the resulting wire format is compatible. Conversely, a producer using native encoding does not force every consumer to use native decoding; consumers can use the conversion path if binder configuration and payload allow it.

When using Spring Kafka JsonDeserializer, check type mapping and trusted packages according to security policy. Trust only necessary packages; do not widen the scope arbitrarily when receiving data from untrusted producers.

## 7. Complete example: Spring Cloud Stream publishing JSON for polyglot consumers

Suppose a payment service publishes events to be read by both Java and Python consumers. The JSON contract is defined independently of Java classes:

    {
      "eventId": "evt-901",
      "eventType": "payment.captured",
      "orderId": "order-42",
      "amountMinor": 12550,
      "currency": "VND"
    }

Java Producer:

    public record PaymentCaptured(
            String eventId,
            String eventType,
            String orderId,
            long amountMinor,
            String currency
    ) {}

    @Bean
    Supplier<PaymentCaptured> paymentEvents(PaymentEventSource source) {
        return source::next;
    }

Configuration:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    key.serializer: org.apache.kafka.common.serialization.StringSerializer
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
                    spring.json.add.type.headers: false

With this configuration, Kafka JsonSerializer produces JSON bytes from the PaymentCaptured object. A Python consumer can read the value bytes and parse JSON without knowing the Java class:

    import json

    def decode_payment(value: bytes) -> dict:
        event = json.loads(value.decode("utf-8"))
        required = {
            "eventId",
            "eventType",
            "orderId",
            "amountMinor",
            "currency",
        }
        missing = required - event.keys()
        if missing:
            raise ValueError(f"Missing fields: {sorted(missing)}")
        return event

The Python example only illustrates decoding and validating required fields; a production consumer also needs to manage polling, offset commits, retries, and idempotency according to the client in use.

The key point is that both sides agree on the JSON schema, field names, data types, and semantics. Disabling Spring type headers avoids introducing Java class names into polyglot consumer compatibility requirements; it does not replace schema validation.

## 8. Per-binding or binder-wide configuration?

When multiple output bindings use different serializers, per-binding configuration limits the blast radius:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
            auditEvents-out-0:
              destination: audit.events
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
              auditEvents-out-0:
                producer:
                  configuration:
                    value.serializer: org.apache.kafka.common.serialization.StringSerializer

In this example, the payment binding sends JSON POJOs while the audit binding sends Strings. Producer code must send the corresponding types. If all bindings share the same serializer, you can consider configuring it at the binder/client level as supported by your version; however, per-binding configuration is usually easier to control when wire contracts differ.

Do not place serializer classes inside domain code. Keep serializer selection in adapter/binder configuration so changing wire formats does not force domain services to depend on the Kafka client.

## 9. Common errors when enabling native encoding

| Symptom | Possible cause | Resolution |
|---|---|---|
| Producer fails when sending a POJO | Using StringSerializer or ByteArraySerializer which does not accept POJOs | Choose JsonSerializer or encode to the right type before sending |
| Consumer cannot read record | Serializer and deserializer do not share the same wire format | Align both sides and inspect actual bytes |
| Python reads JSON but Java consumer gets a type error | Consumer depends on type headers or has different DTO mapping | Use a clear contract/schema and configure target type on consumer |
| Record key fails while value succeeds | Key serializer is incompatible with the key header | Check key type and key.serializer separately |
| Content type is JSON but bytes are not JSON | Native serializer produces a different format | Verify serializer and wire format, do not just read content type |
| Avro consumer cannot find schema | Wrong registry URL, subject, or credentials | Check serializer, registry, and schema compatibility |
| Application fails to start | Serializer class missing from classpath or misconfigured | Check dependencies and properties for your binder version |
| Type header causes dependency on producer class | Spring Kafka JsonSerializer adds type information | Disable type headers if contract does not use them and verify consumer |

Serialization errors generally cannot be resolved by retrying a message indefinitely. If a payload has a type incompatible with the serializer, you must fix the code or configuration; retrying merely repeats the same error.

## 10. Testing serializers and wire format

Testing must prove that the serializer actually produces bytes conforming to the contract, not merely that the Spring application context starts up.

### Unit testing the serializer

You can test the serializer directly:

    @Test
    void shouldSerializePaymentAsJson() {
        JsonSerializer<PaymentCaptured> serializer =
                new JsonSerializer<PaymentCaptured>().noTypeInfo();

        PaymentCaptured event = new PaymentCaptured(
                "evt-901",
                "payment.captured",
                "order-42",
                12550L,
                "VND"
        );

        byte[] bytes = serializer.serialize("payments.captured", event);
        String json = new String(bytes, StandardCharsets.UTF_8);

        assertTrue(json.contains("\"eventId\":\"evt-901\""));
        assertTrue(json.contains("\"amountMinor\":12550"));
    }

This test verifies that the JSON serializer produces the expected content. In a production application, use the same serializer class/configuration as the Kafka binder to avoid testing a different configuration from runtime.

### Integration testing with Kafka

Use Kafka Testcontainers or a test broker to verify:

- Output binding has native encoding enabled.
- Key serializer and value serializer are initialized properly.
- Record key and value bytes match the wire format.
- Custom application headers are propagated according to binder configuration.
- Polyglot consumers or consumers using matching deserializers can read the record.
- Serializer errors are reported accurately and not mistaken for broker delivery failures.
- Schema/DTO changes still satisfy the compatibility policy.

The Test Binder is useful for wiring and function behavior, but it does not replace Kafka broker integration tests when verifying Kafka client serializers and actual record bytes.

## 11. Configuration workflow in production

When enabling native encoding for an output binding:

1. Identify the Java payload sent by the function or StreamBridge.
2. Finalize the wire format: String, JSON, byte array, Avro, Protobuf, or another format.
3. Choose the value serializer; choose the key serializer separately if keys are used.
4. Enable use-native-encoding on the exact output binding.
5. Set client serializer properties in the Kafka binder namespace for that binding.
6. If using a schema registry, configure endpoint, credentials, subject strategy, and compatibility.
7. Decide whether to use Spring Kafka type headers; for polyglot consumers, prefer contracts independent of class names.
8. Align deserializers/schemas on all consumers.
9. Verify record bytes using integration tests on Kafka.
10. Monitor serialization errors, producer error rates, and schema registry failures after deployment.

Schema registry credentials must be managed via a secret store or secure environment variables; do not commit passwords to YAML. Serializers and schemas are part of the integration contract, so any wire format changes must be versioned and compatibility-tested.

## Conclusion

Native encoding lets the Kafka binder use Kafka client Serializers to encode keys and values instead of Spring Cloud Stream's default message conversion. Enable use-native-encoding on the producer binding, then configure key.serializer and value.serializer according to the data types and wire contract.

For JSON, Spring Kafka JsonSerializer can convert POJOs to JSON bytes; for String, byte array, Avro, or Protobuf, choose the corresponding serializer. Content type does not replace the serializer when native encoding is enabled, and native encoding is independent of native decoding on the consumer. Check key/value separately, control type headers, and verify actual bytes on Kafka to ensure Java or polyglot consumers read the same contract.
