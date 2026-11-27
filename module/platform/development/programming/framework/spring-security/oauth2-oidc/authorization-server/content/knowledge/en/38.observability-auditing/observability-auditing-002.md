# Redacting Tokens, Secrets, Authorization Codes, and Personal Data in Logs

An Authorization Server handles many values that can grant access or reveal a user's identity. A seemingly harmless log line can contain an access token, refresh token, authorization code, client secret, session cookie, or ID token claim. Once logs are forwarded to a centralized logging system, APM, analytics service, or backups, those values can outlive the request lifecycle and become accessible to far more people than the original business data.

In Spring Authorization Server, logging must be designed alongside the authorization code, PKCE, refresh token, introspection, revocation, and OpenID Connect flows. The goal is to retain enough information for operations, troubleshooting, and auditing while ensuring that logs never become a replica of credentials or personal data.

## 1. Identifying Data That Must Never Be Logged

Treat all data passing through OAuth 2.0/OIDC endpoints as potentially sensitive until explicitly classified. The following fields must never be logged in raw form:

| Data | Where It Typically Appears | How to Handle |
|---|---|---|
| Access token, refresh token, ID token, and device code | Token endpoint response; introspection, revocation, or userinfo requests | Do not log the value, not even a partial token. Use a request ID or internal reference ID if correlation is needed |
| Authorization code | Redirect URI query string after the authorization endpoint; request sent to the token endpoint | Do not log query strings, request bodies, or codes |
| Client secret and client assertion | Form body, HTTP Basic Authorization, or JWT assertion in client authentication | Do not log Authorization headers, assertions, or secrets |
| PKCE code_verifier | Token request form body | Do not log the token endpoint request body |
| State, nonce, and device user_code | Authorization request, callback, or device authorization flow | Do not log values; log only validation outcomes and event codes |
| Cookies, session IDs, and CSRF tokens | Cookie, Set-Cookie, or session-related headers | Exclude from access logs, application logs, and traces |
| Personal data | Principal, Authentication, ID token claims, userinfo, and profile data | Do not log by default; if needed for auditing, use an approved pseudonymized reference |
| Signing keys and private keys | JWK private members, keystores, environment variables, or deployment configuration | Do not log key material, keystore passwords, or secret values from configuration |

Fields inside a JWT must also be protected. Do not log an entire JWT to inspect sub, email, name, phone_number, address, or other claims. The fact that a token is signed or encrypted does not make its contents suitable for logging.

Do not log entire HttpServletRequest, Authentication, OAuth2Authorization, OAuth2Token, principal, claims, or request/response DTO objects. These objects may contain credentials in nested fields, toString() output, or error details. Select only the safe individual fields to log rather than serializing the entire object.

## 2. Designing Logs with an Allowlist

A secure logging policy starts with an allowlist: each event emits only pre-defined fields. Do not rely on a denylist as the primary safeguard, because a new protocol extension or library version may introduce sensitive fields that the filter does not yet recognize.

An OAuth event typically only needs information such as:

- Event name, timestamp, and success/failure outcome.
- Server-generated or system-generated request ID or trace ID.
- Configured client alias approved to appear in logs.
- Grant type or operation type, taken from a controlled set of values.
- Scope count or classified scope group, if genuinely needed.
- Standardized internal error code, not the raw exception message or text containing request data.
- Pseudonymized subject reference if audit requirements call for correlating multiple events for the same user.

Example of a safe audit event:

~~~json
{
  "event": "oauth.token.issued",
  "timestamp": "2026-11-16T14:25:30Z",
  "request_id": "req-7f2a91",
  "client_alias": "customer-portal",
  "grant_type": "authorization_code",
  "scope_count": 2,
  "outcome": "success"
}
~~~

request_id must be generated on the server side or by a trusted gateway. Do not blindly trust a client-supplied header and use its raw value as the correlation ID. When logging the client, prefer an internal alias; client_id is not a client secret, but it can still reveal the system's integration structure.

If auditing requires correlating events by user, you can generate subject_ref using HMAC-SHA-256 with a private key managed in a secret manager. Keyed HMAC prevents direct lookup-table correlation unlike a plain hash of an email or username. Do not use raw sub, email, or phone number values as correlation keys. Restrict access to the HMAC key, define its lifecycle, and establish a key rotation plan.

## 3. Safe Logging in a Spring Application

Create a dedicated class to emit audit events. This class accepts selected values from the business flow and only logs fields belonging to the allowed schema. The example below uses SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public final class OAuthAuditLog {

    private static final Logger log =
            LoggerFactory.getLogger(OAuthAuditLog.class);

    public void tokenIssued(
            String serverRequestId,
            String clientAlias,
            String grantType,
            int scopeCount) {

        log.info(
                "oauth.audit event=token_issued requestId={} " +
                        "clientAlias={} grantType={} scopeCount={} outcome=success",
                safeLabel(serverRequestId),
                safeLabel(clientAlias),
                safeGrantType(grantType),
                Math.max(scopeCount, 0)
        );
    }

    private static String safeLabel(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }

        String normalized =
                value.replaceAll("[\\r\\n\\p{Cntrl}]", "_");
        return normalized.substring(0, Math.min(normalized.length(), 64));
    }

    private static String safeGrantType(String value) {
        if (value == null) {
            return "unknown";
        }
        return switch (value) {
            case "authorization_code", "refresh_token", "client_credentials" -> value;
            default -> "other";
        };
    }
}
~~~

serverRequestId must come from a trusted request ID generator. clientAlias must be looked up from internal configuration rather than taken directly from an arbitrary request string. grantType should be a controlled value. The safeLabel helper limits length and strips control characters to reduce log injection risk; it does not replace data classification. If a value is not on the allowlist, do not include it in logs.

When handling tokens in Spring Authorization Server, avoid logging patterns such as:

~~~java
// Unsafe: objects may contain tokens, principals, or credentials.
log.debug("authorization={}", authorization);
log.debug("authentication={}", authentication);
log.debug("token response={}", tokenResponse);

// Unsafe: headers and bodies may contain bearer tokens, codes, or secrets.
log.debug("authorizationHeader={}", request.getHeader("Authorization"));
log.debug("requestBody={}", requestBody);
~~~

Instead, log a standardized event such as token_issued, token_refresh_failed, authorization_denied, or token_revoked, along with the request ID, client alias, grant type, and outcome code. For errors, prefer internal error codes such as invalid_grant or client_authentication_failed. Do not append exception.getMessage() to logs if the message may contain URLs, parameters, tokens, or user data. Stack traces must also be controlled because exception messages and object values can appear in them.

Do not enable broad DEBUG or TRACE logging for org.springframework.security, Spring Authorization Server, or OAuth processing filters in production without inspecting the actual log output first. When needed for diagnostics, enable it only briefly, restrict access, and verify beforehand that the configuration does not log credentials or payloads.

## 4. Protecting Request Logs, Access Logs, and Traces

Configuring the application logger alone is not enough. An authorization code can appear in a callback URL; a client secret, code verifier, and refresh token can be in the body; bearer tokens and cookies can be in headers. Proxies, web servers, tracing agents, and APM tools can all record requests before the application processes them.

**At the application layer:** For /oauth2/authorize, /oauth2/token, /oauth2/introspect, /oauth2/revoke, device authorization, and OIDC userinfo endpoints, log only the method, normalized path, status, processing duration, and request ID. Do not log the query string, Authorization header, Cookie, Set-Cookie, or body. If using CommonsRequestLoggingFilter, do not enable includePayload, includeHeaders, or includeQueryString for these endpoints.

**At the reverse proxy:** Avoid logging variables that contain the full request line or query string. With Nginx, you can define an access log that only uses the URI path and operational metadata:

~~~nginx
log_format oauth_safe
    '$request_method $uri $status $body_bytes_sent $request_time';

access_log /var/log/nginx/oauth_access.log oauth_safe;
~~~

$uri does not contain query arguments. Avoid including $request, $request_uri, $args, $http_authorization, $http_cookie, or $http_referer in this format. If IP addresses must be logged for abuse prevention or incident investigation, treat them as personal data and restrict access permissions and retention periods according to organizational policy.

**In tracing and APM:** Attach only approved attributes such as route template, HTTP status, grant type, outcome, and trace ID. Do not attach request/response bodies, tokens, claims, cookies, or full URLs with query strings to spans. Also inspect auto-instrumentation because agents may automatically capture headers or payloads.

**In MDC:** Put only the request ID, trace ID, and safe labels into MDC. Do not put tokens, usernames, emails, session IDs, or request content into MDC. Remove added values in a finally block so data from a previous request does not leak into the next request when threads are reused:

~~~java
MDC.put("requestId", serverRequestId);
try {
    // Execute business logic and emit safe audit events.
} finally {
    MDC.remove("requestId");
}
~~~

If using Tomcat access logs, avoid patterns that log the raw request line such as %r when requests may contain sensitive query parameters; log only the path and approved operational fields. The configuration must be verified on the exact server version being run.

## 5. Distinguishing Audit Logs and Diagnostic Logs

Audit logs answer: who or which client performed what kind of operation, at what time, with what outcome, and to which request the event belongs. Diagnostic logs help find technical errors such as timeouts, database connection failures, or token signing errors. Both log types have different purposes, audiences, and retention periods, yet both must follow the rule of containing no credentials.

For an Authorization Server, useful audit events include token issuance, token refresh, token revocation, introspection, consent approval or denial, failed logins, and client configuration changes. Each event should record only minimal metadata. For example, log scope_count or classified scope groups instead of the full list of scopes if scope names could reveal sensitive permissions.

Store centralized logs in a system with role-based access control, encryption in transit and at rest, access monitoring, clear retention periods, and policy-driven deletion workflows. Audit logs require mechanisms to detect unauthorized modification or deletion. Do not grant broad read access to OAuth logs on par with general application logs.

## 6. Testing to Detect Leaks

Tests must prove that sensitive values do not appear in logs after traversing each flow. Use synthetic test data with easily recognizable markers, such as test-access-token-DO-NOT-LOG, test-refresh-token-DO-NOT-LOG, test-client-secret-DO-NOT-LOG, and dummy email addresses. Do not use live tokens or active secrets as test data.

A basic assertion on captured logs:

~~~java
assertThat(capturedLog)
        .doesNotContain(
                accessToken,
                refreshToken,
                authorizationCode,
                clientSecret,
                codeVerifier,
                testEmail
        );
~~~

Run tests across authorization code with PKCE, code-to-token exchange, refresh token, revocation, introspection, client authentication, and userinfo. Check application logs, proxy/web server access logs, traces/APM, and exception-collection systems. A test that only checks the in-application logger will not catch gateways or agents logging full URLs and headers.

In addition to checking for sensitive strings, verify that logs still contain required operational fields such as event name, request ID, route, status, duration, and outcome. That way operations teams can still trace events without reading credentials.

## 7. Responding When a Secret Leaks into Logs

Treat any token or secret that appears in logs as compromised data. Identify the credential type, time window, logging systems that received the data, people or services that accessed it, and copies that were created. Revoke still-valid tokens; rotate affected client secrets or keys according to key management procedures; evaluate related active sessions and authorizations. For signing keys, coordinate the rollover plan with the validity window of already-issued tokens to avoid creating verification gaps.

After containment, handle copies in centralized logs, APM, exports, and backups in accordance with retention policies and incident response procedures. Document the impact scope using safe metadata, fix the configuration at the source, and re-run canary tests to confirm the data no longer appears. Deleting a single line in an application log does not resolve copies already shipped to other systems.

## 8. Pre-Production Checklist for the Authorization Server

- [ ] Do not log access tokens, refresh tokens, ID tokens, authorization codes, device codes, client secrets, client assertions, or PKCE verifiers.
- [ ] Do not log Authorization, Cookie, or Set-Cookie headers, request bodies, response bodies, or query strings of OAuth/OIDC endpoints.
- [ ] Do not serialize Authentication, principal, OAuth2Authorization, token objects, or claims into logs.
- [ ] Audit events use an allowlist schema, trusted request IDs, and standardized error codes.
- [ ] Client identifiers and subject references are handled according to data classification policy.
- [ ] Proxies, web servers, tracing agents, APM, and exception reporters have been verified separately.
- [ ] MDC contains only safe metadata and is cleared after each request.
- [ ] Tests using synthetic secrets confirm sensitive values do not appear in any log sink.
- [ ] Centralized logs have access controls, encryption, access monitoring, and appropriate retention periods.

When these controls are applied consistently, Spring Authorization Server logs continue to support token lifecycle monitoring, troubleshooting, and auditing of OAuth 2.0/OIDC flows without retaining values that could be used to hijack access or identify users.
