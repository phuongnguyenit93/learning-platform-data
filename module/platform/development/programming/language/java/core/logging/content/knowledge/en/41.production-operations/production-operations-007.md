# Production Log Access Control: Protecting Data and Supporting Java Operations

## 1. Concepts and Goals

**Production log access control** is the definition and enforcement of **who can read, search, write, export, delete, administer, or share which logs in a production environment**, when, and for what reason. It is not just permission to view a dashboard: application logs can flow from a Java logger through stdout/files, container runtimes, collectors, backends, snapshots, archives, alerts, and export files.

Production logs often contain transaction metadata, request IDs, trace IDs, user IDs, IP addresses, stack traces, service names, deployment details, and access history. A logging bug can also put passwords, tokens, or personal data into these places. Therefore, someone with permission to view logs can sometimes infer customer activity, internal architecture, or see exposed credentials.

The **dual goal** of an access control system is: on-call operators can still find evidence to resolve incidents, **but only access the exact amount of data needed**. Foundational principles:

- **Least privilege:** grant only the actions, datasets, environments, and duration needed.
- **Deny by default:** any permission not explicitly granted cannot be exercised.
- **Need to know:** access is tied to an investigation purpose, job responsibility, or valid request.
- **Separation of duties:** permissions to ingest, read, export, delete, configure, manage access, and audit are not arbitrarily bundled together.
- **Strong authentication:** verify identity before evaluating permissions; use MFA/JIT when risk requires it.
- **Auditability:** trace who viewed, exported, deleted, shared, or granted permissions.
- **Defense in depth:** enforce controls at the log source, query backend, runtime/node, secondary storage, and export paths.

After this lesson, you will be able to distinguish RBAC/ABAC, design a permission matrix, understand Kubernetes `pods/log`, run a standalone Java 17 example, verify permissions from backend to archive, and build an audited emergency access workflow.

## 2. Data Boundaries: Where Do Logs Travel?

```text
Java code / SLF4J / Logback / Log4j 2 / JUL
                    |
              Console / File
                    |
           Docker / Kubernetes
                    |
            Collector / Agent
                    |
          Log ingestion endpoint
                    |
        +-----------+-----------+
        |                       |
  Standard log index      Restricted/audit index
        |                       |
        +---- Search API -------+
        |          |            |
    Dashboard    Export      Alert/incident
        |          |            |
        +----------+------------+
                    |
           Archive / backup / snapshot
```

**Each hop has its own permission system:**

1. Application: who can change log levels, enable debug payloads, modify appenders, or add fields?
2. Container/node: who has `docker logs`, `kubectl logs`, node file read access, `pods/exec`, or permission to modify workloads?
3. Collector: which identity can send to which dataset/index, and can it search or export?
4. Backend: authn, query permissions by tenant/service, document/field filtering, and dashboard sharing.
5. Storage: bucket/object permissions, snapshots, backups, decryption keys, and downloads.
6. Alert/ticket/chat: do notifications include raw log excerpts, and who are the recipients?
7. Administration: who grants permissions, deletes data, changes retention, and views audit logs about themselves?

Hiding the "View logs" button in the UI **does not protect** against someone with a Search API token, someone who can read log files on the node, or someone allowed to download snapshots from object storage. Policies must be applied **along the actual data path**, not just in one UI application.

## 3. Classify Logs Before Granting Permissions

An illustrative model:

| Classification | Contents | Reference Audience |
| --- | --- | --- |
| `STANDARD` | Event code, route template, status, duration, service, vetted request ID | Service on-call within scope |
| `INTERNAL` | Controlled stack traces, dependency aliases, internal IDs | Engineering teams genuinely needing diagnostics |
| `RESTRICTED` | Administrative activity audits, investigation records, customer identifiers retained per policy | Approved teams, narrow permissions |
| `HIGHLY_RESTRICTED` | Data for severe incidents or requests with special restrictions | Separate approval and retention workflow |

This is only an **example**; organizational policy determines the names and criteria. Do not classify mechanically by log level: an `INFO` line recording who viewed a private profile can be more sensitive than an `ERROR` containing only a class name and error code.

**Do not create a "raw credential log store" as normal practice.** Passwords, access tokens, refresh tokens, API keys, private keys, session cookies, and request bodies containing secrets should be stripped from events before reaching the logger. RBAC, encryption, retention, and downstream masking cannot make logging secrets safe.

A hashed user ID or IP can still be correlated across events; masking a few characters does not automatically turn data into `STANDARD`.

## 4. Action-Based Permissions, Not Just READ/ADMIN

| Conceptual Permission | Allows | Does Not Implicitly Grant |
| --- | --- | --- |
| `LOG_INGEST` | Push logs into the right index/tenant | Query, export, delete |
| `LOG_READ_STANDARD` | Query standard-level logs within scope | Restricted data |
| `LOG_READ_RESTRICTED` | Query approved restricted datasets | Bulk export or admin |
| `LOG_EXPORT_STANDARD` | Export standard logs within limits | Export restricted |
| `LOG_EXPORT_RESTRICTED` | Export restricted logs under separate policy | Delete or change retention |
| `LOG_MANAGE_PIPELINE` | Change parsers, collectors, destinations via workflow | Default raw log reading |
| `LOG_MANAGE_RETENTION` | Manage approved lifecycle/retention | Unconditional deletion |
| `LOG_DELETE` | Delete/quarantine with authorization and evidence | Deleting one's own access audit |
| `LOG_MANAGE_ACCESS` | Grant/revoke scoped permissions | Automatic reading of all data |
| `LOG_AUDIT_READ` | View access audits | Modify/delete audit events |

These are lesson-defined names, **not built-in permission names** across every log backend.

Key distinctions:
- **READ differs from EXPORT**: searching a few log events via a dashboard carries different risk than generating a ZIP/CSV file containing the entire history.
- **INGEST differs from READ**: a collector needs to write data, not download historical events.
- **CONFIGURE differs from DATA ACCESS**: someone editing the pipeline is not automatically authorized to view restricted data.
- **DELETE differs from MANAGE RETENTION**: retaining data by policy differs from manually deleting a set of records.
- **AUDIT READ differs from APPLICATION LOG READ**: audits of who viewed logs usually need separate protection.

**Warning about indirect permissions:** An admin can change a collector destination, create an API token, or edit a policy to obtain raw logs. Separating roles on paper alone will not prevent that without change approval, immutable audits, or privilege escalation controls.

### 4.1. Sample Role Matrix

| Role | Read | Ingest | Export | Admin |
| --- | --- | --- | --- | --- |
| Application developer | Staging and filtered production logs for supported services, per policy | No | Not by default | No |
| Production on-call | `STANDARD/INTERNAL` for owned team and environment | No | Requires separate permission | No |
| Security analyst | Audit/restricted datasets per approval | No | With audit/approval | Not by default |
| Collector service identity | No | Only to designated destination | No | No |
| Pipeline operator | Possibly pipeline metadata only | Via service identity if needed | No | Reviewed config changes |
| Retention administrator | Not by default | No | Not by default | Scoped retention |
| Break-glass responder | Specific dataset/incident/time window | No by default | Per separate approval | Incident-handling permissions only |

An on-call handling `orders-api` typically does not need to see payment audit logs from another team. Organizations may have more or fewer roles; what matters is ensuring **verifiable effective permissions**.

## 5. RBAC and ABAC

### 5.1. RBAC: Roles Bound to Permissions

**Role-Based Access Control** binds permissions to groups/roles, then authenticates the user/service account and evaluates membership:

```text
identity: alice
groups:   orders-oncall
role:     prod-orders-log-reader
grant:    LOG_READ_STANDARD
scope:    environment=prod AND service=orders
```

Pros: easy to manage by group, easy to review grants. Risks: role creep, staff changing teams while retaining old permissions, an overly broad `ALL_PROD_VIEWER` role, or a role name that sounds narrow while actually bundling many permissions.

Roles must be evaluated together with **resources**: cluster-wide `READ_STANDARD` is still broader than `READ_STANDARD` for a specific service and time window.

### 5.2. ABAC: Subject, Resource, and Context Attributes

**Attribute-Based Access Control** can evaluate:
- Subject: team, employment status, MFA, managed device, on-call rotation, approved incident.
- Resource: environment, service, tenant, classification, region, dataset owner.
- Action: read, ingest, export, delete, manage access.
- Context: purpose, requested time window, temporary elevation, source identity.

A conceptual policy:

```text
ALLOW READ
  IF subject.active
 AND subject.team == resource.owner_team
 AND subject.permissions CONTAINS "LOG_READ_STANDARD"
 AND resource.environment == "prod"
 AND resource.classification == "STANDARD"
 AND context.authentication_strength >= required_strength

DENY OTHERWISE
```

This is **pseudocode**, not specific syntax for IAM, OPA, or a logging backend. For RESTRICTED data, the policy may require an incident reference, approval, and TTL; do not edit the rule above with `OR true` to quickly resolve an incident.

### 5.3. Enforcement Must Live at a Trusted Boundary

An API that merely appends `service=orders` to a query in the browser is not enough. Users can modify requests with Developer Tools, call the backend directly, swap index aliases, use wildcards, or hit the export endpoint.

You need to:
1. Authenticate the subject/session/token at the backend or trusted gateway.
2. Check the action and dataset/tenant scope **before every query/export**.
3. Enforce row/document/field restrictions at a layer clients cannot bypass.
4. Limit time range, records, bytes, rate, and concurrency where appropriate.
5. Audit the decision/outcome, including DENY, without copying raw log data into the audit.
6. Verify whether saved queries, share links, raw document APIs, download endpoints, and service-to-service queries follow the same policy.

If a product does not provide trustworthy field-level security, you can **separate restricted logs into a dedicated index/tenant** and apply appropriate ACLs instead of claiming client-side masking is enough.

## 6. Java 17 Example: Simulating Log Read and Export Permissions

The program below **runs standalone on JDK 17**, using `java.util.logging` (JUL), simulating in-process access control. It intentionally has no real backend: it only demonstrates how **READ differs from EXPORT**, **INGEST does not imply READ**, and **CONFIGURE does not imply permission to view raw logs**.

All identities and record IDs are dummy data generated in code. In a real application, the principal must be built from trusted authentication results, classification must come from a controlled catalog/storage, and policies must be enforced on every query path.

Create `ProductionLogAccessDemo.java`:

```java
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ProductionLogAccessDemo {
    private enum Classification { STANDARD, RESTRICTED }
    private enum Action { READ, EXPORT }
    private enum Permission {
        READ_STANDARD, READ_RESTRICTED,
        EXPORT_STANDARD, EXPORT_RESTRICTED,
        INGEST, CONFIGURE
    }

    private record Principal(
            String id, Set<Permission> grants) {}

    private record LogEntry(
            String id, Classification classification) {}

    private static boolean permitted(
            Principal principal, LogEntry entry, Action action) {
        Permission read =
                entry.classification() == Classification.RESTRICTED
                ? Permission.READ_RESTRICTED
                : Permission.READ_STANDARD;

        if (!principal.grants().contains(read)) {
            return false;
        }

        if (action == Action.READ) {
            return true;
        }

        Permission export =
                entry.classification() == Classification.RESTRICTED
                ? Permission.EXPORT_RESTRICTED
                : Permission.EXPORT_STANDARD;

        // Export requires BOTH read permission and export permission.
        return principal.grants().contains(export);
    }

    private static void check(
            Logger audit, Principal principal,
            LogEntry entry, Action action) {
        boolean allowed = permitted(principal, entry, action);
        audit.info("actor=" + principal.id()
                + " action=" + action
                + " record=" + entry.id()
                + " class=" + entry.classification()
                + " decision=" + (allowed ? "ALLOW" : "DENY"));

        // Print only the decision; do not print raw log contents.
        System.out.println("RESULT actor=" + principal.id()
                + " action=" + action
                + " status=" + (allowed ? "ALLOWED" : "DENIED"));
    }

    public static void main(String[] args) {
        Logger audit = Logger.getLogger("lesson.production.log.access");
        audit.setLevel(Level.INFO);
        audit.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println("AUDIT " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        audit.addHandler(output);

        try {
            LogEntry standard = new LogEntry(
                    "evt-1", Classification.STANDARD);
            LogEntry restricted = new LogEntry(
                    "evt-2", Classification.RESTRICTED);

            Principal oncall = new Principal(
                    "oncall", Set.of(Permission.READ_STANDARD));
            Principal auditor = new Principal(
                    "security-auditor",
                    Set.of(Permission.READ_STANDARD,
                            Permission.READ_RESTRICTED));
            Principal collector = new Principal(
                    "collector", Set.of(Permission.INGEST));
            Principal configAdmin = new Principal(
                    "config-admin", Set.of(Permission.CONFIGURE));

            check(audit, oncall, standard, Action.READ);
            check(audit, oncall, restricted, Action.READ);
            check(audit, auditor, restricted, Action.READ);
            check(audit, auditor, restricted, Action.EXPORT);
            check(audit, collector, standard, Action.READ);
            check(audit, configAdmin, restricted, Action.READ);
        } finally {
            audit.removeHandler(output);
            output.close();
        }
    }
}
```

Compile and run:

```bash
javac ProductionLogAccessDemo.java
java ProductionLogAccessDemo
```

**Exact stdout** in a fresh JVM with no other component interfering with the logger:

```text
AUDIT actor=oncall action=READ record=evt-1 class=STANDARD decision=ALLOW
RESULT actor=oncall action=READ status=ALLOWED
AUDIT actor=oncall action=READ record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=oncall action=READ status=DENIED
AUDIT actor=security-auditor action=READ record=evt-2 class=RESTRICTED decision=ALLOW
RESULT actor=security-auditor action=READ status=ALLOWED
AUDIT actor=security-auditor action=EXPORT record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=security-auditor action=EXPORT status=DENIED
AUDIT actor=collector action=READ record=evt-1 class=STANDARD decision=DENY
RESULT actor=collector action=READ status=DENIED
AUDIT actor=config-admin action=READ record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=config-admin action=READ status=DENIED
```

**Explanation:** on-call can read standard but not restricted; security auditor can read restricted yet lacks `EXPORT_RESTRICTED` so export is denied; collector has `INGEST` without READ permission; config admin has `CONFIGURE` and does not automatically become a data reader.

The custom JUL handler prints `AUDIT` to stdout, while `setUseParentHandlers(false)` prevents the root ConsoleHandler from writing a duplicate line. These events do not contain raw log bodies. In production, access audits should include a timestamp, verified actor, source, resource scope, and incident ID, and be stored in a protected sink.

**Intentional limitations:** This program is an in-memory model only—no identity authentication, no tenant/service/time/approval checks, no expiry, no durable audit storage, and no session or authorization caching management. In particular, `LOG_INGEST` in the demo is a permission name without an implemented INGEST action; it only proves that the permission **does not grant READ**. Do not use this code as a complete IAM/authorization solution.

## 7. Kubernetes RBAC: The `pods/log` Permission

In Kubernetes, `kubectl logs` typically accesses the Kubernetes API subresource **`pods/log`**. The `get` verb on this subresource is a key part of viewing logs within a namespace. This permission **is distinct from** querying a centralized logging system.

An **illustrative-only** YAML example of a namespaced Role and RoleBinding:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: application-log-reader
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: application-log-readers
  namespace: production
subjects:
  - kind: Group
    name: production-oncall-log-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: application-log-reader
  apiGroup: rbac.authorization.k8s.io
```

Meaning and limitations:
- `Role` applies within the `production` namespace; it does not grant cluster-wide permissions.
- `RoleBinding` binds the role to a group; whether a real user belongs to that group **depends on your IdP/authentication setup**.
- `get pods/log` in this example can view logs of **every Pod in the namespace**, regardless of team or classification. If a namespace mixes sensitive and less sensitive applications, you need a different namespace/ACL structure or a log backend with service-scoped authorization.
- This grant does not allow `pods/exec` or `secrets/get`, but a user with other powerful permissions **may find alternative paths to the data**, even when `pods/log` is blocked.
- Reading logs via the Kubernetes API does not grant permission to read centralized log indices/snapshots; conversely, backend viewer permissions do not automatically grant `kubectl logs`.
- Kubernetes logs are subject to rotation, pod restarts, and node storage limits; RBAC does not turn `kubectl logs` into an archive.

You can check the current context's permissions:

```bash
kubectl auth can-i get pods/log -n production
kubectl auth can-i list pods -n production
kubectl logs pod/orders-api-abc -n production -c app --tail=50
```

Pod/container names are illustrative. `kubectl auth can-i` verifies one authorization question at the moment of invocation; it **does not prove the entire log access path is secure**.

### 7.1. Check Indirect Infrastructure Permissions

Do not look only at `pods/log`:
- `pods/exec` can allow running commands inside a container.
- Permission to edit Pods/Deployments or create privileged workloads can lead to accessing files, volumes, or credentials.
- Node access, `hostPath`, SSH, or kubelet/node filesystem access can expose container log files.
- Permission to read Secrets, cloud workload identities, or collector tokens can open a path into the backend.
- Permission to modify collector configs can redirect logs to another destination.
- Permission to edit audit policies/retention or delete logs can cover up activity.

Kubernetes API audit (if enabled/configured) can record `pods/log` calls; the central log backend also needs its own audit for search/export/delete operations within that backend.

## 8. Central Logging: Permissions in Search, API, Index, and Dashboard

A centralized logging system typically includes:
- **Authentication:** SSO/OIDC/SAML/LDAP or equivalent, MFA, and session policies.
- **Authorization:** role/index/dataset/tenant permissions, and in some products document-/field-level controls.
- **Ingest API:** service tokens used to write data.
- **Search API:** querying logs under the caller's identity.
- **Export/snapshot:** generating files, objects, or data copies.
- **Administration:** changing retention, parsers, roles, alerts/routing, and policies.
- **Access audit:** recording who searched, exported, modified permissions, or deleted data.

Not every product has the same capabilities or permission names. For example, `viewer` on two different platforms may differ in raw API access, exports, and saved queries. **Always verify actual permissions and the running version**.

### 8.1. Commonly Forgotten Bypass Paths

A sound policy does not block only in the dashboard. Check:
- Direct API requests instead of the UI.
- Wildcard index/tenant or alias queries.
- Raw document endpoints retrieving by ID.
- Saved queries, dashboard panels, or alerts running under an owner/service account's permissions.
- Shared URLs, embeds, snapshots, and export jobs.
- API tokens issued before a role change.
- Batch queries, aggregations, suggestions/autocomplete, and field previews.
- Exports to object storage read directly via cloud IAM.
- Caches holding stale data after revocation.

If field-level redaction happens only in the UI, raw data may still be exposed via the API or exports. Access control **must be enforced at the backend or trusted gateway**, and when field-level enforcement cannot be guaranteed, separate restricted data into a dataset/index with its own ACL.

### 8.2. Collectors Should Not Have Viewer Permissions

Collectors should have their own identity and `write-only` access to the designated destination. Do not issue one admin token for both collectors and dashboards just to simplify configuration. You should:
- Scope by dataset, namespace, and service/tenant where supported.
- Use a secret store/workload identity, with rotation, expiration, and usage monitoring.
- Never hardcode keys in repositories, container images, or logged command lines.
- Apply quotas/rate limits to prevent ingest spam.
- Authenticate sources so one collector cannot spoof audit events for another tenant.
- Do not grant read, export, delete, or role-admin without an explicit, separate requirement.

Even ingest-only permissions carry risks of **data poisoning** (writing fake logs) and inflated ingest costs; least privilege only reduces the blast radius.

## 9. Read and Export: Governing Data Copies

**Being allowed to search a set of logs does not mean being allowed to download millions of records.** When exporting:
- Data leaves the backend's query and retention controls.
- CSV/ZIP files can be saved on personal machines, emailed, or attached to tickets.
- Shared links or signed URLs may remain usable after the creator's role changes.
- Exported files might include fields hidden in the UI if the export pipeline differs.
- Snapshots/backups might be readable through independent storage IAM.

A restricted export workflow should have a dedicated permission, scope/time range, justification, approval when required by policy, record/byte limits, controlled storage location, export TTL/retention, and **actual auditing** (who, when, which data, and success/failure status).

Separate two events:
- `EXPORT_AUTHORIZED`: the system permitted the operation.
- `EXPORT_COMPLETED`: the export succeeded, with data and destination matching the contract.

Do not log `EXPORT_COMPLETED` as successful merely because the permission check returned ALLOW; storage or network operations can fail.

### 9.1. Archives, Backups, and Decryption Permissions

Log data moved to object storage, snapshots, or backups still requires separate IAM/ACLs. Object read permission + key decryption permission can create a read path outside the UI. A backup admin could copy all data even without being granted backend `LOG_READ_RESTRICTED`.

Review:
- Who can list/get/export archive objects?
- Who has permission to decrypt the keys?
- Can snapshots be copied to another account/region?
- How are retention and legal holds applied?
- When a user is revoked, do existing exports/signed URLs still exist and remain usable?

Do not assume deleting a log index deletes all copies, or that revoking a role deletes already-downloaded ZIP files.

## 10. Scoping by Time, Team, Tenant, and Incident

A useful scope is typically a combination:

```text
subject  = team:orders-oncall
action   = READ
dataset  = prod-application-logs
service  = orders-api
tier     = STANDARD
window   = incident-related, bounded
purpose  = production-incident-investigation
```

If multiple tenants share a backend, the tenant ID must be **attached from a trusted metadata source** and enforced server-side. Never trust a client-supplied query parameter or log field to determine tenant scope.

**Do not treat a request ID as an access credential.** A request ID is useful for searching, not as a credential or proof of authorization. When scoping to an incident, combine identity, grants, and dataset scope; the ID is only a secondary filter.

Temporary/JIT (just-in-time) permissions help reduce long-lived roles. Upon expiration, check sessions, token caches, saved dashboards, and generated exports; a policy that expires on paper may not immediately invalidate old tokens.

## 11. Break-Glass: Audited Emergency Access

**Break-glass** means a controlled elevation path for severe incidents—not a shared root password.

A reference workflow:
1. The responder states the incident ID, reason for needing restricted logs, service/dataset, and time window.
2. Strong authentication; approval based on risk level. In extreme emergencies, policy may allow pre-elevation with **mandatory alerting and post-incident review**.
3. Grant **only the exact action** (usually READ) and exact scope; do not grant EXPORT/DELETE by default.
4. Grants have an expiry (duration set by policy), never permanent access.
5. Access audits record actor, scope, incident, approver, grant changes, and all related queries/exports.
6. Automatic revocation; verify whether sessions, tokens, or links remain usable.
7. Post-incident review: was access used beyond scope, was data exposed, and can the need for restricted logs be reduced with a better schema?

Do not copy raw secrets into tickets, Slack/email, or uncontrolled screenshots just because you are handling an outage.

**Separation of duties:** the person granting permissions, the person administering retention/deletion, and the person reviewing audits should not be able to freely delete or alter their own evidence. A system can use policy-as-code, approvals for high-risk changes, a separate audit store, and alerts for anomalous grant changes.

## 12. Access Audit: Auditing Log Access

**Audit of log access** is distinct from **application logs**. Its goal is to answer **who attempted to view, succeeded in viewing, exported, shared, deleted, or changed permissions**, and what the outcome was.

Simulated JSON event example:

```json
{
  "event": "production_log_access",
  "occurred_at": "2026-11-10T04:00:00Z",
  "actor_id": "staff-123",
  "action": "EXPORT_REQUESTED",
  "dataset": "orders-prod-restricted",
  "decision": "DENY",
  "incident_id": "inc-42",
  "auth_method": "SSO_MFA",
  "request_id": "req-911"
}
```

This is **example data**. A real access audit can also include:
- Verified identity and principal type (USER/SERVICE).
- Source/network info per policy.
- Resource scope, classification, and time range.
- Approval/elevation ID and justification.
- Decision and **post-operation outcome** (success/error/cancel).
- Actual count of exported records/bytes when measurable.
- UTC timestamp, event ID, and correlation ID.
- Policy version or rule ID to aid investigation.

**Do not log raw queries containing PII, raw log bodies, bearer tokens, or API keys into the access audit.** A query template, scope, request ID, or safe reference is usually enough; if using hashes/fingerprints, evaluate the risk of content inference.

Audits should be protected against modification/deletion by those being audited, have separate read permissions, and follow policy-based retention. A `logger.info` line sent into the same backend that an admin can delete **does not guarantee immutable or durable auditing**; critical events may require protected append-only storage, policy engine logs, an outbox, or an appropriate managed solution.

### 12.1. Security Alerts on Log Read Permissions

Monitor these signals:
- Creating new API tokens with broad scopes or privileged role grants.
- Reading restricted logs unrelated to an incident/purpose.
- Unusual spikes in bulk exports.
- Repeated DENY decisions or wildcard dataset searches.
- Reading logs from devices/regions disallowed by policy.
- Modifying masking pipelines, retention, or audit policies.
- Collector credentials unexpectedly calling the Search API.
- Break-glass access lacking post-incident review or exceeding its time limit.

**Alerts must not resend raw sensitive data** in email/chat. Use an event code, safe actor ID, scope, severity, and a link to an authenticated system.

## 13. Java Logging and Sensitive Data

Before backend access control comes into play, Java applications must produce logs with **data minimization**.

Unsafe example:

```java
// Anti-pattern snippet; logger and request exist in the application.
logger.debug("request={}", request);
logger.error("Failed to call {}", fullUrlWithToken);
```

This is not standalone runnable code. `request.toString()` or a serializer can put passwords, tokens, cookies, and bodies into events; URLs can contain API keys in query strings. Parameterized logging `{}` **does not automatically redact data**.

Replace with an event schema containing only needed fields:

```java
// SLF4J integration snippet; values are already validated/allowlisted.
logger.info("event=order_completed service={} requestId={} result={}",
        "orders-api", safeRequestId, "SUCCESS");
```

Review:
- Exception `getMessage()`/cause/suppressed, and stack traces containing URLs or SQL credentials.
- MDC/ThreadContext carrying data propagated across threads.
- Structured key-value logging with raw request objects.
- HTTP request/response payload logging, access logs, and SQL parameter logging.
- Console files, collectors, dashboards, notifications, and archives.

Redaction at the encoder/collector is a supplementary layer, **not a substitute for removing secrets at the call site**. When a credential is discovered in production logs, treat it as a security incident: stop further logging, identify sinks/copies, revoke/rotate per policy, restrict access, and investigate.

## 14. Testing Access Control: DENY Must Be Tested

Testing only "the viewer can read" is not enough. Test suites must verify **denial behavior** and indirect access paths.

| Scenario | Action | Expected |
| --- | --- | --- |
| Orders on-call | Search orders STANDARD in prod | ALLOW within scope |
| Orders on-call | Search payments RESTRICTED | DENY |
| Orders on-call | Export all raw prod logs | DENY unless granted |
| Collector | Ingest to allowed index | ALLOW |
| Collector | Search/export that index | DENY |
| Config admin | Edit parser per policy | May ALLOW with approval |
| Config admin | Search RESTRICTED logs | DENY without read grant |
| Security auditor | Read approved dataset | ALLOW with audit |
| Security auditor | Unapproved bulk export | DENY |
| Revoked user | Search with old session/token | DENY per policy and designed TTL |
| Viewer calling API directly | Bypass UI filters | DENY outside scope |
| Viewer using wildcard index | Search other tenants | DENY |
| K8s on-call granted namespace A | `get pods/log` in namespace A | ALLOW |
| Same on-call | `get pods/log` in namespace B | DENY |
| Backend viewer without K8s grant | `kubectl logs` | DENY |
| User without object IAM | Read archive/snapshot | DENY |
| Expired break-glass | Read restricted dataset | DENY |
| User without export permission | Call raw export API | DENY and record access audit |
| Share link | Opened by out-of-scope user | DENY or show only policy-allowed content |

### 14.1. End-to-End Testing

1. Create accounts with **no permissions**, on-call, and restricted-reader in test/staging environments.
2. Generate dummy log data for both classifications; use **fake canaries**, never real credentials.
3. Query from the UI, Search API, raw document endpoint, saved queries, dashboards, exports, and archives.
4. Attempt to modify URLs, index aliases, tenant filters, query wildcards, and API arguments to bypass scope.
5. Test temporary/JIT grants followed by revocation; check sessions, tokens, caches, and shared links.
6. Test `kubectl auth can-i` and node/workload permissions within permitted scope.
7. Test Search/Export outcomes, action limits, field-level masking, quotas, and rate limiting.
8. Confirm audit records from the policy boundary contain actor/action/scope/decision/outcome and no raw logs.
9. Verify alerts/notification channels contain no secrets.
10. Review effective permissions, role drift, and policy-as-code changes via pull requests.

Testing only the UI leaves backend APIs or snapshots open to bypass. Testing only `kubectl auth can-i` leaves cloud IAM or collector paths open to the same data.

## 15. Managing Grant, Use, and Revocation in Operations

A production log access request should state:
- **Who** needs access? Individual or workload identity?
- **Why?** Which incident, duty, or audit/compliance purpose?
- **Where?** Which environment, service, tenant, and dataset/classification?
- **What action?** Read, query, export, ingest, delete, or configure?
- **How long?** Temporary grant, session TTL, and export retention?
- **Who approves and monitors?** Data owner, service owner, or security/on-call per policy.

Grant permissions via IdP/IAM/JIT rather than sharing admin tokens. Periodically review unused permissions, staff transfers, decommissioned collectors, and long-lived grants.

When a user reports "I can't see logs," **do not immediately grant admin**. Check:
- Are they authenticated with the right identity/IdP group?
- Are they viewing the right workspace, tenant, environment, and time window?
- Does the policy scope allow that service/dataset?
- Was the data emitted, did the collector ingest it successfully, and is it within backend retention?
- Does the UI query use the viewer's permissions or a service owner's?
- Do session/cached claims need a refresh after a grant?
- Is the record hidden by field rules or moved to another archive?

When a log viewer account is compromised:
1. Revoke/disable tokens and sessions.
2. Inspect query/export/share/grant logs and the scope accessed.
3. Assess what raw data and credentials may have been exposed.
4. Revoke/rotate real credentials if needed.
5. Contain exported/downstream copies and coordinate with security/privacy.
6. Update MFA, scopes, token TTLs, alerts, and review grants.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Every developer can view all prod logs | Cross-team/tenant data exposure | Team/service-scoped read |
| One admin key shared by collector and dashboard | Collector can read/delete/export | Ingest-only service identity |
| Hiding Export only in the frontend | API can still export | Backend enforcement per action |
| Filtering tenant only in the UI | Requests can be modified | Server-side tenant scoping |
| Config admins can read raw restricted data by default | Violates separation of duties | Separate grants and control indirect paths |
| Broad `pods/log` in shared namespaces | Viewing logs of other teams' workloads | Namespace/role design or central ACL |
| Reviewing only Kubernetes RBAC | Misses backend, node, and archive | Full-pipeline threat model |
| Not auditing searches/exports | Cannot trace data exposure | Protected access audit |
| Using a shared break-glass password | Unknown who accessed data | Personal identity, MFA, expiry, post-review |
| Sharing raw logs in tickets | Duplicates sensitive data | Safe references and restricted storage |
| Masking in dashboard while raw index is open | Data accessible via API | Redact at source, storage/index ACL |
| Leaving snapshots/exports uncontrolled after revocation | Access never truly ends | File/link lifecycle and cloud IAM |
| Deleting access logs to "clean up" | Loss of evidence | Retention/quarantine and approval |
| Assuming every INFO line is public | Logs may contain audit/PII | Classify by content/purpose |
| Forgetting collector modification permissions | Data can be redirected | Change control and config audit |
| Not testing DENY cases | Policy bypasses go undetected | Negative tests and policy regression |

## 17. Exercises

**Q1.** A collector needs to send logs to `orders-prod`. Should we grant the ADMIN role to avoid permission errors?

**No.** Grant `LOG_INGEST` for the exact destination; do not grant search/export/delete/role administration. Test DENY for unrelated actions.

**Q2.** A developer has `get pods/log` in a production namespace containing both orders and payments. Are they guaranteed to see only orders?

**No.** Namespace-level permissions do not automatically restrict by team. Inspect the exact Role/RoleBinding, split namespaces where appropriate, or enforce service-scoped queries in the central backend.

**Q3.** A user has READ permission for restricted logs. Should they automatically be allowed to export 60 days of raw logs?

**No.** Export is a separate action requiring its own permission, scope, limits, audit, approval, and lifecycle.

**Q4.** A pipeline admin is denied `LOG_READ_RESTRICTED`. Can we be sure they cannot obtain restricted logs?

**Not yet.** They might have permission to change collector destinations, create tokens, or read snapshots through other infrastructure. Privilege escalation and indirect access must be controlled.

**Q5.** An employee was removed from a group, but still holds an API token and an exported ZIP file. Is revocation complete?

**Not necessarily.** Check token/session validity, caches, shared links, and remaining exported copies, and handle them per policy.

**Q6.** Why was the security auditor in the demo allowed READ RESTRICTED but DENIED EXPORT RESTRICTED?

**Because** export permission is a separate grant. The `permitted` method requires both the corresponding read permission and `EXPORT_RESTRICTED`; the auditor only has read permission.

**Q7.** An API allows EXPORT, but storage times out. Should we log `EXPORT_COMPLETED result=SUCCESS`?

**No.** Authorization ALLOW and execution outcome are two distinct events. Log success only after proper confirmation.

## 18. Production Checklist

1. Classify logs/datasets/fields by risk; strip passwords, tokens, and unnecessary PII **before the logger is called**.
2. Separate permissions for ingest, read, export, delete, configure, manage-access, retention, and audit-read.
3. Grant permissions by service/team/environment/tenant and purpose, with TTL where appropriate; deny by default.
4. Authenticate via trusted identity; apply MFA/JIT/break-glass and incident approvals per policy.
5. Enforce permissions in the backend/API/storage, not just by hiding buttons or filtering data in the frontend.
6. Audit Kubernetes `pods/log`, `pods/exec`, node filesystems, workload identities, collectors, and cloud storage IAM.
7. Give collectors ingest-only credentials, restrict destinations, rotate, and monitor usage.
8. Give exports/snapshots separate permissions, data limits, file storage controls, TTLs, and outcome audits.
9. Record actor/action/resource/time/decision/outcome in an independently protected access audit store.
10. Review role grants, unused accounts, session/token caches, privilege escalation paths, and policy drift.
11. Test positive **and negative** cases across direct APIs, wildcards, dashboard links, saved queries, and archives.
12. Maintain revocation/incident response runbooks for compromised viewers/tokens or secrets found in logs.
13. Alert on bulk exports, privilege elevations, repeated DENYs, policy changes, or collector credential misuse.
14. Do not assume backend retention covers all backups/exports; manage copies throughout their lifecycle.
15. When on-call cannot view logs, verify identity/scope/query and ingestion before granting broader permissions.

**Conclusion:** Production log access control is a problem of **data + identity + action + scope + duration + audit**, not merely "can you view logs or not." In Java systems, minimize sensitive data at the source; in infrastructure, separate ingest from read, read from export, and configuration from raw data viewing; govern Kubernetes, backends, snapshots, and notifications as one unified chain. A least-privilege policy is only trustworthy once enforced and tested for every case that must **DENY**.
