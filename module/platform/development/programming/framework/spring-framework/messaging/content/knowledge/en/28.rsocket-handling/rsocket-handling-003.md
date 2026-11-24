# `@Controller`, `@MessageMapping`, and Route Mapping in RSocket

## Objectives

In Spring Messaging, `@Controller` marks a class containing message-handling methods; `@MessageMapping` binds a method to an RSocket message route. When a requester sends a request with a matching route, Spring locates the handler, decodes the payload, invokes the method, and encodes the return value.

This mechanism is RSocket's responder model, not HTTP URL mapping. RSocket is also symmetrical: once a connection is established, each endpoint can send requests and handle incoming requests.

## 1. How Is an RSocket Request Mapped?

An RSocket request can carry **data** and **metadata**. The route typically resides in routing metadata; the business payload resides in data. With Spring, the requester declares the route using `RSocketRequester.route(...)`, while the responder declares the route to handle using `@MessageMapping(...)`.

Typical processing flow:

1. The requester sends a request, along with a route, payload, and optional metadata.
2. `RSocketMessageHandler` extracts the route from metadata and finds a method whose `@MessageMapping` pattern matches that route.
3. Spring uses configured `Decoder`s to convert data into the Java type of the payload parameter; registered metadata is populated into headers.
4. The handler method executes and returns a value, `Mono`, `Flux`, or a void-like result.
5. Spring encodes the result into a response payload according to the corresponding RSocket interaction model.

For example, the route `radar.find.42` can be mapped to `@MessageMapping("radar.find.{id}")`. The value `42` is extracted into the route variable `id`; the payload, if present, remains the separate data part.

## 2. Roles of Annotations and Components

### `@Controller`

- Marks a Spring bean that contains message-handling methods.
- `RSocketMessageHandler` uses `@Controller` beans to detect `@MessageMapping` and `@ConnectMapping` methods.
- The class must be managed by Spring, typically through component scanning or bean declarations.
- Adding `@Controller` alone does not automatically open an RSocket port. The application also needs to configure the responder and attach it to an RSocket server or use the corresponding Spring Boot auto-configuration.

### `@MessageMapping`

- Binds a method to a route or route pattern.
- Each request with a matching route is dispatched to the corresponding method.
- The method can accept the payload, route variables, extracted metadata, or an `RSocketRequester`.
- The return value determines the number of responses and helps determine the RSocket interaction model.

### `RSocketMessageHandler`

This is the component that connects annotations to the RSocket responder. In manual Spring Framework configuration, the handler can be declared as follows:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
class RSocketHandlerConfig {

    @Bean
    RSocketMessageHandler rSocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
```

By default, `RSocketMessageHandler` uses `SimpleRouteMatcher`, which is based on `AntPathMatcher`. `PathPatternRouteMatcher` from the `spring-web` module can be used for more efficient route matching. With Spring Boot, the Spring Messaging infrastructure for RSocket and `RSocketMessageHandler` are usually auto-configured when the appropriate dependencies and server configuration are present; in that case, there is no need to redeclare the bean just to enable annotation mapping.

## 3. Route Design and Matching

An RSocket route is a hierarchical name passed through metadata. It is **not a URL path**. Default route matchers use a dot (`.`) as the separator; URL decoding rules like those used when processing HTTP URLs do not apply.

Examples of route conventions:

| Route | Meaning |
|---|---|
| `radar.find.42` | Find radar with ID `42` |
| `radar.search` | Search multiple radars by payload |
| `radar.report` | Send a radar report |
| `radar.filter` | Send a stream of filter criteria |

A route pattern with a variable:

```java
@MessageMapping("radar.find.{id}")
Mono<Radar> find(@DestinationVariable("id") String id) {
    return radarService.findById(id);
}
```

A request with route `radar.find.42` passes the string `42` into the `id` parameter. `@DestinationVariable` extracts the value from the variable part of the route pattern; it is good practice to specify the variable name explicitly in the annotation to avoid depending on parameter-name metadata at compile time.

When designing routes:

- Use structured and consistent names, such as `resource.action.identifier`.
- Standardize casing, separators, and naming conventions between requester and responder.
- Do not prepend a leading slash to routes out of HTTP URL habit.
- Do not put business data into the route if that data belongs in the payload.
- Choose specific routes to avoid multiple handlers matching the same request.
- Verify that the actual route sent by the requester matches the `@MessageMapping` pattern.

## 4. Handler Method Parameters

| Parameter | Purpose |
|---|---|
| `@Payload T` | Receives the request data after it is decoded into type `T`. The annotation can be omitted if the parameter is a non-simple payload type and does not belong to another special parameter group; writing it explicitly is usually easier to read. |
| `@Payload Mono<T>` | Receives a single payload asynchronously. |
| `@Payload Flux<T>` | Receives a stream of payloads; typically used for the input side of a Channel interaction. |
| `@DestinationVariable("id")` | Extracts a variable value from the route pattern, such as `{id}`. |
| `@Header("tenant-id")` | Retrieves a metadata value decoded and registered by `MetadataExtractor`. |
| `@Headers Map<String, Object>` | Receives extracted metadata values as a map. |
| `RSocketRequester` | Sends requests back over the current connection. RSocket allows both sides to act as requester and responder. |

Not all metadata automatically becomes a header. For custom metadata, the appropriate MIME type, `Decoder`, and `MetadataExtractor` must be configured. If no decoder or extraction key is registered, the `@Header` parameter may not receive the expected value.

## 5. Return Types and the Four Interaction Models

Spring infers the interaction model based on the **cardinality** of the input payload and output result:

- Cardinality `0`: no payload parameter on input; `void` or `Mono<Void>` on output.
- Cardinality `1`: a synchronous single value or a single-value asynchronous type such as `Mono<T>`.
- Cardinality `many`: a multi-value stream such as `Flux<T>`.

Commonly used combinations:

| Input payload | Output result | Interaction model | Usage |
|---|---|---|---|
| Single value (`T` or `Mono<T>`) | Single value (`T` or `Mono<T>`) | Request-Response | Send one request and receive one result |
| Single value | `Flux<T>` | Request-Stream | Send one request and receive a stream of results |
| Single value | `void` or `Mono<Void>` | Fire-and-Forget | Send a message without needing response data |
| `Flux<T>` | None, one, or many values | Request-Channel | Send a stream of messages and optionally receive a stream of responses |

Examples:

- `Mono<Radar>` is suitable when looking up a single radar.
- `Flux<Radar>` is suitable when a query returns multiple radars.
- `Mono<Void>` is suitable when recording an event where the application protocol does not require a data response.
- `Flux<Query>` as input indicates that the requester can send multiple queries over the same Channel request.

RSocket uses Reactive Streams for streams; backpressure allows the receiver to regulate how many elements are sent next. Avoid turning these streams into blocking operations inside handlers.

## 6. Controller Example

The following code illustrates three interaction models and a Channel. This is the controller code; to run in an application, you need an implementation of `RadarService`, Spring Messaging/Reactor dependencies, responder configuration beans, and the corresponding RSocket connection.

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record Radar(String id, String name) {}
record RadarQuery(String region) {}

interface RadarService {
    Mono<Radar> findById(String id);

    Flux<Radar> search(RadarQuery query);

    Mono<Void> report(Radar radar);

    Flux<Radar> filter(Flux<RadarQuery> queries);
}

@Controller
public class RadarController {

    private final RadarService radarService;

    public RadarController(RadarService radarService) {
        this.radarService = radarService;
    }

    // Request-Response: one route variable, one Radar returned.
    @MessageMapping("radar.find.{id}")
    public Mono<Radar> find(
            @DestinationVariable("id") String id) {
        return radarService.findById(id);
    }

    // Request-Stream: one payload, multiple Radars returned.
    @MessageMapping("radar.search")
    public Flux<Radar> search(@Payload RadarQuery query) {
        return radarService.search(query);
    }

    // Fire-and-Forget: receive payload, return no data.
    @MessageMapping("radar.report")
    public Mono<Void> report(@Payload Radar radar) {
        return radarService.report(radar);
    }

    // Request-Channel: receive a stream of queries and return a stream of Radars.
    @MessageMapping("radar.filter")
    public Flux<Radar> filter(@Payload Flux<RadarQuery> queries) {
        return radarService.filter(queries);
    }
}
```

Key observations:

- The route name is in the annotation, while the search criteria reside in `RadarQuery`.
- The `{id}` variable is converted into a Java parameter via `@DestinationVariable`.
- The return type expresses the number of responses: `Mono` is at most one element, `Flux` is a stream of elements.
- The `report` method returns `Mono<Void>`; the requester does not receive a business acknowledgment object from the handler.

## 7. Calling Routes from the Requester

Once a connection and an `RSocketRequester` exist, the requester calls the corresponding routes as follows:

```java
// Request-Response
Mono<Radar> one = requester.route("radar.find.42")
        .retrieveMono(Radar.class);

// Request-Stream
Flux<Radar> many = requester.route("radar.search")
        .data(new RadarQuery("north"))
        .retrieveFlux(Radar.class);

// Fire-and-Forget
Mono<Void> sent = requester.route("radar.report")
        .data(new Radar("42", "North radar"))
        .send();

// Request-Channel
Flux<Radar> filtered = requester.route("radar.filter")
        .data(Flux.just(
                new RadarQuery("north"),
                new RadarQuery("south")),
                RadarQuery.class)
        .retrieveFlux(Radar.class);
```

The variables above are publishers; the request is executed when the publisher is subscribed to. In a reactive application, you typically return the publisher to the next calling layer or subscribe at an appropriate boundary, rather than calling `block()` inside the processing flow.

With Fire-and-Forget, `send()` returns a `Mono<Void>` to signal that sending the message has completed. It **does not confirm that the receiving handler has finished processing**. If the business logic requires confirmation, design a route that returns a result, such as `Mono<ReportAccepted>`, and use Request-Response.

## 8. Metadata and Reverse Communication with the Requester

The payload contains business data; metadata typically contains the route or auxiliary information such as tenant, token, or tracing. Spring supports:

- `@Header` to retrieve a single decoded metadata value.
- `@Headers` to retrieve a map of extracted metadata values.
- `RSocketRequester` as a handler parameter to send requests to the connected peer.

Example combining a route variable with metadata:

```java
@MessageMapping("radar.tenant.{id}")
Mono<Radar> findForTenant(
        @DestinationVariable("id") String id,
        @Header("tenant-id") String tenantId) {
    return radarService.findByIdForTenant(id, tenantId);
}
```

This snippet only works when metadata has an appropriate MIME type and `MetadataExtractor` has been configured to produce the `tenant-id` key. Headers should not be treated as authenticated data; authentication and authorization must still be performed at the security/business layer.

## 9. Distinguishing `@MessageMapping` and `@ConnectMapping`

- `@MessageMapping` handles individual routed requests, such as `radar.find.42`.
- `@ConnectMapping` handles connection-level events: the `SETUP` frame when the connection starts and subsequent `METADATA_PUSH` notifications.

Use `@ConnectMapping` for handling tied to the connection lifecycle or connection-level metadata. Do not use it in place of routes that handle ordinary business requests.

## 10. Common Errors and How to Check

| Symptom | Possible cause | How to check |
|---|---|---|
| Handler not found | Controller is not a Spring bean or responder is not registered | Check component scanning, the `RSocketMessageHandler` bean, and attaching `handler.responder()` to the server |
| Route does not match | Wrong name, separator, casing, or route pattern | Compare the string passed to `requester.route(...)` with `@MessageMapping` |
| Route variable empty or binding error | Name in `@DestinationVariable` does not match placeholder | Compare `{id}` with `@DestinationVariable("id")` |
| Payload cannot be decoded | Missing or wrong `Decoder`, MIME type, or data type | Check `RSocketStrategies`, data MIME type, and codecs for DTOs |
| `@Header` has no value | Metadata has not been decoded/extracted | Check `MetadataExtractor`, MIME type, and key name |
| Client receives no response | Handler returns `void`/`Mono<Void>` or requester chose wrong retrieve method | Check the interaction model and return type |
| Client mistakes Fire-and-Forget for processed | `send()` only signals that sending completed | Use Request-Response if a business ACK is needed |
| Threads blocked or high resource usage | Blocking or handling `Flux` without respecting backpressure | Remove blocking calls in handlers and use appropriate Reactor operators |

When debugging, check in this order: the route sent by the requester, the route pattern in the annotation, controller registration, responder configuration, and then codecs and metadata. This approach helps separate routing errors from payload conversion errors.

## 11. Implementation Checklist

- [ ] Controller is managed by Spring and uses constructor injection for services.
- [ ] Each `@MessageMapping` has a clear, non-overlapping, unambiguous route.
- [ ] Routes on the requester match route patterns on the responder exactly.
- [ ] Placeholders in routes match `@DestinationVariable`.
- [ ] Choose `Mono`, `Flux`, or `Mono<Void>` according to the required interaction model.
- [ ] Encoders/decoders exist for the DTOs being sent and received.
- [ ] Custom metadata is registered before reading with `@Header`/`@Headers`.
- [ ] Fire-and-Forget is not used when business logic requires processing confirmation.
- [ ] Handlers do not call blocking operations on reactive threads.

## References

- [Spring Framework Reference — RSocket, Annotated Responders, and `@MessageMapping`](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/)
