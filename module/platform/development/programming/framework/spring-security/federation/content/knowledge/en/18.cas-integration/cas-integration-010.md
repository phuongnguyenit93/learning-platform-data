# Customizing Responses When a CAS Ticket Is Expired, Reused, or Invalid

## 1. Problem and Objectives

Java Spring Security applications integrating the **CAS Protocol** typically redirect the browser to the CAS Server for login. CAS authenticates the user, issues a short-lived **Service Ticket (ST)** bound to one service URL, and redirects back to the application:

~~~http
GET /login/cas?ticket=ST-EXAMPLE-ONE-TIME HTTP/1.1
Host: app.example.org
~~~

The application must never treat `ticket` as proof of login. The Spring Security CAS client must use `TicketValidator` to call the CAS Server (typically `/serviceValidate` or `/p3/serviceValidate` over HTTPS) to verify the ST and service before creating an `Authentication`.

In practice, the callback can fail because the ST:
- Expired before CAS checked it;
- Was already validated once, and then a browser refresh or a filter/retry reused it;
- Was never issued, is malformed, belongs to another environment, was tampered with, or cannot be found;
- Was issued for a **different service** than the service URL the client sent for validation;
- Failed `renew` or ticket-type rules;
- Could not be verified due to a CAS Server, network, TLS, or parser error.

The goal of **"Customizing Responses When a Ticket Is Expired, Reused, or Invalid"** under **Spring Security - Federation -> CAS Integration** is to build failure handling that is both **safe** and **operable**: accurately recognizing what information is actually available, never logging users in when validation fails, never retrying consumed STs, and never falling into a CAS<->app redirect loop.

After this lesson, you will be able to:
1. Understand the **service-bound**, **one-time**, and **short-lived** properties of a CAS ST.
2. Distinguish CAS codes `INVALID_TICKET`, `INVALID_SERVICE`, `INVALID_REQUEST`, and `INTERNAL_ERROR`.
3. Explain why a CAS client usually **cannot know for certain** whether a ticket expired, was reused, or never existed when seeing only `INVALID_TICKET`.
4. Customize `AuthenticationFailureHandler` on `CasAuthenticationFilter`.
5. Choose HTML redirects vs. JSON/HTTP statuses according to browser and API contracts.
6. Organize logging/metrics, correlation IDs, and internal root-cause classification without leaking tickets.
7. Avoid ST retries, double filter registration, wrong service URLs, and authentication redirect loops.
8. Run a standalone Java 17 exercise simulating CAS one-time, service-bound ticket rules and error mapping.
9. Write test scenarios for expired/replayed/invalid tickets, timeouts, and CAS outages.
10. Distinguish CAS ticket validation errors from SAML Response errors, authorization failures, or HTTP transport errors.

Context: Java 17+, Spring Boot 3.x, Spring Security CAS on Servlet/MVC. When using Spring Security 5.x/6.x/7.x, check Javadocs for your exact version; Jakarta Servlet and `javax.servlet` versions do not share the same imports.

## 2. A CAS Service Ticket Is Valid for Only One Validation Attempt

The CAS Server owns the **Ticket-Granting Ticket (TGT)** representing the central SSO session and uses the **Ticket-Granting Cookie (TGC)** in the browser to recognize that session. An ST is a ticket **specific to one service** and **intended for a single validation by the application**. They are not the same:

| Entity | Function | Where Handled |
| --- | --- | --- |
| `TGT` | CAS Server manages SSO session and ability to mint new STs | CAS Server / ticket registry |
| `TGC` | Browser cookie referencing the CAS session | Browser <-> CAS Server |
| `ST` | Short-lived credential bound to a specific service | Carried by browser to app; app backend validates with CAS |
| `HttpSession`/`JSESSIONID` | Local application session after authentication | Spring Security and app session store |

**CAS Protocol 2.0 specifies that an ST is valid for only one validation attempt, whether that attempt succeeds or fails.** CAS must invalidate the ST after that attempt. This includes when the ticket is valid yet the submitted service URL is wrong: `INVALID_SERVICE` does not permit taking that same ST and retrying with another service. If the ST has expired, CAS also rejects it.

Example flow:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring CAS client
    participant CAS as CAS Server
    B->>SP: GET /protected
    SP-->>B: Redirect /cas/login?service=...
    B->>CAS: CAS login/SSO session
    CAS-->>B: Redirect /login/cas?ticket=ST-ONE
    B->>SP: GET callback with ST-ONE
    SP->>CAS: /serviceValidate?ticket=ST-ONE&service=...
    CAS->>CAS: Validate and consume ticket
    alt Valid
        CAS-->>SP: authenticationSuccess, principal
        SP->>SP: Create Authentication / SecurityContext
        SP-->>B: Redirect to URL without ST
    else Invalid
        CAS-->>SP: authenticationFailure with CAS code
        SP->>SP: AuthenticationFailureHandler
        SP-->>B: Safe error page
    end
    B->>SP: Refresh old callback with ST-ONE
    SP->>CAS: serviceValidate same ST-ONE
    CAS-->>SP: INVALID_TICKET
~~~

An ST can be replayed due to a refresh, back button, browser extension, retry library, or duplicate filter—it does **not necessarily** mean an attacker is present. Conversely, an ST leaked and redeemed by someone else first is a serious risk. Therefore control TLS, service binding, logging, and redirects carefully.

## 3. CAS Validation Success and Failure

In CAS 2.0, the service may call:

~~~http
GET /cas/serviceValidate?ticket=ST-DEMO&service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas HTTP/1.1
Host: cas.example.org
~~~

Illustrative CAS XML **success**:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>opaque-user-id</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Illustrative CAS XML **failure**:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">
    Service ticket cannot be validated
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

These XML snippets are **format examples only**, not live responses from an example server. Never write a custom parser searching for `authenticationSuccess` by substring; use a CAS client library with a safe XML parser and **HTTPS server authentication**.

### Protocol Error Code Reference

| CAS Protocol Error Code | Meaning | Appropriate Response |
| --- | --- | --- |
| `INVALID_REQUEST` | Missing or malformed validation request parameters | Check URL/handler; never create a session |
| `INVALID_TICKET` | Ticket invalid: possibly expired, already used, or nonexistent; also possible due to `renew` requirement | Prompt for a fresh login; never retry the ST |
| `INVALID_SERVICE` | Ticket may be valid, yet `service` differs from the issued service | Fix `ServiceProperties`/public URL/registry; old ST is already consumed |
| `INTERNAL_ERROR` | CAS internal error during validation | Check CAS health/audit; do not blame user |
| `INVALID_TICKET_SPEC` | Ticket fails validation specification rules in some CAS versions | Check validator, `renew`/proxy/policy |
| `UNAUTHORIZED_SERVICE_PROXY` | Service is not authorized to act as a proxy | Check service registry and proxy trust |
| `INVALID_PROXY_CALLBACK` | Proxy callback fails security requirements | Check `pgtUrl`/TLS/callback |

**Version note:** CAS Protocol 2.0 defines a minimal code set, while newer Apereo CAS versions may add codes. Never treat an unknown code as success. CAS 1.0 `/validate` returns plain text yes/no, while CAS 3.0 `/p3/serviceValidate` supports attributes; apply only the XML codes matching your endpoint.

**HTTP status does not replace the CAS protocol result.** A CAS Server can return HTTP 200 containing `cas:authenticationFailure`. Conversely, HTTP 502/503 or a timeout does not prove the ticket itself was invalid.

## 4. Three Scenarios That Can All Produce `INVALID_TICKET`

This is the most important knowledge boundary in this article.

### Expired Ticket

The CAS Server stores STs with a lifetime governed by its ticket expiration policy. If validation arrives too late, CAS rejects it. Causes include browser idle delays, network congestion, clock skew, or an ST TTL configured too short for the flow.

### Reused Ticket

The ST was already checked by CAS—succeeding **or failing**—and another validation attempt submits the same ticket. CAS rejects it. A double-registered filter, automatic GET `/serviceValidate` retry after a timeout, or the user hitting Refresh on the callback can all cause this.

### Unrecognized Ticket

A forged ST, a ticket from another CAS environment, an evicted ticket, or a modified string may not exist in the registry. CAS likewise rejects it.

**A CAS client seeing only `INVALID_TICKET` may NOT know which scenario occurred.** Some CAS Servers record detailed reasons in audits/registries, yet the CAS Protocol does not mandate separate `EXPIRED`/`REUSED`/`UNKNOWN` codes. Therefore:

- Never write `exception.getMessage().contains("expired")` and treat it as a contract.
- Never declare a "replay attack" solely from a single `INVALID_TICKET`.
- Never expose a public API returning whether a ticket existed; that creates a **ticket oracle**.
- When investigating, consult **trusted CAS Server audits**, correlation events, metrics, and timestamps.
- User-facing messages should stay generic: **"Unable to complete this login attempt. Please start a new login."**

Separating **protocol error codes** from **operational root causes** mitigates risk without creating false positives.

## 5. Spring Security CAS Class Structure

In the browser CAS model:

~~~text
Browser:
  GET /login/cas?ticket=ST-...
      |
      v
CasAuthenticationFilter
      |
      v
AuthenticationManager / ProviderManager
      |
      v
CasAuthenticationProvider
      |
      v
CAS Client TicketValidator
      |
      v
CAS Server /serviceValidate
      |
      +--> CAS success -> Spring Authentication -> SecurityContext/session
      |
      +--> CAS failure/exception -> AuthenticationFailureHandler
                                      |
                                      v
                             Safe HTTP response/redirect
~~~

Roles:
- `CasAuthenticationEntryPoint` sends unauthenticated browsers to `/cas/login` with `service`.
- `ServiceProperties` holds the service callback URL and options like `sendRenew`.
- `CasAuthenticationFilter` receives the ST at the callback, defaulting typically to `/login/cas`.
- `CasAuthenticationProvider` validates the ticket and builds authentication from the CAS result.
- `Cas20ServiceTicketValidator` typically calls CAS `/serviceValidate` over HTTPS.
- `AuthenticationFailureHandler` produces the HTTP response when authentication fails in the filter.
- `SecurityContextRepository`/`HttpSession` retains the app session after login if sessions are configured.

A `TicketValidator` error may be wrapped into an `AuthenticationException`, sometimes with a root cause like `TicketValidationException`. **There is no guarantee** that expired, replayed, and invalid errors map to three distinct exception subclasses. Handle structured codes only when your library/version actually provides them; otherwise group them under generic `AUTHENTICATION_FAILED`.

### `AuthenticationFailureHandler` vs. `AccessDeniedHandler`

| Error | Proper Handler |
| --- | --- |
| CAS ST invalid; no new `Authentication` created | CAS filter -> `AuthenticationFailureHandler` |
| CAS validator timeout/TLS failure | CAS provider/filter path; classify as network if evidenced |
| CAS ticket valid yet user lacks permission | Spring `AuthorizationManager` / `AccessDeniedHandler` |
| Unauthenticated user accesses protected route | `AuthenticationEntryPoint` (redirects to CAS) |
| CSRF error on API POST | CSRF filter / `AccessDeniedHandler` per config |
| Browser local logout while CAS TGC remains | Session/logout policy, not ST validation |
| Invalid `SAMLResponse` signature | Spring SAML provider, not CAS `TicketValidator` |

Do not catch every application `Exception` and blindly redirect back to CAS login, as that hides real failures, easily triggers login loops, and breaks HTTP/API semantics.

## 6. Designing Safe Browser Responses

When an ST is rejected by CAS:
1. **Never create an `Authentication`** from the failed ticket or user-supplied query parameters.
2. **Never retry the old ST**, even on an HTTP timeout, because CAS may have already consumed it.
3. Redirect to a fixed **public** page, such as `/cas-error`.
4. Ensure that page URL contains no `ticket` and does not auto-redirect back to CAS.
5. Display a brief message without raw tickets, internal CAS server names, or Java stack traces.
6. Provide a **user-initiated** "Start a new login" action that begins a fresh CAS login transaction and ST.
7. Never redirect to a browser-chosen URL via an unvalidated `returnUrl`.
8. Log the event with a dedicated trace ID while redacting tickets, cookies, and user identifiers.

Suggested user-facing text:

> Unable to complete this login attempt. The authentication link may have expired or already been used. Please start a new login. If the problem persists, contact support.

This message works safely across expired, reused, and unknown tickets. Never claim "expired" with certainty when CAS returned only `INVALID_TICKET`.

### When `INVALID_SERVICE` Is Confirmed

Use a distinct message:

> The application is currently unable to complete sign-in. Please contact support and provide the displayed reference code.

Because service URL / registry errors **will not resolve themselves in a few seconds**, never auto-loop back to CAS login.

### When the CAS System Is Temporarily Unavailable

An appropriate message:

> The login service is temporarily unavailable. Please try again later.

Require actual CAS endpoint/TLS/network evidence before showing this—never treat every `INVALID_TICKET` as an outage.

## 7. Customizing the CAS Filter via `AuthenticationFailureHandler`

`CasAuthenticationFilter` extends `AbstractAuthenticationProcessingFilter` and supports `setAuthenticationFailureHandler(AuthenticationFailureHandler)`. This is the right extension point for controlling the response when **CAS login in the filter** fails.

File `src/main/java/com/example/federation/CasFailureHandler.java`:

~~~java
package com.example.federation;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

@Component
public final class CasFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
            LoggerFactory.getLogger(CasFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        String incidentId = UUID.randomUUID().toString();

        // Never log ticket/query/cookie or raw exception messages.
        log.warn("cas_login_failed incidentId={} exceptionClass={}",
                incidentId, exception.getClass().getSimpleName());

        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        // Fixed local path; never read redirect URL from the browser.
        response.sendRedirect(request.getContextPath() + "/cas-error");
    }
}
~~~

**Code explanation:**
- The handler runs inside the **Spring Security CAS filter** and does not alter or decode tickets.
- `incidentId` is a non-sensitive operational reference, stored only in logs in this example. To display it to users, pass it via a controlled state/view mechanism that never exposes arbitrary log queries.
- `exception.getClass().getSimpleName()` gives diagnostic signal without printing raw messages that might contain an ST.
- `response.sendRedirect` moves the browser to a fixed URL without the `ticket` query parameter.
- There is no `if expired/replayed` branch because Spring exceptions do not guarantee that distinction.
- This is **a Java class inside a Spring Boot project**, requiring Spring Security, Jakarta Servlet, and SLF4J; **it does not run via `javac` alone** and has no fixed stdout.

### Wiring into `CasAuthenticationFilter`

File `src/main/java/com/example/federation/CasFilterConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.web.CasAuthenticationFilter;

@Configuration
public class CasFilterConfig {

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            AuthenticationManager authenticationManager,
            ServiceProperties serviceProperties,
            CasFailureHandler failureHandler) {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(authenticationManager);
        filter.setServiceProperties(serviceProperties);
        filter.setFilterProcessesUrl("/login/cas");
        filter.setAuthenticationFailureHandler(failureHandler);
        return filter;
    }
}
~~~

**Important:** the bean above is **one integration piece**, not a complete CAS login setup on its own. The project also needs `CasAuthenticationEntryPoint`, `CasAuthenticationProvider`, `TicketValidator`, user-details mapping, service registry entries, and a Spring `SecurityFilterChain`.

If the app declares a Filter bean in a way that Spring Boot auto-registers it as a **Servlet Filter** while also calling `addFilterAt` into `SecurityFilterChain`, a single callback can **be processed twice**. Control `FilterRegistrationBean`/registrations and test filter ordering. Never register the filter manually in the Servlet container while also running it inside the security chain.

### `SecurityFilterChain` Illustrating Insertion Point

~~~java
@Bean
SecurityFilterChain casSecurity(
        HttpSecurity http,
        CasAuthenticationFilter casFilter,
        CasAuthenticationEntryPoint entryPoint) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/cas-error", "/public/**").permitAll()
                    .anyRequest().authenticated())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter,
                    UsernamePasswordAuthenticationFilter.class)
            .build();
}
~~~

This is a **snippet** requiring imports for `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `CasAuthenticationFilter`, `CasAuthenticationEntryPoint`, `UsernamePasswordAuthenticationFilter`, and all real CAS beans. Depending on your project, configure filter matchers, session strategies, CSRF, and provider registration separately. **Do not copy this snippet as a full project and expect SSO to work.**

The `/cas-error` page **must be public**. If it requires authentication, the browser will immediately redirect back to CAS and loop when configuration is broken.

## 8. Do Not Confuse CAS `AuthenticationEntryPoint` with CAS Failure Handler

**`AuthenticationEntryPoint`** is invoked when an unauthenticated browser hits a protected route. It typically redirects to CAS login:

~~~text
GET /private
  -> no Authentication
  -> CasAuthenticationEntryPoint
  -> 302 https://cas.example.org/cas/login?service=...
~~~

**`AuthenticationFailureHandler`** is invoked when the **CAS callback was received** yet ticket validation or the provider failed:

~~~text
GET /login/cas?ticket=ST-BAD
  -> CasAuthenticationFilter
  -> TicketValidator rejects
  -> AuthenticationFailureHandler
  -> 302 /cas-error
~~~

If the failure handler redirects straight back to `/private`, the entry point restarts CAS automatically. With a wrong service URL, every fresh ST fails, trapping the browser in an infinite CAS<->app loop.

Safe design:
- Redirect errors to a fixed local public page, **never automatically** back to CAS.
- Provide a user-clicked "Log in again" button to start a fresh flow.
- Rate-limit and alert on repeated failures.
- Check whether callback URLs carrying STs linger in browser history; redirect cleanly after both success and failure.
- Clear or avoid preserving failed ticket request paths afterward.

## 9. Service URL Mismatch: A Specific Error Worth Close Attention

A CAS ST is issued for **one service identifier**. For instance, when requesting the ticket:

~~~text
CAS /login?service=https://app.example.org/login/cas
~~~

yet during validation the app sends:

~~~text
CAS /serviceValidate?service=http://app-internal:8080/login/cas
~~~

CAS can return `INVALID_SERVICE` because the service URLs do not match, even if both addresses reach the same app through a reverse proxy. The CAS Protocol invalidates the ST on a validation mismatch; once you fix the URL, **you must request a new ticket**.

Check:
1. Public HTTPS scheme vs. internal HTTP scheme.
2. Host, port, context path, trailing slash, and query parameters.
3. `ServiceProperties.getService()` and the CAS service registry.
4. LB/ingress rewrites and `Forwarded`/`X-Forwarded-Proto`/`Host` headers only from trusted reverse proxies.
5. Config consistency across pods.
6. CAS Server allowlist policies preventing ST issuance to external hosts.
7. Never appending an unvalidated user-supplied return URL to `service`.

**Never fix this by permitting wildcard services or disabling TLS hostname verification.** That is a trust boundary, not mere configuration convenience.

## 10. Expired Tickets and TTL

Ticket expiration policy is managed by the CAS Server. The app should never:
- Parse an opaque ticket trying to read an expiry timestamp.
- Extend an ST's lifetime.
- Allow an ST to be reused because the browser was slow.
- Skew local clocks so validation passes.
- Stretch ST TTL to hours just to mask bugs.
- Treat "the browser waited 5 seconds" as sufficient proof that the ticket expired.

Investigate:
- CAS Server expiration policy and ticket registry settings.
- When the ST was issued vs. when the validator actually received the request (from authorized audits).
- Time synchronization / NTP across nodes.
- Browser delays or proxy/WAF buffering.
- Ticket store replication/reads across CAS cluster nodes.
- CAS registry evictions or data lifecycle issues.
- CAS client network latency p95/p99.
- Unnecessary timeouts or redirects during the callback.

If CAS returns only `INVALID_TICKET`, show the generic user message while operations consult CAS audits to confirm expiration when reliable data exists.

## 11. Ticket Reuse Caused by Code or Browser Behavior

Common causes:
- User hits Refresh/Back on a URL containing `ticket=ST-OLD`;
- Callback GET is loaded twice by SPA/lifecycle behavior;
- HTTP client auto-retries `/serviceValidate` assuming GET is always idempotent;
- Spring filter registered both in the outer Servlet chain and inside `SecurityFilterChain`;
- Reverse proxy or automated test replays the URL;
- Two tabs or two requests arrive concurrently;
- Backend validates the ST manually in a controller and then `CasAuthenticationFilter` validates it again.

**Caution:** although CAS `/serviceValidate` uses HTTP GET, it has the **side effect of consuming the ST**. Therefore **GET validation is not safe to retry with the same ticket** in the usual idempotent sense.

When the provider returns `INVALID_TICKET` and duplicates are suspected:
1. Count validation attempts via correlation/audit without logging raw STs.
2. Confirm a single callback is processed exactly once by design.
3. Inspect filter registrations and HTTP client retry policies.
4. Redirect the browser off the ticket-bearing URL after every login attempt.
5. Check concurrent requests at the LB and pods.
6. Never weaken CAS's one-time policy just to make a test pass.

**A successful CAS login with an active app session** does not contradict rejecting an old callback URL. The ST is spent; `HttpSession` and app `Authentication` follow their own lifecycle.

## 12. Unknown Errors or Forged Tickets

An ST absent from the CAS registry does not automatically prove replay. Causes include:
- The ticket was never issued by CAS;
- The ticket was modified or belongs to a different staging/production environment;
- The expired ticket was evicted;
- The ticket was consumed and no tombstone remains;
- Misrouted CAS cluster traffic;
- CAS Server rotated keys/stores or a node failed;
- The ticket format is rejected by the validator.

A browser can submit `ticket=ST-guess` to probe. The application must uphold these rules:
- **Never create an `Authentication`** before CAS validation;
- Never respond with "this ticket exists" or "ticket belongs to user X";
- Never treat the URL ticket as a user identity;
- Never store the ticket in the session as a long-lived bearer credential;
- Log a generic category, evaluate rate limiting, and check CAS audits on serious anomalies.

CAS also has **Proxy Tickets (PT)** and `/proxyValidate` endpoints with separate policies. A PT must not be accepted automatically at `/serviceValidate` unless the profile allows it; never treat every string starting with `PT-` as an ST.

## 13. How Should HTML and API Responses Differ?

### Browser SSO

A browser callback can:
- Return **302** to a fixed `/cas-error`;
- Render a friendly message on the error page;
- Provide a "Log in again" button starting a **new CAS transaction**, never retrying the ST;
- Set appropriate `Cache-Control: no-store` and `Referrer-Policy` headers;
- Omit raw tickets and external return URLs.

### API

An API may define:

| Condition | Reference HTTP Status | Note |
| --- | --- | --- |
| No valid `Authentication` | 401 | Insufficient proof to establish a session |
| Authenticated yet lacking permission | 403 | Authorization, not CAS ticket validation |
| Confirmed CAS validator/Server outage | 503 | Depends on API contract and handler |
| Malformed request prior to validation | 400 | Follow contract; never let callers enumerate tickets |
| Browser SSO callback ticket failure | 302 to error page | Browser navigation differs from REST JSON |

Do not coerce **every** CAS error into HTTP 500. CAS can return HTTP 200 containing `authenticationFailure`. HTTP status reflects transport/app outcome, whereas `INVALID_TICKET` is a CAS protocol error.

### JSON Example

~~~json
{
  "error": "authentication_failed",
  "message": "Cannot complete login. Please start a new session.",
  "traceId": "example-reference-001"
}
~~~

This is an **illustrative schema**. Never include raw STs, CAS Server stack traces, usernames, exception causes, or service secrets in the response. When one app serves both browsers and APIs, define distinct security chains and response contracts—**do not merely switch responses arbitrarily on an untrusted `Accept` header**.

## 14. Trustworthy Levels of Error Classification

Separate data into three tiers:

| Tier | Examples | Where Allowed? |
| --- | --- | --- |
| Validator-verified CAS **protocol code** | `INVALID_TICKET`, `INVALID_SERVICE` | App internals / metrics |
| Evidence-backed CAS **operational diagnosis** | `EXPIRED` from CAS Server audit, `REPLAYED` with server-side record, `TLS_TIMEOUT` from network | Operations / forensics |
| **Public response** to user | `AUTHENTICATION_FAILED`, `RETRY_NEW_LOGIN`, `CONTACT_SUPPORT` | Browser / API |

If the CAS protocol returns only `INVALID_TICKET`, record an internal reason of `UNCLASSIFIED` instead of guessing from message substrings. Never use `BadCredentialsException` alone to infer that the ST expired: the Spring provider wraps multiple failures depending on version.

If you truly must separate "expired" from "reused" accurately:
1. The CAS Server must supply ticket issuance/consumption/expiry audit data or trusted extended status.
2. You need a way to correlate events without storing raw STs in the app.
3. Those events require access control, retention limits, and privacy policies.
4. When evidence is insufficient, conclude `UNKNOWN`.
5. Never expose ticket-existence state to the browser to prevent a ticket oracle.

### Avoid Logging Raw Exception Messages

An exception from the validator can include the ticket or service URL. Log instead:
- Stable exception **type** and CAS error code if structured evidence exists;
- App-generated Trace ID;
- Registered service **alias** (not raw query URLs);
- Node, environment, timestamp, and latency;
- `outcome=DENY`, `action=NEW_LOGIN`;
- Classified health error type (timeout, TLS).

Never log:
- Callback query string `ticket=...`;
- `TGC`/`JSESSIONID` cookies;
- Full CAS XML response bodies;
- Session or ticket cache keys;
- Raw stack traces or full request dumps to shared log sinks;
- Personal data such as user principals when unnecessary.

## 15. Monitoring and Post-Deploy Investigation

An internal event:

~~~json
{
  "event": "cas_ticket_validation_failed",
  "traceId": "login-event-7a2e",
  "serviceAlias": "portal-cas",
  "casCode": "INVALID_TICKET",
  "diagnosis": "UNCLASSIFIED",
  "node": "portal-02",
  "durationMs": 117,
  "result": "DENY"
}
~~~

The `diagnosis` field is an internal enum, not a CAS Protocol code. Never use STs as metric labels.

Useful metrics:
- `cas_ticket_validation_failed_total{code="INVALID_TICKET"}`;
- `cas_ticket_validation_failed_total{code="INVALID_SERVICE"}`;
- `cas_dependency_error_total{type="timeout"}`;
- `cas_authentication_success_total`;
- Validation latency p95/p99;
- Failed callbacks per time window;
- CAS<->app redirect loop count;
- Count of nodes running mismatched service URL config versions.

**Never put usernames, STs, or raw service URLs in labels**, due to cardinality and data leakage. If `INVALID_SERVICE` spikes right after a deploy, inspect canonical URLs, proxies, and the service registry first. If `INVALID_TICKET` spikes alongside latency, inspect TTLs, CAS node/time sync, and duplicate requests.

## 16. Network/TLS Errors Are Not CAS `INVALID_TICKET`

Examples:
- DNS lookup failure;
- Connect/read timeout;
- CAS HTTP 502/503;
- Expired TLS certificate or hostname mismatch;
- Non-XML CAS response;
- HTML login page returned instead of CAS validation XML;
- Proxy/WAF blocking the request;
- CAS ticket registry outage.

In all of these cases, the app **could not verify the ticket**, so it must not create a new `Authentication`. However, never report "CAS confirmed the ticket was invalid" when **no valid CAS response arrived**.

Especially dangerous: a network timeout can occur **after CAS already consumed the ST** but before the app received the response. Retrying validation with that same ST **can return `INVALID_TICKET`**. Good policy is:
- Never do unbounded retries on CAS validation;
- During an outage, fail closed for new logins;
- Allow users to start a fresh CAS flow once service recovers;
- Apply backoff/circuit breakers and infrastructure monitoring;
- Never disable TLS validation or switch to plain HTTP to "fix timeouts."

Local sessions authenticated before the outage follow their own lifecycle and policy; do not blindly wipe every active session during a brief CAS disconnect, and never let new logins bypass CAS.

## 17. Standalone Java 17: Simulating Expired, Replayed, and Wrong-Service Tickets

The program below uses **only JDK 17**, simulating the ticket registry **on the CAS Server side**. Because it controls issuance and consumption, it knows whether the cause was `EXPIRED` or `REUSED`. It then maps multiple causes onto the **same protocol code `INVALID_TICKET`**, demonstrating why the client cannot deduce the exact cause.

File `CasTicketFailureDemo.java`:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class CasTicketFailureDemo {

    enum Reason {
        OK, INVALID_REQUEST, EXPIRED, REUSED,
        INVALID_SERVICE, UNKNOWN
    }

    record Ticket(String service, Instant expiresAt) {}

    static final class TicketStore {
        private final Map<String, Ticket> live = new HashMap<>();
        private final Set<String> attempted = new HashSet<>();

        synchronized void issue(
                String id, String service, Instant expiresAt) {
            live.put(id, new Ticket(service, expiresAt));
        }

        synchronized Reason validate(
                String id, String presentedService, Instant now) {
            if (id == null || id.isBlank()
                    || presentedService == null
                    || presentedService.isBlank()) {
                return Reason.INVALID_REQUEST;
            }

            Ticket entry = live.remove(id);
            if (entry == null) {
                return attempted.contains(id)
                        ? Reason.REUSED : Reason.UNKNOWN;
            }
            attempted.add(id);

            if (!entry.expiresAt().isAfter(now)) {
                return Reason.EXPIRED;
            }
            if (!entry.service().equals(presentedService)) {
                return Reason.INVALID_SERVICE;
            }
            return Reason.OK;
        }
    }

    static String casCode(Reason reason) {
        return switch (reason) {
            case OK -> "SUCCESS";
            case INVALID_REQUEST -> "INVALID_REQUEST";
            case INVALID_SERVICE -> "INVALID_SERVICE";
            case EXPIRED, REUSED, UNKNOWN -> "INVALID_TICKET";
        };
    }

    static String userAction(Reason reason) {
        return reason == Reason.OK
                ? "SIGNED_IN" : "NEW_LOGIN_REQUIRED";
    }

    static void print(String label, Reason reason) {
        System.out.println(label + ": " + reason
                + " / CAS=" + casCode(reason)
                + " / UX=" + userAction(reason));
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        String service = "https://app.example.org/login/cas";
        String wrong = "https://other.example.org/login/cas";

        TicketStore server = new TicketStore();
        server.issue("ST-FRESH", service, now.plusSeconds(60));
        server.issue("ST-OLD", service, now.minusSeconds(1));
        server.issue("ST-WRONG", service, now.plusSeconds(60));

        print("fresh",
                server.validate("ST-FRESH", service, now));
        print("replay",
                server.validate("ST-FRESH", service, now));
        print("expired",
                server.validate("ST-OLD", service, now));
        print("wrong-service",
                server.validate("ST-WRONG", wrong, now));
        print("retry-after-wrong",
                server.validate("ST-WRONG", service, now));
        print("unknown",
                server.validate("ST-UNKNOWN", service, now));
        print("missing",
                server.validate("", service, now));
    }
}
~~~

Run with Java 17+:

~~~bash
javac CasTicketFailureDemo.java
java CasTicketFailureDemo
~~~

**Exact** stdout:

~~~text
fresh: OK / CAS=SUCCESS / UX=SIGNED_IN
replay: REUSED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
expired: EXPIRED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
wrong-service: INVALID_SERVICE / CAS=INVALID_SERVICE / UX=NEW_LOGIN_REQUIRED
retry-after-wrong: REUSED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
unknown: UNKNOWN / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
missing: INVALID_REQUEST / CAS=INVALID_REQUEST / UX=NEW_LOGIN_REQUIRED
~~~

**Demo limitations:** this is not a real CAS Server; it does not mint tickets with `SecureRandom`, lacks HTTP/TLS, XML, distributed ticket stores, and account verification. The `attempted` set is **synthetic state** to detect replays; CAS implementations are not required to keep tombstones like this. A CAS client receiving only the protocol result cannot determine `Reason` directly. Never use demo code as production authentication middleware.

Key takeaways:
1. Fresh, unexpired ST with matching service -> succeeds on first attempt.
2. Reused ST -> simulated server knows `REUSED`, yet returns protocol `INVALID_TICKET`.
3. Expired ST -> `EXPIRED` also maps to `INVALID_TICKET`.
4. Valid ST with wrong service -> `INVALID_SERVICE` and ticket is consumed.
5. Retrying that same ST with the right service after mismatch -> still rejected.
6. Never-issued ticket -> also `INVALID_TICKET`.
7. Missing ticket -> `INVALID_REQUEST`.
8. UI does not leak sensitive distinctions and simply prompts for a new login.

## 18. Avoiding a Typical Redirect Loop

Suppose configuration is wrong:

~~~text
App public URL: https://app.example.org/login/cas
App validator service: http://internal:8080/login/cas

1. GET /private -> CAS login
2. CAS issues ST-1 for public URL
3. App validates ST-1 with internal URL -> INVALID_SERVICE
4. Failure handler auto-redirects to /private
5. /private sends browser back to CAS login
6. CAS issues ST-2, still wrong service
7. Infinite loop; browser reports too many redirects
~~~

How to handle it:
- Failure handler redirects to public `/cas-error`, **never back to a protected route**.
- That page does not auto-initiate another login.
- Include a trace ID so operations can identify the error.
- Fix `ServiceProperties.service`, trusted forwarded headers, and the CAS service registry.
- Once fixed, the user chooses to start a **new login transaction** with a fresh ST.
- Never alter the CAS Server to drop service binding.

**Never resolve this by dropping the security filter, trusting client URLs, or allowing all services.** A CAS ticket issued for another recipient must never authenticate the current app.

## 19. System Testing with a CAS Test Server

### Test 1 — Valid Ticket

1. Open a fresh test browser session.
2. Access a protected resource and follow the redirect to CAS login with the right `service`.
3. CAS issues a new ST and redirects the browser to the callback.
4. App calls HTTPS validation with the exact ticket and service.
5. CAS returns success; Spring creates `Authentication` and `HttpSession`.
6. Success redirect removes `ticket` from the URL.
7. Verify permitted pages respect authorization rules.

### Test 2 — Reused Ticket

1. Log in successfully using a test ST.
2. In the lab, resubmit that exact callback URL carrying the ST.
3. CAS rejects the second attempt.
4. App creates no new `Authentication` from the rejected attempt.
5. Handler returns the generic error page without logging or displaying the ST.
6. The "Log in again" button initiates a fresh transaction without retrying the same ST.

### Test 3 — Expired Ticket

1. Configure the test CAS with a short ticket expiration policy or fault injection.
2. Mint an ST and deliberately delay validation beyond TTL in the lab.
3. CAS returns a validation failure.
4. App shows a generic error without claiming "replay attack."
5. Use CAS audits to confirm expiration where available.

### Test 4 — Wrong Service

1. CAS issues an ST for the public HTTPS URL.
2. Client validation submits a wrong internal HTTP service URL.
3. CAS rejects with `INVALID_SERVICE` as expected.
4. Do not retry that ST.
5. Fix the config, obtain a fresh ST, and verify login succeeds.

### Test 5 — Unknown Ticket

1. Send a fabricated ticket in an authorized test environment.
2. CAS rejects it; no `Authentication` is created.
3. App never confirms whether the ticket ever existed.
4. Evaluate rate limiting if requests come from an anomalous source.

### Test 6 — Timeout and Lost Response

1. Inject a network fault between the app and CAS right after validation is sent.
2. CAS may have consumed the ST while the app received no response.
3. App fails closed and never retries the same ST.
4. Use CAS Server logs/audits to explain the event if available.
5. Retry UX starts a fresh login once the service recovers.

### Test 7 — Double Filter Registration

1. Instrument CAS validation counts using an ST-free event/correlation ID.
2. Execute a single browser callback.
3. If the same ST is validated twice due to filters outside and inside `SecurityFilterChain`, fix registration.
4. Never make CAS disable its one-time policy.

### Test 8 — Local Authorization Failure

1. CAS validates the ST successfully.
2. App-mapped account lacks permission for the route.
3. Route denies with 403 or specific policy.
4. Never turn an authorization failure into `INVALID_TICKET`.

## 20. Additional Security Tests

| Negative Scenario | Guarantee to Uphold |
| --- | --- |
| CAS XML has `authenticationFailure` | No `Authentication` created |
| HTTP 200 yet XML failure | Never treat HTTP 200 as login success |
| Forged ticket with `ST-` prefix | Trust only CAS Server validation |
| Reused ST | CAS rejects the second validation attempt |
| ST issued for service A, used at B | Service binding still enforced |
| HTTPS hostname mismatch | Never skip TLS verification |
| XML containing DTD/external entities | Safe CAS parser blocks XXE |
| User supplies arbitrary CAS validator URL | Prevent SSRF |
| Ticket appears in query/logs | Redact tickets and limit telemetry |
| Untrusted return URL | No open redirect |
| Browser refreshes callback | Fail safely; never reuse old ST |
| CAS outage | Never fail open |
| CAS succeeds yet user mapping fails | Never grant high default privileges |
| Divergent multi-node configs | Detect per-node and fix |
| SAML on same CAS platform | Never mix CAS protocol handler with SAML provider |

Never use another person's tickets or accounts in negative testing. Perform tests against authorized test IdP/CAS instances.

## 21. Multiple Pods and Concurrent Browser Requests

One ST may arrive twice concurrently:
- Request A hits pod A;
- Request B hits pod B;
- Both send `/serviceValidate` with the same ST;
- The CAS registry must enforce atomic one-time consumption;
- One validation succeeds while the other returns `INVALID_TICKET`.

Never fix this by allowing STs to be used twice. Instead:
1. Eliminate double filter registration.
2. Audit HTTP client retry policies.
3. Ensure browser callbacks fire once in the UX.
4. Consider navigation/UI idempotency **without skipping validation**.
5. Inspect load balancers, duplicate callbacks, and session stores.
6. Log validation attempt counts alongside trace IDs.
7. Ensure all pods share identical `ServiceProperties`.
8. Never use `INVALID_TICKET` on request B to conclude login A was invalid or the user is locked.

Similarly, a CAS Server cluster needs a consistent ticket store; one node failing to find a ticket may indicate a cluster/registry bug rather than a forged ticket.

## 22. Specifics of Proxy Tickets and Stateless Caching

CAS has **Proxy Tickets (PT)** and `/proxyValidate` endpoints for proxy use cases. Spring Security CAS also supports `StatelessTicketCache` for certain stateful/stateless remoting flows.

Distinguish clearly:
- The **CAS Server** still enforces **one-time ticket validation** for STs and PTs per protocol.
- The **Spring client** may cache verified `Authentication` in stateless proxy-ticket integrations under a specific contract.
- That cache does not grant browsers unlimited reuse of old STs.
- Never send a proxy ticket to `/serviceValidate` and treat it as a service ticket.
- Verify proxy chains, CAS registration, and the right `TicketValidator` when proxy auth is permitted.
- Never copy old stateless CAS examples into browser login sessions without a security review.

In this lesson, the default flow is **stateful browser CAS login** with a one-time ST and a local `HttpSession` after success.

## 23. Misconceptions to Avoid

1. **"INVALID_TICKET definitely means expired."** Wrong. It can be replay, unknown, or `renew` failure.
2. **"INVALID_TICKET proves an attacker replay."** Wrong. Browser refreshes or double-registered filters also cause it.
3. **"CAS /serviceValidate is a GET so it can be retried freely."** Wrong. Validation consumes the ST.
4. **"Wrong service—just fix the URL and retry the same ticket."** Wrong. The ticket is already invalidated.
5. **"An ST-... string is enough to authenticate."** Wrong. Opaque STs require CAS Server validation.
6. **"CAS XML failure with HTTP 200 still counts as login success."** Wrong.
7. **"A network timeout means the ticket was invalid."** Wrong. CAS may have consumed it before the response was lost.
8. **"Spring provides a standard ExpiredTicketException across every CAS version."** Not guaranteed.
9. **"Just regex the exception message to classify errors."** Wrong; fragile and risks leaking the ST.
10. **"Auto-redirecting to CAS login on every error improves UX."** Can trigger infinite loops on `INVALID_SERVICE` or outages.
11. **"A CSRF 403 is always caused by the CAS ticket."** Wrong. Separate HTTP security filters and business authorization.
12. **"An active CAS TGC makes a consumed ST valid again."** Wrong. A TGC can help mint a **new ST**.
13. **"A Spring Boot auto-registered Filter cannot collide with SecurityFilterChain."** Wrong; control registrations explicitly.
14. **"Logging raw tickets is fine because they expire fast."** Unsafe: tickets can be redeemed before consumption.
15. **"A SAML Response error is the same as CAS INVALID_TICKET."** Wrong; different protocols.
16. **"When CAS validation fails, clear all user sessions."** Not by default; session revocation follows its own policy.
17. **"Returning ticket existence details to the UI helps debugging."** Creates a ticket oracle and information leak.
18. **"Locking an account in CAS automatically updates authorities in every app session."** Not guaranteed.

## 24. Review Questions with Answers

**Question 1.** CAS returns `INVALID_TICKET`. Can you conclude with certainty that the ticket expired?

**Answer:** No. This is a generic protocol code covering multiple causes; trusted CAS Server audits are required to prove expiration.

**Question 2.** Why is retrying the same ST after a timeout unsafe?

**Answer:** CAS may have already consumed the ST even though the app never received the response; the second attempt will be rejected. Start a new flow to obtain a new ST.

**Question 3.** CAS returns `INVALID_SERVICE` and the app fixes its service URL config. Can the old ST be resent?

**Answer:** No. The CAS spec requires invalidating the ST after any validation attempt, including wrong-service attempts.

**Question 4.** How do `CasAuthenticationFilter` and `CasAuthenticationEntryPoint` differ in role?

**Answer:** EntryPoint redirects unauthenticated browsers to CAS. Filter receives the ST callback and validates it via provider/validator. FailureHandler controls the response when filter authentication fails.

**Question 5.** Should CAS Server exception stack traces be rendered on the error page?

**Answer:** No. They may leak tickets and internal details. Show a short public message with a trace ID.

**Question 6.** A user refreshes the callback after a successful login and sees `INVALID_TICKET`. Does that prove the initial login failed?

**Answer:** No. The ST was consumed during the successful validation; the local `HttpSession` has its own lifecycle.

**Question 7.** The CAS Server returns HTTP 200 with XML `authenticationFailure`. May the app create an `Authentication`?

**Answer:** No. Verified CAS protocol success is required, not merely HTTP 200.

**Question 8.** One pod calls CAS validation twice because the filter bean is also registered as a Servlet Filter. How do you fix it?

**Answer:** Check `FilterRegistrationBean`/`SecurityFilterChain` to ensure a single handling path for CAS callbacks—never disable CAS's one-time rule.

**Question 9.** Why should `/cas-error` be `permitAll`?

**Answer:** Unauthenticated users must be able to view the error message. If the page is protected, the app redirects back to CAS and loops.

**Question 10.** If CAS fails TLS connection, should you disable hostname verification to make login succeed?

**Answer:** No. Fix the CAS endpoint, truststore, certificates, and network—never skip validation.

**Question 11.** CAS validation succeeds yet the app route returns 403. Should you increase the ST TTL?

**Answer:** Not by default. That is likely post-authentication authorization or account policy.

**Question 12.** A user logs out locally, revisits the app, and gets SSO'd immediately. Was the old ST reused?

**Answer:** No. An active CAS TGT/TGC lets CAS issue a **fresh ST**.

**Question 13.** Should raw STs be stored in a cache to aid replay investigations?

**Answer:** No. Rely on CAS Server audits or protected correlation IDs; never turn app logs into a credential store.

**Question 14.** Can the browser be told specifically "the ticket existed and was already used"?

**Answer:** Better not. Without CAS proof or if revealing it creates a ticket oracle, show a generic message and keep technical classification internal.

**Question 15.** One flow gets XML `INVALID_TICKET` from CAS Server and another hits a network timeout. Are they the same error class?

**Answer:** No. One is a **protocol failure with a CAS response**; the other is **unverifiable** due to a dependency/transport failure.

**Question 16.** When must you inspect the service registry?

**Answer:** Whenever `INVALID_SERVICE` or unauthorized-service errors occur, especially after deploys or reverse-proxy rewrites. Register the exact public HTTPS callback without unbounded wildcards.

## 25. Pre-Production Checklist

- [ ] CAS Server and CAS client use matching CAS Protocol endpoints and versions.
- [ ] CAS Service Tickets are verified over backend HTTPS with TLS server authentication.
- [ ] `ServiceProperties.service` matches both the public callback and CAS service registration.
- [ ] CAS ST preserves one-time, time-limited, service-bound semantics.
- [ ] Old STs are never retried after `INVALID_TICKET`, `INVALID_SERVICE`, or timeouts.
- [ ] Spring CAS filter/provider/validator wiring is right with zero duplicate filter registrations.
- [ ] `AuthenticationFailureHandler` directs browsers to a public page without the ST.
- [ ] Error page never auto-redirects to CAS in a loop and offers a "Start new login" button.
- [ ] No `Authentication` or role is created from unvalidated tickets.
- [ ] `INVALID_TICKET` is never assumed with certainty to mean expired/replayed/unknown.
- [ ] If detailed root causes are needed, trusted CAS Server audits or typed evidence exist.
- [ ] Logs and metrics contain no raw tickets, query strings, cookies, or sensitive CAS XML.
- [ ] Sanitized trace IDs, categories, service aliases, latencies, nodes, and statuses are recorded.
- [ ] Reverse proxies, ingress, `ServiceProperties`, and CAS registry are consistent across nodes.
- [ ] API and browser response contracts are clearly separated; not every failure becomes HTTP 500.
- [ ] CAS outages fail closed for new logins; TLS/certificate verification is never skipped.
- [ ] No open redirects via `service` or return URLs.
- [ ] CSRF, session fixation, user provisioning, and post-login authorization remain tested.
- [ ] Tested expired, replayed, unknown, wrong-service, malformed, timeout, outage, and duplicate-callback cases.
- [ ] Tested browser Refresh, Back, two tabs, long redirect chains, and mobile browsers.
- [ ] Chose the right CAS module without confusing it with SAML 2.0 Web Browser SSO.

## 26. Summary

When a CAS ticket is expired, reused, or invalid, the application must **refuse authentication with that ticket**. The CAS Protocol can emit the same `INVALID_TICKET` code for multiple causes; clients must not fabricate detailed causes from a single generic code. Service Tickets **must never be retried**, because they are service-bound and valid for **one validation attempt**.

Good customization spans three layers: **CAS Server/validator protecting the ticket**, **Spring Security CAS filter + `AuthenticationFailureHandler` returning safe responses**, and **operations using verified audits/metrics to investigate**. Error pages must not leak STs, trigger login loops, or grant sessions; users initiate a fresh transaction when appropriate.

### Official Documentation

1. Apereo CAS — CAS Protocol 2.0 Specification (one-time ST, `INVALID_TICKET`, `INVALID_SERVICE`, `serviceValidate`): https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html
2. Apereo CAS — CAS Protocol Specification (CAS 3.x and proxy error codes): https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
3. Apereo CAS — Troubleshooting Guide: https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/installation/Troubleshooting-Guide.md
4. Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
5. Spring Security API — `CasAuthenticationFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
6. Spring Security API — `CasAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
7. Spring Security API — `AuthenticationFailureHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
8. Spring Security API — `AbstractAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
