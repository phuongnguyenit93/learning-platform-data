# Log Read Permissions in Java: Data Protection, Access Control, and Access Auditing

## 1. Objectives

**Log read permissions** govern the right to view or retrieve events recorded by applications and infrastructure. In a Java system, logs can appear in the console, files, container runtimes, centralized collection systems, dashboards, analytics tools, long-term archives, and forensic copies.

Logs are useful for debugging and incident detection, but **they are not public data**. A seemingly simple record can expose user IDs, IP addresses, request payloads, internal service names, trace IDs, partner names, system paths, transaction details, or accidentally logged secrets. Therefore, reading logs must be controlled according to the actual sensitivity of the log data, not merely treated as viewing a text file.

After this lesson, you will:

1. Distinguish between permissions to **view, query, download/export, share, and administer/delete logs**.
2. Understand the principles of **least privilege**, RBAC, ABAC, tenant/environment scoping, time-bound access grants, and emergency break-glass mechanisms.
3. Know the enforcement points to protect in Java applications, filesystems, Kubernetes, and centralized logging systems.
4. Practice a **standalone Java 17** example of read access control by role, tenant, and sensitivity; understand the limitations of this simulation.
5. Design access auditing, detect anomalous read behavior, and establish a workflow for handling requests to view logs containing sensitive data.
6. Write negative access-control tests so logs do not leak through APIs, exports, backups, or dashboards.

## 2. Why Do Log Read Permissions Relate to Privacy?

A log can contain someone else's information even when the developer logging it did not intend to include it. For example:

~~~text
2026-11-10T02:14:32Z WARN order-service payment verification failed
userId=u-4821 tenant=tenant-a requestId=req-17
~~~

The hypothetical record above already contains an **identifier linkable to an account** and a tenant name. If logs also record emails, tokens, cookies, request bodies, or health information, the consequences of unauthorized reading can be far more severe.

Someone with permission to view logs for a namespace or organization could:

- View information belonging to other users, customers, or tenants.
- Learn internal architecture, APIs, paths, hostnames, and activity timing.
- Harvest accidentally logged tokens/credentials to escalate unauthorized access.
- Export large volumes of records to personal devices or unapproved services.
- Read security incident logs while an investigation still requires need-to-know restrictions.
- Correlate multiple individual records to infer user activity or identity.

**First line of defense:** do not log secrets or unnecessary personal data. **Second principle:** even with redaction in place, read permissions must still be managed. Redaction and access control are two complementary defense layers, not substitutes for each other.

In a centralized logging system, **permission to read a single line** can carry far less risk than **permission to query 90 days of all data**. Both are called "read", yet their scale, scope, and exfiltration potential are vastly different.

## 3. Distinguishing Types of Log Permissions

| Action | Meaning | Risks and Requirements |
| --- | --- | --- |
| **View** | View a scoped page of logs. | On-screen data exposure, screenshots, copying. |
| **Search / Query** | Search and filter by fields and time range. | Can expand scope to millions of records; requires backend scope enforcement. |
| **Download / Export** | Generate CSV/JSON/ZIP files or data for external analysis. | Easy to duplicate data, bypass retention, or redistribute; requires separate permission and audit. |
| **Share** | Grant access, share links, or forward results to others. | Exceeds the authorized audience; public links can lose control. |
| **Stream / Follow** | Continuously watch logs in real time. | Can capture newly arriving sensitive data without re-querying. |
| **Configure** | Change log levels, appenders, pipelines, masking, or retention. | Can cause logs to capture more data or route to another destination. |
| **Delete / Modify** | Delete, alter, or adjust record lifecycle. | Impacts investigations, integrity, and retention obligations. |
| **Manage access** | Grant, revoke, or delegate permissions. | Can indirectly open access to all data; requires strict controls. |

**Read-only does not mean harmless.** Someone with only read access can still copy, screenshot, or export data if the system allows it. Policies must account for both **scope** and **data exfiltration channels**.

A sound design separates the technical permissions **READ**, **EXPORT**, **DELETE**, and **MANAGE_ACCESS** rather than using a single catch-all "log administrator" role. It is also important to separate permission to view **masked logs** from permission to view **raw logs**.

## 4. The Principle of Least Privilege

**Least privilege** means an identity has only the capabilities necessary to complete its assigned task, within the required scope and duration.

A log access request should be able to answer:

- **Who?** The authenticated user or service account identity.
- **What action?** View, query, follow, or export?
- **Which data?** Service, environment, tenant, namespace, sensitivity, and time window.
- **Why?** Ticket investigation, routine operations, security, or audit.
- **For how long?** Standing access or temporary access until a specific expiration?
- **Who approved it?** Data owner or an organization-authorized mechanism.
- **Who knows about the access?** Is there an audit trail and monitoring signal?

For example, a customer support engineer may need to view masked logs for **a single tenant**, without needing to see raw authentication headers across all tenants. An SRE may need to diagnose infrastructure errors without having blanket permission to export personal data. A security team may need elevated access during an investigation, but that does not mean they automatically get to delete logs or grant permissions to themselves.

### 4.1. Reference Permission Matrix

This is an **illustrative policy**, not a built-in default of Java or any specific platform:

| Role | Masked Operational Logs | Detailed Internal Logs | Controlled Sensitive Logs | Export | Access Administration |
| --- | --- | --- | --- | --- | --- |
| **Support** | Read by assigned tenant/ticket | No | No | Not by default | No |
| **Developer** | Read dev/test and temporarily granted production scope | Yes in permitted environments | Not by default | With approval | No |
| **SRE** | Read responsible service/environment | Read as needed for duties | Requires additional workflow | Separate export permission | Not by default |
| **Security investigator** | Scoped to the incident | Scoped to the incident | Only when approved | Controlled/ticketed | Not by default |
| **Platform administrator** | Scoped to admin duties | No automatic access to tenant data | Not by default | Not by default | Administers mechanisms, with separation of duties |
| **Service account / log shipper** | Typically **write/forward only**, no query read needed | Not applicable | Not applicable | No | No |

If an organization has different security constraints, the matrix must be adjusted according to data classification, contracts, internal policies, and applicable laws. Do not treat a job title label as sufficient proof to grant blanket access.

### 4.2. Multi-Dimensional Access Scope

A proper READ decision must evaluate **multiple conditions simultaneously**:

~~~text
allow =
    authenticated_identity
    AND authorized_action
    AND permitted_service
    AND permitted_environment
    AND permitted_tenant
    AND permitted_classification
    AND permitted_time_window
    AND approval_valid_if_required
~~~

This is a logical model, not framework syntax. The key point is **do not check only the role**. A SECURITY role in tenant A must not automatically grant access to tenant B's logs without explicit authorization.

Someone with read access in dev does not automatically have read access in production. A token with query permission does not automatically have export permission. Every request must be re-validated on the backend.

## 5. Authentication, Authorization, and Audit: Three Distinct Concerns

- **Authentication:** verifies who is accessing, typically via SSO/OIDC, service identity, mTLS, or an appropriate mechanism.
- **Authorization:** determines whether that identity is permitted to perform a specific action on specific logs.
- **Auditing:** records who requested what permission, on which target/scope, when, and the allow/deny outcome.

A dashboard with a "Hide sensitive logs" toggle is only UI. **Authorization must be enforced at the query service or storage API**, not merely by hiding buttons on the frontend. If the API still returns raw data, a user can call the API directly.

Never trust `userId`, `role`, or `tenant` parameters sent from a browser as the basis for granting access. The backend must extract the principal from a verified token/session and validate token issuer, audience, expiry, scope, and permissions against secure configuration.

### 5.1. Fail Closed, Never "Bypass Checks on Error"

When authentication fails, policy cannot be retrieved, tenant cannot be determined, or required approval data is missing, the default must be **DENY**. Never use a fallback like "If the policy server times out, allow temporary read" for raw logs containing sensitive information.

Deny responses should not leak record contents, raw tokens, other usernames, or whether an unauthorized tenant exists or not. The backend still needs to record internal audit details sufficient for investigation.

### 5.2. Time-Bound Access and Break-Glass

A **just-in-time access** workflow can require:

1. The requester specifies the ticket/issue, service, tenant, environment, and data type.
2. The system or an authorized approver grants approval.
3. Narrowly scoped access is granted for a predefined duration.
4. All queries and exports are audited against the policy.
5. Access is automatically revoked upon expiration, task completion, or policy violation detection.

**Break-glass** is emergency access, not a default role for bypassing RBAC. It must have activation conditions, a time limit, a documented reason, alerting, and post-incident review. Never create shared accounts that cannot be traced to an individual identity.

## 6. Standalone Java 17 Example: Checking View and Export Permissions

The following code illustrates a **server-side access policy** based on:

- Actor identity.
- Actor's tenant and log entry's tenant.
- Role (`SUPPORT`, `SRE`, `SECURITY`).
- Record classification level (`GENERAL`, `INTERNAL`, `RESTRICTED`).
- Action (`VIEW` or `EXPORT`).
- Export approval permission, simulated here by a flag granted from a trusted source.

In this demo, `SUPPORT` can only read `GENERAL`, `SRE` can read `GENERAL`/`INTERNAL`, and `SECURITY` can read all levels **within their assigned tenant**. `EXPORT` is allowed only for `SECURITY` with approval. Every request produces an audit line; when denied, **no message is returned**.

Name the file **LogAccessDemo.java**:

~~~java
public final class LogAccessDemo {

    enum Role {
        SUPPORT, SRE, SECURITY
    }

    enum Classification {
        GENERAL, INTERNAL, RESTRICTED
    }

    enum Action {
        VIEW, EXPORT
    }

    record Principal(
            String id,
            String tenant,
            Role role,
            boolean exportApproved) {
    }

    record LogEntry(
            String id,
            String tenant,
            Classification classification,
            String message) {
    }

    static boolean isAllowed(
            Principal actor, LogEntry entry, Action action) {
        // Disallow cross-tenant reading.
        if (!actor.tenant().equals(entry.tenant())) {
            return false;
        }

        // Exporting data is a separate permission, not implied by VIEW.
        if (action == Action.EXPORT) {
            return actor.role() == Role.SECURITY
                    && actor.exportApproved();
        }

        return switch (actor.role()) {
            case SUPPORT ->
                    entry.classification() == Classification.GENERAL;
            case SRE ->
                    entry.classification() != Classification.RESTRICTED;
            case SECURITY -> true;
        };
    }

    static void access(
            Principal actor, LogEntry entry, Action action) {
        boolean allowed = isAllowed(actor, entry, action);

        // Audit only identity/decision; do not log the raw message.
        System.out.printf(
                "AUDIT actor=%s action=%s event=%s decision=%s%n",
                actor.id(), action, entry.id(),
                allowed ? "ALLOW" : "DENY");

        if (allowed) {
            System.out.printf(
                    "%s event=%s message=%s%n",
                    action, entry.id(), entry.message());
        } else {
            System.out.println("ACCESS DENIED");
        }
    }

    public static void main(String[] args) {
        Principal support = new Principal(
                "support-a", "tenant-a", Role.SUPPORT, false);
        Principal sre = new Principal(
                "sre-a", "tenant-a", Role.SRE, false);
        Principal security = new Principal(
                "security-a", "tenant-a", Role.SECURITY, true);

        LogEntry general = new LogEntry(
                "ev-1", "tenant-a", Classification.GENERAL,
                "service started");
        LogEntry internal = new LogEntry(
                "ev-2", "tenant-a", Classification.INTERNAL,
                "retry count=2");
        LogEntry restricted = new LogEntry(
                "ev-3", "tenant-a", Classification.RESTRICTED,
                "risk event: sensitive fields redacted");
        LogEntry otherTenant = new LogEntry(
                "ev-4", "tenant-b", Classification.GENERAL,
                "another tenant event");

        access(support, general, Action.VIEW);
        access(support, restricted, Action.VIEW);
        access(sre, internal, Action.VIEW);
        access(sre, restricted, Action.VIEW);
        access(security, restricted, Action.VIEW);
        access(security, otherTenant, Action.VIEW);
        access(security, restricted, Action.EXPORT);
        access(sre, internal, Action.EXPORT);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac LogAccessDemo.java
java LogAccessDemo
~~~

**Deterministic stdout**:

~~~text
AUDIT actor=support-a action=VIEW event=ev-1 decision=ALLOW
VIEW event=ev-1 message=service started
AUDIT actor=support-a action=VIEW event=ev-3 decision=DENY
ACCESS DENIED
AUDIT actor=sre-a action=VIEW event=ev-2 decision=ALLOW
VIEW event=ev-2 message=retry count=2
AUDIT actor=sre-a action=VIEW event=ev-3 decision=DENY
ACCESS DENIED
AUDIT actor=security-a action=VIEW event=ev-3 decision=ALLOW
VIEW event=ev-3 message=risk event: sensitive fields redacted
AUDIT actor=security-a action=VIEW event=ev-4 decision=DENY
ACCESS DENIED
AUDIT actor=security-a action=EXPORT event=ev-3 decision=ALLOW
EXPORT event=ev-3 message=risk event: sensitive fields redacted
AUDIT actor=sre-a action=EXPORT event=ev-2 decision=DENY
ACCESS DENIED
~~~

**Explanation of results:**

- `SUPPORT` can view `ev-1` because it is `GENERAL`, but is denied `ev-3` because it is `RESTRICTED`.
- `SRE` can view `ev-2` (`INTERNAL`), and cannot view `ev-3` (`RESTRICTED`).
- `SECURITY` can view `ev-3` in the same tenant, but **cannot view `ev-4`** because it belongs to another tenant.
- `SECURITY` is allowed to `EXPORT` `ev-3` due to the export approval flag; `SRE` does not inherit `EXPORT` simply because they have `VIEW` permission on `ev-2`.
- Every request generates an `AUDIT` line **without containing the message**. On `DENY`, the system only prints `ACCESS DENIED`.
- Switch expressions, records, and enums are all JDK 17 compatible; the program has no external dependencies, network/file I/O, or real-time clock usage, so stdout is deterministic.

### Security Limitations of the Example

This is a **policy-illustration simulation**, not a production IAM system:

1. `Principal` is hardcoded in `main`; a real application must validate tokens/sessions and obtain roles/scopes from a trusted source. **Never take `role` or `exportApproved` from client-supplied parameters**.
2. The `tenant`/`classification` fields on events must be generated and protected by an authoritative pipeline. Never trust a client to self-label sensitive data as `GENERAL`.
3. Printing an "AUDIT" line to stdout does not guarantee durable, tamper-evident auditing isolated from the protected data. Production requires a dedicated audit trail and retention policy.
4. The `access` method does not actually create an export file. For real exports, you must enforce approval, scope, size limits, download expiration, and destination controls, with dedicated auditing.
5. Only three classification levels are used for learning. Real systems may require additional conditions: service, environment, ticket, purpose, time window, geographic policy, and field-level redaction.
6. Checks must be enforced **on every data-returning API**, including pagination, event details, query aggregators, streaming, saved searches, and exports. A single API endpoint that forgets to invoke the policy can still leak logs.

**Key pattern:** denial must happen **before raw records are sent over the network to an unauthorized user**. You cannot download all raw logs to the browser and then hide the lines that should not be seen.

## 7. RBAC and ABAC in Practice

**RBAC (role-based access control)** maps roles to permissions—for example, Support can VIEW masked logs, and SRE can QUERY services they operate. It is easy to administer when staff groups are well-defined.

**ABAC (attribute-based access control)** adds conditions based on actor, resource, and context attributes: tenant, classification, service, environment, purpose, ticket ID, time, network origin, or approval status.

In a multi-tenant log platform, **RBAC + ABAC** is usually more suitable than either mechanism alone:

~~~text
Actor:
  authenticated id, role, assigned tenant(s), expiration
             │
             ▼
Request:
  action, service, environment, tenant, time window
             │
             ▼
Log resource:
  tenant, classification, owner, storage scope
             │
             ▼
Authorization policy
        ┌────┴─────┐
      ALLOW       DENY
        │           │
        ▼           ▼
   Filter/query   No data
   + redact      returned
        └────┬─────┘
             ▼
          Audit
~~~

Prevent **IDOR/BOLA** vulnerabilities: if an endpoint allows selecting a tenant via a query string, the backend must verify it against the tenants granted to the principal. A URL or filter such as `tenant=tenant-b` **must never expand permissions on its own**.

### 7.1. Where Should Authorization Live?

Place checks at the **server-side enforcement point**, before any query or retrieval command that returns raw data. The storage or log backend itself should also follow least privilege: do not use a superuser backend service account and rely solely on frontend checks.

For example, an API might scope a query like:

~~~text
GET /logs?service=orders&tenant=tenant-a
~~~

However, the backend must independently verify whether **`tenant-a` is within the granted scope**, restrict the service/time range, and minimize returned fields. Never allow this pattern:

~~~text
Frontend only displays tenant-a
Backend still accepts tenant-b if the client modifies the request
~~~

That describes an authorization flaw, not a valid endpoint design.

### 7.2. Field-Level Access Control

Not everyone who can view logs needs to see the exact same fields. For example, customer support might see:

~~~json
{
  "event": "payment.failed",
  "tenant": "tenant-a",
  "request_id": "req-17",
  "result": "DECLINED",
  "account_number": "[REDACTED]"
}
~~~

An approved incident response team may be allowed to see additional diagnostic details. However, raw secrets should never be stored just to support a "show/hide" toggle in a dashboard. The safer approach is to **never log secrets at the source**, isolating genuinely sensitive data into separately controlled systems.

UI-level redaction is insufficient if the network response, export endpoint, or saved query still contains the raw field. Redaction must happen before data crosses to an unauthorized principal.

## 8. Reading Log Files on a Server: Operating System Permissions

A Java application may write to files using JUL `FileHandler`, Logback `FileAppender`/`RollingFileAppender`, Log4j2 `RollingFile`, or a similar backend. When logs are files, **read permissions are enforced by the operating system and filesystem**, not by SLF4J or a `logger.info()` call alone.

### 8.1. POSIX/Linux Example

A reference policy:

- The user running the app is **appuser** and needs write access to logs.
- The authorized log-reading group is **logreaders**.
- Other users have no read access.
- The log directory is accessible only to authorized identities.

This policy can be expressed with permission bits:

~~~text
Directory: drwxr-x---  (750)
Log file:  -rw-r-----  (640)
Owner:     appuser
Group:     logreaders
~~~

Meaning:

- With file mode **640**, the owner has read/write; the group has read-only; others have no permissions.
- With directory mode **750**, the owner has read/write/search; the group has read/search; others cannot traverse into the directory.
- The **x (search/traverse) bit on the directory** is required to open files inside it; setting read on the file without directory traverse permission can still result in access denied.
- This is a basic permission example and does not cover POSIX ACLs, user namespaces, root/capabilities, container mounts, or permissions on parent directories.

The following commands are **illustrative only** on a Linux host that already has the appropriate user/group and file; do not run them verbatim in production without verifying the owner, process, and deployment:

~~~bash
# Check permissions and ownership before making changes.
ls -ld /var/log/order-service
ls -l /var/log/order-service/application.log

# Example of changing permission bits; requires appropriate privileges.
chmod 750 /var/log/order-service
chmod 640 /var/log/order-service/application.log
~~~

Never use **chmod 777** or place the log directory inside a web root to "fix permission errors". Doing so can unintentionally expose logs for reading and modification.

You must control **umask**, the owner/group assigned at file creation, file rotation configuration, and the permissions of newly created files after rollover. A log file that is 640 today but rotates into a 644 file tomorrow still causes a leak. It is best to apply secure permissions **at file creation time**, rather than creating overly permissive files and fixing them afterward.

### 8.2. Java NIO and POSIX Permissions

Java 17 provides the **PosixFilePermissions** API when the underlying filesystem supports the POSIX permission view. The snippet below is an **integration illustration** for an application that already has a `Path` and log file; it **does not run standalone**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

// Applies only on filesystems supporting PosixFileAttributeView.
Path logPath = Path.of("/var/log/order-service/application.log");
Files.setPosixFilePermissions(
        logPath,
        PosixFilePermissions.fromString("rw-r-----"));
~~~

A filesystem that does not support POSIX, such as typical Windows environments, may throw **UnsupportedOperationException**. Windows typically uses **NTFS ACLs**; do not treat `"rw-r-----"` as a universal permission model.

**Important:** fixing permissions after a file is created does not eliminate all risk, because there is an initial window where permissions may be too broad. In production, prefer file/directory creation policies, dedicated app-user privileges, and infrastructure-managed filesystems. Additionally, a privileged process or another account may still access files via OS mechanisms; test using **real identities**, not just by looking at `ls` output.

### 8.3. Do Not Give Readers Write or Admin Permissions

Support teams viewing logs typically only need read/search, and do not need to:

- Edit or delete log files.
- Change owner/group, ACLs, or rotation policies.
- Change logging configuration to enable `DEBUG` and generate sensitive data.
- Access directories containing databases, secrets, or out-of-scope configurations.

If the application writes files as `appuser`, a log shipper may need to read those files to forward them to a collector. That does not mean the log shipper account needs permission to modify files or read every directory on the host.

## 9. Containers and Kubernetes: Viewing stdout Is Not Controlled by Java APIs

In containerized environments, applications typically write to stdout/stderr; kubelet and the container runtime store and serve logs via platform mechanisms. **Who can run `kubectl logs`** is governed by Kubernetes API access controls and related mechanisms, not `Logger.setLevel()` in Java.

### 9.1. Pod Logs Are a Subresource

In Kubernetes RBAC, Pod logs are the **pods/log** subresource. For a specific Pod in a namespace, reading logs typically requires the **get** verb on **pods/log**. If using commands that discover Pods by name or selector, **get/list** permissions on **pods** may also be required.

Example `Role` granting permission to view Pod metadata and Pod logs in the **orders-staging** namespace, without granting create/update/delete:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-log-reader
  namespace: orders-staging
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
~~~

For the `Role` to take effect for an authenticated identity group, a corresponding **RoleBinding** is required. Illustrative YAML example:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-log-reader-binding
  namespace: orders-staging
subjects:
  - kind: Group
    name: staging-log-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: orders-log-reader
  apiGroup: rbac.authorization.k8s.io
~~~

This is an illustrative manifest. The **staging-log-readers** group must exist in the cluster's identity provider and the namespace must match. In practice, check existing admin permissions, group policies, other RoleBindings/ClusterRoleBindings, and admission controls.

**Scope warning:** the `Role` above is not restricted solely to the "orders" deployment; it allows reading logs of **matching Pods across the entire `orders-staging` namespace** as granted. Kubernetes RBAC does not automatically restrict `pods/log` by label selector just because the Role name contains "orders". If multiple tenants share a namespace and require strong isolation, design separate namespaces/identities and query mechanisms accordingly.

### 9.2. Verifying Effective Permissions

Examples for the current identity connected to the target cluster:

~~~bash
kubectl auth can-i get pods/log -n orders-staging
kubectl auth can-i list pods -n orders-staging
~~~

The first command asks whether the caller has permission to **get pods/log** in the namespace; the second asks whether they can list Pods. The **yes/no** result depends on kubeconfig, credentials, and active authorization rules. A single `can-i` check does not replace end-to-end testing of what a user can actually see; namespaces, containers, tokens, policies, and downstream collectors also matter.

Illustrative log viewing command:

~~~bash
kubectl logs -n orders-staging pod/order-service-abc123
~~~

The Pod name is just an example; use the actual Pod name. Multi-container Pods may require **-c**; **-f** follows the stream, carrying the risk of continuous data collection. Never include kubeconfig files or bearer tokens in shared commands.

### 9.3. Other Read Paths Outside `kubectl logs`

Even if someone lacks `pods/log` permission, they might still have access to:

- Centralized log dashboards (Loki, Elastic, OpenSearch, or equivalent platforms).
- Log files on nodes or volumes, if they have infrastructure access.
- Container runtimes or CI/CD tools.
- Storage backends, object storage, snapshots, or backups.
- Support services that export logs to attach to tickets.

Conversely, granting **pods/log** does not automatically grant permission to query every index in a centralized logging system. True read control requires **inventorying every access path to the same data**. RBAC in one place does not protect copies exported elsewhere.

## 10. Centralized Log Read Permissions and Service Accounts

A common architecture:

~~~text
Java applications
        │
        ▼
  stdout / file
        │
        ▼
  agent / collector
        │
        ▼
  central log storage
        │
     ┌──┴──────────────┬───────────────┐
     ▼                 ▼               ▼
 dashboards         query API       export/archive
     │                 │               │
     └────── authn + authz + audit ─────┘
~~~

Identities and permissions should be separated:

- **Application producer**: permission to write logs to local output; no need to query all historical data.
- **Log shipper/exporter**: permission to send data to designated endpoints/namespaces; no need to search all logs or delete indices.
- **Analyst/Support**: permission to read data scoped by service/tenant/time range, typically redacted.
- **Security investigator**: conditional access to sensitive logs for an incident, with time limits and auditing.
- **Platform operator**: permission to administer infrastructure/pipelines as required; does not automatically imply raw log access across all tenants.
- **Storage administrator**: permission to manage indices, retention, and backups; if they can access content, that must be treated as a read path and controlled accordingly.

**Do not reuse the same admin API key for both the logging appender and the query dashboard.** If an application is compromised, an over-privileged key turns a single-service breach into full read/delete access across the entire system's logs.

### 10.1. Environment Separation

Dev, test, staging, and production must have distinct read policies. Access to dev must not automatically grant read access to production; CI accounts should not use production raw-log read permissions to run tests. Partitioning can be done by tenant, namespace, index, project, or account depending on the technology, but **real isolation** is required—not just adding `environment=prod` as a field in each record.

A search query with a tenant filter is not enough if the user can simply remove that filter. Enforce scoping at the data authorization layer or query service so it cannot be bypassed by editing a URL.

### 10.2. Saved Searches, Dashboards, and Exports

A dashboard can inadvertently share data through:

- Public links or embedded iframes.
- Scheduled emails/PDFs/CSVs.
- API keys hardcoded in the client.
- Saved queries with improperly inherited permissions.
- Download buttons exporting more fields than are displayed on screen.
- Caches/CDNs or object storage holding exported files.

Verify that **permission to view a dashboard does not imply permission to query or export raw logs**. If a report is sent to someone who lacks access to the source system, the report itself becomes a **new data copy** and requires its own sharing and retention policy.

## 11. Auditing Log Read Activity

Reading logs can be routine operational work, or it can be unauthorized data lookup. An **audit trail for log access** should record enough to prove who did what without duplicating sensitive data.

Useful attributes:

| Field | Meaning |
| --- | --- |
| **actor_id** | Authenticated identity, not a self-reported name from the request. |
| **action** | `VIEW`, `QUERY`, `FOLLOW`, `EXPORT`, `SHARE`, `MANAGE_ACCESS`. |
| **target_scope** | Service, tenant, environment, index, classification, or relevant event IDs. |
| **time_range** | The data window queried. |
| **request_time / result** | Timestamp and `ALLOW`/`DENY`/`ERROR`. |
| **query_id** | Query identifier to correlate audit with the request, avoiding logging raw queries that may contain PII. |
| **purpose / ticket** | Reason, ticket, or corresponding approval when required by policy. |
| **record_count / export_size** | Scale of data accessed or exported. |
| **network/device context** | Information permitted for investigation, without excessive collection. |

Example of **a minimized audit event**:

~~~json
{
  "actor_id": "security-a",
  "action": "EXPORT",
  "scope": "tenant-a/orders-prod/restricted",
  "query_id": "qry-428",
  "ticket": "INC-104",
  "result": "ALLOW",
  "record_count": 6
}
~~~

This is illustrative JSON and contains no raw log data. Real systems should add timestamps, request IDs, access duration, and corresponding policy details. Never record access tokens, passwords, or full queried payloads inside audit events.

### 11.1. Audit More Than Just DENY

Valid queries can still be risky if their scope is overly broad or behavior is unusual. Monitor for:

- Unusually large numbers of exported records.
- Querying multiple tenants within a short time window.
- Access outside normal hours or from unusual locations/devices per policy.
- Sudden spikes in sensitive data queries after a role change.
- Service accounts querying outside their authorized function.
- Increases in `DENY` events tied to the same actor or resource group.

Avoid writing access audits solely into **the same log system that the person under investigation can modify or delete**. For high assurance, store the audit trail in a separate trust boundary with restricted write/read permissions and appropriate retention/monitoring.

### 11.2. Avoiding Logging Loops

If every read of the audit log writes back into the same audit log and a viewer system polls continuously, it can create noise or an infinite loop. Design a separate audit pipeline, classify events automatically, and test the read path. Do not disable auditing entirely just to reduce volume; approved sampling or aggregation policies can be applied to low-sensitivity technical operations, while sensitive access events must meet full traceability requirements.

## 12. Privacy in Copies and the Data Lifecycle

Keeping logs in a primary storage system with strong RBAC is not enough if **copies** sit outside the control boundary.

Copies to account for:

- Dumps downloaded by investigators.
- Temporary files created when sending logs via support tickets.
- Attachments in email, chat, or issue trackers.
- CI build artifacts containing stdout or test logs.
- Storage snapshots, backups, and archives.
- Files on local machines, personal drives, or temporary memory of analysis scripts.
- Caches in dashboards, proxies, or API gateways.

For every copy, you must know **who can read it, where it lives, when it is deleted, how sharing is revoked, and whether it is encrypted at rest and in transit**.

### 12.1. Retention and Deletion

Log retention periods depend on purpose, internal policy, contracts, and applicable laws. There is no single retention number that fits every Java application. Do not retain logs indefinitely just because storage is cheap; conversely, do not prematurely delete data required for preservation during a valid investigation.

If personal data appears in logs, evaluate governance responsibilities: minimization, classification, access scope, retention, deletion, and related obligations. Legal holds or retention exceptions may be needed, but must be authorized and audited.

### 12.2. Encryption Does Not Replace Authorization

**Encryption at rest** and **TLS in transit** reduce the risk of unintended reading from disk or network. However, if a user with query API access receives plaintext through a dashboard, encryption does not prevent that user from viewing and extracting it. Conversely, strong RBAC does not replace encryption when data traverses networks or unprotected backups.

Similarly, **hashing/masking** helps reduce exposed data but has limits. Hashes of low-entropy identifiers can be brute-forced; having the same hash appear across multiple logs still enables activity correlation. Choose techniques based on purpose, threat model, and data policy.

## 13. Difference Between Viewing Logs and Changing Logging Configuration

Someone with permission to **change `logging.level.root=DEBUG`**, modify patterns to print HTTP headers, or configure an appender to send to another endpoint can increase the amount of information collected. Even without direct permission to read raw logs, configuration-change permissions can create future leaks.

Separate these permissions:

- **READ**: look up authorized logs.
- **CONFIGURE**: change level/pattern/sampling/filters within a granted scope.
- **MANAGE_SINK**: change endpoints/collectors/indices, which can affect access control.
- **EXPORT**: create data copies.
- **DELETE**: delete records or alter retention.
- **GRANT**: change permissions of other actors.

Review all permissions that **indirectly lead to reading**: modifying application code to log secrets, accessing backup files, adding a second exporter, issuing a query token to oneself, or disabling redaction. This is why log privacy cannot be solved with a single `RoleBinding`.

## 14. Testing Log Read Permissions

### 14.1. Minimum Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Unauthenticated call to query API | `DENY`, no raw logs returned. |
| Valid user without `READ` | `DENY`, no sensitive data or metadata returned. |
| `SUPPORT` viewing masked logs in assigned tenant | `ALLOW` within scope, no raw secrets. |
| `SUPPORT` requesting `RESTRICTED` logs | `DENY`, no content leaked. |
| `SRE` viewing an out-of-scope service | `DENY` by scope. |
| User in tenant A modifies query to tenant B | `DENY` or scope B stripped on backend; independent of UI. |
| User with `VIEW` calls `EXPORT` | `DENY` without separate `EXPORT` permission. |
| Expired or revoked token | `DENY` immediately per policy; no stale permissions used. |
| High-privilege role without incident approval | `DENY` for approval-gated data. |
| Expired break-glass grant | Access revoked and audited/reviewed. |
| User with dashboard access calls raw API directly | Cannot bypass redaction/authorization. |
| Saved search, follow, pagination, bulk API | Same scope policy enforced across all endpoints. |
| Logs exported to CSV/ZIP | Authorization, labeling, TTL, secure storage, and audit verified. |
| Rotated/backed-up/archived logs | Permissions on copies are no broader than policy allows. |
| Kubernetes `pods/log` in another namespace | `DENY` per RBAC; verify additional bindings. |
| Employee changes permission groups | Old permissions revoked within organization's SLA. |
| Actor reading their own audit logs | Cannot edit/delete audit trail; independent access control. |
| Attempting file access via symlink/path traversal | Cannot escape authorized directory/data source. |
| Overly broad or continuous queries | Appropriate rate/size limits, approval, and alerting. |

### 14.2. Writing Assertions

Use test logs with **distinct event IDs** and synthetic messages:

~~~text
ev-101 GENERAL tenant-a "health check successful"
ev-102 RESTRICTED tenant-a "sensitive event redacted"
ev-103 GENERAL tenant-b "other tenant event"
~~~

Assert not only the HTTP status code, but also the **response body**:

- On `DENY`, no event message, raw fields, or counts that leak unauthorized information.
- On `ALLOW`, results belong strictly to the granted tenant/service/time range.
- A request combining two tenants must not return merged data outside the actor's scope.
- Exports and saved searches must not broaden the granted view/query permissions.
- Raw secrets must never be included in the payload and merely hidden on the frontend.
- Audits must capture both `ALLOW` and `DENY` and correlate with the request ID without containing sensitive content.

Negative tests are more important than merely verifying that an admin can see everything. For multi-tenant systems, verify that **an actor in tenant A cannot access tenant B** even when the query is manually crafted.

### 14.3. Testing File and Kubernetes Permissions

For POSIX files, test with **two different real OS identities**, rather than relying solely on `chmod` output. For Kubernetes, use test identities with realistic granted permissions, and avoid assuming a `ClusterRoleBinding` does not grant broader access than a local `Role`.

If a centralized logging system runs alongside Kubernetes, test both the **Kubernetes API** and the **collector/storage query API**, as they are two independent read paths.

## 15. Workflow for Handling Sensitive Log Access Requests

A support request needing customer log access can follow this workflow:

1. **Intake**: identify the purpose, ticket, service, environment, time window, and relevant tenant.
2. **Minimization**: can this be resolved using metrics, trace summaries, or masked logs?
3. **Authorization verification**: requester identity, current role/scope, and whether approval is required.
4. **Scoped grant**: short duration, specific tenant/service, and only the necessary classification level.
5. **Monitored access**: audit queries and exports; restrict record counts, fields, and time windows.
6. **Sharing results**: do not send raw logs over unapproved channels; use sanitized/masked versions when sufficient.
7. **Closure**: revoke the grant, handle exported files, and retain audits/tickets per retention policy.
8. **Review**: if repeated access is needed frequently, improve dashboards or log fields to reduce the need for raw access.

During critical incidents, a break-glass workflow may be used, but it still requires a documented reason, expiration, notification, and post-incident review.

## 16. Diagnosing Overly Broad Read Permissions

For example, a support group accidentally has read access across all production namespaces.

**Step 1 — Scope the effective permissions:** identify the identity/provider, roles/groups, tokens/credentials, `RoleBinding`/`ClusterRoleBinding`, dashboard/query API permissions, backups, and exports. Never draw conclusions from a Role's name alone.

**Step 2 — Contain the risk:** revoke or narrow the out-of-policy grant, invalidate sessions/tokens as needed, and preserve audit evidence. Never delete audit logs or access history to "clean up".

**Step 3 — Identify potentially read data:** inspect `ALLOW` audits, query IDs, time ranges, downloads, record counts, and related copies. Distinguish between **having access** and **having actually accessed** the data.

**Step 4 — Assess impact:** classify the log contents (PII, secrets, tenant data, security evidence), affected parties, and reporting requirements under applicable policies or laws. If secrets were exposed, evaluate rotation/revocation per security procedures.

**Step 5 — Prevent recurrence:** fix policy-as-code, add negative tests, enhance log-access auditing, review export permissions, and schedule periodic grant reviews.

Do not remediate by merely hiding a dashboard if the raw query API and export tokens remain open. Re-verify using a **low-privilege account** after the fix.

## 17. Common Misconceptions

1. **"Viewing logs without editing is safe."** False; read access can expose personal data and secrets.
2. **"Production logs have no PII because the app has no PII forms."** False; frameworks, exceptions, headers, trace metadata, and libraries can inadvertently log data.
3. **"Masked in the UI means the data is protected."** False if the raw API or export still sends the full record.
4. **"Infrastructure admins automatically need full raw log read access."** Not necessarily. Platform administration and data viewing permissions can be separated.
5. **"Kubernetes RBAC alone is enough."** False if users can also view logs via SIEM, dashboards, files, or backups.
6. **"A namespace read Role only reads one deployment."** False. `pods/log` RBAC can grant access to Pods across the entire namespace according to its scope.
7. **"Having VIEW means you can EXPORT."** Should not be implied. Exporting creates easily propagated copies and requires its own policy.
8. **"File mode 640 is sufficient on every OS."** False; Windows, POSIX ACLs, groups, symlinks, and identities have different semantics.
9. **"Storage encryption replaces read permissions."** False; query APIs can decrypt and return plaintext to anyone with credentials.
10. **"Reading logs doesn't need auditing."** False; querying and exporting are security-relevant actions.
11. **"No need to revoke temporary access if the person is still on the team."** False; permissions should be tied to active need and duration.
12. **"It's fine to paste raw logs in a ticket or chat for convenience."** Unsafe if that channel has broader access than the log platform.
13. **"Log shippers need admin permissions to make sure no logs are lost."** False; they typically only need specific source-read and destination-write permissions.
14. **"A single `can-i` result proves the whole system is secure."** False; that checks one permission in one API scope and does not cover other data paths.
15. **"Hiding secrets in the viewer is enough."** No; you must prevent logging secrets and protect all copies.
16. **"Returning full event/tenant names on Deny is harmless."** It can cause information disclosure; deny responses should also be minimized.

## 18. Practice Exercises

**Exercise 1.** Run `LogAccessDemo.java` and explain why `SECURITY` cannot read `ev-4` despite being the highest role in the demo.

**Exercise 2.** Extend the policy with an **environment** attribute. Allow `SRE` to read production only when the service is in their responsibility list; write negative tests for staging/prod and other services.

**Exercise 3.** Replace `exportApproved` with an `Approval` record containing `actorId`, `ticket`, `scope`, and `expiry`. Describe the trusted data source, backend validation, and what happens when the approval expires. Do not allow the client to set `approved=true`.

**Exercise 4.** In a POSIX test environment, create a dummy log file with mode 640 inside a mode 750 directory. Test with two OS users: one in the `logreaders` group and one outside the group. Explain the `x` permission on the directory.

**Exercise 5.** Review the Kubernetes `Role`/`RoleBinding` configuration in Section 9. Identify which Pods' logs it allows viewing and why it does not automatically restrict by deployment name.

**Exercise 6.** Design permissions for three groups: Support viewing only masked logs for assigned tenants; SRE scoped by service; Security querying raw logs for an approved incident. List the `VIEW`, `QUERY`, `FOLLOW`, and `EXPORT` endpoints that must be controlled.

**Exercise 7.** A dashboard displays masked data, but its API returns raw JSON. Analyze how the leak can be exploited and where redaction/authorization must be enforced.

**Exercise 8.** Someone with production log access exported 1 million lines and posted them in a chat room. Identify technical and procedural measures to prevent, detect, and respond to this.

**Exercise 9.** Build a periodic log-permission review checklist: unused grants, departed accounts, expired tokens, public links, exports in the last 30 days, backups/archives, and break-glass history.

## 19. Conclusion

**Log read permission is data access permission, not just permission to open a text file.** Risk depends on the data inside the logs, query scope breadth, tenant, environment, retention period, and export capabilities.

To protect privacy in Java logging, combine **avoiding unnecessary data + redaction + authenticated identity + backend-enforced authorization + scoped least privilege + comprehensive access auditing + copy/retention controls**. File permissions, Kubernetes RBAC, and centralized system permissions are **distinct control layers**; you must verify the entire path from the JVM to dashboards and archives.

**Bottom line:** when someone asks "Who can read this log?", the answer should never be "anyone with the dashboard link." You must be able to state clearly **who, which portion, for what purpose, when, under what authorization, and how that access is audited**.

### References

- OWASP Logging Cheat Sheet — Protection, data to exclude, verification: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Developer Guide — Security Logging and Monitoring: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/
- Kubernetes — Using RBAC Authorization, pods/log subresource: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes — kubectl logs: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Oracle JDK 17 — PosixFilePermissions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- Oracle JDK 17 — PosixFileAttributeView: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html
- NIST SP 800-92 — Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final
