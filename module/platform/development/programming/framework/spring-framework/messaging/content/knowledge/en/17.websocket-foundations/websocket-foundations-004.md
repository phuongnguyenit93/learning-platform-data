# Distinguishing STOMP over WebSocket from Plain WebSocket

WebSocket and STOMP often appear together in realtime applications, but they belong to two different layers. **WebSocket** is a bidirectional transport protocol that keeps a connection open between the client and the server. It carries text or binary frames but does not specify the content of messages, how to route them, or a publish-subscribe mechanism. **STOMP** is a messaging protocol at the application layer that can run on top of WebSocket to standardize commands, headers, destinations, subscriptions, and acknowledgements.

Therefore, “STOMP over WebSocket” still uses a WebSocket connection. The difference is that the client and server additionally agree on a message protocol. In Spring, plain WebSocket typically uses WebSocketHandler; STOMP uses WebSocket message broker support, @MessageMapping, and the built-in broker or a broker relay.

## 1. Two Protocol Layers

### 1.1. WebSocket Is the Transport

WebSocket is standardized in RFC 6455. A connection usually starts with an HTTP handshake carrying an Upgrade header. If the server accepts, it returns status 101 Switching Protocols and keeps the TCP connection open so that the client and server can send data in both directions.

After the handshake, the two sides exchange WebSocket messages in the form of:

- **Text message:** text data, usually JSON, XML, or a string following an application convention.
- **Binary message:** binary data such as protobuf, file chunks, or a custom format.

WebSocket also defines control frames such as ping, pong, and close, along with a fragmentation mechanism at the frame layer. However, it does not specify that a text message is a SEND command, that a binary message is an event, or which subscription a client has registered.

A WebSocket connection usually has one URL for initiation. After the connection is established, many application messages pass through that same connection. This is an event-driven, full-duplex model, unlike ordinary HTTP request-response.

### 1.2. STOMP Is a Messaging Protocol

**STOMP (Simple Text Oriented Messaging Protocol)** defines how to represent messages as frames. A frame has a command, headers, an optional body, and a NULL character that terminates the frame.

Example of a client sending a message:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"room":"orders","text":"Hello"}^@
~~~

The ^@ notation in the STOMP documentation represents the NULL byte (0x00), not the two characters caret and @. STOMP uses UTF-8 by default for the command/headers and supports text or binary payloads.

Common commands:

| Command | Role |
|---|---|
| CONNECT or STOMP | Starts a STOMP session and negotiates the version |
| CONNECTED | The server confirms the STOMP connection |
| SEND | Sends a message to a destination |
| SUBSCRIBE | Registers to receive messages from a destination |
| UNSUBSCRIBE | Cancels a subscription |
| MESSAGE | The server delivers a message to a subscriber |
| ACK / NACK | Acknowledges or rejects a message according to the ack mode |
| RECEIPT | Confirms the server has processed a frame that requested a receipt |
| ERROR | Reports a protocol error |
| DISCONNECT | Disconnects the STOMP session in a controlled manner |

STOMP also defines heartbeats, transaction frames, and acknowledgement modes. But the practical meaning of destination, delivery, persistence, redelivery, and dead-letter still depends on the STOMP server/broker. Names such as /queue/orders or /topic/prices are common conventions; STOMP itself treats a destination as an opaque string.

## 2. How Is STOMP Negotiated over WebSocket?

WebSocket lets the client and server negotiate a subprotocol in the HTTP handshake through the **Sec-WebSocket-Protocol** header. With STOMP, the client can propose the subprotocol versions it supports; the server selects a common version and returns it in the handshake response.

Illustrative example:

~~~http
GET /ws HTTP/1.1
Host: example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Protocol: v10.stomp, v11.stomp, v12.stomp
Sec-WebSocket-Version: 13
~~~

The server may respond:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Protocol: v12.stomp
~~~

After the handshake, the client and server exchange STOMP frames inside WebSocket messages. If no subprotocol is negotiated, the two sides can still use WebSocket, but they must agree on a separate application format.

You need to distinguish:

- HTTP Upgrade establishes the WebSocket transport.
- Sec-WebSocket-Protocol negotiates the application protocol running on WebSocket.
- STOMP CONNECT/CONNECTED establishes the STOMP session after the transport is ready.

## 3. Plain WebSocket in Spring

Spring provides a direct API for handling WebSocket messages. An application can implement **WebSocketHandler**, or extend **TextWebSocketHandler** and **BinaryWebSocketHandler** if it only needs to handle one type of payload.

Example of a text handler:

~~~java
package com.example.websocket;

import java.io.IOException;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawChatHandler extends TextWebSocketHandler {
    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws IOException {
        String payload = message.getPayload();
        String response = "received:" + payload;
        session.sendMessage(new TextMessage(response));
    }
}
~~~

Registering the handler with Java configuration:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {
    private final RawChatHandler rawChatHandler;
    public RawWebSocketConfiguration(RawChatHandler rawChatHandler) {
        this.rawChatHandler = rawChatHandler;
    }
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(rawChatHandler, "/raw-chat")
                .setAllowedOrigins("https://app.example.com");
    }
}
~~~

In the example, the client connects to /raw-chat and then sends a text message. The handler receives the WebSocketSession and TextMessage, parses the payload itself, and then decides how to respond.

If you need binary messages, you can extend BinaryWebSocketHandler and override handleBinaryMessage. If you need to manage connect/disconnect, you can override afterConnectionEstablished and afterConnectionClosed.

### 3.1. The Application Must Define Its Own Message Contract

With plain WebSocket, the client and server need to agree on a format. Example JSON:

~~~json
{
  "version": 1,
  "type": "subscribe",
  "requestId": "req-42",
  "destination": "/prices",
  "payload": null
}
~~~

Another message might be:

~~~json
{
  "version": 1,
  "type": "publish",
  "requestId": "req-43",
  "destination": "/prices",
  "payload": {
    "symbol": "ACME",
    "price": 125.5
  }
}
~~~

The application must itself specify:

- Which types may be sent and received.
- The payload structure, the schema version, and how to validate.
- How to register/cancel a subscription.
- How to route a message to one client, a group of clients, or all clients.
- Correlation ID, request-response, and timeout.
- ACK/NACK, retry, duplicate handling, and idempotency if needed.
- A heartbeat at the application layer if the WebSocket ping/pong does not meet the requirements.
- Error rules, reconnect, and restoring subscriptions after a reconnect.

This is an advantage when you need a lean custom protocol close to the business domain. In return, the client and server must both implement and maintain that contract.

### 3.2. Note on Concurrent Message Sending

A standard WebSocketSession does not allow multiple threads to send concurrently on the same session. If multiple server threads send to one client at the same time, the application needs to synchronize the send operation or use **ConcurrentWebSocketSessionDecorator** to serialize sending and limit time/buffer per the configuration.

Do not treat WebSocketSession.sendMessage() as an unbounded thread-safe queue. You need to handle backpressure, limit the message size, and handle the case of a slow-reading client.

~~~java
package com.example.websocket;

public record ChatMessage(String sender, String content) {
}
~~~

~~~java
package com.example.websocket;

import java.math.BigDecimal;

public record PriceUpdate(String symbol, BigDecimal price) {
}
~~~
## 4. STOMP over WebSocket in Spring

When using STOMP, Spring provides a message broker programming model. The configuration typically uses @EnableWebSocketMessageBroker and WebSocketMessageBrokerConfigurer.

Example:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }
    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Meaning:

- /ws is the URL the client uses to perform the WebSocket handshake.
- /app is the prefix for messages sent into the application controllers.
- /topic and /queue are the prefixes used to route to the simple broker in the example.
- The simple broker stores subscriptions in memory and broadcasts messages to the matching subscribers.

The /topic and /queue prefixes in the built-in simple broker are only routing conventions. When using an external broker, follow the destination syntax and semantics that broker supports.

### 4.1. Handling Messages with @MessageMapping

A controller that receives STOMP messages can use @MessageMapping:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return new ChatMessage(message.sender(), message.content());
    }
}
~~~

When the client sends a STOMP SEND to /app/chat.send, Spring strips the application prefix /app and then maps the remainder to the method @MessageMapping("/chat.send"). The return value is sent to the destination /topic/chat, where the broker distributes it to the subscribers.

If you want to send messages from a service or a scheduled task, you can inject SimpMessagingTemplate:

~~~java
package com.example.websocket;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class PricePublisher {
    private final SimpMessagingTemplate messagingTemplate;
    public PricePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }
    public void publish(PriceUpdate update) {
        messagingTemplate.convertAndSend("/topic/prices", update);
    }
}
~~~

The service can broadcast messages without needing to know each client's WebSocketSession. The broker manages subscriptions and distributes messages.

## 5. The STOMP Message Flow inside Spring

Spring converts a STOMP frame into a Spring Message<?>, then passes the message through the internal channels.

~~~mermaid
flowchart TD
    C["WebSocket client"] --> W["WebSocket handshake /ws"]
    W --> S["STOMP frame"]
    S --> I["clientInboundChannel"]
    I --> A{"Destination prefix"}
    A -->|/app| M["@MessageMapping controller"]
    A -->|/topic or /queue| B["Message broker"]
    M --> BC["brokerChannel"]
    BC --> B
    B --> O["clientOutboundChannel"]
    O --> R["STOMP MESSAGE frame"]
    R --> C
~~~

The main components:

- **clientInboundChannel:** receives messages from the WebSocket client.
- **brokerChannel:** passes messages from application code to the broker.
- **clientOutboundChannel:** passes messages from the broker back to the client.
- **@MessageMapping:** handles messages belonging to the application destination.
- **Message broker:** stores subscriptions and distributes messages to the matching subscribers.

This flow helps separate the business logic from managing each individual socket. An HTTP controller or a service can also send messages through the broker to broadcast to the WebSocket clients that are subscribed.

## 6. Simple Broker and External STOMP Broker

Spring has two main choices for the broker.

### 6.1. The Built-in Simple Broker

The simple broker is a small broker running in the memory of the Spring application. It receives subscriptions and broadcasts messages to connected clients whose destinations match.

It suits when:

- You need a demo or the initial development of a realtime feature.
- The number of clients and the traffic are at a moderate level.
- You do not need an independent broker or clustering.
- The limitations of the supported subset of STOMP commands are acceptable.

The simple broker supports only part of STOMP. It does not support ACK, RECEIPT, and some other features of the protocol. It is also not suitable for clustering. Therefore, you should not infer that enabling enableSimpleBroker will provide all the delivery guarantees of a dedicated broker.

### 6.2. External Broker Relay

When you need a fuller broker, you can configure a relay to RabbitMQ, ActiveMQ, or a broker that supports STOMP:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("app-client")
            .setClientPasscode("configured-secret");
}
~~~

The login credentials in the example must come from the security configuration or the secret manager of the deployment environment, not hard-coded into source code.

The broker relay opens a TCP connection to the external broker, forwards STOMP messages from Spring to the broker, and forwards messages from the broker back to the WebSocket clients. A dedicated broker may provide subscription management, ACK, RECEIPT, persistence, clustering, or dead-letter features depending on the product and configuration.

STOMP does not by itself guarantee durable or exactly-once messages. You need to check the broker's semantics, destination, acknowledgement mode, persistence, and redelivery policy.

## 7. JavaScript Clients: Plain WebSocket and STOMP

### 7.1. Plain WebSocket

The browser API can connect and send JSON following a custom protocol:

~~~javascript
const socket = new WebSocket("wss://app.example.com/raw-chat");

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    version: 1,
    type: "subscribe",
    destination: "/prices"
  }));
});

socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  console.log("Application message:", message);
});

socket.addEventListener("close", event => {
  console.log("WebSocket closed:", event.code);
});
~~~

The client and server must understand the same JSON schema. The browser WebSocket does not by itself know that subscribe is a messaging command; that is only an application convention.

### 7.2. A STOMP Client

With STOMP, you can use the JavaScript library STOMP.js:

~~~javascript
const client = new StompJs.Client({
  brokerURL: "wss://app.example.com/ws",
  reconnectDelay: 5000,
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000
});

client.onConnect = () => {
  client.subscribe("/topic/chat", frame => {
    const message = JSON.parse(frame.body);
    console.log("Chat message:", message);
  });

  client.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({
      sender: "Ada",
      content: "Hello"
    }),
    headers: {
      "content-type": "application/json"
    }
  });
};

client.onStompError = frame => {
  console.error("Broker error:", frame.headers["message"]);
};

client.activate();
~~~

The STOMP client provides a high-level API for CONNECT, SUBSCRIBE, SEND, heartbeat, reconnect, and frame handling. The application still needs to manage subscriptions after a reconnect and handle errors according to the business logic.

## 8. Direct Comparison

| Criterion | Plain WebSocket | STOMP over WebSocket |
|---|---|---|
| Main layer | Transport | A messaging protocol on top of the transport |
| Payload | Text or binary following a self-defined contract | A STOMP frame with a command, headers, and a body |
| Routing | The application builds it | Destination header and broker routing |
| Publish-subscribe | Manage the registry/subscriptions yourself | Has SUBSCRIBE, UNSUBSCRIBE, and MESSAGE |
| Request-response | Design the correlation ID and response yourself | Can be built using destinations, headers, and conventions |
| ACK/NACK | Design it yourself | Has commands and ack modes; the broker must support them |
| Heartbeat | WebSocket ping/pong or a custom protocol | STOMP heartbeat; underneath it is still WebSocket |
| Broker | Integrate yourself if needed | Spring simple broker or an external STOMP broker |
| Client | Browser WebSocket or any WebSocket client | A compatible STOMP client |
| Spring API | WebSocketHandler, TextWebSocketHandler | @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate |
| Customizability | Very high | Per the protocol and the broker's extensions |
| Work the application must do itself | Format, routing, subscriptions, ack, correlation, errors | Mainly business logic, authorization, and broker configuration |

## 9. When to Choose Plain WebSocket

Plain WebSocket fits when:

- The application has a custom protocol that has been clearly defined.
- You need a binary payload or a specialized message format.
- There are only a few simple message types, for example a status stream or device control.
- You need precise control over encoding, framing at the application layer, and routing.
- You do not need a standardized broker subscription model.
- The client and server are both developed by the same team and can upgrade the protocol together.

Examples: a realtime game with its own binary protocol, a telemetry streaming application, or an IoT device with a minimal message envelope.

Version the protocol, validate payloads, limit sizes, control the send rate, synchronize sends, and handle reconnect. If many different services or clients need to communicate together, the cost of maintaining a custom protocol rises quickly.

## 10. When to Choose STOMP over WebSocket

STOMP fits when:

- You need publish-subscribe or many clients subscribing to a destination.
- You need to send messages from a controller/service to many clients.
- You want to use @MessageMapping and Spring message channels.
- You need a protocol that has client libraries for many languages.
- You want to integrate a dedicated broker to manage subscriptions and broadcasting.
- You need standard commands for subscription, acknowledgement, receipt, and heartbeat, with a broker that supports the corresponding features.

Examples: chat, a realtime dashboard, a price board, per-user notifications, or order status updates for many clients.

If you only need to experiment in a simple application, the simple broker may be enough. If you need clustering, broker persistence, or full STOMP features, use an external broker relay and clearly verify the semantics the broker supports.

## 11. Security and Reliability

Both approaches need to protect the transport and the messages.

- Use **wss://** in the production environment to encrypt the connection.
- Restrict the Origin and check the handshake. Spring WebSocket by default accepts only same-origin in the standard configuration; only expand the origin list when there is a clear requirement.
- Authenticate users through an appropriate HTTP/Spring Security mechanism and check permissions on each message.
- Do not trust a destination or user ID sent by the client. The server must determine which destinations a client is allowed to publish/subscribe to.
- Limit message size, number of connections, send rate, and number of subscriptions.
- Handle disconnect, timeout, heartbeat, reconnect, and backpressure.
- Do not write tokens, passcodes, or sensitive payloads to logs.

With plain WebSocket, the application must build authorization by message type and destination itself. With STOMP, destinations and message types already have a structure, so Spring Security can apply message protection rules by destination and command.

You need to understand clearly the meaning of acknowledgement. A STOMP RECEIPT confirms that the server has processed the corresponding frame per the protocol; it does not prove that the business logic on the client side has completed or that a database transaction has committed. With ack mode auto, the broker may consider a message received as soon as it is sent to the client; client and client-individual require an explicit ACK. The redelivery behavior when a connection is lost depends on the broker.

## 12. Does SockJS Replace STOMP?

No. SockJS is a layer that supports a fallback transport when the client environment or a proxy cannot use WebSocket. It can use WebSocket or other HTTP-based transports depending on the environment's capabilities.

STOMP is a messaging protocol. A STOMP endpoint can enable SockJS:

~~~java
registry.addEndpoint("/ws").withSockJS();
~~~

The corresponding client needs to use a SockJS client combined with a STOMP client. Enabling SockJS does not change the commands, destinations, or semantics of STOMP.

## 13. Java 17 Example: Comparing a Custom Message with a STOMP Frame

The following example uses plain JDK to analyze two representations of the same subscribe intent. Raw WebSocket uses a format defined by the application itself; STOMP uses standard commands and headers. The program only illustrates the format; it does not open a WebSocket connection and does not replace a production STOMP parser.

Create the file **StompVsRawWebSocketDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class StompVsRawWebSocketDemo {

    record RawEnvelope(
            String operation,
            String destination,
            String payload) {}

    record StompFrame(
            String command,
            Map<String, String> headers,
            String body) {}

    static RawEnvelope parseRawEnvelope(String wire) {
        String[] parts = wire.split("\\|", 3);

        if (parts.length != 3) {
            throw new IllegalArgumentException(
                    "Expected operation|destination|payload");
        }

        return new RawEnvelope(parts[0], parts[1], parts[2]);
    }

    static StompFrame parseStompFrame(String wire) {
        String normalized = wire.replace("\r\n", "\n");
        int separator = normalized.indexOf("\n\n");

        if (separator < 0) {
            throw new IllegalArgumentException(
                    "STOMP frame has no header/body separator");
        }

        String headerBlock = normalized.substring(0, separator);
        String body = normalized.substring(separator + 2);
        String nullOctet = String.valueOf((char) 0);

        if (body.endsWith(nullOctet)) {
            body = body.substring(0, body.length() - 1);
        }

        String[] lines = headerBlock.split("\n");
        String command = lines[0];
        Map<String, String> headers = new LinkedHashMap<>();

        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');

            if (colon <= 0) {
                throw new IllegalArgumentException(
                        "Invalid STOMP header: " + lines[i]);
            }

            String name = lines[i].substring(0, colon);
            String value = lines[i].substring(colon + 1);
            headers.putIfAbsent(name, value);
        }

        return new StompFrame(command, headers, body);
    }

    public static void main(String[] args) {
        String rawWire = "SUBSCRIBE|/topic/prices|";
        RawEnvelope raw = parseRawEnvelope(rawWire);

        String nullOctet = String.valueOf((char) 0);
        String stompWire =
                "SUBSCRIBE\n"
                + "id:sub-1\n"
                + "destination:/topic/prices\n"
                + "ack:client-individual\n"
                + "\n"
                + nullOctet;

        StompFrame stomp = parseStompFrame(stompWire);

        System.out.println(
                "Raw protocol: " + raw.operation()
                        + " " + raw.destination());

        System.out.println(
                "STOMP command: " + stomp.command());

        System.out.println(
                "STOMP destination: "
                        + stomp.headers().get("destination"));

        System.out.println(
                "STOMP ack mode: " + stomp.headers().get("ack"));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac StompVsRawWebSocketDemo.java
java StompVsRawWebSocketDemo
~~~

Result:

~~~text
Raw protocol: SUBSCRIBE /topic/prices
STOMP command: SUBSCRIBE
STOMP destination: /topic/prices
STOMP ack mode: client-individual
~~~

The raw example only understands the three fields defined by the application itself. The sample STOMP parser only handles a simple frame with basic headers; a production parser must also handle header escaping, content-length, binary bodies, multiple frames on a stream, and the other rules of STOMP 1.2.

## 14. Selection and Testing Checklist

Before deciding, answer:

1. Does the application need a bidirectional connection or a messaging model with destinations/subscriptions?
2. Do many clients need to receive the same message?
3. Do you need ACK/NACK, receipts, heartbeat, or broker persistence?
4. Do clients span many languages/platforms and need a standard protocol?
5. Do you need an independent broker to scale or cluster?
6. Is the payload mainly JSON/text or a specialized binary protocol?
7. Who is responsible for versioning and protocol compatibility?
8. Are the rules for authentication, authorization, Origin, and message limits clear yet?

Important tests:

- Handshake and subprotocol negotiation.
- Text/binary payloads and size limits.
- Multiple clients connecting, disconnecting, and reconnecting.
- Subscribe/unsubscribe, routing, and broadcast.
- ACK/NACK, receipts, and redelivery if the broker supports them.
- Heartbeat and timeout when the connection is idle.
- A client sending too fast or reading slowly to test backpressure.
- Verify that users cannot subscribe/publish to destinations they have no permission for.
- Broker restart and Spring application restart.

Plain WebSocket provides a full-duplex transport and leaves the message contract to the application. STOMP over WebSocket adds a standard messaging protocol with commands, headers, destinations, and subscriptions, which lets Spring provide controller routing, a broker, and a high-level client API. Choose plain WebSocket when you need a minimal custom protocol or a specialized binary one; choose STOMP when the application needs publish-subscribe, message routing, and broker integration. In both cases, delivery guarantees, security, and resilience must still be designed according to real requirements.

## References

- [Spring Framework: WebSocket API](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework: STOMP overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework: Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework: Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework: External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)