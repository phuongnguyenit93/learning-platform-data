# Configuring Consistent `RSocketStrategies` Between Requester and Responder

## Objectives

RSocket enables applications to exchange Java objects through binary payloads. Spring uses an `Encoder` to convert objects into payloads when sending and a `Decoder` to restore objects when receiving. `RSocketStrategies` groups these processing components along with related messaging configurations, ensuring requester and responder follow the same data contract.

This lesson shows how to align codecs, MIME types, route matchers, and metadata. The main examples use Java, Spring Framework 7, and Jackson 3; a later section explains how to apply this in Spring Boot and the differences from Spring Framework 6.

## 1. What Is `RSocketStrategies` Responsible For?

`RSocketStrategies` is a reusable configuration set for RSocket. Its core components are:

- **Encoders:** convert Java objects into binary data to send over the connection.
- **Decoders:** convert received binary data into Java objects.
- **MetadataExtractor:** decodes metadata into values handlers can access, such as custom headers.
- **RouteMatcher:** matches incoming routes against patterns in `@MessageMapping`.
- **ReactiveAdapterRegistry:** allows Spring to work with supported reactive types.

The encoder on the sending side must be compatible with the decoder on the receiving side. For example, if the requester sends `CustomerQuery`, the responder must have a decoder that understands that payload's format and structure. When the responder returns `CustomerView`, the responder needs the corresponding encoder and the requester needs the corresponding decoder.

If requester and responder run in the same application, you can declare a single `RSocketStrategies` bean and pass the same instance to both sides. If they run in two separate processes, each process creates its own configuration but must agree on the contract: payload format, MIME type, DTO schema, field naming rules, and metadata.

### Default Codecs and Extended Codecs

The basic codecs from `spring-core` support `String`, `byte[]`, and `ByteBuffer`. To exchange JSON, CBOR, or Protobuf DTOs, the application needs the corresponding module and encoders/decoders; common web codecs reside in `spring-web`.

The examples below use `JacksonJsonEncoder` and `JacksonJsonDecoder` from Spring Framework 7, the branch integrating Jackson 3. In a Spring Boot application, `spring-boot-starter-rsocket` provides dependencies for Boot to auto-configure CBOR and JSON codecs. If configuring Spring Framework manually, you need `spring-web` along with compatible Jackson modules on the classpath and aligned versions.

Do not assume every Java object can be transmitted automatically. Without an appropriate encoder, encoding the request or response will fail. Without a corresponding decoder on the receiving side, it cannot restore the payload into the expected type.

## 2. Distinguishing Strategies and MIME Types

These two concepts are related but serve different roles:

- `RSocketStrategies` defines **which encoders, decoders, and processing mechanisms are available**.
- `dataMimeType` defines **the format of the data payload on the connection**. This MIME type is declared in the `SETUP` frame and applies to data payloads of requests on the connection.
- `metadataMimeType` defines the metadata format of the connection. By default, Spring uses composite metadata so multiple metadata entries can each carry their own MIME type.

`RSocketRequester.Builder` provides `dataMimeType(MimeType)` and `metadataMimeType(MimeType)` to configure MIME types in the `SETUP` frame. If no data MIME type is specified, Spring infers a default from the first configured decoder. When an application has multiple codecs, specifying the MIME type explicitly makes the contract easier to read and verify.

The server reads the MIME type from the `SETUP` frame. If the client sends `application/json`, the server must have a decoder compatible with that MIME type. Having the right encoder/decoder classes with an incompatible MIME type can still cause encode/decode errors.

## 3. Creating a Shared Configuration for Requester and Responder

The following example registers JSON codecs with Jackson 3 and uses `PathPatternRouteMatcher` for pattern-based route matching.

Create `RSocketConfiguration.java`:

~~~java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.JacksonJsonDecoder;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
                .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

Explanation:

1. `RSocketStrategies.builder()` creates a builder with default basic codecs.
2. `encoders(...)` adds the JSON encoder to serialize DTOs.
3. `decoders(...)` adds the JSON decoder to deserialize DTOs.
4. `routeMatcher(...)` uses `PathPatternRouteMatcher` from `spring-web`. RSocket routes remain messaging routes, not HTTP URLs.
5. `RSocketMessageHandler.setRSocketStrategies(...)` applies the same strategies to the responder. The handler receives encoders/decoders, route matcher, and metadata extractor from that strategies instance.

When creating the requester, pass the same bean to the builder:

~~~java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketRequester customerRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);
    }
}
~~~

The requester uses the same registered encoders/decoders and declares the data MIME type as `application/json`. The server receives this MIME type in the `SETUP` frame and selects a compatible decoder.

`tcp("localhost", 7000)` creates a requester for the server address. The connection is not necessarily opened right on this line; Spring establishes and uses the connection when the first request occurs.

Configuring `RSocketMessageHandler` in this example applies when the application manages Spring Messaging handlers manually. If Spring Boot already auto-configures the handler and server, use Boot's customization approach in section 6 and avoid declaring a duplicate handler.

## 4. Using DTOs on Both Sides

Suppose the requester sends a request to find a customer by ID and the responder returns customer information.

Create two DTOs:

~~~java
package example.rsocket;

public record CustomerQuery(String customerId) {
}
~~~

~~~java
package example.rsocket;

public record CustomerView(String customerId, String displayName) {
}
~~~

The responder receives the decoded DTO and returns another DTO:

~~~java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class CustomerResponder {

    @MessageMapping("customers.find")
    public Mono<CustomerView> find(
            @Payload CustomerQuery query) {

        CustomerView result =
                new CustomerView(query.customerId(), "Nguyen An");

        return Mono.just(result);
    }
}
~~~

The requester calls the corresponding route:

~~~java
package example.rsocket;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CustomerClient {

    private final RSocketRequester requester;

    public CustomerClient(RSocketRequester customerRequester) {
        this.requester = customerRequester;
    }

    public Mono<CustomerView> find(String customerId) {
        return requester
                .route("customers.find")
                .data(new CustomerQuery(customerId))
                .retrieveMono(CustomerView.class);
    }
}
~~~

The encode/decode flow proceeds as follows:

| Step | Side | Task |
|---|---|---|
| 1 | Requester | JSON encoder converts `CustomerQuery` into payload |
| 2 | Responder | JSON decoder reads payload into `CustomerQuery` |
| 3 | Responder | Handler processes and creates `CustomerView` |
| 4 | Responder | JSON encoder converts `CustomerView` into response payload |
| 5 | Requester | JSON decoder reads response into `CustomerView` |

The result of `retrieveMono(CustomerView.class)` is `Mono<CustomerView>`. The requester receives the object once the response is decoded and the pipeline is subscribed to.

In this example, the DTOs exist on both sides so they can be placed in a shared contract module or maintained with compatible schemas. If the two sides evolve independently, manage changes to fields, data types, nullability, and schema versions as an API contract.

## 5. When Requester and Responder Live in Separate Applications

Two applications cannot share a single Spring bean over the network. Each application must declare an equivalent configuration:

- Same data MIME type, such as `application/json`.
- Requester has an encoder for outbound DTOs and a decoder for inbound responses.
- Responder has a decoder for inbound requests and an encoder for outbound responses.
- Same serialization/deserialization conventions, such as JSON field names, enums, date/time formats, and numeric types.
- Same metadata conventions if the application sends custom metadata.

If one side changes a DTO structure while the other has not updated yet, payloads may remain valid JSON while becoming incompatible at the business level. Prefer backward-compatible changes: add optional fields with defaults, preserve the meaning of existing fields, and never silently change data types.

You can package codecs and DTO schemas into an internal library to prevent two teams from configuring them differently. However, library and schema versions must still be managed in sync.

## 6. Customizing in Spring Boot

Spring Boot auto-configures an `RSocketStrategies` bean. With `spring-boot-starter-rsocket`, Boot can auto-configure CBOR and JSON codecs based on classpath dependencies. Boot also auto-configures `RSocketMessageHandler` and an `RSocketRequester.Builder` bean.

In a Spring Boot project, if you only need to add configuration, use `RSocketStrategiesCustomizer` to customize the Boot-managed builder. For example, adding a route matcher:

~~~java
package example.rsocket;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketStrategiesConfiguration {

    @Bean
    RSocketStrategiesCustomizer routeMatcherCustomizer() {
        return strategies ->
                strategies.routeMatcher(new PathPatternRouteMatcher());
    }
}
~~~

The requester can use the Boot-injected builder:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class CustomerClient {

    private final RSocketRequester requester;

    public CustomerClient(RSocketRequester.Builder builder) {
        this.requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);
    }
}
~~~

Boot's builder is a prototype bean because it holds configuration state. Each injection point receives a new builder. Do not hold onto one builder and reuse it to create multiple requesters with different connection configurations.

If you need to add custom encoders/decoders, they can be added via `RSocketStrategiesCustomizer`. Watch codec order: `@Order` on customizers affects application order; encoder/decoder order can also affect codec selection when multiple codecs support the same MIME type.

Do not create an entirely new `RSocketStrategies` bean just to add a single codec if your goal is to retain the codecs Boot already auto-configured. Replacing the bean can drop default configuration that the application relies on.

## 7. Metadata Must Also Be Aligned

Data and metadata are two separate sections in an RSocket message. The route is normally sent as metadata. Spring supports composite metadata and routing metadata by default in `RSocketMessageHandler`.

If an application sends custom metadata, such as a tenant ID or tracing information, you must configure the corresponding decoder and `MetadataExtractor`. Registering an encoder on the requester alone is not enough: the responder must understand the MIME type and decode the metadata into headers or values accessible to handlers.

For example, a handler can receive extracted metadata via `@Header`:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenantId") String tenantId) {

    return orderService.find(tenantId, query.orderId());
}
~~~

The `tenantId` header name only holds a value if the metadata extractor has been configured to decode the corresponding metadata entry and put it into the header map. For standard metadata like `route`, Spring provides default support; for custom MIME types, register a decoder and extraction rule on the receiving side.

Do not change `metadataMimeType` arbitrarily. If switching from composite metadata to another format, requester and responder must both understand the new format, including how routes and other metadata are represented.

## 8. Common Errors and How to Check

1. **DTOs present but codecs missing:** errors occur when Spring finds no encoder or decoder supporting the object type. Check dependencies and the codec list in strategies.
2. **The two sides use different MIME types:** requester declares JSON while responder lacks a compatible JSON decoder. Check `dataMimeType` in `SETUP` and the MIME types supported by codecs.
3. **Only encoder or only decoder configured:** requests may succeed in sending while responses fail to decode, or vice versa. Verify both request and response directions.
4. **Replacing Boot's bean and losing default codecs:** check whether the application is overriding the Boot-auto-configured `RSocketStrategies`. Prefer `RSocketStrategiesCustomizer` when only extending configuration.
5. **Route mismatch:** check the route in `requester.route(...)` against `@MessageMapping` and `RouteMatcher` configuration. RSocket routes typically use dots as separators; do not treat routes like HTTP URLs.
6. **Custom metadata missing in handler:** check MIME type, decoder, and `MetadataExtractor` configuration. An encoder on the requester does not automatically create headers for the responder.
7. **DTO changes break compatibility:** check required fields, data types, enums, date/time handling, and unknown-field handling. Use contract tests between client and server versions.

When debugging, identify which stage failed: sender-side encoding, transport/connection, route matching, receiver-side decoding, handler execution, or response encoding/decoding. Categorizing this way helps narrow down the exact configuration to inspect.

## 9. Implementation Checklist

- [ ] Choose a clear payload format and MIME type, e.g. JSON with `application/json`.
- [ ] Both sides have encoders and decoders matching the DTOs to be exchanged.
- [ ] Requester passes the proper `RSocketStrategies` or uses customized Boot configuration.
- [ ] Responder uses the same strategies or an equivalent configuration.
- [ ] Route matcher supports the route style in use.
- [ ] Custom metadata has a decoder and metadata extractor on the receiving side.
- [ ] DTOs and serialization rules are managed as an API contract.
- [ ] Real request/response tests run between requester and responder.

## References

- [Spring Framework Reference — RSocket, Strategies, and Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket auto-configuration and RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocketStrategies — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [RSocketMessageHandler — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)

### Version Notes

The main JSON codec example above uses Spring Framework 7 with Jackson 3: `JacksonJsonEncoder` and `JacksonJsonDecoder`. For Spring Framework 6 / Spring Boot 3 using Jackson 2, the corresponding classes are `Jackson2JsonEncoder` and `Jackson2JsonDecoder`. Do not mix Jackson 2 and Jackson 3 codecs in the same configuration without deliberate intent and matching dependencies. Verify APIs against the Spring version used in your project.
