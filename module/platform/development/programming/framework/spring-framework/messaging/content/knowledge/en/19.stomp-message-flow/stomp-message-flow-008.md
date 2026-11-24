# Application Prefix, Broker Prefix, and User Prefix

Spring STOMP over WebSocket uses the destination in the STOMP frame to decide whether a message goes to a business controller, to the message broker, or to a specific user/session. There are three commonly used groups of prefixes:

- **/app**: messages directed into the application, usually routed to @MessageMapping methods.
- **/topic and /queue**: destinations managed by the broker for delivering messages.
- **/user/**: a logical destination for a user/session; Spring resolves it into an internal destination specific to each connection session.

These prefixes belong to the STOMP destination layer. They differ from the WebSocket endpoint URL such as /ws, which is the HTTP address used to start the handshake. A client can connect to the correct WebSocket endpoint but send messages to the wrong destination if it confuses these two concepts.

## 1. WebSocket endpoint and STOMP destination

The WebSocket endpoint is the URL the client uses to open the connection:

~~~java
registry.addEndpoint("/ws");
~~~

The browser connects to ws://localhost:8080/ws or wss://app.example.com/ws.

After connecting, the client sends STOMP frames with a destination header, for example:

~~~text
/app/chat.send
/topic/chat
/user/queue/reply
~~~

Spring classifies destinations after the handshake completes. They are not HTTP URLs and do not need to be registered as separate endpoints.

General configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The client connects to /ws, sends commands to /app/..., subscribes to broker destinations such as /topic/... or /queue/..., and can use /user/ to receive private messages. Do not add /app to the handshake URL.

## 2. Application prefix: setApplicationDestinationPrefixes

The application prefix determines which STOMP messages are passed to @MessageMapping methods in controllers.

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

Controller example:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

The client sends a STOMP SEND to /app/chat.send:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"sender":"alice","content":"Hello"}
^@
~~~

Spring notices that the destination starts with /app, strips this prefix, and then uses the remaining part /chat.send to look up @MessageMapping("/chat.send").

Because the prefix has been stripped before the lookup, the annotation only contains the remaining path:

~~~java
@MessageMapping("/chat.send")
~~~

Do not write @MessageMapping("/app/chat.send"), because that mapping would repeat the prefix that Spring has already stripped.

You can declare multiple application prefixes:

~~~java
registry.setApplicationDestinationPrefixes("/app", "/api");
~~~

Spring strips the matching prefix before looking up the mapping. Prefixes should follow a clear convention and not overlap with the broker prefixes. Spring automatically appends a trailing / if an application prefix does not already have one.

The application prefix is only a routing rule, not an authentication or authorization mechanism. The controller must still validate the payload, identity, permissions, and business state. Spring Security can restrict clients to SEND only to /app/** and control SUBSCRIBE to permitted destinations.

If a client is allowed to SEND directly to /topic/..., it can bypass the validation in @MessageMapping. Open only the destinations that clients actually need.

## 3. Broker prefix: simple broker and broker relay

The broker prefix determines the destinations managed by the broker. Clients usually SUBSCRIBE to these destinations; the server can also send messages to them.

Spring supports two ways of configuring this:

- enableSimpleBroker(...): a simple broker running in the application's memory.
- enableStompBrokerRelay(...): a relay that forwards messages to an external STOMP broker.

### Simple broker

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Client subscribes:

~~~text
SUBSCRIBE
id:chat-subscription
destination:/topic/chat
ack:auto
^@
~~~

When the server sends a message to /topic/chat, the simple broker finds the subscriptions that match the destination and delivers the message to the corresponding clients.

In the simple broker, /topic and /queue have no special semantics imposed by Spring. They are naming conventions to distinguish publish-subscribe from flows generally understood as point-to-point. Therefore, /queue/orders on the simple broker is not automatically a durable queue with competing consumers like the queue of a dedicated broker.

The simple broker is suitable for small applications or experiments. It supports only a subset of STOMP commands, does not have full ACK/RECEIPT, and is not suitable for clustering.

### STOMP broker relay

When you need a dedicated broker, configure the relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613)
            .setClientLogin("stomp-client")
            .setClientPasscode("CLIENT_PASSWORD")
            .setSystemLogin("stomp-system")
            .setSystemPasscode("SYSTEM_PASSWORD");
}
~~~

The relay is a MessageHandler in Spring. It opens a TCP connection to the external STOMP broker, forwards messages from the application up to the broker, and forwards messages sent back by the broker down to WebSocket clients.

- enableStompBrokerRelay chooses the destinations that are forwarded to the broker.
- setRelayHost and setRelayPort set the broker's TCP address.
- setClientLogin and setClientPasscode set the credentials for the relayed client connections.
- setSystemLogin and setSystemPasscode set the credentials for Spring's system connection.

Obtain credentials from a secret manager or environment variables; do not commit passwords into source code. The syntax and semantics of /topic, /queue, or other prefixes depend on the broker. Check the STOMP documentation of RabbitMQ, ActiveMQ Artemis, or whichever broker you use.

| Destination | Simple broker | External STOMP broker |
|---|---|---|
| /topic/news | Convention for broadcasting to matching subscribers | Usually a pub-sub destination |
| /queue/orders | In-memory destination, not a real durable queue | Usually a point-to-point queue |
| /app/orders.create | Routed to the controller | Handled by Spring before the relay |
| /user/queue/alerts | Spring resolves the user destination before the broker | Spring resolves it, then relays to the broker |

## 4. User prefix: /user/

Spring's default user destination prefix is /user/. It lets clients subscribe to the same logical name but receive messages at internal destinations specific to each user or session.

For example, Alice and Bob both subscribe:

~~~text
/user/queue/notifications
~~~

Spring uses UserDestinationMessageHandler to convert the logical destination into a separate internal name. The physical names may look like the following:

~~~text
Alice: /queue/notifications-userA-session1
Bob:   /queue/notifications-userB-session1
~~~

This is only an illustrative example. The application should not create, or depend on, the way Spring names these internally. The client only needs to subscribe to /user/queue/notifications.

The SUBSCRIBE frame:

~~~text
SUBSCRIBE
id:private-notifications
destination:/user/queue/notifications
^@
~~~

Spring processes /user/, finds the matching user/session, and then passes the subscription to the separate destination. When the server sends a message to a user, Spring resolves it to the corresponding destination so that the broker delivers it to the correct session.

 /user/ is not an ordinary broker prefix. It is handled by UserDestinationMessageHandler; only the internal destination after resolution is passed on to the broker. Avoid configuring a broker prefix that is too broad, such as /, which would make the broker catch /user/... before Spring handles it.

You can change the default prefix:

~~~java
registry.setUserDestinationPrefix("/private/");
~~~

If you change it, the client and server must consistently use the new prefix. If the setter is not called, Spring defaults to /user/.

## 5. Sending messages to a user with SimpMessagingTemplate

A service can send a message to a specific user with SimpMessagingTemplate.convertAndSendToUser():

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

The first parameter is the user name, usually taken from Principal.getName(). The second parameter is the destination part after the user prefix; do not add /user/ to this parameter.

The Principal reflects the authenticated user of the WebSocket session. In a Spring Security application, identity is usually established through the HTTP handshake and the security context. Do not treat a username that the client sends in JSON as a trustworthy identity.

A user can log in from multiple tabs or devices. By default, a user destination can send to all of the user's sessions that subscribe to that destination. If you only want to reply to the session that sent the message, use @SendToUser with broadcast=false:

~~~java
@MessageMapping("/orders.validate")
@SendToUser(value = "/queue/validation", broadcast = false)
public ValidationResult validate(OrderRequest request) {
    return validationService.validate(request);
}
~~~

For a session with no authenticated user attached, @SendToUser also has the semantics of sending only to the session that sent the message.

## 6. @SendTo, @SendToUser, and @SubscribeMapping

@SendTo routes the return value to a broker destination:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(ChatMessage message) {
    return message;
}
~~~

The client sends /app/chat.send; Spring strips /app, invokes the method, and sends the result to /topic/chat. The broker publishes the message to the matching subscribers.

You can specify multiple destinations:

~~~java
@MessageMapping("/orders.created")
@SendTo({"/topic/orders", "/topic/audit"})
public OrderEvent publish(OrderEvent event) {
    return event;
}
~~~

If @SendTo is not declared, Spring uses a default reply destination based on the input destination and the default broadcast prefix. Using an explicit @SendTo helps the client and server agree on the contract.

@SendToUser routes the result to a user/session:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

The client subscribes to /user/queue/profile. A method-level annotation can override the default configuration at the class level.

@SubscribeMapping handles STOMP SUBSCRIBE instead of SEND. It is useful when the client needs to fetch the initial state at registration time:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard")
    public DashboardSnapshot initialSnapshot(Principal principal) {
        return dashboardService.load(principal.getName());
    }
}
~~~

The client subscribes to /app/dashboard. Spring invokes the method and by default sends the result directly back to the client that initiated the subscription, without broadcasting through the broker. If you want the result to go through the broker, add @SendTo or @SendToUser.

| Annotation | STOMP frame | Purpose |
|---|---|---|
| @MessageMapping | SEND | Handle commands/messages sent into the application |
| @SubscribeMapping | SUBSCRIBE | Return initial data to the subscribing client |
| @SendTo | Return routing | Send the result to a broker destination |
| @SendToUser | Return routing | Send the result to a user/session destination |

## 7. The complete routing flow in Spring

When /app, /topic, /queue, and /user/ are configured, messages pass through the main channels:

~~~text
Client
  |
  | SEND /app/chat.send
  v
clientInboundChannel
  |
  | match /app, remove application prefix
  v
@MessageMapping("/chat.send")
  |
  | @SendTo("/topic/chat")
  v
brokerChannel
  |
  v
Message Broker
  |
  | find matching subscriptions
  v
clientOutboundChannel
  |
  v
WebSocket clients
~~~

The roles of the channels:

- clientInboundChannel: receives messages from WebSocket clients after the STOMP frame has been decoded.
- brokerChannel: carries messages from server-side code to the broker.
- clientOutboundChannel: carries messages from the server/broker to WebSocket clients.

With a user destination, UserDestinationMessageHandler processes the subscription and then registers the separate destination at the broker. When the server calls convertAndSendToUser, Spring resolves the user/session and then sends through the broker and clientOutboundChannel.

## 8. Configuring the three kinds of prefixes together

An easy-to-understand configuration uses prefixes that do not overlap:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

| Prefix | Where it is handled | Example |
|---|---|---|
| /app | Spring annotated controller | SEND /app/chat.send |
| /topic | Simple broker or external relay | SUBSCRIBE /topic/chat |
| /queue | Simple broker or external relay | SUBSCRIBE /queue/jobs |
| /user/ | UserDestinationMessageHandler, then the broker | SUBSCRIBE /user/queue/notifications |

setUserDestinationPrefix("/user/") can be called to state the convention explicitly or to change the default value. Do not set the same prefix for both the application and the broker. For example, /app being both an application prefix and a broker prefix would make the routing flow hard to understand.

## 9. External broker and multiple instances

When enableStompBrokerRelay is used, Spring still handles /app and /user/; the broker destinations are forwarded to the external broker.

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user/");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin(System.getenv("STOMP_CLIENT_LOGIN"))
            .setClientPasscode(System.getenv("STOMP_CLIENT_PASSWORD"))
            .setSystemLogin(System.getenv("STOMP_SYSTEM_LOGIN"))
            .setSystemPasscode(System.getenv("STOMP_SYSTEM_PASSWORD"));
}
~~~

Check that the broker has the STOMP listener enabled, that the relay account has SEND/SUBSCRIBE permissions, TLS for the broker connection if needed, and the provider's destination semantics. Temporary destinations created by user destinations need to be cleaned up by the broker when the session ends.

In an application with multiple Spring nodes, a user may connect on node A while the event is processed on node B. Node B may not know that the user's session is on A. MessageBrokerRegistry has the options setUserDestinationBroadcast(...) and setUserRegistryBroadcast(...) to help share user destination/registry information between nodes.

When deploying multiple nodes, you need a suitable external broker, configure broadcasting of unresolved user destinations when needed, synchronize prefixes and user identity across nodes, test reconnects, and monitor messages that cannot be resolved. The in-memory simple broker does not share subscriptions between instances on its own.

## 10. Security by destination prefix

The destination prefix only decides routing; it does not replace authentication or authorization.

A common policy:

- Authenticated clients may SEND to /app/**.
- Clients may SUBSCRIBE to public topics or permission-based topics.
- Clients may SUBSCRIBE only to /user/queue/** meant for that user/session itself.
- Clients may not SEND by themselves into administrative or internal destinations.
- The server uses SimpMessagingTemplate to send notifications to users according to the authenticated Principal.

Do not let clients freely choose a username in /user/{username}/... and then treat that as the right to send to other people. The server must determine the target user from validated business data and use the server-side API for sending to a user.

If you use Spring Security, configure message authorization on the STOMP inbound channel. You can allow SEND /app/** and restrict SUBSCRIBE /topic/**, /user/** by role or ownership. The specific rules depend on the application's permission model.

You need to validate the payload, limit message size, apply rate limits, and check permissions on each business object. A client that has the right to connect over WebSocket is not implicitly allowed to read every topic.

## 11. Complete example: chat broadcast and user reply

The example uses Java 17, Spring Boot 3.4.4, and spring-boot-starter-websocket. The application has the endpoint /ws, application prefix /app, broker prefixes /topic and /queue, and user prefix /user/. /app/chat.send broadcasts to /topic/chat; /app/chat.echo replies privately to the sending session at /user/queue/reply.

The simple broker runs in memory, so no external broker needs to be installed.

Structure:

~~~text
stomp-prefix-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── StompApplication.java
        │       ├── WebSocketConfiguration.java
        │       ├── ChatMessage.java
        │       └── ChatController.java
        └── resources/
            └── static/
                └── index.html
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stomp-prefix-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

### src/main/java/demo/StompApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompApplication.class, args);
    }
}
~~~

### src/main/java/demo/WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

### src/main/java/demo/ChatMessage.java

~~~java
package demo;

public record ChatMessage(String sender, String content) {
}
~~~

### src/main/java/demo/ChatController.java

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage broadcast(ChatMessage message) {
        return message;
    }

    @MessageMapping("/chat.echo")
    @SendToUser(value = "/queue/reply", broadcast = false)
    public ChatMessage echo(ChatMessage message) {
        return new ChatMessage(
                "server",
                "Private reply: " + message.content()
        );
    }
}
~~~

Note on imports: @SendTo belongs to the package org.springframework.messaging.handler.annotation; @SendToUser belongs to org.springframework.messaging.simp.annotation.

The broadcast method receives the message via /app/chat.send, then returns the result to /topic/chat. All clients subscribed to /topic/chat receive the message.

The echo method receives the message via /app/chat.echo, then returns the result to /user/queue/reply. broadcast=false limits the reply to the session that sent the message. The example does not require login in order to illustrate a session-specific reply; a real application usually combines private user destinations with authentication and authorization.

### src/main/resources/static/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Spring STOMP Prefix Demo</title>
</head>
<body>
    <h1>Spring STOMP Prefix Demo</h1>
    <button id="send">Send test messages</button>
    <pre id="log"></pre>

    <script type="module">
        import { Client } from "https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.1.1/esm6/index.js";

        const logElement = document.getElementById("log");

        function log(value) {
            logElement.textContent += value + "\n";
        }

        const scheme = location.protocol === "https:" ? "wss" : "ws";
        const client = new Client({
            brokerURL: scheme + "://" + location.host + "/ws",
            reconnectDelay: 5000
        });

        client.onConnect = () => {
            log("STOMP connected");

            client.subscribe("/topic/chat", (frame) => {
                log("broadcast: " + frame.body);
            });

            client.subscribe("/user/queue/reply", (frame) => {
                log("private: " + frame.body);
            });

            document.getElementById("send").disabled = false;
        };

        client.onStompError = (frame) => {
            log("STOMP error: " + frame.headers.message);
        };

        document.getElementById("send").disabled = true;
        document.getElementById("send").addEventListener("click", () => {
            const message = {
                sender: "browser",
                content: "Hello from STOMP"
            };

            client.publish({
                destination: "/app/chat.send",
                body: JSON.stringify(message)
            });

            client.publish({
                destination: "/app/chat.echo",
                body: JSON.stringify(message)
            });
        });

        client.activate();
    </script>
</body>
</html>
~~~

Run in the directory containing pom.xml:

~~~shell
mvn spring-boot:run
~~~

Open http://localhost:8080 in two browser windows. Click Send test messages in one window.

Both windows receive the broadcast on /topic/chat. Only the sending window receives the private reply on /user/queue/reply.

Expected output in the sending window:

~~~text
STOMP connected
broadcast: {"sender":"browser","content":"Hello from STOMP"}
private: {"sender":"server","content":"Private reply: Hello from STOMP"}
~~~

Expected output in the other window:

~~~text
STOMP connected
broadcast: {"sender":"browser","content":"Hello from STOMP"}
~~~

The example verifies the three groups of destinations:

1. /app/chat.send and /app/chat.echo go into @MessageMapping.
2. /topic/chat is managed by the simple broker and broadcast to subscribers.
3. /user/queue/reply is resolved by Spring into a destination specific to the sending session.

If you use HTTPS, the client picks wss:// by itself based on location.protocol. In production, you need to configure allowed origins, TLS, authentication, and message authorization.

## 12. Common mistakes

**Putting the application prefix into @MessageMapping:** the client sends /app/chat.send, and Spring strips /app before looking up the mapping. The annotation must be /chat.send.

**Using the WebSocket endpoint as a STOMP destination:** /ws is the handshake URL. /app, /topic, /queue, and /user/ are destinations inside STOMP frames.

**Forgetting to configure the application prefix:** if a controller is designed to receive /app/** but the registry does not declare an application prefix, messages may go to the broker instead of the controller.

**Using the same prefix for the application and the broker:** overlapping prefixes make the routing flow hard to control and make it easy to send a message to the wrong handler.

**Registering /user/ as an ordinary broker prefix:** user destinations need to be resolved by UserDestinationMessageHandler first. Make sure the broker prefix does not accidentally catch /user/.

**Assuming the simple broker's /queue is a real queue:** the simple broker uses in-memory destination names and subscription matching. It does not provide all the semantics of a dedicated queue broker.

**Assuming /topic and /queue mean the same thing on every broker:** destination semantics depend on the broker. Check the broker's STOMP documentation when using a relay.

**Subscribing to /user/{username}/queue/... on the client:** a normal client subscribes to /user/queue/.... The username is used on the server side when sending to a specific user.

**Passing /user/ into convertAndSendToUser:** the destination parameter of convertAndSendToUser is the part after the user prefix, for example /queue/notifications.

**Taking the username from the payload to send a private message:** the user's identity must come from the authenticated Principal or from data the server has verified. A client can forge the username in JSON.

**Thinking a user destination authenticates the user automatically:** /user/ only routes messages by user/session. It does not log users in or grant access rights.

**Not handling multiple sessions of the same user:** by default, a user destination can send to multiple registered sessions. Use broadcast=false if you only need to reply to the originating session.

**Using the simple broker for a multi-node system:** the in-memory simple broker does not share subscriptions between instances. Use a broker relay and configure the user registry/broadcast appropriately when you need to scale out.

**Not controlling SEND/SUBSCRIBE permissions:** a prefix is not authorization. Configure Spring Security to restrict which destinations clients may send to and subscribe to.

## 13. Destination design checklist

- The WebSocket handshake URL is separated from STOMP destinations.
- The application prefix is only for messages that need to be handled by @MessageMapping.
- @MessageMapping annotations do not repeat the application prefix.
- Broker prefixes include only the destinations that the broker actually manages.
- The default user prefix /user/ is kept separate for Spring to resolve.
- Application and broker prefixes do not overlap.
- @SendTo points to a destination under the broker prefix.
- Clients subscribe to /user/queue/... to receive private messages.
- The server uses convertAndSendToUser(username, "/queue/...", payload) when sending to a specific user.
- The Principal comes from the configured authentication mechanism.
- A decision has been made on how to handle multiple sessions of the same user.
- A choice has been made between the simple broker and an external broker relay based on requirements for clustering, ACK, RECEIPT, and durability.
- The destination semantics of the specific broker have been checked.
- Spring Security restricts SEND and SUBSCRIBE by permission.
- Integration tests exist for broadcast, private reply, reconnect, and multiple sessions.

## 14. Key takeaways

- /app is the application destination prefix; Spring strips the prefix and then routes the remainder to @MessageMapping.
- /topic and /queue are broker destination prefixes; they are configured with enableSimpleBroker or enableStompBrokerRelay.
- In the simple broker, /topic and /queue are naming conventions and do not by themselves create durable queue/topic semantics like a dedicated broker.
- /user/ is the default user destination prefix; UserDestinationMessageHandler converts the logical destination into a destination specific to the user/session.
- Clients typically send SEND to /app/... and SUBSCRIBE to /topic/... or /user/queue/....
- The server can send to a user with convertAndSendToUser(username, "/queue/...", payload).
- @SendTo routes the result to a broker destination; @SendToUser routes the result to a user/session.
- /ws is the handshake URL, not a STOMP destination prefix.
- A prefix only decides routing; authentication and authorization still need to be configured separately.
- When using multiple instances, you need a shared broker and a suitable user destination mechanism so that messages reach the correct session.

## References

- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — Flow of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html)
- [Spring Framework 6.2 — User Destinations](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/user-destination.html)
- [Spring Framework 6.2 — External Broker and Broker Relay](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-broker-relay.html)
- [MessageBrokerRegistry Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [MessageMapping Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [SendTo Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/handler/annotation/SendTo.html)
