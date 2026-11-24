# Failing Safely When Configuration Is Missing, External Services Fail, or Data Is Invalid

A secure application must properly answer **"If there is insufficient information to confirm an action is permitted, what will the system do?"**. In practice, failures do not come only from attackers: a forgotten environment variable, an unresponsive external authentication system, malformed input data, or an interrupted authorization database can all push the application into an indeterminate state.

The key principle is **never turn uncertainty into access**. For sensitive operations, the system must refuse execution or temporarily suspend offering that operation until safety conditions are verified. At the same time, handle errors in a controlled manner: distinguish invalid requests, missing permissions, and unavailable services; keep data consistent; log usefully; avoid leaking secrets; and recover only when conditions are met.

This lesson belongs to Spring Security's security mindset, focusing on designing **safe defaults**, **fail closed**, **graceful degradation**, and error handling across configuration, external dependency, and user data boundaries.

## 1. Foundational Principles

### 1.1. Fail Closed, Fail Open, and Graceful Degradation

| Behavior | Meaning | Example | When Appropriate |
| --- | --- | --- | --- |
| **Fail closed** | When permissions or safety conditions cannot be confirmed, do not execute the protected action | Refund permission service stops responding → do not transfer money | Sensitive actions, identity checks, permissions, or security policies |
| **Fail open** | When a check fails, the system still lets the action proceed | Skipping authorization because the policy server errored | Usually dangerous for security gates; never choose as default for sensitive tasks |
| **Fail fast** | Detect invalid required configuration at startup and report a clear error | Missing signing key or missing admin protection policy → app refuses to start | Configuration mistakes that must be fixed before accepting traffic |
| **Graceful degradation** | Keep providing genuinely safe features while another dependency fails | Product recommendation service fails → still display basic catalog | Auxiliary features that do not alter permissions, integrity, or data scope |

**Fail closed does not mean always returning 403.** The safe decision is *do not grant access or execute the operation*; the message and HTTP status should still reflect the situation. When the authorization service is disrupted, HTTP **503 Service Unavailable** usually describes the issue better than **403 Forbidden**, provided the request still cannot proceed to cause side effects.

**Fail fast does not mean every glitch must crash the entire system.** Invalid mandatory security configuration should prevent the app from serving traffic. Yet an auxiliary service like recommendations failing can be contained at that feature's boundary without affecting other critical APIs.

### 1.2. Distinguishing Result Types

A policy can return:

- **ALLOW**: checked and sufficient evidence exists to execute the action.
- **DENY**: checked and the outcome shows the action is not permitted.
- **UNAVAILABLE / ERROR**: unable to check because required configuration or dependencies are unavailable; never silently convert to ALLOW.
- **INVALID_REQUEST**: input data fails acceptance criteria; reject and describe the error safely.

Do not collapse **DENY**, **UNAVAILABLE**, and **INVALID_REQUEST** into the same internal cause, because their remediation, retry behavior, monitoring, and HTTP responses differ. However, all three must block the protected operation whenever a valid ALLOW decision is absent.

### 1.3. "Proof of Permission" Thinking

For an operation requiring authorization, a clean workflow is:

```text
Incoming request
  |
  +-- Valid data? ------------------------ No --> REJECT (appropriate 4xx)
  |
  +-- Config/policy ready? --------------- No --> UNAVAILABLE (do not execute)
  |
  +-- Valid identity authentication? ----- No --> UNAUTHENTICATED
  |
  +-- Permission check operational? ------ No --> UNAVAILABLE (do not execute)
  |
  +-- Policy allows on resource? --------- No --> DENY
  |
  v
ALLOW -> execute business logic within safe boundary
```

This is a design-level decision diagram, not the fixed execution order of all Spring Security filters. A request may be blocked earlier by CSRF or another security filter. The goal is executing the operation only after **the mandatory conditions for that operation** have all passed.

## 2. When Security Configuration Is Missing or Wrong

Configuration can come from `application.yml`, environment variables, secret managers, config servers, or startup defaults. Missing a property never gives the application license to drop security policies.

### 2.1. Classifying Configuration by Mandatory Level

| Config Category | Example | Safe Behavior When Missing/Wrong |
| --- | --- | --- |
| **Required to verify trust** | JWT issuer/audience, signing-key configuration, trusted public key source, required secrets | Fail fast or reject affected authentications; never skip signature verification |
| **Required to decide permissions** | Admin protection policy, valid permission list, tenant boundary | Fail fast/deny; never fall back to `permitAll()` |
| **Required to preserve data consistency** | Permission store connection, transaction control parameters | Halt dependent operations if safety cannot be guaranteed |
| **Optional features** | Enabling recommendations, UI styling, optional telemetry | Safe defaults or disable only that feature |
| **Security control flags** | Enabling admin action guards, export limits | Must define explicit default mode; never default controls to off |

**Dangerous** configuration example:

```java
// Anti-pattern example, do not apply:
if (adminAuthority == null) {
    http.authorizeHttpRequests(auth ->
        auth.requestMatchers("/api/admin/**").permitAll()
    );
}
```

A deployment mistake leaving a config variable blank turned into **privilege bypass**. The fix is requiring valid config values or refusing to let the application/sensitive entry point operate.

### 2.2. Spring Boot 3 / Spring Security 6 Pattern: Missing Config Fails Startup

For a Spring Boot 3 project using `spring-boot-starter-web` and `spring-boot-starter-security`, the configuration class below requires the `app.security.admin-authority` property:

```java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${app.security.admin-authority}") String adminAuthority
    ) throws Exception {
        if (adminAuthority == null || adminAuthority.isBlank()) {
            throw new IllegalStateException(
                "Required admin authority must be configured"
            );
        }

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
                .requestMatchers("/api/admin/**").hasAuthority(adminAuthority)
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

In `application.yml`:

```yaml
app:
  security:
    admin-authority: "ROLE_ADMIN"
```

Meaning:

1. When the required property is missing, Spring's placeholder resolution fails; the app cannot construct the security chain and fails to start normally. If the property is empty/whitespace, the explicit check also rejects the config.
2. `/api/admin/**` accepts only principals with the exact `ROLE_ADMIN` authority; all other `/api/**` routes require authentication; any other path hits `denyAll()`.
3. `GET /public/status` is public per access policy. `permitAll()` still passes through appropriate security filters.
4. The example assumes the app has an account/authentication mechanism. This is a configuration class for a Spring Boot project, **not a standalone Java file compiled directly with `javac`**.
5. In production, health endpoints must be designed safely; never return secrets, config contents, permission lists, or sensitive internal details to public callers.

When dynamically modifying or reloading security configs, validate the new version **before applying it**. Never let the system drop into an empty policy window between clearing old config and loading new config.

### 2.3. Defaults Must Be Semantically Safe

Avoid patterns like:

- `requiredPermission = ""` and treating empty string as permission for everyone.
- `unknownRole -> ROLE_ADMIN` "so the system keeps running."
- `security.enabled = false` when an environment variable is missing.
- Skipping token verification because the signing key has not loaded yet.
- Automatically granting anonymous access to internal APIs when the user store cannot be found.

For mandatory policies or roles, **configuration errors should fail startup or disable dependent operations in a controlled way**. For harmless options like display names, defaults may let the system continue operating.

## 3. When External Systems Are Unavailable

An application may depend on an identity provider (IdP), policy decision point (PDP), JWKS endpoint, Redis/session store, database, tenant service, payment gateway, or other business services. Distinguish two cases:

- **External system validly replies no permission:** this is **DENY**.
- **External system fails to reply reliably:** this is **UNAVAILABLE**. Never assume permission was granted.

### 3.1. Example: External Authorization Service Failure

Suppose `POST /api/orders/100/refund` must confirm the caller has refund permission and the order meets conditions. When the permission service times out:

```text
User -> Refund API -> Permission service (timeout)
                         |
                         +--> No trusted ALLOW decision
                                  |
                                  v
                            Do not refund
                                  |
                                  v
                    Appropriate service error response
```

Never do this:

```java
// Anti-pattern: timeout allows the transaction.
try {
    return permissionClient.isAllowed(userId, orderId, "refund");
} catch (Exception ignored) {
    return true;
}
```

Instead, **block the action**, log the incident, and return a meaningful error. If the application maps an unavailable dependency to a business exception `DependencyUnavailableException` and returns 503, still ensure **no refund operation has occurred**.

Distinguishing typical outcomes:

| Condition | Safe Decision | Typical Appropriate HTTP Status |
| --- | --- | --- |
| Missing/invalid credentials | Cannot authenticate | 401 for Basic/Bearer-style APIs |
| Authenticated, policy denies | Insufficient permission | 403 |
| Resource not found | Do not process | 404; sometimes 404 is used to hide out-of-scope resource existence |
| Request missing/invalid valid data | Do not process | 400; some APIs use 422 for semantic errors |
| Authorization system or required data down | Do not process; may retry after recovery | 503 or appropriate 5xx |
| Valid operation with full proof of permission | Allow processing | 2xx/3xx per API |

HTTP codes depend on the auth protocol, context, and API contract. For example, form login typically redirects to a login page instead of returning 401 directly. More important than the status code is **never turning a system error into ALLOW**.

### 3.2. IdP, OAuth2, JWT, and JWKS: No "Shortcuts"

- **New logins during IdP outage:** may be impossible. Never create a logged-in session based solely on a user-submitted email or name.
- **JWTs require verification:** verify signature, allowed algorithms, issuer, audience, expiration, and token-type conditions. If trusted keys cannot be loaded, never skip signature validation.
- **Trusted cached public keys:** within an appropriate TTL and policy, a resource server can still verify tokens locally without hitting the IdP on every request. Caches must be bounded and have rotation/revocation plans; never extend keys or privileges indefinitely to mask outages.
- **Sessions validly authenticated before an outage:** may continue within session policy and expiration limits. However, if an operation requires checking up-to-date permissions while the authz service is down, that operation must still be blocked.
- **Identity tokens differ from access tokens:** use only the right token type and verification criteria for the right purpose. Never trust an unverified token or wrong-audience token just because it decodes.

The rule is **proceed only with valid authentication and authorization proof under current policy**. "Previously authenticated" does not implicitly authorize all future requests.

### 3.3. Retries, Timeouts, Circuit Breakers, and Caching

Resilience patterns are only safe when they do not compromise security decisions:

1. **Bounded timeouts:** never hang requests indefinitely. A timeout must count as a check failure, never ALLOW.
2. **Bounded retries:** retry only safe operations when appropriate. For refunds, transfers, granting permissions, or sensitive updates, enforce idempotency keys / transaction IDs and duplicate-prevention logic before retrying.
3. **Circuit breakers:** reduce load on failing dependencies, yet an open circuit state remains **UNAVAILABLE**, not an allow signal.
4. **Cache policies:** cache results strictly scoped by subject/action/resource/tenant, with TTLs, invalidation mechanisms, and revocation handling. Caching ALLOW decisions too long can preserve revoked permissions.
5. **Last known good:** may fit verified configs with versioning, expiration, and governance policies. Never assume "the old version is always safe"; a config may have been pulled due to a vulnerability or permission change.
6. **Graceful degradation:** a failing product-recommendation or avatar service can hide auxiliary UI; an outage in authorization or tenant isolation must never lower checking standards.

**Transaction note:** if missing permissions or a dependency failure is discovered only after side effects occurred, returning 503 is insufficient. Design check ordering, transactions/rollbacks, outboxes, idempotency, and reconciliation properly to avoid an "executed yet returned error" state. Avoid placing untrusted network calls inside long-running transactions without evaluating timeouts and locks.

## 4. When Input Data Is Invalid

Data from requests, headers, path variables, query parameters, message queues, and external callbacks all cross a **trust boundary**. Data may be wrong due to user error or deliberate exploitation. Never use unvalidated data as grounds for granting permissions or mutating state.

### 4.1. Checking at Three Levels

1. **Syntax and data types:** is JSON valid, are numeric fields really numbers, do IDs match expected formats, are required fields present?
2. **Limits and business rules:** is the amount positive, is quantity within quota, are timestamps valid, does resource state allow the operation?
3. **Permission boundaries and trusted data:** is the caller allowed to modify this object, does tenant match the trusted source, is the caller allowed to set this role/price/ownerId?

Example request:

```json
{
  "orderId": "ORD-100",
  "amountCents": -500,
  "tenantId": "another-shop",
  "isAdmin": true
}
```

This payload has several independent issues. Negative `amountCents` violates business rules; client-sent `tenantId` and `isAdmin` prove neither permissions nor scope. Checking `amountCents > 0` is **insufficient** to know whether the user may refund that order.

### 4.2. Bean Validation in Spring Boot 3

In Spring Boot 3 using Spring MVC and the `spring-boot-starter-validation` dependency, you can declare a DTO:

```java
package example.orders;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record RefundRequest(
    @NotBlank String orderId,
    @NotNull @Positive Long amountCents,
    @NotBlank String reason
) {}
```

Using it in a controller:

```java
@PostMapping("/api/refunds")
public ResponseEntity<Void> refund(
        @Valid @RequestBody RefundRequest request,
        Authentication authentication
) {
    refundService.refund(
        authentication,
        request.orderId(),
        request.amountCents(),
        request.reason()
    );
    return ResponseEntity.noContent().build();
}
```

These are **two illustrative snippets inside a Spring Boot project**, not a standalone program compiled with `javac`; the controller requires imports for `@PostMapping`, `@Valid`, `@RequestBody`, `ResponseEntity`, `Authentication`, and a real service implementation. With default Spring MVC, a request body failing Bean Validation typically yields `MethodArgumentNotValidException` and HTTP 400 unless customized by a handler.

Rule to preserve: the DTO **never accepts role, isAdmin, or tenantId as granted privileges**. The service must extract identity and permissions from the authenticated `Authentication`; query the order scoped by trusted tenant; and verify permissions and actual state **before refunding**. `@Valid` handles input validation, **not authorization**.

Do not rely solely on annotations to prevent all bugs: parseable types do not imply business validity, and valid inputs can still cause SQL injection/XSS if mishandled. Pair with parameterized queries, output encoding, length caps, proper canonicalization, path/file controls, and domain constraints.

### 4.3. When Data Comes from External Services

An HTTP 200 from an external system does not prove its content is trustworthy. Validate schema, required fields, identifiers/tenants, signatures, or origin when required by protocol. For example:

- An unverified payment webhook must not update payment status.
- An event carrying a `userId` must not automatically treat that user as the API's authenticated caller.
- An unparseable PDP response must never be interpreted as ALLOW.
- If a new or unknown `decision` value appears, deny / raise a protocol error by default instead of treating it as true.
- When required `ownerId` or `tenantId` is missing for a permission check, never default to "no owner means anyone can view."

### 4.4. Do Not "Fix" Bad Data by Escalating Privileges

Dangerous anti-patterns:

```java
// Do not apply these patterns.
boolean isAdmin = request.isAdmin();            // trusting client's claim
String tenantId = request.tenantId();           // trusting self-declared scope
String owner = order.ownerId() == null ? "*" : order.ownerId();
boolean canWrite = lookupPermission(user) == null; // null becomes ALLOW
```

Instead, verify principal and permissions through trusted mechanisms; look up owner/tenant from server-side data; and leave state-changing requests unexecuted whenever decision data is incomplete.

## 5. Standalone Java 17 Pattern: Safe Decision with Four Outcomes

This example simulates an access and refund gate. The goal is clearly distinguishing **missing config**, **unavailable dependency**, **invalid input**, and **lacking permission** without any of them turning into ALLOW.

Create **`SafeDecisionDemo.java`**:

```java
import java.util.Set;

public class SafeDecisionDemo {

    enum Action { READ_ORDER, REFUND }

    enum Decision { ALLOW, DENY, INVALID_REQUEST, UNAVAILABLE }

    record Config(boolean policyConfigured) {}

    record Principal(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record Request(
        String orderId,
        String tenantId,
        Action action,
        long amountCents
    ) {}

    @FunctionalInterface
    interface OwnershipGateway {
        boolean isOwner(Principal principal, Request request)
            throws DependencyUnavailableException;
    }

    static class DependencyUnavailableException extends Exception {}

    static Decision decide(
        Config config,
        Principal principal,
        Request request,
        OwnershipGateway gateway
    ) {
        // Do not pass invalid data into business logic.
        if (request == null
                || request.orderId() == null
                || request.orderId().isBlank()
                || request.tenantId() == null
                || request.tenantId().isBlank()
                || request.action() == null
                || (request.action() == Action.REFUND
                    && request.amountCents() <= 0)) {
            return Decision.INVALID_REQUEST;
        }

        // Missing required policy or dependency: do not grant access.
        if (config == null || !config.policyConfigured()
                || gateway == null) {
            return Decision.UNAVAILABLE;
        }

        if (principal == null || !principal.authenticated()
                || principal.userId() == null
                || principal.tenantId() == null
                || principal.permissions() == null) {
            return Decision.DENY;
        }

        // Principal's tenant is verified, never blindly trust the request.
        if (!principal.tenantId().equals(request.tenantId())) {
            return Decision.DENY;
        }

        String requiredPermission = switch (request.action()) {
            case READ_ORDER -> "order:read";
            case REFUND -> "order:refund";
        };

        if (!principal.permissions().contains(requiredPermission)) {
            return Decision.DENY;
        }

        try {
            return gateway.isOwner(principal, request)
                ? Decision.ALLOW : Decision.DENY;
        } catch (DependencyUnavailableException ex) {
            return Decision.UNAVAILABLE;
        }
    }

    public static void main(String[] args) {
        Config ready = new Config(true);
        Config missing = new Config(false);

        Principal alice = new Principal(
            "alice", "shop-a", true,
            Set.of("order:read", "order:refund")
        );
        Principal bob = new Principal(
            "bob", "shop-a", true, Set.of("order:read")
        );
        Principal anonymous = new Principal(
            "guest", "shop-a", false, Set.of("order:read")
        );

        Request read = new Request(
            "ORD-100", "shop-a", Action.READ_ORDER, 0
        );
        Request invalidRefund = new Request(
            "ORD-100", "shop-a", Action.REFUND, -100
        );

        OwnershipGateway ownerLookup = (subject, request) ->
            subject.userId().equals("alice")
                && request.orderId().equals("ORD-100");

        OwnershipGateway offline = (subject, request) -> {
            throw new DependencyUnavailableException();
        };

        System.out.println("Normal: "
            + decide(ready, alice, read, ownerLookup));
        System.out.println("Different owner: "
            + decide(ready, bob, read, ownerLookup));
        System.out.println("Anonymous: "
            + decide(ready, anonymous, read, ownerLookup));
        System.out.println("Invalid refund: "
            + decide(ready, alice, invalidRefund, ownerLookup));
        System.out.println("Missing config: "
            + decide(missing, alice, read, ownerLookup));
        System.out.println("Dependency down: "
            + decide(ready, alice, read, offline));
    }
}
```

Run with JDK 17 or higher:

```bash
javac SafeDecisionDemo.java
java SafeDecisionDemo
```

**Exact stdout:**

```text
Normal: ALLOW
Different owner: DENY
Anonymous: DENY
Invalid refund: INVALID_REQUEST
Missing config: UNAVAILABLE
Dependency down: UNAVAILABLE
```

Case-by-case explanation:

- **Normal:** Alice has `order:read`, matching tenant, and owns the order, so she gets ALLOW.
- **Different owner:** Bob is logged in and has general read permission yet does not own the exact order; gateway decides DENY.
- **Anonymous:** lacks authenticated status, so DENY without calling the gateway.
- **Invalid refund:** negative amount is blocked before checking permissions or causing side effects.
- **Missing config:** policy decisions cannot be trusted, so UNAVAILABLE is returned; there is no default ALLOW branch.
- **Dependency down:** exception from gateway maps to UNAVAILABLE, preserving the rule of never granting access without proof.

Intentionally simplified example: principal, permissions, and tenant are constructed in code; real apps must obtain them from trusted authentication/sources. `OwnershipGateway` must query real data scoped by tenant, checking state and business rules. `Decision.ALLOW` here is only a **decision**, not the refund execution itself. Mapping to HTTP and executing transactions belong in controllers/services.

### 5.1. Mapping Internal State to API Results

| Decision | Handling Direction | Notes |
| --- | --- | --- |
| `ALLOW` | Proceed with controlled business logic | Still needs transactions, state checks, duplicate prevention |
| `DENY` | Stop, usually 403 | If no valid identity exists, auth mechanism may return 401 |
| `INVALID_REQUEST` | Stop, return 400/422 per contract | Never send stack traces or sensitive data |
| `UNAVAILABLE` | Stop, return 503/appropriate 5xx | Monitor, handle incident, retry safely if appropriate |

In the learning example, we use a single `Decision` enum so every branch is easy to see. Production may use exceptions or richer result types; what is mandatory is **never equating a dependency failure with granted access**.

## 6. Applying to Spring Security's Request Lifecycle

In a Servlet application, controls can be organized as follows:

```text
HTTP request
    |
    v
SecurityFilterChain
    |-- CSRF / request protections (when applicable)
    |-- Authentication filter: credentials/token/session
    |-- AuthorizationFilter: URL + HTTP method policy
    v
Controller / Bean Validation
    |
    v
Application Service
    |-- Load resource by trusted tenant
    |-- Object permissions + business conditions
    |-- Verify dependent services (if policy requires)
    v
Transaction / Side effect -> Response
```

The diagram shows **responsibilities** only. Actual filter order depends on the security chain and version/config; some input errors can happen before the controller and be handled by Spring MVC.

### 6.1. Do Not Turn Errors into Privileges in Security Filters

- When a JWT is invalid or expired, never manually fabricate an authenticated `Authentication`.
- When `SecurityContext` is missing, never "temporarily treat it as ADMIN" to let the request continue.
- When a policy rule is indeterminate, use deny/fail-safe instead of falling back to `permitAll()`.
- When a CSRF token is missing/wrong in a CSRF-required context, never skip the check just because the endpoint requires `authenticated()`.
- For a resource server, accept tokens only from trusted issuers/audiences and verify signatures. Never Base64-decode claims and treat them as an authenticated identity.

### 6.2. Exception Handling: Right Layer, Zero Leakage

Spring Security typically uses `AuthenticationEntryPoint` to initiate authentication challenges and `AccessDeniedHandler` for access denials. Applications may also use `@RestControllerAdvice` to render validation or business-service errors per API contract.

| Error Group | Usually Handled At | Target Response Style |
| --- | --- | --- |
| Unauthenticated / invalid token | Security authentication handlers | 401/challenge or redirect, never fake authentication |
| Principal exists, lacks permission | Security access-denied handling, method security | 403 or resource-existence-hiding policy |
| DTO invalid format/constraint | Spring MVC validation/exception handling | 400, expose only necessary field info |
| Policy service timeout | Service boundary + exception handler | 503 or appropriate 5xx, do not execute business logic |
| Unexpected internal bug | Global error handling | 500, log for investigation, never return stack traces/secrets to client |

Note: authorization errors can happen inside the filter chain or method security; never assume a `@ControllerAdvice` automatically handles every exception before security filters act. Verify real behavior with integration tests.

### 6.3. Avoid Confusing "Degraded Service Quality" with "Lowered Security Policy"

A sound degradation policy must explicitly specify **which features remain safe when a dependency fails**:

- Permitted: temporarily hiding product recommendations if the recommendation engine is offline.
- Potentially permitted: displaying cached public data, provided the cache has a trusted origin and safe scope.
- Forbidden: continuing to issue refunds when the authorization service stops responding.
- Forbidden: returning another tenant's data because the tenant filter timed out.
- Forbidden: skipping token verification due to an IdP or JWKS endpoint outage.

If a fallback path is ever needed for a sensitive operation, it must be **a pre-approved design with equivalent or stricter authentication/authorization, time bounds, and auditing**; never improvise a bypass inside a catch block.

## 7. Data and Transactions Must Stay Consistent on Failure

Executing side effects without permission is a severe flaw. Even with valid permissions, failing midway between steps can still leave inconsistent state.

Refund example:

```text
1. Validate amount and order state.
2. Authenticate principal, verify tenant, role/permission, and permission on the order.
3. Check limits, idempotency, and financial conditions.
4. Send refund command to payment provider.
5. Record transaction result and audit.
```

If step 4 times out, you cannot conclude "refund did not happen" because the provider may have received and processed the request. Store a request ID/idempotency key, query status, and reconcile safely. Blindly retrying without an idempotency key can refund the customer twice.

Practical rules:

- **Verify preconditions before side effects**; never call the provider first and check authorization afterward.
- **DB transactions** roll back DB changes, not outbound network calls already sent.
- **Idempotency** is critical when retrying transaction creation, permission changes, or side-effecting notifications.
- **Never treat a timeout as certain success or failure** if the partner may have processed it; use PENDING/UNKNOWN state when needed and reconcile.
- **Data can change between check and write**; for contested order states or permissions, apply transactions, version checks, conditional updates, or appropriate synchronization.
- **Constrain async worker permissions**: jobs or consumers do not automatically inherit the original request's privileges. Define explicit identity, tenant scope, and execution permissions.

## 8. Observability and Recovery Without Leaking Data

When failing closed, the system must still help operations distinguish "legitimately denied" from "unable to verify due to infrastructure failure."

### 8.1. Logging and Metrics

Log in a controlled manner:

- Action type, resource type, timestamp, and correlation/request ID;
- Outcome category: `DENY`, `UNAVAILABLE`, `INVALID_REQUEST`;
- Technical reason as a stable code, e.g., `AUTHZ_DEPENDENCY_TIMEOUT`, `CONFIG_MISSING`, `VALIDATION_ERROR`;
- Latency, dependency group name, and circuit breaker state;
- Sanitized/access-controlled subject or tenant identifiers, per privacy requirements.

**Never log** passwords, access tokens, refresh tokens, secrets, full `Authorization` headers, sensitive request values, or expose stack traces in public responses. Restrict log read access because logs themselves are assets needing protection. Avoid putting user/tenant IDs into metric labels where cardinality explodes.

### 8.2. Health and Readiness

- **Liveness** indicates whether the process is alive.
- **Readiness** indicates whether the instance is ready to accept traffic.
- If mandatory security config is missing, the instance must not be marked ready simply because the HTTP server started.
- If a dependency affects only one feature, you can fail that feature instead of taking down the whole system. The choice depends on app scope and operational requirements.

Never expose detailed config state, stack traces, secrets, or internal versions through health endpoints.

### 8.3. Conditional Recovery

When an external service recovers, evaluate new requests against the currently active policy. If old decisions were cached or queued tasks are waiting, never assume all requests remain permitted. For delayed sensitive tasks, re-verify grant validity or permissions at execution time per business policy.

## 9. Failure-Testing Checklist by Root Cause

| Test Scenario | Outcome to Verify | What Must Never Happen |
| --- | --- | --- |
| Missing mandatory security property | Clear startup failure or sensitive endpoints unavailable | Endpoints silently becoming public |
| Blank/invalid config value | Rejected by validation rules | Defaulting to ADMIN role or allowing empty authority |
| Expired JWT or invalid signature | No authenticated identity established | Skipping verification or trusting unverified claims |
| Policy service timeout | Action not executed; service error observed | Timeout interpreted as ALLOW |
| Policy service returns DENY | Request blocked | Retrying to "hunt for an ALLOW" |
| Logged-in user lacking role | Denied by authorization | Request reaching sensitive operation |
| Wrong JSON types or missing required fields | Returns 400/4xx, business logic not called | Invalid values swapped for higher privileges |
| Tampered tenant in request | Out-of-scope access denied | Trusting client-declared tenant |
| DB returns no owner result | Access denied on missing data | Treating null owner as public |
| Payment provider times out after sending command | Record uncertain state and reconcile | Unbounded retries or double refunds |
| Non-sensitive feature offline | Remaining safe features work properly | Auxiliary failure disabling security controls |
| Invalid CSRF token on protected request | Request blocked | Disabling CSRF just to make requests succeed |

Run tests with unauthorized accounts, authorized accounts, wrong tenants, missing fields, simulated 500s from dependencies, timeouts, and malformed schemas. Especially **verify zero side effects**: assert not only the status code, but also that no data was modified, no events/transactions were emitted, and no permissions were granted.

In Spring Boot, use MockMvc for request-level cases, integration tests with mocked dependencies to simulate timeouts, and service/DB tests to prove zero side effects. A test showing "returned 403" is insufficient if the transaction actually committed.

## 10. Mistakes to Avoid

1. **Catching all exceptions and allowing:** `catch (Exception e) { return true; }` turns infrastructure errors into privilege bypass.
2. **Dropping policy when config is blank:** one bad deployment becomes a system-wide hole.
3. **Lumping all errors into "unauthorized":** hides operational incidents behind user denials and triggers bad retries.
4. **Reading role and tenant from headers/body/query:** client-claimed values are unverified.
5. **Unbounded ALLOW caching:** permissions may have been revoked; enforce TTLs, scoping, and policy updates.
6. **Disabling CSRF because POST returned 403:** analyze auth mechanism, tokens, and threat model before changing anything.
7. **Retrying transactions with unknown outcomes:** causes duplicate side effects, especially in payments/refunds.
8. **Returning raw stack traces to clients:** can leak internal paths, configs, user info, and secrets.
9. **Asserting only status codes:** prove data stays unchanged when requests are unauthorized or dependencies fail.
10. **Assuming every error must halt the whole app:** pick the right blast radius; keep independent, safe functionality running when possible.

## 11. Self-Check Questions

**1.** An environment variable holding the admin authority is missing. If code falls back to `permitAll()` for `/api/admin/**`, what is the consequence?

**2.** The authorization service times out while processing a refund request. Should the system return DENY or UNAVAILABLE, and may the refund proceed?

**3.** When the IdP is offline, must a resource server skip JWT verification to preserve availability?

**4.** A refund DTO has a valid amount. Why must we still check principal, tenant, permission on the order, and business state?

**5.** Why does HTTP 503 not mean "fail open"?

**6.** A refund command sent to the payment provider timed out. Why shouldn't you immediately call it again without an idempotency key or reconciliation?

**7.** Why can a cached ALLOW value become unsafe even though it was computed accurately at first?

**Suggested Answers:**

1. Admin endpoints become public upon misconfiguration; you must fail fast or deny the affected feature properly.
2. It is UNAVAILABLE when no decision was obtained; never let sensitive actions proceed.
3. No. Verify locally using still-trusted keys and valid cache policies; without sufficient verification proof, reject the token.
4. Validation only checks input data; authorization and domain invariants are independent requirements.
5. Fail closed means not executing the action when safety grounds are insufficient; 503 expresses that a dependency is unavailable.
6. The partner may have already refunded; uncontrolled retries risk duplicate refunds.
7. Permissions may be revoked, tenants changed, policies updated, or TTL expired; bound lifetimes and support refresh/revocation.

### References

- [Spring Security Reference – Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Security Reference – Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
