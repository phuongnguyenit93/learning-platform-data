# Permissions to Run UDFs, Plugins, or Extensions

> **Chapter:** Security  
> **Scope:** Apache Cassandra — a distributed *wide-column* database, role-based CQL authorization, and extension mechanisms capable of running code inside the server process. Includes CQL examples, threat models, operational workflows, and a verification snippet using Cassandra Java Driver 4.x.
>
> **Learning Objectives:** Distinguish **permissions to create/alter/drop/call UDFs or UDAs**, **cluster/node-level feature gates**, and **server-level rights to install/run plugins**. Design least privilege, test for resource abuse, deploy with approval, revoke permissions, and protect the cluster on failure.

## 1. Problem: The App Only Needs SELECT—Why Can a UDF Create Huge Risk?

A Java application wants to display a device's normalized score. Instead of just reading the `score` column, the dev team proposes a **User-Defined Function (UDF)** running right inside Cassandra:

```cql
SELECT device_id, lab.score_plus_one(score) AS adjusted_score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

At first glance, this looks like a tiny calculation. Yet it raises distinct security questions:

1. Who is allowed to **define** the function via `CREATE FUNCTION`?
2. Who is allowed to **invoke** the function in a `SELECT`?
3. Does the cluster **allow UDFs** in the current version/configuration?
4. **Where** does the function body run, and whose CPU and memory does it consume?
5. If the function is slow, throws errors, or tries to reach out-of-scope resources, who suffers?
6. If a third-party library is installed into Cassandra as a **plugin/server extension**, are CQL permissions enough to control it?

Key point: **user-supplied code running inside the database has a different trust boundary than a pure `SELECT`**. Data-permission management cannot substitute for code-execution governance.

A service holding `SELECT` on a table may be barred from calling a UDF; a role holding `EXECUTE` on a UDF does not automatically get to alter the UDF's definition. Furthermore, **not every plugin even has a resource targetable by `GRANT EXECUTE`**.

## 2. Three Control Layers That Must Coexist

```text
                  APPLICATION / USER
                            |
                  CQL over TLS, authentication
                            |
                            v
              +---------------------------+
              | LAYER 1: CQL AUTHORIZATION|
              | SELECT / EXECUTE / CREATE |
              | roles, resources, grants  |
              +---------------------------+
                            |
                            v
              +---------------------------+
              | LAYER 2: FEATURE GATE     |
              | Is UDF enabled?           |
              | Supported runtime/engine? |
              +---------------------------+
                            |
                            v
              +---------------------------+
              | LAYER 3: SERVER TRUST     |
              | JVM process / classpath   |
              | plugin package / OS user  |
              | node rollout / sandbox    |
              +---------------------------+
                            |
                            v
              NODE CPU / MEMORY / DISK / NETWORK
                            |
                            v
                 CQL p99, GC, REPLICAS, CL
```

| Layer | Purpose | Example | What It Cannot Replace |
| --- | --- | --- | --- |
| **Authentication** | Verify client identity | Login role, credentials, TLS client identity if supported | What actions are allowed after login |
| **CQL Authorization** | Restrict role actions on resources | `SELECT` on table, `EXECUTE` on one UDF | OS policies for code installed into the JVM |
| **Feature gate** | Enable/disable a feature class on the server | Server config toggling UDFs per release | Fine-grained per-role authorization |
| **Runtime/security boundary** | Constrain capabilities and impact of running code | Java UDF/runtime model, API restrictions per release | Code review, least privilege, and source control |
| **OS/deployment control** | Who can edit JARs/classpath/configs/restarts | File permissions, CI/CD, package signing, approval | Automatically restricting every behavior of a loaded plugin |
| **Observability** | Detect risks and degraded performance | Audits, JVM/CPU/GC, CQL p99, error rates | Preventing bugs upfront |

A role holding `EXECUTE` still cannot run a UDF if **the server-level feature is disabled**. Conversely, enabling UDFs cluster-wide without authorization and code review opens a large attack surface.

## 3. Defining UDFs, UDAs, and Plugins

### UDF — User-Defined Function

A UDF is a user-defined function in CQL. It has a **name, parameter type list, return type, and body**, stored in schema metadata and invoked during query execution.

Conceptual example:

```text
lab.score_plus_one(int) -> int
Input: 41
Output: 42
```

If a query returns many rows, the function can be evaluated many times. **A UDF that runs fast on one row is not guaranteed safe in a query scanning a large partition.**

### UDA — User-Defined Aggregate

A UDA is a user-defined aggregate function, typically combining a **state function**, a state type, and optionally a **final function** to accumulate/transform multiple values.

If an aggregate runs over many rows, state and computations can burn CPU/memory and stretch read latencies. Creation/execution support and auxiliary-function permissions must be verified for your Cassandra version.

### Plugin / Server Extension

The term "plugin" can refer to different extension forms:

- **Server-side Java extensions** placed on the classpath / packaged alongside Cassandra.
- Custom classes for authentication/authorization, external integrations, or release-supported *extension points*.
- **Custom indexes** or **triggers** (where supported by release/config), referencing code executed inside the JVM.
- External integrations alongside Cassandra, such as metrics agents or services querying CQL.
- **Client-side plugins** like custom codecs or load-balancing policies in the Java Driver — running inside the application, not the Cassandra server process.

**There is no universal `GRANT EXECUTE ON PLUGIN ...` command covering every plugin type.** Installation, enablement, and controls depend on the extension point, version, and system policy.

## 4. Separating "Permitted to Call" from "Permitted to Install"

Suppose Team A owns UDF `lab.score_plus_one(int)` and Team B supplies a JAR installed into Cassandra.

| Scenario | Which Permissions to Check? | Who Is Responsible? |
| --- | --- | --- |
| Service reads table and calls UDF | Table `SELECT` **and** function resource `EXECUTE` | App role owner and CQL admin |
| Developer creates new UDF | `CREATE` on function resource scope, feature gate | Schema/security owner |
| Developer alters function body | Replace/`ALTER` rights per CQL release and code review process | Security reviewer + schema owner |
| Operator deploys JAR to classpath | OS/filesystem/CI-CD/deployment admin; rollout policy | Platform/SRE |
| Service calls a custom endpoint outside Cassandra | Auth/RBAC of that external endpoint | External system owner |
| Java app installs a custom codec | Application code deployment rights | App owner, not Cassandra CQL roles |

Boundary rule: **granting permissions inside the database does not sandbox a JAR trusted by operators to run inside the Cassandra process**. Treat server-side code as part of the *trusted computing base*.

## 5. RBAC Model in Cassandra

Cassandra implements **role-based access control** with these concepts:

- **Role:** an identity that may have `LOGIN`, receive permissions, and inherit through other roles.
- **Permission:** actions such as `SELECT`, `MODIFY`, `CREATE`, `ALTER`, `DROP`, `AUTHORIZE`, `EXECUTE` depending on resource type.
- **Resource:** tables, keyspaces, roles, or **functions/aggregates** per syntax and version.
- **Authorizer:** the component deciding whether a role is allowed; must be configured on the server.

**Not every permission is valid on every resource.** For instance, `SELECT` applies to tables while `EXECUTE` applies to function/aggregate resources; never grab a `GRANT` example and apply it blindly to custom plugins.

### Superuser Is a High-Risk Exception

A superuser/broad admin role bypasses normal restrictions and can execute cluster-level admin operations. Never grant superuser to an application just so a `SELECT` can invoke a UDF.

Separate duties:

1. `platform_admin`: manages nodes/configs/plugin deployment, minimal audited access.
2. `schema_maintainer`: updates schemas/function definitions in approved keyspaces.
3. `app_reader`: reads tables and invokes **only the required UDFs**.
4. `security_auditor`: reviews configs/permissions/logs per duty, no data modification by default.
5. `incident_operator`: executes time-bounded, approved emergency procedures.

This is a suggested role model, **not a list of built-in Cassandra roles**.

## 6. Function Resource Scope: Per Function or Whole Keyspace?

Suppose keyspace `lab` has two UDFs:

```text
lab.score_plus_one(int)
lab.normalize_label(text)
```

With CQL authorization supporting function resources, common scopes include:

| Resource Scope | Example Meaning | Breadth |
| --- | --- | --- |
| **Single function signature** | `FUNCTION lab.score_plus_one(int)` | Narrowest for one UDF |
| **All functions in keyspace** | `ALL FUNCTIONS IN KEYSPACE lab` | Covers many existing and potentially future UDFs/UDAs |
| **All functions cluster-wide** | `ALL FUNCTIONS` | Very broad; avoid granting to applications |

**Function names alone do not distinguish overloads.** Cassandra allows functions sharing a name with different parameter types; function resources are identified by **name and parameter-type signature** in CQL.

For example, `lab.cast_score(int)` and `lab.cast_score(text)` are two distinct function resources. Granting `EXECUTE` on the `int` overload must not be assumed to grant the `text` overload.

### Why Can `ALL FUNCTIONS IN KEYSPACE` Be Too Broad?

If another team later adds a CPU-heavy function or one containing sensitive logic in the same keyspace, any role holding keyspace-wide `EXECUTE` can immediately invoke the new function without separate approval.

**Least privilege:** grant on **each specific signature needed**; broaden scope only with controlled justification, never "for convenience."

## 7. CQL Hands-On: UDFs in a Test Environment

> **Prerequisites:** Examples apply only to Cassandra versions supporting Java UDFs **and** authorized by the operator in an isolated lab cluster. If UDFs are disabled by config or unsupported by the runtime, **never modify a production server to run an exercise**. Roles `app_reader` and `udf_maintainer` are assumed to exist in a working authn/authz setup.

### Step A — Create Test Data Schema

Assuming keyspace `lab` exists with replication matching real node/DC counts:

```cql
CREATE TABLE IF NOT EXISTS lab.metric_by_id (
    device_id text PRIMARY KEY,
    score int,
    updated_at timestamp
);
```

Insert one row:

```cql
INSERT INTO lab.metric_by_id (device_id, score, updated_at)
VALUES ('device-01', 41, '2026-11-21T08:00:00Z');
```

### Step B — Define a Simple, Purely Computational UDF

An authorized user with function-management rights and lab approval can create the function:

```cql
CREATE FUNCTION IF NOT EXISTS lab.score_plus_one(x int)
RETURNS NULL ON NULL INPUT
RETURNS int
LANGUAGE java
AS 'return x + 1;';
```

Meaning:

- `RETURNS NULL ON NULL INPUT`: skips evaluation on null input and returns null.
- `RETURNS int`: return type.
- `LANGUAGE java`: body handled by the version's Java UDF engine.
- `x + 1` is illustrative only; `int` arithmetic risks overflow near type bounds, so **never use for financial or reconciliation logic without bounds checks**.

In some releases, UDFs may be disabled by default or Java UDF execution/limits may differ. Read docs for your running release and test in a lab.

### Step C — Query with the UDF

```cql
SELECT device_id, score,
       lab.score_plus_one(score) AS adjusted_score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

Expected on the lab data: `device_id=device-01`, `score=41`, `adjusted_score=42`.

The UDF is evaluated server-side in Cassandra during query execution, **not downloaded and executed by the client**.

### Step D — Grant Least Privilege

Example commands run by an authorized admin role:

```cql
GRANT SELECT ON TABLE lab.metric_by_id TO app_reader;

GRANT EXECUTE ON FUNCTION lab.score_plus_one(int)
TO app_reader;
```

Two separate permissions:

- `SELECT` allows reading columns the role may query on the table per Cassandra's permission model.
- `EXECUTE` allows calling the exact granted function signature.

**Granting `EXECUTE` does not grant `CREATE`/`ALTER`/`DROP` on functions.** Nor does it turn a role into a superuser or let it add JARs to Cassandra's classpath.

### Step E — Inspect Permissions

A user authorized to read metadata can run:

```cql
LIST ALL PERMISSIONS OF app_reader;
```

Exact `LIST PERMISSIONS` syntax, inherited role semantics, and metadata visibility depend on the authorizer, release, and caller privileges. Cross-check expected output against the **role graph**, not a single isolated grant line.

Run **negative tests** with a restricted identity:

1. `app_reader` can read the table and invoke `lab.score_plus_one(int)`.
2. A role with table `SELECT` but **without matching `EXECUTE`** is denied calling the function.
3. `app_reader` cannot create new functions or alter definitions without DDL rights.
4. After revoking `EXECUTE`, function calls must fail **once permission caches converge per config**.

### Step F — Revoke Permissions

```cql
REVOKE EXECUTE ON FUNCTION lab.score_plus_one(int)
FROM app_reader;
```

Revoking the permission **does not drop the function**, alter table data, or immediately abort already-started requests. Auth/permission caches and open sessions affect when changes take effect; test per cluster policy.

To stop one application from calling a function, **do not `DROP FUNCTION` while other systems use it** without a dependency inventory.

## 8. Permissions to Create, Replace, and Drop UDFs/UDAs

Creating a new UDF typically involves `CREATE` at the keyspace function scope. Conceptual example, granted only once operators confirm policy compliance:

```cql
GRANT CREATE ON ALL FUNCTIONS IN KEYSPACE lab
TO udf_maintainer;
```

Actions such as replacing a function body or dropping a function may require `ALTER`/`DROP` on the function resource and related permissions depending on CQL release. UDAs may also depend on **`EXECUTE` permissions on their state/final functions**, not only `CREATE` on the aggregate.

**Do not infer replacement rights solely from creation rights.** Before deploying, check the permission matrix for your exact Cassandra version and test with a non-superuser role in a lab.

### What Are the Risks of Broad `CREATE` Grants?

A role permitted to create any function in a keyspace can supply complex or resource-hungry bodies even if its stated business purpose was "write one text helper."

Good workflow:

- Author proposes code; security/performance reviewers approve.
- CI produces verifiable artifacts/schema migrations with hashes and versions.
- A dedicated deployment role applies the change in an approved window.
- Application roles hold only `EXECUTE` on approved functions.
- Post-rollout, monitor query p99, GC, CPU, and timeouts.

Never grant cluster-wide `CREATE ON ALL FUNCTIONS` to a developer just to test one function.

## 9. Feature Gate: Permitted Role Yet Cassandra Refuses to Run UDFs

Cassandra versions include security switches/configs controlling user-defined functions; for example, some releases use configuration keys such as:

```yaml
# Illustrates common option names only; verify against your release.
enable_user_defined_functions: false
enable_scripted_user_defined_functions: false
```

**Do not copy these lines into production configs or assume both keys exist in every version.** Meaning, defaults, and support for scripted functions have changed across releases. Some versions restrict or drop certain UDF/runtime types for security reasons.

If a query reports the feature is disabled:

1. Check Cassandra version and matching configuration docs.
2. Distinguish **server feature disabled** from **missing `EXECUTE`/`CREATE` permission**.
3. Check auth/authorizer and the role used by the client.
4. Assess actual need: can the computation move to the Java application instead of enabling UDFs?
5. Enable the feature only via formal approval, testing, and uniform rollout.

**Enabling UDFs expands the cluster's risk surface**—it is not a fix for a single permission error.

## 10. Why Are UDFs Especially Resource-Sensitive?

CQL can apply a UDF across many rows/cells. If one evaluation takes 1 ms CPU and a query invokes it 10,000 times, theoretical cost reaches 10 single-thread CPU seconds before overhead.

```text
One UDF:
  score_plus_one(41) -> 42
  Tiny cost on 1 row.

Another query:
  SELECT udf(big_column) ...
  On a huge partition with many results.
  UDF may be invoked repeatedly thousands of times.
        |
        +--> CPU spikes
        +--> allocations / GC increase
        +--> coordinator/replicas slow down
        +--> pending reads and timeouts rise
```

A UDF body with an unbounded loop or large allocations can degrade every request sharing node resources.

### Why `LIMIT 20` Is Not a Complete Safeguard

`LIMIT` caps returned rows in CQL, yet replicas may still traverse SSTables and tombstones to find live rows. Depending on query structure and execution engine, function invocation cost can still surprise you. Never treat `LIMIT` as a sandbox.

Safeguards:

- Query by **exact partition key** with bounded clustering ranges.
- Bound data/collection sizes.
- Keep UDFs purely computational: zero external I/O, no unbounded loops or allocations.
- Benchmark invocation counts/CPU/memory under realistic hot-key distributions.
- Enforce concurrency limits and rate limits at the service/gateway layer.
- Alert on p95/p99, query timeouts, GC, and per-node CPU.

**Consistency level `LOCAL_QUORUM` does not cap CPU or function execution counts.** CL governs replica acknowledgments, not a UDF's CPU budget.

## 11. UDAs: Aggregate State Is a Distinct Risk Source

UDAs process multiple values, maintain state, and invoke final functions. Depending on the model, huge state or unbounded aggregations strain RAM and CPU.

A business request like "compute median across all events of a customer" sounds simple yet can scan millions of rows, accumulate large state, or execute expensive math.

A UDA design review should answer:

| Question | Reason |
| --- | --- |
| How many partitions/rows must be scanned? | Large datasets cause read amplification and CPU load |
| Can state grow with element count? | Risk of memory exhaustion |
| Is the aggregate deterministic and thoroughly tested? | Easy to corrupt business reports |
| Are state/final functions called on nulls? | Semantics must be unambiguous |
| Who may `CREATE`/`DROP`/`EXECUTE` the UDA and helper functions? | Avoid overly broad permission scope |
| Can results be cached or pre-aggregated per query? | Often better than computing at read time |

If a UDA is expensive, consider **query-driven summary tables**, stream processing, or Java application computation with proper synchronization.

Never confuse permission to `EXECUTE` a UDA with permission to run arbitrary external code. Check permission semantics for aggregates and helper functions per version.

## 12. Server Plugins: Where Does Execution Privilege Live?

A plugin installed as a JAR/server Java class may load and run inside the Cassandra process or a specific extension point. When it does:

- It largely shares the server JVM's fault domain: CPU, heap/native memory, GC, threads, and OS resources accessible to the process user.
- It may interact with internal storage/messaging/callbacks via extension APIs.
- It usually requires consistent deployment across nodes; version mismatches cause runtime failures.
- It can alter read/write path behavior or observability depending on plugin type.

**CQL RBAC does not automatically sandbox a server-side JAR.** A plugin placed on the classpath by an operator cannot be assumed safe just because app roles lack `EXECUTE ON FUNCTION`.

### Plugin Control Layers

| Stage | Mandatory Control | Evidence |
| --- | --- | --- |
| Plugin selection | Business need, vendor/source, license, maintenance | Approval record |
| Security review | Dependencies/SBOM, source code, vulnerability scan | Review findings |
| Compatibility testing | Cassandra/JDK version, binary API, serialization/schema | Test results on matching cluster |
| OS privilege scoping | File ownership, classpath/config access, secret access | Access review |
| Performance testing | CPU, GC, off-heap, read/write p99, compaction/repair | Before/after benchmarks |
| Rollout | Canary by node/rack/DC, change window | Change plan |
| Operations | Logs/audits, health checks, alerts, rollback | Dashboards/runbook |
| Removal | Dependencies, schema, data state after disabling | Validation results |

A cleanly compiling JAR can still crash the JVM, degrade I/O, or alter system semantics. Reviewing a plugin must therefore carry the same rigor as a **server code change**.

## 13. Custom Triggers, Indexes, and Extension Points Can Have Distinct CQL DDL

Do not lump everything under "UDF."

- **Triggers:** on some Cassandra releases, reference server-side classes and require enabling flags. Code runs on DML callbacks and can impact write latency.
- **Custom indexes:** can use server-side implementations; index schema is CQL metadata while execution code comes from classpath/JARs.
- **Custom authenticators/authorizers:** sit directly on the login/authorization boundary. Bugs risk locking out admins or granting unintended access.
- **Custom compaction/internal extensions:** where supported, alter I/O cost and operational stability.
- **Driver codecs/policies:** run inside the Java client, not the Cassandra server.

**Each extension point has distinct syntax, DDL permissions, lifecycles, and risks.** Never extrapolate `GRANT EXECUTE ON FUNCTION` to creating custom indexes or attaching trigger classes.

This lesson illustrates exact permissions for functions; for triggers/indexes/plugins, consult docs for your **exact release and extension** before executing real commands.

## 14. Threat Model: What Can an Overly Broad Grant Lead To?

Consider these actors:

1. **Application role** whose credentials live in a service.
2. **Schema/deployment role** allowed to create functions or indexes.
3. **Operator/CI runner** allowed to deploy JVM code and restart nodes.
4. **Attacker** compromising one of those three credential types or a supply-chain artifact.
5. **Business user** sending inputs that make queries/UDFs resource-intensive.

Risk categories:

| Risk | Example | Mitigation |
| --- | --- | --- |
| **Privilege escalation** | Role granted overly broad function scope | Least privilege, role-graph reviews, never use superuser for apps |
| **Denial of service** | UDF/UDA allocates heavily or burns CPU, slowing nodes | Query bounds, resource testing, monitoring, rate limiting |
| **Supply chain** | Plugin/JAR contains compromised dependency | Version pinning, artifact verification, SBOM, approvals |
| **Data integrity** | Extension corrupts writes or misinterprets data | Schema/serialization tests, canary, auditing, and rollback |
| **Credential/secret exposure** | Plugin reads/logs secrets visible to the process | File/service isolation, secret management, no sensitive logging |
| **Availability failure** | Faulty auth plugin breaks logins/admin access | Staged rollout, break-glass plan, tested rollback |

No single `GRANT` policy solves all of these. In *defense in depth*, restrict both **who can invoke** and **how new code enters the server**.

## 15. When Should You Avoid UDFs Altogether?

Computing inside CQL is not automatically optimal. Choose based on where CPU and trust boundaries belong:

| Option | Pros | Cons | Best Fit |
| --- | --- | --- | --- |
| **Server-side Cassandra UDF** | Transforms values near read path; avoids duplicated client logic | Custom code runs in DB JVM; hard to isolate resources | Small, pure, approved calculations supported by version |
| **Java service** | Easy testing, deployment, circuit breakers, per-service resource isolation | May transfer slightly more raw data over network | Frequently changing or security-sensitive business logic |
| **Projection/precomputed table** | Fast query-time reads without per-read computation | Extra write/storage cost; requires reconciliation | Read-heavy APIs with stable calculation logic |
| **Stream processing/analytics** | Scales and isolates load away from OLTP Cassandra | Needs pipelines/checkpoints and data convergence | Large aggregations, batch/stream workloads |
| **Built-in CQL functions** | Zero custom code uploaded to cluster | Limited to built-in features | Simple conversions already supported by engine |

### Example Moving Logic to Java

Instead of `lab.score_plus_one(score)` in `SELECT`, read the raw value:

```cql
SELECT score
FROM lab.metric_by_id
WHERE device_id = 'device-01';
```

Then compute in the Java service. This is usually far easier to roll out and roll back, especially when organizations keep UDFs disabled on production Cassandra.

With sensitive data, never grant Java services access to every column just because logic moved client-side. **`SELECT` permissions and app-layer data controls must still be minimized.**

## 16. Java Driver 4.x: Testing a UDF with an Authorized Role

Java 4.x example using a `CqlSession` configured **to log in as the exact test role**, with local DC and environment TLS enabled. This snippet creates no roles and hardcodes no passwords:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class UdfAuthorizationProbe {
    private final CqlSession session;
    private final PreparedStatement byDevice;

    public UdfAuthorizationProbe(CqlSession session) {
        this.session = session;
        this.byDevice = session.prepare(
            "SELECT score, lab.score_plus_one(score) AS adjusted_score " +
            "FROM lab.metric_by_id WHERE device_id = ?"
        );
    }

    public Integer readAdjustedScore(String deviceId) {
        BoundStatement stmt = byDevice.bind(deviceId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(stmt).one();
        if (row == null || row.isNull("adjusted_score")) {
            return null;
        }
        return row.getInt("adjusted_score");
    }
}
```

Required conditions:

- Cluster **enables the corresponding UDF type**, and schema contains `lab.score_plus_one(int)`.
- Login role holds `SELECT` on the table and `EXECUTE` on the exact function signature.
- RF/datacenter matches `LOCAL_QUORUM`; each environment configures the right driver local DC.
- Never assume `prepare` succeeding proves sufficient rights; verify **execution** and negative tests.
- `setIdempotent(true)` fits a pure `SELECT`; **never enable speculative execution blindly**.

### Never Swallow Authorization Errors

In production, classify failures properly:

- **Authentication failure:** credentials or login mechanism rejected.
- **Authorization failure:** role logged in but lacks resource permission.
- **Feature disabled / invalid function:** server disallows UDFs or function is missing/incompatible.
- **Execution error:** function body throws or exceeds resource limits.
- **Timeout:** coordinator/replica/driver failed to respond in time—typically load, not missing permissions.

Never retry unrecoverable permission errors indefinitely. Retry storms flood logs and cluster resources.

## 17. Security Testing: Include Both Positive and Negative Tests

### Recommended Test Matrix

| Actor / Role | `SELECT lab.metric_by_id` | `EXECUTE lab.score_plus_one(int)` | `CREATE` UDF | Expected |
| --- | --- | --- | --- | --- |
| `app_reader` | Yes | Yes | No | `SELECT` with UDF succeeds |
| `read_only_without_udf` | Yes | No | No | Plain `SELECT` succeeds; UDF call denied |
| `udf_maintainer` | Per duty | Only if needed | Yes in `lab` keyspace | Can deploy within scope |
| `unrelated_service` | No | No | No | Denied both read and call |
| Test superuser | High | High | High | Only to verify setup, never as a service role |

Create and use roles in a **lab cluster with proper authentication+authorization**, never testing as superuser and assuming RBAC works.

### Testing Additional Boundaries

1. **Feature gate off:** function fails to run even when role holds `EXECUTE`; check error reporting.
2. **Grant one signature:** role cannot automatically call another overload.
3. **Revoke:** role loses permission after cache convergence; other services keep access as planned.
4. **DROP/replace attempt:** a role with only `EXECUTE` cannot alter the body or drop the function.
5. **Oversized inputs:** UDF handles nulls, empties, boundary values, and overflow per spec.
6. **Load testing:** scale QPS/rows; confirm CPU/GC/p99 remain within SLO.
7. **Node failure/rollout:** verify cluster behavior when one node lacks a plugin or errors—depends on extension; test in lab.
8. **Audit/tracing:** trace roles/DDL/authz errors without leaking sensitive data.

Never run malicious bodies or sandbox-escape attempts in production "to verify." Evaluate code inside isolated environments owned by security reviewers.

## 18. Auth Caches, Role Inheritance, and Revocation Latency

Cassandra can cache roles, authentication, and permission data depending on version/configuration. Therefore:

- A `GRANT` or `REVOKE` may not take effect simultaneously across every node instantly.
- Clients with open sessions may stay connected; per-request enforcement depends on server checks and caching.
- A role may inherit `EXECUTE` **indirectly** via a granted parent role.
- Revoking one direct grant may **not be enough** if a parent role still grants the same or broader scope.

### How to Confirm Revocation

1. Inventory the role graph and function permissions.
2. Revoke across all relevant resource scopes.
3. Inspect permission metadata via release-supported API/CQL.
4. From the restricted role, execute a **real** query to prove denial.
5. Test across multiple coordinators in multi-node/multi-DC clusters with auth caches.
6. Verify no alternate credentials/service accounts still hold the unintended rights.

**Never restart the whole cluster "to force fast revocation"** without understanding the mechanism and availability impact. For emergency lockouts, follow runbooks for credential rotation, disabling roles, network isolation, or supported admin tools.

## 19. Auditing and Observability: Is Function Execution Slowing Nodes Down?

Auditing tells you **who** created/altered/called risky features and **when**. Monitoring detects **resource impact**.

### Events to Capture

- Who proposed, approved, and deployed functions/plugins; versions, hashes, timestamps.
- Grant/revoke/role changes and authentication/authorization failures.
- Schema DDL for functions/aggregates/indexes/triggers per release audit support.
- Errors and timeouts on queries invoking functions.
- Plugin rollout/rollback events, node restarts, classpath/config edits.

**Never assume Cassandra auditing logs every individual UDF invocation**, as event types, audit filters, and logging capabilities vary by release. If per-function call counts are needed, add telemetry at the application/driver layer or appropriate observability hooks without exploding label cardinality.

### Metrics to Monitor

| Metric | Why It Matters |
| --- | --- |
| CQL read/write p95/p99 and timeouts | Are application SLOs impacted? |
| Request rate per query shape calling UDFs | Is the function on a hot query path? |
| Process/node CPU and container throttling | Is code or UDA saturating CPU? |
| JVM heap/GC pauses, native memory/RSS | Is the body/UDA/plugin leaking or allocating heavily? |
| `nodetool tpstats` pending/dropped | Are execution stages backing up? |
| Disk read/write latency and compaction | Are UDF queries over huge partitions worsening read amplification? |
| Crashes/restarts/OOMs | Is a plugin threatening availability? |
| Permission-denied rate | Misconfigured permissions or suspicious probing? |
| Deployed version/hash per node | Plugin drift across replicas/DCs? |

**One rising metric does not automatically prove a UDF is at fault.** Correlate deploy times, query profiles, GC logs, network/compaction/repair activity, and comparable workloads before rolling back.

## 20. Relationship to Consistency Levels and Multi-DC Architecture

Cassandra picks replicas by partition key, token, and RF; the coordinator replies once the consistency level is met. UDFs run inside server-side query processing and can lengthen execution, yet **do not alter quorum math**.

With RF=3 in one DC:

- `LOCAL_ONE` requires one local replica to respond.
- `LOCAL_QUORUM` requires two replicas in the coordinator's DC to respond.
- One replica slowed by a UDF/plugin can stretch read latency or trigger timeouts depending on request routing.
- In multi-DC setups, global `QUORUM` may need remote-DC ACKs; uneven plugin/extension rollouts across DCs complicate diagnosis.

**Never treat `LOCAL_QUORUM` as a security sandbox.** It sets request consistency, not resource or capability limits on server-side code.

### Protecting the Write Path

A server-side extension attached to the mutation path (where supported) can affect commit logs, memtables, write paths, and replication latency.

When a plugin causes a write timeout, the write outcome is **uncertain** to the client: some replicas may have already applied the mutation. Retries must account for idempotency, timestamps, LWTs, and business consequences.

Monitor both **read and write paths** and evaluate how a fault on one replica affects application-wide quorum.

## 21. Version-Specific Deployment Compatibility

Plugins and UDFs running inside Cassandra carry many version-specific constraints:

| Area | What to Verify |
| --- | --- |
| Cassandra release | CQL function syntax, enablement flags, RBAC function resources |
| JDK/runtime | Supported Java APIs, sandbox/execution limits |
| Plugin binary | ABI/API compatibility with Cassandra and dependencies |
| Schema | Function signatures, UDA state/final functions, index/trigger definitions |
| Mixed-version cluster | Have all request-handling nodes received compatible versions? |
| Rolling restart | Is a restart needed to load JARs or config changes? |
| Rollback | Can artifacts and schemas revert without breaking data formats? |
| Observability | Are audits/metrics/reporting sufficient to confirm safety? |

Never assume a flag name, plugin class, or grant command behaves identically across Cassandra 3.x, 4.x, 5.x, or CQL-compatible products. **Re-test on the exact matching version/configuration** before every rollout.

## 22. Approval and Rollout Process for UDFs/Plugins

### Phase A — Triage the Request

1. Document the use case and exact queries requiring the extension.
2. Ask whether built-in CQL functions, a Java service, or a projection table can solve it instead.
3. Classify accurately: UDF, UDA, trigger, index, server plugin, or client codec.
4. Identify accessed data, code behavior, dependency sources, and least privilege.
5. Verify feature gates and version compatibility.

### Phase B — Review and Testing

6. Separate the code author from the execution/deployment approver.
7. Review code, dependencies, purity/idempotency, and boundary-input handling.
8. Verify no unauthorized external I/O or side effects per runtime capabilities.
9. Build negative tests for `SELECT`/`EXECUTE`/`CREATE`/`DROP` rights.
10. Benchmark CPU, memory, GC, p99, and failure modes in a lab with representative data.
11. Define safe rollback, including query/index/aggregate dependencies.

### Phase C — Deployment

12. Record change ticket, artifact hash, role/resource scope, and schedule.
13. Canary roll out by node/rack/DC if the plugin requires it.
14. Synchronize schemas and permissions; grant `EXECUTE` only to roles that genuinely need it.
15. Canary the application via Java Driver with production-like local DC, RF, and CL.
16. Monitor p95/p99, timeouts, GC, CPU, disk, and permission errors.

### Phase D — Post-Deployment Verification

17. Confirm uniform plugin versions across relevant nodes.
18. Verify audit logs and change traceability.
19. Remove temporary rights or deployment credentials once done.
20. Re-measure SLOs across a cycle covering real compaction/repair/load.
21. Archive rollback runbooks and security review evidence.

Never declare a canary successful just because one query on one node returned `42`. Verify **permissions, correctness, performance impact, and rollout uniformity**.

## 23. Runbook When a UDF/Plugin Causes Errors or Shows Signs of Abuse

### A — "Not Authorized" Error Calling a UDF

**Signs:** app reads the table normally, yet `SELECT` invoking the function is denied.

**Check:** actual logged-in role, table `SELECT`, `EXECUTE` on exact function signature, role inheritance/permissions cache.

**Fix:** grant least privilege after approval or rewrite the query without the UDF. Never make the service a superuser just to clear the error.

### B — Role Holds `EXECUTE` Yet Server Rejects Function

**Signs:** error reports feature disabled, unsupported function/runtime, or missing function.

**Check:** Cassandra version, feature flags, schema/function signatures, and mixed-version cluster state.

**Fix:** fix deployment/config via controlled change, or move computation to the Java app. Never enable UDFs in production without review.

### C — After Rollout, p99 and GC Spike

**Signs:** higher read p99, heavy CPU/GC allocations, rising pending reads/dropped messages.

**Check:** share of queries calling UDF, rows per query, hot partitions, GC/CPU timelines, and plugin rollout state.

**Fix:** throttle traffic or roll back per runbook; move computation to services if appropriate. Never just bump read timeouts.

### D — Plugin Missing on Some Nodes

**Signs:** requests succeed via some coordinators/replicas while other nodes throw class-not-found or initialization errors.

**Check:** artifact checksums, classpath, restart status, per-node compatibility, and topology.

**Fix:** halt rollout expansion and return the cluster to a uniform version per plan; never ad-hoc patch node classpaths outside change control.

### E — Admin Lockout Due to Custom Authenticator/Authorizer

**Signs:** both operators and applications fail to log in or manage permissions after a plugin swap.

**Check:** deployment/config logs, role backend, and lab-tested fail-safe mechanisms.

**Fix:** trigger approved break-glass/rollback procedures; protect credentials and preserve evidence. This is far higher risk than a simple UDF.

### F — Overly Broad `EXECUTE` Permission Discovered

**Signs:** an app role holds `EXECUTE ON ALL FUNCTIONS` or inherits broad scope.

**Check:** role graph and actual callers/functions; check whether other apps depend on it.

**Fix:** inventory callers, grant per-signature replacements, verify traffic, then revoke the broad scope; verify cache convergence and other roles.

### G — UDA Exhausting Memory on Large Scans

**Signs:** high aggregate query p99, rising heap/native memory, GC thrashing/OOM.

**Check:** state size, partition size, fan-out, row counts, and processing stage.

**Fix:** stop/rate-limit the risky query and move to pre-aggregation or external processing; never raise heap limits indefinitely.

## 24. Sample Production Permission Matrix

| Actor | Tables to Read | Function `EXECUTE` | Function DDL | OS / Plugin Deployment |
| --- | --- | --- | --- | --- |
| API service | Only tables required by API | Only approved signatures | No | No |
| Batch analytics | Approved tables only | Dedicated functions if needed | No | No |
| Schema CI/CD | Per migration | Conditional | `CREATE`/replace/`DROP` in assigned keyspace | No by default |
| Security team | Metadata/audits per policy | Not needed to read audits | Approved grant/revoke management | No by default |
| Platform operator | When operationally needed | No by default | No by default | Yes, via approved pipeline |
| Emergency admin | Per break-glass | Per incident | Per incident | Per incident, time-bounded |

Principles:

- **Separation of duties:** code reviewers, permission grantors, and deployers should not all be one account.
- **Time-bounded privileges:** revoke temporary DDL/deployment rights once finished.
- **No secrets in CQL/scripts:** store passwords and tokens in secret managers/CI protected variables.
- **Audit all privilege changes** and periodically review role scopes.
- **Shrink blast radius:** keyspace, table, function signature, node/DC rollout, and app rate limits.
- **Rehearsed rollback:** never wait for a production outage to figure out how to remove a plugin.

## 25. Common Mistakes

**"Having `SELECT` on a table automatically permits calling any UDF."** False when function authorization is enabled and enforced per release. Check `EXECUTE` on the function resource.

**"`EXECUTE` on a function allows modifying that function's code."** False. Invoking and managing definitions are separate permissions.

**"Once UDFs are enabled, every role can use them freely."** Check the active authorizer and RBAC; feature enablement and role permissions are two separate layers.

**"Plugins can be blocked using `REVOKE EXECUTE ON FUNCTION`."** No guarantee. Server Java plugins execute under deployment rights and extension runtimes, not necessarily as CQL functions.

**"If a UDF is written in Java, it runs inside the Java Driver."** False. CQL UDFs execute on Cassandra nodes during query handling; the Java Driver only sends requests and reads results.

**"A function with no I/O cannot affect the cluster."** False. CPU burn, memory allocations, and errors across many rows still spike p99.

**"A simple UDF called over millions of rows stays cheap."** Doubtful. Per-row cost multiplies by evaluation count plus read amplification.

**"`LOCAL_QUORUM` guarantees a UDF cannot affect other nodes."** False. CL is not a resource-isolation policy.

**"Granting on `ALL FUNCTIONS IN KEYSPACE` is equivalent to one function."** False. Broad scope automatically covers future functions added later.

**"Revoking a permission immediately stops every active session."** Never assume this; account for caches, in-flight requests, and role inheritance.

**"Superuser is easier, so give service accounts superuser."** A severe anti-pattern that destroys blast-radius containment when credentials leak.

**"Deploy a new JAR to one replica and consider the cluster plugin-ready."** False. Compatibility/rollout must be assessed across topology and request paths.

**"CQL permissions replace OS file permissions on the classpath."** False. Those are two separate security boundaries.

**"A query succeeding means the plugin is safe."** False. Supply-chain, side-effect, memory/CPU, mixed-version, and data-correctness risks remain.

**"Disable auditing to save CPU when a UDF is slow."** Wrong fix; profile the real cost while preserving required security evidence.

## 26. Questions and Exercises

1. Distinguish authentication, authorization, and feature gates when a role wants to call `lab.score_plus_one(int)`.
2. Why must table `SELECT` and function `EXECUTE` be verified separately?
3. What role does a function signature play when two overloads `lab.f(int)` and `lab.f(text)` exist?
4. Compare the risk of granting `EXECUTE` on one signature vs. `ALL FUNCTIONS IN KEYSPACE`.
5. When modifying a UDF body, which permissions/workflows besides `EXECUTE` must be checked?
6. Why does granting superuser to a Java service to call a UDF violate least privilege?
7. A UDF is fast for one row yet spikes p99 on a 5-million-row partition. Analyze why.
8. Why does a UDA whose state grows with item count risk OOM?
9. A plugin JAR is installed in the Cassandra JVM, yet the app role lacks `EXECUTE` UDF rights. Is the plugin automatically disabled? Why or why not?
10. Distinguish a custom codec in the Java Driver from a server-side plugin.
11. If the cluster disables UDFs on the server, can a role holding `EXECUTE` run them?
12. Why shouldn't `enable_user_defined_functions` be enabled directly in production just to test one function?
13. A role lost direct permissions yet can still call a UDF; how should you investigate role inheritance/caching?
14. A UDF grant was revoked, yet old-behavior requests persist; where can that come from?
15. Build a table for three roles—`app_reader`, `udf_maintainer`, and `platform_operator`—granting least privilege to each.
16. How do you verify a role can read a table yet is denied calling a UDF without using superuser?
17. A new plugin raises `tpstats` pending/dropped counts. Which metrics help isolate the cause?
18. In a two-DC RF=3 cluster, how can a buggy UDF/plugin on one node affect `LOCAL_QUORUM`?
19. Why shouldn't one successful query on one node count as proof that a JAR/plugin is fully deployed?
20. When a faulty custom authorizer breaks logins, how should the break-glass runbook be prepared?
21. List the required artifacts to retain: artifact hashes, security reviews, grant/revoke records, benchmarks, canary results, and rollback plans.
22. Give cases where moving UDF logic to a Java service or precomputed table is better.
23. If a plugin has a dependency CVE, why are SBOM scanning and version pinning needed even if the CQL role only holds `SELECT`?
24. Explain the difference between CQL execution rights and OS/JVM rights in defense in depth.
25. Design a negative test confirming an app role cannot create, replace, or drop other functions.

## 27. Decision Flow

```text
EXTENSION FEATURE REQUESTED ON CASSANDRA
                         |
                         v
      Can it be solved with built-in CQL,
      a Java service, or a projection table?
                  |                   |
                 Yes                  No
                  |                   |
         Prefer the lower-            v
         privilege solution      Is it a UDF/UDA or a plugin?
                                        |
                       +----------------+----------------+
                       |                                 |
                    UDF/UDA                        Server plugin
                       |                                 |
             Check feature gate                  Review artifact, OS,
             + version + CQL RBAC                classpath, rollout
                       |                                 |
             GRANT exact signature               Control CI/CD and
             + required role                     deployment admin
                       |                                 |
                       +----------------+----------------+
                                        |
                               Lab security + load test
                                        |
                              Canary/metrics/rollback
                                        |
                           Monitor p99, CPU, GC, errors
                                        |
                             Periodic audits & reviews
```

**Key Takeaway:** Permission to run a UDF is a **CQL privilege on a function resource**, yet actual UDF execution also depends on **Cassandra's feature gates and runtime**. Server plugins/extensions are **code changes inside the server's trust boundary**, uncontrollable by `GRANT EXECUTE` alone. Protecting the cluster requires **signature-level least privilege, separating creators from callers, OS/classpath controls, code/dependency reviews, p99/GC/CPU benchmarking, and tested rollbacks**. Above all, never trade the safety of every replica just to save a trivial computation easily done in the Java application.
