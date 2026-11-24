# Integrating a Policy Service with Bounded Timeouts and Controlled Caching

## 1. The Problem of Integrating a Policy Service in Authorization

In a Spring Security application, access decisions are sometimes made by a **centralized policy service** (Policy Decision Point, **PDP**). The application calling that service is the **Policy Enforcement Point (PEP)**: it must verify the decision and block unauthorized actions.

For example, Alice holds the functional authority `DOCUMENT_READ`, yet she may not view every document. Upon receiving `GET /documents/101`, the API must know which tenant Alice belongs to, which tenant owns document 101, which grants/ACLs Alice holds, whether a grant has expired, and whether the policy just changed.

```text
Client ──► Spring Security authentication
                 │
                 ▼
       HTTP / service-level authorization
                 │
                 ▼
       PEP ──► PDP: subject + action + resource + tenant
                 │         │
                 │         ├─ Valid ALLOW
                 │         ├─ DENY
                 │         └─ timeout / error / malformed response
                 ▼
       Execute only when the decision is trustworthy
       and data remains within tenant/owner scope
```

If the PEP merely calls the PDP for logging yet still executes business logic after `DENY` or a timeout, authorization is not enforced. If the API returns HTTP 403 while the database was already updated beforehand, security has likewise failed.

Three goals go together: **bounded wait time**, **fail-safe denial (fail closed)**, and **bounded caching that never extends permissions past expiration**. These mechanisms protect both authorization correctness and application availability when the PDP experiences latency or stops responding.

## 2. PDP Request/Response Contract: What Data Is Needed?

A server-to-server request can be represented as follows:

```json
{
  "subjectId": "user-42",
  "tenantId": "tenant-a",
  "action": "DOCUMENT_READ",
  "resourceId": 101,
  "permissionRevision": 7
}
```

The PDP returns a decision following this illustrative API contract:

```json
{
  "allowed": true,
  "validUntil": "2026-11-06T08:00:02Z",
  "policyVersion": "p-183",
  "decisionId": "dec-8721"
}
```

Security significance:

- `subjectId`, `tenantId`, and `permissionRevision` must be determined by the authentication provider and trusted server data. Never accept them from headers/client bodies as truth.
- `action` must distinguish READ, EXPORT, ARCHIVE, ADMIN, etc. `resourceId` must carry its namespace/tenant so two resources sharing an ID in different scopes are never confused.
- `allowed` **must** be a valid boolean. An HTTP 200 response does not equate to ALLOW; null body, malformed JSON, or missing fields mean **no valid decision**.
- `validUntil` is the expiration timestamp, verified by the invariant `now < validUntil`. The PDP must compute this bound from grant expiry and policy constraints.
- `policyVersion` and `decisionId` aid auditing, yet a version string in a response does not automatically notify other caches that a new policy exists.
- When the PDP returns *obligations* (field masking, step-up MFA, transaction limits), the PEP must enforce them; never treat ALLOW as ignoring obligations.

Every field affecting the decision must be sent to the PDP or reliably looked up by the PDP itself. When permissions depend on ACLs, ownership, or record state, sending only a generic role lacks context. The contract must also clearly define DENY for nonexistent objects vs. unauthorized objects to avoid leaking ID existence via error messages.

## 3. Timeouts: Connect, Request, and Overall Deadline

Two distinct timeouts:

| Mechanism | What Does It Bound? | Key Consideration |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout` | Establishing a new connection to the PDP | When a connection is reused, this limit may not apply |
| `HttpRequest.Builder.timeout` | Time a single request waits for a response | Without this limit, waiting for a response can stall indefinitely |
| Business request deadline | Total time for authentication, PDP, database, and response | Retries must fit within remaining budget |

Illustrative budget example: business request has 1,000 ms; connect timeout 100 ms; PDP request timeout 300 ms; remaining time reserved for DB/serialization. These numbers are **not Spring Security defaults**. Derive them from p95/p99 latency, SLOs, traffic, thread counts, and business risk.

**Do not add the two timeouts to 400 ms as a guarantee**: request timeout applies to the request call, which includes connection setup depending on HTTP client behavior. New connections and pooled connections must be tested separately. HTTP timeouts may cover response wait time; enforce deadlines in upstream layers so the overall budget is not exceeded.

A bad retry policy might call the PDP three times at 300 ms each, exhausting nearly the entire 1-second budget before touching the database while overloading a failing PDP. A sound default is a single evaluation with a clear deadline, very limited retries only on transient errors when budget remains. **Never retry a valid DENY decision.**

## 4. Fail Closed and Degradation Policy

`DENY` returned by the PDP differs from `UNAVAILABLE` when the PDP fails to respond. Both must **block execution**, yet audits and metrics should record distinct reasons.

| State | Internal Read Allowing Short Cache | Sensitive Mutation/Admin |
| --- | --- | --- |
| Valid ALLOW from PDP | Permitted if data scope matches | Permitted if all extra conditions hold |
| Valid DENY | Blocked | Blocked |
| Timeout/error, empty cache | Blocked | Blocked |
| Cache ALLOW for matching key, unexpired | Usable if contract accepts stale window | Do not use if live permission check is required |
| Expired cache while PDP errors | Blocked, do not extend stale ALLOW | Blocked |
| Circuit breaker OPEN | Blocked when no policy-accepted decision exists | Blocked |

Never implement:

```java
// WRONG: policy service unavailable yet opens access.
try {
    return pdp.isAllowed(input);
} catch (Exception failure) {
    return true;
}
```

In the `@PreAuthorize` example, the guard returns `false` when the PDP is unavailable, so the caller receives a Spring method security denial. Depending on the HTTP contract, the API can return 403 or map an exception to 503 for infrastructure outages; **both must guarantee the business method does not execute**. Using a cached ALLOW while the PDP is unreachable is an explicit risk acceptance within a bounded window, not a guarantee that current permissions remain ALLOW.

## 5. Cache Key, TTL, and Stale Permission Window

A minimal object-scoped decision key:

```text
(subjectId, tenantId, action, resourceId, permissionRevision)
```

If decisions depend on groups, owner, resource state, MFA, trusted IP, resource type, or environmental attributes, include those dependencies in the key/trusted version or **do not cache**. Caching solely by username or URL is dangerous: the same caller can read multiple documents, or the same URL can handle multiple actions.

In the example below, the Caffeine cache has `maximumSize(10_000)` and `expireAfterWrite(2 seconds)`. Beyond the hard TTL, the guard checks `validUntil` from the PDP on every hit. `expireAfterWrite` does not extend on read; `expireAfterAccess` can keep ALLOW alive longer under continuous traffic.

### The Revocation Problem

If the PDP revokes Alice at `t=0` while an app node still holds a cached ALLOW until `t+2s`, Alice can keep reading during that window. For actions requiring **immediate revocation**, a 2-second TTL is insufficient: skip ALLOW caching or use versioning/freshness mechanisms with appropriate consistency guarantees.

Scenarios to model:

1. Revoke event reaches instance A only; instance B retains its cache.
2. Cache eviction arrives first; an in-flight older PDP response arrives afterward and refills ALLOW.
3. An old JWT still carries an older `permissionRevision`; token claims do not update automatically on revocation.
4. A resource's owner changes, yet caches are invalidated only by subject.
5. A grant expires before the cache TTL; the PDP must cap `validUntil` so it never exceeds that expiry.
6. A still-valid DENY cache delays a newly granted permission from taking effect; usually less dangerous than stale ALLOW, yet still affects UX/SLA.

`invalidateSubject` inside one JVM clears only the local cache. Multi-instance deployments need reliable events, version fences, or direct PDP checks for operations that cannot tolerate stale ALLOWs.

## 6. Standalone Java 17: Simulating Timeout/Cache/Revocation

This Java snippet **runs standalone**, without Spring or Caffeine, to verify invariants: cache hits avoid extra PDP calls, invalidation fetches fresh decisions, timeouts never open access, and sensitive actions bypass caching.

File `PolicyCacheDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class PolicyCacheDemo {
    record Key(String subject, String tenant,
               String action, long resource, long revision) {}
    record Reply(boolean allowed, Instant validUntil) {}

    static class FakePdp {
        final Map<Key, Boolean> grants = new HashMap<>();
        boolean online = true;
        int calls;

        Reply decide(Key key, Instant now) {
            calls++;
            if (!online) throw new IllegalStateException("timeout");
            return new Reply(grants.getOrDefault(key, false),
                    now.plusSeconds(10));
        }
    }

    static class Guard {
        final FakePdp pdp;
        final Map<Key, Reply> cache = new HashMap<>();

        Guard(FakePdp pdp) { this.pdp = pdp; }

        boolean check(Key key, Instant now, boolean critical) {
            if (!critical) {
                Reply old = cache.get(key);
                if (old != null && now.isBefore(old.validUntil())) {
                    return old.allowed();
                }
            }
            try {
                Reply decision = pdp.decide(key, now);
                if (!critical) {
                    Instant hardLimit = now.plusSeconds(2);
                    Instant until = decision.validUntil()
                            .isBefore(hardLimit)
                            ? decision.validUntil() : hardLimit;
                    cache.put(key, new Reply(decision.allowed(), until));
                }
                return decision.allowed();
            } catch (IllegalStateException down) {
                return false;
            }
        }

        void invalidate(Key key) { cache.remove(key); }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T08:00:00Z");
        Key read = new Key("alice", "tenant-a",
                "DOCUMENT_READ", 101, 7);
        Key admin = new Key("alice", "tenant-a",
                "POLICY_EDIT", 101, 7);

        FakePdp pdp = new FakePdp();
        pdp.grants.put(read, true);
        Guard guard = new Guard(pdp);

        System.out.println("first=" + guard.check(read, now, false));
        System.out.println("cached=" +
                guard.check(read, now.plusMillis(500), false));
        System.out.println("calls=" + pdp.calls);

        pdp.grants.put(read, false);
        guard.invalidate(read);
        System.out.println("revoked=" +
                guard.check(read, now.plusMillis(600), false));

        pdp.online = false;
        Key other = new Key("alice", "tenant-a",
                "DOCUMENT_READ", 102, 7);
        System.out.println("timeoutRead=" +
                guard.check(other, now.plusSeconds(1), false));
        System.out.println("timeoutAdmin=" +
                guard.check(admin, now.plusSeconds(1), true));
        System.out.println("totalCalls=" + pdp.calls);
    }
}
```

Run on JDK 17 or higher:

```bash
javac PolicyCacheDemo.java
java PolicyCacheDemo
```

Exact stdout:

```text
first=true
cached=true
calls=1
revoked=false
timeoutRead=false
timeoutAdmin=false
totalCalls=4
```

If you remove `guard.invalidate(read)`, `revoked` can stay `true` because the cached ALLOW is still valid at `t+600ms`. This code simulates logical ordering and assumes a single thread; production requires thread-safe caching, multi-node invalidation, and real HTTP timeouts.

## 7. Spring Boot: Dependencies and Timeout Configuration

The integration example uses Java 17+, Spring Boot 3.x, Spring Security 6, Jackson, Caffeine, and JDBC. The snippets below belong to an application that already has authentication and a database, **not** standalone `javac` files. Illustrative Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In package `demo.policy`, file `PolicyConfig.java`:

```java
package demo.policy;

import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class PolicyConfig {
    @Bean
    Clock policyClock() {
        return Clock.systemUTC();
    }

    @Bean
    HttpClient policyHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(100))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }
}
```

The Spring Security starter **does not automatically enable** method authorization. `@EnableMethodSecurity` must be present, and methods must be invoked via a Spring-managed AOP proxy. `HttpClient` is reused as a bean rather than created per request. In production, configure TLS trust, mTLS/workload identity or service credentials, and host allowlists; never disable TLS verification when encountering connection errors.

## 8. Contracts and HTTP Adapter: Always Validate Responses

File `PolicyContracts.java` containing package-private types:

```java
package demo.policy;

import java.time.Instant;

record AccessPrincipal(
        String subject, String tenant, long permissionRevision) {}

record PolicyKey(
        String subject, String tenant, String action,
        long resourceId, long permissionRevision) {}

record PolicyReply(
        Boolean allowed, Instant validUntil,
        String policyVersion, String decisionId) {}

record CachedDecision(boolean allowed, Instant validUntil) {}

interface PolicyClient {
    PolicyReply decide(PolicyKey key);
}

final class PolicyUnavailableException extends RuntimeException {
    PolicyUnavailableException(String text) { super(text); }
    PolicyUnavailableException(String text, Throwable cause) {
        super(text, cause);
    }
}
```

`AccessPrincipal` must be constructed by a trusted authentication provider/converter, never accepted directly from external JSON. File `HttpPolicyClient.java`:

```java
package demo.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
final class HttpPolicyClient implements PolicyClient {
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final URI endpoint;

    HttpPolicyClient(HttpClient client, ObjectMapper mapper,
                     @Value("${security.policy.decision-url}")
                     String url) {
        this.client = client;
        this.mapper = mapper;
        this.endpoint = URI.create(url);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException("PDP must use HTTPS");
        }
    }

    @Override
    public PolicyReply decide(PolicyKey key) {
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofMillis(300))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            mapper.writeValueAsString(key),
                            StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            if (response.statusCode() != 200) {
                throw new PolicyUnavailableException(
                        "PDP HTTP " + response.statusCode());
            }
            PolicyReply reply = mapper.readValue(
                    response.body(), PolicyReply.class);
            if (reply == null || reply.allowed() == null
                    || reply.validUntil() == null
                    || reply.policyVersion() == null
                    || reply.decisionId() == null) {
                throw new PolicyUnavailableException("Invalid PDP response");
            }
            return reply;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new PolicyUnavailableException("Interrupted", ex);
        } catch (IOException ex) {
            throw new PolicyUnavailableException("PDP I/O or JSON error", ex);
        }
    }
}
```

In real files, `${security.policy.decision-url}` corresponds to the Spring `@Value` configuration expression for property `security.policy.decision-url`, such as the standard form `@Value("${security.policy.decision-url}")`. Provide a trusted HTTPS URL in configuration and configure service-to-service authentication. The illustrative adapter does not configure mTLS/tokens or bound response size; add those per operational standards before production.

`HttpRequest.timeout` bounds each request to 300 ms; `HttpClient.connectTimeout` bounds establishing a new connection to 100 ms. `HttpTimeoutException` is an `IOException` and translates to `PolicyUnavailableException`. `ObjectMapper` must be configured to support `Instant` (Spring Boot normally auto-configures Jackson Java Time when the module is present); test real response parsing. Never accept an empty HTTP 200, `allowed=null`, or a response without expiry.

## 9. Caffeine Guard: Bounding TTL and Skipping Cache on Mutations

File `PolicyGuard.java`:

```java
package demo.policy;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("policyGuard")
public final class PolicyGuard {
    private static final Duration MAX_AGE = Duration.ofSeconds(2);
    private final PolicyClient client;
    private final Clock clock;
    private final Cache<PolicyKey, CachedDecision> cache;

    public PolicyGuard(PolicyClient client, Clock clock) {
        this.client = client;
        this.clock = clock;
        this.cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(MAX_AGE)
                .build();
    }

    public boolean canRead(Authentication auth, long id) {
        return decide(auth, "DOCUMENT_READ", id, true);
    }

    public boolean canArchive(Authentication auth, long id) {
        return decide(auth, "DOCUMENT_ARCHIVE", id, false);
    }

    private boolean decide(
            Authentication auth, String action,
            long resourceId, boolean cacheAllowed) {
        if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof AccessPrincipal p)
                || p.subject() == null || p.subject().isBlank()
                || p.tenant() == null || p.tenant().isBlank()
                || p.permissionRevision() < 0 || resourceId <= 0) {
            return false;
        }

        PolicyKey key = new PolicyKey(
                p.subject(), p.tenant(), action,
                resourceId, p.permissionRevision());

        Instant now = clock.instant();
        if (cacheAllowed) {
            CachedDecision previous = cache.getIfPresent(key);
            if (previous != null) {
                if (now.isBefore(previous.validUntil())) {
                    return previous.allowed();
                }
                cache.invalidate(key);
            }
        }

        try {
            PolicyReply answer = client.decide(key);
            Instant afterCall = clock.instant();
            if (!answer.validUntil().isAfter(afterCall)) {
                return false;
            }
            if (cacheAllowed) {
                Instant hardLimit = afterCall.plus(MAX_AGE);
                Instant until = answer.validUntil().isBefore(hardLimit)
                        ? answer.validUntil() : hardLimit;
                cache.put(key, new CachedDecision(
                        answer.allowed(), until));
            }
            return answer.allowed();
        } catch (PolicyUnavailableException ex) {
            return false;
        }
    }

    public void invalidateSubject(String subject) {
        cache.asMap().keySet().removeIf(
                k -> k.subject().equals(subject));
    }
}
```

Here `canRead` may use a key-scoped cache for two seconds; `canArchive` always queries the PDP. If the PDP times out and no valid cached ALLOW exists, the guard returns `false`. Caching **does not** handle multi-instance revocation automatically: `invalidateSubject` is only a hook to receive trusted events. An in-flight request calling the PDP before revocation could refill ALLOW after invalidation. For sensitive permissions requiring immediate revocation, disable ALLOW caching or build stricter version fencing/decision reconciliation.

`validUntil` must be decided by the PDP based on grant expiry/policy and verified by the PEP on every hit. Short DENY caches can also delay newly granted permissions from taking effect immediately, so document that in SLAs and tests. In production, normalize adapter errors into `PolicyUnavailableException`; never silently turn exceptions into ALLOW.

## 10. Method Security and Data-Layer Conditions

File `DocumentService.java` illustrates with table `documents(id, tenant_id, title, archived)`. It is invoked through a Spring-managed bean proxy with `@EnableMethodSecurity` as shown in section 7:

```java
package demo.policy;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final JdbcTemplate jdbc;

    public DocumentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("""
            hasAuthority('DOCUMENT_READ') and
            @policyGuard.canRead(authentication, #id)
            """)
    public String readTitle(@P("id") long id) {
        AccessPrincipal p = principal();
        List<String> titles = jdbc.query("""
                SELECT title FROM documents
                 WHERE id = ? AND tenant_id = ?
                """, (rs, i) -> rs.getString("title"),
                id, p.tenant());
        return titles.isEmpty() ? null : titles.get(0);
    }

    @Transactional
    @PreAuthorize("""
            hasAuthority('DOCUMENT_ARCHIVE') and
            @policyGuard.canArchive(authentication, #id)
            """)
    public boolean archive(@P("id") long id) {
        AccessPrincipal p = principal();
        int count = jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ? AND tenant_id = ?
                   AND archived = FALSE
                """, id, p.tenant());
        return count == 1;
    }

    private AccessPrincipal principal() {
        Authentication authentication = SecurityContextHolder
                .getContext().getAuthentication();
        return (AccessPrincipal) authentication.getPrincipal();
    }
}
```

`@P("id")` helps Spring SpEL recognize the `#id` parameter when built without `-parameters`. Functional permissions `DOCUMENT_READ`/`DOCUMENT_ARCHIVE` and the PDP decision are **simultaneous requirements**. Queries/updates also enforce tenant scoping; if the domain uses ACLs/owners, add the corresponding predicates. Never let callers pass someone else's tenant to the repository.

An ALLOW decision at `t1` and a database write at `t2` can race if permissions change. `@Transactional` manages DB transactions, not distributed transactions with the PDP. For high-risk actions, check version/permission at write time or enforce safe conditional updates. Calling methods via `this.method()` inside the same bean can bypass AOP interception; test real entry points.

## 11. Unit Tests and Integration Tests

Use a fake `PolicyClient` to test caching and fail-closed behavior independently of the network. In the same `demo.policy` package, the following JUnit 5 snippet can go into `PolicyGuardTest.java`:

```java
package demo.policy;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class PolicyGuardTest {
    static final Instant NOW =
            Instant.parse("2026-11-06T08:00:00Z");

    Authentication actor(String user, String tenant) {
        return UsernamePasswordAuthenticationToken.authenticated(
                new AccessPrincipal(user, tenant, 7L), "N/A",
                List.of(new SimpleGrantedAuthority("DOCUMENT_READ")));
    }

    @Test
    void cacheHitThenInvalidate() {
        AtomicBoolean allow = new AtomicBoolean(true);
        AtomicInteger calls = new AtomicInteger();
        PolicyClient fake = key -> {
            calls.incrementAndGet();
            return new PolicyReply(
                    allow.get(), NOW.plusSeconds(5), "p1", "d1");
        };
        PolicyGuard guard = new PolicyGuard(
                fake, Clock.fixed(NOW, ZoneOffset.UTC));

        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertEquals(1, calls.get());
        allow.set(false);
        guard.invalidateSubject("alice");
        assertFalse(guard.canRead(actor("alice", "t1"), 101));
        assertEquals(2, calls.get());
    }

    @Test
    void timeoutAndExpiredReplyDeny() {
        PolicyClient down = key -> {
            throw new PolicyUnavailableException("timeout");
        };
        PolicyGuard guard = new PolicyGuard(
                down, Clock.fixed(NOW, ZoneOffset.UTC));
        assertFalse(guard.canRead(actor("alice", "t1"), 101));
        assertFalse(guard.canArchive(actor("alice", "t1"), 101));

        PolicyClient expired = key -> new PolicyReply(
                true, NOW, "p1", "d2");
        assertFalse(new PolicyGuard(
                expired, Clock.fixed(NOW, ZoneOffset.UTC))
                .canRead(actor("alice", "t1"), 101));
    }

    @Test
    void keySeparatesTenantsAndResources() {
        AtomicInteger calls = new AtomicInteger();
        PolicyClient fake = key -> {
            calls.incrementAndGet();
            return new PolicyReply(
                    true, NOW.plusSeconds(5), "p1", "d1");
        };
        PolicyGuard guard = new PolicyGuard(
                fake, Clock.fixed(NOW, ZoneOffset.UTC));
        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertTrue(guard.canRead(actor("alice", "t2"), 101));
        assertTrue(guard.canRead(actor("alice", "t1"), 102));
        assertTrue(guard.canRead(actor("bob", "t1"), 101));
        assertEquals(4, calls.get());
    }
}
```

Run with Gradle in the corresponding module:

```bash
./gradlew test --tests demo.policy.PolicyGuardTest
```

This test verifies guard logic with a fake PDP, **not measuring real HTTP timeouts or testing Spring AOP/DB**. Use a mock HTTP server intentionally responding after 300 ms to test `HttpTimeoutException`; test HTTP 500/429, malformed JSON, `allowed=null`, and `validUntil==now`. With `@SpringBootTest`/`MockMvc`, obtain the service from the Spring context and use an authentication carrying `AccessPrincipal` instead of the string principal from `@WithMockUser`. After denied/timed-out requests, assert database and events remain unchanged.

## 12. Concurrency, Circuit Breakers, and Operations

`HttpClient.send` is a blocking call; if the PDP slows down, servlet threads can be held up to the timeout limit. High-throughput systems need **bulkheads/concurrency limits**, bounded queues, rate limits, and circuit breakers. When a breaker is OPEN or a bulkhead is full, requests must be blocked rather than bypassing authorization.

With WebFlux, never call a blocking HTTP client on the event loop; use a reactive client with timeouts and propagate SecurityContext properly via Reactor context, or use a bounded scheduler if blocking is unavoidable. Retries must stay within the request budget and never amplify load when the PDP is failing.

Logs should distinguish `ALLOW`, `DENY`, and `UNAVAILABLE`, source `PDP` vs. `CACHE`, action, policy version, decision ID, correlation ID, and latency. Protect PII and never log tokens/secrets. Metric labels should omit subjectId/resourceId (high cardinality). Track p95/p99 PDP latency, timeout ratio, cache hit/miss, stale ALLOW window, revocation lag, circuit breaker OPEN events, and writes occurring after denial (must be 0).

## 13. Test Matrix and Common Pitfalls

| Scenario | Expectation |
| --- | --- |
| ALLOW with matching identity/action/tenant | Only in-scope resources can be read/edited |
| PDP DENY | Method does not run, no writes/success events |
| Missing functional authority | `@PreAuthorize` blocks even if PDP might ALLOW |
| PDP timeout or connection refused | No side effects |
| HTTP 500/429, malformed JSON, empty body | Fail closed, do not cache ALLOW |
| ALLOW past `validUntil` | Do not use cache beyond this timestamp |
| Same user switching tenant/action/resource | Different cache key |
| Cache hit within TTL | No extra PDP call if action type permits caching |
| Revoke with invalidation event | Post-invalidation requests query PDP and deny |
| Dropped event/stale in-flight response | Does not violate SLA; sensitive actions require strong consistency |
| Admin/archiving | Bypasses cache; denies if PDP unavailable |
| Empty cache when breaker OPEN | Deny, never fall back to ALLOW automatically |
| High concurrent traffic | Bounded threads, queues, and connections |
| Session/JWT with old permissions | Behavior follows revocation SLA, never assuming permissions remain alive |
| Missing `@EnableMethodSecurity` | Tests must catch inactive method protection |
| DB tenant/owner changes mid-request | Predicates/transactions protect data scope |

Typical pitfalls: setting only connect timeout; caching per username; using `expireAfterAccess` to prolong permissions; returning `true` when the PDP fails; treating HTTP 200 without inspecting the body; omitting tenant checks in SQL; invalidating one node while assuming cluster-wide revocation; trusting a revision claim in an old JWT as the latest version; automatically returning ALLOW when the circuit breaker is OPEN; and testing only HTTP status without verifying the database.

## 14. Practice Exercises and Acceptance Criteria

**Exercise A — Deadline:** build a mock PDP responding after 600 ms with a 300 ms request timeout. Prove `archive` never runs, the database does not change, and logs distinguish the unavailable reason.

**Exercise B — Cache isolation:** Alice in tenant A reads 101, Bob in tenant A reads 101, Alice in tenant B reads 101, and Alice in tenant A reads 102. Distinct keys must yield distinct decisions; bump revision to test cache misses.

**Exercise C — Revocation:** let Alice read 101, revoke in PDP, emit invalidation, read again, and confirm denial. Repeat without invalidation to measure the stale window. Test an older PDP response arriving after invalidation to observe the need for version fencing.

**Exercise D — Risk tiering:** internal reads may accept a 2-second ALLOW cache, while archive/admin must query the PDP. Take the PDP down and verify expired cache entries are never reused and mutations never execute.

**Exercise E — Operations:** measure p99 latency, timeouts, cache hits, and revocation lag across multiple instances; tune timeouts, TTL, and concurrency to fit SLOs. Never lengthen TTL for sensitive permissions just to boost performance.

**Completion criteria:** the PEP obtains identity from an authenticated source, the PDP evaluates subject/action/resource/scope accurately, timeouts are bounded, no fail-open paths exist, cache keys and expiries are accurate, invalidation/races meet SLAs, method security truly takes effect, the DB checks tenant/owner, and tests verify ALLOW/DENY/timeout/revocation plus post-denial data state.

## References

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Java SE 17 — HttpClient.Builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 — HttpRequest.Builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Caffeine — Eviction: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Cleanup: https://github.com/ben-manes/caffeine/wiki/Cleanup
