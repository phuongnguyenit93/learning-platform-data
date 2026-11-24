# Never Log Tokens, Credentials, or Sensitive Payloads

> Scope: Spring Framework STOMP over WebSocket, Java 17+. This article focuses on safe logging in STOMP flows: CONNECT, SEND, and SUBSCRIBE frames, authentication headers, application payloads, interceptors, security event logs, and testing to ensure secrets never leak into logs.

## 1. Why can STOMP logs expose data?

A STOMP frame typically contains a command, headers, and a body. For instance, CONNECT can carry credentials; SEND can carry chat content, order data, or personal information. When overly verbose logging is enabled or entire message objects are logged, the application can copy this data to log files, centralized logging systems, APM platforms, or log storage services.

Logs are often accessible to far more people and systems than the original business data. Logs may be forwarded to other environments, retained longer than a session's lifetime, or appear in backups. Consequently, a token written to logs can remain exposed even after the token has expired or the session has closed.

Principle to follow: **log minimal events and metadata needed for operations, investigation, and monitoring; never log authentication secrets or sensitive message contents.**

## 2. Data that must never be logged directly

| Data category | Examples | How to handle |
|---|---|---|
| Access and refresh tokens | JWT, bearer token, opaque token | Never log values; log only the authentication type or outcome. |
| Credentials | Passwords, STOMP login/passcode, API keys, client secrets | Never log; never include in exception or diagnostic messages. |
| Authentication headers | Authorization, Cookie, Set-Cookie, custom auth headers | Never log raw headers or the entire native header map. |
| Sessions and CSRF | Session cookies, session IDs, CSRF tokens | Never log raw values; if event correlation is needed, use a correlation ID or protected identifier. |
| Sensitive payloads | Private messages, customer profiles, payment data, health data | Never log the body; log only the event type and processing outcome. |
| Identifying data | Email, phone number, address, username, or user ID when unnecessary | Omit or replace with a pseudonym per policy. |
| Internal headers and attributes | Native headers, simpSessionAttributes, Principal details | Extract only allowlisted fields; never dump entire objects. |
| URLs with secrets | Query parameters containing tokens or access codes | Avoid passing tokens via URLs; configure access logs not to record sensitive query strings. |

Do not log full STOMP frames, bodies, `Message<?>`, `Message.toString()`, `StompHeaderAccessor.toString()`, or header maps for debugging. Those can leak data even when the logging code never directly mentions tokens or passwords.

Destinations must also be considered. A destination such as `/user/alice/queue/notifications`, `/tenant/acme/orders/123`, or a path containing an email address can reveal identity or business details. Not every destination is safe to log verbatim.

## 3. Notes on STOMP authentication in Spring

In typical STOMP over WebSocket applications, Spring attaches the authenticated Principal from the HTTP handshake to the WebSocket session and subsequent messages. By default, Spring ignores the `login` and `passcode` headers of STOMP CONNECT when running over WebSocket; authentication normally relies on the HTTP request and existing security context.

An application may choose token authentication at the STOMP layer. In that case, the client sends the token in a CONNECT header and the application uses a `ChannelInterceptor` to validate it and attach the user to the message. The CONNECT headers become especially sensitive data. The interceptor is permitted to read the header to authenticate, but must never log that header.

Do not place access tokens in the WebSocket URL query string. URLs can appear in access logs, reverse proxies, monitoring, or diagnostic tool history. Choose an authentication mechanism matching the client type and Spring Security guidance; if using a STOMP CONNECT header, read it only during the authentication step and never copy it into logs.

Example comparing two actions:

- Allowed: reading the Authorization header inside the interceptor to verify signature, expiration, and permissions.
- Forbidden: logging `accessor.getNativeHeaderMap()`, `accessor.getFirstNativeHeader("Authorization")`, or the token to “debug login”.

## 4. What should be logged to maintain observability?

A useful log does not need to contain bodies or tokens. Prefer allowlisted fields:

| Log field | Safe example | Purpose |
|---|---|---|
| Timestamp | UTC timestamp | Order and correlate events. |
| Event type | `stomp.frame.received`, `stomp.auth.denied` | Categorize events. |
| STOMP command | `CONNECT`, `SEND`, `SUBSCRIBE`, `DISCONNECT` | Identify the operation type. |
| Normalized route | `chat.send`, `orders.submit`, `other` | Identify application flow without exposing dynamic IDs. |
| Outcome | `accepted`, `rejected`, `failed` | Track results. |
| Reason code | `invalid_token`, `destination_denied` | Investigate failures using stable codes. |
| Correlation ID | Random server-generated ID | Link logs across a request or processing flow. |
| User pseudonym | Approved HMAC or internal identifier | Correlate by user without logging raw identifiers. |
| Application instance | Normalized instance or pod name | Identify the node processing the message. |
| Latency / size bucket | Processing duration or size bucket | Observe performance without logging payloads. |

Log a user pseudonym or session fingerprint only when genuinely necessary and approved. If correlating by session is required, use an HMAC with a separately managed secret key rather than a raw session ID or unkeyed hash. Do not place user IDs, session IDs, or dynamic destinations into high-cardinality metric labels.

## 5. Using ChannelInterceptor to log selected metadata

Spring allows registering a `ChannelInterceptor` on the client inbound channel. The interceptor can read the STOMP command and destination using `StompHeaderAccessor`. The example below logs only the command and an allowlisted route name; it does not read the body, token, native headers, Principal, or session ID.

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

            // Log only the command and allowlisted static route.
            // Do not log the message, payload, headers, Principal, or session ID.
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

The `safeRoute` function returns fixed labels instead of logging arbitrary client-supplied destinations. If the application has dynamic destinations like `/app/rooms/{roomId}/messages`, map them to the route template `/app/rooms/{roomId}/messages`; do not log the actual roomId value unless policy allows it.

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

    // Keep existing endpoint, broker, and application prefix configurations.
}
~~~

This adds to the application's existing configuration; do not create a second `@EnableWebSocketMessageBroker` configuration if the project already has one. The sample interceptor observes only inbound frames. If outbound observation is needed, register a separate interceptor on the client outbound channel and apply the same allowlist principle.

Example logs:

~~~text
stomp.in command=CONNECT route=none
stomp.in command=SEND route=chat.send
stomp.in command=SUBSCRIBE route=other
~~~

There are no bodies, tokens, passwords, usernames, or session IDs in these lines.

## 6. Logging security events without leaking secrets

Not logging secrets does not mean ignoring security events. You can log:

- CONNECT authentication outcome: success or failure.
- Failure reason using stable codes such as `invalid_token`, `expired_credential`, or `missing_identity`.
- SEND or SUBSCRIBE commands denied by authorization.
- Clients sending to disallowed destinations.
- Malformed frames, size limit violations, or validation failures.
- Unexpected disconnects, heartbeat timeouts, or broker connection failures.
- Abnormal send rates, destination probing, or rate-limit breaches.

Example security event log from authentication logic:

~~~java
log.warn(
    "stomp.auth outcome={} reason={} route={} correlationId={}",
    "rejected",
    "invalid_token",
    "connect",
    correlationId
);
~~~

`correlationId` in the example must be a correlation ID generated by the server or a trusted tracing system. Do not take arbitrary values verbatim from the client and write them to logs without restricting format and length. Never log invalid tokens, CONNECT headers, exception messages that might contain tokens, or raw frames to explain why a request was rejected.

For errors, prefer logging the exception class, internal error code, and correlation ID. Log stack traces only after verifying that exception messages and related fields do not contain secrets or payloads. Technical details can be sent to a separately controlled diagnostic system, while still applying the same data protection policies.

## 7. Redaction, allowlists, and log injection prevention

### Prefer allowlists

The safer approach is to choose allowed fields upfront. Do not log all headers and then try to strip a list of a few sensitive names. The list of secrets can grow, custom headers can exist, and secrets can appear in many different formats.

If logging a client-supplied field is strictly required:

1. Clearly define the operational need for that field.
2. Validate its type, length, and format.
3. Strip or encode control characters such as CR and LF.
4. Truncate to a maximum length before logging.
5. Never allow the value to overwrite field names or inject extra log lines.
6. Test with strings containing newlines, delimiters, and simulated secrets.

Use structured logging and parameterized logger calls so data is written into separate fields. Never concatenate raw client-supplied data into log strings. However, structured logging does not replace filtering and redaction: if a field contains a token, a JSON log will still expose that token.

### Redaction at the source

Remove sensitive data right at the point where logs are created. Do not rely solely on downstream pipelines to mask a token after it has already been written to a local file or shipped by a log collector agent. Masking in a centralized system is only an additional layer of defense.

Do not log `payload.length()` or a hash of the payload as a default workaround. Size and hashes can sometimes still allow data inference; log them only when there is a clear purpose and the risk has been evaluated.

## 8. Log level configuration and volume control

In production environments:

- Do not enable broad TRACE or DEBUG logging for WebSocket, Messaging, Security packages, or the entire application without verifying what the loggers actually emit.
- Use a dedicated application logger to emit sanitized events.
- Enable debug logging only temporarily in test environments, limiting duration, access, and test data.
- Never enable raw frame logging in production.
- Use sampling for high-frequency success events; retain important security events while still stripping secrets.
- Rate-limit repeated logs caused by clients continuously sending malformed frames to avoid log flooding.
- Use aggregated metrics for throughput, errors, latency, and connection counts; never use tokens, usernames, session IDs, or payloads as metric labels.

Also check logs produced by reverse proxies, load balancers, API gateways, container runtimes, and APM agents. Even if the application does not log tokens, a URL containing a token in the query string can still be logged at the HTTP layer.

## 9. Protecting logs after creation

Logs can still contain operational metadata and minimized personal data. Protect them as a controlled asset:

- Restrict read access by role and job need.
- Audit when users access or export sensitive logs.
- Encrypt in transit and at rest.
- Set retention periods aligned with purpose and legal requirements; delete automatically upon expiration.
- Separate log administration privileges from application administration privileges where possible.
- Protect integrity and backups according to operational policy.
- Never copy production logs containing personal data to developer machines or public tickets.

If a token or password is discovered in logs, treat it as a secret exposure incident: restrict log access, identify the scope of copies and downstream systems, revoke or rotate the affected credentials, and handle the log records per incident response procedures. Deleting a local log file does not guarantee that copies in centralized logging, backups, or APM are gone.

## 10. Testing to prove logs contain no secrets

A useful test is to send synthetic canary data through STOMP paths and assert it never appears in logs:

- CONNECT with a synthetic header `Authorization: Bearer CANARY_TOKEN`.
- CONNECT with a custom header containing `CANARY_SECRET`.
- SEND with a JSON body containing `CANARY_PRIVATE_MESSAGE`.
- Payloads containing synthetic email addresses or phone numbers.
- Destinations containing dynamic IDs or CR/LF characters.

After running, search for each canary string across all application logs, access logs, proxy logs, and test-environment log collectors. Expected result: logs contain only command, allowlisted route, outcome, and correlation ID; no canary values appear.

You can also verify that:

- Logging does not call `message.toString()` or dump headers/bodies.
- Unknown destination paths map to `other`.
- Authentication failures log only reason codes, not input tokens.
- Log injection attempts do not create extra lines or forged fields.
- Temporary debug logging is not accidentally enabled in production.

## 11. Comparison of unsafe vs. safe logs

| Unsafe | Safer |
|---|---|
| Logging raw `Message<?>` or STOMP frames | Logging the command and normalized route. |
| Logging the entire native header map | Logging the authentication type name or outcome. |
| Logging `Authorization` or CONNECT login/passcode | Logging `auth.outcome=rejected` and `reason=invalid_token`. |
| Logging the JSON body of SEND | Logging the event type and processing outcome. |
| Logging session IDs or cookies | Using a server-generated correlation ID; HMAC session identifier if genuinely needed. |
| Logging dynamic destinations with emails/user IDs | Logging route templates or allowlist labels. |
| Logging exception messages verbatim | Logging exception class, error code, and correlation ID after reviewing content. |

## 12. Checklist before enabling STOMP logging

1. Does any logger record raw frames, bodies, `Message<?>`, or native headers?
2. Can CONNECT contain tokens, logins, passcodes, or CSRF tokens?
3. Can destinations contain usernames, tenant IDs, emails, or business data?
4. Do access logs record the query string of WebSocket URLs?
5. Does the interceptor log only allowlisted fields?
6. Could exception messages and stack traces contain payloads or credentials?
7. Are logs access-restricted, encrypted, retention-bounded, and audited?
8. Are there canary tests proving tokens, credentials, and payloads never appear in logs?

If any answer indicates secret data could enter logs, fix it at the logging source before deploying to production.

## References

- [Spring Framework — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): registering `ChannelInterceptor`, reading STOMP commands and header accessors.
- [Spring Framework — Authentication](https://docs.spring.io/spring/reference/7.1/web/websocket/stomp/authentication.html): HTTP handshake authentication and Principal bound to STOMP sessions.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): handling tokens at CONNECT with an interceptor and query-string token risks.
- [Spring Security — WebSocket Security](https://www.springframework.org/spring-security/reference/servlet/integrations/websocket.html): authentication, message authorization, and protecting CONNECT.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude, mask, hash, or encrypt in logs.
