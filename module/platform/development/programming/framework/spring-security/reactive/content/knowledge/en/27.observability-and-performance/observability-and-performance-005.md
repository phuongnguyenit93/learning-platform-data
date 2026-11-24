# Redacting Passwords, Authorization Headers, Cookies, and Personal Data in Logs — Spring Security Reactive

## 1. Objectives and Scope

Logs help diagnose authentication failures, authorization denials, latency, and HTTP incidents. However, in a Spring Security application running on Spring WebFlux, a single log line dumping an entire request, exception, or HTTP client exchange can leak passwords, bearer tokens, session cookies, refresh tokens, or personal data into log files, centralized log stores, traces, dashboards, and backups.

After this lesson, learners should be able to:
- Identify every log emission point that can receive sensitive data in a reactive flow.
- Design log events using an **allowlist of fields**; never serialize entire requests, responses, or security contexts.
- Distinguish between **omitting**, **redacting**, and **pseudonymizing**; choose the right handling per observability purpose.
- Write a safe HTTP filter for WebFlux, configure libraries, and test for leaks in both application logs and observability backends.

**Decision principle:** If a value is not genuinely needed for incident investigation, never emit that value into logs. Redaction at the log output step is only a supplementary defense layer, not a substitute for avoiding secret collection.

## 2. Why Are Logs a Data Leak Vector?

A request traverses many layers: reverse proxy/API gateway → Reactor Netty → WebFlux WebFilter → Spring Security WebFilterChain → controller/handler → WebClient or dependent services → logging/tracing/metrics. Any layer can log data before application-level masking runs. Logs are also replicated to collectors, APMs, SIEMs, support tickets, dumps, and backups with broader access permissions than business data.

Common cases:
1. Directly debugging headers exposes Authorization: Bearer ..., Authorization: Basic ..., Cookie, or Set-Cookie.
2. Logging request bodies on login, password-change, or account-creation endpoints exposes passwords, OTPs, and recovery codes.
3. Logging full URLs exposes emails, password reset tokens, and authorization codes in query strings; URL paths may also contain names or personal identifiers.
4. Printing intact Authentication, SecurityContext, Jwt, OAuth2AccessToken objects, or raw exceptions exposes principals, claims, credentials, or user input embedded in messages.
5. Enabling HTTP wiretap/access logs or logging WebClient requests/responses without controlling content.
6. Attaching emails, phone numbers, session IDs, or JWTs to trace baggage, span attributes, metric labels, or MDC and accidentally shipping them to an observability backend.

Do not assume a string that “only appears in DEBUG” is safe: log levels can be raised during troubleshooting, and once emitted, data is very difficult to purge from every replica.

## 3. Data Classification and Appropriate Actions

| Data | Source Examples | Logging Rule |
| --- | --- | --- |
| Passwords, password confirmation, PINs, OTPs, recovery codes | Forms, JSON bodies, queries, exceptions | **Never log** values, not even partially; log event codes like LOGIN_FAILED. |
| Authorization / Proxy-Authorization | Bearer JWT, opaque token, Basic credentials | **Never log** headers or tokens; if presence must be indicated, log only auth_present=true/false. |
| Cookie / Set-Cookie | Session ID, refresh token, CSRF token, preferences | Never log values, never dump the whole collection; custom cookies also require individual evaluation. |
| API keys, client secrets, access/refresh tokens | Headers, config, bodies, OAuth2/JWT | Never log; do not output raw claims, token prefixes/suffixes, or credential toString() output. |
| Email, phone number, full name, address, ID numbers, date of birth, IP address | Path, query, payload, principal, headers | Do not log by default. Retain only fields truly needed with clear business justification, protection level, and retention period. |
| Status and technical metrics | HTTP method, status, duration, static route name, normalized error code | Can be logged via allowlist after verifying fields contain no user data. |
| Correlation IDs | Server-generated request ID, trusted trace ID | Can be logged if not a token/session ID and not derived from personal data. |

Three techniques to distinguish:

- **Omit:** Do not include the field in the log event. Best suited for passwords, tokens, cookies, and payloads.
- **Redact:** If you need to indicate a sensitive field was present, log a constant [REDACTED] or a boolean flag. For example, auth_present=true; never pass the original value into format arguments, exceptions, or MDC.
- **Pseudonymize:** When events must be linked by an identifier, use a random investigation-session ID or HMAC with a separately managed secret key. Plain unsalted hashing of emails/phone numbers is not secure enough against dictionary attacks. Pseudonymized values may still count as personal data depending on context.

Do not treat “masking the last 4 characters”, URL encoding, Base64, or easily reversible encoding as adequate protection for bearer tokens. Tokens carrying access privileges must be treated like passwords.

## 4. Designing an Allowlist-Based Log Schema

Instead of logging entire objects, define events useful to operations:

| Field | Example | Notes |
| --- | --- | --- |
| event | http_request, auth_failed, downstream_error | Value from a fixed catalog, never raw exception text. |
| request_id | Server-generated UUID | Do not use session ID, access token, or email as a correlation ID. |
| method | GET, POST | Attribute provided by the framework. |
| route | /accounts/{accountId} | Take the registered **route template**; not the actual URL path containing IDs. |
| status | 200, 401, 403, 500, unset | unset if the response has no HTTP status yet; do not assume 200 on error. |
| duration_ms | 38 | Measured on a monotonic clock; independent of system wall clock. |
| failure_code | BAD_CREDENTIALS, ACCESS_DENIED | Fixed code; do not concatenate username, bearer token, or request details. |

Example of safe events (illustrative values only):

~~~text
event=http_request request_id=2d894fd1-12e6-4fc8-aa7b-9dedf380780d method=POST route=/login status=401 duration_ms=24 signal=on_complete
event=auth_failed request_id=2d894fd1-12e6-4fc8-aa7b-9dedf380780d failure_code=BAD_CREDENTIALS
~~~

Do not include in the schema: bodies, query strings, full URLs, arbitrary headers, cookies, credentials, access tokens, JWT claims, principal.toString(), or stack traces whose messages contain request input. Even JSON object keys can be sensitive if not curated.

## 5. Safe Access Log WebFilter Pattern in Spring WebFlux

The following example uses Java 17+, Spring Framework 6 / Spring Boot 3, Spring WebFlux, and SLF4J. This is a component class for a Spring application with the corresponding dependencies; it is not a standalone Java program runnable with `javac` alone. The class logs only allowlisted fields. When a handler matches a route, it uses the framework's pattern rather than the actual path; for unmatched requests, it uses the literal `unmatched`.

~~~java
package example.logging;

import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class SafeHttpLoggingWebFilter implements WebFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeHttpLoggingWebFilter.class);

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        long started = System.nanoTime();
        String requestId = UUID.randomUUID().toString();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched"
                            : pattern.toString();

                    HttpStatusCode status = exchange.getResponse().getStatusCode();
                    String statusCode = status == null
                            ? "unset"
                            : Integer.toString(status.value());

                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    LOG.info(
                            "event=http_request request_id={} method={} route={} " +
                            "status={} duration_ms={} signal={}",
                            requestId, method, route, statusCode, elapsedMs,
                            signal.name().toLowerCase(Locale.ROOT));
                })
                .contextWrite(context -> context.put("requestId", requestId));
    }
}
~~~

**Technical explanation:**
- WebFilter runs inside reactive processing; chain.filter(exchange) returns Mono<Void>. doFinally runs when the subscription completes, errors, or is cancelled. Logging the signal helps distinguish scenarios, while status may not be set yet; unset accurately represents that state.
- It does not read exchange.getRequest().getURI(), getQueryParams(), getHeaders(), getCookies(), the request body, or the principal. Thus URLs containing tokens or cookies carrying sessions cannot alter what the filter emits.
- HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE is read after the chain executes. When the framework has no pattern, the filter falls back to unmatched. Use only patterns from trusted route configurations; if the system builds routes dynamically from user data, normalize them further.
- The server-generated UUID enables correlation. contextWrite passes requestId through Reactor Context to downstream reactive operators; the code does not rely on ThreadLocal/MDC to preserve IDs across threads.
- It does not log the response body. If the application already has a trustworthy trace ID system, you can use the controlled trace ID instead of generating an independent request ID to correlate events consistently.

**Filter placement:** Spring Security WebFlux also uses WebFilters; verify the actual filter order and scope when integrating with SecurityWebFilterChain. The example filter focuses on data safety; a requirement that “every request has an access log” must also account for errors at the Netty layer, gateway, and requests that never enter WebFlux.

## 6. Dangerous Logging Patterns and Safe Alternatives

The lines below illustrate **what to avoid**, placed in a context where exchange or jwt already exists; this is not a standalone program:

~~~java
// Dangerous: may contain Authorization, Cookie, API key.
log.debug("headers={}", exchange.getRequest().getHeaders());

// Dangerous: query/path may contain reset_token, email, phone number.
log.info("uri={}", exchange.getRequest().getURI());

// Dangerous: logs the entire JWT or credential contents.
log.debug("jwt={}", jwt.getTokenValue());

// Dangerous: object toString may contain unexpected data.
log.warn("authentication={}", authentication);
~~~

Replace with predefined events:

~~~java
// method, route, and statusCode variables are controlled values.
log.info("event=http_request method={} route={} status={}",
        method, route, statusCode);

// Only log stable error codes; never log username or credentials.
log.warn("event=auth_failed reason=BAD_CREDENTIALS");
~~~

**Never log the entire header collection hoping a regex in the log sink will catch all secrets.** Custom header names like X-Api-Key, X-Auth-Token, or partner-defined headers easily bypass denylists; secret strings can appear outside expected fields. If observing headers is necessary, pick only individually verified safe headers and validate both names and values against policy. Content-Type or User-Agent also need evaluation when they can hold arbitrary data.

## 7. Login, Authentication Failures, and Authorization in Spring Security Reactive

The most sensitive paths are typically login, password change, forgot-password, OAuth2 callbacks, token refresh, and CSRF/session handling. For Spring Security:

1. **Authentication failure:** Log auth_failed and a normalized reason code (BAD_CREDENTIALS, ACCOUNT_LOCKED, TOKEN_EXPIRED when classified in a controlled way). Do not print username, form login body, uncontrolled AuthenticationException.getMessage(), or the Authentication object.
2. **Authorization failure:** Log access_denied, route pattern, HTTP status, and request ID. Do not log full GrantedAuthority sets, security contexts, or JWT claims by default; roles can reveal internal privileges.
3. **JWT/OAuth2:** Do not log getTokenValue(), token strings, authorization codes, refresh tokens, ID tokens, or full claims lists. If error statistics are needed, use internally defined codes like INVALID_SIGNATURE, EXPIRED, MISSING_TOKEN and aggregate counts.
4. **Session/cookie:** Do not log JSESSIONID, SESSION, XSRF-TOKEN, or Set-Cookie. Cookies flagged HttpOnly or Secure still appear in HTTP headers on the server; those flags do not stop the server from logging them.
5. **Exceptions and stack traces:** An exception message can contain paths, inputs, response bodies, or user data. Log only approved exception classes or mapped error codes. When stack traces are genuinely needed for investigation, review messages, storage location, read permissions, and retention before enabling.

Example of formatting a usable authentication event:

~~~text
event=auth_failed request_id=<server-generated-id> mechanism=password failure_code=BAD_CREDENTIALS
event=access_denied request_id=<server-generated-id> route=/admin/reports status=403
~~~

The `<server-generated-id>` marker above is an illustrative placeholder, not fixed log output. Keep user-facing responses appropriately generic to avoid revealing whether an account exists; login response messaging policy is separate from logging policy.

## 8. WebClient and Reactor Netty: Preventing Leaks at Lower HTTP Layers

WebClient is widely used in WebFlux services. Interceptors or ExchangeFilterFunctions can easily log request.headers(), request.url(), or response bodies accidentally when debugging downstream errors. In particular, reactive bodies are single-consumption streams: reading a body just to log it can alter behavior, consume memory, violate backpressure, and put sensitive data into logs.

You can log a fixed service name, method, and status instead of URLs/headers/bodies. Example bean in a Spring application, with a target name decided at design time:

~~~java
package example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class SafeWebClientConfiguration {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeWebClientConfiguration.class);

    @Bean
    WebClient billingWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://billing.example.internal")
                .filter((request, next) ->
                        next.exchange(request)
                                .doOnNext(response -> LOG.info(
                                        "event=outbound_http service=billing " +
                                        "method={} status={}",
                                        request.method().name(),
                                        response.statusCode().value())))
                .build();
    }
}
~~~

This is a bean example requiring a Spring WebFlux project and a real base URL supplied via configuration at deployment. To record latency/errors, you can extend it with doOnError or doFinally, logging only error types/normalized codes rather than arbitrary exception messages or response bodies. Do not automatically turn request.url() into a log field even if the host looks static: queries/paths can contain tokens.

**Reactor Netty wiretap:** Configurations enabling wiretap and DEBUG/TRACE can emit headers and network payloads depending on mode. Never enable payload-logging wiretap in environments with real data just to troubleshoot. If transport-layer diagnostics are unavoidable, use an isolated environment with synthetic data, a very short time window, formal approval, and strict access control.

**Reactor Netty, proxy, and gateway HTTP access logs:** These are separate log sources; they can log request targets including query strings before WebFilter runs. You must check formats/components and redaction policies at each of those layers individually. A safe WebFlux filter does not automatically sanitize logs emitted by Netty or a reverse proxy.

## 9. Controlled Log Level Configuration

Example baseline configuration for application.yml:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: INFO
    org.springframework.web: INFO
    reactor.netty: INFO
~~~

The purpose is to avoid broadly enabling DEBUG/TRACE for HTTP- and security-related packages in environments with real data. These levels are **not a data-masking mechanism**: a mistaken log.info statement still leaks; another logger or separate access log/wiretap config can still emit data. Check the effective configuration of every deployment profile, communication library, gateway, sidecar, APM agent, and log collector.

If the system uses JSON/structured logging, serialize only approved field DTOs/schemas. Masking filters in encoders, collectors, or SIEMs can serve as a backup to catch oversights, but cannot guarantee stripping all variants of secrets, encoded strings, multiline payloads, or logs from third-party libraries.

## 10. Reactor Context, MDC, and Tracing

A reactive pipeline can switch threads via publishOn, subscribeOn, or during I/O; a ThreadLocal/MDC set on the request-receiving thread is not guaranteed to be present in every callback. Never treat missing MDC as a reason to copy Authentication, bearer tokens, or personal information into MDC.

- Propagate **only safe metadata** (request ID, controlled trace ID, operation name) via Reactor Context. If MDC population is required, use a context propagation mechanism compatible with your Reactor/Micrometer version and always clean up within the proper scope.
- Never put raw Authorization headers, cookies, tokens, emails, or bodies into Reactor Context, MDC, tracing baggage, span names, or span attributes.
- Span names should be operation names or route templates, such as HTTP GET /orders/{id}; never use raw URLs with queries or paths containing identifiers.
- Avoid metric labels containing user IDs, emails, tokens, or free-form request values: they are both sensitive and high-cardinality. Use method, route template, status, and error class from fixed catalogs.
- Inspect auto-instrumentation tools: agents may automatically capture HTTP URLs, request headers, query params, or exception messages; enforce allowlists/redaction in agent and backend configs, not only in source code.

A request ID used for correlation must never be used as an authentication secret. If accepting X-Request-ID from clients, treat it as untrusted input: accept only bounded length/character sets, block newline injection, or generate your own ID. Never use a client-supplied header value verbatim as a log field.

## 11. When Business Payload Observation Is Mandatory

Some flows require evidence of transaction state or processing steps. Log **business events with safely extracted fields** instead of raw request/response JSON: event=payment_confirmed, result=declined, provider_code from an allowlist; never store card numbers, CVVs, access tokens, passwords, or free-form content.

Field selection process:
1. State the exact operational question to answer; select only fields that answer that question.
2. Identify which sources are user/partner-controlled and could contain secrets even inside error messages.
3. Choose bounded value types (enum, boolean, status, numeric measurement). Drop free-form strings by default.
4. Assess impacts on personal data, read permissions, retention, exports, and backups.
5. Test error, retry, timeout, cancellation, and abnormal response paths.
6. Re-review whenever endpoints, DTOs, SDKs, or instrumentation change.

Encrypting sensitive data in centralized storage may protect data at rest, but does not make writing secrets to logs necessary or safe. Once copied across observability systems, secrets are very difficult to delete everywhere in sync.

## 12. Leak Testing with Sentinels and Log Readback

Do not rely solely on code review; inspect the **actual output** of loggers, gateway access logs, tracing, and collectors in a test environment.

**Minimum test suite:**

| Test Scenario | Deliberately Injected Test Data | Expectation |
| --- | --- | --- |
| Failed login | password=PASSWORD_SENTINEL_731 | No sentinel in logs, traces, error messages, or unintended responses. |
| Invalid Bearer | Authorization: Bearer TOKEN_SENTINEL_742 | Only normalized event/error code; no token or partial token. |
| Session cookie | Cookie: SESSION=COOKIE_SENTINEL_753 | No cookie value in application, proxy, or Netty logs. |
| URL with sensitive query | /reset?token=QUERY_SENTINEL_764 | HTTP log uses route template, not actual URL/query. |
| Payload with PII | email=PII_SENTINEL_775 | No email/raw body in any log sink. |
| Downstream error | response body contains ERROR_SENTINEL_786 | No raw body or exception message containing sentinel logged. |

The sentinels above are test strings, not real credentials. Also test strings with spaces, newlines, and URL-encoded variants if the logging layer transforms data. Test GET/POST, 2xx/4xx/5xx, errors before route matching, timeouts, retries, and cancellations. Collect logs from all real sources, search for both raw and encoded representations, and verify allowlisted fields still provide method, route, status, duration, and request ID for operations.

With Spring Boot, you can use WebTestClient to send requests and OutputCaptureExtension (spring-boot-test) to capture output in integration tests; results will depend on the app, endpoints, and appenders. **Assert absence of sentinels**, while also asserting expected events exist. A unit test on a single string-masking helper cannot prove the gateway, Netty, or APM does not leak data.

Protection tests must be re-run when upgrading Spring Security or Reactor Netty, changing log levels, or adding new filters/instrumentation. Use fake secrets in development; never use real passwords or tokens to demonstrate logging features.

## 13. Operations, Storage, and Incident Response for Leaks

- Apply least privilege for viewing dashboards, querying logs, exports, archives, and support attachments; audit access to sensitive data where supported.
- Set retention according to real investigation needs; control backups and third-party data-copy pipelines. Redaction in the UI viewer is insufficient because raw data may remain in indexes/storage.
- If tokens/cookies are discovered in logs: stop the emitting source, invalidate or revoke potentially exposed tokens/sessions, rotate affected credentials, assess data scope and replicas, follow incident response procedures, and purge/delete per applicable policy. Never paste secrets into tickets or other logs when reporting the bug.
- For leaked personal data, handle according to security policies, data processing agreements, and applicable legal obligations. Do not assume masking in a dashboard remedies the leak.

## 14. Common Mistakes and Self-Check Checklist

**Common pitfalls:**
- Masking only the keyword password while forgetting Authorization, Cookie, X-Api-Key, refresh_token, custom headers, or different letter casings.
- Logging entire ServerWebExchange, HttpHeaders, request URI, Authentication, or Jwt via toString() thinking they hold only metadata.
- Using raw URLs to group logs/traces/metrics instead of route templates.
- Believing INFO level, HttpOnly cookies, TLS, or disk encryption automatically prevents log leaks.
- Checking only controller logs while overlooking WebClient, proxies, Netty, APM agents, and exception handlers.
- Using unsalted email hashes as “anonymization” or putting user IDs into metric labels, making correlation/guessing easy or causing cardinality explosions.
- Enabling wiretap, verbose access logs, or DEBUG/TRACE in production and forgetting to turn them off.

**Pre-release checklist:**
- [ ] Log schema consists primarily of event/method/route-template/status/duration/request_id and allowlisted error codes.
- [ ] No request/response bodies, full headers/cookies, raw URIs, passwords, tokens, claims, credentials, or PII appear in logs.
- [ ] Spring Security/WebFlux/WebClient/Reactor Netty/gateway/observability agents have each been verified separately.
- [ ] Error logging does not automatically emit exception messages containing user input.
- [ ] Reactor Context, MDC, trace baggage, and metric attributes carry only safe metadata.
- [ ] Sentinel tests across both success and error paths, in all relevant log sinks, pass.
- [ ] Access permissions, retention periods, and log export paths are restricted; credential revocation procedures exist for leaks.

**Remember:** In a Spring Security Reactive application, protecting logs starts with **never putting secrets into log events**. A useful HTTP event can still tell you what happened, on which route, when, how long it took, and which request it correlated with—without knowing the user's password, Authorization header, cookie, or personal information.
