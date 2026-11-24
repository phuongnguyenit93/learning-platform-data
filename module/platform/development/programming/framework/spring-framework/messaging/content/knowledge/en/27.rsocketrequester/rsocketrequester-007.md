# Receiving a Single Result with `retrieveMono`

## Objectives

When sending an RSocket request and expecting exactly one response, use `RSocketRequester` to specify the route, payload, and return data type, then call `retrieveMono`. This method executes a **Request-Response** interaction and returns a `Mono<T>` containing the decoded response.

## 1. How Does `retrieveMono` Work?

RSocket supports multiple interaction models. Request-Response sends one message and receives one message back. This is the right fit for `retrieveMono`.

A request typically looks like:

```java
Mono<User> result = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
```

Each step in the chain above has its own meaning:

1. `route("users.find")` places the route into the message metadata. The route must match the route registered by the receiver.
2. `data(userId)` supplies the outgoing payload. This value is converted by an encoder into the wire format sent over the connection.
3. `retrieveMono(User.class)` declares the expected response type and selects the Request-Response interaction. A decoder converts the response payload into a `User` object.
4. The result is a `Mono<User>`, a reactive stream of at most one value.

`retrieveMono` does not return the object immediately and does not turn the call into a synchronous operation. It creates a reactive pipeline. Only when the pipeline is subscribed to is the request executed. With a connection created via `RSocketRequester.Builder`, connection establishment is also performed transparently on the first request.

Payload is optional. If the route does not need input data, you can omit `data`:

```java
Mono<HealthStatus> status = requester
    .route("system.health")
    .retrieveMono(HealthStatus.class);
```

Route is routing metadata; payload is business data. Do not confuse the two.

## 2. Runnable Example with Spring Boot

The example below runs an RSocket server and client in the same application so Request-Response is easy to observe. The application uses TCP on port 7000 and exchanges a string.

### Dependency

Add the following starter to the `dependencies` section of the Maven project. Use a Spring Boot parent or BOM to manage versions:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
```

The starter provides Spring Boot's RSocket infrastructure and the codecs needed for payloads, including JSON/CBOR support when Jackson is present.

### Server Configuration

In `src/main/resources/application.properties`:

```properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
```

### Responder: Receiving a Request and Producing a Response

Create `GreetingResponder.java`:

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingResponder {

    @MessageMapping("greeting")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Hello " + name);
    }
}
```

`@MessageMapping("greeting")` registers a handler for the `greeting` route. The handler receives a `String` payload and returns `Mono<String>`. Spring Messaging uses the value emitted by the Mono as the response to the request.

### Requester: Calling `retrieveMono`

Create `GreetingClient.java`:

```java
package example.rsocket;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingClient {

    private final RSocketRequester requester;

    public GreetingClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    public Mono<String> greet(String name) {
        return requester
                .route("greeting")
                .data(name)
                .retrieveMono(String.class);
    }
}
```

Spring Boot auto-configures an `RSocketRequester.Builder` bean. The client uses the builder to create a requester connecting over TCP to the server. Calling `tcp` prepares the requester; the connection is used when a request occurs. The builder is a prototype bean and holds configuration state, so inject the builder at each site where a requester needs to be created rather than sharing one builder to create multiple requesters with different configurations.

### Running the Demo

Create `RSocketDemoApplication.java`:

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(GreetingClient client) {
        return args -> {
            String reply = client.greet("Lan").block(Duration.ofSeconds(5));
            System.out.println(reply);
        };
    }
}
```

Run the application with Maven:

```bash
./mvnw spring-boot:run
```

On Windows you can use:

```powershell
.mvnw.cmd spring-boot:run
```

Expected output:

```text
Hello Lan
```

In the example, `block(Duration)` is only used at the command-line demo boundary to wait for the result and bound the wait time. In a reactive application such as WebFlux, return `Mono<String>` directly to the framework or compose the Mono into an existing pipeline; do not block on the event loop.

## 3. Choosing the Response Data Type

The argument to `retrieveMono` is the type the client wants to receive after decoding:

```java
Mono<User> user = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
```

If the response type has generic type parameters, such as `ApiResponse<List<User>>`, passing only `ApiResponse.class` loses element type information due to Java type erasure. Use `ParameterizedTypeReference` to preserve full type information:

```java
import org.springframework.core.ParameterizedTypeReference;

Mono<ApiResponse<List<User>>> users = requester
    .route("users.search")
    .data(criteria)
    .retrieveMono(
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
    );
```

If you only need to wait for an operation to complete without response data, you can use `Void`:

```java
Mono<Void> completed = requester
    .route("cache.refresh")
    .data("product-cache")
    .retrieveMono(Void.class);
```

With a `Mono<Void>` response, the pipeline completes after data is consumed; it does not emit a business object to process in `doOnNext`.

The data type declared by the client must be compatible with the payload sent back by the responder. Both sides must also have matching encoders/decoders. When using Spring Framework directly, default basic codecs support `String`, `byte[]`, and `ByteBuffer`; to exchange JSON, CBOR, or other DTO formats, configure `RSocketStrategies` with the corresponding encoders and decoders. Spring Boot can auto-configure common codecs through the RSocket starter.

## 4. Handling Results Reactively

Because `retrieveMono` returns `Mono<T>`, you can combine it with Reactor operators before subscribing:

```java
import java.time.Duration;

Mono<String> response = requester
    .route("greeting")
    .data("Lan")
    .retrieveMono(String.class)
    .timeout(Duration.ofSeconds(3))
    .doOnNext(value -> System.out.println("Response: " + value))
    .doOnError(error ->
        System.err.println("RSocket request failed: " + error.getMessage())
    );
```

Points to remember:

- `doOnNext` observes the response value; it does not alter that value.
- `doOnError` observes errors such as connection errors, responder errors, or encode/decode errors. The error still propagates downstream.
- `timeout` bounds the wait duration on the application side. Choose a timeout appropriate for latency and business requirements.
- Use `onErrorResume` when there is a valid fallback; use `onErrorMap` when you need to translate the error type. Avoid turning every error into a success value because that can mask incidents.

A Mono only runs when there is a subscriber. In services, the common pattern is to return the Mono to the caller so the caller decides how to compose and consume the result:

```java
public Mono<String> greet(String name) {
    return requester.route("greeting")
            .data(name)
            .retrieveMono(String.class);
}
```

Do not call `subscribe()` inside every service method just to "trigger" the request. Doing so detaches the request from the caller's pipeline, making it harder for the caller to coordinate results, handle errors, and manage lifecycle. Only subscribe directly at an imperative boundary when the application genuinely needs to launch an independent task itself.

## 5. Distinguishing `retrieveMono`, `retrieveFlux`, and `send`

| Method | RSocket interaction | Return type | When to use |
|---|---|---|---|
| `retrieveMono(Type.class)` | Request-Response | `Mono<T>` | One request, one response |
| `retrieveFlux(Type.class)` | Request-Stream or Request-Channel depending on input cardinality | `Flux<T>` | Need to receive multiple responses or exchange a stream |
| `send()` | Fire-and-Forget | `Mono<Void>` | Only need to send a one-way message |

Do not use `retrieveMono` for a request payload that is a multi-element Publisher. RSocket has no "many-to-one" interaction model; this case will produce an error. If you need to send or receive multiple elements, choose an appropriate streaming interaction and use `retrieveFlux`.

Also distinguish `send()` from Request-Response: the Mono returned by `send()` only indicates whether sending the payload completed successfully. It does not confirm that the responder processed the business logic or produced a result.

## 6. Common Errors

1. **Route mismatch:** the client calls `route("greeting")` while the responder registers a different route. Check spelling and route configuration on both sides.
2. **No subscriber:** creating a Mono and leaving it unused means the request has not been executed. Return the Mono to the framework/caller or subscribe at an appropriate imperative boundary.
3. **Wrong response type:** the client declares `User.class` while the server returns a different data type, or a decoder for the payload format is missing. Align the contract and codec configuration.
4. **Using a multi-element Publisher with `retrieveMono`:** this combination is invalid. Choose `retrieveFlux` and an appropriate streaming model.
5. **Blocking on a reactive thread:** `block()` can stall the event loop. Only use it in command-line examples, tests, or intentional imperative boundaries.
6. **Ignoring asynchronous errors:** errors do not necessarily occur on the line creating the Mono. Place error handling in the pipeline and configure appropriate timeouts.

## 7. Implementation Checklist

- Client-side route matches the responder's route.
- Outgoing payload has the type and format expected by the responder.
- Type in `retrieveMono` matches the actual response.
- Encoders/decoders for data and metadata are registered on both sides.
- A subscriber consumes the Mono; errors and timeouts are handled at the appropriate layer.
- Use `retrieveMono` when expecting one response; use `retrieveFlux` when expecting a stream; use `send` when only sending one-way.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.RetrieveSpec — API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
