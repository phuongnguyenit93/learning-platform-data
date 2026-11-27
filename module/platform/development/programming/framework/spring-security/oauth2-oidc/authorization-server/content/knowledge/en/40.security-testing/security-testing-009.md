# Testing load, rate limiting, and behavior during data store outages

An Authorization Server must preserve its security properties when traffic spikes or a storage component loses connectivity. Performance testing must therefore measure throughput and latency while confirming the system does not issue invalid tokens, bypass rate limits, or leak data when the database or token store fails.

This lesson focuses on Spring Authorization Server (SAS), covering heavily loaded endpoints such as the token endpoint, authorization endpoint, and JWK Set endpoint. Examples assume the application stores clients, authorizations, and consents in a relational database; Redis may be used for caching or rate limiting.

## 1. Defining test objectives and boundaries

Each grant type has distinct costs and characteristics. Never collapse all flows into a single load figure.

| Flow | Primary endpoint | What to observe |
|---|---|---|
| Client Credentials | POST /oauth2/token | Client authentication, access token creation and persistence |
| Authorization Code + PKCE | GET /oauth2/authorize, POST /oauth2/token | Session, consent, authorization code exchange |
| Refresh Token | POST /oauth2/token | Reading authorization, rotating refresh token if enabled |
| JWKS | GET /oauth2/jwks | Serving public keys, caching, and response time |
| Introspection / Revocation | Corresponding endpoint if enabled | Querying token state and revoking tokens |

A load run consisting solely of JWKS requests can achieve high throughput because public keys are usually cached; that result does not represent token issuance capacity when every request must read and write the database.

Set measurement goals before running tests:

- **Throughput:** successful requests per second (RPS), broken down by endpoint and grant type.
- **Latency:** p50, p95, p99; track time spent in the application and database.
- **Error rates:** distinguish expected authentication errors, 429 from rate limits, 5xx errors, and dependency timeouts.
- **Resources:** CPU, heap, garbage collection, thread counts, connection pools, database connections, and Redis.
- **Correctness:** never issue tokens on failed requests; never lose authorization/consent records; revoked tokens follow policy.
- **Resilience:** after dependencies recover, the system handles normal load again.

SLOs must tie to specific loads and environments—for example, Client Credentials p95 below an agreed threshold at 300 RPS for 15 minutes. Never apply one generic threshold across all systems.

## 2. Designing repeatable workloads

### 2.1 Preparing data

Create dedicated test data with enough clients to prevent a single client from skewing results. Include clients using Client Credentials, public clients using Authorization Code + PKCE, clients with small and large scope sets, and varying TTL settings. Never place real secrets or production tokens in load scripts.

### 2.2 Load phases

1. **Baseline:** low load to verify correct flows and capture baseline latency.
2. **Ramp-up:** gradually increase load to find where p95/p99 spikes sharply.
3. **Sustained load:** hold target load to uncover resource leaks, pool exhaustion, or data accumulation.
4. **Spike:** sudden load surges to test autoscaling and protective controls.
5. **Stress:** push beyond expected load within test environment limits to characterize degradation behavior.
6. **Recovery:** reduce load and confirm latency, error rates, and connection pools return to normal.

Run each workload individually before running mixed workloads. For mixed workloads, explicitly document weights—such as 60% Client Credentials, 25% refresh token, 10% authorization code exchange, and 5% JWKS. Replace illustrative weights with anonymized production usage ratios.

### 2.3 Example k6 script for Client Credentials

The following script illustrates generating load against the token endpoint. Pass the endpoint and test client credentials via k6 environment variables; never commit secrets to the repository.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import encoding from 'k6/encoding';

export const options = {
  stages: [
    { duration: '2m', target: 20 },
    { duration: '5m', target: 100 },
    { duration: '10m', target: 100 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
  },
};

const tokenUrl = __ENV.TOKEN_URL;
const clientId = __ENV.CLIENT_ID;
const clientSecret = __ENV.CLIENT_SECRET;
const scope = __ENV.SCOPE || 'api.read';
const basic = encoding.b64encode(clientId + ':' + clientSecret);

export default function () {
  const response = http.post(
    tokenUrl,
    'grant_type=client_credentials&scope=' + encodeURIComponent(scope),
    {
      headers: {
        Authorization: 'Basic ' + basic,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      tags: { endpoint: 'token', grant_type: 'client_credentials' },
    },
  );

  check(response, {
    'token endpoint returns 200': (r) => r.status === 200,
    'response contains access_token': (r) => {
      try { return Boolean(r.json('access_token')); } catch (_) { return false; }
    },
    'response contains token_type': (r) => {
      try { return Boolean(r.json('token_type')); } catch (_) { return false; }
    },
  });

  sleep(1);
}
~~~

Thresholds in this example are illustrative only. Set thresholds according to your SLOs and test environment hardware. Adjust sleep and virtual user counts depending on your goal: measuring raw throughput versus simulating realistic client behavior.

## 3. Testing rate limiting

Rate limiting protects the Authorization Server against buggy clients, credential stuffing, token harvesting, and traffic spikes. Policies must define the rate-limit key, time window, limit level, response upon exceeding limits, and behavior when distributed counters are unavailable.

### 3.1 Choosing rate-limit keys

| Endpoint / flow | Applicable keys | Notes |
|---|---|---|
| Token endpoint | Authenticated client ID; IP as an additional defense layer | Avoid letting one large NAT lock out all legitimate clients |
| Authorization endpoint | IP, session, and risk signals | Avoid locking out users after a few legitimate actions |
| JWKS | Proxy/CDN caching and global limits | Do not count every public key fetch like a token issuance |
| Introspection | Authenticated client and per-resource-server quota | Short caching depending on revocation requirements |
| Revocation | Authenticated client and IP | Keep limits generous enough to handle revocation incidents |

For the token endpoint, using IP alone can cause false positives when multiple services share a NAT. Using client ID alone is insufficient against unauthenticated requests or distributed attacks. You can combine an aggregate pre-authentication IP limit with post-authentication per-client quotas.

### 3.2 Responses when limits are exceeded

When limits are exceeded, return HTTP 429 Too Many Requests. If wait duration can be calculated, send `Retry-After` in a valid HTTP format. OAuth responses must remain consistent with the system's error policy; never return stack traces, internal state, or sensitive secrets.

Clients should honor `Retry-After`, use exponential backoff with jitter, and distinguish 429 from credential errors, client configuration errors, or transient 5xx errors. Never retry indefinitely, as that amplifies load.

Never blindly retry authorization code exchanges: codes are typically single-use. If a client cannot tell whether a request completed due to a timeout, apply a recovery workflow suited to the authorization state instead of repeatedly resending the code.

### 3.3 Rate-limit test cases

For each policy, verify:

1. Just below the limit: valid requests continue succeeding.
2. At the threshold: behavior matches window and algorithm definitions.
3. Above the threshold: returns 429 and issues no tokens.
4. After wait window expires: quota recovers accurately per window.
5. Two distinct clients: client A's quota does not exhaust client B's quota when policies are independent.
6. Multiple instances: quota is enforced consistently cluster-wide.
7. High concurrency: no race condition lets request counts significantly exceed the quota.
8. Redis outage: behavior matches the declared fail-open or fail-closed choice.

If using Redis as a counter, incrementing and setting TTL must be atomic. Avoid executing INCR and EXPIRE as two separate commands without guarantees, because an instance could crash between commands and leave a key that never expires. Use a Lua script or atomic primitives appropriate to your library. With token buckets or sliding windows, also test window boundaries and clock drift between nodes.

### 3.4 Enforcement placement

Rate limiting can live at an API gateway, reverse proxy, or inside the application. Gateways are convenient for IP-based limits and early protection; applications can enforce quotas per authenticated client. If using both, clearly define ordering and total limits to avoid unintentionally double-limiting.

In Spring Security, rate-limiting filters must sit in the proper position in the security filter chain and apply only to intended endpoints. Define how IPs are extracted from trusted proxies; never trust arbitrary client-supplied `X-Forwarded-For` headers directly. Test both paths through the gateway and direct calls to the application if the architecture allows them.

## 4. Testing behavior during data store outages

Spring Authorization Server can rely on multiple storage backends. Map data and dependencies before injecting faults:

| Component | Data | Impact when unreachable |
|---|---|---|
| RegisteredClientRepository | Clients, grant types, redirect URIs, scopes | Cannot authenticate or load new client configurations |
| OAuth2AuthorizationService | Authorizations, access tokens, refresh tokens, authorization codes | Cannot persist tokens or look up state |
| OAuth2AuthorizationConsentService | User consents | Cannot read or save consents |
| Database / transaction manager | Transactions and consistency | Transactions may roll back or time out |
| Redis / rate-limit store | Quota counters, caches | Loss of distributed quota enforcement or caching |
| Key store / KMS | Signing keys and encryption keys | May be unable to sign or decrypt data |

A system might store JWT signing keys in a local keystore while storing authorizations in a database. Being able to sign JWTs does not mean tokens can be issued safely: if saving the authorization fails, the token endpoint must handle the error and never return tokens the system cannot manage per policy. If signing keys reside in a KMS, a KMS outage can directly impact token signing.

### 4.1 Fail-safe principles

Fail-open versus fail-closed decisions must be made per capability:

- **Token issuance:** if mandatory state cannot be persisted or transaction success cannot be confirmed, do not return a successful token.
- **Client lookup and redirect URI checks:** never automatically accept unverified configurations when the repository is unreachable.
- **Consent:** never skip consent requirements simply because the consent store fails.
- **Introspection:** if status cannot be verified per policy, never assert the token is active.
- **Revocation:** if revocation state cannot be recorded, report an appropriate error; never fabricate a successful revocation confirmation.
- **Rate limiting:** choose fail-open or fail-closed based on risk. For sensitive token-issuance endpoints, fail-closed is usually safer, though you must weigh how a Redis outage affects widespread token issuance.
- **JWKS:** if current public keys can be served safely from cache without violating policy expiration, cached keys may continue being served briefly. Never generate or publish invalid keys to mask a key store outage.

Never turn a dependency error into a 200 response with an empty body or a fake token. Never return exception details, SQL, internal hostnames, or credentials to clients.

### 4.2 Fault injection matrix

| Incident | How to simulate in test environment | Outcomes to verify |
|---|---|---|
| Database refuses connections | Stop database or block connections from application | Token flows fail cleanly; no unpersisted tokens issued |
| Increased database latency | Inject proxy delay or constrain resources | Bounded timeouts; pool does not hang indefinitely; p99 recorded |
| Database drops connection mid-transaction | Sever connection while writing authorization | Rollback or consistent state; no false success responses |
| Redis unavailable | Stop node or block port | Rate limiting follows fallback policy |
| Redis slow | Inject network latency | Threads not held indefinitely; timeouts and metrics reflect impact |
| KMS / key store error | Mock endpoint failure or deny test permissions | Never signs with out-of-policy keys; errors categorized properly |
| Single application node isolated | Block network traffic from one instance | Remaining nodes operate per architecture; load balancer ejects unhealthy node if configured |

Prefer fault injection in an isolated environment. Start with one dependency and one failure type; only then combine faults with load. Record fault start time, recovery time, in-flight request count, and failed request count to correlate logs, traces, and metrics.

### 4.3 Timeouts, connection pools, and transactions

Tests must verify bounded timeouts across layers: connect, read, pool connection acquisition, and transaction timeout. If application timeouts exceed load balancer timeouts, clients may receive errors before the application knows whether a transaction completed. If the pool allows unbounded waits, a slow database can tie up every request thread.

Monitor active/idle/pending connections, connection wait time, query latency, timed-out queries, transaction rollbacks, request timeouts, thread pools, and request queues.

Circuit breakers can stop the application from hammering a failing dependency. Explicitly define which exceptions count as failures, open duration, probe request counts, and recovery rules. Avoid retrying non-idempotent writes without idempotency guarantees, as uncertain transaction outcomes can produce unpredictable state.

## 5. Building integration tests

Unit tests verify how the application reacts to mocked exceptions, but cannot prove connection pool, transaction, or network behavior. Combine three layers:

- **Unit tests:** verify fail-open/fail-closed policies, error mapping, and rate-limit rules.
- **Integration tests:** use containerized real databases/Redis to test repositories, transactions, and multi-instance quotas.
- **Load/fault tests:** drive HTTP load while actively slowing or severing dependencies.

You can use Testcontainers to run the same database and Redis engines as deployment. To simulate network faults and latency, place Toxiproxy between the application and dependencies. Tests must control proxy toggles cleanly and always restore dependencies after assertions.

A token-issuance test during database outage should verify:

1. Send a valid Client Credentials request while the database is healthy and confirm a token is issued.
2. Block database connectivity.
3. Resend the request and confirm an appropriate error is returned within bounded response time.
4. Confirm the response contains no access token.
5. Confirm logs contain no client secrets or tokens.
6. Restore the database and send a new request.
7. Confirm the system recovers and functions without requiring a manual restart.
8. Inspect authorization data to verify no half-written records remain.

With Redis, run multiple application instances against one shared store to verify cluster-wide quotas. If each instance uses local counters, allowed total requests multiply by instance count. For example, a 100-request/minute per-node quota across three nodes accidentally permits 300 requests/minute.

## 6. Observing and diagnosing results

Test results must show where the system slows down and why. Use metrics with bounded-cardinality labels; never place access tokens, refresh tokens, authorization codes, client secrets, session IDs, or user IDs into metric labels.

| Category | Metrics / data |
|---|---|
| HTTP | Request count, status code, latency histogram by endpoint and grant type |
| OAuth | Token issuances, grant errors, client authentication errors, refresh/revocation counts |
| Rate limit | Rate-limited requests, store connection errors, counter operation latency |
| Database | Pool active/idle/pending, query latency, timeouts, rollbacks |
| Redis | Command latency, connection errors, timeouts, memory and evictions |
| JVM | Heap, GC pauses, CPU, threads, and request queues |
| Resilience | Circuit breaker state, retry counts, dependency health |

Logs should include correlation IDs linking requests to traces. Record grant type, endpoint, outcome, and normalized internal error codes; avoid logging credentials or tokens. For OAuth errors, separate business errors such as `invalid_client`, `invalid_grant`, and `invalid_scope` from internal dependency failures. Never let dashboards lump 429, 4xx auth errors, and 5xx into one aggregate error rate.

When p99 rises, correlate token endpoint traces against client authentication duration, repository queries, authorization writes, and token signing. If connection pool wait time rises alongside database latency, increasing application thread counts usually fails to fix the root cause and can worsen contention.

## 7. End-to-end test scenarios

| ID | Scenario | Expected outcome |
|---|---|---|
| ST-01 | Client Credentials baseline load | Valid tokens; latency and error rate within SLO |
| ST-02 | Gradual ramp-up on token endpoint | Saturation point identified; resources do not grow unboundedly |
| ST-03 | Concurrent load from multiple clients | Per-client quotas and data remain isolated |
| ST-04 | Exceeding token endpoint quota | 429; no tokens created; appropriate retry info provided |
| ST-05 | Multiple nodes enforcing quota | Total cluster quota matches policy |
| ST-06 | Redis outage | Fail-open/fail-closed behavior matches design |
| ST-07 | Database down before token request | Controlled failure; no token returned |
| ST-08 | Database disconnects mid-write | No partial authorization state causing bad token issuance |
| ST-09 | Slow database under load | Bounded timeouts; pools and threads recover |
| ST-10 | Database and Redis recovery | Requests succeed again; no unexpected restarts needed |
| ST-11 | JWKS during authorization database outage | JWKS operates from its key source; serving keys is not confused with issuing tokens |
| ST-12 | Mixed load with fault injection | SLOs, protective limits, and degradation behavior hold |

ST-11 applies only if signing keys are managed independently from the authorization database. Adapt scenarios to your actual architecture.

## 8. Procedure for executing a test run

1. Record application version, Spring configuration, pool settings, database/Redis versions, instance count, and gateway configuration.
2. Prepare test clients and data; verify OAuth flows work at low load.
3. Run baselines per grant type and endpoint.
4. Run ramp-up and sustained load; archive raw results, dashboards, and sample traces.
5. Enable rate limits; re-run below threshold, at threshold, and above threshold.
6. Run multi-instance workloads to verify distributed quotas.
7. Run fault injection per dependency at low load, then repeat at target load.
8. Restore dependencies; confirm data, quotas, connection pools, and latency return to normal.
9. Compare results against SLOs; document load, environment, config, and any deviations.
10. Create remediation items with owners and re-measurement criteria.

Never compare two runs across differing hardware, instance counts, datasets, application versions, or workload mixes without explicitly noting differences. Archive scripts, run parameters, and mock data versions to reproduce results.

## 9. Completion criteria

A test cycle meets requirements when:

- Every critical endpoint and grant type has its own baseline and load results.
- Latency, throughput, and error rate SLOs are measured under defined workloads.
- Rate limits behave accurately below threshold, at threshold, above threshold, and across multiple instances.
- Database, Redis, and key store outages are simulated; responses follow the chosen policy.
- No tokens are returned when mandatory persistence fails.
- Timeouts and pools are bounded; the application never hangs indefinitely when dependencies slow down.
- After dependencies recover, the system resumes operation and data remains consistent.
- Logs, metrics, and traces are sufficient for root-cause analysis without exposing credentials or tokens.
- Results are reproducible from archived scripts, configurations, and test data.

Load testing and fault injection establish the operational boundaries of an Authorization Server. Use the findings to tune quotas, timeouts, connection pools, caches, instance counts, and SLOs; after every significant change, re-run workloads to confirm the impact.
