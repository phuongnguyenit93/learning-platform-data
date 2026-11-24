# Policy Service Failures Leading to Accidental Access Grants

## Learning Objectives

A system can authenticate users accurately, configure endpoints properly, and yet still **grant permissions mistakenly** when its policy decision service times out, loses connectivity, returns invalid responses, or is temporarily unavailable. The core bug is the application interpreting “failed to obtain authorization decision” as “access permitted” — **fail-open**.

After this lesson, you can:

1. Distinguish **PERMIT** and **DENY** outcomes from **INDETERMINATE**, **NOT_APPLICABLE**, empty responses, and infrastructure failures.
2. Pinpoint fail-open points in Spring Security flows using an external policy service/PDP.
3. Implement a **fail-closed** authorization boundary: allow only upon receiving an **explicit, valid, context-matching PERMIT**; deny protected execution in all other cases.
4. Design timeouts, retries, circuit breakers, caching, and monitoring to maintain availability without accidentally elevating privileges.
5. Write tests that intentionally fault the policy service, proving controllers/services/repositories never execute unauthorized operations.

## 1. Scenario: Policy Decision Service Temporarily Unavailable

Suppose `GET /api/documents/42` requires a logged-in user and also needs per-document decisions:

- **PEP (Policy Enforcement Point)**: the place intercepting requests and enforcing decisions, e.g., `AuthorizationManager`, `@PreAuthorize`, or a dedicated service layer in the Spring app.
- **PDP (Policy Decision Point)**: the policy service deciding whether a subject may perform an action on a resource, potentially a remote policy engine.
- **PIP (Policy Information Point)**: information sources for decisions, such as tenant, owner, document classification, org relationships, policy version; critical attributes must come from server-trusted sources.

Normal flow:

```text
Client (authenticated)
    |
    v
Spring Security + PEP  -- decision query: user, tenant, action, resource --> PDP
    |                                                                         |
    |<------------------------------ PERMIT / DENY ---------------------------|
    |
    +-- valid PERMIT --> read data / execute operation
    |
    +-- DENY or no trusted decision --> block
```

When the PDP fails, dangerous handling often hides inside seemingly harmless code:

```java
// WRONG: for bug recognition only; never use in real systems.
boolean canRead(PolicyRequest request) {
    try {
        return policyClient.evaluate(request).isPermit();
    } catch (Exception ex) {
        return true; // FAIL-OPEN: policy service outage equals read permission!
    }
}
```

If an attacker or network outage prevents the policy service from responding, every request takes the `return true` branch. A low-privilege account can then read documents it does not own; on write/delete/export APIs, the impact is even worse. Another variant is “when the policy service errors, only check `authenticated()`” — still wrong when policy requires owner, tenant, ACL, sensitivity level, or approval state.

**Principle:** wherever an authorization decision is required, **without a trusted PERMIT result, do not execute the protected action**. “Unable to decide” is not the same as a “business DENY” diagnostically, yet both must result in **not granting access** at the PEP.

## 2. Distinguishing Business Decisions from Policy Evaluation Errors

Not every PDP system uses the same status set. The table below is an **illustrative contract**; applications must map strictly from their real PDP protocol.

| Outcome / Condition | Meaning | May the PEP Proceed? |
| --- | --- | --- |
| Valid `PERMIT` | Policy confirms allowing exact subject, tenant, action, resource, conditions, and version | **Yes**, after verifying any mandatory obligations/constraints |
| `DENY` | Policy explicitly forbids access | **No** |
| `NOT_APPLICABLE` | No rule applies; **not** PERMIT | **No**, unless a clearly defined combining rule explicitly yields a valid PERMIT |
| `INDETERMINATE` | PDP cannot reach a definitive decision | **No** |
| Timeout, DNS, TLS, connection reset, HTTP 5xx | No trusted decision | **No** |
| HTTP 200 with empty body, invalid JSON schema, unknown status, `null` | Outcome cannot be verified | **No** |
| Response belongs to another user/tenant/resource/action or was replayed | Outcome does not match context | **No** |
| Cached PERMIT expired or revoked | Permission is no longer confirmed | **No** |
| Unauthenticated, invalid principal | No trusted identity | **No** |

**Checking only the PDP's HTTP status is insufficient.** HTTP 200 only means the service call succeeded at the transport level. Responses must be validated for schema, result, request context, and policy constraints; never interpret an absent `"allow"` as true, `"deny": false` as allow, or any value other than `"deny"` as PERMIT.

If the PDP returns PERMIT with obligations such as “show redacted copy only” or “limit within allowed time window”, the PEP must enforce those obligations. If the PEP cannot enforce a mandatory obligation, the result does not qualify for granting access. With multiple policies, combining algorithms (deny-overrides, permit-overrides, etc.) must be **approved rules**; a `NOT_APPLICABLE` or error component must never automatically escalate to ALLOW.

### Fail-Open vs Fail-Closed

- **Fail-open:** “PDP did not answer → grant access as if PERMIT”. Preserves partial availability by sacrificing the security boundary.
- **Fail-closed:** “PDP did not answer → block the protected operation from proceeding”. Preserves the permission boundary, potentially making the feature temporarily unavailable.
- **Per-scope fail-secure:** truly public endpoints with an **explicit, PDP-independent** `permitAll()` rule continue serving; policy-gated operations close when lacking a decision. This is pre-designed permission classification, not auto-loosening permissions during outages.

Example: `GET /health` marked public from the start can keep returning infrastructure status; `GET /api/documents/42` must not use a PDP outage as an excuse to skip ACL checks. If security policy mandates all read paths require the PDP, there are no ad-hoc exceptions.

## 3. A Tiny Java Bug Can Alter the Entire Contract

The snippet below **runs standalone on Java 17+**, simulating an adapter where invalid outcomes or exceptions must not grant access. File name must be `FailClosedDemo.java`:

```java
public class FailClosedDemo {
    enum Decision {
        PERMIT, DENY, NOT_APPLICABLE, INDETERMINATE
    }

    @FunctionalInterface
    interface PolicyClient {
        Decision query();
    }

    static boolean authorized(PolicyClient client) {
        try {
            return client.query() == Decision.PERMIT;
        } catch (RuntimeException failure) {
            return false;
        }
    }

    public static void main(String[] args) {
        for (Decision d : Decision.values()) {
            System.out.println(d + " -> " + authorized(() -> d));
        }
        System.out.println("NULL -> " + authorized(() -> null));
        System.out.println("TIMEOUT -> " + authorized(() -> {
            throw new IllegalStateException("timeout");
        }));
    }
}
```

Compile/run:

```bash
javac FailClosedDemo.java
java FailClosedDemo
```

Exact stdout:

```text
PERMIT -> true
DENY -> false
NOT_APPLICABLE -> false
INDETERMINATE -> false
NULL -> false
TIMEOUT -> false
```

The key point is not that every exception in the application should be swallowed. **Only failures occurring along the policy evaluation path** should convert into “do not grant access”, accompanied by logs/metrics/alerts. Unexpected programming bugs must not let operations proceed either; exceptions may bubble up as server errors and halt request processing. In production, you must know **why** the PDP denied or was unavailable rather than collapsing every cause into an anonymous log message.

## 4. Fail-Closed Integration at the Spring Security Boundary

Spring Security manages authentication, request authorization, and method authorization; it **does not turn remote policy service failures into PERMIT by default**. Risk arises when applications add callbacks, `AuthorizationManager`s, SpEL expressions, custom filters, or client fallbacks containing faulty allow logic.

A straightforward strategy is keeping services protected by `@PreAuthorize`, backed by a policy bean that returns `true` only on an explicit PERMIT. The snippets below are **integration code for a Spring Boot 3.x/Spring Security 6.x application**, not a standalone program; entities, repositories, HTTP clients, DI setup, and imports must exist in the project.

### 4.1. Decision Adapter: Only PERMIT Grants Access

Example file `DocumentPolicy.java` (supporting types can be split into separate files in a project):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

enum PolicyDecision {
    PERMIT, DENY, NOT_APPLICABLE, INDETERMINATE
}

record PolicyQuery(
        String subjectId, String tenantId, String action, long documentId) {}

record PolicyResult(PolicyDecision decision) {}

interface RemotePolicyClient {
    PolicyResult evaluate(PolicyQuery query);
}

interface TenantIdentity {
    String verifiedTenant(Authentication authentication);
}

@Component("documentPolicy")
public final class DocumentPolicy {
    private static final Logger log =
            LoggerFactory.getLogger(DocumentPolicy.class);

    private final RemotePolicyClient remote;
    private final TenantIdentity tenants;

    public DocumentPolicy(RemotePolicyClient remote, TenantIdentity tenants) {
        this.remote = remote;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication actor, long documentId) {
        if (actor == null
                || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || documentId <= 0) {
            return false;
        }

        try {
            String tenantId = tenants.verifiedTenant(actor);
            if (tenantId == null || tenantId.isBlank()) {
                return false;
            }

            PolicyQuery query = new PolicyQuery(
                    actor.getName(), tenantId, "document:read", documentId);
            PolicyResult result = remote.evaluate(query);

            return result != null
                    && result.decision() == PolicyDecision.PERMIT;
        } catch (RuntimeException policyEvaluationFailure) {
            log.warn("Policy evaluation failed; access denied (type={})",
                    policyEvaluationFailure.getClass().getSimpleName());
            return false;
        }
    }
}
```

This is a **deny-by-default rule at the PEP**, with critical constraints:

- `TenantIdentity.verifiedTenant(...)` must pull the tenant from a trusted identity source (e.g., JWT claims verified for signature and audience/issuer, or an authenticated session); never use caller-supplied `?tenant=...`.
- `RemotePolicyClient` is responsible for deadlines, TLS/authentication with the PDP, response schema validation, and request–response binding if supported by the protocol; any parse/transport failure must never convert to PERMIT.
- The PDP must rely on **trusted** document attributes (owner, tenant, classification, ACL) from the source of truth. Sending only `documentId` + caller tenant without checking the resource–tenant relationship at the PDP creates another IDOR vulnerability.
- Return PERMIT only when mandatory obligations can be fulfilled. The example above assumes the policy produces no obligations; if it can, `PolicyResult` must carry them and the PEP must confirm before returning `true`.
- `catch (RuntimeException)` wraps only policy evaluation and returns denial; in real systems add safe metrics/structured audits, handle known errors explicitly, and ensure unexpected errors also **halt the operation**. Never log tokens, raw documents, or PDP secrets.

### 4.2. Placing Guards Before Operations with Side Effects

Example service and controller (each public class in its appropriate Java file):

```java
// DocumentService.java
@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public DocumentDto read(@P("documentId") long documentId) {
        Document entity = repository.findById(documentId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new DocumentDto(entity.getId(), entity.getTitle());
    }
}

// DocumentController.java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public DocumentDto read(@PathVariable long documentId) {
        return service.read(documentId);
    }
}
```

Configuration must enable method security and declare explicit request rules; for example:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .authenticated()
                .anyRequest().denyAll());
        return http.build();
    }
}
```

Required `import`s (such as `@P` from `org.springframework.security.access.method.P`) must be present in real files. The `authenticated()` gate ensures identity at the request level; `@PreAuthorize` enforces the decision **on the specific document**. Never replace `@PreAuthorize` with `authenticated()` when the PDP fails. The `anyRequest().denyAll()` rule prevents accidentally leaving new unreviewed routes open.

Method security works via Spring AOP proxies, so `DocumentService.read` must be called through a Spring-managed bean; self-invocation like `this.read(...)` inside the same class can skip the interceptor. Do not treat controllers as the only call path: batch jobs, message consumers, or other services must also respect permissions at the appropriate business boundary.

**Note on HTTP results:** when `@PreAuthorize` returns false, an authenticated caller typically receives **403** from the authorization layer. Unauthenticated callers enter the authentication entry point, typically **401** for APIs, depending on config. If you need to distinguish “PDP error” from “PDP DENY” for clients and return **503**, design a dedicated unavailable error path ensuring it **halts** the protected operation without turning into allow or leaking data. Exact status codes must be proven with integration tests using real filter chains/exception handlers.

## 5. Code Patterns Prone to Fail-Open

### 5.1. Dangerous Default Values

```java
// WRONG: defaults to true and only updates when remote call succeeds.
boolean permitted = true;
try {
    permitted = remotePolicyAllows();
} catch (RuntimeException ignored) {
    // permitted remains true
}
return permitted;
```

The right approach is **defaulting to deny**, promoting to allow only after a valid result. You can express this principle as `result != null && result.decision() == PERMIT` as shown earlier.

### 5.2. Broad Fallback to `permitAll()`

```java
// WRONG: config permits all requests when policy bean is not found.
if (!policyServiceConfigured) {
    http.authorizeHttpRequests(a -> a.anyRequest().permitAll());
}
```

A missing policy service is a configuration or availability issue, not a reason to drop security. Only endpoints designed as public from the outset should use `permitAll()`. Review `SecurityFilterChain` in matcher order (matchers are evaluated sequentially in the DSL) and test sensitive routes. Watch out for multiple filter chains, test/dev profiles enabled in production, fallback rules after upgrades, and misplaced custom filters.

### 5.3. Treating “No DENY” as PERMIT

```java
// WRONG: null or unknown statuses will be permitted.
return response == null || response.decision() != PolicyDecision.DENY;
```

Comparing strictly against verified `PERMIT` is safer; `NOT_APPLICABLE`/`INDETERMINATE` is not ALLOW. If the policy engine has complex multi-rule semantics, combine rules inside the PDP before emitting one final decision; the PEP must not invent interpretations for missing states.

### 5.4. JSON Errors, Timeouts, HTTP 5xx, and Hidden “Default True” Client Code

Some SDKs/clients deserialize missing boolean fields as `false`; other snippets use `Boolean.TRUE.equals(...)`; a new wrapper might declare `Optional.orElse(true)` or a resilience library `fallbackMethod` returning true. Inspect **the entire path** from HTTP PDP response → adapter → cache → gate → security expression, not just the controller method. Forbid recovering from timeouts to PERMIT via `onErrorReturn(true)`, `exceptionally(ex -> true)`, `onErrorResume(... -> Mono.just(true))`, or equivalents in reactive code.

### 5.5. When Stale Cached PERMITs Become a Bypass

Caching solely by `documentId` while omitting `subjectId`, `tenantId`, or `action` can return someone else's PERMIT. Caching PERMITs too long keeps decisions alive after permissions are revoked. When the PDP fails, “reading every old decision” is especially dangerous. Caches need keys with full context, validity/version policies, short TTLs matching sensitivity, and revocation handling; cache misses/expiries must never escalate to allow. Never cache across tenants, roles, access purposes, or policy versions.

Offline-capable designs based on signed policies with controlled expiration exist, yet must be **specified and evaluated separately**. Never assume stale PERMITs are safe in general systems.

## 6. Testing Policy Service Failures: Proving No Data Is Accessed

Do not stop at unit testing a `canRead()` method. Verify the entire Spring Security chain, method interceptor, and work-execution layer. For read endpoints, assert status, zero leaked data in the body, and **zero repository interactions**; for write/delete operations, verify side effects against a real database. Seed fixtures with out-of-scope users/tenants/documents so failures are visible.

Test example based on `DocumentPolicy` and `DocumentService` above. Assumes the application already provides controller/repository and beans; `@MockBean` is used on Spring Boot 3.3, and tests require JUnit, Mockito, Spring Test Security, and Spring MVC imports:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PolicyUnavailableHttpTest {
    @Autowired MockMvc mvc;

    @MockBean RemotePolicyClient remote;
    @MockBean TenantIdentity tenants;
    @MockBean DocumentRepository repository;

    @BeforeEach
    void trustedTenant() {
        when(tenants.verifiedTenant(any(Authentication.class)))
                .thenReturn("tenant-a");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void timeoutDoesNotReadProtectedDocument() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class)))
                .thenThrow(new IllegalStateException("timeout"));

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden())
                .andExpect(content().string(""));

        verifyNoInteractions(repository);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingResponseNeverMeansPermit() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class))).thenReturn(null);

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void indeterminateDecisionNeverMeansPermit() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class)))
                .thenReturn(new PolicyResult(PolicyDecision.INDETERMINATE));

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }
}
```

The sample test assumes the filter chain actually activates method security, MockMvc uses the real application context, and 403 responses have empty bodies. If the app uses a custom `AccessDeniedHandler` producing JSON errors, replace the empty-body assertion with checks that **no document/canary content appears** and the agreed error structure holds. If `DocumentPolicy` returns false yet the service still reads data, inspect Spring proxies/method security rather than relaxing test expectations.

Add independent tests for valid `PERMIT` (reaching the right resource), `DENY`, `NOT_APPLICABLE`, null, malformed payloads, missing fields, missing tenant info, and unauthenticated users. HTTP tests with real principals/JWTs verify validated tokens and confirm claims cannot be overridden by client-sent headers or queries.

### Fault Injection Matrix

| Intentionally Injected Fault | Mandatory Outcome | What to Verify |
| --- | --- | --- |
| PDP unreachable, DNS error, or bad TLS | Do not grant access | Resource not read/written; request terminates in bounded time |
| PDP returns 500/502/503 or times out | Do not grant access | No fallback to allow; error-type metrics recorded |
| Empty/corrupt JSON, missing or unknown decision field | Do not grant access | Never interpret `null`/unknown as PERMIT |
| PDP returns `DENY` | Business denial | Never turn DENY into retries that accidentally yield PERMIT |
| PDP returns `NOT_APPLICABLE`/`INDETERMINATE` | Do not grant access | No “not DENY equals ALLOW” path |
| PDP returns PERMIT for wrong user/tenant/resource/action | Do not grant access | Request–response binding and trusted attribute sources |
| User loses permission while old PERMIT remains cached | Expired decision must not be used | Cache key, TTL, invalidation, policy version |
| Circuit breaker opens after repeated errors | Do not grant access | No side effects invoked; predictable error returned |
| Service boots before PDP is configured | Do not grant access on PDP-gated APIs | Clear startup/readiness; never enable `permitAll()` |
| Multiple concurrent requests during PDP outage | Do not grant access on any affected request | No shared mutable “last allow” boolean |
| PDP recovers | Only valid new PERMIT allows access | Recovery path neither stays stuck in permanent deny nor serves stale allows |

The **sample integration test snippet** tests proxies and endpoints; an acceptance suite should add fault injection on a real HTTP client (mock server returning 5xx/delays/bad bodies) and a data test confirming zero DB/side effects. If logic uses retries/circuit breakers/caches, test each state separately for potential false grants.

## 7. Improving Resilience Without Opening Permissions

Fail-closed can temporarily make an API unavailable. Solve availability through **infrastructure and policy design**, not by returning true inside a `catch`:

1. **Clear timeouts/deadlines:** set connect timeouts and overall response deadlines matching SLA; never let requests hang indefinitely. When a deadline expires without a decision, deny.
2. **Bounded retries:** retry only recoverable errors, small retry counts, exponential backoff/jitter, respecting deadlines and load budgets. If retries exhaust without PERMIT, deny. Never retry entire business operations with side effects just because the PDP did not reply.
3. **Circuit breakers:** when the PDP continuously fails, stop calling it briefly and return unavailable/denied; never use an allow fallback. Include half-open probes and metrics for recovery.
4. **Replicas and health/readiness:** increase PDP availability, isolate resources with bulkheads, and monitor queues/saturation. Readiness can reflect inability to serve PDP-dependent requests; public health endpoints must not leak secrets.
5. **Bounded caching:** if policy allows caching, key by exact actor–tenant–resource–action–version/conditions, enforce strict TTLs, and handle revocation. Never reuse expired PERMITs as an outage “fix”.
6. **Distinguish errors from denies in observability:** `policy_decision_total{outcome=permit|deny|unavailable|invalid}`, latency/timeouts, circuit-breaker state, and correlation IDs. Never put tokens, emails, or raw policy inputs in metric labels.
7. **Transparent exception policies:** approved public endpoints or offline content must be pre-defined with specific scope/expiry. “Break-glass” privileges require deliberate mechanisms, strong authentication, audits, and expiration; never materialize because a policy service failed.

In systems where effective permissions change over time (account locked, tenant moved, ACL revoked), prioritize freshness and revocability. A stale PERMIT cache can make fail-closed code **effectively fail-open on permission validity**.

### 403 or 503 During a PDP Outage?

Two distinct objectives:

- **Authorization:** operations must not execute without PERMIT.
- **Protocol/UX:** you may return 403 for gate-denied commands, or 503 “authorization service temporarily unavailable” if the exception layer distinguishes outages and the contract allows it. Never leak internal details or confirm existence of sensitive resources.

If returning 503 and clients retry, still return zero data and commit zero transactions; never change the response to 200 to “preserve UX”. Even a 403 during an outage requires alerting, because it is an infrastructure failure rather than every account suddenly getting a policy DENY. Never rely solely on HTTP status codes to track PDP decision metrics.

## 8. Subtle Dangers in Multi-Layered Applications

**TOCTOU (time-of-check/time-of-use).** If the PEP checks based on a document's owner/tenant, and ownership changes before the service updates it, the decision may no longer hold at execution time. For critical actions, coordinate checks and writes inside a transaction/conditional update per policy or recheck at the data boundary; never treat a PERMIT as immutable forever.

**Path-based authorization without data-level authorization.** `requestMatchers("/api/documents/**").authenticated()` only blocks anonymous users. It does not check who owns document 42. A policy service failure certainly does not eliminate resource checks; row/object-level PDP or local decisions are required.

**Self-invocation and alternative call paths.** `@PreAuthorize` on a public service method may not execute on internal `this.method()` calls. Background jobs, message listeners, GraphQL resolvers, and other APIs can call services through unguarded paths. Test real flows and place permissions at layers that cannot be easily bypassed.

**Inconsistent source of truth.** A PDP trusting client-sent roles/tenants can return PERMIT for a forged context; even with a healthy PDP, that remains a vulnerability. Subject attributes must be authenticated, and resource attributes must come from trusted data. A PERMIT response is meaningful only when bound to the right subject/action/resource/policy conditions.

**Deployment-only bugs.** Local mocks often always return PERMIT/DENY, whereas production configuration might miss the PDP URL, have expired tokens, rotated certs, DNS glitches, broken mTLS, schema drift, or feature flags disabling policies. Deployment/chaos tests must use isolated realistic data and verify “PDP down ⇒ no grants”.

**Reactive/asynchronous.** With WebFlux, a `Mono<Boolean>` defaulting to `true` via `onErrorReturn(true)`, `onErrorResume`, or mishandled empty streams can fail-open. Async jobs must also await decisions before executing side effects. Regardless of runtime, the invariant remains “no valid PERMIT ⇒ no resource side effects”.

## 9. Acceptance Checklist

Before approving an external policy service integration, prove via tests and review:

1. Only **explicit, valid, context-matching PERMIT** opens the gate; DENY, unknown, empty, NOT_APPLICABLE, INDETERMINATE, timeouts, network errors, and parse errors keep the gate closed.
2. Authentication, tenant/owner, and resource metadata come from trusted sources; clients cannot forge request context or replay another user's decision.
3. `@PreAuthorize`/`AuthorizationManager` actually executes on every critical business path, never bypassed by self-invocation, faulty chains/matchers, or fallback configs.
4. When the policy service fails, no sensitive data appears in responses and no protected reads or side effects execute; test both defined 403/503 behaviors.
5. Retries, caches, circuit breakers, and startup states **never** silently turn unavailable into allow.
6. Logs/metrics/alerts distinguish policy DENY from PDP outages; no secrets enter telemetry and a recovery procedure exists.
7. When the PDP recovers or permissions change, updated permissions take effect accurately with zero stale cached PERMITs.

**Conclusion:** policy service reliability affects availability, yet must never dictate the system's default privilege level. In Spring Security, every PEP must guarantee: **only a valid PERMIT allows the operation, while policy evaluation failures verifiably halt access**.

## References

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): configuring `authorizeHttpRequests`, `permitAll`/`denyAll`, and using `AuthorizationManager`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): decision execution mechanics of `AuthorizationManager`.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): placement of `AuthorizationFilter` and `ExceptionTranslationFilter` when requests are denied.
