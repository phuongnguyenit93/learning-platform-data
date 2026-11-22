# Choosing Access Permissions in a Java Logging Strategy

## 1. Why Must Log Access Permissions Be Designed from the Start?

A Java application's logs can contain much more information than a single error line: API paths, IP addresses, authentication traces, order IDs, request IDs, trace IDs, hostnames, stack traces, runtime configurations, and fields that inadvertently carry user data. If an account can read all logs, it can view data outside its responsibilities. If a service that writes logs also has permission to delete them or change retention, a security incident can wipe out the forensic trail.

**Choosing access permissions** means clearly defining: **who** is allowed to **perform which action** on **which type of log**, within **which service/tenant/environment scope**, for **how long**, and **who can audit** that behavior.

Illustrative diagram:

~~~text
payment-service               log collector                 central log store
     |                            |                               |
     | emit stdout                | ingest/forward                | index/retain
     v                            v                               v
 APP_LOG_WRITER             COLLECTOR_WRITER               PROTECTED LOG DATA
                                                                  |
                             +------------------------------------+----------------+
                             |                                    |                |
                        ONCALL_READER                        SECURITY_AUDITOR   CONFIG_ADMIN
                       operational only                     sensitive by scope  manage pipeline
                       own service/env                      approved cases      not implicit read
~~~

A generic role named `admin` should not be treated as the solution. **Least privilege**, **separation of duties**, and **deny by default** are the three foundational principles.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between EMIT, INGEST, READ, SEARCH, EXPORT, CONFIGURE, DELETE, GRANT, and AUDIT_ACCESS permissions.
2. Design RBAC together with ABAC to restrict permissions by role, tenant, service, environment, classification, and time window.
3. Explain why JUL/Logback/Log4j 2 alone do not manage log read permissions in a centralized system.
4. Apply Linux/POSIX file permissions, Windows ACLs, Kubernetes Pod log permissions, and log backend IAM.
5. Know how to use human identity, workload identity, SSO/MFA, JIT access, and break-glass access.
6. Write standalone Java 17 code to test deny-by-default, tenant isolation, and security log restrictions.
7. Protect export permissions, retention, archives, backups, privacy, and audit logs.
8. Build a test matrix for easily overlooked access paths: API, UI, raw files, dashboards, exports, Kubernetes, and cold storage.

## 2. First, Identify Resources and Actions

"Logs" are not a single homogeneous block of data. They may include:

- JVM or Pod stdout/stderr.
- `application.log`, `security.log`, and rotated archives.
- Backend/SIEM log streams, indexes, and datasets.
- Trace/correlation context contained within structured logs.
- Raw payloads, stack traces, HTTP metadata, and sensitive fields.
- Audit trails recording who viewed, exported, or modified logs.
- Disk spools at the collector, backups, and CSV/JSON exports.
- Route, filter, log level, redaction, retention, and alert configurations.

Similarly, users may need to perform many different actions:

| Action | Meaning | What Must Be Restricted |
| --- | --- | --- |
| EMIT | App generates a logging event | Source, schema, and sensitive information |
| INGEST | Agent/backend receives and writes events | Target stream/namespace, no implicit READ |
| READ | View an event or result set | Service, tenant, environment, category |
| SEARCH | Query/filter logs | Same authorization as the underlying data |
| REVEAL_SENSITIVE | View raw fields that were masked | Separate permission, justification, audit |
| EXPORT | Download/copy logs out of the backend | Scope, volume, destination, retention |
| CONFIGURE | Change pipelines, filters, redaction, retention | Change review, audit, separation from READ |
| DELETE | Delete indexes/files/archives | Only via lifecycle/approval policy |
| GRANT | Grant or expand permissions | Controlled identity admin |
| AUDIT_ACCESS | View log access decisions | Not open to every log reader |

**Write permission does not imply read permission. Read permission does not imply export permission. Configuration permission does not automatically include viewing raw security logs.**

A service account used only for ingestion should not be granted search or delete "for convenient debugging." An SRE allowed to view operational logs does not automatically get to view the audit trail of customer account access.

## 3. Classify Data Before Defining Roles

A policy that only states "who can read logs" is too coarse if datasets have different sensitivity levels.

| Log Type | Example Content | Roles to Consider |
| --- | --- | --- |
| Operational | Startup, duration, error code, health | Service on-call/SRE |
| Business/application | Order processing status, correlation ID | Teams responsible per tenant/service |
| Security | Authentication failures, policy decisions | Authorized security responders/auditors |
| Audit | Permission changes, data exports, admin actions | Audit team or authorized delegates |
| Detailed debug/trace | Stack traces, query params, object fields | Only when truly needed, short-lived, with redaction |
| Collector internal | Retries, queue full, transport errors | Logging platform operators |

Each source may need **field classification**, not just dataset classification. A seemingly harmless operational log might contain an access token because code accidentally logged the entire Authorization header. Therefore, **not logging secrets is the top priority**, followed by ACLs, encryption, and masking.

An index containing both normal and sensitive fields may require field-level security or separate datasets. If the backend does not support reliable field restrictions, hiding columns in the dashboard will not stop the API from returning raw data.

### Data Minimization

OWASP recommends protecting log information in storage and access while limiting unnecessary data from being logged. In Java, do not log passwords, session cookies, access tokens, private keys, or raw request bodies just for debugging. Use error codes, event types, safe IDs, and controlled correlation identifiers.

If sensitive data is never logged in the first place, the risk across all log readers, archives, and exported copies is reduced.

## 4. RBAC: Separate Roles by Responsibility

**Role-Based Access Control (RBAC)** assigns a set of actions to a role. The matrix below is a policy template, not built-in role names in Logback or Kubernetes.

| Role | Ingest | Read Operational | Read Security | Export | Config | Delete |
| --- | --- | --- | --- | --- | --- | --- |
| APP_LOG_WRITER | App's own logs only | No | No | No | No | No |
| COLLECTOR_WRITER | Assigned stream only | No | No | No | No | No |
| ONCALL_READER | No | Assigned service/env | Not by default | Only with separate grant | No | No |
| SECURITY_AUDITOR | No | If needed per case | Within approved scope | With approval | No | No |
| LOG_CONFIG_ADMIN | Not by default | Not by default | Not by default | No | Under change control | Not by default |
| RETENTION_OPERATOR | No | Not by default | Not by default | No | Lifecycle policy only | With approval |
| BREAK_GLASS_RESPONDER | Per incident | When needed, within TTL | If approved | Restricted | Restricted | Not by default |

This is a proposed model for discussion. During implementation, it must be translated into the actual permission/action names and resource scopes of the target backend. A well-named role attached to a wildcard resource is still dangerous.

### Do Not Infer Permissions from Job Titles

Someone named "operator" or placed in an "admin" group in a tool might only need to adjust the collection pipeline. If they need to read security logs, they must have a separate permission, justification, and audit trail. Separation of duties limits the blast radius when credentials are compromised.

## 5. ABAC: Scope Determines Which Data Can Be Viewed

**Attribute-Based Access Control (ABAC)** adds attributes of the identity, resource, action, and context.

- **Subject:** authenticated identity, groups, team, tenant grants, MFA status, session validity.
- **Resource:** dataset, service, namespace, environment, `tenant_id`, sensitivity.
- **Action:** read/search/reveal/export/configure/delete.
- **Context:** incident ID, JIT permission, expiration time, access environment, and security policy.

Pseudo-policy:

~~~text
ALLOW READ(event)
  IF authenticated(subject)
 AND hasRole(subject, ONCALL_READER)
 AND event.service in subject.allowedServices
 AND event.environment in subject.allowedEnvironments
 AND event.tenant in subject.allowedTenants
 AND event.classification == OPERATIONAL
 AND requestedFields subsetOf subject.allowedFields

OTHERWISE DENY
~~~

This is a way to describe the contract, **not directly executable IAM syntax**.

A user with `LOG_READER` should not be able to see every tenant; a developer with staging access should not automatically see prod. In a multi-tenant system, the tenant must come from the **authenticated principal and server-controlled resource metadata**, not just from a `tenant_id` parameter that the caller can alter.

### Deny by Default and Fail Closed

If the principal or role is missing, the TTL has expired, the tenant is missing, or the classification is invalid, default to **DENY** or quarantine per policy. Never write a condition that allows access when the role is null.

~~~java
// Anti-pattern, non-standalone and dangerous snippet:
boolean allowed = role == null || role.equals("LOG_READER");
~~~

Missing authentication information must never turn into granted access. The API should distinguish between unauthenticated and unauthorized according to the security framework, and must never return raw logs in error response bodies.

## 6. Complete Java 17 Example: Testing Access Decisions

The following program uses only JDK 17, with no Maven, Spring, IAM backend, or external libraries. It simulates a log viewer that must check **role and tenant before displaying** an event.

Policy in this example:

- `LOG_READER` reads operational logs in the same tenant.
- `SECURITY_AUDITOR` reads security and operational logs in the same tenant.
- `LOG_INGEST` has permission to send/write logs under a different contract, **no read permission**.
- `LOG_CONFIG_ADMIN` only manages configuration, **no read permission** unless explicitly granted.
- No cross-tenant access path exists.
- Every read attempt produces an audit line; only `ALLOW` produces a `VIEW` line.

Actors and events are hardcoded for deterministic stdout. In a real application, identities and tenant grants must come from a trusted authentication/IdP system.

**File: LogAccessDecisionDemo.java**

~~~java
import java.util.Objects;
import java.util.Set;

public final class LogAccessDecisionDemo {
    enum Role {
        LOG_INGEST,
        LOG_READER,
        SECURITY_AUDITOR,
        LOG_CONFIG_ADMIN
    }

    enum Category {
        OPERATIONAL,
        SECURITY
    }

    record Actor(String subject, String tenant, Set<Role> roles) {
        Actor {
            Objects.requireNonNull(subject);
            Objects.requireNonNull(tenant);
            roles = Set.copyOf(Objects.requireNonNull(roles));
        }
    }

    record LogEvent(
            String id,
            String tenant,
            Category category,
            String safeSummary) {

        LogEvent {
            Objects.requireNonNull(id);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(category);
            Objects.requireNonNull(safeSummary);
        }
    }

    static boolean canRead(Actor actor, LogEvent event) {
        if (!actor.tenant().equals(event.tenant())) {
            return false;
        }
        return switch (event.category()) {
            case OPERATIONAL ->
                actor.roles().contains(Role.LOG_READER)
                || actor.roles().contains(Role.SECURITY_AUDITOR);
            case SECURITY ->
                actor.roles().contains(Role.SECURITY_AUDITOR);
        };
    }

    static int attemptRead(Actor actor, LogEvent event) {
        boolean allowed = canRead(actor, event);

        // Audit the decision; do not copy the raw event payload.
        System.out.println(
                "AUDIT subject=" + actor.subject()
                + " log=" + event.id()
                + " decision=" + (allowed ? "ALLOW" : "DENY"));

        if (allowed) {
            System.out.println(
                    "VIEW log=" + event.id()
                    + " summary=" + event.safeSummary());
        }
        return allowed ? 1 : 0;
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", "tenant-a", Set.of(Role.LOG_READER));
        Actor sara = new Actor(
                "sara", "tenant-a", Set.of(Role.SECURITY_AUDITOR));
        Actor service = new Actor(
                "svc-payments", "tenant-a", Set.of(Role.LOG_INGEST));
        Actor ops = new Actor(
                "ops", "tenant-a", Set.of(Role.LOG_CONFIG_ADMIN));

        LogEvent operational = new LogEvent(
                "evt-1", "tenant-a",
                Category.OPERATIONAL, "payment_started");
        LogEvent security = new LogEvent(
                "evt-2", "tenant-a",
                Category.SECURITY, "login_failed_count_1");
        LogEvent otherTenant = new LogEvent(
                "evt-3", "tenant-b",
                Category.OPERATIONAL, "shipment_created");

        int allowed = 0;
        allowed += attemptRead(alice, operational);
        allowed += attemptRead(alice, security);
        allowed += attemptRead(alice, otherTenant);
        allowed += attemptRead(sara, security);
        allowed += attemptRead(service, operational);
        allowed += attemptRead(ops, operational);

        System.out.println(
                "SUMMARY allowed=" + allowed
                + " denied=" + (6 - allowed));
    }
}
~~~

**Compile and run with JDK 17 or later:**

~~~bash
javac -encoding UTF-8 LogAccessDecisionDemo.java
java LogAccessDecisionDemo
~~~

**Exact stdout:**

~~~text
AUDIT subject=alice log=evt-1 decision=ALLOW
VIEW log=evt-1 summary=payment_started
AUDIT subject=alice log=evt-2 decision=DENY
AUDIT subject=alice log=evt-3 decision=DENY
AUDIT subject=sara log=evt-2 decision=ALLOW
VIEW log=evt-2 summary=login_failed_count_1
AUDIT subject=svc-payments log=evt-1 decision=DENY
AUDIT subject=ops log=evt-1 decision=DENY
SUMMARY allowed=2 denied=4
~~~

### Result Analysis

1. Alice has `LOG_READER` on `tenant-a`, so she can read operational log `evt-1`.
2. Alice does not have `SECURITY_AUDITOR`, so she cannot read security log `evt-2` even in the same tenant.
3. Alice cannot view `evt-3` in `tenant-b`, even though its category is `OPERATIONAL`.
4. Sara has `SECURITY_AUDITOR` on `tenant-a`, so she can read security log `evt-2`.
5. Service `svc-payments` only has the ingest role, so `READ` is denied.
6. Ops has the configuration admin role, which does not grant `READ` by default.
7. There are two `ALLOW` decisions and four `DENY` decisions. Only `ALLOW` prints `VIEW`.
8. No clock, threads, or network are used, so output does not depend on scheduling.

### Limitations of the Demo

This is only an **authorization model** with identities created in code; there is no authentication, JWT validation, session management, database, or real log backend. In production, you must validate the principal on the server, verify the event's tenant, enforce scope across every API, protect the audit sink, and avoid printing raw sensitive content into the audit log.

- `Set.copyOf` protects the record's role set from in-place mutation; it does not replace role provisioning/revocation via an IdP.
- `canRead` only governs `READ`. `EXPORT`, `DELETE`, `CONFIGURE`, and `GRANT` must have their own methods/policies.
- Never take `actor.tenant` or `event.tenant` from unauthenticated client query parameters or headers.
- Never use a correlation ID or event ID as a credential.
- Printing audit lines to stdout is only for observation in the demo; a real system's audit log needs an independent sink with controlled read/delete permissions.
- If an actor ID or event ID comes from external input, validate/escape it before writing to text logs to prevent log injection.
- A boolean check in Java does not stop users from querying the backend directly with an overly broad token; restrict service credentials and backend IAM.

## 7. Java Logging APIs Do Not Solve IAM on Their Own

JUL, SLF4J/Logback, Log4j 2, and Spring Boot logging primarily decide **whether to emit an event, its level/filter, format, and write destination**.

| Component | What It Controls | What Must Not Be Inferred |
| --- | --- | --- |
| JUL Logger/Handler | Level, filter, FileHandler, ConsoleHandler | Read permissions for all log copies |
| Logback FileAppender | File path, encoder, rolling behavior | Dashboard/central SIEM access permissions |
| Log4j 2 Appender | Destination, filters, layouts, async | API query tenant isolation |
| Spring Boot logging | Bootstrapping backend, config file/console | Log storage IAM |
| OS filesystem ACL | Who can read/write files on the host | Query permissions for hot indexes/other archives |
| Kubernetes RBAC | API permissions such as Pod logs/namespace | Field-level redaction/tenant filtering |
| Central log backend IAM | Product-specific search/export/index privileges | Preventing the app from logging secrets before ingest |

In Java 17, `java.util.logging.FileHandler` writes files according to the process's filesystem capabilities. It does not provide a built-in `SECURITY_AUDITOR` role for file readers. Once files are shipped to a collector/backend, permissions at the backend form a separate authorization layer.

### Log Ingestion Must Be Protected Separately

A service account with `INGEST` permission should only write to its scoped stream/dataset and should not have search or delete by default. If stolen, an ingest token could be used to spam or forge events; source authentication, rate limits/quotas, schema validation, and alerts are needed. Narrow write permissions do not solve every risk, but they reduce the impact.

## 8. File and Directory Permissions on Linux/POSIX

If Java writes local files, you must restrict permissions on **directories, files, archives, and the rotation process**.

A desired state:

~~~text
/var/log/myapp/                   owner=appsvc group=logreaders mode=0750
/var/log/myapp/application.log    owner=appsvc group=logreaders mode=0640
~~~

- Directory `0750`: owner has `rwx`, group has `r-x`, others have no permissions. The group needs execute/traverse to open files.
- File `0640`: owner has `rw`, group has `r`, others have no permissions.
- An agent that needs to tail the file can belong to the group or use an appropriate ACL; it does not need to run as root.
- Parent directories must also allow traversal according to policy.
- `umask`, default ACLs, FileHandler/appender creation mode, and `logrotate` can change modes after a restart.
- During rotation, newly created files and archives must also have their permissions checked, not just the active file.
- On Windows, use NTFS ACLs and service identities; POSIX-style `chmod` is not a general-purpose permission tool.

**Metadata read-only** commands on Linux:

~~~bash
namei -l /var/log/myapp/application.log
stat -c '%U %G %a %n' /var/log/myapp /var/log/myapp/application.log
getfacl /var/log/myapp/application.log
~~~

Commands depend on the environment; `getfacl` may require a separate package.

### 0640 Does Not Mean Append-Only

An owner with write permission on a file can modify its contents; someone with write permission on the directory can rename or delete the file under POSIX semantics. Root or users with high-level infrastructure privileges can bypass normal ACLs. Therefore, `0640` is only **basic access control**, not a tamper-evident guarantee.

If you need to prevent a compromised application from erasing evidence, prefer shipping logs to a backend where the app only has ingest permission, with immutable/tamper-evident retention when required. If using a hash chain, the baseline/keys must be protected independently; a hash stored in the same file where an attacker can edit the entire file does not prove integrity on its own.

### Do Not Store Logs in the Web Root

Log files should not reside in directories serving static assets or have public URLs. A file download endpoint where the user controls the path can lead to path traversal. If a log viewer is needed, it must authenticate, authorize, audit, redact, and only read from restricted sources or queries.

## 9. Kubernetes: Reading Pod Logs via pods/log

In Kubernetes, Pod logs are accessed through the **pods/log** API subresource. RBAC allows granting the `get` verb on this subresource within a namespace.

**Example Role/RoleBinding granting only `get pods/log` in the `payments` namespace:**

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payments-pod-log-reader
  namespace: payments
rules:
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payments-pod-log-readers
  namespace: payments
subjects:
  - kind: Group
    name: sre-payments
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: payments-pod-log-reader
  apiGroup: rbac.authorization.k8s.io
~~~

The `sre-payments` group must be authenticated and mapped by the identity provider in reality; YAML does not create groups. Apply only to authorized clusters/namespaces with change review.

**Understand the limits accurately:**

- The rule above grants `get` on `pods/log`; it does not grant `secrets`, `pods/exec`, `pods/delete`, or `cluster-admin`.
- If users need to list Pod names before viewing logs, you may need to grant `get`/`list` on `pods` after review. Do not grant wildcards just to make `kubectl logs` convenient.
- A namespaced `RoleBinding` does not grant permissions in other namespaces. However, a person may hold multiple Roles or ClusterRoleBindings simultaneously, so inspect **effective aggregate permissions**.
- Kubernetes RBAC controls API requests by Pod/namespace; it **does not filter individual lines or sensitive fields inside Pod logs**.
- If a single Pod handles multiple tenants, granting `pods/log` can expose logs of all tenants in that Pod. Tenant-scoped users should query a backend with real scope/field filtering rather than viewing raw Pod logs.
- Someone with `pods/exec`, `hostPath`/node access, or a central log backend token can read logs through another path. Every path must be controlled.
- Node/runtime log rotation and collector retention are separate from API permissions.

Example checks for the current identity:

~~~bash
kubectl auth can-i get pods/log -n payments
kubectl auth can-i get secrets -n payments
kubectl auth can-i create pods/exec -n payments
~~~

Results will be `yes`/`no` based on all active grants, not just the Role above. Do not use unauthorized impersonation.

### Log Collector Service Account

If an agent runs as a DaemonSet and reads host log files, it may need sensitive node mounts/permissions. Avoid granting `cluster-admin` by default; evaluate `hostPath`, pod security, file ACLs, namespace, and runtime identity. The collector needs permission to read logs on the node and ingest into the backend; **it does not need backend delete/modify or search permissions by default**.

## 10. Log Backend/SIEM IAM

Once logs are centralized, the backend is where read/search/export must actually be enforced. An example policy:

~~~text
payments-ingester service:
  ALLOW ingest -> payments-prod-operational
  DENY search/export/delete/configure

payments-oncall:
  ALLOW search/read -> payments-prod-operational (redacted)
  DENY security-raw, other-tenant datasets, delete
  EXPORT only with additional grant

security-incident-reader:
  ALLOW read designated security datasets
        within approved case/tenant/time window
  DENY changing retention

logging-platform-operator:
  ALLOW manage pipeline, schema, routing
  DENY raw sensitive read unless separately granted

retention-operator:
  ALLOW policy-governed lifecycle tasks
  DENY ad-hoc purge without approvals
~~~

This is a pseudo-policy, not vendor-specific IAM syntax. When implementing, use the actual action names, resource patterns, and conditions supported by the product.

### Mandatory Questions

- Does the backend support resource/index ACLs, or only a global admin account?
- Is there document-level/row-level security for multi-tenancy?
- Is there field-level access or server-side data masking?
- Do the search API and bulk export API enforce the same policy?
- Under whose identity do saved dashboards/alerts run? Can cached results be viewed by others?
- Do cold archives, object storage, and backups use different ACLs?
- Was the ingest token accidentally granted delete or read permissions?
- Is there a separate API to change retention or disable ingestion?
- Are TTLs/token rotation and the audit logs of these permissions themselves managed?

A dashboard hiding sensitive columns is not enough if users can call the backend API directly. You need a security boundary on the server/backend and service credentials narrow enough to limit damage even if the API is exploited.

## 11. Export Permission Is Different from Read Permission

Exporting creates a new copy: CSV, JSON, object storage, email attachment, or an analytics system. That copy may no longer be governed by the original retention/ACL.

Before granting `EXPORT`, you need:

1. A separate permission distinct from `READ`.
2. Defined scope for tenant, service, environment, classification, and time range.
3. Field masking/redaction enforced in the **export path**, not just the UI.
4. Size/rate limits and alerts for anomalous bulk exports.
5. Approved destinations, encryption, and ACLs for exported files.
6. A TTL and deletion process for exported files once the purpose ends.
7. Audit logging of who exported, when, what scope, how many records/bytes, and why.
8. For sensitive data, potential requirements for approval/MFA/incident ID.
9. Evaluation of saved reports, scheduled exports, and email notifications as well.

Someone who can read 10 lines of operational logs does not automatically need permission to download an entire month of security logs. Likewise, having a Download button in the UI does not prove permissions are checked at the API.

## 12. Identity Authentication: Humans and Machines Must Be Separate

### Human Access

- SSO/IdP with individual identities; never use shared admin accounts.
- MFA when viewing sensitive data or elevating privileges.
- Group-based grants paired with scope and expiry/JIT.
- Time-bound permissions tied to on-call shifts/incidents.
- Revoke access when a user changes teams, leaves, or is no longer on call.
- Audit read/export sessions and permission changes.
- Review grants periodically to prevent privilege creep.

### Service/Workload Identity

- Each app/collector has a dedicated identity or token.
- An ingest token only needs to write to its assigned stream, not query or delete.
- Never store tokens in code, log payloads, or container images.
- Use workload identity/secret managers, with rotation and short TTLs where possible.
- Use TLS for transport, verifying certificates and hostnames.
- When ingest permission fails, emit an error metric/alert through an independent channel; do not log raw credentials.
- Do not reuse one token across all environments if they can be separated.

An API client passing `request_id`, `correlation_id`, or `trace_id` in a request **does not prove identity**. Never use those IDs as access tokens.

## 13. Break-Glass for Emergency Investigation

During a severe incident, an on-call responder may need to read sensitive data beyond their normal permissions. Break-glass should be **controlled temporary access**, not permanent superadmin.

Illustrative workflow:

1. Authenticate the responder with MFA.
2. Attach an incident/ticket ID and justification.
3. Select only the necessary dataset, tenant, environment, and time range.
4. Grant JIT access with a short TTL and automatic revocation.
5. Alert when emergency access is activated.
6. Audit `READ`, `SEARCH`, `EXPORT`, `CONFIGURE`, and `DENY` during that window.
7. Review after the incident and confirm grants have expired.
8. Manage any exported copies according to retention and privacy policies.

If the break-glass mechanism depends entirely on an IdP or network that could fail during the incident itself, there must be a pre-approved and pre-tested recovery plan.

## 14. Audit Every Privileged Operation on Logs

Log readers must also have their access recorded, especially when viewing security logs, exporting, modifying permissions, or reducing retention.

**Example structured access audit:**

~~~json
{
  "event_type": "LOG_ACCESS_DECISION",
  "subject_id": "alice",
  "action": "READ",
  "resource_kind": "log_dataset",
  "resource_id": "payments-prod-operational",
  "requested_tenant_scope": "tenant-b",
  "decision": "DENY",
  "reason_code": "SCOPE_MISMATCH",
  "request_id": "audit-request-42"
}
~~~

This is a suggested schema, not a default format of JUL, Spring, or any SIEM.

**What to log:** authenticated subject, action, resource, approved/requested scope, decision, safe reason code, timestamp, session/request ID, policy version, and incident ID if applicable.

**What not to log:** the raw logs the user just viewed, tokens/cookies, full unredacted queries, passwords, or exported payloads. The audit log must not itself create another sensitive copy.

**Protect the audit sink:** someone with permission to view operational logs or change routine configurations should not be able to easily delete the audit trail of those very activities. Separate storage/retention or immutable controls may be needed. If using hash/tamper-evident mechanisms, baselines/keys must be protected independently.

### Why Logging Only DENY Is Not Enough

An actor with `READ` permission can abuse it to query millions of records. Recording `ALLOW` events and retrieval volume helps detect anomalies. Viewer access logs also need retention and privacy management, rather than being kept indefinitely.

## 15. Java Web/API Viewer: Enforce on the Server, Not on the Button

A log viewer architecture:

~~~text
Browser
   |
   v
Identity provider -> authenticated principal
   |
   v
API Gateway / Spring Security
   |
   v
Policy check (action + role + scopes)
   |
   v
Query backend with enforced dataset/tenant filter
   |
   v
Mask fields / limit pagination
   |
   v
Response + independent access audit
~~~

Hiding the Export button on the frontend does not replace checking permissions at `POST /logs/export`. Read the allowed tenant list from the authenticated principal/policy service; never trust client-supplied tenant parameters.

Pseudo-example:

~~~text
principal:
  subject=alice
  roles=[LOG_READER]
  allowed_tenants=[tenant-a]
  environments=[staging]

request:
  GET /logs?tenant=tenant-b&env=prod

policy:
  DENY
  never trust query params as authorization grants
  do not return log content in error response
  audit decision and safe reason code
~~~

In Spring Security, an annotation checking `hasAuthority` can be the first layer, but data fetched from the repository/search backend must still enforce tenant/environment/dataset scope. If the backend query token has wildcard access, a single API bug can leak another tenant's logs; use defense in depth.

## 16. Scoping by Tenant, Environment, and Time

`READ` permission should have clear boundaries:

| Scope | Example | Mistake to Avoid |
| --- | --- | --- |
| Tenant | `tenant-a` only | Trusting `tenant_id` sent by the client |
| Service | `payments` only | Allowing access to all cluster indexes |
| Environment | Separate staging/prod | Dev role reading prod by default |
| Classification | operational/security | Using one shared unmasked raw index |
| Time range | Incident window | Querying full history unnecessarily |
| Fields | `status` and `error_code` | Exporting raw payload when UI only hides columns |
| Data volume | Page/query limit | Unthrottled bulk downloads |
| Session | 30-minute JIT access | Failing to revoke when the incident ends |

If a Pod handles multiple tenants and writes to shared stdout, Kubernetes `pods/log` RBAC does not provide field-level tenant filtering. Tenant-scoped users should access a backend/API with real isolation, or the system should separate datasets/workloads appropriately.

Note that data may remain in backups, cold archives, or disk spools longer than in dashboards. Permissions on the hot index do not automatically govern those locations.

## 17. Log Deletion, Retention Changes, and Integrity

At minimum, separate:

- `WRITE`/`INGEST` to add events.
- `READ`/`SEARCH` to query.
- `EXPORT` to create copies.
- `CONFIGURE` to change routes/schemas/redaction/retention.
- `DELETE` to remove data.
- `GRANT` to assign permissions.
- `AUDIT_ACCESS` to view access decisions.

A config admin could lower retention from 90 days to 1 day and cause massive log deletion without ever calling `DELETE` directly. Therefore, `CONFIGURE` is also a sensitive permission that requires review/approval and auditing.

When strong integrity is required, consider append-only ingestion, immutable/WORM archives, or tamper-evident logs, along with key/manifest protection and policy-governed data destruction. Simply using `chmod 0444` or file hashes is insufficient against an attacker with root access or permission to alter the baseline.

## 18. Process for Choosing Permissions in a Java Project

### Step 1: Inventory

List application services, log categories, stdout/files, collectors, indexes, archives, backups, exports, and the owner of each source.

### Step 2: Classify

Assess privacy/security/audit levels. Strip secrets and unnecessary data right at the code/encoder level; define redaction and retention.

### Step 3: Build Roles

Separate writer, collector writer, operational reader, security auditor, config admin, retention operator, and break-glass responder. Do not bundle `READ` + `EXPORT` + `DELETE` into a default "admin" role.

### Step 4: Attach Scopes

Service, namespace, tenant, env, classification, time, and fields. Determine where each policy is enforced.

### Step 5: Apply Identity

Humans via IdP/SSO/MFA; machines via workload/service identity and narrow tokens. Enable time-bound access where appropriate.

### Step 6: Enforce on Every Path

OS files, Kubernetes API, backend query API, dashboards, scheduled exports, archives, backups, and spools.

### Step 7: Audit and Test

Log privileged actions and grant changes. Test both positive and negative cases, cross-tenant access, expired grants, API bypasses, raw files, and bulk exports. Review permissions periodically.

## 19. Policy Test Matrix

| Test | Identity/Action | Expected |
| --- | --- | --- |
| Operational log same tenant | Alice `LOG_READER` `tenant-a` `READ` `evt-1` | ALLOW |
| Security log same tenant | Alice `READ` `evt-2` | DENY |
| Operational different tenant | Alice `READ` `tenant-b` `evt-3` | DENY |
| Security auditor right tenant | Sara `READ` `evt-2` | ALLOW |
| Ingest-only service tries to read | `svc-payments` `READ` `evt-1` | DENY |
| Config admin tries to read | `ops` `READ` `evt-1` | DENY |
| Unauthenticated | Anonymous `READ` | DENY |
| Missing role/tenant scope | Unknown principal `READ` | DENY |
| JIT time expired | Expired grant `READ` | DENY |
| Reader calls export | Alice `EXPORT` | DENY unless separately granted |
| Dev reads prod | Staging-only user `READ` prod | DENY |
| Reader changes retention | `ONCALL_READER` `CONFIGURE` | DENY |
| Service deletes logs | `APP_LOG_WRITER` `DELETE` | DENY |
| Export API bypasses UI | No `EXPORT` grant invokes API | DENY |
| Spoofed tenant header | Caller claims `tenant-b` | Does not expand grant |
| Kubernetes Pod logs | Role `get pods/log` right namespace | ALLOW per RBAC |
| Kubernetes secret | Role only has `pods/log` | Not granted by that Role |
| Bulk query via backend | Unauthorized dataset | DENY |
| Cold archive | No archive grant | DENY |
| Break-glass TTL expired | Expired role | DENY |
| Authorized export | `EXPORT` grant, right scope, destination | ALLOW and audit |

**Testing denied cases:** no raw content in response, appropriate status code, audit recorded, no stack traces or other-tenant details leaked. **Testing allowed cases:** returned data includes only the allowed tenant/service/fields and respects query limits.

For Java policies, you can write JUnit 5 parameterized tests for combinations of role × category × tenant. Then you need integration tests with real auth middleware and the log backend; a `canRead` unit test cannot detect that a backend API token has wildcard permissions.

## 20. Common Mistakes

1. **Anyone operating servers can view all logs.** On-call engineers need investigation access, not default access to raw PII/security logs across all tenants.
2. **The writer is also a reader.** A compromised ingest credential can both forge events and read data if over-privileged.
3. **Config admin equals data admin.** Separate roles and audit policy changes.
4. **Only hiding the Export button.** The export API must still authorize requests.
5. **Relying only on `chmod 0640`.** What about parent directories, rotation, root, backend, and archives?
6. **Trusting client-supplied tenant directly.** Derive it from the principal and trusted metadata.
7. **Using Kubernetes RBAC as a field filter.** `pods/log` is a subresource; it does not filter fields or tenants.
8. **Securing the hot index while forgetting archives/backups.** Cold storage can be a bypass path.
9. **Access audit logs printing full raw queries/results.** Creates unnecessary sensitive copies.
10. **Shared admin accounts.** No clear attribution, hard to revoke per person.
11. **JIT permissions that never expire.** Can turn into permanent privileged access.
12. **Long-lived tokens committed to repos/logs.** Can be leaked and used to query the backend.
13. **Thinking encryption is enough.** Encryption does not replace authorization, scoping, or auditing.
14. **Testing everything with an admin token.** Fails to verify least privilege and deny cases.
15. **Unaudited retention changes.** Can indirectly destroy evidence.
16. **Never testing break-glass.** During an incident, it might not work or might fail to revoke.

## 21. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| User with right role cannot view logs | Wrong tenant/service/env scope | Auth principal and policy grants |
| User sees another tenant's logs | Filtering only in UI | Backend query/API authorization |
| Writer can delete indexes | Wildcard token | Service IAM actions/resources |
| Export exposes masked fields | Masking only in frontend | Server/export path and field security |
| Pod logs readable but SIEM denied | Kubernetes RBAC differs from backend IAM | Two separate identity/permission planes |
| RoleBinding does not work | IdP group unmapped, wrong namespace | Kubernetes authn and `roleRef` |
| New file unreadable by agent | Umask/default ACL/logrotate | Owner/group/mode and parent dirs |
| Audit log deleted with operational log | Shared delete rights | Separate storage/retention/admin |
| Dev can read prod | Wildcard env grants | Review role inheritance |
| JIT role persists forever | Missing TTL/revocation | Identity lifecycle |
| Shared dashboard leaks data | Saved query runs as admin | Run-as identity, cache, API |
| Log viewer returns 500 with raw stack trace | Improper error handling | Safe error response and access audit |

Investigation workflow: identify identity → action → resource/scope → policy version → backend grant → raw file/API bypass → access audit → fix to least privilege → re-test.

## 22. Practice Exercises

**Exercise 1 – Separate READ and EXPORT.** Add an `Action` enum with `READ`/`EXPORT`/`DELETE`/`CONFIGURE` to the demo. Only grant `EXPORT` with a separate permission. Write expected `ALLOW`/`DENY` outcomes and audits.

**Exercise 2 – Environment Control.** Add `environment` to `Actor`/`LogEvent`. A `tenant-a` user with only `staging` access must not view `prod`, even if the query specifies a valid tenant.

**Exercise 3 – Linux ACL.** In a sandbox, create a `0750` directory and `0640` file; test owner, reader group, and a user outside the group. Test rotation and verify the new file's permissions. Do not modify production directories.

**Exercise 4 – Kubernetes RBAC.** Apply the sample `Role`/`RoleBinding` in a test cluster with a mapped group. Verify `get pods/log` in the right namespace and confirm `secrets` or `exec` are not granted by that role.

**Exercise 5 – Export Policy.** Design an export endpoint with a separate permission, field redaction, byte limit, TTL for exported files, and auditing. Test calling the API directly without the UI button.

**Exercise 6 – Break-Glass.** Grant temporary 30-minute security read access in a test policy engine; attach an incident ID, MFA, alert, read/deny logging, and automatic revocation after TTL.

**Exercise 7 – Multi-Tenant.** Create log records for `tenant-a` and `tenant-b` in the same dataset. Using two test identities, ensure the backend query returns only authorized data rather than filtering only in the frontend.

**Exercise 8 – Access Audit.** Record an access event for `READ`/`EXPORT`/`DENY` without copying the raw log message into the audit. Test that an identity with operational `READ` cannot delete the audit trail.

**Exercise 9 – Read Path Inventory.** Trace the same event across stdout, Pod logs, node files, collector spool, SIEM, backups, dashboards, and exports. Ensure an unauthorized actor cannot bypass via any path.

## 23. Implementation Checklist

- [ ] Inventory of sources, files, streams, archives, backups, and exports exists.
- [ ] Every dataset has an owner, classification, and retention policy.
- [ ] Rules exist to exclude passwords/tokens/secrets at the source.
- [ ] `APP_LOG_WRITER`/`COLLECTOR_WRITER` roles do not have `READ` by default.
- [ ] `READ`/`SEARCH`, `EXPORT`, `CONFIGURE`, `DELETE`, and `GRANT` are separated.
- [ ] Tenant/service/environment scope is enforced on the server/backend.
- [ ] Field masking or dataset separation is in place when the backend lacks field-level security.
- [ ] SSO/MFA for humans, dedicated workload identities for machines.
- [ ] JIT/break-glass has TTL, approval, alerting, and revocation.
- [ ] File permissions, rotated archives, and parent directories are verified.
- [ ] Kubernetes `pods/log`, `exec`, and `secrets` permissions are reviewed independently.
- [ ] Backend IAM applies to UI, API, saved queries, exports, and cold storage.
- [ ] Privileged `READ`/`EXPORT`/`CONFIGURE`/`DELETE`/`GRANT` actions have access audits.
- [ ] Access audits have separate retention/ACLs and appropriate integrity protection.
- [ ] Positive, denied, cross-tenant, expired grant, and API bypass cases are tested.
- [ ] Grants and token rotations are reviewed periodically, removing unneeded permissions.

## 24. Summary

**Choosing access permissions is part of designing a Java logging strategy.** Separate emit/ingest, read/search, sensitive data reveal, export, configuration, deletion, and permission-granting rights. Use RBAC for role separation and ABAC to constrain tenant/service/environment/fields/time. **Deny by default** whenever grant evidence is insufficient.

The logger API and appender are only one layer; permissions must be controlled across OS files/ACLs, Kubernetes Pod logs, collectors, SIEM/log backends, and APIs/exports/archives. Never expand production log read access for convenience, never use correlation IDs as credentials, and never treat data encryption as a substitute for authorization.

For logs to retain investigative value, avoid logging secrets from the start, protect audit integrity, issue time-bound emergency access, monitor all sensitive access, and test every path that can view or extract logs from the system.

### References

- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Kubernetes RBAC Authorization: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes RBAC Good Practices: https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- Kubernetes kubectl logs: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Oracle Java 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java 17 PosixFilePermissions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- NIST SP 800-92 Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 Manual: https://logging.apache.org/log4j/2.x/manual/
- Spring Security Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
