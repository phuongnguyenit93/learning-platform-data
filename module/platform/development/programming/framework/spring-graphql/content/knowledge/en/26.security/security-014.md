# Never log tokens and secrets in Spring for GraphQL

Logs help monitor activity, investigate incidents, and detect abnormal behavior. However, logs are also an easy place to leak credentials if an application records entire HTTP headers, GraphQL request bodies, variables, execution contexts, or exception messages.

In Spring for GraphQL, sensitive data can appear across many layers: HTTP Authorization headers, Cookies, GraphQL variables, literals inside GraphQL documents, WebSocket connection_init payloads, RSocket metadata, GraphQLContext, mutation results, and error details. The safe rule is to log only operationally necessary fields using an allowlist; never log raw requests/responses and attempt to mask secrets afterward.

This lesson applies to Spring for GraphQL applications using Queries, Mutations, Subscriptions, and HTTP, WebSocket, or RSocket transports. It focuses on designing safe logs while retaining enough information to trace requests and investigate errors.

## 1. Why must tokens and secrets never appear in logs?

Logs are typically forwarded to multiple systems: console, files, container runtimes, log collection agents, APM, SIEM, centralized storage, backups, and operational support tools. Someone authorized to read logs may not have access to the application's database or secret manager.

If logs contain tokens or secrets, anyone reading the logs could use them to:

- Impersonate users with access tokens or session cookies.
- Use refresh tokens to mint new access tokens.
- Call internal APIs with API keys or service credentials.
- Access databases via connection strings containing usernames/passwords.
- Decrypt or sign data if logs expose encryption keys/private keys.
- Compromise accounts via passwords, OTPs, reset tokens, or recovery codes.
- Access personal data or payment details logged alongside requests.

A logged secret can outlive the credential's lifespan in the application because logs are backed up, replicated, and stored under retention policies. Deleting a log line in one location does not guarantee all copies are gone.

## 2. Identifying sensitive data in GraphQL

Fields named token or password are not the only secrets. Identify sensitive data based on its ability to grant permissions, authenticate, recover accounts, or disclose private information.

| Data category | Examples in GraphQL/Spring | Log handling |
| --- | --- | --- |
| Access/refresh token | Authorization: Bearer ..., tokens in login mutation | Never log values; if needed, log credential type and authentication outcome. |
| Session credential | JSESSIONID, SESSION cookie, session ID | Never log raw values; use a keyed fingerprint if correlation is needed. |
| Password/PIN/OTP | login(password), changePassword, verifyOtp | Never log values, even when validation fails. |
| API key/client secret | X-API-Key, client_secret, webhook secret | Never log headers or input values. |
| Cryptographic key | Private key, signing key, encryption key | Never log key material; log only key identifier/version. |
| Database credential | JDBC URL with user/password, connection string | Mask all credentials and sensitive parameters. |
| Personal/sensitive data | Email, phone number, address, health info | Log only with justification and need; prefer pseudonymization. |
| Payment data | Card number, CVV, bank account | Never log payment authentication data; comply with PCI scope and applicable regulations. |
| Recovery data | Password reset token, magic link, invite token | Never log tokens or URLs containing tokens. |

A GraphQL input can contain secrets even if the schema does not use sensitive field names. For example, fields named credential, proof, authorizationCode, or challengeResponse must all be classified according to business semantics.

## 3. Places where GraphQL commonly leaks secrets

### HTTP headers and cookies

Headers to exclude from raw logs:

- Authorization
- Proxy-Authorization
- Cookie
- Set-Cookie
- X-API-Key and custom API key headers
- Headers carrying signatures, client secrets, or internal credentials

Never log an entire HttpHeaders object by calling toString or serializing the whole map. Headers can hold many credentials beyond the most common names.

### GraphQL documents and variables

A GraphQL request typically has a JSON structure:

~~~json
{
  "query": "mutation Login($input: LoginInput!) { login(input: $input) { accessToken } }",
  "operationName": "Login",
  "variables": {
    "input": {
      "username": "user@example.com",
      "password": "correct-horse-battery-staple"
    }
  }
}
~~~

Logging the entire body can persist the password. Variables are not the only sensitive part: clients can also write literals directly inside the document:

~~~graphql
mutation {
    login(input: {
        username: "user@example.com",
        password: "literal-password"
    }) {
        accessToken
    }
}
~~~

Therefore, never log raw GraphQL documents, variables, or entire request bodies by default. Merely stripping a password field from variables is still unsafe if secrets can appear in literals, aliases, or nested input objects.

### GraphQLContext and Principal

GraphQLContext may hold tenant, principal, locale, correlation ID, or authentication metadata. Never log the entire context, Principal.toString(), Authentication objects, or SecurityContext. These objects can contain credentials, internal authorities, or personal information.

If identity logging is required, log only an approved identifier, potentially pseudonymized or using an internal ID that carries no credential value.

### WebSocket connection_init

GraphQL WebSocket clients can send an authentication payload when initializing a connection. That payload may contain an access token or session credential. Avoid enabling frame-level logging or debug logging that might record raw connection_init contents.

Once connected, subscribe/next/error messages may also carry sensitive business data. Never log full frames or event payloads without a classification policy.

### RSocket metadata

When using RSocket, credentials may reside in metadata or the setup payload instead of an HTTP Authorization header. Apply the same rule: never dump the metadata map, setup payload, or authentication objects into logs.

## 4. Using an allowlist instead of logging everything and redacting later

An allowlist defines beforehand which fields are permitted to be logged. This is safer than a denylist because the application cannot anticipate every secret field name clients might send.

Example log fields that are usually sufficient for operations:

| Log field | Example | Notes |
| --- | --- | --- |
| event | graphql.request.completed | Fixed event name. |
| operation | Login, SearchBooks | Log only controlled operation names or map to safe labels. |
| correlationId | Server-generated ID | Never use access token/session ID as correlation ID. |
| durationMs | 42 | Processing duration. |
| outcome | SUCCESS, GRAPHQL_ERROR, TRANSPORT_ERROR | Outcome classification. |
| errorCount | 1 | Error count, not the full error payload. |
| errorCode | BOOK_NOT_FOUND | Use approved error codes only. |
| userRef | HMAC/pseudonymous ID | Never log raw tokens or session IDs. |
| transport | HTTP, WEBSOCKET, RSOCKET | Useful for classifying request source. |

Do not include the following in the default allowlist:

- Raw Authorization/Cookie headers.
- Raw request bodies, GraphQL documents, and variables.
- Raw GraphQLContext, Principal, or Authentication.
- Raw response bodies or subscription event payloads.
- Unvetted exception messages.
- Database URLs, connection strings, or secret manager responses.

## 5. Examples of unsafe logging and safe logging

### Unsafe approach

~~~java
log.info("GraphQL request: {}", request);
log.debug("GraphQL headers: {}", request.getHeaders());
log.debug("GraphQL context: {}", executionInput.getGraphQLContext());
log.error("GraphQL failed: {}", exception.getMessage(), exception);
~~~

These calls can record requests, headers, contexts, or exceptions containing credentials. Merely lowering the log level to DEBUG does not solve the issue if production environments can enable DEBUG/TRACE during incident investigation.

### Safer approach

Emit events with explicitly selected fields:

~~~java
log.info(
        "graphql.request.completed operation={} correlationId={} durationMs={} errorCount={}",
        operationLabel,
        correlationId,
        durationMs,
        errorCount);
~~~

For errors, prefer logging the exception type and a classified internal error code:

~~~java
log.warn(
        "graphql.request.failed operation={} correlationId={} exceptionType={}",
        operationLabel,
        correlationId,
        exception.getClass().getSimpleName());
~~~

If stack traces are needed for investigation, use an access-restricted log stream with tested redaction and an appropriately short retention period. Do not automatically log full exception objects across every logger, as messages, causes, or custom fields may hold secrets.

## 6. Creating a WebGraphQlInterceptor that logs only safe metadata

WebGraphQlInterceptor lets you observe requests and responses at the HTTP/WebSocket transport. You do not need to log bodies to know which operation ran, how long it took, and how many GraphQL errors occurred.

The example below logs only allowlisted operation labels, a server-generated correlation ID, duration, and error count:

~~~java
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SafeGraphQlLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGraphQlLoggingInterceptor.class);

    private static final Set<String> ALLOWED_OPERATIONS =
            Set.of("SearchBooks", "CreateOrder", "TrackOrder");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        long startedAt = System.nanoTime();
        String correlationId = UUID.randomUUID().toString();
        String operation = safeOperationLabel(request.getOperationName());

        return chain.next(request)
                .doOnNext(response -> log.info(
                        "graphql.request.completed operation={} correlationId={} durationMs={} errorCount={}",
                        operation,
                        correlationId,
                        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt),
                        response.getErrors().size()))
                .doOnError(error -> log.warn(
                        "graphql.request.failed operation={} correlationId={} exceptionType={}",
                        operation,
                        correlationId,
                        error.getClass().getSimpleName()));
    }

    private String safeOperationLabel(String operationName) {
        if (operationName == null || !ALLOWED_OPERATIONS.contains(operationName)) {
            return "OTHER";
        }
        return operationName;
    }
}
~~~

Points to note:

- The interceptor never reads or logs the request body.
- It never serializes request headers, variables, GraphQLContext, or response data.
- Operation names are logged only if present in the allowlist. Operation names are client-supplied, so never treat them as trusted data by default.
- The correlation ID is newly generated by the server, not taken from an Authorization header or cookie.
- When reactive errors occur, the example logs only the exception class. If stack traces are needed, enforce a dedicated logging policy.
- This interceptor does not automatically protect logs in reverse proxies, gateways, WebSocket frame loggers, or APM agents; those layers require their own configuration.

When using multiple interceptors, ensure the logging interceptor does not sit behind another interceptor that already logged raw headers/bodies. Allowlist rules must apply throughout the chain.

## 7. Do not copy Authorization headers into GraphQLContext for logging

Spring for GraphQL can use HttpRequestHeaderInterceptor to copy selected HTTP headers into GraphQLContext. Map only headers genuinely needed for business logic; never map Authorization, Cookie, or API keys merely for debugging convenience.

Example mapping a non-sensitive header:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration
class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Region")
                .build();
    }
}
~~~

If the application needs an access token for authentication, let Spring Security handle credentials and expose the principal/authentication through the security context. There is no need to copy raw tokens into GraphQLContext. Resolvers should only receive the principal or required permission info, not raw credentials again.

## 8. Never log raw responses or GraphQL errors

Secrets do not live only in requests. Mutations can return one-time API keys, refresh tokens, or sensitive details. Resolver errors can also contain invalid values, SQL fragments, upstream URLs, tokens, or exception messages from dependencies.

Do not log:

~~~java
log.info("GraphQL response: {}", response);
log.error("GraphQL errors: {}", response.getErrors());
~~~

Instead, log the error count and standardized error codes:

~~~java
int errorCount = response.getErrors().size();
log.info("graphql.response.completed errorCount={}", errorCount);
~~~

If you need error category analysis, map exceptions to stable codes such as VALIDATION_FAILED, ACCESS_DENIED, or UPSTREAM_UNAVAILABLE. Avoid using raw messages provided by clients or dependencies as log fields.

## 9. Masking data if partial logging is unavoidable

Prefer omitting sensitive fields from logs altogether. Mask only when there is an approved business requirement and a partial value is genuinely needed for investigation.

Examples:

| Original data | Preferred handling |
| --- | --- |
| Authorization: Bearer eyJ... | Do not log header; if needed, log credentialType=BEARER. |
| Session ID | Do not log raw ID; use an HMAC fingerprint if correlation is needed. |
| Email | Use a user reference or partially mask if permitted. |
| API key | Log only key identifier/version, never the secret value. |
| Database URL | Log datasource name or database alias, never URLs with credentials. |
| Password/OTP/reset token | Never log any portion of the value. |

Do not use naive substitutions such as keeping only the last 4 characters of an access token or API key. Partial tokens can still aid correlation or attacks while offering negligible diagnostic value.

If you need to correlate logs across the same session, OWASP recommends not logging raw session IDs. A salted hash/fingerprint can be used for correlation. In systems that must prevent guessing values or reusing fingerprints outside logging, prefer HMAC with a dedicated key for logging, managed and rotated independently.

Do not use unsalted/unkeyed hashes for low-entropy data such as emails, phone numbers, or usernames if dictionary attacks are possible. Pseudonymization does not mean the data is anonymized.

## 10. Redaction must happen before data leaves the application

A logging pipeline might look like:

~~~mermaid
flowchart LR
    A[HTTP / WebSocket / RSocket request] --> B[Application]
    B --> C[Allowlist and sanitize before log call]
    C --> D[Structured log event]
    D --> E[Log agent]
    E --> F[Central log platform]
    F --> G[Retention / archive]
~~~

If the application passes a raw token to an appender and relies on redacting it in a log collector later, the secret has already passed through process memory, temporary files, agent buffers, or networks. Post-collection redaction cannot guarantee removing all copies.

Therefore:

1. Never construct a log event containing a secret.
2. If using a sanitizer, run it before calling the logger.
3. Pass only approved fields to the structured logging encoder.
4. Configure log agents, gateways, and APMs to strip sensitive headers/bodies as a defense-in-depth layer.
5. Audit log files, consoles, container logs, trace attributes, and backups alike.

## 11. Be careful with structured logging, MDC, and tracing

Structured logging gives logs clear fields and makes them easy to query, but JSON does not automatically make data safe. If a token is put into an authorization field, the encoder will still write that token.

Spring Boot supports structured logging in formats such as ECS, GELF, and Logstash. You can add MDC or ad-hoc fields, but add only approved metadata:

~~~yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs
~~~

Never put Authorization, raw session IDs, passwords, or secrets into MDC. MDC can be attached to every log line of a request, widening the blast radius of a leak.

For tracing/OpenTelemetry/APM, never attach raw tokens, cookies, GraphQL variables, or request/response bodies to span attributes or span events. Traces are often sent to separate systems with independent retention policies. Use low-sensitivity attributes such as operation label, transport, duration, error category, and correlation ID.

## 12. Auditing logging layers outside the application

Even when WebGraphQlInterceptor is safe, credentials can still be logged at other layers:

| Component | Risk | Mitigation |
| --- | --- | --- |
| Reverse proxy / ingress | Logs URI/query string, headers, or request body | Log only necessary route info; strip Authorization/Cookie; do not log bodies. |
| API gateway / WAF | Request inspection or debug capture | Disable body capture containing credentials; enable policy-based redaction. |
| Web server access log | Logs query string or headers | Avoid raw request targets when GET requests may contain sensitive variables. |
| WebSocket frame logger | Logs connection_init payload and event frames | Never log auth payloads or frame contents. |
| RSocket logging | Logs metadata/setup payload | Redact credential metadata before logging. |
| APM agent | Automatically captures HTTP body, headers, and exceptions | Disable sensitive capture, configure field allowlists/denylists, and verify. |
| Container platform | Collects stdout/stderr | Never print secrets to console; restrict read permissions and retention. |
| CI/CD and startup diagnostics | Prints environment/configuration | Never dump full configs or secret environment variables. |

Do not assume that because one layer masks data, the next layer is also protected. Verify actual configurations from the client all the way to log storage.

## 13. Preventing log injection and log flooding

Operation names, user agents, correlation headers, error inputs, and certain client-sent metadata are untrusted data. Logging strings containing newlines or control characters directly lets attackers forge log entries or corrupt log structure.

Mitigations:

- Prefer allowlisted operation names.
- Enforce length limits on all client-controlled fields.
- Strip or encode CR, LF, and control characters before logging.
- Use structured logging instead of manual string concatenation.
- Never put raw GraphQL queries, aliases, paths, or variables into logs.
- Rate-limit and size-cap logs for repeated error requests.
- Avoid logging full stack traces for client-induced errors unless necessary.

Structured JSON encoders usually escape certain characters, but you still need to control field sizes and content. Do not treat encoding as a replacement for an allowlist.

## 14. Protecting logs after creation

Safe logs can still contain user references, operation metadata, IPs, or operational info. Protect the log storage system itself:

- Grant log read access only to groups who need it by role.
- Encrypt data in transit and at rest.
- Restrict retention according to purpose, regulations, and organizational policy.
- Audit log access, exports, modifications, and deletions.
- Separate application administration privileges from log administration privileges where possible.
- Protect log backups and replicas with the same controls as the primary store.
- Verify the logging pipeline does not silently drop critical security events.
- Do not retain temporary debug logs longer than necessary.

Not logging secrets does not mean skipping auditing. You can record who performed an action, what action was taken, what resource type was involved, the success/failure outcome, and safe reference IDs without logging credentials or sensitive payloads.

## 15. Testing to prove secrets never appear in logs

A useful test injects fake secret markers into various locations, executes requests, and verifies the markers never appear in captured logs.

Example test using Spring Boot OutputCapture:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.junit.jupiter.api.extension.ExtendWith;

@ExtendWith(OutputCaptureExtension.class)
class GraphQlLoggingSecurityTests {

    @Test
    void doesNotLogAuthorizationToken(CapturedOutput output) {
        String fakeToken = "test-token-DO-NOT-LOG-7f9a";

        // Send a GraphQL request via test HTTP client with an Authorization header.
        // The helper represents an application test fixture.
        performAuthenticatedGraphQlRequest(fakeToken);

        assertThat(output.getAll())
                .doesNotContain(fakeToken)
                .doesNotContain("Authorization: Bearer");
    }

    @Test
    void doesNotLogPasswordFromGraphQlVariables(CapturedOutput output) {
        String fakePassword = "test-password-DO-NOT-LOG-2c4e";

        performLoginMutation(fakePassword);

        assertThat(output.getAll())
                .doesNotContain(fakePassword);
    }
}
~~~

The two helpers in the example are application-provided test fixtures; they must send requests through the real HTTP handler and wait for requests to finish before inspecting output.

Expand tests to cover:

1. Authorization bearer tokens and cookie/session IDs.
2. Passwords, OTPs, and reset tokens in GraphQL variables.
3. Secrets written directly as literals inside GraphQL documents.
4. WebSocket connection_init payloads.
5. RSocket metadata if that transport is enabled.
6. GraphQLContext and Principal not being serialized.
7. Exception messages and validation errors not echoing secrets.
8. Mutation responses containing one-time tokens not being logged.
9. Structured logs, access logs, traces, and APM capture.
10. CR/LF and oversized payloads unable to forge or flood logs.

Use unique fake markers for each secret type to pinpoint exact data paths. Never use real credentials in tests, staging logs, or documentation examples.

## 16. Incident response workflow when a secret is found in logs

If a token or secret is discovered in logs, treat it as a credential exposure:

1. Identify the secret type, affected systems, and time window during which it was logged.
2. Restrict log read access and stop further log propagation.
3. Revoke or rotate the credential if it is still valid.
4. Identify copies: local files, log agents, SIEM, APM, backups, and exports.
5. Handle records per approved deletion/retention procedures; do not erase mandatory audit trails.
6. Audit log access during the exposure window.
7. Fix the logging source in the application, gateway, or agent.
8. Add a regression test confirming the secret marker no longer appears.

Deleting a log line in one dashboard is insufficient if data was already copied to other systems. If the credential may have been accessed, rotating/revoking it matters far more than merely hiding it in a viewer.

## 17. Common issues

| Symptom | Cause | Solution |
| --- | --- | --- |
| Token appears in DEBUG logs | Logging entire request or headers | Remove log dump; use allowlisted metadata. |
| Password recorded in mutation trace | APM auto-captures GraphQL body/variables | Disable body capture or configure redaction at the agent. |
| Token appears in WebSocket logs | Debug frame logger records connection_init | Do not log frame payloads; log only message type and handshake result. |
| Secret still appears after masking variables | Secret sits in literals or another nested input | Do not log documents/bodies; prefer an allowlist. |
| Raw session ID used for correlation | Treating a credential as a request identifier | Generate a new correlation ID or use an HMAC fingerprint. |
| MDC leaks token on every log line | Putting Authorization into MDC | Put only safe metadata in MDC and clear context with lifecycle. |
| Exception log leaks connection string | Uncontrolled logging of full exception message/stack trace | Standardize errors; restrict sink access if stack traces are needed. |
| Gateway log leaks query variables | GET requests or access logs include query strings | Never put secrets in URLs; configure route-safe access logs. |
| Secret leaked in startup logs | Dumping environment/configuration | Log only configuration names or secret references, never values. |

## 18. Checklist for never logging tokens and secrets

1. Use an allowlist for application logs; never dump entire requests/responses.
2. Never log Authorization, Cookie, Set-Cookie, API keys, or credential headers.
3. Never log GraphQL documents, variables, or raw request bodies.
4. Never log GraphQLContext, Principal, Authentication, or RSocket metadata.
5. Never log WebSocket connection_init payloads or frames containing sensitive data.
6. Never log mutation responses containing tokens, keys, or secrets.
7. Never log exception messages/stack traces that have not been vetted for sensitive data.
8. Use only server-generated correlation IDs; pseudonymize user/session references when needed.
9. Redact before calling the logger; do not rely on post-collection processing.
10. Control MDC, structured logging, tracing, APM, and gateway/access logs.
11. Sanitize client-controlled data to prevent log injection and log flooding.
12. Restrict read permissions, retention, exports, and backups of logs.
13. Test with fake secret markers across all enabled transports.
14. Maintain a credential revoke/rotate and log-copy cleanup process if a leak is detected.

Never logging tokens and secrets is a cross-cutting requirement from GraphQL resolvers down through transports, gateways, APMs, and log storage. Spring for GraphQL provides interceptors for request-level metadata logging, yet the application must proactively choose which fields are permitted. By logging via an allowlist, avoiding payload/context serialization, pseudonymizing correlation identifiers, and testing the full pipeline, operations teams can still trace requests without turning logs into a credential store.

References:
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Logging and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
