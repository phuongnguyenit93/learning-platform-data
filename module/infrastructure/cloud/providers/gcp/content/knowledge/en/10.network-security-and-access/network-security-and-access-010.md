# Access Context Manager and Context-Aware Access

## Learning Objectives

After this lesson, learners will be able to:

1. Explain how **Access Context Manager** defines and evaluates request context; distinguish **access policies**, **access levels**, **basic/custom conditions**, and where policies are **enforced**.
2. Identify contextual attributes including **source IP address, geolocation, identity, device posture**, and dependent access levels, while understanding each signal's limitations.
3. Design **context-aware access** for internal applications via **Identity-Aware Proxy (IAP)** using IAM Conditions, and for Google Cloud APIs via **VPC Service Controls** where appropriate.
4. Create, inspect, and update an access level with **gcloud**; test both positive and negative cases before production rollout.
5. Analyze **Zero Trust** principles, least-privilege IAM, user-lockout risks, audit logs, and impacts on reliability, cost, and operations.

## 1. The Problem: Having the Right Account Is Not Always Secure Enough

In the **CLOUD_PROVIDERS_GCP** module, an organization deploys projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, databases, storage, and release pipelines. Employees may work from the office, remotely, or on unmanaged devices. Relying solely on whether an account **holds an IAM role** to permit every request regardless of context may fall short of protecting sensitive data.

Examples:

- An engineer holds permission to access the **order administration portal**. Security wants them to sign in via **IAP** only from a device with disk encryption and screen lock enabled, or when connecting from an approved corporate IP range.
- An analytics team holds IAM permissions to read **BigQuery**, yet data in a project is protected by a **VPC Service Controls service perimeter**; requests from outside the perimeter must also satisfy ingress rules.
- A compromised password or session can originate from an unusual network or device. **Request context** serves as an additional signal to reduce risk, not a replacement for strong authentication, IAM, or monitoring.

**Access Context Manager (ACM)** is the service used to declare **access levels**—condition sets that classify a request by contextual attributes. **Creating an access level does not automatically block access.** You must attach it to a supported enforcement point, such as **IAP** or **VPC Service Controls**.

### Quick Distinction Across Five Questions

| Question | Primary tool/layer | Example |
|---|---|---|
| **Who is making the request?** | Identity, authentication, IAM principal | employee@example.com, service account |
| **What is the request allowed to do?** | IAM roles, permissions, applicable IAM Conditions | Allowed to access an app via IAP, read a bucket |
| **In what context did the request originate?** | Access Context Manager access levels; device/IP/origin signals | Corporate IP, encrypted device, valid access path |
| **Do service or data boundaries allow it through?** | VPC Service Controls, IAP, or equivalent control | Whether external callers may invoke protected data APIs |
| **Do IP packets reach the destination?** | VPC routes, firewalls, Cloud Armor, load balancing | TCP/443 reaching the application backend |

Only when **every relevant control layer** permits it does a request succeed. Satisfying an access level does not grant BigQuery permissions, bypass IAM, or open VPC firewall ports.

## 2. Logical Architecture of Access Context Manager

~~~mermaid
flowchart TD
    USER["User / workload sending request"] --> CTX["Context: principal, IP, region, device"]
    ORG["Organization-level access policy"] --> L["Access levels: CorpNet, TrustedDevice, AdminAccess"]
    CTX --> L
    L --> IAP["IAP + IAM conditional binding"]
    L --> VPCSC["VPC Service Controls perimeter"]
    IAP --> APP["Internal HTTP(S) / TCP app"]
    VPCSC --> API["Protected Google Cloud APIs and data"]
    IAM["IAM roles / effective permissions"] --> IAP
    IAM --> API
~~~

In the diagram:

1. **Access policy** is the container holding access levels and service perimeters. It has its own numeric ID and is governed at the supported organization/scope level.
2. **Access level** is a rule set evaluating to **true/false** for a request's context.
3. **Enforcement point** is where the evaluation result is consumed: an **IAM binding on an IAP resource** or a **service perimeter** and its ingress rules.
4. **IAM** remains the authorization layer for resources or applications.

**Key point:** A context policy only has effect when its evaluation result is **wired into the live access path**. Creating a level named **CorpNet** without referencing it in IAP or a perimeter leaves existing access behavior unchanged.

## 3. Access Policy, Access Level, and Governance Scope

### 3.1. Access Policy as the Configuration Container

An **Access Context Manager access policy** holds the access levels and service perimeters within its scope.

Google Cloud supports:

- **Organization-level access policy**: a single organization-wide policy. This is required for **IAP context-aware access** and can also be used for VPC Service Controls.
- **Scoped access policies**: folder- or project-scoped policies for delegating **VPC Service Controls** administration. Current documentation limits scoped policies to VPC Service Controls; they do not replace the organization-level policy for IAP.

Each access policy has a **numeric policy ID**, such as **123456789012**. Full identifier of a level:

~~~text
accessPolicies/123456789012/accessLevels/CorpNet
~~~

Here **123456789012** is the **policy number**, not a project ID or organization ID. Two organizations can both name a level **CorpNet** while having distinct full identifiers. The casing of **accessLevels** is case-sensitive: **accesslevels** is not equivalent.

### 3.2. IAM for Administering Access Context Manager

Common roles:

| Role | Primary meaning |
|---|---|
| **roles/accesscontextmanager.policyReader** | Read access policies/access levels within granted scope |
| **roles/accesscontextmanager.policyEditor** | Create/update access policies and levels within permitted scope |
| **roles/accesscontextmanager.policyAdmin** | Administer Access Context Manager within granted scope |
| **roles/iap.httpsResourceAccessor** | Allows a principal to access an IAP-protected web app if attached IAM conditions hold |
| **roles/iap.tunnelResourceAccessor** | Corresponding permission for IAP TCP tunnels |

These roles are **not identical**. Someone permitted to **edit an access level** can affect many applications if that level is reused. Separate policy administrators from application access approvers and require change reviews.

For scoped access policies, granting a role on an ordinary project **does not automatically** grant management rights over the scoped policy. Per Access Context Manager IAM docs, roles must be granted at the **organization** or on **the access policy itself** as supported.

### 3.3. Modifying an Access Level Can Impact Multiple Consumers

Suppose **TrustedDevice** is referenced by 5 IAP IAM bindings and one service perimeter. If an administrator loosens the level from "encrypted device" to "any device," multiple resources open up simultaneously. Conversely, tightening conditions too aggressively can lock out multiple teams.

Change management should include: a list of consumers referencing the level, the previous config snapshot, approvers, testing on affected targets, and rollback readiness.

## 4. Commonly Used Contextual Attributes

### 4.1. Signal Table

| Attribute | Condition example | Practical value | Limitations to understand |
|---|---|---|---|
| **IP subnetworks** | Source in 203.0.113.0/24 | Identifies known office/VPN networks | NAT, proxies, rotating IPs; IP does not prove identity |
| **Region** | Origin geolocated to VN/SG | Enforces policy-based geographic bounds | GeoIP is approximate; VPN/proxies reflect egress location |
| **Members** | Specific user or serviceAccount | Adds principal constraints where consumer supports it | Does not replace IAM permissions; groups are not directly supported in this attribute |
| **Device policy** | Screen lock, disk encrypted, OS version | Confirms device posture compliance | Requires reported device telemetry and proper MDM/Endpoint Verification licensing |
| **Required access levels** | Satisfies both CorpNet and ManagedDevice | Composes existing levels | Wrong AND/OR logic can over-open or lock out access |
| **Custom CEL expression** | Checks criteria not easily expressed in basic levels | Flexible conditions per supported context sources | Syntax/attribute and license limits apply; test thoroughly |

**The CIDRs 203.0.113.0/24 and 198.51.100.0/24 in this lesson are documentation ranges**, not real enterprise networks. In production, substitute the **actual public egress IPs** observed by Google Cloud—never arbitrary internal office private subnets.

### 4.2. Source IP Is Not Always the User's Machine IP

An employee connecting over a corporate VPN appears with the **VPN's public egress IP**, not their laptop's private IP. When proxies, NAT, or intermediaries sit in the path, the address seen at the enforcement point differs from what the user sees locally in their OS.

Cases to analyze:

- Corporate VPN exiting to the Internet via a fixed IP pool: the allowlist must list that **public egress** pool.
- User switches from home Wi-Fi to mobile hotspot: context changes even though user and device remain identical.
- Service account or GCP workload calling APIs via **Private Google Access**: source IP context may not carry a public IP expected by an IP allowlist rule.
- VPC Service Controls handles request sources through multiple mechanisms; never assume Cloud NAT public IPs act as the source IP across all Google API calls.

For requests from GCP resources in another project or perimeter, evaluate **ingress rules by source project/VPC or service account**, rather than trying to rely on a single public IP.

### 4.3. GeoIP Does Not Mean "Physically in That Country"

The **regions** condition uses ISO 3166-1 alpha-2 country codes such as **VN** and **SG**. It relies on observed IP geolocation. Using a VPN exiting in Singapore makes requests appear to come from **SG** even if the user is physically in Vietnam.

Access Context Manager docs note limitations for requests carrying only private IPs: geographic region may be indeterminable. Therefore, geo restrictions should remain supplementary signals, not primary authentication factors.

### 4.4. Device Signals and Device Preparation

Common device conditions:

- **requireScreenlock**: requires screen lock enabled.
- **allowedEncryptionStatuses: [ENCRYPTED]**: disk storage is encrypted.
- **requireCorpOwned**: device is verified as company-owned.
- **requireAdminApproval**: device is approved by an administrator.
- **osConstraints**: restricts OS types and minimum versions, optionally combined with ChromeOS verification.

To use device attributes, the organization must deploy **Endpoint Verification** on desktops or **MDM** on mobile devices per docs; many capabilities also require **Chrome Enterprise Premium** or compatible licensing. Without reliable device telemetry, a level requiring device posture can reject legitimate users.

Do not assume every API client, service account, or browser sends complete device posture. Check which IAP/Context-Aware Access client types are supported before enforcing.

## 5. Basic Access Levels and Condition Logic

A **basic access level** contains one or more **conditions**. A single condition can combine multiple attributes such as **ipSubnetworks** and **devicePolicy**.

### 5.1. Logic Inside One Condition

Within a single condition, attributes combine using **AND**:

~~~text
Condition A:
  IP in 203.0.113.0/24
  AND device encrypted
  AND screen lock enabled
  → A passes only when every criterion passes
~~~

Items inside a list of the same attribute type typically evaluate with **OR** per attribute semantics—for example, IP matches **either** of two listed CIDRs. Setting **negate: true** inverts the condition result per its defined semantics; it is not an arbitrary negative allowlist shortcut.

### 5.2. Logic Across Multiple Conditions

When a basic access level has **two conditions**, **combineFunction** controls how they combine:

- **AND**: requires passing **both** conditions.
- **OR**: requires passing **at least one** condition.

Desired policy:

> Allow employees access only if they are on the **corporate network** **and** using an **encrypted device**.

You must use **AND**. Accidentally choosing OR lets an unencrypted personal device on the corporate network pass—or lets an encrypted device pass from an untrusted network.

| IP in allowlist | Device encrypted | **AND** | **OR** |
|---|---|---|---|
| Yes | Yes | **Level satisfied** | Level satisfied |
| Yes | No | Not satisfied | **Level satisfied** |
| No | Yes | Not satisfied | **Level satisfied** |
| No | No | Not satisfied | Not satisfied |

"Level satisfied" here means only that **the access level evaluates true**; IAP/IAM or the perimeter still enforces other conditions and permissions.

### 5.3. Simple Basic Level Example: CorpNet

YAML condition spec passed to the CLI via **--basic-level-spec**:

~~~yaml
# corp-net.yaml — CLI input spec, not a Kubernetes manifest
- ipSubnetworks:
    - 203.0.113.0/24
    - 198.51.100.0/24
~~~

Both CIDRs combine via **OR**: matching either range suffices. However, this is still a single condition with no device posture constraint.

### 5.4. Combining IP and Device in One Condition

~~~yaml
# corp-managed-device.yaml — requires both IP and device posture
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

In this structure, both IP and device policy must **pass simultaneously**. Operations must first verify Endpoint Verification/MDM and appropriate licensing. For alternative rules like "corp-owned devices can access from any network," build **two conditions with combineFunction=OR** or a reviewed custom expression rather than toggling flags randomly.

### 5.5. Required Access Levels: Reusing Levels While Avoiding Cycles

An access level can require another level via **requiredAccessLevels**:

~~~yaml
- requiredAccessLevels:
    - accessPolicies/123456789012/accessLevels/CorpNet
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

This example passes only when **CorpNet** passes **and** the device policy passes. Referenced levels must exist in the right policy; avoid circular dependencies and document reuse so edits to base levels do not trigger unexpected cascading impacts.

## 6. Custom Access Levels with Common Expression Language

A **custom access level** uses a subset of **Common Expression Language (CEL)** to write more flexible conditions than basic levels—checking source IPs, regions, or device/context attributes from supported sources.

Simple YAML file example:

~~~yaml
# trusted-region.yaml — CEL illustration; avoid relying on geo rules alone
expression: "origin.region_code in ['VN', 'SG']"
~~~

Example using the **inIpRange** function:

~~~yaml
# trusted-ip.yaml
expression: "inIpRange(origin.ip, ['203.0.113.0/24'])"
~~~

In CEL, **origin.ip** and **origin.region_code** may be undefined for certain requests. When an attribute is missing, the expression may fail to evaluate as expected; test live request flows rather than merely checking that the CLI accepts the syntax.

### When to Choose Custom vs. Basic?

Choose a **basic level** if the policy only needs straightforward IP/region/device attributes and clear AND/OR logic. Choose a **custom level** when conditions genuinely require CEL or data from supported third-party security/endpoint integrations.

**Advanced Mode** and certain device/custom access level features carry distinct licensing prerequisites. Verify licensing, supported CEL attributes, and enforcement-point compatibility before production use.

## 7. Access Context Manager Is Not the Same as IAM Conditions

Both mention "conditions," yet they serve different roles:

| Capability | Access Context Manager | IAM Conditions |
|---|---|---|
| Where configured | Access policy and access level | Conditional binding on an IAM policy |
| Typical criteria | IP, region, device, members, supported custom CEL | Request/resource/time attributes per permission type |
| Grants access permissions? | **No** | Conditional IAM binding grants roles when permissions align |
| Can they be combined? | **Yes**, when supported by enforcement point (e.g., IAP) | IAP can reference access levels via IAM Condition attributes |
| Applies to all APIs? | No; depends on consumer | Also no; attributes only work for specific permissions/resources |

Important: **request.auth.access_levels** in IAM Conditions is supported for requests passing through **IAP**, such as IAP web apps and IAP TCP tunneling. Never copy this condition onto an ordinary **Cloud Storage/BigQuery/Compute Engine** IAM binding expecting those APIs to check device context; that attribute is unsupported on those bindings.

## 8. Enforcing Context with Identity-Aware Proxy (IAP)

### 8.1. IAP Adds Identity and Context Checks for Applications

IAP can protect **web applications** behind supported apps/load balancers, or **TCP forwarding** to VMs/tunnel destinations. Users must authenticate and satisfy IAM roles/conditions before passing through IAP.

~~~mermaid
sequenceDiagram
    participant U as Employee
    participant I as IAP
    participant A as Access Context Manager
    participant IAM as IAP IAM policy
    participant W as Internal web app
    U->>I: HTTPS request /admin
    I->>A: Evaluate access levels by IP/device
    A-->>I: Satisfied access levels
    I->>IAM: Check role and IAM Condition
    alt Authorized and context satisfied
        IAM-->>I: Allow
        I->>W: Forward request
        W-->>U: Application response
    else Unauthorized or context failed
        IAM-->>I: Deny
        I-->>U: Access denied
    end
~~~

This diagram illustrates logical flow, not a guarantee of internal call ordering. **IAP and IAM** form the enforcement point; access levels supply the contextual signals evaluated against it.

### 8.2. Illustrative IAM Conditional Binding

Suppose:

- Organization access policy: **123456789012**.
- Access level: **CorpManagedDevice**.
- Employee group: **platform-team@example.com**.
- Application has IAP enabled behind a supported backend.

An IAM binding on the **IAP resource** (illustrative snippet, not a full policy):

~~~yaml
bindings:
  - role: roles/iap.httpsResourceAccessor
    members:
      - group:platform-team@example.com
    condition:
      title: CorpManagedDeviceOnly
      description: Platform team only from approved device context
      expression: "'accessPolicies/123456789012/accessLevels/CorpManagedDevice' in request.auth.access_levels"
~~~

Only when the principal belongs to the granted group **and** the matching access level is present in **request.auth.access_levels** does this binding grant access through IAP.

**The IAM role governs app access**, not Access Context Manager ACL management. Do not confuse **roles/iap.httpsResourceAccessor** with **roles/accesscontextmanager.policyEditor**.

### 8.3. Adding URL Path or Time Restrictions

IAP IAM Conditions can evaluate attributes like **request.host**, **request.path**, and **request.time** within supported scope. Example restricting an app's admin section further:

~~~text
'accessPolicies/123456789012/accessLevels/CorpManagedDevice'
    in request.auth.access_levels
&&
(request.path == '/admin' || request.path.startsWith('/admin/'))
~~~

This condition applies only to the exact URL path per IAM rules; watch out for **URL encoding, path normalization, trailing slashes**, alternate endpoints performing the same action, and backend routing logic. Never rely on a path string condition in place of application-level authentication/authorization.

**Security note:** Other IAP bindings might exist that grant the principal access without requiring an access level. IAM allow bindings are additive, so audit **all** effective bindings—including higher-level inherited ones—to ensure no unintended access path remains.

### 8.4. Steps to Configure via Console

1. Ensure the app runs behind an **IAP-supported** model and enable IAP per documentation.
2. Create the access level in **Access Context Manager** under the organization-level policy.
3. Open **Security → Identity-Aware Proxy** and select the right web app/backend service or IAP tunnel resource.
4. Add the principal or Google Group to **IAP-secured Web App User** (or the corresponding TCP role).
5. Attach an **IAM Condition** referencing the access level; verify the full resource name has the right policy ID and casing.
6. Test access from both compliant and non-compliant devices before broad rollout.
7. Inspect IAP Data Access audit logs after enabling needed logging; monitor denial rates and user feedback.

For sensitive policies, never edit a project IAM policy by overwriting the whole file just to add one IAP binding. Use targeted IAP resource API/Console actions and review diffs.

### 8.5. How Do IAP and Network Security Differ?

IAP protects requests passing through IAP. It does not protect a backend if a **direct access path** remains open outside IAP. Audit LB/ingress configs, firewalls, private networks, and internal paths to the backend to eliminate bypasses. Across Cloud Run, GKE, and Compute Engine, supported paths and backend types vary; do not assume enabling IAP in one place secures every endpoint.

IAP does not replace:

- **MFA/2-Step Verification** and account protection.
- **IAM roles** for GCP resources such as Storage buckets.
- **Cloud Armor** or firewalls blocking invalid traffic at their respective layers.
- **In-app authorization** deciding which user may view or edit specific orders.

## 9. Enforcing Access Levels with VPC Service Controls

### 9.1. What Does a Service Perimeter Do?

**VPC Service Controls (VPC SC)** establishes a **service perimeter** around supported Google Cloud projects and services to mitigate unauthorized API access and data exfiltration across boundaries.

Example: **analytics-prod-001** holds sensitive BigQuery and Cloud Storage data. Even if a user holds an IAM role on a dataset or bucket, requests from outside the perimeter can still be **blocked by the VPC SC boundary** unless an authorized ingress path exists.

~~~mermaid
flowchart LR
    EXT["Client outside perimeter"] --> EV{"Valid access level or<br/>ingress rule?"}
    EV -->|No| DENY["VPC SC blocks"]
    EV -->|Yes| IAM["IAM and other policies"]
    IAM -->|Authorized| DATA["BigQuery / Cloud Storage<br/>inside perimeter"]
    IAM -->|Unauthorized| DENY2["IAM blocks"]
~~~

**VPC SC blocks and IAM blocks are two distinct causes.** Never loosen IAM roles to troubleshoot a VPC SC violation when the caller already has sufficient IAM permissions.

### 9.2. Access Levels and Ingress Rules Are Complementary

Per VPC SC documentation:

- If a request from **outside the perimeter** to a protected resource **satisfies an access level** attached to the perimeter **or** matches a valid **ingress rule**, VPC SC can permit it inward.
- Adding **multiple access levels** to a perimeter allows passing **any one** listed level through the access-levels branch. This is **OR** logic, not default AND.
- An access level **does not** grant IAM permissions. After crossing the perimeter, requests still need permissions on the API/resource.
- Access levels attached to a perimeter primarily open **inbound access from outside**; they **cannot** serve as rules governing outbound **egress** from internal resources outward.

For example, attaching both **CorpNet** (corporate IP) and **TrustedDevice** (managed device) as two separate access levels to a perimeter does **not** enforce "must satisfy both" because the list evaluates as OR. To require both, create **one composite access level** combining IP and device with AND and attach only that level—or design precise ingress rules.

### 9.3. Cases Where Access Levels Do Not Replace Ingress/Egress Rules

| Scenario | Mechanism to consider |
|---|---|
| Users outside perimeter need conditional IP/device access to sensitive BigQuery | Appropriate access level attached to perimeter, plus IAM |
| Workload in another project must call protected APIs | Ingress rule constraining source project/VPC/service account and API operations, plus IAM |
| Service inside perimeter calls external resources outside perimeter | Suitable **egress rule**; ingress access levels do not cover this |
| Two perimeters need to exchange data | Egress on source and ingress on destination as needed; a single access level won't bridge both sides alone |
| Restrict HTTP path **/admin** of a web app | **IAP + IAM Conditions**, not VPC SC API perimeters |
| Lock down a TCP port on a VM | Firewall/IAP TCP or network control; access levels only act through supported enforcement points |

**Key limitation:** Access levels are not the standard way to allow requests from **another perimeter** to bypass the source perimeter's egress policy. For cross-perimeter flows, analyze both **source egress and destination ingress**.

### 9.4. VPC SC Is Not a Firewall for Every Packet

VPC SC protects supported Google Cloud services/APIs per Google Cloud mechanisms. It does not replace:

- **VPC firewall rules** for VM/endpoint network traffic.
- **Cloud Armor** in front of web applications.
- **Network routing/VPN/Private Service Connect** for connectivity paths.
- **Database authentication** or IAM permissions.
- **Data Loss Prevention** and application-layer data controls.

Putting a perimeter around a project with Compute Engine does not automatically put custom APIs you run on VMs under VPC SC protection. Check the perimeter's **restricted services** and the exact request types.

### 9.5. Dry-Run Before Enforcement

VPC SC offers a **dry-run configuration** to evaluate perimeter/policy impact without blocking live traffic. Always use it to spot legitimate calls that would be denied—especially in projects using Cloud Build, GKE, BigQuery, Storage, Artifact Registry, and CI/CD pipelines.

When promoting from dry-run to enforced:

1. Inventory required services/APIs and cross-project data flows.
2. Verify IAM, caller identities, source projects/VPCs, destinations, and API methods.
3. Author least-privilege ingress/egress policies.
4. Monitor simulated and live violations via audit logs.
5. Prepare a rollback plan before enforcing in production.

## 10. CLI Guide: Creating and Inspecting Access Levels

This exercise focuses on **declaring access levels** without provisioning an IAP app or service perimeter itself. Appropriate organization permissions are required; all IDs/emails/IPs are illustrative. Never run in production without authorization and approval.

### 10.1. Step 1 — Locate Organization and Existing Access Policy

Suppose the organization has organization ID **987654321098**:

~~~bash
# List access policies in the organization
gcloud access-context-manager policies list \
  --organization=987654321098
~~~

Output may show an **organization-level policy** and **scoped policies** for VPC Service Controls. Find the right **numeric policy ID**. Commands below use **POLICY_NUMBER=123456789012** as a placeholder—replace it with your real ID.

Only if the organization **does not yet have an organization-level policy** should an authorized administrator create one:

~~~bash
# Example organization-level admin action; do not run if a policy already exists
gcloud access-context-manager policies create \
  --organization=987654321098 \
  --title="Corporate Access Policy"
~~~

**An organization cannot have two organization-level access policies in the same role.** If one already exists, reuse it rather than creating another. Scoped policies target VPC Service Controls delegation use cases and are not a substitute for IAP.

### 10.2. Step 2 — Author a Basic Access Level Restricting IP

File **corp-net.yaml**:

~~~yaml
# These two networks are documentation ranges only. Replace with real public egress IPs.
- ipSubnetworks:
    - 203.0.113.0/24
    - 198.51.100.0/24
~~~

### 10.3. Step 3 — Create the Access Level

~~~bash
gcloud access-context-manager levels create CorpNet \
  --policy=123456789012 \
  --title="Corporate network" \
  --description="Allow evaluated requests from approved egress networks" \
  --basic-level-spec=corp-net.yaml \
  --combine-function=and
~~~

This example has only one condition, so **combine-function=and** makes no difference here; it matters when multiple conditions exist. Creating the level neither grants IAP access nor opens a VPC SC perimeter.

### 10.4. Step 4 — List and Describe Accurately

~~~bash
gcloud access-context-manager levels list \
  --policy=123456789012

gcloud access-context-manager levels describe CorpNet \
  --policy=123456789012
~~~

Confirm:

- The level lives under **accessPolicies/123456789012**.
- Exact name is **CorpNet**.
- Subnets were saved accurately.
- Classified as a basic level with expected conditions.

### 10.5. Step 5 — Add Device Posture When Prerequisites Are Met

File **corp-managed-device.yaml**:

~~~yaml
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Ensure Endpoint Verification/MDM and licenses are ready so devices report posture. Create a **new** access level for testing:

~~~bash
gcloud access-context-manager levels create CorpManagedDevice \
  --policy=123456789012 \
  --title="Managed device on corp network" \
  --description="Approved network AND compliant device" \
  --basic-level-spec=corp-managed-device.yaml \
  --combine-function=and

gcloud access-context-manager levels describe CorpManagedDevice \
  --policy=123456789012
~~~

**Never modify a widely shared level** before inventorying affected users and resources. Create a new level first and test it against a staging IAP application.

### 10.6. Step 6 — Updating or Creating a Custom Level

To change CIDRs in a basic level, prepare the updated YAML file and update:

~~~bash
gcloud access-context-manager levels update CorpNet \
  --policy=123456789012 \
  --basic-level-spec=corp-net.yaml
~~~

To create a custom level from CEL file **trusted-region.yaml**:

~~~bash
gcloud access-context-manager levels create TrustedRegion \
  --policy=123456789012 \
  --title="Trusted geographic region" \
  --custom-level-spec=trusted-region.yaml
~~~

This is a syntax illustration. **Custom levels** carry feature/license prerequisites, and a single geographic rule is insufficient for sensitive systems. When updating production levels, save the prior version, check dependencies, and keep rollback ready.

## 11. Wiring an Access Level into IAP: A Controlled Process

Once **CorpManagedDevice** exists, design a Java application running on GKE/Compute Engine or Cloud Run behind a supported load balancer/IAP:

| Component | Example | Role |
|---|---|---|
| Application project | **orders-admin-stg** | Hosts staging application |
| Application | **admin.orders.example.com** | Internal admin UI |
| User group | **platform-team@example.com** | Authorized IAP users |
| Access policy | **123456789012** | Holds access levels |
| Access level | **CorpManagedDevice** | Corporate IP AND encrypted/screen-locked device |
| Enforcement | **IAP IAM binding** | Permits group when level passes |

### Workflow

1. Deploy the staging app and enable IAP per supported pattern; verify basic authentication works before adding context conditions.
2. Create **CorpManagedDevice** without applying it immediately across all production.
3. In the IAP IAM policy for that exact app, add **roles/iap.httpsResourceAccessor** for the group with a condition referencing the full access level name.
4. Test across at least four contexts: right IP/compliant device; right IP/non-compliant device; wrong IP/compliant device; wrong IP/non-compliant device.
5. Test a user **outside the group** on the right network and compliant device: IAM must still deny them.
6. Inspect access logs and app logs to confirm you can tell IAP context denials apart from backend errors.
7. Only after tests pass should you promote the policy to production through code review.

**Mind user experience:** switching networks, dropping VPN, rebooting, expired sessions, or out-of-date Endpoint Verification can lock out legitimate users. Maintain troubleshooting docs, support channels, and an **approved, audited emergency workflow** rather than arbitrarily deleting conditions.

## 12. Wiring an Access Level into VPC Service Controls

Suppose the organization has a service perimeter **prod-data** protecting **analytics-prod-001** with restricted services enabled. Administrators evaluate letting requests from the corporate network enter when **CorpNet** passes.

### 12.1. Inspect the Perimeter First

~~~bash
gcloud access-context-manager perimeters list \
  --policy=123456789012

gcloud access-context-manager perimeters describe prod-data \
  --policy=123456789012
~~~

Inspect **resources**, **restrictedServices**, **accessLevels**, **ingress/egress policies**, and enforced/dry-run status for active resources.

### 12.2. Sample Command to Attach an Access Level to a Perimeter

~~~bash
# MUTATING command for perimeter; run only with approval
gcloud access-context-manager perimeters update prod-data \
  --policy=123456789012 \
  --add-access-levels="accessPolicies/123456789012/accessLevels/CorpNet"
~~~

This appends **CorpNet** to the perimeter's existing access levels list rather than creating a new access level. It can **open ingress** to many identities on that approved network depending on IAM and related rules. Evaluate whether **CorpNet** alone is too broad; often **CorpManagedDevice** or identity/API-scoped ingress rules are safer.

### 12.3. Access Levels in VPC SC Do Not Govern Every Path

- Requests **from outside into** protected services: can be permitted by an **access level or ingress rule**.
- Requests **from inside outward**: inspect **egress policies**, not the access level added in step 12.2.
- Requests from **another perimeter**: verify source egress and destination ingress.
- For private calls from Google Cloud workloads, source project/VPC/service account often fits better than public IP; use **ingress rules** with appropriate metadata.

Before broad rollout, test in **dry-run** and inspect audit logs. **VPC SC does not grant users data-reading rights**; IAM still governs authorization.

## 13. Zero Trust: Multi-Layer Policy Design

**Zero Trust** is not simply "everyone must connect to VPN." It requires evaluating access by identity, context, resource sensitivity, timing, and risk rather than trusting traffic simply because it came from an internal subnet.

Illustrative governance model:

~~~mermaid
flowchart TB
    ID["Identity: SSO/MFA + Google Group"] --> DEC["Access decision"]
    DEV["Device: managed + encrypted + screenlock"] --> DEC
    NET["Network: corporate egress / source address"] --> DEC
    RES["Resource: IAP app or protected API"] --> DEC
    IAM["Least-privilege IAM"] --> DEC
    DEC -->|Conditions met| ALLOW["Allow within scoped permissions"]
    DEC -->|Conditions unmet| DENY["Deny + audit/triage"]
~~~

### 13.1. Tailoring Constraints to Resource Sensitivity

| Resource type | Suggested context controls | Additional controls needed |
|---|---|---|
| Internal observability dashboard | IAP, authorized group, access level per org policy | SSO/MFA, read-only permissions, auditing |
| Order administration portal | IAP + managed device + admin group, adding network signals as needed | In-app role enforcement for sensitive actions |
| Sensitive BigQuery | VPC SC perimeter + tailored ingress/egress; dataset-scoped IAM | IAM, auditing, data access reviews |
| Audit data in Cloud Storage | VPC SC on protected APIs where fitting | Bucket IAM, retention, encryption, logging |
| GKE admin interface | IAP suited for web apps/tunnels | RBAC, network policies, kubeconfig and cluster IAM |
| Cloud Run public API | IAP if supported app model fits, or auth/app access controls | Never assume ACM blocks every public endpoint |
| CI/CD service account | Workload Identity Federation, IAM, and ingress rules if needed | Do not apply human device policies to machine workloads |

### 13.2. Naming and Reuse Conventions

Name levels by **what the signal means**, not by one application's name, e.g.:

- **CorpNet**: source IP belongs to approved egress networks.
- **TrustedDevice**: device meets baseline posture.
- **CorpManagedDevice**: CorpNet **AND** TrustedDevice.
- **RemoteAdminApproved**: approved policy for remote administrators.

When multiple apps reference a shared level, naming and documentation must be clear enough for admins to grasp the **global impact of edits**. Never name a level **HighSecurity** if it merely checks an IP range.

### 13.3. Separating Environments and Edit Permissions

Staging should test policies ahead of production without making production easier to reach. Trust-level edits require independent review from IAM role grants. Separate responsibilities:

- Owner defining **security policy** and access level ownership.
- **Access Context Manager** administrator.
- Application **IAP** administrator.
- **VPC SC service perimeter** administrator.
- **Application and data** owner.

Recording approvers, business justification, expected impact, and rollback steps is an operational discipline, not an automatic ACM feature.

## 14. Troubleshooting and Evaluating Context-Aware Access

### 14.1. Diagnostic Matrix

| Symptom | Possible cause | Priority check |
|---|---|---|
| Level created successfully yet IAP behavior didn't change | Level not yet referenced by an IAP IAM binding | IAP IAM policy, full access level name |
| IAP denies users inside corporate network | Egress IP outside CIDR; missing device signal; wrong group | Observed IP, VPN, device posture, IAM binding |
| User on personal device still gets through IAP | Condition uses OR instead of AND, or another IAP binding lacks the condition | Level logic, all effective IAM bindings |
| Device is encrypted yet level fails | Endpoint Verification/MDM not deployed or not reporting, invalid license | Device inventory, management status, login session |
| IAP returns 403 yet app returns 200 via another URL | Backend still exposes a bypass path outside IAP | LB, ingress/firewalls, alternate URLs, network path |
| Has BigQuery IAM role yet API still errors | VPC SC perimeter violation or other IAM/API restriction | Cloud Audit Logs, restricted services, ingress/egress |
| Workload outside perimeter misses IP allowlist | Caller IP appears internal, NAT/Private Google Access | Source project/VPC/identity, ingress rule |
| Adding multiple access levels widened access | Multiple levels on a perimeter combine via OR | Composite level if AND is needed; review ingress |
| Wrong Policy ID in IAM Condition | Confused organization ID/project ID or wrong casing in `accessLevels` | List policies/levels, verify exact full name |
| Custom CEL behaves unexpectedly | Attribute unavailable, syntax/semantics mismatch | Attribute reference, negative test cases |
| A team loses access after editing a shared level | Level has multiple consumers | Consumer list, config diff, rollback |
| Cannot create level due to permission error | Missing ACM Editor/Admin or wrong policy scope | IAM at org or policy level, licensing |
| Access level added to perimeter yet data still blocked | IAM, restricted service, egress/ingress, or cross-perimeter source | Analyze violation logs and full policy set |

### 14.2. Isolating IAP vs. Application Errors

When a web app denies access:

1. Verify the **user signed in with the right identity** and belongs to the Google Group granted the IAP role.
2. Verify the **IAM binding on the exact IAP resource** and that the condition uses the exact full access level name.
3. Check the **observed source IP**; compare real egress IP against CIDR rather than trusting the laptop's local private IP.
4. Check **device posture** and Endpoint Verification/MDM reporting status.
5. Check **IAP Data Access audit logs** when enabled; inspect which access levels the request actually satisfied.
6. If IAP passed the request through, inspect app/backend logs, health checks, HTTP status, and application authorization.

A request can satisfy **CorpNet** while failing **CorpManagedDevice**; seeing one access level in logs does not mean all levels passed.

### 14.3. Isolating VPC SC Errors

1. Identify the relevant **perimeter** and **restricted service**.
2. Check whether the caller is inside or outside the perimeter, its identity, source project/VPC, and API method.
3. If inbound from outside: is there an accepted access level or ingress rule?
4. If outbound from inside: is there a valid egress rule?
5. If crossing two perimeters: do both sides permit it?
6. Correlate Cloud Audit Logs with IAM state; never loosen IAM blindly when the root cause is the perimeter.
7. Apply the minimal fix, test in dry-run where fitting, and monitor after rollout.

### 14.4. Account for Caching, Tokens, and Propagation Delays

Updates to Google Group membership, device state, IP/VPN, or policies can take time to propagate across systems and sessions. When a user is denied right after a change, check propagation delay and session state instead of immediately deleting the condition. Analyze log timestamps, principal, request path, and recent changes.

## 15. Capstone Scenario: Sales Admin Portal and Analytics Data

Enterprise **An Thanh** operates:

- **shop-prod-001**: Cloud Run/Compute Engine serving APIs and applications.
- **orders-admin-prod**: order administration web app accessed through IAP.
- **analytics-prod-001**: BigQuery and Cloud Storage holding controlled data.
- **admin-users@example.com**: approved administration group.
- **Office** has stable public egress IPs; remote staff use corporate devices.

### 15.1. Security Requirements

1. Only the admin group may enter **orders-admin**; users must use policy-compliant devices, optionally paired with network conditions based on risk.
2. Analytics data must not be reachable from arbitrary Internet API clients merely because a caller holds an IAM role.
3. Service-account CI/CD tasks must access certain protected APIs under logged workflows, without pretending a human "encrypted device" signal applies to machine workloads.
4. Tightening policies must not cause outages: require staging tests, an audited emergency path, and a rollback plan.

### 15.2. Recommended Design

| Layer | orders-admin portal | BigQuery/Storage analytics-prod |
|---|---|---|
| Identity | SSO/MFA and Google Group **admin-users** | Purpose-built user/service account |
| Context | **CorpManagedDevice** or access level aligned with VPN/remote policy | Access level for external access, or workload-scoped ingress rules |
| Enforcement | **IAP + IAM Condition** | **VPC SC perimeter + ingress/egress rules** |
| IAM | **roles/iap.httpsResourceAccessor** with condition | Least-privilege dataset/bucket IAM roles |
| Network | LB, ingress paths, firewalls eliminating bypass | Routing/Private Google Access and VPC SC config per architecture |
| Operations | IAP audit logs, denied rate, app errors | Violation logs, method/project/source attribution |
| Change safety | Review groups and conditions, negative tests | Dry-run, dataflow source review, rollback |

**Never treat a single access level as universal protection for every system.** Even the same **CorpManagedDevice** level behaves differently depending on enforcement point, client type, IP, device signals, and IAM.

### 15.3. Pre-Release Test Matrix

| Test | Expected IAP admin outcome | Expected VPC SC analytics outcome |
|---|---|---|
| Right group, right IP, compliant device | Allowed through IAP; app still enforces authorization | Allowed only if API/IAM/perimeter all permit |
| Right group, wrong IP, compliant device | Denied if level requires both | IP access level fails; other ingress only works if explicitly designed |
| Right group, right IP, non-compliant device | Denied if device posture is required | Denied via level; check any other ingress rules |
| Outside group, all context valid | **Denied by IAM** | Denied if lacking data IAM permissions |
| CI pipeline using service account | Permitted by IAP only if explicitly designed for that model | Uses ingress/egress rules specifying workload source and IAM |
| Request from another perimeter | Not directly tied to IAP web access | Requires source egress and destination ingress |
| Valid user hitting app bypassing IAP | **Bypass path must be blocked** | Not directly applicable; check target API perimeter |

### 15.4. Practical Trade-Offs

- **Security:** adding context shrinks risk surface, yet IP-only rules allow all devices behind a shared NAT.
- **Availability:** if Endpoint Verification breaks or VPN egress rotates, valid staff can be locked out.
- **Cost:** endpoint management/licenses, operations, audit logs, and VPC SC/Cloud services can incur costs; do not assume Access Context Manager adds a default per-request surcharge without checking official product and license pricing.
- **Scalability:** a level shared by many teams requires clear change control and ownership.

## 16. Practice Exercises

### Exercise A — Evaluate Access Level Logic

An access level requires:

~~~yaml
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Determine the result for four requests:

1. IP inside CIDR, device encrypted, screen lock on.
2. IP inside CIDR, encrypted, but screen lock off.
3. IP outside CIDR, encrypted, screen lock on.
4. IP outside CIDR, device does not report posture.

**Answer:** Only (1) satisfies the level assuming valid device signals; all others fail. Attributes within a single condition combine with **AND**.

### Exercise B — Distinguish ACM, IAP, and IAM

An engineer creates **CorpNet**, grants **roles/iap.httpsResourceAccessor** to the admin group, yet adds **no IAM Condition** referencing CorpNet. Are external non-corporate IPs guaranteed to be rejected?

**Answer:** No. The level is unused as a binding condition, so the IAP policy still allows access via the role alone. Attach the access level in an IAM Condition on the exact IAP resource and audit all other IAM bindings.

### Exercise C — VPC SC Multi-Level Logic

Perimeter **analytics-prod** references two levels: **CorpNet** and **ManagedDevice**. A client outside CorpNet has a passing ManagedDevice. Can the client pass the perimeter's access-level ingress check?

**Answer:** Potentially yes, because multiple access levels on a perimeter combine with **OR**. Afterward the client still needs IAM and any other requirements. To require **both IP and device**, build a composite AND level or design an appropriate ingress rule.

### Exercise D — Reading Logs to Find Errors

VPN users cannot enter the admin portal after IT rotated egress IPs. IAP logs show users authenticated, yet **CorpNet** is missing from satisfied access levels. List:

1. Information to collect.
2. How to verify the real IP seen in requests.
3. Why granting Owner/Editor must not be used to resolve it.
4. Safe CIDR update workflow with review, staging test, and rollback.

**Hint:** adding IAM roles will not fix IP context; inspect VPN/public egress, access level revision, IAM Conditions, and dependent levels. Updating CIDRs requires assessing impact on every consumer.

### Exercise E — Designing Access for Three Principal Types

Design separately for:

- Admin staff accessing an IAP web app via browser.
- A Java service on GKE reading BigQuery in the same perimeter.
- An external pipeline using Workload Identity Federation to deploy Cloud Run and call a VPC SC-protected API.

**Guidance:** web users: IAP + IAM + context; GKE workload: IAM + perimeter behavior + source project/VPC; CI: WIF identity, IAM, ingress/egress rules, and API methods. Never impose browser device policies onto workload tokens.

## 17. Key Takeaways and Official References

**Seven points to remember:**

1. **Access Context Manager defines access levels**; it does not enforce them alone.
2. **Basic levels** combine attributes within a condition using AND; across multiple conditions use **combineFunction=AND or OR**.
3. **Custom levels** use CEL with supported attributes and licenses; test both positive and negative cases.
4. **IAP** can evaluate **request.auth.access_levels** in IAM Conditions on supported IAP roles. Do not apply this attribute blindly to standard IAM roles across all Google Cloud APIs.
5. **VPC Service Controls** can use access levels to allow external requests into a perimeter; listed access levels use OR semantics; **ingress/egress** and IAM remain essential.
6. **IP, geolocation, and device posture** each have limits; no single signal replaces MFA, IAM, or endpoint management.
7. Any edit to an access level referenced by multiple apps requires **review, testing, logging, and rollback**.

**Official Google Cloud documentation:**

1. [Access Context Manager overview](https://docs.cloud.google.com/access-context-manager/docs/overview) — access policies, basic/custom levels, and context mechanics.
2. [Access level attributes](https://docs.cloud.google.com/access-context-manager/docs/access-level-attributes) — IP subnetworks, regions, members, devicePolicy, and requiredAccessLevels.
3. [Create a basic access level](https://docs.cloud.google.com/access-context-manager/docs/create-basic-access-level) — YAML conditions and gcloud.
4. [Custom access levels](https://docs.cloud.google.com/access-context-manager/docs/custom-access-levels) — CEL and Advanced Mode.
5. [Access Context Manager access control](https://docs.cloud.google.com/access-context-manager/docs/access-control) — IAM roles and permission scopes.
6. [Create an access policy](https://docs.cloud.google.com/access-context-manager/docs/create-access-policy) — organization-level/scoped policies.
7. [Set up context-aware access with IAP](https://docs.cloud.google.com/iap/docs/cloud-iap-context-aware-access-howto) — IAM conditional bindings and IAP audit logs.
8. [IAM Conditions attribute reference](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference) — scope of **request.auth.access_levels**.
9. [Use access levels with VPC Service Controls](https://docs.cloud.google.com/vpc-service-controls/docs/use-access-levels) — perimeter ingress and limitations.
10. [VPC Service Controls ingress and egress rules](https://docs.cloud.google.com/vpc-service-controls/docs/ingress-egress-rules) — access boundaries and data flows.
11. [gcloud access-context-manager levels create](https://docs.cloud.google.com/sdk/gcloud/reference/access-context-manager/levels/create) — CLI reference and basic/custom spec formats.
