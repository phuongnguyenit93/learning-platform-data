# Access Control for Administrative and Broad Deletion Commands in Spring Data Redis

## 1. Why Does Key Management Require Access Control?

Redis commonly stores sessions, caches, coordination locks, and temporary data across many features. Deleting a single key may be a normal business operation; the exact same command applied to thousands of keys or combined with full-keyspace listing can cause widespread data loss. Administrative commands can also alter configuration, drop connections, shut down the server, or wipe entire databases.

In a Spring Data Redis application, `RedisTemplate`, `StringRedisTemplate`, and abstractions like Spring Cache execute commands under the identity of the Redis connection. **Spring Data Redis does not decide on its own which account may run dangerous commands**: Redis ACL (Access Control List) is the server-side authorization layer. The application must connect with the right account, design bounded APIs, and isolate maintenance tasks.

Learning objectives:

- Distinguish single-key operations, multi-key deletions, and instance-wide Redis administrative commands.
- Grant least-privilege permissions for both **commands** and **key name patterns**.
- Separate identities for application runtime, cleanup jobs, and administration.
- Design bounded, previewable, and auditable deletion operations.
- Verify permissions without executing destructive commands.

## 2. Impact Levels of Command Groups

| Group | Typical Commands | Primary Risk |
| --- | --- | --- |
| Regular key read/write | `GET`, `SET`, `EXPIRE`, `TTL` | Accessing data outside business scope if key names are unrestricted. |
| Key deletion | `DEL key [key ...]`, `UNLINK key [key ...]` | Deletes one or more keys; combined with a scan loop, can delete in bulk. |
| Key listing | `KEYS pattern`, `SCAN cursor MATCH pattern` | `KEYS` traverses the entire keyspace in one command and can block the server on large data; `SCAN` iterates incrementally yet can still enumerate huge numbers of key names. |
| Database/instance wipe | `FLUSHDB`, `FLUSHALL` | `FLUSHDB` wipes the current database; `FLUSHALL` wipes all databases on the Redis instance. Not scoped by prefix. |
| Server administration | `CONFIG`, `SHUTDOWN`, `DEBUG`, `REPLICAOF` | Alters operations, affecting availability, configuration, or replication state. |
| Security and connections | `ACL`, `CLIENT KILL` | Changes permissions or disconnects other clients. |
| Scripting/extensions | `EVAL`, `EVALSHA`, `FUNCTION`, `MODULE` | Opens additional execution paths performing multiple operations against data or the server. |

Several distinctions must be understood:

1. `UNLINK` removes the key from the keyspace immediately and primarily frees memory on a background thread. **The data is still deleted**; it is not a way to recover from an accidental deletion.
2. `SCAN` iterates incrementally with `MATCH` and `COUNT`. `COUNT` is only a workload hint, not a hard cap. Results may repeat or shift as the keyspace mutates; `SCAN` does not create a consistent snapshot.
3. `FLUSHDB` and `FLUSHALL` can support asynchronous memory-freeing options, but the scope of deleted data does not change.
4. Blocking `FLUSHALL` is not enough: a `SCAN` + `UNLINK` loop, or `DEL` with a huge key list, can still cause widespread data loss.
5. Separating logical databases via `SELECT` does not create a strong security boundary. `FLUSHALL` affects the entire instance; Redis Cluster normally uses only database 0.

## 3. Designing Access Roles

Instead of letting every component share one broad account, separate identities:

| Identity | Need | Recommended Permissions |
| --- | --- | --- |
| `app_runtime` | Read, write, and set TTL on sessions | Only commands actually used on `app:session:*`; no bulk deletion or admin commands. |
| `cleanup_job` | Clean up a designated cache namespace | `SCAN` and `UNLINK` restricted to controlled maintenance tasks. |
| `observer` | Check system health | Selected observation commands; do not grant all of `@admin` by default. |
| `redis_operator` | Incident handling, config changes, recovery | Dedicated admin identity, time-bounded access tied to operational procedures. |

For example, a session app relying on TTLs may not need `DEL` or `UNLINK` at all. If logout requires immediate session removal, deletion can be granted within the session namespace, while recognizing that ACLs do not cap how many keys get deleted.

### Boundaries of Redis ACLs

Redis 6 and later support ACLs allowing or denying individual commands, command categories, and key patterns. For example, `~app:session:*` allows commands whose Redis-recognized key arguments operate on keys matching that prefix.

**ACLs do not enforce conditions like "at most one key per delete command," "at most 100 keys/minute," "must dry-run," or "must be approved."** If a user is allowed `DEL` on `app:session:*`, it can still delete many keys in that namespace. Limits on count, rate, operator, and business context must live in the application or job layer.

Another critical boundary: the `~prefix:*` pattern is checked against arguments classified as **keys**; `SCAN` output is not automatically filtered by ACL key patterns. A connection allowed to run `SCAN` can see key names outside the prefix it is allowed to modify. `MATCH` is a caller-chosen filter, not a security fence. Therefore, grant scan permissions only to trusted identities and consider separate Redis instances when strict isolation is required.

## 4. Declaring ACLs by Explicit Allowlisting

The ACL file example below illustrates a policy where `REPLACE_*` are placeholders for securely managed passwords:

```text
# users.acl — example, never commit real passwords to Git
user default off
user app_runtime on >REPLACE_APP_SECRET resetkeys ~app:session:* -@all +ping +get +set +exists +expire +ttl +pttl
user cleanup_job on >REPLACE_CLEANUP_SECRET resetkeys ~app:cache:expired:* -@all +ping +scan +unlink
```

- `user default off` disables the default account. **Create and verify another admin login path before enabling this policy**, otherwise you can lock out administrative access.
- `on` enables the user, `>...` sets the password, `resetkeys` clears prior key patterns, and `~...` sets allowed key scope.
- `-@all` revokes all command permissions; `+...` explicitly allows each needed command.
- `app_runtime` does not have `DEL`, `UNLINK`, `KEYS`, `SCAN`, `FLUSHDB`, or `FLUSHALL`.
- `cleanup_job` has `UNLINK` permission on keys matching `app:cache:expired:*`. `SCAN` permission should be treated as sensitive because it can enumerate other key names.

Redis provides command categories like `@read`, `@write`, `@keyspace`, `@admin`, and `@dangerous`. Categories are handy when auditing permissions, but per-command allowlisting is usually easier to control for dedicated users. Notably, `-@dangerous` **does not block all forms of broad data deletion**: `DEL` and `UNLINK` can still be granted through other categories.

Depending on Redis and client versions, connection handshakes may issue commands such as `HELLO`, `CLIENT SETINFO`, or `SELECT`. Observe the actual commands used and add the exact required commands or subcommands rather than granting `+@all` to hide errors. Protect ACL files and secrets with strict read permissions; rotate credentials according to policy.

### Safely Verifying Policies

Redis 7 and later support `ACL DRYRUN` to test hypothetical permissions **without executing the command**. Using an admin identity authorized to check ACLs:

```redis
ACL DRYRUN app_runtime GET app:session:123
ACL DRYRUN app_runtime GET other-service:session:123
ACL DRYRUN app_runtime DEL app:session:123
ACL DRYRUN app_runtime FLUSHALL
ACL DRYRUN cleanup_job UNLINK app:cache:expired:123
ACL DRYRUN cleanup_job UNLINK app:session:123
```

With the example policy, expected outcomes are respectively: allowed; denied by key pattern; denied by command; denied by command; allowed; denied by key pattern. On Redis 6, test non-destructive commands as the test user and check permission responses; never send `FLUSH*` against real data to "test blocking."

`ACL LOG` helps investigate authentication or authorization denials, but it is **not an audit log of all successfully executed commands**. To trace deletions, emit logs from the application, job, and admin tooling along with request IDs.

## 5. Connection Identities in Spring Data Redis

Spring Boot 3.x can obtain standard Redis configuration from environment variables or secrets injected by the deployment platform:

```text
SPRING_DATA_REDIS_HOST=redis.internal.example
SPRING_DATA_REDIS_PORT=6379
SPRING_DATA_REDIS_USERNAME=app_runtime
SPRING_DATA_REDIS_PASSWORD=<injected-secret>
SPRING_DATA_REDIS_SSL_ENABLED=true
```

The example assumes the environment configures Redis with TLS; adjust host, port, and SSL for your deployment. Never store real passwords in committed `application.yml` files, source code, connection URLs, or logs. Alongside ACLs, restrict network access to Redis and use TLS when traffic traverses untrusted networks.

A cache cleanup worker should use its own connection factory with the `cleanup_job` account. Never inject the cleanup connection into normal request-handling controllers. If two connections must coexist in one process, assign explicit bean names and qualifiers:

```java
@Configuration
class CleanupRedisConfig {

    @Bean("cleanupConnectionFactory")
    RedisConnectionFactory cleanupConnectionFactory(Environment env) {
        String host = env.getRequiredProperty("cleanup.redis.host");
        int port = env.getRequiredProperty("cleanup.redis.port", Integer.class);
        String username = env.getRequiredProperty("cleanup.redis.username");
        String password = env.getRequiredProperty("cleanup.redis.password");

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(host, port);
        config.setUsername(username);
        config.setPassword(RedisPassword.of(password));

        return new LettuceConnectionFactory(config);
    }

    @Bean("cleanupRedisTemplate")
    StringRedisTemplate cleanupRedisTemplate(
            @Qualifier("cleanupConnectionFactory") RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

The corresponding imports come from Spring Framework, Spring Data Redis, and Spring Data Redis's Lettuce integration. This illustrates identity separation for a standalone connection: if the endpoint requires TLS, configure `LettuceClientConfiguration` appropriately for this factory; it does not automatically inherit SSL settings from the primary factory. The `cleanup.redis.*` properties come from dedicated secrets/configuration, never from user requests.

## 6. Namespace Key Cleanup and Quotas

Separate **permission to delete** from **policy deciding what, when, and how much may be deleted**. Redis ACLs handle the former; the application or maintenance job handles the latter.

A cleanup job should combine:

1. **Fixed scope:** prefixes like `app:cache:expired:` are hardcoded in the job; never allow requests to pass arbitrary `*` patterns.
2. **Preview:** run a dry run to collect candidate counts and present results for operator review.
3. **Quantity limits:** each run has a max key count, rate limit, runtime budget, and dedicated trigger permission.
4. **Small-batch deletion:** use `SCAN` to traverse and `UNLINK` when appropriate; verify the prefix before deleting.
5. **Audit recording:** log namespace, candidate count, actual removed count, timestamp, job identity, and approval ID.
6. **Lock down entry points:** only schedulers or authorized operators can trigger it; never expose a public endpoint carrying `cleanup_job` privileges.

Example maintenance service for standalone Redis, using the dedicated `StringRedisTemplate` bound to `cleanup_job`:

```java
@Service
public class ScopedCacheCleanup {

    private static final String PREFIX = "app:cache:expired:";
    private final StringRedisTemplate redis;

    public ScopedCacheCleanup(
            @Qualifier("cleanupRedisTemplate") StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Result(int candidates, long removed, boolean dryRun) {}

    public Result execute(boolean dryRun, int maxKeys) {
        if (maxKeys < 1 || maxKeys > 200) {
            throw new IllegalArgumentException("maxKeys must be in range 1..200");
        }

        Set<String> candidates = new LinkedHashSet<>();
        ScanOptions options = ScanOptions.scanOptions()
                .match(PREFIX + "*")
                .count(100)
                .build();

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && candidates.size() < maxKeys) {
                String key = cursor.next();
                if (key.startsWith(PREFIX)) {
                    candidates.add(key);
                }
            }
        }

        if (dryRun) {
            return new Result(candidates.size(), 0, true);
        }

        long removed = 0;
        for (String key : candidates) {
            if (Boolean.TRUE.equals(redis.unlink(key))) {
                removed++;
            }
        }
        return new Result(candidates.size(), removed, false);
    }
}
```

Required imports include `java.util.Set`, `java.util.LinkedHashSet`, `org.springframework.data.redis.core.Cursor`, `org.springframework.data.redis.core.ScanOptions`, `org.springframework.data.redis.core.StringRedisTemplate`, and the corresponding Spring annotations. This snippet illustrates key-count capping; production usage must add caller authentication, approval, rate limiting, logging, and metrics.

**Limitations to accept:** the job processes at most 200 candidates per run and does not guarantee scanning the whole keyspace; `SCAN` does not guarantee a consistent snapshot; keys may expire or be modified between scanning and deletion; and the number of deleted keys may differ from candidates. In Redis Cluster, scanning must handle each primary node; do not assume a single `scan()` covers the entire cluster. Avoid deleting multiple keys across different hash slots in one command; for example, call `unlink(key)` per key.

For very large deletion needs, design jobs with checkpoints, rate limits, pause capability, and per-batch confirmation. Do not simply raise `maxKeys` to run faster.

### Spring Data Redis APIs Prone to Broad Impact

- `redisTemplate.keys("app:*")` uses `KEYS`, unsuitable for scanning large keyspaces in production.
- `redisTemplate.delete(collection)` and `unlink(collection)` can delete many keys; control the source of the list and cap its size.
- `Cache.clear()`, `@CacheEvict(allEntries = true)`, and cache-clear endpoints can trigger multi-key deletion commands. Depending on `RedisCacheWriter` configuration, clearing a cache may use `KEYS` plus `DEL`. A batch strategy using `SCAN` lowers blocking risk during traversal but still deletes large amounts of data.

For ordinary caches, prefer TTLs, versioned namespaces, or pre-designed expiration mechanisms. Broad cache-clearing functions should go through dedicated, separately authorized maintenance jobs rather than business controllers.

## 7. Operational Procedure for Dangerous Commands

Commands such as `FLUSHDB`, `FLUSHALL`, `CONFIG`, `SHUTDOWN`, `ACL SETUSER`, or `REPLICAOF` should be used only through controlled administrative channels. Runtime accounts and cache cleanup jobs must not hold these permissions.

| Step | Information to Confirm |
| --- | --- |
| Target selection | Redis instance/cluster, environment, database, namespace, shared services. |
| Impact assessment | Can the data be rebuilt? Does it involve sessions, queues, locks, or business data? |
| Recovery readiness | Snapshot/backup, restore point, outage mitigation plan; rehearse when needed. |
| Approval | Requester, approver, change ticket, maintenance window, and admin privilege duration. |
| Execution | Re-verify the exact environment and host before running the approved command. |
| Post-check | Check key count, error rate, latency, cache hit/miss, connections, and service recovery. |

If `FLUSH*` must be used, use a temporary administrative session/tool and log the action. On a shared Redis instance, `FLUSHDB` or `FLUSHALL` cannot be treated as a local cache clear; evaluate namespace-scoped deletion before granting such access.

## 8. Defense in Depth and Troubleshooting

ACLs are only one layer in a security architecture:

- **Resource isolation:** data with different criticality or isolation requirements should be considered for separate Redis instances/clusters. Prefixes do not replace isolation boundaries.
- **Connection protection:** restrict network access, enable TLS when needed, separate secrets by identity, rotate credentials, and limit secret read access.
- **Policy management:** store ACLs in controlled configuration, track changes, and re-verify permissions when upgrading Redis or drivers.
- **Monitoring:** watch latency, key count, memory, evictions, hit rate, `NOPERM` errors, and cleanup job effects; record run IDs.
- **Avoid workarounds:** never grant `EVAL`, `FUNCTION`, `MODULE`, or broad command categories just to work around a small operation.

| Symptom | Initial Interpretation | How to Handle |
| --- | --- | --- |
| `WRONGPASS` or `NOAUTH` | Wrong credentials or unauthenticated. | Check identity, secret, and connection setup flow. |
| `NOPERM` | Missing permission for command or key. | Check command and key pattern; run `ACL DRYRUN`/`ACL LOG` before considering expanding permissions. |
| `CROSSSLOT` | Multi-key command in Redis Cluster violates hash-slot rule. | Split operations by slot/key; granting more ACLs will not fix this error. |
| Widespread cache disappearance | Job/API may have overly broad permissions and scope. | Inspect job logs, schedules, cache-clear calls, and account permissions. |
| Latency spikes during maintenance | Broad scans, heavy commands, or high delete throughput. | Lower batch size/rate, check metrics, and pause job per runbook. |

## 9. End-to-End Example: Scheduled Session and Cache Cleanup

Suppose a single Redis instance holds these keys:

```text
app:session:<session-id>          # sessions with TTL
app:cache:expired:<cache-id>      # key group allowed for cleanup
other-service:*                   # data belonging to another service
```

Implementation plan:

1. HTTP threads use `app_runtime`, reading/writing only `app:session:*` keys and updating TTLs. The account has no `FLUSHALL` or `SCAN` permission.
2. A maintenance scheduler uses `cleanup_job`, runs a dry run first, logs candidate counts, caps runs at 200 keys, and only runs `UNLINK` on `app:cache:expired:*` keys.
3. `other-service:*` data lies outside the key permissions of both accounts. Because `SCAN` can expose key names, the cleanup job is isolated in a trusted environment.
4. Instance-wide wipes happen only through an operator procedure with a separate admin identity after assessing impact and recoverability.

This design combines **least privilege in Redis** with **business limits in Spring Data Redis**. ACLs control commands and keys; the application bounds purpose, quantity, timing, and authorized callers. Both layers are required to limit the blast radius of coding bugs, misconfigurations, and human error.

## 10. Self-Check Questions

1. Why is forbidding `FLUSHALL` while granting `SCAN` + `UNLINK` across the entire keyspace still unsafe?
2. Does the ACL `~app:session:*` guarantee each `DEL` command deletes only one key? Which layer must enforce that?
3. How does `UNLINK` differ from `DEL` in freeing memory, and why do both still need quotas?
4. Why should `@CacheEvict(allEntries = true)` be treated as a risky maintenance operation?
5. What do `ACL DRYRUN` and `ACL LOG` help verify and diagnose, and which audit log do they not replace?

**Safe practice exercise:** on a test Redis instance, create the accounts with the minimal command set, use `ACL DRYRUN` to confirm allow/deny cases, and then run a cleanup job in dry-run mode with a low quota. Inspect candidate lists and logs before allowing test data deletion in an isolated namespace.
