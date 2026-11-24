# @MessageMapping, @SendTo, @SendToUser, and SimpMessagingTemplate in Spring WebSocket/STOMP

## 1. Role of Each Component

STOMP over WebSocket enables browsers and servers to exchange messages over a single WebSocket connection. In Spring Framework, four components commonly work together:

- `@MessageMapping`: maps a STOMP message to a Spring `@Controller` method by destination; similar in concept to HTTP routing, but for messaging.
- `@SendTo`: takes the **return value** from a message handler, converts it into a message, and sends it to a broker-managed destination; typically a topic for multiple subscribers.
- `@SendToUser`: takes the **return value** and sends it to the logical user destination of the user/session that sent the request; includes an option to target only the originating session.
- `SimpMessagingTemplate`: proactively sends messages from a service, scheduler, listener, HTTP controller, or any Spring bean, independent of handling an inbound STOMP message.

They solve different problems: **receiving commands**, **broadcasting shared results**, **private replies**, and **proactive publishing**.

Business examples:

- Chat: a client sends a message, and everyone in the room receives the update.
- Pricing form: only the tab that submitted the request receives its own result.
- Orders: after an admin changes status via HTTP, the server pushes a notification to subscribed clients.
- Personal notifications: a service sends to the WebSocket sessions of an authenticated user.

Do not confuse STOMP destinations with HTTP URLs. `SEND /app/chat` is a STOMP frame; `POST /app/chat` is an HTTP request and does not automatically trigger `@MessageMapping("/chat")`.

## 2. STOMP Configuration and Message Path

A basic configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Meaning of the prefixes:

| Destination | Who handles it? | Purpose |
| --- | --- | --- |
| `/ws` | HTTP/WebSocket handshake handler | Client opens the WebSocket connection and negotiates STOMP. |
| `/app/chat` | Application controller | STOMP `SEND` is routed to `@MessageMapping("/chat")`. |
| `/topic/chat` | Message broker | Client `SUBSCRIBE`; receives messages broadcast to the topic. |
| `/queue/updates` | Message broker | Broker destination; the name `queue` does not automatically guarantee durability. |
| `/user/queue/replies` | `UserDestinationMessageHandler` | Client subscribes to a user/session-scoped private destination. |

`/app` is normally stripped before matching `@MessageMapping`; meanwhile `/topic` and `/queue` route messages to the broker. `/user` is a prefix for Spring to **transform user destinations** into session-qualified internal destinations; do not add `/user` to `enableSimpleBroker` alongside `/topic`/`/queue`.

Broadcast flow:

~~~text
Browser A                         Spring application                  Browser B
    |                                     |                               |
    | -- SUBSCRIBE /topic/chat ---------> | broker stores subscription    |
    |                                     | <--- SUBSCRIBE /topic/chat -- |
    | -- SEND /app/chat ----------------> |                               |
    |                          clientInboundChannel                       |
    |                             @MessageMapping("/chat")                |
    |                                @SendTo("/topic/chat")               |
    |                          brokerChannel -> simple broker             |
    | <--- MESSAGE /topic/chat ---------- | -------- MESSAGE -----------> |
~~~

Key channels: `clientInboundChannel` receives STOMP frames, `brokerChannel` passes messages from application code to the broker, and `clientOutboundChannel` distributes them out to WebSocket sessions. A message delivered to the broker does not automatically mean every user has read or acknowledged it.

The **simple broker** suits demos and small single-JVM deployments. When cross-instance communication, durable delivery, or an external broker is required, additional architecture is needed—see the final section.

## 3. @MessageMapping: Mapping Destinations and Reading Payloads

Example:

~~~java
@Controller
class ChatController {
    @MessageMapping("/chat")
    public void accept(ChatInput input) {
        // Receive STOMP SEND /app/chat and process input.
    }
}
~~~

STOMP client sends:

~~~text
SEND
destination:/app/chat
content-type:application/json

{"text":"hello"}^@
~~~

`^@` in the illustration represents the NUL byte terminating a STOMP frame. STOMP client libraries handle protocol framing automatically; you do not append those characters to JSON manually.

Messaging `@Controller` methods support several useful parameters:

- `ChatInput input` or `@Payload ChatInput input`: deserializes the body using an appropriate `MessageConverter`, typically JSON; `@Payload` can be inferred.
- `@DestinationVariable String roomId`: extracts variables from a destination template, e.g. `@MessageMapping("/rooms/{roomId}/post")`.
- `@Header("simpSessionId") String id`, `MessageHeaders`, `StompHeaderAccessor`: accesses headers/session metadata when present.
- `Principal principal`: identity bound to an authenticated WebSocket handshake; may be `null` for anonymous connections.
- `@Valid Request request`: triggers Bean Validation if supporting dependencies/config exist, such as `spring-boot-starter-validation` in Spring Boot.

Dynamic room example:

~~~java
@MessageMapping("/rooms/{roomId}/post")
public void post(@DestinationVariable String roomId,
                 ChatInput message,
                 Principal principal) {
    // Verify principal is authorized to join roomId.
    // Only then call the service and publish to the corresponding room.
}
~~~

Client sends `SEND /app/rooms/42/post`. The destination template maps path variables; **a client-supplied roomId does not prove authorization**. The server must still validate membership, tenant, and permissions.

`@MessageMapping` can also be placed at the class level to share a prefix. STOMP handler annotations do not replace `@GetMapping`/`@PostMapping` for REST.

## 4. @SendTo: Broadcasting Results to Destination Subscribers

If a `@MessageMapping` method returns an object, `@SendTo` specifies where Spring routes that object as a message:

~~~java
@Controller
class ChatHandler {
    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatEvent handle(ChatInput input) {
        return new ChatEvent("message", input.text());
    }
}
~~~

Suppose both browsers A and B subscribe to `/topic/chat`. A sends `SEND /app/chat` with body `{"text":"hi"}`. The server invokes the method, converts the `ChatEvent` return value, and sends it to `/topic/chat`; the broker delivers it to subscribers, including A if A is subscribed. **@SendTo does not send exclusively to the request sender by default.**

You can send to multiple destinations:

~~~java
@MessageMapping("/metrics")
@SendTo({"/topic/metrics", "/topic/dashboard"})
public MetricUpdated publish(MetricRequest request) {
    return new MetricUpdated(request.name(), request.value());
}
~~~

Do this only when both subscriber groups genuinely need the same data; with sensitive data, broadcasting to the wrong destination leaks information.

### What if @SendTo is omitted?

In common configurations, Spring infers a default return destination for `@MessageMapping("/hello")` as `/topic/hello`. Nevertheless, declare `@SendTo` when you want an explicit outbound contract, especially when inbound is `/app/order/submit` while outbound is `/topic/orders`.

This annotation publishes the **return value**. For `void` methods, there is no object for Spring to publish automatically. To send proactively inside a `void` method, use `SimpMessagingTemplate`.

## 5. @SendToUser: Replying by User or Exact Session

`@SendToUser` is used when a response should not be broadcast to all subscribers of a public topic:

~~~java
@MessageMapping("/quote")
@SendToUser("/queue/quotes")
public QuoteResult quote(QuoteRequest input, Principal principal) {
    return quotationService.calculate(input, principal);
}
~~~

Clients subscribe to **`/user/queue/quotes`**, while the annotation declares `/queue/quotes`. Spring resolves the `/user` prefix per user/session automatically; do not write `@SendToUser("/user/queue/quotes")` when using the configuration conventions in section 2.

### broadcast=true vs. broadcast=false

If an authenticated user has multiple open tabs:

| Usage | Scope |
| --- | --- |
| `@SendToUser("/queue/quotes")` | Default `broadcast=true`: sends to all subscribed sessions of that same user. |
| `@SendToUser(value="/queue/replies", broadcast=false)` | Only the session that sent the STOMP message being handled. |
| `@SendToUser(value="/queue/errors", broadcast=false)` on an error handler | Sends errors only to the tab that caused the error, without notifying other tabs. |

Request–reply example targeting the originating tab:

~~~java
@MessageMapping("/calculate")
@SendToUser(value = "/queue/replies", broadcast = false)
public CalculationResult calculate(CalculationCommand command) {
    return calculator.execute(command);
}
~~~

The client sends `SEND /app/calculate` after subscribing to `/user/queue/replies`. If user `alice` has tabs A and B connected, and A sends the command, only A receives this method's reply.

**Anonymous sessions:** Spring can still support user destinations in sessions without an authenticated principal. In that case `@SendToUser` behaves like `broadcast=false`, targeting only the session that sent the message; it cannot locate "other tabs of the same user" when the user is unidentified.

### What does Spring do with /user?

~~~text
Alice, session S1: SUBSCRIBE /user/queue/inbox
    -> Spring resolves to a unique internal destination for S1

Alice, session S2: SUBSCRIBE /user/queue/inbox
    -> separate internal destination for S2

Bob, session S3: SUBSCRIBE /user/queue/inbox
    -> separate internal destination for S3

Server proactively sends to username "alice":
    -> Spring can resolve to S1 and S2 if connected/subscribed.
~~~

Internal destination formatting is managed by Spring; never depend on specific session suffixes in business code. User destinations are a **routing convenience** and do not natively provide authentication, access control, offline message storage, or transport-independent encryption.

### Combining @MessageExceptionHandler with @SendToUser

~~~java
@MessageExceptionHandler(IllegalArgumentException.class)
@SendToUser(value = "/queue/errors", broadcast = false)
public ErrorEvent invalidCommand(IllegalArgumentException ex) {
    return new ErrorEvent("INVALID_COMMAND", ex.getMessage());
}
~~~

Spring Messaging invokes `@MessageExceptionHandler` when a STOMP controller throws a matching exception. Clients subscribe to `/user/queue/errors` to receive the response. This is a messaging controller mechanism, distinct from HTTP `@ExceptionHandler`. Avoid returning stack traces or sensitive system details in error payloads.

## 6. SimpMessagingTemplate: Proactive Publishing from Services and HTTP

`SimpMessagingTemplate` allows any Spring bean to push messages into the broker system without an inbound STOMP frame.

### Public broadcast

~~~java
@Service
class StatusPublisher {
    private final SimpMessagingTemplate template;

    StatusPublisher(SimpMessagingTemplate template) {
        this.template = template;
    }

    public void publish(StatusChanged event) {
        template.convertAndSend("/topic/status", event);
    }
}
~~~

`convertAndSend` uses the configured message converter to build the payload and dispatches it to the messaging channel. It does not guarantee the message is already rendered in the UI or durably stored when the method returns.

An HTTP endpoint can also emit events:

~~~java
@RestController
class UpdateApi {
    private final SimpMessagingTemplate template;

    UpdateApi(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/api/announce")
    ResponseEntity<Void> announce(@RequestBody Announcement request) {
        template.convertAndSend("/topic/announcements", request);
        return ResponseEntity.accepted().build();
    }
}
~~~

`HTTP 202` is the HTTP processing result, not confirmation that every WebSocket client received the message. When business logic requires reliable auditing, ACKs, or retries, design an additional mechanism.

### Sending to one user from the backend

~~~java
@Service
class InboxService {
    private final SimpMessagingTemplate template;

    InboxService(SimpMessagingTemplate template) {
        this.template = template;
    }

    public void notifyAuthenticatedUser(
            String authenticatedUsername, InboxEvent event) {
        template.convertAndSendToUser(
                authenticatedUsername, "/queue/inbox", event);
    }
}
~~~

Authenticated user clients subscribe to `/user/queue/inbox`. `convertAndSendToUser("alice", "/queue/inbox", event)` is logically equivalent to publishing to `/user/alice/queue/inbox` under default prefixes, while providing a cleaner API that avoids string-concatenation mistakes.

**Never take `authenticatedUsername` from a client-declared STOMP payload and push private data to that user without verifying permissions.** Identity must come from `Principal` or a trusted server-side source, and you must still verify the sender's permissions for the recipient and resource.

A single user can have multiple sessions; sending by username normally targets all subscribed sessions of that user, not strictly one tab. If you must target one exact session outside a message handler, route properly using session IDs/headers and carefully verify user-destination behavior.

### After database commit

If you emit a notification before a data-saving transaction commits and the transaction rolls back, clients receive a "phantom" event. You can defer emission until after commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void onOrderChanged(OrderChanged event) {
    template.convertAndSend("/topic/orders", event);
}
~~~

The snippet above only illustrates attaching a listener to an existing transaction; you need listener beans, an event publisher, and transaction infrastructure. Publishing after commit **does not guarantee durable delivery** if the process crashes after commit but before sending; high-reliability systems should consider a transactional outbox or event log.

## 7. Comparing APIs and Choosing the Right Approach

| Goal | Choice | Notes |
| --- | --- | --- |
| Receive `SEND /app/...` | `@MessageMapping` | Handler receives and processes input; does not broadcast unless returning a value or sending explicitly. |
| Return value to everyone subscribed to a topic | `@SendTo("/topic/...")` | Anyone permitted to subscribe can receive it. |
| Return value to sender's sessions | `@SendToUser("/queue/...")` | Based on authenticated user; broadcasts across that user's sessions by default. |
| Return value to exact originating session | `@SendToUser(value="/queue/...",broadcast=false)` | Useful for tab-specific replies and errors. |
| Proactively push from business service/HTTP/scheduler | `template.convertAndSend(destination,payload)` | Does not require an inbound STOMP message. |
| Notify a user with a verified username | `template.convertAndSendToUser(username,"/queue/...",payload)` | Client subscribes to `/user/queue/...`; requires proper auth and user registry. |

Choose based on **who initiates the event** and **who must receive it**, not on JSON size or shorter annotation names.

## 8. Complete Demo with Java 17 and Spring Boot 3.x

This demo runs Spring MVC + STOMP simple broker on a single instance. Three capabilities:

1. `SEND /app/hello` → `@MessageMapping` → `@SendTo("/topic/news")`: broadcasts to all subscribed tabs.
2. `SEND /app/echo` → `@SendToUser(..., broadcast=false)`: replies only to the originating tab.
3. `POST /api/announcements` → `SimpMessagingTemplate.convertAndSend(...)`: broadcasts from an HTTP controller.

To keep the demo runnable as easily as possible, Spring Security is omitted; `@SendToUser(broadcast=false)` still works using **anonymous sessions**. An example of `convertAndSendToUser(username,...)` for authenticated users was shown separately in section 6.

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>stomp-routing</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.2. src/main/java/demo/StompRoutingApplication.java

All of the following Java code lives in **one file**. Only the main class is `public`; the other package-private classes/records are valid in Java 17.

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class StompRoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompRoutingApplication.class, args);
    }
}

record Input(String text) {}
record Event(String type, String text) {}

@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}

@Controller
class CommandController {
    @MessageMapping("/hello")
    @SendTo("/topic/news")
    Event hello(Input input) {
        return new Event("hello", checked(input));
    }

    @MessageMapping("/echo")
    @SendToUser(value = "/queue/replies", broadcast = false)
    Event echo(Input input) {
        return new Event("reply", "Echo: " + checked(input));
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    Event invalid(IllegalArgumentException error) {
        return new Event("error", error.getMessage());
    }

    static String checked(Input input) {
        if (input == null || input.text() == null
                || input.text().isBlank() || input.text().length() > 500) {
            throw new IllegalArgumentException(
                    "text must contain 1..500 characters");
        }
        return input.text().trim();
    }
}

@RestController
class AnnouncementController {
    private final SimpMessagingTemplate template;

    AnnouncementController(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/api/announcements")
    ResponseEntity<Void> announce(@RequestBody Input input) {
        if (input == null || input.text() == null
                || input.text().isBlank() || input.text().length() > 500) {
            return ResponseEntity.badRequest().build();
        }

        template.convertAndSend("/topic/news",
                new Event("announcement", input.text().trim()));
        return ResponseEntity.accepted().build();
    }
}
~~~

In the demo:

- `@SendTo("/topic/news")` broadcasts the return value, even though the method does not touch the template directly.
- `@SendToUser(... broadcast=false)` replies only to the session that sent the `/app/echo` command.
- `@MessageExceptionHandler` sends private errors to `/user/queue/errors` when the handler throws `IllegalArgumentException`.
- `@PostMapping` is an HTTP endpoint calling the template to broadcast a message without an inbound STOMP command.
- `Event` is a Java record; Jackson serializes it to JSON via converters provided by Spring Boot.
- `ResponseEntity.accepted()` on HTTP confirms only that the server accepted the publish request, not that browsers have received it.

### 8.3. src/main/resources/static/index.html

The following HTML uses the UMD build of `@stomp/stompjs`. The browser needs Internet access to fetch the CDN script; alternatively, install via npm and serve a local bundle for offline usage.

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <title>Spring STOMP demo</title>
</head>
<body>
    <h1>STOMP demo</h1>
    <input id="text" value="Hello">
    <button id="hello">Broadcast</button>
    <button id="echo">Reply to this tab</button>
    <button id="announce">Publish from HTTP</button>
    <pre id="log"></pre>

    <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.2.0/bundles/stomp.umd.min.js"></script>
    <script>
        const input = document.getElementById("text");
        const logPanel = document.getElementById("log");
        const log = value => {
            logPanel.textContent += value + "\n";
        };

        const protocol = location.protocol === "https:" ? "wss://" : "ws://";
        const client = new StompJs.Client({
            brokerURL: protocol + location.host + "/ws",
            reconnectDelay: 3000,
            onConnect: () => {
                log("CONNECTED");
                client.subscribe("/topic/news", message => {
                    log("TOPIC: " + message.body);
                });
                client.subscribe("/user/queue/replies", message => {
                    log("REPLY: " + message.body);
                });
                client.subscribe("/user/queue/errors", message => {
                    log("ERROR: " + message.body);
                });
            },
            onStompError: frame => {
                log("STOMP ERROR: " + (frame.headers.message || "unknown"));
            }
        });
        client.activate();

        function send(destination) {
            if (!client.connected) {
                log("STOMP not connected yet");
                return;
            }
            client.publish({
                destination: destination,
                body: JSON.stringify({ text: input.value })
            });
        }

        document.getElementById("hello").onclick = () => {
            send("/app/hello");
        };
        document.getElementById("echo").onclick = () => {
            send("/app/echo");
        };
        document.getElementById("announce").onclick = async () => {
            try {
                const response = await fetch("/api/announcements", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: input.value })
                });
                log("HTTP status: " + response.status);
            } catch (error) {
                log("HTTP request failed: " + error);
            }
        };

        // When leaving the screen: await client.deactivate();
    </script>
</body>
</html>
~~~

The code registers all subscriptions inside `onConnect`: when the STOMP client reconnects, the callback runs again and subscribes on the new connection. Using `textContent` prevents rendering untrusted content as HTML.

### 8.4. Running and Results

Using JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/`, wait for status `CONNECTED`, then test the buttons:

1. **Broadcast:** sends `/app/hello`, logging `TOPIC: {"type":"hello","text":"Hello"}`. Open a second subscribed tab and send again; both tabs receive the broadcast.
2. **Reply to this tab:** sends `/app/echo`, logging `REPLY: {"type":"reply","text":"Echo: Hello"}` only on the sending tab. The other tab does not receive this reply.
3. **Publish from HTTP:** the browser POSTs `/api/announcements`, receiving `HTTP status: 202`, while tabs subscribed to the topic receive a message with `"type":"announcement"`.
4. **Error:** clear the input and click **Reply to this tab**. The handler rejects empty text, and the originating session receives a message on `/user/queue/errors` when the error handler runs.

Sample JSON shows the key fields; serialized field order is not part of the transport contract.

You can also invoke the HTTP endpoint directly with a command (for terminals supporting the curl CLI):

~~~bash
curl -i -X POST http://localhost:8080/api/announcements -H "Content-Type: application/json" -d '{"text":"Update from API"}'
~~~

The HTTP response has status 202, while the broadcast message is pushed to WebSocket subscriptions. On Windows PowerShell, `curl` may be an alias; use `curl.exe` and shell-appropriate JSON quoting.

**Ordering note:** the simple broker does not retain events emitted before a subscription becomes active. Wait for STOMP connect and subscribe to take effect before testing. This example illustrates mapping and routing, not delivery/ACK guarantees or a benchmark.

## 9. Common Mistakes

### 9.1. Sending to the wrong destination

- Client does `SEND /topic/chat` and expects `@MessageMapping("/chat")` to run: wrong if the app prefix is `/app`.
- Client must `SEND /app/chat`; server uses `@SendTo("/topic/chat")`; subscribers listen on `/topic/chat`.
- For user replies, client listens on `/user/queue/replies`, server uses `@SendToUser("/queue/replies")`.

### 9.2. Using @SendTo to send private data

`@SendTo` publishes to a broker destination; if unauthorized users can subscribe to the topic, they can receive the data. Choose a user destination and enforce Spring Security message authorization / business permission checks before sending.

### 9.3. Confusing username with session

`@SendToUser(broadcast=false)` targets the session that invoked the handler; `convertAndSendToUser(username, ...)` targets the user via the registry and can fan out to multiple sessions. If exactly one tab must be targeted, identify the session explicitly.

### 9.4. Assuming naming it /queue creates a durable queue

The simple broker does not provide persistence, clustering, offline queues, replay, or exactly-once guarantees. High-reliability systems need an external broker and/or business persistence via database/outbox.

### 9.5. Assuming a successful template call means the client read it

`convertAndSend` hands off to the message channel system; it is not a browser acknowledgement. For critical workflows, assign application message IDs, track status, design retries/deduplication, and handle offline users.

### 9.6. Blocking too long inside a handler

STOMP message handlers execute via inbound channels/executors. Running unbounded heavy I/O or DB work on them can back up queues and raise latency. Measure handler latency, inbound/outbound queues, and memory; tune threading and backpressure for actual load.

### 9.7. Forgetting to re-subscribe on reconnect

A new WebSocket/STOMP session does not inherit subscriptions from the old connection. StompJS generally needs to subscribe inside `onConnect` and resync snapshots/missed events after reconnecting.

## 10. Security, Scaling, and Production

**Authentication/authorization:** Browser setups typically inherit the authenticated user from the HTTP/WebSocket handshake. Never trust STOMP `CONNECT` `login`/`passcode` headers to verify identity unless a dedicated token mechanism is configured. Enforce `SEND`/`SUBSCRIBE` permissions per destination, restrict topics, validate room/order/tenant access in the business layer, rate-limit, and validate payloads. When using Spring Security, configure message authorization and WebSocket CSRF/origin protections.

**SimpMessagingTemplate and transactions:** For database events, publish after commit or via an outbox to avoid false events if a transaction rolls back. Critical events require persisted state and retry models rather than relying solely on open sockets.

**Multiple instances:** `enableSimpleBroker` stores subscriptions inside one JVM. With replicas A and B, sending on A will not automatically reach users connected to B. Use a STOMP broker relay with a suitable broker, or a coordinated message backplane and user registry; scaling design depends on load and desired durability.

**User routing:** In multi-node systems, locating users/sessions may require user-destination broadcast or a shared user registry; define behavior clearly when a user is offline or holds multiple sessions.

**Resource limits:** Monitor active WebSocket sessions, message sizes, send queues, latency, reconnect counts, send failures, and slow clients. Heartbeats, timeouts, outbound buffer caps, backoff, and session cleanup are critical operational requirements.

## 11. Pre-Integration Checklist

- [ ] `/ws` is the handshake endpoint, `/app` is the controller prefix, `/topic`/`/queue` go to the broker, and `/user` is resolved separately by Spring.
- [ ] Clients send STOMP `SEND` via a STOMP-compatible library; do not send raw JSON to a STOMP handler.
- [ ] `@MessageMapping` has the proper destination, converter, DTO, and validation.
- [ ] `@SendTo` only broadcasts data appropriate for all subscribers of that topic.
- [ ] `@SendToUser` sets `broadcast` properly: all user sessions vs. originating session only.
- [ ] `SimpMessagingTemplate` is injected into services for notifications originating from HTTP, schedulers, or other business logic.
- [ ] Auth, per-user/room authorization, input validation, rate limiting, and safe logging are implemented.
- [ ] Strategies exist for reconnect, resubscribe, snapshot/replay if needed, offline notifications, and delivery semantics.
- [ ] Load-tested with realistic session/message counts and multi-replica topology if applicable.

**Rule of thumb:** `@MessageMapping` **receives**; `@SendTo` **broadcasts to subscribers**; `@SendToUser` **replies to user/session**; `SimpMessagingTemplate` **proactively sends from application code**. These choices define message paths; reliability, permissions, and security are the next layers to design.

## 12. Official References

- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Enable STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — Message Flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- StompJS — Browser Client & UMD Bundle: https://stomp-js.github.io/guide/stompjs/using-stompjs-v5.html
