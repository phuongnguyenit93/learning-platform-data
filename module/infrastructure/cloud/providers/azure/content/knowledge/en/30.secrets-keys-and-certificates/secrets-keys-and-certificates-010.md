# Secret Access Auditing and Authentication Troubleshooting

A Java service running on Azure App Service receives **403 Forbidden** when retrieving an API key from Azure Key Vault. An operator sees the **Contributor** role on the resource group and assumes the app already has permission. In another scenario, that same app successfully reads the secret, yet monitoring detects hundreds of off-hours secret reads from an unapproved identity. Both cases require knowing **who accessed which secret, at what time, with which identity, over which network, and whether the operation succeeded or was denied**, without ever exposing the secret value during investigation.

**Azure Key Vault** stores and manages the lifecycle of **secrets, cryptographic keys, and certificates**. A secure design does not stop at putting credentials inside a vault: it requires **enabling auditing**, enforcing least privilege, controlling network paths, alerting on anomalous access, classifying authentication failures, and having an incident response workflow when credentials leak. This lesson focuses on **auditing secret operations** and troubleshooting **Microsoft Entra ID, Azure RBAC/access policies, firewalls/Private Link, and secret-consuming applications**. Differences for Keys/Certificates are noted where they affect auditing or permissions.

This lesson belongs to the **Secrets, Keys, and Certificates** chapter of the `CLOUD_PROVIDERS_AZURE` module. Within the module scope, learners explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to compute, networking, storage, and data, then deploy, monitor, protect, and control costs of a real-world application architecture.

> **Safety rule:** Audit logs let you **observe operations and access outcomes**—they do not prove every retrieved secret value was used legitimately, nor do they replace rotating/revoking credentials at the target system. Never turn on debug modes that print **secret values, Authorization headers, access tokens, or secret-bearing request/response bodies** just to “see the error”.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **Key Vault data-plane `AuditEvent`**, **Azure Activity Log**, **Microsoft Entra sign-in/workload identity telemetry**, and **application logs**.
2. Explain what trace and permissions a secret **`Get`/`List`/`Set`/`Delete`/`Recover`/`Purge`** creates, without confusing metadata access with reading secret values.
3. Configure diagnostic settings to a **Log Analytics workspace**, Storage, or Event Hubs per permissions and policy.
4. Read critical audit fields: time, operation, status/result, resource, caller IP, identity claims, and request/correlation ID.
5. Write KQL queries to analyze failed access, high `Get` counts, anomalous activity by principal/IP, and timelines around role changes.
6. Distinguish **401 Unauthorized**, **403 Forbidden**, **404 Not Found**, **429 Too Many Requests**, 5xx, timeouts/DNS/TLS, and bearer challenges.
7. Diagnose **control plane vs. data plane**, Azure RBAC vs. Key Vault access policies, role scopes, and propagation.
8. Inspect **`DefaultAzureCredential`**, managed identities, user-assigned identities, AKS workload identities, and token audiences/tenants.
9. Explain Private Endpoints, public firewalls, private DNS, and why 403 can stem from network restrictions rather than a missing role.
10. Design Java SDK logging/exception handling without leaking secrets, along with bounded retries.
11. Build runbooks for **compromised credentials**, **anomalous reads**, **apps failing to fetch secrets**, and **failed rotations**.
12. Define log retention, forensic evidence preservation, least privilege, alerts, SLOs, and cost controls.
13. Execute a lab using synthetic data testing both successful and denied requests without touching a production vault.
14. Create checklists and negative tests to verify production readiness before launching workloads.

## 2. Running Scenario: Orders API and Payment Secret

Suppose an enterprise runs an **Orders API** written in Java 17/Spring Boot on Azure App Service. The app needs **`orders-payment-api-key`** to call a payment partner. Components:

- **Subscription/resource group:** hosts the vault, application, role assignments, and monitoring.
- **Microsoft Entra ID:** provides the identity and access tokens for the Orders API managed identity.
- **Azure Key Vault:** stores secrets by name with multiple versions and enforces data-plane authorization.
- **App Service/AKS:** runs the Java workload; outbound networking must reach the vault.
- **Azure Monitor/Log Analytics:** aggregates audit and operational telemetry.
- **Partner API:** uses the API key to authenticate business requests.
- **Rotation operator/pipeline:** holds secret-management permissions separate from the app reader.

Diagram:

~~~mermaid
flowchart LR
    APP["Orders API<br/>Java + Managed Identity"] --> ENTRA["Microsoft Entra ID<br/>access token"]
    APP --> KV["Azure Key Vault<br/>SecretGet"]
    KV --> PARTNER["Secret value used by<br/>backend Partner API client"]
    APP --> PARTNER
    KV --> DIAG["Diagnostic settings<br/>AuditEvent"]
    DIAG --> LAW["Log Analytics Workspace"]
    ARM["ARM / IAM / vault settings"] --> ACT["Azure Activity Log"]
    ENTRA --> IDLOG["Identity/sign-in telemetry"]
    APP --> APM["Application Insights<br/>sanitized traces"]
    LAW --> SOC["Security operations<br/>KQL + alerts"]
    ACT --> SOC
    IDLOG --> SOC
    APM --> SOC
~~~

**Operational questions to investigate:**

- How many successful **`SecretGet`** calls hit the vault in the last 24 hours?
- Which identity read the secret at 02:00 UTC? Is it on the workload/region allowlist?
- Was a 403 caused by **RBAC** or by the **firewall**?
- Who changed the permission model or added a role assignment right before the anomalous access?
- Did the app pick the right **managed identity**, or accidentally pick up a developer/service-principal credential?
- Which secret version is in use; was it disabled/expired, or did the app cache an old version?
- If the API key leaked, is deleting it from Key Vault enough to stop attackers from using it at the partner?

## 3. Concepts That Must Be Distinguished

| Concept | Meaning | Example |
|---|---|---|
| **Secret value** | Confidential value used by the app to authenticate externally | Actual API key |
| **Secret name** | Logical name used by the app to look up the secret | `orders-payment-api-key` |
| **Secret version** | Specific value version under that name, with its own identifier | GUID-like version string |
| **Secret ID** | URI pointing to name/version in the vault | `https://vault.vault.azure.net/secrets/name/version` |
| **Vault URI** | Key Vault data-plane endpoint | `https://vault.vault.azure.net/` |
| **Caller identity** | Principal/token executing the data-plane operation | Orders API managed identity |
| **Control plane** | ARM managing resources/IAM/networking, separate from reading values | Updating vault firewall |
| **Data plane** | REST operations reading/writing secrets/keys/certificates | `SecretGet` |
| **Diagnostic setting** | Rule forwarding logs/metrics to a destination | `AuditEvent` → Log Analytics |
| **Audit event** | Operation record; must not contain the secret value | `SecretGet`, status 200/403 |
| **Correlation/request ID** | Linking ID across service/app layers | Request tracking ID |
| **Rotation** | Replacing a credential and migrating apps to the new one | Partner key v1 → v2 |
| **Revocation** | Invalidating the old credential where it is verified | Disabling partner API key v1 |

### 3.1. Secret vs. Key vs. Certificate

**Secret:** if the caller has read access, the secret value can be returned to the JVM. **Key:** with HSM-backed/non-exportable keys, cryptographic operations execute via `CryptoClient`/`CryptographyClient` without exporting the private key. **Certificate:** has its own lifecycle, policy, and permissions, and may link to key/secret objects depending on certificate configuration.

When auditing **secret reads**, focus on **`SecretGet`**, rather than confusing **`KeySign`**, **`KeyDecrypt`**, or **`CertificateGet`** with downloading secret values. Someone permitted to view vault metadata is not necessarily permitted to read values.

### 3.2. Secrets Have Multiple Versions

~~~text
Vault: kv-orders-prod-example
  Secret: orders-payment-api-key
    Version V1: legacy credential
    Version V2: replacement credential
~~~

**`getSecret(name)`** and **`getSecret(name, version)`** have different semantics. When investigating rotation, know which version the app uses. Never write V1/V2 values into logs; handle version IDs and metadata per security policy, hashing or masking them if required.

### 3.3. Authentication, Authorization, and Networking

A **Get Secret** flow has independent prerequisites:

~~~mermaid
flowchart TD
    A["Java caller"] --> B["Authentication<br/>Entra token issued"]
    B --> C["Network path<br/>firewall / Private Endpoint"]
    C --> D["Authorization<br/>Key Vault RBAC / access policies"]
    D --> E["Secret lifecycle state<br/>exists/enabled/valid"]
    E --> F["Return secret value to authorized app"]
~~~

This diagram is a logical model and **does not assert Key Vault's internal evaluation order** for every request. Troubleshooting must distinguish bad tokens, blocked networks, missing roles, and secret lifecycle states.

## 4. Four Evidence Sources and Their Boundaries

### 4.1. Key Vault Data-Plane Audit Logs

**Key Vault diagnostic logs** are the primary source for investigating data-plane operations on a vault once enabled and routed to a destination. They typically use the **`AuditEvent`** category per Key Vault/SKU support, recording operation, timestamp, caller IP, identity claims, outcome, and error code.

**Audits must never contain plaintext secret values**, yet logs still contain **secret names, secret URIs, identities, IPs, and sensitive metadata**. Restrict log read access and retention.

**Never assume logs existed before diagnostic settings were enabled.** Turning them on today does not retroactively populate prior `getSecret` calls.

### 4.2. Azure Activity Log

**Azure Activity Log** is the key source for **control-plane** operations, such as:

- Creating/deleting a vault resource.
- Modifying public network access, firewall rules, or private endpoints on the resource.
- Switching between Azure RBAC and access policies.
- Adding/removing Azure role assignments (often logged under `Microsoft.Authorization`).
- Updating diagnostic settings.
- Related deployments and policy actions.

**The Activity Log is not a complete list of every secret-value read.** A successful `SecretGet` happens on the Key Vault data plane; seeing it requires data-plane audit logging.

### 4.3. Microsoft Entra Identity Telemetry

Identity/sign-in/workload logs help verify:

- Which identity is requesting tokens.
- Authentication success/failure and Conditional Access policies where applicable.
- Which service principal or managed identity was used.
- Tenant, subject, and resource audience.
- Changes to credentials, federated identities, and principal configurations.

A successfully issued token **does not prove** the caller holds Key Vault data-plane permissions. Furthermore, token/identity logs vary by log type, limits, licensing, retention, and latency. Never assume every token acquisition appears in the same table or on every single request.

### 4.4. Application Telemetry

Application Insights/OpenTelemetry or app logs reveal:

- Which Java component called `getSecret`.
- Startup vs. refresh vs. business-request paths.
- Latency, retry counts, and cache hits/misses.
- Which secret name/version/credential type was chosen (within safe logging rules).
- Outcomes when using the secret against the **Partner API**, such as HTTP 401 from the partner.

**Critical point:** a 401 from the **Partner API** is not a 401 from **Key Vault**, even though both say Unauthorized. Record **dependency name + endpoint/service** in telemetry to pinpoint the real failure.

### 4.5. Asking Evidence-Based Questions

| Question | Appropriate source | Cannot be inferred alone |
|---|---|---|
| Were there `SecretGet` calls to the vault during window X? | Key Vault `AuditEvent` | Which actions the secret value was used for |
| Who assigned `Key Vault Secrets User`? | Azure Activity Log / authorization audit | Whether the principal actually called `getSecret` |
| Which identity is Java using? | Sanitized Identity SDK diagnostics, app context, Entra logs | All claims inside Key Vault if unlogged |
| Why did Java GET return 403? | Key Vault failure details + audit + RBAC + networking | Looking at Portal permissions alone is insufficient |
| Was the secret used against the partner API? | Partner audit logs, application telemetry | Key Vault audits do not see partner requests |
| Did a key leak in CI logs? | CI log inspection/scanners and incident review | Absence of anomalous `SecretGet` does not prove no leak occurred |

## 5. Permission Models: Azure RBAC vs. Access Policies

### 5.1. Control Plane Differs from Data Plane

An Azure **Contributor** on a resource group can modify many resource properties, yet **does not inherently hold data-plane permission to read secret values** under Azure RBAC.

Similarly, **Key Vault Reader** primarily reads metadata and does not grant **Secret Get value**. **Key Vault Secrets User** is typical for an app that only reads secrets; **Key Vault Secrets Officer** is for operators/rotation workloads managing secrets; **Key Vault Administrator** holds broad data-plane rights and should not be granted to ordinary apps.

| Task | Permissions to evaluate | Example principal |
|---|---|---|
| Read API key at runtime | Key Vault Secrets User / Secret Get | Orders API managed identity |
| Create new version / rotate | Key Vault Secrets Officer per policy | Rotation service |
| Inventory metadata | Key Vault Reader if sufficient | Inventory operator |
| Edit vault firewall | Appropriate ARM management role | Platform team |
| Create role assignments | Authorized Owner / User Access Administrator / RBAC Administrator | IAM operator |
| Configure diagnostic settings | Appropriate Monitoring/ARM permissions + destination access | Platform monitoring team |
| Query Log Analytics audits | Appropriate workspace/table/query RBAC | SOC/SRE |

Role names and exact **`dataActions`**, scopes, and conditional assignments can evolve; verify role definitions in the active tenant. **Never grant Owner to an app to fix 403.**

### 5.2. Permission Model Is a Vault-Level Choice

Key Vault offers:

- **Azure role-based access control** (Azure RBAC) as the data-plane permission model.
- **Vault access policies** (legacy/compatibility model) granting get/list/set/delete permissions per principal.

Check **which model the vault has enabled**. Creating an RBAC role on a vault in access policy mode—or adding an access policy to an RBAC vault—does not produce the expected effect.

### 5.3. Scope and Least Privilege

A role assigned at subscription or resource group scope affects far more vaults than a vault-level assignment. For sensitive secrets, pick the **narrowest practical scope**, considering secret-scoped assignments where supported by features and operations. Separate vaults when clear security boundaries are needed between production and development.

Pay special attention to the **access policy model**: anyone allowed to edit vault access policies on the control plane can grant themselves data access unless blocked by governance—one strong reason to tighten provisioning roles and prefer Azure RBAC.

### 5.4. Authorization Propagation and Token Caching

Added or revoked role assignments may not take effect instantaneously due to **propagation and caching**. In an urgent security incident, never remove one role and declare all access blocked. Verify empirically, apply multi-layer containment (identity, networking, vault, partner credential rotation), and follow your organization's runbook.

## 6. Configuring Auditing Before an Incident Happens

### 6.1. Diagnostic Settings

Key Vault **diagnostic settings** ship logs/metrics to supported destinations:

- **Log Analytics workspace:** run Kusto Query Language (KQL), alert rules, and analytics.
- **Azure Storage account:** retain logs for archival/compliance.
- **Azure Event Hubs:** stream audit events to SIEMs or data pipelines.
- Other destinations supported by Azure Monitor and resource tier.

Schema options include **`AzureDiagnostics`** (legacy/shared table) or **resource-specific tables**; exact table and column names depend on diagnostic settings, date, and resource type. **Never assume every workspace has an `AZKVAuditLogs` table** if diagnostics are not configured for resource-specific mode.

### 6.2. Collect All Required Log Sources

Investigating an authentication incident end to end typically requires:

1. **Key Vault `AuditEvent`:** data-plane operations.
2. **Azure Activity Log** for the subscription/resource group: resource changes.
3. **IAM / role-assignment change events:** when permissions changed and who changed them.
4. **Microsoft Entra workload/service principal/managed identity logs** where available.
5. **Application/HTTP dependency telemetry** from the Java runtime.
6. **Network telemetry** when using firewalls, private endpoints, VNets, or Azure Firewall.
7. **Partner API audits** when secrets authenticate against external systems.

A single log source rarely proves the full root cause of an incident.

### 6.3. Audit Logs Are Not Secret Backups

**Never log secret values**, even at backend debug levels. Key Vault logs are not designed as a plaintext secret recovery store. Key Vault backup/recovery and rotation are separate processes; never treat a Log Analytics export as a “secret backup”.

### 6.4. Retention, Time, and Chain of Custody

- Enable logging **before launching** production apps.
- Set retention per security, legal, environmental, and budget requirements.
- Standardize on UTC timestamps for correlation; keep system clocks synced.
- Lock down workspaces, storage, and event streams with RBAC and least privilege.
- Restrict permissions to delete/modify logs and destination settings.
- Configure archive/immutable storage if policy requires it.
- During an incident, preserve records under chain-of-custody procedures—logging who accessed what, scope, time, queries, and export hashes/metadata.
- Practice data minimization: identities, IPs, and secret names remain sensitive metadata.

### 6.5. Diagnostic Settings Need Auditing Too

An attacker with admin privileges might try disabling or redirecting diagnostic settings before reading secrets. Alert on **monitoring configuration changes** on the control plane, not only on `SecretGet`. Log retention and destinations are themselves assets to protect.

## 7. Azure Lab: Enabling Auditing Safely

These commands are **for guidance**; reading this lesson executes nothing against Azure. Run only against an approved lab subscription, resource group, and vault; Key Vault and Log Analytics usage can incur costs.

### 7.1. Inspect Vault and Permission Model

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table

VAULT="<approved-lab-vault-name>"
RG="<lab-resource-group>"

az keyvault show \
  --name "$VAULT" \
  --resource-group "$RG" \
  --query "{name:name,uri:properties.vaultUri,rbac:properties.enableRbacAuthorization,publicNetworkAccess:properties.publicNetworkAccess}" \
  --output json

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --resource-group "$RG" \
  --query id --output tsv)
~~~

**`az keyvault show`** is a control-plane query, not a `SecretGet`. You can read vault metadata without having permission to read secret values.

### 7.2. View Categories and Existing Diagnostic Settings

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json
~~~

Look for **`AuditEvent`** per current capabilities. If diagnostics are already configured, never overwrite, delete, or redirect a destination actively used by your SOC.

### 7.3. Route AuditEvent to Log Analytics

~~~bash
WORKSPACE_RG="<monitoring-resource-group>"
WORKSPACE="<approved-log-analytics-workspace>"

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$WORKSPACE_RG" \
  --workspace-name "$WORKSPACE" \
  --query id --output tsv)

az monitor diagnostic-settings create \
  --name "kv-audit-lab" \
  --resource "$VAULT_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'

az monitor diagnostic-settings show \
  --name "kv-audit-lab" \
  --resource "$VAULT_ID" \
  --output json
~~~

Run this only if the lab vault lacks a diagnostic setting of that name and the operator holds sufficient permissions. CLI syntax, flags, and diagnostic modes vary by version; verify with CLI help and Portal. You can target Storage or Event Hubs instead per policy. **Ingestion has latency**: do not assume auditing is broken simply because an event hasn't appeared within a few seconds.

### 7.4. Generate Test Activity Using a Dummy Secret

Use an authorized identity and a dummy secret with value **`DEMO_ONLY`**, never a production key:

~~~bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "lab-audit-demo" \
  --query "{id:id,enabled:attributes.enabled}" \
  --output json
~~~

Even when filtering output to metadata, `show` performs a **data-plane Get** returning the value to the CLI before formatting output. Therefore never run it on real secrets “just to test”. You can also test with an unauthorized lab identity to generate denied events under an owner-approved plan.

### 7.5. Prepare Log Query Permissions

An operator granted workspace read access should confirm:

- Diagnostic settings are enabled and pointing to the **right workspace**.
- Logs and schemas appear in the chosen table.
- Retention and table-level/RBAC permissions are configured.
- Ability to query Azure Activity Log and IAM changes.
- Test app emits safe correlation and status telemetry.
- Logs contain zero secret values, tokens, or full Authorization headers.
- Do not delete newly created diagnostic settings/logs during lab cleanup if retention policy prohibits it.

## 8. AzureDiagnostics, Resource-Specific Tables, and Schemas

Key Vault `AuditEvent` logs land in **`AzureDiagnostics`** (shared table) or a resource-specific table such as **`AZKVAuditLogs`** depending on diagnostic configuration. Table and column names vary by mode, resource type, and version.

### 8.1. Explore AzureDiagnostics

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| take 10
~~~

Then inspect the schema:

~~~kusto
AzureDiagnostics
| getschema
~~~

### 8.2. Explore the Resource-Specific Table (If Enabled)

~~~kusto
AZKVAuditLogs
| where TimeGenerated >= ago(1h)
| take 10
~~~

**Do not run on a workspace lacking this table.** If the query throws table-not-found, check diagnostic mode and destination rather than assuming the vault had zero access.

### 8.3. Attributes to Investigate

| Field group | Meaning | Warning |
|---|---|---|
| `TimeGenerated` | Event timestamp | Ingestion delay and UTC |
| `ResourceId` / `_ResourceId` | Target vault | Filter to exact vault to avoid mixing |
| `OperationName` | `SecretGet`/`SecretList`/`SecretSet`... | Naming varies by schema |
| `ResultType`/`ResultSignature`/status | Success/403/404/429... | Inspect actual fields |
| `CallerIPAddress` | Source IP behind NAT/proxy | Not necessarily the end user's IP |
| Identity claims, `oid`/`appid` | Principal calling data plane | May be absent in some records |
| `RequestUri` | Secret path | Sensitive metadata |
| Correlation/request ID | Investigation join key | Not all layers share the same ID |
| Duration/latency | Performance | Separate client vs. server timings |

Illustrative **lesson-defined normalized JSON** (not an official schema):

~~~json
{
  "timeUtc": "2026-11-20T04:30:00Z",
  "vault": "kv-orders-prod-example",
  "operation": "SecretGet",
  "statusCode": 403,
  "result": "Forbidden",
  "principalId": "example-principal-object-id",
  "callerIp": "198.51.100.20",
  "requestId": "example-request-id"
}
~~~

Fields such as **URI, IP, secret name, and identity** must still be protected even though the secret value itself is absent from audit logs.

## 9. KQL Queries for Data-Plane Auditing

The following queries target **`AzureDiagnostics`** when matching columns exist. For resource-specific tables, inspect the schema first and adjust table/field names rather than swapping table names blindly.

### 9.1. Operation Breakdown Over 24 Hours

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| summarize Requests = count() by OperationName
| order by Requests desc
~~~

### 9.2. Outcomes and Source IPs

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Result = strcat(
    tostring(column_ifexists("ResultType", "")), " ",
    tostring(column_ifexists("ResultSignature", "")))
| extend Caller = tostring(
    column_ifexists("CallerIPAddress", ""))
| summarize Requests = count() by OperationName, Result, Caller
| order by Requests desc
~~~

`ResultType` may hold text or codes; if you need a numeric HTTP status, verify the column in a real event. **Never treat status text alone as a probability or risk score.**

### 9.3. Hourly Request Spikes

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(7d)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| summarize Calls = count()
    by bin(TimeGenerated, 1h), OperationName
| order by TimeGenerated asc
~~~

This chart helps correlate deployments, scale-outs, and rotation schedules. A spike post-deployment can be normal; a spike from a new principal without a change ticket warrants investigation.

### 9.4. Filter for 401/403 Indicators

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Outcome = strcat(
    tostring(column_ifexists("ResultType", "")), " ",
    tostring(column_ifexists("ResultSignature", "")))
| where Outcome has_any ("Forbidden", "Unauthorized", "401", "403")
| project TimeGenerated, ResourceId, OperationName,
          Outcome, CallerIPAddress
| order by TimeGenerated desc
~~~

This is a text-based investigative filter. If status sits in another numeric column, update the query to use the actual field name. Never conclude “zero 403s” simply because your schema doesn't emit the string `Forbidden`.

### 9.5. Track a Specific Secret When `requestUri_s` Exists

~~~kusto
let TargetSecret = "orders-payment-api-key";
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Path = tostring(
    column_ifexists("requestUri_s", ""))
| where Path has TargetSecret
| project TimeGenerated, OperationName, Path, ResultType
| order by TimeGenerated desc
~~~

**If `Path` is blank**, the table may lack `requestUri_s` or store it differently. Inspect the schema; an empty query result does not prove the secret was never read.

### 9.6. Inspect Caller Principal Conditionally

Claims may appear as dedicated columns or inside JSON/dynamic fields. If your workspace uses `identity_claim_oid_g`, explore with:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Principal = tostring(
    column_ifexists("identity_claim_oid_g", ""))
| summarize Calls = count() by Principal, OperationName
| order by Calls desc
~~~

If `Principal` is blank across most events, **do not conclude anonymous access**. Check the equivalent identity column in your actual schema and client auth context.

## 10. Activity Log and Role Assignment Events

**`AzureActivity`** exists in Log Analytics only if the Activity Log is routed to the workspace. Otherwise, inspect the Azure Portal Activity Log or your configured destination.

### 10.1. Key Vault Resource Changes

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where ResourceProviderValue =~ "MICROSOFT.KEYVAULT"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

### 10.2. Azure RBAC Role Assignment Changes

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where OperationNameValue has "roleAssignments"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

Role assignments usually belong to **`Microsoft.Authorization`** and may be logged at scopes above the vault. Filtering only by the Key Vault provider **misses IAM changes**. Inspect all relevant scopes: subscription, resource group, vault, or secret.

### 10.3. Building an Evidenced Timeline

~~~text
04:05 UTC  Role assignment created for principal X
04:06 UTC  SecretList from principal X
04:07 UTC  SecretGet for secret Y
04:09 UTC  Partner API anomaly observed
04:15 UTC  SOC acknowledges alert
~~~

This is a hypothetical example. Never assume two events occurring close together prove causality: verify **principal ID, role scope, timestamps, log ingestion lag, request details, and partner telemetry**.

### 10.4. Never Infer Everything from a Single IP

A `CallerIPAddress` may be a shared NAT/firewall egress across many pods or instances. An unfamiliar IP may be legitimate after a workload shifts VNet/NAT during deployment; a familiar IP can still be abused by an attacker on a compromised host. Always correlate IPs with identity, service, operation, timestamp, and network telemetry.

## 11. Correlating End-to-End Evidence: WHO–WHAT–WHEN–WHERE–RESULT

An investigator should never rely on a single role-assignment screenshot or a single 403 line. Build a structured table:

| Question | Evidence to gather |
|---|---|
| **WHO** | Principal object ID, app/client ID, tenant, credential source |
| **WHAT** | `SecretGet`/`List`/`Set`/`Delete`, secret name/version where appropriate |
| **WHEN** | UTC timestamps, token validity, ingestion delay |
| **WHERE** | Vault resource ID, region, caller IP/NAT, network route |
| **RESULT** | Final HTTP status, service error code, request ID, latency |
| **WHY** | Deployment, startup, refresh, approved rotation, or anomalous activity |
| **FOLLOW-ON** | Whether the Partner API used the key or data leaked |

### 11.1. One HTTP Request Across Multiple Layers

~~~mermaid
sequenceDiagram
    participant U as User/Job trigger
    participant APP as Java Orders API
    participant EN as Entra ID
    participant KV as Key Vault
    participant P as Partner API
    U->>APP: Business call, traceId A
    APP->>EN: Acquire token (if needed)
    EN-->>APP: Access token
    APP->>KV: GET secret, dependency span B
    KV-->>APP: Status + x-ms-request-id C
    APP->>P: Business API using secret
    P-->>APP: Partner response
    APP-->>U: Business outcome
~~~

The HTTP request's trace ID, Key Vault's request ID, and Entra token issuance IDs **do not have to match**. Application telemetry should capture **service dependency, UTC timestamp, sanitized secret alias, operation, status, latency, and request ID** to correlate across layers by time and identity.

### 11.2. Key Vault Sees the App Principal, Not Always the End User

If Orders API uses **one managed identity** to read secrets, Key Vault `AuditEvent` reflects the app principal, not individual API callers. A single `SecretGet` at startup can serve thousands of user requests via cache. Tracing back to an end user requires **application traces** with data minimization—never try to infer end users from Key Vault logs.

### 11.3. Baseline-Driven Anomaly Detection

Build baselines around:

- Vault and secret name/classification.
- Approved principals/managed identities.
- Operation types: `SecretGet` vs. `SecretList` vs. `SecretSet`/`Delete`.
- Expected network/IP/VNet sources.
- Operating hours, timezones, and rotation windows.
- `GET` counts during startup, scale-out, and refresh.
- Deprecated versions/secrets no longer in use.

A `SecretGet` spike after scale-out may be benign; `SecretList` from a workload that only ever needs `Get` by name is suspicious. **Never classify solely by raw request count.**

## 12. Diagnosing HTTP 401: Authentication, Tokens, and Bearer Challenges

### 12.1. A 401 Is Not Always an Incident

Some Key Vault clients use **challenge-based authentication**. The initial request can receive HTTP **401** with **`WWW-Authenticate`**, after which the SDK acquires the matching token and retries successfully. Thus, **a single 401 in a dependency trace does not prove the app is broken or under attack**. Inspect the **final outcome**, request sequence, SDK version, and credential acquisition timing.

### 12.2. Root Causes to Distinguish

- Token expired or clock skew invalidated validity.
- Access token targets the wrong Key Vault resource/audience.
- App targets the wrong tenant.
- Managed identity is disabled or unavailable in the runtime.
- User-assigned identity configured with the wrong **client ID**.
- `DefaultAzureCredential` picked an environment credential leftover from CI/dev.
- AKS Workload ID issuer/subject/audience federation mismatch.
- Proxy/TLS/network blocked token acquisition from Entra.
- Outdated client library or broken auth handshake.

### 12.3. 401 Runbook

1. Identify **which service returned 401**: Key Vault or the partner/payment API.
2. Capture status, service error code, request ID, timestamp, and trace ID; never store raw JWTs.
3. Verify where Java runs: local, App Service, VM, Container Apps, or AKS.
4. Check which credential provider the SDK actually selected.
5. Verify principal/client/tenant IDs against approved config rather than trusting environment variable names alone.
6. Confirm managed/workload identity is enabled and properly bound.
7. Check token scope/resource if constructing a custom `TokenCredential` (normally handled by SDK).
8. Check clocks, proxies, DNS/TLS, and token endpoints.
9. If a 401 challenge is followed by a 200 `Get`, do not file an incident on the challenge alone.
10. Once authentication passes, proceed to **authorization** if 403s remain.

### 12.4. Never Debug by Logging Tokens

Access/bearer tokens are credentials. Never paste full tokens into Jira, chat, Git, Java exceptions, browser consoles, or Application Insights custom dimensions. If you must inspect claims during an investigation, use approved channels/tools, minimize data, and enforce strict retention.

## 13. Diagnosing HTTP 403: RBAC, Access Policies, or Networking?

### 13.1. 403 Is the Most Common Error Class

**Forbidden** can stem from several distinct causes:

| Category | Example | What to inspect |
|---|---|---|
| Data-plane RBAC | App lacks **Key Vault Secrets User** | Role/scope and permission model |
| Access policy | Vault uses legacy access policies and app lacks `Get` | Vault access policy list |
| Wrong principal | Role granted to managed identity A, app runs as B | Actual object ID / client ID |
| Wrong scope | Role granted on another vault or resource group | Full resource IDs |
| Pending propagation | Role was just assigned | Assignment audit and elapsed time |
| Network restriction | Public firewall/IP/VNet/Private Endpoint rule blocks access | Error details, DNS, routes |
| Disabled secret/version | Secret lifecycle blocks reading | Secret properties and service error |
| Different authorization boundary | Different vault/tenant/config than intended | Endpoint, subscription, tenant |

Some network restrictions return HTTP 403, so **never look at a 403 and immediately grant Owner**.

### 13.2. Ordered Runbook

1. Capture the **final HTTP response**, sanitized Key Vault error code/message, and request ID.
2. Verify **vault URI** and tenant/environment.
3. Verify token principal; does it match the app's managed identity?
4. Check **`enableRbacAuthorization`** and the vault's access policy mode.
5. If using RBAC, check **Key Vault Secrets User** at the right vault/secret scope.
6. If using legacy access policies, check **`get`** and **`list`** independently; `Get` does not require `List`.
7. Inspect public network access, firewall rules, allowed networks/IPs, and Private Endpoint approval.
8. From the actual host/pod, test DNS and network reachability to the vault FQDN.
9. If a role was just assigned, wait per runbook propagation guidance and retest with the exact principal.
10. Check secret name/version and lifecycle status.
11. Correlate Key Vault audit events with Azure Activity Log role/network edits.
12. After fixing, verify with a **demo secret** without printing its value.

### 13.3. Read-Only Azure CLI RBAC Checks

~~~bash
VAULT="<approved-vault-name>"

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --query id --output tsv)

az keyvault show \
  --name "$VAULT" \
  --query "{rbac:properties.enableRbacAuthorization,publicNetworkAccess:properties.publicNetworkAccess}" \
  --output json

az role assignment list \
  --assignee "<application-principal-object-id>" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
~~~

**Never run role assignment lookups with placeholders** or an object ID guessed from an app name. Read-only IAM inspection still requires IAM read permissions; lacking permission to list assignments does not prove no role exists.

### 13.4. App Role and User Role Are Two Different Things

A developer may hold **Secrets Officer** to create lab secrets, yet Orders API **does not run as the developer's identity** in production. App Service system-assigned identities, user-assigned identities, and AKS Workload IDs are distinct principals needing their own role assignments.

### 13.5. Permission Scope and Propagation

Roles at subscription or resource group scope create a wider blast radius; roles at vault scope (or secret scope where supported) are narrower. Revoking a role during an incident can take time to propagate across every access path. Pair revocation with network containment, credential rotation, and log monitoring to confirm access is truly cut off.

## 14. 404, 429, and Other Operational Errors

### 14.1. 404: Wrong Name/Version or Lifecycle State

A **404** can occur due to:

- Wrong vault URI or secret name.
- Secret never created or already deleted.
- App pinning a version ID that no longer exists.
- Secret unavailable due to lifecycle/API state.
- An app wrapper translating a different error into a “not found” message.

Runbook:

1. Verify the vault URI for the target environment.
2. Verify the exact secret name in config.
3. Check version-pinned vs. versionless fetch.
4. Check soft-delete/recovery state using an authorized admin identity.
5. Check latest version `enabled`/`notBefore`/`expiresOn`.
6. Never auto-create an empty secret or hardcode a fallback when `Get` fails.
7. If recovery is required, follow secret owner approvals and auditing.

**Never assume disabled/expired always returns 404**; error types vary. Read the actual service error code.

### 14.2. 429: Throttling

Key Vault enforces limits by operation, tier, and scope. Common triggers:

- Calling `SecretGet` on every HTTP request instead of caching.
- Hundreds of instances restarting simultaneously and fetching en masse.
- Rotation/inventory jobs calling `LIST`/`GET` excessively.
- Compounding SDK retries × app retries × gateway retries.
- Too many unthrottled workloads sharing a single vault.

Mitigations:

1. Measure requests/sec by operation and principal.
2. Honor HTTP status and `Retry-After` headers when present.
3. Use exponential backoff + jitter, bounded concurrency, and retry budgets.
4. Cache secrets under a **policy-approved TTL and rotation strategy**.
5. Never call Key Vault from liveness probes.
6. Scale/partition vaults per real quotas and baselines—never “grant Owner”.
7. Alert when sustained 429s block app startup.

### 14.3. 5xx and Timeouts

- 5xx errors can reflect transient service or dependency issues.
- Timeouts/DNS/TLS errors can occur in app networking, Private Endpoints, or proxies before ever reaching Key Vault.
- A request that never reaches Key Vault **will not emit a data-plane audit event**.
- Never assume “no `AuditEvent` = no request”; it may have failed upstream of the data plane or logs may be delayed/dropped.
- Check Azure Service Health, client telemetry, DNS/firewall traces, and log ingestion.

### 14.4. Partner API Errors Differ from Key Vault Errors

~~~text
Key Vault GET = 200
Orders API caches key version V1
Partner API = 401 Unauthorized
~~~

Here **Key Vault authentication succeeded**, while the partner key may be revoked or mismatched. Check **partner credential rotation**, app caches, and downstream auth—do not touch Key Vault RBAC.

## 15. Private Networking: Firewalls, Private Endpoints, and DNS

### 15.1. Key Vault FQDN Never Changes

Clients continue calling:

~~~text
https://<vault-name>.vault.azure.net/
~~~

With a Private Endpoint, private-environment DNS must resolve the hostname onto the private network per configuration. Key Vault's Private DNS zone is typically **`privatelink.vaultcore.azure.net`**.

**Never replace the vault URL with a raw private IP** and never disable TLS hostname verification.

### 15.2. Azure App Service VNet Integration

- **VNet Integration** handles outbound access from App Service into the VNet.
- **Key Vault Private Endpoint** is the private endpoint exposing the vault.
- **App Service Private Endpoint** handles inbound private access to the app; it does not replace outbound VNet Integration.
- DNS, firewalls, route tables, and NSGs must all align.
- Entra token acquisition has different network paths/requirements than Key Vault data-plane traffic.

### 15.3. AKS Networking

In AKS:

- Pod outbound DNS must resolve the vault FQDN properly.
- CNI/network policies, NAT/firewalls, and route rules can block egress.
- ServiceAccounts/Workload IDs provide identity separately; **network reachability does not grant RBAC**.
- A node/pod can use multiple egress IPs, so correlate `CallerIPAddress` in audits with your NAT topology.

### 15.4. Network Diagram

~~~mermaid
flowchart LR
    POD["App Service / AKS<br/>Java workload"] --> DNS["VNet DNS resolver"]
    DNS --> PE["Key Vault Private Endpoint<br/>private IP"]
    PE --> KV["Key Vault"]
    POD --> ID["Microsoft Entra token endpoint"]
    AUTH["Key Vault data-plane RBAC"] --> KV
    LOG["Key Vault AuditEvent"] --> SOC["Log Analytics / SOC"]
    KV --> LOG
~~~

### 15.5. DNS/Network Checklist

1. Confirm vault public network access and firewall policy.
2. From the **actual host/pod**, resolve **`vault-name.vault.azure.net`**.
3. Check Private DNS zone links and forwarding resolvers.
4. Check Private Endpoint connection approval/status.
5. Check routing, firewalls, NSGs, and egress proxies.
6. Verify TLS certificate validation and hostname.
7. Use sanitized dependency traces to tell whether errors occur before or after an HTTP response.
8. Once networking passes, verify identity and data roles.
9. Never open global public network access just to work around a DNS issue.

### 15.6. “Trusted Services” Does Not Mean Every Workload Is Allowed

Certain Azure services have documented bypass/exception support per configuration, yet you should never assume every Azure-hosted app counts as a trusted service. Check official eligibility lists/conditions and prefer private connectivity per policy.

## 16. Java SDK: Reading Secrets and Logging Status Safely

A Java application typically pairs **`com.azure:azure-security-keyvault-secrets`** with **`com.azure:azure-identity`**.

### 16.1. Maven Dependencies

~~~xml
<dependencies>
  <!-- Use Azure SDK BOM or pin versions appropriate for your project. -->
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
~~~

This is a **POM fragment** requiring an Azure SDK BOM/explicit versions, JDK, and project build configuration. Do not treat placeholders as a tested build.

### 16.2. Java 17 SecretClient

~~~java
package com.example.orders.security;

import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class KeyVaultAuditDemo {
    private KeyVaultAuditDemo() {}

    public static void main(String[] args) {
        String vaultUrl = requiredEnv("KEY_VAULT_URL");
        String secretName = requiredEnv("SECRET_NAME");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(credential)
            .buildClient();

        try {
            KeyVaultSecret secret = client.getSecret(secretName);
            String value = secret.getValue();

            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                    "Required secret unavailable");
            }

            // Use value in an appropriate server-side component.
            // NEVER log, print, or serialize the secret value.
            System.out.println(
                "Secret dependency available; value not displayed.");

        } catch (HttpResponseException error) {
            int status = error.getResponse() == null
                ? -1 : error.getResponse().getStatusCode();

            // Status + sanitized correlation only;
            // NEVER print a body containing credentials.
            System.err.println(
                "Key Vault dependency failed; status=" + status);
            throw error;
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required environment variable " + name);
        }
        return value;
    }
}
~~~

This demo succeeds while **never displaying the secret value**. Both environment variables hold only the vault URL and secret name, never credentials. The SDK can also throw token-acquisition or transport exceptions; production code must handle them explicitly without dumping raw error bodies.

### 16.3. What Production Must Add

- **Singleton `SecretClient`/`TokenCredential`** via dependency injection rather than creating clients per request.
- Timeouts, cancellation, and bounded SDK retries for 429/5xx per policy.
- Sanitized structured logs with dependency name, status, operation, duration, and correlation.
- Secret caching/refresh aligned with the rotation contract—never infinite caching.
- Alerts when `getSecret` fails at startup; explicit readiness semantics.
- Never enable SDK HTTP wire logging for **request/response bodies** or headers containing secrets/tokens.
- Never place secret values in exception messages, thread names, metric labels, config dumps, or traces.
- Test user-assigned identities/AKS workload federation where used.
- Distinguish Key Vault 401s from partner API 401s via distinct OpenTelemetry service names.

### 16.4. Java Strings and Memory

`SecretClient` returns secret values as a **`String`**. Java `String`s are immutable with no guaranteed immediate zeroization. Minimize copies, shorten lifetime, prevent crash dumps, and avoid serialization; wherever an Azure service supports Entra/managed identity directly, **avoid static secrets altogether**.

### 16.5. Diagnosing `DefaultAzureCredential`

Locally, the SDK may pick developer tooling credentials; on Azure, it uses managed identity. **The same code path does not guarantee the same principal.** If leftover environment variables hold service principal credentials, the credential chain may pick an unintended identity depending on SDK version.

For sensitive production workloads, consider explicit **`ManagedIdentityCredential`** or **`WorkloadIdentityCredential`** per runtime, pin SDK versions, and verify the actual principal. When using a user-assigned identity, verify the exact **client ID** and avoid confusing it with the **principal object ID** used for role assignments.

### 16.6. Never Self-Escalate Privileges in Exception Handlers

Anti-pattern:

~~~java
// WRONG: attempting to edit RBAC or switch to an admin credential
// when SecretGet returns 403, then retrying forever.
~~~

A runtime reader must never hold permissions to alter role assignments. Modifying roles belongs to platform/IAM teams under approval, auditing, and rollback—not app self-healing logic.

## 17. When Auditing Detects Anomalous Secret Reads

An alert might look like:

~~~text
Alert: successful SecretGet spike
Vault: kv-orders-prod-example
Time: 02:05–02:20 UTC
Principal: new service-principal
Caller IP: unexpected egress
Operation: SecretGet and SecretList
~~~

This is a hypothetical example; the SOC must compare against deployment allowlists, rotation windows, and network inventories. A **successful `Get`** proves an authorized read was served, not automatically that data was exfiltrated.

### 17.1. Response Tiers

| Situation | Initial Response |
|---|---|
| Known app scale-out, startup `GET` surge | Cross-check deployments, baselines, and caching |
| New role + `GET` from principal without a change ticket | Open a security investigation |
| Sensitive secret `GET` from an unapproved principal | Prioritize containment + incident |
| Bulk `SecretList` from a workload that only `Get`s by name | Investigate intent and potential credential misuse |
| Partner key found in public logs/repository | Treat as potential credential exposure; rotate/revoke |
| Diagnostic settings disabled near `GET` activity | High-severity telemetry tampering signal |
| Logs show 403s with zero 200s | Likely probing or misconfiguration; verify |

**Severity** must reflect data classification, evidence, blast radius, and business impact—not one fixed threshold across all vaults.

### 17.2. Triage Procedure

1. **Confirm alert:** query actual logs; check UTC times, ingestion lag, resource ID, status, and operation.
2. **Verify principal:** object ID, app ID, tenant, owner, and approved identity inventory.
3. **Correlate change events:** deployments, role assignments, vault firewalls, access policies, and diagnostic setting edits.
4. **Correlate networking:** caller IP/NAT, VNet, Private Endpoint, and egress route.
5. **Scope exposed secrets:** identify which names/versions could have been accessed—never download values just to investigate.
6. **Verify app path:** startup, refresh, inventory job, or business request.
7. **Look for follow-on evidence:** partner API logs, app egress, CI secret scans, anomalous downstream activity.
8. **Assess risk:** is the accessed credential still usable? Which environments/tenants are impacted?
9. **Escalate** per security playbook if a principal or sensitive secret may be compromised.
10. **Preserve evidence and timeline** before making destructive config changes.

### 17.3. What Not to Do

- Never print secret values from the vault to “check if they changed”.
- Never paste request logs or raw tokens into unapproved chat channels.
- Never delete a vault or purge a secret to “erase tracks”.
- Never grant a broader role just to gather investigative context.
- Never jump to conclusions from a single IP alone.
- Never disable monitoring to quiet noisy alerts.
- Never just delete the Key Vault secret while ignoring copies at the partner or in app caches.

## 18. Incident Runbook: Suspected Secret Value Exposure

A credential can leak via repositories, CI logs, client bundles, crash dumps, APM traces, malicious insiders, or over-privileged Key Vault principals. **Even if `AuditEvent` logs look clean, a secret may have leaked from an earlier copy.**

### 18.1. Response Objectives

- **Contain:** cut off unauthorized access paths and shrink blast radius.
- **Preserve evidence:** retain audit, identity, role/network, and app/partner logs.
- **Revoke:** make the old credential unacceptable to the target system.
- **Rotate:** issue a new credential and migrate apps safely.
- **Verify:** confirm workloads use the new key and attackers can no longer use the old key.
- **Learn:** fix root cause, strengthen detection, and add tests.

### 18.2. Response Timeline

~~~mermaid
flowchart TD
    DET["Detect suspected exposure"] --> TRIAGE["Validate alert + classify secret"]
    TRIAGE --> EVID["Preserve logs, trace, change timeline"]
    EVID --> CON["Contain principal/network access"]
    CON --> NEW["Issue replacement credential at partner"]
    NEW --> KV["Set new Key Vault version"]
    KV --> CAN["Canary app uses new version"]
    CAN --> DEC{"Partner auth + business SLO OK?"}
    DEC -->|No| FIX["Repair/controlled rollback"]
    DEC -->|Yes| ROLL["Roll out all app instances"]
    ROLL --> REVOKE["Revoke old partner credential"]
    REVOKE --> VERIFY["Verify no unauthorized use, audit"]
    VERIFY --> RETRO["Post-incident review + tests"]
~~~

**Exact ordering depends on urgency:** for an actively exploited credential, you may need to revoke immediately before a canary is ready, accepting downtime. When dual-key support exists, a controlled cutover reduces outage duration. The security incident commander decides based on risk.

### 18.3. Containing Permissions and Networking

- Disable/quarantine the compromised app deployment or workload identity federation where appropriate.
- Revoke overly broad roles or access policies.
- Disable static credentials and rotate service-principal secrets/certificates if exposed.
- Tighten network paths, firewalls, and Private Endpoint access per policy.
- Check permissions at parent scopes (resource group/subscription) and inherited roles.
- Cross-check Entra sign-ins and app/infrastructure changes.
- **Never assume removing a role takes effect instantaneously** due to token caches and propagation.

### 18.4. Rotation at the Target System Is Decisive

Suppose Key Vault stores a payment partner API key:

1. Generate a new key **in the partner system**.
2. Confirm the new key is active per partner API/token rules.
3. Write the new key as a **new secret version in Key Vault**.
4. Update app caches/version references via controlled rollout.
5. Test a demo/canary transaction with the new key without logging the raw key.
6. Revoke the old key **at the partner**.
7. Watch partner 401/403s/anomalous usage and vault `Get` logs.
8. Confirm no instances retain old cached credentials past approved retention.
9. Scrub copies in logs, source history, snapshots, and backups per policy.

**Deleting or disabling a secret in Key Vault does not invalidate a key value already copied externally.** If an attacker already holds the API key, deleting it from the vault alone will not stop them from using it at the partner.

### 18.5. When It Is a Database Password

For legacy DB passwords:

- Change the password at the database/identity authority.
- Update the Key Vault version.
- Coordinate DB connection pool lifetimes and required restarts.
- Expect already-open connections to stay alive depending on DB auth/session semantics.
- Audit SQL/Azure RBAC permissions and active connections.
- Migrate to Entra managed identity where supported to curb password sprawl.

### 18.6. When It Is a Certificate / Private Key

- Check certificate issuance/CA policies and private key exportability.
- If the private key leaked, revoke/reissue the certificate and update trust/consumers.
- With non-exportable Key Vault Keys/HSMs, unusual signing does not mean the private key was exported; inspect **key operation audits**, service permissions, and cryptographic usage.
- Never apply the exact same playbook across Secrets, Keys, and Certificates when trust chains differ.

### 18.7. Proving Incident Closure

Saying “created a new version” is not enough. Require evidence that:

- All active workloads use the new credential.
- The partner rejects the old credential.
- Anomalous network/identity permissions are contained.
- Vault/partner logs show zero unauthorized usage across an observation window.
- Monitoring is restored and protected.
- Secret-bearing artifacts were remediated per policy.
- Incident timeline, root cause, and corrective actions are recorded and reviewed.

## 19. Runbook: App Cannot Read Secret After Deployment

Another operational incident: a new release on App Service hits **HTTP 403**, and checkout returns 503.

### 19.1. Dependency-Chain Diagnosis

~~~text
Application startup
   |
   +-- Azure Identity TokenCredential?
   |      +-- Tenant / client ID / managed identity source
   |
   +-- Key Vault reachability?
   |      +-- Vault FQDN / DNS / firewall / private endpoint
   |
   +-- Key Vault authorization?
   |      +-- Permission model / principal / role scope
   |
   +-- Secret lifecycle?
   |      +-- Name / version / enabled / expiry
   |
   +-- Application binding?
          +-- Cache / env / dependency injection / partner key
~~~

### 19.2. Non-Destructive Procedure

1. Check app health/status prior to the deployment.
2. Confirm the error comes from **Key Vault**, not the partner.
3. Use sanitized logs and Key Vault data-plane audits to capture status and timestamps.
4. Match the App Service/AKS identity against role assignments.
5. Verify tenant and vault URI for the target environment.
6. Check VNet/private DNS/firewall from the corresponding container/host.
7. Check last successful secret retrieval and version metadata.
8. Check role propagation if permissions were just granted.
9. Never use production secret values during manual diagnostics.
10. Roll back the binary/config or feature-flag off the dependent flow if safe.
11. Once fixed, verify with a minimal allowed `SecretGet`; monitor dependency p95 and availability.
12. Add a regression test or infrastructure assertion.

### 19.3. Fail-Fast or Last-Known-Good?

| State | Acceptable behavior |
|---|---|
| New instance that never fetched the credential | Do not serve secret-dependent routes; fail startup/readiness |
| Running instance holding a valid cached key | May continue within a policy-approved stale window |
| Suspected compromise / revoked credential | Fail closed; never retain a stale cached key for availability |
| Rotated to new version but partner fails | Canary rollback / dual-key per runbook |
| Brief Key Vault 429 | Backoff/jitter; never `GET` per request |
| Extended Key Vault outage | Escalate, execute DR/runbook and risk decision |

Never hardcode a backup key into a JAR or silently borrow a dev credential to rescue production.

### 19.4. Readiness vs. Liveness

Kubernetes/App Service health probes must never call **Key Vault `Get` every few seconds**. During a vault outage, liveness-triggered mass restarts unleash a storm of `GET`s and 429s. Readiness should reflect whether the app holds valid config/credentials to serve traffic; liveness should reflect whether the process is alive and not deadlocked.

## 20. Secret Rotation and Version Auditing

### 20.1. Standard Rotation Sequence

~~~text
V1 active at partner + Key Vault
→ V2 created at partner
→ Key Vault Set creates V2 secret version
→ Canary uses V2 (optionally pinned)
→ Validate partner authentication and business outcomes
→ Roll out V2 to all instances
→ Revoke partner V1
→ Audit, close rotation ticket
~~~

Audit timelines may show `SecretSet`/`SecretGet`/`List` or metadata operations depending on SDK and calls. However, **`SecretGet` from an app does not prove its in-memory cache switched versions**; emit non-sensitive version-metadata telemetry from the app per policy.

### 20.2. Versionless vs. Version-Pinned

- **Versionless `GET`** fetches the active version per service semantics, though app caches/refresh cycles may hold the old value.
- **Version-pinned `GET`** enables reproducible rollouts; apps pinned to V1 will not move to V2 automatically.
- **Secret `expiry`/`notBefore`/`disabled`** affect availability; inspect metadata carefully.
- Never set `ExpiresOn` assuming the partner rotated the key.
- With App Service Key Vault references or Azure App Configuration references, understand their **distinct refresh/cache semantics**.

### 20.3. Logging Rotation Without Exposing Values

Metadata logs can look like:

~~~json
{
  "event": "SECRET_ROTATION_APPLIED",
  "vaultAlias": "kv-orders-prod",
  "secretAlias": "payment-key",
  "versionHash": "sha256-demo-prefix",
  "result": "SUCCESS",
  "timeUtc": "2026-11-20T05:30:00Z"
}
~~~

This telemetry is illustrative; **`versionHash`** is not a hash of the secret value, just a masked/hashed representation of the **version ID** where needed. Never log plaintext secrets, signed JWTs, tokens, partner headers, or key material.

### 20.4. Audit Shows `Set`, Yet the App Still Fails?

A new Key Vault version may exist, yet:

- The partner has not activated the key.
- The app still pins the old version.
- Some instances still cache the old secret.
- Vault roles/networking changed and blocked `Get`.
- The new version is disabled or has a future `notBefore`.
- The HTTP client initialized once with the old `Authorization` header.
- The downstream partner API rejects another permission unrelated to the API key.

Therefore, rotation verification must track **vault audits, app configuration, and partner API outcomes** together.

## 21. Soft-Delete, Recover, Purge, and Evidence Preservation

Key Vault provides **soft-delete** and optional **purge protection** per vault type/policy. Understand:

| Action | Meaning | Audit / incident consideration |
|---|---|---|
| Delete Secret | Secret enters deleted state per service lifecycle | May need recovery; never delete casually during an incident |
| Recover | Restores if within retention and authorized | Requires approval and auditing |
| Purge | Permanently deletes if allowed | Irreversible; may be blocked by purge protection |
| Rotate | Issues new credential/version and migrates consumers | Does not delete the partner's copy |
| Disable | Prevents using a version per policy | Does not revoke the key on external systems |
| Backup/restore | Per Key Vault API and constraints | Never treat diagnostic logs as a secret backup |

**Never run `Purge` in labs or production** just to reuse a name. Deletion and recovery are sensitive data-plane changes requiring approvals and audits.

### 21.1. Evidence Preservation

During a security incident:

- Preserve audit records, Activity Logs, identity logs, and relevant app/partner logs.
- Export logs under an approved chain of custody, computing file hashes if required.
- Avoid uncontrolled sharing of potentially sensitive names, URIs, and IPs.
- Never shorten retention or delete settings before the incident commander approves.
- Audit who can read logs; log readers are often privileged too.
- Enforce compliance/regulatory holds where applicable.

### 21.2. Read Secrets Cannot Be “Unsent”

Anyone with `Get` permission may have copied the secret value out. **No Key Vault feature can recall bytes already read by a recipient's machine.** True remediation requires revoking/rotating at the target system and closing all paths to the old copy.

## 22. Detection Engineering: Right Alerts, Fewer False Positives

### 22.1. Do Not Alert on Every `GET`

An app with 100 instances refreshing hourly produces 100 near-simultaneous `GET`s. A deployment can legitimately emit hundreds of `GET`s. Instead of alerting on everything:

- Baseline per vault, principal, operation, and time window.
- Allowlist approved identities and expected access patterns.
- Watch for **new principals** or unexpected caller networks.
- Track **`GET`/`LIST` ratios** and rate spikes.
- Watch **write/delete/purge operations** outside change windows.
- Correlate role assignments with subsequent data-plane access.
- Alert on diagnostic setting edits as potential tampering.

### 22.2. Hypothetical Detection Rule

~~~text
Trigger:
  New principal not in approved inventory
  AND successful SecretGet against production vault
  AND no active deployment/rotation change ticket
Window:
  15 minutes
Severity:
  High if secret is classified critical
Actions:
  Create security incident
  Preserve Key Vault / Activity / Entra logs
  Verify principal and network
  Request containment approval
~~~

This is an **example rule**, not a deployed Azure Alert Rule. Production detections require suppressions, exceptions, seasonality tuning, and clear incident ownership.

### 22.3. Failed Access Can Be a Deployment Bug

A surge of 403s after a rolling release often indicates:

- Role assigned to the wrong principal.
- Managed identity not enabled.
- Access policy vs. Azure RBAC mismatch.
- Unpropagated Private DNS.
- App requesting a misspelled secret name.

Include deployment correlation and impacted instance counts in alerts to separate **SRE incidents** from **security probing**.

### 22.4. Alert on Log Pipeline Health

Alert when data-plane auditing drops:

- Diagnostic settings deleted/disabled or destination altered.
- Workspace ingestion stops receiving `AuditEvent` for an unusual duration.
- Event Hubs/Storage exports fail where monitored.
- Log permissions or retention modified without approval.

**Never rely on missing events alone** as proof of log tampering—a vault might simply have zero traffic. Combine with service request metrics, authorized lab heartbeats, and Activity Log changes.

## 23. Managed Identities, Service Principals, and Workload Identities in Audits

### 23.1. Easily Confused Identifiers

| Identifier | Meaning | Used for |
|---|---|---|
| **Tenant ID** | Microsoft Entra directory | Identifying where identities live |
| **Application (client) ID** | Application/client identifier | Selecting a user-assigned managed identity or app |
| **Principal object ID** | Service principal/managed identity object in directory | Azure RBAC role assignments and principal investigation |
| **Resource ID** | Azure ARM path | Identifying the vault/scope carrying a role |
| **Secret name** | Logical secret identifier | `Get`/`list`/`rotate` per application |
| **Secret version** | Version ID | Analyzing rotation and rollback |
| **Key Vault request ID** | Service-side request identifier | Correlating data-plane logs |

Never assign a role to a **client ID** when the tool requires a **principal object ID**, and never confuse a subscription ID with a tenant ID.

### 23.2. App Service System-Assigned Identity

- Enable the identity on the exact App Service.
- Record its **principal object ID** in inventory and safe IaC outputs.
- Assign **Key Vault Secrets User** at the required scope.
- Confirm the app uses that managed identity rather than an environment service principal.
- Ensure outbound networking reaches the vault.
- When an app is deleted/recreated, **its system-assigned principal can change**; old roles do not automatically transfer to the new principal.
- Historical audits must link both old and new principals for the same logical service name.

### 23.3. User-Assigned Managed Identity

- Standalone Azure resource with both a client ID and a principal ID.
- Workloads with multiple attached identities may require an explicit client ID.
- Never assume the SDK picks the right identity when multiple exist.
- Assign roles to the **actual** user-assigned identity.
- Audit `Get` events reflect the underlying principal, not necessarily a human-readable App Service name.

### 23.4. AKS Microsoft Entra Workload ID

Components to reconcile:

- AKS OIDC issuer.
- Kubernetes `ServiceAccount` namespace/name.
- Federated identity credential subject/audience.
- Entra application/managed identity principal.
- Projected service account token and Azure Identity SDK.
- Key Vault data-plane RBAC on the exact principal.
- Pod DNS/egress to the vault.

When federation fails, token acquisition fails before reaching the data plane; **Key Vault audits may show zero events** because requests never reached the vault.

### 23.5. Service Principal Client Secrets/Certificates

If CI or legacy apps still use service principal credentials:

- Store and rotate credentials via a secret store.
- Never log client secrets, private keys, or tokens.
- Monitor secret expiration and token audiences.
- Migrate to OIDC federation/managed identity wherever supported.
- If compromised, revoke the credential, roles, and downstream credentials per incident plan.

**Rotating an Entra service principal's client secret** differs from **rotating an app-stored Key Vault Secret**. Both may need handling when a principal is compromised.

## 24. Log Permissions and Security Obligations

### 24.1. Audit Logs Require Least Privilege Too

Only authorized roles—security analysts, incident responders, and SREs with a valid need—should query Key Vault audit logs. App runtimes **do not need log-reading access** to operate.

Separate:

- **Vault data reader:** `get` secret values for runtime duties.
- **Vault data manager/rotator:** `set`/`update`/`recover` under approval.
- **Diagnostic setting operator:** configures log export paths.
- **Log reader:** queries workspace or storage audits.
- **Incident commander:** coordinates containment and evidence preservation.

### 24.2. Sensitive Data Inside Audits

Even without plaintext secrets, logs can expose:

- Vault/secret names revealing topology.
- Internal IPs/hostnames.
- Application/principal object IDs.
- URI paths or versions.
- Timing patterns revealing operating hours and rotation schedules.
- User/service principal claims or tenant metadata.

Comply with privacy, retention, access-review, and SIEM-sharing policies. Redact logs before pasting into tickets or shared dashboards.

### 24.3. Never Use Auditing as a “Secret Backdoor”

If a manual debug flag logs full request/response bodies, that is an **information leak**, not legitimate auditing. Never disable SDK redaction/HTTP header sanitation or save HARs/packet captures containing `Authorization` headers without incident approval.

### 24.4. Log Tampering and Evidence Integrity

- Alert on edits/deletions to diagnostic settings.
- Protect workspaces/storage with RBAC, policies, and proper retention.
- Record change tickets/approvals whenever log destinations change.
- Where compliance requires immutable evidence, evaluate immutable storage/legal hold per policy.
- Log who queried/exported data, storage locations, and hashes if required.
- Never manually delete “false positive” records from central logs.

## 25. Defining Security and Operational SLOs/SLIs

### 25.1. Useful SLIs

| SLI | Example measurement | Notes |
|---|---|---|
| **Audit coverage** | % of production vaults with `AuditEvent` diagnostics enabled | Inventory via ARM + diagnostic settings |
| **Successful `Get` rate** | `Get` 2xx / all `Get` attempts | Exclude initial 401 challenges from final failures |
| **Denied request rate** | 401/403s by principal and env | Separate auth, networking, and role |
| **Refresh latency** | Time from rotation until all instances adopt the new version | Requires app telemetry |
| **Time-to-detect** | Suspicious event to alert firing | Factor in ingestion delay |
| **Time-to-contain** | Alert firing to blocking principal/credential | May depend on approvals |
| **Old credential revocation** | Time until partner stops accepting V1 | Requires partner audits |
| **Identity drift** | Runtime identities absent from inventory | IaC + policy validation |
| **Diagnostics freshness** | Time since last event against traffic baseline | Zero traffic is not an error on its own |

### 25.2. Illustrative SLOs

- 100% of production vaults route data-plane audits to an approved destination.
- 99% of Key Vault `Get` calls from the approved Orders API succeed within operating windows, excluding auth challenges.
- 95% of actionable audit events reach monitoring within the organization's target latency.
- 100% of critical rotations record **partner-side revocation evidence**.
- Every production IAM, network, or diagnostic setting edit has a change ticket and audit entry.
- Unapproved principal access triggers a SOC alert within the detection SLO.

**These targets are illustrative policies**, not Azure SLAs. Measure real baselines and define denominators explicitly.

### 25.3. Avoid Misleading Metrics

Never reason:

~~~text
Key Vault SecretGet success = 100%
⇒ All payments are secure
~~~

This inference fails: the partner API might reject credentials, secrets could be copied from app memory, or the app might skip business checks. End-to-end security requires multi-layer verification.

## 26. Capacity and Auditing Costs

### 26.1. Impact of Per-Request `SecretGet`

Suppose Orders API serves **600 requests/s**, calling Key Vault on every request:

~~~text
600 GET/s × 60 × 60 × 24
= 51,840,000 GET/day
~~~

This is a hypothetical calculation, not a quota. It drives up Key Vault operations, latency, throttling, and audit log volume.

With **30 app instances**, each fetching at startup and refreshing **every 10 minutes**:

~~~text
30 instances × 6 fetches/hour × 24 hours
= 4,320 GET/day
~~~

Actual counts vary with startup churn, retries, multiple secrets, token challenges, caching, SDK behavior, and feature calls. Never treat this as an exact billable total.

### 26.2. Monitoring Cost Drivers

| Component | Potential cost drivers |
|---|---|
| Key Vault | Data-plane operations, tier, Key/HSM operations if used |
| Log Analytics | Ingestion volume/tier, retention, queries, plan features |
| Storage archive | Log storage and retrieval |
| Event Hubs/SIEM | Streaming, ingestion, processing |
| Application Insights | Telemetry ingestion, sampling, retention |
| Private Link/Firewall/NAT | Network resources and data transfer |
| Alert rules | Query/rule evaluations and action groups per model |
| App/Rotation workers | Compute, schedulers, retry traffic |

Use rate cards for your **actual region, tier, and date**. Never quote fixed unit prices when rates and quotas change.

### 26.3. Optimize Without Dropping Audits

- Cache secret values for a **security-policy-approved** duration.
- Never call Key Vault on every business request.
- Curb unnecessary inventory `LIST`/`GET` polling.
- Sample **application debug telemetry** per policy, while **never dropping mandatory vault audits**.
- Pick fitting retention tiers and archive policies rather than “turning off `AuditEvent` to save money”.
- Remove duplicate app-layer logs.
- Scope alerts by principal/operation to cut noise and triage costs.
- Separate workload identities/vaults when blast radius is high—raising baseline cost slightly while reducing breach risk.

### 26.4. Measuring Operational Cost per Investigated Incident

An additional metric:

~~~text
Monitoring cost per investigated incident
= (data ingestion + retention + analytics
   + investigation time + corrective work)
  / number of incidents reaching useful conclusions
~~~

Never optimize this ratio by **failing to detect incidents**. Prioritize audit coverage, evidence quality, and time-to-contain.

## 27. Decision Tree for Authentication and Secret Access

~~~mermaid
flowchart TD
    START["Java getSecret failed"] --> SERVICE{"Response from which service?"}
    SERVICE -->|Partner API| PARTNER["Verify partner key/rotation<br/>not Key Vault RBAC"]
    SERVICE -->|Key Vault| HTTP{"HTTP status / transport"}
    HTTP -->|401| ID["Token/tenant/audience<br/>challenge vs final failure"]
    HTTP -->|403| FORB{"Network policy denial?"}
    FORB -->|Yes| NET["Firewall/VNet/private DNS"]
    FORB -->|No| RBAC["Vault permission model<br/>principal ID/role/scope"]
    HTTP -->|404| NAME["Vault/name/version/<br/>deleted/disabled state"]
    HTTP -->|429| THROTTLE["Retry-After/backoff<br/>cache/scale"]
    HTTP -->|5xx| TRANSIENT["Service health/retry budget"]
    HTTP -->|DNS/TLS timeout| ROUTE["Hostname/routing/cert"]
    ID --> FIX["Apply approved fix + safe retest"]
    NET --> FIX
    RBAC --> FIX
    NAME --> FIX
    THROTTLE --> FIX
    TRANSIENT --> FIX
    ROUTE --> FIX
    PARTNER --> FIX
    FIX --> AUDIT["Check app + KV audit<br/>record root cause"]
~~~

**First diagnostic question:** Is the failure at **Key Vault**, **Entra**, **the network**, or the **partner API**? That is the fastest way to avoid fixing the wrong system.

### 27.1. Symptoms and First Checks

| Symptom | First check | What not to do |
|---|---|---|
| Works locally, prod gets 403 | Prod managed identity principal, RBAC, networking | Copy developer secret into prod |
| Multiple 401s followed by 200 | Auth challenge sequence/SDK | Alert every 401 as an attack |
| 403 after enabling Private Endpoint | DNS/VNet firewall | Disable the entire firewall |
| 404 on just one secret | Name/version/deletion state | Auto-create a production secret |
| 429 after scale-out | Startup `GET` burst, cache refresh | Retry endlessly |
| App gets 200 from Key Vault, partner returns 401 | Key rotation/downstream auth | Grant Key Vault Administrator |
| Audit shows zero events | Diagnostic destination/table/ingestion lag, pre-KV network failure | Conclude no requests happened |
| Unknown principal reads secret | Correlate role/network/deploy, classify exposure | Only delete logs or delete the secret |
| Rotation `Set` succeeded, app stays on V1 | Cache/version pinning/app rollout | Assume `Set` equals `revoke` |
| IAM role removed yet activity continues | Token/auth caching, inherited roles, alternate identity | Declare containment complete |

## 28. End-to-End Investigation Lab Using Synthetic Data

Goal: a lab vault, a dummy secret, a data-plane audit destination, two identities (authorized vs. denied), and a Java test app that never prints values.

### 28.1. Scenario A: Success

1. Confirm the vault has `AuditEvent` diagnostics enabled.
2. Identity A holds data-plane **Key Vault Secrets User**.
3. Call Java `SecretClient.getSecret(name)` on the demo value.
4. Log only status, duration, and correlation metadata.
5. After ingestion delay, find `SecretGet` in the workspace.
6. Match principal/operation/result with the app trace.
7. Confirm zero secret values appear in logs.

### 28.2. Scenario B: RBAC Denial

1. Identity B lacks Secret Get permission.
2. Target the same demo vault/secret over the same network path.
3. Call `getSecret` as B and record sanitized status/error code.
4. Query `AuditEvent` for failed access if the request reached Key Vault.
5. Inspect vault permission model and role assignments.
6. Only authorized admins may alter permissions; the app never self-grants.
7. Confirm identity B cannot read the value via any alternative path.

### 28.3. Scenario C: Network Denial

1. In lab only, apply test firewall/Private Endpoint rules per approval.
2. Call from a host outside the allowed network.
3. Record HTTP 403/network timeout errors and DNS behavior.
4. Inspect data-plane logs (if requests reached the service) and network traces.
5. Never switch the vault URL to a private IP or disable TLS.
6. Restore approved network settings.

### 28.4. Scenario D: Wrong Secret Name/Version

1. Call `getSecret` with a non-existent demo name/version.
2. Record sanitized error type and status.
3. Inspect Key Vault `AuditEvent` queries and app dependency traces.
4. Never auto-create secrets or fall back to hardcoded defaults.

### 28.5. Scenario E: Rotation

1. Operator creates demo versions V1 and V2.
2. App tests both versionless and pinned V1 to compare lifecycles.
3. Log version metadata aliases without logging values.
4. Simulate application cache refresh.
5. Link data-plane `Set`/`Get` audits with the change ticket.
6. Test rollback per policy and clean up the lab only with owner approval.

### 28.6. Lab Report Template

| Field | Example value |
|---|---|
| TestCase | Denied SecretGet |
| Resource | kv-audit-lab |
| Principal | lab-identity-B |
| Start UTC | 2026-11-20T08:00:00Z |
| Expected | Denied / no secret disclosure |
| Observed | HTTP 403, sanitized |
| Evidence | Key Vault AuditEvent + app trace |
| Root cause | Missing Get permission |
| Fix | None; expected negative test |
| Secrets in logs? | No |
| Owner | Lab operator |

Use metadata only; never attach demo or production secret values to reports.

## 29. Negative Tests and Staging Drills

| Test | Expected Outcome |
|---|---|
| Identity lacks Secret Get | Cannot retrieve value; denied audit recorded |
| App holds Azure Contributor without data-plane role | Cannot call `Get` |
| RBAC-mode vault with only legacy access policy added | Treated as ineffective |
| Legacy access policy vault with only Data Reader RBAC role | Still denied per active model |
| App Service selects wrong user-assigned client ID | Token/auth failure classified cleanly |
| AKS federation subject mismatch | Token acquisition fails; zero KV events is expected |
| Role on a different resource | Not treated as sufficient permission |
| Newly assigned role | Observe propagation; no infinite retries |
| Network blocks public endpoint | Never bypass firewall to make tests pass |
| Wrong Private DNS | FQDN/TLS routing fails cleanly; never connect by raw IP |
| Wrong secret name | Never auto-create fallback |
| Disabled/expired version | App fails per policy; never reuse revoked cached keys |
| 100 instances start simultaneously | Bounded retries/jitter; vault not overwhelmed |
| One 401 challenge then 200 | Not misclassified as an attack/failure |
| Partner API returns 401 while KV `Get=200` | Debug downstream credential |
| Audit settings disabled | Detection and change audit fire signals |
| Log query table mismatch | Inspect diagnostic mode/schema rather than assuming zero events |
| App error log accidentally contains secret | Scanner catches it; incident process and rotation trigger |
| V1→V2 rotation | Partner revokes V1 and all app instances converge |
| Identity compromised | Containment, evidence preservation, and verification |

Rehearse in **staging/lab**—never intentionally break a production vault, disable monitoring, or test purges on shared resources.

## 30. Decision Table for Common Troubleshooting Scenarios

| Symptom | Initial Classification | Priority Action |
|---|---|---|
| `SecretGet` 200 from approved principal at startup | Likely normal | Match against deployment, rotation window, baseline |
| `SecretGet` 200 from new principal without change ticket | Security suspicion | Audit role changes, principal, network, and partner usage |
| Bulk `SecretList` from a `Get`-only workload | Privilege misuse suspicion | Verify principal, scope, owner, access pattern |
| Initial 401 followed by 200 | Normal auth challenge | Check final response; don't page on single 401 |
| Final 401 from Key Vault | Authentication/token issue | Check credential source, audience, tenant, clock |
| 403 from Key Vault | Authorization or networking | Check permission model/RBAC/identity/firewall/Private DNS |
| 404 from Key Vault | Resource/name/version/lifecycle | Check vault URI, secret name, version, deleted state |
| 429 from Key Vault | Throttling | Backoff/jitter, caching, reduce concurrency |
| TLS/DNS timeout | Network path | Check DNS FQDN, VNet, Private Endpoint, firewall/proxy |
| Key Vault `Get` succeeds, partner returns 401 | Downstream credential | Check partner rotation, app cache, and revocation |
| Unexpected role assignment | Control-plane incident | Preserve Activity Log, review principal/scope, contain |
| Diagnostic setting disabled | Monitoring tampering or unapproved edit | Check Activity Log, restore approved config, investigate |
| Secret deleted yet partner still accepts key | Credential still valid externally | Revoke/rotate at partner, not just vault delete |
| Secret in application log | Exfiltration risk | Open incident, restrict logs, revoke/rotate, scrub copies |
| App still uses V1 after V2 rollout | Rotation propagation | Check pinned version, TTL/cache, instances, partner |
| No `AuditEvent` after client error | Pre-data-plane failure or ingestion lag | Check client traces, networking, diagnostics destination |
| Works locally, Azure app fails | Different runtime identity/network | Check managed identity, role scope, VNet DNS |

### 30.1. Separating Operational and Security Priorities

**Operational incident:** typically an app failing to read a secret due to role/network/config issues, impacting availability and requiring an approved fix or rollback.

**Security incident:** evidence of unauthorized access, leaked credentials, compromised principals, or audit tampering. Preserve evidence and coordinate response—never “fix” by granting broader permissions.

Both can happen together: after an unauthorized IAM edit, the app loses access while another principal reads the secret. Coordinate SRE, IAM, and SOC together.

## 31. Production Checklist for Auditing and Authentication

### 31.1. Identity and Permission Design

- [ ] Every workload has an explicit managed/workload identity with an owner.
- [ ] Runtime identities hold minimal **Get secrets** permissions.
- [ ] Key Vault Administrator/Secrets Officer are never granted to read-only apps.
- [ ] Azure Contributor is not treated as a substitute for data-plane Secrets User.
- [ ] RBAC vs. access policy model is explicitly chosen and verified.
- [ ] Inherited role assignments and scopes are reviewed.
- [ ] User-assigned client ID and principal object ID are never confused.
- [ ] AKS federation issuer/subject/audience tested where used.
- [ ] Local developer credentials never carry over to production.
- [ ] Identity/permission changes require approvals, change tickets, and auditing.
- [ ] Containment plans account for role revocation caching/propagation delays.

### 31.2. Auditing and Logging

- [ ] `AuditEvent` diagnostics enabled on all production vaults per policy.
- [ ] Azure Activity Log and IAM change events have governed destinations/retention.
- [ ] Entra identity events and Java dependency telemetry correlate by time/principal.
- [ ] Data-plane and control-plane logs are clearly separated.
- [ ] Team knows whether workspaces use **`AzureDiagnostics` or resource-specific tables**.
- [ ] KQL queries tested against real schemas, not just demos.
- [ ] Logs capture status, operation, principal, resource, time, and request ID metadata.
- [ ] Zero secret values, access tokens, or `Authorization` headers in logs.
- [ ] Alerts monitor diagnostic setting and destination edits.
- [ ] SOC/IR hold audit read access without defaulting to `Secret Get`.
- [ ] Retention, legal hold, and export/chain-of-custody follow policy.
- [ ] Alerts exist for unknown principals, unusual `SecretList`, and failed-access spikes.
- [ ] False-positive tuning covers planned deployments and scale-outs.
- [ ] Monitoring ingestion lag and alert health are measured.

### 31.3. Networking and Key Vault Operations

- [ ] Vault public network/firewall/Private Endpoint design approved.
- [ ] DNS for `vault-name.vault.azure.net` verified from actual hosts/pods.
- [ ] Private DNS zone links and routes verified.
- [ ] TLS/certificate verification is never disabled to bypass DNS errors.
- [ ] Apps acquire valid tokens for the right tenant and Key Vault audience.
- [ ] Secret names/versions configured per environment.
- [ ] Startup cache/refresh TTL and failure behaviors defined.
- [ ] `getSecret` is never called on every request or liveness probe.
- [ ] 401 challenges and final outcomes are distinguished.
- [ ] 403s are classified between networking vs. RBAC/policy.
- [ ] 404 runbooks cover name/version/deleted states.
- [ ] 429s enforce retry budgets/backoff/jitter and honor `Retry-After`.
- [ ] 5xx/timeouts have degraded-service and health-check strategies.
- [ ] Partner auth failures are tracked separately from Key Vault failures.

### 31.4. Incident Response and Rotation

- [ ] Inventory tracks secret owners, data classification, and consuming partners/systems.
- [ ] Incident severity criteria and on-call contacts defined.
- [ ] Log evidence preservation precedes destructive remediation.
- [ ] Playbooks exist for compromised identities and compromised secrets.
- [ ] Process issues new keys at the target system before updating the vault.
- [ ] Old credentials can be revoked at the partner/DB/CA, not merely deleted in the vault.
- [ ] Canary, rollback, and version-metadata telemetry accompany rotations.
- [ ] All instances verified to adopt new keys.
- [ ] Soft-delete, purge protection, and recovery policies configured.
- [ ] Production secrets are never purged or disabled without approval.
- [ ] Logs, source code, CI artifacts, and config snapshots scanned on suspected leaks.
- [ ] Postmortems and regression tests follow root causes.
- [ ] Log pipeline and `SecretGet` costs/quotas/retention measured.
- [ ] All practice exercises use lab secrets, never production values.

## 32. Practice Exercises

### Exercise 1: Identifying Log Sources

Given three events:

1. Java **`SecretGet`** to Key Vault returns 403.
2. An admin modifies the vault's firewall settings.
3. A managed identity fails to acquire an access token due to broken federation.

Choose **`Key Vault AuditEvent`**, **`Azure Activity Log`**, or **`Entra/workload/application telemetry`** as the primary source for each, and explain why no single other source proves the entire event.

### Exercise 2: Enabling Auditing on a Lab Vault

1. Select an approved subscription and resource group.
2. Verify the vault's permission model.
3. List diagnostic log categories.
4. Enable `AuditEvent` to an owner-approved Log Analytics workspace.
5. Re-read the setting and workspace ID.
6. Run one `Get` on a demo secret.
7. Wait for ingestion and locate the event.
8. Print only operation/status/metadata—never the value.

### Exercise 3: KQL Baselines

Write KQL summarizing:

- `SecretGet`/`SecretList`/`SecretSet` per day.
- Successful vs. failed request counts.
- Top principals/caller IPs by operation count.
- Post-deployment 403 rate.
- A verified benign post-rotation spike.

First run **`getschema`/`take`** against the live table; never assume `requestUri_s` exists without checking.

### Exercise 4: Distinguishing 401 Challenges

A Java SDK sends a request:

~~~text
12:00:00 Key Vault GET returns 401 with challenge
12:00:00 Azure Identity obtains token
12:00:01 Key Vault GET returns 200
~~~

Is this an authentication incident? How should alerts track **final outcomes** to avoid false positives?

### Exercise 5: Troubleshooting 403 on App Service

Local dev reads the demo secret, while production App Service gets 403.

Build a verification table covering:

1. App Service managed identity principal ID.
2. Vault RBAC vs. access policy authorization model.
3. `Key Vault Secrets User` scope.
4. Role propagation.
5. Private Endpoint/firewall/DNS.
6. Vault URL and tenant.
7. Audit/request ID correlation.

Never propose granting Azure Owner to the app.

### Exercise 6: 404 from Secret Name/Version

An app pins V1, and after rotation V1 is disabled/deleted. Design:

- Secret URI/version verification.
- 404/lifecycle error handling workflow.
- Canarying V2.
- Verifying partner usage of V2.
- Risk-based rollback vs. fail-closed behavior.
- Logging version metadata without exposing keys.

### Exercise 7: Partner Returns 401

Key Vault `Get` returns 200, while the payment partner API returns 401. Explain why you shouldn't modify Key Vault RBAC. Design checks for: active partner keys, app caching, V1/V2 rollout, `Authorization` header sanitation, and partner audits.

### Exercise 8: KQL for an Unknown Principal

A production vault has 10 approved identities. A new principal executes 200 `SecretGet`s in 15 minutes.

- Inspect role assignment and owner.
- Check deployments/change tickets.
- Inspect caller IP/NAT.
- Inspect accessed secret paths.
- Classify security vs. operational event.
- Design alerting and containment.
- Note the limits of conclusions drawn from audits alone.

### Exercise 9: Disabled Diagnostic Settings

Combine Azure Activity Log and diagnostic inventories to detect someone disabling `AuditEvent` right before suspected `SecretGet` activity. Identify the unrecoverable evidence blind spots.

### Exercise 10: Retry Storm

100 app instances scale out, each fetching 5 secrets and retrying 5 times on 429:

1. Calculate hypothetical max attempts if every call retries.
2. Propose bounded concurrency and jitter.
3. Compare against startup caching with 10-minute refresh.
4. Define metrics for both Key Vault and the app.
5. Explain why liveness probes must never call Key Vault.

### Exercise 11: Secret Exposed in CI Logs

A build log contains a partner API key, even though Key Vault `AuditEvent` shows only authorized `Get`s.

Design a runbook:

1. Restrict logs and preserve evidence.
2. Classify credential exposure.
3. Issue a new key at the partner.
4. Update the Key Vault version.
5. Canary/roll out app.
6. Revoke old partner key.
7. Audit repos/CI/artifacts.
8. Run postmortem and redaction regression tests.

### Exercise 12: RBAC Negative Tests

Two identities:

- A: **Key Vault Secrets User** on the lab vault.
- B: **Key Vault Reader** or no data-plane `Get`.

Test `SecretGet` and metadata listing, comparing results against current role definitions. Why doesn't `Key Vault Reader` grant viewing plaintext secrets?

### Exercise 13: Private Link Failure

An AKS pod holds the right role yet fails to resolve the private vault FQDN.

- Diagram DNS, private endpoint, and routing.
- Measure TLS/timeouts from inside the pod.
- Compare app traces against Key Vault `AuditEvent`.
- Explain why zero data-plane events may exist.
- Write a fix plan without disabling firewalls or TLS.

### Exercise 14: Capacity and FinOps

Compare daily `GET` volume for 600 req/s with 1 `SecretGet`/request vs. 30 instances refreshing every 10 minutes. Estimate impact on Key Vault operations and log ingestion **without inventing unit prices**. Propose an appropriate TTL/rotation SLO.

### Exercise 15: Security Tabletop

SOC alerts on an unknown principal reading 3 sensitive secrets. IAM is waiting on RBAC propagation, SRE worries about a checkout outage, and the Partner API lacks dual-key support.

Define:

- Who is incident commander.
- Priority containment steps.
- When downtime must be accepted to revoke.
- Which logs must be preserved.
- How to verify the old key no longer works.
- Incident closure criteria and lessons learned.

## 33. Self-Check Questions

1. How does Key Vault data-plane auditing differ from Azure Activity Log?
2. Which questions does `AuditEvent` typically help answer?
3. Do diagnostic settings retroactively generate logs from before they were enabled?
4. How does `AzureDiagnostics` differ from resource-specific tables like `AZKVAuditLogs`?
5. If a table does not exist, can you conclude the vault received zero requests?
6. Why inspect the schema before writing KQL?
7. How does `SecretList` differ from `SecretGet`?
8. Does a successful `SecretGet` prove data was exfiltrated?
9. Does zero anomalous `SecretGet` activity prove a secret hasn't leaked?
10. Why isn't `CallerIPAddress` enough to identify an end user?
11. Does a managed identity map to individual end users in logs?
12. How do control-plane roles and data-plane roles differ?
13. Can Azure Contributor read secret values by default?
14. How does `Key Vault Reader` differ from `Key Vault Secrets User`?
15. Does a vault in RBAC mode honor access policies automatically?
16. How many vaults can a resource-group role assignment affect?
17. Why inventory both principal object ID and client ID?
18. Can an App Service system-assigned identity change its principal after recreation?
19. Which issuer/subject/audience settings does AKS Workload ID require?
20. Does successful Entra token acquisition guarantee Key Vault `Get` is permitted?
21. Why can a 401 challenge be normal behavior?
22. How do you distinguish a final 401 from a 401 challenge?
23. Which causes other than RBAC can trigger 403?
24. Can a network firewall denial return HTTP 403?
25. Why never disable TLS to work around a private DNS failure?
26. When does a 404 require checking the secret version?
27. Why never auto-create a secret when hitting 404?
28. Which SDK calling habits trigger 429s?
29. When should secrets be cached instead of fetched via `GET` per request?
30. Is token caching the same as secret-value caching?
31. How does a Partner API 401 differ from a Key Vault 401?
32. Does a versionless secret automatically force every JVM to switch to the new version immediately?
33. Does `Set`ting a new Key Vault version revoke the old key at the partner?
34. Why doesn't deleting a vault secret stop an attacker from using a copied key?
35. How does soft-delete differ from purge protection?
36. Which stages of rotation must be audited?
37. Which logs must be preserved when credential compromise is suspected?
38. Should diagnostic setting changes have their own dedicated alert?
39. Why shouldn't alerts fire solely on a single `SecretGet` spike?
40. How do you distinguish legitimate scale-out from anomalous access?
41. Why shouldn't removing an IAM role be treated as instantaneous containment?
42. What should Application Insights log, and what must it avoid logging?
43. Does a Java `String` guarantee immediate removal of credentials from RAM?
44. What must happen if a secret appears in a CI log?
45. When must an app fail closed instead of using a cached key?
46. How do readiness and liveness probes differ regarding Key Vault dependencies?
47. Which field issues can cause a KQL query to return empty results?
48. Why do audit logs need tight access control even without secret values?
49. Which cost drivers exist beyond Key Vault operations?
50. What constitutes sufficient evidence to close a secret exposure incident?

## 34. References

- [Azure Key Vault overview — Microsoft Learn](https://learn.microsoft.com/azure/key-vault/general/overview)
- [Key Vault authentication and authorization](https://learn.microsoft.com/azure/key-vault/general/authentication)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Key Vault access policies](https://learn.microsoft.com/azure/key-vault/general/assign-access-policy)
- [Monitor Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/monitor-key-vault)
- [Key Vault logging and diagnostics](https://learn.microsoft.com/azure/key-vault/general/logging)
- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings)
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log)
- [Log Analytics Kusto Query Language](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview)
- [Azure Monitor reference: AZKVAuditLogs](https://learn.microsoft.com/azure/azure-monitor/reference/tables/azkvauditlogs)
- [Azure Monitor reference: AzureDiagnostics](https://learn.microsoft.com/azure/azure-monitor/reference/tables/azurediagnostics)
- [Key Vault network security](https://learn.microsoft.com/azure/key-vault/general/network-security)
- [Azure Key Vault Private Link](https://learn.microsoft.com/azure/key-vault/general/private-link-service)
- [Key Vault soft-delete overview](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview)
- [Key Vault backup and restore](https://learn.microsoft.com/azure/key-vault/general/backup)
- [Azure Key Vault secret management with Java](https://learn.microsoft.com/azure/key-vault/secrets/quick-create-java)
- [Azure Key Vault Secrets Java SDK](https://learn.microsoft.com/java/api/overview/azure/security-keyvault-secrets-readme)
- [Azure Identity for Java SDK](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [AKS Microsoft Entra Workload ID](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure Event Grid integration with Key Vault](https://learn.microsoft.com/azure/key-vault/general/event-grid-overview)
- [Azure Key Vault pricing](https://azure.microsoft.com/pricing/details/key-vault/)
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
