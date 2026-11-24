# Payload Validation, Size Limits, and Rate Limiting

STOMP opens a bidirectional communication channel over WebSocket. That also means the server must accept client-controlled data: frames can be oversized, JSON can have unexpected structures, fields can have out-of-range values, or a client can send commands faster than the application can process them.

Messaging protection requires multiple layers:

1. Limit frame size right at the WebSocket/STOMP layer to block oversized payloads before deserialization.
2. Validate DTO structure and field values after the message converter builds Java objects.
3. Verify destination and data access permissions against the authenticated Principal.
4. Rate-limit sending per user or session while controlling subscription counts and processing resources.
5. Test limits, validation failures, reconnection, and behavior when clients deliberately send too fast.

No single annotation or single limit can replace these layers of control. A small payload can still contain invalid data; a valid payload can still be sent at a rate that causes overload.

## 1. Distinguishing the validation layers

| Layer | Question to answer | Appropriate mechanism |
|---|---|---|
| WebSocket/STOMP transport | Does the inbound frame exceed the allowed size? | Message size limits in WebSocket transport configuration |
| Message conversion | Can the payload be converted to the expected data type? | MessageConverter and content type |
| DTO validation | Are fields missing, too long, or out of valid range? | Jakarta Bean Validation with @Valid |
| Business validation | Is the sender permitted to act on this object? | Principal, authorization, and business data checks |
| Rate limiting | Is the client sending too many commands within a time window? | Token bucket or rate-limiting algorithm |
| Resource control | Is the client opening too many subscriptions or creating too much work? | Connection, subscription, queue, and concurrency limits |

The layers execute in different orders. Transport limits must operate before the application parses a large payload. DTO validation runs only after the payload has been converted into an object. Business validation must check permissions and data state at processing time.

## 2. Limiting STOMP message size at the transport layer

Spring lets you configure inbound message size limits in the WebSocket transport using configureWebSocketTransport:

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

- **setMessageSizeLimit:** limits the size of a single inbound STOMP message received by Spring over the WebSocket transport. The value is typically in bytes; configure it to match the maximum size the application genuinely needs.
- **setSendBufferSizeLimit:** limits the amount of outbound data buffered when sending to a slow client.
- **setSendTimeLimit:** limits the outbound send duration before Spring considers the connection too slow.

The send buffer and send time settings protect the outbound path to clients; they do not replace inbound message size limits.

Do not set limits unnecessarily high just to avoid payload errors. A multi-megabyte frame increases memory allocation, JSON parsing cost, data copying, and queue retention. Choose a limit based on the largest valid payload plus a reasonable margin.

When a client sends a frame exceeding the limit, the transport may reject it or close the connection depending on the processing path. Do not assume the controller will receive the payload to return a business error; this limit is enforced before the message reaches the controller.

## 3. Limiting payloads at the application layer

Transport limits control overall frame size. The application can still enforce specific limits per command or data type.

For example, an order creation command only needs an order code and a small quantity. There is no reason to allow a description string hundreds of kilobytes long.

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

Meaning of the constraints:

- @NotBlank requires orderId to have content after trimming whitespace.
- @Size(max = 40) limits string length.
- @Pattern restricts allowed characters according to the order ID rule.
- @Min and @Max bound the quantity.
- note may be null if business rules permit, but if present it must not exceed 200 characters.

String length limits in Bean Validation are measured in Java characters (UTF-16 code units) of the String, not UTF-8 byte count. If storage or protocol limits are measured in bytes, also check byte length after fixing the encoding.

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

@Size(max = 50) limits the number of elements in the list. @Valid requires continuing validation on each CreateOrder. If a DTO has multiple levels of nesting, limit string lengths, element counts, and structural depth per business requirements.

## 4. Running Bean Validation on @MessageMapping

Spring can validate @MessageMapping method payloads when the parameter is annotated with @Valid or @Validated and the application has a Bean Validation provider.

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

When the client sends to /app/orders:

1. Spring receives STOMP SEND and routes it to the handler.
2. The message converter converts the payload into CreateOrder.
3. Bean Validation checks the constraints.
4. Only when the payload is valid does the controller method process the command.
5. The service must still check permissions and business rules before persisting data.

DTO validation does not prove the sender has permission to create an order for a specific account. Take the user identity from the authenticated Principal and check permissions in the service layer.

You can convert validation errors into a structured error message:

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
            "Submitted payload is invalid"
        );
    }

    public record ErrorPayload(String code, String message) {}
}
~~~

The response returned to the client should contain a stable error code and displayable text. Do not return stack traces, internal class names, SQL, or sensitive information. Detailed validation failures can be logged on the server with a correlation ID for investigation.

If you need to return errors for commands from anonymous sessions, verify how the application routes errors to the right session. Do not use a public destination that broadcasts one user's validation errors to all clients.

## 5. Checking commands and destinations before the controller

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

Registering the interceptor:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(stompInboundGuard);
}
~~~

The example limits SEND commands to the application destination /app/. Actual destinations must match the prefix configuration and API contract of the application. Do not allow clients to send SEND directly to internal destinations reserved for the broker or administrative channels.

An interceptor does not replace authorization. Prefix checking only validates destination shape; the server still needs to determine whether the Principal is permitted to execute that command and access the related data.

For SUBSCRIBE, there should be a separate policy: allowed destinations, maximum subscriptions per session, and data read permissions. A client might not send many SEND frames yet still exhaust resources by creating excessive subscriptions.

## 6. Token bucket for rate-limiting sends

A token bucket is a simple algorithm that permits small bursts while limiting the average rate. The bucket has a maximum capacity; over time, tokens are refilled. Each valid command consumes one token.

For example: a bucket holds at most 20 tokens and refills at 5 tokens per second. A client can send a burst of up to 20 commands when the bucket is full, after which the sustained rate is limited to roughly 5 commands per second.

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

This example illustrates the algorithm. An in-memory map grows as new users/sessions appear; a production implementation needs a cache with TTL/eviction or an expiration cleanup mechanism for idle buckets. If the application runs multiple instances, each node has its own map, allowing a client to obtain a larger total quota than intended. When cluster-wide limits are needed, use a shared rate limiter such as Redis or enforce limits at the API gateway.

Choose keys based on your goal:

- **Principal:** limits the total rate of one user across multiple sessions.
- **Session ID:** limits per connection, useful for guest sessions.
- **Principal + destination:** applies separate limits per command group.
- **IP at gateway:** blocks connection bursts or requests from one network source; trust forwarded IPs only when set by a trusted proxy.

A user can open multiple tabs. Limiting solely by session lets them multiply their quota by opening additional sessions. Conversely, limiting solely by user can make devices sharing an account compete for one quota. Choose the policy that fits the product.

## 7. Checking payload size inside an interceptor

Transport limits are the first line of defense. You can add a byte-size check on the inbound channel to enforce tighter limits for specific command groups:

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

In the inbound STOMP pipeline, the payload is normally still a byte[] before the message converter turns it into a DTO. If the interceptor is placed at another stage or an internal message already carries a Java object, you must decide how to compute size accordingly. Never use String.valueOf(object) to estimate JSON size because that string does not necessarily match the serialized payload.

This check is only an auxiliary layer. It does not replace setMessageSizeLimit because by the time the interceptor runs, the frame has already been received and decoded. For already-deserialized objects, re-serializing to measure size can burn CPU and create extra allocations.

When using per-destination limits, set small thresholds for sensitive or frequently invoked commands such as heartbeats, typing indicators, or status updates. Large uploads should go through HTTP/object storage with appropriate limits and streaming, and STOMP should only broadcast notifications referencing the resource.

## 8. Limiting queues, concurrency, and outbound fan-out

Rate limiting only controls the number of incoming messages over a time interval. A single valid message can still trigger a heavy query, long computation, or broadcast to thousands of subscribers.

Also review:

- **Inbound executor:** bound threads and queue capacity on clientInboundChannel so messages do not accumulate indefinitely when handlers are slow.
- **Outbound buffer:** configure send buffer and send time limits so slow-reading clients do not hold excessive data in memory.
- **Subscription count:** limit subscriptions per session and enforce subscribe permissions.
- **Fan-out:** restrict broadcasting large payloads or sending too frequently to destinations with many subscribers.
- **Business concurrency:** limit concurrent work per user or per command type.
- **Timeouts:** set timeouts for database and external service calls triggered from handlers.

Example inbound executor configuration:

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

These numbers are illustrative values only. Tune them based on CPU cores, handler latency, concurrent connections, and memory limits. A bounded queue lets backpressure surface early; when full, the system must handle send failures or reject messages per the chosen policy.

Never make queues unbounded to mask slow handlers. Large queues can turn brief overload into prolonged latency and keep large numbers of payloads on the heap.

## 9. Protecting against malicious payloads and anomalous data

Syntactically valid JSON payloads can still be dangerous or invalid for business logic.

- **Excessively long strings:** can cause high memory usage, huge logs, or exceed storage column limits.
- **Oversized collections:** can trigger large loops, queries, or massive fan-out.
- **Deeply nested objects:** increase parsing and validation cost; restrict depth/complexity in the parser or schema appropriately.
- **Out-of-range numbers:** negative, huge, or overflowing values can corrupt logic.
- **Invalid enums:** do not fall back to default values to mask bad data when business logic requires rejection.
- **Spoofed headers:** client-sent custom headers are not authentication proof.
- **Unsafe polymorphic JSON:** avoid enabling broad default typing for untrusted data; use explicitly typed DTOs and safe Jackson settings.
- **Encoding errors:** check content type and charset, and do not assume every text payload is UTF-8 if the protocol permits otherwise.

Validation must include both syntactic limits and business limits. For example, quantity must be positive and within order caps; orderId must belong to the scope the Principal is allowed to act upon. Checking @NotBlank alone is insufficient to protect resources.

## 10. Returning errors to clients

An error can be detected before the controller (transport/interceptor), during message conversion, during Bean Validation, or inside a business service. Not every error can return the same response DTO.

You can standardize business errors at the controller layer with @MessageExceptionHandler:

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

For payload validation, handle the specific validation exception and map it to a stable error code. For rate limits, distinguish a RATE_LIMITED code and optionally provide a retry-after time if the application computes one. Never send internal details or stack traces to clients.

Transport errors such as oversized frames can close the connection before the controller runs. In that case, the client must handle transport error/close events and display an appropriate status; it should not expect a business error message to always arrive.

## 11. Instrumentation and operations

Track separate metrics for each layer:

- Number of frames/messages rejected for exceeding size limits.
- Number of Bean Validation errors by command type and constraint.
- Number of commands rejected by the rate limiter.
- Number of active WebSocket/STOMP connections and reconnection counts.
- Number of subscriptions per session.
- Inbound/outbound queue depths and handler execution durations.
- Number of message conversion errors, broker errors, and transport errors.
- Client message delivery rate and business ACK rate if implemented by the application.

Attach a correlation ID or event ID to logs to link steps together. Never use client-supplied values as unbounded-cardinality metric labels; for example, do not create per-session-ID or per-user-ID metric series. Use bounded labels such as command type, destination group, and error code.

Rate limiting must emit clear operational signals. Silently dropping messages can make clients believe commands succeeded. Standardize observable error responses or states for clients.

## 12. Testing limits

Tests should verify both valid cases and rejected cases:

1. Send a valid JSON payload and verify the handler receives the expected DTO.
2. Send a string exceeding @Size and verify validation rejects it before the service writes data.
3. Send a negative quantity or one exceeding @Max and verify the error code.
4. Send a frame exceeding setMessageSizeLimit and verify the transport rejects/closes the connection per configured behavior.
5. Send multiple commands in a burst to verify the token bucket permits bursts up to capacity.
6. Continue sending once the bucket is exhausted and verify commands are rate-limited.
7. Open multiple sessions for the same Principal to verify per-user or per-session quotas match policy.
8. Send to a destination outside /app and verify the interceptor rejects it.
9. Open many subscriptions and verify the subscription cap takes effect.
10. Use a slow-reading client to test send buffer and send time limits.
11. Run two instances to verify shared rate limiting when cluster-wide enforcement is required.
12. Verify reconnecting does not replay already-processed commands unless idempotency keys are used.

Do not use fixed Thread.sleep calls to verify timing. Use latches/futures with timeouts and assert explicit states. For the rate limiter, test the algorithm directly with a fake clock so results are deterministic rather than depending on wall-clock time.

## 13. STOMP endpoint protection checklist

- Does the transport enforce an appropriate inbound STOMP message size limit?
- Do send buffer and send time limits protect against slow outbound clients?
- Do DTOs bound string lengths, collection sizes, and value ranges?
- Does the message converter use explicit payload types without dangerous polymorphic settings?
- Do controllers/services verify the Principal and permissions on business objects?
- Does the interceptor validate destinations, commands, and rate limits?
- Are subscription counts, queues, and concurrency bounded?
- Does the rate limiter include eviction and use shared storage when running across multiple nodes?
- Are validation, rate-limit, and transport errors properly observable?
- Do metrics/logs carry correlation IDs without leaking tokens or creating unbounded cardinality?

Protecting STOMP requires control from frame to business logic. Size limits reduce risks from oversized payloads; Bean Validation checks structure and values; authorization protects data; rate limiting and resource caps keep the server responsive when clients send too fast.