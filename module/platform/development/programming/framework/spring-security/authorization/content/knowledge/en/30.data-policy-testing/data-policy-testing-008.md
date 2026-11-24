# Testing Policy Services on Timeout, Error, or Invalid Responses

## 1. Problem and Objectives

In Spring Security, an application can delegate an authorization decision to an external **policy service** (Policy Decision Point, PDP). The application acts as the **Policy Enforcement Point (PEP)**: it receives requests, builds trusted context, calls the PDP, and enforces or denies access. An example query is: is user alice permitted to READ resource /reports/42?

Typical flow:

~~~text
HTTP request
  -> SecurityFilterChain
  -> AuthorizationManager (PEP)
  -> PolicyGateway / HTTP client
  -> Policy service (PDP)
  <- policy response
  -> allow or deny decision
  -> controller runs only when permitted
~~~

This lesson focuses on testing **when the PDP fails to return a trustworthy decision**: timeouts, network/HTTP errors, malformed responses, or contract violations. The goal is not testing policy-authoring logic inside the PDP, but verifying trust boundaries and enforcement behavior in the application calling the PDP.

After this lesson, you must be able to prove these invariants:

1. **Only a valid ALLOW response matching the current request grants access.** DENY, missing data, errors, and timeouts all deny access (fail closed).
2. **DENY is distinct from an indeterminate decision.** Both block entry, yet they must be classified differently for logs, metrics, investigations, and operations.
3. **Finite time budgets.** Never let requests hang indefinitely, retry excessively, or allow a late response to turn into access for an already-finished request.
4. **Never enter business logic when authorization fails.** Tests must verify data-writing controllers/services do not execute, not merely check the HTTP status.
5. **Distinguish PDP failures from PEP programming bugs.** Catch expected failure types cleanly; never silently swallow all exceptions into an unobservable outcome.

## 2. Making the Contract Testable

Suppose the protocol between the application and PDP is agreed as follows (this is an **illustrative contract**, not a mandatory Spring Security format):

| Component | Field / Signal | What to Guarantee |
| --- | --- | --- |
| Request | subject, action, resource | Derived from Authentication and server-normalized resources; never trust user-declared permissions |
| Request | requestId | Unique correlation ID per evaluation |
| Response | effect = ALLOW or DENY | Explicit allowed value set; unknown values must never default to ALLOW |
| Response | requestId | Must match the current request; a reply from another request is invalid |
| Response | policyVersion | Mandatory in this sample contract; if the real system lacks it, update contract and tests accordingly |
| Infrastructure | connect timeout, read/response timeout, overall deadline | Must actually be enforced by the HTTP client; passing a Duration argument alone is not enough |
| Errors | timeout, connection reset, DNS, HTTP 429/5xx, JSON parse error | Normalized into testable error categories, never returning ALLOW |

Internal outcomes can be modeled with four categories:

- **ALLOW**: valid response, matching request, effect is strictly ALLOW.
- **DENY**: valid response, matching request, effect is strictly DENY.
- **INVALID**: input/output violates the contract: null, missing fields, unknown values, malformed JSON, mismatched requestId.
- **UNAVAILABLE**: no decision received due to timeout, connection failure, HTTP error, or an open circuit breaker.

Only ALLOW maps to **granted = true**; the other three map to **false**. How PDP HTTP 401/403/429/5xx statuses map to categories must be defined in the concrete adapter, yet **none of those errors may ever become ALLOW**. In systems with specific reliability or availability requirements, returning HTTP 503 for requests rejected due to PDP unavailability can be a valid design choice; the safety rule remains never executing the protected business logic.

## 3. Mandatory Test Case Matrix

| Case | Simulation | Gateway Outcome | Invariant to Assert |
| --- | --- | --- | --- |
| Valid ALLOW | PDP returns ALLOW with matching requestId and required fields | ALLOW | Permits only the authorized request |
| Valid DENY | PDP returns valid DENY | DENY | Business logic does not run |
| Connect timeout | Cannot establish connection within budget | UNAVAILABLE | Denies; finishes within deadline |
| Read/response timeout | Connected, but PDP does not finish responding | UNAVAILABLE | Denies, never hangs indefinitely |
| HTTP 500/503 | PDP stub returns server error | UNAVAILABLE | Does not fall back to ALLOW |
| DNS/reset/connection refused | Client throws corresponding IOException | UNAVAILABLE | Does not grant access |
| HTTP 429 | PDP rate-limits requests | UNAVAILABLE or predefined operational error type | No bypass; retries stay within budget |
| PDP returns malformed JSON | Decoder detects parse error | INVALID | Does not use partial data |
| Missing/null effect | Syntactically valid JSON lacking semantics | INVALID | Does not infer a default value |
| Unknown effect (e.g. PERMIT) | Not in the enum/contract set | INVALID | Never uses "anything other than DENY is allowed" |
| Mismatched requestId | Data from another request | INVALID | Never accepts the wrong decision |
| Missing required field | Empty policyVersion under sample contract | INVALID | Does not grant access |
| Null response / empty body | Invalid 204 or empty body | INVALID | No NPE or accidental ALLOW |
| Response arrives after deadline | Delay then return ALLOW | UNAVAILABLE for the timed-out request | Late ALLOW never alters the completed decision |
| Circuit breaker OPEN | Client skips calling PDP | UNAVAILABLE | Controller not invoked; metric recorded |
| Invalid input | Missing principal/resource/action/requestId | INVALID | Invalid request not sent to PDP |
| Concurrent requests | One ALLOW and one timeout, distinct requestIds | Isolated per-request outcomes | Decisions never leak across requests |

For policies carrying obligations (e.g., mandatory column/tenant filters), signatures, validity windows, or minimum versions, add cases where those fields are missing or invalid. **An ALLOW missing required enforcement conditions must also be denied.**

## 4. Standalone Java 17+ Example: Gateway and Fake-Client Tests

The example below uses a fake client to produce **deterministic** outcomes without sleeping or real networking. The fake client throws TimeoutException, IOException, or BadPayloadException just like a real adapter normalized from an HTTP client. Real socket timeout tests are covered in Section 6.

Save the following in **PolicyFailureDemo.java**:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;

public class PolicyFailureDemo {
    private static final Duration BUDGET = Duration.ofMillis(250);
    private static final Request REQUEST =
            new Request("alice", "READ", "/reports/42", "req-42");

    record Request(String subject, String action, String resource, String requestId) {}
    record Reply(String requestId, String effect, String policyVersion) {}

    enum Outcome { ALLOW, DENY, INVALID, UNAVAILABLE }

    static final class BadPayloadException extends Exception {
        BadPayloadException(String message) { super(message); }
    }

    @FunctionalInterface
    interface PolicyClient {
        Reply evaluate(Request request, Duration deadline)
                throws IOException, TimeoutException, BadPayloadException;
    }

    static final class PolicyGateway {
        private final PolicyClient client;

        PolicyGateway(PolicyClient client) { this.client = client; }

        Outcome authorize(Request request) {
            if (request == null || !present(request.subject())
                    || !present(request.action()) || !present(request.resource())
                    || !present(request.requestId())) {
                return Outcome.INVALID;
            }

            try {
                Reply reply = client.evaluate(request, BUDGET);
                if (reply == null || !request.requestId().equals(reply.requestId())
                        || !present(reply.effect()) || !present(reply.policyVersion())) {
                    return Outcome.INVALID;
                }

                return switch (reply.effect()) {
                    case "ALLOW" -> Outcome.ALLOW;
                    case "DENY" -> Outcome.DENY;
                    default -> Outcome.INVALID;
                };
            } catch (BadPayloadException ex) {
                return Outcome.INVALID;
            } catch (TimeoutException | IOException ex) {
                return Outcome.UNAVAILABLE;
            }
        }
    }

    private static boolean present(String text) {
        return text != null && !text.isBlank();
    }

    private static void verify(String label, PolicyClient client, Outcome expected) {
        Outcome actual = new PolicyGateway(client).authorize(REQUEST);
        if (actual != expected) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
        System.out.printf("%s -> %s; granted=%s%n",
                label, actual, actual == Outcome.ALLOW);
    }

    public static void main(String[] args) {
        verify("valid ALLOW", (req, deadline) ->
                new Reply(req.requestId(), "ALLOW", "v1"), Outcome.ALLOW);
        verify("explicit DENY", (req, deadline) ->
                new Reply(req.requestId(), "DENY", "v1"), Outcome.DENY);
        verify("timeout", (req, deadline) -> {
            throw new TimeoutException("deadline exceeded");
        }, Outcome.UNAVAILABLE);
        verify("HTTP 503", (req, deadline) -> {
            throw new IOException("503 Service Unavailable");
        }, Outcome.UNAVAILABLE);
        verify("malformed JSON", (req, deadline) -> {
            throw new BadPayloadException("invalid JSON");
        }, Outcome.INVALID);
        verify("unknown effect", (req, deadline) ->
                new Reply(req.requestId(), "PERMIT", "v1"), Outcome.INVALID);
        verify("wrong requestId", (req, deadline) ->
                new Reply("req-other", "ALLOW", "v1"), Outcome.INVALID);
        verify("missing policy version", (req, deadline) ->
                new Reply(req.requestId(), "ALLOW", ""), Outcome.INVALID);
        verify("null reply", (req, deadline) -> null, Outcome.INVALID);
    }
}
~~~

Compile with Java 17 or newer and run:

~~~bash
javac --release 17 PolicyFailureDemo.java
java PolicyFailureDemo
~~~

Exact stdout:

~~~text
valid ALLOW -> ALLOW; granted=true
explicit DENY -> DENY; granted=false
timeout -> UNAVAILABLE; granted=false
HTTP 503 -> UNAVAILABLE; granted=false
malformed JSON -> INVALID; granted=false
unknown effect -> INVALID; granted=false
wrong requestId -> INVALID; granted=false
missing policy version -> INVALID; granted=false
null reply -> INVALID; granted=false
~~~

**Explanation:** The gateway validates inputs before calling the PDP; accepts only effects in ALLOW/DENY; checks requestId and required fields; maps decoder errors to INVALID and infrastructure errors to UNAVAILABLE. `main` acts as a simple test runner: a single mismatch throws AssertionError and halts. In production code, turn each case into a JUnit 5 unit test with mocks/fakes, asserting client invocation counts and verifying metrics and logs by error type.

**Intentional demo limitation:** Duration is passed to PolicyClient, yet the fake client does not measure real elapsed time. In a real implementation, the HTTP adapter must configure overall deadlines, connect timeouts, and read timeouts rather than hoping callers throw TimeoutException on their own. The sample reply contract requires policyVersion; a real project schema may differ and must be tested against the approved schema. The code does not catch every RuntimeException: programming bugs should surface and trigger alerts; at the security boundary, every error path must still guarantee no access is granted.

## 5. Wiring Decisions into Spring Security

In Servlet applications using Spring Security 6.x, the gateway can sit behind an AuthorizationManager<RequestAuthorizationContext>. This is an **integration excerpt** requiring Spring Security dependencies, bean configuration, and the project's gateway classes; it is not a standalone Java file like Section 4.

~~~java
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

final class PolicyAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final PolicyFailureDemo.PolicyGateway gateway;

    PolicyAuthorizationManager(PolicyFailureDemo.PolicyGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> supplier,
            RequestAuthorizationContext context) {
        Authentication auth = supplier.get();
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        var httpRequest = context.getRequest();
        var input = new PolicyFailureDemo.Request(
                auth.getName(),
                httpRequest.getMethod(),
                httpRequest.getRequestURI(),
                UUID.randomUUID().toString()
        );

        var outcome = gateway.authorize(input);
        return new AuthorizationDecision(
                outcome == PolicyFailureDemo.Outcome.ALLOW
        );
    }
}
~~~

Example wiring into SecurityFilterChain (excerpt inside a configuration providing HttpSecurity):

~~~java
http.authorizeHttpRequests(registry -> registry
    .requestMatchers("/reports/**").access(policyAuthorizationManager)
    .anyRequest().authenticated());
~~~

When an authenticated user gets DENY, INVALID, or UNAVAILABLE from the gateway, the denied decision typically produces **HTTP 403** via access-denied handling. For unauthenticated users, the HTTP status depends on the AuthenticationEntryPoint and authentication configuration (e.g., HTTP Basic typically returns 401, form login may redirect). Do not hardcode HTTP 401/403 for every PDP failure if the architecture defines specific rules; first and foremost, tests must prove **no success response leaks resources and no side effects execute**.

In production, resource names should come from normalized identifiers/validated routes (especially when paths contain tenants or object IDs), and actions should reflect the protected business operation; the example merely illustrates deriving from HTTP method/path. Never send raw tokens, unnecessary data, or client-declared permission lists to the PDP. With Spring Security Reactive, use ReactiveAuthorizationManager and a non-blocking pipeline; apply timeouts on Mono/Flux, map categorized failures to denied decisions, and **never call block() on the event loop**.

## 6. Three Test Layers and How to Verify Real Timeouts

### 6.1. Unit Tests for PolicyGateway (Fast and Deterministic)

Replace PolicyClient with a fake/mock, without using Thread.sleep to simulate timeouts. Have the client return a Reply or throw exceptions corresponding to every row in Section 3's matrix.

Verify simultaneously:

- Outcome is exact and granted is true only for valid ALLOW.
- A valid request input invokes the client the expected number of times; inputs missing fields are blocked before calling the client.
- The deadline passed to the client matches configuration; timeouts/errors never trigger fallback to default permissions.
- Replies with a different requestId, null/unknown effect, empty body, or missing version are all INVALID even if "ALLOW" appears elsewhere.
- Issue two concurrent requests with distinct requestIds and force out-of-order replies; each request receives only its own decision.

With Mockito/JUnit, name tests after behaviors: shouldDenyWhenPolicyTimesOut, shouldRejectUnknownEffect, shouldRejectMismatchedRequestId, shouldPermitOnlyValidAllow. For unchecked decoder exceptions from a JSON library, test that the HTTP adapter converts them into BadPayloadException (or the equivalent domain error) before reaching the gateway.

### 6.2. Integration Tests for the HTTP Adapter / PDP Stub

Use WireMock or MockWebServer to control real HTTP responses; configure the client with a finite overall deadline and appropriate per-phase timeouts. For each case, bound completion duration within CI-safe tolerances rather than asserting exact milliseconds.

1. **Server delays** longer than the read timeout/deadline before returning ALLOW. Gateway must return UNAVAILABLE within budget rather than waiting for the late ALLOW.
2. **Socket closed mid-response** or connection refused. Client translates I/O failures into UNAVAILABLE; zero infinite retries.
3. **HTTP 503 or 429**. Adapter never parses an error body into a fake ALLOW; retry count and total duration remain bounded.
4. **HTTP 200 with invalid JSON**, valid JSON missing effect, unknown effect, or wrong requestId. Categorize as INVALID; never use partial fields to grant access.
5. **Valid ALLOW within deadline**. Grants access, proving test setup does not break the happy path.

If the system uses retries, enforce a deadline covering the **entire** evaluation (including retries/backoff), verify PDP call counts, and test impact when multiple requests time out simultaneously. Cancelling a Future/Mono is only a signal; verify actual resources/sockets are released according to the HTTP library used. Never assume cancellation automatically stops all remote work.

### 6.3. Testing Spring Security at the HTTP Boundary

Use MockMvc (Servlet) or WebTestClient (Reactive) through the **real SecurityFilterChain**, mocking the gateway at the appropriate boundary:

| Scenario | HTTP / Application Assertion |
| --- | --- |
| Valid principal + ALLOW | Request reaches controller; API success status |
| Valid principal + DENY | Blocked, typically 403; business method does not execute |
| Valid principal + timeout, 5xx, bad JSON | Blocked; zero side effects; failure outcome logged/metered |
| Unauthenticated | Does not pass authorization; HTTP response follows configured auth mechanism |
| Unprotected route | Accessible only under explicit route policy; matchers never widened accidentally |
| After an ALLOW, PDP fails on new request | New request denied per cache policy; never misuses stale ALLOW |

For data-writing endpoints, add verify(service, never()).update(...) or check before/after database state; asserting only status 403 can miss side effects that ran before authorization. Test multi-tenant data to catch improperly shared requestIds/contexts. If permission caching is permitted by business requirements, cache keys must include subject/resource/action/tenant/policy version with explicit TTL and expiration rules; **never automatically grant access from a stale ALLOW while the PDP is failing** without an explicitly approved exception policy.

## 7. Operational Signals and Common Design Mistakes

**Observable without leaking secrets.** Emit metrics by outcome (ALLOW, DENY, INVALID, UNAVAILABLE), granular cause (timeout, HTTP 5xx, parse, mismatch), and latency; trace with correlation/requestId. Keep metric labels bounded: never put access tokens, personal subjects, resource IDs, or full PDP bodies into metric tags. Log at appropriate levels without exposing credentials or sensitive payloads. Tests can use an in-memory meter registry/log appender to verify classification without manual log inspection.

**Circuit breakers and retries.** When the breaker is open, decisions must fail closed and be recorded as unavailable. Never retry indiscriminately on all errors, exceed the total deadline, or trigger retry storms when the PDP is already overloaded. PDP failures must never cause protection paths to fall back to permitAll or bypass AuthorizationManager.

**Ambiguous responses.** Never use expressions like "if effect != DENY then allow", "null means no policy restriction", or "PDP error means no rules apply." Each of those turns a data failure into an authorization bypass.

**Clear classification.** Valid DENY is a policy decision; INVALID is a data contract violation; UNAVAILABLE is an infrastructure failure. Collapsing all three into a single boolean when returning to Spring Security is acceptable at the final boundary, but keep their classifications distinct in gateway/telemetry layers for operations and forensics.

**Consistency.** A PDP response applies solely to the request that sent it; requestId, tenant context, and policy obligations must be checked. Never reuse another thread's outcome during concurrent requests; discard ALLOWs arriving after timeout. When permission data changes, caches and policy versions must have invalidation rules.

**Common testing mistakes:** simulating only IOException while skipping parse/schema errors; testing timeouts with long sleeps that slow CI and cause flakiness; calling the gateway directly without traversing the filter chain; checking only status without confirming the controller stayed unexecuted; expecting 401 for every failure; letting mocks return null by default without asserting reasons; or asserting deadlines against exact millisecond thresholds that flake on CI runners.

## 8. Completion Criteria

A test suite is sufficient for this lesson's scope when: valid ALLOW/DENY cases are tested; timeouts, network/HTTP errors, and invalid responses are all denied; requestId and required fields are checked; real deadlines are verified with a network stub; SecurityFilterChain blocks before business logic; failures are observably classified; retries/breakers/caches introduce no bypasses; and tests run deterministically without depending on a live PDP.

The governing principle at every layer: **without a valid ALLOW for the exact current context, no access is granted**.