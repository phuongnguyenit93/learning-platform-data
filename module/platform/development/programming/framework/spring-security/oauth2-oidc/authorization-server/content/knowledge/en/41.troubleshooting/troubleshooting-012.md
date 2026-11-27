# Reproducing Errors with Masked Logs and Minimal Requests

When an Authorization Server fails, logs typically show which components a request traversed, which status the endpoint returned, and which OAuth error was reported. However, logging full requests or enabling broad DEBUG logging can expose authorization codes, access tokens, refresh tokens, session cookies, client secrets, and user data. A sound diagnostic workflow must retain enough evidence to reconstruct what happened while stripping values that could be used to sign in or call APIs.

This lesson explains how to investigate OAuth 2.0/OpenID Connect errors using structured masked logs, correlate events across multiple services, distill a flow into minimal requests, and reproduce issues safely in a Spring Authorization Server test environment.

After completing it, you will be able to:

- Build a timeline from reverse proxy, Authorization Server, and Resource Server logs using request IDs or trace IDs.
- Decide which fields to keep, which to remove, and which to replace with aliases.
- Turn an observed failure into a testable hypothesis.
- Reconstruct minimal authorization requests and token requests with a test client.
- Document reproduction findings so others can verify them without receiving secrets.

## 1. Diagnostic Principles

The goal of reproducing an error is proving that a specific condition produces the observed behavior. You do not need to replay an entire user session if the failure can be reproduced with a smaller request.

The workflow should follow four principles:

1. **Start from evidence**: use timestamps, endpoints, HTTP statuses, OAuth errors, and request/trace IDs to establish what flow actually ran.
2. **Keep structure, drop secrets**: logs should show which parameters were present and which check failed without storing credential values.
3. **Vary one thing at a time**: change only a single condition per attempt, such as redirect URI, code verifier, scope, or client configuration.
4. **Reproduce with test data**: use fresh test clients, accounts, and authorization codes in a test environment; never replay tokens or codes taken from a real incident.

Logs are evidence of system behavior. Logs are not a complete copy of the request, especially once sensitive data is stripped. When a needed field is missing, add a safe diagnostic event for the next run instead of trying to recover secrets from old logs.

## 2. Preparing Log Correlation

An OAuth request may traverse a CDN, load balancer, ingress, Authorization Server, data store, and Resource Server. If each component uses a different identifier or clocks drift, reconstructing event order becomes difficult.

### 2.1. Request ID and Trace ID

Each request should receive a unique request ID at the ingress boundary. If the system uses distributed tracing, propagate trace context per the deployed standard, such as W3C Trace Context via the traceparent header. Logs at each service record the same trace ID and corresponding span ID.

| Field | Purpose | Notes |
|---|---|---|
| request_id | Look up a single request within one service | Generated at gateway or application; validate format and length limits |
| trace_id | Link spans in one flow across multiple services | Never use as a credential or authentication data |
| span_id | Identify one operation within a trace | Each component can create its own span |
| event | Business or technical event name | Use stable names such as oauth.token.exchange.failed |
| timestamp | Order events | Record in UTC and synchronize clocks across nodes |
| route | Normalized endpoint | Use route templates; never log query strings |

Never blindly trust request IDs sent from the Internet. The gateway should strip arbitrary client-supplied values and mint a fresh ID, or validate format before accepting. IDs serve observability only and must never grant permissions.

If distributed tracing is not yet in place, you can still use a request ID generated at the reverse proxy and forwarded via an internal header. The application must accept this header only from trusted proxies. Across multiple hops, document whether the ID is preserved or mapped to an internal ID.

### 2.2. Clock Synchronization and Service Identity

Record timestamps in UTC with sufficient precision to order closely spaced events. Synchronize node clocks via NTP or an equivalent service. Logs should include service name, environment, application version, and instance/pod so you can spot failures affecting only one replica.

When aggregating logs, sort by timestamp yet rely on trace/span relationships to establish causality. Two requests with adjacent timestamps do not necessarily belong to the same flow.

### 2.3. Events Worth Recording

For the Authorization Server, record normalized events for key steps:

- Receiving the authorization request and validation results for client, redirect URI, response type, scope, and PKCE.
- Starting and completing user authentication; login outcome at success/failure level.
- Displaying or completing consent by status, without recording personal data contents.
- Issuing an authorization code and code exchange result at the token endpoint.
- Client authentication, grant check, redirect URI, PKCE, and token issuance result.
- Request rejection with HTTP status and OAuth error code.
- Access token validation at the Resource Server, recording only the outcome and needed error category.

Event names should describe the action and result, such as oauth.authorization_request.rejected, oauth.user_authentication.failed, oauth.token.exchange.failed, or oauth.access_token.validation.failed. Avoid a generic message like authentication error for every case.

## 3. Masking Sensitive Data Before Logging

Design logging around an allowlist: record only fields required for diagnosis. Do not log full headers, query strings, or request bodies and rely on a downstream scrubber to remove secrets at log export time.

### 3.1. Values to Remove or Alias

| Data | How to Handle in Logs | Reason |
|---|---|---|
| Authorization header, Basic credentials | Do not log value; if needed, log only authentication method | May contain client secret or access token |
| access_token, refresh_token, id_token | Do not log value | Can be used to access resources or login sessions |
| authorization code | Do not log value; log only issued, redeemed, expired, or rejected events | Short-lived, yet redeemable for tokens |
| client_secret, client_assertion, private_key_jwt | Do not log value or JWT assertion | Serves as client authentication proof |
| code_verifier | Do not log value; log only presence and PKCE validation result | Can be used to complete authorization code exchange |
| state, nonce | Do not log value; log only presence or match outcome | Tied to session correlation and replay protection |
| Cookie, Set-Cookie, session ID, CSRF token | Do not log value | Can hijack sessions or forge requests |
| Password, OTP, recovery code | Do not log in any form | Direct authentication credentials |
| Request object, JWT assertion, SAML response | Do not log intact payload or signature | May contain personal claims and auth data |
| Private key, keystore password | Do not log; exclude from diagnostic bundles | Infrastructure secrets |
| Email, phone number, user subject | Use aliases or pseudonyms when correlation is needed | Personally identifiable |
| Client certificate | Log only fingerprint or alias when truly needed; never private key | Fingerprint can still act as a stable identifier |

Replace entire sensitive values with a marker such as [REDACTED]. Do not mask only the middle while leaving leading/trailing characters of tokens, codes, or secrets, as remaining fragments can still leak data and encourage sharing credentials.

### 3.2. Fields Worth Keeping

The following fields are generally useful and lower-risk once normalized:

- HTTP method, route template, status code, duration, and service name.
- OAuth error codes such as invalid_request, unauthorized_client, invalid_grant, or invalid_scope.
- Grant type, response type, PKCE method, and authentication method.
- Client aliases such as diagnostic-public-client instead of production identifiers when exporting logs externally.
- Registered redirect URI aliases, e.g. callback-main, alongside redirect_uri_match.
- Allowlisted scopes if scopes do not reveal sensitive data.
- Check states such as client_authenticated, redirect_uri_match, code_expired, code_already_used, and pkce_validation.
- Request ID, trace ID, application version, and instance.

For state, nonce, code, and code verifier, presence alone is usually enough for diagnosis. For redirect URIs, log the configured alias and match result instead of raw URLs that could carry queries or user data.

### 3.3. Example of Logs Before and After Masking

An unsafe log might include full URLs with queries, Authorization headers, cookies, and request bodies. Never paste that kind of log into tickets or send it over chat for analysis.

Example of a normalized structured log:

~~~json
{
  "timestamp": "2026-11-16T14:20:31.418Z",
  "level": "WARN",
  "service": "authorization-server",
  "environment": "test",
  "event": "oauth.token.exchange.failed",
  "request_id": "req-7f21a9",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "instance": "authorization-server-2",
  "method": "POST",
  "route": "/oauth2/token",
  "http_status": 400,
  "client_alias": "diagnostic-public-client",
  "grant_type": "authorization_code",
  "pkce_method": "S256",
  "code_present": true,
  "code_verifier_present": true,
  "redirect_uri_alias": "callback-main",
  "redirect_uri_match": true,
  "pkce_validation": "failed",
  "oauth_error": "invalid_grant",
  "duration_ms": 14
}
~~~

This log shows that the token request failed at the PKCE validation step while confirming the redirect URI matched. It contains no authorization code, verifier, token, cookie, or user data.

Not every system can precisely distinguish code_expired, code_already_used, or pkce_validation. Log only outcomes the application genuinely observed; never guess and record speculation as fact.

## 4. Safe Logging at the Reverse Proxy and Application

### 4.1. Reverse Proxy

Access logs should record the normalized URI rather than the entire request line with query strings. With Nginx, you can define a minimal log format:

~~~nginx
log_format oauth_safe
    '$time_iso8601 request_id=$request_id '
    'method=$request_method uri=$uri '
    'status=$status request_time=$request_time';

access_log /var/log/nginx/oauth_access.log oauth_safe;
~~~

In this example, the uri variable logs only the normalized path, whereas request_line can contain query strings. Never add variables such as http_authorization, http_cookie, or request_body to access logs. If client IP addresses are needed for investigation, enforce dedicated policies on access control, retention, and anonymization.

If a load balancer sits in front of Nginx, configure trusted proxies and the real IP module strictly for the load balancer's address range. Never use client-supplied X-Forwarded-For values to determine identity or request origin.

### 4.2. Spring Boot and Spring Security

At the application layer, log events with explicitly chosen fields instead of serializing HttpServletRequest, all headers, or bodies:

~~~java
log.info(
    "oauth.request.completed requestId={} traceId={} route={} method={} " +
    "status={} durationMs={} clientAlias={} oauthError={}",
    requestId,
    traceId,
    routeTemplate,
    requestMethod,
    statusCode,
    durationMs,
    clientAlias,
    oauthError
);
~~~

routeTemplate should come from the fixed route or endpoint name, such as /oauth2/authorize and /oauth2/token. Never use request.getRequestURL() plus query string as the route field. clientAlias should be mapped from known client registrations rather than logging an arbitrary request-supplied value verbatim.

If using a OncePerRequestFilter or interceptor to populate request IDs, add the ID to MDC only after format validation and clear MDC inside a finally block to prevent leaking context across requests sharing a thread. Never place tokens, codes, or session IDs into MDC.

Do not enable global DEBUG/TRACE for Spring Security in production just to chase one bug. Some logging frameworks or libraries print request details, principals, or authentication data. Prefer allowlisted diagnostic events; if temporarily raising log levels is unavoidable, restrict it by package, instance, duration, and access controls, then revert configuration immediately once sufficient evidence is gathered.

## 5. Investigation Workflow from Logs to Hypotheses

### Step 1: Describe a Testable Symptom

Record what was observed with concrete facts:

- Occurrence timestamp and timezone.
- Environment, application version, and instance if known.
- Endpoint, HTTP status, and OAuth error code.
- Affected flow: authorization request, login, consent, token exchange, or Resource Server call.
- Expected behavior vs. actual behavior.
- Masked request ID or trace ID.

Avoid vague descriptions like OAuth is broken. A concrete statement is: the token endpoint returns HTTP 400 with invalid_grant for the test client after the user completes the authorization code flow.

### Step 2: Gather Logs by the Same Request or Trace

Look up the request ID in reverse proxy and Authorization Server logs. If the request triggered downstream services, use the trace ID to find related spans. Pull a tight time window before and after the event to capture both initiation and final outcome.

Do not filter solely by client ID or IP address because one client can issue concurrent requests. Do not merge events merely because they occurred close together in time.

### Step 3: Build a Timeline

Order events by UTC timestamp, noting the emitting component and outcome:

| Order | Component | Event | Data to Verify |
|---|---|---|---|
| 1 | Ingress | Request arrives at Authorization Server | Route, method, status, request ID |
| 2 | Authorization Server | Authorization request validated | Client alias, response type, redirect URI match, PKCE method |
| 3 | Login/session | User authenticated | Login outcome, session status; never log cookies |
| 4 | Consent | User approved or denied | Consent outcome and scope aliases |
| 5 | Authorization Server | Authorization code issued | Issuance status, client alias, expiration time; never log code |
| 6 | Token endpoint | Code exchanged for token | Grant type, client authentication result, redirect URI match, PKCE result |
| 7 | Resource Server | Access token validated | Validation outcome and error code; never log token |

Not every request passes through all steps. Mark missing steps as not observed rather than assuming they failed.

### Step 4: Compare Expectations Against Reality

At each step, ask two questions: what did the system check, and what was the actual result? For the authorization code flow, common checkpoints include:

- Is the client permitted to use the authorization_code grant and response_type=code?
- Does the redirect URI match a registered URI exactly?
- Is PKCE required and is the right code_challenge_method used?
- Did the user authenticate and consent according to policy?
- Is the authorization code unexpired, unused, and bound to the right client?
- Does the token request use the exact redirect URI bound to the authorization request?
- Does the code verifier correspond to the issued code challenge?
- Does client authentication match the client type and registered method?

### Step 5: Write Hypotheses and Tests

Every hypothesis needs supporting evidence and a test that can falsify it.

| Hypothesis | Sign to Look For | Minimal Test |
|---|---|---|
| Redirect URI mismatch | redirect_uri_match=false or invalid_request at authorization endpoint | Send authorization request with valid URI and invalid URI on test client |
| PKCE verifier mismatch | pkce_validation=failed at token endpoint | Mint fresh code, exchange with right verifier, then repeat with a different verifier |
| Expired or already-used authorization code | code_expired or code_already_used if system records state | Mint fresh code; exchange once, then retry with the used code in test environment |
| Client authentication failure | client_authenticated=false or invalid_client | Use registered auth method and verify test client config |
| Wrong scope or grant | unauthorized_client or invalid_scope | Drop scopes one by one or use a grant permitted for the client |
| Wrong public URL behind proxy | Metadata/redirect uses internal host or scheme | Compare trusted Forwarded headers with published issuer and metadata |

Never treat invalid_grant as sole proof of a PKCE error. That error can occur when a code is invalid, expired, already used, bound to another client, mismatched on redirect URI, or paired with a wrong verifier. Rely on safe internal events to distinguish the cause.

## 6. Distilling into a Minimal Request

A minimal request contains only the parameters required for the scenario under test. Drop optional headers, stale cookies, unrelated scopes, and unnecessary application parameters. Use a fresh authorization code on each attempt since codes are normally single-use and short-lived.

### 6.1. Preparing a Test Client

Create a dedicated client in the test environment with known configuration:

- Client alias: diagnostic-public-client.
- Grant: authorization_code.
- Client type: public, no client secret.
- PKCE: required, method S256.
- Redirect URI: https://client.example.test/callback.
- Scope: keep only scopes needed for the test case, e.g. openid.

example.test is a domain reserved for examples. Replace it with the endpoints and redirect URIs of your test environment. If testing a confidential client, use the configured client authentication method; never embed secrets or client assertions directly in commands, tickets, or logs.

Test accounts should contain no real data. Use a clean browser profile per run if the flow involves login and consent so cookies or sessions from prior runs do not skew results.

### 6.2. Minimal Authorization Request

An authorization request using authorization code and PKCE looks like:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP %{http_code}\n' \
  --get 'https://auth.example.test/oauth2/authorize' \
  --data-urlencode 'response_type=code' \
  --data-urlencode 'client_id=diagnostic-public-client' \
  --data-urlencode 'redirect_uri=https://client.example.test/callback' \
  --data-urlencode 'scope=openid' \
  --data-urlencode 'state=<fresh-random-state>' \
  --data-urlencode 'code_challenge=<S256-challenge-for-this-test>' \
  --data-urlencode 'code_challenge_method=S256'
~~~

State and code challenge must be freshly generated for each test run. The code challenge is the Base64URL-encoded SHA-256 hash of the corresponding code verifier. The command above checks only the endpoint request and status; it does not complete login, consent, or callback. For interactive flows, use a test browser profile to complete those steps.

Never pass curl -v when capturing evidence to share. Verbose output can print full URLs, headers, or cookies. If inspecting redirects, do so inside the test environment and redact queries containing codes/states before saving screenshots or logs.

### 6.3. Minimal Token Request

After completing the test authorization flow, use the fresh authorization code issued in that exact run to call the token endpoint:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP %{http_code}\n' \
  --request POST 'https://auth.example.test/oauth2/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode 'client_id=diagnostic-public-client' \
  --data-urlencode 'redirect_uri=https://client.example.test/callback' \
  --data-urlencode 'code=<fresh-authorization-code-from-this-test>' \
  --data-urlencode 'code_verifier=<matching-test-code-verifier>'
~~~

This command prints only the HTTP status and discards the response body to avoid printing access tokens, refresh tokens, or ID Tokens to the terminal. Use normalized logs on the Authorization Server to read the OAuth error code and failing validation step. If you must inspect the response body in a test environment, save it in a protected location, extract only allowlisted error fields, and delete the token-bearing file immediately afterward.

For confidential clients, the request also requires client authentication per the registered method such as client_secret_basic, private_key_jwt, or mTLS. Never turn those credentials into CLI arguments or copyable examples. Use a secret manager or test tooling with secure credential input.

### 6.4. Keeping the Request Truly Minimal

Once you have a successful request as a baseline, make a copy changing only one factor:

- Change the redirect URI to test exact matching.
- Use a different verifier to test PKCE.
- Use a fresh code intentionally allowed to expire in the test environment to test expiration.
- Use a test client without the grant permitted to test unauthorized_client.
- Drop one scope to test scope policy.

Record the single variable changed, HTTP status, OAuth error, and request ID. Never reuse real users' codes or tokens to test another scenario.

## 7. Example: Investigating a PKCE invalid_grant Error

Suppose a test client completes login, yet the token endpoint returns HTTP 400 and invalid_grant. Masked logs show:

~~~json
{
  "event": "oauth.token.exchange.failed",
  "request_id": "req-7f21a9",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "route": "/oauth2/token",
  "http_status": 400,
  "client_alias": "diagnostic-public-client",
  "grant_type": "authorization_code",
  "redirect_uri_match": true,
  "pkce_method": "S256",
  "pkce_validation": "failed",
  "oauth_error": "invalid_grant"
}
~~~

From this log you can rule out redirect URI mismatch, yet it is not enough to conclude a wrong code verifier if the system has not recorded code state. Also check the code issuance event and lookup/expiration/redeemed results if available.

A controlled experiment:

1. Generate a random code verifier A and compute its corresponding S256 code challenge.
2. Send a new authorization request with that challenge, finish login with a test account, and receive a fresh code.
3. Send a token request with verifier A. Record status and PKCE validation event.
4. Create a new authorization request with verifier B and B's challenge.
5. When exchanging the second run's code, intentionally send verifier A. Expected result: token endpoint rejects with invalid_grant and logs pkce_validation=failed.
6. Exchange a subsequent fresh code using verifier B. Expected result: success if client, redirect URI, and code conditions hold.

Each authorization code is valid for a single exchange. Do not test verifier A and then verifier B against the same code to compare, because the first attempt may already consume the code. Start a fresh authorization flow for each test.

This confirms PKCE validation works as expected in the test environment. If the attempt with the right verifier still fails, widen the investigation to code lifetime, client binding, redirect URI, code state, and the client's PKCE configuration.

## 8. Common Mistakes During Reproduction

| Misleading Practice | Why Results Are Unreliable | Correct Approach |
|---|---|---|
| Replaying an already-used authorization code | Code may already be consumed or expired | Start a fresh authorization flow and code per attempt |
| Reusing session cookies from another browser | Session, CSRF, or consent state may mismatch | Use a fresh test browser profile and record interactive steps |
| Changing multiple parameters at once | Impossible to tell which change caused the error | Change only one variable per run |
| Enabling DEBUG globally in production | Can log credentials and create huge log volume | Use allowlisted events, narrow scope, and short windows |
| Sharing raw Network tab screenshots | Callback URLs, cookies, or responses may contain codes/tokens | Redact data before exporting images and keep only needed fields |
| Using local times in mixed timezones | Timeline order may be wrong | Normalize to UTC and check clock drift |
| Relying solely on HTTP status | One status maps to multiple OAuth causes | Cross-check OAuth error and validation events |
| Hitting backend directly to bypass proxy | Headers, scheme, host, and TLS policy may differ from reality | Reproduce via the same ingress path as the original request; test backend separately only to isolate |
| Using production clients to test failures | Can create grants, tokens, or consents affecting real users | Create test clients and accounts with equivalent configuration |

## 9. Packaging Evidence for Handoff

A good report lets someone else reproduce the bug without needing access to credentials or personal data. The report should contain:

1. **Symptom**: expected behavior, actual behavior, endpoint, status, and OAuth error.
2. **Environment**: test/staging/production, application version, instance, and sanitized relevant config.
3. **Timeline**: events in UTC, request ID/trace ID, and emitting service.
4. **Masked logs**: allowlisted fields only, no raw headers/bodies.
5. **Minimal request**: method, endpoint, parameter names, and dummy values; replace credentials with placeholders.
6. **Outcome**: status, OAuth error, validation result, and the condition changed.
7. **Remaining hypotheses**: what has been ruled out and the next test to run.

Report template:

~~~text
Symptom:
  Expected: token endpoint returns success for a valid test authorization code.
  Actual: HTTP 400, invalid_grant.

Environment:
  Environment: test
  Service version: <version>
  Client alias: diagnostic-public-client

Evidence:
  Timestamp UTC: <timestamp>
  Request ID: <request-id>
  Trace ID: <trace-id>
  Route: POST /oauth2/token
  Redirect URI match: true
  PKCE method: S256
  PKCE validation: failed

Minimal reproduction:
  Use a fresh authorization flow and code.
  Exchange with a verifier that does not match the issued challenge.

Observed result:
  HTTP 400
  OAuth error: invalid_grant

Secrets and personal data:
  Redacted before sharing.
~~~

Attach only logs and configs the recipient truly needs. Enforce read permissions, retention limits, and sharing channels per organizational policy. Before handoff, search for common sensitive strings such as Bearer, client_secret, refresh_token, code_verifier, Cookie, Set-Cookie, and private key headers to ensure nothing slipped through.

## 10. Pre-Closure Checklist

- [ ] Exact failing flow and failing endpoint identified.
- [ ] Proxy and application logs share correlatable request IDs or trace IDs.
- [ ] Timestamps normalized to UTC and node clocks synchronized.
- [ ] Logs include allowlisted fields only; raw queries, bodies, Authorization headers, and cookies are excluded.
- [ ] Authorization codes, tokens, client secrets, assertions, verifiers, states, and nonces removed.
- [ ] Clients, redirect URIs, and users in examples replaced with aliases or test data.
- [ ] Timeline captures observed steps and clearly marks steps lacking evidence.
- [ ] Every hypothesis has a confirming or falsifying test.
- [ ] Every attempt uses a fresh code and varies a single variable.
- [ ] Token-bearing responses are never printed to terminals or attached to reports.
- [ ] Both OAuth errors and internal validation outcomes checked; no conclusions drawn from HTTP status alone.
- [ ] Diagnostic bundle reviewed for secrets before sharing.

## Conclusion

Reliable error reproduction starts with structured logs and correlatable identifiers across components. Allowlists preserve diagnostic essentials like route, grant type, OAuth error, and validation outcomes while stripping credentials and personal data at the source. Once you have a timeline and hypothesis, distill the flow into test requests, vary one variable at a time, and use a fresh authorization code for every run. The final report should give enough request shape, masked logs, and outcomes for others to verify without ever touching incident secrets.
