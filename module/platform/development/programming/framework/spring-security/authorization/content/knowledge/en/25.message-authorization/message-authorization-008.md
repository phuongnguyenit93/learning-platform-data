# clientInboundChannel and the Outbound Data Protection Boundary in Spring Security STOMP

## 1. The Problem: Controlling Inbound Commands Does Not Guarantee Outbound Data Safety

A Spring Boot application uses WebSocket and STOMP to push real-time messages or notifications. Alice is permitted to view room 42 in tenant A; Bob is permitted to view only room 77; Carol belongs to tenant B. All three are subscribed to general announcements at `/topic/public`.

The system enables `@EnableWebSocketSecurity` and configures an `AuthorizationManager<Message<?>>` checking every `SEND` or `SUBSCRIBE` from clients. However, a scheduled job accidentally calls:

```java
messagingTemplate.convertAndSend("/topic/public", privatePayrollReport);
```

Alice, Bob, and Carol can then all receive tenant A's payroll report. **Inbound authorization may have executed completely accurately**: these clients genuinely hold permission to listen to the public topic. The bug stems from **the server choosing the wrong destination for the data**.

Spring Security documentation confirms that integrated STOMP security protects **`clientInboundChannel`**, rather than automatically enforcing authorization on every frame on **`clientOutboundChannel`**. A single inbound message can generate many outbound messages, so the framework encourages protecting subscriptions rather than re-evaluating the entire fan-out by default.

That does not mean outbound traffic can lack security. Multiple boundaries must work together:

1. How are clients connected and authenticated?
2. Which commands or destinations may clients send to or subscribe to?
3. Does the server have authority to create the event and emit it to that destination?
4. Does the payload belong to the right tenant, resource, and recipient?
5. When permissions are revoked, are active subscriptions canceled or re-checked?

**Principle:** a valid `SUBSCRIBE` does not grant permanent permission to all content the server emits in the future.

## 2. The Three Spring Messaging Channels

| Component | Primary Direction | Function |
| --- | --- | --- |
| `clientInboundChannel` | Client → server | Receives STOMP `CONNECT`, `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`... |
| `brokerChannel` | Application → broker | Receives messages produced by `@MessageMapping`, services, HTTP controllers, cron jobs |
| `clientOutboundChannel` | Broker → client | Delivers STOMP `MESSAGE` frames to subscribed WebSocket sessions |

Diagram:

```text
WebSocket client
      |
      | STOMP SEND /app/chat.send
      | STOMP SUBSCRIBE /topic/rooms/42
      v
clientInboundChannel
      |
      +--> Message AuthorizationManager
      |        +--> DENY: do not process further
      |        +--> ALLOW
      v
@MessageMapping / broker subscription
      |
      +--> Domain service, resource ACL
      +--> Select data, audience, DTO
      |
      v
SimpMessagingTemplate
      |
      v
brokerChannel <----- cron, HTTP, Kafka, outbox...
      |
      v
Message broker
      |
      +--> identify matching subscriptions
      v
clientOutboundChannel
      |
      v
WebSocket clients receive STOMP MESSAGE
```

This diagram is a logical model; Spring Framework uses different handlers for the simple broker and STOMP broker relays. Key takeaway: **calling `SimpMessagingTemplate` inside the server does not generate a new inbound STOMP SEND for Spring Security to re-check**.

### Do Not Confuse MESSAGE Types

A client's STOMP `SEND` command is typically represented as `SimpMessageType.MESSAGE` on the inbound channel. A STOMP `MESSAGE` pushed by the broker to clients is outbound traffic. `simpMessageDestMatchers(...)` does not automatically become a content filter on every STOMP MESSAGE emitted by the server.

## 3. Four Moments Where Permissions Must Be Evaluated

Suppose:

```text
10:00 Alice HTTP handshake + STOMP CONNECT succeed
10:01 Alice SUBSCRIBE room42, membership verified → ALLOW
10:05 Server publishes a valid room42 event
10:10 Admin revokes Alice from room42 in database
10:11 Server publishes a new room42 event
```

There are four distinct decisions:

- **Connection authorization:** should Alice be allowed to open a WebSocket/STOMP session?
- **Inbound authorization:** was Alice allowed to request `SUBSCRIBE` to room42 at 10:01?
- **Publication authorization:** does the new event belong to the right room/tenant and may it be published to that topic?
- **Delivery/revocation:** should Alice still receive the event at 10:11?

If the broker still holds Alice's subscription, the event at 10:11 **can** be delivered to Alice. An ACL change in the database does not automatically make Spring Security outbound filter recipients against the new ACL version.

Therefore, the policy must clearly define whether permissions are checked at subscribe time, publish time, delivery time, or multiple points, the SLA for revocation taking effect, and how races are handled.

## 4. Minimal STOMP Broker Configuration

Java Config example with Spring MVC/Servlet and STOMP-over-WebSocket:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("https://portal.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
```

This is a **Spring configuration class**, not a standalone program runnable with plain `javac`. It requires Spring WebSocket/Messaging, authentication/session setup, and a server. The domain `example.test` is illustrative; replace it with genuinely trusted origins.

In this configuration:

- `GET /ws`: HTTP handshake endpoint, not a STOMP SEND destination.
- `/app/**`: messages routed to application handlers such as `@MessageMapping`.
- `/topic/**`: broker broadcast destinations.
- `/queue/**`: broker queue destinations, depending on broker semantics.
- `/user/**`: Spring user destination abstraction, mapped to specific users/sessions.

Prefixes **do not create object-level ACLs automatically**. A destination named `/topic/tenants/a/rooms/42` does not prove the user belongs to tenant A.

## 5. Protecting Inbound Commands

Since 5.8, Spring Security supports WebSocket message authorization with `AuthorizationManager`. Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("CHAT_SEND")
            .simpSubscribeDestMatchers("/topic/public")
                .authenticated()
            .simpSubscribeDestMatchers("/user/queue/notifications")
                .authenticated()
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

This is a **Spring component** requiring compatible dependencies; authentication, CONNECT CSRF, broker, and business policies must be configured separately.

Meaning:

1. Frames without a destination require `authenticated` via `nullDestMatcher`. STOMP CONNECT also carries CSRF/Same-Origin requirements from Spring Security in the corresponding setup.
2. Only inbound `MESSAGE`/STOMP SEND to `/app/chat.send` is permitted when holding authority `CHAT_SEND`.
3. Only SUBSCRIBE to `/topic/public` or `/user/queue/notifications` is opened in the example.
4. Direct SEND to `/topic/public`, `/topic/system`, or `/queue/private` is blocked by the catch-all.
5. Other destinations/types are DENIED by default.
6. Matchers are evaluated in order: specific rules must precede broad rules.

The example **does not yet grant private room subscriptions**. To open `/topic/tenants/{tenant}/rooms/{room}`, a dedicated manager must verify active tenant membership, room membership, resource state, and action.

### Why Avoid Broad simpDestMatchers?

This snippet:

```java
messages.simpDestMatchers("/topic/**").authenticated();
```

can grant overly broad access to messages with a destination rather than SUBSCRIBE only. If clients can SEND directly to a broker prefix, an attacker can spoof notices the server intended to publish exclusively. For private topics, checking only `authenticated()` also introduces BOLA/IDOR risk.

## 6. HTTP Handshake Is Not Outbound Data Authorization

HTTP `SecurityFilterChain` can authenticate the `Principal` during upgrade. Spring propagates the `Principal` from HTTP to the WebSocket/STOMP session in the standard integration model.

However:

- HTTP 101 means the transport upgraded successfully, not that every STOMP command is allowed.
- STOMP `CONNECT` is a separate step; Spring Security also requires a CSRF token in CONNECT as a same-origin check, depending on configuration.
- An allowed STOMP `SUBSCRIBE` verifies subscription permission only at the moment it is evaluated.
- After upgrade, there is no new HTTP `SecurityFilterChain` pass per outbound MESSAGE frame.
- If using a raw `WebSocketHandler` or a non-Spring-Messaging/STOMP protocol, `@EnableWebSocketSecurity` does not automatically protect individual raw frames.

Test each layer rather than testing only HTTP status or CONNECTED.

## 7. Right Subscription, Wrong Data: Publisher-Side Vulnerability

A validly subscribed public topic can receive confidential payloads due to a publisher mistake:

```java
messaging.convertAndSend("/topic/public", payrollEntity);
```

This is a leak even though the inbound SUBSCRIBE rule works accurately.

A publisher must verify:

- The event source is a trusted service/actor.
- The event's tenant, room, and resource come from trusted sources.
- The payload classification matches the destination.
- The recipient/audience is permitted to view that data classification.
- Only necessary fields are serialized.
- The transaction has committed or an appropriate outbox mechanism is used.
- ACL/revocation policies are satisfied per contract.

### Data Classification Contract

| Classification | Example Destination | Primary Condition |
| --- | --- | --- |
| PUBLIC | `/topic/public` | DTO genuinely safe for the entire public audience |
| TENANT_PRIVATE | `/topic/tenants/a/updates` | Event belongs to tenant A and subscribers are authorized |
| ROOM_PRIVATE | `/topic/tenants/a/rooms/42` | Event belongs to room 42; room ACL applies |
| USER_PRIVATE | `convertAndSendToUser(recipient,...)` | Recipient and contents verified |
| UNKNOWN | Do not send | Default DENY, audit |

Never treat a client-sent classification label as proof. The server must classify based on verified resource facts and workflows.

### Illustrative Publisher Service

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class RoomEventPublisher {
    private final TrustedEventRepository events;
    private final PublishPolicy policy;
    private final SimpMessagingTemplate messaging;

    public RoomEventPublisher(
            TrustedEventRepository events,
            PublishPolicy policy,
            SimpMessagingTemplate messaging) {
        this.events = events;
        this.policy = policy;
        this.messaging = messaging;
    }

    public void publish(VerifiedServiceActor actor, long eventId) {
        RoomEvent event = events.findRequired(eventId);
        policy.requireCanPublish(actor, event);

        String destination = "/topic/tenants/" + event.tenantId()
            + "/rooms/" + event.roomId();

        RoomEventDto safeDto = new RoomEventDto(
            event.publicId(),
            event.displayText(),
            event.createdAt()
        );

        messaging.convertAndSend(destination, safeDto);
    }
}
```

This is a **component fragment**, not standalone runnable code: `TrustedEventRepository`, `PublishPolicy`, `VerifiedServiceActor`, `RoomEvent`, and `RoomEventDto` are application-implemented types. `event.tenantId()`/`roomId()` must come from the verified real resource, never trusting client-set headers or body fields.

Mistake to avoid:

```java
messaging.convertAndSend(request.destination(), request.payload());
```

Here a client can steer content into sensitive topics or someone else's topic. Replace it with a server-determined destination derived from trusted facts.

## 8. Outbound Data Must Have the Right Recipient and Right Fields

Two distinct bugs:

1. **Wrong routing:** Bob does not belong to room42, yet the broker lets Bob subscribe to room42.
2. **Wrong content:** Alice legitimately belongs to room42, yet the publisher pushes a record belonging to Bob/tenant B onto that topic.

Guard the first with subscription ACLs and broker isolation. Guard the second with domain/publisher policies, DTO projections, and properly scoped source queries.

An entity might contain:

```text
id, tenantId, ownerId, title, description,
privateNotes, accessToken, internalFlag, salary
```

Even if the frontend does not display `privateNotes`, the serializer can still transmit that field if the server passes the full entity. Use a minimal DTO containing only permitted attributes.

When field-level access varies across subscribers, consider **per-user fan-out** or pushing only a minimal ID and requiring clients to call a REST detail API enforcing object-level authorization.

## 9. User Destinations Do Not Automatically Solve Payload Permissions

Client:

```text
SUBSCRIBE
id:personal
destination:/user/queue/notifications
```

Server:

```java
messagingTemplate.convertAndSendToUser(
    verifiedRecipientName,
    "/queue/notifications",
    safeNotification);
```

Spring Framework resolves the user destination to a per-user/per-session queue. When a user has multiple sessions, messages sent by username can reach multiple sessions; `@SendToUser(broadcast = false)` can be used when targeting a single session inside a message handler.

Risks:

- Sending Bob's private data into Alice's queue.
- Using colliding usernames across tenants/IdPs when the system needs a stable subject.
- Clients subscribing directly to raw `/queue/**` instead of `/user/queue/**`.
- A session scoped to a different tenant with the same username receiving an inappropriate event.
- Broker queues retaining messages after logout/revocation.
- Multi-node user destinations out of sync or unresolved destinations.

**Routing to the right user queue does not prove the data belongs to that user.** Policies must verify recipient–resource–action.

## 10. Revoking Permissions After a Subscription Already Exists

Example:

```text
10:00 Alice SUBSCRIBE room42: ALLOW
10:05 Broker holds active subscription Alice-room42
10:10 Admin revokes Alice membership
10:11 Server publishes room42 event
```

Spring Security does not automatically repeat inbound authorization on every outgoing frame. If the subscription has not been removed, Alice can still receive the message.

Strategies:

| Strategy | How It Works | What to Check |
| --- | --- | --- |
| Disconnect/unsubscribe | Actively terminate revoked sessions/subscriptions | User-session map and multi-node sync |
| Subscription lease | Bound TTL, require grant renewal | Staleness within the TTL window |
| Grant/policy epoch | Invalidate old subscriptions when ACL changes | Consistent version propagation |
| Publish-time recipient check | Select only users still holding grants | Load/p99 latency and TOCTOU |
| Per-user fan-out | Send individually to recipient list from trusted ACL | High message count and cost |
| Minimal push + fetch | Push only ID; detail GET re-checks | Metadata still needs protection |

An expired JWT **does not automatically** close an open WebSocket unless the app implements session expiry/re-authentication. To make revocation take effect within a defined timeframe, design and test that SLA.

### TOCTOU Race

Can happen:

```text
T1 publisher: check Alice grant = true
T2 admin: revoke Alice grant
T1 broker: deliver message
```

No single check automatically guarantees atomicity across the database, application nodes, broker, and socket. Define a contract for check timing, ordering/epochs, or acceptable delay.

## 11. Emission Sources Outside clientInboundChannel

Code paths that can emit messages without passing through a new inbound STOMP SEND:

- HTTP controller handling POST.
- Scheduled job.
- Kafka/RabbitMQ consumer.
- Transactional outbox relay.
- Application event listener.
- Database change stream.
- Admin tool or internal service.
- External STOMP broker publisher.

Thus if permissions live only on `@MessageMapping`, a cron job can still bypass them. Put publication policy inside **a shared domain/publisher service** or equivalent trust boundary.

### Background Jobs Do Not Automatically Have an HTTP Principal

Never read `SecurityContextHolder.getContext()` in a worker thread and assume it represents the user who requested the work. Distinguish **verified service actor**, **initiating user** (if proven), and **resource tenant/owner**. `initiatedBy=alice` in an event body does not create delegated user permission by itself.

### Transactions and Outbox

A publisher emitting an event before DB commit can announce nonexistent data if the transaction rolls back. Use transactional outbox, after-commit hooks, or idempotent workflows depending on architecture. Never rely on post-publish checks to recall an already-sent message.

## 12. External Broker Relays and Bypass Paths

When using RabbitMQ/ActiveMQ or a STOMP relay:

```text
Client -> Spring clientInboundChannel -> Spring message security
       -> Broker relay -> External broker
       -> Spring clientOutboundChannel -> Client
```

If the broker exposes public/direct connections, a client or another integration can subscribe/publish **without going through Spring inbound security**. Protect at the broker/network layer:

- TLS and broker authentication.
- Destination ACLs.
- Least-privilege service credentials.
- No unauthorized open management/queue endpoints.
- Retention, durable subscriptions, and replay policies.
- Network isolation and rate limits.
- Multi-node user destinations and revocation propagation.

Never assume an external broker knows your application's domain owner/tenant ACLs.

## 13. Is a Custom Outbound Interceptor the Default Solution?

Spring Messaging provides `ChannelInterceptor` for customizing outbound processing. However, **standard Spring Security WebSocket message authorization does not provide a general authorization manager for every outgoing message**.

If writing a custom outbound checker, you must solve:

- How to obtain the right user/session/resource context?
- A single incoming event can fan out into 10,000 outgoing deliveries; will it execute 10,000 queries?
- Can queues, thread pools, and slow clients handle the load?
- Was the event already published into the broker/buffer before the checker ran?
- Does the interceptor run across every path/relay/node?
- Once bytes leave the server, they cannot be recalled.

Designs may use outbound interception as defense in depth, yet **never loosen inbound subscriptions or publishers hoping an interceptor will rescue them**.

## 14. Ordering, Buffers, and Revocation

Per Spring Framework, inbound/outbound channels use executors; messages may be processed or received out of publish order in certain setups. `setPreserveReceiveOrder(true)` and `setPreservePublishOrder(true)` exist when per-session ordering is required, at some performance cost.

These flags **are not authorization primitives**. They do not synchronize across:

```text
DB revoke -> Kafka event -> node A -> node B -> broker queues -> clients
```

If tenant A revokes a subscription on node A, node B may keep publishing events before receiving the notice. You need permission consistency management, revocation epochs, queue purging, or an explicit SLA.

Slow consumers can hold buffered private messages longer than expected; test latency, send time limits, message sizes, subscription counts, and broker retention.

## 15. Standalone Java 17: Proving Subscription Permission Differs from Data Delivery

This example uses pure Java 17 without Spring/JWT/brokers. It simulates SUBSCRIBE, SEND, publisher source checks, and delivery decisions when an ACL is revoked.

Create `InboundOutboundBoundaryDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class InboundOutboundBoundaryDemo {
    static final String PUBLIC = "/topic/public";
    static final String ROOM_A = "/topic/tenants/a/rooms/42";
    static final String ROOM_B = "/topic/tenants/a/rooms/77";

    record User(String id, boolean authenticated) {}
    record Subscription(String userId, String destination) {}
    enum Visibility { PUBLIC, ROOM }

    static boolean maySubscribe(
            User user, String destination, Set<String> grants) {
        if (user == null || !user.authenticated()) {
            return false;
        }
        return PUBLIC.equals(destination)
            || grants.contains(user.id() + "|" + destination);
    }

    static boolean maySend(User user, String destination) {
        return user != null && user.authenticated()
            && "/app/chat.send".equals(destination);
    }

    static boolean mayPublish(
            Visibility classification, String destination,
            String expectedRoom) {
        return switch (classification) {
            case PUBLIC -> PUBLIC.equals(destination);
            case ROOM -> expectedRoom != null
                && expectedRoom.equals(destination)
                && destination.startsWith("/topic/tenants/");
        };
    }

    static void subscribe(
            List<Subscription> active,
            User user, String destination, Set<String> grants) {
        if (maySubscribe(user, destination, grants)) {
            active.add(new Subscription(user.id(), destination));
        }
    }

    static List<String> recipients(
            List<Subscription> subscriptions,
            String destination, Set<String> grants,
            boolean checkCurrentGrants) {
        return subscriptions.stream()
            .filter(s -> s.destination().equals(destination))
            .filter(s -> !checkCurrentGrants
                || PUBLIC.equals(destination)
                || grants.contains(s.userId() + "|" + destination))
            .map(Subscription::userId)
            .distinct()
            .sorted()
            .toList();
    }

    static String label(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        User alice = new User("alice", true);
        User bob = new User("bob", true);
        User carol = new User("carol", true);
        User guest = new User("guest", false);

        Set<String> grants = new HashSet<>();
        grants.add("alice|" + ROOM_A);
        grants.add("bob|" + ROOM_B);

        System.out.println("Alice room A SUBSCRIBE: "
            + label(maySubscribe(alice, ROOM_A, grants)));
        System.out.println("Bob room A SUBSCRIBE: "
            + label(maySubscribe(bob, ROOM_A, grants)));
        System.out.println("Guest public SUBSCRIBE: "
            + label(maySubscribe(guest, PUBLIC, grants)));
        System.out.println("Alice broker SEND: "
            + label(maySend(alice, PUBLIC)));
        System.out.println("Alice app SEND: "
            + label(maySend(alice, "/app/chat.send")));

        List<Subscription> active = new ArrayList<>();
        subscribe(active, alice, PUBLIC, grants);
        subscribe(active, bob, PUBLIC, grants);
        subscribe(active, carol, PUBLIC, grants);
        subscribe(active, alice, ROOM_A, grants);
        subscribe(active, bob, ROOM_B, grants);

        System.out.println("Public recipients: "
            + recipients(active, PUBLIC, grants, false));
        System.out.println("Room A recipients: "
            + recipients(active, ROOM_A, grants, false));
        System.out.println("Private event on public topic: "
            + label(mayPublish(Visibility.ROOM, PUBLIC, ROOM_A)));

        grants.remove("alice|" + ROOM_A);

        System.out.println("Old subscription after revoke: "
            + recipients(active, ROOM_A, grants, false));
        System.out.println("Rechecked delivery after revoke: "
            + recipients(active, ROOM_A, grants, true));
        System.out.println("Room publisher destination: "
            + label(mayPublish(Visibility.ROOM, ROOM_A, ROOM_A)));
        System.out.println("Public publisher destination: "
            + label(mayPublish(Visibility.PUBLIC, PUBLIC, null)));
    }
}
```

Compile and run:

```bash
javac InboundOutboundBoundaryDemo.java
java InboundOutboundBoundaryDemo
```

Exact stdout:

```text
Alice room A SUBSCRIBE: ALLOW
Bob room A SUBSCRIBE: DENY
Guest public SUBSCRIBE: DENY
Alice broker SEND: DENY
Alice app SEND: ALLOW
Public recipients: [alice, bob, carol]
Room A recipients: [alice]
Private event on public topic: DENY
Old subscription after revoke: [alice]
Rechecked delivery after revoke: []
Room publisher destination: ALLOW
Public publisher destination: ALLOW
```

Explanation:

- Alice holds the room grant; Bob holds only room B's grant.
- Direct SEND to the broker prefix is denied, even though Alice can send application commands.
- All authenticated users can receive public events.
- Private room events cannot be published to the public destination.
- Revocation updates only the ACL source and does not automatically remove registered subscriptions; without re-checking, Alice remains in the recipient set.
- Checking current grants at delivery excludes Alice, or the application can close the session/cancel the subscription.
- The code is an in-memory simulation and **does not** execute Spring `MessageChannel`s, STOMP frames, JWT, CSRF, R2DBC, or external brokers. Production must verify event sources, DTO fields, user/tenant/resource, timeouts, and consistency.

## 16. Testing Inbound Properly

Build a fixture with Spring Messaging:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

SimpMessageHeaderAccessor headers =
    SimpMessageHeaderAccessor.create(SimpMessageType.SUBSCRIBE);
headers.setDestination("/topic/public");
headers.setLeaveMutable(true);

Message<byte[]> subscribe = MessageBuilder.createMessage(
    new byte[0], headers.getMessageHeaders());
```

This is a JUnit fragment; it requires the manager and an `Authentication` fixture. Depending on version, invoke `authorizationManager.authorize(() -> auth, subscribe)` and check `isGranted()`.

| Inbound message | Expectation |
| --- | --- |
| SEND `/app/chat.send`, with CHAT_SEND | ALLOW |
| SEND `/topic/public` | DENY |
| SEND `/topic/system` | DENY |
| SUBSCRIBE `/topic/public`, authenticated | ALLOW |
| SUBSCRIBE private room, active membership | ALLOW per custom policy |
| SUBSCRIBE private room, wrong tenant | DENY |
| SUBSCRIBE raw `/queue/other-session` | DENY |
| SUBSCRIBE unknown destination | DENY |
| CONNECT missing/invalid CSRF under required policy | Disallow business messaging |

These tests prove only the **inbound manager**; they do not verify what content the server emits.

## 17. Testing Outbound: Unauthorized Users Must Not Receive Events

A WebSocket/STOMP integration test should run a real server or Spring channels/broker test harness with Alice/Bob/Carol, two tenants, and multiple rooms. Verify:

1. Bob receives no room42 events even if he attempts to SUBSCRIBE.
2. `ROOM_PRIVATE` events are never published to `/topic/public`; `convertAndSend` is never invoked.
3. Alice receives only the safe DTO, without out-of-scope `privateNotes`/tokens/salary.
4. The app never sends Bob's data into Alice's user queue.
5. After revocation, Alice's open socket receives no new events per SLA, and re-subscribing is DENIED.
6. Producers from cron, HTTP, and Kafka/outbox pass through the same publisher policy.
7. An external broker forbids direct subscribe/publish bypassing Spring.
8. Broker replay, multi-node, and reconnects never resend unauthorized data.
9. Transaction rollbacks emit no event claiming committed state.
10. Slow-client/outbound buffers are bounded without breaking tenant isolation.

### Standalone Publisher Test

```text
Given:
  event.kind = ROOM_PRIVATE
  event.tenant = tenant-a
  event.room = room42
  destination proposed = /topic/public
When:
  publisher.publish(event)
Then:
  DENY
  SimpMessagingTemplate.convertAndSend not called
  audit.reason = DESTINATION_CLASSIFICATION_MISMATCH
```

Do not assert only HTTP 101 or STOMP CONNECTED. After Upgrade, a STOMP failure may appear as an ERROR frame or connection close; verify **recipients, exact payload, absence of sensitive messages, and side effects**.

## 18. Observability, Performance, and Privacy

Relevant metrics:

- Inbound ALLOW/DENY by message type and destination template.
- Active subscriptions by tenant/room/user (with safe cardinality).
- Blocked publishes due to classification/tenant/recipient mismatch.
- Revocation propagation latency.
- Outbound queue depth, slow consumers, and broker latency.
- Unintended deliveries caught in security tests.
- Permission DB/PDP timeouts and invalidation errors.

Cap connections, subscriptions, frame size, SEND rate, memory, and broker retention. If one event fans out to 10,000 subscribers, querying ACLs individually per delivery can be prohibitively expensive; consider subscription leases, indexed/batched grants, or bounded per-user fan-out.

Audit logs should include event ID, caller kind, verified tenant, resource type, policy version, destination template, decision, and reason; never log raw JWTs, STOMP CSRF tokens, private payloads, or cookies.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming inbound manager protects outbound | Data leak despite valid subscriptions | Publisher/data/audience policy |
| Protecting only the HTTP handshake | SEND/SUBSCRIBE lack guards | STOMP AuthorizationManager |
| Allowing direct SEND to broker topics | Server spoofing | Deny broker-prefix SEND |
| Allowing SUBSCRIBE to any room via authenticated | Cross-room/tenant BOLA | Room membership ACL |
| Trusting payload `destination`/`senderId` | Arbitrary routing/identity spoofing | Verified Principal and resource facts |
| Publishing raw entities | Sensitive field leakage | Safe DTO |
| Assuming user queue protects payload | Recipient mismatch | User/resource/payload policy |
| Revoking while keeping old subscriptions | Stale delivery | Disconnect/invalidate/recheck |
| Assuming JWT expiry closes the socket | Old session stays alive | Session lifetime strategy |
| Broker relay permits direct client access | Bypasses Spring inbound | Broker ACL/network |
| Background job calls broker outside policy | Bypasses domain authorization | Shared publisher service |
| Emitting events before transaction commit | Incorrect state/event | Outbox/after-commit |
| Replaying private events after revocation | Historical data leak | Replay authorization |
| Testing only HTTP status/CONNECTED | Misses outbound leaks | Assert absent recipients/messages |
| Unbounded ACL queries on every outbound | Fan-out overload | Batch/lease/index/limits |

## 20. Pre-Production Checklist

- [ ] Distinguish `clientInboundChannel`, `brokerChannel`, and `clientOutboundChannel`.
- [ ] Enforce authentication and Origin/CSRF policies for handshake/CONNECT.
- [ ] Inbound message manager separates SEND and SUBSCRIBE, with default DENY.
- [ ] Deny client SEND to `/topic/**` and raw `/queue/**`.
- [ ] Private SUBSCRIBEs enforce verified tenant/room/object ACLs.
- [ ] Publisher verifies event source, classification, audience, and destination.
- [ ] Never trust unverified `senderId`, `recipientId`, `tenantId`, or `destination`.
- [ ] Send only DTOs with approved fields; never publish raw entities.
- [ ] Enforce user-specific routing and verify content for the recipient.
- [ ] Background jobs, HTTP handlers, and Kafka/outbox share the same domain policy.
- [ ] Have a revocation plan covering live subscriptions and multi-node deployments.
- [ ] External broker enforces TLS/authentication/destination ACLs.
- [ ] Test stale sessions, broker replay, wrong audience, and wrong tenant.
- [ ] Negative tests prove unauthorized clients **receive no messages**.
- [ ] Logs/metrics contain no credentials or private payloads.

**Conclusion:** `clientInboundChannel` is where Spring Security checks **STOMP commands from clients**, whereas `clientOutboundChannel` is the path where the broker/server delivers **data** to clients and standard message authorization does not automatically re-check every frame. Therefore, you must protect **both SUBSCRIBE permissions and emission sources, destinations, payloads, recipients, revocation, and broker trust boundaries**. A valid connection or subscription does not automatically authorize all data emitted later.

## Official References

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): inbound-only enforcement, SEND vs. SUBSCRIBE, user destinations, CSRF.
- [Spring Security API — MessageMatcherDelegatingAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.html): message authorization API.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): the three channels and message routing.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): per-user/per-session and multi-node behavior.
- [Spring Framework — Ordered Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): message ordering and executors.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): external broker boundary.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): resource limits.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): message authorization, lifecycle, and privacy.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege and deny-by-default.
