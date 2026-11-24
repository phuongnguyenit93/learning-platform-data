# Payload Validation, Size Limits, and Rate Limiting

STOMP opens a bidirectional communication channel over WebSocket. That also means the server must accept client-controlled data: frames may be too large, JSON may have abnormal structure, fields may have out-of-range values, or clients may send commands faster than the application can process them.

Protecting messaging requires multiple layers:

1. Limit frame size right at the WebSocket/STOMP layer to block oversized payloads before deserialization.
2. Validate DTO structure and field values after the message converter creates the Java object.
3. Check destination and data authorization against the authenticated Principal.
4. Rate-limit sends per user or session, while controlling subscription counts and processing resources.
5. Test limits, validation errors, reconnects, and behavior when clients intentionally send too fast.

No single annotation or single limit replaces these control layers. Small sizes can still contain invalid data; valid payloads can still be sent at rates that cause overload.

## 1. Distinguishing Validation Layers

| Layer | Question to Answer | Appropriate Mechanism |
|---|---|---|
| WebSocket/STOMP transport | Does the incoming frame exceed the allowed size? | Message size limit when configuring WebSocket transport |
| Message conversion | Can the payload be converted to the expected type? | MessageConverter and content type |
| DTO validation | Are fields missing, too long, or outside valid bounds? | Jakarta Bean Validation with @Valid |
| Business validation | Does the sender have permission to operate on this object? | Principal, authorization, and business data checks |
| Rate limiting | Is the client sending too many commands in a time window? | Token bucket or rate-limiting algorithm |
| Resource control | Is the client opening too many subscriptions or creating too much work? | Connection, subscription, queue, and concurrency limits |

Layers execute in a specific order. Transport limits need to act before the application parses a large payload. DTO validation runs only after the payload has been converted into an object. Business validation needs to check permissions and data state at processing time.

## 2. Limiting STOMP Message Size at Transport

Spring allows configuring the incoming message size limit on the WebSocket transport using configureWebSocketTransport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(64 * 1024);
        registration.setSendBufferSizeLimit(512 * 1024);
        registration.setSendTimeLimit(15_000);
    }
}
~~~

Meaning of the limits:

- **setMessageSizeLimit:** limits the size of an incoming STOMP message that Spring receives over the WebSocket transport. The value is usually in bytes; configure it to match the maximum size the application genuinely needs.
- **setSendBufferSizeLimit:** limits the amount of outbound data buffered when sending to a slow client.
- **setSendTimeLimit:** limits the outbound send duration before Spring considers the connection too slow.

The send buffer and send time settings protect the outbound path to clients; they do not replace the incoming message size limit.

Do not set limits too large just to avoid payload errors. A multi-megabyte frame increases memory allocation, JSON parsing, data copying, and holding messages in queues. Choose limits based on the largest valid payload plus reasonable headroom.

When a client sends a frame exceeding the limit, the transport may reject or close the connection depending on the processing path. Do not assume the controller will receive the payload to return a business error; this limit is enforced before the message reaches the controller.

## 3. Limiting Payloads at the Application Layer

Transport limits control overall frame size. The application can still apply dedicated limits per command or data type.

For example, a create-order command only needs an order ID and a small quantity. There is no reason to allow a description string hundreds of kilobytes long.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateOrder(
    @NotBlank
    @Size(max = 40)
    @Pattern(regexp = "[A-Za-z0-9_-]+")
    String orderId,

    @Min(1)
    @Max(100)
    int quantity,

    @Size(max = 200)
    String note
) {}
~~~

Meaningful constraints:

- @NotBlank requires orderId to have content after trimming whitespace.
- @Size(max = 40) limits string length.
- @Pattern restricts allowed characters per order ID rules.
- @Min and @Max bound the quantity.
- note can be null if business rules permit, but if present must not exceed 200 characters.

String length limits in Bean Validation are counted in Java characters (UTF-16 code units) of the String, not UTF-8 byte count. If storage or protocol limits are measured in bytes, also check byte size after determining encoding.

For nested collections or objects, place limits at every level:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record BatchCommand(
    @NotEmpty
    @Size(max = 50)
    List<@Valid CreateOrder> orders
) {}
~~~

@Size(max = 50) caps the number of elements in the list. @Valid requires continuing to validate each CreateOrder. If a DTO has multiple nested levels, cap string lengths, element counts, and structural depth per business requirements.

## 4. Running Bean Validation on @MessageMapping

Spring can validate the payload of `@MessageMapping` methods when the parameter is annotated with @Valid or @Validated and the application has a Bean Validation provider.

~~~java
import jakarta.validation.Valid;
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders")
    public void create(
            @Payload @Valid CreateOrder command,
            Principal principal) {

        orderService.create(principal.getName(), command);
    }
}
~~~

When a client sends to /app/orders:

1. Spring receives STOMP SEND and routes it to the handler.
2. The message converter converts the payload to CreateOrder.
3. Bean Validation checks the constraints.
4. Only when the payload is valid does the controller method process the command.
5. The service must still check permissions and business rules before writing data.

DTO validation does not prove the sender is authorized to create an order for a specific account. Obtain user identity from the authenticated Principal and check authorization at the service layer.

Validation errors can be converted into a structured error message:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.MethodArgumentNotValidException;

@Controller
public class MessagingValidationAdvice {

    @MessageExceptionHandler(MethodArgumentNotValidException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorPayload invalidPayload(MethodArgumentNotValidException ex) {
        return new ErrorPayload(
            "INVALID_PAYLOAD",
            "Invalid payload"
        );
    }

    public record ErrorPayload(String code, String message) {}
}
~~~

Messages returned to the client should contain a stable error code and displayable text. Do not send stack traces, internal class names, SQL, or sensitive details. Detailed validation info can be logged on the server with a correlation ID for investigation.

If errors must be returned for commands from anonymous sessions, check how the application routes errors to the right session. Do not use a public destination that broadcasts one person's validation error to every client.

## 5. Checking Commands and Destinations Before the Controller

A ChannelInterceptor on clientInboundChannel can inspect messages before they reach @MessageMapping. This is the right place to enforce common policies for STOMP commands, such as destination restrictions and send rate limits.

~~~java
import java.security.Principal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;

@Component
public class StompInboundGuard implements ChannelInterceptor {

    private final TokenBucketRateLimiter rateLimiter;

    public StompInboundGuard(TokenBucketRateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
            );

        if (accessor == null || accessor.getCommand() == null) {
            return message;
        }

        if (accessor.getCommand() == StompCommand.SEND) {
            String destination = accessor.getDestination();

            if (destination == null || !destination.startsWith("/app/")) {
                throw new MessageDeliveryException(
                    message,
                    "STOMP SEND destination is not allowed"
                );
            }

            Principal principal = accessor.getUser();
            String sessionId = accessor.getSessionId();

            String rateLimitKey = principal != null
                ? "user:" + principal.getName()
                : "session:" + sessionId;

            if (!rateLimiter.tryAcquire(rateLimitKey)) {
                throw new MessageDeliveryException(
                    message,
                    "STOMP send rate limit exceeded"
                );
            }
        }

        return message;
    }
}
~~~

Register the interceptor:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(stompInboundGuard);
}
~~~

The example only restricts the SEND command to the application destination /app/. Actual destinations must match the configured prefixes and the application's API contract. Do not allow clients to send SEND directly to internal broker-only destinations or administrative channels.

An interceptor does not replace authorization. Prefix checking only validates destination shape; the server still needs to verify the Principal has permission to execute that command and access the related data.

For SUBSCRIBE, there should be a separate policy: allowed destinations, maximum subscriptions per session, and data read permissions. A client might not send many SENDs yet still consume resources by creating a huge number of subscriptions.

## 6. Token Bucket for Rate Limiting Sends

Token bucket is a simple algorithm that allows a small burst while capping the average rate. The bucket has a maximum capacity; over time, tokens are refilled. Each valid command consumes one token.

Example: a bucket holds at most 20 tokens and refills 5 tokens per second. A client can send a burst of up to 20 commands when the bucket is full, after which the sustained rate is limited to roughly 5 commands per second.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class TokenBucketRateLimiter {

    private final ConcurrentMap<String, Bucket> buckets =
        new ConcurrentHashMap<>();

    private final int capacity;
    private final double refillPerSecond;

    public TokenBucketRateLimiter(
            int capacity,
            double refillPerSecond) {

        if (capacity < 1 || refillPerSecond <= 0) {
            throw new IllegalArgumentException("Invalid token bucket settings");
        }

        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
    }

    public boolean tryAcquire(String key) {
        if (key == null || key.isBlank()) {
            return false;
        }

        Bucket bucket = buckets.computeIfAbsent(
            key,
            ignored -> new Bucket(capacity, System.nanoTime())
        );

        return bucket.tryAcquire(
            capacity,
            refillPerSecond,
            System.nanoTime()
        );
    }

    private static final class Bucket {

        private double tokens;
        private long lastRefillNanos;

        private Bucket(int capacity, long now) {
            this.tokens = capacity;
            this.lastRefillNanos = now;
        }

        private synchronized boolean tryAcquire(
                int capacity,
                double refillPerSecond,
                long now) {

            long elapsed = Math.max(0, now - lastRefillNanos);
            double elapsedSeconds = elapsed / 1_000_000_000.0;

            tokens = Math.min(
                capacity,
                tokens + elapsedSeconds * refillPerSecond
            );

            lastRefillNanos = now;

            if (tokens < 1.0) {
                return false;
            }

            tokens -= 1.0;
            return true;
        }
    }
}
~~~

This is an example to illustrate the algorithm. An in-memory map grows as new users/sessions appear; a production implementation needs a cache with TTL/eviction or an expiration cleanup mechanism. If the application runs multiple instances, each node has its own map so clients could get a higher total quota than intended. When cluster-wide limits are needed, use a shared rate limiter such as Redis or limit at the API gateway.

Choose the key according to your goal:

- **Principal:** limits total rate of one user across multiple sessions.
- **Session ID:** limits each connection, useful for guest sessions.
- **Principal + destination:** separate limits per command group.
- **IP at gateway:** blocks connection or request bursts from one network source; trust only forwarded IPs set by trusted proxies.

One user can open multiple tabs. If limited only by session, they can multiply their quota by opening more sessions. Conversely, limiting only by user can cause devices of the same account to share one quota. Choose a policy that fits the product.

## 7. Checking Payload Size in an Interceptor

Transport limits are the first line of defense. You can add a byte payload check in the inbound channel to apply dedicated limits to a group of commands:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.messaging.Message;

public final class PayloadSizePolicy {

    private PayloadSizePolicy() {
    }

    public static boolean exceedsLimit(Message<?> message, int maxBytes) {
        Object payload = message.getPayload();

        if (payload instanceof byte[] bytes) {
            return bytes.length > maxBytes;
        }

        if (payload instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8).length > maxBytes;
        }

        return false;
    }
}
~~~

In the inbound STOMP pipeline, the payload is typically still `byte[]` before being converted into a DTO by the message converter. If an interceptor is placed at another stage or an internal message already carries a Java object, determine how to measure size accordingly. Do not use `String.valueOf(object)` to estimate JSON size because that string does not necessarily match the serialized payload.

This check is only a secondary layer. It does not replace `setMessageSizeLimit` because by the time the interceptor runs, the frame has already been received and decoded. For already-deserialized objects, computing size by re-serializing can waste CPU and create extra allocations.

If using dedicated limits per destination, set small thresholds for sensitive or frequently called commands, such as heartbeats, typing indicators, or status update commands. Large uploads should go through HTTP/object storage with appropriate limits and streaming, after which STOMP only emits a notification referencing the resource.

## 8. Limiting Queues, Concurrency, and Outbound Fan-Out

Rate limiting only controls how many messages arrive within a time window. A valid message can still trigger heavy queries, long computations, or broadcasts to thousands of subscribers.

Also consider:

- **Inbound executor:** cap threads and queue of clientInboundChannel so messages do not accumulate unboundedly when handlers are slow.
- **Outbound buffer:** configure send buffer and send time limits so slow-reading clients do not hold excessive memory.
- **Subscription count:** cap subscriptions per session and check subscribe permissions.
- **Fan-out:** restrict broadcasting large payloads or emitting too frequently to destinations with many subscribers.
- **Business concurrency:** cap concurrent jobs per user or command type.
- **Timeouts:** set timeouts for database and external service calls from handlers.

Example configuring the inbound executor:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration
        .taskExecutor()
        .corePoolSize(4)
        .maxPoolSize(16)
        .queueCapacity(500);
}
~~~

The numbers above are only illustrative values. Adjust according to CPU cores, handler latency, concurrent connections, and memory limits. A bounded queue exposes backpressure early; when full, the system must handle send errors or reject messages according to the chosen policy.

Do not increase queues unboundedly to mask slow handlers. Large queues can turn short overloads into prolonged latency and keep many payloads in the heap.

## 9. Protecting Against Malicious Payloads and Abnormal Data

Syntactically valid JSON payloads can still be dangerous or invalid for business logic.

- **Overly long strings:** can cause excessive memory consumption, huge logs, or exceed storage column limits.
- **Overly large collections:** can trigger large loops, queries, or fan-out.
- **Deeply nested objects:** increase parsing and validation costs; cap depth/complexity in the parser or schema as appropriate.
- **Out-of-range numbers:** negative, excessively large, or overflowing values can break logic.
- **Invalid enums:** do not use default values to mask bad data when business rules require rejection.
- **Spoofed headers:** client-sent custom headers are not proof of authentication.
- **Unsafe polymorphic JSON:** avoid enabling broad default typing on untrusted data; use strongly typed DTOs and safe Jackson configuration.
- **Encoding issues:** check content type and charset; do not assume all text payloads are UTF-8 if the protocol allows others.

Validation needs both syntactic limits and business limits. For example, quantity must be positive and within order limits; orderId must belong to the scope the Principal is allowed to operate on. Checking only @NotBlank is not enough to protect resources.

## 10. Returning Errors to Clients

An error can be detected before the controller (transport/interceptor), during message conversion, in Bean Validation, or in a business service. Not every error can return the same response DTO.

Business errors at the controller layer can be standardized with @MessageExceptionHandler:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class MessagingErrorHandler {

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidCommand(IllegalArgumentException ex) {
        return new ErrorPayload(
            "INVALID_COMMAND",
            "Invalid command"
        );
    }

    public record ErrorPayload(String code, String message) {}
}
~~~

For payload validation, specific validation exceptions can be handled and mapped to stable error codes. For rate limits, distinguish a `RATE_LIMITED` code and optionally provide a retry-after time if the application computes one. Do not send internal details or stack traces to clients.

Transport errors such as oversized frames can cause the connection to be closed before the controller runs. In that case, the client must handle transport error/close events and show an appropriate status; it should not assume a business error message is guaranteed to arrive.

## 11. Measurement and Operations

Separate metrics should be tracked for each layer:

- Number of frames/messages rejected due to size limits.
- Bean Validation errors by command type and constraint.
- Commands rejected by the rate limiter.
- Active WebSocket/STOMP connections and reconnect counts.
- Subscriptions per session.
- Inbound/outbound queue depths and handler processing times.
- Message conversion errors, broker errors, and transport errors.
- Client message receipt rate and business ACKs if implemented by the application.

Attach a correlation ID or event ID to logs to link steps. Do not use client-supplied values as unbounded-cardinality metric labels; for example, do not create per-session-ID or per-user-ID metrics. Use bounded labels such as command type, destination group, and error code.

Rate limiting must produce clear operational signals. If messages are silently dropped, clients may think commands were processed. Agree on an error response or status that clients can observe.

## 12. Testing the Limits

Tests should verify both valid cases and rejected cases:

1. Send a valid JSON payload and verify the handler receives the right DTO.
2. Send a string exceeding @Size and verify validation rejects it before the service writes data.
3. Send a negative quantity or one exceeding @Max and verify the error code.
4. Send a frame exceeding setMessageSizeLimit and verify the transport rejects/closes the connection per configured behavior.
5. Send multiple commands in a burst to verify the token bucket permits bursts up to capacity.
6. Keep sending when the bucket is depleted and verify commands are rate-limited.
7. Open multiple sessions for the same Principal to verify per-user or per-session quotas match policy.
8. Send to a destination outside /app and verify the interceptor rejects it.
9. Open many subscriptions and verify the subscription limit works.
10. Use a slow-reading client to test send buffer and send time limits.
11. Run two instances to verify shared rate limiting if cluster-wide enforcement is required.
12. Verify reconnect does not re-execute already-processed commands if no idempotency key is present.

Do not use fixed `Thread.sleep` to verify timing. Use latches/futures with timeouts and assert concrete state. For the rate limiter, you can test the algorithm directly with a fake clock for deterministic results instead of relying on wall-clock time.

## 13. STOMP Endpoint Protection Checklist

- Does the transport have an appropriate incoming STOMP message size limit?
- Do send buffer and send time limits protect against slow outbound clients?
- Do DTOs cap string lengths, element counts, and value ranges?
- Does the message converter use explicit payload types and avoid dangerous polymorphic configurations?
- Do controllers/services verify Principal authentication and authorization on business objects?
- Does the interceptor validate destinations, commands, and rate limits?
- Are subscription counts, queues, and concurrency capped?
- Does the rate limiter have eviction and use a shared store if running across multiple nodes?
- Are validation, rate limit, and transport errors properly observable?
- Do metrics/logs include correlation IDs without exposing tokens or creating unbounded cardinality?

Protecting STOMP requires control from frame to business logic. Size limits reduce large-payload risk; Bean Validation checks structure and values; authorization protects data; rate limiting and resource limits help the server maintain availability when clients send too fast.