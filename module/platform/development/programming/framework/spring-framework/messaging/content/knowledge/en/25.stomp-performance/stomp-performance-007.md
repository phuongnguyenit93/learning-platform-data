# Do Not Log Tokens, Credentials, or Sensitive Payloads

> Scope: Spring Framework STOMP over WebSocket, Java 17+. This lesson guides safe logging design for CONNECT, SEND, SUBSCRIBE, and DISCONNECT frames; handling auth headers; observing errors; using ChannelInterceptor; and testing to ensure tokens, credentials, and sensitive payloads are not written to logs.

## 1. Why Can STOMP Logs Expose Data?

A STOMP frame consists of a command, headers, and optionally a body. CONNECT may involve authentication information. SEND may contain private messages, customer data, order details, or user-submitted content. SUBSCRIBE may carry destinations that reveal usernames, tenants, chat rooms, or internal resources.

If an application logs raw frames, messages, header maps, or payloads for debugging, that data can appear in logs of the application, container, reverse proxy, APM system, and log collection platform. Copies may be retained longer than the lifetime of the token or session and accessed by broader groups of people than the original business data.

An expired token can still pose a risk if that token was previously logged. Passwords, API keys, session cookies, and refresh tokens can be exploited if anyone without log-reading authorization gains access to them.

The practical principle is to **log minimal events and metadata for operations, monitoring, and investigation; never log authentication secrets or sensitive message contents**.

## 2. Data to Exclude from Logs

| Data Category | Examples | How to Handle |
|---|---|---|
| Tokens | Access tokens, refresh tokens, JWTs, bearer tokens, opaque tokens | Do not log values; log only authentication type and outcome. |
| Credentials | Passwords, STOMP login/passcode, API keys, client secrets | Do not log; do not include in log messages or exceptions. |
| Auth Headers | Authorization, Cookie, Set-Cookie, custom auth headers | Do not log full headers or the entire native header map. |
| Session and CSRF | Session cookies, session IDs, CSRF tokens | Do not log raw values; use a server-generated correlation ID if needed. |
| Sensitive Payloads | Private messages, customer profiles, payment data, health data | Do not log body; log only event type and processing outcome. |
| Identifying Data | Emails, phone numbers, addresses, usernames, user IDs | Strip or use a pseudonym if there is an approved purpose. |
| Internal Context | Principal, simpSessionAttributes, native headers, broker credentials | Extract only allowed fields; do not dump entire objects. |
| URLs with Secrets | Query parameters containing tokens or access codes | Avoid putting tokens in URLs; configure access logs not to log sensitive query strings. |

Do not use the following approaches for debugging:

- Logging full STOMP frames or frame bodies.
- Logging entire Message<?> objects or calling Message.toString().
- Logging StompHeaderAccessor.toString() or the entire header map.
- Logging accessor.getFirstNativeHeader("Authorization") or CONNECT login/passcode values.
- Logging exception messages without knowing whether they contain incoming tokens, payloads, or headers.

Destinations also need evaluation. Paths such as /user/alice/queue/notifications, /tenant/acme/orders/123, or paths containing emails can reveal identities and business data. If you need to log a route, log a route template or an allowlisted label instead of the dynamic destination.

## 3. Understanding STOMP Authentication in Spring Properly

A STOMP over WebSocket session starts with an HTTP handshake. In common Spring configurations, users are authenticated at the HTTP layer, for example via Spring Security and session cookies. Spring attaches the authenticated Principal to the WebSocket session and subsequent STOMP messages.

The STOMP protocol has login and passcode headers in the CONNECT frame. However, for STOMP over WebSocket, Spring ignores these authentication headers by default and assumes identity was already authenticated at the HTTP layer. Do not rely on clients sending login/passcode in CONNECT to replace the application's authentication mechanism.

An application may implement token authentication at the STOMP layer. In that case, the client sends a token in a CONNECT header and the server uses a ChannelInterceptor to authenticate, then attaches the Principal to the message via accessor.setUser(...). The CONNECT header then contains a high-value secret. The interceptor can read the header to authenticate, but must not log the header or token.

Do not place access tokens in the WebSocket URL query string. URLs can appear in access logs of servers, reverse proxies, load balancers, APMs, or monitoring tools. Spring documentation also explicitly warns that tokens in query parameters can be accidentally logged with the URL.

If using tokens in CONNECT headers alongside Spring Security message authorization, ensure the authentication interceptor runs before Spring Security's authorization interceptor so the Principal is present when authorization is evaluated.

## 4. What Should Be Logged to Keep the System Observable?

Useful logs do not need to contain bodies or tokens. Prefer pre-selected fields:

| Log Field | Example | Purpose |
|---|---|---|
| Timestamp | UTC timestamp | Ordering and correlating events. |
| Event type | stomp.auth.denied, stomp.frame.received | Categorizing events. |
| STOMP command | CONNECT, SEND, SUBSCRIBE, DISCONNECT | Knowing the operation type. |
| Normalized route | chat.send, orders.submit, other | Knowing the application flow without exposing dynamic IDs. |
| Outcome | accepted, rejected, failed | Tracking results. |
| Reason code | invalid_token, destination_denied | Investigating errors with stable codes. |
| Correlation ID | Server-generated random ID | Linking logs of the same processing flow. |
| Application instance | Normalized instance or pod name | Identifying the node handling the message. |
| Latency | Processing time in ms | Performance analysis. |
| Size bucket | Size bucket, if needed | Observing trends without storing bodies. |

Only log user pseudonyms or session fingerprints when genuinely necessary and approved. If events must be linked per session, you can use HMAC with a separately managed secret key; avoid logging raw session IDs or using unkeyed hashes for predictable values.

Do not put tokens, usernames, session IDs, or dynamic destinations into metric labels. High-cardinality values increase cardinality, consume metric system resources, and can expose data.

## 5. Using ChannelInterceptor to Log Metadata Safely

Spring allows registering a ChannelInterceptor on the client inbound channel. The interceptor can read the STOMP command and destination via StompHeaderAccessor. The example below logs only the command and a fixed allowlisted route; it does not read the body, token, native headers, Principal, or session ID.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;

@Component
public class SafeStompLoggingInterceptor implements ChannelInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeStompLoggingInterceptor.class);

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        if (accessor.getCommand() != null) {
            String route = safeRoute(accessor.getDestination());

            // Command is an enum; route can only be a fixed label.
            // Do not log message, payload, headers, Principal, or session ID.
            log.debug("stomp.in command={} route={}",
                    accessor.getCommand(), route);
        }

        return message;
    }

    private static String safeRoute(String destination) {
        if (destination == null) {
            return "none";
        }

        return switch (destination) {
            case "/app/chat.send" -> "chat.send";
            case "/app/orders.submit" -> "orders.submit";
            case "/topic/announcements" -> "announcements";
            default -> "other";
        };
    }
}
~~~

The safeRoute helper returns fixed labels instead of arbitrary client-supplied destinations. If the application has dynamic destinations like /app/rooms/{roomId}/messages, map them to a route template or label like room.message. Do not log the actual roomId without clear need and authorization.

Register the interceptor in the existing WebSocket configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final SafeStompLoggingInterceptor safeLoggingInterceptor;

    public WebSocketConfig(SafeStompLoggingInterceptor safeLoggingInterceptor) {
        this.safeLoggingInterceptor = safeLoggingInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(safeLoggingInterceptor);
    }

    // Keep existing endpoint, broker, and application prefix configuration.
}
~~~

This is an addition to an existing configuration. If the project already has a WebSocketConfig with @EnableWebSocketMessageBroker, add the configureClientInboundChannel method and interceptor dependency to that class; do not create a second broker configuration.

The sample interceptor only observes inbound messages. If outbound observation is needed, you can register an interceptor on the client outbound channel and apply the same allowlist. Do not assume outbound bodies are safe just because messages are server-generated; bodies can still contain private data.

Example log:

~~~text
stomp.in command=CONNECT route=none
stomp.in command=SEND route=chat.send
stomp.in command=SUBSCRIBE route=other
~~~

These lines show the operation type and normalized route without containing tokens, passwords, usernames, session IDs, or payloads.

## 6. Recording Security Events Without Exposing Secrets

Not logging secrets does not mean ignoring security events. You can log:

- CONNECT authentication result: accepted or rejected.
- Failure reason using stable codes such as invalid_token, expired_credential, or missing_identity.
- SEND or SUBSCRIBE commands denied by authorization.
- Clients accessing unauthorized destinations.
- Malformed frames, size-limit violations, or validation failures.
- Abnormal disconnects, heartbeat timeouts, or broker connection failures.
- Unusual send rates, destination probing behavior, or rate-limit violations.

Example logging an authentication failure event:

~~~java
log.warn(
    "stomp.auth outcome={} reason={} route={} correlationId={}",
    "rejected",
    "invalid_token",
    "connect",
    correlationId
);
~~~

correlationId in the example must be generated by the server or a trusted tracing system. Do not take arbitrary client-supplied values and log them without format and length restrictions.

For errors, prefer logging the exception class, internal error code, and correlation ID. Only log stack traces after verifying that exception messages and related fields do not contain secrets or payloads. Do not log invalid raw tokens, CONNECT headers, or frames to explain why a request was rejected.

## 7. Allowlists, Redaction, and Log Injection

### Prefer Allowlists

Pre-select fields allowed to be logged. Do not log all headers and try to scrub a list of a few sensitive names. The list of secrets can grow, custom headers can exist, and secrets can appear in many different formats.

If a client-supplied field must be logged, you should:

1. Define a specific operational purpose.
2. Validate type, length, and format.
3. Strip or encode control characters such as CR and LF.
4. Truncate length before logging.
5. Prevent values from injecting extra lines or fake log fields.
6. Test with newlines, delimiters, and mock secret canary data.

Use structured logging and parameterized loggers so data is written as separate fields. Structured logging does not replace filtering and redaction: if a field contains a token, JSON logs still expose the token.

### Redaction at the Source

Remove sensitive data right at the log generation point. Do not rely entirely on downstream pipelines to mask tokens after they have already been written to local files or shipped through log collection agents. Masking in centralized systems is only an additional defense layer.

Do not log payload.length() or payload hashes by default. Size and hashes can still allow data inference; log them only when there is a clear purpose and the risk has been assessed.

## 8. Log Levels and Volume Control

In production:

- Do not enable broad TRACE or DEBUG for WebSocket, Messaging, Security, or the whole application without checking what those loggers actually emit.
- Use a dedicated application logger to write sanitized events.
- Enable temporary debug only in test environments, limiting duration, access, and test data.
- Do not enable raw frame logging in production.
- Use sampling for high-frequency success events; continue logging important security events after stripping secrets.
- Rate-limit repeated logs triggered by clients continuously sending malformed frames to avoid log flooding.
- Use aggregated metrics for throughput, errors, latency, and connection counts; do not use tokens, usernames, session IDs, or payloads as metric labels.

Check logs produced by reverse proxies, load balancers, API gateways, container runtimes, and APM agents as well. Even if the application does not log tokens, URLs with tokens in query strings can still be logged at the HTTP layer.

## 9. Protecting Logs After Generation

Logs can still contain operational metadata and minimized personal data. Protect them as controlled assets:

- Restrict read access by role and job need.
- Audit when users access or export sensitive logs.
- Encrypt in transit and at rest.
- Set retention aligned with purpose and legal requirements; automatically delete upon expiration.
- Separate log administration privileges from application administration privileges where possible.
- Protect integrity and backups according to operational policy.
- Never copy production logs containing personal data to developer machines or public tickets.

If you discover that tokens or passwords have been logged, handle it as a secret exposure incident: restrict log access, identify the scope of copies and downstream systems, revoke or rotate affected credentials, and handle log records under incident response procedures. Deleting a local log file does not guarantee copies in centralized systems, backups, or APMs are gone.

## 10. Testing to Prove Logs Contain No Secrets

A useful test sends mock canary data through STOMP paths and verifies it does not appear in logs:

- CONNECT with a mock header Authorization: Bearer CANARY_TOKEN.
- CONNECT with a custom header containing CANARY_SECRET.
- SEND with a JSON body containing CANARY_PRIVATE_MESSAGE.
- Payload containing a mock email or phone number.
- Destination containing dynamic IDs or CR/LF characters.

After running, search for each canary string in application logs, access logs, proxy logs, and test environment log collectors. Expected outcome: logs contain only command, allowlisted route, outcome, and correlation ID; no canary values appear.

Additionally verify that:

- Logging code does not call message.toString() or dump headers/bodies.
- Unknown destinations map to other.
- Authentication errors log only reason codes, not incoming tokens.
- Log injection does not create extra lines or forged fields.
- Temporary debug logging is not accidentally enabled in production.

## 11. Comparing Unsafe and Safe Logging Examples

| Unsafe | Safer |
|---|---|
| Logging raw Message<?> or STOMP frames | Log command and normalized route. |
| Logging the full native header map | Log authentication type or authentication outcome. |
| Logging Authorization or CONNECT login/passcode | Log auth.outcome=rejected and reason=invalid_token. |
| Logging the JSON body of SEND | Log event type and processing outcome. |
| Logging session ID or cookies | Use server-generated correlation ID; HMAC session identifier only if truly needed. |
| Logging dynamic destinations containing email/user ID | Log route template or allowlisted label. |
| Logging exception messages verbatim | Log exception class, error code, and correlation ID after evaluating content. |

## 12. Checklist Before Enabling STOMP Logging

1. Does any logger record raw frames, bodies, Message<?>, or native headers?
2. Can CONNECT contain tokens, logins, passcodes, or CSRF tokens?
3. Can destinations contain usernames, tenant IDs, emails, or business data?
4. Do access logs record WebSocket URL query strings?
5. Does the interceptor log only allowlisted fields?
6. Could exception messages and stack traces contain payloads or credentials?
7. Are logs access-restricted, encrypted, retention-configured, and audited?
8. Are there canary tests proving tokens, credentials, and payloads do not appear in logs?

If any answer shows secret data could enter logs, fix it at the log generation source before deploying to production.

## References

- [Spring Framework — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): registering ChannelInterceptor, reading STOMP commands and header accessors.
- [Spring Framework — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): HTTP handshake authentication and Principal attached to STOMP sessions.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): handling tokens in CONNECT via interceptors and risks of tokens in query strings.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): authentication, message authorization, and securing CONNECT.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude, mask, hash, or encrypt in logs.
