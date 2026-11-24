# Timeouts, Network Errors, Invalid Responses, and Fail-Closed Policies in Spring Security

## 1. Context: dynamic policies and when the PDP fails

A Spring Security application can use `hasAuthority("DOC_READ")` for basic permission checks. Yet for dynamic rules like "Alice may read Document 42 when in the same tenant, holding an active share, the document is unlocked, and at the right security level", the decision may require a remote **Policy Decision Point (PDP)**. The component blocking the operation and calling the PDP is the **Policy Enforcement Point (PEP)**.

Normally the PDP may return:

```json
{
  "requestId": "req-42",
  "subject": "alice",
  "tenant": "alpha",
  "resource": "document:42",
  "action": "READ",
  "effect": "PERMIT",
  "policyVersion": 81
}
```

If the PDP times out, drops the connection, returns HTTP 200 with malformed JSON, or returns PERMIT **for tenant beta**, what must the right behavior be?

**Safety principle:** only a **valid, authenticated PERMIT matching subject–tenant–resource–action, still within validity, and at the right policy version** may pass. Without receiving such a PERMIT, the protected action **must not execute**. This is **fail closed**.

However, distinguish carefully:

- **Policy DENY:** the PDP evaluated and returned a valid DENY. The caller lacks permission; typically HTTP 403 for authenticated callers.
- **Unable to evaluate policy:** timeout, DNS/TLS/network error, circuit breaker OPEN. Access must be blocked, yet it is an availability issue; may return 503/502 per API contract.
- **Invalid response:** response has wrong structure, version, or binding; access must be blocked and adapter/PDP error alerted.
- **Authentication failure:** caller has not proven identity, typically 401, occurring before querying the PDP.

"Fail closed" **does not mean every failure must return 403**. The invariant is **zero side effects, and never reading or returning protected data without a valid permit decision**.

## 2. Architecture: PEP, PDP, PIP, and checkpoints

```text
HTTP / Method invocation
    |
    v
Spring Security Authentication
    |   subject, issuer, authorities
    v
Local guards
    |   authenticated? tenant? action? resource?
    v
PEP (AuthorizationManager / method guard)
    |
    v
Policy request builder
    |   canonical principal + tenant + resource + action
    v
PDP client (strict timeouts, TLS, bounded retry)
    |
    v
PDP policy engine
    |   policy version, attributes from PIP
    v
Response validator
    |   authenticated source
    |   exact request binding
    |   valid effect, expiry, policy revision, obligations
    v
Typed outcome
    |-- PERMIT_VALID --------> continue with guarded business action
    |-- DENY_POLICY ---------> deny
    |-- UNAVAILABLE_* -------> block action, record operational fault
    |-- INVALID_RESPONSE ----> block action, alert
```

| Component | Responsibility |
| --- | --- |
| **Authentication** | Verify caller; never trust raw JWTs/headers |
| **PEP** | Block access right before the action |
| **PDP** | Evaluate policy and return PERMIT/DENY |
| **PIP** | Supply attributes such as membership, owner, classification, resource state |
| **PAP** | Administer policies/revisions/rollouts |
| **Adapter/validator** | Ensure the response truly corresponds to the exact query sent |
| **Failure policy** | Define timeouts/retries/denial/error mapping |
| **Audit** | Log decision ID, latency, version, and reason codes under log-protection rules |

Spring Security uses `AuthorizationManager<T>` across many checkpoints, including request and method authorization. `authorize(Supplier<Authentication>, T)` returns `AuthorizationResult`; `AuthorizationDecision(true/false)` is a simple representation. Returning `null` in some APIs means **abstain/no decision**, not "definite denial".

**Never return `null` when the PDP breaks** if this guard must make the final decision. Return an explicit DENY or throw a typed failure handled safely by your integration.

## 3. Classifying decisions before converting to boolean

A plain `boolean allowed` is insufficient for operating dynamic policies because it loses the cause. Use an explicit domain result:

| Outcome | Meaning | Proceed with business logic? |
| --- | --- | --- |
| `PERMIT_VALID` | A PERMIT with valid source, binding, expiry, version, and obligations | Yes, if other guards also pass |
| `DENY_POLICY` | PDP returned a valid DENY | No |
| `UNAVAILABLE_TIMEOUT` | Timed out waiting | No |
| `UNAVAILABLE_NETWORK` | DNS, connection reset/refused, TLS error | No |
| `UNAVAILABLE_CIRCUIT_OPEN` | Circuit breaker is blocking PDP calls | No |
| `INVALID_RESPONSE` | Empty/malformed JSON, wrong type, unrecognized effect | No |
| `INVALID_BINDING` | Wrong subject, tenant, action, resource, or requestId | No |
| `STALE_DECISION` | Expired, old policy/entitlement version | No |
| `UNTRUSTED_RESPONSE` | Unable to verify source/TLS/signature | No |
| `UNAUTHENTICATED` | Caller not authenticated | No |

Three key points:

1. A network error means **no decision**, not that the policy decided DENY.
2. Without a decision, **never default to ALLOW**.
3. Preserve typed outcomes for telemetry and HTTP mapping; at the PEP, only `PERMIT_VALID` permits the action.

You may record a dedicated internal `DecisionReason`; avoid logging full personal data or policy attributes.

## 4. Fail open is a vulnerability, fail closed is the baseline

Counterexample:

```java
boolean canRead(User user, long documentId) {
    try {
        return policyClient.canRead(user, documentId);
    } catch (Exception ex) {
        return true; // WRONG: PDP outage = grant access to everything.
    }
}
```

If an attacker induces timeouts via heavy load, the error path becomes an authorization bypass. A TLS error could likewise open access.

Fail-closed approach:

```java
boolean canRead(User user, long documentId) {
    try {
        return policyClient.canRead(user, documentId);
    } catch (PdpUnavailableException ex) {
        return false; // Do not execute the protected operation.
    }
}
```

This is an **integration snippet** (`User`/`policyClient`/`PdpUnavailableException` are application-defined types). Returning false is safe for enforcement, though it tends to produce HTTP 403 even during PDP outages. For systems needing 503, use typed exceptions/outcomes and map them at **the exact security filter/service boundary**, while still blocking the business action.

### Do not turn availability into a "permitAll" exception

A public health endpoint may be configured `permitAll()` because **policy defines it as public**. That has nothing to do with a broken PDP. For private resources, never temporarily open `permitAll()` across routes to reduce 403s.

If the architecture includes a signed local policy bundle or independently verified short-lived capabilities, those can serve as a valid PERMIT source when the remote PDP is unavailable **only if** TTL, scope, issuer, audience, revocation SLA, and policy version were designed upfront. "Indefinite last-known PERMIT" is not a safe fallback.

## 5. Timeouts: define end-to-end deadlines

A remote policy check incurs multiple wait phases:

- Acquiring a slot from the HTTP connection pool.
- DNS lookup and TCP connect.
- TLS handshake.
- Sending request body.
- Waiting for response headers/first byte.
- Reading the full body.
- Parsing JSON, validating bindings, expiry/version.
- Enforcing mandatory obligations.

Setting only a connect timeout is insufficient if the server accepts TCP yet hangs without responding. Setting only a per-attempt timeout is also insufficient if a request retries repeatedly.

An **illustrative budget** example, not a universal recommended config for every system:

```text
API request deadline:       1000 ms
Other application work:      350 ms
Reserve:                     150 ms
PDP overall budget:          500 ms
  connect timeout:           120 ms
  response timeout:          280 ms
  retry/backoff reserve:     remaining budget
```

Invariant:

```text
attempt time + backoff + retry + validation
    <= remaining PDP deadline
PDP deadline <= remaining caller/request deadline
```

If the deadline expires, **do not wait indefinitely and do not proceed with the protected operation**. Once a call is canceled, a late-arriving PERMIT response must never resume the canceled action.

### Rules on interruption

Java blocking clients can throw `InterruptedException`. Never swallow interrupts and retry forever:

```java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new PolicyCheckInterruptedException(ex);
}
```

This is an integration snippet; `PolicyCheckInterruptedException` is app-defined. Code requires importing `HttpResponse` and properly constructed `client` and `request`.

## 6. HTTP/network/TLS errors are not valid policy DENYs

Common failures: DNS failure, connection refused, connection reset, read timeout, untrusted TLS certificate, hostname mismatch, reverse proxy returning HTML 502, PDP 503, wrong service credentials causing PDP 401.

| Status | Appropriate classification | Handling |
| --- | --- | --- |
| HTTPS 200 + valid body | May evaluate decision | Validate everything before PERMIT/DENY |
| 200 with empty body | INVALID_RESPONSE | Deny |
| 200 with schema-invalid JSON | INVALID_RESPONSE | Deny |
| 204 | No decision | Deny |
| Unexpected 3xx redirect | Transport/protocol error | Never auto-follow to untrusted hosts |
| 401/403 from PDP gateway | Service credential/config error | Never treat as policy DENY unless defined by protocol |
| 408, 429, 502, 503, 504 | Unavailable/transient per contract | Deny; conditional retry |
| Other 5xx | Unavailable/internal PDP error | Deny |
| DNS/TCP/TLS/timeout | Transport failure | Deny, emit metrics |

**Never equate HTTP 403 from the PDP endpoint with JSON `effect=DENY`.** A 403 might mean the calling service account itself is blocked by the PDP; a decision protocol must define what a valid PDP response looks like.

**Never disable TLS certificate validation** to "fix PDP errors" because an intermediary could then inject forged `PERMIT` responses.

## 7. Verifying response provenance and request binding

Illustrative response:

```json
{
  "requestId": "r-123",
  "decisionId": "d-77",
  "effect": "PERMIT",
  "subject": "issuerA:alice",
  "tenant": "alpha",
  "resource": "document:42",
  "action": "READ",
  "policyVersion": 81,
  "issuedAt": "2026-11-05T03:00:00Z",
  "expiresAt": "2026-11-05T03:00:02Z"
}
```

This is an **example contract**, not a mandatory schema for every policy engine. Each PDP adapter must map appropriately.

### Validation checklist before PERMIT

1. Response channel is authenticated (TLS/mTLS with server trust and hostname verification, or appropriate signature).
2. HTTP status, content-type, and body size match the contract.
3. JSON parses into exactly one object without truncation.
4. Required fields are present with exact types, without silent coercion.
5. `effect` accepts strictly `PERMIT`/`DENY` per protocol.
6. `requestId`/nonce matches this query, preventing response mix-ups/replays.
7. `subject` matches the verified identity, including issuer if `sub` is not globally unique.
8. `tenant` matches the authorized tenant, not raw client headers/paths.
9. `resource` matches the server's canonical type/id of the object.
10. `action` matches the exact operation to execute (READ does not imply DELETE).
11. `policyVersion` meets or exceeds the caller's required floor.
12. `issuedAt`/`expiresAt` are valid given clock skew/TTL policy.
13. Attribute/entitlement versions match if included in the policy request.
14. All **mandatory obligations** are understood and enforceable.

A `PERMIT` response for tenant beta when the caller is in alpha is **INVALID_BINDING**, not allow. Likewise, a response for another resource or action must be rejected.

### Never use "truthy" strings or default allow

```java
// WRONG: any effect other than DENY grants access.
boolean allow = !"DENY".equals(effect);

// WRONG: non-null body is not proof of authorization.
boolean allow = httpResponse.body() != null;

// RIGHT DIRECTION: only PERMIT from a validated decision.
boolean allow = validated.effect() == Effect.PERMIT;
```

These are snippets; `Effect`/`validated` must be typed decisions produced after validation completes.

### JSON ambiguity

The following response must not be treated as a clear decision:

```json
{"effect":"DENY","effect":"PERMIT"}
```

If a parser accepts duplicate keys and keeps the last one, attackers or server bugs can alter semantics. For policy-critical JSON, reject duplicate keys or enforce strict schema contracts. Likewise, never coerce `"true"`, `1`, or `"yes"` into PERMIT when the protocol defines an enum string.

## 8. Policy DENY and endpoint verification errors must stay separate

Example where Alice is genuinely not allowed:

```text
PDP authenticated
  -> parse response
  -> match subject/tenant/resource/action
  -> effect DENY
  -> DENY_POLICY
```

This is a normal decision: do not retry hoping to "get a PERMIT", and do not mark the PDP unhealthy.

Conversely:

```text
PDP timeout          -> UNAVAILABLE_TIMEOUT
PDP connection reset -> UNAVAILABLE_NETWORK
JSON missing effect  -> INVALID_RESPONSE
Version 79 < min 81  -> STALE_DECISION
TLS hostname invalid -> UNTRUSTED_RESPONSE
```

All error outcomes **block the action**, yet need distinct statuses/metrics for operations.

### Suggested HTTP mapping

| Situation | Suggested HTTP API |
| --- | --- |
| Unauthenticated | 401 |
| Valid DENY_POLICY | 403 or 404 per API privacy contract |
| Timeout/circuit open | 503, sometimes 502/504 per gateway design |
| Invalid PDP response | 502/503 or neutral internal error |
| Invalid request input | 400 |
| Definite local policy DENY | 403 |

In Spring Security, if a manager returns `new AuthorizationDecision(false)`, `AuthorizationFilter` and exception translation typically yield 403 for authenticated callers. If a PDP outage needs HTTP 503, **do not just add `@RestControllerAdvice` assuming all security filter exceptions will be caught**. Handle it at the appropriate filter/authorization boundary or in a service boundary managed by the controller handler, and test with `MockMvc`.

## 9. Bounded retries, never retry everything

Retries can help with transient network failures, yet a 1,000 req/s system doing 3 extra retries can drive the PDP from 1,000 to 4,000 calls/s and worsen an outage.

Rules:

- Retry only classified transient cases: connection resets, 503/429 per contract, select timeouts.
- Never retry `DENY_POLICY`.
- Never retry response mismatches/untrusted TLS/malformed schemas hoping the next try grants access.
- Retry only **idempotent policy evaluations**; never auto-retry business mutations (transfers, approvals) on policy call timeouts.
- Bound attempts (e.g., max 2 total calls) and overall deadline.
- Add jittered backoff to avoid synchronized bursts.
- Respect `Retry-After` if supported by the provider, without exceeding the deadline.
- Never alter subject/action/resource between retries.
- Once a request is canceled, stop retrying and never execute the business action.

A retry may observe a newer policy than the first attempt due to membership changes; this is why you must validate policy revisions and handle state changes per consistency contract rather than reading `effect` alone.

## 10. Circuit breakers and bulkheads

Circuit breakers protect resources when the PDP fails repeatedly:

```text
CLOSED -> call PDP, measure errors/latency
   |
   v
OPEN -> skip calling PDP, return UNAVAILABLE_CIRCUIT_OPEN
   |
   v
HALF_OPEN -> allow limited probes
   | healthy              | still failing
   v                      v
CLOSED                   OPEN
```

**Circuit OPEN is NOT PERMIT.** If code has a fallback "when circuit is open, skip the PDP", that is a bypass.

Resilience4j provides `CircuitBreaker`, `Retry`, `TimeLimiter`, and `Bulkhead`. Per documentation, `CircuitBreaker` does not itself limit concurrent calls; add `Bulkhead` when concurrency isolation is needed.

Configuration points:

- Per-cluster/endpoint breakers suffice to isolate faults; do not create a breaker per arbitrary client key.
- Base thresholds on failure rate and slow calls; never count `DENY_POLICY` as a transport failure.
- OPEN returns a failure type, never an expired `cached PERMIT`.
- HALF_OPEN probes must also pass the validator; a schema-invalid PERMIT from a probe is still a failure.
- Rejections from full bulkheads/pools are unavailable, never converted to allow.
- Emit alerts/metrics on breaker state and blocked request counts.

## 11. Decision caching: keys, TTL, and revocation

A cached authorization decision must bind to:

```text
issuer + canonical subject
tenant
resource type + canonical resource ID
action
affecting attributes / resource version
policy version + entitlement version
authentication assurance if used by policy
decision issuedAt / expiresAt
```

**Caching by `resourceId` alone is wrong:** Alice having access to document 42 does not mean Bob does. Caching by tenant alone is also insufficient when users have distinct ownership/shares.

### Can cached PERMITs be used when the PDP is unavailable?

Only when it is **an unexpired, contract-valid PERMIT** with bounded TTL, policy version, revocation SLA, full-scope key, and trusted provenance. Once expiry passes or membership is revoked, never extend validity merely to preserve availability.

Distinguish:

- Caching valid `DENY_POLICY` may be acceptable briefly per policy.
- Caching `UNAVAILABLE_TIMEOUT` as a permanent DENY breaks semantics/monitoring.
- Caching `INVALID_RESPONSE` as allow is critical.
- Permission changes require invalidation or version bumps; for immediate revocation, you may need to disable positive decision caching.

### Local policy bundles

A local policy engine with signed/versioned bundles can support offline evaluation. Still, if a bundle is older than the minimum required revision or unaware of newly revoked memberships, a local PERMIT can violate policy. Enforce version floors and update mechanisms rather than assuming "a bundle file exists so it's usable".

## 12. Runnable Java 17: simulating all critical failure branches

This example **needs no Spring, Maven, or Internet**. It models a PDP transport adapter covering timeouts, `IOException`, empty replies, wrong effects, wrong tenant/resource/requestId, stale versions, expiry, and untrusted sources. A boolean `sourceVerified` simulates **the client-side TLS/signature verifier outcome**, not a self-declared client/PDP JSON field.

File `PdpFailureLab.java`:

```java
import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.TimeoutException;

public final class PdpFailureLab {

    record Query(
            String requestId,
            String subject,
            String tenant,
            String resource,
            String action,
            long minPolicyVersion) {}

    record Reply(
            String requestId,
            String subject,
            String tenant,
            String resource,
            String action,
            String effect,
            long policyVersion,
            long expiresAtMillis,
            boolean sourceVerified) {}

    enum Scenario {
        ALLOW,
        POLICY_DENY,
        TIMEOUT,
        NETWORK_ERROR,
        EMPTY_REPLY,
        UNKNOWN_EFFECT,
        WRONG_TENANT,
        WRONG_RESOURCE,
        WRONG_REQUEST_ID,
        STALE_POLICY,
        EXPIRED,
        UNTRUSTED_SOURCE
    }

    enum Outcome {
        PERMIT,
        DENY_POLICY,
        DENY_TIMEOUT,
        DENY_NETWORK,
        DENY_INVALID
    }

    private PdpFailureLab() {}

    private static Reply valid(Query q, String effect) {
        return new Reply(
                q.requestId(), q.subject(), q.tenant(),
                q.resource(), q.action(), effect,
                7L, 2_000L, true);
    }

    private static Reply remote(Query q, Scenario scenario)
            throws IOException, TimeoutException {
        return switch (scenario) {
            case ALLOW -> valid(q, "PERMIT");
            case POLICY_DENY -> valid(q, "DENY");
            case TIMEOUT -> throw new TimeoutException("Simulated timeout");
            case NETWORK_ERROR -> throw new IOException("Simulated network error");
            case EMPTY_REPLY -> null;
            case UNKNOWN_EFFECT -> valid(q, "MAYBE");
            case WRONG_TENANT -> new Reply(
                    q.requestId(), q.subject(), "beta",
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, true);
            case WRONG_RESOURCE -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    "document:999", q.action(), "PERMIT",
                    7L, 2_000L, true);
            case WRONG_REQUEST_ID -> new Reply(
                    "other-request", q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, true);
            case STALE_POLICY -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    6L, 2_000L, true);
            case EXPIRED -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 900L, true);
            case UNTRUSTED_SOURCE -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, false);
        };
    }

    private static Outcome decide(
            Query q, Scenario scenario, long nowMillis) {
        try {
            Reply r = remote(q, scenario);

            if (r == null || !r.sourceVerified()
                    || !Objects.equals(r.requestId(), q.requestId())
                    || !Objects.equals(r.subject(), q.subject())
                    || !Objects.equals(r.tenant(), q.tenant())
                    || !Objects.equals(r.resource(), q.resource())
                    || !Objects.equals(r.action(), q.action())
                    || r.policyVersion() < q.minPolicyVersion()
                    || r.expiresAtMillis() <= nowMillis) {
                return Outcome.DENY_INVALID;
            }

            return switch (r.effect()) {
                case "PERMIT" -> Outcome.PERMIT;
                case "DENY" -> Outcome.DENY_POLICY;
                default -> Outcome.DENY_INVALID;
            };
        } catch (TimeoutException ex) {
            return Outcome.DENY_TIMEOUT;
        } catch (IOException ex) {
            return Outcome.DENY_NETWORK;
        }
    }

    public static void main(String[] args) {
        Query query = new Query(
                "req-001", "alice", "alpha",
                "document:42", "READ", 7L);

        for (Scenario scenario : Scenario.values()) {
            System.out.println(
                    scenario + "=" + decide(query, scenario, 1_000L));
        }
    }
}
```

Run commands with JDK 17+:

```bash
javac PdpFailureLab.java
java PdpFailureLab
```

Exact stdout according to program logic:

```text
ALLOW=PERMIT
POLICY_DENY=DENY_POLICY
TIMEOUT=DENY_TIMEOUT
NETWORK_ERROR=DENY_NETWORK
EMPTY_REPLY=DENY_INVALID
UNKNOWN_EFFECT=DENY_INVALID
WRONG_TENANT=DENY_INVALID
WRONG_RESOURCE=DENY_INVALID
WRONG_REQUEST_ID=DENY_INVALID
STALE_POLICY=DENY_INVALID
EXPIRED=DENY_INVALID
UNTRUSTED_SOURCE=DENY_INVALID
```

**Explanation:**

- `ALLOW` has PERMIT, valid bindings, version 7, and expiry=2000 > now=1000.
- `POLICY_DENY` is a valid policy refusal, not a network failure.
- `TIMEOUT`/`NETWORK_ERROR` are blocked while classified distinctly.
- `EMPTY_REPLY` models the adapter failing to obtain a decision object.
- `UNKNOWN_EFFECT` is rejected because "MAYBE" is not a valid value.
- `WRONG_TENANT/RESOURCE/REQUEST_ID` prevent granting from a response meant for another request.
- `STALE_POLICY` returns version 6, below required version 7.
- `EXPIRED` returns expiry=900, already expired at now=1000.
- `UNTRUSTED_SOURCE` simulates failed TLS/signature/source verification.

**Limitations:** the demo does not parse real JSON, open sockets, verify TLS signatures, or include Spring Security. It intentionally isolates the state machine/validation rules to highlight invariants; production needs real JSON/TLS/clock/attribute/obligation adapters. Never hardcode time or versions as in the demo when deploying.

## 13. Spring Security AuthorizationManager: wiring strict policy gates to HTTP

Spring Security 6.4+ provides `AuthorizationManager<T>.authorize` returning `AuthorizationResult`, and `AuthorizationDecision` can be used. Below illustrates a mandatory decision-making manager on an endpoint:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

final class RemoteDocumentAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final DocumentPolicyGate policyGate;

    RemoteDocumentAuthorizationManager(DocumentPolicyGate policyGate) {
        this.policyGate = policyGate;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        if (current == null || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        String requestedTenant = context.getVariables().get("tenant");
        String id = context.getVariables().get("id");

        if (requestedTenant == null || id == null) {
            return new AuthorizationDecision(false);
        }

        // Policy gate verifies membership, canonical resource tenant,
        // local authority, PERMIT response, binding, and expiry.
        PolicyOutcome result =
                policyGate.checkRead(current, requestedTenant, id);

        // Every error and every DENY produces a negative decision.
        return new AuthorizationDecision(
                result == PolicyOutcome.PERMIT_VALID);
    }
}
```

`DocumentPolicyGate` and `PolicyOutcome` are project domain abstractions, **not built-in Spring classes**. The gate must return `PERMIT_VALID` **only** after verifying all conditions, and must turn timeouts/invalid replies into non-permits (or typed operational errors handled at the security boundary).

Wiring into the filter chain:

```java
@Bean
SecurityFilterChain apiFilter(
        HttpSecurity http,
        RemoteDocumentAuthorizationManager remoteManager)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET,
                "/api/tenants/{tenant}/documents/{id}"
            ).access(remoteManager)
            .anyRequest().denyAll());

    return http.build();
}
```

Requires `@Bean`, `HttpSecurity`, `HttpMethod`, and `SecurityFilterChain` imports; this is an **integration snippet** requiring authentication setup, Spring context, policy gate, and controller. `RequestAuthorizationContext.getVariables()` holds path variables when extracted by the matching `RequestMatcher`; path variables remain **unauthorized inputs**. Verify tenant membership and actual resource tenant membership rather than copying `{tenant}` straight into the PDP request.

### If 403 and 503 need to be distinguished

The adapter above returns `AuthorizationDecision(false)` for every non-permit, so Spring Security routes it through `AccessDenied`, normally HTTP 403 for authenticated callers. If PDP unavailability requires HTTP 503, design exception mapping at the appropriate filter/authorization boundary or an application policy gate running before mutations under a controlled handler, and test actual responses. Never let 503 mapping accidentally bypass authorization guards.

**Never use `return null` on timeout.** For a mandatory manager, that is not an explicit DENY, and composition semantics can surprise you.

## 14. Combining local guards and dynamic PDP properly

Suppose reading is permitted if the caller is authenticated **and** belongs to the tenant **and** holds the base role **and** the PDP PERMITs:

```text
allowed =
  authenticated
  AND tenantMembershipValid
  AND resourceTenantMatches
  AND hasLocalAuthority
  AND validRemotePermit
  AND mandatoryObligationsSatisfied
```

Counterexample:

```java
boolean allowed = hasAuthority || pdpAllowed; // WRONG if policy requires both.
```

Correct condition:

```java
boolean allowed = authenticated
        && tenantMembershipValid
        && resourceTenantMatches
        && hasAuthority
        && remotePermitValid
        && obligationsSatisfied;
```

Variables represent verified policy outcomes, never values from the client request body. Definite local denials can short-circuit before calling the remote PDP to lower latency and limit sensitive attributes sent externally. However, passing local checks never suffices if the dynamic PDP is mandatory.

### Avoiding time-of-check/time-of-use

A remote PDP PERMIT at T1 does not prove the document still belongs to that tenant at T2. For sensitive mutations, use conditional SQL/transaction/version checks:

```sql
UPDATE documents
SET status = 'APPROVED'
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND owner_id = :authenticated_subject
  AND status = 'PENDING'
  AND version = :expected_version;
```

Check that affected rows equal 1. If the resource changed state between authorization and update, never use the old PERMIT to bypass the race. Depending on business rules, re-evaluate against a fresh snapshot.

## 15. Response obligations: PERMIT received yet cannot execute yet

The PDP may return PERMIT with requirements:

```json
{
  "effect": "PERMIT",
  "obligations": [
    {"type": "MASK_FIELD", "field": "salary"},
    {"type": "AUDIT", "level": "SENSITIVE"}
  ]
}
```

If the application does not support `MASK_FIELD` and still sends raw salaries, the PERMIT was misinterpreted. The policy gate must check that every mandatory obligation is enforceable; if not, **deny/invalid**. Obligations may include mandatory MFA, auditing, watermarking, redaction, rate-limiting, or resource conditions.

Never read an empty `obligations` list when a parser ignores unknown fields and assume all conditions passed. Obligation schemas/versions require testing just like `effect`.

### Data minimization

Do not send raw access tokens, passwords, private document bodies, or unnecessary PII to the PDP. Send minimal canonical subject/tenant/resource attributes over a protected transport. Audit/logs should use decision IDs and reason codes rather than logging entire sensitive payloads.

## 16. Java 17 HttpClient: transport is one layer, policy validator is another

JDK 17 transport example (**integration snippet**, requiring `jsonBody` serialized from a trusted request):

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(150))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://pdp.internal.example/check"))
        .timeout(Duration.ofMillis(300))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Corresponding imports: `java.net.URI`, `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`.

Warnings:

- PDP URI comes from an allowlisted config, **never from client headers/URLs** to prevent SSRF.
- Never auto-follow redirects to unknown endpoints.
- Never disable TLS/hostname verification.
- `response.statusCode() == 200` is only the first transport check; strict JSON parsing and binding checks are still required.
- `send` can throw `IOException`/`InterruptedException`; classify, preserve interrupts, and fail closed.
- Do not treat connect timeout=150ms and request timeout=300ms as universal constants; size to your SLO.

With Spring `RestClient`/`WebClient`, configure connect/response timeouts on the underlying HTTP client and test empirically. In reactive stacks, watch the overall budget/deadline and avoid blocking calls on the event loop.

## 17. Batch policy decisions and missing response items

A PDP may return multiple decisions:

```json
{
  "requestId": "batch-01",
  "results": [
    {"resource":"document:41","effect":"PERMIT"},
    {"resource":"document:42","effect":"DENY"}
  ]
}
```

If a request asks for 3 resources and the response contains only 2, **missing items must not default to PERMIT**. Verify:

- Every resource/action in the response belongs to the request; no extras.
- No duplicate resource IDs with conflicting outcomes.
- No positional matching based on array order if the provider does not guarantee order.
- Every item binds correctly to subject, tenant, expiry, and policy version.
- All-or-nothing operations require every requested item to PERMIT before mutating; partial success requires an explicit contract reporting per-item outcomes.
- Cross-tenant items must be authorized individually rather than under one shared tenant ID.

Example adapter all-of policy **after map validation**:

```java
boolean allPermitted = !requestedIds.isEmpty()
        && requestedIds.stream().allMatch(id ->
                validatedById.containsKey(id)
                && validatedById.get(id) == Effect.PERMIT);
```

`validatedById` must be a map already checked for schema, duplicates, and bindings—never raw JSON. `!requestedIds.isEmpty()` prevents `Stream.allMatch` from returning true on an empty stream if business rules forbid empty batches.

## 18. Observability: do not collapse every error into 403

Example audit event:

```json
{
  "event": "policy_decision",
  "requestId": "req-001",
  "decisionId": null,
  "actorRef": "opaque-actor-id",
  "tenantAlias": "tenant-a",
  "action": "READ",
  "resourceType": "document",
  "outcome": "UNAVAILABLE_TIMEOUT",
  "durationMillis": 302,
  "policyVersion": null,
  "pdpCluster": "zone-a"
}
```

Depending on your system, `actorRef`/`tenantAlias` may still constitute personal data requiring log access controls.

Useful metrics:

| Metric | Rationale |
| --- | --- |
| `pdp_checks_total{outcome}` | Separate PERMIT, DENY_POLICY, TIMEOUT, INVALID, CIRCUIT_OPEN |
| `pdp_duration_seconds` | Track latency percentiles |
| `pdp_retry_total` | Detect retry storms |
| `pdp_circuit_state` | Observe OPEN/HALF_OPEN/CLOSED |
| `pdp_invalid_response_total{reason}` | Spot schema/binding/version faults |
| `pdp_tls_error_total` | Diagnose trust stores and certificates |
| `policy_revision_lag` | Detect stale PDP/cached policy bundles |
| `authorization_unavailable_total` | Count requests blocked by PDP outages |

Avoid putting `requestId`, `subjectId`, or `documentId` into **metric labels** due to high cardinality and data disclosure risks. Use traces/logs with proper access controls. Clients receive neutral messages without revealing document existence or internal policies.

## 19. Failure test suite: cover success and all failure paths

| Case | Expected enforcement |
| --- | --- |
| PERMIT matching caller/tenant/resource/action/version/expiry | Proceeds if local guards also pass |
| Valid DENY | Never enters business method |
| Connect timeout | Never enters business method |
| Response timeout | Never enters business method |
| Connection refused/reset | Never enters business method |
| DNS failure | Never enters business method |
| Untrusted TLS certificate/hostname | Never enters business method |
| 200 with empty body | Never enters business method |
| 200 with malformed JSON | Never enters business method |
| JSON with duplicate effect keys | Reject/deny |
| Effect null/unknown/bool/string "true" | Reject/deny |
| Wrong subject | Reject/deny |
| Wrong tenant | Reject/deny |
| Wrong resource ID/type | Reject/deny |
| Wrong action | Reject/deny |
| Wrong requestId/nonce | Reject/deny |
| Expired reply | Reject/deny |
| Stale policy version | Reject/deny |
| PERMIT with unsupported obligation | Reject/deny |
| PDP returns 401/403 due to service credential | Never treat as valid user PERMIT/DENY |
| Circuit OPEN | Does not call PDP, still blocks business action |
| Retries exhaust attempts/deadline | Business operation does not run |
| Cache holds PERMIT for another user | Cache key test catches it, forbids use |
| Membership/ACL just revoked | Never uses stale positive cache |
| Batch missing an item | Never auto-grants missing item |
| Request canceled | Does not continue mutation |
| Resource version changed before UPDATE | Conditional update hits 0 rows; never treats as success |

**Tests must assert zero side effects** on failure paths, not just HTTP status codes. A controller might update the DB before throwing an exception.

### HTTP-layer fault injection

Use WireMock/MockWebServer or a suitable HTTP stub server to simulate slow responses, socket resets, truncated bodies, 200 HTML, mismatched IDs, 503s, bad TLS certs, and open circuits. Unit tests merely mocking `policyGate.check()` returning false do not test real transport, parsing, or deadlines.

### Integration via Spring Security

`@SpringBootTest`, `@AutoConfigureMockMvc`, and `@WithMockUser` verify endpoint matchers and managers. With the manager in section 13, timeouts map to `AuthorizationDecision(false)`, so authenticated callers typically get 403. If your project maps typed operational errors to 503, assert that status accordingly.

`@WithMockUser` does not validate JWT signatures/issuers/audiences. If the app is a Resource Server, add decoder/security filter tests using real tokens signed with test keys alongside mock auth tests.

## 20. Runbook for PDP outages or schema misdeployments

### When timeouts/network errors spike

1. Confirm `UNAVAILABLE_TIMEOUT`/`UNAVAILABLE_NETWORK` spikes, separate from `DENY_POLICY`.
2. Check PDP clusters, endpoints/certificates, DNS, gateways, service credentials, and policy backends.
3. Inspect deadlines, connection pools, thread pool saturation, retry rates, and circuit states.
4. Never enable `permitAll()` on protected routes.
5. Activate redundancy/locally verified bundles only if designed into the architecture.
6. Measure canary valid PERMITs and DENYs once the service recovers.
7. Confirm zero unauthorized side effects occurred during the outage.
8. Conduct a security incident review if any fail-open path is discovered.

### When INVALID_RESPONSE spikes

- Likely causes: client/server schema mismatch, altered content-type, proxy returning HTML 200, or policy version mismatch.
- Check strict parser/duplicate key handling, response signatures, bindings, and obligations.
- Canary test with ALLOW, DENY, and invalid responses; never "fix" by disabling validation.
- Roll back or forward-fix the protocol per compatibility plan while preserving audits.
- Never assume an `INVALID_RESPONSE` spike means users suddenly lack permissions.

### When revoking permissions

- Invalidate relevant cached PERMITs or bump entitlement/policy revisions.
- Update bundles and verify all instances enforce the version floor.
- For background jobs, reauthorize at execution time if policy requires.
- Verify TOCTOU protections and conditional writes.
- Monitor for stale PERMIT decisions and investigate any occurrence.

## 21. Dangerous anti-patterns

**1. `catch (Exception) return true`:** PDP outage becomes an access bypass.

**2. `HTTP 200 = PERMIT`:** fails to verify decision content.

**3. `if (effect != "DENY") allow`:** null/unknown responses become allow.

**4. `AuthorizationManager` returning null on timeout:** abstain is not an explicit denial.

**5. No request/read deadlines:** pools exhaust easily, enabling DoS.

**6. Retrying `DENY_POLICY`:** pointless, amplifies load, and creates unstable behavior.

**7. Falling back to `permitAll` or unbounded stale PERMITs:** violates revocation.

**8. Caching by `resourceId` alone:** leaks access across users/tenants.

**9. Checking only `effect` without subject/tenant/action/resource:** replies for other requests can grant wrong access.

**10. Skipping TLS/source verification:** attackers can forge JSON PERMITs.

**11. Ignoring obligations:** conditional PERMITs turn into unconditional PERMITs.

**12. Logging raw JWTs or sensitive policy requests/responses:** leaks secrets/PII.

**13. Taking PDP URL/policy revision from client input:** invites SSRF and bypass/downgrade.

**14. Conflating transport 403 with policy DENY:** corrupts metrics and incident triage.

**15. Checking the PDP after mutation:** policy DENY cannot undo side effects already committed.

**16. Reusing an old document PERMIT after owner/tenant/version changes:** TOCTOU.

**17. Skipping batch response ID validation:** mixes outcomes or skips missing items.

**18. Metrics tracking only total 403s:** hides outages and schema faults.

**19. A platform ADMIN service credential acting across all tenants without scope checks:** confused deputy.

**20. Raising retries/timeouts indefinitely to "stop errors":** degrades availability further.

## 22. Production checklist

- [ ] Allow only on a **valid, properly bound, unexpired PERMIT**.
- [ ] Authentication/tenant/resource local guards are independent and fail closed.
- [ ] `DENY_POLICY` is separated from `TIMEOUT`, `NETWORK`, `INVALID`, `CIRCUIT_OPEN`.
- [ ] `AuthorizationManager` never returns null/abstain on PDP failures when acting as a mandatory guard.
- [ ] Connect/read/overall timeouts are finite and fit inside the request deadline.
- [ ] Retries apply only to transient/idempotent evaluations with bounded attempts and backoff.
- [ ] Circuit breaker OPEN is never treated as PERMIT; bulkheads added where needed.
- [ ] PDP URLs are allowlisted, and TLS/hostname/mTLS/provenance are verified.
- [ ] Strict JSON schema/duplicate keys/effect checks; reject empty or malformed replies.
- [ ] RequestId/subject/tenant/resource/action/version/expiry are all verified.
- [ ] Mandatory obligations are supported and enforced.
- [ ] Positive decision caches use full-scope keys, bounded TTLs, and revocation policies.
- [ ] Side effects happen only after authorization; writes also enforce tenant/version conditional predicates.
- [ ] Batch policy checks handle missing items and atomicity properly.
- [ ] HTTP 401/403/503 are mapped at the right security/application boundaries.
- [ ] Audit logs record decisionId, reason, latency, and policy revision without secrets.
- [ ] Tests cover HTTP fault injection, invalid responses, wrong bindings, revocations, retries, caching, open circuits, and zero side effects.
- [ ] Runbooks exist for outages, schema mismatches, and revocations.

**Remember:** timeouts, network errors, and malformed responses **do not prove the caller was policy-DENIED**, yet they **never produce a PERMIT either**. Enforcement may proceed only with a **validated PERMIT** for the exact current caller, tenant, resource, and action. Keep operational faults distinct for diagnosis and recovery while maintaining the invariant **never allow unauthorized data access or side effects**.

## Official documentation

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — AuthorizationManager JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j — TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
