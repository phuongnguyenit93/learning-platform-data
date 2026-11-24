# Phased Authorization Migration Using a Permission Matrix as the Regression Standard

## 1. Why Does an Authorization Migration Need a Regression Standard?

When changing Spring Security — such as migrating from `authorizeRequests` and `AccessDecisionVoter` to `authorizeHttpRequests`/`AuthorizationManager`, splitting multiple `SecurityFilterChain`s, altering role mappings, or moving permission checks from controllers into services — code can compile and endpoints can still return 200 while **access semantics have changed**. A critical bug is granting extra permissions to a user unintentionally, even when every existing unit test passes.

The solution is creating an **approved permission matrix** prior to migration. Each row describes a realistic scenario with enough data to evaluate, along with a **golden expected decision**. We use that matrix to run the old policy, the new policy, and HTTP/method security tests across multiple phases. The old policy's outcome serves as a **baseline for comparison**, not automatically as truth: if the old policy had a vulnerability, the golden matrix must capture the right behavior agreed upon by business and security owners.

After this lesson, you will be able to:
- Build a golden matrix covering user/role/authority, tenant, resource, action, state, authentication status, and negative branches.
- Break migration into phases with entry/exit gates, passive comparison mechanisms, canarying, rollback, and retirement of legacy paths.
- Distinguish **tightened permissions**, **widened permissions**, and **approved legitimate differences**.
- Create a runnable regression gate in Java 17, then extend it to Spring Security `MockMvc` and method security.
- Avoid drift caused by matchers, filter chain ordering, `hasRole`/`hasAuthority`, anonymous users, CSRF, proxies, and resource data.

**Scope:** Spring Security on Servlet/MVC, focusing on HTTP and method authorization policies. For WebFlux, apply the same matrix/regression methodology using `SecurityWebFilterChain`, `ServerHttpSecurity`, and appropriate test tools.

## 2. Lock Down Semantics Before Locking Down Implementation

### 2.1. What fields should a matrix row carry?

| Field | Test Question |
| --- | --- |
| `scenarioId` and approval source | Who defined the expectation? Which requirement/ADR/policy version? |
| Identity / authentication | Anonymous, authenticated user, which principal, which issuer/tenant? |
| Authority/role | `ROLE_REVIEWER`, `SCOPE_documents.read`, or an internal permission? |
| Target / action | `GET /documents/{id}`, `POST /documents/{id}/approve`, or `approve` method? |
| Resource context | Owner, tenant, state `DRAFT`/`PUBLISHED`, sensitivity level |
| Logical expectation | `PERMIT`, `DENY`; if API has abstain/error, separate them as distinct states |
| HTTP expectation | 200/201, 401/403, or controlled error depending on authentication mechanism |
| Side effects | Should DB writes, messages, or outbound API calls happen? |
| Priority/risk | Admin, cross-tenant, sensitive data, public endpoint |
| Version and validity | Which policy version, fixture/snapshot/clock produced the decision? |

**Do not treat URL and role alone as the entire test case.** Ownership, tenant, and business-state permissions can differ for two requests hitting the same endpoint. For endpoints with differing bodies/queries/path variables or HTTP methods, add corresponding dimensions to the matrix.

### 2.2. Illustrative matrix for a document system

Suppose the system has approved rules:

1. `PUBLIC_READ` is open to everyone.
2. `PRIVATE_READ` is allowed only for logged-in users who are the owner and in the same tenant as the document.
3. `APPROVE` is allowed only for logged-in users with role `REVIEWER`, in the same tenant as the document, while the document is still `DRAFT`.
4. All other cases are denied. System roles do not automatically grant cross-tenant access.

| ID | Principal / Role | Action | User → Document Tenant | Context | Golden |
| --- | --- | --- | --- | --- | --- |
| `P01` | Anonymous | PUBLIC_READ | N/A | Public document | PERMIT |
| `P02` | Anonymous | PRIVATE_READ | — → acme | Owner=false | DENY |
| `P03` | alice / STAFF | PRIVATE_READ | acme → acme | Owner=true | PERMIT |
| `P04` | alice / STAFF | PRIVATE_READ | acme → beta | Owner=true in fixture | **DENY** |
| `P05` | reviewer / REVIEWER | APPROVE | acme → acme | DRAFT | PERMIT |
| `P06` | reviewer / REVIEWER | APPROVE | acme → beta | DRAFT | **DENY** |
| `P07` | reviewer / REVIEWER | APPROVE | acme → acme | PUBLISHED | DENY |
| `P08` | staff / STAFF | APPROVE | acme → acme | DRAFT | DENY |
| `P09` | bob / STAFF | PRIVATE_READ | acme → acme | Owner=false | DENY |

Rows `P04` and `P06` are deliberately designed to catch a **cross-tenant permission leak** in an old policy that only checked owner/role while forgetting tenant. These are valid golden expectations per approved business policy, even though a legacy implementation might return PERMIT.

Beyond the rows above, a real system needs nonexistent routes, other HTTP methods, missing authorities, disabled users, deleted resources, changed owners, annotations on other methods, `ERROR/FORWARD` requests, and requests falling outside all security filter chains. Negative cases must be thorough enough to uncover unintended permission widening.

### 2.3. Aligning three layers of expectations

~~~text
Golden business decision (PERMIT / DENY / ERROR / ABSTAIN if applicable)
           │
           ├── policy-level test: AuthorizationManager / domain policy
           │
           ├── method-level test: proxy / @PreAuthorize / method invocation
           │
           └── HTTP-level test: SecurityFilterChain + authentication
                                 + exception translation + controller/side effect
~~~

A logical `DENY` can become **401** if the client is unauthenticated and `AuthenticationEntryPoint` issues a login challenge, or **403** if authenticated yet lacking permission. Do not use HTTP 401/403 status codes as a substitute for verifying the logical decision, and do not force fixed statuses when intentionally changing authentication mechanisms. `CSRF`, path matchers, or gateways can also produce 403/404 before the policy is ever invoked.

## 3. Phased Migration Process

| Phase | Tasks | Exit Criteria |
| --- | --- | --- |
| **0. Inventory** | List all `SecurityFilterChain`s, request matchers, role mappings, method security, custom voters/managers, actuators, and entry points | Know which policy governs every endpoint/method; no "unknown zones" left |
| **1. Golden freeze** | Review matrix with business/security owners; record `policyVersion`, dataset, source, and expectations | All critical scenarios have positive/negative/cross-tenant cases; matrix is version-controlled |
| **2. Baseline** | Run old policy against golden, classify known gaps; produce initial report | All legacy gaps addressed or covered by time-bound remediation/waiver decisions |
| **3. Build candidate** | Implement new `AuthorizationManager`/DSL; test against matrix at domain, method, and HTTP layers | Candidate passes golden with zero unexpected PERMITs |
| **4. Shadow compare** | Old policy enforces; new policy evaluates **passively** on identical safe input/snapshot | Diffs classified; zero duplicate writes executed; overhead within budget |
| **5. Canary** | Enable new policy for selected users/tenants/traffic via approved rollout mechanism | Zero unauthorized grants; error/latency/deny anomalies within thresholds |
| **6. Expand** | Gradually broaden candidate activation while monitoring real permissions and rollback gates | Safety criteria met in every observation window |
| **7. Retire** | Remove legacy code/policies once backed by evidence; retain golden tests, audits, and playbooks | No legacy execution paths or ambiguous duplicate matchers remain |

Do not interpret shadow comparison as "letting both policies drive the same request." **Only one policy decides whether the request proceeds**; the other merely observes. Never replay POST/approve/transfer requests to compare permissions; shadow evaluation must call a side-effect-free decision function on the same data snapshot, or log drift caused by data changing between evaluations.

### 3.1. Preserving the baseline in every phase

Store together in the same revision:
- Golden permission matrix with stable IDs, approval sources, expectations, and risk levels.
- Old and new policy code (commit/version), flag/route configurations, and standard fixture data.
- CI report: scenario ID, expected, actual legacy, actual candidate, and diff root cause.
- Release gate: unexpected permits = 0, critical scenarios 100% pass, latency/canary thresholds, and rollback owner.

When intentionally granting additional permissions, **never update golden expectations merely to turn tests green**. File an approved change request, add tests for the new permission scope and impact boundaries, and preserve golden change history between before/after versions.

### 3.2. Classifying diffs

| Legacy | Candidate | Golden | Interpretation |
| --- | --- | --- | --- |
| PERMIT | DENY | DENY | **Fixes legacy vulnerability**; valid diff if approved |
| DENY | PERMIT | PERMIT | **Policy-aligned expansion**; still requires approval since permissions increased |
| PERMIT | DENY | PERMIT | Regression removing legitimate access |
| DENY | PERMIT | DENY | **Unexpected privilege expansion**; block rollout |
| PERMIT | PERMIT | DENY | Both policies wrong; diff = 0 does not mean safe |
| DENY | DENY | PERMIT | Both deny legitimate access; fix before release |

Hence there are at least two independent test gates: **candidate-vs-golden** and **old-vs-candidate**. A diff of 0 only shows the two implementations agree on tested cases—not that they are right or that the matrix has sufficient coverage.

## 4. Standalone Java 17: Regression Gate from a Golden Matrix

To illustrate the mechanism without booting Spring Boot, the example below implements two plain Java policies: legacy omits the tenant check, while candidate enforces it. Every row carries `expectedPermit` independent of implementation code. When executed, the program counts mismatches and **throws AssertionError if the candidate violates golden**. Fixture data is strictly educational, not a production authorization system.

Create file **`PermissionMatrixMigrationDemo.java`**:

~~~java
import java.util.List;

public final class PermissionMatrixMigrationDemo {

    enum Action { PUBLIC_READ, PRIVATE_READ, APPROVE }

    record Scenario(
            String id,
            String principal,
            String role,
            String callerTenant,
            String documentTenant,
            boolean owner,
            boolean draft,
            Action action,
            boolean expectedPermit) {}

    // Simulates faulty legacy policy: missing tenant check.
    static boolean legacy(Scenario s) {
        if (s.action() == Action.PUBLIC_READ) {
            return true;
        }
        if (s.principal() == null) {
            return false;
        }
        return switch (s.action()) {
            case PUBLIC_READ -> true;
            case PRIVATE_READ -> s.owner();
            case APPROVE -> "REVIEWER".equals(s.role()) && s.draft();
        };
    }

    // New policy: preserves valid access, blocks cross-tenant access.
    static boolean candidate(Scenario s) {
        if (s.action() == Action.PUBLIC_READ) {
            return true;
        }
        if (s.principal() == null
                || s.callerTenant() == null
                || !s.callerTenant().equals(s.documentTenant())) {
            return false;
        }
        return switch (s.action()) {
            case PUBLIC_READ -> true;
            case PRIVATE_READ -> s.owner();
            case APPROVE -> "REVIEWER".equals(s.role()) && s.draft();
        };
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Scenario> golden = List.of(
            new Scenario("P01", null, null, null, "acme",
                    false, false, Action.PUBLIC_READ, true),
            new Scenario("P02", null, null, null, "acme",
                    false, false, Action.PRIVATE_READ, false),
            new Scenario("P03", "alice", "STAFF", "acme", "acme",
                    true, false, Action.PRIVATE_READ, true),
            new Scenario("P04", "alice", "STAFF", "acme", "beta",
                    true, false, Action.PRIVATE_READ, false),
            new Scenario("P05", "reviewer", "REVIEWER", "acme", "acme",
                    false, true, Action.APPROVE, true),
            new Scenario("P06", "reviewer", "REVIEWER", "acme", "beta",
                    false, true, Action.APPROVE, false),
            new Scenario("P07", "reviewer", "REVIEWER", "acme", "acme",
                    false, false, Action.APPROVE, false),
            new Scenario("P08", "staff", "STAFF", "acme", "acme",
                    false, true, Action.APPROVE, false),
            new Scenario("P09", "bob", "STAFF", "acme", "acme",
                    false, false, Action.PRIVATE_READ, false)
        );

        int legacyMismatches = 0;
        int candidateMismatches = 0;
        int unexpectedPermits = 0;

        for (Scenario s : golden) {
            boolean oldDecision = legacy(s);
            boolean newDecision = candidate(s);
            if (oldDecision != s.expectedPermit()) {
                legacyMismatches++;
            }
            if (newDecision != s.expectedPermit()) {
                candidateMismatches++;
                System.err.println("GOLDEN MISMATCH: " + s.id());
            }
            if (newDecision && !s.expectedPermit()) {
                unexpectedPermits++;
            }
        }

        System.out.println("Scenarios: " + golden.size());
        System.out.println("Legacy mismatches: " + legacyMismatches);
        System.out.println("Candidate mismatches: " + candidateMismatches);
        System.out.println("Candidate unexpected permits: " + unexpectedPermits);

        require(legacyMismatches == 2,
                "Fixture should expose two legacy tenant bugs");
        require(candidateMismatches == 0,
                "Candidate does not match approved golden matrix");
        require(unexpectedPermits == 0,
                "Unexpected permission expansion");
        System.out.println("Regression gate: PASS");
    }
}
~~~

Run in a directory with JDK 17+:

~~~bash
javac -encoding UTF-8 PermissionMatrixMigrationDemo.java
java PermissionMatrixMigrationDemo
~~~

**Exact stdout**:

~~~text
Scenarios: 9
Legacy mismatches: 2
Candidate mismatches: 0
Candidate unexpected permits: 0
Regression gate: PASS
~~~

Explanation: legacy fails at `P04` and `P06` because it permits cross-tenant access; candidate keeps valid cases working and blocks both leaks. `Legacy mismatches: 2` is **not** a gate failure in this fixture because those are previously detected and recorded legacy bugs. In a real system, only an approved waiver/remediation allows proceeding—never hardcode `2` to ignore arbitrary old bugs.

This is a two-valued PERMIT/DENY logic engine. In real Spring Security, managers can return `null` (abstain) or throw exceptions. **Do not coerce abstain into deny/permit and do not treat policy errors as missing permissions**; model result types, fallbacks, and error policies per API/policy version and add dedicated rows to the golden matrix.

## 5. Moving Into Spring Security While Preserving Exact Outcomes

### 5.1. Changes that easily distort policy

| Topic | Migration Risk | Testing Action |
| --- | --- | --- |
| `authorizeRequests` → `authorizeHttpRequests` | Moving from `FilterSecurityInterceptor`/voters to `AuthorizationFilter`/`AuthorizationManager` can alter custom logic semantics | Golden cases for grant/deny/abstain, custom expressions, and exceptions |
| `securityMatcher` vs `requestMatchers` | `securityMatcher` scopes **the whole chain**; `anyRequest` applies only inside the selected chain | Test chain coverage, routes outside `/api/**`, and catch-all |
| Multiple `SecurityFilterChain`s | First matching chain is chosen; chains are not combined | Test `@Order` and matchers per servlet path/method |
| `hasRole` vs `hasAuthority` | `hasRole("ADMIN")` normally checks authority `ROLE_ADMIN`; `hasAuthority` checks exact string | Test role prefixes, JWT authorities, and custom `GrantedAuthoritiesMapper` |
| `@EnableMethodSecurity`/proxies | Methods may be invoked via `this.` bypassing proxies; multiple annotations/advisors may stack | Test service beans via Spring context, both intra-class and from external callers |
| `@PreAuthorize` vs `@PostAuthorize` | Pre- and post-method checks differ in timing; post-check does not stop prior side effects | Test outputs and before/after side effects |
| Anonymous / remember-me / session | `authenticated()` and `fullyAuthenticated()` have distinct meanings | Test anonymous, authenticated, remember-me, and session timeouts if used |
| CSRF / HTTP methods | POST returns 403 for missing CSRF despite valid permissions, or GET does not represent POST | Test HTTP methods, CSRF tokens per client architecture, and real HTTP responses |
| `permitAll` vs `web.ignoring` | `ignoring` skips security filters and may omit security headers | Test security chain and headers on public routes |
| Default/fallback rules | New URLs or management paths fall outside all chains, or `permitAll` is overly broad | Test endpoint inventory and `anyRequest().denyAll()` on an appropriate fallback |

**Common pitfall:** if a chain uses `securityMatcher("/api/**")` and calls `anyRequest().denyAll()` inside, `/admin/report` may **never match that chain**. Golden tests for admin routes must pass through the real filter chain, not just an internal policy function.

### 5.2. A reference HTTP configuration

The following is a **configuration excerpt**; add imports, Spring Boot project setup, authentication mechanism, and application controllers. It authenticates users at HTTP, while document permissions by tenant/owner/state are verified in the service:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This **does not automatically grant `APPROVE`** solely via `authenticated()`. A service may use a dedicated policy like this (excerpt requiring `documentPolicy` bean implementation and tenant/resource-checking repository):

~~~java
@PreAuthorize("@documentPolicy.canApprove(authentication, #documentId)")
public void approve(@P("documentId") String documentId) {
    // Update state within a transaction with appropriate integrity checks.
}
~~~

With `@PreAuthorize`, tests must invoke **Spring-managed beans through proxies** and verify side effects. Resource permissions can change after pre-checks; for sensitive operations, re-check conditions inside the same transaction or use conditional database updates to avoid TOCTOU.

### 5.3. Golden matrix flowing through HTTP

A golden row "a manager of tenant acme must not approve a tenant beta document" can be expressed in `MockMvc` within an app configured with controllers/fixtures:

~~~java
// Fragment in @SpringBootTest + @AutoConfigureMockMvc;
// DB fixture: document D-42 belongs to tenant beta, principal belongs to acme.
mockMvc.perform(post("/api/documents/D-42/approve")
        .with(user("reviewer").roles("REVIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

This snippet is **not a standalone program**; it requires `spring-security-test`, static imports, proper authentication setup, a security context carrying the principal's tenant, resource fixtures, and controllers. If the app is a stateless bearer-token API without browser cookies, CSRF may be configured differently per threat model; never disable CSRF app-wide just to pass tests.

Mandatory additional assertions:
- Grant test: returns success and causes **exactly one** business mutation/side effect.
- Deny test: returns policy-aligned response and causes **zero** DB mutations/outbound messages.
- Public route test: requires no authentication while still passing through appropriate filters.
- Test cross-tenant callers, disabled users, changed resource states, and different HTTP methods.
- Test a request matching no chain; if detected, fail the coverage gate.

When migrating multi-outcome policies, write separate tests for `AuthorizationResult.isGranted()`, `null`/abstain, `AccessDeniedException`, and authorization-service failures; never lump every exception into 403.

## 6. Shadow Traffic: Parallel Evaluation Without Altering Behavior

Shadow evaluation is a technique for **comparing decisions** on the exact same data snapshot—not duplicating HTTP requests with side effects.

Pseudocode example for a pure domain policy layer:

~~~java
// Architectural illustration; PolicyInput/Decision/metrics belong to the app.
Decision enforced = legacyPolicy.evaluate(input);
Decision observed = candidatePolicy.evaluate(input);

if (!observed.equals(enforced)) {
    metrics.recordPolicyDiff(
            policyVersion, input.scenarioClass(), enforced, observed);
}

// Only enforced decides whether the request proceeds during shadow mode.
return enforced;
~~~

Mandatory constraints:
1. Both policies must evaluate **without side effects**. Never re-invoke `approve`, publish messages, or log sensitive PII.
2. Use the identical identity/tenant/resource snapshot; if one policy queries the DB after data changed, flag stale-snapshot drift before blaming the code.
3. Record diffs by **scenario class, action, policy version, and risk group**, never emitting tokens, bodies, secrets, or sensitive resource IDs to telemetry.
4. Shadowing does not replace golden tests: still test expectations and review every **DENY → PERMIT**.
5. If shadow evaluation times out, define timeouts/budgets, circuit breakers, and telemetry skipping; never let the observing policy hang the enforced request or open permissions.
6. For policies relying on time, randomness, feature flags, or distributed data, pin clocks/seeds and context in tests for meaningful comparisons.

Only after resolving diffs should the candidate become the enforcing policy for an approved tenant/cluster canary, backed by metrics and a rollback switch. Canary bucketing must be sticky for a given user/request class; otherwise consecutive requests may hit different policies and behave unpredictably.

## 7. Canary, Rollback, and Acceptance Criteria

### 7.1. Security and operational gates

| Metric | Example Criterion | Consequence if Unmet |
| --- | --- | --- |
| Critical golden tests | 100% pass | Halt merge/deploy |
| Candidate unexpected PERMIT | **0** across golden and verified canary signals | Halt rollout, roll back |
| Cross-tenant privilege | 0 unauthorized accesses in tests/e2e | Halt rollout immediately |
| Unexpected DENY | Within business-approved threshold | Hold canary, investigate |
| Authorization errors/timeouts | Below defined availability/latency threshold | Halt expansion, apply fail-safe |
| p95/p99 authorization latency | Within API SLO | Optimize queries/caching; never drop checks |
| Coverage | Zero sensitive routes outside filter chains/policies | Block rollout |
| Audit/telemetry | Complete policy version and source, zero PII leaks | Fix observability before expanding |

**Never set "mismatch rate under 1%" as acceptable for granting extra permissions**: even a single critical over-grant can be severe. Production traffic metrics do not replace golden tests because rare/sensitive cases may never appear during canary.

### 7.2. Designing rollback before enabling

Rollback must restore a **known-safe policy** and synchronized configuration:
- Preserve pre-rollout code/rules/mappings, flag switches, or tested redeploy paths.
- Record newly approved permissions; rollback must never accidentally re-enable a known legacy vulnerability that was previously patched.
- Include the policy version in audit logs to identify which version evaluated any request.
- If grant/schema data migrations occurred, prepare backward-compatibility or dedicated data rollback plans; a feature flag toggling code alone cannot restore mutated data.
- After rolling back, re-run the golden matrix and canary smoke tests; verify live API behavior rather than trusting the flag state alone.

If the legacy policy is proven to contain a privilege escalation bug, fall back in emergencies to an approved **safe fallback** (potentially denying certain sensitive operations) rather than flipping a flag back to the vulnerability. Canary rollout is an impact-control mechanism, not an excuse to lower security standards.

## 8. Automated Testing from a Single Matrix Source

In a real project, store the golden matrix in a reviewable data source such as JSON/YAML with `scenarioId`, `policyVersion`, fixture references, and expectations. A CI variant:

~~~yaml
policyVersion: 17
cases:
  - id: P04
    principal: alice
    role: STAFF
    action: PRIVATE_READ
    callerTenant: acme
    documentTenant: beta
    owner: true
    expected: DENY
  - id: P05
    principal: reviewer
    role: REVIEWER
    action: APPROVE
    callerTenant: acme
    documentTenant: acme
    state: DRAFT
    expected: PERMIT
~~~

This is **sample data**, not a built-in Spring Security schema. When parsing YAML/JSON, validate required enums/fields and fail if a case omits `expected`; never default `expected` to PERMIT. Golden matrices require owner approval and diff reviews on edits.

In JUnit 5, use `@ParameterizedTest` and `@MethodSource` per scenario, alongside Spring Boot/`MockMvc` tests to confirm real configuration enforcement. **Never skip the HTTP layer**: domain policy may be sound while wrong `SecurityFilterChain` matchers or ordering leave an endpoint unprotected.

Suggested test split in the pipeline:
- **Unit:** evaluate every case, including expected denies and error/abstain; fast and deterministic.
- **Component:** `AuthorizationManager`, authority mappers, Spring AOP beans, and repository ACLs against data fixtures.
- **Integration:** `MockMvc` or live test server covering filter chains, CSRF, authentication entry points, HTTP methods, role prefixes, and tenants.
- **Contract/e2e:** token/IdP mappings, session invalidation, multiple chains, gateways, and migrated data; balance count due to runtime cost.
- **Performance:** benchmark policies involving DB/cache and shadow overhead; never remove query/tenant checks merely to hit latency targets.

Run at least the critical subset in CI before merging, and the full regression suite before promotion. Tag build results with the policy version and matrix data to avoid silent fixture changes between comparisons.

## 9. Common Migration Risks and How to Spot Them

1. **Using old policy outcomes as golden:** legalizes legacy vulnerabilities. Separate legacy baseline from business-approved expectations.
2. **Matching only total DENY/PERMIT counts:** two wrong grants can cancel out in counts. Compare per `scenarioId` with diff root causes.
3. **Altered role prefixes:** `hasRole("REVIEWER")` normally expects `ROLE_REVIEWER`, while `hasAuthority("REVIEWER")` matches the exact string.
4. **Confusing `securityMatcher` with `requestMatchers`:** `anyRequest` in a narrow chain does not cover the app; test all sensitive endpoints.
5. **Skipping method security:** controller tests pass while calling services from another path bypasses checks; test services via proxies.
6. **Shadow evaluation causing side effects:** comparisons must never re-execute business requests or double-grant access.
7. **Collapsing null-abstain and errors into deny:** loses manager/composer semantics and can cause bypasses or false blocks.
8. **Failing to distinguish 401, 403, and CSRF:** differing statuses do not always stem from authorization; identify which layer denied.
9. **Testing only valid users:** omits anonymous, cross-tenant, disabled users, other owners, nonexistent resources, and other HTTP methods.
10. **Unstable canary routing:** same principal/resource alternates between old and new policies, complicating triage and rollback.
11. **Changing policies and grants/schemas simultaneously:** obscures diff causes; separate migrations or maintain compatible data versions.
12. **Watching only diff %:** a single unintended allow on a sensitive export endpoint must still block rollout.
13. **Skipping post-rollback integrity checks:** flag flips succeed while caches, DBs, or old policy mappings remain out of sync.
14. **Deleting golden tests after migration completes:** the next Spring Security upgrade can reintroduce old bugs.

## 10. Practical Checklist

- [ ] Complete inventory of endpoints, methods, filter chains, role mappings, and custom voters/managers.
- [ ] Golden matrix has owner approval, version, case IDs, and PERMIT/DENY/ABSTAIN/ERROR branches where applicable.
- [ ] Covers anonymous, roles, tenants, owners, states, HTTP methods, nonexistent resources, and fallback chains.
- [ ] Candidate-vs-golden and legacy-vs-candidate computed **separately**, with diffs clearly classified.
- [ ] Zero unexpected PERMITs; permission-widening changes have documented approval.
- [ ] Shadowing causes zero side effects, uses identical inputs, and leaks no tokens/PII.
- [ ] Tested Spring-managed proxies, HTTP filter chains, statuses, CSRF, and side effects.
- [ ] Defined canary cohorts, SLOs/alerts, rollback paths, and policy versions in audit logs.
- [ ] Re-ran matrix after rollback/promotion; retired old code only after sufficient evidence.
- [ ] Matrix retained as the regression contract for future upgrades.

## 11. References

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, `authorizeHttpRequests`, matcher ordering, `hasRole`/`hasAuthority`.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, migrating from voters/decision managers, result contracts.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and proxies.
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing authorization for Servlet/MVC.
- [JUnit 5 – Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): generating test cases from data sources.

**Takeaway to remember:** phased migration is safe only when you have a **correct permission definition independent of legacy code**. The golden matrix determines pass/fail; shadow comparison provides visibility, canarying limits blast radius, and rollback protects when live data triggers issues. Success means *business permissions remain accurate* across every version change—not merely that Spring Security boots.
