# Collecting Audits, Regression Testing, and Assembling Evidence for Each Authorization Decision

## 1. Goal: Answering “Who Is Permitted to Do What, Why, and Where Is the Evidence?”

In Spring Security, HTTP statuses 200/401/403 are only one perspective on authorization. Whenever a request is blocked or permitted, we must simultaneously verify **who requested**, **which action on which resource**, **which policy and context were evaluated**, **outcome and reason**, **whether the decision was enforced**, and **evidence sufficient to reproduce**. A single request can pass through multiple checks: HTTP `AuthorizationFilter`, method `@PreAuthorize`, resource ACLs, and business constraints prior to commit.

For example: Alice in tenant `acme`, holding `ROLE_REVIEWER`, requests approval of document `D-42` belonging to tenant `beta`. Good evidence proves that `document.approve` version `17` returned **DENY/TENANT_MISMATCH**, the method did not write the document, the response was 403 per the API contract, and the cross-tenant regression case passed. Merely logging “request returned 403” does not identify which policy denied it.

After this lesson, you will be able to:
- Design structured audit events with correlation linking HTTP, methods, policies, transactions, and tests.
- Instrument at the right Spring Security checkpoints; understand the limits of `AuthorizationEventPublisher` and differences among `PERMIT, DENY, ABSTAIN, ERROR`.
- Build a golden permission matrix independent of old implementations, testing outcomes, side effects, and proxy/filter-chain enforcement.
- Package `scenarioId → decisionId → traceId → policyVersion → artifact` into a reviewable dossier.
- Ensure audits are secure, with retention, failure policies, good performance, and measurable completeness.

**Scope:** Spring Security Servlet/MVC, primarily Spring Security 6.4–6.5 and Java 17+. WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain` and corresponding observability mechanisms; never copy Servlet configurations verbatim to Reactive.

## 2. Distinguishing Four Outcome Layers

| Layer | Facts to Observe | What Cannot Be Inferred Automatically |
| --- | --- | --- |
| Authentication | Authentication type, principal reference, status, issuer | A valid token does not prove resource permissions |
| Authorization decision | Policy/rule, resource/action, `PERMIT / DENY / ABSTAIN / ERROR`, reason | A grant decision does not guarantee the entire request is ultimately allowed |
| Enforcement and business outcome | `PROCEED / BLOCK`, whether method ran, transaction commit/rollback | A method running does not guarantee the DB committed |
| HTTP response | Status, entry point, exception mapping, headers | 401/403 can originate from authentication, CSRF, firewall, or another policy |

**DENY does not rigidly mean HTTP 403.** For anonymous callers, Spring Security may return 401 to challenge for authentication; for authenticated users lacking privileges, it usually returns 403. A POST missing CSRF can be blocked before reaching the intended policy. Therefore tests must observe decision + enforcement + response + side effects, not just HTTP status.

### 2.1. One Request Can Have Multiple Decisions

~~~text
HTTP request [traceId=t-840]
  │
  ├─ AuthorizationFilter    [decisionId=d-1, PERMIT, http:authenticated]
  │
  ├─ method @PreAuthorize   [decisionId=d-2, DENY, TENANT_MISMATCH]
  │
  ├─ business method        [NOT_EXECUTED]
  │
  └─ HTTP response          [403]
       └─ audit: trace t-840 links decision d-1, d-2, and response
~~~

`traceId` groups stages of the same request; `decisionId` must distinguish **each evaluation**; `scenarioId` links records in regression tests. Never use `traceId` as a decision ID because multiple advisors can evaluate in one request. Never merge HTTP and method denials into an unattributed single event.

### 2.2. Distinguishing Null, Errors, and Effective Decisions

An `AuthorizationManager` can permit, deny, abstain (some APIs return `null` to make no decision), or throw an exception on policy error. Depending on the manager/composition, an abstain may be handled by another manager; it is **neither DENY nor PERMIT by default**. Record two fields:

- `decision`: the component's actual result (`PERMIT/DENY/ABSTAIN/ERROR`).
- `enforcement`: the final outcome after applying the full policy and fallback (`PROCEED/BLOCK/UNAVAILABLE`).

Sensitive applications typically design a fallback “without an explicit permit decision, block,” yet this must be explicit in code and tests; never assume it is the default in every Spring Security version.

## 3. Reconcilable and Data-Safe Audit Schema

| Field | Purpose | Implementation Notes |
| --- | --- | --- |
| `schemaVersion` | Manage event evolution | Never silently change field semantics |
| `eventId` | Identify audit record | Unique per emission; retries need a dedup strategy |
| `decisionId` | Identify policy evaluation | Unique per evaluation |
| `traceId`, `spanId` | Link to trace/HTTP | Propagate across async when needed |
| `occurredAt`, `durationMs` | Timeline and performance | UTC; synchronized clocks; never treat time as revision |
| `principalRef`, `authType` | Authenticated account/request | Internal ref/pseudonym; never log tokens/passwords |
| `tenantRef`, `resourceType`, `resourceRef` | Verify permission boundaries | Normalize tenant/resource, store minimally |
| `action`, `enforcementPoint` | Operation and checkpoint | E.g., `document.approve`, `METHOD_PRE_AUTHORIZE` |
| `policyId`, `policyVersion`, `ruleId` | Applied policy | Pin real commit/config version, never write “latest” |
| `decision`, `reasonCode` | Structured conclusion | Stable reason codes, no PII |
| `enforcement`, `businessOutcome` | Did the decision take effect? | `BLOCK/PROCEED` and `COMMITTED/ROLLED_BACK/NOT_EXECUTED` |
| `contextVersion`, `grantVersion` | Data used for evaluation | ACL version, membership snapshot, cache |
| `scenarioId`, `testRunId` | Correlate test artifacts | Include only when a real test context exists |

Illustrative **mock, minimally identified** audit record:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-840-2",
  "decisionId": "decision-840-2",
  "traceId": "trace-840",
  "occurredAt": "2026-10-01T09:15:30Z",
  "principalRef": "actor-17",
  "tenantRef": "acme",
  "resourceType": "document",
  "resourceRef": "doc-42",
  "action": "document.approve",
  "policyId": "document-approval",
  "policyVersion": "17",
  "ruleId": "TENANT_BOUNDARY",
  "enforcementPoint": "METHOD_PRE_AUTHORIZE",
  "decision": "DENY",
  "reasonCode": "TENANT_MISMATCH",
  "enforcement": "BLOCK",
  "businessOutcome": "NOT_EXECUTED"
}
~~~

This schema is an **application-defined contract**, not built-in output of `AuthorizationDeniedEvent`. Never serialize raw `Authentication`, `MethodInvocation`, `HttpServletRequest`, or `toString()` of protected objects: they can contain passwords/tokens, query strings, arguments, and sensitive data.

**Reason codes** like `AUTH_REQUIRED`, `ROLE_MISSING`, `TENANT_MISMATCH`, `NOT_OWNER`, and `POLICY_UNAVAILABLE` must remain stable for tests and dashboards rather than comparing human-language strings. Never place userId/resourceId into high-cardinality metric labels; store them in an access-controlled audit store.

## 4. Where in Spring Security Should You Collect Events?

### 4.1. Framework Authorization Events

Spring Security provides `AuthorizationEventPublisher` and two events: `AuthorizationDeniedEvent` and `AuthorizationGrantedEvent`. In Spring Security 6.5, `SpringAuthorizationEventPublisher` builds on Spring's `ApplicationEventPublisher`; **by default it publishes only deny events**, whereas grant events require deliberate publishing due to high volume. These events appear only on authorization paths wired with the publisher and do not automatically cover every custom policy call or error branch.

In a security-enabled `@Configuration`, you can register:

~~~java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher events) {
    return new SpringAuthorizationEventPublisher(events);
}
~~~

Relevant imports: `org.springframework.context.ApplicationEventPublisher`, `org.springframework.security.authorization.AuthorizationEventPublisher`, `org.springframework.security.authorization.SpringAuthorizationEventPublisher`, `org.springframework.context.annotation.Bean`.

The listener is an **integration snippet**, requiring a project-implemented `AuditSink` and business-layer correlation:

~~~java
@Component
class AuthorizationDeniedListener {

    private final AuditSink auditSink;

    AuthorizationDeniedListener(AuditSink auditSink) {
        this.auditSink = auditSink;
    }

    @EventListener
    void onDenied(AuthorizationDeniedEvent<?> event) {
        if (!event.getAuthorizationResult().isGranted()) {
            Object securedObject = event.getObject();
            String targetKind = securedObject == null
                    ? "UNKNOWN"
                    : securedObject.getClass().getSimpleName();

            // Do not log toString() of request / MethodInvocation.
            auditSink.offerDenied("SPRING_AUTHZ", targetKind);
        }
    }
}
~~~

Import `@Component`, `@EventListener`, and `AuthorizationDeniedEvent` from Spring. This listener does not yet produce the complete audit schema: `AuditSink` needs correlation IDs, policy version, and resource references from trusted request/policy context. Avoid long blocking network calls inside listeners. The `getAuthorizationResult()` API belongs to 6.4+; for 6.3 and 7.x, verify the version-specific Javadoc.

**Scope trap:** `AuthorizationDeniedEvent` does not fire when a request misses every `SecurityFilterChain`, when a service is invoked outside an AOP proxy, or when a custom policy throws an exception before emitting an event. If audits must cover those cases, add instrumentation there along with coverage tests.

### 4.2. Domain-Policy Auditing to Record PERMIT, ABSTAIN, ERROR

For resource-level permissions (`document.approve`, `invoice.pay`), instrument inside the policy evaluator where action, resource, tenant, rule ID, and version are known. Suggested contract:

~~~text
PolicyInput(identity, action, resource, contextVersion)
      │
      ▼
evaluate() -> PolicyEvaluation(decision, reasonCode, policyVersion)
      │                    └── exception -> ERROR
      ▼
record sanitized audit(eventId, decisionId, traceId, ...)
      │
      ▼
enforce final policy (including abstain fallback and error handling)
      │
      ▼
record business outcome AFTER commit/rollback
~~~

Evaluate the **policy exactly once** per attempt, then record that exact result; never invoke the policy a second time just to “audit” because ACL data may change or evaluation may have side effects. On exceptions, log a generic reason code and let exception handling proceed per policy; never turn errors into PERMIT. If downstream audit fails, fallback/durability strategy must follow security requirements rather than emerging accidentally from listener errors.

### 4.3. HTTP, Method, and DB Share One Trace Yet Emit Distinct Events

- HTTP `AuthorizationFilter` evaluates `authorizeHttpRequests` rules. An HTTP permit does not prove the business method is allowed.
- `@PreAuthorize`/`@PostAuthorize` use AOP method security. With `@PostAuthorize`, the body may already have run before denial; check side effects separately.
- Domain ACLs may rely on ownership, tenant, resource state, and DB grant version; record minimal references sufficient to reproduce.
- DB `COMMITTED` outcomes must be observed after actual commit via transaction hooks/outbox if reliable evidence is required. A pre-transaction PERMIT event does not prove the transaction succeeded.

## 5. Golden Permission Matrix: A Benchmark Independent of Legacy Code

The matrix must be approved by business and security owners, carrying `scenarioId`, expected decision, identity/tenant/resource/action inputs, and fixture version. Never treat legacy policy output as golden because it can legitimize bugs.

Hypothetical document system table:

| ID | Principal | Action | Resource Context | Expected Decision | Enforced | Business Calls |
| --- | --- | --- | --- | --- | --- | --- |
| `A01` | Anonymous | PUBLIC_READ | Public document | PERMIT | PROCEED | 1 |
| `A02` | Alice/STAFF | PRIVATE_READ | Owner, same tenant | PERMIT | PROCEED | 1 |
| `A03` | Anonymous | PRIVATE_READ | Private document | DENY | BLOCK | 0 |
| `A04` | Alice/STAFF | PRIVATE_READ | Cross-tenant even with owner=true | DENY | BLOCK | 0 |
| `A05` | Alice/STAFF | PRIVATE_READ | Not owner | DENY | BLOCK | 0 |
| `A06` | Alice/REVIEWER | APPROVE | Same tenant, DRAFT | PERMIT | PROCEED | 1 |
| `A07` | Alice/STAFF | APPROVE | Same tenant, DRAFT | DENY | BLOCK | 0 |
| `A08` | Alice/REVIEWER | APPROVE | Same tenant, PUBLISHED | DENY | BLOCK | 0 |
| `A09` | Alice | UNSUPPORTED | No matching rule | ABSTAIN | BLOCK per fixture fallback | 0 |
| `A10` | Alice/REVIEWER | APPROVE | Policy service unavailable | ERROR | BLOCK per failure policy | 0 |

`A09`/`A10` test the distinction between **policy result** and **enforcement behavior**. The fixture defaults to blocking ABSTAIN/ERROR; this is an intentional illustrative policy, not a claim that every Spring Security interceptor handles `null` that way.

A test must check **expected vs. actual policy**, **enforced outcome**, **side effects**, and **audit correlation/count**. For multi-layer permission matrices, do not force one HTTP request to emit exactly one audit: a single request can traverse multiple policies.

## 6. Standalone Java 17: Checking 10 Decisions and 10 Audit Records

This example uses only JDK 17. It creates no HTTP server or DB; it simulates document permission policies, records in-memory audits, checks against golden expectations, and counts business calls. Fixed data keeps stdout exact.

Create file **`AuthorizationAuditEvidenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class AuthorizationAuditEvidenceDemo {

    enum Action { PUBLIC_READ, PRIVATE_READ, APPROVE, UNSUPPORTED }
    enum Decision { PERMIT, DENY, ABSTAIN, ERROR }

    record Scenario(
            String id, Action action, boolean authenticated,
            String actorTenant, String resourceTenant,
            boolean owner, boolean reviewer, boolean draft,
            boolean policyAvailable, Decision expected) {}

    record PolicyResult(Decision decision, String reasonCode) {}

    record AuditEvent(
            String eventId, String decisionId, String traceId,
            String scenarioId, String policyVersion,
            Decision decision, String enforcement, String reasonCode) {}

    static PolicyResult evaluate(Scenario s) {
        if (!s.policyAvailable()) {
            return new PolicyResult(Decision.ERROR, "POLICY_UNAVAILABLE");
        }
        if (s.action() == Action.UNSUPPORTED) {
            return new PolicyResult(Decision.ABSTAIN, "NO_MATCHING_RULE");
        }
        if (s.action() == Action.PUBLIC_READ) {
            return new PolicyResult(Decision.PERMIT, "PUBLIC_RESOURCE");
        }
        if (!s.authenticated()) {
            return new PolicyResult(Decision.DENY, "AUTH_REQUIRED");
        }
        if (!Objects.equals(s.actorTenant(), s.resourceTenant())) {
            return new PolicyResult(Decision.DENY, "TENANT_MISMATCH");
        }
        return switch (s.action()) {
            case PRIVATE_READ -> s.owner()
                    ? new PolicyResult(Decision.PERMIT, "OWNER_MATCH")
                    : new PolicyResult(Decision.DENY, "NOT_OWNER");
            case APPROVE -> !s.reviewer()
                    ? new PolicyResult(Decision.DENY, "REVIEWER_REQUIRED")
                    : !s.draft()
                        ? new PolicyResult(Decision.DENY, "NOT_DRAFT")
                        : new PolicyResult(Decision.PERMIT, "REVIEWER_DRAFT");
            case PUBLIC_READ, UNSUPPORTED ->
                    throw new IllegalStateException("Handled above");
        };
    }

    public static void main(String[] args) {
        List<Scenario> cases = List.of(
            new Scenario("A01", Action.PUBLIC_READ, false, null, "acme",
                    false, false, false, true, Decision.PERMIT),
            new Scenario("A02", Action.PRIVATE_READ, true, "acme", "acme",
                    true, false, false, true, Decision.PERMIT),
            new Scenario("A03", Action.PRIVATE_READ, false, null, "acme",
                    false, false, false, true, Decision.DENY),
            new Scenario("A04", Action.PRIVATE_READ, true, "acme", "beta",
                    true, false, false, true, Decision.DENY),
            new Scenario("A05", Action.PRIVATE_READ, true, "acme", "acme",
                    false, false, false, true, Decision.DENY),
            new Scenario("A06", Action.APPROVE, true, "acme", "acme",
                    false, true, true, true, Decision.PERMIT),
            new Scenario("A07", Action.APPROVE, true, "acme", "acme",
                    false, false, true, true, Decision.DENY),
            new Scenario("A08", Action.APPROVE, true, "acme", "acme",
                    false, true, false, true, Decision.DENY),
            new Scenario("A09", Action.UNSUPPORTED, true, "acme", "acme",
                    false, false, false, true, Decision.ABSTAIN),
            new Scenario("A10", Action.APPROVE, true, "acme", "acme",
                    false, true, true, false, Decision.ERROR)
        );

        List<AuditEvent> audit = new ArrayList<>();
        Set<String> seenDecisions = new HashSet<>();
        int businessCalls = 0;
        int passed = 0;
        String version = "doc-authz-v17";

        for (Scenario s : cases) {
            PolicyResult result = evaluate(s);
            boolean proceed = result.decision() == Decision.PERMIT;

            AuditEvent event = new AuditEvent(
                    "evt-" + s.id(),
                    "decision-" + s.id(),
                    "trace-" + s.id(),
                    s.id(),
                    version,
                    result.decision(),
                    proceed ? "PROCEED" : "BLOCK",
                    result.reasonCode());
            audit.add(event);

            if (!seenDecisions.add(event.decisionId())) {
                throw new AssertionError("Duplicate decisionId");
            }
            if (!event.traceId().equals("trace-" + s.id())
                    || !event.scenarioId().equals(s.id())
                    || !event.policyVersion().equals(version)) {
                throw new AssertionError("Missing correlation");
            }
            if (result.decision() != s.expected()
                    || proceed != (s.expected() == Decision.PERMIT)) {
                throw new AssertionError("Regression failed: " + s.id());
            }

            // Simulates a protected business call.
            if (proceed) {
                businessCalls++;
            }
            passed++;
            System.out.printf("%s | %s | %s | %s%n",
                    s.id(), event.decision(),
                    event.enforcement(), event.reasonCode());
        }

        if (audit.size() != cases.size() || businessCalls != 3) {
            throw new AssertionError("Incomplete audit or wrong side effects");
        }
        System.out.println("Golden regression: " + passed + "/10");
        System.out.println("Audit events: " + audit.size());
        System.out.println("Business calls: " + businessCalls);
    }
}
~~~

Run command:

~~~bash
javac -encoding UTF-8 AuthorizationAuditEvidenceDemo.java
java AuthorizationAuditEvidenceDemo
~~~

**Exact** expected stdout:

~~~text
A01 | PERMIT | PROCEED | PUBLIC_RESOURCE
A02 | PERMIT | PROCEED | OWNER_MATCH
A03 | DENY | BLOCK | AUTH_REQUIRED
A04 | DENY | BLOCK | TENANT_MISMATCH
A05 | DENY | BLOCK | NOT_OWNER
A06 | PERMIT | PROCEED | REVIEWER_DRAFT
A07 | DENY | BLOCK | REVIEWER_REQUIRED
A08 | DENY | BLOCK | NOT_DRAFT
A09 | ABSTAIN | BLOCK | NO_MATCHING_RULE
A10 | ERROR | BLOCK | POLICY_UNAVAILABLE
Golden regression: 10/10
Audit events: 10
Business calls: 3
~~~

**Interpretation:** A04 denies despite owner flag true thanks to the tenant check. A06 permits when reviewer and document is draft. A09 records ABSTAIN while the **demo** fallback blocks, and A10 records ERROR separately. There are 10 decision audits and three simulated business calls. The demo does not guarantee audit storage or transactions of a real system; if a real policy throws an exception, the adapter must record ERROR and propagate/fail-safe per policy. The demo uses fixed `eventId` per case for easy stdout verification; production requires a unique ID per emission, including distinct retries/attempts, plus an appropriate dedup mechanism.

## 7. End-to-End Regression Testing with Spring Security

### 7.1. Test Configuration

In a Spring Boot 3.5.x project already using the Spring plugin/BOM, add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

For services, enable `@EnableMethodSecurity` and invoke through a **Spring-managed proxy**; calling `new ServiceImpl()` directly or `this.securedMethod()` can bypass AOP interceptors. For HTTP endpoints, use `MockMvc` and `spring-security-test` to ensure requests traverse the security filter chain.

**An illustrative test snippet** — requires `@SpringBootTest`, `@AutoConfigureMockMvc`, controller, DB fixture, `MockMvc`, and static imports:

~~~java
// Document D-42 belongs to tenant beta; this principal belongs to tenant acme.
mockMvc.perform(post("/api/documents/D-42/approve")
        .with(user("reviewer").roles("REVIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());

// The same test must verify:
// - document D-42 is not mutated and message count = 0;
// - audit records DENY/TENANT_MISMATCH with the right policyVersion;
// - decisionId/traceId are bound to the request and test case;
// - no call path bypasses method security.
~~~

`with(user())` creates only test principal/authorities; **it does not automatically grant a tenant**. Tenants must come from trusted sources and real fixtures. For POSTs using browser/session, the CSRF token must be valid; for bearer-only APIs, configure CSRF per threat model rather than disabling it wholesale to make tests pass.

### 7.2. Required Test Layers

| Layer | What to Verify |
| --- | --- |
| Unit policy | `PERMIT/DENY/ABSTAIN/ERROR`, reason, tenant, ownership, role, state |
| Spring component | `AuthorizationManager`, publisher/listener, `@PreAuthorize` via proxy, exception mapping |
| HTTP integration | `SecurityFilterChain`, authentication, status, CSRF, matcher/order, request methods |
| Business integration | DB state, transactions, message/external side effects, commit/rollback |
| Evidence contract | Schema/correlation, audit count, policy version, artifact link/hash |
| Performance/failure | Full queue, failing audit sink, retries, dedupe, latency, and backpressure |

Never use HTTP status as sole proof of authorization. A CSRF failure can produce 403 before the intended rule; a request matching no chain can return 404 from MVC without any protection. Tests must identify the exact policy checkpoint that executed.

### 7.3. Critical Additional Matrix Cases

- Anonymous/public/private, locked user, missing authority, and differing role prefixes (`ROLE_ADMIN` vs. `ADMIN`).
- Cross-tenant even when owner flag or role matches; resource transferred between tenants/owners.
- Stale permission caches, revoked ACLs, policy/version changing between check and commit.
- `@PostAuthorize` denying after the body ran; test real side effects.
- Narrow `securityMatcher("/api/**")` chains leaving endpoints outside `/api/**` uncovered by any filter chain.
- One request triggering multiple advisors; audit must show multiple `decisionId`s under one trace.
- Policy abstaining or throwing exceptions, failing audit pipelines, and fail-closed/continue contracts.
- Concurrency, retries, and asynchronous requests: correlation must not mix two principals; eventId/attemptId must never collide accidentally.
- Migrating `authorizeRequests` to `authorizeHttpRequests` or voters to `AuthorizationManager`: golden expectations must never come from potentially flawed legacy outputs.

## 8. Assembling a Reviewable Evidence Bundle

A review dossier must connect **scenario → policy version → decision → enforcement → HTTP/side effects → test results → artifacts**.

~~~text
evidence/
  manifest.json             # build, source revision, testRunId, policy/matrix version
  golden-matrix.json        # input/expected/approval reference
  results.json              # actual decision and pass/fail by scenario
  audit-events.ndjson       # sanitized decisions, correlation IDs
  http-results.json         # response status and business observations
  coverage.json             # filter-chain and method-security checks
  checksums.sha256          # hashes over actual finalized artifact bytes
~~~

Example `manifest.json` with illustrative data:

~~~json
{
  "schemaVersion": 1,
  "testRunId": "integration-run-42",
  "gitRevision": "example-commit-id",
  "policyVersion": "doc-authz-v17",
  "matrixVersion": "matrix-v5",
  "javaRuntime": "17",
  "springSecurityLine": "6.5",
  "environment": "integration",
  "expectedScenarios": 10,
  "passedScenarios": 10,
  "auditEventCount": 10,
  "checksums": "checksums.sha256"
}
~~~

Never self-declare `passedScenarios`: CI must extract counts from the test runner and verify real numbers and schemas. SHA-256 hashes of files are computed **after finalization** to verify byte integrity. Hashes do not prove origin, so where tamper resistance is required, use trusted signatures/provenance and access-controlled immutable storage. Synchronize clocks well enough to align timelines while relying on trace/decision IDs rather than timestamps alone.

A linked record should allow querying:

~~~text
scenarioId=A04
  ├─ expected=DENY (matrix-v5, owner-approved)
  ├─ policyVersion=doc-authz-v17 (gitRevision)
  ├─ decisionId=decision-A04, reason=TENANT_MISMATCH
  ├─ traceId=trace-A04, enforce=BLOCK
  ├─ HTTP=403; document not updated; message count=0
  └─ regression test PASS; audit schema PASS; artifact checksums
~~~

Never stitch together logs from different test runs/fixtures to fabricate a cohesive story. When sensitive data cannot be exported, store references to the fixture version/DB snapshot inside an authorized test environment and document how to reproduce.

### Recommended Acceptance Gates

| Gate | Condition |
| --- | --- |
| Permissions | Critical golden cases pass; unexpected PERMIT = 0 |
| Side effects | DENY/ERROR do not write DB or emit messages; ABSTAIN applies the right fallback |
| Audit | Required events present for mandatory policy points, no missing correlation/version |
| Coverage | HTTP filter chain/method proxies tested; no sensitive route missed |
| Data safety | Audits contain no tokens, secrets, or raw PII; retention complies |
| Integrity | Checksums/provenance verified and stored with proper permissions |
| Operations | Audit sink/backpressure/retries failure-tested; authorization latency within SLO |

Zero diff after changing a policy **does not automatically prove safety**: if the golden expectations were wrong, two overly permissive versions will still “match.” Changes to expected outcomes require explicit approval and versioning.

## 9. Operating Audits: Complete, Secure, Low Performance Impact

### 9.1. Storage Strategy and Sink Failures

Synchronous network/DB writes on every request can spike p99 authorization latency and cause outages when the audit sink slows down. For ordinary events, use buffers/queues with backpressure and metrics; for sensitive actions requiring guaranteed audits, specify exact durability requirements (possibly requiring a transactional outbox or deliberate fail-closed). Never let an exception from an audit listener accidentally turn a `DENY` into a `PERMIT`. When the sink is down, track rejected queue enqueues and backlog; never pretend writes succeeded.

If a business action commits, audit the outcome after commit via appropriate transaction hooks/outbox. Recording `COMMITTED` before DB commit creates false evidence. On retries, distinguish attempt IDs from logical operation IDs; never drop valid events due to faulty deduplication.

### 9.2. Privacy and Integrity

Audit stores need RBAC, encryption in transit/at rest, retention policies, export/view workflows, and access logs for auditors. Never record full tokens, cookies, raw method arguments, full request bodies, or stack traces containing PII. Plain SHA-256 pseudonymization over guessable emails is vulnerable to dictionary attacks; use keyed pseudonymization like HMAC with proper key management when appropriate. Resource identifiers can still be sensitive data even when they are not emails.

### 9.3. Observability and Alerting

Track bounded-cardinality metrics such as:
- `authz_decisions_total{decision,policy,reason_group}` and `authz_decision_duration_seconds`.
- `audit_enqueue_failures_total`, queue age/depth, DLQ, and lag to storage.
- `regression_unexpected_permit_total`, policy errors, missing correlations, coverage failures.
- Deny/permit ratios by action type/tenant class if consistent with security and cardinality constraints.

Never put userId/resourceId into metric labels. Alert on sustained audit loss, backlog thresholds, rising policy errors, missing traces, or any critical golden case unexpectedly returning PERMIT.

## 10. Common Mistakes

1. **Logging only HTTP 403.** Misses rule/tenant/version and side effects; add policy-level audits.
2. **Assuming granted events are always published.** Spring's default publisher emits denials only; grants need explicit config and overhead budgeting.
3. **Logging raw `Authentication` or requests.** Risks exposing tokens, bodies, and PII; design an allowlist schema.
4. **Assuming one decisionId per request.** One trace can hold multiple decisions across HTTP/method/domain layers.
5. **Collapsing ABSTAIN/ERROR into DENY.** Loses policy boundaries and diagnostic details; record evaluation and final outcome separately.
6. **Asserting only 401/403 status in tests.** Failures might come from CSRF/entry points; assert decisions and side effects.
7. **Calling services outside the Spring proxy.** Method security is bypassed, yielding false-green tests.
8. **Using the old policy as the golden benchmark.** Can preserve tenant/owner flaws from earlier versions.
9. **Logging PERMIT and claiming COMMITTED.** Transactions can roll back; audit outcomes after commit.
10. **Ignoring full queues/failing audit sinks.** Creates missing evidence and stalls requests; define failure policies.
11. **Having enough event counts without policyVersion/fixture.** Cannot prove decisions came from the right code version.
12. **Treating hashes as proof of origin.** Hashes verify byte integrity only; provenance is a separate concern.
13. **Putting userId/resourceId into metric labels.** Causes cardinality explosion.
14. **Enforcing exactly one audit event per request.** A request can evaluate multiple decisions or hit routes outside an event emitter.

## 11. Completion Checklist

- [ ] Golden matrix has independent expected outcomes, scenario IDs, approvers, and version.
- [ ] Every policy evaluation records decisionId, traceId, policy/rule ID, and normalized actor/action/resource.
- [ ] Audits distinguish `PERMIT/DENY/ABSTAIN/ERROR` from `PROCEED/BLOCK` and business outcomes.
- [ ] Security chain coverage, AOP proxies, authentication, HTTP statuses, and side effects are verified.
- [ ] Regression covers cross-tenant, roles, owners, disabled users, stale data, nulls, and exceptions.
- [ ] Framework events understood: denials by default, grants not automatic; extra instrumentation added for other branches.
- [ ] Audit data is sanitized, with RBAC, retention, and export controls.
- [ ] Audit sink has retries/queues/alerts and tested failure policies.
- [ ] Evidence bundle links case → policy → decision → response/DB → test → artifact hash.
- [ ] CI enforces unexpected PERMIT = 0 on critical cases and verifies checksums/provenance as required.

## 12. References

- [Spring Security 6.5 — Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): registering `AuthorizationEventPublisher`, denials, and grants.
- [Spring Security 6.5 — AuthorizationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html): `AuthorizationResult` and event contract.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and interceptors.
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` and matchers.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): `MockMvc`, `spring-security-test`, and enforcement testing.
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): trace/span correlation and observability standardization.

**Final result of authorization testing is a trustworthy chain of evidence:** right actor, right action, right resource, right policy version; decision enforced, side effects verified, and audits traceable.
