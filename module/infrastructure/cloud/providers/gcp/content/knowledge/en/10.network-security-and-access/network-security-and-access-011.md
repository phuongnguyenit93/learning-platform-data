# VPC Service Controls and Building a Service Perimeter

When an enterprise stores order data in Cloud Storage or analyzes customer data in BigQuery, **IAM** decides which identity may read or modify data. However, if an authorized credential is stolen, someone holding that credential might try calling APIs from an untrusted environment or copying data into another project. **VPC Service Controls (VPC SC)** adds another defensive layer: creating a **service perimeter** around Google Cloud resources and governing API calls crossing that boundary.

This lesson belongs to the **Network Security and Access** chapter in the `CLOUD_PROVIDERS_GCP` module. After learning project organization, IAM, and VPC, learners can apply this knowledge when building systems with Compute Engine, GKE, Cloud Run, Cloud Storage, BigQuery, and databases—choosing the right services, protecting data, controlling releases, and monitoring reliability and cost.

VPC Service Controls is **not a network firewall**, does not replace IAM, and does not support every Google Cloud API. This guide covers the design model, deploying via **dry-run before enforced**, defining ingress/egress rules, and troubleshooting errors without accidentally disrupting workloads.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the data-exfiltration risks VPC Service Controls helps mitigate and its remaining limitations.
2. Distinguish **access policy**, **service perimeter**, **restricted services**, **protected resources**, **access levels**, **ingress/egress rules**, and **VPC accessible services**.
3. Design a perimeter for one or more Google Cloud projects, understanding its impact on applications and CI/CD.
4. Identify when requests must cross boundaries and how to allow only the exact identity, source, service, method, and destination.
5. Design private access to Google APIs using `restricted.googleapis.com` where appropriate.
6. Create a dry-run configuration, inspect violation logs, and define criteria for promoting to enforced mode.
7. Diagnose perimeter-related `403` errors without confusing them with IAM, DNS, firewall, or quota errors.
8. Build operational, change-management, and safe recovery checklists for production environments.

## 1. Why Is IAM Not the Sole Data Protection Layer?

Suppose the Commerce team has:

- Project `commerce-secure` holding bucket `order-exports` and sensitive BigQuery datasets.
- Service account `orders-etl@commerce-secure.iam.gserviceaccount.com` granted IAM permissions to read required data.
- Project `experiments-sandbox` strictly for experimentation, outside the sensitive data zone.
- An unauthorized actor who obtains a valid access token for the ETL service account.

With IAM alone, that actor could attempt to exercise those granted permissions from an untrusted location. VPC Service Controls helps block calls to **protected services** or actions crossing the **service perimeter** that violate policy.

~~~mermaid
flowchart LR
    O["Untrusted client<br/>or sandbox project"]
    P["Service perimeter: data-secure"]
    S["Project: commerce-secure"]
    G["Cloud Storage / BigQuery<br/>restricted services"]
    W["Valid workload<br/>inside perimeter"]
    O -->|"Does not match ingress policy"| X["Denied by VPC SC"]
    W -->|"Valid request"| P
    P --> S --> G
~~~

Points to emphasize:

- **IAM** checks identity and permissions on resources.
- **VPC SC** enforces access boundaries for **supported and configured restricted APIs/services**.
- **VPC firewalls, routing, DNS, and TLS** govern or secure transport at the network and application layers.
- **Application security, data classification, auditing, and DLP** remain necessary for comprehensive data protection.

**Warning:** A perimeter does not prevent every form of data leakage. For instance, an authorized workload reading data could still send that content to an external host over a channel outside VPC SC's scope. Therefore, combine network egress controls, proxies, least-privilege IAM, logging, and incident-response processes.

## 2. What Does VPC Service Controls Protect?

VPC SC establishes a **logical security boundary** around configured Google Cloud resources. When an API call targets a service listed in **restricted services**, perimeter policy is evaluated to decide whether the call may cross the boundary.

### 2.1. Core Components

| Component | Function | Example |
| --- | --- | --- |
| **Access policy** | Organization-level container holding access levels and service perimeters; managed by Access Context Manager | Policy for organization Atlas |
| **Regular service perimeter** | Defines protected projects or VPC networks and which services to restrict | `data-secure` |
| **Protected resources** | Projects or VPC networks declared inside the perimeter per supported capabilities | `projects/111111111111` |
| **Restricted services** | List of APIs for VPC SC-integrated products to enforce at the boundary | `storage.googleapis.com`, `bigquery.googleapis.com` |
| **Access level** | Context-based access conditions such as source IP, device attributes, or identity where supported | Access from corporate-approved environments |
| **Ingress policy** | Specifies which **external** API clients may call **internal** perimeter resources and with which operations | Partner uploader writing objects to a bucket |
| **Egress policy** | Specifies requests from **internal** sources to resources **outside** the perimeter | Job allowed to write aggregated data to a reporting project |
| **VPC accessible services** | Restricts which Google APIs may be called from VPC networks inside the perimeter | Approved services only |
| **Enforced configuration** | Active policy blocking violating requests | Blocks unauthorized API calls |
| **Dry-run configuration** | Evaluates proposed policy and logs violations without blocking via the dry-run config | Test impact before production |

### 2.2. Perimeter Scope and Resource Hierarchy

~~~mermaid
flowchart TD
    O["Organization Atlas<br/>Access Context Manager policy"]
    F["Folder Production"]
    P["Project commerce-secure<br/>number: 111111111111"]
    Q["Project analytics-secure<br/>number: 222222222222"]
    X["Project experiments-sandbox<br/>outside perimeter"]
    SP["Regular perimeter: data-secure"]
    O --> F
    F --> P
    F --> Q
    O --> X
    SP -. "Protected per configured membership" .-> P
    SP -. "Protected per configured membership" .-> Q
~~~

**A perimeter is not simply an IAM folder.** Even though org/folder diagrams help governance, perimeter membership must be specified by **project number** or full VPC network resource name as supported. Moving a project between folders must not be assumed to automatically add or remove it from a perimeter the way IAM inheritance works.

Within an access policy, a project typically belongs to at most **one regular perimeter in enforced mode** and at most one regular perimeter in its corresponding dry-run configuration. Before adding an active project into a new perimeter, check existing memberships and plan migration carefully to avoid conflicts or unintended disruptions.

### 2.3. Protected Service vs. Enabled Service

Enabling the Cloud Storage API on a project is a **Service Usage** action. Adding `storage.googleapis.com` to **restricted services** tells VPC SC to enforce perimeter rules on that integrated API. The two actions do not substitute for one another.

**Never assume every GCP product is protected by VPC SC.** Supported products and integration caveats vary by service and change over time. Before deploying, consult [Supported products and limitations](https://cloud.google.com/vpc-service-controls/docs/supported-products) for each API. Even supported products may have specific methods, tasks, or integration flows with limitations.

## 3. When a Call Is Blocked: Source, Destination, and Service Locations

Consider three scenarios:

| Flow | Meaning from perimeter perspective | Design approach |
| --- | --- | --- |
| ETL running in `commerce-secure` reads a bucket in the same perimeter | Internal access within the same boundary for a protected service | IAM and related policies still must allow it |
| Laptop outside perimeter uses `gcloud storage` to read a bucket inside perimeter | **Ingress**: external client accessing internal resource | Narrow access level or ingress rule, plus IAM |
| Job inside perimeter writes results to `experiments-sandbox` outside perimeter | **Egress**: internal source/resource calling external resource | Appropriate egress rule and source/target scoping |

**VPC SC ingress and egress are not defined simply by which way bytes move.** They describe the API client's and resource's relationship to the boundary. For example, **reading** an object from inside the perimeter by an external client is still **ingress**; **writing** data to an external project can be **egress**.

### 3.1. Calls Involving Multiple Resources

A single command copying an object from a bucket in perimeter A to a bucket outside perimeter A can touch **two resources and one API method**. You must evaluate policies across **all participating resources**.

When the destination resides in **another perimeter B**, you may need:

- An appropriate **egress rule** on perimeter A.
- An appropriate **ingress rule** on perimeter B.
- Additional egress/ingress rules if the API touches multiple resources or access directions.
- IAM for the service account, source data, and destination; VPC SC never grants permissions itself.

~~~mermaid
flowchart LR
    A["Perimeter A<br/>Source data project"]
    EA["Egress policy A"]
    IB["Ingress policy B"]
    B["Perimeter B<br/>Destination project"]
    A --> EA --> IB --> B
    IAM["IAM and service policies"]
    IAM -. "Still checked" .-> B
~~~

An egress rule on A **does not override** B's ingress policy. When designing cross-team data sharing, both sides' policies must align.

## 4. Perimeters and Other Security Layers

| Mechanism | Question it answers | Do not confuse with |
| --- | --- | --- |
| **IAM allow/deny** | Does the identity hold permission to invoke an API/action on the resource? | VPC SC source–destination boundary |
| **VPC Service Controls** | May a request to a **restricted service** cross the logical boundary? | Standard TCP/UDP firewall |
| **VPC firewall rules** | Are packets from source IP permitted to destination IP/port? | Cloud Storage object read permissions |
| **Cloud NAT** | Can private resources translate IPs to reach the Internet? | Restricted services list |
| **Private Google Access / Private Service Connect** | How do private workloads reach Google APIs over private paths? | VPC SC access policy |
| **Cloud Armor** | Should HTTP client traffic to a protected endpoint be blocked by security policy? | Google API service ingress/egress governance |
| **Organization Policy** | Which infrastructure configurations does the organization permit? | API data boundary perimeter |
| **Cloud Audit Logs** | Which actions/violations were recorded? | Access permission configuration |

**A successful Cloud Storage call generally requires valid IAM, working network paths, and VPC SC allowance when the service/resource sits in a perimeter.** Receiving `403` alone is not enough to blame a single layer.

## 5. Enforced vs. Dry-Run: Choosing a Safe Rollout Path

VPC SC provides two configuration evaluation modes:

### 5.1. Enforced Mode

An **enforced** configuration blocks requests to protected services that violate the perimeter. For instance, a developer machine outside the perimeter lacking a matching ingress rule may receive:

~~~text
Error 403: Request is prohibited by organization's policy.
~~~

In production, enabling enforced mode without preparation can break CI/CD pipelines, BigQuery queries from notebooks, Cloud Storage calls from apps in other projects, log exports, or backup workflows.

### 5.2. Dry-Run Mode

**Dry-run** simulates a configuration: logging requests that **would be denied if enforced** while **not blocking them** due to the dry-run config itself.

~~~mermaid
flowchart TD
    A["Propose a new perimeter"] --> B["Create dry-run config"]
    B --> C["Run live workloads and use cases"]
    C --> D["Collect VPC SC dry-run violations"]
    D --> E["Classify legitimate vs. unauthorized traffic"]
    E --> F{"Any valid calls flagged as blocked?"}
    F -->|Yes| G["Adjust design, ingress/egress, access levels"]
    G --> C
    F -->|No| H["Approve change, schedule enforcement"]
    H --> I["Monitor 403s/violations after enforcement"]
~~~

Understand clearly: a perimeter can hold **enforced and dry-run** configurations side by side. Dry-run tests **proposed changes relative to** enforced; calls already blocked by an active enforced config will not "pass through" merely because dry-run permits them. Access levels have no separate dry-run mode: to test a new access level condition, create a new access level and reference it in the dry-run spec.

**Dry-run is safer, yet does not replace functional testing.** A month-end batch job, disaster-recovery workflow, service agent, or infrequent pipeline might emit no logs during a short dry-run window.

## 6. Designing a Perimeter for Data Systems

Suppose an enterprise has four resource groups:

| Illustrative project | Role | Design choice |
| --- | --- | --- |
| `commerce-secure` | Buckets and BigQuery holding sensitive data | Inside perimeter `data-secure` |
| `analytics-secure` | ETL and internal reporting BigQuery | Same perimeter if trust level aligns |
| `ci-deploy` | Deployment pipelines outside data scope | Outside perimeter; narrow ingress rule for valid API calls |
| `experiments-sandbox` | Testing without real data | Outside perimeter; blocked from accessing protected data by default |

### 6.1. Design Around Trust Boundaries, Not Convenience

If two projects share the same protection level, exchange data frequently, and have the same owner, placing them in one perimeter reduces cross-boundary rules. However, never lump **every project in the organization** into a single perimeter just to avoid authoring policies; that renders the security boundary meaningless.

One design option:

~~~mermaid
flowchart TB
    subgraph DATA["Service perimeter data-secure"]
        P1["commerce-secure"]
        P2["analytics-secure"]
        S1["Cloud Storage"]
        S2["BigQuery"]
        P1 --> S1
        P2 --> S2
    end
    CI["CI/CD project or external provider"]
    DEV["Developer laptop"]
    EXP["experiments-sandbox"]
    CI -. "Restricted ingress rule" .-> DATA
    DEV -. "Only if approved" .-> DATA
    DATA -. "Egress only for approved export flows" .-> EXP
~~~

Dashed lines in the diagram represent **policy-controlled possibilities**, not default open paths.

### 6.2. Inventory All Dependencies Before Enforcing

A data project can depend on:

- Cloud Run/Compute Engine/GKE calling Storage/BigQuery from the same or different projects.
- BigQuery jobs, scheduled queries, and cross-project datasets.
- Dataflow/Cloud Composer/managed services and **service agents**.
- CI/CD pipelines, Terraform/GitOps, workload identity federation.
- Log sinks, security tooling, backup/restore, and data exports.
- Operations staff using Console, Cloud Shell, workstations, or VPN.
- APIs in external projects or services not supporting VPC SC.

For **managed services**, service agents and service-to-service calls can have specialized VPC SC behavior; check product documentation for constraints. **Never add wildcards or `ANY_IDENTITY` to silence every `403`**.

## 7. Ingress Policy: Conditionally Allowing External Sources Inward

An **ingress rule** has two main parts:

- `ingressFrom`: permitted **API client sources** and **identities**.
- `ingressTo`: **restricted services/operations** and **target resources inside the perimeter**.

Conditions in both parts must match. Multiple rules can exist; a request only needs to match one valid rule in the ingress set while still passing all other authorization layers.

### 7.1. Ingress Example by Service Account and Source Project

Suppose service account `partner-import@partner-ingest.iam.gserviceaccount.com` runs in project `partner-ingest` (project number `333333333333`), and is authorized to **create objects** in a bucket inside `commerce-secure` (project number `111111111111`). Illustrative YAML **demonstrating the rule**:

~~~yaml
- title: "partner-object-upload"
  ingressFrom:
    identities:
      - serviceAccount:partner-import@partner-ingest.iam.gserviceaccount.com
    sources:
      - resource: projects/333333333333
  ingressTo:
    resources:
      - projects/111111111111
    operations:
      - serviceName: storage.googleapis.com
        methodSelectors:
          - permission: storage.objects.create
~~~

Verify method/permission support against the service's **VPC SC method restrictions**. The source service account must also hold **actual IAM permission** to create objects in the bucket, and the application must execute from that source context. The rule does not grant `roles/storage.objectCreator`.

**Note:** This YAML snippet is educational content, **not an auto-generated config file**; apply it to a live perimeter only with authorization and change approval.

### 7.2. Access Levels in Ingress

Access levels created in **Access Context Manager** express supported conditions on source IP, device posture, or identity context. An ingress rule can reference an access level instead of allowing an entire source project.

Example policy statement:

> Allow only specific user accounts, from approved networks satisfying the access level, to read protected project data via permitted APIs.

**Avoid using `ANY_IDENTITY`, `accessLevel: "*"`, and all methods/resources merely to "avoid errors."** Such values widen the boundary beyond intent. If an emergency broad exception is unavoidable during an incident, set an expiration and owner, then tighten it promptly.

### 7.3. Ingress Is Not an Inbound HTTP Rule

VPC SC ingress **does not open a TCP port** from the Internet to a VM, GKE Pod, or Cloud Run URL. It governs **calls to VPC SC-scoped Google Cloud APIs** from outside the perimeter. Port 443 on an application load balancer must still be protected with dedicated ingress/network/application security controls.

## 8. Egress Policy: Controlling Calls to Resources Outside the Perimeter

An **egress rule** specifies:

- `egressFrom`: identities or sources inside the perimeter allowed to initiate calls.
- `egressTo`: permitted APIs/operations and destination resources outside the perimeter.

Example: an ETL service account in `analytics-secure` is permitted to **write reviewed summary objects** to reporting project `finance-reports` (project number `444444444444`):

~~~yaml
- title: "publish-approved-reports"
  egressFrom:
    identities:
      - serviceAccount:etl-exporter@analytics-secure.iam.gserviceaccount.com
  egressTo:
    resources:
      - projects/444444444444
    operations:
      - serviceName: storage.googleapis.com
        methodSelectors:
          - permission: storage.objects.create
~~~

This illustrates a **conceptual policy scoped by principal, permission, and target project**. In practice, check whether the request invokes auxiliary APIs/methods, whether data export is approved, and which perimeter owns the destination project.

If `finance-reports` sits inside **another perimeter**, verify the **destination perimeter's ingress policy** as well. Beyond VPC SC, IAM on the destination bucket must still grant write access.

### 8.1. Rules Do Not Replace Data Governance Reviews

An egress rule permits **an API operation**, without knowing whether an object contains PII, secrets, or safely aggregated data. For sensitive data, pair with approval workflows, data classification, DLP, and auditing. Whenever feasible, export through a purpose-built, least-privilege pipeline rather than granting write access to arbitrary external buckets.

### 8.2. Perimeter Bridges

Some legacy documentation/configs use **perimeter bridges** for exchanges across perimeters. For new designs, prefer **explicit ingress/egress rules** because they constrain identities, services, and operations granularly. Never use a bridge to open unrestricted two-way access without evaluating security consequences and current product limits.

## 9. VPC Accessible Services: An Internal API Allowlist Layer

**VPC accessible services** restricts which Google APIs clients inside a perimeter's VPC networks can access, beyond just protecting restricted services at the perimeter boundary.

For example, security might restrict workloads inside the VPC to only approved APIs such as Cloud Storage and Cloud Logging, shrinking exposure to other Google services.

**Distinction:**

- **Restricted services:** services for which the perimeter enforces boundary controls.
- **VPC accessible services:** services that VPC clients inside the perimeter are permitted to reach under an additional allowlist policy.

Do not enable VPC accessible services restrictions blindly for all workloads. An application may rely on the IAM Credentials API, Artifact Registry, or other services during deployment; missing an API from the allowlist breaks workloads even when IAM is valid.

Build the allowed-services list from a **dependency inventory**, not by guessing two primary data APIs. Some configurations support `RESTRICTED-SERVICES` to reference the restricted services set, subject to feature rules.

## 10. Private Connectivity with restricted.googleapis.com

A logical perimeter alone does not force packets onto private network paths. When workloads with private VPC IPs need to call Google APIs while minimizing exposure to non-VPC-SC APIs, configure **Private Google Access** with the **restricted VIP**.

### 10.1. Restricted VIP and Private VIP

| DNS/VIP | IPv4 range | Typical purpose |
| --- | --- | --- |
| `restricted.googleapis.com` | `199.36.153.4/30` | Access VPC SC-supported Google APIs/services privately; blocks services unsupported on the restricted VIP |
| `private.googleapis.com` | `199.36.153.8/30` | Access most Google APIs privately, including some services not yet supporting VPC SC |
| Default `*.googleapis.com` endpoint | Depends on DNS/service | Does not automatically enforce restricted VIP limitations |

**The restricted VIP does not replace IAM or ingress/egress policies.** Requests to VPC SC-protected services still undergo perimeter checks regardless of endpoint; the restricted VIP adds a **layer reducing leakage risk** by disallowing unsupported non-VPC-SC APIs on that path.

If a workload must use a service unsupported by VPC SC, `private.googleapis.com` or Private Service Connect with `all-apis` may fit, provided you review **service patterns** and compensating controls because allowing broader non-VPC-SC APIs widens risk exposure.

### 10.2. Components to Configure

For VMs with internal IPs in a private subnet:

1. Enable **Private Google Access** on the subnet.
2. Configure **Cloud DNS private zones/response policies** per docs so target Google API domains resolve to `restricted.googleapis.com`.
3. Ensure a route to `199.36.153.4/30` with next hop **default internet gateway** per Google Cloud networking design. Despite that next-hop name, traffic to the restricted VIP stays inside Google's network and does not traverse the public Internet.
4. Permit egress firewall rules to the restricted VIP on TCP 443 and any extra ranges required by service docs.
5. Verify DNS, routes, TLS, identity/IAM, and VPC SC outcomes.
6. For hybrid access over Cloud VPN/Interconnect, follow the **Private Google Access for on-premises hosts** guide.

~~~mermaid
flowchart LR
    VM["Private VM/GKE workload"]
    DNS["Private DNS mapping<br/>*.googleapis.com"]
    VIP["restricted.googleapis.com<br/>199.36.153.4/30"]
    API["Supported Google APIs"]
    PER["VPC SC perimeter evaluation"]
    VM --> DNS --> VIP --> API
    API --> PER
~~~

**Do not confuse `default internet gateway` in the route with sending requests over the public Internet.** However, to block other Internet paths, manage remaining routes/firewalls separately. Never delete the default route without first verifying the path to the restricted VIP, or workloads may lose all access to Google APIs.

### 10.3. Cloud NAT Does Not Solve Everything

Cloud NAT provides outbound Internet egress for private workloads; it **does not restrict calls to only VPC SC-supported Google APIs**. Therefore, when protecting data via Google APIs is the primary goal, prioritize evaluating the restricted VIP, VPC egress controls, IAM, and perimeters rather than relying solely on NAT IPs.

## 11. Applying Across Compute Engine, GKE, Cloud Run, and CI/CD

| Workload type | What to check for VPC SC | Common oversights |
| --- | --- | --- |
| **Compute Engine VM** | Project/VPC membership, VM identity, restricted services, DNS/VPC path | VM has valid IAM yet wrong routing/DNS or perimeter mismatch |
| **GKE workload** | Cluster project, Workload Identity Federation, called APIs, network origin | KSA/IAM SA, service agents, artifact fetching, node/Pod egress |
| **Cloud Run** | Service project, VPC egress config, Google APIs, service integrations | Not every HTTP request to a Cloud Run URL is an API call to a restricted service |
| **Cloud Storage** | Bucket project, principal, `objects.get/create` methods, cross-project flows | Object copies can span multiple resources/perimeters |
| **BigQuery** | Job project, datasets, cross-service connections/exports | Jobs and datasets residing in separate projects |
| **CI/CD/Terraform** | Runner location, identity, deployment APIs, service agents | External pipelines may need matching ingress rules |
| **External developer/Cloud Shell** | API client origin, access level, identity, API method | Console/CLI queries hit 403 despite user holding IAM roles |
| **On-premises/hybrid** | Origin via VPN/Interconnect, landing-zone VPC, IP context, Private Google Access | Network connectivity does not grant perimeter access |

### 11.1. Do Not Confuse API Boundaries with Application HTTP Ingress

A Cloud Run service accepts client HTTP requests per **Cloud Run ingress settings** and its own IAM authentication. VPC SC protects integrated, restricted APIs/resources—it **does not replace** app URL controls, API Gateway, Cloud Armor, or HTTPS load balancers.

### 11.2. Service Agents and Automated Systems

Many managed services rely on service agents or invoke multiple APIs on your behalf. For instance, a pipeline loading data into BigQuery might read Cloud Storage objects from another project, write logs to a central project, and decrypt keys via Cloud KMS. Allowlisting only the primary application principal still leaves valid background flows blocked.

Build a **dependency map**: actual principals, execution locations, API methods, source–destination projects, network conditions, schedules, and owners for every integration. Never grant `ANY_SERVICE_ACCOUNT` everywhere as a shortcut.

## 12. Safe Hands-On: Preparing a Dry-Run Service Perimeter

**Commands in this section are illustrative examples for a test environment with organization-admin privileges—not for student accounts on arbitrary projects.** Creating or modifying a service perimeter is an organization-level policy change that can impact multiple projects and cause outages if the wrong project is selected. Obtain Cloud Security team approval first.

### 12.1. Verify Permissions, Access Policy, and Project Numbers

Access Context Manager is managed at the organization level. You need appropriate service perimeter / Access Context Manager permissions and must identify the right **access policy ID**.

~~~bash
# Check active CLI identity and project; does not modify IAM
gcloud auth list
gcloud config get-value project

# List access policies visible to you
gcloud access-context-manager policies list

# List perimeters within an access policy
gcloud access-context-manager perimeters list \
  --policy=ACCESS_POLICY_ID
~~~

For resource members, use the **project number** formatted as `projects/PROJECT_NUMBER`, **never an arbitrary project ID**. Before deploying, confirm which perimeter currently contains each project and whether the policy has existing enforced/dry-run configurations to preserve.

### 12.2. Sample Dry-Run Perimeter Creation

Hypothetical example:

~~~text
Access policy ID: 123456789012
Perimeter name: CommerceDataTrial
Project numbers: 111111111111,222222222222
Restricted services: storage.googleapis.com,bigquery.googleapis.com
Mode: dry-run only
~~~

Illustrative command:

~~~bash
gcloud access-context-manager perimeters dry-run create CommerceDataTrial \
  --perimeter-title="Commerce Data Trial" \
  --perimeter-type=regular \
  --perimeter-resources=projects/111111111111,projects/222222222222 \
  --perimeter-restricted-services=storage.googleapis.com,bigquery.googleapis.com \
  --policy=123456789012
~~~

This command **creates a dry-run configuration**; it does not create buckets, projects, or service accounts. However, it **writes to the Access Context Manager policy** and will fail if permissions, quotas, membership, or organization rules are unmet. Execute only when approved. If an enforced perimeter already exists in the policy, plan an update to its **dry-run configuration** rather than creating arbitrary duplicate perimeters.

**The service list above is strictly an educational example**, not a complete list for production protection. Google Cloud documentation recommends identifying all relevant supported services and backing integrations before enforcing.

### 12.3. Inspect Created Configuration

~~~bash
gcloud access-context-manager perimeters describe CommerceDataTrial \
  --policy=123456789012

gcloud access-context-manager perimeters list \
  --policy=123456789012
~~~

In the output, distinguish **`status`** (enforced config) from **`spec`** and **`useExplicitDryRunSpec`** (dry-run config/API), rather than glancing at a single field to assume whether a policy is enforced.

### 12.4. Test Valid Use Cases

Have application teams execute a representative workload suite:

- VM/GKE/Cloud Run inside the perimeter reading objects in protected buckets.
- Internal BigQuery jobs querying approved project datasets.
- CI/CD pipelines executing valid deployments.
- Developers running authorized CLI commands per workflow.
- Backup/restore, log sinks, and service agents operating.
- Controlled valid data-export flows to external projects.

Then, owners and Security review dry-run violations, classify mandatory flows, design minimal ingress/egress rules, and iterate until no unintended violations remain across tested scenarios.

## 13. Reading VPC Service Controls Violation Logs

VPC SC surfaces violation telemetry through **Cloud Audit Logs**, with key details inside `protoPayload.metadata`.

Important fields to inspect:

| Metadata field | Role |
| --- | --- |
| `dryRun` | Indicates whether the entry is a dry-run evaluation or an enforced violation |
| `violationReason` | Reason the perimeter rejected/flagged the call |
| `resourceNames` | Involved resources |
| `vpcServiceControlsUniqueId` | Unique violation identifier for correlation |
| `vpcServiceControlsTroubleshootToken` | Token for the VPC SC troubleshooting analyzer |
| `securityPolicyInfo` | Related perimeter/policy metadata |
| `egressViolations` | Details of violated egress conditions if applicable |

Additional fields may report principal, method, service, project, or access origin depending on the service and logging setup. Some fields may be redacted for security or permission reasons.

### 13.1. Filtering Dry-Run Logs

In **Logs Explorer**, start with:

~~~text
log_id("cloudaudit.googleapis.com/policy")
AND severity="ERROR"
AND protoPayload.metadata.dryRun=true
~~~

Or via CLI:

~~~bash
gcloud logging read \
  'log_id("cloudaudit.googleapis.com/policy") AND severity="ERROR" AND protoPayload.metadata.dryRun=true' \
  --project=PROJECT_ID \
  --limit=50
~~~

Queries return results within **the log scope you are authorized to view**. One project may not show every violation across the organization. Across multiple projects, route via an **aggregated log sink** to a secured, access-controlled destination; log export, BigQuery storage, and queries can incur costs.

### 13.2. Filtering Enforced Violations

If an app gets `403` after enforcement, check Policy Audit Logs for the violation reason. Common messages/reasons relate to:

- `RESOURCE_NOT_IN_SAME_SERVICE_PERIMETER`: involved resources do not share the same perimeter in a single call.
- Failing to match an **ingress rule** or **access level** for an external client.
- Failing to match an **egress rule** when calling external resources.
- Incomplete propagation of a recent perimeter edit.

Exact error codes and payload details vary across services/APIs and over time; **never rely on a single log string as the sole diagnostic indicator**.

### 13.3. Violation Triage Sequence

~~~mermaid
flowchart TD
    A["403 or dry-run violation"] --> B["Identify service, API method, principal, and source"]
    B --> C["Identify target project/resource and perimeter membership"]
    C --> D{"Are IAM and networking valid?"}
    D -->|No| E["Fix IAM/DNS/routes/firewalls per root cause"]
    D -->|Yes| F{"Ingress, egress, or cross-perimeter?"}
    F --> G["Check from → to rules, permissions, and identities"]
    G --> H["Test narrow rule in dry-run"]
    H --> I["Assess risk then approve enforced update"]
~~~

**Never fix errors by removing the project from the perimeter, disabling VPC SC, or allowing all principals** unless executing an approved emergency response with an accountable owner and recovery plan.

## 14. Distinguishing 403 Errors: IAM, VPC SC, and Service Issues

The same HTTP `403 PERMISSION_DENIED` status can stem from multiple causes.

| Indicator | Likely cause | How to verify |
| --- | --- | --- |
| Message mentions `organization's policy` and Policy Audit Logs show a VPC SC violation | Blocked by service perimeter | Inspect ingress/egress, source context, membership, restricted services |
| Message cites missing `storage.objects.get` or similar permission, with no VPC SC log | Missing IAM permission or IAM deny policy | Inspect IAM bindings, IAM Deny, and Policy Troubleshooter |
| Cannot resolve Google API hostname | Cloud DNS / Private Google Access issue | Private DNS zone, restricted VIP, resolver |
| TCP timeout instead of HTTP response | Route, firewall, private connectivity, or proxy/egress issue | VPC routes, firewall logs, Connectivity Tests |
| `401 UNAUTHENTICATED` | Invalid credential/ADC/token | Check workload auth, service account, token |
| Service unsupported by VPC SC via restricted VIP | API blocked on VIP path | Check supported products; design private VIP/PSC + compensating controls |
| Fails only right after policy update | Propagation delay or mis-scoped rule | Compare enforced/dry-run, timestamps, rollback plan |
| Data in one project, BigQuery job in another | Cross-project / multi-resource request | Verify job project and dataset project, ingress/egress on both sides |

Service perimeter updates take time to propagate. Google Cloud notes perimeter updates can take **up to roughly 30 minutes** to take effect globally; never judge protection status from a single call immediately after an edit.

### 14.1. Why Does "Signed In with the Right Account" Still Fail?

A developer holds `roles/storage.objectViewer` on a bucket yet runs `gcloud` from a laptop outside the perimeter. **IAM permits it**, whereas the **ingress policy does not allow that source and identity**, so the request is rejected. Always analyze the full tuple: **identity + source context + method + resource + perimeter**, not merely the login account.

### 14.2. Why Does "App Running in the Same VPC" Still Fail?

Perhaps the project or VPC belongs to a different perimeter, the target API resides in another perimeter, an out-of-scope service agent is invoked, or the request touches another external resource. **Sharing a subnet/VPC or having VPN connectivity** does not imply VPC SC approval.

## 15. Controlled Promotion to Enforced Mode

Before enforcing a production perimeter:

1. **Lock scope:** project numbers, VPC networks (if applicable), supported services, data classes, owners.
2. **Finalize API flow map:** workloads, principals, internal/external resources, methods, and release flows.
3. **Run dry-run thoroughly:** cover daily runs, scheduled jobs, simulated incidents, backup/restore, CI/CD, and admin tasks.
4. **Tighten exceptions:** strip `ANY_IDENTITY`, `accessLevel: "*"`, or all-APIs wildcards unless strictly justified.
5. **Verify IAM/networking:** VPC SC is a complementary boundary and does not fix broken permissions or routes.
6. **Prepare monitoring:** logs, `403` dashboards, alerts, on-call owners, and violation-log access.
7. **Prepare rollback:** narrow ingress/egress adjustments, revert to prior policy, or approved incident runbook.
8. **Follow change management:** agree on change window, approvers, and post-deploy verifiers.
9. **Monitor after enforcing:** verify approved flows and inspect all denied requests.
10. **Review periodically:** whenever adding projects, altering pipelines, service accounts, or Google Cloud API integrations.

**Never treat "zero dry-run violations" as proof of complete safety** if live workloads never ran during the observation window.

### 15.1. Runbook When a Production App Is Blocked

- Record timestamp, project, API method, principal, full resource name, and request ID if available.
- Inspect VPC SC violation logs, effective perimeter membership, and enforced configuration.
- Determine whether the flow is legitimate or an intended policy block.
- If legitimate, design the **narrowest** rule restoring it without opening the whole boundary.
- Validate the fix in dry-run or a prod-like environment where possible.
- Apply via emergency change process and monitor results after propagation.
- Update the dependency inventory and analyze why the flow was missed earlier.

## 16. Protecting Data Does Not Mean Blocking All Egress

A dangerous mistake is assuming placing a project inside a perimeter blocks **every** data exfiltration vector.

VPC Service Controls governs boundaries for **supported Google Cloud services via integrated APIs/flows**. It does not automatically control:

- Arbitrary TCP/UDP traffic to the Internet from VMs/GKE.
- Applications legitimately reading data and then posting it over HTTP to an external server.
- Google Cloud services lacking VPC SC integration.
- Misconfigured IAM, leaked service account keys, or public bucket sharing via uncovered paths.
- Data already exported before the policy took effect.

To reduce risk holistically, combine layers:

| Layer | Controls |
| --- | --- |
| **Identity** | Dedicated service accounts, ADC/WIF, least-privilege IAM, restricted impersonation |
| **Data** | Classification, retention, encryption, DLP, sharing and export controls |
| **API boundary** | VPC SC with restricted services, minimal ingress/egress |
| **Network** | Egress firewalls, proxies, Cloud NAT where needed, restricted VIP/Private Service Connect |
| **Application** | Authentication, authorization, input validation, outbound endpoint controls |
| **Operations** | Audit logs, alerts, incident response, policy reviews, and verified rollouts |

### 16.1. Does VPC SC Increase Cost?

Deploying a perimeter may require enabling logging, log exports, Cloud DNS, private network connectivity, or supporting services. **Never assume every supporting component is free.** Overall cost also depends on network topology, workloads, BigQuery queries, log storage, and operational effort. Review pricing for each related service and set a **Cloud Billing budget** for lab environments.

Note: a misconfigured perimeter policy can break deployments or background jobs, hurting **reliability** far more than direct service costs. Therefore, dry-run testing and controlled rollouts are vital operational investments.

## 17. Capstone Scenario: Protecting Order Data

The Commerce team is preparing order data for production:

- `commerce-secure`: stores invoice objects and transaction tables.
- `analytics-secure`: runs internal ETL and dashboards.
- `ci-deploy`: external deployment pipeline.
- `sandbox-dev`: testing environment, prohibited from reading live data.
- `audit-logs`: centralized monitoring project.

### 17.1. Architectural Option

~~~mermaid
flowchart TB
    subgraph PER["Regular service perimeter: commerce-data"]
        A["commerce-secure<br/>Cloud Storage"]
        B["analytics-secure<br/>BigQuery + ETL"]
        A -->|"Approved internal flow"| B
    end
    CI["ci-deploy<br/>External CI/CD"]
    SB["sandbox-dev"]
    LOG["audit-logs<br/>Log collection"]
    CI -. "Ingress for required APIs only" .-> PER
    PER -. "Conditional egress if needed" .-> LOG
    SB --> DENY["Must not open access for convenience"]
~~~

**Recommended design:**

1. Confirm exactly which two data projects belong in the same perimeter and which supported services must be restricted.
2. List the exact CI/CD operations truly required on protected projects; where possible, separate deployment admin rights from data-read permissions.
3. Inventory automated service flows such as log sinks, service agents, and backups.
4. Create **dry-run**, run the test suite, and inspect violation logs.
5. Add ingress/egress rules only for flows approved by business owners.
6. Configure tight IAM and private networking/restricted VIP as needed.
7. Promote to enforced after change review, monitoring functionality and request latency.
8. Re-evaluate whenever adding GKE/Cloud Run, Dataflow, or new projects.

### 17.2. Security Questions to Answer

| Question | Acceptance criteria |
| --- | --- |
| Can developers read live data from laptops? | Only if explicitly allowed by identity, source, and operation policy; default no |
| Can CI/CD create services without reading objects? | Separate IAM roles and API methods; test least privilege |
| Can ETL jobs export data to the sandbox project? | Default no; exceptions require owner/approval and tight destination scope |
| What if a service agent must write logs outside the perimeter? | Identify exact principal/destination and write a narrow rule per docs |
| How are policy mistakes impacting production caught? | Dry-run, Policy Audit Logs, SLOs, and runbooks |
| Must the perimeter update when resource hierarchy changes? | Verify actual membership and dependencies; never infer from folders |

## 18. Self-Check Exercises

**Question 1.** A developer holds `roles/storage.objectViewer` yet receives a VPC SC `403` when calling a protected bucket from a laptop. Is IAM misconfigured?

*Suggested answer:* Not necessarily. IAM may be sufficient while the ingress policy/access level rejects calls from outside the perimeter. Inspect origin, identity, method, resource, and violation logs.

**Question 2.** Copying an object from a bucket in perimeter A to a bucket in perimeter B. Is adding an egress policy on A always enough?

*Suggested answer:* No. All participating perimeters must allow the request per API requirements; perimeter B likely needs an ingress rule too, alongside verifying methods, all involved resources, and IAM.

**Question 3.** In VPC SC, do ingress/egress correspond directly to upload/download byte direction on a VM NIC?

*Suggested answer:* No. Direction is defined by the API client and resources relative to the perimeter boundary, not merely bytes sent or received.

**Question 4.** Why run dry-run before enforced mode?

*Suggested answer:* Dry-run logs calls that would fail if enforced without blocking them via the dry-run policy. Teams can gather evidence, test CI/CD, handle integrations, and prepare rollbacks.

**Question 5.** Dry-run reports zero violations after 20 minutes. Can you guarantee production will have no outages?

*Suggested answer:* No. Scheduled jobs, recovery tasks, rare workflows, or service agents may not have executed yet.

**Question 6.** Does `restricted.googleapis.com` grant permission to read Cloud Storage?

*Suggested answer:* No. It is a restricted API path/VIP supporting VPC SC; IAM and perimeter policies are still enforced.

**Question 7.** A VM can legitimately read data and post it over HTTPS to an Internet server unprotected by VPC SC. What is missing from the design?

*Suggested answer:* VPC SC does not govern all TCP/HTTP egress. Design egress firewalls/proxies, application policies, DLP, and monitoring to reduce risk.

**Question 8.** A team restricts Cloud Storage and BigQuery, yet workloads need Artifact Registry to deploy. How should this be handled?

*Suggested answer:* Identify Artifact/API dependencies, verify VPC SC integration, and configure VPC accessible services / restricted VIP appropriately. Never open `ANY_IDENTITY` or all APIs indiscriminately.

**Question 9.** Should you pass project ID or project number to `--perimeter-resources=projects/...` in gcloud?

*Suggested answer:* Use the **project number** in the format required by Access Context Manager, e.g., `projects/111111111111`.

**Question 10.** A project is already in enforced perimeter A. Should you create a new enforced perimeter B containing that project to test a new config?

*Suggested answer:* No. Follow membership rules and use dry-run or governed migration workflows instead of creating conflicting enforced memberships.

**Question 11.** Why is an `ANY_IDENTITY` rule allowing all sources and all operations risky even though APIs still check IAM?

*Suggested answer:* It drastically widens the perimeter boundary, negating much of its added protection and exposing data if a credential with valid IAM is stolen. Restrict principal, source, API, operation, and resource.

**Question 12.** After enforcing the policy, a Cloud Run job gets `403` calling BigQuery while a VM in the same project succeeds. What do you check?

*Suggested answer:* Actual principal, API method, involved resources (job project/dataset project), VPC SC source context, ingress/egress, IAM, DNS/egress config, and violation logs—never assume parity merely from sharing a project.

## 19. Implementation and Operations Checklist

- [ ] Clearly identified **data to protect**, owners, and sensitivity levels.
- [ ] Selected the right organization access policy and project numbers.
- [ ] Checked existing enforced/dry-run memberships so projects do not conflict.
- [ ] Cross-checked **supported services and limitations** for every critical API.
- [ ] Inventoried principals, sources, resources, API methods, and service agents.
- [ ] Reviewed Cloud Run/GKE/VM/CI/CD, logs, backups, BigQuery jobs, and admin operations.
- [ ] Designed least-privilege ingress/egress rules with an owner for each exception.
- [ ] Evaluated access levels and VPC accessible services.
- [ ] Verified DNS, routes, firewalls, and restricted VIP if using private connectivity.
- [ ] Ran dry-run over a sufficient window and all key use cases; analyzed violation logs.
- [ ] Prepared change window, monitoring, incident permissions, and rollback plan.
- [ ] Verified critical workloads after enforcement and after propagation.
- [ ] Embedded perimeter reviews into project onboarding and release automation.
- [ ] Planned logging, operational effort, quotas, and associated costs.

## 20. Key Takeaways

- **VPC Service Controls is a boundary layer for supported Google Cloud APIs/data**, complementing rather than replacing IAM.
- **Regular service perimeters** define configured protected resources and restricted services; they are neither VPC firewalls nor IAM folders.
- **Ingress/egress** describes API request direction relative to perimeters and participating resources, not merely data transfer direction.
- **Cross-perimeter** flows may require policies on every involved perimeter; IAM must still permit the action.
- **Dry-run before enforced** is essential to avoid breaking CI/CD, managed services, and business flows.
- **Restricted VIP** provides private paths to VPC SC-supported services while still requiring DNS, routes, firewalls, IAM, and perimeter policies.
- **Investigate violations** via Policy Audit Logs, principal, method, source, resource, and violation reason rather than loosening the entire policy on a `403`.
- **Comprehensive protection** still requires Internet egress limits, credential hygiene, app security, data controls, auditing, and cost management.

When building Google Cloud systems with sensitive data, always answer: **"Which resources sit inside the boundary? Which APIs are protected? Who can call from where, to where, using which method? How do we verify the perimeter blocks unwanted behavior without breaking valid business flows?"**

## Official References

- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Service perimeter details and configuration](https://cloud.google.com/vpc-service-controls/docs/service-perimeters)
- [Supported products and limitations](https://cloud.google.com/vpc-service-controls/docs/supported-products)
- [Create service perimeters](https://cloud.google.com/vpc-service-controls/docs/create-service-perimeters)
- [Ingress and egress rules](https://cloud.google.com/vpc-service-controls/docs/ingress-egress-rules)
- [Configuring ingress and egress policies](https://cloud.google.com/vpc-service-controls/docs/configuring-ingress-egress-policies)
- [Dry run mode for service perimeters](https://cloud.google.com/vpc-service-controls/docs/dry-run-mode)
- [Best practices for enabling VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/enable)
- [VPC Service Controls audit logging](https://cloud.google.com/vpc-service-controls/docs/audit-logging)
- [Troubleshoot VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/troubleshooting)
- [Private Google Access with VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/private-connectivity)
- [Configure Private Google Access](https://cloud.google.com/vpc/docs/configure-private-google-access)
