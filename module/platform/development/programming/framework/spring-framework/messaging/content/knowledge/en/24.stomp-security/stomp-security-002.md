# Limitations of STOMP login and passcode in Spring Application Authentication

## Objectives and Scope

STOMP defines two headers, **login** and **passcode**, in the **CONNECT** frame. They are often misunderstood as the user login mechanism for the entire Spring application. In practice, authentication must be distinguished across three boundaries:

1. **Client → Spring WebSocket endpoint:** authenticates the application user and creates a **Principal** bound to the WebSocket session.
2. **STOMP CONNECT:** headers of the STOMP protocol. With STOMP over WebSocket in Spring, **login/passcode are ignored by default**; Spring assumes the user has already been authenticated at the HTTP layer.
3. **Spring broker relay → message broker:** the relay uses credentials configured on the server to authenticate TCP connections to the broker. This is the relay's broker identity, not automatically the application user's identity.

Therefore, merely adding login and passcode to the browser's connectHeaders does not cause Spring Security to authenticate the user. To authenticate at the STOMP layer, the application must actively read the credentials in the CONNECT frame, validate them, and attach an **Authentication/Principal** object to the message.

This document focuses on Spring Framework STOMP over WebSocket/SockJS, Spring Security, and the broker relay scenario. A STOMP client connecting directly over TCP to a broker may use login/passcode according to the broker's own authentication mechanism; that is a different flow from logging into a Spring application.

## 1. login and passcode in the STOMP protocol

### 1.1. Role of the two headers

A STOMP **CONNECT** frame may contain:

- **accept-version:** STOMP versions supported by the client.
- **host:** virtual host the client wants to connect to, depending on the broker.
- **login:** username that the broker or STOMP server may use for authentication.
- **passcode:** corresponding password or secret.
- **heart-beat:** proposed bidirectional heartbeat intervals.

Illustrative CONNECT frame example:

~~~text
CONNECT
accept-version:1.2
host:/
login:messaging-client
passcode:example-secret
heart-beat:10000,10000

^@
~~~

The values in the example are for illustration only. Do not store real passcodes in source control, documentation, logs, or debug captures.

### 1.2. What login/passcode do not do on their own

These headers do not by themselves define how Spring Security logs a user in, do not automatically create a SecurityContext, do not grant roles/authorities, and do not automatically authorize individual destinations.

STOMP is a messaging protocol. The exact meaning of credentials depends on the server receiving the CONNECT frame. A broker may use login/passcode to authenticate a broker account, whereas Spring WebSocket by default uses the Principal already present from the HTTP request.

In addition, login/passcode are a reusable pair of secrets. They are not a challenge-response mechanism or short-lived token. If sent over an unencrypted connection, anyone observing the traffic can capture the credentials. Use TLS/WSS on the relevant network hops and manage secrets securely.

## 2. Default model of Spring STOMP over WebSocket

### 2.1. Authentication at the HTTP handshake

A STOMP over WebSocket session starts with an HTTP request to upgrade to a WebSocket connection. With SockJS, a session may start with a sequence of HTTP transport requests.

In a typical Spring application, Spring Security authenticates the HTTP request first. For example, the user logs in via form login and a session cookie. When the WebSocket handshake occurs, HttpServletRequest#getUserPrincipal() returns the authenticated user. Spring binds that Principal to the WebSocket/SockJS session and attaches the user information to subsequent STOMP messages.

Default flow:

~~~mermaid
sequenceDiagram
    participant Browser
    participant SpringSecurity as Spring Security / HTTP
    participant WebSocket as Spring WebSocket
    participant App as STOMP application
    Browser->>SpringSecurity: HTTP handshake + session cookie
    SpringSecurity->>SpringSecurity: Authenticate HTTP user
    SpringSecurity->>WebSocket: Authenticated Principal
    Browser->>WebSocket: STOMP CONNECT
    WebSocket->>App: CONNECT with session Principal
    Browser->>WebSocket: SEND / SUBSCRIBE
    WebSocket->>App: Message stamped with Principal
~~~

Spring automatically associates the HTTP request's Principal with the WebSocket/SockJS session. Therefore, applications using cookie-based HTTP sessions normally do not need to re-authenticate the user using STOMP login/passcode.

### 2.2. Spring ignores login/passcode on WebSocket by default

The STOMP protocol has login and passcode headers, which were designed for STOMP connections such as STOMP over TCP. However, with STOMP over WebSocket, Spring by default **ignores authentication headers at the STOMP layer** and assumes the user has already been authenticated at the HTTP transport layer.

For example, a client sending:

~~~javascript
client.connectHeaders = {
    login: "alice",
    passcode: "secret"
};
~~~

does not cause Spring Security to automatically log in user alice. If the HTTP handshake has no Principal, adding those two headers does not create a Principal. If a token mechanism at CONNECT is needed, a ChannelInterceptor must be implemented as in section 5.

### 2.3. Benefits and limitations

The HTTP Principal model has the advantage of reusing existing web security mechanisms: sessions, form login, OAuth2 login, or HTTP authentication. The identity is attached once to the session and then used consistently for messages on that session.

The limitation is that the client must be able to carry credentials during the HTTP handshake. Cookie-based sessions work naturally with browsers. However, some mobile applications, clients without cookie sessions, or stateless applications may need a different authentication approach.

## 3. Distinguishing application authentication from broker relay authentication

When configuring **enableStompBrokerRelay**, the Spring relay opens TCP connections to an external broker. There are two groups of credentials:

| Configuration | Connection used | Meaning |
|---|---|---|
| **clientLogin / clientPasscode** | Each TCP connection opened on behalf of a WebSocket client | Shared broker account for client connections via the relay |
| **systemLogin / systemPasscode** | A single shared TCP system connection | Broker account for messages sent by server-side code, e.g. via SimpMessagingTemplate |

The relay always resets the login and passcode headers on the CONNECT frame it forwards to the broker on behalf of the client. Credentials sent by the browser in STOMP CONNECT are not forwarded verbatim as the user's own broker identity. Instead, the relay uses the clientLogin and clientPasscode configured on the server.

According to Spring's API, the default values for broker relay credentials are guest and guest. These defaults should not be kept in production; configure accounts with the minimum required privileges.

Example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class MessagingConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setClientLogin("spring-relay-client");
        relay.setClientPasscode(System.getenv("STOMP_CLIENT_PASSCODE"));

        relay.setSystemLogin("spring-relay-system");
        relay.setSystemPasscode(System.getenv("STOMP_SYSTEM_PASSCODE"));

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

The example above only configures authentication between the relay and the broker. It does not authenticate users logging into the Spring application. Users still need to be authenticated at the HTTP handshake or via a custom CONNECT token mechanism.

### 3.1. Identity implications

WebSocket clients going through the broker relay typically share a single clientLogin/clientPasscode pair to open broker connections. The broker may see the same broker account for many different application users.

Therefore:

- Do not use the broker username to infer the current application user.
- Do not treat broker authentication as a replacement for Spring Security.
- Do not assume an account's broker permissions automatically map to user roles/authorities.
- Authorize each user at the Spring message layer based on the authenticated Principal.
- Grant least-privilege broker permissions to the client relay and system relay; consider separating the two accounts to limit the scope of operations.

If the system requires each user to have a separate broker identity, a dedicated authentication/authorization architecture must be deliberately designed. The standard relay configuration of clientLogin and clientPasscode is shared credentials, not a mechanism that automatically maps per-browser credentials.

## 4. Limitations of using login/passcode for application login

### 4.1. Does not automatically create a Principal or SecurityContext

Spring does not automatically convert login into the username of an Authentication. The header is merely data inside STOMP CONNECT. Without a valid Authentication, message authorization cannot rely on this header to identify the user.

### 4.2. Does not grant destination access permissions

Even if the broker accepts login/passcode, that does not mean the user is allowed to send to /app/admin, subscribe to /topic/private, or read /user/queue/notifications.

Authentication answers the question **who is connecting**. Authorization answers **what that person is allowed to do**. Separate rules must be configured for SEND, SUBSCRIBE, and other message types.

### 4.3. Not a short-lived token

A static passcode can be copied, stored in browser storage, or leaked through logs/debugging. If reused across multiple sessions, revoking one credential can impact many clients. JWTs or access tokens with explicit expiration, issuer, audience, and scopes are usually more suitable when stateless authentication is needed, though server-side token validation is still required.

### 4.4. Does not replace TLS

STOMP login/passcode do not encrypt traffic. If the WebSocket/TCP connection does not use TLS, credentials and payloads can be observed in transit. With browsers using wss://, TLS protects the browser-to-Spring hop. If the Spring relay connects to the broker over a separate TCP connection, the Spring-to-broker hop also needs TLS if it traverses an untrusted network.

### 4.5. Does not solve CSRF or Origin control

A valid session cookie can be sent automatically by the browser during the WebSocket handshake. Therefore, the endpoint must be protected against unwanted cross-site connections. Spring Security requires a CSRF token on STOMP CONNECT by default when WebSocket security is enabled. This token protects against CSRF; it does not replace user authentication.

## 5. Using a token in STOMP CONNECT when messaging-layer authentication is needed

If cookie-based sessions are not used, the application can send a token in a STOMP CONNECT header and validate it with a ChannelInterceptor.

Workflow:

1. The client sends the token in a CONNECT header, e.g., Authorization: Bearer ...
2. The interceptor processes only the CONNECT frame.
3. The server validates the token's signature, issuer, audience, expiration, revocation status, and required claims.
4. The server creates an authenticated Authentication.
5. The interceptor calls accessor.setUser(authentication).
6. Spring stores the user for the session and associates that Principal with subsequent STOMP messages.
7. Spring Security uses the Principal to enforce authorization rules.

### 5.1. Client sending a token in STOMP CONNECT

Example with @stomp/stompjs:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    reconnectDelay: 5000
});

client.activate();
~~~

connectHeaders are headers of STOMP CONNECT after the WebSocket has been established. They are not HTTP headers of the handshake.

Browsers do not allow JavaScript to arbitrarily set HTTP headers for the WebSocket handshake. Therefore, do not confuse connectHeaders with custom HTTP handshake headers. The SockJS JavaScript client also has limitations on sending HTTP headers in transport requests; however, STOMP CONNECT can still carry protocol headers once the transport is established.

Avoid sending tokens via URL query parameters because URLs frequently appear in access logs, proxy logs, telemetry, or monitoring tools.

### 5.2. Authenticating tokens with a ChannelInterceptor

The example below shows where to process the token and how to attach the Principal. TokenAuthenticationService is an application service; it must genuinely verify the token and return an authenticated Authentication. You must not merely decode the JWT payload and trust the claims without checking the signature and security conditions.

~~~java
package com.example.messaging.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final TokenAuthenticationService tokenAuthenticationService;

    public StompTokenAuthenticationConfiguration(
            TokenAuthenticationService tokenAuthenticationService) {
        this.tokenAuthenticationService = tokenAuthenticationService;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor != null &&
                        StompCommand.CONNECT.equals(accessor.getCommand())) {

                    String authorization =
                            accessor.getFirstNativeHeader("Authorization");

                    if (authorization == null ||
                            !authorization.startsWith("Bearer ")) {
                        throw new BadCredentialsException(
                                "Missing bearer token");
                    }

                    String token = authorization.substring(7);
                    Authentication authentication =
                            tokenAuthenticationService.authenticate(token);

                    if (authentication == null ||
                            !authentication.isAuthenticated()) {
                        throw new BadCredentialsException(
                                "Invalid bearer token");
                    }

                    accessor.setUser(authentication);
                }

                return message;
            }
        });
    }
}
~~~

The authentication service is an abstraction provided by the application:

~~~java
public interface TokenAuthenticationService {
    Authentication authenticate(String token);
}
~~~

The implementation can use Spring Security Resource Server and JwtDecoder to verify the JWT signature, issuer, audience, and expiration, and then map claims to authorities. If the token is invalid or expired, CONNECT must be rejected.

The code above illustrates the interceptor portion; to compile into a complete application, you must provide a TokenAuthenticationService implementation and the corresponding JWT dependencies.

### 5.3. Interceptor ordering

When using Spring Security authorization for STOMP messages, the token authentication interceptor needs to run **before** Spring Security's authorization interceptor. Spring recommends placing the authentication configuration in a separate WebSocketMessageBrokerConfigurer and using:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
~~~

If the interceptor runs after authorization, Spring Security may evaluate the message before the Principal is attached to CONNECT/session.

### 5.4. Remaining limitations of CONNECT tokens

A CONNECT token authenticates the identity at the time the session is opened. Spring attaches that user to subsequent messages of the session. Therefore, the application must decide how to handle an expired or revoked token while the WebSocket session is still open: limit session lifetime, close the session when the token expires, or check sensitive permissions per message.

Do not trust usernames, roles, or user IDs sent by the client in custom headers. Those values must be derived from a verified token or from a server-side identity store.

## 6. Authentication and authorization with Spring Security

### 6.1. Protecting messages after authentication

@EnableWebSocketSecurity integrates Spring Security with STOMP messaging. Spring Security can use AuthorizationManager<Message<?>> to decide which destinations a user is allowed to send to or subscribe to.

Examples of necessary policies:

- Only authenticated users may send messages to /app/**.
- Only users with appropriate roles may subscribe to private destinations.
- Clients must not send directly to internal broker destinations such as /topic/** or /queue/** unless the application intentionally allows it.
- The /user/** destination must be controlled based on the Principal and application policy.
- Deny message types or destinations that are not explicitly declared.

You should not merely authenticate CONNECT and then allow all SEND/SUBSCRIBE frames. Each destination may access different data or perform different actions.

### 6.2. CSRF token on CONNECT

When Spring Security WebSocket security is enabled, inbound STOMP CONNECT requires a valid CSRF token by default. With browser clients, obtain the token from the application's CSRF mechanism and send it in the STOMP CONNECT headers under the header name configured by the server.

Illustrative example:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken,
        "X-CSRF-TOKEN": csrfToken
    }
});
~~~

The CSRF header name must match the Spring Security configuration and the token issued to the client. A CSRF token does not prove who the user is; the bearer token or HTTP session is the authentication credential. Do not disable CSRF globally just to make STOMP CONNECT work. If using SockJS and you need to adjust the HTTP CSRF matcher for the transport endpoint, restrict the change strictly to the specific endpoint according to the Spring Security guide.

### 6.3. Checking Origin and endpoints

Allowed origins for the WebSocket endpoint should be configured to match the frontend domains. Do not use a wildcard origin indiscriminately when connections carry credentials/cookies. HTTP handshake authentication, CONNECT CSRF, Principal checking, and message authorization are complementary layers.

## 7. Choosing an appropriate authentication model

| Model | Where does the application identity come from? | When is it suitable? | Points to note |
|---|---|---|---|
| HTTP session cookie | Spring Security Principal of the HTTP handshake | Same-domain web app with existing session login | Requires CSRF protection and session lifecycle management |
| HTTP Basic or suitable HTTP auth | HTTP request authentication | Clients that can provide an HTTP auth mechanism | Browser APIs have restrictions on setting handshake headers |
| Bearer token in STOMP CONNECT | Token verified by interceptor and attached as Principal | Mobile, stateless SPA, or clients without cookies | Must write interceptor, validate token, and handle expiry/revocation |
| STOMP login/passcode directly to broker | Broker account authenticated by the broker | Clients connecting directly to the STOMP broker over TCP | Does not automatically create a Spring application Principal |
| Broker relay clientLogin/clientPasscode | Broker account configured on the Spring relay | Applications using a broker relay | Usually shared across all client connections via the relay |

For typical Spring WebSocket applications, leverage the existing HTTP Principal. If stateless token authentication is needed, validate the token at CONNECT with an interceptor and set the Principal explicitly. Use login/passcode only as broker credentials when the protocol and architecture require it; do not rely on them to replace application security.

## 8. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| Client sends login/passcode, yet Principal remains null | Spring ignores STOMP authentication headers by default on WebSocket | Authenticate at HTTP handshake or install a CONNECT ChannelInterceptor |
| Broker relay still connects using one shared user | Relay overwrites CONNECT login/passcode with clientLogin/clientPasscode | Distinguish broker identity from application Principal |
| Message authorization does not recognize roles | Principal has not been attached or authorities were not mapped properly | Validate the token and set Authentication in accessor.setUser |
| Token header is rejected before authorization | Authentication interceptor runs in the wrong order | Place the interceptor before Spring Security per Spring's recommended ordering |
| CONNECT is rejected despite a valid bearer token | Missing CSRF token or invalid Origin | Check CONNECT CSRF and allowed origins |
| Token in URL appears in logs | Token passed via query parameter | Send the token in a CONNECT header or suitable HTTP auth mechanism |
| A user can subscribe to another user's destination | Only CONNECT was authenticated without checking SUBSCRIBE permissions | Configure per-destination authorization and check resource ownership |

## 9. Testing checklist

Before release, verify the following scenarios:

1. An authenticated HTTP session creates a WebSocket session with the right Principal.
2. An unauthenticated HTTP session is rejected at the handshake or according to endpoint policy.
3. Sending STOMP login/passcode without an HTTP Principal is not inadvertently treated as an authenticated user.
4. A valid CONNECT token produces the right Principal and authorities.
5. Tokens with an invalid signature, expired timestamp, wrong issuer, or wrong audience are rejected.
6. CONNECT missing a CSRF token is rejected when Spring Security requires it.
7. An authenticated user can only SEND/SUBSCRIBE to authorized destinations.
8. Clients cannot spoof the Principal using an arbitrary username or user ID header.
9. The broker relay uses client credentials and system credentials as configured; credentials are not written to logs.
10. Old sessions are closed or permissions updated when a token expires/is revoked per system policy.

You can use integration tests with WebSocketStompClient and a test broker to check CONNECT, Principal, SEND/SUBSCRIBE, and message rejection. Separate unit tests for the token validator should cover signature, issuer, audience, expiration, and authority mapping.

## 10. Security principles

1. **Authenticate at the right boundary.** HTTP Principal authenticates the WebSocket user; broker credentials authenticate the relay's connection to the broker.
2. **Do not confuse login/passcode with Spring Security.** On STOMP over WebSocket, Spring ignores these two headers by default.
3. **Attach the Principal on the server.** Set the user only after verifying a trusted session or token.
4. **Authorize every message.** Check SEND, SUBSCRIBE, destination, and resource access permissions.
5. **Protect CONNECT.** Use TLS/WSS, appropriate CSRF tokens, and Origin restrictions.
6. **Protect credentials.** Do not hard-code or log passcodes, bearer tokens, session IDs, or private secrets.
7. **Manage session lifecycle.** Handle token expiry, revocation, logout, and disconnect explicitly.
8. **Limit broker privileges.** Grant least privilege to the client relay and system relay; do not treat a shared broker account as an individual user identity.

## 11. References

- [Spring Framework – Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework – Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework – Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework – Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Security – WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
