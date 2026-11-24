# RSocketMessageHandler and Annotation-Based Handlers

## 1. Role of RSocketMessageHandler

In Spring Framework, RSocketMessageHandler dispatches incoming requests to an RSocket responder following Spring's message-handling model. It bridges the RSocket protocol with annotation-declared handler methods:

1. Receive a request or connection event from RSocket.
2. Read the route and metadata from the payload.
3. Locate the matching method based on @MessageMapping or @ConnectMapping.
4. Decode the payload into the Java parameter types and convert metadata into injectable values.
5. Invoke the handler method and encode the return value into a response or stream.

RSocketMessageHandler does not open a TCP/WebSocket port on its own. The responder() method creates a SocketAcceptor to attach to RSocketServer or to an RSocketRequester on the client side. Therefore, three responsibilities should be distinguished:

- RSocketServer and the transport are responsible for listening for and accepting connections.
- RSocketMessageHandler is responsible for finding and invoking message-handling methods.
- RSocketRequester is responsible for sending requests and reading responses on the requester side.

RSocket is bidirectional. Once a connection is established, both sides can both send requests and act as responders; the terms client and server only describe the roles when initiating the connection.

## 2. Routes and Handler Annotations

### @Controller

An RSocketMessageHandler declared as a Spring bean on the server side detects @Controller beans with @MessageMapping or @ConnectMapping methods by default. This is the handler registration mechanism; simply writing an annotated class without registering that class in the Spring ApplicationContext is not enough for the handler to detect it.

If an application has multiple types of responders—for example, a server and multiple client responders in the same ApplicationContext—you can change the handler detection condition using handlerPredicate. This helps prevent a handler class from being accidentally registered with an unintended responder.

### @MessageMapping

@MessageMapping maps a route in the request metadata to a method that handles an RSocket request. The annotation can be placed at the class level to declare a common prefix and at the method level to declare the specific route segment.

Example:

~~~java
@Controller
@MessageMapping("catalog")
public class CatalogRSocketController {

    @MessageMapping("products.{sku}")
    public Mono<Product> find(
            @DestinationVariable("sku") String sku) {
        // Handle the product lookup request.
        return Mono.empty();
    }
}
~~~

With the default route matcher configuration using a dot as the separator, the full route of the method above has the form catalog.products.{sku}. A request with route catalog.products.A-101 passes the value A-101 to the sku parameter.

An RSocket route resides in metadata, not an HTTP URL. You should not mechanically apply URL routing rules, URL decoding, or HTTP configuration from Spring MVC/WebFlux to RSocket routes.

Commonly used parameters in @MessageMapping methods:

| Parameter | Meaning |
| --- | --- |
| @Payload | The request payload; Spring decodes it into the parameter type. Can be an object or a reactive type such as Mono/Flux. |
| @DestinationVariable | Value extracted from a variable in the route pattern. |
| RSocketRequester | Requester bound to the current connection, used when the responder needs to send requests back to the other side. |
| @Header | A metadata value registered with MetadataExtractor. |
| @Headers Map<String, Object> | Metadata values extracted and converted into headers. |

@Payload can be omitted when the parameter is an object type that does not belong to the special parameter groups already supported by Spring. However, explicitly writing @Payload often makes the handler signature easier to read.

### @ConnectMapping

@ConnectMapping handles connection-level events rather than ordinary business requests. This annotation maps:

- The initial SETUP frame when an RSocket connection is established.
- Subsequent metadata push notifications via METADATA_PUSH frames.

@ConnectMapping can declare a route pattern to accept only connections with matching route metadata. If no pattern is declared, the method matches all setup and metadata push events. It can also be combined with class-level @MessageMapping to share a common route prefix.

A @ConnectMapping method does not return data. The return type must be void or Mono<Void>. On the server side, if handling SETUP returns an error, the new connection can be rejected. On the client side, this acts as a callback and does not determine connection establishment.

An important note: do not block SETUP handling to wait for a new request sent back through RSocketRequester. If you need to actively call the other side as soon as the connection starts, decouple sending that request from the connection-handling flow and perform it asynchronously.

## 3. Cardinality Determines the RSocket Interaction Model

RSocket supports four interaction models:

- Request-Response: send one message and receive one message.
- Request-Stream: send one message and receive a stream of messages.
- Request-Channel: both sides exchange streams of messages.
- Fire-and-Forget: send a one-way message without waiting for a response.

With @MessageMapping, Spring infers the interaction model based on the input and output cardinality of the method signature.

| Cardinality | Meaning in handler signature |
| --- | --- |
| 0 input | No @Payload parameter. |
| 1 input | A concrete value or a single-element asynchronous type such as Mono<T>. |
| Many input | A multi-element asynchronous type such as Flux<T>. |
| 0 output | void or a non-emitting type such as Mono<Void>. |
| 1 output | A concrete object or Mono<T>. |
| Many output | A multi-element type such as Flux<T>. |

Supported combinations:

| Input cardinality | Output cardinality | Interaction model |
| --- | --- | --- |
| 0 or 1 | 0 | Fire-and-Forget, Request-Response |
| 0 or 1 | 1 | Request-Response |
| 0 or 1 | Many | Request-Stream |
| Many | 0, 1, or Many | Request-Channel |

Examples:

- Mono<Product> represents a single result.
- Flux<Product> represents a stream of results.
- Mono<Void> represents completion without emitting a value.
- Flux<Command> as input indicates that the handler receives multiple messages in a request-channel.

RSocket uses Reactive Streams so demand and back pressure can propagate across network boundaries. When handling a Flux, keep processing reactive if possible; do not call block() inside a handler because that operation can block the processing thread and defeat the benefits of the asynchronous model.

## 4. Configuring RSocketMessageHandler

The typical server-side configuration declares RSocketMessageHandler as a bean. The example below chooses PathPatternRouteMatcher:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketHandlerConfiguration {

    @Bean
    public RSocketMessageHandler rSocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

By default, the handler uses SimpleRouteMatcher based on AntPathMatcher. PathPatternRouteMatcher from spring-web uses pre-parsed routes and patterns, which is usually more efficient when there are many routes to match. Both matchers use a dot as the default route separator. An RSocket route is an application hierarchical string, not a URL path.

After obtaining the bean, you can attach the responder to RSocketServer:

~~~java
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.context.ApplicationContext;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;

ApplicationContext context = /* Application's ApplicationContext */;
RSocketMessageHandler handler =
        context.getBean(RSocketMessageHandler.class);

var server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
~~~

The bind snippet above illustrates how to connect the adapter to the RSocket Java API. A real application needs to manage the lifecycle of the returned channel and dispose of the channel when stopping the server. If using Spring Boot, you can let Boot manage the server/transport configuration; the important part here is the responder provided by RSocketMessageHandler.

## 5. Controller Example Handling Multiple Request Types

The following example uses Java 17 records to represent payloads. The controller has the route prefix catalog and four handlers: request-response, request-stream, request-channel, and fire-and-forget.

~~~java
import java.util.Map;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
@MessageMapping("catalog")
public class CatalogRSocketController {

    private final Map<String, Product> products = Map.of(
            "A-101", new Product("A-101", "Keyboard", 12),
            "B-205", new Product("B-205", "Mouse", 0)
    );

    // Request-Response: one route variable, one result.
    @MessageMapping("products.{sku}")
    public Mono<Product> find(
            @DestinationVariable("sku") String sku) {
        return Mono.justOrEmpty(products.get(sku));
    }

    // Request-Stream: one payload, multiple results.
    @MessageMapping("products.available")
    public Flux<Product> available(
            @Payload AvailabilityFilter filter) {
        return Flux.fromIterable(products.values())
                .filter(product ->
                        product.stock() >= filter.minimumStock());
    }

    // Request-Channel: receive a stream of commands and return a stream of results.
    @MessageMapping("stock.echo")
    public Flux<StockCommand> echo(
            @Payload Flux<StockCommand> commands) {
        return commands.doOnNext(System.out::println);
    }

    // Fire-and-Forget: receive one payload and complete without emitting data.
    @MessageMapping("audit.record")
    public Mono<Void> record(@Payload AuditEvent event) {
        return Mono.fromRunnable(() ->
                System.out.println("audit=" + event.action()));
    }

    public record Product(String sku, String name, int stock) {
    }

    public record AvailabilityFilter(int minimumStock) {
    }

    public record StockCommand(String sku, int delta) {
    }

    public record AuditEvent(String action) {
    }
}
~~~

The full routes formed from the catalog prefix and the method-level routes:

| Method | Route | Interaction model |
| --- | --- | --- |
| find | catalog.products.{sku} | Request-Response |
| available | catalog.products.available | Request-Stream |
| echo | catalog.stock.echo | Request-Channel |
| record | catalog.audit.record | Fire-and-Forget |

The find method does not need a payload because the SKU is already in the route. The available method receives an AvailabilityFilter object and emits multiple Products. The echo method receives Flux<StockCommand>, so it is a bidirectional stream. The record method returns Mono<Void>; the requester can use send() to send as Fire-and-Forget.

## 6. Sending Requests with RSocketRequester

RSocketRequester provides a fluent API to declare the route, payload, and expected result type. Example:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

// Request-Response.
Mono<CatalogRSocketController.Product> product =
        requester.route("catalog.products.A-101")
                .retrieveMono(CatalogRSocketController.Product.class);

// Request-Stream.
Flux<CatalogRSocketController.Product> available =
        requester.route("catalog.products.available")
                .data(new CatalogRSocketController.AvailabilityFilter(1))
                .retrieveFlux(CatalogRSocketController.Product.class);

// Fire-and-Forget.
Mono<Void> sent =
        requester.route("catalog.audit.record")
                .data(new CatalogRSocketController.AuditEvent("PRODUCT_VIEWED"))
                .send();
~~~

Calling send() returns Mono<Void> to signal that sending the message has completed. It does not confirm that the receiving handler method has finished processing the message. If you need a processing result, use an interaction model with a response such as Request-Response.

RSocketRequester also supports Request-Channel. When sending a multi-element Publisher, you can declare the element type to avoid inferring the data type for each element:

~~~java
Flux<CatalogRSocketController.StockCommand> commands = Flux.just(
        new CatalogRSocketController.StockCommand("A-101", 2),
        new CatalogRSocketController.StockCommand("B-205", -1)
);

Flux<CatalogRSocketController.StockCommand> replies =
        requester.route("catalog.stock.echo")
                .data(commands, CatalogRSocketController.StockCommand.class)
                .retrieveFlux(CatalogRSocketController.StockCommand.class);
~~~

The requester and responder examples must agree on the route, payload type, data MIME type, and corresponding codec.

## 7. RSocketStrategies, Codecs, and Metadata

RSocketStrategies groups components shared between requester and responder, including encoders, decoders, route matcher, MetadataExtractor, and ReactiveAdapterRegistry. You can configure these strategies once and reuse them on both sides.

Example registering JSON codecs from spring-web:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketStrategiesConfiguration {

    @Bean
    public RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    public RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

JSON codecs require spring-web and Jackson on the classpath. If using CBOR or Protobuf, register the corresponding encoder/decoder. By default, RSocketStrategies only has basic codecs for String, byte[], and ByteBuffer; you should not assume an arbitrary Java DTO is automatically serialized without an appropriate codec.

RSocket declares the MIME types of data and metadata in the SETUP frame. Both sides must agree on the format to decode the payload properly. Metadata can contain routes, authentication information, tracing, or other application data. RSocketMessageHandler supports composite metadata and routing metadata by default; DefaultMetadataExtractor decodes the route into the route header. To read additional metadata via @Header or @Headers, register the appropriate MIME type and decoder with MetadataExtractor.

## 8. Client-Side Responders

Annotated responders are not limited to the server. A client can also receive requests from the server and handle them with @MessageMapping or @ConnectMapping. A concise way to register one is using the static factory method:

~~~java
import io.rsocket.SocketAcceptor;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientResponder());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector ->
                connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
~~~

ClientResponder is an object with methods annotated with @MessageMapping or @ConnectMapping. When passing the object directly to the factory method, it is not required to have the @Controller stereotype. If you need handler detection by custom annotations or more complex multi-responder configurations, you can declare RSocketMessageHandler as a bean and adjust handlerPredicate.

Since Spring Framework 6.1, RSocketMessageHandler also supports @RSocketExchange. This is another option to declare an RSocket contract using an interface and use that interface on both requester and responder. @MessageMapping is more flexible when you need multiple routes or route patterns; @RSocketExchange requires a concrete route per method.

## 9. Common Errors and How to Troubleshoot

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Handler not found | Handler class is not a bean, missing @Controller in default detection mode, or route mismatch. | Check component scan, handlerPredicate, and the route formed by combining class-level prefix with method-level route. |
| Route variable not injected | Variable name in @DestinationVariable does not match the variable in the pattern, or sent route is wrong. | Compare @MessageMapping("products.{sku}") with @DestinationVariable("sku") and the actual route. |
| Unable to decode DTO | Missing decoder or incompatible data MIME type between the two ends. | Configure RSocketStrategies and codecs on both requester and responder. |
| Unable to read custom metadata | MetadataExtractor has not registered the corresponding MIME type or decoder. | Register the metadata extractor and check the extracted header name. |
| Request-Stream does not emit multiple elements | Handler returns a single object or Mono instead of Flux. | Use Flux<T> when multiple results are needed and ensure requester calls retrieveFlux(). |
| Request-Channel does not work as expected | Handler does not accept a multi-element Publisher or the two sides do not agree on data types. | Use Flux<T> on input, choose the appropriate return type, and declare the element type when sending a Publisher. |
| Connection rejected during SETUP | Server-side @ConnectMapping emits an error. | Check authentication, setup data validation, and errors in Mono<Void>. |
| Handler blocks reactive thread | Calling block() or performing blocking I/O directly inside the handler method. | Use reactive APIs; if blocking work is unavoidable, isolate it on an appropriate scheduler. |

When debugging, inspect in order: route metadata, handler signature, cardinality, MIME types, encoders/decoders, and metadata extractor. Do not rely solely on the Java method name because the actual route is the result of combining the class-level pattern, method-level pattern, and the route sent by the requester.

## 10. References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketMessageHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [MessageMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [ConnectMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [PathPatternRouteMatcher — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/util/pattern/PathPatternRouteMatcher.html)
