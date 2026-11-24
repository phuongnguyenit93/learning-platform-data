# Session Principal and Trust Limits of Client-Sent Headers

## 1. The Problem to Solve

In a **Spring Security message authorization** system, a browser or mobile client opens a WebSocket and sends STOMP frames to the server. For example, a client connects to `/ws` and sends:

~~~text
CONNECT
login:root
passcode:anything
X-User-Id:admin
X-Tenant:finance
X-Role:SUPER_ADMIN

^@
~~~

Then the client continues:

~~~text
SEND
destination:/app/chat.send
X-User-Id:admin
X-Tenant:finance
X-Role:SUPER_ADMIN
content-type:application/json

{"roomId":"private-room","sender":"admin","text":"Approved"}^@
~~~

The `^@` notation in documentation merely represents the STOMP frame terminator character; it is not a literal character string to send verbatim. These client-sent headers and JSON **do not prove the caller is admin**. If the application uses `X-User-Id`/`sender` as the sender, or trusts `X-Role` to permit sending/subscribing, an attacker can **impersonate** others and read or emit messages without authorization.

The right boundary:

> **The session Principal must come from trusted authentication; client-sent STOMP headers and payloads are merely input data. Every SEND/SUBSCRIBE must verify the authenticated subject, message type, destination, and permissions on the specific room/tenant/resource.**

This lesson belongs to **Message Authorization**, focusing on **Spring Framework STOMP over WebSocket + Spring Security Messaging**, covering the HTTP handshake mechanism, `simpUser`, token authentication on `CONNECT`, `ChannelInterceptor`, `@EnableWebSocketSecurity`, permissions by message type/destination, user destinations, and limits of trusting headers.

This is not a lesson on pure HTTP REST APIs, pure AMQP/JMS broker auth, or raw WebFlux `WebSocketHandler`. The trust-boundary ideas apply broadly, yet the code APIs below target **Spring WebSocket/STOMP on the Servlet stack** per the official Spring Security documentation.

## 2. Learning Objectives

After this lesson, you will be able to:
- Distinguish **HTTP handshake**, **WebSocket session**, **STOMP CONNECT**, **SEND**, **SUBSCRIBE**, **MESSAGE**, and broker output.
- Understand how Spring obtains the `Principal` from an authenticated HTTP request and binds it to the WebSocket/STOMP session.
- Recognize the difference between client-written **native STOMP headers** and the **server-managed `simpUser` header**.
- Explain why `login`/`passcode` or `Authorization` in STOMP CONNECT are not automatically treated by Spring as authentication.
- Deliberately choose between HTTP/session authentication and JWT Bearer at STOMP CONNECT.
- Register a custom authentication `ChannelInterceptor` and order it before Spring Security's authorization interceptors.
- Configure `AuthorizationManager<Message<?>>` for inbound messages with deny-by-default.
- Prevent users from sending `SEND` directly to `/topic/**` or subscribing directly to `/queue/**` without authorization.
- Protect `/user/queue/**` and understand user-destination resolution.
- Check tenant, room membership, and READ/SEND permissions on every SEND/SUBSCRIBE without trusting `roomId`/`sender` in JSON.
- Analyze Origin, Same-Origin, CONNECT CSRF, SockJS, reconnect, logout, and revocation.
- Distinguish a connection's principal from permissions that can change during a long-lived session.
- Build a header-spoofing attack test matrix and a standalone Java 17 demo to verify the policy.

## 3. Map of the STOMP-over-WebSocket Flow

~~~text
Browser / STOMP client
       |
       | HTTP GET /ws + Upgrade / SockJS transport
       v
Spring Security HTTP filter chain
       | authentication: session cookie / HTTP auth / gateway policy
       | verified HttpServletRequest.getUserPrincipal()
       v
WebSocket handshake -> established WebSocket session
       | Principal associated with session
       v
STOMP CONNECT frame
       | default: Spring trusts HTTP-authenticated session Principal
       | optional: custom CONNECT token auth interceptor (verify token!)
       v
clientInboundChannel
       | security context + AuthorizationManager<Message<?>>
       | differentiate CONNECT, SUBSCRIBE, SEND, DISCONNECT
       v
@MessageMapping controller / application service
       | verified actor, room tenant, membership, object policy
       v
brokerChannel -> simple broker / external broker relay
       |
       v
clientOutboundChannel -> WebSocket subscribers
~~~

This is a conceptual diagram of components and trust boundaries, not an absolute ordering of every custom interceptor/transport. Current Spring Security Messaging primarily secures **`clientInboundChannel`**; it does not re-check every message on `clientOutboundChannel` by default. Hence SUBSCRIBE permissions and destination publishing must be tightly designed.

**Important:** transport-level WebSocket connection and STOMP `CONNECT` are two distinct events. The HTTP handshake may already be authenticated before STOMP `CONNECT`. The CONNECT frame carries client-supplied native headers. Do not conflate them into a single piece of evidence.

## 4. What Is a Principal Really?

In Java, `java.security.Principal` represents an identity with `getName()`. Spring Security typically provides `Authentication extends Principal`, carrying authorities, credentials, details, and authentication state in addition to the name.

Example:
~~~text
HTTP authenticated user:
  issuer = issuerA
  subject = an
  principal name = issuerA|an
  authorities = [ROLE_USER, SCOPE_chat.send]

WebSocket session:
  id = 9fe2...
  Principal = verified Authentication of issuerA|an

STOMP SEND:
  native header X-User-Id = admin (client-controlled)
  simpUser = Authentication of issuerA|an (server-managed)
~~~

Business logic must use the **principal supplied by the framework or a trusted authentication interceptor**, never the native `X-User-Id` header. Likewise, do not take an arbitrary `Principal.getName()` as proof of room access: tenant- and action-scoped membership/ACLs are required.

A principal name may be a username, internal actor ID, or another representation; do not assume usernames are unique across issuers. With multi-issuer OAuth2, use a canonical actor key `(validated issuer, sub)`.

## 5. HTTP Handshake Attaches the Principal to the WebSocket Session

According to the Spring Framework STOMP authentication documentation:
1. A STOMP-over-WebSocket session begins with an HTTP request (Upgrade or SockJS transport).
2. If Spring Security has authenticated the HTTP request, `HttpServletRequest#getUserPrincipal()` represents the trusted actor.
3. Spring Framework associates that Principal with the WebSocket/SockJS session.
4. When processing STOMP frames from that session, Spring populates user information in a server-managed header and exposes the `Principal` parameter to controllers.

Handler example:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ChatIdentityController {

    @MessageMapping("/whoami")
    public String whoAmI(Principal principal) {
        if (principal == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Authenticated session required");
        }
        return principal.getName();
    }
}
~~~

This is a **Spring integration snippet**, requiring STOMP endpoint setup, broker/application prefixes, inbound message security, and a client receiving results. The return value of `@MessageMapping` is sent to a destination per messaging convention, unlike a REST controller returning an HTTP body. Do not use a `whoami` endpoint as an alternate authorization mechanism.

With cookie sessions, protect HTTP login/session fixation/logout, `Secure`/`HttpOnly`/`SameSite` cookies, WebSocket Origin, and CONNECT CSRF. Never treat a long-lived socket as proof that permissions never change.

### HTTP Authentication Is Not Always Present

Native/mobile WebSocket clients, Bearer-only APIs, or browsers unable to attach custom Authorization headers at handshake time may not receive an HTTP-authenticated Principal. In those cases, you may need **token authentication in STOMP CONNECT via a custom interceptor**, or another trusted protocol. Never take identity from the `login` native header as a shortcut.

## 6. Native STOMP Headers Are Not a Security Context

A STOMP frame carries many native headers:
- `login`, `passcode`.
- Client-supplied `Authorization`.
- `X-User-Id`, `X-Role`, `X-Tenant-Id`.
- `destination`, `subscription id`.
- App-specific: `roomId`, `from`, `toUser`.

Every value can be altered by the client. Spring Framework **ignores STOMP protocol-level authentication headers by default** for STOMP over WebSocket, because it typically relies on HTTP handshake authentication. Specifically:
- `login=root` does not mean the server authenticated `root`.
- `passcode=secret` does not trigger Spring's `PasswordEncoder`.
- `Authorization: Bearer ...` in CONNECT is unverified without a custom token authentication mechanism.
- `X-Role=ADMIN` is plain text, not a `GrantedAuthority`.
- Server-managed message header `simpUser` may hold an `Authentication`; **never** let a same-named native STOMP header replace this value.

An anti-pattern:
~~~java
StompHeaderAccessor accessor =
        StompHeaderAccessor.wrap(message);
String role = accessor.getFirstNativeHeader("X-Role");
if ("ADMIN".equals(role)) {
    // BAD: caller controls X-Role.
    approveEverything();
}
~~~

**This is WRONG code shown for recognition**—never use it in production. Use `Authentication.getAuthorities()` after verification alongside a domain policy service.

## 7. Header Comparison Table

| Type | Example | Controlled By | Usable as Identity Proof? |
|---|---|---|---|
| HTTP handshake headers | Cookie, Authorization | Presented by client; verified by filters | Only **after** HTTP authn |
| STOMP CONNECT native | `login`, `passcode` | Client | Not by default |
| STOMP custom native | `X-User`, `X-Role`, `X-Tenant` | Client | **No** |
| STOMP destination | `/app/chat.send`, `/topic/rooms/7` | Chosen by client | No, only action/target |
| STOMP body | `senderId`, `roomId` | Client | No |
| Server-managed `simpUser` | Principal/Authentication | Framework or trusted interceptor | Yes, **if** trust boundary is protected |
| `simpSessionId` | Transport session ID | Framework | Not a resource permission |
| Session attributes | Session-scoped map | Stored by server; may originate from request | Trust only attributes with clear provenance/validation |
| Broker output headers | Broker-generated destination/metadata | Server/broker | Does not replace resource permissions |

**A header named "authenticated" proves no authenticity.** Only an actually configured and executed authentication flow establishes trust. Copying raw STOMP native headers into the server-managed header map can break the trust boundary.

## 8. HTTP Authentication vs. STOMP CONNECT Authentication: Choosing a Model

Two common models:

### Model A — Authenticated HTTP/Session

~~~text
Login form/OIDC web login
     -> session cookie and SecurityContext
HTTP GET /ws
     -> Spring Security authenticated Principal
STOMP CONNECT
     -> user inherited from HTTP handshake
SEND/SUBSCRIBE
     -> message authorization + domain policy
~~~

Fits many session-based browser apps. Clients do not need to send usernames/passwords in STOMP. CONNECT CSRF and Origin restrictions are critical because browsers may automatically send cookies.

### Model B — Token Authentication at STOMP CONNECT

~~~text
HTTP /ws handshake (token may not be in HTTP headers)
STOMP CONNECT:
  Authorization: Bearer <token>
     |
     v
Trusted ChannelInterceptor
  -> JwtDecoder/AuthManager verifies token, issuer, audience, expiry
  -> constructs Authentication
  -> accessor.setUser(verifiedAuthentication)
     |
     v
Spring Security message authorization
     |
     v
SEND/SUBSCRIBE
~~~

Model B makes sense when browser STOMP clients cannot send custom HTTP handshake headers. However, **only the CONNECT frame presents the credential**; the interceptor must verify the token with trusted code rather than building an authenticated `UsernamePasswordAuthenticationToken` from unverified `sub`/`role` strings.

Pick the right model, design conflict resolution if both an HTTP handshake Principal and a CONNECT token are present, and test re-auth/reconnect. Never silently let account B's token **replace session A's Principal** without explicit intent and policy.

## 9. CONNECT Tokens: Why Is a ChannelInterceptor Needed?

Spring Framework guides STOMP token authentication in two steps:
1. The STOMP client sends an authentication header on CONNECT.
2. The server processes it in a `ChannelInterceptor` registered on `clientInboundChannel`, **verifies the token**, and calls `StompHeaderAccessor.setUser(authentication)`.

Crucially, **authenticate CONNECT once and bind the verified user to the session**; Spring Framework manages the user association for subsequent STOMP messages.

Below is a **Spring integration** example using a configured Spring Security `AuthenticationManager` to verify a Bearer token. This is not a standalone application:

~~~java
import java.security.Principal;
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.socket.config.annotation.ChannelRegistration;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompConnectAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final AuthenticationManager bearerAuthenticationManager;

    public StompConnectAuthenticationConfig(
            AuthenticationManager bearerAuthenticationManager) {
        this.bearerAuthenticationManager = bearerAuthenticationManager;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor == null
                        || accessor.getCommand() != StompCommand.CONNECT) {
                    return message;
                }

                List<String> values =
                        accessor.getNativeHeader("Authorization");

                if (values == null || values.size() != 1
                        || !values.get(0).startsWith("Bearer ")) {
                    throw new BadCredentialsException(
                            "Bearer token required at CONNECT");
                }

                String credential =
                        values.get(0).substring("Bearer ".length()).trim();
                if (credential.isBlank()) {
                    throw new BadCredentialsException(
                            "Empty Bearer token");
                }

                Authentication verified =
                        bearerAuthenticationManager.authenticate(
                            new BearerTokenAuthenticationToken(credential));

                if (verified == null || !verified.isAuthenticated()) {
                    throw new BadCredentialsException(
                            "Token authentication failed");
                }

                Principal httpPrincipal = accessor.getUser();
                if (httpPrincipal != null
                        && !httpPrincipal.getName().equals(
                                verified.getName())) {
                    throw new BadCredentialsException(
                            "HTTP/STOMP principal conflict");
                }

                accessor.setUser(verified);
                return message;
            }
        });
    }
}
~~~

**Integration constraints and conditions of this snippet:**
- `bearerAuthenticationManager` must have a real token-verifying provider, such as `JwtAuthenticationProvider` with proper `JwtDecoder`/issuer/audience validators. **Never use** a manager that builds an authenticated user from raw claims.
- `Authorization` is a client-sent native STOMP header: use it solely as a **credential to verify**, never trusting roles/tenant/other headers.
- This snippet assumes a token-at-CONNECT model. If using HTTP session-only, do not require a Bearer token on every CONNECT.
- Avoid storing raw tokens in session attributes, exceptions, or logs.
- The `Bearer ...` header string needs real input length caps, malformed-case handling, and rate limits. This code illustrates the trust boundary, not complete hardening.
- If the HTTP Principal and token Principal differ, the example chooses to **reject the conflict**. If a product allows identity switching, explicit protocol/session isolation and tests are required.
- Specific versions/configs may also need SecurityContext/authorities handling; only call `setUser` with a verified `Authentication` before proceeding to authorization.
- **Mandatory interceptor order:** Spring Framework recommends placing the authentication interceptor before Spring Security, using a separate `WebSocketMessageBrokerConfigurer` with `@Order(Ordered.HIGHEST_PRECEDENCE + 99)`. Do not assume registering in another bean automatically gets the right order.
- With `@EnableWebSocketSecurity`, Spring Security also requires CONNECT CSRF by default. A Bearer-only STOMP flow must coordinate CSRF/Origin protection **per version and threat model**; this code does not mean "Bearer automatically bypasses CSRF."

Never arbitrarily mutate Spring Security's `simpUser` in an interceptor running after authorization; identity must be established **before** permission decisions rely on it.

## 10. Why Not Read the Authorization Header and Decode the Token Yourself?

Wrong code:

~~~java
String bearer = accessor.getFirstNativeHeader("Authorization");
// WRONG: split JWT, Base64URL decode payload,
// extract "sub" and "roles" and build an authenticated=true Authentication.
~~~

A JWT can be re-encoded with `sub=admin` without a valid signature. Use `JwtDecoder` + trusted issuer/audience/timestamps/algorithm checks, or trusted OAuth2 opaque token introspection.

Even with real tokens:
- A signature may be valid while `aud` belongs to another API.
- An OIDC ID token may be a signed JWT yet is not an API access token.
- A token with `scope=chat.send` may not be allowed to post in room 42.
- Tenant roles can go stale when membership is revoked.
- Service account tokens differ from human user tokens.

**Do not equate** `setUser(new UsernamePasswordAuthenticationToken("admin",null,adminAuthorities))` with authentication: taking username/authorities from native headers creates a **forged principal**.

## 11. User Principal in @MessageMapping

Spring Messaging can inject `Principal` into a handler:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class ChatMessageController {

    private final ChatPermissionService permissions;
    private final SimpMessagingTemplate broker;

    public ChatMessageController(
            ChatPermissionService permissions, SimpMessagingTemplate broker) {
        this.permissions = permissions;
        this.broker = broker;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        if (principal == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Authenticated WebSocket principal required");
        }

        VerifiedRoom room =
                permissions.requireCanSend(principal, input.roomId());

        ChatEvent event = new ChatEvent(
                principal.getName(), room.id(), input.text());

        broker.convertAndSend(
                "/topic/rooms/" + room.id(), event);
    }
}
~~~

**Integration code**: `ChatInput`, `VerifiedRoom`, `ChatEvent`, and `ChatPermissionService` are domain types the application must implement; the class/field names here illustrate the contract. Prefer a canonical actor identity over username under multi-issuer setups. Spring config must map the `/app` application prefix so `SEND destination:/app/chat.send` reaches the handler.

**Key point:** `ChatInput` has no `fromUserId` as an authority. The actor is identified by the trusted `Principal`, and the real room is resolved via the permission service. If the body still carries `sender` for client UI needs, the server must ignore or cross-check it, never using it as the audit identity.

If `roomId` comes from the body, it is a **requested target** and must be queried by tenant and membership. Never publish straight to `"/topic/rooms/"+input.roomId()` prior to authorization.

## 12. Message Type: SEND Differs from SUBSCRIBE

STOMP uses multiple frame types:
- `CONNECT`: client opens the STOMP protocol session.
- `SUBSCRIBE`: client requests messages from a destination.
- `SEND`: client sends a message to a destination.
- `UNSUBSCRIBE`: cancels a subscription.
- `DISCONNECT`: closes the STOMP session.
- Heartbeat/control frames depending on transport.

Spring Security authorization can match message types:
- `SimpMessageType.MESSAGE` corresponds to inbound application messages (such as STOMP SEND).
- `SimpMessageType.SUBSCRIBE` matches subscriptions.
- `nullDestMatcher()` matches messages without a destination, such as CONNECT/UNSUBSCRIBE/DISCONNECT/heartbeat depending on the setup.

**Do not apply the same rule to every message based solely on destination.** A chat room may allow READ without allowing SEND. Subscribing to notifications may be allowed while direct client sends to that broker topic must be forbidden.

Table:
| Frame | Destination | Typically Required Permission |
|---|---|---|
| CONNECT | None | Appropriate Authentication/CSRF/Origin |
| SUBSCRIBE | `/user/queue/alerts` | Principal matching the session |
| SUBSCRIBE | `/topic/rooms/42` | READ membership of Room #42 |
| SEND | `/app/chat.send` | SEND permission on target Room |
| SEND | `/topic/system/alerts` | **DENY** for clients; only server may broadcast |
| SUBSCRIBE | `/queue/internal/**` | **DENY** unless a trusted mapping exists |
| SEND | `/app/admin.deleteRoom` | Admin role/action + tenant/resource policy |
| DISCONNECT | None | Lifecycle handling; produce no unauthorized side effects |

## 13. Spring Security @EnableWebSocketSecurity and AuthorizationManager

Spring Security 5.8+ introduced configuring message authorization via `AuthorizationManager<Message<?>>`. Example deny-by-default **coarse boundary**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
public class ChatMessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/user/queue/alerts")
                .authenticated()
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("SCOPE_chat.send")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

This is a **Spring Security Messaging integration snippet**, requiring Spring Security Messaging, a Spring WebSocket broker, and an appropriate authentication scheme. It enforces:
- CONNECT and control messages without a destination require authenticated (plus CONNECT CSRF when enabled).
- Users may SUBSCRIBE only to their session's `/user/queue/alerts`.
- SEND to `/app/chat.send` requires authority `SCOPE_chat.send`.
- All other SUBSCRIBE/MESSAGE frames are denied.
- All remaining messages are denied by fallback.

**Why not allow a blanket `/topic/rooms/**`?** A coarse `authenticated()` on private room topics **does not prove READ permission for a room**. For private room topics, add a room+tenant-aware matcher/policy, or deny subscribing until the backend checks subscriptions via a custom authorization manager. The example intentionally **denies** private topics lacking explicit policies.

`hasRole("USER")` checks authority `ROLE_USER`, whereas OAuth scopes normally map to `SCOPE_chat.send`, so use `hasAuthority(...)` with the exact string. Never trust a native `role=USER` header.

### Version Note

The matcher APIs `simpMessageDestMatchers` and `simpSubscribeDestMatchers` appear in Spring Security Messaging 6.5 and 7.x Javadocs. Older examples using `AbstractSecurityWebSocketMessageBrokerConfigurer`/SpEL expressions differ; when upgrading, check your Spring Security version, deprecations, and migration docs. Do not confuse message authorization `AuthorizationManager<Message<?>>` with WebFlux's `ReactiveAuthorizationManager<AuthorizationContext>`.

## 14. SUBSCRIBE to a Private Topic Must Check Room Membership

A destination:

~~~text
/topic/tenants/north/rooms/42
~~~

contains tenant and room IDs **chosen by the client**. A user with a real Principal who does not belong to Room #42 could still attempt to subscribe. You must verify:
1. The actor is authenticated from the session.
2. The requested tenant/room target has a valid format.
3. Room #42 exists in tenant `north` (within viewable scope).
4. The actor holds active membership / READ grant on the room.
5. The subscription destination uses an allowed prefix and message type.
6. Policy versioning/revocation and session subscription lifecycle are managed.

Pseudo policy:
~~~text
ALLOW_SUBSCRIBE_ROOM =
    authenticatedSessionPrincipal
    AND frame.type == SUBSCRIBE
    AND destination == verifiedRoomDestination(room)
    AND requestedTenant == verifiedRoom.tenant
    AND activeTenantMembership(actor, verifiedRoom.tenant)
    AND activeRoomMembership(actor, verifiedRoom.id)
    AND canReadMessages(actor, verifiedRoom.id)
~~~

**You cannot use** `X-Room-Member=true`, `X-Tenant=north`, or body `isOwner=true` as proof.

For broker topics carrying private data, the system must **block unauthorized SUBSCRIBEs before the broker begins delivering**. Spring Security primarily inspects inbound, so do not expect a default outbound interceptor to scrub sensitive data afterward.

## 15. SEND to an Application Destination Also Needs Resource Authorization

A user with `SCOPE_chat.send` can send to the application handler `/app/chat.send`. Yet a functional scope is not enough to SEND in every room.

Example:
~~~text
Verified Principal = issuerA|an
Authorities = [SCOPE_chat.send]

Client payload:
{
  "roomId": "room-of-other-tenant",
  "sender": "system",
  "text": "System announcement"
}
~~~

Coarse HTTP/message gates may PASS based on scope. The application service must:
- Obtain the actor from the verified Principal/Authentication.
- Fetch room metadata from a trusted repository.
- Check tenant membership and SEND permission.
- Check room status, muted/blocked/archived flags, and rate limits.
- Record `ChatEvent`'s sender using the verified actor, not the JSON field.
- Publish only after authorization and mutation/auditing succeed.

A malicious client might send STOMP `SEND destination:/topic/system/alerts`. That is why safe practice is to **deny client SEND to broker prefixes** such as `/topic/**` and `/queue/**`. The application server can publish after checking permissions; clients send only to `/app/**` and specifically granted routes.

## 16. /user Destinations Do Not Let Clients Pick Arbitrary Recipients

Spring Framework supports user destinations:
- Client subscribes to `/user/queue/alerts`.
- Server calls `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/alerts", payload)`.
- `UserDestinationMessageHandler` translates the destination to the matching session(s) (with transformed destination names to avoid collisions).

This is **user/session routing**, not an automatic permission system for every business object.

Example:
~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {
    private final SimpMessagingTemplate messaging;

    public NotificationPublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void sendVerifiedRecipient(String canonicalUsername,
                                      Object safePayload) {
        messaging.convertAndSendToUser(
                canonicalUsername, "/queue/alerts", safePayload);
    }
}
~~~

**Integration code**; the caller of `sendVerifiedRecipient` must resolve the recipient from a trusted domain policy and verify privacy. Never use a client-supplied `toUser` value as justification to send secrets to someone else; it is a **requested target** requiring policy approval.

If a user has multiple sessions, user destinations by default can deliver to multiple sessions of that same user; `@SendToUser(broadcast = false)` is one way to limit replies to the current session in the appropriate case. Do not assume messages go to only one browser tab unless the application is configured that way.

Block clients from subscribing directly to resolved broker queues, such as `/queue/alerts-user-session-123`, if doing so could bypass user-destination isolation.

## 17. Session ID Is Not a Shareable Credential

`simpSessionId` and the WebSocket session ID are identifiers attached by the framework to a connection. They are useful for logs, subscription mapping, and routing. However:
- A session ID does not prove an account has permission on a room.
- A client can send a string resembling a session ID in a native header; it has zero trust.
- Never use a session ID declared in the request body as an identity.
- Never let clients set the `simpUser` server header via direct message maps.
- On disconnect, clean up session state and subscriptions per lifecycle rules.
- A new session after reconnect must re-authenticate under the chosen mechanism.

If multiple WebSocket connections per user must be supported, the model must distinguish **actor identity** (potentially shared) from **session identity** (distinct per connection).

## 18. Distinguishing WebSocket Session, HTTP Session, and Bean Scope

| Concept | Lifecycle | Trustworthiness |
|---|---|---|
| HTTP session | Multiple HTTP requests per cookie/session | Depends on authentication provider and session policy |
| WebSocket session | One WebSocket connection; can be long-lived | Has authenticated Principal, yet permissions can change |
| STOMP subscription | One subscription on a session | Must be authorized separately per destination |
| Session attributes map | Server data attached to WebSocket session | Trust only fields written after validation |
| WebSocket-scoped bean | One bean per session when using this scope | Not an authorization proof by itself |
| Singleton service | Shared application-wide | Never store mutable `currentUser`/`currentTenant` |
| Message payload/native headers | One client-sent frame | Untrusted |

Spring Framework supports WebSocket-scoped beans via `@Scope(scopeName="websocket", proxyMode=...)`. Scope manages **lifecycle**, not role/owner verification. Never let a session bean carry stale `ADMIN` rights indefinitely without revalidation/revocation design.

A singleton `@Controller` or `@Service` **must never** store:
~~~java
private Principal currentPrincipal;
private String currentTenant;
~~~
and overwrite them on every frame. Concurrent sessions will mix identities. Pass Principal and resource scope through handler/service parameters or a trusted per-message/per-session context.

## 19. WebSocket Origin and Same-Origin: Easy to Misunderstand

Browsers **do not enforce the Same-Origin Policy on WebSockets like XMLHttpRequest/fetch**. Another site can open a WebSocket handshake to your server if the server allows it. When browsers automatically attach session cookies, **Cross-Site WebSocket Hijacking** risk arises.

Defense layers:
1. Restrict allowed origins on WebSocket endpoints (Spring Framework typically defaults to same-origin in the corresponding setup).
2. Keep CSRF tokens on STOMP CONNECT when supported by Spring Security Messaging, per version/flow.
3. Configure `Secure`, `HttpOnly`, and `SameSite` cookies properly.
4. Authenticate and authorize every message/destination.
5. Do not trust `Origin` as a role/tenant; non-browser clients can forge `Origin`.
6. Never enable `setAllowedOriginPatterns("*")` just to test connections when using session cookies.

In WebSocket config, it is standard to write:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.test");
~~~

which is a **transport snippet** used in `registerStompEndpoints(StompEndpointRegistry registry)`, requiring full imports/config. An Origin allowlist is a browser-oriented protection and never replaces authentication or tenant ACLs.

## 20. Spring Security CSRF Token in STOMP CONNECT

Spring Security WebSocket docs note that by default `@EnableWebSocketSecurity` requires a CSRF token on inbound `CONNECT` to enforce Same-Origin policy (especially for cookie-authenticated sessions).

Because SockJS browser clients may be unable to send custom HTTP headers on the transport, the token can be sent in **native STOMP CONNECT headers** using the name/value expected by CSRF support. The token must come from a legitimate channel and be verified by the server.

Flow:
~~~text
HTML/SPA fetches CSRF token from server after obtaining a valid session
        |
        v
STOMP CONNECT native header:
  X-CSRF-TOKEN: token-value
        |
        v
Spring Security Messaging CSRF check
        |
        v
Message authorization
~~~

**A CSRF token is not permission to read a room.** It prevents another site from abusing cookies; it does not verify that the user may subscribe to a private topic. Nor does CONNECT CSRF replace JWT/HTTP authentication.

Depending on Spring Security version, disabling or customizing WebSocket CSRF under `@EnableWebSocketSecurity` is restricted and may require manual component/XML configuration rather than a simple DSL toggle. Never copy HTTP `csrf().disable()` thinking it solves WebSocket CONNECT cleanly; check official docs and real integration tests.

## 21. SockJS and Tokens in URLs: Avoid Leaking Credentials

SockJS falls back across multiple HTTP requests and faces browser limits on custom headers. Putting a Bearer token in the query string:
~~~text
/ws?access_token=eyJ...
~~~
is dangerous because it can leak into access logs, reverse proxies, analytics, history, monitoring, or diagnostic URLs.

Options:
- HTTP/session authentication where possible.
- STOMP CONNECT token header + trusted authentication interceptor.
- A short-lived token mechanism dedicated to the WebSocket handshake, with clear audience/scope and replay/expiry checks, if the architecture requires it.
- Protect TLS/WSS and secrets; never hardcode tokens in client bundles.

Do not put refresh tokens in STOMP headers when only an access token is needed. Do not log full STOMP CONNECT frames when debugging. A valid token at CONNECT can still expire or be revoked during a long-lived session — a lifecycle policy is required.

## 22. Broker Relay login/passcode Is Not User Auth

When using an external STOMP broker relay, Spring may use `systemLogin/systemPasscode` for the system connection and `clientLogin/clientPasscode` for broker-side TCP connections. The broker relay attaches these credentials when forwarding CONNECT to the broker.

**Do not confuse** these with `login/passcode` sent by a browser client in a STOMP frame. By default Spring does not use those native headers to authenticate users at the application. Granting a shared broker account for the relay also does not replace per-end-user permissions in Spring Security Messaging.

Rules:
- User authorization must happen before the broker is permitted to deliver/receive.
- Store broker credentials in a secret store and rotate them.
- Clients must not SEND directly to broker prefixes or bypass the relay.
- External broker permissions are defense in depth, not a substitute for per-room/tenant ACLs.
- If the broker has any other public endpoint, lock down network access and auth for that endpoint.

## 23. Long-Lived Sessions: Permissions Can Change After CONNECT

Suppose:
~~~text
T0: An is HTTP-authenticated; WebSocket CONNECT succeeds.
T1: An is allowed to READ room #42 and SUBSCRIBEs.
T2: Admin revokes READ on room #42.
T3: Broker continues pushing messages to the existing subscription.
~~~

If authorization is checked only at T1, An may keep receiving messages until the session/subscription is terminated. The token signature at CONNECT can still be valid even after membership changes.

Define a policy:
- When does revocation take effect?
- Is there an active mechanism to **cancel the subscription/disconnect** when ACLs change?
- Are permissions re-checked before sensitive outbound publishing?
- Must high-privacy messages use per-recipient user destinations and filtered fan-out?
- How long is an ALLOW cache TTL or policy revision window?
- How is session/token expiration handled while a connection remains open?
- Are reconnects blocked if an account is disabled?

**Never promise instant revocation** merely because authentication was checked at CONNECT. With multi-subscriber streams, you may need a subscription registry and re-evaluation on policy changes. Spring Security primarily guards inbound, so this is an architectural responsibility when streaming sensitive data.

## 24. An Authenticated CONNECT Does Not Grant Every SUBSCRIBE

An actor with `ROLE_USER` is usually allowed to connect, yet:
- Does not necessarily have READ permission in every room.
- Does not have permission to SUBSCRIBE to admin events.
- Does not have permission to view another user's queue.
- Does not necessarily have permission to SEND announcements.
- Does not have permission to invoke a room deletion command.
- Must not skip tenant checks when `roomId` is in the destination.

A conservative policy:
~~~text
CONNECT: verified session + CSRF/Origin checks
SUBSCRIBE /user/queue/alerts: authenticated own-user destination
SUBSCRIBE private rooms: verified tenant + room READ permission
SEND /app/chat.send: scope/action + room SEND permission
SEND /topic/**: deny from client
SUBSCRIBE /queue/** directly: deny
Unknown frame/destination: deny
~~~

Deny-by-default ensures new routes do not open accidentally when adding message handlers. Test control frames CONNECT/UNSUBSCRIBE/DISCONNECT/heartbeat for your specific setup so lifecycle behavior is not broken.

## 25. Subscription Paths, Wildcards, and Encoded Destinations

Error-prone destination patterns:
- `/topic/rooms/*` is too broad for private rooms.
- `/topic/tenants/{tenant}/rooms/{room}`: tenant/room are client-requested path variables, not verified resources.
- `/user/queue/**`: a newly added queue holding sensitive data could lack its own dedicated policy.
- `/topic/**`: public and private topics sharing a prefix.
- Slash/dot separators or destination normalization differing by configured path matcher.

Verify:
1. Message type (SUBSCRIBE vs. SEND).
2. Destination matchers matching your Spring Security and Spring Messaging path matcher versions.
3. Path variables validated for format/length and resolved to real resource IDs.
4. Membership/ACLs against real resources, not wildcards.
5. Wildcard fallback deny.
6. Direct user-resolved queue subscriptions rejected.
7. Broker/application/user prefixes do not overlap or misroute.

Never build a policy "all authenticated users may SUBSCRIBE `/topic/**`" if topics carry private data. Never trust an `X-Subscription-Allowed: true` native header.

## 26. Authentication Principal and Per-Tenant Scope

A Principal may look like:
~~~text
issuerA|an
~~~
while user An has:
~~~text
tenant north: CHAT_READ, CHAT_SEND
tenant south: CHAT_READ only
~~~

If `Authentication` holds a global `SCOPE_chat.send`, that authorizes only the **action type** at the message authorization layer, not SEND across every tenant. The service must verify:
~~~text
ALLOW_SEND =
    verifiedPrincipal
    AND message.type == SEND
    AND destination == /app/chat.send
    AND general CHAT_SEND authority
    AND activeTenantMembership(principal, targetRoom.tenant)
    AND roomMembership grants SEND
    AND room.enabled && notMuted(principal)
~~~

A client may send `X-Tenant:south` or `role:owner`, which proves zero membership. Actor keys should also namespace issuer+subject when multiple OAuth issuers exist.

Do not treat a browser `sessionId` as a tenant-identifying token, since a single user may access multiple tenants across tabs/connections simultaneously. If tenant context is bound per session, tenant selection and verification at CONNECT must be strict, and every message must cross-check the destination/resource tenant.

## 27. Gateway-Injected Headers: When Can They Be Trusted?

A reverse proxy might authenticate and attach:
~~~http
X-Authenticated-User: an
X-Authenticated-Tenant: north
X-Authenticated-Roles: CHAT_SEND
~~~

If the backend WebSocket handshake can be reached directly, or if the proxy fails to strip client-sent headers, an attacker simply supplies them directly.

Trust proxy identity only when:
- There is no bypass path to the backend.
- The gateway authenticates credentials and checks audience.
- The proxy strips/overwrites incoming identity headers from the public network.
- The backend verifies request origin via mTLS/service identity/trusted signed context.
- Identity namespace, tenant scope, expiry, audience, and replay protections are checked.
- Tests hit the backend directly with forged identity headers and verify they are rejected.

**A header labeled "Verified" has no inherent verification value.** Just like STOMP's `simpUser`, distinguish client-supplied data from metadata created by Spring/the framework or a trusted interceptor.

## 28. Standalone Java 17: Proving Session Principal Beats Forged Headers

The snippet below **compiles/runs on JDK 17** without Spring. It simulates a server-authenticated session and server-owned room metadata. Client-supplied fields `claimedUser`, `claimedRole`, and `claimedTenant` are completely ignored in authorization. The goal is illustrating the trust boundary, not simulating the full STOMP protocol or JWT signatures.

Create `StompSessionTrustDemo.java`:

~~~java
import java.util.Set;

public class StompSessionTrustDemo {
    enum Type { CONNECT, SEND, SUBSCRIBE }

    record VerifiedSession(
            String sessionId,
            String actorKey,
            String tenant,
            Set<String> scopes) { }

    record Frame(
            Type type,
            String destination,
            String claimedUser,
            String claimedRole,
            String claimedTenant) { }

    record Room(
            String id,
            String tenant,
            Set<String> members,
            boolean locked) { }

    static String decide(
            VerifiedSession session, Frame frame, Room room) {

        if (session == null || session.actorKey() == null
                || session.actorKey().isBlank()) {
            return "DENY_NO_SESSION";
        }
        if (frame == null || frame.type() == null) {
            return "DENY_BAD_FRAME";
        }

        // STOMP native claims are deliberately never read.
        if (frame.type() == Type.CONNECT) {
            return "CONNECT_AS:" + session.actorKey();
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/user/queue/alerts".equals(
                    frame.destination())) {
            return "ALLOW";
        }

        if (frame.type() == Type.SEND
                && frame.destination() != null
                && (frame.destination().startsWith("/topic/")
                    || frame.destination().startsWith("/queue/"))) {
            return "DENY_BROKER_SEND";
        }

        String subscribeDest = room == null
                ? "" : "/topic/rooms/" + room.id();
        String sendDest = room == null
                ? "" : "/app/rooms/" + room.id() + "/post";

        boolean subscribe =
                frame.type() == Type.SUBSCRIBE
                && subscribeDest.equals(frame.destination());
        boolean send =
                frame.type() == Type.SEND
                && sendDest.equals(frame.destination());

        if (!subscribe && !send) {
            return "DENY_DESTINATION";
        }

        if (room == null || session.tenant() == null
                || !session.tenant().equals(room.tenant())) {
            return "DENY_TENANT";
        }

        if (!room.members().contains(session.actorKey())) {
            return "DENY_ROOM_MEMBERSHIP";
        }

        if (send && !session.scopes().contains("CHAT_SEND")) {
            return "DENY_SEND_SCOPE";
        }

        if (subscribe && !session.scopes().contains("CHAT_READ")) {
            return "DENY_READ_SCOPE";
        }

        if (send && room.locked()) {
            return "DENY_LOCKED_ROOM";
        }

        return "ALLOW";
    }

    public static void main(String[] args) {
        VerifiedSession an = new VerifiedSession(
                "session-an", "issuerA|an", "north",
                Set.of("CHAT_READ"));

        VerifiedSession carol = new VerifiedSession(
                "session-carol", "issuerA|carol", "north",
                Set.of("CHAT_READ", "CHAT_SEND"));

        Room room = new Room(
                "r7", "north",
                Set.of("issuerA|an", "issuerA|carol"), false);

        Room privateRoom = new Room(
                "r8", "north",
                Set.of("issuerA|carol"), false);

        Room southRoom = new Room(
                "r9", "south",
                Set.of("issuerA|an"), false);

        Frame connectSpoof = new Frame(
                Type.CONNECT, null, "admin", "SUPER_ADMIN", "south");
        Frame subRoom = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r7",
                "admin", "SUPER_ADMIN", "north");
        Frame subPrivate = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r8",
                "issuerA|carol", "ADMIN", "north");
        Frame sendRoom = new Frame(
                Type.SEND, "/app/rooms/r7/post",
                "admin", "SUPER_ADMIN", "north");
        Frame subSouth = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r9",
                "admin", "SUPER_ADMIN", "south");
        Frame brokerSend = new Frame(
                Type.SEND, "/topic/rooms/r7",
                "system", "SUPER_ADMIN", "north");
        Frame userQueue = new Frame(
                Type.SUBSCRIBE, "/user/queue/alerts",
                "admin", "SUPER_ADMIN", "north");
        Frame rawQueue = new Frame(
                Type.SUBSCRIBE, "/queue/alerts-foreign-session",
                "admin", "SUPER_ADMIN", "north");

        System.out.println("connect-spoofed-header="
                + decide(an, connectSpoof, room));
        System.out.println("member-subscribe="
                + decide(an, subRoom, room));
        System.out.println("spoofed-user-subscribe="
                + decide(an, subPrivate, privateRoom));
        System.out.println("spoofed-role-send="
                + decide(an, sendRoom, room));
        System.out.println("real-sender-send="
                + decide(carol, sendRoom, room));
        System.out.println("cross-tenant-subscribe="
                + decide(an, subSouth, southRoom));
        System.out.println("broker-send="
                + decide(carol, brokerSend, room));
        System.out.println("user-queue="
                + decide(an, userQueue, room));
        System.out.println("raw-queue="
                + decide(an, rawQueue, room));
        System.out.println("no-session="
                + decide(null, subRoom, room));
    }
}
~~~

Compile and run:

~~~bash
javac StompSessionTrustDemo.java
java StompSessionTrustDemo
~~~

Exact stdout:

~~~text
connect-spoofed-header=CONNECT_AS:issuerA|an
member-subscribe=ALLOW
spoofed-user-subscribe=DENY_ROOM_MEMBERSHIP
spoofed-role-send=DENY_SEND_SCOPE
real-sender-send=ALLOW
cross-tenant-subscribe=DENY_TENANT
broker-send=DENY_BROKER_SEND
user-queue=ALLOW
raw-queue=DENY_DESTINATION
no-session=DENY_NO_SESSION
~~~

Why these results matter:
1. The client claims `admin`, yet CONNECT still binds verified actor `issuerA|an`.
2. An can subscribe to `r7` because she has READ and membership.
3. An trying to spoof Carol's name to subscribe to `r8` is denied because her session identity is not in `r8`.
4. Native role `SUPER_ADMIN` does not grant An SEND permission.
5. Carol has `CHAT_SEND` and room membership, so SEND succeeds.
6. Room `south` does not match the `north` session's tenant.
7. Direct client SEND to the broker topic is blocked.
8. The session's own user destination is allowed; resolved/raw other queues are denied.
9. Without a verified session, there are no permissions, even with a well-formed frame.

**Model limits:** `VerifiedSession` is a trusted demo fixture; production must establish it from HTTP authentication or a CONNECT token verified for signature/issuer/audience/expiry. The demo also does not simulate CSRF, Origin, STOMP header internals, network brokers, username collisions, or post-subscribe revocation. Those require Spring integration tests.

## 29. Why Not Store the User in a ThreadLocal or Singleton?

A singleton handler may process frames from multiple WebSocket sessions concurrently:

~~~text
Thread T1: An's frame -> currentUser = An
Thread T2: Binh's frame -> currentUser = Binh
Thread T1: resumes processing -> reads currentUser = Binh
~~~

If a bean holds `private String currentUser`, identities can collide and messages can be sent under another actor. In Servlet/Spring Messaging, Spring Security's `SecurityContextChannelInterceptor` can synchronize `SecurityContext` on the inbound processing thread; apps should use `Principal`/`Authentication` in handlers rather than creating mutable global state.

With async tasks or scheduled workers, pass the verified context explicitly rather than assuming a `SecurityContext` `ThreadLocal` is always populated. With Reactor/WebFlux handlers, use Reactor Context/`ReactiveSecurityContextHolder` per stack rather than copying a Servlet `ThreadLocal` approach. Never subscribe or publish after authorization is denied.

## 30. Error Frames, Receipts, and Disclosure

A client may send unauthorized `SEND`/`SUBSCRIBE` frames. Spring Messaging/Security may return a STOMP ERROR, close the session, or throw `AccessDeniedException` depending on configuration.

Never send to clients:
- Room owner/ACL graphs or unauthorized memberships.
- Raw JWTs, cookies, or native CONNECT headers.
- Full `Authentication` objects and security exceptions.
- Internal broker topology or other users' queue/session IDs.
- Stack traces or detailed DB queries.

Instead:
- Log internal reason codes such as `STOMP_SUBSCRIBE_DENIED_ROOM`, `STOMP_SEND_DENIED_SCOPE`.
- Record a bounded actor alias/session correlation ID and tenant/resource type.
- Keep error messages minimal.
- Never let clients turn an error/receipt ID into proof.
- Separate CONNECT authn failures, message authorization denials, and policy backend outages.

A STOMP `receipt` is a protocol/broker processing acknowledgment per its semantics; **it is not proof** that the caller may view any content or that a business transaction committed unless the contract defines and verifies it as such.

## 31. Testing with WebSocketStompClient and Spring Security Messaging

A good end-to-end test needs:
1. HTTP handshake with authenticated principal A.
2. STOMP CONNECT carrying native `X-User-Id=B`/`X-Role=ADMIN`.
3. SUBSCRIBE to private room belonging to B → rejected.
4. SEND to application destination with valid scope/membership → permitted.
5. SEND to broker `/topic/**` → rejected.
6. SUBSCRIBE `/user/queue/alerts` → receives only that user/session's notifications.
7. SUBSCRIBE to another user's resolved queue → blocked.
8. CONNECT missing CSRF under cookie session auth → fails per config.
9. Token-auth CONNECT with wrong signature/issuer/audience → fails before message auth.
10. Reconnect with expired/revoked token → no trusted Principal.

Spring Framework provides `WebSocketStompClient`, `StompSessionHandler`, and STOMP test support. Use a real test client to verify session principals and interceptor ordering. Unit tests of `AuthorizationManager<Message<?>>` can build messages with trusted server headers yet **do not prove** handshake/token verification. Both layers are required.

**Mock Principal test ≠ authentication test.** If a test injects an `Authentication` with `ROLE_ADMIN`, it checks permissions, yet does not prove the server rejects native `X-Role=ADMIN` or invalid-signature JWTs.

## 32. Security Testing Matrix

| Scenario | Session Principal | Native Header/Payload | Required Outcome |
|---|---|---|---|
| HTTP session An, CONNECT claims user B | Verified An | `X-User=B` | Remains An |
| STOMP CONNECT with `login=admin` | Unauthenticated | login/passcode | Does not become admin |
| CONNECT Bearer JWT bad signature | Unauthenticated | Forged token | Reject |
| CONNECT Bearer JWT wrong audience | Unauthenticated | Other API's token | Reject |
| HTTP Principal An, CONNECT token Binh | Conflicting | Binh's token | Reject or explicit account-switch protocol |
| SUBSCRIBE own user queue | Verified An | `/user/queue/alerts` | Allow per policy |
| SUBSCRIBE Binh's raw session queue | Verified An | `/queue/alerts-B` | Deny |
| SUBSCRIBE room An is member of | Verified An | `/topic/rooms/r7` | Allow READ per domain policy |
| SUBSCRIBE someone else's room | Verified An | `X-IsMember=true` | Deny |
| SEND room An has scope, lacks SEND grant | Verified An | `X-Role=ADMIN` | Deny |
| SEND with payload `sender=system` | Verified An | Forged sender | Actor remains An; verify action |
| SEND `/topic/system/alerts` | Verified An | Broker prefix | Deny |
| SUBSCRIBE south tenant when north-only member | Verified An | `X-Tenant=south` | Deny |
| CONNECT from Origin outside allowlist | Has cookie | Forged Origin | Rejected by browser-origin policy |
| CONNECT without CSRF on cookie session | Verified An from HTTP | Missing token | Reject when CSRF enabled |
| SockJS token in query string | Unauthenticated | URL token | Avoid; never log credentials |
| Room ACL revoked after SUBSCRIBE | Verified An (long-lived) | Existing subscription | Cancel/revalidate per revocation policy |
| HTTP session revoked/logged out | Live WebSocket | Old session | Invalidate/disconnect per policy |
| Broker unavailable / PDP timeout | Possibly verified | Destination | Never fail open |
| Multi-issuer same sub | Verified issuerA|123 | User header 123 | Do not grant issuerB|123 permissions |
| Malformed destination | Verified An | Encoded/traversal | Reject/default deny |
| Denied SEND with DB side effects | Verified An | Bad room | No commit, no publish |
| New private topic without rule | Verified An | Unknown path | DenyAll |

For every denial, test that **no event is sent to the broker and nothing is written to the DB/outbox**, not merely that an ERROR frame appeared. For private topics, test that browser B receives none of A's messages via either direct queue or topic subscriptions.

## 33. Common Mistakes and How to Fix Them

**1. Trusting `login`/`passcode` in STOMP CONNECT as Spring authentication.** By default Spring ignores STOMP-protocol credentials. Use HTTP auth or a custom verified CONNECT interceptor.

**2. Taking `X-User-Id`/`sender` from STOMP headers/body as the Principal.** Clients can edit them. Use the server-managed Principal.

**3. Calling `accessor.setUser(...)` with an `Authentication` built from native claims.** That is privilege escalation. Only call `setUser` after verification via `AuthenticationManager`/`JwtDecoder`.

**4. Running a custom authentication interceptor after Spring Security.** Authorization sees null or a stale user. Order it before Spring Security, per docs `@Order(Ordered.HIGHEST_PRECEDENCE + 99)`.

**5. Having an HTTP handshake Principal overwritten by someone else's CONNECT token.** Reject conflicts or enforce an explicit re-auth model.

**6. Letting every authenticated user SUBSCRIBE `/topic/**`.** Leaks private rooms. Enforce room/tenant READ ACLs.

**7. Letting clients SEND directly to broker destination `/topic/**`.** Allows spoofing system messages. Block it and publish only from application handlers.

**8. Treating `/user/queue/**` as an unrestricted wildcard queue.** Block direct resolved `/queue/**` and check user-specific destinations.

**9. Treating `simpSessionId`/header `roomId` as proof.** IDs are metadata/targets, not permissions.

**10. Not checking the room's tenant from the database.** A user authorized for `north` could guess a `south` room.

**11. Checking only `CHAT_SEND` scope without checking room membership.** Functional scope is not object permission.

**12. Using global roles from a token lacking tenant context.** Tenant A rights can bleed into tenant B.

**13. Assuming WebSockets inherit browser Same-Origin enforcement like fetch.** Server-side Origin/CSRF policies are required.

**14. Dropping CONNECT CSRF for "easier connection" with cookie auth.** Can open Cross-Site WebSocket Hijacking.

**15. Putting access tokens in SockJS/WebSocket URLs.** Easily leaks via logs/proxies. Choose another auth channel.

**16. Authorizing only at CONNECT and not on SUBSCRIBE/SEND.** Connecting does not grant all actions.

**17. Revoking room ACLs while letting existing subscriptions receive messages forever.** Revocation propagation/disconnect/revalidation is needed.

**18. Assuming Spring Security filters outbound data on `clientOutboundChannel`.** The framework primarily guards inbound; protect subscribe/publish lifecycles.

**19. Storing `currentUser` in a singleton field.** Leaks context across sessions. Use per-message `Principal`.

**20. Testing with `mockUser` and believing native spoofing is blocked.** Integration tests with real handshakes, CONNECT, and headers are required.

## 34. Secure Deployment Checklist

- [ ] Confirm the stack is Spring Servlet STOMP WebSocket (do not confuse with WebFlux/raw WebSocket).
- [ ] Protect the HTTP handshake, or use a custom trusted token authentication interceptor at STOMP CONNECT.
- [ ] Obtain `Principal` from an HTTP-authenticated session or verified `AuthenticationManager`; never from native headers.
- [ ] If using CONNECT token auth, ensure the authentication interceptor runs before security message authorization.
- [ ] If both HTTP Principal and CONNECT token can appear, handle conflicts explicitly.
- [ ] Verify JWT/opaque token signature/issuer/audience/exp/typ/status per contract.
- [ ] Ensure native `login`, `passcode`, `X-User`, `X-Role`, `X-Tenant` grant zero privileges.
- [ ] Protect browser flows with cookies/Origin/CONNECT CSRF, and test SockJS separately.
- [ ] Configure `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>` for your exact version.
- [ ] Distinguish SEND/MESSAGE and SUBSCRIBE in rules, with fallback deny.
- [ ] Block clients from direct SEND to broker prefixes `/topic`, `/queue`.
- [ ] Block clients from subscribing to raw resolved queues outside user destinations.
- [ ] Expose data on `/user/queue/**` only per matching identity/authorization.
- [ ] Enforce custom policies on private topics for room/tenant READ membership.
- [ ] Verify permissions on real resources in SEND handlers before publishing.
- [ ] Ignore payload `sender`, `from`, `owner`, and `isAdmin` as identity proofs.
- [ ] Use canonical principal keys distinguishing issuer + subject when needed.
- [ ] Define clear propagation/lifecycle SLAs for permission revocation and session expiry.
- [ ] Never store mutable user/tenant in singletons or cache cross-session Principals.
- [ ] Test spoofed native headers, raw queues, direct topic SEND, and wrong-room SUBSCRIBE.
- [ ] Test invalid CONNECT tokens, interceptor order, CSRF/Origin, and multi-session isolation.
- [ ] Verify denied SEND/SUBSCRIBE produce no DB/broker side effects or data leaks.
- [ ] Keep structured audits free of tokens, cookies, or unauthorized private message payloads.

**Conclusion:** The WebSocket/STOMP session Principal must originate from **real authentication**, normally at the HTTP handshake or through a token-verifying `ChannelInterceptor` at STOMP CONNECT. Client-sent native headers are just data; `login=admin`, `X-Role=ADMIN`, or `sender=system` **never change the principal**. Spring Security Messaging then checks inbound SEND/SUBSCRIBE, while per-room and per-tenant read/write rights, broker publishing, user destinations, and long-lived session revocation must still be deliberately protected by the application.

## Official References

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): HTTP Principal inheritance, `@EnableWebSocketSecurity`, `AuthorizationManager<Message<?>>`, inbound security, broker prefixes, CONNECT CSRF.
- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): semantics for the 6.x line.
- [Spring Security — MessageMatcherDelegatingAuthorizationManager.Builder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `nullDestMatcher`, `anyMessage`.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): Principal from HTTP session, STOMP login/passcode ignored by default.
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): custom CONNECT token auth `ChannelInterceptor` and ordering before Spring Security.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): message authorization.
- [Spring Framework — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/`, user session routing, and `@SendToUser`.
- [Spring Framework — STOMP Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, Principal, and argument resolution.
- [Spring Framework — STOMP WebSocket Scope](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/scope.html): session attributes, websocket-scoped beans.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): broker/system client credentials vs. user auth.
- [Spring Framework — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html): Origin restrictions and browser semantics.
