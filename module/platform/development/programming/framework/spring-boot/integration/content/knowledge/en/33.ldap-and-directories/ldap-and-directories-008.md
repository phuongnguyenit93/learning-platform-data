# Timeouts, Pooling, and Directory Server Errors

## 1. The Problem in Spring Boot Integration

A **Spring Boot Integration** service synchronizes employee accounts from LDAP/Active Directory (AD), checks permissions before calling internal APIs, and writes results to a database or broker. Along the integration path, several hard-to-distinguish situations can arise: a domain controller stops responding; an idle connection in the pool has died; the application's bind account password expired; LDAP returns a referral; or an overly broad query hits server limits.

Each situation demands a different response. Without timeouts, an HTTP or message-processing thread can block indefinitely. Without pool connection validation, users hit sporadic failures after idle periods. Retrying every error blindly can repeat bad passwords and trigger account lockouts. Treating an LDAP timeout as "employee not found" can accidentally delete cached data or corrupt sync state.

This lesson focuses on **three control layers**:

1. **Timeouts:** bounding connection setup, response wait, context borrowing, and total flow duration.
2. **Pooling:** reusing `DirContext` instances when appropriate, enforcing caps, and evicting broken connections.
3. **Directory server errors:** classifying, recording, controlled retrying/failover, and preserving data contracts.

### Illustrative Flow

~~~mermaid
flowchart TD
    A[HTTP / Kafka / Scheduled sync] --> B[EmployeeDirectoryAdapter]
    B --> C{Circuit breaker allows?}
    C -- No --> H[Return DirectoryUnavailable / defer message]
    C -- Yes --> D[Borrow DirContext from pool]
    D --> E{Pool has available context?}
    E -- No --> H
    E -- Yes --> F[LDAP search with timeout]
    F --> G{Outcome}
    G -- Found --> I[Map internal profile]
    G -- Valid not found --> J[Not found per contract]
    G -- Server timeout / disconnect --> H
    G -- Bad credentials / schema / referral --> K[Classify, handle separately]
    I --> L[DB / HTTP / Broker]
~~~

**Design principle:** "LDAP has no matching record" can be confirmed only after **a search operation completes successfully** over the right scope. Connection errors, timeouts, or partial results represent an *uncertain* state and must never be turned into an empty list.

## 2. Timeout Layers You Need to Know

Spring's LDAP client typically layers **Spring LDAP → JNDI → socket → directory server**. Time limits operate at different layers and do not replace one another.

| Limit | Applies to Which Step? | Illustrative Config | When Expired |
| --- | --- | --- | --- |
| TCP/connect timeout | Establishing connection to an LDAP host | `com.sun.jndi.ldap.connect.timeout=2000` | Socket not established in time; may try next endpoint per provider/topology |
| LDAP read timeout | Waiting for LDAP response after sending operation | `com.sun.jndi.ldap.read.timeout=5000` | Aborted client-side; server outcome is not guaranteed to have failed |
| SearchControls time limit | Search duration limit at search/JNDI level | `SearchControls#setTimeLimit(3000)` | May throw time limit error; never treat partial data as complete |
| Pool borrow timeout | Waiting for a free `DirContext` when pool is full | `PoolConfig#setMaxWaitMillis(750)` | Could not borrow a context in allotted time |
| Overall request/job deadline | Budget for LDAP + checks + DB/API/broker | Service/caller timeout | Stop/mark work overdue, control retries |
| Server-side search limit | Server limit enforced per bind/query | LDAP server size/time limit policy | Server rejects or returns partial results |

### 2.1. JDK LDAP Provider Connect and Read Timeouts

With the **JNDI LDAP provider built into the JDK**, two common properties are:

~~~properties
com.sun.jndi.ldap.connect.timeout=2000
com.sun.jndi.ldap.read.timeout=5000
~~~

Units are **milliseconds**, formatted as positive integer strings. They are **JDK provider-specific properties**, not standard names every LDAP client must honor. Without a connect timeout, JNDI may wait for OS network timeouts. Without a read timeout or with values `<= 0`, reads may block indefinitely depending on provider behavior. Some custom socket factories may ignore connect timeouts; test carefully when customizing the TLS/socket layer.

Never confuse `connect.timeout=2000` with "the entire LDAP query finishes in under 2 seconds": after TCP connects, bind/TLS, search execution, transfer, and result reading each take time. With multiple LDAP URLs, each endpoint attempt consumes budget; total duration can exceed a single connection timeout.

### 2.2. Business-Level Deadlines

Suppose an HTTP endpoint has a 3-second SLA. Setting an LDAP read timeout of 10 seconds and a pool borrow timeout of 5 seconds means LDAP alone can blow the SLA. A sound initial budget accounts for:

~~~text
Request budget ≈ pool-wait + connect/TLS/bind + search/read
                 + mapping time + downstream DB/HTTP
                 + safety margin for retries/serialization
~~~

For example, starting values in a load-tested setup: max pool wait `500 ms`, connect timeout `1,500 ms`, read timeout `3,000 ms`, full request `5,000 ms`. These are purely *illustrative* numbers, not universal optimums. With retries or multiple DCs, recalculate the total budget instead of summing unbounded attempts.

Setting a timeout at the HTTP/controller layer **does not automatically cancel a blocking LDAP socket call**; enforce limits in JNDI and manage thread/concurrency caps. Conversely, cancelling a future does not prove the server aborted an ongoing search or attribute modification.

### 2.3. Search Time Limits and Size Limits

`SearchControls.setTimeLimit(...)` and `setCountLimit(...)` bound searches issued by the application. When looking up a single employee by fixed ID, cap results (e.g., 2 to still catch duplicate data) and keep the search base narrow. However, the server enforces its own policies; on `TimeLimitExceededException`, `SizeLimitExceededException`, or `PartialResultException`, never assume returned results are complete.

## 3. Configuring Timeouts in Spring Boot

With `spring-boot-starter-data-ldap`, Spring Boot can auto-configure `LdapContextSource` and `LdapTemplate`. Example using LDAPS in an operational environment:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
~~~

~~~yaml
# application.yml
spring:
  ldap:
    urls:
      - ldaps://ldap-a.example.internal:636
      - ldaps://ldap-b.example.internal:636
    base: dc=example,dc=internal
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    referral: ignore
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "2000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

| Property | Effect |
| --- | --- |
| `spring.ldap.urls` | List of LDAP server URLs for creating contexts; supports trying another endpoint if one is unavailable |
| `spring.ldap.base` | Base DN for operations; DNs in `LdapTemplate` APIs are typically relative to this base |
| `spring.ldap.username/password` | *Service account* identity used for reads/operations per granted permissions |
| `spring.ldap.referral` | Referral handling strategy; choose `ignore`/`follow`/`throw` after understanding topology |
| `spring.ldap.base-environment.*` | JNDI environment properties, such as JDK LDAP provider timeouts |

JNDI keys are wrapped in brackets and quotes to **preserve dots** when Spring Boot binds the map into the `DirContext` environment. Never mistakenly write `spring.ldap.connect-timeout` expecting Boot to configure timeouts automatically: this example uses `base-environment` to pass the exact two JNDI provider keys.

### 3.1. LDAPS and StartTLS Security

`ldaps://` protects the connection with TLS from the beginning. Plain LDAP (`ldap://`) must never transmit bind passwords in cleartext over the network. In Spring Boot versions supporting LDAP SSL bundles, `spring.ldap.ssl.bundle` can point to a bundle with trust material; check that version's documentation for LDAPS support. **StartTLS** upgrades an existing `ldap://` connection and requires a corresponding `DirContextAuthenticationStrategy`/socket setup; never conflate StartTLS with LDAPS or mix their configurations.

Use only valid certificates and managed truststores; **never disable certificate/hostname verification** just to silence connection errors. In production, grant the service account least privilege, supply secrets from a secret manager, plan rotations, and never log password DNs or sensitive attribute values.

### 3.2. Multiple URLs Provide Failover, Not Absolute HA Guarantees

A list in `spring.ldap.urls` supports connecting to multiple endpoints, yet:

- There is no guarantee requests load-balance evenly across DCs.
- An already-open TCP context does not migrate seamlessly mid-call when that server goes down.
- A pool may still hold dead contexts after network drops or failover.
- Multiple DCs may have replication lag; a read right after a write may see stale data if hitting another endpoint.
- Bind errors from wrong passwords or bad certificates **must not** be treated as "server overloaded" and retried endlessly.

High availability requires combining multiple endpoints, sound DNS/health checks, finite timeouts, borrow-time validation, conditional retries, and real monitoring. With Active Directory, understand domain controllers, Global Catalog, referrals, child domains, and replication latency.

## 4. Connection Pooling: Benefits, Limits, and Choices

Creating an LDAP connection involves TCP, TLS, and a service account bind. For frequent short queries, that setup cost adds up. Pooling reuses `DirContext` instances and caps concurrent connections to the directory server.

### 4.1. Comparing Three Options

| Option | Characteristics | Best Fit |
| --- | --- | --- |
| No pooling | Each operation opens/borrows and closes a context; simple, no stale connections | Low traffic, early testing, or binds with constantly changing credentials |
| JNDI native pooling | Enabled via `LdapContextSource.setPooled(true)`; many settings live in JVM system properties | Simple needs where JNDI limits are understood |
| Spring LDAP Commons Pool 2 | `PooledContextSource` wraps a `ContextSource`; total/per-key caps, wait timeout, validation, eviction | Services doing high-volume lookups/binds via a fixed service account needing pool visibility and control |

Spring LDAP **disables JNDI pooling by default**. Never enable both native JNDI pooling and Spring LDAP pooling on the same target context: two stacked pools hide dead connections and make metrics unreliable.

### 4.2. Pool Sizing Parameters

| PoolConfig | Meaning |
| --- | --- |
| `maxTotal` | Total contexts in the pool, active plus idle |
| `maxTotalPerKey` | Limit per context type/key; read-only and read-write can use separate pools |
| `maxIdlePerKey` | Max idle contexts per key |
| `minIdlePerKey` | Minimum idle contexts per key when supported |
| `maxWaitMillis` | Maximum time to wait when exhausted and pool is busy |
| `testOnBorrow` | Validate context before handing it to a query |
| `testWhileIdle` | Periodically validate idle contexts to evict dead connections |
| `timeBetweenEvictionRunsMillis` | Interval for the idle connection evictor/validator |

Suppose an app has 10 message-processing threads, each using at most one LDAP context at a time. Start around `maxTotal=12`, `maxTotalPerKey=12`, and `maxWaitMillis=750`, then measure active connections, waiters, and P95 latency. **Never** blindly set 100 connections per pod across 50 pods: 5,000 total connections can overwhelm the directory server.

### 4.3. Spring LDAP Pool 2 Example with Validation

Spring LDAP provides `PooledContextSource` backed by Apache Commons Pool 2. With `spring-ldap-core` from the starter, ensure a compatible `commons-pool2` is on the runtime classpath:

~~~xml
<dependency>
  <groupId>org.apache.commons</groupId>
  <artifactId>commons-pool2</artifactId>
</dependency>
~~~

Spring Boot dependency management/BOM selects the version; cross-check your project's BOM if customizing dependency management.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class DirectoryPoolConfig {

    @Bean
    @Primary
    PooledContextSource pooledDirectoryContextSource(
            LdapContextSource bootConfiguredTarget) {

        // Each JVM/pod has its own pool; compute the total across the deployment.
        PoolConfig config = new PoolConfig();
        config.setMaxTotal(12);
        config.setMaxTotalPerKey(12);
        config.setMaxIdlePerKey(6);
        config.setMinIdlePerKey(0);
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(750);

        // Detect dead contexts from server restarts, firewalls, or closed TLS.
        config.setTestOnBorrow(true);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(30_000);
        config.setMinEvictableIdleTimeMillis(60_000);

        // Boot's target already holds urls/base/bind DN/timeouts.
        // Keep native JNDI pooling off to avoid stacking two pools.
        PooledContextSource pooled = new PooledContextSource(config);
        pooled.setContextSource(bootConfiguredTarget);
        pooled.setDirContextValidator(new DefaultDirContextValidator());
        return pooled;
    }
}
~~~

The `@Primary` bean tells Spring to inject `PooledContextSource` when auto-configuring `LdapTemplate`, while the underlying `LdapContextSource` remains the target. This is the Spring Boot documented pattern; verify auto-configuration and bean resolution on your exact Boot version. If multiple directory tenants or `LdapTemplate`s exist, use explicit qualifiers instead of marking every context source primary.

**`DefaultDirContextValidator`** runs a lightweight check query before reusing a context (by default searching `objectClass=*` at the relative base for one result). On AD or subtrees disallowing base queries, configure an appropriate validation base/filter, or validation will fail continuously even on healthy connections. `testOnBorrow=true` improves reliability at the cost of an extra round-trip; measure actual latency before keeping it enabled for every lookup.

Spring LDAP can invalidate a context upon encountering non-transient exceptions like communication failures. However, a freshly borrowed context does not guarantee the upcoming operation succeeds: the server can still stall mid-search. Therefore **pool validation + read timeout + bounded retries** must be designed together.

### 4.4. Why Never Reuse the Same Pool for End-User Password Binds?

Pools work best for queries under **one stable service account**. If each HTTP request binds with a different user identity, reusing contexts under the wrong principal risks errors or security boundary violations. Never wrap an `LdapContextSource` using a per-thread `AuthenticationSource` inside a shared pool.

For end-user password authentication, use a dedicated context per credential check or Spring Security LDAP's dedicated authentication mechanism; never let one user's cached authenticated context serve another user. Password changes and account locks must take effect immediately per security policy without relying on stale pre-authenticated contexts.

Also note two easily confused names in Spring LDAP:

- `org.springframework.ldap.pool.factory.PoolingContextSource` (legacy Commons Pool 1).
- `org.springframework.ldap.pool2.factory.PooledContextSource` (Commons Pool 2, used in this example).

Check your Spring LDAP version's API before copying setters and defaults. Never confuse `PooledContextSource` with JNDI native pooling (`LdapContextSource#setPooled(true)`).

### 4.5. Controlling Pool Exhaustion

When all 12 contexts are borrowed and the 13th request arrives:

~~~text
request --> borrow context
             |
         pool full?
          /       \
        No        Yes
         |         |
     use now    wait up to 750 ms
                   |
               context returned?
                /          \
              Yes           No
               |             |
          validate/use   pool borrow failure
~~~

Without a finite `maxWaitMillis`, threads queue indefinitely, rendering overall flow timeouts ineffective. With automatic retries, single requests may consume multiple borrows and exhaust the pool faster. Cap in-flight LDAP operations at the application layer, monitor active/idle/waiter counts, and fail fast when a circuit breaker is open.

## 5. Classifying LDAP Errors for Correct Handling

Spring LDAP translates checked `javax.naming.NamingException`s from JNDI into runtime exceptions under `org.springframework.ldap.*`. Never catch `javax.naming.AuthenticationException` when calling through `LdapTemplate`, which throws Spring exceptions.

| Error / Signal | Likely Cause | Retry Immediately? | How to Handle |
| --- | --- | --- | --- |
| `org.springframework.ldap.CommunicationException` | Dropped connection, closed socket, unreachable server, network timeout | Conditionally, bounded count | Invalidate context, retry with backoff/jitter, switch endpoint if appropriate |
| `ServiceUnavailableException` | Directory server unavailable or temporarily overloaded | Conditionally | Check server/bind/throttling; trip circuit breaker on sustained errors |
| `AuthenticationException` | Wrong bind DN/password, account locked/expired, or auth policy | Do not retry same credentials | Separate service account errors from user creds; alert/rotate secret if needed |
| `NoPermissionException` | Account lacks permission on DN/attribute | Do not retry | Fix ACL/bind identity; avoid logging sensitive details |
| `NameNotFoundException` | Base DN or entry does not exist | Do not retry endlessly | Distinguish valid "user not found" from wrong base/config |
| `InvalidNameException` / `InvalidSearchFilterException` | Malformed DN or filter | Do not retry | Fix mapping/filter; escape external inputs |
| `SizeLimitExceededException` | Search exceeded server/client entry cap | Usually no | Narrow search base/filter, paginate |
| `TimeLimitExceededException` | Server/client search time limit exceeded | Policy-dependent | Optimize filter/indexes, narrow scope, or raise limit with justification |
| `PartialResultException` | Referrals or incomplete results, common in some AD topologies | Never treat as empty result | Configure referral handling properly; flag uncertain completeness |
| `SchemaViolationException` / `AttributeModificationException` | DN/attribute update violates schema | Do not retry | Fix payload or business operation |
| `DataAccessResourceFailureException` on pool borrow | Pool exhausted, validation failed, or context creation error | Conditionally after backoff | Monitor pool wait, evict dead contexts, reduce concurrency |
| TLS certificate / hostname error | Invalid trust chain, expired cert, hostname mismatch | Do not retry same config | Fix trust/cert/DNS; never disable TLS verification |

**Never treat a "single exception class" as an absolute rule.** Connectivity faults can be wrapped inside Spring data access exceptions, pool exceptions, or underlying TLS errors; inspect the `cause chain` and provider LDAP error code. Likewise, `NameNotFoundException` during a specific DN lookup might mean "not found," whereas during a people search after an OU rename it indicates a serious configuration failure.

### 5.1. Separating Application Binds from User Binds

Two requests may hit authentication errors with completely different meanings:

1. **Application connecting to LDAP with its service account:** a bind error breaks *all* lookups. Alert operations, mark the dependency unhealthy per policy, and never return "user does not exist."
2. **User logging in with personal credentials:** a bad password is an invalid login for that request—never retry the same password repeatedly; enforce IdP/AD security policies and avoid leaking "whether user exists" in public responses.

Keep context sources/call paths, permissions, and logging separate for the two bind types. Never reuse the service account pool to bypass lockout protections during user authentication.

### 5.2. Referrals, PartialResultException, and Multi-Domain Searches

A directory can return a referral to another naming context or domain controller. Spring Boot exposes `spring.ldap.referral`, and LDAP providers support:

- `ignore`: do not auto-follow referrals; depending on provider/server, may throw `PartialResultException`.
- `follow`: chase the referral, incurring extra connections/TLS/binds, latency, and trust/credential rules.
- `throw`: surface the referral error for the caller to handle.

In multi-domain AD setups, understand OUs, naming contexts, Global Catalog, and replicated attributes. Never set `spring.ldap.template.ignore-partial-result-exception=true` just to "silence errors" and then assume data is complete. Ignore partial results only when business logic **truly tolerates incomplete lists** and has alerting/telemetry.

## 6. Integration Example: Looking Up Employee Profiles with Clear Bounds and Errors

The adapter below forms the boundary between Spring Boot and the directory server. It returns `Optional.empty()` **only when the LDAP search completes normally with zero matches**; on connectivity errors, it throws a transient domain exception so the HTTP/message layer decides retries.

~~~java
// DirectoryProfile.java
public record DirectoryProfile(
        String uid,
        String displayName,
        String email) {
}
~~~

~~~java
// DirectoryTemporarilyUnavailable.java
public class DirectoryTemporarilyUnavailable extends RuntimeException {

    public DirectoryTemporarilyUnavailable(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
// EmployeeDirectoryAdapter.java
import java.util.List;
import java.util.Optional;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Component;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Component
public class EmployeeDirectoryAdapter {
    private final LdapTemplate template;

    public EmployeeDirectoryAdapter(LdapTemplate template) {
        this.template = template;
    }

    public Optional<DirectoryProfile> findByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid format");
        }

        // Query only a known OU, bounding result count and search duration.
        // base is relative to spring.ldap.base.
        LdapQuery lookup = query()
                .base("ou=people")
                .countLimit(2)
                .timeLimit(3_000)
                .attributes("uid", "cn", "mail")
                .where("uid").is(uid);

        try {
            List<DirectoryProfile> results = template.search(
                    lookup,
                    (AttributesMapper<DirectoryProfile>) attrs ->
                            new DirectoryProfile(
                                    getValue(attrs, "uid"),
                                    getValue(attrs, "cn"),
                                    getValue(attrs, "mail")));

            if (results.isEmpty()) {
                return Optional.empty();
            }
            if (results.size() != 1) {
                throw new IllegalStateException(
                        "LDAP returned multiple profiles for the same uid");
            }
            return Optional.of(results.get(0));
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DirectoryTemporarilyUnavailable(
                    "Unable to connect to or read from directory server", ex);
        }
    }

    private static String getValue(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : String.valueOf(attribute.get());
    }
}
~~~

**Rationale behind code choices:**

- `LdapQueryBuilder.where("uid").is(uid)` generates a properly escaped filter, preventing filter string concatenation from HTTP input (LDAP injection).
- `.base("ou=people")` narrows scope within `spring.ldap.base` instead of scanning the entire directory.
- `.attributes(...)` limits returned fields, reducing exposure and bandwidth.
- `.countLimit(2)` detects duplicate entries when mapping assumptions break. If the server throws `SizeLimitExceededException` per policy, the adapter must surface the limit error rather than claiming "not found."
- `.timeLimit(3_000)` is the search time limit, while the 5,000 ms read timeout still guards waiting for provider responses. These are two distinct limit layers.
- Missing `mail` values map to `null`; business validation should enforce required fields before writing to the DB or emitting messages.

**Confirm actual schema:** Active Directory usually uses `sAMAccountName` or `userPrincipalName` rather than `uid`. This example illustrates a generic LDAP directory with `uid` and `ou=people`. When targeting AD, adapt filter/attributes/base to your organizational contract and test against a real or schema-equivalent directory.

### 6.1. Never Swallow Errors into Empty Results

This is the wrong way to handle errors:

~~~java
// WRONG: timeout gets turned into "no employee found".
try {
    return directoryAdapter.findByUid(uid);
} catch (RuntimeException ex) {
    return Optional.empty();
}
~~~

If a periodic sync job retrieves employee lists, a fake empty result can cause downstream "sync-deletes" across the board. Over HTTP, return an error status reflecting a directory dependency failure (typically `503 Service Unavailable` or equivalent infrastructure error mapping). With brokers, keep the message incomplete and use bounded retries with backoff or route to a retry topic/DLQ. With scheduled jobs, record `RETRY_PENDING` or `FAILED_TRANSIENT` for the next run.

### 6.2. Retrying According to Operation Semantics

| Operation | Safe to Retry? | Additional Conditions |
| --- | --- | --- |
| Read-only search by `uid` | Safe with short backoff | Respect overall deadline; prevent retry storms during full outages |
| Bind with user password | Never retry bad credentials | Separate user errors from network errors; avoid triggering account lockouts |
| Add/modify/delete LDAP entry | Retry only with idempotency / state checks | A timeout does not prove the server did not execute the mutation |
| Syncing state to SQL/MongoDB | Retry by stable business key | Unique keys, upserts/transactions, and sync status tracking |
| Calling HTTP or message broker post-lookup | Per downstream contract | Idempotency keys, outbox/inbox, bounded retries, and DLQ |

Example: a worker consumes `syncEmployee(employeeId=E42)`, succeeds on LDAP lookup, and updates a profile table. If SQL commits and the consumer crashes before acking the broker, the message is redelivered; the worker must upsert by `employeeId` and version/modified timestamp so it does not create duplicate users or emit duplicate events. LDAP pooling improves connection efficiency; it **does not** grant cross-system exactly-once semantics.

### 6.3. Retry Budgets, Circuit Breakers, and Bulkheads

An initial policy for read-only lookups:

~~~text
1 request / message
    |
    |-- LDAP attempt #1
    |      connect/unavailable error?
    |          |
    |          +-- If deadline permits, wait 100–200 ms + jitter
    |                  |
    |                  +-- LDAP attempt #2
    |
    +-- Success: proceed, preserve requestId
    +-- Failure: return 503 / schedule retry / log incident
~~~

Never stack unbounded retries across HTTP clients, workers, and LDAP adapters simultaneously. Place **one intentional retry policy** at the right layer, use exponential backoff + jitter for sustained outages, and cap concurrency to protect DCs. A circuit breaker can open after repeated technical faults; **never** count "employee not found" or "wrong password" toward availability failures.

When the breaker is open, pipelines can defer work via queues or return dependency errors. Serve stale cached snapshots only for dashboards or non-sensitive info if the contract allows; **never** rely on stale cache for authentication, authorization, or deleting user data while the directory is unreachable.

## 7. Testing Failure Scenarios

Tests should separate **data contracts** from **operational faults**. Embedded LDAP/UnboundID can verify mapping and searches; slow sockets, TLS errors, pool exhaustion, and failover require controlled integration environments, typically using LDAP test containers or network fault proxies.

| Test Case | How to Simulate | What to Verify |
| --- | --- | --- |
| Valid lookup | Seed an entry in OU | Exact `uid/cn/mail`; no extra attributes leaked |
| Non-existent | Query missing `uid` with healthy server | `Optional.empty()`; no retries |
| Filter injection | `uid` with special chars or out-of-schema input | Input rejected/escaped, search scope not broadened |
| Connect timeout | LDAP host drops TCP handshake or blocked | Bounded availability error, threads not held forever |
| Read timeout | TCP connects yet server withholds LDAP response | Exception/incident, never returns "not found" |
| DC restart | Restart server while pool holds idle contexts | Stale contexts evicted via validation/non-transient handling; new connection succeeds |
| Pool exhausted | Open more concurrent queries than `maxTotal` | Borrow times out around `maxWaitMillis`, no unbounded queuing |
| Wrong service bind password | Inject bad secret in test | Reports config/auth error; not retried as transient |
| Wrong user bind password | Test user intentionally sends wrong creds | Returns invalid auth, does not use shared service pool |
| Referrals | Query across naming context with referral | Matches `ignore/follow/throw` policy; never treats partial result as complete |
| Overly broad search | Query exceeds size/time limit | Classified error, incomplete data never applied to sync |
| Expired TLS certificate | Use expired test CA/cert | Refuses connection if unverified; no TLS bypass |
| Failover between two URLs | Stop active endpoint in test | Reconnects to healthy endpoint; measure downtime and replication lag |
| Message redelivery | Consumer commits DB before acking broker | Reprocessing same business key causes no duplicate side effects |

### 7.1. Dedicated Tests for Adapter Error Classification

In unit tests, mock `LdapTemplate.search(...)` to return empty, one match, or throw `CommunicationException` and `AuthenticationException`. Assert:

- Only a completed search with zero matches returns `Optional.empty()`.
- `CommunicationException` maps to `DirectoryTemporarilyUnavailable`, preserving cause.
- Service account `AuthenticationException` never turns into "user not found."
- Malicious inputs never reach raw concatenated filter strings.

This tests adapter policy, **never replacing** real LDAP/proxy integration tests. You do not need to target production LDAP to test timeouts or forced connection resets.

### 7.2. Meaningful Pool Tests

To test pool exhaustion, hold `maxTotal` operations open inside a test harness, issue one more operation, and assert it fails near `maxWaitMillis`. After releasing a context, verify active counts drop and borrowing succeeds again. Inspect `getNumActive()`, `getNumIdle()`, and `getNumWaiters()` on `PooledContextSource` directly or via JMX/Micrometer if integrated. Always close contexts in `finally` or use `LdapTemplate` APIs so the framework returns them; leaks will starve the pool over time.

For failover tests, prove **observable availability** rather than assuming "two URLs means zero downtime." Measure P50/P95/P99 latency, timeout counts, retry counts, recovery time, and data consistency across replicating domain controllers.

## 8. Logging, Metrics, Readiness, and Incident Handling

### 8.1. Essential Metrics

Name metrics according to your app's Micrometer conventions, for example:

| Recommended Metric | What to Measure | Operational Value |
| --- | --- | --- |
| `ldap_operation_duration_seconds{operation,result}` | Duration of search/bind/modify, split by outcome | Spots rising P95/P99 or slow servers |
| `ldap_operations_total{operation,result}` | Total successes, not-found, timeouts, bind failures | Distinguishes data misses from infra faults |
| `ldap_pool_active` / `ldap_pool_idle` | Borrowed vs. ready contexts | Diagnoses pool exhaustion or over-provisioning |
| `ldap_pool_waiters` / `ldap_pool_borrow_timeout_total` | Waiting threads and pool borrow timeouts | Detects backpressure and mis-sized pools |
| `ldap_retry_total{cause}` | Retries by cause category | Spots retry storms and prolonged network issues |
| `ldap_dependency_unavailable_total` | Requests/jobs unable to query directory | Tracks integration SLOs |
| `directory_sync_backlog` / `directory_sync_oldest_age_seconds` | Unprocessed messages and accumulated lag | Assesses business impact during LDAP outages |

Never use `uid`, email, raw DNs, user IP addresses, or request IDs as **metric labels** to prevent high cardinality and data exposure. Identifiers may be stored per security policy in access-controlled, retention-bounded logs/traces; never log bind passwords, tokens, sensitive hashes, or full LDAP entries.

When tracing from HTTP clients through message brokers, emit an `ldap.search` span with operation name, normalized endpoint, timeout, and result status. A sync correlation ID traces "LDAP succeeded → DB written → event sent" or pinpoints where messages stalled.

### 8.2. Readiness Differs from Liveness

A Spring Boot app can remain healthy as a process while LDAP is disconnected. **Never** tie every LDAP fault to liveness probes causing Kubernetes to continuously restart pods, piling fresh connection floods onto the directory server. Readiness should reflect whether the app can serve *LDAP-mandatory workflows* per product contract; if the API has LDAP-independent routes, health policies need finer granularity than an all-or-nothing switch.

A TCP/SSL-only check misses broken binds or missing search permissions. Yet running a heavy LDAP query on every health probe adds load and triggers cascading failures on weak servers. Use lightweight probes, brief result caching, or dependency-grouped readiness per your SRE policy.

### 8.3. Incident Response When LDAP Errors Spike

1. **Identify error type:** network timeout, authentication bind, TLS trust, query limits, or pool exhaustion? Check cause chains and correlated logs/metrics.
2. **Isolate scope:** all pods or one host? One DC or the entire domain? Any recent secret, certificate, firewall, DNS, schema, or ACL changes?
3. **Inspect the pool:** active/idle/waiter counts, maxWait, invalidated contexts; is the pool full because queries are slow or contexts leaked?
4. **Assess impact:** message backlogs, HTTP 503s, sync lag, cached data; verify jobs are not misinterpreting errors as "employee not found."
5. **Shed load safely:** stop retry storms, trip circuit breakers where appropriate, cap concurrency; park messages in retry queues if available.
6. **Recover:** once the directory stabilizes, reset breakers, redrive messages by idempotency keys; confirm zero duplicates and verify endpoint replication lag.
7. **Postmortem:** tune timeouts, pool sizes, retention, alerts, and rotation workflows; add regression tests for the failure encountered.

### Configurations That Commonly Backfire

**Trap 1 – Raising read timeout to "eliminate errors":** if the HTTP target is 3 seconds, raising LDAP read timeout to 30 seconds just stalls request threads longer. Diagnose slow servers or overly broad queries instead of cranking timeouts up.

**Trap 2 – Sizing pools to peak concurrent requests:** if each pod holds hundreds of contexts and deployments scale out replicas, total connections can breach LDAP server quotas. Start from measured concurrency and observe pool wait/latency.

**Trap 3 – Caching "not found" when the server errors:** timeouts are not 0 records. Never write negative cache entries, delete employees, or revoke rights simply because LDAP is unavailable.

**Trap 4 – Swallowing partial/size limits:** in some Boot versions, `spring.ldap.template.ignore-size-limit-exceeded-exception` may default to `true`, while `ignore-partial-result-exception` is typically `false`. If sync logic needs complete lists, configure these flags **explicitly** and test them. Example strict config:

~~~yaml
spring:
  ldap:
    template:
      ignore-size-limit-exceeded-exception: false
      ignore-partial-result-exception: false
      ignore-name-not-found-exception: false
~~~

No single flag fits every system: looking up one employee vs. listing all group members have different needs. When using paged results or AD ranged retrieval, pair paging/range handling with completeness checks.

**Trap 5 – Retrying every exception identically:** wrong service passwords, invalid TLS certs, and malformed filters will never heal through retries. Instead, aggressive retries lock accounts or overload DCs.

**Trap 6 – Enabling `follow` referrals indiscriminately:** referrals can cross domains, altering endpoints, latencies, TLS policies, and bind accounts. Explicitly allowlist queryable domains.

## 9. Implementation Decision Table

| Business Requirement | Recommended Configuration / Behavior |
| --- | --- |
| Look up one employee for a synchronous API | Finite connect/read timeouts; narrow search base; low `countLimit`; separate not-found mapping |
| Scheduled sync of tens of thousands of users | Paging, incremental sync, load caps; never treat partial data as complete |
| High lookup throughput via fixed service account | `PooledContextSource` with validation, pool caps, and borrow timeout; monitor waiters |
| Personal password authentication | Per-user context/bind under security policy; avoid shared pools with dynamic principals |
| Multiple domain controllers | Multiple URLs/proper DNS, validation, tested failover, account for replication lag |
| Transient server errors | Bounded retries with backoff/jitter and budget; circuit breaker; message redrive/idempotency |
| Wrong password/certificate/ACL | Diagnose configuration, alert; never retry infinitely |
| HTTP or broker depending on LDAP | Never confuse unavailable with not-found; proper status/requeue/dead-letter handling |
| Deleting or updating downstream data | Act only on complete, verified LDAP results; use transactions/idempotency |

### Self-Check Questions

1. Do a 2-second connect timeout and 5-second read timeout guarantee an entire request finishes under 7 seconds? Why or why not?
2. Why can a 20-connection LDAP pool still stall all incoming requests if a DC hangs?
3. Why must a `CommunicationException` never be turned into a "user does not exist" result?
4. Which faults does `testOnBorrow=true` catch, and what faults can still occur mid-query?
5. What is the difference between a service account bind and a user password verification bind?
6. If a search throws `PartialResultException` or exceeds size limit, what happens if sync treats the output as complete?
7. Why must retrying an LDAP modify after a timeout include state checks/idempotency even though it is just a single LDAP call?

Resilience in an LDAP-integrated app never comes from a single timeout value or pool size. In a **Spring Boot Integration** system bridging APIs, databases, caches, and brokers, combine **contract-aligned queries**, **layered time bounds**, **controlled pooling**, **exception classification**, **bounded retries/idempotency**, and **end-to-end observability**.

## References

- [Spring Boot Reference — LDAP and Data Access](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap)
- [Spring Boot 3.5 — Common Application Properties (LDAP)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring LDAP — Configuration, Native Java LDAP Pooling](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html)
- [Spring LDAP Javadoc — PooledContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Spring LDAP Javadoc — PoolConfig](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html)
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Oracle JNDI LDAP — Connect and Read Timeout Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/module-summary.html)
