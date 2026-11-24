# Consistency Across Multiple Providers, Retries, and Multi-Request Authentication

## 1. Goals and problem statement in Spring Security

A Spring Boot application may simultaneously accept **web login passwords**, **integration system API keys**, **OAuth2 bearer tokens**, or authenticate via an external identity system. Those mechanisms may traverse multiple `AuthenticationProvider` instances, multiple `ProviderManager` instances, and multiple `SecurityFilterChain` configurations. After each check, the application wants to emit **authentication success/failure** events for auditing, monitoring, or limiting anomalous behavior.

However, "authenticated successfully" and "each event appears exactly once across the entire system" are two different things:

- One `ProviderManager` can try **multiple providers in a single** `authenticate(...)` call.
- One HTTP request can carry **one login** or perform no new authentication check if a valid session already exists.
- A stateless client may have to **re-authenticate on every request**.
- A client or gateway may **retry a request** on timeout, triggering a new attempt.
- An event listener may be invoked repeatedly due to **multiple configured publishers**, or an event may be redelivered when forwarded to a message broker/outbox.
- Two concurrent requests may read/update session, credential state, or audit counters at the same time.
- An event indicates **authentication succeeded**, not that the controller succeeded or that the user is authorized for every resource.

This lesson belongs to the **"Authentication Events"** group in the Spring Security - authentication module. The goal is not to build a full event broker, but to understand **event semantics and boundaries** when multiple providers, retries, and consecutive requests are involved. You will be able to:

1. Predict `AuthenticationProvider` ordering and the final outcome of `ProviderManager`.
2. Distinguish **provider attempt**, **authentication-manager decision**, **HTTP request**, **interactive login event**, **session**, and **business operation**.
3. Understand where `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent` are emitted, and why missing or duplicated publishers corrupt audits.
4. Design retries properly for credential failures, transient dependency errors, one-time tokens, and duplicate requests.
5. Keep login results consistent across multiple stateful/stateless requests and prevent `SecurityContext` leaks across threads.
6. Write a Spring Boot 3.5.x / Java 17+ application with two provider types, one manager, one event publisher, and a thread-safe listener.
7. Test success/failure across multiple HTTP requests with MockMvc, recognizing the difference between event counts and business request counts.
8. Use correlation IDs, deduplication, and outboxes when events trigger critical side effects.

**General principle:** classify the exact unit you need consistency over. You cannot use a single `AuthenticationSuccessEvent` counter to deduce exact user session counts, unique user counts, or successful API request counts.

## 2. Six distinct concepts often conflated into one

| Concept | Meaning | Example |
| --- | --- | --- |
| **Provider attempt** | A provider asked by the manager to process an `Authentication` | Provider A sees `UsernamePasswordAuthenticationToken` and checks the password |
| **Manager authentication decision** | Final result of one `AuthenticationManager.authenticate(...)` call | Manager returns a valid `Authentication` or throws `AuthenticationException` |
| **Authentication event** | Notification in the Spring ApplicationContext about an authentication outcome | `AuthenticationSuccessEvent` or `AuthenticationFailureBadCredentialsEvent` |
| **HTTP request** | A request sent by a client over the network | `POST /login`, `GET /private/me`, `GET /api/key/whoami` |
| **SecurityContext/session** | Storage holding `Authentication` for the current request and optionally reusable across a session | User logs in once, then GETs 5 pages without re-entering the password |
| **Business operation** | A business action requiring authorization and dedicated handling | Creating an invoice, transferring funds, changing email, creating an API key |

**There is no mandatory 1:1 relationship.** One `authenticate` call can traverse multiple providers; one session can span many requests; a stateless request can invoke `authenticate` every time; and a successful authentication can still be rejected by `AuthorizationFilter` downstream.

Boundary diagram:

```text
HTTP request
    |
    v
Authentication filter (when the mechanism needs to authenticate on this request)
    |
    v
AuthenticationManager.authenticate(token)  <-- 1 decision
    |
    +--> Provider A (supports? result/null/error)
    |
    +--> Provider B (if needed)
    |
    +--> optional parent AuthenticationManager
    |
    v
Final Authentication / AuthenticationException
    |
    +--> AuthenticationEventPublisher
    |       +--> success/failure event
    |
    +--> Filter:
            +--> SecurityContext
            +--> session persistence or stateless request context
            +--> success/failure response
    |
    v
Authorization, Controller, Service, Business transaction
```

The event publisher reports the **authentication outcome**—it does not imply a database transaction at the end of the diagram committed successfully.

## 3. How does ProviderManager decide when multiple providers coexist?

Spring Security defines `AuthenticationManager` as an interface that takes an unauthenticated `Authentication` and returns an authenticated `Authentication` or throws an `AuthenticationException`. The most common implementation is `ProviderManager`, which holds an ordered list of `AuthenticationProvider` instances.

Each provider has two methods:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

These are **abbreviated signatures** from the interface, not a standalone Java class. Combining the two methods yields these cases:

| Provider behavior | Effect on the manager |
| --- | --- |
| `supports(tokenType) == false` | Skips that provider without calling `authenticate` |
| `supports(...) == true` and returns **non-null Authentication** | Success; stops iterating providers and uses that result |
| Returns `null` | Provider is undecided; continues trying other providers |
| Throws `BadCredentialsException` | Records error; a subsequent provider can still succeed per `ProviderManager` contract |
| Throws `AccountStatusException` (e.g., locked/disabled) | Stops trying subsequent providers; prevents later providers from bypassing account status policy |
| No provider supports or decides | May yield `ProviderNotFoundException` or the last error; if a parent manager exists, the parent may be tried per contract |

Per `ProviderManager` Javadoc, if a later provider **succeeds**, errors from earlier providers are disregarded and the **final successful result** is used. If no later provider succeeds, the last relevant error is thrown. `AccountStatusException` is an important exception that halts iteration.

### 3.1. Example ordering of two separated mechanisms

```text
ProviderManager [
    DaoAuthenticationProvider           -> UsernamePasswordAuthenticationToken
    ApiKeyAuthenticationProvider        -> ApiKeyAuthenticationToken
]
```

- Browser `POST /login` creates `UsernamePasswordAuthenticationToken`: Dao provider checks it; API-key provider does not support that token.
- Machine client sending `X-API-Key` creates `ApiKeyAuthenticationToken`: Dao provider does not support it; API-key provider verifies the digest.
- Two distinct token types prevent a provider from accidentally "trying its luck" with another mechanism's credentials.

**Provider ordering still requires management**, especially if two providers support the **same token type**. For example, password provider A uses LDAP and provider B uses a legacy database: if A throws `BadCredentialsException`, B could still accept the same username/password. That might be intentional by design, or it could be a **bypass** of account policies.

### 3.2. Final outcome truth table

| Provider A | Provider B | Actual conclusion |
| --- | --- | --- |
| Does not support token | Authenticates successfully | Success via B |
| Returns `null` | Authenticates successfully | Success via B |
| `BadCredentialsException` | Authenticates successfully | Success via B; never assume a final failure event |
| Authenticates successfully | Not called | Success via A; stops |
| `DisabledException`/`LockedException` | Not called | Failure due to account status; no fallback |
| No provider supports | No provider supports | `ProviderNotFoundException` if no matching parent |
| Providers A/B both hit dependency errors | Unsuccessful | Final error per contract; **never** fall back to anonymous |

**Never use fallback to turn an outage into a bypass:** if the central credential store loses connectivity, do not automatically fall back to a weaker local account store unless backed by an explicit threat model, policy, account binding, and tests. "Availability" must never be traded for fake authentication.

## 4. At which boundary does Spring Security publish events?

Spring Security uses `AuthenticationEventPublisher` to turn authentication decisions into Spring application events. The typical implementation is `DefaultAuthenticationEventPublisher`.

Common event types:

- `AuthenticationSuccessEvent`: a manager invocation reached a successful authentication result.
- `AuthenticationFailureBadCredentialsEvent`: bad credentials error per default mapping.
- `AuthenticationFailureDisabledEvent` / `AuthenticationFailureLockedEvent`: corresponding account state errors.
- `AuthenticationFailureProviderNotFoundEvent`: no suitable provider was found.
- `AuthenticationFailureServiceExceptionEvent`: mapped system-outage authentication error.
- `AbstractAuthenticationFailureEvent`: superclass for listeners catching multiple failure types.
- `InteractiveAuthenticationSuccessEvent`: a separate event that an authentication filter may emit for successful interactive login; **does not mean the manager ran a second time**.

These events are not equivalent to `HttpSessionCreatedEvent`, `SessionFixationProtectionEvent`, `LogoutSuccessEvent`, or business events. **Never lump every event with the word "success" into "user logged in once."**

### 4.1. One manager.authenticate call, multiple providers: how many events?

With a standard `ProviderManager` wired with one publisher and providers that do not publish events themselves:

```text
authenticate(token)
  Provider A -> BadCredentialsException
  Provider B -> Authentication success
  ProviderManager -> decides SUCCESS
  Publisher -> AuthenticationSuccessEvent
```

**The final outcome is success.** Do not expect each provider attempt to emit a standalone `AuthenticationFailureBadCredentialsEvent`. If provider A/B calls `ApplicationEventPublisher.publishEvent(...)` internally, that is an **application-emitted custom event**, no longer equivalent to a manager-level final outcome.

Conversely:

```text
authenticate(token)
  Provider A -> BadCredentialsException
  Provider B -> BadCredentialsException
  ProviderManager -> decides FAILURE
  Publisher -> AuthenticationFailureBadCredentialsEvent
```

This is **one failed authentication attempt from the manager's perspective**, even though two providers were invoked.

### 4.2. Important: manually constructing ProviderManager does not include a publisher by default

`ProviderManager` Javadoc states that the default publisher of a manually constructed manager is a no-op implementation. Therefore:

```java
// Insufficient if the system needs to receive authentication events:
ProviderManager manager = new ProviderManager(
    List.of(providerOne, providerTwo));
```

Attach the appropriate `AuthenticationEventPublisher`:

```java
ProviderManager manager = new ProviderManager(
    List.of(providerOne, providerTwo));
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
```

This is a **snippet**; the provider variables are supplied via configuration below. To prevent events from "disappearing" in audits, tests must prove not only that login succeeded, but that **the listener received the expected event**.

In standard Spring Security/Boot setups, an event publisher may be registered automatically by how the framework builds the manager. However, **never assume that applies to a `new ProviderManager(...)` you instantiate manually**. Configure the publisher explicitly wherever you own the manager's lifecycle.

### 4.3. Parent managers and duplicated events

A `ProviderManager` can accept a **parent AuthenticationManager**. If the child cannot resolve the authentication, the parent is consulted. Javadoc notes that the child can also publish an event for the parent's outcome; if **both child and parent have publishing publishers**, there is a risk of **double publication**.

```text
Child ProviderManager
  |
  +-- local providers -> undecided
  |
  v
Parent ProviderManager -> success
  |
  +-- parent publisher emits success event
  |
  v
Child receives parent's result
  |
  +-- child publisher emits success event AGAIN
```

**Recommendation:** pick **one place responsible for publishing events** in a manager chain with a parent, or actively deduplicate by design. Never assume two events mean the user logged in twice—and never disable all auth auditing out of fear of duplicates.

### 4.4. AuthenticationException mappings have limits

`DefaultAuthenticationEventPublisher` maps known exceptions to failure events. Spring Security 6.5 docs state that default mapping uses **exact exception class matching**, not automatic expansion to arbitrary custom subclasses.

For example, if an application has:

```java
public final class ExternalIdentityUnavailableException
        extends AuthenticationServiceException {
    public ExternalIdentityUnavailableException(String message) {
        super(message);
    }
}
```

If the publisher lacks a mapping for the **exact custom class**, it may **fail to emit the failure event you expect**. Add `setAdditionalExceptionMappings(...)` or a suitable fallback event; never coerce an exception into `BadCredentialsException` just to "get an event," as that corrupts error semantics.

## 5. Authentication events are not HTTP request events

A browser user typically logs in once and sends many requests:

```text
T0 POST /login + valid password
   -> manager.authenticate(...) SUCCESS
   -> AuthenticationSuccessEvent
   -> session stores SecurityContext

T1 GET /private/me + JSESSIONID
   -> SecurityContextRepository loads authentication
   -> controller returns 200
   -> no new manager.authenticate call necessarily

T2 GET /private/report + JSESSIONID
   -> loads SecurityContext, authorization
   -> no new authentication success event necessarily

T3 POST /logout
   -> logout/session cleanup; other event if configured
```

**An authentication event does not tell you how many requests were served in a session.** Conversely, a user might log back in after logging out, hold multiple browser sessions, or undergo reauthentication/step-up, yielding multiple events for the same principal.

With stateless API keys / bearer tokens:

```text
GET /api/key/whoami + X-API-Key: secret
    -> verifies key on this request
    -> AuthenticationSuccessEvent

GET /api/key/whoami + same key, second request
    -> re-verifies key
    -> AuthenticationSuccessEvent again
```

If the endpoint filter genuinely invokes the manager on **every request**, receiving two success events is normal. Do not deduplicate two genuine authentications solely because `principal` matches, or you will lose audit signals.

A variant that caches token validation might not call the manager on every request; thus event frequency depends on **authentication architecture**, not a fixed Spring Security guarantee.

## 6. Retries: three concepts that must be distinguished

### 6.1. Retries at the provider layer

Suppose a provider queries an identity server that temporarily times out. A single `authenticate(...)` call might include internal retry logic if implemented by the application. However:

- **Never retry `BadCredentialsException`** repeatedly: a wrong password will not become right on retry; it wastes load and clutters audits.
- **Never retry `DisabledException`/`LockedException`** with another provider to bypass account status.
- Transient errors like network timeouts can be retried **with bounds**, timeouts/budgets/circuit breakers, and only for authentication operations safe to retry.
- **Single-use credentials** such as OTPs, magic links, authorization codes, and consumed or ceremony-bound WebAuthn challenges may be unsafe to replay as a fresh transaction.
- If the external authentication system has side effects (lockout counters, access logs, failed-attempt counters), retries increase check counts and audit trails.

**Internal provider retries do not automatically make the manager emit multiple events**; the manager's publisher typically sees only the final outcome of one call. If a provider emits custom events per network attempt, clearly separate `provider_attempt` from `authentication_outcome`.

### 6.2. Retries at the HTTP client/gateway layer

If a `POST /login` request times out after the backend already succeeded, the client might miss the response/cookie and **resend**. The backend sees a brand-new request:

```text
Client                Gateway                 Server
  | POST /login A        |                      |
  |--------------------->|---- attempt A ------>|
  |                      |                auth SUCCESS
  |                      |                session/context stored
  |       timeout        |                      |
  |<---------------------X                      |
  | POST /login A retry  |                      |
  |--------------------->|---- attempt B ------>|
  |                      |                auth SUCCESS again
  |<---------------------|<----- response ------|
```

Two authentication success events can reflect **two actual submissions**, not a publisher bug. Never assume "POST requests are normally idempotent": HTTP POST is not idempotent by default; only the application can supply custom semantics.

If retries must be handled safely, define the **intent of the retry**: should the same auth request preserve its result, or is it a new attempt for rate limiting? **Never let a client supply an arbitrary idempotency key and skip credential verification on the next call just because it "succeeded earlier."**

### 6.3. Retries when pushing events to external systems

If a listener forwards events to Kafka/RabbitMQ/outbox/HTTP collectors, a missed ACK can cause the same event to be **redelivered**. This is a **delivery retry**, completely different from a user attempting to log in a second time.

How to handle it:

1. Generate a **stable event ID** for each outbound business/audit event at the source.
2. Persist the event alongside transaction state in an outbox or durable store; if downstream fails, retry with the **same event ID**.
3. Consumers enforce unique constraints/deduplication by event ID and business key; on redelivery of the same ID, skip the **side effect** without deleting records of other authentication requests.
4. Ensure metrics do not double-count on duplicate deliveries. Keep request counts and delivered-event counts separate.
5. Design dead-letter/replay procedures and audits for undelivered events.

**Spring's `AuthenticationSuccessEvent` is not an outbox event with a durable event ID and automatic exactly-once delivery.** If the application needs such guarantees, you must add the proper persistence/transaction/deduplication layer.

## 7. Classifying outcomes to prevent corrupted audit data

A minimal audit event should distinguish:

| Field | Example | Reason |
| --- | --- | --- |
| `event_id` | Server-generated UUID for **one** persisted event | Deduplicates deliveries; does not replace "attempt count" |
| `attempt_id` | Correlation ID for one manager invocation, if applicable | Links provider diagnostics to manager decision |
| `request_id` | HTTP request ID from trusted reverse proxy/server | Links logs, traces, and request retries |
| `principal_ref` | Pseudonymized or access-controlled user/service ID | Avoids storing plaintext passwords or raw API keys |
| `auth_method` | password, API key, bearer, WebAuthn | Categorizes the mechanism |
| `result` | SUCCESS/FAILURE/ERROR | Separates wrong passwords from infrastructure errors |
| `provider_id` | Safe provider identifier | Debugs routing across multiple providers |
| `failure_code` | BAD_CREDENTIALS, ACCOUNT_LOCKED, SERVICE_UNAVAILABLE | Avoids exposing raw exception text as a public contract |
| `occurred_at` | Server UTC timestamp | Analyzes retries/freshness and ordering |
| `session_ref` | Pseudonymized session ref if stateful | Distinguishes requests/sessions |
| `policy_version` | Authentication rule version when applicable | Debugs behavior changes across deployments |

This is a **recommended design schema**, not fields Spring includes automatically in every event. Never log `Authentication.toString()` directly if tokens/principals/details may contain credentials or personal data.

For username/password failures, the username may be arbitrary attacker input containing sensitive data. Use normalized values, controlled masking/hashing, or omit usernames when unnecessary. Never trust `X-Forwarded-For` unless the gateway enforces a trust boundary.

**Metrics that should remain separate:**

- `auth_attempts_total`: manager invocations or actual attempts per product definition.
- `auth_success_total` / `auth_failure_total`: outcomes, not sessions.
- `http_requests_total`: HTTP requests past ingress.
- `active_sessions`: live sessions per repository/registry.
- `auth_event_delivery_retries_total`: outbound event delivery retries.
- `login_users_distinct`: unique principals in a window, requiring privacy controls and exact definitions.

If a dashboard combines these metrics into a single "Successful Logins" chart without clear definitions, numbers will break when migrating from sessions to stateless tokens or changing providers.

## 8. Preserving Authentication and SecurityContext across requests

Spring Security Servlet normally uses `SecurityContextHolder` to keep `Authentication` on the request-handling thread. `SecurityContextRepository` determines how `Authentication` is saved and restored when the next request arrives.

Three typical repositories:

| Repository | Meaning | When to use |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Stores `SecurityContext` in `HttpSession` | Stateful web login / session cookies |
| `RequestAttributeSecurityContextRepository` | Keeps context in attributes of the current request dispatch | Error/forward dispatches needing context |
| `NullSecurityContextRepository` | Does not persist `SecurityContext` for future requests | Stateless APIs authenticating every request |

Spring Security 6.x defaults to `SecurityContextHolderFilter` with an **explicit save** model. If a custom filter/controller sets the context manually and needs it persisted for future requests, it must call:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// ONLY when this mechanism truly intends to persist across future requests:
securityContextRepository.saveContext(
    context, request, response);
```

This is a **snippet**, assuming `authenticated` is verified and `securityContextRepository` is supplied by the application. Do not use this when only stateless per-request authentication is needed. If a custom authentication filter skips saving while expecting login to persist across requests, the first request may return 200 while the second becomes anonymous.

**Key point:** standard authentication filters like form login handle context/session persistence per framework configuration. You do not need to manually inject `saveContext` into controllers after standard form login.

### 8.1. Stateful sessions and events

A user authenticates once, context is stored in the session, and subsequent requests restore context without calling `AuthenticationManager` again. Therefore:
- One user can have many requests yet only one manager success event.
- Session expiration or logout does not "erase" historical audit events.
- When updating authorities in the database, old sessions may still hold prior authorities until refreshed/revalidated.
- Across multiple app instances, a shared session store/affinity is required; verify behavior during deploys or failovers.

### 8.2. Stateless credentials and events

With bearer tokens, API keys, mTLS, or request signatures, every request can be authenticated independently. When the filter invokes the manager each time:
- Every valid request can emit a success event.
- Revocation takes effect per check/cache speed; never rely on an old event to permit a new request.
- Client retries generate additional requests and events if verification repeats.
- When scaling horizontally, per-instance in-memory counters do not equal the system-wide total; use metrics aggregation or a durable audit pipeline.

**Never store raw API keys or bearer tokens in `HttpSession` just to reduce event counts.** That alters the threat model and credential revocation behavior.

## 9. Concurrency: ThreadLocal, session races, and concurrent logins

### 9.1. SecurityContextHolder and request threads

`SecurityContextHolder` defaults to `MODE_THREADLOCAL` in the Servlet stack. Request threads are reused by pools, so custom code must:

- Construct a fresh `SecurityContext` after successful authentication.
- Expose `Authentication` only to the current request/thread being handled.
- Clear the context in a `finally` block after the filter if managing lifecycle manually.
- Never store a global static `SecurityContext` shared across all requests.
- Never leave user A's `Authentication` in an async task where user B might reuse that thread.

Example custom request-only pattern:

```java
try {
    SecurityContext context =
        SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authenticated);
    SecurityContextHolder.setContext(context);
    chain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

This is only a snippet inside `OncePerRequestFilter` and **does not** yet include credential verification. The complete demo in section 11 implements both.

If running asynchronous tasks that need context propagated by design (such as `DelegatingSecurityContextExecutor` or Spring Security async integration), never assume `ThreadLocal` copies automatically to new threads. For long-running jobs, prefer passing a verified user ID and re-checking authorization at execution time if needed.

### 9.2. Same session, two concurrent requests

Two requests in the same browser session can start nearly simultaneously:

```text
Request A (GET /private/me)            Request B (POST /logout)
  |                                        |
  +-- load old SecurityContext             +-- invalidate session
  |                                        |
  +-- controller processing                +-- complete logout
  |
  +-- response already processed using pre-logout snapshot
```

Completing logout in request B **does not instantaneously abort every thread already executing request A**. For ultra-sensitive actions, check account/session/revocation state right before transaction commit as required by the system; never treat an old `SecurityContext` snapshot as a global lock.

### 9.3. Multiple sessions across devices

Spring Security supports concurrent session control:

```java
// SessionManagement DSL snippet for form login:
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

When limiting sessions, configure `HttpSessionEventPublisher` and a matching session registry per documentation; multi-node environments require a distributed registry/session store. This configuration **caps concurrent login sessions**; it does not turn authentication events into exactly-once events.

If `SessionRegistry` uses a custom `UserDetails`, ensure proper `equals()/hashCode()` implementations for accurate session tracking; with multiple instances, per-instance in-memory registries cannot aggregate cluster-wide.

## 10. Designing idempotency and consistency when events have side effects

Listening to authentication events to increment a metrics counter is usually simple. However, if a listener triggers:

- Sending a "new login" alert email;
- Writing a compliance audit ledger entry;
- Incrementing failed-attempt counters leading to account lockout;
- Updating a risk score;
- Creating an external session or provisioning access;
- Forwarding events to a billing pipeline…

…then **duplicate processing has consequences**. Define which operations are **idempotent**:

| Side effect | Safer strategy |
| --- | --- |
| Per-event metrics counter | Tie to metric definition; if consumed via broker, deduplicate deliveries or count at producer |
| Compliance audit | Append records with a stable event ID and unique constraints for delivery retries |
| Email notifications | Rate-limit per user/session/device and event ID; avoid endless emails on retries |
| Failed login counter | Count **actual authentication attempts** per policy, not duplicate broker deliveries; defend against bots/distributed attacks |
| External provisioning | Use an idempotency key per authorized operation and check target state |
| Critical business transaction | Never trigger solely on `AuthenticationSuccessEvent`; require a valid request, authorization, validation, and a dedicated transaction |

A simple outbox pattern:

```text
Authentication outcome -> app creates audit event
    |
    | durable write within appropriate transaction/unit of work
    v
audit_outbox(event_id UNIQUE, event_type, payload, status)
    |
    | publisher retries when broker has not ACKed
    v
message broker
    |
    | consumer INSERT ... ON CONFLICT DO NOTHING
    v
audit_event_processed(event_id UNIQUE)
    |
    +--> side effect executed once per event_id
```

**Technical warning:** events emitted by `DefaultAuthenticationEventPublisher` are normally in-process Spring application events, **not transactionally persisted outboxes**. A DB transaction saving a user profile can roll back after the auth event already fired. If compliance/audit guarantees are required, design a dedicated persistence/outbox boundary and handle audit sink failures per SLA—never slap `@EventListener` on a method and call it "exactly once."

### 10.1. Standalone Java 17: deduplicate event delivery, not credential checks

To see the difference between **duplicate event delivery** and **two real logins**, create `EventDeliveryDemo.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class EventDeliveryDemo {

    record Delivery(String eventId, String kind) {}

    public static void main(String[] args) {
        List<Delivery> deliveries = List.of(
            new Delivery("event-001", "AUTH_SUCCESS"),
            new Delivery("event-001", "AUTH_SUCCESS"),
            new Delivery("event-002", "AUTH_SUCCESS"),
            new Delivery("event-003", "AUTH_FAILURE")
        );

        Set<String> processed = new HashSet<>();
        int persisted = 0;

        for (Delivery delivery : deliveries) {
            if (processed.add(delivery.eventId())) {
                persisted++;
                System.out.println("stored "
                    + delivery.eventId() + " " + delivery.kind());
            } else {
                System.out.println("duplicate delivery ignored "
                    + delivery.eventId());
            }
        }

        System.out.println("stored events=" + persisted);
    }
}
```

Run with Java 17+:

```bash
javac --release 17 EventDeliveryDemo.java
java EventDeliveryDemo
```

Exact stdout:

```text
stored event-001 AUTH_SUCCESS
duplicate delivery ignored event-001
stored event-002 AUTH_SUCCESS
stored event-003 AUTH_FAILURE
stored events=3
```

**Interpretation:** `event-001` was redelivered so it was stored only once, whereas `event-002`, though also `AUTH_SUCCESS`, must still be recorded because it is a **different** event. There is no rule saying "one user can only have one AUTH_SUCCESS." The `Set` here is purely in-memory; production requires durable uniqueness/indexes/concurrency controls.

## 11. Spring Boot 3.5.16 + Java 17 example: two providers, one publisher

This Servlet/MVC sample intentionally organizes:

1. `DaoAuthenticationProvider` for browser form login `UsernamePasswordAuthenticationToken`.
2. `ApiKeyAuthenticationProvider` for machine-to-machine client custom `ApiKeyToken`.
3. One `ProviderManager` holding both providers in **explicit order**.
4. One `DefaultAuthenticationEventPublisher` attached to the manager.
5. One `@EventListener` recording only thread-safe counters for manager-level successes/failures.
6. **Two `SecurityFilterChain` beans:** stateful web `formLogin` and a stateless API-key chain.
7. `/private/me` serving multiple requests via session; `/api/key/whoami` re-authenticating on every request.
8. An admin-only demo audit endpoint exposing no raw credentials in responses.

This is a hands-on project: a 256-bit random hex API key is supplied via an environment variable, with an in-memory demo user/password and in-process audit counters. **Do not treat this as a production auth server**, as it lacks database key rotation/revocation, distributed rate limiting, durable audit storage, or secret management.

### 11.1. File structure

```text
auth-events-consistency/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/events/AuthEventsApplication.java
└── src/test/java/demo/events/AuthEventsApplicationTests.java
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>auth-events-consistency</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-security` provides `ProviderManager`, `DaoAuthenticationProvider`, `AuthenticationEventPublisher`, and related filters; no separate "authentication events" library is needed.

### 11.3. application.yml

```yaml
server:
  port: 8080

app:
  api-key:
    secret: "${APP_API_KEY}"
```

The application refuses to start if `APP_API_KEY` is missing or malformed (per the provider below). In production, use a secret manager for key provisioning and store verifiers; never store real keys in source/version control. In this example, `APP_API_KEY` must be 64 lowercase hex characters generated by a CSPRNG.

### 11.4. AuthEventsApplication.java (complete Java file)

Create `src/main/java/demo/events/AuthEventsApplication.java`:

```java
package demo.events;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.LongAdder;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class AuthEventsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthEventsApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("local-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    DaoAuthenticationProvider passwordProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    ApiKeyProvider apiKeyProvider(
            @Value("${app.api-key.secret}") String secret) {
        return new ApiKeyProvider(secret);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    AuthenticationManager authenticationManager(
            DaoAuthenticationProvider passwordProvider,
            ApiKeyProvider apiKeyProvider,
            AuthenticationEventPublisher publisher) {

        // One manager responsible for deciding outcomes.
        ProviderManager manager = new ProviderManager(
            List.of(passwordProvider, apiKeyProvider));

        // Attach publisher directly: new ProviderManager(...)
        // does not publish events by default when constructed manually.
        manager.setAuthenticationEventPublisher(publisher);
        return manager;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiKeyChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        ApiKeyFilter apiKeyFilter = new ApiKeyFilter(manager);

        return http
            .securityMatcher("/api/key/**")
            .authenticationManager(manager)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            // Chain ONLY for header-based machine API keys,
            // do not use cookies/sessions for authentication.
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("API_READ"))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Created locally, DO NOT declare filter as a @Bean;
            // avoids Boot registering the filter outside SecurityFilterChain.
            .addFilterBefore(
                apiKeyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/audit").hasRole("ADMIN")
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            // Form Login manages session and CSRF automatically.
            .formLogin(Customizer.withDefaults())
            .build();
    }
}

/**
 * Token for API key: raw credential exists only before authentication.
 */
final class ApiKeyToken extends AbstractAuthenticationToken {

    private final String principal;
    private String rawKey;

    private ApiKeyToken(
            String principal,
            String rawKey,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.rawKey = rawKey;
        super.setAuthenticated(verified);
    }

    static ApiKeyToken requested(String rawKey) {
        return new ApiKeyToken(null, rawKey, null, false);
    }

    static ApiKeyToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyToken(clientId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return rawKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        rawKey = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Use verified factory after credential validation");
        }
        super.setAuthenticated(false);
    }
}

/**
 * Provider for a high-entropy demo API key.
 * Production patterns require key IDs, multiple keys, expiry, and a revocation store.
 */
final class ApiKeyProvider implements AuthenticationProvider {

    private static final Pattern SECRET_FORMAT =
        Pattern.compile("[0-9a-f]{64}");

    private final byte[] expectedDigest;

    ApiKeyProvider(String secret) {
        if (secret == null ||
                !SECRET_FORMAT.matcher(secret).matches()) {
            throw new IllegalArgumentException(
                "APP_API_KEY must be 64 lowercase hex characters");
        }
        expectedDigest = sha256(secret);
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return ApiKeyToken.class.isAssignableFrom(tokenType);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof ApiKeyToken token)
                || token.isAuthenticated()) {
            return null;
        }

        Object value = token.getCredentials();
        if (!(value instanceof String key)
                || !SECRET_FORMAT.matcher(key).matches()
                || !MessageDigest.isEqual(
                    expectedDigest, sha256(key))) {
            throw new BadCredentialsException("Invalid API key");
        }

        // Authorities and principal come from server, NOT from headers.
        return ApiKeyToken.verified(
            "integration-reader",
            List.of(new SimpleGrantedAuthority("API_READ")));
    }

    private static byte[] sha256(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(secret.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}

/**
 * Only inside the /api/key/** security chain.
 * Each request with an API key goes through the same manager;
 * does not store Authentication in HttpSession.
 */
final class ApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;

    ApiKeyFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> headers =
            request.getHeaders("X-API-Key");

        if (!headers.hasMoreElements()) {
            reject(response);
            return;
        }

        String rawKey = headers.nextElement();
        if (headers.hasMoreElements()) {
            // Do not accept multiple key values on the same request.
            reject(response);
            return;
        }

        try {
            Authentication accepted =
                manager.authenticate(ApiKeyToken.requested(rawKey));

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(accepted);
            SecurityContextHolder.setContext(context);

            chain.doFilter(request, response);
        } catch (AuthenticationException rejected) {
            // Publisher already handled failure for the manager outcome.
            // Do not publish another AuthenticationFailureEvent manually.
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private void reject(HttpServletResponse response)
            throws IOException {
        SecurityContextHolder.clearContext();
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
    }
}

/**
 * Thread-safe listener, avoiding logging raw credentials and full Authentication.
 * These are IN-MEMORY counters IN ONE JVM, not durable global auditing.
 */
@org.springframework.stereotype.Component
final class AuthEventCounters {

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();

    @EventListener
    void onSuccess(AuthenticationSuccessEvent event) {
        successes.increment();
    }

    @EventListener
    void onFailure(AbstractAuthenticationFailureEvent event) {
        failures.increment();
    }

    long successes() {
        return successes.sum();
    }

    long failures() {
        return failures.sum();
    }
}

@RestController
class Endpoints {

    private final AuthEventCounters events;

    Endpoints(AuthEventCounters events) {
        this.events = events;
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/private/me")
    Map<String, String> browserUser(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @GetMapping("/api/key/whoami")
    Map<String, String> apiClient(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @GetMapping("/audit")
    Map<String, Long> audit() {
        return Map.of(
            "successes", events.successes(),
            "failures", events.failures());
    }
}
```

**Consistency guarantees preserved in the code:**

- Only **one** shared `AuthenticationManager`, with two providers separated by token type; passwords are never "tested as API keys."
- `ProviderManager.setAuthenticationEventPublisher(...)` is called exactly once at manager creation; the event listener does not republish the same event.
- `@EventListener` listens only to `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent`; it does not lump `InteractiveAuthenticationSuccessEvent` into the same metric as another manager success.
- `LongAdder` prevents lost updates on counters across concurrent requests within the **same JVM**.
- The API key chain uses `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository`; each API request authenticates independently. The web chain uses form login/sessions.
- `ApiKeyFilter` runs once on the right chain, catches `AuthenticationException`, and returns 401. When keys are missing or headers are duplicated, the filter rejects **before calling the manager**, so **no manager failure event is emitted** for those requests; log HTTP rejections separately if auditing is needed.
- `ApiKeyToken` has two states: before auth it holds the raw key; after auth it holds server-assigned principal/authorities with no raw key.
- `MessageDigest.isEqual` compares SHA-256 digests against a high-entropy demo key without storing plaintext secrets in source. Production patterns need key IDs/DB/revocation/expiry and request size limits.
- Being logged into the browser does **not** allow calling `/api/key/**` via session; the stateless chain requires its own header.
- An API key request succeeding at the manager can still get 403 if it lacks authority for a new endpoint; **a success event does not guarantee HTTP 2xx**.

### 11.5. Running locally

Generate a random API key with OpenSSL:

```bash
export APP_API_KEY="$(openssl rand -hex 32)"
mvn spring-boot:run
```

Run on a machine with Java 17+ and Maven. Never print the key to public logs or store it in plaintext in Git. To test the API from a terminal sharing the environment variable:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/key/whoami \
  -H "X-API-Key: $APP_API_KEY"

curl -i http://localhost:8080/api/key/whoami
```

Expected results:

- `/health`: HTTP 200, body `ok`.
- API with valid key: HTTP 200 and JSON `{"name":"integration-reader"}`.
- API without key: HTTP 401, no success event; this request never passed credentials to the manager.
- Calling the API with the valid key **a second time**: produces a **second** success event, because the chain remembers no session.
- Opening `http://localhost:8080/private/me` in a browser while unauthenticated: redirects to the login page.
- Logging in as `learner` / `local-demo-password` on a **local learning machine**; once logged in, the session allows multiple GET `/private/me` requests.
- `/audit` is readable only by users with `ROLE_ADMIN` to view in-memory metrics.

**Note:** shell `export` does not carry over into a new terminal window; share keys via a secret management channel rather than screenshots or pasting into issue trackers.

## 12. Testing with MockMvc: manager outcomes and multiple requests

The test suite below has two goals:

1. Prove **two providers matching two token types** both authenticate properly.
2. Prove **events follow `manager.authenticate` invocations**, not prior logged-in request counts.

Create `src/test/java/demo/events/AuthEventsApplicationTests.java`:

```java
package demo.events;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.api-key.secret=" +
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
})
@AutoConfigureMockMvc
class AuthEventsApplicationTests {

    private static final String KEY =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    @Autowired
    MockMvc mvc;

    @Autowired
    AuthEventCounters events;

    @Test
    void apiKeyAuthenticatesViaItsOwnProvider()
            throws Exception {
        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name")
                .value("integration-reader"));
    }

    @Test
    void repeatedStatelessRequestsProduceSeparateSuccessEvents()
            throws Exception {
        long before = events.successes();

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk());

        assertThat(events.successes())
            .isEqualTo(before + 2);
    }

    @Test
    void invalidKeyProducesManagerFailureEvent()
            throws Exception {
        long before = events.failures();

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key",
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))
            .andExpect(status().isUnauthorized());

        assertThat(events.failures())
            .isEqualTo(before + 1);
    }

    @Test
    void missingKeyIsRejectedBeforeCallingManager()
            throws Exception {
        long before = events.failures();

        mvc.perform(get("/api/key/whoami"))
            .andExpect(status().isUnauthorized());

        assertThat(events.failures())
            .isEqualTo(before);
    }

    @Test
    void passwordLoginSurvivesSubsequentRequestsViaSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mvc.perform(get("/private/me")
                .session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));

        mvc.perform(get("/private/me")
                .session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }

    @Test
    void badPasswordIsARealAuthenticationFailure()
            throws Exception {
        long before = events.failures();

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection());

        assertThat(events.failures())
            .isEqualTo(before + 1);
    }
}
```

Run:

```bash
mvn test
```

Expected under Java 17+ with matching dependencies: **6 tests pass**. This is a design expectation, not a report of having executed Maven. When tests run **in parallel** or multiple test classes mutate the counters concurrently, delta assertions using before/after differences are no longer fully isolated; disable parallel execution for this fixture or use test-scoped spies/event collectors with clear correlation IDs.

**Test limitations:** `MockMvc` simulates the Servlet layer; it does not verify reverse proxies, session clustering, network retries, gateway duplication, DB outboxes, broker at-least-once delivery, or real external identity servers. Those requirements need integration/load/fault-injection tests.

### 12.1. What does each result prove?

| Test | What is proven | What is not yet proven |
| --- | --- | --- |
| Valid API key | Dedicated provider and manager handle the token | Production key issuance/rotation and revocation |
| Two API key GETs | Two manager calls produce two success events in the same process | System-wide unique login user count |
| Invalid API key | One manager failure event for one rejected credential | Rate limiting, account lockout, broker durability |
| Missing key | No manager failure event if filter rejects before manager | No HTTP request happened; an HTTP request was still rejected |
| Form login and two GETs | Session reuses authentication on post-login GETs | Cluster-wide logout/expired session behavior |
| Wrong password | Manager emits a failure event for one login attempt | Timing side-channels, brute-force defenses |

## 13. Subtle pitfalls: ProviderManager, event publishers, and caches

### 13.1. Duplicate publishers with a parent manager

If both parent and child publish, one outcome can pass through both. The fix is not checking "same username within 5 seconds," because that drops legitimate back-to-back logins. Inspect the **publisher architecture**, provider routing, and event sources; if delivery deduplication is needed, use a **server-issued event ID**, never just username/time.

### 13.2. Duplicate events from a listener republishing

An `@EventListener` should not call `publisher.publishEvent(event)` on the same event instance without guards, as it can cause an infinite loop. If translating to another event type, define a new event with clear semantics (e.g., `AuditAuthOutcomeRecorded`) and clear responsibility boundaries.

### 13.3. Erasing credentials and cached principals

`ProviderManager` erases credentials on a successful `Authentication` by default when implementing `CredentialsContainer`. This is good security hygiene, yet if `Authentication.principal` shares **the exact same cached `UserDetails` instance** whose credentials get erased, subsequent authentications may fail due to an erased password hash.

The right fix is creating/copying principals safely, designing caches not to share mutable objects, or configuring cache/provider behavior properly. **Do not rush to disable `eraseCredentialsAfterAuthentication` across the whole manager** to work around a cache bug, as doing so keeps passwords/tokens in sessions longer than necessary.

### 13.4. Provider falling back to local store after external outage

If two providers both support `UsernamePasswordAuthenticationToken`, a local fallback might accept an account that an external IdP marks as locked/revoked. Avoid sharing username namespaces or ambiguous fallbacks; enforce clear token types, realms, tenants, chains, and provider mappings. An undecided provider returns `null`; invalid credentials or locked states must fail per contract and threat model.

### 13.5. Event listeners blocking requests or throwing errors

Spring application events are dispatched synchronously by default unless async is configured. A listener making slow HTTP or DB calls increases login latency; a listener throwing an unchecked exception can disrupt the authentication path.

If auditing is mandatory, define the policy when auditing is unavailable (fail-closed or controlled degraded mode) and use an appropriate outbox/buffer. If metrics tolerate sample loss during incidents, keep listeners lightweight and isolate errors; **never accidentally treat a monitoring outage as a wrong password**.

### 13.6. Event counts shifting after migrating to stateless

A session-based app emits one auth event at login, whereas switching to per-request bearer/API keys can raise event volume to match the request rate. Never leave old logic like "send a new-login email on every `AuthenticationSuccessEvent`" enabled for API clients; apply thresholds/windows and filter by mechanism.

## 14. Layered consistency checklist

| Layer | Check question | Recommended rule |
| --- | --- | --- |
| Provider | Do multiple providers support the same token type? | Clearly define order/fallbacks and account state rules |
| Manager | Is there a shared parent? | Prevent double publication; verify final outcome |
| Event publisher | Does a manually created ProviderManager have a publisher attached? | One publisher with clear ownership |
| Exception mapping | Do custom exceptions emit events? | Configure exact mappings/fallback and test |
| Filter | Can one request authenticate twice due to filter auto-registration? | Manage `SecurityFilterChain` and `FilterRegistration` |
| Session | Do browser GETs after login re-authenticate? | Check `SecurityContextRepository` and session mode |
| Stateless | Are keys/bearer tokens verified on every request? | Never treat session event counts as request counts |
| Retries | Do network retries create new authentication attempts? | Separate internal/HTTP/event-delivery retries |
| OTP | Can a consumed token be reused? | Enforce single-use per policy and anti-replay |
| Concurrency | Are counters and event processing thread-safe? | Use `LongAdder`/atomic DB updates/unique constraints |
| Audit | Must events be durable? | Transactional outbox, event ID, replay, and deduplication |
| Security | Are raw passwords/tokens logged? | Redaction, least privilege, retention |
| Authorization | Are auth success events confused with business operation success? | Enforce separate authorization at API/service |
| Deployment | Do multiple instances share sessions/counters? | Shared session store/metrics aggregation/outbox |

**Define acceptance criteria before implementing**, for instance: "One final successful `manager.authenticate` call emits only one manager success event at the owned publisher; an outbox retry with the same event ID never triggers side effects twice; two independent API key requests create two auth attempts; session-backed browser GETs do not increment login counters."

## 15. Diagnosing common symptoms

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| Login succeeds yet no `AuthenticationSuccessEvent` | Manually created manager missing publisher; listener not registered | Check `setAuthenticationEventPublisher` and component scan |
| Two success events for one login | Duplicate parent/child publishers; filter running twice; or `InteractiveAuthenticationSuccessEvent` miscounted together | Check event classes, call stacks, and manager graph |
| Wrong password in provider A yet provider B logs in | `ProviderManager` fallback when both support the token | Check `supports`/ordering and account namespaces |
| Locked account still logs in via another provider | Provider misinterprets status or bypasses policy | Ensure account status failures halt and providers do not bypass |
| Every API key request increments login counter | Stateless API invokes manager per request | Separate API auth request metrics from session logins |
| Browser GET after login emits no new success event | Uses `SecurityContext` from session | Normal; never force re-authentication just to emit events |
| Old GET still finishes after logout | Request started before logout or session not revoked cluster-wide | Evaluate races, session invalidation, and transactional policy |
| Custom login succeeds first time, anonymous on next request | Custom filter sets context without saving to repository | Call `saveContext` if stateful is desired; inspect session |
| Two concurrent requests for same account lose failure counts | Non-atomic `int++` counter or unsynced cache | Use `AtomicLong`/`LongAdder` or atomic DB updates |
| Broker redelivery sends alert email twice | Consumer lacks deduplication/outbox | Use unique `eventId` and unique constraint |
| Listener error causes login POST 500 | Synchronous listener throws exception | Isolate side effects; review audit guarantee policy |
| Custom `AuthenticationServiceException` subclass emits no failure event | Default mapping requires exact exception class | Configure additional mappings or fallback |
| Quota-blocked attempt emits no auth failure event | Rate limiter blocks before manager | Emit separate security-rejection audit event |
| HTTP 403 despite authentication success event | `AuthorizationFilter` found missing role/scope | Authn success is not authorization success |
| Cannot distinguish network retries from user re-logins | Missing request ID/attempt ID or unlinked logs | Design tracing/correlation and idempotency |
| Revoked JWT still accepted from cache | Stale token validation/cache/state | Choose proper TTL/invalidation and fail closed |

**Minimal debugging checklist:**

1. Did the request hit the right chain/filter and execute the filter only once?
2. Which manager is used? Is there a parent? What is the provider order and `supports(...)` behavior?
3. For one `authenticate(...)` call, which provider returned non-null/null/exception? What was the final outcome?
4. Which `AuthenticationEventPublisher` does the manager use? Do both parent and child publish?
5. Which event classes is the listener counting? Is it mixing in `InteractiveAuthenticationSuccessEvent`?
6. Does the request use a session or stay stateless? Does the second request actually invoke the manager?
7. Did the client/gateway perform an HTTP retry, or did the event pipeline perform a broker redelivery?
8. Are counters/audit stores thread-safe, shared across instances, and deduplicated?
9. Did authentication succeed while authorization or a business transaction was rejected/rolled back downstream?
10. Are credentials, session IDs, or raw exceptions leaking into logs/tracing?

Never log full `Authentication` credentials or secret-bearing exceptions just to debug; use correlation IDs and filtered exception classes/categories.

## 16. Self-check questions

1. **Does one `authenticate` call traversing two providers automatically emit two authentication events?** No. Standard `ProviderManager` publishes based on the final outcome; custom providers could emit other events if designed by the app.
2. **If Provider A throws BadCredentials and Provider B succeeds, what does the manager return?** B's result; the earlier error is no longer the final outcome.
3. **If Provider A throws LockedException, does it continue to B?** Per the `AccountStatusException` contract, remaining providers are not tried.
4. **Does `new ProviderManager(...)` emit events by default?** Never assume so; explicitly attach an `AuthenticationEventPublisher`.
5. **Why can parent/child managers produce duplicate events?** Both parent and child may publish the outcome that the child receives from the parent.
6. **Must a browser GET with a valid session emit `AuthenticationSuccessEvent`?** No. It may simply load `SecurityContext`.
7. **Can two API key GET requests with the same key emit two success events?** Yes, if the manager is called on each stateless request.
8. **Does `AuthenticationSuccessEvent` guarantee the controller returned HTTP 200?** No; authorization, validation, or services can still reject/fail.
9. **Is a custom `AuthenticationException` subclass automatically mapped to its parent's event?** Not by default; the default publisher maps by exact class, so register mappings as needed.
10. **Is deduplicating all authentication events by username and timestamp accurate?** No; two genuine logins can occur close together for the same username.
11. **Does the `LongAdder` counter in the demo guarantee cluster-wide auditing?** No; it is only thread-safe within one JVM.
12. **How do gateway auth retries differ from broker redeliveries?** Gateways can create new authentication attempts; broker redeliveries resend the same audit event.
13. **Can key verification be skipped when a client resends an old idempotency key?** No. Idempotency must never become an authentication bypass.
14. **Why must a custom filter wanting session persistence call `saveContext`?** Spring Security 6+ uses explicit-save behavior for contexts set by custom code.
15. **Does `SessionConcurrency` `maximumSessions(1)` guarantee only one auth success event per user?** No. It is a session policy, not event deduplication.
16. **If an email-sending listener fails, what should happen to login?** It is decided by policy balancing auditing and availability; never arbitrarily turn it into "bad password."
17. **Does a login blocked by a rate limiter before the manager emit a manager failure event?** Not necessarily; track separate request/security rejection metrics.
18. **Why must you watch `eraseCredentialsAfterAuthentication` when caching `UserDetails`?** Sharing an erased object can unexpectedly wipe verification data in the cache.
19. **How do you prove delivery retries do not cause duplicate side effects?** Use a durable event ID, unique constraints, and tests redelivering the same ID.
20. **Can a provider return `null` to "defer to another provider"?** Yes, though invalid credentials/account states must be represented accurately rather than using `null` to hide security errors.

## 17. Official references

- Spring Security 6.5 – Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 – Authentication Events: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html
- Spring Security – ProviderManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security – AuthenticationProvider API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security – DefaultAuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html
- Spring Security 6.5 – DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 – Session Management and Explicit Save: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security – SecurityContext persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security – Concurrent Session Control: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_configuring_concurrent_session_control
- Spring Security – DelegatingSecurityContextExecutor: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/concurrency.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
